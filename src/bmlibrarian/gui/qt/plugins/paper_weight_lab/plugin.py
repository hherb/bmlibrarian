"""
Paper Weight Lab Plugin for BMLibrarian Qt GUI.

Provides an interactive interface for assessing evidential weight of
research papers using the PaperWeightAssessmentAgent.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QTabWidget
from PySide6.QtCore import Signal
from typing import Optional

from ..base_tab import BaseTabPlugin, TabPluginMetadata
from ...core.document_receiver import IDocumentReceiver
from ...core.document_receiver_registry import DocumentReceiverRegistry


class PaperWeightLabTabWidget(QWidget, IDocumentReceiver):
    """
    Paper Weight Lab tab widget wrapper for the plugin system.

    This widget wraps the existing Paper Weight Lab tabs and provides
    document receiver capability for inter-plugin communication.
    """

    status_message = Signal(str)

    # IDocumentReceiver identifier
    RECEIVER_ID = "paper_weight_lab"

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize Paper Weight Lab tab wrapper.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)

        # Import lab components here to avoid circular imports
        from bmlibrarian.lab.paper_weight_lab.tabs import (
            SearchTab, PDFUploadTab, ResultsTab, DocumentViewerTab
        )
        from bmlibrarian.lab.paper_weight_lab.main_window import (
            PDFIngestWorker, EmbeddingWorker
        )
        from bmlibrarian.agents.paper_weight import PaperWeightAssessmentAgent
        from bmlibrarian.database import get_document_details
        from bmlibrarian.utils.pdf_manager import PDFManager
        from bmlibrarian.gui.qt.resources.styles.dpi_scale import get_font_scale
        from bmlibrarian.gui.qt.resources.styles.stylesheet_generator import (
            get_stylesheet_generator
        )

        # Get scaling
        self.scale = get_font_scale()
        self.styles = get_stylesheet_generator()

        # Initialize agent
        try:
            self.agent = PaperWeightAssessmentAgent(show_model_info=False)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to initialize agent: {e}")
            self.agent = None

        # Worker references
        self._ingest_worker = None
        self._pending_document_id = None

        # Store references to worker classes
        self._PDFIngestWorker = PDFIngestWorker
        self._EmbeddingWorker = EmbeddingWorker
        self._get_document_details = get_document_details
        self._PDFManager = PDFManager

        # Set up UI
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

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

        layout.addWidget(self.tab_widget)

        # Connect signals
        self._connect_signals()

    def _connect_signals(self) -> None:
        """Connect tab signals."""
        self.search_tab.document_selected.connect(self._on_document_selected)
        self.pdf_upload_tab.document_selected.connect(self._on_document_selected)
        self.search_tab.full_text_downloaded.connect(self._on_full_text_downloaded)

    def _on_document_selected(self, document_id: int) -> None:
        """
        Handle document selection.

        Args:
            document_id: Selected document ID
        """
        self.results_tab.load_document(document_id)
        self._load_document_viewer(document_id)
        self.tab_widget.setCurrentIndex(2)  # Results tab
        self.search_tab.load_recent_assessments()
        self.status_message.emit(f"Document {document_id} selected for assessment")

    def _load_document_viewer(self, document_id: int) -> None:
        """Load document into document viewer tab.

        Uses the canonical get_document_details function for consistent
        document fetching across all widgets.
        """
        import logging
        logger = logging.getLogger(__name__)

        try:
            doc_data = self._get_document_details(document_id)
            if not doc_data:
                logger.warning(f"Document {document_id} not found for viewer")
                self.document_viewer_tab.clear()
                return

            title = doc_data.get('title', 'Untitled')
            full_text = doc_data.get('full_text')
            pdf_filename = doc_data.get('pdf_filename')
            year = doc_data.get('year')

            pdf_path = None
            if pdf_filename:
                pdf_manager = self._PDFManager()
                doc_for_path = {
                    'pdf_filename': pdf_filename,
                    'publication_date': f"{year}-01-01" if year else None
                }
                pdf_path = pdf_manager.get_pdf_path(doc_for_path)

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
        """Handle full text download."""
        import logging
        from pathlib import Path
        logger = logging.getLogger(__name__)

        self._pending_document_id = document_id
        self.tab_widget.setCurrentIndex(2)  # Results tab

        if pdf_path is None:
            # NXML case - just need embeddings
            logger.info(f"Full text from NXML for document {document_id}")
            self.results_tab.show_ingestion_status("Creating embeddings from full text...")

            self._ingest_worker = self._EmbeddingWorker(document_id, self)
            self._ingest_worker.status_update.connect(self._on_ingest_status)
            self._ingest_worker.embedding_complete.connect(self._on_embedding_complete)
            self._ingest_worker.embedding_error.connect(self._on_ingest_error)
            self._ingest_worker.start()
            return

        if not isinstance(pdf_path, Path):
            pdf_path = Path(str(pdf_path))

        logger.info(f"Full text downloaded for document {document_id}")

        self._ingest_worker = self._PDFIngestWorker(document_id, pdf_path, self)
        self._ingest_worker.status_update.connect(self._on_ingest_status)
        self._ingest_worker.ingest_complete.connect(self._on_ingest_complete)
        self._ingest_worker.ingest_error.connect(self._on_ingest_error)
        self._ingest_worker.start()

        self.results_tab.show_ingestion_status("Starting PDF ingestion...")

    def _on_ingest_status(self, status: str) -> None:
        """Handle ingestion status update."""
        self.results_tab.show_ingestion_status(status)
        self.status_message.emit(status)

    def _on_ingest_complete(self, result: object) -> None:
        """Handle PDF ingestion completion."""
        document_id = self._pending_document_id

        if hasattr(result, 'success') and result.success:
            chunks = getattr(result, 'chunks_created', 0)
            chars = getattr(result, 'char_count', 0)
            self.results_tab.show_ingestion_status(
                f"Ingestion complete: {chunks} chunks, {chars:,} chars"
            )

        if document_id is not None:
            self.results_tab.load_document(document_id)
            self._load_document_viewer(document_id)

        self.search_tab.load_recent_assessments()

    def _on_ingest_error(self, error: str) -> None:
        """Handle ingestion error."""
        document_id = self._pending_document_id
        self.results_tab.show_ingestion_status(f"Ingestion failed: {error}")

        if document_id is not None:
            self.results_tab.load_document(document_id)
            self._load_document_viewer(document_id)

    def _on_embedding_complete(self, num_chunks: int) -> None:
        """Handle embedding completion."""
        document_id = self._pending_document_id
        self.results_tab.show_ingestion_status(
            f"Embedding complete: {num_chunks} chunks created"
        )

        if document_id is not None:
            self.results_tab.load_document(document_id)
            self._load_document_viewer(document_id)

        self.search_tab.load_recent_assessments()

    # IDocumentReceiver interface implementation

    def get_receiver_id(self) -> str:
        """Return unique identifier for this receiver."""
        return self.RECEIVER_ID

    def get_receiver_name(self) -> str:
        """Return display name for context menu."""
        return "Paper Weight Lab"

    def get_receiver_description(self) -> Optional[str]:
        """Return tooltip description for context menu."""
        return "Assess evidential weight of research papers across multiple dimensions"

    def can_receive_document(self, document: dict) -> bool:
        """Check if this receiver can handle the document."""
        return document.get('id') is not None

    def receive_document(self, document: dict) -> bool:
        """
        Receive a document from another tab.

        Uses DocumentProcessor to ensure embeddings exist before loading.

        Args:
            document: Document dictionary with at least 'id' key

        Returns:
            True if document was accepted
        """
        document_id = document.get('id')
        if document_id is None:
            return False

        # Use the document processor to check/create embeddings
        self._receive_and_prepare_document(document_id)
        return True

    def _receive_and_prepare_document(self, document_id: int) -> None:
        """
        Prepare a received document by ensuring embeddings exist.

        Args:
            document_id: Document ID to prepare
        """
        from ...core.document_processor import DocumentProcessor

        import logging
        logger = logging.getLogger(__name__)

        # Get document info via processor
        processor = DocumentProcessor()
        doc_info = processor.get_document_info(document_id)

        if not doc_info:
            logger.error(f"Document {document_id} not found")
            self._on_document_selected(document_id)
            return

        # If document already has embeddings, just load it
        if doc_info.has_embeddings:
            logger.info(f"Document {document_id} has {doc_info.embedding_count} embeddings, loading directly")
            self._on_document_selected(document_id)
            return

        # If document has full text, create embeddings
        if doc_info.has_full_text:
            logger.info(f"Document {document_id} has full text, creating embeddings")
            self._pending_document_id = document_id
            self.tab_widget.setCurrentIndex(2)  # Results tab
            self.results_tab.show_ingestion_status("Creating embeddings from full text...")

            self._ingest_worker = self._EmbeddingWorker(document_id, self)
            self._ingest_worker.status_update.connect(self._on_ingest_status)
            self._ingest_worker.embedding_complete.connect(self._on_embedding_complete)
            self._ingest_worker.embedding_error.connect(self._on_ingest_error)
            self._ingest_worker.start()
            return

        # If document has PDF, process it
        if doc_info.has_pdf:
            pdf_path = processor.get_pdf_path(doc_info)
            if pdf_path and pdf_path.exists():
                logger.info(f"Document {document_id} has PDF at {pdf_path}, processing")
                self._pending_document_id = document_id
                self.tab_widget.setCurrentIndex(2)  # Results tab
                self.results_tab.show_ingestion_status("Processing PDF...")

                self._ingest_worker = self._PDFIngestWorker(document_id, pdf_path, self)
                self._ingest_worker.status_update.connect(self._on_ingest_status)
                self._ingest_worker.ingest_complete.connect(self._on_ingest_complete)
                self._ingest_worker.ingest_error.connect(self._on_ingest_error)
                self._ingest_worker.start()
                return

        # No content - load anyway (search tab will offer to find PDF)
        logger.info(f"Document {document_id} has no content, loading with search tab")
        self._on_document_selected(document_id)

    def cleanup(self) -> None:
        """Clean up resources."""
        # Stop any running workers
        if self._ingest_worker is not None and self._ingest_worker.isRunning():
            self._ingest_worker.terminate()
            self._ingest_worker.wait(3000)

        # Clear tabs
        if hasattr(self.results_tab, '_terminate_workers'):
            self.results_tab._terminate_workers()


class PaperWeightLabPlugin(BaseTabPlugin):
    """Plugin for Paper Weight Lab interface."""

    def __init__(self):
        """Initialize Paper Weight Lab plugin."""
        super().__init__()
        self.tab_widget: Optional[PaperWeightLabTabWidget] = None

    def get_metadata(self) -> TabPluginMetadata:
        """
        Get plugin metadata.

        Returns:
            Plugin metadata including ID, name, and description
        """
        return TabPluginMetadata(
            plugin_id="paper_weight_lab",
            display_name="Paper Weight Lab",
            description="Interactive laboratory for assessing evidential weight of research papers across multiple dimensions (study design, sample size, methodology, bias)",
            version="1.0.0",
            icon="balance_scale",
            requires=[]
        )

    def create_widget(self, parent: Optional[QWidget] = None) -> QWidget:
        """
        Create the main widget for this tab.

        Args:
            parent: Optional parent widget

        Returns:
            Main Paper Weight Lab tab widget
        """
        self.tab_widget = PaperWeightLabTabWidget(parent)

        # Connect signals
        self.tab_widget.status_message.connect(
            lambda msg: self.status_changed.emit(msg)
        )

        # Register as document receiver
        registry = DocumentReceiverRegistry()
        registry.register_receiver(self.tab_widget)

        return self.tab_widget

    def on_tab_activated(self):
        """Called when this tab becomes active."""
        self._is_active = True
        self.status_changed.emit("Paper Weight Lab activated - Ready to assess evidence weight")

    def on_tab_deactivated(self):
        """Called when this tab is deactivated."""
        self._is_active = False

    def cleanup(self):
        """Cleanup resources when plugin is unloaded."""
        # Unregister from document receiver registry
        if self.tab_widget:
            registry = DocumentReceiverRegistry()
            registry.unregister_receiver(self.tab_widget.get_receiver_id())
            self.tab_widget.cleanup()

        super().cleanup()


def create_plugin() -> BaseTabPlugin:
    """
    Plugin factory function.

    Returns:
        Initialized PaperWeightLabPlugin instance
    """
    return PaperWeightLabPlugin()
