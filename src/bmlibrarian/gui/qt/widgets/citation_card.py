"""
Citation card widget for BMLibrarian Qt GUI.

Specialized collapsible card for displaying citations with passage highlighting in abstracts.
Styled consistently with CollapsibleDocumentCard layout.

Layout when expanded:
1. Title + score badge (header row) - pale blue background
2. Author / Journal / Year (single metadata line) - pale blue background
3. Summary (if present) - pale green background, max 10 lines then scrollable
4. Abstract with highlighted passage - max 10 lines then scrollable
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QMenu
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from typing import Optional, Dict, Any, List
import re
import logging

from .card_utils import html_escape
from ..resources.styles import get_font_scale
from ..resources.constants import DocumentCardColors, DefaultLimits
from ..core.document_receiver_registry import DocumentReceiverRegistry
from ..core.event_bus import EventBus

logger = logging.getLogger(__name__)


# ============================================================================
# Configuration Constants
# ============================================================================

# Score thresholds for color coding
SCORE_THRESHOLD_HIGH = 4.0
SCORE_THRESHOLD_MEDIUM = 2.5

# Theme colors
COLOR_HIGH_SCORE = "#27ae60"
COLOR_MEDIUM_SCORE = "#3498db"
COLOR_LOW_SCORE = "#95a5a6"
COLOR_BORDER_ACCENT = "#3498db"
COLOR_BORDER_ACCENT_HOVER = "#2980b9"
COLOR_BACKGROUND_COLLAPSED = "#f8f9fa"
COLOR_BACKGROUND_COLLAPSED_HOVER = "#e9ecef"
COLOR_BACKGROUND_EXPANDED = "#ffffff"
COLOR_BACKGROUND_EXPANDED_HOVER = "#f8f9fa"
COLOR_BORDER_NEUTRAL = "#dee2e6"

# Highlight color for passages
COLOR_PASSAGE_BG = "#FFD54F"
COLOR_PASSAGE_APPROX_BG = "#FFB74D"

# Border widths
BORDER_WIDTH_COLLAPSED = 3
BORDER_WIDTH_EXPANDED = 2


class CitationCard(QFrame):
    """
    Collapsible card widget for displaying citations with passage highlighting.

    Collapsed: Shows title + score in one line
    Expanded: Shows metadata, summary, abstract with highlighted passage

    Signals:
        clicked: Emitted when card header is clicked (toggles expansion)
        expanded: Emitted when card is expanded
        collapsed: Emitted when card is collapsed
    """

    # Signals
    clicked = Signal(dict)
    expanded = Signal()
    collapsed = Signal()

    def __init__(
        self,
        citation_data: Dict[str, Any],
        index: int = 1,
        parent: Optional[QWidget] = None,
        pdf_button_widget: Optional[QWidget] = None
    ):
        """
        Initialize citation card.

        Args:
            citation_data: Dictionary or citation object containing citation information
            index: Citation number (for display)
            parent: Optional parent widget
            pdf_button_widget: Optional PDF button widget to add to details section
        """
        super().__init__(parent)

        # Get DPI-aware scale
        self.scale = get_font_scale()
        s = self.scale

        # Convert citation object to dict if needed
        if hasattr(citation_data, '__dict__'):
            self.citation_data = {
                'document_title': getattr(citation_data, 'document_title', ''),
                'document_id': getattr(citation_data, 'document_id', None),
                'authors': getattr(citation_data, 'authors', []),
                'publication_date': getattr(citation_data, 'publication_date', ''),
                'publication': getattr(citation_data, 'publication', ''),
                'relevance_score': getattr(citation_data, 'relevance_score', 0),
                'summary': getattr(citation_data, 'summary', ''),
                'abstract': getattr(citation_data, 'abstract', None),
                'passage': getattr(citation_data, 'passage', ''),
                'pdf_url': getattr(citation_data, 'pdf_url', None),
                'pdf_path': getattr(citation_data, 'pdf_path', None),
            }
        else:
            self.citation_data = citation_data

        self.index = index
        self._is_expanded = False
        self._pdf_button_widget = pdf_button_widget

        # Configure frame
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setObjectName("citationCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # Setup context menu support
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        # Create layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Create header section (title + metadata) with pale blue background
        self._create_header_section()

        # Create details section (hidden by default)
        self._create_details()
        self.details_widget.setVisible(False)

        # Style the card
        self._apply_collapsed_style()

    def _create_header_section(self):
        """Create the header section with title, score badge, and metadata on pale blue background."""
        s = self.scale

        # Header container with pale blue background
        self.header_section = QWidget()
        self.header_section.setObjectName("headerSection")
        header_section_layout = QVBoxLayout(self.header_section)
        header_section_layout.setContentsMargins(
            s['padding_medium'], s['padding_small'],
            s['padding_medium'], s['padding_small']
        )
        header_section_layout.setSpacing(s['spacing_tiny'])

        # Row 1: Title + Score badge
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(s['spacing_small'])

        # Title with index
        title = self.citation_data.get('document_title', self.citation_data.get('title', 'Untitled Document'))
        self.title_label = QLabel(f"<b>{self.index}. {html_escape(title)}</b>")
        self.title_label.setObjectName("title")
        self.title_label.setWordWrap(False)
        self.title_label.setTextFormat(Qt.TextFormat.RichText)
        self.title_label.setMinimumWidth(s['control_width_large'])
        title_row.addWidget(self.title_label, stretch=1)

        # Score badge
        self.score_tag = self._create_score_tag()
        if self.score_tag:
            title_row.addWidget(self.score_tag)

        header_section_layout.addLayout(title_row)

        # Row 2: Metadata line (authors / journal / year)
        self.metadata_label = self._create_metadata_line()
        if self.metadata_label:
            header_section_layout.addWidget(self.metadata_label)

        # Apply pale blue background
        self.header_section.setStyleSheet(f"""
            QWidget#headerSection {{
                background-color: {DocumentCardColors.HEADER_BG};
                border-radius: {s['radius_tiny']}px {s['radius_tiny']}px 0 0;
            }}
        """)

        self.main_layout.addWidget(self.header_section)

    def _create_metadata_line(self) -> Optional[QLabel]:
        """
        Create single-line metadata display (authors | journal (year)).

        Returns:
            QLabel with formatted metadata or None if no metadata available
        """
        s = self.scale
        parts: List[str] = []

        # Authors (abbreviated)
        authors = self.citation_data.get('authors', [])
        if isinstance(authors, list):
            if len(authors) > 2:
                authors_str = ', '.join(authors[:2]) + ' et al.'
            elif authors:
                authors_str = ', '.join(authors)
            else:
                authors_str = None
        else:
            authors_str = str(authors) if authors else None

        if authors_str:
            parts.append(f"<i>{html_escape(authors_str)}</i>")

        # Publication (journal) and year
        publication = self.citation_data.get('publication', '')
        publication_date = self.citation_data.get('publication_date', '')

        year_str = ''
        if publication_date and publication_date != 'Unknown':
            year_str = str(publication_date)[:4] if len(str(publication_date)) >= 4 else ''

        if publication and publication != 'Unknown journal':
            if year_str:
                parts.append(f"{html_escape(publication)} ({year_str})")
            else:
                parts.append(html_escape(publication))
        elif year_str:
            parts.append(f"({year_str})")

        if not parts:
            return None

        metadata_text = " | ".join(parts)
        label = QLabel(metadata_text)
        label.setObjectName("metadataLine")
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setStyleSheet(f"""
            QLabel {{
                color: {DocumentCardColors.METADATA_TEXT};
                font-size: {s['font_tiny']}pt;
            }}
        """)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        return label

    def _create_score_tag(self) -> Optional[QLabel]:
        """
        Create score tag badge.

        Returns:
            QLabel with formatted score, or None if no score available
        """
        s = self.scale

        score = self.citation_data.get('relevance_score')
        if score is None or score == 0:
            return None

        # Color code based on score magnitude
        if isinstance(score, (int, float)):
            score_val = float(score)
            if score_val >= SCORE_THRESHOLD_HIGH:
                color = COLOR_HIGH_SCORE
            elif score_val >= SCORE_THRESHOLD_MEDIUM:
                color = COLOR_MEDIUM_SCORE
            else:
                color = COLOR_LOW_SCORE
            tag = QLabel(f"<b>{score_val:.2f}</b>")
        else:
            color = COLOR_LOW_SCORE
            tag = QLabel(f"<b>{score}</b>")

        tag.setStyleSheet(f"""
            QLabel {{
                background-color: {color};
                color: white;
                padding: {s['padding_tiny']}px {s['padding_medium']}px;
                border-radius: {s['radius_medium']}px;
                font-size: {s['font_normal']}pt;
            }}
        """)
        tag.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tag.setFixedHeight(s['control_height_small'])
        tag.setMinimumWidth(s['control_width_tiny'])

        return tag

    def _create_details(self):
        """Create the details section (shown when expanded)."""
        s = self.scale

        self.details_widget = QWidget()
        self.details_layout = QVBoxLayout(self.details_widget)
        self.details_layout.setContentsMargins(
            s['padding_medium'], s['spacing_tiny'],
            s['padding_medium'], s['padding_small']
        )
        self.details_layout.setSpacing(s['spacing_tiny'])

        # Summary section (if available) - styled like AI reasoning
        summary = self.citation_data.get('summary', '')
        if summary:
            self._create_summary_section(summary)

        # Abstract with highlighted passage
        abstract = self.citation_data.get('abstract')
        passage = self.citation_data.get('passage', '')

        if abstract:
            self._create_abstract_section(abstract, passage)
        elif passage:
            self._create_passage_only_section(passage)

        # Add PDF button widget if provided
        if self._pdf_button_widget:
            self.details_layout.addWidget(self._pdf_button_widget)

        self.main_layout.addWidget(self.details_widget)

    def _create_summary_section(self, summary: str):
        """
        Create summary section with pale green background (like AI reasoning).
        Text box grows with content up to max height, then scrolls.

        Args:
            summary: Summary text
        """
        s = self.scale
        bg_color = DocumentCardColors.AI_REASONING_POSITIVE_BG

        # Create label with prefix on same line - "[AI Summary: text here]"
        display_text = f"AI Summary: {summary}"
        summary_label = QLabel(display_text)
        summary_label.setWordWrap(True)
        summary_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        summary_label.setStyleSheet(f"""
            QLabel {{
                background-color: {bg_color};
                border: 1px solid {bg_color};
                border-radius: {s['radius_tiny']}px;
                padding: {s['padding_small']}px;
                font-size: {s['font_small']}pt;
                color: {DocumentCardColors.AI_REASONING_TEXT};
            }}
        """)

        # Calculate max height based on line count
        line_height = s['base_line_height']
        max_height = line_height * DefaultLimits.AI_REASONING_MAX_LINES + s['padding_small'] * 2

        # Wrap in scroll area for overflow
        from PySide6.QtWidgets import QScrollArea
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setMaximumHeight(max_height)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setStyleSheet(f"""
            QScrollArea {{
                background-color: {bg_color};
                border: 1px solid {bg_color};
                border-radius: {s['radius_tiny']}px;
            }}
        """)
        scroll_area.setWidget(summary_label)

        self.details_layout.addWidget(scroll_area)

    def _create_abstract_section(self, abstract: str, passage: str):
        """
        Create abstract section with scrollable overflow and passage highlighting.
        Text box grows with content up to max height, then scrolls.

        Args:
            abstract: Abstract text
            passage: Passage to highlight
        """
        s = self.scale

        # Create highlighted content
        highlighted_html = self._create_highlighted_html(abstract, passage)

        # Create QLabel for HTML content with highlighting
        abstract_label = QLabel(highlighted_html)
        abstract_label.setWordWrap(True)
        abstract_label.setTextFormat(Qt.TextFormat.RichText)
        abstract_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        abstract_label.setStyleSheet(f"""
            QLabel {{
                background-color: {DocumentCardColors.ABSTRACT_BG};
                padding: {s['padding_small']}px;
                font-size: {s['font_small']}pt;
                color: {DocumentCardColors.ABSTRACT_TEXT};
            }}
        """)

        # Calculate max height based on line count
        line_height = s['base_line_height']
        max_height = line_height * DefaultLimits.ABSTRACT_MAX_LINES + s['padding_small'] * 2

        # Wrap in scroll area for overflow
        from PySide6.QtWidgets import QScrollArea
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setMaximumHeight(max_height)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setStyleSheet(f"""
            QScrollArea {{
                background-color: {DocumentCardColors.ABSTRACT_BG};
                border: 1px solid #eee;
                border-radius: {s['radius_tiny']}px;
            }}
        """)
        scroll_area.setWidget(abstract_label)

        self.details_layout.addWidget(scroll_area)

    def _create_highlighted_html(self, abstract: str, passage: str) -> str:
        """
        Create HTML with highlighted passage in abstract.

        Args:
            abstract: Full abstract text
            passage: Passage to highlight

        Returns:
            HTML string with highlighting
        """
        s = self.scale

        if not passage:
            return f"Abstract: {html_escape(abstract)}"

        # Clean up passage for matching
        clean_passage = ' '.join(passage.split())

        # Try exact match (case-insensitive)
        pattern = re.compile(re.escape(clean_passage), re.IGNORECASE)
        match = pattern.search(abstract)

        if match:
            start, end = match.span()
            before = html_escape(abstract[:start])
            highlighted = html_escape(abstract[start:end])
            after = html_escape(abstract[end:])

            return f"""Abstract: {before}<span style="background-color: {COLOR_PASSAGE_BG}; font-weight: 600; padding: 2px 4px;">📌 {highlighted} 📌</span>{after}"""

        # Try fuzzy matching with first 10 words
        passage_start = ' '.join(passage.split()[:10])
        fuzzy_pattern = re.compile(re.escape(passage_start), re.IGNORECASE)
        fuzzy_match = fuzzy_pattern.search(abstract)

        if fuzzy_match:
            start = fuzzy_match.span()[0]
            end = min(start + len(clean_passage), len(abstract))

            before = html_escape(abstract[:start])
            highlighted = html_escape(abstract[start:end])
            after = html_escape(abstract[end:])

            return f"""Abstract: ⚠️ <i>Approximate match</i><br>{before}<span style="background-color: {COLOR_PASSAGE_APPROX_BG}; font-weight: 600; padding: 2px 4px;">⚠️ {highlighted} ⚠️</span>{after}"""

        # No match - show passage separately then abstract
        return f"""Abstract: <span style="background-color: {COLOR_PASSAGE_BG}; font-weight: 600; padding: 2px 4px; display: block; margin-bottom: 8px;">📌 Cited passage: {html_escape(passage)}</span><br>{html_escape(abstract)}"""

    def _create_passage_only_section(self, passage: str):
        """
        Create section showing only the passage (fallback when no abstract).
        Text box grows with content up to max height, then scrolls.

        Args:
            passage: Passage text
        """
        s = self.scale

        # Create label with prefix on same line
        display_text = f"📌 Cited passage: {passage}"
        passage_label = QLabel(display_text)
        passage_label.setWordWrap(True)
        passage_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        passage_label.setStyleSheet(f"""
            QLabel {{
                background-color: {COLOR_PASSAGE_BG};
                border: 1px solid {COLOR_PASSAGE_BG};
                border-radius: {s['radius_tiny']}px;
                padding: {s['padding_small']}px;
                font-size: {s['font_small']}pt;
                color: #333;
                font-weight: 600;
            }}
        """)

        # Calculate max height based on line count
        line_height = s['base_line_height']
        max_height = line_height * DefaultLimits.ABSTRACT_MAX_LINES + s['padding_small'] * 2

        # Wrap in scroll area for overflow
        from PySide6.QtWidgets import QScrollArea
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setMaximumHeight(max_height)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setStyleSheet(f"""
            QScrollArea {{
                background-color: {COLOR_PASSAGE_BG};
                border: 1px solid {COLOR_PASSAGE_BG};
                border-radius: {s['radius_tiny']}px;
            }}
        """)
        scroll_area.setWidget(passage_label)

        self.details_layout.addWidget(scroll_area)

    def _apply_collapsed_style(self):
        """Apply styling for collapsed state."""
        s = self.scale

        self.setStyleSheet(f"""
            QFrame#citationCard {{
                background-color: {COLOR_BACKGROUND_COLLAPSED};
                border: 1px solid {COLOR_BORDER_NEUTRAL};
                border-left: {BORDER_WIDTH_COLLAPSED}px solid {COLOR_BORDER_ACCENT};
                border-radius: {s['radius_tiny']}px;
            }}
            QFrame#citationCard:hover {{
                background-color: {COLOR_BACKGROUND_COLLAPSED_HOVER};
                border-left: {BORDER_WIDTH_COLLAPSED}px solid {COLOR_BORDER_ACCENT_HOVER};
            }}
        """)

    def _apply_expanded_style(self):
        """Apply styling for expanded state."""
        s = self.scale

        self.setStyleSheet(f"""
            QFrame#citationCard {{
                background-color: {COLOR_BACKGROUND_EXPANDED};
                border: {BORDER_WIDTH_EXPANDED}px solid {COLOR_BORDER_ACCENT};
                border-radius: {s['radius_tiny']}px;
            }}
            QFrame#citationCard:hover {{
                background-color: {COLOR_BACKGROUND_EXPANDED_HOVER};
            }}
        """)

    def mousePressEvent(self, event):
        """
        Handle mouse press event to toggle expansion.
        Only toggle when clicking on the header section, not on details.

        Args:
            event: Mouse event
        """
        if event.button() == Qt.MouseButton.LeftButton:
            # Only toggle if click is in header section (not in details)
            click_pos = event.position().toPoint()
            header_rect = self.header_section.geometry()
            if header_rect.contains(click_pos):
                self._toggle_expansion()
        super().mousePressEvent(event)

    def _toggle_expansion(self):
        """Toggle card expansion state."""
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

        self.clicked.emit(self.citation_data)

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

    def get_document_id(self) -> Optional[int]:
        """Get the document ID."""
        return self.citation_data.get("document_id")

    def get_title(self) -> str:
        """Get the document title."""
        return self.citation_data.get("document_title", self.citation_data.get("title", "Untitled"))

    def get_passage(self) -> str:
        """Get the citation passage/quote."""
        return self.citation_data.get("passage", self.citation_data.get("quote", ""))

    def _show_context_menu(self, position):
        """
        Show context menu with "Send to" submenu for registered document receivers.

        Args:
            position: Position where context menu was requested
        """
        # Get available document receivers
        registry = DocumentReceiverRegistry()
        receivers = registry.get_available_receivers(self.citation_data)

        if not receivers:
            logger.debug("No document receivers available for context menu")
            return

        # Create context menu
        context_menu = QMenu(self)

        # Create "Send to" submenu
        send_to_menu = context_menu.addMenu("Send to")

        # Add action for each receiver
        for receiver in receivers:
            receiver_id = receiver.get_receiver_id()
            receiver_name = receiver.get_receiver_name()
            receiver_desc = receiver.get_receiver_description()

            action = QAction(receiver_name, send_to_menu)

            # Set tooltip if description available
            if receiver_desc:
                action.setToolTip(receiver_desc)

            # Connect to handler with receiver_id
            action.triggered.connect(
                lambda checked=False, rid=receiver_id: self._send_to_receiver(rid)
            )

            send_to_menu.addAction(action)

        # Show context menu at cursor position
        context_menu.exec(self.mapToGlobal(position))

    def _send_to_receiver(self, receiver_id: str):
        """
        Send this document to a specific receiver.

        Args:
            receiver_id: ID of the receiver to send document to
        """
        registry = DocumentReceiverRegistry()
        event_bus = EventBus()

        # Send document via registry
        success = registry.send_document(receiver_id, self.citation_data)

        if success:
            # Request navigation to the receiver's tab
            event_bus.request_navigation(receiver_id)
            logger.info(
                f"Sent document {self.get_document_id()} to receiver '{receiver_id}'"
            )
        else:
            logger.error(
                f"Failed to send document {self.get_document_id()} "
                f"to receiver '{receiver_id}'"
            )
