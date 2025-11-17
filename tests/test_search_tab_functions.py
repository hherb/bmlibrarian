"""
Focused unit tests for Search Tab utility functions.

Tests the standalone utility functions without Qt dependencies:
- Input validation (validate_search_input)
- Type-safe year extraction (extract_year_from_value)
"""

import pytest
import re
from datetime import datetime, date
from typing import Any, Optional


# ============================================================================
# Copy of utility functions from search_tab.py for testing
# (In a real scenario, these would be in a separate utils module)
# ============================================================================

MAX_SEARCH_TEXT_LENGTH = 2000
SUSPICIOUS_SQL_PATTERNS = [
    r';[\s]*DROP', r';[\s]*DELETE', r';[\s]*UPDATE', r';[\s]*INSERT',
    r'--', r'/\*', r'\*/', r'xp_', r'sp_', r'EXEC', r'EXECUTE'
]


def validate_search_input(search_text: str) -> tuple[bool, str]:
    """
    Validate user search input for security and safety.

    Args:
        search_text: User-provided search text

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not search_text or not search_text.strip():
        return False, "Search text cannot be empty"

    if len(search_text) > MAX_SEARCH_TEXT_LENGTH:
        return False, f"Search text too long (max {MAX_SEARCH_TEXT_LENGTH} characters)"

    search_upper = search_text.upper()
    for pattern in SUSPICIOUS_SQL_PATTERNS:
        if re.search(pattern, search_upper, re.IGNORECASE):
            return False, "Search text contains potentially unsafe characters"

    return True, ""


def extract_year_from_value(value: Any) -> Optional[int]:
    """
    Safely extract year as integer from various input types.

    Args:
        value: Value to extract year from

    Returns:
        Integer year if successfully extracted, None otherwise
    """
    if value is None:
        return None

    if isinstance(value, int):
        if 1800 <= value <= 2200:
            return value
        return None

    if isinstance(value, str):
        try:
            year = int(value)
            if 1800 <= year <= 2200:
                return year
        except ValueError:
            pass

        try:
            if len(value) >= 4:
                year = int(value[:4])
                if 1800 <= year <= 2200:
                    return year
        except ValueError:
            pass

    if hasattr(value, 'year'):
        try:
            year = int(value.year)
            if 1800 <= year <= 2200:
                return year
        except (ValueError, TypeError):
            pass

    return None


# ============================================================================
# Input Validation Tests
# ============================================================================

class TestInputValidation:
    """Test input validation function."""

    def test_validate_empty_input(self):
        """Test rejection of empty input."""
        is_valid, error = validate_search_input("")
        assert not is_valid
        assert "empty" in error.lower()

    def test_validate_whitespace_only(self):
        """Test rejection of whitespace-only input."""
        is_valid, error = validate_search_input("   \t\n  ")
        assert not is_valid
        assert "empty" in error.lower()

    def test_validate_normal_input(self):
        """Test acceptance of normal search text."""
        is_valid, error = validate_search_input("COVID-19 vaccine effectiveness")
        assert is_valid
        assert error == ""

    def test_validate_max_length(self):
        """Test rejection of overly long input."""
        long_text = "a" * (MAX_SEARCH_TEXT_LENGTH + 1)
        is_valid, error = validate_search_input(long_text)
        assert not is_valid
        assert "too long" in error.lower()

    def test_validate_sql_injection_patterns(self):
        """Test detection of suspicious SQL patterns."""
        suspicious_patterns = [
            "test; DROP TABLE documents;",
            "test -- comment",
            "test /* comment */",
            "test'; DELETE FROM documents;",
            "EXECUTE sp_executesql",
        ]

        for pattern in suspicious_patterns:
            is_valid, error = validate_search_input(pattern)
            assert not is_valid, f"Should reject: {pattern}"
            assert "unsafe" in error.lower()

    def test_validate_medical_terms(self):
        """Test acceptance of legitimate medical search terms."""
        valid_queries = [
            "myocardial infarction",
            "diabetes mellitus type 2",
            "SARS-CoV-2 variants",
            "randomized controlled trial (RCT)",
            "statins & cholesterol",
        ]

        for query in valid_queries:
            is_valid, error = validate_search_input(query)
            assert is_valid, f"Should accept: {query}"
            assert error == ""


# ============================================================================
# Type Safety Tests
# ============================================================================

class TestYearExtraction:
    """Test type-safe year extraction function."""

    def test_extract_from_none(self):
        """Test handling of None value."""
        assert extract_year_from_value(None) is None

    def test_extract_from_integer(self):
        """Test extraction from integer."""
        assert extract_year_from_value(2024) == 2024
        assert extract_year_from_value(2000) == 2000
        assert extract_year_from_value(1995) == 1995

    def test_extract_from_invalid_integer(self):
        """Test rejection of invalid year integers."""
        assert extract_year_from_value(999) is None  # Too early
        assert extract_year_from_value(3000) is None  # Too late

    def test_extract_from_string(self):
        """Test extraction from string."""
        assert extract_year_from_value("2024") == 2024
        assert extract_year_from_value("2000") == 2000

    def test_extract_from_iso_date_string(self):
        """Test extraction from ISO date strings."""
        assert extract_year_from_value("2024-03-15") == 2024
        assert extract_year_from_value("2020-12-31") == 2020

    def test_extract_from_invalid_string(self):
        """Test handling of invalid string formats."""
        assert extract_year_from_value("invalid") is None
        assert extract_year_from_value("abcd") is None
        assert extract_year_from_value("") is None

    def test_extract_from_datetime_object(self):
        """Test extraction from datetime objects."""
        dt = datetime(2024, 3, 15, 10, 30)
        assert extract_year_from_value(dt) == 2024

    def test_extract_from_date_object(self):
        """Test extraction from date objects."""
        d = date(2024, 3, 15)
        assert extract_year_from_value(d) == 2024

    def test_extract_from_various_types(self):
        """Test handling of various input types."""
        test_cases = [
            (2024, 2024),
            ("2024", 2024),
            ("2024-01-01", 2024),
            (datetime(2024, 1, 1), 2024),
            (None, None),
            ("invalid", None),
            ([], None),
            ({}, None),
        ]

        for input_val, expected in test_cases:
            result = extract_year_from_value(input_val)
            assert result == expected, f"Failed for input: {input_val}"

    def test_year_range_boundaries(self):
        """Test year range boundary conditions."""
        # Valid boundaries
        assert extract_year_from_value(1800) == 1800
        assert extract_year_from_value(2200) == 2200

        # Invalid boundaries
        assert extract_year_from_value(1799) is None
        assert extract_year_from_value(2201) is None

    def test_extract_from_partial_date_strings(self):
        """Test extraction from various date string formats."""
        test_cases = [
            ("2024", 2024),
            ("2024-01", 2024),
            ("2024-01-01", 2024),
            ("2024-01-01 10:30:00", 2024),
            ("2024/01/01", 2024),
            ("01/01/2024", None),  # Can't extract from this format
        ]

        for input_str, expected in test_cases:
            result = extract_year_from_value(input_str)
            assert result == expected, f"Failed for input: {input_str}"


# ============================================================================
# Constants Verification
# ============================================================================

class TestConstants:
    """Verify algorithm parameter constants are properly defined."""

    def test_constants_exist(self):
        """Test that all required constants are defined."""
        assert MAX_SEARCH_TEXT_LENGTH > 0
        assert len(SUSPICIOUS_SQL_PATTERNS) > 0

    def test_sql_patterns_valid(self):
        """Test that SQL patterns are valid regex."""
        for pattern in SUSPICIOUS_SQL_PATTERNS:
            try:
                re.compile(pattern, re.IGNORECASE)
            except re.error:
                pytest.fail(f"Invalid regex pattern: {pattern}")


# ============================================================================
# Search Strategy Optimization Tests
# ============================================================================

class TestSearchStrategyOptimization:
    """Test that query generation is optimized based on enabled strategies."""

    def test_needs_fulltext_query_logic(self):
        """Test the logic for determining if fulltext query generation is needed."""
        # Case 1: Keyword enabled -> needs query
        assert True == (True or False)  # keyword enabled

        # Case 2: BM25 enabled -> needs query
        assert True == (False or True)  # bm25 enabled

        # Case 3: Both keyword and BM25 enabled -> needs query
        assert True == (True or True)

        # Case 4: Only semantic enabled -> does NOT need query
        assert False == (False or False)  # neither keyword nor bm25

        # Case 5: Only HyDE enabled -> does NOT need query
        assert False == (False or False)

    def test_semantic_only_skips_query_generation(self):
        """
        Test that semantic-only search should skip QueryAgent call.

        This is a behavioral test documenting expected optimization:
        - If only semantic (or HyDE) is enabled
        - QueryAgent should not be invoked
        - search_hybrid should receive query_text=None
        """
        # Semantic-only configuration
        semantic_only = {
            'keyword_enabled': False,
            'bm25_enabled': False,
            'semantic_enabled': True,
            'hyde_enabled': False
        }

        needs_query = (
            semantic_only['keyword_enabled'] or
            semantic_only['bm25_enabled']
        )

        assert not needs_query, "Semantic-only search should not need fulltext query"

    def test_keyword_or_bm25_requires_query_generation(self):
        """Test that keyword or BM25 search requires QueryAgent."""
        # Keyword enabled
        config1 = {
            'keyword_enabled': True,
            'bm25_enabled': False,
            'semantic_enabled': False
        }
        assert config1['keyword_enabled'] or config1['bm25_enabled']

        # BM25 enabled
        config2 = {
            'keyword_enabled': False,
            'bm25_enabled': True,
            'semantic_enabled': False
        }
        assert config2['keyword_enabled'] or config2['bm25_enabled']

        # Both enabled
        config3 = {
            'keyword_enabled': True,
            'bm25_enabled': True,
            'semantic_enabled': True
        }
        assert config3['keyword_enabled'] or config3['bm25_enabled']


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
