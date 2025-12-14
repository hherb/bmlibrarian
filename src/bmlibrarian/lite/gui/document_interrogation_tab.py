"""
Document Interrogation tab for BMLibrarian Lite.

Provides an interactive Q&A interface for loaded documents using
RAG (Retrieval Augmented Generation) pattern.

Features:
- Split-pane layout: document viewer (60%) / chat interface (40%)
- Tabbed document viewer: PDF / Full Text tabs
- Styled chat bubbles with markdown rendering
- Conversation history with export
- PDF discovery and download with verification
"""

import logging
from pathlib import Path
from typing import List, Optional

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QPushButton,
    QLabel,
    QFileDialog,
    QScrollArea,
    QSplitter,
    QSizePolicy,
    QMenu,
    QMessageBox,
    QProgressDialog,
)
from PySide6.QtCore import Qt, Signal, QTimer

from bmlibrarian.gui.qt.resources.styles.dpi_scale import scaled, get_font_scale

from ..config import LiteConfig
from ..storage import LiteStorage
from ..agents import LiteInterrogationAgent
from ..pdf_utils import (
    get_pdf_base_dir,
    find_existing_pdf,
    extract_pdf_text,
    get_progress_stage_message,
)
from ..conversation_export import (
    export_conversation_to_json,
    export_conversation_to_markdown,
    create_conversation_message,
)
from .workers import AnswerWorker, PDFDiscoveryWorker
from .chat_widgets import ChatBubble
from .document_viewer import LiteDocumentViewWidget
from .dialogs import WrongPDFDialog, IdentifierInputDialog
from .citation_loader import (
    build_doc_metadata,
    build_abstract_text,
    has_pdf_identifiers,
    get_document_title,
)

logger = logging.getLogger(__name__)

# Constants for layout proportions
DOCUMENT_PANE_WIDTH = 600  # Initial width proportion for document viewer
CHAT_PANE_WIDTH = 400  # Initial width proportion for chat interface
PROGRESS_DIALOG_MIN_WIDTH = 350  # Minimum width for progress dialog


