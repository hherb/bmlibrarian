"""Tests for quality report formatter."""

import pytest
from unittest.mock import MagicMock

from bmlibrarian.lite.quality.data_models import (
    QualityTier,
    StudyDesign,
    QualityAssessment,
)
from bmlibrarian.lite.quality.report_formatter import (
    QualityReportFormatter,
    TIER_EMOJI,
    DESIGN_SHORT_LABELS,
)


class TestReportFormatterConstants:
    """Tests for report formatter constants."""

    def test_tier_emoji_complete(self) -> None:
        """All quality tiers should have emoji."""
        for tier in QualityTier:
            assert tier in TIER_EMOJI, f"Missing emoji for {tier}"

    def test_design_short_labels_have_valid_values(self) -> None:
        """Design short labels should be non-empty strings."""
        for design, label in DESIGN_SHORT_LABELS.items():
            assert isinstance(label, str)
            assert len(label) > 0


class TestQualityReportFormatterInit:
    """Tests for QualityReportFormatter initialization."""

    def test_default_no_emoji(self) -> None:
        """Default formatter should not use emoji."""
        formatter = QualityReportFormatter()
        assert formatter.use_emoji is False

    def test_emoji_mode_enabled(self) -> None:
        """Emoji mode should be configurable."""
        formatter = QualityReportFormatter(use_emoji=True)
        assert formatter.use_emoji is True


class TestInlineCitationFormatting:
    """Tests for inline citation formatting."""

    @pytest.fixture
    def formatter(self) -> QualityReportFormatter:
        """Create a formatter without emoji."""
        return QualityReportFormatter(use_emoji=False)

    @pytest.fixture
    def emoji_formatter(self) -> QualityReportFormatter:
        """Create a formatter with emoji."""
        return QualityReportFormatter(use_emoji=True)

    @pytest.fixture
    def mock_citation(self) -> MagicMock:
        """Create a mock citation."""
        citation = MagicMock()
        citation.formatted_reference = "Smith et al., 2023"
        citation.assessment = None
        return citation

    @pytest.fixture
    def mock_citation_with_quality(self) -> MagicMock:
        """Create a mock citation with quality assessment."""
        citation = MagicMock()
        citation.formatted_reference = "Smith et al., 2023"
        citation.assessment = QualityAssessment(
            assessment_tier=2,
            extraction_method="llm_haiku",
            study_design=StudyDesign.RCT,
            quality_tier=QualityTier.TIER_4_EXPERIMENTAL,
            quality_score=8.0,
            confidence=0.9,
            sample_size=150,
            is_blinded="double",
        )
        return citation

    def test_basic_citation_format(
        self,
        formatter: QualityReportFormatter,
        mock_citation: MagicMock,
    ) -> None:
        """Basic citation should include reference and number."""
        result = formatter.format_inline_citation(mock_citation, 1)
        assert "Smith et al., 2023" in result
        assert "(1)" in result

    def test_citation_with_quality_includes_annotation(
        self,
        formatter: QualityReportFormatter,
        mock_citation_with_quality: MagicMock,
    ) -> None:
        """Citation with quality should include annotation."""
        result = formatter.format_inline_citation(mock_citation_with_quality, 1)
        assert "RCT" in result or "Rct" in result
        assert "n=150" in result

    def test_emoji_formatter_includes_emoji(
        self,
        emoji_formatter: QualityReportFormatter,
        mock_citation_with_quality: MagicMock,
    ) -> None:
        """Emoji formatter should include tier emoji."""
        result = emoji_formatter.format_inline_citation(mock_citation_with_quality, 1)
        # Should include the blue circle emoji for Tier 4
        assert TIER_EMOJI[QualityTier.TIER_4_EXPERIMENTAL] in result


class TestNumberedCitationFormatting:
    """Tests for numbered citation formatting."""

    @pytest.fixture
    def formatter(self) -> QualityReportFormatter:
        """Create a formatter."""
        return QualityReportFormatter()

    def test_numbered_format(self, formatter: QualityReportFormatter) -> None:
        """Numbered citation should include number in brackets."""
        citation = MagicMock()
        citation.assessment = None
        result = formatter.format_numbered_citation(citation, 5)
        assert "[5]" in result

    def test_numbered_with_quality(self, formatter: QualityReportFormatter) -> None:
        """Numbered citation with quality should include annotation."""
        citation = MagicMock()
        citation.assessment = QualityAssessment(
            assessment_tier=2,
            extraction_method="llm_haiku",
            study_design=StudyDesign.META_ANALYSIS,
            quality_tier=QualityTier.TIER_5_SYNTHESIS,
            quality_score=9.0,
            confidence=0.95,
        )
        result = formatter.format_numbered_citation(citation, 3)
        assert "[3]" in result
        assert "MA" in result or "Meta" in result


