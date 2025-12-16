"""Tests for quality filtering data models."""

import pytest

from bmlibrarian.lite.quality.data_models import (
    StudyDesign,
    QualityTier,
    QualityFilter,
    StudyClassification,
    BiasRisk,
    QualityAssessment,
    DESIGN_TO_TIER,
    DESIGN_TO_SCORE,
    DESIGN_LABELS,
    TIER_LABELS,
)


class TestStudyDesignEnum:
    """Tests for StudyDesign enumeration."""

    def test_all_designs_have_string_values(self) -> None:
        """Test that all study designs have string values."""
        for design in StudyDesign:
            assert isinstance(design.value, str)
            assert len(design.value) > 0

    def test_expected_designs_exist(self) -> None:
        """Test that expected study designs exist."""
        expected = [
            "META_ANALYSIS",
            "SYSTEMATIC_REVIEW",
            "RCT",
            "COHORT_PROSPECTIVE",
            "COHORT_RETROSPECTIVE",
            "CASE_CONTROL",
            "CROSS_SECTIONAL",
            "CASE_REPORT",
            "CASE_SERIES",
            "EDITORIAL",
            "LETTER",
            "COMMENT",
            "GUIDELINE",
            "UNKNOWN",
            "OTHER",
        ]
        for name in expected:
            assert hasattr(StudyDesign, name), f"Missing StudyDesign.{name}"

    def test_designs_are_unique(self) -> None:
        """Test that all study design values are unique."""
        values = [design.value for design in StudyDesign]
        assert len(values) == len(set(values))


class TestQualityTierEnum:
    """Tests for QualityTier enumeration."""

    def test_all_tiers_have_integer_values(self) -> None:
        """Test that all quality tiers have integer values."""
        for tier in QualityTier:
            assert isinstance(tier.value, int)

    def test_tier_ordering(self) -> None:
        """Test that tiers are ordered from lowest to highest."""
        assert QualityTier.UNCLASSIFIED.value == 0
        assert QualityTier.TIER_1_ANECDOTAL.value == 1
        assert QualityTier.TIER_2_OBSERVATIONAL.value == 2
        assert QualityTier.TIER_3_CONTROLLED.value == 3
        assert QualityTier.TIER_4_EXPERIMENTAL.value == 4
        assert QualityTier.TIER_5_SYNTHESIS.value == 5

    def test_tier_comparison(self) -> None:
        """Test that tiers can be compared by value."""
        assert QualityTier.TIER_5_SYNTHESIS.value > QualityTier.TIER_4_EXPERIMENTAL.value
        assert QualityTier.TIER_4_EXPERIMENTAL.value > QualityTier.TIER_3_CONTROLLED.value
        assert QualityTier.TIER_3_CONTROLLED.value > QualityTier.TIER_2_OBSERVATIONAL.value


class TestDesignMappings:
    """Tests for design-to-tier and design-to-score mappings."""

    def test_all_designs_mapped_to_tier(self) -> None:
        """Test that all study designs have a tier mapping."""
        for design in StudyDesign:
            assert design in DESIGN_TO_TIER, f"Missing tier mapping for {design}"

    def test_all_designs_mapped_to_score(self) -> None:
        """Test that all study designs have a score mapping."""
        for design in StudyDesign:
            assert design in DESIGN_TO_SCORE, f"Missing score mapping for {design}"

    def test_all_designs_have_labels(self) -> None:
        """Test that all study designs have labels."""
        for design in StudyDesign:
            assert design in DESIGN_LABELS, f"Missing label for {design}"
            assert isinstance(DESIGN_LABELS[design], str)

    def test_all_tiers_have_labels(self) -> None:
        """Test that all quality tiers have labels."""
        for tier in QualityTier:
            assert tier in TIER_LABELS, f"Missing label for {tier}"
            assert isinstance(TIER_LABELS[tier], str)

    def test_score_ranges(self) -> None:
        """Test that scores are within expected range (0-10)."""
        for design, score in DESIGN_TO_SCORE.items():
            assert 0.0 <= score <= 10.0, f"Invalid score {score} for {design}"

    def test_tier_score_consistency(self) -> None:
        """Test that higher tiers have higher scores."""
        synthesis = DESIGN_TO_SCORE[StudyDesign.META_ANALYSIS]
        experimental = DESIGN_TO_SCORE[StudyDesign.RCT]
        anecdotal = DESIGN_TO_SCORE[StudyDesign.CASE_REPORT]

        assert synthesis > experimental
        assert experimental > anecdotal


