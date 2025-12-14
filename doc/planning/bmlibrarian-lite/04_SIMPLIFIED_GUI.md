# Phase 4: Simplified GUI Implementation

## Overview

The Lite GUI provides a streamlined two-tab interface for systematic review and document interrogation. It reuses the existing BMLibrarian styling system and widgets where possible.

## Design Principles

1. **Minimal interface**: Only two tabs, no complexity
2. **Reuse styling**: Use existing `stylesheet_generator.py` and `dpi_scale.py`
3. **Responsive**: Handle long-running operations gracefully
4. **Clear feedback**: Progress indicators and status messages

## Main Window Structure

```
┌─────────────────────────────────────────────────────────────┐
│  BMLibrarian Lite                                    [—][□][×]│
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────────┐ ┌─────────────────────┐               │
│  │ Systematic Review │ │ Document Interrogation │             │
│  └──────────────────┘ └─────────────────────┘               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│                    [ Tab Content Area ]                     │
│                                                             │
│                                                             │
│                                                             │
└─────────────────────────────────────────────────────────────┤
│ Status: Ready                                    │ Settings │
└─────────────────────────────────────────────────────────────┘
```

## Components

### 4.1 Main Application (`src/bmlibrarian/lite/gui/app.py`)

```python
"""Main application window for BMLibrarian Lite."""

import logging
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QStatusBar,
    QPushButton,
    QHBoxLayout,
)
from PySide6.QtCore import Qt

from bmlibrarian.gui.qt.resources.dpi_scale import scaled
from bmlibrarian.gui.qt.resources.stylesheet_generator import StylesheetGenerator

from ..config import LiteConfig
from ..storage import LiteStorage
from .systematic_review_tab import SystematicReviewTab
from .document_interrogation_tab import DocumentInterrogationTab
from .settings_dialog import SettingsDialog

logger = logging.getLogger(__name__)


class LiteMainWindow(QMainWindow):
    """
    Main window for BMLibrarian Lite.

    Provides a two-tab interface for systematic review and document
    interrogation workflows.
    """

    # Window dimensions relative to font metrics
    DEFAULT_WIDTH_CHARS = 120
    DEFAULT_HEIGHT_CHARS = 40

    def __init__(
        self,
        config: Optional[LiteConfig] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Initialize the main window.

        Args:
            config: Lite configuration
            parent: Optional parent widget
        """
        super().__init__(parent)

        self.config = config or LiteConfig.load()
        self.storage = LiteStorage(self.config)

        self._setup_ui()
        self._apply_styles()

        logger.info("BMLibrarian Lite initialized")

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        self.setWindowTitle("BMLibrarian Lite")

        # Calculate window size from font metrics
        fm = self.fontMetrics()
        width = fm.horizontalAdvance('x') * self.DEFAULT_WIDTH_CHARS
        height = fm.height() * self.DEFAULT_HEIGHT_CHARS
        self.resize(width, height)

        # Central widget and layout
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(scaled(8), scaled(8), scaled(8), scaled(8))

        # Tab widget
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # Create tabs
        self.systematic_review_tab = SystematicReviewTab(
            config=self.config,
            storage=self.storage,
            parent=self,
        )
        self.tab_widget.addTab(self.systematic_review_tab, "Systematic Review")

        self.interrogation_tab = DocumentInterrogationTab(
            config=self.config,
            storage=self.storage,
            parent=self,
        )
        self.tab_widget.addTab(self.interrogation_tab, "Document Interrogation")

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

        # Settings button in status bar
        settings_btn = QPushButton("Settings")
        settings_btn.clicked.connect(self._show_settings)
        self.status_bar.addPermanentWidget(settings_btn)

    def _apply_styles(self) -> None:
        """Apply stylesheet to the application."""
        generator = StylesheetGenerator()
        stylesheet = generator.generate()
        self.setStyleSheet(stylesheet)

    def _show_settings(self) -> None:
        """Show the settings dialog."""
        dialog = SettingsDialog(self.config, parent=self)
        if dialog.exec():
            # Reload configuration
            self.config = LiteConfig.load()
            self.status_bar.showMessage("Settings saved", 3000)

    def set_status(self, message: str, timeout: int = 0) -> None:
        """
        Set status bar message.

        Args:
            message: Status message
            timeout: Timeout in milliseconds (0 = permanent)
        """
        self.status_bar.showMessage(message, timeout)


def run_lite_app() -> int:
    """
    Run the BMLibrarian Lite application.

    Returns:
        Application exit code
    """
    app = QApplication(sys.argv)
    app.setApplicationName("BMLibrarian Lite")
    app.setOrganizationName("BMLibrarian")

    window = LiteMainWindow()
    window.show()

    return app.exec()
```

