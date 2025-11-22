"""
Unit tests for PaperChecker citation extraction integration.

Tests the _extract_citations method and related helper methods:
- _build_extraction_question
- _format_citation
- _extract_metadata

Test categories:
    1. Extraction question construction
    2. AMA citation formatting
    3. Metadata extraction
    4. Citation extraction flow
    5. Min score filtering
    6. Max citations limit
    7. Error handling
"""

import pytest
from unittest.mock import MagicMock, patch
from typing import Dict, Any, List

from bmlibrarian.paperchecker import (
    PaperCheckerAgent,
    Statement,
    CounterStatement,
    ScoredDocument,
    ExtractedCitation,
)
from bmlibrarian.agents.citation_agent import Citation


# ==================== FIXTURES ====================

@pytest.fixture
def sample_statement() -> Statement:
    """Create a sample statement for testing."""
    return Statement(
        text="Metformin is superior to GLP-1 agonists for type 2 diabetes",
        context="In this study, we compared the efficacy...",
        statement_type="finding",
        confidence=0.9,
        statement_order=1
    )


@pytest.fixture
def sample_counter_statement(sample_statement: Statement) -> CounterStatement:
    """Create a sample counter-statement for testing."""
    return CounterStatement(
        original_statement=sample_statement,
        negated_text="GLP-1 agonists are superior or equivalent to metformin",
        hyde_abstracts=["A hypothetical study showing GLP-1 superiority..."],
        keywords=["GLP-1", "metformin", "diabetes"],
        generation_metadata={"model": "test-model"}
    )


@pytest.fixture
def sample_scored_documents() -> List[ScoredDocument]:
    """Create sample scored documents for testing."""
    return [
        ScoredDocument(
            doc_id=1,
            document={
                "id": 1,
                "title": "GLP-1 vs Metformin Study",
                "abstract": "Results showed GLP-1 superior glycemic control...",
                "authors": ["Smith J", "Jones A"],
                "publication_date": "2023-01-15",
                "journal": "Diabetes Care",
                "pmid": "12345678",
                "doi": "10.1234/example",
                "source_id": 1
            },
            score=5,
            explanation="Highly relevant",
            supports_counter=True,
            found_by=["semantic", "hyde"]
        ),
        ScoredDocument(
            doc_id=2,
            document={
                "id": 2,
                "title": "Another Diabetes Study",
                "abstract": "GLP-1 showed better outcomes in elderly patients...",
                "authors": ["Brown B"],
                "publication_date": "2022-06-20",
                "publication": "JAMA",
                "pmid": "23456789",
                "doi": "10.1234/another",
                "source_id": 2
            },
            score=4,
            explanation="Very relevant",
            supports_counter=True,
            found_by=["keyword"]
        ),
        ScoredDocument(
            doc_id=3,
            document={
                "id": 3,
                "title": "Low Score Study",
                "abstract": "Unrelated study...",
                "authors": ["White W"],
                "publication_date": "2021-03-10",
                "journal": "Some Journal",
                "pmid": "34567890",
                "source_id": 3
            },
            score=2,
            explanation="Minimally relevant",
            supports_counter=False,
            found_by=["semantic"]
        )
    ]


@pytest.fixture
def mock_citation_objects() -> List[Citation]:
    """Create mock Citation objects as returned by CitationFinderAgent."""
    return [
        Citation(
            passage="Results showed GLP-1 provided superior glycemic control compared to metformin.",
            summary="GLP-1 outperformed metformin in glycemic control",
            relevance_score=0.9,
            document_id="1",
            document_title="GLP-1 vs Metformin Study",
            authors=["Smith J", "Jones A"],
            publication_date="2023-01-15",
            pmid="12345678",
            doi="10.1234/example"
        ),
        Citation(
            passage="GLP-1 showed better outcomes in elderly patients with improved adherence.",
            summary="GLP-1 beneficial for elderly patients",
            relevance_score=0.85,
            document_id="2",
            document_title="Another Diabetes Study",
            authors=["Brown B"],
            publication_date="2022-06-20",
            pmid="23456789",
            doi="10.1234/another"
        )
    ]


