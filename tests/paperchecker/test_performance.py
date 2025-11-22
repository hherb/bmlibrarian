"""
Performance tests and benchmarks for PaperChecker.

Tests cover:
    1. Response time benchmarks
    2. Memory usage patterns
    3. Batch processing efficiency
    4. JSON parsing performance
    5. Deduplication efficiency

These tests use pytest-benchmark markers and can be run with:
    pytest tests/paperchecker/test_performance.py -v --benchmark-only

Note: Tests marked with @pytest.mark.benchmark require pytest-benchmark.
      Tests marked with @pytest.mark.slow are skipped by default.
"""

import json
import time
import pytest
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

from bmlibrarian.paperchecker.data_models import (
    Statement,
    CounterStatement,
    SearchResults,
    ScoredDocument,
    ExtractedCitation,
    CounterReport,
    Verdict,
    PaperCheckResult,
)
from bmlibrarian.paperchecker.components.statement_extractor import StatementExtractor
from bmlibrarian.paperchecker.components.hyde_generator import HyDEGenerator


# ==================== PERFORMANCE CONSTANTS ====================

# Timing thresholds in seconds
MAX_STATEMENT_PARSE_TIME: float = 0.1
MAX_JSON_EXTRACT_TIME: float = 0.01
MAX_DEDUPLICATION_TIME: float = 0.1

# Size thresholds
LARGE_DOCUMENT_COUNT: int = 1000
LARGE_KEYWORD_COUNT: int = 100


# ==================== JSON PARSING BENCHMARKS ====================

class TestJsonParsingPerformance:
    """Benchmark JSON parsing operations."""

    @patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client')
    def test_json_extraction_speed(self, mock_client: MagicMock) -> None:
        """Test that JSON extraction completes within time limit."""
        extractor = StatementExtractor(model="test-model")

        # Create a complex response with nested JSON in markdown
        complex_response = '''
        Here is my analysis of the medical abstract:

        Based on the content, I have identified the following key statements:

        ```json
        {
            "statements": [
                {
                    "text": "This is a test statement about clinical outcomes",
                    "context": "In this randomized controlled trial, we examined...",
                    "statement_type": "finding",
                    "confidence": 0.95
                },
                {
                    "text": "Another statement about drug efficacy",
                    "context": "Previous studies have shown...",
                    "statement_type": "conclusion",
                    "confidence": 0.88
                }
            ]
        }
        ```

        These statements represent the key findings of the study.
        '''

        start_time = time.time()
        for _ in range(100):
            extractor._extract_json(complex_response)
        elapsed = time.time() - start_time

        avg_time = elapsed / 100
        assert avg_time < MAX_JSON_EXTRACT_TIME, \
            f"JSON extraction took {avg_time:.4f}s avg, expected < {MAX_JSON_EXTRACT_TIME}s"

    @patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client')
    def test_statement_parsing_speed(self, mock_client: MagicMock) -> None:
        """Test that statement parsing completes within time limit."""
        extractor = StatementExtractor(model="test-model", max_statements=10)

        # Create a large response with many statements
        statements_data = [
            {
                "text": f"Statement {i} about medical treatment efficacy in patients.",
                "context": f"Context {i} providing background information about the study.",
                "statement_type": ["hypothesis", "finding", "conclusion"][i % 3],
                "confidence": 0.7 + (i % 30) / 100
            }
            for i in range(10)
        ]
        response = json.dumps({"statements": statements_data})

        start_time = time.time()
        for _ in range(50):
            extractor._parse_response(response)
        elapsed = time.time() - start_time

        avg_time = elapsed / 50
        assert avg_time < MAX_STATEMENT_PARSE_TIME, \
            f"Statement parsing took {avg_time:.4f}s avg, expected < {MAX_STATEMENT_PARSE_TIME}s"


# ==================== DEDUPLICATION BENCHMARKS ====================

