"""
Citation card widget for BMLibrarian Qt GUI.

Specialized collapsible card for displaying citations with passage highlighting in abstracts.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
)
from PySide6.QtCore import Qt, Signal
from typing import Optional, Dict, Any
import re

from .card_utils import (
    html_escape
)


class CitationCard(QFrame):
    """
    Collapsible card widget for displaying citations with passage highlighting.

    Collapsed: Shows title, authors, year, relevance score
    Expanded: Shows summary + abstract with highlighted passage

    Signals:
        clicked: Emitted when card header is clicked (toggles expansion)
        expanded: Emitted when card is expanded
        collapsed: Emitted when card is collapsed
    """

    # Signals
    clicked = Signal(dict)
    expanded = Signal()
    collapsed = Signal()

    # Font sizes (consistent with research_tab)
    CARD_TITLE_FONT_SIZE = 11
    CARD_SUBTITLE_FONT_SIZE = 10
    CARD_BODY_FONT_SIZE = 10
    CARD_LABEL_FONT_SIZE = 9

    # Colors
    COLOR_PRIMARY_BLUE = "#1976D2"
    COLOR_TEXT_GREY = "#666666"
    COLOR_BORDER_GREY = "#dee2e6"
    COLOR_BORDER_ACCENT = "#3498db"
    COLOR_BORDER_ACCENT_HOVER = "#2980b9"
    COLOR_BACKGROUND_COLLAPSED = "#f8f9fa"
    COLOR_BACKGROUND_COLLAPSED_HOVER = "#e9ecef"
    COLOR_BACKGROUND_WHITE = "#ffffff"
    COLOR_SUMMARY_BG = "#e8f5e9"
    COLOR_SUMMARY_BORDER = "#c8e6c9"
    COLOR_ABSTRACT_BG = "#f5f5f5"
    COLOR_ABSTRACT_BORDER = "#ddd"
    COLOR_PASSAGE_BG = "#FFD54F"

    def __init__(
        self,
        citation_data: Dict[str, Any],
        index: int = 1,
        parent: Optional[QWidget] = None
    ):
        """
        Initialize citation card.

        Args:
            citation_data: Dictionary or citation object containing citation information
            index: Citation number (for display)
            parent: Optional parent widget
        """
        super().__init__(parent)

        # Convert citation object to dict if needed (for compatibility with BMLibrarian citation objects)
        if hasattr(citation_data, '__dict__'):
            # It's an object, convert to dict
            self.citation_data = {
                'document_title': getattr(citation_data, 'document_title', ''),
                'authors': getattr(citation_data, 'authors', []),
                'publication_date': getattr(citation_data, 'publication_date', ''),
                'publication': getattr(citation_data, 'publication', ''),
                'relevance_score': getattr(citation_data, 'relevance_score', 0),
                'summary': getattr(citation_data, 'summary', ''),
                'abstract': getattr(citation_data, 'abstract', None),
                'passage': getattr(citation_data, 'passage', ''),
            }
        else:
            # It's already a dict
            self.citation_data = citation_data

        self.index = index
        self._is_expanded = False

        # Configure frame
        self.setFrameShape(QFrame.Shape.Box)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # Create layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 2)
        main_layout.setSpacing(0)

        # Create header (always visible)
        self.header = self._create_header()
        main_layout.addWidget(self.header)

        # Create details section (collapsible)
        self.details = self._create_details()
        self.details.setVisible(False)
        main_layout.addWidget(self.details)

        # Set up click handler
        self.header.mousePressEvent = lambda event: self._toggle_expansion()

    def _create_header(self) -> QFrame:
        """Create the header section (always visible)."""
        header = QFrame()
        header.setStyleSheet(f"""
            QFrame {{
                background-color: {self.COLOR_BACKGROUND_COLLAPSED};
                border: 1px solid {self.COLOR_BORDER_GREY};
                border-left: 4px solid {self.COLOR_BORDER_ACCENT};
                border-radius: 4px;
                padding: 8px;
            }}
            QFrame:hover {{
                background-color: {self.COLOR_BACKGROUND_COLLAPSED_HOVER};
                border-left: 4px solid {self.COLOR_BORDER_ACCENT_HOVER};
            }}
        """)

        header_layout = QVBoxLayout(header)
        header_layout.setSpacing(4)
        header_layout.setContentsMargins(6, 6, 6, 6)

        # Title row with relevance badge
        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        title = self.citation_data.get('document_title', self.citation_data.get('title', 'Untitled Document'))
        # Truncate long titles
        if len(title) > 80:
            title = title[:77] + "..."

        title_label = QLabel(f"<b>{self.index}. {html_escape(title)}</b>")
        title_label.setWordWrap(True)
        title_label.setStyleSheet(f"color: {self.COLOR_PRIMARY_BLUE}; font-size: {self.CARD_TITLE_FONT_SIZE}pt;")
        title_row.addWidget(title_label, 1)

        # Relevance score badge
        relevance_score = self.citation_data.get('relevance_score', 0)
        if relevance_score:
            score_badge = QLabel(f"{relevance_score:.2f}")
            score_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            score_badge.setFixedSize(50, 24)
            score_badge.setStyleSheet(f"""
                QLabel {{
                    background-color: #4CAF50;
                    color: white;
                    font-size: {self.CARD_LABEL_FONT_SIZE}pt;
                    font-weight: bold;
                    border-radius: 12px;
                    padding: 2px 6px;
                }}
            """)
            title_row.addWidget(score_badge)

        header_layout.addLayout(title_row)

        # Subtitle row (authors and publication info)
        authors = self.citation_data.get('authors', [])
        if isinstance(authors, list):
            if len(authors) > 2:
                authors_str = ', '.join(authors[:2]) + ' et al.'
            elif authors:
                authors_str = ', '.join(authors)
            else:
                authors_str = 'Unknown authors'
        else:
            authors_str = str(authors) if authors else 'Unknown authors'

        # Extract year from publication_date
        publication_date = self.citation_data.get('publication_date', '')
        if publication_date and publication_date != 'Unknown':
            year_str = str(publication_date)[:4] if len(str(publication_date)) >= 4 else 'Unknown year'
        else:
            year_str = 'Unknown year'

        publication = self.citation_data.get('publication', '')
        pub_info = f"{publication} • {year_str}" if publication else year_str

        subtitle = f"{authors_str} | {pub_info}"
        subtitle_label = QLabel(subtitle)
        subtitle_label.setWordWrap(True)
        subtitle_label.setStyleSheet(f"color: {self.COLOR_TEXT_GREY}; font-size: {self.CARD_SUBTITLE_FONT_SIZE}pt;")
        header_layout.addWidget(subtitle_label)

        return header

    def _create_details(self) -> QFrame:
        """Create the details section (collapsible)."""
        details = QFrame()
        details.setStyleSheet(f"""
            QFrame {{
                background-color: {self.COLOR_BACKGROUND_WHITE};
                border: 1px solid {self.COLOR_BORDER_GREY};
                border-top: none;
                border-radius: 0 0 4px 4px;
                padding: 10px;
            }}
        """)

        self.details_layout = QVBoxLayout(details)
        self.details_layout.setSpacing(8)
        self.details_layout.setContentsMargins(10, 10, 10, 10)

        # Summary section
        summary = self.citation_data.get('summary', '')
        if summary:
            summary_container = self._create_summary_section(summary)
            self.details_layout.addWidget(summary_container)

        # Abstract with highlighted passage
        abstract = self.citation_data.get('abstract')
        passage = self.citation_data.get('passage', '')

        if abstract and passage:
            abstract_container = self._create_abstract_with_highlight(abstract, passage)
            self.details_layout.addWidget(abstract_container)
        elif passage:
            # Fallback: just show the passage
            passage_container = self._create_passage_only(passage)
            self.details_layout.addWidget(passage_container)

        return details

    def _create_summary_section(self, summary: str) -> QFrame:
        """Create the summary section."""
        summary_container = QFrame()
        summary_container.setStyleSheet(f"""
            QFrame {{
                background-color: {self.COLOR_SUMMARY_BG};
                border: 1px solid {self.COLOR_SUMMARY_BORDER};
                border-radius: 3px;
                padding: 8px;
            }}
        """)
        summary_layout = QVBoxLayout(summary_container)
        summary_layout.setContentsMargins(8, 8, 8, 8)
        summary_layout.setSpacing(5)

        summary_title = QLabel("<b>Summary:</b>")
        summary_title.setStyleSheet(f"font-size: {self.CARD_LABEL_FONT_SIZE}pt; background-color: transparent; border: none;")
        summary_layout.addWidget(summary_title)

        summary_text = QLabel(html_escape(summary))
        summary_text.setWordWrap(True)
        summary_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        summary_text.setStyleSheet(f"color: #333; font-size: {self.CARD_BODY_FONT_SIZE}pt; background-color: transparent; border: none;")
        summary_layout.addWidget(summary_text)

        return summary_container

    def _create_abstract_with_highlight(self, abstract: str, passage: str) -> QFrame:
        """Create abstract section with highlighted passage."""
        abstract_container = QFrame()
        abstract_container.setStyleSheet(f"""
            QFrame {{
                background-color: {self.COLOR_ABSTRACT_BG};
                border: 1px solid {self.COLOR_ABSTRACT_BORDER};
                border-radius: 3px;
                padding: 8px;
            }}
        """)
        abstract_layout = QVBoxLayout(abstract_container)
        abstract_layout.setContentsMargins(8, 8, 8, 8)
        abstract_layout.setSpacing(5)

        abstract_title = QLabel("<b>Abstract with Highlighted Citation:</b>")
        abstract_title.setStyleSheet(f"font-size: {self.CARD_LABEL_FONT_SIZE}pt; background-color: transparent; border: none;")
        abstract_layout.addWidget(abstract_title)

        # Create highlighted widget
        highlighted_widget = self._create_highlighted_abstract_widget(abstract, passage)
        abstract_layout.addWidget(highlighted_widget)

        return abstract_container

    def _create_highlighted_abstract_widget(self, abstract: str, passage: str) -> QWidget:
        """Create widget showing abstract with passage highlighted."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        if not abstract or not passage:
            label = QLabel(abstract or "No abstract available")
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            label.setStyleSheet(f"font-size: {self.CARD_BODY_FONT_SIZE}pt; color: #333;")
            layout.addWidget(label)
            return container

        # Clean up passage for matching (remove extra whitespace)
        clean_passage = ' '.join(passage.split())

        # Try to find exact match (case-insensitive)
        pattern = re.compile(re.escape(clean_passage), re.IGNORECASE)
        match = pattern.search(abstract)

        if match:
            # Exact match - create highlighted text
            start, end = match.span()

            # Build HTML with highlighted section
            before = html_escape(abstract[:start])
            highlighted = html_escape(abstract[start:end])
            after = html_escape(abstract[end:])

            html = f"""
            <style>
                .abstract-text {{ font-size: {self.CARD_BODY_FONT_SIZE}pt; color: #333; line-height: 1.4; }}
                .highlight {{ background-color: {self.COLOR_PASSAGE_BG}; font-weight: 600; padding: 2px 4px; }}
            </style>
            <div class="abstract-text">
                {before}<span class="highlight">📌 {highlighted} 📌</span>{after}
            </div>
            """

            label = QLabel(html)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(label)

        else:
            # Try fuzzy matching with first 10 words
            passage_start = ' '.join(passage.split()[:10])
            fuzzy_pattern = re.compile(re.escape(passage_start), re.IGNORECASE)
            fuzzy_match = fuzzy_pattern.search(abstract)

            if fuzzy_match:
                # Partial match
                start = fuzzy_match.span()[0]
                end = min(start + len(clean_passage), len(abstract))

                warning_label = QLabel("⚠️ Approximate match only")
                warning_label.setStyleSheet(f"font-size: {self.CARD_LABEL_FONT_SIZE}pt; color: #F57C00; font-style: italic;")
                layout.addWidget(warning_label)

                before = html_escape(abstract[:start])
                highlighted = html_escape(abstract[start:end])
                after = html_escape(abstract[end:])

                html = f"""
                <style>
                    .abstract-text {{ font-size: {self.CARD_BODY_FONT_SIZE}pt; color: #333; line-height: 1.4; }}
                    .highlight {{ background-color: #FFB74D; font-weight: 600; padding: 2px 4px; }}
                </style>
                <div class="abstract-text">
                    {before}<span class="highlight">⚠️ {highlighted} ⚠️</span>{after}
                </div>
                """

                label = QLabel(html)
                label.setWordWrap(True)
                label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                layout.addWidget(label)

            else:
                # No match - show separately
                passage_frame = QFrame()
                passage_frame.setStyleSheet(f"""
                    QFrame {{
                        background-color: {self.COLOR_PASSAGE_BG};
                        border-radius: 3px;
                        padding: 8px;
                    }}
                """)
                passage_layout = QVBoxLayout(passage_frame)
                passage_layout.setContentsMargins(8, 8, 8, 8)

                passage_label = QLabel(f"📌 Cited Passage:\n{html_escape(passage)}")
                passage_label.setWordWrap(True)
                passage_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                passage_label.setStyleSheet(f"font-size: {self.CARD_BODY_FONT_SIZE}pt; font-weight: 600; background-color: transparent; border: none;")
                passage_layout.addWidget(passage_label)

                layout.addWidget(passage_frame)

                abstract_title = QLabel("Full Abstract:")
                abstract_title.setStyleSheet(f"font-size: {self.CARD_LABEL_FONT_SIZE}pt; font-weight: bold; margin-top: 5px;")
                layout.addWidget(abstract_title)

                abstract_label = QLabel(html_escape(abstract))
                abstract_label.setWordWrap(True)
                abstract_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                abstract_label.setStyleSheet(f"font-size: {self.CARD_BODY_FONT_SIZE}pt; color: #333;")
                layout.addWidget(abstract_label)

        return container

    def _create_passage_only(self, passage: str) -> QFrame:
        """Create section showing only the passage (fallback when no abstract)."""
        passage_container = QFrame()
        passage_container.setStyleSheet(f"""
            QFrame {{
                background-color: {self.COLOR_ABSTRACT_BG};
                border: 1px solid {self.COLOR_ABSTRACT_BORDER};
                border-radius: 3px;
                padding: 10px;
            }}
        """)
        passage_layout = QVBoxLayout(passage_container)
        passage_layout.setContentsMargins(10, 10, 10, 10)
        passage_layout.setSpacing(5)

        passage_title = QLabel("<b>Cited Passage:</b>")
        passage_title.setStyleSheet(f"font-size: {self.CARD_LABEL_FONT_SIZE}pt; background-color: transparent; border: none;")
        passage_layout.addWidget(passage_title)

        passage_text = QLabel(html_escape(passage))
        passage_text.setWordWrap(True)
        passage_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        passage_text.setStyleSheet(f"color: #333; font-size: {self.CARD_BODY_FONT_SIZE}pt; background-color: transparent; border: none;")
        passage_layout.addWidget(passage_text)

        return passage_container

    def _toggle_expansion(self):
        """Toggle card expansion state."""
        self._is_expanded = not self._is_expanded
        self.details.setVisible(self._is_expanded)

        if self._is_expanded:
            self.expanded.emit()
        else:
            self.collapsed.emit()

    @property
    def is_expanded(self) -> bool:
        """Check if card is currently expanded."""
        return self._is_expanded

    def expand(self):
        """Expand the card."""
        if not self._is_expanded:
            self._toggle_expansion()

    def collapse(self):
        """Collapse the card."""
        if self._is_expanded:
            self._toggle_expansion()

    # Keep backward compatibility with old API
    def get_document_id(self) -> Optional[int]:
        """Get the document ID."""
        return self.citation_data.get("document_id")

    def get_title(self) -> str:
        """Get the document title."""
        return self.citation_data.get("document_title", self.citation_data.get("title", "Untitled"))

    def get_passage(self) -> str:
        """Get the citation passage/quote."""
        return self.citation_data.get("passage", self.citation_data.get("quote", ""))
