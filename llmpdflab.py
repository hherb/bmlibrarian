"""
LLM PDF Lab Application

A PySide6 application for testing LLM-based PDF text reformatting.
Uses PyMuPDF for text extraction and Ollama LLM for Markdown formatting.

Features:
- Tab 1: PDF viewer with model selector and Markdown preview
- Tab 2: Editable prompt for LLM reformatting customization
- Dynamic context window sizing based on text length
- Spinner status indicator during LLM processing
"""

import sys
import logging
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QTextEdit, QSplitter, QLabel, QMessageBox,
    QComboBox, QTabWidget, QPlainTextEdit, QProgressBar, QFrame
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtGui import QFont, QCloseEvent

import pymupdf
import ollama

# Configure logging
logger = logging.getLogger('llmpdflab')

# Ollama configuration
OLLAMA_HOST = "http://localhost:11434"

# LLM generation parameters
LLM_TEMPERATURE = 0.1  # Low temperature for consistent formatting
LLM_TOP_P = 0.9

# Window dimensions
WINDOW_WIDTH = 1400
WINDOW_HEIGHT = 900
WINDOW_X = 100
WINDOW_Y = 100

# Splitter initial sizes
SPLITTER_LEFT_WIDTH = 700
SPLITTER_RIGHT_WIDTH = 700

# Token estimation constants
CHARS_PER_TOKEN = 4  # Rough estimate: ~4 characters per token
TOKEN_RESERVE_RATIO = 1.5  # Reserve 50% extra for output and overhead
MIN_CONTEXT_LENGTH = 4096  # Minimum context length
MAX_CONTEXT_LENGTH = 131072  # Maximum context length (128K)

# Default model
DEFAULT_MODEL = "granite4:tiny-h"

# Default prompt for LLM reformatting
DEFAULT_PROMPT = """You are a text formatting assistant. Your task is to clean up and format raw text extracted from a PDF document into proper Markdown.

Instructions:
1. Remove line numbers if present (e.g., "1", "2", "3" at the start of lines)
2. Remove headers and footers if present (e.g., page numbers, running titles, copyright notices)
3. Format the title as a level 1 heading (#)
4. Format section headers as level 2 headings (##) and subsections as level 3 (###)
5. Fix paragraph formatting:
   - Remove inappropriate line breaks within paragraphs (join broken lines)
   - Add proper blank lines between paragraphs
   - Preserve intentional line breaks in lists, tables, and code blocks
6. Preserve any existing formatting like bold, italic, or lists
7. Do NOT add any commentary or explanation - output ONLY the formatted text

Raw text to format:
"""

# Styles
BUTTON_STYLE = """
    QPushButton {
        background-color: #4CAF50;
        color: white;
        padding: 10px 20px;
        font-size: 14px;
        border-radius: 5px;
    }
    QPushButton:hover {
        background-color: #45a049;
    }
    QPushButton:disabled {
        background-color: #BDBDBD;
        color: #757575;
    }
"""

RECONVERT_BUTTON_STYLE = """
    QPushButton {
        background-color: #2196F3;
        color: white;
        padding: 8px 16px;
        font-size: 13px;
        border-radius: 4px;
    }
    QPushButton:hover {
        background-color: #1976D2;
    }
    QPushButton:disabled {
        background-color: #BDBDBD;
        color: #757575;
    }
"""

COMBOBOX_STYLE = """
    QComboBox {
        padding: 5px 10px;
        font-size: 13px;
        min-width: 200px;
    }
"""

TITLE_STYLE = "font-size: 16px; font-weight: bold; padding: 5px;"
INFO_LABEL_STYLE = "font-weight: bold; padding: 5px;"
STATUS_STYLE = "padding: 5px; color: #666;"
PROMPT_STYLE = """
    QPlainTextEdit {
        font-family: monospace;
        font-size: 12px;
        line-height: 1.4;
    }
"""


def extract_text_with_pymupdf(file_path: str) -> str:
    """
    Extract text from PDF using basic PyMuPDF text extraction.

    Args:
        file_path: Path to PDF file.

    Returns:
        Raw extracted text.
    """
    doc = pymupdf.open(file_path)
    text_parts = []

    for page in doc:
        text = page.get_text("text")
        if text.strip():
            text_parts.append(text)

    doc.close()
    return "\n\n".join(text_parts)


