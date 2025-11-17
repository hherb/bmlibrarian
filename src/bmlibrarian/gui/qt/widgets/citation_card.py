"""
Citation card widget for BMLibrarian Qt GUI.

Displays citation information with passage text using centralized
styles and utility functions for consistent formatting.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame, QTextEdit
from PySide6.QtCore import Qt, Signal
from typing import Optional, Dict, Any

from .card_utils import (
    CitationData,
    validate_citation_data,
    format_authors,
    extract_year,
    format_document_ids,
    html_escape
)


class CitationCard(QFrame):
    """
    Card widget for displaying citation information.

    Shows document info and relevant passage/quote using centralized
    stylesheet and utility functions.

    Signals:
        clicked: Emitted when card is clicked, passes citation data

    Example:
        >>> citation_data = {
        ...     "title": "Example Study",
        ...     "authors": ["Smith J", "Jones A"],
        ...     "year": 2023,
        ...     "passage": "This is a relevant passage from the document.",
        ...     "pmid": 12345678
        ... }
        >>> card = CitationCard(citation_data)
    """

    # Signal emitted when card is clicked
    clicked = Signal(dict)  # Emits citation data

    def __init__(self, citation_data: Dict[str, Any], parent: Optional[QWidget] = None):
        """
        Initialize citation card.

        Args:
            citation_data: Dictionary containing citation information
            parent: Optional parent widget

        Raises:
            TypeError: If citation_data is not a dictionary
            ValueError: If required fields are missing
        """
        super().__init__(parent)

        # Validate and store citation data
        self.citation_data = validate_citation_data(citation_data)

        # Configure frame (styling from QSS)
        self.setFrameShape(QFrame.StyledPanel)
        self.setObjectName("citationCard")

        # Create layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        # Document title
        title = self.citation_data.get("title", "Untitled")
        title_label = QLabel(f"<b>{html_escape(title)}</b>")
        title_label.setObjectName("title")
        title_label.setWordWrap(True)
        title_label.setTextFormat(Qt.RichText)
        layout.addWidget(title_label)

        # Authors and year
        authors = format_authors(
            self.citation_data.get("authors"),
            max_authors=2,
            et_al=True
        )
        year_str = extract_year(self.citation_data.get("year"))

        if authors or year_str:
            author_text = html_escape(authors) if authors else ""
            year_text = f" ({year_str})" if year_str else ""
            author_label = QLabel(f"<i>{author_text}{year_text}</i>")
            author_label.setObjectName("authors")
            layout.addWidget(author_label)

        # Citation passage/quote
        passage = self.citation_data.get("passage", self.citation_data.get("quote", ""))
        if passage:
            passage_widget = QTextEdit()
            passage_widget.setPlainText(passage)
            passage_widget.setReadOnly(True)
            passage_widget.setMaximumHeight(100)
            passage_widget.setObjectName("passageText")
            layout.addWidget(passage_widget)

        # Document ID (PMID/DOI)
        ids_text = format_document_ids(
            pmid=self.citation_data.get("pmid"),
            doi=self.citation_data.get("doi"),
            doc_id=self.citation_data.get("document_id")
        )
        if ids_text:
            id_label = QLabel(ids_text)
            id_label.setObjectName("metadata")
            layout.addWidget(id_label)

    def mousePressEvent(self, event):
        """
        Handle mouse press event.

        Emits clicked signal with citation data on left button click.

        Args:
            event: Mouse event
        """
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.citation_data)
        super().mousePressEvent(event)

    def get_document_id(self) -> Optional[int]:
        """
        Get the document ID.

        Returns:
            Document ID if available, None otherwise
        """
        return self.citation_data.get("document_id")

    def get_title(self) -> str:
        """
        Get the document title.

        Returns:
            Document title
        """
        return self.citation_data.get("title", "Untitled")

    def get_passage(self) -> str:
        """
        Get the citation passage/quote.

        Returns:
            Passage or quote text
        """
        return self.citation_data.get("passage", self.citation_data.get("quote", ""))
