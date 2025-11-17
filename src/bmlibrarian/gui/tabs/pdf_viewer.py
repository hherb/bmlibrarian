"""
PDF Viewer Component with Search and Highlighting

Provides PDF rendering, navigation, search, and programmatic highlighting
capabilities using PyMuPDF (fitz).
"""

import flet as ft
from typing import Optional, List, Tuple, Callable
from pathlib import Path
import base64
import io

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False


class HighlightRegion:
    """Represents a highlighted region in the PDF."""

    def __init__(self, page_num: int, rect: Tuple[float, float, float, float],
                 color: Tuple[int, int, int] = (255, 255, 0), alpha: int = 64,
                 label: str = ""):
        """
        Create a highlight region.

        Args:
            page_num: Page number (0-indexed)
            rect: Rectangle (x0, y0, x1, y1) in PDF coordinates
            color: RGB color tuple (0-255 range)
            alpha: Transparency (0-255, lower is more transparent)
            label: Optional label for this highlight
        """
        self.page_num = page_num
        self.rect = rect
        self.color = color
        self.alpha = alpha
        self.label = label


class PDFViewer:
    """
    Interactive PDF viewer with search and highlighting capabilities.

    Features:
    - Page rendering as images
    - Navigation controls (previous/next, jump to page)
    - Zoom controls
    - Text search with highlighting
    - Programmatic highlighting API for citations
    """

    def __init__(self, page: ft.Page, on_page_change: Optional[Callable] = None):
        """
        Initialize PDF viewer.

        Args:
            page: Flet page for UI updates
            on_page_change: Optional callback when page changes
        """
        self.page = page
        self.on_page_change = on_page_change

        # PDF state
        self.pdf_document: Optional[fitz.Document] = None
        self.current_page_num = 0
        self.total_pages = 0
        self.zoom_level = 1.0
        self.highlights: List[HighlightRegion] = []
        self.search_results: List[Tuple[int, fitz.Rect]] = []  # (page_num, rect)
        self.current_search_index = 0

        # UI components
        self.page_image = None
        self.page_number_field = None
        self.total_pages_text = None
        self.zoom_text = None
        self.search_field = None
        self.search_results_text = None
        self.controls_container = None
        self.image_container = None

    def build(self) -> ft.Container:
        """Build the PDF viewer UI."""

        if not PYMUPDF_AVAILABLE:
            return self._build_error_view("PyMuPDF not installed. Run: pip install PyMuPDF")

        # Page navigation controls
        nav_controls = self._build_navigation_controls()

        # Search controls
        search_controls = self._build_search_controls()

        # Zoom controls
        zoom_controls = self._build_zoom_controls()

        # Controls container (top toolbar)
        self.controls_container = ft.Container(
            content=ft.Column([
                ft.Row([
                    nav_controls,
                    ft.VerticalDivider(width=1),
                    zoom_controls,
                ],
                alignment=ft.MainAxisAlignment.START,
                spacing=15
                ),
                search_controls
            ],
            spacing=10
            ),
            padding=ft.padding.all(10),
            bgcolor=ft.Colors.GREY_100,
            border=ft.border.only(bottom=ft.BorderSide(1, ft.Colors.GREY_400))
        )

        # Page image display
        self.page_image = ft.Image(
            fit=ft.ImageFit.CONTAIN,
            width=None,
            height=None
        )

        self.image_container = ft.Container(
            content=self.page_image,
            bgcolor=ft.Colors.GREY_300,
            expand=True,
            alignment=ft.alignment.center,
            padding=ft.padding.all(10)
        )

        return ft.Column([
            self.controls_container,
            self.image_container
        ],
        spacing=0,
        expand=True
        )

    def _build_navigation_controls(self) -> ft.Row:
        """Build page navigation controls."""

        # Previous page button
        prev_button = ft.IconButton(
            icon=ft.Icons.NAVIGATE_BEFORE,
            tooltip="Previous page",
            on_click=self._on_prev_page,
            icon_color=ft.Colors.BLUE_600
        )

        # Page number input
        self.page_number_field = ft.TextField(
            value="1",
            width=60,
            height=40,
            text_align=ft.TextAlign.CENTER,
            on_submit=self._on_page_jump,
            border_color=ft.Colors.BLUE_400
        )

        # Total pages text
        self.total_pages_text = ft.Text(
            "/ 0",
            size=14,
            color=ft.Colors.GREY_700
        )

        # Next page button
        next_button = ft.IconButton(
            icon=ft.Icons.NAVIGATE_NEXT,
            tooltip="Next page",
            on_click=self._on_next_page,
            icon_color=ft.Colors.BLUE_600
        )

        return ft.Row([
            ft.Text("Page:", size=14, weight=ft.FontWeight.BOLD),
            prev_button,
            self.page_number_field,
            self.total_pages_text,
            next_button
        ],
        spacing=5,
        vertical_alignment=ft.CrossAxisAlignment.CENTER
        )

    def _build_zoom_controls(self) -> ft.Row:
        """Build zoom controls."""

        zoom_out_button = ft.IconButton(
            icon=ft.Icons.ZOOM_OUT,
            tooltip="Zoom out",
            on_click=lambda _: self._on_zoom(-0.1),
            icon_color=ft.Colors.BLUE_600
        )

        self.zoom_text = ft.Text(
            "100%",
            size=14,
            weight=ft.FontWeight.BOLD,
            width=60,
            text_align=ft.TextAlign.CENTER
        )

        zoom_in_button = ft.IconButton(
            icon=ft.Icons.ZOOM_IN,
            tooltip="Zoom in",
            on_click=lambda _: self._on_zoom(0.1),
            icon_color=ft.Colors.BLUE_600
        )

        zoom_reset_button = ft.IconButton(
            icon=ft.Icons.FIT_SCREEN,
            tooltip="Reset zoom",
            on_click=lambda _: self._on_zoom_reset(),
            icon_color=ft.Colors.BLUE_600
        )

        return ft.Row([
            ft.Text("Zoom:", size=14, weight=ft.FontWeight.BOLD),
            zoom_out_button,
            self.zoom_text,
            zoom_in_button,
            zoom_reset_button
        ],
        spacing=5,
        vertical_alignment=ft.CrossAxisAlignment.CENTER
        )

    def _build_search_controls(self) -> ft.Row:
        """Build search controls."""

        self.search_field = ft.TextField(
            hint_text="Search in PDF...",
            width=300,
            height=40,
            on_submit=self._on_search,
            border_color=ft.Colors.BLUE_400
        )

        search_button = ft.IconButton(
            icon=ft.Icons.SEARCH,
            tooltip="Search",
            on_click=self._on_search,
            icon_color=ft.Colors.BLUE_600
        )

        prev_result_button = ft.IconButton(
            icon=ft.Icons.ARROW_UPWARD,
            tooltip="Previous result",
            on_click=self._on_prev_search_result,
            icon_color=ft.Colors.BLUE_600
        )

        next_result_button = ft.IconButton(
            icon=ft.Icons.ARROW_DOWNWARD,
            tooltip="Next result",
            on_click=self._on_next_search_result,
            icon_color=ft.Colors.BLUE_600
        )

        self.search_results_text = ft.Text(
            "",
            size=12,
            color=ft.Colors.GREY_700,
            width=120
        )

        clear_search_button = ft.IconButton(
            icon=ft.Icons.CLEAR,
            tooltip="Clear search",
            on_click=self._on_clear_search,
            icon_color=ft.Colors.ORANGE_600
        )

        return ft.Row([
            self.search_field,
            search_button,
            prev_result_button,
            next_result_button,
            self.search_results_text,
            clear_search_button
        ],
        spacing=5,
        vertical_alignment=ft.CrossAxisAlignment.CENTER
        )

    def _build_error_view(self, error_msg: str) -> ft.Container:
        """Build error view when PDF cannot be displayed."""
        return ft.Container(
            content=ft.Column([
                ft.Icon(ft.Icons.ERROR_OUTLINE, size=80, color=ft.Colors.RED_400),
                ft.Text(
                    "PDF Viewer Error",
                    size=16,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.RED_700
                ),
                ft.Text(
                    error_msg,
                    size=12,
                    color=ft.Colors.GREY_600,
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

    def load_pdf(self, file_path: str):
        """
        Load a PDF document.

        Args:
            file_path: Path to PDF file
        """
        try:
            if not PYMUPDF_AVAILABLE:
                raise Exception("PyMuPDF is not installed")

            # Open PDF document
            self.pdf_document = fitz.open(file_path)
            self.total_pages = len(self.pdf_document)
            self.current_page_num = 0
            self.highlights = []
            self.search_results = []
            self.current_search_index = 0

            # Update UI
            self.total_pages_text.value = f"/ {self.total_pages}"
            self.page_number_field.value = "1"

            # Render first page
            self._render_current_page()

            if self.page:
                self.page.update()

        except Exception as ex:
            raise Exception(f"Failed to load PDF: {str(ex)}")

    def _render_current_page(self):
        """Render the current page with all highlights and search results."""
        if not self.pdf_document:
            return

        try:
            # Get current page
            page = self.pdf_document[self.current_page_num]

            # Calculate zoom matrix
            mat = fitz.Matrix(self.zoom_level, self.zoom_level)

            # Render page to pixmap
            pix = page.get_pixmap(matrix=mat, alpha=False)

            # Draw highlights on pixmap
            self._draw_highlights_on_pixmap(pix, page, mat)

            # Convert pixmap to PNG bytes
            img_bytes = pix.tobytes("png")

            # Convert to base64 for Flet
            img_base64 = base64.b64encode(img_bytes).decode()

            # Update image
            self.page_image.src_base64 = img_base64

            # Call page change callback
            if self.on_page_change:
                self.on_page_change(self.current_page_num, self.total_pages)

        except Exception as ex:
            print(f"Error rendering page: {ex}")

    def _draw_highlights_on_pixmap(self, pix: fitz.Pixmap, page: fitz.Page, mat: fitz.Matrix):
        """
        Draw all highlights (search results and custom highlights) on the pixmap.

        Args:
            pix: Pixmap to draw on
            page: PDF page object
            mat: Transformation matrix for zoom
        """
        # Create a temporary PDF page from pixmap for drawing
        # We'll use page annotations instead since pixmap drawing is limited

        # Draw search result highlights (yellow)
        for search_page_num, rect in self.search_results:
            if search_page_num == self.current_page_num:
                # Transform rectangle with zoom matrix
                highlight_rect = rect * mat
                # Add highlight annotation (this modifies the page temporarily for rendering)
                page.add_highlight_annot(rect)

        # Draw custom highlights
        for highlight in self.highlights:
            if highlight.page_num == self.current_page_num:
                rect = fitz.Rect(highlight.rect)
                page.add_highlight_annot(rect)

    def _on_prev_page(self, e):
        """Handle previous page button click."""
        if self.current_page_num > 0:
            self.current_page_num -= 1
            self.page_number_field.value = str(self.current_page_num + 1)
            self._render_current_page()
            if self.page:
                self.page.update()

    def _on_next_page(self, e):
        """Handle next page button click."""
        if self.current_page_num < self.total_pages - 1:
            self.current_page_num += 1
            self.page_number_field.value = str(self.current_page_num + 1)
            self._render_current_page()
            if self.page:
                self.page.update()

    def _on_page_jump(self, e):
        """Handle page number input."""
        try:
            page_num = int(self.page_number_field.value) - 1
            if 0 <= page_num < self.total_pages:
                self.current_page_num = page_num
                self._render_current_page()
                if self.page:
                    self.page.update()
            else:
                self.page_number_field.value = str(self.current_page_num + 1)
        except ValueError:
            self.page_number_field.value = str(self.current_page_num + 1)

    def _on_zoom(self, delta: float):
        """Handle zoom change."""
        new_zoom = self.zoom_level + delta
        new_zoom = max(0.5, min(3.0, new_zoom))  # Clamp between 50% and 300%
        self.zoom_level = new_zoom
        self.zoom_text.value = f"{int(self.zoom_level * 100)}%"
        self._render_current_page()
        if self.page:
            self.page.update()

    def _on_zoom_reset(self):
        """Reset zoom to 100%."""
        self.zoom_level = 1.0
        self.zoom_text.value = "100%"
        self._render_current_page()
        if self.page:
            self.page.update()

    def _on_search(self, e):
        """Handle search button click."""
        search_text = self.search_field.value

        if not search_text or not search_text.strip():
            return

        if not self.pdf_document:
            return

        # Clear previous search results
        self.search_results = []
        self.current_search_index = 0

        # Search all pages
        for page_num in range(self.total_pages):
            page = self.pdf_document[page_num]
            # Search for text (case-insensitive)
            text_instances = page.search_for(search_text)
            for rect in text_instances:
                self.search_results.append((page_num, rect))

        # Update search results display
        if self.search_results:
            self.search_results_text.value = f"{self.current_search_index + 1} / {len(self.search_results)}"
            # Jump to first result
            first_result_page = self.search_results[0][0]
            self.current_page_num = first_result_page
            self.page_number_field.value = str(first_result_page + 1)
            self._render_current_page()
        else:
            self.search_results_text.value = "No results"

        if self.page:
            self.page.update()

    def _on_prev_search_result(self, e):
        """Navigate to previous search result."""
        if not self.search_results:
            return

        self.current_search_index = (self.current_search_index - 1) % len(self.search_results)
        result_page = self.search_results[self.current_search_index][0]

        self.current_page_num = result_page
        self.page_number_field.value = str(result_page + 1)
        self.search_results_text.value = f"{self.current_search_index + 1} / {len(self.search_results)}"

        self._render_current_page()
        if self.page:
            self.page.update()

    def _on_next_search_result(self, e):
        """Navigate to next search result."""
        if not self.search_results:
            return

        self.current_search_index = (self.current_search_index + 1) % len(self.search_results)
        result_page = self.search_results[self.current_search_index][0]

        self.current_page_num = result_page
        self.page_number_field.value = str(result_page + 1)
        self.search_results_text.value = f"{self.current_search_index + 1} / {len(self.search_results)}"

        self._render_current_page()
        if self.page:
            self.page.update()

    def _on_clear_search(self, e):
        """Clear search results."""
        self.search_results = []
        self.current_search_index = 0
        self.search_field.value = ""
        self.search_results_text.value = ""
        self._render_current_page()
        if self.page:
            self.page.update()

    # Public API for programmatic control

    def add_highlight(self, page_num: int, rect: Tuple[float, float, float, float],
                     color: Tuple[int, int, int] = (255, 200, 0), label: str = ""):
        """
        Add a programmatic highlight to the PDF.

        Args:
            page_num: Page number (0-indexed)
            rect: Rectangle (x0, y0, x1, y1) in PDF coordinates
            color: RGB color tuple (default: orange)
            label: Optional label for this highlight

        Example:
            viewer.add_highlight(0, (100, 100, 300, 120), label="Citation 1")
        """
        highlight = HighlightRegion(page_num, rect, color, alpha=64, label=label)
        self.highlights.append(highlight)
        if self.current_page_num == page_num:
            self._render_current_page()
            if self.page:
                self.page.update()

    def clear_highlights(self):
        """Clear all programmatic highlights."""
        self.highlights = []
        self._render_current_page()
        if self.page:
            self.page.update()

    def search_and_highlight(self, text: str):
        """
        Search for text and automatically highlight all instances.

        Args:
            text: Text to search for

        Returns:
            Number of results found
        """
        self.search_field.value = text
        self._on_search(None)
        return len(self.search_results)

    def jump_to_page(self, page_num: int):
        """
        Jump to a specific page.

        Args:
            page_num: Page number (0-indexed)
        """
        if 0 <= page_num < self.total_pages:
            self.current_page_num = page_num
            self.page_number_field.value = str(page_num + 1)
            self._render_current_page()
            if self.page:
                self.page.update()

    def get_text_from_page(self, page_num: int) -> str:
        """
        Extract all text from a specific page.

        Args:
            page_num: Page number (0-indexed)

        Returns:
            Page text content
        """
        if not self.pdf_document or page_num >= self.total_pages:
            return ""

        page = self.pdf_document[page_num]
        return page.get_text()

    def get_all_text(self) -> str:
        """
        Extract all text from the entire PDF.

        Returns:
            Complete PDF text content
        """
        if not self.pdf_document:
            return ""

        full_text = []
        for page_num in range(self.total_pages):
            page_text = self.get_text_from_page(page_num)
            full_text.append(f"--- Page {page_num + 1} ---\n{page_text}\n")

        return "\n".join(full_text)

    def close(self):
        """Close the PDF document and free resources."""
        if self.pdf_document:
            self.pdf_document.close()
            self.pdf_document = None
            self.total_pages = 0
            self.current_page_num = 0
            self.highlights = []
            self.search_results = []
