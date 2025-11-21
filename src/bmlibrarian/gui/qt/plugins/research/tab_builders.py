"""
Tab builder functions for the Research Tab.

This module contains pure functions that create the UI structure for each tab
in the research interface. Each function returns a widget and a dictionary of
UI element references that need to be accessed later.
"""

from dataclasses import dataclass, field
from typing import Optional

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTextEdit,
    QLabel,
    QScrollArea,
    QFrame,
    QProgressBar,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from .constants import UIConstants, StyleSheets
from ...widgets.markdown_viewer import MarkdownViewer


@dataclass
class TabRefs:
    """Container for UI element references from a tab builder."""
    widgets: dict = field(default_factory=dict)


def build_placeholder_tab(
    ui: UIConstants,
    icon: str,
    title: str,
    description: str
) -> tuple[QWidget, TabRefs]:
    """
    Create a placeholder tab with consistent formatting.

    Args:
        ui: UI constants for styling
        icon: Emoji icon for the tab
        title: Tab title
        description: Bulleted list of what will be displayed

    Returns:
        Tuple of (widget, refs) where refs contains UI element references
    """
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(
        ui.TAB_WIDGET_MARGIN,
        ui.TAB_WIDGET_MARGIN,
        ui.TAB_WIDGET_MARGIN,
        ui.TAB_WIDGET_MARGIN
    )

    # Header
    label = QLabel(f"{icon} {title}")
    label_font = QFont()
    label_font.setPointSize(ui.TAB_HEADER_FONT_SIZE)
    label_font.setBold(True)
    label.setFont(label_font)
    layout.addWidget(label)

    # Description
    desc_label = QLabel(description)
    desc_label.setStyleSheet(f"color: {ui.COLOR_TEXT_GREY}; margin-top: 10px;")
    desc_label.setWordWrap(True)
    layout.addWidget(desc_label)

    layout.addStretch()
    return widget, TabRefs()


def build_search_tab(ui: UIConstants) -> tuple[QWidget, TabRefs]:
    """
    Create Search tab (query generation and display).

    Shows the generated PostgreSQL tsquery and search results summary.

    Args:
        ui: UI constants for styling

    Returns:
        Tuple of (widget, refs) where refs.widgets contains:
        - 'query_text_display': QTextEdit for query display
        - 'document_count_label': QLabel for document count
    """
    refs = TabRefs()

    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(
        ui.TAB_WIDGET_MARGIN,
        ui.TAB_WIDGET_MARGIN,
        ui.TAB_WIDGET_MARGIN,
        ui.TAB_WIDGET_MARGIN
    )

    # Header
    header = QLabel("Search Query Generation")
    header_font = QFont()
    header_font.setPointSize(ui.TAB_HEADER_FONT_SIZE)
    header_font.setBold(True)
    header.setFont(header_font)
    layout.addWidget(header)

    # Query section
    query_label = QLabel("Generated PostgreSQL Query:")
    query_label_font = QFont()
    query_label_font.setBold(True)
    query_label.setFont(query_label_font)
    layout.addWidget(query_label)

    # Query text display
    query_text_display = QTextEdit()
    query_text_display.setReadOnly(True)
    query_text_display.setMaximumHeight(100)
    query_text_display.setPlaceholderText("Query will appear here after clicking 'Start Research'...")
    query_text_display.setStyleSheet(StyleSheets.query_display())
    layout.addWidget(query_text_display)
    refs.widgets['query_text_display'] = query_text_display

    # Results summary section
    results_label = QLabel("Search Results:")
    results_label_font = QFont()
    results_label_font.setBold(True)
    results_label.setFont(results_label_font)
    layout.addWidget(results_label)

    # Document count display
    document_count_label = QLabel("No search performed yet")
    document_count_label.setStyleSheet(f"color: {ui.COLOR_TEXT_GREY};")
    layout.addWidget(document_count_label)
    refs.widgets['document_count_label'] = document_count_label

    # Add stretch to push everything to the top
    layout.addStretch()

    return widget, refs


