"""
Unit tests for PaperCheckerAgent.

Tests the core PaperCheckerAgent class structure, configuration integration,
connection testing, and public API validation.

Test categories:
    1. Initialization tests
    2. Configuration tests
    3. Connection testing
    4. Public API validation
    5. Error handling
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from typing import Dict, Any

from bmlibrarian.paperchecker import (
    PaperCheckerAgent,
    PaperCheckDB,
    StatementExtractor,
    CounterStatementGenerator,
    HyDEGenerator,
    SearchCoordinator,
    VerdictAnalyzer,
    Statement,
    CounterStatement,
    SearchResults,
    ScoredDocument,
    ExtractedCitation,
    CounterReport,
    Verdict,
    PaperCheckResult,
)


# ==================== FIXTURES ====================

@pytest.fixture
def mock_config() -> Dict[str, Any]:
    """Create mock configuration for testing."""
    return {
        "models": {
            "paper_checker_agent": "test-model:latest",
            "scoring_agent": "test-model:latest",
            "citation_agent": "test-model:latest",
        },
        "ollama": {
            "host": "http://localhost:11434",
        },
        "agents": {
            "paper_checker": {
                "temperature": 0.3,
                "top_p": 0.9,
                "max_statements": 2,
                "score_threshold": 3.0,
                "search": {
                    "semantic_limit": 50,
                    "hyde_limit": 50,
                    "keyword_limit": 50,
                    "max_deduplicated": 100,
                },
                "citation": {
                    "min_score": 3,
                    "max_citations_per_statement": 10,
                },
                "hyde": {
                    "num_abstracts": 2,
                    "max_keywords": 10,
                },
            },
        },
    }


@pytest.fixture
def mock_db():
    """Create mock database for testing."""
    db = MagicMock(spec=PaperCheckDB)
    db.test_connection.return_value = True
    db.get_connection.return_value = MagicMock()
    db.save_complete_result.return_value = 1
    return db


@pytest.fixture
def mock_ollama_client():
    """Create mock Ollama client for testing."""
    client = MagicMock()
    client.list.return_value = MagicMock(models=[
        MagicMock(model="test-model:latest"),
        MagicMock(model="gpt-oss:20b"),
    ])
    return client


# ==================== INITIALIZATION TESTS ====================

class TestPaperCheckerAgentInit:
    """Test PaperCheckerAgent initialization."""

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('ollama.Client')
    def test_init_with_default_config(
        self,
        mock_ollama,
        mock_citation,
        mock_scoring,
        mock_db,
        mock_host,
        mock_agent_config,
        mock_model,
        mock_config_fn
    ):
        """Test initialization with default configuration."""
        # Setup mocks
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {
            "temperature": 0.3,
            "top_p": 0.9,
            "max_statements": 2,
        }
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        # Create agent
        agent = PaperCheckerAgent(show_model_info=False)

        # Verify initialization
        assert agent.model == "gpt-oss:20b"
        assert agent.max_statements == 2
        assert mock_db.called
        assert mock_scoring.called
        assert mock_citation.called

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('ollama.Client')
    def test_init_with_custom_db(
        self,
        mock_ollama,
        mock_citation,
        mock_scoring,
        mock_host,
        mock_agent_config,
        mock_model,
        mock_config_fn,
        mock_db
    ):
        """Test initialization with custom database connection."""
        # Setup mocks
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {"max_statements": 3}

        # Create agent with custom db
        agent = PaperCheckerAgent(db_connection=mock_db, show_model_info=False)

        # Verify custom db is used
        assert agent.db == mock_db


class TestPaperCheckerAgentConfiguration:
    """Test configuration integration."""

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('ollama.Client')
    def test_filter_agent_params(
        self,
        mock_ollama,
        mock_citation,
        mock_scoring,
        mock_db,
        mock_host,
        mock_agent_config,
        mock_model,
        mock_config_fn
    ):
        """Test that only supported parameters are passed to BaseAgent."""
        # Setup mocks
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {
            "temperature": 0.3,
            "top_p": 0.9,
            "max_statements": 2,  # Should be filtered out
            "score_threshold": 3.0,  # Should be filtered out
            "unsupported_param": "value",  # Should be filtered out
        }
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        # Create agent
        agent = PaperCheckerAgent(show_model_info=False)

        # Verify only supported params are used
        assert agent.temperature == 0.3
        assert agent.top_p == 0.9

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('ollama.Client')
    def test_max_statements_property(
        self,
        mock_ollama,
        mock_citation,
        mock_scoring,
        mock_db,
        mock_host,
        mock_agent_config,
        mock_model,
        mock_config_fn
    ):
        """Test max_statements property returns correct value."""
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {"max_statements": 5}
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        agent = PaperCheckerAgent(show_model_info=False)

        assert agent.max_statements == 5

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('ollama.Client')
    def test_search_config_property(
        self,
        mock_ollama,
        mock_citation,
        mock_scoring,
        mock_db,
        mock_host,
        mock_agent_config,
        mock_model,
        mock_config_fn
    ):
        """Test search_config property returns correct configuration."""
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {
            "search": {
                "semantic_limit": 100,
                "hyde_limit": 75,
            }
        }
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        agent = PaperCheckerAgent(show_model_info=False)

        assert agent.search_config["semantic_limit"] == 100
        assert agent.search_config["hyde_limit"] == 75


# ==================== CONNECTION TESTING ====================

class TestPaperCheckerAgentConnection:
    """Test connection testing functionality."""

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('ollama.Client')
    def test_connection_all_pass(
        self,
        mock_ollama,
        mock_citation,
        mock_scoring,
        mock_db,
        mock_host,
        mock_agent_config,
        mock_model,
        mock_config_fn
    ):
        """Test connection test passes when all services are available."""
        # Setup mocks
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {}

        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db_instance.test_connection.return_value = True
        mock_db.return_value = mock_db_instance

        mock_scoring_instance = MagicMock()
        mock_scoring_instance.test_connection.return_value = True
        mock_scoring.return_value = mock_scoring_instance

        mock_citation_instance = MagicMock()
        mock_citation_instance.test_connection.return_value = True
        mock_citation.return_value = mock_citation_instance

        mock_ollama_instance = MagicMock()
        mock_ollama_instance.list.return_value = MagicMock(
            models=[MagicMock(model="gpt-oss:20b")]
        )
        mock_ollama.return_value = mock_ollama_instance

        agent = PaperCheckerAgent(show_model_info=False)

        assert agent.test_connection() is True

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('ollama.Client')
    def test_connection_db_failure(
        self,
        mock_ollama,
        mock_citation,
        mock_scoring,
        mock_db,
        mock_host,
        mock_agent_config,
        mock_model,
        mock_config_fn
    ):
        """Test connection test fails when database is unavailable."""
        # Setup mocks
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {}

        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db_instance.test_connection.return_value = False  # DB fails
        mock_db.return_value = mock_db_instance

        mock_ollama_instance = MagicMock()
        mock_ollama_instance.list.return_value = MagicMock(
            models=[MagicMock(model="gpt-oss:20b")]
        )
        mock_ollama.return_value = mock_ollama_instance

        agent = PaperCheckerAgent(show_model_info=False)

        assert agent.test_connection() is False


# ==================== PUBLIC API VALIDATION ====================

class TestPaperCheckerAgentAPI:
    """Test public API validation."""

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('ollama.Client')
    def test_check_abstract_empty_raises_error(
        self,
        mock_ollama,
        mock_citation,
        mock_scoring,
        mock_db,
        mock_host,
        mock_agent_config,
        mock_model,
        mock_config_fn
    ):
        """Test check_abstract raises ValueError on empty input."""
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {}
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        agent = PaperCheckerAgent(show_model_info=False)

        with pytest.raises(ValueError, match="Abstract cannot be empty"):
            agent.check_abstract("")

        with pytest.raises(ValueError, match="Abstract cannot be empty"):
            agent.check_abstract("   ")

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('ollama.Client')
    def test_check_abstract_none_raises_error(
        self,
        mock_ollama,
        mock_citation,
        mock_scoring,
        mock_db,
        mock_host,
        mock_agent_config,
        mock_model,
        mock_config_fn
    ):
        """Test check_abstract raises ValueError on None input."""
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {}
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        agent = PaperCheckerAgent(show_model_info=False)

        with pytest.raises(ValueError, match="Abstract cannot be empty"):
            agent.check_abstract(None)

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('ollama.Client')
    def test_get_agent_type(
        self,
        mock_ollama,
        mock_citation,
        mock_scoring,
        mock_db,
        mock_host,
        mock_agent_config,
        mock_model,
        mock_config_fn
    ):
        """Test get_agent_type returns correct identifier."""
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {}
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        agent = PaperCheckerAgent(show_model_info=False)

        assert agent.get_agent_type() == "PaperCheckerAgent"


# ==================== PROGRESS CALLBACK TESTS ====================

class TestPaperCheckerAgentProgress:
    """Test progress callback functionality."""

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('ollama.Client')
    def test_progress_callback_invoked(
        self,
        mock_ollama,
        mock_citation,
        mock_scoring,
        mock_db,
        mock_host,
        mock_agent_config,
        mock_model,
        mock_config_fn
    ):
        """Test that progress callback is invoked during processing."""
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {}
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        agent = PaperCheckerAgent(show_model_info=False)

        # Create mock callback
        callback = MagicMock()

        # Call _report_progress directly
        agent._report_progress(callback, "Test step", 0.5)

        # Verify callback was invoked
        callback.assert_called_once_with("Test step", 0.5)

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('ollama.Client')
    def test_progress_callback_none_no_error(
        self,
        mock_ollama,
        mock_citation,
        mock_scoring,
        mock_db,
        mock_host,
        mock_agent_config,
        mock_model,
        mock_config_fn
    ):
        """Test that None callback doesn't cause errors."""
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {}
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        agent = PaperCheckerAgent(show_model_info=False)

        # Should not raise an error
        agent._report_progress(None, "Test step", 0.5)


