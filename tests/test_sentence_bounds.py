"""
Tests for sentence-boundary checks used to validate citation passages (#289).

A citation must be at least one complete sentence: a fragment or a span that
starts or ends mid-sentence risks quoting the source out of context.
"""

import pytest

from bmlibrarian.utils.sentence_bounds import (
    MAX_WIDENING_CHARS,
    complete_sentence_span,
    enclosing_sentence_span,
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
        # Bold label with the colon outside the emphasis.
        ("Deaths fell. **Results**: Radiotherapy delays predicted outcome. End.",
         "Radiotherapy delays predicted outcome."),
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
        # "et al." ends a sentence at the end of the text or before a capital.
        ("Intro. This was first shown by Smith et al.", "This was first shown by Smith et al."),
        ("Intro. As shown by Smith et al. The effect was large. End.",
         "The effect was large."),
        ("Intro. As shown by SMITH ET AL. The effect was large. End.",
         "The effect was large."),
        ("Intro. It was studied by Knaus et al. Curves were plotted.",
         "It was studied by Knaus et al."),
        # A single capital letter after a word is a designator, not an initial.
        ("Intro. Rates were higher in type B. Type A was rare. End.",
         "Rates were higher in type B."),
        ("Intro. Rates were higher in type B. Type A was rare. End.", "Type A was rare."),
        ("Punctures were rarer in Group B. Incidence fell. End.", "Incidence fell."),
        ("Intro. Cases were TDP-43 types B, E and C. In contrast, others were not.",
         "Cases were TDP-43 types B, E and C."),
        # All-caps tokens are not the abbreviations they spell ("ca.", "no.").
        ("EPO rose with clinical CA. Umbilical IL-6 rose too. End.", "Umbilical IL-6 rose too."),
        ("Intro. Levels of NO. Were measured daily. End.", "Were measured daily."),
        # Labels with an apostrophe (Cochrane).
        ("No trials were found.\n\n**AUTHORS' CONCLUSIONS:** This review found no evidence. More.",
         "This review found no evidence."),
        # Source text that lost its spaces between sentences and labels.
        ("Intro.The effect was large. End.", "The effect was large."),
        ("Risk factors predicted stenosis.Conclusion:Pre-operative screening is needed.",
         "Pre-operative screening is needed."),
        ("Risk factors predicted stenosis.Conclusion:Pre-operative screening is needed.",
         "Risk factors predicted stenosis."),
        ("Background:The predictive value is unclear. End.", "The predictive value is unclear."),
        ("Intro (i.e. 20-32 years).Results:our results show an effect. End.",
         "our results show an effect."),
        # Time units are not abbreviations: their full stop ends a sentence.
        ("Patients waited 3 min. Then pain was measured. End.", "Patients waited 3 min."),
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
        # A lowercase word glued to a full stop is not a new sentence.
        ("Intro.the effect was large. End.", "the effect was large. End."),
        # After a period followed by an ordinary lowercase word the period is
        # not an end, so a span starting there is mid-sentence.
        ("The rate was measured. levels rose. End.", "levels rose."),
        # A colon that is not a section label does not start a sentence.
        ("We compared two arms: Group A received aspirin. End.",
         "Group A received aspirin."),
        # A period after an initial is not a sentence end (U.S., S. aureus,
        # J. M. Smith); quoting from there drops the qualifier before it.
        ("In the U.S. Army personnel were enrolled. End.", "Army personnel were enrolled."),
        ("Infection with S. aureus was rare. End.", "aureus was rare."),
        ("As J. M. Smith reported the trial. End.", "Smith reported the trial."),
        # Known abbreviations keep their full stop in mixed or lower case.
        ("Results are in No. 5 of the series. End.", "5 of the series."),
        ("We used vit. D supplements daily. End.", "D supplements daily."),
        # Both full stops of "J. M." are initials, not only the second.
        ("Data reported by J. M. Smith in 2019. End.", "Data reported by J."),
        ("Patients in the U.S.A. were enrolled here. End.", "Patients in the U."),
        ("Patients in the U.S.A. were enrolled here. End.", "S.A. were enrolled here."),
        # "et al." before anything but a capitalised word is not an end.
        ("Intro. Smith et al. (2019) showed a rise. End.", "Intro. Smith et al."),
        ("Intro. Smith et al. reported a rise. End.", "Intro. Smith et al."),
        ("Intro. Smith et al. 2019 showed a rise. End.", "Intro. Smith et al."),
        ("Intro. Smith et al. [12] showed a rise. End.", "Intro. Smith et al."),
        ("Intro. Smith et al. (Lancet, 2019) showed a rise. End.", "Intro. Smith et al."),
        # All-caps abbreviations before a digit or an all-caps word stay
        # abbreviations; only a capitalised word after them starts a sentence.
        ("We compared ASPIRIN VS. PLACEBO in adults with stroke.", "We compared ASPIRIN VS."),
        ("As shown in FIG. 2 the effect was large.", "As shown in FIG."),
        ("Patients were enrolled in ST. LOUIS hospitals.", "Patients were enrolled in ST."),
        ("Funded by MERCK & CO. Inc. All authors approved.", "Funded by MERCK & CO."),
        # Time units end a sentence only before a word that can start one.
        ("Patients waited 3 min. later pain was measured. End.", "Patients waited 3 min."),
        # Glued text after an abbreviation or initial, after a one-letter token
        # or inside a token (HGVS notation, domains) is not a boundary.
        ("See Fig.The figure shows it. End.", "The figure shows it."),
        ("Data in the U.S.Army were found. End.", "Army were found."),
        ("We found the variant p.Arg506Gln in five cases. End.", "We found the variant p."),
        ("The BRAF p.Val600Glu mutation was found in most tumours. End.",
         "Val600Glu mutation was found in most tumours."),
        ("Mutations (p.Gly12Asp) occurred in KRAS in all patients. End.",
         "Gly12Asp) occurred in KRAS in all patients."),
        ("Published in N.Engl J Med in 2020. End.", "Published in N."),
        ("As shown by J.Smith the effect was large in all.", "As shown by J."),
        ("The trial was registered at www.ClinicalTrials.gov under NCT01234567. End.",
         "The trial was registered at www."),
        ("The trial was registered at www.ClinicalTrials.gov under NCT01234567. End.",
         "ClinicalTrials.gov under NCT01234567."),
        # A bold phrase before a colon is not a label.
        ("Deaths fell. **two arms**: Group A received aspirin. End.", "Group A received aspirin."),
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


@pytest.mark.parametrize("invisible", ["​", "﻿", "­", "⁠"])
def test_invisible_format_characters_count_as_whitespace(invisible: str) -> None:
    """Zero-width characters at a boundary neither hide nor join a sentence (#302)."""
    text = f"Intro.{invisible} Rates fell in this cohort.{invisible} Next sentence."
    assert _complete(text, "Rates fell in this cohort.") == "Rates fell in this cohort."
    assert _complete(text, "Rates fell in this cohort." + invisible) == "Rates fell in this cohort."
    assert _complete(f"Rates fell.{invisible}", "Rates fell.") == "Rates fell."
    assert _complete(f"Intro.{invisible}Rates fell. End.", "Rates fell.") == "Rates fell."
    # Still no sentence end after an abbreviation or before a lowercase word.
    assert _complete(f"See Fig.{invisible} 2 for details.", "See Fig.") is None
    assert _complete(f"It rose.{invisible} and fell.", "It rose.") is None
    # Between the tokens of "J. M." and "et al." they do not split them.
    assert _complete(f"Written by J.{invisible} M. Smith in 2020. End.", f"Written by J.{invisible} M.") is None
    assert _complete(f"Data per Smith et{invisible} al. (2019) rose. End.", f"Data per Smith et{invisible} al.") is None
    # Nor do they glue two words into one.
    assert _complete(f"Intro. Rates{invisible}fell. End.", f"Rates{invisible}fell.") == f"Rates{invisible}fell."


def test_known_trade_offs_split_single_initials() -> None:
    """A lone initial before a capitalised word is cut like a designator (#303)."""
    assert _complete("Intro. Infection with S. Typhimurium was rare.", "Infection with S.") == (
        "Infection with S."
    )
    assert _complete("Intro. It was shown by J. Smith in 2020.", "It was shown by J.") == (
        "It was shown by J."
    )


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


# ---- source damage: fused labels (#304) and lost text --------------------


@pytest.mark.parametrize(
    ("text", "passage"),
    [
        # PubMed serves some structured abstracts with labels fused on (#304).
        ("The role of NfL remains unclear.ObjectiveThis study examined NfL in a cohort.",
         "This study examined NfL in a cohort."),
        ("ResultsWe estimated a 22% reduction in deaths.", "We estimated a 22% reduction in deaths."),
        ("Deaths fell.MethodsA cohort of 476 adults was followed.",
         "A cohort of 476 adults was followed."),
        ("Deaths fell. ConclusionsCSF NfL is a marker of decline.", "CSF NfL is a marker of decline."),
        # Text the source lost leaves a double space or "( " before a sentence.
        ("Rates rose (all  Women with hypothyroidism had more complications.",
         "Women with hypothyroidism had more complications."),
        ("It was lower on E4 ( A minority of women reported less desire.",
         "A minority of women reported less desire."),
        # A stray colon after a bold label.
        ("**CONCLUSIONS:** : Reconstruction does not delay chemotherapy.",
         "Reconstruction does not delay chemotherapy."),
    ],
)
def test_sentences_after_source_damage_are_accepted(text: str, passage: str) -> None:
    """A fused label or lost text before a sentence does not hide its start."""
    assert _complete(text, passage) == passage


@pytest.mark.parametrize(
    ("text", "passage"),
    [
        # The broken sentence before a lost-text gap still has no end.
        ("Rates rose (all  Women with hypothyroidism had more complications.", "Rates rose (all"),
        # A gap before a lowercase word, or across a line break, is no start.
        ("Rates rose in  women with hypothyroidism overall.", "women with hypothyroidism overall."),
        # Not a known label, or not at a sentence start.
        ("Deaths fell.CohortThe study ended.", "The study ended."),
        ("We used the ResultsWe tool here.", "We tool here."),
    ],
)
def test_damage_rules_do_not_accept_fragments(text: str, passage: str) -> None:
    """The source-damage rules only open a sentence start where one is certain."""
    assert _complete(text, passage) is None


# ---- widening a fragment to its sentence ----------------------------------


def _widen(text: str, passage: str, **kwargs: int) -> str | None:
    """The enclosing complete-sentence text for ``passage``, or None."""
    span = enclosing_sentence_span(text, *_span(text, passage), **kwargs)
    return None if span is None else text[span[0]:span[1]]


@pytest.mark.parametrize(
    "fragment",
    [
        "however it may increase bleeding risk.",  # starts mid-sentence
        "Aspirin reduces the risk",  # ends mid-sentence
        "risk of heart attack",  # both
        "spirin reduces",  # mid-word
        SENTENCE,  # already complete: unchanged
    ],
)
def test_fragments_widen_to_their_enclosing_sentence(fragment: str) -> None:
    """The widened span is the whole sentence around the fragment."""
    assert _widen(ABSTRACT, fragment) == SENTENCE


def test_widening_spans_several_sentences_for_a_fragment_across_a_boundary() -> None:
    """A fragment crossing a sentence end widens to both sentences."""
    text = "Deaths fell by half. Strokes fell by a third. Costs rose."
    assert _widen(text, "by half. Strokes fell") == "Deaths fell by half. Strokes fell by a third."


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        # The sentence never ends (truncated text, a keyword list).
        ("Aspirin reduces the risk of heart attack in patients", "risk of heart"),
        # The source broke the sentence off: never run it into the next one.
        ("Rates rose (all  Women had more complications.", "Rates rose"),
        ("Rates rose\n\nWomen had more complications.", "Rates rose"),
        # Only a label.
        ("BACKGROUND: Deaths fell.", "BACKGROUN"),
    ],
)
def test_fragments_without_an_enclosing_sentence_are_not_widened(text: str, fragment: str) -> None:
    """No certain enclosing sentence means None, never a guess."""
    assert _widen(text, fragment) is None


def test_widening_is_limited() -> None:
    """A fragment is not widened past ``max_added_chars``."""
    assert _widen(ABSTRACT, "risk of heart attack", max_added_chars=10) is None
    added = len(SENTENCE) - len("risk of heart attack")
    assert _widen(ABSTRACT, "risk of heart attack", max_added_chars=added) == SENTENCE
    long_sentence = "Aspirin " + "and aspirin " * MAX_WIDENING_CHARS + "worked."
    assert _widen(long_sentence, "worked.") is None


@pytest.mark.parametrize(
    ("args", "error"),
    [
        ((None, 0, 1), TypeError),
        (("text", 3, 1), ValueError),
        (("text", 0, 1, -1), ValueError),
        (("text", 0, 1, 1.5), TypeError),
        (("text", 0, 1, True), TypeError),
    ],
)
def test_enclosing_sentence_span_validates_arguments(args: tuple, error: type) -> None:
    """Bad arguments raise instead of being silently accepted."""
    with pytest.raises(error):
        enclosing_sentence_span(*args)
