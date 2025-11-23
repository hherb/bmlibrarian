"""
PDF Ingestor for BMLibrarian.

Handles the complete workflow for ingesting PDFs into the system:
1. Store PDF according to naming conventions
2. Convert PDF to text
3. Store full_text in document table
4. Chunk and embed the full text

Supports both async (queue-based) and immediate (synchronous) processing.

Example usage:
    from bmlibrarian.importers.pdf_ingestor import PDFIngestor, IngestResult

    ingestor = PDFIngestor()

    # Immediate processing (for GUI)
    result = ingestor.ingest_pdf_immediate(
        document_id=12345,
        pdf_path=Path("/path/to/paper.pdf"),
        progress_callback=lambda stage, cur, tot: print(f"{stage}: {cur}/{tot}")
    )

    if result.success:
        print(f"Created {result.chunks_created} chunks")

    # Or just ingest without immediate embedding (will be queued)
    result = ingestor.ingest_pdf(document_id=12345, pdf_path=Path("/path/to/paper.pdf"))
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List

from bmlibrarian.database import get_db_manager
from bmlibrarian.importers.pdf_converter import (
    get_converter,
    ConversionResult,
    DEFAULT_CONVERTER,
)
from bmlibrarian.embeddings.chunk_embedder import (
    ChunkEmbedder,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_CHUNK_OVERLAP,
)

logger = logging.getLogger(__name__)

# Environment variable for PDF base directory
ENV_PDF_BASE_DIR = "PDF_BASE_DIR"
DEFAULT_PDF_BASE_DIR = "~/knowledgebase/pdf"


@dataclass
class IngestResult:
    """
    Result of PDF ingestion.

    Attributes:
        success: Whether ingestion completed successfully.
        document_id: Database document ID.
        pdf_stored: Whether PDF was stored to filesystem.
        pdf_path: Path where PDF was stored (if stored).
        text_extracted: Whether text was extracted from PDF.
        full_text_stored: Whether full_text was stored in database.
        chunks_created: Number of chunks created (0 if not embedded).
        char_count: Character count of extracted text.
        page_count: Number of pages in PDF.
        warnings: List of non-fatal warnings during processing.
        error_message: Error message if success=False.
        conversion_result: Raw ConversionResult from PDF converter.
    """

    success: bool
    document_id: int
    pdf_stored: bool = False
    pdf_path: Optional[Path] = None
    text_extracted: bool = False
    full_text_stored: bool = False
    chunks_created: int = 0
    char_count: int = 0
    page_count: int = 0
    warnings: List[str] = field(default_factory=list)
    error_message: Optional[str] = None
    conversion_result: Optional[ConversionResult] = None

    def __str__(self) -> str:
        """Return human-readable summary."""
        status = "SUCCESS" if self.success else "FAILED"
        return (
            f"IngestResult({status}, doc_id={self.document_id}, "
            f"chunks={self.chunks_created}, chars={self.char_count})"
        )


class PDFIngestor:
    """
    Handles PDF ingestion including storage, text extraction, and embedding.

    Integrates with PDFManager for storage conventions, PDF converters for
    text extraction, and ChunkEmbedder for embedding generation.
    """

    def __init__(
        self,
        pdf_base_dir: Optional[str] = None,
        converter_name: str = DEFAULT_CONVERTER,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    ) -> None:
        """
        Initialize the PDF ingestor.

        Args:
            pdf_base_dir: Base directory for PDF storage.
                         If None, uses PDF_BASE_DIR environment variable.
            converter_name: Name of PDF converter to use (default: "pymupdf").
            chunk_size: Default chunk size for text chunking.
            chunk_overlap: Default overlap between chunks.
        """
        self.db_manager = get_db_manager()

        # Initialize PDF base directory
        if pdf_base_dir is None:
            pdf_base_dir = os.getenv(ENV_PDF_BASE_DIR, DEFAULT_PDF_BASE_DIR)
        self.pdf_base_dir = Path(pdf_base_dir).expanduser()

        # Initialize converter
        self.converter_name = converter_name
        self._converter = None  # Lazy initialization

        # Chunking parameters
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        # Embedder (lazy initialization)
        self._embedder: Optional[ChunkEmbedder] = None

        logger.info(
            f"PDFIngestor initialized: base_dir={self.pdf_base_dir}, "
            f"converter={converter_name}"
        )

    @property
    def converter(self):
        """Lazy-load the PDF converter."""
        if self._converter is None:
            self._converter = get_converter(self.converter_name)
        return self._converter

    @property
    def embedder(self) -> ChunkEmbedder:
        """Lazy-load the chunk embedder."""
        if self._embedder is None:
            self._embedder = ChunkEmbedder()
        return self._embedder

    def get_document(self, document_id: int) -> Optional[Dict[str, Any]]:
        """
        Fetch document from database.

        Args:
            document_id: Document database ID.

        Returns:
            Document dict or None if not found.
        """
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, doi, title, publication_date, pdf_filename,
                           pdf_url, full_text, external_id
                    FROM public.document
                    WHERE id = %s
                    """,
                    (document_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None

                return {
                    "id": row[0],
                    "doi": row[1],
                    "title": row[2],
                    "publication_date": row[3],
                    "pdf_filename": row[4],
                    "pdf_url": row[5],
                    "full_text": row[6],
                    "external_id": row[7],
                }

    def _get_year_from_document(self, document: Dict[str, Any]) -> str:
        """
        Extract year from document for directory organization.

        Args:
            document: Document dict with publication_date.

        Returns:
            Year string or "unknown" if not available.
        """
        pub_date = document.get("publication_date")
        if pub_date:
            if hasattr(pub_date, "year"):
                return str(pub_date.year)
            # Try parsing string
            try:
                from datetime import datetime

                if isinstance(pub_date, str):
                    parsed = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                    return str(parsed.year)
            except (ValueError, TypeError):
                pass
        return "unknown"

    def _generate_pdf_filename(self, document: Dict[str, Any]) -> str:
        """
        Generate PDF filename based on document metadata.

        Uses DOI (sanitized) or document ID as filename.

        Args:
            document: Document dict.

        Returns:
            Generated filename (without path).
        """
        doi = document.get("doi")
        if doi:
            # Sanitize DOI for filename (replace / with _)
            safe_doi = doi.replace("/", "_").replace(":", "_")
            return f"{safe_doi}.pdf"

        # Fallback to document ID
        return f"doc_{document['id']}.pdf"

    def _get_pdf_storage_path(
        self, document: Dict[str, Any], create_dirs: bool = False
    ) -> Path:
        """
        Get the storage path for a PDF following naming conventions.

        Structure: {base_dir}/{year}/{filename}

        Args:
            document: Document dict.
            create_dirs: If True, create directories if they don't exist.

        Returns:
            Full path for PDF storage.
        """
        year = self._get_year_from_document(document)
        year_dir = self.pdf_base_dir / year

        if create_dirs:
            year_dir.mkdir(parents=True, exist_ok=True)

        # Use existing pdf_filename or generate one
        filename = document.get("pdf_filename")
        if filename:
            # If filename includes path, extract just the filename
            filename = Path(filename).name
        else:
            filename = self._generate_pdf_filename(document)

        return year_dir / filename

    def _store_pdf(
        self, source_path: Path, document: Dict[str, Any]
    ) -> Optional[Path]:
        """
        Copy PDF to storage location following naming conventions.

        Args:
            source_path: Path to source PDF file.
            document: Document dict.

        Returns:
            Destination path if successful, None otherwise.
        """
        import shutil

        dest_path = self._get_pdf_storage_path(document, create_dirs=True)

        try:
            # Don't copy if source and destination are the same
            if source_path.resolve() == dest_path.resolve():
                logger.debug(f"PDF already at destination: {dest_path}")
                return dest_path

            shutil.copy2(source_path, dest_path)
            logger.info(f"Stored PDF at: {dest_path}")
            return dest_path

        except Exception as e:
            logger.error(f"Failed to store PDF: {e}")
            return None

    def _update_document_full_text(
        self, document_id: int, full_text: str, pdf_filename: str
    ) -> bool:
        """
        Update document with full_text and pdf_filename.

        Args:
            document_id: Document database ID.
            full_text: Extracted text content.
            pdf_filename: Relative path to stored PDF.

        Returns:
            True if update successful, False otherwise.
        """
        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE public.document
                        SET full_text = %s,
                            pdf_filename = %s,
                            updated_date = CURRENT_TIMESTAMP
                        WHERE id = %s
                        """,
                        (full_text, pdf_filename, document_id),
                    )
                    logger.info(
                        f"Updated document {document_id} with full_text "
                        f"({len(full_text)} chars)"
                    )
                    return True

        except Exception as e:
            logger.error(f"Failed to update document {document_id}: {e}")
            return False

    def _get_relative_pdf_path(self, full_path: Path) -> str:
        """
        Get PDF path relative to base directory for database storage.

        Args:
            full_path: Full path to PDF.

        Returns:
            Relative path string (e.g., "2023/paper.pdf").
        """
        try:
            return str(full_path.relative_to(self.pdf_base_dir))
        except ValueError:
            # Not relative to base dir, return filename only
            return full_path.name

    def ingest_pdf(
        self,
        document_id: int,
        pdf_path: Path,
        store_pdf: bool = True,
        extract_text: bool = True,
        store_full_text: bool = True,
    ) -> IngestResult:
        """
        Ingest a PDF for a document (text extraction only, no embedding).

        This method stores the PDF, extracts text, and updates the database.
        Embedding will be handled by the async queue/background worker.

        Args:
            document_id: Database document ID.
            pdf_path: Path to the PDF file.
            store_pdf: If True, copy PDF to storage location.
            extract_text: If True, extract text from PDF.
            store_full_text: If True, store extracted text in database.

        Returns:
            IngestResult with details of the operation.
        """
        warnings: List[str] = []

        # Validate PDF path
        if not pdf_path.exists():
            return IngestResult(
                success=False,
                document_id=document_id,
                error_message=f"PDF file not found: {pdf_path}",
            )

        # Get document from database
        document = self.get_document(document_id)
        if not document:
            return IngestResult(
                success=False,
                document_id=document_id,
                error_message=f"Document not found in database: {document_id}",
            )

        result = IngestResult(success=True, document_id=document_id)

        # Step 1: Store PDF
        stored_path: Optional[Path] = None
        if store_pdf:
            stored_path = self._store_pdf(pdf_path, document)
            if stored_path:
                result.pdf_stored = True
                result.pdf_path = stored_path
            else:
                warnings.append("Failed to store PDF to standard location")

        # Step 2: Extract text
        conversion_result: Optional[ConversionResult] = None
        if extract_text:
            try:
                conversion_result = self.converter.convert(pdf_path)
                result.conversion_result = conversion_result

                if conversion_result.success:
                    result.text_extracted = True
                    result.char_count = conversion_result.char_count
                    result.page_count = conversion_result.page_count

                    if conversion_result.warnings:
                        warnings.extend(conversion_result.warnings)

                    if not conversion_result.is_complete:
                        warnings.append(
                            f"Incomplete conversion: {conversion_result.converted_pages}/"
                            f"{conversion_result.page_count} pages"
                        )
                else:
                    warnings.append(
                        f"Text extraction failed: {conversion_result.error_message}"
                    )
                    result.success = False
                    result.error_message = conversion_result.error_message

            except Exception as e:
                error_msg = f"Text extraction error: {e}"
                logger.error(error_msg)
                warnings.append(error_msg)
                result.success = False
                result.error_message = error_msg

        # Step 3: Store full_text in database
        if store_full_text and conversion_result and conversion_result.success:
            # Determine pdf_filename for database
            pdf_filename = ""
            if stored_path:
                pdf_filename = self._get_relative_pdf_path(stored_path)
            elif document.get("pdf_filename"):
                pdf_filename = document["pdf_filename"]

            if self._update_document_full_text(
                document_id, conversion_result.text, pdf_filename
            ):
                result.full_text_stored = True
            else:
                warnings.append("Failed to store full_text in database")

        result.warnings = warnings
        return result

    def ingest_pdf_immediate(
        self,
        document_id: int,
        pdf_path: Path,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> IngestResult:
        """
        Ingest PDF with immediate (synchronous) embedding.

        This is the GUI path - processes everything immediately without
        using the background queue.

        Args:
            document_id: Database document ID.
            pdf_path: Path to the PDF file.
            chunk_size: Chunk size for embedding (uses default if None).
            chunk_overlap: Chunk overlap for embedding (uses default if None).
            progress_callback: Optional callback(stage, current, total) for progress.
                              Stages: "storing", "converting", "embedding"

        Returns:
            IngestResult with complete details including chunks created.
        """
        chunk_size = chunk_size or self.chunk_size
        chunk_overlap = chunk_overlap or self.chunk_overlap

        # Report progress: storing
        if progress_callback:
            progress_callback("storing", 0, 1)

        # First do basic ingestion (store, extract, update DB)
        result = self.ingest_pdf(
            document_id=document_id,
            pdf_path=pdf_path,
            store_pdf=True,
            extract_text=True,
            store_full_text=True,
        )

        if progress_callback:
            progress_callback("storing", 1, 1)

        if not result.success or not result.full_text_stored:
            return result

        # Report progress: embedding
        if progress_callback:
            progress_callback("embedding", 0, 1)

        # Now do immediate embedding
        try:
            # Create embedder progress callback wrapper
            def embedding_progress(current: int, total: int) -> None:
                if progress_callback:
                    progress_callback("embedding", current, total)

            chunks_created = self.embedder.chunk_and_embed(
                document_id=document_id,
                chunk_size=chunk_size,
                overlap=chunk_overlap,
                overwrite=True,
                progress_callback=embedding_progress,
            )

            result.chunks_created = chunks_created

            if chunks_created == 0:
                result.warnings.append("No chunks created during embedding")

        except Exception as e:
            error_msg = f"Embedding failed: {e}"
            logger.error(error_msg)
            result.warnings.append(error_msg)
            # Don't mark as failed - text extraction succeeded

        return result

    def ingest_from_text(
        self,
        document_id: int,
        text: str,
        immediate_embed: bool = False,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> IngestResult:
        """
        Ingest full text directly (without PDF).

        Useful when text is already available (e.g., from another source).

        Args:
            document_id: Database document ID.
            text: Full text content.
            immediate_embed: If True, embed immediately. Otherwise queued.
            progress_callback: Optional callback for progress (if immediate_embed).

        Returns:
            IngestResult with details.
        """
        # Validate
        if not text or not text.strip():
            return IngestResult(
                success=False,
                document_id=document_id,
                error_message="Text is empty",
            )

        # Get document
        document = self.get_document(document_id)
        if not document:
            return IngestResult(
                success=False,
                document_id=document_id,
                error_message=f"Document not found: {document_id}",
            )

        result = IngestResult(
            success=True,
            document_id=document_id,
            text_extracted=True,
            char_count=len(text),
        )

        # Store full_text
        pdf_filename = document.get("pdf_filename", "")
        if self._update_document_full_text(document_id, text, pdf_filename):
            result.full_text_stored = True
        else:
            result.warnings.append("Failed to store full_text")
            result.success = False
            return result

        # Embed if requested
        if immediate_embed:
            if progress_callback:
                progress_callback("embedding", 0, 1)

            try:
                def embedding_progress(current: int, total: int) -> None:
                    if progress_callback:
                        progress_callback("embedding", current, total)

                chunks_created = self.embedder.chunk_and_embed(
                    document_id=document_id,
                    chunk_size=self.chunk_size,
                    overlap=self.chunk_overlap,
                    overwrite=True,
                    progress_callback=embedding_progress,
                )
                result.chunks_created = chunks_created

            except Exception as e:
                logger.error(f"Embedding failed: {e}")
                result.warnings.append(f"Embedding failed: {e}")

        return result
