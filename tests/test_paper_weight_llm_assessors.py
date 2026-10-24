"""
Tests for paper_weight_llm_assessors.py

Tests cover:
- Text preparation for LLM analysis
- Methodological quality score calculation
- Risk of bias score calculation
- StudyAssessmentAgent integration functions
- Error handling and edge cases
"""

from typing import Any, Dict

import pytest

from bmlibrarian.agents.paper_weight.llm_assessors import (
    DEFAULT_MAX_TEXT_LENGTH,
    MQ_COMPONENTS,
    ROB_COMPONENTS,
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
)
from bmlibrarian.agents.paper_weight import (
    DIMENSION_METHODOLOGICAL_QUALITY,
    DIMENSION_RISK_OF_BIAS,
)


def mq_reply(**overrides: Any) -> Dict[str, Any]:
    """Return a complete MQ reply scoring 0 everywhere, with ``overrides`` applied."""
    reply: Dict[str, Any] = {name: {'score': 0.0, 'evidence': '', 'reasoning': ''}
                             for name in MQ_COMPONENTS}
    reply.update(overrides)
    return reply


def rob_reply(**overrides: Any) -> Dict[str, Any]:
    """Return a complete RoB reply scoring 0 everywhere, with ``overrides`` applied."""
    reply: Dict[str, Any] = {name: {'score': 0.0, 'risk_level': 'high', 'evidence': '',
                                    'reasoning': ''}
                             for name in ROB_COMPONENTS}
    reply.update(overrides)
    return reply


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

    def test_scores_are_summed(self) -> None:
        """Component scores add up."""
        components = mq_reply(randomization={'score': 2.0}, blinding={'score': 1.0})
        result = calculate_methodological_quality_score(components)

        assert result.score == 3.0
        assert len(result.details) == len(MQ_COMPONENTS)

    def test_attrition_rate_in_value(self) -> None:
        """Test that attrition rate appears in value field."""
        components = mq_reply(attrition_handling={'score': 0.5, 'attrition_rate': 0.15})
        result = calculate_methodological_quality_score(components)

        detail = next(d for d in result.details if d.component == 'attrition_handling')
        assert 'attrition rate: 0.15' in detail.extracted_value

    def test_extra_keys_ignored(self) -> None:
        """Keys the prompt did not ask for neither break nor inflate the score."""
        components = mq_reply(randomization={'score': 2.0}, invalid='not a dict',
                              bonus={'score': 5.0})
        result = calculate_methodological_quality_score(components)

        assert result.score == 2.0
        assert len(result.details) == len(MQ_COMPONENTS)

    @pytest.mark.parametrize('reply', [
        {},
        mq_reply(blinding='not a dict'),
        mq_reply(blinding={'evidence': 'no score'}),
        mq_reply(blinding={'score': 'high'}),
        mq_reply(blinding={'score': True}),
        {'components': mq_reply()},
    ], ids=['empty', 'non_dict', 'no_score', 'text_score', 'bool_score', 'wrapped'])
    def test_malformed_reply_raises(self, reply: Dict[str, Any]) -> None:
        """A malformed reply raises instead of scoring missing parts as 0 (#345)."""
        with pytest.raises(ValueError, match='methodological quality'):
            calculate_methodological_quality_score(reply)

    def test_non_object_reply_raises(self) -> None:
        """A JSON array reply raises."""
        with pytest.raises(ValueError, match='not a JSON object'):
            calculate_methodological_quality_score([])  # type: ignore[arg-type]


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

    def test_high_risk_components(self) -> None:
        """A complete all-high-risk reply scores 0 (a real finding)."""
        result = calculate_risk_of_bias_score(rob_reply())

        assert result.score == 0.0

    def test_risk_level_in_value(self) -> None:
        """Test that risk level appears in value field."""
        components = rob_reply(selection_bias={'score': 1.25, 'risk_level': 'moderate'})
        result = calculate_risk_of_bias_score(components)

        assert 'moderate risk' in result.details[0].extracted_value

    def test_score_capped_at_10(self) -> None:
        """Test that score is capped at 10."""
        components = rob_reply(**{name: {'score': 5.0} for name in ROB_COMPONENTS})
        result = calculate_risk_of_bias_score(components)

        assert result.score == 10.0

    @pytest.mark.parametrize('reply', [
        {},
        {'selection_bias': 2, 'performance_bias': 2, 'detection_bias': 2, 'reporting_bias': 2},
        rob_reply(reporting_bias={'risk_level': 'low'}),
    ], ids=['empty', 'flat', 'no_score'])
    def test_malformed_reply_raises(self, reply: Dict[str, Any]) -> None:
        """A malformed reply raises instead of scoring missing parts as 0 (#345)."""
        with pytest.raises(ValueError, match='risk of bias'):
            calculate_risk_of_bias_score(reply)


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
