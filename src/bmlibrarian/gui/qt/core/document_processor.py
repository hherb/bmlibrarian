"""
Reusable document processing module for BMLibrarian Qt GUI.

Provides a unified pipeline for processing incoming documents across
different plugins (Document Interrogation, Paper Weight Lab, etc.).

The processing pipeline handles:
1. Checking if embeddings already exist
2. Checking for full text in database
3. PDF discovery and download (if needed)
4. PDF conversion to text
5. Embedding creation
6. Progress callbacks for UI updates

Example usage:
    from bmlibrarian.gui.qt.core.document_processor import (
        DocumentProcessor,
        DocumentProcessingResult,
        ProcessingStage,
    )

    processor = DocumentProcessor()

    # Process document with callback
    def on_progress(stage, message, current, total):
        print(f"{stage.value}: {message} ({current}/{total})")

    result = processor.process_document(
        document_id=12345,
        progress_callback=on_progress,
        prompt_for_pdf_search=True,  # Ask user if PDF should be searched
    )

    if result.success:
        print(f"Created {result.chunks_created} chunks")
        if result.pdf_path:
            print(f"PDF at: {result.pdf_path}")
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List

logger = logging.getLogger(__name__)


class ProcessingStage(Enum):
    """Stages of document processing pipeline."""

    CHECKING_EMBEDDINGS = "checking_embeddings"
    CHECKING_FULL_TEXT = "checking_full_text"
    DISCOVERING_PDF = "discovering_pdf"
    DOWNLOADING_PDF = "downloading_pdf"
    EXTRACTING_TEXT = "extracting_text"
    CREATING_EMBEDDINGS = "creating_embeddings"
    COMPLETE = "complete"
    ERROR = "error"


class ContentSource(Enum):
    """Source of document content."""

    EXISTING_EMBEDDINGS = "existing_embeddings"
    EXISTING_FULL_TEXT = "existing_full_text"
    EXISTING_PDF = "existing_pdf"
    DOWNLOADED_PDF = "downloaded_pdf"
    NXML_FULL_TEXT = "nxml_full_text"
    ABSTRACT_ONLY = "abstract_only"


@dataclass
class DocumentInfo:
    """Information about a document retrieved from the database."""

    id: int
    title: Optional[str] = None
    abstract: Optional[str] = None
    doi: Optional[str] = None
    pmid: Optional[str] = None
    pdf_url: Optional[str] = None
    pdf_filename: Optional[str] = None
    full_text: Optional[str] = None
    year: Optional[int] = None
    has_embeddings: bool = False
    embedding_count: int = 0

    @property
    def has_full_text(self) -> bool:
        """Check if document has full text."""
        return bool(self.full_text and self.full_text.strip())

    @property
    def has_pdf(self) -> bool:
        """Check if document has a PDF file reference."""
        return bool(self.pdf_filename and self.pdf_filename.strip())

    @property
    def has_identifiers_for_search(self) -> bool:
        """Check if document has identifiers for online search."""
        return any([self.doi, self.pmid, self.pdf_url, self.title])


@dataclass
class DocumentProcessingResult:
    """Result of document processing."""

    success: bool
    document_id: int
    content_source: Optional[ContentSource] = None
    chunks_created: int = 0
    pdf_path: Optional[Path] = None
    full_text: Optional[str] = None
    full_text_char_count: int = 0
    error_message: Optional[str] = None
    warnings: List[str] = field(default_factory=list)

    def __str__(self) -> str:
        """Return human-readable summary."""
        status = "SUCCESS" if self.success else "FAILED"
        source = self.content_source.value if self.content_source else "none"
        return (
            f"DocumentProcessingResult({status}, doc_id={self.document_id}, "
            f"source={source}, chunks={self.chunks_created})"
        )


# Type alias for progress callback
# Signature: (stage, message, current, total) -> None
ProgressCallback = Callable[[ProcessingStage, str, int, int], None]

# Type alias for user prompt callback
# Signature: (title, message, options) -> str
# Returns selected option key or None if cancelled
PromptCallback = Callable[[str, str, List[str]], Optional[str]]

# Progress report interval for chunk creation
CHUNK_PROGRESS_INTERVAL = 10


class DocumentProcessor:
    """
    Unified document processing pipeline.

    Handles the complete workflow for making a document ready for
    interrogation or analysis:
    1. Check if embeddings already exist (skip processing if so)
    2. Check for existing full text in database
    3. Discover and download PDF if needed
    4. Extract text from PDF
    5. Create embeddings

    Designed to be reusable across different plugins.
    """

    def __init__(
        self,
        pdf_base_dir: Optional[str] = None,
        unpaywall_email: Optional[str] = None,
    ) -> None:
        """
        Initialize document processor.

        Args:
            pdf_base_dir: Base directory for PDF storage.
                         If None, uses config or default.
            unpaywall_email: Email for Unpaywall API access.
                            If None, uses config.
        """
        from bmlibrarian.database import get_db_manager
        from bmlibrarian.config import get_config

        self.db_manager = get_db_manager()
        self.config = get_config()

        # Set PDF base directory
        if pdf_base_dir is None:
            pdf_config = self.config.get('pdf') or {}
            if isinstance(pdf_config, dict):
                pdf_base_dir = pdf_config.get('base_dir', '~/knowledgebase/pdf')
            else:
                pdf_base_dir = '~/knowledgebase/pdf'
        self.pdf_base_dir = Path(pdf_base_dir).expanduser()

        # Set unpaywall email
        if unpaywall_email is None:
            unpaywall_email = self.config.get('unpaywall_email')
        self.unpaywall_email = str(unpaywall_email) if unpaywall_email else None

        logger.info(f"DocumentProcessor initialized: pdf_base_dir={self.pdf_base_dir}")

    def get_document_info(self, document_id: int) -> Optional[DocumentInfo]:
        """
        Retrieve document information from database.

        Args:
            document_id: Database document ID.

        Returns:
            DocumentInfo or None if not found.
        """
        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    # Get document details
                    # Note: document table uses external_id + source_id, not pmid directly
                    # source_id=1 is typically PubMed, so external_id would be the PMID
                    cur.execute(
                        """
                        SELECT d.id, d.title, d.abstract, d.doi, d.external_id,
                               d.source_id, d.pdf_url, d.pdf_filename, d.full_text,
                               EXTRACT(YEAR FROM d.publication_date)::int
                        FROM public.document d
                        WHERE d.id = %s
                        """,
                        (document_id,),
                    )
                    row = cur.fetchone()
                    if not row:
                        return None

                    # external_id is PMID when source_id=1 (PubMed)
                    external_id = row[4]
                    source_id = row[5]
                    pmid = external_id if source_id == 1 else None

                    doc_info = DocumentInfo(
                        id=row[0],
                        title=row[1],
                        abstract=row[2],
                        doi=row[3],
                        pmid=pmid,
                        pdf_url=row[6],
                        pdf_filename=row[7],
                        full_text=row[8],
                        year=row[9],
                    )

                    # Check for existing embeddings
                    cur.execute(
                        """
                        SELECT COUNT(*)
                        FROM semantic.chunks
                        WHERE document_id = %s
                        """,
                        (document_id,),
                    )
                    count_row = cur.fetchone()
                    doc_info.embedding_count = count_row[0] if count_row else 0
                    doc_info.has_embeddings = doc_info.embedding_count > 0

                    return doc_info

        except Exception as e:
            logger.error(f"Error getting document info for {document_id}: {e}")
            return None

    def get_pdf_path(self, doc_info: DocumentInfo) -> Optional[Path]:
        """
        Get the full path to a document's PDF file.

        Args:
            doc_info: Document information.

        Returns:
            Path to PDF file if it exists, None otherwise.
        """
        if not doc_info.pdf_filename:
            return None

        # Handle both relative (year/file.pdf) and absolute paths
        pdf_filename = doc_info.pdf_filename

        # Check if it's a relative path (contains year subdirectory)
        if '/' in pdf_filename:
            pdf_path = self.pdf_base_dir / pdf_filename
        else:
            # Try with year subdirectory
            if doc_info.year:
                pdf_path = self.pdf_base_dir / str(doc_info.year) / pdf_filename
            else:
                pdf_path = self.pdf_base_dir / pdf_filename

        if pdf_path.exists():
            return pdf_path

        # Try without year directory as fallback
        pdf_path = self.pdf_base_dir / Path(pdf_filename).name
        if pdf_path.exists():
            return pdf_path

        return None

    def process_document(
        self,
        document_id: int,
        progress_callback: Optional[ProgressCallback] = None,
        prompt_callback: Optional[PromptCallback] = None,
        force_reprocess: bool = False,
        skip_pdf_search: bool = False,
    ) -> DocumentProcessingResult:
        """
        Process a document through the complete pipeline.

        Args:
            document_id: Database document ID.
            progress_callback: Optional callback for progress updates.
                              Signature: (stage, message, current, total)
            prompt_callback: Optional callback for user prompts.
                            If None, PDF search will be skipped when no
                            full text is available.
            force_reprocess: If True, reprocess even if embeddings exist.
            skip_pdf_search: If True, skip online PDF search entirely.

        Returns:
            DocumentProcessingResult with details of the operation.
        """

        def report_progress(
            stage: ProcessingStage,
            message: str,
            current: int = 0,
            total: int = 0,
        ) -> None:
            """Report progress to callback if available."""
            if progress_callback:
                progress_callback(stage, message, current, total)

        # Step 1: Get document info
        report_progress(ProcessingStage.CHECKING_EMBEDDINGS, "Checking document...", 0, 1)

        doc_info = self.get_document_info(document_id)
        if not doc_info:
            return DocumentProcessingResult(
                success=False,
                document_id=document_id,
                error_message=f"Document not found: {document_id}",
            )

        # Step 2: Check if embeddings already exist
        if doc_info.has_embeddings and not force_reprocess:
            report_progress(
                ProcessingStage.COMPLETE,
                f"Document has {doc_info.embedding_count} existing chunks",
                1, 1,
            )
            return DocumentProcessingResult(
                success=True,
                document_id=document_id,
                content_source=ContentSource.EXISTING_EMBEDDINGS,
                chunks_created=doc_info.embedding_count,
                full_text=doc_info.full_text,
                full_text_char_count=len(doc_info.full_text) if doc_info.full_text else 0,
            )

        # Step 3: Check for existing full text
        report_progress(ProcessingStage.CHECKING_FULL_TEXT, "Checking for full text...", 0, 1)

        if doc_info.has_full_text:
            # Full text exists, just need to create embeddings
            report_progress(
                ProcessingStage.CHECKING_FULL_TEXT,
                f"Full text found ({len(doc_info.full_text):,} chars)",
                1, 1,
            )
            return self._create_embeddings_from_text(
                document_id=document_id,
                full_text=doc_info.full_text,
                content_source=ContentSource.EXISTING_FULL_TEXT,
                progress_callback=progress_callback,
            )

        # Step 4: Check for existing PDF
        pdf_path = self.get_pdf_path(doc_info)
        if pdf_path:
            report_progress(
                ProcessingStage.EXTRACTING_TEXT,
                f"Found PDF: {pdf_path.name}",
                0, 1,
            )
            return self._process_pdf(
                document_id=document_id,
                pdf_path=pdf_path,
                content_source=ContentSource.EXISTING_PDF,
                progress_callback=progress_callback,
            )

        # Step 5: No local content - try online discovery
        if skip_pdf_search or not doc_info.has_identifiers_for_search:
            # Use abstract only
            report_progress(
                ProcessingStage.COMPLETE,
                "No full text available, using abstract only",
                1, 1,
            )
            if doc_info.abstract:
                return self._create_embeddings_from_text(
                    document_id=document_id,
                    full_text=doc_info.abstract,
                    content_source=ContentSource.ABSTRACT_ONLY,
                    progress_callback=progress_callback,
                    store_as_full_text=False,  # Don't overwrite full_text field
                )
            else:
                return DocumentProcessingResult(
                    success=False,
                    document_id=document_id,
                    error_message="No content available (no full text, PDF, or abstract)",
                )

        # Ask user if they want to search for PDF
        should_search = True
        if prompt_callback:
            response = prompt_callback(
                "No Full Text Available",
                f"Document '{doc_info.title or f'#{document_id}'}' has no full text.\n\n"
                "Would you like to search online for the PDF?\n"
                "If not, only the abstract will be used.",
                ["search", "abstract_only", "cancel"],
            )
            if response == "cancel":
                return DocumentProcessingResult(
                    success=False,
                    document_id=document_id,
                    error_message="Processing cancelled by user",
                )
            should_search = response == "search"

        if should_search:
            # Try online discovery
            report_progress(ProcessingStage.DISCOVERING_PDF, "Searching for PDF online...", 0, 1)
            discovery_result = self._discover_and_download_pdf(
                doc_info=doc_info,
                progress_callback=progress_callback,
            )

            if discovery_result.success:
                return discovery_result

            # Discovery failed - fall back to abstract
            logger.info(f"PDF discovery failed for {document_id}, using abstract")

        # Fallback: Use abstract only
        if doc_info.abstract:
            report_progress(
                ProcessingStage.COMPLETE,
                "Using abstract only",
                1, 1,
            )
            return self._create_embeddings_from_text(
                document_id=document_id,
                full_text=doc_info.abstract,
                content_source=ContentSource.ABSTRACT_ONLY,
                progress_callback=progress_callback,
                store_as_full_text=False,
            )
        else:
            return DocumentProcessingResult(
                success=False,
                document_id=document_id,
                error_message="No content available",
            )

    def _create_embeddings_from_text(
        self,
        document_id: int,
        full_text: str,
        content_source: ContentSource,
        progress_callback: Optional[ProgressCallback] = None,
        store_as_full_text: bool = True,
    ) -> DocumentProcessingResult:
        """
        Create embeddings from text content.

        Args:
            document_id: Document ID.
            full_text: Text to chunk and embed.
            content_source: Source of the content.
            progress_callback: Optional progress callback.
            store_as_full_text: If True, update full_text in database.

        Returns:
            DocumentProcessingResult.
        """
        from bmlibrarian.embeddings.chunk_embedder import ChunkEmbedder

        def report_progress(
            stage: ProcessingStage,
            message: str,
            current: int = 0,
            total: int = 0,
        ) -> None:
            if progress_callback:
                progress_callback(stage, message, current, total)

        try:
            # Optionally store full text in database
            if store_as_full_text:
                self._update_full_text_in_database(document_id, full_text)

            # Create embeddings
            report_progress(
                ProcessingStage.CREATING_EMBEDDINGS,
                "Initializing embedder...",
                0, 1,
            )

            embedder = ChunkEmbedder()

            # Progress wrapper that reports every N chunks
            chunk_counter = [0]

            def embedding_progress(current: int, total: int) -> None:
                chunk_counter[0] = current
                if current % CHUNK_PROGRESS_INTERVAL == 0 or current == total:
                    report_progress(
                        ProcessingStage.CREATING_EMBEDDINGS,
                        f"Creating embeddings: {current}/{total}",
                        current,
                        total,
                    )

            chunks_created = embedder.chunk_and_embed(
                document_id=document_id,
                overwrite=True,
                progress_callback=embedding_progress,
            )

            report_progress(
                ProcessingStage.COMPLETE,
                f"Created {chunks_created} chunks",
                chunks_created,
                chunks_created,
            )

            return DocumentProcessingResult(
                success=True,
                document_id=document_id,
                content_source=content_source,
                chunks_created=chunks_created,
                full_text=full_text,
                full_text_char_count=len(full_text),
            )

        except Exception as e:
            logger.error(f"Error creating embeddings for {document_id}: {e}")
            return DocumentProcessingResult(
                success=False,
                document_id=document_id,
                content_source=content_source,
                error_message=str(e),
            )

    def _process_pdf(
        self,
        document_id: int,
        pdf_path: Path,
        content_source: ContentSource,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> DocumentProcessingResult:
        """
        Process a PDF file: extract text and create embeddings.

        Args:
            document_id: Document ID.
            pdf_path: Path to PDF file.
            content_source: Source of the PDF.
            progress_callback: Optional progress callback.

        Returns:
            DocumentProcessingResult.
        """
        from bmlibrarian.importers.pdf_ingestor import PDFIngestor

        def report_progress(
            stage: ProcessingStage,
            message: str,
            current: int = 0,
            total: int = 0,
        ) -> None:
            if progress_callback:
                progress_callback(stage, message, current, total)

        try:
            report_progress(
                ProcessingStage.EXTRACTING_TEXT,
                f"Processing PDF: {pdf_path.name}",
                0, 1,
            )

            ingestor = PDFIngestor()

            # Progress wrapper for ingestor
            def ingestor_progress(stage_name: str, current: int, total: int) -> None:
                if stage_name == "storing":
                    report_progress(
                        ProcessingStage.EXTRACTING_TEXT,
                        "Storing PDF...",
                        current, total,
                    )
                elif stage_name == "converting":
                    report_progress(
                        ProcessingStage.EXTRACTING_TEXT,
                        f"Extracting text: {current}/{total}",
                        current, total,
                    )
                elif stage_name == "embedding":
                    if current % CHUNK_PROGRESS_INTERVAL == 0 or current == total:
                        report_progress(
                            ProcessingStage.CREATING_EMBEDDINGS,
                            f"Creating embeddings: {current}/{total}",
                            current, total,
                        )

            result = ingestor.ingest_pdf_immediate(
                document_id=document_id,
                pdf_path=pdf_path,
                progress_callback=ingestor_progress,
            )

            if result.success:
                report_progress(
                    ProcessingStage.COMPLETE,
                    f"Created {result.chunks_created} chunks from PDF",
                    result.chunks_created,
                    result.chunks_created,
                )

                # Get full text from database
                doc_info = self.get_document_info(document_id)
                full_text = doc_info.full_text if doc_info else None

                return DocumentProcessingResult(
                    success=True,
                    document_id=document_id,
                    content_source=content_source,
                    chunks_created=result.chunks_created,
                    pdf_path=pdf_path,
                    full_text=full_text,
                    full_text_char_count=result.char_count,
                    warnings=result.warnings,
                )
            else:
                return DocumentProcessingResult(
                    success=False,
                    document_id=document_id,
                    content_source=content_source,
                    pdf_path=pdf_path,
                    error_message=result.error_message,
                    warnings=result.warnings,
                )

        except Exception as e:
            logger.error(f"Error processing PDF for {document_id}: {e}")
            return DocumentProcessingResult(
                success=False,
                document_id=document_id,
                content_source=content_source,
                pdf_path=pdf_path,
                error_message=str(e),
            )

    def _discover_and_download_pdf(
        self,
        doc_info: DocumentInfo,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> DocumentProcessingResult:
        """
        Discover and download PDF from online sources.

        Args:
            doc_info: Document information.
            progress_callback: Optional progress callback.

        Returns:
            DocumentProcessingResult.
        """
        from bmlibrarian.discovery import FullTextFinder, DocumentIdentifiers

        def report_progress(
            stage: ProcessingStage,
            message: str,
            current: int = 0,
            total: int = 0,
        ) -> None:
            if progress_callback:
                progress_callback(stage, message, current, total)

        try:
            discovery_config = self.config.get('discovery') or {}

            # Create finder
            finder = FullTextFinder(
                unpaywall_email=self.unpaywall_email,
                timeout=int(discovery_config.get('timeout', 30)),
                prefer_open_access=bool(discovery_config.get('prefer_open_access', True)),
            )

            # Build document dictionary for finder
            document = {
                'id': doc_info.id,
                'doi': doc_info.doi,
                'pmid': doc_info.pmid,
                'pdf_url': doc_info.pdf_url,
                'title': doc_info.title,
                'year': doc_info.year,
            }

            # Progress callback wrapper
            def discovery_progress(stage_name: str, status: str) -> None:
                stage_map = {
                    'pmc': ProcessingStage.DISCOVERING_PDF,
                    'unpaywall': ProcessingStage.DISCOVERING_PDF,
                    'doi': ProcessingStage.DISCOVERING_PDF,
                    'crossref_title': ProcessingStage.DISCOVERING_PDF,
                    'download': ProcessingStage.DOWNLOADING_PDF,
                }
                mapped_stage = stage_map.get(stage_name, ProcessingStage.DISCOVERING_PDF)
                report_progress(mapped_stage, f"{stage_name}: {status}", 0, 1)

            # Ensure PDF directory exists
            self.pdf_base_dir.mkdir(parents=True, exist_ok=True)

            # Execute discovery and download
            result = finder.download_for_document(
                document=document,
                output_dir=self.pdf_base_dir,
                use_browser_fallback=discovery_config.get('use_browser_fallback', True),
                progress_callback=discovery_progress,
            )

            # Check if we got NXML full text (preferred) or PDF
            if result.full_text:
                # Got full text from NXML - this is the best case
                report_progress(
                    ProcessingStage.CHECKING_FULL_TEXT,
                    f"Got full text from NXML ({len(result.full_text):,} chars)",
                    1, 1,
                )

                # Update database with full text
                self._update_full_text_in_database(doc_info.id, result.full_text)

                # Also update PDF if we got one
                if result.file_path:
                    self._update_pdf_in_database(doc_info.id, Path(result.file_path), doc_info.year)

                return self._create_embeddings_from_text(
                    document_id=doc_info.id,
                    full_text=result.full_text,
                    content_source=ContentSource.NXML_FULL_TEXT,
                    progress_callback=progress_callback,
                    store_as_full_text=False,  # Already stored above
                )

            elif result.file_path:
                # Got PDF file
                pdf_path = Path(result.file_path)
                report_progress(
                    ProcessingStage.DOWNLOADING_PDF,
                    f"Downloaded PDF: {pdf_path.name}",
                    1, 1,
                )

                # Update database with PDF path
                self._update_pdf_in_database(doc_info.id, pdf_path, doc_info.year)

                return self._process_pdf(
                    document_id=doc_info.id,
                    pdf_path=pdf_path,
                    content_source=ContentSource.DOWNLOADED_PDF,
                    progress_callback=progress_callback,
                )

            else:
                # No content found
                return DocumentProcessingResult(
                    success=False,
                    document_id=doc_info.id,
                    error_message=result.error_message or "No PDF or full text found online",
                )

        except Exception as e:
            logger.error(f"Error during PDF discovery for {doc_info.id}: {e}")
            return DocumentProcessingResult(
                success=False,
                document_id=doc_info.id,
                error_message=str(e),
            )

    def _update_full_text_in_database(self, document_id: int, full_text: str) -> None:
        """Update document full text in database."""
        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE document SET full_text = %s WHERE id = %s",
                        (full_text, document_id),
                    )
                    conn.commit()
                    logger.info(
                        f"Updated full_text for document {document_id} "
                        f"({len(full_text):,} chars)"
                    )
        except Exception as e:
            logger.error(f"Failed to update full_text for {document_id}: {e}")

    def _update_pdf_in_database(
        self,
        document_id: int,
        pdf_path: Path,
        year: Optional[int],
    ) -> None:
        """Update document PDF filename in database."""
        try:
            # Calculate relative path (year/filename.pdf)
            if year:
                relative_path = f"{year}/{pdf_path.name}"
            else:
                relative_path = pdf_path.name

            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE document SET pdf_filename = %s WHERE id = %s",
                        (relative_path, document_id),
                    )
                    conn.commit()
                    logger.info(
                        f"Updated pdf_filename for document {document_id}: {relative_path}"
                    )
        except Exception as e:
            logger.error(f"Failed to update pdf_filename for {document_id}: {e}")


# Convenience function for simple use cases
def process_incoming_document(
    document_id: int,
    progress_callback: Optional[ProgressCallback] = None,
    prompt_callback: Optional[PromptCallback] = None,
) -> DocumentProcessingResult:
    """
    Convenience function to process an incoming document.

    Creates a DocumentProcessor instance and processes the document.

    Args:
        document_id: Database document ID.
        progress_callback: Optional callback for progress updates.
                          Signature: (stage, message, current, total)
        prompt_callback: Optional callback for user prompts.

    Returns:
        DocumentProcessingResult with details of the operation.
    """
    processor = DocumentProcessor()
    return processor.process_document(
        document_id=document_id,
        progress_callback=progress_callback,
        prompt_callback=prompt_callback,
    )


__all__ = [
    'ProcessingStage',
    'ContentSource',
    'DocumentInfo',
    'DocumentProcessingResult',
    'ProgressCallback',
    'PromptCallback',
    'DocumentProcessor',
    'process_incoming_document',
]
