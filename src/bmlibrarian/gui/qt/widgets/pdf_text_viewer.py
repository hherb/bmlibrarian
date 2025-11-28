"""
PDF Text Viewer widget with text selection support.

Uses PyMuPDF (fitz) for rendering and text extraction, providing
full text selection and copy functionality that QPdfView lacks.
"""

import logging
from pathlib import Path
from typing import Optional, List, Tuple

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QMessageBox, QSpinBox, QScrollArea, QApplication, QMenu
)
from PySide6.QtCore import Qt, Signal, QRect, QPoint, QRectF
from PySide6.QtGui import (
    QPixmap, QImage, QPainter, QColor, QPen, QBrush,
    QMouseEvent, QPaintEvent, QKeyEvent, QAction
)

from ..resources.styles import get_font_scale, StylesheetGenerator

logger = logging.getLogger(__name__)


class TextBlock:
    """Represents a text block with position information."""

    def __init__(
        self,
        text: str,
        rect: QRectF,
        page: int,
        line_num: int = 0
    ) -> None:
        """
        Initialize text block.

        Args:
            text: The text content
            rect: Bounding rectangle in page coordinates
            page: Page number (0-indexed)
            line_num: Line number within the page for proper ordering
        """
        self.text = text
        self.rect = rect
        self.page = page
        self.line_num = line_num