def create_mock_paper_checker():
    """Create a mock PaperCheckerAgent for testing."""
    with patch('bmlibrarian.paperchecker.agent.get_config') as mock_config_fn, \
         patch('bmlibrarian.paperchecker.agent.get_model') as mock_model, \
         patch('bmlibrarian.paperchecker.agent.get_agent_config') as mock_agent_config, \
         patch('bmlibrarian.paperchecker.agent.get_ollama_host') as mock_host, \
         patch('bmlibrarian.paperchecker.agent.PaperCheckDB') as mock_db, \
         patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent') as mock_scoring, \
         patch('bmlibrarian.paperchecker.agent.CitationFinderAgent') as mock_citation, \
         patch('bmlibrarian.paperchecker.agent.SearchCoordinator') as mock_search, \
         patch('ollama.Client') as mock_ollama:

        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {
            "score_threshold": 3.0,
            "citation": {
                "min_score": 3,
                "max_citations_per_statement": 10
            }
        }
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        agent = PaperCheckerAgent(show_model_info=False)
        return agent


# ==================== EXTRACTION QUESTION TESTS ====================

class TestBuildExtractionQuestion:
    """Test extraction question construction."""

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_extraction_question_contains_counter_claim(
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
        sample_counter_statement
    ):
        """Test extraction question includes counter-claim text."""
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {"citation": {"min_score": 3}}
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        agent = PaperCheckerAgent(show_model_info=False)

        question = agent._build_extraction_question(sample_counter_statement)

        assert "GLP-1 agonists are superior or equivalent to metformin" in question
        assert "evidence" in question.lower()

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_extraction_question_contains_original_statement(
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
        sample_counter_statement
    ):
        """Test extraction question includes original statement for context."""
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {"citation": {"min_score": 3}}
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        agent = PaperCheckerAgent(show_model_info=False)

        question = agent._build_extraction_question(sample_counter_statement)

        assert "Metformin is superior to GLP-1 agonists" in question
        assert "contradicts" in question.lower()


# ==================== AMA CITATION FORMATTING TESTS ====================

