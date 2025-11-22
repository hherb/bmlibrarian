"""
End-to-end integration tests for PaperChecker workflow.

Tests the complete workflow from abstract input to final verdict,
verifying that all components integrate correctly.

Test Categories:
    1. Full workflow tests (statement -> verdict)
    2. Multi-statement processing
    3. Error propagation and handling
    4. Result data model integrity
    5. Markdown report generation
"""

import json
import pytest
from typing import List
from unittest.mock import MagicMock, patch, PropertyMock

from bmlibrarian.paperchecker.data_models import (
    Statement,
    CounterStatement,
    SearchResults,
    ScoredDocument,
    ExtractedCitation,
    CounterReport,
    Verdict,
    PaperCheckResult,
    VALID_VERDICT_VALUES,
    VALID_CONFIDENCE_LEVELS,
)
from bmlibrarian.paperchecker.components import (
    StatementExtractor,
    CounterStatementGenerator,
    HyDEGenerator,
    SearchCoordinator,
    VerdictAnalyzer,
)


# ==================== FULL WORKFLOW TESTS ====================

class TestFullWorkflow:
    """Test complete end-to-end workflow."""

    def test_statement_extraction_produces_valid_statements(
        self,
        sample_abstract,
        statement_extraction_response
    ):
        """Test that statement extraction produces valid Statement objects."""
        with patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client') as mock_client:
            mock_instance = MagicMock()
            mock_instance.chat.return_value = {
                "message": {"content": statement_extraction_response}
            }
            mock_client.return_value = mock_instance

            extractor = StatementExtractor(model="test-model")
            statements = extractor.extract(sample_abstract)

            assert len(statements) > 0
            assert all(isinstance(s, Statement) for s in statements)
            assert all(s.statement_order > 0 for s in statements)
            assert all(s.statement_type in ["hypothesis", "finding", "conclusion"] for s in statements)

    def test_counter_generation_produces_valid_output(
        self,
        sample_statement,
        counter_statement_response
    ):
        """Test that counter generation produces valid output."""
        with patch('bmlibrarian.paperchecker.components.counter_statement_generator.ollama.Client') as mock_client:
            mock_instance = MagicMock()
            mock_instance.chat.return_value = {
                "message": {"content": counter_statement_response}
            }
            mock_client.return_value = mock_instance

            generator = CounterStatementGenerator(model="test-model")
            counter_text = generator.generate(sample_statement)

            assert isinstance(counter_text, str)
            assert len(counter_text) > 10

    def test_hyde_generation_produces_valid_materials(
        self,
        sample_statement,
        hyde_generation_response
    ):
        """Test that HyDE generation produces valid materials."""
        with patch('bmlibrarian.paperchecker.components.hyde_generator.ollama.Client') as mock_client:
            mock_instance = MagicMock()
            mock_instance.chat.return_value = {
                "message": {"content": hyde_generation_response}
            }
            mock_client.return_value = mock_instance

            generator = HyDEGenerator(model="test-model")
            materials = generator.generate(
                sample_statement,
                "Test counter-statement for HyDE generation"
            )

            assert "hyde_abstracts" in materials
            assert "keywords" in materials
            assert len(materials["hyde_abstracts"]) > 0
            assert len(materials["keywords"]) > 0

    def test_verdict_analysis_produces_valid_verdict(
        self,
        sample_statement,
        sample_counter_report,
        verdict_analysis_response
    ):
        """Test that verdict analysis produces valid verdict."""
        with patch('bmlibrarian.paperchecker.components.verdict_analyzer.ollama.Client') as mock_client:
            mock_instance = MagicMock()
            mock_instance.chat.return_value = {
                "message": {"content": verdict_analysis_response}
            }
            mock_client.return_value = mock_instance

            analyzer = VerdictAnalyzer(model="test-model")
            verdict = analyzer.analyze(sample_statement, sample_counter_report)

            assert isinstance(verdict, Verdict)
            assert verdict.verdict in VALID_VERDICT_VALUES
            assert verdict.confidence in VALID_CONFIDENCE_LEVELS
            assert len(verdict.rationale) > 0


# ==================== DATA FLOW TESTS ====================

