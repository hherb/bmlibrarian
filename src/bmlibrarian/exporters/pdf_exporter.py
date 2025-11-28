"""
PDF Export Module for BMLibrarian

This module provides PDF export functionality for medical research reports,
converting markdown-formatted content to professional PDF documents using ReportLab.

License: ReportLab is BSD-licensed and free for commercial use and redistribution.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from html.parser import HTMLParser

from markdown import markdown
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle,
    ListFlowable, ListItem, Preformatted, KeepTogether
)
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.pdfgen import canvas


class PDFExportError(Exception):
    """Exception raised when PDF export fails"""
    pass


@dataclass
class PDFExportConfig:
    """Configuration for PDF export"""

    # Page settings
    page_size: tuple = field(default=letter)  # letter or A4
    margin_left: float = field(default=0.75 * inch)
    margin_right: float = field(default=0.75 * inch)
    margin_top: float = field(default=1.0 * inch)
    margin_bottom: float = field(default=0.75 * inch)

    # Document metadata
    title: Optional[str] = None
    author: Optional[str] = field(default="BMLibrarian")
    subject: Optional[str] = None
    keywords: Optional[List[str]] = None

    # Styling options
    base_font_size: int = 11
    heading_color: tuple = field(default=(0.2, 0.2, 0.4))  # RGB
    link_color: tuple = field(default=(0.0, 0.2, 0.6))
    code_background: tuple = field(default=(0.95, 0.95, 0.95))

    # Content options
    include_toc: bool = True
    include_header: bool = True
    include_footer: bool = True
    include_page_numbers: bool = True
    include_timestamp: bool = True

    # Medical report specific
    show_confidence_indicators: bool = True
    highlight_citations: bool = True


class MarkdownHTMLParser(HTMLParser):
    """
    Parse HTML generated from markdown and convert to ReportLab flowables
    """

    def __init__(self, styles: Dict[str, ParagraphStyle]):
        super().__init__()
        self.styles = styles
        self.flowables: List[Any] = []
        self.current_text: List[str] = []
        self.current_style = 'Normal'
        self.list_stack: List[str] = []  # Track nested lists (ul/ol)
        self.list_items: List[Any] = []
        self.in_code_block = False
        self.code_lines: List[str] = []
        self.table_data: List[List[str]] = []
        self.in_table = False
        self.current_row: List[str] = []
        self.in_cell = False

    def handle_starttag(self, tag: str, attrs: List[tuple]):
        """Handle opening HTML tags"""
        if tag == 'h1':
            self.current_style = 'Heading1'
        elif tag == 'h2':
            self.current_style = 'Heading2'
        elif tag == 'h3':
            self.current_style = 'Heading3'
        elif tag == 'h4':
            self.current_style = 'Heading4'
        elif tag == 'p':
            self.current_style = 'Normal'
        elif tag == 'blockquote':
            self.current_style = 'Quote'
        elif tag in ('ul', 'ol'):
            self._flush_text()
            self.list_stack.append(tag)
        elif tag == 'li':
            pass  # Handle in data
        elif tag == 'pre':
            self.in_code_block = True
            self._flush_text()
        elif tag == 'code' and not self.in_code_block:
            self.current_text.append('<font name="Courier">')
        elif tag == 'strong' or tag == 'b':
            self.current_text.append('<b>')
        elif tag == 'em' or tag == 'i':
            self.current_text.append('<i>')
        elif tag == 'a':
            href = dict(attrs).get('href', '#')
            self.current_text.append(f'<link href="{href}" color="blue"><u>')
        elif tag == 'table':
            self._flush_text()
            self.in_table = True
            self.table_data = []
        elif tag == 'tr':
            self.current_row = []
        elif tag in ('td', 'th'):
            self.in_cell = True
        elif tag == 'hr':
            self._flush_text()
            self.flowables.append(Spacer(1, 0.2*inch))

    def handle_endtag(self, tag: str):
        """Handle closing HTML tags"""
        if tag in ('h1', 'h2', 'h3', 'h4', 'p', 'blockquote'):
            self._flush_text()
            self.current_style = 'Normal'
        elif tag in ('ul', 'ol'):
            self._flush_list()
        elif tag == 'pre':
            self.in_code_block = False
            self._flush_code()
        elif tag == 'code' and not self.in_code_block:
            self.current_text.append('</font>')
        elif tag == 'strong' or tag == 'b':
            self.current_text.append('</b>')
        elif tag == 'em' or tag == 'i':
            self.current_text.append('</i>')
        elif tag == 'a':
            self.current_text.append('</u></link>')
        elif tag == 'table':
            self._flush_table()
            self.in_table = False
        elif tag == 'tr':
            if self.current_row:
                self.table_data.append(self.current_row)
        elif tag in ('td', 'th'):
            self.in_cell = False

    def handle_data(self, data: str):
        """Handle text content"""
        if self.in_code_block:
            self.code_lines.append(data)
        elif self.in_cell:
            self.current_row.append(data.strip())
        elif self.list_stack and not self.in_table:
            # Collect list item text
            self.current_text.append(data)
        else:
            self.current_text.append(data)

    def _flush_text(self):
        """Convert accumulated text to a Paragraph flowable"""
        if self.current_text:
            text = ''.join(self.current_text).strip()
            if text:
                if self.list_stack:
                    # Add to list items
                    self.list_items.append(
                        Paragraph(text, self.styles[self.current_style])
                    )
                else:
                    self.flowables.append(
                        Paragraph(text, self.styles[self.current_style])
                    )
                    self.flowables.append(Spacer(1, 0.1*inch))
            self.current_text = []

    def _flush_list(self):
        """Convert accumulated list items to a ListFlowable"""
        if self.list_items:
            list_type = self.list_stack.pop()
            bullet_type = 'bullet' if list_type == 'ul' else '1'
            list_flowable = ListFlowable(
                self.list_items,
                bulletType=bullet_type,
                start=bullet_type
            )
            self.flowables.append(list_flowable)
            self.flowables.append(Spacer(1, 0.1*inch))
            self.list_items = []

    def _flush_code(self):
        """Convert accumulated code lines to Preformatted flowable"""
        if self.code_lines:
            code_text = ''.join(self.code_lines).strip()
            self.flowables.append(
                Preformatted(code_text, self.styles['Code'])
            )
            self.flowables.append(Spacer(1, 0.1*inch))
            self.code_lines = []

    def _flush_table(self):
        """Convert accumulated table data to Table flowable"""
        if self.table_data:
            table = Table(self.table_data)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ]))
            self.flowables.append(table)
            self.flowables.append(Spacer(1, 0.2*inch))
            self.table_data = []


class NumberedCanvas(canvas.Canvas):
    """Custom canvas for adding page numbers and headers/footers"""

    def __init__(self, *args, **kwargs):
        self.config: PDFExportConfig = kwargs.pop('config', PDFExportConfig())
        super().__init__(*args, **kwargs)
        self._saved_page_states: List[Any] = []

    def showPage(self):
        """Save current page state before showing"""
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        """Add page numbers to all pages before saving"""
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_page_decorations(self, num_pages: int):
        """Draw headers, footers, and page numbers"""
        page_num = self._pageNumber

        # Footer with page numbers
        if self.config.include_footer and self.config.include_page_numbers:
            footer_text = f"Page {page_num} of {num_pages}"
            self.setFont('Helvetica', 9)
            self.setFillColorRGB(0.5, 0.5, 0.5)
            self.drawRightString(
                letter[0] - self.config.margin_right,
                self.config.margin_bottom / 2,
                footer_text
            )

        # Header with title
        if self.config.include_header and self.config.title and page_num > 1:
            self.setFont('Helvetica-Oblique', 9)
            self.setFillColorRGB(0.5, 0.5, 0.5)
            self.drawString(
                self.config.margin_left,
                letter[1] - self.config.margin_top / 2,
                self.config.title[:80]  # Truncate long titles
            )

        # Timestamp in footer
        if self.config.include_timestamp and page_num == num_pages:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.setFont('Helvetica', 8)
            self.setFillColorRGB(0.6, 0.6, 0.6)
            self.drawString(
                self.config.margin_left,
                self.config.margin_bottom / 2,
                f"Generated: {timestamp}"
            )


class PDFExporter:
    """
    Export markdown content to professional PDF documents

    This class handles conversion of markdown-formatted medical research reports
    to publication-quality PDF files using ReportLab.
    """

    def __init__(self, config: Optional[PDFExportConfig] = None):
        """
        Initialize PDF exporter

        Args:
            config: PDF export configuration (uses defaults if None)
        """
        self.config = config or PDFExportConfig()
        self.styles = self._create_styles()

    def _create_styles(self) -> Dict[str, ParagraphStyle]:
        """Create paragraph styles for document elements"""
        styles = getSampleStyleSheet()
        base_size = self.config.base_font_size

        # Customize existing styles
        styles['Normal'].fontSize = base_size
        styles['Normal'].leading = base_size * 1.2
        styles['Normal'].alignment = TA_JUSTIFY

        # Heading styles
        styles['Heading1'].fontSize = base_size + 8
        styles['Heading1'].textColor = colors.Color(*self.config.heading_color)
        styles['Heading1'].spaceAfter = 12
        styles['Heading1'].spaceBefore = 12
        styles['Heading1'].keepWithNext = True

        styles['Heading2'].fontSize = base_size + 6
        styles['Heading2'].textColor = colors.Color(*self.config.heading_color)
        styles['Heading2'].spaceAfter = 10
        styles['Heading2'].spaceBefore = 10
        styles['Heading2'].keepWithNext = True

        styles['Heading3'].fontSize = base_size + 4
        styles['Heading3'].textColor = colors.Color(*self.config.heading_color)
        styles['Heading3'].spaceAfter = 8
        styles['Heading3'].spaceBefore = 8
        styles['Heading3'].keepWithNext = True

        styles['Heading4'].fontSize = base_size + 2
        styles['Heading4'].textColor = colors.Color(*self.config.heading_color)
        styles['Heading4'].spaceAfter = 6
        styles['Heading4'].spaceBefore = 6

        # Create custom styles (only if they don't exist)
        if 'Quote' not in styles:
            styles.add(ParagraphStyle(
                name='Quote',
                parent=styles['Normal'],
                fontSize=base_size - 1,
                leftIndent=20,
                rightIndent=20,
                textColor=colors.Color(0.3, 0.3, 0.3),
                borderPadding=10,
                borderColor=colors.Color(0.7, 0.7, 0.7),
                borderWidth=1,
                spaceAfter=10
            ))

        # Modify existing Code style or create new one
        if 'Code' in styles:
            styles['Code'].fontName = 'Courier'
            styles['Code'].fontSize = base_size - 1
            styles['Code'].leftIndent = 10
            styles['Code'].backColor = colors.Color(*self.config.code_background)
            styles['Code'].borderPadding = 10
            styles['Code'].spaceAfter = 10
        else:
            styles.add(ParagraphStyle(
                name='Code',
                parent=styles['Normal'],
                fontName='Courier',
                fontSize=base_size - 1,
                leftIndent=10,
                backColor=colors.Color(*self.config.code_background),
                borderPadding=10,
                spaceAfter=10
            ))

        if 'Citation' not in styles:
            styles.add(ParagraphStyle(
                name='Citation',
                parent=styles['Normal'],
                fontSize=base_size - 1,
                leftIndent=15,
                textColor=colors.Color(0.2, 0.2, 0.2),
                spaceAfter=6
            ))

        if 'Title' not in styles:
            styles.add(ParagraphStyle(
                name='Title',
                parent=styles['Heading1'],
                fontSize=base_size + 12,
                alignment=TA_CENTER,
                spaceAfter=30
            ))

        return styles

    def markdown_to_pdf(
        self,
        markdown_content: str,
        output_path: Path,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Path:
        """
        Convert markdown content to PDF

        Args:
            markdown_content: Markdown-formatted text
            output_path: Path for output PDF file
            metadata: Optional metadata (title, author, etc.)

        Returns:
            Path to created PDF file

        Raises:
            PDFExportError: If PDF generation fails
        """
        try:
            # Update config with metadata
            if metadata:
                if 'title' in metadata:
                    self.config.title = metadata['title']
                if 'author' in metadata:
                    self.config.author = metadata['author']
                if 'subject' in metadata:
                    self.config.subject = metadata['subject']
                if 'keywords' in metadata:
                    self.config.keywords = metadata['keywords']

            # Create output directory if needed
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Create PDF document
            doc = SimpleDocTemplate(
                str(output_path),
                pagesize=self.config.page_size,
                leftMargin=self.config.margin_left,
                rightMargin=self.config.margin_right,
                topMargin=self.config.margin_top,
                bottomMargin=self.config.margin_bottom,
                title=self.config.title,
                author=self.config.author,
                subject=self.config.subject
            )

            # Build document content
            story = self._build_story(markdown_content)

            # Build PDF with custom canvas
            doc.build(
                story,
                canvasmaker=lambda *args, **kwargs: NumberedCanvas(
                    *args, config=self.config, **kwargs
                )
            )

            return output_path

        except Exception as e:
            raise PDFExportError(f"Failed to generate PDF: {str(e)}") from e

    def _build_story(self, markdown_content: str) -> List[Any]:
        """Build the PDF story (content flowables) from markdown"""
        story = []

        # Add title page if title is provided
        if self.config.title:
            story.append(Paragraph(self.config.title, self.styles['Title']))
            if self.config.author:
                story.append(Spacer(1, 0.2*inch))
                story.append(Paragraph(
                    f"<i>{self.config.author}</i>",
                    self.styles['Normal']
                ))
            story.append(PageBreak())

        # Convert markdown to HTML
        html_content = markdown(
            markdown_content,
            extensions=['extra', 'codehilite', 'tables', 'fenced_code', 'nl2br']
        )

        # Parse HTML and convert to ReportLab flowables
        parser = MarkdownHTMLParser(self.styles)
        parser.feed(html_content)

        # Add parsed content to story
        story.extend(parser.flowables)

        return story

    def export_report(
        self,
        report_content: str,
        output_path: Path,
        research_question: Optional[str] = None,
        citation_count: Optional[int] = None,
        document_count: Optional[int] = None
    ) -> Path:
        """
        Export a BMLibrarian research report to PDF

        Args:
            report_content: Markdown-formatted report
            output_path: Path for output PDF
            research_question: Original research question
            citation_count: Number of citations in report
            document_count: Number of documents analyzed

        Returns:
            Path to created PDF file
        """
        metadata = {
            'title': research_question or 'BMLibrarian Research Report',
            'author': 'BMLibrarian',
            'subject': 'Medical Literature Review'
        }

        # Add summary section at the beginning
        summary_parts = []
        if research_question:
            summary_parts.append(f"**Research Question:** {research_question}\n")
        if document_count is not None:
            summary_parts.append(f"**Documents Analyzed:** {document_count}\n")
        if citation_count is not None:
            summary_parts.append(f"**Citations Extracted:** {citation_count}\n")
        summary_parts.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

        if summary_parts:
            summary = "## Report Summary\n\n" + "\n".join(summary_parts) + "\n---\n\n"
            report_content = summary + report_content

        return self.markdown_to_pdf(report_content, output_path, metadata)
