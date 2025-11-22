"""
Shared fixtures for PaperChecker test suite.

This module provides reusable fixtures and test data for all PaperChecker tests.
Fixtures are organized by component type and use case.

Usage:
    All fixtures are automatically available in test files within this package.
    Import additional fixtures using:
        from tests.paperchecker.conftest import sample_statement

Fixture Categories:
    - Mock Configurations: Ollama, database, and agent configurations
    - Data Models: Statement, CounterStatement, SearchResults, etc.
    - Sample Responses: Mock LLM responses for testing parsers
    - Component Mocks: Mocked components for integration testing
"""

import json
import pytest
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch


# ==================== CONSTANTS ====================

# Test model names
TEST_MODEL_NAME: str = "test-model:latest"
TEST_OLLAMA_HOST: str = "http://localhost:11434"

# Test abstract for extraction
SAMPLE_ABSTRACT_TEXT: str = """
Background: Previous studies have shown conflicting results regarding the efficacy
of metformin versus GLP-1 receptor agonists for type 2 diabetes management.

Methods: This randomized controlled trial compared metformin (n=500) with GLP-1
receptor agonist semaglutide (n=500) over 52 weeks in patients with newly diagnosed
type 2 diabetes.

Results: Patients receiving semaglutide showed significantly greater HbA1c reduction
(-1.8% vs -1.2%, p<0.001) and weight loss (-5.2kg vs -1.1kg, p<0.001) compared
to metformin. Cardiovascular events were similar between groups (2.1% vs 2.4%, p=0.68).

Conclusion: GLP-1 receptor agonists may be superior to metformin as first-line
therapy for type 2 diabetes, particularly in patients with obesity.
"""

# Minimum length constant for abstracts
MIN_ABSTRACT_LENGTH: int = 50


# ==================== MOCK CONFIGURATION FIXTURES ====================

@pytest.fixture
def mock_ollama_client() -> MagicMock:
    """Create a mock Ollama client for testing without network calls."""
    mock_client = MagicMock()
    mock_client.list.return_value = {
        "models": [
            {"name": TEST_MODEL_NAME, "size": 1000000000}
        ]
    }
    return mock_client


@pytest.fixture
def mock_ollama_chat_response() -> Dict[str, Any]:
    """Return a standard mock response from Ollama chat endpoint."""
    return {
        "message": {
            "role": "assistant",
            "content": '{"test": "response"}'
        },
        "done": True
    }


@pytest.fixture
def mock_db_manager() -> MagicMock:
    """Create a mock DatabaseManager for testing without database."""
    mock_manager = MagicMock()
    mock_conn = MagicMock()
    mock_cursor = MagicMock()

    mock_manager.get_connection.return_value.__enter__ = MagicMock(
        return_value=mock_conn
    )
    mock_manager.get_connection.return_value.__exit__ = MagicMock(
        return_value=None
    )
    mock_conn.cursor.return_value.__enter__ = MagicMock(
        return_value=mock_cursor
    )
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=None)

    return mock_manager


@pytest.fixture
def mock_config() -> Dict[str, Any]:
    """Return a standard test configuration dictionary."""
    return {
        "model": TEST_MODEL_NAME,
        "temperature": 0.3,
        "host": TEST_OLLAMA_HOST,
        "semantic_limit": 50,
        "hyde_limit": 50,
        "keyword_limit": 50,
        "max_deduplicated": 100,
        "embedding_model": "snowflake-arctic-embed2:latest",
    }


# ==================== DATA MODEL FIXTURES ====================

@pytest.fixture
def sample_statement():
    """Create a sample Statement object for testing."""
    from bmlibrarian.paperchecker.data_models import Statement

    return Statement(
        text="GLP-1 receptor agonists may be superior to metformin as first-line therapy for type 2 diabetes",
        context="Results showed significantly greater HbA1c reduction and weight loss with GLP-1 agonists.",
        statement_type="conclusion",
        confidence=0.9,
        statement_order=1
    )


@pytest.fixture
def sample_statement_hypothesis():
    """Create a sample hypothesis Statement for testing."""
    from bmlibrarian.paperchecker.data_models import Statement

    return Statement(
        text="Early intervention with SGLT2 inhibitors reduces cardiovascular mortality",
        context="We hypothesize that starting SGLT2 inhibitors within 6 months of diagnosis improves outcomes.",
        statement_type="hypothesis",
        confidence=0.85,
        statement_order=1
    )


