"""
Unit tests for SearchCoordinator component.

Tests cover:
    1. Initialization and configuration
    2. Multi-strategy search orchestration
    3. Semantic search functionality
    4. HyDE search functionality
    5. Keyword search functionality
    6. Result deduplication and prioritization
    7. Provenance tracking
    8. Error handling and graceful degradation
"""

import pytest
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

from bmlibrarian.paperchecker.components.search_coordinator import (
    SearchCoordinator,
    DEFAULT_SEMANTIC_LIMIT,
    DEFAULT_HYDE_LIMIT,
    DEFAULT_KEYWORD_LIMIT,
    DEFAULT_MAX_DEDUPLICATED,
    DEFAULT_EMBEDDING_MODEL,
    KEYWORD_SEARCH_OPERATOR,
)
from bmlibrarian.paperchecker.data_models import CounterStatement, SearchResults


# ==================== INITIALIZATION TESTS ====================

class TestSearchCoordinatorInit:
    """Test SearchCoordinator initialization."""

    @patch('bmlibrarian.paperchecker.components.search_coordinator.get_db_manager')
    @patch('bmlibrarian.paperchecker.components.search_coordinator.get_ollama_host')
    def test_init_with_defaults(
        self,
        mock_get_host: MagicMock,
        mock_get_db: MagicMock,
        mock_config: Dict[str, Any]
    ) -> None:
        """Test initialization with default parameters."""
        mock_get_host.return_value = "http://localhost:11434"
        mock_get_db.return_value = MagicMock()

        coordinator = SearchCoordinator(config={})

        assert coordinator.semantic_limit == DEFAULT_SEMANTIC_LIMIT
        assert coordinator.hyde_limit == DEFAULT_HYDE_LIMIT
        assert coordinator.keyword_limit == DEFAULT_KEYWORD_LIMIT
        assert coordinator.max_deduplicated == DEFAULT_MAX_DEDUPLICATED
        assert coordinator.embedding_model == DEFAULT_EMBEDDING_MODEL

    @patch('bmlibrarian.paperchecker.components.search_coordinator.get_db_manager')
    @patch('bmlibrarian.paperchecker.components.search_coordinator.get_ollama_host')
    def test_init_with_custom_config(
        self,
        mock_get_host: MagicMock,
        mock_get_db: MagicMock
    ) -> None:
        """Test initialization with custom configuration."""
        mock_get_host.return_value = "http://localhost:11434"
        mock_get_db.return_value = MagicMock()

        config = {
            "semantic_limit": 100,
            "hyde_limit": 75,
            "keyword_limit": 80,
            "max_deduplicated": 150,
            "embedding_model": "custom-embed:latest"
        }
        coordinator = SearchCoordinator(config=config)

        assert coordinator.semantic_limit == 100
        assert coordinator.hyde_limit == 75
        assert coordinator.keyword_limit == 80
        assert coordinator.max_deduplicated == 150
        assert coordinator.embedding_model == "custom-embed:latest"

    @patch('bmlibrarian.paperchecker.components.search_coordinator.get_db_manager')
    @patch('bmlibrarian.paperchecker.components.search_coordinator.get_ollama_host')
    def test_init_with_custom_ollama_host(
        self,
        mock_get_host: MagicMock,
        mock_get_db: MagicMock
    ) -> None:
        """Test initialization with custom Ollama host."""
        mock_get_host.return_value = "http://default:11434"
        mock_get_db.return_value = MagicMock()

        coordinator = SearchCoordinator(
            config={},
            ollama_host="http://custom:11434"
        )

        assert coordinator.ollama_host == "http://custom:11434"


# ==================== CONSTANTS TESTS ====================

class TestSearchCoordinatorConstants:
    """Test module constants are properly defined."""

    def test_default_limits_positive(self) -> None:
        """Test default limit constants are positive."""
        assert DEFAULT_SEMANTIC_LIMIT > 0
        assert DEFAULT_HYDE_LIMIT > 0
        assert DEFAULT_KEYWORD_LIMIT > 0
        assert DEFAULT_MAX_DEDUPLICATED > 0

    def test_keyword_search_operator(self) -> None:
        """Test keyword search operator is valid."""
        assert KEYWORD_SEARCH_OPERATOR in ["|", "&"]


# ==================== EMBEDDING GENERATION TESTS ====================

