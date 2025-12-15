"""PMC tar.gz package downloader with PDF and NXML extraction.

Downloads PMC Open Access tar.gz packages via FTP, extracts the PDF
and NXML full-text files, and parses the NXML for plain text content.

PMC tar.gz packages typically contain:
- PDF file
- NXML file (full-text in JATS XML format)
- Image files (GIF, JPG, etc.)
"""

import ftplib
import io
import logging
import tarfile
import time
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

from .data_types import DownloadResult, PDFSource

logger = logging.getLogger(__name__)

# Default timeout for FTP operations (seconds)
DEFAULT_FTP_TIMEOUT = 60

# Maximum retries for FTP downloads
DEFAULT_MAX_RETRIES = 3


@dataclass
class ExtractedPackage:
    """Contents extracted from a PMC tar.gz package."""

    pdf_path: Optional[Path] = None
    pdf_size: int = 0
    nxml_path: Optional[Path] = None
    nxml_size: int = 0
    full_text: Optional[str] = None
    package_contents: Optional[List[str]] = None
    error_message: Optional[str] = None


class NXMLParser:
    """Parser for PMC NXML (JATS XML) full-text files.

    Extracts plain text content from JATS XML format used by PMC.
    Handles article structure including:
    - Front matter (title, abstract)
    - Body (sections, paragraphs)
    - Back matter (references, acknowledgments)
    """

    # Tags to skip entirely (these contain metadata, not content)
    SKIP_TAGS = {
        'object-id', 'journal-id', 'issn', 'publisher', 'contrib-group',
        'aff', 'author-notes', 'pub-date', 'volume', 'issue', 'fpage',
        'lpage', 'history', 'permissions', 'self-uri', 'counts',
        'custom-meta-group', 'funding-group', 'ref-list', 'table-wrap',
        'fig', 'supplementary-material', 'inline-formula', 'disp-formula'
    }

    # Tags that add whitespace/newlines
    BLOCK_TAGS = {
        'article-title', 'title', 'abstract', 'sec', 'p', 'list-item',
        'def-item', 'boxed-text', 'disp-quote', 'speech', 'verse-group'
    }

    def parse(self, nxml_content: str) -> str:
        """Parse NXML content to extract plain text.

        Args:
            nxml_content: Raw NXML (JATS XML) content

        Returns:
            Extracted plain text with preserved paragraph structure
        """
        try:
            root = ET.fromstring(nxml_content)
        except ET.ParseError as e:
            logger.warning(f"Failed to parse NXML: {e}")
            return ""

        text_parts = []

        # Extract front matter (title, abstract)
        front = root.find('.//front')
        if front is not None:
            # Article title
            title = front.find('.//article-title')
            if title is not None:
                title_text = self._extract_text(title).strip()
                if title_text:
                    text_parts.append(f"# {title_text}\n")

            # Abstract
            abstract = front.find('.//abstract')
            if abstract is not None:
                abstract_text = self._extract_text(abstract).strip()
                if abstract_text:
                    text_parts.append(f"\n## Abstract\n\n{abstract_text}\n")

        # Extract body
        body = root.find('.//body')
        if body is not None:
            body_text = self._extract_body(body)
            if body_text:
                text_parts.append(f"\n{body_text}")

        # Extract back matter (acknowledgments, etc.) - skip references
        back = root.find('.//back')
        if back is not None:
            ack = back.find('.//ack')
            if ack is not None:
                ack_text = self._extract_text(ack).strip()
                if ack_text:
                    text_parts.append(f"\n## Acknowledgments\n\n{ack_text}\n")

        full_text = '\n'.join(text_parts)

        # Clean up excessive whitespace
        full_text = re.sub(r'\n{3,}', '\n\n', full_text)
        full_text = re.sub(r' {2,}', ' ', full_text)

        return full_text.strip()

    def _extract_body(self, body: ET.Element) -> str:
        """Extract text from body element with section structure.

        Args:
            body: Body XML element

        Returns:
            Formatted text with section headers
        """
        parts = []

        for sec in body.findall('.//sec'):
            # Get section title
            title = sec.find('title')
            if title is not None:
                title_text = self._extract_text(title).strip()
                if title_text:
                    parts.append(f"\n## {title_text}\n")

            # Get paragraphs directly under this section
            for p in sec.findall('p'):
                p_text = self._extract_text(p).strip()
                if p_text:
                    parts.append(f"\n{p_text}\n")

        # Also get any paragraphs not in sections
        for p in body.findall('p'):
            p_text = self._extract_text(p).strip()
            if p_text:
                parts.append(f"\n{p_text}\n")

        return '\n'.join(parts)

    def _extract_text(self, element: ET.Element) -> str:
        """Recursively extract text from an element.

        Args:
            element: XML element

        Returns:
            Concatenated text content
        """
        if element.tag in self.SKIP_TAGS:
            return ""

        parts = []

        # Add element's direct text
        if element.text:
            parts.append(element.text)

        # Process children
        for child in element:
            child_text = self._extract_text(child)
            if child_text:
                if child.tag in self.BLOCK_TAGS:
                    parts.append(f"\n{child_text}\n")
                else:
                    parts.append(child_text)

            # Add tail text (text after this child)
            if child.tail:
                parts.append(child.tail)

        return ''.join(parts)


