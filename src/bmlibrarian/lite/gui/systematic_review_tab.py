"""
Systematic Review tab for BMLibrarian Lite.

Provides a complete workflow for literature review:
1. Enter research question
2. Search PubMed
3. Score documents for relevance
4. Extract citations
5. Generate report
"""

import logging
from typing import Optional, List, Any

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QPushButton,
    QLabel,
    QProgressBar,
    QGroupBox,
    QSpinBox,
    QFileDialog,
)
from PySide6.QtCore import Signal, QThread

from bmlibrarian.gui.qt.resources.dpi_scale import scaled

from ..config import LiteConfig
from ..storage import LiteStorage
from ..data_models import LiteDocument, ScoredDocument, Citation
from ..agents import (
    LiteSearchAgent,
    LiteScoringAgent,
    LiteCitationAgent,
    LiteReportingAgent,
)

logger = logging.getLogger(__name__)


class WorkflowWorker(QThread):
    """
    Background worker for systematic review workflow.

    Executes the full workflow in a background thread:
    1. Search PubMed
    2. Score documents
    3. Extract citations
    4. Generate report

    Signals:
        progress: Emitted during progress (step, current, total)
        step_complete: Emitted when a step completes (step name, result)
        error: Emitted on error (step, error message)
        finished: Emitted when workflow completes (final report)
    """

    progress = Signal(str, int, int)  # step, current, total
    step_complete = Signal(str, object)  # step name, result
    error = Signal(str, str)  # step, error message
    finished = Signal(str)  # final report

    def __init__(
        self,
        question: str,
        config: LiteConfig,
        storage: LiteStorage,
        max_results: int = 100,
        min_score: int = 3,
    ) -> None:
        """
        Initialize the workflow worker.

        Args:
            question: Research question
            config: Lite configuration
            storage: Storage layer
            max_results: Maximum PubMed results to fetch
            min_score: Minimum relevance score (1-5)
        """
        super().__init__()
        self.question = question
        self.config = config
        self.storage = storage
        self.max_results = max_results
        self.min_score = min_score
        self._cancelled = False

    def run(self) -> None:
        """Execute the systematic review workflow."""
        try:
            # Step 1: Search PubMed
            self.progress.emit("search", 0, 1)
            search_agent = LiteSearchAgent(
                config=self.config,
                storage=self.storage,
            )
            session, documents = search_agent.search(
                self.question,
                max_results=self.max_results,
            )
            self.step_complete.emit("search", documents)

            if self._cancelled:
                self.finished.emit("Workflow cancelled.")
                return

            if not documents:
                self.finished.emit("No documents found for this query.")
                return

            # Step 2: Score documents
            scoring_agent = LiteScoringAgent(config=self.config)
            scored_docs = scoring_agent.score_documents(
                self.question,
                documents,
                min_score=self.min_score,
                progress_callback=lambda c, t: self.progress.emit("scoring", c, t),
            )
            self.step_complete.emit("scoring", scored_docs)

            if self._cancelled:
                self.finished.emit("Workflow cancelled.")
                return

            if not scored_docs:
                self.finished.emit(
                    f"No documents scored {self.min_score} or higher. "
                    "Try lowering the minimum score threshold."
                )
                return

            # Step 3: Extract citations
            citation_agent = LiteCitationAgent(config=self.config)
            citations = citation_agent.extract_all_citations(
                self.question,
                scored_docs,
                min_score=self.min_score,
                progress_callback=lambda c, t: self.progress.emit("citations", c, t),
            )
            self.step_complete.emit("citations", citations)

            if self._cancelled:
                self.finished.emit("Workflow cancelled.")
                return

            # Step 4: Generate report
            self.progress.emit("report", 0, 1)
            reporting_agent = LiteReportingAgent(config=self.config)
            report = reporting_agent.generate_report(self.question, citations)
            self.step_complete.emit("report", report)

            self.finished.emit(report)

        except Exception as e:
            logger.exception("Workflow error")
            self.error.emit("workflow", str(e))

    def cancel(self) -> None:
        """Cancel the workflow."""
        self._cancelled = True


