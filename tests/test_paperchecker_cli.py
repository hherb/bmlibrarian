"""
Tests for PaperChecker CLI module.

Tests cover:
- Input validation (abstract length, PMID range)
- JSON file loading
- Output formatting
- Statistics calculation
- Error handling
"""

import json
import pytest
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

from bmlibrarian.paperchecker.cli.commands import (
    validate_abstract,
    load_abstracts_from_json,
    export_markdown_reports,
    MIN_ABSTRACT_LENGTH,
    MAX_ABSTRACT_LENGTH,
    MIN_PMID,
    MAX_PMID,
    MAX_VALIDATION_ERRORS_DISPLAYED,
    MAX_ERROR_PREVIEW_LENGTH,
    LARGE_BATCH_THRESHOLD,
    VERY_LARGE_BATCH_THRESHOLD,
    ESTIMATED_MB_PER_RESULT,
)
from bmlibrarian.paperchecker.cli.formatters import (
    _safe_percentage,
    _create_bar,
    _truncate,
    format_verdict_summary,
    SEPARATOR_WIDTH,
    DEFAULT_BAR_WIDTH,
    MAX_PREVIEW_LENGTH,
)


# ==================== Validation Tests ====================

class TestValidateAbstract:
    """Tests for validate_abstract function."""

    def test_valid_abstract(self) -> None:
        """Test validation accepts valid abstracts."""
        abstract = "A" * MIN_ABSTRACT_LENGTH
        is_valid, error = validate_abstract(abstract, 0)
        assert is_valid is True
        assert error is None

    def test_empty_abstract(self) -> None:
        """Test validation rejects empty abstracts."""
        is_valid, error = validate_abstract("", 0)
        assert is_valid is False
        assert "empty" in error.lower()

    def test_none_abstract(self) -> None:
        """Test validation rejects None abstracts."""
        is_valid, error = validate_abstract(None, 0)
        assert is_valid is False
        assert "empty" in error.lower()

    def test_abstract_too_short(self) -> None:
        """Test validation rejects short abstracts."""
        abstract = "A" * (MIN_ABSTRACT_LENGTH - 1)
        is_valid, error = validate_abstract(abstract, 5)
        assert is_valid is False
        assert "too short" in error.lower()
        assert "5" in error  # Index should be in error message

    def test_abstract_too_long(self) -> None:
        """Test validation rejects long abstracts."""
        abstract = "A" * (MAX_ABSTRACT_LENGTH + 1)
        is_valid, error = validate_abstract(abstract, 3)
        assert is_valid is False
        assert "too long" in error.lower()

    def test_abstract_at_min_length(self) -> None:
        """Test validation accepts abstract at exactly minimum length."""
        abstract = "A" * MIN_ABSTRACT_LENGTH
        is_valid, error = validate_abstract(abstract, 0)
        assert is_valid is True

    def test_abstract_at_max_length(self) -> None:
        """Test validation accepts abstract at exactly maximum length."""
        abstract = "A" * MAX_ABSTRACT_LENGTH
        is_valid, error = validate_abstract(abstract, 0)
        assert is_valid is True

    def test_abstract_with_whitespace(self) -> None:
        """Test validation strips whitespace before checking length."""
        # Abstract that's long enough after stripping
        abstract = "  " + "A" * MIN_ABSTRACT_LENGTH + "  "
        is_valid, error = validate_abstract(abstract, 0)
        assert is_valid is True

    def test_non_string_abstract(self) -> None:
        """Test validation rejects non-string abstracts."""
        is_valid, error = validate_abstract(123, 0)
        assert is_valid is False
        assert "not a string" in error.lower()


# ==================== JSON Loading Tests ====================