def estimate_tokens(text: str) -> int:
    """
    Estimate the number of tokens in text.

    Uses a simple character-based estimation (roughly 4 chars per token).

    Args:
        text: Input text.

    Returns:
        Estimated token count.
    """
    return max(1, len(text) // CHARS_PER_TOKEN)


def calculate_context_length(input_text: str, prompt: str) -> int:
    """
    Calculate the required context length for LLM processing.

    Takes into account input tokens, prompt tokens, and reserves space
    for output tokens.

    Args:
        input_text: The text to be processed.
        prompt: The system prompt.

    Returns:
        Recommended context length (num_ctx value).
    """
    input_tokens = estimate_tokens(input_text)
    prompt_tokens = estimate_tokens(prompt)
    total_input = input_tokens + prompt_tokens

    # Reserve space for output (assume output is similar size to input)
    required_tokens = int(total_input * TOKEN_RESERVE_RATIO) + input_tokens

    # Clamp to reasonable bounds
    context_length = max(MIN_CONTEXT_LENGTH, min(required_tokens, MAX_CONTEXT_LENGTH))

    # Round up to nearest power of 2 for efficiency
    power = 1
    while power < context_length:
        power *= 2

    return min(power, MAX_CONTEXT_LENGTH)


class LLMWorker(QThread):
    """Worker thread for LLM processing to avoid blocking the UI."""

    finished = Signal(str)
    error = Signal(str)
    progress = Signal(str)

    def __init__(
        self,
        text: str,
        prompt: str,
        model: str,
        host: str = OLLAMA_HOST
    ) -> None:
        """
        Initialize the LLM worker.

        Args:
            text: Text to process.
            prompt: Formatting prompt.
            model: Ollama model name.
            host: Ollama server host.
        """
        super().__init__()
        self.text = text
        self.prompt = prompt
        self.model = model
        self.host = host

    def run(self) -> None:
        """Execute LLM processing in background thread."""
        try:
            self.progress.emit("Connecting to Ollama...")
            logger.debug(f"Connecting to Ollama at {self.host}")

            client = ollama.Client(host=self.host)

            # Calculate context length
            context_length = calculate_context_length(self.text, self.prompt)
            self.progress.emit(f"Using context length: {context_length:,} tokens")
            logger.info(f"Calculated context length: {context_length:,} tokens")

            # Build the full prompt
            full_prompt = self.prompt + self.text

            self.progress.emit(f"Processing with {self.model}...")
            logger.info(f"Starting generation with model: {self.model}")

            # Make the request with dynamic context length
            response = client.generate(
                model=self.model,
                prompt=full_prompt,
                options={
                    'num_ctx': context_length,
                    'temperature': LLM_TEMPERATURE,
                    'top_p': LLM_TOP_P
                }
            )

            result = response.get('response', '')
            if result:
                logger.info(f"Generation complete, received {len(result)} characters")
                self.finished.emit(result.strip())
            else:
                logger.warning("Empty response from LLM")
                self.error.emit("Empty response from LLM")

        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            self.error.emit(str(e))


class LLMPDFLabWindow(QMainWindow):
    """Main window for LLM PDF Lab application."""

    def __init__(self) -> None:
        """Initialize the LLM PDF Lab window."""
        super().__init__()
        self.setWindowTitle("LLM PDF Lab")
        self.setGeometry(WINDOW_X, WINDOW_Y, WINDOW_WIDTH, WINDOW_HEIGHT)

        # Initialize components
        self.pdf_document = QPdfDocument(self)
        self.current_pdf_path: Optional[str] = None
        self.raw_extracted_text: str = ""
        self.llm_worker: Optional[LLMWorker] = None

        # UI Components - initialized in _setup_ui
        self.tab_widget: QTabWidget
        self.info_label: QLabel
        self.model_combo: QComboBox
        self.pdf_view: QPdfView
        self.markdown_text: QTextEdit
        self.status_label: QLabel
        self.progress_bar: QProgressBar
        self.prompt_editor: QPlainTextEdit
        self.reconvert_button: QPushButton

        # Setup UI
        self._setup_ui()

        # Initialize model list
        self._refresh_models()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        # Central widget with tabs
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Create tab widget
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        # Tab 1: PDF Viewer and Markdown Preview
        viewer_tab = self._create_viewer_tab()
        self.tab_widget.addTab(viewer_tab, "PDF Viewer")

        # Tab 2: Prompt Editor
        prompt_tab = self._create_prompt_tab()
        self.tab_widget.addTab(prompt_tab, "Prompt Editor")

    def _create_viewer_tab(self) -> QWidget:
        """
        Create the PDF viewer and markdown preview tab.

        Returns:
            QWidget containing the viewer tab.
        """
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Top bar with file picker and model selector
        top_bar = self._create_top_bar()
        layout.addLayout(top_bar)

        # Splitter for PDF view and markdown
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left side: PDF viewer
        pdf_container = self._create_pdf_viewer()
        splitter.addWidget(pdf_container)

        # Right side: Markdown display
        markdown_container = self._create_markdown_viewer()
        splitter.addWidget(markdown_container)

        # Set initial sizes (50-50 split)
        splitter.setSizes([SPLITTER_LEFT_WIDTH, SPLITTER_RIGHT_WIDTH])
        layout.addWidget(splitter)

        # Status bar
        status_bar = self._create_status_bar()
        layout.addWidget(status_bar)

        return tab

    def _create_prompt_tab(self) -> QWidget:
        """
        Create the prompt editor tab.

        Returns:
            QWidget containing the prompt editor tab.
        """
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Header
        header_layout = QHBoxLayout()

        header_label = QLabel("LLM Formatting Prompt")
        header_label.setStyleSheet(TITLE_STYLE)
        header_layout.addWidget(header_label)

        header_layout.addStretch()

        # Reset to default button
        reset_btn = QPushButton("Reset to Default")
        reset_btn.clicked.connect(self._reset_prompt)
        header_layout.addWidget(reset_btn)

        # Reconvert button
        self.reconvert_button = QPushButton("Re-convert with New Prompt")
        self.reconvert_button.setStyleSheet(RECONVERT_BUTTON_STYLE)
        self.reconvert_button.clicked.connect(self._reconvert)
        self.reconvert_button.setEnabled(False)
        header_layout.addWidget(self.reconvert_button)

        layout.addLayout(header_layout)

        # Prompt editor
        self.prompt_editor = QPlainTextEdit()
        self.prompt_editor.setStyleSheet(PROMPT_STYLE)
        self.prompt_editor.setPlainText(DEFAULT_PROMPT)
        self.prompt_editor.setPlaceholderText("Enter your formatting prompt here...")
        layout.addWidget(self.prompt_editor)

        # Help text
        help_text = QLabel(
            "Edit the prompt above to customize how the LLM formats the extracted text. "
            "The raw PDF text will be appended to this prompt. "
            "Click 'Re-convert with New Prompt' to apply changes."
        )
        help_text.setWordWrap(True)
        help_text.setStyleSheet("color: #666; padding: 10px;")
        layout.addWidget(help_text)

        return tab

    def _create_top_bar(self) -> QHBoxLayout:
        """
        Create top bar with file picker and model selector.

        Returns:
            QHBoxLayout containing the top bar widgets.
        """
        layout = QHBoxLayout()

        # File picker button
        select_btn = QPushButton("Select PDF File")
        select_btn.clicked.connect(self._select_pdf)
        select_btn.setStyleSheet(BUTTON_STYLE)
        layout.addWidget(select_btn)

        # File info label
        self.info_label = QLabel("No file selected")
        self.info_label.setStyleSheet(INFO_LABEL_STYLE)
        layout.addWidget(self.info_label)

        layout.addStretch()

        # Model selection
        model_label = QLabel("Model:")
        model_label.setStyleSheet("padding: 5px;")
        layout.addWidget(model_label)

        self.model_combo = QComboBox()
        self.model_combo.setStyleSheet(COMBOBOX_STYLE)
        self.model_combo.setMinimumWidth(250)
        layout.addWidget(self.model_combo)

        # Refresh models button
        refresh_btn = QPushButton("↻")
        refresh_btn.setToolTip("Refresh model list")
        refresh_btn.setFixedWidth(30)
        refresh_btn.clicked.connect(self._refresh_models)
        layout.addWidget(refresh_btn)

        return layout

    def _create_pdf_viewer(self) -> QWidget:
        """
        Create PDF viewer widget.

        Returns:
            QWidget containing the PDF viewer.
        """
        container = QWidget()
        layout = QVBoxLayout(container)

        # Title
        title = QLabel("PDF Document")
        title.setStyleSheet(TITLE_STYLE)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # PDF view
        self.pdf_view = QPdfView()
        self.pdf_view.setDocument(self.pdf_document)
        self.pdf_view.setPageMode(QPdfView.PageMode.MultiPage)
        layout.addWidget(self.pdf_view)

        return container

    def _create_markdown_viewer(self) -> QWidget:
        """
        Create markdown display widget.

        Returns:
            QWidget containing the markdown viewer.
        """
        container = QWidget()
        layout = QVBoxLayout(container)

        # Title
        title = QLabel("Formatted Markdown")
        title.setStyleSheet(TITLE_STYLE)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Text edit for markdown
        self.markdown_text = QTextEdit()
        self.markdown_text.setReadOnly(True)
        self.markdown_text.setFont(QFont("Courier", 10))
        self.markdown_text.setPlaceholderText(
            "Formatted markdown will appear here after selecting a PDF...\n\n"
            "1. Select a PDF file\n"
            "2. PyMuPDF extracts the raw text\n"
            "3. LLM reformats it into proper Markdown"
        )
        layout.addWidget(self.markdown_text)

        return container

    def _create_status_bar(self) -> QFrame:
        """
        Create status bar with progress indicator.

        Returns:
            QFrame containing the status bar.
        """
        frame = QFrame()
        frame.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        layout = QHBoxLayout(frame)

        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet(STATUS_STYLE)
        layout.addWidget(self.status_label)

        layout.addStretch()

        # Progress bar (hidden by default)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.progress_bar.setMaximumWidth(200)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        return frame

    def _refresh_models(self) -> None:
        """Refresh the list of available Ollama models."""
        try:
            client = ollama.Client(host=OLLAMA_HOST)
            models = client.list()
            available_models = [model.model for model in models.models]

            self.model_combo.clear()
            self.model_combo.addItems(sorted(available_models))

            # Select default model if available
            default_index = self.model_combo.findText(DEFAULT_MODEL)
            if default_index >= 0:
                self.model_combo.setCurrentIndex(default_index)
            elif self.model_combo.count() > 0:
                self.model_combo.setCurrentIndex(0)

            logger.info(f"Found {len(available_models)} models")

        except Exception as e:
            logger.error(f"Failed to get models: {e}")
            QMessageBox.warning(
                self,
                "Ollama Connection",
                f"Could not connect to Ollama server.\n\n{e}"
            )

    def _select_pdf(self) -> None:
        """Open file dialog to select PDF."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select PDF File",
            str(Path.home()),
            "PDF Files (*.pdf)"
        )

        if file_path:
            self._load_pdf(file_path)

    def _is_processing(self) -> bool:
        """
        Check if an LLM conversion is currently in progress.

        Returns:
            True if a worker thread is running, False otherwise.
        """
        return self.llm_worker is not None and self.llm_worker.isRunning()

    def _load_pdf(self, file_path: str) -> None:
        """
        Load and process PDF file.

        Args:
            file_path: Path to PDF file.
        """
        # Validate file path
        pdf_path = Path(file_path)
        if not pdf_path.exists():
            logger.error(f"PDF file not found: {file_path}")
            QMessageBox.critical(
                self,
                "File Not Found",
                f"The selected file does not exist:\n{file_path}"
            )
            return

        if not pdf_path.is_file():
            logger.error(f"Path is not a file: {file_path}")
            QMessageBox.critical(
                self,
                "Invalid File",
                f"The selected path is not a file:\n{file_path}"
            )
            return

        if pdf_path.suffix.lower() != '.pdf':
            logger.warning(f"File may not be a PDF: {file_path}")

        try:
            # Update info label
            file_name = pdf_path.name
            self.info_label.setText(f"Loading: {file_name}")
            self.status_label.setText("Extracting text with PyMuPDF...")
            QApplication.processEvents()

            # Load PDF for viewing
            self.pdf_document.load(file_path)
            self.current_pdf_path = file_path

            # Extract text with PyMuPDF
            self.raw_extracted_text = extract_text_with_pymupdf(file_path)

            # Show raw text initially
            char_count = len(self.raw_extracted_text)
            token_estimate = estimate_tokens(self.raw_extracted_text)
            self.markdown_text.setPlainText(
                f"=== Raw Extracted Text ===\n"
                f"(Characters: {char_count:,} | Estimated tokens: {token_estimate:,})\n\n"
                f"{self.raw_extracted_text}"
            )

            # Update info
            self.info_label.setText(f"Loaded: {file_name}")
            self.status_label.setText("Raw text extracted. Starting LLM conversion...")

            # Enable reconvert button
            self.reconvert_button.setEnabled(True)

            # Start LLM conversion
            self._start_llm_conversion()

        except Exception as e:
            logger.error(f"Failed to load PDF: {e}")
            QMessageBox.critical(
                self,
                "Error Loading PDF",
                f"Failed to load PDF:\n{str(e)}"
            )
            self.info_label.setText("Error loading PDF")
            self.status_label.setText("Error")

    def _stop_current_worker(self) -> None:
        """Stop the currently running LLM worker thread if any."""
        if self.llm_worker and self.llm_worker.isRunning():
            logger.info("Stopping current LLM worker")
            self.llm_worker.terminate()
            self.llm_worker.wait()
            self.llm_worker = None

    def _start_llm_conversion(self) -> None:
        """Start the LLM conversion process."""
        if not self.raw_extracted_text:
            logger.warning("No text to convert")
            return

        model = self.model_combo.currentText()
        if not model:
            QMessageBox.warning(self, "No Model", "Please select an Ollama model.")
            return

        prompt = self.prompt_editor.toPlainText()
        if not prompt.strip():
            QMessageBox.warning(self, "Empty Prompt", "Please enter a formatting prompt.")
            return

        # Stop any existing worker before starting a new one
        self._stop_current_worker()

        # Show progress
        self.progress_bar.show()
        self.status_label.setText("LLM converting...")
        logger.info(f"Starting LLM conversion with model: {model}")

        # Create and start worker thread
        self.llm_worker = LLMWorker(
            text=self.raw_extracted_text,
            prompt=prompt,
            model=model
        )
        self.llm_worker.finished.connect(self._on_llm_finished)
        self.llm_worker.error.connect(self._on_llm_error)
        self.llm_worker.progress.connect(self._on_llm_progress)
        self.llm_worker.start()

    def _on_llm_progress(self, message: str) -> None:
        """
        Handle LLM progress update.

        Args:
            message: Progress message.
        """
        self.status_label.setText(message)

    def _on_llm_finished(self, result: str) -> None:
        """
        Handle successful LLM conversion.

        Args:
            result: Formatted markdown text.
        """
        self.progress_bar.hide()
        self.status_label.setText("Conversion complete")

        # Display formatted markdown
        self.markdown_text.setMarkdown(result)

        logger.info("LLM conversion completed successfully")

    def _on_llm_error(self, error_message: str) -> None:
        """
        Handle LLM conversion error.

        Args:
            error_message: Error description.
        """
        self.progress_bar.hide()
        self.status_label.setText(f"Error: {error_message}")

        logger.error(f"LLM conversion failed: {error_message}")
        QMessageBox.warning(
            self,
            "LLM Error",
            f"Failed to convert text:\n\n{error_message}"
        )

    def _reset_prompt(self) -> None:
        """Reset the prompt to default."""
        self.prompt_editor.setPlainText(DEFAULT_PROMPT)

    def _reconvert(self) -> None:
        """Re-run LLM conversion with current prompt."""
        if not self.raw_extracted_text:
            QMessageBox.warning(self, "No Text", "Please load a PDF first.")
            return

        self._start_llm_conversion()

    def closeEvent(self, event: QCloseEvent) -> None:
        """
        Handle window close event.

        Ensures any running LLM worker thread is properly terminated
        before the application closes.

        Args:
            event: The close event from Qt.
        """
        self._stop_current_worker()
        event.accept()


def main() -> None:
    """Main entry point for the application."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    app = QApplication(sys.argv)

    # Set application style
    app.setStyle("Fusion")

    # Create and show main window
    window = LLMPDFLabWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
