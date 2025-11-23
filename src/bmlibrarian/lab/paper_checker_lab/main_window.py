"""
PaperChecker Laboratory - Main Window

Main application window coordinating the tabbed interface.
"""

import logging
import time
from typing import Optional, Dict, Any

from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QVBoxLayout,
    QMessageBox, QApplication,
)
from PySide6.QtCore import Qt

from bmlibrarian.gui.qt.resources.styles.dpi_scale import get_font_scale
from bmlibrarian.gui.qt.resources.styles.stylesheet_generator import get_stylesheet_generator
from bmlibrarian.paperchecker.agent import PaperCheckerAgent

from .constants import (
    APP_TITLE, APP_SUBTITLE,
    WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT,
    WINDOW_DEFAULT_WIDTH, WINDOW_DEFAULT_HEIGHT,
    TAB_INDEX_INPUT, TAB_INDEX_PDF_UPLOAD, TAB_INDEX_WORKFLOW, TAB_INDEX_RESULTS,
)
from .worker import PaperCheckWorker
from .tabs import InputTab, PDFUploadTab, WorkflowTab, ResultsTab


logger = logging.getLogger(__name__)


class PaperCheckerLab(QMainWindow):
    """
    Main window for the PaperChecker Laboratory.

    Coordinates the tabbed interface for abstract input, PDF upload,
    workflow visualization, and results display.
    """

    def __init__(self) -> None:
        """Initialize the main window."""
        super().__init__()

        self.scale = get_font_scale()
        self.styles = get_stylesheet_generator()
        self._agent: Optional[PaperCheckerAgent] = None
        self._worker: Optional[PaperCheckWorker] = None
        self._check_start_time: Optional[float] = None

        self._setup_window()
        self._setup_ui()
        self._connect_signals()
        self._initialize_agent()

    def _setup_window(self) -> None:
        """Configure main window properties."""
        self.setWindowTitle(f"{APP_TITLE} - {APP_SUBTITLE}")
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self.resize(WINDOW_DEFAULT_WIDTH, WINDOW_DEFAULT_HEIGHT)

    def _setup_ui(self) -> None:
        """Setup the main user interface."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create tab widget
        self._tab_widget = QTabWidget()

        # Create tabs
        self._input_tab = InputTab()
        self._pdf_upload_tab = PDFUploadTab()
        self._workflow_tab = WorkflowTab()
        self._results_tab = ResultsTab()

        # Add tabs
        self._tab_widget.addTab(self._input_tab, "Text Input")
        self._tab_widget.addTab(self._pdf_upload_tab, "PDF Upload")
        self._tab_widget.addTab(self._workflow_tab, "Workflow")
        self._tab_widget.addTab(self._results_tab, "Results")

        layout.addWidget(self._tab_widget)

    def _connect_signals(self) -> None:
        """Connect signals between tabs and handlers."""
        # Input tab signals
        self._input_tab.check_requested.connect(self._start_check)
        self._input_tab.clear_requested.connect(self._on_clear)

        # PDF upload tab signals
        self._pdf_upload_tab.check_requested.connect(self._start_check)
        self._pdf_upload_tab.abstract_extracted.connect(self._on_abstract_extracted)

        # Workflow tab signals
        self._workflow_tab.abort_requested.connect(self._abort_check)

    def _initialize_agent(self) -> None:
        """Initialize the PaperCheckerAgent."""
        try:
            model = self._input_tab.get_selected_model()
            self._agent = PaperCheckerAgent(show_model_info=False)
            logger.info(f"PaperCheckerAgent initialized")
        except Exception as e:
            logger.error(f"Failed to initialize agent: {e}")
            QMessageBox.critical(
                self,
                "Initialization Error",
                f"Failed to initialize PaperCheckerAgent:\n{str(e)}\n\n"
                "Please ensure Ollama is running and try again."
            )

    def _start_check(self, abstract: str, metadata: Dict[str, Any]) -> None:
        """
        Start a paper check.

        Args:
            abstract: Abstract text to check
            metadata: Source metadata dictionary
        """
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.warning(
                self,
                "Check in Progress",
                "A check is already in progress. Please wait or abort."
            )
            return

        if not self._agent:
            self._initialize_agent()
            if not self._agent:
                return

        # Reinitialize agent with selected model if different
        selected_model = self._input_tab.get_selected_model()
        # Agent will use its configured model

        # Switch to workflow tab
        self._tab_widget.setCurrentIndex(TAB_INDEX_WORKFLOW)

        # Reset and start workflow visualization
        self._workflow_tab.reset()
        self._workflow_tab.start()

        # Disable input tabs during processing
        self._input_tab.set_enabled(False)
        self._pdf_upload_tab.set_enabled(False)

        # Record start time
        self._check_start_time = time.time()

        # Create and start worker
        self._worker = PaperCheckWorker(self._agent, abstract, metadata)
        self._worker.progress_update.connect(self._on_progress_update)
        self._worker.check_complete.connect(self._on_check_complete)
        self._worker.check_error.connect(self._on_check_error)
        self._worker.start()

        logger.info(f"Started paper check for abstract ({len(abstract)} chars)")

    def _on_progress_update(self, step_name: str, progress: float) -> None:
        """
        Handle progress update from worker.

        Args:
            step_name: Current step name
            progress: Progress fraction (0.0-1.0)
        """
        self._workflow_tab.update_step(step_name, progress)

    def _on_check_complete(self, result: Any) -> None:
        """
        Handle check completion.

        Args:
            result: PaperCheckResult from the agent
        """
        # Calculate elapsed time
        elapsed = None
        if self._check_start_time:
            elapsed = time.time() - self._check_start_time
            self._check_start_time = None

        # Update workflow tab
        self._workflow_tab.set_complete(elapsed)

        # Load results
        self._results_tab.load_result(result)

        # Switch to results tab
        self._tab_widget.setCurrentIndex(TAB_INDEX_RESULTS)

        # Re-enable input tabs
        self._input_tab.set_enabled(True)
        self._pdf_upload_tab.set_enabled(True)

        logger.info(f"Paper check completed in {elapsed:.1f}s" if elapsed else "Paper check completed")

    def _on_check_error(self, error: str) -> None:
        """
        Handle check error.

        Args:
            error: Error message
        """
        self._check_start_time = None

        # Update workflow tab
        self._workflow_tab.set_error(error)

        # Re-enable input tabs
        self._input_tab.set_enabled(True)
        self._pdf_upload_tab.set_enabled(True)

        # Show error dialog
        QMessageBox.critical(
            self,
            "Check Error",
            f"Paper check failed:\n{error}"
        )

        logger.error(f"Paper check error: {error}")

    def _abort_check(self) -> None:
        """Abort the current check."""
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._workflow_tab.set_error("Aborted by user")

            # Re-enable input tabs
            self._input_tab.set_enabled(True)
            self._pdf_upload_tab.set_enabled(True)

            logger.info("Paper check aborted by user")

    def _on_abstract_extracted(self, abstract: str, metadata: Dict[str, Any]) -> None:
        """
        Handle abstract extracted from PDF.

        Args:
            abstract: Extracted abstract text
            metadata: Extracted metadata
        """
        # Populate input tab and switch to it
        self._input_tab.set_abstract(abstract, metadata)
        self._tab_widget.setCurrentIndex(TAB_INDEX_INPUT)

    def _on_clear(self) -> None:
        """Handle clear request."""
        self._results_tab.clear()
        self._workflow_tab.reset()


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
    window = PaperCheckerLab()
    window.show()

    # Run event loop
    sys.exit(app.exec())


__all__ = ['PaperCheckerLab', 'main']
