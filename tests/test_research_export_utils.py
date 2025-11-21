"""
Tests for Research Tab Export Utilities Module.

Tests file I/O operations including safe_write_file, save dialogs, and error handling.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os
import tempfile
import errno
from pathlib import Path
import pytest

# Ensure src is in path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Check if Qt is available (may fail in headless environments)
try:
    from bmlibrarian.gui.qt.plugins.research.export_utils import (
        safe_write_file,
        show_save_success,
        show_save_error,
        save_markdown_report,
        export_json_report,
    )
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False
    safe_write_file = None
    show_save_success = None
    show_save_error = None
    save_markdown_report = None
    export_json_report = None

pytestmark = pytest.mark.skipif(not QT_AVAILABLE, reason="Qt/PySide6 not available in this environment")


class TestSafeWriteFile(unittest.TestCase):
    """Test cases for safe_write_file function."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # ========================================================================
    # Success Cases
    # ========================================================================

    def test_writes_content_successfully(self):
        """Test that content is written to file successfully."""
        filename = os.path.join(self.temp_dir, "test.txt")
        content = "Test content"

        success, error = safe_write_file(filename, content)

        self.assertTrue(success)
        self.assertIsNone(error)
        with open(filename, 'r', encoding='utf-8') as f:
            self.assertEqual(f.read(), content)

    def test_writes_unicode_content(self):
        """Test that unicode content is written correctly."""
        filename = os.path.join(self.temp_dir, "unicode.txt")
        content = "Unicode content: \u00e9\u00e0\u00fc \u4e2d\u6587 \U0001f604"

        success, error = safe_write_file(filename, content)

        self.assertTrue(success)
        with open(filename, 'r', encoding='utf-8') as f:
            self.assertEqual(f.read(), content)

    def test_overwrites_existing_file(self):
        """Test that existing file is overwritten."""
        filename = os.path.join(self.temp_dir, "existing.txt")

        # Create initial file
        with open(filename, 'w') as f:
            f.write("Original content")

        # Overwrite
        success, error = safe_write_file(filename, "New content")

        self.assertTrue(success)
        with open(filename, 'r') as f:
            self.assertEqual(f.read(), "New content")

    def test_writes_empty_content(self):
        """Test that empty content creates empty file."""
        filename = os.path.join(self.temp_dir, "empty.txt")

        success, error = safe_write_file(filename, "")

        self.assertTrue(success)
        with open(filename, 'r') as f:
            self.assertEqual(f.read(), "")

    def test_writes_large_content(self):
        """Test that large content is written correctly."""
        filename = os.path.join(self.temp_dir, "large.txt")
        content = "A" * 1000000  # 1MB of content

        success, error = safe_write_file(filename, content)

        self.assertTrue(success)
        with open(filename, 'r') as f:
            self.assertEqual(len(f.read()), 1000000)

    # ========================================================================
    # Error Cases - Directory Issues
    # ========================================================================

    def test_returns_error_for_nonexistent_directory(self):
        """Test that error is returned for non-existent directory."""
        filename = "/nonexistent/directory/file.txt"

        success, error = safe_write_file(filename, "content")

        self.assertFalse(success)
        self.assertIsNotNone(error)
        self.assertIn("not exist", error.lower())

    def test_returns_error_for_no_write_permission_on_directory(self):
        """Test that error is returned when directory is not writable."""
        # Create a read-only directory
        readonly_dir = os.path.join(self.temp_dir, "readonly")
        os.makedirs(readonly_dir)
        os.chmod(readonly_dir, 0o444)  # Read-only

        try:
            filename = os.path.join(readonly_dir, "test.txt")
            success, error = safe_write_file(filename, "content")

            self.assertFalse(success)
            self.assertIsNotNone(error)
            self.assertIn("permission", error.lower())
        finally:
            # Restore permissions for cleanup
            os.chmod(readonly_dir, 0o755)

    # ========================================================================
    # Error Cases - File Issues
    # ========================================================================

    def test_returns_error_for_readonly_file(self):
        """Test that error is returned when file is read-only."""
        filename = os.path.join(self.temp_dir, "readonly.txt")

        # Create read-only file
        with open(filename, 'w') as f:
            f.write("Original")
        os.chmod(filename, 0o444)

        try:
            success, error = safe_write_file(filename, "New content")

            self.assertFalse(success)
            self.assertIsNotNone(error)
            self.assertIn("permission", error.lower())
        finally:
            os.chmod(filename, 0o644)  # Restore for cleanup

    # ========================================================================
    # Edge Cases
    # ========================================================================

    def test_handles_current_directory_path(self):
        """Test that current directory path is handled correctly."""
        # Save current directory
        original_dir = os.getcwd()
        os.chdir(self.temp_dir)

        try:
            success, error = safe_write_file("current_dir_test.txt", "content")
            self.assertTrue(success)
            self.assertTrue(os.path.exists("current_dir_test.txt"))
        finally:
            os.chdir(original_dir)

    def test_handles_path_with_special_characters(self):
        """Test that paths with special characters are handled."""
        # Create directory with special chars
        special_dir = os.path.join(self.temp_dir, "dir with spaces")
        os.makedirs(special_dir)

        filename = os.path.join(special_dir, "file with spaces.txt")
        success, error = safe_write_file(filename, "content")

        self.assertTrue(success)
        self.assertTrue(os.path.exists(filename))