class TestLoadAbstractsFromJson:
    """Tests for load_abstracts_from_json function."""

    def test_load_valid_json(self, tmp_path: Path) -> None:
        """Test loading valid JSON file."""
        json_file = tmp_path / "test.json"
        data = [
            {"abstract": "A" * MIN_ABSTRACT_LENGTH, "metadata": {"pmid": 12345}},
            {"abstract": "B" * MIN_ABSTRACT_LENGTH, "metadata": {"pmid": 67890}},
        ]
        json_file.write_text(json.dumps(data))

        abstracts = load_abstracts_from_json(str(json_file))

        assert len(abstracts) == 2
        assert abstracts[0]["metadata"]["pmid"] == 12345
        assert abstracts[1]["metadata"]["pmid"] == 67890

    def test_load_file_not_found(self) -> None:
        """Test loading non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_abstracts_from_json("/nonexistent/path.json")

    def test_load_invalid_json(self, tmp_path: Path) -> None:
        """Test loading invalid JSON raises JSONDecodeError."""
        json_file = tmp_path / "invalid.json"
        json_file.write_text("not valid json {")

        with pytest.raises(json.JSONDecodeError):
            load_abstracts_from_json(str(json_file))

    def test_load_non_list_json(self, tmp_path: Path) -> None:
        """Test loading JSON that's not a list raises ValueError."""
        json_file = tmp_path / "dict.json"
        json_file.write_text(json.dumps({"abstract": "test"}))

        with pytest.raises(ValueError, match="list"):
            load_abstracts_from_json(str(json_file))

    def test_load_empty_list(self, tmp_path: Path) -> None:
        """Test loading empty list raises ValueError."""
        json_file = tmp_path / "empty.json"
        json_file.write_text(json.dumps([]))

        with pytest.raises(ValueError, match="no abstracts"):
            load_abstracts_from_json(str(json_file))

    def test_load_missing_abstract_key(self, tmp_path: Path) -> None:
        """Test loading items without 'abstract' key raises ValueError."""
        json_file = tmp_path / "missing_key.json"
        data = [{"metadata": {"pmid": 123}}]
        json_file.write_text(json.dumps(data))

        with pytest.raises(ValueError, match="abstract"):
            load_abstracts_from_json(str(json_file))

    def test_load_with_optional_metadata(self, tmp_path: Path) -> None:
        """Test loading abstracts without metadata."""
        json_file = tmp_path / "no_metadata.json"
        data = [{"abstract": "A" * MIN_ABSTRACT_LENGTH}]
        json_file.write_text(json.dumps(data))

        abstracts = load_abstracts_from_json(str(json_file))

        assert len(abstracts) == 1
        assert abstracts[0]["metadata"] == {}


# ==================== Formatter Tests ====================

class TestSafePercentage:
    """Tests for _safe_percentage function."""

    def test_normal_percentage(self) -> None:
        """Test normal percentage calculation."""
        assert _safe_percentage(50, 100) == 50.0

    def test_zero_total(self) -> None:
        """Test zero total returns 0.0."""
        assert _safe_percentage(10, 0) == 0.0

    def test_zero_count(self) -> None:
        """Test zero count returns 0.0."""
        assert _safe_percentage(0, 100) == 0.0

    def test_full_percentage(self) -> None:
        """Test 100% calculation."""
        assert _safe_percentage(100, 100) == 100.0


class TestCreateBar:
    """Tests for _create_bar function."""

    def test_empty_bar(self) -> None:
        """Test 0% bar."""
        bar = _create_bar(0.0)
        assert bar == "[" + " " * DEFAULT_BAR_WIDTH + "]"

    def test_full_bar(self) -> None:
        """Test 100% bar."""
        bar = _create_bar(100.0)
        assert bar == "[" + "=" * DEFAULT_BAR_WIDTH + "]"

    def test_half_bar(self) -> None:
        """Test 50% bar."""
        bar = _create_bar(50.0)
        expected_filled = DEFAULT_BAR_WIDTH // 2
        expected_empty = DEFAULT_BAR_WIDTH - expected_filled
        assert bar == "[" + "=" * expected_filled + " " * expected_empty + "]"

    def test_custom_width(self) -> None:
        """Test bar with custom width."""
        bar = _create_bar(50.0, width=10)
        assert bar == "[=====     ]"


class TestTruncate:
    """Tests for _truncate function."""

    def test_no_truncation_needed(self) -> None:
        """Test text shorter than max is unchanged."""
        text = "short text"
        result = _truncate(text, 50)
        assert result == text

    def test_truncation_applied(self) -> None:
        """Test text longer than max is truncated."""
        text = "A" * 100
        result = _truncate(text, 50)
        assert len(result) == 50
        assert result.endswith("...")

    def test_exact_length(self) -> None:
        """Test text at exactly max length is unchanged."""
        text = "A" * 50
        result = _truncate(text, 50)
        assert result == text


class TestFormatVerdictSummary:
    """Tests for format_verdict_summary function."""

    def test_empty_verdicts(self) -> None:
        """Test empty verdict list."""
        result = format_verdict_summary([])
        assert result == "no verdicts"

    def test_single_verdict(self) -> None:
        """Test single verdict formatting."""
        mock_verdict = MagicMock()
        mock_verdict.verdict = "supports"
        mock_verdict.confidence = "high"

        result = format_verdict_summary([mock_verdict])
        assert "1 supports" in result

    def test_mixed_verdicts(self) -> None:
        """Test mixed verdict formatting."""
        verdicts = []
        for v, c in [("supports", "high"), ("contradicts", "medium"), ("supports", "high")]:
            mock = MagicMock()
            mock.verdict = v
            mock.confidence = c
            verdicts.append(mock)

        result = format_verdict_summary(verdicts)
        assert "2 supports" in result
        assert "1 contradicts" in result


