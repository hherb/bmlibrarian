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
class VerificationResult:
    """Result of PDF content verification."""

    verified: bool
    confidence: float  # 0.0 to 1.0
    match_type: Optional[str] = None  # 'doi', 'pmid', 'title', None
    expected_doi: Optional[str] = None
    extracted_doi: Optional[str] = None
    expected_pmid: Optional[str] = None
    extracted_pmid: Optional[str] = None
    expected_title: Optional[str] = None
    extracted_title: Optional[str] = None
    title_similarity: Optional[float] = None
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

    def __init__(self) -> None:
        """Initialize PDF verifier."""
        self._pymupdf = None

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

    def verify_pdf(
        self,
        pdf_path: Path,
        expected_doi: Optional[str] = None,
        expected_pmid: Optional[str] = None,
        expected_title: Optional[str] = None
    ) -> VerificationResult:
        """Verify PDF content matches expected document metadata.

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

        # Check file exists
        if not pdf_path.exists():
            result.error = f"PDF file not found: {pdf_path}"
            return result

        # Extract text from PDF
        text = self.extract_text_from_pdf(pdf_path)
        if not text:
            result.error = "Could not extract text from PDF"
            return result

        # Extract identifiers from PDF content
        extracted = self.extract_identifiers(text)
        result.extracted_doi = extracted.doi
        result.extracted_pmid = extracted.pmid
        result.extracted_title = extracted.title

        # Verification priority: DOI > PMID > Title

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

        # 3. Title similarity verification (lower confidence)
        if expected_title and extracted.title:
            similarity = self._calculate_title_similarity(expected_title, extracted.title)
            result.title_similarity = similarity

            if similarity >= self.MIN_TITLE_SIMILARITY:
                result.verified = True
                result.confidence = similarity
                result.match_type = 'title'
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

        # 4. No match found - inconclusive
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