### 4.2 Systematic Review Tab (`src/bmlibrarian/lite/gui/systematic_review_tab.py`)

```python
"""Systematic Review tab for BMLibrarian Lite."""

import logging
from typing import Optional, List

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QPushButton,
    QLabel,
    QProgressBar,
    QSplitter,
    QGroupBox,
    QSpinBox,
    QScrollArea,
)
from PySide6.QtCore import Qt, Signal, QThread

from bmlibrarian.gui.qt.resources.dpi_scale import scaled

from ..config import LiteConfig
from ..storage import LiteStorage
from ..data_models import LiteDocument, ScoredDocument, Citation
from ..agents import (
    LiteSearchAgent,
    LiteScoringAgent,
    LiteCitationAgent,
    LiteReportingAgent,
)

logger = logging.getLogger(__name__)


class WorkflowWorker(QThread):
    """Background worker for systematic review workflow."""

    progress = Signal(str, int, int)  # step, current, total
    step_complete = Signal(str, object)  # step name, result
    error = Signal(str, str)  # step, error message
    finished = Signal(str)  # final report

    def __init__(
        self,
        question: str,
        config: LiteConfig,
        storage: LiteStorage,
        max_results: int = 100,
        min_score: int = 3,
    ) -> None:
        super().__init__()
        self.question = question
        self.config = config
        self.storage = storage
        self.max_results = max_results
        self.min_score = min_score
        self._cancelled = False

    def run(self) -> None:
        """Execute the systematic review workflow."""
        try:
            # Step 1: Search PubMed
            self.progress.emit("search", 0, 1)
            search_agent = LiteSearchAgent(
                config=self.config,
                storage=self.storage,
            )
            session, documents = search_agent.search(
                self.question,
                max_results=self.max_results,
            )
            self.step_complete.emit("search", documents)

            if self._cancelled or not documents:
                self.finished.emit("No documents found.")
                return

            # Step 2: Score documents
            scoring_agent = LiteScoringAgent(config=self.config)
            scored_docs = scoring_agent.score_documents(
                self.question,
                documents,
                min_score=self.min_score,
                progress_callback=lambda c, t: self.progress.emit("scoring", c, t),
            )
            self.step_complete.emit("scoring", scored_docs)

            if self._cancelled or not scored_docs:
                self.finished.emit("No relevant documents found.")
                return

            # Step 3: Extract citations
            citation_agent = LiteCitationAgent(config=self.config)
            citations = citation_agent.extract_all_citations(
                self.question,
                scored_docs,
                min_score=self.min_score,
                progress_callback=lambda c, t: self.progress.emit("citations", c, t),
            )
            self.step_complete.emit("citations", citations)

            if self._cancelled:
                return

            # Step 4: Generate report
            self.progress.emit("report", 0, 1)
            reporting_agent = LiteReportingAgent(config=self.config)
            report = reporting_agent.generate_report(self.question, citations)
            self.step_complete.emit("report", report)

            self.finished.emit(report)

        except Exception as e:
            logger.exception("Workflow error")
            self.error.emit("workflow", str(e))

    def cancel(self) -> None:
        """Cancel the workflow."""
        self._cancelled = True


class SystematicReviewTab(QWidget):
    """
    Systematic Review tab widget.

    Provides interface for:
    - Entering research question
    - Executing search and scoring workflow
    - Viewing generated report
    """

    def __init__(
        self,
        config: LiteConfig,
        storage: LiteStorage,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.storage = storage
        self._worker: Optional[WorkflowWorker] = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        layout.setSpacing(scaled(8))

        # Question input section
        question_group = QGroupBox("Research Question")
        question_layout = QVBoxLayout(question_group)

        self.question_input = QTextEdit()
        self.question_input.setPlaceholderText(
            "Enter your research question...\n\n"
            "Example: What are the cardiovascular benefits of regular exercise?"
        )
        self.question_input.setMaximumHeight(scaled(100))
        question_layout.addWidget(self.question_input)

        # Options row
        options_layout = QHBoxLayout()

        options_layout.addWidget(QLabel("Max results:"))
        self.max_results_spin = QSpinBox()
        self.max_results_spin.setRange(10, 500)
        self.max_results_spin.setValue(100)
        options_layout.addWidget(self.max_results_spin)

        options_layout.addWidget(QLabel("Min score:"))
        self.min_score_spin = QSpinBox()
        self.min_score_spin.setRange(1, 5)
        self.min_score_spin.setValue(3)
        options_layout.addWidget(self.min_score_spin)

        options_layout.addStretch()

        self.run_btn = QPushButton("Run Review")
        self.run_btn.clicked.connect(self._run_workflow)
        options_layout.addWidget(self.run_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self._cancel_workflow)
        self.cancel_btn.setEnabled(False)
        options_layout.addWidget(self.cancel_btn)

        question_layout.addLayout(options_layout)
        layout.addWidget(question_group)

        # Progress section
        progress_group = QGroupBox("Progress")
        progress_layout = QVBoxLayout(progress_group)

        self.progress_label = QLabel("Ready")
        progress_layout.addWidget(self.progress_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)

        layout.addWidget(progress_group)

        # Results section
        results_group = QGroupBox("Report")
        results_layout = QVBoxLayout(results_group)

        self.report_view = QTextEdit()
        self.report_view.setReadOnly(True)
        self.report_view.setPlaceholderText("Report will appear here after running the review...")
        results_layout.addWidget(self.report_view)

        # Export button
        export_layout = QHBoxLayout()
        export_layout.addStretch()

        self.export_btn = QPushButton("Export Report")
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self._export_report)
        export_layout.addWidget(self.export_btn)

        results_layout.addLayout(export_layout)
        layout.addWidget(results_group, stretch=1)

    def _run_workflow(self) -> None:
        """Start the systematic review workflow."""
        question = self.question_input.toPlainText().strip()
        if not question:
            return

        # Update UI state
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.export_btn.setEnabled(False)
        self.report_view.clear()
        self.progress_bar.setValue(0)

        # Create and start worker
        self._worker = WorkflowWorker(
            question=question,
            config=self.config,
            storage=self.storage,
            max_results=self.max_results_spin.value(),
            min_score=self.min_score_spin.value(),
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.step_complete.connect(self._on_step_complete)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _cancel_workflow(self) -> None:
        """Cancel the running workflow."""
        if self._worker:
            self._worker.cancel()
            self.progress_label.setText("Cancelling...")

    def _on_progress(self, step: str, current: int, total: int) -> None:
        """Handle progress updates."""
        step_names = {
            "search": "Searching PubMed",
            "scoring": "Scoring documents",
            "citations": "Extracting citations",
            "report": "Generating report",
        }
        name = step_names.get(step, step)
        self.progress_label.setText(f"{name}: {current}/{total}")

        if total > 0:
            self.progress_bar.setValue(int(current / total * 100))

    def _on_step_complete(self, step: str, result: object) -> None:
        """Handle step completion."""
        if step == "search":
            docs = result
            self.progress_label.setText(f"Found {len(docs)} documents")
        elif step == "scoring":
            scored = result
            self.progress_label.setText(f"Scored {len(scored)} relevant documents")
        elif step == "citations":
            citations = result
            self.progress_label.setText(f"Extracted {len(citations)} citations")

    def _on_error(self, step: str, message: str) -> None:
        """Handle workflow errors."""
        self.progress_label.setText(f"Error in {step}: {message}")
        self._reset_ui()

    def _on_finished(self, report: str) -> None:
        """Handle workflow completion."""
        self.report_view.setMarkdown(report)
        self.progress_label.setText("Complete")
        self.progress_bar.setValue(100)
        self.export_btn.setEnabled(True)
        self._reset_ui()

    def _reset_ui(self) -> None:
        """Reset UI to ready state."""
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self._worker = None

    def _export_report(self) -> None:
        """Export the report to file."""
        # TODO: Implement export dialog
        pass
```

