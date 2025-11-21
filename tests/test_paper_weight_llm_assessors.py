"""
Tests for paper_weight_llm_assessors.py

Tests cover:
- Text preparation for LLM analysis
- Methodological quality score calculation
- Risk of bias score calculation
- StudyAssessmentAgent integration functions
- Error handling and edge cases
"""

import pytest

from bmlibrarian.agents.paper_weight_llm_assessors import (
    DEFAULT_MAX_TEXT_LENGTH,
    RISK_LEVEL_SCORES,
    RANDOMIZATION_SCORE,
    DOUBLE_BLIND_SCORE,
    SINGLE_BLIND_SCORE,
    REMAINING_COMPONENTS_MAX,
    QUALITY_SCORE_MAX,
    prepare_text_for_analysis,
    calculate_methodological_quality_score,
    calculate_risk_of_bias_score,
    extract_mq_from_study_assessment,
    extract_rob_from_study_assessment,
    create_error_dimension_score,
)
from bmlibrarian.agents.paper_weight_models import (
    DIMENSION_METHODOLOGICAL_QUALITY,
    DIMENSION_RISK_OF_BIAS,
)


class TestPrepareTextForAnalysis:
    """Tests for prepare_text_for_analysis function."""

    def test_basic_preparation_with_abstract(self):
        """Test basic text preparation with abstract only."""
        document = {
            'title': 'Test Study',
            'abstract': 'This is the abstract text.',
            'full_text': None
        }
        result = prepare_text_for_analysis(document)
        
        assert 'TITLE: Test Study' in result
        assert 'ABSTRACT:' in result
        assert 'This is the abstract text.' in result

    def test_prefers_full_text(self):
        """Test that full_text is preferred over abstract."""
        document = {
            'title': 'Test Study',
            'abstract': 'Short abstract.',
            'full_text': 'This is the full text of the paper.'
        }
        result = prepare_text_for_analysis(document)
        
        assert 'FULL TEXT:' in result
        assert 'full text of the paper' in result
        assert 'ABSTRACT:' not in result

    def test_truncation(self):
        """Test text truncation at max_length."""
        document = {
            'title': 'Test',
            'abstract': 'A' * 10000,  # Very long abstract
            'full_text': None
        }
        result = prepare_text_for_analysis(document, max_length=100)
        
        assert len(result) <= 130  # Some buffer for truncation message
        assert '[Text truncated...]' in result

    def test_empty_document(self):
        """Test with empty document fields."""
        document = {
            'title': '',
            'abstract': '',
            'full_text': ''
        }
        result = prepare_text_for_analysis(document)
        
        assert 'TITLE: ' in result
        assert 'ABSTRACT:' in result

    def test_none_values(self):
        """Test with None values."""
        document = {
            'title': None,
            'abstract': None,
            'full_text': None
        }
        result = prepare_text_for_analysis(document)
        
        assert 'TITLE: ' in result


class TestCalculateMethodologicalQualityScore:
    """Tests for calculate_methodological_quality_score function."""

    def test_full_score_components(self):
        """Test with all components present."""
        components = {
            'randomization': {'score': 2.0, 'evidence': 'random', 'reasoning': 'good'},
            'blinding': {'score': 3.0, 'evidence': 'triple', 'reasoning': 'excellent'},
            'allocation_concealment': {'score': 1.5, 'evidence': 'sealed', 'reasoning': 'ok'},
            'protocol_preregistration': {'score': 1.5, 'evidence': 'yes', 'reasoning': 'ok'},
            'itt_analysis': {'score': 1.0, 'evidence': 'ITT', 'reasoning': 'ok'},
            'attrition_handling': {'score': 1.0, 'attrition_rate': 0.05, 'evidence': 'low', 'reasoning': 'ok'}
        }
        result = calculate_methodological_quality_score(components)
        
        assert result.dimension_name == DIMENSION_METHODOLOGICAL_QUALITY
        assert result.score == 10.0  # Capped at 10
        assert len(result.details) == 6

    def test_partial_components(self):
        """Test with partial components."""
        components = {
            'randomization': {'score': 2.0, 'evidence': '', 'reasoning': ''},
            'blinding': {'score': 1.0, 'evidence': '', 'reasoning': ''}
        }
        result = calculate_methodological_quality_score(components)
        
        assert result.score == 3.0
        assert len(result.details) == 2

    def test_empty_components(self):
        """Test with empty components dict."""
        result = calculate_methodological_quality_score({})
        
        assert result.score == 0.0
        assert len(result.details) == 0

    def test_attrition_rate_in_value(self):
        """Test that attrition rate appears in value field."""
        components = {
            'attrition_handling': {'score': 0.5, 'attrition_rate': 0.15, 'evidence': '', 'reasoning': ''}
        }
        result = calculate_methodological_quality_score(components)
        
        assert 'attrition rate: 0.15' in result.details[0].extracted_value

    def test_non_dict_components_skipped(self):
        """Test that non-dict component values are skipped."""
        components = {
            'randomization': {'score': 2.0, 'evidence': '', 'reasoning': ''},
            'invalid': 'not a dict',
            'also_invalid': 123
        }
        result = calculate_methodological_quality_score(components)
        
        assert result.score == 2.0
        assert len(result.details) == 1