class PMCPackageDownloader:
    """Downloads and extracts PMC tar.gz packages.

    Handles:
    1. FTP download of tar.gz from PMC
    2. Extraction of PDF and NXML files
    3. NXML parsing for full-text extraction
    4. File organization in pdf/ and fulltext/ directories
    """

    def __init__(
        self,
        timeout: int = DEFAULT_FTP_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES
    ):
        """Initialize downloader.

        Args:
            timeout: FTP operation timeout in seconds
            max_retries: Maximum retry attempts for FTP downloads
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.nxml_parser = NXMLParser()

    def download_and_extract(
        self,
        source: PDFSource,
        pdf_output_dir: Path,
        fulltext_output_dir: Path,
        base_filename: Optional[str] = None
    ) -> DownloadResult:
        """Download PMC tar.gz package and extract PDF + NXML.

        Args:
            source: PDFSource with FTP URL to tar.gz
            pdf_output_dir: Directory to save extracted PDF
            fulltext_output_dir: Directory to save extracted NXML
            base_filename: Base filename without extension (uses PMCID if None)

        Returns:
            DownloadResult with extracted paths and full text
        """
        start_time = time.time()

        # Validate source type
        if not source.url.lower().startswith('ftp://'):
            return DownloadResult(
                success=False,
                source=source,
                error_message=f"Expected FTP URL, got: {source.url}",
                duration_ms=(time.time() - start_time) * 1000
            )

        # Determine base filename
        if base_filename is None:
            base_filename = source.metadata.get('pmcid', 'unknown')

        # Download tar.gz to memory
        tar_data = self._download_ftp(source.url)
        if tar_data is None:
            return DownloadResult(
                success=False,
                source=source,
                error_message="FTP download failed",
                duration_ms=(time.time() - start_time) * 1000,
                attempts=self.max_retries
            )

        # Extract contents
        extracted = self._extract_package(
            tar_data=tar_data,
            pdf_output_dir=pdf_output_dir,
            fulltext_output_dir=fulltext_output_dir,
            base_filename=base_filename
        )

        if extracted.error_message:
            return DownloadResult(
                success=False,
                source=source,
                error_message=extracted.error_message,
                duration_ms=(time.time() - start_time) * 1000
            )

        # Must have at least a PDF
        if not extracted.pdf_path or not extracted.pdf_path.exists():
            return DownloadResult(
                success=False,
                source=source,
                error_message="No PDF found in package",
                duration_ms=(time.time() - start_time) * 1000,
                package_contents=extracted.package_contents
            )

        return DownloadResult(
            success=True,
            source=source,
            file_path=str(extracted.pdf_path),
            file_size=extracted.pdf_size,
            full_text=extracted.full_text,
            full_text_path=str(extracted.nxml_path) if extracted.nxml_path else None,
            package_contents=extracted.package_contents,
            duration_ms=(time.time() - start_time) * 1000
        )

    def _download_ftp(self, url: str) -> Optional[bytes]:
        """Download file from FTP URL.

        Args:
            url: FTP URL (e.g., ftp://ftp.ncbi.nlm.nih.gov/pub/pmc/...)

        Returns:
            File contents as bytes, or None on failure
        """
        parsed = urlparse(url)
        host = parsed.hostname
        port = parsed.port or 21
        path = parsed.path

        if not host or not path:
            logger.error(f"Invalid FTP URL: {url}")
            return None

        last_error = None
        for attempt in range(self.max_retries):
            try:
                if attempt > 0:
                    logger.info(f"FTP retry attempt {attempt + 1}/{self.max_retries}")
                    time.sleep(2 ** attempt)  # Exponential backoff

                # Connect to FTP server
                ftp = ftplib.FTP()
                ftp.connect(host, port, timeout=self.timeout)
                ftp.login()  # Anonymous login

                # Download to memory
                buffer = io.BytesIO()
                ftp.retrbinary(f'RETR {path}', buffer.write)
                ftp.quit()

                content = buffer.getvalue()
                if len(content) == 0:
                    last_error = "Downloaded file is empty"
                    continue

                logger.info(f"Downloaded {len(content)} bytes from FTP")
                return content

            except ftplib.error_perm as e:
                last_error = f"FTP permission error: {e}"
                logger.debug(f"FTP permission denied for {url}: {e}")
                break  # Don't retry on permission errors

            except ftplib.error_temp as e:
                last_error = f"FTP temporary error: {e}"
                logger.debug(f"FTP temporary error for {url}: {e}")

            except (TimeoutError, ftplib.error_reply) as e:
                last_error = f"FTP connection error: {e}"
                logger.debug(f"FTP connection error for {url}: {e}")

            except Exception as e:
                last_error = f"FTP error: {e}"
                logger.debug(f"FTP download error for {url}: {e}")

        logger.error(f"FTP download failed after {self.max_retries} attempts: {last_error}")
        return None

    def _extract_package(
        self,
        tar_data: bytes,
        pdf_output_dir: Path,
        fulltext_output_dir: Path,
        base_filename: str
    ) -> ExtractedPackage:
        """Extract PDF and NXML from tar.gz data.

        Args:
            tar_data: Raw tar.gz file contents
            pdf_output_dir: Directory to save PDF
            fulltext_output_dir: Directory to save NXML
            base_filename: Base filename without extension

        Returns:
            ExtractedPackage with paths and content
        """
        result = ExtractedPackage(package_contents=[])

        try:
            # Validate gzip magic bytes before attempting extraction
            # Gzip files start with 0x1f 0x8b
            if len(tar_data) < 2 or tar_data[:2] != b'\x1f\x8b':
                # Check if it's an HTML error page
                if tar_data[:100].lower().find(b'<!doctype') >= 0 or tar_data[:100].lower().find(b'<html') >= 0:
                    result.error_message = "Server returned HTML error page instead of tar.gz file"
                else:
                    result.error_message = f"Downloaded data is not a valid gzip file (got magic bytes: {tar_data[:2].hex() if tar_data else 'empty'})"
                logger.error(result.error_message)
                return result

            # Open tar.gz from memory
            tar_buffer = io.BytesIO(tar_data)
            with tarfile.open(fileobj=tar_buffer, mode='r:gz') as tar:
                # List contents
                members = tar.getmembers()
                result.package_contents = [m.name for m in members]

                logger.debug(f"Package contains {len(members)} files: {result.package_contents}")

                # Find PDF and NXML files
                pdf_member = None
                nxml_member = None

                for member in members:
                    name_lower = member.name.lower()
                    if name_lower.endswith('.pdf') and not member.isdir():
                        pdf_member = member
                    elif name_lower.endswith('.nxml') and not member.isdir():
                        nxml_member = member

                # Extract PDF
                if pdf_member:
                    pdf_output_dir.mkdir(parents=True, exist_ok=True)
                    pdf_path = pdf_output_dir / f"{base_filename}.pdf"

                    pdf_file = tar.extractfile(pdf_member)
                    if pdf_file:
                        pdf_content = pdf_file.read()

                        # Verify it's actually a PDF
                        if pdf_content[:4] == b'%PDF':
                            pdf_path.write_bytes(pdf_content)
                            result.pdf_path = pdf_path
                            result.pdf_size = len(pdf_content)
                            logger.info(f"Extracted PDF: {pdf_path} ({result.pdf_size} bytes)")
                        else:
                            logger.warning(f"File {pdf_member.name} is not a valid PDF")
                else:
                    logger.warning("No PDF file found in package")

                # Extract NXML
                if nxml_member:
                    fulltext_output_dir.mkdir(parents=True, exist_ok=True)
                    nxml_path = fulltext_output_dir / f"{base_filename}.nxml"

                    nxml_file = tar.extractfile(nxml_member)
                    if nxml_file:
                        nxml_content = nxml_file.read()
                        nxml_path.write_bytes(nxml_content)
                        result.nxml_path = nxml_path
                        result.nxml_size = len(nxml_content)
                        logger.info(f"Extracted NXML: {nxml_path} ({result.nxml_size} bytes)")

                        # Parse NXML to extract full text
                        try:
                            nxml_text = nxml_content.decode('utf-8')
                            result.full_text = self.nxml_parser.parse(nxml_text)
                            if result.full_text:
                                logger.info(f"Extracted {len(result.full_text)} chars of full text")
                        except UnicodeDecodeError as e:
                            logger.warning(f"Failed to decode NXML as UTF-8: {e}")
                else:
                    logger.debug("No NXML file found in package")

        except tarfile.TarError as e:
            result.error_message = f"Failed to extract tar.gz: {e}"
            logger.error(result.error_message)

        except Exception as e:
            result.error_message = f"Package extraction error: {e}"
            logger.error(result.error_message)

        return result


def download_pmc_package(
    source: PDFSource,
    pdf_output_dir: Path,
    fulltext_output_dir: Optional[Path] = None,
    base_filename: Optional[str] = None,
    timeout: int = DEFAULT_FTP_TIMEOUT
) -> DownloadResult:
    """Convenience function to download and extract a PMC package.

    Args:
        source: PDFSource with FTP URL to tar.gz
        pdf_output_dir: Directory to save extracted PDF
        fulltext_output_dir: Directory to save NXML (defaults to pdf_output_dir/../fulltext)
        base_filename: Base filename without extension
        timeout: FTP timeout in seconds

    Returns:
        DownloadResult with extracted paths and full text

    Example:
        from bmlibrarian.discovery.pmc_package_downloader import download_pmc_package
        from bmlibrarian.discovery.data_types import PDFSource, SourceType, AccessType
        from pathlib import Path

        source = PDFSource(
            url='ftp://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_package/...',
            source_type=SourceType.PMC_PACKAGE,
            access_type=AccessType.OPEN,
            metadata={'pmcid': 'PMC11052067'}
        )

        result = download_pmc_package(
            source=source,
            pdf_output_dir=Path('~/pdfs/2024').expanduser(),
            base_filename='PMC11052067'
        )

        if result.success:
            print(f"PDF: {result.file_path}")
            print(f"Full text: {len(result.full_text)} chars")
    """
    if fulltext_output_dir is None:
        # Default: sibling directory to pdf
        fulltext_output_dir = pdf_output_dir.parent / 'fulltext' / pdf_output_dir.name

    downloader = PMCPackageDownloader(timeout=timeout)
    return downloader.download_and_extract(
        source=source,
        pdf_output_dir=pdf_output_dir,
        fulltext_output_dir=fulltext_output_dir,
        base_filename=base_filename
    )
