"""
Tests for Cochrane Assessment System

Tests the Cochrane-aligned study characterization and risk of bias assessment
components used in systematic reviews.
"""

import pytest
from datetime import datetime, timezone
from typing import Any, Dict

from bmlibrarian.agents.systematic_review.cochrane_models import (
    RiskOfBiasJudgement,
    RiskOfBiasItem,
    CochraneRiskOfBias,
    CochraneParticipants,
    CochraneInterventions,
    CochraneOutcomes,
    CochraneNotes,
    CochraneStudyCharacteristics,
    CochraneStudyAssessment,
    create_default_risk_of_bias_item,
    create_default_cochrane_risk_of_bias,
    ROB_JUDGEMENT_LOW,
    ROB_JUDGEMENT_HIGH,
    ROB_JUDGEMENT_UNCLEAR,
    VALID_ROB_JUDGEMENTS,
)
from bmlibrarian.agents.systematic_review.cochrane_formatter import (
    format_study_characteristics_markdown,
    format_risk_of_bias_markdown,
    format_complete_assessment_markdown,
    format_multiple_assessments_markdown,
    format_risk_of_bias_summary_markdown,
    format_study_characteristics_html,
    format_risk_of_bias_html,
    get_cochrane_css,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_rob_item() -> RiskOfBiasItem:
    """Create a sample RiskOfBiasItem for testing."""
    return RiskOfBiasItem(
        domain="Random sequence generation",
        bias_type="selection bias",
        judgement=ROB_JUDGEMENT_LOW,
        support_for_judgement="Computer-generated random sequence was used",
    )


@pytest.fixture
def sample_rob_item_with_outcome_type() -> RiskOfBiasItem:
    """Create a sample RiskOfBiasItem with outcome_type for testing."""
    return RiskOfBiasItem(
        domain="Blinding of outcome assessment (subjective outcomes)",
        bias_type="detection bias",
        judgement=ROB_JUDGEMENT_UNCLEAR,
        support_for_judgement="Methods not reported",
        outcome_type="subjective",
    )


@pytest.fixture
def sample_participants() -> CochraneParticipants:
    """Create sample CochraneParticipants for testing."""
    return CochraneParticipants(
        setting="United States",
        population="Adults with hypertension aged 40-70 years",
        inclusion_criteria=["Diagnosed hypertension", "Age 40-70"],
        exclusion_criteria=["Secondary hypertension", "Pregnancy"],
        total_participants=200,
        group_sizes={"intervention": 100, "control": 100},
        baseline_characteristics_reported=True,
    )


@pytest.fixture
def sample_interventions() -> CochraneInterventions:
    """Create sample CochraneInterventions for testing."""
    return CochraneInterventions(
        description="ACE inhibitor therapy for 12 months",
        intervention_groups=["Lisinopril 10mg daily"],
        control_description="Placebo",
        duration="12 months",
    )


@pytest.fixture
def sample_outcomes() -> CochraneOutcomes:
    """Create sample CochraneOutcomes for testing."""
    return CochraneOutcomes(
        description="Blood pressure, cardiovascular events, mortality",
        primary_outcomes=["Systolic blood pressure reduction"],
        secondary_outcomes=["Cardiovascular events", "All-cause mortality"],
        outcome_timepoints=["3 months", "6 months", "12 months"],
    )


@pytest.fixture
def sample_notes() -> CochraneNotes:
    """Create sample CochraneNotes for testing."""
    return CochraneNotes(
        follow_up_periods=["3 months", "6 months", "12 months"],
        funding_source="National Institutes of Health",
        conflicts_of_interest="None declared",
        ethical_approval="Approved by institutional review board",
        trial_registration="NCT12345678",
        publication_status="Full publication",
    )


@pytest.fixture
def sample_study_characteristics(
    sample_participants: CochraneParticipants,
    sample_interventions: CochraneInterventions,
    sample_outcomes: CochraneOutcomes,
    sample_notes: CochraneNotes,
) -> CochraneStudyCharacteristics:
    """Create sample CochraneStudyCharacteristics for testing."""
    return CochraneStudyCharacteristics(
        study_id="Smith 2023",
        methods="Parallel randomised controlled trial",
        participants=sample_participants,
        interventions=sample_interventions,
        outcomes=sample_outcomes,
        notes=sample_notes,
        document_id=12345,
        document_title="Effects of ACE inhibitors on blood pressure",
        pmid="12345678",
        doi="10.1000/example",
    )


@pytest.fixture
def sample_cochrane_rob() -> CochraneRiskOfBias:
    """Create sample CochraneRiskOfBias for testing."""
    return CochraneRiskOfBias(
        random_sequence_generation=RiskOfBiasItem(
            domain="Random sequence generation",
            bias_type="selection bias",
            judgement=ROB_JUDGEMENT_LOW,
            support_for_judgement="Computer-generated random sequence",
        ),
        allocation_concealment=RiskOfBiasItem(
            domain="Allocation concealment",
            bias_type="selection bias",
            judgement=ROB_JUDGEMENT_LOW,
            support_for_judgement="Central allocation with sealed envelopes",
        ),
        baseline_outcome_measurements=RiskOfBiasItem(
            domain="Baseline outcome measurements",
            bias_type="selection bias",
            judgement=ROB_JUDGEMENT_LOW,
            support_for_judgement="Groups similar at baseline",
        ),
        baseline_characteristics=RiskOfBiasItem(
            domain="Baseline characteristics",
            bias_type="selection bias",
            judgement=ROB_JUDGEMENT_LOW,
            support_for_judgement="Well-balanced baseline characteristics",
        ),
        blinding_participants_personnel=RiskOfBiasItem(
            domain="Blinding of participants and personnel",
            bias_type="performance bias",
            judgement=ROB_JUDGEMENT_LOW,
            support_for_judgement="Double-blind placebo-controlled",
        ),
        blinding_outcome_assessment_subjective=RiskOfBiasItem(
            domain="Blinding of outcome assessment (subjective outcomes)",
            bias_type="detection bias",
            judgement=ROB_JUDGEMENT_LOW,
            support_for_judgement="Outcome assessors blinded",
            outcome_type="subjective",
        ),
        blinding_outcome_assessment_objective=RiskOfBiasItem(
            domain="Blinding of outcome assessment (objective outcomes)",
            bias_type="detection bias",
            judgement=ROB_JUDGEMENT_LOW,
            support_for_judgement="Objective outcomes not affected by blinding",
            outcome_type="objective",
        ),
        incomplete_outcome_data=RiskOfBiasItem(
            domain="Incomplete outcome data",
            bias_type="attrition bias",
            judgement=ROB_JUDGEMENT_LOW,
            support_for_judgement="Low dropout rate (<5%)",
        ),
        selective_reporting=RiskOfBiasItem(
            domain="Selective reporting",
            bias_type="reporting bias",
            judgement=ROB_JUDGEMENT_LOW,
            support_for_judgement="All pre-specified outcomes reported",
        ),
    )


@pytest.fixture
def sample_assessment(
    sample_study_characteristics: CochraneStudyCharacteristics,
    sample_cochrane_rob: CochraneRiskOfBias,
) -> CochraneStudyAssessment:
    """Create sample CochraneStudyAssessment for testing."""
    return CochraneStudyAssessment(
        study_characteristics=sample_study_characteristics,
        risk_of_bias=sample_cochrane_rob,
        overall_quality_score=8.5,
        overall_confidence=0.85,
        evidence_level="Level 2 (moderate-high)",
        assessment_notes=["Well-designed RCT", "Large sample size"],
    )


# =============================================================================
# RiskOfBiasItem Tests
# =============================================================================

class TestRiskOfBiasItem:
    """Tests for RiskOfBiasItem dataclass."""

    def test_create_valid_item(self, sample_rob_item: RiskOfBiasItem) -> None:
        """Test creating a valid RiskOfBiasItem."""
        assert sample_rob_item.domain == "Random sequence generation"
        assert sample_rob_item.bias_type == "selection bias"
        assert sample_rob_item.judgement == ROB_JUDGEMENT_LOW
        assert sample_rob_item.support_for_judgement == "Computer-generated random sequence was used"
        assert sample_rob_item.outcome_type is None

    def test_create_item_with_outcome_type(
        self, sample_rob_item_with_outcome_type: RiskOfBiasItem
    ) -> None:
        """Test creating a RiskOfBiasItem with outcome_type."""
        assert sample_rob_item_with_outcome_type.outcome_type == "subjective"

    def test_to_dict(self, sample_rob_item: RiskOfBiasItem) -> None:
        """Test serialization to dictionary."""
        result = sample_rob_item.to_dict()
        assert result["domain"] == "Random sequence generation"
        assert result["bias_type"] == "selection bias"
        assert result["judgement"] == ROB_JUDGEMENT_LOW
        assert "outcome_type" not in result  # None values not included

    def test_to_dict_with_outcome_type(
        self, sample_rob_item_with_outcome_type: RiskOfBiasItem
    ) -> None:
        """Test serialization includes outcome_type when present."""
        result = sample_rob_item_with_outcome_type.to_dict()
        assert result["outcome_type"] == "subjective"

    def test_from_dict(self, sample_rob_item: RiskOfBiasItem) -> None:
        """Test deserialization from dictionary."""
        data = sample_rob_item.to_dict()
        restored = RiskOfBiasItem.from_dict(data)
        assert restored.domain == sample_rob_item.domain
        assert restored.judgement == sample_rob_item.judgement

    def test_invalid_judgement_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test that invalid judgement values trigger a warning."""
        with caplog.at_level("WARNING"):
            RiskOfBiasItem(
                domain="Test",
                bias_type="test",
                judgement="Invalid value",
                support_for_judgement="Test",
            )
        assert "Invalid RoB judgement" in caplog.text


# =============================================================================
# CochraneRiskOfBias Tests
# =============================================================================

class TestCochraneRiskOfBias:
    """Tests for CochraneRiskOfBias dataclass."""

    def test_has_all_nine_domains(self, sample_cochrane_rob: CochraneRiskOfBias) -> None:
        """Test that all 9 Cochrane domains are present."""
        items = sample_cochrane_rob.to_list()
        assert len(items) == 9

    def test_to_dict(self, sample_cochrane_rob: CochraneRiskOfBias) -> None:
        """Test serialization to dictionary."""
        result = sample_cochrane_rob.to_dict()
        assert "random_sequence_generation" in result
        assert "allocation_concealment" in result
        assert "baseline_outcome_measurements" in result
        assert "baseline_characteristics" in result
        assert "blinding_participants_personnel" in result
        assert "blinding_outcome_assessment_subjective" in result
        assert "blinding_outcome_assessment_objective" in result
        assert "incomplete_outcome_data" in result
        assert "selective_reporting" in result

    def test_from_dict(self, sample_cochrane_rob: CochraneRiskOfBias) -> None:
        """Test deserialization from dictionary."""
        data = sample_cochrane_rob.to_dict()
        restored = CochraneRiskOfBias.from_dict(data)
        assert len(restored.to_list()) == 9
        assert restored.random_sequence_generation.judgement == ROB_JUDGEMENT_LOW

    def test_get_summary_counts(self, sample_cochrane_rob: CochraneRiskOfBias) -> None:
        """Test summary count calculation."""
        counts = sample_cochrane_rob.get_summary_counts()
        assert counts[ROB_JUDGEMENT_LOW] == 9
        assert counts[ROB_JUDGEMENT_HIGH] == 0
        assert counts[ROB_JUDGEMENT_UNCLEAR] == 0


# =============================================================================
# CochraneStudyCharacteristics Tests
# =============================================================================

class TestCochraneStudyCharacteristics:
    """Tests for CochraneStudyCharacteristics dataclass."""

    def test_create_valid_characteristics(
        self, sample_study_characteristics: CochraneStudyCharacteristics
    ) -> None:
        """Test creating valid study characteristics."""
        assert sample_study_characteristics.study_id == "Smith 2023"
        assert sample_study_characteristics.methods == "Parallel randomised controlled trial"
        assert sample_study_characteristics.document_id == 12345

    def test_to_dict(
        self, sample_study_characteristics: CochraneStudyCharacteristics
    ) -> None:
        """Test serialization to dictionary."""
        result = sample_study_characteristics.to_dict()
        assert result["study_id"] == "Smith 2023"
        assert "participants" in result
        assert "interventions" in result
        assert "outcomes" in result
        assert "notes" in result

    def test_from_dict(
        self, sample_study_characteristics: CochraneStudyCharacteristics
    ) -> None:
        """Test deserialization from dictionary."""
        data = sample_study_characteristics.to_dict()
        restored = CochraneStudyCharacteristics.from_dict(data)
        assert restored.study_id == sample_study_characteristics.study_id
        assert restored.participants.setting == sample_study_characteristics.participants.setting

    def test_created_at_auto_set(self) -> None:
        """Test that created_at is automatically set."""
        participants = CochraneParticipants(
            setting="Test", population="Test population"
        )
        interventions = CochraneInterventions(description="Test intervention")
        outcomes = CochraneOutcomes(description="Test outcomes")
        notes = CochraneNotes()

        chars = CochraneStudyCharacteristics(
            study_id="Test 2023",
            methods="Test",
            participants=participants,
            interventions=interventions,
            outcomes=outcomes,
            notes=notes,
        )
        assert chars.created_at is not None


# =============================================================================
# CochraneStudyAssessment Tests
# =============================================================================

class TestCochraneStudyAssessment:
    """Tests for CochraneStudyAssessment dataclass."""

    def test_create_valid_assessment(
        self, sample_assessment: CochraneStudyAssessment
    ) -> None:
        """Test creating a valid assessment."""
        assert sample_assessment.study_id == "Smith 2023"
        assert sample_assessment.document_id == 12345
        assert sample_assessment.overall_quality_score == 8.5

    def test_to_dict(self, sample_assessment: CochraneStudyAssessment) -> None:
        """Test serialization to dictionary."""
        result = sample_assessment.to_dict()
        assert "study_characteristics" in result
        assert "risk_of_bias" in result
        assert result["overall_quality_score"] == 8.5
        assert result["assessment_version"] == "2.0.0"

    def test_from_dict(self, sample_assessment: CochraneStudyAssessment) -> None:
        """Test deserialization from dictionary."""
        data = sample_assessment.to_dict()
        restored = CochraneStudyAssessment.from_dict(data)
        assert restored.study_id == sample_assessment.study_id
        assert restored.overall_quality_score == sample_assessment.overall_quality_score


# =============================================================================
# Factory Function Tests
# =============================================================================

class TestFactoryFunctions:
    """Tests for factory functions."""

    def test_create_default_risk_of_bias_item(self) -> None:
        """Test creating default RiskOfBiasItem."""
        item = create_default_risk_of_bias_item(
            "Test domain", "test bias"
        )
        assert item.domain == "Test domain"
        assert item.bias_type == "test bias"
        assert item.judgement == ROB_JUDGEMENT_UNCLEAR
        assert "Not reported" in item.support_for_judgement

    def test_create_default_risk_of_bias_item_with_outcome_type(self) -> None:
        """Test creating default RiskOfBiasItem with outcome_type."""
        item = create_default_risk_of_bias_item(
            "Test domain", "detection bias", outcome_type="subjective"
        )
        assert item.outcome_type == "subjective"

    def test_create_default_cochrane_risk_of_bias(self) -> None:
        """Test creating default CochraneRiskOfBias."""
        rob = create_default_cochrane_risk_of_bias()
        items = rob.to_list()
        assert len(items) == 9
        # All should be unclear
        for item in items:
            assert item.judgement == ROB_JUDGEMENT_UNCLEAR


# =============================================================================
# Formatter Tests
# =============================================================================

class TestCochraneFormatters:
    """Tests for Cochrane output formatters."""

    def test_format_study_characteristics_markdown(
        self, sample_study_characteristics: CochraneStudyCharacteristics
    ) -> None:
        """Test Markdown formatting of study characteristics."""
        result = format_study_characteristics_markdown(sample_study_characteristics)
        assert "### Smith 2023" in result
        assert "Study characteristics" in result
        assert "Methods" in result
        assert "Participants" in result
        assert "Interventions" in result
        assert "Outcomes" in result
        assert "Notes" in result

    def test_format_risk_of_bias_markdown(
        self, sample_cochrane_rob: CochraneRiskOfBias
    ) -> None:
        """Test Markdown formatting of risk of bias."""
        result = format_risk_of_bias_markdown(sample_cochrane_rob)
        assert "Risk of bias" in result
        assert "Random sequence generation" in result
        assert "Low risk" in result
        assert "Support for judgement" in result

    def test_format_complete_assessment_markdown(
        self, sample_assessment: CochraneStudyAssessment
    ) -> None:
        """Test complete assessment Markdown formatting."""
        result = format_complete_assessment_markdown(sample_assessment)
        assert "Smith 2023" in result
        assert "Study characteristics" in result
        assert "Risk of bias" in result
        assert "8.5" in result  # Quality score

    def test_format_multiple_assessments_markdown(
        self, sample_assessment: CochraneStudyAssessment
    ) -> None:
        """Test multiple assessments Markdown formatting."""
        result = format_multiple_assessments_markdown(
            [sample_assessment],
            title="Test title"
        )
        assert "## Test title" in result
        assert "Smith 2023" in result

    def test_format_risk_of_bias_summary_markdown(
        self, sample_assessment: CochraneStudyAssessment
    ) -> None:
        """Test risk of bias summary Markdown formatting."""
        result = format_risk_of_bias_summary_markdown([sample_assessment])
        assert "Risk of Bias Summary" in result
        assert "+" in result  # Low risk symbol
        assert "Legend" in result

    def test_format_study_characteristics_html(
        self, sample_study_characteristics: CochraneStudyCharacteristics
    ) -> None:
        """Test HTML formatting of study characteristics."""
        result = format_study_characteristics_html(sample_study_characteristics)
        assert "<table" in result
        assert "Smith 2023" in result
        assert "cochrane-characteristics" in result

    def test_format_risk_of_bias_html(
        self, sample_cochrane_rob: CochraneRiskOfBias
    ) -> None:
        """Test HTML formatting of risk of bias."""
        result = format_risk_of_bias_html(sample_cochrane_rob)
        assert "<table" in result
        assert "cochrane-risk-of-bias" in result
        assert "judgement-low" in result

    def test_get_cochrane_css(self) -> None:
        """Test CSS generation."""
        css = get_cochrane_css()
        assert "<style>" in css
        assert ".cochrane-characteristics" in css
        assert ".judgement-low" in css
        assert ".judgement-high" in css
        assert ".judgement-unclear" in css


# =============================================================================
# Participants Format Tests
# =============================================================================

class TestCochraneParticipants:
    """Tests for CochraneParticipants formatting."""

    def test_format_for_table(self, sample_participants: CochraneParticipants) -> None:
        """Test participants table formatting."""
        result = sample_participants.format_for_table()
        assert "United States" in result
        assert "200" in result
        assert "intervention" in result

    def test_format_for_table_minimal(self) -> None:
        """Test minimal participants formatting."""
        participants = CochraneParticipants(
            setting="Unknown",
            population="Not reported",
        )
        result = participants.format_for_table()
        assert "Unknown" in result


# =============================================================================
# Notes Format Tests
# =============================================================================

class TestCochraneNotes:
    """Tests for CochraneNotes formatting."""

    def test_format_for_table(self, sample_notes: CochraneNotes) -> None:
        """Test notes table formatting."""
        result = sample_notes.format_for_table()
        assert "Follow-up" in result
        assert "Funding" in result
        assert "Conflicts" in result
        assert "Ethical approval" in result

    def test_format_for_table_empty(self) -> None:
        """Test empty notes formatting."""
        notes = CochraneNotes()
        result = notes.format_for_table()
        assert "No additional notes" in result


# =============================================================================
# RiskOfBiasJudgement Enum Tests
# =============================================================================

class TestRiskOfBiasJudgement:
    """Tests for RiskOfBiasJudgement enum."""

    def test_from_string_low(self) -> None:
        """Test parsing 'low' variations."""
        assert RiskOfBiasJudgement.from_string("low") == RiskOfBiasJudgement.LOW
        assert RiskOfBiasJudgement.from_string("Low risk") == RiskOfBiasJudgement.LOW
        assert RiskOfBiasJudgement.from_string("LOW_RISK") == RiskOfBiasJudgement.LOW

    def test_from_string_high(self) -> None:
        """Test parsing 'high' variations."""
        assert RiskOfBiasJudgement.from_string("high") == RiskOfBiasJudgement.HIGH
        assert RiskOfBiasJudgement.from_string("High risk") == RiskOfBiasJudgement.HIGH

    def test_from_string_unclear(self) -> None:
        """Test parsing 'unclear' variations."""
        assert RiskOfBiasJudgement.from_string("unclear") == RiskOfBiasJudgement.UNCLEAR
        assert RiskOfBiasJudgement.from_string("Unclear risk") == RiskOfBiasJudgement.UNCLEAR
        assert RiskOfBiasJudgement.from_string("unknown") == RiskOfBiasJudgement.UNCLEAR

    def test_from_string_invalid_defaults_to_unclear(self) -> None:
        """Test that invalid values default to UNCLEAR with warning."""
        result = RiskOfBiasJudgement.from_string("invalid")
        assert result == RiskOfBiasJudgement.UNCLEAR


# =============================================================================
# Constants Tests
# =============================================================================

class TestConstants:
    """Tests for module constants."""

    def test_valid_rob_judgements(self) -> None:
        """Test that valid judgements set is correct."""
        assert ROB_JUDGEMENT_LOW in VALID_ROB_JUDGEMENTS
        assert ROB_JUDGEMENT_HIGH in VALID_ROB_JUDGEMENTS
        assert ROB_JUDGEMENT_UNCLEAR in VALID_ROB_JUDGEMENTS
        assert len(VALID_ROB_JUDGEMENTS) == 3

    def test_judgement_values(self) -> None:
        """Test that judgement constants have correct values."""
        assert ROB_JUDGEMENT_LOW == "Low risk"
        assert ROB_JUDGEMENT_HIGH == "High risk"
        assert ROB_JUDGEMENT_UNCLEAR == "Unclear risk"
