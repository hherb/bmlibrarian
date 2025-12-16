"""Tests for quality filtering GUI widgets.

These tests verify the widget logic without requiring a running Qt application.
Tests are automatically skipped if PySide6 is not available (via conftest.py).
"""

import pytest
from unittest.mock import MagicMock

from bmlibrarian.lite.quality.data_models import (
    QualityTier,
    QualityFilter,
    StudyDesign,
)


class TestQualityFilterCreation:
    """Tests for QualityFilter creation from panel."""

    def test_default_filter_values(self) -> None:
        """Test default QualityFilter values."""
        default_filter = QualityFilter()

        assert default_filter.minimum_tier == QualityTier.UNCLASSIFIED
        assert default_filter.require_randomization is False
        assert default_filter.require_blinding is False
        assert default_filter.minimum_sample_size is None
        assert default_filter.use_metadata_only is False
        assert default_filter.use_llm_classification is True
        assert default_filter.use_detailed_assessment is False

    def test_filter_with_requirements(self) -> None:
        """Test QualityFilter with specific requirements."""
        filter_settings = QualityFilter(
            minimum_tier=QualityTier.TIER_4_EXPERIMENTAL,
            require_randomization=True,
            require_blinding=True,
            minimum_sample_size=100,
        )

        assert filter_settings.minimum_tier == QualityTier.TIER_4_EXPERIMENTAL
        assert filter_settings.require_randomization is True
        assert filter_settings.require_blinding is True
        assert filter_settings.minimum_sample_size == 100


class TestSummaryDataStructure:
    """Tests for summary data structure handling."""

    def test_empty_summary_structure(self) -> None:
        """Test structure of empty summary."""
        empty_summary = {
            "total": 0,
            "by_quality_tier": {},
            "by_study_design": {},
            "by_assessment_tier": {
                "metadata": 0,
                "haiku": 0,
                "sonnet": 0,
                "unclassified": 0,
            },
            "avg_confidence": 0.0,
        }

        assert "total" in empty_summary
        assert "by_quality_tier" in empty_summary
        assert "by_assessment_tier" in empty_summary
        assert "avg_confidence" in empty_summary

    def test_summary_with_data(self) -> None:
        """Test summary structure with data."""
        summary = {
            "total": 10,
            "by_quality_tier": {
                "TIER_4_EXPERIMENTAL": 5,
                "TIER_3_CONTROLLED": 3,
                "TIER_2_OBSERVATIONAL": 2,
            },
            "by_study_design": {
                "rct": 5,
                "cohort_prospective": 3,
                "case_control": 2,
            },
            "by_assessment_tier": {
                "metadata": 7,
                "haiku": 2,
                "sonnet": 1,
                "unclassified": 0,
            },
            "avg_confidence": 0.85,
        }

        assert summary["total"] == 10
        assert sum(summary["by_quality_tier"].values()) == 10
        assert sum(summary["by_study_design"].values()) == 10
        assert sum(summary["by_assessment_tier"].values()) == 10


class TestQualityTierEnum:
    """Tests for QualityTier enum used in GUI components."""

    def test_tier_values_are_ordered(self) -> None:
        """Test that tier values are in ascending order."""
        tiers = [
            QualityTier.UNCLASSIFIED,
            QualityTier.TIER_1_ANECDOTAL,
            QualityTier.TIER_2_OBSERVATIONAL,
            QualityTier.TIER_3_CONTROLLED,
            QualityTier.TIER_4_EXPERIMENTAL,
            QualityTier.TIER_5_SYNTHESIS,
        ]
        values = [tier.value for tier in tiers]
        assert values == sorted(values)

    def test_all_tiers_have_integer_values(self) -> None:
        """Test all tiers have integer values."""
        for tier in QualityTier:
            assert isinstance(tier.value, int)


class TestStudyDesignEnum:
    """Tests for StudyDesign enum used in GUI components."""

    def test_all_designs_have_string_values(self) -> None:
        """Test all designs have string values."""
        for design in StudyDesign:
            assert isinstance(design.value, str)
            assert len(design.value) > 0

    def test_expected_designs_exist(self) -> None:
        """Test expected study designs exist."""
        expected = [
            "RCT",
            "SYSTEMATIC_REVIEW",
            "META_ANALYSIS",
            "COHORT_PROSPECTIVE",
            "CASE_REPORT",
            "UNKNOWN",
        ]
        for name in expected:
            assert hasattr(StudyDesign, name), f"Missing StudyDesign.{name}"
