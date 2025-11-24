"""
Tests for paper_weight_extractors.py

Tests cover:
- Study type extraction from various document formats
- Sample size extraction with different patterns
- Power calculation detection
- Confidence interval detection
- Edge cases: empty text, no matches, multiple matches
"""

import pytest
import math

from bmlibrarian.agents.paper_weight.extractors import (
    STUDY_TYPE_PRIORITY,
    DEFAULT_STUDY_TYPE_KEYWORDS,
    DEFAULT_STUDY_TYPE_HIERARCHY,
    STUDY_TYPE_EXCLUSIONS,
    SAMPLE_SIZE_PATTERNS,
    POWER_CALCULATION_KEYWORDS,
    CI_PATTERNS,
    extract_text_context,
    find_sample_size,
    calculate_sample_size_score,
    has_power_calculation,
    find_power_calc_context,
    has_ci_reporting,
    has_exclusion_pattern,
    extract_study_type,
    extract_sample_size_dimension,
    get_extracted_sample_size,
    get_extracted_study_type,
)
from bmlibrarian.agents.paper_weight import DIMENSION_STUDY_DESIGN, DIMENSION_SAMPLE_SIZE


class TestExtractTextContext:
    """Tests for extract_text_context function."""

    def test_basic_context_extraction(self):
        """Test basic context extraction around keyword."""
        text = "This is a randomized controlled trial with 100 participants."
        context = extract_text_context(text, "randomized", context_chars=10)
        
        assert "randomized" in context
        assert len(context) < len(text)

    def test_keyword_at_start(self):
        """Test context when keyword is at start of text."""
        text = "RCT study design was used for this research project."
        context = extract_text_context(text, "RCT", context_chars=20)
        
        assert context.startswith("RCT")
        assert "..." in context  # Should have ellipsis at end

    def test_keyword_at_end(self):
        """Test context when keyword is at end of text."""
        text = "The study was conducted as a double-blind RCT"
        context = extract_text_context(text, "RCT", context_chars=20)
        
        assert context.endswith("RCT")
        assert "..." in context  # Should have ellipsis at start

    def test_keyword_not_found(self):
        """Test when keyword is not found."""
        text = "This is a cohort study."
        context = extract_text_context(text, "randomized", context_chars=20)
        
        assert context == ""

    def test_empty_text(self):
        """Test with empty text."""
        context = extract_text_context("", "keyword", context_chars=20)
        assert context == ""


class TestFindSampleSize:
    """Tests for find_sample_size function."""

    def test_n_equals_pattern(self):
        """Test n = 450 pattern."""
        text = "We enrolled n = 450 participants in the study."
        size = find_sample_size(text)
        assert size == 450

    def test_N_equals_pattern(self):
        """Test N = 450 pattern."""
        text = "The total sample size was N = 1000."
        size = find_sample_size(text)
        assert size == 1000

    def test_participants_pattern(self):
        """Test '450 participants' pattern."""
        text = "A total of 250 participants were recruited."
        size = find_sample_size(text)
        assert size == 250

    def test_patients_pattern(self):
        """Test '450 patients' pattern."""
        text = "We analyzed data from 300 patients."
        size = find_sample_size(text)
        assert size == 300

    def test_sample_size_of_pattern(self):
        """Test 'sample size of 450' pattern."""
        text = "The study had a sample size of 500."
        size = find_sample_size(text)
        assert size == 500

    def test_multiple_matches_returns_largest(self):
        """Test that largest value is returned when multiple matches."""
        text = "We enrolled 100 participants in group A and 150 participants in group B, for a total of 250 participants."
        size = find_sample_size(text)
        assert size == 250

    def test_no_match(self):
        """Test when no sample size found."""
        text = "This study examined the effects of treatment."
        size = find_sample_size(text)
        assert size is None

    def test_filter_unrealistic_values(self):
        """Test that unrealistic values are filtered."""
        text = "The year 2020 and n = 50 participants."
        size = find_sample_size(text)
        assert size == 50  # 2020 should be filtered out by patterns

    def test_min_n_filter(self):
        """Test minimum sample size filter."""
        text = "n = 3 patients were examined."
        size = find_sample_size(text, min_n=5)
        assert size is None

    def test_max_n_filter(self):
        """Test maximum sample size filter."""
        text = "n = 5000000 records."
        size = find_sample_size(text, max_n=1000000)
        assert size is None


