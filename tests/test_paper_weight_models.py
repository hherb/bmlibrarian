"""Tests for paper weight assessment data models.

This test module verifies the functionality of the paper weight assessment
dataclasses: AssessmentDetail, DimensionScore, and PaperWeightResult.
"""

import pytest
from datetime import datetime
import json
from bmlibrarian.agents.paper_weight_agent import (
    AssessmentDetail, DimensionScore, PaperWeightResult,
    EVIDENCE_TRUNCATION_LENGTH
)


class TestAssessmentDetail:
    """Tests for AssessmentDetail dataclass."""

    def test_creation_with_all_fields(self):
        """Test creating an AssessmentDetail with all fields populated."""
        detail = AssessmentDetail(
            dimension="study_design",
            component="study_type",
            extracted_value="RCT",
            score_contribution=8.0,
            evidence_text="randomized controlled trial",
            reasoning="Identified as RCT from methods section"
        )

        assert detail.dimension == "study_design"
        assert detail.component == "study_type"
        assert detail.extracted_value == "RCT"
        assert detail.score_contribution == 8.0
        assert "randomized" in detail.evidence_text
        assert "RCT" in detail.reasoning

    def test_creation_with_optional_fields_none(self):
        """Test creating an AssessmentDetail with optional fields as None."""
        detail = AssessmentDetail(
            dimension="sample_size",
            component="extracted_n",
            extracted_value="250",
            score_contribution=4.8
        )

        assert detail.dimension == "sample_size"
        assert detail.evidence_text is None
        assert detail.reasoning is None

    def test_to_dict(self):
        """Test serialization to dictionary."""
        detail = AssessmentDetail(
            dimension="methodological_quality",
            component="blinding_type",
            extracted_value="double-blind",
            score_contribution=3.0,
            evidence_text="participants were masked",
            reasoning="Full blinding detected"
        )

        data = detail.to_dict()

        assert data['dimension'] == "methodological_quality"
        assert data['component'] == "blinding_type"
        assert data['extracted_value'] == "double-blind"
        assert data['score_contribution'] == 3.0
        assert data['evidence_text'] == "participants were masked"
        assert data['reasoning'] == "Full blinding detected"

    def test_to_dict_with_none_values(self):
        """Test serialization preserves None values."""
        detail = AssessmentDetail(
            dimension="risk_of_bias",
            component="selection_bias",
            extracted_value=None,
            score_contribution=0.0
        )

        data = detail.to_dict()

        assert data['extracted_value'] is None
        assert data['evidence_text'] is None
        assert data['reasoning'] is None


class TestDimensionScore:
    """Tests for DimensionScore dataclass."""

    def test_creation_with_score(self):
        """Test creating a DimensionScore with just a score."""
        score = DimensionScore(dimension_name="sample_size", score=7.5)

        assert score.dimension_name == "sample_size"
        assert score.score == 7.5
        assert score.details == []

    def test_add_detail(self):
        """Test adding details to DimensionScore."""
        score = DimensionScore(dimension_name="sample_size", score=7.5)

        score.add_detail(
            component="extracted_n",
            value="450",
            contribution=5.5
        )

        score.add_detail(
            component="power_calculation",
            value="yes",
            contribution=2.0,
            reasoning="Power calculation mentioned in methods"
        )

        assert len(score.details) == 2
        assert score.details[0].component == "extracted_n"
        assert score.details[0].extracted_value == "450"
        assert score.details[0].score_contribution == 5.5
        assert score.details[0].dimension == "sample_size"  # Auto-set from dimension_name
        assert score.details[1].component == "power_calculation"
        assert score.details[1].score_contribution == 2.0
        assert score.details[1].reasoning == "Power calculation mentioned in methods"

    def test_add_detail_with_evidence(self):
        """Test adding a detail with evidence text."""
        score = DimensionScore(dimension_name="methodological_quality", score=6.5)

        score.add_detail(
            component="randomization",
            value="computer-generated",
            contribution=2.0,
            evidence="Randomization was performed using a computer-generated sequence",
            reasoning="Proper sequence generation method described"
        )

        assert len(score.details) == 1
        detail = score.details[0]
        assert detail.evidence_text is not None
        assert "computer-generated" in detail.evidence_text
        assert detail.reasoning is not None

    def test_to_dict(self):
        """Test serialization of DimensionScore."""
        score = DimensionScore(dimension_name="study_design", score=8.0)
        score.add_detail(
            component="study_type",
            value="RCT",
            contribution=8.0
        )

        data = score.to_dict()

        assert data['dimension_name'] == "study_design"
        assert data['score'] == 8.0
        assert len(data['details']) == 1
        assert data['details'][0]['component'] == "study_type"

    def test_to_dict_empty_details(self):
        """Test serialization with no details."""
        score = DimensionScore(dimension_name="replication_status", score=0.0)

        data = score.to_dict()

        assert data['details'] == []


