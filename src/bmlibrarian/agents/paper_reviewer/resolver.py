"""
Document Resolver for Paper Reviewer

Resolves paper identifiers (DOI, PMID, PDF, text) to document dictionaries.

Resolution priority:
1. Local database (fastest, most complete metadata)
2. Web fetch (DOI.org, PubMed API, CrossRef)
"""

import logging
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

import requests

from .models import SourceType

logger = logging.getLogger(__name__)


# Constants
REQUEST_TIMEOUT = 30  # seconds
PUBMED_EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
CROSSREF_API_URL = "https://api.crossref.org/works"
DOI_ORG_URL = "https://doi.org"

# User agent for API requests
USER_AGENT = "BMLibrarian/1.0 (Paper Reviewer; mailto:contact@bmlibrarian.org)"


class DocumentResolver:
    """
    Resolves paper identifiers to document dictionaries.

    Supports:
    - DOI: Local DB lookup, then CrossRef/DOI.org API
    - PMID: Local DB lookup, then PubMed E-utilities API
    - PDF: Extract text using pdf_processor
    - Text: Parse markdown/plain text files or raw text
    """

    def __init__(
        self,
        ncbi_email: Optional[str] = None,
        ncbi_api_key: Optional[str] = None,
        crossref_email: Optional[str] = None,
    ):
        """
        Initialize the document resolver.

        Args:
            ncbi_email: Email for NCBI API (recommended)
            ncbi_api_key: NCBI API key for higher rate limits
            crossref_email: Email for CrossRef polite pool
        """
        self.ncbi_email = ncbi_email
        self.ncbi_api_key = ncbi_api_key
        self.crossref_email = crossref_email

        # Rate limiting
        self._last_pubmed_request = 0.0
        self._last_crossref_request = 0.0
        self._pubmed_delay = 0.1 if ncbi_api_key else 0.34  # 10/s with key, 3/s without
        self._crossref_delay = 0.05  # 20/s for polite pool

    def resolve(
        self,
        doi: Optional[str] = None,
        pmid: Optional[str] = None,
        pdf_path: Optional[Path] = None,
        text: Optional[str] = None,
        text_file: Optional[Path] = None,
        prefer_local: bool = True,
    ) -> Tuple[Dict[str, Any], SourceType]:
        """
        Resolve any input to a document dictionary.

        Exactly one of doi, pmid, pdf_path, text, or text_file must be provided.

        Args:
            doi: DOI to resolve
            pmid: PubMed ID to resolve
            pdf_path: Path to PDF file
            text: Raw text content
            text_file: Path to text/markdown file
            prefer_local: Try local database first (default True)

        Returns:
            Tuple of (document_dict, source_type)

        Raises:
            ValueError: If no input provided or multiple inputs provided
            FileNotFoundError: If PDF or text file not found
            RuntimeError: If resolution fails
        """
        # Validate inputs - exactly one must be provided
        inputs = [doi, pmid, pdf_path, text, text_file]
        provided = [x for x in inputs if x is not None]
        if len(provided) != 1:
            raise ValueError(
                "Exactly one of doi, pmid, pdf_path, text, or text_file must be provided"
            )

        if doi:
            return self.resolve_doi(doi, prefer_local=prefer_local)
        elif pmid:
            return self.resolve_pmid(pmid, prefer_local=prefer_local)
        elif pdf_path:
            return self.resolve_pdf(pdf_path)
        elif text_file:
            return self.resolve_text_file(text_file)
        else:
            return self.resolve_text(text)

    def resolve_doi(
        self, doi: str, prefer_local: bool = True
    ) -> Tuple[Dict[str, Any], SourceType]:
        """
        Resolve DOI to document dictionary.

        Args:
            doi: DOI to resolve (with or without doi.org prefix)
            prefer_local: Try local database first

        Returns:
            Tuple of (document_dict, source_type)
        """
        # Normalize DOI
        doi = self._normalize_doi(doi)
        logger.info(f"Resolving DOI: {doi}")

        # Try local database first
        if prefer_local:
            doc = self._search_local_by_doi(doi)
            if doc:
                logger.info(f"Found DOI {doi} in local database (id={doc.get('id')})")
                return doc, SourceType.DATABASE

        # Fetch from web
        logger.info(f"DOI {doi} not in local database, fetching from CrossRef")
        doc = self._fetch_from_crossref(doi)
        if doc:
            return doc, SourceType.DOI_FETCH

        raise RuntimeError(f"Could not resolve DOI: {doi}")

    def resolve_pmid(
        self, pmid: str, prefer_local: bool = True
    ) -> Tuple[Dict[str, Any], SourceType]:
        """
        Resolve PMID to document dictionary.

        Args:
            pmid: PubMed ID to resolve
            prefer_local: Try local database first

        Returns:
            Tuple of (document_dict, source_type)
        """
        # Normalize PMID
        pmid = self._normalize_pmid(pmid)
        logger.info(f"Resolving PMID: {pmid}")

        # Try local database first
        if prefer_local:
            doc = self._search_local_by_pmid(pmid)
            if doc:
                logger.info(f"Found PMID {pmid} in local database (id={doc.get('id')})")
                return doc, SourceType.DATABASE

        # Fetch from PubMed
        logger.info(f"PMID {pmid} not in local database, fetching from PubMed")
        doc = self._fetch_from_pubmed(pmid)
        if doc:
            return doc, SourceType.PMID_FETCH

        raise RuntimeError(f"Could not resolve PMID: {pmid}")

    def resolve_pdf(self, pdf_path: Path) -> Tuple[Dict[str, Any], SourceType]:
        """
        Extract document from PDF file.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Tuple of (document_dict, source_type)
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        logger.info(f"Processing PDF: {pdf_path}")

        try:
            from bmlibrarian.pdf_processor import PDFExtractor, SectionSegmenter

            # Extract text from PDF
            extractor = PDFExtractor()
            text_blocks = extractor.extract(pdf_path)

            # Segment into sections
            segmenter = SectionSegmenter()
            document = segmenter.segment(text_blocks)

            # Build document dict
            doc = self._pdf_document_to_dict(document, pdf_path)

            # Try to find in local database by DOI if extracted
            if doc.get('doi'):
                local_doc = self._search_local_by_doi(doc['doi'])
                if local_doc:
                    # Merge PDF content with database metadata
                    local_doc['full_text'] = doc.get('full_text', '')
                    local_doc['pdf_path'] = str(pdf_path)
                    logger.info(f"Matched PDF to database record (id={local_doc.get('id')})")
                    return local_doc, SourceType.DATABASE

            return doc, SourceType.PDF

        except ImportError as e:
            logger.error(f"pdf_processor not available: {e}")
            raise RuntimeError("PDF processing requires pdf_processor module") from e
        except Exception as e:
            logger.error(f"Error processing PDF: {e}")
            raise RuntimeError(f"Failed to process PDF: {e}") from e

    def resolve_text_file(self, file_path: Path) -> Tuple[Dict[str, Any], SourceType]:
        """
        Process text or markdown file.

        Args:
            file_path: Path to text file

        Returns:
            Tuple of (document_dict, source_type)
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        logger.info(f"Processing text file: {file_path}")

        content = file_path.read_text(encoding='utf-8')

        # Check if markdown with front matter
        doc = self._parse_markdown_file(content, file_path)

        return doc, SourceType.FILE

    def resolve_text(self, text: str) -> Tuple[Dict[str, Any], SourceType]:
        """
        Process raw text content.

        Args:
            text: Raw text (abstract or full text)

        Returns:
            Tuple of (document_dict, source_type)
        """
        logger.info(f"Processing raw text ({len(text)} characters)")

        doc = {
            'id': None,
            'title': 'User-provided text',
            'authors': [],
            'year': None,
            'journal': None,
            'doi': None,
            'pmid': None,
            'abstract': text if len(text) < 3000 else text[:3000],
            'full_text': text if len(text) >= 3000 else None,
        }

        return doc, SourceType.TEXT

    # --- Private helper methods ---

    def _normalize_doi(self, doi: str) -> str:
        """Normalize DOI to bare format (without URL prefix)."""
        doi = doi.strip()
        # Remove common prefixes
        prefixes = ['https://doi.org/', 'http://doi.org/', 'doi.org/', 'doi:']
        for prefix in prefixes:
            if doi.lower().startswith(prefix.lower()):
                doi = doi[len(prefix):]
        return doi

    def _normalize_pmid(self, pmid: str) -> str:
        """Normalize PMID to numeric string."""
        pmid = str(pmid).strip()
        # Remove common prefixes
        prefixes = ['pmid:', 'pmid', 'pubmed:']
        for prefix in prefixes:
            if pmid.lower().startswith(prefix.lower()):
                pmid = pmid[len(prefix):]
        # Extract numeric part
        match = re.search(r'(\d+)', pmid)
        if match:
            return match.group(1)
        return pmid

    def _search_local_by_doi(self, doi: str) -> Optional[Dict[str, Any]]:
        """Search local database for document by DOI."""
        try:
            from bmlibrarian.database import get_db_manager
            from psycopg.rows import dict_row

            db_manager = get_db_manager()
            with db_manager.get_connection() as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute(
                        """
                        SELECT d.*, s.name as source_name
                        FROM document d
                        LEFT JOIN sources s ON d.source_id = s.id
                        WHERE LOWER(d.doi) = LOWER(%s)
                        LIMIT 1
                        """,
                        (doi,)
                    )
                    row = cur.fetchone()
                    if row:
                        return self._db_row_to_doc(dict(row))
            return None
        except Exception as e:
            logger.warning(f"Error searching local database by DOI: {e}")
            return None

    def _search_local_by_pmid(self, pmid: str) -> Optional[Dict[str, Any]]:
        """Search local database for document by PMID."""
        try:
            from bmlibrarian.database import get_db_manager
            from psycopg.rows import dict_row

            db_manager = get_db_manager()
            with db_manager.get_connection() as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    # PMID is stored in external_id field for PubMed source
                    cur.execute(
                        """
                        SELECT d.*, s.name as source_name
                        FROM document d
                        LEFT JOIN sources s ON d.source_id = s.id
                        WHERE d.external_id = %s
                           OR d.external_id LIKE %s
                        LIMIT 1
                        """,
                        (pmid, f'%pmid:{pmid}%')
                    )
                    row = cur.fetchone()
                    if row:
                        return self._db_row_to_doc(dict(row))
            return None
        except Exception as e:
            logger.warning(f"Error searching local database by PMID: {e}")
            return None

    def _db_row_to_doc(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Convert database row to standardized document dict."""
        # Extract PMID from external_id
        pmid = None
        external_id = row.get('external_id', '')
        if external_id:
            if external_id.isdigit():
                pmid = external_id
            elif 'pmid:' in external_id.lower():
                match = re.search(r'pmid:(\d+)', external_id.lower())
                if match:
                    pmid = match.group(1)

        # Parse authors from array or string
        authors = row.get('authors', [])
        if isinstance(authors, str):
            authors = [a.strip() for a in authors.split(',')]

        return {
            'id': row.get('id'),
            'title': row.get('title', ''),
            'authors': authors,
            'year': self._extract_year(row.get('publication_date')),
            'journal': row.get('journal'),
            'doi': row.get('doi'),
            'pmid': pmid,
            'abstract': row.get('abstract', ''),
            'full_text': row.get('full_text', ''),
            'source_name': row.get('source_name'),
        }

    def _extract_year(self, date_value: Any) -> Optional[int]:
        """Extract year from date value."""
        if not date_value:
            return None
        if hasattr(date_value, 'year'):
            return date_value.year
        if isinstance(date_value, str):
            match = re.search(r'(\d{4})', date_value)
            if match:
                return int(match.group(1))
        return None

    def _fetch_from_pubmed(self, pmid: str) -> Optional[Dict[str, Any]]:
        """Fetch article from PubMed E-utilities API."""
        # Rate limiting
        elapsed = time.time() - self._last_pubmed_request
        if elapsed < self._pubmed_delay:
            time.sleep(self._pubmed_delay - elapsed)

        params = {
            'db': 'pubmed',
            'id': pmid,
            'retmode': 'xml',
        }
        if self.ncbi_email:
            params['email'] = self.ncbi_email
        if self.ncbi_api_key:
            params['api_key'] = self.ncbi_api_key

        try:
            response = requests.get(
                PUBMED_EFETCH_URL,
                params=params,
                timeout=REQUEST_TIMEOUT,
                headers={'User-Agent': USER_AGENT}
            )
            self._last_pubmed_request = time.time()

            if response.status_code != 200:
                logger.error(f"PubMed API returned status {response.status_code}")
                return None

            # Parse XML
            root = ET.fromstring(response.content)
            article = root.find('.//PubmedArticle')
            if article is None:
                logger.warning(f"No article found for PMID {pmid}")
                return None

            return self._parse_pubmed_article(article, pmid)

        except Exception as e:
            logger.error(f"Error fetching from PubMed: {e}")
            return None

    def _parse_pubmed_article(self, article: ET.Element, pmid: str) -> Dict[str, Any]:
        """Parse PubMed XML article element."""
        # Title
        title_elem = article.find('.//ArticleTitle')
        title = self._get_element_text(title_elem) if title_elem is not None else ''

        # Authors
        authors = []
        for author in article.findall('.//Author'):
            last_name = author.findtext('LastName', '')
            fore_name = author.findtext('ForeName', '')
            if last_name:
                authors.append(f"{last_name} {fore_name}".strip())

        # Year
        year = None
        pub_date = article.find('.//PubDate')
        if pub_date is not None:
            year_elem = pub_date.find('Year')
            if year_elem is not None and year_elem.text:
                year = int(year_elem.text)

        # Journal
        journal = article.findtext('.//Journal/Title', '')

        # DOI
        doi = None
        for id_elem in article.findall('.//ArticleId'):
            if id_elem.get('IdType') == 'doi':
                doi = id_elem.text
                break

        # Abstract
        abstract_parts = []
        for abstract_text in article.findall('.//AbstractText'):
            label = abstract_text.get('Label', '')
            text = self._get_element_text(abstract_text)
            if label:
                abstract_parts.append(f"**{label}:** {text}")
            else:
                abstract_parts.append(text)
        abstract = '\n\n'.join(abstract_parts)

        return {
            'id': None,
            'title': title,
            'authors': authors,
            'year': year,
            'journal': journal,
            'doi': doi,
            'pmid': pmid,
            'abstract': abstract,
            'full_text': None,
        }

    def _get_element_text(self, elem: Optional[ET.Element]) -> str:
        """Get all text content from XML element."""
        if elem is None:
            return ''
        if not list(elem):  # No children
            return elem.text or ''
        # Build text from element + all children
        text = elem.text or ''
        for child in elem:
            text += self._get_element_text(child)
            if child.tail:
                text += child.tail
        return text

    def _fetch_from_crossref(self, doi: str) -> Optional[Dict[str, Any]]:
        """Fetch article from CrossRef API."""
        # Rate limiting
        elapsed = time.time() - self._last_crossref_request
        if elapsed < self._crossref_delay:
            time.sleep(self._crossref_delay - elapsed)

        url = f"{CROSSREF_API_URL}/{doi}"
        headers = {'User-Agent': USER_AGENT}
        if self.crossref_email:
            headers['User-Agent'] += f' (mailto:{self.crossref_email})'

        try:
            response = requests.get(url, timeout=REQUEST_TIMEOUT, headers=headers)
            self._last_crossref_request = time.time()

            if response.status_code == 404:
                logger.warning(f"DOI {doi} not found in CrossRef")
                return None
            if response.status_code != 200:
                logger.error(f"CrossRef API returned status {response.status_code}")
                return None

            data = response.json()
            return self._parse_crossref_work(data.get('message', {}), doi)

        except Exception as e:
            logger.error(f"Error fetching from CrossRef: {e}")
            return None

    def _parse_crossref_work(self, work: Dict[str, Any], doi: str) -> Dict[str, Any]:
        """Parse CrossRef work object."""
        # Title
        titles = work.get('title', [])
        title = titles[0] if titles else ''

        # Authors
        authors = []
        for author in work.get('author', []):
            name_parts = []
            if author.get('family'):
                name_parts.append(author['family'])
            if author.get('given'):
                name_parts.append(author['given'])
            if name_parts:
                authors.append(' '.join(name_parts))

        # Year
        year = None
        published = work.get('published-print') or work.get('published-online') or work.get('created')
        if published and 'date-parts' in published:
            date_parts = published['date-parts']
            if date_parts and date_parts[0]:
                year = date_parts[0][0]

        # Journal
        container = work.get('container-title', [])
        journal = container[0] if container else ''

        # Abstract (CrossRef often doesn't have abstracts)
        abstract = work.get('abstract', '')
        # Strip JATS XML tags if present
        if abstract:
            abstract = re.sub(r'<[^>]+>', '', abstract)

        return {
            'id': None,
            'title': title,
            'authors': authors,
            'year': year,
            'journal': journal,
            'doi': doi,
            'pmid': None,
            'abstract': abstract,
            'full_text': None,
        }

    def _pdf_document_to_dict(self, document: Any, pdf_path: Path) -> Dict[str, Any]:
        """Convert pdf_processor Document to dictionary."""
        from bmlibrarian.pdf_processor import SectionType

        # Extract metadata
        title = getattr(document, 'title', '') or pdf_path.stem
        authors = getattr(document, 'authors', []) or []
        doi = getattr(document, 'doi', None)

        # Extract abstract section
        abstract = ''
        for section in getattr(document, 'sections', []):
            if section.section_type == SectionType.ABSTRACT:
                abstract = section.text
                break

        # Build full text from all sections
        full_text_parts = []
        for section in getattr(document, 'sections', []):
            if section.text:
                full_text_parts.append(section.text)
        full_text = '\n\n'.join(full_text_parts)

        return {
            'id': None,
            'title': title,
            'authors': authors,
            'year': None,  # Could try to extract from PDF
            'journal': None,
            'doi': doi,
            'pmid': None,
            'abstract': abstract,
            'full_text': full_text,
            'pdf_path': str(pdf_path),
        }

    def _parse_markdown_file(self, content: str, file_path: Path) -> Dict[str, Any]:
        """Parse markdown file, extracting YAML front matter if present."""
        title = file_path.stem
        authors = []
        year = None
        doi = None
        abstract = ''
        full_text = content

        # Check for YAML front matter
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 3:
                front_matter = parts[1]
                full_text = parts[2].strip()

                # Parse front matter (simple key: value parsing)
                for line in front_matter.strip().split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        key = key.strip().lower()
                        value = value.strip().strip('"\'')
                        if key == 'title':
                            title = value
                        elif key in ('author', 'authors'):
                            authors = [a.strip() for a in value.split(',')]
                        elif key == 'year':
                            try:
                                year = int(value)
                            except ValueError:
                                pass
                        elif key == 'doi':
                            doi = value

        # If content is short, treat as abstract
        if len(full_text) < 3000:
            abstract = full_text
            full_text = None

        return {
            'id': None,
            'title': title,
            'authors': authors,
            'year': year,
            'journal': None,
            'doi': doi,
            'pmid': None,
            'abstract': abstract,
            'full_text': full_text,
        }


__all__ = ['DocumentResolver']
