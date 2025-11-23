"""
PaperChecker Laboratory - PDF Upload Tab

Tab widget for uploading PDFs and matching/creating documents.
Wraps the reusable PDFUploadWidget with paper checker lab specific behavior.

This follows the same pattern as paper_weight_lab's PDF upload tab.
"""

import logging
from pathlib import Path
from typing import Optional, Any

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QGroupBox,
    QCheckBox,
    QHBoxLayout,
    QMessageBox,
)
from PySide6.QtCore import Signal, QThread
from PySide6.QtGui import QCloseEvent

from bmlibrarian.gui.qt.resources.styles.dpi_scale import get_font_scale
from bmlibrarian.gui.qt.resources.styles.stylesheet_generator import get_stylesheet_generator
from bmlibrarian.gui.qt.widgets import PDFUploadWidget

from ..constants import WORKER_TERMINATE_TIMEOUT_MS
from ..widgets import StatusSpinnerWidget


logger = logging.getLogger(__name__)


class PDFIngestWorker(QThread):
    """
    Worker thread for PDF ingestion.

    Performs PDF storage, text extraction, and embedding in background.
    This enables semantic search over the full document text, which is used
    during fact-checking to find evidence and clarification for statements
    extracted from the abstract.
    """

    ingest_complete = Signal(object)  # IngestResult
    ingest_error = Signal(str)
    status_update = Signal(str)

    def __init__(
        self,
        document_id: int,
        pdf_path: Path,
        parent: Optional[object] = None
    ):
        """
        Initialize worker.

        Args:
            document_id: Database document ID
            pdf_path: Path to PDF file
            parent: Parent object
        """
        super().__init__(parent)
        self.document_id = document_id
        self.pdf_path = pdf_path

    def run(self) -> None:
        """Run PDF ingestion in background."""
        try:
            from bmlibrarian.importers.pdf_ingestor import PDFIngestor

            self.status_update.emit("Initializing PDF ingestor...")

            ingestor = PDFIngestor()

            def progress_callback(stage: str, current: int, total: int) -> None:
                """Handle progress updates."""
                if total > 0:
                    self.status_update.emit(f"{stage}: {current}/{total}")
                else:
                    self.status_update.emit(stage)

            self.status_update.emit("Ingesting PDF...")

            result = ingestor.ingest_pdf_immediate(
                document_id=self.document_id,
                pdf_path=self.pdf_path,
                progress_callback=progress_callback,
            )

            self.ingest_complete.emit(result)

        except Exception as e:
            logger.exception(f"PDF ingestion error: {e}")
            self.ingest_error.emit(str(e))


