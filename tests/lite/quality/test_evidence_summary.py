"""Tests for evidence summary generator."""

import pytest
from collections import Counter

from bmlibrarian.lite.quality.data_models import (
    QualityTier,
    StudyDesign,
    QualityAssessment,
)
from bmlibrarian.lite.quality.evidence_summary import (
    EvidenceSummaryGenerator,
    TIER_DESCRIPTIONS,
    DESIGN_LABELS,
    HIGH_QUALITY_TIER,
    SMALL_SAMPLE_SIZE_THRESHOLD,
    LOW_QUALITY_WARNING_THRESHOLD,
    UNCLASSIFIED_WARNING_THRESHOLD,
)


class TestEvidenceSummaryGeneratorConstants:
    """Tests for evidence summary generator constants."""

    def test_tier_descriptions_complete(self) -> None:
        """All quality tiers should have descriptions."""
        for tier in QualityTier:
            assert tier in TIER_DESCRIPTIONS, f"Missing description for {tier}"

    def test_design_labels_complete(self) -> None:
        """All study designs should have labels."""
        for design in StudyDesign:
            assert design in DESIGN_LABELS, f"Missing label for {design}"

    def test_high_quality_tier_valid(self) -> None:
        """High quality tier should be a valid QualityTier."""
        assert HIGH_QUALITY_TIER in QualityTier
        # Should be at least experimental level
        assert HIGH_QUALITY_TIER.value >= QualityTier.TIER_4_EXPERIMENTAL.value

    def test_small_sample_size_threshold_reasonable(self) -> None:
        """Small sample size threshold should be reasonable."""
        assert SMALL_SAMPLE_SIZE_THRESHOLD > 0
        assert SMALL_SAMPLE_SIZE_THRESHOLD < 200

    def test_low_quality_warning_threshold_valid(self) -> None:
        """Low quality warning threshold should be between 0 and 1."""
        assert 0 < LOW_QUALITY_WARNING_THRESHOLD <= 1

    def test_unclassified_warning_threshold_valid(self) -> None:
        """Unclassified warning threshold should be between 0 and 1."""
        assert 0 < UNCLASSIFIED_WARNING_THRESHOLD <= 1


class TestEvidenceSummaryGeneratorBasic:
    """Basic tests for EvidenceSummaryGenerator."""

    @pytest.fixture
    def generator(self) -> EvidenceSummaryGenerator:
        """Create a generator instance."""
        return EvidenceSummaryGenerator()

    def test_empty_assessments_returns_empty_string(
        self, generator: EvidenceSummaryGenerator
    ) -> None:
        """Empty assessment list should return empty string."""
        result = generator.generate_summary([])
        assert result == ""

    def test_summary_has_evidence_summary_heading(
        self, generator: EvidenceSummaryGenerator
    ) -> None:
        """Summary should include Evidence Summary heading."""
        assessment = QualityAssessment(
            assessment_tier=2,
            extraction_method="llm_haiku",
            study_design=StudyDesign.RCT,
            quality_tier=QualityTier.TIER_4_EXPERIMENTAL,
            quality_score=8.0,
            confidence=0.9,
        )
        result = generator.generate_summary([assessment])
        assert "## Evidence Summary" in result

    def test_summary_includes_study_count(
        self, generator: EvidenceSummaryGenerator
    ) -> None:
        """Summary should include total study count."""
        assessments = [
            QualityAssessment(
                assessment_tier=2,
                extraction_method="llm_haiku",
                study_design=StudyDesign.RCT,
                quality_tier=QualityTier.TIER_4_EXPERIMENTAL,
                quality_score=8.0,
                confidence=0.9,
            )
            for _ in range(3)
        ]
        result = generator.generate_summary(assessments)
        assert "3 studies" in result

    def test_single_study_uses_singular(
        self, generator: EvidenceSummaryGenerator
    ) -> None:
        """Single study should use singular form."""
        assessment = QualityAssessment(
            assessment_tier=2,
            extraction_method="llm_haiku",
            study_design=StudyDesign.RCT,
            quality_tier=QualityTier.TIER_4_EXPERIMENTAL,
            quality_score=8.0,
            confidence=0.9,
        )
        result = generator.generate_summary([assessment])
        assert "1 study" in result


