"""
Paper Weight Assessment Laboratory - Main Window

The main application window for the Paper Weight Assessment Laboratory.
Uses a tabbed interface with search, PDF upload, and results tabs.
"""

import logging
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QTabWidget, QMessageBox
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QCloseEvent

from bmlibrarian.agents.paper_weight import PaperWeightAssessmentAgent, get_document_for_viewer
from bmlibrarian.utils.pdf_manager import PDFManager
from bmlibrarian.gui.qt.resources.styles.dpi_scale import get_font_scale
from bmlibrarian.gui.qt.resources.styles.stylesheet_generator import get_stylesheet_generator

from .constants import (
    WINDOW_MIN_WIDTH,
    WINDOW_MIN_HEIGHT,
    WINDOW_DEFAULT_WIDTH,
    WINDOW_DEFAULT_HEIGHT,
    TAB_INDEX_SEARCH,
    TAB_INDEX_PDF_UPLOAD,
    TAB_INDEX_RESULTS,
    TAB_INDEX_DOCUMENT_VIEWER,
    WORKER_TERMINATE_TIMEOUT_MS,
)
from .tabs import SearchTab, PDFUploadTab, ResultsTab, DocumentViewerTab


logger = logging.getLogger(__name__)


class PDFIngestWorker(QThread):
    """
    Worker thread for PDF ingestion after download.

    Performs PDF text extraction and embedding creation in background.
    """

    ingest_complete = Signal(object)  # IngestResult
    ingest_error = Signal(str)
    status_update = Signal(str)

    def __init__(
        self,
        document_id: int,
        pdf_path: Path,
        parent: Optional[QThread] = None
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

            self.status_update.emit("Extracting text and creating embeddings...")

            result = ingestor.ingest_pdf_immediate(
                document_id=self.document_id,
                pdf_path=self.pdf_path,
                progress_callback=progress_callback,
            )

            self.ingest_complete.emit(result)

        except Exception as e:
            logger.exception(f"PDF ingestion error: {e}")
            self.ingest_error.emit(str(e))


class EmbeddingWorker(QThread):
    """
    Worker thread for creating embeddings from existing full_text.

    Used when full text is already in the database (e.g., from NXML extraction)
    and only embeddings need to be created.
    """

    embedding_complete = Signal(int)  # chunks_created
    embedding_error = Signal(str)
    status_update = Signal(str)

    def __init__(
        self,
        document_id: int,
        parent: Optional[QThread] = None
    ):
        """
        Initialize worker.

        Args:
            document_id: Database document ID
            parent: Parent object
        """
        super().__init__(parent)
        self.document_id = document_id

    def run(self) -> None:
        """Create embeddings from existing full_text in background."""
        try:
            from bmlibrarian.embeddings.chunk_embedder import ChunkEmbedder

            self.status_update.emit("Initializing embedder...")

            embedder = ChunkEmbedder()

            def progress_callback(current: int, total: int) -> None:
                """Handle progress updates."""
                if total > 0:
                    self.status_update.emit(f"Embedding: {current}/{total}")
                else:
                    self.status_update.emit("Embedding...")

            self.status_update.emit("Creating embeddings from full text...")

            num_chunks = embedder.chunk_and_embed(
                document_id=self.document_id,
                progress_callback=progress_callback,
            )

            self.embedding_complete.emit(num_chunks)

        except Exception as e:
            logger.exception(f"Embedding error: {e}")
            self.embedding_error.emit(str(e))


class PaperWeightLab(QMainWindow):
    """
    Main laboratory GUI window for paper weight assessment.

    Provides a tabbed interface with:
    - Search tab: Find documents by keyword or semantic search
    - PDF Upload tab: Upload PDFs and match/create documents
    - Results tab: Assessment, visualization, and export

    Workflow:
    - App starts on Search tab
    - After document selection, switches to Results tab
    - If full text is downloaded, it's automatically ingested before assessment
    """

    def __init__(self):
        """Initialize the Paper Weight Laboratory."""
        super().__init__()

        # Get scaling values
        self.scale = get_font_scale()
        self.styles = get_stylesheet_generator()

        # Initialize agent
        try:
            self.agent = PaperWeightAssessmentAgent(show_model_info=False)
        except Exception as e:
            logger.error(f"Failed to initialize agent: {e}")
            self.agent = None

        # Worker for PDF ingestion
        self._ingest_worker: Optional[PDFIngestWorker] = None
        self._pending_document_id: Optional[int] = None

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Initialize user interface."""
        self.setWindowTitle("Paper Weight Assessment Laboratory")
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self.resize(WINDOW_DEFAULT_WIDTH, WINDOW_DEFAULT_HEIGHT)

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(self.scale['spacing_medium'])
        main_layout.setContentsMargins(
            self.scale['padding_medium'],
            self.scale['padding_medium'],
            self.scale['padding_medium'],
            self.scale['padding_medium']
        )

        # Tab widget
        self.tab_widget = QTabWidget()

        # Create tabs
        self.search_tab = SearchTab()
        self.pdf_upload_tab = PDFUploadTab()
        self.results_tab = ResultsTab(agent=self.agent)
        self.document_viewer_tab = DocumentViewerTab()

        # Add tabs
        self.tab_widget.addTab(self.search_tab, "Document Search")
        self.tab_widget.addTab(self.pdf_upload_tab, "PDF Upload")
        self.tab_widget.addTab(self.results_tab, "Assessment Results")
        self.tab_widget.addTab(self.document_viewer_tab, "Full Text")

        main_layout.addWidget(self.tab_widget)

    def _connect_signals(self) -> None:
        """Connect tab signals."""
        # Connect document selection signals to switch to results tab
        self.search_tab.document_selected.connect(self._on_document_selected)
        self.pdf_upload_tab.document_selected.connect(self._on_document_selected)

        # Connect full text download signal to trigger ingestion
        self.search_tab.full_text_downloaded.connect(self._on_full_text_downloaded)

    def _on_document_selected(self, document_id: int) -> None:
        """
        Handle document selection from search or PDF upload tabs.

        Args:
            document_id: Selected document ID
        """
        # Load document in results tab
        self.results_tab.load_document(document_id)

        # Load document in document viewer tab
        self._load_document_viewer(document_id)

        # Switch to results tab
        self.tab_widget.setCurrentIndex(TAB_INDEX_RESULTS)

        # Refresh recent assessments in search tab
        self.search_tab.load_recent_assessments()

    def _load_document_viewer(self, document_id: int) -> None:
        """
        Load document content into the document viewer tab.

        Args:
            document_id: Database document ID
        """
        try:
            # Get document data
            doc_data = get_document_for_viewer(document_id)
            if not doc_data:
                logger.warning(f"Document {document_id} not found for viewer")
                self.document_viewer_tab.clear()
                return

            title = doc_data.get('title', 'Untitled')
            full_text = doc_data.get('full_text')
            pdf_filename = doc_data.get('pdf_filename')
            year = doc_data.get('year')

            # Resolve PDF path if filename exists
            pdf_path = None
            if pdf_filename:
                pdf_manager = PDFManager()
                # Build document dict for pdf_manager
                doc_for_path = {
                    'pdf_filename': pdf_filename,
                    'publication_date': f"{year}-01-01" if year else None
                }
                pdf_path = pdf_manager.get_pdf_path(doc_for_path)

            # Load into viewer
            self.document_viewer_tab.load_document(
                document_id=document_id,
                title=title,
                pdf_path=pdf_path,
                full_text=full_text
            )

        except Exception as e:
            logger.error(f"Error loading document viewer: {e}")
            self.document_viewer_tab.clear()

    def _on_full_text_downloaded(self, document_id: int, pdf_path: object) -> None:
        """
        Handle full text download from search tab.

        Starts PDF ingestion to extract text and create embeddings,
        then proceeds to document selection.

        For NXML downloads (no PDF), the full_text is already in the database,
        so we only need to create embeddings.

        Args:
            document_id: Document ID
            pdf_path: Path to downloaded PDF (as object due to Signal limitation).
                     May be None if full text came from NXML (already in DB).
        """
        # Store pending document ID
        self._pending_document_id = document_id

        # Show status in results tab (switch there first)
        self.tab_widget.setCurrentIndex(TAB_INDEX_RESULTS)

        # Handle NXML case (full text already in DB, just need embeddings)
        if pdf_path is None:
            logger.info(f"Full text from NXML for document {document_id}, creating embeddings...")
            self.results_tab.show_ingestion_status("Creating embeddings from full text...")

            # Use embedding worker instead of PDF ingest worker
            self._ingest_worker = EmbeddingWorker(document_id, self)
            self._ingest_worker.status_update.connect(self._on_ingest_status)
            self._ingest_worker.embedding_complete.connect(self._on_embedding_complete)
            self._ingest_worker.embedding_error.connect(self._on_ingest_error)
            self._ingest_worker.start()
            return

        # Convert to Path if needed
        if not isinstance(pdf_path, Path):
            pdf_path = Path(str(pdf_path))

        logger.info(f"Full text downloaded for document {document_id}, starting ingestion...")

        # Start ingestion worker
        self._ingest_worker = PDFIngestWorker(document_id, pdf_path, self)
        self._ingest_worker.status_update.connect(self._on_ingest_status)
        self._ingest_worker.ingest_complete.connect(self._on_ingest_complete)
        self._ingest_worker.ingest_error.connect(self._on_ingest_error)
        self._ingest_worker.start()

        # Show progress in results tab
        self.results_tab.show_ingestion_status("Starting PDF ingestion...")

    def _on_ingest_status(self, status: str) -> None:
        """
        Handle ingestion status update.

        Args:
            status: Status message
        """
        self.results_tab.show_ingestion_status(status)

    def _on_ingest_complete(self, result: object) -> None:
        """
        Handle completed PDF ingestion.

        Args:
            result: IngestResult from PDFIngestor
        """
        document_id = self._pending_document_id

        # Check result success
        if hasattr(result, 'success') and result.success:
            chunks = getattr(result, 'chunks_created', 0)
            chars = getattr(result, 'char_count', 0)
            self.results_tab.show_ingestion_status(
                f"Ingestion complete: {chunks} chunks, {chars:,} chars"
            )
            logger.info(f"PDF ingestion complete for document {document_id}")
        else:
            error_msg = getattr(result, 'error_message', 'Unknown error')
            self.results_tab.show_ingestion_status(f"Ingestion warning: {error_msg}")
            logger.warning(f"PDF ingestion warning for document {document_id}: {error_msg}")

        # Load document in results tab and document viewer
        if document_id is not None:
            self.results_tab.load_document(document_id)
            self._load_document_viewer(document_id)

        # Refresh recent assessments
        self.search_tab.load_recent_assessments()

    def _on_ingest_error(self, error: str) -> None:
        """
        Handle ingestion error.

        Args:
            error: Error message
        """
        document_id = self._pending_document_id

        self.results_tab.show_ingestion_status(f"Ingestion failed: {error}")
        logger.error(f"PDF ingestion error for document {document_id}: {error}")

        # Show error dialog
        QMessageBox.warning(
            self,
            "Ingestion Error",
            f"Failed to process PDF:\n{error}\n\n"
            "The assessment will proceed using only the abstract."
        )

        # Still load document
        if document_id is not None:
            self.results_tab.load_document(document_id)
            self._load_document_viewer(document_id)

    def _on_embedding_complete(self, num_chunks: int) -> None:
        """
        Handle completed embedding creation (for NXML full text).

        Args:
            num_chunks: Number of chunks created
        """
        document_id = self._pending_document_id

        self.results_tab.show_ingestion_status(
            f"Embedding complete: {num_chunks} chunks created"
        )
        logger.info(f"Embedding complete for document {document_id}: {num_chunks} chunks")

        # Load document in results tab and document viewer
        if document_id is not None:
            self.results_tab.load_document(document_id)
            self._load_document_viewer(document_id)

        # Refresh recent assessments
        self.search_tab.load_recent_assessments()

    def _terminate_workers(self) -> None:
        """Safely terminate any running worker threads."""
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
        Handle window close event.

        Ensures all child tab worker threads are properly terminated
        before closing the application.

        Args:
            event: The close event
        """
        logger.info("Closing Paper Weight Laboratory...")

        # Terminate our own workers
        self._terminate_workers()

        # Terminate workers in child tabs
        # The tabs' closeEvent will be called automatically, but we ensure
        # cleanup happens even if closeEvent propagation fails
        if hasattr(self.pdf_upload_tab, '_terminate_workers'):
            self.pdf_upload_tab._terminate_workers()
        if hasattr(self.results_tab, '_terminate_workers'):
            self.results_tab._terminate_workers()

        super().closeEvent(event)


def main() -> None:
    """Main entry point for the Paper Weight Laboratory."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    lab = PaperWeightLab()
    lab.show()

    sys.exit(app.exec())


__all__ = ['PaperWeightLab', 'main']