class TestDataFlowIntegrity:
    """Test data integrity through the workflow."""

    def test_statement_to_counter_statement_linkage(
        self,
        sample_statement,
        counter_statement_response
    ):
        """Test that CounterStatement correctly links to original Statement."""
        with patch('bmlibrarian.paperchecker.components.counter_statement_generator.ollama.Client') as mock_client:
            mock_instance = MagicMock()
            mock_instance.chat.return_value = {
                "message": {"content": counter_statement_response}
            }
            mock_client.return_value = mock_instance

            generator = CounterStatementGenerator(model="test-model")
            counter_text = generator.generate(sample_statement)

        counter_stmt = CounterStatement(
            original_statement=sample_statement,
            negated_text=counter_text,
            hyde_abstracts=["Test abstract " * 20],
            keywords=["test keyword"],
            generation_metadata={"model": "test-model"}
        )

        assert counter_stmt.original_statement is sample_statement
        assert counter_stmt.original_statement.text == sample_statement.text

    def test_search_results_deduplication_consistency(
        self,
        sample_search_results
    ):
        """Test that SearchResults maintains consistency in deduplication."""
        # Verify deduplicated_docs is subset of all strategy results
        all_docs = set(
            sample_search_results.semantic_docs +
            sample_search_results.hyde_docs +
            sample_search_results.keyword_docs
        )

        for doc_id in sample_search_results.deduplicated_docs:
            assert doc_id in all_docs

    def test_provenance_tracking_accuracy(
        self,
        sample_search_results
    ):
        """Test that provenance correctly tracks which strategies found each doc."""
        for doc_id, strategies in sample_search_results.provenance.items():
            # Verify the provenance matches actual strategy results
            if "semantic" in strategies:
                assert doc_id in sample_search_results.semantic_docs
            if "hyde" in strategies:
                assert doc_id in sample_search_results.hyde_docs
            if "keyword" in strategies:
                assert doc_id in sample_search_results.keyword_docs

    def test_verdict_references_counter_report(
        self,
        sample_verdict,
        sample_counter_report
    ):
        """Test that Verdict correctly references its CounterReport."""
        assert sample_verdict.counter_report is sample_counter_report


# ==================== PAPER CHECK RESULT TESTS ====================

class TestPaperCheckResult:
    """Test PaperCheckResult data model integrity."""

    def test_result_has_matching_list_lengths(
        self,
        sample_paper_check_result
    ):
        """Test that all lists in result have matching lengths."""
        result = sample_paper_check_result
        num_statements = len(result.statements)

        assert len(result.counter_statements) == num_statements
        assert len(result.search_results) == num_statements
        assert len(result.scored_documents) == num_statements
        assert len(result.counter_reports) == num_statements
        assert len(result.verdicts) == num_statements

    def test_result_source_metadata_complete(
        self,
        sample_paper_check_result
    ):
        """Test that source metadata contains expected fields."""
        metadata = sample_paper_check_result.source_metadata

        assert "pmid" in metadata or "doi" in metadata
        if "pmid" in metadata:
            assert isinstance(metadata["pmid"], int)

    def test_result_processing_metadata_exists(
        self,
        sample_paper_check_result
    ):
        """Test that processing metadata is populated."""
        metadata = sample_paper_check_result.processing_metadata

        assert "model" in metadata

    def test_result_overall_assessment_populated(
        self,
        sample_paper_check_result
    ):
        """Test that overall assessment is populated."""
        assert len(sample_paper_check_result.overall_assessment) > 0


# ==================== MARKDOWN REPORT TESTS ====================

class TestMarkdownReportGeneration:
    """Test markdown report generation from results."""

    def test_paper_check_result_to_markdown(
        self,
        sample_paper_check_result
    ):
        """Test markdown report generation from PaperCheckResult."""
        # The to_markdown_report method should exist
        assert hasattr(sample_paper_check_result, 'to_markdown_report')

        report = sample_paper_check_result.to_markdown_report()

        assert isinstance(report, str)
        assert len(report) > 0
        assert "#" in report  # Should have markdown headers

    def test_markdown_report_contains_key_sections(
        self,
        sample_paper_check_result
    ):
        """Test that markdown report contains expected sections."""
        report = sample_paper_check_result.to_markdown_report()

        # Should contain key sections
        assert "statement" in report.lower() or "claim" in report.lower()
        assert "verdict" in report.lower() or "conclusion" in report.lower()


# ==================== ERROR HANDLING TESTS ====================

