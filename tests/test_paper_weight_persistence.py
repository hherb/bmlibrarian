"""Tests for database persistence in PaperWeightAssessmentAgent

This test module covers:
- Cache retrieval (_get_cached_assessment)
- Cache invalidation on version change
- Assessment storage (_store_assessment)
- Final weight calculation
- Error handling
"""

import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock
from bmlibrarian.agents.paper_weight import (
    PaperWeightAssessmentAgent,
    PaperWeightResult,
    DimensionScore,
    AssessmentDetail,
)


@pytest.fixture
def agent():
    """Create agent instance for testing (mocked DB connection)"""
    with patch.object(PaperWeightAssessmentAgent, '_get_db_connection'):
        agent = PaperWeightAssessmentAgent(show_model_info=False)
        return agent


@pytest.fixture
def sample_result():
    """Create sample result for testing"""
    study_design = DimensionScore('study_design', 8.0)
    study_design.add_detail('study_type', 'RCT', 8.0, reasoning='RCT detected')

    sample_size = DimensionScore('sample_size', 7.5)
    sample_size.add_detail('extracted_n', '450', 5.5, reasoning='Log10(450) * 2 = 5.3')
    sample_size.add_detail('power_calculation', 'yes', 2.0, reasoning='Power calculation mentioned')

    methodological_quality = DimensionScore('methodological_quality', 6.5)
    methodological_quality.add_detail(
        'randomization', '2.0', 2.0,
        evidence='computer-generated random numbers',
        reasoning='Proper randomization'
    )
    methodological_quality.add_detail(
        'blinding', '2.0', 2.0,
        evidence='double-blind',
        reasoning='Double-blind design'
    )

    risk_of_bias = DimensionScore('risk_of_bias', 7.0)
    risk_of_bias.add_detail(
        'selection_bias', 'low (2.5)', 2.5,
        evidence='random sampling',
        reasoning='Low risk of selection bias'
    )

    replication_status = DimensionScore('replication_status', 0.0)
    replication_status.add_detail(
        'replication_count', '0', 0.0,
        reasoning='No confirming replications found'
    )

    return PaperWeightResult(
        document_id=99999,  # Test document ID
        assessor_version='1.0.0',
        assessed_at=datetime.now(),
        study_design=study_design,
        sample_size=sample_size,
        methodological_quality=methodological_quality,
        risk_of_bias=risk_of_bias,
        replication_status=replication_status,
        final_weight=7.2,
        dimension_weights={
            'study_design': 0.25,
            'sample_size': 0.15,
            'methodological_quality': 0.30,
            'risk_of_bias': 0.20,
            'replication_status': 0.10
        },
        study_type='RCT',
        sample_size_n=450
    )


class TestComputeFinalWeight:
    """Tests for final weight calculation"""

    def test_compute_final_weight_default_weights(self, agent):
        """Test final weight calculation with default weights"""
        dimension_scores = {
            'study_design': DimensionScore('study_design', 8.0),
            'sample_size': DimensionScore('sample_size', 7.0),
            'methodological_quality': DimensionScore('methodological_quality', 6.0),
            'risk_of_bias': DimensionScore('risk_of_bias', 7.0),
            'replication_status': DimensionScore('replication_status', 5.0)
        }

        # Default weights: 0.25, 0.15, 0.30, 0.20, 0.10
        # Expected: 8.0*0.25 + 7.0*0.15 + 6.0*0.30 + 7.0*0.20 + 5.0*0.10
        #         = 2.0 + 1.05 + 1.8 + 1.4 + 0.5 = 6.75

        final_weight = agent._compute_final_weight(dimension_scores)

        assert final_weight == pytest.approx(6.75, abs=0.01)

    def test_compute_final_weight_capped_at_10(self, agent):
        """Test that final weight is capped at 10.0"""
        # All perfect scores
        dimension_scores = {
            'study_design': DimensionScore('study_design', 10.0),
            'sample_size': DimensionScore('sample_size', 10.0),
            'methodological_quality': DimensionScore('methodological_quality', 10.0),
            'risk_of_bias': DimensionScore('risk_of_bias', 10.0),
            'replication_status': DimensionScore('replication_status', 10.0)
        }

        final_weight = agent._compute_final_weight(dimension_scores)

        # 10*(0.25+0.15+0.30+0.20+0.10) = 10*1.0 = 10.0
        assert final_weight == 10.0

    def test_compute_final_weight_minimum_zero(self, agent):
        """Test that final weight has minimum of 0.0"""
        # All zero scores
        dimension_scores = {
            'study_design': DimensionScore('study_design', 0.0),
            'sample_size': DimensionScore('sample_size', 0.0),
            'methodological_quality': DimensionScore('methodological_quality', 0.0),
            'risk_of_bias': DimensionScore('risk_of_bias', 0.0),
            'replication_status': DimensionScore('replication_status', 0.0)
        }

        final_weight = agent._compute_final_weight(dimension_scores)

        assert final_weight == 0.0


