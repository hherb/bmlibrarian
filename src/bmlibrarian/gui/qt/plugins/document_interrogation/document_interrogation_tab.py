"""
Document Interrogation Tab Widget for BMLibrarian Qt GUI.

Interactive split-pane interface with document viewer (PDF/Markdown) and
AI chat interface for asking questions about documents using
DocumentInterrogationAgent with sliding window chunk processing.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QSplitter, QFileDialog, QMessageBox, QComboBox,
    QScrollArea, QFrame, QSizePolicy, QTextBrowser, QMenu, QSpinBox
)
from PySide6.QtCore import Qt, Signal, QThread, Slot
from typing import Optional, List
from pathlib import Path
from datetime import datetime
import json
import markdown

from bmlibrarian.agents import DocumentInterrogationAgent, ProcessingMode
from bmlibrarian.config import get_config
from ...widgets.pdf_viewer import PDFViewerWidget
from ...widgets.markdown_viewer import MarkdownViewer
from ...resources.styles import get_font_scale, StylesheetGenerator
from ...core.document_receiver import IDocumentReceiver
from ...core.document_processor import (
    DocumentProcessor,
    ProcessingStage,
    ContentSource,
)


class DocumentProcessingWorker(QThread):
    """Worker thread for document interrogation to prevent UI blocking."""

    result_ready = Signal(str)  # Final answer
    error_occurred = Signal(str)  # Error message
    progress_update = Signal(str)  # Progress messages

    def __init__(
        self,
        agent: DocumentInterrogationAgent,
        question: str,
        document_text: Optional[str] = None,
        mode: ProcessingMode = ProcessingMode.EMBEDDING,
        max_sections: int = 10,
        document_id: Optional[int] = None,
        conversation_context: Optional[str] = None
    ):
        """
        Initialize worker thread.

        Args:
            agent: DocumentInterrogationAgent instance
            question: User's question
            document_text: Full document text (for file-based documents)
            mode: Processing mode (SEQUENTIAL, EMBEDDING, HYBRID)
            max_sections: Maximum number of relevant sections
            document_id: Database document ID (for database documents, uses semantic search)
            conversation_context: Optional formatted string of previous Q&A pairs for context
        """
        super().__init__()
        self.agent = agent
        self.question = question
        self.document_text = document_text
        self.mode = mode
        self.max_sections = max_sections
        self.document_id = document_id
        self.conversation_context = conversation_context

    def run(self):
        """Execute document interrogation in background thread."""
        try:
            # Build the effective question with conversation context if provided
            if self.conversation_context:
                effective_question = (
                    f"Previous conversation context:\n{self.conversation_context}\n\n"
                    f"Current question: {self.question}"
                )
            else:
                effective_question = self.question

            # Use optimized answer_question for database documents
            if self.document_id is not None:
                result = self.agent.answer_question(
                    document_id=self.document_id,
                    question=effective_question,
                    max_chunks=self.max_sections
                )
            else:
                # Process document with agent (file-based)
                result = self.agent.process_document(
                    question=effective_question,
                    document_text=self.document_text,
                    mode=self.mode,
                    max_sections=self.max_sections
                )

            # Format response
            response_parts = [result.answer]

            # Add debug information about chunks used
            if result.relevant_sections:
                debug_info = []
                debug_info.append(f"\n\n---\n**Debug Info:**")
                debug_info.append(
                    f"- Processing mode: {result.processing_mode.value}"
                )
                debug_info.append(
                    f"- Chunks processed: {result.chunks_processed}/{result.chunks_total}"
                )
                debug_info.append(
                    f"- Relevant sections found: {len(result.relevant_sections)}"
                )
                debug_info.append(f"- Confidence: {result.confidence:.2f}")

                # Show chunk scores
                if result.relevant_sections:
                    scores = [
                        f"chunk {s.chunk_index}: {s.relevance_score:.3f}"
                        for s in result.relevant_sections[:5]  # Show top 5
                    ]
                    debug_info.append(f"- Top chunk scores: {', '.join(scores)}")

                # Show metadata source if available
                if result.metadata:
                    source = result.metadata.get('source', 'unknown')
                    debug_info.append(f"- Source: {source}")
                    if result.metadata.get('reasoning'):
                        debug_info.append(
                            f"- Reasoning: {result.metadata['reasoning'][:200]}..."
                        )

                response_parts.append('\n'.join(debug_info))
            else:
                # No sections found - provide debug feedback
                response_parts.append(
                    f"\n\n---\n**Debug Info:**\n"
                    f"- No relevant sections found above threshold.\n"
                    f"- Processing mode: {result.processing_mode.value}\n"
                    f"- Chunks total: {result.chunks_total}\n"
                    f"- Try lowering the similarity threshold in config, "
                    f"or check if the document has been properly embedded."
                )

            # Emit result
            self.result_ready.emit('\n'.join(response_parts))

        except Exception as e:
            import traceback
            error_msg = f"{str(e)}\n\nTraceback:\n{traceback.format_exc()}"
            self.error_occurred.emit(error_msg)


class DocumentPreparationWorker(QThread):
    """Worker thread for document preparation (embedding creation) to prevent UI blocking."""

    progress_update = Signal(str, str, int, int)  # stage, message, current, total
    preparation_complete = Signal(object)  # DocumentProcessingResult
    preparation_error = Signal(str)

    def __init__(
        self,
        document_id: int,
        parent: Optional[QThread] = None,
    ):
        """
        Initialize worker thread.

        Args:
            document_id: Database document ID to prepare
            parent: Parent object
        """
        super().__init__(parent)
        self.document_id = document_id
        self._processor: Optional[DocumentProcessor] = None

    def run(self):
        """Execute document preparation in background thread."""
        try:
            self._processor = DocumentProcessor()

            def progress_callback(
                stage: ProcessingStage,
                message: str,
                current: int,
                total: int,
            ) -> None:
                self.progress_update.emit(stage.value, message, current, total)

            result = self._processor.process_document(
                document_id=self.document_id,
                progress_callback=progress_callback,
                prompt_callback=None,  # No user prompts in background thread
                skip_pdf_search=False,
            )

            self.preparation_complete.emit(result)

        except Exception as e:
            self.preparation_error.emit(str(e))


class ChatBubble(QFrame):
    """A single chat message bubble with DPI-aware dimensions and markdown support."""

    def __init__(self, text: str, is_user: bool, scale: dict, parent: Optional[QWidget] = None):
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

        # Get scaled dimensions - double the padding and use larger radius
        # Doubled padding for more comfortable spacing
        radius = max(20, int(scale['bubble_radius'] * 1.8))  # Much more rounded corners

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

        # Layout with original padding (not doubled)
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
                    font-family: 'Segoe UI', Arial, sans-serif;
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

    def _adjust_browser_height(self):
        """Adjust the QTextBrowser height to fit its content."""
        if hasattr(self, '_message_browser') and self._message_browser:
            doc_height = self._message_browser.document().size().height()
            # Add small margin to prevent clipping
            self._message_browser.setFixedHeight(int(doc_height) + 8)


class DocumentInterrogationTabWidget(QWidget, IDocumentReceiver):
    """Main Document Interrogation tab widget with document receiver capability."""

    status_message = Signal(str)

    # IDocumentReceiver identifier
    RECEIVER_ID = "document_interrogation"

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
        self.current_document_id: Optional[int] = None  # Database document ID
        self.interrogation_agent: Optional[DocumentInterrogationAgent] = None
        self.worker: Optional[DocumentProcessingWorker] = None
        self.preparation_worker: Optional[DocumentPreparationWorker] = None

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
        self.save_btn: Optional[QPushButton] = None
        self.history_spinbox: Optional[QSpinBox] = None
        self.progress_label: Optional[QLabel] = None

        # Conversation history for export
        self.conversation_history: List[dict] = []

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
        header_label = QLabel("💬 Chat")
        header_label.setStyleSheet(f"""
            QLabel {{
                font-weight: bold;
                font-size: {s['font_large']}pt;
                background-color: transparent;
            }}
        """)
        header_layout.addWidget(header_label)

        # Spacer to push controls to the right
        header_layout.addStretch()

        # History context control - how many previous Q&A pairs to include
        history_label = QLabel("Remember:")
        history_label.setStyleSheet(f"""
            QLabel {{
                font-size: {s['font_small']}pt;
                background-color: transparent;
            }}
        """)
        header_layout.addWidget(history_label)

        self.history_spinbox = QSpinBox()
        self.history_spinbox.setRange(0, 10)
        self.history_spinbox.setValue(0)  # Default: no history context
        self.history_spinbox.setSuffix(" Q&A")
        self.history_spinbox.setFixedHeight(s['control_height_small'])
        self.history_spinbox.setFixedWidth(max(70, int(s['char_width'] * 10)))
        self.history_spinbox.setToolTip(
            "Number of previous Q&A pairs to include as context.\n\n"
            "• 0 = No history (each question is independent)\n"
            "• 1-3 = Good for follow-up questions\n"
            "• 4-10 = Extended context for complex discussions\n\n"
            "Trade-off: More history provides better context continuity\n"
            "but reduces space for document content in the LLM context.\n"
            "Start with 0-2 for most use cases."
        )
        self.history_spinbox.setStyleSheet(f"""
            QSpinBox {{
                font-size: {s['font_small']}pt;
                padding: {s['padding_tiny']}px;
                border: 1px solid #CCC;
                border-radius: {s['radius_small']}px;
                background-color: #FFFFFF;
            }}
            QSpinBox:focus {{
                border: 1px solid #2196F3;
            }}
        """)
        header_layout.addWidget(self.history_spinbox)

        # Small spacing before save button
        header_layout.addSpacing(s['spacing_medium'])

        # Save conversation button
        self.save_btn = QPushButton("💾 Save")
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

        # Chat messages area - expands to fill available vertical space
        self.chat_scroll_area = QScrollArea()
        self.chat_scroll_area.setWidgetResizable(True)
        self.chat_scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #FAFAFA;
            }
        """)

        # Chat container with doubled spacing between bubbles
        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(
            s['spacing_medium'],
            s['spacing_medium'],
            s['spacing_medium'],
            s['spacing_medium']
        )
        # Double the spacing between chat bubbles for better visual separation
        self.chat_layout.setSpacing(s['spacing_medium'] * 2)
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

    def _add_chat_bubble(self, text: str, is_user: bool, track_history: bool = True):
        """Add a chat bubble to the chat area with icon on the left.

        Args:
            text: Message text (supports markdown formatting)
            is_user: True if user message, False if AI message
            track_history: If True, add message to conversation history for export
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
        container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
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

    def _get_save_directory(self) -> Path:
        """Get the configured save directory for conversation exports.

        Returns:
            Path to the save directory (creates if doesn't exist)
        """
        # Get from config or use default
        doc_qa_config = self.config.get_agent_config('document_qa')
        save_dir_str = doc_qa_config.get(
            'conversation_save_dir',
            str(Path.home() / '.bmlibrarian' / 'document_qa')
        )
        save_dir = Path(save_dir_str).expanduser()

        # Create directory if it doesn't exist
        save_dir.mkdir(parents=True, exist_ok=True)
        return save_dir

    def _generate_filename_base(self) -> str:
        """Generate a base filename for conversation export.

        Returns:
            Filename base string (without extension)
        """
        # Get document name if available
        doc_name = "conversation"
        if self.current_document_path:
            doc_name = Path(self.current_document_path).stem
        elif self.current_document_id:
            doc_name = f"doc_{self.current_document_id}"

        # Add timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{doc_name}_{timestamp}"

    @Slot()
    def _on_save_conversation(self):
        """Handle save conversation button click - show format selection menu."""
        if not self.conversation_history:
            QMessageBox.information(
                self, "No Conversation",
                "No conversation to save yet. Ask some questions first!"
            )
            return

        # Show menu with format options
        menu = QMenu(self)

        json_action = menu.addAction("💾 Save as JSON")
        md_action = menu.addAction("📝 Save as Markdown")
        menu.addSeparator()
        both_action = menu.addAction("📁 Save Both Formats")

        # Show menu at button position
        if self.save_btn is None:
            return
        action = menu.exec_(self.save_btn.mapToGlobal(self.save_btn.rect().bottomLeft()))

        if action == json_action:
            self._save_conversation_json()
        elif action == md_action:
            self._save_conversation_markdown()
        elif action == both_action:
            self._save_conversation_json()
            self._save_conversation_markdown()

    def _save_conversation_json(self, custom_path: Optional[Path] = None) -> Optional[Path]:
        """Save conversation history as JSON.

        Args:
            custom_path: Optional custom file path. If None, uses default directory.

        Returns:
            Path to saved file, or None if cancelled/failed
        """
        try:
            if custom_path:
                file_path = custom_path
            else:
                # Get default save directory and filename
                save_dir = self._get_save_directory()
                default_filename = f"{self._generate_filename_base()}.json"
                default_path = save_dir / default_filename

                # Show file dialog
                file_path_str, _ = QFileDialog.getSaveFileName(
                    self,
                    "Save Conversation as JSON",
                    str(default_path),
                    "JSON Files (*.json);;All Files (*)"
                )

                if not file_path_str:
                    return None  # User cancelled
                file_path = Path(file_path_str)

            # Build export data
            export_data = {
                "metadata": {
                    "exported_at": datetime.now().isoformat(),
                    "document_path": self.current_document_path,
                    "document_id": self.current_document_id,
                    "model": self.model_combo.currentText() if self.model_combo else None,
                    "message_count": len(self.conversation_history)
                },
                "messages": self.conversation_history
            }

            # Write JSON file
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)

            self.status_message.emit(f"Conversation saved to: {file_path.name}")
            return file_path

        except Exception as e:
            QMessageBox.critical(
                self, "Save Error",
                f"Failed to save conversation as JSON:\n{str(e)}"
            )
            return None

    def _save_conversation_markdown(self, custom_path: Optional[Path] = None) -> Optional[Path]:
        """Save conversation history as Markdown.

        Args:
            custom_path: Optional custom file path. If None, uses default directory.

        Returns:
            Path to saved file, or None if cancelled/failed
        """
        try:
            if custom_path:
                file_path = custom_path
            else:
                # Get default save directory and filename
                save_dir = self._get_save_directory()
                default_filename = f"{self._generate_filename_base()}.md"
                default_path = save_dir / default_filename

                # Show file dialog
                file_path_str, _ = QFileDialog.getSaveFileName(
                    self,
                    "Save Conversation as Markdown",
                    str(default_path),
                    "Markdown Files (*.md);;All Files (*)"
                )

                if not file_path_str:
                    return None  # User cancelled
                file_path = Path(file_path_str)

            # Build markdown content
            lines = []

            # Header
            lines.append("# Document Q&A Conversation")
            lines.append("")

            # Metadata section
            lines.append("## Metadata")
            lines.append("")
            lines.append(f"- **Exported:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            if self.current_document_path:
                lines.append(f"- **Document:** {Path(self.current_document_path).name}")
            elif self.current_document_id:
                lines.append(f"- **Document ID:** {self.current_document_id}")
            if self.model_combo and self.model_combo.currentText():
                lines.append(f"- **Model:** {self.model_combo.currentText()}")
            lines.append(f"- **Messages:** {len(self.conversation_history)}")
            lines.append("")

            # Conversation section
            lines.append("## Conversation")
            lines.append("")

            for msg in self.conversation_history:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                timestamp = msg.get("timestamp", "")

                if role == "user":
                    lines.append("### 👤 User")
                else:
                    lines.append("### 🤖 Assistant")

                if timestamp:
                    # Format timestamp for display
                    try:
                        dt = datetime.fromisoformat(timestamp)
                        lines.append(f"*{dt.strftime('%H:%M:%S')}*")
                    except ValueError:
                        pass

                lines.append("")
                lines.append(content)
                lines.append("")
                lines.append("---")
                lines.append("")

            # Write markdown file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))

            self.status_message.emit(f"Conversation saved to: {file_path.name}")
            return file_path

        except Exception as e:
            QMessageBox.critical(
                self, "Save Error",
                f"Failed to save conversation as Markdown:\n{str(e)}"
            )
            return None

    def clear_conversation(self):
        """Clear the conversation history and chat display."""
        self.conversation_history.clear()

        # Clear chat layout
        if self.chat_layout is not None:
            while self.chat_layout.count():
                child = self.chat_layout.takeAt(0)
                widget = child.widget()
                if widget is not None:
                    widget.deleteLater()

        # Re-add welcome message
        self._add_welcome_message()

    def _build_conversation_context(self) -> Optional[str]:
        """
        Build conversation context string from recent history.

        Returns:
            Formatted context string with recent Q&A pairs, or None if disabled/empty.
        """
        if self.history_spinbox is None:
            return None

        history_count = self.history_spinbox.value()
        if history_count <= 0:
            return None

        if not self.conversation_history:
            return None

        # Get last N Q&A pairs (each pair = 2 messages: user + assistant)
        # We want pairs, so multiply by 2 for message count
        messages_to_include = history_count * 2
        recent_messages = self.conversation_history[-messages_to_include:]

        if not recent_messages:
            return None

        # Build context string
        context_parts = []
        for msg in recent_messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if role == "user":
                context_parts.append(f"User: {content}")
            elif role == "assistant":
                context_parts.append(f"Assistant: {content}")

        if not context_parts:
            return None

        return "\n\n".join(context_parts)

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
            self.current_document_id = None  # Clear database document ID

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

    def load_database_document(self, document_id: int, title: Optional[str] = None):
        """
        Load a document from the database for interrogation.

        Uses the DocumentProcessor to ensure embeddings exist, then displays
        the document content (PDF or full text) in the viewer pane.

        Args:
            document_id: Database ID of the document
            title: Optional document title for display
        """
        try:
            # Clear file-based document state
            self.current_document_path = None
            self.current_document_text = None

            # Set database document ID
            self.current_document_id = document_id

            # Get document info first for display
            processor = DocumentProcessor()
            doc_info = processor.get_document_info(document_id)

            display_title = title or (doc_info.title if doc_info else None) or f"Document #{document_id}"

            # Update label
            self.current_doc_label.setText(f"📄 {display_title}")
            self.current_doc_label.setStyleSheet(f"""
                QLabel {{
                    color: #000;
                    font-weight: bold;
                    font-size: {self.scale['font_small']}pt;
                }}
            """)

            # Clear existing document viewer
            self._clear_document_container()

            # Show loading placeholder initially
            loading_widget = self._create_loading_placeholder(document_id, display_title)
            self.document_container.layout().addWidget(loading_widget)

            # Add initial chat message
            self._add_chat_bubble(
                f"📥 Loading document: {display_title}\n\n"
                f"Checking for existing content and embeddings...",
                is_user=False
            )

            self.status_message.emit(f"Loading database document: {display_title}")

            # Start document preparation in background thread
            self._start_document_preparation(document_id, display_title, doc_info)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load database document:\n{str(e)}")

    def _clear_document_container(self) -> None:
        """Clear all widgets from the document container."""
        while self.document_container.layout().count():
            child = self.document_container.layout().takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _create_loading_placeholder(self, document_id: int, title: str) -> QWidget:
        """Create loading placeholder widget."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignCenter)

        icon_label = QLabel("⏳")
        icon_label.setStyleSheet("font-size: 72pt;")
        icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_label)

        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 14pt; font-weight: bold; color: #333;")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setWordWrap(True)
        layout.addWidget(title_label)

        self._loading_status_label = QLabel("Checking document...")
        self._loading_status_label.setStyleSheet("font-size: 10pt; color: #666;")
        self._loading_status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._loading_status_label)

        return widget

    def _start_document_preparation(
        self,
        document_id: int,
        title: str,
        doc_info: Optional['DocumentInfo'] = None,
    ) -> None:
        """
        Start document preparation in background thread.

        Args:
            document_id: Document ID
            title: Document title for display
            doc_info: Optional pre-fetched document info
        """
        # Stop any existing worker
        if self.preparation_worker and self.preparation_worker.isRunning():
            self.preparation_worker.quit()
            self.preparation_worker.wait()

        # Store title for later use
        self._pending_title = title
        self._pending_doc_info = doc_info

        # Create and start worker
        self.preparation_worker = DocumentPreparationWorker(document_id, self)
        self.preparation_worker.progress_update.connect(self._on_preparation_progress)
        self.preparation_worker.preparation_complete.connect(self._on_preparation_complete)
        self.preparation_worker.preparation_error.connect(self._on_preparation_error)
        self.preparation_worker.start()

    @Slot(str, str, int, int)
    def _on_preparation_progress(
        self,
        stage: str,
        message: str,
        current: int,
        total: int,
    ) -> None:
        """Handle document preparation progress updates."""
        # Update loading status label if it exists
        if hasattr(self, '_loading_status_label') and self._loading_status_label:
            self._loading_status_label.setText(message)
        self.status_message.emit(message)

    @Slot(object)
    def _on_preparation_complete(self, result: 'DocumentProcessingResult') -> None:
        """Handle document preparation completion."""
        from bmlibrarian.gui.qt.core.document_processor import DocumentProcessingResult

        title = getattr(self, '_pending_title', f"Document #{result.document_id}")

        if result.success:
            # Clear container and show actual document content
            self._clear_document_container()

            # Load document content into viewer
            self._display_document_content(result)

            # Build success message based on content source
            source_descriptions = {
                ContentSource.EXISTING_EMBEDDINGS: "using existing embeddings",
                ContentSource.EXISTING_FULL_TEXT: "from database full text",
                ContentSource.EXISTING_PDF: "from local PDF",
                ContentSource.DOWNLOADED_PDF: "from downloaded PDF",
                ContentSource.NXML_FULL_TEXT: "from PMC NXML",
                ContentSource.ABSTRACT_ONLY: "using abstract only",
            }
            source_desc = source_descriptions.get(
                result.content_source, "from available content"
            )

            self._add_chat_bubble(
                f"✅ Document ready: {title}\n\n"
                f"Content loaded {source_desc}.\n"
                f"Chunks available: {result.chunks_created}\n\n"
                f"You can now ask questions about this document.",
                is_user=False
            )

            self.status_message.emit(f"Document ready: {title}")

        else:
            # Show error state
            self._clear_document_container()
            error_widget = self._create_error_placeholder(
                result.document_id,
                title,
                result.error_message or "Unknown error",
            )
            self.document_container.layout().addWidget(error_widget)

            self._add_chat_bubble(
                f"❌ Failed to load document: {title}\n\n"
                f"Error: {result.error_message}\n\n"
                f"Please try again or select a different document.",
                is_user=False
            )

            self.status_message.emit(f"Failed to load document: {title}")

    @Slot(str)
    def _on_preparation_error(self, error: str) -> None:
        """Handle document preparation error."""
        title = getattr(self, '_pending_title', "Unknown document")

        self._clear_document_container()
        error_widget = self._create_error_placeholder(
            self.current_document_id or 0,
            title,
            error,
        )
        self.document_container.layout().addWidget(error_widget)

        self._add_chat_bubble(
            f"❌ Error preparing document: {title}\n\n"
            f"Error: {error}\n\n"
            f"Please try again or select a different document.",
            is_user=False
        )

        self.status_message.emit(f"Error: {error}")

    def _create_error_placeholder(
        self,
        document_id: int,
        title: str,
        error: str,
    ) -> QWidget:
        """Create error placeholder widget."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignCenter)

        icon_label = QLabel("❌")
        icon_label.setStyleSheet("font-size: 72pt;")
        icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_label)

        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 14pt; font-weight: bold; color: #333;")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setWordWrap(True)
        layout.addWidget(title_label)

        error_label = QLabel(error)
        error_label.setStyleSheet("font-size: 10pt; color: #d32f2f;")
        error_label.setAlignment(Qt.AlignCenter)
        error_label.setWordWrap(True)
        layout.addWidget(error_label)

        return widget

    def _display_document_content(self, result: 'DocumentProcessingResult') -> None:
        """
        Display document content in the viewer pane.

        Checks for PDF first, then falls back to full text display.

        Args:
            result: Document processing result with content info
        """
        # Try to display PDF if available
        if result.pdf_path and result.pdf_path.exists():
            try:
                self.pdf_viewer = PDFViewerWidget()
                self.pdf_viewer.load_pdf(str(result.pdf_path))
                self.document_container.layout().addWidget(self.pdf_viewer)
                self.current_document_path = str(result.pdf_path)
                return
            except Exception as e:
                # PDF load failed, fall through to text display
                import logging
                logging.getLogger(__name__).warning(f"PDF load failed: {e}")

        # Check for PDF in database via processor
        if self.current_document_id:
            processor = DocumentProcessor()
            doc_info = processor.get_document_info(self.current_document_id)
            if doc_info:
                pdf_path = processor.get_pdf_path(doc_info)
                if pdf_path and pdf_path.exists():
                    try:
                        self.pdf_viewer = PDFViewerWidget()
                        self.pdf_viewer.load_pdf(str(pdf_path))
                        self.document_container.layout().addWidget(self.pdf_viewer)
                        self.current_document_path = str(pdf_path)
                        return
                    except Exception as e:
                        import logging
                        logging.getLogger(__name__).warning(f"PDF load failed: {e}")

        # Fall back to full text display
        if result.full_text:
            self.current_document_text = result.full_text
            self.markdown_viewer = MarkdownViewer()
            self.markdown_viewer.set_markdown(result.full_text)
            self.document_container.layout().addWidget(self.markdown_viewer)
            return

        # No content available - show placeholder
        placeholder = self._create_database_document_placeholder(
            result.document_id,
            getattr(self, '_pending_title', f"Document #{result.document_id}"),
        )
        self.document_container.layout().addWidget(placeholder)

    def _create_database_document_placeholder(
        self,
        document_id: int,
        title: str
    ) -> QWidget:
        """Create placeholder widget for database document display."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignCenter)

        icon_label = QLabel("🗄️")
        icon_label.setStyleSheet("font-size: 72pt;")
        icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_label)

        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 14pt; font-weight: bold; color: #333;")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setWordWrap(True)
        layout.addWidget(title_label)

        id_label = QLabel(f"Document ID: {document_id}")
        id_label.setStyleSheet("font-size: 10pt; color: #666;")
        id_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(id_label)

        hint_label = QLabel("Using semantic search for efficient chunk retrieval")
        hint_label.setStyleSheet("font-size: 10pt; color: #999; font-style: italic;")
        hint_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint_label)

        return widget

    @Slot()
    def _on_send_message(self):
        """Handle send message button click."""
        message = self.message_input.toPlainText().strip()

        if not message:
            return

        # Validation - require either file path or database document ID
        if not self.current_document_path and self.current_document_id is None:
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
            mode_str = doc_config.get('processing_mode', 'embedding').lower()
            max_sections = doc_config.get('max_sections', 10)

            # Convert mode string to enum
            if mode_str == 'sequential':
                mode = ProcessingMode.SEQUENTIAL
            elif mode_str == 'embedding':
                mode = ProcessingMode.EMBEDDING
            elif mode_str == 'hybrid':
                mode = ProcessingMode.HYBRID
            else:
                mode = ProcessingMode.EMBEDDING  # Default to embedding for efficiency

            # Build conversation context from history (if enabled)
            conversation_context = self._build_conversation_context()

            # Create and start worker - pass document_id for database documents
            self.worker = DocumentProcessingWorker(
                agent=self.interrogation_agent,
                question=question,
                document_text=self.current_document_text,
                mode=mode,
                max_sections=max_sections,
                document_id=self.current_document_id,
                conversation_context=conversation_context
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

    # IDocumentReceiver interface implementation

    def get_receiver_id(self) -> str:
        """Return unique identifier for this receiver."""
        return self.RECEIVER_ID

    def get_receiver_name(self) -> str:
        """Return display name for context menu."""
        return "Document Interrogation"

    def get_receiver_description(self) -> Optional[str]:
        """Return tooltip description for context menu."""
        return "Ask questions about this document using AI chat interface"

    def can_receive_document(self, document_data: dict) -> bool:
        """
        Check if this receiver can handle the document.

        Args:
            document_data: Document dictionary with document metadata

        Returns:
            True if document has an ID we can use
        """
        doc_id = document_data.get('id') or document_data.get('document_id')
        return doc_id is not None

    def receive_document(self, document_data: dict) -> bool:
        """
        Receive a document from another tab.

        Args:
            document_data: Document dictionary with at least 'id' key

        Returns:
            True if document was accepted
        """
        doc_id = document_data.get('id') or document_data.get('document_id')
        if doc_id is None:
            return False

        title = document_data.get('title')
        self.load_database_document(doc_id, title)
        return True

    def cleanup(self):
        """Cleanup resources."""
        if self.worker and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait()

        if self.preparation_worker and self.preparation_worker.isRunning():
            self.preparation_worker.quit()
            self.preparation_worker.wait()


# Import QTimer for scroll delay
from PySide6.QtCore import QTimer