class TestQualityFilter:
    """Tests for QualityFilter dataclass."""

    def test_default_values(self) -> None:
        """Test default filter values."""
        qf = QualityFilter()
        assert qf.minimum_tier == QualityTier.UNCLASSIFIED
        assert qf.require_randomization is False
        assert qf.require_blinding is False
        assert qf.minimum_sample_size is None
        assert qf.use_metadata_only is False
        assert qf.use_llm_classification is True
        assert qf.use_detailed_assessment is False

    def test_custom_filter(self) -> None:
        """Test creating custom filter."""
        qf = QualityFilter(
            minimum_tier=QualityTier.TIER_4_EXPERIMENTAL,
            require_randomization=True,
            require_blinding=True,
            minimum_sample_size=100,
        )
        assert qf.minimum_tier == QualityTier.TIER_4_EXPERIMENTAL
        assert qf.require_randomization is True
        assert qf.require_blinding is True
        assert qf.minimum_sample_size == 100


class TestStudyClassification:
    """Tests for StudyClassification dataclass."""

    def test_basic_classification(self) -> None:
        """Test creating basic classification."""
        sc = StudyClassification(
            study_design=StudyDesign.RCT,
            confidence=0.9,
        )
        assert sc.study_design == StudyDesign.RCT
        assert sc.confidence == 0.9
        assert sc.is_randomized is None
        assert sc.is_blinded is None
        assert sc.sample_size is None

    def test_detailed_classification(self) -> None:
        """Test creating detailed classification."""
        sc = StudyClassification(
            study_design=StudyDesign.RCT,
            confidence=0.95,
            is_randomized=True,
            is_blinded="double",
            sample_size=250,
        )
        assert sc.is_randomized is True
        assert sc.is_blinded == "double"
        assert sc.sample_size == 250


class TestBiasRisk:
    """Tests for BiasRisk dataclass."""

    def test_default_values(self) -> None:
        """Test default bias risk values."""
        br = BiasRisk()
        assert br.selection == "unclear"
        assert br.performance == "unclear"
        assert br.detection == "unclear"
        assert br.attrition == "unclear"
        assert br.reporting == "unclear"

    def test_custom_risk_assessment(self) -> None:
        """Test creating custom risk assessment."""
        br = BiasRisk(
            selection="low",
            performance="high",
            detection="unclear",
            attrition="low",
            reporting="low",
        )
        assert br.selection == "low"
        assert br.performance == "high"
        assert br.detection == "unclear"


