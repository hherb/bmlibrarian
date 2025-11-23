"""
Background worker threads for PDF upload functionality.

Provides two worker classes:
- QuickExtractWorker: Fast regex extraction + database lookup (~100ms)
- LLMExtractWorker: Slow LLM-based extraction (5-30s fallback)

These workers run in background threads to keep the UI responsive during
PDF analysis operations.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThread, Signal

from bmlibrarian.importers.pdf_matcher import (
    PDFMatcher,
    ExtractedIdentifiers,
)
from .validators import sanitize_llm_input

logger = logging.getLogger(__name__)


@dataclass
class QuickMatchResult:
    """
    Result from quick extraction and database lookup.

    Attributes:
        success: Whether the operation completed successfully
        identifiers: Extracted identifiers (DOI/PMID) if found
        document: Matched document dict if found in database
        extracted_text: The extracted text from first page
        error: Error message if operation failed
    """

    success: bool
    identifiers: Optional[ExtractedIdentifiers] = None
    document: Optional[dict] = None
    extracted_text: Optional[str] = None
    error: Optional[str] = None

    def has_quick_match(self) -> bool:
        """Check if a quick database match was found."""
        return self.document is not None


@dataclass
class LLMExtractResult:
    """
    Result from LLM metadata extraction.

    Attributes:
        success: Whether the operation completed successfully
        metadata: Extracted metadata (doi, pmid, title, authors)
        document: Best matching document if found
        alternatives: List of alternative matches
        error: Error message if operation failed
    """

    success: bool
    metadata: Optional[dict] = None
    document: Optional[dict] = None
    alternatives: Optional[list[dict]] = None
    error: Optional[str] = None


class QuickExtractWorker(QThread):
    """
    Fast background worker for regex extraction and database lookup.

    This worker performs:
    1. Text extraction from PDF first page
    2. Regex-based DOI/PMID extraction
    3. Quick database lookup by exact identifier match

    Typical execution time: ~100-500ms

    Signals:
        quick_match_found: Emitted when an exact database match is found
        no_quick_match: Emitted when no quick match, provides text for LLM fallback
        error_occurred: Emitted on any error
        status_update: Emitted for status updates
    """

    quick_match_found = Signal(QuickMatchResult)
    no_quick_match = Signal(QuickMatchResult)
    error_occurred = Signal(str)
    status_update = Signal(str)

    def __init__(
        self,
        pdf_path: Path,
        parent: Optional[QThread] = None
    ):
        """
        Initialize the quick extract worker.

        Args:
            pdf_path: Path to PDF file to analyze
            parent: Optional parent QObject
        """
        super().__init__(parent)
        self.pdf_path = pdf_path
        self._matcher: Optional[PDFMatcher] = None

    def run(self):
        """Execute the quick extraction and lookup."""
        try:
            self.status_update.emit("Initializing PDF matcher...")
            self._matcher = PDFMatcher()

            # Step 1: Extract text from first page
            self.status_update.emit("Extracting text from PDF...")
            text = self._matcher.extract_first_page_text(self.pdf_path)

            if not text:
                result = QuickMatchResult(
                    success=False,
                    error="Could not extract text from PDF first page"
                )
                self.error_occurred.emit(result.error)
                return

            # Step 2: Regex extraction of identifiers
            self.status_update.emit("Searching for DOI/PMID...")
            identifiers = self._matcher.extract_identifiers_regex(text)

            if not identifiers.has_identifiers():
                # No identifiers found - need LLM fallback
                result = QuickMatchResult(
                    success=True,
                    identifiers=identifiers,
                    extracted_text=text
                )
                self.no_quick_match.emit(result)
                return

            # Step 3: Quick database lookup
            self.status_update.emit("Looking up in database...")
            document = self._matcher.quick_database_lookup(
                doi=identifiers.doi,
                pmid=identifiers.pmid
            )

            if document:
                # Found a quick match!
                result = QuickMatchResult(
                    success=True,
                    identifiers=identifiers,
                    document=document,
                    extracted_text=text
                )
                self.quick_match_found.emit(result)
            else:
                # Identifiers found but not in database
                result = QuickMatchResult(
                    success=True,
                    identifiers=identifiers,
                    extracted_text=text
                )
                self.no_quick_match.emit(result)

        except Exception as e:
            logger.exception(f"Error in quick extraction: {e}")
            self.error_occurred.emit(str(e))


class LLMExtractWorker(QThread):
    """
    Slow background worker for LLM-based metadata extraction.

    This worker performs:
    1. LLM-based metadata extraction (DOI, PMID, title, authors)
    2. Database matching using all available metadata
    3. Finding alternative matches by title similarity

    Typical execution time: 5-30 seconds

    Signals:
        extraction_complete: Emitted when extraction and matching is complete
        error_occurred: Emitted on any error
        status_update: Emitted for status updates
    """

    extraction_complete = Signal(LLMExtractResult)
    error_occurred = Signal(str)
    status_update = Signal(str)

    def __init__(
        self,
        extracted_text: str,
        parent: Optional[QThread] = None
    ):
        """
        Initialize the LLM extract worker.

        Args:
            extracted_text: Text from PDF first page to analyze
            parent: Optional parent QObject
        """
        super().__init__(parent)
        self.extracted_text = extracted_text
        self._matcher: Optional[PDFMatcher] = None

    def run(self):
        """Execute the LLM extraction and matching."""
        try:
            self.status_update.emit("Initializing LLM extraction...")
            self._matcher = PDFMatcher()

            # Step 1: Sanitize input text before sending to LLM
            # This prevents potential injection attacks and handles malformed text
            self.status_update.emit("Sanitizing extracted text...")
            sanitized_text = sanitize_llm_input(self.extracted_text)

            if not sanitized_text:
                result = LLMExtractResult(
                    success=False,
                    error="No usable text after sanitization"
                )
                self.error_occurred.emit(result.error)
                return

            # Step 2: LLM metadata extraction
            self.status_update.emit("Extracting metadata with LLM (this may take a moment)...")
            metadata = self._matcher.extract_metadata_with_llm(sanitized_text)

            if not metadata:
                result = LLMExtractResult(
                    success=False,
                    error="LLM failed to extract any metadata"
                )
                self.error_occurred.emit(result.error)
                return

            # Check if we got any useful metadata
            has_useful_data = any([
                metadata.get('doi'),
                metadata.get('pmid'),
                metadata.get('title')
            ])

            if not has_useful_data:
                result = LLMExtractResult(
                    success=True,
                    metadata=metadata,
                    error="Could not extract DOI, PMID, or title from PDF"
                )
                self.extraction_complete.emit(result)
                return

            # Step 2: Find matching document
            self.status_update.emit("Searching database for matches...")
            document = self._matcher.find_matching_document(metadata)

            # Step 3: Find alternative matches by title
            alternatives = []
            if metadata.get('title'):
                self.status_update.emit("Finding alternative matches...")
                exclude_id = document['id'] if document else None
                alternatives = self._matcher.find_alternative_matches(
                    metadata['title'],
                    exclude_id=exclude_id
                )

            result = LLMExtractResult(
                success=True,
                metadata=metadata,
                document=document,
                alternatives=alternatives
            )
            self.extraction_complete.emit(result)

        except Exception as e:
            logger.exception(f"Error in LLM extraction: {e}")
            self.error_occurred.emit(str(e))