@pytest.fixture
def sample_statement_finding():
    """Create a sample finding Statement for testing."""
    from bmlibrarian.paperchecker.data_models import Statement

    return Statement(
        text="Patients receiving semaglutide showed 1.8% HbA1c reduction compared to 1.2% with metformin",
        context="This randomized controlled trial compared treatment outcomes over 52 weeks.",
        statement_type="finding",
        confidence=0.95,
        statement_order=1
    )


@pytest.fixture
def sample_counter_statement(sample_statement):
    """Create a sample CounterStatement for testing."""
    from bmlibrarian.paperchecker.data_models import CounterStatement

    return CounterStatement(
        original_statement=sample_statement,
        negated_text="Metformin is as effective or superior to GLP-1 receptor agonists as first-line therapy for type 2 diabetes",
        hyde_abstracts=[
            "Background: We evaluated the comparative effectiveness of metformin "
            "versus GLP-1 receptor agonists in type 2 diabetes management. "
            "Methods: A meta-analysis of 25 randomized controlled trials (n=15,000). "
            "Results: Metformin showed equivalent HbA1c reduction (-1.5% vs -1.6%, p=0.42) "
            "with superior cost-effectiveness. Conclusion: Metformin remains the optimal "
            "first-line therapy for most patients with type 2 diabetes.",
            "This systematic review found that metformin provides comparable glycemic "
            "control to GLP-1 agonists while being more cost-effective and having a "
            "longer safety track record.",
        ],
        keywords=[
            "metformin effectiveness",
            "GLP-1 agonist comparison",
            "type 2 diabetes first-line therapy",
            "HbA1c reduction",
            "cost-effectiveness diabetes treatment",
        ],
        generation_metadata={
            "model": TEST_MODEL_NAME,
            "temperature": 0.3,
            "timestamp": "2024-01-15T10:00:00"
        }
    )


@pytest.fixture
def sample_search_results():
    """Create sample SearchResults for testing."""
    from bmlibrarian.paperchecker.data_models import SearchResults

    return SearchResults.from_strategy_results(
        semantic=[101, 102, 103, 104, 105],
        hyde=[102, 103, 106, 107],
        keyword=[103, 104, 108, 109, 110],
        metadata={
            "semantic_limit": 50,
            "hyde_limit": 50,
            "keyword_limit": 50,
            "total_search_time_seconds": 2.5
        }
    )


@pytest.fixture
def sample_scored_document():
    """Create a sample ScoredDocument for testing."""
    from bmlibrarian.paperchecker.data_models import ScoredDocument

    return ScoredDocument(
        doc_id=101,
        document={
            "id": 101,
            "title": "Metformin vs GLP-1 Agonists: A Meta-Analysis",
            "abstract": "This meta-analysis compared the efficacy of metformin "
                       "and GLP-1 receptor agonists for type 2 diabetes...",
            "authors": ["Smith J", "Jones A", "Brown C"],
            "publication_date": "2023-06-15",
            "journal": "Diabetes Care",
            "pmid": "12345678",
            "doi": "10.1000/dc.2023.12345",
            "source_id": 1
        },
        score=5,
        explanation="Highly relevant meta-analysis directly comparing the treatments in question.",
        supports_counter=True,
        found_by=["semantic", "hyde"]
    )


@pytest.fixture
def sample_scored_documents():
    """Create a list of sample ScoredDocuments for testing."""
    from bmlibrarian.paperchecker.data_models import ScoredDocument

    return [
        ScoredDocument(
            doc_id=101,
            document={
                "id": 101,
                "title": "Metformin vs GLP-1 Agonists: A Meta-Analysis",
                "abstract": "This meta-analysis compared efficacy...",
                "authors": ["Smith J", "Jones A"],
                "publication_date": "2023-06-15",
                "journal": "Diabetes Care",
                "pmid": "12345678",
                "doi": "10.1000/dc.2023.12345",
            },
            score=5,
            explanation="Highly relevant meta-analysis.",
            supports_counter=True,
            found_by=["semantic", "hyde"]
        ),
        ScoredDocument(
            doc_id=102,
            document={
                "id": 102,
                "title": "Long-term Metformin Outcomes",
                "abstract": "Metformin shows sustained effectiveness...",
                "authors": ["Brown B"],
                "publication_date": "2022-03-20",
                "journal": "JAMA",
                "pmid": "23456789",
            },
            score=4,
            explanation="Relevant longitudinal study.",
            supports_counter=True,
            found_by=["semantic"]
        ),
        ScoredDocument(
            doc_id=103,
            document={
                "id": 103,
                "title": "Cost-Effectiveness of Diabetes Treatments",
                "abstract": "Economic analysis shows metformin superiority...",
                "authors": ["White W", "Green G"],
                "publication_date": "2021-09-10",
                "journal": "PharmacoEconomics",
                "pmid": "34567890",
            },
            score=3,
            explanation="Moderately relevant economic analysis.",
            supports_counter=True,
            found_by=["keyword"]
        ),
    ]


