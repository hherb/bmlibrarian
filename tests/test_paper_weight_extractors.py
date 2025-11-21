"""Tests for rule-based extractors in PaperWeightAssessmentAgent.

This module tests the study type detection and sample size extraction
functionality implemented in Step 4 of the PaperWeight system.
"""

import pytest
import math
from unittest.mock import patch, MagicMock


# Mock the config loading before importing the agent
@pytest.fixture(autouse=True)
def mock_config():
    """Mock configuration to avoid needing actual config files."""
    mock_agent_config = {
        'temperature': 0.3,
        'top_p': 0.9,
        'max_tokens': 3000,
        'version': '1.0.0',
        'dimension_weights': {
            'study_design': 0.25,
            'sample_size': 0.15,
            'methodological_quality': 0.30,
            'risk_of_bias': 0.20,
            'replication_status': 0.10
        },
        'study_type_hierarchy': {
            'systematic_review': 10.0,
            'meta_analysis': 10.0,
            'rct': 8.0,
            'cohort_prospective': 6.0,
            'cohort_retrospective': 5.0,
            'case_control': 4.0,
            'cross_sectional': 3.0,
            'case_series': 2.0,
            'case_report': 1.0
        },
        'study_type_keywords': {
            'systematic_review': ['systematic review', 'systematic literature review'],
            'meta_analysis': ['meta-analysis', 'meta analysis', 'pooled analysis'],
            'rct': ['randomized controlled trial', 'randomised controlled trial', 'RCT',
                   'randomized trial', 'randomised trial', 'random allocation', 'randomly assigned'],
            'cohort_prospective': ['prospective cohort', 'prospective study', 'longitudinal cohort'],
            'cohort_retrospective': ['retrospective cohort', 'retrospective study'],
            'case_control': ['case-control', 'case control study'],
            'cross_sectional': ['cross-sectional', 'cross sectional study', 'prevalence study'],
            'case_series': ['case series', 'case-series'],
            'case_report': ['case report', 'case study']
        },
        'sample_size_scoring': {
            'log_base': 10,
            'log_multiplier': 2.0,
            'power_calculation_bonus': 2.0,
            'ci_reported_bonus': 0.5
        }
    }

    with patch('bmlibrarian.agents.paper_weight_agent.get_agent_config', return_value=mock_agent_config):
        with patch('bmlibrarian.agents.paper_weight_agent.get_model', return_value='gpt-oss:20b'):
            with patch('bmlibrarian.agents.paper_weight_agent.get_ollama_host', return_value='http://localhost:11434'):
                with patch('bmlibrarian.agents.base.ollama.Client'):
                    yield


@pytest.fixture
def agent(mock_config):
    """Create agent instance for testing."""
    from bmlibrarian.agents.paper_weight_agent import PaperWeightAssessmentAgent
    return PaperWeightAssessmentAgent(show_model_info=False)


