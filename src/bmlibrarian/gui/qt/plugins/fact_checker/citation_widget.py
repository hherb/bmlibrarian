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

# Import DPI-aware styling
from ...resources.styles import get_font_scale


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

        # DPI-aware scaling
        self.scale = get_font_scale()

        self.citation_data = citation_data
        self.is_expanded = False

        self._setup_ui()

    def _setup_ui(self):
        """Setup the user interface."""
        s = self.scale

        layout = QVBoxLayout(self)
        layout.setContentsMargins(s['spacing_medium'], s['spacing_medium'], s['spacing_medium'], s['spacing_medium'])
        layout.setSpacing(s['spacing_small'])

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
        self.expand_button.setFixedWidth(int(s['control_height_medium'] * 3.9))
        self.expand_button.clicked.connect(self._toggle_abstract)
        self.expand_button.setStyleSheet(f"""
            QPushButton {{
                background-color: #ff9800;
                color: white;
                padding: {s['padding_tiny']}px {s['padding_small']}px;
                border: none;
                border-radius: {s['radius_small']}px;
                font-size: {s['font_tiny']}pt;
            }}
            QPushButton:hover {{
                background-color: #f57c00;
            }}
        """)
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
            passage_label.setStyleSheet(f"""
                font-style: italic; color: #37474f;
                background-color: #fff3e0; padding: {s['padding_small']}px; border-radius: {s['radius_small']}px;
            """)
            layout.addWidget(passage_label)

        # Abstract (initially hidden)
        self.abstract_widget = QTextEdit()
        abstract = self.citation_data.get('abstract', 'No abstract available')
        self.abstract_widget.setPlainText(abstract)
        self.abstract_widget.setReadOnly(True)
        self.abstract_widget.setMinimumHeight(int(s['control_height_large'] * 3.75))
        self.abstract_widget.setMaximumHeight(int(s['control_height_large'] * 7.5))
        self.abstract_widget.setVisible(False)
        self.abstract_widget.setStyleSheet(f"""
            QTextEdit {{
                background-color: #f5f5f5;
                border: 1px solid #ddd;
                padding: {s['padding_small']}px;
                border-radius: {s['radius_small']}px;
            }}
        """)
        layout.addWidget(self.abstract_widget)

        # Authors and journal info
        authors = self.citation_data.get('authors', 'Unknown authors')
        journal = self.citation_data.get('journal', 'Unknown journal')
        year = self.citation_data.get('pub_year', 'N/A')

        info_label = QLabel(f"{authors} - {journal} ({year})")
        info_label.setWordWrap(True)
        info_label.setStyleSheet(f"font-size: {s['font_tiny']}pt; color: #666;")
        layout.addWidget(info_label)

        # Style the card
        self.setStyleSheet(f"""
            CitationCard {{
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: {s['radius_medium']}px;
            }}
        """)

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

        # DPI-aware scaling
        self.scale = get_font_scale()

        self._setup_ui()

    def _setup_ui(self):
        """Setup the user interface."""
        s = self.scale

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(s['spacing_medium'])

        # Empty state message
        self.empty_label = QLabel("No citations available")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet(f"color: #999; font-style: italic; padding: {s['padding_xlarge']}px;")
        self.layout.addWidget(self.empty_label)

    def set_citations(self, citations: list, db=None):
        """
        Set the list of citations to display.

        Args:
            citations: List of citation dictionaries
            db: Optional database connection for enriching citation data
        """
        s = self.scale

        # Clear existing citations
        while self.layout.count() > 0:
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add new citations
        if not citations:
            self.empty_label = QLabel("No citations available")
            self.empty_label.setAlignment(Qt.AlignCenter)
            self.empty_label.setStyleSheet(f"color: #999; font-style: italic; padding: {s['padding_xlarge']}px;")
            self.layout.addWidget(self.empty_label)
        else:
            for citation in citations:
                # Enrich citation with database data if needed
                enriched_citation = self._enrich_citation(citation, db)
                card = CitationCard(enriched_citation)
                self.layout.addWidget(card)

            # Add stretch at the end
            self.layout.addStretch()

    def _enrich_citation(self, citation: dict, db) -> dict:
        """
        Enrich citation with data from database if fields are missing.

        Args:
            citation: Citation dictionary
            db: Database connection

        Returns:
            Enriched citation dictionary
        """
        # If no database or document_id, return as-is
        if not db or 'document_id' not in citation:
            return citation

        # Check if we need to enrich (missing abstract or PMID)
        needs_enrichment = (
            not citation.get('abstract') or
            citation.get('abstract') == 'No abstract' or
            not citation.get('pmid') or
            citation.get('pmid') == 'N/A'
        )

        if not needs_enrichment:
            return citation

        try:
            # Fetch document from database
            from bmlibrarian.database import get_db_manager
            db_manager = get_db_manager()

            with db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT
                            d.id, d.title, d.abstract, d.authors,
                            d.journal, d.pub_year, d.external_id, d.doi
                        FROM document d
                        WHERE d.id = %s
                    """, (citation.get('document_id'),))
                    row = cur.fetchone()

                    if row:
                        # Update missing fields
                        enriched = citation.copy()
                        if not enriched.get('abstract') or enriched['abstract'] == 'No abstract':
                            enriched['abstract'] = row[2] or 'No abstract available'
                        if not enriched.get('pmid') or enriched['pmid'] == 'N/A':
                            enriched['pmid'] = row[6] or 'N/A'
                        if not enriched.get('doi'):
                            enriched['doi'] = row[7] or ''
                        if not enriched.get('title'):
                            enriched['title'] = row[1] or 'No title'
                        if not enriched.get('authors'):
                            enriched['authors'] = row[3] or 'Unknown authors'
                        if not enriched.get('journal'):
                            enriched['journal'] = row[4] or 'Unknown journal'
                        if not enriched.get('pub_year'):
                            enriched['pub_year'] = row[5] or 'N/A'

                        return enriched

        except Exception as e:
            print(f"Warning: Failed to enrich citation from database: {e}")
            import traceback
            traceback.print_exc()

        return citation

    def clear(self):
        """Clear all citations."""
        self.set_citations([])