def build_literature_tab(ui: UIConstants) -> tuple[QWidget, TabRefs]:
    """
    Create Literature tab (document list with scores).

    Args:
        ui: UI constants for styling

    Returns:
        Tuple of (widget, refs) where refs.widgets contains:
        - 'summary_label': QLabel for summary
        - 'progress_bar': QProgressBar for scoring progress
        - 'container': QWidget container for document cards
        - 'layout': QVBoxLayout for adding cards
        - 'empty_label': QLabel for empty state
    """
    refs = TabRefs()

    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(
        ui.TAB_WIDGET_MARGIN, ui.TAB_WIDGET_MARGIN,
        ui.TAB_WIDGET_MARGIN, ui.TAB_WIDGET_MARGIN
    )

    # Header
    header_label = QLabel("Literature Documents")
    header_font = QFont()
    header_font.setPointSize(ui.TAB_HEADER_FONT_SIZE)
    header_font.setBold(True)
    header_label.setFont(header_font)
    layout.addWidget(header_label)

    # Subtitle
    subtitle_label = QLabel("Documents retrieved from search with AI relevance scores")
    subtitle_label.setStyleSheet(f"color: {ui.COLOR_TEXT_GREY};")
    layout.addWidget(subtitle_label)

    # Document count and score summary
    summary_label = QLabel("No documents scored yet")
    summary_label.setStyleSheet(f"color: {ui.COLOR_TEXT_GREY};")
    layout.addWidget(summary_label)
    refs.widgets['summary_label'] = summary_label

    # Progress bar for scoring (hidden by default)
    progress_bar = QProgressBar()
    progress_bar.setTextVisible(True)
    progress_bar.setFormat("Scoring document %v/%m")
    progress_bar.setStyleSheet(StyleSheets.progress_bar())
    progress_bar.setVisible(False)
    layout.addWidget(progress_bar)
    refs.widgets['progress_bar'] = progress_bar

    # Scroll area for document list
    scroll_area = QScrollArea()
    scroll_area.setWidgetResizable(True)
    scroll_area.setFrameShape(QFrame.Shape.NoFrame)

    # Container widget for document cards
    container = QWidget()
    container_layout = QVBoxLayout(container)
    container_layout.setSpacing(8)
    container_layout.setContentsMargins(0, 10, 0, 0)

    # Empty state message
    empty_label = QLabel("No documents to display")
    empty_label.setStyleSheet(f"color: {ui.COLOR_TEXT_GREY}; padding: 20px;")
    empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    container_layout.addWidget(empty_label)

    # Add stretch at bottom
    container_layout.addStretch()

    scroll_area.setWidget(container)
    layout.addWidget(scroll_area)

    refs.widgets['container'] = container
    refs.widgets['layout'] = container_layout
    refs.widgets['empty_label'] = empty_label

    return widget, refs


def build_scoring_tab(ui: UIConstants) -> tuple[QWidget, TabRefs]:
    """Create Scoring tab (document relevance scoring)."""
    return build_placeholder_tab(
        ui,
        "",
        "Document Scoring",
        "This tab will display:\n"
        "- Interactive scoring interface (in interactive mode)\n"
        "- Automated scoring results (in auto mode)\n"
        "- Document relevance scores (1-5 scale)\n"
        "- Color-coded score badges\n"
        "- Scoring progress and statistics"
    )