# ==================== Constants Tests ====================

class TestConstants:
    """Tests for module constants."""

    def test_min_abstract_length_positive(self) -> None:
        """Test MIN_ABSTRACT_LENGTH is positive."""
        assert MIN_ABSTRACT_LENGTH > 0

    def test_max_abstract_length_greater_than_min(self) -> None:
        """Test MAX_ABSTRACT_LENGTH > MIN_ABSTRACT_LENGTH."""
        assert MAX_ABSTRACT_LENGTH > MIN_ABSTRACT_LENGTH

    def test_pmid_range_valid(self) -> None:
        """Test PMID range is valid."""
        assert MIN_PMID >= 1
        assert MAX_PMID > MIN_PMID

    def test_error_limits_positive(self) -> None:
        """Test error display limits are positive."""
        assert MAX_VALIDATION_ERRORS_DISPLAYED > 0
        assert MAX_ERROR_PREVIEW_LENGTH > 0

    def test_separator_width_reasonable(self) -> None:
        """Test separator width is reasonable for terminal."""
        assert 40 <= SEPARATOR_WIDTH <= 120

    def test_preview_length_reasonable(self) -> None:
        """Test preview length is reasonable."""
        assert 40 <= MAX_PREVIEW_LENGTH <= 200

    def test_memory_thresholds_ordered(self) -> None:
        """Test memory batch thresholds are properly ordered."""
        assert LARGE_BATCH_THRESHOLD > 0
        assert VERY_LARGE_BATCH_THRESHOLD > LARGE_BATCH_THRESHOLD

    def test_estimated_memory_positive(self) -> None:
        """Test estimated memory per result is positive."""
        assert ESTIMATED_MB_PER_RESULT > 0


# ==================== Export Markdown Tests ====================

class TestExportMarkdownReports:
    """Tests for export_markdown_reports function."""

    def test_export_empty_results_raises(self, tmp_path: Path) -> None:
        """Test exporting empty results raises ValueError."""
        with pytest.raises(ValueError, match="No results"):
            export_markdown_reports([], str(tmp_path / "reports"))

    def test_export_returns_tuple(self, tmp_path: Path) -> None:
        """Test export returns (successful_files, failed_files) tuple."""
        # Create a mock result
        mock_result = MagicMock()
        mock_result.source_metadata = {"pmid": 12345}
        mock_result.to_markdown_report.return_value = "# Test Report\n\nContent"

        output_dir = tmp_path / "reports"
        created, failed = export_markdown_reports([mock_result], str(output_dir))

        assert isinstance(created, list)
        assert isinstance(failed, list)
        assert len(created) == 1
        assert len(failed) == 0
        assert "report_pmid_12345.md" in created[0]

    def test_export_with_failures(self, tmp_path: Path) -> None:
        """Test export captures failures in failed_files list."""
        # Create mock results - one succeeds, one fails
        success_result = MagicMock()
        success_result.source_metadata = {"pmid": 11111}
        success_result.to_markdown_report.return_value = "# Success"

        fail_result = MagicMock()
        fail_result.source_metadata = {"pmid": 22222}
        fail_result.to_markdown_report.side_effect = Exception("Conversion error")

        output_dir = tmp_path / "reports"
        created, failed = export_markdown_reports(
            [success_result, fail_result], str(output_dir)
        )

        assert len(created) == 1
        assert len(failed) == 1
        assert failed[0]["pmid"] == 22222
        assert "Conversion error" in failed[0]["error"]
        assert failed[0]["index"] == 2
        assert "filename" in failed[0]

    def test_export_without_pmid_uses_index(self, tmp_path: Path) -> None:
        """Test export uses index for filename when PMID not available."""
        mock_result = MagicMock()
        mock_result.source_metadata = {}  # No PMID
        mock_result.to_markdown_report.return_value = "# Test Report"

        output_dir = tmp_path / "reports"
        created, failed = export_markdown_reports([mock_result], str(output_dir))

        assert len(created) == 1
        assert "report_abstract_1.md" in created[0]

    def test_export_creates_directory(self, tmp_path: Path) -> None:
        """Test export creates output directory if not exists."""
        mock_result = MagicMock()
        mock_result.source_metadata = {"pmid": 12345}
        mock_result.to_markdown_report.return_value = "# Test"

        output_dir = tmp_path / "nested" / "reports"
        assert not output_dir.exists()

        created, failed = export_markdown_reports([mock_result], str(output_dir))

        assert output_dir.exists()
        assert len(created) == 1