class TestCalculateSampleSizeScore:
    """Tests for calculate_sample_size_score function."""

    def test_basic_calculation(self):
        """Test basic logarithmic calculation."""
        # log10(100) = 2, * 2.0 = 4.0
        score = calculate_sample_size_score(100, log_multiplier=2.0)
        assert abs(score - 4.0) < 0.01

    def test_large_sample(self):
        """Test with large sample size (should cap at 10)."""
        # log10(100000) = 5, * 2.0 = 10.0
        score = calculate_sample_size_score(100000, log_multiplier=2.0)
        assert score == 10.0

    def test_very_large_sample_caps_at_10(self):
        """Test that score caps at 10."""
        score = calculate_sample_size_score(1000000, log_multiplier=2.0)
        assert score == 10.0

    def test_zero_sample(self):
        """Test with zero sample size."""
        score = calculate_sample_size_score(0)
        assert score == 0.0

    def test_negative_sample(self):
        """Test with negative sample size."""
        score = calculate_sample_size_score(-10)
        assert score == 0.0

    def test_custom_multiplier(self):
        """Test with custom multiplier."""
        # log10(100) = 2, * 3.0 = 6.0
        score = calculate_sample_size_score(100, log_multiplier=3.0)
        assert abs(score - 6.0) < 0.01


class TestHasPowerCalculation:
    """Tests for has_power_calculation function."""

    def test_power_calculation_present(self):
        """Test detection of power calculation."""
        text = "A power calculation was performed to determine the sample size."
        assert has_power_calculation(text) is True

    def test_power_analysis_present(self):
        """Test detection of power analysis."""
        text = "Power analysis indicated we needed 200 participants."
        assert has_power_calculation(text) is True

    def test_sample_size_calculation_present(self):
        """Test detection of sample size calculation."""
        text = "The sample size calculation showed 150 patients were required."
        assert has_power_calculation(text) is True

    def test_case_insensitive(self):
        """Test case insensitive matching."""
        text = "POWER CALCULATION was done a priori."
        assert has_power_calculation(text) is True

    def test_not_present(self):
        """Test when power calculation not mentioned."""
        text = "We enrolled 100 participants in the study."
        assert has_power_calculation(text) is False


class TestHasCiReporting:
    """Tests for has_ci_reporting function."""

    def test_confidence_interval_text(self):
        """Test detection of 'confidence interval'."""
        text = "The 95% confidence interval was 1.2 to 3.4."
        assert has_ci_reporting(text) is True

    def test_ci_abbreviation(self):
        """Test detection of CI abbreviation."""
        text = "HR 1.5 (95% CI 1.1-2.0)"
        assert has_ci_reporting(text) is True

    def test_bracket_notation(self):
        """Test detection of bracket notation [1.2, 3.4]."""
        text = "The mean was 5.0 [3.2, 6.8]."
        assert has_ci_reporting(text) is True

    def test_not_present(self):
        """Test when CI not reported."""
        text = "The mean was 5.0 with SD of 1.2."
        assert has_ci_reporting(text) is False