class TestDeduplicationPerformance:
    """Benchmark deduplication operations."""

    def test_search_results_deduplication_speed(self) -> None:
        """Test that deduplication handles large doc sets efficiently."""
        # Create large strategy result sets with overlap
        semantic_docs = list(range(0, LARGE_DOCUMENT_COUNT, 3))  # 0, 3, 6, ...
        hyde_docs = list(range(1, LARGE_DOCUMENT_COUNT, 3))  # 1, 4, 7, ...
        keyword_docs = list(range(2, LARGE_DOCUMENT_COUNT, 3))  # 2, 5, 8, ...

        start_time = time.time()
        for _ in range(10):
            SearchResults.from_strategy_results(
                semantic=semantic_docs,
                hyde=hyde_docs,
                keyword=keyword_docs,
                metadata={"test": "value"}
            )
        elapsed = time.time() - start_time

        avg_time = elapsed / 10
        assert avg_time < MAX_DEDUPLICATION_TIME, \
            f"Deduplication took {avg_time:.4f}s avg for {LARGE_DOCUMENT_COUNT} docs"

    def test_provenance_tracking_speed(self) -> None:
        """Test that provenance tracking is efficient for overlapping results."""
        # Create results with high overlap
        base_docs = list(range(500))
        semantic = base_docs[:400]
        hyde = base_docs[100:500]
        keyword = base_docs[200:450]

        start_time = time.time()
        for _ in range(20):
            results = SearchResults.from_strategy_results(
                semantic=semantic,
                hyde=hyde,
                keyword=keyword,
                metadata={}
            )
            # Access provenance to ensure it's computed
            _ = len(results.provenance)
        elapsed = time.time() - start_time

        avg_time = elapsed / 20
        assert avg_time < MAX_DEDUPLICATION_TIME


# ==================== DATA MODEL CREATION BENCHMARKS ====================

class TestDataModelCreationPerformance:
    """Benchmark data model object creation."""

    def test_statement_creation_speed(self) -> None:
        """Test that Statement creation is fast."""
        start_time = time.time()
        for i in range(1000):
            Statement(
                text=f"Test statement {i} about medical treatment outcomes.",
                context=f"Context {i} with background information.",
                statement_type="finding",
                confidence=0.85,
                statement_order=i + 1
            )
        elapsed = time.time() - start_time

        assert elapsed < 1.0, f"Creating 1000 Statements took {elapsed:.2f}s, expected < 1s"

    def test_scored_document_creation_speed(self) -> None:
        """Test that ScoredDocument creation is fast."""
        document_data = {
            "id": 1,
            "title": "Test Document Title",
            "abstract": "This is a test abstract " * 50,
            "authors": ["Author A", "Author B", "Author C"],
            "publication_date": "2023-01-15",
            "journal": "Test Journal",
            "pmid": "12345678",
            "doi": "10.1000/test.12345"
        }

        start_time = time.time()
        for i in range(1, 1001):  # Start from 1 since doc_id must be >= 1
            ScoredDocument(
                doc_id=i,
                document=document_data.copy(),
                score=4,
                explanation="Relevant document explaining findings.",
                supports_counter=True,
                found_by=["semantic", "hyde"]
            )
        elapsed = time.time() - start_time

        assert elapsed < 1.0, f"Creating 1000 ScoredDocuments took {elapsed:.2f}s"

    def test_citation_creation_speed(self) -> None:
        """Test that ExtractedCitation creation is fast."""
        start_time = time.time()
        for i in range(1000):
            ExtractedCitation(
                doc_id=i,
                passage=f"Evidence passage {i} from the document " * 5,
                relevance_score=4,
                full_citation=f"Author {i}. Title {i}. Journal. 2023;1:1-10.",
                metadata={
                    "pmid": str(10000000 + i),
                    "doi": f"10.1000/test.{i}",
                    "year": 2023,
                },
                citation_order=i + 1
            )
        elapsed = time.time() - start_time

        assert elapsed < 1.0, f"Creating 1000 Citations took {elapsed:.2f}s"


# ==================== SERIALIZATION BENCHMARKS ====================

class TestSerializationPerformance:
    """Benchmark serialization and deserialization operations."""

    def test_paper_check_result_serialization(
        self,
        sample_paper_check_result: PaperCheckResult
    ) -> None:
        """Test PaperCheckResult serialization speed."""
        start_time = time.time()
        for _ in range(100):
            # Serialize to dict (if method exists)
            if hasattr(sample_paper_check_result, 'to_dict'):
                _ = sample_paper_check_result.to_dict()
            else:
                # Fallback to dataclasses asdict
                import dataclasses
                _ = dataclasses.asdict(sample_paper_check_result)
        elapsed = time.time() - start_time

        avg_time = elapsed / 100
        assert avg_time < 0.1, f"Serialization took {avg_time:.4f}s avg, expected < 0.1s"

    def test_markdown_report_generation_speed(
        self,
        sample_paper_check_result: PaperCheckResult
    ) -> None:
        """Test markdown report generation speed."""
        start_time = time.time()
        for _ in range(50):
            _ = sample_paper_check_result.to_markdown_report()
        elapsed = time.time() - start_time

        avg_time = elapsed / 50
        assert avg_time < 0.1, f"Markdown generation took {avg_time:.4f}s avg, expected < 0.1s"


# ==================== MEMORY EFFICIENCY TESTS ====================

