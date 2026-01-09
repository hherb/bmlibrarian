"""
Paper Reviewer Lab Worker

QThread worker for running paper review in background.
Emits signals for progress updates and results.
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any

from PySide6.QtCore import QObject, QThread, Signal

from bmlibrarian.agents.paper_reviewer import PaperReviewerAgent, PaperReviewResult

logger = logging.getLogger(__name__)


class ReviewWorker(QObject):
    """
    Worker object that runs paper review in a background thread.

    Signals:
        progress: Emitted for each step (step_name, message)
        step_data: Emitted with intermediate data (step_name, data_dict)
        finished: Emitted when review completes (result)
        error: Emitted on error (error_message)
    """

    # Signals
    progress = Signal(str, str)  # step_name, message
    step_data = Signal(str, dict)  # step_name, data
    finished = Signal(object)  # PaperReviewResult
    error = Signal(str)  # error message

    def __init__(
        self,
        doi: Optional[str] = None,
        pmid: Optional[str] = None,
        pdf_path: Optional[Path] = None,
        text: Optional[str] = None,
        text_file: Optional[Path] = None,
        search_external: bool = True,
        model: Optional[str] = None,
        host: Optional[str] = None,
    ):
        """
        Initialize the worker.

        Args:
            doi: DOI to review
            pmid: PMID to review
            pdf_path: PDF file path
            text: Raw text content
            text_file: Text file path
            search_external: Whether to search PubMed
            model: LLM model name
            host: Ollama host URL
        """
        super().__init__()
        self.doi = doi
        self.pmid = pmid
        self.pdf_path = pdf_path
        self.text = text
        self.text_file = text_file
        self.search_external = search_external
        self.model = model
        self.host = host
        self._abort = False

    def abort(self) -> None:
        """Request abort of the review process."""
        self._abort = True
        logger.info("Review abort requested")

    def _progress_callback(self, step_name: str, message: str) -> None:
        """Callback for progress updates from the agent."""
        if self._abort:
            raise InterruptedError("Review aborted by user")
        self.progress.emit(step_name, message)

    def _data_callback(self, step_name: str, data: Dict[str, Any]) -> None:
        """Callback for intermediate data from the agent."""
        self.step_data.emit(step_name, data)

    def run(self) -> None:
        """Run the paper review process."""
        try:
            logger.info("Starting paper review worker")

            # Create the agent
            agent = PaperReviewerAgent(
                model=self.model,
                host=self.host,
                callback=self._progress_callback,
                data_callback=self._data_callback,
            )

            # Run the review
            result = agent.review_paper(
                doi=self.doi,
                pmid=self.pmid,
                pdf_path=self.pdf_path,
                text=self.text,
                text_file=self.text_file,
                search_external=self.search_external,
            )

            if self._abort:
                logger.info("Review was aborted")
                self.error.emit("Review was aborted by user")
                return

            logger.info(f"Review completed successfully: {result.title}")
            self.finished.emit(result)

        except InterruptedError as e:
            logger.info(f"Review interrupted: {e}")
            self.error.emit(str(e))
        except Exception as e:
            logger.error(f"Review failed: {e}", exc_info=True)
            self.error.emit(str(e))


class ReviewThread(QThread):
    """
    Thread wrapper for the review worker.

    Creates and manages the worker, handling thread lifecycle.
    """

    # Forward signals from worker
    progress = Signal(str, str)
    step_data = Signal(str, dict)
    finished = Signal(object)
    error = Signal(str)

    def __init__(
        self,
        doi: Optional[str] = None,
        pmid: Optional[str] = None,
        pdf_path: Optional[Path] = None,
        text: Optional[str] = None,
        text_file: Optional[Path] = None,
        search_external: bool = True,
        model: Optional[str] = None,
        host: Optional[str] = None,
        parent: Optional[QObject] = None,
    ):
        """
        Initialize the review thread.

        Args:
            doi: DOI to review
            pmid: PMID to review
            pdf_path: PDF file path
            text: Raw text content
            text_file: Text file path
            search_external: Whether to search PubMed
            model: LLM model name
            host: Ollama host URL
            parent: Parent QObject
        """
        super().__init__(parent)
        self.worker = ReviewWorker(
            doi=doi,
            pmid=pmid,
            pdf_path=pdf_path,
            text=text,
            text_file=text_file,
            search_external=search_external,
            model=model,
            host=host,
        )

        # Connect worker signals to thread signals
        self.worker.progress.connect(self.progress.emit)
        self.worker.step_data.connect(self.step_data.emit)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)

    def run(self) -> None:
        """Run the worker in this thread."""
        self.worker.run()

    def abort(self) -> None:
        """Request abort of the review process."""
        self.worker.abort()

    def _on_finished(self, result: PaperReviewResult) -> None:
        """Handle worker finished signal."""
        self.finished.emit(result)

    def _on_error(self, error_msg: str) -> None:
        """Handle worker error signal."""
        self.error.emit(error_msg)


__all__ = ['ReviewWorker', 'ReviewThread']
