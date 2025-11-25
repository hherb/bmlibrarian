"""PDF Content Verification Module.

Verifies that downloaded PDFs match their expected document metadata by
extracting identifiers (DOI, PMID, title) from the PDF content and comparing
against the expected values.

This helps detect cases where:
- Browser fallback grabbed the wrong PDF link
- DOI resolution redirected to wrong article
- Unpaywall returned incorrect metadata
- PMC package extraction error
"""

import logging
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

logger = logging.getLogger(__name__)

# Minimum text length for valid extraction
MIN_TEXT_LENGTH = 50

# Maximum text to analyze (first N chars usually contain metadata)
MAX_ANALYSIS_LENGTH = 5000


@dataclass
class PDFIdentifiers:
    """Identifiers extracted from PDF content."""

    doi: Optional[str] = None
    pmid: Optional[str] = None
    title: Optional[str] = None

    def has_identifiers(self) -> bool:
        """Check if any identifiers were extracted."""
        return bool(self.doi or self.pmid or self.title)


@dataclass
class PDFValidityResult:
    """Result of PDF file validity check."""

    is_valid: bool
    is_pdf: bool = False  # File has PDF magic bytes
    page_count: int = 0
    has_text: bool = False  # Text is extractable
    file_size: int = 0
    error: Optional[str] = None


@dataclass
class VerificationResult:
    """Result of PDF content verification."""

    verified: bool
    confidence: float  # 0.0 to 1.0
    match_type: Optional[str] = None  # 'doi', 'pmid', 'title', 'title_exact', None
    expected_doi: Optional[str] = None
    extracted_doi: Optional[str] = None
    expected_pmid: Optional[str] = None
    extracted_pmid: Optional[str] = None
    expected_title: Optional[str] = None
    extracted_title: Optional[str] = None
    title_similarity: Optional[float] = None
    is_valid_pdf: bool = True  # Whether the file is a valid PDF
    error: Optional[str] = None
    warnings: Optional[List[str]] = None

    def __post_init__(self) -> None:
        """Initialize warnings list if not provided."""
        if self.warnings is None:
            self.warnings = []