class TestEmbeddingGeneration:
    """Test embedding generation functionality."""

    @patch('bmlibrarian.paperchecker.components.search_coordinator.get_db_manager')
    @patch('bmlibrarian.paperchecker.components.search_coordinator.get_ollama_host')
    @patch('bmlibrarian.paperchecker.components.search_coordinator.ollama.embeddings')
    def test_generate_embedding_success(
        self,
        mock_embeddings: MagicMock,
        mock_get_host: MagicMock,
        mock_get_db: MagicMock
    ) -> None:
        """Test successful embedding generation."""
        mock_get_host.return_value = "http://localhost:11434"
        mock_get_db.return_value = MagicMock()
        mock_embeddings.return_value = {"embedding": [0.1, 0.2, 0.3]}

        coordinator = SearchCoordinator(config={})
        embedding = coordinator._generate_embedding("test text")

        assert embedding == [0.1, 0.2, 0.3]

    @patch('bmlibrarian.paperchecker.components.search_coordinator.get_db_manager')
    @patch('bmlibrarian.paperchecker.components.search_coordinator.get_ollama_host')
    @patch('bmlibrarian.paperchecker.components.search_coordinator.ollama.embeddings')
    def test_generate_embedding_returns_empty_on_failure(
        self,
        mock_embeddings: MagicMock,
        mock_get_host: MagicMock,
        mock_get_db: MagicMock
    ) -> None:
        """Test that embedding generation returns empty list on failure."""
        mock_get_host.return_value = "http://localhost:11434"
        mock_get_db.return_value = MagicMock()
        mock_embeddings.side_effect = Exception("API error")

        coordinator = SearchCoordinator(config={})
        embedding = coordinator._generate_embedding("test text")

        assert embedding == []

    @patch('bmlibrarian.paperchecker.components.search_coordinator.get_db_manager')
    @patch('bmlibrarian.paperchecker.components.search_coordinator.get_ollama_host')
    def test_generate_embedding_returns_empty_for_empty_text(
        self,
        mock_get_host: MagicMock,
        mock_get_db: MagicMock
    ) -> None:
        """Test that empty text returns empty embedding."""
        mock_get_host.return_value = "http://localhost:11434"
        mock_get_db.return_value = MagicMock()

        coordinator = SearchCoordinator(config={})
        embedding = coordinator._generate_embedding("")

        assert embedding == []


# ==================== TSQUERY ESCAPING TESTS ====================

class TestTsqueryEscaping:
    """Test PostgreSQL tsquery term escaping."""

    @patch('bmlibrarian.paperchecker.components.search_coordinator.get_db_manager')
    @patch('bmlibrarian.paperchecker.components.search_coordinator.get_ollama_host')
    def test_escape_simple_term(
        self,
        mock_get_host: MagicMock,
        mock_get_db: MagicMock
    ) -> None:
        """Test escaping a simple term."""
        mock_get_host.return_value = "http://localhost:11434"
        mock_get_db.return_value = MagicMock()

        coordinator = SearchCoordinator(config={})
        result = coordinator._escape_tsquery_term("diabetes")

        assert result == "diabetes"

    @patch('bmlibrarian.paperchecker.components.search_coordinator.get_db_manager')
    @patch('bmlibrarian.paperchecker.components.search_coordinator.get_ollama_host')
    def test_escape_multi_word_term(
        self,
        mock_get_host: MagicMock,
        mock_get_db: MagicMock
    ) -> None:
        """Test escaping multi-word terms uses AND operator."""
        mock_get_host.return_value = "http://localhost:11434"
        mock_get_db.return_value = MagicMock()

        coordinator = SearchCoordinator(config={})
        result = coordinator._escape_tsquery_term("type 2 diabetes")

        assert "&" in result
        assert "type" in result
        assert "diabetes" in result

    @patch('bmlibrarian.paperchecker.components.search_coordinator.get_db_manager')
    @patch('bmlibrarian.paperchecker.components.search_coordinator.get_ollama_host')
    def test_escape_removes_special_characters(
        self,
        mock_get_host: MagicMock,
        mock_get_db: MagicMock
    ) -> None:
        """Test that special tsquery characters are removed."""
        mock_get_host.return_value = "http://localhost:11434"
        mock_get_db.return_value = MagicMock()

        coordinator = SearchCoordinator(config={})
        result = coordinator._escape_tsquery_term("test'term & other | !term")

        assert "'" not in result
        assert "|" not in result
        assert "!" not in result


# ==================== PRIORITIZATION TESTS ====================

