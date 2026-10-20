"""
Locate an (LLM-copied) passage inside a source text and return the exact
source span.

LLMs asked to quote a passage "verbatim" frequently change whitespace, case or
a punctuation mark. ``find_passage`` finds where the passage really is in the
source and returns the source's own text for that span, so callers can store
the original wording instead of the model's copy. Paraphrases fall below the
similarity threshold and are rejected.

Similarity is ``difflib.SequenceMatcher.ratio()`` (``2*M / (len(a)+len(b))``)
between the normalised passage and the normalised candidate window. Text is
normalised by folding typographic quotes and dashes to ASCII, decomposing
compatibility characters, dropping accents, lowercasing and collapsing
whitespace; an offset map turns a window in normalised text back into an
exact span of the original.

Search strategy:

1. Exact substring match of the normalised passage (similarity 1.0).
2. Size check: a passage longer than ``len(text) * (2-s)/s`` cannot reach
   threshold ``s`` against any window, so it is rejected without a search.
3. Seed voting: the passage is cut into short non-overlapping seeds, each
   seed's occurrences in the text vote for an alignment offset. A window
   scoring ``>= min_similarity`` contains at most ``2P(1-s)/s`` edit points,
   so with that many seeds plus one, at least one seed survives intact and
   votes for the true location. This holds for high thresholds such as 0.95,
   provided that seed is not skipped as too common (more than
   ``SEED_MAX_OCCURRENCES`` hits) and its location ranks among the
   ``MAX_CANDIDATE_REGIONS`` best supported. Seed length is floored at
   ``SEED_MIN_LENGTH``, so low thresholds are best-effort.
4. For each candidate location, one ``SequenceMatcher`` alignment of the
   passage against the surrounding text estimates where the passage starts
   and ends; the window edges are then refined over the few word boundaries
   near those estimates. This is a local search: the result is the best
   window found, not a guaranteed global optimum.

Cost is dominated by step 4: per candidate location, one alignment plus a
bounded number of window scores (independent of the passage length), each a
``SequenceMatcher`` comparison that costs quadratic or more in the passage
length ``P``. The seed lookups are linear in the text length. Measured on
prose: a sentence takes a few milliseconds, a 1 kB passage about 0.1 s, a
2 kB passage up to about 2 s.
"""

from __future__ import annotations

import bisect
import math
import unicodedata
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
from itertools import accumulate
from typing import Callable

# Shortest seed used for voting; shorter seeds match almost anywhere.
SEED_MIN_LENGTH = 4
# Seeds occurring more often than this carry no location signal and are skipped.
SEED_MAX_OCCURRENCES = 64
# Number of distinct candidate locations refined per search.
MAX_CANDIDATE_REGIONS = 5
# Alternating start/end refinement passes per candidate location.
REFINEMENT_PASSES = 2
# Matching blocks shorter than this are ignored when estimating where the
# passage starts and ends; short blocks also match stray text nearby.
EDGE_BLOCK_MIN_LENGTH = 2 * SEED_MIN_LENGTH
# Characters searched for word boundaries on either side of an estimated
# window edge (a few words).
EDGE_SEARCH_MARGIN = 16

_SPACE = " "

# Typographic punctuation folded to ASCII before comparing (LLMs copy curly
# quotes as straight ones and dashes as hyphens), and invisible characters
# dropped. Other compatibility forms are handled by NFKD in fold_char().
_TYPOGRAPHIC_FOLDS = str.maketrans({
    **dict.fromkeys("‘’‚‛′´`", "'"),
    **dict.fromkeys("“”„‟″«»", '"'),
    **dict.fromkeys("‐‑‒–—―−﹘﹣－", "-"),
    **dict.fromkeys("­​‌‍⁠﻿", None),
})
# Combining overlays that negate their base character ("≠" is "=" + U+0338);
# kept so a negated relation never folds to its positive form.
_NEGATION_MARKS = frozenset("\u0338\u20d2\u20e5")
# Distinct characters whose folding is cached (text is mostly a small alphabet).
FOLD_CACHE_SIZE = 4096


