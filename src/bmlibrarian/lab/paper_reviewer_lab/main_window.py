"""
Paper Reviewer Lab - Main Window

Main application window coordinating the tabbed interface for paper review.
"""

import logging
import time
from pathlib import Path
from typing import Optional, Dict, Any

from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QVBoxLayout,
    QMessageBox, QApplication,
)
from PySide6.QtCore import Qt

from bmlibrarian.gui.qt.resources.styles.dpi_scale import scaled

from .constants import (
    VERSION,
    WINDOW_MIN_WIDTH_MULTIPLIER,
    WINDOW_MIN_HEIGHT_MULTIPLIER,
    WINDOW_DEFAULT_WIDTH_MULTIPLIER,
    WINDOW_DEFAULT_HEIGHT_MULTIPLIER,
    TAB_INPUT, TAB_WORKFLOW, TAB_RESULTS,
    STATUS_IN_PROGRESS, STATUS_COMPLETED, STATUS_FAILED, STATUS_SKIPPED,
    INPUT_TYPE_DOI, INPUT_TYPE_PMID, INPUT_TYPE_PDF, INPUT_TYPE_TEXT, INPUT_TYPE_FILE,
)
from .worker import ReviewThread
from .tabs import InputPanel, WorkflowPanel, ResultsPanel

logger = logging.getLogger(__name__)


# Application metadata
APP_TITLE = "Paper Reviewer Lab"
APP_SUBTITLE = f"Comprehensive Paper Assessment v{VERSION}"