class TestExtractStudyType:
    """Tests for extract_study_type function."""

    def test_rct_detection(self):
        """Test RCT detection."""
        document = {'abstract': 'This was a randomized controlled trial of aspirin.'}
        result = extract_study_type(document)
        
        assert result.dimension_name == DIMENSION_STUDY_DESIGN
        assert result.score == 8.0  # RCT score from hierarchy
        assert len(result.details) == 1
        assert result.details[0].extracted_value == 'rct'

    def test_systematic_review_detection(self):
        """Test systematic review detection (highest priority)."""
        document = {'abstract': 'This systematic review examines evidence from RCTs.'}
        result = extract_study_type(document)
        
        assert result.score == 10.0
        assert result.details[0].extracted_value == 'systematic_review'

    def test_meta_analysis_detection(self):
        """Test meta-analysis detection."""
        document = {'abstract': 'We conducted a meta-analysis of 15 studies.'}
        result = extract_study_type(document)
        
        assert result.score == 10.0
        assert result.details[0].extracted_value == 'meta_analysis'

    def test_cohort_prospective_detection(self):
        """Test prospective cohort detection."""
        document = {'abstract': 'This prospective cohort study followed 1000 patients.'}
        result = extract_study_type(document)
        
        assert result.score == 6.0
        assert result.details[0].extracted_value == 'cohort_prospective'

    def test_case_control_detection(self):
        """Test case-control detection."""
        document = {'abstract': 'We conducted a case-control study.'}
        result = extract_study_type(document)
        
        assert result.score == 4.0
        assert result.details[0].extracted_value == 'case_control'

    def test_unknown_study_type(self):
        """Test when no study type detected."""
        document = {'abstract': 'We examined the effects of treatment.'}
        result = extract_study_type(document)
        
        assert result.score == 5.0  # Neutral score
        assert result.details[0].extracted_value == 'unknown'

    def test_priority_order(self):
        """Test that higher priority study types are detected first."""
        # Both RCT and meta-analysis mentioned, meta-analysis should win
        document = {'abstract': 'This meta-analysis included 10 randomized controlled trials.'}
        result = extract_study_type(document)
        
        # meta_analysis comes before rct in priority
        assert result.details[0].extracted_value in ['systematic_review', 'meta_analysis']

    def test_methods_text_searched(self):
        """Test that methods_text is also searched."""
        document = {
            'abstract': 'We studied 100 patients.',
            'methods_text': 'This was a randomized controlled trial.'
        }
        result = extract_study_type(document)
        
        assert result.details[0].extracted_value == 'rct'

    def test_empty_document(self):
        """Test with empty document."""
        document = {'abstract': ''}
        result = extract_study_type(document)
        
        assert result.score == 5.0
        assert result.details[0].extracted_value == 'unknown'

    def test_none_abstract(self):
        """Test with None abstract."""
        document = {'abstract': None}
        result = extract_study_type(document)
        
        assert result.score == 5.0


class TestExtractSampleSizeDimension:
    """Tests for extract_sample_size_dimension function."""

    def test_basic_extraction(self):
        """Test basic sample size extraction."""
        document = {'abstract': 'We enrolled n = 450 participants.'}
        result = extract_sample_size_dimension(document)
        
        assert result.dimension_name == DIMENSION_SAMPLE_SIZE
        assert result.score > 0
        assert len(result.details) >= 1
        assert result.details[0].extracted_value == '450'

    def test_with_power_calculation_bonus(self):
        """Test that power calculation adds bonus."""
        document = {
            'abstract': 'We enrolled n = 100 participants. A power calculation showed 80% power.'
        }
        result = extract_sample_size_dimension(document)
        
        # Should have both extracted_n and power_calculation details
        components = [d.component for d in result.details]
        assert 'extracted_n' in components
        assert 'power_calculation' in components

    def test_with_ci_reporting_bonus(self):
        """Test that CI reporting adds bonus."""
        document = {
            'abstract': 'We enrolled n = 100 participants. The 95% CI was 1.2-3.4.'
        }
        result = extract_sample_size_dimension(document)
        
        components = [d.component for d in result.details]
        assert 'ci_reporting' in components

    def test_no_sample_size_found(self):
        """Test when no sample size found."""
        document = {'abstract': 'This study examined treatment effects.'}
        result = extract_sample_size_dimension(document)
        
        assert result.score == 0.0
        assert result.details[0].extracted_value == 'not_found'

    def test_custom_scoring_config(self):
        """Test with custom scoring configuration."""
        document = {'abstract': 'We enrolled n = 100 participants.'}
        config = {
            'log_multiplier': 3.0,
            'power_calculation_bonus': 1.0,
            'ci_reported_bonus': 0.25
        }
        result = extract_sample_size_dimension(document, scoring_config=config)
        
        # log10(100) * 3.0 = 6.0
        assert abs(result.score - 6.0) < 0.1


