"""
Citation card widget for BMLibrarian Qt GUI.

Displays citation information with passage text.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame, QTextEdit
from PySide6.QtCore import Qt, Signal
from typing import Optional, Dict, Any


class CitationCard(QFrame):
    """
    Card widget for displaying citation information.

    Shows document info and relevant passage/quote.
    """

    # Signal emitted when card is clicked
    clicked = Signal(dict)  # Emits citation data

    def __init__(self, citation_data: Dict[str, Any], parent: Optional[QWidget] = None):
        """
        Initialize citation card.

        Args:
            citation_data: Dictionary containing citation information
            parent: Optional parent widget
        """
        super().__init__(parent)

        self.citation_data = citation_data

        # Configure frame
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            """
            CitationCard {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-left: 4px solid #3498db;
                border-radius: 4px;
                padding: 8px;
            }
            CitationCard:hover {
                background-color: #e9ecef;
                border-left: 4px solid #2980b9;
            }
        """
        )

        # Create layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        # Document title
        title = citation_data.get("title", "Untitled")
        title_label = QLabel(f"<b>{title}</b>")
        title_label.setWordWrap(True)
        title_label.setTextFormat(Qt.RichText)
        layout.addWidget(title_label)

        # Authors and year
        authors = citation_data.get("authors", "")
        if isinstance(authors, list):
            authors = ", ".join(authors[:2])  # First 2 authors
            if len(citation_data.get("authors", [])) > 2:
                authors += " et al."
        year = citation_data.get("year", "")
        if authors or year:
            author_text = f"{authors}" if authors else ""
            year_text = f" ({year})" if year else ""
            author_label = QLabel(f"<i>{author_text}{year_text}</i>")
            author_label.setStyleSheet("color: #666;")
            layout.addWidget(author_label)

        # Citation passage/quote
        passage = citation_data.get("passage", citation_data.get("quote", ""))
        if passage:
            passage_widget = QTextEdit()
            passage_widget.setPlainText(passage)
            passage_widget.setReadOnly(True)
            passage_widget.setMaximumHeight(100)
            passage_widget.setStyleSheet(
                """
                QTextEdit {
                    background-color: white;
                    border: 1px solid #ddd;
                    border-radius: 3px;
                    padding: 6px;
                    font-size: 9pt;
                }
            """
            )
            layout.addWidget(passage_widget)

        # Document ID (PMID/DOI)
        pmid = citation_data.get("pmid")
        doi = citation_data.get("doi")
        doc_id = citation_data.get("document_id")

        id_parts = []
        if pmid:
            id_parts.append(f"PMID: {pmid}")
        if doi:
            id_parts.append(f"DOI: {doi}")
        if doc_id and not pmid:
            id_parts.append(f"ID: {doc_id}")

        if id_parts:
            id_label = QLabel(" | ".join(id_parts))
            id_label.setStyleSheet("font-size: 8pt; color: #888;")
            layout.addWidget(id_label)

    def mousePressEvent(self, event):
        """
        Handle mouse press event.

        Args:
            event: Mouse event
        """
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.citation_data)
        super().mousePressEvent(event)
