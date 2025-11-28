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
from bmlibrarian.gui.qt.resources.styles.dpi_scale import get_font_scale, scale_px
from bmlibrarian.agents.systematic_review.config import DEFAULT_OUTPUT_DIR

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
    checkpoint_reached = Signal(str, dict)  # (checkpoint_type, state)
    step_completed = Signal(str, dict)  # (step_name, metrics)
    review_complete = Signal(dict)  # result data
    error_occurred = Signal(str)  # error message

    def __init__(
        self,
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
            mode: "new" for new review, "resume" for checkpoint resume
            checkpoint_path: Path to checkpoint file (for resume)
            criteria_dict: Search criteria dictionary (for new review)
            weights_dict: Scoring weights dictionary
            config_overrides: Configuration overrides (thresholds, etc.)
            output_path: Path to save output files
        """
        super().__init__()
        self.mode = mode
        self.checkpoint_path = checkpoint_path
        self.criteria_dict = criteria_dict
        self.weights_dict = weights_dict
        self.config_overrides = config_overrides or {}
        self.output_path = output_path
        self._cancelled = False

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
        """Handle progress callbacks from the agent."""
        if self._cancelled:
            return

        # Parse event type to estimate progress
        progress_map = {
            "execution_started": 15,
            "query_started": 20,
            "query_completed": 30,
            "execution_completed": 40,
            "filtering_started": 45,
            "filtering_complete": 50,
            "scoring_started": 55,
            "scoring_complete": 70,
            "quality_started": 75,
            "quality_complete": 85,
            "reporting_started": 90,
            "reporting_complete": 95,
        }

        percentage = progress_map.get(event, 50)
        self.progress_update.emit(f"{event}: {data}", percentage)


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

        # Inclusion criteria
        layout.addWidget(QLabel("Inclusion Criteria (one per line):"))
        self.inclusion_edit = QPlainTextEdit()
        self.inclusion_edit.setPlaceholderText(
            "Human studies\n"
            "Randomized controlled trials\n"
            "Published after 2015"
        )
        self.inclusion_edit.setMaximumHeight(scale_px(80))
        layout.addWidget(self.inclusion_edit)

        # Exclusion criteria
        layout.addWidget(QLabel("Exclusion Criteria (one per line):"))
        self.exclusion_edit = QPlainTextEdit()
        self.exclusion_edit.setPlaceholderText(
            "Animal studies\n"
            "Case reports\n"
            "Non-English language"
        )
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

        # Relevance threshold
        self.relevance_threshold_spin = QDoubleSpinBox()
        self.relevance_threshold_spin.setRange(0.0, 10.0)
        self.relevance_threshold_spin.setSingleStep(0.5)
        self.relevance_threshold_spin.setValue(3.0)
        self.relevance_threshold_spin.setToolTip(
            "Minimum relevance score for papers to be included"
        )
        layout.addRow("Relevance Threshold:", self.relevance_threshold_spin)

        # Quality threshold
        self.quality_threshold_spin = QDoubleSpinBox()
        self.quality_threshold_spin.setRange(0.0, 10.0)
        self.quality_threshold_spin.setSingleStep(0.5)
        self.quality_threshold_spin.setValue(5.0)
        self.quality_threshold_spin.setToolTip(
            "Minimum quality score for final inclusion"
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
        """Create the right panel with progress and results."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(scale_px(8))

        # Progress section
        progress_group = QGroupBox("Progress")
        progress_layout = QVBoxLayout(progress_group)

        # Status label
        self.status_label = QLabel("Ready to start")
        progress_layout.addWidget(self.status_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)

        # Cancel button
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel_review)
        button_layout.addWidget(self.cancel_btn)

        progress_layout.addLayout(button_layout)

        layout.addWidget(progress_group)

        # Workflow steps display
        steps_group = QGroupBox("Workflow Steps")
        steps_layout = QVBoxLayout(steps_group)

        self.steps_list = QListWidget()
        steps_layout.addWidget(self.steps_list)

        layout.addWidget(steps_group)

        # Results summary
        results_group = QGroupBox("Results Summary")
        results_layout = QVBoxLayout(results_group)

        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setPlaceholderText(
            "Results will be displayed here after the review completes..."
        )
        results_layout.addWidget(self.results_text)

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

        results_layout.addLayout(export_layout)

        layout.addWidget(results_group)

        return panel

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

        # Clear previous results
        self.steps_list.clear()
        self.results_text.clear()
        self.progress_bar.setValue(0)
        self.status_label.setText("Initializing...")

        # Create and start worker
        self._worker = ReviewWorker(
            mode=mode,
            checkpoint_path=checkpoint_path,
            criteria_dict=criteria_dict,
            config_overrides=self._get_config_overrides(),
            output_path=output_path,
        )

        self._worker.progress_update.connect(self._on_progress_update)
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

    @Slot(str, dict)
    def _on_checkpoint_reached(self, checkpoint_type: str, state: Dict) -> None:
        """Handle checkpoint reached signal."""
        display_name = CHECKPOINT_TYPE_DISPLAY_NAMES.get(
            checkpoint_type, checkpoint_type
        )
        self.steps_list.addItem(f"✓ {display_name}")
        self.status_message.emit(f"Checkpoint: {display_name}")

    @Slot(str, dict)
    def _on_step_completed(self, step_name: str, metrics: Dict) -> None:
        """Handle step completed signal."""
        self.steps_list.addItem(f"  - {step_name}")

    @Slot(dict)
    def _on_review_complete(self, result: Dict) -> None:
        """Handle review completion."""
        self.progress_bar.setValue(100)
        self.status_label.setText("Review complete!")

        # Display results summary
        stats = result.get("statistics", {})
        summary_lines = [
            "<h3>Review Complete</h3>",
            f"<b>Total Considered:</b> {stats.get('total_considered', 0)}",
            f"<b>Passed Initial Filter:</b> {stats.get('passed_initial_filter', 0)}",
            f"<b>Passed Relevance:</b> {stats.get('passed_relevance_threshold', 0)}",
            f"<b>Passed Quality:</b> {stats.get('passed_quality_gate', 0)}",
            f"<b>Final Included:</b> {stats.get('final_included', 0)}",
            f"<b>Final Excluded:</b> {stats.get('final_excluded', 0)}",
            f"<b>Uncertain (Need Review):</b> {stats.get('uncertain_for_review', 0)}",
            "",
            f"<b>Processing Time:</b> {stats.get('processing_time_seconds', 0):.1f} seconds",
        ]

        self.results_text.setHtml("<br>".join(summary_lines))
        self.export_json_btn.setEnabled(True)
        self.export_md_btn.setEnabled(True)

        # Store result for export
        self._last_result = result

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
        if not hasattr(self, '_last_result'):
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

                # Note: This is a simplified export - full implementation would
                # use Reporter.generate_markdown_report()
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(f"# Systematic Review Results\n\n")
                    stats = self._last_result.get("statistics", {})
                    f.write(f"## Summary\n\n")
                    f.write(f"- Total Considered: {stats.get('total_considered', 0)}\n")
                    f.write(f"- Final Included: {stats.get('final_included', 0)}\n")
                    f.write(f"- Final Excluded: {stats.get('final_excluded', 0)}\n")

                self.status_message.emit(f"Exported to {file_path}")
            except Exception as e:
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
