"""
PaperChecker Laboratory - Custom Widgets

Custom Qt widgets for the PaperChecker Laboratory.
Includes workflow step cards, citation display, verdict badges, and status indicators.
"""

import logging
from typing import Optional, Dict, List, Any

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QGroupBox, QApplication, QPushButton, QTextEdit, QSizePolicy,
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont

from bmlibrarian.gui.qt.resources.styles.dpi_scale import get_font_scale
from bmlibrarian.gui.qt.resources.styles.stylesheet_generator import get_stylesheet_generator

from .constants import (
    SPINNER_ANIMATION_INTERVAL_MS, SPINNER_FRAMES,
    PROGRESS_PENDING, PROGRESS_RUNNING, PROGRESS_COMPLETE, PROGRESS_ERROR,
    WORKFLOW_STEPS, COLOR_PRIMARY, COLOR_PRIMARY_LIGHT, COLOR_SUCCESS,
    COLOR_WARNING, COLOR_ERROR,
    COLOR_GREY_100, COLOR_GREY_200, COLOR_GREY_300, COLOR_GREY_600, COLOR_WHITE,
)
from .utils import (
    format_verdict_display, format_confidence_display, format_statement_type_display,
    format_score_badge, format_provenance_display, truncate_passage, truncate_title,
    format_document_metadata, extract_year_from_date,
)


logger = logging.getLogger(__name__)


class StatusSpinnerWidget(QWidget):
    """
    A status line widget with an animated spinner.

    Displays a single line of status text with an optional animated
    spinner to indicate work in progress.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize status spinner widget.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        self.scale = get_font_scale()
        self._frame_index = 0
        self._is_spinning = False

        self._setup_ui()
        self._setup_timer()

    def _setup_ui(self) -> None:
        """Setup widget UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self.scale['spacing_small'])

        # Spinner label (fixed width for consistent alignment)
        self._spinner_label = QLabel("")
        self._spinner_label.setFixedWidth(self.scale['char_width'] * 2)
        layout.addWidget(self._spinner_label)

        # Status text label
        self._status_label = QLabel("Ready")
        layout.addWidget(self._status_label, stretch=1)

    def _setup_timer(self) -> None:
        """Setup animation timer."""
        self._timer = QTimer(self)
        self._timer.setInterval(SPINNER_ANIMATION_INTERVAL_MS)
        self._timer.timeout.connect(self._animate_spinner)

    def _animate_spinner(self) -> None:
        """Advance spinner animation frame."""
        if self._is_spinning:
            self._spinner_label.setText(SPINNER_FRAMES[self._frame_index])
            self._frame_index = (self._frame_index + 1) % len(SPINNER_FRAMES)

    def set_status(self, text: str) -> None:
        """
        Set the status text.

        Args:
            text: Status message to display
        """
        self._status_label.setText(text)

    def start_spinner(self) -> None:
        """Start the spinner animation."""
        self._is_spinning = True
        self._frame_index = 0
        self._timer.start()

    def stop_spinner(self) -> None:
        """Stop the spinner animation."""
        self._is_spinning = False
        self._timer.stop()
        self._spinner_label.setText("")

    def set_complete(self, text: str) -> None:
        """
        Set status to complete state.

        Args:
            text: Completion message to display
        """
        self.stop_spinner()
        self._spinner_label.setText(PROGRESS_COMPLETE)
        self._status_label.setText(text)

    def set_error(self, text: str) -> None:
        """
        Set status to error state.

        Args:
            text: Error message to display
        """
        self.stop_spinner()
        self._spinner_label.setText(PROGRESS_ERROR)
        self._status_label.setText(text)

    def reset(self) -> None:
        """Reset to initial state."""
        self.stop_spinner()
        self._spinner_label.setText("")
        self._status_label.setText("Ready")


