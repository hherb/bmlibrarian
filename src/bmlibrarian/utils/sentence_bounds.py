"""
Sentence-boundary checks for quoted passages in biomedical abstracts.

A citation must be at least one complete sentence (issue #289): a bare term
("Aspirin"), a clause, or a span that starts or ends mid-sentence can be
quoted out of context. ``complete_sentence_span`` decides whether a span of a
source text runs from a sentence start to a sentence end.

The rules are conservative. When a boundary is ambiguous it is treated as
*not* a boundary, so a doubtful span is rejected rather than accepted. The
exceptions (designator letters, all-caps tokens, "et al." before a capital,
time units, glued text) were accepted on purpose because they lost real
evidence (#303).

- A sentence ends at ``.``, ``!`` or ``?`` (optionally followed by closing
  brackets/quotes) that is followed by whitespace, the end of the text, or a
  glued capitalised word ("DAPT.The", "stenosis.Conclusion:" -- source text
  that lost its spaces; not after a one-letter token or inside a token such
  as "p.Val600Glu", "J.Smith" or "www.ClinicalTrials.gov"). Nothing else ends a sentence: a line break is not a
  boundary (hard-wrapped text breaks lines mid-sentence), and neither is the
  end of a text without closing punctuation (a truncated sentence, a keyword
  list).
- A ``.`` is not a sentence end if the token before it is a known
  abbreviation ("Fig. 2", "e.g. Aspirin", "No. 5"; an all-caps token before
  a capitalised word ends the sentence, so "clinical CA. The" and "levels of
  NO. In" end sentences but "FIG. 2" and "VS. PLACEBO" do not), "et al."
  before anything but a capitalised word ("et al. (2019)", "et al. (Lancet,
  2019)"; "...by Smith et al. The effect" does end), or an initial ("U.S.
  Army", "J. M. Smith"), or if the next word starts with an ordinary
  lowercase word ("et al. reported", "sp. nov.", "S. aureus"). A single
  capital letter is an initial only next to another initial: elsewhere it is
  a designator that can end a sentence ("type B.", "Group A.", "hepatitis
  B."), at the price of splitting "by J. Smith" and "with S. Typhimurium". A
  lowercase word that contains a digit or a capital ("p53", "mRNA", "eGFR")
  or starts with a Greek letter ("β-blockers") can start a sentence.
- A sentence starts at the beginning of the text, after a sentence end, after
  a blank line, after a single line break that follows a sentence end or a
  label/heading line ("BACKGROUND", "## Results"), or after a section label
  that itself starts a sentence ("RESULTS:", "**RESULTS:**", "Materials and
  methods:", "AUTHORS' CONCLUSIONS:"), with or without a space after it. A
  label is all upper case or one of ``KNOWN_SECTION_LABELS``, so an ordinary
  colon ("two arms: Group A ...") does not start a sentence. Damaged source
  text also starts a sentence: a one-word label fused onto the next word
  ("unclear.ObjectiveThis study", #304), and a double space or "( " before a
  capitalised word, where PubMed dropped a formula or symbol ("(all  Women
  with").
- A span that is only a section label, or has fewer than
  ``MIN_SENTENCE_WORDS`` words once a leading label is set aside, is not a
  sentence.

``enclosing_sentence_span`` widens a fragment to the complete sentence(s)
around it, for callers that may cite the source's own sentence instead of
rejecting a verbatim fragment.

"Whitespace" in these rules (and in the docstrings below) includes invisible
format characters (zero-width space, soft hyphen, word joiner, BOM): they
never hide or join a boundary.

All functions are pure and work on character offsets into the original text.
"""

import re
import unicodedata
from typing import Optional