class PDFPageWidget(QLabel):
    """
    Widget that displays a single PDF page with text selection support.

    Renders the page as a pixmap and overlays text selection highlighting.
    """

    text_selected = Signal(str)  # Emitted when text is selected

    def __init__(
        self,
        page_num: int,
        parent: Optional[QWidget] = None
    ) -> None:
        """
        Initialize page widget.

        Args:
            page_num: Page number (0-indexed)
            parent: Parent widget
        """
        super().__init__(parent)
        self.page_num = page_num
        self._pixmap: Optional[QPixmap] = None
        self._text_blocks: List[TextBlock] = []
        self._scale_factor: float = 1.0

        # Selection state
        self._selection_start: Optional[QPoint] = None
        self._selection_end: Optional[QPoint] = None
        self._selected_blocks: List[TextBlock] = []

        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.IBeamCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def set_page_data(
        self,
        pixmap: QPixmap,
        text_blocks: List[TextBlock],
        scale_factor: float
    ) -> None:
        """
        Set the page image and text data.

        Args:
            pixmap: Rendered page image
            text_blocks: List of text blocks with positions
            scale_factor: Scale factor applied to coordinates
        """
        self._pixmap = pixmap
        self._text_blocks = text_blocks
        self._scale_factor = scale_factor
        self._clear_selection()
        self.setPixmap(pixmap)
        self.setFixedSize(pixmap.size())

    def _clear_selection(self) -> None:
        """Clear the current text selection."""
        self._selection_start = None
        self._selection_end = None
        self._selected_blocks = []
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse press to start selection."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._selection_start = event.pos()
            self._selection_end = event.pos()
            self._selected_blocks = []
            self.update()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Handle mouse move to extend selection."""
        if self._selection_start is not None:
            self._selection_end = event.pos()
            self._update_selection()
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Handle mouse release to finalize selection."""
        if event.button() == Qt.MouseButton.LeftButton:
            if self._selection_start is not None:
                self._selection_end = event.pos()
                self._update_selection()
                self.update()

                # Emit selected text
                selected_text = self.get_selected_text()
                if selected_text:
                    self.text_selected.emit(selected_text)
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Handle double-click to select word."""
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.pos()
            # Find the text block at this position
            for block in self._text_blocks:
                scaled_rect = self._scale_rect(block.rect)
                if scaled_rect.contains(pos):
                    self._selected_blocks = [block]
                    self.update()
                    self.text_selected.emit(block.text)
                    break
        super().mouseDoubleClickEvent(event)

    def _scale_rect(self, rect: QRectF) -> QRect:
        """Scale a rect from page coordinates to widget coordinates."""
        return QRect(
            int(rect.x() * self._scale_factor),
            int(rect.y() * self._scale_factor),
            int(rect.width() * self._scale_factor),
            int(rect.height() * self._scale_factor)
        )

    def _update_selection(self) -> None:
        """Update selected blocks based on selection rectangle."""
        if self._selection_start is None or self._selection_end is None:
            return

        # Create selection rectangle
        x1 = min(self._selection_start.x(), self._selection_end.x())
        y1 = min(self._selection_start.y(), self._selection_end.y())
        x2 = max(self._selection_start.x(), self._selection_end.x())
        y2 = max(self._selection_start.y(), self._selection_end.y())
        selection_rect = QRect(x1, y1, x2 - x1, y2 - y1)

        # Find intersecting text blocks
        self._selected_blocks = []
        for block in self._text_blocks:
            scaled_rect = self._scale_rect(block.rect)
            if selection_rect.intersects(scaled_rect):
                self._selected_blocks.append(block)

    def get_selected_text(self) -> str:
        """
        Get the currently selected text.

        Returns:
            Selected text string with proper whitespace
        """
        if not self._selected_blocks:
            return ""

        # Sort blocks by line number then horizontal position
        sorted_blocks = sorted(
            self._selected_blocks,
            key=lambda b: (b.line_num, b.rect.x())
        )

        # Group by line and join with appropriate whitespace
        lines: List[List[str]] = []
        current_line: List[str] = []
        current_line_num = -1

        for block in sorted_blocks:
            if block.line_num != current_line_num:
                if current_line:
                    lines.append(current_line)
                current_line = [block.text]
                current_line_num = block.line_num
            else:
                current_line.append(block.text)

        if current_line:
            lines.append(current_line)

        # Join words within lines with space, lines with newline
        return "\n".join(" ".join(words) for words in lines)

    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint the page with selection highlighting."""
        super().paintEvent(event)

        if not self._selected_blocks:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw selection highlight
        highlight_color = QColor(51, 153, 255, 100)  # Semi-transparent blue
        painter.setBrush(QBrush(highlight_color))
        painter.setPen(Qt.PenStyle.NoPen)

        for block in self._selected_blocks:
            scaled_rect = self._scale_rect(block.rect)
            painter.drawRect(scaled_rect)

        painter.end()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle keyboard shortcuts."""
        if event.matches(QKeyEvent.StandardKey.Copy):
            self._copy_selection()
        elif event.matches(QKeyEvent.StandardKey.SelectAll):
            self._select_all()
        else:
            super().keyPressEvent(event)

    def _copy_selection(self) -> None:
        """Copy selected text to clipboard."""
        text = self.get_selected_text()
        if text:
            QApplication.clipboard().setText(text)

    def _select_all(self) -> None:
        """Select all text on this page."""
        self._selected_blocks = self._text_blocks.copy()
        self.update()
        selected_text = self.get_selected_text()
        if selected_text:
            self.text_selected.emit(selected_text)

    def _show_context_menu(self, pos: QPoint) -> None:
        """Show context menu with copy option."""
        menu = QMenu(self)

        copy_action = QAction("Copy", self)
        copy_action.setShortcut("Ctrl+C")
        copy_action.triggered.connect(self._copy_selection)
        copy_action.setEnabled(bool(self._selected_blocks))
        menu.addAction(copy_action)

        select_all_action = QAction("Select All", self)
        select_all_action.setShortcut("Ctrl+A")
        select_all_action.triggered.connect(self._select_all)
        menu.addAction(select_all_action)

        menu.exec(self.mapToGlobal(pos))


class PDFTextViewerWidget(QWidget):
    """
    PDF viewer widget with full text selection support.

    Uses PyMuPDF (fitz) for rendering and text extraction, providing
    text selection and copy functionality. Supports seamless multi-page
    scrolling and fit-to-width zoom mode.
    """

    page_changed = Signal(int)  # Emits current page number (1-indexed)
    text_selected = Signal(str)  # Emits selected text

    # Zoom level constants
    ZOOM_MIN = 0.5
    ZOOM_MAX = 3.0
    ZOOM_STEP = 0.25
    ZOOM_DEFAULT = 1.0  # Will be overridden by fit-width calculation
    DPI_BASE = 72  # PDF base DPI
    DPI_RENDER = 150  # Render DPI for better quality

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize PDF text viewer.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)

        self.scale = get_font_scale()
        self.pdf_path: Optional[Path] = None
        self.current_page: int = 0
        self.total_pages: int = 0
        self.zoom_level: float = self.ZOOM_DEFAULT
        self._fit_width_mode: bool = True  # Default to fit-width mode

        self._fitz_doc = None
        self._page_widgets: List[PDFPageWidget] = []
        self._has_fitz = False

        try:
            import fitz
            self._has_fitz = True
        except ImportError:
            logger.warning(
                "PyMuPDF not available - PDF text viewer requires PyMuPDF. "
                "Install with: pip install pymupdf"
            )

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        s = self.scale
        style_gen = StylesheetGenerator()

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
        self.page_spin.valueChanged.connect(self._on_page_spin_changed)
        nav_layout.addWidget(self.page_spin)

        self.page_label = QLabel("of 0")
        nav_layout.addWidget(self.page_label)

        self.next_btn = QPushButton("Next ▶")
        self.next_btn.clicked.connect(self._on_next_page)
        self.next_btn.setEnabled(False)
        nav_layout.addWidget(self.next_btn)

        nav_layout.addStretch()

        # Copy button
        self.copy_page_btn = QPushButton("Copy Page")
        self.copy_page_btn.setToolTip("Copy all text from current page")
        self.copy_page_btn.clicked.connect(self._copy_page_text)
        self.copy_page_btn.setEnabled(False)
        nav_layout.addWidget(self.copy_page_btn)

        btn_size = s['control_height_small']

        # Fit Width button
        self.fit_width_btn = QPushButton("Fit Width")
        self.fit_width_btn.setToolTip("Fit page to viewer width")
        self.fit_width_btn.clicked.connect(self._on_fit_width)
        nav_layout.addWidget(self.fit_width_btn)

        self.zoom_out_btn = QPushButton("−")
        self.zoom_out_btn.setFixedWidth(btn_size)
        self.zoom_out_btn.setToolTip("Zoom out")
        self.zoom_out_btn.clicked.connect(self._on_zoom_out)
        nav_layout.addWidget(self.zoom_out_btn)

        self.zoom_label = QLabel("Fit")
        self.zoom_label.setFixedWidth(btn_size * 2)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav_layout.addWidget(self.zoom_label)

        self.zoom_in_btn = QPushButton("+")
        self.zoom_in_btn.setFixedWidth(btn_size)
        self.zoom_in_btn.setToolTip("Zoom in")
        self.zoom_in_btn.clicked.connect(self._on_zoom_in)
        nav_layout.addWidget(self.zoom_in_btn)

        layout.addLayout(nav_layout)

        # Scroll area for page display
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Container for pages
        self.pages_container = QWidget()
        self.pages_layout = QVBoxLayout(self.pages_container)
        self.pages_layout.setContentsMargins(
            s['padding_medium'], s['padding_medium'],
            s['padding_medium'], s['padding_medium']
        )
        self.pages_layout.setSpacing(s['spacing_medium'])
        self.pages_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self.scroll_area.setWidget(self.pages_container)
        layout.addWidget(self.scroll_area)

        # Status bar
        self.status_label = QLabel("Select text with mouse, Ctrl+C to copy")
        self.status_label.setStyleSheet(
            style_gen.label_stylesheet(font_size_key='font_tiny', color='gray')
        )
        layout.addWidget(self.status_label)

    def load_pdf(self, pdf_path: str | Path) -> None:
        """
        Load a PDF file for viewing.

        Args:
            pdf_path: Path to PDF file
        """
        if not self._has_fitz:
            QMessageBox.critical(
                self,
                "Error",
                "PyMuPDF is required for PDF text selection.\n"
                "Install with: pip install pymupdf"
            )
            return

        self.pdf_path = Path(pdf_path)

        if not str(self.pdf_path).lower().endswith('.pdf'):
            logger.error("Not a PDF file: %s", pdf_path)
            QMessageBox.critical(self, "Error", f"Not a PDF file: {pdf_path}")
            return

        if not self.pdf_path.exists():
            logger.error("PDF file not found: %s", pdf_path)
            QMessageBox.critical(self, "Error", f"PDF file not found: {pdf_path}")
            return

        # Clear existing pages
        self._clear_pages()

        try:
            import fitz
            self._fitz_doc = fitz.open(str(self.pdf_path))
            self.total_pages = len(self._fitz_doc)
            self.current_page = 0

            # Update UI
            self.page_spin.setMaximum(self.total_pages)
            self.page_spin.setValue(1)
            self.page_label.setText(f"of {self.total_pages}")
            self.copy_page_btn.setEnabled(True)
            self._update_navigation_buttons()

            # Calculate fit-width zoom and render all pages
            self._fit_width_mode = True
            self._calculate_fit_width_zoom()
            self._render_all_pages()

            self.status_label.setText(
                f"Loaded: {self.pdf_path.name} ({self.total_pages} pages) - "
                "Select text with mouse, Ctrl+C to copy"
            )

        except Exception as e:
            logger.error("Failed to load PDF: %s - %s", pdf_path, e)
            QMessageBox.critical(self, "Error", f"Failed to load PDF:\n{e}")

    def _clear_pages(self) -> None:
        """Clear all page widgets."""
        for widget in self._page_widgets:
            self.pages_layout.removeWidget(widget)
            widget.deleteLater()
        self._page_widgets = []

    def _calculate_fit_width_zoom(self) -> None:
        """Calculate zoom level to fit page width to viewport."""
        if not self._fitz_doc or self.total_pages == 0:
            return

        # Get first page dimensions
        first_page = self._fitz_doc[0]
        page_rect = first_page.rect
        page_width = page_rect.width

        # Get scroll area viewport width (minus scrollbar and margins)
        viewport_width = self.scroll_area.viewport().width()
        margin = self.scale['padding_medium'] * 2  # Left + right margins
        scrollbar_width = 20  # Approximate scrollbar width
        available_width = viewport_width - margin - scrollbar_width

        if available_width <= 0:
            available_width = 600  # Fallback default

        # Calculate zoom to fit width
        # page_width * zoom * (DPI_RENDER / DPI_BASE) = available_width
        # zoom = available_width / (page_width * DPI_RENDER / DPI_BASE)
        dpi_scale = self.DPI_RENDER / self.DPI_BASE
        self.zoom_level = available_width / (page_width * dpi_scale)

        # Clamp to reasonable range
        self.zoom_level = max(self.ZOOM_MIN, min(self.zoom_level, self.ZOOM_MAX))

        # Update zoom label
        if self._fit_width_mode:
            self.zoom_label.setText("Fit")
        else:
            self.zoom_label.setText(f"{int(self.zoom_level * 100)}%")

    def _render_all_pages(self) -> None:
        """Render all pages for seamless scrolling."""
        if not self._fitz_doc:
            return

        import fitz

        # Clear existing pages
        self._clear_pages()

        # Calculate scale for rendering
        scale = self.zoom_level * (self.DPI_RENDER / self.DPI_BASE)
        matrix = fitz.Matrix(scale, scale)

        # Render all pages
        for page_num in range(self.total_pages):
            page = self._fitz_doc[page_num]

            # Render page to pixmap
            pix = page.get_pixmap(matrix=matrix)

            # Convert to QImage
            if pix.alpha:
                image = QImage(
                    pix.samples, pix.width, pix.height,
                    pix.stride, QImage.Format.Format_RGBA8888
                )
            else:
                image = QImage(
                    pix.samples, pix.width, pix.height,
                    pix.stride, QImage.Format.Format_RGB888
                )

            pixmap = QPixmap.fromImage(image)

            # Extract text blocks with positions
            text_blocks = self._extract_text_blocks(page, page_num)

            # Create page widget
            page_widget = PDFPageWidget(page_num, self.pages_container)
            page_widget.set_page_data(pixmap, text_blocks, scale)
            page_widget.text_selected.connect(self._on_text_selected)

            self._page_widgets.append(page_widget)
            self.pages_layout.addWidget(page_widget)

        # Set focus to first page
        if self._page_widgets:
            self._page_widgets[0].setFocus()

        self.page_changed.emit(1)

    def _extract_text_blocks(
        self,
        page,
        page_num: int
    ) -> List[TextBlock]:
        """
        Extract text blocks with positions from a page.

        Extracts individual words with their bounding boxes for accurate
        text selection and proper whitespace handling.

        Args:
            page: PyMuPDF page object
            page_num: Page number

        Returns:
            List of TextBlock objects
        """
        blocks = []

        try:
            # Get word-level text with positions for proper spacing
            # words format: (x0, y0, x1, y1, "word", block_no, line_no, word_no)
            words = page.get_text("words")

            for word_data in words:
                if len(word_data) >= 7:
                    x0, y0, x1, y1 = word_data[:4]
                    text = str(word_data[4]).strip()
                    line_no = word_data[6]  # Line number for grouping

                    if text:
                        rect = QRectF(x0, y0, x1 - x0, y1 - y0)
                        blocks.append(TextBlock(text, rect, page_num, line_no))

        except Exception as e:
            logger.error("Error extracting text blocks: %s", e)

        return blocks

    def _on_text_selected(self, text: str) -> None:
        """Handle text selection from page widget."""
        word_count = len(text.split())
        self.status_label.setText(
            f"Selected {word_count} word(s) - Ctrl+C to copy"
        )
        self.text_selected.emit(text)

    def _on_previous_page(self) -> None:
        """Navigate to previous page by scrolling."""
        if self.current_page > 0:
            self.current_page -= 1
            self.page_spin.setValue(self.current_page + 1)
            self._scroll_to_page(self.current_page)
            self._update_navigation_buttons()

    def _on_next_page(self) -> None:
        """Navigate to next page by scrolling."""
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.page_spin.setValue(self.current_page + 1)
            self._scroll_to_page(self.current_page)
            self._update_navigation_buttons()

    def _on_page_spin_changed(self, page_num: int) -> None:
        """Handle page spin box change."""
        if self.total_pages == 0:
            return

        new_page = page_num - 1
        if 0 <= new_page < self.total_pages and new_page != self.current_page:
            self.current_page = new_page
            self._scroll_to_page(self.current_page)
            self._update_navigation_buttons()

    def _scroll_to_page(self, page_num: int) -> None:
        """Scroll to show a specific page."""
        if 0 <= page_num < len(self._page_widgets):
            widget = self._page_widgets[page_num]
            self.scroll_area.ensureWidgetVisible(widget, 0, 50)
            self.page_changed.emit(page_num + 1)

    def _on_fit_width(self) -> None:
        """Reset zoom to fit-to-width mode."""
        self._fit_width_mode = True
        self._calculate_fit_width_zoom()
        self._render_all_pages()
        self.status_label.setText("Zoom: Fit to Width")

    def _on_zoom_in(self) -> None:
        """Increase zoom level."""
        self._fit_width_mode = False
        self.zoom_level = min(self.zoom_level + self.ZOOM_STEP, self.ZOOM_MAX)
        self.zoom_label.setText(f"{int(self.zoom_level * 100)}%")
        self._render_all_pages()

    def _on_zoom_out(self) -> None:
        """Decrease zoom level."""
        self._fit_width_mode = False
        self.zoom_level = max(self.zoom_level - self.ZOOM_STEP, self.ZOOM_MIN)
        self.zoom_label.setText(f"{int(self.zoom_level * 100)}%")
        self._render_all_pages()

    def _update_navigation_buttons(self) -> None:
        """Update navigation button states."""
        self.prev_btn.setEnabled(self.current_page > 0)
        self.next_btn.setEnabled(self.current_page < self.total_pages - 1)

    def _copy_page_text(self) -> None:
        """Copy all text from the current page to clipboard."""
        if not self._fitz_doc or self.current_page >= self.total_pages:
            return

        try:
            page = self._fitz_doc[self.current_page]
            text = page.get_text()
            if text:
                QApplication.clipboard().setText(text)
                self.status_label.setText(
                    f"Copied page {self.current_page + 1} text to clipboard"
                )
        except Exception as e:
            logger.error("Error copying page text: %s", e)

    def get_all_text(self) -> str:
        """
        Extract all text from the PDF.

        Returns:
            All text from all pages
        """
        if not self._fitz_doc:
            return ""

        try:
            text_parts = []
            for page_num in range(len(self._fitz_doc)):
                page = self._fitz_doc[page_num]
                text_parts.append(page.get_text())
            return '\n\n'.join(text_parts)
        except Exception as e:
            logger.error("Error extracting text: %s", e)
            return ""

    def get_current_page_text(self) -> str:
        """
        Get text from the current page.

        Returns:
            Text from current page
        """
        if not self._fitz_doc or self.current_page >= self.total_pages:
            return ""

        try:
            page = self._fitz_doc[self.current_page]
            return page.get_text()
        except Exception as e:
            logger.error("Error getting page text: %s", e)
            return ""

    def clear(self) -> None:
        """Clear the viewer."""
        self._clear_pages()

        if self._fitz_doc:
            self._fitz_doc.close()
            self._fitz_doc = None

        self.pdf_path = None
        self.current_page = 0
        self.total_pages = 0
        self.zoom_level = self.ZOOM_DEFAULT
        self._fit_width_mode = True  # Reset to fit-width mode

        self.page_spin.setMaximum(1)
        self.page_spin.setValue(1)
        self.page_label.setText("of 0")
        self.zoom_label.setText("Fit")  # Reset to fit-width display
        self.copy_page_btn.setEnabled(False)
        self.status_label.setText("Select text with mouse, Ctrl+C to copy")
        self._update_navigation_buttons()