class WorkflowStepCard(QFrame):
    """
    A collapsible card widget displaying a single workflow step with expandable content.

    Shows step icon, name, and status. Visual state changes based on
    whether the step is pending, running, complete, or errored.

    The card is collapsible - click the header to expand/collapse content area.
    Content can be added dynamically as intermediate results are produced.

    Signals:
        clicked: Emitted when the header is clicked (toggle expand/collapse)
    """

    clicked = Signal()  # Emitted when header is clicked

    def __init__(
        self,
        step_index: int,
        step_name: str,
        parent: Optional[QWidget] = None
    ) -> None:
        """
        Initialize workflow step card.

        Args:
            step_index: Index of this step (0-based)
            step_name: Display name of the step
            parent: Parent widget
        """
        super().__init__(parent)

        self.step_index = step_index
        self.step_name = step_name
        self.scale = get_font_scale()
        self.styles = get_stylesheet_generator()
        self._status = "pending"
        self._expanded = False
        self._has_content = False

        self._setup_ui()
        self._update_style()

    def _setup_ui(self) -> None:
        """Setup card UI with header and collapsible content area."""
        self.setFrameShape(QFrame.StyledPanel)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header row (clickable)
        self._header_widget = QFrame()
        self._header_widget.setCursor(Qt.PointingHandCursor)
        header_layout = QHBoxLayout(self._header_widget)
        header_layout.setContentsMargins(
            self.scale['padding_medium'],
            self.scale['padding_small'],
            self.scale['padding_medium'],
            self.scale['padding_small']
        )
        header_layout.setSpacing(self.scale['spacing_medium'])

        # Step number
        self._number_label = QLabel(f"{self.step_index + 1}.")
        self._number_label.setFixedWidth(self.scale['char_width'] * 3)
        header_layout.addWidget(self._number_label)

        # Status icon
        self._icon_label = QLabel(PROGRESS_PENDING)
        self._icon_label.setFixedWidth(self.scale['char_width'] * 2)
        header_layout.addWidget(self._icon_label)

        # Step name
        self._name_label = QLabel(self.step_name)
        header_layout.addWidget(self._name_label, stretch=1)

        # Expand/collapse indicator (shows when content exists)
        self._expand_indicator = QLabel("")
        self._expand_indicator.setFixedWidth(self.scale['char_width'] * 2)
        header_layout.addWidget(self._expand_indicator)

        main_layout.addWidget(self._header_widget)

        # Content area (collapsible)
        self._content_widget = QFrame()
        self._content_widget.setVisible(False)
        content_layout = QVBoxLayout(self._content_widget)
        content_layout.setContentsMargins(
            self.scale['padding_large'],
            self.scale['padding_small'],
            self.scale['padding_medium'],
            self.scale['padding_medium']
        )
        content_layout.setSpacing(self.scale['spacing_small'])

        # Content text area (for displaying intermediate results)
        self._content_text = QTextEdit()
        self._content_text.setReadOnly(True)
        self._content_text.setMinimumHeight(self.scale['base_line_height'] * 3)
        self._content_text.setMaximumHeight(self.scale['base_line_height'] * 12)
        self._content_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        content_layout.addWidget(self._content_text)

        # Stats row (for counts, etc.)
        self._stats_layout = QHBoxLayout()
        self._stats_layout.setSpacing(self.scale['spacing_small'])
        self._stats_layout.addStretch()
        content_layout.addLayout(self._stats_layout)

        main_layout.addWidget(self._content_widget)

    def _update_style(self) -> None:
        """Update visual style based on status."""
        if self._status == "running":
            bg_color = COLOR_PRIMARY
            text_color = COLOR_WHITE
            content_bg = COLOR_PRIMARY_LIGHT if hasattr(self, '_content_widget') else COLOR_PRIMARY
            self._icon_label.setText(PROGRESS_RUNNING)
        elif self._status == "complete":
            bg_color = COLOR_SUCCESS
            text_color = COLOR_WHITE
            content_bg = "#66BB6A"  # Lighter green for content
            self._icon_label.setText(PROGRESS_COMPLETE)
        elif self._status == "error":
            bg_color = COLOR_ERROR
            text_color = COLOR_WHITE
            content_bg = "#EF5350"  # Lighter red for content
            self._icon_label.setText(PROGRESS_ERROR)
        else:  # pending
            bg_color = COLOR_GREY_100
            text_color = COLOR_GREY_600
            content_bg = COLOR_GREY_200
            self._icon_label.setText(PROGRESS_PENDING)

        # Update expand indicator
        if self._has_content:
            self._expand_indicator.setText("▼" if self._expanded else "▶")
        else:
            self._expand_indicator.setText("")

        self.setStyleSheet(f"""
            WorkflowStepCard {{
                background-color: {bg_color};
                border-radius: {self.scale['radius_small']}px;
            }}
            WorkflowStepCard QFrame {{
                background-color: transparent;
            }}
            WorkflowStepCard QLabel {{
                color: {text_color};
                background-color: transparent;
            }}
            WorkflowStepCard QTextEdit {{
                background-color: {content_bg};
                color: {text_color};
                border: none;
                border-radius: {self.scale['radius_small']}px;
            }}
        """)

    def mousePressEvent(self, event) -> None:
        """Handle mouse press to toggle expansion."""
        # Only toggle if clicking on header and has content
        if self._has_content:
            # Check if click is in header area
            header_rect = self._header_widget.geometry()
            if header_rect.contains(event.pos()):
                self._expanded = not self._expanded
                self._content_widget.setVisible(self._expanded)
                self._update_style()
                self.clicked.emit()
        super().mousePressEvent(event)

    def set_status(self, status: str) -> None:
        """
        Set the step status.

        Args:
            status: One of "pending", "running", "complete", "error"
        """
        if status not in ("pending", "running", "complete", "error"):
            logger.warning(f"Invalid step status: {status}")
            status = "pending"

        self._status = status
        self._update_style()

        # Auto-expand when running if has content
        if status == "running" and self._has_content and not self._expanded:
            self._expanded = True
            self._content_widget.setVisible(True)
            self._update_style()

    def get_status(self) -> str:
        """
        Get current step status.

        Returns:
            Current status string
        """
        return self._status

    def set_content(self, text: str) -> None:
        """
        Set the content text for the expandable area.

        Args:
            text: Content text to display (supports markdown-like formatting)
        """
        self._content_text.setPlainText(text)
        self._has_content = bool(text.strip())
        self._update_style()

        # Auto-expand when content is added during running state
        if self._status == "running" and self._has_content and not self._expanded:
            self._expanded = True
            self._content_widget.setVisible(True)
            self._update_style()

    def append_content(self, text: str) -> None:
        """
        Append text to the content area.

        Args:
            text: Text to append
        """
        current = self._content_text.toPlainText()
        if current:
            new_text = current + "\n" + text
        else:
            new_text = text
        self.set_content(new_text)

    def clear_content(self) -> None:
        """Clear the content area."""
        self._content_text.clear()
        self._has_content = False
        self._expanded = False
        self._content_widget.setVisible(False)
        self._update_style()

        # Clear any stat chips
        while self._stats_layout.count() > 1:  # Keep the stretch
            item = self._stats_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def add_stat_chip(self, label: str, value: str, color: str = COLOR_PRIMARY) -> None:
        """
        Add a statistics chip to the content area.

        Args:
            label: Stat label (e.g., "Documents")
            value: Stat value (e.g., "42")
            color: Chip background color
        """
        chip = StatChipWidget(label, value, color, self)
        # Insert before the stretch
        self._stats_layout.insertWidget(self._stats_layout.count() - 1, chip)
        self._has_content = True
        self._update_style()

    def is_expanded(self) -> bool:
        """
        Check if the card is currently expanded.

        Returns:
            True if expanded, False otherwise
        """
        return self._expanded

    def set_expanded(self, expanded: bool) -> None:
        """
        Programmatically set the expanded state.

        Args:
            expanded: Whether the card should be expanded
        """
        if self._has_content:
            self._expanded = expanded
            self._content_widget.setVisible(expanded)
            self._update_style()


