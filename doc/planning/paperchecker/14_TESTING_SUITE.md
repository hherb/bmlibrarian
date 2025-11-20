# Step 14: Comprehensive Testing Suite

## Context

All PaperChecker components and interfaces are now implemented. We need comprehensive testing to ensure reliability and correctness.

## Objective

Create a complete test suite that covers:
- All components (unit tests)
- Integration between components
- End-to-end workflows
- Error handling and edge cases
- Performance benchmarks

## Requirements

- pytest framework
- >90% code coverage
- Mock LLM calls for reproducibility
- Database fixtures for integration tests
- Performance benchmarks

## Implementation Location

Create comprehensive tests in `tests/paperchecker/`:

```
tests/paperchecker/
├── __init__.py
├── conftest.py                    # Shared fixtures
├── test_data_models.py            # Data models (Step 1)
├── test_statement_extractor.py    # Statement extraction (Step 4)
├── test_counter_generator.py      # Counter-statement generation (Step 5)
├── test_hyde_generator.py         # HyDE generation (Step 5)
├── test_search_coordinator.py     # Search (Step 6)
├── test_document_scoring.py       # Scoring (Step 7)
├── test_citation_extraction.py    # Citation extraction (Step 8)
├── test_counter_report.py         # Report generation (Step 9)
├── test_verdict_analyzer.py       # Verdict analysis (Step 10)
├── test_papercheck_database.py    # Database (Step 11)
├── test_paperchecker_agent.py     # Main agent integration
└── test_end_to_end.py             # End-to-end workflows
```

## Shared Fixtures (`conftest.py`)

