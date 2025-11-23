"""
PDF Viewer widget for BMLibrarian Qt GUI.

Provides a PDF viewing interface using the native PySide6 QPdfView widget.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QMessageBox, QSpinBox
)
from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from typing import Optional
from pathlib import Path

from ..resources.styles import get_font_scale


class PDFViewerWidget(QWidget):
    """
    PDF viewer widget using native PySide6 QPdfView.

    Provides a modern PDF viewing experience with built-in scrolling,
    zooming, and multi-page display using Qt's native PDF support.
    """

    page_changed = Signal(int)  # Emits current page number

    # Zoom level constants
    ZOOM_MIN = 0.5
    ZOOM_MAX = 3.0
    ZOOM_STEP = 0.2
    ZOOM_DEFAULT = 1.0

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize PDF viewer.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)

        # Get DPI scale
        self.scale = get_font_scale()

        self.pdf_path: Optional[Path] = None
        self.current_page: int = 0
        self.total_pages: int = 0
        self.zoom_level: float = self.ZOOM_DEFAULT

        # PDF document model
        self._pdf_document = QPdfDocument(self)
        self._pdf_document.statusChanged.connect(self._on_document_status_changed)

        # Text extraction backend (for get_all_text)
        self._text_extraction_doc = None
        self._has_text_extraction = False
        try:
            import fitz  # PyMuPDF
            self._has_text_extraction = True
        except ImportError:
            pass

        self._setup_ui()

    def _setup_ui(self):
        """Setup the user interface."""
        s = self.scale

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(s['spacing_tiny'])

        # Navigation bar
        nav_layout = QHBoxLayout()
        nav_layout.setSpacing(s['spacing_medium'])

        self.prev_btn = QPushButton("◀ Previous")
        self.prev_btn.clicked.connect(self._on_previous_page)
        self.prev_btn.setEnabled(False)
        nav_layout.addWidget(self.prev_btn)

        nav_layout.addWidget(QLabel("Page:"))

        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.setMaximum(1)
        self.page_spin.valueChanged.connect(self._on_page_changed)
        nav_layout.addWidget(self.page_spin)

        self.page_label = QLabel("of 0")
        nav_layout.addWidget(self.page_label)

        self.next_btn = QPushButton("Next ▶")
        self.next_btn.clicked.connect(self._on_next_page)
        self.next_btn.setEnabled(False)
        nav_layout.addWidget(self.next_btn)

        nav_layout.addStretch()

        self.zoom_in_btn = QPushButton("Zoom In")
        self.zoom_in_btn.clicked.connect(self._on_zoom_in)
        nav_layout.addWidget(self.zoom_in_btn)

        self.zoom_out_btn = QPushButton("Zoom Out")
        self.zoom_out_btn.clicked.connect(self._on_zoom_out)
        nav_layout.addWidget(self.zoom_out_btn)

        layout.addLayout(nav_layout)

        # Native PDF view
        self._pdf_view = QPdfView()
        self._pdf_view.setDocument(self._pdf_document)
        self._pdf_view.setPageMode(QPdfView.PageMode.MultiPage)
        self._pdf_view.setZoomMode(QPdfView.ZoomMode.Custom)
        self._pdf_view.setZoomFactor(self.zoom_level)
        layout.addWidget(self._pdf_view)

        # Status bar
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(f"color: gray; font-size: {s['font_tiny']}pt;")
        layout.addWidget(self.status_label)

    def load_pdf(self, pdf_path: str | Path):
        """
        Load a PDF file for viewing.

        Args:
            pdf_path: Path to PDF file
        """
        self.pdf_path = Path(pdf_path)

        if not self.pdf_path.exists():
            QMessageBox.critical(self, "Error", f"PDF file not found: {pdf_path}")
            self.status_label.setText("Error: File not found")
            return

        # Load PDF using native Qt PDF support
        self._pdf_document.load(str(self.pdf_path))

        # Load for text extraction (if available)
        if self._has_text_extraction:
            try:
                import fitz
                self._text_extraction_doc = fitz.open(str(self.pdf_path))
            except Exception as e:
                self._text_extraction_doc = None
                # Non-fatal: text extraction just won't work

    def _on_document_status_changed(self, status: QPdfDocument.Status):
        """
        Handle document status changes.

        Args:
            status: New document status
        """
        if status == QPdfDocument.Status.Ready:
            self.total_pages = self._pdf_document.pageCount()
            self.current_page = 0

            # Update UI
            self.page_spin.setMaximum(self.total_pages)
            self.page_spin.setValue(1)
            self.page_label.setText(f"of {self.total_pages}")

            # Enable navigation
            self._update_navigation_buttons()

            self.status_label.setText(
                f"Loaded: {self.pdf_path.name if self.pdf_path else 'PDF'} "
                f"({self.total_pages} pages)"
            )

            # Navigate to first page
            self._navigate_to_page(0)

        elif status == QPdfDocument.Status.Error:
            error_msg = "Failed to load PDF"
            QMessageBox.critical(self, "Error", error_msg)
            self.status_label.setText(f"Error: {error_msg}")

        elif status == QPdfDocument.Status.Loading:
            self.status_label.setText("Loading PDF...")

    def _navigate_to_page(self, page: int):
        """
        Navigate to a specific page.

        Args:
            page: Page number (0-indexed)
        """
        if 0 <= page < self.total_pages:
            self.current_page = page
            navigator = self._pdf_view.pageNavigator()
            if navigator:
                navigator.jump(page, point=navigator.currentLocation().position)
            self.page_changed.emit(page + 1)

    def _on_previous_page(self):
        """Navigate to previous page."""
        if self.current_page > 0:
            self.current_page -= 1
            self.page_spin.setValue(self.current_page + 1)
            self._navigate_to_page(self.current_page)
            self._update_navigation_buttons()

    def _on_next_page(self):
        """Navigate to next page."""
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.page_spin.setValue(self.current_page + 1)
            self._navigate_to_page(self.current_page)
            self._update_navigation_buttons()

    def _on_page_changed(self, page_num: int):
        """
        Handle page spin box change.

        Args:
            page_num: New page number (1-indexed)
        """
        new_page = page_num - 1
        if 0 <= new_page < self.total_pages and new_page != self.current_page:
            self.current_page = new_page
            self._navigate_to_page(self.current_page)
            self._update_navigation_buttons()

    def _on_zoom_in(self):
        """Increase zoom level."""
        self.zoom_level = min(self.zoom_level + self.ZOOM_STEP, self.ZOOM_MAX)
        self._pdf_view.setZoomFactor(self.zoom_level)
        self.status_label.setText(f"Zoom: {int(self.zoom_level * 100)}%")

    def _on_zoom_out(self):
        """Decrease zoom level."""
        self.zoom_level = max(self.zoom_level - self.ZOOM_STEP, self.ZOOM_MIN)
        self._pdf_view.setZoomFactor(self.zoom_level)
        self.status_label.setText(f"Zoom: {int(self.zoom_level * 100)}%")

    def _update_navigation_buttons(self):
        """Update navigation button states."""
        self.prev_btn.setEnabled(self.current_page > 0)
        self.next_btn.setEnabled(self.current_page < self.total_pages - 1)

    def get_all_text(self) -> str:
        """
        Extract all text from the PDF document.

        Uses PyMuPDF for text extraction as QPdfDocument doesn't provide
        text extraction capability.

        Returns:
            String containing all text from all pages, or empty string if
            text extraction is not available or no PDF is loaded.
        """
        if not self._text_extraction_doc:
            return ""

        try:
            text_parts = []
            for page_num in range(len(self._text_extraction_doc)):
                page = self._text_extraction_doc[page_num]
                text = page.get_text()
                text_parts.append(text)
            return '\n\n'.join(text_parts)

        except Exception as e:
            print(f"Error extracting text from PDF: {e}")
            return ""

    def clear(self):
        """Clear the PDF viewer."""
        self.pdf_path = None
        self.current_page = 0
        self.total_pages = 0
        self.zoom_level = self.ZOOM_DEFAULT

        # Close documents
        self._pdf_document.close()
        if self._text_extraction_doc:
            self._text_extraction_doc.close()
            self._text_extraction_doc = None

        # Reset UI
        self.page_spin.setMaximum(1)
        self.page_spin.setValue(1)
        self.page_label.setText("of 0")
        self.status_label.setText("")

        self._pdf_view.setZoomFactor(self.ZOOM_DEFAULT)
        self._update_navigation_buttons()