class TestEvidenceSummaryTierBreakdown:
    """Tests for tier breakdown in evidence summary."""

    @pytest.fixture
    def generator(self) -> EvidenceSummaryGenerator:
        """Create a generator instance."""
        return EvidenceSummaryGenerator()

    def test_rcts_listed_separately(
        self, generator: EvidenceSummaryGenerator
    ) -> None:
        """RCTs should be listed in the breakdown."""
        assessments = [
            QualityAssessment(
                assessment_tier=2,
                extraction_method="llm_haiku",
                study_design=StudyDesign.RCT,
                quality_tier=QualityTier.TIER_4_EXPERIMENTAL,
                quality_score=8.0,
                confidence=0.9,
            )
            for _ in range(2)
        ]
        result = generator.generate_summary(assessments)
        assert "**2**" in result

    def test_mixed_tiers_listed(
        self, generator: EvidenceSummaryGenerator
    ) -> None:
        """Mixed quality tiers should all be listed."""
        assessments = [
            QualityAssessment(
                assessment_tier=2,
                extraction_method="llm_haiku",
                study_design=StudyDesign.RCT,
                quality_tier=QualityTier.TIER_4_EXPERIMENTAL,
                quality_score=8.0,
                confidence=0.9,
            ),
            QualityAssessment(
                assessment_tier=2,
                extraction_method="llm_haiku",
                study_design=StudyDesign.COHORT_PROSPECTIVE,
                quality_tier=QualityTier.TIER_3_CONTROLLED,
                quality_score=6.0,
                confidence=0.85,
            ),
            QualityAssessment(
                assessment_tier=2,
                extraction_method="llm_haiku",
                study_design=StudyDesign.CASE_REPORT,
                quality_tier=QualityTier.TIER_1_ANECDOTAL,
                quality_score=3.0,
                confidence=0.7,
            ),
        ]
        result = generator.generate_summary(assessments)
        # Should have bullets for each tier
        assert result.count("- **1**") >= 2


class TestEvidenceSummaryQualityMetrics:
    """Tests for quality metrics in evidence summary."""

    @pytest.fixture
    def generator(self) -> EvidenceSummaryGenerator:
        """Create a generator instance."""
        return EvidenceSummaryGenerator()

    def test_average_quality_score_included(
        self, generator: EvidenceSummaryGenerator
    ) -> None:
        """Average quality score should be shown."""
        assessments = [
            QualityAssessment(
                assessment_tier=2,
                extraction_method="llm_haiku",
                study_design=StudyDesign.RCT,
                quality_tier=QualityTier.TIER_4_EXPERIMENTAL,
                quality_score=8.0,
                confidence=0.9,
            ),
            QualityAssessment(
                assessment_tier=2,
                extraction_method="llm_haiku",
                study_design=StudyDesign.RCT,
                quality_tier=QualityTier.TIER_4_EXPERIMENTAL,
                quality_score=6.0,
                confidence=0.9,
            ),
        ]
        result = generator.generate_summary(assessments)
        # Average is 7.0
        assert "7.0/10" in result

    def test_high_quality_percentage_included(
        self, generator: EvidenceSummaryGenerator
    ) -> None:
        """High-quality evidence percentage should be shown."""
        assessments = [
            QualityAssessment(
                assessment_tier=2,
                extraction_method="llm_haiku",
                study_design=StudyDesign.RCT,
                quality_tier=QualityTier.TIER_4_EXPERIMENTAL,
                quality_score=8.0,
                confidence=0.9,
            ),
            QualityAssessment(
                assessment_tier=2,
                extraction_method="llm_haiku",
                study_design=StudyDesign.CASE_REPORT,
                quality_tier=QualityTier.TIER_1_ANECDOTAL,
                quality_score=3.0,
                confidence=0.7,
            ),
        ]
        result = generator.generate_summary(assessments)
        # 50% high quality
        assert "50%" in result


