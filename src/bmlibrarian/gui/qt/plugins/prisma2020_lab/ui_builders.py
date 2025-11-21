"""
UI builder functions for PRISMA 2020 Lab plugin.

Contains factory functions for creating reusable UI panels and components.
These functions create configured widgets without coupling to specific widget instances.
"""

import logging
from typing import Callable, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QLineEdit, QComboBox, QTextEdit, QTabWidget,
    QScrollArea, QSizePolicy
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIntValidator
from PySide6.QtPdfWidgets import QPdfView

from ...resources.styles import StylesheetGenerator, scale_px
from .constants import (
    SECTION_COLORS,
    DOC_ID_MIN_VALUE, DOC_ID_MAX_VALUE,
    WINDOW_TITLE, WINDOW_SUBTITLE,
    NO_DOCUMENT_LOADED,
    ASSESSMENT_PLACEHOLDER,
    DOC_ID_PLACEHOLDER,
)

logger = logging.getLogger(__name__)


class UIComponents:
    """
    Container for UI component references.

    Holds references to widgets created by builder functions,
    enabling the main tab to access them after creation.
    """

    def __init__(self) -> None:
        """Initialize empty component references."""
        # Input controls
        self.model_combo: Optional[QComboBox] = None
        self.doc_id_input: Optional[QLineEdit] = None
        self.load_button: Optional[QPushButton] = None
        self.clear_button: Optional[QPushButton] = None
        self.refresh_button: Optional[QPushButton] = None

        # Document display
        self.doc_title_label: Optional[QLabel] = None
        self.doc_metadata_label: Optional[QLabel] = None
        self.doc_tabs: Optional[QTabWidget] = None
        self.doc_abstract_edit: Optional[QTextEdit] = None
        self.doc_fulltext_edit: Optional[QTextEdit] = None
        self.doc_pdf_view: Optional[QPdfView] = None

        # Assessment results
        self.assessment_scroll: Optional[QScrollArea] = None
        self.assessment_widget: Optional[QWidget] = None
        self.assessment_layout: Optional[QVBoxLayout] = None

        # Status
        self.status_label: Optional[QLabel] = None


def create_header(stylesheet_gen: StylesheetGenerator) -> QWidget:
    """
    Create header section with title and subtitle.

    Args:
        stylesheet_gen: StylesheetGenerator for styling

    Returns:
        QWidget containing header layout
    """
    header_widget = QWidget()
    header_layout = QVBoxLayout(header_widget)
    header_layout.setContentsMargins(0, 0, 0, 0)
    header_layout.setSpacing(scale_px(5))

    title = QLabel(WINDOW_TITLE)
    title.setFont(QFont("", 10, QFont.Bold))
    title.setStyleSheet(
        stylesheet_gen.label_stylesheet(
            font_size_key='font_large',
            color=SECTION_COLORS['title'],
            bold=True
        )
    )

    subtitle = QLabel(WINDOW_SUBTITLE)
    subtitle.setStyleSheet(
        stylesheet_gen.label_stylesheet(
            font_size_key='font_medium',
            color='gray'
        )
    )

    header_layout.addWidget(title)
    header_layout.addWidget(subtitle)

    return header_widget


def create_model_selection_row(
    stylesheet_gen: StylesheetGenerator,
    components: UIComponents,
    on_model_changed: Callable[[str], None],
    on_refresh: Callable[[], None]
) -> QHBoxLayout:
    """
    Create model selection row with combo box and refresh button.

    Args:
        stylesheet_gen: StylesheetGenerator for styling
        components: UIComponents to store widget references
        on_model_changed: Callback for model selection change
        on_refresh: Callback for refresh button click

    Returns:
        QHBoxLayout containing model selection widgets
    """
    model_row = QHBoxLayout()

    model_label = QLabel("PRISMA Model:")
    model_label.setFont(QFont("", 10, QFont.Bold))

    components.model_combo = QComboBox()
    components.model_combo.setMinimumWidth(scale_px(300))
    components.model_combo.currentTextChanged.connect(on_model_changed)

    components.refresh_button = QPushButton("Refresh")
    components.refresh_button.clicked.connect(on_refresh)
    components.refresh_button.setMaximumWidth(scale_px(80))
    components.refresh_button.setStyleSheet(
        stylesheet_gen.button_stylesheet()
    )

    model_row.addWidget(model_label)
    model_row.addWidget(components.model_combo)
    model_row.addWidget(components.refresh_button)
    model_row.addStretch()

    return model_row