@pytest.fixture
def sample_extracted_citation():
    """Create a sample ExtractedCitation for testing."""
    from bmlibrarian.paperchecker.data_models import ExtractedCitation

    return ExtractedCitation(
        doc_id=101,
        passage="In this meta-analysis of 25 RCTs, metformin demonstrated equivalent "
                "glycemic control compared to GLP-1 receptor agonists (mean HbA1c "
                "reduction -1.5% vs -1.6%, p=0.42).",
        relevance_score=5,
        full_citation="Smith J, Jones A, Brown C. Metformin vs GLP-1 Agonists: "
                     "A Meta-Analysis. Diabetes Care. 2023;46(6):1234-1245. "
                     "doi:10.1000/dc.2023.12345",
        metadata={
            "pmid": "12345678",
            "doi": "10.1000/dc.2023.12345",
            "year": 2023,
            "journal": "Diabetes Care",
            "authors": ["Smith J", "Jones A", "Brown C"],
            "title": "Metformin vs GLP-1 Agonists: A Meta-Analysis",
        },
        citation_order=1
    )


@pytest.fixture
def sample_counter_report(sample_extracted_citation):
    """Create a sample CounterReport for testing."""
    from bmlibrarian.paperchecker.data_models import CounterReport

    return CounterReport(
        summary="A meta-analysis of 25 RCTs found that metformin provides equivalent "
                "glycemic control to GLP-1 receptor agonists (mean HbA1c reduction "
                "-1.5% vs -1.6%, p=0.42). Additionally, metformin showed superior "
                "cost-effectiveness and a 20-year safety track record.",
        num_citations=1,
        citations=[sample_extracted_citation],
        search_stats={
            "documents_found": 150,
            "documents_scored": 50,
            "citations_extracted": 3
        },
        generation_metadata={
            "model": TEST_MODEL_NAME,
            "timestamp": "2024-01-15T10:30:00"
        }
    )


@pytest.fixture
def sample_verdict(sample_counter_report):
    """Create a sample Verdict for testing."""
    from bmlibrarian.paperchecker.data_models import Verdict

    return Verdict(
        verdict="contradicts",
        rationale="The meta-analysis provides strong evidence that metformin has "
                  "equivalent glycemic control to GLP-1 agonists, contradicting the "
                  "original claim of GLP-1 superiority. The evidence quality is high "
                  "with consistent findings across 25 RCTs.",
        confidence="high",
        counter_report=sample_counter_report,
        analysis_metadata={
            "model": TEST_MODEL_NAME,
            "temperature": 0.3,
            "timestamp": "2024-01-15T11:00:00"
        }
    )


@pytest.fixture
def sample_paper_check_result(
    sample_statement,
    sample_counter_statement,
    sample_search_results,
    sample_scored_documents,
    sample_counter_report,
    sample_verdict
):
    """Create a complete sample PaperCheckResult for testing."""
    from bmlibrarian.paperchecker.data_models import PaperCheckResult

    return PaperCheckResult(
        original_abstract=SAMPLE_ABSTRACT_TEXT,
        source_metadata={
            "pmid": 99999999,
            "doi": "10.1000/test.99999",
            "title": "Test Study on Diabetes Treatment",
            "authors": ["Test Author A", "Test Author B"],
            "year": 2024,
            "journal": "Journal of Testing"
        },
        statements=[sample_statement],
        counter_statements=[sample_counter_statement],
        search_results=[sample_search_results],
        scored_documents=[sample_scored_documents],
        counter_reports=[sample_counter_report],
        verdicts=[sample_verdict],
        overall_assessment="The original claim was contradicted by strong literature evidence.",
        processing_metadata={
            "model": TEST_MODEL_NAME,
            "processing_time_seconds": 45.5
        }
    )


# ==================== LLM RESPONSE FIXTURES ====================