# Characters that end a sentence.
SENTENCE_TERMINATORS = ".!?"
# Characters that may follow a terminator and still belong to the sentence
# (closing brackets, quotes, Markdown emphasis).
CLOSING_CHARS = ")]}\"'”’»*"
# Characters that may precede a sentence's first word (opening brackets,
# quotes, Markdown emphasis or heading marks).
OPENING_CHARS = "([{\"'“‘«*#"
# Closing marks and the opening mark each one needs; the remaining closing
# characters (straight quotes, ``*``) pair with themselves.
PAIRED_CLOSERS = {")": "(", "]": "[", "}": "{", "”": "“", "’": "‘", "»": "«"}
# Tokens (lower case, without the final ".") whose full stop is never taken as
# a sentence end when more text follows, even before a capital or a digit --
# except in all caps before a capitalised word (see _is_abbreviation_period).
NON_TERMINAL_ABBREVIATIONS = frozenset({
    "e.g", "i.e", "vs", "cf", "ca", "approx", "fig", "figs", "eq", "eqs",
    "ref", "refs", "no", "nos", "vol", "pp", "dr", "prof", "mr", "mrs", "ms",
    "st", "sp", "spp", "subsp", "var", "resp", "viz", "inc", "ltd", "co", "jr",
    "sr", "vit", "max", "dept", "univ", "eds",
})
# Time units ("3 min.", "2 hrs.", "12 wks.") are deliberately not in the list:
# in abstracts their full stop before a capital or digit ends the sentence
# (at the price of "Range was min. 3 to max. 10" ending after "min.").
# "al." is only an abbreviation in "et al."; on its own it can be a sentence
# ending in the element symbol "Al" (aluminium). Compared case-insensitively.
# Before a capitalised word "et al." ends the sentence.
ET_AL = ("et", "al")
# An initial: letters joined by full stops ("U.S", "e.g", "a.m") before a
# full stop. A single capital letter ("J", "B") is matched separately.
INITIAL_PATTERN = re.compile(r"(?:[A-Za-z]\.)+[A-Za-z]")
SINGLE_CAPITAL = re.compile(r"[A-Z]")
# Lowercase Greek letters, which start sentences as prefixes ("β-blockers").
GREEK_LOWERCASE = ("α", "ω")
# Mixed-case section labels of structured abstracts (lower case). All-caps
# labels ("MATERIAL AND METHODS") are recognised without this list.
KNOWN_SECTION_LABELS = frozenset({
    "abstract", "background", "introduction", "context", "importance",
    "rationale", "objective", "objectives", "aim", "aims", "purpose",
    "hypothesis", "background and aims", "background and objectives",
    "aims and objectives", "method", "methods", "materials and methods",
    "patients and methods", "methods and materials", "methods and results",
    "methods and findings", "design", "study design",
    "design, setting, and participants", "design, setting and participants",
    "setting", "settings", "participants", "patients", "subjects", "population",
    "intervention", "interventions", "exposure", "exposures", "measurements",
    "main outcome measures", "main outcomes and measures", "outcomes",
    "data sources", "study selection", "data extraction", "data synthesis",
    "data collection and analysis", "search methods", "selection criteria",
    "review methods", "evidence acquisition", "evidence synthesis",
    "eligibility criteria", "case presentation", "case report", "case summary",
    "results", "findings", "main results", "results and conclusions",
    "discussion", "limitations", "conclusion", "conclusions",
    "conclusions and relevance", "interpretation", "implications",
    "significance", "summary", "level of evidence", "trial registration",
    "registration", "funding", "clinical relevance",
})
# Non-letters allowed in a section label ("AUTHORS' CONCLUSIONS").
LABEL_PUNCTUATION = " &/-,'’"
# Longest section label considered, in words and in characters.
LABEL_MAX_WORDS = 6
LABEL_MAX_CHARS = 60
# Fewest words a citable sentence has, not counting a leading section label.
MIN_SENTENCE_WORDS = 2
# Unicode category of invisible format characters, treated like whitespace.
FORMAT_CATEGORY = "Cf"
# Line breaks in a stretch of whitespace that make a paragraph break.
PARAGRAPH_BREAK_NEWLINES = 2
# Blanks in a row on one line that mark text the source lost (see
# _is_lost_text_gap), and the opening brackets after which one blank does.
LOST_TEXT_GAP_SPACES = 2
OPENING_BRACKETS = "([{"
# Most characters ``enclosing_sentence_span`` may add around a fragment, so a
# fragment in text without detectable boundaries (keyword lists, hard-wrapped
# text) is not widened into most of the abstract.
MAX_WIDENING_CHARS = 400