@dataclass(frozen=True)
class PassageMatch:
    """Result of :func:`find_passage`.

    A match is either accepted (``start``, ``end`` and ``text`` all set) or
    rejected (all three None); ``__post_init__`` enforces this.

    Attributes:
        similarity: Best similarity found, in [0, 1]. 1.0 for a passage found
            verbatim after normalisation; 0.0 when no candidate location was
            found at all, or the passage is too long to reach the threshold
            against the text. Reported even when the match is rejected.
        start: Start index of the matched span in the original text, or None.
        end: End index (exclusive) of the matched span, or None.
        text: ``original_text[start:end]`` when the match was accepted, else None.
        exact: True when the normalised passage occurs verbatim in the
            normalised text (only case, whitespace, accents, typographic
            variants, compatibility forms such as "²" vs "2", and invisible
            characters differ). An exact span may start or end inside a
            character that folds to several ("ﬁ"), so ``text`` can then hold
            one more letter than the passage.
    """

    similarity: float
    start: int | None = None
    end: int | None = None
    text: str | None = None
    exact: bool = False

    def __post_init__(self) -> None:
        """Reject internally inconsistent results.

        Raises:
            ValueError: If ``similarity`` is outside [0, 1], the span fields
                are only partly set, the span is empty or inconsistent with
                ``text``, or ``exact`` is set on a rejected match.
        """
        if not 0.0 <= self.similarity <= 1.0:
            raise ValueError(f"similarity must be in [0, 1], got {self.similarity}")
        span = (self.start, self.end, self.text)
        if all(field is None for field in span):
            if self.exact:
                raise ValueError("a rejected match cannot be exact")
            return
        if self.start is None or self.end is None or self.text is None:
            raise ValueError("start, end and text must be all set or all None")
        if not 0 <= self.start < self.end or len(self.text) != self.end - self.start:
            raise ValueError(
                f"invalid span start={self.start} end={self.end} for {len(self.text)} chars"
            )

    @property
    def matched(self) -> bool:
        """Whether a span at or above the threshold was found."""
        return self.text is not None


@lru_cache(maxsize=FOLD_CACHE_SIZE)
def fold_char(char: str) -> str:
    """Fold one character to the form passages are compared in.

    Typographic quotes and dashes become ASCII, compatibility characters
    are decomposed (NFKD: "ﬁ" -> "fi", "²" -> "2"), accents and other
    combining marks are dropped (so NFC and NFD spellings compare equal)
    except negation overlays ("≠" stays distinct from "="), and the result
    is lowercased.

    Args:
        char: A single character.

    Returns:
        Zero or more code points; "" for a character that is dropped
        entirely (a combining mark, soft hyphen or zero-width character).
    """
    # Fold before NFKD ("´" would decompose to a bare accent) and after it
    # (NFKD turns "⁻" into U+2212 and "‴" into primes).
    decomposed = unicodedata.normalize(
        "NFKD", char.translate(_TYPOGRAPHIC_FOLDS)
    ).translate(_TYPOGRAPHIC_FOLDS)
    return "".join(
        code_point for code_point in decomposed
        if (code_point in _NEGATION_MARKS or not unicodedata.combining(code_point))
        and not code_point.isspace()
    ).lower()