class VerdictBadge(QFrame):
    """
    A compact badge displaying a verdict with appropriate styling.

    Shows verdict text (Supports/Contradicts/Undecided) with color coding.
    """

    def __init__(
        self,
        verdict: str = "undecided",
        confidence: str = "medium",
        parent: Optional[QWidget] = None
    ) -> None:
        """
        Initialize verdict badge.

        Args:
            verdict: Verdict value ("supports", "contradicts", "undecided")
            confidence: Confidence level ("high", "medium", "low")
            parent: Parent widget
        """
        super().__init__(parent)

        self.scale = get_font_scale()
        self._setup_ui()
        self.set_verdict(verdict, confidence)

    def _setup_ui(self) -> None:
        """Setup badge UI."""
        self.setFrameShape(QFrame.StyledPanel)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            self.scale['padding_small'],
            self.scale['padding_tiny'],
            self.scale['padding_small'],
            self.scale['padding_tiny']
        )
        layout.setSpacing(self.scale['spacing_small'])

        # Verdict text
        self._verdict_label = QLabel("Undecided")
        font = self._verdict_label.font()
        font.setBold(True)
        self._verdict_label.setFont(font)
        layout.addWidget(self._verdict_label)

        # Confidence (smaller text)
        self._confidence_label = QLabel("medium")
        layout.addWidget(self._confidence_label)

    def set_verdict(self, verdict: str, confidence: str = "medium") -> None:
        """
        Set the verdict and confidence.

        Args:
            verdict: Verdict value
            confidence: Confidence level
        """
        verdict_text, verdict_color = format_verdict_display(verdict)
        confidence_text, confidence_color = format_confidence_display(confidence)

        self._verdict_label.setText(verdict_text)
        self._confidence_label.setText(f"({confidence_text})")

        self.setStyleSheet(f"""
            VerdictBadge {{
                background-color: {verdict_color};
                border-radius: {self.scale['radius_small']}px;
            }}
            QLabel {{
                color: {COLOR_WHITE};
            }}
        """)