class TestGetExtractedValues:
    """Tests for get_extracted_sample_size and get_extracted_study_type."""

    def test_get_extracted_sample_size(self):
        """Test extracting sample size from DimensionScore."""
        document = {'abstract': 'We enrolled n = 200 participants.'}
        result = extract_sample_size_dimension(document)
        
        sample_size = get_extracted_sample_size(result)
        assert sample_size == 200

    def test_get_extracted_sample_size_not_found(self):
        """Test when sample size not found."""
        document = {'abstract': 'No sample size mentioned.'}
        result = extract_sample_size_dimension(document)
        
        sample_size = get_extracted_sample_size(result)
        assert sample_size is None

    def test_get_extracted_study_type(self):
        """Test extracting study type from DimensionScore."""
        document = {'abstract': 'This was a randomized controlled trial.'}
        result = extract_study_type(document)
        
        study_type = get_extracted_study_type(result)
        assert study_type == 'rct'

    def test_get_extracted_study_type_unknown(self):
        """Test when study type is unknown."""
        document = {'abstract': 'We studied patients.'}
        result = extract_study_type(document)
        
        study_type = get_extracted_study_type(result)
        assert study_type == 'unknown'


class TestConstants:
    """Tests for module constants."""

    def test_study_type_priority(self):
        """Test study type priority order."""
        assert STUDY_TYPE_PRIORITY[0] == 'systematic_review'
        assert STUDY_TYPE_PRIORITY[1] == 'meta_analysis'
        # quasi_experimental should come BEFORE rct to catch non-randomized trials first
        assert STUDY_TYPE_PRIORITY[2] == 'quasi_experimental'
        assert STUDY_TYPE_PRIORITY[3] == 'rct'
        assert STUDY_TYPE_PRIORITY[4] == 'pilot_feasibility'
        assert STUDY_TYPE_PRIORITY[2] == 'interventional_single_arm'
        assert STUDY_TYPE_PRIORITY[4] == 'cohort_prospective'

    def test_default_keywords_coverage(self):
        """Test that all priority types have keywords."""
        for study_type in STUDY_TYPE_PRIORITY:
            assert study_type in DEFAULT_STUDY_TYPE_KEYWORDS
            assert len(DEFAULT_STUDY_TYPE_KEYWORDS[study_type]) > 0

    def test_hierarchy_scores(self):
        """Test hierarchy score values."""
        assert DEFAULT_STUDY_TYPE_HIERARCHY['systematic_review'] == 10.0
        assert DEFAULT_STUDY_TYPE_HIERARCHY['rct'] == 8.0
        assert DEFAULT_STUDY_TYPE_HIERARCHY['quasi_experimental'] == 7.0
        assert DEFAULT_STUDY_TYPE_HIERARCHY['pilot_feasibility'] == 6.5
        assert DEFAULT_STUDY_TYPE_HIERARCHY['case_report'] == 1.0

    def test_exclusions_defined(self):
        """Test that exclusion patterns are defined for RCT."""
        assert 'rct' in STUDY_TYPE_EXCLUSIONS
        assert 'non-randomized' in STUDY_TYPE_EXCLUSIONS['rct']


