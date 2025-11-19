"""
Document Display Factory - Reusable widget factory for tabbed document display

Provides a tabbed interface showing document abstract and full text (PDF or text).
This factory is used across multiple lab interfaces (PICO, PRISMA 2020, Study Assessment).

The factory creates non-blocking document displays with async PDF text extraction
to prevent GUI freezes when loading large PDF files.
"""

import flet as ft
from pathlib import Path
from typing import Dict, Any, Optional, Callable
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor

# ============================================================================
# CONSTANTS - All dimensions and styling parameters
# ============================================================================

# Font sizes
FONT_SIZE_TINY = 11
FONT_SIZE_SMALL = 12
FONT_SIZE_NORMAL = 13
FONT_SIZE_MEDIUM = 14
FONT_SIZE_LARGE = 16
FONT_SIZE_XLARGE = 18

# Spacing and padding
SPACING_SMALL = 5
SPACING_MEDIUM = 10
SPACING_LARGE = 15

PADDING_SMALL = 5
PADDING_MEDIUM = 10
PADDING_LARGE = 15

# Container dimensions
DEFAULT_PANEL_WIDTH = 500
DEFAULT_ABSTRACT_HEIGHT = 300
MIN_ABSTRACT_HEIGHT = 200
MAX_ABSTRACT_HEIGHT = 600

# Border styling
BORDER_WIDTH = 1
BORDER_RADIUS = 5

# Colors (Flet color constants)
COLOR_GREY_50 = ft.Colors.GREY_50
COLOR_GREY_300 = ft.Colors.GREY_300
COLOR_GREY_600 = ft.Colors.GREY_600
COLOR_GREY_700 = ft.Colors.GREY_700
COLOR_GREY_800 = ft.Colors.GREY_800
COLOR_WHITE = ft.Colors.WHITE

# Tab configuration
TAB_ANIMATION_DURATION_MS = 300
TAB_INDEX_ABSTRACT = 0
TAB_INDEX_FULLTEXT = 1

# PDF extraction settings
PDF_EXTRACTION_TIMEOUT_SECONDS = 30
PDF_MAX_PAGES_PREVIEW = 100  # Limit pages to prevent extremely long extractions

# Text labels
LABEL_DOCUMENT = "Document"
LABEL_TAB_ABSTRACT = "Abstract"
LABEL_TAB_FULLTEXT = "Full Text"
LABEL_TAB_FULLTEXT_PDF = "Full Text (PDF)"
PLACEHOLDER_NO_DOCUMENT = "Load a document to view its abstract and full text."
PLACEHOLDER_NO_FULLTEXT = "Full text not available for this document."
PLACEHOLDER_PDF_EXTRACTING = "Extracting text from PDF..."
PLACEHOLDER_PDF_FAILED = "Failed to extract text from PDF. Please check if the PDF is readable."

