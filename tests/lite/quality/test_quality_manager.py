"""Tests for quality manager orchestration."""

import pytest
from unittest.mock import MagicMock, patch

from bmlibrarian.lite.quality.quality_manager import QualityManager
from bmlibrarian.lite.quality.data_models import (
    StudyDesign,
    QualityTier,
    QualityFilter,
    QualityAssessment,
    StudyClassification,
)


class TestQualityManagerInit:
    """Tests for QualityManager initialization."""

    @pytest.fixture
    def mock_config(self) -> MagicMock:
        """Create mock configuration."""
        config = MagicMock()
        config.llm = MagicMock()
        config.llm.provider = "anthropic"
        config.llm.temperature = 0.3
        config.llm.max_tokens = 4096
        return config

    def test_initialization(self, mock_config: MagicMock) -> None:
        """Test manager initialization."""
        manager = QualityManager(mock_config)

        assert manager.config is not None
        assert manager.metadata_filter is not None
        assert manager.study_classifier is not None
        assert manager.quality_agent is not None

    def test_custom_models(self, mock_config: MagicMock) -> None:
        """Test manager with custom models."""
        manager = QualityManager(
            mock_config,
            classification_model="custom-haiku",
            assessment_model="custom-sonnet",
        )

        assert manager.study_classifier.model == "custom-haiku"
        assert manager.quality_agent.model == "custom-sonnet"


class TestAssessDocument:
    """Tests for document assessment."""

    @pytest.fixture
    def mock_config(self) -> MagicMock:
        """Create mock configuration."""
        config = MagicMock()
        config.llm = MagicMock()
        config.llm.provider = "anthropic"
        return config

    @pytest.fixture
    def manager(self, mock_config: MagicMock) -> QualityManager:
        """Create manager with mocked components."""
        manager = QualityManager(mock_config)
        manager.metadata_filter = MagicMock()
        manager.study_classifier = MagicMock()
        manager.quality_agent = MagicMock()
        return manager

    def test_uses_metadata_when_confident(self, manager: QualityManager) -> None:
        """Manager should use metadata when confidence is high."""
        metadata_result = QualityAssessment.from_metadata(
            study_design=StudyDesign.RCT,
            confidence=0.95,
        )
        manager.metadata_filter.assess.return_value = metadata_result

        doc = MagicMock()
        filter_settings = QualityFilter()

        result = manager.assess_document(doc, filter_settings)

        assert result.study_design == StudyDesign.RCT
        assert result.assessment_tier == 1
        # Study classifier should not be called
        manager.study_classifier.classify.assert_not_called()

    def test_uses_metadata_only_when_requested(self, manager: QualityManager) -> None:
        """Manager should use only metadata when use_metadata_only is True."""
        metadata_result = QualityAssessment.unclassified()
        manager.metadata_filter.assess.return_value = metadata_result

        doc = MagicMock()
        filter_settings = QualityFilter(use_metadata_only=True)

        result = manager.assess_document(doc, filter_settings)

        assert result.study_design == StudyDesign.UNKNOWN
        # LLM should not be called
        manager.study_classifier.classify.assert_not_called()
        manager.quality_agent.assess_quality.assert_not_called()

    def test_falls_back_to_llm_when_unclassified(self, manager: QualityManager) -> None:
        """Manager should use LLM when metadata is unclassified."""
        metadata_result = QualityAssessment.unclassified()
        manager.metadata_filter.assess.return_value = metadata_result

        classification = StudyClassification(
            study_design=StudyDesign.COHORT_PROSPECTIVE,
            confidence=0.88,
        )
        manager.study_classifier.classify.return_value = classification

        doc = MagicMock()
        filter_settings = QualityFilter(use_llm_classification=True)

        result = manager.assess_document(doc, filter_settings)

        assert result.study_design == StudyDesign.COHORT_PROSPECTIVE
        assert result.assessment_tier == 2
        manager.study_classifier.classify.assert_called_once()

    def test_falls_back_to_llm_when_low_confidence(self, manager: QualityManager) -> None:
        """Manager should use LLM when metadata has low confidence."""
        # Low confidence metadata result
        metadata_result = QualityAssessment.from_metadata(
            study_design=StudyDesign.RCT,
            confidence=0.5,  # Below threshold
        )
        manager.metadata_filter.assess.return_value = metadata_result

        classification = StudyClassification(
            study_design=StudyDesign.RCT,
            confidence=0.92,
        )
        manager.study_classifier.classify.return_value = classification

        doc = MagicMock()
        filter_settings = QualityFilter(use_llm_classification=True)

        result = manager.assess_document(doc, filter_settings)

        # Should use LLM classification
        manager.study_classifier.classify.assert_called_once()
        assert result.assessment_tier == 2

    def test_uses_detailed_assessment_when_requested(self, manager: QualityManager) -> None:
        """Manager should use Sonnet when detailed assessment requested."""
        metadata_result = QualityAssessment.unclassified()
        manager.metadata_filter.assess.return_value = metadata_result

        detailed_result = QualityAssessment(
            assessment_tier=3,
            extraction_method="llm_sonnet",
            study_design=StudyDesign.RCT,
            quality_tier=QualityTier.TIER_4_EXPERIMENTAL,
            quality_score=8.0,
            confidence=0.92,
        )
        manager.quality_agent.assess_quality.return_value = detailed_result

        doc = MagicMock()
        filter_settings = QualityFilter(
            use_llm_classification=True,
            use_detailed_assessment=True,
        )

        result = manager.assess_document(doc, filter_settings)

        assert result.assessment_tier == 3
        manager.quality_agent.assess_quality.assert_called_once()

    def test_detailed_assessment_despite_confident_metadata(
        self, manager: QualityManager
    ) -> None:
        """Manager should use Sonnet when requested even if metadata is confident."""
        metadata_result = QualityAssessment.from_metadata(
            study_design=StudyDesign.RCT,
            confidence=0.95,
        )
        manager.metadata_filter.assess.return_value = metadata_result

        detailed_result = QualityAssessment(
            assessment_tier=3,
            extraction_method="llm_sonnet",
            study_design=StudyDesign.RCT,
            quality_tier=QualityTier.TIER_4_EXPERIMENTAL,
            quality_score=8.5,
            confidence=0.95,
        )
        manager.quality_agent.assess_quality.return_value = detailed_result

        doc = MagicMock()
        filter_settings = QualityFilter(use_detailed_assessment=True)

        result = manager.assess_document(doc, filter_settings)

        # Should use detailed assessment
        assert result.assessment_tier == 3
        manager.quality_agent.assess_quality.assert_called_once()


