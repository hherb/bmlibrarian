"""
Syntax highlighter for markdown with citation marker support.

Provides highlighting for:
- Markdown headers, bold, italic, code, links
- Citation markers [@id:12345:Label]
- Block quotes and lists
"""

import re
from typing import List, Tuple
from PySide6.QtGui import (
    QSyntaxHighlighter, QTextCharFormat, QColor, QFont, QTextDocument
)
from PySide6.QtCore import Qt


class MarkdownCitationHighlighter(QSyntaxHighlighter):
    """
    Syntax highlighter for markdown with citation marker support.

    Highlights:
    - Headers (# ## ###)
    - Bold (**text**)
    - Italic (*text* or _text_)
    - Code (`code` and ```blocks```)
    - Links [text](url)
    - Citation markers [@id:12345:Label]
    - Block quotes (> text)
    - Lists (- item, * item, 1. item)
    """

    def __init__(self, document: QTextDocument) -> None:
        """
        Initialize syntax highlighter.

        Args:
            document: QTextDocument to highlight
        """
        super().__init__(document)
        self._rules: List[Tuple[re.Pattern, QTextCharFormat]] = []
        self._setup_rules()

    def _setup_rules(self) -> None:
        """Set up highlighting rules."""
        # Citation marker - prominent blue
        citation_format = QTextCharFormat()
        citation_format.setForeground(QColor("#1565C0"))  # Blue
        citation_format.setFontWeight(QFont.Weight.Bold)
        citation_format.setBackground(QColor("#E3F2FD"))  # Light blue background
        self._rules.append((
            re.compile(r'\[@id:\d+:[^\]]+\]'),
            citation_format
        ))

        # Headers - dark blue, bold
        header_format = QTextCharFormat()
        header_format.setForeground(QColor("#0D47A1"))
        header_format.setFontWeight(QFont.Weight.Bold)
        # H1
        self._rules.append((re.compile(r'^# .+$', re.MULTILINE), header_format))
        # H2
        h2_format = QTextCharFormat()
        h2_format.setForeground(QColor("#1565C0"))
        h2_format.setFontWeight(QFont.Weight.Bold)
        self._rules.append((re.compile(r'^## .+$', re.MULTILINE), h2_format))
        # H3-H6
        h3_format = QTextCharFormat()
        h3_format.setForeground(QColor("#1976D2"))
        h3_format.setFontWeight(QFont.Weight.Bold)
        self._rules.append((re.compile(r'^#{3,6} .+$', re.MULTILINE), h3_format))

        # Bold - dark text, bold
        bold_format = QTextCharFormat()
        bold_format.setFontWeight(QFont.Weight.Bold)
        self._rules.append((
            re.compile(r'\*\*[^*]+\*\*'),
            bold_format
        ))
        self._rules.append((
            re.compile(r'__[^_]+__'),
            bold_format
        ))

        # Italic - dark text, italic
        italic_format = QTextCharFormat()
        italic_format.setFontItalic(True)
        self._rules.append((
            re.compile(r'(?<!\*)\*(?!\*)([^*]+)(?<!\*)\*(?!\*)'),
            italic_format
        ))
        self._rules.append((
            re.compile(r'(?<!_)_(?!_)([^_]+)(?<!_)_(?!_)'),
            italic_format
        ))

        # Inline code - monospace, gray background
        code_format = QTextCharFormat()
        code_format.setFontFamily("Consolas, Monaco, monospace")
        code_format.setForeground(QColor("#D32F2F"))  # Red
        code_format.setBackground(QColor("#F5F5F5"))
        self._rules.append((
            re.compile(r'`[^`]+`'),
            code_format
        ))

        # Links - blue, underline
        link_format = QTextCharFormat()
        link_format.setForeground(QColor("#1976D2"))
        link_format.setFontUnderline(True)
        self._rules.append((
            re.compile(r'\[([^\]]+)\]\([^\)]+\)'),
            link_format
        ))

        # Block quote - gray, italic
        quote_format = QTextCharFormat()
        quote_format.setForeground(QColor("#616161"))
        quote_format.setFontItalic(True)
        self._rules.append((
            re.compile(r'^>\s?.+$', re.MULTILINE),
            quote_format
        ))

        # List items - bullet/number in different color
        list_format = QTextCharFormat()
        list_format.setForeground(QColor("#7B1FA2"))  # Purple
        self._rules.append((
            re.compile(r'^[\s]*[-*+]\s', re.MULTILINE),
            list_format
        ))
        self._rules.append((
            re.compile(r'^[\s]*\d+\.\s', re.MULTILINE),
            list_format
        ))

        # Horizontal rule
        hr_format = QTextCharFormat()
        hr_format.setForeground(QColor("#BDBDBD"))
        self._rules.append((
            re.compile(r'^[-*_]{3,}$', re.MULTILINE),
            hr_format
        ))

        # URLs (standalone)
        url_format = QTextCharFormat()
        url_format.setForeground(QColor("#0277BD"))
        url_format.setFontUnderline(True)
        self._rules.append((
            re.compile(r'https?://[^\s\)]+'),
            url_format
        ))

    def highlightBlock(self, text: str) -> None:
        """
        Apply syntax highlighting to a block of text.

        Args:
            text: Text block to highlight
        """
        for pattern, format_ in self._rules:
            for match in pattern.finditer(text):
                start = match.start()
                length = match.end() - start
                self.setFormat(start, length, format_)

        # Handle multi-line code blocks
        self._highlight_code_blocks(text)

    def _highlight_code_blocks(self, text: str) -> None:
        """
        Handle multi-line code block highlighting.

        Args:
            text: Text block to check
        """
        # Check for code fence
        code_fence = re.compile(r'^```')

        # State: 0 = normal, 1 = in code block
        self.setCurrentBlockState(0)

        if self.previousBlockState() == 1:
            # We're inside a code block
            if code_fence.match(text):
                # End of code block
                self.setCurrentBlockState(0)
            else:
                # Still in code block
                self.setCurrentBlockState(1)
                code_format = QTextCharFormat()
                code_format.setFontFamily("Consolas, Monaco, monospace")
                code_format.setForeground(QColor("#D32F2F"))
                code_format.setBackground(QColor("#F5F5F5"))
                self.setFormat(0, len(text), code_format)
        else:
            # Check if this line starts a code block
            if code_fence.match(text):
                self.setCurrentBlockState(1)
                code_format = QTextCharFormat()
                code_format.setForeground(QColor("#757575"))
                self.setFormat(0, len(text), code_format)


class CitationHighlighter(QSyntaxHighlighter):
    """
    Minimal highlighter for just citation markers.

    Use this for performance when full markdown highlighting is not needed.
    """

    def __init__(self, document: QTextDocument) -> None:
        """
        Initialize citation-only highlighter.

        Args:
            document: QTextDocument to highlight
        """
        super().__init__(document)
        self._citation_pattern = re.compile(r'\[@id:\d+:[^\]]+\]')
        self._citation_format = QTextCharFormat()
        self._citation_format.setForeground(QColor("#1565C0"))
        self._citation_format.setFontWeight(QFont.Weight.Bold)
        self._citation_format.setBackground(QColor("#E3F2FD"))

    def highlightBlock(self, text: str) -> None:
        """
        Apply citation highlighting to a block of text.

        Args:
            text: Text block to highlight
        """
        for match in self._citation_pattern.finditer(text):
            self.setFormat(match.start(), match.end() - match.start(), self._citation_format)