def create_document_input_row(
    stylesheet_gen: StylesheetGenerator,
    components: UIComponents,
    on_load: Callable[[], None],
    on_clear: Callable[[], None]
) -> QHBoxLayout:
    """
    Create document ID input row with load and clear buttons.

    Args:
        stylesheet_gen: StylesheetGenerator for styling
        components: UIComponents to store widget references
        on_load: Callback for load button click
        on_clear: Callback for clear button click

    Returns:
        QHBoxLayout containing input widgets
    """
    input_row = QHBoxLayout()

    doc_id_label = QLabel("Document ID:")

    components.doc_id_input = QLineEdit()
    components.doc_id_input.setPlaceholderText(DOC_ID_PLACEHOLDER)
    components.doc_id_input.setMaximumWidth(scale_px(200))
    components.doc_id_input.setValidator(QIntValidator(DOC_ID_MIN_VALUE, DOC_ID_MAX_VALUE))
    components.doc_id_input.returnPressed.connect(on_load)
    components.doc_id_input.setStyleSheet(
        stylesheet_gen.input_stylesheet()
    )

    components.load_button = QPushButton("Load & Assess")
    components.load_button.clicked.connect(on_load)
    components.load_button.setMinimumHeight(scale_px(35))
    components.load_button.setMaximumWidth(scale_px(150))
    components.load_button.setStyleSheet(
        stylesheet_gen.button_stylesheet(
            bg_color='#43A047',
            hover_color='#2E7D32'
        )
    )

    components.clear_button = QPushButton("Clear")
    components.clear_button.clicked.connect(on_clear)
    components.clear_button.setMaximumWidth(scale_px(80))
    components.clear_button.setMinimumHeight(scale_px(35))
    components.clear_button.setStyleSheet(
        stylesheet_gen.button_stylesheet()
    )

    input_row.addWidget(doc_id_label)
    input_row.addWidget(components.doc_id_input)
    input_row.addWidget(components.load_button)
    input_row.addWidget(components.clear_button)
    input_row.addStretch()

    return input_row


def create_input_panel(
    stylesheet_gen: StylesheetGenerator,
    components: UIComponents,
    on_model_changed: Callable[[str], None],
    on_refresh: Callable[[], None],
    on_load: Callable[[], None],
    on_clear: Callable[[], None]
) -> QGroupBox:
    """
    Create complete input panel with model selection and document input.

    Args:
        stylesheet_gen: StylesheetGenerator for styling
        components: UIComponents to store widget references
        on_model_changed: Callback for model selection change
        on_refresh: Callback for refresh button click
        on_load: Callback for load button click
        on_clear: Callback for clear button click

    Returns:
        QGroupBox containing all input widgets
    """
    group = QGroupBox("Document Input")
    layout = QVBoxLayout(group)
    layout.setSpacing(scale_px(10))

    model_row = create_model_selection_row(
        stylesheet_gen, components, on_model_changed, on_refresh
    )
    layout.addLayout(model_row)

    input_row = create_document_input_row(
        stylesheet_gen, components, on_load, on_clear
    )
    layout.addLayout(input_row)

    return group