class TestFilterDocuments:
    """Tests for document filtering."""

    @pytest.fixture
    def mock_config(self) -> MagicMock:
        """Create mock configuration."""
        config = MagicMock()
        config.llm = MagicMock()
        config.llm.provider = "anthropic"
        return config

    @pytest.fixture
    def manager(self, mock_config: MagicMock) -> QualityManager:
        """Create manager with mocked components."""
        manager = QualityManager(mock_config)
        manager.metadata_filter = MagicMock()
        manager.study_classifier = MagicMock()
        manager.quality_agent = MagicMock()
        return manager

    def test_filter_documents_by_tier(self, manager: QualityManager) -> None:
        """Manager should correctly filter documents by quality tier."""
        docs = [MagicMock() for _ in range(5)]

        # Mock assessments: 3 RCTs (pass), 2 case reports (fail)
        def mock_assess(doc):
            idx = docs.index(doc)
            if idx < 3:
                return QualityAssessment.from_metadata(
                    study_design=StudyDesign.RCT,
                    confidence=0.95,
                )
            else:
                return QualityAssessment.from_metadata(
                    study_design=StudyDesign.CASE_REPORT,
                    confidence=0.95,
                )

        manager.metadata_filter.assess.side_effect = mock_assess

        filter_settings = QualityFilter(
            minimum_tier=QualityTier.TIER_4_EXPERIMENTAL,
            use_metadata_only=True,
        )

        filtered, assessments = manager.filter_documents(docs, filter_settings)

        assert len(filtered) == 3
        assert len(assessments) == 5

    def test_filter_with_progress_callback(self, manager: QualityManager) -> None:
        """Manager should call progress callback during filtering."""
        docs = [MagicMock() for _ in range(3)]
        manager.metadata_filter.assess.return_value = QualityAssessment.from_metadata(
            study_design=StudyDesign.RCT,
            confidence=0.95,
        )

        callback = MagicMock()
        filter_settings = QualityFilter(use_metadata_only=True)

        manager.filter_documents(docs, filter_settings, progress_callback=callback)

        assert callback.call_count == 3

    def test_filter_empty_list(self, manager: QualityManager) -> None:
        """Manager should handle empty document list."""
        filter_settings = QualityFilter()

        filtered, assessments = manager.filter_documents([], filter_settings)

        assert len(filtered) == 0
        assert len(assessments) == 0