class TestStudyTypeExtraction:
    """Tests for study type extraction."""

    def test_extract_study_type_rct(self, agent):
        """Test RCT detection."""
        document = {
            'abstract': 'This randomized controlled trial examined the effect of...'
        }

        result = agent._extract_study_type(document)

        assert result.dimension_name == 'study_design'
        assert result.score == 8.0  # RCT baseline
        assert len(result.details) > 0
        assert result.details[0].extracted_value == 'rct'

    def test_extract_study_type_systematic_review(self, agent):
        """Test systematic review detection."""
        document = {
            'abstract': 'This systematic review analyzed 25 studies on...'
        }

        result = agent._extract_study_type(document)

        assert result.score == 10.0  # Systematic review
        assert result.details[0].extracted_value == 'systematic_review'

    def test_extract_study_type_meta_analysis(self, agent):
        """Test meta-analysis detection."""
        document = {
            'abstract': 'We conducted a meta-analysis of 12 RCTs...'
        }

        result = agent._extract_study_type(document)

        assert result.score == 10.0  # Meta-analysis
        assert result.details[0].extracted_value == 'meta_analysis'

    def test_extract_study_type_priority(self, agent):
        """Test that systematic review takes priority over RCT."""
        document = {
            'abstract': 'This systematic review of randomized controlled trials...'
        }

        result = agent._extract_study_type(document)

        assert result.score == 10.0  # Systematic review, not RCT
        assert result.details[0].extracted_value == 'systematic_review'

    def test_extract_study_type_prospective_cohort(self, agent):
        """Test prospective cohort study detection."""
        document = {
            'abstract': 'This prospective cohort study followed 500 patients...'
        }

        result = agent._extract_study_type(document)

        assert result.score == 6.0  # Prospective cohort
        assert result.details[0].extracted_value == 'cohort_prospective'

    def test_extract_study_type_retrospective_cohort(self, agent):
        """Test retrospective cohort study detection."""
        document = {
            'abstract': 'In this retrospective study, we analyzed medical records...'
        }

        result = agent._extract_study_type(document)

        assert result.score == 5.0  # Retrospective cohort
        assert result.details[0].extracted_value == 'cohort_retrospective'

    def test_extract_study_type_case_control(self, agent):
        """Test case-control study detection."""
        document = {
            'abstract': 'A case-control study was performed to investigate...'
        }

        result = agent._extract_study_type(document)

        assert result.score == 4.0  # Case-control
        assert result.details[0].extracted_value == 'case_control'

    def test_extract_study_type_cross_sectional(self, agent):
        """Test cross-sectional study detection."""
        document = {
            'abstract': 'This cross-sectional study surveyed 1000 adults...'
        }

        result = agent._extract_study_type(document)

        assert result.score == 3.0  # Cross-sectional
        assert result.details[0].extracted_value == 'cross_sectional'

    def test_extract_study_type_case_series(self, agent):
        """Test case series detection."""
        document = {
            'abstract': 'We present a case series of 10 patients with...'
        }

        result = agent._extract_study_type(document)

        assert result.score == 2.0  # Case series
        assert result.details[0].extracted_value == 'case_series'

    def test_extract_study_type_case_report(self, agent):
        """Test case report detection."""
        document = {
            'abstract': 'This case report describes a rare presentation of...'
        }

        result = agent._extract_study_type(document)

        assert result.score == 1.0  # Case report
        assert result.details[0].extracted_value == 'case_report'

    def test_extract_study_type_unknown(self, agent):
        """Test handling of unknown study type."""
        document = {
            'abstract': 'We examined some data and found interesting results.'
        }

        result = agent._extract_study_type(document)

        assert result.details[0].extracted_value == 'unknown'
        assert result.score == 5.0  # Neutral score

    def test_extract_study_type_from_methods(self, agent):
        """Test study type extraction from methods section."""
        document = {
            'abstract': 'This study evaluated treatment outcomes.',
            'methods_text': 'This was a randomized controlled trial with parallel groups.'
        }

        result = agent._extract_study_type(document)

        assert result.score == 8.0  # RCT
        assert result.details[0].extracted_value == 'rct'

    def test_extract_study_type_case_insensitive(self, agent):
        """Test case-insensitive keyword matching."""
        document = {
            'abstract': 'This RANDOMIZED CONTROLLED TRIAL examined...'
        }

        result = agent._extract_study_type(document)

        assert result.score == 8.0  # RCT
        assert result.details[0].extracted_value == 'rct'

    def test_extract_study_type_with_evidence(self, agent):
        """Test that evidence context is extracted."""
        document = {
            'abstract': 'Background: Cardiovascular disease is common. Methods: This randomized controlled trial enrolled patients from 3 centers.'
        }

        result = agent._extract_study_type(document)

        assert result.details[0].evidence_text is not None
        assert 'randomized controlled trial' in result.details[0].evidence_text