class TestResultSerialization:
    """Tests for result serialization methods"""

    def test_result_to_dict(self, sample_result):
        """Test PaperWeightResult.to_dict() serialization"""
        result_dict = sample_result.to_dict()

        assert result_dict['document_id'] == 99999
        assert result_dict['assessor_version'] == '1.0.0'
        assert result_dict['study_design_score'] == 8.0
        assert result_dict['sample_size_score'] == 7.5
        assert result_dict['methodological_quality_score'] == 6.5
        assert result_dict['risk_of_bias_score'] == 7.0
        assert result_dict['replication_status_score'] == 0.0
        assert result_dict['final_weight'] == 7.2
        assert result_dict['study_type'] == 'RCT'
        assert result_dict['sample_size'] == 450

    def test_get_all_details(self, sample_result):
        """Test collecting all assessment details"""
        all_details = sample_result.get_all_details()

        # Should have all details from all dimensions
        assert len(all_details) >= 5  # At least 5 details added in fixture

        # Check dimensions are present
        dimensions = set(d.dimension for d in all_details)
        assert 'study_design' in dimensions
        assert 'sample_size' in dimensions
        assert 'methodological_quality' in dimensions
        assert 'risk_of_bias' in dimensions
        assert 'replication_status' in dimensions

    def test_result_to_markdown(self, sample_result):
        """Test markdown report generation"""
        markdown = sample_result.to_markdown()

        assert '# Paper Weight Assessment Report' in markdown
        assert 'Document ID:** 99999' in markdown
        assert 'Study Type:** RCT' in markdown
        assert 'Sample Size:** 450' in markdown
        assert 'Final Weight: 7.20/10' in markdown
        assert '### Study Design: 8.00/10' in markdown


class TestDimensionScore:
    """Tests for DimensionScore operations"""

    def test_add_detail(self):
        """Test adding details to a dimension score"""
        score = DimensionScore('test_dimension', 5.0)

        score.add_detail(
            component='test_component',
            value='test_value',
            contribution=2.5,
            evidence='test evidence',
            reasoning='test reasoning'
        )

        assert len(score.details) == 1
        detail = score.details[0]
        assert detail.dimension == 'test_dimension'
        assert detail.component == 'test_component'
        assert detail.extracted_value == 'test_value'
        assert detail.score_contribution == 2.5
        assert detail.evidence_text == 'test evidence'
        assert detail.reasoning == 'test reasoning'

    def test_to_dict(self):
        """Test DimensionScore.to_dict() serialization"""
        score = DimensionScore('test_dimension', 7.5)
        score.add_detail('comp1', 'val1', 3.0)
        score.add_detail('comp2', 'val2', 4.5)

        result = score.to_dict()

        assert result['dimension_name'] == 'test_dimension'
        assert result['score'] == 7.5
        assert len(result['details']) == 2


class TestErrorHandling:
    """Tests for error handling methods"""

    def test_create_error_result(self, agent):
        """Test creation of error result"""
        error_result = agent._create_error_result(
            document_id=12345,
            error_message="Test error message"
        )

        assert error_result.document_id == 12345
        assert error_result.final_weight == 0.0
        assert error_result.assessor_version == agent.config.get('version', '1.0.0')

        # All dimension scores should be error scores
        assert error_result.study_design.dimension_name == 'error'
        assert error_result.sample_size.dimension_name == 'error'

        # Check error detail is present
        assert len(error_result.study_design.details) == 1
        assert error_result.study_design.details[0].reasoning == 'Test error message'