class PDFUploadTab(QWidget):
    """
    Tab widget for PDF upload and document matching.

    Wraps the reusable PDFUploadWidget and adds paper checker lab specific
    functionality including PDF ingestion (text extraction and embedding)
    to enable semantic search over the full document.

    Signals:
        document_selected: Emitted when a document is selected/created.
            Args: document_id (int)
    """

    document_selected = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize PDF upload tab.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        self.scale = get_font_scale()
        self.styles = get_stylesheet_generator()

        self._ingest_worker: Optional[PDFIngestWorker] = None
        self._pending_document_id: Optional[int] = None

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Setup tab user interface."""
        layout = QVBoxLayout(self)
        layout.setSpacing(self.scale['spacing_medium'])
        layout.setContentsMargins(
            self.scale['padding_medium'],
            self.scale['padding_medium'],
            self.scale['padding_medium'],
            self.scale['padding_medium']
        )

        # PDF Upload Widget (main component)
        self._upload_widget = PDFUploadWidget()
        layout.addWidget(self._upload_widget, stretch=1)

        # Ingestion status section
        status_group = QGroupBox("Ingestion Status")
        status_layout = QVBoxLayout()

        self._ingest_spinner = StatusSpinnerWidget()
        status_layout.addWidget(self._ingest_spinner)

        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        # Additional options section
        options_group = QGroupBox("Options")
        options_layout = QHBoxLayout()

        self._ingest_on_select = QCheckBox("Ingest PDF on selection")
        self._ingest_on_select.setChecked(True)
        self._ingest_on_select.setToolTip(
            "When checked, automatically ingest PDF (extract text and create embeddings)\n"
            "when selecting or creating a document. This enables semantic search over the\n"
            "full document text to find evidence and clarification during fact-checking."
        )
        options_layout.addWidget(self._ingest_on_select)
        options_layout.addStretch()

        options_group.setLayout(options_layout)
        layout.addWidget(options_group)

    def _connect_signals(self) -> None:
        """Connect widget signals."""
        # Connect PDFUploadWidget signals
        self._upload_widget.document_selected.connect(self._on_document_selected)
        self._upload_widget.document_created.connect(self._on_document_created)

    def _on_document_selected(self, document_id: int) -> None:
        """
        Handle document selection from PDFUploadWidget.

        Args:
            document_id: Selected document ID
        """
        logger.info(f"Document selected: {document_id}")

        if self._should_ingest():
            self._start_ingestion(document_id)
        else:
            self.document_selected.emit(document_id)

    def _on_document_created(self, document_id: int) -> None:
        """
        Handle document creation from PDFUploadWidget.

        Args:
            document_id: Created document ID
        """
        logger.info(f"Document created: {document_id}")

        if self._should_ingest():
            self._start_ingestion(document_id)
        else:
            self.document_selected.emit(document_id)

    def _should_ingest(self) -> bool:
        """
        Check if PDF should be ingested.

        Returns:
            True if ingestion should occur
        """
        # Check if checkbox is checked
        if not self._ingest_on_select.isChecked():
            return False

        # Check if widget has ingestion requested
        if not self._upload_widget.should_ingest():
            return False

        # Check if we have a PDF
        pdf_path = self._upload_widget.get_pdf_path()
        return pdf_path is not None

    def _start_ingestion(self, document_id: int) -> None:
        """
        Start PDF ingestion for a document.

        Args:
            document_id: Document ID to ingest PDF for
        """
        pdf_path = self._upload_widget.get_pdf_path()
        if not pdf_path:
            # No PDF to ingest, just emit the signal
            self.document_selected.emit(document_id)
            return

        # Store pending document ID
        self._pending_document_id = document_id

        # Start ingestion spinner
        self._ingest_spinner.start_spinner()
        self._ingest_spinner.set_status("Preparing ingestion...")

        # Create and start worker
        self._ingest_worker = PDFIngestWorker(document_id, pdf_path, self)
        self._ingest_worker.status_update.connect(self._on_ingest_status)
        self._ingest_worker.ingest_complete.connect(self._on_ingest_complete)
        self._ingest_worker.ingest_error.connect(self._on_ingest_error)
        self._ingest_worker.start()

    def _on_ingest_status(self, status: str) -> None:
        """
        Handle ingestion status update.

        Args:
            status: Status message
        """
        self._ingest_spinner.set_status(status)

    def _on_ingest_complete(self, result: Any) -> None:
        """
        Handle completed PDF ingestion.

        Args:
            result: IngestResult from PDFIngestor
        """
        document_id = self._pending_document_id

        if result.success:
            self._ingest_spinner.set_complete(
                f"Ingestion complete: {result.chunks_created} chunks, "
                f"{result.char_count:,} chars"
            )

            QMessageBox.information(
                self,
                "PDF Ingested",
                f"PDF successfully ingested:\n"
                f"- Text extracted: {result.char_count:,} characters\n"
                f"- Pages: {result.page_count}\n"
                f"- Chunks created: {result.chunks_created}\n\n"
                "Semantic search over full text is now available for finding\n"
                "evidence during fact-checking."
            )
        else:
            self._ingest_spinner.set_error("Ingestion completed with warnings")

            # Show warning but still proceed
            QMessageBox.warning(
                self,
                "Ingestion Warning",
                f"PDF ingestion completed with issues:\n{result.error_message}\n\n"
                "The document was still associated, but full-text semantic search "
                "may not be available."
            )

        # Emit document selected signal
        if document_id is not None:
            self.document_selected.emit(document_id)

    def _on_ingest_error(self, error: str) -> None:
        """
        Handle ingestion error.

        Args:
            error: Error message
        """
        document_id = self._pending_document_id

        self._ingest_spinner.set_error("Ingestion failed")

        # Show error but offer to continue
        reply = QMessageBox.question(
            self,
            "Ingestion Error",
            f"Failed to ingest PDF:\n{error}\n\n"
            "Do you want to continue without PDF ingestion?\n"
            "(Note: Semantic search over full text will not be available)",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )

        if reply == QMessageBox.Yes and document_id is not None:
            self.document_selected.emit(document_id)

    def set_enabled(self, enabled: bool) -> None:
        """
        Enable or disable the tab controls.

        Args:
            enabled: Whether controls should be enabled
        """
        self._upload_widget.setEnabled(enabled)
        self._ingest_on_select.setEnabled(enabled)

    def _terminate_workers(self) -> None:
        """
        Safely terminate any running worker threads.

        Waits up to WORKER_TERMINATE_TIMEOUT_MS for workers to finish.
        """
        if self._ingest_worker is not None and self._ingest_worker.isRunning():
            logger.info("Terminating ingest worker thread...")
            self._ingest_worker.terminate()
            if not self._ingest_worker.wait(WORKER_TERMINATE_TIMEOUT_MS):
                logger.warning(
                    f"Ingest worker did not terminate within "
                    f"{WORKER_TERMINATE_TIMEOUT_MS}ms"
                )

    def closeEvent(self, event: QCloseEvent) -> None:
        """
        Handle widget close event.

        Ensures worker threads are properly terminated before closing.

        Args:
            event: The close event
        """
        self._terminate_workers()
        # Clear worker reference for garbage collection
        self._ingest_worker = None
        super().closeEvent(event)


__all__ = ['PDFUploadTab']