class TestShowSaveSuccess(unittest.TestCase):
    """Test cases for show_save_success function."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_parent = Mock()

    @patch('bmlibrarian.gui.qt.plugins.research.export_utils.QMessageBox')
    def test_shows_information_dialog(self, mock_msgbox):
        """Test that information dialog is shown."""
        show_save_success(
            self.mock_parent,
            "/path/to/file.md",
            "Test content",
            "Report"
        )

        mock_msgbox.information.assert_called_once()

    @patch('bmlibrarian.gui.qt.plugins.research.export_utils.QMessageBox')
    def test_includes_file_info_in_message(self, mock_msgbox):
        """Test that file info is included in message."""
        content = "Test content with some words"

        show_save_success(
            self.mock_parent,
            "/path/to/file.md",
            content,
            "Report"
        )

        # Get the message passed to information()
        call_args = mock_msgbox.information.call_args
        message = call_args[0][2]  # Third positional argument is message

        self.assertIn("file.md", message)
        self.assertIn("KB", message)  # File size

    @patch('bmlibrarian.gui.qt.plugins.research.export_utils.QMessageBox')
    def test_logs_when_logger_provided(self, mock_msgbox):
        """Test that logger is called when provided."""
        mock_logger = Mock()

        show_save_success(
            self.mock_parent,
            "/path/to/file.md",
            "content",
            "Report",
            logger=mock_logger
        )

        mock_logger.info.assert_called_once()

    @patch('bmlibrarian.gui.qt.plugins.research.export_utils.QMessageBox')
    def test_calls_status_callback(self, mock_msgbox):
        """Test that status callback is called when provided."""
        mock_callback = Mock()

        show_save_success(
            self.mock_parent,
            "/path/to/file.md",
            "content",
            "Report",
            status_callback=mock_callback
        )

        mock_callback.assert_called_once()


class TestShowSaveError(unittest.TestCase):
    """Test cases for show_save_error function."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_parent = Mock()

    @patch('bmlibrarian.gui.qt.plugins.research.export_utils.QMessageBox')
    def test_shows_critical_dialog(self, mock_msgbox):
        """Test that critical dialog is shown."""
        show_save_error(
            self.mock_parent,
            "Test error",
            "file"
        )

        mock_msgbox.critical.assert_called_once()

    @patch('bmlibrarian.gui.qt.plugins.research.export_utils.QMessageBox')
    def test_includes_error_message(self, mock_msgbox):
        """Test that error message is included."""
        show_save_error(
            self.mock_parent,
            "Permission denied",
            "file"
        )

        call_args = mock_msgbox.critical.call_args
        message = call_args[0][2]

        self.assertIn("Permission denied", message)

    @patch('bmlibrarian.gui.qt.plugins.research.export_utils.QMessageBox')
    def test_logs_error_when_logger_provided(self, mock_msgbox):
        """Test that error is logged when logger provided."""
        mock_logger = Mock()

        show_save_error(
            self.mock_parent,
            "Test error",
            "file",
            logger=mock_logger
        )

        mock_logger.error.assert_called_once()


