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
  A line break, or the end of the text, also ends a sentence without
  punctuation (title lines, a truncated last sentence).
- A ``.`` is not a sentence end if the next word starts with a lowercase
  letter ("et al. reported", "E. coli", "sp. nov."), or if the token before
  it is a known abbreviation ("Fig. 2", "e.g. Aspirin", "et al. (2019)").
- A sentence starts at the beginning of the text, after a sentence end, after
  a line break, or after a section label that itself starts a sentence
  ("RESULTS:", "**RESULTS:**", "Materials and methods:"). A label is all
  upper case or one of ``KNOWN_SECTION_LABELS``, so an ordinary colon
  ("two arms: Group A ...") does not start a sentence.

All functions are pure and work on character offsets into the original text.
"""

from typing import Optional

# Characters that end a sentence.
SENTENCE_TERMINATORS = ".!?"
# Characters that may follow a terminator and still belong to the sentence
# (closing brackets, quotes, Markdown emphasis).
CLOSING_CHARS = ")]}\"'”’»*"
# Characters that may precede a sentence's first word (opening brackets,
# quotes, Markdown emphasis or heading marks).
OPENING_CHARS = "([{\"'“‘«*#"
# Tokens (lower case, without the final ".") whose full stop never ends a
# sentence, even when a capital letter or digit follows.
NON_TERMINAL_ABBREVIATIONS = frozenset({
    "e.g", "i.e", "vs", "cf", "ca", "approx", "fig", "figs", "eq", "eqs",
    "ref", "refs", "no", "nos", "vol", "pp", "dr", "prof", "mr", "mrs", "ms",
    "st", "sp", "spp", "subsp", "var", "resp", "viz", "inc", "ltd", "co", "jr",
    "sr",
})
# "al." is only an abbreviation in "et al."; on its own it can be a sentence
# ending in the element symbol "Al" (aluminium).
ET_AL = ("et", "al")
# Mixed-case section labels of structured abstracts (lower case). All-caps
# labels ("MATERIAL AND METHODS") are recognised without this list.
KNOWN_SECTION_LABELS = frozenset({
    "background", "introduction", "context", "importance", "rationale",
    "objective", "objectives", "aim", "aims", "purpose", "hypothesis",
    "method", "methods", "materials and methods", "patients and methods",
    "methods and materials", "methods and results", "design", "study design",
    "setting", "settings", "participants", "patients", "subjects", "population",
    "intervention", "interventions", "exposure", "exposures", "measurements",
    "main outcome measures", "main outcomes and measures", "outcomes",
    "data sources", "study selection", "data extraction", "data synthesis",
    "evidence acquisition", "evidence synthesis", "eligibility criteria",
    "results", "findings", "main results", "discussion", "limitations",
    "conclusion", "conclusions", "interpretation", "implications",
    "significance", "summary", "trial registration", "registration",
    "funding", "clinical relevance",
})
# Longest section label considered, in words and in characters.
LABEL_MAX_WORDS = 6
LABEL_MAX_CHARS = 60


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


def _next_word_char(text: str, index: int) -> Optional[str]:
    """
    The first character of the next word at or after ``index``.

    Skips whitespace and opening brackets/quotes.

    Args:
        text: The source text.
        index: Where to start looking.

    Returns:
        The character, or None at the end of the text.
    """
    while index < len(text) and (text[index].isspace() or text[index] in OPENING_CHARS):
        index += 1
    return text[index] if index < len(text) else None


def _is_abbreviation_period(text: str, period: int) -> bool:
    """
    Whether the full stop at ``period`` belongs to a known abbreviation.

    Args:
        text: The source text.
        period: Index of a ``.`` in ``text``.

    Returns:
        True if the token before it is in ``NON_TERMINAL_ABBREVIATIONS``, or
        is the "al" of "et al.".
    """
    start = period
    while start > 0 and not text[start - 1].isspace() and text[start - 1] not in OPENING_CHARS:
        start -= 1
    token = text[start:period]
    if token == ET_AL[1]:
        return text[:start].rstrip().endswith(ET_AL[0])
    return token.lower() in NON_TERMINAL_ABBREVIATIONS


def _whitespace_has_line_break(text: str, start: int, end: int) -> bool:
    """
    Whether ``text[start:end]`` is whitespace containing a line break.

    Args:
        text: The source text.
        start: Start of the stretch.
        end: End of the stretch.

    Returns:
        True for a non-empty all-whitespace stretch with a ``\\n``.
    """
    stretch = text[start:end]
    return bool(stretch) and stretch.isspace() and "\n" in stretch


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
    if end == len(text) or not text[end:].strip():
        return True
    if not text[end].isspace():
        return False

    after = end
    while after < len(text) and text[after].isspace():
        after += 1
    if _whitespace_has_line_break(text, end, after):
        return True

    last = end
    while last > 0 and text[last - 1] in CLOSING_CHARS:
        last -= 1
    if last == 0 or text[last - 1] not in SENTENCE_TERMINATORS:
        return False
    if text[last - 1] == ".":
        if _is_abbreviation_period(text, last - 1):
            return False
        next_char = _next_word_char(text, end)
        if next_char is not None and next_char.islower():
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
    if _whitespace_has_line_break(text, content_end, before):
        return True
    if content_end < before and is_sentence_end(text, content_end):
        return True
    return content_end < before and _label_start(text, content_end) is not None


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


def complete_sentence_span(text: str, start: int, end: int) -> Optional[tuple[int, int]]:
    """
    Check that ``text[start:end]`` consists of one or more complete sentences.

    Surrounding whitespace is trimmed, and closing punctuation that the quote
    omitted is taken from the source (see ``_extend_over_sentence_end``).
    Nothing else is added: a span that starts or ends mid-sentence, or is
    only a section label, is rejected.

    Args:
        text: The source text (e.g. an abstract).
        start: Start offset of the quoted span.
        end: End offset (exclusive) of the quoted span.

    Returns:
        The ``(start, end)`` of the complete sentences, or None if the span is
        not one or more complete sentences.

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

    content = text[start:end].strip().strip("*#").strip()
    if content.endswith(":") and _is_label(content[:-1].strip("*").strip()):
        return None
    return start, end