def build_citations_tab(ui: UIConstants) -> tuple[QWidget, TabRefs]:
    """
    Create Citations tab (extracted citations).

    Args:
        ui: UI constants for styling

    Returns:
        Tuple of (widget, refs) where refs.widgets contains:
        - 'summary_label': QLabel for summary
        - 'container': QWidget container for citation cards
        - 'layout': QVBoxLayout for adding cards
        - 'empty_label': QLabel for empty state
    """
    refs = TabRefs()

    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(
        ui.TAB_WIDGET_MARGIN, ui.TAB_WIDGET_MARGIN,
        ui.TAB_WIDGET_MARGIN, ui.TAB_WIDGET_MARGIN
    )

    # Header
    header_label = QLabel("Extracted Citations")
    header_font = QFont()
    header_font.setPointSize(ui.TAB_HEADER_FONT_SIZE)
    header_font.setBold(True)
    header_label.setFont(header_font)
    layout.addWidget(header_label)

    # Subtitle
    subtitle_label = QLabel("Relevant passages from high-scoring documents (score >= 3.0)")
    subtitle_label.setStyleSheet(f"color: {ui.COLOR_TEXT_GREY};")
    layout.addWidget(subtitle_label)

    # Citation count summary
    summary_label = QLabel("No citations extracted yet")
    summary_label.setStyleSheet(f"color: {ui.COLOR_TEXT_GREY};")
    layout.addWidget(summary_label)
    refs.widgets['summary_label'] = summary_label

    # Scroll area for citation list
    scroll_area = QScrollArea()
    scroll_area.setWidgetResizable(True)
    scroll_area.setFrameShape(QFrame.Shape.NoFrame)

    # Container widget for citation cards
    container = QWidget()
    container_layout = QVBoxLayout(container)
    container_layout.setSpacing(8)
    container_layout.setContentsMargins(0, 10, 0, 0)

    # Empty state message
    empty_label = QLabel("No citations to display")
    empty_label.setStyleSheet(f"color: {ui.COLOR_TEXT_GREY}; padding: 20px;")
    empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    container_layout.addWidget(empty_label)

    # Add stretch at bottom
    container_layout.addStretch()

    scroll_area.setWidget(container)
    layout.addWidget(scroll_area)

    refs.widgets['container'] = container
    refs.widgets['layout'] = container_layout
    refs.widgets['empty_label'] = empty_label

    return widget, refs


def build_preliminary_tab(ui: UIConstants) -> tuple[QWidget, TabRefs]:
    """
    Create Preliminary Report tab.

    Args:
        ui: UI constants for styling

    Returns:
        Tuple of (widget, refs) where refs.widgets contains:
        - 'summary_label': QLabel for summary
        - 'report_viewer': MarkdownViewer for report display
    """
    refs = TabRefs()

    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(
        ui.TAB_WIDGET_MARGIN, ui.TAB_WIDGET_MARGIN,
        ui.TAB_WIDGET_MARGIN, ui.TAB_WIDGET_MARGIN
    )

    # Header
    header_label = QLabel("Preliminary Report")
    header_font = QFont()
    header_font.setPointSize(ui.TAB_HEADER_FONT_SIZE)
    header_font.setBold(True)
    header_label.setFont(header_font)
    layout.addWidget(header_label)

    # Subtitle
    subtitle_label = QLabel("Report generated from extracted citations (before counterfactual analysis)")
    subtitle_label.setStyleSheet(f"color: {ui.COLOR_TEXT_GREY};")
    layout.addWidget(subtitle_label)

    # Report statistics summary
    summary_label = QLabel("No report generated yet")
    summary_label.setStyleSheet(f"color: {ui.COLOR_TEXT_GREY};")
    layout.addWidget(summary_label)
    refs.widgets['summary_label'] = summary_label

    # Markdown viewer for report
    report_viewer = MarkdownViewer()
    report_viewer.set_markdown("_No report available yet. Please run a research workflow first._")
    layout.addWidget(report_viewer)
    refs.widgets['report_viewer'] = report_viewer

    return widget, refs


