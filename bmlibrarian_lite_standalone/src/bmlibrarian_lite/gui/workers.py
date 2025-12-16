"""
Background worker threads for BMLibrarian Lite GUI.

Provides QThread-based workers for long-running operations:
- AnswerWorker: Generate answers using the interrogation agent
- PDFDiscoveryWorker: Discover and download PDFs (stub - not available in lite)
- QualityFilterWorker: Filter documents by quality criteria

These workers allow the main GUI thread to remain responsive while
background operations execute.
"""

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QWidget

if TYPE_CHECKING:
    from ..data_models import LiteDocument
    from ..quality.data_models import QualityFilter, QualityAssessment
    from ..quality.quality_manager import QualityManager

logger = logging.getLogger(__name__)


class AnswerWorker(QThread):
    """
    Background worker for generating answers.

    Executes the interrogation agent's ask() method in a background thread
    to prevent blocking the GUI.

    Signals:
        finished: Emitted when answer is ready (answer, sources)
        error: Emitted on error (error message)
    """

    finished = Signal(str, list)  # answer, sources
    error = Signal(str)

    def __init__(
        self,
        agent: 'LiteInterrogationAgent',
        question: str,
    ) -> None:
        """
        Initialize the answer worker.

        Args:
            agent: Interrogation agent instance
            question: Question to answer
        """
        super().__init__()
        self.agent = agent
        self.question = question

    def run(self) -> None:
        """Generate answer in background thread."""
        try:
            answer, sources = self.agent.ask(self.question)
            self.finished.emit(answer, sources)
        except Exception as e:
            logger.exception("Answer generation error")
            self.error.emit(str(e))


class PDFDiscoveryWorker(QThread):
    """
    Background worker for PDF discovery and download.

    Note: In BMLibrarian Lite, PDF discovery is not available.
    This worker always returns an error indicating the feature is not available.

    Signals:
        progress: Emitted with (stage, status) during download
        finished: Emitted with file_path when download succeeds
        verification_warning: Emitted with (file_path, warning_message) on verification mismatch
        paywall_detected: Emitted with (article_url, error_message) when paywall blocks access
        error: Emitted with error message on failure
    """

    progress = Signal(str, str)  # stage, status
    finished = Signal(str)  # file_path on success
    verification_warning = Signal(str, str)  # file_path, warning_message
    paywall_detected = Signal(str, str)  # article_url, error_message
    error = Signal(str)  # error message

    def __init__(
        self,
        doc_dict: Dict[str, Any],
        output_dir: Path,
        unpaywall_email: Optional[str] = None,
        openathens_url: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Initialize PDF discovery worker.

        Args:
            doc_dict: Document dictionary with doi, pmid, title, year, etc.
            output_dir: Base directory for PDF storage (year subdirs created)
            unpaywall_email: Email for Unpaywall API
            openathens_url: OpenAthens institution URL for authenticated downloads
            parent: Optional parent widget
        """
        super().__init__(parent)
        self.doc_dict = doc_dict
        self.output_dir = output_dir
        self.unpaywall_email = unpaywall_email
        self.openathens_url = openathens_url
        self._cancelled = False

    def run(self) -> None:
        """Execute PDF discovery and download."""
        # PDF discovery is not available in BMLibrarian Lite
        self.error.emit(
            "PDF discovery is not available in BMLibrarian Lite.\n"
            "You can manually download PDFs and import them into the application."
        )

    def cancel(self) -> None:
        """Request cancellation of the operation."""
        self._cancelled = True


class OpenAthensAuthWorker(QThread):
    """
    Background worker for OpenAthens interactive authentication.

    Note: In BMLibrarian Lite, OpenAthens authentication is not available.
    This worker always returns an error indicating the feature is not available.

    Signals:
        finished: Emitted when authentication succeeds
        error: Emitted with error message on failure
    """

    finished = Signal()  # Authentication succeeded
    error = Signal(str)  # error message

    def __init__(
        self,
        institution_url: str,
        session_max_age_hours: int = 24,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Initialize OpenAthens authentication worker.

        Args:
            institution_url: Institution's OpenAthens login URL (HTTPS)
            session_max_age_hours: Maximum session age before re-authentication
            parent: Optional parent widget
        """
        super().__init__(parent)
        self.institution_url = institution_url
        self.session_max_age_hours = session_max_age_hours

    def run(self) -> None:
        """Execute OpenAthens interactive authentication."""
        # OpenAthens authentication is not available in BMLibrarian Lite
        self.error.emit(
            "OpenAthens authentication is not available in BMLibrarian Lite.\n"
            "This feature requires the full BMLibrarian installation."
        )


class QualityFilterWorker(QThread):
    """
    Background worker for quality filtering documents.

    Executes quality assessment and filtering in a background thread
    to prevent blocking the GUI during LLM calls.

    Signals:
        progress: Emitted during progress (current, total, assessment)
        finished: Emitted when filtering completes (filtered_docs, all_assessments)
        error: Emitted on error (error message)
    """

    progress = Signal(int, int, object)  # current, total, QualityAssessment
    finished = Signal(list, list)  # filtered docs, all assessments
    error = Signal(str)

    def __init__(
        self,
        quality_manager: "QualityManager",
        documents: List["LiteDocument"],
        filter_settings: "QualityFilter",
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Initialize the quality filter worker.

        Args:
            quality_manager: QualityManager instance for assessment
            documents: List of documents to filter
            filter_settings: Quality filter configuration
            parent: Optional parent widget
        """
        super().__init__(parent)
        self.quality_manager = quality_manager
        self.documents = documents
        self.filter_settings = filter_settings
        self._cancelled = False

    def run(self) -> None:
        """Run quality filtering in background thread."""
        try:
            def progress_callback(
                current: int,
                total: int,
                assessment: "QualityAssessment",
            ) -> None:
                """Emit progress signal if not cancelled."""
                if not self._cancelled:
                    self.progress.emit(current, total, assessment)

            filtered, assessments = self.quality_manager.filter_documents(
                self.documents,
                self.filter_settings,
                progress_callback=progress_callback,
            )

            if not self._cancelled:
                self.finished.emit(filtered, assessments)

        except Exception as e:
            logger.exception("Quality filtering failed")
            if not self._cancelled:
                self.error.emit(str(e))

    def cancel(self) -> None:
        """Request cancellation of the operation."""
        self._cancelled = True