class TestDocumentPrioritization:
    """Test document prioritization logic."""

    @patch('bmlibrarian.paperchecker.components.search_coordinator.get_db_manager')
    @patch('bmlibrarian.paperchecker.components.search_coordinator.get_ollama_host')
    def test_prioritize_multi_strategy_docs(
        self,
        mock_get_host: MagicMock,
        mock_get_db: MagicMock
    ) -> None:
        """Test documents found by multiple strategies are prioritized."""
        mock_get_host.return_value = "http://localhost:11434"
        mock_get_db.return_value = MagicMock()

        coordinator = SearchCoordinator(config={})
        doc_ids = [1, 2, 3, 4, 5]
        provenance = {
            1: ["semantic"],
            2: ["semantic", "hyde", "keyword"],  # Found by all 3
            3: ["semantic", "hyde"],  # Found by 2
            4: ["keyword"],
            5: ["hyde"]
        }

        result = coordinator._prioritize_multi_strategy_docs(
            doc_ids, provenance, limit=3
        )

        # Doc 2 should be first (found by 3 strategies)
        assert result[0] == 2
        # Doc 3 should be second (found by 2 strategies)
        assert result[1] == 3
        # Only 3 docs returned
        assert len(result) == 3

    @patch('bmlibrarian.paperchecker.components.search_coordinator.get_db_manager')
    @patch('bmlibrarian.paperchecker.components.search_coordinator.get_ollama_host')
    def test_prioritize_stable_ordering_for_same_count(
        self,
        mock_get_host: MagicMock,
        mock_get_db: MagicMock
    ) -> None:
        """Test stable ordering when strategy counts are equal."""
        mock_get_host.return_value = "http://localhost:11434"
        mock_get_db.return_value = MagicMock()

        coordinator = SearchCoordinator(config={})
        doc_ids = [5, 3, 1, 4, 2]
        provenance = {
            1: ["semantic"],
            2: ["semantic"],
            3: ["semantic"],
            4: ["semantic"],
            5: ["semantic"]
        }

        result = coordinator._prioritize_multi_strategy_docs(
            doc_ids, provenance, limit=5
        )

        # When counts are equal, should sort by doc_id for stability
        assert result == sorted(result)


# ==================== SEARCH RESULTS LIMITING TESTS ====================

class TestSearchResultsLimiting:
    """Test SearchResults creation with limits."""

    @patch('bmlibrarian.paperchecker.components.search_coordinator.get_db_manager')
    @patch('bmlibrarian.paperchecker.components.search_coordinator.get_ollama_host')
    def test_create_limited_results_filters_provenance(
        self,
        mock_get_host: MagicMock,
        mock_get_db: MagicMock,
        sample_search_results: SearchResults
    ) -> None:
        """Test that limited results filter provenance correctly."""
        mock_get_host.return_value = "http://localhost:11434"
        mock_get_db.return_value = MagicMock()

        coordinator = SearchCoordinator(config={})

        # Get first 3 docs from deduplicated_docs
        limited_docs = sample_search_results.deduplicated_docs[:3]

        result = coordinator._create_limited_results(
            sample_search_results, limited_docs
        )

        # Provenance should only contain limited docs
        assert len(result.provenance) <= len(limited_docs)
        for doc_id in result.provenance:
            assert doc_id in limited_docs

    @patch('bmlibrarian.paperchecker.components.search_coordinator.get_db_manager')
    @patch('bmlibrarian.paperchecker.components.search_coordinator.get_ollama_host')
    def test_create_limited_results_preserves_original_strategy_lists(
        self,
        mock_get_host: MagicMock,
        mock_get_db: MagicMock,
        sample_search_results: SearchResults
    ) -> None:
        """Test that original strategy lists are preserved."""
        mock_get_host.return_value = "http://localhost:11434"
        mock_get_db.return_value = MagicMock()

        coordinator = SearchCoordinator(config={})
        limited_docs = sample_search_results.deduplicated_docs[:2]

        result = coordinator._create_limited_results(
            sample_search_results, limited_docs
        )

        # Original strategy lists should be unchanged
        assert result.semantic_docs == sample_search_results.semantic_docs
        assert result.hyde_docs == sample_search_results.hyde_docs
        assert result.keyword_docs == sample_search_results.keyword_docs

    @patch('bmlibrarian.paperchecker.components.search_coordinator.get_db_manager')
    @patch('bmlibrarian.paperchecker.components.search_coordinator.get_ollama_host')
    def test_create_limited_results_adds_metadata(
        self,
        mock_get_host: MagicMock,
        mock_get_db: MagicMock,
        sample_search_results: SearchResults
    ) -> None:
        """Test that limiting adds appropriate metadata."""
        mock_get_host.return_value = "http://localhost:11434"
        mock_get_db.return_value = MagicMock()

        coordinator = SearchCoordinator(config={})
        limited_docs = sample_search_results.deduplicated_docs[:2]

        result = coordinator._create_limited_results(
            sample_search_results, limited_docs
        )

        assert result.search_metadata["was_limited"] is True
        assert result.search_metadata["limited_count"] == 2


