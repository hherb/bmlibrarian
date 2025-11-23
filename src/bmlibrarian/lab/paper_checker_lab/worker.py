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
        check_complete: Emitted with PaperCheckResult when done
        check_error: Emitted with error message on failure
    """

    # Signals for thread-safe GUI updates
    progress_update = Signal(str, float)  # (step_name, progress_fraction 0.0-1.0)
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

            # Perform the check with progress callback
            result = self.agent.check_abstract(
                abstract=self.abstract,
                source_metadata=self.source_metadata,
                progress_callback=self._progress_callback
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


class PDFAnalysisWorker(QThread):
    """
    Background worker for PDF analysis and abstract extraction.

    Extracts text from PDF and uses LLM to identify the abstract
    and extract metadata.

    Signals:
        progress_update: Emitted with status message
        analysis_complete: Emitted with extracted data dict
        analysis_error: Emitted with error message on failure
    """

    progress_update = Signal(str)  # status_message
    analysis_complete = Signal(dict)  # {abstract, title, authors, year, pmid, doi, ...}
    analysis_error = Signal(str)  # error_message

    def __init__(
        self,
        pdf_path: str,
        pdf_matcher: Any = None  # PDFMatcher instance
    ) -> None:
        """
        Initialize PDF analysis worker.

        Args:
            pdf_path: Path to PDF file
            pdf_matcher: Optional PDFMatcher instance for LLM extraction
        """
        super().__init__()
        self.pdf_path = pdf_path
        self.pdf_matcher = pdf_matcher
        self._cancelled = False

    def cancel(self) -> None:
        """Request cancellation of analysis."""
        self._cancelled = True

    def run(self) -> None:
        """Run PDF analysis in background thread."""
        try:
            logger.info(f"Starting PDF analysis: {self.pdf_path}")
            self.progress_update.emit("Reading PDF file...")

            if self._cancelled:
                return

            # Import here to avoid circular imports and for lazy loading
            from bmlibrarian.importers.pdf_matcher import PDFMatcher

            # Use provided matcher or create new one
            matcher = self.pdf_matcher
            if matcher is None:
                self.progress_update.emit("Initializing PDF matcher...")
                matcher = PDFMatcher()

            if self._cancelled:
                return

            self.progress_update.emit("Extracting text from PDF...")

            # Extract text - try multiple pages if first page has insufficient text
            # (handles PDFs with cover pages or sparse first pages)
            text = self._extract_text_with_fallback(self.pdf_path)
            if not text or len(text.strip()) < 100:
                raise ValueError("Could not extract sufficient text from PDF")

            if self._cancelled:
                return

            self.progress_update.emit("Analyzing document with LLM...")

            # Use LLM to extract metadata
            metadata = matcher.extract_metadata_with_llm(text)

            if self._cancelled:
                return

            # Build result
            result = {
                'abstract': metadata.get('abstract', ''),
                'title': metadata.get('title', ''),
                'authors': metadata.get('authors', []),
                'year': metadata.get('year'),
                'pmid': metadata.get('pmid'),
                'doi': metadata.get('doi'),
                'journal': metadata.get('journal', ''),
                'pdf_path': self.pdf_path,
                'extracted_text_length': len(text),
            }

            logger.info(f"PDF analysis complete: {result.get('title', 'No title')}")
            self.progress_update.emit("Analysis complete")
            self.analysis_complete.emit(result)

        except Exception as e:
            logger.error(f"PDF analysis error: {e}", exc_info=True)
            if not self._cancelled:
                self.analysis_error.emit(str(e))

    def _extract_text_with_fallback(self, pdf_path: str) -> Optional[str]:
        """
        Extract text from PDF, trying multiple pages if first page is insufficient.

        Some PDFs have cover pages or sparse first pages. This method tries
        pages 1-3 to find sufficient text content.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Extracted text or None if all pages fail
        """
        try:
            import pymupdf
        except ImportError:
            logger.error("PyMuPDF not available for multi-page extraction")
            return None

        min_text_length = 100
        max_pages_to_try = 3

        try:
            doc = pymupdf.open(str(pdf_path))
            if len(doc) == 0:
                logger.warning(f"PDF has no pages: {pdf_path}")
                doc.close()
                return None

            pages_to_try = min(max_pages_to_try, len(doc))

            for page_num in range(pages_to_try):
                page = doc[page_num]
                text = page.get_text()

                if text and len(text.strip()) >= min_text_length:
                    logger.debug(
                        f"Extracted {len(text)} chars from page {page_num + 1} "
                        f"of {pdf_path}"
                    )
                    doc.close()
                    return text

                logger.debug(
                    f"Page {page_num + 1} has insufficient text "
                    f"({len(text.strip()) if text else 0} chars), trying next..."
                )

            # If individual pages don't have enough, try combining first few pages
            combined_text = ""
            for page_num in range(pages_to_try):
                page = doc[page_num]
                combined_text += page.get_text() + "\n"

            doc.close()

            if combined_text and len(combined_text.strip()) >= min_text_length:
                logger.debug(
                    f"Using combined text from first {pages_to_try} pages "
                    f"({len(combined_text)} chars)"
                )
                return combined_text

            logger.warning(f"Could not extract sufficient text from {pdf_path}")
            return None

        except Exception as e:
            logger.error(f"Error extracting text from {pdf_path}: {e}")
            return None


class DocumentFetchWorker(QThread):
    """
    Background worker for fetching document by PMID from database.

    Signals:
        fetch_complete: Emitted with document dict when found
        fetch_error: Emitted with error message on failure
    """

    fetch_complete = Signal(dict)  # document data
    fetch_error = Signal(str)  # error message

    def __init__(self, pmid: int) -> None:
        """
        Initialize document fetch worker.

        Args:
            pmid: PubMed ID to fetch
        """
        super().__init__()
        self.pmid = pmid

    def run(self) -> None:
        """Fetch document from database."""
        try:
            logger.info(f"Fetching document with PMID: {self.pmid}")

            # Import here to avoid circular imports
            from bmlibrarian.database import get_db_manager

            db = get_db_manager()

            # Query for document by PMID
            query = """
                SELECT id, title, abstract, authors, publication_date,
                       pmid, doi, publication, source_id
                FROM documents
                WHERE pmid = %s
                LIMIT 1
            """

            with db.get_connection() as conn:
                from psycopg.rows import dict_row
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute(query, (self.pmid,))
                    row = cur.fetchone()

            if row is None:
                raise ValueError(f"No document found with PMID {self.pmid}")

            # Convert to dict
            result = dict(row)
            logger.info(f"Found document: {result.get('title', 'No title')[:50]}")
            self.fetch_complete.emit(result)

        except Exception as e:
            logger.error(f"Document fetch error: {e}", exc_info=True)
            self.fetch_error.emit(str(e))


__all__ = [
    'PaperCheckWorker',
    'PDFAnalysisWorker',
    'DocumentFetchWorker',
]