class TestQualityAssessment:
    """Tests for QualityAssessment dataclass."""

    def test_basic_assessment(self) -> None:
        """Test creating basic assessment."""
        qa = QualityAssessment(
            assessment_tier=1,
            extraction_method="metadata",
            study_design=StudyDesign.RCT,
            quality_tier=QualityTier.TIER_4_EXPERIMENTAL,
            quality_score=8.0,
            confidence=0.95,
        )
        assert qa.assessment_tier == 1
        assert qa.extraction_method == "metadata"
        assert qa.study_design == StudyDesign.RCT
        assert qa.quality_tier == QualityTier.TIER_4_EXPERIMENTAL
        assert qa.quality_score == 8.0
        assert qa.confidence == 0.95

    def test_full_assessment(self) -> None:
        """Test creating full assessment with all fields."""
        bias_risk = BiasRisk(
            selection="low",
            performance="low",
        )

        qa = QualityAssessment(
            assessment_tier=3,
            extraction_method="llm_sonnet",
            study_design=StudyDesign.RCT,
            quality_tier=QualityTier.TIER_4_EXPERIMENTAL,
            quality_score=8.5,
            confidence=0.9,
            bias_risk=bias_risk,
            strengths=["Double-blind", "Large sample size"],
            limitations=["Single center"],
            evidence_level="1b",
        )
        assert qa.bias_risk is not None
        assert len(qa.strengths) == 2
        assert len(qa.limitations) == 1
        assert qa.evidence_level == "1b"

    def test_from_metadata_factory(self) -> None:
        """Test from_metadata factory method."""
        qa = QualityAssessment.from_metadata(
            study_design=StudyDesign.SYSTEMATIC_REVIEW,
            confidence=0.95,
        )
        assert qa.assessment_tier == 1
        assert qa.extraction_method == "metadata"
        assert qa.study_design == StudyDesign.SYSTEMATIC_REVIEW
        assert qa.quality_tier == QualityTier.TIER_5_SYNTHESIS
        assert qa.confidence == 0.95

    def test_from_classification_factory(self) -> None:
        """Test from_classification factory method."""
        classification = StudyClassification(
            study_design=StudyDesign.CASE_CONTROL,
            confidence=0.85,
        )
        qa = QualityAssessment.from_classification(classification)

        assert qa.assessment_tier == 2
        assert qa.extraction_method == "llm_haiku"
        assert qa.study_design == StudyDesign.CASE_CONTROL
        assert qa.quality_tier == QualityTier.TIER_3_CONTROLLED
        assert qa.confidence == 0.85

    def test_unclassified_factory(self) -> None:
        """Test unclassified factory method."""
        qa = QualityAssessment.unclassified()

        assert qa.assessment_tier == 0
        assert qa.extraction_method == "none"
        assert qa.study_design == StudyDesign.UNKNOWN
        assert qa.quality_tier == QualityTier.UNCLASSIFIED
        assert qa.quality_score == 0.0
        assert qa.confidence == 0.0

    def test_to_dict(self) -> None:
        """Test serialization."""
        qa = QualityAssessment(
            assessment_tier=2,
            extraction_method="llm_haiku",
            study_design=StudyDesign.COHORT_PROSPECTIVE,
            quality_tier=QualityTier.TIER_3_CONTROLLED,
            quality_score=7.0,
            confidence=0.85,
            strengths=["Large sample"],
            limitations=["Observational design"],
        )
        data = qa.to_dict()

        assert data["assessment_tier"] == qa.assessment_tier
        assert data["extraction_method"] == qa.extraction_method
        assert data["study_design"] == qa.study_design.value
        assert data["quality_tier"] == qa.quality_tier.value

    def test_passes_filter_by_tier(self) -> None:
        """Test passes_filter checks tier requirement."""
        qa = QualityAssessment(
            assessment_tier=1,
            extraction_method="metadata",
            study_design=StudyDesign.RCT,
            quality_tier=QualityTier.TIER_4_EXPERIMENTAL,
            quality_score=8.0,
            confidence=0.95,
        )

        # Should pass tier 4 requirement
        filter_4 = QualityFilter(minimum_tier=QualityTier.TIER_4_EXPERIMENTAL)
        assert qa.passes_filter(filter_4)

        # Should fail tier 5 requirement
        filter_5 = QualityFilter(minimum_tier=QualityTier.TIER_5_SYNTHESIS)
        assert not qa.passes_filter(filter_5)

    def test_passes_filter_randomization(self) -> None:
        """Test passes_filter checks randomization requirement."""
        qa_randomized = QualityAssessment(
            assessment_tier=1,
            extraction_method="metadata",
            study_design=StudyDesign.RCT,
            quality_tier=QualityTier.TIER_4_EXPERIMENTAL,
            quality_score=8.0,
            confidence=0.95,
            is_randomized=True,
        )
        qa_not_randomized = QualityAssessment(
            assessment_tier=1,
            extraction_method="metadata",
            study_design=StudyDesign.COHORT_PROSPECTIVE,
            quality_tier=QualityTier.TIER_3_CONTROLLED,
            quality_score=6.0,
            confidence=0.85,
            is_randomized=False,
        )

        filter_require_random = QualityFilter(require_randomization=True)
        assert qa_randomized.passes_filter(filter_require_random)
        assert not qa_not_randomized.passes_filter(filter_require_random)

    def test_passes_filter_blinding(self) -> None:
        """Test passes_filter checks blinding requirement."""
        qa_blinded = QualityAssessment(
            assessment_tier=1,
            extraction_method="metadata",
            study_design=StudyDesign.RCT,
            quality_tier=QualityTier.TIER_4_EXPERIMENTAL,
            quality_score=8.0,
            confidence=0.95,
            is_blinded="double",
        )
        qa_not_blinded = QualityAssessment(
            assessment_tier=1,
            extraction_method="metadata",
            study_design=StudyDesign.RCT,
            quality_tier=QualityTier.TIER_4_EXPERIMENTAL,
            quality_score=7.0,
            confidence=0.85,
            is_blinded=None,
        )

        filter_require_blind = QualityFilter(require_blinding=True)
        assert qa_blinded.passes_filter(filter_require_blind)
        assert not qa_not_blinded.passes_filter(filter_require_blind)

    def test_passes_filter_sample_size(self) -> None:
        """Test passes_filter checks sample size requirement."""
        qa_large = QualityAssessment(
            assessment_tier=1,
            extraction_method="metadata",
            study_design=StudyDesign.RCT,
            quality_tier=QualityTier.TIER_4_EXPERIMENTAL,
            quality_score=8.0,
            confidence=0.95,
            sample_size=500,
        )
        qa_small = QualityAssessment(
            assessment_tier=1,
            extraction_method="metadata",
            study_design=StudyDesign.RCT,
            quality_tier=QualityTier.TIER_4_EXPERIMENTAL,
            quality_score=7.0,
            confidence=0.85,
            sample_size=50,
        )

        filter_min_100 = QualityFilter(minimum_sample_size=100)
        assert qa_large.passes_filter(filter_min_100)
        assert not qa_small.passes_filter(filter_min_100)
