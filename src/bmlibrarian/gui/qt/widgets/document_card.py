"""
Document card widget for BMLibrarian Qt GUI.

Displays document information in a card format.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt, Signal
from typing import Optional, Dict, Any


class DocumentCard(QFrame):
    """
    Card widget for displaying document information.

    Shows title, authors, journal, year, and relevance score.
    """

    # Signal emitted when card is clicked
    clicked = Signal(dict)  # Emits document data

    def __init__(self, document_data: Dict[str, Any], parent: Optional[QWidget] = None):
        """
        Initialize document card.

        Args:
            document_data: Dictionary containing document information
            parent: Optional parent widget
        """
        super().__init__(parent)

        self.document_data = document_data

        # Configure frame
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            """
            DocumentCard {
                background-color: white;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 8px;
            }
            DocumentCard:hover {
                border: 1px solid #3498db;
                background-color: #f8f9fa;
            }
        """
        )

        # Create layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(4)

        # Title
        title = document_data.get("title", "Untitled")
        title_label = QLabel(f"<b>{title}</b>")
        title_label.setWordWrap(True)
        title_label.setTextFormat(Qt.RichText)
        layout.addWidget(title_label)

        # Authors
        authors = document_data.get("authors", "Unknown authors")
        if isinstance(authors, list):
            authors = ", ".join(authors[:3])  # First 3 authors
            if len(document_data.get("authors", [])) > 3:
                authors += " et al."
        authors_label = QLabel(f"<i>{authors}</i>")
        authors_label.setWordWrap(True)
        layout.addWidget(authors_label)

        # Journal and year
        journal = document_data.get("journal", "")
        year = document_data.get("year", "")
        if journal or year:
            journal_text = f"{journal}" if journal else ""
            year_text = f" ({year})" if year else ""
            journal_label = QLabel(f"{journal_text}{year_text}")
            layout.addWidget(journal_label)

        # Relevance score (if available)
        score = document_data.get("relevance_score")
        if score is not None:
            score_label = QLabel(f"Relevance Score: {score:.1f}/5")
            score_label.setStyleSheet("color: #3498db; font-weight: bold;")
            layout.addWidget(score_label)

        # PMID/DOI
        pmid = document_data.get("pmid")
        doi = document_data.get("doi")
        if pmid:
            pmid_label = QLabel(f"PMID: {pmid}")
            pmid_label.setStyleSheet("font-size: 8pt; color: #666;")
            layout.addWidget(pmid_label)
        if doi:
            doi_label = QLabel(f"DOI: {doi}")
            doi_label.setStyleSheet("font-size: 8pt; color: #666;")
            layout.addWidget(doi_label)

    def mousePressEvent(self, event):
        """
        Handle mouse press event.

        Args:
            event: Mouse event
        """
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.document_data)
        super().mousePressEvent(event)