# Environment variables
ENV_PDF_BASE_DIR = 'PDF_BASE_DIR'
DEFAULT_PDF_BASE_DIR = '~/knowledgebase/pdf'


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _extract_text_from_pdf_sync(pdf_path: Path) -> Optional[str]:
    """
    Synchronously extract text content from a PDF file.

    This function is designed to be run in a background thread to avoid
    blocking the GUI. It attempts to use PyPDF2 first, then pdfplumber
    as a fallback.

    Args:
        pdf_path: Path to PDF file

    Returns:
        Extracted text or None if extraction fails
    """
    try:
        # Try PyPDF2 first (faster)
        try:
            import PyPDF2
            with open(pdf_path, 'rb') as pdf_file:
                pdf_reader = PyPDF2.PdfReader(pdf_file)
                num_pages = min(len(pdf_reader.pages), PDF_MAX_PAGES_PREVIEW)
                text_parts = []
                for i in range(num_pages):
                    page_text = pdf_reader.pages[i].extract_text()
                    if page_text:
                        text_parts.append(page_text)

                result = '\n\n'.join(text_parts)
                if len(pdf_reader.pages) > PDF_MAX_PAGES_PREVIEW:
                    result += f"\n\n[Preview truncated - showing first {PDF_MAX_PAGES_PREVIEW} of {len(pdf_reader.pages)} pages]"
                return result if result.strip() else None
        except ImportError:
            pass

        # Try pdfplumber as fallback (more accurate but slower)
        try:
            import pdfplumber
            with pdfplumber.open(pdf_path) as pdf:
                num_pages = min(len(pdf.pages), PDF_MAX_PAGES_PREVIEW)
                text_parts = []
                for i in range(num_pages):
                    page_text = pdf.pages[i].extract_text()
                    if page_text:
                        text_parts.append(page_text)

                result = '\n\n'.join(text_parts)
                if len(pdf.pages) > PDF_MAX_PAGES_PREVIEW:
                    result += f"\n\n[Preview truncated - showing first {PDF_MAX_PAGES_PREVIEW} of {len(pdf.pages)} pages]"
                return result if result.strip() else None
        except ImportError:
            pass

        # If no PDF libraries available, return placeholder
        return (f"[PDF file available at: {pdf_path}]\n\n"
                f"PDF text extraction requires PyPDF2 or pdfplumber library.\n"
                f"Install with: pip install PyPDF2")

    except Exception as e:
        print(f"Error extracting text from PDF {pdf_path}: {e}")
        return None


# ============================================================================
# MAIN FACTORY CLASS
# ============================================================================

