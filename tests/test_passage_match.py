"""
Tests for bmlibrarian.utils.passage_match.

Covers whitespace/case normalisation with offset mapping, exact and fuzzy
passage location, rejection of paraphrases and fabrications, input
validation, and the performance bound that motivated the module (the old
sliding-window matcher in CitationFinderAgent took ~30 s per citation on a
1 kB abstract).
"""

import time

import pytest

from bmlibrarian.utils.passage_match import (
    PassageMatch,
    find_passage,
    normalize_with_offsets,
)

SENTENCES = [
    "Background: Atrial fibrillation is the most common sustained arrhythmia and is "
    "associated with a fivefold increase in the risk of stroke.",
    "Methods: We conducted a randomised controlled trial in 1,204 patients aged 65 "
    "years or older across 14 centres in Europe between 2015 and 2019.",
    "Patients were assigned to apixaban 5 mg twice daily or to warfarin with a target "
    "international normalised ratio of 2.0 to 3.0.",
    "The primary outcome was stroke or systemic embolism; the primary safety outcome "
    "was major bleeding according to ISTH criteria.",
    "Results: Over a median follow-up of 2.1 years, stroke or systemic embolism "
    "occurred in 1.27% per year in the apixaban group and 1.60% per year in the "
    "warfarin group (hazard ratio 0.79; 95% CI 0.66 to 0.95).",
    "Major bleeding occurred in 2.13% per year with apixaban versus 3.09% per year "
    "with warfarin.",
    "Conclusions: In elderly patients with atrial fibrillation, apixaban was superior "
    "to warfarin in preventing stroke or systemic embolism, caused less bleeding and "
    "resulted in lower mortality.",
]
ABSTRACT = " ".join(SENTENCES)

# Generous wall-clock bound for a fuzzy match on a ~10 kB text. The old
# implementation would take hours here; the new one takes milliseconds.
FUZZY_TIME_BUDGET_SECONDS = 2.0
LONG_TEXT_REPEATS = 10


class TestNormalizeWithOffsets:
    """normalize_with_offsets() lowercases, collapses whitespace, maps back."""

    def test_collapses_and_strips_whitespace(self) -> None:
        norm, offsets = normalize_with_offsets("  Foo \n\t Bar  ")
        assert norm == "foo bar"
        assert len(offsets) == len(norm)

    def test_offsets_point_into_original(self) -> None:
        original = "A  B\nC"
        norm, offsets = normalize_with_offsets(original)
        assert norm == "a b c"
        assert [original[i] for i in offsets] == ["A", " ", "B", "\n", "C"]

    def test_length_changing_lowercase_keeps_offsets_aligned(self) -> None:
        # "İ".lower() is two code points; both must map to the same source index.
        original = "İstanbul x"
        norm, offsets = normalize_with_offsets(original)
        assert len(offsets) == len(norm)
        assert offsets[0] == offsets[1] == 0

    def test_empty(self) -> None:
        assert normalize_with_offsets("   ") == ("", [])


class TestExactMatch:
    """Passages present verbatim (modulo case/whitespace) score 1.0."""

    def test_verbatim(self) -> None:
        match = find_passage(SENTENCES[4], ABSTRACT, min_similarity=0.95)
        assert match.matched
        assert match.similarity == 1.0
        assert match.text == SENTENCES[4]
        assert ABSTRACT[match.start:match.end] == SENTENCES[4]

    def test_case_differences_return_original_case(self) -> None:
        match = find_passage(SENTENCES[0].lower(), ABSTRACT, min_similarity=0.95)
        assert match.similarity == 1.0
        assert match.text == SENTENCES[0]

    def test_whitespace_differences_return_original_whitespace(self) -> None:
        text = "Type 2 diabetes   can often be\n managed through lifestyle changes."
        passage = "Type 2 diabetes can often be managed through lifestyle changes."
        match = find_passage(passage, text, min_similarity=0.95)
        assert match.similarity == 1.0
        assert match.text == text