class TestSampleSizeExtraction:
    """Tests for sample size extraction."""

    def test_extract_sample_size_basic(self, agent):
        """Test basic sample size extraction."""
        document = {
            'abstract': 'We enrolled n=450 participants in this study.'
        }

        result = agent._extract_sample_size(document)

        assert result.dimension_name == 'sample_size'
        assert result.details[0].extracted_value == '450'
        # log10(450) * 2 ≈ 5.3
        assert 5.0 <= result.score <= 6.0

    def test_extract_sample_size_uppercase_n(self, agent):
        """Test sample size extraction with uppercase N."""
        document = {
            'abstract': 'The total sample size was N=1000 patients.'
        }

        result = agent._extract_sample_size(document)

        assert result.details[0].extracted_value == '1000'
        # log10(1000) * 2 = 6.0
        assert result.score == pytest.approx(6.0, abs=0.1)

    def test_extract_sample_size_participants(self, agent):
        """Test sample size extraction with 'participants' keyword."""
        document = {
            'abstract': 'A total of 250 participants completed the study.'
        }

        result = agent._extract_sample_size(document)

        assert result.details[0].extracted_value == '250'

    def test_extract_sample_size_patients(self, agent):
        """Test sample size extraction with 'patients' keyword."""
        document = {
            'abstract': 'We recruited 500 patients from local clinics.'
        }

        result = agent._extract_sample_size(document)

        assert result.details[0].extracted_value == '500'

    def test_extract_sample_size_subjects(self, agent):
        """Test sample size extraction with 'subjects' keyword."""
        document = {
            'abstract': 'The study included 300 subjects aged 18-65.'
        }

        result = agent._extract_sample_size(document)

        assert result.details[0].extracted_value == '300'

    def test_extract_sample_size_with_power_calc(self, agent):
        """Test sample size extraction with power calculation bonus."""
        document = {
            'abstract': 'Sample size was calculated using power analysis. We enrolled n=450 participants.'
        }

        result = agent._extract_sample_size(document)

        # Base score + power calculation bonus (2.0)
        assert result.score > 7.0  # Should be ~7.3
        assert any(d.component == 'power_calculation' for d in result.details)

    def test_extract_sample_size_with_ci(self, agent):
        """Test sample size extraction with CI reporting bonus."""
        document = {
            'abstract': 'We enrolled n=450 participants. The mean difference was 2.5 (95% CI: 1.2-3.8).'
        }

        result = agent._extract_sample_size(document)

        # Base score + CI bonus (0.5)
        assert result.score > 5.3  # Base is ~5.3, should have CI bonus
        assert any(d.component == 'ci_reporting' for d in result.details)

    def test_extract_sample_size_with_both_bonuses(self, agent):
        """Test sample size extraction with both bonuses."""
        document = {
            'abstract': 'Power analysis determined that n=450 participants were needed. '
                       'Results showed significant improvement (95% CI: 1.2-3.8).'
        }

        result = agent._extract_sample_size(document)

        # Base (~5.3) + power (2.0) + CI (0.5) = ~7.8
        assert result.score > 7.5
        assert any(d.component == 'power_calculation' for d in result.details)
        assert any(d.component == 'ci_reporting' for d in result.details)

    def test_extract_sample_size_not_found(self, agent):
        """Test handling when sample size not found."""
        document = {
            'abstract': 'We studied many participants.'
        }

        result = agent._extract_sample_size(document)

        assert result.score == 0.0
        assert result.details[0].extracted_value == 'not_found'

    def test_extract_sample_size_multiple_mentions(self, agent):
        """Test that largest sample size is selected."""
        document = {
            'abstract': 'We screened 1000 participants and enrolled 450 participants in the final analysis.'
        }

        result = agent._extract_sample_size(document)

        # Should extract 1000, not 450
        assert result.details[0].extracted_value == '1000'

    def test_extract_sample_size_from_methods(self, agent):
        """Test sample size extraction from methods section."""
        document = {
            'abstract': 'This was a clinical trial.',
            'methods_text': 'We enrolled n=750 participants from 5 sites.'
        }

        result = agent._extract_sample_size(document)

        assert result.details[0].extracted_value == '750'