class TestErrorHandling:
    """Test error handling across the workflow."""

    def test_extraction_error_propagates_correctly(
        self,
        sample_abstract
    ):
        """Test that extraction errors propagate as RuntimeError."""
        with patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client') as mock_client:
            mock_instance = MagicMock()
            mock_instance.chat.side_effect = Exception("LLM unavailable")
            mock_client.return_value = mock_instance

            extractor = StatementExtractor(model="test-model")

            with pytest.raises(RuntimeError, match="Failed to extract"):
                extractor.extract(sample_abstract)

    def test_counter_generation_error_propagates(
        self,
        sample_statement
    ):
        """Test that counter generation errors propagate as RuntimeError."""
        with patch('bmlibrarian.paperchecker.components.counter_statement_generator.ollama.Client') as mock_client:
            mock_instance = MagicMock()
            mock_instance.chat.side_effect = Exception("LLM unavailable")
            mock_client.return_value = mock_instance

            generator = CounterStatementGenerator(model="test-model")

            with pytest.raises(RuntimeError, match="Failed to generate"):
                generator.generate(sample_statement)

    def test_verdict_error_propagates(
        self,
        sample_statement,
        sample_counter_report
    ):
        """Test that verdict errors propagate as RuntimeError."""
        with patch('bmlibrarian.paperchecker.components.verdict_analyzer.ollama.Client') as mock_client:
            mock_instance = MagicMock()
            mock_instance.chat.side_effect = Exception("LLM unavailable")
            mock_client.return_value = mock_instance

            analyzer = VerdictAnalyzer(model="test-model")

            with pytest.raises(RuntimeError, match="LLM call failed"):
                analyzer.analyze(sample_statement, sample_counter_report)


# ==================== MULTI-STATEMENT TESTS ====================

class TestMultiStatementProcessing:
    """Test processing multiple statements."""

    def test_multiple_statements_produce_multiple_verdicts(
        self,
        counter_statement_response
    ):
        """Test that multiple statements produce multiple verdicts."""
        # Create multiple statements
        statements = [
            Statement(
                text=f"Statement {i} about diabetes treatment",
                context="Test context",
                statement_type="finding",
                confidence=0.8,
                statement_order=i
            )
            for i in range(1, 4)
        ]

        with patch('bmlibrarian.paperchecker.components.counter_statement_generator.ollama.Client') as mock_client:
            mock_instance = MagicMock()
            mock_instance.chat.return_value = {
                "message": {"content": counter_statement_response}
            }
            mock_client.return_value = mock_instance

            # Verify we can create counter-statements for each
            generator = CounterStatementGenerator(model="test-model")
            counter_texts = [generator.generate(stmt) for stmt in statements]

            assert len(counter_texts) == 3
            assert all(len(ct) > 10 for ct in counter_texts)

    def test_overall_assessment_aggregates_verdicts(
        self,
        sample_counter_report
    ):
        """Test that overall assessment aggregates multiple verdicts."""
        with patch('bmlibrarian.paperchecker.components.verdict_analyzer.ollama.Client'):
            analyzer = VerdictAnalyzer(model="test-model")

        statements = [
            Statement(
                text=f"Statement {i}",
                context="",
                statement_type="finding",
                confidence=0.8,
                statement_order=i
            )
            for i in range(1, 4)
        ]

        verdicts = [
            Verdict(
                verdict="contradicts" if i == 1 else "supports",
                rationale=f"Rationale for statement {i} " * 5,
                confidence="high",
                counter_report=sample_counter_report,
                analysis_metadata={}
            )
            for i in range(1, 4)
        ]

        assessment = analyzer.generate_overall_assessment(statements, verdicts)

        assert len(assessment) > 0
        # Should mention both supported and contradicted
        assert "support" in assessment.lower() or "contradict" in assessment.lower()


# ==================== DATA MODEL VALIDATION TESTS ====================

class TestDataModelValidation:
    """Test data model validation across the workflow."""

    def test_statement_type_validation(self):
        """Test that invalid statement types are rejected."""
        with pytest.raises((ValueError, AssertionError)):
            Statement(
                text="Test statement",
                context="Test context",
                statement_type="invalid_type",
                confidence=0.8,
                statement_order=1
            )

    def test_verdict_value_validation(self, sample_counter_report):
        """Test that invalid verdict values are rejected."""
        with pytest.raises((ValueError, AssertionError)):
            Verdict(
                verdict="invalid_verdict",
                rationale="Test rationale " * 5,
                confidence="high",
                counter_report=sample_counter_report,
                analysis_metadata={}
            )

    def test_confidence_level_validation(self, sample_counter_report):
        """Test that invalid confidence levels are rejected."""
        with pytest.raises((ValueError, AssertionError)):
            Verdict(
                verdict="contradicts",
                rationale="Test rationale " * 5,
                confidence="invalid_confidence",
                counter_report=sample_counter_report,
                analysis_metadata={}
            )

    def test_search_results_factory_method(self):
        """Test SearchResults.from_strategy_results factory method."""
        results = SearchResults.from_strategy_results(
            semantic=[1, 2, 3],
            hyde=[2, 3, 4],
            keyword=[3, 4, 5],
            metadata={"test": "value"}
        )

        assert len(results.semantic_docs) == 3
        assert len(results.hyde_docs) == 3
        assert len(results.keyword_docs) == 3
        # Deduplicated should have 5 unique docs
        assert len(results.deduplicated_docs) == 5
        assert results.search_metadata["test"] == "value"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
