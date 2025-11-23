"""
Unit tests for PDF Upload Widget.

Tests the main PDFUploadWidget class including:
- UI initialization
- PDF loading and validation
- Signal emissions
- Worker management
"""

import pytest
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import Mock, patch, MagicMock

# Skip tests if PySide6 is not available
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt

from bmlibrarian.gui.qt.widgets.pdf_upload_widget import PDFUploadWidget
from bmlibrarian.gui.qt.widgets.validators import ValidationStatus


@pytest.fixture(scope="module")
def qapp():
    """Create QApplication for tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def widget(qapp):
    """Create a PDFUploadWidget instance."""
    widget = PDFUploadWidget()
    yield widget
    widget.close()


class TestPDFUploadWidgetInit:
    """Tests for widget initialization."""

    def test_widget_creation(self, qapp):
        """Test widget can be created."""
        widget = PDFUploadWidget()
        assert widget is not None
        widget.close()

    def test_initial_state(self, widget):
        """Test initial state of widget."""
        assert widget._pdf_path is None
        assert widget._extracted_text is None
        assert widget._current_metadata is None
        assert widget._selected_document is None

    def test_ui_elements_exist(self, widget):
        """Test required UI elements exist."""
        assert widget.pdf_viewer is not None
        assert widget.file_path_edit is not None
        assert widget.browse_btn is not None
        assert widget.status_label is not None
        assert widget.title_edit is not None
        assert widget.authors_edit is not None
        assert widget.doi_edit is not None
        assert widget.pmid_edit is not None
        assert widget.matches_tree is not None

    def test_buttons_exist(self, widget):
        """Test action buttons exist."""
        assert widget.use_match_btn is not None
        assert widget.create_new_btn is not None
        assert widget.cancel_btn is not None

    def test_signals_defined(self, widget):
        """Test signals are defined."""
        assert hasattr(widget, 'document_selected')
        assert hasattr(widget, 'document_created')
        assert hasattr(widget, 'pdf_loaded')
        assert hasattr(widget, 'cancelled')


class TestPDFUploadWidgetLoadPdf:
    """Tests for PDF loading functionality."""

    def test_load_nonexistent_pdf(self, widget, qapp):
        """Test loading non-existent PDF shows error."""
        with patch.object(QMessageBox, 'critical') as mock_critical:
            widget.load_pdf("/nonexistent/file.pdf")
            mock_critical.assert_called_once()
            assert "not found" in str(mock_critical.call_args).lower()

    def test_load_invalid_file_type(self, widget, qapp):
        """Test loading non-PDF file shows error."""
        with NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"test content")
            temp_path = Path(f.name)

        try:
            with patch.object(QMessageBox, 'critical') as mock_critical:
                widget.load_pdf(temp_path)
                mock_critical.assert_called_once()
        finally:
            temp_path.unlink()

    def test_load_valid_pdf_updates_ui(self, widget, qapp):
        """Test loading valid PDF updates UI."""
        with NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4 test content")
            temp_path = Path(f.name)

        try:
            # Mock the pdf viewer to avoid actual PDF loading
            widget.pdf_viewer = MagicMock()
            # Mock the quick extraction to avoid thread issues
            widget._start_quick_extraction = MagicMock()

            widget.load_pdf(temp_path)

            assert widget._pdf_path == temp_path
            assert widget.file_path_edit.text() == str(temp_path)
            widget._start_quick_extraction.assert_called_once()
        finally:
            temp_path.unlink()

    def test_load_large_pdf_shows_warning(self, widget, qapp):
        """Test loading large PDF shows warning dialog."""
        from bmlibrarian.gui.qt.widgets.validators import PDF_MAX_FILE_SIZE_MB

        with NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            # Write more than limit
            f.write(b"%PDF-1.4" + b"x" * (PDF_MAX_FILE_SIZE_MB * 1024 * 1024 + 1000))
            temp_path = Path(f.name)

        try:
            with patch.object(QMessageBox, 'warning', return_value=QMessageBox.No):
                widget.load_pdf(temp_path)
                # Should not proceed when user clicks No
                assert widget._pdf_path is None or widget.file_path_edit.text() == ""
        finally:
            temp_path.unlink()


class TestPDFUploadWidgetWorkerManagement:
    """Tests for worker thread management."""

    def test_cleanup_workers_clears_references(self, widget):
        """Test cleanup_workers clears worker references."""
        # Create mock workers
        widget._quick_worker = MagicMock()
        widget._quick_worker.isRunning.return_value = False
        widget._llm_worker = MagicMock()
        widget._llm_worker.isRunning.return_value = False

        widget._cleanup_workers()

        assert widget._quick_worker is None
        assert widget._llm_worker is None

    def test_cleanup_workers_terminates_running_workers(self, widget):
        """Test cleanup terminates running workers."""
        # Create mock running worker
        mock_worker = MagicMock()
        mock_worker.isRunning.return_value = True
        mock_worker.wait.return_value = True  # Graceful termination succeeds
        widget._quick_worker = mock_worker

        widget._cleanup_workers()

        mock_worker.requestInterruption.assert_called_once()
        mock_worker.wait.assert_called()

    def test_cleanup_workers_force_terminates_stuck_workers(self, widget):
        """Test cleanup force terminates stuck workers."""
        # Create mock stuck worker
        mock_worker = MagicMock()
        mock_worker.isRunning.return_value = True
        mock_worker.wait.side_effect = [False, True]  # First wait fails, second succeeds
        widget._quick_worker = mock_worker

        widget._cleanup_workers()

        mock_worker.requestInterruption.assert_called_once()
        mock_worker.terminate.assert_called_once()


class TestPDFUploadWidgetSignals:
    """Tests for signal handling."""

    def test_cancel_emits_cancelled_signal(self, widget, qapp):
        """Test cancel button emits cancelled signal."""
        signal_received = []
        widget.cancelled.connect(lambda: signal_received.append(True))

        widget._on_cancel()

        assert len(signal_received) == 1

    def test_use_match_emits_document_selected(self, widget, qapp):
        """Test selecting match emits document_selected signal."""
        widget._selected_document = {"id": 123, "title": "Test"}

        signal_received = []
        widget.document_selected.connect(lambda doc_id: signal_received.append(doc_id))

        widget._on_use_match()

        assert len(signal_received) == 1
        assert signal_received[0] == 123

    def test_accept_quick_match_emits_document_selected(self, widget, qapp):
        """Test accepting quick match emits document_selected signal."""
        widget._selected_document = {"id": 456, "title": "Quick Match"}

        signal_received = []
        widget.document_selected.connect(lambda doc_id: signal_received.append(doc_id))

        widget._on_accept_quick_match()

        assert len(signal_received) == 1
        assert signal_received[0] == 456


class TestPDFUploadWidgetHelperMethods:
    """Tests for helper methods."""

    def test_should_ingest_returns_checkbox_state(self, widget):
        """Test should_ingest returns checkbox state."""
        widget.ingest_checkbox.setChecked(True)
        assert widget.should_ingest() is True

        widget.ingest_checkbox.setChecked(False)
        assert widget.should_ingest() is False

    def test_get_pdf_path_returns_path(self, widget):
        """Test get_pdf_path returns current PDF path."""
        assert widget.get_pdf_path() is None

        widget._pdf_path = Path("/test/file.pdf")
        assert widget.get_pdf_path() == Path("/test/file.pdf")

    def test_get_selected_document_returns_document(self, widget):
        """Test get_selected_document returns selected document."""
        assert widget.get_selected_document() is None

        widget._selected_document = {"id": 1, "title": "Test"}
        assert widget.get_selected_document() == {"id": 1, "title": "Test"}

    def test_get_extracted_metadata_returns_metadata(self, widget):
        """Test get_extracted_metadata returns metadata."""
        assert widget.get_extracted_metadata() is None

        widget._current_metadata = {"title": "Test", "doi": "10.1234/test"}
        assert widget.get_extracted_metadata() == {"title": "Test", "doi": "10.1234/test"}

    def test_update_status_updates_label(self, widget):
        """Test _update_status updates status label."""
        widget._update_status("Processing...")
        assert widget.status_label.text() == "Processing..."

    def test_clear_results_resets_state(self, widget):
        """Test _clear_results resets all state."""
        # Set some state
        widget._extracted_text = "Some text"
        widget._current_metadata = {"title": "Test"}
        widget._selected_document = {"id": 1}
        widget.title_edit.setText("Test Title")
        widget.use_match_btn.setEnabled(True)

        widget._clear_results()

        assert widget._extracted_text is None
        assert widget._current_metadata is None
        assert widget._selected_document is None
        assert widget.title_edit.text() == ""
        assert widget.use_match_btn.isEnabled() is False


class TestPDFUploadWidgetDocumentCreation:
    """Tests for document creation functionality."""

    @patch('bmlibrarian.gui.qt.widgets.pdf_upload_widget.DocumentCreateDialog')
    def test_create_new_opens_dialog(self, MockDialog, widget, qapp):
        """Test _on_create_new opens document creation dialog."""
        mock_dialog_instance = MagicMock()
        MockDialog.return_value = mock_dialog_instance
        mock_dialog_instance.exec.return_value = False  # User cancels

        widget._on_create_new()

        MockDialog.assert_called_once()

    @patch('bmlibrarian.gui.qt.widgets.pdf_upload_widget.DocumentCreateDialog')
    def test_create_new_passes_metadata(self, MockDialog, widget, qapp):
        """Test _on_create_new passes extracted metadata to dialog."""
        widget._current_metadata = {"title": "Extracted Title"}
        widget.doi_edit.setText("10.1234/test")
        widget.pmid_edit.setText("12345")

        mock_dialog_instance = MagicMock()
        MockDialog.return_value = mock_dialog_instance
        mock_dialog_instance.exec.return_value = False

        widget._on_create_new()

        # Check metadata was passed
        call_kwargs = MockDialog.call_args[1]
        assert call_kwargs['metadata']['title'] == "Extracted Title"
        assert call_kwargs['metadata']['doi'] == "10.1234/test"
        assert call_kwargs['metadata']['pmid'] == "12345"

    @patch('bmlibrarian.gui.qt.widgets.pdf_upload_widget.DocumentCreateDialog')
    def test_create_new_emits_signal_on_success(self, MockDialog, widget, qapp):
        """Test _on_create_new emits document_created on success."""
        from PySide6.QtWidgets import QDialog

        mock_dialog_instance = MagicMock()
        MockDialog.return_value = mock_dialog_instance
        mock_dialog_instance.exec.return_value = QDialog.Accepted
        mock_dialog_instance.get_document_id.return_value = 789

        signal_received = []
        widget.document_created.connect(lambda doc_id: signal_received.append(doc_id))

        widget._on_create_new()

        assert len(signal_received) == 1
        assert signal_received[0] == 789


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
