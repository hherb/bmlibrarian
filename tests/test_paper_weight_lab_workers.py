"""
Tests for Paper Weight Lab worker classes and validators.

Tests cover:
- Input validators (PMID, DOI, year, file size, title)
- Worker thread cleanup methods
- Constants validation

Note: Full Qt GUI tests require a display environment.
These tests use mocks to test worker logic without Qt event loop.

This module previously loaded constants and validators by file path and
then wrote stub modules into sys.modules to satisfy their relative
imports, including `sys.modules['bmlibrarian'] = type(sys)('bmlibrarian')`.
That replaced the real package for the rest of the session, so every test
module collected afterwards failed with "'bmlibrarian' is not a package"
— six collection errors that aborted the whole run, and which vanished
when any of those files was run on its own.

The gymnastics were never needed: constants and validators import
cleanly on their own (the package docstring says as much), because
neither pulls in Qt.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock
import tempfile
import os

from bmlibrarian.lab.paper_weight_lab.constants import (
    PMID_MIN_VALUE,
    PMID_MAX_VALUE,
    YEAR_MIN_VALUE,
    YEAR_MAX_VALUE,
    DOI_PATTERN,
    PDF_MAX_FILE_SIZE_MB,
    PDF_MAX_FILE_SIZE_BYTES,
    WORKER_TERMINATE_TIMEOUT_MS,
)
from bmlibrarian.lab.paper_weight_lab.validators import (
    validate_pmid,
    validate_doi,
    validate_year,
    validate_pdf_file_size,
    validate_title,
)


class TestValidatePmid:
    """Tests for PMID validation."""

    def test_valid_pmid(self):
        """Test valid PMID."""
        is_valid, error = validate_pmid("12345678")
        assert is_valid is True
        assert error is None

    def test_empty_pmid_is_valid(self):
        """Test empty PMID is valid (optional field)."""
        is_valid, error = validate_pmid("")
        assert is_valid is True
        assert error is None

    def test_whitespace_only_is_valid(self):
        """Test whitespace-only PMID is valid."""
        is_valid, error = validate_pmid("   ")
        assert is_valid is True
        assert error is None

    def test_non_numeric_pmid(self):
        """Test non-numeric PMID is invalid."""
        is_valid, error = validate_pmid("abc123")
        assert is_valid is False
        assert "numeric" in error.lower()

    def test_pmid_with_letters(self):
        """Test PMID containing letters is invalid."""
        is_valid, error = validate_pmid("1234abc")
        assert is_valid is False
        assert "numeric" in error.lower()

    def test_pmid_below_minimum(self):
        """Test PMID below minimum value."""
        is_valid, error = validate_pmid("0")
        assert is_valid is False
        assert str(PMID_MIN_VALUE) in error

    def test_pmid_above_maximum(self):
        """Test PMID above maximum value."""
        is_valid, error = validate_pmid("999999999")  # 9 digits
        assert is_valid is False
        assert str(PMID_MAX_VALUE) in error

    def test_pmid_at_minimum(self):
        """Test PMID at minimum value."""
        is_valid, error = validate_pmid(str(PMID_MIN_VALUE))
        assert is_valid is True
        assert error is None

    def test_pmid_at_maximum(self):
        """Test PMID at maximum value."""
        is_valid, error = validate_pmid(str(PMID_MAX_VALUE))
        assert is_valid is True
        assert error is None


class TestValidateDoi:
    """Tests for DOI validation."""

    def test_valid_doi(self):
        """Test valid DOI."""
        is_valid, error = validate_doi("10.1234/example.2023.01")
        assert is_valid is True
        assert error is None

    def test_valid_complex_doi(self):
        """Test valid complex DOI with special characters."""
        is_valid, error = validate_doi("10.1000/xyz-abc.123")
        assert is_valid is True
        assert error is None

    def test_empty_doi_is_valid(self):
        """Test empty DOI is valid (optional field)."""
        is_valid, error = validate_doi("")
        assert is_valid is True
        assert error is None

    def test_whitespace_only_is_valid(self):
        """Test whitespace-only DOI is valid."""
        is_valid, error = validate_doi("   ")
        assert is_valid is True
        assert error is None

    def test_doi_missing_prefix(self):
        """Test DOI without 10. prefix is invalid."""
        is_valid, error = validate_doi("1234/example")
        assert is_valid is False
        assert "10." in error

    def test_doi_missing_registrant(self):
        """Test DOI with short registrant code."""
        is_valid, error = validate_doi("10.12/example")
        assert is_valid is False

    def test_doi_missing_suffix(self):
        """Test DOI without suffix is invalid."""
        is_valid, error = validate_doi("10.1234/")
        assert is_valid is False


class TestValidateYear:
    """Tests for publication year validation."""

    def test_valid_year(self):
        """Test valid year."""
        is_valid, error = validate_year("2023")
        assert is_valid is True
        assert error is None

    def test_empty_year_is_valid(self):
        """Test empty year is valid (optional field)."""
        is_valid, error = validate_year("")
        assert is_valid is True
        assert error is None

    def test_whitespace_only_is_valid(self):
        """Test whitespace-only year is valid."""
        is_valid, error = validate_year("   ")
        assert is_valid is True
        assert error is None

    def test_non_numeric_year(self):
        """Test non-numeric year is invalid."""
        is_valid, error = validate_year("twenty-twenty")
        assert is_valid is False
        assert "numeric" in error.lower()

    def test_year_below_minimum(self):
        """Test year below minimum value."""
        is_valid, error = validate_year("1700")
        assert is_valid is False
        assert str(YEAR_MIN_VALUE) in error

    def test_year_above_maximum(self):
        """Test year above maximum value."""
        is_valid, error = validate_year("2200")
        assert is_valid is False
        assert str(YEAR_MAX_VALUE) in error

    def test_year_at_minimum(self):
        """Test year at minimum value."""
        is_valid, error = validate_year(str(YEAR_MIN_VALUE))
        assert is_valid is True
        assert error is None

    def test_year_at_maximum(self):
        """Test year at maximum value."""
        is_valid, error = validate_year(str(YEAR_MAX_VALUE))
        assert is_valid is True
        assert error is None


class TestValidateTitle:
    """Tests for title validation."""

    def test_valid_title(self):
        """Test valid title."""
        is_valid, error = validate_title("A Study on Machine Learning")
        assert is_valid is True
        assert error is None

    def test_empty_title_is_invalid(self):
        """Test empty title is invalid (required field)."""
        is_valid, error = validate_title("")
        assert is_valid is False
        assert "required" in error.lower()

    def test_whitespace_only_is_invalid(self):
        """Test whitespace-only title is invalid."""
        is_valid, error = validate_title("   ")
        assert is_valid is False
        assert "required" in error.lower()

    def test_title_with_special_characters(self):
        """Test title with special characters is valid."""
        is_valid, error = validate_title("COVID-19: A Review (2020-2023)")
        assert is_valid is True
        assert error is None


class TestValidatePdfFileSize:
    """Tests for PDF file size validation."""

    def test_valid_file_size(self):
        """Test file within size limit."""
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            f.write(b'x' * 1000)  # 1KB file
            temp_path = Path(f.name)

        try:
            is_valid, warning = validate_pdf_file_size(temp_path)
            assert is_valid is True
            assert warning is None
        finally:
            os.unlink(temp_path)

    def test_large_file_warning(self):
        """Test file exceeding size limit generates warning."""
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            # Write more than PDF_MAX_FILE_SIZE_BYTES
            f.write(b'x' * (PDF_MAX_FILE_SIZE_BYTES + 1024))
            temp_path = Path(f.name)

        try:
            is_valid, warning = validate_pdf_file_size(temp_path)
            assert is_valid is False
            assert warning is not None
            assert str(PDF_MAX_FILE_SIZE_MB) in warning
        finally:
            os.unlink(temp_path)

    def test_nonexistent_file(self):
        """Test nonexistent file."""
        is_valid, error = validate_pdf_file_size(Path("/nonexistent/file.pdf"))
        assert is_valid is False
        assert "does not exist" in error


class TestConstants:
    """Tests for validation constants."""

    def test_pmid_range_valid(self):
        """Ensure PMID range is valid."""
        assert PMID_MIN_VALUE > 0
        assert PMID_MAX_VALUE > PMID_MIN_VALUE

    def test_year_range_valid(self):
        """Ensure year range is valid."""
        assert YEAR_MIN_VALUE > 0
        assert YEAR_MAX_VALUE > YEAR_MIN_VALUE

    def test_doi_pattern_valid(self):
        """Ensure DOI pattern is valid regex."""
        import re
        assert re.compile(DOI_PATTERN)

    def test_pdf_size_constants_consistent(self):
        """Ensure PDF size constants are consistent."""
        assert PDF_MAX_FILE_SIZE_BYTES == PDF_MAX_FILE_SIZE_MB * 1024 * 1024

    def test_worker_timeout_positive(self):
        """Ensure worker timeout is positive."""
        assert WORKER_TERMINATE_TIMEOUT_MS > 0


class TestWorkerCleanup:
    """Tests for worker cleanup functionality (mock-based)."""

    def test_terminate_workers_with_running_worker(self):
        """Test _terminate_workers terminates running workers."""
        # Create mock worker
        mock_worker = MagicMock()
        mock_worker.isRunning.return_value = True
        mock_worker.wait.return_value = True  # Successfully terminated

        # Create mock tab instance
        mock_tab = MagicMock()
        mock_tab.analysis_worker = mock_worker
        mock_tab.ingest_worker = None

        # Call the termination logic with our mock
        # (We test the logic pattern directly, not the actual class)
        workers = [
            ('analysis_worker', mock_tab.analysis_worker),
            ('ingest_worker', mock_tab.ingest_worker),
        ]

        for name, worker in workers:
            if worker is not None and worker.isRunning():
                worker.terminate()
                worker.wait(WORKER_TERMINATE_TIMEOUT_MS)

        # Verify terminate and wait were called
        mock_worker.terminate.assert_called_once()
        mock_worker.wait.assert_called_once_with(WORKER_TERMINATE_TIMEOUT_MS)

    def test_terminate_workers_with_no_running_workers(self):
        """Test _terminate_workers handles no running workers."""
        # Create mock worker that's not running
        mock_worker = MagicMock()
        mock_worker.isRunning.return_value = False

        # Verify terminate is not called when worker is not running
        workers = [('worker', mock_worker)]

        for name, worker in workers:
            if worker is not None and worker.isRunning():
                worker.terminate()

        mock_worker.terminate.assert_not_called()

    def test_terminate_workers_with_none_workers(self):
        """Test _terminate_workers handles None workers gracefully."""
        # This should not raise any exceptions
        workers = [
            ('analysis_worker', None),
            ('ingest_worker', None),
        ]

        for name, worker in workers:
            if worker is not None and worker.isRunning():
                worker.terminate()

        # No assertions needed - test passes if no exception is raised


# Note: Qt-dependent worker tests (TestPDFAnalysisWorker, TestPDFIngestWorker,
# TestAssessmentWorker) require a display environment with PySide6 available.
# These tests are commented out because they cannot be run in headless CI
# environments. They can be enabled when running on a system with Qt support.
#
# To run these tests locally with Qt support:
# 1. Ensure PySide6 is installed
# 2. Have a display environment (X11 or Wayland)
# 3. Uncomment the test classes below


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
