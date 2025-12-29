"""Europe PMC XML Importer.

Imports full-text articles from Europe PMC downloaded XML packages into
the BMLibrarian database. Uses the existing NXMLParser for consistent
JATS XML to Markdown extraction.

Features:
- Parses gzip-compressed XML packages containing multiple articles
- Extracts metadata (PMCID, PMID, DOI, title, authors, etc.)
- Converts full-text to Markdown format with proper headers
- Handles figure/image references as Markdown placeholders
- Supports batch importing with progress tracking
- Resumable imports with state persistence

Usage:
    from pathlib import Path
    from bmlibrarian.importers import EuropePMCImporter

    importer = EuropePMCImporter(
        packages_dir=Path('~/europepmc/packages'),
        batch_size=100
    )

    # Import all downloaded packages
    stats = importer.import_all_packages()
    print(f"Imported {stats['imported']} articles")

    # Check status
    status = importer.get_status()
    print(f"Total: {status['total_articles']}, Imported: {status['imported']}")
"""

import gzip
import json
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, Iterator, Tuple

from bmlibrarian.discovery.pmc_package_downloader import NXMLParser

logger = logging.getLogger(__name__)

# Constants
DEFAULT_BATCH_SIZE = 100
EUROPE_PMC_SOURCE_NAME = 'europepmc'


@dataclass
class ArticleMetadata:
    """Metadata extracted from a JATS XML article."""

    pmcid: str  # e.g., "PMC123456"
    pmid: Optional[str] = None
    doi: Optional[str] = None
    title: Optional[str] = None
    abstract: Optional[str] = None
    authors: List[str] = field(default_factory=list)
    journal: Optional[str] = None
    publication_date: Optional[str] = None  # YYYY-MM-DD format
    year: Optional[int] = None
    full_text: Optional[str] = None  # Markdown formatted
    license: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    mesh_terms: List[str] = field(default_factory=list)
    figures: List[Dict[str, str]] = field(default_factory=list)  # [{id, label, caption}]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'pmcid': self.pmcid,
            'pmid': self.pmid,
            'doi': self.doi,
            'title': self.title,
            'abstract': self.abstract,
            'authors': self.authors,
            'journal': self.journal,
            'publication_date': self.publication_date,
            'year': self.year,
            'full_text_length': len(self.full_text) if self.full_text else 0,
            'license': self.license,
            'keywords': self.keywords,
            'mesh_terms': self.mesh_terms,
            'figures_count': len(self.figures)
        }


@dataclass
class ImportProgress:
    """Tracks overall import progress."""

    total_packages: int = 0
    imported_packages: int = 0
    total_articles: int = 0
    imported_articles: int = 0
    updated_articles: int = 0
    skipped_articles: int = 0
    failed_articles: int = 0
    errors: List[str] = field(default_factory=list)
    start_time: Optional[datetime] = None
    last_update: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'total_packages': self.total_packages,
            'imported_packages': self.imported_packages,
            'total_articles': self.total_articles,
            'imported_articles': self.imported_articles,
            'updated_articles': self.updated_articles,
            'skipped_articles': self.skipped_articles,
            'failed_articles': self.failed_articles,
            'errors': self.errors[-100:],  # Keep last 100 errors
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'last_update': self.last_update.isoformat() if self.last_update else None
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ImportProgress':
        """Create from dictionary."""
        return cls(
            total_packages=data.get('total_packages', 0),
            imported_packages=data.get('imported_packages', 0),
            total_articles=data.get('total_articles', 0),
            imported_articles=data.get('imported_articles', 0),
            updated_articles=data.get('updated_articles', 0),
            skipped_articles=data.get('skipped_articles', 0),
            failed_articles=data.get('failed_articles', 0),
            errors=data.get('errors', []),
            start_time=datetime.fromisoformat(data['start_time']) if data.get('start_time') else None,
            last_update=datetime.fromisoformat(data['last_update']) if data.get('last_update') else None
        )


