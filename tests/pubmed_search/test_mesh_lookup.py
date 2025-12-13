"""
Unit tests for MeSH lookup service.

Tests the MeSHLookup class for term validation and caching.
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from bmlibrarian.pubmed_search.mesh_lookup import MeSHLookup
from bmlibrarian.pubmed_search.data_types import MeSHTerm


class TestMeSHLookupInit:
    """Tests for MeSHLookup initialization."""

    def test_init_creates_cache_dir(self) -> None:
        """Test that initialization creates cache directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "test_cache"
            lookup = MeSHLookup(cache_dir=cache_dir)
            assert cache_dir.exists()

    def test_init_creates_cache_db(self) -> None:
        """Test that initialization creates cache database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            lookup = MeSHLookup(cache_dir=cache_dir)
            cache_path = cache_dir / "mesh_cache.db"
            assert cache_path.exists()


class TestMeSHLookupValidation:
    """Tests for MeSH term validation."""

    @pytest.fixture
    def lookup(self) -> MeSHLookup:
        """Create a MeSHLookup with temporary cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            return MeSHLookup(cache_dir=Path(tmpdir))

    def test_validate_empty_term(self, lookup: MeSHLookup) -> None:
        """Test validation of empty term."""
        result = lookup.validate_term("")
        assert result.is_valid is False

    def test_validate_whitespace_term(self, lookup: MeSHLookup) -> None:
        """Test validation of whitespace-only term."""
        result = lookup.validate_term("   ")
        assert result.is_valid is False

    @patch("bmlibrarian.pubmed_search.mesh_lookup.MeSHLookup._make_request")
    def test_validate_term_api_success(self, mock_request: MagicMock, lookup: MeSHLookup) -> None:
        """Test successful term validation via API."""
        # Mock successful API response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "esearchresult": {
                "count": "1",
                "idlist": ["D002318"],
            }
        }
        mock_request.return_value = mock_response

        result = lookup.validate_term("Cardiovascular Diseases", use_cache=False)
        assert result.is_valid is True
        assert result.descriptor_ui == "D002318"

    @patch("bmlibrarian.pubmed_search.mesh_lookup.MeSHLookup._make_request")
    def test_validate_term_not_found(self, mock_request: MagicMock, lookup: MeSHLookup) -> None:
        """Test validation when term not found by any strategy."""
        # Mock empty response for all API calls (esearch, NLM API, entry term search)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "esearchresult": {
                "count": "0",
                "idlist": [],
            }
        }
        mock_request.return_value = mock_response

        result = lookup.validate_term("Not A Real Term XYZ123", use_cache=False)
        assert result.is_valid is False

    @patch("bmlibrarian.pubmed_search.mesh_lookup.MeSHLookup._make_request")
    def test_validate_term_via_nlm_api_fallback(self, mock_request: MagicMock, lookup: MeSHLookup) -> None:
        """Test validation falls back to NLM MeSH API when esearch fails."""
        # First call (esearch) returns empty, second call (NLM API) returns match
        esearch_response = MagicMock()
        esearch_response.json.return_value = {
            "esearchresult": {"count": "0", "idlist": []}
        }
        nlm_response = MagicMock()
        nlm_response.json.return_value = [
            {
                "resource": "http://id.nlm.nih.gov/mesh/D019586",
                "label": "Intracranial Hypertension"
            }
        ]
        mock_request.side_effect = [esearch_response, nlm_response]

        result = lookup.validate_term("Intracranial Hypertension", use_cache=False)
        assert result.is_valid is True
        assert result.descriptor_ui == "D019586"
        assert result.descriptor_name == "Intracranial Hypertension"

    @patch("bmlibrarian.pubmed_search.mesh_lookup.MeSHLookup._make_request")
    def test_validate_common_mesh_terms(self, mock_request: MagicMock, lookup: MeSHLookup) -> None:
        """Test validation of commonly used MeSH terms."""
        # Mock esearch finding the term
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "esearchresult": {"count": "1", "idlist": ["068956"]}
        }
        mock_request.return_value = mock_response

        # These are real MeSH terms that should validate
        terms_to_test = [
            "Sensitivity and Specificity",
            "Diagnostic Accuracy",
        ]

        for term in terms_to_test:
            result = lookup.validate_term(term, use_cache=False)
            assert result.is_valid is True, f"Expected {term} to be valid"

    @patch("bmlibrarian.pubmed_search.mesh_lookup.MeSHLookup._make_request")
    def test_validate_term_api_failure(self, mock_request: MagicMock, lookup: MeSHLookup) -> None:
        """Test validation when API fails."""
        mock_request.return_value = None

        result = lookup.validate_term("Exercise", use_cache=False)
        assert result.is_valid is False


