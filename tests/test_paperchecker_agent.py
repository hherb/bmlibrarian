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
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_init_with_default_config(
        self,
        mock_ollama,
        mock_search_coord,
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
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_init_with_custom_db(
        self,
        mock_ollama,
        mock_search_coord,
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
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_filter_agent_params(
        self,
        mock_ollama,
        mock_search_coord,
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
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_max_statements_property(
        self,
        mock_ollama,
        mock_search_coord,
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
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_search_config_property(
        self,
        mock_ollama,
        mock_search_coord,
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
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_connection_all_pass(
        self,
        mock_ollama,
        mock_search_coord,
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
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_connection_db_failure(
        self,
        mock_ollama,
        mock_search_coord,
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
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_check_abstract_empty_raises_error(
        self,
        mock_ollama,
        mock_search_coord,
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
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_check_abstract_none_raises_error(
        self,
        mock_ollama,
        mock_search_coord,
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
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_get_agent_type(
        self,
        mock_ollama,
        mock_search_coord,
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
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_progress_callback_invoked(
        self,
        mock_ollama,
        mock_search_coord,
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
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_progress_callback_none_no_error(
        self,
        mock_ollama,
        mock_search_coord,
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
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_components_initialized(
        self,
        mock_ollama,
        mock_search_coord,
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
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_batch_empty_list(
        self,
        mock_ollama,
        mock_search_coord,
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


# ==================== DOCUMENT SCORING TESTS ====================

class TestPaperCheckerDocumentScoring:
    """Test document scoring integration."""

    @pytest.fixture
    def sample_statement(self) -> Statement:
        """Create a sample statement for testing."""
        return Statement(
            text="Metformin is superior to GLP-1 agonists for type 2 diabetes",
            context="In this study, we compared the efficacy...",
            statement_type="finding",
            confidence=0.9,
            statement_order=1
        )

    @pytest.fixture
    def sample_counter_statement(self, sample_statement: Statement) -> CounterStatement:
        """Create a sample counter-statement for testing."""
        return CounterStatement(
            original_statement=sample_statement,
            negated_text="GLP-1 agonists are superior or equivalent to metformin",
            hyde_abstracts=["A hypothetical study showing GLP-1 superiority..."],
            keywords=["GLP-1", "metformin", "diabetes"],
            generation_metadata={"model": "test-model"}
        )

    @pytest.fixture
    def sample_search_results(self) -> SearchResults:
        """Create sample search results for testing."""
        return SearchResults(
            semantic_docs=[1, 2, 3],
            hyde_docs=[2, 3, 4],
            keyword_docs=[3, 4, 5],
            deduplicated_docs=[1, 2, 3, 4, 5],
            provenance={
                1: ["semantic"],
                2: ["semantic", "hyde"],
                3: ["semantic", "hyde", "keyword"],
                4: ["hyde", "keyword"],
                5: ["keyword"]
            },
            search_metadata={"test": True}
        )

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('bmlibrarian.paperchecker.agent.get_db_manager')
    @patch('ollama.Client')
    def test_build_scoring_question(
        self,
        mock_ollama,
        mock_db_manager,
        mock_search_coord,
        mock_citation,
        mock_scoring,
        mock_db,
        mock_host,
        mock_agent_config,
        mock_model,
        mock_config_fn,
        sample_counter_statement
    ):
        """Test scoring question construction."""
        # Setup mocks
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {}
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        agent = PaperCheckerAgent(show_model_info=False)

        # Build question
        question = agent._build_scoring_question(sample_counter_statement)

        # Verify question contains key elements
        assert "GLP-1 agonists are superior or equivalent to metformin" in question
        assert "Metformin is superior to GLP-1 agonists" in question
        assert "evidence" in question.lower()
        assert "contradicts" in question.lower()

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('bmlibrarian.paperchecker.agent.get_db_manager')
    @patch('ollama.Client')
    def test_get_score_explanation_with_title(
        self,
        mock_ollama,
        mock_db_manager,
        mock_search_coord,
        mock_citation,
        mock_scoring,
        mock_db,
        mock_host,
        mock_agent_config,
        mock_model,
        mock_config_fn
    ):
        """Test score explanation includes title."""
        # Setup mocks
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {}
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        agent = PaperCheckerAgent(show_model_info=False)

        document = {
            "id": 1,
            "title": "GLP-1 Receptor Agonists in Type 2 Diabetes",
            "abstract": "This study evaluates..."
        }

        explanation = agent._get_score_explanation(
            score=4,
            document=document,
            reasoning="Document provides relevant evidence"
        )

        # Should include reasoning and title
        assert "Document provides relevant evidence" in explanation
        assert "GLP-1 Receptor Agonists" in explanation

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('bmlibrarian.paperchecker.agent.get_db_manager')
    @patch('ollama.Client')
    def test_get_score_explanation_long_title_truncated(
        self,
        mock_ollama,
        mock_db_manager,
        mock_search_coord,
        mock_citation,
        mock_scoring,
        mock_db,
        mock_host,
        mock_agent_config,
        mock_model,
        mock_config_fn
    ):
        """Test long titles are truncated in explanation."""
        # Setup mocks
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {}
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        agent = PaperCheckerAgent(show_model_info=False)

        # Create document with very long title
        long_title = "A" * 200
        document = {
            "id": 1,
            "title": long_title,
            "abstract": "..."
        }

        explanation = agent._get_score_explanation(
            score=3,
            document=document,
            reasoning="Some reasoning"
        )

        # Title should be truncated
        assert "..." in explanation
        assert len(explanation) < len(long_title) + 100  # Reasonable length

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('bmlibrarian.paperchecker.agent.get_db_manager')
    @patch('ollama.Client')
    def test_fetch_documents_empty_list(
        self,
        mock_ollama,
        mock_db_manager,
        mock_search_coord,
        mock_citation,
        mock_scoring,
        mock_db,
        mock_host,
        mock_agent_config,
        mock_model,
        mock_config_fn
    ):
        """Test fetching with empty document list returns empty dict."""
        # Setup mocks
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {}
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        agent = PaperCheckerAgent(show_model_info=False)

        result = agent._fetch_documents([])

        assert result == {}

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('bmlibrarian.paperchecker.agent.get_db_manager')
    @patch('ollama.Client')
    def test_score_documents_empty_search_results(
        self,
        mock_ollama,
        mock_db_manager,
        mock_search_coord,
        mock_citation,
        mock_scoring,
        mock_db,
        mock_host,
        mock_agent_config,
        mock_model,
        mock_config_fn,
        sample_counter_statement
    ):
        """Test scoring with empty search results returns empty list."""
        # Setup mocks
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {"score_threshold": 3.0}
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        agent = PaperCheckerAgent(show_model_info=False)

        # Create empty search results
        empty_results = SearchResults(
            semantic_docs=[],
            hyde_docs=[],
            keyword_docs=[],
            deduplicated_docs=[],
            provenance={},
            search_metadata={}
        )

        result = agent._score_documents(sample_counter_statement, empty_results)

        assert result == []

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('bmlibrarian.paperchecker.agent.get_db_manager')
    @patch('ollama.Client')
    def test_score_documents_filters_below_threshold(
        self,
        mock_ollama,
        mock_db_manager,
        mock_search_coord,
        mock_citation,
        mock_scoring,
        mock_db,
        mock_host,
        mock_agent_config,
        mock_model,
        mock_config_fn,
        sample_counter_statement,
        sample_search_results
    ):
        """Test that documents below threshold are filtered out."""
        # Setup mocks
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {
            "score_threshold": 3.0,
            "scoring": {"batch_size": 10, "early_stop_count": 0}
        }
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        # Mock database manager to return documents
        mock_db_mgr = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {"id": 1, "title": "Doc 1", "abstract": "Abstract 1"},
            {"id": 2, "title": "Doc 2", "abstract": "Abstract 2"},
            {"id": 3, "title": "Doc 3", "abstract": "Abstract 3"},
        ]
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=None)
        mock_db_mgr.get_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db_mgr.get_connection.return_value.__exit__ = MagicMock(return_value=None)
        mock_db_manager.return_value = mock_db_mgr

        # Mock scoring agent to return different scores
        mock_scoring_instance = MagicMock()
        mock_scoring_instance.evaluate_document.side_effect = [
            {"score": 2, "reasoning": "Low relevance"},  # Below threshold
            {"score": 4, "reasoning": "High relevance"},  # Above threshold
            {"score": 5, "reasoning": "Very high relevance"},  # Above threshold
        ]
        mock_scoring.return_value = mock_scoring_instance

        agent = PaperCheckerAgent(show_model_info=False)
        agent.scoring_agent = mock_scoring_instance

        # Limit search results to 3 docs for test
        limited_results = SearchResults(
            semantic_docs=[1, 2, 3],
            hyde_docs=[],
            keyword_docs=[],
            deduplicated_docs=[1, 2, 3],
            provenance={1: ["semantic"], 2: ["semantic"], 3: ["semantic"]},
            search_metadata={}
        )

        result = agent._score_documents(sample_counter_statement, limited_results)

        # Should only have docs above threshold (2 docs)
        assert len(result) == 2
        assert all(doc.score >= 3 for doc in result)

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('bmlibrarian.paperchecker.agent.get_db_manager')
    @patch('ollama.Client')
    def test_score_documents_sorted_descending(
        self,
        mock_ollama,
        mock_db_manager,
        mock_search_coord,
        mock_citation,
        mock_scoring,
        mock_db,
        mock_host,
        mock_agent_config,
        mock_model,
        mock_config_fn,
        sample_counter_statement
    ):
        """Test that scored documents are sorted by score descending."""
        # Setup mocks
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {
            "score_threshold": 3.0,
            "scoring": {"batch_size": 10, "early_stop_count": 0}
        }
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        # Mock database manager
        mock_db_mgr = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {"id": 1, "title": "Doc 1", "abstract": "Abstract 1"},
            {"id": 2, "title": "Doc 2", "abstract": "Abstract 2"},
            {"id": 3, "title": "Doc 3", "abstract": "Abstract 3"},
        ]
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=None)
        mock_db_mgr.get_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db_mgr.get_connection.return_value.__exit__ = MagicMock(return_value=None)
        mock_db_manager.return_value = mock_db_mgr

        # Mock scoring agent - return scores in non-sorted order
        mock_scoring_instance = MagicMock()
        mock_scoring_instance.evaluate_document.side_effect = [
            {"score": 3, "reasoning": "Medium"},
            {"score": 5, "reasoning": "High"},
            {"score": 4, "reasoning": "Good"},
        ]
        mock_scoring.return_value = mock_scoring_instance

        agent = PaperCheckerAgent(show_model_info=False)
        agent.scoring_agent = mock_scoring_instance

        search_results = SearchResults(
            semantic_docs=[1, 2, 3],
            hyde_docs=[],
            keyword_docs=[],
            deduplicated_docs=[1, 2, 3],
            provenance={1: ["semantic"], 2: ["semantic"], 3: ["semantic"]},
            search_metadata={}
        )

        result = agent._score_documents(sample_counter_statement, search_results)

        # Verify sorted descending
        scores = [doc.score for doc in result]
        assert scores == sorted(scores, reverse=True)

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('bmlibrarian.paperchecker.agent.get_db_manager')
    @patch('ollama.Client')
    def test_score_documents_preserves_provenance(
        self,
        mock_ollama,
        mock_db_manager,
        mock_search_coord,
        mock_citation,
        mock_scoring,
        mock_db,
        mock_host,
        mock_agent_config,
        mock_model,
        mock_config_fn,
        sample_counter_statement
    ):
        """Test that provenance is preserved in scored documents."""
        # Setup mocks
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {
            "score_threshold": 3.0,
            "scoring": {"batch_size": 10, "early_stop_count": 0}
        }
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        # Mock database manager
        mock_db_mgr = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {"id": 1, "title": "Doc 1", "abstract": "Abstract 1"},
            {"id": 2, "title": "Doc 2", "abstract": "Abstract 2"},
        ]
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=None)
        mock_db_mgr.get_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db_mgr.get_connection.return_value.__exit__ = MagicMock(return_value=None)
        mock_db_manager.return_value = mock_db_mgr

        # Mock scoring agent
        mock_scoring_instance = MagicMock()
        mock_scoring_instance.evaluate_document.side_effect = [
            {"score": 4, "reasoning": "Relevant"},
            {"score": 5, "reasoning": "Very relevant"},
        ]
        mock_scoring.return_value = mock_scoring_instance

        agent = PaperCheckerAgent(show_model_info=False)
        agent.scoring_agent = mock_scoring_instance

        search_results = SearchResults(
            semantic_docs=[1],
            hyde_docs=[1, 2],
            keyword_docs=[2],
            deduplicated_docs=[1, 2],
            provenance={
                1: ["semantic", "hyde"],
                2: ["hyde", "keyword"]
            },
            search_metadata={}
        )

        result = agent._score_documents(sample_counter_statement, search_results)

        # Verify provenance is preserved
        assert len(result) == 2
        for scored_doc in result:
            expected_provenance = search_results.provenance[scored_doc.doc_id]
            assert set(scored_doc.found_by) == set(expected_provenance)


# ==================== COUNTER-REPORT GENERATION TESTS ====================

class TestPaperCheckerCounterReportGeneration:
    """Test counter-report generation functionality."""

    @pytest.fixture
    def sample_statement(self) -> Statement:
        """Create a sample statement for testing."""
        return Statement(
            text="Metformin is superior to GLP-1 agonists",
            context="Comparison study context",
            statement_type="finding",
            confidence=0.9,
            statement_order=1
        )

    @pytest.fixture
    def sample_counter_statement(self, sample_statement: Statement) -> CounterStatement:
        """Create a sample counter-statement for testing."""
        return CounterStatement(
            original_statement=sample_statement,
            negated_text="GLP-1 agonists are superior or equivalent to metformin",
            hyde_abstracts=["Hypothetical abstract showing GLP-1 efficacy..."],
            keywords=["GLP-1", "metformin", "diabetes"],
            generation_metadata={"model": "test-model"}
        )

    @pytest.fixture
    def sample_citations(self) -> list:
        """Create sample citations for testing."""
        return [
            ExtractedCitation(
                doc_id=1,
                passage="GLP-1 agonists demonstrated superior HbA1c reduction of 1.8% compared to metformin's 1.2% (p<0.001).",
                relevance_score=5,
                full_citation="Smith J, et al. GLP-1 vs Metformin Study. Diabetes Care. 2023. doi:10.1234/example",
                metadata={"pmid": 12345678, "year": 2023},
                citation_order=1
            ),
            ExtractedCitation(
                doc_id=2,
                passage="Meta-analysis of 20 trials showed GLP-1 associated with better cardiovascular outcomes (HR 0.85, 95% CI 0.75-0.95).",
                relevance_score=4,
                full_citation="Jones A, et al. GLP-1 Meta-Analysis. JAMA. 2022. doi:10.1234/another",
                metadata={"pmid": 23456789, "year": 2022},
                citation_order=2
            )
        ]

    @pytest.fixture
    def sample_search_results(self) -> SearchResults:
        """Create sample search results for testing."""
        return SearchResults(
            semantic_docs=[1, 2, 3],
            hyde_docs=[2, 3, 4],
            keyword_docs=[3, 4, 5],
            deduplicated_docs=[1, 2, 3, 4, 5],
            provenance={
                1: ["semantic"],
                2: ["semantic", "hyde"],
                3: ["semantic", "hyde", "keyword"],
                4: ["hyde", "keyword"],
                5: ["keyword"]
            },
            search_metadata={}
        )

    @pytest.fixture
    def sample_scored_docs(self) -> list:
        """Create sample scored documents for testing."""
        return [
            ScoredDocument(
                doc_id=1,
                document={"id": 1, "title": "Doc 1"},
                score=5,
                explanation="High relevance",
                supports_counter=True,
                found_by=["semantic"]
            ),
            ScoredDocument(
                doc_id=2,
                document={"id": 2, "title": "Doc 2"},
                score=4,
                explanation="Good relevance",
                supports_counter=True,
                found_by=["semantic", "hyde"]
            )
        ]

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_build_report_prompt(
        self,
        mock_ollama,
        mock_search_coord,
        mock_citation,
        mock_scoring,
        mock_db,
        mock_host,
        mock_agent_config,
        mock_model,
        mock_config_fn,
        sample_counter_statement,
        sample_citations
    ):
        """Test report prompt construction."""
        # Setup mocks
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {}
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        agent = PaperCheckerAgent(show_model_info=False)
        prompt = agent._build_report_prompt(sample_counter_statement, sample_citations)

        # Should contain counter-statement
        assert "GLP-1 agonists are superior or equivalent to metformin" in prompt

        # Should contain original statement for context
        assert "Metformin is superior to GLP-1 agonists" in prompt

        # Should contain all citations
        for citation in sample_citations:
            assert citation.passage in prompt

        # Should contain instructions
        assert "inline" in prompt.lower()
        assert "citation" in prompt.lower()
        assert "professional" in prompt.lower()

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_parse_report_response_clean(
        self,
        mock_ollama,
        mock_search_coord,
        mock_citation,
        mock_scoring,
        mock_db,
        mock_host,
        mock_agent_config,
        mock_model,
        mock_config_fn
    ):
        """Test parsing of clean LLM responses."""
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {}
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        agent = PaperCheckerAgent(show_model_info=False)

        clean_response = "This is a clean report with [1] citation and [2] another."
        result = agent._parse_report_response(clean_response)
        assert result == clean_response

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_parse_report_response_with_prefix(
        self,
        mock_ollama,
        mock_search_coord,
        mock_citation,
        mock_scoring,
        mock_db,
        mock_host,
        mock_agent_config,
        mock_model,
        mock_config_fn
    ):
        """Test parsing of responses with Summary: prefix."""
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {}
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        agent = PaperCheckerAgent(show_model_info=False)

        prefixed_response = "Summary: This is a report with prefix that should be removed."
        result = agent._parse_report_response(prefixed_response)
        assert result == "This is a report with prefix that should be removed."
        assert not result.startswith("Summary:")

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_parse_report_response_with_code_blocks(
        self,
        mock_ollama,
        mock_search_coord,
        mock_citation,
        mock_scoring,
        mock_db,
        mock_host,
        mock_agent_config,
        mock_model,
        mock_config_fn
    ):
        """Test parsing of responses wrapped in code blocks."""
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {}
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        agent = PaperCheckerAgent(show_model_info=False)

        # Test with ```markdown wrapper
        code_blocked = "```markdown\nThis is in code block that should be unwrapped. This is additional text to meet minimum length.\n```"
        result = agent._parse_report_response(code_blocked)
        assert result == "This is in code block that should be unwrapped. This is additional text to meet minimum length."
        assert "```" not in result

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_parse_report_response_too_short_raises(
        self,
        mock_ollama,
        mock_search_coord,
        mock_citation,
        mock_scoring,
        mock_db,
        mock_host,
        mock_agent_config,
        mock_model,
        mock_config_fn
    ):
        """Test that too-short responses raise ValueError."""
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {}
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        agent = PaperCheckerAgent(show_model_info=False)

        with pytest.raises(ValueError, match="too short"):
            agent._parse_report_response("Short")

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_generate_empty_report(
        self,
        mock_ollama,
        mock_search_coord,
        mock_citation,
        mock_scoring,
        mock_db,
        mock_host,
        mock_agent_config,
        mock_model,
        mock_config_fn,
        sample_counter_statement,
        sample_search_results,
        sample_scored_docs
    ):
        """Test generation of empty report when no citations available."""
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {"score_threshold": 3.0}
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        agent = PaperCheckerAgent(show_model_info=False)

        report = agent._generate_empty_report(
            sample_counter_statement, sample_search_results, sample_scored_docs
        )

        assert report.num_citations == 0
        assert len(report.citations) == 0
        assert len(report.summary) > 0
        assert "no substantial evidence" in report.summary.lower()
        assert report.generation_metadata.get("empty_report") is True

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_calculate_search_stats(
        self,
        mock_ollama,
        mock_search_coord,
        mock_citation,
        mock_scoring,
        mock_db,
        mock_host,
        mock_agent_config,
        mock_model,
        mock_config_fn,
        sample_search_results,
        sample_scored_docs,
        sample_citations
    ):
        """Test search statistics calculation."""
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {}
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        agent = PaperCheckerAgent(show_model_info=False)

        stats = agent._calculate_search_stats(
            sample_search_results, sample_scored_docs, sample_citations
        )

        # Verify correct counts
        assert stats["documents_found"] == 5
        assert stats["documents_scored"] == 2
        assert stats["documents_cited"] == 2
        assert stats["citations_extracted"] == 2

        # Verify strategy breakdown
        assert stats["search_strategies"]["semantic"] == 3
        assert stats["search_strategies"]["hyde"] == 3
        assert stats["search_strategies"]["keyword"] == 3

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_generate_counter_report_with_citations(
        self,
        mock_ollama,
        mock_search_coord,
        mock_citation,
        mock_scoring,
        mock_db,
        mock_host,
        mock_agent_config,
        mock_model,
        mock_config_fn,
        sample_counter_statement,
        sample_citations,
        sample_search_results,
        sample_scored_docs
    ):
        """Test counter-report generation with citations."""
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {"temperature": 0.3}
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        # Mock the ollama client's generate method
        mock_ollama_instance = MagicMock()
        mock_ollama_instance.generate.return_value = {
            "response": "Evidence from multiple studies supports the efficacy of GLP-1 agonists. "
                       "In a 2023 study, Smith et al. demonstrated superior HbA1c reduction [1]. "
                       "Furthermore, a meta-analysis by Jones et al. in 2022 showed improved "
                       "cardiovascular outcomes [2]. These findings suggest GLP-1 agonists "
                       "may be preferable for certain patient populations.",
            "prompt_eval_count": 100,
            "eval_count": 50,
            "eval_duration": 1000000000,
            "prompt_eval_duration": 500000000
        }
        mock_ollama.return_value = mock_ollama_instance

        agent = PaperCheckerAgent(show_model_info=False)
        agent.client = mock_ollama_instance

        report = agent._generate_counter_report(
            sample_counter_statement,
            sample_citations,
            sample_search_results,
            sample_scored_docs
        )

        # Verify report structure
        assert isinstance(report, CounterReport)
        assert len(report.summary) > 50
        assert report.num_citations == len(sample_citations)
        assert len(report.citations) == len(sample_citations)
        assert isinstance(report.search_stats, dict)

        # Verify search stats populated
        assert report.search_stats["documents_found"] == 5
        assert report.search_stats["documents_scored"] == 2
        assert report.search_stats["citations_extracted"] == 2

        # Verify metadata
        assert "model" in report.generation_metadata
        assert "timestamp" in report.generation_metadata

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_generate_counter_report_empty_citations(
        self,
        mock_ollama,
        mock_search_coord,
        mock_citation,
        mock_scoring,
        mock_db,
        mock_host,
        mock_agent_config,
        mock_model,
        mock_config_fn,
        sample_counter_statement,
        sample_search_results,
        sample_scored_docs
    ):
        """Test counter-report generation with no citations returns empty report."""
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {"score_threshold": 3.0}
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        agent = PaperCheckerAgent(show_model_info=False)

        # Call with empty citations
        report = agent._generate_counter_report(
            sample_counter_statement,
            [],  # No citations
            sample_search_results,
            sample_scored_docs
        )

        # Should generate empty report
        assert report.num_citations == 0
        assert len(report.citations) == 0
        assert "no substantial evidence" in report.summary.lower()
        assert report.generation_metadata.get("empty_report") is True

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_counter_report_to_markdown(
        self,
        mock_ollama,
        mock_search_coord,
        mock_citation,
        mock_scoring,
        mock_db,
        mock_host,
        mock_agent_config,
        mock_model,
        mock_config_fn,
        sample_counter_statement,
        sample_citations,
        sample_search_results,
        sample_scored_docs
    ):
        """Test that counter-report can be converted to markdown."""
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {"temperature": 0.3}
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        # Mock ollama client
        mock_ollama_instance = MagicMock()
        mock_ollama_instance.generate.return_value = {
            "response": "Multiple studies support GLP-1 efficacy [1][2]. Evidence shows superior outcomes.",
            "prompt_eval_count": 100,
            "eval_count": 50,
            "eval_duration": 1000000000,
            "prompt_eval_duration": 500000000
        }
        mock_ollama.return_value = mock_ollama_instance

        agent = PaperCheckerAgent(show_model_info=False)
        agent.client = mock_ollama_instance

        report = agent._generate_counter_report(
            sample_counter_statement,
            sample_citations,
            sample_search_results,
            sample_scored_docs
        )

        markdown = report.to_markdown()

        # Should contain summary
        assert report.summary in markdown

        # Should contain references section
        assert "References" in markdown or "references" in markdown.lower()

        # Should contain all citations
        for citation in sample_citations:
            assert citation.full_citation in markdown

    # ==================== VALIDATION METHOD TESTS ====================

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_validate_citation_format_valid(
        self,
        mock_ollama,
        mock_search_coord,
        mock_citation,
        mock_scoring,
        mock_db,
        mock_host,
        mock_agent_config,
        mock_model,
        mock_config_fn
    ):
        """Test citation format validation with valid sequential citations."""
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {}
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        agent = PaperCheckerAgent(show_model_info=False)

        # Valid report with sequential citations - should not raise
        report = "Studies show [1] that results are significant [2]. More data [3]."
        agent._validate_citation_format(report)  # Should not raise

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_validate_citation_format_missing_logs_warning(
        self,
        mock_ollama,
        mock_search_coord,
        mock_citation,
        mock_scoring,
        mock_db,
        mock_host,
        mock_agent_config,
        mock_model,
        mock_config_fn,
        caplog
    ):
        """Test citation format validation logs warning when no citations present."""
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {}
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        agent = PaperCheckerAgent(show_model_info=False)

        import logging
        with caplog.at_level(logging.WARNING):
            agent._validate_citation_format("A report without any citation references.")

        assert "does not contain inline citations" in caplog.text

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_validate_coherence_valid(
        self,
        mock_ollama,
        mock_search_coord,
        mock_citation,
        mock_scoring,
        mock_db,
        mock_host,
        mock_agent_config,
        mock_model,
        mock_config_fn
    ):
        """Test coherence validation with valid sentences."""
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {}
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        agent = PaperCheckerAgent(show_model_info=False)

        # Valid report with complete sentences - should not raise
        report = "This is a complete sentence. Here is another one with more text."
        agent._validate_coherence(report)  # Should not raise

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_validate_coherence_no_punctuation_raises(
        self,
        mock_ollama,
        mock_search_coord,
        mock_citation,
        mock_scoring,
        mock_db,
        mock_host,
        mock_agent_config,
        mock_model,
        mock_config_fn
    ):
        """Test coherence validation raises on missing punctuation."""
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {}
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        agent = PaperCheckerAgent(show_model_info=False)

        with pytest.raises(ValueError, match="lack complete sentences"):
            agent._validate_coherence("This has no sentence ending punctuation")

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_validate_coherence_short_fragments_raises(
        self,
        mock_ollama,
        mock_search_coord,
        mock_citation,
        mock_scoring,
        mock_db,
        mock_host,
        mock_agent_config,
        mock_model,
        mock_config_fn
    ):
        """Test coherence validation raises on too-short sentences."""
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {}
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        agent = PaperCheckerAgent(show_model_info=False)

        with pytest.raises(ValueError, match="lacks substantive sentences"):
            agent._validate_coherence("A. B. C.")  # All fragments below min length

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_validate_markdown_valid(
        self,
        mock_ollama,
        mock_search_coord,
        mock_citation,
        mock_scoring,
        mock_db,
        mock_host,
        mock_agent_config,
        mock_model,
        mock_config_fn
    ):
        """Test markdown validation with valid formatting."""
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {}
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        agent = PaperCheckerAgent(show_model_info=False)

        # Valid markdown - should not raise
        report = "This has **bold** and *italic* and `code` formatting."
        agent._validate_markdown(report)  # Should not raise

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_validate_markdown_unclosed_code_block_raises(
        self,
        mock_ollama,
        mock_search_coord,
        mock_citation,
        mock_scoring,
        mock_db,
        mock_host,
        mock_agent_config,
        mock_model,
        mock_config_fn
    ):
        """Test markdown validation raises on unclosed code blocks."""
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {}
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        agent = PaperCheckerAgent(show_model_info=False)

        with pytest.raises(ValueError, match="Malformed markdown"):
            agent._validate_markdown("Here is code:\n```python\nprint('test')\n")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
