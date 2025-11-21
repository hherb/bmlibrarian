"""
Tests for paper_weight_models.py

Tests cover:
- AssessmentDetail creation and serialization
- DimensionScore creation, adding details, and serialization
- PaperWeightResult creation, serialization, and markdown output
- Edge cases: empty details, None values, boundary scores
"""

import pytest
from datetime import datetime
import json

from bmlibrarian.agents.paper_weight_models import (
    AssessmentDetail,
    DimensionScore,
    PaperWeightResult,
    DATETIME_FORMAT,
    DIMENSION_STUDY_DESIGN,
    DIMENSION_SAMPLE_SIZE,
    DIMENSION_METHODOLOGICAL_QUALITY,
    DIMENSION_RISK_OF_BIAS,
    DIMENSION_REPLICATION_STATUS,
    ALL_DIMENSIONS,
)


class TestAssessmentDetail:
    """Tests for AssessmentDetail dataclass."""

    def test_creation_with_required_fields(self):
        """Test creating AssessmentDetail with required fields only."""
        detail = AssessmentDetail(
            dimension='study_design',
            component='study_type',
            extracted_value='rct',
            score_contribution=8.0
        )
        assert detail.dimension == 'study_design'
        assert detail.component == 'study_type'
        assert detail.extracted_value == 'rct'
        assert detail.score_contribution == 8.0
        assert detail.evidence_text is None
        assert detail.reasoning is None

    def test_creation_with_all_fields(self):
        """Test creating AssessmentDetail with all fields."""
        detail = AssessmentDetail(
            dimension='methodological_quality',
            component='blinding',
            extracted_value='double-blind',
            score_contribution=3.0,
            evidence_text='Participants and investigators were masked...',
            reasoning='Double-blind design detected'
        )
        assert detail.evidence_text == 'Participants and investigators were masked...'
        assert detail.reasoning == 'Double-blind design detected'

    def test_to_dict(self):
        """Test to_dict serialization."""
        detail = AssessmentDetail(
            dimension='sample_size',
            component='extracted_n',
            extracted_value='450',
            score_contribution=5.3,
            evidence_text='n=450 participants',
            reasoning='Log10(450) * 2'
        )
        result = detail.to_dict()

        assert result['dimension'] == 'sample_size'
        assert result['component'] == 'extracted_n'
        assert result['extracted_value'] == '450'
        assert result['score_contribution'] == 5.3
        assert result['evidence_text'] == 'n=450 participants'
        assert result['reasoning'] == 'Log10(450) * 2'

    def test_to_dict_with_none_values(self):
        """Test to_dict when optional fields are None."""
        detail = AssessmentDetail(
            dimension='test',
            component='test_component',
            extracted_value=None,
            score_contribution=0.0
        )
        result = detail.to_dict()

        assert result['extracted_value'] is None
        assert result['evidence_text'] is None
        assert result['reasoning'] is None


class TestDimensionScore:
    """Tests for DimensionScore dataclass."""

    def test_creation_basic(self):
        """Test basic DimensionScore creation."""
        score = DimensionScore(dimension_name='study_design', score=8.0)

        assert score.dimension_name == 'study_design'
        assert score.score == 8.0
        assert score.details == []

    def test_add_detail(self):
        """Test adding details to a DimensionScore."""
        score = DimensionScore(dimension_name='sample_size', score=7.0)

        score.add_detail(
            component='extracted_n',
            value='500',
            contribution=5.4,
            evidence='n=500 participants',
            reasoning='Logarithmic scaling'
        )

        assert len(score.details) == 1
        detail = score.details[0]
        assert detail.dimension == 'sample_size'
        assert detail.component == 'extracted_n'
        assert detail.extracted_value == '500'
        assert detail.score_contribution == 5.4

    def test_add_multiple_details(self):
        """Test adding multiple details."""
        score = DimensionScore(dimension_name='sample_size', score=9.0)

        score.add_detail('extracted_n', '1000', 6.0)
        score.add_detail('power_calculation', 'yes', 2.0, reasoning='Power calc found')
        score.add_detail('ci_reporting', 'yes', 0.5, reasoning='CI reported')

        assert len(score.details) == 3
        assert score.details[0].component == 'extracted_n'
        assert score.details[1].component == 'power_calculation'
        assert score.details[2].component == 'ci_reporting'

    def test_to_dict(self):
        """Test to_dict serialization."""
        score = DimensionScore(dimension_name='methodological_quality', score=6.5)
        score.add_detail('randomization', 'yes', 2.0)

        result = score.to_dict()

        assert result['dimension_name'] == 'methodological_quality'
        assert result['score'] == 6.5
        assert len(result['details']) == 1
        assert result['details'][0]['component'] == 'randomization'

    def test_empty_details(self):
        """Test DimensionScore with no details."""
        score = DimensionScore(dimension_name='test', score=5.0)
        result = score.to_dict()

        assert result['details'] == []

    def test_boundary_scores(self):
        """Test boundary score values."""
        zero_score = DimensionScore(dimension_name='test', score=0.0)
        assert zero_score.score == 0.0

        max_score = DimensionScore(dimension_name='test', score=10.0)
        assert max_score.score == 10.0


