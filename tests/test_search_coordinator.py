"""
Tests for SearchCoordinator component.

This module contains comprehensive tests for the multi-strategy search functionality,
including unit tests with mocked database and Ollama responses, and integration tests
that can optionally run against a real database and Ollama server.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, List, Any

from bmlibrarian.paperchecker.components import SearchCoordinator
from bmlibrarian.paperchecker.data_models import (
    Statement,
    CounterStatement,
    SearchResults,
    VALID_SEARCH_STRATEGIES,
)


# Test Fixtures


@pytest.fixture
def search_config() -> Dict[str, Any]:
    """Search configuration for tests."""
    return {
        "semantic_limit": 50,
        "hyde_limit": 50,
        "keyword_limit": 50,
        "max_deduplicated": 100,
        "embedding_model": "snowflake-arctic-embed2:latest",
    }


@pytest.fixture
def minimal_config() -> Dict[str, Any]:
    """Minimal search configuration."""
    return {
        "semantic_limit": 10,
        "hyde_limit": 10,
        "keyword_limit": 10,
        "max_deduplicated": 20,
    }


@pytest.fixture
def sample_statement() -> Statement:
    """Sample Statement for testing."""
    return Statement(
        text="Metformin demonstrates superior efficacy over GLP-1 receptor agonists",
        context="Results from a large randomized controlled trial",
        statement_type="finding",
        confidence=0.9,
        statement_order=1,
    )


@pytest.fixture
def sample_counter_statement(sample_statement: Statement) -> CounterStatement:
    """Sample CounterStatement with all search materials."""
    return CounterStatement(
        original_statement=sample_statement,
        negated_text="GLP-1 receptor agonists are superior or equivalent to metformin",
        hyde_abstracts=[
            "Background: GLP-1 agonists show promise. Methods: RCT with 1000 patients. Results: GLP-1 reduced HbA1c by 1.8% vs metformin 1.2% (p<0.001). Conclusion: GLP-1 superior.",
            "Objective: Compare GLP-1 and metformin. Design: Meta-analysis of 20 trials. Findings: GLP-1 associated with better outcomes (OR 1.45). Conclusion: GLP-1 preferred.",
        ],
        keywords=[
            "GLP-1",
            "metformin",
            "type 2 diabetes",
            "glycemic control",
            "HbA1c",
            "semaglutide",
            "liraglutide",
            "randomized controlled trial",
        ],
        generation_metadata={"model": "test", "timestamp": "2024-01-01T00:00:00"},
    )


@pytest.fixture
def mock_db_manager():
    """Mock DatabaseManager for testing."""
    mock_manager = MagicMock()
    mock_conn = MagicMock()
    mock_cursor = MagicMock()

    # Set up context manager returns
    mock_manager.get_connection.return_value.__enter__ = Mock(return_value=mock_conn)
    mock_manager.get_connection.return_value.__exit__ = Mock(return_value=None)
    mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = Mock(return_value=None)

    return mock_manager, mock_cursor


# Unit Tests - Initialization


class TestInitialization:
    """Tests for SearchCoordinator initialization."""

    @patch("bmlibrarian.paperchecker.components.search_coordinator.get_db_manager")
    def test_init_with_defaults(self, mock_get_db, search_config):
        """Test initialization with default settings."""
        mock_get_db.return_value = MagicMock()

        coordinator = SearchCoordinator(config=search_config)

        assert coordinator.semantic_limit == 50
        assert coordinator.hyde_limit == 50
        assert coordinator.keyword_limit == 50
        assert coordinator.max_deduplicated == 100

    @patch("bmlibrarian.paperchecker.components.search_coordinator.get_db_manager")
    def test_init_with_custom_limits(self, mock_get_db, minimal_config):
        """Test initialization with custom limits."""
        mock_get_db.return_value = MagicMock()

        coordinator = SearchCoordinator(config=minimal_config)

        assert coordinator.semantic_limit == 10
        assert coordinator.hyde_limit == 10
        assert coordinator.keyword_limit == 10
        assert coordinator.max_deduplicated == 20

    @patch("bmlibrarian.paperchecker.components.search_coordinator.get_db_manager")
    def test_init_with_empty_config(self, mock_get_db):
        """Test initialization with empty config uses defaults."""
        mock_get_db.return_value = MagicMock()

        coordinator = SearchCoordinator(config={})

        # Should use default values
        assert coordinator.semantic_limit == 50  # DEFAULT_SEMANTIC_LIMIT
        assert coordinator.hyde_limit == 50  # DEFAULT_HYDE_LIMIT
        assert coordinator.keyword_limit == 50  # DEFAULT_KEYWORD_LIMIT
        assert coordinator.max_deduplicated == 100  # DEFAULT_MAX_DEDUPLICATED

    @patch("bmlibrarian.paperchecker.components.search_coordinator.get_db_manager")
    def test_init_with_query_timeout(self, mock_get_db):
        """Test initialization with custom query timeout."""
        mock_get_db.return_value = MagicMock()

        config = {"query_timeout_ms": 600000}  # 10 minutes
        coordinator = SearchCoordinator(config=config)

        assert coordinator.query_timeout_ms == 600000


# Unit Tests - Semantic Search


class TestSemanticSearch:
    """Tests for semantic search functionality.

    Note: Semantic search now uses PostgreSQL's semantic_docsearch() function
    which handles embedding generation server-side.
    """

    @patch("bmlibrarian.paperchecker.components.search_coordinator.get_db_manager")
    def test_semantic_search_returns_doc_ids(self, mock_get_db, search_config):
        """Test semantic search returns list of document IDs."""
        mock_get_db.return_value = MagicMock()

        coordinator = SearchCoordinator(config=search_config)

        # Mock database results from semantic_docsearch function
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [(123, 0.9), (456, 0.8), (789, 0.7)]

        with patch.object(coordinator.db_manager, "get_connection") as mock_conn:
            mock_conn.return_value.__enter__ = Mock(return_value=MagicMock())
            mock_conn.return_value.__exit__ = Mock(return_value=None)
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__ = Mock(
                return_value=mock_cursor
            )
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__exit__ = Mock(
                return_value=None
            )

            results = coordinator.search_semantic("test query", limit=10)

        assert isinstance(results, list)
        assert results == [123, 456, 789]

    @patch("bmlibrarian.paperchecker.components.search_coordinator.get_db_manager")
    def test_semantic_search_handles_db_embedding_failure(self, mock_get_db, search_config):
        """Test semantic search handles server-side embedding failure gracefully."""
        mock_get_db.return_value = MagicMock()

        coordinator = SearchCoordinator(config=search_config)

        # Simulate server-side embedding failure via exception
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = [
            None,  # SET statement_timeout
            Exception("Failed to generate embedding for search text"),
        ]

        with patch.object(coordinator.db_manager, "get_connection") as mock_conn:
            mock_conn.return_value.__enter__ = Mock(return_value=MagicMock())
            mock_conn.return_value.__exit__ = Mock(return_value=None)
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__ = Mock(
                return_value=mock_cursor
            )
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__exit__ = Mock(
                return_value=None
            )

            results = coordinator.search_semantic("test query", limit=10)

        assert results == []

    @patch("bmlibrarian.paperchecker.components.search_coordinator.get_db_manager")
    def test_semantic_search_handles_timeout(self, mock_get_db, search_config):
        """Test semantic search handles query timeout gracefully."""
        mock_get_db.return_value = MagicMock()

        coordinator = SearchCoordinator(config=search_config)

        # Simulate timeout exception
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = [
            None,  # SET statement_timeout
            Exception("canceling statement due to statement timeout"),
        ]

        with patch.object(coordinator.db_manager, "get_connection") as mock_conn:
            mock_conn.return_value.__enter__ = Mock(return_value=MagicMock())
            mock_conn.return_value.__exit__ = Mock(return_value=None)
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__ = Mock(
                return_value=mock_cursor
            )
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__exit__ = Mock(
                return_value=None
            )

            results = coordinator.search_semantic("test query", limit=10)

        assert results == []


# Unit Tests - HyDE Search


class TestHyDESearch:
    """Tests for HyDE search functionality.

    Note: HyDE search now uses PostgreSQL's semantic_docsearch() function
    which handles embedding generation server-side.
    """

    @patch("bmlibrarian.paperchecker.components.search_coordinator.get_db_manager")
    def test_hyde_search_returns_deduplicated_ids(self, mock_get_db, search_config):
        """Test HyDE search returns deduplicated document IDs."""
        mock_get_db.return_value = MagicMock()

        coordinator = SearchCoordinator(config=search_config)

        # Mock database results (same doc 123 in both searches)
        mock_cursor = MagicMock()
        mock_cursor.fetchall.side_effect = [
            [(123, 0.9), (456, 0.8)],  # First HyDE abstract
            [(123, 0.85), (789, 0.7)],  # Second HyDE abstract
        ]

        with patch.object(coordinator.db_manager, "get_connection") as mock_conn:
            mock_conn.return_value.__enter__ = Mock(return_value=MagicMock())
            mock_conn.return_value.__exit__ = Mock(return_value=None)
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__ = Mock(
                return_value=mock_cursor
            )
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__exit__ = Mock(
                return_value=None
            )

            results = coordinator.search_hyde(
                hyde_abstracts=["abstract1", "abstract2"],
                limit=10
            )

        # Should have 3 unique documents (123 deduplicated)
        assert len(results) == 3
        assert 123 in results
        assert 456 in results
        assert 789 in results

    @patch("bmlibrarian.paperchecker.components.search_coordinator.get_db_manager")
    def test_hyde_search_empty_abstracts_returns_empty(self, mock_get_db, search_config):
        """Test HyDE search with empty abstracts list returns empty list."""
        mock_get_db.return_value = MagicMock()

        coordinator = SearchCoordinator(config=search_config)

        results = coordinator.search_hyde(hyde_abstracts=[], limit=10)

        assert results == []

    @patch("bmlibrarian.paperchecker.components.search_coordinator.get_db_manager")
    def test_hyde_search_partial_failure_continues(self, mock_get_db, search_config):
        """Test HyDE search continues if some abstracts fail."""
        mock_get_db.return_value = MagicMock()

        coordinator = SearchCoordinator(config=search_config)

        # First abstract fails with embedding error, second succeeds
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = [
            None,  # SET timeout for first abstract
            Exception("Failed to generate embedding"),  # First query fails
            None,  # SET timeout for second abstract
            None,  # Second query succeeds
        ]
        mock_cursor.fetchall.return_value = [(123, 0.9)]

        with patch.object(coordinator.db_manager, "get_connection") as mock_conn:
            mock_conn.return_value.__enter__ = Mock(return_value=MagicMock())
            mock_conn.return_value.__exit__ = Mock(return_value=None)
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__ = Mock(
                return_value=mock_cursor
            )
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__exit__ = Mock(
                return_value=None
            )

            results = coordinator.search_hyde(
                hyde_abstracts=["abstract1", "abstract2"],
                limit=10
            )

        # Should still return results from successful search
        assert len(results) == 1
        assert results[0] == 123

    @patch("bmlibrarian.paperchecker.components.search_coordinator.get_db_manager")
    def test_hyde_search_all_failures_returns_empty(self, mock_get_db, search_config):
        """Test HyDE search returns empty list if all abstracts fail.

        Note: Changed from raising RuntimeError to returning empty list
        to allow other search strategies to continue.
        """
        mock_get_db.return_value = MagicMock()

        coordinator = SearchCoordinator(config=search_config)

        # All abstracts fail with embedding errors
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("Failed to generate embedding")

        with patch.object(coordinator.db_manager, "get_connection") as mock_conn:
            mock_conn.return_value.__enter__ = Mock(return_value=MagicMock())
            mock_conn.return_value.__exit__ = Mock(return_value=None)
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__ = Mock(
                return_value=mock_cursor
            )
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__exit__ = Mock(
                return_value=None
            )

            results = coordinator.search_hyde(hyde_abstracts=["abstract1"], limit=10)

        # Should return empty list instead of raising
        assert results == []


# Unit Tests - Keyword Search


class TestKeywordSearch:
    """Tests for keyword search functionality."""

    @patch("bmlibrarian.paperchecker.components.search_coordinator.get_db_manager")
    def test_keyword_search_returns_doc_ids(self, mock_get_db, search_config):
        """Test keyword search returns list of document IDs."""
        mock_get_db.return_value = MagicMock()

        coordinator = SearchCoordinator(config=search_config)

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [(123, 0.9), (456, 0.8), (789, 0.7)]

        with patch.object(coordinator.db_manager, "get_connection") as mock_conn:
            mock_conn.return_value.__enter__ = Mock(return_value=MagicMock())
            mock_conn.return_value.__exit__ = Mock(return_value=None)
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__ = Mock(
                return_value=mock_cursor
            )
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__exit__ = Mock(
                return_value=None
            )

            results = coordinator.search_keyword(
                keywords=["diabetes", "treatment"],
                limit=10
            )

        assert isinstance(results, list)
        assert results == [123, 456, 789]

    @patch("bmlibrarian.paperchecker.components.search_coordinator.get_db_manager")
    def test_keyword_search_empty_keywords_returns_empty(self, mock_get_db, search_config):
        """Test keyword search with empty keywords returns empty list."""
        mock_get_db.return_value = MagicMock()

        coordinator = SearchCoordinator(config=search_config)

        results = coordinator.search_keyword(keywords=[], limit=10)

        assert results == []


# Unit Tests - Tsquery Escaping


class TestTsqueryEscaping:
    """Tests for tsquery term escaping."""

    @patch("bmlibrarian.paperchecker.components.search_coordinator.get_db_manager")
    def test_escape_special_characters(self, mock_get_db, search_config):
        """Test escaping of special tsquery characters."""
        mock_get_db.return_value = MagicMock()
        coordinator = SearchCoordinator(config=search_config)

        # Test single-word terms - special chars should be removed
        assert coordinator._escape_tsquery_term("test&term") == "testterm"
        assert coordinator._escape_tsquery_term("test|term") == "testterm"
        assert coordinator._escape_tsquery_term("test!term") == "testterm"
        assert coordinator._escape_tsquery_term("(test)") == "test"
        assert coordinator._escape_tsquery_term("test:term") == "testterm"
        assert coordinator._escape_tsquery_term("test'term") == "testterm"

        # Multi-word terms use & to join words (after removing special chars)
        result = coordinator._escape_tsquery_term("test term")
        assert " & " in result

    @patch("bmlibrarian.paperchecker.components.search_coordinator.get_db_manager")
    def test_escape_multi_word_terms(self, mock_get_db, search_config):
        """Test multi-word terms are joined with AND."""
        mock_get_db.return_value = MagicMock()
        coordinator = SearchCoordinator(config=search_config)

        result = coordinator._escape_tsquery_term("type 2 diabetes")
        assert "&" in result

    @patch("bmlibrarian.paperchecker.components.search_coordinator.get_db_manager")
    def test_escape_empty_term(self, mock_get_db, search_config):
        """Test empty term returns fallback."""
        mock_get_db.return_value = MagicMock()
        coordinator = SearchCoordinator(config=search_config)

        result = coordinator._escape_tsquery_term("")
        assert result == "dummy_search_term"


# Unit Tests - Full Search


class TestFullSearch:
    """Tests for the full multi-strategy search."""

    @patch("bmlibrarian.paperchecker.components.search_coordinator.get_db_manager")
    def test_search_combines_all_strategies(
        self, mock_get_db, search_config, sample_counter_statement
    ):
        """Test that search combines results from all strategies."""
        mock_get_db.return_value = MagicMock()

        coordinator = SearchCoordinator(config=search_config)

        # Mock individual search methods
        with patch.object(coordinator, "search_semantic", return_value=[1, 2, 3]):
            with patch.object(coordinator, "search_hyde", return_value=[2, 3, 4]):
                with patch.object(coordinator, "search_keyword", return_value=[3, 4, 5]):
                    results = coordinator.search(sample_counter_statement)

        assert isinstance(results, SearchResults)
        assert results.semantic_docs == [1, 2, 3]
        assert results.hyde_docs == [2, 3, 4]
        assert results.keyword_docs == [3, 4, 5]
        # Deduplicated should have all unique IDs
        assert set(results.deduplicated_docs) == {1, 2, 3, 4, 5}

    @patch("bmlibrarian.paperchecker.components.search_coordinator.get_db_manager")
    def test_search_provenance_tracking(
        self, mock_get_db, search_config, sample_counter_statement
    ):
        """Test that provenance is tracked correctly."""
        mock_get_db.return_value = MagicMock()

        coordinator = SearchCoordinator(config=search_config)

        # Doc 2 found by semantic and hyde, doc 3 by all three
        with patch.object(coordinator, "search_semantic", return_value=[1, 2, 3]):
            with patch.object(coordinator, "search_hyde", return_value=[2, 3]):
                with patch.object(coordinator, "search_keyword", return_value=[3, 4]):
                    results = coordinator.search(sample_counter_statement)

        # Check provenance
        assert "semantic" in results.provenance[1]
        assert "hyde" not in results.provenance[1]

        assert "semantic" in results.provenance[2]
        assert "hyde" in results.provenance[2]

        assert "semantic" in results.provenance[3]
        assert "hyde" in results.provenance[3]
        assert "keyword" in results.provenance[3]

    @patch("bmlibrarian.paperchecker.components.search_coordinator.get_db_manager")
    def test_search_continues_on_partial_failure(
        self, mock_get_db, search_config, sample_counter_statement
    ):
        """Test search continues when some strategies fail."""
        mock_get_db.return_value = MagicMock()

        coordinator = SearchCoordinator(config=search_config)

        # Semantic fails, others succeed
        with patch.object(coordinator, "search_semantic", side_effect=RuntimeError("Failed")):
            with patch.object(coordinator, "search_hyde", return_value=[1, 2]):
                with patch.object(coordinator, "search_keyword", return_value=[3]):
                    results = coordinator.search(sample_counter_statement)

        assert results.semantic_docs == []
        assert results.hyde_docs == [1, 2]
        assert results.keyword_docs == [3]
        assert set(results.deduplicated_docs) == {1, 2, 3}

    @patch("bmlibrarian.paperchecker.components.search_coordinator.get_db_manager")
    def test_search_raises_when_all_fail(
        self, mock_get_db, search_config, sample_counter_statement
    ):
        """Test search raises when all strategies fail."""
        mock_get_db.return_value = MagicMock()

        coordinator = SearchCoordinator(config=search_config)

        with patch.object(coordinator, "search_semantic", return_value=[]):
            with patch.object(coordinator, "search_hyde", return_value=[]):
                with patch.object(coordinator, "search_keyword", return_value=[]):
                    with pytest.raises(RuntimeError, match="All search strategies failed"):
                        coordinator.search(sample_counter_statement)


# Unit Tests - Prioritization


class TestPrioritization:
    """Tests for multi-strategy document prioritization."""

    @patch("bmlibrarian.paperchecker.components.search_coordinator.get_db_manager")
    def test_prioritize_multi_strategy_docs(self, mock_get_db, search_config):
        """Test documents found by multiple strategies are prioritized."""
        mock_get_db.return_value = MagicMock()
        coordinator = SearchCoordinator(config=search_config)

        doc_ids = [1, 2, 3, 4, 5]
        provenance = {
            1: ["semantic"],  # 1 strategy
            2: ["semantic", "hyde"],  # 2 strategies
            3: ["semantic", "hyde", "keyword"],  # 3 strategies
            4: ["keyword"],  # 1 strategy
            5: ["hyde", "keyword"],  # 2 strategies
        }

        result = coordinator._prioritize_multi_strategy_docs(doc_ids, provenance, limit=3)

        # Doc 3 should be first (3 strategies), then 2 and 5 (2 strategies each)
        assert result[0] == 3
        assert len(result) == 3

    @patch("bmlibrarian.paperchecker.components.search_coordinator.get_db_manager")
    def test_prioritize_respects_limit(self, mock_get_db, search_config):
        """Test prioritization respects the limit parameter."""
        mock_get_db.return_value = MagicMock()
        coordinator = SearchCoordinator(config=search_config)

        doc_ids = list(range(1, 11))  # 10 documents
        provenance = {i: ["semantic"] for i in doc_ids}

        result = coordinator._prioritize_multi_strategy_docs(doc_ids, provenance, limit=5)

        assert len(result) == 5


# Unit Tests - Result Limiting


class TestResultLimiting:
    """Tests for result limiting."""

    @patch("bmlibrarian.paperchecker.components.search_coordinator.get_db_manager")
    def test_limits_results_when_exceeds_max(
        self, mock_get_db, minimal_config, sample_counter_statement
    ):
        """Test that results are limited when exceeding max_deduplicated."""
        mock_get_db.return_value = MagicMock()

        coordinator = SearchCoordinator(config=minimal_config)

        # Return more docs than max_deduplicated (20)
        many_docs = list(range(1, 51))  # 50 documents

        with patch.object(coordinator, "search_semantic", return_value=many_docs[:20]):
            with patch.object(coordinator, "search_hyde", return_value=many_docs[10:30]):
                with patch.object(coordinator, "search_keyword", return_value=many_docs[20:40]):
                    results = coordinator.search(sample_counter_statement)

        # Should be limited to max_deduplicated (20)
        assert len(results.deduplicated_docs) <= 20


# Unit Tests - Connection Testing


class TestConnectionTesting:
    """Tests for connection testing functionality.

    Note: test_connection now uses semantic_docsearch() to verify
    both database and Ollama connectivity in one call.
    """

    @patch("bmlibrarian.paperchecker.components.search_coordinator.get_db_manager")
    def test_connection_success(self, mock_get_db, search_config):
        """Test successful connection check."""
        mock_get_db.return_value = MagicMock()

        coordinator = SearchCoordinator(config=search_config)

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1,)
        mock_cursor.fetchall.return_value = []  # Empty result from semantic_docsearch

        with patch.object(coordinator.db_manager, "get_connection") as mock_conn:
            mock_conn.return_value.__enter__ = Mock(return_value=MagicMock())
            mock_conn.return_value.__exit__ = Mock(return_value=None)
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__ = Mock(
                return_value=mock_cursor
            )
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__exit__ = Mock(
                return_value=None
            )

            result = coordinator.test_connection()

        assert result is True

    @patch("bmlibrarian.paperchecker.components.search_coordinator.get_db_manager")
    def test_connection_failure_db(self, mock_get_db, search_config):
        """Test connection failure when database fails."""
        mock_get_db.return_value = MagicMock()

        coordinator = SearchCoordinator(config=search_config)

        with patch.object(coordinator.db_manager, "get_connection") as mock_conn:
            mock_conn.side_effect = Exception("Database error")

            result = coordinator.test_connection()

        assert result is False

    @patch("bmlibrarian.paperchecker.components.search_coordinator.get_db_manager")
    def test_connection_failure_embedding(self, mock_get_db, search_config):
        """Test connection failure when server-side embedding fails."""
        mock_get_db.return_value = MagicMock()

        coordinator = SearchCoordinator(config=search_config)

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1,)  # Basic SELECT 1 works
        # But semantic_docsearch fails with embedding error
        mock_cursor.execute.side_effect = [
            None,  # SELECT 1
            None,  # SET statement_timeout
            Exception("Failed to generate embedding for search text"),
        ]

        with patch.object(coordinator.db_manager, "get_connection") as mock_conn:
            mock_conn.return_value.__enter__ = Mock(return_value=MagicMock())
            mock_conn.return_value.__exit__ = Mock(return_value=None)
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__ = Mock(
                return_value=mock_cursor
            )
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__exit__ = Mock(
                return_value=None
            )

            result = coordinator.test_connection()

        assert result is False

    @patch("bmlibrarian.paperchecker.components.search_coordinator.get_db_manager")
    def test_connection_failure_missing_function(self, mock_get_db, search_config):
        """Test connection failure when semantic_docsearch function is missing."""
        mock_get_db.return_value = MagicMock()

        coordinator = SearchCoordinator(config=search_config)

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1,)
        mock_cursor.execute.side_effect = [
            None,  # SELECT 1
            None,  # SET statement_timeout
            Exception("function semantic_docsearch(text, double, integer) does not exist"),
        ]

        with patch.object(coordinator.db_manager, "get_connection") as mock_conn:
            mock_conn.return_value.__enter__ = Mock(return_value=MagicMock())
            mock_conn.return_value.__exit__ = Mock(return_value=None)
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__ = Mock(
                return_value=mock_cursor
            )
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__exit__ = Mock(
                return_value=None
            )

            result = coordinator.test_connection()

        assert result is False


# Integration Tests - These require a running database and Ollama server


@pytest.mark.integration
class TestIntegration:
    """Integration tests requiring running services."""

    @pytest.fixture
    def live_coordinator(self):
        """Create coordinator for live testing."""
        config = {
            "semantic_limit": 10,
            "hyde_limit": 10,
            "keyword_limit": 10,
            "max_deduplicated": 20,
        }
        try:
            return SearchCoordinator(config=config)
        except Exception:
            pytest.skip("Services not available")

    def test_live_semantic_search(self, live_coordinator):
        """Test semantic search with real services."""
        if not live_coordinator.test_connection():
            pytest.skip("Services not available")

        results = live_coordinator.search_semantic(
            "diabetes treatment efficacy",
            limit=5
        )

        assert isinstance(results, list)
        assert all(isinstance(doc_id, int) for doc_id in results)

    def test_live_keyword_search(self, live_coordinator):
        """Test keyword search with real services."""
        if not live_coordinator.test_connection():
            pytest.skip("Services not available")

        results = live_coordinator.search_keyword(
            keywords=["diabetes", "metformin"],
            limit=5
        )

        assert isinstance(results, list)
        assert all(isinstance(doc_id, int) for doc_id in results)

    def test_live_full_search(self, live_coordinator, sample_counter_statement):
        """Test full search with real services."""
        if not live_coordinator.test_connection():
            pytest.skip("Services not available")

        results = live_coordinator.search(sample_counter_statement)

        assert isinstance(results, SearchResults)
        assert isinstance(results.deduplicated_docs, list)
        assert isinstance(results.provenance, dict)

        # Verify provenance is valid
        for doc_id in results.deduplicated_docs:
            assert doc_id in results.provenance
            assert set(results.provenance[doc_id]).issubset(VALID_SEARCH_STRATEGIES)
