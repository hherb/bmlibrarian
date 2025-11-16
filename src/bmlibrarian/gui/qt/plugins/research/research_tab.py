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

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize research tab.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)

        # Logger
        self.logger = logging.getLogger("bmlibrarian.gui.qt.plugins.research.ResearchTabWidget")

        # Workflow state
        self.current_results: dict = {}
        self.workflow_running: bool = False

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
        header_layout.setContentsMargins(0, 0, 0, 10)
        header_layout.setSpacing(5)

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
        layout.setContentsMargins(15, 15, 15, 15)

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
        """Create Search tab (query generation and display)."""
        return self._create_placeholder_tab(
            "🔍",
            "Search Query Generation",
            "This tab will display:\n"
            "• Research question\n"
            "• Generated PostgreSQL query\n"
            "• Multi-model query details (if enabled)\n"
            "• Query performance statistics\n"
            "• Interactive query editing (in interactive mode)"
        )

    def _create_literature_tab(self) -> QWidget:
        """Create Literature tab (document list)."""
        return self._create_placeholder_tab(
            "📚",
            "Literature Documents",
            "This tab will display:\n"
            "• List of all documents found by search\n"
            "• Document cards with title, authors, journal, year\n"
            "• Expandable abstracts\n"
            "• Document metadata (DOI, PMID, etc.)"
        )

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
        return self._create_placeholder_tab(
            "💬",
            "Citations",
            "This tab will display:\n"
            "• Extracted citations from high-scoring documents\n"
            "• Citation cards with document title and relevant passage\n"
            "• Relevance scores for each citation\n"
            "• Grouped by document\n"
            "• Interactive citation requests (in interactive mode)"
        )

    def _create_preliminary_tab(self) -> QWidget:
        """Create Preliminary Report tab."""
        return self._create_placeholder_tab(
            "📄",
            "Preliminary Report",
            "This tab will display:\n"
            "• Preliminary report (before counterfactual analysis)\n"
            "• Markdown-rendered content\n"
            "• Word count and citation statistics\n"
            "• Interactive report editing (in interactive mode)\n"
            "• Export options"
        )

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
    def _on_min_relevant_changed(self, value: int) -> None:
        """
        Handle min relevant value changes with validation.

        Args:
            value: New min relevant value
        """
        try:
            # Validate: min_relevant should not exceed max_results
            max_results = self.max_results_spin.value()
            if value > max_results:
                self.logger.warning(
                    f"Min relevant ({value}) exceeds max results ({max_results}). "
                    "Adjusting max results."
                )
                self.max_results_spin.setValue(value)
        except Exception as e:
            self.logger.error(f"Error in _on_min_relevant_changed: {e}", exc_info=True)

    @Slot()
    def _on_start_research(self) -> None:
        """Handle Start Research button click with error handling."""
        try:
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

            # Phase 1: Just show a message
            # Phase 2+: Will connect to real workflow
            self.status_message.emit(f"Research started: {question[:50]}...")
            self.start_button.setEnabled(False)

            self.logger.info(f"Research started: {question[:100]}")
            self.logger.debug(
                f"Parameters: max_results={max_results}, min_relevant={min_relevant}, "
                f"interactive={self.interactive_checkbox.isChecked()}, "
                f"counterfactual={self.counterfactual_checkbox.isChecked()}"
            )

            # TODO Phase 2: Connect to real workflow executor
            # TODO Phase 3: Execute workflow in background thread

            # For now, just show a placeholder message
            QMessageBox.information(
                self,
                "Phase 1 - Layout Complete",
                f"Research question received:\n\n{question}\n\n"
                f"Parameters:\n"
                f"• Max Results: {max_results}\n"
                f"• Min Relevant: {min_relevant}\n"
                f"• Interactive: {self.interactive_checkbox.isChecked()}\n"
                f"• Counterfactual: {self.counterfactual_checkbox.isChecked()}\n\n"
                "This is Phase 1 (layout only).\n"
                "Phase 2 will connect to real agents and execute the workflow."
            )

            self.start_button.setEnabled(True)

        except Exception as e:
            self.logger.error(f"Error in _on_start_research: {e}", exc_info=True)
            self.start_button.setEnabled(True)
            QMessageBox.critical(
                self,
                "Error",
                f"An error occurred while starting research:\n\n{str(e)}"
            )
            self.workflow_error.emit(e)