```python
"""
Shared pytest fixtures for PaperChecker tests
"""

import pytest
from typing import Dict, Any
import psycopg
from psycopg.rows import dict_row
from unittest.mock import Mock, patch

from bmlibrarian.paperchecker.agent import PaperCheckerAgent
from bmlibrarian.paperchecker.database import PaperCheckDB
from bmlibrarian.paperchecker.data_models import (
    Statement, CounterStatement, SearchResults,
    ScoredDocument, ExtractedCitation, CounterReport, Verdict
)


# ==================== Database Fixtures ====================

@pytest.fixture(scope="session")
def test_db_connection():
    """Test database connection"""
    conn_string = "dbname=bmlibrarian_dev user=postgres host=localhost"
    conn = psycopg.connect(conn_string)
    yield conn
    conn.close()


@pytest.fixture
def paper_check_db(test_db_connection):
    """PaperCheckDB instance with test database"""
    return PaperCheckDB(connection=test_db_connection)


# ==================== Sample Data Fixtures ====================

@pytest.fixture
def sample_abstract():
    """Sample medical abstract"""
    return """
    Background: Type 2 diabetes management requires effective long-term
    glycemic control. Objective: To compare the efficacy of metformin versus
    GLP-1 receptor agonists in long-term outcomes. Methods: Retrospective
    cohort study of 10,000 patients over 5 years. Results: Metformin
    demonstrated superior HbA1c reduction (1.5% vs 1.2%, p<0.001) and lower
    cardiovascular events (HR 0.75, 95% CI 0.65-0.85). Conclusion: Metformin
    shows superior long-term efficacy compared to GLP-1 agonists for T2DM.
    """


@pytest.fixture
def sample_statement():
    """Sample statement"""
    return Statement(
        text="Metformin demonstrates superior efficacy to GLP-1 agonists",
        context="...",
        statement_type="finding",
        confidence=0.9,
        statement_order=1
    )


@pytest.fixture
def sample_counter_statement(sample_statement):
    """Sample counter-statement"""
    return CounterStatement(
        original_statement=sample_statement,
        negated_text="GLP-1 agonists are superior or equivalent to metformin",
        hyde_abstracts=[
            "Background: GLP-1 agonists show promise...",
            "Objective: Compare GLP-1 to metformin..."
        ],
        keywords=["GLP-1", "metformin", "type 2 diabetes", "HbA1c"],
        generation_metadata={}
    )


@pytest.fixture
def sample_search_results():
    """Sample search results"""
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
def sample_scored_documents():
    """Sample scored documents"""
    return [
        ScoredDocument(
            doc_id=1,
            document={"id": 1, "title": "Study 1", "abstract": "..."},
            score=5,
            explanation="Highly relevant",
            supports_counter=True,
            found_by=["semantic"]
        ),
        ScoredDocument(
            doc_id=2,
            document={"id": 2, "title": "Study 2", "abstract": "..."},
            score=4,
            explanation="Very relevant",
            supports_counter=True,
            found_by=["semantic", "hyde"]
        )
    ]


@pytest.fixture
def sample_citations():
    """Sample citations"""
    return [
        ExtractedCitation(
            doc_id=1,
            passage="GLP-1 demonstrated superior outcomes...",
            relevance_score=5,
            full_citation="Smith J, et al. Study 1. Journal. 2023.",
            metadata={"pmid": 12345678, "year": 2023},
            citation_order=1
        ),
        ExtractedCitation(
            doc_id=2,
            passage="Meta-analysis showed GLP-1 superiority...",
            relevance_score=4,
            full_citation="Jones A, et al. Study 2. JAMA. 2022.",
            metadata={"pmid": 23456789, "year": 2022},
            citation_order=2
        )
    ]


# ==================== Mock LLM Fixtures ====================

@pytest.fixture
def mock_llm_response():
    """Mock LLM response generator"""
    def _mock_response(response_type: str, **kwargs):
        """Generate mock responses for different request types"""

        if response_type == "statement_extraction":
            return {
                "statements": [
                    {
                        "text": "Metformin is superior to GLP-1",
                        "context": "Results showed...",
                        "statement_type": "finding",
                        "confidence": 0.9,
                        "statement_order": 1
                    }
                ]
            }

        elif response_type == "counter_statement":
            return "GLP-1 is superior or equivalent to metformin"

        elif response_type == "hyde":
            return {
                "hyde_abstracts": [
                    "Background: GLP-1 study. Methods: RCT. Results: GLP-1 superior. Conclusion: GLP-1 preferred.",
                    "Objective: Compare drugs. Design: Meta-analysis. Findings: GLP-1 better. Conclusion: Recommend GLP-1."
                ],
                "keywords": [
                    "GLP-1", "metformin", "type 2 diabetes", "glycemic control",
                    "HbA1c", "cardiovascular outcomes", "semaglutide", "liraglutide"
                ]
            }

        elif response_type == "counter_report":
            return """
Multiple studies have demonstrated GLP-1 receptor agonist superiority over metformin.
Smith et al. (2023) found GLP-1 reduced HbA1c by 1.8% compared to metformin's 1.2% [1].
A 2022 meta-analysis by Jones et al. showed GLP-1 associated with better cardiovascular
outcomes (HR 0.85) [2]. These findings suggest GLP-1 may be preferred for T2DM management.
            """

        elif response_type == "verdict":
            return {
                "verdict": "contradicts",
                "confidence": "high",
                "rationale": "Multiple high-quality RCTs demonstrate clear superiority of GLP-1 over metformin with consistent findings across studies."
            }

        else:
            raise ValueError(f"Unknown response type: {response_type}")

    return _mock_response


@pytest.fixture
def mock_ollama_api(mock_llm_response):
    """Mock Ollama API calls"""
    with patch('requests.post') as mock_post:
        def side_effect(*args, **kwargs):
            # Determine response type from prompt
            prompt = kwargs.get('json', {}).get('prompt', '')

            if 'extract' in prompt.lower() and 'statement' in prompt.lower():
                response_type = "statement_extraction"
                response_text = json.dumps(mock_llm_response(response_type))
            elif 'negate' in prompt.lower() or 'counter' in prompt.lower():
                response_type = "counter_statement"
                response_text = mock_llm_response(response_type)
            elif 'hyde' in prompt.lower() or 'hypothetical' in prompt.lower():
                response_type = "hyde"
                response_text = json.dumps(mock_llm_response(response_type))
            elif 'report' in prompt.lower() or 'summary' in prompt.lower():
                response_type = "counter_report"
                response_text = mock_llm_response(response_type)
            elif 'verdict' in prompt.lower():
                response_type = "verdict"
                response_text = json.dumps(mock_llm_response(response_type))
            else:
                response_text = "Default response"

            mock_response = Mock()
            mock_response.json.return_value = {"response": response_text}
            mock_response.raise_for_status.return_value = None
            return mock_response

        mock_post.side_effect = side_effect
        yield mock_post


# ==================== Agent Fixtures ====================

@pytest.fixture
def paper_checker_agent(mock_ollama_api, paper_check_db):
    """PaperCheckerAgent with mocked LLM"""
    return PaperCheckerAgent(db_connection=paper_check_db)
```

## End-to-End Test (`test_end_to_end.py`)

