"""
Document Interrogation Tab Widget for BMLibrarian Qt GUI.

Interactive split-pane interface with document viewer (PDF/Markdown) and
AI chat interface for asking questions about documents using
DocumentInterrogationAgent with sliding window chunk processing.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QSplitter, QFileDialog, QMessageBox, QComboBox,
    QScrollArea, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QThread, Slot
from PySide6.QtGui import QFont, QTextCursor
from typing import Optional, List
from pathlib import Path

from bmlibrarian.agents import DocumentInterrogationAgent, ProcessingMode
from bmlibrarian.config import get_config
from ...widgets.pdf_viewer import PDFViewerWidget
from ...widgets.markdown_viewer import MarkdownViewer
from ...resources.styles import get_font_scale, StylesheetGenerator


class DocumentProcessingWorker(QThread):
    """Worker thread for document interrogation to prevent UI blocking."""

    result_ready = Signal(str)  # Final answer
    error_occurred = Signal(str)  # Error message
    progress_update = Signal(str)  # Progress messages

    def __init__(
        self,
        agent: DocumentInterrogationAgent,
        question: str,
        document_text: str,
        mode: ProcessingMode,
        max_sections: int
    ):
        """
        Initialize worker thread.

        Args:
            agent: DocumentInterrogationAgent instance
            question: User's question
            document_text: Full document text
            mode: Processing mode (SEQUENTIAL, EMBEDDING, HYBRID)
            max_sections: Maximum number of relevant sections
        """
        super().__init__()
        self.agent = agent
        self.question = question
        self.document_text = document_text
        self.mode = mode
        self.max_sections = max_sections

    def run(self):
        """Execute document interrogation in background thread."""
        try:
            # Process document with agent
            result = self.agent.process_document(
                question=self.question,
                document_text=self.document_text,
                mode=self.mode,
                max_sections=self.max_sections
            )

            # Format response
            response_parts = [result.answer]

            # Add metadata if available
            if result.metadata:
                chunk_info = result.metadata.get('chunk_info', {})
                num_chunks = chunk_info.get('num_chunks', 0)
                if num_chunks > 1:
                    response_parts.append(
                        f"\n\n---\n*Processed {num_chunks} chunks. "
                        f"Found {len(result.relevant_sections)} relevant sections. "
                        f"Confidence: {result.confidence:.2f}*"
                    )

            # Emit result
            self.result_ready.emit('\n'.join(response_parts))

        except Exception as e:
            self.error_occurred.emit(str(e))


class ChatBubble(QFrame):
    """A single chat message bubble with DPI-aware dimensions."""

    def __init__(self, text: str, is_user: bool, scale: dict, parent: Optional[QWidget] = None):
        """
        Initialize chat bubble.

        Args:
            text: Message text
            is_user: True if user message, False if AI message
            scale: Font-relative scaling dimensions from get_font_scale()
            parent: Optional parent widget
        """
        super().__init__(parent)

        # Get scaled dimensions
        radius = scale['bubble_radius']
        padding = scale['bubble_padding']

        # Allow bubble to expand horizontally based on content
        # Set size policy to expand with content
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        # Styling with proper colors and rounded corners
        if is_user:
            # User: pale sand background
            self.setStyleSheet(f"""
                QFrame {{
                    background-color: #F4EAD5;
                    border-radius: {radius}px;
                    padding: {padding}px;
                }}
                QLabel {{
                    color: #333333;
                    background-color: transparent;
                }}
            """)
        else:
            # LLM: pale blue background
            self.setStyleSheet(f"""
                QFrame {{
                    background-color: #E3F2FD;
                    border-radius: {radius}px;
                    padding: {padding}px;
                }}
                QLabel {{
                    color: #1A1A1A;
                    background-color: transparent;
                }}
            """)

        # Simple layout with just the message (no icon, no header)
        layout = QVBoxLayout(self)
        # Increased padding for more comfortable spacing around text
        layout.setContentsMargins(
            scale['padding_large'],
            scale['padding_medium'],
            scale['padding_large'],
            scale['padding_medium']
        )
        layout.setSpacing(0)

        # Message text only
        message_label = QLabel(text)
        message_label.setWordWrap(True)
        message_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        message_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        message_font = QFont()
        # Use larger font size for better readability
        message_font.setPointSize(scale['font_large'])
        message_label.setFont(message_font)
        layout.addWidget(message_label)


class DocumentInterrogationTabWidget(QWidget):
    """Main Document Interrogation tab widget."""

    status_message = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize Document Interrogation tab.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)

        self.config = get_config()
        self.current_document_path: Optional[str] = None
        self.current_document_text: Optional[str] = None
        self.interrogation_agent: Optional[DocumentInterrogationAgent] = None
        self.worker: Optional[DocumentProcessingWorker] = None

        # Get DPI-aware font-relative scaling dimensions
        self.scale = get_font_scale()

        # UI Components
        self.load_doc_btn: Optional[QPushButton] = None
        self.current_doc_label: Optional[QLabel] = None
        self.model_combo: Optional[QComboBox] = None
        self.refresh_models_btn: Optional[QPushButton] = None
        self.pdf_viewer: Optional[PDFViewerWidget] = None
        self.markdown_viewer: Optional[MarkdownViewer] = None
        self.document_container: Optional[QWidget] = None
        self.chat_scroll_area: Optional[QScrollArea] = None
        self.chat_container: Optional[QWidget] = None
        self.chat_layout: Optional[QVBoxLayout] = None
        self.message_input: Optional[QTextEdit] = None
        self.send_btn: Optional[QPushButton] = None
        self.progress_label: Optional[QLabel] = None

        self._setup_ui()
        self._load_models()

    def _setup_ui(self):
        """Setup the user interface."""
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Top bar
        top_bar = self._create_top_bar()
        main_layout.addWidget(top_bar)

        # Split pane
        splitter = self._create_split_pane()
        main_layout.addWidget(splitter)

    def _create_top_bar(self) -> QWidget:
        """Create top bar with file selector and model dropdown."""
        s = self.scale  # Shorthand for scale dict

        widget = QWidget()
        widget.setStyleSheet("""
            QWidget {
                background-color: #F5F5F5;
                border-bottom: 1px solid #D0D0D0;
            }
        """)
        # Height based on control height + padding
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
        self.load_doc_btn = QPushButton("📄 Load Document")
        self.load_doc_btn.clicked.connect(self._on_load_document)
        self.load_doc_btn.setFixedHeight(s['control_height_medium'])
        self.load_doc_btn.setStyleSheet(f"""
            QPushButton {{
                padding: {s['padding_tiny']}px {s['padding_medium']}px;
                font-size: {s['font_small']}pt;
            }}
        """)
        layout.addWidget(self.load_doc_btn)

        # Current document label
        self.current_doc_label = QLabel("No document loaded")
        self.current_doc_label.setStyleSheet(f"""
            QLabel {{
                color: #666;
                font-style: italic;
                font-size: {s['font_small']}pt;
            }}
        """)
        layout.addWidget(self.current_doc_label, 1)

        # Model selection
        model_label = QLabel("Model:")
        model_label.setStyleSheet(f"font-size: {s['font_small']}pt;")
        layout.addWidget(model_label)
        self.model_combo = QComboBox()
        combo_width = max(180, int(s['char_width'] * 25))
        self.model_combo.setMinimumWidth(combo_width)
        self.model_combo.setFixedHeight(s['control_height_medium'])
        self.model_combo.setStyleSheet(f"font-size: {s['font_small']}pt;")
        self.model_combo.currentTextChanged.connect(self._on_model_changed)
        layout.addWidget(self.model_combo)

        # Refresh models button
        self.refresh_models_btn = QPushButton("🔄")
        self.refresh_models_btn.setToolTip("Refresh model list")
        self.refresh_models_btn.clicked.connect(self._load_models)
        self.refresh_models_btn.setFixedSize(
            s['control_height_medium'],
            s['control_height_medium']
        )
        layout.addWidget(self.refresh_models_btn)

        return widget

    def _create_split_pane(self) -> QSplitter:
        """Create split pane with document viewer and chat interface."""
        splitter = QSplitter(Qt.Horizontal)

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

        # Header with minimal padding
        header = QLabel("📖 Document Viewer")
        header.setStyleSheet(f"""
            QLabel {{
                background-color: #E0E0E0;
                padding: {s['padding_small']}px {s['padding_medium']}px;
                font-weight: bold;
                font-size: {s['font_large']}pt;
            }}
        """)
        layout.addWidget(header)

        # Document container (will hold PDF viewer or markdown viewer)
        # Minimal padding to maximize PDF viewing area
        self.document_container = QWidget()
        self.document_container.setStyleSheet(f"""
            QWidget {{
                background-color: #FFFFFF;
                padding: {s['padding_tiny']}px;
            }}
        """)
        container_layout = QVBoxLayout(self.document_container)
        container_layout.setContentsMargins(
            s['padding_tiny'],
            s['padding_tiny'],
            s['padding_tiny'],
            s['padding_tiny']
        )
        container_layout.setSpacing(0)

        # Initial empty state
        empty_state = self._create_empty_document_state()
        container_layout.addWidget(empty_state)

        layout.addWidget(self.document_container)

        return widget

    def _create_empty_document_state(self) -> QWidget:
        """Create empty state widget for document viewer."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignCenter)

        icon_label = QLabel("📄")
        icon_label.setStyleSheet("font-size: 72pt;")
        icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_label)

        text_label = QLabel("No document loaded")
        text_label.setStyleSheet("font-size: 14pt; color: #666;")
        text_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(text_label)

        hint_label = QLabel("Click 'Load Document' to open a PDF or Markdown file")
        hint_label.setStyleSheet("font-size: 10pt; color: #999;")
        hint_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint_label)

        return widget

    def _create_chat_pane(self) -> QWidget:
        """Create chat interface pane."""
        s = self.scale

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header with minimal padding
        header = QLabel("💬 Chat")
        header.setStyleSheet(f"""
            QLabel {{
                background-color: #E0E0E0;
                padding: {s['padding_small']}px {s['padding_medium']}px;
                font-weight: bold;
                font-size: {s['font_large']}pt;
            }}
        """)
        layout.addWidget(header)

        # Chat messages area - expands to fill available vertical space
        self.chat_scroll_area = QScrollArea()
        self.chat_scroll_area.setWidgetResizable(True)
        self.chat_scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #FAFAFA;
            }
        """)

        # Chat container with reduced padding
        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(
            s['spacing_medium'],
            s['spacing_medium'],
            s['spacing_medium'],
            s['spacing_medium']
        )
        self.chat_layout.setSpacing(s['spacing_medium'])
        self.chat_layout.setAlignment(Qt.AlignTop)

        # Welcome message
        self._add_welcome_message()

        self.chat_scroll_area.setWidget(self.chat_container)
        layout.addWidget(self.chat_scroll_area, 1)  # Stretch factor 1 to expand

        # Progress label
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

        # Input area - fixed height, expands horizontally
        input_widget = self._create_input_area()
        layout.addWidget(input_widget)

        return widget

    def _create_input_area(self) -> QWidget:
        """Create message input area - fixed height, expands horizontally."""
        s = self.scale

        widget = QWidget()
        widget.setStyleSheet("""
            QWidget {
                background-color: white;
                border-top: 1px solid #CCC;
            }
        """)
        # Fixed height for input area - relative to control height
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

        # Message input - expands horizontally, fixed height
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
        layout.addWidget(self.message_input, 1)  # Stretch factor 1 to expand horizontally

        # Send button - fixed width and height
        self.send_btn = QPushButton("▶ Send")
        self.send_btn.clicked.connect(self._on_send_message)
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

    def _add_welcome_message(self):
        """Add welcome message to chat."""
        welcome_text = (
            "👋 Welcome to Document Interrogation!\n\n"
            "Load a document and select an LLM model to get started. "
            "I'll help you analyze and answer questions about your document."
        )
        self._add_chat_bubble(welcome_text, is_user=False)

    def _add_chat_bubble(self, text: str, is_user: bool):
        """Add a chat bubble to the chat area with icon on the left."""
        s = self.scale

        # Create the bubble
        bubble = ChatBubble(text, is_user, s)

        # Create small icon - always on the left side of the bubble
        icon_label = QLabel("👤" if is_user else "🤖")
        icon_label.setStyleSheet(f"""
            QLabel {{
                font-size: {s['font_icon']}pt;
                background-color: transparent;
            }}
        """)
        icon_label.setAlignment(Qt.AlignTop)
        # Small fixed size for icon
        icon_size = s['icon_small']
        icon_label.setFixedSize(icon_size, icon_size)

        # Create container for icon + bubble with asymmetric padding
        container = QWidget()
        container.setStyleSheet("background-color: transparent;")
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        container_layout = QHBoxLayout(container)
        container_layout.setSpacing(s['spacing_small'])

        if is_user:
            # User messages: left-aligned
            # Minor left padding, more right padding
            container_layout.setContentsMargins(
                s['bubble_margin_small'],
                0,
                s['bubble_margin_large'],
                0
            )
            # Layout: [icon] [bubble with expansion]
            # Icon is fixed size, bubble takes all remaining space
            container_layout.addWidget(icon_label, 0)
            container_layout.addWidget(bubble, 1)  # Stretch factor 1 to take remaining space
        else:
            # LLM messages: right-aligned
            # More left padding, minor right padding
            container_layout.setContentsMargins(
                s['bubble_margin_large'],
                0,
                s['bubble_margin_small'],
                0
            )
            # Layout: [icon] [bubble with expansion]
            # Icon is fixed size, bubble takes all remaining space
            container_layout.addWidget(icon_label, 0)
            container_layout.addWidget(bubble, 1)  # Stretch factor 1 to take remaining space

        self.chat_layout.addWidget(container)

        # Auto-scroll to bottom
        QTimer.singleShot(s['spacing_medium'] * 10, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        """Scroll chat area to bottom."""
        scrollbar = self.chat_scroll_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _load_models(self):
        """Load available Ollama models."""
        try:
            import ollama

            # Get Ollama config
            ollama_config = self.config.get_ollama_config()
            host = ollama_config.get('host', 'http://localhost:11434')

            # Create client and fetch models
            client = ollama.Client(host=host)
            models_response = client.list()
            models = [model.model for model in models_response.models]

            # Update combo box
            current = self.model_combo.currentText()
            self.model_combo.clear()
            self.model_combo.addItems(models)

            # Restore selection or use default
            if current and current in models:
                self.model_combo.setCurrentText(current)
            elif models:
                # Try to use configured model
                default_model = self.config.get_model('document_interrogation_agent')
                if default_model and default_model in models:
                    self.model_combo.setCurrentText(default_model)
                else:
                    self.model_combo.setCurrentIndex(0)

            self.status_message.emit(f"Loaded {len(models)} models from Ollama")

        except Exception as e:
            QMessageBox.warning(self, "Model Load Error", f"Failed to load models: {str(e)}")

    def _on_model_changed(self, model: str):
        """Handle model selection change."""
        if model:
            self._add_chat_bubble(f"🤖 Model changed to: {model}", is_user=False)
            # Reinitialize agent with new model
            self.interrogation_agent = None

    @Slot()
    def _on_load_document(self):
        """Handle load document button click."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Document",
            "",
            "Documents (*.pdf *.md *.txt);;PDF Files (*.pdf);;Markdown Files (*.md);;Text Files (*.txt)"
        )

        if file_path:
            self._load_document(file_path)

    def _load_document(self, file_path: str):
        """Load a document for viewing and interrogation."""
        try:
            path = Path(file_path)

            # Validate file
            if not path.exists():
                raise FileNotFoundError(f"File not found: {file_path}")

            if not path.is_file():
                raise ValueError(f"Path is not a file: {file_path}")

            # Check file size (100MB limit)
            max_size = 100 * 1024 * 1024
            if path.stat().st_size > max_size:
                raise ValueError(f"File too large. Maximum size is 100MB.")

            self.current_document_path = file_path

            # Update label
            self.current_doc_label.setText(f"📄 {path.name}")
            self.current_doc_label.setStyleSheet(f"""
                QLabel {{
                    color: #000;
                    font-weight: bold;
                    font-size: {self.scale['font_small']}pt;
                }}
            """)

            # Clear existing document viewer
            while self.document_container.layout().count():
                child = self.document_container.layout().takeAt(0)
                if child.widget():
                    child.widget().deleteLater()

            # Load based on file type
            if path.suffix.lower() == '.pdf':
                self._load_pdf(file_path)
            elif path.suffix.lower() in ['.md', '.txt']:
                self._load_text_document(file_path)
            else:
                raise ValueError(f"Unsupported file type: {path.suffix}")

            # Add confirmation to chat
            self._add_chat_bubble(
                f"✅ Document loaded: {path.name}\n\nYou can now ask questions about this document.",
                is_user=False
            )

            self.status_message.emit(f"Loaded document: {path.name}")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load document:\n{str(e)}")

    def _load_pdf(self, file_path: str):
        """Load and display PDF document."""
        try:
            # Create PDF viewer
            self.pdf_viewer = PDFViewerWidget()
            self.pdf_viewer.load_pdf(file_path)

            # Add to container
            self.document_container.layout().addWidget(self.pdf_viewer)

            # Extract text for LLM processing
            self.current_document_text = self.pdf_viewer.get_all_text()

        except Exception as e:
            raise Exception(f"PDF loading error: {str(e)}")

    def _load_text_document(self, file_path: str):
        """Load and display text/markdown document."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            self.current_document_text = content

            if Path(file_path).suffix.lower() == '.md':
                # Use markdown viewer
                self.markdown_viewer = MarkdownViewer()
                self.markdown_viewer.set_markdown(content)
                self.document_container.layout().addWidget(self.markdown_viewer)
            else:
                # Use plain text viewer
                text_viewer = QTextEdit()
                text_viewer.setReadOnly(True)
                text_viewer.setPlainText(content)
                self.document_container.layout().addWidget(text_viewer)

        except Exception as e:
            raise Exception(f"Text loading error: {str(e)}")

    @Slot()
    def _on_send_message(self):
        """Handle send message button click."""
        message = self.message_input.toPlainText().strip()

        if not message:
            return

        # Validation
        if not self.current_document_path:
            QMessageBox.warning(self, "No Document", "Please load a document first.")
            return

        if not self.model_combo.currentText():
            QMessageBox.warning(self, "No Model", "Please select an LLM model first.")
            return

        # Add user message
        self._add_chat_bubble(message, is_user=True)

        # Clear input
        self.message_input.clear()

        # Show processing indicator
        self._show_processing()

        # Initialize agent if needed
        if not self.interrogation_agent:
            self._init_agent()

        # Start processing in worker thread
        self._start_processing(message)

    def _init_agent(self):
        """Initialize DocumentInterrogationAgent."""
        try:
            # Get configuration
            ollama_config = self.config.get_ollama_config()
            host = ollama_config.get('host', 'http://localhost:11434')

            doc_interrogation_config = self.config.get_agent_config('document_interrogation')
            chunk_size = doc_interrogation_config.get('chunk_size', 10000)
            chunk_overlap = doc_interrogation_config.get('chunk_overlap', 250)
            temperature = doc_interrogation_config.get('temperature', 0.1)
            top_p = doc_interrogation_config.get('top_p', 0.9)
            embedding_threshold = doc_interrogation_config.get('embedding_threshold', 0.5)

            # Get models
            main_model = self.model_combo.currentText() or self.config.get_model('document_interrogation_agent')
            embedding_model = self.config.get_model('document_interrogation_embedding')

            # Create agent with progress callback
            def progress_callback(step: str, data: str):
                self.progress_label.setText(f"{step}: {data}")

            self.interrogation_agent = DocumentInterrogationAgent(
                model=main_model,
                embedding_model=embedding_model,
                host=host,
                temperature=temperature,
                top_p=top_p,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                embedding_threshold=embedding_threshold,
                callback=progress_callback,
                show_model_info=False
            )

        except Exception as e:
            QMessageBox.critical(self, "Agent Error", f"Failed to initialize agent:\n{str(e)}")

    def _start_processing(self, question: str):
        """Start document processing in worker thread."""
        try:
            # Get processing mode from config
            doc_config = self.config.get_agent_config('document_interrogation')
            mode_str = doc_config.get('processing_mode', 'sequential').lower()
            max_sections = doc_config.get('max_sections', 10)

            # Convert mode string to enum
            if mode_str == 'sequential':
                mode = ProcessingMode.SEQUENTIAL
            elif mode_str == 'embedding':
                mode = ProcessingMode.EMBEDDING
            elif mode_str == 'hybrid':
                mode = ProcessingMode.HYBRID
            else:
                mode = ProcessingMode.SEQUENTIAL

            # Create and start worker
            self.worker = DocumentProcessingWorker(
                self.interrogation_agent,
                question,
                self.current_document_text,
                mode,
                max_sections
            )

            self.worker.result_ready.connect(self._on_result_ready)
            self.worker.error_occurred.connect(self._on_error)
            self.worker.finished.connect(self._on_processing_finished)

            self.worker.start()

        except Exception as e:
            self._hide_processing()
            QMessageBox.critical(self, "Processing Error", str(e))

    @Slot(str)
    def _on_result_ready(self, answer: str):
        """Handle processing result."""
        self._add_chat_bubble(answer, is_user=False)

    @Slot(str)
    def _on_error(self, error: str):
        """Handle processing error."""
        self._add_chat_bubble(f"❌ Error: {error}", is_user=False)

    @Slot()
    def _on_processing_finished(self):
        """Handle processing completion."""
        self._hide_processing()

    def _show_processing(self):
        """Show processing indicator."""
        self.progress_label.setText("🤔 Analyzing document...")
        self.progress_label.setVisible(True)
        self.send_btn.setEnabled(False)

    def _hide_processing(self):
        """Hide processing indicator."""
        self.progress_label.setVisible(False)
        self.send_btn.setEnabled(True)

    def cleanup(self):
        """Cleanup resources."""
        if self.worker and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait()


# Import QTimer for scroll delay
from PySide6.QtCore import QTimer