def _is_blank(char: str) -> bool:
    """
    Whether ``char`` separates text without being content.

    Args:
        char: One character.

    Returns:
        True for whitespace and invisible format characters (Unicode ``Cf``:
        zero-width space, soft hyphen, word joiner, BOM), which a boundary
        check must see through (issue #302).
    """
    return char.isspace() or unicodedata.category(char) == FORMAT_CATEGORY


def _check_offset(text: str, index: int) -> None:
    """
    Validate a text/offset pair.

    Args:
        text: The source text.
        index: A character offset into it.

    Raises:
        TypeError: If ``text`` is not a str or ``index`` is not an int.
        ValueError: If ``index`` is outside ``[0, len(text)]``.
    """
    if not isinstance(text, str):
        raise TypeError(f"text must be a str, got {type(text).__name__}")
    if not isinstance(index, int) or isinstance(index, bool):
        raise TypeError(f"offset must be an int, got {type(index).__name__}")
    if not 0 <= index <= len(text):
        raise ValueError(f"offset {index} outside [0, {len(text)}]")


def _next_word(text: str, index: int) -> Optional[str]:
    """
    The next word at or after ``index``.

    Skips whitespace and opening brackets/quotes.

    Args:
        text: The source text.
        index: Where to start looking.

    Returns:
        The word (up to the next whitespace or ``Cf`` character, see
        ``_is_blank``), or None at the end of the text.
    """
    while index < len(text) and (_is_blank(text[index]) or text[index] in OPENING_CHARS):
        index += 1
    if index == len(text):
        return None
    end = index
    while end < len(text) and not _is_blank(text[end]):
        end += 1
    return text[index:end]


def _can_start_sentence(word: str) -> bool:
    """
    Whether ``word`` may be the first word of a sentence.

    Args:
        word: A non-empty word.

    Returns:
        True unless it is an ordinary lowercase word. Words starting with a
        capital, a digit or another non-letter qualify, and so do lowercase
        words containing a digit or a capital ("p53", "mRNA", "eGFR") or
        starting with a Greek letter ("β-blockers").
    """
    first = word[0]
    if not first.isalpha() or not first.islower():
        return True
    if GREEK_LOWERCASE[0] <= first <= GREEK_LOWERCASE[1]:
        return True
    return any(c.isdigit() or c.isupper() for c in word[1:])


def _token_start(text: str, end: int) -> int:
    """
    Start of the token that ends at ``end``.

    Args:
        text: The source text.
        end: Offset just after the token.

    Returns:
        The offset after the preceding whitespace (``_is_blank``) or opening
        bracket/quote.
    """
    start = end
    while start > 0 and not _is_blank(text[start - 1]) and text[start - 1] not in OPENING_CHARS:
        start -= 1
    return start


def _previous_token(text: str, start: int) -> str:
    """
    The token before the one starting at ``start``.

    Args:
        text: The source text.
        start: Start offset of a token.

    Returns:
        The preceding token, or "" at the start of the text.
    """
    end = start
    while end > 0 and _is_blank(text[end - 1]):
        end -= 1
    return text[_token_start(text, end):end]


def _is_abbreviation_period(text: str, period: int, next_word: Optional[str]) -> bool:
    """
    Whether the full stop at ``period`` belongs to an abbreviation or initial.

    Args:
        text: The source text.
        period: Index of a ``.`` in ``text``.
        next_word: The word after the full stop, or None at the end of the text.

    Returns:
        True if the token before it is in ``NON_TERMINAL_ABBREVIATIONS`` (but
        not in all caps before a capitalised word: "CA. The", "NO. In"), is
        the "al" of "et al." (any case) not followed by a capitalised word or
        followed by an opening bracket, is an initial (``INITIAL_PATTERN``),
        or is a single capital letter next to another one ("J. M. Smith").
    """
    start = _token_start(text, period)
    token = text[start:period]
    if token.lower() == ET_AL[1]:
        if _previous_token(text, start).lower() != ET_AL[0]:
            return False
        after = period + 1
        while after < len(text) and _is_blank(text[after]):
            after += 1
        if after < len(text) and text[after] in OPENING_CHARS:  # "et al. (Lancet, 2019)"
            return True
        return not (next_word and next_word[0].isupper())
    if SINGLE_CAPITAL.fullmatch(token):
        return _is_single_initial(_previous_token(text, start)) or _is_single_initial(next_word)
    if (
        token.isupper() and len(token) > 1 and not INITIAL_PATTERN.fullmatch(token)
        and _is_capitalised_word(next_word)
    ):
        return False
    return token.lower() in NON_TERMINAL_ABBREVIATIONS or bool(INITIAL_PATTERN.fullmatch(token))


