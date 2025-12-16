"""
Document viewer widgets for BMLibrarian Lite.

Provides tabbed document viewing components:
- PDFViewerTab: Tab for viewing PDF documents with text selection
- FullTextTab: Tab for viewing full text/markdown content
- LiteDocumentViewWidget: Combined tabbed document viewer

Usage:
    from bmlibrarian_lite.gui.document_viewer import LiteDocumentViewWidget

    viewer = LiteDocumentViewWidget()
    text = viewer.load_file("/path/to/document.pdf")
    print(viewer.get_text())
"""

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
    QScrollArea,
    QLabel,
)
from PySide6.QtCore import Qt

from bmlibrarian_lite.resources.styles.dpi_scale import get_font_scale

logger = logging.getLogger(__name__)


class PDFViewerTab(QWidget):
    """
    Tab for viewing PDF documents with text selection.

    Uses PyMuPDF (fitz) for PDF text extraction and displays
    the extracted text in a scrollable text browser.

    Attributes:
        text_viewer: The text viewer widget
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize PDF viewer tab.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)
        self.scale = get_font_scale()
        self._pdf_path: Optional[str] = None
        self._pdf_text: str = ""
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Use QTextBrowser for displaying extracted PDF text
        self.text_viewer = QTextBrowser()
        self.text_viewer.setReadOnly(True)
        self.text_viewer.setOpenExternalLinks(True)
        layout.addWidget(self.text_viewer)

    def load_pdf(self, pdf_path: str) -> bool:
        """
        Load a PDF file.

        Args:
            pdf_path: Path to PDF file

        Returns:
            True if loaded successfully
        """
        path = Path(pdf_path)
        if not path.exists():
            logger.warning(f"PDF file not found: {pdf_path}")
            return False

        try:
            import fitz  # PyMuPDF

            doc = fitz.open(pdf_path)
            text_parts = []
            for page_num, page in enumerate(doc, 1):
                text_parts.append(f"--- Page {page_num} ---\n")
                text_parts.append(page.get_text())
            doc.close()

            self._pdf_path = pdf_path
            self._pdf_text = "\n".join(text_parts)
            self.text_viewer.setPlainText(self._pdf_text)
            return True

        except ImportError:
            logger.error("PyMuPDF not installed. Install with: pip install pymupdf")
            self.text_viewer.setPlainText(
                "PDF viewing requires PyMuPDF.\n"
                "Install with: pip install pymupdf"
            )
            return False
        except Exception as e:
            logger.error(f"Failed to load PDF: {e}")
            return False

    def get_text(self) -> str:
        """
        Get all text from the loaded PDF.

        Returns:
            Extracted text or empty string
        """
        return self._pdf_text

    def get_pdf_path(self) -> Optional[str]:
        """
        Get the path of the currently loaded PDF.

        Returns:
            PDF file path or None if no PDF is loaded
        """
        return self._pdf_path

    def clear(self) -> None:
        """Clear the PDF viewer."""
        self._pdf_path = None
        self._pdf_text = ""
        self.text_viewer.clear()


class FullTextTab(QWidget):
    """
    Tab for viewing full text / markdown content.

    Uses QTextBrowser with basic markdown support.

    Attributes:
        content_viewer: The text viewer widget
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize full text tab.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)
        self.scale = get_font_scale()
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Use QTextBrowser with markdown support
        self.content_viewer = QTextBrowser()
        self.content_viewer.setReadOnly(True)
        self.content_viewer.setOpenExternalLinks(True)
        layout.addWidget(self.content_viewer)

    def set_content(self, text: str) -> None:
        """
        Set the text content to display.

        Args:
            text: Text content (plain text or markdown)
        """
        # Try to render as markdown if it looks like markdown
        if self._looks_like_markdown(text):
            self.content_viewer.setMarkdown(text)
        else:
            self.content_viewer.setPlainText(text)

    def _looks_like_markdown(self, text: str) -> bool:
        """
        Check if text appears to be markdown.

        Args:
            text: Text to check

        Returns:
            True if text appears to contain markdown
        """
        markdown_indicators = ['#', '**', '__', '```', '- ', '* ', '1. ', '[', '](']
        return any(indicator in text for indicator in markdown_indicators)

    def get_text(self) -> str:
        """
        Get the current text content.

        Returns:
            Current text content
        """
        return self.content_viewer.toPlainText()

    def clear(self) -> None:
        """Clear the content."""
        self.content_viewer.clear()