class StatChipWidget(QFrame):
    """
    A compact chip displaying a statistic with label.

    Used for showing counts, scores, and other numeric values.
    """

    def __init__(
        self,
        label: str = "",
        value: str = "0",
        color: str = COLOR_PRIMARY,
        parent: Optional[QWidget] = None
    ) -> None:
        """
        Initialize stat chip.

        Args:
            label: Label text (e.g., "Documents")
            value: Value to display (e.g., "42")
            color: Background color hex string
            parent: Parent widget
        """
        super().__init__(parent)

        self.scale = get_font_scale()
        self._color = color

        self._setup_ui()
        self.set_value(label, value)

    def _setup_ui(self) -> None:
        """Setup chip UI."""
        self.setFrameShape(QFrame.StyledPanel)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            self.scale['padding_small'],
            self.scale['padding_tiny'],
            self.scale['padding_small'],
            self.scale['padding_tiny']
        )
        layout.setSpacing(self.scale['spacing_tiny'])

        # Value (bold)
        self._value_label = QLabel("0")
        font = self._value_label.font()
        font.setBold(True)
        self._value_label.setFont(font)
        layout.addWidget(self._value_label)

        # Label
        self._label_label = QLabel("")
        layout.addWidget(self._label_label)

        self._update_style()

    def _update_style(self) -> None:
        """Update visual style."""
        self.setStyleSheet(f"""
            StatChipWidget {{
                background-color: {self._color};
                border-radius: {self.scale['radius_small']}px;
            }}
            QLabel {{
                color: {COLOR_WHITE};
            }}
        """)

    def set_value(self, label: str, value: str) -> None:
        """
        Set the label and value.

        Args:
            label: Label text
            value: Value to display
        """
        self._label_label.setText(label)
        self._value_label.setText(str(value))

    def set_color(self, color: str) -> None:
        """
        Set the background color.

        Args:
            color: Color hex string
        """
        self._color = color
        self._update_style()