class TestMeSHLookupCaching:
    """Tests for MeSH term caching."""

    def test_cache_hit(self) -> None:
        """Test that cached terms are returned without API call."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lookup = MeSHLookup(cache_dir=Path(tmpdir))

            # Manually save a term to cache
            term = MeSHTerm(
                descriptor_ui="D015444",
                descriptor_name="Exercise",
                is_valid=True,
            )
            lookup._save_to_cache("exercise", term)

            # Retrieve from cache (no API call needed)
            with patch.object(lookup, "_make_request") as mock_request:
                result = lookup.validate_term("exercise", use_cache=True)
                mock_request.assert_not_called()
                assert result.is_valid is True
                assert result.descriptor_name == "Exercise"

    def test_cache_invalid_term(self) -> None:
        """Test that invalid terms are cached."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lookup = MeSHLookup(cache_dir=Path(tmpdir))

            # Save invalid term
            invalid_term = MeSHTerm(
                descriptor_ui="",
                descriptor_name="Invalid",
                is_valid=False,
            )
            lookup._save_to_cache("invalid", invalid_term)

            # Should return cached invalid result
            result = lookup.validate_term("invalid", use_cache=True)
            assert result.is_valid is False

    def test_clear_cache(self) -> None:
        """Test cache clearing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lookup = MeSHLookup(cache_dir=Path(tmpdir))

            # Add some cached terms
            term = MeSHTerm(
                descriptor_ui="D015444",
                descriptor_name="Exercise",
                is_valid=True,
            )
            lookup._save_to_cache("exercise", term)

            # Verify cache has entries
            stats = lookup.get_cache_stats()
            assert stats["cached_terms"] >= 1

            # Clear cache
            cleared = lookup.clear_cache()
            assert cleared >= 1

            # Verify cache is empty
            stats = lookup.get_cache_stats()
            assert stats["cached_terms"] == 0


class TestMeSHLookupBatchValidation:
    """Tests for batch term validation."""

    @patch("bmlibrarian.pubmed_search.mesh_lookup.MeSHLookup.validate_term")
    def test_validate_terms_list(self, mock_validate: MagicMock) -> None:
        """Test validation of multiple terms."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lookup = MeSHLookup(cache_dir=Path(tmpdir))

            # Mock validate_term responses
            mock_validate.side_effect = [
                MeSHTerm("D015444", "Exercise", is_valid=True),
                MeSHTerm("", "Invalid", is_valid=False),
                MeSHTerm("D006331", "Heart Diseases", is_valid=True),
            ]

            terms = ["Exercise", "Invalid", "Heart Diseases"]
            results = lookup.validate_terms(terms)

            assert len(results) == 3
            assert results[0].is_valid is True
            assert results[1].is_valid is False
            assert results[2].is_valid is True