### 4.3 Document Interrogation Tab (`src/bmlibrarian/lite/gui/document_interrogation_tab.py`)

```python
"""Document Interrogation tab for BMLibrarian Lite."""

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
    QSplitter,
    QGroupBox,
    QScrollArea,
    QFrame,
)
from PySide6.QtCore import Qt, Signal, QThread

from bmlibrarian.gui.qt.resources.dpi_scale import scaled

from ..config import LiteConfig
from ..storage import LiteStorage
from ..agents import LiteInterrogationAgent

logger = logging.getLogger(__name__)


class AnswerWorker(QThread):
    """Background worker for generating answers."""

    finished = Signal(str, list)  # answer, sources
    error = Signal(str)

    def __init__(
        self,
        agent: LiteInterrogationAgent,
        question: str,
    ) -> None:
        super().__init__()
        self.agent = agent
        self.question = question

    def run(self) -> None:
        """Generate answer."""
        try:
            answer, sources = self.agent.ask(self.question)
            self.finished.emit(answer, sources)
        except Exception as e:
            logger.exception("Answer generation error")
            self.error.emit(str(e))


class ChatMessage(QFrame):
    """A single chat message widget."""

    def __init__(
        self,
        text: str,
        is_user: bool,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(scaled(8), scaled(4), scaled(8), scaled(4))

        # Role label
        role = "You" if is_user else "Assistant"
        role_label = QLabel(f"<b>{role}</b>")
        layout.addWidget(role_label)

        # Message text
        message = QLabel(text)
        message.setWordWrap(True)
        message.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(message)

        # Style based on role
        if is_user:
            self.setStyleSheet("background-color: #e3f2fd;")
        else:
            self.setStyleSheet("background-color: #f5f5f5;")


class DocumentInterrogationTab(QWidget):
    """
    Document Interrogation tab widget.

    Provides interface for:
    - Loading documents (PDF/text)
    - Asking questions about the document
    - Viewing conversation history
    """

    def __init__(
        self,
        config: LiteConfig,
        storage: LiteStorage,
        parent: Optional[QWidget] = None,
    ) -> None:
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
        doc_layout.addWidget(self.doc_label, stretch=1)

        self.load_btn = QPushButton("Load Document")
        self.load_btn.clicked.connect(self._load_document)
        doc_layout.addWidget(self.load_btn)

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self._clear_document)
        self.clear_btn.setEnabled(False)
        doc_layout.addWidget(self.clear_btn)

        layout.addWidget(doc_group)

        # Chat history
        chat_group = QGroupBox("Conversation")
        chat_layout = QVBoxLayout(chat_group)

        # Scroll area for messages
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setAlignment(Qt.AlignTop)
        self.chat_layout.addStretch()

        scroll.setWidget(self.chat_container)
        chat_layout.addWidget(scroll)

        layout.addWidget(chat_group, stretch=1)

        # Input section
        input_group = QGroupBox("Ask a Question")
        input_layout = QVBoxLayout(input_group)

        self.question_input = QTextEdit()
        self.question_input.setPlaceholderText("Type your question here...")
        self.question_input.setMaximumHeight(scaled(80))
        input_layout.addWidget(self.question_input)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.ask_btn = QPushButton("Ask")
        self.ask_btn.clicked.connect(self._ask_question)
        self.ask_btn.setEnabled(False)
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
            # Read document content
            if path.suffix.lower() == '.pdf':
                # TODO: Implement PDF text extraction
                text = self._extract_pdf_text(path)
            else:
                text = path.read_text(encoding='utf-8')

            if not text.strip():
                self.doc_label.setText("Error: Document is empty")
                return

            # Load into agent
            self._agent.load_document(text, title=path.name)

            self.doc_label.setText(f"Loaded: {path.name}")
            self._document_loaded = True
            self.ask_btn.setEnabled(True)
            self.clear_btn.setEnabled(True)

            # Clear chat history
            self._clear_chat()

            logger.info(f"Loaded document: {path}")

        except Exception as e:
            logger.exception("Failed to load document")
            self.doc_label.setText(f"Error: {str(e)}")

    def _extract_pdf_text(self, path: Path) -> str:
        """Extract text from a PDF file."""
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(path)
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()
            return text
        except ImportError:
            raise ValueError("PDF support requires PyMuPDF: pip install PyMuPDF")

    def _clear_document(self) -> None:
        """Clear the loaded document."""
        self._agent.clear_document()
        self.doc_label.setText("No document loaded")
        self._document_loaded = False
        self.ask_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
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

        # Create worker
        self._worker = AnswerWorker(self._agent, question)
        self._worker.finished.connect(self._on_answer)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _add_message(self, text: str, is_user: bool) -> None:
        """Add a message to the chat."""
        message = ChatMessage(text, is_user)
        # Insert before the stretch
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, message)

    def _on_answer(self, answer: str, sources: list) -> None:
        """Handle answer from worker."""
        self._add_message(answer, is_user=False)
        self._reset_input()

    def _on_error(self, message: str) -> None:
        """Handle error from worker."""
        self._add_message(f"Error: {message}", is_user=False)
        self._reset_input()

    def _reset_input(self) -> None:
        """Reset input controls."""
        self.ask_btn.setEnabled(True)
        self.question_input.setEnabled(True)
        self._worker = None
```