class CitationCardWidget(QFrame):
    """
    A card widget displaying a single citation with expandable details.

    Shows document title, authors, score, and strategies that found it.
    Click to expand/collapse passage text.
    """

    clicked = Signal()  # Emitted when card is clicked

    def __init__(
        self,
        citation_data: Dict[str, Any],
        parent: Optional[QWidget] = None
    ) -> None:
        """
        Initialize citation card.

        Args:
            citation_data: Dict with keys: title, authors, year, pmid, doi,
                          passage, score, strategies
            parent: Parent widget
        """
        super().__init__(parent)

        self.scale = get_font_scale()
        self.styles = get_stylesheet_generator()
        self._data = citation_data
        self._expanded = False

        self._setup_ui()
        self._populate()

    def _setup_ui(self) -> None:
        """Setup card UI."""
        self.setFrameShape(QFrame.StyledPanel)
        self.setCursor(Qt.PointingHandCursor)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(
            self.scale['padding_medium'],
            self.scale['padding_medium'],
            self.scale['padding_medium'],
            self.scale['padding_medium']
        )
        main_layout.setSpacing(self.scale['spacing_small'])

        # Header row (title + score)
        header_layout = QHBoxLayout()
        header_layout.setSpacing(self.scale['spacing_medium'])

        self._title_label = QLabel("")
        self._title_label.setWordWrap(True)
        font = self._title_label.font()
        font.setBold(True)
        self._title_label.setFont(font)
        header_layout.addWidget(self._title_label, stretch=1)

        self._score_chip = StatChipWidget("Score", "0", COLOR_PRIMARY, self)
        header_layout.addWidget(self._score_chip)

        main_layout.addLayout(header_layout)

        # Metadata row (authors, year, identifiers)
        self._metadata_label = QLabel("")
        self._metadata_label.setStyleSheet(f"color: {COLOR_GREY_600};")
        main_layout.addWidget(self._metadata_label)

        # Strategies row
        self._strategies_layout = QHBoxLayout()
        self._strategies_layout.setSpacing(self.scale['spacing_small'])
        self._strategies_label = QLabel("Found by:")
        self._strategies_label.setStyleSheet(f"color: {COLOR_GREY_600};")
        self._strategies_layout.addWidget(self._strategies_label)
        self._strategies_badges = QLabel("")
        self._strategies_layout.addWidget(self._strategies_badges)
        self._strategies_layout.addStretch()
        main_layout.addLayout(self._strategies_layout)

        # Passage (expandable)
        self._passage_widget = QTextEdit()
        self._passage_widget.setReadOnly(True)
        self._passage_widget.setVisible(False)
        self._passage_widget.setMaximumHeight(self.scale['base_line_height'] * 6)
        main_layout.addWidget(self._passage_widget)

        # Expand hint
        self._expand_hint = QLabel("Click to expand passage")
        self._expand_hint.setStyleSheet(f"color: {COLOR_GREY_600}; font-style: italic;")
        main_layout.addWidget(self._expand_hint)

        self._update_style()

    def _update_style(self) -> None:
        """Update card style."""
        bg_color = COLOR_WHITE if not self._expanded else COLOR_GREY_100
        self.setStyleSheet(f"""
            CitationCardWidget {{
                background-color: {bg_color};
                border: 1px solid {COLOR_GREY_300};
                border-radius: {self.scale['radius_small']}px;
            }}
        """)

    def _populate(self) -> None:
        """Populate card with data."""
        # Title
        title = self._data.get('title', 'No title')
        self._title_label.setText(truncate_title(title))
        self._title_label.setToolTip(title)

        # Score
        score = self._data.get('score', 0)
        score_text, score_color = format_score_badge(score)
        self._score_chip.set_value("", score_text)
        self._score_chip.set_color(score_color)

        # Metadata
        authors = self._data.get('authors', [])
        year = extract_year_from_date(self._data.get('year') or self._data.get('publication_date'))
        pmid = self._data.get('pmid')
        doi = self._data.get('doi')
        metadata_str = format_document_metadata(authors, year, pmid, doi)
        self._metadata_label.setText(metadata_str)
        self._metadata_label.setToolTip(metadata_str)

        # Strategies
        strategies = self._data.get('strategies', self._data.get('found_by', []))
        if strategies:
            strategies_text = format_provenance_display(strategies)
            self._strategies_badges.setText(strategies_text)
        else:
            self._strategies_label.setVisible(False)
            self._strategies_badges.setVisible(False)

        # Passage
        passage = self._data.get('passage', '')
        if passage:
            self._passage_widget.setPlainText(passage)
        else:
            self._expand_hint.setText("No passage extracted")

    def mousePressEvent(self, event) -> None:
        """Handle mouse press to toggle expansion."""
        self._expanded = not self._expanded
        self._passage_widget.setVisible(self._expanded)
        self._expand_hint.setVisible(not self._expanded)
        self._update_style()
        self.clicked.emit()
        super().mousePressEvent(event)


