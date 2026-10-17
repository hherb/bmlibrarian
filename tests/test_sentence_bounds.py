"""
Tests for sentence-boundary checks used to validate citation passages (#289).

A citation must be at least one complete sentence: a fragment or a span that
starts or ends mid-sentence risks quoting the source out of context.
"""

import pytest

from bmlibrarian.utils.sentence_bounds import (
    complete_sentence_span,
    is_sentence_end,
    is_sentence_start,
)

ABSTRACT = (
    "Background: cardiovascular disease is common. Aspirin reduces the risk "
    "of heart attack in patients with cardiovascular disease, however it may "
    "increase bleeding risk. Conclusions: weigh benefits and harms."
)
SENTENCE = (
    "Aspirin reduces the risk of heart attack in patients with cardiovascular "
    "disease, however it may increase bleeding risk."
)


def _span(text: str, passage: str) -> tuple[int, int]:
    """The (start, end) of ``passage`` in ``text``."""
    start = text.index(passage)
    return start, start + len(passage)


def _complete(text: str, passage: str, last: bool = False) -> str | None:
    """The complete-sentence text for ``passage``, or None if rejected.

    Args:
        text: The source text.
        passage: The quoted span.
        last: Use the last occurrence of ``passage`` instead of the first.
    """
    start = text.rindex(passage) if last else text.index(passage)
    span = complete_sentence_span(text, start, start + len(passage))
    return None if span is None else text[span[0]:span[1]]


# ---- accepted -------------------------------------------------------------


@pytest.mark.parametrize(
    "passage",
    [
        SENTENCE,
        "cardiovascular disease is common.",  # after an inline label, lowercase start
        "Conclusions: weigh benefits and harms.",  # label included, ends the text
        "Background: cardiovascular disease is common.",  # first sentence of the text
        "cardiovascular disease is common. " + SENTENCE,  # several sentences
    ],
)
def test_complete_sentences_are_accepted(passage: str) -> None:
    """Spans running from a sentence start to a sentence end are kept as-is."""
    assert _complete(ABSTRACT, passage) == passage


def test_missing_closing_period_is_added_from_the_source() -> None:
    """A quote that stops just before the full stop gets the source's full stop."""
    assert _complete(ABSTRACT, SENTENCE[:-1]) == SENTENCE


def test_missing_period_and_bracket_are_added() -> None:
    """Closing brackets and quotes after the terminator are included too."""
    text = 'First point. The effect was large (n = 40). Next point.'
    assert _complete(text, "The effect was large (n = 40") == "The effect was large (n = 40)."


def test_surrounding_whitespace_is_trimmed() -> None:
    """Whitespace at either edge of the span is not part of the citation."""
    passage = " " + SENTENCE + " "
    assert _complete(ABSTRACT, passage) == SENTENCE


@pytest.mark.parametrize(
    ("text", "passage"),
    [
        (
            "**INTRODUCTION:** Virus particles were found. The purpose was to classify them.",
            "Virus particles were found.",
        ),
        (
            "Some species are rare. RESULTS: Morphological investigations were conducted.",
            "Morphological investigations were conducted.",
        ),
        (
            "**PURPOSE:** A trial.\n\n**RESULTS:** Five of 22 patients (23%; 95% CI, 10% to 43%) "
            "had partial responses. Median duration was 5 months.",
            "Five of 22 patients (23%; 95% CI, 10% to 43%) had partial responses.",
        ),
        ("Materials and methods: We enrolled 25 patients. Results followed.",
         "We enrolled 25 patients."),
    ],
)
def test_sentences_after_section_labels_are_accepted(text: str, passage: str) -> None:
    """Structured-abstract labels (plain or Markdown bold) start a sentence."""
    assert _complete(text, passage) == passage


