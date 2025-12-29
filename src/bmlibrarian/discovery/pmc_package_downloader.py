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

    Extracts Markdown-formatted content from JATS XML format used by PMC.
    Handles article structure including:
    - Front matter (title, abstract)
    - Body (sections, paragraphs, tables, figures)
    - Back matter (references, acknowledgments)

    Note: Tables are converted to Markdown table format. Figures are converted
    to Markdown image placeholders (the actual images must be fetched separately
    from PMC servers).
    """

    # Tags to skip entirely (these contain metadata, not content)
    # Note: table-wrap and fig are NOT skipped - they are handled specially
    SKIP_TAGS = {
        'object-id', 'journal-id', 'issn', 'publisher', 'contrib-group',
        'aff', 'author-notes', 'pub-date', 'volume', 'issue', 'fpage',
        'lpage', 'history', 'permissions', 'self-uri', 'counts',
        'custom-meta-group', 'funding-group', 'ref-list',
        'supplementary-material', 'inline-formula', 'disp-formula'
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

        Handles tables, figures, and paragraphs with embedded content.
        JATS XML often embeds floating elements (table-wrap, fig) inside
        paragraphs at the point where they're referenced.

        Args:
            body: Body XML element

        Returns:
            Formatted Markdown text with section headers, tables, and figures
        """
        parts = []

        def process_element(elem: ET.Element, level: int = 2) -> None:
            """Process an element and its children recursively."""
            if elem.tag == 'sec':
                # Section with title
                title = elem.find('title')
                if title is not None:
                    title_text = self._extract_text(title).strip()
                    if title_text:
                        prefix = '#' * min(level, 6)
                        parts.append(f"\n{prefix} {title_text}\n")

                # Process section children (skip title, already processed)
                for child in elem:
                    if child.tag != 'title':
                        process_element(child, level + 1)

            elif elem.tag == 'p':
                p_text = self._format_paragraph(elem)
                if p_text:
                    parts.append(f"\n{p_text}\n")

            elif elem.tag == 'table-wrap':
                table_text = self._format_table(elem)
                if table_text:
                    parts.append(f"\n{table_text}\n")

            elif elem.tag == 'fig':
                fig_text = self._format_figure(elem)
                if fig_text:
                    parts.append(f"\n{fig_text}\n")

            elif elem.tag == 'fig-group':
                # Process all figures in the group
                for fig in elem.findall('fig'):
                    fig_text = self._format_figure(fig)
                    if fig_text:
                        parts.append(f"\n{fig_text}\n")

            elif elem.tag == 'list':
                list_text = self._format_list(elem)
                if list_text:
                    parts.append(f"\n{list_text}\n")

        # Process all direct children of body
        for child in body:
            process_element(child, level=2)

        return '\n'.join(parts)

    def _format_paragraph(self, p: ET.Element) -> str:
        """Format a paragraph with inline elements and embedded tables/figures.

        JATS XML often embeds floating tables and figures inside paragraphs
        at the point where they're referenced. This method extracts both the
        paragraph text and any embedded content.

        Args:
            p: Paragraph XML element

        Returns:
            Formatted paragraph text with embedded tables/figures appended
        """
        text_parts = []
        embedded_content = []

        if p.text:
            text_parts.append(p.text)

        for child in p:
            if child.tag == 'table-wrap':
                # Embedded table - format and collect for later
                table_md = self._format_table(child)
                if table_md:
                    embedded_content.append(table_md)
            elif child.tag == 'fig':
                # Embedded figure - format and collect for later
                fig_md = self._format_figure(child)
                if fig_md:
                    embedded_content.append(fig_md)
            elif child.tag == 'xref':
                # Cross-reference (figure, table, etc.) - keep the text
                ref_text = child.text or ''
                text_parts.append(ref_text)
            elif child.tag == 'italic' or child.tag == 'i':
                text_parts.append(f"*{self._extract_text(child)}*")
            elif child.tag == 'bold' or child.tag == 'b':
                text_parts.append(f"**{self._extract_text(child)}**")
            elif child.tag == 'sup':
                text_parts.append(f"^{self._extract_text(child)}^")
            elif child.tag == 'sub':
                text_parts.append(f"~{self._extract_text(child)}~")
            else:
                text_parts.append(self._extract_text(child))

            if child.tail:
                text_parts.append(child.tail)

        # Combine paragraph text with embedded content
        result = ''.join(text_parts).strip()
        if embedded_content:
            result = result + '\n\n' + '\n\n'.join(embedded_content)

        return result

    def _format_table(self, table_wrap: ET.Element) -> str:
        """Format a table-wrap element as Markdown table.

        Args:
            table_wrap: table-wrap XML element containing label, caption, and table

        Returns:
            Markdown formatted table with caption
        """
        parts = []

        # Get label (e.g., "Table 1")
        label_elem = table_wrap.find('label')
        label = label_elem.text.strip() if label_elem is not None and label_elem.text else ''

        # Get caption/title
        caption_title = table_wrap.find('.//caption/title')
        caption_p = table_wrap.find('.//caption/p')
        caption_text = ''
        if caption_title is not None:
            caption_text = self._extract_text(caption_title).strip()
        elif caption_p is not None:
            caption_text = self._extract_text(caption_p).strip()

        # Add table header with label and caption
        if label or caption_text:
            header = f"**{label}**" if label else ""
            if caption_text:
                header = f"{header}: {caption_text}" if header else caption_text
            parts.append(f"\n{header}\n")

        # Find the actual table element
        table = table_wrap.find('.//table')
        if table is None:
            return '\n'.join(parts) if parts else ''

        # Extract headers from thead
        headers = []
        thead = table.find('.//thead')
        if thead is not None:
            for th in thead.findall('.//th'):
                headers.append(self._extract_text(th).strip() or ' ')
            # Also check for td in thead (some tables use td instead of th)
            if not headers:
                for td in thead.findall('.//td'):
                    headers.append(self._extract_text(td).strip() or ' ')

        # Extract rows from tbody
        rows = []
        tbody = table.find('.//tbody')
        if tbody is not None:
            for tr in tbody.findall('tr'):
                row = []
                for td in tr.findall('td'):
                    cell_text = self._extract_text(td).strip()
                    # Escape pipe characters in cell content
                    cell_text = cell_text.replace('|', '\\|')
                    row.append(cell_text or ' ')
                if row:
                    rows.append(row)

        # If no headers but we have rows, use first row as headers
        if not headers and rows:
            headers = rows.pop(0)

        # Build Markdown table
        if headers:
            col_count = len(headers)
            # Header row
            parts.append('| ' + ' | '.join(headers) + ' |')
            # Separator row
            parts.append('| ' + ' | '.join(['---'] * col_count) + ' |')
            # Data rows
            for row in rows:
                # Pad row to match header count
                while len(row) < col_count:
                    row.append(' ')
                parts.append('| ' + ' | '.join(row[:col_count]) + ' |')

        return '\n'.join(parts)

    def _format_figure(self, fig: ET.Element) -> str:
        """Format a figure element as Markdown image placeholder.

        Args:
            fig: Figure XML element

        Returns:
            Markdown image placeholder with caption
        """
        fig_id = fig.get('id', '')

        # Get label from element
        label_elem = fig.find('label')
        label = label_elem.text if label_elem is not None and label_elem.text else fig_id

        # Get caption
        caption_elem = fig.find('.//caption')
        caption = ''
        if caption_elem is not None:
            caption = self._extract_text(caption_elem).strip()

        # Get graphic reference
        graphic = fig.find('.//graphic')
        if graphic is not None:
            graphic_ref = graphic.get('{http://www.w3.org/1999/xlink}href', fig_id)
        else:
            graphic_ref = fig_id

        # Create Markdown image placeholder
        if caption:
            alt_text = f"{label}: {caption}"
        else:
            alt_text = label

        return f"![{alt_text}]({graphic_ref})"

    def _format_list(self, list_elem: ET.Element) -> str:
        """Format a list element to Markdown.

        Args:
            list_elem: List XML element

        Returns:
            Formatted Markdown list
        """
        parts = []
        list_type = list_elem.get('list-type', 'bullet')

        for i, item in enumerate(list_elem.findall('list-item'), 1):
            item_text = self._extract_text(item).strip()
            if list_type == 'order':
                parts.append(f"{i}. {item_text}")
            else:
                parts.append(f"- {item_text}")

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

        # Download and extract with retry on corruption
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            # Download tar.gz to memory
            logger.info(f"PMC package download attempt {attempt}/{self.max_retries}")
            tar_data = self._download_ftp(source.url)

            if tar_data is None:
                last_error = "FTP download failed - could not retrieve file from server"
                logger.warning(f"Attempt {attempt}: {last_error}")
                continue

            # Extract contents
            extracted = self._extract_package(
                tar_data=tar_data,
                pdf_output_dir=pdf_output_dir,
                fulltext_output_dir=fulltext_output_dir,
                base_filename=base_filename
            )

            if extracted.error_message:
                last_error = extracted.error_message
                logger.warning(f"Attempt {attempt}: Extraction failed - {last_error}")
                # Retry on corruption (likely incomplete download)
                if "invalid" in last_error.lower() or "corrupt" in last_error.lower() or "gzip" in last_error.lower():
                    logger.info(f"Retrying due to possible download corruption...")
                    continue
                # Non-recoverable error
                break

            # Success - we have extracted content
            break
        else:
            # All attempts failed
            return DownloadResult(
                success=False,
                source=source,
                error_message=f"PMC package download failed after {self.max_retries} attempts: {last_error}",
                duration_ms=(time.time() - start_time) * 1000,
                attempts=self.max_retries
            )

        # Check if extraction ultimately failed (non-recoverable error)
        if extracted.error_message:
            return DownloadResult(
                success=False,
                source=source,
                error_message=f"PMC package extraction failed: {extracted.error_message}",
                duration_ms=(time.time() - start_time) * 1000,
                attempts=attempt,
                package_contents=extracted.package_contents
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