class DocumentDisplayFactory:
    """
    Factory for creating tabbed document display widgets for Flet labs.

    This factory creates non-blocking document displays with async PDF
    text extraction to prevent GUI freezes.
    """

    def __init__(self, page: ft.Page):
        """
        Initialize document display factory.

        Args:
            page: Flet page instance for updates
        """
        self.page = page
        self._executor = ThreadPoolExecutor(max_workers=2)

    def create_document_display(
        self,
        title_label: ft.Text,
        metadata_label: ft.Text,
        width: int = DEFAULT_PANEL_WIDTH,
        abstract_height: int = DEFAULT_ABSTRACT_HEIGHT
    ) -> Dict[str, Any]:
        """
        Create a tabbed document display widget with title, metadata, and content tabs.

        Returns a dictionary containing:
        - 'container': The main container widget to add to layouts
        - 'title': Reference to title label
        - 'metadata': Reference to metadata label
        - 'tabs': Reference to tabs widget
        - 'abstract_text': Reference to abstract text widget
        - 'fulltext_text': Reference to fulltext text widget
        - 'update_func': Async function to update document display
        - 'cleanup_func': Function to cleanup resources

        Args:
            title_label: Pre-configured title label widget
            metadata_label: Pre-configured metadata label widget
            width: Width of the document panel (default: from constants)
            abstract_height: Height of abstract/fulltext containers (default: from constants)

        Returns:
            Dictionary with widget references and update function
        """
        # Validate dimensions
        abstract_height = max(MIN_ABSTRACT_HEIGHT, min(abstract_height, MAX_ABSTRACT_HEIGHT))

        # Create tab content widgets
        abstract_text = ft.Text(
            PLACEHOLDER_NO_DOCUMENT,
            size=FONT_SIZE_NORMAL,
            color=COLOR_GREY_700
        )

        fulltext_text = ft.Text(
            PLACEHOLDER_NO_FULLTEXT,
            size=FONT_SIZE_NORMAL,
            color=COLOR_GREY_700
        )

        # Create tabs
        tabs = ft.Tabs(
            selected_index=TAB_INDEX_ABSTRACT,
            animation_duration=TAB_ANIMATION_DURATION_MS,
            tabs=[
                ft.Tab(
                    text=LABEL_TAB_ABSTRACT,
                    content=ft.Container(
                        content=ft.Column(
                            [abstract_text],
                            spacing=SPACING_SMALL,
                            scroll=ft.ScrollMode.AUTO
                        ),
                        height=abstract_height,
                        padding=ft.padding.all(PADDING_MEDIUM),
                        bgcolor=COLOR_WHITE,
                        border_radius=BORDER_RADIUS,
                        border=ft.border.all(BORDER_WIDTH, COLOR_GREY_300)
                    )
                ),
                ft.Tab(
                    text=LABEL_TAB_FULLTEXT,
                    content=ft.Container(
                        content=ft.Column(
                            [fulltext_text],
                            spacing=SPACING_SMALL,
                            scroll=ft.ScrollMode.AUTO
                        ),
                        height=abstract_height,
                        padding=ft.padding.all(PADDING_MEDIUM),
                        bgcolor=COLOR_WHITE,
                        border_radius=BORDER_RADIUS,
                        border=ft.border.all(BORDER_WIDTH, COLOR_GREY_300)
                    )
                )
            ],
            expand=False
        )

        # Create main container
        container = ft.Column([
            ft.Text(LABEL_DOCUMENT, size=FONT_SIZE_XLARGE, weight=ft.FontWeight.BOLD, color=COLOR_GREY_800),
            ft.Divider(),
            title_label,
            metadata_label,
            ft.Divider(),
            tabs
        ], spacing=SPACING_MEDIUM, scroll=ft.ScrollMode.AUTO)

        async def update_document_display_async(document: Optional[Dict[str, Any]]) -> None:
            """
            Asynchronously update the document display with new document data.

            This function extracts PDF text in a background thread to avoid
            blocking the GUI.

            Args:
                document: Document dictionary from database (or None to clear)
            """
            if not document:
                # Clear display
                title_label.value = "No document loaded"
                metadata_label.value = ""
                abstract_text.value = PLACEHOLDER_NO_DOCUMENT
                fulltext_text.value = PLACEHOLDER_NO_FULLTEXT
                tabs.tabs[TAB_INDEX_FULLTEXT].text = LABEL_TAB_FULLTEXT
                self.page.update()
                return

            # Update title
            title_label.value = document.get('title', 'No title')

            # Update metadata
            metadata_parts = []
            if document.get('year'):
                metadata_parts.append(f"Year: {document['year']}")
            if document.get('pmid'):
                metadata_parts.append(f"PMID: {document['pmid']}")
            if document.get('doi'):
                metadata_parts.append(f"DOI: {document['doi']}")
            if document.get('id'):
                metadata_parts.append(f"ID: {document['id']}")

            metadata_label.value = " | ".join(metadata_parts)

            # Update abstract
            abstract = document.get('abstract', 'No abstract available')
            abstract_text.value = abstract

            # Update full text (async for PDF extraction)
            fulltext_text.value = PLACEHOLDER_PDF_EXTRACTING
            self.page.update()

            fulltext_content = await self._get_fulltext_content_async(document)
            if fulltext_content['available']:
                fulltext_text.value = fulltext_content['text']
                tabs.tabs[TAB_INDEX_FULLTEXT].text = fulltext_content['tab_label']
            else:
                fulltext_text.value = PLACEHOLDER_NO_FULLTEXT
                tabs.tabs[TAB_INDEX_FULLTEXT].text = LABEL_TAB_FULLTEXT

            self.page.update()

        def cleanup() -> None:
            """Cleanup resources (shutdown thread pool)."""
            self._executor.shutdown(wait=False)

        def update_document_display_sync(document: Optional[Dict[str, Any]]) -> None:
            """
            Synchronously update the document display (wrapper for async version).

            This is a convenience wrapper that runs the async update function
            in a way that's compatible with synchronous Flet event handlers.

            Args:
                document: Document dictionary from database (or None to clear)
            """
            # Run the async function using asyncio
            import asyncio
            try:
                # Try to get existing event loop
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If loop is already running (in Flet), create task
                    asyncio.create_task(update_document_display_async(document))
                else:
                    # If no loop or not running, run until complete
                    loop.run_until_complete(update_document_display_async(document))
            except RuntimeError:
                # No event loop, create new one
                asyncio.run(update_document_display_async(document))

        return {
            'container': container,
            'title': title_label,
            'metadata': metadata_label,
            'tabs': tabs,
            'abstract_text': abstract_text,
            'fulltext_text': fulltext_text,
            'update_func': update_document_display_sync,  # Sync wrapper for easy use
            'update_func_async': update_document_display_async,  # Async version if needed
            'cleanup_func': cleanup
        }

    async def _get_fulltext_content_async(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """
        Asynchronously extract full text content from document (PDF or text field).

        PDF extraction runs in a background thread to prevent GUI blocking.

        Args:
            document: Document dictionary from database

        Returns:
            Dictionary with:
            - 'available': Boolean indicating if full text is available
            - 'text': Full text content string
            - 'tab_label': Label for the full text tab
        """
        # Check for PDF file first
        pdf_filename = document.get('pdf_filename')
        if pdf_filename:
            # Construct full path from PDF_BASE_DIR environment variable
            pdf_base_dir = Path(os.path.expanduser(
                os.getenv(ENV_PDF_BASE_DIR, DEFAULT_PDF_BASE_DIR)
            ))
            pdf_path = pdf_base_dir / pdf_filename

            if pdf_path.exists():
                try:
                    # Extract PDF text in background thread (non-blocking)
                    loop = asyncio.get_event_loop()
                    pdf_text = await asyncio.wait_for(
                        loop.run_in_executor(
                            self._executor,
                            _extract_text_from_pdf_sync,
                            pdf_path
                        ),
                        timeout=PDF_EXTRACTION_TIMEOUT_SECONDS
                    )

                    if pdf_text:
                        return {
                            'available': True,
                            'text': pdf_text,
                            'tab_label': LABEL_TAB_FULLTEXT_PDF
                        }
                except asyncio.TimeoutError:
                    print(f"Warning: PDF extraction timed out for {pdf_path}")
                    return {
                        'available': True,
                        'text': f"PDF extraction timed out after {PDF_EXTRACTION_TIMEOUT_SECONDS} seconds.\nThe PDF file may be too large or corrupted.",
                        'tab_label': LABEL_TAB_FULLTEXT_PDF
                    }
                except Exception as e:
                    print(f"Warning: Failed to extract text from PDF {pdf_path}: {e}")

        # Check for text full_text field
        full_text = document.get('full_text')
        if full_text:
            return {
                'available': True,
                'text': full_text,
                'tab_label': LABEL_TAB_FULLTEXT
            }

        # No full text available
        return {
            'available': False,
            'text': PLACEHOLDER_NO_FULLTEXT,
            'tab_label': LABEL_TAB_FULLTEXT
        }


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def create_document_display_simple(
    page: ft.Page,
    initial_title: str = "No document loaded",
    width: int = DEFAULT_PANEL_WIDTH,
    abstract_height: int = DEFAULT_ABSTRACT_HEIGHT
) -> Dict[str, Any]:
    """
    Convenience function to create a complete document display with default labels.

    Args:
        page: Flet page instance
        initial_title: Initial title text (default: "No document loaded")
        width: Width of document panel (default: from constants)
        abstract_height: Height of content containers (default: from constants)

    Returns:
        Dictionary with widget references, update function, and cleanup function
    """
    factory = DocumentDisplayFactory(page)

    title_label = ft.Text(
        initial_title,
        size=FONT_SIZE_LARGE,
        weight=ft.FontWeight.BOLD,
        color=COLOR_GREY_700
    )

    metadata_label = ft.Text(
        "",
        size=FONT_SIZE_SMALL,
        color=COLOR_GREY_600
    )

    return factory.create_document_display(
        title_label=title_label,
        metadata_label=metadata_label,
        width=width,
        abstract_height=abstract_height
    )