class PDFVerifier:
    """Verifies PDF content matches expected document metadata."""

    # DOI patterns found in PDFs
    DOI_PATTERNS = [
        r'doi[:\s]+\s*(10\.\d{4,}/[^\s\]>\)]+)',  # doi: 10.xxxx/...
        r'https?://doi\.org/(10\.\d{4,}/[^\s\]>\)]+)',  # https://doi.org/10.xxxx/...
        r'https?://dx\.doi\.org/(10\.\d{4,}/[^\s\]>\)]+)',  # https://dx.doi.org/10.xxxx/...
        r'DOI\s+(10\.\d{4,}/[^\s\]>\)]+)',  # DOI 10.xxxx/...
        r'\b(10\.\d{4,}/[^\s\]>\),]+)',  # bare DOI 10.xxxx/...
    ]

    # PMID patterns found in PDFs
    PMID_PATTERNS = [
        r'PMID[:\s]+\s*(\d{7,8})',  # PMID: 12345678
        r'PubMed\s*ID[:\s]+\s*(\d{7,8})',  # PubMed ID: 12345678
        r'pubmed/(\d{7,8})',  # pubmed/12345678
        r'ncbi\.nlm\.nih\.gov/pubmed/(\d{7,8})',  # full URL
    ]

    # Minimum title similarity for match
    MIN_TITLE_SIMILARITY = 0.80

    # PDF magic bytes
    PDF_MAGIC = b'%PDF'

    def __init__(self) -> None:
        """Initialize PDF verifier."""
        self._pymupdf = None

    def check_pdf_validity(self, pdf_path: Path) -> PDFValidityResult:
        """Check if a file is a valid PDF.

        Performs multiple checks:
        1. File exists and is readable
        2. File has PDF magic bytes
        3. PDF can be opened by PyMuPDF
        4. PDF has at least one page
        5. Text can be extracted (for scanned docs this may fail)

        Args:
            pdf_path: Path to the file to check

        Returns:
            PDFValidityResult with validity details
        """
        result = PDFValidityResult(is_valid=False)

        # Check file exists
        if not pdf_path.exists():
            result.error = f"File not found: {pdf_path}"
            return result

        # Get file size
        try:
            result.file_size = pdf_path.stat().st_size
        except OSError as e:
            result.error = f"Cannot read file: {e}"
            return result

        # Check for empty file
        if result.file_size == 0:
            result.error = "File is empty"
            return result

        # Check PDF magic bytes
        try:
            with open(pdf_path, 'rb') as f:
                header = f.read(8)
                result.is_pdf = header.startswith(self.PDF_MAGIC)
        except Exception as e:
            result.error = f"Cannot read file header: {e}"
            return result

        if not result.is_pdf:
            result.error = "File is not a PDF (invalid magic bytes)"
            return result

        # Try to open with PyMuPDF
        try:
            fitz = self._get_pymupdf()
            doc = fitz.open(str(pdf_path))

            result.page_count = len(doc)
            if result.page_count == 0:
                result.error = "PDF has no pages"
                doc.close()
                return result

            # Try to extract text from first page
            try:
                first_page = doc[0]
                text = first_page.get_text()
                result.has_text = len(text.strip()) > MIN_TEXT_LENGTH
            except Exception:
                result.has_text = False

            doc.close()
            result.is_valid = True

        except Exception as e:
            result.error = f"Cannot open PDF: {e}"
            return result

        return result

    def _get_pymupdf(self) -> Any:
        """Lazy-load PyMuPDF.

        Returns:
            PyMuPDF (fitz) module

        Raises:
            ImportError: If PyMuPDF is not installed
        """
        if self._pymupdf is None:
            try:
                import fitz
                self._pymupdf = fitz
            except ImportError:
                try:
                    import pymupdf as fitz
                    self._pymupdf = fitz
                except ImportError:
                    raise ImportError(
                        "PyMuPDF not installed. Install with: uv add pymupdf"
                    )
        return self._pymupdf

    def extract_text_from_pdf(
        self,
        pdf_path: Path,
        max_pages: int = 2
    ) -> Optional[str]:
        """Extract text from first pages of PDF.

        Args:
            pdf_path: Path to PDF file
            max_pages: Maximum pages to extract (default 2)

        Returns:
            Extracted text or None if failed
        """
        fitz = self._get_pymupdf()

        try:
            doc = fitz.open(str(pdf_path))
            if len(doc) == 0:
                logger.warning(f"PDF has no pages: {pdf_path}")
                return None

            text_parts = []
            for page_num in range(min(max_pages, len(doc))):
                page = doc[page_num]
                text_parts.append(page.get_text())

            doc.close()

            text = '\n'.join(text_parts)
            if len(text.strip()) < MIN_TEXT_LENGTH:
                logger.warning(f"Extracted text too short from {pdf_path}")
                return None

            return text[:MAX_ANALYSIS_LENGTH]

        except Exception as e:
            logger.error(f"Error extracting text from {pdf_path}: {e}")
            return None

    def extract_identifiers(self, text: str) -> PDFIdentifiers:
        """Extract DOI, PMID, and title from PDF text.

        Args:
            text: Text extracted from PDF

        Returns:
            PDFIdentifiers with extracted values
        """
        doi = self._extract_doi(text)
        pmid = self._extract_pmid(text)
        title = self._extract_title(text)

        return PDFIdentifiers(doi=doi, pmid=pmid, title=title)

    def _extract_doi(self, text: str) -> Optional[str]:
        """Extract DOI from text using regex patterns."""
        for pattern in self.DOI_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                doi = match.group(1).rstrip('.,;:')
                # Basic validation
                if doi.startswith('10.') and '/' in doi:
                    logger.debug(f"Extracted DOI: {doi}")
                    return doi
        return None

    def _extract_pmid(self, text: str) -> Optional[str]:
        """Extract PMID from text using regex patterns."""
        for pattern in self.PMID_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                pmid = match.group(1)
                logger.debug(f"Extracted PMID: {pmid}")
                return pmid
        return None

    def _extract_title(self, text: str) -> Optional[str]:
        """Extract likely title from PDF text.

        Heuristic: The title is usually one of the first lines,
        often in larger font, typically 5-200 characters.
        """
        lines = text.split('\n')

        # Look at first 20 non-empty lines
        candidates = []
        for line in lines[:30]:
            line = line.strip()
            # Skip empty, very short, or very long lines
            if len(line) < 10 or len(line) > 300:
                continue
            # Skip lines that look like metadata
            if any(skip in line.lower() for skip in [
                'doi:', 'pmid:', 'received:', 'accepted:', 'published:',
                'copyright', '©', 'article info', 'keywords:',
                'author:', 'correspondence:', 'e-mail:', '@',
                'abstract', 'introduction', 'methods', 'results',
                'www.', 'http', '.com', '.org',
            ]):
                continue
            # Skip lines that are mostly numbers or symbols
            alpha_ratio = sum(c.isalpha() for c in line) / len(line) if line else 0
            if alpha_ratio < 0.5:
                continue
            candidates.append(line)

        # Return first reasonable candidate
        if candidates:
            # Prefer longer candidates (titles tend to be substantial)
            candidates.sort(key=len, reverse=True)
            return candidates[0]

        return None

    def _normalize_doi(self, doi: Optional[str]) -> Optional[str]:
        """Normalize DOI for comparison."""
        if not doi:
            return None

        doi = doi.strip().lower()
        # Remove common prefixes
        for prefix in ['https://doi.org/', 'http://doi.org/', 'doi:', 'doi ']:
            if doi.startswith(prefix):
                doi = doi[len(prefix):]

        return doi.strip()

    def _normalize_title(self, title: Optional[str]) -> str:
        """Normalize title for comparison."""
        if not title:
            return ''

        # Lowercase and remove extra whitespace
        title = ' '.join(title.lower().split())

        # Remove punctuation for comparison
        title = re.sub(r'[^\w\s]', '', title)

        return title

    def _calculate_title_similarity(
        self,
        title1: Optional[str],
        title2: Optional[str]
    ) -> float:
        """Calculate similarity between two titles."""
        norm1 = self._normalize_title(title1)
        norm2 = self._normalize_title(title2)

        if not norm1 or not norm2:
            return 0.0

        return SequenceMatcher(None, norm1, norm2).ratio()

    def _check_exact_title_match(
        self,
        expected_title: Optional[str],
        extracted_title: Optional[str]
    ) -> bool:
        """Check for exact title match (after normalization).

        This is a stricter check than semantic similarity - the normalized
        titles must be exactly equal.

        Args:
            expected_title: Expected title from database
            extracted_title: Title extracted from PDF

        Returns:
            True if titles match exactly after normalization
        """
        norm1 = self._normalize_title(expected_title)
        norm2 = self._normalize_title(extracted_title)

        if not norm1 or not norm2:
            return False

        return norm1 == norm2

    def _check_title_contains(
        self,
        expected_title: Optional[str],
        pdf_text: str
    ) -> Tuple[bool, float]:
        """Check if expected title appears in PDF text.

        This handles titles that are split across multiple lines in PDF text
        by joining the first 30 lines into a continuous string and doing
        a simple substring search.

        Args:
            expected_title: Expected title from database
            pdf_text: Full extracted text from PDF

        Returns:
            Tuple of (found, confidence)
        """
        if not expected_title or not pdf_text:
            return False, 0.0

        # Normalize title: lowercase, remove ALL non-alphanumeric characters
        norm_title = re.sub(r'[^a-z0-9]', '', expected_title.lower())

        if not norm_title or len(norm_title) < 10:
            return False, 0.0

        # Take first 50 lines (where title typically appears) - increased from 30
        lines = pdf_text.split('\n')[:50]
        # Join into one continuous string, remove ALL non-alphanumeric
        first_page_text = ''.join(lines)
        norm_text = re.sub(r'[^a-z0-9]', '', first_page_text.lower())

        # Simple substring search - title should appear in the first page text
        if norm_title in norm_text:
            logger.info(f"Title contains match: found '{expected_title[:50]}...' in PDF text")
            return True, 0.95

        # Fallback 1: check if first 60 chars of title appear (for very long titles)
        if len(norm_title) > 60:
            title_start = norm_title[:60]
            if title_start in norm_text:
                logger.info(f"Title start match: found first 60 chars of '{expected_title[:50]}...'")
                return True, 0.85

        # Fallback 2: Word-based matching - check if all significant words appear
        # Extract words (3+ chars) from title
        title_words = [w.lower() for w in re.findall(r'[a-z]{3,}', expected_title.lower())]
        if len(title_words) >= 4:
            # Check how many title words appear in the text
            text_lower = first_page_text.lower()
            matches = sum(1 for w in title_words if w in text_lower)
            match_ratio = matches / len(title_words)
            if match_ratio >= 0.9:  # 90% of words found
                logger.info(
                    f"Word-based title match: {matches}/{len(title_words)} words "
                    f"({match_ratio:.0%}) for '{expected_title[:50]}...'"
                )
                return True, 0.88

        return False, 0.0

    def verify_pdf(
        self,
        pdf_path: Path,
        expected_doi: Optional[str] = None,
        expected_pmid: Optional[str] = None,
        expected_title: Optional[str] = None
    ) -> VerificationResult:
        """Verify PDF content matches expected document metadata.

        Verification order:
        1. Check PDF validity first (magic bytes, can open, has pages)
        2. DOI match (highest confidence)
        3. PMID match (high confidence)
        4. Exact title match (high confidence)
        5. Title contains check (medium-high confidence)
        6. Title similarity (lower confidence)

        Args:
            pdf_path: Path to PDF file
            expected_doi: Expected DOI for this document
            expected_pmid: Expected PMID for this document
            expected_title: Expected title for this document

        Returns:
            VerificationResult with verification status and details
        """
        result = VerificationResult(
            verified=False,
            confidence=0.0,
            expected_doi=expected_doi,
            expected_pmid=expected_pmid,
            expected_title=expected_title,
        )

        # Step 0: Check PDF validity first
        validity = self.check_pdf_validity(pdf_path)
        result.is_valid_pdf = validity.is_valid

        if not validity.is_valid:
            result.error = validity.error or "Invalid PDF file"
            if not validity.is_pdf:
                result.error = "File is not a PDF (invalid format)"
            return result

        if not validity.has_text:
            # PDF is valid but text extraction failed (likely scanned document)
            result.warnings.append(
                "PDF appears to be scanned/image-based - text extraction limited"
            )

        # Extract text from PDF
        text = self.extract_text_from_pdf(pdf_path)
        if not text:
            result.error = "Could not extract text from PDF (may be scanned)"
            return result

        # Extract identifiers from PDF content
        extracted = self.extract_identifiers(text)
        result.extracted_doi = extracted.doi
        result.extracted_pmid = extracted.pmid
        result.extracted_title = extracted.title

        # Verification priority: DOI > PMID > Exact Title > Title Contains > Title Similarity

        # 1. DOI verification (highest confidence)
        if expected_doi and extracted.doi:
            norm_expected = self._normalize_doi(expected_doi)
            norm_extracted = self._normalize_doi(extracted.doi)

            if norm_expected == norm_extracted:
                result.verified = True
                result.confidence = 1.0
                result.match_type = 'doi'
                logger.info(f"PDF verified by DOI match: {expected_doi}")
                return result
            else:
                # DOI mismatch is a strong signal of wrong PDF
                result.verified = False
                result.confidence = 0.0
                result.match_type = 'doi_mismatch'
                result.warnings.append(
                    f"DOI MISMATCH: Expected {expected_doi}, found {extracted.doi}"
                )
                logger.warning(
                    f"PDF verification FAILED - DOI mismatch: "
                    f"expected={expected_doi}, found={extracted.doi}"
                )
                return result

        # 2. PMID verification (high confidence)
        if expected_pmid and extracted.pmid:
            if str(expected_pmid) == str(extracted.pmid):
                result.verified = True
                result.confidence = 0.95
                result.match_type = 'pmid'
                logger.info(f"PDF verified by PMID match: {expected_pmid}")
                return result
            else:
                # PMID mismatch
                result.verified = False
                result.confidence = 0.0
                result.match_type = 'pmid_mismatch'
                result.warnings.append(
                    f"PMID MISMATCH: Expected {expected_pmid}, found {extracted.pmid}"
                )
                logger.warning(
                    f"PDF verification FAILED - PMID mismatch: "
                    f"expected={expected_pmid}, found={extracted.pmid}"
                )
                return result

        # 3. Exact title match (high confidence) - NEW
        if expected_title and extracted.title:
            if self._check_exact_title_match(expected_title, extracted.title):
                result.verified = True
                result.confidence = 0.98
                result.match_type = 'title_exact'
                result.title_similarity = 1.0
                logger.info(f"PDF verified by exact title match")
                return result

        # 4. Title contains check (medium-high confidence) - NEW
        if expected_title:
            found, confidence = self._check_title_contains(expected_title, text)
            if found:
                result.verified = True
                result.confidence = confidence
                result.match_type = 'title_in_text'
                result.title_similarity = confidence
                logger.info(f"PDF verified by title found in text: confidence={confidence:.2f}")
                return result

        # 5. Title similarity verification (lower confidence)
        if expected_title and extracted.title:
            similarity = self._calculate_title_similarity(expected_title, extracted.title)
            result.title_similarity = similarity

            if similarity >= self.MIN_TITLE_SIMILARITY:
                result.verified = True
                result.confidence = similarity
                result.match_type = 'title_similar'
                logger.info(
                    f"PDF verified by title similarity: {similarity:.2f}"
                )
                return result
            else:
                result.warnings.append(
                    f"Low title similarity ({similarity:.2f}): "
                    f"Expected '{expected_title[:50]}...', "
                    f"Found '{extracted.title[:50] if extracted.title else 'N/A'}...'"
                )

        # 6. No match found - inconclusive
        if not extracted.has_identifiers():
            result.error = "Could not extract any identifiers from PDF"
            result.confidence = 0.0
        else:
            # We extracted something but couldn't verify
            result.warnings.append(
                "Could not verify PDF - no matching identifiers found"
            )
            result.confidence = 0.3  # Low confidence but not certain failure

        return result

    def verify_pdf_for_document(
        self,
        pdf_path: Path,
        document: Dict[str, Any]
    ) -> VerificationResult:
        """Verify PDF matches a document dictionary.

        Args:
            pdf_path: Path to PDF file
            document: Document dictionary with doi, pmid/external_id, title

        Returns:
            VerificationResult
        """
        expected_doi = document.get('doi')
        expected_pmid = document.get('pmid') or document.get('external_id')
        expected_title = document.get('title')

        return self.verify_pdf(
            pdf_path=pdf_path,
            expected_doi=expected_doi,
            expected_pmid=str(expected_pmid) if expected_pmid else None,
            expected_title=expected_title
        )


def verify_downloaded_pdf(
    pdf_path: Path,
    expected_doi: Optional[str] = None,
    expected_pmid: Optional[str] = None,
    expected_title: Optional[str] = None
) -> VerificationResult:
    """Convenience function to verify a downloaded PDF.

    Args:
        pdf_path: Path to downloaded PDF
        expected_doi: Expected DOI
        expected_pmid: Expected PMID
        expected_title: Expected title

    Returns:
        VerificationResult
    """
    verifier = PDFVerifier()
    return verifier.verify_pdf(
        pdf_path=pdf_path,
        expected_doi=expected_doi,
        expected_pmid=expected_pmid,
        expected_title=expected_title
    )