def build_counterfactual_tab(ui: UIConstants) -> tuple[QWidget, TabRefs]:
    """
    Create Counterfactual Analysis tab.

    Args:
        ui: UI constants for styling

    Returns:
        Tuple of (widget, refs) where refs.widgets contains:
        - 'summary_label': QLabel for summary
        - 'layout': QVBoxLayout for adding content
    """
    refs = TabRefs()

    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(15, 15, 15, 15)
    layout.setSpacing(10)

    # Header
    header = QLabel("Counterfactual Analysis")
    header_font = QFont()
    header_font.setPointSize(ui.TAB_HEADER_FONT_SIZE)
    header_font.setBold(True)
    header.setFont(header_font)
    layout.addWidget(header)

    # Summary label
    summary_label = QLabel("Waiting for analysis...")
    summary_label.setStyleSheet(f"color: {ui.COLOR_TEXT_GREY};")
    layout.addWidget(summary_label)
    refs.widgets['summary_label'] = summary_label

    # Scroll area for counterfactual content
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)

    # Content widget
    content_widget = QWidget()
    content_layout = QVBoxLayout(content_widget)
    content_layout.setSpacing(10)
    content_layout.setContentsMargins(0, 0, 0, 0)

    # Initial placeholder
    placeholder = QLabel(
        "Counterfactual analysis will appear here when enabled.\n\n"
        "This analysis:\n"
        "- Identifies key claims in the preliminary report\n"
        "- Generates research questions to find contradictory evidence\n"
        "- Searches for documents that might contradict the findings\n"
        "- Provides a balanced view of the evidence"
    )
    placeholder.setStyleSheet(f"color: {ui.COLOR_TEXT_GREY}; padding: 20px;")
    placeholder.setWordWrap(True)
    placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
    content_layout.addWidget(placeholder)
    content_layout.addStretch()

    scroll.setWidget(content_widget)
    layout.addWidget(scroll, stretch=1)

    refs.widgets['content_layout'] = content_layout

    return widget, refs


def build_report_tab(ui: UIConstants) -> tuple[QWidget, TabRefs]:
    """
    Create Final Report tab with export buttons.

    Args:
        ui: UI constants for styling

    Returns:
        Tuple of (widget, refs) where refs.widgets contains:
        - 'summary_label': QLabel for summary
        - 'report_viewer': MarkdownViewer for report display
        - 'save_markdown_button': QPushButton for saving markdown
        - 'export_json_button': QPushButton for exporting JSON
    """
    refs = TabRefs()

    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(10, 10, 10, 10)
    layout.setSpacing(10)

    # Header row with title and export buttons
    header_row = QHBoxLayout()

    # Header label
    header_label = QLabel("Final Comprehensive Report")
    header_row.addWidget(header_label)

    header_row.addStretch()

    # Export buttons container
    export_buttons_layout = QHBoxLayout()
    export_buttons_layout.setSpacing(10)

    # Save Markdown button
    save_markdown_button = QPushButton("Save Report (Markdown)")
    save_markdown_button.setStyleSheet(StyleSheets.save_button())
    save_markdown_button.setEnabled(False)  # Disabled until report is ready
    export_buttons_layout.addWidget(save_markdown_button)
    refs.widgets['save_markdown_button'] = save_markdown_button

    # Export JSON button
    export_json_button = QPushButton("Export as JSON")
    export_json_button.setStyleSheet(StyleSheets.export_button())
    export_json_button.setEnabled(False)  # Disabled until report is ready
    export_buttons_layout.addWidget(export_json_button)
    refs.widgets['export_json_button'] = export_json_button

    header_row.addLayout(export_buttons_layout)
    layout.addLayout(header_row)

    # Summary label
    summary_label = QLabel("No report generated yet")
    summary_label.setStyleSheet(f"color: {ui.COLOR_TEXT_GREY};")
    layout.addWidget(summary_label)
    refs.widgets['summary_label'] = summary_label

    # Markdown viewer
    report_viewer = MarkdownViewer()
    report_viewer.set_markdown("_No final report available yet. The final report will be generated after counterfactual analysis._")
    layout.addWidget(report_viewer)
    refs.widgets['report_viewer'] = report_viewer

    return widget, refs