def _is_single_initial(word: Optional[str]) -> bool:
    """
    Whether ``word`` is one capital letter and a full stop ("J.", "M.").

    Args:
        word: A token, or None.

    Returns:
        True for a single-letter initial.
    """
    return word is not None and word.endswith(".") and bool(SINGLE_CAPITAL.fullmatch(word[:-1]))


def _is_capitalised_word(word: Optional[str]) -> bool:
    """
    Whether ``word`` looks like an ordinary capitalised sentence start.

    Args:
        word: A word, or None.

    Returns:
        True for a capital followed by a lower-case letter ("The", "In") that
        is not itself a listed abbreviation ("Inc.", "No."); False for digits
        and all-caps words ("2", "PLACEBO").
    """
    return (
        word is not None and len(word) > 1 and word[0].isupper() and word[1].islower()
        and word.rstrip(".").lower() not in NON_TERMINAL_ABBREVIATIONS
    )


def _is_glued_sentence_end(text: str, index: int) -> bool:
    """
    Whether a sentence ends at ``index`` although no space follows it.

    Args:
        text: The source text.
        index: Offset just after a terminator and any closing marks.

    Returns:
        True when a capitalised word of letters only starts at ``index``
        ("DAPT.The", "stenosis.Conclusion:"): source text that lost the space
        between sentences. False after a one-letter token ("p.Arg506Gln",
        "J.Smith", "N.Engl") and when the glued word runs on into a digit or a
        full stop ("p53.Val600Glu", "www.ClinicalTrials.gov").
    """
    run_end = index
    while run_end < len(text) and text[run_end].isalpha():
        run_end += 1
    if not _is_capitalised_word(text[index:run_end]):
        return False
    if run_end < len(text) and (text[run_end] == "." or text[run_end].isdigit()):
        return False
    last = index
    while last > 0 and text[last - 1] in CLOSING_CHARS:
        last -= 1
    if last == 0:
        return False
    return last - 1 - _token_start(text, last - 1) > 1


def is_sentence_end(text: str, end: int) -> bool:
    """
    Whether a sentence ends exactly at offset ``end`` (exclusive).

    Args:
        text: The source text.
        end: Offset just after the candidate sentence's last character.

    Returns:
        True if ``end`` is a sentence end under the module's rules.

    Raises:
        TypeError: If ``text`` is not a str or ``end`` is not an int.
        ValueError: If ``end`` is outside ``[0, len(text)]``.
    """
    _check_offset(text, end)
    if end == 0:
        return False
    if end < len(text) and not _is_blank(text[end]) and not _is_glued_sentence_end(text, end):
        return False

    last = end
    while last > 0 and text[last - 1] in CLOSING_CHARS:
        last -= 1
    if last == 0 or text[last - 1] not in SENTENCE_TERMINATORS:
        return False
    if all(_is_blank(c) for c in text[end:]):
        return True
    if text[last - 1] == ".":
        next_word = _next_word(text, end)
        if _is_abbreviation_period(text, last - 1, next_word):
            return False
        if next_word is not None and not _can_start_sentence(next_word):
            return False
    return True


def _is_label(label: str) -> bool:
    """
    Whether ``label`` looks like a structured-abstract section label.

    Args:
        label: Candidate label text, without its colon or Markdown marks.

    Returns:
        True for an all-caps label or one of ``KNOWN_SECTION_LABELS``.
    """
    if not label or not any(c.isalpha() for c in label):
        return False
    if not all(c.isalpha() or c in LABEL_PUNCTUATION for c in label):
        return False
    return label.upper() == label or label.lower() in KNOWN_SECTION_LABELS


