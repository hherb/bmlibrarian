"""
Collapsible document card widget for BMLibrarian Qt GUI.

Displays document information with collapsible details - collapsed state shows
title + score tag, expanded state shows full metadata and abstract.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QTextEdit
)
from PySide6.QtCore import Qt, Signal
from typing import Optional, Dict, Any

from .card_utils import (
    validate_document_data,
    format_authors,
    format_journal_year,
    format_document_ids,
    html_escape
)


class CollapsibleDocumentCard(QFrame):
    """
    Collapsible card widget for displaying document information.

    Collapsed: Shows title + score/tag in one line
    Expanded: Shows full metadata including authors, journal, abstract

    Signals:
        clicked: Emitted when card header is clicked (toggles expansion)
        expanded: Emitted when card is expanded
        collapsed: Emitted when card is collapsed
    """

    # Signals
    clicked = Signal(dict)  # Emits document data
    expanded = Signal()
    collapsed = Signal()

    def __init__(self, document_data: Dict[str, Any], parent: Optional[QWidget] = None):
        """
        Initialize collapsible document card.

        Args:
            document_data: Dictionary containing document information
            parent: Optional parent widget
        """
        super().__init__(parent)

        # Validate and store document data
        self.document_data = validate_document_data(document_data)
        self._is_expanded = False

        # Configure frame
        self.setFrameShape(QFrame.StyledPanel)
        self.setObjectName("collapsibleDocumentCard")
        self.setCursor(Qt.PointingHandCursor)

        # Create layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 8, 10, 8)
        self.main_layout.setSpacing(8)

        # Create header (always visible)
        self._create_header()

        # Create details section (hidden by default)
        self._create_details()
        self.details_widget.setVisible(False)

        # Style the card
        self._apply_collapsed_style()

    def _create_header(self):
        """Create the header row (title + tag)."""
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        # Title (truncated in collapsed state)
        title = self.document_data.get("title", "Untitled")
        self.title_label = QLabel(f"<b>{html_escape(title)}</b>")
        self.title_label.setObjectName("title")
        self.title_label.setWordWrap(False)  # No wrap when collapsed
        self.title_label.setTextFormat(Qt.RichText)

        # Enable text elision for long titles
        from PySide6.QtGui import QFontMetrics
        self.title_label.setMinimumWidth(200)

        header_layout.addWidget(self.title_label, stretch=1)

        # Score/tag badge
        self.score_tag = self._create_score_tag()
        if self.score_tag:
            header_layout.addWidget(self.score_tag)

        self.header_widget = QWidget()
        self.header_widget.setLayout(header_layout)
        self.main_layout.addWidget(self.header_widget)

    def _create_score_tag(self) -> Optional[QLabel]:
        """
        Create score tag badge.

        Returns:
            QLabel with formatted score, or None if no score available
        """
        # Check for combined score first (from hybrid search)
        score = self.document_data.get("_combined_score")
        if score is None:
            score = self.document_data.get("relevance_score")

        if score is None:
            return None

        # Format score with color coding
        if isinstance(score, (int, float)):
            score_val = float(score)

            # Color code based on score magnitude
            if score_val >= 4.0:
                color = "#27ae60"  # Green for high scores
            elif score_val >= 2.5:
                color = "#3498db"  # Blue for medium scores
            else:
                color = "#95a5a6"  # Gray for low scores

            tag = QLabel(f"<b>{score_val:.2f}</b>")
        else:
            color = "#95a5a6"
            tag = QLabel(f"<b>{score}</b>")

        tag.setStyleSheet(f"""
            QLabel {{
                background-color: {color};
                color: white;
                padding: 4px 10px;
                border-radius: 10px;
                font-size: 11pt;
            }}
        """)
        tag.setAlignment(Qt.AlignCenter)
        tag.setFixedHeight(24)
        tag.setMinimumWidth(50)

        return tag

    def _create_details(self):
        """Create the details section (shown when expanded)."""
        self.details_widget = QWidget()
        details_layout = QVBoxLayout(self.details_widget)
        details_layout.setContentsMargins(0, 4, 0, 0)
        details_layout.setSpacing(4)

        # Authors
        authors = format_authors(
            self.document_data.get("authors"),
            max_authors=10,  # Show more authors when expanded
            et_al=True
        )
        authors_label = QLabel(f"<i>{html_escape(authors)}</i>")
        authors_label.setObjectName("authors")
        authors_label.setWordWrap(True)
        authors_label.setStyleSheet("color: #555; font-size: 10pt;")
        details_layout.addWidget(authors_label)

        # Journal and year
        journal_year = format_journal_year(
            self.document_data.get("journal"),
            self.document_data.get("year")
        )
        if journal_year:
            journal_label = QLabel(html_escape(journal_year))
            journal_label.setObjectName("journal")
            journal_label.setStyleSheet("color: #666; font-size: 9pt;")
            details_layout.addWidget(journal_label)

        # PMID/DOI
        ids_text = format_document_ids(
            pmid=self.document_data.get("pmid"),
            doi=self.document_data.get("doi"),
            doc_id=self.document_data.get("document_id") or self.document_data.get("id")
        )
        if ids_text:
            ids_label = QLabel(ids_text)
            ids_label.setObjectName("metadata")
            ids_label.setStyleSheet("color: #888; font-size: 8pt;")
            details_layout.addWidget(ids_label)

        # Abstract (if available)
        abstract = self.document_data.get("abstract")
        if abstract:
            # Separator
            separator = QFrame()
            separator.setFrameShape(QFrame.HLine)
            separator.setFrameShadow(QFrame.Sunken)
            separator.setStyleSheet("background-color: #ddd;")
            details_layout.addWidget(separator)

            # Abstract label
            abstract_header = QLabel("<b>Abstract:</b>")
            abstract_header.setStyleSheet("color: #333; font-size: 9pt; margin-top: 4px;")
            details_layout.addWidget(abstract_header)

            # Abstract text (read-only, scrollable for very long abstracts)
            abstract_text = QTextEdit()
            abstract_text.setReadOnly(True)
            abstract_text.setPlainText(abstract)
            abstract_text.setMaximumHeight(200)  # Limit height for very long abstracts
            abstract_text.setStyleSheet("""
                QTextEdit {
                    background-color: #f9f9f9;
                    border: 1px solid #ddd;
                    border-radius: 4px;
                    padding: 6px;
                    font-size: 9pt;
                    color: #444;
                }
            """)
            details_layout.addWidget(abstract_text)

        self.main_layout.addWidget(self.details_widget)

    def _apply_collapsed_style(self):
        """Apply styling for collapsed state."""
        self.setStyleSheet("""
            QFrame#collapsibleDocumentCard {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-left: 3px solid #3498db;
                border-radius: 4px;
            }
            QFrame#collapsibleDocumentCard:hover {
                background-color: #e9ecef;
                border-left: 3px solid #2980b9;
            }
        """)

    def _apply_expanded_style(self):
        """Apply styling for expanded state."""
        self.setStyleSheet("""
            QFrame#collapsibleDocumentCard {
                background-color: #ffffff;
                border: 2px solid #3498db;
                border-radius: 4px;
            }
            QFrame#collapsibleDocumentCard:hover {
                background-color: #f8f9fa;
            }
        """)

    def mousePressEvent(self, event):
        """
        Handle mouse press event to toggle expansion.

        Args:
            event: Mouse event
        """
        if event.button() == Qt.LeftButton:
            self.toggle()
        super().mousePressEvent(event)

    def toggle(self):
        """Toggle expanded/collapsed state."""
        self._is_expanded = not self._is_expanded
        self.details_widget.setVisible(self._is_expanded)

        # Update title wrapping
        self.title_label.setWordWrap(self._is_expanded)

        # Update styling
        if self._is_expanded:
            self._apply_expanded_style()
            self.expanded.emit()
        else:
            self._apply_collapsed_style()
            self.collapsed.emit()

        self.clicked.emit(self.document_data)

    def expand(self):
        """Expand the card."""
        if not self._is_expanded:
            self.toggle()

    def collapse(self):
        """Collapse the card."""
        if self._is_expanded:
            self.toggle()

    def is_expanded(self) -> bool:
        """
        Check if card is expanded.

        Returns:
            True if expanded, False otherwise
        """
        return self._is_expanded

    def get_document_id(self) -> Optional[int]:
        """
        Get the document ID.

        Returns:
            Document ID if available, None otherwise
        """
        return self.document_data.get("document_id") or self.document_data.get("id")

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

        # Recreate score tag
        if self.score_tag:
            self.score_tag.deleteLater()

        self.score_tag = self._create_score_tag()
        if self.score_tag:
            # Find header layout and add new tag
            header_layout = self.header_widget.layout()
            header_layout.addWidget(self.score_tag)
