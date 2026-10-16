"""JATS / NXML full-text parser.

Converts PMC-style JATS XML (``.nxml`` / ``.xml``) into Markdown-formatted
plain text. Used by PDF discovery (PMC Cloud Service article XML) and by the
medRxiv, Europe PMC and PMC bulk importers.
"""

import logging
import re
import xml.etree.ElementTree as ET
from typing import List, Dict

logger = logging.getLogger(__name__)


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

    # Tags to skip entirely (metadata that doesn't belong in body text)
    # Note: table-wrap, fig, formulas, supplementary-material are NOT skipped - they are handled specially
    # Note: funding-group, ref-list, author-notes are NOT skipped - they have dedicated handlers
    SKIP_TAGS = {
        'object-id', 'journal-id', 'issn', 'publisher', 'contrib-group',
        'pub-date', 'volume', 'issue', 'fpage', 'lpage', 'history',
        'permissions', 'self-uri', 'counts', 'custom-meta-group'
    }

    # Tags that contain affiliations - extracted separately for metadata
    AFFILIATION_TAGS = {'aff', 'aff-group'}

    # MathML namespace
    MATHML_NS = '{http://www.w3.org/1998/Math/MathML}'

    # Tags that add whitespace/newlines
    BLOCK_TAGS = {
        'article-title', 'title', 'abstract', 'sec', 'p', 'list-item',
        'def-item', 'boxed-text', 'disp-quote', 'speech', 'verse-group'
    }

    def parse(self, nxml_content: str, include_references: bool = True) -> str:
        """Parse NXML content to extract Markdown-formatted text.

        Args:
            nxml_content: Raw NXML (JATS XML) content
            include_references: If True, include bibliography at the end

        Returns:
            Extracted Markdown text with preserved structure
        """
        try:
            root = ET.fromstring(nxml_content)
        except ET.ParseError as e:
            logger.warning(f"Failed to parse NXML: {e}")
            return ""

        text_parts = []

        # Extract front matter (title, abstract, author notes)
        front = root.find('.//front')
        if front is not None:
            # Article title
            title = front.find('.//article-title')
            if title is not None:
                title_text = self._extract_text(title).strip()
                if title_text:
                    text_parts.append(f"# {title_text}\n")

            # Author notes (corresponding author, contributions, conflicts)
            author_notes = front.find('.//author-notes')
            if author_notes is not None:
                notes_text = self._format_author_notes(author_notes)
                if notes_text:
                    text_parts.append(notes_text)

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

        # Extract back matter
        back = root.find('.//back')
        if back is not None:
            # Acknowledgments
            ack = back.find('.//ack')
            if ack is not None:
                ack_text = self._extract_text(ack).strip()
                if ack_text:
                    text_parts.append(f"\n## Acknowledgments\n\n{ack_text}\n")

            # Funding information
            funding_group = back.find('.//funding-group')
            if funding_group is None:
                # Sometimes in front matter
                funding_group = root.find('.//front//funding-group')
            if funding_group is not None:
                funding_text = self._format_funding_group(funding_group)
                if funding_text:
                    text_parts.append(funding_text)

            # References/bibliography
            if include_references:
                ref_list = back.find('.//ref-list')
                if ref_list is not None:
                    refs_text = self._format_ref_list(ref_list)
                    if refs_text:
                        text_parts.append(refs_text)

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
            elif child.tag == 'supplementary-material':
                # Supplementary material embedded in paragraph
                supp_text = self._format_supplementary(child)
                if supp_text:
                    embedded_content.append(supp_text)
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
        parts = []

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
                    if len(children) > 1:
                        # Add the accent/overscript as a marker
                        accent_text = ''.join(children[1].itertext()).strip()
                        if accent_text in ['ˆ', '^', '̂']:
                            parts.append('̂')
                        elif accent_text in ['¯', '−', '-']:
                            parts.append('̄')
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

    def _format_funding_group(self, funding_elem: ET.Element) -> str:
        """Format a funding-group element.

        Extracts funding sources, grant numbers, and any conflict of interest
        statements. This information is important for transparency.

        Args:
            funding_elem: funding-group XML element

        Returns:
            Markdown formatted funding information
        """
        parts = []

        # Process individual funding sources (award-group elements)
        for award in funding_elem.findall('.//award-group'):
            funding_source = award.find('.//funding-source')
            award_id = award.find('.//award-id')

            source_text = ''
            if funding_source is not None:
                source_text = self._extract_text(funding_source, skip_affiliations=False).strip()

            award_text = ''
            if award_id is not None:
                award_text = award_id.text.strip() if award_id.text else ''

            if source_text:
                if award_text:
                    parts.append(f"- {source_text} (Grant: {award_text})")
                else:
                    parts.append(f"- {source_text}")

        # Also check for funding-statement elements (sometimes used for freeform text)
        for stmt in funding_elem.findall('.//funding-statement'):
            stmt_text = self._extract_text(stmt, skip_affiliations=False).strip()
            if stmt_text:
                parts.append(f"- {stmt_text}")

        if parts:
            return "\n**Funding:**\n" + '\n'.join(parts) + "\n"
        return ""

    def _format_author_notes(self, notes_elem: ET.Element) -> str:
        """Format an author-notes element.

        Extracts corresponding author information, footnotes about authors,
        and any conflict of interest statements.

        Args:
            notes_elem: author-notes XML element

        Returns:
            Markdown formatted author notes
        """
        parts = []

        # Look for corresponding author info
        for corresp in notes_elem.findall('.//corresp'):
            corresp_text = self._extract_text(corresp, skip_affiliations=False).strip()
            if corresp_text:
                parts.append(f"**Corresponding Author:** {corresp_text}")

        # Look for footnotes (fn elements)
        for fn in notes_elem.findall('.//fn'):
            fn_type = fn.get('fn-type', '')
            fn_text = self._extract_text(fn, skip_affiliations=False).strip()

            if fn_text:
                if fn_type == 'con':
                    parts.append(f"**Author Contributions:** {fn_text}")
                elif fn_type == 'conflict':
                    parts.append(f"**Conflict of Interest:** {fn_text}")
                elif fn_type == 'present-address':
                    parts.append(f"**Present Address:** {fn_text}")
                elif fn_type == 'equal':
                    parts.append(f"**Equal Contribution:** {fn_text}")
                else:
                    # Generic footnote
                    parts.append(fn_text)

        if parts:
            return "\n" + '\n\n'.join(parts) + "\n"
        return ""

    def _format_ref_list(self, ref_list_elem: ET.Element) -> str:
        """Format a ref-list element as a references section.

        Extracts bibliographic references with formatting.

        Args:
            ref_list_elem: ref-list XML element

        Returns:
            Markdown formatted references section
        """
        refs = []

        # Check for title
        title_elem = ref_list_elem.find('title')
        title = "References"
        if title_elem is not None and title_elem.text:
            title = title_elem.text.strip()

        # Process each reference
        for ref in ref_list_elem.findall('.//ref'):
            ref_id = ref.get('id', '')
            ref_text = ""

            # Try to find citation or mixed-citation
            citation = ref.find('.//mixed-citation')
            if citation is None:
                citation = ref.find('.//element-citation')
            if citation is None:
                citation = ref.find('.//citation')

            if citation is not None:
                # Extract structured citation parts
                parts = []

                # Authors
                authors = []
                for name in citation.findall('.//name'):
                    surname = name.findtext('surname', '')
                    given = name.findtext('given-names', '')
                    if surname:
                        authors.append(f"{surname} {given}".strip())

                if authors:
                    parts.append(', '.join(authors[:3]))
                    if len(authors) > 3:
                        parts.append(' et al.')
                    parts.append('. ')

                # Year
                year = citation.findtext('.//year', '')
                if year:
                    parts.append(f"({year}). ")

                # Article title
                article_title = citation.find('.//article-title')
                if article_title is not None:
                    title_text = self._extract_text(article_title, skip_affiliations=False).strip()
                    if title_text:
                        parts.append(f"{title_text}. ")

                # Journal/Source
                source = citation.findtext('.//source', '')
                if source:
                    parts.append(f"*{source}*")

                # Volume, issue, pages
                volume = citation.findtext('.//volume', '')
                issue = citation.findtext('.//issue', '')
                fpage = citation.findtext('.//fpage', '')
                lpage = citation.findtext('.//lpage', '')

                if volume:
                    parts.append(f", {volume}")
                if issue:
                    parts.append(f"({issue})")
                if fpage:
                    if lpage:
                        parts.append(f": {fpage}-{lpage}")
                    else:
                        parts.append(f": {fpage}")

                # DOI
                doi = citation.findtext('.//pub-id[@pub-id-type="doi"]', '')
                if doi:
                    parts.append(f". doi: {doi}")

                ref_text = ''.join(parts)

            # Fallback to raw text extraction
            if not ref_text:
                ref_text = self._extract_text(ref, skip_affiliations=False).strip()

            if ref_text:
                # Add reference number if available
                label = ref.find('label')
                if label is not None and label.text:
                    refs.append(f"{label.text.strip()}. {ref_text}")
                else:
                    refs.append(f"- {ref_text}")

        if refs:
            return f"\n## {title}\n\n" + '\n'.join(refs) + "\n"
        return ""

    def _extract_affiliations(self, front_elem: ET.Element) -> List[Dict[str, str]]:
        """Extract author affiliations from front matter.

        Args:
            front_elem: Front matter XML element

        Returns:
            List of affiliation dictionaries with 'id' and 'text' keys
        """
        affiliations = []

        for aff in front_elem.findall('.//aff'):
            aff_id = aff.get('id', '')

            # Get institution name
            institution = aff.find('.//institution')
            addr_line = aff.find('.//addr-line')
            country = aff.find('.//country')

            parts = []
            if institution is not None and institution.text:
                parts.append(institution.text.strip())

            # Sometimes the text is directly in the aff element
            if not parts:
                aff_text = self._extract_text(aff, skip_affiliations=False).strip()
                # Remove the label if present
                label = aff.find('label')
                if label is not None and label.text and aff_text.startswith(label.text):
                    aff_text = aff_text[len(label.text):].strip()
                if aff_text:
                    parts.append(aff_text)
            else:
                if addr_line is not None:
                    addr_text = self._extract_text(addr_line, skip_affiliations=False).strip()
                    if addr_text:
                        parts.append(addr_text)
                if country is not None and country.text:
                    parts.append(country.text.strip())

            if parts:
                affiliations.append({
                    'id': aff_id,
                    'text': ', '.join(parts)
                })

        return affiliations

    def _extract_text(self, element: ET.Element, skip_affiliations: bool = True) -> str:
        """Recursively extract text from an element.

        Args:
            element: XML element
            skip_affiliations: If True, skip affiliation tags (for body text)

        Returns:
            Concatenated text content
        """
        if element.tag in self.SKIP_TAGS:
            return ""

        # Affiliations are typically handled separately in metadata extraction
        if skip_affiliations and element.tag in self.AFFILIATION_TAGS:
            return ""

        parts = []

        # Add element's direct text
        if element.text:
            parts.append(element.text)

        # Process children
        for child in element:
            child_text = self._extract_text(child, skip_affiliations)
            if child_text:
                if child.tag in self.BLOCK_TAGS:
                    parts.append(f"\n{child_text}\n")
                else:
                    parts.append(child_text)

            # Add tail text (text after this child)
            if child.tail:
                parts.append(child.tail)

        return ''.join(parts)