class TestHasExclusionPattern:
    """Tests for has_exclusion_pattern function."""

    def test_exclusion_found_before_keyword(self):
        """Test detection of exclusion pattern before keyword."""
        text = "this was a non-randomized trial of aspirin"
        result = has_exclusion_pattern(
            text, "randomized trial", ['non-randomized']
        )
        assert result is True

    def test_no_exclusion_when_absent(self):
        """Test no exclusion when pattern is not present."""
        text = "this was a double-blind randomized trial of aspirin"
        result = has_exclusion_pattern(
            text, "randomized trial", ['non-randomized']
        )
        assert result is False

    def test_exclusion_with_hyphen_variants(self):
        """Test exclusion with different hyphen formats."""
        text = "this nonrandomized trial tested new medication"
        result = has_exclusion_pattern(
            text, "randomized trial", ['nonrandomized']
        )
        assert result is True

    def test_exclusion_case_insensitive(self):
        """Test that exclusion matching is case insensitive."""
        text = "This was a NON-RANDOMIZED trial of the treatment"
        result = has_exclusion_pattern(
            text.lower(), "randomized trial", ['non-randomized']
        )
        assert result is True

    def test_keyword_not_found(self):
        """Test returns False when keyword not found."""
        text = "this is a cohort study"
        result = has_exclusion_pattern(
            text, "randomized trial", ['non-randomized']
        )
        assert result is False


class TestKeywordCollisionFix:
    """Tests for keyword collision prevention (PR#158 fix).

    These tests verify that "non-randomized trial" does NOT incorrectly
    match as an RCT, which was a potential issue when "randomized trial"
    is a substring of "non-randomized trial".
    """

    def test_non_randomized_trial_detected_as_quasi_experimental(self):
        """Test that 'non-randomized trial' is detected as quasi_experimental."""
        document = {'abstract': 'This was a non-randomized trial of aspirin therapy.'}
        result = extract_study_type(document)

        assert result.details[0].extracted_value == 'quasi_experimental'
        assert result.score == 7.0

    def test_nonrandomized_variant_detected(self):
        """Test 'nonrandomized' (without hyphen) is detected correctly."""
        document = {'abstract': 'A nonrandomized trial was conducted.'}
        result = extract_study_type(document)

        assert result.details[0].extracted_value == 'quasi_experimental'

    def test_rct_still_detected_correctly(self):
        """Test that legitimate RCTs are still detected correctly."""
        document = {'abstract': 'This was a randomized controlled trial of aspirin.'}
        result = extract_study_type(document)

        assert result.details[0].extracted_value == 'rct'
        assert result.score == 8.0

    def test_double_blind_randomized_detected_as_rct(self):
        """Test that 'double-blind randomized' is detected as RCT."""
        document = {'abstract': 'We conducted a double-blind randomized study.'}
        result = extract_study_type(document)

        assert result.details[0].extracted_value == 'rct'

    def test_quasi_experimental_detected(self):
        """Test 'quasi-experimental' keyword detection."""
        document = {'abstract': 'This quasi-experimental study examined outcomes.'}
        result = extract_study_type(document)

        assert result.details[0].extracted_value == 'quasi_experimental'

    def test_single_arm_trial_detected(self):
        """Test 'single-arm trial' is detected as quasi_experimental."""
        document = {'abstract': 'A single-arm trial was performed to evaluate efficacy.'}
        result = extract_study_type(document)

        assert result.details[0].extracted_value == 'quasi_experimental'

    def test_open_label_trial_detected(self):
        """Test 'open-label trial' is detected as quasi_experimental."""
        document = {'abstract': 'An open-label trial was conducted.'}
        result = extract_study_type(document)

        assert result.details[0].extracted_value == 'quasi_experimental'

    def test_rct_priority_over_open_label_randomized(self):
        """Test that open-label RCT is detected correctly.

        "Open-label randomized controlled trial" is still an RCT - open-label
        refers to blinding (participants know which treatment), not to
        randomization. The "randomized controlled trial" keyword matches RCT.
        """
        document = {
            'abstract': 'This open-label randomized controlled trial tested the drug.'
        }
        result = extract_study_type(document)

        # Should detect as RCT because "randomized controlled trial" is a more
        # complete and specific match than "open-label trial"
        assert result.details[0].extracted_value == 'rct'

    def test_standalone_open_label_trial_detected_as_quasi(self):
        """Test that standalone 'open-label trial' (without 'randomized') is quasi_experimental."""
        document = {
            'abstract': 'This was an open-label trial to assess tolerability.'
        }
        result = extract_study_type(document)

        # Standalone "open-label trial" without randomization keywords is quasi_experimental
        assert result.details[0].extracted_value == 'quasi_experimental'


