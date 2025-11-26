"""
PaperChecker Laboratory - Worker Threads

Background worker threads for paper checking to keep GUI responsive.
"""

import logging
from typing import TYPE_CHECKING, Optional, Dict, Any

from PySide6.QtCore import QThread, Signal

from .utils import map_agent_progress_to_step

if TYPE_CHECKING:
    from bmlibrarian.paperchecker.agent import PaperCheckerAgent
    from bmlibrarian.paperchecker.data_models import PaperCheckResult


logger = logging.getLogger(__name__)


class PaperCheckWorker(QThread):
    """
    Background worker thread for paper checking.

    Runs the PaperCheckerAgent.check_abstract() in a separate thread to keep
    GUI responsive during LLM calls which can take several seconds to minutes.

    Signals:
        progress_update: Emitted when progress is made (step_name, progress_fraction)
        intermediate_data: Emitted when intermediate results are available
                          (step_name, data_dict) for displaying in collapsible cards
        check_complete: Emitted with PaperCheckResult when done
        check_error: Emitted with error message on failure
    """

    # Signals for thread-safe GUI updates
    progress_update = Signal(str, float)  # (step_name, progress_fraction 0.0-1.0)
    intermediate_data = Signal(str, dict)  # (step_name, data_dict)
    check_complete = Signal(object)  # PaperCheckResult
    check_error = Signal(str)  # error_message

    def __init__(
        self,
        agent: "PaperCheckerAgent",
        abstract: str,
        source_metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Initialize paper check worker.

        Args:
            agent: PaperCheckerAgent instance
            abstract: Abstract text to check
            source_metadata: Optional metadata dict with pmid, doi, title, authors, year
        """
        super().__init__()
        self.agent = agent
        self.abstract = abstract
        self.source_metadata = source_metadata or {}
        self._cancelled = False

    def cancel(self) -> None:
        """
        Request cancellation of the check.

        Note: This sets a flag but cannot immediately stop LLM calls.
        The worker will check this flag between operations.
        """
        self._cancelled = True
        logger.info("Paper check cancellation requested")

    def _progress_callback(self, step_name: str, progress: float) -> None:
        """
        Internal callback bridging agent progress to Qt signals.

        Args:
            step_name: Current step name from agent
            progress: Progress fraction from agent (0.0-1.0)
        """
        if self._cancelled:
            return

        # Map agent step to our workflow steps
        step_index, display_name = map_agent_progress_to_step(step_name, progress)

        # Emit progress signal (thread-safe via Qt's signal mechanism)
        self.progress_update.emit(display_name, progress)

    def _data_callback(self, step_name: str, data: Dict[str, Any]) -> None:
        """
        Internal callback bridging agent intermediate data to Qt signals.

        Args:
            step_name: Current step name from agent
            data: Dictionary containing step-specific intermediate results
        """
        if self._cancelled:
            return

        # Map agent step to our workflow steps for consistent naming
        step_index, display_name = map_agent_progress_to_step(step_name, 0.0)

        # Emit intermediate data signal (thread-safe via Qt's signal mechanism)
        self.intermediate_data.emit(display_name, data)

    def run(self) -> None:
        """Run paper check in background thread."""
        try:
            logger.info(f"Starting paper check for abstract ({len(self.abstract)} chars)")

            # Check for early cancellation
            if self._cancelled:
                logger.info("Paper check cancelled before start")
                return

            # Emit initial progress
            self.progress_update.emit("Initializing", 0.0)

            # Perform the check with progress and data callbacks
            result = self.agent.check_abstract(
                abstract=self.abstract,
                source_metadata=self.source_metadata,
                progress_callback=self._progress_callback,
                data_callback=self._data_callback
            )

            # Check for cancellation after completion
            if self._cancelled:
                logger.info("Paper check completed but was cancelled")
                return

            # Emit completion signal
            logger.info("Paper check completed successfully")
            self.check_complete.emit(result)

        except Exception as e:
            logger.error(f"Paper check worker error: {e}", exc_info=True)
            if not self._cancelled:
                self.check_error.emit(str(e))


class DocumentFetchWorker(QThread):
    """
    Background worker for fetching document by ID or PMID from database.

    Signals:
        fetch_complete: Emitted with document dict when found
        fetch_error: Emitted with error message on failure
    """

    fetch_complete = Signal(dict)  # document data
    fetch_error = Signal(str)  # error message

    def __init__(
        self,
        document_id: Optional[int] = None,
        pmid: Optional[int] = None
    ) -> None:
        """
        Initialize document fetch worker.

        Args:
            document_id: Database document ID (preferred)
            pmid: PubMed ID (fallback if document_id not provided)
        """
        super().__init__()
        self.document_id = document_id
        self.pmid = pmid

    def run(self) -> None:
        """Fetch document from database.

        Uses the canonical get_document_details function for consistent
        document fetching. For PMID lookups, first resolves to document_id.
        """
        try:
            # Import here to avoid circular imports
            from bmlibrarian.database import get_document_details, get_db_manager

            doc_id = self.document_id

            # If PMID provided but not document_id, look up the document_id first
            if doc_id is None and self.pmid is not None:
                logger.info(f"Looking up document_id for PMID: {self.pmid}")
                db = get_db_manager()
                with db.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT id FROM document WHERE external_id = %s LIMIT 1",
                            (str(self.pmid),)
                        )
                        row = cur.fetchone()
                        if row:
                            doc_id = row[0]
                        else:
                            raise ValueError(f"No document found with PMID {self.pmid}")

            if doc_id is None:
                raise ValueError("Either document_id or pmid must be provided")

            # Use canonical function to get complete document details
            logger.info(f"Fetching document with ID: {doc_id}")
            result = get_document_details(doc_id)

            if result is None:
                raise ValueError(f"No document found with ID {doc_id}")

            logger.info(f"Found document: {result.get('title', 'No title')[:50]}")
            self.fetch_complete.emit(result)

        except Exception as e:
            logger.error(f"Document fetch error: {e}", exc_info=True)
            self.fetch_error.emit(str(e))


__all__ = [
    'PaperCheckWorker',
    'DocumentFetchWorker',
]