def normalize_with_offsets(text: str) -> tuple[str, list[int]]:
    """Fold ``text`` and collapse whitespace, keeping a map back to it.

    Each character is folded with :func:`fold_char`. Leading and trailing
    whitespace is dropped and every internal whitespace run becomes one space.

    Args:
        text: Original text.

    Returns:
        ``(normalised, offsets)`` where ``offsets[i]`` is the index in ``text``
        of the character that produced ``normalised[i]`` (for a collapsed
        whitespace run, its first character). Characters folded to nothing
        have no entry.
    """
    chars: list[str] = []
    offsets: list[int] = []
    pending_space = -1
    for index, char in enumerate(text):
        if char.isspace():
            if pending_space < 0 and chars:
                pending_space = index
            continue
        folded = fold_char(char)
        if not folded:
            continue
        if pending_space >= 0:
            chars.append(_SPACE)
            offsets.append(pending_space)
            pending_space = -1
        # Folding can yield several code points ("ﬁ" -> "fi"); map each back.
        for code_point in folded:
            chars.append(code_point)
            offsets.append(index)
    return "".join(chars), offsets


def occurs_once(fragment: str, text: str) -> bool:
    """Whether ``fragment`` occurs exactly once in ``text``.

    Compared the way :func:`find_passage` compares (both sides normalised by
    :func:`normalize_with_offsets`), so copies that differ only in case,
    whitespace, invisible characters or typography count as the same text.
    Overlapping occurrences count too.

    Args:
        fragment: Text to look for (e.g. a matched span of ``text``).
        text: Text to search.

    Returns:
        True if the normalised fragment is non-empty and found exactly once.

    Raises:
        TypeError: If ``fragment`` or ``text`` is not a string.
    """
    if not isinstance(fragment, str) or not isinstance(text, str):
        raise TypeError("fragment and text must be strings")
    norm_fragment, _ = normalize_with_offsets(fragment)
    norm_text, _ = normalize_with_offsets(text)
    if not norm_fragment:
        return False
    first = norm_text.find(norm_fragment)
    return first >= 0 and norm_text.find(norm_fragment, first + 1) < 0


def find_passage(passage: str, text: str, min_similarity: float) -> PassageMatch:
    """Find the best-scoring span of ``text`` it can locate for ``passage``.

    An exact match (after normalisation) is returned as the raw source span
    and may start or end mid-word; a fuzzy match starts and ends on word
    boundaries (unless no boundary lies near an estimated edge).

    Args:
        passage: Passage to locate (e.g. an LLM's "verbatim" quote).
        text: Source text to search.
        min_similarity: Acceptance threshold in (0, 1].

    Returns:
        A :class:`PassageMatch`; ``matched`` is True and ``text`` holds the
        original source wording when the best similarity reaches the threshold.

    Raises:
        TypeError: If ``passage`` or ``text`` is not a string.
        ValueError: If ``min_similarity`` is outside (0, 1].
    """
    if not isinstance(passage, str) or not isinstance(text, str):
        raise TypeError("passage and text must be strings")
    if not 0.0 < min_similarity <= 1.0:
        raise ValueError(f"min_similarity must be in (0, 1], got {min_similarity}")

    norm_passage, _ = normalize_with_offsets(passage)
    norm_text, offsets = normalize_with_offsets(text)
    if not norm_passage or not norm_text:
        return PassageMatch(similarity=0.0)

    exact_at = norm_text.find(norm_passage)
    if exact_at >= 0:
        return _accepted(
            text, offsets, exact_at, exact_at + len(norm_passage), 1.0, exact=True
        )
    if not fits_text(len(norm_passage), len(norm_text), min_similarity):
        return PassageMatch(similarity=0.0)

    max_edits = max_edit_points(len(norm_passage), min_similarity)
    matcher = SequenceMatcher(None, autojunk=False)
    matcher.set_seq2(norm_passage)

    best_similarity, best_start, best_end = 0.0, 0, 0
    for anchor in _candidate_anchors(norm_passage, norm_text, max_edits):
        similarity, start, end = _refine_window(
            matcher, norm_text, anchor, len(norm_passage), max_edits + 1, min_similarity
        )
        if similarity > best_similarity:
            best_similarity, best_start, best_end = similarity, start, end

    if best_similarity >= min_similarity:
        return _accepted(text, offsets, best_start, best_end, best_similarity)
    return PassageMatch(similarity=best_similarity)


