"""
Document Interrogation tab for BMLibrarian Lite.

Provides an interactive Q&A interface for loaded documents using
RAG (Retrieval Augmented Generation) pattern.

Features:
- Split-pane layout: document viewer (60%) / chat interface (40%)
- Tabbed document viewer: PDF / Full Text tabs
- Styled chat bubbles with markdown rendering
- Conversation history with export
"""

import logging
import markdown
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QPushButton,
    QLabel,
    QFileDialog,
    QScrollArea,
    QFrame,
    QSplitter,
    QTabWidget,
    QSizePolicy,
    QTextBrowser,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QDialog,
)
from PySide6.QtCore import Qt, Signal, QThread, QTimer

from bmlibrarian.gui.qt.resources.styles.dpi_scale import scaled, get_font_scale, FONT_FAMILY
from bmlibrarian.gui.qt.resources.styles.stylesheet_generator import StylesheetGenerator

from ..config import LiteConfig
from ..storage import LiteStorage
from ..agents import LiteInterrogationAgent

logger = logging.getLogger(__name__)


class AnswerWorker(QThread):
    """
    Background worker for generating answers.

    Signals:
        finished: Emitted when answer is ready (answer, sources)
        error: Emitted on error (error message)
    """

    finished = Signal(str, list)  # answer, sources
    error = Signal(str)

    def __init__(
        self,
        agent: LiteInterrogationAgent,
        question: str,
    ) -> None:
        """
        Initialize the answer worker.

        Args:
            agent: Interrogation agent
            question: Question to answer
        """
        super().__init__()
        self.agent = agent
        self.question = question

    def run(self) -> None:
        """Generate answer in background thread."""
        try:
            answer, sources = self.agent.ask(self.question)
            self.finished.emit(answer, sources)
        except Exception as e:
            logger.exception("Answer generation error")
            self.error.emit(str(e))


