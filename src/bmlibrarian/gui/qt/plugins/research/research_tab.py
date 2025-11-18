"""
Research tab widget for BMLibrarian Qt GUI - Phase 1 Implementation.

Qt-native design matching Flet functionality with proper Qt widgets and layouts.
"""

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTextEdit,
    QLabel,
    QSpinBox,
    QCheckBox,
    QTabWidget,
    QScrollArea,
    QFrame,
    QSizePolicy,
    QMessageBox,
    QProgressBar,
    QGroupBox,
    QApplication,
    QFileDialog,
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QFont
from typing import Optional
import logging
import json
import os
import errno
from datetime import datetime

# Import markdown viewer for report display
from ...widgets.markdown_viewer import MarkdownViewer

# Import document card factory
from ...qt_document_card_factory import QtDocumentCardFactory
from bmlibrarian.gui.document_card_factory_base import (
    DocumentCardData,
    CardContext
)
from ...resources.styles import get_font_scale


# ============================================================================
# UI Constants
# ============================================================================

class UIConstants:
    """UI layout and styling constants with DPI-aware scaling."""

    def __init__(self, scale_func):
        """Initialize constants with scale function."""
        s = scale_func

        # Fonts
        self.TITLE_FONT_SIZE = s(18)
        self.SUBTITLE_FONT_SIZE = s(10)
        self.TAB_HEADER_FONT_SIZE = s(12)
        self.CARD_TITLE_FONT_SIZE = s(11)  # Document/citation card titles
        self.CARD_SUBTITLE_FONT_SIZE = s(10)  # Authors, publication info
        self.CARD_BODY_FONT_SIZE = s(10)  # Abstract, reasoning, passages
        self.CARD_LABEL_FONT_SIZE = s(9)  # Section labels like "Abstract:", "Summary:"

        # Colors (not scaled)
        self.COLOR_PRIMARY_BLUE = "#1976D2"
        self.COLOR_PRIMARY_BLUE_HOVER = "#1565C0"
        self.COLOR_DISABLED_GREY = "#BDBDBD"
        self.COLOR_TEXT_GREY = "#666666"
        self.COLOR_BACKGROUND_GREY = "#F5F5F5"
        self.COLOR_BORDER_GREY = "#E0E0E0"
        self.COLOR_WHITE = "white"
        self.COLOR_TEXT_INPUT_BACKGROUND = "#FFF8F0"  # Very faint pastel sand color

        # Spacing
        self.MAIN_LAYOUT_MARGIN = s(15)
        self.MAIN_LAYOUT_SPACING = s(10)
        self.CONTROLS_SPACING = s(10)
        self.ROW2_SPACING = s(15)
        self.HEADER_BOTTOM_MARGIN = s(10)
        self.HEADER_SPACING = s(5)
        self.TAB_WIDGET_MARGIN = s(15)

        # Widget Sizes
        self.QUESTION_INPUT_MIN_HEIGHT = s(70)
        self.QUESTION_INPUT_MAX_HEIGHT = s(100)
        self.START_BUTTON_MIN_HEIGHT = s(45)
        self.START_BUTTON_MIN_WIDTH = s(140)
        self.SPINBOX_WIDTH = s(80)

        # Border Radii
        self.CONTROLS_BORDER_RADIUS = s(8)
        self.BUTTON_BORDER_RADIUS = s(4)

        # Spinbox Ranges (not scaled - these are value ranges)
        self.MAX_RESULTS_MIN = 10
        self.MAX_RESULTS_MAX = 1000
        self.MAX_RESULTS_DEFAULT = 100
        self.MIN_RELEVANT_MIN = 1
        self.MIN_RELEVANT_MAX = 100
        self.MIN_RELEVANT_DEFAULT = 10

        # Document Score Thresholds (not scaled - these are score values)
        self.SCORE_THRESHOLD_HIGH_RELEVANCE = 4.0
        self.SCORE_THRESHOLD_RELEVANT = 3.0
        self.SCORE_THRESHOLD_SOMEWHAT_RELEVANT = 2.0

        # Document Score Colors (not scaled)
        self.SCORE_COLOR_HIGH = "#4CAF50"  # Green
        self.SCORE_COLOR_RELEVANT = "#2196F3"  # Blue
        self.SCORE_COLOR_SOMEWHAT = "#FF9800"  # Orange
        self.SCORE_COLOR_LOW = "#9E9E9E"  # Grey


class StyleSheets:
    """Centralized stylesheet definitions with DPI-aware scaling."""

    @staticmethod
    def controls_frame(c: UIConstants) -> str:
        """Stylesheet for controls section frame."""
        return f"""
            QFrame {{
                background-color: {c.COLOR_BACKGROUND_GREY};
                border: 1px solid {c.COLOR_BORDER_GREY};
                border-radius: {c.CONTROLS_BORDER_RADIUS}px;
                padding: {c.CONTROLS_SPACING}px;
            }}
        """

    @staticmethod
    def start_button(c: UIConstants, scale_func) -> str:
        """Stylesheet for Start Research button."""
        s = scale_func
        return f"""
            QPushButton {{
                background-color: {c.COLOR_PRIMARY_BLUE};
                color: {c.COLOR_WHITE};
                font-weight: bold;
                border-radius: {c.BUTTON_BORDER_RADIUS}px;
                padding: {s(8)}px {s(16)}px;
            }}
            QPushButton:hover {{
                background-color: {c.COLOR_PRIMARY_BLUE_HOVER};
            }}
            QPushButton:disabled {{
                background-color: {c.COLOR_DISABLED_GREY};
            }}
        """

    @staticmethod
    def text_input(c: UIConstants, scale_func) -> str:
        """Stylesheet for all text input widgets (QTextEdit, QLineEdit, QSpinBox)."""
        s = scale_func
        return f"""
            QTextEdit, QLineEdit, QSpinBox {{
                background-color: {c.COLOR_TEXT_INPUT_BACKGROUND};
                border: 1px solid {c.COLOR_BORDER_GREY};
                border-radius: {s(4)}px;
                padding: {s(4)}px;
            }}
            QTextEdit:focus, QLineEdit:focus, QSpinBox:focus {{
                border: 2px solid {c.COLOR_PRIMARY_BLUE};
            }}
        """


# ============================================================================
# Main Research Tab Widget
# ============================================================================