class SystematicReviewTab(QWidget):
    """
    Systematic Review tab widget.

    Provides interface for:
    - Entering research question
    - Configuring search parameters
    - Executing search and scoring workflow
    - Viewing generated report
    - Exporting report

    Attributes:
        config: Lite configuration
        storage: Storage layer
    """

    def __init__(
        self,
        config: LiteConfig,
        storage: LiteStorage,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Initialize the systematic review tab.

        Args:
            config: Lite configuration
            storage: Storage layer
            parent: Optional parent widget
        """
        super().__init__(parent)
        self.config = config
        self.storage = storage
        self._worker: Optional[WorkflowWorker] = None
        self._current_report: str = ""

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        layout.setSpacing(scaled(8))

        # Question input section
        question_group = QGroupBox("Research Question")
        question_layout = QVBoxLayout(question_group)

        self.question_input = QTextEdit()
        self.question_input.setPlaceholderText(
            "Enter your research question...\n\n"
            "Example: What are the cardiovascular benefits of regular exercise "
            "in adults over 50?"
        )
        self.question_input.setMaximumHeight(scaled(100))
        question_layout.addWidget(self.question_input)

        # Options row
        options_layout = QHBoxLayout()

        options_layout.addWidget(QLabel("Max results:"))
        self.max_results_spin = QSpinBox()
        self.max_results_spin.setRange(10, 500)
        self.max_results_spin.setValue(100)
        self.max_results_spin.setToolTip("Maximum number of PubMed articles to retrieve")
        options_layout.addWidget(self.max_results_spin)

        options_layout.addSpacing(scaled(16))

        options_layout.addWidget(QLabel("Min score:"))
        self.min_score_spin = QSpinBox()
        self.min_score_spin.setRange(1, 5)
        self.min_score_spin.setValue(3)
        self.min_score_spin.setToolTip(
            "Minimum relevance score (1-5) to include in report"
        )
        options_layout.addWidget(self.min_score_spin)

        options_layout.addStretch()

        self.run_btn = QPushButton("Run Review")
        self.run_btn.clicked.connect(self._run_workflow)
        self.run_btn.setToolTip("Start the systematic review workflow")
        options_layout.addWidget(self.run_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self._cancel_workflow)
        self.cancel_btn.setEnabled(False)
        options_layout.addWidget(self.cancel_btn)

        question_layout.addLayout(options_layout)
        layout.addWidget(question_group)

        # Progress section
        progress_group = QGroupBox("Progress")
        progress_layout = QVBoxLayout(progress_group)

        self.progress_label = QLabel("Ready")
        progress_layout.addWidget(self.progress_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)

        layout.addWidget(progress_group)

        # Results section
        results_group = QGroupBox("Report")
        results_layout = QVBoxLayout(results_group)

        self.report_view = QTextEdit()
        self.report_view.setReadOnly(True)
        self.report_view.setPlaceholderText(
            "Report will appear here after running the review...\n\n"
            "The workflow will:\n"
            "1. Search PubMed for relevant articles\n"
            "2. Score each document for relevance\n"
            "3. Extract key passages as citations\n"
            "4. Generate a comprehensive report"
        )
        results_layout.addWidget(self.report_view)

        # Export button
        export_layout = QHBoxLayout()
        export_layout.addStretch()

        self.export_btn = QPushButton("Export Report")
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self._export_report)
        self.export_btn.setToolTip("Save report to file")
        export_layout.addWidget(self.export_btn)

        results_layout.addLayout(export_layout)
        layout.addWidget(results_group, stretch=1)

    def _run_workflow(self) -> None:
        """Start the systematic review workflow."""
        question = self.question_input.toPlainText().strip()
        if not question:
            self.progress_label.setText("Please enter a research question")
            return

        # Update UI state
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.export_btn.setEnabled(False)
        self.report_view.clear()
        self.progress_bar.setValue(0)
        self._current_report = ""

        # Create and start worker
        self._worker = WorkflowWorker(
            question=question,
            config=self.config,
            storage=self.storage,
            max_results=self.max_results_spin.value(),
            min_score=self.min_score_spin.value(),
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.step_complete.connect(self._on_step_complete)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _cancel_workflow(self) -> None:
        """Cancel the running workflow."""
        if self._worker:
            self._worker.cancel()
            self.progress_label.setText("Cancelling...")

    def _on_progress(self, step: str, current: int, total: int) -> None:
        """Handle progress updates from worker."""
        step_names = {
            "search": "Searching PubMed",
            "scoring": "Scoring documents",
            "citations": "Extracting citations",
            "report": "Generating report",
        }
        name = step_names.get(step, step)
        self.progress_label.setText(f"{name}: {current}/{total}")

        if total > 0:
            self.progress_bar.setValue(int(current / total * 100))

    def _on_step_complete(self, step: str, result: Any) -> None:
        """Handle step completion from worker."""
        if step == "search":
            docs = result
            self.progress_label.setText(f"Found {len(docs)} documents")
        elif step == "scoring":
            scored = result
            self.progress_label.setText(f"Scored {len(scored)} relevant documents")
        elif step == "citations":
            citations = result
            self.progress_label.setText(f"Extracted {len(citations)} citations")

    def _on_error(self, step: str, message: str) -> None:
        """Handle workflow errors."""
        self.progress_label.setText(f"Error in {step}: {message}")
        self.report_view.setPlainText(f"Error during {step}:\n\n{message}")
        self._reset_ui()

    def _on_finished(self, report: str) -> None:
        """Handle workflow completion."""
        self._current_report = report
        self.report_view.setMarkdown(report)
        self.progress_label.setText("Complete")
        self.progress_bar.setValue(100)
        self.export_btn.setEnabled(bool(report))
        self._reset_ui()

    def _reset_ui(self) -> None:
        """Reset UI to ready state."""
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self._worker = None

    def _export_report(self) -> None:
        """Export the report to a file."""
        if not self._current_report:
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Report",
            "research_report.md",
            "Markdown (*.md);;Text (*.txt);;All Files (*)",
        )

        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(self._current_report)
                self.progress_label.setText(f"Report exported to {file_path}")
            except Exception as e:
                self.progress_label.setText(f"Export failed: {e}")