class StatisticsSection(QGroupBox):
    """
    A group box displaying search/processing statistics.

    Shows counts for documents found by each strategy, scored, cited, etc.
    """

    def __init__(
        self,
        title: str = "Statistics",
        parent: Optional[QWidget] = None
    ) -> None:
        """
        Initialize statistics section.

        Args:
            title: Group box title
            parent: Parent widget
        """
        super().__init__(title, parent)

        self.scale = get_font_scale()
        self._chips: List[StatChipWidget] = []

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup section UI."""
        self._layout = QHBoxLayout()
        self._layout.setSpacing(self.scale['spacing_medium'])
        self.setLayout(self._layout)

    def clear(self) -> None:
        """Clear all statistics."""
        for chip in self._chips:
            self._layout.removeWidget(chip)
            chip.deleteLater()
        self._chips.clear()

    def add_stat(self, label: str, value: Any, color: str = COLOR_PRIMARY) -> None:
        """
        Add a statistic chip.

        Args:
            label: Stat label
            value: Stat value
            color: Chip color
        """
        chip = StatChipWidget(label, str(value), color, self)
        self._chips.append(chip)
        self._layout.addWidget(chip)

    def set_search_stats(self, stats: Dict[str, Any]) -> None:
        """
        Set search statistics from a stats dict.

        Args:
            stats: Dict with semantic_count, hyde_count, keyword_count, deduplicated_count
        """
        self.clear()

        from .constants import SEARCH_STRATEGY_COLORS

        if 'semantic_count' in stats:
            self.add_stat("Semantic", stats['semantic_count'], SEARCH_STRATEGY_COLORS['semantic'])
        if 'hyde_count' in stats:
            self.add_stat("HyDE", stats['hyde_count'], SEARCH_STRATEGY_COLORS['hyde'])
        if 'keyword_count' in stats:
            self.add_stat("Keyword", stats['keyword_count'], SEARCH_STRATEGY_COLORS['keyword'])
        if 'deduplicated_count' in stats:
            self.add_stat("Total", stats['deduplicated_count'], COLOR_PRIMARY)

        self._layout.addStretch()


__all__ = [
    'StatusSpinnerWidget',
    'WorkflowStepCard',
    'VerdictBadge',
    'StatChipWidget',
    'CitationCardWidget',
    'StatisticsSection',
]