class TestPaperWeightResult:
    """Tests for PaperWeightResult dataclass."""

    @pytest.fixture
    def sample_result(self):
        """Create a sample PaperWeightResult for testing."""
        return PaperWeightResult(
            document_id=12345,
            assessor_version="1.0.0",
            assessed_at=datetime(2025, 1, 15, 10, 30),
            study_design=DimensionScore("study_design", 8.0),
            sample_size=DimensionScore("sample_size", 7.5),
            methodological_quality=DimensionScore("methodological_quality", 6.5),
            risk_of_bias=DimensionScore("risk_of_bias", 7.0),
            replication_status=DimensionScore("replication_status", 5.0),
            final_weight=7.2,
            dimension_weights={
                "study_design": 0.25,
                "sample_size": 0.15,
                "methodological_quality": 0.30,
                "risk_of_bias": 0.20,
                "replication_status": 0.10
            },
            study_type="RCT",
            sample_size_n=450
        )

    def test_creation(self, sample_result):
        """Test creating a PaperWeightResult."""
        assert sample_result.document_id == 12345
        assert sample_result.assessor_version == "1.0.0"
        assert sample_result.study_design.score == 8.0
        assert sample_result.sample_size.score == 7.5
        assert sample_result.final_weight == 7.2
        assert sample_result.study_type == "RCT"
        assert sample_result.sample_size_n == 450

    def test_creation_without_metadata(self):
        """Test creating without optional metadata."""
        result = PaperWeightResult(
            document_id=99999,
            assessor_version="1.0.0",
            assessed_at=datetime.now(),
            study_design=DimensionScore("study_design", 5.0),
            sample_size=DimensionScore("sample_size", 5.0),
            methodological_quality=DimensionScore("methodological_quality", 5.0),
            risk_of_bias=DimensionScore("risk_of_bias", 5.0),
            replication_status=DimensionScore("replication_status", 5.0),
            final_weight=5.0,
            dimension_weights={}
        )

        assert result.study_type is None
        assert result.sample_size_n is None

    def test_to_dict(self, sample_result):
        """Test serialization of PaperWeightResult."""
        data = sample_result.to_dict()

        assert data['document_id'] == 12345
        assert data['assessor_version'] == "1.0.0"
        assert data['study_design_score'] == 8.0
        assert data['sample_size_score'] == 7.5
        assert data['methodological_quality_score'] == 6.5
        assert data['risk_of_bias_score'] == 7.0
        assert data['replication_status_score'] == 5.0
        assert data['final_weight'] == 7.2
        assert data['study_type'] == "RCT"
        assert data['sample_size'] == 450  # Note: maps to sample_size, not sample_size_n

        # Dimension weights should be JSON string
        weights = json.loads(data['dimension_weights'])
        assert weights['study_design'] == 0.25
        assert weights['methodological_quality'] == 0.30

    def test_get_all_details(self):
        """Test collecting all audit trail details."""
        study_design = DimensionScore("study_design", 8.0)
        study_design.add_detail("study_type", "RCT", 8.0)

        sample_size = DimensionScore("sample_size", 7.5)
        sample_size.add_detail("extracted_n", "450", 5.5)
        sample_size.add_detail("power_calculation", "yes", 2.0)

        methodological = DimensionScore("methodological_quality", 6.5)
        methodological.add_detail("blinding", "double-blind", 3.0)

        result = PaperWeightResult(
            document_id=12345,
            assessor_version="1.0.0",
            assessed_at=datetime.now(),
            study_design=study_design,
            sample_size=sample_size,
            methodological_quality=methodological,
            risk_of_bias=DimensionScore("risk_of_bias", 7.0),
            replication_status=DimensionScore("replication_status", 5.0),
            final_weight=7.2,
            dimension_weights={}
        )

        all_details = result.get_all_details()

        assert len(all_details) == 4  # 1 + 2 + 1 + 0 + 0
        assert all_details[0].dimension == "study_design"
        assert all_details[1].dimension == "sample_size"
        assert all_details[2].dimension == "sample_size"
        assert all_details[3].dimension == "methodological_quality"

    def test_get_all_details_empty(self, sample_result):
        """Test get_all_details when no details exist."""
        all_details = sample_result.get_all_details()
        assert all_details == []

    def test_to_markdown(self):
        """Test Markdown report generation."""
        study_design = DimensionScore("study_design", 8.0)
        study_design.add_detail(
            "study_type", "RCT", 8.0,
            evidence="This randomized controlled trial...",
            reasoning="Clear RCT identified"
        )

        result = PaperWeightResult(
            document_id=12345,
            assessor_version="1.0.0",
            assessed_at=datetime(2025, 1, 15, 10, 30),
            study_design=study_design,
            sample_size=DimensionScore("sample_size", 7.5),
            methodological_quality=DimensionScore("methodological_quality", 6.5),
            risk_of_bias=DimensionScore("risk_of_bias", 7.0),
            replication_status=DimensionScore("replication_status", 5.0),
            final_weight=7.2,
            dimension_weights={"study_design": 0.25},
            study_type="RCT",
            sample_size_n=450
        )

        markdown = result.to_markdown()

        assert "# Paper Weight Assessment Report" in markdown
        assert "**Document ID:** 12345" in markdown
        assert "**Study Type:** RCT" in markdown
        assert "**Sample Size:** 450" in markdown
        assert "**Assessor Version:** 1.0.0" in markdown
        assert "## Final Weight: 7.20/10" in markdown
        assert "### Study Design: 8.00/10" in markdown
        assert "### Sample Size: 7.50/10" in markdown
        assert "**study_type:** RCT" in markdown
        assert "Score contribution: 8.00" in markdown
        assert "Clear RCT identified" in markdown

    def test_to_markdown_without_details(self, sample_result):
        """Test Markdown generation for dimensions without details."""
        markdown = sample_result.to_markdown()

        # Should indicate no detailed breakdown
        assert "*No detailed breakdown available*" in markdown

    def test_to_markdown_truncates_long_evidence(self):
        """Test that long evidence text is truncated in Markdown."""
        study_design = DimensionScore("study_design", 8.0)
        # Create evidence longer than truncation threshold
        long_evidence_length = EVIDENCE_TRUNCATION_LENGTH * 2
        long_evidence = "A" * long_evidence_length
        study_design.add_detail(
            "study_type", "RCT", 8.0,
            evidence=long_evidence
        )

        result = PaperWeightResult(
            document_id=12345,
            assessor_version="1.0.0",
            assessed_at=datetime.now(),
            study_design=study_design,
            sample_size=DimensionScore("sample_size", 5.0),
            methodological_quality=DimensionScore("methodological_quality", 5.0),
            risk_of_bias=DimensionScore("risk_of_bias", 5.0),
            replication_status=DimensionScore("replication_status", 5.0),
            final_weight=5.5,
            dimension_weights={}
        )

        markdown = result.to_markdown()

        # Evidence should be truncated with "..."
        assert "..." in markdown
        # Should not contain full evidence string
        assert "A" * long_evidence_length not in markdown
        # Should contain truncated version
        assert "A" * EVIDENCE_TRUNCATION_LENGTH in markdown

    def test_from_db_row(self):
        """Test reconstructing PaperWeightResult from database rows."""
        # Simulate database row
        row = {
            'document_id': 12345,
            'assessor_version': "1.0.0",
            'assessed_at': datetime(2025, 1, 15, 10, 30),
            'study_design_score': 8.0,
            'sample_size_score': 7.5,
            'methodological_quality_score': 6.5,
            'risk_of_bias_score': 7.0,
            'replication_status_score': 5.0,
            'final_weight': 7.2,
            'dimension_weights': '{"study_design": 0.25, "sample_size": 0.15}',
            'study_type': "RCT",
            'sample_size': 450
        }

        # Simulate detail rows
        details = [
            {
                'dimension': 'study_design',
                'component': 'study_type',
                'extracted_value': 'RCT',
                'score_contribution': 8.0,
                'evidence_text': 'randomized controlled',
                'reasoning': 'Identified as RCT'
            },
            {
                'dimension': 'sample_size',
                'component': 'extracted_n',
                'extracted_value': '450',
                'score_contribution': 5.5,
                'evidence_text': None,
                'reasoning': 'Log10(450) * 2'
            }
        ]

        result = PaperWeightResult.from_db_row(row, details)

        assert result.document_id == 12345
        assert result.assessor_version == "1.0.0"
        assert result.study_design.score == 8.0
        assert result.sample_size.score == 7.5
        assert result.final_weight == 7.2
        assert result.study_type == "RCT"
        assert result.sample_size_n == 450
        assert len(result.study_design.details) == 1
        assert len(result.sample_size.details) == 1
        assert result.study_design.details[0].component == "study_type"
        assert result.dimension_weights['study_design'] == 0.25

    def test_from_db_row_with_dict_weights(self):
        """Test from_db_row when dimension_weights is already a dict."""
        row = {
            'document_id': 99999,
            'assessor_version': "1.0.0",
            'assessed_at': datetime.now(),
            'study_design_score': 5.0,
            'sample_size_score': 5.0,
            'methodological_quality_score': 5.0,
            'risk_of_bias_score': 5.0,
            'replication_status_score': 5.0,
            'final_weight': 5.0,
            'dimension_weights': {"study_design": 0.25},  # Already dict
            'study_type': None,
            'sample_size': None
        }

        result = PaperWeightResult.from_db_row(row, [])

        assert result.dimension_weights == {"study_design": 0.25}

    def test_from_db_row_empty_details(self):
        """Test from_db_row with no detail rows."""
        row = {
            'document_id': 99999,
            'assessor_version': "1.0.0",
            'assessed_at': datetime.now(),
            'study_design_score': 5.0,
            'sample_size_score': 5.0,
            'methodological_quality_score': 5.0,
            'risk_of_bias_score': 5.0,
            'replication_status_score': 5.0,
            'final_weight': 5.0,
            'dimension_weights': '{}',
            'study_type': None,
            'sample_size': None
        }

        result = PaperWeightResult.from_db_row(row, [])

        assert len(result.get_all_details()) == 0

    def test_from_db_row_null_score_contribution(self):
        """Test from_db_row handles NULL score_contribution."""
        row = {
            'document_id': 99999,
            'assessor_version': "1.0.0",
            'assessed_at': datetime.now(),
            'study_design_score': 5.0,
            'sample_size_score': 5.0,
            'methodological_quality_score': 5.0,
            'risk_of_bias_score': 5.0,
            'replication_status_score': 5.0,
            'final_weight': 5.0,
            'dimension_weights': '{}',
            'study_type': None,
            'sample_size': None
        }

        details = [
            {
                'dimension': 'study_design',
                'component': 'unknown',
                'extracted_value': None,
                'score_contribution': None,  # NULL from database
                'evidence_text': None,
                'reasoning': None
            }
        ]

        result = PaperWeightResult.from_db_row(row, details)

        assert result.study_design.details[0].score_contribution == 0.0


