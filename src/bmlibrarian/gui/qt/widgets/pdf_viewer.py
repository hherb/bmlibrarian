"""
PDF Viewer widget for BMLibrarian Qt GUI.

Provides a simple PDF viewing interface with page navigation.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QMessageBox, QSpinBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QImage
from typing import Optional
from pathlib import Path

from ..resources.styles import get_font_scale


class PDFViewerWidget(QWidget):
    """
    PDF viewer widget with page navigation.

    Simple PDF viewer using PDF rendering libraries.
    Falls back to displaying file path if rendering libraries are not available.
    """

    page_changed = Signal(int)  # Emits current page number

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
        self.pdf_document = None

        # Try to import PDF rendering library
        self.has_pdf_support = False
        try:
            import fitz  # PyMuPDF
            self.has_pdf_support = True
            self._render_backend = 'pymupdf'
        except ImportError:
            try:
                import pypdf
                self.has_pdf_support = True
                self._render_backend = 'pypdf'
            except ImportError:
                self._render_backend = None

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

        # PDF display area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignCenter)

        self.pdf_label = QLabel("No PDF loaded")
        self.pdf_label.setAlignment(Qt.AlignCenter)
        self.pdf_label.setStyleSheet(f"background-color: #f0f0f0; padding: {s['padding_xlarge']}px;")

        self.scroll_area.setWidget(self.pdf_label)
        layout.addWidget(self.scroll_area)

        # Status bar
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(f"color: gray; font-size: {s['font_tiny']}pt;")
        layout.addWidget(self.status_label)

        # Zoom level
        self.zoom_level = 1.0

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

        if not self.has_pdf_support:
            # Fallback: Just show file info
            self.pdf_label.setText(
                f"PDF Support not available\n\n"
                f"File: {self.pdf_path.name}\n"
                f"Path: {self.pdf_path}\n\n"
                f"Install PyMuPDF (pip install pymupdf) for PDF rendering support."
            )
            self.status_label.setText("PDF rendering not available")
            return

        try:
            # Load PDF with appropriate backend
            if self._render_backend == 'pymupdf':
                import fitz
                self.pdf_document = fitz.open(str(self.pdf_path))
                self.total_pages = len(self.pdf_document)
            elif self._render_backend == 'pypdf':
                import pypdf
                self.pdf_document = pypdf.PdfReader(str(self.pdf_path))
                self.total_pages = len(self.pdf_document.pages)

            # Update UI
            self.current_page = 0
            self.page_spin.setMaximum(self.total_pages)
            self.page_spin.setValue(1)
            self.page_label.setText(f"of {self.total_pages}")

            # Enable navigation
            self._update_navigation_buttons()

            # Render first page
            self._render_current_page()

            self.status_label.setText(f"Loaded: {self.pdf_path.name} ({self.total_pages} pages)")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load PDF:\n\n{str(e)}")
            self.status_label.setText(f"Error loading PDF: {str(e)}")

    def _render_current_page(self):
        """Render the current page."""
        if not self.pdf_document:
            return

        try:
            if self._render_backend == 'pymupdf':
                # PyMuPDF rendering
                import fitz
                page = self.pdf_document[self.current_page]

                # Create transformation matrix with zoom (identity matrix scaled)
                mat = fitz.Matrix(self.zoom_level, self.zoom_level)

                pix = page.get_pixmap(matrix=mat)

                # Convert to QImage
                img = QImage(
                    pix.samples,
                    pix.width,
                    pix.height,
                    pix.stride,
                    QImage.Format_RGB888
                )

                # Display
                pixmap = QPixmap.fromImage(img)
                self.pdf_label.setPixmap(pixmap)

            elif self._render_backend == 'pypdf':
                # PyPDF fallback (text only)
                page = self.pdf_document.pages[self.current_page]
                text = page.extract_text()

                self.pdf_label.setText(
                    f"Page {self.current_page + 1} of {self.total_pages}\n\n"
                    f"Text Content:\n\n{text[:2000]}..."
                )

            self.page_changed.emit(self.current_page + 1)

        except Exception as e:
            self.pdf_label.setText(f"Error rendering page: {str(e)}")
            self.status_label.setText(f"Render error: {str(e)}")

    def _on_previous_page(self):
        """Navigate to previous page."""
        if self.current_page > 0:
            self.current_page -= 1
            self.page_spin.setValue(self.current_page + 1)
            self._render_current_page()
            self._update_navigation_buttons()

    def _on_next_page(self):
        """Navigate to next page."""
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.page_spin.setValue(self.current_page + 1)
            self._render_current_page()
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
            self._render_current_page()
            self._update_navigation_buttons()

    def _on_zoom_in(self):
        """Increase zoom level."""
        self.zoom_level = min(self.zoom_level + 0.2, 3.0)
        self._render_current_page()
        self.status_label.setText(f"Zoom: {int(self.zoom_level * 100)}%")

    def _on_zoom_out(self):
        """Decrease zoom level."""
        self.zoom_level = max(self.zoom_level - 0.2, 0.5)
        self._render_current_page()
        self.status_label.setText(f"Zoom: {int(self.zoom_level * 100)}%")

    def _update_navigation_buttons(self):
        """Update navigation button states."""
        self.prev_btn.setEnabled(self.current_page > 0)
        self.next_btn.setEnabled(self.current_page < self.total_pages - 1)

    def get_all_text(self) -> str:
        """
        Extract all text from the PDF document.

        Returns:
            String containing all text from all pages, or empty string if no PDF loaded
        """
        if not self.pdf_document:
            return ""

        try:
            text_parts = []

            if self._render_backend == 'pymupdf':
                # PyMuPDF text extraction
                for page_num in range(self.total_pages):
                    page = self.pdf_document[page_num]
                    text = page.get_text()
                    text_parts.append(text)

            elif self._render_backend == 'pypdf':
                # PyPDF text extraction
                for page_num in range(self.total_pages):
                    page = self.pdf_document.pages[page_num]
                    text = page.extract_text()
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
        self.pdf_document = None
        self.zoom_level = 1.0

        self.pdf_label.setText("No PDF loaded")
        self.page_spin.setMaximum(1)
        self.page_spin.setValue(1)
        self.page_label.setText("of 0")
        self.status_label.setText("")

        self._update_navigation_buttons()