class LiteDocumentViewWidget(QWidget):
    """
    Simplified document view widget for BMLibrarian Lite.

    Provides two tabs:
    - PDF tab: PDF viewer with text selection
    - Full Text tab: Plain text / markdown viewer

    Unlike the full version, this does not include database features,
    PDF discovery, or chunk embedding.

    Attributes:
        pdf_tab: The PDF viewer tab
        fulltext_tab: The full text viewer tab
        tab_widget: The tab container widget

    Example:
        viewer = LiteDocumentViewWidget()
        text = viewer.load_file("/path/to/paper.pdf")
        title = viewer.get_title()
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize document view widget.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)
        self.scale = get_font_scale()
        self._current_text: str = ""
        self._current_title: str = ""
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Tab widget
        self.tab_widget = QTabWidget()

        # Tab 1: PDF Viewer
        self.pdf_tab = PDFViewerTab()
        self.tab_widget.addTab(self.pdf_tab, "PDF")

        # Tab 2: Full Text
        self.fulltext_tab = FullTextTab()
        self.tab_widget.addTab(self.fulltext_tab, "Full Text")

        layout.addWidget(self.tab_widget)

    def load_file(self, file_path: str) -> str:
        """
        Load a document file.

        Args:
            file_path: Path to document file

        Returns:
            Extracted text content

        Raises:
            ValueError: If file type is not supported or file is empty
        """
        path = Path(file_path)
        self._current_title = path.name

        if path.suffix.lower() == '.pdf':
            return self._load_pdf(file_path)
        elif path.suffix.lower() in ['.txt', '.md']:
            return self._load_text(file_path)
        else:
            raise ValueError(f"Unsupported file type: {path.suffix}")

    def _load_pdf(self, file_path: str) -> str:
        """
        Load a PDF file.

        Args:
            file_path: Path to PDF file

        Returns:
            Extracted text content
        """
        # Load into PDF tab
        if self.pdf_tab.load_pdf(file_path):
            text = self.pdf_tab.get_text()
            self._current_text = text
            # Also show in full text tab
            self.fulltext_tab.set_content(text)
            # Switch to PDF tab
            self.tab_widget.setCurrentIndex(0)
            return text
        else:
            # PDF loading failed, try extracting text manually
            try:
                import fitz
                doc = fitz.open(file_path)
                text = ""
                for page in doc:
                    text += page.get_text()
                doc.close()
                self._current_text = text
                self.fulltext_tab.set_content(text)
                # Switch to full text tab since PDF view failed
                self.tab_widget.setCurrentIndex(1)
                return text
            except Exception as e:
                logger.error(f"Failed to extract PDF text: {e}")
                return ""

    def _load_text(self, file_path: str) -> str:
        """
        Load a text/markdown file.

        Args:
            file_path: Path to text file

        Returns:
            File content
        """
        text = Path(file_path).read_text(encoding='utf-8')
        self._current_text = text
        self.fulltext_tab.set_content(text)
        # Switch to full text tab
        self.tab_widget.setCurrentIndex(1)
        return text

    def get_text(self) -> str:
        """
        Get the current document text.

        Returns:
            Document text content
        """
        return self._current_text

    def set_text(self, text: str, title: str = "") -> None:
        """
        Set document text directly without loading from file.

        Useful for loading text from citations or database records.

        Args:
            text: Document text content
            title: Document title
        """
        self._current_text = text
        self._current_title = title
        self.fulltext_tab.set_content(text)

    def get_title(self) -> str:
        """
        Get the current document title.

        Returns:
            Document title (filename)
        """
        return self._current_title

    def set_title(self, title: str) -> None:
        """
        Set the document title.

        Args:
            title: Document title
        """
        self._current_title = title

    def clear(self) -> None:
        """Clear all displayed content."""
        self._current_text = ""
        self._current_title = ""
        self.pdf_tab.clear()
        self.fulltext_tab.clear()

    def show_pdf_tab(self) -> None:
        """Switch to the PDF tab."""
        self.tab_widget.setCurrentIndex(0)

    def show_fulltext_tab(self) -> None:
        """Switch to the Full Text tab."""
        self.tab_widget.setCurrentIndex(1)