def fits_text(passage_length: int, text_length: int, min_similarity: float) -> bool:
    """Whether a passage this long could reach the threshold against the text.

    A window ``W`` of the text matches at most ``W`` characters, so
    ``ratio <= 2W / (P + W) <= 2T / (P + T)``; that bound reaches ``s`` only
    when ``P <= T(2-s)/s``.

    Args:
        passage_length: Length of the normalised passage.
        text_length: Length of the normalised text.
        min_similarity: Acceptance threshold in (0, 1].

    Returns:
        False when no window of the text can score ``>= min_similarity``.
    """
    return passage_length * min_similarity <= text_length * (2 - min_similarity)


def max_edit_points(passage_length: int, min_similarity: float) -> int:
    """Upper bound on edit points in a window scoring ``>= min_similarity``.

    With ``ratio = 2M / (P + W)`` and the longest admissible window
    ``W = P(2-s)/s``, unmatched characters on both sides total at most
    ``(1-s)(P+W) = 2P(1-s)/s``. Each is at most one edit point, and the
    alignment offset can drift by at most that much along the window.

    Args:
        passage_length: Length of the normalised passage.
        min_similarity: Acceptance threshold in (0, 1].

    Returns:
        Non-negative bound on the number of edit points.
    """
    return math.floor(2 * passage_length * (1 - min_similarity) / min_similarity)