class EuropePMCXMLParser:
    """Enhanced parser for Europe PMC XML packages.

    Extends NXMLParser functionality to handle:
    - Multiple articles in a single XML file
    - Figure/graphic references with placeholders
    - Complete metadata extraction
    """

    def __init__(self):
        """Initialize the parser."""
        self.nxml_parser = NXMLParser()
        # XML namespace for xlink
        self.namespaces = {
            'xlink': 'http://www.w3.org/1999/xlink'
        }

    def parse_package(self, xml_content: str) -> Iterator[ArticleMetadata]:
        """Parse a Europe PMC XML package containing multiple articles.

        DEPRECATED: Use parse_package_streaming() for large files to avoid
        memory issues. This method loads the entire XML into memory.

        Args:
            xml_content: Raw XML content from a .xml.gz package

        Yields:
            ArticleMetadata for each article in the package
        """
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            logger.error(f"Failed to parse XML package: {e}")
            return

        # Europe PMC packages wrap articles in <articles> container
        # or may be a single <article>
        if root.tag == 'articles':
            articles = root.findall('article')
        elif root.tag == 'article':
            articles = [root]
        else:
            logger.warning(f"Unexpected root tag: {root.tag}")
            return

        for article_elem in articles:
            try:
                metadata = self._parse_article(article_elem)
                if metadata:
                    yield metadata
            except Exception as e:
                # Try to get PMCID for error logging
                pmcid = "unknown"
                for article_id in article_elem.findall('.//article-id'):
                    if article_id.get('pub-id-type') == 'pmcid':
                        pmcid = article_id.text or "unknown"
                        break
                logger.warning(f"Failed to parse article {pmcid}: {e}")

    def parse_package_streaming(
        self,
        file_handle
    ) -> Iterator[ArticleMetadata]:
        """Parse a Europe PMC XML package using streaming/iterative parsing.

        Uses xml.etree.ElementTree.iterparse() to process articles one at a
        time without loading the entire XML tree into memory. This is essential
        for large packages that would otherwise cause out-of-memory errors.

        Args:
            file_handle: File-like object (e.g., from gzip.open()) containing XML

        Yields:
            ArticleMetadata for each article in the package
        """
        # Use iterparse with 'end' events to get complete article elements
        # Clear elements after processing to free memory
        context = ET.iterparse(file_handle, events=('end',))

        article_count = 0
        for event, elem in context:
            # Only process complete article elements
            if elem.tag == 'article':
                article_count += 1
                try:
                    metadata = self._parse_article(elem)
                    if metadata:
                        yield metadata
                except Exception as e:
                    # Try to get PMCID for error logging
                    pmcid = "unknown"
                    for article_id in elem.findall('.//article-id'):
                        if article_id.get('pub-id-type') == 'pmcid':
                            pmcid = article_id.text or "unknown"
                            break
                    logger.warning(f"Failed to parse article {pmcid}: {e}")
                finally:
                    # CRITICAL: Clear the element to free memory
                    # This is what makes iterparse memory-efficient
                    elem.clear()

        if article_count == 0:
            logger.warning("No articles found in package")

    def _parse_article(self, article: ET.Element) -> Optional[ArticleMetadata]:
        """Parse a single article element.

        Args:
            article: XML Element for the article

        Returns:
            ArticleMetadata or None if parsing fails
        """
        # Extract PMCID (required)
        pmcid = None
        for article_id in article.findall('.//article-id'):
            pub_id_type = article_id.get('pub-id-type')
            if pub_id_type == 'pmcid':
                pmcid = article_id.text
                if pmcid and not pmcid.startswith('PMC'):
                    pmcid = f"PMC{pmcid}"
                break

        if not pmcid:
            # Try pmc type
            for article_id in article.findall('.//article-id'):
                if article_id.get('pub-id-type') == 'pmc':
                    pmcid = f"PMC{article_id.text}"
                    break

        if not pmcid:
            logger.debug("Article has no PMCID, skipping")
            return None

        metadata = ArticleMetadata(pmcid=pmcid)

        # Extract other IDs
        for article_id in article.findall('.//article-id'):
            pub_id_type = article_id.get('pub-id-type')
            if pub_id_type == 'pmid' and article_id.text:
                metadata.pmid = article_id.text
            elif pub_id_type == 'doi' and article_id.text:
                metadata.doi = article_id.text

        # Extract title
        title_elem = article.find('.//article-title')
        if title_elem is not None:
            metadata.title = self._extract_text(title_elem).strip()

        # Extract abstract
        abstract_elem = article.find('.//abstract')
        if abstract_elem is not None:
            metadata.abstract = self._extract_text(abstract_elem).strip()

        # Extract authors
        for contrib in article.findall('.//contrib[@contrib-type="author"]'):
            name_elem = contrib.find('.//name')
            if name_elem is not None:
                surname = name_elem.findtext('surname', '')
                given = name_elem.findtext('given-names', '')
                if surname:
                    full_name = f"{surname} {given}".strip()
                    metadata.authors.append(full_name)

        # Extract journal
        journal_elem = article.find('.//journal-title')
        if journal_elem is not None:
            metadata.journal = journal_elem.text

        # Extract publication date
        pub_date = article.find('.//pub-date[@pub-type="epub"]')
        if pub_date is None:
            pub_date = article.find('.//pub-date')
        if pub_date is not None:
            year_text = pub_date.findtext('year')
            month = pub_date.findtext('month', '01')
            day = pub_date.findtext('day', '01')
            if year_text:
                metadata.year = int(year_text)
                # Ensure valid month and day
                try:
                    month_int = int(month) if month else 1
                    day_int = int(day) if day else 1
                    month_int = max(1, min(12, month_int))
                    day_int = max(1, min(28, day_int))  # Safe max
                    metadata.publication_date = f"{year_text}-{month_int:02d}-{day_int:02d}"
                except ValueError:
                    metadata.publication_date = f"{year_text}-01-01"

        # Extract license
        license_elem = article.find('.//license')
        if license_elem is not None:
            xlink_href = license_elem.get('{http://www.w3.org/1999/xlink}href')
            if xlink_href:
                metadata.license = xlink_href

        # Extract keywords
        for kwd in article.findall('.//kwd'):
            if kwd.text:
                metadata.keywords.append(kwd.text.strip())

        # Extract MeSH terms
        for mesh_heading in article.findall('.//subject[@subject-type="mesh"]'):
            if mesh_heading.text:
                metadata.mesh_terms.append(mesh_heading.text.strip())

        # Extract figures info
        for fig in article.findall('.//fig'):
            fig_id = fig.get('id', '')
            label_elem = fig.find('label')
            caption_elem = fig.find('.//caption')

            fig_info = {
                'id': fig_id,
                'label': label_elem.text if label_elem is not None and label_elem.text else '',
                'caption': self._extract_text(caption_elem).strip() if caption_elem is not None else ''
            }

            # Get graphic reference
            graphic = fig.find('.//graphic')
            if graphic is not None:
                xlink_href = graphic.get('{http://www.w3.org/1999/xlink}href', '')
                fig_info['graphic_ref'] = xlink_href

            metadata.figures.append(fig_info)

        # Convert article to Markdown full text using enhanced parser
        article_xml = ET.tostring(article, encoding='unicode')
        metadata.full_text = self._parse_to_markdown(article, metadata.figures)

        return metadata

    def _parse_to_markdown(
        self,
        article: ET.Element,
        figures: List[Dict[str, str]]
    ) -> str:
        """Parse article to Markdown with enhanced formatting.

        Args:
            article: Article XML element
            figures: List of figure info dicts

        Returns:
            Markdown-formatted full text
        """
        parts = []

        # Title
        front = article.find('.//front')
        if front is not None:
            title = front.find('.//article-title')
            if title is not None:
                title_text = self._extract_text(title).strip()
                if title_text:
                    parts.append(f"# {title_text}\n")

            # Abstract
            abstract = front.find('.//abstract')
            if abstract is not None:
                abstract_text = self._format_abstract(abstract)
                if abstract_text:
                    parts.append(f"\n## Abstract\n\n{abstract_text}\n")

        # Body sections
        body = article.find('.//body')
        if body is not None:
            body_text = self._format_body(body, figures)
            if body_text:
                parts.append(f"\n{body_text}")

        # Acknowledgments
        back = article.find('.//back')
        if back is not None:
            ack = back.find('.//ack')
            if ack is not None:
                ack_text = self._extract_text(ack).strip()
                if ack_text:
                    parts.append(f"\n## Acknowledgments\n\n{ack_text}\n")

        full_text = '\n'.join(parts)

        # Clean up whitespace
        full_text = re.sub(r'\n{3,}', '\n\n', full_text)
        full_text = re.sub(r' {2,}', ' ', full_text)

        return full_text.strip()

    def _format_abstract(self, abstract: ET.Element) -> str:
        """Format abstract with section labels if present.

        Args:
            abstract: Abstract XML element

        Returns:
            Formatted abstract text
        """
        parts = []

        # Check for structured abstract with sections
        sections = abstract.findall('sec')
        if sections:
            for sec in sections:
                title = sec.find('title')
                if title is not None and title.text:
                    parts.append(f"**{title.text}**: ")

                for p in sec.findall('p'):
                    p_text = self._extract_text(p).strip()
                    if p_text:
                        parts.append(p_text)
                        parts.append('\n\n')
        else:
            # Simple abstract
            abstract_text = self._extract_text(abstract).strip()
            if abstract_text:
                parts.append(abstract_text)

        return ''.join(parts).strip()

    def _format_body(
        self,
        body: ET.Element,
        figures: List[Dict[str, str]]
    ) -> str:
        """Format body with sections, figures, and tables.

        Args:
            body: Body XML element
            figures: Figure info for references

        Returns:
            Formatted body text
        """
        parts = []

        # Create figure lookup
        fig_lookup = {f.get('id', ''): f for f in figures}

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

                # Process section children
                for child in elem:
                    if child.tag != 'title':  # Skip title, already processed
                        process_element(child, level + 1)

            elif elem.tag == 'p':
                p_text = self._format_paragraph(elem, fig_lookup)
                if p_text:
                    parts.append(f"\n{p_text}\n")

            elif elem.tag == 'list':
                list_text = self._format_list(elem)
                if list_text:
                    parts.append(f"\n{list_text}\n")

            elif elem.tag == 'fig':
                fig_text = self._format_figure(elem, fig_lookup)
                if fig_text:
                    parts.append(f"\n{fig_text}\n")

            elif elem.tag == 'table-wrap':
                table_text = self._format_table(elem)
                if table_text:
                    parts.append(f"\n{table_text}\n")

            elif elem.tag == 'fig-group':
                # Process all figures in the group
                for fig in elem.findall('fig'):
                    fig_text = self._format_figure(fig, fig_lookup)
                    if fig_text:
                        parts.append(f"\n{fig_text}\n")

            elif elem.tag == 'disp-formula':
                formula_text = self._format_formula(elem, display=True)
                if formula_text:
                    parts.append(f"\n{formula_text}\n")

            elif elem.tag == 'supplementary-material':
                supp_text = self._format_supplementary(elem)
                if supp_text:
                    parts.append(f"\n{supp_text}\n")

        # Process all direct children of body
        for child in body:
            process_element(child, level=2)

        return '\n'.join(parts)

    def _format_paragraph(
        self,
        p: ET.Element,
        fig_lookup: Dict[str, Dict]
    ) -> str:
        """Format a paragraph with inline elements, tables, and figures.

        JATS XML often embeds floating tables and figures inside paragraphs
        at the point where they're referenced. This method handles both
        inline formatting and extracts embedded table-wrap/fig elements.

        Args:
            p: Paragraph XML element
            fig_lookup: Figure info lookup by ID

        Returns:
            Formatted paragraph text with embedded tables/figures
        """
        # Build text with replacements for special elements
        text_parts = []
        # Collect embedded tables and figures to append after paragraph text
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
                fig_md = self._format_figure(child, fig_lookup)
                if fig_md:
                    embedded_content.append(fig_md)
            elif child.tag == 'xref' and child.get('ref-type') == 'fig':
                # Figure reference (not embedded figure)
                ref_id = child.get('rid', '')
                fig_info = fig_lookup.get(ref_id, {})
                label = fig_info.get('label', child.text or ref_id)
                text_parts.append(f"[{label}]")
            elif child.tag == 'xref' and child.get('ref-type') == 'table':
                # Table reference - keep the reference text
                text_parts.append(child.text or '')
            elif child.tag == 'inline-formula':
                # Inline formula - format and include inline
                formula_text = self._format_formula(child, display=False)
                if formula_text:
                    text_parts.append(formula_text)
            elif child.tag == 'disp-formula':
                # Display formula embedded in paragraph
                formula_text = self._format_formula(child, display=True)
                if formula_text:
                    embedded_content.append(formula_text)
            elif child.tag == 'supplementary-material':
                # Supplementary material embedded in paragraph
                supp_text = self._format_supplementary(child)
                if supp_text:
                    embedded_content.append(supp_text)
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

        # Combine paragraph text with any embedded content
        result = ''.join(text_parts).strip()
        if embedded_content:
            result = result + '\n\n' + '\n\n'.join(embedded_content)

        return result

    def _format_list(self, list_elem: ET.Element) -> str:
        """Format a list to Markdown.

        Args:
            list_elem: List XML element

        Returns:
            Formatted list text
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

    def _format_figure(
        self,
        fig: ET.Element,
        fig_lookup: Dict[str, Dict]
    ) -> str:
        """Format a figure as a Markdown placeholder.

        Args:
            fig: Figure XML element
            fig_lookup: Figure info lookup

        Returns:
            Markdown figure placeholder
        """
        fig_id = fig.get('id', '')
        fig_info = fig_lookup.get(fig_id, {})

        # Get label from element or lookup
        label_elem = fig.find('label')
        label = label_elem.text if label_elem is not None and label_elem.text else fig_info.get('label', fig_id)

        # Get caption from element or lookup
        caption_elem = fig.find('.//caption')
        if caption_elem is not None:
            caption = self._extract_text(caption_elem).strip()
        else:
            caption = fig_info.get('caption', '')

        # Get graphic reference
        graphic = fig.find('.//graphic')
        if graphic is not None:
            graphic_ref = graphic.get('{http://www.w3.org/1999/xlink}href', fig_id)
        else:
            graphic_ref = fig_info.get('graphic_ref', fig_id)

        # Create Markdown image placeholder with full caption
        # Format: ![Label: Caption](graphic_reference)
        if caption:
            alt_text = f"{label}: {caption}"
        else:
            alt_text = label

        return f"![{alt_text}]({graphic_ref})"

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
            # No table structure, just return caption
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

        # Build markdown table
        if headers:
            # Determine column count
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

    def _format_formula(self, formula_elem: ET.Element, display: bool = False) -> str:
        """Format a formula element (inline-formula or disp-formula).

        Attempts to extract readable mathematical content from formulas.
        Handles both simple text formulas and MathML content.

        Args:
            formula_elem: Formula XML element
            display: If True, format as display (block) equation

        Returns:
            Formatted formula text
        """
        # First check if there's a label (for numbered equations)
        label_elem = formula_elem.find('label')
        label = ''
        if label_elem is not None and label_elem.text:
            label = f"({label_elem.text.strip()})"

        # Try to find MathML content
        # MathML can be with namespace prefix (mml:math) or without (math)
        math_elem = formula_elem.find('.//{http://www.w3.org/1998/Math/MathML}math')
        if math_elem is None:
            math_elem = formula_elem.find('.//math')

        if math_elem is not None:
            # Extract text from MathML - this gives a simplified representation
            math_text = self._extract_mathml_text(math_elem)
            if math_text:
                if display:
                    # Display formula: put on its own line with optional label
                    if label:
                        return f"\n> **Equation {label}**: {math_text}\n"
                    return f"\n> {math_text}\n"
                else:
                    # Inline formula
                    return f" {math_text} "

        # No MathML, try to get direct text content
        text_content = self._extract_text(formula_elem).strip()
        if text_content:
            # Remove any label text that might be duplicated
            if label and text_content.startswith(label):
                text_content = text_content[len(label):].strip()

            if display:
                if label:
                    return f"\n> **Equation {label}**: {text_content}\n"
                return f"\n> {text_content}\n"
            else:
                return f" {text_content} "

        return ''

    def _extract_mathml_text(self, math_elem: ET.Element) -> str:
        """Extract readable text from MathML element.

        Converts MathML to a simplified text representation.
        This preserves the mathematical meaning while making it readable.

        Args:
            math_elem: MathML math element

        Returns:
            Simplified text representation of the formula
        """
        parts: List[str] = []

        def process_mathml(elem: ET.Element) -> None:
            """Recursively process MathML elements."""
            # Get local tag name (remove namespace)
            tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag

            # Handle specific MathML elements
            if tag == 'mfrac':
                # Fraction: numerator/denominator
                children = list(elem)
                if len(children) >= 2:
                    parts.append('(')
                    process_mathml(children[0])
                    parts.append(')/(')
                    process_mathml(children[1])
                    parts.append(')')
                return
            elif tag == 'msup':
                # Superscript: base^exponent
                children = list(elem)
                if len(children) >= 2:
                    process_mathml(children[0])
                    parts.append('^')
                    process_mathml(children[1])
                return
            elif tag == 'msub':
                # Subscript: base_subscript
                children = list(elem)
                if len(children) >= 2:
                    process_mathml(children[0])
                    parts.append('_')
                    process_mathml(children[1])
                return
            elif tag == 'msubsup':
                # Subscript and superscript
                children = list(elem)
                if len(children) >= 3:
                    process_mathml(children[0])
                    parts.append('_')
                    process_mathml(children[1])
                    parts.append('^')
                    process_mathml(children[2])
                return
            elif tag == 'msqrt':
                # Square root
                parts.append('√(')
                for child in elem:
                    process_mathml(child)
                parts.append(')')
                return
            elif tag == 'mroot':
                # nth root
                children = list(elem)
                if len(children) >= 2:
                    parts.append('root(')
                    process_mathml(children[1])
                    parts.append(', ')
                    process_mathml(children[0])
                    parts.append(')')
                return
            elif tag == 'mover':
                # Overscript (e.g., hat, bar)
                children = list(elem)
                if children:
                    process_mathml(children[0])
                return
            elif tag == 'munder':
                # Underscript (e.g., limits)
                for child in elem:
                    process_mathml(child)
                return
            elif tag == 'munderover':
                # Both under and over (e.g., sum with limits)
                children = list(elem)
                if children:
                    process_mathml(children[0])
                return
            elif tag in ['mrow', 'mstyle', 'mpadded', 'mphantom', 'menclose']:
                # Container elements - just process children
                for child in elem:
                    process_mathml(child)
                return
            elif tag == 'mfenced':
                # Fenced content (parentheses, brackets, etc.)
                open_char = elem.get('open', '(')
                close_char = elem.get('close', ')')
                parts.append(open_char)
                for child in elem:
                    process_mathml(child)
                parts.append(close_char)
                return
            elif tag == 'mtable':
                # Table/matrix - simplified representation
                parts.append('[matrix]')
                return

            # For text-containing elements, extract the text
            if elem.text:
                text = elem.text.strip()
                # Convert common Unicode math characters
                text = self._convert_math_unicode(text)
                parts.append(text)

            # Process children for other elements
            for child in elem:
                process_mathml(child)
                if child.tail:
                    parts.append(child.tail.strip())

        process_mathml(math_elem)
        result = ''.join(parts).strip()

        # Clean up excessive spaces
        result = ' '.join(result.split())

        return result

    def _convert_math_unicode(self, text: str) -> str:
        """Convert common Unicode math characters to readable ASCII equivalents.

        Args:
            text: Text potentially containing Unicode math symbols

        Returns:
            Text with Unicode converted to ASCII where possible
        """
        # Common mathematical Unicode to ASCII mappings
        replacements = {
            '×': '*',
            '÷': '/',
            '±': '±',
            '−': '-',
            '≤': '<=',
            '≥': '>=',
            '≠': '!=',
            '≈': '≈',
            '∞': '∞',
            'π': 'π',
            'α': 'α',
            'β': 'β',
            'γ': 'γ',
            'δ': 'δ',
            'ε': 'ε',
            'θ': 'θ',
            'λ': 'λ',
            'μ': 'μ',
            'σ': 'σ',
            'Σ': 'Σ',
            'φ': 'φ',
            'ω': 'ω',
            'Ω': 'Ω',
            '\u00a0': ' ',  # Non-breaking space
            '\u2009': ' ',  # Thin space
            '\u2003': ' ',  # Em space
        }

        for old, new in replacements.items():
            text = text.replace(old, new)

        return text

    def _format_supplementary(self, supp_elem: ET.Element) -> str:
        """Format a supplementary-material element.

        Args:
            supp_elem: supplementary-material XML element

        Returns:
            Markdown formatted supplementary material reference
        """
        supp_id = supp_elem.get('id', '')

        # Try to get the media href
        media = supp_elem.find('.//media')
        href = ''
        if media is not None:
            href = media.get('{http://www.w3.org/1999/xlink}href', '')

        # Get caption if available
        caption = supp_elem.find('.//caption')
        caption_text = ''
        if caption is not None:
            caption_text = self._extract_text(caption).strip()

        # Get label if available
        label = supp_elem.find('label')
        label_text = ''
        if label is not None and label.text:
            label_text = label.text.strip()

        # Build the reference
        if label_text:
            ref = f"**{label_text}**"
        elif supp_id:
            ref = f"**Supplementary Material ({supp_id})**"
        else:
            ref = "**Supplementary Material**"

        if caption_text:
            ref = f"{ref}: {caption_text}"

        if href:
            ref = f"{ref} [{href}]"

        return f"\n> 📎 {ref}\n"

    def _extract_text(self, element: ET.Element) -> str:
        """Recursively extract text from an element.

        Args:
            element: XML element

        Returns:
            Concatenated text content
        """
        if element is None:
            return ""

        # Skip certain tags (metadata, references)
        # Note: table-wrap, fig, formulas, supplementary are handled separately
        skip_tags = {
            'object-id', 'journal-id', 'issn', 'publisher', 'contrib-group',
            'aff', 'author-notes', 'pub-date', 'volume', 'issue', 'fpage',
            'lpage', 'history', 'permissions', 'self-uri', 'counts',
            'custom-meta-group', 'funding-group', 'ref-list'
        }

        if element.tag in skip_tags:
            return ""

        parts = []

        if element.text:
            parts.append(element.text)

        for child in element:
            child_text = self._extract_text(child)
            if child_text:
                parts.append(child_text)
            if child.tail:
                parts.append(child.tail)

        return ''.join(parts)


class EuropePMCImporter:
    """Imports Europe PMC XML packages into the BMLibrarian database.

    Handles:
    - Reading gzip-compressed XML packages
    - Parsing multiple articles per package
    - Database upsert operations (insert or update)
    - Progress tracking and resumability
    """

    def __init__(
        self,
        packages_dir: Path,
        batch_size: int = DEFAULT_BATCH_SIZE,
        update_existing: bool = True
    ):
        """Initialize the importer.

        Args:
            packages_dir: Directory containing downloaded .xml.gz packages
            batch_size: Number of articles per database commit
            update_existing: If True, update existing records with new full_text
        """
        self.packages_dir = Path(packages_dir).expanduser()
        self.batch_size = batch_size
        self.update_existing = update_existing

        # State file in same directory as packages
        self.state_file = self.packages_dir.parent / 'import_state.json'

        # Parser
        self.parser = EuropePMCXMLParser()

        # Progress tracking
        self.progress = ImportProgress()
        self._load_state()

        # Source ID (loaded on first use)
        self._source_id: Optional[int] = None

        logger.info(
            f"Europe PMC Importer initialized with packages_dir: {self.packages_dir}"
        )

    def _load_state(self) -> None:
        """Load import state from file."""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    state = json.load(f)

                if 'import_progress' in state:
                    self.progress = ImportProgress.from_dict(state['import_progress'])
                    logger.info(
                        f"Loaded state: {self.progress.imported_articles} articles imported"
                    )
            except Exception as e:
                logger.warning(f"Failed to load state: {e}")

    def _save_state(self) -> None:
        """Save import state to file."""
        self.progress.last_update = datetime.now()

        # Load existing state to preserve download state
        existing_state = {}
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    existing_state = json.load(f)
            except Exception:
                pass

        existing_state['import_progress'] = self.progress.to_dict()

        with open(self.state_file, 'w') as f:
            json.dump(existing_state, f, indent=2)

    def _get_source_id(self, db_manager) -> int:
        """Get or create source ID for Europe PMC.

        Args:
            db_manager: Database manager instance

        Returns:
            Source ID
        """
        if self._source_id is not None:
            return self._source_id

        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Try to find existing source
                cur.execute(
                    "SELECT id FROM sources WHERE LOWER(name) = %s",
                    (EUROPE_PMC_SOURCE_NAME,)
                )
                result = cur.fetchone()

                if result:
                    self._source_id = result[0]
                else:
                    # Create new source
                    cur.execute(
                        """
                        INSERT INTO sources (name, url, is_reputable, is_free)
                        VALUES (%s, %s, %s, %s)
                        RETURNING id
                        """,
                        (
                            EUROPE_PMC_SOURCE_NAME,
                            'https://europepmc.org',
                            True,
                            True
                        )
                    )
                    result = cur.fetchone()
                    self._source_id = result[0] if result else None
                    conn.commit()
                    logger.info(f"Created Europe PMC source with ID: {self._source_id}")

        if self._source_id is None:
            raise ValueError("Failed to get or create Europe PMC source")

        return self._source_id

    def list_packages(self) -> List[Path]:
        """List all available XML packages.

        Returns:
            List of .xml.gz file paths
        """
        if not self.packages_dir.exists():
            logger.warning(f"Packages directory does not exist: {self.packages_dir}")
            return []

        packages = list(self.packages_dir.glob('*.xml.gz'))
        packages.sort()

        return packages

    def import_all_packages(
        self,
        progress_callback: Optional[Callable[[str, int, int, int], None]] = None,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """Import all downloaded packages.

        Args:
            progress_callback: Callback(package_name, pkg_num, total_pkgs, articles_imported)
            limit: Maximum number of packages to import

        Returns:
            Import statistics
        """
        from bmlibrarian.database import get_db_manager

        packages = self.list_packages()
        if limit:
            packages = packages[:limit]

        if not packages:
            logger.info("No packages to import")
            return self.get_status()

        self.progress.total_packages = len(packages)
        if not self.progress.start_time:
            self.progress.start_time = datetime.now()

        db_manager = get_db_manager()
        source_id = self._get_source_id(db_manager)

        logger.info(f"Importing {len(packages)} packages...")

        for pkg_num, package_path in enumerate(packages, 1):
            if progress_callback:
                progress_callback(
                    package_path.name,
                    pkg_num,
                    len(packages),
                    self.progress.imported_articles
                )

            try:
                stats = self._import_package(package_path, db_manager, source_id)
                self.progress.imported_packages += 1
                self.progress.imported_articles += stats['inserted']
                self.progress.updated_articles += stats['updated']
                self.progress.skipped_articles += stats['skipped']
                self.progress.failed_articles += stats['failed']
                self._save_state()

                logger.info(
                    f"[{pkg_num}/{len(packages)}] {package_path.name}: "
                    f"{stats['inserted']} new, {stats['updated']} updated, "
                    f"{stats['skipped']} skipped, {stats['failed']} failed"
                )

            except Exception as e:
                error_msg = f"Failed to import {package_path.name}: {e}"
                logger.error(error_msg)
                self.progress.errors.append(error_msg)
                self._save_state()

        return self.get_status()

    def _import_package(
        self,
        package_path: Path,
        db_manager,
        source_id: int
    ) -> Dict[str, int]:
        """Import a single package using streaming XML parsing.

        Uses iterative parsing to process articles one at a time without
        loading the entire XML file into memory. This prevents out-of-memory
        errors for large Europe PMC packages.

        Args:
            package_path: Path to .xml.gz file
            db_manager: Database manager
            source_id: Source ID for Europe PMC

        Returns:
            Stats dict with inserted, updated, skipped, failed counts
        """
        stats = {'inserted': 0, 'updated': 0, 'skipped': 0, 'failed': 0}
        article_count = 0

        # Use streaming parser - opens gzip file and parses iteratively
        try:
            with gzip.open(package_path, 'rb') as f:
                # Batch insert/update as articles are streamed
                batch: List[ArticleMetadata] = []

                for article in self.parser.parse_package_streaming(f):
                    article_count += 1
                    batch.append(article)

                    if len(batch) >= self.batch_size:
                        batch_stats = self._upsert_batch(batch, db_manager, source_id)
                        stats['inserted'] += batch_stats['inserted']
                        stats['updated'] += batch_stats['updated']
                        stats['skipped'] += batch_stats['skipped']
                        stats['failed'] += batch_stats['failed']
                        batch = []

                # Process remaining articles in final batch
                if batch:
                    batch_stats = self._upsert_batch(batch, db_manager, source_id)
                    stats['inserted'] += batch_stats['inserted']
                    stats['updated'] += batch_stats['updated']
                    stats['skipped'] += batch_stats['skipped']
                    stats['failed'] += batch_stats['failed']

        except Exception as e:
            logger.error(f"Failed to process {package_path}: {e}")
            stats['failed'] = 1
            return stats

        self.progress.total_articles += article_count
        return stats

    def _upsert_batch(
        self,
        articles: List[ArticleMetadata],
        db_manager,
        source_id: int
    ) -> Dict[str, int]:
        """Insert or update a batch of articles.

        Args:
            articles: List of ArticleMetadata
            db_manager: Database manager
            source_id: Source ID

        Returns:
            Stats dict
        """
        stats = {'inserted': 0, 'updated': 0, 'skipped': 0, 'failed': 0}

        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                for article in articles:
                    try:
                        result = self._upsert_article(cur, article, source_id)
                        stats[result] += 1
                    except Exception as e:
                        logger.debug(f"Failed to upsert {article.pmcid}: {e}")
                        stats['failed'] += 1

                conn.commit()

        return stats

    def _upsert_article(
        self,
        cursor,
        article: ArticleMetadata,
        source_id: int
    ) -> str:
        """Insert or update a single article.

        Args:
            cursor: Database cursor
            article: Article metadata
            source_id: Source ID

        Returns:
            'inserted', 'updated', or 'skipped'
        """
        # Check if exists by PMCID (external_id) and source
        cursor.execute(
            "SELECT id, full_text FROM document WHERE source_id = %s AND external_id = %s",
            (source_id, article.pmcid)
        )
        existing = cursor.fetchone()

        if existing:
            doc_id, existing_fulltext = existing

            # Update if we have new full_text and update_existing is True
            if self.update_existing and article.full_text:
                # Only update if we have new content
                if not existing_fulltext or len(article.full_text) > len(existing_fulltext):
                    cursor.execute(
                        """
                        UPDATE document SET
                            doi = COALESCE(%s, doi),
                            title = COALESCE(%s, title),
                            abstract = COALESCE(%s, abstract),
                            authors = COALESCE(%s, authors),
                            publication = COALESCE(%s, publication),
                            publication_date = COALESCE(%s::date, publication_date),
                            full_text = %s,
                            keywords = COALESCE(%s, keywords),
                            mesh_terms = COALESCE(%s, mesh_terms),
                            updated_date = CURRENT_TIMESTAMP
                        WHERE id = %s
                        """,
                        (
                            article.doi,
                            article.title,
                            article.abstract,
                            article.authors if article.authors else None,
                            article.journal,
                            article.publication_date,
                            article.full_text,
                            article.keywords if article.keywords else None,
                            article.mesh_terms if article.mesh_terms else None,
                            doc_id
                        )
                    )
                    return 'updated'

            return 'skipped'

        # Also check by DOI if available (may exist from another source)
        if article.doi:
            cursor.execute(
                "SELECT id FROM document WHERE doi = %s AND source_id != %s",
                (article.doi, source_id)
            )
            doi_match = cursor.fetchone()
            if doi_match:
                # Update the existing record with Europe PMC full text
                if self.update_existing and article.full_text:
                    cursor.execute(
                        """
                        UPDATE document SET
                            full_text = COALESCE(%s, full_text),
                            updated_date = CURRENT_TIMESTAMP
                        WHERE id = %s AND (full_text IS NULL OR full_text = '')
                        """,
                        (article.full_text, doi_match[0])
                    )
                    return 'updated'
                return 'skipped'

        # Insert new record
        cursor.execute(
            """
            INSERT INTO document (
                source_id, external_id, doi, title, abstract,
                authors, publication, publication_date, full_text,
                keywords, mesh_terms, url
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s::date, %s,
                %s, %s, %s
            )
            """,
            (
                source_id,
                article.pmcid,
                article.doi,
                article.title,
                article.abstract,
                article.authors if article.authors else None,
                article.journal,
                article.publication_date,
                article.full_text,
                article.keywords if article.keywords else None,
                article.mesh_terms if article.mesh_terms else None,
                f"https://europepmc.org/article/PMC/{article.pmcid.replace('PMC', '')}"
            )
        )

        return 'inserted'

    def import_single_package(
        self,
        package_path: Path,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> Dict[str, Any]:
        """Import a single package.

        Args:
            package_path: Path to .xml.gz file
            progress_callback: Callback(articles_processed, total_articles)

        Returns:
            Import statistics for this package
        """
        from bmlibrarian.database import get_db_manager

        db_manager = get_db_manager()
        source_id = self._get_source_id(db_manager)

        stats = self._import_package(package_path, db_manager, source_id)

        return {
            'package': package_path.name,
            'inserted': stats['inserted'],
            'updated': stats['updated'],
            'skipped': stats['skipped'],
            'failed': stats['failed'],
            'total': sum(stats.values())
        }

    def get_status(self) -> Dict[str, Any]:
        """Get current import status.

        Returns:
            Status dictionary
        """
        packages = self.list_packages()

        return {
            'packages_dir': str(self.packages_dir),
            'total_packages': len(packages),
            'imported_packages': self.progress.imported_packages,
            'total_articles': self.progress.total_articles,
            'imported_articles': self.progress.imported_articles,
            'updated_articles': self.progress.updated_articles,
            'skipped_articles': self.progress.skipped_articles,
            'failed_articles': self.progress.failed_articles,
            'errors': len(self.progress.errors),
            'recent_errors': self.progress.errors[-5:],
            'start_time': self.progress.start_time.isoformat() if self.progress.start_time else None,
            'last_update': self.progress.last_update.isoformat() if self.progress.last_update else None
        }

    def verify_package(self, package_path: Path) -> Dict[str, Any]:
        """Verify a package can be parsed correctly.

        Args:
            package_path: Path to .xml.gz file

        Returns:
            Verification results
        """
        result = {
            'package': package_path.name,
            'valid': False,
            'article_count': 0,
            'sample_articles': [],
            'error': None
        }

        try:
            with gzip.open(package_path, 'rt', encoding='utf-8') as f:
                xml_content = f.read()

            articles = list(self.parser.parse_package(xml_content))
            result['valid'] = True
            result['article_count'] = len(articles)

            # Sample first 3 articles
            for article in articles[:3]:
                result['sample_articles'].append({
                    'pmcid': article.pmcid,
                    'title': article.title[:100] if article.title else None,
                    'doi': article.doi,
                    'has_fulltext': bool(article.full_text),
                    'fulltext_length': len(article.full_text) if article.full_text else 0,
                    'figures_count': len(article.figures)
                })

        except Exception as e:
            result['error'] = str(e)

        return result