class DocumentInterrogationTab(QWidget):
    """
    Document Interrogation tab widget with split-pane layout.

    Provides interface for:
    - Loading documents (PDF/text) with tabbed viewer
    - Asking questions about the document with styled chat bubbles
    - Viewing conversation history
    - Exporting conversations
    """

    status_message = Signal(str)

    def __init__(
        self,
        config: LiteConfig,
        storage: LiteStorage,
        parent: Optional[QWidget] = None,
    ) -> None:
        """Initialize the document interrogation tab."""
        super().__init__(parent)
        self.config = config
        self.storage = storage
        self._agent = LiteInterrogationAgent(config=config, storage=storage)
        self._worker: Optional[AnswerWorker] = None
        self._pdf_worker: Optional[PDFDiscoveryWorker] = None
        self._pdf_progress_dialog: Optional[QProgressDialog] = None
        self._document_loaded = False
        self._current_doc_metadata: Optional[dict] = None
        self._current_pdf_path: Optional[Path] = None
        self._pending_citation: Optional['Citation'] = None
        self._pending_fetch_title: Optional[str] = None

        self.scale = get_font_scale()
        self.conversation_history: List[dict] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._create_top_bar())
        layout.addWidget(self._create_split_pane())

    def _create_top_bar(self) -> QWidget:
        """Create top bar with file selector."""
        s = self.scale
        widget = QWidget()
        widget.setStyleSheet("QWidget { background-color: #F5F5F5; border-bottom: 1px solid #D0D0D0; }")
        widget.setFixedHeight(s['control_height_medium'] + s['padding_medium'])

        layout = QHBoxLayout(widget)
        layout.setContentsMargins(s['padding_small'], s['padding_tiny'], s['padding_small'], s['padding_tiny'])
        layout.setSpacing(s['spacing_medium'])

        self.load_btn = self._create_button("Load Document", self._load_document, "Load a text, markdown, or PDF document")
        layout.addWidget(self.load_btn)

        self.fetch_pdf_btn = QPushButton("Fetch PDF")
        self.fetch_pdf_btn.clicked.connect(self._fetch_pdf_from_identifier)
        self.fetch_pdf_btn.setFixedHeight(s['control_height_medium'])
        self.fetch_pdf_btn.setToolTip("Try to fetch PDF from DOI/PMID")
        self.fetch_pdf_btn.setStyleSheet(f"QPushButton {{ padding: {s['padding_tiny']}px {s['padding_medium']}px; font-size: {s['font_small']}pt; background-color: #FFA726; color: white; }} QPushButton:hover {{ background-color: #FF9800; }}")
        layout.addWidget(self.fetch_pdf_btn)

        self.doc_label = QLabel("No document loaded")
        self.doc_label.setStyleSheet(f"QLabel {{ color: #666; font-style: italic; font-size: {s['font_small']}pt; }}")
        layout.addWidget(self.doc_label, 1)

        self.clear_btn = self._create_button("Clear", self._clear_document)
        self.clear_btn.setEnabled(False)
        layout.addWidget(self.clear_btn)

        self.wrong_pdf_btn = QPushButton("Wrong PDF")
        self.wrong_pdf_btn.clicked.connect(self._handle_wrong_pdf)
        self.wrong_pdf_btn.setEnabled(False)
        self.wrong_pdf_btn.setVisible(False)
        self.wrong_pdf_btn.setFixedHeight(s['control_height_medium'])
        self.wrong_pdf_btn.setStyleSheet(f"QPushButton {{ padding: {s['padding_tiny']}px {s['padding_medium']}px; font-size: {s['font_small']}pt; background-color: #FFE4E1; color: #8B0000; }} QPushButton:hover {{ background-color: #FFB6C1; }}")
        layout.addWidget(self.wrong_pdf_btn)

        return widget

    def _create_button(self, text: str, callback, tooltip: str = "") -> QPushButton:
        """Create a styled button."""
        s = self.scale
        btn = QPushButton(text)
        btn.clicked.connect(callback)
        btn.setFixedHeight(s['control_height_medium'])
        if tooltip:
            btn.setToolTip(tooltip)
        btn.setStyleSheet(f"QPushButton {{ padding: {s['padding_tiny']}px {s['padding_medium']}px; font-size: {s['font_small']}pt; }}")
        return btn

    def _create_split_pane(self) -> QSplitter:
        """Create split pane with document viewer and chat interface."""
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._create_document_pane())
        splitter.addWidget(self._create_chat_pane())
        splitter.setSizes([DOCUMENT_PANE_WIDTH, CHAT_PANE_WIDTH])
        return splitter

    def _create_document_pane(self) -> QWidget:
        """Create document viewer pane."""
        s = self.scale
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QLabel("Document Viewer")
        header.setStyleSheet(f"QLabel {{ background-color: #E0E0E0; padding: {s['padding_small']}px {s['padding_medium']}px; font-weight: bold; font-size: {s['font_large']}pt; }}")
        layout.addWidget(header)

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

        # Header
        header_widget = QWidget()
        header_widget.setStyleSheet("QWidget { background-color: #E0E0E0; }")
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(s['padding_medium'], s['padding_small'], s['padding_medium'], s['padding_small'])

        header_label = QLabel("Chat")
        header_label.setStyleSheet(f"QLabel {{ font-weight: bold; font-size: {s['font_large']}pt; background-color: transparent; }}")
        header_layout.addWidget(header_label)
        header_layout.addStretch()

        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self._on_save_conversation)
        self.save_btn.setFixedHeight(s['control_height_small'])
        self.save_btn.setStyleSheet(f"QPushButton {{ padding: {s['padding_tiny']}px {s['padding_small']}px; font-size: {s['font_small']}pt; background-color: #FFFFFF; border: 1px solid #CCC; border-radius: {s['radius_small']}px; }} QPushButton:hover {{ background-color: #F0F0F0; }}")
        header_layout.addWidget(self.save_btn)
        layout.addWidget(header_widget)

        # Chat area
        self.chat_scroll_area = QScrollArea()
        self.chat_scroll_area.setWidgetResizable(True)
        self.chat_scroll_area.setStyleSheet("QScrollArea { border: none; background-color: #FAFAFA; }")

        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(s['spacing_medium'], s['spacing_medium'], s['spacing_medium'], s['spacing_medium'])
        self.chat_layout.setSpacing(s['spacing_medium'] * 2)
        self.chat_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._add_welcome_message()
        self.chat_scroll_area.setWidget(self.chat_container)
        layout.addWidget(self.chat_scroll_area, 1)

        # Progress
        self.progress_label = QLabel("")
        self.progress_label.setStyleSheet(f"QLabel {{ color: #666; font-style: italic; padding: {s['padding_tiny']}px {s['padding_medium']}px; font-size: {s['font_small']}pt; }}")
        self.progress_label.setVisible(False)
        layout.addWidget(self.progress_label)

        # Input
        layout.addWidget(self._create_input_area())
        return widget

    def _create_input_area(self) -> QWidget:
        """Create message input area."""
        s = self.scale
        widget = QWidget()
        widget.setStyleSheet("QWidget { background-color: white; border-top: 1px solid #CCC; }")
        widget.setFixedHeight(s['control_height_large'] + (s['padding_medium'] * 2))

        layout = QHBoxLayout(widget)
        layout.setContentsMargins(s['spacing_medium'], s['spacing_medium'], s['spacing_medium'], s['spacing_medium'])
        layout.setSpacing(s['spacing_medium'])

        self.message_input = QTextEdit()
        self.message_input.setPlaceholderText("Ask a question about the document...")
        self.message_input.setStyleSheet(f"QTextEdit {{ border: 1px solid #CCC; border-radius: {s['padding_tiny']}px; padding: {s['padding_small']}px; font-size: {s['font_medium']}pt; }} QTextEdit:focus {{ border: 1px solid #2196F3; }}")
        self.message_input.setFixedHeight(s['control_height_large'])
        layout.addWidget(self.message_input, 1)

        self.send_btn = QPushButton("Send")
        self.send_btn.clicked.connect(self._ask_question)
        self.send_btn.setEnabled(False)
        self.send_btn.setFixedSize(max(70, int(s['char_width'] * 8)), s['control_height_large'])
        self.send_btn.setStyleSheet(f"QPushButton {{ background-color: #2196F3; color: white; border-radius: {s['padding_tiny']}px; font-weight: bold; font-size: {s['font_medium']}pt; }} QPushButton:hover {{ background-color: #1976D2; }} QPushButton:disabled {{ background-color: #CCC; color: #666; }}")
        layout.addWidget(self.send_btn)
        return widget

    # -------------------------------------------------------------------------
    # Chat Methods
    # -------------------------------------------------------------------------

    def _add_welcome_message(self) -> None:
        """Add welcome message to chat."""
        self._add_chat_bubble(
            "Welcome to Document Interrogation!\n\nLoad a document to get started. "
            "I'll help you analyze and answer questions about your document.",
            is_user=False, track_history=False
        )

    def _add_chat_bubble(self, text: str, is_user: bool, track_history: bool = True) -> None:
        """Add a chat bubble to the chat area."""
        s = self.scale
        if track_history:
            self.conversation_history.append(create_conversation_message("user" if is_user else "assistant", text))

        bubble = ChatBubble(text, is_user, s)
        icon_label = QLabel("You" if is_user else "AI")
        icon_label.setStyleSheet(f"QLabel {{ font-size: {s['font_small']}pt; font-weight: bold; background-color: transparent; color: {'#666' if is_user else '#2196F3'}; }}")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        icon_label.setFixedWidth(int(s['char_width'] * 4))

        container = QWidget()
        container.setStyleSheet("background-color: transparent;")
        container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        container_layout = QHBoxLayout(container)
        container_layout.setSpacing(s['spacing_small'])

        m_small, m_large = s.get('bubble_margin_small', s['spacing_small']), s.get('bubble_margin_large', s['spacing_large'])
        container_layout.setContentsMargins(m_small if is_user else m_large, 0, m_large if is_user else m_small, 0)
        container_layout.addWidget(icon_label, 0)
        container_layout.addWidget(bubble, 1)
        self.chat_layout.addWidget(container)
        QTimer.singleShot(100, lambda: self.chat_scroll_area.verticalScrollBar().setValue(self.chat_scroll_area.verticalScrollBar().maximum()))

    def _clear_chat(self) -> None:
        """Clear chat history and re-add welcome message."""
        self.conversation_history.clear()
        while self.chat_layout.count():
            child = self.chat_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self._add_welcome_message()

    # -------------------------------------------------------------------------
    # Document Loading
    # -------------------------------------------------------------------------

    def _load_document(self) -> None:
        """Load a document from file."""
        file_path, _ = QFileDialog.getOpenFileName(self, "Load Document", str(Path.home()), "Documents (*.txt *.md *.pdf);;All Files (*)")
        if not file_path:
            return

        path = Path(file_path)
        try:
            self.progress_label.setText("Loading document...")
            self.progress_label.setVisible(True)
            text = self.document_view.load_file(file_path)
            if not text.strip():
                self.doc_label.setText("Error: Document is empty")
                self.progress_label.setVisible(False)
                return

            self._agent.load_document(text, title=path.name)
            self._set_document_loaded(path.name)
            self._add_chat_bubble(f"Document loaded: **{path.name}**\n\nYou can now ask questions about this document.", is_user=False)
            self.status_message.emit(f"Loaded document: {path.name}")
        except Exception as e:
            logger.exception("Failed to load document")
            self.doc_label.setText(f"Error: {str(e)}")
            self.progress_label.setVisible(False)
            QMessageBox.critical(self, "Error", f"Failed to load document:\n{str(e)}")

    def _clear_document(self) -> None:
        """Clear the loaded document."""
        self._agent.clear_document()
        self.document_view.clear()
        self.doc_label.setText("No document loaded")
        self.doc_label.setStyleSheet(f"QLabel {{ color: #666; font-style: italic; font-size: {self.scale['font_small']}pt; }}")
        self._document_loaded = False
        self._current_doc_metadata = None
        self._current_pdf_path = None
        self.send_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        self.wrong_pdf_btn.setEnabled(False)
        self.wrong_pdf_btn.setVisible(False)
        self._clear_chat()

    def _set_document_loaded(self, title: str, source_type: str = "", show_wrong_pdf: bool = False) -> None:
        """Set UI state for loaded document."""
        display = f"Loaded: {title[:50]}{'...' if len(title) > 50 else ''}"
        if source_type:
            display += f" ({source_type})"
        self.doc_label.setText(display)
        self.doc_label.setStyleSheet(f"QLabel {{ color: #000; font-weight: bold; font-size: {self.scale['font_small']}pt; }}")
        self._document_loaded = True
        self.send_btn.setEnabled(True)
        self.clear_btn.setEnabled(True)
        self.progress_label.setVisible(False)
        self.wrong_pdf_btn.setEnabled(show_wrong_pdf)
        self.wrong_pdf_btn.setVisible(show_wrong_pdf)

    # -------------------------------------------------------------------------
    # Question Asking
    # -------------------------------------------------------------------------

    def _ask_question(self) -> None:
        """Ask a question about the document."""
        question = self.message_input.toPlainText().strip()
        if not question or not self._document_loaded:
            return

        self._add_chat_bubble(question, is_user=True)
        self.message_input.clear()
        self.send_btn.setEnabled(False)
        self.message_input.setEnabled(False)
        self.progress_label.setText("Thinking...")
        self.progress_label.setVisible(True)

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

    # -------------------------------------------------------------------------
    # Conversation Export
    # -------------------------------------------------------------------------

    def _on_save_conversation(self) -> None:
        """Handle save conversation button click."""
        if not self.conversation_history:
            QMessageBox.information(self, "No Conversation", "No conversation to save yet.")
            return

        menu = QMenu(self)
        json_action = menu.addAction("Save as JSON")
        md_action = menu.addAction("Save as Markdown")
        action = menu.exec_(self.save_btn.mapToGlobal(self.save_btn.rect().bottomLeft()))

        if action == json_action:
            self._save_as_format("json", export_conversation_to_json)
        elif action == md_action:
            self._save_as_format("md", export_conversation_to_markdown)

    def _save_as_format(self, ext: str, export_func) -> None:
        """Save conversation in specified format."""
        file_path, _ = QFileDialog.getSaveFileName(self, f"Save Conversation as {ext.upper()}", str(Path.home() / f"conversation.{ext}"), f"{ext.upper()} Files (*.{ext})")
        if not file_path:
            return
        try:
            content = export_func(self.conversation_history, self.document_view.get_title())
            Path(file_path).write_text(content, encoding='utf-8')
            self.status_message.emit(f"Saved conversation to: {Path(file_path).name}")
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save:\n{str(e)}")

    # -------------------------------------------------------------------------
    # PDF Discovery
    # -------------------------------------------------------------------------

    def _create_progress_dialog(self, title: str) -> QProgressDialog:
        """Create a progress dialog for PDF operations."""
        dialog = QProgressDialog(self)
        dialog.setWindowTitle(title)
        dialog.setLabelText("Initializing...")
        dialog.setMinimum(0)
        dialog.setMaximum(0)
        dialog.setMinimumWidth(scaled(PROGRESS_DIALOG_MIN_WIDTH))
        dialog.setAutoClose(True)
        dialog.setAutoReset(True)
        dialog.setCancelButtonText("Cancel")
        return dialog

    def _update_progress_dialog(self, stage: str, status: str) -> None:
        """Update the progress dialog."""
        if self._pdf_progress_dialog:
            self._pdf_progress_dialog.setLabelText(get_progress_stage_message(stage, status))

    def _cancel_pdf_discovery(self) -> None:
        """Cancel any running PDF discovery."""
        if self._pdf_worker:
            self._pdf_worker.cancel()
            self._pdf_worker = None
        if self._pdf_progress_dialog:
            self._pdf_progress_dialog.close()
            self._pdf_progress_dialog = None

    def _fetch_pdf_from_identifier(self) -> None:
        """Fetch PDF using DOI/PMID."""
        doi, pmid, pmcid, title = None, None, None, None
        if self._current_doc_metadata:
            doi, pmid = self._current_doc_metadata.get('doi'), self._current_doc_metadata.get('pmid')
            pmcid, title = self._current_doc_metadata.get('pmc_id'), self._current_doc_metadata.get('title')

        if not (doi or pmid or pmcid):
            dialog = IdentifierInputDialog(self)
            doi, pmid = dialog.get_identifiers()
            if not (doi or pmid):
                QMessageBox.warning(self, "No Identifier", "Please enter a DOI or PMID.")
                return

        self._start_pdf_discovery({'doi': doi, 'pmid': pmid, 'pmcid': pmcid, 'title': title}, title or f"PDF ({doi or pmid or pmcid})")

    def _start_pdf_discovery(self, doc_dict: dict, display_title: str, on_success=None, on_error=None) -> None:
        """Start PDF discovery in background."""
        self._current_doc_metadata = doc_dict
        self._pending_fetch_title = display_title

        existing = find_existing_pdf(doc_dict)
        if existing:
            self._load_pdf_file(existing, display_title)
            return

        self._pdf_progress_dialog = self._create_progress_dialog("Fetching PDF")
        self._pdf_progress_dialog.canceled.connect(lambda: (self._cancel_pdf_discovery(), on_error and on_error("Cancelled")))
        self._pdf_progress_dialog.show()

        self._pdf_worker = PDFDiscoveryWorker(doc_dict, get_pdf_base_dir(), getattr(self.config, 'unpaywall_email', None), self)
        self._pdf_worker.progress.connect(self._update_progress_dialog)
        self._pdf_worker.finished.connect(lambda p: self._on_pdf_ready(p, on_success))
        self._pdf_worker.verification_warning.connect(self._on_pdf_warning)
        self._pdf_worker.error.connect(lambda e: self._on_pdf_error(e, on_error))
        self._pdf_worker.start()

    def _on_pdf_ready(self, file_path: str, callback=None) -> None:
        """Handle PDF download completion."""
        if self._pdf_progress_dialog:
            self._pdf_progress_dialog.close()
            self._pdf_progress_dialog = None
        self._pdf_worker = None
        if callback:
            callback(file_path)
        else:
            self._load_pdf_file(Path(file_path), self._pending_fetch_title)

    def _on_pdf_error(self, error: str, callback=None) -> None:
        """Handle PDF download error."""
        if self._pdf_progress_dialog:
            self._pdf_progress_dialog.close()
            self._pdf_progress_dialog = None
        self._pdf_worker = None
        if callback:
            callback(error)
        else:
            QMessageBox.warning(self, "PDF Fetch Failed", f"Could not download PDF:\n{error}")

    def _on_pdf_warning(self, file_path: str, warning: str) -> None:
        """Handle PDF verification warning."""
        if self._pdf_progress_dialog:
            self._pdf_progress_dialog.close()
            self._pdf_progress_dialog = None
        self._pdf_worker = None
        logger.warning(f"PDF verification failed: {warning}")
        QMessageBox.warning(self, "PDF Verification Failed", f"Downloaded PDF may not match.\n\n{warning}\n\nFile: {file_path}")

    def _load_pdf_file(self, pdf_path: Path, title: str) -> None:
        """Load a PDF file into the viewer."""
        if not pdf_path.exists():
            QMessageBox.warning(self, "File Not Found", f"PDF not found:\n{pdf_path}")
            return
        try:
            text = extract_pdf_text(pdf_path)
            if not text.strip():
                QMessageBox.warning(self, "Empty PDF", "PDF contained no extractable text.")
                return

            self._current_pdf_path = pdf_path
            self.document_view.set_text(text, title)
            if self.document_view.pdf_tab.load_pdf(str(pdf_path)):
                self.document_view.show_pdf_tab()
            else:
                self.document_view.show_fulltext_tab()
            self._agent.load_document(text, title=title)
            self._set_document_loaded(title, "PDF", show_wrong_pdf=True)
            self._add_chat_bubble(f"Document loaded: **{title}**\n\nSource: PDF Discovery\n\nYou can now ask questions.", is_user=False)
            self.status_message.emit(f"Loaded: {title}")
        except Exception as e:
            logger.exception("Failed to load PDF")
            QMessageBox.critical(self, "Error", f"Failed to load PDF:\n{str(e)}")

    # -------------------------------------------------------------------------
    # Citation Loading
    # -------------------------------------------------------------------------

    def load_from_citation(self, citation: 'Citation') -> None:
        """Load a document from a citation object."""
        self._clear_document()
        self._current_doc_metadata = build_doc_metadata(citation)
        self._pending_citation = citation
        title = get_document_title(citation)

        existing = find_existing_pdf(self._current_doc_metadata)
        if existing:
            self._load_citation_pdf(existing, citation, "Full Text (PDF - cached)")
            return

        if not has_pdf_identifiers(citation):
            self._load_citation_abstract(citation)
            return

        self._start_pdf_discovery(
            self._current_doc_metadata, title,
            on_success=lambda p: self._load_citation_pdf(Path(p), citation, "Full Text (PDF)"),
            on_error=lambda e: self._load_citation_abstract(citation)
        )

    def _load_citation_pdf(self, pdf_path: Path, citation: 'Citation', source_type: str) -> None:
        """Load PDF for citation."""
        title = get_document_title(citation)
        try:
            text = extract_pdf_text(pdf_path)
            if not text.strip():
                self._load_citation_abstract(citation)
                return

            self._current_pdf_path = pdf_path
            self._agent.load_document(text, title=title)
            self.document_view.set_text(text, title)
            if self.document_view.pdf_tab.load_pdf(str(pdf_path)):
                self.document_view.show_pdf_tab()
            else:
                self.document_view.show_fulltext_tab()
            self._finalize_citation_load(citation, source_type, show_wrong_pdf=True)
        except Exception as e:
            logger.exception("Failed to load PDF")
            self._load_citation_abstract(citation)

    def _load_citation_abstract(self, citation: 'Citation') -> None:
        """Load abstract for citation."""
        title = get_document_title(citation)
        text = build_abstract_text(citation)
        if not text.strip():
            QMessageBox.warning(self, "No Content", f"No content available for:\n{title}")
            return
        try:
            self._agent.load_document(text, title=title)
            self.document_view.set_text(text, title)
            self.document_view.show_fulltext_tab()
            self._finalize_citation_load(citation, "Abstract")
        except Exception as e:
            logger.exception("Failed to load abstract")
            QMessageBox.critical(self, "Error", f"Failed to load document:\n{str(e)}")

    def _finalize_citation_load(self, citation: 'Citation', source_type: str, show_wrong_pdf: bool = False) -> None:
        """Finalize citation document load."""
        title = get_document_title(citation)
        self._set_document_loaded(title, source_type, show_wrong_pdf)
        passage = citation.passage[:500] + ('...' if len(citation.passage) > 500 else '')
        self._add_chat_bubble(f"Document loaded: **{title}**\n\nSource: {source_type}\n\n**Relevant passage:**\n> {passage}\n\nYou can now ask questions.", is_user=False)
        self.status_message.emit(f"Loaded: {title}")

    # -------------------------------------------------------------------------
    # Wrong PDF Handling
    # -------------------------------------------------------------------------

    def _handle_wrong_pdf(self) -> None:
        """Handle the Wrong PDF button click."""
        if not self._current_pdf_path:
            QMessageBox.warning(self, "No PDF", "No PDF is currently loaded.")
            return

        dialog = WrongPDFDialog(self._current_pdf_path, self.scale, self)
        action = dialog.get_action()

        if action == WrongPDFDialog.ACTION_DELETE:
            self._delete_pdf(self._current_pdf_path)
            self._clear_document()
            self._add_chat_bubble("The incorrect PDF has been deleted.", is_user=False)
        elif action == WrongPDFDialog.ACTION_RETRY:
            self._delete_pdf(self._current_pdf_path)
            doc_meta = self._current_doc_metadata
            self._clear_document()
            if doc_meta:
                self._add_chat_bubble("Deleted incorrect PDF. Attempting to fetch correct PDF...", is_user=False)
                self._start_pdf_discovery(doc_meta, doc_meta.get('title', 'PDF'))
            else:
                self._add_chat_bubble("Deleted incorrect PDF. Use Fetch PDF button manually.", is_user=False)
        elif action == WrongPDFDialog.ACTION_CLEAR_ONLY:
            pdf_path = self._current_pdf_path
            self._clear_document()
            self._add_chat_bubble(f"View cleared. PDF file kept at:\n`{pdf_path}`", is_user=False)

    def _delete_pdf(self, pdf_path: Path) -> bool:
        """Delete a PDF file and clean up."""
        try:
            if pdf_path.exists():
                pdf_path.unlink()
                logger.info(f"Deleted PDF: {pdf_path}")
                if self.storage and self._current_doc_metadata:
                    doc_id = self._current_doc_metadata.get('id')
                    if doc_id:
                        try:
                            self.storage.get_chunks_collection().delete(where={"source_id": str(doc_id)})
                        except Exception as e:
                            logger.warning(f"Could not delete chunks: {e}")
                return True
        except Exception as e:
            logger.exception(f"Failed to delete PDF: {pdf_path}")
            QMessageBox.warning(self, "Deletion Failed", f"Could not delete PDF:\n{str(e)}")
        return False