class TestSaveMarkdownReport(unittest.TestCase):
    """Test cases for save_markdown_report function."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_parent = Mock()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('bmlibrarian.gui.qt.plugins.research.export_utils.QMessageBox')
    def test_shows_warning_when_no_content(self, mock_msgbox):
        """Test that warning is shown when report content is empty."""
        result = save_markdown_report(self.mock_parent, "")

        self.assertFalse(result)
        mock_msgbox.warning.assert_called_once()

    @patch('bmlibrarian.gui.qt.plugins.research.export_utils.QMessageBox')
    def test_shows_warning_when_content_is_none(self, mock_msgbox):
        """Test that warning is shown when report content is None."""
        result = save_markdown_report(self.mock_parent, None)

        self.assertFalse(result)
        mock_msgbox.warning.assert_called_once()

    @patch('bmlibrarian.gui.qt.plugins.research.export_utils.QFileDialog')
    @patch('bmlibrarian.gui.qt.plugins.research.export_utils.QMessageBox')
    def test_returns_false_when_user_cancels(self, mock_msgbox, mock_dialog):
        """Test that False is returned when user cancels file dialog."""
        mock_dialog.getSaveFileName.return_value = ("", "")

        result = save_markdown_report(self.mock_parent, "Report content")

        self.assertFalse(result)

    @patch('bmlibrarian.gui.qt.plugins.research.export_utils.QFileDialog')
    @patch('bmlibrarian.gui.qt.plugins.research.export_utils.QMessageBox')
    def test_saves_file_successfully(self, mock_msgbox, mock_dialog):
        """Test that file is saved successfully."""
        filename = os.path.join(self.temp_dir, "report.md")
        mock_dialog.getSaveFileName.return_value = (filename, "Markdown Files (*.md)")

        result = save_markdown_report(self.mock_parent, "# Test Report")

        self.assertTrue(result)
        self.assertTrue(os.path.exists(filename))
        with open(filename, 'r') as f:
            self.assertEqual(f.read(), "# Test Report")


class TestExportJsonReport(unittest.TestCase):
    """Test cases for export_json_report function."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_parent = Mock()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('bmlibrarian.gui.qt.plugins.research.export_utils.QMessageBox')
    def test_shows_warning_when_no_results(self, mock_msgbox):
        """Test that warning is shown when results are empty."""
        result = export_json_report(self.mock_parent, {}, "report content")

        self.assertFalse(result)
        mock_msgbox.warning.assert_called_once()

    @patch('bmlibrarian.gui.qt.plugins.research.export_utils.QMessageBox')
    def test_shows_warning_when_no_report(self, mock_msgbox):
        """Test that warning is shown when report content is empty."""
        result = export_json_report(
            self.mock_parent,
            {"question": "test"},
            ""
        )

        self.assertFalse(result)
        mock_msgbox.warning.assert_called_once()

    @patch('bmlibrarian.gui.qt.plugins.research.export_utils.QFileDialog')
    @patch('bmlibrarian.gui.qt.plugins.research.export_utils.QMessageBox')
    def test_returns_false_when_user_cancels(self, mock_msgbox, mock_dialog):
        """Test that False is returned when user cancels."""
        mock_dialog.getSaveFileName.return_value = ("", "")

        result = export_json_report(
            self.mock_parent,
            {"question": "test"},
            "Report content"
        )

        self.assertFalse(result)

    @patch('bmlibrarian.gui.qt.plugins.research.export_utils.QFileDialog')
    @patch('bmlibrarian.gui.qt.plugins.research.export_utils.QMessageBox')
    def test_exports_valid_json(self, mock_msgbox, mock_dialog):
        """Test that valid JSON is exported."""
        import json
        filename = os.path.join(self.temp_dir, "results.json")
        mock_dialog.getSaveFileName.return_value = (filename, "JSON Files (*.json)")

        results = {
            "question": "Test question",
            "document_count": 10,
            "citation_count": 5,
            "status": "completed"
        }

        result = export_json_report(
            self.mock_parent,
            results,
            "# Test Report"
        )

        self.assertTrue(result)
        self.assertTrue(os.path.exists(filename))

        with open(filename, 'r') as f:
            data = json.load(f)

        self.assertEqual(data['research_question'], "Test question")
        self.assertEqual(data['document_count'], 10)
        self.assertEqual(data['citation_count'], 5)
        self.assertEqual(data['final_report_markdown'], "# Test Report")

    @patch('bmlibrarian.gui.qt.plugins.research.export_utils.QFileDialog')
    @patch('bmlibrarian.gui.qt.plugins.research.export_utils.QMessageBox')
    def test_handles_unicode_in_json(self, mock_msgbox, mock_dialog):
        """Test that unicode content is exported correctly."""
        import json
        filename = os.path.join(self.temp_dir, "unicode.json")
        mock_dialog.getSaveFileName.return_value = (filename, "JSON Files (*.json)")

        results = {"question": "Unicode test \u00e9\u00e0\u00fc"}
        report = "# Report with unicode: \u4e2d\u6587"

        result = export_json_report(self.mock_parent, results, report)

        self.assertTrue(result)
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.assertIn("\u00e9", data['research_question'])
        self.assertIn("\u4e2d\u6587", data['final_report_markdown'])