# ==================== CONNECTION TEST ====================

class TestConnectionTest:
    """Test connection testing functionality."""

    @patch('bmlibrarian.paperchecker.components.search_coordinator.get_db_manager')
    @patch('bmlibrarian.paperchecker.components.search_coordinator.get_ollama_host')
    @patch('bmlibrarian.paperchecker.components.search_coordinator.ollama.embeddings')
    def test_test_connection_success(
        self,
        mock_embeddings: MagicMock,
        mock_get_host: MagicMock,
        mock_get_db: MagicMock
    ) -> None:
        """Test successful connection test."""
        mock_get_host.return_value = "http://localhost:11434"

        # Setup database mock
        mock_manager = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1,)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=None)
        mock_manager.get_connection.return_value.__enter__ = MagicMock(
            return_value=mock_conn
        )
        mock_manager.get_connection.return_value.__exit__ = MagicMock(
            return_value=None
        )
        mock_get_db.return_value = mock_manager

        # Setup embedding mock
        mock_embeddings.return_value = {"embedding": [0.1, 0.2]}

        coordinator = SearchCoordinator(config={})
        result = coordinator.test_connection()

        assert result is True

    @patch('bmlibrarian.paperchecker.components.search_coordinator.get_db_manager')
    @patch('bmlibrarian.paperchecker.components.search_coordinator.get_ollama_host')
    def test_test_connection_failure_db_error(
        self,
        mock_get_host: MagicMock,
        mock_get_db: MagicMock
    ) -> None:
        """Test connection test failure due to database error."""
        mock_get_host.return_value = "http://localhost:11434"
        mock_manager = MagicMock()
        mock_manager.get_connection.side_effect = Exception("DB connection failed")
        mock_get_db.return_value = mock_manager

        coordinator = SearchCoordinator(config={})
        result = coordinator.test_connection()

        assert result is False


# ==================== SEARCH INTEGRATION TESTS ====================

class TestSearchIntegration:
    """Integration tests for the search method."""

    @patch('bmlibrarian.paperchecker.components.search_coordinator.get_db_manager')
    @patch('bmlibrarian.paperchecker.components.search_coordinator.get_ollama_host')
    def test_search_raises_when_all_strategies_fail(
        self,
        mock_get_host: MagicMock,
        mock_get_db: MagicMock,
        sample_counter_statement: CounterStatement
    ) -> None:
        """Test that RuntimeError is raised when all strategies fail."""
        mock_get_host.return_value = "http://localhost:11434"
        mock_get_db.return_value = MagicMock()

        coordinator = SearchCoordinator(config={})

        # Mock all search methods to return empty
        coordinator.search_semantic = MagicMock(return_value=[])
        coordinator.search_hyde = MagicMock(return_value=[])
        coordinator.search_keyword = MagicMock(return_value=[])

        with pytest.raises(RuntimeError, match="All search strategies failed"):
            coordinator.search(sample_counter_statement)

    @patch('bmlibrarian.paperchecker.components.search_coordinator.get_db_manager')
    @patch('bmlibrarian.paperchecker.components.search_coordinator.get_ollama_host')
    def test_search_succeeds_with_one_strategy(
        self,
        mock_get_host: MagicMock,
        mock_get_db: MagicMock,
        sample_counter_statement: CounterStatement
    ) -> None:
        """Test that search succeeds if at least one strategy works."""
        mock_get_host.return_value = "http://localhost:11434"
        mock_get_db.return_value = MagicMock()

        coordinator = SearchCoordinator(config={})

        # Mock semantic to return results, others fail
        coordinator.search_semantic = MagicMock(return_value=[1, 2, 3])
        coordinator.search_hyde = MagicMock(side_effect=Exception("HyDE failed"))
        coordinator.search_keyword = MagicMock(side_effect=Exception("Keyword failed"))

        result = coordinator.search(sample_counter_statement)

        assert isinstance(result, SearchResults)
        assert len(result.semantic_docs) == 3
        assert len(result.deduplicated_docs) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