@pytest.mark.parametrize(
    ("text", "passage"),
    [
        # Abbreviations and decimals inside the sentence are not sentence ends.
        ("Intro. Smith et al. (2019) showed a 3.4 mg/L rise, e.g. in Fig. 2 of the trial. End.",
         "Smith et al. (2019) showed a 3.4 mg/L rise, e.g. in Fig. 2 of the trial."),
        ("Intro. Dysteria bella sp. nov. and D. armata form a sister clade. End.",
         "Dysteria bella sp. nov. and D. armata form a sister clade."),
        ("Intro. Infection with E. coli was rare. End.", "Infection with E. coli was rare."),
        # "Al" (aluminium) at a sentence end is not the "al" of "et al.".
        ("Species (c) is monomeric Al. Group (b) includes simple species. End.",
         "Group (b) includes simple species."),
        # Question and exclamation marks end sentences.
        ("Does aspirin help? Yes, in most trials. End.", "Does aspirin help?"),
        # A sentence starting with a digit.
        ("Intro text. 25 patients were enrolled. End.", "25 patients were enrolled."),
        # Quotes and brackets around a sentence.
        ('Intro. "The drug works." End.', '"The drug works."'),
        ("Intro. (Data not shown.) End.", "(Data not shown.)"),
        # A blank line starts a new paragraph, whatever came before it.
        ("A title without a full stop\n\nThe body starts here.", "The body starts here."),
        # A single line break after a finished sentence, a label or a heading.
        ("Patients were enrolled.\nAspirin reduced the risk.", "Aspirin reduced the risk."),
        ("BACKGROUND\nAspirin reduced the risk of stroke.", "Aspirin reduced the risk of stroke."),
        ("## Results\nAspirin reduced the risk of stroke.", "Aspirin reduced the risk of stroke."),
        # Gene, molecule and unit names that start lowercase begin a sentence.
        ("The rate was measured. mRNA levels rose. End.", "mRNA levels rose."),
        ("Aspirin reduced the risk of stroke. p53 was mutated in most tumours.",
         "Aspirin reduced the risk of stroke."),
        ("Aspirin reduced the risk of stroke. p53 was mutated in most tumours.",
         "p53 was mutated in most tumours."),
        ("Renal function was stable. eGFR did not change. End.", "eGFR did not change."),
        ("Heart rate fell. β-blockers were well tolerated. End.", "β-blockers were well tolerated."),
        # Mixed-case labels of JAMA-style structured abstracts.
        ("Conclusions and Relevance: In this trial, aspirin helped.", "In this trial, aspirin helped."),
        ("Design, Setting, and Participants: We enrolled 40 adults. End.",
         "We enrolled 40 adults."),
        # "et al." ends a sentence at the end of the text.
        ("Intro. This was first shown by Smith et al.", "This was first shown by Smith et al."),
    ],
)
def test_biomedical_sentence_edge_cases_are_accepted(text: str, passage: str) -> None:
    """Abbreviations, initials, decimals and brackets do not break sentences."""
    assert _complete(text, passage) == passage


@pytest.mark.parametrize(
    ("text", "passage", "expected"),
    [
        # Closing marks taken from the source must have their opening mark.
        ("*Rates fell sharply.* Next point.", "Rates fell sharply.", "Rates fell sharply."),
        ("Intro. (Data not shown.) End.", "Data not shown.", "Data not shown."),
        ('Intro. "The drug works." End.', "The drug works.", "The drug works."),
        ('Intro. "The drug works." End.', 'The drug works."', "The drug works."),
        # Balanced marks are kept.
        ("We saw **lower bleeding risk**. Next point.", "We saw **lower bleeding risk",
         "We saw **lower bleeding risk**."),
        ("Intro. The dose (in mg). End.", "The dose (in mg", "The dose (in mg)."),
    ],
)
def test_borrowed_closing_marks_are_balanced(text: str, passage: str, expected: str) -> None:
    """Extending a quote never leaves an unmatched bracket, quote or ``*``."""
    assert _complete(text, passage) == expected


# ---- rejected -------------------------------------------------------------


@pytest.mark.parametrize(
    "passage",
    [
        "Aspirin",  # a bare key term
        "the",
        "a",
        ".",
        "spirin reduces the risk of heart attack",  # starts mid-word
        "Aspirin reduces the risk of heart attack",  # stops mid-sentence
        "Aspirin reduces the risk of heart attack in patients with cardiovascular disease",
        "however it may increase bleeding risk.",  # starts mid-sentence
        "may increase bleeding risk.",
        "risk. Conclusions: weigh",  # straddles a boundary
        "Background:",  # a label alone
        "Conclusions:",
    ],
)
def test_fragments_are_rejected(passage: str) -> None:
    """Words, clauses and spans that start or end mid-sentence are rejected."""
    assert _complete(ABSTRACT, passage) is None