class TestAssessmentSummary:
    """Tests for assessment summary generation."""

    @pytest.fixture
    def mock_config(self) -> MagicMock:
        """Create mock configuration."""
        config = MagicMock()
        config.llm = MagicMock()
        config.llm.provider = "anthropic"
        return config

    @pytest.fixture
    def manager(self, mock_config: MagicMock) -> QualityManager:
        """Create manager."""
        return QualityManager(mock_config)

    def test_summary_empty_list(self, manager: QualityManager) -> None:
        """Test summary for empty assessment list."""
        summary = manager.get_assessment_summary([])

        assert summary["total"] == 0
        assert summary["avg_confidence"] == 0.0
        assert summary["by_assessment_tier"]["metadata"] == 0

    def test_summary_with_assessments(self, manager: QualityManager) -> None:
        """Test summary with multiple assessments."""
        assessments = [
            QualityAssessment.from_metadata(StudyDesign.RCT, 0.9),
            QualityAssessment.from_metadata(StudyDesign.RCT, 0.95),
            QualityAssessment.from_metadata(StudyDesign.SYSTEMATIC_REVIEW, 0.95),
            QualityAssessment.from_metadata(StudyDesign.CASE_REPORT, 0.85),
        ]

        summary = manager.get_assessment_summary(assessments)

        assert summary["total"] == 4
        assert summary["by_study_design"]["rct"] == 2
        assert summary["by_study_design"]["systematic_review"] == 1
        assert summary["by_study_design"]["case_report"] == 1
        assert summary["by_assessment_tier"]["metadata"] == 4
        assert 0.9 <= summary["avg_confidence"] <= 0.95

    def test_summary_by_assessment_tier(self, manager: QualityManager) -> None:
        """Test summary correctly counts assessment tiers."""
        assessments = [
            # Tier 1 (metadata)
            QualityAssessment.from_metadata(StudyDesign.RCT, 0.95),
            # Tier 2 (Haiku)
            QualityAssessment.from_classification(
                StudyClassification(
                    study_design=StudyDesign.COHORT_PROSPECTIVE,
                    confidence=0.88,
                )
            ),
            # Tier 3 (Sonnet)
            QualityAssessment(
                assessment_tier=3,
                extraction_method="llm_sonnet",
                study_design=StudyDesign.RCT,
                quality_tier=QualityTier.TIER_4_EXPERIMENTAL,
                quality_score=8.0,
                confidence=0.92,
            ),
        ]

        summary = manager.get_assessment_summary(assessments)

        assert summary["by_assessment_tier"]["metadata"] == 1
        assert summary["by_assessment_tier"]["haiku"] == 1
        assert summary["by_assessment_tier"]["sonnet"] == 1


class TestTierDistribution:
    """Tests for tier distribution calculation."""

    @pytest.fixture
    def mock_config(self) -> MagicMock:
        """Create mock configuration."""
        config = MagicMock()
        config.llm = MagicMock()
        config.llm.provider = "anthropic"
        return config

    @pytest.fixture
    def manager(self, mock_config: MagicMock) -> QualityManager:
        """Create manager."""
        return QualityManager(mock_config)

    def test_tier_distribution(self, manager: QualityManager) -> None:
        """Test tier distribution calculation."""
        assessments = [
            QualityAssessment.from_metadata(StudyDesign.RCT, 0.9),
            QualityAssessment.from_metadata(StudyDesign.RCT, 0.9),
            QualityAssessment.from_metadata(StudyDesign.SYSTEMATIC_REVIEW, 0.95),
            QualityAssessment.from_metadata(StudyDesign.CASE_REPORT, 0.85),
        ]

        distribution = manager.get_tier_distribution(assessments)

        assert distribution[QualityTier.TIER_4_EXPERIMENTAL] == 2
        assert distribution[QualityTier.TIER_5_SYNTHESIS] == 1
        assert distribution[QualityTier.TIER_1_ANECDOTAL] == 1

    def test_tier_distribution_empty(self, manager: QualityManager) -> None:
        """Test tier distribution with empty list."""
        distribution = manager.get_tier_distribution([])

        # All tiers should be 0
        for tier in QualityTier:
            assert distribution[tier] == 0


class TestDesignDistribution:
    """Tests for study design distribution calculation."""

    @pytest.fixture
    def mock_config(self) -> MagicMock:
        """Create mock configuration."""
        config = MagicMock()
        config.llm = MagicMock()
        config.llm.provider = "anthropic"
        return config

    @pytest.fixture
    def manager(self, mock_config: MagicMock) -> QualityManager:
        """Create manager."""
        return QualityManager(mock_config)

    def test_design_distribution(self, manager: QualityManager) -> None:
        """Test study design distribution calculation."""
        assessments = [
            QualityAssessment.from_metadata(StudyDesign.RCT, 0.9),
            QualityAssessment.from_metadata(StudyDesign.RCT, 0.9),
            QualityAssessment.from_metadata(StudyDesign.COHORT_PROSPECTIVE, 0.85),
        ]

        distribution = manager.get_design_distribution(assessments)

        assert distribution["rct"] == 2
        assert distribution["cohort_prospective"] == 1

    def test_design_distribution_empty(self, manager: QualityManager) -> None:
        """Test design distribution with empty list."""
        distribution = manager.get_design_distribution([])
        assert len(distribution) == 0