class TestReferenceEntryFormatting:
    """Tests for reference entry formatting."""

    @pytest.fixture
    def formatter(self) -> QualityReportFormatter:
        """Create a formatter."""
        return QualityReportFormatter()

    @pytest.fixture
    def mock_citation(self) -> MagicMock:
        """Create a mock citation with document."""
        citation = MagicMock()
        citation.document.authors = ["Smith J", "Jones A"]
        citation.document.year = 2023
        citation.document.title = "Test Study"
        citation.document.journal = "Test Journal"
        citation.document.pmid = "12345678"
        citation.document.doi = None
        citation.assessment = None
        return citation

    def test_basic_reference_format(
        self,
        formatter: QualityReportFormatter,
        mock_citation: MagicMock,
    ) -> None:
        """Reference should include author, year, title, journal."""
        result = formatter.format_reference_entry(mock_citation, 1)
        assert "1." in result
        assert "Smith J, Jones A" in result
        assert "2023" in result
        assert "Test Study" in result
        assert "*Test Journal*" in result
        assert "PMID: 12345678" in result

    def test_reference_with_quality_badge(
        self,
        formatter: QualityReportFormatter,
        mock_citation: MagicMock,
    ) -> None:
        """Reference with quality should include design label."""
        mock_citation.assessment = QualityAssessment(
            assessment_tier=2,
            extraction_method="llm_haiku",
            study_design=StudyDesign.RCT,
            quality_tier=QualityTier.TIER_4_EXPERIMENTAL,
            quality_score=8.0,
            confidence=0.9,
        )
        result = formatter.format_reference_entry(mock_citation, 1)
        assert "[Rct]" in result or "[RCT]" in result.upper()

    def test_reference_many_authors(
        self,
        formatter: QualityReportFormatter,
        mock_citation: MagicMock,
    ) -> None:
        """Reference with many authors should use et al."""
        mock_citation.document.authors = ["A", "B", "C", "D", "E"]
        result = formatter.format_reference_entry(mock_citation, 1)
        assert "et al." in result


class TestQualityBadgeFormatting:
    """Tests for standalone quality badge formatting."""

    @pytest.fixture
    def formatter(self) -> QualityReportFormatter:
        """Create a formatter."""
        return QualityReportFormatter()

    def test_badge_includes_design_and_level(
        self, formatter: QualityReportFormatter
    ) -> None:
        """Badge should include design and level."""
        assessment = QualityAssessment(
            assessment_tier=2,
            extraction_method="llm_haiku",
            study_design=StudyDesign.SYSTEMATIC_REVIEW,
            quality_tier=QualityTier.TIER_5_SYNTHESIS,
            quality_score=9.0,
            confidence=0.95,
        )
        result = formatter.format_quality_badge(assessment)
        assert "Systematic Review" in result
        assert "Level 5" in result


class TestCitationsForPrompt:
    """Tests for formatting citations for LLM prompt."""

    @pytest.fixture
    def formatter(self) -> QualityReportFormatter:
        """Create a formatter."""
        return QualityReportFormatter()

    def test_prompt_format_includes_doc_info(
        self, formatter: QualityReportFormatter
    ) -> None:
        """Prompt format should include document information."""
        citation = MagicMock()
        citation.document.formatted_authors = "Smith et al."
        citation.document.year = 2023
        citation.document.id = "pmid-12345"
        citation.document.title = "Test Study"
        citation.document.journal = "Test Journal"
        citation.passage = "Test passage text."
        citation.assessment = None

        result = formatter.format_citations_for_prompt([citation])
        assert "[1]" in result
        assert "Smith et al." in result
        assert "pmid-12345" in result
        assert "Test passage text." in result

    def test_prompt_format_with_quality(
        self, formatter: QualityReportFormatter
    ) -> None:
        """Prompt format with quality should include quality info."""
        citation = MagicMock()
        citation.document.formatted_authors = "Smith et al."
        citation.document.year = 2023
        citation.document.id = "pmid-12345"
        citation.document.title = "Test Study"
        citation.document.journal = "Test Journal"
        citation.passage = "Test passage text."
        citation.assessment = QualityAssessment(
            assessment_tier=2,
            extraction_method="llm_haiku",
            study_design=StudyDesign.RCT,
            quality_tier=QualityTier.TIER_4_EXPERIMENTAL,
            quality_score=8.0,
            confidence=0.9,
            sample_size=100,
        )

        result = formatter.format_citations_for_prompt([citation], include_quality=True)
        assert "Study Design:" in result
        assert "Sample Size: 100" in result
        assert "Quality Score: 8.0/10" in result

    def test_prompt_format_without_quality(
        self, formatter: QualityReportFormatter
    ) -> None:
        """Prompt format without quality flag should not include quality."""
        citation = MagicMock()
        citation.document.formatted_authors = "Smith et al."
        citation.document.year = 2023
        citation.document.id = "pmid-12345"
        citation.document.title = "Test Study"
        citation.document.journal = "Test Journal"
        citation.passage = "Test passage text."
        citation.assessment = QualityAssessment(
            assessment_tier=2,
            extraction_method="llm_haiku",
            study_design=StudyDesign.RCT,
            quality_tier=QualityTier.TIER_4_EXPERIMENTAL,
            quality_score=8.0,
            confidence=0.9,
        )

        result = formatter.format_citations_for_prompt([citation], include_quality=False)
        assert "Study Design:" not in result
        assert "Quality Score:" not in result