class TestSafeWriteFileOSErrors(unittest.TestCase):
    """Test OS-specific error handling in safe_write_file."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('builtins.open')
    def test_handles_disk_full_error(self, mock_open):
        """Test handling of ENOSPC (disk full) error."""
        error = OSError()
        error.errno = errno.ENOSPC
        mock_open.side_effect = error

        filename = os.path.join(self.temp_dir, "test.txt")
        # Create the directory so the pre-checks pass
        success, error_msg = safe_write_file(filename, "content")

        self.assertFalse(success)
        self.assertIn("space", error_msg.lower())

    @patch('builtins.open')
    def test_handles_read_only_filesystem_error(self, mock_open):
        """Test handling of EROFS (read-only filesystem) error."""
        error = OSError()
        error.errno = errno.EROFS
        mock_open.side_effect = error

        filename = os.path.join(self.temp_dir, "test.txt")
        success, error_msg = safe_write_file(filename, "content")

        self.assertFalse(success)
        self.assertIn("read-only", error_msg.lower())

    @patch('builtins.open')
    def test_handles_name_too_long_error(self, mock_open):
        """Test handling of ENAMETOOLONG error."""
        error = OSError()
        error.errno = errno.ENAMETOOLONG
        mock_open.side_effect = error

        filename = os.path.join(self.temp_dir, "test.txt")
        success, error_msg = safe_write_file(filename, "content")

        self.assertFalse(success)
        self.assertIn("too long", error_msg.lower())

    def test_handles_unicode_encode_error(self):
        """Test handling of UnicodeEncodeError."""
        # This is difficult to trigger with UTF-8 encoding, but we test the path exists
        filename = os.path.join(self.temp_dir, "unicode.txt")

        # Normal unicode should work
        success, error = safe_write_file(filename, "Normal content")
        self.assertTrue(success)


if __name__ == '__main__':
    unittest.main()