```python
"""
End-to-end integration tests for PaperChecker
"""

import pytest
from bmlibrarian.paperchecker.agent import PaperCheckerAgent


def test_complete_workflow(paper_checker_agent, sample_abstract, mock_ollama_api):
    """Test complete workflow from abstract to verdict"""

    # Run complete check
    result = paper_checker_agent.check_abstract(
        abstract=sample_abstract,
        source_metadata={"pmid": 12345678}
    )

    # Verify result structure
    assert result is not None
    assert len(result.statements) > 0
    assert len(result.counter_statements) == len(result.statements)
    assert len(result.search_results) == len(result.statements)
    assert len(result.scored_documents) == len(result.statements)
    assert len(result.counter_reports) == len(result.statements)
    assert len(result.verdicts) == len(result.statements)
    assert result.overall_assessment is not None

    # Verify data consistency
    for i, statement in enumerate(result.statements):
        # Each statement has corresponding data
        assert result.counter_statements[i].original_statement == statement
        assert len(result.search_results[i].deduplicated_docs) > 0
        assert len(result.scored_documents[i]) >= 0
        assert result.verdicts[i].counter_report == result.counter_reports[i]


def test_workflow_with_database_persistence(
    paper_checker_agent, sample_abstract, paper_check_db, mock_ollama_api
):
    """Test workflow with database persistence"""

    # Run check
    result = paper_checker_agent.check_abstract(
        abstract=sample_abstract,
        source_metadata={"pmid": 12345678}
    )

    # Should have been saved to database
    abstract_id = result.processing_metadata.get("abstract_id")
    assert abstract_id is not None
    assert abstract_id > 0

    # Verify can retrieve from database
    recent_checks = paper_check_db.list_recent_checks(limit=10)
    assert any(check["id"] == abstract_id for check in recent_checks)


def test_workflow_error_recovery(paper_checker_agent, mock_ollama_api):
    """Test error handling in workflow"""

    # Invalid abstract (too short)
    with pytest.raises(ValueError, match="too short"):
        paper_checker_agent.check_abstract(
            abstract="Too short",
            source_metadata={}
        )

    # Empty abstract
    with pytest.raises(ValueError, match="cannot be empty"):
        paper_checker_agent.check_abstract(
            abstract="",
            source_metadata={}
        )
```

## Performance Benchmarks (`test_performance.py`)

```python
"""
Performance benchmarks for PaperChecker
"""

import pytest
import time
from bmlibrarian.paperchecker.agent import PaperCheckerAgent


@pytest.mark.benchmark
def test_single_abstract_performance(paper_checker_agent, sample_abstract, mock_ollama_api):
    """Benchmark single abstract processing time"""

    start = time.time()
    result = paper_checker_agent.check_abstract(
        abstract=sample_abstract,
        source_metadata={}
    )
    end = time.time()

    processing_time = end - start

    # Should complete in reasonable time (< 5 minutes with mocks)
    assert processing_time < 300

    print(f"\nSingle abstract processing time: {processing_time:.2f}s")


@pytest.mark.benchmark
def test_batch_processing_performance(paper_checker_agent, sample_abstract, mock_ollama_api):
    """Benchmark batch processing"""

    abstracts = [
        {"abstract": sample_abstract, "metadata": {"pmid": i}}
        for i in range(10)
    ]

    start = time.time()
    results = paper_checker_agent.check_abstracts_batch(abstracts)
    end = time.time()

    processing_time = end - start
    avg_time = processing_time / len(abstracts)

    # Should process batch efficiently
    assert len(results) == len(abstracts)
    assert processing_time < 3000  # < 50 minutes for 10 abstracts

    print(f"\nBatch processing: {len(abstracts)} abstracts in {processing_time:.2f}s")
    print(f"Average per abstract: {avg_time:.2f}s")
```

## Running Tests

```bash
# Run all tests
uv run python -m pytest tests/paperchecker/ -v

# Run with coverage
uv run python -m pytest tests/paperchecker/ --cov=bmlibrarian.paperchecker --cov-report=html

# Run specific test file
uv run python -m pytest tests/paperchecker/test_end_to_end.py -v

# Run benchmarks
uv run python -m pytest tests/paperchecker/test_performance.py -m benchmark -v

# Run with verbose output
uv run python -m pytest tests/paperchecker/ -vv --log-cli-level=DEBUG
```

## Success Criteria

- [ ] All component unit tests passing
- [ ] Integration tests passing
- [ ] End-to-end tests passing
- [ ] Code coverage > 90%
- [ ] Performance benchmarks meet targets
- [ ] Error handling tests comprehensive
- [ ] Edge cases covered
- [ ] Mock LLM responses realistic
- [ ] Database fixtures working
- [ ] Test documentation complete

## Next Steps

After completing this step, proceed to:
- **Step 15**: Documentation (15_DOCUMENTATION.md)
- Comprehensive user and developer documentation
