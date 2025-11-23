"""PDF Matcher for BMLibrarian

This module provides functionality to analyze PDF files and match them to existing
documents in the BMLibrarian database using LLM-based metadata extraction.

Example usage:
    from bmlibrarian.importers import PDFMatcher

    matcher = PDFMatcher()
    result = matcher.match_and_import_pdf('/path/to/paper.pdf')

    # Or import entire directory
    results = matcher.match_and_import_directory('/path/to/pdfs/')
"""

import os
import sys
import json
import logging
import re
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime

import ollama

from bmlibrarian.database import get_db_manager
from bmlibrarian.utils.pdf_manager import PDFManager

logger = logging.getLogger(__name__)

# Regex pattern for validating DOI format (basic validation)
# DOIs start with 10. followed by a registrant code and a suffix
DOI_PATTERN = re.compile(r'^10\.\d{4,}/[^\s]+$')

# Regex pattern for validating PMID format (7-8 digit numeric ID)
PMID_PATTERN = re.compile(r'^\d{7,8}$')

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

from dataclasses import dataclass

# Minimum text length for valid extraction
MIN_EXTRACTED_TEXT_LENGTH = 50

# Maximum text length to send to LLM for metadata extraction
# First 3000 chars typically contain all metadata (title, authors, DOI, PMID)
MAX_LLM_TEXT_LENGTH = 3000

# Column index for has_full_text in check_document_status query result
# Query returns: id, title, abstract, authors, doi, pmid, external_id,
#                publication_date, journal, source_id, pdf_filename, pdf_url, has_full_text
_HAS_FULL_TEXT_COLUMN_INDEX = 12


@dataclass
class ExtractedIdentifiers:
    """
    Container for identifiers extracted from PDF text via regex.

    Attributes:
        doi: Digital Object Identifier if found
        pmid: PubMed ID if found
    """

    doi: Optional[str] = None
    pmid: Optional[str] = None

    def has_identifiers(self) -> bool:
        """Check if any identifiers were found."""
        return bool(self.doi or self.pmid)


@dataclass
class DocumentStatus:
    """
    Status information about a document in the database.

    Attributes:
        exists: Whether the document exists in the database
        has_full_text: Whether the document has full_text populated
        has_chunks: Whether the document has been chunked (with default parameters)
        document: The document dictionary if found
    """

    exists: bool = False
    has_full_text: bool = False
    has_chunks: bool = False
    document: Optional[Dict[str, Any]] = None


