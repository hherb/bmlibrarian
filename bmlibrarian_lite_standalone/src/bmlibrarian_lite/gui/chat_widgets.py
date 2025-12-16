"""
Chat UI widgets for BMLibrarian Lite.

Provides chat interface components with markdown support:
- ChatBubble: Styled message bubble with markdown rendering
- generate_markdown_html(): Pure function for converting markdown to styled HTML

Usage:
    from bmlibrarian_lite.gui.chat_widgets import ChatBubble, generate_markdown_html

    # Create a chat bubble
    bubble = ChatBubble("Hello **world**!", is_user=True, scale=scale_dict)

    # Or just generate HTML
    html = generate_markdown_html("Hello **world**!", font_size=12, text_color="#333")
"""

import markdown
from typing import Optional

from PySide6.QtWidgets import (
    QFrame,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt

from bmlibrarian_lite.resources.styles.dpi_scale import FONT_FAMILY

# Constants for chat bubble styling
BUBBLE_RADIUS_MIN = 20  # Minimum bubble corner radius in scaled pixels
BUBBLE_RADIUS_MULTIPLIER = 1.8  # Multiplier for bubble radius from scale
BROWSER_HEIGHT_MARGIN = 8  # Extra margin for text browser height to prevent clipping


def generate_markdown_html(
    text: str,
    font_size: int,
    text_color: str,
    font_family: str = FONT_FAMILY,
) -> str:
    """
    Convert markdown text to styled HTML.

    Pure function that generates a complete HTML document from markdown text,
    with comprehensive styling for various markdown elements.

    Args:
        text: Markdown text to convert
        font_size: Base font size in points
        text_color: Text color as hex string (e.g., "#333333")
        font_family: Font family name (default: system FONT_FAMILY)

    Returns:
        Complete HTML document string with embedded styles

    Example:
        html = generate_markdown_html(
            "**Bold** and *italic* text",
            font_size=12,
            text_color="#1A1A1A"
        )
    """
    # Configure markdown processor
    md = markdown.Markdown(
        extensions=[
            "extra",  # Tables, fenced code blocks, etc.
            "nl2br",  # Newline to <br>
            "sane_lists",  # Better list handling
        ]
    )

    # Convert markdown to HTML body
    html_body = md.convert(text)

    # Create styled HTML document
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{
                font-family: {font_family};
                font-size: {font_size}pt;
                line-height: 1.5;
                color: {text_color};
                background-color: transparent;
                margin: 0;
                padding: 0;
            }}
            p {{
                margin: 0.3em 0;
            }}
            code {{
                background-color: rgba(0,0,0,0.05);
                border-radius: 3px;
                padding: 2px 4px;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 0.9em;
            }}
            pre {{
                background-color: rgba(0,0,0,0.05);
                border-radius: 6px;
                padding: 8px;
                overflow-x: auto;
            }}
            pre code {{
                background-color: transparent;
                padding: 0;
            }}
            ul, ol {{
                margin: 0.3em 0;
                padding-left: 1.5em;
            }}
            li {{
                margin: 0.2em 0;
            }}
            blockquote {{
                border-left: 3px solid #3498db;
                padding-left: 0.8em;
                margin-left: 0;
                color: #666;
            }}
            strong {{
                font-weight: 600;
            }}
            em {{
                font-style: italic;
            }}
            a {{
                color: #2196F3;
                text-decoration: none;
            }}
            a:hover {{
                text-decoration: underline;
            }}
            hr {{
                border: none;
                border-top: 1px solid rgba(0,0,0,0.1);
                margin: 0.8em 0;
            }}
            h1, h2, h3, h4, h5, h6 {{
                margin-top: 0.6em;
                margin-bottom: 0.3em;
                font-weight: 600;
            }}
            h1 {{ font-size: 1.4em; }}
            h2 {{ font-size: 1.2em; }}
            h3 {{ font-size: 1.1em; }}
            table {{
                border-collapse: collapse;
                margin: 0.5em 0;
            }}
            th, td {{
                border: 1px solid rgba(0,0,0,0.15);
                padding: 4px 8px;
                text-align: left;
            }}
            th {{
                background-color: rgba(0,0,0,0.05);
                font-weight: 600;
            }}
        </style>
    </head>
    <body>{html_body}</body>
    </html>
    """


class ChatBubble(QFrame):
    """
    A single chat message bubble with DPI-aware dimensions and markdown support.

    Renders markdown text in a styled bubble with appropriate colors for
    user vs AI messages. Matches the styling of the full BMLibrarian
    document interrogation interface.

    Attributes:
        original_text: The raw markdown text (for export)
        is_user: True if this is a user message

    Example:
        scale = get_font_scale()
        bubble = ChatBubble(
            "Here's a **bold** response with `code`.",
            is_user=False,
            scale=scale,
        )
        layout.addWidget(bubble)
    """

    # Color constants for message types
    USER_BG_COLOR = "#F4EAD5"  # Pale sand background
    USER_TEXT_COLOR = "#333333"
    AI_BG_COLOR = "#E3F2FD"  # Pale blue background
    AI_TEXT_COLOR = "#1A1A1A"

    def __init__(
        self,
        text: str,
        is_user: bool,
        scale: dict,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Initialize chat bubble with markdown rendering.

        Args:
            text: Message text (supports markdown formatting)
            is_user: True if user message, False if AI message
            scale: Font-relative scaling dimensions from get_font_scale()
            parent: Optional parent widget
        """
        super().__init__(parent)

        # Store original text for conversation export
        self.original_text = text
        self.is_user = is_user

        # Get scaled dimensions - use larger radius for rounded corners
        radius = max(BUBBLE_RADIUS_MIN, int(scale['bubble_radius'] * BUBBLE_RADIUS_MULTIPLIER))

        # Allow bubble to expand horizontally based on content
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        # Determine colors based on message type
        if is_user:
            bg_color = self.USER_BG_COLOR
            text_color = self.USER_TEXT_COLOR
        else:
            bg_color = self.AI_BG_COLOR
            text_color = self.AI_TEXT_COLOR

        # Apply frame styling with rounded corners
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_color};
                border-radius: {radius}px;
            }}
        """)

        # Layout with padding
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            scale['padding_large'],
            scale['padding_medium'],
            scale['padding_large'],
            scale['padding_medium']
        )
        layout.setSpacing(0)

        # Use QTextBrowser for markdown rendering
        message_browser = QTextBrowser()
        message_browser.setOpenExternalLinks(True)
        message_browser.setFrameShape(QFrame.Shape.NoFrame)
        message_browser.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        # Generate styled HTML from markdown
        font_size = scale['font_large']
        html = generate_markdown_html(text, font_size, text_color)
        message_browser.setHtml(html)

        # Style the browser to be transparent
        message_browser.setStyleSheet(f"""
            QTextBrowser {{
                background-color: transparent;
                border: none;
                color: {text_color};
            }}
        """)

        # Make the browser auto-resize to content
        message_browser.document().setDocumentMargin(0)
        message_browser.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        message_browser.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Store reference for dynamic height adjustment
        self._message_browser = message_browser

        # Connect document size changes to height adjustment
        message_browser.document().documentLayout().documentSizeChanged.connect(
            self._adjust_browser_height
        )

        layout.addWidget(message_browser)

        # Initial height adjustment after widget is added
        self._adjust_browser_height()

    def _adjust_browser_height(self) -> None:
        """Adjust the QTextBrowser height to fit its content."""
        if hasattr(self, '_message_browser') and self._message_browser:
            doc_height = self._message_browser.document().size().height()
            # Add small margin to prevent clipping
            self._message_browser.setFixedHeight(int(doc_height) + BROWSER_HEIGHT_MARGIN)
