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
normalised by lowercasing and collapsing whitespace; an offset map turns a
window in normalised text back into an exact span of the original.

Search strategy (bounded; cost grows roughly linearly with the text length
and quadratically with the passage length — milliseconds for a sentence,
~0.4 s for a 1 kB passage):

1. Exact substring match of the normalised passage (similarity 1.0).
2. Seed voting: the passage is cut into short non-overlapping seeds, each
   seed's occurrences in the text vote for an alignment offset. A window
   scoring ``>= min_similarity`` contains at most ``2P(1-s)/s`` edit points,
   so with that many seeds plus one, at least one seed survives intact and
   votes for the true location (for high thresholds such as 0.95; seed
   length is floored at ``SEED_MIN_LENGTH``, so low thresholds are
   best-effort).
3. For the best-supported offsets, the window's start and end are refined
   over nearby word boundaries, scoring each candidate with one cached
   ``SequenceMatcher``.
"""

from __future__ import annotations

import bisect
import math
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from itertools import accumulate

# Shortest seed used for voting; shorter seeds match almost anywhere.
SEED_MIN_LENGTH = 4
# Seeds occurring more often than this carry no location signal and are skipped.
SEED_MAX_OCCURRENCES = 64
# Number of distinct candidate locations refined per search.
MAX_CANDIDATE_REGIONS = 5
# Alternating start/end refinement passes per candidate location.
REFINEMENT_PASSES = 2

_SPACE = " "


@dataclass(frozen=True)
class PassageMatch:
    """Result of :func:`find_passage`.

    Attributes:
        similarity: Best similarity found (1.0 for an exact match, 0.0 when no
            candidate location was found at all). Reported even when the
            match is rejected.
        start: Start index of the matched span in the original text, or None.
        end: End index (exclusive) of the matched span, or None.
        text: ``original_text[start:end]`` when the match was accepted, else None.
    """

    similarity: float
    start: int | None = None
    end: int | None = None
    text: str | None = None

    @property
    def matched(self) -> bool:
        """Whether a span at or above the threshold was found."""
        return self.text is not None


def normalize_with_offsets(text: str) -> tuple[str, list[int]]:
    """Lowercase ``text`` and collapse whitespace, keeping a map back to it.

    Leading and trailing whitespace is dropped and every internal whitespace
    run becomes one space.

    Args:
        text: Original text.

    Returns:
        ``(normalised, offsets)`` where ``offsets[i]`` is the index in ``text``
        of the character that produced ``normalised[i]`` (for a collapsed
        whitespace run, its first character).
    """
    chars: list[str] = []
    offsets: list[int] = []
    pending_space = -1
    for index, char in enumerate(text):
        if char.isspace():
            if pending_space < 0 and chars:
                pending_space = index
            continue
        if pending_space >= 0:
            chars.append(_SPACE)
            offsets.append(pending_space)
            pending_space = -1
        # lower() can yield several code points ("İ" -> "i̇"); map each back.
        for lowered in char.lower():
            chars.append(lowered)
            offsets.append(index)
    return "".join(chars), offsets


def find_passage(passage: str, text: str, min_similarity: float) -> PassageMatch:
    """Find the span of ``text`` that best matches ``passage``.

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
        return _accepted(text, offsets, exact_at, exact_at + len(norm_passage), 1.0)

    max_edits = max_edit_points(len(norm_passage), min_similarity)
    matcher = SequenceMatcher(None, autojunk=False)
    matcher.set_seq2(norm_passage)

    best_similarity, best_start, best_end = 0.0, 0, 0
    for anchor in _candidate_anchors(norm_passage, norm_text, max_edits):
        similarity, start, end = _refine_window(
            matcher, norm_text, anchor, len(norm_passage), max_edits + 1
        )
        if similarity > best_similarity:
            best_similarity, best_start, best_end = similarity, start, end

    if best_similarity >= min_similarity:
        return _accepted(text, offsets, best_start, best_end, best_similarity)
    return PassageMatch(similarity=best_similarity)


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
        Up to ``MAX_CANDIDATE_REGIONS`` offsets (possibly negative or past the
        end of ``text``), strongest first, more than ``max_edits`` apart.
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
) -> tuple[float, int, int]:
    """Choose the best-scoring window near an anchor offset.

    Starts from ``[anchor, anchor + passage_length)`` and alternately moves the
    start, then the end, to the best word boundary within ``slack``.

    Args:
        matcher: SequenceMatcher with the normalised passage set as ``seq2``.
        text: Normalised text.
        anchor: Candidate start offset (may lie outside ``text``).
        passage_length: Length of the normalised passage.
        slack: Search radius around the initial start and end.

    Returns:
        ``(similarity, start, end)`` of the best window, in normalised indices.
    """
    length = len(text)
    initial_start = min(max(anchor, 0), length - 1)
    initial_end = min(max(anchor + passage_length, initial_start + 1), length)
    start_candidates = _word_starts(text, initial_start - slack, initial_start + slack)
    start_candidates.add(initial_start)
    end_candidates = _word_ends(text, initial_end - slack, initial_end + slack)
    end_candidates.add(initial_end)

    best_start, best_end = initial_start, initial_end
    best = _similarity(matcher, text, best_start, best_end, floor=-1.0)
    for _ in range(REFINEMENT_PASSES):
        for start in sorted(start_candidates):
            if start < best_end:
                score = _similarity(matcher, text, start, best_end, floor=best)
                if score > best:
                    best, best_start = score, start
        for end in sorted(end_candidates):
            if end > best_start:
                score = _similarity(matcher, text, best_start, end, floor=best)
                if score > best:
                    best, best_end = score, end
    return best, best_start, best_end


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
    original: str, offsets: list[int], start: int, end: int, similarity: float
) -> PassageMatch:
    """Map a normalised window back onto the original text.

    Args:
        original: Original (un-normalised) text.
        offsets: Offset map from :func:`normalize_with_offsets`.
        start: Window start in normalised indices.
        end: Window end (exclusive) in normalised indices; ``end > start``.
        similarity: Similarity of the window.

    Returns:
        An accepted :class:`PassageMatch` spanning whole original characters.
    """
    original_start = offsets[start]
    original_end = offsets[end - 1] + 1
    # A window edge on a collapsed space maps to raw whitespace: trim it.
    span = original[original_start:original_end]
    original_start += len(span) - len(span.lstrip())
    original_end -= len(span) - len(span.rstrip())
    return PassageMatch(
        similarity=similarity,
        start=original_start,
        end=original_end,
        text=original[original_start:original_end],
    )