def _candidate_anchors(passage: str, text: str, max_edits: int) -> list[int]:
    """Rank text offsets where the passage plausibly starts, by seed votes.

    Args:
        passage: Normalised passage.
        text: Normalised text.
        max_edits: Bound from :func:`max_edit_points`; also the clustering radius.

    Returns:
        Up to ``MAX_CANDIDATE_REGIONS`` offsets (possibly negative), strongest
        first, more than ``max_edits`` apart.
    """
    seed_length = max(SEED_MIN_LENGTH, len(passage) // (max_edits + 1))
    votes: Counter[int] = Counter()
    for seed_start in range(0, len(passage) - seed_length + 1, seed_length):
        positions = _occurrences(text, passage[seed_start:seed_start + seed_length])
        for position in positions:
            votes[position - seed_start] += 1
    if not votes:
        return []

    # Indels shift the offset by up to max_edits, splitting one location's
    # votes over neighbouring offsets: score each offset by its neighbourhood.
    offsets = sorted(votes)
    cumulative = [0, *accumulate(votes[offset] for offset in offsets)]

    def neighbourhood(offset: int) -> int:
        """Total votes within ``max_edits`` of ``offset``."""
        low = bisect.bisect_left(offsets, offset - max_edits)
        high = bisect.bisect_right(offsets, offset + max_edits)
        return cumulative[high] - cumulative[low]

    ranked = sorted(offsets, key=lambda offset: (-neighbourhood(offset), -votes[offset]))
    chosen: list[int] = []
    for offset in ranked:
        if all(abs(offset - kept) > max_edits for kept in chosen):
            chosen.append(offset)
            if len(chosen) == MAX_CANDIDATE_REGIONS:
                break
    return chosen


def _occurrences(text: str, seed: str) -> list[int]:
    """Positions of ``seed`` in ``text``; empty if it is too common to locate.

    Args:
        text: Normalised text.
        seed: Substring to find.

    Returns:
        All start positions, or ``[]`` when there are more than
        ``SEED_MAX_OCCURRENCES``.
    """
    positions: list[int] = []
    position = text.find(seed)
    while position >= 0:
        if len(positions) == SEED_MAX_OCCURRENCES:
            return []
        positions.append(position)
        position = text.find(seed, position + 1)
    return positions


def _refine_window(
    matcher: SequenceMatcher,
    text: str,
    anchor: int,
    passage_length: int,
    slack: int,
    min_similarity: float,
) -> tuple[float, int, int]:
    """Choose the best-scoring window near an anchor offset.

    Aligns the passage against ``text`` around the anchor (``slack`` on either
    side) to estimate where it starts and ends, then, starting from the word
    boundaries nearest those estimates, alternately moves the start, then the
    end, to the best nearby word boundary. Refinement is skipped when the
    alignment matches too few characters for any window to reach
    ``min_similarity``; the estimated window's score is then returned for
    diagnostics.

    Args:
        matcher: SequenceMatcher with the normalised passage set as ``seq2``.
        text: Normalised text.
        anchor: Candidate start offset (may be negative).
        passage_length: Length of the normalised passage.
        slack: Radius around the anchored window searched for the passage.
        min_similarity: Acceptance threshold in (0, 1].

    Returns:
        ``(similarity, start, end)`` of the best window, in normalised indices.
    """
    length = len(text)
    starts, ends, aligned = _edge_estimates(matcher, text, anchor, passage_length, slack)
    start_candidates = _near_boundaries(_word_starts, text, starts, 0, length - 1)
    end_candidates = _near_boundaries(_word_ends, text, ends, 1, length)
    best_start = _closest(start_candidates, starts[0])
    viable_ends = [end for end in end_candidates if end > best_start]
    best_end = _closest(viable_ends or [min(best_start + passage_length, length)], ends[1])
    best = _similarity(matcher, text, best_start, best_end, floor=-1.0)
    # A window matching M characters scores at most 2M / (P + M). ``aligned``
    # is difflib's count for the wider region (a heuristic, not the longest
    # common subsequence), so this skips regions that are almost surely too
    # dissimilar; the exhaustive-search test in test_passage_match guards it.
    if 2 * aligned < min_similarity * (passage_length + aligned):
        return best, best_start, best_end
    for _ in range(REFINEMENT_PASSES):
        for start in start_candidates:
            if start < best_end:
                score = _similarity(matcher, text, start, best_end, floor=best)
                if score > best:
                    best, best_start = score, start
        for end in end_candidates:
            if end > best_start:
                score = _similarity(matcher, text, best_start, end, floor=best)
                if score > best:
                    best, best_end = score, end
    return best, best_start, best_end


def _near_boundaries(
    boundaries: Callable[[str, int, int], set[int]],
    text: str,
    estimates: tuple[int, int],
    lowest: int,
    highest: int,
) -> list[int]:
    """Word boundaries within ``EDGE_SEARCH_MARGIN`` of either estimate.

    Args:
        boundaries: :func:`_word_starts` or :func:`_word_ends`.
        text: Normalised text.
        estimates: Low and high estimate of the edge.
        lowest: Smallest valid edge index.
        highest: Largest valid edge index.

    Returns:
        Sorted candidate edges; the clamped estimates themselves when no word
        boundary lies near them (e.g. inside one very long token).
    """
    found: set[int] = set()
    for estimate in estimates:
        found |= boundaries(
            text, estimate - EDGE_SEARCH_MARGIN, estimate + EDGE_SEARCH_MARGIN
        )
    if not found:
        found = {min(max(estimate, lowest), highest) for estimate in estimates}
    return sorted(found)


def _closest(candidates: list[int], target: int) -> int:
    """The candidate nearest ``target`` (the lower one on ties)."""
    return min(candidates, key=lambda candidate: (abs(candidate - target), candidate))


def _edge_estimates(
    matcher: SequenceMatcher,
    text: str,
    anchor: int,
    passage_length: int,
    slack: int,
) -> tuple[tuple[int, int], tuple[int, int], int]:
    """Estimate where the passage starts and ends near an anchor.

    The passage is aligned against ``text`` from ``slack`` before the anchor
    to ``slack`` past the anchored end. Its start lies between where the
    first substantial matching block begins and where the passage would begin
    if its unmatched prefix were substitutions (inserted words put it at the
    former, substituted ones at the latter); likewise for the end.

    Args:
        matcher: SequenceMatcher with the normalised passage set as ``seq2``.
        text: Normalised text.
        anchor: Candidate start offset (may be negative).
        passage_length: Length of the normalised passage.
        slack: Radius around the anchored window to align against.

    Returns:
        ``((start_low, start_high), (end_low, end_high), aligned)``: edge
        estimates in normalised text indices (not clamped to the text; both
        pairs are the anchored window edges when the alignment has no
        substantial block), and the number of passage characters aligned.
    """
    low = max(anchor - slack, 0)
    high = min(anchor + passage_length + slack, len(text))
    matcher.set_seq1(text[low:high])
    all_blocks = matcher.get_matching_blocks()
    aligned = sum(block.size for block in all_blocks)
    blocks = [block for block in all_blocks if block.size >= EDGE_BLOCK_MIN_LENGTH]
    if not blocks:
        anchored_end = anchor + passage_length
        return (anchor, anchor), (anchored_end, anchored_end), aligned
    first, last = blocks[0], blocks[-1]
    first_at = low + first.a
    last_end = low + last.a + last.size
    unmatched_tail = passage_length - (last.b + last.size)
    return (first_at - first.b, first_at), (last_end, last_end + unmatched_tail), aligned


def _similarity(
    matcher: SequenceMatcher, text: str, start: int, end: int, floor: float
) -> float:
    """Ratio of the passage against ``text[start:end]``, pruned by upper bounds.

    Args:
        matcher: SequenceMatcher with the normalised passage set as ``seq2``.
        text: Normalised text.
        start: Window start.
        end: Window end (exclusive).
        floor: Score to beat; returns early with ``floor`` when the cheap
            upper bounds show the window cannot exceed it.

    Returns:
        The window's similarity, or ``floor`` if it cannot beat it.
    """
    matcher.set_seq1(text[start:end])
    if matcher.real_quick_ratio() <= floor or matcher.quick_ratio() <= floor:
        return floor
    return matcher.ratio()


def _word_starts(text: str, low: int, high: int) -> set[int]:
    """Indices in ``[low, high]`` where a word starts in normalised ``text``."""
    low, high = max(low, 0), min(high, len(text) - 1)
    return {
        index for index in range(low, high + 1)
        if text[index] != _SPACE and (index == 0 or text[index - 1] == _SPACE)
    }


def _word_ends(text: str, low: int, high: int) -> set[int]:
    """Exclusive indices in ``[low, high]`` where a word ends in normalised ``text``."""
    low, high = max(low, 1), min(high, len(text))
    return {
        index for index in range(low, high + 1)
        if text[index - 1] != _SPACE and (index == len(text) or text[index] == _SPACE)
    }


def _accepted(
    original: str,
    offsets: list[int],
    start: int,
    end: int,
    similarity: float,
    exact: bool = False,
) -> PassageMatch:
    """Map a normalised window back onto the original text.

    Args:
        original: Original (un-normalised) text.
        offsets: Offset map from :func:`normalize_with_offsets`.
        start: Window start in normalised indices.
        end: Window end (exclusive) in normalised indices; ``end > start``.
        similarity: Similarity of the window.
        exact: Whether the window is a verbatim (normalised) match.

    Returns:
        An accepted :class:`PassageMatch` spanning whole original characters.
    """
    original_start = offsets[start]
    # Extend up to the next kept character so marks folded to nothing (an
    # NFD accent after the last letter) stay in the span; a window ending
    # inside a multi-code-point fold ("ﬁ") keeps the whole character.
    next_kept = offsets[end] if end < len(offsets) else len(original)
    original_end = max(offsets[end - 1] + 1, next_kept)
    # A window edge on a collapsed space maps to raw whitespace: trim it.
    span = original[original_start:original_end]
    original_start += len(span) - len(span.lstrip())
    original_end -= len(span) - len(span.rstrip())
    return PassageMatch(
        similarity=similarity,
        start=original_start,
        end=original_end,
        text=original[original_start:original_end],
        exact=exact,
    )
