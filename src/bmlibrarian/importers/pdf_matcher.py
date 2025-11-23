"""PDF Matcher for BMLibrarian

This module provides functionality to analyze PDF files and match them to existing
documents in the BMLibrarian database using LLM-based metadata extraction.

The module provides a tiered extraction approach:
1. Fast regex extraction for DOI/PMID (~100ms)
2. Quick database lookup by exact identifier match
3. LLM-based metadata extraction (fallback, 5-30s)

Example usage:
    from bmlibrarian.importers import PDFMatcher

    matcher = PDFMatcher()

    # Quick extraction + lookup (fast path)
    text = matcher.extract_first_page_text(pdf_path)
    identifiers = matcher.extract_identifiers_regex(text)
    document = matcher.quick_database_lookup(identifiers.get('doi'), identifiers.get('pmid'))

    if document:
        print(f"Quick match found: {document['title']}")
    else:
        # Fall back to LLM extraction
        metadata = matcher.extract_metadata_with_llm(text)
        document = matcher.find_matching_document(metadata)

    # Or use full workflow
    result = matcher.match_and_import_pdf('/path/to/paper.pdf')

    # Or import entire directory
    results = matcher.match_and_import_directory('/path/to/pdfs/')
"""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import ollama

from bmlibrarian.database import get_db_manager
from bmlibrarian.utils.pdf_manager import PDFManager

logger = logging.getLogger(__name__)

try:
    import pymupdf  # PyMuPDF
except ImportError:
    logger.error("pymupdf not installed. Please install with: uv add pymupdf")
    pymupdf = None

try:
    from tqdm import tqdm
except ImportError:
    logger.warning("tqdm not installed. Progress bars will not be displayed.")
    tqdm = None


# Regex patterns for identifier extraction
# DOI pattern: 10.xxxx/... (standard DOI format)
DOI_PATTERN = re.compile(
    r'(?:doi[:\s]*)?'  # Optional "doi:" or "doi " prefix
    r'(10\.\d{4,}/[^\s\"\'\<\>\]\)]+)',  # DOI: 10.xxxx/anything until whitespace or delimiter
    re.IGNORECASE
)

# PMID patterns: various formats found in papers
PMID_PATTERNS = [
    re.compile(r'PMID[:\s]*(\d{7,8})', re.IGNORECASE),  # PMID: 12345678
    re.compile(r'PubMed\s*ID[:\s]*(\d{7,8})', re.IGNORECASE),  # PubMed ID: 12345678
    re.compile(r'(?:^|\s)PMID(\d{7,8})(?:\s|$)', re.IGNORECASE),  # PMID12345678
]

# Title similarity threshold for database matching
TITLE_SIMILARITY_THRESHOLD_STRICT = 0.6
TITLE_SIMILARITY_THRESHOLD_RELAXED = 0.3
MAX_ALTERNATIVE_MATCHES = 5

# LLM extraction parameters
LLM_TEXT_TRUNCATION_LENGTH = 3000
LLM_TEMPERATURE = 0.1
LLM_TOP_P = 0.9
LLM_TIMEOUT_SECONDS = 60

# Minimum text length for valid extraction
MIN_EXTRACTED_TEXT_LENGTH = 50


@dataclass
class ExtractedIdentifiers:
    """
    Container for identifiers extracted from PDF text.

    Attributes:
        doi: Digital Object Identifier if found
        pmid: PubMed ID if found
        extraction_method: Method used ('regex' or 'llm')
    """

    doi: Optional[str]
    pmid: Optional[str]
    extraction_method: str = "regex"

    def has_identifiers(self) -> bool:
        """Check if any identifiers were extracted."""
        return bool(self.doi or self.pmid)