class TestPilotFeasibilityStudies:
    """Tests for pilot and feasibility study detection (PR#158 enhancement)."""

    def test_pilot_study_detected(self):
        """Test 'pilot study' detection."""
        document = {'abstract': 'This pilot study examined the intervention.'}
        result = extract_study_type(document)

        assert result.details[0].extracted_value == 'pilot_feasibility'
        assert result.score == 6.5

    def test_pilot_trial_detected(self):
        """Test 'pilot trial' detection."""
        document = {'abstract': 'A pilot trial was conducted with 20 patients.'}
        result = extract_study_type(document)

        assert result.details[0].extracted_value == 'pilot_feasibility'

    def test_feasibility_study_detected(self):
        """Test 'feasibility study' detection."""
        document = {'abstract': 'This feasibility study assessed patient recruitment.'}
        result = extract_study_type(document)

        assert result.details[0].extracted_value == 'pilot_feasibility'

    def test_proof_of_concept_study_detected(self):
        """Test 'proof-of-concept study' detection."""
        document = {'abstract': 'A proof-of-concept study demonstrated efficacy.'}
        result = extract_study_type(document)

        assert result.details[0].extracted_value == 'pilot_feasibility'

    def test_proof_of_concept_without_hyphen_detected(self):
        """Test 'proof of concept study' (without hyphens) detection."""
        document = {'abstract': 'This was a proof of concept study for the device.'}
        result = extract_study_type(document)

        assert result.details[0].extracted_value == 'pilot_feasibility'


class TestExclusionPatternIntegration:
    """Integration tests for exclusion pattern functionality."""

    def test_exclusion_prevents_false_positive_rct(self):
        """Test that exclusion patterns prevent false positive RCT matches.

        When the abstract contains 'non-randomized' followed by 'randomized trial',
        the exclusion pattern should prevent the RCT match.
        """
        document = {
            'abstract': 'This non-randomized trial compared outcomes. '
                       'The randomized trial approach was not suitable.'
        }
        result = extract_study_type(document)

        # Should detect quasi_experimental first due to priority order
        assert result.details[0].extracted_value == 'quasi_experimental'

    def test_without_randomization_detected(self):
        """Test 'without randomization' exclusion."""
        # This tests that even if 'randomized' appears later, the exclusion works
        document = {
            'abstract': 'This study was conducted without randomization. '
                       'A randomized design would have been preferable.'
        }
        result = extract_study_type(document)

        # Since no quasi_experimental keyword is present, and RCT is excluded,
        # it should fall through to unknown or another match
        # Actually, 'without randomization' is in exclusions but there's no
        # quasi_experimental keyword, so it would be unknown
        assert result.details[0].extracted_value == 'unknown'
        assert DEFAULT_STUDY_TYPE_HIERARCHY['interventional_single_arm'] == 7.0
        assert DEFAULT_STUDY_TYPE_HIERARCHY['cohort_prospective'] == 6.0
        assert DEFAULT_STUDY_TYPE_HIERARCHY['case_report'] == 1.0