@pytest.mark.parametrize(
    ("text", "passage"),
    [
        # "et al." followed by a capital is ambiguous; never treated as an end.
        ("Intro. As shown by Smith et al. The effect was large. End.",
         "The effect was large."),
        # The same in capitals.
        ("Intro. As shown by SMITH ET AL. The effect was large. End.",
         "The effect was large."),
        # A sentence glued to the previous one without a space.
        ("Intro.The effect was large. End.", "The effect was large."),
        # After a period followed by an ordinary lowercase word the period is
        # not an end, so a span starting there is mid-sentence.
        ("The rate was measured. levels rose. End.", "levels rose."),
        # A colon that is not a section label does not start a sentence.
        ("We compared two arms: Group A received aspirin. End.",
         "Group A received aspirin."),
        # A period after an initial is not a sentence end (U.S., S. aureus,
        # J. Smith); quoting from there drops the qualifier before it.
        ("In the U.S. Army personnel were enrolled. End.", "Army personnel were enrolled."),
        ("Infection with S. Aureus was rare. End.", "Aureus was rare."),
        ("J. Smith and K. Jones reported the trial. End.", "Jones reported the trial."),
        ("We used vit. D supplements daily. End.", "D supplements daily."),
    ],
)
def test_ambiguous_boundaries_are_rejected(text: str, passage: str) -> None:
    """When a boundary is ambiguous the span is rejected, never accepted."""
    assert _complete(text, passage) is None


@pytest.mark.parametrize(
    ("text", "passage", "last"),
    [
        # Hard-wrapped text: a single line break is not a sentence boundary.
        ("Aspirin reduced the\nrisk of stroke in older adults.", "Aspirin reduced the", False),
        ("Aspirin reduced the\nrisk of stroke in older adults.",
         "risk of stroke in older adults.", False),
        ("Smith et\nal. reported the trial.", "al. reported the trial.", False),
        # A bare term on its own line.
        ("Aspirin\nAspirin reduces the risk of stroke.", "Aspirin", False),
        # A label without a colon on its own line.
        ("BACKGROUND\nAspirin reduced the risk.", "BACKGROUND", False),
        ("BACKGROUND\n\nAspirin reduced the risk.", "BACKGROUND", False),
        # No closing punctuation: a truncated text or a keyword list.
        ("Intro. The abstract ends without punctuation",
         "The abstract ends without punctuation", False),
        ("Aspirin helped. KEYWORDS: aspirin, stroke", "aspirin, stroke", False),
        ("Aspirin helped. RESULTS: Aspirin", "Aspirin", True),
        # A single word is not a sentence, punctuated or not.
        ("Intro. RESULTS: Aspirin. End.", "Aspirin.", False),
        ("Intro. Next. End.", "Next.", False),
        # A label alone, even with a full stop.
        ("Intro. MATERIALS AND METHODS. We enrolled 40 adults.", "MATERIALS AND METHODS.", False),
    ],
)
def test_line_wrapped_and_unpunctuated_fragments_are_rejected(
    text: str, passage: str, last: bool
) -> None:
    """Line breaks and text ends without punctuation never end a citation."""
    assert _complete(text, passage, last=last) is None


@pytest.mark.parametrize(
    "text",
    ["BACKGROUND:\nAspirin works.", "**RESULTS:**\n\nAspirin works.", "Methods:\nWe did it."],
)
def test_label_on_its_own_line_is_not_a_sentence(text: str) -> None:
    """A section label ending at a line break is still not a citation."""
    label = text.split("\n")[0]
    assert _complete(text, label) is None


def test_sentence_including_its_label_is_accepted() -> None:
    """Quoting the label together with its sentence is fine."""
    text = "Intro. RESULTS: Five patients responded. End."
    assert _complete(text, "RESULTS: Five patients responded.") == "RESULTS: Five patients responded."


def test_whitespace_only_span_is_rejected() -> None:
    """A span with no letters is never a sentence."""
    assert complete_sentence_span(ABSTRACT, 0, 0) is None
    text = "One.   Two."
    assert complete_sentence_span(text, 4, 7) is None


# ---- building blocks ------------------------------------------------------


def test_is_sentence_start_and_end_at_text_edges() -> None:
    """The text's first position starts and its last position ends a sentence."""
    assert is_sentence_start(ABSTRACT, 0)
    assert is_sentence_end(ABSTRACT, len(ABSTRACT))


def test_is_sentence_end_requires_whitespace_after_the_terminator() -> None:
    """A full stop inside a token (decimal, domain name) is not an end."""
    text = "The dose was 3.4 mg. Done."
    assert not is_sentence_end(text, text.index("3.") + 2)
    assert is_sentence_end(text, text.index("mg.") + 3)


@pytest.mark.parametrize(
    ("args", "error"),
    [
        ((None, 0, 1), TypeError),
        (("text", "0", 1), TypeError),
        (("text", 3, 1), ValueError),
        (("text", -1, 2), ValueError),
        (("text", 0, 99), ValueError),
    ],
)
def test_complete_sentence_span_validates_arguments(args: tuple, error: type) -> None:
    """Bad arguments raise instead of being silently accepted."""
    with pytest.raises(error):
        complete_sentence_span(*args)