# ==================== COMPONENT INITIALIZATION TESTS ====================

class TestPaperCheckerComponentInit:
    """Test sub-component initialization."""

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('ollama.Client')
    def test_components_initialized(
        self,
        mock_ollama,
        mock_citation,
        mock_scoring,
        mock_db,
        mock_host,
        mock_agent_config,
        mock_model,
        mock_config_fn
    ):
        """Test that all sub-components are initialized."""
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {
            "max_statements": 2,
            "search": {},
            "hyde": {},
        }
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        agent = PaperCheckerAgent(show_model_info=False)

        # Verify all components exist
        assert hasattr(agent, 'statement_extractor')
        assert hasattr(agent, 'counter_generator')
        assert hasattr(agent, 'hyde_generator')
        assert hasattr(agent, 'search_coordinator')
        assert hasattr(agent, 'verdict_analyzer')
        assert hasattr(agent, 'scoring_agent')
        assert hasattr(agent, 'citation_agent')


# ==================== BATCH PROCESSING TESTS ====================

class TestPaperCheckerBatchProcessing:
    """Test batch processing functionality."""

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('ollama.Client')
    def test_batch_empty_list(
        self,
        mock_ollama,
        mock_citation,
        mock_scoring,
        mock_db,
        mock_host,
        mock_agent_config,
        mock_model,
        mock_config_fn
    ):
        """Test batch processing with empty list returns empty results."""
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {}
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        agent = PaperCheckerAgent(show_model_info=False)

        results = agent.check_abstracts_batch([])

        assert results == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