class TestCalculateRiskOfBiasScore:
    """Tests for calculate_risk_of_bias_score function."""

    def test_low_risk_all_domains(self):
        """Test with low risk in all domains."""
        components = {
            'selection_bias': {'score': 2.5, 'risk_level': 'low', 'evidence': '', 'reasoning': ''},
            'performance_bias': {'score': 2.5, 'risk_level': 'low', 'evidence': '', 'reasoning': ''},
            'detection_bias': {'score': 2.5, 'risk_level': 'low', 'evidence': '', 'reasoning': ''},
            'reporting_bias': {'score': 2.5, 'risk_level': 'low', 'evidence': '', 'reasoning': ''}
        }
        result = calculate_risk_of_bias_score(components)
        
        assert result.dimension_name == DIMENSION_RISK_OF_BIAS
        assert result.score == 10.0
        assert len(result.details) == 4

    def test_high_risk_components(self):
        """Test with high risk components."""
        components = {
            'selection_bias': {'score': 0.0, 'risk_level': 'high', 'evidence': '', 'reasoning': ''},
            'performance_bias': {'score': 0.0, 'risk_level': 'high', 'evidence': '', 'reasoning': ''}
        }
        result = calculate_risk_of_bias_score(components)
        
        assert result.score == 0.0

    def test_risk_level_in_value(self):
        """Test that risk level appears in value field."""
        components = {
            'selection_bias': {'score': 1.25, 'risk_level': 'moderate', 'evidence': '', 'reasoning': ''}
        }
        result = calculate_risk_of_bias_score(components)
        
        assert 'moderate risk' in result.details[0].extracted_value

    def test_score_capped_at_10(self):
        """Test that score is capped at 10."""
        components = {
            'selection_bias': {'score': 5.0, 'risk_level': 'low', 'evidence': '', 'reasoning': ''},
            'performance_bias': {'score': 5.0, 'risk_level': 'low', 'evidence': '', 'reasoning': ''},
            'detection_bias': {'score': 5.0, 'risk_level': 'low', 'evidence': '', 'reasoning': ''}
        }
        result = calculate_risk_of_bias_score(components)
        
        assert result.score == 10.0


class TestExtractMQFromStudyAssessment:
    """Tests for extract_mq_from_study_assessment function."""

    def test_randomized_double_blind(self):
        """Test extraction with randomized and double-blind study."""
        study_assessment = {
            'is_randomized': True,
            'is_double_blinded': True,
            'is_blinded': True,
            'quality_score': 8.0
        }
        result = extract_mq_from_study_assessment(study_assessment)
        
        assert result is not None
        assert result.dimension_name == DIMENSION_METHODOLOGICAL_QUALITY
        # 2.0 (random) + 2.0 (double-blind) + 4.0 (quality estimate) = 8.0
        expected_score = RANDOMIZATION_SCORE + DOUBLE_BLIND_SCORE + (8.0 / QUALITY_SCORE_MAX * REMAINING_COMPONENTS_MAX)
        assert abs(result.score - expected_score) < 0.1

    def test_randomized_single_blind(self):
        """Test extraction with randomized and single-blind study."""
        study_assessment = {
            'is_randomized': True,
            'is_double_blinded': False,
            'is_blinded': True,
            'quality_score': 6.0
        }
        result = extract_mq_from_study_assessment(study_assessment)
        
        assert result is not None
        # 2.0 (random) + 1.0 (single-blind) + 3.0 (quality estimate) = 6.0
        expected_score = RANDOMIZATION_SCORE + SINGLE_BLIND_SCORE + (6.0 / QUALITY_SCORE_MAX * REMAINING_COMPONENTS_MAX)
        assert abs(result.score - expected_score) < 0.1

    def test_not_randomized_not_blinded(self):
        """Test extraction with non-randomized, non-blinded study."""
        study_assessment = {
            'is_randomized': False,
            'is_double_blinded': False,
            'is_blinded': False,
            'quality_score': 5.0
        }
        result = extract_mq_from_study_assessment(study_assessment)
        
        assert result is not None
        # 0 + 0 + 2.5 (quality estimate) = 2.5
        expected_score = 0 + 0 + (5.0 / QUALITY_SCORE_MAX * REMAINING_COMPONENTS_MAX)
        assert abs(result.score - expected_score) < 0.1

    def test_missing_fields_use_defaults(self):
        """Test that missing fields use default values."""
        study_assessment = {}
        result = extract_mq_from_study_assessment(study_assessment)
        
        assert result is not None
        # Should use defaults: not randomized, not blinded, quality_score=5.0

    def test_none_quality_score(self):
        """Test handling of None quality_score."""
        study_assessment = {
            'is_randomized': True,
            'quality_score': None
        }
        result = extract_mq_from_study_assessment(study_assessment)
        
        assert result is not None


