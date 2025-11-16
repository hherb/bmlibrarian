"""
Markdown viewer widget for BMLibrarian Qt GUI.

Provides a widget for rendering and displaying markdown content.
"""

import markdown
from PySide6.QtWidgets import QTextBrowser, QWidget, QVBoxLayout
from PySide6.QtCore import Qt, Signal
from typing import Optional


class MarkdownViewer(QTextBrowser):
    """
    Widget for displaying formatted markdown content.

    Converts markdown to HTML and displays with proper styling.
    """

    # Signal emitted when content changes
    content_changed = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize markdown viewer.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)

        # Configure text browser
        self.setReadOnly(True)
        self.setOpenExternalLinks(True)
        self.setOpenLinks(True)

        # Configure markdown processor
        self.md = markdown.Markdown(
            extensions=[
                "extra",  # Tables, fenced code blocks, etc.
                "codehilite",  # Code syntax highlighting
                "nl2br",  # Newline to <br>
                "sane_lists",  # Better list handling
            ]
        )

        # Set stylesheet for better rendering
        self._apply_stylesheet()

    def _apply_stylesheet(self):
        """Apply custom stylesheet for markdown rendering."""
        stylesheet = """
        QTextBrowser {
            background-color: white;
            color: #333;
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 10pt;
            padding: 10px;
        }
        """
        self.setStyleSheet(stylesheet)

    def set_markdown(self, markdown_text: str):
        """
        Set and display markdown content.

        Args:
            markdown_text: Markdown-formatted text to display
        """
        # Convert markdown to HTML
        html = self._markdown_to_html(markdown_text)

        # Set HTML content
        self.setHtml(html)

        # Emit signal
        self.content_changed.emit(markdown_text)

    def _markdown_to_html(self, markdown_text: str) -> str:
        """
        Convert markdown to styled HTML.

        Args:
            markdown_text: Markdown text to convert

        Returns:
            HTML string
        """
        # Reset markdown processor
        self.md.reset()

        # Convert to HTML
        body = self.md.convert(markdown_text)

        # Wrap in full HTML document with styling
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{
                    font-family: 'Segoe UI', Arial, sans-serif;
                    font-size: 10pt;
                    line-height: 1.6;
                    color: #333;
                    max-width: 100%;
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
                    border-radius: 3px;
                    padding: 2px 4px;
                    font-family: 'Consolas', 'Monaco', monospace;
                    font-size: 0.9em;
                }}
                pre {{
                    background-color: #f8f8f8;
                    border: 1px solid #e0e0e0;
                    border-radius: 3px;
                    padding: 10px;
                    overflow-x: auto;
                }}
                pre code {{
                    background-color: transparent;
                    border: none;
                    padding: 0;
                }}
                blockquote {{
                    border-left: 4px solid #3498db;
                    padding-left: 1em;
                    margin-left: 0;
                    color: #666;
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
                    color: #3498db;
                    text-decoration: none;
                }}
                a:hover {{
                    text-decoration: underline;
                }}
                hr {{
                    border: none;
                    border-top: 1px solid #bdc3c7;
                    margin: 1em 0;
                }}
            </style>
        </head>
        <body>
            {body}
        </body>
        </html>
        """

        return html

    def clear_content(self):
        """Clear the displayed content."""
        self.clear()
        self.content_changed.emit("")

    def append_markdown(self, markdown_text: str):
        """
        Append markdown content to existing content.

        Args:
            markdown_text: Markdown text to append
        """
        # Get current HTML
        current_html = self.toHtml()

        # Convert new markdown to HTML
        new_html = self._markdown_to_html(markdown_text)

        # Append (simplified - just concatenate body content)
        self.append(new_html)