class TestLLMJSONParsing:
    """Tests for LLM response JSON parsing"""

    def test_parse_json_with_markdown_block(self, agent):
        """Test parsing JSON wrapped in markdown code block"""
        response = '''```json
{
    "randomization": {"score": 2.0, "evidence": "computer-generated", "reasoning": "Proper method"},
    "blinding": {"score": 2.0, "evidence": "double-blind", "reasoning": "Participants and assessors"}
}
```'''
        result = agent._parse_llm_json_response(response)

        assert result['randomization']['score'] == 2.0
        assert result['blinding']['score'] == 2.0

    def test_parse_bare_json(self, agent):
        """Test parsing bare JSON without markdown"""
        response = '''{
    "randomization": {"score": 2.0, "evidence": "test", "reasoning": "test"},
    "blinding": {"score": 3.0, "evidence": "test", "reasoning": "test"}
}'''
        result = agent._parse_llm_json_response(response)

        assert result['randomization']['score'] == 2.0
        assert result['blinding']['score'] == 3.0

    def test_parse_json_with_extra_text(self, agent):
        """Test parsing JSON with surrounding text"""
        response = '''Here is the analysis:
{
    "test_component": {"score": 1.5, "evidence": "found", "reasoning": "good"}
}
That concludes the assessment.'''
        result = agent._parse_llm_json_response(response)

        assert result['test_component']['score'] == 1.5

    def test_parse_invalid_json_raises(self, agent):
        """Test that invalid JSON raises ValueError"""
        response = "This is not JSON at all"

        with pytest.raises(ValueError, match="Could not find JSON"):
            agent._parse_llm_json_response(response)

    def test_parse_malformed_json_raises(self, agent):
        """Test that malformed JSON raises ValueError"""
        response = '{"incomplete": {"score": '

        with pytest.raises(ValueError):
            agent._parse_llm_json_response(response)


class TestMethodologicalQualityScoring:
    """Tests for methodological quality score calculation"""

    def test_calculate_mq_score_perfect(self, agent):
        """Test MQ score calculation with perfect scores"""
        components = {
            "randomization": {"score": 2.0, "evidence": "proper", "reasoning": "good"},
            "blinding": {"score": 3.0, "evidence": "triple", "reasoning": "excellent"},
            "allocation_concealment": {"score": 1.5, "evidence": "sealed", "reasoning": "proper"},
            "protocol_preregistration": {"score": 1.5, "evidence": "NCT123", "reasoning": "registered"},
            "itt_analysis": {"score": 1.0, "evidence": "ITT", "reasoning": "proper"},
            "attrition_handling": {"score": 1.0, "evidence": "5%", "reasoning": "excellent"}
        }

        result = agent._calculate_methodological_quality_score(components)

        assert result.dimension_name == 'methodological_quality'
        assert result.score == 10.0  # Perfect score (sum = 10.0)
        assert len(result.details) == 6

    def test_calculate_mq_score_capped(self, agent):
        """Test that MQ score is capped at 10.0"""
        # Artificially high scores that would sum > 10
        components = {
            "comp1": {"score": 6.0, "evidence": "test", "reasoning": "test"},
            "comp2": {"score": 6.0, "evidence": "test", "reasoning": "test"}
        }

        result = agent._calculate_methodological_quality_score(components)

        assert result.score == 10.0  # Should be capped


class TestRiskOfBiasScoring:
    """Tests for risk of bias score calculation"""

    def test_calculate_rob_score(self, agent):
        """Test RoB score calculation"""
        components = {
            "selection_bias": {"score": 2.5, "risk_level": "low", "evidence": "random", "reasoning": "good"},
            "performance_bias": {"score": 2.5, "risk_level": "low", "evidence": "blinded", "reasoning": "good"},
            "detection_bias": {"score": 2.0, "risk_level": "low", "evidence": "blinded", "reasoning": "good"},
            "reporting_bias": {"score": 2.5, "risk_level": "low", "evidence": "protocol", "reasoning": "good"}
        }

        result = agent._calculate_risk_of_bias_score(components)

        assert result.dimension_name == 'risk_of_bias'
        assert result.score == pytest.approx(9.5, abs=0.01)
        assert len(result.details) == 4

        # Check that value includes risk level
        assert 'low' in result.details[0].extracted_value


