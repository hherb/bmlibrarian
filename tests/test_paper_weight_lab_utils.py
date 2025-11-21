"""
Tests for paper_weight_lab utility functions and constants

Tests cover:
- Pure utility functions (formatting, truncation, validation)
- Constants validation
- Weight conversion functions

These tests do NOT require Qt/PySide6 as they test only the pure functions.
"""

import pytest
from datetime import datetime

from bmlibrarian.lab.paper_weight_lab.constants import (
    WINDOW_MIN_WIDTH,
    WINDOW_MIN_HEIGHT,
    WINDOW_DEFAULT_WIDTH,
    WINDOW_DEFAULT_HEIGHT,
    SCORE_MAX,
    SCORE_DECIMALS,
    WEIGHT_SLIDER_MIN,
    WEIGHT_SLIDER_MAX,
    WEIGHT_SLIDER_PRECISION,
    AUTHOR_DISPLAY_MAX_LENGTH,
    PROGRESS_PENDING,
    PROGRESS_COMPLETE,
)
from bmlibrarian.lab.paper_weight_lab.utils import (
    format_dimension_name,
    format_score,
    format_score_with_max,
    format_datetime,
    truncate_with_ellipsis,
    truncate_authors,
    format_document_metadata,
    format_recent_assessment_display,
    validate_weights_sum,
    slider_value_to_weight,
    weight_to_slider_value,
)


class TestConstants:
    """Tests for module constants."""

    def test_window_dimensions_positive(self):
        """Ensure window dimensions are positive."""
        assert WINDOW_MIN_WIDTH > 0
        assert WINDOW_MIN_HEIGHT > 0
        assert WINDOW_DEFAULT_WIDTH > 0
        assert WINDOW_DEFAULT_HEIGHT > 0

    def test_default_larger_than_min(self):
        """Ensure default dimensions are larger than minimum."""
        assert WINDOW_DEFAULT_WIDTH >= WINDOW_MIN_WIDTH
        assert WINDOW_DEFAULT_HEIGHT >= WINDOW_MIN_HEIGHT

    def test_score_max_positive(self):
        """Ensure score max is positive."""
        assert SCORE_MAX > 0

    def test_score_decimals_non_negative(self):
        """Ensure score decimals is non-negative."""
        assert SCORE_DECIMALS >= 0

    def test_weight_slider_range_valid(self):
        """Ensure weight slider range is valid."""
        assert WEIGHT_SLIDER_MIN < WEIGHT_SLIDER_MAX
        assert WEIGHT_SLIDER_PRECISION > 0

    def test_author_display_length_positive(self):
        """Ensure author display max length is positive."""
        assert AUTHOR_DISPLAY_MAX_LENGTH > 0

    def test_progress_symbols_are_strings(self):
        """Ensure progress symbols are non-empty strings."""
        assert isinstance(PROGRESS_PENDING, str)
        assert len(PROGRESS_PENDING) > 0
        assert isinstance(PROGRESS_COMPLETE, str)
        assert len(PROGRESS_COMPLETE) > 0


class TestFormatDimensionName:
    """Tests for format_dimension_name function."""

    def test_underscore_to_space(self):
        """Test underscores are converted to spaces."""
        assert format_dimension_name('study_design') == 'Study Design'

    def test_title_case(self):
        """Test result is title case."""
        assert format_dimension_name('sample_size') == 'Sample Size'

    def test_single_word(self):
        """Test single word dimensions."""
        assert format_dimension_name('methodology') == 'Methodology'

    def test_multiple_underscores(self):
        """Test dimensions with multiple underscores."""
        result = format_dimension_name('risk_of_bias')
        assert result == 'Risk Of Bias'

    def test_empty_string(self):
        """Test empty string input."""
        assert format_dimension_name('') == ''


class TestFormatScore:
    """Tests for format_score function."""

    def test_default_decimals(self):
        """Test score formatting with default decimals."""
        result = format_score(7.5)
        assert result == f"7.{50:0{SCORE_DECIMALS - 1}d}"

    def test_custom_decimals(self):
        """Test score formatting with custom decimals."""
        assert format_score(7.5, decimals=1) == '7.5'
        assert format_score(7.5, decimals=3) == '7.500'

    def test_zero_score(self):
        """Test zero score."""
        assert format_score(0.0, decimals=2) == '0.00'

    def test_integer_score(self):
        """Test integer score."""
        assert format_score(10, decimals=2) == '10.00'


class TestFormatScoreWithMax:
    """Tests for format_score_with_max function."""

    def test_default_max(self):
        """Test with default max score."""
        result = format_score_with_max(7.5)
        assert '/10' in result
        assert '7.' in result

    def test_custom_max(self):
        """Test with custom max score."""
        result = format_score_with_max(7.5, max_score=100.0)
        assert '/100' in result


class TestFormatDatetime:
    """Tests for format_datetime function."""

    def test_default_format(self):
        """Test datetime with default format."""
        dt = datetime(2024, 1, 15, 10, 30)
        result = format_datetime(dt)
        assert '2024-01-15' in result
        assert '10:30' in result

    def test_custom_format(self):
        """Test datetime with custom format."""
        dt = datetime(2024, 1, 15, 10, 30)
        result = format_datetime(dt, fmt='%Y/%m/%d')
        assert result == '2024/01/15'


