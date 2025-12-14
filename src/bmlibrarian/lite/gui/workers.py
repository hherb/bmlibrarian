"""
Background worker threads for BMLibrarian Lite GUI.

Provides QThread-based workers for long-running operations:
- AnswerWorker: Generate answers using the interrogation agent
- PDFDiscoveryWorker: Discover and download PDFs with verification

These workers allow the main GUI thread to remain responsive while
background operations execute.
"""

import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QWidget

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

    Discovers PDF sources and downloads to year-based folder structure.
    Includes verification to detect when wrong PDF is downloaded.

    Signals:
        progress: Emitted with (stage, status) during download
        finished: Emitted with file_path when download succeeds
        verification_warning: Emitted with (file_path, warning_message) on verification mismatch
        error: Emitted with error message on failure
    """

    progress = Signal(str, str)  # stage, status
    finished = Signal(str)  # file_path on success
    verification_warning = Signal(str, str)  # file_path, warning_message
    error = Signal(str)  # error message

    def __init__(
        self,
        doc_dict: Dict[str, Any],
        output_dir: Path,
        unpaywall_email: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Initialize PDF discovery worker.

        Args:
            doc_dict: Document dictionary with doi, pmid, title, year, etc.
            output_dir: Base directory for PDF storage (year subdirs created)
            unpaywall_email: Email for Unpaywall API
            parent: Optional parent widget
        """
        super().__init__(parent)
        self.doc_dict = doc_dict
        self.output_dir = output_dir
        self.unpaywall_email = unpaywall_email
        self._cancelled = False

    def run(self) -> None:
        """Execute PDF discovery and download with verification."""
        try:
            from bmlibrarian.discovery import download_pdf_for_document

            def progress_callback(stage: str, status: str) -> None:
                if not self._cancelled:
                    self.progress.emit(stage, status)

            result = download_pdf_for_document(
                document=self.doc_dict,
                output_dir=self.output_dir,
                unpaywall_email=self.unpaywall_email,
                progress_callback=progress_callback,
                verify_content=True,  # Enable verification to detect wrong PDFs
                delete_on_mismatch=False,  # Keep file but warn user
            )

            if self._cancelled:
                return

            if result.success and result.file_path:
                # Check if verification detected a mismatch
                if result.verified is False:
                    # Build warning message with details
                    warnings = result.verification_warnings or []
                    warning_parts = []

                    if result.extracted_doi and self.doc_dict.get('doi'):
                        warning_parts.append(
                            f"Expected DOI: {self.doc_dict['doi']}, "
                            f"Found: {result.extracted_doi}"
                        )
                    if result.extracted_title:
                        warning_parts.append(f"PDF title: {result.extracted_title[:80]}...")

                    warning_msg = "PDF verification FAILED - wrong document may have been downloaded.\n"
                    if warning_parts:
                        warning_msg += "\n".join(warning_parts)
                    elif warnings:
                        warning_msg += "; ".join(warnings)

                    logger.warning(f"PDF mismatch detected: {warning_msg}")
                    self.verification_warning.emit(result.file_path, warning_msg)
                else:
                    self.finished.emit(result.file_path)
            else:
                self.error.emit(result.error_message or "Unknown error")

        except Exception as e:
            logger.exception("PDF discovery failed")
            if not self._cancelled:
                self.error.emit(str(e))

    def cancel(self) -> None:
        """Request cancellation of the operation."""
        self._cancelled = True