class ResearchTabWidget(QWidget):
    """
    Main research workflow widget - Qt-native design.

    Structure:
    - Header (title + subtitle)
    - Controls section (question input, parameters, toggles, start button)
    - 8-tab interface (Search, Literature, Scoring, Citations, Preliminary,
      Counterfactual, Report, Settings)
    """

    # Signals for plugin integration
    status_message: Signal = Signal(str)  # Status updates
    workflow_started: Signal = Signal()  # Workflow execution started
    workflow_completed: Signal = Signal(dict)  # Workflow completed with results
    workflow_error: Signal = Signal(Exception)  # Workflow error occurred

    def __init__(self, parent: Optional[QWidget] = None, agents: Optional[dict] = None) -> None:
        """
        Initialize research tab.

        Args:
            parent: Optional parent widget
            agents: Optional dictionary of initialized BMLibrarian agents
        """
        super().__init__(parent)

        # DPI-aware scaling
        self.scale = get_font_scale()
        self.ui = UIConstants(self.scale)

        # Logger
        self.logger = logging.getLogger("bmlibrarian.gui.qt.plugins.research.ResearchTabWidget")

        # Workflow state
        self.current_results: dict = {}
        self.counterfactual_results: Optional[dict] = None
        self.workflow_running: bool = False
        self.final_report_markdown: str = ""  # Store final report for export

        # Validation state (prevent infinite spinbox adjustment loops)
        self._validation_in_progress: bool = False

        # Agents and workflow executor
        self.agents: Optional[dict] = agents
        self.workflow_executor: Optional['QtWorkflowExecutor'] = None

        # Initialize workflow executor if agents available
        if self.agents:
            from .workflow_executor import QtWorkflowExecutor
            self.workflow_executor = QtWorkflowExecutor(self.agents, parent=self)
            # Connect workflow signals
            self.workflow_executor.workflow_started.connect(self._on_workflow_started)
            self.workflow_executor.workflow_completed.connect(self._on_workflow_completed)
            self.workflow_executor.workflow_error.connect(self._on_workflow_error)
            self.workflow_executor.status_message.connect(self._on_workflow_status)

            # Connect step-specific signals (Milestone 1)
            self.workflow_executor.query_generated.connect(self._on_query_generated)
            self.workflow_executor.documents_found.connect(self._on_documents_found)

            # Connect Milestone 2 signals
            self.workflow_executor.scoring_progress.connect(self._on_scoring_progress)
            self.workflow_executor.documents_scored.connect(self._on_documents_scored)

            # Connect Milestone 3 signals
            self.workflow_executor.citations_extracted.connect(self._on_citations_extracted)
            self.workflow_executor.preliminary_report_generated.connect(self._on_preliminary_report_generated)

            self.logger.info("✅ Workflow executor initialized with agents")
        else:
            self.logger.warning("⚠️ No agents provided - workflow functionality disabled")

        # Workflow thread (Milestone 4: Background execution)
        self.workflow_thread: Optional['WorkflowThread'] = None

        # Document card factory for creating consistent document cards
        self.document_card_factory = QtDocumentCardFactory()
        self.logger.info("✅ Document card factory initialized")

        # UI Components (initialized in _setup_ui)
        self.question_input: Optional[QTextEdit] = None
        self.start_button: Optional[QPushButton] = None
        self.cancel_button: Optional[QPushButton] = None
        self.new_button: Optional[QPushButton] = None
        self.progress_label: Optional[QLabel] = None
        self.status_label: Optional[QLabel] = None
        self.max_results_spin: Optional[QSpinBox] = None
        self.min_relevant_spin: Optional[QSpinBox] = None
        self.interactive_checkbox: Optional[QCheckBox] = None
        self.counterfactual_checkbox: Optional[QCheckBox] = None
        self.study_quality_checkbox: Optional[QCheckBox] = None
        self.research_tabs: Optional[QTabWidget] = None

        # Initialize UI
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup the user interface with Qt-native design."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(
            self.ui.MAIN_LAYOUT_MARGIN,
            self.ui.MAIN_LAYOUT_MARGIN,
            self.ui.MAIN_LAYOUT_MARGIN,
            self.ui.MAIN_LAYOUT_MARGIN
        )
        main_layout.setSpacing(self.ui.MAIN_LAYOUT_SPACING)

        # 1. Header section (Row 1 - fixed height, expands horizontally)
        header = self._create_header_section()
        main_layout.addWidget(header)

        # 2. Controls section (Rows 2-3 - fixed height, expands horizontally)
        controls = self._create_controls_section()
        main_layout.addWidget(controls)

        # 3. Tabbed interface (Row 4 - expands both horizontally and vertically)
        self.research_tabs = self._create_tabbed_interface()
        main_layout.addWidget(self.research_tabs, stretch=1)

        # 4. Status bar (fixed height, expands horizontally)
        status_bar = self._create_status_bar()
        main_layout.addWidget(status_bar)

    def _create_header_section(self) -> QWidget:
        """
        Create header section with single-line title.

        Returns:
            Header widget
        """
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, self.ui.HEADER_BOTTOM_MARGIN)
        header_layout.setSpacing(0)

        # Single-line title
        title = QLabel("BMLibrarian Research Assistant - AI Powered Evidence Based Biomedical Literature Research")
        title_font = QFont()
        title_font.setPointSize(self.ui.TITLE_FONT_SIZE)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet(f"color: {self.ui.COLOR_PRIMARY_BLUE};")
        header_layout.addWidget(title)

        # Add stretch to keep title left-aligned
        header_layout.addStretch()

        # Set fixed height for header
        header_widget.setMaximumHeight(40)

        return header_widget

    def _create_controls_section(self) -> QWidget:
        """
        Create controls section with question input, parameters, and buttons.

        Layout:
        Row 2: [Research question: _____(2 lines)_____] [Start Research → Cancel] [New]
        Row 3: [Max results (...)] [Min relevant (...)] [☐ Interactive mode] [☐ Counterfactual analysis] [☐ Study quality rating]

        Returns:
            Controls widget
        """
        # Container with frame and background
        controls_frame = QFrame()
        controls_frame.setFrameShape(QFrame.StyledPanel)
        controls_frame.setFrameShadow(QFrame.Raised)
        controls_frame.setStyleSheet(StyleSheets.controls_frame(self.ui))
        controls_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        controls_layout = QVBoxLayout(controls_frame)
        controls_layout.setSpacing(self.ui.CONTROLS_SPACING)

        # Row 2: Research question label + input + buttons
        row2 = QHBoxLayout()
        row2.setSpacing(self.ui.CONTROLS_SPACING)

        # Research Question label
        question_label = QLabel("Research question:")
        question_label.setStyleSheet("font-weight: bold;")
        row2.addWidget(question_label)

        # Question input (2 lines)
        self.question_input = QTextEdit()
        self.question_input.setPlaceholderText(
            "Enter your biomedical research question here..."
        )
        self.question_input.setMaximumHeight(60)  # 2 lines
        self.question_input.setMinimumHeight(60)
        self.question_input.setStyleSheet(StyleSheets.text_input(self.ui, self.scale))
        self.question_input.textChanged.connect(self._on_question_changed)
        row2.addWidget(self.question_input, stretch=1)

        # Start/Cancel button (dynamic)
        self.start_button = QPushButton("Start Research")
        self.start_button.setIcon(self.start_button.style().standardIcon(
            self.start_button.style().StandardPixmap.SP_MediaPlay
        ))
        self.start_button.setMinimumHeight(60)
        self.start_button.setMinimumWidth(140)
        self.start_button.setEnabled(False)
        self.start_button.setStyleSheet(StyleSheets.start_button(self.ui, self.scale))
        self.start_button.clicked.connect(self._on_start_research)
        row2.addWidget(self.start_button)

        # Cancel button (shown during workflow)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setIcon(self.cancel_button.style().standardIcon(
            self.cancel_button.style().StandardPixmap.SP_DialogCancelButton
        ))
        self.cancel_button.setMinimumHeight(60)
        self.cancel_button.setMinimumWidth(140)
        self.cancel_button.setEnabled(False)
        self.cancel_button.setVisible(False)  # Hidden initially
        self.cancel_button.setStyleSheet("""
            QPushButton {
                background-color: #F44336;
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #D32F2F;
            }
            QPushButton:pressed {
                background-color: #C62828;
            }
            QPushButton:disabled {
                background-color: #BDBDBD;
                color: #757575;
            }
        """)
        self.cancel_button.clicked.connect(self._on_cancel_clicked)
        row2.addWidget(self.cancel_button)

        # New button
        self.new_button = QPushButton("New")
        self.new_button.setMinimumHeight(60)
        self.new_button.setMinimumWidth(80)
        self.new_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
        """)
        self.new_button.clicked.connect(self._on_new_research)
        row2.addWidget(self.new_button)

        controls_layout.addLayout(row2)

        # Row 3: Parameters and toggles
        row3 = QHBoxLayout()
        row3.setSpacing(self.ui.ROW2_SPACING)

        # Max Results
        max_results_label = QLabel("Max results:")
        row3.addWidget(max_results_label)

        self.max_results_spin = QSpinBox()
        self.max_results_spin.setMinimum(self.ui.MAX_RESULTS_MIN)
        self.max_results_spin.setMaximum(self.ui.MAX_RESULTS_MAX)
        self.max_results_spin.setValue(self.ui.MAX_RESULTS_DEFAULT)
        self.max_results_spin.setFixedWidth(self.ui.SPINBOX_WIDTH)
        self.max_results_spin.setStyleSheet(StyleSheets.text_input(self.ui, self.scale))
        self.max_results_spin.setToolTip("Maximum number of documents to retrieve from database")
        self.max_results_spin.valueChanged.connect(self._on_max_results_changed)
        row3.addWidget(self.max_results_spin)

        # Min Relevant
        min_relevant_label = QLabel("Min relevant:")
        row3.addWidget(min_relevant_label)

        self.min_relevant_spin = QSpinBox()
        self.min_relevant_spin.setMinimum(self.ui.MIN_RELEVANT_MIN)
        self.min_relevant_spin.setMaximum(self.ui.MIN_RELEVANT_MAX)
        self.min_relevant_spin.setValue(self.ui.MIN_RELEVANT_DEFAULT)
        self.min_relevant_spin.setFixedWidth(self.ui.SPINBOX_WIDTH)
        self.min_relevant_spin.setStyleSheet(StyleSheets.text_input(self.ui, self.scale))
        self.min_relevant_spin.setToolTip(
            "Minimum high-scoring documents to find (triggers iterative search)"
        )
        self.min_relevant_spin.valueChanged.connect(self._on_min_relevant_changed)
        row3.addWidget(self.min_relevant_spin)

        # Spacer
        row3.addSpacing(20)

        # Interactive mode toggle
        self.interactive_checkbox = QCheckBox("Interactive mode")
        self.interactive_checkbox.setChecked(False)
        self.interactive_checkbox.setToolTip(
            "Enable human-in-the-loop for query editing, manual scoring, etc."
        )
        row3.addWidget(self.interactive_checkbox)

        # Counterfactual toggle
        self.counterfactual_checkbox = QCheckBox("Counterfactual analysis")
        self.counterfactual_checkbox.setChecked(True)
        self.counterfactual_checkbox.setToolTip(
            "Search for contradictory evidence and create balanced report"
        )
        row3.addWidget(self.counterfactual_checkbox)

        # Study quality rating toggle
        self.study_quality_checkbox = QCheckBox("Study quality rating")
        self.study_quality_checkbox.setChecked(False)
        self.study_quality_checkbox.setToolTip(
            "Assess and display study quality metrics for documents"
        )
        row3.addWidget(self.study_quality_checkbox)

        # Stretch to push everything left
        row3.addStretch()

        controls_layout.addLayout(row3)

        return controls_frame

    def _create_status_bar(self) -> QWidget:
        """
        Create status bar with progress indicator and status messages.

        Layout:
        [Progress indicator / messages (left half)] | [Status / warning messages (right half)]

        Returns:
            Status bar widget
        """
        status_widget = QWidget()
        status_widget.setStyleSheet(f"""
            QWidget {{
                background-color: {self.ui.COLOR_BACKGROUND_GREY};
                border-top: 1px solid {self.ui.COLOR_BORDER_GREY};
            }}
        """)
        status_widget.setMaximumHeight(30)
        status_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        status_layout = QHBoxLayout(status_widget)
        status_layout.setContentsMargins(10, 5, 10, 5)
        status_layout.setSpacing(20)

        # Left half: Progress indicator / messages
        self.progress_label = QLabel("")
        self.progress_label.setStyleSheet(f"color: {self.ui.COLOR_TEXT_GREY};")
        status_layout.addWidget(self.progress_label, stretch=1)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        status_layout.addWidget(separator)

        # Right half: Status / warning messages
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet(f"color: {self.ui.COLOR_TEXT_GREY};")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        status_layout.addWidget(self.status_label, stretch=1)

        return status_widget

    def _create_tabbed_interface(self) -> QTabWidget:
        """
        Create the 8-tab interface for workflow stages.

        Tabs:
        1. Search - Query generation and display
        2. Literature - Document list
        3. Scoring - Document relevance scoring
        4. Citations - Extracted citations
        5. Preliminary - Preliminary report
        6. Counterfactual - Contradictory evidence analysis
        7. Report - Final comprehensive report
        8. Settings - Configuration and preferences

        Returns:
            Tab widget with 8 tabs
        """
        tab_widget = QTabWidget()
        tab_widget.setTabPosition(QTabWidget.TabPosition.North)
        tab_widget.setMovable(False)
        tab_widget.setDocumentMode(False)

        # Create 8 empty tab placeholders
        self.search_tab = self._create_search_tab()
        self.literature_tab = self._create_literature_tab()
        self.scoring_tab = self._create_scoring_tab()
        self.citations_tab = self._create_citations_tab()
        self.preliminary_tab = self._create_preliminary_tab()
        self.counterfactual_tab = self._create_counterfactual_tab()
        self.report_tab = self._create_report_tab()
        self.settings_tab = self._create_settings_tab()

        # Add tabs
        tab_widget.addTab(self.search_tab, "Search")
        tab_widget.addTab(self.literature_tab, "Literature")
        tab_widget.addTab(self.scoring_tab, "Scoring")
        tab_widget.addTab(self.citations_tab, "Citations")
        tab_widget.addTab(self.preliminary_tab, "Preliminary")
        tab_widget.addTab(self.counterfactual_tab, "Counterfactual")
        tab_widget.addTab(self.report_tab, "Report")
        tab_widget.addTab(self.settings_tab, "Settings")

        return tab_widget

    # ========================================================================
    # Tab Creation Methods (Empty placeholders for Phase 1)
    # ========================================================================

    def _create_placeholder_tab(self, icon: str, title: str, description: str) -> QWidget:
        """
        Create a placeholder tab with consistent formatting.

        Args:
            icon: Emoji icon for the tab
            title: Tab title
            description: Bulleted list of what will be displayed

        Returns:
            Placeholder tab widget
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(
            self.ui.TAB_WIDGET_MARGIN,
            self.ui.TAB_WIDGET_MARGIN,
            self.ui.TAB_WIDGET_MARGIN,
            self.ui.TAB_WIDGET_MARGIN
        )

        # Header
        label = QLabel(f"{icon} {title}")
        label_font = QFont()
        label_font.setPointSize(self.ui.TAB_HEADER_FONT_SIZE)
        label_font.setBold(True)
        label.setFont(label_font)
        layout.addWidget(label)

        # Description
        desc_label = QLabel(description)
        desc_label.setStyleSheet(f"color: {self.ui.COLOR_TEXT_GREY}; margin-top: 10px;")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        layout.addStretch()
        return widget

    def _create_search_tab(self) -> QWidget:
        """
        Create Search tab (query generation and display).

        Shows the generated PostgreSQL tsquery and search results summary.
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(
            self.ui.TAB_WIDGET_MARGIN,
            self.ui.TAB_WIDGET_MARGIN,
            self.ui.TAB_WIDGET_MARGIN,
            self.ui.TAB_WIDGET_MARGIN
        )

        # Header
        header = QLabel("🔍 Search Query Generation")
        header_font = QFont()
        header_font.setPointSize(self.ui.TAB_HEADER_FONT_SIZE)
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
        self.query_text_display = QTextEdit()
        self.query_text_display.setReadOnly(True)
        self.query_text_display.setMaximumHeight(100)
        self.query_text_display.setPlaceholderText("Query will appear here after clicking 'Start Research'...")
        self.query_text_display.setStyleSheet("""
            QTextEdit {
                background-color: #F5F5F5;
                border: 1px solid #E0E0E0;
                border-radius: 4px;
                padding: 8px;
                font-family: 'Courier New', monospace;
            }
        """)
        layout.addWidget(self.query_text_display)

        # Results summary section
        results_label = QLabel("Search Results:")
        results_label_font = QFont()
        results_label_font.setBold(True)
        results_label.setFont(results_label_font)
        layout.addWidget(results_label)

        # Document count display
        self.document_count_label = QLabel("No search performed yet")
        self.document_count_label.setStyleSheet(f"color: {self.ui.COLOR_TEXT_GREY};")
        layout.addWidget(self.document_count_label)

        # Add stretch to push everything to the top
        layout.addStretch()

        return widget

    def _create_literature_tab(self) -> QWidget:
        """Create Literature tab (document list with scores)."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(self.ui.TAB_WIDGET_MARGIN, self.ui.TAB_WIDGET_MARGIN,
                                 self.ui.TAB_WIDGET_MARGIN, self.ui.TAB_WIDGET_MARGIN)

        # Header
        header_label = QLabel("📚 Literature Documents")
        header_font = QFont()
        header_font.setPointSize(self.ui.TAB_HEADER_FONT_SIZE)
        header_font.setBold(True)
        header_label.setFont(header_font)
        layout.addWidget(header_label)

        # Subtitle
        subtitle_label = QLabel("Documents retrieved from search with AI relevance scores")
        subtitle_label.setStyleSheet(f"color: {self.ui.COLOR_TEXT_GREY};")
        layout.addWidget(subtitle_label)

        # Document count and score summary
        self.literature_summary_label = QLabel("No documents scored yet")
        self.literature_summary_label.setStyleSheet(f"color: {self.ui.COLOR_TEXT_GREY};")
        layout.addWidget(self.literature_summary_label)

        # Progress bar for scoring (hidden by default)
        from PySide6.QtWidgets import QProgressBar
        self.literature_progress_bar = QProgressBar()
        self.literature_progress_bar.setTextVisible(True)
        self.literature_progress_bar.setFormat("Scoring document %v/%m")
        self.literature_progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #E0E0E0;
                border-radius: 4px;
                text-align: center;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: #2196F3;
                border-radius: 3px;
            }
        """)
        self.literature_progress_bar.setVisible(False)
        layout.addWidget(self.literature_progress_bar)

        # Scroll area for document list
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        # Container widget for document cards
        self.literature_container = QWidget()
        self.literature_layout = QVBoxLayout(self.literature_container)
        self.literature_layout.setSpacing(8)
        self.literature_layout.setContentsMargins(0, 10, 0, 0)

        # Empty state message
        self.literature_empty_label = QLabel("No documents to display")
        self.literature_empty_label.setStyleSheet(f"color: {self.ui.COLOR_TEXT_GREY}; padding: 20px;")
        self.literature_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.literature_layout.addWidget(self.literature_empty_label)

        # Add stretch at bottom
        self.literature_layout.addStretch()

        scroll_area.setWidget(self.literature_container)
        layout.addWidget(scroll_area)

        return widget

    def _create_scoring_tab(self) -> QWidget:
        """Create Scoring tab (document relevance scoring)."""
        return self._create_placeholder_tab(
            "📊",
            "Document Scoring",
            "This tab will display:\n"
            "• Interactive scoring interface (in interactive mode)\n"
            "• Automated scoring results (in auto mode)\n"
            "• Document relevance scores (1-5 scale)\n"
            "• Color-coded score badges\n"
            "• Scoring progress and statistics"
        )

    def _create_citations_tab(self) -> QWidget:
        """Create Citations tab (extracted citations)."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(self.ui.TAB_WIDGET_MARGIN, self.ui.TAB_WIDGET_MARGIN,
                                 self.ui.TAB_WIDGET_MARGIN, self.ui.TAB_WIDGET_MARGIN)

        # Header
        header_label = QLabel("💬 Extracted Citations")
        header_font = QFont()
        header_font.setPointSize(self.ui.TAB_HEADER_FONT_SIZE)
        header_font.setBold(True)
        header_label.setFont(header_font)
        layout.addWidget(header_label)

        # Subtitle
        subtitle_label = QLabel("Relevant passages from high-scoring documents (score ≥ 3.0)")
        subtitle_label.setStyleSheet(f"color: {self.ui.COLOR_TEXT_GREY};")
        layout.addWidget(subtitle_label)

        # Citation count summary
        self.citations_summary_label = QLabel("No citations extracted yet")
        self.citations_summary_label.setStyleSheet(f"color: {self.ui.COLOR_TEXT_GREY};")
        layout.addWidget(self.citations_summary_label)

        # Scroll area for citation list
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        # Container widget for citation cards
        self.citations_container = QWidget()
        self.citations_layout = QVBoxLayout(self.citations_container)
        self.citations_layout.setSpacing(8)
        self.citations_layout.setContentsMargins(0, 10, 0, 0)

        # Empty state message
        self.citations_empty_label = QLabel("No citations to display")
        self.citations_empty_label.setStyleSheet(f"color: {self.ui.COLOR_TEXT_GREY}; padding: 20px;")
        self.citations_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.citations_layout.addWidget(self.citations_empty_label)

        # Add stretch at bottom
        self.citations_layout.addStretch()

        scroll_area.setWidget(self.citations_container)
        layout.addWidget(scroll_area)

        return widget

    def _create_preliminary_tab(self) -> QWidget:
        """Create Preliminary Report tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(self.ui.TAB_WIDGET_MARGIN, self.ui.TAB_WIDGET_MARGIN,
                                 self.ui.TAB_WIDGET_MARGIN, self.ui.TAB_WIDGET_MARGIN)

        # Header
        header_label = QLabel("📄 Preliminary Report")
        header_font = QFont()
        header_font.setPointSize(self.ui.TAB_HEADER_FONT_SIZE)
        header_font.setBold(True)
        header_label.setFont(header_font)
        layout.addWidget(header_label)

        # Subtitle
        subtitle_label = QLabel("Report generated from extracted citations (before counterfactual analysis)")
        subtitle_label.setStyleSheet(f"color: {self.ui.COLOR_TEXT_GREY};")
        layout.addWidget(subtitle_label)

        # Report statistics summary
        self.preliminary_report_summary_label = QLabel("No report generated yet")
        self.preliminary_report_summary_label.setStyleSheet(f"color: {self.ui.COLOR_TEXT_GREY};")
        layout.addWidget(self.preliminary_report_summary_label)

        # Markdown viewer for report
        self.preliminary_report_viewer = MarkdownViewer()
        self.preliminary_report_viewer.set_markdown("_No report available yet. Please run a research workflow first._")
        layout.addWidget(self.preliminary_report_viewer)

        return widget

    def _create_counterfactual_tab(self) -> QWidget:
        """Create Counterfactual Analysis tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # Header
        header = QLabel("🧠 Counterfactual Analysis")
        header_font = QFont()
        header_font.setPointSize(self.ui.TAB_HEADER_FONT_SIZE)
        header_font.setBold(True)
        header.setFont(header_font)
        layout.addWidget(header)

        # Summary label
        self.counterfactual_summary_label = QLabel("Waiting for analysis...")
        self.counterfactual_summary_label.setStyleSheet(f"color: {self.ui.COLOR_TEXT_GREY};")
        layout.addWidget(self.counterfactual_summary_label)

        # Scroll area for counterfactual content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        # Content widget
        content_widget = QWidget()
        self.counterfactual_layout = QVBoxLayout(content_widget)
        self.counterfactual_layout.setSpacing(10)
        self.counterfactual_layout.setContentsMargins(0, 0, 0, 0)

        # Initial placeholder
        placeholder = QLabel(
            "Counterfactual analysis will appear here when enabled.\n\n"
            "This analysis:\n"
            "• Identifies key claims in the preliminary report\n"
            "• Generates research questions to find contradictory evidence\n"
            "• Searches for documents that might contradict the findings\n"
            "• Provides a balanced view of the evidence"
        )
        placeholder.setStyleSheet(f"color: {self.ui.COLOR_TEXT_GREY}; padding: 20px;")
        placeholder.setWordWrap(True)
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.counterfactual_layout.addWidget(placeholder)
        self.counterfactual_layout.addStretch()

        scroll.setWidget(content_widget)
        layout.addWidget(scroll, stretch=1)

        return tab

    def _create_report_tab(self) -> QWidget:
        """Create Final Report tab with export buttons."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Header row with title and export buttons
        header_row = QHBoxLayout()

        # Header label
        header_label = QLabel("📋 Final Comprehensive Report")
        header_label.setStyleSheet(f"font-size: 14pt; font-weight: bold; color: {self.ui.COLOR_PRIMARY_BLUE};")
        header_row.addWidget(header_label)

        header_row.addStretch()

        # Export buttons container
        export_buttons_layout = QHBoxLayout()
        export_buttons_layout.setSpacing(10)

        # Save Markdown button
        self.report_save_markdown_button = QPushButton("Save Report (Markdown)")
        self.report_save_markdown_button.setIcon(self.report_save_markdown_button.style().standardIcon(
            self.report_save_markdown_button.style().StandardPixmap.SP_DialogSaveButton
        ))
        self.report_save_markdown_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
            QPushButton:disabled {
                background-color: #BDBDBD;
                color: #757575;
            }
        """)
        self.report_save_markdown_button.setEnabled(False)  # Disabled until report is ready
        self.report_save_markdown_button.clicked.connect(self._on_save_markdown_report)
        export_buttons_layout.addWidget(self.report_save_markdown_button)

        # Export JSON button
        self.report_export_json_button = QPushButton("Export as JSON")
        self.report_export_json_button.setIcon(self.report_export_json_button.style().standardIcon(
            self.report_export_json_button.style().StandardPixmap.SP_FileDialogDetailedView
        ))
        self.report_export_json_button.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:pressed {
                background-color: #1565C0;
            }
            QPushButton:disabled {
                background-color: #BDBDBD;
                color: #757575;
            }
        """)
        self.report_export_json_button.setEnabled(False)  # Disabled until report is ready
        self.report_export_json_button.clicked.connect(self._on_export_json_report)
        export_buttons_layout.addWidget(self.report_export_json_button)

        header_row.addLayout(export_buttons_layout)
        layout.addLayout(header_row)

        # Summary label
        self.report_summary_label = QLabel("No report generated yet")
        self.report_summary_label.setStyleSheet(f"color: {self.ui.COLOR_TEXT_GREY};")
        layout.addWidget(self.report_summary_label)

        # Markdown viewer
        self.report_viewer = MarkdownViewer()
        self.report_viewer.set_markdown("_No final report available yet. The final report will be generated after counterfactual analysis._")
        layout.addWidget(self.report_viewer)

        return widget

    def _create_settings_tab(self) -> QWidget:
        """Create Settings tab using the modular SettingsPlugin."""
        from ..settings import SettingsPlugin

        # Create the settings plugin
        self.settings_plugin = SettingsPlugin(self)

        # Connect signal to reinitialize agents when settings change
        self.settings_plugin.agents_need_reinit.connect(self._reinitialize_agents)

        return self.settings_plugin

    def _reinitialize_agents(self):
        """Reinitialize agents with new configuration from settings."""
        try:
            from bmlibrarian.agents import (
                QueryAgent, DocumentScoringAgent, CitationFinderAgent,
                ReportingAgent, CounterfactualAgent, EditorAgent, AgentOrchestrator
            )

            self.logger.info("🔧 Reinitializing agents with new configuration...")

            # Create new orchestrator
            orchestrator = AgentOrchestrator(max_workers=4)

            # Reinitialize all agents
            self.agents = {
                'query_agent': QueryAgent(orchestrator=orchestrator),
                'scoring_agent': DocumentScoringAgent(orchestrator=orchestrator),
                'citation_agent': CitationFinderAgent(orchestrator=orchestrator),
                'reporting_agent': ReportingAgent(orchestrator=orchestrator),
                'counterfactual_agent': CounterfactualAgent(orchestrator=orchestrator),
                'editor_agent': EditorAgent(orchestrator=orchestrator)
            }

            self.logger.info("✅ Agents reinitialized successfully")

        except Exception as e:
            self.logger.error(f"⚠️ Error reinitializing agents: {e}", exc_info=True)

    # ========================================================================
    # Event Handlers
    # ========================================================================

    @Slot()
    def _on_question_changed(self) -> None:
        """Handle research question text changes."""
        try:
            has_text = len(self.question_input.toPlainText().strip()) > 0
            self.start_button.setEnabled(has_text and not self.workflow_running)
        except Exception as e:
            self.logger.error(f"Error in _on_question_changed: {e}", exc_info=True)

    @Slot(int)
    def _on_max_results_changed(self, value: int) -> None:
        """
        Handle max results value changes with validation.

        Args:
            value: New max results value
        """
        try:
            # Prevent infinite validation loops
            if self._validation_in_progress:
                return

            # Validate: max_results should not be less than min_relevant
            min_relevant = self.min_relevant_spin.value()
            if value < min_relevant:
                self.logger.warning(
                    f"Max results ({value}) is less than min relevant ({min_relevant}). "
                    "Adjusting min relevant."
                )
                self._validation_in_progress = True
                try:
                    self.min_relevant_spin.setValue(value)
                finally:
                    self._validation_in_progress = False
        except Exception as e:
            self.logger.error(f"Error in _on_max_results_changed: {e}", exc_info=True)

    @Slot(int)
    def _on_min_relevant_changed(self, value: int) -> None:
        """
        Handle min relevant value changes with validation.

        Args:
            value: New min relevant value
        """
        try:
            # Prevent infinite validation loops
            if self._validation_in_progress:
                return

            # Validate: min_relevant should not exceed max_results
            max_results = self.max_results_spin.value()
            if value > max_results:
                self.logger.warning(
                    f"Min relevant ({value}) exceeds max results ({max_results}). "
                    "Adjusting max results."
                )
                self._validation_in_progress = True
                try:
                    self.max_results_spin.setValue(value)
                finally:
                    self._validation_in_progress = False
        except Exception as e:
            self.logger.error(f"Error in _on_min_relevant_changed: {e}", exc_info=True)

    @Slot()
    def _on_start_research(self) -> None:
        """Handle Start Research button click with error handling."""
        try:
            # Prevent concurrent workflow execution
            if self.workflow_running:
                self.logger.warning("Workflow already running - ignoring duplicate start request")
                QMessageBox.warning(
                    self,
                    "Workflow Running",
                    "A research workflow is already in progress.\n\n"
                    "Please wait for it to complete before starting a new one."
                )
                return

            question = self.question_input.toPlainText().strip()

            if not question:
                QMessageBox.warning(
                    self,
                    "No Question",
                    "Please enter a research question before starting."
                )
                return

            # Validate parameters
            max_results = self.max_results_spin.value()
            min_relevant = self.min_relevant_spin.value()

            if min_relevant > max_results:
                QMessageBox.warning(
                    self,
                    "Invalid Parameters",
                    f"Min relevant ({min_relevant}) cannot exceed max results ({max_results}).\n\n"
                    "Please adjust the values."
                )
                return

            # Check if workflow executor is available
            if not self.workflow_executor:
                QMessageBox.critical(
                    self,
                    "Agents Not Initialized",
                    "BMLibrarian agents are not initialized.\n\n"
                    "The application may have failed to start properly.\n"
                    "Please check the logs and restart the application."
                )
                return

            # Milestone 4: Create and start background workflow thread
            self.status_message.emit(f"Research started: {question[:50]}...")

            # Update status bar
            self.progress_label.setText("Initializing workflow...")
            self.status_label.setText("Starting")

            self.workflow_running = True

            self.logger.info(f"Research started: {question[:100]}")
            self.logger.debug(
                f"Parameters: max_results={max_results}, min_relevant={min_relevant}, "
                f"interactive={self.interactive_checkbox.isChecked()}, "
                f"counterfactual={self.counterfactual_checkbox.isChecked()}"
            )

            # Create and configure workflow thread
            from .workflow_thread import WorkflowThread

            self.workflow_thread = WorkflowThread(
                executor=self.workflow_executor,
                question=question,
                max_results=max_results,
                score_threshold=3.0,  # Use relevance threshold
                enable_counterfactual=self.counterfactual_checkbox.isChecked(),
                parent=self
            )

            # Connect thread signals to UI handlers
            self._connect_workflow_thread_signals()

            # Start thread
            self.workflow_thread.start()
            self.logger.info("Background workflow thread started")

        except Exception as e:
            self.logger.error(f"Error in _on_start_research: {e}", exc_info=True)
            self.start_button.setEnabled(True)
            self.workflow_running = False
            QMessageBox.critical(
                self,
                "Error",
                f"An error occurred while starting research:\n\n{str(e)}"
            )
            self.workflow_error.emit(e)

    # ========================================================================
    # Workflow Signal Handlers
    # ========================================================================

    @Slot()
    def _on_workflow_started(self) -> None:
        """Handle workflow started signal."""
        self.logger.info("Workflow started")
        self.workflow_running = True

        # Hide Start button, show Cancel button
        self.start_button.setVisible(False)
        self.cancel_button.setVisible(True)
        self.cancel_button.setEnabled(True)

        # Update status bar
        self.status_label.setText("Running")
        self.progress_label.setText("Starting research workflow...")

        self.workflow_started.emit()

    @Slot(dict)
    def _on_workflow_completed(self, results: dict) -> None:
        """Handle workflow completed signal."""
        self.logger.info(f"Workflow completed: {results.get('status', 'unknown')}")
        self.workflow_running = False

        # Show Start button, hide Cancel button
        self.start_button.setVisible(True)
        self.start_button.setEnabled(True)
        self.cancel_button.setVisible(False)

        # Update status bar
        self.status_label.setText("Completed")
        self.progress_label.setText("Research workflow completed successfully")

        self.current_results = results
        self.workflow_completed.emit(results)

        # Check which phase/milestone completed
        phase = results.get('phase', 'unknown')
        milestone = results.get('milestone', None)

        if phase == 2:
            # Phase 2: Agent connection test
            QMessageBox.information(
                self,
                "Phase 2 Complete - Agents Connected!",
                f"Research question: {results.get('question', 'N/A')}\n\n"
                "✅ All agents are initialized and ready!\n\n"
                "Agent connection test successful:\n"
                "• QueryAgent\n"
                "• ScoringAgent\n"
                "• CitationAgent\n"
                "• ReportingAgent\n"
                "• EditorAgent\n"
                "• CounterfactualAgent (optional)\n\n"
                "Phase 3 will implement full workflow execution."
            )
        elif phase == 3 and milestone == 1:
            # Milestone 1: Query generation and search complete
            document_count = results.get('document_count', 0)
            query = results.get('query', 'N/A')

            QMessageBox.information(
                self,
                "Milestone 1 Complete - Search Successful!",
                f"Research question: {results.get('question', 'N/A')}\n\n"
                f"✅ Search completed successfully!\n\n"
                f"Query: {query[:100]}{'...' if len(query) > 100 else ''}\n\n"
                f"Found {document_count} documents\n\n"
                "Check the 'Search' tab to see the query and results summary."
            )
        elif phase == 3 and milestone == 3:
            # Milestone 3: Citations and preliminary report complete
            document_count = results.get('document_count', 0)
            citation_count = results.get('citation_count', 0)
            report_length = results.get('report_length', 0)
            word_count = len(results.get('preliminary_report', '').split())

            QMessageBox.information(
                self,
                "Milestone 3 Complete - Report Generated!",
                f"Research question: {results.get('question', 'N/A')}\n\n"
                f"✅ Research workflow completed successfully!\n\n"
                f"Results:\n"
                f"• {document_count} documents found and scored\n"
                f"• {citation_count} citations extracted\n"
                f"• Preliminary report generated (~{word_count} words)\n\n"
                "Check the tabs:\n"
                "• 'Citations' tab - Extracted citations\n"
                "• 'Preliminary' tab - Generated report\n\n"
                "Next milestone will add counterfactual analysis."
            )

    @Slot(Exception)
    def _on_workflow_error(self, error: Exception) -> None:
        """Handle workflow error signal."""
        self.logger.error(f"Workflow error: {error}", exc_info=True)
        self.workflow_running = False

        # Show Start button, hide Cancel button
        self.start_button.setVisible(True)
        self.start_button.setEnabled(True)
        self.cancel_button.setVisible(False)

        # Update status bar
        self.status_label.setText("⚠️ Error")
        self.progress_label.setText("Workflow failed - see error message")

        self.workflow_error.emit(error)

        QMessageBox.critical(
            self,
            "Workflow Error",
            f"An error occurred during workflow execution:\n\n{str(error)}"
        )

    @Slot(str)
    def _on_workflow_status(self, message: str) -> None:
        """Handle workflow status message signal."""
        self.logger.debug(f"Workflow status: {message}")
        # Update progress label with status messages
        self.progress_label.setText(message)
        self.status_message.emit(message)

    # ========================================================================
    # Workflow Thread Methods (Milestone 4: Background Execution)
    # ========================================================================

    def _connect_workflow_thread_signals(self) -> None:
        """Connect workflow thread signals to UI handlers."""
        if not self.workflow_thread:
            return

        # Progress signals
        self.workflow_thread.step_started.connect(self._on_thread_step_started)
        self.workflow_thread.step_progress.connect(self._on_thread_step_progress)
        self.workflow_thread.step_completed.connect(self._on_thread_step_completed)
        self.workflow_thread.status_message.connect(self._on_workflow_status)

        # Result signals (reuse existing handlers)
        self.workflow_thread.query_generated.connect(self._on_query_generated)
        self.workflow_thread.documents_found.connect(self._on_documents_found)
        self.workflow_thread.documents_scored.connect(self._on_documents_scored)
        self.workflow_thread.citations_extracted.connect(self._on_citations_extracted)
        self.workflow_thread.preliminary_report_generated.connect(self._on_preliminary_report_generated)

        # Counterfactual analysis signals
        self.workflow_thread.counterfactual_analysis_complete.connect(self._on_counterfactual_analysis_complete)
        self.workflow_thread.final_report_generated.connect(self._on_final_report_generated)

        # Completion signals
        self.workflow_thread.workflow_completed.connect(self._on_thread_workflow_completed)
        self.workflow_thread.workflow_error.connect(self._on_thread_workflow_error)
        self.workflow_thread.workflow_cancelled.connect(self._on_thread_workflow_cancelled)

        # Thread finished signal for cleanup
        self.workflow_thread.finished.connect(self._on_thread_finished)

        self.logger.info("Workflow thread signals connected")

    @Slot()
    def _on_cancel_clicked(self) -> None:
        """Handle Cancel button click."""
        if not self.workflow_thread or not self.workflow_thread.isRunning():
            self.logger.warning("Cancel clicked but no workflow thread is running")
            return

        self.logger.info("User requested workflow cancellation")
        self.cancel_button.setEnabled(False)  # Prevent double-cancel
        self.progress_label.setText("Cancelling workflow...")
        self.status_label.setText("Cancelled")
        self.workflow_thread.cancel()

    def _on_new_research(self) -> None:
        """Handle New button click to start a fresh research session."""
        # Confirm if there are unsaved results
        if self.current_results or self.counterfactual_results:
            reply = QMessageBox.question(
                self,
                "Start New Research",
                "This will clear your current research results.\n\n"
                "Are you sure you want to start a new research session?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return

        # Clear all results and UI
        self.current_results = {}
        self.counterfactual_results = None
        self.question_input.clear()

        # Clear all tabs (delegate to tab-specific methods if they exist)
        # For now, we'll just log this action
        self.logger.info("Starting new research session - clearing previous results")

        # Update status
        self.status_label.setText("Ready")
        self.progress_label.setText("")

        # Focus on question input
        self.question_input.setFocus()

    @Slot(str, str)
    def _on_thread_step_started(self, step_name: str, description: str) -> None:
        """Handle workflow step started signal."""
        self.logger.info(f"Step started: {step_name} - {description}")
        self.progress_label.setText(f"⚙️ {description}")

        # Update status label based on major steps
        if 'query' in step_name.lower():
            self.status_label.setText("Generating query")
        elif 'search' in step_name.lower():
            self.status_label.setText("Searching documents")
        elif 'scor' in step_name.lower():
            self.status_label.setText("Scoring documents")
        elif 'citation' in step_name.lower():
            self.status_label.setText("Extracting citations")
        elif 'report' in step_name.lower():
            self.status_label.setText("Generating report")
        elif 'counterfactual' in step_name.lower():
            self.status_label.setText("Analyzing evidence")

    @Slot(str, int, int)
    def _on_thread_step_progress(self, step_name: str, current: int, total: int) -> None:
        """Handle workflow step progress signal."""
        if total > 0:
            percentage = int((current / total) * 100)
            self.progress_label.setText(f"⚙️ Processing {current}/{total} documents... ({percentage}%)")

    @Slot(str)
    def _on_thread_step_completed(self, step_name: str) -> None:
        """Handle workflow step completed signal."""
        self.logger.info(f"Step completed: {step_name}")

    @Slot(dict)
    def _on_thread_workflow_completed(self, results: dict) -> None:
        """Handle workflow completed signal from thread."""
        self.logger.info(f"Thread workflow completed: {results.get('status', 'unknown')}")

        # Update UI state
        self.workflow_running = False

        # Show Start button, hide Cancel button
        self.start_button.setVisible(True)
        self.start_button.setEnabled(True)
        self.cancel_button.setVisible(False)

        # Update status bar
        doc_count = results.get('document_count', 0)
        citation_count = results.get('citation_count', 0)
        self.progress_label.setText(
            f"✅ Found {doc_count} documents, extracted {citation_count} citations"
        )
        self.status_label.setText("Completed")

        # Store results
        self.current_results = results

        # Emit completion signal
        self.workflow_completed.emit(results)

    @Slot(Exception)
    def _on_thread_workflow_error(self, error: Exception) -> None:
        """Handle workflow error signal from thread."""
        self.logger.error(f"Thread workflow error: {error}", exc_info=True)

        # Update UI state
        self.workflow_running = False

        # Show Start button, hide Cancel button
        self.start_button.setVisible(True)
        self.start_button.setEnabled(True)
        self.cancel_button.setVisible(False)

        # Update status bar
        self.progress_label.setText("❌ Workflow failed - see error message")
        self.status_label.setText("⚠️ Error")

        # Emit error signal
        self.workflow_error.emit(error)

        # Show error dialog
        QMessageBox.critical(
            self,
            "Workflow Error",
            f"An error occurred during workflow execution:\n\n{str(error)}"
        )

    @Slot()
    def _on_thread_workflow_cancelled(self) -> None:
        """Handle workflow cancelled signal from thread."""
        self.logger.info("Workflow cancelled by user")

        # Update UI state
        self.workflow_running = False

        # Show Start button, hide Cancel button
        self.start_button.setVisible(True)
        self.start_button.setEnabled(True)
        self.cancel_button.setVisible(False)

        # Update status bar
        self.progress_label.setText("🛑 Workflow cancelled by user")
        self.status_label.setText("Cancelled")

        self.status_message.emit("🛑 Workflow cancelled by user")

    @Slot()
    def _on_thread_finished(self) -> None:
        """Handle thread finished signal for cleanup."""
        self.logger.info("Workflow thread finished")
        if self.workflow_thread:
            self.workflow_thread.deleteLater()
            self.workflow_thread = None

    # ========================================================================
    # Step-Specific Signal Handlers (Milestone 1)
    # ========================================================================

    @Slot(str)
    def _on_query_generated(self, query: str) -> None:
        """
        Handle query generated signal.

        Updates the Search tab to display the generated query.

        Args:
            query: The generated PostgreSQL tsquery string
        """
        self.logger.info(f"Query generated: {query}")

        # Update the query display in the Search tab
        if hasattr(self, 'query_text_display'):
            self.query_text_display.setPlainText(query)

        self.status_message.emit(f"Query generated: {query[:50]}...")

    @Slot(list)
    def _on_documents_found(self, documents: list) -> None:
        """
        Handle documents found signal.

        Updates the Search tab to display the document count and populates
        the Literature tab with document cards (without scores).

        Args:
            documents: List of document dictionaries
        """
        doc_count = len(documents)
        self.logger.info(f"Documents found: {doc_count}")

        # Update the document count display in the Search tab
        if hasattr(self, 'document_count_label'):
            self.document_count_label.setText(
                f"✅ Found {doc_count} documents matching your query"
            )
            self.document_count_label.setStyleSheet(f"color: {self.ui.COLOR_PRIMARY_BLUE};")

        # Populate Literature tab with unscored documents
        self._populate_literature_tab_with_unscored_documents(documents)

        self.status_message.emit(f"Found {doc_count} documents")

    @Slot(int, int)
    def _on_scoring_progress(self, current: int, total: int) -> None:
        """
        Handle scoring progress signal (Milestone 2).

        Updates the progress bar in the Literature tab.

        Args:
            current: Current document number being scored
            total: Total number of documents to score
        """
        if hasattr(self, 'literature_progress_bar'):
            # Show progress bar if it's hidden
            if not self.literature_progress_bar.isVisible():
                self.literature_progress_bar.setVisible(True)

            # Update progress
            self.literature_progress_bar.setMaximum(total)
            self.literature_progress_bar.setValue(current)

    @Slot(list)
    def _on_documents_scored(self, scored_documents: list) -> None:
        """
        Handle documents scored signal (Milestone 2).

        Updates the Literature tab to display scored documents.

        Args:
            scored_documents: List of (document, score_result) tuples
        """
        self.logger.info(f"Documents scored: {len(scored_documents)}")

        # Hide progress bar
        if hasattr(self, 'literature_progress_bar'):
            self.literature_progress_bar.setVisible(False)

        # Update the Literature tab with scored documents
        self._update_literature_tab(scored_documents)

        # Update summary label
        total = len(scored_documents)
        # Type-safe score extraction with validation
        high_scoring = len([
            d for d, s in scored_documents
            if isinstance(s.get('score'), (int, float)) and s.get('score', 0) >= self.ui.SCORE_THRESHOLD_RELEVANT
        ])

        if hasattr(self, 'literature_summary_label'):
            self.literature_summary_label.setText(
                f"✅ {total} documents scored | {high_scoring} highly relevant (score ≥ {self.ui.SCORE_THRESHOLD_RELEVANT})"
            )

        self.status_message.emit(f"Scored {total} documents ({high_scoring} highly relevant)")

    @Slot(list)
    def _on_citations_extracted(self, citations: list) -> None:
        """
        Handle citations extracted signal (Milestone 3).

        Updates the Citations tab to display extracted citations.

        Args:
            citations: List of citation dictionaries
        """
        self.logger.info(f"Citations extracted: {len(citations)}")

        # Update the Citations tab with citations
        self._update_citations_tab(citations)

        # Update summary label
        if hasattr(self, 'citations_summary_label'):
            self.citations_summary_label.setText(
                f"✅ {len(citations)} citations extracted from high-scoring documents"
            )

        self.status_message.emit(f"Extracted {len(citations)} citations")

    @Slot(str)
    def _on_preliminary_report_generated(self, report: str) -> None:
        """
        Handle preliminary report generated signal (Milestone 3).

        Updates the Preliminary Report tab to display the generated report.

        Args:
            report: Markdown-formatted preliminary report
        """
        self.logger.info(f"Preliminary report generated ({len(report)} characters)")

        # Update the Preliminary Report tab with markdown
        if hasattr(self, 'preliminary_report_viewer'):
            self.preliminary_report_viewer.set_markdown(report)

        # Update summary label (word count approximation)
        word_count = len(report.split())
        if hasattr(self, 'preliminary_report_summary_label'):
            self.preliminary_report_summary_label.setText(
                f"✅ Report generated | ~{word_count} words | {len(report)} characters"
            )

        self.status_message.emit(f"Generated preliminary report ({word_count} words)")

    @Slot(dict)
    def _on_counterfactual_analysis_complete(self, results: dict) -> None:
        """
        Handle counterfactual analysis complete signal.

        Updates the Counterfactual tab with analysis results.

        Args:
            results: Dictionary with counterfactual analysis results
        """
        self.logger.info(f"Counterfactual analysis complete: {results.get('question_count', 0)} questions")

        # Store results for later display
        self.counterfactual_results = results

        # Update status
        question_count = results.get('question_count', 0)
        doc_count = results.get('document_count', 0)
        self.status_message.emit(
            f"Counterfactual analysis: {question_count} questions, {doc_count} contradictory documents"
        )

        # Update Counterfactual tab (will be implemented next)
        self._update_counterfactual_tab(results)

    @Slot(str)
    def _on_final_report_generated(self, report: str) -> None:
        """
        Handle final comprehensive report generated signal.

        Updates the Report tab with the comprehensive balanced report.

        Args:
            report: Markdown-formatted comprehensive report
        """
        self.logger.info(f"Final report generated ({len(report)} characters)")

        # Store the final report for export
        self.final_report_markdown = report

        # Update the Report tab with markdown
        if hasattr(self, 'report_viewer'):
            self.report_viewer.set_markdown(report)

        # Update summary label (word count approximation)
        word_count = len(report.split())
        if hasattr(self, 'report_summary_label'):
            self.report_summary_label.setText(
                f"✅ Comprehensive report generated | ~{word_count} words | {len(report)} characters"
            )

        # Enable export buttons
        if hasattr(self, 'report_save_markdown_button'):
            self.report_save_markdown_button.setEnabled(True)
        if hasattr(self, 'report_export_json_button'):
            self.report_export_json_button.setEnabled(True)

        self.status_message.emit(f"Generated comprehensive final report ({word_count} words)")

    def _update_counterfactual_tab(self, results: dict) -> None:
        """
        Update the Counterfactual tab with analysis results.

        Args:
            results: Dictionary containing counterfactual analysis results
        """
        try:
            # Clear existing widgets
            self._clear_layout_widgets(self.counterfactual_layout)

            # Update summary label
            question_count = results.get('question_count', 0)
            doc_count = results.get('document_count', 0)
            self.counterfactual_summary_label.setText(
                f"✅ Analysis complete | {question_count} counterfactual questions | "
                f"{doc_count} potentially contradictory documents found"
            )

            if question_count == 0:
                # Show message if no questions generated
                no_questions_label = QLabel("No counterfactual questions were generated.")
                no_questions_label.setStyleSheet(f"color: {self.ui.COLOR_TEXT_GREY}; padding: 20px;")
                no_questions_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.counterfactual_layout.addWidget(no_questions_label)
                self.counterfactual_layout.addStretch()
                return

            # Display counterfactual questions
            questions = results.get('questions', [])
            for i, question in enumerate(questions, 1):
                # Create question card
                card = QFrame()
                card.setFrameShape(QFrame.Shape.StyledPanel)
                card.setStyleSheet(f"""
                    QFrame {{
                        background-color: {self.ui.COLOR_WHITE};
                        border: 1px solid {self.ui.COLOR_BORDER_GREY};
                        border-radius: 6px;
                        padding: 12px;
                    }}
                """)

                card_layout = QVBoxLayout(card)
                card_layout.setSpacing(8)

                # Question number and priority
                header_layout = QHBoxLayout()
                question_number = QLabel(f"Question {i}")
                question_number.setStyleSheet("font-weight: bold; font-size: 11pt;")
                header_layout.addWidget(question_number)

                priority = getattr(question, 'priority', 'MEDIUM')
                priority_label = QLabel(f"Priority: {priority}")
                priority_colors = {
                    'HIGH': '#F44336',
                    'MEDIUM': '#FF9800',
                    'LOW': '#9E9E9E'
                }
                priority_color = priority_colors.get(priority, '#9E9E9E')
                priority_label.setStyleSheet(f"color: {priority_color}; font-weight: bold;")
                header_layout.addWidget(priority_label)
                header_layout.addStretch()

                card_layout.addLayout(header_layout)

                # Research question
                question_text = getattr(question, 'question', 'No question text')
                question_label = QLabel(f"<b>Research Question:</b><br>{question_text}")
                question_label.setWordWrap(True)
                question_label.setStyleSheet("padding: 4px;")
                card_layout.addWidget(question_label)

                # Counterfactual statement
                cf_statement = getattr(question, 'counterfactual_statement', '')
                if cf_statement:
                    statement_label = QLabel(f"<b>Counterfactual Statement:</b><br>{cf_statement}")
                    statement_label.setWordWrap(True)
                    statement_label.setStyleSheet(f"padding: 4px; color: {self.ui.COLOR_TEXT_GREY};")
                    card_layout.addWidget(statement_label)

                # Reasoning
                reasoning = getattr(question, 'reasoning', '')
                if reasoning:
                    reasoning_label = QLabel(f"<b>Reasoning:</b><br>{reasoning}")
                    reasoning_label.setWordWrap(True)
                    reasoning_label.setStyleSheet("padding: 4px; font-style: italic;")
                    card_layout.addWidget(reasoning_label)

                # Search keywords
                keywords = getattr(question, 'search_keywords', [])
                if keywords:
                    keywords_text = ", ".join(keywords[:10])  # Limit display
                    keywords_label = QLabel(f"<b>Search Keywords:</b> {keywords_text}")
                    keywords_label.setWordWrap(True)
                    keywords_label.setStyleSheet(f"padding: 4px; color: {self.ui.COLOR_TEXT_GREY}; font-size: 9pt;")
                    card_layout.addWidget(keywords_label)

                self.counterfactual_layout.addWidget(card)

            # Display contradictory documents using document card factory
            contradictory_docs = results.get('contradictory_documents', [])
            if contradictory_docs:
                # Add section header
                doc_header = QLabel(f"\n📚 Potentially Contradictory Documents ({len(contradictory_docs)})")
                doc_header.setStyleSheet("font-weight: bold; font-size: 11pt; padding-top: 15px; padding-bottom: 5px;")
                self.counterfactual_layout.addWidget(doc_header)

                # Create document cards using factory
                cards_created = 0
                for i, doc in enumerate(contradictory_docs):
                    try:
                        # Extract year from publication_date or year field
                        publication_date = doc.get('publication_date', '')
                        year = doc.get('year', '')
                        if publication_date and publication_date != 'Unknown':
                            year_value = int(str(publication_date)[:4]) if len(str(publication_date)) >= 4 else (int(year) if year else None)
                        else:
                            year_value = int(year) if year else None

                        # Create DocumentCardData for counterfactual context
                        card_data = DocumentCardData(
                            doc_id=doc.get('id', 0),
                            title=doc.get('title', 'Untitled Document'),
                            abstract=doc.get('abstract', ''),
                            authors=doc.get('authors', []),
                            year=year_value,
                            journal=doc.get('publication', ''),
                            pmid=doc.get('pmid'),
                            doi=doc.get('doi'),
                            source=doc.get('source'),
                            pdf_url=doc.get('pdf_url'),
                            context=CardContext.COUNTERFACTUAL,
                            show_abstract=True,
                            show_metadata=True,
                            show_pdf_button=True,
                            expanded_by_default=False
                        )

                        # Create card using factory
                        card = self.document_card_factory.create_card(card_data)

                        # Add counterfactual question tag if available
                        cf_question = doc.get('_counterfactual_question')
                        cf_priority = doc.get('_counterfactual_priority')
                        if cf_question and hasattr(card, 'details_layout'):
                            cf_info_container = QFrame()
                            cf_info_container.setStyleSheet("""
                                QFrame {
                                    background-color: #FFF9C4;
                                    border: 1px solid #FFF176;
                                    border-radius: 3px;
                                    padding: 8px;
                                }
                            """)
                            cf_info_layout = QVBoxLayout(cf_info_container)
                            cf_info_layout.setContentsMargins(8, 8, 8, 8)
                            cf_info_layout.setSpacing(5)

                            cf_title = QLabel(f"<b>Related Counterfactual Question:</b>")
                            if cf_priority:
                                priority_colors = {'HIGH': '#F44336', 'MEDIUM': '#FF9800', 'LOW': '#9E9E9E'}
                                priority_color = priority_colors.get(cf_priority, '#9E9E9E')
                                cf_title.setText(f"<b>Related Counterfactual Question</b> <span style='color: {priority_color};'>[{cf_priority} Priority]</span>")
                            cf_title.setStyleSheet(f"font-size: {self.ui.CARD_LABEL_FONT_SIZE}pt; background-color: transparent; border: none;")
                            cf_info_layout.addWidget(cf_title)

                            cf_question_text = QLabel(cf_question)
                            cf_question_text.setWordWrap(True)
                            cf_question_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                            cf_question_text.setStyleSheet(f"color: #333; font-size: {self.ui.CARD_BODY_FONT_SIZE}pt; background-color: transparent; border: none;")
                            cf_info_layout.addWidget(cf_question_text)

                            # Insert at the beginning of details_layout (before abstract)
                            card.details_layout.insertWidget(0, cf_info_container)

                        self.counterfactual_layout.addWidget(card)
                        cards_created += 1
                    except Exception as card_error:
                        self.logger.error(f"Error creating counterfactual document card {i+1}: {card_error}", exc_info=True)

                self.logger.info(f"Counterfactual tab updated with {cards_created}/{len(contradictory_docs)} document cards")

            # Display contradictory citations (extracted passages from contradictory documents)
            contradictory_citations = results.get('contradictory_citations', [])
            if contradictory_citations:
                # Add section header for citations
                citations_header = QLabel(f"\n💬 Contradictory Citations ({len(contradictory_citations)})")
                citations_header.setStyleSheet("font-weight: bold; font-size: 11pt; padding-top: 15px; padding-bottom: 5px;")
                self.counterfactual_layout.addWidget(citations_header)

                citations_desc = QLabel(
                    "Specific passages extracted from contradictory documents that challenge the original claims:"
                )
                citations_desc.setStyleSheet(f"color: {self.ui.COLOR_TEXT_GREY}; font-size: 10pt; padding-bottom: 10px;")
                citations_desc.setWordWrap(True)
                self.counterfactual_layout.addWidget(citations_desc)

                # Import CitationCard widget
                from ...widgets.citation_card import CitationCard

                # Create citation cards
                for i, citation_info in enumerate(contradictory_citations, 1):
                    try:
                        # Extract citation object (may be wrapped in dict)
                        if isinstance(citation_info, dict) and 'citation' in citation_info:
                            citation = citation_info['citation']
                            original_claim = citation_info.get('original_claim', '')
                            cf_question = citation_info.get('counterfactual_question', '')
                        else:
                            citation = citation_info
                            original_claim = ''
                            cf_question = ''

                        # Create citation card using the existing widget
                        citation_card = CitationCard(citation, index=i)

                        # Add context information if available
                        if original_claim or cf_question:
                            context_frame = QFrame()
                            context_frame.setStyleSheet("""
                                QFrame {
                                    background-color: #FFF9C4;
                                    border: 1px solid #FFF176;
                                    border-radius: 3px;
                                    padding: 8px;
                                }
                            """)
                            context_layout = QVBoxLayout(context_frame)
                            context_layout.setContentsMargins(8, 8, 8, 8)
                            context_layout.setSpacing(5)

                            if original_claim:
                                claim_label = QLabel(f"<b>Challenges Claim:</b> {original_claim}")
                                claim_label.setWordWrap(True)
                                claim_label.setStyleSheet("background-color: transparent; border: none;")
                                context_layout.addWidget(claim_label)

                            if cf_question:
                                question_label = QLabel(f"<b>Research Question:</b> {cf_question}")
                                question_label.setWordWrap(True)
                                question_label.setStyleSheet("background-color: transparent; border: none;")
                                context_layout.addWidget(question_label)

                            # Insert context at the top of the citation card
                            if hasattr(citation_card, 'main_layout'):
                                citation_card.main_layout.insertWidget(0, context_frame)

                        self.counterfactual_layout.addWidget(citation_card)

                    except Exception as citation_error:
                        self.logger.error(f"Error creating counterfactual citation card {i}: {citation_error}", exc_info=True)

                self.logger.info(f"Counterfactual tab updated with {len(contradictory_citations)} citation cards")

            self.counterfactual_layout.addStretch()

        except Exception as e:
            self.logger.error(f"Error updating counterfactual tab: {e}", exc_info=True)

    def _clear_layout_widgets(self, layout) -> None:
        """
        Safely clear all widgets from a layout with proper cleanup.

        This method properly cleans up widgets by removing them from the layout
        and scheduling them for deletion. PySide6 will automatically handle
        signal disconnection when widgets are deleted.

        Args:
            layout: The layout to clear (QVBoxLayout, QHBoxLayout, or QLayout)
        """
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                widget = child.widget()
                if widget:  # Type guard for None check
                    # Set parent to None to ensure immediate cleanup
                    widget.setParent(None)
                    # Schedule deletion (PySide6 handles signal disconnection automatically)
                    widget.deleteLater()
            elif child.layout():
                # Recursively clear nested layouts
                nested_layout = child.layout()
                if nested_layout:  # Type guard for None check
                    self._clear_layout_widgets(nested_layout)

    def _populate_literature_tab_with_unscored_documents(self, documents: list) -> None:
        """
        Populate the Literature tab with unscored documents.

        This shows documents immediately after search, before scoring happens.
        Documents are displayed with basic metadata only (no scores).

        Args:
            documents: List of document dictionaries
        """
        try:
            # Clear existing widgets
            try:
                self._clear_layout_widgets(self.literature_layout)
            except Exception as clear_error:
                self.logger.warning(f"Error clearing layout (will continue): {clear_error}")

            if not documents:
                # Show empty state
                empty_label = QLabel("No documents to display")
                empty_label.setStyleSheet(f"color: {self.ui.COLOR_TEXT_GREY}; padding: 20px;")
                empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.literature_layout.addWidget(empty_label)
                self.literature_layout.addStretch()
                return

            # Create simple document cards (without scores)
            cards_created = 0
            for i, doc in enumerate(documents):
                try:
                    # Create fake score_result with "pending" status for display
                    score_result = {
                        'score': 0,
                        'reasoning': 'Awaiting relevance scoring...',
                        'confidence': 0,
                        'pending': True
                    }
                    card = self._create_document_score_card(i + 1, doc, score_result)
                    self.literature_layout.addWidget(card)
                    cards_created += 1
                except Exception as card_error:
                    self.logger.error(f"Error creating card for document {i+1}: {card_error}", exc_info=True)

            # Add stretch at the end
            self.literature_layout.addStretch()

            self.logger.info(f"Literature tab populated with {cards_created}/{len(documents)} unscored documents")

        except Exception as e:
            self.logger.error(f"Error populating literature tab: {e}", exc_info=True)

    def _update_literature_tab(self, scored_documents: list) -> None:
        """
        Update the Literature tab with scored documents.

        Args:
            scored_documents: List of (document, score_result) tuples
        """
        try:
            # Clear existing widgets with proper cleanup
            try:
                self._clear_layout_widgets(self.literature_layout)
            except Exception as clear_error:
                self.logger.warning(f"Error clearing layout (will continue): {clear_error}")

            if not scored_documents:
                # Show empty state
                empty_label = QLabel("No documents to display")
                empty_label.setStyleSheet(f"color: {self.ui.COLOR_TEXT_GREY}; padding: 20px;")
                empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.literature_layout.addWidget(empty_label)
                self.literature_layout.addStretch()
                return

            # Sort by score (highest first)
            sorted_docs = sorted(scored_documents, key=lambda x: x[1].get('score', 0), reverse=True)

            # Create document cards
            cards_created = 0
            for i, (doc, score_result) in enumerate(sorted_docs):
                try:
                    card = self._create_document_score_card(i + 1, doc, score_result)
                    self.literature_layout.addWidget(card)
                    cards_created += 1
                except Exception as card_error:
                    self.logger.error(f"Error creating card for document {i+1}: {card_error}", exc_info=True)

            # Add stretch at the end
            self.literature_layout.addStretch()

            self.logger.info(f"Literature tab updated with {cards_created}/{len(scored_documents)} documents")

        except Exception as e:
            self.logger.error(f"Error updating literature tab: {e}", exc_info=True)

    def _update_citations_tab(self, citations: list) -> None:
        """
        Update the Citations tab with extracted citations using CitationCard widget.

        Args:
            citations: List of citation dictionaries or citation objects
        """
        try:
            # Clear existing widgets with proper cleanup
            try:
                self._clear_layout_widgets(self.citations_layout)
            except Exception as clear_error:
                self.logger.warning(f"Error clearing layout (will continue): {clear_error}")

            if not citations:
                # Show empty state
                empty_label = QLabel("No citations to display")
                empty_label.setStyleSheet(f"color: {self.ui.COLOR_TEXT_GREY}; padding: 20px;")
                empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.citations_layout.addWidget(empty_label)
                self.citations_layout.addStretch()
                return

            # Import CitationCard widget
            from ...widgets.citation_card import CitationCard

            # Create citation cards using the CitationCard widget
            cards_created = 0
            for i, citation in enumerate(citations):
                try:
                    card = CitationCard(citation_data=citation, index=i + 1)
                    self.citations_layout.addWidget(card)
                    cards_created += 1
                except Exception as card_error:
                    self.logger.error(f"Error creating citation card {i+1}: {card_error}", exc_info=True)

            # Add stretch at the end
            self.citations_layout.addStretch()

            self.logger.info(f"Citations tab updated with {cards_created}/{len(citations)} citations using CitationCard widget")

        except Exception as e:
            self.logger.error(f"Error updating citations tab: {e}", exc_info=True)

    def _create_document_score_card(self, index: int, doc: dict, score_result: dict) -> QWidget:
        """
        Create a collapsible document card showing score and metadata using the factory.

        Args:
            index: Document number (for display)
            doc: Document dictionary
            score_result: Scoring result dictionary

        Returns:
            QWidget containing the collapsible document card
        """
        try:
            # Extract score information
            score = score_result.get('score', 0)
            reasoning = score_result.get('reasoning', '')
            is_pending = score_result.get('pending', False)

            # Extract year from publication_date or year field
            publication_date = doc.get('publication_date', '')
            year = doc.get('year', '')
            if publication_date and publication_date != 'Unknown':
                year_value = int(str(publication_date)[:4]) if len(str(publication_date)) >= 4 else (int(year) if year else None)
            else:
                year_value = int(year) if year else None

            # Create DocumentCardData
            card_data = DocumentCardData(
                doc_id=doc.get('id', 0),
                title=doc.get('title', 'Untitled Document'),
                abstract=doc.get('abstract', ''),
                authors=doc.get('authors', []),
                year=year_value,
                journal=doc.get('publication', ''),
                pmid=doc.get('pmid'),
                doi=doc.get('doi'),
                source=doc.get('source'),
                relevance_score=score if not is_pending else None,
                pdf_url=doc.get('pdf_url'),
                context=CardContext.LITERATURE,
                show_abstract=True,
                show_metadata=True,
                show_pdf_button=True,
                expanded_by_default=False
            )

            # Create card using factory
            card = self.document_card_factory.create_card(card_data)

            # Add AI reasoning section if available (prepend to details_layout)
            if reasoning and not is_pending and hasattr(card, 'details_layout'):
                reasoning_container = QFrame()
                reasoning_container.setStyleSheet("""
                    QFrame {
                        background-color: #E3F2FD;
                        border: 1px solid #BBDEFB;
                        border-radius: 3px;
                        padding: 8px;
                    }
                """)
                reasoning_layout = QVBoxLayout(reasoning_container)
                reasoning_layout.setContentsMargins(8, 8, 8, 8)
                reasoning_layout.setSpacing(5)

                reasoning_title = QLabel("<b>AI Reasoning:</b>")
                reasoning_title.setStyleSheet(f"font-size: {self.ui.CARD_LABEL_FONT_SIZE}pt; background-color: transparent; border: none;")
                reasoning_layout.addWidget(reasoning_title)

                reasoning_text = QLabel(reasoning)
                reasoning_text.setWordWrap(True)
                reasoning_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                reasoning_text.setStyleSheet(f"color: #333; font-size: {self.ui.CARD_BODY_FONT_SIZE}pt; background-color: transparent; border: none;")
                reasoning_layout.addWidget(reasoning_text)

                # Insert at the beginning of details_layout (before abstract)
                card.details_layout.insertWidget(0, reasoning_container)

            return card

        except Exception as e:
            self.logger.error(f"Error creating document card using factory: {e}", exc_info=True)
            # Fallback to a simple error card
            error_widget = QLabel(f"Error displaying document: {str(e)}")
            error_widget.setStyleSheet("color: red; padding: 10px;")
            return error_widget

    # ========================================================================
    # Export Report Handlers
    # ========================================================================

    def _safe_write_file(self, filename: str, content: str, file_type: str = "file") -> tuple[bool, Optional[str]]:
        """Safely write content to a file with comprehensive error handling.

        Args:
            filename: Path to the file to write
            content: Content to write
            file_type: Type of file being written (for error messages)

        Returns:
            Tuple of (success: bool, error_message: Optional[str])
        """
        try:
            # Get parent directory (use '.' if empty for current directory)
            parent_dir = os.path.dirname(filename)
            if not parent_dir:
                parent_dir = '.'

            # Check if parent directory exists
            if not os.path.exists(parent_dir):
                return False, f"Directory does not exist: {parent_dir}"

            # Check if we have write permissions on the directory
            if not os.access(parent_dir, os.W_OK):
                return False, f"No write permission for directory: {parent_dir}"

            # Check if file exists and we can overwrite it
            if os.path.exists(filename) and not os.access(filename, os.W_OK):
                return False, f"No write permission for file: {filename}"

            # Try to write the file
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(content)

            return True, None

        except OSError as e:
            # Handle specific OS errors
            if e.errno == errno.ENOSPC:
                return False, "No space left on device"
            elif e.errno == errno.EROFS:
                return False, "Read-only file system"
            elif e.errno == errno.EACCES:
                return False, "Permission denied"
            elif e.errno == errno.ENAMETOOLONG:
                return False, "Filename is too long"
            elif e.errno == errno.ENOENT:
                return False, f"Directory not found: {os.path.dirname(filename) or '.'}"
            else:
                return False, f"OS error: {str(e)}"
        except UnicodeEncodeError as e:
            return False, f"Encoding error: {str(e)}"
        except Exception as e:
            return False, f"Unexpected error: {str(e)}"

    def _show_save_success(self, filename: str, content: str, file_type: str = "Report") -> None:
        """Show a standardized success message for file saves.

        Args:
            filename: Path to the saved file
            content: Content that was saved
            file_type: Type of file saved (for display)
        """
        file_size = len(content.encode('utf-8'))
        file_size_kb = file_size / 1024

        # Calculate word count for text content
        word_count = len(content.split()) if isinstance(content, str) else "N/A"

        message_parts = [
            f"{file_type} saved successfully!\n",
            f"File: {filename}",
            f"Size: {file_size_kb:.1f} KB"
        ]

        if word_count != "N/A":
            message_parts.append(f"Words: ~{word_count}")

        QMessageBox.information(
            self,
            f"{file_type} Saved",
            "\n".join(message_parts)
        )

        self.logger.info(f"{file_type} saved to: {filename} ({file_size_kb:.1f} KB)")
        self.status_message.emit(f"✅ {file_type} saved to {filename}")

    def _show_save_error(self, error_msg: str, file_type: str = "file") -> None:
        """Show a standardized error message for file save failures.

        Args:
            error_msg: Error message to display
            file_type: Type of file being saved (for display)
        """
        QMessageBox.critical(
            self,
            "Save Error",
            f"An error occurred while saving the {file_type}:\n\n{error_msg}"
        )
        self.logger.error(f"Error saving {file_type}: {error_msg}")

    @Slot()
    def _on_save_markdown_report(self) -> None:
        """Handle Save Report (Markdown) button click."""
        # Check if report is available
        if not hasattr(self, 'final_report_markdown') or not self.final_report_markdown:
            QMessageBox.warning(
                self,
                "No Report Available",
                "No final report is available to save.\n\n"
                "Please complete a research workflow first."
            )
            return

        # Generate default filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"bmlibrarian_report_{timestamp}.md"

        # Show save file dialog
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save Research Report",
            default_filename,
            "Markdown Files (*.md);;All Files (*)"
        )

        if not filename:
            # User cancelled
            return

        # Save the report using safe write helper
        success, error_msg = self._safe_write_file(filename, self.final_report_markdown, "markdown report")

        if success:
            self._show_save_success(filename, self.final_report_markdown, "Research Report")
        else:
            self._show_save_error(error_msg, "markdown report")

    @Slot()
    def _on_export_json_report(self) -> None:
        """Handle Export as JSON button click."""
        # Validate that we have results and a report to export
        if not self.current_results:
            QMessageBox.warning(
                self,
                "No Results Available",
                "No research results are available to export.\n\n"
                "Please complete a research workflow first."
            )
            return

        # Validate that we have a final report (use self.final_report_markdown for consistency)
        if not hasattr(self, 'final_report_markdown') or not self.final_report_markdown:
            QMessageBox.warning(
                self,
                "No Report Available",
                "No final report is available to export.\n\n"
                "Please complete the report generation step first."
            )
            return

        # Generate default filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"bmlibrarian_results_{timestamp}.json"

        # Show save file dialog
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export Results as JSON",
            default_filename,
            "JSON Files (*.json);;All Files (*)"
        )

        if not filename:
            # User cancelled
            return

        # Prepare export data with validated structure
        # Use self.final_report_markdown for consistency with markdown export
        export_data = {
            'research_question': self.current_results.get('question', ''),
            'document_count': self.current_results.get('document_count', 0),
            'citation_count': self.current_results.get('citation_count', 0),
            'final_report_markdown': self.final_report_markdown,  # ✅ Fixed: Use self.final_report_markdown
            'generated_at': datetime.now().isoformat(),
            'workflow_status': self.current_results.get('status', 'unknown')
        }

        # Validate export data structure
        if not export_data['research_question']:
            self.logger.warning("Exporting JSON with empty research question")
        if not export_data['final_report_markdown']:
            self.logger.warning("Exporting JSON with empty final report")

        try:
            # Serialize to JSON string
            json_content = json.dumps(export_data, indent=2, ensure_ascii=False)
        except (TypeError, ValueError) as e:
            self._show_save_error(f"Failed to serialize data to JSON: {str(e)}", "JSON export")
            return

        # Save the JSON using safe write helper
        success, error_msg = self._safe_write_file(filename, json_content, "JSON export")

        if success:
            self._show_save_success(filename, json_content, "Research Results")
        else:
            self._show_save_error(error_msg, "JSON export")

    # ========================================================================
    # Settings Tab Handlers
    # ========================================================================

    # ========================================================================
    # Settings Tab Methods - Now handled by SettingsPlugin
    # ========================================================================
    # The following methods have been moved to the SettingsPlugin:
    # - _test_ollama_connection() - now in SettingsPlugin._test_connection()
    # - _test_database_connection() - handled by SettingsPlugin
    # - _open_config_gui() - no longer needed (settings are now integrated)

    # ========================================================================
    # Cleanup Utilities
    # ========================================================================

    @staticmethod
    def _safe_disconnect(signal, slot) -> None:
        """
        Safely disconnect a signal from a slot.

        This method handles the case where the signal was never connected
        or has already been disconnected.

        Args:
            signal: Qt signal to disconnect
            slot: Slot function to disconnect from the signal
        """
        try:
            signal.disconnect(slot)
        except (RuntimeError, TypeError):
            # RuntimeError: Signal not connected or already disconnected
            # TypeError: Signal doesn't have disconnect method or invalid slot
            pass

    # ========================================================================
    # Cleanup
    # ========================================================================

    def cleanup(self) -> None:
        """
        Cleanup resources and disconnect signals.

        This method should be called when the widget is being destroyed
        to prevent memory leaks from signal connections.
        """
        try:
            self.logger.info("Cleaning up research tab widget...")

            # Milestone 4: Cleanup workflow thread first
            if self.workflow_thread and self.workflow_thread.isRunning():
                self.logger.info("Stopping workflow thread...")
                self.workflow_thread.cancel()  # Request cancellation
                self.workflow_thread.wait(5000)  # Wait up to 5 seconds for thread to finish
                if self.workflow_thread.isRunning():
                    self.logger.warning("Workflow thread did not stop in time, forcing termination")
                    self.workflow_thread.terminate()
                    self.workflow_thread.wait()
                self.workflow_thread.deleteLater()
                self.workflow_thread = None

            # Disconnect workflow executor signals FIRST (before cleanup)
            # This prevents signals being processed after executor is cleaned up
            if self.workflow_executor:
                self._safe_disconnect(self.workflow_executor.workflow_started, self._on_workflow_started)
                self._safe_disconnect(self.workflow_executor.workflow_completed, self._on_workflow_completed)
                self._safe_disconnect(self.workflow_executor.workflow_error, self._on_workflow_error)
                self._safe_disconnect(self.workflow_executor.status_message, self._on_workflow_status)
                self._safe_disconnect(self.workflow_executor.query_generated, self._on_query_generated)
                self._safe_disconnect(self.workflow_executor.documents_found, self._on_documents_found)
                self._safe_disconnect(self.workflow_executor.scoring_progress, self._on_scoring_progress)
                self._safe_disconnect(self.workflow_executor.documents_scored, self._on_documents_scored)
                # Milestone 3 signals
                self._safe_disconnect(self.workflow_executor.citations_extracted, self._on_citations_extracted)
                self._safe_disconnect(self.workflow_executor.preliminary_report_generated, self._on_preliminary_report_generated)

                # Now cleanup workflow executor resources
                if hasattr(self.workflow_executor, 'cleanup'):
                    self.workflow_executor.cleanup()

            # Disconnect UI element signals
            self._safe_disconnect(self.question_input.textChanged, self._on_question_changed)
            self._safe_disconnect(self.start_button.clicked, self._on_start_research)
            self._safe_disconnect(self.cancel_button.clicked, self._on_cancel_clicked)
            self._safe_disconnect(self.max_results_spin.valueChanged, self._on_max_results_changed)
            self._safe_disconnect(self.min_relevant_spin.valueChanged, self._on_min_relevant_changed)

            # Disconnect export button signals
            if hasattr(self, 'report_save_markdown_button'):
                self._safe_disconnect(self.report_save_markdown_button.clicked, self._on_save_markdown_report)
            if hasattr(self, 'report_export_json_button'):
                self._safe_disconnect(self.report_export_json_button.clicked, self._on_export_json_report)

            self.logger.info("✅ Research tab widget cleanup complete")

        except Exception as e:
            self.logger.error(f"Error during research tab widget cleanup: {e}", exc_info=True)