class TestEvidenceSummaryQualityNotes:
    """Tests for quality notes in evidence summary."""

    @pytest.fixture
    def generator(self) -> EvidenceSummaryGenerator:
        """Create a generator instance."""
        return EvidenceSummaryGenerator()

    def test_no_rcts_note_when_missing(
        self, generator: EvidenceSummaryGenerator
    ) -> None:
        """Should note when no RCTs are available."""
        assessments = [
            QualityAssessment(
                assessment_tier=2,
                extraction_method="llm_haiku",
                study_design=StudyDesign.COHORT_PROSPECTIVE,
                quality_tier=QualityTier.TIER_3_CONTROLLED,
                quality_score=6.0,
                confidence=0.85,
            ),
        ]
        result = generator.generate_summary(assessments, include_quality_notes=True)
        assert "No systematic reviews or RCTs" in result

    def test_notes_excluded_when_disabled(
        self, generator: EvidenceSummaryGenerator
    ) -> None:
        """Quality notes should be excluded when disabled."""
        assessments = [
            QualityAssessment(
                assessment_tier=2,
                extraction_method="llm_haiku",
                study_design=StudyDesign.CASE_REPORT,
                quality_tier=QualityTier.TIER_1_ANECDOTAL,
                quality_score=3.0,
                confidence=0.7,
            ),
        ]
        result = generator.generate_summary(assessments, include_quality_notes=False)
        assert "Quality Considerations" not in result

    def test_small_sample_warning_when_median_small(
        self, generator: EvidenceSummaryGenerator
    ) -> None:
        """Should warn about small median sample sizes."""
        assessments = [
            QualityAssessment(
                assessment_tier=2,
                extraction_method="llm_haiku",
                study_design=StudyDesign.RCT,
                quality_tier=QualityTier.TIER_4_EXPERIMENTAL,
                quality_score=8.0,
                confidence=0.9,
                sample_size=20,
            ),
            QualityAssessment(
                assessment_tier=2,
                extraction_method="llm_haiku",
                study_design=StudyDesign.RCT,
                quality_tier=QualityTier.TIER_4_EXPERIMENTAL,
                quality_score=7.0,
                confidence=0.85,
                sample_size=30,
            ),
        ]
        result = generator.generate_summary(assessments, include_quality_notes=True)
        assert "small samples" in result.lower() or "median sample size" in result.lower()


class TestStudyTableGeneration:
    """Tests for study table generation."""

    @pytest.fixture
    def generator(self) -> EvidenceSummaryGenerator:
        """Create a generator instance."""
        return EvidenceSummaryGenerator()

    def test_empty_returns_empty_string(
        self, generator: EvidenceSummaryGenerator
    ) -> None:
        """Empty list should return empty string."""
        result = generator.generate_study_table([])
        assert result == ""

    def test_table_has_header_row(
        self, generator: EvidenceSummaryGenerator
    ) -> None:
        """Table should have proper header row."""
        assessments = [
            QualityAssessment(
                assessment_tier=2,
                extraction_method="llm_haiku",
                study_design=StudyDesign.RCT,
                quality_tier=QualityTier.TIER_4_EXPERIMENTAL,
                quality_score=8.0,
                confidence=0.9,
            ),
        ]
        result = generator.generate_study_table(assessments)
        assert "| Study | Design | N | Quality | Confidence |" in result

    def test_table_includes_study_data(
        self, generator: EvidenceSummaryGenerator
    ) -> None:
        """Table should include study data."""
        assessments = [
            QualityAssessment(
                assessment_tier=2,
                extraction_method="llm_haiku",
                study_design=StudyDesign.RCT,
                quality_tier=QualityTier.TIER_4_EXPERIMENTAL,
                quality_score=8.0,
                confidence=0.9,
                sample_size=100,
            ),
        ]
        result = generator.generate_study_table(assessments)
        assert "8.0/10" in result
        assert "100" in result
        assert "90%" in result


class TestBriefSummary:
    """Tests for brief summary generation."""

    @pytest.fixture
    def generator(self) -> EvidenceSummaryGenerator:
        """Create a generator instance."""
        return EvidenceSummaryGenerator()

    def test_empty_returns_no_studies(
        self, generator: EvidenceSummaryGenerator
    ) -> None:
        """Empty list should return 'No studies' message."""
        result = generator.generate_brief_summary([])
        assert "No studies" in result

    def test_brief_summary_format(
        self, generator: EvidenceSummaryGenerator
    ) -> None:
        """Brief summary should follow expected format."""
        assessments = [
            QualityAssessment(
                assessment_tier=2,
                extraction_method="llm_haiku",
                study_design=StudyDesign.RCT,
                quality_tier=QualityTier.TIER_4_EXPERIMENTAL,
                quality_score=8.0,
                confidence=0.9,
            ),
            QualityAssessment(
                assessment_tier=2,
                extraction_method="llm_haiku",
                study_design=StudyDesign.SYSTEMATIC_REVIEW,
                quality_tier=QualityTier.TIER_5_SYNTHESIS,
                quality_score=9.0,
                confidence=0.95,
            ),
        ]
        result = generator.generate_brief_summary(assessments)
        assert "2 studies" in result
        # Should include breakdown
        assert "(" in result and ")" in result
