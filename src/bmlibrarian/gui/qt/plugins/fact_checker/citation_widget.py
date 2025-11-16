"""
Citation Widget for Fact-Checker Review.

Displays citation cards with expandable abstracts.
"""

from typing import Optional
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QFrame,
)
from PySide6.QtCore import Qt, Signal


class CitationCard(QWidget):
    """Individual citation card with expandable abstract."""

    def __init__(self, citation_data: dict, parent: Optional[QWidget] = None):
        """
        Initialize citation card.

        Args:
            citation_data: Citation data dictionary with pmid, title, abstract, etc.
            parent: Optional parent widget
        """
        super().__init__(parent)

        self.citation_data = citation_data
        self.is_expanded = False

        self._setup_ui()

    def _setup_ui(self):
        """Setup the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Title row with expand button
        title_layout = QHBoxLayout()

        # PMID/DOI label
        pmid = self.citation_data.get('pmid', 'N/A')
        doi = self.citation_data.get('doi', '')
        id_label = QLabel(f"PMID: {pmid}")
        id_label.setStyleSheet("font-weight: bold; color: #1565c0;")
        title_layout.addWidget(id_label)

        title_layout.addStretch()

        # Expand/collapse button
        self.expand_button = QPushButton("▼ Show Abstract")
        self.expand_button.setFixedWidth(140)
        self.expand_button.clicked.connect(self._toggle_abstract)
        self.expand_button.setStyleSheet(
            """
            QPushButton {
                background-color: #ff9800;
                color: white;
                padding: 4px 8px;
                border: none;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #f57c00;
            }
        """
        )
        title_layout.addWidget(self.expand_button)

        layout.addLayout(title_layout)

        # Title
        title = self.citation_data.get('title', 'No title')
        self.title_label = QLabel(title)
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet("font-weight: bold; color: #263238;")
        layout.addWidget(self.title_label)

        # Passage/excerpt (if available)
        passage = self.citation_data.get('passage', '')
        if passage:
            passage_label = QLabel(f"Relevant passage: \"{passage}\"")
            passage_label.setWordWrap(True)
            passage_label.setStyleSheet(
                "font-style: italic; color: #37474f; "
                "background-color: #fff3e0; padding: 8px; border-radius: 4px;"
            )
            layout.addWidget(passage_label)

        # Abstract (initially hidden)
        self.abstract_widget = QTextEdit()
        abstract = self.citation_data.get('abstract', 'No abstract available')
        self.abstract_widget.setPlainText(abstract)
        self.abstract_widget.setReadOnly(True)
        self.abstract_widget.setMinimumHeight(150)
        self.abstract_widget.setMaximumHeight(300)
        self.abstract_widget.setVisible(False)
        self.abstract_widget.setStyleSheet(
            """
            QTextEdit {
                background-color: #f5f5f5;
                border: 1px solid #ddd;
                padding: 8px;
                border-radius: 4px;
            }
        """
        )
        layout.addWidget(self.abstract_widget)

        # Authors and journal info
        authors = self.citation_data.get('authors', 'Unknown authors')
        journal = self.citation_data.get('journal', 'Unknown journal')
        year = self.citation_data.get('pub_year', 'N/A')

        info_label = QLabel(f"{authors} - {journal} ({year})")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("font-size: 11px; color: #666;")
        layout.addWidget(info_label)

        # Style the card
        self.setStyleSheet(
            """
            CitationCard {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
            }
        """
        )

    def _toggle_abstract(self):
        """Toggle abstract visibility."""
        self.is_expanded = not self.is_expanded

        if self.is_expanded:
            self.abstract_widget.setVisible(True)
            self.expand_button.setText("▲ Hide Abstract")
        else:
            self.abstract_widget.setVisible(False)
            self.expand_button.setText("▼ Show Abstract")


class CitationListWidget(QWidget):
    """Widget for displaying a list of citations."""

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize citation list widget.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)

        self._setup_ui()

    def _setup_ui(self):
        """Setup the user interface."""
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(10)

        # Empty state message
        self.empty_label = QLabel("No citations available")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet("color: #999; font-style: italic; padding: 20px;")
        self.layout.addWidget(self.empty_label)

    def set_citations(self, citations: list):
        """
        Set the list of citations to display.

        Args:
            citations: List of citation dictionaries
        """
        # Clear existing citations
        while self.layout.count() > 0:
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add new citations
        if not citations:
            self.empty_label = QLabel("No citations available")
            self.empty_label.setAlignment(Qt.AlignCenter)
            self.empty_label.setStyleSheet("color: #999; font-style: italic; padding: 20px;")
            self.layout.addWidget(self.empty_label)
        else:
            for citation in citations:
                card = CitationCard(citation)
                self.layout.addWidget(card)

            # Add stretch at the end
            self.layout.addStretch()

    def clear(self):
        """Clear all citations."""
        self.set_citations([])
