"""
Document Interrogation Tab for BMLibrarian Configuration GUI.

Provides a document viewer (PDF/Markdown) with an AI chatbot interface
for asking questions about the displayed document.
"""

import flet as ft
from typing import TYPE_CHECKING, Optional, List, Dict
from pathlib import Path
from .pdf_viewer import PDFViewer, PYMUPDF_AVAILABLE, PyMuPDFNotAvailableError, PDFLoadError


# Custom Exceptions
class FileValidationError(Exception):
    """Raised when file validation fails."""
    pass


class FileSizeError(FileValidationError):
    """Raised when file exceeds size limit."""
    pass

if TYPE_CHECKING:
    from ..config_app import BMLibrarianConfigApp


class ChatMessage:
    """Represents a single chat message."""

    def __init__(self, text: str, is_user: bool):
        self.text = text
        self.is_user = is_user


class DocumentInterrogationTab:
    """Document interrogation tab with split-pane document viewer and chat interface."""

    def __init__(self, app: "BMLibrarianConfigApp"):
        self.app = app
        self.current_document_path: Optional[str] = None
        self.current_document_content: Optional[str] = None
        self.selected_model: Optional[str] = None
        self.chat_history: List[ChatMessage] = []

        # PDF viewer
        self.pdf_viewer: Optional[PDFViewer] = None
        self.is_pdf_loaded = False

        # UI controls
        self.file_selector_button = None
        self.model_dropdown = None
        self.document_viewer = None
        self.chat_container = None
        self.chat_messages_column = None
        self.message_input = None
        self.send_button = None
        self.pane_divider = None

    def build(self) -> ft.Container:
        """Build the document interrogation tab content."""

        # Top bar with file selector and model dropdown
        top_bar = self._build_top_bar()

        # Split-pane content area
        split_pane = self._build_split_pane()

        # Main layout
        return ft.Container(
            content=ft.Column([
                top_bar,
                ft.Divider(height=1, color=ft.Colors.GREY_400),
                split_pane
            ],
            spacing=0
            ),
            expand=True,
            padding=0
        )

    def _build_top_bar(self) -> ft.Container:
        """Build the top bar with file selector and model dropdown."""

        # File selector button
        self.file_selector_button = ft.ElevatedButton(
            "Load Document",
            icon=ft.Icons.FOLDER_OPEN,
            on_click=self._on_file_select_click,
            height=40,
            style=ft.ButtonStyle(
                bgcolor=ft.Colors.BLUE_600,
                color=ft.Colors.WHITE
            )
        )

        # Current document label
        self.current_doc_label = ft.Text(
            "No document loaded",
            size=12,
            color=ft.Colors.GREY_600,
            italic=True,
            expand=True
        )

        # Model dropdown
        self.model_dropdown = ft.Dropdown(
            label="LLM Model",
            hint_text="Select Ollama model",
            width=300,
            on_change=self._on_model_change,
            options=[]
        )

        # Refresh models button
        refresh_models_button = ft.IconButton(
            icon=ft.Icons.REFRESH,
            tooltip="Refresh model list",
            on_click=self._refresh_models,
            icon_color=ft.Colors.BLUE_600
        )

        # Initial model load
        self._refresh_models(None)

        return ft.Container(
            content=ft.Row([
                self.file_selector_button,
                self.current_doc_label,
                self.model_dropdown,
                refresh_models_button
            ],
            alignment=ft.MainAxisAlignment.START,
            spacing=15,
            vertical_alignment=ft.CrossAxisAlignment.CENTER
            ),
            padding=ft.padding.all(10),
            bgcolor=ft.Colors.GREY_100,
            height=60
        )

    def _build_split_pane(self) -> ft.Container:
        """Build the split-pane layout with document viewer and chat interface."""

        # Left pane: Document viewer
        document_pane = self._build_document_viewer_pane()

        # Right pane: Chat interface
        chat_pane = self._build_chat_interface_pane()

        # Split layout using Row with resizable containers
        # Note: Flet doesn't have a native splitter, so we use fixed proportions
        # In a future enhancement, could add manual resize handles
        split_layout = ft.Row(
            [
                ft.Container(
                    content=document_pane,
                    expand=3,  # 60% width
                    border=ft.border.only(right=ft.BorderSide(1, ft.Colors.GREY_400))
                ),
                ft.Container(
                    content=chat_pane,
                    expand=2,  # 40% width
                )
            ],
            spacing=0,
            expand=True
        )

        return ft.Container(
            content=split_layout,
            expand=True,
            padding=0
        )

    def _build_document_viewer_pane(self) -> ft.Column:
        """Build the document viewer pane (left side)."""

        # Document content viewer
        self.document_viewer = ft.Container(
            content=ft.Column([
                ft.Icon(
                    ft.Icons.DESCRIPTION_OUTLINED,
                    size=100,
                    color=ft.Colors.GREY_400
                ),
                ft.Text(
                    "No document loaded",
                    size=16,
                    color=ft.Colors.GREY_500,
                    text_align=ft.TextAlign.CENTER
                ),
                ft.Text(
                    "Click 'Load Document' to open a PDF or Markdown file",
                    size=12,
                    color=ft.Colors.GREY_400,
                    text_align=ft.TextAlign.CENTER
                )
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            expand=True
            ),
            bgcolor=ft.Colors.WHITE,
            padding=ft.padding.all(20),
            expand=True
        )

        return ft.Column([
            ft.Container(
                content=ft.Text("Document Viewer", size=14, weight=ft.FontWeight.BOLD),
                padding=ft.padding.all(10),
                bgcolor=ft.Colors.GREY_200
            ),
            self.document_viewer
        ],
        spacing=0,
        expand=True
        )

    def _build_chat_interface_pane(self) -> ft.Column:
        """Build the chat interface pane (right side)."""

        # Chat messages column (scrollable)
        self.chat_messages_column = ft.Column(
            controls=[
                self._create_welcome_message()
            ],
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
            expand=True
        )

        # Chat messages container
        self.chat_container = ft.Container(
            content=self.chat_messages_column,
            bgcolor=ft.Colors.GREY_50,
            padding=ft.padding.all(10),
            expand=True,
            border=ft.border.all(1, ft.Colors.GREY_300)
        )

        # Message input area
        self.message_input = ft.TextField(
            hint_text="Ask a question about the document...",
            multiline=True,
            min_lines=1,
            max_lines=3,
            expand=True,
            on_submit=self._on_send_message,
            shift_enter=True,  # Shift+Enter for new line
            border_color=ft.Colors.BLUE_400
        )

        self.send_button = ft.IconButton(
            icon=ft.Icons.SEND,
            icon_color=ft.Colors.WHITE,
            bgcolor=ft.Colors.BLUE_600,
            on_click=self._on_send_message,
            tooltip="Send message (or press Enter)"
        )

        # Input row
        input_row = ft.Row([
            self.message_input,
            self.send_button
        ],
        spacing=10,
        vertical_alignment=ft.CrossAxisAlignment.END
        )

        return ft.Column([
            ft.Container(
                content=ft.Text("Chat", size=14, weight=ft.FontWeight.BOLD),
                padding=ft.padding.all(10),
                bgcolor=ft.Colors.GREY_200
            ),
            self.chat_container,
            ft.Container(
                content=input_row,
                padding=ft.padding.all(10),
                bgcolor=ft.Colors.WHITE,
                border=ft.border.only(top=ft.BorderSide(1, ft.Colors.GREY_300))
            )
        ],
        spacing=0,
        expand=True
        )

    def _create_welcome_message(self) -> ft.Container:
        """Create the initial welcome message bubble."""
        return self._create_message_bubble(
            "👋 Welcome to Document Interrogation!\n\n"
            "Load a document and select an LLM model to get started. "
            "I'll help you analyze and answer questions about your document.",
            is_user=False
        )

    def _create_message_bubble(self, text: str, is_user: bool) -> ft.Container:
        """Create a message bubble with appropriate styling."""

        if is_user:
            # User message: right-aligned, blue
            return ft.Container(
                content=ft.Row([
                    ft.Container(expand=1),  # Spacer for right alignment
                    ft.Container(
                        content=ft.Column([
                            ft.Text("You", size=10, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_900),
                            ft.Text(text, size=13, color=ft.Colors.WHITE, selectable=True)
                        ],
                        spacing=5
                        ),
                        bgcolor=ft.Colors.BLUE_600,
                        padding=ft.padding.all(12),
                        border_radius=ft.border_radius.only(12, 12, 0, 12),
                        max_width=500
                    )
                ]),
                margin=ft.margin.only(bottom=5)
            )
        else:
            # LLM message: left-aligned, grey
            return ft.Container(
                content=ft.Row([
                    ft.Container(
                        content=ft.Column([
                            ft.Text("AI Assistant", size=10, weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_800),
                            ft.Text(text, size=13, color=ft.Colors.BLACK87, selectable=True)
                        ],
                        spacing=5
                        ),
                        bgcolor=ft.Colors.GREY_200,
                        padding=ft.padding.all(12),
                        border_radius=ft.border_radius.only(12, 12, 12, 0),
                        max_width=500
                    ),
                    ft.Container(expand=1)  # Spacer for left alignment
                ]),
                margin=ft.margin.only(bottom=5)
            )

    def _on_file_select_click(self, e):
        """Handle file selector button click."""
        def file_picker_result(result: ft.FilePickerResultEvent):
            try:
                # Clear file picker overlay
                self.app.page.overlay.clear()
                self.app.page.update()

                if result.files:
                    file_path = result.files[0].path
                    self._load_document(file_path)

            except Exception as ex:
                self._show_error(f"Failed to load document: {str(ex)}")

        file_picker = ft.FilePicker(on_result=file_picker_result)
        self.app.page.overlay.append(file_picker)
        self.app.page.update()

        file_picker.pick_files(
            dialog_title="Select Document",
            allowed_extensions=["pdf", "md", "txt"],
            file_type=ft.FilePickerFileType.CUSTOM
        )

    def _load_document(self, file_path: str):
        """
        Load a document for viewing and interrogation.

        Args:
            file_path: Path to the document to load

        Raises:
            FileValidationError: If file validation fails
            FileSizeError: If file exceeds size limit
        """
        try:
            # Security: Validate file path
            path = Path(file_path)

            # Check file exists
            if not path.exists():
                raise FileValidationError(f"File does not exist: {file_path}")

            # Check it's a file (not directory)
            if not path.is_file():
                raise FileValidationError(f"Path is not a file: {file_path}")

            # Security: Check file size (100MB limit)
            max_size_bytes = 100 * 1024 * 1024  # 100MB
            file_size = path.stat().st_size
            if file_size > max_size_bytes:
                size_mb = file_size / (1024 * 1024)
                raise FileSizeError(
                    f"File too large ({size_mb:.1f}MB). Maximum size is 100MB."
                )

            self.current_document_path = file_path

            # Update label
            self.current_doc_label.value = f"📄 {path.name}"
            self.current_doc_label.italic = False
            self.current_doc_label.color = ft.Colors.BLACK87

            # Load content based on file type
            if path.suffix.lower() == '.pdf':
                self._load_pdf(file_path)
            elif path.suffix.lower() in ['.md', '.txt']:
                self._load_text_document(file_path)
            else:
                raise FileValidationError(f"Unsupported file type: {path.suffix}")

            # Add system message to chat
            self._add_chat_message(
                f"✅ Document loaded: {path.name}\n\n"
                f"You can now ask questions about this document.",
                is_user=False
            )

            self.app.page.update()

        except (FileValidationError, FileSizeError) as ex:
            self._show_error(str(ex))
        except (PyMuPDFNotAvailableError, PDFLoadError) as ex:
            self._show_error(f"PDF Error: {str(ex)}")
        except Exception as ex:
            self._show_error(f"Error loading document: {str(ex)}")

    def _load_pdf(self, file_path: str):
        """
        Load and display a PDF document.

        Raises:
            PyMuPDFNotAvailableError: If PyMuPDF is not installed
            PDFLoadError: If PDF cannot be loaded
        """
        try:
            if not PYMUPDF_AVAILABLE:
                # Show error message if PyMuPDF is not installed
                self.document_viewer.content = ft.Column([
                    ft.Icon(ft.Icons.ERROR_OUTLINE, size=80, color=ft.Colors.RED_400),
                    ft.Text(
                        "PyMuPDF Not Installed",
                        size=16,
                        weight=ft.FontWeight.BOLD,
                        text_align=ft.TextAlign.CENTER,
                        color=ft.Colors.RED_700
                    ),
                    ft.Container(height=10),
                    ft.Text(
                        "To view PDF files, install PyMuPDF:",
                        size=12,
                        color=ft.Colors.GREY_600,
                        text_align=ft.TextAlign.CENTER
                    ),
                    ft.Text(
                        "pip install PyMuPDF",
                        size=12,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.BLUE_700,
                        text_align=ft.TextAlign.CENTER
                    )
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                expand=True
                )
                self.current_document_content = f"[PDF Document: {file_path}] (PyMuPDF not installed)"
                raise PyMuPDFNotAvailableError("PyMuPDF is not installed. Run: pip install PyMuPDF")

            # Create PDF viewer if not already created
            if not self.pdf_viewer:
                self.pdf_viewer = PDFViewer(
                    page=self.app.page,
                    on_page_change=self._on_pdf_page_change
                )

            # Load PDF
            self.pdf_viewer.load_pdf(file_path)

            # Replace document viewer content with PDF viewer
            self.document_viewer.content = self.pdf_viewer.build()
            self.is_pdf_loaded = True

            # Extract all text for LLM processing
            self.current_document_content = self.pdf_viewer.get_all_text()

        except PyMuPDFNotAvailableError:
            raise
        except PDFLoadError as ex:
            # Show error in viewer
            self.document_viewer.content = ft.Column([
                ft.Icon(ft.Icons.ERROR_OUTLINE, size=80, color=ft.Colors.RED_400),
                ft.Text(
                    "PDF Loading Error",
                    size=16,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.RED_700
                ),
                ft.Container(height=10),
                ft.Text(
                    str(ex),
                    size=12,
                    color=ft.Colors.GREY_600,
                    text_align=ft.TextAlign.CENTER
                )
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            expand=True
            )
            raise
        except Exception as ex:
            # Show error in viewer
            self.document_viewer.content = ft.Column([
                ft.Icon(ft.Icons.ERROR_OUTLINE, size=80, color=ft.Colors.RED_400),
                ft.Text(
                    "PDF Loading Error",
                    size=16,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.RED_700
                ),
                ft.Container(height=10),
                ft.Text(
                    str(ex),
                    size=12,
                    color=ft.Colors.GREY_600,
                    text_align=ft.TextAlign.CENTER
                )
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            expand=True
            )
            raise PDFLoadError(f"Failed to load PDF: {str(ex)}")

    def _load_text_document(self, file_path: str):
        """
        Load and display a text/markdown document.

        Raises:
            FileValidationError: If file cannot be read
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            self.current_document_content = content

            # Display content in scrollable markdown or text viewer
            if Path(file_path).suffix.lower() == '.md':
                # Use Markdown control for .md files
                self.document_viewer.content = ft.Markdown(
                    content,
                    selectable=True,
                    extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                    on_tap_link=lambda e: self.app.page.launch_url(e.data)
                )
            else:
                # Use Text for .txt files
                self.document_viewer.content = ft.Container(
                    content=ft.Text(
                        content,
                        size=12,
                        selectable=True,
                        color=ft.Colors.BLACK87
                    ),
                    padding=ft.padding.all(10)
                )

        except UnicodeDecodeError as ex:
            raise FileValidationError(f"File encoding error: {str(ex)}")
        except PermissionError as ex:
            raise FileValidationError(f"Permission denied: {str(ex)}")
        except Exception as ex:
            raise FileValidationError(f"Failed to read text document: {str(ex)}")

    def _on_model_change(self, e):
        """Handle model selection change."""
        self.selected_model = self.model_dropdown.value

        # Add confirmation message
        if self.selected_model:
            self._add_chat_message(
                f"🤖 Model changed to: {self.selected_model}",
                is_user=False
            )

    def _refresh_models(self, e):
        """Refresh the list of available Ollama models."""
        try:
            import ollama

            # Get Ollama config from app
            ollama_config = self.app.config.get_ollama_config()
            host = ollama_config.get('host', 'http://localhost:11434')

            # Create client and fetch models
            client = ollama.Client(host=host)
            models_response = client.list()
            models = [model.model for model in models_response.models]

            # Update dropdown options
            self.model_dropdown.options = [
                ft.dropdown.Option(model) for model in models
            ]

            # Set default if available
            if models and not self.selected_model:
                self.model_dropdown.value = models[0]
                self.selected_model = models[0]

            if self.app.page:
                self.app.page.update()

        except Exception as ex:
            self._show_error(f"Failed to fetch models: {str(ex)}")

    def _on_send_message(self, e):
        """Handle sending a chat message."""
        message_text = self.message_input.value

        if not message_text or not message_text.strip():
            return

        # Validation checks
        if not self.current_document_path:
            self._show_error("Please load a document first")
            return

        if not self.selected_model:
            self._show_error("Please select an LLM model first")
            return

        # Add user message to chat
        self._add_chat_message(message_text, is_user=True)

        # Clear input
        self.message_input.value = ""
        self.app.page.update()

        # Show thinking indicator
        thinking_bubble = self._create_message_bubble("🤔 Analyzing document...", is_user=False)
        self.chat_messages_column.controls.append(thinking_bubble)
        self.app.page.update()

        try:
            # Get LLM response
            response = self._get_llm_response(message_text)

            # Remove thinking indicator
            self.chat_messages_column.controls.remove(thinking_bubble)

            # Add LLM response to chat
            self._add_chat_message(response, is_user=False)

        except Exception as ex:
            # Remove thinking indicator
            if thinking_bubble in self.chat_messages_column.controls:
                self.chat_messages_column.controls.remove(thinking_bubble)

            # Show error message
            self._add_chat_message(
                f"❌ Error communicating with LLM:\n\n{str(ex)}",
                is_user=False
            )

        self.app.page.update()

    def _get_llm_response(self, question: str) -> str:
        """
        Get LLM response for a question about the document.

        Args:
            question: User's question

        Returns:
            LLM response text

        Raises:
            Exception: If LLM communication fails
        """
        try:
            import ollama

            # Get Ollama config from app
            ollama_config = self.app.config.get_ollama_config()
            host = ollama_config.get('host', 'http://localhost:11434')

            # Create client
            client = ollama.Client(host=host)

            # Prepare context with document content
            # Truncate document if it's too long to avoid context overflow
            max_doc_length = 50000  # ~12k tokens at 4 chars/token
            document_content = self.current_document_content
            if len(document_content) > max_doc_length:
                document_content = document_content[:max_doc_length] + "\n\n[Document truncated due to length...]"

            # Build the prompt
            system_prompt = (
                "You are a helpful AI assistant analyzing a document. "
                "Answer questions about the document based on the provided content. "
                "Be concise and accurate. If the information is not in the document, say so."
            )

            user_prompt = f"""Document Content:
{document_content}

Question: {question}

Please answer the question based on the document content above."""

            # Get response from Ollama
            response = client.chat(
                model=self.selected_model,
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_prompt}
                ]
            )

            # Extract response text
            return response['message']['content']

        except ImportError:
            raise Exception("Ollama Python library not installed. Run: pip install ollama")
        except Exception as ex:
            raise Exception(f"LLM communication error: {str(ex)}")

    def _add_chat_message(self, text: str, is_user: bool):
        """Add a message to the chat history and UI."""
        # Add to history
        message = ChatMessage(text, is_user)
        self.chat_history.append(message)

        # Create bubble and add to UI
        bubble = self._create_message_bubble(text, is_user)
        self.chat_messages_column.controls.append(bubble)

        # Auto-scroll to bottom
        if self.app.page:
            self.app.page.update()

    def _show_error(self, message: str):
        """Show error message as snackbar."""
        if self.app.page:
            snack_bar = ft.SnackBar(
                ft.Text(f"❌ {message}"),
                bgcolor=ft.Colors.RED_100
            )
            self.app.page.open(snack_bar)

    def _on_pdf_page_change(self, page_num: int, total_pages: int):
        """
        Callback when PDF page changes.

        Args:
            page_num: Current page number (0-indexed)
            total_pages: Total number of pages
        """
        # Can be used to update chat with page context or other UI elements
        pass

    def load_document_programmatically(self, file_path: str):
        """
        Programmatically load a document (for integration with other plugins).

        Args:
            file_path: Path to the document to load
        """
        self._load_document(file_path)

    def clear_chat(self):
        """Clear the chat history."""
        self.chat_history = []
        self.chat_messages_column.controls = [self._create_welcome_message()]
        if self.app.page:
            self.app.page.update()

    # PDF-specific API methods

    def highlight_pdf_region(self, page_num: int, rect: tuple, color: tuple = (255, 200, 0), label: str = ""):
        """
        Programmatically highlight a region in the PDF.

        This is useful for highlighting citations or specific passages mentioned
        in chat responses.

        Args:
            page_num: Page number (0-indexed)
            rect: Rectangle (x0, y0, x1, y1) in PDF coordinates
            color: RGB color tuple (default: orange)
            label: Optional label for this highlight

        Example:
            tab.highlight_pdf_region(0, (100, 100, 300, 120), label="Citation 1")
        """
        if self.pdf_viewer and self.is_pdf_loaded:
            self.pdf_viewer.add_highlight(page_num, rect, color, label)

    def search_pdf(self, text: str) -> int:
        """
        Search for text in the PDF and highlight all occurrences.

        Args:
            text: Text to search for

        Returns:
            Number of results found

        Example:
            count = tab.search_pdf("cardiovascular")
        """
        if self.pdf_viewer and self.is_pdf_loaded:
            return self.pdf_viewer.search_and_highlight(text)
        return 0

    def clear_pdf_highlights(self):
        """Clear all programmatic PDF highlights."""
        if self.pdf_viewer and self.is_pdf_loaded:
            self.pdf_viewer.clear_highlights()

    def jump_to_pdf_page(self, page_num: int):
        """
        Jump to a specific PDF page.

        Args:
            page_num: Page number (0-indexed)

        Example:
            tab.jump_to_pdf_page(5)  # Jump to page 6
        """
        if self.pdf_viewer and self.is_pdf_loaded:
            self.pdf_viewer.jump_to_page(page_num)