class TestMeSHLookupExpansion:
    """Tests for MeSH term expansion."""

    def test_expand_invalid_term(self) -> None:
        """Test expansion of invalid term returns original."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lookup = MeSHLookup(cache_dir=Path(tmpdir))

            # Save as invalid
            invalid = MeSHTerm("", "NotReal", is_valid=False)
            lookup._save_to_cache("notreal", invalid)

            expanded = lookup.expand_term("NotReal")
            assert expanded == ["NotReal"]

    def test_expand_term_with_entry_terms(self) -> None:
        """Test expansion includes entry terms."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lookup = MeSHLookup(cache_dir=Path(tmpdir))

            # Save term with entry terms
            term = MeSHTerm(
                descriptor_ui="D015444",
                descriptor_name="Exercise",
                entry_terms=["Physical Activity", "Aerobic Exercise"],
                is_valid=True,
            )
            lookup._save_to_cache("exercise", term)

            expanded = lookup.expand_term("exercise")
            assert "Exercise" in expanded
            assert "Physical Activity" in expanded
            assert "Aerobic Exercise" in expanded


class TestMeSHLookupStats:
    """Tests for cache statistics."""

    def test_get_cache_stats(self) -> None:
        """Test cache statistics retrieval."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lookup = MeSHLookup(cache_dir=Path(tmpdir))

            stats = lookup.get_cache_stats()
            assert "cached_terms" in stats
            assert "cached_lookups" in stats
            assert "invalid_terms_cached" in stats
            assert "cache_path" in stats
            assert "cache_ttl_days" in stats


class TestMeSHLookupCacheCleanup:
    """Tests for MeSH cache cleanup functionality."""

    def test_cleanup_expired_cache_alias(self) -> None:
        """Test that cleanup_expired_cache is an alias for clear_expired_cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lookup = MeSHLookup(cache_dir=Path(tmpdir))

            # Both methods should exist and be callable
            assert hasattr(lookup, "cleanup_expired_cache")
            assert hasattr(lookup, "clear_expired_cache")
            assert callable(lookup.cleanup_expired_cache)
            assert callable(lookup.clear_expired_cache)

    def test_cleanup_expired_cache_empty(self) -> None:
        """Test cleanup with no expired entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lookup = MeSHLookup(cache_dir=Path(tmpdir))

            # Add a fresh cache entry
            term = MeSHTerm(
                descriptor_ui="D015444",
                descriptor_name="Exercise",
                is_valid=True,
            )
            lookup._save_to_cache("exercise", term)

            # Cleanup should remove 0 entries (nothing expired)
            cleared = lookup.cleanup_expired_cache()
            assert cleared == 0

            # Entry should still be in cache
            stats = lookup.get_cache_stats()
            assert stats["cached_terms"] >= 1

    def test_clear_expired_cache_with_expired_entries(self) -> None:
        """Test clearing expired entries from cache."""
        from datetime import datetime, timedelta
        import sqlite3
        import json

        with tempfile.TemporaryDirectory() as tmpdir:
            lookup = MeSHLookup(cache_dir=Path(tmpdir), cache_ttl_days=30)

            # Add an entry directly with an old timestamp (expired)
            old_date = (datetime.now() - timedelta(days=60)).isoformat()
            with sqlite3.connect(lookup.cache_path) as conn:
                conn.execute(
                    """
                    INSERT INTO mesh_terms
                    (descriptor_ui, descriptor_name, tree_numbers, entry_terms, scope_note, cached_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    ("D001234", "Old Term", "[]", "[]", None, old_date),
                )
                conn.execute(
                    """
                    INSERT INTO mesh_name_lookup
                    (search_name, descriptor_ui, is_valid, cached_at)
                    VALUES (?, ?, 1, ?)
                    """,
                    ("old term", "D001234", old_date),
                )

            # Verify we have an expired entry
            stats = lookup.get_cache_stats()
            assert stats["expired_entries"] >= 1

            # Clear expired entries
            cleared = lookup.clear_expired_cache()
            assert cleared >= 1

            # Verify expired entries are gone
            stats = lookup.get_cache_stats()
            assert stats["expired_entries"] == 0