class TestMemoryEfficiency:
    """Test memory efficiency of data structures."""

    def test_search_results_memory_for_large_sets(self) -> None:
        """Test that SearchResults handles large sets without excessive memory."""
        import sys

        # Create a large SearchResults
        semantic = list(range(10000))
        hyde = list(range(5000, 15000))
        keyword = list(range(10000, 20000))

        results = SearchResults.from_strategy_results(
            semantic=semantic,
            hyde=hyde,
            keyword=keyword,
            metadata={}
        )

        # Get approximate size
        size = sys.getsizeof(results)
        size += sys.getsizeof(results.deduplicated_docs)
        size += sys.getsizeof(results.provenance)

        # Should be reasonable (less than 10MB for this test case)
        assert size < 10 * 1024 * 1024, f"SearchResults too large: {size / 1024 / 1024:.2f} MB"

    def test_counter_statement_memory_efficiency(
        self,
        sample_statement: Statement
    ) -> None:
        """Test that CounterStatement doesn't duplicate statement data."""
        import sys

        # Create CounterStatement
        counter = CounterStatement(
            original_statement=sample_statement,
            negated_text="Counter to original statement",
            hyde_abstracts=["Abstract " * 100 for _ in range(3)],
            keywords=["keyword"] * 20,
            generation_metadata={"model": "test"}
        )

        # Check that original_statement is a reference, not a copy
        assert counter.original_statement is sample_statement


# ==================== BATCH PROCESSING TESTS ====================

@pytest.mark.slow
class TestBatchProcessing:
    """Test batch processing efficiency (marked as slow)."""

    def test_batch_statement_extraction_efficiency(self) -> None:
        """Test efficiency of processing multiple abstracts."""
        # Create mock abstracts
        abstracts = [
            f"Abstract {i}: This study investigates the efficacy of treatment {i}. "
            "Background: Previous research has shown mixed results. "
            "Methods: We conducted a randomized controlled trial. "
            "Results: Treatment group showed significant improvement. "
            "Conclusion: The treatment is effective for this condition."
            for i in range(10)
        ]

        with patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client') as mock_client:
            mock_instance = MagicMock()
            mock_instance.chat.return_value = {
                "message": {"content": json.dumps({
                    "statements": [{
                        "text": "Test statement",
                        "context": "Test context",
                        "statement_type": "finding",
                        "confidence": 0.9
                    }]
                })}
            }
            mock_client.return_value = mock_instance

            extractor = StatementExtractor(model="test-model")

            start_time = time.time()
            for abstract in abstracts:
                _ = extractor.extract(abstract)
            elapsed = time.time() - start_time

            # Should process 10 abstracts quickly (mocked LLM)
            assert elapsed < 1.0, f"Batch processing took {elapsed:.2f}s for 10 abstracts"


# ==================== STRESS TESTS ====================

@pytest.mark.slow
class TestStressConditions:
    """Test behavior under stress conditions (marked as slow)."""

    def test_large_abstract_handling(self) -> None:
        """Test handling of very large abstracts."""
        # Create a large abstract (10000 chars)
        large_abstract = "This is a test sentence. " * 500

        with patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client') as mock_client:
            mock_instance = MagicMock()
            mock_instance.chat.return_value = {
                "message": {"content": json.dumps({
                    "statements": [{
                        "text": "Test statement",
                        "context": "Test context",
                        "statement_type": "finding",
                        "confidence": 0.9
                    }]
                })}
            }
            mock_client.return_value = mock_instance

            extractor = StatementExtractor(model="test-model")

            start_time = time.time()
            result = extractor.extract(large_abstract)
            elapsed = time.time() - start_time

            assert len(result) > 0
            assert elapsed < 2.0, f"Large abstract processing took {elapsed:.2f}s"

    def test_many_keywords_handling(self) -> None:
        """Test handling of many keywords."""
        with patch('bmlibrarian.paperchecker.components.hyde_generator.ollama.Client') as mock_client:
            mock_instance = MagicMock()
            mock_instance.chat.return_value = {
                "message": {"content": json.dumps({
                    "hyde_abstracts": ["A" * 150 for _ in range(3)],
                    "keywords": [f"keyword_{i}" for i in range(LARGE_KEYWORD_COUNT)]
                })}
            }
            mock_client.return_value = mock_instance

            generator = HyDEGenerator(model="test-model", max_keywords=LARGE_KEYWORD_COUNT)

            statement = Statement(
                text="Test statement",
                context="Test context",
                statement_type="finding",
                confidence=0.9,
                statement_order=1
            )

            start_time = time.time()
            result = generator.generate(statement, "Counter statement")
            elapsed = time.time() - start_time

            assert len(result["keywords"]) <= LARGE_KEYWORD_COUNT
            assert elapsed < 1.0, f"Keyword processing took {elapsed:.2f}s"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--ignore-glob=*slow*"])
