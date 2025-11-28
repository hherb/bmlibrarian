"""
Markdown preview widget with citation tooltip support.

Renders markdown content with:
- Citation markers displayed as clickable references
- Hover tooltips showing document metadata
- Live update as user types
"""

import re
import logging
from typing import Optional, Dict

import markdown
from PySide6.QtWidgets import QTextBrowser, QWidget, QToolTip
from PySide6.QtCore import Signal, QPoint, Qt, QEvent
from PySide6.QtGui import QFont, QTextCursor

from ...resources.styles import get_font_scale, FONT_FAMILY

logger = logging.getLogger(__name__)


class CitationMarkdownPreview(QTextBrowser):
    """
    Markdown preview widget with citation support.

    Displays rendered markdown with citation markers shown as
    clickable references with hover tooltips.

    Signals:
        citation_clicked: Emitted when a citation is clicked (document_id)
        link_clicked: Emitted when a link is clicked (url)
    """

    citation_clicked = Signal(int)  # document_id
    link_clicked = Signal(str)  # url

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize markdown preview.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        self.scale = get_font_scale()
        self._citation_metadata: Dict[int, Dict] = {}  # Cache for tooltips
        self._citation_pattern = re.compile(r'\[@id:(\d+):([^\]]+)\]')

        self._setup_ui()
        self._setup_markdown()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        s = self.scale

        # Configuration
        self.setReadOnly(True)
        self.setOpenExternalLinks(False)  # Handle links ourselves
        self.setOpenLinks(False)

        # Styling
        self.setStyleSheet(f"""
            QTextBrowser {{
                background-color: white;
                color: #333;
                border: 1px solid #E0E0E0;
                border-radius: {s['radius_small']}px;
                padding: {s['padding_medium']}px;
            }}
        """)

        # Enable mouse tracking for tooltips
        self.setMouseTracking(True)

        # Connect anchor click
        self.anchorClicked.connect(self._on_anchor_clicked)

    def _setup_markdown(self) -> None:
        """Set up markdown processor."""
        self._md = markdown.Markdown(
            extensions=[
                'extra',
                'codehilite',
                'nl2br',
                'sane_lists',
                'tables',
            ]
        )

    def set_markdown(self, text: str) -> None:
        """
        Set and display markdown content.

        Args:
            text: Markdown text to display
        """
        # Pre-process citations to convert to clickable links
        processed_text = self._process_citations(text)

        # Convert to HTML
        self._md.reset()
        html_body = self._md.convert(processed_text)

        # Wrap in full HTML with styling
        html = self._wrap_html(html_body)

        self.setHtml(html)

    def _process_citations(self, text: str) -> str:
        """
        Convert citation markers to clickable markdown links.

        Args:
            text: Text with citation markers

        Returns:
            Text with citations converted to links
        """
        def replace_citation(match: re.Match) -> str:
            doc_id = match.group(1)
            label = match.group(2)
            # Create a special link that we can identify
            return f'[{label}](cite:{doc_id})'

        return self._citation_pattern.sub(replace_citation, text)

    def _wrap_html(self, body: str) -> str:
        """
        Wrap HTML body with full document and styling.

        Args:
            body: HTML body content

        Returns:
            Full HTML document
        """
        s = self.scale

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{
                    font-family: {FONT_FAMILY};
                    font-size: {s['font_small']}pt;
                    line-height: 1.6;
                    color: #333;
                    max-width: 100%;
                    padding: 0;
                    margin: 0;
                }}
                h1, h2, h3, h4, h5, h6 {{
                    color: #2c3e50;
                    margin-top: 1em;
                    margin-bottom: 0.5em;
                    font-weight: 600;
                }}
                h1 {{
                    font-size: 1.8em;
                    border-bottom: 2px solid #3498db;
                    padding-bottom: 0.3em;
                }}
                h2 {{
                    font-size: 1.5em;
                    border-bottom: 1px solid #bdc3c7;
                    padding-bottom: 0.3em;
                }}
                h3 {{
                    font-size: 1.2em;
                }}
                p {{
                    margin: 0.5em 0;
                }}
                code {{
                    background-color: #f8f8f8;
                    border: 1px solid #e0e0e0;
                    border-radius: {s['radius_tiny']}px;
                    padding: 2px 4px;
                    font-family: 'Consolas', 'Monaco', monospace;
                    font-size: 0.9em;
                    color: #d32f2f;
                }}
                pre {{
                    background-color: #f8f8f8;
                    border: 1px solid #e0e0e0;
                    border-radius: {s['radius_tiny']}px;
                    padding: {s['padding_medium']}px;
                    overflow-x: auto;
                }}
                pre code {{
                    background-color: transparent;
                    border: none;
                    padding: 0;
                    color: inherit;
                }}
                blockquote {{
                    border-left: 4px solid #3498db;
                    padding-left: 1em;
                    margin-left: 0;
                    color: #666;
                    font-style: italic;
                }}
                ul, ol {{
                    margin: 0.5em 0;
                    padding-left: 2em;
                }}
                li {{
                    margin: 0.2em 0;
                }}
                table {{
                    border-collapse: collapse;
                    width: 100%;
                    margin: 1em 0;
                }}
                th, td {{
                    border: 1px solid #ddd;
                    padding: 8px;
                    text-align: left;
                }}
                th {{
                    background-color: #3498db;
                    color: white;
                    font-weight: 600;
                }}
                tr:nth-child(even) {{
                    background-color: #f8f8f8;
                }}
                a {{
                    color: #1565C0;
                    text-decoration: none;
                }}
                a:hover {{
                    text-decoration: underline;
                }}
                /* Citation links - special styling */
                a[href^="cite:"] {{
                    color: #1565C0;
                    font-weight: 500;
                    background-color: #E3F2FD;
                    padding: 1px 4px;
                    border-radius: 3px;
                }}
                a[href^="cite:"]:hover {{
                    background-color: #BBDEFB;
                }}
                hr {{
                    border: none;
                    border-top: 1px solid #bdc3c7;
                    margin: 1em 0;
                }}
                /* Reference list styling */
                .references {{
                    margin-top: 2em;
                    padding-top: 1em;
                    border-top: 2px solid #3498db;
                }}
            </style>
        </head>
        <body>
            {body}
        </body>
        </html>
        """

    def _on_anchor_clicked(self, url) -> None:
        """
        Handle link clicks.

        Args:
            url: Clicked URL
        """
        url_str = url.toString()

        if url_str.startswith('cite:'):
            # Citation link
            try:
                doc_id = int(url_str.replace('cite:', ''))
                self.citation_clicked.emit(doc_id)
            except ValueError:
                logger.warning(f"Invalid citation URL: {url_str}")
        else:
            # Regular link
            self.link_clicked.emit(url_str)

    def set_citation_metadata(self, metadata: Dict[int, Dict]) -> None:
        """
        Set citation metadata for tooltips.

        Args:
            metadata: Dictionary mapping document_id to metadata dict
                     Each metadata dict should have: title, authors, year, journal
        """
        self._citation_metadata = metadata

    def event(self, event: QEvent) -> bool:
        """
        Handle events, including tooltip display.

        Args:
            event: Event to handle

        Returns:
            True if event was handled
        """
        if event.type() == QEvent.Type.ToolTip:
            # Get the anchor at cursor position
            cursor = self.cursorForPosition(event.pos())
            anchor = self.anchorAt(event.pos())

            if anchor and anchor.startswith('cite:'):
                try:
                    doc_id = int(anchor.replace('cite:', ''))
                    if doc_id in self._citation_metadata:
                        meta = self._citation_metadata[doc_id]
                        tooltip = self._format_citation_tooltip(meta)
                        QToolTip.showText(event.globalPos(), tooltip, self)
                        return True
                except ValueError:
                    pass

            QToolTip.hideText()
            return True

        return super().event(event)

    def _format_citation_tooltip(self, metadata: Dict) -> str:
        """
        Format citation metadata as tooltip HTML.

        Args:
            metadata: Citation metadata dict

        Returns:
            HTML formatted tooltip
        """
        title = metadata.get('title', 'Unknown title')
        authors = metadata.get('authors', 'Unknown authors')
        year = metadata.get('year', 'n.d.')
        journal = metadata.get('journal', '')

        lines = [
            f"<b>{title}</b>",
            f"<i>{authors}</i>",
        ]

        if journal:
            lines.append(f"{journal} ({year})")
        else:
            lines.append(f"({year})")

        return "<br>".join(lines)

    def clear_content(self) -> None:
        """Clear the displayed content."""
        self.clear()
        self._citation_metadata = {}

    def scroll_to_citation(self, document_id: int) -> None:
        """
        Scroll to the first occurrence of a citation.

        Args:
            document_id: Document ID to scroll to
        """
        # Find the anchor in the HTML
        cursor = self.document().find(f"cite:{document_id}")
        if not cursor.isNull():
            self.setTextCursor(cursor)
            self.centerCursor()
