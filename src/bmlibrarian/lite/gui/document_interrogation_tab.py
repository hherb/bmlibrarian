"""
Document Interrogation tab for BMLibrarian Lite.

Provides an interactive Q&A interface for loaded documents using
RAG (Retrieval Augmented Generation) pattern.
"""

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QPushButton,
    QLabel,
    QFileDialog,
    QGroupBox,
    QScrollArea,
    QFrame,
)
from PySide6.QtCore import Qt, Signal, QThread

from bmlibrarian.gui.qt.resources.dpi_scale import scaled
from bmlibrarian.gui.qt.resources.stylesheet_generator import StylesheetGenerator

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


class ChatMessage(QFrame):
    """
    A single chat message widget.

    Displays a message with role indicator and appropriate styling.
    """

    def __init__(
        self,
        text: str,
        is_user: bool,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Initialize the chat message.

        Args:
            text: Message text
            is_user: True if this is a user message, False for assistant
            parent: Optional parent widget
        """
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Raised)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(scaled(8), scaled(4), scaled(8), scaled(4))
        layout.setSpacing(scaled(4))

        # Role label
        role = "You" if is_user else "Assistant"
        role_label = QLabel(f"<b>{role}</b>")
        layout.addWidget(role_label)

        # Message text - use QTextEdit for markdown support
        message = QTextEdit()
        message.setReadOnly(True)
        message.setFrameShape(QFrame.NoFrame)
        message.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        if is_user:
            message.setPlainText(text)
        else:
            message.setMarkdown(text)

        # Adjust height to content
        doc = message.document()
        doc.setTextWidth(message.viewport().width())
        height = int(doc.size().height()) + scaled(10)
        message.setFixedHeight(min(height, scaled(400)))

        layout.addWidget(message)

        # Apply role-based styling via property for stylesheet matching
        self.setProperty("messageRole", "user" if is_user else "assistant")


class DocumentInterrogationTab(QWidget):
    """
    Document Interrogation tab widget.

    Provides interface for:
    - Loading documents (PDF/text)
    - Asking questions about the document
    - Viewing conversation history

    Attributes:
        config: Lite configuration
        storage: Storage layer
    """

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
        self._document_loaded = False

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        layout.setSpacing(scaled(8))

        # Document section
        doc_group = QGroupBox("Document")
        doc_layout = QHBoxLayout(doc_group)

        self.doc_label = QLabel("No document loaded")
        self.doc_label.setWordWrap(True)
        doc_layout.addWidget(self.doc_label, stretch=1)

        self.load_btn = QPushButton("Load Document")
        self.load_btn.clicked.connect(self._load_document)
        self.load_btn.setToolTip("Load a text or PDF document")
        doc_layout.addWidget(self.load_btn)

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self._clear_document)
        self.clear_btn.setEnabled(False)
        self.clear_btn.setToolTip("Clear the loaded document")
        doc_layout.addWidget(self.clear_btn)

        layout.addWidget(doc_group)

        # Chat history
        chat_group = QGroupBox("Conversation")
        chat_layout = QVBoxLayout(chat_group)

        # Scroll area for messages
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setAlignment(Qt.AlignTop)
        self.chat_layout.setSpacing(scaled(8))
        self.chat_layout.addStretch()

        self.scroll_area.setWidget(self.chat_container)
        chat_layout.addWidget(self.scroll_area)

        layout.addWidget(chat_group, stretch=1)

        # Input section
        input_group = QGroupBox("Ask a Question")
        input_layout = QVBoxLayout(input_group)

        self.question_input = QTextEdit()
        self.question_input.setPlaceholderText(
            "Type your question here...\n\n"
            "Examples:\n"
            "- What is the main finding of this study?\n"
            "- What methodology was used?\n"
            "- What are the limitations mentioned?"
        )
        self.question_input.setMaximumHeight(scaled(80))
        input_layout.addWidget(self.question_input)

        btn_layout = QHBoxLayout()

        self.status_label = QLabel("")
        btn_layout.addWidget(self.status_label, stretch=1)

        self.ask_btn = QPushButton("Ask")
        self.ask_btn.clicked.connect(self._ask_question)
        self.ask_btn.setEnabled(False)
        self.ask_btn.setToolTip("Submit your question")
        btn_layout.addWidget(self.ask_btn)

        input_layout.addLayout(btn_layout)
        layout.addWidget(input_group)

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
            self.status_label.setText("Loading document...")

            # Read document content
            if path.suffix.lower() == '.pdf':
                text = self._extract_pdf_text(path)
            else:
                text = path.read_text(encoding='utf-8')

            if not text.strip():
                self.doc_label.setText("Error: Document is empty")
                self.status_label.setText("")
                return

            # Load into agent
            self._agent.load_document(text, title=path.name)

            self.doc_label.setText(f"Loaded: {path.name}")
            self._document_loaded = True
            self.ask_btn.setEnabled(True)
            self.clear_btn.setEnabled(True)
            self.status_label.setText("Document ready")

            # Clear chat history
            self._clear_chat()

            logger.info(f"Loaded document: {path}")

        except Exception as e:
            logger.exception("Failed to load document")
            self.doc_label.setText(f"Error: {str(e)}")
            self.status_label.setText("")

    def _extract_pdf_text(self, path: Path) -> str:
        """
        Extract text from a PDF file.

        Args:
            path: Path to PDF file

        Returns:
            Extracted text content

        Raises:
            ValueError: If PyMuPDF is not installed
        """
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(path)
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()
            return text
        except ImportError:
            raise ValueError(
                "PDF support requires PyMuPDF. Install with: pip install PyMuPDF"
            )

    def _clear_document(self) -> None:
        """Clear the loaded document."""
        self._agent.clear_document()
        self.doc_label.setText("No document loaded")
        self._document_loaded = False
        self.ask_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        self.status_label.setText("")
        self._clear_chat()

    def _clear_chat(self) -> None:
        """Clear chat history."""
        while self.chat_layout.count() > 1:
            item = self.chat_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _ask_question(self) -> None:
        """Ask a question about the document."""
        question = self.question_input.toPlainText().strip()
        if not question or not self._document_loaded:
            return

        # Add user message to chat
        self._add_message(question, is_user=True)
        self.question_input.clear()

        # Disable input while processing
        self.ask_btn.setEnabled(False)
        self.question_input.setEnabled(False)
        self.status_label.setText("Thinking...")

        # Create worker
        self._worker = AnswerWorker(self._agent, question)
        self._worker.finished.connect(self._on_answer)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _add_message(self, text: str, is_user: bool) -> None:
        """
        Add a message to the chat.

        Args:
            text: Message text
            is_user: True if user message, False for assistant
        """
        message = ChatMessage(text, is_user)
        # Insert before the stretch
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, message)

        # Scroll to bottom
        self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        )

    def _on_answer(self, answer: str, sources: list) -> None:
        """Handle answer from worker."""
        self._add_message(answer, is_user=False)
        self.status_label.setText("")
        self._reset_input()

    def _on_error(self, message: str) -> None:
        """Handle error from worker."""
        self._add_message(f"Error: {message}", is_user=False)
        self.status_label.setText("Error occurred")
        self._reset_input()

    def _reset_input(self) -> None:
        """Reset input controls."""
        self.ask_btn.setEnabled(True)
        self.question_input.setEnabled(True)
        self._worker = None