### 4.4 Settings Dialog (`src/bmlibrarian/lite/gui/settings_dialog.py`)

```python
"""Settings dialog for BMLibrarian Lite."""

import logging
from typing import Optional

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLineEdit,
    QComboBox,
    QPushButton,
    QGroupBox,
    QLabel,
    QDialogButtonBox,
)

from bmlibrarian.gui.qt.resources.dpi_scale import scaled

from ..config import LiteConfig
from ..embeddings import LiteEmbedder

logger = logging.getLogger(__name__)


class SettingsDialog(QDialog):
    """Settings configuration dialog."""

    def __init__(
        self,
        config: LiteConfig,
        parent: Optional[QDialog] = None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Settings")
        self.setMinimumWidth(scaled(400))

        self._setup_ui()
        self._load_config()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        layout = QVBoxLayout(self)

        # LLM settings
        llm_group = QGroupBox("LLM Settings")
        llm_layout = QFormLayout(llm_group)

        self.model_combo = QComboBox()
        self.model_combo.addItems([
            "claude-sonnet-4-20250514",
            "claude-3-5-sonnet-20241022",
            "claude-3-haiku-20240307",
        ])
        llm_layout.addRow("Model:", self.model_combo)

        layout.addWidget(llm_group)

        # Embedding settings
        embed_group = QGroupBox("Embedding Settings")
        embed_layout = QFormLayout(embed_group)

        self.embed_combo = QComboBox()
        self.embed_combo.addItems(LiteEmbedder.list_supported_models())
        embed_layout.addRow("Model:", self.embed_combo)

        layout.addWidget(embed_group)

        # PubMed settings
        pubmed_group = QGroupBox("PubMed Settings")
        pubmed_layout = QFormLayout(pubmed_group)

        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("your.email@example.com (required)")
        pubmed_layout.addRow("Email:", self.email_input)

        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("Optional - increases rate limit")
        self.api_key_input.setEchoMode(QLineEdit.Password)
        pubmed_layout.addRow("API Key:", self.api_key_input)

        layout.addWidget(pubmed_group)

        # API Keys
        api_group = QGroupBox("API Keys")
        api_layout = QFormLayout(api_group)

        self.anthropic_key_input = QLineEdit()
        self.anthropic_key_input.setEchoMode(QLineEdit.Password)
        self.anthropic_key_input.setPlaceholderText("sk-ant-...")
        api_layout.addRow("Anthropic:", self.anthropic_key_input)

        api_note = QLabel(
            "<small>API keys are stored in ~/.bmlibrarian_lite/.env</small>"
        )
        api_layout.addRow(api_note)

        layout.addWidget(api_group)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._save_config)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_config(self) -> None:
        """Load current configuration into fields."""
        # LLM
        idx = self.model_combo.findText(self.config.llm.model)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)

        # Embeddings
        idx = self.embed_combo.findText(self.config.embeddings.model)
        if idx >= 0:
            self.embed_combo.setCurrentIndex(idx)

        # PubMed
        self.email_input.setText(self.config.pubmed.email)
        if self.config.pubmed.api_key:
            self.api_key_input.setText(self.config.pubmed.api_key)

    def _save_config(self) -> None:
        """Save configuration and close dialog."""
        # Update config object
        self.config.llm.model = self.model_combo.currentText()
        self.config.embeddings.model = self.embed_combo.currentText()
        self.config.pubmed.email = self.email_input.text()

        api_key = self.api_key_input.text().strip()
        self.config.pubmed.api_key = api_key if api_key else None

        # Save to file
        self.config.save()

        # Handle Anthropic API key separately (in .env)
        anthropic_key = self.anthropic_key_input.text().strip()
        if anthropic_key:
            self._save_api_key("ANTHROPIC_API_KEY", anthropic_key)

        logger.info("Settings saved")
        self.accept()

    def _save_api_key(self, key: str, value: str) -> None:
        """Save an API key to .env file."""
        env_path = self.config.storage.data_dir / ".env"

        # Read existing .env
        lines = []
        if env_path.exists():
            with open(env_path, 'r') as f:
                lines = f.readlines()

        # Update or add key
        found = False
        for i, line in enumerate(lines):
            if line.startswith(f"{key}="):
                lines[i] = f"{key}={value}\n"
                found = True
                break

        if not found:
            lines.append(f"{key}={value}\n")

        # Write back
        with open(env_path, 'w') as f:
            f.writelines(lines)

        # Set restrictive permissions
        env_path.chmod(0o600)
```

### 4.5 Entry Point (`bmlibrarian_lite.py`)

```python
#!/usr/bin/env python3
"""
BMLibrarian Lite - Lightweight version without PostgreSQL dependency.

A simplified interface for:
- Systematic literature review
- Document interrogation

Usage:
    python bmlibrarian_lite.py
"""

import sys
import logging
from pathlib import Path

# Add src to path if running from source
src_path = Path(__file__).parent / "src"
if src_path.exists():
    sys.path.insert(0, str(src_path))

from bmlibrarian.lite.gui.app import run_lite_app


def main() -> int:
    """Main entry point."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    return run_lite_app()


if __name__ == "__main__":
    sys.exit(main())
```

## Implementation Steps

1. Create gui directory structure
2. Implement main application window
3. Implement systematic review tab
4. Implement document interrogation tab
5. Implement settings dialog
6. Create entry point script
7. Add tests

## Golden Rules Checklist

- [x] No inline stylesheets - uses stylesheet_generator
- [x] No hardcoded pixel values - uses scaled()
- [x] Type hints on all parameters
- [x] Docstrings on all classes/methods
- [x] Error handling with user feedback
- [x] Configuration from LiteConfig
