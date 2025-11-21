"""
Research tab widget for BMLibrarian Qt GUI.

Qt-native design matching Flet functionality with proper Qt widgets and layouts.
This is the main widget that orchestrates the research workflow interface.
"""

from typing import Optional
import logging

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
    QFrame,
    QSizePolicy,
    QMessageBox,
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QFont

# Import refactored modules
from .constants import UIConstants, StyleSheets
from .tab_builders import (
    build_search_tab,
    build_literature_tab,
    build_scoring_tab,
    build_citations_tab,
    build_preliminary_tab,
    build_counterfactual_tab,
    build_report_tab,
    TabRefs,
)
from .workflow_handlers import WorkflowHandlersMixin
from . import export_utils

# Import document card factory
from ...qt_document_card_factory import QtDocumentCardFactory
from ...resources.styles import get_font_scale

# Import PDF manager
from bmlibrarian.utils.pdf_manager import PDFManager
from pathlib import Path
import os


class ResearchTabWidget(WorkflowHandlersMixin, QWidget):
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

        # Tab UI references (populated during tab creation)
        self.search_refs: Optional[TabRefs] = None
        self.literature_refs: Optional[TabRefs] = None
        self.citations_refs: Optional[TabRefs] = None
        self.preliminary_refs: Optional[TabRefs] = None
        self.counterfactual_refs: Optional[TabRefs] = None
        self.report_refs: Optional[TabRefs] = None

        # Agents and workflow executor
        self.agents: Optional[dict] = agents
        self.workflow_executor: Optional['QtWorkflowExecutor'] = None

        # Initialize workflow executor if agents available
        if self.agents:
            self._initialize_workflow_executor()
        else:
            self.logger.warning("No agents provided - workflow functionality disabled")

        # Workflow thread (Background execution)
        self.workflow_thread: Optional['WorkflowThread'] = None

        # Document card factory for creating consistent document cards
        # Initialize PDF manager for handling PDF downloads and storage
        pdf_dir_str = os.getenv('PDF_BASE_DIR', '~/knowledgebase/pdf')
        pdf_base_dir = Path(pdf_dir_str).expanduser()
        self.pdf_manager = PDFManager(base_dir=str(pdf_base_dir))
        self.document_card_factory = QtDocumentCardFactory(
            pdf_manager=self.pdf_manager,
            base_pdf_dir=pdf_base_dir
        )
        self.logger.info("Document card factory initialized with PDF manager")

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

    def _initialize_workflow_executor(self) -> None:
        """Initialize the workflow executor with signal connections."""
        from .workflow_executor import QtWorkflowExecutor

        self.workflow_executor = QtWorkflowExecutor(self.agents, parent=self)

        # Connect workflow signals
        self.workflow_executor.workflow_started.connect(self._on_workflow_started)
        self.workflow_executor.workflow_completed.connect(self._on_workflow_completed)
        self.workflow_executor.workflow_error.connect(self._on_workflow_error)
        self.workflow_executor.status_message.connect(self._on_workflow_status)

        # Connect step-specific signals
        self.workflow_executor.query_generated.connect(self._on_query_generated)
        self.workflow_executor.documents_found.connect(self._on_documents_found)
        self.workflow_executor.scoring_progress.connect(self._on_scoring_progress)
        self.workflow_executor.documents_scored.connect(self._on_documents_scored)
        self.workflow_executor.citations_extracted.connect(self._on_citations_extracted)
        self.workflow_executor.preliminary_report_generated.connect(self._on_preliminary_report_generated)

        self.logger.info("Workflow executor initialized with agents")

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

        # 1. Header section
        header = self._create_header_section()
        main_layout.addWidget(header)

        # 2. Controls section
        controls = self._create_controls_section()
        main_layout.addWidget(controls)

        # 3. Tabbed interface
        self.research_tabs = self._create_tabbed_interface()
        main_layout.addWidget(self.research_tabs, stretch=1)

        # 4. Status bar
        status_bar = self._create_status_bar()
        main_layout.addWidget(status_bar)

    def _create_header_section(self) -> QWidget:
        """Create header section with single-line title."""
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
        header_layout.addStretch()
        header_widget.setMaximumHeight(40)

        return header_widget

    def _create_controls_section(self) -> QWidget:
        """Create controls section with question input, parameters, and buttons."""
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
        self.question_input.setPlaceholderText("Enter your biomedical research question here...")
        self.question_input.setMaximumHeight(60)
        self.question_input.setMinimumHeight(60)
        self.question_input.setStyleSheet(StyleSheets.text_input(self.ui, self.scale))
        self.question_input.textChanged.connect(self._on_question_changed)
        row2.addWidget(self.question_input, stretch=1)

        # Start button
        self.start_button = QPushButton("Start Research")
        self.start_button.setMinimumHeight(60)
        self.start_button.setMinimumWidth(140)
        self.start_button.setEnabled(False)
        self.start_button.setStyleSheet(StyleSheets.start_button(self.ui, self.scale))
        self.start_button.clicked.connect(self._on_start_research)
        row2.addWidget(self.start_button)

        # Cancel button (hidden initially)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setMinimumHeight(60)
        self.cancel_button.setMinimumWidth(140)
        self.cancel_button.setEnabled(False)
        self.cancel_button.setVisible(False)
        self.cancel_button.setStyleSheet(StyleSheets.cancel_button(self.ui))
        self.cancel_button.clicked.connect(self._on_cancel_clicked)
        row2.addWidget(self.cancel_button)

        # New button
        self.new_button = QPushButton("New")
        self.new_button.setMinimumHeight(60)
        self.new_button.setMinimumWidth(80)
        self.new_button.setStyleSheet(StyleSheets.new_button(self.ui))
        self.new_button.clicked.connect(self._on_new_research)
        row2.addWidget(self.new_button)

        controls_layout.addLayout(row2)

        # Row 3: Parameters and toggles
        row3 = QHBoxLayout()
        row3.setSpacing(self.ui.ROW2_SPACING)

        # Max Results
        row3.addWidget(QLabel("Max results:"))
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
        row3.addWidget(QLabel("Min relevant:"))
        self.min_relevant_spin = QSpinBox()
        self.min_relevant_spin.setMinimum(self.ui.MIN_RELEVANT_MIN)
        self.min_relevant_spin.setMaximum(self.ui.MIN_RELEVANT_MAX)
        self.min_relevant_spin.setValue(self.ui.MIN_RELEVANT_DEFAULT)
        self.min_relevant_spin.setFixedWidth(self.ui.SPINBOX_WIDTH)
        self.min_relevant_spin.setStyleSheet(StyleSheets.text_input(self.ui, self.scale))
        self.min_relevant_spin.setToolTip("Minimum high-scoring documents to find (triggers iterative search)")
        self.min_relevant_spin.valueChanged.connect(self._on_min_relevant_changed)
        row3.addWidget(self.min_relevant_spin)

        row3.addSpacing(20)

        # Toggles
        self.interactive_checkbox = QCheckBox("Interactive mode")
        self.interactive_checkbox.setChecked(False)
        self.interactive_checkbox.setToolTip("Enable human-in-the-loop for query editing, manual scoring, etc.")
        row3.addWidget(self.interactive_checkbox)

        self.counterfactual_checkbox = QCheckBox("Counterfactual analysis")
        self.counterfactual_checkbox.setChecked(True)
        self.counterfactual_checkbox.setToolTip("Search for contradictory evidence and create balanced report")
        row3.addWidget(self.counterfactual_checkbox)

        self.study_quality_checkbox = QCheckBox("Study quality rating")
        self.study_quality_checkbox.setChecked(False)
        self.study_quality_checkbox.setToolTip("Assess and display study quality metrics for documents")
        row3.addWidget(self.study_quality_checkbox)

        row3.addStretch()
        controls_layout.addLayout(row3)

        return controls_frame

    def _create_status_bar(self) -> QWidget:
        """Create status bar with progress indicator and status messages."""
        status_widget = QWidget()
        status_widget.setStyleSheet(StyleSheets.status_bar(self.ui))
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
        """Create the 8-tab interface for workflow stages."""
        tab_widget = QTabWidget()
        tab_widget.setTabPosition(QTabWidget.TabPosition.North)
        tab_widget.setMovable(False)
        tab_widget.setDocumentMode(False)

        # Create tabs using builder functions
        search_tab, self.search_refs = build_search_tab(self.ui)
        literature_tab, self.literature_refs = build_literature_tab(self.ui)
        scoring_tab, _ = build_scoring_tab(self.ui)
        citations_tab, self.citations_refs = build_citations_tab(self.ui)
        preliminary_tab, self.preliminary_refs = build_preliminary_tab(self.ui)
        counterfactual_tab, self.counterfactual_refs = build_counterfactual_tab(self.ui)
        report_tab, self.report_refs = build_report_tab(self.ui)
        settings_tab = self._create_settings_tab()

        # Connect export button signals
        if self.report_refs and 'save_markdown_button' in self.report_refs.widgets:
            self.report_refs.widgets['save_markdown_button'].clicked.connect(self._on_save_markdown_report)
        if self.report_refs and 'export_json_button' in self.report_refs.widgets:
            self.report_refs.widgets['export_json_button'].clicked.connect(self._on_export_json_report)

        # Add tabs
        tab_widget.addTab(search_tab, "Search")
        tab_widget.addTab(literature_tab, "Literature")
        tab_widget.addTab(scoring_tab, "Scoring")
        tab_widget.addTab(citations_tab, "Citations")
        tab_widget.addTab(preliminary_tab, "Preliminary")
        tab_widget.addTab(counterfactual_tab, "Counterfactual")
        tab_widget.addTab(report_tab, "Report")
        tab_widget.addTab(settings_tab, "Settings")

        return tab_widget

    def _create_settings_tab(self) -> QWidget:
        """Create Settings tab using the modular SettingsWidget."""
        from ..settings.plugin import SettingsWidget

        self.settings_widget = SettingsWidget(self)
        self.settings_widget.agents_need_reinit.connect(self._reinitialize_agents)

        return self.settings_widget

    def _reinitialize_agents(self) -> None:
        """Reinitialize agents with new configuration from settings."""
        try:
            from bmlibrarian.agents import (
                QueryAgent, DocumentScoringAgent, CitationFinderAgent,
                ReportingAgent, CounterfactualAgent, EditorAgent, AgentOrchestrator
            )

            self.logger.info("Reinitializing agents with new configuration...")

            orchestrator = AgentOrchestrator(max_workers=4)
            self.agents = {
                'query_agent': QueryAgent(orchestrator=orchestrator),
                'scoring_agent': DocumentScoringAgent(orchestrator=orchestrator),
                'citation_agent': CitationFinderAgent(orchestrator=orchestrator),
                'reporting_agent': ReportingAgent(orchestrator=orchestrator),
                'counterfactual_agent': CounterfactualAgent(orchestrator=orchestrator),
                'editor_agent': EditorAgent(orchestrator=orchestrator)
            }

            self.logger.info("Agents reinitialized successfully")

        except Exception as e:
            self.logger.error(f"Error reinitializing agents: {e}", exc_info=True)

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
        """Handle max results value changes with validation."""
        try:
            if self._validation_in_progress:
                return

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
        """Handle min relevant value changes with validation."""
        try:
            if self._validation_in_progress:
                return

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
                QMessageBox.warning(self, "No Question", "Please enter a research question before starting.")
                return

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

            if not self.workflow_executor:
                QMessageBox.critical(
                    self,
                    "Agents Not Initialized",
                    "BMLibrarian agents are not initialized.\n\n"
                    "The application may have failed to start properly.\n"
                    "Please check the logs and restart the application."
                )
                return

            # Start workflow
            self.status_message.emit(f"Research started: {question[:50]}...")
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
                score_threshold=3.0,
                enable_counterfactual=self.counterfactual_checkbox.isChecked(),
                parent=self
            )

            # Connect thread signals
            self._connect_workflow_thread_signals()

            # Start thread
            self.workflow_thread.start()
            self.logger.info("Background workflow thread started")

        except Exception as e:
            self.logger.error(f"Error in _on_start_research: {e}", exc_info=True)
            self.start_button.setEnabled(True)
            self.workflow_running = False
            QMessageBox.critical(self, "Error", f"An error occurred while starting research:\n\n{str(e)}")
            self.workflow_error.emit(e)

    @Slot()
    def _on_cancel_clicked(self) -> None:
        """Handle Cancel button click."""
        if not self.workflow_thread or not self.workflow_thread.isRunning():
            self.logger.warning("Cancel clicked but no workflow thread is running")
            return

        self.logger.info("User requested workflow cancellation")
        self.cancel_button.setEnabled(False)
        self.progress_label.setText("Cancelling workflow...")
        self.status_label.setText("Cancelled")
        self.workflow_thread.cancel()

    def _on_new_research(self) -> None:
        """Handle New button click to start a fresh research session."""
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

        self.current_results = {}
        self.counterfactual_results = None
        self.question_input.clear()

        self.logger.info("Starting new research session - clearing previous results")
        self.status_label.setText("Ready")
        self.progress_label.setText("")
        self.question_input.setFocus()

    # ========================================================================
    # Export Handlers
    # ========================================================================

    @Slot()
    def _on_save_markdown_report(self) -> None:
        """Handle Save Report (Markdown) button click."""
        export_utils.save_markdown_report(
            self,
            self.final_report_markdown,
            self.logger,
            lambda msg: self.status_message.emit(msg)
        )

    @Slot()
    def _on_export_json_report(self) -> None:
        """Handle Export as JSON button click."""
        export_utils.export_json_report(
            self,
            self.current_results,
            self.final_report_markdown,
            self.logger,
            lambda msg: self.status_message.emit(msg)
        )

    # ========================================================================
    # Cleanup
    # ========================================================================

    @staticmethod
    def _safe_disconnect(signal, slot) -> None:
        """Safely disconnect a signal from a slot."""
        try:
            signal.disconnect(slot)
        except (RuntimeError, TypeError):
            pass

    def cleanup(self) -> None:
        """Cleanup resources and disconnect signals."""
        try:
            self.logger.info("Cleaning up research tab widget...")

            # Cleanup workflow thread
            if self.workflow_thread and self.workflow_thread.isRunning():
                self.logger.info("Stopping workflow thread...")
                self.workflow_thread.cancel()
                self.workflow_thread.wait(5000)
                if self.workflow_thread.isRunning():
                    self.logger.warning("Workflow thread did not stop in time, forcing termination")
                    self.workflow_thread.terminate()
                    self.workflow_thread.wait()
                self.workflow_thread.deleteLater()
                self.workflow_thread = None

            # Disconnect workflow executor signals
            if self.workflow_executor:
                self._safe_disconnect(self.workflow_executor.workflow_started, self._on_workflow_started)
                self._safe_disconnect(self.workflow_executor.workflow_completed, self._on_workflow_completed)
                self._safe_disconnect(self.workflow_executor.workflow_error, self._on_workflow_error)
                self._safe_disconnect(self.workflow_executor.status_message, self._on_workflow_status)
                self._safe_disconnect(self.workflow_executor.query_generated, self._on_query_generated)
                self._safe_disconnect(self.workflow_executor.documents_found, self._on_documents_found)
                self._safe_disconnect(self.workflow_executor.scoring_progress, self._on_scoring_progress)
                self._safe_disconnect(self.workflow_executor.documents_scored, self._on_documents_scored)
                self._safe_disconnect(self.workflow_executor.citations_extracted, self._on_citations_extracted)
                self._safe_disconnect(self.workflow_executor.preliminary_report_generated, self._on_preliminary_report_generated)

                if hasattr(self.workflow_executor, 'cleanup'):
                    self.workflow_executor.cleanup()

            # Disconnect UI element signals
            self._safe_disconnect(self.question_input.textChanged, self._on_question_changed)
            self._safe_disconnect(self.start_button.clicked, self._on_start_research)
            self._safe_disconnect(self.cancel_button.clicked, self._on_cancel_clicked)
            self._safe_disconnect(self.max_results_spin.valueChanged, self._on_max_results_changed)
            self._safe_disconnect(self.min_relevant_spin.valueChanged, self._on_min_relevant_changed)

            # Disconnect export button signals
            if self.report_refs and 'save_markdown_button' in self.report_refs.widgets:
                self._safe_disconnect(self.report_refs.widgets['save_markdown_button'].clicked, self._on_save_markdown_report)
            if self.report_refs and 'export_json_button' in self.report_refs.widgets:
                self._safe_disconnect(self.report_refs.widgets['export_json_button'].clicked, self._on_export_json_report)

            self.logger.info("Research tab widget cleanup complete")

        except Exception as e:
            self.logger.error(f"Error during research tab widget cleanup: {e}", exc_info=True)
