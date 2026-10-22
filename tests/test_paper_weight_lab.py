"""
Tests for the paper weight lab's database helper functions

Tests cover:
- Database helper functions (search_documents, get_recent_assessments, get_document_metadata)
- Helper function error handling
- Constants validation

Note: Qt/GUI tests are not included as they require a display environment.
The helpers live in bmlibrarian.agents.paper_weight.db and reach the database
through get_db_manager(), which these tests replace with a mock.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from bmlibrarian.agents.paper_weight import (
    search_documents,
    get_recent_assessments,
    get_document_metadata,
    SEARCH_RESULT_LIMIT,
    RECENT_ASSESSMENTS_LIMIT,
)

DB_MANAGER_PATH = 'bmlibrarian.agents.paper_weight.db.get_db_manager'
PUBMED_SOURCE_ID = 1


def mock_db(mock_cursor: MagicMock):
    """Patch get_db_manager() so its connection yields ``mock_cursor``."""
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    db_manager = MagicMock()
    db_manager.get_connection.return_value.__enter__.return_value = mock_conn
    db_manager.get_cached_source_ids.return_value = {'pubmed': PUBMED_SOURCE_ID}
    return patch(DB_MANAGER_PATH, return_value=db_manager)


def failing_db(message: str):
    """Patch get_db_manager() so connecting raises ``message``."""
    db_manager = MagicMock()
    db_manager.get_connection.side_effect = Exception(message)
    return patch(DB_MANAGER_PATH, return_value=db_manager)


def search_row(doc_id, title, pmid, doi, year):
    """A search_documents result row: id, title, pmid, doi, year, has_pdf, has_full_text, pdf_filename, pdf_url."""
    return (doc_id, title, pmid, doi, year, False, False, None, None)


class TestConstants:
    """Tests for module constants."""

    def test_search_limit_positive(self):
        """Ensure search limit is positive."""
        assert SEARCH_RESULT_LIMIT > 0, "Search limit must be positive"

    def test_recent_assessments_limit_positive(self):
        """Ensure recent assessments limit is positive."""
        assert RECENT_ASSESSMENTS_LIMIT > 0, "Recent assessments limit must be positive"


class TestSearchDocuments:
    """Tests for search_documents function."""

    def test_search_by_pmid(self):
        """Test searching by PMID (numeric query)."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            search_row(12345, 'Test Paper Title', 12345678, '10.1234/test', 2023)
        ]

        with mock_db(mock_cursor):
            results = search_documents('12345678')

        assert len(results) == 1
        assert results[0]['id'] == 12345
        assert results[0]['title'] == 'Test Paper Title'
        assert results[0]['pmid'] == 12345678
        assert results[0]['doi'] == '10.1234/test'
        assert results[0]['year'] == 2023

    def test_search_by_doi(self):
        """Test searching by DOI pattern."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            search_row(54321, 'DOI Paper', 87654321, '10.5678/example', 2022)
        ]

        with mock_db(mock_cursor):
            results = search_documents('10.5678/example')

        assert len(results) == 1
        assert results[0]['doi'] == '10.5678/example'

    def test_search_by_title(self):
        """Test searching by title keywords."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            search_row(111, 'Cardiovascular Health Study', 11111111, '10.1111/cvh', 2021),
            search_row(222, 'Heart Disease Prevention', 22222222, '10.2222/hdp', 2020)
        ]

        with mock_db(mock_cursor):
            results = search_documents('cardiovascular')

        assert len(results) == 2
        assert results[0]['title'] == 'Cardiovascular Health Study'

    def test_search_no_results(self):
        """Test search with no results."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []

        with mock_db(mock_cursor):
            results = search_documents('nonexistent')

        assert results == []

    def test_search_database_error(self):
        """Test search with database error returns empty list."""
        with failing_db("Database connection failed"):
            results = search_documents('test')

        assert results == []

    def test_search_respects_custom_limit(self):
        """Test that search respects custom limit parameter."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []

        with mock_db(mock_cursor):
            search_documents('test', limit=10)

        # Verify the query was called with the limit
        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args
        # The second parameter should be a tuple containing the limit
        assert 10 in call_args[0][1]


class TestGetRecentAssessments:
    """Tests for get_recent_assessments function."""

    def test_get_recent_assessments_success(self):
        """Test fetching recent assessments."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            (12345, 'Recent Paper 1', 11111111, '10.1111/rp1', 7.5,
             datetime(2024, 1, 15, 10, 30), '1.0.0'),
            (54321, 'Recent Paper 2', 22222222, '10.2222/rp2', 6.8,
             datetime(2024, 1, 14, 9, 0), '1.0.0'),
        ]

        with mock_db(mock_cursor):
            results = get_recent_assessments()

        assert len(results) == 2
        assert results[0]['document_id'] == 12345
        assert results[0]['title'] == 'Recent Paper 1'
        assert results[0]['final_weight'] == 7.5
        assert results[0]['version'] == '1.0.0'

    def test_get_recent_assessments_with_limit(self):
        """Test fetching recent assessments with custom limit."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            (12345, 'Paper', 11111111, '10.1111/p', 7.0,
             datetime(2024, 1, 15), '1.0.0'),
        ]

        with mock_db(mock_cursor):
            get_recent_assessments(limit=5)

        # Verify the query was called with the limit (after the PubMed source_id)
        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args
        assert call_args[0][1] == (PUBMED_SOURCE_ID, 5)

    def test_get_recent_assessments_empty(self):
        """Test fetching recent assessments when none exist."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []

        with mock_db(mock_cursor):
            results = get_recent_assessments()

        assert results == []

    def test_get_recent_assessments_database_error(self):
        """Test get_recent_assessments with database error."""
        with failing_db("Database error"):
            results = get_recent_assessments()

        assert results == []


class TestGetDocumentMetadata:
    """Tests for get_document_metadata function."""

    def test_get_document_metadata_success(self):
        """Test fetching document metadata."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (
            12345,
            'Test Paper Title',
            'This is the abstract...',
            11111111,
            '10.1111/test',
            'Smith J, Johnson A',
            2023
        )

        with mock_db(mock_cursor):
            result = get_document_metadata(12345)

        assert result is not None
        assert result['id'] == 12345
        assert result['title'] == 'Test Paper Title'
        assert result['abstract'] == 'This is the abstract...'
        assert result['pmid'] == 11111111
        assert result['doi'] == '10.1111/test'
        assert result['authors'] == 'Smith J, Johnson A'
        assert result['year'] == 2023

    def test_get_document_metadata_not_found(self):
        """Test fetching non-existent document."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None

        with mock_db(mock_cursor):
            result = get_document_metadata(99999)

        assert result is None

    def test_get_document_metadata_database_error(self):
        """Test get_document_metadata with database error."""
        with failing_db("Connection failed"):
            result = get_document_metadata(12345)

        assert result is None

    def test_get_document_metadata_with_null_fields(self):
        """Test fetching document with null optional fields."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (
            12345,
            'Paper Without Abstract',
            None,  # No abstract
            None,  # No PMID
            None,  # No DOI
            None,  # No authors
            None   # No year
        )

        with mock_db(mock_cursor):
            result = get_document_metadata(12345)

        assert result is not None
        assert result['id'] == 12345
        assert result['title'] == 'Paper Without Abstract'
        assert result['abstract'] is None
        assert result['pmid'] is None
        assert result['doi'] is None
        assert result['authors'] is None
        assert result['year'] is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