class TestFormatCitation:
    """Test AMA-style citation formatting."""

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_format_citation_full_document(
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
        sample_scored_documents
    ):
        """Test AMA citation formatting with all fields present."""
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {"citation": {"min_score": 3}}
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        agent = PaperCheckerAgent(show_model_info=False)

        document = sample_scored_documents[0].document
        citation = agent._format_citation(document)

        # Check for key components
        assert "Smith J" in citation or "Jones A" in citation
        assert "GLP-1 vs Metformin Study" in citation
        assert "2023" in citation
        assert "doi:10.1234/example" in citation
        assert citation.endswith(".")

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_format_citation_many_authors(
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
        """Test AMA citation truncates authors to 3 + et al."""
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {"citation": {"min_score": 3}}
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        agent = PaperCheckerAgent(show_model_info=False)

        document = {
            "authors": ["Smith A", "Jones B", "Brown C", "White D", "Green E"],
            "title": "Multi-Author Study",
            "publication_date": "2023-01-01"
        }

        citation = agent._format_citation(document)

        # Should have first 3 authors + et al
        assert "Smith A" in citation
        assert "Jones B" in citation
        assert "Brown C" in citation
        assert "et al" in citation
        assert "White D" not in citation
        assert "Green E" not in citation

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_format_citation_uses_publication_fallback(
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
        """Test citation uses 'publication' if 'journal' not present."""
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {"citation": {"min_score": 3}}
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        agent = PaperCheckerAgent(show_model_info=False)

        document = {
            "title": "Test Study",
            "publication": "Alternative Journal Name",
            "publication_date": "2023-01-01"
        }

        citation = agent._format_citation(document)

        assert "Alternative Journal Name" in citation

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_format_citation_empty_document(
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
        """Test citation formatting with empty document returns fallback."""
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {"citation": {"min_score": 3}}
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        agent = PaperCheckerAgent(show_model_info=False)

        citation = agent._format_citation({})

        assert citation == "Citation information unavailable."


# ==================== METADATA EXTRACTION TESTS ====================

class TestExtractMetadata:
    """Test metadata extraction from documents."""

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_extract_metadata_full_document(
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
        sample_scored_documents
    ):
        """Test metadata extraction from document with all fields."""
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {"citation": {"min_score": 3}}
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        agent = PaperCheckerAgent(show_model_info=False)

        document = sample_scored_documents[0].document
        metadata = agent._extract_metadata(document)

        assert metadata["pmid"] == "12345678"
        assert metadata["doi"] == "10.1234/example"
        assert metadata["year"] == 2023
        assert metadata["journal"] == "Diabetes Care"
        assert "Smith J" in metadata["authors"]
        assert metadata["title"] == "GLP-1 vs Metformin Study"
        assert metadata["source"] == 1

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_extract_metadata_year_from_date(
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
        """Test year is extracted correctly from publication_date."""
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {"citation": {"min_score": 3}}
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        agent = PaperCheckerAgent(show_model_info=False)

        # Test with full date
        doc1 = {"publication_date": "2021-06-15"}
        assert agent._extract_metadata(doc1)["year"] == 2021

        # Test with year only
        doc2 = {"publication_date": "2022"}
        assert agent._extract_metadata(doc2)["year"] == 2022

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_extract_metadata_missing_fields(
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
        """Test metadata extraction handles missing fields gracefully."""
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {"citation": {"min_score": 3}}
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        agent = PaperCheckerAgent(show_model_info=False)

        metadata = agent._extract_metadata({})

        assert metadata["pmid"] is None
        assert metadata["doi"] is None
        assert metadata["year"] is None
        assert metadata["journal"] is None
        assert metadata["title"] is None
        assert metadata["source"] is None
        assert metadata["authors"] == []


# ==================== CITATION EXTRACTION FLOW TESTS ====================

class TestExtractCitations:
    """Test the complete citation extraction flow."""

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_extract_citations_empty_scored_docs(
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
        sample_counter_statement
    ):
        """Test citation extraction with empty scored documents."""
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {"citation": {"min_score": 3}}
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        agent = PaperCheckerAgent(show_model_info=False)

        result = agent._extract_citations(sample_counter_statement, [])

        assert result == []

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_extract_citations_filters_below_min_score(
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
        sample_scored_documents
    ):
        """Test that documents below min_citation_score are filtered out."""
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {
            "citation": {"min_score": 3, "max_citations_per_statement": 10}
        }
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        # Mock citation agent to return empty for this test
        mock_citation_instance = MagicMock()
        mock_citation_instance.process_scored_documents_for_citations.return_value = []
        mock_citation.return_value = mock_citation_instance

        agent = PaperCheckerAgent(show_model_info=False)
        agent.citation_agent = mock_citation_instance

        # Only docs with score >= 3 should be processed
        # sample_scored_documents[2] has score=2, should be filtered
        agent._extract_citations(sample_counter_statement, sample_scored_documents)

        # Verify the call to citation agent used only eligible docs
        call_args = mock_citation_instance.process_scored_documents_for_citations.call_args
        scored_tuples = call_args.kwargs.get('scored_documents') or call_args[1].get('scored_documents')
        if scored_tuples is None:
            scored_tuples = call_args[0][1] if len(call_args[0]) > 1 else []

        # Should have 2 documents (score 5 and score 4), not 3
        assert len(scored_tuples) == 2

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_extract_citations_converts_to_extracted_citation(
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
        sample_scored_documents,
        mock_citation_objects
    ):
        """Test that Citation objects are converted to ExtractedCitation."""
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {
            "citation": {"min_score": 3, "max_citations_per_statement": 10}
        }
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        # Mock citation agent to return our test citations
        mock_citation_instance = MagicMock()
        mock_citation_instance.process_scored_documents_for_citations.return_value = mock_citation_objects
        mock_citation.return_value = mock_citation_instance

        agent = PaperCheckerAgent(show_model_info=False)
        agent.citation_agent = mock_citation_instance

        # Use only docs with score >= 3
        eligible_docs = [d for d in sample_scored_documents if d.score >= 3]
        result = agent._extract_citations(sample_counter_statement, eligible_docs)

        # Should have converted citations
        assert len(result) == 2
        assert all(isinstance(c, ExtractedCitation) for c in result)

        # Verify first citation
        assert result[0].doc_id == 1
        assert "superior glycemic control" in result[0].passage
        assert result[0].relevance_score == 5  # From ScoredDocument
        assert result[0].citation_order == 1

        # Verify second citation
        assert result[1].doc_id == 2
        assert result[1].citation_order == 2

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_extract_citations_respects_max_limit(
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
        sample_counter_statement
    ):
        """Test that max_citations_per_statement limit is respected."""
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {
            "citation": {"min_score": 3, "max_citations_per_statement": 2}
        }
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        # Create 5 citations
        many_citations = [
            Citation(
                passage=f"Passage {i}",
                summary=f"Summary {i}",
                relevance_score=0.9,
                document_id=str(i),
                document_title=f"Study {i}",
                authors=[f"Author {i}"],
                publication_date="2023-01-01",
                pmid=str(10000 + i),
            )
            for i in range(1, 6)
        ]

        mock_citation_instance = MagicMock()
        mock_citation_instance.process_scored_documents_for_citations.return_value = many_citations
        mock_citation.return_value = mock_citation_instance

        agent = PaperCheckerAgent(show_model_info=False)
        agent.citation_agent = mock_citation_instance

        # Create matching scored documents
        scored_docs = [
            ScoredDocument(
                doc_id=i,
                document={"id": i, "title": f"Study {i}", "abstract": f"Abstract {i}"},
                score=4,
                explanation="Relevant",
                supports_counter=True,
                found_by=["semantic"]
            )
            for i in range(1, 6)
        ]

        result = agent._extract_citations(sample_counter_statement, scored_docs)

        # Should be limited to 2 (max_citations_per_statement)
        assert len(result) <= 2

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_extract_citations_error_handling(
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
        sample_scored_documents
    ):
        """Test that errors in citation extraction are handled properly."""
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {
            "citation": {"min_score": 3, "max_citations_per_statement": 10}
        }
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        # Mock citation agent to raise an error
        mock_citation_instance = MagicMock()
        mock_citation_instance.process_scored_documents_for_citations.side_effect = (
            Exception("Test error")
        )
        mock_citation.return_value = mock_citation_instance

        agent = PaperCheckerAgent(show_model_info=False)
        agent.citation_agent = mock_citation_instance

        eligible_docs = [d for d in sample_scored_documents if d.score >= 3]

        with pytest.raises(RuntimeError, match="Failed to extract citations"):
            agent._extract_citations(sample_counter_statement, eligible_docs)

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_extract_citations_skips_unmatched_docs(
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
        sample_scored_documents
    ):
        """Test that citations from unmatched documents are skipped."""
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {
            "citation": {"min_score": 3, "max_citations_per_statement": 10}
        }
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        # Citation with doc_id=999 that doesn't match any scored doc
        unmatched_citation = Citation(
            passage="Some passage",
            summary="Some summary",
            relevance_score=0.9,
            document_id="999",  # Not in scored docs
            document_title="Unknown Study",
            authors=["Unknown A"],
            publication_date="2023-01-01",
        )

        mock_citation_instance = MagicMock()
        mock_citation_instance.process_scored_documents_for_citations.return_value = [
            unmatched_citation
        ]
        mock_citation.return_value = mock_citation_instance

        agent = PaperCheckerAgent(show_model_info=False)
        agent.citation_agent = mock_citation_instance

        eligible_docs = [d for d in sample_scored_documents if d.score >= 3]
        result = agent._extract_citations(sample_counter_statement, eligible_docs)

        # Should be empty since doc_id=999 doesn't match any scored doc
        assert len(result) == 0

    @patch('bmlibrarian.paperchecker.agent.get_config')
    @patch('bmlibrarian.paperchecker.agent.get_model')
    @patch('bmlibrarian.paperchecker.agent.get_agent_config')
    @patch('bmlibrarian.paperchecker.agent.get_ollama_host')
    @patch('bmlibrarian.paperchecker.agent.PaperCheckDB')
    @patch('bmlibrarian.paperchecker.agent.DocumentScoringAgent')
    @patch('bmlibrarian.paperchecker.agent.CitationFinderAgent')
    @patch('bmlibrarian.paperchecker.agent.SearchCoordinator')
    @patch('ollama.Client')
    def test_extract_citations_includes_metadata(
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
        sample_scored_documents,
        mock_citation_objects
    ):
        """Test that extracted citations include proper metadata."""
        mock_config_fn.return_value = MagicMock(_config={})
        mock_model.return_value = "gpt-oss:20b"
        mock_host.return_value = "http://localhost:11434"
        mock_agent_config.return_value = {
            "citation": {"min_score": 3, "max_citations_per_statement": 10}
        }
        mock_db_instance = MagicMock()
        mock_db_instance.get_connection.return_value = MagicMock()
        mock_db.return_value = mock_db_instance

        # Return only first citation
        mock_citation_instance = MagicMock()
        mock_citation_instance.process_scored_documents_for_citations.return_value = [
            mock_citation_objects[0]
        ]
        mock_citation.return_value = mock_citation_instance

        agent = PaperCheckerAgent(show_model_info=False)
        agent.citation_agent = mock_citation_instance

        eligible_docs = [d for d in sample_scored_documents if d.score >= 3]
        result = agent._extract_citations(sample_counter_statement, eligible_docs)

        assert len(result) == 1
        citation = result[0]

        # Verify metadata
        assert citation.metadata["pmid"] == "12345678"
        assert citation.metadata["doi"] == "10.1234/example"
        assert citation.metadata["year"] == 2023
        assert citation.metadata["journal"] == "Diabetes Care"
        assert "Smith J" in citation.metadata["authors"]

        # Verify full_citation is populated
        assert len(citation.full_citation) > 0
        assert "." in citation.full_citation  # AMA format uses periods


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