def _clean_label(label: str) -> str:
    """
    Strip Markdown marks, whitespace and a trailing colon from a label.

    Args:
        label: Raw label text, e.g. ``"**RESULTS:**"``.

    Returns:
        The bare label, e.g. ``"RESULTS"``.
    """
    return label.strip().strip("*#").strip().rstrip(":").strip("*").strip()


def _is_heading_line(text: str, line_end: int) -> bool:
    """
    Whether the line ending at ``line_end`` is a heading or a section label.

    Args:
        text: The source text.
        line_end: Offset just after the line's last non-space character.

    Returns:
        True for a Markdown heading (``# ...``) or a line that is only a
        section label, with or without a colon ("BACKGROUND", "Methods:").
    """
    line = text[text.rfind("\n", 0, line_end) + 1:line_end].strip()
    return line.startswith("#") or _is_label(_clean_label(line))


def _label_start(text: str, end: int) -> Optional[int]:
    """
    Find a section label ending at ``end`` that itself starts a sentence.

    Args:
        text: The source text.
        end: Offset just after the label's colon (and closing ``**``).

    Returns:
        The label's start offset, or None if ``text[:end]`` does not end
        with such a label.
    """
    body_end = end
    if text[:body_end].endswith("**"):
        body_end -= 2
    if body_end == 0 or text[body_end - 1] != ":":
        return None
    body_end -= 1
    if text[:body_end].endswith("**"):  # "**Results**:"
        body_end -= 2
    while body_end > 0 and _is_blank(text[body_end - 1]):
        body_end -= 1

    scan_from = max(0, body_end - LABEL_MAX_CHARS)
    word_starts = [
        i for i in range(scan_from, body_end)
        if not _is_blank(text[i])
        and (i == 0 or _is_blank(text[i - 1]) or is_sentence_end(text, i))
    ]
    for start in reversed(word_starts[-LABEL_MAX_WORDS:]):
        # _clean_label also takes the stray colon of "**CONCLUSIONS:** :".
        label = _clean_label(text[start:body_end])
        if _is_label(label) and is_sentence_start(text, start):
            return start
    return None


def _is_fused_label_end(text: str, index: int) -> bool:
    """
    Whether a section label fused onto the next word ends at ``index``.

    Args:
        text: The source text.
        index: Offset of a capital letter with no space before it.

    Returns:
        True when the letters directly before ``index`` are a capitalised
        one-word ``KNOWN_SECTION_LABELS`` entry that starts a sentence
        ("unclear.ObjectiveThis study", "ResultsWe", "MethodsA cohort",
        "ConclusionsCSF"): PubMed and Europe PMC serve some structured
        abstracts that way (#304). Multi-word labels are not recognised.
    """
    if index == len(text) or not text[index].isupper():
        return False
    label_start = index
    while label_start > 0 and text[label_start - 1].isalpha():
        label_start -= 1
    label = text[label_start:index]
    return (
        len(label) > 1 and label[0].isupper() and label[1:].islower()
        and label.lower() in KNOWN_SECTION_LABELS
        and is_sentence_start(text, label_start)
    )


def _is_lost_text_gap(text: str, content_end: int, word_start: int) -> bool:
    """
    Whether a sentence starts after a gap where the source lost text.

    PubMed drops some inline content (formulas, symbols) and leaves a double
    space or "( " behind, so the sentence before the gap never ends
    ("(all  Women with…", "patients ( A minority of women…"). The sentence
    after the gap is accepted; the broken one before it still has no end.

    Args:
        text: The source text.
        content_end: Offset just after the last non-blank character before
            the gap.
        word_start: Offset of the first character after the gap and any
            opening marks.

    Returns:
        True when a capitalised word (``_is_capitalised_word``, or "A")
        follows at least ``LOST_TEXT_GAP_SPACES`` spaces, or a space after
        an opening bracket. The caller checks that the gap has no line break.
    """
    gap = sum(1 for c in text[content_end:word_start] if c.isspace())
    after_bracket = content_end > 0 and text[content_end - 1] in OPENING_BRACKETS
    if gap < LOST_TEXT_GAP_SPACES and not after_bracket:
        return False
    word = _next_word(text, word_start)
    # A one-letter capital word counts too ("( A minority of women").
    return _is_capitalised_word(word) or bool(word and SINGLE_CAPITAL.fullmatch(word))


