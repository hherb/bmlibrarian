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
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QFont
from typing import Optional
import logging

# Import markdown viewer for report display
from ...widgets.markdown_viewer import MarkdownViewer


# ============================================================================
# UI Constants
# ============================================================================

class UIConstants:
    """UI layout and styling constants."""

    # Fonts
    TITLE_FONT_SIZE = 18
    SUBTITLE_FONT_SIZE = 10
    TAB_HEADER_FONT_SIZE = 12

    # Colors
    COLOR_PRIMARY_BLUE = "#1976D2"
    COLOR_PRIMARY_BLUE_HOVER = "#1565C0"
    COLOR_DISABLED_GREY = "#BDBDBD"
    COLOR_TEXT_GREY = "#666666"
    COLOR_BACKGROUND_GREY = "#F5F5F5"
    COLOR_BORDER_GREY = "#E0E0E0"
    COLOR_WHITE = "white"

    # Spacing
    MAIN_LAYOUT_MARGIN = 15
    MAIN_LAYOUT_SPACING = 10
    CONTROLS_SPACING = 10
    ROW2_SPACING = 15
    HEADER_BOTTOM_MARGIN = 10
    HEADER_SPACING = 5
    TAB_WIDGET_MARGIN = 15

    # Widget Sizes
    QUESTION_INPUT_MIN_HEIGHT = 70
    QUESTION_INPUT_MAX_HEIGHT = 100
    START_BUTTON_MIN_HEIGHT = 45
    START_BUTTON_MIN_WIDTH = 140
    SPINBOX_WIDTH = 80

    # Border Radii
    CONTROLS_BORDER_RADIUS = 8
    BUTTON_BORDER_RADIUS = 4

    # Spinbox Ranges
    MAX_RESULTS_MIN = 10
    MAX_RESULTS_MAX = 1000
    MAX_RESULTS_DEFAULT = 100
    MIN_RELEVANT_MIN = 1
    MIN_RELEVANT_MAX = 100
    MIN_RELEVANT_DEFAULT = 10

    # Document Score Thresholds
    SCORE_THRESHOLD_HIGH_RELEVANCE = 4.0
    SCORE_THRESHOLD_RELEVANT = 3.0
    SCORE_THRESHOLD_SOMEWHAT_RELEVANT = 2.0

    # Document Score Colors
    SCORE_COLOR_HIGH = "#4CAF50"  # Green
    SCORE_COLOR_RELEVANT = "#2196F3"  # Blue
    SCORE_COLOR_SOMEWHAT = "#FF9800"  # Orange
    SCORE_COLOR_LOW = "#9E9E9E"  # Grey


