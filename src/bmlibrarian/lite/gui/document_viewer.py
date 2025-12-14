"""
Document viewer widgets for BMLibrarian Lite.

Provides tabbed document viewing components:
- PDFViewerTab: Tab for viewing PDF documents with text selection
- FullTextTab: Tab for viewing full text/markdown content
- LiteDocumentViewWidget: Combined tabbed document viewer

Usage:
    from bmlibrarian.lite.gui.document_viewer import LiteDocumentViewWidget

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
)

from bmlibrarian.gui.qt.resources.styles.dpi_scale import get_font_scale

logger = logging.getLogger(__name__)


class PDFViewerTab(QWidget):
    """
    Tab for viewing PDF documents with text selection.

    Wraps the PDFTextViewerWidget to provide PDF viewing capabilities
    within a tab interface.

    Attributes:
        pdf_viewer: The underlying PDF viewer widget
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
        from bmlibrarian.gui.qt.widgets.pdf_text_viewer import PDFTextViewerWidget

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.pdf_viewer = PDFTextViewerWidget()
        layout.addWidget(self.pdf_viewer)

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
            self.pdf_viewer.load_pdf(pdf_path)
            self._pdf_path = pdf_path
            self._pdf_text = self.pdf_viewer.get_all_text()
            return True
        except Exception as e:
            logger.error(f"Failed to load PDF: {e}")
            return False

    def get_text(self) -> str:
        """
        Get all text from the loaded PDF.

        Returns:
            Extracted text or empty string
        """
        return self.pdf_viewer.get_all_text()

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
        self.pdf_viewer.clear()


class FullTextTab(QWidget):
    """
    Tab for viewing full text / markdown content.

    Uses MarkdownViewer if available, otherwise falls back to QTextBrowser.

    Attributes:
        content_viewer: The text/markdown viewer widget
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize full text tab.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)
        self.scale = get_font_scale()
        self._has_markdown = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Try to use MarkdownViewer if available, else fallback to QTextBrowser
        try:
            from bmlibrarian.gui.qt.widgets.markdown_viewer import MarkdownViewer
            self.content_viewer = MarkdownViewer()
            self._has_markdown = True
        except ImportError:
            # Fallback to basic QTextBrowser
            self.content_viewer = QTextBrowser()
            self.content_viewer.setReadOnly(True)
            self.content_viewer.setOpenExternalLinks(True)
            self._has_markdown = False

        layout.addWidget(self.content_viewer)

    def set_content(self, text: str) -> None:
        """
        Set the text content to display.

        Args:
            text: Text content (plain text or markdown)
        """
        if self._has_markdown:
            self.content_viewer.set_markdown(text)
        else:
            self.content_viewer.setPlainText(text)

    def get_text(self) -> str:
        """
        Get the current text content.

        Returns:
            Current text content
        """
        return self.content_viewer.toPlainText()

    def clear(self) -> None:
        """Clear the content."""
        if self._has_markdown:
            self.content_viewer.clear_content()
        else:
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
            # PDF loading failed (e.g., corrupted file), try extracting text manually
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