class PDFMatcher:
    """
    PDF matcher and importer for BMLibrarian.

    Analyzes PDF files to extract metadata using LLM, matches them to existing
    documents in the database, and imports them with proper naming and organization.
    """

    DEFAULT_MODEL = "medgemma4B_it_q8:latest"
    FALLBACK_MODEL = "gpt-oss:20b"

    def __init__(
        self,
        pdf_base_dir: Optional[str] = None,
        ollama_host: Optional[str] = None,
        model: Optional[str] = None
    ):
        """
        Initialize the PDF matcher.

        Args:
            pdf_base_dir: Base directory for PDF storage. If None, uses PDF_BASE_DIR
                         environment variable or defaults to ~/knowledgebase/pdf
            ollama_host: Host URL for Ollama service. If None, uses OLLAMA_HOST
                        environment variable or defaults to localhost:11434
            model: LLM model to use for metadata extraction
        """
        self.db_manager = get_db_manager()
        self.model = model or self.DEFAULT_MODEL

        # Initialize Ollama client with optional custom host
        self.ollama_client = ollama.Client(host=ollama_host) if ollama_host else ollama.Client()

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
            text: Text extracted from PDF

        Returns:
            ExtractedIdentifiers with any found DOI/PMID
        """
        doi = None
        pmid = None

        # DOI patterns - various formats found in papers
        doi_patterns = [
            r'doi[:\s]+\s*(10\.\d{4,}/[^\s\]>]+)',  # doi: 10.xxxx/...
            r'https?://doi\.org/(10\.\d{4,}/[^\s\]>]+)',  # https://doi.org/10.xxxx/...
            r'https?://dx\.doi\.org/(10\.\d{4,}/[^\s\]>]+)',  # https://dx.doi.org/10.xxxx/...
            r'\b(10\.\d{4,}/[^\s\]>\)]+)',  # bare DOI 10.xxxx/...
        ]

        for pattern in doi_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                doi = match.group(1).rstrip('.,;')
                logger.debug(f"Found DOI via regex: {doi}")
                break

        # PMID patterns
        pmid_patterns = [
            r'PMID[:\s]+\s*(\d{7,8})',  # PMID: 12345678
            r'PubMed\s*ID[:\s]+\s*(\d{7,8})',  # PubMed ID: 12345678
            r'pubmed/(\d{7,8})',  # pubmed/12345678
        ]

        for pattern in pmid_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                pmid = match.group(1)
                logger.debug(f"Found PMID via regex: {pmid}")
                break

        return ExtractedIdentifiers(doi=doi, pmid=pmid)

    def quick_database_lookup(
        self,
        doi: Optional[str] = None,
        pmid: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Quick database lookup by exact DOI or PMID match.

        This is the fast path for finding documents when we have extracted
        identifiers via regex. Much faster than LLM-based matching.

        Args:
            doi: DOI to search for
            pmid: PMID to search for

        Returns:
            Document dict if found, None otherwise
        """
        # Validate inputs
        validated_doi = self._validate_doi(doi) if doi else None
        validated_pmid = self._validate_pmid(pmid) if pmid else None

        if not validated_doi and not validated_pmid:
            return None

        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    # Try DOI first (more reliable)
                    if validated_doi:
                        cur.execute(
                            """
                            SELECT id, title, abstract, authors, doi, external_id,
                                   publication_date, publication, source_id
                            FROM document
                            WHERE LOWER(doi) = LOWER(%s)
                            LIMIT 1
                            """,
                            (validated_doi,)
                        )
                        row = cur.fetchone()
                        if row:
                            logger.debug(f"Found document by DOI: {validated_doi}")
                            return self._row_to_quick_lookup_dict(row)

                    # Try PMID (stored in external_id column)
                    if validated_pmid:
                        cur.execute(
                            """
                            SELECT id, title, abstract, authors, doi, external_id,
                                   publication_date, publication, source_id
                            FROM document
                            WHERE external_id = %s
                            LIMIT 1
                            """,
                            (validated_pmid,)
                        )
                        row = cur.fetchone()
                        if row:
                            logger.debug(f"Found document by PMID: {validated_pmid}")
                            return self._row_to_quick_lookup_dict(row)

            return None

        except Exception as e:
            logger.error(f"Error in quick database lookup: {e}")
            return None

    def check_document_status(
        self,
        doi: Optional[str] = None,
        pmid: Optional[str] = None
    ) -> DocumentStatus:
        """
        Check if a document exists in the database and its processing status.

        This method performs a comprehensive check:
        1. Checks if document exists by DOI or PMID
        2. If found, checks if full_text is populated
        3. If full_text exists, checks if document is already chunked

        Args:
            doi: DOI to search for
            pmid: PMID to search for

        Returns:
            DocumentStatus with exists, has_full_text, has_chunks, and document dict
        """
        # Validate inputs - note: we use lenient validation here since
        # identifiers from regex extraction may have slight variations
        validated_doi = self._validate_doi(doi) if doi else None
        validated_pmid = self._validate_pmid(pmid) if pmid else None

        if not validated_doi and not validated_pmid:
            logger.debug(f"check_document_status: no valid identifiers, returning empty status")
            return DocumentStatus()

        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    # Look up document with full_text status
                    if validated_doi:
                        cur.execute(
                            """
                            SELECT id, title, abstract, authors, doi, pmid, external_id,
                                   publication_date, publication as journal, source_id,
                                   pdf_filename, pdf_url,
                                   (full_text IS NOT NULL AND full_text != '') as has_full_text
                            FROM document
                            WHERE LOWER(doi) = LOWER(%s)
                            LIMIT 1
                            """,
                            (validated_doi,)
                        )
                        row = cur.fetchone()
                        if row:
                            logger.info(f"Found document by DOI: {validated_doi}")
                            doc = self._row_to_full_dict(row)
                            has_full_text = row[_HAS_FULL_TEXT_COLUMN_INDEX]

                            # Check chunking status if has full_text
                            has_chunks = False
                            if has_full_text:
                                cur.execute(
                                    "SELECT semantic.has_chunks(%s)",
                                    (doc['id'],)
                                )
                                chunk_result = cur.fetchone()
                                has_chunks = chunk_result[0] if chunk_result else False

                            return DocumentStatus(
                                exists=True,
                                has_full_text=has_full_text,
                                has_chunks=has_chunks,
                                document=doc
                            )

                    # Try PMID (check both pmid and external_id)
                    if validated_pmid:
                        cur.execute(
                            """
                            SELECT id, title, abstract, authors, doi, pmid, external_id,
                                   publication_date, publication as journal, source_id,
                                   pdf_filename, pdf_url,
                                   (full_text IS NOT NULL AND full_text != '') as has_full_text
                            FROM document
                            WHERE pmid = %s OR external_id = %s
                            LIMIT 1
                            """,
                            (validated_pmid, validated_pmid)
                        )
                        row = cur.fetchone()
                        if row:
                            logger.info(f"Found document by PMID: {validated_pmid}")
                            doc = self._row_to_full_dict(row)
                            has_full_text = row[_HAS_FULL_TEXT_COLUMN_INDEX]

                            # Check chunking status if has full_text
                            has_chunks = False
                            if has_full_text:
                                cur.execute(
                                    "SELECT semantic.has_chunks(%s)",
                                    (doc['id'],)
                                )
                                chunk_result = cur.fetchone()
                                has_chunks = chunk_result[0] if chunk_result else False

                            return DocumentStatus(
                                exists=True,
                                has_full_text=has_full_text,
                                has_chunks=has_chunks,
                                document=doc
                            )

            return DocumentStatus()

        except Exception as e:
            logger.error(f"Error checking document status: {e}")
            return DocumentStatus()

    def _row_to_full_dict(self, row: tuple) -> Dict[str, Any]:
        """
        Convert database row to full document dictionary.

        Used by check_document_status() which queries:
        SELECT id, title, abstract, authors, doi, pmid, external_id,
               publication_date, publication as journal, source_id,
               pdf_filename, pdf_url, (full_text IS NOT NULL...) as has_full_text

        Args:
            row: Database row tuple with 12+ columns in order:
                 id, title, abstract, authors, doi, pmid, external_id,
                 publication_date, journal, source_id, pdf_filename, pdf_url
                 (Note: has_full_text at index 12 is handled separately)

        Returns:
            Document dictionary with all relevant fields for status checking
        """
        return {
            'id': row[0],
            'title': row[1],
            'abstract': row[2],
            'authors': row[3] or [],
            'doi': row[4],
            'pmid': row[5],
            'external_id': row[6],
            'publication_date': row[7],
            'journal': row[8],
            'source_id': row[9],
            'pdf_filename': row[10],
            'pdf_url': row[11],
        }

    def extract_metadata_with_llm(self, text: str) -> Dict[str, Any]:
        """
        Use LLM to extract metadata from PDF text.

        Args:
            text: Text from first page of PDF

        Returns:
            Dictionary with extracted metadata (doi, pmid, title, authors)
        """
        # Truncate text to first N characters for efficiency (metadata is on first page)
        truncated_text = text[:MAX_LLM_TEXT_LENGTH] if len(text) > MAX_LLM_TEXT_LENGTH else text

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
            response = self.ollama_client.generate(
                model=self.model,
                prompt=prompt,
                options={
                    "temperature": 0.1,  # Low temperature for factual extraction
                    "top_p": 0.9
                }
            )

            response_text = response.get('response', '').strip()

            # Try to parse JSON from response
            metadata = self._parse_llm_response(response_text)
            logger.debug(f"Extracted metadata: {metadata}")
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

    def _parse_llm_response(self, response_text: str) -> Dict[str, Any]:
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

    def _empty_metadata(self) -> Dict[str, Any]:
        """Return empty metadata structure."""
        return {
            'doi': None,
            'pmid': None,
            'title': None,
            'authors': []
        }

    def _validate_doi(self, doi: Optional[str]) -> Optional[str]:
        """
        Validate and sanitize a DOI string.

        Args:
            doi: DOI string to validate

        Returns:
            Sanitized DOI if valid, None otherwise
        """
        if not doi:
            return None

        # Strip whitespace and normalize
        doi = doi.strip()

        # Basic format validation: DOIs start with 10. followed by registrant code
        if not DOI_PATTERN.match(doi):
            logger.warning(f"Invalid DOI format: {doi}")
            return None

        return doi

    def _validate_pmid(self, pmid: Optional[str]) -> Optional[str]:
        """
        Validate and sanitize a PMID string.

        Args:
            pmid: PMID string to validate

        Returns:
            Sanitized PMID if valid, None otherwise
        """
        if not pmid:
            return None

        # Convert to string and strip whitespace
        pmid = str(pmid).strip()

        # PMID should be 7-8 digit numeric ID
        if not PMID_PATTERN.match(pmid):
            logger.warning(f"Invalid PMID format: {pmid}")
            return None

        return pmid

    def find_matching_document(self, metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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
                # Strategy 1: Exact DOI match (case-insensitive)
                doi = self._validate_doi(metadata.get('doi'))
                if doi:
                    cur.execute(
                        "SELECT id, doi, title, publication_date, pdf_filename, pdf_url, external_id FROM document WHERE LOWER(doi) = LOWER(%s)",
                        (doi,)
                    )
                    result = cur.fetchone()
                    if result:
                        logger.info(f"Found match by DOI: {doi}")
                        return self._row_to_basic_document_dict(result)

                # Strategy 2: Exact PMID match
                pmid = self._validate_pmid(metadata.get('pmid'))
                if pmid:
                    cur.execute(
                        "SELECT id, doi, title, publication_date, pdf_filename, pdf_url, external_id FROM document WHERE external_id = %s",
                        (pmid,)
                    )
                    result = cur.fetchone()
                    if result:
                        logger.info(f"Found match by PMID: {pmid}")
                        return self._row_to_basic_document_dict(result)

                # Strategy 3: Title semantic search (fast - uses HNSW vector index)
                # Note: similarity() is extremely slow without a trigram index on 40M+ documents
                # semantic_docsearch uses ollama_embedding and HNSW index for fast search
                if metadata.get('title'):
                    title = metadata['title'].strip()
                    # Use semantic search for fast title matching
                    # Lower threshold (0.6) since we're matching titles, not full documents
                    cur.execute("""
                        SELECT DISTINCT ON (document_id)
                            document_id as id, doi, title, publication_date,
                            NULL as pdf_filename, NULL as pdf_url, external_id,
                            score as sim
                        FROM semantic_docsearch(%s, 0.6, 10)
                        ORDER BY document_id, score DESC
                    """, (title,))
                    result = cur.fetchone()
                    if result:
                        # Row has 8 columns (id, doi, title, publication_date, pdf_filename, pdf_url, external_id, sim)
                        doc = self._row_to_basic_document_dict(result[:7])  # Take first 7 columns
                        similarity = result[7]
                        logger.info(f"Found match by title similarity ({similarity:.2f}): {doc['title'][:50]}...")
                        return doc

        logger.info("No matching document found in database")
        return None

    def find_alternative_matches(
        self,
        title: str,
        exclude_id: Optional[int] = None,
        max_results: int = 5,
        min_similarity: float = 0.4
    ) -> List[Dict[str, Any]]:
        """
        Find alternative matching documents by title similarity.

        This method is used to provide a list of potential matches when
        the primary match might not be correct, allowing users to select
        the correct document from alternatives.

        Args:
            title: Title to search for
            exclude_id: Document ID to exclude from results (e.g., primary match)
            max_results: Maximum number of alternatives to return
            min_similarity: Minimum similarity score (0.0 to 1.0)

        Returns:
            List of document dictionaries ordered by similarity
        """
        if not title or not title.strip():
            return []

        title = title.strip()

        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    # Use semantic search for fast alternative matching
                    # Note: similarity() is extremely slow without trigram index on 40M+ documents
                    # semantic_docsearch uses HNSW vector index for fast approximate nearest neighbor
                    # Fetch more results to allow for exclusion filtering
                    fetch_limit = max_results * 2 if exclude_id else max_results

                    cur.execute("""
                        SELECT DISTINCT ON (document_id)
                            document_id as id, doi, title, publication_date,
                            NULL as pdf_filename, NULL as pdf_url, external_id,
                            score as sim
                        FROM semantic_docsearch(%s, %s, %s)
                        ORDER BY document_id, score DESC
                    """, (title, min_similarity, fetch_limit))

                    results = []
                    for row in cur.fetchall():
                        # Skip excluded document if specified
                        if exclude_id and row[0] == exclude_id:
                            continue
                        doc = self._row_to_basic_document_dict(row[:7])  # First 7 columns
                        doc['similarity'] = row[7]  # Last column is similarity score
                        results.append(doc)
                        # Stop once we have enough results
                        if len(results) >= max_results:
                            break

                    if results:
                        logger.info(f"Found {len(results)} alternative matches for title")
                    return results

        except Exception as e:
            logger.error(f"Error finding alternative matches: {e}")
            return []

    def _row_to_basic_document_dict(self, row: tuple) -> Dict[str, Any]:
        """
        Convert database row to basic document dictionary.

        Used by find_matching_document() which queries:
        SELECT id, doi, title, publication_date, pdf_filename, pdf_url, external_id

        Args:
            row: Database row tuple with 7 columns in order:
                 id, doi, title, publication_date, pdf_filename, pdf_url, external_id

        Returns:
            Document dictionary with basic fields for PDF import operations
        """
        return {
            'id': row[0],
            'doi': row[1],
            'title': row[2],
            'publication_date': row[3],
            'pdf_filename': row[4],
            'pdf_url': row[5],
            'external_id': row[6]
        }

    def _row_to_quick_lookup_dict(self, row: tuple) -> Dict[str, Any]:
        """
        Convert database row to document dictionary for quick lookup.

        Used by quick_database_lookup() which queries:
        SELECT id, title, abstract, authors, doi, external_id,
               publication_date, publication, source_id

        Args:
            row: Database row tuple with 9 columns in order:
                 id, title, abstract, authors, doi, external_id,
                 publication_date, publication, source_id

        Returns:
            Document dictionary with full metadata from quick lookup
        """
        return {
            'id': row[0],
            'title': row[1],
            'abstract': row[2],
            'authors': row[3] or [],
            'doi': row[4],
            'external_id': row[5],  # PMID stored in external_id
            'publication_date': row[6],
            'publication': row[7],
            'source_id': row[8]
        }

    def import_pdf_for_document(
        self,
        pdf_path: Path,
        document: Dict[str, Any],
        dry_run: bool = False
    ) -> Dict[str, Any]:
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
        logger.debug(f"import_pdf_for_document: doc_id={doc_id}, doi={document.get('doi')}")

        # Generate proper filename from DOI or document ID
        if document.get('doi'):
            safe_doi = document['doi'].replace('/', '_').replace('\\', '_')
            new_filename = f"{safe_doi}.pdf"
        else:
            new_filename = f"doc_{doc_id}.pdf"

        logger.debug(f"import_pdf_for_document: new_filename={new_filename}")

        # Update document dict with new filename
        document['pdf_filename'] = new_filename

        # Get target path (year-based organization)
        logger.debug("import_pdf_for_document: getting db connection for target path")
        with self.db_manager.get_connection() as conn:
            logger.debug("import_pdf_for_document: got db connection, creating PDFManager")
            pdf_manager = PDFManager(base_dir=self.pdf_manager.base_dir, db_conn=conn)
            logger.debug("import_pdf_for_document: calling get_pdf_path")
            target_path = pdf_manager.get_pdf_path(document, create_dirs=not dry_run)
            logger.debug(f"import_pdf_for_document: target_path={target_path}")

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
    ) -> Dict[str, Any]:
        """
        Analyze PDF, match to database, and import if match found.

        Uses a fast-path approach:
        1. Try regex extraction of DOI/PMID from first page (fast, ~100ms)
        2. If identifier found, immediately check database
        3. If document exists in database, use database metadata (skip LLM)
        4. Only fall back to slow LLM extraction if no identifiers found

        Args:
            pdf_path: Path to PDF file
            dry_run: If True, only report what would be done

        Returns:
            Dictionary with complete analysis and import results, including:
            - has_full_text: Whether document has full_text in database
            - has_chunks: Whether document is already chunked/embedded
            - needs_chunking: True if full_text exists but not chunked
        """
        result = {
            'pdf_path': str(pdf_path),
            'pdf_filename': pdf_path.name,
            'status': 'unknown',
            'has_full_text': False,
            'has_chunks': False,
            'needs_chunking': False,
            'match_method': None,  # 'regex_doi', 'regex_pmid', 'llm_doi', 'llm_pmid', 'llm_title'
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

        # ===== FAST PATH: Try regex extraction first =====
        identifiers = self.extract_identifiers_regex(text)
        document = None
        doc_status = None

        if identifiers.has_identifiers():
            logger.info(f"Found identifiers via regex - DOI: {identifiers.doi}, PMID: {identifiers.pmid}")

            # Check database immediately - this is the key optimization
            doc_status = self.check_document_status(
                doi=identifiers.doi,
                pmid=identifiers.pmid
            )

            if doc_status.exists and doc_status.document is not None:
                document = doc_status.document
                result['match_method'] = 'regex_doi' if identifiers.doi else 'regex_pmid'
                result['has_full_text'] = doc_status.has_full_text
                result['has_chunks'] = doc_status.has_chunks
                result['needs_chunking'] = doc_status.has_full_text and not doc_status.has_chunks

                logger.info(
                    f"Found document in database via fast path (DOI/PMID). "
                    f"full_text: {doc_status.has_full_text}, chunked: {doc_status.has_chunks}"
                )

                # Store extracted identifiers as metadata (from regex, not LLM)
                result['metadata'] = {
                    'doi': identifiers.doi,
                    'pmid': identifiers.pmid,
                    'title': document.get('title'),
                    'authors': document.get('authors', []),
                    'source': 'database'  # Metadata came from database, not LLM
                }

        # ===== SLOW PATH: Fall back to LLM extraction if needed =====
        if document is None:
            logger.info("No match via fast path, falling back to LLM extraction...")

            # Extract metadata with LLM
            metadata = self.extract_metadata_with_llm(text)
            result['metadata'] = metadata

            # Check if we got any useful metadata
            if not any([metadata.get('doi'), metadata.get('pmid'), metadata.get('title')]):
                result['status'] = 'no_metadata'
                result['error'] = 'Could not extract DOI, PMID, or title from PDF'
                return result

            # Try database lookup with LLM-extracted identifiers
            if metadata.get('doi') or metadata.get('pmid'):
                doc_status = self.check_document_status(
                    doi=metadata.get('doi'),
                    pmid=metadata.get('pmid')
                )
                if doc_status.exists and doc_status.document is not None:
                    document = doc_status.document
                    result['match_method'] = 'llm_doi' if metadata.get('doi') else 'llm_pmid'
                    result['has_full_text'] = doc_status.has_full_text
                    result['has_chunks'] = doc_status.has_chunks
                    result['needs_chunking'] = doc_status.has_full_text and not doc_status.has_chunks

            # If still no match, try title similarity (original find_matching_document)
            if document is None:
                logger.debug("Trying title similarity match via find_matching_document")
                document = self.find_matching_document(metadata)
                if document:
                    logger.debug(f"Title match found: doc_id={document.get('id')}, doi={document.get('doi')}")
                    result['match_method'] = 'llm_title'
                    # For title match, need to check status separately
                    if document.get('id'):
                        logger.debug(f"Checking document status for title match")
                        title_status = self.check_document_status(doi=document.get('doi'))
                        logger.debug(f"Document status: has_full_text={title_status.has_full_text}, has_chunks={title_status.has_chunks}")
                        result['has_full_text'] = title_status.has_full_text
                        result['has_chunks'] = title_status.has_chunks
                        result['needs_chunking'] = title_status.has_full_text and not title_status.has_chunks

        # No match found at all
        if not document:
            result['status'] = 'no_match'
            result['message'] = 'No matching document found in database'
            return result

        # Build matched document info
        result['matched_document'] = {
            'id': document['id'],
            'doi': document.get('doi'),
            'pmid': document.get('pmid') or document.get('external_id'),
            'title': document.get('title', '')[:100],
            'has_full_text': result['has_full_text'],
            'has_chunks': result['has_chunks'],
        }

        # Import PDF
        logger.debug(f"Starting import_pdf_for_document for doc_id={document.get('id')}")
        import_result = self.import_pdf_for_document(pdf_path, document, dry_run)
        logger.debug(f"Finished import_pdf_for_document, status={import_result.get('status')}")
        result.update(import_result)

        return result

    def match_and_import_directory(
        self,
        directory: Path,
        dry_run: bool = False,
        recursive: bool = False
    ) -> Dict[str, Any]:
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