class TestSampleSizeScoring:
    """Tests for logarithmic sample size scoring."""

    def test_calculate_sample_size_score_10(self, agent):
        """Test score for n=10."""
        # log10(10) * 2 = 2.0
        assert agent._calculate_sample_size_score(10) == pytest.approx(2.0, abs=0.1)

    def test_calculate_sample_size_score_100(self, agent):
        """Test score for n=100."""
        # log10(100) * 2 = 4.0
        assert agent._calculate_sample_size_score(100) == pytest.approx(4.0, abs=0.1)

    def test_calculate_sample_size_score_1000(self, agent):
        """Test score for n=1000."""
        # log10(1000) * 2 = 6.0
        assert agent._calculate_sample_size_score(1000) == pytest.approx(6.0, abs=0.1)

    def test_calculate_sample_size_score_10000(self, agent):
        """Test score for n=10000."""
        # log10(10000) * 2 = 8.0
        assert agent._calculate_sample_size_score(10000) == pytest.approx(8.0, abs=0.1)

    def test_calculate_sample_size_score_100000(self, agent):
        """Test score for n=100000."""
        # log10(100000) * 2 = 10.0
        assert agent._calculate_sample_size_score(100000) == pytest.approx(10.0, abs=0.1)

    def test_calculate_sample_size_score_max_capped(self, agent):
        """Test score is capped at 10.0 for very large n."""
        # log10(10000000) * 2 = 14.0 -> capped to 10.0
        assert agent._calculate_sample_size_score(10000000) == 10.0

    def test_calculate_sample_size_score_zero(self, agent):
        """Test score for n=0."""
        assert agent._calculate_sample_size_score(0) == 0.0

    def test_calculate_sample_size_score_negative(self, agent):
        """Test score for negative n."""
        assert agent._calculate_sample_size_score(-100) == 0.0


class TestPowerCalculationDetection:
    """Tests for power calculation detection."""

    def test_has_power_calculation_true(self, agent):
        """Test power calculation detection with various keywords."""
        texts = [
            "Sample size was determined using power calculation to detect...",
            "A power analysis was performed...",
            "The sample size calculation determined that...",
            "We calculated sample size based on statistical power of 80%...",
            "The study had 80% power to detect a 10% difference."
        ]

        for text in texts:
            assert agent._has_power_calculation(text) is True, f"Failed for: {text}"

    def test_has_power_calculation_false(self, agent):
        """Test power calculation detection returns false for non-matching text."""
        text_without_power = "We enrolled participants between 2020 and 2022."
        assert agent._has_power_calculation(text_without_power) is False


class TestCIReportingDetection:
    """Tests for confidence interval detection."""

    def test_has_ci_reporting_keyword(self, agent):
        """Test CI detection with 'confidence interval' keyword."""
        text = "The 95% confidence interval was [1.2, 3.4]"
        assert agent._has_ci_reporting(text) is True

    def test_has_ci_reporting_abbreviation(self, agent):
        """Test CI detection with 'CI' abbreviation."""
        text = "The mean difference was 2.5 (95% CI: 1.2-3.8)"
        assert agent._has_ci_reporting(text) is True

    def test_has_ci_reporting_bracket_format(self, agent):
        """Test CI detection with bracket format."""
        text = "The odds ratio was 1.5 [1.2, 1.8]"
        assert agent._has_ci_reporting(text) is True

    def test_has_ci_reporting_parenthesis_format(self, agent):
        """Test CI detection with parenthesis format."""
        text = "The hazard ratio was 0.75 (0.60-0.90)"
        assert agent._has_ci_reporting(text) is True

    def test_has_ci_reporting_false(self, agent):
        """Test CI detection returns false when no CI present."""
        text = "The mean difference was 2.5"
        assert agent._has_ci_reporting(text) is False


class TestContextExtraction:
    """Tests for context extraction around keywords."""

    def test_extract_context_basic(self, agent):
        """Test basic context extraction."""
        text = "This is some text before the keyword and some text after."
        context = agent._extract_context(text, "keyword", context_chars=10)

        assert "keyword" in context
        assert context.startswith("...")
        assert context.endswith("...")

    def test_extract_context_at_start(self, agent):
        """Test context extraction when keyword at start."""
        text = "keyword is at the beginning of this text."
        context = agent._extract_context(text, "keyword", context_chars=20)

        assert "keyword" in context
        assert not context.startswith("...")  # No ellipsis at start
        assert context.endswith("...")

    def test_extract_context_at_end(self, agent):
        """Test context extraction when keyword at end."""
        text = "This text ends with the keyword"
        context = agent._extract_context(text, "keyword", context_chars=20)

        assert "keyword" in context
        assert context.startswith("...")
        assert not context.endswith("...")  # No ellipsis at end

    def test_extract_context_not_found(self, agent):
        """Test context extraction when keyword not found."""
        text = "This text does not contain the search term."
        context = agent._extract_context(text, "missing", context_chars=20)

        assert context == ""