class TestExtractROBFromStudyAssessment:
    """Tests for extract_rob_from_study_assessment function."""

    def test_all_low_risk(self):
        """Test extraction with all low risk domains."""
        study_assessment = {
            'selection_bias_risk': 'low',
            'performance_bias_risk': 'low',
            'detection_bias_risk': 'low',
            'reporting_bias_risk': 'low'
        }
        result = extract_rob_from_study_assessment(study_assessment)
        
        assert result is not None
        assert result.dimension_name == DIMENSION_RISK_OF_BIAS
        # 4 * 2.5 = 10.0
        assert result.score == 10.0

    def test_all_high_risk(self):
        """Test extraction with all high risk domains."""
        study_assessment = {
            'selection_bias_risk': 'high',
            'performance_bias_risk': 'high',
            'detection_bias_risk': 'high',
            'reporting_bias_risk': 'high'
        }
        result = extract_rob_from_study_assessment(study_assessment)
        
        assert result is not None
        assert result.score == 0.0

    def test_mixed_risk_levels(self):
        """Test extraction with mixed risk levels."""
        study_assessment = {
            'selection_bias_risk': 'low',
            'performance_bias_risk': 'moderate',
            'detection_bias_risk': 'high',
            'reporting_bias_risk': 'unclear'
        }
        result = extract_rob_from_study_assessment(study_assessment)
        
        assert result is not None
        # 2.5 + 1.25 + 0 + 0.625 = 4.375
        expected = RISK_LEVEL_SCORES['low'] + RISK_LEVEL_SCORES['moderate'] + RISK_LEVEL_SCORES['high'] + RISK_LEVEL_SCORES['unclear']
        assert abs(result.score - expected) < 0.1

    def test_case_insensitive(self):
        """Test that risk levels are case insensitive."""
        study_assessment = {
            'selection_bias_risk': 'LOW',
            'performance_bias_risk': 'MODERATE'
        }
        result = extract_rob_from_study_assessment(study_assessment)
        
        assert result is not None
        assert result.score > 0

    def test_missing_fields(self):
        """Test with missing risk fields."""
        study_assessment = {}
        result = extract_rob_from_study_assessment(study_assessment)
        
        assert result is not None


class TestCreateErrorDimensionScore:
    """Tests for create_error_dimension_score function."""

    def test_basic_error_score(self):
        """Test creating error dimension score."""
        result = create_error_dimension_score(
            DIMENSION_METHODOLOGICAL_QUALITY,
            'LLM timeout'
        )
        
        assert result.dimension_name == DIMENSION_METHODOLOGICAL_QUALITY
        assert result.score == 5.0  # Default neutral score
        assert len(result.details) == 1
        assert result.details[0].component == 'error'
        assert 'LLM timeout' in result.details[0].reasoning

    def test_custom_default_score(self):
        """Test with custom default score."""
        result = create_error_dimension_score(
            DIMENSION_RISK_OF_BIAS,
            'Connection failed',
            default_score=3.0
        )
        
        assert result.score == 3.0


class TestConstants:
    """Tests for module constants."""

    def test_risk_level_scores(self):
        """Test risk level score mappings."""
        assert RISK_LEVEL_SCORES['low'] == 2.5
        assert RISK_LEVEL_SCORES['moderate'] == 1.25
        assert RISK_LEVEL_SCORES['high'] == 0.0
        assert RISK_LEVEL_SCORES['unclear'] == 0.625

    def test_mq_score_constants(self):
        """Test methodological quality score constants."""
        assert RANDOMIZATION_SCORE == 2.0
        assert DOUBLE_BLIND_SCORE == 2.0
        assert SINGLE_BLIND_SCORE == 1.0
        assert REMAINING_COMPONENTS_MAX == 5.0
        assert QUALITY_SCORE_MAX == 10.0

    def test_max_text_length(self):
        """Test max text length constant."""
        assert DEFAULT_MAX_TEXT_LENGTH == 8000