def create_document_panel(
    stylesheet_gen: StylesheetGenerator,
    components: UIComponents
) -> QGroupBox:
    """
    Create document display panel with tabbed interface.

    Args:
        stylesheet_gen: StylesheetGenerator for styling
        components: UIComponents to store widget references

    Returns:
        QGroupBox containing document display widgets
    """
    group = QGroupBox("Document")
    layout = QVBoxLayout(group)
    layout.setSpacing(scale_px(10))

    # Title
    components.doc_title_label = QLabel(NO_DOCUMENT_LOADED)
    components.doc_title_label.setFont(QFont("", 10, QFont.Bold))
    components.doc_title_label.setWordWrap(True)
    components.doc_title_label.setStyleSheet(
        stylesheet_gen.label_stylesheet(
            font_size_key='font_medium',
            color='#424242',
            bold=True
        )
    )

    # Metadata
    components.doc_metadata_label = QLabel("")
    components.doc_metadata_label.setWordWrap(True)
    components.doc_metadata_label.setStyleSheet(
        stylesheet_gen.label_stylesheet(
            font_size_key='font_small',
            color='gray'
        )
    )

    # Tabbed interface for document content
    components.doc_tabs = QTabWidget()
    components.doc_tabs.setStyleSheet(
        stylesheet_gen.input_stylesheet()
    )

    # Tab 1: Abstract
    abstract_tab = QWidget()
    abstract_layout = QVBoxLayout(abstract_tab)
    abstract_layout.setContentsMargins(0, 0, 0, 0)

    components.doc_abstract_edit = QTextEdit()
    components.doc_abstract_edit.setReadOnly(True)
    components.doc_abstract_edit.setPlaceholderText("Document abstract will appear here...")
    components.doc_abstract_edit.setStyleSheet(
        stylesheet_gen.input_stylesheet()
    )
    abstract_layout.addWidget(components.doc_abstract_edit)
    components.doc_tabs.addTab(abstract_tab, "Abstract")

    # Tab 2: Full Text
    fulltext_tab = QWidget()
    fulltext_layout = QVBoxLayout(fulltext_tab)
    fulltext_layout.setContentsMargins(0, 0, 0, 0)

    components.doc_fulltext_edit = QTextEdit()
    components.doc_fulltext_edit.setReadOnly(True)
    components.doc_fulltext_edit.setPlaceholderText("Full text not available for this document...")
    components.doc_fulltext_edit.setStyleSheet(
        stylesheet_gen.input_stylesheet()
    )
    components.doc_fulltext_edit.setVisible(False)
    fulltext_layout.addWidget(components.doc_fulltext_edit)

    components.doc_pdf_view = QPdfView()
    components.doc_pdf_view.setVisible(False)
    fulltext_layout.addWidget(components.doc_pdf_view)

    components.doc_tabs.addTab(fulltext_tab, "Full Text")

    layout.addWidget(components.doc_title_label)
    layout.addWidget(components.doc_metadata_label)
    layout.addSpacing(scale_px(10))
    layout.addWidget(components.doc_tabs, stretch=1)

    return group


def create_assessment_panel(
    stylesheet_gen: StylesheetGenerator,
    components: UIComponents
) -> QGroupBox:
    """
    Create assessment results display panel.

    Args:
        stylesheet_gen: StylesheetGenerator for styling
        components: UIComponents to store widget references

    Returns:
        QGroupBox containing assessment display widgets
    """
    group = QGroupBox("PRISMA 2020 Assessment")
    layout = QVBoxLayout(group)
    layout.setSpacing(scale_px(10))
    layout.setContentsMargins(scale_px(5), scale_px(5), scale_px(5), scale_px(5))

    components.assessment_scroll = QScrollArea()
    components.assessment_scroll.setWidgetResizable(True)
    components.assessment_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    components.assessment_scroll.setSizePolicy(
        QSizePolicy.Policy.Expanding,
        QSizePolicy.Policy.Expanding
    )

    components.assessment_widget = QWidget()
    components.assessment_layout = QVBoxLayout(components.assessment_widget)
    components.assessment_layout.setSpacing(scale_px(10))
    components.assessment_layout.setContentsMargins(0, 0, 0, 0)

    placeholder = QLabel(ASSESSMENT_PLACEHOLDER)
    placeholder.setStyleSheet(
        stylesheet_gen.label_stylesheet(
            font_size_key='font_medium',
            color='gray'
        )
    )
    components.assessment_layout.addWidget(placeholder)

    components.assessment_scroll.setWidget(components.assessment_widget)
    layout.addWidget(components.assessment_scroll, stretch=1)

    return group


def create_status_label(stylesheet_gen: StylesheetGenerator) -> QLabel:
    """
    Create status label for bottom of window.

    Args:
        stylesheet_gen: StylesheetGenerator for styling

    Returns:
        QLabel configured as status bar
    """
    status_label = QLabel("Ready")
    status_label.setStyleSheet(
        stylesheet_gen.label_stylesheet(
            font_size_key='font_small',
            color='gray'
        )
    )
    return status_label


def clear_layout(layout: Optional[QVBoxLayout]) -> None:
    """
    Recursively clear a layout and delete all child widgets and layouts.

    Args:
        layout: Layout to clear, or None
    """
    if layout is None:
        return

    while layout.count():
        child = layout.takeAt(0)
        if child.widget():
            child.widget().deleteLater()
        elif child.layout():
            clear_layout(child.layout())