class StyleSheets:
    """Centralized stylesheet definitions."""

    @staticmethod
    def controls_frame() -> str:
        """Stylesheet for controls section frame."""
        return f"""
            QFrame {{
                background-color: {UIConstants.COLOR_BACKGROUND_GREY};
                border: 1px solid {UIConstants.COLOR_BORDER_GREY};
                border-radius: {UIConstants.CONTROLS_BORDER_RADIUS}px;
                padding: 10px;
            }}
        """

    @staticmethod
    def start_button() -> str:
        """Stylesheet for Start Research button."""
        return f"""
            QPushButton {{
                background-color: {UIConstants.COLOR_PRIMARY_BLUE};
                color: {UIConstants.COLOR_WHITE};
                font-weight: bold;
                border-radius: {UIConstants.BUTTON_BORDER_RADIUS}px;
                padding: 8px 16px;
            }}
            QPushButton:hover {{
                background-color: {UIConstants.COLOR_PRIMARY_BLUE_HOVER};
            }}
            QPushButton:disabled {{
                background-color: {UIConstants.COLOR_DISABLED_GREY};
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

        # Logger
        self.logger = logging.getLogger("bmlibrarian.gui.qt.plugins.research.ResearchTabWidget")

        # Workflow state
        self.current_results: dict = {}
        self.counterfactual_results: Optional[dict] = None
        self.workflow_running: bool = False

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

        # UI Components (initialized in _setup_ui)
        self.question_input: Optional[QTextEdit] = None
        self.start_button: Optional[QPushButton] = None
        self.cancel_button: Optional[QPushButton] = None
        self.progress_bar: Optional[QProgressBar] = None
        self.step_status_label: Optional[QLabel] = None
        self.max_results_spin: Optional[QSpinBox] = None
        self.min_relevant_spin: Optional[QSpinBox] = None
        self.interactive_checkbox: Optional[QCheckBox] = None
        self.counterfactual_checkbox: Optional[QCheckBox] = None
        self.research_tabs: Optional[QTabWidget] = None

        # Initialize UI
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup the user interface with Qt-native design."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(
            UIConstants.MAIN_LAYOUT_MARGIN,
            UIConstants.MAIN_LAYOUT_MARGIN,
            UIConstants.MAIN_LAYOUT_MARGIN,
            UIConstants.MAIN_LAYOUT_MARGIN
        )
        main_layout.setSpacing(UIConstants.MAIN_LAYOUT_SPACING)

        # 1. Header section
        header = self._create_header_section()
        main_layout.addWidget(header)

        # 2. Controls section (question input, parameters, buttons)
        controls = self._create_controls_section()
        main_layout.addWidget(controls)

        # 3. Tabbed interface (8 tabs)
        self.research_tabs = self._create_tabbed_interface()
        main_layout.addWidget(self.research_tabs, stretch=1)

    def _create_header_section(self) -> QWidget:
        """
        Create header section with title and subtitle.

        Returns:
            Header widget
        """
        header_widget = QWidget()
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, UIConstants.HEADER_BOTTOM_MARGIN)
        header_layout.setSpacing(UIConstants.HEADER_SPACING)

        # Title
        title = QLabel("BMLibrarian Research Assistant")
        title_font = QFont()
        title_font.setPointSize(UIConstants.TITLE_FONT_SIZE)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet(f"color: {UIConstants.COLOR_PRIMARY_BLUE};")
        header_layout.addWidget(title)

        # Subtitle
        subtitle = QLabel("AI-Powered Evidence-Based Medical Literature Research")
        subtitle_font = QFont()
        subtitle_font.setPointSize(UIConstants.SUBTITLE_FONT_SIZE)
        subtitle.setFont(subtitle_font)
        subtitle.setStyleSheet(f"color: {UIConstants.COLOR_TEXT_GREY};")
        header_layout.addWidget(subtitle)

        return header_widget

    def _create_controls_section(self) -> QWidget:
        """
        Create controls section with question input, parameters, and buttons.

        Layout:
        Row 1: [Question Text Edit --------] [Start Button]
        Row 2: [Max Results] [Min Relevant] [Interactive ☐] [Counterfactual ☑]

        Returns:
            Controls widget
        """
        # Container with frame and background
        controls_frame = QFrame()
        controls_frame.setFrameShape(QFrame.StyledPanel)
        controls_frame.setFrameShadow(QFrame.Raised)
        controls_frame.setStyleSheet(StyleSheets.controls_frame())

        controls_layout = QVBoxLayout(controls_frame)
        controls_layout.setSpacing(UIConstants.CONTROLS_SPACING)

        # Row 1: Question input + Start button
        row1 = QHBoxLayout()
        row1.setSpacing(UIConstants.CONTROLS_SPACING)

        # Question input
        question_container = QVBoxLayout()
        question_label = QLabel("Research Question:")
        question_label.setStyleSheet("font-weight: bold;")
        question_container.addWidget(question_label)

        self.question_input = QTextEdit()
        self.question_input.setPlaceholderText(
            "Enter your biomedical research question here...\n\n"
            "Example: What are the cardiovascular benefits of regular exercise in adults?"
        )
        self.question_input.setMaximumHeight(UIConstants.QUESTION_INPUT_MAX_HEIGHT)
        self.question_input.setMinimumHeight(UIConstants.QUESTION_INPUT_MIN_HEIGHT)
        self.question_input.textChanged.connect(self._on_question_changed)
        question_container.addWidget(self.question_input)
        row1.addLayout(question_container, stretch=1)

        # Button container for Start and Cancel buttons
        button_container = QVBoxLayout()
        button_container.setSpacing(5)

        # Start and Cancel buttons in horizontal layout
        button_row = QHBoxLayout()
        button_row.setSpacing(8)

        # Start button
        self.start_button = QPushButton("Start Research")
        self.start_button.setIcon(self.start_button.style().standardIcon(
            self.start_button.style().StandardPixmap.SP_MediaPlay
        ))
        self.start_button.setMinimumHeight(UIConstants.START_BUTTON_MIN_HEIGHT)
        self.start_button.setMinimumWidth(UIConstants.START_BUTTON_MIN_WIDTH)
        self.start_button.setEnabled(False)
        self.start_button.setStyleSheet(StyleSheets.start_button())
        self.start_button.clicked.connect(self._on_start_research)
        button_row.addWidget(self.start_button)

        # Cancel button (Milestone 4: Workflow cancellation)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setIcon(self.cancel_button.style().standardIcon(
            self.cancel_button.style().StandardPixmap.SP_DialogCancelButton
        ))
        self.cancel_button.setMinimumHeight(UIConstants.START_BUTTON_MIN_HEIGHT)
        self.cancel_button.setMinimumWidth(100)
        self.cancel_button.setEnabled(False)  # Only enabled during workflow
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
        button_row.addWidget(self.cancel_button)

        button_container.addLayout(button_row)

        # Progress bar (Milestone 4: Progress tracking)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setMaximumHeight(6)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #E0E0E0;
                border-radius: 3px;
                background-color: #F5F5F5;
            }
            QProgressBar::chunk {
                background-color: #1976D2;
                border-radius: 2px;
            }
        """)
        self.progress_bar.setVisible(False)  # Hidden until workflow starts
        button_container.addWidget(self.progress_bar)

        row1.addLayout(button_container)
        row1.setAlignment(button_container, Qt.AlignmentFlag.AlignBottom)

        controls_layout.addLayout(row1)

        # Row 2: Parameters and toggles
        row2 = QHBoxLayout()
        row2.setSpacing(UIConstants.ROW2_SPACING)

        # Max Results
        max_results_label = QLabel("Max Results:")
        row2.addWidget(max_results_label)

        self.max_results_spin = QSpinBox()
        self.max_results_spin.setMinimum(UIConstants.MAX_RESULTS_MIN)
        self.max_results_spin.setMaximum(UIConstants.MAX_RESULTS_MAX)
        self.max_results_spin.setValue(UIConstants.MAX_RESULTS_DEFAULT)
        self.max_results_spin.setFixedWidth(UIConstants.SPINBOX_WIDTH)
        self.max_results_spin.setToolTip("Maximum number of documents to retrieve from database")
        self.max_results_spin.valueChanged.connect(self._on_max_results_changed)
        row2.addWidget(self.max_results_spin)

        # Min Relevant
        min_relevant_label = QLabel("Min Relevant:")
        row2.addWidget(min_relevant_label)

        self.min_relevant_spin = QSpinBox()
        self.min_relevant_spin.setMinimum(UIConstants.MIN_RELEVANT_MIN)
        self.min_relevant_spin.setMaximum(UIConstants.MIN_RELEVANT_MAX)
        self.min_relevant_spin.setValue(UIConstants.MIN_RELEVANT_DEFAULT)
        self.min_relevant_spin.setFixedWidth(UIConstants.SPINBOX_WIDTH)
        self.min_relevant_spin.setToolTip(
            "Minimum high-scoring documents to find (triggers iterative search)"
        )
        self.min_relevant_spin.valueChanged.connect(self._on_min_relevant_changed)
        row2.addWidget(self.min_relevant_spin)

        # Spacer
        row2.addSpacing(20)

        # Interactive mode toggle
        self.interactive_checkbox = QCheckBox("Interactive Mode")
        self.interactive_checkbox.setChecked(False)
        self.interactive_checkbox.setToolTip(
            "Enable human-in-the-loop for query editing, manual scoring, etc."
        )
        row2.addWidget(self.interactive_checkbox)

        # Counterfactual toggle
        self.counterfactual_checkbox = QCheckBox("Comprehensive Counterfactual Analysis")
        self.counterfactual_checkbox.setChecked(True)
        self.counterfactual_checkbox.setToolTip(
            "Search for contradictory evidence and create balanced report"
        )
        row2.addWidget(self.counterfactual_checkbox)

        # Stretch to push everything left
        row2.addStretch()

        controls_layout.addLayout(row2)

        # Row 3: Step status label (Milestone 4: Progress display)
        self.step_status_label = QLabel("")
        self.step_status_label.setStyleSheet(f"""
            color: {UIConstants.COLOR_TEXT_GREY};
            font-style: italic;
            padding: 5px;
        """)
        self.step_status_label.setWordWrap(True)
        self.step_status_label.setVisible(False)  # Hidden until workflow starts
        controls_layout.addWidget(self.step_status_label)

        return controls_frame

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
            UIConstants.TAB_WIDGET_MARGIN,
            UIConstants.TAB_WIDGET_MARGIN,
            UIConstants.TAB_WIDGET_MARGIN,
            UIConstants.TAB_WIDGET_MARGIN
        )

        # Header
        label = QLabel(f"{icon} {title}")
        label_font = QFont()
        label_font.setPointSize(UIConstants.TAB_HEADER_FONT_SIZE)
        label_font.setBold(True)
        label.setFont(label_font)
        layout.addWidget(label)

        # Description
        desc_label = QLabel(description)
        desc_label.setStyleSheet(f"color: {UIConstants.COLOR_TEXT_GREY}; margin-top: 10px;")
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
            UIConstants.TAB_WIDGET_MARGIN,
            UIConstants.TAB_WIDGET_MARGIN,
            UIConstants.TAB_WIDGET_MARGIN,
            UIConstants.TAB_WIDGET_MARGIN
        )

        # Header
        header = QLabel("🔍 Search Query Generation")
        header_font = QFont()
        header_font.setPointSize(UIConstants.TAB_HEADER_FONT_SIZE)
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
        self.document_count_label.setStyleSheet(f"color: {UIConstants.COLOR_TEXT_GREY};")
        layout.addWidget(self.document_count_label)

        # Add stretch to push everything to the top
        layout.addStretch()

        return widget

    def _create_literature_tab(self) -> QWidget:
        """Create Literature tab (document list with scores)."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(UIConstants.TAB_WIDGET_MARGIN, UIConstants.TAB_WIDGET_MARGIN,
                                 UIConstants.TAB_WIDGET_MARGIN, UIConstants.TAB_WIDGET_MARGIN)

        # Header
        header_label = QLabel("📚 Literature Documents")
        header_font = QFont()
        header_font.setPointSize(UIConstants.TAB_HEADER_FONT_SIZE)
        header_font.setBold(True)
        header_label.setFont(header_font)
        layout.addWidget(header_label)

        # Subtitle
        subtitle_label = QLabel("Documents retrieved from search with AI relevance scores")
        subtitle_label.setStyleSheet(f"color: {UIConstants.COLOR_TEXT_GREY};")
        layout.addWidget(subtitle_label)

        # Document count and score summary
        self.literature_summary_label = QLabel("No documents scored yet")
        self.literature_summary_label.setStyleSheet(f"color: {UIConstants.COLOR_TEXT_GREY};")
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
        self.literature_empty_label.setStyleSheet(f"color: {UIConstants.COLOR_TEXT_GREY}; padding: 20px;")
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
        layout.setContentsMargins(UIConstants.TAB_WIDGET_MARGIN, UIConstants.TAB_WIDGET_MARGIN,
                                 UIConstants.TAB_WIDGET_MARGIN, UIConstants.TAB_WIDGET_MARGIN)

        # Header
        header_label = QLabel("💬 Extracted Citations")
        header_font = QFont()
        header_font.setPointSize(UIConstants.TAB_HEADER_FONT_SIZE)
        header_font.setBold(True)
        header_label.setFont(header_font)
        layout.addWidget(header_label)

        # Subtitle
        subtitle_label = QLabel("Relevant passages from high-scoring documents (score ≥ 3.0)")
        subtitle_label.setStyleSheet(f"color: {UIConstants.COLOR_TEXT_GREY};")
        layout.addWidget(subtitle_label)

        # Citation count summary
        self.citations_summary_label = QLabel("No citations extracted yet")
        self.citations_summary_label.setStyleSheet(f"color: {UIConstants.COLOR_TEXT_GREY};")
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
        self.citations_empty_label.setStyleSheet(f"color: {UIConstants.COLOR_TEXT_GREY}; padding: 20px;")
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
        layout.setContentsMargins(UIConstants.TAB_WIDGET_MARGIN, UIConstants.TAB_WIDGET_MARGIN,
                                 UIConstants.TAB_WIDGET_MARGIN, UIConstants.TAB_WIDGET_MARGIN)

        # Header
        header_label = QLabel("📄 Preliminary Report")
        header_font = QFont()
        header_font.setPointSize(UIConstants.TAB_HEADER_FONT_SIZE)
        header_font.setBold(True)
        header_label.setFont(header_font)
        layout.addWidget(header_label)

        # Subtitle
        subtitle_label = QLabel("Report generated from extracted citations (before counterfactual analysis)")
        subtitle_label.setStyleSheet(f"color: {UIConstants.COLOR_TEXT_GREY};")
        layout.addWidget(subtitle_label)

        # Report statistics summary
        self.preliminary_report_summary_label = QLabel("No report generated yet")
        self.preliminary_report_summary_label.setStyleSheet(f"color: {UIConstants.COLOR_TEXT_GREY};")
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
        header_font.setPointSize(UIConstants.TAB_HEADER_FONT_SIZE)
        header_font.setBold(True)
        header.setFont(header_font)
        layout.addWidget(header)

        # Summary label
        self.counterfactual_summary_label = QLabel("Waiting for analysis...")
        self.counterfactual_summary_label.setStyleSheet(f"color: {UIConstants.COLOR_TEXT_GREY};")
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
        placeholder.setStyleSheet(f"color: {UIConstants.COLOR_TEXT_GREY}; padding: 20px;")
        placeholder.setWordWrap(True)
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.counterfactual_layout.addWidget(placeholder)
        self.counterfactual_layout.addStretch()

        scroll.setWidget(content_widget)
        layout.addWidget(scroll, stretch=1)

        return tab

    def _create_report_tab(self) -> QWidget:
        """Create Final Report tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Header
        header_label = QLabel("📋 Final Comprehensive Report")
        header_label.setStyleSheet(f"font-size: 14pt; font-weight: bold; color: {UIConstants.COLOR_PRIMARY};")
        layout.addWidget(header_label)

        # Summary label
        self.report_summary_label = QLabel("No report generated yet")
        self.report_summary_label.setStyleSheet(f"color: {UIConstants.COLOR_TEXT_GREY};")
        layout.addWidget(self.report_summary_label)

        # Markdown viewer
        self.report_viewer = MarkdownViewer()
        self.report_viewer.set_markdown("_No final report available yet. The final report will be generated after counterfactual analysis._")
        layout.addWidget(self.report_viewer)

        return widget

    def _create_settings_tab(self) -> QWidget:
        """Create Settings tab."""
        return self._create_placeholder_tab(
            "⚙️",
            "Settings",
            "This tab will display:\n"
            "• Agent configuration options\n"
            "• Model selection dropdowns\n"
            "• Parameter sliders (temperature, top_p, etc.)\n"
            "• Quick toggles for workflow options\n"
            "• Database and Ollama connection status\n"
            "• Reset to defaults button"
        )

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
            self.start_button.setEnabled(False)
            self.cancel_button.setEnabled(True)
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
            self.step_status_label.setVisible(True)
            self.step_status_label.setText("Initializing workflow...")
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
        self.start_button.setEnabled(False)
        self.workflow_started.emit()

    @Slot(dict)
    def _on_workflow_completed(self, results: dict) -> None:
        """Handle workflow completed signal."""
        self.logger.info(f"Workflow completed: {results.get('status', 'unknown')}")
        self.workflow_running = False
        self.start_button.setEnabled(True)
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
        self.start_button.setEnabled(True)
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
        self.step_status_label.setText("Cancelling workflow...")
        self.workflow_thread.cancel()

    @Slot(str, str)
    def _on_thread_step_started(self, step_name: str, description: str) -> None:
        """Handle workflow step started signal."""
        self.logger.info(f"Step started: {step_name} - {description}")
        self.step_status_label.setText(f"⚙️ {description}")

        # Update progress bar based on step (rough percentage)
        step_progress_map = {
            'generate_query': 10,
            'search_documents': 20,
            'score_documents': 40,
            'extract_citations': 60,
            'generate_preliminary_report': 70,
            'counterfactual_analysis': 75,
            'search_contradictory_evidence': 85,
            'generate_final_report': 95
        }
        progress = step_progress_map.get(step_name, 0)
        self.progress_bar.setValue(progress)

    @Slot(str, int, int)
    def _on_thread_step_progress(self, step_name: str, current: int, total: int) -> None:
        """Handle workflow step progress signal."""
        if total > 0:
            percentage = int((current / total) * 100)
            # For scoring step, show fine-grained progress between 20% and 60%
            if step_name == 'score_documents':
                progress = 20 + int((current / total) * 40)
                self.progress_bar.setValue(progress)
            self.step_status_label.setText(f"⚙️ Processing {current}/{total} documents...")

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
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_bar.setValue(100)
        self.step_status_label.setText("✅ Workflow completed successfully!")

        # Store results
        self.current_results = results

        # Emit completion signal
        self.workflow_completed.emit(results)

        # Display summary
        doc_count = results.get('document_count', 0)
        citation_count = results.get('citation_count', 0)
        self.status_message.emit(
            f"✅ Research complete! Found {doc_count} documents, "
            f"extracted {citation_count} citations"
        )

    @Slot(Exception)
    def _on_thread_workflow_error(self, error: Exception) -> None:
        """Handle workflow error signal from thread."""
        self.logger.error(f"Thread workflow error: {error}", exc_info=True)

        # Update UI state
        self.workflow_running = False
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.step_status_label.setText("❌ Workflow failed")

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
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.step_status_label.setText("🛑 Workflow cancelled")

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
            self.document_count_label.setStyleSheet(f"color: {UIConstants.COLOR_PRIMARY_BLUE};")

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
            if isinstance(s.get('score'), (int, float)) and s.get('score', 0) >= UIConstants.SCORE_THRESHOLD_RELEVANT
        ])

        if hasattr(self, 'literature_summary_label'):
            self.literature_summary_label.setText(
                f"✅ {total} documents scored | {high_scoring} highly relevant (score ≥ {UIConstants.SCORE_THRESHOLD_RELEVANT})"
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

        # Update the Report tab with markdown
        if hasattr(self, 'report_viewer'):
            self.report_viewer.set_markdown(report)

        # Update summary label (word count approximation)
        word_count = len(report.split())
        if hasattr(self, 'report_summary_label'):
            self.report_summary_label.setText(
                f"✅ Comprehensive report generated | ~{word_count} words | {len(report)} characters"
            )

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
                no_questions_label.setStyleSheet(f"color: {UIConstants.COLOR_TEXT_GREY}; padding: 20px;")
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
                        background-color: {UIConstants.COLOR_WHITE};
                        border: 1px solid {UIConstants.COLOR_BORDER_GREY};
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
                    statement_label.setStyleSheet(f"padding: 4px; color: {UIConstants.COLOR_TEXT_GREY};")
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
                    keywords_label.setStyleSheet(f"padding: 4px; color: {UIConstants.COLOR_TEXT_GREY}; font-size: 9pt;")
                    card_layout.addWidget(keywords_label)

                self.counterfactual_layout.addWidget(card)

            # Show contradictory documents summary
            if doc_count > 0:
                doc_summary = QLabel(f"\n📚 Found {doc_count} potentially contradictory documents")
                doc_summary.setStyleSheet("font-weight: bold; font-size: 10pt; padding-top: 10px;")
                self.counterfactual_layout.addWidget(doc_summary)

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
                empty_label.setStyleSheet(f"color: {UIConstants.COLOR_TEXT_GREY}; padding: 20px;")
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
                empty_label.setStyleSheet(f"color: {UIConstants.COLOR_TEXT_GREY}; padding: 20px;")
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
        Update the Citations tab with extracted citations.

        Args:
            citations: List of citation dictionaries
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
                empty_label.setStyleSheet(f"color: {UIConstants.COLOR_TEXT_GREY}; padding: 20px;")
                empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.citations_layout.addWidget(empty_label)
                self.citations_layout.addStretch()
                return

            # Create citation cards
            cards_created = 0
            for i, citation in enumerate(citations):
                try:
                    card = self._create_citation_card(i + 1, citation)
                    self.citations_layout.addWidget(card)
                    cards_created += 1
                except Exception as card_error:
                    self.logger.error(f"Error creating citation card {i+1}: {card_error}", exc_info=True)

            # Add stretch at the end
            self.citations_layout.addStretch()

            self.logger.info(f"Citations tab updated with {cards_created}/{len(citations)} citations")

        except Exception as e:
            self.logger.error(f"Error updating citations tab: {e}", exc_info=True)

    def _create_highlighted_abstract_widget(self, abstract: str, passage: str) -> QWidget:
        """
        Create a widget showing the abstract with the passage highlighted in yellow.
        Matches the Flet implementation's highlighting logic.

        Args:
            abstract: Full abstract text
            passage: Passage to highlight within the abstract

        Returns:
            QWidget containing the highlighted abstract
        """
        import re

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        if not abstract or not passage:
            label = QLabel(abstract or "No abstract available")
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            label.setStyleSheet("font-size: 9pt; color: #333;")
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
            before = abstract[:start]
            highlighted = abstract[start:end]
            after = abstract[end:]

            html = f"""
            <style>
                .abstract-text {{ font-size: 9pt; color: #333; line-height: 1.4; }}
                .highlight {{ background-color: #FFD54F; font-weight: 600; padding: 2px 4px; }}
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
                warning_label.setStyleSheet("font-size: 9pt; color: #F57C00; font-style: italic;")
                layout.addWidget(warning_label)

                before = abstract[:start]
                highlighted = abstract[start:end]
                after = abstract[end:]

                html = f"""
                <style>
                    .abstract-text {{ font-size: 9pt; color: #333; line-height: 1.4; }}
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
                passage_frame.setStyleSheet("""
                    QFrame {
                        background-color: #FFD54F;
                        border-radius: 3px;
                        padding: 8px;
                    }
                """)
                passage_layout = QVBoxLayout(passage_frame)
                passage_layout.setContentsMargins(8, 8, 8, 8)

                passage_label = QLabel(f"📌 Cited Passage:\n{passage}")
                passage_label.setWordWrap(True)
                passage_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                passage_label.setStyleSheet("font-size: 9pt; font-weight: 600; background-color: transparent; border: none;")
                passage_layout.addWidget(passage_label)

                layout.addWidget(passage_frame)

                abstract_title = QLabel("Full Abstract:")
                abstract_title.setStyleSheet("font-size: 9pt; font-weight: bold; margin-top: 5px;")
                layout.addWidget(abstract_title)

                abstract_label = QLabel(abstract)
                abstract_label.setWordWrap(True)
                abstract_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                abstract_label.setStyleSheet("font-size: 9pt; color: #333;")
                layout.addWidget(abstract_label)

        return container

    def _create_citation_card(self, index: int, citation) -> QWidget:
        """
        Create a collapsible citation card showing document info and relevant passage.
        Matches the Flet GUI ExpansionTile style with abstract highlighting.

        Args:
            index: Citation number (for display)
            citation: Citation object (from CitationFinderAgent)

        Returns:
            QWidget containing the collapsible citation card
        """
        # Container widget
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 2)
        container_layout.setSpacing(0)

        # Header frame (always visible, clickable)
        header = QFrame()
        header.setFrameShape(QFrame.Shape.Box)
        header.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-left: 4px solid #3498db;
                border-radius: 4px;
                padding: 8px;
            }
            QFrame:hover {
                background-color: #e9ecef;
                border-left: 4px solid #2980b9;
            }
        """)
        header.setCursor(Qt.CursorShape.PointingHandCursor)

        header_layout = QVBoxLayout(header)
        header_layout.setSpacing(4)
        header_layout.setContentsMargins(6, 6, 6, 6)

        # Title row with relevance badge
        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        title = getattr(citation, 'document_title', 'Untitled Document')
        # Truncate long titles
        if len(title) > 80:
            title = title[:77] + "..."

        title_label = QLabel(f"<b>{index}. {title}</b>")
        title_label.setWordWrap(True)
        title_label.setStyleSheet("color: #1976D2; font-size: 10pt;")
        title_row.addWidget(title_label, 1)

        # Relevance score badge
        relevance_score = getattr(citation, 'relevance_score', 0)
        if relevance_score:
            score_badge = QLabel(f"{relevance_score:.2f}")
            score_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            score_badge.setFixedSize(50, 24)
            score_badge.setStyleSheet("""
                QLabel {
                    background-color: #4CAF50;
                    color: white;
                    font-size: 9pt;
                    font-weight: bold;
                    border-radius: 12px;
                    padding: 2px 6px;
                }
            """)
            title_row.addWidget(score_badge)

        header_layout.addLayout(title_row)

        # Subtitle row (authors and publication info)
        authors = getattr(citation, 'authors', [])
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
        publication_date = getattr(citation, 'publication_date', '')
        if publication_date and publication_date != 'Unknown':
            year_str = str(publication_date)[:4] if len(str(publication_date)) >= 4 else 'Unknown year'
        else:
            year_str = 'Unknown year'

        publication = getattr(citation, 'publication', '')
        pub_info = f"{publication} • {year_str}" if publication else year_str

        subtitle = f"{authors_str} | {pub_info}"
        subtitle_label = QLabel(subtitle)
        subtitle_label.setWordWrap(True)
        subtitle_label.setStyleSheet(f"color: {UIConstants.COLOR_TEXT_GREY}; font-size: 9pt;")
        header_layout.addWidget(subtitle_label)

        container_layout.addWidget(header)

        # Details frame (collapsible content)
        details = QFrame()
        details.setFrameShape(QFrame.Shape.Box)
        details.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 1px solid #dee2e6;
                border-top: none;
                border-radius: 0 0 4px 4px;
                padding: 10px;
            }
        """)
        details.setVisible(False)  # Collapsed by default

        details_layout = QVBoxLayout(details)
        details_layout.setSpacing(8)
        details_layout.setContentsMargins(10, 10, 10, 10)

        # Summary section
        summary = getattr(citation, 'summary', '')
        if summary:
            summary_container = QFrame()
            summary_container.setStyleSheet("""
                QFrame {
                    background-color: #e8f5e9;
                    border: 1px solid #c8e6c9;
                    border-radius: 3px;
                    padding: 8px;
                }
            """)
            summary_layout = QVBoxLayout(summary_container)
            summary_layout.setContentsMargins(8, 8, 8, 8)
            summary_layout.setSpacing(5)

            summary_title = QLabel("<b>Summary:</b>")
            summary_title.setStyleSheet("font-size: 9pt; background-color: transparent; border: none;")
            summary_layout.addWidget(summary_title)

            summary_text = QLabel(summary)
            summary_text.setWordWrap(True)
            summary_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            summary_text.setStyleSheet("color: #333; font-size: 9pt; background-color: transparent; border: none;")
            summary_layout.addWidget(summary_text)

            details_layout.addWidget(summary_container)

        # Abstract with highlighted citation
        abstract = getattr(citation, 'abstract', None)
        passage = getattr(citation, 'passage', '')

        if abstract and passage:
            abstract_container = QFrame()
            abstract_container.setStyleSheet("""
                QFrame {
                    background-color: #f5f5f5;
                    border: 1px solid #ddd;
                    border-radius: 3px;
                    padding: 8px;
                }
            """)
            abstract_layout = QVBoxLayout(abstract_container)
            abstract_layout.setContentsMargins(8, 8, 8, 8)
            abstract_layout.setSpacing(5)

            abstract_title = QLabel("<b>Abstract with Highlighted Citation:</b>")
            abstract_title.setStyleSheet("font-size: 9pt; background-color: transparent; border: none;")
            abstract_layout.addWidget(abstract_title)

            # Create highlighted abstract widget
            highlighted_widget = self._create_highlighted_abstract_widget(abstract, passage)
            abstract_layout.addWidget(highlighted_widget)

            details_layout.addWidget(abstract_container)
        elif passage:
            # Fallback: just show the passage if no abstract
            passage_container = QFrame()
            passage_container.setStyleSheet("""
                QFrame {
                    background-color: #f5f5f5;
                    border: 1px solid #ddd;
                    border-left: 3px solid #2196F3;
                    border-radius: 3px;
                    padding: 8px;
                }
            """)
            passage_layout = QVBoxLayout(passage_container)
            passage_layout.setContentsMargins(8, 8, 8, 8)
            passage_layout.setSpacing(5)

            passage_title = QLabel("<b>Extracted Passage:</b>")
            passage_title.setStyleSheet("font-size: 9pt; background-color: transparent; border: none;")
            passage_layout.addWidget(passage_title)

            passage_text = QLabel(f'<i>"{passage}"</i>')
            passage_text.setWordWrap(True)
            passage_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            passage_text.setStyleSheet("color: #333; font-size: 9pt; background-color: transparent; border: none;")
            passage_layout.addWidget(passage_text)

            details_layout.addWidget(passage_container)

        # Document identifiers
        id_parts = []
        pmid = getattr(citation, 'pmid', None)
        doi = getattr(citation, 'doi', None)
        doc_id = getattr(citation, 'document_id', None)

        if pmid:
            id_parts.append(f"PMID: {pmid}")
        if doi:
            id_parts.append(f"DOI: {doi}")
        if doc_id and not pmid:
            id_parts.append(f"ID: {doc_id}")

        if id_parts:
            id_label = QLabel(' | '.join(id_parts))
            id_label.setStyleSheet("color: #888; font-size: 8pt;")
            details_layout.addWidget(id_label)

        container_layout.addWidget(details)

        # Make header clickable to toggle details
        def toggle_details():
            details.setVisible(not details.isVisible())

        header.mousePressEvent = lambda _: toggle_details()

        return container

    def _create_document_score_card(self, index: int, doc: dict, score_result: dict) -> QFrame:
        """
        Create a document card showing score and metadata.
        Matches the Flet GUI style with comprehensive information.

        Args:
            index: Document number (for display)
            doc: Document dictionary
            score_result: Scoring result dictionary

        Returns:
            QFrame containing the document card
        """
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.Box)
        frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 1px solid #E0E0E0;
                border-radius: 8px;
                padding: 10px;
            }
            QFrame:hover {
                border: 1px solid #1976D2;
                background-color: #FAFAFA;
            }
        """)

        layout = QVBoxLayout(frame)
        layout.setSpacing(6)

        # Row 1: Index, Title, and Score Badge
        title_row = QHBoxLayout()

        # Index and Title
        title = doc.get('title', 'Untitled Document')
        title_label = QLabel(f"<b>{index}. {title}</b>")
        title_label.setWordWrap(True)
        title_label.setStyleSheet("color: #1976D2; font-size: 11pt;")
        title_row.addWidget(title_label, 1)

        # Score badge
        score = score_result.get('score', 0)
        confidence = score_result.get('confidence', 1.0)
        is_pending = score_result.get('pending', False)

        # Show different badge for pending (unscored) vs scored documents
        if is_pending:
            score_badge = QLabel("⏳ Pending")
            bgcolor = "#9E9E9E"  # Grey for pending
        else:
            score_badge = QLabel(f"⭐ {score:.1f}")
            # Color based on score (using constants)
            if score >= UIConstants.SCORE_THRESHOLD_HIGH_RELEVANCE:
                bgcolor = UIConstants.SCORE_COLOR_HIGH
            elif score >= UIConstants.SCORE_THRESHOLD_RELEVANT:
                bgcolor = UIConstants.SCORE_COLOR_RELEVANT
            elif score >= UIConstants.SCORE_THRESHOLD_SOMEWHAT_RELEVANT:
                bgcolor = UIConstants.SCORE_COLOR_SOMEWHAT
            else:
                bgcolor = UIConstants.SCORE_COLOR_LOW

        score_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        score_badge.setStyleSheet(f"""
            QLabel {{
                background-color: {bgcolor};
                color: white;
                font-weight: bold;
                padding: 4px 8px;
                border-radius: 4px;
                min-width: 40px;
            }}
        """)
        title_row.addWidget(score_badge)

        layout.addLayout(title_row)

        # Row 2: Authors and Year
        authors = doc.get('authors', [])
        if isinstance(authors, list):
            # Format authors list - show first 3 with et al. if more
            if len(authors) > 3:
                authors_str = ', '.join(authors[:3]) + ' et al.'
            elif authors:
                authors_str = ', '.join(authors)
            else:
                authors_str = 'Unknown authors'
        else:
            authors_str = str(authors) if authors else 'Unknown authors'

        # Extract year from publication_date or use year field
        publication_date = doc.get('publication_date', '')
        year = doc.get('year', '')
        if publication_date and publication_date != 'Unknown':
            # Extract year from publication_date (format: YYYY-MM-DD or YYYY)
            year_str = str(publication_date)[:4] if len(str(publication_date)) >= 4 else year
        else:
            year_str = year if year else 'Unknown year'

        meta_label = QLabel(f"<i>{authors_str} ({year_str})</i>")
        meta_label.setStyleSheet(f"color: {UIConstants.COLOR_TEXT_GREY}; font-size: 10pt;")
        layout.addWidget(meta_label)

        # Row 3: Publication (using correct field name)
        publication = doc.get('publication', '')
        if publication and publication.strip():
            publication_label = QLabel(f"📖 {publication}")
            publication_label.setStyleSheet(f"color: {UIConstants.COLOR_TEXT_GREY}; font-size: 9pt;")
            layout.addWidget(publication_label)

        # Row 4: Document identifiers (PMID, DOI)
        id_parts = []
        pmid = doc.get('pmid')
        doi = doc.get('doi')

        if pmid:
            id_parts.append(f"PMID: {pmid}")
        if doi:
            id_parts.append(f"DOI: {doi}")

        if id_parts:
            id_label = QLabel(' | '.join(id_parts))
            id_label.setStyleSheet("color: #888; font-size: 8pt;")
            layout.addWidget(id_label)

        # Row 5: Score Reasoning (in styled container)
        reasoning = score_result.get('reasoning', 'No reasoning provided')
        reasoning_container = QFrame()
        reasoning_container.setStyleSheet("""
            QFrame {
                background-color: #E3F2FD;
                border: 1px solid #BBDEFB;
                border-radius: 5px;
                padding: 6px;
            }
        """)
        reasoning_layout = QVBoxLayout(reasoning_container)
        reasoning_layout.setContentsMargins(6, 6, 6, 6)
        reasoning_layout.setSpacing(3)

        reasoning_title = QLabel("<b>AI Reasoning:</b>")
        reasoning_title.setStyleSheet("font-size: 9pt; background-color: transparent; border: none;")
        reasoning_layout.addWidget(reasoning_title)

        reasoning_text = QLabel(reasoning)
        reasoning_text.setWordWrap(True)
        reasoning_text.setStyleSheet("color: #333; font-size: 9pt; background-color: transparent; border: none;")
        reasoning_layout.addWidget(reasoning_text)

        layout.addWidget(reasoning_container)

        # Row 6: Abstract (FULL, never truncated - essential for human review)
        abstract = doc.get('abstract', '')
        if abstract and abstract.strip():
            abstract_container = QFrame()
            abstract_container.setStyleSheet("""
                QFrame {
                    background-color: #F5F5F5;
                    border: 1px solid #E0E0E0;
                    border-radius: 5px;
                    padding: 6px;
                }
            """)
            abstract_layout = QVBoxLayout(abstract_container)
            abstract_layout.setContentsMargins(6, 6, 6, 6)
            abstract_layout.setSpacing(3)

            abstract_title = QLabel("<b>Abstract:</b>")
            abstract_title.setStyleSheet("font-size: 9pt; background-color: transparent; border: none;")
            abstract_layout.addWidget(abstract_title)

            # Display FULL abstract with word wrapping (never truncate)
            abstract_text = QLabel(abstract)
            abstract_text.setWordWrap(True)
            abstract_text.setStyleSheet("color: #555; font-size: 9pt; background-color: transparent; border: none;")
            abstract_layout.addWidget(abstract_text)

            layout.addWidget(abstract_container)

        return frame

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

            self.logger.info("✅ Research tab widget cleanup complete")

        except Exception as e:
            self.logger.error(f"Error during research tab widget cleanup: {e}", exc_info=True)