class PDFDiscoveryWorker(QThread):
    """
    Background worker for PDF discovery and download.

    Discovers PDF sources and downloads to year-based folder structure.
    Includes verification to detect when wrong PDF is downloaded.

    Signals:
        progress: Emitted with (stage, status) during download
        finished: Emitted with file_path when download succeeds
        verification_warning: Emitted with (file_path, warning_message) on verification mismatch
        error: Emitted with error message on failure
    """

    progress = Signal(str, str)  # stage, status
    finished = Signal(str)  # file_path on success
    verification_warning = Signal(str, str)  # file_path, warning_message
    error = Signal(str)  # error message

    def __init__(
        self,
        doc_dict: Dict[str, Any],
        output_dir: Path,
        unpaywall_email: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Initialize PDF discovery worker.

        Args:
            doc_dict: Document dictionary with doi, pmid, title, year, etc.
            output_dir: Base directory for PDF storage (year subdirs created)
            unpaywall_email: Email for Unpaywall API
            parent: Optional parent widget
        """
        super().__init__(parent)
        self.doc_dict = doc_dict
        self.output_dir = output_dir
        self.unpaywall_email = unpaywall_email
        self._cancelled = False

    def run(self) -> None:
        """Execute PDF discovery and download with verification."""
        try:
            from bmlibrarian.discovery import download_pdf_for_document

            def progress_callback(stage: str, status: str) -> None:
                if not self._cancelled:
                    self.progress.emit(stage, status)

            result = download_pdf_for_document(
                document=self.doc_dict,
                output_dir=self.output_dir,
                unpaywall_email=self.unpaywall_email,
                progress_callback=progress_callback,
                verify_content=True,  # Enable verification to detect wrong PDFs
                delete_on_mismatch=False,  # Keep file but warn user
            )

            if self._cancelled:
                return

            if result.success and result.file_path:
                # Check if verification detected a mismatch
                if result.verified is False:
                    # Build warning message with details
                    warnings = result.verification_warnings or []
                    warning_parts = []

                    if result.extracted_doi and self.doc_dict.get('doi'):
                        warning_parts.append(
                            f"Expected DOI: {self.doc_dict['doi']}, "
                            f"Found: {result.extracted_doi}"
                        )
                    if result.extracted_title:
                        warning_parts.append(f"PDF title: {result.extracted_title[:80]}...")

                    warning_msg = "PDF verification FAILED - wrong document may have been downloaded.\n"
                    if warning_parts:
                        warning_msg += "\n".join(warning_parts)
                    elif warnings:
                        warning_msg += "; ".join(warnings)

                    logger.warning(f"PDF mismatch detected: {warning_msg}")
                    self.verification_warning.emit(result.file_path, warning_msg)
                else:
                    self.finished.emit(result.file_path)
            else:
                self.error.emit(result.error_message or "Unknown error")

        except Exception as e:
            logger.exception("PDF discovery failed")
            if not self._cancelled:
                self.error.emit(str(e))

    def cancel(self) -> None:
        """Request cancellation of the operation."""
        self._cancelled = True


class ChatBubble(QFrame):
    """
    A single chat message bubble with DPI-aware dimensions and markdown support.

    Matches the styling of the full BMLibrarian document interrogation.
    """

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
        radius = max(20, int(scale['bubble_radius'] * 1.8))

        # Allow bubble to expand horizontally based on content
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        # Determine colors based on message type
        if is_user:
            bg_color = "#F4EAD5"  # Pale sand background
            text_color = "#333333"
        else:
            bg_color = "#E3F2FD"  # Pale blue background
            text_color = "#1A1A1A"

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

        # Configure markdown processor
        md = markdown.Markdown(
            extensions=[
                "extra",  # Tables, fenced code blocks, etc.
                "nl2br",  # Newline to <br>
                "sane_lists",  # Better list handling
            ]
        )

        # Convert markdown to HTML
        html_body = md.convert(text)

        # Create styled HTML document
        font_size = scale['font_large']
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: {FONT_FAMILY};
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
            self._message_browser.setFixedHeight(int(doc_height) + 8)


class PDFViewerTab(QWidget):
    """Tab for viewing PDF documents with text selection."""

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

    def clear(self) -> None:
        """Clear the PDF viewer."""
        self._pdf_path = None
        self._pdf_text = ""
        self.pdf_viewer.clear()


class FullTextTab(QWidget):
    """Tab for viewing full text / markdown content."""

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

    def get_title(self) -> str:
        """
        Get the current document title.

        Returns:
            Document title (filename)
        """
        return self._current_title

    def clear(self) -> None:
        """Clear all displayed content."""
        self._current_text = ""
        self._current_title = ""
        self.pdf_tab.clear()
        self.fulltext_tab.clear()


class DocumentInterrogationTab(QWidget):
    """
    Document Interrogation tab widget with split-pane layout.

    Provides interface for:
    - Loading documents (PDF/text) with tabbed viewer
    - Asking questions about the document with styled chat bubbles
    - Viewing conversation history
    - Exporting conversations

    Attributes:
        config: Lite configuration
        storage: Storage layer
    """

    status_message = Signal(str)

    def __init__(
        self,
        config: LiteConfig,
        storage: LiteStorage,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Initialize the document interrogation tab.

        Args:
            config: Lite configuration
            storage: Storage layer
            parent: Optional parent widget
        """
        super().__init__(parent)
        self.config = config
        self.storage = storage
        self._agent = LiteInterrogationAgent(config=config, storage=storage)
        self._worker: Optional[AnswerWorker] = None
        self._pdf_worker: Optional[PDFDiscoveryWorker] = None
        self._pdf_progress_dialog: Optional[QProgressDialog] = None
        self._document_loaded = False
        self._current_doc_metadata: Optional[dict] = None  # For PDF discovery
        self._current_pdf_path: Optional[Path] = None  # Track local PDF path
        self._pending_citation: Optional['Citation'] = None  # For async completion
        self._pending_fetch_title: Optional[str] = None  # For fetch button

        # Get DPI-aware font-relative scaling dimensions
        self.scale = get_font_scale()

        # Conversation history for export
        self.conversation_history: List[dict] = []

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Top bar with document controls
        top_bar = self._create_top_bar()
        layout.addWidget(top_bar)

        # Split pane: document viewer (left) / chat (right)
        splitter = self._create_split_pane()
        layout.addWidget(splitter)

    def _create_top_bar(self) -> QWidget:
        """Create top bar with file selector."""
        s = self.scale

        widget = QWidget()
        widget.setStyleSheet("""
            QWidget {
                background-color: #F5F5F5;
                border-bottom: 1px solid #D0D0D0;
            }
        """)
        bar_height = s['control_height_medium'] + s['padding_medium']
        widget.setFixedHeight(bar_height)

        layout = QHBoxLayout(widget)
        layout.setContentsMargins(
            s['padding_small'],
            s['padding_tiny'],
            s['padding_small'],
            s['padding_tiny']
        )
        layout.setSpacing(s['spacing_medium'])

        # Load document button
        self.load_btn = QPushButton("Load Document")
        self.load_btn.clicked.connect(self._load_document)
        self.load_btn.setFixedHeight(s['control_height_medium'])
        self.load_btn.setToolTip("Load a text, markdown, or PDF document")
        self.load_btn.setStyleSheet(f"""
            QPushButton {{
                padding: {s['padding_tiny']}px {s['padding_medium']}px;
                font-size: {s['font_small']}pt;
            }}
        """)
        layout.addWidget(self.load_btn)

        # Fetch PDF button (PDF discovery)
        self.fetch_pdf_btn = QPushButton("Fetch PDF")
        self.fetch_pdf_btn.clicked.connect(self._fetch_pdf_from_identifier)
        self.fetch_pdf_btn.setFixedHeight(s['control_height_medium'])
        self.fetch_pdf_btn.setToolTip(
            "Try to fetch PDF from DOI/PMID via PMC, Unpaywall, or DOI.org"
        )
        self.fetch_pdf_btn.setStyleSheet(f"""
            QPushButton {{
                padding: {s['padding_tiny']}px {s['padding_medium']}px;
                font-size: {s['font_small']}pt;
                background-color: #FFA726;
                color: white;
            }}
            QPushButton:hover {{
                background-color: #FF9800;
            }}
        """)
        layout.addWidget(self.fetch_pdf_btn)

        # Current document label
        self.doc_label = QLabel("No document loaded")
        self.doc_label.setStyleSheet(f"""
            QLabel {{
                color: #666;
                font-style: italic;
                font-size: {s['font_small']}pt;
            }}
        """)
        layout.addWidget(self.doc_label, 1)

        # Clear button
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self._clear_document)
        self.clear_btn.setEnabled(False)
        self.clear_btn.setFixedHeight(s['control_height_medium'])
        self.clear_btn.setToolTip("Clear the loaded document")
        self.clear_btn.setStyleSheet(f"""
            QPushButton {{
                padding: {s['padding_tiny']}px {s['padding_medium']}px;
                font-size: {s['font_small']}pt;
            }}
        """)
        layout.addWidget(self.clear_btn)

        # Wrong PDF button - for handling incorrectly downloaded PDFs
        self.wrong_pdf_btn = QPushButton("Wrong PDF")
        self.wrong_pdf_btn.clicked.connect(self._handle_wrong_pdf)
        self.wrong_pdf_btn.setEnabled(False)
        self.wrong_pdf_btn.setVisible(False)  # Only show when PDF is loaded
        self.wrong_pdf_btn.setFixedHeight(s['control_height_medium'])
        self.wrong_pdf_btn.setToolTip(
            "Report that this PDF is wrong - delete or reassign it"
        )
        self.wrong_pdf_btn.setStyleSheet(f"""
            QPushButton {{
                padding: {s['padding_tiny']}px {s['padding_medium']}px;
                font-size: {s['font_small']}pt;
                background-color: #FFE4E1;
                color: #8B0000;
            }}
            QPushButton:hover {{
                background-color: #FFB6C1;
            }}
        """)
        layout.addWidget(self.wrong_pdf_btn)

        return widget

    def _create_split_pane(self) -> QSplitter:
        """Create split pane with document viewer and chat interface."""
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left pane: Document viewer
        doc_pane = self._create_document_pane()
        splitter.addWidget(doc_pane)

        # Right pane: Chat interface
        chat_pane = self._create_chat_pane()
        splitter.addWidget(chat_pane)

        # Set initial sizes (60% document, 40% chat)
        splitter.setSizes([600, 400])

        return splitter

    def _create_document_pane(self) -> QWidget:
        """Create document viewer pane."""
        s = self.scale

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QLabel("Document Viewer")
        header.setStyleSheet(f"""
            QLabel {{
                background-color: #E0E0E0;
                padding: {s['padding_small']}px {s['padding_medium']}px;
                font-weight: bold;
                font-size: {s['font_large']}pt;
            }}
        """)
        layout.addWidget(header)

        # Document view widget (tabbed)
        self.document_view = LiteDocumentViewWidget()
        layout.addWidget(self.document_view, 1)

        return widget

    def _create_chat_pane(self) -> QWidget:
        """Create chat interface pane."""
        s = self.scale

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header with save button
        header_widget = QWidget()
        header_widget.setStyleSheet(f"""
            QWidget {{
                background-color: #E0E0E0;
            }}
        """)
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(
            s['padding_medium'], s['padding_small'],
            s['padding_medium'], s['padding_small']
        )
        header_layout.setSpacing(s['spacing_small'])

        # Header label
        header_label = QLabel("Chat")
        header_label.setStyleSheet(f"""
            QLabel {{
                font-weight: bold;
                font-size: {s['font_large']}pt;
                background-color: transparent;
            }}
        """)
        header_layout.addWidget(header_label)

        header_layout.addStretch()

        # Save conversation button
        self.save_btn = QPushButton("Save")
        self.save_btn.setToolTip("Save conversation as JSON or Markdown")
        self.save_btn.clicked.connect(self._on_save_conversation)
        self.save_btn.setFixedHeight(s['control_height_small'])
        self.save_btn.setStyleSheet(f"""
            QPushButton {{
                padding: {s['padding_tiny']}px {s['padding_small']}px;
                font-size: {s['font_small']}pt;
                background-color: #FFFFFF;
                border: 1px solid #CCC;
                border-radius: {s['radius_small']}px;
            }}
            QPushButton:hover {{
                background-color: #F0F0F0;
            }}
        """)
        header_layout.addWidget(self.save_btn)

        layout.addWidget(header_widget)

        # Chat messages area
        self.chat_scroll_area = QScrollArea()
        self.chat_scroll_area.setWidgetResizable(True)
        self.chat_scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #FAFAFA;
            }
        """)

        # Chat container
        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(
            s['spacing_medium'],
            s['spacing_medium'],
            s['spacing_medium'],
            s['spacing_medium']
        )
        self.chat_layout.setSpacing(s['spacing_medium'] * 2)
        self.chat_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Welcome message
        self._add_welcome_message()

        self.chat_scroll_area.setWidget(self.chat_container)
        layout.addWidget(self.chat_scroll_area, 1)

        # Progress/status label
        self.progress_label = QLabel("")
        self.progress_label.setStyleSheet(f"""
            QLabel {{
                color: #666;
                font-style: italic;
                padding: {s['padding_tiny']}px {s['padding_medium']}px;
                font-size: {s['font_small']}pt;
            }}
        """)
        self.progress_label.setVisible(False)
        layout.addWidget(self.progress_label)

        # Input area
        input_widget = self._create_input_area()
        layout.addWidget(input_widget)

        return widget

    def _create_input_area(self) -> QWidget:
        """Create message input area."""
        s = self.scale

        widget = QWidget()
        widget.setStyleSheet("""
            QWidget {
                background-color: white;
                border-top: 1px solid #CCC;
            }
        """)
        input_height = s['control_height_large'] + (s['padding_medium'] * 2)
        widget.setFixedHeight(input_height)

        layout = QHBoxLayout(widget)
        layout.setContentsMargins(
            s['spacing_medium'],
            s['spacing_medium'],
            s['spacing_medium'],
            s['spacing_medium']
        )
        layout.setSpacing(s['spacing_medium'])

        # Message input
        self.message_input = QTextEdit()
        self.message_input.setPlaceholderText("Ask a question about the document...")
        self.message_input.setStyleSheet(f"""
            QTextEdit {{
                border: 1px solid #CCC;
                border-radius: {s['padding_tiny']}px;
                padding: {s['padding_small']}px;
                font-size: {s['font_medium']}pt;
            }}
            QTextEdit:focus {{
                border: 1px solid #2196F3;
            }}
        """)
        self.message_input.setFixedHeight(s['control_height_large'])
        layout.addWidget(self.message_input, 1)

        # Send button
        self.send_btn = QPushButton("Send")
        self.send_btn.clicked.connect(self._ask_question)
        self.send_btn.setEnabled(False)
        btn_width = max(70, int(s['char_width'] * 8))
        self.send_btn.setFixedSize(btn_width, s['control_height_large'])
        self.send_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #2196F3;
                color: white;
                border-radius: {s['padding_tiny']}px;
                font-weight: bold;
                font-size: {s['font_medium']}pt;
            }}
            QPushButton:hover {{
                background-color: #1976D2;
            }}
            QPushButton:disabled {{
                background-color: #CCC;
                color: #666;
            }}
        """)
        layout.addWidget(self.send_btn)

        return widget

    def _add_welcome_message(self) -> None:
        """Add welcome message to chat."""
        welcome_text = (
            "Welcome to Document Interrogation!\n\n"
            "Load a document to get started. "
            "I'll help you analyze and answer questions about your document."
        )
        self._add_chat_bubble(welcome_text, is_user=False, track_history=False)

    def _add_chat_bubble(
        self,
        text: str,
        is_user: bool,
        track_history: bool = True,
    ) -> None:
        """
        Add a chat bubble to the chat area.

        Args:
            text: Message text (supports markdown formatting)
            is_user: True if user message, False if AI message
            track_history: If True, add message to conversation history
        """
        s = self.scale

        # Track in conversation history for export
        if track_history:
            self.conversation_history.append({
                "role": "user" if is_user else "assistant",
                "content": text,
                "timestamp": datetime.now().isoformat()
            })

        # Create the bubble
        bubble = ChatBubble(text, is_user, s)

        # Create icon label
        icon_label = QLabel("You" if is_user else "AI")
        icon_label.setStyleSheet(f"""
            QLabel {{
                font-size: {s['font_small']}pt;
                font-weight: bold;
                background-color: transparent;
                color: {'#666' if is_user else '#2196F3'};
            }}
        """)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        icon_label.setFixedWidth(int(s['char_width'] * 4))

        # Create container for icon + bubble
        container = QWidget()
        container.setStyleSheet("background-color: transparent;")
        container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        container_layout = QHBoxLayout(container)
        container_layout.setSpacing(s['spacing_small'])

        if is_user:
            # User messages: left-aligned with right padding
            container_layout.setContentsMargins(
                s.get('bubble_margin_small', s['spacing_small']),
                0,
                s.get('bubble_margin_large', s['spacing_large']),
                0
            )
        else:
            # AI messages: right-aligned with left padding
            container_layout.setContentsMargins(
                s.get('bubble_margin_large', s['spacing_large']),
                0,
                s.get('bubble_margin_small', s['spacing_small']),
                0
            )

        container_layout.addWidget(icon_label, 0)
        container_layout.addWidget(bubble, 1)

        self.chat_layout.addWidget(container)

        # Auto-scroll to bottom
        QTimer.singleShot(100, self._scroll_to_bottom)

    def _scroll_to_bottom(self) -> None:
        """Scroll chat area to bottom."""
        scrollbar = self.chat_scroll_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _load_document(self) -> None:
        """Load a document from file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Document",
            str(Path.home()),
            "Documents (*.txt *.md *.pdf);;All Files (*)",
        )

        if not file_path:
            return

        path = Path(file_path)

        try:
            self.progress_label.setText("Loading document...")
            self.progress_label.setVisible(True)

            # Load into document view and get text
            text = self.document_view.load_file(file_path)

            if not text.strip():
                self.doc_label.setText("Error: Document is empty")
                self.progress_label.setVisible(False)
                return

            # Load into agent for Q&A
            self._agent.load_document(text, title=path.name)

            self.doc_label.setText(f"Loaded: {path.name}")
            self.doc_label.setStyleSheet(f"""
                QLabel {{
                    color: #000;
                    font-weight: bold;
                    font-size: {self.scale['font_small']}pt;
                }}
            """)
            self._document_loaded = True
            self.send_btn.setEnabled(True)
            self.clear_btn.setEnabled(True)
            self.progress_label.setVisible(False)

            # Add confirmation to chat
            self._add_chat_bubble(
                f"Document loaded: **{path.name}**\n\n"
                f"You can now ask questions about this document.",
                is_user=False
            )

            self.status_message.emit(f"Loaded document: {path.name}")
            logger.info(f"Loaded document: {path}")

        except Exception as e:
            logger.exception("Failed to load document")
            self.doc_label.setText(f"Error: {str(e)}")
            self.progress_label.setVisible(False)
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to load document:\n{str(e)}"
            )

    def _clear_document(self) -> None:
        """Clear the loaded document."""
        self._agent.clear_document()
        self.document_view.clear()
        self.doc_label.setText("No document loaded")
        self.doc_label.setStyleSheet(f"""
            QLabel {{
                color: #666;
                font-style: italic;
                font-size: {self.scale['font_small']}pt;
            }}
        """)
        self._document_loaded = False
        self._current_doc_metadata = None  # Clear metadata
        self._current_pdf_path = None  # Clear PDF path
        self.send_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        self.wrong_pdf_btn.setEnabled(False)
        self.wrong_pdf_btn.setVisible(False)
        self._clear_chat()

    def _clear_chat(self) -> None:
        """Clear chat history and re-add welcome message."""
        self.conversation_history.clear()

        # Clear chat layout
        while self.chat_layout.count():
            child = self.chat_layout.takeAt(0)
            widget = child.widget()
            if widget:
                widget.deleteLater()

        # Re-add welcome message
        self._add_welcome_message()

    def _ask_question(self) -> None:
        """Ask a question about the document."""
        question = self.message_input.toPlainText().strip()
        if not question or not self._document_loaded:
            return

        # Add user message to chat
        self._add_chat_bubble(question, is_user=True)
        self.message_input.clear()

        # Disable input while processing
        self.send_btn.setEnabled(False)
        self.message_input.setEnabled(False)
        self.progress_label.setText("Thinking...")
        self.progress_label.setVisible(True)

        # Create worker
        self._worker = AnswerWorker(self._agent, question)
        self._worker.finished.connect(self._on_answer)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_answer(self, answer: str, sources: list) -> None:
        """Handle answer from worker."""
        self._add_chat_bubble(answer, is_user=False)
        self.progress_label.setVisible(False)
        self._reset_input()

    def _on_error(self, message: str) -> None:
        """Handle error from worker."""
        self._add_chat_bubble(f"**Error:** {message}", is_user=False)
        self.progress_label.setText("Error occurred")
        self._reset_input()

    def _reset_input(self) -> None:
        """Reset input controls."""
        self.send_btn.setEnabled(True)
        self.message_input.setEnabled(True)
        self._worker = None

    def _on_save_conversation(self) -> None:
        """Handle save conversation button click."""
        if not self.conversation_history:
            QMessageBox.information(
                self,
                "No Conversation",
                "No conversation to save yet. Ask some questions first!"
            )
            return

        # Show menu with format options
        menu = QMenu(self)
        json_action = menu.addAction("Save as JSON")
        md_action = menu.addAction("Save as Markdown")

        action = menu.exec_(
            self.save_btn.mapToGlobal(self.save_btn.rect().bottomLeft())
        )

        if action == json_action:
            self._save_conversation_json()
        elif action == md_action:
            self._save_conversation_markdown()

    def _save_conversation_json(self) -> None:
        """Save conversation as JSON."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Conversation as JSON",
            str(Path.home() / "conversation.json"),
            "JSON Files (*.json)"
        )

        if not file_path:
            return

        try:
            import json

            export_data = {
                "metadata": {
                    "exported_at": datetime.now().isoformat(),
                    "document": self.document_view.get_title(),
                    "message_count": len(self.conversation_history)
                },
                "messages": self.conversation_history
            }

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)

            self.status_message.emit(f"Saved conversation to: {Path(file_path).name}")

        except Exception as e:
            QMessageBox.critical(
                self,
                "Save Error",
                f"Failed to save conversation:\n{str(e)}"
            )

    def _save_conversation_markdown(self) -> None:
        """Save conversation as Markdown."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Conversation as Markdown",
            str(Path.home() / "conversation.md"),
            "Markdown Files (*.md)"
        )

        if not file_path:
            return

        try:
            lines = [
                "# Document Q&A Conversation",
                "",
                "## Metadata",
                "",
                f"- **Exported:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                f"- **Document:** {self.document_view.get_title()}",
                f"- **Messages:** {len(self.conversation_history)}",
                "",
                "## Conversation",
                "",
            ]

            for msg in self.conversation_history:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")

                if role == "user":
                    lines.append("### You")
                else:
                    lines.append("### AI")

                lines.append("")
                lines.append(content)
                lines.append("")
                lines.append("---")
                lines.append("")

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))

            self.status_message.emit(f"Saved conversation to: {Path(file_path).name}")

        except Exception as e:
            QMessageBox.critical(
                self,
                "Save Error",
                f"Failed to save conversation:\n{str(e)}"
            )

    # -------------------------------------------------------------------------
    # PDF Discovery and Archiving Helpers
    # -------------------------------------------------------------------------

    def _get_pdf_base_dir(self) -> Path:
        """
        Get the base directory for PDF storage.

        Uses PDF_BASE_DIR environment variable or defaults to ~/knowledgebase/pdf.

        Returns:
            Path to PDF base directory
        """
        pdf_base = os.environ.get('PDF_BASE_DIR')
        if pdf_base:
            return Path(pdf_base).expanduser()
        return Path.home() / 'knowledgebase' / 'pdf'

    def _generate_pdf_path(self, doc_dict: Dict[str, Any]) -> Path:
        """
        Generate the standard PDF path for a document.

        Uses year-based folder structure with DOI-based or ID-based filename.

        Args:
            doc_dict: Document dictionary with doi, year, id, etc.

        Returns:
            Path where PDF should be stored
        """
        base_dir = self._get_pdf_base_dir()

        # Extract year for subdirectory
        year = doc_dict.get('year')
        if not year:
            pub_date = doc_dict.get('publication_date')
            if pub_date:
                if isinstance(pub_date, str) and len(pub_date) >= 4:
                    try:
                        year = int(pub_date[:4])
                    except ValueError:
                        year = None

        year_dir = str(year) if year else 'unknown'
        output_dir = base_dir / year_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename from DOI or document ID
        doi = doc_dict.get('doi')
        if doi:
            # DOI-based filename (replace slashes)
            safe_doi = doi.replace('/', '_').replace('\\', '_')
            filename = f"{safe_doi}.pdf"
        else:
            # Document ID-based filename
            doc_id = doc_dict.get('id', 'unknown')
            filename = f"doc_{doc_id}.pdf"

        return output_dir / filename

    def _find_existing_pdf(self, doc_dict: Dict[str, Any]) -> Optional[Path]:
        """
        Check if a PDF already exists locally for this document.

        Searches both the expected path and year-based subdirectories.

        Args:
            doc_dict: Document dictionary with doi, year, id, etc.

        Returns:
            Path to existing PDF if found, None otherwise
        """
        # First check expected path
        expected_path = self._generate_pdf_path(doc_dict)
        if expected_path.exists():
            logger.info(f"Found existing PDF at: {expected_path}")
            return expected_path

        # Also check by DOI in all year directories
        doi = doc_dict.get('doi')
        if doi:
            base_dir = self._get_pdf_base_dir()
            safe_doi = doi.replace('/', '_').replace('\\', '_')
            filename = f"{safe_doi}.pdf"

            # Search all year directories
            if base_dir.exists():
                for year_dir in base_dir.iterdir():
                    if year_dir.is_dir():
                        pdf_path = year_dir / filename
                        if pdf_path.exists():
                            logger.info(f"Found existing PDF at: {pdf_path}")
                            return pdf_path

        return None

    def _create_progress_dialog(self, title: str) -> QProgressDialog:
        """
        Create a progress dialog for PDF operations.

        Args:
            title: Dialog title

        Returns:
            Configured QProgressDialog
        """
        dialog = QProgressDialog(self)
        dialog.setWindowTitle(title)
        dialog.setLabelText("Initializing...")
        dialog.setMinimum(0)
        dialog.setMaximum(0)  # Indeterminate progress
        dialog.setMinimumWidth(scaled(350))
        dialog.setAutoClose(True)
        dialog.setAutoReset(True)
        dialog.setCancelButtonText("Cancel")
        return dialog

    def _update_progress_dialog(self, stage: str, status: str) -> None:
        """
        Update the progress dialog with current stage information.

        Args:
            stage: Current stage (discovery, download, browser_download, etc.)
            status: Current status (starting, found, success, failed, etc.)
        """
        if not self._pdf_progress_dialog:
            return

        # Map stages and statuses to user-friendly messages
        stage_messages = {
            'discovery': {
                'starting': "Searching for PDF sources...",
                'resolving': "Checking PDF sources...",
                'found': "Found PDF source!",
                'found_oa': "Found open access PDF!",
                'not_found': "No PDF sources found",
                'error': "Error searching for PDF",
            },
            'download': {
                'starting': "Downloading PDF...",
                'success': "Download complete!",
                'failed': "Download failed",
            },
            'browser_download': {
                'starting': "Downloading PDF (browser mode)...",
                'success': "Download complete!",
                'failed': "Browser download failed",
            },
            'verification': {
                'starting': "Verifying PDF content...",
                'success': "Verification complete",
                'mismatch': "Content verification failed",
                'skipped': "Verification skipped",
                'error': "Verification error",
            },
        }

        # Get appropriate message
        message = stage_messages.get(stage, {}).get(
            status, f"{stage.replace('_', ' ').title()}: {status}"
        )
        self._pdf_progress_dialog.setLabelText(message)

    def _cancel_pdf_discovery(self) -> None:
        """Cancel any running PDF discovery operation."""
        if self._pdf_worker:
            self._pdf_worker.cancel()
            self._pdf_worker = None
        if self._pdf_progress_dialog:
            self._pdf_progress_dialog.close()
            self._pdf_progress_dialog = None

    def load_from_citation(self, citation: 'Citation') -> None:
        """
        Load a document from a citation object.

        Uses a non-blocking approach:
        1. Check for existing local PDF first
        2. If not found, start background PDF discovery
        3. Fall back to abstract while waiting / if PDF unavailable

        Args:
            citation: Citation object containing document metadata
        """
        from ..data_models import Citation

        doc = citation.document
        title = doc.title or "Untitled Document"

        # Clear any previous document
        self._clear_document()

        # Store document metadata for PDF discovery button and background download
        self._current_doc_metadata = {
            'id': doc.id,
            'doi': doc.doi,
            'pmid': doc.pmid,
            'pmcid': doc.pmc_id,  # Use correct field name for discovery
            'pmc_id': doc.pmc_id,  # Keep original for backwards compat
            'title': doc.title,
            'year': doc.year,
        }

        # Store citation for use in completion handlers
        self._pending_citation = citation

        # First, check if PDF already exists locally
        existing_pdf = self._find_existing_pdf(self._current_doc_metadata)
        if existing_pdf:
            # Load existing PDF directly
            self._load_pdf_and_complete(existing_pdf, citation, "Full Text (PDF - cached)")
            return

        # Check if we have identifiers for discovery
        if not doc.doi and not doc.pmid and not doc.pmc_id:
            # No identifiers - just load abstract
            self._load_abstract_and_complete(citation)
            return

        # Start background PDF discovery with progress dialog
        self._start_pdf_discovery(citation)

    def _start_pdf_discovery(self, citation: 'Citation') -> None:
        """
        Start PDF discovery in background thread with progress dialog.

        Args:
            citation: Citation object for document to fetch
        """
        # Create progress dialog
        self._pdf_progress_dialog = self._create_progress_dialog("Fetching PDF")
        self._pdf_progress_dialog.canceled.connect(self._on_pdf_discovery_cancelled)
        self._pdf_progress_dialog.show()

        # Get configuration
        unpaywall_email = getattr(self.config, 'unpaywall_email', None)
        output_dir = self._get_pdf_base_dir()

        # Create worker
        self._pdf_worker = PDFDiscoveryWorker(
            doc_dict=self._current_doc_metadata,
            output_dir=output_dir,
            unpaywall_email=unpaywall_email,
            parent=self,
        )
        self._pdf_worker.progress.connect(self._update_progress_dialog)
        self._pdf_worker.finished.connect(self._on_pdf_discovery_finished)
        self._pdf_worker.verification_warning.connect(self._on_pdf_verification_warning)
        self._pdf_worker.error.connect(self._on_pdf_discovery_error)
        self._pdf_worker.start()

    def _on_pdf_discovery_finished(self, file_path: str) -> None:
        """
        Handle successful PDF discovery completion.

        Args:
            file_path: Path to downloaded PDF file
        """
        # Close progress dialog
        if self._pdf_progress_dialog:
            self._pdf_progress_dialog.close()
            self._pdf_progress_dialog = None

        self._pdf_worker = None

        # Load the PDF
        pdf_path = Path(file_path)
        if pdf_path.exists():
            self._load_pdf_and_complete(
                pdf_path,
                self._pending_citation,
                "Full Text (PDF)"
            )
        else:
            logger.error(f"Downloaded PDF not found at: {file_path}")
            self._load_abstract_and_complete(self._pending_citation)

    def _on_pdf_discovery_error(self, error_message: str) -> None:
        """
        Handle PDF discovery error.

        Falls back to loading abstract.

        Args:
            error_message: Error description
        """
        # Close progress dialog
        if self._pdf_progress_dialog:
            self._pdf_progress_dialog.close()
            self._pdf_progress_dialog = None

        self._pdf_worker = None

        logger.info(f"PDF discovery failed, using abstract: {error_message}")
        self._load_abstract_and_complete(self._pending_citation)

    def _on_pdf_discovery_cancelled(self) -> None:
        """Handle user cancelling PDF discovery."""
        self._cancel_pdf_discovery()
        logger.info("PDF discovery cancelled by user")
        self._load_abstract_and_complete(self._pending_citation)

    def _on_pdf_verification_warning(self, file_path: str, warning_message: str) -> None:
        """
        Handle PDF verification warning - wrong document may have been downloaded.

        Shows a warning dialog to the user and falls back to abstract.
        The mismatched PDF is kept for inspection but not loaded.

        Args:
            file_path: Path to the mismatched PDF file
            warning_message: Description of the mismatch
        """
        # Close progress dialog
        if self._pdf_progress_dialog:
            self._pdf_progress_dialog.close()
            self._pdf_progress_dialog = None

        self._pdf_worker = None

        # Log the issue
        logger.warning(f"PDF verification failed for {file_path}: {warning_message}")

        # Show warning to user
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.warning(
            self,
            "PDF Verification Failed",
            f"The downloaded PDF does not match the expected document.\n\n"
            f"{warning_message}\n\n"
            f"The file has been saved to:\n{file_path}\n\n"
            f"Falling back to abstract view.",
            QMessageBox.StandardButton.Ok
        )

        # Fall back to abstract
        self._load_abstract_and_complete(self._pending_citation)

    def _load_pdf_and_complete(
        self,
        pdf_path: Path,
        citation: 'Citation',
        source_type: str,
    ) -> None:
        """
        Load a PDF file and complete the document loading process.

        Args:
            pdf_path: Path to PDF file
            citation: Citation object
            source_type: Description of source for display
        """
        doc = citation.document
        title = doc.title or "Untitled Document"

        try:
            # Extract text from PDF
            import fitz
            pdf_doc = fitz.open(str(pdf_path))
            text_parts = []
            for page in pdf_doc:
                text_parts.append(page.get_text())
            pdf_doc.close()

            text = "\n\n".join(text_parts)

            if not text.strip():
                logger.warning("PDF contained no text, falling back to abstract")
                self._load_abstract_and_complete(citation)
                return

            # Store PDF path
            self._current_pdf_path = pdf_path

            # Load into agent for Q&A
            self._agent.load_document(text, title=title)

            # Display in the full text tab
            self.document_view.fulltext_tab.set_content(text)
            self.document_view._current_text = text
            self.document_view._current_title = title

            # Load PDF into viewer
            if self.document_view.pdf_tab.load_pdf(str(pdf_path)):
                # Switch to PDF tab
                self.document_view.tab_widget.setCurrentIndex(0)
            else:
                # PDF load failed, show full text tab
                self.document_view.tab_widget.setCurrentIndex(1)

            self._finalize_document_load(title, source_type, citation)

        except Exception as e:
            logger.exception("Failed to load PDF")
            self._load_abstract_and_complete(citation)

    def _load_abstract_and_complete(self, citation: 'Citation') -> None:
        """
        Load document abstract and complete the loading process.

        Args:
            citation: Citation object
        """
        doc = citation.document
        title = doc.title or "Untitled Document"
        source_type = "Abstract"

        text = self._format_abstract_as_document(doc, citation)

        if not text.strip():
            self.doc_label.setText("Error: No content available")
            QMessageBox.warning(
                self,
                "No Content",
                f"No text content available for:\n{title}"
            )
            return

        try:
            # Load into agent for Q&A
            self._agent.load_document(text, title=title)

            # Display in the full text tab
            self.document_view.fulltext_tab.set_content(text)
            self.document_view._current_text = text
            self.document_view._current_title = title

            # Switch to full text tab (no PDF)
            self.document_view.tab_widget.setCurrentIndex(1)

            self._finalize_document_load(title, source_type, citation)

        except Exception as e:
            logger.exception("Failed to load abstract")
            self.doc_label.setText(f"Error: {str(e)}")
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to load document:\n{str(e)}"
            )

    def _finalize_document_load(
        self,
        title: str,
        source_type: str,
        citation: 'Citation',
    ) -> None:
        """
        Finalize document loading - update UI state and add chat message.

        Args:
            title: Document title
            source_type: Source description
            citation: Citation object
        """
        self.doc_label.setText(f"Loaded: {title[:50]}... ({source_type})")
        self.doc_label.setStyleSheet(f"""
            QLabel {{
                color: #000;
                font-weight: bold;
                font-size: {self.scale['font_small']}pt;
            }}
        """)
        self._document_loaded = True
        self.send_btn.setEnabled(True)
        self.clear_btn.setEnabled(True)
        self.progress_label.setVisible(False)

        # Show Wrong PDF button only when a PDF is loaded (not abstract)
        if self._current_pdf_path is not None:
            self.wrong_pdf_btn.setEnabled(True)
            self.wrong_pdf_btn.setVisible(True)
        else:
            self.wrong_pdf_btn.setEnabled(False)
            self.wrong_pdf_btn.setVisible(False)

        # Add confirmation to chat with citation context
        self._add_chat_bubble(
            f"Document loaded: **{title}**\n\n"
            f"Source: {source_type}\n\n"
            f"**Relevant passage from this document:**\n"
            f"> {citation.passage[:500]}{'...' if len(citation.passage) > 500 else ''}\n\n"
            f"You can now ask questions about this document.",
            is_user=False
        )

        self.status_message.emit(f"Loaded: {title}")
        logger.info(f"Loaded document: {title[:50]}... ({source_type})")

    def _try_pdf_discovery(self, doc: 'LiteDocument') -> tuple[Optional[str], Optional[Path]]:
        """
        Try to discover and download PDF for the document.

        Uses the BMLibrarian PDF discovery system to find and download
        the full text from PMC, Unpaywall, or DOI.

        Args:
            doc: LiteDocument with identifiers (DOI, PMID, PMC ID)

        Returns:
            Tuple of (extracted_text, pdf_path) - both None if unavailable
        """
        from ..data_models import LiteDocument

        try:
            from bmlibrarian.discovery import (
                FullTextFinder,
                DocumentIdentifiers,
            )
            import tempfile

            # Build identifiers from document metadata
            identifiers = DocumentIdentifiers(
                doi=doc.doi,
                pmid=doc.pmid,
                pmcid=doc.pmc_id,  # Note: DocumentIdentifiers uses pmcid
            )

            # Skip if no identifiers
            if not identifiers.doi and not identifiers.pmid and not identifiers.pmcid:
                logger.debug("No identifiers available for PDF discovery")
                return None, None

            self.progress_label.setText("Searching for full text PDF...")

            # Create finder with Unpaywall email from config if available
            unpaywall_email = getattr(self.config, 'unpaywall_email', None)
            finder = FullTextFinder(unpaywall_email=unpaywall_email)

            # Try to discover sources
            discovery_result = finder.discover(identifiers)

            if not discovery_result.best_source:
                logger.info(f"No PDF source found for {doc.id}")
                return None, None

            self.progress_label.setText("Downloading PDF...")

            # Download to temp file
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
                tmp_path = Path(tmp.name)

            download_result = finder.discover_and_download(
                identifiers,
                output_path=tmp_path,
                use_browser_fallback=True,
            )

            if not download_result.success:
                logger.info(f"PDF download failed: {download_result.error}")
                tmp_path.unlink(missing_ok=True)
                return None, None

            # Extract text from PDF
            self.progress_label.setText("Extracting text from PDF...")

            import fitz
            pdf_doc = fitz.open(str(tmp_path))
            text_parts = []
            for page in pdf_doc:
                text_parts.append(page.get_text())
            pdf_doc.close()

            text = "\n\n".join(text_parts)

            if text.strip():
                logger.info(f"Successfully extracted {len(text)} chars from PDF")
                # Return text AND path - don't delete the temp file yet
                return text, tmp_path
            else:
                logger.warning("PDF extracted but contained no text")
                tmp_path.unlink(missing_ok=True)
                return None, None

        except ImportError as e:
            logger.debug(f"PDF discovery not available: {e}")
            return None, None
        except Exception as e:
            logger.warning(f"PDF discovery failed: {e}")
            return None, None

    def _format_abstract_as_document(
        self, doc: 'LiteDocument', citation: 'Citation'
    ) -> str:
        """
        Format abstract and citation as a readable document.

        Creates a structured document from the abstract and metadata
        when full text is not available.

        Args:
            doc: LiteDocument with metadata
            citation: Citation with extracted passage

        Returns:
            Formatted document text
        """
        from ..data_models import LiteDocument, Citation

        parts = []

        # Title
        parts.append(f"# {doc.title}")
        parts.append("")

        # Authors and publication info
        if doc.authors:
            parts.append(f"**Authors:** {doc.formatted_authors}")
        if doc.journal:
            parts.append(f"**Journal:** {doc.journal}")
        if doc.year:
            parts.append(f"**Year:** {doc.year}")
        if doc.doi:
            parts.append(f"**DOI:** {doc.doi}")
        if doc.pmid:
            parts.append(f"**PMID:** {doc.pmid}")

        parts.append("")

        # Abstract
        parts.append("## Abstract")
        parts.append("")
        parts.append(doc.abstract or "No abstract available.")
        parts.append("")

        # Relevant passage from citation
        if citation.passage:
            parts.append("## Relevant Passage")
            parts.append("")
            parts.append(f"> {citation.passage}")
            parts.append("")

        # Context if available
        if citation.context:
            parts.append("## Context")
            parts.append("")
            parts.append(citation.context)
            parts.append("")

        # Note about limited content
        parts.append("---")
        parts.append("")
        parts.append(
            "*Note: Full text was not available. This document contains only "
            "the abstract and citation information.*"
        )

        return "\n".join(parts)

    def _fetch_pdf_from_identifier(self) -> None:
        """
        Fetch PDF using DOI/PMID from stored document metadata.

        If no metadata is available, prompts user to enter identifiers.
        Uses the existing PDF discovery system.
        """
        # Check if we have identifiers from current document context
        doi = None
        pmid = None
        pmcid = None
        title = None

        if hasattr(self, '_current_doc_metadata') and self._current_doc_metadata:
            doi = self._current_doc_metadata.get('doi')
            pmid = self._current_doc_metadata.get('pmid')
            pmcid = self._current_doc_metadata.get('pmc_id')
            title = self._current_doc_metadata.get('title')

        # If no identifiers, ask user
        if not doi and not pmid and not pmcid:
            from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLineEdit

            dialog = QDialog(self)
            dialog.setWindowTitle("Fetch PDF - Enter Identifier")
            dialog.setMinimumWidth(scaled(400))

            form_layout = QFormLayout(dialog)

            doi_input = QLineEdit()
            doi_input.setPlaceholderText("e.g., 10.1038/nature12373")
            form_layout.addRow("DOI:", doi_input)

            pmid_input = QLineEdit()
            pmid_input.setPlaceholderText("e.g., 12345678")
            form_layout.addRow("PMID:", pmid_input)

            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
            )
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            form_layout.addRow(buttons)

            if dialog.exec() != QDialog.DialogCode.Accepted:
                return

            doi = doi_input.text().strip() or None
            pmid = pmid_input.text().strip() or None

            if not doi and not pmid:
                QMessageBox.warning(
                    self,
                    "No Identifier",
                    "Please enter a DOI or PMID."
                )
                return

        # Perform PDF discovery
        self._do_pdf_discovery(doi=doi, pmid=pmid, pmcid=pmcid, title=title)

    def _do_pdf_discovery(
        self,
        doi: Optional[str] = None,
        pmid: Optional[str] = None,
        pmcid: Optional[str] = None,
        title: Optional[str] = None,
    ) -> None:
        """
        Execute PDF discovery in background thread with progress dialog.

        Uses non-blocking background thread for PDF discovery and download.

        Args:
            doi: Digital Object Identifier
            pmid: PubMed ID
            pmcid: PubMed Central ID
            title: Document title for display
        """
        # Create document metadata dict for the worker
        doc_dict = {
            'doi': doi,
            'pmid': pmid,
            'pmcid': pmcid,
            'title': title,
        }

        # Store metadata for completion handlers
        self._current_doc_metadata = doc_dict
        self._pending_fetch_title = title or f"PDF ({doi or pmid or pmcid})"

        # First check for existing PDF
        existing_pdf = self._find_existing_pdf(doc_dict)
        if existing_pdf:
            self._load_fetched_pdf(str(existing_pdf))
            return

        # Create progress dialog
        self._pdf_progress_dialog = self._create_progress_dialog("Fetching PDF")
        self._pdf_progress_dialog.canceled.connect(self._on_fetch_cancelled)
        self._pdf_progress_dialog.show()

        # Get configuration
        unpaywall_email = getattr(self.config, 'unpaywall_email', None)
        output_dir = self._get_pdf_base_dir()

        # Create worker
        self._pdf_worker = PDFDiscoveryWorker(
            doc_dict=doc_dict,
            output_dir=output_dir,
            unpaywall_email=unpaywall_email,
            parent=self,
        )
        self._pdf_worker.progress.connect(self._update_progress_dialog)
        self._pdf_worker.finished.connect(self._on_fetch_finished)
        self._pdf_worker.verification_warning.connect(self._on_fetch_verification_warning)
        self._pdf_worker.error.connect(self._on_fetch_error)
        self._pdf_worker.start()

    def _on_fetch_finished(self, file_path: str) -> None:
        """
        Handle successful PDF fetch completion.

        Args:
            file_path: Path to downloaded PDF file
        """
        # Close progress dialog
        if self._pdf_progress_dialog:
            self._pdf_progress_dialog.close()
            self._pdf_progress_dialog = None

        self._pdf_worker = None
        self._load_fetched_pdf(file_path)

    def _on_fetch_error(self, error_message: str) -> None:
        """
        Handle PDF fetch error.

        Args:
            error_message: Error description
        """
        # Close progress dialog
        if self._pdf_progress_dialog:
            self._pdf_progress_dialog.close()
            self._pdf_progress_dialog = None

        self._pdf_worker = None

        QMessageBox.warning(
            self,
            "PDF Fetch Failed",
            f"Could not download PDF:\n{error_message}\n\n"
            "You can try again or use the document with abstract only."
        )

    def _on_fetch_cancelled(self) -> None:
        """Handle user cancelling PDF fetch."""
        self._cancel_pdf_discovery()
        logger.info("PDF fetch cancelled by user")

    def _on_fetch_verification_warning(self, file_path: str, warning_message: str) -> None:
        """
        Handle PDF verification warning during fetch - wrong document may have been downloaded.

        Shows a warning dialog to the user. The mismatched PDF is kept for inspection.

        Args:
            file_path: Path to the mismatched PDF file
            warning_message: Description of the mismatch
        """
        # Close progress dialog
        if self._pdf_progress_dialog:
            self._pdf_progress_dialog.close()
            self._pdf_progress_dialog = None

        self._pdf_worker = None

        # Log the issue
        logger.warning(f"PDF verification failed for fetch {file_path}: {warning_message}")

        # Show warning to user
        QMessageBox.warning(
            self,
            "PDF Verification Failed",
            f"The downloaded PDF does not match the expected document.\n\n"
            f"{warning_message}\n\n"
            f"The file has been saved to:\n{file_path}\n\n"
            "Please verify the PDF manually before use.",
            QMessageBox.StandardButton.Ok
        )

    def _load_fetched_pdf(self, file_path: str) -> None:
        """
        Load a fetched PDF into the viewer.

        Args:
            file_path: Path to PDF file
        """
        pdf_path = Path(file_path)
        if not pdf_path.exists():
            QMessageBox.warning(
                self,
                "File Not Found",
                f"PDF file not found at:\n{file_path}"
            )
            return

        try:
            # Extract text from PDF
            import fitz
            pdf_doc = fitz.open(str(pdf_path))
            text_parts = []
            for page in pdf_doc:
                text_parts.append(page.get_text())
            pdf_doc.close()

            text = "\n\n".join(text_parts)

            if not text.strip():
                QMessageBox.warning(
                    self,
                    "Empty PDF",
                    "PDF contained no extractable text."
                )
                return

            # Get display title
            display_title = getattr(self, '_pending_fetch_title', None)
            if not display_title:
                display_title = pdf_path.stem

            # Store PDF path
            self._current_pdf_path = pdf_path

            # Load into viewer
            self.document_view.fulltext_tab.set_content(text)
            self.document_view._current_text = text
            self.document_view._current_title = display_title

            if self.document_view.pdf_tab.load_pdf(str(pdf_path)):
                self.document_view.tab_widget.setCurrentIndex(0)
            else:
                self.document_view.tab_widget.setCurrentIndex(1)

            # Load into agent for Q&A
            self._agent.load_document(text, title=display_title)

            # Update UI state
            self.doc_label.setText(f"Loaded: {display_title[:50]}...")
            self.doc_label.setStyleSheet(f"""
                QLabel {{
                    color: #000;
                    font-weight: bold;
                    font-size: {self.scale['font_small']}pt;
                }}
            """)
            self._document_loaded = True
            self.send_btn.setEnabled(True)
            self.clear_btn.setEnabled(True)

            # Show Wrong PDF button since this is a PDF
            self.wrong_pdf_btn.setEnabled(True)
            self.wrong_pdf_btn.setVisible(True)

            self._add_chat_bubble(
                f"Document loaded: **{display_title}**\n\n"
                f"Source: PDF Discovery\n\n"
                f"You can now ask questions about this document.",
                is_user=False
            )

            self.status_message.emit(f"Loaded: {display_title}")
            logger.info(f"Loaded PDF from: {pdf_path}")

        except Exception as e:
            logger.exception("Failed to load fetched PDF")
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to load PDF:\n{str(e)}"
            )

    def _handle_wrong_pdf(self) -> None:
        """
        Handle the 'Wrong PDF' button click.

        Shows a dialog allowing the user to:
        - Delete the incorrect PDF file
        - Clear the current view and extracted text
        - Optionally try to fetch the correct PDF again
        """
        if not self._current_pdf_path:
            QMessageBox.warning(
                self,
                "No PDF Loaded",
                "No PDF file is currently loaded."
            )
            return

        pdf_path = self._current_pdf_path

        # Create custom dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Wrong PDF - Actions")
        dialog.setMinimumWidth(450)

        layout = QVBoxLayout(dialog)
        s = self.scale

        # Info section
        info_label = QLabel(
            f"<b>Current PDF:</b><br>"
            f"<code>{pdf_path}</code><br><br>"
            f"This PDF appears to be incorrect. Choose an action below:"
        )
        info_label.setWordWrap(True)
        info_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(info_label)

        layout.addSpacing(s['spacing_medium'])

        # Action buttons
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(s['spacing_small'])

        # Delete and clear button
        delete_btn = QPushButton("Delete PDF and Clear View")
        delete_btn.setToolTip(
            "Delete the PDF file from disk and clear the document view"
        )
        delete_btn.setStyleSheet(f"""
            QPushButton {{
                padding: {s['padding_small']}px;
                background-color: #FFCCCB;
            }}
            QPushButton:hover {{
                background-color: #FF9999;
            }}
        """)
        btn_layout.addWidget(delete_btn)

        # Delete and retry button
        retry_btn = QPushButton("Delete PDF and Try Again")
        retry_btn.setToolTip(
            "Delete the PDF file and attempt to fetch the correct one"
        )
        retry_btn.setStyleSheet(f"""
            QPushButton {{
                padding: {s['padding_small']}px;
                background-color: #FFE4B5;
            }}
            QPushButton:hover {{
                background-color: #FFD700;
            }}
        """)
        btn_layout.addWidget(retry_btn)

        # Keep file but clear view
        clear_only_btn = QPushButton("Clear View Only (Keep File)")
        clear_only_btn.setToolTip(
            "Clear the document view but keep the PDF file for manual inspection"
        )
        clear_only_btn.setStyleSheet(f"""
            QPushButton {{
                padding: {s['padding_small']}px;
            }}
        """)
        btn_layout.addWidget(clear_only_btn)

        # Cancel button
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                padding: {s['padding_small']}px;
            }}
        """)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

        # Store result - use list to allow mutation in nested function
        result: list[Optional[str]] = [None]

        def on_delete() -> None:
            result[0] = 'delete'
            dialog.accept()

        def on_retry() -> None:
            result[0] = 'retry'
            dialog.accept()

        def on_clear_only() -> None:
            result[0] = 'clear_only'
            dialog.accept()

        delete_btn.clicked.connect(on_delete)
        retry_btn.clicked.connect(on_retry)
        clear_only_btn.clicked.connect(on_clear_only)
        cancel_btn.clicked.connect(dialog.reject)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        action = result[0]
        doc_metadata = self._current_doc_metadata

        if action == 'delete':
            self._delete_wrong_pdf(pdf_path)
            self._clear_document()
            self._add_chat_bubble(
                "The incorrect PDF has been deleted and the view cleared.",
                is_user=False
            )

        elif action == 'retry':
            self._delete_wrong_pdf(pdf_path)
            self._clear_document()

            # Try to fetch again if we have metadata
            if doc_metadata:
                self._add_chat_bubble(
                    "The incorrect PDF has been deleted. Attempting to fetch the correct PDF...",
                    is_user=False
                )
                # Use the fetch workflow
                self._do_pdf_discovery(
                    doi=doc_metadata.get('doi'),
                    pmid=doc_metadata.get('pmid'),
                    pmcid=doc_metadata.get('pmcid'),
                    title=doc_metadata.get('title')
                )
            else:
                self._add_chat_bubble(
                    "The incorrect PDF has been deleted. "
                    "No document metadata available for retry - use the Fetch PDF button manually.",
                    is_user=False
                )

        elif action == 'clear_only':
            self._clear_document()
            self._add_chat_bubble(
                f"View cleared. The PDF file has been kept at:\n`{pdf_path}`",
                is_user=False
            )

    def _delete_wrong_pdf(self, pdf_path: Path) -> bool:
        """
        Delete an incorrect PDF file and clean up related data.

        Args:
            pdf_path: Path to the PDF file to delete

        Returns:
            True if deletion was successful, False otherwise
        """
        try:
            if pdf_path.exists():
                pdf_path.unlink()
                logger.info(f"Deleted wrong PDF: {pdf_path}")

                # Also try to clean up related files
                # (e.g., extracted text, chunks in ChromaDB, etc.)
                self._cleanup_pdf_artifacts(pdf_path)

                return True
            else:
                logger.warning(f"PDF file not found for deletion: {pdf_path}")
                return False

        except Exception as e:
            logger.exception(f"Failed to delete PDF: {pdf_path}")
            QMessageBox.warning(
                self,
                "Deletion Failed",
                f"Could not delete PDF file:\n{str(e)}"
            )
            return False

    def _cleanup_pdf_artifacts(self, pdf_path: Path) -> None:
        """
        Clean up artifacts related to a PDF file.

        This includes:
        - Extracted text chunks from ChromaDB
        - Any cached metadata

        Args:
            pdf_path: Path to the PDF that was deleted
        """
        try:
            # If we have a storage instance, try to clean up chunks
            if hasattr(self, 'storage') and self.storage:
                # Get document ID if available
                doc_id = None
                if self._current_doc_metadata:
                    doc_id = self._current_doc_metadata.get('id')

                if doc_id:
                    # Try to delete chunks associated with this document
                    try:
                        # Get the chunks collection and delete by source_id
                        chunks_collection = self.storage.get_chunks_collection()
                        chunks_collection.delete(
                            where={"source_id": str(doc_id)}
                        )
                        logger.info(f"Deleted chunks for document ID: {doc_id}")
                    except Exception as e:
                        logger.warning(f"Could not delete chunks for {doc_id}: {e}")

            logger.info(f"Cleaned up artifacts for: {pdf_path}")

        except Exception as e:
            logger.warning(f"Error cleaning up PDF artifacts: {e}")
