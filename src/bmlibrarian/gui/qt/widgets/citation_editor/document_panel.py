"""
Document panel for viewing selected document and inserting citations.

Provides:
- 3-tab document viewer (metadata, PDF, full text)
- Insert Citation button
- Back to Search button
"""

import logging
from typing import Optional, Dict, Any

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
)
from PySide6.QtCore import Signal

from ...resources.styles import get_font_scale, StylesheetGenerator
from ..document_view_widget import DocumentViewWidget, DocumentViewData

logger = logging.getLogger(__name__)


class CitationDocumentPanel(QWidget):
    """
    Document panel for viewing and citing documents.

    Signals:
        insert_citation: Emitted when Insert Citation is clicked (document_id, label)
        back_to_search: Emitted when Back to Search is clicked
    """

    insert_citation = Signal(int, str)  # document_id, label
    back_to_search = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize document panel.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        self.scale = get_font_scale()
        self.style_gen = StylesheetGenerator()

        self._current_document: Optional[Dict[str, Any]] = None
        self._current_document_id: Optional[int] = None

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        s = self.scale

        layout = QVBoxLayout(self)
        layout.setContentsMargins(s['padding_small'], s['padding_small'],
                                  s['padding_small'], s['padding_small'])
        layout.setSpacing(s['spacing_small'])

        # Header with back button
        header_layout = QHBoxLayout()
        header_layout.setSpacing(s['spacing_small'])

        self.back_btn = QPushButton("← Back to Search")
        self.back_btn.setStyleSheet(
            self.style_gen.button_stylesheet(
                bg_color="#757575",
                hover_color="#616161"
            )
        )
        self.back_btn.setToolTip("Return to search results")
        header_layout.addWidget(self.back_btn)

        header_layout.addStretch()

        # Document title label
        self.title_label = QLabel("Select a document")
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet(
            self.style_gen.label_stylesheet(font_size_key='font_medium', bold=True)
        )
        header_layout.addWidget(self.title_label, 1)

        layout.addLayout(header_layout)

        # Document viewer (3-tab widget)
        self.document_viewer = DocumentViewWidget()
        layout.addWidget(self.document_viewer, 1)

        # Bottom button bar
        button_layout = QHBoxLayout()
        button_layout.setSpacing(s['spacing_medium'])

        button_layout.addStretch()

        # Insert Citation button (prominent)
        self.insert_btn = QPushButton("Insert Citation")
        self.insert_btn.setStyleSheet(
            self.style_gen.button_stylesheet(
                bg_color="#4CAF50",
                hover_color="#388E3C",
                font_size_key='font_medium'
            )
        )
        self.insert_btn.setToolTip("Insert citation marker at cursor position (Ctrl+Shift+K)")
        self.insert_btn.setEnabled(False)
        button_layout.addWidget(self.insert_btn)

        layout.addLayout(button_layout)

    def _connect_signals(self) -> None:
        """Connect signal handlers."""
        self.back_btn.clicked.connect(self.back_to_search.emit)
        self.insert_btn.clicked.connect(self._on_insert_citation)

    def load_document(self, document_data: Dict[str, Any]) -> None:
        """
        Load a document for display.

        Args:
            document_data: Document data dictionary
        """
        self._current_document = document_data
        self._current_document_id = document_data.get('id') or document_data.get('document_id')

        # Update title
        title = document_data.get('title', 'Untitled')
        if len(title) > 100:
            title = title[:97] + "..."
        self.title_label.setText(title)

        # Load into document viewer
        try:
            if self._current_document_id:
                self.document_viewer.load_document_by_id(self._current_document_id)
            else:
                self.document_viewer.set_document_from_dict(document_data)

            self.insert_btn.setEnabled(True)

        except Exception as e:
            logger.error(f"Failed to load document: {e}")
            self.insert_btn.setEnabled(False)

    def load_document_by_id(self, document_id: int) -> bool:
        """
        Load a document by ID.

        Args:
            document_id: Document database ID

        Returns:
            True if loaded successfully
        """
        self._current_document_id = document_id

        try:
            success = self.document_viewer.load_document_by_id(document_id)
            if success:
                # Get title from viewer
                data = self.document_viewer._document_data
                if data:
                    title = data.title or "Untitled"
                    if len(title) > 100:
                        title = title[:97] + "..."
                    self.title_label.setText(title)
                    self._current_document = {
                        'id': document_id,
                        'title': data.title,
                        'authors': data.authors,
                        'year': data.year,
                        'journal': data.journal,
                    }
                self.insert_btn.setEnabled(True)
            else:
                self.insert_btn.setEnabled(False)

            return success

        except Exception as e:
            logger.error(f"Failed to load document {document_id}: {e}")
            self.insert_btn.setEnabled(False)
            return False

    def _on_insert_citation(self) -> None:
        """Handle Insert Citation button click."""
        if not self._current_document_id:
            return

        # Generate citation label
        label = self._generate_label()

        self.insert_citation.emit(self._current_document_id, label)

    def _generate_label(self) -> str:
        """
        Generate citation label from current document.

        Returns:
            Label like "Smith2023"
        """
        if not self._current_document:
            return f"Doc{self._current_document_id}"

        # Try to get first author surname
        authors = self._current_document.get('authors', '')
        year = self._current_document.get('year', '')

        if isinstance(authors, list):
            if authors:
                first_author = authors[0]
            else:
                first_author = ''
        else:
            # String - split by comma or semicolon
            first_author = str(authors).split(',')[0].split(';')[0].strip()

        # Extract surname
        surname = self._extract_surname(first_author)

        if not surname:
            surname = "Unknown"

        if year:
            return f"{surname}{year}"
        else:
            return surname

    def _extract_surname(self, author: str) -> str:
        """
        Extract surname from author name.

        Args:
            author: Author name string

        Returns:
            Surname
        """
        author = author.strip()

        if not author:
            return ""

        if ',' in author:
            # Format: "Surname, Firstname"
            return author.split(',')[0].strip()
        else:
            # Format: "Firstname Surname"
            parts = author.split()
            return parts[-1] if parts else ""

    def clear(self) -> None:
        """Clear the document panel."""
        self._current_document = None
        self._current_document_id = None
        self.title_label.setText("Select a document")
        self.document_viewer.clear()
        self.insert_btn.setEnabled(False)

    def get_current_document_id(self) -> Optional[int]:
        """
        Get the current document ID.

        Returns:
            Document ID or None
        """
        return self._current_document_id

    def get_current_document(self) -> Optional[Dict[str, Any]]:
        """
        Get the current document data.

        Returns:
            Document data dictionary or None
        """
        return self._current_document.copy() if self._current_document else None
