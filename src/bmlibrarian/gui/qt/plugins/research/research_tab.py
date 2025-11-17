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

        # UI Components (initialized in _setup_ui)
        self.question_input: Optional[QTextEdit] = None
        self.start_button: Optional[QPushButton] = None
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
        row1.addWidget(self.start_button, alignment=Qt.AlignmentFlag.AlignBottom)

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
        return self._create_placeholder_tab(
            "🧠",
            "Counterfactual Analysis",
            "This tab will display:\n"
            "• Research questions for finding contradictory evidence\n"
            "• Search results for contradictory documents\n"
            "• Contradictory document list\n"
            "• Evidence assessment\n"
            "• Interactive controls (skip, regenerate)"
        )

    def _create_report_tab(self) -> QWidget:
        """Create Final Report tab."""
        return self._create_placeholder_tab(
            "📋",
            "Final Report",
            "This tab will display:\n"
            "• Final comprehensive report (with counterfactual evidence)\n"
            "• Markdown-rendered content\n"
            "• Supporting and contradictory evidence sections\n"
            "• Word count, citation count, metadata\n"
            "• Export options (Markdown, PDF)"
        )

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

            # Phase 2: Call workflow executor (just test agent connection)
            # Phase 3+: Will execute full workflow
            self.status_message.emit(f"Research started: {question[:50]}...")
            self.start_button.setEnabled(False)
            self.workflow_running = True

            self.logger.info(f"Research started: {question[:100]}")
            self.logger.debug(
                f"Parameters: max_results={max_results}, min_relevant={min_relevant}, "
                f"interactive={self.interactive_checkbox.isChecked()}, "
                f"counterfactual={self.counterfactual_checkbox.isChecked()}"
            )

            # Start workflow (Phase 2: agent connection test)
            self.workflow_executor.start_workflow(
                question=question,
                max_results=max_results,
                min_relevant=min_relevant,
                interactive=self.interactive_checkbox.isChecked(),
                counterfactual=self.counterfactual_checkbox.isChecked()
            )

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

        Updates the Search tab to display the document count.

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

    def _clear_layout_widgets(self, layout: QVBoxLayout) -> None:
        """
        Safely clear all widgets from a layout with proper cleanup.

        This method uses aggressive signal disconnection (widget.disconnect()) because:
        1. Widgets are being permanently destroyed via deleteLater()
        2. We want to prevent any lingering signal connections from causing errors
        3. These are self-contained UI components with no external dependencies

        Args:
            layout: The layout to clear
        """
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                widget = child.widget()
                try:
                    # Disconnect ALL signals - safe because widget is being deleted
                    # This prevents any lingering connections from accessing deleted objects
                    widget.disconnect()
                except RuntimeError:
                    # Widget already deleted - safe to ignore
                    pass
                # Set parent to None to ensure immediate cleanup
                widget.setParent(None)
                # Schedule deletion
                widget.deleteLater()

    def _update_literature_tab(self, scored_documents: list) -> None:
        """
        Update the Literature tab with scored documents.

        Args:
            scored_documents: List of (document, score_result) tuples
        """
        try:
            # Clear existing widgets with proper cleanup
            self._clear_layout_widgets(self.literature_layout)

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
            for i, (doc, score_result) in enumerate(sorted_docs):
                card = self._create_document_score_card(i + 1, doc, score_result)
                self.literature_layout.addWidget(card)

            # Add stretch at the end
            self.literature_layout.addStretch()

            self.logger.info(f"Literature tab updated with {len(scored_documents)} documents")

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
            self._clear_layout_widgets(self.citations_layout)

            if not citations:
                # Show empty state
                empty_label = QLabel("No citations to display")
                empty_label.setStyleSheet(f"color: {UIConstants.COLOR_TEXT_GREY}; padding: 20px;")
                empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.citations_layout.addWidget(empty_label)
                self.citations_layout.addStretch()
                return

            # Create citation cards
            for i, citation in enumerate(citations):
                card = self._create_citation_card(i + 1, citation)
                self.citations_layout.addWidget(card)

            # Add stretch at the end
            self.citations_layout.addStretch()

            self.logger.info(f"Citations tab updated with {len(citations)} citations")

        except Exception as e:
            self.logger.error(f"Error updating citations tab: {e}", exc_info=True)

    def _create_citation_card(self, index: int, citation: dict) -> QFrame:
        """
        Create a citation card showing document info and relevant passage.

        Args:
            index: Citation number (for display)
            citation: Citation dictionary

        Returns:
            QFrame containing the citation card
        """
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.Box)
        frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 1px solid #E0E0E0;
                border-radius: 4px;
                padding: 10px;
            }
        """)

        layout = QVBoxLayout(frame)
        layout.setSpacing(5)

        # Row 1: Citation number and document title
        title = citation.get('document_title', 'Untitled Document')
        title_label = QLabel(f"<b>{index}. {title}</b>")
        title_label.setWordWrap(True)
        layout.addWidget(title_label)

        # Row 2: Authors and Year
        authors = citation.get('authors', 'Unknown authors')
        year = citation.get('year', 'Unknown year')
        meta_label = QLabel(f"{authors} ({year})")
        meta_label.setStyleSheet(f"color: {UIConstants.COLOR_TEXT_GREY}; font-size: 10pt;")
        layout.addWidget(meta_label)

        # Row 3: Relevant passage
        passage = citation.get('passage', 'No passage extracted')
        passage_label = QLabel(f'<i>"{passage}"</i>')
        passage_label.setWordWrap(True)
        passage_label.setStyleSheet("color: #333; font-size: 10pt; padding: 5px 0; background-color: #F9F9F9; border-left: 3px solid #2196F3; padding-left: 10px;")
        layout.addWidget(passage_label)

        # Row 4: Relevance note (if available)
        relevance_note = citation.get('relevance_note', '')
        if relevance_note:
            note_label = QLabel(f"<i>Note: {relevance_note}</i>")
            note_label.setWordWrap(True)
            note_label.setStyleSheet(f"color: {UIConstants.COLOR_TEXT_GREY}; font-size: 9pt;")
            layout.addWidget(note_label)

        return frame

    def _create_document_score_card(self, index: int, doc: dict, score_result: dict) -> QFrame:
        """
        Create a document card showing score and metadata.

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
                border-radius: 4px;
                padding: 10px;
            }
        """)

        layout = QVBoxLayout(frame)
        layout.setSpacing(5)

        # Row 1: Index, Title, and Score Badge
        title_row = QHBoxLayout()

        # Index and Title
        title = doc.get('title', 'Untitled Document')
        title_label = QLabel(f"<b>{index}. {title}</b>")
        title_label.setWordWrap(True)
        title_row.addWidget(title_label, 1)

        # Score badge
        score = score_result.get('score', 0)
        confidence = score_result.get('confidence', 1.0)

        score_badge = QLabel(f"⭐ {score:.1f}")
        score_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Color based on score (using constants)
        if score >= UIConstants.SCORE_THRESHOLD_HIGH_RELEVANCE:
            bgcolor = UIConstants.SCORE_COLOR_HIGH
        elif score >= UIConstants.SCORE_THRESHOLD_RELEVANT:
            bgcolor = UIConstants.SCORE_COLOR_RELEVANT
        elif score >= UIConstants.SCORE_THRESHOLD_SOMEWHAT_RELEVANT:
            bgcolor = UIConstants.SCORE_COLOR_SOMEWHAT
        else:
            bgcolor = UIConstants.SCORE_COLOR_LOW

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
        authors = doc.get('authors', 'Unknown authors')
        year = doc.get('year', 'Unknown year')
        meta_label = QLabel(f"{authors} ({year})")
        meta_label.setStyleSheet(f"color: {UIConstants.COLOR_TEXT_GREY}; font-size: 10pt;")
        layout.addWidget(meta_label)

        # Row 3: Journal
        journal = doc.get('journal', 'Unknown journal')
        journal_label = QLabel(f"📖 {journal}")
        journal_label.setStyleSheet(f"color: {UIConstants.COLOR_TEXT_GREY}; font-size: 9pt;")
        layout.addWidget(journal_label)

        # Row 4: Score Reasoning (collapsed by default)
        reasoning = score_result.get('reasoning', 'No reasoning provided')
        reasoning_label = QLabel(f"<i>Reasoning: {reasoning}</i>")
        reasoning_label.setWordWrap(True)
        reasoning_label.setStyleSheet("color: #666; font-size: 9pt; padding: 5px 0;")
        layout.addWidget(reasoning_label)

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
            self._safe_disconnect(self.max_results_spin.valueChanged, self._on_max_results_changed)
            self._safe_disconnect(self.min_relevant_spin.valueChanged, self._on_min_relevant_changed)

            self.logger.info("✅ Research tab widget cleanup complete")

        except Exception as e:
            self.logger.error(f"Error during research tab widget cleanup: {e}", exc_info=True)