class PDFMatcher:
    """
    PDF matcher and importer for BMLibrarian.

    Analyzes PDF files to extract metadata using a tiered approach:
    1. Fast regex extraction for DOI/PMID (~100ms)
    2. Quick database lookup by exact identifier match
    3. LLM-based metadata extraction (fallback, 5-30s)

    Matches documents to the database and imports them with proper naming
    and organization.
    """

    DEFAULT_MODEL = "gpt-oss:20b"
    FALLBACK_MODEL = "medgemma4B_it_q8:latest"

    def __init__(
        self,
        pdf_base_dir: Optional[str] = None,
        model: Optional[str] = None
    ):
        """
        Initialize the PDF matcher.

        Args:
            pdf_base_dir: Base directory for PDF storage. If None, uses PDF_BASE_DIR
                         environment variable or defaults to ~/knowledgebase/pdf
            model: LLM model to use for metadata extraction
        """
        self.db_manager = get_db_manager()
        self.model = model or self.DEFAULT_MODEL

        # Initialize PDF manager with database connection
        with self.db_manager.get_connection() as conn:
            self.pdf_manager = PDFManager(base_dir=pdf_base_dir, db_conn=conn)

        logger.info(f"PDF matcher initialized with model: {self.model}")
        logger.info(f"PDF base directory: {self.pdf_manager.base_dir}")

    def extract_first_page_text(self, pdf_path: Path) -> Optional[str]:
        """
        Extract text from the first page of a PDF.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Extracted text or None if failed
        """
        if not pymupdf:
            logger.error("PyMuPDF not available")
            return None

        try:
            doc = pymupdf.open(str(pdf_path))
            if len(doc) == 0:
                logger.warning(f"PDF has no pages: {pdf_path}")
                return None

            # Get first page
            page = doc[0]
            text = page.get_text()
            doc.close()

            if not text or len(text.strip()) < MIN_EXTRACTED_TEXT_LENGTH:
                logger.warning(f"Extracted text too short from {pdf_path}")
                return None

            logger.debug(f"Extracted {len(text)} characters from first page of {pdf_path.name}")
            return text

        except Exception as e:
            logger.error(f"Error extracting text from {pdf_path}: {e}")
            return None

    def extract_identifiers_regex(self, text: str) -> ExtractedIdentifiers:
        """
        Fast regex-based extraction of DOI and PMID from PDF text.

        This is the fast path (~100ms) that should be tried before falling back
        to LLM-based extraction. Looks for common identifier patterns in the text.

        Args:
            text: Text extracted from PDF (typically first page)

        Returns:
            ExtractedIdentifiers with doi and/or pmid if found
        """
        doi: Optional[str] = None
        pmid: Optional[str] = None

        # Try to extract DOI
        doi_match = DOI_PATTERN.search(text)
        if doi_match:
            extracted_doi = doi_match.group(1)
            # Clean up trailing punctuation that might have been captured
            extracted_doi = extracted_doi.rstrip('.,;:')
            doi = extracted_doi
            logger.debug(f"Extracted DOI via regex: {doi}")

        # Try to extract PMID using multiple patterns
        for pattern in PMID_PATTERNS:
            pmid_match = pattern.search(text)
            if pmid_match:
                pmid = pmid_match.group(1)
                logger.debug(f"Extracted PMID via regex: {pmid}")
                break

        identifiers = ExtractedIdentifiers(doi=doi, pmid=pmid, extraction_method="regex")

        if identifiers.has_identifiers():
            logger.info(
                f"Regex extraction found: DOI={doi or 'None'}, PMID={pmid or 'None'}"
            )
        else:
            logger.debug("No identifiers found via regex extraction")

        return identifiers

    def quick_database_lookup(
        self,
        doi: Optional[str] = None,
        pmid: Optional[str] = None
    ) -> Optional[dict[str, any]]:
        """
        Fast database lookup by exact DOI or PMID match.

        This is a quick lookup method (~100ms) that should be used after
        regex extraction before falling back to LLM-based matching.

        Args:
            doi: DOI to search for (optional)
            pmid: PMID to search for (optional)

        Returns:
            Document dictionary if found, None otherwise
        """
        if not doi and not pmid:
            logger.debug("No identifiers provided for quick lookup")
            return None

        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Try DOI first (most specific)
                if doi:
                    cur.execute(
                        """SELECT id, doi, title, publication_date, pdf_filename,
                                  pdf_url, external_id
                           FROM document
                           WHERE doi = %s""",
                        (doi.strip(),)
                    )
                    result = cur.fetchone()
                    if result:
                        logger.info(f"Quick lookup: Found document by DOI: {doi}")
                        return self._row_to_dict(result)

                # Try PMID (stored in external_id field)
                if pmid:
                    cur.execute(
                        """SELECT id, doi, title, publication_date, pdf_filename,
                                  pdf_url, external_id
                           FROM document
                           WHERE external_id = %s""",
                        (str(pmid).strip(),)
                    )
                    result = cur.fetchone()
                    if result:
                        logger.info(f"Quick lookup: Found document by PMID: {pmid}")
                        return self._row_to_dict(result)

        logger.debug(f"Quick lookup: No document found for DOI={doi}, PMID={pmid}")
        return None

    def extract_metadata_with_llm(self, text: str) -> dict[str, any]:
        """
        Use LLM to extract metadata from PDF text.

        This is the slow path (5-30 seconds) that should only be used as a fallback
        when regex extraction fails to find identifiers or when title/authors are needed.

        Uses the ollama Python library for communication (golden rule #4).

        Args:
            text: Text from first page of PDF

        Returns:
            Dictionary with extracted metadata (doi, pmid, title, authors)
        """
        # Truncate text for efficiency
        truncated_text = (
            text[:LLM_TEXT_TRUNCATION_LENGTH]
            if len(text) > LLM_TEXT_TRUNCATION_LENGTH
            else text
        )

        prompt = f"""Analyze this text from the first page of a biomedical research paper and extract the following metadata in JSON format:

1. DOI (Digital Object Identifier) - look for patterns like "10.xxxx/..." or "doi:" followed by the identifier
2. PMID (PubMed ID) - look for "PMID:" or "PubMed ID:" followed by numbers
3. Title - the paper title (usually prominent at top of page)
4. Authors - list of author names (usually appears near title)

Return ONLY a valid JSON object with these fields:
{{
  "doi": "the DOI if found, otherwise null",
  "pmid": "the PMID if found, otherwise null",
  "title": "the paper title if found, otherwise null",
  "authors": ["list", "of", "author", "names"] or []
}}

Important:
- Return ONLY the JSON object, no other text
- Use null for missing values
- For DOI, include the full identifier (e.g., "10.1234/example")
- For PMID, include only the numeric ID
- For title, include the complete title
- For authors, extract as many as clearly visible

Text to analyze:
{truncated_text}
"""

        try:
            # Use ollama library instead of HTTP requests (golden rule #4)
            response = ollama.generate(
                model=self.model,
                prompt=prompt,
                options={
                    "temperature": LLM_TEMPERATURE,
                    "top_p": LLM_TOP_P
                }
            )

            response_text = response.get('response', '').strip()

            # Try to parse JSON from response
            metadata = self._parse_llm_response(response_text)
            logger.debug(f"LLM extracted metadata: {metadata}")
            return metadata

        except ollama.ResponseError as e:
            logger.error(f"Ollama API error: {e}")
            return self._empty_metadata()
        except ConnectionError:
            logger.error("Cannot connect to Ollama service")
            return self._empty_metadata()
        except Exception as e:
            logger.error(f"Error calling LLM: {e}")
            return self._empty_metadata()

    def _parse_llm_response(self, response_text: str) -> dict[str, any]:
        """
        Parse LLM response to extract JSON metadata.

        Args:
            response_text: Raw LLM response

        Returns:
            Parsed metadata dictionary
        """
        try:
            # Try to find JSON in response
            # Look for opening brace
            start_idx = response_text.find('{')
            if start_idx == -1:
                logger.warning("No JSON object found in LLM response")
                return self._empty_metadata()

            # Find matching closing brace
            end_idx = response_text.rfind('}')
            if end_idx == -1:
                logger.warning("No closing brace found in LLM response")
                return self._empty_metadata()

            json_text = response_text[start_idx:end_idx + 1]
            metadata = json.loads(json_text)

            # Validate structure
            return {
                'doi': metadata.get('doi'),
                'pmid': metadata.get('pmid'),
                'title': metadata.get('title'),
                'authors': metadata.get('authors', [])
            }

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from LLM response: {e}")
            logger.debug(f"Response text: {response_text}")
            return self._empty_metadata()

    def _empty_metadata(self) -> dict[str, any]:
        """Return empty metadata structure."""
        return {
            'doi': None,
            'pmid': None,
            'title': None,
            'authors': []
        }

    def find_matching_document(self, metadata: dict[str, any]) -> Optional[dict[str, any]]:
        """
        Find matching document in database using extracted metadata.

        Tries multiple matching strategies in order:
        1. Exact DOI match
        2. Exact PMID match (external_id for PubMed source)
        3. Title similarity match (fuzzy matching)

        Args:
            metadata: Extracted metadata dictionary

        Returns:
            Matching document dictionary or None
        """
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Strategy 1: Exact DOI match
                if metadata.get('doi'):
                    doi = metadata['doi'].strip()
                    cur.execute(
                        "SELECT id, doi, title, publication_date, pdf_filename, pdf_url, external_id FROM document WHERE doi = %s",
                        (doi,)
                    )
                    result = cur.fetchone()
                    if result:
                        logger.info(f"Found match by DOI: {doi}")
                        return self._row_to_dict(result)

                # Strategy 2: Exact PMID match
                if metadata.get('pmid'):
                    pmid = str(metadata['pmid']).strip()
                    cur.execute(
                        "SELECT id, doi, title, publication_date, pdf_filename, pdf_url, external_id FROM document WHERE external_id = %s",
                        (pmid,)
                    )
                    result = cur.fetchone()
                    if result:
                        logger.info(f"Found match by PMID: {pmid}")
                        return self._row_to_dict(result)

                # Strategy 3: Title similarity match
                if metadata.get('title'):
                    title = metadata['title'].strip()
                    # Use PostgreSQL similarity for fuzzy matching
                    cur.execute("""
                        SELECT id, doi, title, publication_date, pdf_filename, pdf_url, external_id,
                               similarity(title, %s) AS sim
                        FROM document
                        WHERE similarity(title, %s) > %s
                        ORDER BY sim DESC
                        LIMIT 1
                    """, (title, title, TITLE_SIMILARITY_THRESHOLD_STRICT))
                    result = cur.fetchone()
                    if result:
                        # Row now has 8 columns (7 original + similarity score)
                        doc = self._row_to_dict(result[:7])  # Take first 7 columns
                        similarity_score = result[7]
                        logger.info(
                            f"Found match by title similarity ({similarity_score:.2f}): "
                            f"{doc['title'][:50]}..."
                        )
                        return doc

        logger.info("No matching document found in database")
        return None

    def _row_to_dict(self, row: tuple) -> dict[str, any]:
        """Convert database row to document dictionary."""
        return {
            'id': row[0],
            'doi': row[1],
            'title': row[2],
            'publication_date': row[3],
            'pdf_filename': row[4],
            'pdf_url': row[5],
            'external_id': row[6]
        }

    def find_alternative_matches(
        self,
        title: str,
        exclude_id: Optional[int] = None
    ) -> list[dict[str, any]]:
        """
        Find alternative document matches by title similarity with relaxed threshold.

        This method is useful for showing the user multiple possible matches
        when exact identifier matching fails or when they want to see alternatives.

        Args:
            title: Title to search for
            exclude_id: Document ID to exclude from results (e.g., already selected)

        Returns:
            List of document dictionaries with similarity scores
        """
        if not title or not title.strip():
            return []

        title = title.strip()

        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                if exclude_id:
                    cur.execute("""
                        SELECT id, doi, title, external_id,
                               EXTRACT(YEAR FROM publication_date) as year,
                               similarity(title, %s) AS sim
                        FROM document
                        WHERE similarity(title, %s) > %s
                          AND id != %s
                        ORDER BY sim DESC
                        LIMIT %s
                    """, (title, title, TITLE_SIMILARITY_THRESHOLD_RELAXED,
                          exclude_id, MAX_ALTERNATIVE_MATCHES))
                else:
                    cur.execute("""
                        SELECT id, doi, title, external_id,
                               EXTRACT(YEAR FROM publication_date) as year,
                               similarity(title, %s) AS sim
                        FROM document
                        WHERE similarity(title, %s) > %s
                        ORDER BY sim DESC
                        LIMIT %s
                    """, (title, title, TITLE_SIMILARITY_THRESHOLD_RELAXED,
                          MAX_ALTERNATIVE_MATCHES))

                results = cur.fetchall()

                alternatives = []
                for row in results:
                    alternatives.append({
                        'id': row[0],
                        'doi': row[1],
                        'title': row[2],
                        'external_id': row[3],
                        'year': int(row[4]) if row[4] else None,
                        'similarity': float(row[5])
                    })

                logger.debug(
                    f"Found {len(alternatives)} alternative matches for title: "
                    f"{title[:50]}..."
                )
                return alternatives

    def import_pdf_for_document(
        self,
        pdf_path: Path,
        document: dict[str, any],
        dry_run: bool = False
    ) -> dict[str, any]:
        """
        Import PDF file for a matched document.

        Renames and moves the PDF to the correct location according to naming
        conventions, and updates the database.

        Args:
            pdf_path: Path to source PDF file
            document: Matched document dictionary
            dry_run: If True, only report what would be done

        Returns:
            Dictionary with import result details
        """
        doc_id = document['id']

        # Generate proper filename from DOI or document ID
        if document.get('doi'):
            safe_doi = document['doi'].replace('/', '_').replace('\\', '_')
            new_filename = f"{safe_doi}.pdf"
        else:
            new_filename = f"doc_{doc_id}.pdf"

        # Update document dict with new filename
        document['pdf_filename'] = new_filename

        # Get target path (year-based organization)
        with self.db_manager.get_connection() as conn:
            pdf_manager = PDFManager(base_dir=self.pdf_manager.base_dir, db_conn=conn)
            target_path = pdf_manager.get_pdf_path(document, create_dirs=not dry_run)

        if not target_path:
            return {
                'status': 'failed',
                'reason': 'Could not determine target path',
                'doc_id': doc_id
            }

        # Check if PDF already exists at target
        if target_path.exists():
            # Compare file sizes and dates
            source_size = pdf_path.stat().st_size
            target_size = target_path.stat().st_size
            source_mtime = pdf_path.stat().st_mtime
            target_mtime = target_path.stat().st_mtime

            if pdf_path.resolve() == target_path.resolve():
                return {
                    'status': 'already_exists',
                    'message': 'PDF already at correct location',
                    'doc_id': doc_id,
                    'path': str(target_path)
                }

            if source_size == target_size:
                return {
                    'status': 'duplicate',
                    'message': 'PDF already exists with same size',
                    'doc_id': doc_id,
                    'existing_path': str(target_path)
                }

            # Different files - prefer newer one
            if source_mtime > target_mtime:
                logger.warning(f"Source PDF is newer than existing - will replace")
                if not dry_run:
                    target_path.unlink()
            else:
                return {
                    'status': 'skipped',
                    'reason': 'Existing PDF is newer',
                    'doc_id': doc_id,
                    'existing_path': str(target_path)
                }

        if dry_run:
            return {
                'status': 'would_import',
                'doc_id': doc_id,
                'source': str(pdf_path),
                'target': str(target_path),
                'filename': new_filename
            }

        # Actually perform import
        try:
            import shutil

            # Ensure target directory exists
            target_path.parent.mkdir(parents=True, exist_ok=True)

            # Copy file (don't move in case of errors)
            shutil.copy2(str(pdf_path), str(target_path))
            logger.info(f"Copied PDF: {pdf_path} -> {target_path}")

            # Update database
            relative_path = pdf_manager.get_relative_pdf_path(document)
            with self.db_manager.get_connection() as conn:
                pdf_manager_with_conn = PDFManager(base_dir=self.pdf_manager.base_dir, db_conn=conn)
                success = pdf_manager_with_conn.update_database_pdf_path(doc_id, relative_path)

            if not success:
                # Rollback - delete copied file
                target_path.unlink()
                return {
                    'status': 'failed',
                    'reason': 'Database update failed',
                    'doc_id': doc_id
                }

            return {
                'status': 'imported',
                'doc_id': doc_id,
                'source': str(pdf_path),
                'target': str(target_path),
                'filename': new_filename,
                'doi': document.get('doi'),
                'title': document.get('title', '')[:100]
            }

        except Exception as e:
            logger.error(f"Error importing PDF: {e}")
            return {
                'status': 'failed',
                'reason': str(e),
                'doc_id': doc_id
            }

    def match_and_import_pdf(
        self,
        pdf_path: Path,
        dry_run: bool = False
    ) -> dict[str, any]:
        """
        Analyze PDF, match to database, and import if match found.

        Args:
            pdf_path: Path to PDF file
            dry_run: If True, only report what would be done

        Returns:
            Dictionary with complete analysis and import results
        """
        result = {
            'pdf_path': str(pdf_path),
            'pdf_filename': pdf_path.name,
            'status': 'unknown'
        }

        # Check file exists
        if not pdf_path.exists():
            result['status'] = 'not_found'
            result['error'] = 'File not found'
            return result

        # Extract text from first page
        logger.info(f"Analyzing PDF: {pdf_path.name}")
        text = self.extract_first_page_text(pdf_path)
        if not text:
            result['status'] = 'extraction_failed'
            result['error'] = 'Could not extract text from PDF'
            return result

        # Extract metadata with LLM
        metadata = self.extract_metadata_with_llm(text)
        result['metadata'] = metadata

        # Check if we got any useful metadata
        if not any([metadata.get('doi'), metadata.get('pmid'), metadata.get('title')]):
            result['status'] = 'no_metadata'
            result['error'] = 'Could not extract DOI, PMID, or title from PDF'
            return result

        # Find matching document
        document = self.find_matching_document(metadata)
        if not document:
            result['status'] = 'no_match'
            result['message'] = 'No matching document found in database'
            return result

        result['matched_document'] = {
            'id': document['id'],
            'doi': document.get('doi'),
            'pmid': document.get('external_id'),
            'title': document.get('title', '')[:100]
        }

        # Import PDF
        import_result = self.import_pdf_for_document(pdf_path, document, dry_run)
        result.update(import_result)

        return result

    def match_and_import_directory(
        self,
        directory: Path,
        dry_run: bool = False,
        recursive: bool = False
    ) -> dict[str, any]:
        """
        Process all PDF files in a directory.

        Args:
            directory: Directory containing PDF files
            dry_run: If True, only report what would be done
            recursive: If True, search subdirectories

        Returns:
            Dictionary with batch processing statistics
        """
        if not directory.exists():
            logger.error(f"Directory not found: {directory}")
            return {
                'error': f'Directory not found: {directory}',
                'total': 0
            }

        # Find all PDF files
        if recursive:
            pdf_files = list(directory.rglob('*.pdf'))
        else:
            pdf_files = list(directory.glob('*.pdf'))

        stats = {
            'total': len(pdf_files),
            'imported': 0,
            'no_match': 0,
            'already_exists': 0,
            'failed': 0,
            'skipped': 0,
            'details': []
        }

        logger.info(f"Found {stats['total']} PDF files in {directory}")

        # Process each PDF
        if tqdm:
            progress = tqdm(pdf_files, desc="Processing PDFs", unit="file")
        else:
            progress = pdf_files

        for pdf_file in progress:
            if tqdm:
                progress.set_description(f"Processing {pdf_file.name[:30]}")

            result = self.match_and_import_pdf(pdf_file, dry_run)

            # Update statistics
            status = result.get('status', 'unknown')
            if status == 'imported':
                stats['imported'] += 1
            elif status == 'no_match':
                stats['no_match'] += 1
            elif status in ['already_exists', 'duplicate']:
                stats['already_exists'] += 1
            elif status == 'skipped':
                stats['skipped'] += 1
            else:
                stats['failed'] += 1

            stats['details'].append(result)

        logger.info(f"Batch processing complete: {stats['imported']} imported, "
                   f"{stats['no_match']} no match, {stats['failed']} failed")

        return stats
