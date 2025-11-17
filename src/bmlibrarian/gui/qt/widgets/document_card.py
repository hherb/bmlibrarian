"""
Document card widget for BMLibrarian Qt GUI.

Displays document information in a card format using centralized
styles and utility functions for consistent formatting.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt, Signal
from typing import Optional, Dict, Any

from .card_utils import (
    DocumentData,
    validate_document_data,
    format_authors,
    extract_year,
    format_journal_year,
    format_document_ids,
    format_relevance_score,
    html_escape
)


class DocumentCard(QFrame):
    """
    Card widget for displaying document information.

    Shows title, authors, journal, year, and relevance score using
    centralized stylesheet and utility functions.

    Signals:
        clicked: Emitted when card is clicked, passes document data

    Example:
        >>> doc_data = {
        ...     "title": "Example Study",
        ...     "authors": ["Smith J", "Jones A"],
        ...     "journal": "Nature",
        ...     "year": 2023,
        ...     "pmid": 12345678,
        ...     "relevance_score": 4.5
        ... }
        >>> card = DocumentCard(doc_data)
    """

    # Signal emitted when card is clicked
    clicked = Signal(dict)  # Emits document data

    def __init__(self, document_data: Dict[str, Any], parent: Optional[QWidget] = None):
        """
        Initialize document card.

        Args:
            document_data: Dictionary containing document information
            parent: Optional parent widget

        Raises:
            TypeError: If document_data is not a dictionary
            ValueError: If required fields are missing
        """
        super().__init__(parent)

        # Validate and store document data
        self.document_data = validate_document_data(document_data)

        # Configure frame (styling from QSS)
        self.setFrameShape(QFrame.StyledPanel)
        self.setObjectName("documentCard")

        # Create layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(4)

        # Title
        title = self.document_data.get("title", "Untitled")
        title_label = QLabel(f"<b>{html_escape(title)}</b>")
        title_label.setObjectName("title")
        title_label.setWordWrap(True)
        title_label.setTextFormat(Qt.RichText)
        layout.addWidget(title_label)

        # Authors
        authors = format_authors(
            self.document_data.get("authors"),
            max_authors=3,
            et_al=True
        )
        authors_label = QLabel(f"<i>{html_escape(authors)}</i>")
        authors_label.setObjectName("authors")
        authors_label.setWordWrap(True)
        layout.addWidget(authors_label)

        # Journal and year
        journal_year = format_journal_year(
            self.document_data.get("journal"),
            self.document_data.get("year")
        )
        if journal_year:
            journal_label = QLabel(html_escape(journal_year))
            journal_label.setObjectName("journal")
            layout.addWidget(journal_label)

        # Relevance score (if available)
        score_text = format_relevance_score(self.document_data.get("relevance_score"))
        if score_text:
            score_label = QLabel(score_text)
            score_label.setObjectName("score")
            layout.addWidget(score_label)

        # PMID/DOI
        ids_text = format_document_ids(
            pmid=self.document_data.get("pmid"),
            doi=self.document_data.get("doi"),
            doc_id=self.document_data.get("document_id")
        )
        if ids_text:
            ids_label = QLabel(ids_text)
            ids_label.setObjectName("metadata")
            layout.addWidget(ids_label)

    def mousePressEvent(self, event):
        """
        Handle mouse press event.

        Emits clicked signal with document data on left button click.

        Args:
            event: Mouse event
        """
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.document_data)
        super().mousePressEvent(event)

    def get_document_id(self) -> Optional[int]:
        """
        Get the document ID.

        Returns:
            Document ID if available, None otherwise
        """
        return self.document_data.get("document_id")

    def get_title(self) -> str:
        """
        Get the document title.

        Returns:
            Document title
        """
        return self.document_data.get("title", "Untitled")

    def update_relevance_score(self, score: float) -> None:
        """
        Update the relevance score display.

        Args:
            score: New relevance score value
        """
        self.document_data["relevance_score"] = score

        # Find and update the score label
        for i in range(self.layout().count()):
            widget = self.layout().itemAt(i).widget()
            if isinstance(widget, QLabel) and widget.objectName() == "score":
                score_text = format_relevance_score(score)
                widget.setText(score_text)
                break