def is_sentence_start(text: str, start: int) -> bool:
    """
    Whether a sentence starts exactly at offset ``start``.

    Args:
        text: The source text.
        start: Offset of the candidate sentence's first character.

    Returns:
        True if ``start`` is a sentence start under the module's rules.

    Raises:
        TypeError: If ``text`` is not a str or ``start`` is not an int.
        ValueError: If ``start`` is outside ``[0, len(text)]``.
    """
    _check_offset(text, start)
    before = start
    while before > 0 and text[before - 1] in OPENING_CHARS:
        before -= 1
    content_end = before
    while content_end > 0 and _is_blank(text[content_end - 1]):
        content_end -= 1

    if content_end == 0:
        return True
    if content_end == before:
        # No space: only a glued sentence end or section label ("stenosis.The",
        # "Conclusion:Pre-operative") starts a sentence here.
        return (
            is_sentence_end(text, before)
            or _label_start(text, before) is not None
            or _is_fused_label_end(text, before)
        )
    line_breaks = text[content_end:before].count("\n")
    if not line_breaks and _is_lost_text_gap(text, content_end, before):
        return True
    if line_breaks >= PARAGRAPH_BREAK_NEWLINES:
        return True
    if is_sentence_end(text, content_end):
        return True
    if line_breaks and _is_heading_line(text, content_end):
        return True
    return _label_start(text, content_end) is not None


def _extend_over_sentence_end(text: str, end: int) -> Optional[int]:
    """
    Extend ``end`` over closing punctuation the quote left out.

    Only closing brackets/quotes and sentence terminators are added, never
    words: "...bleeding risk" becomes "...bleeding risk." when the source
    continues with ``.``.

    Args:
        text: The source text.
        end: Offset where the quoted span stops.

    Returns:
        The extended end if it is a sentence end, else None.
    """
    extended = end
    while extended < len(text) and text[extended] in CLOSING_CHARS:
        extended += 1
    while extended < len(text) and text[extended] in SENTENCE_TERMINATORS:
        extended += 1
    while extended < len(text) and text[extended] in CLOSING_CHARS:
        extended += 1
    if extended == end or not is_sentence_end(text, extended):
        return None
    return extended


def _trim_unbalanced_closers(text: str, start: int, end: int) -> int:
    """
    Drop trailing closing marks that have no opening mark in the span.

    A sentence quoted from inside brackets, quotes or Markdown emphasis
    ("(Data not shown.)", "*Rates fell.*") would otherwise end with the
    outer closing mark.

    Args:
        text: The source text.
        start: Start of the span.
        end: End of the span.

    Returns:
        The end with unmatched trailing closing marks removed.
    """
    while end > start and text[end - 1] in CLOSING_CHARS:
        closer = text[end - 1]
        span = text[start:end]
        if closer in PAIRED_CLOSERS:
            balanced = span.count(PAIRED_CLOSERS[closer]) >= span.count(closer)
        else:
            balanced = span.count(closer) % 2 == 0
        if balanced:
            break
        end -= 1
    return end


def _without_leading_label(content: str) -> str:
    """
    Set aside a section label at the start of a span ("RESULTS: ...").

    Args:
        content: The span's text, Markdown marks at its edges removed.

    Returns:
        The text after the label, or ``content`` if it does not start with one.
    """
    head, colon, tail = content.partition(":")
    if colon and _is_label(_clean_label(head)):
        return tail.strip().lstrip("*").strip()
    return content


def _word_count(content: str) -> int:
    """
    Count the words of ``content`` that contain a letter or a digit.

    Args:
        content: Text to count.

    Returns:
        The number of such words.
    """
    spaced = "".join(" " if _is_blank(c) else c for c in content)
    return sum(1 for word in spaced.split() if any(c.isalnum() for c in word))


