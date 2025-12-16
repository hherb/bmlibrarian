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
        assert QualityTier.TIER_5_SYSTEMATIC.value == 5

    def test_tier_comparison(self) -> None:
        """Test that tiers can be compared by value."""
        assert QualityTier.TIER_5_SYSTEMATIC.value > QualityTier.TIER_4_EXPERIMENTAL.value
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
        """Test that scores are within expected range."""
        for design, score in DESIGN_TO_SCORE.items():
            assert 0.0 <= score <= 1.0, f"Invalid score {score} for {design}"

    def test_tier_score_consistency(self) -> None:
        """Test that higher tiers have higher scores."""
        systematic = DESIGN_TO_SCORE[StudyDesign.META_ANALYSIS]
        experimental = DESIGN_TO_SCORE[StudyDesign.RCT]
        anecdotal = DESIGN_TO_SCORE[StudyDesign.CASE_REPORT]

        assert systematic > experimental
        assert experimental > anecdotal


class TestQualityFilter:
    """Tests for QualityFilter dataclass."""

    def test_default_values(self) -> None:
        """Test default filter values."""
        qf = QualityFilter()
        assert qf.minimum_tier == QualityTier.UNCLASSIFIED
        assert qf.minimum_score == 0.0
        assert qf.require_randomization is False
        assert qf.require_blinding is False
        assert qf.minimum_sample_size is None
        assert qf.exclude_designs == []

    def test_custom_filter(self) -> None:
        """Test creating custom filter."""
        qf = QualityFilter(
            minimum_tier=QualityTier.TIER_4_EXPERIMENTAL,
            minimum_score=0.7,
            require_randomization=True,
            require_blinding=True,
            minimum_sample_size=100,
            exclude_designs=[StudyDesign.CASE_REPORT, StudyDesign.EDITORIAL],
        )
        assert qf.minimum_tier == QualityTier.TIER_4_EXPERIMENTAL
        assert qf.minimum_score == 0.7
        assert qf.require_randomization is True
        assert qf.require_blinding is True
        assert qf.minimum_sample_size == 100
        assert len(qf.exclude_designs) == 2

    def test_to_dict_and_from_dict(self) -> None:
        """Test serialization and deserialization."""
        qf = QualityFilter(
            minimum_tier=QualityTier.TIER_3_CONTROLLED,
            minimum_score=0.5,
            require_blinding=True,
            exclude_designs=[StudyDesign.EDITORIAL],
        )
        data = qf.to_dict()
        restored = QualityFilter.from_dict(data)

        assert restored.minimum_tier == qf.minimum_tier
        assert restored.minimum_score == qf.minimum_score
        assert restored.require_blinding == qf.require_blinding
        assert restored.exclude_designs == qf.exclude_designs


class TestStudyClassification:
    """Tests for StudyClassification dataclass."""

    def test_basic_classification(self) -> None:
        """Test creating basic classification."""
        sc = StudyClassification(
            study_design=StudyDesign.RCT,
            confidence=0.9,
            extraction_method="metadata",
        )
        assert sc.study_design == StudyDesign.RCT
        assert sc.confidence == 0.9
        assert sc.extraction_method == "metadata"
        assert sc.is_randomized is None
        assert sc.is_blinded is None
        assert sc.sample_size is None

    def test_detailed_classification(self) -> None:
        """Test creating detailed classification."""
        sc = StudyClassification(
            study_design=StudyDesign.RCT,
            confidence=0.95,
            extraction_method="llm_haiku",
            is_randomized=True,
            is_blinded=True,
            blinding_type="double",
            is_controlled=True,
            sample_size=250,
            extraction_details=["Phase III RCT", "Double-blind design"],
        )
        assert sc.is_randomized is True
        assert sc.is_blinded is True
        assert sc.blinding_type == "double"
        assert sc.sample_size == 250
        assert len(sc.extraction_details) == 2

    def test_to_dict_and_from_dict(self) -> None:
        """Test serialization and deserialization."""
        sc = StudyClassification(
            study_design=StudyDesign.COHORT_PROSPECTIVE,
            confidence=0.85,
            extraction_method="llm_sonnet",
            sample_size=500,
            extraction_details=["Large prospective cohort"],
        )
        data = sc.to_dict()
        restored = StudyClassification.from_dict(data)

        assert restored.study_design == sc.study_design
        assert restored.confidence == sc.confidence
        assert restored.extraction_method == sc.extraction_method
        assert restored.sample_size == sc.sample_size


class TestBiasRisk:
    """Tests for BiasRisk dataclass."""

    def test_default_values(self) -> None:
        """Test default bias risk values."""
        br = BiasRisk()
        assert br.selection_bias is None
        assert br.performance_bias is None
        assert br.detection_bias is None
        assert br.attrition_bias is None
        assert br.reporting_bias is None
        assert br.overall_risk is None
        assert br.notes == []

    def test_custom_risk_assessment(self) -> None:
        """Test creating custom risk assessment."""
        br = BiasRisk(
            selection_bias="low",
            performance_bias="high",
            detection_bias="unclear",
            attrition_bias="low",
            reporting_bias="low",
            overall_risk="moderate",
            notes=["Open-label study", "Incomplete blinding"],
        )
        assert br.selection_bias == "low"
        assert br.performance_bias == "high"
        assert br.overall_risk == "moderate"
        assert len(br.notes) == 2

    def test_to_dict_and_from_dict(self) -> None:
        """Test serialization and deserialization."""
        br = BiasRisk(
            selection_bias="low",
            overall_risk="low",
            notes=["Well-designed RCT"],
        )
        data = br.to_dict()
        restored = BiasRisk.from_dict(data)

        assert restored.selection_bias == br.selection_bias
        assert restored.overall_risk == br.overall_risk
        assert restored.notes == br.notes


