"""
Systematic Review Tab Widget.

Main tab interface for the systematic review plugin providing:
- Checkpoint listing and selection
- Parameter modification for resume
- Real-time progress monitoring
- New review creation
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal, Slot, QThread
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QLabel,
    QPushButton,
    QGroupBox,
    QFormLayout,
    QLineEdit,
    QTextEdit,
    QDoubleSpinBox,
    QSpinBox,
    QComboBox,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QScrollArea,
    QFrame,
    QTabWidget,
    QFileDialog,
    QMessageBox,
    QPlainTextEdit,
)

from bmlibrarian.gui.qt.resources.styles.stylesheet_generator import (
    StylesheetGenerator,
)
from bmlibrarian.gui.qt.resources.styles.dpi_scale import scale_px
from bmlibrarian.gui.qt.widgets.markdown_viewer import MarkdownViewer
from bmlibrarian.agents.systematic_review.config import (
    DEFAULT_OUTPUT_DIR,
    DEFAULT_INCLUSION_CRITERIA,
    DEFAULT_EXCLUSION_CRITERIA,
    DEFAULT_RELEVANCE_THRESHOLD,
    DEFAULT_QUALITY_THRESHOLD,
)
from bmlibrarian.database import get_db_manager, DatabaseManager
from .report_preview_widget import ReportPreviewWidget

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

CHECKPOINT_TYPES = [
    "search_strategy",
    "initial_results",
    "scoring_complete",
    "quality_assessment",
]

CHECKPOINT_TYPE_DISPLAY_NAMES = {
    "search_strategy": "Search Strategy Generated",
    "initial_results": "Search Results Retrieved",
    "scoring_complete": "Relevance Scoring Complete",
    "quality_assessment": "Quality Assessment Complete",
}

# Worker thread constants
WORKER_CLEANUP_TIMEOUT_MS = 5000  # Timeout in milliseconds for worker cleanup


# =============================================================================
# Worker Thread for Background Operations
# =============================================================================

class ReviewWorker(QThread):
    """Worker thread for running systematic review operations."""

    progress_update = Signal(str, int)  # (message, percentage)
    step_progress = Signal(str, int, int)  # (step_name, current, total)
    activity_update = Signal(str)  # markdown activity log entry
    state_update = Signal(dict)  # accumulated state JSON
    checkpoint_reached = Signal(str, dict)  # (checkpoint_type, state)
    step_completed = Signal(str, dict)  # (step_name, metrics)
    review_complete = Signal(dict)  # result data
    report_update = Signal(str)  # markdown report content
    error_occurred = Signal(str)  # error message

    def __init__(
        self,
        db_manager: DatabaseManager,
        mode: str,  # "new" or "resume"
        checkpoint_path: Optional[str] = None,
        criteria_dict: Optional[Dict[str, Any]] = None,
        weights_dict: Optional[Dict[str, Any]] = None,
        config_overrides: Optional[Dict[str, Any]] = None,
        output_path: Optional[str] = None,
    ) -> None:
        """
        Initialize the review worker.

        Args:
            db_manager: DatabaseManager instance for database access
            mode: "new" for new review, "resume" for checkpoint resume
            checkpoint_path: Path to checkpoint file (for resume)
            criteria_dict: Search criteria dictionary (for new review)
            weights_dict: Scoring weights dictionary
            config_overrides: Configuration overrides (thresholds, etc.)
            output_path: Path to save output files
        """
        super().__init__()
        self.db_manager = db_manager
        self.mode = mode
        self.checkpoint_path = checkpoint_path
        self.criteria_dict = criteria_dict
        self.weights_dict = weights_dict
        self.config_overrides = config_overrides or {}
        self.output_path = output_path
        self._cancelled = False
        # Accumulated state for Details tab
        self._accumulated_state: Dict[str, Any] = {
            "mode": mode,
            "started_at": datetime.now().isoformat(),
            "config_overrides": config_overrides or {},
        }

    def cancel(self) -> None:
        """Cancel the running operation."""
        self._cancelled = True

    def run(self) -> None:
        """Execute the systematic review operation."""
        try:
            from bmlibrarian.agents.systematic_review.agent import (
                SystematicReviewAgent,
            )
            from bmlibrarian.agents.systematic_review.data_models import (
                SearchCriteria,
                ScoringWeights,
            )
            from bmlibrarian.agents.systematic_review.config import (
                get_systematic_review_config,
            )

            # Build config with overrides
            config = get_systematic_review_config()

            # Apply overrides
            if "relevance_threshold" in self.config_overrides:
                config.relevance_threshold = self.config_overrides["relevance_threshold"]
            if "quality_threshold" in self.config_overrides:
                config.quality_threshold = self.config_overrides["quality_threshold"]
            if "max_results_per_query" in self.config_overrides:
                config.max_results_per_query = self.config_overrides["max_results_per_query"]

            # Initialize agent with callback
            agent = SystematicReviewAgent(
                db_manager=self.db_manager,
                config=config,
                callback=self._progress_callback,
            )

            # Create checkpoint callback
            def checkpoint_callback(checkpoint_type: str, state: Dict) -> bool:
                if self._cancelled:
                    return False
                self.checkpoint_reached.emit(checkpoint_type, state)
                return True  # Auto-approve in GUI (user can cancel via button)

            if self.mode == "resume":
                # Resume from checkpoint
                self.progress_update.emit("Resuming from checkpoint...", 10)

                result = agent.run_review_from_checkpoint(
                    checkpoint_path=self.checkpoint_path,
                    interactive=False,
                    output_path=self.output_path,
                    checkpoint_callback=checkpoint_callback,
                )
            else:
                # Start new review
                self.progress_update.emit("Starting new review...", 5)

                # Build criteria
                criteria = SearchCriteria.from_dict(self.criteria_dict)

                # Build weights if provided
                weights = None
                if self.weights_dict:
                    weights = ScoringWeights.from_dict(self.weights_dict)

                result = agent.run_review(
                    criteria=criteria,
                    weights=weights,
                    interactive=False,
                    output_path=self.output_path,
                    checkpoint_callback=checkpoint_callback,
                )

            if not self._cancelled:
                self.review_complete.emit(result.to_dict())

        except Exception as e:
            logger.error(f"Review worker error: {e}", exc_info=True)
            self.error_occurred.emit(str(e))

    def _progress_callback(self, event: str, data: str) -> None:
        """
        Handle progress callbacks from the agent.

        Emits multiple signals to update different UI components:
        - progress_update: Overall progress bar
        - activity_update: Activity log markdown entries
        - step_progress: Per-step progress (current/total)
        - state_update: Accumulated JSON state
        """
        if self._cancelled:
            return

        # Parse event type to estimate progress
        progress_map = {
            "checkpoint_restored": 10,
            "execution_started": 15,
            "query_started": 20,
            "query_completed": 30,
            "execution_completed": 40,
            "filtering_started": 45,
            "filtering_complete": 50,
            "batch_scoring_started": 55,
            "scoring_started": 55,
            "scoring_progress": 60,
            "inclusion_evaluation_started": 60,
            "inclusion_evaluation_completed": 60,
            "scoring_completed": 65,
            "batch_scoring_completed": 70,
            "scoring_complete": 70,
            "quality_assessment_started": 75,
            "quality_started": 75,
            "quality_progress": 80,
            "quality_complete": 85,
            "quality_assessment_completed": 85,
            "reporting_started": 90,
            "reporting_complete": 95,
        }

        percentage = progress_map.get(event, 50)
        self.progress_update.emit(f"{event}: {data}", percentage)

        # Generate activity log entries based on event type
        activity_entry = self._format_activity_entry(event, data)
        if activity_entry:
            self.activity_update.emit(activity_entry)

        # Update accumulated state based on event
        self._update_accumulated_state(event, data)
        self.state_update.emit(self._accumulated_state.copy())

        # Parse step progress for specific events
        self._emit_step_progress(event, data)

    def _format_activity_entry(self, event: str, data: str) -> Optional[str]:
        """
        Format an activity log entry in markdown based on the event type.

        Args:
            event: The event name
            data: The event data string

        Returns:
            Markdown-formatted activity entry, or None if not loggable
        """
        timestamp = datetime.now().strftime("%H:%M:%S")

        # Map events to readable activity entries
        # Handle restored events (from checkpoint resume) with special formatting
        if data.startswith("[RESTORED]"):
            # Format restored events with a distinctive style
            restored_data = data.replace("[RESTORED] ", "")
            return f"**[{timestamp}]** 🔄 _{restored_data}_ (from checkpoint)\n"

        if event == "checkpoint_restored":
            return f"\n**[{timestamp}]** 📂 **Checkpoint Restored**\n{data}\n\n---\n"
        elif event == "execution_started":
            return f"**[{timestamp}]** Starting search execution...\n"
        elif event == "query_started":
            return f"**[{timestamp}]** Executing query: `{data[:100]}{'...' if len(data) > 100 else ''}`\n"
        elif event == "query_completed":
            return f"**[{timestamp}]** Query completed: {data}\n"
        elif event == "execution_completed":
            return f"**[{timestamp}]** ✓ Search execution completed: {data}\n\n---\n"
        elif event == "filtering_started":
            return f"**[{timestamp}]** Starting initial filtering...\n"
        elif event == "filtering_complete":
            return f"**[{timestamp}]** ✓ Filtering complete: {data}\n\n---\n"
        elif event == "batch_scoring_started":
            return f"**[{timestamp}]** Starting relevance scoring: {data}\n"
        elif event == "scoring_started":
            return None  # Don't log individual paper scoring starts (too verbose)
        elif event == "scoring_progress":
            # Format: "X/Y | Score S/5 for <title>" - extract the meaningful part
            if " | " in data:
                _, info = data.split(" | ", 1)
                return f"**[{timestamp}]** {info}\n"
            return f"**[{timestamp}]** {data}\n"
        elif event == "batch_scoring_completed" or event == "scoring_complete":
            return f"**[{timestamp}]** ✓ Scoring complete: {data}\n\n---\n"
        elif event == "quality_started":
            return f"**[{timestamp}]** Starting quality assessment...\n"
        elif event == "quality_progress":
            # Format: "X/Y | Quality S/10 for <title>" - extract the meaningful part
            if " | " in data:
                _, info = data.split(" | ", 1)
                return f"**[{timestamp}]** {info}\n"
            return f"**[{timestamp}]** {data}\n"
        elif event == "quality_complete" or event == "quality_assessment_completed":
            return f"**[{timestamp}]** ✓ Quality assessment complete: {data}\n\n---\n"
        elif event == "reporting_started":
            return f"**[{timestamp}]** Generating report...\n"
        elif event == "reporting_complete":
            return f"**[{timestamp}]** ✓ Report generation complete\n\n---\n"

        return None

    def _update_accumulated_state(self, event: str, data: str) -> None:
        """
        Update the accumulated state dictionary based on events.

        Args:
            event: The event name
            data: The event data string
        """
        if event == "query_completed":
            if "queries" not in self._accumulated_state:
                self._accumulated_state["queries"] = []
            self._accumulated_state["queries"].append({
                "timestamp": datetime.now().isoformat(),
                "result": data,
            })
        elif event == "execution_completed":
            self._accumulated_state["search_complete"] = True
            self._accumulated_state["search_summary"] = data
        elif event == "filtering_complete":
            self._accumulated_state["filtering_complete"] = True
            self._accumulated_state["filtering_summary"] = data
        elif event == "scoring_complete":
            self._accumulated_state["scoring_complete"] = True
            self._accumulated_state["scoring_summary"] = data
        elif event == "quality_complete":
            self._accumulated_state["quality_complete"] = True
            self._accumulated_state["quality_summary"] = data
        elif event == "reporting_complete":
            self._accumulated_state["reporting_complete"] = True

        self._accumulated_state["last_event"] = event
        self._accumulated_state["last_update"] = datetime.now().isoformat()

    def _emit_step_progress(self, event: str, data: str) -> None:
        """
        Parse and emit step-specific progress for UI progress indicators.

        Args:
            event: The event name
            data: The event data string (may contain "X/Y" format)
        """
        # Try to parse progress from data like "25/100 documents"
        import re
        match = re.search(r"(\d+)/(\d+)", data)
        if match:
            current = int(match.group(1))
            total = int(match.group(2))

            # Determine step name from event
            if "scoring" in event or "inclusion_evaluation" in event:
                step_name = "Relevance Scoring"
            elif "quality" in event:
                step_name = "Quality Assessment"
            elif "filtering" in event:
                step_name = "Initial Filtering"
            else:
                step_name = event.replace("_", " ").title()

            self.step_progress.emit(step_name, current, total)


# =============================================================================
# Main Tab Widget
# =============================================================================

class SystematicReviewTabWidget(QWidget):
    """
    Main widget for the systematic review tab.

    Provides:
    - Left panel: Checkpoint browser and parameter editor
    - Right panel: Progress monitoring and results display
    """

    status_message = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize the systematic review tab widget.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)
        self._worker: Optional[ReviewWorker] = None
        self._current_checkpoint_path: Optional[str] = None
        # Use the same default directory as the agent config
        self._review_directory: Path = Path(DEFAULT_OUTPUT_DIR).expanduser()

        # State tracking for right panel tabs
        self._activity_log: str = ""  # Accumulated markdown activity log
        self._accumulated_state: Dict[str, Any] = {}  # JSON state for Details tab
        self._report_content: str = ""  # Markdown report for Report tab
        self._last_result: Optional[Dict[str, Any]] = None  # Final result for export

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        scaled_margin = scale_px(8)
        layout.setContentsMargins(scaled_margin, scaled_margin, scaled_margin, scaled_margin)
        layout.setSpacing(scale_px(8))

        # Main splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel: Checkpoint browser and controls
        left_panel = self._create_left_panel()
        splitter.addWidget(left_panel)

        # Right panel: Progress and results
        right_panel = self._create_right_panel()
        splitter.addWidget(right_panel)

        # Set initial splitter sizes (40% left, 60% right)
        splitter.setSizes([scale_px(400), scale_px(600)])

        layout.addWidget(splitter)

    def _create_left_panel(self) -> QWidget:
        """Create the left panel with checkpoint browser and controls."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(scale_px(8))

        # Tab widget for New Review vs Resume
        tab_widget = QTabWidget()

        # New Review Tab
        new_review_widget = self._create_new_review_widget()
        tab_widget.addTab(new_review_widget, "New Review")

        # Resume Tab
        resume_widget = self._create_resume_widget()
        tab_widget.addTab(resume_widget, "Resume from Checkpoint")

        layout.addWidget(tab_widget)

        # Parameters section (shared)
        params_group = self._create_parameters_widget()
        layout.addWidget(params_group)

        return panel

    def _create_new_review_widget(self) -> QWidget:
        """Create the new review input widget."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(scale_px(6))

        # Research question
        layout.addWidget(QLabel("Research Question:"))
        self.research_question_edit = QTextEdit()
        self.research_question_edit.setPlaceholderText(
            "Enter your research question...\n"
            "e.g., What is the efficacy of metformin for type 2 diabetes?"
        )
        self.research_question_edit.setMaximumHeight(scale_px(100))
        layout.addWidget(self.research_question_edit)

        # Purpose
        form_layout = QFormLayout()

        self.purpose_edit = QLineEdit()
        self.purpose_edit.setPlaceholderText("e.g., Clinical guideline development")
        form_layout.addRow("Purpose:", self.purpose_edit)

        layout.addLayout(form_layout)

        # Inclusion criteria - pre-populated with defaults
        layout.addWidget(QLabel("Inclusion Criteria (one per line):"))
        self.inclusion_edit = QPlainTextEdit()
        self.inclusion_edit.setPlainText("\n".join(DEFAULT_INCLUSION_CRITERIA))
        self.inclusion_edit.setMaximumHeight(scale_px(80))
        layout.addWidget(self.inclusion_edit)

        # Exclusion criteria - pre-populated with defaults
        layout.addWidget(QLabel("Exclusion Criteria (one per line):"))
        self.exclusion_edit = QPlainTextEdit()
        self.exclusion_edit.setPlainText("\n".join(DEFAULT_EXCLUSION_CRITERIA))
        self.exclusion_edit.setMaximumHeight(scale_px(80))
        layout.addWidget(self.exclusion_edit)

        # Output directory
        output_layout = QHBoxLayout()
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setText(str(self._review_directory))
        self.output_dir_edit.setReadOnly(True)
        output_layout.addWidget(self.output_dir_edit)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_output_directory)
        output_layout.addWidget(browse_btn)

        form_layout2 = QFormLayout()
        form_layout2.addRow("Output Directory:", output_layout)
        layout.addLayout(form_layout2)

        # Start button
        self.start_new_btn = QPushButton("Start New Review")
        self.start_new_btn.setObjectName("primary_button")
        self.start_new_btn.clicked.connect(self._start_new_review)
        layout.addWidget(self.start_new_btn)

        layout.addStretch()

        return widget

    def _create_resume_widget(self) -> QWidget:
        """Create the checkpoint resume widget."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(scale_px(6))

        # Directory selection
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(QLabel("Review Directory:"))

        self.review_dir_edit = QLineEdit()
        self.review_dir_edit.setText(str(self._review_directory))
        dir_layout.addWidget(self.review_dir_edit)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_review_directory)
        dir_layout.addWidget(browse_btn)

        layout.addLayout(dir_layout)

        refresh_btn = QPushButton("Refresh Checkpoints")
        refresh_btn.clicked.connect(self.refresh_checkpoints)
        layout.addWidget(refresh_btn)

        # Checkpoint list
        layout.addWidget(QLabel("Available Checkpoints:"))

        self.checkpoint_list = QListWidget()
        self.checkpoint_list.currentItemChanged.connect(self._on_checkpoint_selected)
        layout.addWidget(self.checkpoint_list)

        # Checkpoint details
        details_group = QGroupBox("Checkpoint Details")
        details_layout = QVBoxLayout(details_group)

        self.checkpoint_details_label = QLabel("Select a checkpoint to view details")
        self.checkpoint_details_label.setWordWrap(True)
        details_layout.addWidget(self.checkpoint_details_label)

        layout.addWidget(details_group)

        # Resume button
        self.resume_btn = QPushButton("Resume from Selected Checkpoint")
        self.resume_btn.setObjectName("primary_button")
        self.resume_btn.setEnabled(False)
        self.resume_btn.clicked.connect(self._resume_from_checkpoint)
        layout.addWidget(self.resume_btn)

        layout.addStretch()

        return widget

    def _create_parameters_widget(self) -> QGroupBox:
        """Create the parameters adjustment widget."""
        group = QGroupBox("Parameters (Adjustable Before Resume)")
        layout = QFormLayout(group)

        # Relevance threshold (1-5 scale as per agent scoring)
        self.relevance_threshold_spin = QDoubleSpinBox()
        self.relevance_threshold_spin.setRange(1.0, 5.0)
        self.relevance_threshold_spin.setSingleStep(0.5)
        self.relevance_threshold_spin.setValue(DEFAULT_RELEVANCE_THRESHOLD)
        self.relevance_threshold_spin.setToolTip(
            "Minimum relevance score (1-5) for papers to be included"
        )
        layout.addRow("Relevance Threshold:", self.relevance_threshold_spin)

        # Quality threshold (0-10 scale)
        self.quality_threshold_spin = QDoubleSpinBox()
        self.quality_threshold_spin.setRange(0.0, 10.0)
        self.quality_threshold_spin.setSingleStep(0.5)
        self.quality_threshold_spin.setValue(DEFAULT_QUALITY_THRESHOLD)
        self.quality_threshold_spin.setToolTip(
            "Minimum quality score (0-10) for final inclusion"
        )
        layout.addRow("Quality Threshold:", self.quality_threshold_spin)

        # Max results per query
        self.max_results_spin = QSpinBox()
        self.max_results_spin.setRange(10, 1000)
        self.max_results_spin.setSingleStep(50)
        self.max_results_spin.setValue(100)
        self.max_results_spin.setToolTip(
            "Maximum documents to retrieve per search query"
        )
        layout.addRow("Max Results per Query:", self.max_results_spin)

        return group

    def _create_right_panel(self) -> QWidget:
        """
        Create the right panel with tabbed interface.

        Contains three tabs:
        - Results: Progress bars and activity log
        - Details: JSON structure viewer
        - Report: Formatted markdown report
        """
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(scale_px(8))

        # Tab widget for Results, Details, Report
        self.right_tab_widget = QTabWidget()

        # Tab 1: Results (progress + activity log)
        results_tab = self._create_results_tab()
        self.right_tab_widget.addTab(results_tab, "Results")

        # Tab 2: Details (JSON viewer)
        details_tab = self._create_details_tab()
        self.right_tab_widget.addTab(details_tab, "Details")

        # Tab 3: Report (markdown viewer)
        report_tab = self._create_report_tab()
        self.right_tab_widget.addTab(report_tab, "Report")

        layout.addWidget(self.right_tab_widget)

        return panel

    def _create_results_tab(self) -> QWidget:
        """
        Create the Results tab with progress tracking and activity log.

        Contains:
        - Progress section at top with step-specific progress
        - Scrollable markdown activity log below
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(scale_px(8))

        # Progress section
        progress_group = QGroupBox("Progress")
        progress_layout = QVBoxLayout(progress_group)

        # Status label
        self.status_label = QLabel("Ready to start")
        progress_layout.addWidget(self.status_label)

        # Overall progress bar
        overall_label = QLabel("Overall Progress:")
        progress_layout.addWidget(overall_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)

        # Step-specific progress bar
        self.step_label = QLabel("Current Step:")
        progress_layout.addWidget(self.step_label)

        self.step_progress_bar = QProgressBar()
        self.step_progress_bar.setRange(0, 100)
        self.step_progress_bar.setValue(0)
        self.step_progress_bar.setFormat("%v / %m")
        progress_layout.addWidget(self.step_progress_bar)

        # Cancel button
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel_review)
        button_layout.addWidget(self.cancel_btn)

        progress_layout.addLayout(button_layout)

        layout.addWidget(progress_group)

        # Activity log section
        activity_group = QGroupBox("Activity Log")
        activity_layout = QVBoxLayout(activity_group)

        self.activity_viewer = MarkdownViewer()
        self.activity_viewer.set_markdown(
            "*Waiting to start...*\n\n"
            "Activity will be logged here as the review progresses."
        )
        activity_layout.addWidget(self.activity_viewer)

        layout.addWidget(activity_group, stretch=1)

        return widget

    def _create_details_tab(self) -> QWidget:
        """
        Create the Details tab with JSON structure viewer.

        Displays the accumulated state as pretty-printed JSON that
        builds up as the review progresses.
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(scale_px(8))

        # JSON viewer
        details_group = QGroupBox("Review State (JSON)")
        details_layout = QVBoxLayout(details_group)

        self.details_text = QPlainTextEdit()
        self.details_text.setReadOnly(True)
        self.details_text.setPlaceholderText(
            "JSON state will appear here as the review progresses..."
        )

        # Apply monospace font styling using stylesheet generator
        style_gen = StylesheetGenerator()
        self.details_text.setStyleSheet(style_gen.code_text_stylesheet())

        details_layout.addWidget(self.details_text)

        layout.addWidget(details_group, stretch=1)

        return widget

    def _create_report_tab(self) -> QWidget:
        """
        Create the Report tab with markdown viewer and export buttons.

        Displays the final formatted markdown report with export options.
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(scale_px(8))

        # Report viewer using ReportPreviewWidget for rich display and export
        self.report_preview = ReportPreviewWidget()
        layout.addWidget(self.report_preview, stretch=1)

        # Export buttons
        export_layout = QHBoxLayout()

        self.export_json_btn = QPushButton("Export JSON")
        self.export_json_btn.setEnabled(False)
        self.export_json_btn.clicked.connect(self._export_json)
        export_layout.addWidget(self.export_json_btn)

        self.export_md_btn = QPushButton("Export Markdown")
        self.export_md_btn.setEnabled(False)
        self.export_md_btn.clicked.connect(self._export_markdown)
        export_layout.addWidget(self.export_md_btn)

        export_layout.addStretch()

        layout.addLayout(export_layout)

        return widget

    def _connect_signals(self) -> None:
        """Connect internal signals."""
        pass  # Signals connected in individual methods

    # =========================================================================
    # Checkpoint Management
    # =========================================================================

    def refresh_checkpoints(self) -> None:
        """Refresh the list of available checkpoints."""
        self.checkpoint_list.clear()
        self.checkpoint_details_label.setText("Select a checkpoint to view details")
        self.resume_btn.setEnabled(False)

        review_dir = Path(self.review_dir_edit.text())
        checkpoint_dir = review_dir / "checkpoints"

        if not checkpoint_dir.exists():
            self.status_message.emit("No checkpoints directory found")
            return

        checkpoints = list(checkpoint_dir.glob("*.json"))

        if not checkpoints:
            self.status_message.emit("No checkpoints found")
            return

        # Sort by modification time (newest first)
        checkpoints.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        for checkpoint_path in checkpoints:
            try:
                with open(checkpoint_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                checkpoint_type = data.get("checkpoint_type")

                # Skip files that aren't valid checkpoint files
                # (e.g., final report JSONs, PRISMA files, etc.)
                if checkpoint_type not in CHECKPOINT_TYPES:
                    logger.debug(
                        f"Skipping non-checkpoint file: {checkpoint_path.name} "
                        f"(type: {checkpoint_type})"
                    )
                    continue

                timestamp = data.get("timestamp", "unknown")
                review_id = data.get("review_id", "unknown")[:8]

                display_name = CHECKPOINT_TYPE_DISPLAY_NAMES.get(
                    checkpoint_type, checkpoint_type
                )

                # Format timestamp
                try:
                    dt = datetime.fromisoformat(timestamp)
                    time_str = dt.strftime("%Y-%m-%d %H:%M")
                except (ValueError, TypeError):
                    time_str = timestamp

                item = QListWidgetItem(f"{display_name} - {time_str} [{review_id}]")
                item.setData(Qt.ItemDataRole.UserRole, str(checkpoint_path))
                item.setData(Qt.ItemDataRole.UserRole + 1, data)

                self.checkpoint_list.addItem(item)

            except Exception as e:
                logger.warning(f"Error loading checkpoint {checkpoint_path}: {e}")

        self.status_message.emit(f"Found {self.checkpoint_list.count()} checkpoints")

    def _on_checkpoint_selected(
        self,
        current: Optional[QListWidgetItem],
        previous: Optional[QListWidgetItem],
    ) -> None:
        """Handle checkpoint selection."""
        if current is None:
            self.checkpoint_details_label.setText("Select a checkpoint to view details")
            self.resume_btn.setEnabled(False)
            self._current_checkpoint_path = None
            return

        checkpoint_path = current.data(Qt.ItemDataRole.UserRole)
        checkpoint_data = current.data(Qt.ItemDataRole.UserRole + 1)

        self._current_checkpoint_path = checkpoint_path

        # Build details text
        details = []
        details.append(f"<b>Review ID:</b> {checkpoint_data.get('review_id', 'N/A')}")
        details.append(f"<b>Checkpoint:</b> {checkpoint_data.get('checkpoint_type', 'N/A')}")
        details.append(f"<b>Timestamp:</b> {checkpoint_data.get('timestamp', 'N/A')}")

        # Paper counts
        paper_count = checkpoint_data.get("paper_count", 0)
        scored_count = len(checkpoint_data.get("scored_paper_ids", []))
        details.append(f"<b>Papers Found:</b> {paper_count}")
        if scored_count > 0:
            details.append(f"<b>Papers Scored:</b> {scored_count}")

        # Criteria summary
        criteria = checkpoint_data.get("criteria", {})
        if criteria:
            question = criteria.get("research_question", "")[:100]
            if len(criteria.get("research_question", "")) > 100:
                question += "..."
            details.append(f"<b>Research Question:</b> {question}")

        self.checkpoint_details_label.setText("<br>".join(details))
        self.resume_btn.setEnabled(True)

    # =========================================================================
    # Review Execution
    # =========================================================================

    def _get_config_overrides(self) -> Dict[str, Any]:
        """Get current parameter values as config overrides."""
        return {
            "relevance_threshold": self.relevance_threshold_spin.value(),
            "quality_threshold": self.quality_threshold_spin.value(),
            "max_results_per_query": self.max_results_spin.value(),
        }

    def _start_new_review(self) -> None:
        """Start a new systematic review."""
        # Validate inputs
        research_question = self.research_question_edit.toPlainText().strip()
        if not research_question:
            QMessageBox.warning(
                self,
                "Missing Input",
                "Please enter a research question.",
            )
            return

        # Build criteria dictionary
        inclusion_text = self.inclusion_edit.toPlainText().strip()
        inclusion_criteria = [
            line.strip()
            for line in inclusion_text.split("\n")
            if line.strip()
        ]

        exclusion_text = self.exclusion_edit.toPlainText().strip()
        exclusion_criteria = [
            line.strip()
            for line in exclusion_text.split("\n")
            if line.strip()
        ]

        criteria_dict = {
            "research_question": research_question,
            "purpose": self.purpose_edit.text() or "Systematic literature review",
            "inclusion_criteria": inclusion_criteria or ["Relevant to research question"],
            "exclusion_criteria": exclusion_criteria or [],
        }

        # Set up output path
        output_dir = Path(self.output_dir_edit.text())
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = str(output_dir / f"systematic_review_{timestamp}.json")

        # Start worker
        self._start_worker(
            mode="new",
            criteria_dict=criteria_dict,
            output_path=output_path,
        )

    def _resume_from_checkpoint(self) -> None:
        """Resume from selected checkpoint."""
        if not self._current_checkpoint_path:
            QMessageBox.warning(
                self,
                "No Checkpoint Selected",
                "Please select a checkpoint to resume from.",
            )
            return

        # Get output path from checkpoint directory
        checkpoint_path = Path(self._current_checkpoint_path)
        output_dir = checkpoint_path.parent.parent  # checkpoints/.. = review_dir
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = str(output_dir / f"systematic_review_resumed_{timestamp}.json")

        # Start worker
        self._start_worker(
            mode="resume",
            checkpoint_path=self._current_checkpoint_path,
            output_path=output_path,
        )

    def _start_worker(
        self,
        mode: str,
        checkpoint_path: Optional[str] = None,
        criteria_dict: Optional[Dict[str, Any]] = None,
        output_path: Optional[str] = None,
    ) -> None:
        """Start the review worker thread."""
        # Disable UI elements
        self.start_new_btn.setEnabled(False)
        self.resume_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.export_json_btn.setEnabled(False)
        self.export_md_btn.setEnabled(False)

        # Reset state tracking
        self._activity_log = ""
        self._accumulated_state = {}
        self._report_content = ""

        # Reset progress bars
        self.progress_bar.setValue(0)
        self.step_progress_bar.setValue(0)
        self.step_progress_bar.setRange(0, 100)
        self.step_label.setText("Current Step:")
        self.status_label.setText("Initializing...")

        # Reset activity log
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        initial_log = f"# Systematic Review Started\n\n**Started at:** {timestamp}\n\n---\n\n"
        self._activity_log = initial_log
        self.activity_viewer.set_markdown(initial_log)

        # Reset details view
        self.details_text.clear()

        # Reset report view
        self.report_preview.set_report(
            "# Report\n\n"
            "*Processing... The report will appear here when the review completes.*"
        )

        # Switch to Results tab
        self.right_tab_widget.setCurrentIndex(0)

        # Create and start worker
        db_manager = get_db_manager()
        self._worker = ReviewWorker(
            db_manager=db_manager,
            mode=mode,
            checkpoint_path=checkpoint_path,
            criteria_dict=criteria_dict,
            config_overrides=self._get_config_overrides(),
            output_path=output_path,
        )

        # Connect all signals
        self._worker.progress_update.connect(self._on_progress_update)
        self._worker.step_progress.connect(self._on_step_progress)
        self._worker.activity_update.connect(self._on_activity_update)
        self._worker.state_update.connect(self._on_state_update)
        self._worker.checkpoint_reached.connect(self._on_checkpoint_reached)
        self._worker.step_completed.connect(self._on_step_completed)
        self._worker.review_complete.connect(self._on_review_complete)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.finished.connect(self._on_worker_finished)

        self._worker.start()

    def _cancel_review(self) -> None:
        """Cancel the running review."""
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self.status_label.setText("Cancelling...")

    @Slot(str, int)
    def _on_progress_update(self, message: str, percentage: int) -> None:
        """Handle progress update from worker."""
        self.status_label.setText(message)
        self.progress_bar.setValue(percentage)
        self.status_message.emit(message)

    @Slot(str, int, int)
    def _on_step_progress(self, step_name: str, current: int, total: int) -> None:
        """
        Handle step-specific progress updates.

        Updates the step progress bar with current/total values.

        Args:
            step_name: Name of the current step
            current: Current progress count
            total: Total count for this step
        """
        self.step_label.setText(f"Current Step: {step_name}")
        self.step_progress_bar.setRange(0, total)
        self.step_progress_bar.setValue(current)

    @Slot(str)
    def _on_activity_update(self, entry: str) -> None:
        """
        Handle activity log updates.

        Appends the new entry to the activity log and updates the viewer.

        Args:
            entry: Markdown-formatted activity log entry
        """
        self._activity_log += entry
        self.activity_viewer.set_markdown(self._activity_log)

    @Slot(dict)
    def _on_state_update(self, state: Dict) -> None:
        """
        Handle accumulated state updates.

        Updates the Details tab with pretty-printed JSON.

        Args:
            state: Current accumulated state dictionary
        """
        self._accumulated_state = state
        formatted_json = json.dumps(state, indent=2, ensure_ascii=False, default=str)
        self.details_text.setPlainText(formatted_json)

    @Slot(str, dict)
    def _on_checkpoint_reached(self, checkpoint_type: str, state: Dict) -> None:
        """
        Handle checkpoint reached signal.

        Adds a checkpoint entry to the activity log.

        Args:
            checkpoint_type: Type of checkpoint reached
            state: Checkpoint state dictionary
        """
        display_name = CHECKPOINT_TYPE_DISPLAY_NAMES.get(
            checkpoint_type, checkpoint_type
        )
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"**[{timestamp}]** ✅ **Checkpoint:** {display_name}\n\n"
        self._activity_log += entry
        self.activity_viewer.set_markdown(self._activity_log)
        self.status_message.emit(f"Checkpoint: {display_name}")

    @Slot(str, dict)
    def _on_step_completed(self, step_name: str, metrics: Dict) -> None:
        """
        Handle step completed signal.

        Adds step completion to the activity log with metrics.

        Args:
            step_name: Name of the completed step
            metrics: Step completion metrics
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        metrics_str = ", ".join(f"{k}: {v}" for k, v in metrics.items()) if metrics else "completed"
        entry = f"**[{timestamp}]** Step completed: {step_name} ({metrics_str})\n"
        self._activity_log += entry
        self.activity_viewer.set_markdown(self._activity_log)

    @Slot(dict)
    def _on_review_complete(self, result: Dict) -> None:
        """
        Handle review completion.

        Updates all three tabs with final results:
        - Results: Final summary in activity log
        - Details: Complete result JSON
        - Report: Formatted markdown report
        """
        self.progress_bar.setValue(100)
        self.step_progress_bar.setValue(self.step_progress_bar.maximum())
        self.status_label.setText("Review complete!")

        # Store result for export
        self._last_result = result

        # Update activity log with summary
        stats = result.get("statistics", {})
        timestamp = datetime.now().strftime("%H:%M:%S")
        summary_entry = f"""
---

## ✅ Review Complete ({timestamp})

| Metric | Count |
|--------|-------|
| Total Considered | {stats.get('total_considered', 0)} |
| Passed Initial Filter | {stats.get('passed_initial_filter', 0)} |
| Passed Relevance | {stats.get('passed_relevance_threshold', 0)} |
| Passed Quality | {stats.get('passed_quality_gate', 0)} |
| **Final Included** | **{stats.get('final_included', 0)}** |
| Final Excluded | {stats.get('final_excluded', 0)} |
| Uncertain (Need Review) | {stats.get('uncertain_for_review', 0)} |

**Processing Time:** {stats.get('processing_time_seconds', 0):.1f} seconds
"""
        self._activity_log += summary_entry
        self.activity_viewer.set_markdown(self._activity_log)

        # Update details with complete result
        formatted_json = json.dumps(result, indent=2, ensure_ascii=False, default=str)
        self.details_text.setPlainText(formatted_json)

        # Update report preview widget with results
        self.report_preview.set_report_from_result(result)

        # Enable export buttons
        self.export_json_btn.setEnabled(True)
        self.export_md_btn.setEnabled(True)

        # Switch to Report tab
        self.right_tab_widget.setCurrentIndex(2)

        self.status_message.emit("Review complete!")
        self.refresh_checkpoints()  # Refresh to show new checkpoints

    @Slot(str)
    def _on_error(self, error_message: str) -> None:
        """Handle error from worker."""
        self.status_label.setText(f"Error: {error_message}")
        self.status_message.emit(f"Error: {error_message}")

        QMessageBox.critical(
            self,
            "Review Error",
            f"An error occurred during the review:\n\n{error_message}",
        )

    @Slot()
    def _on_worker_finished(self) -> None:
        """Handle worker thread completion."""
        self.start_new_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

        if self.checkpoint_list.currentItem():
            self.resume_btn.setEnabled(True)

        self._worker = None

    # =========================================================================
    # Export and File Operations
    # =========================================================================

    def _browse_output_directory(self) -> None:
        """Browse for output directory."""
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Output Directory",
            self.output_dir_edit.text(),
        )
        if directory:
            self.output_dir_edit.setText(directory)
            self._review_directory = Path(directory)

    def _browse_review_directory(self) -> None:
        """Browse for review directory containing checkpoints."""
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Review Directory",
            self.review_dir_edit.text(),
        )
        if directory:
            self.review_dir_edit.setText(directory)
            self.output_dir_edit.setText(directory)
            self._review_directory = Path(directory)
            self.refresh_checkpoints()

    def _export_json(self) -> None:
        """Export results to JSON."""
        if not hasattr(self, '_last_result'):
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export JSON",
            str(self._review_directory / "export.json"),
            "JSON Files (*.json)",
        )

        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(self._last_result, f, indent=2, ensure_ascii=False)
                self.status_message.emit(f"Exported to {file_path}")
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Export Error",
                    f"Failed to export: {e}",
                )

    def _export_markdown(self) -> None:
        """Export results to Markdown."""
        if not hasattr(self, '_last_result') or self._last_result is None:
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Markdown",
            str(self._review_directory / "export.md"),
            "Markdown Files (*.md)",
        )

        if file_path:
            try:
                from bmlibrarian.agents.systematic_review.reporter import Reporter
                from bmlibrarian.agents.systematic_review.data_models import (
                    SystematicReviewResult,
                )

                # Convert dict back to SystematicReviewResult for proper formatting
                result = SystematicReviewResult.from_dict(self._last_result)

                # Create reporter and generate full markdown report
                reporter = Reporter(documenter=None, criteria=None, weights=None)
                reporter.generate_markdown_report(result, file_path)

                self.status_message.emit(f"Exported to {file_path}")
            except Exception as e:
                logger.error(f"Failed to export markdown: {e}", exc_info=True)
                QMessageBox.critical(
                    self,
                    "Export Error",
                    f"Failed to export: {e}",
                )

    def cleanup(self) -> None:
        """Cleanup resources."""
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(WORKER_CLEANUP_TIMEOUT_MS)
