"""
Unit tests for PDF Upload workers.

Tests the QThread-based workers used by PDFUploadWidget:
- QuickExtractWorker: Fast regex extraction
- LLMExtractWorker: LLM-based metadata extraction
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from dataclasses import asdict

from bmlibrarian.gui.qt.widgets.pdf_upload_workers import (
    QuickExtractWorker,
    LLMExtractWorker,
    QuickMatchResult,
    LLMExtractResult,
)
from bmlibrarian.importers.pdf_matcher import ExtractedIdentifiers


class TestQuickMatchResult:
    """Tests for QuickMatchResult dataclass."""

    def test_creation_success(self):
        """Test successful result creation."""
        result = QuickMatchResult(
            success=True,
            identifiers=ExtractedIdentifiers(doi="10.1234/test", pmid="12345"),
            document={"id": 1, "title": "Test"},
            extracted_text="Test text"
        )
        assert result.success is True
        assert result.has_quick_match() is True
        assert result.document["id"] == 1

    def test_creation_no_match(self):
        """Test result with no match."""
        result = QuickMatchResult(
            success=True,
            identifiers=ExtractedIdentifiers(doi="10.1234/test"),
            extracted_text="Test text"
        )
        assert result.success is True
        assert result.has_quick_match() is False
        assert result.document is None

    def test_creation_failure(self):
        """Test failed result creation."""
        result = QuickMatchResult(
            success=False,
            error="Could not extract text"
        )
        assert result.success is False
        assert result.has_quick_match() is False
        assert result.error == "Could not extract text"


class TestLLMExtractResult:
    """Tests for LLMExtractResult dataclass."""

    def test_creation_success_with_match(self):
        """Test successful result with document match."""
        result = LLMExtractResult(
            success=True,
            metadata={"title": "Test", "doi": "10.1234/test"},
            document={"id": 1, "title": "Test"},
            alternatives=[{"id": 2, "title": "Alternative"}]
        )
        assert result.success is True
        assert result.metadata["title"] == "Test"
        assert result.document is not None
        assert len(result.alternatives) == 1

    def test_creation_success_no_match(self):
        """Test successful extraction with no database match."""
        result = LLMExtractResult(
            success=True,
            metadata={"title": "New Paper"},
            document=None,
            alternatives=[]
        )
        assert result.success is True
        assert result.document is None

    def test_creation_failure(self):
        """Test failed extraction."""
        result = LLMExtractResult(
            success=False,
            error="LLM service unavailable"
        )
        assert result.success is False
        assert "unavailable" in result.error


class TestQuickExtractWorker:
    """Tests for QuickExtractWorker thread."""

    @patch('bmlibrarian.gui.qt.widgets.pdf_upload_workers.PDFMatcher')
    def test_initialization(self, mock_matcher):
        """Test worker initialization."""
        worker = QuickExtractWorker(Path("/test/file.pdf"))
        assert worker.pdf_path == Path("/test/file.pdf")
        assert worker._matcher is None

    @patch('bmlibrarian.gui.qt.widgets.pdf_upload_workers.PDFMatcher')
    def test_run_emits_quick_match_found(self, MockMatcher):
        """Test run emits quick_match_found when match found."""
        # Setup mock
        mock_instance = MockMatcher.return_value
        mock_instance.extract_first_page_text.return_value = "DOI: 10.1234/test"
        mock_instance.extract_identifiers_regex.return_value = ExtractedIdentifiers(
            doi="10.1234/test"
        )
        mock_instance.quick_database_lookup.return_value = {
            "id": 1,
            "title": "Test Document"
        }

        # Create worker and connect signals
        worker = QuickExtractWorker(Path("/test/file.pdf"))
        received_result = []
        worker.quick_match_found.connect(lambda r: received_result.append(r))

        # Run directly (not threaded for testing)
        worker.run()

        # Verify
        assert len(received_result) == 1
        assert received_result[0].success is True
        assert received_result[0].document is not None

    @patch('bmlibrarian.gui.qt.widgets.pdf_upload_workers.PDFMatcher')
    def test_run_emits_no_quick_match(self, MockMatcher):
        """Test run emits no_quick_match when no identifiers found."""
        mock_instance = MockMatcher.return_value
        mock_instance.extract_first_page_text.return_value = "Some text without DOI"
        mock_instance.extract_identifiers_regex.return_value = ExtractedIdentifiers()

        worker = QuickExtractWorker(Path("/test/file.pdf"))
        received_result = []
        worker.no_quick_match.connect(lambda r: received_result.append(r))

        worker.run()

        assert len(received_result) == 1
        assert received_result[0].success is True
        assert received_result[0].document is None

    @patch('bmlibrarian.gui.qt.widgets.pdf_upload_workers.PDFMatcher')
    def test_run_emits_error_on_extraction_failure(self, MockMatcher):
        """Test run emits error when text extraction fails."""
        mock_instance = MockMatcher.return_value
        mock_instance.extract_first_page_text.return_value = None

        worker = QuickExtractWorker(Path("/test/file.pdf"))
        received_errors = []
        worker.error_occurred.connect(lambda e: received_errors.append(e))

        worker.run()

        assert len(received_errors) == 1
        assert "extract" in received_errors[0].lower()

    @patch('bmlibrarian.gui.qt.widgets.pdf_upload_workers.PDFMatcher')
    def test_run_emits_error_on_exception(self, MockMatcher):
        """Test run emits error when exception occurs."""
        MockMatcher.side_effect = Exception("Connection error")

        worker = QuickExtractWorker(Path("/test/file.pdf"))
        received_errors = []
        worker.error_occurred.connect(lambda e: received_errors.append(e))

        worker.run()

        assert len(received_errors) == 1
        assert "Connection error" in received_errors[0]


class TestLLMExtractWorker:
    """Tests for LLMExtractWorker thread."""

    def test_initialization(self):
        """Test worker initialization."""
        worker = LLMExtractWorker("Test text content")
        assert worker.extracted_text == "Test text content"
        assert worker._matcher is None

    @patch('bmlibrarian.gui.qt.widgets.pdf_upload_workers.PDFMatcher')
    @patch('bmlibrarian.gui.qt.widgets.pdf_upload_workers.sanitize_llm_input')
    def test_run_emits_extraction_complete(self, mock_sanitize, MockMatcher):
        """Test run emits extraction_complete on success."""
        mock_sanitize.return_value = "Sanitized text"

        mock_instance = MockMatcher.return_value
        mock_instance.extract_metadata_with_llm.return_value = {
            "title": "Test Paper",
            "doi": "10.1234/test",
            "authors": ["Author One"]
        }
        mock_instance.find_matching_document.return_value = {
            "id": 1,
            "title": "Test Paper"
        }
        mock_instance.find_alternative_matches.return_value = []

        worker = LLMExtractWorker("Test text")
        received_results = []
        worker.extraction_complete.connect(lambda r: received_results.append(r))

        worker.run()

        assert len(received_results) == 1
        assert received_results[0].success is True
        assert received_results[0].metadata["title"] == "Test Paper"

    @patch('bmlibrarian.gui.qt.widgets.pdf_upload_workers.PDFMatcher')
    @patch('bmlibrarian.gui.qt.widgets.pdf_upload_workers.sanitize_llm_input')
    def test_run_sanitizes_input(self, mock_sanitize, MockMatcher):
        """Test that input text is sanitized before LLM processing."""
        mock_sanitize.return_value = "Sanitized text"
        mock_instance = MockMatcher.return_value
        mock_instance.extract_metadata_with_llm.return_value = {"title": "Test"}

        worker = LLMExtractWorker("Raw text with <|im_start|> injection")
        worker.run()

        # Verify sanitize was called with the original text
        mock_sanitize.assert_called_once_with("Raw text with <|im_start|> injection")
        # Verify LLM received sanitized text
        mock_instance.extract_metadata_with_llm.assert_called_once_with("Sanitized text")

    @patch('bmlibrarian.gui.qt.widgets.pdf_upload_workers.PDFMatcher')
    @patch('bmlibrarian.gui.qt.widgets.pdf_upload_workers.sanitize_llm_input')
    def test_run_emits_error_when_sanitization_returns_empty(
        self, mock_sanitize, MockMatcher
    ):
        """Test error is emitted when sanitization returns empty string."""
        mock_sanitize.return_value = ""

        worker = LLMExtractWorker("Some text")
        received_errors = []
        worker.error_occurred.connect(lambda e: received_errors.append(e))

        worker.run()

        assert len(received_errors) == 1
        assert "sanitization" in received_errors[0].lower()

    @patch('bmlibrarian.gui.qt.widgets.pdf_upload_workers.PDFMatcher')
    @patch('bmlibrarian.gui.qt.widgets.pdf_upload_workers.sanitize_llm_input')
    def test_run_emits_error_when_llm_fails(self, mock_sanitize, MockMatcher):
        """Test error is emitted when LLM extraction fails."""
        mock_sanitize.return_value = "Sanitized text"
        mock_instance = MockMatcher.return_value
        mock_instance.extract_metadata_with_llm.return_value = None

        worker = LLMExtractWorker("Test text")
        received_errors = []
        worker.error_occurred.connect(lambda e: received_errors.append(e))

        worker.run()

        assert len(received_errors) == 1
        assert "failed" in received_errors[0].lower()

    @patch('bmlibrarian.gui.qt.widgets.pdf_upload_workers.PDFMatcher')
    @patch('bmlibrarian.gui.qt.widgets.pdf_upload_workers.sanitize_llm_input')
    def test_run_handles_no_useful_metadata(self, mock_sanitize, MockMatcher):
        """Test handling when LLM returns metadata without useful fields."""
        mock_sanitize.return_value = "Sanitized text"
        mock_instance = MockMatcher.return_value
        mock_instance.extract_metadata_with_llm.return_value = {
            "authors": ["Unknown"]
        }  # No doi, pmid, or title

        worker = LLMExtractWorker("Test text")
        received_results = []
        worker.extraction_complete.connect(lambda r: received_results.append(r))

        worker.run()

        assert len(received_results) == 1
        assert received_results[0].success is True
        assert received_results[0].error is not None  # Should have error message

    @patch('bmlibrarian.gui.qt.widgets.pdf_upload_workers.PDFMatcher')
    @patch('bmlibrarian.gui.qt.widgets.pdf_upload_workers.sanitize_llm_input')
    def test_run_emits_error_on_exception(self, mock_sanitize, MockMatcher):
        """Test error is emitted when exception occurs."""
        mock_sanitize.return_value = "Sanitized text"
        MockMatcher.side_effect = Exception("Service unavailable")

        worker = LLMExtractWorker("Test text")
        received_errors = []
        worker.error_occurred.connect(lambda e: received_errors.append(e))

        worker.run()

        assert len(received_errors) == 1
        assert "unavailable" in received_errors[0]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