class TestAgentConfiguration:
    """Tests for agent configuration loading."""

    def test_agent_has_config(self, agent):
        """Test agent has configuration loaded."""
        assert agent.config is not None
        assert 'dimension_weights' in agent.config
        assert 'study_type_hierarchy' in agent.config
        assert 'study_type_keywords' in agent.config
        assert 'sample_size_scoring' in agent.config

    def test_get_dimension_weights(self, agent):
        """Test dimension weights retrieval."""
        weights = agent.get_dimension_weights()

        assert weights['study_design'] == 0.25
        assert weights['sample_size'] == 0.15
        assert weights['methodological_quality'] == 0.30
        assert weights['risk_of_bias'] == 0.20
        assert weights['replication_status'] == 0.10

    def test_dimension_weights_sum_to_one(self, agent):
        """Test dimension weights sum to 1.0."""
        weights = agent.get_dimension_weights()
        total = sum(weights.values())

        assert total == pytest.approx(1.0, abs=0.01)

    def test_agent_version(self, agent):
        """Test agent has version attribute."""
        assert hasattr(agent, 'version')
        assert agent.version == '1.0.0'

    def test_agent_type(self, agent):
        """Test agent type identifier."""
        assert agent.get_agent_type() == "PaperWeightAssessmentAgent"


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_abstract(self, agent):
        """Test handling of empty abstract."""
        document = {'abstract': ''}

        study_result = agent._extract_study_type(document)
        sample_result = agent._extract_sample_size(document)

        assert study_result.details[0].extracted_value == 'unknown'
        assert sample_result.details[0].extracted_value == 'not_found'

    def test_none_abstract(self, agent):
        """Test handling of None abstract."""
        document = {'abstract': None}

        study_result = agent._extract_study_type(document)
        sample_result = agent._extract_sample_size(document)

        assert study_result.details[0].extracted_value == 'unknown'
        assert sample_result.details[0].extracted_value == 'not_found'

    def test_missing_abstract_key(self, agent):
        """Test handling of missing abstract key."""
        document = {}

        study_result = agent._extract_study_type(document)
        sample_result = agent._extract_sample_size(document)

        assert study_result.details[0].extracted_value == 'unknown'
        assert sample_result.details[0].extracted_value == 'not_found'

    def test_very_small_sample_size(self, agent):
        """Test sample sizes below threshold are ignored."""
        document = {
            'abstract': 'We studied n=3 patients in this pilot study.'
        }

        result = agent._extract_sample_size(document)

        # n=3 is below threshold of 5
        assert result.details[0].extracted_value == 'not_found'

    def test_very_large_sample_size(self, agent):
        """Test very large sample sizes are handled correctly."""
        document = {
            'abstract': 'This population study included 500000 participants.'
        }

        result = agent._extract_sample_size(document)

        assert result.details[0].extracted_value == '500000'
        assert result.score == 10.0  # Capped at max (log10(500000)*2 = 11.4 -> capped to 10)


class TestDimensionScoreIntegration:
    """Tests for DimensionScore dataclass integration."""

    def test_study_type_returns_dimension_score(self, agent):
        """Test _extract_study_type returns proper DimensionScore."""
        from bmlibrarian.agents.paper_weight_agent import DimensionScore

        document = {'abstract': 'This was a randomized controlled trial.'}
        result = agent._extract_study_type(document)

        assert isinstance(result, DimensionScore)
        assert result.dimension_name == 'study_design'
        assert 0 <= result.score <= 10

    def test_sample_size_returns_dimension_score(self, agent):
        """Test _extract_sample_size returns proper DimensionScore."""
        from bmlibrarian.agents.paper_weight_agent import DimensionScore

        document = {'abstract': 'We enrolled n=100 participants.'}
        result = agent._extract_sample_size(document)

        assert isinstance(result, DimensionScore)
        assert result.dimension_name == 'sample_size'
        assert 0 <= result.score <= 10

    def test_dimension_score_to_dict(self, agent):
        """Test DimensionScore serialization."""
        document = {'abstract': 'This randomized controlled trial enrolled n=450 participants.'}

        study_result = agent._extract_study_type(document)
        study_dict = study_result.to_dict()

        assert 'dimension_name' in study_dict
        assert 'score' in study_dict
        assert 'details' in study_dict
        assert isinstance(study_dict['details'], list)
