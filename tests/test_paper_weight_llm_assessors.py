"""Tests for LLM-based assessors in PaperWeightAssessmentAgent

This module tests the methodological quality and risk of bias assessors
that use LLM analysis for nuanced paper evaluation.

Tests are organized into:
1. Unit tests (fast, no external dependencies)
2. Integration tests (require Ollama, marked with pytest.mark.slow)
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock

from bmlibrarian.agents.paper_weight_agent import (
    PaperWeightAssessmentAgent,
    DimensionScore,
    AssessmentDetail
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def agent():
    """Create agent instance for testing (without connecting to Ollama)."""
    with patch.object(PaperWeightAssessmentAgent, 'test_connection', return_value=True):
        agent = PaperWeightAssessmentAgent(show_model_info=False)
    return agent


@pytest.fixture
def sample_rct_document():
    """Sample RCT document for testing."""
    return {
        'title': 'Effect of Exercise on Cardiovascular Health: A Randomized Controlled Trial',
        'abstract': '''This double-blind randomized controlled trial examined
        the effect of exercise on cardiovascular outcomes. Participants were
        randomly assigned using computer-generated random numbers to either
        exercise or control groups. Allocation was concealed using sealed
        envelopes. The study was registered at ClinicalTrials.gov (NCT12345678)
        before enrollment. We enrolled 450 participants and followed them for
        12 months. Outcome assessors were blinded to group assignment.
        Analysis was conducted using intention-to-treat principles.
        The dropout rate was 5%. Missing data were handled using multiple
        imputation. Confidence intervals are reported for all primary outcomes.''',
        'full_text': ''
    }


@pytest.fixture
def sample_observational_document():
    """Sample observational study document for testing."""
    return {
        'title': 'Association Between Diet and Cancer Risk: A Cohort Study',
        'abstract': '''This retrospective cohort study examined the association
        between dietary patterns and cancer risk. We reviewed medical records
        of 1200 patients treated at our center between 2010 and 2020.
        Inclusion criteria were age > 18 and complete dietary records.
        No blinding was performed. Statistical analysis used Cox proportional
        hazards models with 95% confidence intervals reported.''',
        'full_text': ''
    }


@pytest.fixture
def sample_study_assessment():
    """Sample StudyAssessmentAgent output for integration testing."""
    return {
        'study_type': 'Randomized Controlled Trial',
        'study_design': 'Prospective, double-blinded, multi-center',
        'quality_score': 8.5,
        'is_prospective': True,
        'is_retrospective': False,
        'is_randomized': True,
        'is_controlled': True,
        'is_blinded': True,
        'is_double_blinded': True,
        'is_multi_center': True,
        'selection_bias_risk': 'low',
        'performance_bias_risk': 'low',
        'detection_bias_risk': 'moderate',
        'attrition_bias_risk': 'low',
        'reporting_bias_risk': 'low'
    }


# ============================================================================
# Unit Tests - Text Preparation
# ============================================================================

class TestTextPreparation:
    """Tests for _prepare_text_for_analysis helper method."""

    def test_prepare_text_with_abstract_only(self, agent):
        """Test text preparation when only abstract is available."""
        document = {
            'title': 'Test Study',
            'abstract': 'This is a test abstract about cardiovascular research.',
            'full_text': ''
        }

        text = agent._prepare_text_for_analysis(document)

        assert 'TITLE: Test Study' in text
        assert 'ABSTRACT:' in text
        assert 'cardiovascular research' in text
        assert 'FULL TEXT:' not in text

    def test_prepare_text_with_full_text(self, agent):
        """Test text preparation when full text is available."""
        document = {
            'title': 'Test Study',
            'abstract': 'Short abstract.',
            'full_text': 'This is the full text of the paper with much more detail.'
        }

        text = agent._prepare_text_for_analysis(document)

        assert 'TITLE: Test Study' in text
        assert 'FULL TEXT:' in text
        assert 'much more detail' in text
        assert 'Short abstract' not in text  # Full text takes precedence

    def test_prepare_text_truncates_long_text(self, agent):
        """Test that long text is truncated to MAX_TEXT_LENGTH."""
        long_abstract = 'A' * 10000  # Longer than MAX_TEXT_LENGTH
        document = {
            'title': 'Test',
            'abstract': long_abstract,
            'full_text': ''
        }

        text = agent._prepare_text_for_analysis(document)

        assert len(text) <= agent.MAX_TEXT_LENGTH + 50  # Allow for truncation message
        assert '[Text truncated...]' in text

    def test_prepare_text_handles_none_values(self, agent):
        """Test handling of None values in document fields."""
        document = {
            'title': None,
            'abstract': None,
            'full_text': None
        }

        text = agent._prepare_text_for_analysis(document)

        assert 'TITLE:' in text
        assert 'ABSTRACT:' in text


# ============================================================================
# Unit Tests - Prompt Building
# ============================================================================

class TestPromptBuilding:
    """Tests for prompt building methods."""

    def test_build_methodological_quality_prompt(self, agent, sample_rct_document):
        """Test prompt building for methodological quality."""
        text = agent._prepare_text_for_analysis(sample_rct_document)
        prompt = agent._build_methodological_quality_prompt(text)

        # Check required elements in prompt
        assert 'RANDOMIZATION' in prompt
        assert 'BLINDING' in prompt
        assert 'ALLOCATION CONCEALMENT' in prompt
        assert 'PROTOCOL PREREGISTRATION' in prompt
        assert 'ITT ANALYSIS' in prompt
        assert 'ATTRITION HANDLING' in prompt
        assert 'JSON' in prompt
        assert 'cardiovascular' in prompt.lower()  # Document content included

    def test_build_risk_of_bias_prompt(self, agent, sample_rct_document):
        """Test prompt building for risk of bias."""
        text = agent._prepare_text_for_analysis(sample_rct_document)
        prompt = agent._build_risk_of_bias_prompt(text)

        # Check required elements in prompt
        assert 'SELECTION BIAS' in prompt
        assert 'PERFORMANCE BIAS' in prompt
        assert 'DETECTION BIAS' in prompt
        assert 'REPORTING BIAS' in prompt
        assert 'INVERTED SCALE' in prompt
        assert 'JSON' in prompt


# ============================================================================
# Unit Tests - Score Calculation
# ============================================================================

class TestScoreCalculation:
    """Tests for score calculation methods."""

    def test_calculate_methodological_quality_score_perfect(self, agent):
        """Test score calculation with perfect component scores."""
        components = {
            "randomization": {"score": 2.0, "evidence": "computer-generated", "reasoning": "Proper method"},
            "blinding": {"score": 3.0, "evidence": "triple-blind", "reasoning": "Excellent"},
            "allocation_concealment": {"score": 1.5, "evidence": "sealed envelopes", "reasoning": "Proper"},
            "protocol_preregistration": {"score": 1.5, "evidence": "NCT12345", "reasoning": "Registered"},
            "itt_analysis": {"score": 1.0, "evidence": "ITT analysis", "reasoning": "Proper"},
            "attrition_handling": {"score": 1.0, "evidence": "5% dropout", "reasoning": "Low attrition"}
        }

        result = agent._calculate_methodological_quality_score(components)

        assert result.dimension_name == 'methodological_quality'
        assert result.score == 10.0  # Perfect score
        assert len(result.details) == 6

    def test_calculate_methodological_quality_score_partial(self, agent):
        """Test score calculation with partial scores."""
        components = {
            "randomization": {"score": 1.0, "evidence": "mentioned", "reasoning": "Unclear"},
            "blinding": {"score": 0.0, "evidence": "none", "reasoning": "Not blinded"},
            "allocation_concealment": {"score": 0.0, "evidence": "", "reasoning": "Not mentioned"},
            "protocol_preregistration": {"score": 0.0, "evidence": "", "reasoning": "Not registered"},
            "itt_analysis": {"score": 0.5, "evidence": "modified ITT", "reasoning": "Partial"},
            "attrition_handling": {"score": 0.5, "evidence": "10% dropout", "reasoning": "Moderate"}
        }

        result = agent._calculate_methodological_quality_score(components)

        assert result.dimension_name == 'methodological_quality'
        assert result.score == 2.0  # 1.0 + 0 + 0 + 0 + 0.5 + 0.5
        assert len(result.details) == 6

    def test_calculate_methodological_quality_score_with_attrition_rate(self, agent):
        """Test that attrition rate is included in value string."""
        components = {
            "attrition_handling": {
                "score": 0.8,
                "attrition_rate": 0.05,
                "evidence": "5% dropout",
                "reasoning": "Low attrition"
            }
        }

        result = agent._calculate_methodological_quality_score(components)

        assert len(result.details) == 1
        assert 'attrition rate: 0.05' in result.details[0].extracted_value

    def test_calculate_risk_of_bias_score_low_risk(self, agent):
        """Test risk of bias score calculation with low risk."""
        components = {
            "selection_bias": {"score": 2.5, "risk_level": "low", "evidence": "random", "reasoning": "Good"},
            "performance_bias": {"score": 2.5, "risk_level": "low", "evidence": "blinded", "reasoning": "Good"},
            "detection_bias": {"score": 2.5, "risk_level": "low", "evidence": "blinded", "reasoning": "Good"},
            "reporting_bias": {"score": 2.5, "risk_level": "low", "evidence": "protocol", "reasoning": "Good"}
        }

        result = agent._calculate_risk_of_bias_score(components)

        assert result.dimension_name == 'risk_of_bias'
        assert result.score == 10.0  # Perfect score (low risk)
        assert len(result.details) == 4

    def test_calculate_risk_of_bias_score_high_risk(self, agent):
        """Test risk of bias score calculation with high risk."""
        components = {
            "selection_bias": {"score": 0, "risk_level": "high", "evidence": "convenience", "reasoning": "Poor"},
            "performance_bias": {"score": 0, "risk_level": "high", "evidence": "unblinded", "reasoning": "Poor"},
            "detection_bias": {"score": 0, "risk_level": "high", "evidence": "unblinded", "reasoning": "Poor"},
            "reporting_bias": {"score": 0, "risk_level": "high", "evidence": "selective", "reasoning": "Poor"}
        }

        result = agent._calculate_risk_of_bias_score(components)

        assert result.score == 0.0  # Zero score (high risk)
        assert all('high risk' in d.extracted_value for d in result.details)

    def test_calculate_score_handles_non_dict_components(self, agent):
        """Test that non-dict components are skipped."""
        components = {
            "randomization": {"score": 2.0, "evidence": "test", "reasoning": "test"},
            "invalid_component": "not a dict",  # Should be skipped
            "another_invalid": 123  # Should be skipped
        }

        result = agent._calculate_methodological_quality_score(components)

        assert len(result.details) == 1
        assert result.score == 2.0


# ============================================================================
# Unit Tests - StudyAssessmentAgent Integration
# ============================================================================

class TestStudyAssessmentIntegration:
    """Tests for StudyAssessmentAgent integration helpers."""

    def test_extract_mq_from_study_assessment_high_quality(self, agent, sample_study_assessment):
        """Test MQ extraction from high-quality RCT assessment."""
        document = {'title': 'Test'}

        result = agent._extract_mq_from_study_assessment(sample_study_assessment, document)

        assert result is not None
        assert result.dimension_name == 'methodological_quality'
        assert result.score > 5.0  # High quality RCT should score well
        assert len(result.details) >= 3  # At least randomization, blinding, other_components

        # Check specific components
        component_names = [d.component for d in result.details]
        assert 'randomization' in component_names
        assert 'blinding' in component_names

    def test_extract_mq_from_study_assessment_no_randomization(self, agent):
        """Test MQ extraction when study is not randomized."""
        study_assessment = {
            'is_randomized': False,
            'is_blinded': False,
            'is_double_blinded': False,
            'quality_score': 4.0
        }
        document = {'title': 'Test'}

        result = agent._extract_mq_from_study_assessment(study_assessment, document)

        assert result is not None
        # Score should be lower due to no randomization or blinding
        randomization_detail = next(d for d in result.details if d.component == 'randomization')
        assert randomization_detail.score_contribution == 0.0

    def test_extract_rob_from_study_assessment(self, agent, sample_study_assessment):
        """Test RoB extraction from StudyAssessmentAgent output."""
        document = {'title': 'Test'}

        result = agent._extract_rob_from_study_assessment(sample_study_assessment, document)

        assert result is not None
        assert result.dimension_name == 'risk_of_bias'
        assert len(result.details) == 4  # 4 bias types

        # Check that low risk gives high scores
        for detail in result.details:
            if 'low' in detail.extracted_value:
                assert detail.score_contribution == 2.5

    def test_extract_rob_from_study_assessment_high_risk(self, agent):
        """Test RoB extraction with high risk bias ratings."""
        study_assessment = {
            'selection_bias_risk': 'high',
            'performance_bias_risk': 'high',
            'detection_bias_risk': 'high',
            'reporting_bias_risk': 'high'
        }
        document = {'title': 'Test'}

        result = agent._extract_rob_from_study_assessment(study_assessment, document)

        assert result is not None
        assert result.score == 0.0  # All high risk = 0

    def test_extract_mq_handles_invalid_input(self, agent):
        """Test that MQ extraction returns None on invalid input."""
        result = agent._extract_mq_from_study_assessment(None, {})

        # Should either handle gracefully or return None
        # The implementation catches exceptions and returns None
        assert result is None or isinstance(result, DimensionScore)


# ============================================================================
# Unit Tests - Error Handling
# ============================================================================

class TestErrorHandling:
    """Tests for error handling in LLM assessors."""

    def test_assess_mq_returns_degraded_score_on_error(self, agent, sample_rct_document):
        """Test that methodological quality assessment returns neutral score on error."""
        with patch.object(agent, '_generate_and_parse_json', side_effect=Exception("LLM error")):
            result = agent._assess_methodological_quality(sample_rct_document)

        assert result.dimension_name == 'methodological_quality'
        assert result.score == 5.0  # Neutral degraded score
        assert len(result.details) == 1
        assert result.details[0].component == 'error'
        assert 'LLM error' in result.details[0].reasoning

    def test_assess_rob_returns_degraded_score_on_error(self, agent, sample_rct_document):
        """Test that risk of bias assessment returns neutral score on error."""
        with patch.object(agent, '_generate_and_parse_json', side_effect=Exception("LLM error")):
            result = agent._assess_risk_of_bias(sample_rct_document)

        assert result.dimension_name == 'risk_of_bias'
        assert result.score == 5.0  # Neutral degraded score
        assert result.details[0].component == 'error'


# ============================================================================
# Unit Tests - JSON Response Parsing
# ============================================================================

class TestJsonParsing:
    """Tests for JSON response parsing from LLM."""

    def test_parse_methodological_quality_response_with_markdown(self, agent):
        """Test JSON parsing from markdown code block response."""
        response_with_markdown = '''```json
        {
          "randomization": {"score": 2.0, "evidence": "computer-generated", "reasoning": "Proper method"},
          "blinding": {"score": 2.0, "evidence": "double-blind", "reasoning": "Participants and assessors"}
        }
        ```'''

        # Use the base agent's _parse_json_response method
        result = agent._parse_json_response(response_with_markdown)

        assert result['randomization']['score'] == 2.0
        assert result['blinding']['score'] == 2.0

    def test_parse_methodological_quality_response_bare_json(self, agent):
        """Test JSON parsing from bare JSON response."""
        response_bare = '''{
          "randomization": {"score": 2.0, "evidence": "test", "reasoning": "test"}
        }'''

        result = agent._parse_json_response(response_bare)

        assert result['randomization']['score'] == 2.0


# ============================================================================
# Unit Tests - Edge Cases
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_components_dict(self, agent):
        """Test score calculation with empty components dict."""
        result = agent._calculate_methodological_quality_score({})

        assert result.dimension_name == 'methodological_quality'
        assert result.score == 0.0
        assert len(result.details) == 0

    def test_components_missing_score_key(self, agent):
        """Test handling of components missing score key."""
        components = {
            "randomization": {"evidence": "test", "reasoning": "test"},  # No score
            "blinding": {"score": 2.0, "evidence": "test", "reasoning": "test"}
        }

        result = agent._calculate_methodological_quality_score(components)

        # Should use default score of 0.0 for missing score
        assert result.score == 2.0  # Only blinding contributes

    def test_components_with_negative_score(self, agent):
        """Test handling of negative score values."""
        components = {
            "randomization": {"score": -1.0, "evidence": "test", "reasoning": "test"}
        }

        result = agent._calculate_methodological_quality_score(components)

        # Negative scores should still be used (clamping happens at final score)
        assert result.details[0].score_contribution == -1.0

    def test_score_capped_at_10(self, agent):
        """Test that total score is capped at 10.0."""
        components = {
            "randomization": {"score": 5.0, "evidence": "test", "reasoning": "test"},
            "blinding": {"score": 5.0, "evidence": "test", "reasoning": "test"},
            "allocation": {"score": 5.0, "evidence": "test", "reasoning": "test"}
        }

        result = agent._calculate_methodological_quality_score(components)

        assert result.score == 10.0  # Capped at 10

    def test_empty_document(self, agent):
        """Test text preparation with empty document."""
        document = {}

        text = agent._prepare_text_for_analysis(document)

        assert 'TITLE:' in text
        assert 'ABSTRACT:' in text

    def test_extract_mq_with_none_quality_score(self, agent):
        """Test MQ extraction when quality_score is None."""
        study_assessment = {
            'is_randomized': True,
            'is_double_blinded': True,
            'quality_score': None  # Explicit None
        }
        document = {'title': 'Test'}

        result = agent._extract_mq_from_study_assessment(study_assessment, document)

        assert result is not None
        # Should use default of 5.0 for None quality_score
        other_component = next(d for d in result.details if d.component == 'other_components')
        assert 'quality_score=5.0' in other_component.extracted_value

    def test_extract_mq_with_extreme_quality_score(self, agent):
        """Test MQ extraction with extreme quality_score values."""
        # Test with quality_score > 10
        study_assessment = {
            'is_randomized': False,
            'quality_score': 15.0  # Out of range
        }
        document = {'title': 'Test'}

        result = agent._extract_mq_from_study_assessment(study_assessment, document)

        # Should clamp to 10.0
        assert result.score <= 10.0

    def test_extract_rob_with_unknown_risk_level(self, agent):
        """Test RoB extraction with unknown risk levels."""
        study_assessment = {
            'selection_bias_risk': 'unknown',
            'performance_bias_risk': 'very_high',  # Not in mapping
            'detection_bias_risk': 'low',
            'reporting_bias_risk': None
        }
        document = {'title': 'Test'}

        result = agent._extract_rob_from_study_assessment(study_assessment, document)

        assert result is not None
        # Unknown risk levels should get default score (0.625)

    def test_components_with_string_score(self, agent):
        """Test handling of string score values (should convert to float)."""
        components = {
            "randomization": {"score": "2.0", "evidence": "test", "reasoning": "test"}
        }

        result = agent._calculate_methodological_quality_score(components)

        assert result.score == 2.0  # String converted to float

    def test_risk_of_bias_with_mixed_risk_levels(self, agent):
        """Test RoB calculation with mixed risk levels."""
        components = {
            "selection_bias": {"score": 2.5, "risk_level": "low", "evidence": "", "reasoning": ""},
            "performance_bias": {"score": 0, "risk_level": "high", "evidence": "", "reasoning": ""},
            "detection_bias": {"score": 1.25, "risk_level": "moderate", "evidence": "", "reasoning": ""}
        }

        result = agent._calculate_risk_of_bias_score(components)

        assert result.score == 3.75  # 2.5 + 0 + 1.25


# ============================================================================
# Integration Tests (require Ollama)
# ============================================================================

@pytest.mark.slow
@pytest.mark.requires_ollama
class TestLLMIntegration:
    """Integration tests that require a running Ollama instance."""

    @pytest.fixture
    def live_agent(self):
        """Create agent that connects to real Ollama instance."""
        return PaperWeightAssessmentAgent(show_model_info=False)

    def test_assess_methodological_quality_integration(self, live_agent, sample_rct_document):
        """Integration test for methodological quality assessment."""
        if not live_agent.test_connection():
            pytest.skip("Ollama not available")

        result = live_agent._assess_methodological_quality(sample_rct_document)

        assert result.dimension_name == 'methodological_quality'
        assert 0 <= result.score <= 10
        assert len(result.details) > 0

        # High quality RCT should score well
        assert result.score > 5.0, f"Expected score > 5.0 for RCT, got {result.score}"

    def test_assess_risk_of_bias_integration(self, live_agent, sample_rct_document):
        """Integration test for risk of bias assessment."""
        if not live_agent.test_connection():
            pytest.skip("Ollama not available")

        result = live_agent._assess_risk_of_bias(sample_rct_document)

        assert result.dimension_name == 'risk_of_bias'
        assert 0 <= result.score <= 10
        assert len(result.details) > 0

        # Low risk RCT should have high score (inverted scale)
        assert result.score > 5.0, f"Expected score > 5.0 for RCT (low risk), got {result.score}"

    def test_assess_observational_study(self, live_agent, sample_observational_document):
        """Test assessment of observational study (should score lower than RCT)."""
        if not live_agent.test_connection():
            pytest.skip("Ollama not available")

        mq_result = live_agent._assess_methodological_quality(sample_observational_document)
        rob_result = live_agent._assess_risk_of_bias(sample_observational_document)

        # Observational study should score lower than RCT
        assert mq_result.score < 8.0, "Observational study shouldn't score as high as RCT"
        # Retrospective study typically has higher bias risk (lower score)
        assert rob_result.score < 8.0, "Retrospective study should have some bias risk"

    def test_uses_study_assessment_when_provided(self, live_agent, sample_rct_document, sample_study_assessment):
        """Test that StudyAssessmentAgent output is used when provided."""
        # When study_assessment is provided, should use extraction instead of LLM
        mq_result = live_agent._assess_methodological_quality(
            sample_rct_document,
            study_assessment=sample_study_assessment
        )
        rob_result = live_agent._assess_risk_of_bias(
            sample_rct_document,
            study_assessment=sample_study_assessment
        )

        # Results should come from extraction (check reasoning mentions StudyAssessmentAgent)
        assert any('StudyAssessmentAgent' in d.reasoning for d in mq_result.details if d.reasoning)
        assert any('StudyAssessmentAgent' in d.reasoning for d in rob_result.details if d.reasoning)


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == '__main__':
    # Run unit tests only (fast)
    # pytest tests/test_paper_weight_llm_assessors.py -v -m "not slow"

    # Run all tests including integration tests (requires Ollama)
    # pytest tests/test_paper_weight_llm_assessors.py -v

    pytest.main([__file__, '-v', '-m', 'not slow'])