class TestTruncateWithEllipsis:
    """Tests for truncate_with_ellipsis function."""

    def test_short_text_not_truncated(self):
        """Test short text is not truncated."""
        text = "Short text"
        result, was_truncated = truncate_with_ellipsis(text, 100)
        assert result == text
        assert was_truncated is False

    def test_long_text_truncated(self):
        """Test long text is truncated."""
        text = "This is a very long text that should be truncated"
        result, was_truncated = truncate_with_ellipsis(text, 20)
        assert len(result) == 20
        assert result.endswith('...')
        assert was_truncated is True

    def test_custom_ellipsis(self):
        """Test with custom ellipsis."""
        text = "Long text here"
        result, _ = truncate_with_ellipsis(text, 10, ellipsis='…')
        assert result.endswith('…')

    def test_empty_text(self):
        """Test empty text."""
        result, was_truncated = truncate_with_ellipsis('', 10)
        assert result == ''
        assert was_truncated is False

    def test_none_input(self):
        """Test None-like empty input."""
        result, was_truncated = truncate_with_ellipsis('', 10)
        assert result == ''
        assert was_truncated is False

    def test_exact_length(self):
        """Test text exactly at max length."""
        text = "Exact"
        result, was_truncated = truncate_with_ellipsis(text, 5)
        assert result == text
        assert was_truncated is False


class TestTruncateAuthors:
    """Tests for truncate_authors function."""

    def test_short_authors_not_truncated(self):
        """Test short authors string is not truncated."""
        authors = "Smith J, Johnson A"
        result = truncate_authors(authors)
        assert result == authors

    def test_long_authors_truncated(self):
        """Test long authors string is truncated."""
        authors = "A" * 200
        result = truncate_authors(authors)
        assert len(result) <= AUTHOR_DISPLAY_MAX_LENGTH
        assert result.endswith('...')

    def test_none_authors(self):
        """Test None authors."""
        assert truncate_authors(None) == ''

    def test_empty_authors(self):
        """Test empty authors."""
        assert truncate_authors('') == ''


class TestFormatDocumentMetadata:
    """Tests for format_document_metadata function."""

    def test_all_fields(self):
        """Test with all fields populated."""
        result = format_document_metadata(
            authors="Smith J",
            year=2024,
            pmid=12345678,
            doi="10.1234/test"
        )
        assert "Smith J" in result
        assert "2024" in result
        assert "PMID: 12345678" in result
        assert "DOI: 10.1234/test" in result
        assert " | " in result

    def test_partial_fields(self):
        """Test with partial fields."""
        result = format_document_metadata(year=2024, pmid=12345678)
        assert "2024" in result
        assert "PMID:" in result
        assert "DOI:" not in result

    def test_no_fields(self):
        """Test with no fields."""
        result = format_document_metadata()
        assert result == ''

    def test_long_authors_truncated(self):
        """Test that long authors are truncated."""
        long_authors = "A" * 200
        result = format_document_metadata(authors=long_authors)
        assert len(result) <= AUTHOR_DISPLAY_MAX_LENGTH + 10  # Some margin for ellipsis


class TestFormatRecentAssessmentDisplay:
    """Tests for format_recent_assessment_display function."""

    def test_normal_title(self):
        """Test with normal title."""
        result = format_recent_assessment_display("Test Paper", 7.5)
        assert "[7.5]" in result
        assert "Test Paper" in result

    def test_long_title_truncated(self):
        """Test long title is truncated."""
        long_title = "A" * 100
        result = format_recent_assessment_display(long_title, 7.5, max_title_length=60)
        assert len(result) < 80  # Score + truncated title
        assert "..." in result

    def test_no_title(self):
        """Test with no title."""
        result = format_recent_assessment_display(None, 5.0)
        assert "No title" in result


class TestValidateWeightsSum:
    """Tests for validate_weights_sum function."""

    def test_valid_weights(self):
        """Test weights that sum to 1.0."""
        weights = {'a': 0.5, 'b': 0.3, 'c': 0.2}
        is_valid, total = validate_weights_sum(weights)
        assert is_valid is True
        assert abs(total - 1.0) < 0.01

    def test_invalid_weights(self):
        """Test weights that don't sum to 1.0."""
        weights = {'a': 0.5, 'b': 0.5, 'c': 0.5}
        is_valid, total = validate_weights_sum(weights)
        assert is_valid is False
        assert abs(total - 1.5) < 0.01

    def test_within_tolerance(self):
        """Test weights within tolerance."""
        weights = {'a': 0.505, 'b': 0.495}
        is_valid, total = validate_weights_sum(weights, tolerance=0.02)
        assert is_valid is True

    def test_empty_weights(self):
        """Test empty weights."""
        is_valid, total = validate_weights_sum({})
        assert is_valid is False
        assert total == 0.0


class TestSliderWeightConversion:
    """Tests for slider/weight conversion functions."""

    def test_slider_to_weight(self):
        """Test slider value to weight conversion."""
        assert slider_value_to_weight(50) == 0.5
        assert slider_value_to_weight(100) == 1.0
        assert slider_value_to_weight(0) == 0.0
        assert slider_value_to_weight(25) == 0.25

    def test_weight_to_slider(self):
        """Test weight to slider value conversion."""
        assert weight_to_slider_value(0.5) == 50
        assert weight_to_slider_value(1.0) == 100
        assert weight_to_slider_value(0.0) == 0
        assert weight_to_slider_value(0.25) == 25

    def test_round_trip(self):
        """Test round-trip conversion."""
        for slider_val in [0, 25, 50, 75, 100]:
            weight = slider_value_to_weight(slider_val)
            result = weight_to_slider_value(weight)
            assert result == slider_val

    def test_custom_precision(self):
        """Test with custom precision."""
        assert slider_value_to_weight(50, precision=1000) == 0.05
        assert weight_to_slider_value(0.05, precision=1000) == 50


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