class TestQualityAssessment:
    """Tests for QualityAssessment dataclass."""

    def test_basic_assessment(self) -> None:
        """Test creating basic assessment."""
        qa = QualityAssessment(
            assessment_tier=1,
            extraction_method="metadata",
            study_design=StudyDesign.RCT,
            quality_tier=QualityTier.TIER_4_EXPERIMENTAL,
            quality_score=0.8,
            confidence=0.95,
        )
        assert qa.assessment_tier == 1
        assert qa.extraction_method == "metadata"
        assert qa.study_design == StudyDesign.RCT
        assert qa.quality_tier == QualityTier.TIER_4_EXPERIMENTAL
        assert qa.quality_score == 0.8
        assert qa.confidence == 0.95

    def test_full_assessment(self) -> None:
        """Test creating full assessment with all fields."""
        classification = StudyClassification(
            study_design=StudyDesign.RCT,
            confidence=0.9,
            extraction_method="llm_sonnet",
            is_randomized=True,
            is_blinded=True,
        )
        bias_risk = BiasRisk(
            selection_bias="low",
            overall_risk="low",
        )

        qa = QualityAssessment(
            assessment_tier=3,
            extraction_method="llm_sonnet",
            study_design=StudyDesign.RCT,
            quality_tier=QualityTier.TIER_4_EXPERIMENTAL,
            quality_score=0.85,
            confidence=0.9,
            classification=classification,
            bias_risk=bias_risk,
            strengths=["Double-blind", "Large sample size"],
            limitations=["Single center"],
            evidence_level="1b",
        )
        assert qa.classification is not None
        assert qa.bias_risk is not None
        assert len(qa.strengths) == 2
        assert len(qa.limitations) == 1
        assert qa.evidence_level == "1b"

    def test_from_metadata_factory(self) -> None:
        """Test from_metadata factory method."""
        qa = QualityAssessment.from_metadata(
            study_design=StudyDesign.SYSTEMATIC_REVIEW,
            confidence=0.95,
            extraction_details=["Matched publication type: Systematic Review"],
        )
        assert qa.assessment_tier == 1
        assert qa.extraction_method == "metadata"
        assert qa.study_design == StudyDesign.SYSTEMATIC_REVIEW
        assert qa.quality_tier == QualityTier.TIER_5_SYSTEMATIC
        assert qa.confidence == 0.95

    def test_from_classification_factory(self) -> None:
        """Test from_classification factory method."""
        classification = StudyClassification(
            study_design=StudyDesign.CASE_CONTROL,
            confidence=0.85,
            extraction_method="llm_haiku",
            is_controlled=True,
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

    def test_to_dict_and_from_dict(self) -> None:
        """Test serialization and deserialization."""
        qa = QualityAssessment(
            assessment_tier=2,
            extraction_method="llm_haiku",
            study_design=StudyDesign.COHORT_PROSPECTIVE,
            quality_tier=QualityTier.TIER_3_CONTROLLED,
            quality_score=0.7,
            confidence=0.85,
            strengths=["Large sample"],
            limitations=["Observational design"],
        )
        data = qa.to_dict()
        restored = QualityAssessment.from_dict(data)

        assert restored.assessment_tier == qa.assessment_tier
        assert restored.extraction_method == qa.extraction_method
        assert restored.study_design == qa.study_design
        assert restored.quality_tier == qa.quality_tier
        assert restored.quality_score == qa.quality_score
        assert restored.confidence == qa.confidence
        assert restored.strengths == qa.strengths
        assert restored.limitations == qa.limitations

    def test_meets_filter_by_tier(self) -> None:
        """Test meets_filter checks tier requirement."""
        qa = QualityAssessment(
            assessment_tier=1,
            extraction_method="metadata",
            study_design=StudyDesign.RCT,
            quality_tier=QualityTier.TIER_4_EXPERIMENTAL,
            quality_score=0.8,
            confidence=0.95,
        )

        # Should pass tier 4 requirement
        filter_4 = QualityFilter(minimum_tier=QualityTier.TIER_4_EXPERIMENTAL)
        assert qa.meets_filter(filter_4)

        # Should fail tier 5 requirement
        filter_5 = QualityFilter(minimum_tier=QualityTier.TIER_5_SYSTEMATIC)
        assert not qa.meets_filter(filter_5)

    def test_meets_filter_by_score(self) -> None:
        """Test meets_filter checks score requirement."""
        qa = QualityAssessment(
            assessment_tier=1,
            extraction_method="metadata",
            study_design=StudyDesign.COHORT_PROSPECTIVE,
            quality_tier=QualityTier.TIER_3_CONTROLLED,
            quality_score=0.6,
            confidence=0.85,
        )

        # Should pass 0.5 threshold
        filter_low = QualityFilter(minimum_score=0.5)
        assert qa.meets_filter(filter_low)

        # Should fail 0.7 threshold
        filter_high = QualityFilter(minimum_score=0.7)
        assert not qa.meets_filter(filter_high)

    def test_meets_filter_excluded_designs(self) -> None:
        """Test meets_filter checks excluded designs."""
        qa = QualityAssessment(
            assessment_tier=1,
            extraction_method="metadata",
            study_design=StudyDesign.EDITORIAL,
            quality_tier=QualityTier.TIER_1_ANECDOTAL,
            quality_score=0.1,
            confidence=0.95,
        )

        # Should pass if not excluded
        filter_no_exclude = QualityFilter()
        assert qa.meets_filter(filter_no_exclude)

        # Should fail if excluded
        filter_exclude = QualityFilter(
            exclude_designs=[StudyDesign.EDITORIAL, StudyDesign.LETTER]
        )
        assert not qa.meets_filter(filter_exclude)
