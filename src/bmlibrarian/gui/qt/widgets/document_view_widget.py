"""
Reusable document view widget with three tabs.

Provides a comprehensive document viewing interface with:
- Tab 1: Metadata and abstract display with PDF discovery/upload buttons
- Tab 2: Native PDF viewer with zoom controls
- Tab 3: Full text/chunks display with toggle and embedding functionality
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QLabel,
    QPushButton, QScrollArea, QFrame, QMessageBox, QProgressDialog,
    QFileDialog, QSplitter
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QFont

from ..resources.styles import get_font_scale, StylesheetGenerator
from .markdown_viewer import MarkdownViewer
from .pdf_viewer import PDFViewerWidget

logger = logging.getLogger(__name__)


@dataclass
class DocumentViewData:
    """Data structure for document view widget."""

    document_id: Optional[int] = None
    title: str = ""
    authors: Optional[str] = None
    journal: Optional[str] = None
    year: Optional[int] = None
    pmid: Optional[str] = None
    doi: Optional[str] = None
    abstract: Optional[str] = None
    full_text: Optional[str] = None
    pdf_path: Optional[str] = None
    pdf_url: Optional[str] = None
    publication_date: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DocumentViewData":
        """Create DocumentViewData from a dictionary.

        Args:
            data: Dictionary with document fields

        Returns:
            DocumentViewData instance
        """
        return cls(
            document_id=data.get('document_id') or data.get('id'),
            title=data.get('title', ''),
            authors=data.get('authors'),
            journal=data.get('journal'),
            year=data.get('year'),
            pmid=str(data.get('pmid')) if data.get('pmid') else None,
            doi=data.get('doi'),
            abstract=data.get('abstract'),
            full_text=data.get('full_text'),
            pdf_path=data.get('pdf_path'),
            pdf_url=data.get('pdf_url'),
            publication_date=data.get('publication_date'),
        )


class ChunkEmbeddingWorker(QThread):
    """Background worker for chunking and embedding a document."""

    progress = Signal(int, int)  # current, total
    finished = Signal(int)  # chunks_created
    error = Signal(str)  # error message

    def __init__(
        self,
        document_id: int,
        parent: Optional[QWidget] = None
    ) -> None:
        """Initialize chunk embedding worker.

        Args:
            document_id: Document ID to chunk and embed
            parent: Optional parent widget
        """
        super().__init__(parent)
        self.document_id = document_id
        self._cancelled = False

    def run(self) -> None:
        """Execute chunking and embedding."""
        try:
            from bmlibrarian.embeddings.chunk_embedder import ChunkEmbedder

            embedder = ChunkEmbedder()

            def progress_callback(current: int, total: int) -> None:
                if not self._cancelled:
                    self.progress.emit(current, total)

            chunks_created = embedder.chunk_and_embed(
                document_id=self.document_id,
                progress_callback=progress_callback
            )

            if not self._cancelled:
                self.finished.emit(chunks_created)

        except Exception as e:
            logger.error(f"Chunk embedding failed: {e}")
            if not self._cancelled:
                self.error.emit(str(e))

    def cancel(self) -> None:
        """Request cancellation of the operation."""
        self._cancelled = True


class MetadataTab(QWidget):
    """Tab displaying document metadata and abstract."""

    pdf_discovery_requested = Signal()  # Emitted when PDF discovery button clicked
    pdf_upload_requested = Signal()  # Emitted when PDF upload button clicked
    pdf_replace_requested = Signal()  # Emitted when PDF replace button clicked

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Initialize metadata tab.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)
        self.scale = get_font_scale()
        self.style_gen = StylesheetGenerator()
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        s = self.scale

        layout = QVBoxLayout(self)
        layout.setContentsMargins(s['padding_medium'], s['padding_medium'],
                                  s['padding_medium'], s['padding_medium'])
        layout.setSpacing(s['spacing_medium'])

        # Scrollable area for content
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(s['spacing_medium'])

        # Title
        self.title_label = QLabel()
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet(
            self.style_gen.label_stylesheet(font_size_key='font_large', bold=True)
        )
        content_layout.addWidget(self.title_label)

        # Authors
        self.authors_label = QLabel()
        self.authors_label.setWordWrap(True)
        self.authors_label.setStyleSheet(
            self.style_gen.label_stylesheet(font_size_key='font_normal', color='#555')
        )
        content_layout.addWidget(self.authors_label)

        # Journal and Year
        self.journal_label = QLabel()
        self.journal_label.setStyleSheet(
            self.style_gen.label_stylesheet(font_size_key='font_small', color='#666')
        )
        content_layout.addWidget(self.journal_label)

        # IDs (PMID, DOI)
        self.ids_label = QLabel()
        self.ids_label.setWordWrap(True)
        self.ids_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.ids_label.setStyleSheet(
            self.style_gen.label_stylesheet(font_size_key='font_tiny', color='#888')
        )
        content_layout.addWidget(self.ids_label)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet("background-color: #ddd;")
        separator.setFixedHeight(1)
        content_layout.addWidget(separator)

        # Abstract header
        abstract_header = QLabel("Abstract")
        abstract_header.setStyleSheet(
            self.style_gen.label_stylesheet(font_size_key='font_medium', bold=True)
        )
        content_layout.addWidget(abstract_header)

        # Abstract content (markdown capable)
        self.abstract_viewer = MarkdownViewer()
        self.abstract_viewer.setMinimumHeight(s['control_height_large'] * 3)
        content_layout.addWidget(self.abstract_viewer)

        content_layout.addStretch()

        scroll_area.setWidget(content_widget)
        layout.addWidget(scroll_area, 1)

        # Button bar at the bottom
        button_layout = QHBoxLayout()
        button_layout.setSpacing(s['spacing_medium'])

        self.discover_btn = QPushButton("Discover PDF")
        self.discover_btn.setToolTip("Search for PDF from online sources")
        self.discover_btn.setStyleSheet(
            self.style_gen.button_stylesheet(
                bg_color="#FF9800",
                hover_color="#F57C00"
            )
        )
        self.discover_btn.clicked.connect(self.pdf_discovery_requested.emit)
        button_layout.addWidget(self.discover_btn)

        self.replace_btn = QPushButton("Replace PDF")
        self.replace_btn.setToolTip("Replace existing PDF with another file")
        self.replace_btn.setStyleSheet(
            self.style_gen.button_stylesheet(
                bg_color="#9C27B0",
                hover_color="#7B1FA2"
            )
        )
        self.replace_btn.clicked.connect(self.pdf_replace_requested.emit)
        self.replace_btn.hide()  # Hidden by default, shown when PDF exists
        button_layout.addWidget(self.replace_btn)

        self.upload_btn = QPushButton("Upload PDF")
        self.upload_btn.setToolTip("Upload a PDF file from your computer")
        self.upload_btn.setStyleSheet(
            self.style_gen.button_stylesheet(
                bg_color="#4CAF50",
                hover_color="#388E3C"
            )
        )
        self.upload_btn.clicked.connect(self.pdf_upload_requested.emit)
        button_layout.addWidget(self.upload_btn)

        button_layout.addStretch()
        layout.addLayout(button_layout)

    def set_document(self, data: DocumentViewData) -> None:
        """Set document data for display.

        Args:
            data: Document data to display
        """
        self.title_label.setText(data.title or "Untitled")
        self.authors_label.setText(data.authors or "Unknown authors")

        # Journal and year
        journal_parts = []
        if data.journal:
            journal_parts.append(data.journal)
        if data.year:
            journal_parts.append(f"({data.year})")
        self.journal_label.setText(" ".join(journal_parts))

        # IDs
        id_parts = []
        if data.pmid:
            id_parts.append(f"PMID: {data.pmid}")
        if data.doi:
            id_parts.append(f"DOI: {data.doi}")
        if data.document_id:
            id_parts.append(f"ID: {data.document_id}")
        self.ids_label.setText(" | ".join(id_parts))

        # Abstract
        if data.abstract:
            self.abstract_viewer.set_markdown(data.abstract)
        else:
            self.abstract_viewer.set_markdown("*No abstract available*")

        # Update button visibility based on PDF state
        has_pdf = bool(data.pdf_path and Path(data.pdf_path).exists())
        self.replace_btn.setVisible(has_pdf)
        self.discover_btn.setVisible(not has_pdf and bool(data.doi or data.pmid))
        self.upload_btn.setVisible(not has_pdf)

    def clear(self) -> None:
        """Clear all displayed content."""
        self.title_label.clear()
        self.authors_label.clear()
        self.journal_label.clear()
        self.ids_label.clear()
        self.abstract_viewer.clear_content()
        self.replace_btn.hide()
        self.discover_btn.show()
        self.upload_btn.show()


class PDFViewerTab(QWidget):
    """Tab for viewing PDF documents."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Initialize PDF viewer tab.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)
        self.scale = get_font_scale()
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # PDF viewer widget (includes navigation and zoom controls)
        self.pdf_viewer = PDFViewerWidget()
        layout.addWidget(self.pdf_viewer)

        # Placeholder for when no PDF is loaded
        self.placeholder = QLabel("No PDF loaded")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder.setStyleSheet(
            StylesheetGenerator().label_stylesheet(
                font_size_key='font_large',
                color='#888'
            )
        )
        layout.addWidget(self.placeholder)

        self._show_placeholder(True)

    def _show_placeholder(self, show: bool) -> None:
        """Toggle between placeholder and PDF viewer.

        Args:
            show: True to show placeholder, False to show PDF viewer
        """
        self.placeholder.setVisible(show)
        self.pdf_viewer.setVisible(not show)

    def load_pdf(self, pdf_path: str) -> bool:
        """Load a PDF file.

        Args:
            pdf_path: Path to PDF file

        Returns:
            True if loaded successfully
        """
        path = Path(pdf_path)
        if not path.exists():
            logger.warning(f"PDF file not found: {pdf_path}")
            self._show_placeholder(True)
            return False

        try:
            self.pdf_viewer.load_pdf(pdf_path)
            self._show_placeholder(False)
            return True
        except Exception as e:
            logger.error(f"Failed to load PDF: {e}")
            self._show_placeholder(True)
            return False

    def clear(self) -> None:
        """Clear the PDF viewer."""
        self.pdf_viewer.clear()
        self._show_placeholder(True)

    def get_all_text(self) -> str:
        """Extract all text from the loaded PDF.

        Returns:
            Extracted text or empty string
        """
        return self.pdf_viewer.get_all_text()


