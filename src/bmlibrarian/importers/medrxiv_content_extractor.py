"""
MedRxiv Multi-Format Content Extractor.

Provides priority-based full-text extraction from multiple formats:
1. Plain text (.full.txt) - Direct download, cleanest output
2. HTML (.full or .full.html) - Web scraping + markdownify conversion
3. JATS XML (via API jats_xml_path) - Structured XML parsing
4. PDF (.full.pdf) - Subprocess-isolated pymupdf4llm extraction (delegated to importer)

This module implements the extraction strategy from the localknowledge project,
prioritizing structured formats over PDF extraction for better quality.

Usage:
    from bmlibrarian.importers.medrxiv_content_extractor import MedRxivContentExtractor

    extractor = MedRxivContentExtractor()
    result = extractor.extract(doi="10.1101/2024.01.01.123456", version="1")
    if result.success:
        print(f"Extracted {len(result.content)} chars via {result.format.value}")
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Callable

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md

from bmlibrarian.discovery.pmc_package_downloader import NXMLParser

logger = logging.getLogger(__name__)

# Default timeout for HTTP requests (seconds)
DEFAULT_TIMEOUT = 30

# Minimum content length to consider extraction successful
MIN_CONTENT_LENGTH = 100

# User agent for HTTP requests
USER_AGENT = "BMLibrarian/1.0 (Biomedical Literature Librarian; +https://github.com/hherb/bmlibrarian)"


class ContentFormat(Enum):
    """Available content formats for medRxiv papers."""
    TEXT = "text"
    HTML = "html"
    JATS_XML = "jats_xml"
    PDF = "pdf"


@dataclass
class ExtractionResult:
    """Result of content extraction attempt."""
    success: bool
    content: str = ""
    format: Optional[ContentFormat] = None
    error_message: Optional[str] = None
    extraction_time_ms: float = 0.0
    attempts: List[str] = field(default_factory=list)

    def __str__(self) -> str:
        """String representation for logging."""
        if self.success:
            return f"ExtractionResult(success=True, format={self.format.value}, chars={len(self.content)})"
        return f"ExtractionResult(success=False, error={self.error_message})"


class MedRxivContentExtractor:
    """Multi-format content extractor for medRxiv papers.

    Extracts full-text content from medRxiv preprints using multiple formats
    in priority order. Falls back to next format if extraction fails.

    Attributes:
        priority: List of format names in extraction priority order
        timeout: HTTP request timeout in seconds
        session: Requests session for HTTP operations
    """

    MEDRXIV_BASE = "https://www.medrxiv.org/content"

    # CSS selectors for extracting main content from HTML
    CONTENT_SELECTORS = [
        'div.article-full-text',
        'div.fulltext-view',
        'article.article',
        'div.highwire-markup',
        'div#article-content',
        'article',
        'main',
    ]

    # Elements to remove from HTML before conversion
    REMOVE_SELECTORS = [
        'script',
        'style',
        'nav',
        'header.site-header',
        'footer.site-footer',
        'div.sidebar',
        'div.article-nav',
        'div.fig-inline',
        'div.table-inline',
        'div.supplementary-material',
        'div.ref-list',
    ]

    def __init__(
        self,
        priority: Optional[List[str]] = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        """Initialize extractor with format priority.

        Args:
            priority: List of format names in priority order.
                     Valid values: 'text', 'html', 'jats_xml', 'pdf'
                     Default: ['text', 'html', 'jats_xml', 'pdf']
            timeout: HTTP request timeout in seconds
        """
        self.priority = priority or ['text', 'html', 'jats_xml', 'pdf']
        self.timeout = timeout
        self.nxml_parser = NXMLParser()

        # HTTP session with proper headers
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        })

    def extract(
        self,
        doi: str,
        version: str = "1",
        jats_xml_path: Optional[str] = None,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> ExtractionResult:
        """Extract full text using priority-based format selection.

        Tries each format in priority order until successful extraction.
        PDF format is skipped (returns special result) as it requires
        delegation to MedRxivImporter's subprocess-isolated extraction.

        Args:
            doi: Paper DOI (e.g., "10.1101/2024.01.01.123456")
            version: Paper version number (default "1")
            jats_xml_path: Optional path to JATS XML from API response
            progress_callback: Optional callback for progress updates

        Returns:
            ExtractionResult with content and format used, or error details
        """
        start_time = time.time()
        attempts = []

        for format_name in self.priority:
            if progress_callback:
                progress_callback(f"Trying {format_name} extraction for {doi}...")

            try:
                format_enum = ContentFormat(format_name)

                # PDF extraction is handled by MedRxivImporter, not here
                if format_enum == ContentFormat.PDF:
                    attempts.append(f"{format_name}: delegated to importer")
                    continue

                result = self._extract_format(doi, version, format_enum, jats_xml_path)
                result.attempts = attempts.copy()
                result.extraction_time_ms = (time.time() - start_time) * 1000

                if result.success and result.content:
                    attempts.append(f"{format_name}: success ({len(result.content)} chars)")
                    result.attempts = attempts
                    logger.info(f"Successfully extracted {doi} via {format_name} ({len(result.content)} chars)")
                    return result
                else:
                    attempts.append(f"{format_name}: {result.error_message or 'empty content'}")
                    logger.debug(f"Extraction failed for {doi} via {format_name}: {result.error_message}")

            except ValueError as e:
                attempts.append(f"{format_name}: invalid format")
                logger.warning(f"Invalid format '{format_name}': {e}")
            except Exception as e:
                attempts.append(f"{format_name}: error - {str(e)}")
                logger.debug(f"Extraction error for {doi} via {format_name}: {e}")

        # All formats failed (or only PDF remaining)
        extraction_time = (time.time() - start_time) * 1000
        return ExtractionResult(
            success=False,
            error_message=f"All extraction formats exhausted for {doi}",
            extraction_time_ms=extraction_time,
            attempts=attempts
        )

    def _extract_format(
        self,
        doi: str,
        version: str,
        format_type: ContentFormat,
        jats_xml_path: Optional[str]
    ) -> ExtractionResult:
        """Extract content using specific format.

        Args:
            doi: Paper DOI
            version: Paper version
            format_type: ContentFormat to use
            jats_xml_path: Optional JATS XML path from API

        Returns:
            ExtractionResult for this format attempt
        """
        if format_type == ContentFormat.TEXT:
            return self._extract_text(doi, version)
        elif format_type == ContentFormat.HTML:
            return self._extract_html(doi, version)
        elif format_type == ContentFormat.JATS_XML:
            return self._extract_jats_xml(doi, version, jats_xml_path)
        elif format_type == ContentFormat.PDF:
            return ExtractionResult(
                success=False,
                format=ContentFormat.PDF,
                error_message="PDF extraction delegated to MedRxivImporter"
            )
        else:
            return ExtractionResult(
                success=False,
                error_message=f"Unknown format: {format_type}"
            )

    def _extract_text(self, doi: str, version: str) -> ExtractionResult:
        """Extract plain text format.

        MedRxiv may provide .full.txt for some papers, which is the
        cleanest and fastest extraction method.

        Args:
            doi: Paper DOI
            version: Paper version

        Returns:
            ExtractionResult with plain text content
        """
        # Try versioned URL first, then unversioned
        urls = [
            f"{self.MEDRXIV_BASE}/{doi}v{version}.full.txt",
            f"{self.MEDRXIV_BASE}/{doi}.full.txt",
        ]

        for url in urls:
            try:
                response = self.session.get(url, timeout=self.timeout)

                if response.status_code == 200:
                    content = response.text.strip()

                    # Validate content
                    if content and len(content) > MIN_CONTENT_LENGTH:
                        # Check it's not an error page
                        if not self._is_error_page(content):
                            return ExtractionResult(
                                success=True,
                                content=content,
                                format=ContentFormat.TEXT
                            )

                logger.debug(f"Text URL {url} returned status {response.status_code}")

            except requests.RequestException as e:
                logger.debug(f"Text extraction request failed for {url}: {e}")

        return ExtractionResult(
            success=False,
            format=ContentFormat.TEXT,
            error_message="Text format not available"
        )

    def _extract_html(self, doi: str, version: str) -> ExtractionResult:
        """Extract and convert HTML to markdown.

        Fetches the HTML version of the paper and converts it to
        Markdown format using BeautifulSoup and markdownify.

        Args:
            doi: Paper DOI
            version: Paper version

        Returns:
            ExtractionResult with Markdown-converted content
        """
        # Try versioned .full first, then .full.html, then base URL
        urls = [
            f"{self.MEDRXIV_BASE}/{doi}v{version}.full",
            f"{self.MEDRXIV_BASE}/{doi}v{version}.full.html",
            f"{self.MEDRXIV_BASE}/{doi}v{version}",
        ]

        for url in urls:
            try:
                response = self.session.get(url, timeout=self.timeout)

                if response.status_code != 200:
                    logger.debug(f"HTML URL {url} returned status {response.status_code}")
                    continue

                # Parse HTML with lxml for speed
                soup = BeautifulSoup(response.content, 'lxml')

                # Check if this is an error page
                if self._is_soup_error_page(soup):
                    logger.debug(f"HTML URL {url} returned error page")
                    continue

                # Find main article content using selectors
                content_div = None
                for selector in self.CONTENT_SELECTORS:
                    content_div = soup.select_one(selector)
                    if content_div:
                        break

                if not content_div:
                    # Fall back to body
                    content_div = soup.body

                if content_div:
                    # Remove unwanted elements
                    for selector in self.REMOVE_SELECTORS:
                        for tag in content_div.select(selector):
                            tag.decompose()

                    # Convert to markdown with ATX-style headers
                    markdown_content = md(
                        str(content_div),
                        heading_style="ATX",
                        strip=['script', 'style']
                    )

                    # Clean up the markdown
                    markdown_content = self._clean_markdown(markdown_content)

                    if markdown_content and len(markdown_content) > MIN_CONTENT_LENGTH:
                        return ExtractionResult(
                            success=True,
                            content=markdown_content,
                            format=ContentFormat.HTML
                        )

            except requests.RequestException as e:
                logger.debug(f"HTML extraction request failed for {url}: {e}")
            except Exception as e:
                logger.debug(f"HTML parsing failed for {url}: {e}")

        return ExtractionResult(
            success=False,
            format=ContentFormat.HTML,
            error_message="HTML format not available or parsing failed"
        )

    def _extract_jats_xml(
        self,
        doi: str,
        version: str,
        jats_xml_path: Optional[str]
    ) -> ExtractionResult:
        """Extract from JATS XML format.

        Uses the NXMLParser from the discovery module to parse
        JATS XML and extract structured content.

        Args:
            doi: Paper DOI
            version: Paper version
            jats_xml_path: Path to JATS XML from API response

        Returns:
            ExtractionResult with parsed XML content
        """
        # Build list of potential XML URLs
        urls = []

        # Use provided jats_xml_path if available
        if jats_xml_path:
            if jats_xml_path.startswith('http'):
                urls.append(jats_xml_path)
            else:
                urls.append(f"https://www.medrxiv.org{jats_xml_path}")

        # Try common XML URL patterns
        urls.extend([
            f"{self.MEDRXIV_BASE}/{doi}v{version}.source.xml",
            f"{self.MEDRXIV_BASE}/{doi}.source.xml",
            f"{self.MEDRXIV_BASE}/{doi}v{version}.full.xml",
            f"{self.MEDRXIV_BASE}/{doi}.full.xml",
        ])

        for url in urls:
            try:
                response = self.session.get(url, timeout=self.timeout)

                if response.status_code != 200:
                    logger.debug(f"XML URL {url} returned status {response.status_code}")
                    continue

                # Check content type
                content_type = response.headers.get('content-type', '').lower()
                if 'xml' not in content_type and 'text' not in content_type:
                    logger.debug(f"XML URL {url} returned non-XML content type: {content_type}")
                    continue

                # Parse JATS XML
                content = self.nxml_parser.parse(response.text)

                if content and len(content) > MIN_CONTENT_LENGTH:
                    return ExtractionResult(
                        success=True,
                        content=content,
                        format=ContentFormat.JATS_XML
                    )

            except requests.RequestException as e:
                logger.debug(f"XML extraction request failed for {url}: {e}")
            except Exception as e:
                logger.debug(f"XML parsing failed for {url}: {e}")

        return ExtractionResult(
            success=False,
            format=ContentFormat.JATS_XML,
            error_message="JATS XML not available or parsing failed"
        )

    def _is_error_page(self, content: str) -> bool:
        """Check if content appears to be an error page.

        Args:
            content: Text content to check

        Returns:
            True if content looks like an error page
        """
        error_indicators = [
            'page not found',
            'error 404',
            'access denied',
            'not available',
            'under maintenance',
            '<!DOCTYPE html>',  # Plain text shouldn't have HTML
        ]
        content_lower = content.lower()
        return any(indicator in content_lower for indicator in error_indicators)

    def _is_soup_error_page(self, soup: BeautifulSoup) -> bool:
        """Check if parsed HTML is an error page.

        Args:
            soup: BeautifulSoup parsed HTML

        Returns:
            True if page appears to be an error page
        """
        # Check title
        title = soup.find('title')
        if title:
            title_text = title.get_text().lower()
            if any(x in title_text for x in ['error', 'not found', '404', 'denied']):
                return True

        # Check for error elements
        error_elements = soup.select('.error, .not-found, #error-page')
        if error_elements:
            return True

        return False

    def _clean_markdown(self, content: str) -> str:
        """Clean up markdown content.

        Removes excessive whitespace, normalizes line breaks,
        and fixes common conversion artifacts.

        Args:
            content: Raw markdown content

        Returns:
            Cleaned markdown content
        """
        import re

        if not content:
            return ""

        # Normalize line endings
        content = content.replace('\r\n', '\n').replace('\r', '\n')

        # Remove excessive blank lines (more than 2 consecutive)
        content = re.sub(r'\n{3,}', '\n\n', content)

        # Remove excessive spaces
        content = re.sub(r' {2,}', ' ', content)

        # Fix header spacing
        content = re.sub(r'(#+)\s*\n+', r'\1 ', content)

        # Remove leading/trailing whitespace from lines
        lines = [line.strip() for line in content.split('\n')]
        content = '\n'.join(lines)

        # Remove empty headers
        content = re.sub(r'^#+\s*$', '', content, flags=re.MULTILINE)

        # Final cleanup
        content = content.strip()

        return content

    def discover_available_formats(self, doi: str, version: str = "1") -> List[ContentFormat]:
        """Discover which formats are available for a paper.

        Makes HEAD requests to check format availability without
        downloading full content.

        Args:
            doi: Paper DOI
            version: Paper version

        Returns:
            List of available ContentFormat values
        """
        available = []

        format_urls = {
            ContentFormat.TEXT: f"{self.MEDRXIV_BASE}/{doi}v{version}.full.txt",
            ContentFormat.HTML: f"{self.MEDRXIV_BASE}/{doi}v{version}.full",
            ContentFormat.JATS_XML: f"{self.MEDRXIV_BASE}/{doi}v{version}.source.xml",
            ContentFormat.PDF: f"{self.MEDRXIV_BASE}/{doi}v{version}.full.pdf",
        }

        for format_type, url in format_urls.items():
            try:
                response = self.session.head(url, timeout=10, allow_redirects=True)
                if response.status_code == 200:
                    available.append(format_type)
            except requests.RequestException:
                pass

        return available
