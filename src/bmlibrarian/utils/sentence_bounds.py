"""
Sentence-boundary checks for quoted passages in biomedical abstracts.

A citation must be at least one complete sentence (issue #289): a bare term
("Aspirin"), a clause, or a span that starts or ends mid-sentence can be
quoted out of context. ``complete_sentence_span`` decides whether a span of a
source text runs from a sentence start to a sentence end.

The rules are conservative. When a boundary is ambiguous it is treated as
*not* a boundary, so a doubtful span is rejected rather than accepted.

- A sentence ends at ``.``, ``!`` or ``?`` (optionally followed by closing
  brackets/quotes) that is followed by whitespace or the end of the text.
  Nothing else ends a sentence: a line break is not a boundary (hard-wrapped
  text breaks lines mid-sentence), and neither is the end of a text without
  closing punctuation (a truncated sentence, a keyword list).
- A ``.`` is not a sentence end if the token before it is a known
  abbreviation ("Fig. 2", "e.g. Aspirin", "et al. (2019)", in any case) or an
  initial ("J. Smith", "S. aureus", "U.S. Army"), or if the next word starts
  with an ordinary lowercase word ("et al. reported", "sp. nov."). A lowercase
  word that contains a digit or a capital ("p53", "mRNA", "eGFR") or starts
  with a Greek letter ("β-blockers") can start a sentence.
- A sentence starts at the beginning of the text, after a sentence end, after
  a blank line, after a single line break that follows a sentence end or a
  label/heading line ("BACKGROUND", "## Results"), or after a section label
  that itself starts a sentence ("RESULTS:", "**RESULTS:**", "Materials and
  methods:"). A label is all upper case or one of ``KNOWN_SECTION_LABELS``, so
  an ordinary colon ("two arms: Group A ...") does not start a sentence.
- A span that is only a section label, or has fewer than
  ``MIN_SENTENCE_WORDS`` words once a leading label is set aside, is not a
  sentence.

All functions are pure and work on character offsets into the original text.
"""

import re
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
# a sentence end when more text follows, even before a capital or a digit.
NON_TERMINAL_ABBREVIATIONS = frozenset({
    "e.g", "i.e", "vs", "cf", "ca", "approx", "fig", "figs", "eq", "eqs",
    "ref", "refs", "no", "nos", "vol", "pp", "dr", "prof", "mr", "mrs", "ms",
    "st", "sp", "spp", "subsp", "var", "resp", "viz", "inc", "ltd", "co", "jr",
    "sr", "vit", "wk", "wks", "yr", "yrs", "mo", "mos", "hr", "hrs", "min",
    "max", "dept", "univ", "eds",
})
# "al." is only an abbreviation in "et al."; on its own it can be a sentence
# ending in the element symbol "Al" (aluminium). Compared case-insensitively.
ET_AL = ("et", "al")
# An initial: one capital letter ("J", "S"), or letters joined by full stops
# ("U.S", "e.g", "a.m"), before a full stop.
INITIAL_PATTERN = re.compile(r"[A-Z]|(?:[A-Za-z]\.)+[A-Za-z]")
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
# Longest section label considered, in words and in characters.
LABEL_MAX_WORDS = 6
LABEL_MAX_CHARS = 60
# Fewest words a citable sentence has, not counting a leading section label.
MIN_SENTENCE_WORDS = 2
# Line breaks in a stretch of whitespace that make a paragraph break.
PARAGRAPH_BREAK_NEWLINES = 2


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
        The word (up to the next whitespace), or None at the end of the text.
    """
    while index < len(text) and (text[index].isspace() or text[index] in OPENING_CHARS):
        index += 1
    if index == len(text):
        return None
    end = index
    while end < len(text) and not text[end].isspace():
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
        The offset after the preceding whitespace or opening bracket/quote.
    """
    start = end
    while start > 0 and not text[start - 1].isspace() and text[start - 1] not in OPENING_CHARS:
        start -= 1
    return start


def _is_abbreviation_period(text: str, period: int) -> bool:
    """
    Whether the full stop at ``period`` belongs to an abbreviation or initial.

    Args:
        text: The source text.
        period: Index of a ``.`` in ``text``.

    Returns:
        True if the token before it is in ``NON_TERMINAL_ABBREVIATIONS``, is
        the "al" of "et al." (any case), or is an initial (``INITIAL_PATTERN``).
    """
    start = _token_start(text, period)
    token = text[start:period]
    if token.lower() == ET_AL[1]:
        before = text[:start].rstrip()
        previous = before[_token_start(before, len(before)):]
        return previous.lower() == ET_AL[0]
    return token.lower() in NON_TERMINAL_ABBREVIATIONS or bool(INITIAL_PATTERN.fullmatch(token))


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
    if end < len(text) and not text[end].isspace():
        return False

    last = end
    while last > 0 and text[last - 1] in CLOSING_CHARS:
        last -= 1
    if last == 0 or text[last - 1] not in SENTENCE_TERMINATORS:
        return False
    if not text[end:].strip():
        return True
    if text[last - 1] == ".":
        if _is_abbreviation_period(text, last - 1):
            return False
        next_word = _next_word(text, end)
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
    if not all(c.isalpha() or c in " &/-," for c in label):
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
    while body_end > 0 and text[body_end - 1].isspace():
        body_end -= 1

    scan_from = max(0, body_end - LABEL_MAX_CHARS)
    word_starts = [
        i for i in range(scan_from, body_end)
        if not text[i].isspace() and (i == 0 or text[i - 1].isspace())
    ]
    for start in reversed(word_starts[-LABEL_MAX_WORDS:]):
        label = text[start:body_end].lstrip("*#").strip()
        if _is_label(label) and is_sentence_start(text, start):
            return start
    return None


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
    while content_end > 0 and text[content_end - 1].isspace():
        content_end -= 1

    if content_end == 0:
        return True
    if content_end == before:
        return False
    line_breaks = text[content_end:before].count("\n")
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
    return sum(1 for word in content.split() if any(c.isalnum() for c in word))


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

    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
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