class TestPaperWeightResult:
    """Tests for PaperWeightResult dataclass."""

    @pytest.fixture
    def sample_result(self):
        """Create a sample PaperWeightResult for testing."""
        return PaperWeightResult(
            document_id=12345,
            assessor_version='1.0.0',
            assessed_at=datetime(2024, 1, 15, 10, 30, 0),
            study_design=DimensionScore(DIMENSION_STUDY_DESIGN, 8.0),
            sample_size=DimensionScore(DIMENSION_SAMPLE_SIZE, 7.5),
            methodological_quality=DimensionScore(DIMENSION_METHODOLOGICAL_QUALITY, 6.5),
            risk_of_bias=DimensionScore(DIMENSION_RISK_OF_BIAS, 7.0),
            replication_status=DimensionScore(DIMENSION_REPLICATION_STATUS, 5.0),
            final_weight=7.2,
            dimension_weights={
                'study_design': 0.25,
                'sample_size': 0.15,
                'methodological_quality': 0.30,
                'risk_of_bias': 0.20,
                'replication_status': 0.10
            },
            study_type='rct',
            sample_size_n=450
        )

    def test_creation(self, sample_result):
        """Test PaperWeightResult creation."""
        assert sample_result.document_id == 12345
        assert sample_result.assessor_version == '1.0.0'
        assert sample_result.final_weight == 7.2
        assert sample_result.study_type == 'rct'
        assert sample_result.sample_size_n == 450

    def test_to_dict(self, sample_result):
        """Test to_dict serialization."""
        result = sample_result.to_dict()

        assert result['document_id'] == 12345
        assert result['assessor_version'] == '1.0.0'
        assert result['study_design_score'] == 8.0
        assert result['sample_size_score'] == 7.5
        assert result['final_weight'] == 7.2
        assert result['study_type'] == 'rct'
        assert result['sample_size'] == 450

        weights = json.loads(result['dimension_weights'])
        assert weights['study_design'] == 0.25

    def test_get_all_details(self, sample_result):
        """Test collecting all details from all dimensions."""
        sample_result.study_design.add_detail('study_type', 'rct', 8.0)
        sample_result.sample_size.add_detail('extracted_n', '450', 5.3)
        sample_result.sample_size.add_detail('power_calculation', 'yes', 2.0)

        all_details = sample_result.get_all_details()

        assert len(all_details) == 3
        dimensions = {d.dimension for d in all_details}
        assert DIMENSION_STUDY_DESIGN in dimensions
        assert DIMENSION_SAMPLE_SIZE in dimensions

    def test_get_all_details_empty(self, sample_result):
        """Test get_all_details when no details exist."""
        all_details = sample_result.get_all_details()
        assert all_details == []

    def test_to_markdown(self, sample_result):
        """Test Markdown report generation."""
        sample_result.study_design.add_detail('study_type', 'rct', 8.0, reasoning='Matched RCT keyword')

        markdown = sample_result.to_markdown()

        assert '# Paper Weight Assessment Report' in markdown
        assert '**Document ID:** 12345' in markdown
        assert '**Study Type:** rct' in markdown
        assert '**Sample Size:** 450' in markdown
        assert '## Final Weight: 7.20/10' in markdown
        assert '### Study Design: 8.00/10' in markdown

    def test_to_markdown_unknown_study_type(self):
        """Test Markdown when study_type is None."""
        result = PaperWeightResult(
            document_id=1,
            assessor_version='1.0.0',
            assessed_at=datetime.now(),
            study_design=DimensionScore(DIMENSION_STUDY_DESIGN, 5.0),
            sample_size=DimensionScore(DIMENSION_SAMPLE_SIZE, 0.0),
            methodological_quality=DimensionScore(DIMENSION_METHODOLOGICAL_QUALITY, 5.0),
            risk_of_bias=DimensionScore(DIMENSION_RISK_OF_BIAS, 5.0),
            replication_status=DimensionScore(DIMENSION_REPLICATION_STATUS, 0.0),
            final_weight=3.5,
            dimension_weights={'study_design': 0.25},
            study_type=None,
            sample_size_n=None
        )

        markdown = result.to_markdown()

        assert '**Study Type:** Unknown' in markdown
        assert '**Sample Size:** Not extracted' in markdown


class TestConstants:
    """Tests for module constants."""

    def test_dimension_constants(self):
        """Test dimension name constants."""
        assert DIMENSION_STUDY_DESIGN == 'study_design'
        assert DIMENSION_SAMPLE_SIZE == 'sample_size'
        assert DIMENSION_METHODOLOGICAL_QUALITY == 'methodological_quality'
        assert DIMENSION_RISK_OF_BIAS == 'risk_of_bias'
        assert DIMENSION_REPLICATION_STATUS == 'replication_status'

    def test_all_dimensions_list(self):
        """Test ALL_DIMENSIONS contains all dimension constants."""
        assert len(ALL_DIMENSIONS) == 5
        assert DIMENSION_STUDY_DESIGN in ALL_DIMENSIONS

    def test_datetime_format(self):
        """Test datetime format constant."""
        test_dt = datetime(2024, 1, 15, 10, 30, 45)
        formatted = test_dt.strftime(DATETIME_FORMAT)
        assert formatted == '2024-01-15 10:30:45'