class FullTextTab(QWidget):
    """Tab for viewing full text and chunks."""

    chunk_embedding_requested = Signal()  # Emitted when user wants to embed chunks

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Initialize full text tab.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)
        self.scale = get_font_scale()
        self.style_gen = StylesheetGenerator()

        self._document_id: Optional[int] = None
        self._full_text: Optional[str] = None
        self._chunks: Optional[List[Dict[str, Any]]] = None
        self._showing_chunks = False

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        s = self.scale

        layout = QVBoxLayout(self)
        layout.setContentsMargins(s['padding_small'], s['padding_small'],
                                  s['padding_small'], s['padding_small'])
        layout.setSpacing(s['spacing_small'])

        # Content viewer (markdown capable)
        self.content_viewer = MarkdownViewer()
        layout.addWidget(self.content_viewer, 1)

        # Button bar at the bottom
        button_layout = QHBoxLayout()
        button_layout.setSpacing(s['spacing_medium'])

        self.toggle_btn = QPushButton("Show Chunks")
        self.toggle_btn.setToolTip("Toggle between full text and chunks view")
        self.toggle_btn.setStyleSheet(
            self.style_gen.button_stylesheet(
                bg_color="#2196F3",
                hover_color="#1976D2"
            )
        )
        self.toggle_btn.clicked.connect(self._on_toggle_clicked)
        button_layout.addWidget(self.toggle_btn)

        button_layout.addStretch()
        layout.addLayout(button_layout)

    def set_document(
        self,
        document_id: Optional[int],
        full_text: Optional[str]
    ) -> None:
        """Set document data for display.

        Args:
            document_id: Document database ID
            full_text: Full text content
        """
        self._document_id = document_id
        self._full_text = full_text
        self._chunks = None
        self._showing_chunks = False

        self._update_display()
        self.toggle_btn.setText("Show Chunks")
        self.toggle_btn.setEnabled(bool(document_id))

    def _update_display(self) -> None:
        """Update the displayed content based on current state."""
        if self._showing_chunks and self._chunks:
            self._display_chunks()
        elif self._full_text:
            self.content_viewer.set_markdown(self._full_text)
        else:
            self.content_viewer.set_markdown("*No full text available*")

    def _display_chunks(self) -> None:
        """Display chunks as markdown."""
        if not self._chunks:
            self.content_viewer.set_markdown("*No chunks available*")
            return

        # Format chunks as markdown
        md_parts = [f"# Document Chunks ({len(self._chunks)} total)\n"]

        for chunk in self._chunks:
            chunk_no = chunk.get('chunk_no', 0)
            start_pos = chunk.get('start_pos', 0)
            end_pos = chunk.get('end_pos', 0)
            text = chunk.get('text', '')

            md_parts.append(f"\n## Chunk {chunk_no + 1}")
            md_parts.append(f"*Position: {start_pos} - {end_pos} ({end_pos - start_pos + 1} chars)*\n")
            md_parts.append(text)
            md_parts.append("\n---\n")

        self.content_viewer.set_markdown("\n".join(md_parts))

    def _on_toggle_clicked(self) -> None:
        """Handle toggle button click."""
        if self._showing_chunks:
            # Switch back to full text
            self._showing_chunks = False
            self.toggle_btn.setText("Show Chunks")
            self._update_display()
        else:
            # Switch to chunks view
            if self._chunks is None:
                # Need to load chunks
                self._load_chunks()

            if self._chunks:
                self._showing_chunks = True
                self.toggle_btn.setText("Show Full Text")
                self._update_display()
            elif self._chunks == []:
                # No chunks exist, ask if user wants to create them
                self._prompt_chunk_embedding()

    def _load_chunks(self) -> None:
        """Load chunks from database."""
        if not self._document_id:
            self._chunks = []
            return

        try:
            from bmlibrarian.database import get_db_manager

            db_manager = get_db_manager()
            with db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT chunk_no, start_pos, end_pos
                        FROM semantic.chunks
                        WHERE document_id = %s
                        ORDER BY chunk_no
                        """,
                        (self._document_id,),
                    )
                    rows = cur.fetchall()

            if rows and self._full_text:
                self._chunks = []
                for row in rows:
                    chunk_no, start_pos, end_pos = row
                    text = self._full_text[start_pos:end_pos + 1]
                    self._chunks.append({
                        'chunk_no': chunk_no,
                        'start_pos': start_pos,
                        'end_pos': end_pos,
                        'text': text
                    })
            else:
                self._chunks = []

        except Exception as e:
            logger.error(f"Failed to load chunks: {e}")
            self._chunks = []

    def _prompt_chunk_embedding(self) -> None:
        """Prompt user to create chunks if none exist."""
        if not self._document_id:
            return

        if not self._full_text:
            QMessageBox.warning(
                self,
                "No Full Text",
                "This document has no full text to chunk.\n\n"
                "Please ensure the document has full text content before chunking."
            )
            return

        reply = QMessageBox.question(
            self,
            "No Chunks Found",
            "This document has not been chunked and embedded yet.\n\n"
            "Would you like to chunk and embed it now?\n"
            "This may take a few moments.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.chunk_embedding_requested.emit()

    def set_chunks(self, chunks: List[Dict[str, Any]]) -> None:
        """Set chunks directly.

        Args:
            chunks: List of chunk dictionaries with chunk_no, start_pos, end_pos, text
        """
        self._chunks = chunks
        if self._showing_chunks:
            self._update_display()

    def reload_chunks(self) -> None:
        """Reload chunks from database and update display."""
        self._chunks = None
        self._load_chunks()
        if self._chunks:
            self._showing_chunks = True
            self.toggle_btn.setText("Show Full Text")
            self._update_display()

    def clear(self) -> None:
        """Clear all displayed content."""
        self._document_id = None
        self._full_text = None
        self._chunks = None
        self._showing_chunks = False
        self.content_viewer.clear_content()
        self.toggle_btn.setText("Show Chunks")
        self.toggle_btn.setEnabled(False)


class DocumentViewWidget(QWidget):
    """
    Reusable document view widget with three tabs.

    Provides comprehensive document viewing with:
    - Metadata tab: Title, authors, abstract, PDF discovery/upload
    - PDF tab: Native PDF viewer with zoom controls
    - Full text tab: Full text and chunk viewing with embedding

    Signals:
        document_changed: Emitted when a new document is loaded
        pdf_downloaded: Emitted when PDF is successfully downloaded
        pdf_uploaded: Emitted when PDF is successfully uploaded
        chunks_created: Emitted when chunks are created, with count
    """

    document_changed = Signal(int)  # document_id
    pdf_downloaded = Signal(str)  # pdf_path
    pdf_uploaded = Signal(str)  # pdf_path
    chunks_created = Signal(int)  # chunks_count

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Initialize document view widget.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)
        self.scale = get_font_scale()

        self._document_data: Optional[DocumentViewData] = None
        self._embedding_worker: Optional[ChunkEmbeddingWorker] = None
        self._progress_dialog: Optional[QProgressDialog] = None

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Tab widget
        self.tab_widget = QTabWidget()

        # Tab 1: Metadata
        self.metadata_tab = MetadataTab()
        self.tab_widget.addTab(self.metadata_tab, "Metadata")

        # Tab 2: PDF Viewer
        self.pdf_tab = PDFViewerTab()
        self.tab_widget.addTab(self.pdf_tab, "PDF")

        # Tab 3: Full Text / Chunks
        self.fulltext_tab = FullTextTab()
        self.tab_widget.addTab(self.fulltext_tab, "Full Text")

        layout.addWidget(self.tab_widget)

    def _connect_signals(self) -> None:
        """Connect internal signals."""
        # Metadata tab signals
        self.metadata_tab.pdf_discovery_requested.connect(self._on_pdf_discovery)
        self.metadata_tab.pdf_upload_requested.connect(self._on_pdf_upload)
        self.metadata_tab.pdf_replace_requested.connect(self._on_pdf_replace)

        # Full text tab signals
        self.fulltext_tab.chunk_embedding_requested.connect(self._on_chunk_embedding)

    def set_document(self, data: DocumentViewData) -> None:
        """Set document to display.

        Args:
            data: Document data to display
        """
        self._document_data = data

        # Update metadata tab
        self.metadata_tab.set_document(data)

        # Update PDF tab
        if data.pdf_path:
            self.pdf_tab.load_pdf(data.pdf_path)
        else:
            self.pdf_tab.clear()

        # Update full text tab
        self.fulltext_tab.set_document(data.document_id, data.full_text)

        # Emit signal
        if data.document_id:
            self.document_changed.emit(data.document_id)

    def set_document_from_dict(self, data: Dict[str, Any]) -> None:
        """Set document from a dictionary.

        Args:
            data: Dictionary with document fields
        """
        doc_data = DocumentViewData.from_dict(data)
        self.set_document(doc_data)

    def load_document_by_id(self, document_id: int) -> bool:
        """Load document from database by ID.

        Args:
            document_id: Document database ID

        Returns:
            True if loaded successfully
        """
        try:
            from bmlibrarian.database import get_db_manager

            db_manager = get_db_manager()
            with db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                            id, title, authors, journal,
                            EXTRACT(YEAR FROM publication_date)::integer as year,
                            pmid, doi, abstract, full_text, pdf_path,
                            publication_date::text
                        FROM public.document
                        WHERE id = %s
                        """,
                        (document_id,),
                    )
                    row = cur.fetchone()

            if not row:
                logger.warning(f"Document not found: {document_id}")
                return False

            data = DocumentViewData(
                document_id=row[0],
                title=row[1] or "",
                authors=row[2],
                journal=row[3],
                year=row[4],
                pmid=str(row[5]) if row[5] else None,
                doi=row[6],
                abstract=row[7],
                full_text=row[8],
                pdf_path=row[9],
                publication_date=row[10],
            )

            self.set_document(data)
            return True

        except Exception as e:
            logger.error(f"Failed to load document {document_id}: {e}")
            return False

    def clear(self) -> None:
        """Clear all displayed content."""
        self._document_data = None
        self.metadata_tab.clear()
        self.pdf_tab.clear()
        self.fulltext_tab.clear()

    def _on_pdf_discovery(self) -> None:
        """Handle PDF discovery request."""
        if not self._document_data:
            return

        # Create progress dialog
        progress = QProgressDialog(
            "Discovering PDF sources...",
            "Cancel",
            0, 0,
            self
        )
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()

        try:
            from bmlibrarian.discovery import download_pdf_for_document
            from bmlibrarian.config import get_config

            config = get_config()
            pdf_base_dir = Path(config.get('pdf', {}).get('base_dir', '~/knowledgebase/pdf'))
            pdf_base_dir = pdf_base_dir.expanduser()

            # Build document dict for discovery
            doc_dict = {
                'id': self._document_data.document_id,
                'doi': self._document_data.doi,
                'pmid': self._document_data.pmid,
                'title': self._document_data.title,
                'publication_date': self._document_data.publication_date,
            }

            def update_progress(stage: str, status: str) -> None:
                progress.setLabelText(f"{stage}: {status}")

            result = download_pdf_for_document(
                document=doc_dict,
                output_dir=pdf_base_dir,
                unpaywall_email=config.get('unpaywall_email'),
                progress_callback=update_progress
            )

            progress.close()

            if result.success and result.file_path:
                # Update database with PDF path
                self._update_pdf_path(result.file_path)

                # Reload document
                if self._document_data.document_id:
                    self.load_document_by_id(self._document_data.document_id)

                self.pdf_downloaded.emit(result.file_path)

                QMessageBox.information(
                    self,
                    "PDF Downloaded",
                    f"PDF successfully downloaded and saved.\n\n{result.file_path}"
                )
            else:
                QMessageBox.warning(
                    self,
                    "PDF Discovery Failed",
                    f"Could not find or download PDF.\n\n{result.error_message}"
                )

        except Exception as e:
            progress.close()
            logger.error(f"PDF discovery failed: {e}")
            QMessageBox.critical(
                self,
                "Error",
                f"PDF discovery failed:\n\n{e}"
            )

    def _on_pdf_upload(self) -> None:
        """Handle PDF upload request."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select PDF File",
            "",
            "PDF Files (*.pdf)"
        )

        if not file_path:
            return

        self._process_uploaded_pdf(file_path)

    def _on_pdf_replace(self) -> None:
        """Handle PDF replacement request."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Replacement PDF",
            "",
            "PDF Files (*.pdf)"
        )

        if not file_path:
            return

        self._process_uploaded_pdf(file_path, is_replacement=True)

    def _process_uploaded_pdf(
        self,
        source_path: str,
        is_replacement: bool = False
    ) -> None:
        """Process an uploaded PDF file.

        Args:
            source_path: Path to source PDF
            is_replacement: True if replacing existing PDF
        """
        try:
            from bmlibrarian.config import get_config
            import shutil

            config = get_config()
            pdf_base_dir = Path(config.get('pdf', {}).get('base_dir', '~/knowledgebase/pdf'))
            pdf_base_dir = pdf_base_dir.expanduser()

            # Determine destination path
            year = self._document_data.year if self._document_data else None
            if year:
                dest_dir = pdf_base_dir / str(year)
            else:
                dest_dir = pdf_base_dir / "unknown"

            dest_dir.mkdir(parents=True, exist_ok=True)

            # Generate filename
            if self._document_data and self._document_data.doi:
                safe_doi = self._document_data.doi.replace('/', '_').replace('\\', '_')
                filename = f"{safe_doi}.pdf"
            elif self._document_data and self._document_data.document_id:
                filename = f"doc_{self._document_data.document_id}.pdf"
            else:
                filename = Path(source_path).name

            dest_path = dest_dir / filename

            # Copy file
            shutil.copy2(source_path, dest_path)

            # Update database
            self._update_pdf_path(str(dest_path))

            # Reload document
            if self._document_data and self._document_data.document_id:
                self.load_document_by_id(self._document_data.document_id)

            self.pdf_uploaded.emit(str(dest_path))

            action = "replaced" if is_replacement else "uploaded"
            QMessageBox.information(
                self,
                f"PDF {action.title()}",
                f"PDF successfully {action}.\n\n{dest_path}"
            )

        except Exception as e:
            logger.error(f"Failed to upload PDF: {e}")
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to upload PDF:\n\n{e}"
            )

    def _update_pdf_path(self, pdf_path: str) -> None:
        """Update PDF path in database.

        Args:
            pdf_path: Path to PDF file
        """
        if not self._document_data or not self._document_data.document_id:
            return

        try:
            from bmlibrarian.database import get_db_manager

            db_manager = get_db_manager()
            with db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE public.document
                        SET pdf_path = %s
                        WHERE id = %s
                        """,
                        (pdf_path, self._document_data.document_id),
                    )

        except Exception as e:
            logger.error(f"Failed to update PDF path: {e}")

    def _on_chunk_embedding(self) -> None:
        """Handle chunk embedding request."""
        if not self._document_data or not self._document_data.document_id:
            return

        # Create progress dialog
        self._progress_dialog = QProgressDialog(
            "Chunking and embedding document...",
            "Cancel",
            0, 100,
            self
        )
        self._progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress_dialog.setMinimumDuration(0)
        self._progress_dialog.canceled.connect(self._cancel_embedding)

        # Create and start worker
        self._embedding_worker = ChunkEmbeddingWorker(
            self._document_data.document_id,
            self
        )
        self._embedding_worker.progress.connect(self._on_embedding_progress)
        self._embedding_worker.finished.connect(self._on_embedding_finished)
        self._embedding_worker.error.connect(self._on_embedding_error)
        self._embedding_worker.start()

    def _on_embedding_progress(self, current: int, total: int) -> None:
        """Handle embedding progress update.

        Args:
            current: Current progress
            total: Total items
        """
        if self._progress_dialog:
            if total > 0:
                percentage = int((current / total) * 100)
                self._progress_dialog.setValue(percentage)
                self._progress_dialog.setLabelText(
                    f"Processing chunks: {current}/{total}"
                )
            else:
                self._progress_dialog.setLabelText("Processing...")

    def _on_embedding_finished(self, chunks_created: int) -> None:
        """Handle embedding completion.

        Args:
            chunks_created: Number of chunks created
        """
        if self._progress_dialog:
            self._progress_dialog.close()
            self._progress_dialog = None

        self._embedding_worker = None

        # Reload chunks display
        self.fulltext_tab.reload_chunks()

        self.chunks_created.emit(chunks_created)

        QMessageBox.information(
            self,
            "Chunking Complete",
            f"Successfully created {chunks_created} chunks.\n\n"
            "The document has been chunked and embedded for semantic search."
        )

    def _on_embedding_error(self, error_message: str) -> None:
        """Handle embedding error.

        Args:
            error_message: Error description
        """
        if self._progress_dialog:
            self._progress_dialog.close()
            self._progress_dialog = None

        self._embedding_worker = None

        QMessageBox.critical(
            self,
            "Chunking Failed",
            f"Failed to chunk and embed document:\n\n{error_message}"
        )

    def _cancel_embedding(self) -> None:
        """Cancel ongoing embedding operation."""
        if self._embedding_worker:
            self._embedding_worker.cancel()
            self._embedding_worker.wait()
            self._embedding_worker = None

        if self._progress_dialog:
            self._progress_dialog.close()
            self._progress_dialog = None

    def get_current_document_id(self) -> Optional[int]:
        """Get the ID of the currently displayed document.

        Returns:
            Document ID or None if no document loaded
        """
        return self._document_data.document_id if self._document_data else None

    def get_pdf_text(self) -> str:
        """Get extracted text from the loaded PDF.

        Returns:
            PDF text or empty string
        """
        return self.pdf_tab.get_all_text()