class TestIntegration:
    """Integration tests for the complete data model workflow."""

    def test_full_workflow_serialization_roundtrip(self):
        """Test that data can be serialized and deserialized correctly."""
        # Create a comprehensive result
        study_design = DimensionScore("study_design", 8.0)
        study_design.add_detail("study_type", "RCT", 8.0, reasoning="Clear RCT")

        sample_size = DimensionScore("sample_size", 7.3)
        sample_size.add_detail("extracted_n", "450", 5.3, reasoning="Log10(450) * 2")
        sample_size.add_detail("power_calculation", "yes", 2.0, evidence="80% power")

        result = PaperWeightResult(
            document_id=12345,
            assessor_version="1.0.0",
            assessed_at=datetime(2025, 1, 15, 10, 30),
            study_design=study_design,
            sample_size=sample_size,
            methodological_quality=DimensionScore("methodological_quality", 6.5),
            risk_of_bias=DimensionScore("risk_of_bias", 7.0),
            replication_status=DimensionScore("replication_status", 5.0),
            final_weight=7.2,
            dimension_weights={
                "study_design": 0.25,
                "sample_size": 0.15,
                "methodological_quality": 0.30,
                "risk_of_bias": 0.20,
                "replication_status": 0.10
            },
            study_type="RCT",
            sample_size_n=450
        )

        # Serialize
        data = result.to_dict()
        all_details = [d.to_dict() for d in result.get_all_details()]

        # Convert to DB format (simulate database retrieval)
        db_row = {
            'document_id': data['document_id'],
            'assessor_version': data['assessor_version'],
            'assessed_at': data['assessed_at'],
            'study_design_score': data['study_design_score'],
            'sample_size_score': data['sample_size_score'],
            'methodological_quality_score': data['methodological_quality_score'],
            'risk_of_bias_score': data['risk_of_bias_score'],
            'replication_status_score': data['replication_status_score'],
            'final_weight': data['final_weight'],
            'dimension_weights': data['dimension_weights'],
            'study_type': data['study_type'],
            'sample_size': data['sample_size']
        }

        # Deserialize
        reconstructed = PaperWeightResult.from_db_row(db_row, all_details)

        # Verify
        assert reconstructed.document_id == result.document_id
        assert reconstructed.final_weight == result.final_weight
        assert reconstructed.study_design.score == result.study_design.score
        assert len(reconstructed.get_all_details()) == len(result.get_all_details())
        assert reconstructed.study_design.details[0].reasoning == "Clear RCT"

    def test_dimension_weights_sum_validation(self):
        """Test that dimension weights can be validated to sum to 1.0."""
        weights = {
            "study_design": 0.25,
            "sample_size": 0.15,
            "methodological_quality": 0.30,
            "risk_of_bias": 0.20,
            "replication_status": 0.10
        }

        # Weights should sum to 1.0
        assert abs(sum(weights.values()) - 1.0) < 0.001
