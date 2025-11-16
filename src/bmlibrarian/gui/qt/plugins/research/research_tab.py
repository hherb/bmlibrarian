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
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QFont, QPalette
from typing import Optional


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
    status_message = Signal(str)  # Status updates
    workflow_started = Signal()  # Workflow execution started
    workflow_completed = Signal(dict)  # Workflow completed with results
    workflow_error = Signal(Exception)  # Workflow error occurred

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize research tab.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)

        # Workflow state
        self.current_results = {}
        self.workflow_running = False

        # Initialize UI
        self._setup_ui()

    def _setup_ui(self):
        """Setup the user interface with Qt-native design."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)

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
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: #1976D2;")  # Blue color
        header_layout.addWidget(title)

        # Subtitle
        subtitle = QLabel("AI-Powered Evidence-Based Medical Literature Research")
        subtitle_font = QFont()
        subtitle_font.setPointSize(10)
        subtitle.setFont(subtitle_font)
        subtitle.setStyleSheet("color: #666666;")  # Grey color
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
        controls_frame.setStyleSheet("""
            QFrame {
                background-color: #F5F5F5;
                border: 1px solid #E0E0E0;
                border-radius: 8px;
                padding: 10px;
            }
        """)

        controls_layout = QVBoxLayout(controls_frame)
        controls_layout.setSpacing(10)

        # Row 1: Question input + Start button
        row1 = QHBoxLayout()
        row1.setSpacing(10)

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
        self.question_input.setMaximumHeight(100)
        self.question_input.setMinimumHeight(70)
        self.question_input.textChanged.connect(self._on_question_changed)
        question_container.addWidget(self.question_input)
        row1.addLayout(question_container, stretch=1)

        # Start button
        self.start_button = QPushButton("Start Research")
        self.start_button.setIcon(self.start_button.style().standardIcon(
            self.start_button.style().StandardPixmap.SP_MediaPlay
        ))
        self.start_button.setMinimumHeight(45)
        self.start_button.setMinimumWidth(140)
        self.start_button.setEnabled(False)
        self.start_button.setStyleSheet("""
            QPushButton {
                background-color: #1976D2;
                color: white;
                font-weight: bold;
                border-radius: 4px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #1565C0;
            }
            QPushButton:disabled {
                background-color: #BDBDBD;
            }
        """)
        self.start_button.clicked.connect(self._on_start_research)
        row1.addWidget(self.start_button, alignment=Qt.AlignmentFlag.AlignBottom)

        controls_layout.addLayout(row1)

        # Row 2: Parameters and toggles
        row2 = QHBoxLayout()
        row2.setSpacing(15)

        # Max Results
        max_results_label = QLabel("Max Results:")
        row2.addWidget(max_results_label)

        self.max_results_spin = QSpinBox()
        self.max_results_spin.setMinimum(10)
        self.max_results_spin.setMaximum(1000)
        self.max_results_spin.setValue(100)
        self.max_results_spin.setFixedWidth(80)
        self.max_results_spin.setToolTip("Maximum number of documents to retrieve from database")
        row2.addWidget(self.max_results_spin)

        # Min Relevant
        min_relevant_label = QLabel("Min Relevant:")
        row2.addWidget(min_relevant_label)

        self.min_relevant_spin = QSpinBox()
        self.min_relevant_spin.setMinimum(1)
        self.min_relevant_spin.setMaximum(100)
        self.min_relevant_spin.setValue(10)
        self.min_relevant_spin.setFixedWidth(80)
        self.min_relevant_spin.setToolTip(
            "Minimum high-scoring documents to find (triggers iterative search)"
        )
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

    def _create_search_tab(self) -> QWidget:
        """Create Search tab (query generation and display)."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)

        label = QLabel("🔍 Search Query Generation")
        label_font = QFont()
        label_font.setPointSize(12)
        label_font.setBold(True)
        label.setFont(label_font)
        layout.addWidget(label)

        description = QLabel(
            "This tab will display:\n"
            "• Research question\n"
            "• Generated PostgreSQL query\n"
            "• Multi-model query details (if enabled)\n"
            "• Query performance statistics\n"
            "• Interactive query editing (in interactive mode)"
        )
        description.setStyleSheet("color: #666666; margin-top: 10px;")
        layout.addWidget(description)

        layout.addStretch()
        return widget

    def _create_literature_tab(self) -> QWidget:
        """Create Literature tab (document list)."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)

        label = QLabel("📚 Literature Documents")
        label_font = QFont()
        label_font.setPointSize(12)
        label_font.setBold(True)
        label.setFont(label_font)
        layout.addWidget(label)

        description = QLabel(
            "This tab will display:\n"
            "• List of all documents found by search\n"
            "• Document cards with title, authors, journal, year\n"
            "• Expandable abstracts\n"
            "• Document metadata (DOI, PMID, etc.)"
        )
        description.setStyleSheet("color: #666666; margin-top: 10px;")
        layout.addWidget(description)

        layout.addStretch()
        return widget

    def _create_scoring_tab(self) -> QWidget:
        """Create Scoring tab (document relevance scoring)."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)

        label = QLabel("📊 Document Scoring")
        label_font = QFont()
        label_font.setPointSize(12)
        label_font.setBold(True)
        label.setFont(label_font)
        layout.addWidget(label)

        description = QLabel(
            "This tab will display:\n"
            "• Interactive scoring interface (in interactive mode)\n"
            "• Automated scoring results (in auto mode)\n"
            "• Document relevance scores (1-5 scale)\n"
            "• Color-coded score badges\n"
            "• Scoring progress and statistics"
        )
        description.setStyleSheet("color: #666666; margin-top: 10px;")
        layout.addWidget(description)

        layout.addStretch()
        return widget

    def _create_citations_tab(self) -> QWidget:
        """Create Citations tab (extracted citations)."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)

        label = QLabel("💬 Citations")
        label_font = QFont()
        label_font.setPointSize(12)
        label_font.setBold(True)
        label.setFont(label_font)
        layout.addWidget(label)

        description = QLabel(
            "This tab will display:\n"
            "• Extracted citations from high-scoring documents\n"
            "• Citation cards with document title and relevant passage\n"
            "• Relevance scores for each citation\n"
            "• Grouped by document\n"
            "• Interactive citation requests (in interactive mode)"
        )
        description.setStyleSheet("color: #666666; margin-top: 10px;")
        layout.addWidget(description)

        layout.addStretch()
        return widget

    def _create_preliminary_tab(self) -> QWidget:
        """Create Preliminary Report tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)

        label = QLabel("📄 Preliminary Report")
        label_font = QFont()
        label_font.setPointSize(12)
        label_font.setBold(True)
        label.setFont(label_font)
        layout.addWidget(label)

        description = QLabel(
            "This tab will display:\n"
            "• Preliminary report (before counterfactual analysis)\n"
            "• Markdown-rendered content\n"
            "• Word count and citation statistics\n"
            "• Interactive report editing (in interactive mode)\n"
            "• Export options"
        )
        description.setStyleSheet("color: #666666; margin-top: 10px;")
        layout.addWidget(description)

        layout.addStretch()
        return widget

    def _create_counterfactual_tab(self) -> QWidget:
        """Create Counterfactual Analysis tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)

        label = QLabel("🧠 Counterfactual Analysis")
        label_font = QFont()
        label_font.setPointSize(12)
        label_font.setBold(True)
        label.setFont(label_font)
        layout.addWidget(label)

        description = QLabel(
            "This tab will display:\n"
            "• Research questions for finding contradictory evidence\n"
            "• Search results for contradictory documents\n"
            "• Contradictory document list\n"
            "• Evidence assessment\n"
            "• Interactive controls (skip, regenerate)"
        )
        description.setStyleSheet("color: #666666; margin-top: 10px;")
        layout.addWidget(description)

        layout.addStretch()
        return widget

    def _create_report_tab(self) -> QWidget:
        """Create Final Report tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)

        label = QLabel("📋 Final Report")
        label_font = QFont()
        label_font.setPointSize(12)
        label_font.setBold(True)
        label.setFont(label_font)
        layout.addWidget(label)

        description = QLabel(
            "This tab will display:\n"
            "• Final comprehensive report (with counterfactual evidence)\n"
            "• Markdown-rendered content\n"
            "• Supporting and contradictory evidence sections\n"
            "• Word count, citation count, metadata\n"
            "• Export options (Markdown, PDF)"
        )
        description.setStyleSheet("color: #666666; margin-top: 10px;")
        layout.addWidget(description)

        layout.addStretch()
        return widget

    def _create_settings_tab(self) -> QWidget:
        """Create Settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)

        label = QLabel("⚙️ Settings")
        label_font = QFont()
        label_font.setPointSize(12)
        label_font.setBold(True)
        label.setFont(label_font)
        layout.addWidget(label)

        description = QLabel(
            "This tab will display:\n"
            "• Agent configuration options\n"
            "• Model selection dropdowns\n"
            "• Parameter sliders (temperature, top_p, etc.)\n"
            "• Quick toggles for workflow options\n"
            "• Database and Ollama connection status\n"
            "• Reset to defaults button"
        )
        description.setStyleSheet("color: #666666; margin-top: 10px;")
        layout.addWidget(description)

        layout.addStretch()
        return widget

    # ========================================================================
    # Event Handlers
    # ========================================================================

    @Slot()
    def _on_question_changed(self):
        """Handle research question text changes."""
        has_text = len(self.question_input.toPlainText().strip()) > 0
        self.start_button.setEnabled(has_text and not self.workflow_running)

    @Slot()
    def _on_start_research(self):
        """Handle Start Research button click."""
        question = self.question_input.toPlainText().strip()

        if not question:
            return

        # Phase 1: Just show a message
        # Phase 2+: Will connect to real workflow
        self.status_message.emit(f"Research started: {question[:50]}...")
        self.start_button.setEnabled(False)

        # TODO Phase 2: Connect to real workflow executor
        # TODO Phase 3: Execute workflow in background thread

        # For now, just show a placeholder message
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(
            self,
            "Phase 1 - Layout Complete",
            f"Research question received:\n\n{question}\n\n"
            "This is Phase 1 (layout only).\n"
            "Phase 2 will connect to real agents and execute the workflow."
        )

        self.start_button.setEnabled(True)