class TestFuzzyMatch:
    """Near-verbatim passages map onto the exact source span."""

    def test_single_edit_returns_source_sentence(self) -> None:
        passage = SENTENCES[4].replace("hazard ratio", "hazard-ratio")
        match = find_passage(passage, ABSTRACT, min_similarity=0.95)
        assert match.matched
        assert 0.95 <= match.similarity < 1.0
        assert match.text == SENTENCES[4]

    def test_span_does_not_drift_late_in_text(self) -> None:
        # Regression: the old matcher counted only non-whitespace characters
        # when mapping back, so the start drifted one char per preceding word.
        passage = SENTENCES[6].replace("lower mortality", "lower  mortality;")
        match = find_passage(passage, ABSTRACT, min_similarity=0.95)
        assert match.matched
        assert match.text.startswith("Conclusions:")
        assert match.text.endswith("mortality.")

    def test_punctuation_change(self) -> None:
        text = (
            "Aspirin reduces the risk of heart attack in patients with cardiovascular "
            "disease, however it may increase bleeding risk."
        )
        passage = text.replace("disease, however", "disease; however")
        match = find_passage(passage, text, min_similarity=0.95)
        assert match.matched
        assert match.text == text

    def test_returned_text_is_from_source_not_passage(self) -> None:
        passage = SENTENCES[2].replace("twice daily", "twice-daily")
        match = find_passage(passage, ABSTRACT, min_similarity=0.95)
        assert match.matched
        assert "twice daily" in match.text
        assert match.text in ABSTRACT

    def test_long_text_is_fast(self) -> None:
        text = " ".join(
            f"Section {i}. " + " ".join(SENTENCES) for i in range(LONG_TEXT_REPEATS)
        )
        passage = SENTENCES[4].replace("hazard ratio", "hazard-ratio")
        started = time.perf_counter()
        match = find_passage(passage, text, min_similarity=0.95)
        elapsed = time.perf_counter() - started
        assert match.matched
        assert match.text == SENTENCES[4]
        assert elapsed < FUZZY_TIME_BUDGET_SECONDS


class TestRejection:
    """Paraphrases and fabrications fall below the threshold."""

    def test_fabricated(self) -> None:
        match = find_passage(
            "Statins are the most effective treatment for lowering cholesterol levels.",
            ABSTRACT,
            min_similarity=0.95,
        )
        assert not match.matched
        assert match.text is None
        assert match.start is None and match.end is None
        assert match.similarity < 0.95

    def test_paraphrase(self) -> None:
        text = (
            "Liver transplantation with living related donor has been recently "
            "developed to compensate for the insufficient number of liver grafts "
            "for children."
        )
        passage = (
            "Liver transplantation with living related donors has recently been "
            "developed to address the insufficient number of liver grafts for children"
        )
        match = find_passage(passage, text, min_similarity=0.95)
        assert not match.matched
        assert match.similarity < 0.95

    def test_best_similarity_reported_on_rejection(self) -> None:
        passage = SENTENCES[4].replace("stroke or systemic embolism", "any thromboembolic event")
        match = find_passage(passage, ABSTRACT, min_similarity=0.95)
        assert not match.matched
        assert 0.5 < match.similarity < 0.95

    @pytest.mark.parametrize(
        ("passage", "text"),
        [("", ABSTRACT), ("   ", ABSTRACT), ("some passage", ""), ("ab", "xyz")],
    )
    def test_degenerate_inputs(self, passage: str, text: str) -> None:
        match = find_passage(passage, text, min_similarity=0.95)
        assert match == PassageMatch(similarity=match.similarity)
        assert not match.matched


class TestValidation:
    """Invalid arguments raise instead of silently matching."""

    @pytest.mark.parametrize("threshold", [0.0, -0.1, 1.01])
    def test_threshold_out_of_range(self, threshold: float) -> None:
        with pytest.raises(ValueError):
            find_passage("abc", "abc", min_similarity=threshold)

    def test_non_string_inputs(self) -> None:
        with pytest.raises(TypeError):
            find_passage(None, "abc", min_similarity=0.95)  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            find_passage("abc", None, min_similarity=0.95)  # type: ignore[arg-type]
