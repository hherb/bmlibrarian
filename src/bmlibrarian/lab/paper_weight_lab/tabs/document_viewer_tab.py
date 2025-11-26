"""
Paper Weight Laboratory - Document Viewer Tab

Provides document viewing using the reusable DocumentViewWidget.
"""

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtCore import Signal

from bmlibrarian.gui.qt.widgets import DocumentViewWidget, DocumentViewData


logger = logging.getLogger(__name__)


class DocumentViewerTab(QWidget):
    """
    Tab for viewing full text content of documents.

    Wraps DocumentViewWidget to provide document viewing with:
    - Metadata tab with title, authors, abstract
    - PDF tab with native viewer and zoom controls
    - Full text/chunks tab with embedding support
    """

    # Signal emitted when view mode changes (for compatibility)
    view_mode_changed = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize document viewer tab.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)

        # Current document state
        self._document_id: Optional[int] = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the user interface components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Use reusable DocumentViewWidget
        self._document_view = DocumentViewWidget()
        layout.addWidget(self._document_view)

        # Connect signals
        self._document_view.document_changed.connect(self._on_document_changed)

    def _on_document_changed(self, document_id: int) -> None:
        """Handle document change from the view widget."""
        self._document_id = document_id
        self.view_mode_changed.emit("loaded")

    def load_document(
        self,
        document_id: int,
        title: str,
        pdf_path: Optional[Path] = None,
        full_text: Optional[str] = None,
        authors: Optional[str] = None,
        journal: Optional[str] = None,
        year: Optional[int] = None,
        pmid: Optional[str] = None,
        doi: Optional[str] = None,
        abstract: Optional[str] = None,
    ) -> None:
        """
        Load a document for viewing.

        Args:
            document_id: Database document ID
            title: Document title for display
            pdf_path: Optional path to PDF file
            full_text: Optional full text content
            authors: Optional authors string
            journal: Optional journal name
            year: Optional publication year
            pmid: Optional PubMed ID
            doi: Optional DOI
            abstract: Optional abstract text
        """
        self._document_id = document_id

        doc_data = DocumentViewData(
            document_id=document_id,
            title=title,
            authors=authors,
            journal=journal,
            year=year,
            pmid=pmid,
            doi=doi,
            abstract=abstract,
            full_text=full_text,
            pdf_path=str(pdf_path) if pdf_path else None,
        )

        self._document_view.set_document(doc_data)

        logger.info(f"Document viewer loaded document {document_id}")

    def load_document_by_id(self, document_id: int) -> bool:
        """
        Load a document from the database by ID.

        Args:
            document_id: Database document ID

        Returns:
            True if loaded successfully
        """
        return self._document_view.load_document_by_id(document_id)

    def clear(self) -> None:
        """Clear the document viewer."""
        self._document_id = None
        self._document_view.clear()
        self.view_mode_changed.emit("empty")

    @property
    def document_id(self) -> Optional[int]:
        """Get the currently loaded document ID."""
        return self._document_id

    @property
    def current_view_mode(self) -> str:
        """Get the current view mode (for compatibility)."""
        if self._document_id:
            return "loaded"
        return "empty"


__all__ = ['DocumentViewerTab']