class TestInterventionalSingleArmDetection:
    """Tests for interventional_single_arm study type detection.

    This study type was added to capture open-label, single-arm interventional
    studies that fall between RCTs and prospective cohort studies in the
    evidence hierarchy.
    """

    def test_open_label_detection(self):
        """Test detection of open-label studies."""
        document = {'abstract': 'This was an open-label study of telmisartan.'}
        result = extract_study_type(document)

        assert result.score == 7.0
        assert result.details[0].extracted_value == 'interventional_single_arm'

    def test_open_labeled_detection(self):
        """Test detection of open-labeled studies (hyphenated variant)."""
        document = {'abstract': 'Patients were administered telmisartan using an open-labeled and prospective protocol.'}
        result = extract_study_type(document)

        assert result.score == 7.0
        assert result.details[0].extracted_value == 'interventional_single_arm'

    def test_open_label_no_hyphen_detection(self):
        """Test detection of 'open label' without hyphen."""
        document = {'abstract': 'This open label study examined drug efficacy.'}
        result = extract_study_type(document)

        assert result.score == 7.0
        assert result.details[0].extracted_value == 'interventional_single_arm'

    def test_single_arm_trial_detection(self):
        """Test detection of single-arm trial."""
        document = {'abstract': 'We conducted a single-arm trial to assess treatment effects.'}
        result = extract_study_type(document)

        assert result.score == 7.0
        assert result.details[0].extracted_value == 'interventional_single_arm'

    def test_single_arm_study_detection(self):
        """Test detection of single-arm study."""
        document = {'abstract': 'This was a single arm study without control group.'}
        result = extract_study_type(document)

        assert result.score == 7.0
        assert result.details[0].extracted_value == 'interventional_single_arm'

    def test_prospective_protocol_detection(self):
        """Test detection of prospective protocol studies."""
        document = {'abstract': 'Patients were treated using a prospective protocol.'}
        result = extract_study_type(document)

        assert result.score == 7.0
        assert result.details[0].extracted_value == 'interventional_single_arm'

    def test_uncontrolled_trial_detection(self):
        """Test detection of uncontrolled trial.

        Note: We use 'uncontrolled trial' instead of 'non-randomized trial'
        because 'non-randomized trial' contains 'randomized trial' as a substring,
        which gets matched by the RCT keywords first (higher priority).
        """
        document = {'abstract': 'This was an uncontrolled trial of the new intervention.'}
        result = extract_study_type(document)

        assert result.score == 7.0
        assert result.details[0].extracted_value == 'interventional_single_arm'

    def test_before_and_after_study_detection(self):
        """Test detection of before-and-after study."""
        document = {'abstract': 'We conducted a before-and-after study of the intervention.'}
        result = extract_study_type(document)

        assert result.score == 7.0
        assert result.details[0].extracted_value == 'interventional_single_arm'

    def test_pretest_posttest_detection(self):
        """Test detection of pretest-posttest study design."""
        document = {'abstract': 'A pretest-posttest design was used to evaluate outcomes.'}
        result = extract_study_type(document)

        assert result.score == 7.0
        assert result.details[0].extracted_value == 'interventional_single_arm'

    def test_rct_takes_priority_over_open_label(self):
        """Test that RCT detection takes priority over open-label."""
        # Some studies are described as 'open-label randomized trials'
        document = {'abstract': 'This was an open-label randomized controlled trial.'}
        result = extract_study_type(document)

        # RCT should win because 'randomized controlled trial' is checked first
        # and RCT is higher in priority
        assert result.details[0].extracted_value == 'rct'
        assert result.score == 8.0

    def test_real_world_telmisartan_abstract(self):
        """Test with the actual telmisartan abstract that prompted this fix.

        The abstract states: 'using an open-labeled and prospective protocol'
        which should be detected as interventional_single_arm.
        """
        abstract = """Several studies have shown that angiotensin II receptor blockers (ARBs)
        improve endothelial function and arterial stiffness. Telmisartan is a highly selective
        ARB that activates peroxisome proliferator-activated receptor gamma (PPARgamma).
        The purpose of this study was to evaluate the effects of telmisartan, such as
        endothelial function, arterial stiffness, and insulin sensitivity, in patients with
        essential hypertension. Thirty-nine patients with essential hypertension were
        administered telmisartan (80 mg once daily) using an open-labeled and prospective protocol."""

        document = {'abstract': abstract}
        result = extract_study_type(document)

        assert result.details[0].extracted_value == 'interventional_single_arm'
        assert result.score == 7.0
        assert 'open-labeled' in result.details[0].evidence_text
