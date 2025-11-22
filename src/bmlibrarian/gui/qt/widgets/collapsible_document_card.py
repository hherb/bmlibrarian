"""
Collapsible document card widget for BMLibrarian Qt GUI.

Displays document information with collapsible details - collapsed state shows
title + score tag, expanded state shows full metadata, AI reasoning, and abstract.

Layout when expanded:
1. Title + score badge (header row) - pale blue background
2. Author / Journal / DOI / ID (single metadata line) - pale blue background
3. AI reasoning (if present) - pale green/orange background, max 10 lines then scrollable
4. Abstract - max 10 lines then scrollable
5. PDF buttons row
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QMenu
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from typing import Optional, Dict, Any, List
import logging

from .card_utils import (
    validate_document_data,
    format_authors,
    html_escape
)
from ..resources.styles import get_font_scale
from ..resources.constants import DocumentCardColors, DefaultLimits
from ..core.document_receiver_registry import DocumentReceiverRegistry
from ..core.event_bus import EventBus

logger = logging.getLogger(__name__)


# ============================================================================
# Configuration Constants
# ============================================================================

# Layout constants
CARD_SPACING = 4             # Spacing between card elements (reduced for compactness)
HEADER_SPACING = 8           # Spacing in header row

# Score thresholds for color coding
SCORE_THRESHOLD_HIGH = 4.0   # Threshold for high relevance (green)
SCORE_THRESHOLD_MEDIUM = 2.5 # Threshold for medium relevance (blue)

# Border widths
BORDER_WIDTH_COLLAPSED = 3   # Left border width when collapsed
BORDER_WIDTH_EXPANDED = 2    # Border width when expanded

# Theme colors (should match application theme)
COLOR_HIGH_SCORE = "#27ae60"      # Green for high relevance scores
COLOR_MEDIUM_SCORE = "#3498db"    # Blue for medium relevance scores
COLOR_LOW_SCORE = "#95a5a6"       # Gray for low relevance scores
COLOR_BORDER_ACCENT = "#3498db"   # Blue accent for borders
COLOR_BORDER_ACCENT_HOVER = "#2980b9"  # Darker blue on hover
COLOR_BACKGROUND_COLLAPSED = "#f8f9fa"  # Light gray background
COLOR_BACKGROUND_COLLAPSED_HOVER = "#e9ecef"  # Slightly darker on hover
COLOR_BACKGROUND_EXPANDED = "#ffffff"  # White background when expanded
COLOR_BACKGROUND_EXPANDED_HOVER = "#f8f9fa"  # Light gray on hover
COLOR_BORDER_NEUTRAL = "#dee2e6"  # Neutral border color
COLOR_TEXT_SECONDARY = "#555"     # Secondary text color


class CollapsibleDocumentCard(QFrame):
    """
    Collapsible card widget for displaying document information.

    Collapsed: Shows title + score/tag in one line
    Expanded: Shows full metadata, AI reasoning, and abstract in compact layout

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

        # Get DPI scale
        self.scale = get_font_scale()
        s = self.scale

        # Validate and store document data
        self.document_data = validate_document_data(document_data)
        self._is_expanded = False

        # Configure frame
        self.setFrameShape(QFrame.StyledPanel)
        self.setObjectName("collapsibleDocumentCard")
        self.setCursor(Qt.PointingHandCursor)

        # Setup context menu support
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        # Create layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)  # No margins - sections have their own
        self.main_layout.setSpacing(0)  # No spacing - sections manage their own

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

        # Title
        title = self.document_data.get("title", "Untitled")
        self.title_label = QLabel(f"<b>{html_escape(title)}</b>")
        self.title_label.setObjectName("title")
        self.title_label.setWordWrap(False)  # No wrap when collapsed
        self.title_label.setTextFormat(Qt.RichText)
        self.title_label.setMinimumWidth(s['control_width_large'])
        title_row.addWidget(self.title_label, stretch=1)

        # Score badge
        self.score_tag = self._create_score_tag()
        if self.score_tag:
            title_row.addWidget(self.score_tag)

        header_section_layout.addLayout(title_row)

        # Row 2: Metadata line (authors / journal / year / DOI / ID)
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
        Create single-line metadata display (authors / journal (year) / DOI: xxx | ID: xxx).

        Returns:
            QLabel with formatted metadata or None if no metadata available
        """
        s = self.scale
        parts: List[str] = []

        # Authors (abbreviated)
        authors = format_authors(
            self.document_data.get("authors"),
            max_authors=2,  # More compact
            et_al=True
        )
        if authors and authors != "Unknown authors":
            parts.append(f"<i>{html_escape(authors)}</i>")

        # Journal and year
        journal = self.document_data.get("journal")
        year = self.document_data.get("year")
        if journal and year:
            parts.append(f"{html_escape(journal)} ({year})")
        elif journal:
            parts.append(html_escape(journal))
        elif year:
            parts.append(f"({year})")

        # DOI
        doi = self.document_data.get("doi")
        if doi:
            parts.append(f"DOI: {html_escape(doi)}")

        # Document ID
        doc_id = self.document_data.get("document_id") or self.document_data.get("id")
        if doc_id:
            parts.append(f"ID: {doc_id}")

        # PMID
        pmid = self.document_data.get("pmid")
        if pmid:
            parts.append(f"PMID: {pmid}")

        if not parts:
            return None

        metadata_text = " | ".join(parts)
        label = QLabel(metadata_text)
        label.setObjectName("metadataLine")
        label.setTextFormat(Qt.RichText)
        label.setStyleSheet(f"""
            QLabel {{
                color: {DocumentCardColors.METADATA_TEXT};
                font-size: {s['font_tiny']}pt;
            }}
        """)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        return label

    def _create_score_tag(self) -> Optional[QLabel]:
        """
        Create score tag badge.

        Returns:
            QLabel with formatted score, or None if no score available
        """
        s = self.scale

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
        tag.setAlignment(Qt.AlignCenter)
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

        # AI Reasoning section (if available)
        ai_reasoning = self.document_data.get("ai_reasoning") or self.document_data.get("reasoning")
        if ai_reasoning:
            self._create_ai_reasoning_section(ai_reasoning)

        # Abstract section (if available)
        abstract = self.document_data.get("abstract")
        if abstract:
            self._create_abstract_section(abstract)

        self.main_layout.addWidget(self.details_widget)

    def _create_ai_reasoning_section(self, reasoning: str):
        """
        Create AI reasoning section with pale green/orange background.

        Args:
            reasoning: AI reasoning text
        """
        s = self.scale

        # Determine background color based on content (warning indicators)
        warning_keywords = ['contradict', 'negate', 'warn', 'caution', 'however',
                           'limitation', 'conflict', 'dispute', 'oppose', 'disagree']
        is_warning = any(kw in reasoning.lower() for kw in warning_keywords)
        bg_color = DocumentCardColors.AI_REASONING_WARNING_BG if is_warning else DocumentCardColors.AI_REASONING_POSITIVE_BG

        # Create label with prefix on same line
        display_text = f"AI reasoning: {reasoning}"
        ai_label = QLabel(display_text)
        ai_label.setWordWrap(True)
        ai_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        ai_label.setStyleSheet(f"""
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
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setMaximumHeight(max_height)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setStyleSheet(f"""
            QScrollArea {{
                background-color: {bg_color};
                border: 1px solid {bg_color};
                border-radius: {s['radius_tiny']}px;
            }}
        """)
        scroll_area.setWidget(ai_label)

        self.details_layout.addWidget(scroll_area)

    def _create_abstract_section(self, abstract: str):
        """
        Create abstract section with scrollable overflow.

        Args:
            abstract: Abstract text
        """
        s = self.scale

        # Create label with prefix on same line
        display_text = f"Abstract: {abstract}"
        abstract_label = QLabel(display_text)
        abstract_label.setWordWrap(True)
        abstract_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
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
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setMaximumHeight(max_height)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setStyleSheet(f"""
            QScrollArea {{
                background-color: {DocumentCardColors.ABSTRACT_BG};
                border: 1px solid #eee;
                border-radius: {s['radius_tiny']}px;
            }}
        """)
        scroll_area.setWidget(abstract_label)

        self.details_layout.addWidget(scroll_area)

    def _apply_collapsed_style(self):
        """Apply styling for collapsed state."""
        s = self.scale

        self.setStyleSheet(f"""
            QFrame#collapsibleDocumentCard {{
                background-color: {COLOR_BACKGROUND_COLLAPSED};
                border: 1px solid {COLOR_BORDER_NEUTRAL};
                border-left: {BORDER_WIDTH_COLLAPSED}px solid {COLOR_BORDER_ACCENT};
                border-radius: {s['radius_tiny']}px;
            }}
            QFrame#collapsibleDocumentCard:hover {{
                background-color: {COLOR_BACKGROUND_COLLAPSED_HOVER};
                border-left: {BORDER_WIDTH_COLLAPSED}px solid {COLOR_BORDER_ACCENT_HOVER};
            }}
        """)

    def _apply_expanded_style(self):
        """Apply styling for expanded state."""
        s = self.scale

        self.setStyleSheet(f"""
            QFrame#collapsibleDocumentCard {{
                background-color: {COLOR_BACKGROUND_EXPANDED};
                border: {BORDER_WIDTH_EXPANDED}px solid {COLOR_BORDER_ACCENT};
                border-radius: {s['radius_tiny']}px;
            }}
            QFrame#collapsibleDocumentCard:hover {{
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
        if event.button() == Qt.LeftButton:
            # Only toggle if click is in header section (not in details)
            click_pos = event.position().toPoint()
            header_rect = self.header_section.geometry()
            if header_rect.contains(click_pos):
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
            # Find title row layout and add new tag
            header_layout = self.header_section.layout()
            if header_layout and header_layout.count() > 0:
                title_row = header_layout.itemAt(0)
                if title_row and title_row.layout():
                    title_row.layout().addWidget(self.score_tag)

    def _show_context_menu(self, position):
        """
        Show context menu with "Send to" submenu for registered document receivers.

        Args:
            position: Position where context menu was requested
        """
        # Get available document receivers
        registry = DocumentReceiverRegistry()
        receivers = registry.get_available_receivers(self.document_data)

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
        success = registry.send_document(receiver_id, self.document_data)

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
