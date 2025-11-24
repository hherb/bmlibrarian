"""
Paper Weight Laboratory - Document Viewer Tab

Displays full text content using PDF viewer for PDFs or
markdown/plain text viewer as fallback.
"""

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QStackedWidget,
    QFrame, QPushButton
)
from PySide6.QtCore import Signal, Qt

from bmlibrarian.gui.qt.resources.styles.dpi_scale import get_font_scale
from bmlibrarian.gui.qt.resources.styles.stylesheet_generator import get_stylesheet_generator
from bmlibrarian.gui.qt.widgets.pdf_viewer import PDFViewerWidget
from bmlibrarian.gui.qt.widgets.markdown_viewer import MarkdownViewer

from ..constants import AUTHOR_DISPLAY_MAX_LENGTH


logger = logging.getLogger(__name__)


# View mode indices for stacked widget
VIEW_MODE_EMPTY = 0
VIEW_MODE_PDF = 1
VIEW_MODE_TEXT = 2


class DocumentViewerTab(QWidget):
    """
    Tab for viewing full text content of documents.

    Supports:
    - PDF viewing via native Qt PDF widget
    - Markdown/plain text viewing as fallback
    - Automatic mode selection based on available content

    The tab shows either the PDF file (if available) or the full_text
    from the database rendered as markdown.
    """

    # Signal emitted when view mode changes
    view_mode_changed = Signal(str)  # "pdf", "text", or "empty"

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize document viewer tab.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)

        # Get scaling values
        self.scale = get_font_scale()
        self.styles = get_stylesheet_generator()

        # Current document state
        self._document_id: Optional[int] = None
        self._document_title: str = ""
        self._pdf_path: Optional[Path] = None
        self._full_text: Optional[str] = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the user interface components."""
        s = self.scale

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            s['padding_medium'],
            s['padding_medium'],
            s['padding_medium'],
            s['padding_medium']
        )
        layout.setSpacing(s['spacing_medium'])

        # Header with document info
        self._header_frame = QFrame()
        self._header_frame.setStyleSheet(
            self.styles.card_stylesheet(
                bg_color='#f5f5f5',
                border_color='#ddd',
                radius_key='radius_small',
                padding_key='padding_small'
            )
        )
        header_layout = QVBoxLayout(self._header_frame)
        header_layout.setContentsMargins(
            s['padding_medium'],
            s['padding_small'],
            s['padding_medium'],
            s['padding_small']
        )

        # Title row
        title_layout = QHBoxLayout()
        title_layout.setSpacing(s['spacing_medium'])

        self._title_label = QLabel("No document loaded")
        self._title_label.setStyleSheet(
            self.styles.label_stylesheet(
                font_size_key='font_medium',
                bold=True
            )
        )
        self._title_label.setWordWrap(True)
        title_layout.addWidget(self._title_label, stretch=1)

        # View mode indicator and toggle button
        self._view_mode_label = QLabel("")
        self._view_mode_label.setStyleSheet(
            self.styles.label_stylesheet(
                font_size_key='font_small',
                color='#666'
            )
        )
        title_layout.addWidget(self._view_mode_label)

        self._toggle_view_btn = QPushButton("Switch View")
        self._toggle_view_btn.setStyleSheet(
            self.styles.button_stylesheet(
                font_size_key='font_small',
                padding_key='padding_small'
            )
        )
        self._toggle_view_btn.setMinimumWidth(s['control_width_small'])
        self._toggle_view_btn.clicked.connect(self._on_toggle_view)
        self._toggle_view_btn.setVisible(False)  # Only visible when both views available
        title_layout.addWidget(self._toggle_view_btn)

        header_layout.addLayout(title_layout)

        layout.addWidget(self._header_frame)

        # Stacked widget for different view modes
        self._view_stack = QStackedWidget()

        # Empty state placeholder
        empty_widget = QWidget()
        empty_layout = QVBoxLayout(empty_widget)
        empty_layout.addStretch()
        empty_label = QLabel("Select a document to view its full text")
        empty_label.setStyleSheet(
            self.styles.label_stylesheet(
                font_size_key='font_medium',
                color='#888'
            )
        )
        empty_label.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(empty_label)
        empty_layout.addStretch()
        self._view_stack.addWidget(empty_widget)

        # PDF viewer
        self._pdf_viewer = PDFViewerWidget()
        self._view_stack.addWidget(self._pdf_viewer)

        # Text/Markdown viewer
        self._text_viewer = MarkdownViewer()
        self._view_stack.addWidget(self._text_viewer)

        layout.addWidget(self._view_stack, stretch=1)

        # Start with empty state
        self._view_stack.setCurrentIndex(VIEW_MODE_EMPTY)

    def load_document(
        self,
        document_id: int,
        title: str,
        pdf_path: Optional[Path] = None,
        full_text: Optional[str] = None
    ) -> None:
        """
        Load a document for viewing.

        Args:
            document_id: Database document ID
            title: Document title for display
            pdf_path: Optional path to PDF file
            full_text: Optional full text content (used if no PDF)
        """
        self._document_id = document_id
        self._document_title = title
        self._pdf_path = pdf_path
        self._full_text = full_text

        # Update title display
        display_title = title if len(title) <= AUTHOR_DISPLAY_MAX_LENGTH else title[:AUTHOR_DISPLAY_MAX_LENGTH] + "..."
        self._title_label.setText(display_title)

        # Determine what content is available
        has_pdf = pdf_path is not None and pdf_path.exists()
        has_text = full_text is not None and len(full_text.strip()) > 0

        # Update toggle button visibility
        self._toggle_view_btn.setVisible(has_pdf and has_text)

        # Select best view mode
        if has_pdf:
            self._show_pdf(pdf_path)
        elif has_text:
            self._show_text(full_text)
        else:
            self._show_empty("No full text available for this document")

        logger.info(
            f"Document viewer loaded document {document_id}: "
            f"pdf={has_pdf}, text={has_text}"
        )

    def _show_pdf(self, pdf_path: Path) -> None:
        """
        Show PDF viewer with the given file.

        Args:
            pdf_path: Path to PDF file
        """
        try:
            self._pdf_viewer.load_pdf(pdf_path)
            self._view_stack.setCurrentIndex(VIEW_MODE_PDF)
            self._view_mode_label.setText("PDF View")
            self.view_mode_changed.emit("pdf")
        except Exception as e:
            logger.error(f"Failed to load PDF {pdf_path}: {e}")
            # Fall back to text if available
            if self._full_text:
                self._show_text(self._full_text)
            else:
                self._show_empty(f"Failed to load PDF: {e}")

    def _show_text(self, text: str) -> None:
        """
        Show text viewer with the given content.

        Args:
            text: Text content to display (rendered as markdown)
        """
        self._text_viewer.set_markdown(text)
        self._view_stack.setCurrentIndex(VIEW_MODE_TEXT)
        self._view_mode_label.setText("Text View")
        self.view_mode_changed.emit("text")

    def _show_empty(self, message: str = "No content available") -> None:
        """
        Show empty state with a message.

        Args:
            message: Message to display
        """
        self._view_stack.setCurrentIndex(VIEW_MODE_EMPTY)
        self._view_mode_label.setText("")
        self._title_label.setText(message)
        self.view_mode_changed.emit("empty")

    def _on_toggle_view(self) -> None:
        """Toggle between PDF and text view."""
        current_mode = self._view_stack.currentIndex()

        if current_mode == VIEW_MODE_PDF and self._full_text:
            self._show_text(self._full_text)
        elif current_mode == VIEW_MODE_TEXT and self._pdf_path:
            self._show_pdf(self._pdf_path)

    def clear(self) -> None:
        """Clear the document viewer."""
        self._document_id = None
        self._document_title = ""
        self._pdf_path = None
        self._full_text = None

        self._pdf_viewer.clear()
        self._text_viewer.clear_content()
        self._show_empty("Select a document to view its full text")
        self._toggle_view_btn.setVisible(False)

    @property
    def document_id(self) -> Optional[int]:
        """Get the currently loaded document ID."""
        return self._document_id

    @property
    def current_view_mode(self) -> str:
        """Get the current view mode ("pdf", "text", or "empty")."""
        index = self._view_stack.currentIndex()
        if index == VIEW_MODE_PDF:
            return "pdf"
        elif index == VIEW_MODE_TEXT:
            return "text"
        return "empty"


__all__ = ['DocumentViewerTab']