class TestTextPreparation:
    """Tests for document text preparation"""

    def test_prepare_text_with_full_text(self, agent):
        """Test text preparation when full text is available"""
        document = {
            'title': 'Test Paper',
            'abstract': 'Short abstract',
            'full_text': 'Long full text content here'
        }

        text = agent._prepare_text_for_analysis(document)

        assert 'TITLE: Test Paper' in text
        assert 'FULL TEXT:' in text
        assert 'Long full text content' in text
        assert 'ABSTRACT:' not in text  # Should use full text, not abstract

    def test_prepare_text_abstract_fallback(self, agent):
        """Test text preparation falls back to abstract when no full text"""
        document = {
            'title': 'Test Paper',
            'abstract': 'Abstract content here',
            'full_text': ''
        }

        text = agent._prepare_text_for_analysis(document)

        assert 'TITLE: Test Paper' in text
        assert 'ABSTRACT:' in text
        assert 'Abstract content here' in text

    def test_prepare_text_length_limit(self, agent):
        """Test that text preparation limits length"""
        document = {
            'title': 'Test',
            'abstract': 'A' * 10000,  # Very long abstract
            'full_text': ''
        }

        text = agent._prepare_text_for_analysis(document)

        assert len(text) <= 8000

    def test_prepare_text_handles_none(self, agent):
        """Test text preparation handles None values"""
        document = {
            'title': None,
            'abstract': None,
            'full_text': None
        }

        text = agent._prepare_text_for_analysis(document)

        assert 'TITLE:' in text
        assert 'ABSTRACT:' in text


class TestGetDimensionWeights:
    """Tests for dimension weight retrieval"""

    def test_get_dimension_weights_default(self, agent):
        """Test getting default dimension weights"""
        weights = agent.get_dimension_weights()

        assert weights['study_design'] == 0.25
        assert weights['sample_size'] == 0.15
        assert weights['methodological_quality'] == 0.30
        assert weights['risk_of_bias'] == 0.20
        assert weights['replication_status'] == 0.10

        # Weights should sum to 1.0
        total = sum(weights.values())
        assert total == pytest.approx(1.0, abs=0.001)


# Database Integration Tests (require database connection)
# These are marked with @pytest.mark.requires_database

@pytest.mark.requires_database
class TestDatabasePersistence:
    """Integration tests for database persistence (require live database)"""

    @pytest.fixture
    def db_agent(self):
        """Create agent with real database connection"""
        return PaperWeightAssessmentAgent(show_model_info=False)

    def test_store_and_retrieve_assessment(self, db_agent, sample_result):
        """Test storing and retrieving assessment from database"""
        # Store assessment
        db_agent._store_assessment(sample_result)

        # Retrieve from cache
        cached = db_agent._get_cached_assessment(sample_result.document_id)

        assert cached is not None
        assert cached.document_id == sample_result.document_id
        assert cached.final_weight == pytest.approx(sample_result.final_weight, abs=0.01)
        assert cached.study_type == sample_result.study_type
        assert cached.sample_size_n == sample_result.sample_size_n

        # Verify dimension scores
        assert cached.study_design.score == pytest.approx(sample_result.study_design.score, abs=0.01)
        assert cached.sample_size.score == pytest.approx(sample_result.sample_size.score, abs=0.01)

        # Verify details were stored
        assert len(cached.study_design.details) > 0
        assert len(cached.sample_size.details) > 0

    def test_cache_invalidation_on_version_change(self, db_agent, sample_result):
        """Test that cache is invalidated when version changes"""
        # Store with version 1.0.0
        db_agent._store_assessment(sample_result)

        # Should retrieve with same version
        cached = db_agent._get_cached_assessment(sample_result.document_id)
        assert cached is not None

        # Change version in config
        db_agent.config['version'] = '2.0.0'

        # Should NOT retrieve (version mismatch)
        cached = db_agent._get_cached_assessment(sample_result.document_id)
        assert cached is None

        # Restore version
        db_agent.config['version'] = '1.0.0'

    def test_upsert_behavior(self, db_agent, sample_result):
        """Test that storing same document_id + version updates existing record"""
        # Store initial assessment
        db_agent._store_assessment(sample_result)

        # Modify the result
        modified_result = sample_result
        modified_result.final_weight = 8.5
        modified_result.assessed_at = datetime.now()

        # Store again (should update, not insert duplicate)
        db_agent._store_assessment(modified_result)

        # Retrieve and verify it was updated
        cached = db_agent._get_cached_assessment(sample_result.document_id)
        assert cached is not None
        assert cached.final_weight == pytest.approx(8.5, abs=0.01)


@pytest.mark.requires_database
class TestReplicationStatusLookup:
    """Tests for replication status database lookup"""

    @pytest.fixture
    def db_agent(self):
        """Create agent with real database connection"""
        return PaperWeightAssessmentAgent(show_model_info=False)

    def test_no_replications_returns_zero(self, db_agent):
        """Test that document with no replications returns 0 score"""
        # Use a document ID that likely has no replications
        result = db_agent._check_replication_status(999999999)

        assert result.dimension_name == 'replication_status'
        assert result.score == 0.0
        assert len(result.details) == 1
        assert result.details[0].extracted_value == '0'