@pytest.fixture
def statement_extraction_response() -> str:
    """Return a valid JSON response for statement extraction."""
    return json.dumps({
        "statements": [
            {
                "text": "GLP-1 receptor agonists may be superior to metformin as first-line therapy",
                "context": "Based on HbA1c reduction and weight loss outcomes.",
                "statement_type": "conclusion",
                "confidence": 0.9
            },
            {
                "text": "Patients receiving semaglutide showed significantly greater HbA1c reduction",
                "context": "Results: -1.8% vs -1.2%, p<0.001",
                "statement_type": "finding",
                "confidence": 0.95
            }
        ]
    })


@pytest.fixture
def counter_statement_response() -> str:
    """Return a valid counter-statement response."""
    return "Metformin is as effective or superior to GLP-1 receptor agonists as first-line therapy for type 2 diabetes"


@pytest.fixture
def hyde_generation_response() -> str:
    """Return a valid JSON response for HyDE generation."""
    return json.dumps({
        "hyde_abstracts": [
            "Background: We conducted a systematic review comparing metformin and "
            "GLP-1 receptor agonists for type 2 diabetes. Methods: Meta-analysis of "
            "25 RCTs with 15,000 patients. Results: Metformin showed equivalent HbA1c "
            "reduction (-1.5% vs -1.6%, p=0.42) with superior cost-effectiveness. "
            "Conclusion: Metformin remains the optimal first-line therapy.",
            "This prospective cohort study followed 5,000 patients over 5 years. "
            "Patients on metformin had similar cardiovascular outcomes and better "
            "tolerability profiles compared to GLP-1 agonist users."
        ],
        "keywords": [
            "metformin effectiveness type 2 diabetes",
            "GLP-1 agonist comparison",
            "first-line diabetes therapy",
            "HbA1c reduction metformin",
            "cost-effectiveness diabetes treatment"
        ]
    })


@pytest.fixture
def verdict_analysis_response() -> str:
    """Return a valid JSON response for verdict analysis."""
    return json.dumps({
        "verdict": "contradicts",
        "confidence": "high",
        "rationale": "The meta-analysis of 25 RCTs provides strong evidence that "
                    "metformin has equivalent glycemic control to GLP-1 agonists, "
                    "directly contradicting the original claim of GLP-1 superiority."
    })


# ==================== MOCK COMPONENT FIXTURES ====================

@pytest.fixture
def mock_statement_extractor():
    """Create a mock StatementExtractor for integration testing."""
    mock = MagicMock()
    mock.test_connection.return_value = True
    return mock


@pytest.fixture
def mock_counter_generator():
    """Create a mock CounterStatementGenerator for integration testing."""
    mock = MagicMock()
    mock.test_connection.return_value = True
    return mock


@pytest.fixture
def mock_hyde_generator():
    """Create a mock HyDEGenerator for integration testing."""
    mock = MagicMock()
    mock.test_connection.return_value = True
    return mock


@pytest.fixture
def mock_search_coordinator(sample_search_results):
    """Create a mock SearchCoordinator for integration testing."""
    mock = MagicMock()
    mock.search.return_value = sample_search_results
    mock.test_connection.return_value = True
    return mock


@pytest.fixture
def mock_verdict_analyzer(sample_verdict):
    """Create a mock VerdictAnalyzer for integration testing."""
    mock = MagicMock()
    mock.analyze.return_value = sample_verdict
    mock.test_connection.return_value = True
    return mock


# ==================== HELPER FIXTURES ====================

@pytest.fixture
def sample_abstract() -> str:
    """Return a sample medical abstract for testing."""
    return SAMPLE_ABSTRACT_TEXT


@pytest.fixture
def short_abstract() -> str:
    """Return an abstract that's too short for extraction."""
    return "Short abstract text."


@pytest.fixture
def empty_json_response() -> str:
    """Return an empty JSON object response."""
    return "{}"


@pytest.fixture
def malformed_json_response() -> str:
    """Return malformed JSON for error handling tests."""
    return '{"invalid json without closing brace'


@pytest.fixture
def json_in_markdown_response() -> str:
    """Return JSON wrapped in markdown code blocks."""
    return '''Here is the response:

```json
{
  "statements": [
    {
      "text": "Test statement",
      "context": "Test context",
      "statement_type": "finding",
      "confidence": 0.85
    }
  ]
}
```

That completes the extraction.
'''