def complete_sentence_span(text: str, start: int, end: int) -> Optional[tuple[int, int]]:
    """
    Check that ``text[start:end]`` consists of one or more complete sentences.

    Surrounding whitespace is trimmed, closing punctuation the quote omitted
    is taken from the source (see ``_extend_over_sentence_end``), and closing
    marks without an opening mark in the span are dropped
    (``_trim_unbalanced_closers``). Nothing else is added or removed.

    Args:
        text: The source text (e.g. an abstract).
        start: Start offset of the quoted span.
        end: End offset (exclusive) of the quoted span.

    Returns:
        The ``(start, end)`` of the complete sentences, or None if the span
        starts or ends mid-sentence, has no letters, is only a section label,
        or has fewer than ``MIN_SENTENCE_WORDS`` words besides a leading label.

    Raises:
        TypeError: If ``text`` is not a str or an offset is not an int.
        ValueError: If an offset is outside ``[0, len(text)]`` or
            ``start > end``.
    """
    _check_offset(text, start)
    _check_offset(text, end)
    if start > end:
        raise ValueError(f"start {start} is after end {end}")

    while start < end and _is_blank(text[start]):
        start += 1
    while end > start and _is_blank(text[end - 1]):
        end -= 1
    if not any(c.isalpha() for c in text[start:end]):
        return None
    if not is_sentence_start(text, start):
        return None
    if not is_sentence_end(text, end):
        extended = _extend_over_sentence_end(text, end)
        if extended is None:
            return None
        end = extended
    end = _trim_unbalanced_closers(text, start, end)

    body = _without_leading_label(text[start:end].strip().strip("*#").strip())
    if _is_label(_clean_label(body.rstrip(SENTENCE_TERMINATORS))):
        return None
    if _word_count(body) < MIN_SENTENCE_WORDS:
        return None
    return start, end


def enclosing_sentence_span(
    text: str, start: int, end: int, max_added_chars: int = MAX_WIDENING_CHARS
) -> Optional[tuple[int, int]]:
    """
    Widen ``text[start:end]`` to the complete sentence(s) that contain it.

    For a quote that is a fragment ("while prior use of statins was ...", a
    clause after a semicolon): the span is moved back to the nearest
    sentence start and forward to the nearest sentence end, then checked
    with ``complete_sentence_span``. The result is the source's own text;
    callers should record that it was widened.

    Args:
        text: The source text (e.g. an abstract).
        start: Start offset of the quoted span.
        end: End offset (exclusive) of the quoted span.
        max_added_chars: Most characters the widening may add on both sides
            together (default ``MAX_WIDENING_CHARS``).

    Returns:
        The ``(start, end)`` of the enclosing complete sentences (equal to
        ``complete_sentence_span``'s result if the span already is one), or
        None if no sentence boundary lies within ``max_added_chars`` or the
        widened span is not a citable sentence (only a label, too few words).

    Raises:
        TypeError: If ``text`` is not a str or an offset or the limit is not
            an int.
        ValueError: If an offset is outside ``[0, len(text)]``,
            ``start > end``, or ``max_added_chars`` is negative.
    """
    _check_offset(text, start)
    _check_offset(text, end)
    if start > end:
        raise ValueError(f"start {start} is after end {end}")
    if not isinstance(max_added_chars, int) or isinstance(max_added_chars, bool):
        raise TypeError(f"max_added_chars must be an int, got {type(max_added_chars).__name__}")
    if max_added_chars < 0:
        raise ValueError(f"max_added_chars must not be negative, got {max_added_chars}")

    while start < end and _is_blank(text[start]):
        start += 1
    while end > start and _is_blank(text[end - 1]):
        end -= 1

    new_start = start
    # Only a word or an opening mark can begin a sentence; is_sentence_start
    # alone also holds at the stray colon of "**CONCLUSIONS:** : Text".
    while not (
        (text[new_start:new_start + 1].isalnum() or text[new_start:new_start + 1] in OPENING_CHARS)
        and is_sentence_start(text, new_start)
    ):
        if new_start == 0 or start - new_start >= max_added_chars:
            return None
        new_start -= 1
    budget = max_added_chars - (start - new_start)
    new_end = end
    while not is_sentence_end(text, new_end):
        if new_end == len(text) or new_end - end >= budget:
            return None
        new_end += 1
        # A new sentence starting before this one ended means the source
        # broke it off (lost text, a heading without punctuation): reject
        # rather than run the broken sentence into the next one.
        if text[new_end:new_end + 1].isalnum() and is_sentence_start(text, new_end):
            return None
    return complete_sentence_span(text, new_start, new_end)