class PaperReviewerLab(QMainWindow):
    """
    Main window for the Paper Reviewer Laboratory.

    Coordinates the tabbed interface for paper input, workflow
    visualization, and results display.
    """

    def __init__(self) -> None:
        """Initialize the main window."""
        super().__init__()

        self._thread: Optional[ReviewThread] = None
        self._review_start_time: Optional[float] = None

        self._setup_window()
        self._setup_ui()
        self._connect_signals()

    def _setup_window(self) -> None:
        """Configure main window properties."""
        self.setWindowTitle(f"{APP_TITLE} - {APP_SUBTITLE}")
        self.setMinimumSize(
            scaled(WINDOW_MIN_WIDTH_MULTIPLIER),
            scaled(WINDOW_MIN_HEIGHT_MULTIPLIER)
        )
        self.resize(
            scaled(WINDOW_DEFAULT_WIDTH_MULTIPLIER),
            scaled(WINDOW_DEFAULT_HEIGHT_MULTIPLIER)
        )

    def _setup_ui(self) -> None:
        """Set up the main user interface."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create tab widget
        self._tab_widget = QTabWidget()

        # Create panels (tabs)
        self._input_panel = InputPanel()
        self._workflow_panel = WorkflowPanel()
        self._results_panel = ResultsPanel()

        # Add tabs
        self._tab_widget.addTab(self._input_panel, "Input")
        self._tab_widget.addTab(self._workflow_panel, "Workflow")
        self._tab_widget.addTab(self._results_panel, "Results")

        layout.addWidget(self._tab_widget)

    def _connect_signals(self) -> None:
        """Connect signals between panels and handlers."""
        # Input panel signals
        self._input_panel.review_requested.connect(self._start_review)

        # Workflow panel signals
        self._workflow_panel.abort_requested.connect(self._abort_review)

    def _start_review(self, input_data: Dict[str, Any]) -> None:
        """
        Start a paper review.

        Args:
            input_data: Dictionary containing input type, value, and options
        """
        if self._thread is not None and self._thread.isRunning():
            QMessageBox.warning(
                self,
                "Review in Progress",
                "A review is already in progress. Please wait or abort."
            )
            return

        # Switch to workflow tab and reset
        self._tab_widget.setCurrentIndex(TAB_WORKFLOW)
        self._workflow_panel.reset()
        self._workflow_panel.start_processing()

        # Disable input panel during processing
        self._input_panel.set_enabled(False)

        # Extract input parameters
        input_type = input_data.get("type")
        value = input_data.get("value")
        search_external = input_data.get("search_external", True)
        model = input_data.get("model")

        # Map input type to worker parameters
        doi = None
        pmid = None
        pdf_path = None
        text = None
        text_file = None

        if input_type == INPUT_TYPE_DOI:
            doi = value
        elif input_type == INPUT_TYPE_PMID:
            pmid = value
        elif input_type == INPUT_TYPE_PDF:
            pdf_path = Path(value) if isinstance(value, str) else value
        elif input_type == INPUT_TYPE_TEXT:
            text = value
        elif input_type == INPUT_TYPE_FILE:
            text_file = Path(value) if isinstance(value, str) else value

        # Record start time
        self._review_start_time = time.time()

        # Create and start worker thread
        self._thread = ReviewThread(
            doi=doi,
            pmid=pmid,
            pdf_path=pdf_path,
            text=text,
            text_file=text_file,
            search_external=search_external,
            model=model,
            parent=self,
        )

        # Connect worker signals
        self._thread.progress.connect(self._on_progress)
        self._thread.step_data.connect(self._on_step_data)
        self._thread.finished.connect(self._on_review_complete)
        self._thread.error.connect(self._on_review_error)

        self._thread.start()

        logger.info(f"Started paper review: type={input_type}")

    def _on_progress(self, step_name: str, message: str) -> None:
        """
        Handle progress update from worker.

        Args:
            step_name: Current step identifier
            message: Progress message
        """
        self._workflow_panel.update_step(step_name, STATUS_IN_PROGRESS, message)

    def _on_step_data(self, step_name: str, data: Dict[str, Any]) -> None:
        """
        Handle intermediate data from worker.

        Args:
            step_name: Step that produced the data
            data: Dictionary with step results
        """
        # Determine status from data
        status = data.get("status", STATUS_COMPLETED)
        if status == "skipped":
            status = STATUS_SKIPPED
        elif status == "error":
            status = STATUS_FAILED
        else:
            status = STATUS_COMPLETED

        message = data.get("message", "")

        self._workflow_panel.update_step(step_name, status, message, data)

    def _on_review_complete(self, result: Any) -> None:
        """
        Handle review completion.

        Args:
            result: PaperReviewResult from the agent
        """
        # Calculate elapsed time
        elapsed = None
        if self._review_start_time:
            elapsed = time.time() - self._review_start_time
            self._review_start_time = None

        # Format completion message
        if elapsed:
            message = f"Review completed in {elapsed:.1f}s"
        else:
            message = "Review completed"

        # Update workflow panel
        self._workflow_panel.set_completed(message)

        # Load results
        self._results_panel.set_result(result)

        # Switch to results tab
        self._tab_widget.setCurrentIndex(TAB_RESULTS)

        # Re-enable input panel
        self._input_panel.set_enabled(True)

        logger.info(message)

    def _on_review_error(self, error: str) -> None:
        """
        Handle review error.

        Args:
            error: Error message
        """
        self._review_start_time = None

        # Update workflow panel
        self._workflow_panel.set_failed(error)

        # Re-enable input panel
        self._input_panel.set_enabled(True)

        # Show error dialog
        QMessageBox.critical(
            self,
            "Review Error",
            f"Paper review failed:\n{error}"
        )

        logger.error(f"Paper review error: {error}")

    def _abort_review(self) -> None:
        """Abort the current review."""
        if self._thread and self._thread.isRunning():
            self._thread.abort()
            self._workflow_panel.set_failed("Aborted by user")

            # Re-enable input panel
            self._input_panel.set_enabled(True)

            logger.info("Paper review aborted by user")

    def closeEvent(self, event) -> None:
        """Handle window close event."""
        # Abort any running review
        if self._thread and self._thread.isRunning():
            self._thread.abort()
            self._thread.wait()

        event.accept()


def main() -> None:
    """Main entry point for the application."""
    import sys

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)

    # Create and show main window
    window = PaperReviewerLab()
    window.show()

    # Run event loop
    sys.exit(app.exec())


__all__ = ['PaperReviewerLab', 'main', 'APP_TITLE', 'APP_SUBTITLE']
