"""
Document Display Factory - Reusable widget factory for tabbed document display

Provides a tabbed interface showing document abstract and full text (PDF or text).
This factory is used across multiple lab interfaces (PICO, PRISMA 2020, Study Assessment).
"""

import flet as ft
from pathlib import Path
from typing import Dict, Any, Optional
import os


class DocumentDisplayFactory:
    """Factory for creating tabbed document display widgets for Flet labs."""

    def __init__(self, page: ft.Page):
        """
        Initialize document display factory.

        Args:
            page: Flet page instance for updates
        """
        self.page = page

    def create_document_display(
        self,
        title_label: ft.Text,
        metadata_label: ft.Text,
        width: int = 500,
        title_size: int = 16,
        metadata_size: int = 12,
        abstract_height: int = 300
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
        - 'update_func': Function to update document display

        Args:
            title_label: Pre-configured title label widget
            metadata_label: Pre-configured metadata label widget
            width: Width of the document panel (default: 500)
            title_size: Font size for title (default: 16)
            metadata_size: Font size for metadata (default: 12)
            abstract_height: Height of abstract/fulltext containers (default: 300)

        Returns:
            Dictionary with widget references and update function
        """
        # Create tab content widgets
        abstract_text = ft.Text(
            "Load a document to view its abstract and full text.",
            size=13,
            color=ft.Colors.GREY_700
        )

        fulltext_text = ft.Text(
            "Full text not available for this document.",
            size=13,
            color=ft.Colors.GREY_700
        )

        # Create tabs
        tabs = ft.Tabs(
            selected_index=0,
            animation_duration=300,
            tabs=[
                ft.Tab(
                    text="Abstract",
                    content=ft.Container(
                        content=ft.Column(
                            [abstract_text],
                            spacing=5,
                            scroll=ft.ScrollMode.AUTO
                        ),
                        height=abstract_height,
                        padding=ft.padding.all(10),
                        bgcolor=ft.Colors.WHITE,
                        border_radius=5,
                        border=ft.border.all(1, ft.Colors.GREY_300)
                    )
                ),
                ft.Tab(
                    text="Full Text",
                    content=ft.Container(
                        content=ft.Column(
                            [fulltext_text],
                            spacing=5,
                            scroll=ft.ScrollMode.AUTO
                        ),
                        height=abstract_height,
                        padding=ft.padding.all(10),
                        bgcolor=ft.Colors.WHITE,
                        border_radius=5,
                        border=ft.border.all(1, ft.Colors.GREY_300)
                    )
                )
            ],
            expand=False
        )

        # Create main container
        container = ft.Column([
            ft.Text("Document", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_800),
            ft.Divider(),
            title_label,
            metadata_label,
            ft.Divider(),
            tabs
        ], spacing=10, scroll=ft.ScrollMode.AUTO)

        def update_document_display(document: Optional[Dict[str, Any]]):
            """
            Update the document display with new document data.

            Args:
                document: Document dictionary from database (or None to clear)
            """
            if not document:
                # Clear display
                title_label.value = "No document loaded"
                metadata_label.value = ""
                abstract_text.value = "Load a document to view its abstract and full text."
                fulltext_text.value = "Full text not available for this document."
                tabs.tabs[1].text = "Full Text"
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

            # Update full text
            fulltext_content = self._get_fulltext_content(document)
            if fulltext_content['available']:
                fulltext_text.value = fulltext_content['text']
                tabs.tabs[1].text = fulltext_content['tab_label']
            else:
                fulltext_text.value = "Full text not available for this document."
                tabs.tabs[1].text = "Full Text"

            self.page.update()

        return {
            'container': container,
            'title': title_label,
            'metadata': metadata_label,
            'tabs': tabs,
            'abstract_text': abstract_text,
            'fulltext_text': fulltext_text,
            'update_func': update_document_display
        }

    def _get_fulltext_content(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract full text content from document (PDF or text field).

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
                os.getenv('PDF_BASE_DIR', '~/knowledgebase/pdf')
            ))
            pdf_path = pdf_base_dir / pdf_filename

            if pdf_path.exists():
                try:
                    # Extract text from PDF using PyPDF2 or similar
                    pdf_text = self._extract_text_from_pdf(pdf_path)
                    if pdf_text:
                        return {
                            'available': True,
                            'text': pdf_text,
                            'tab_label': 'Full Text (PDF)'
                        }
                except Exception as e:
                    print(f"Warning: Failed to extract text from PDF {pdf_path}: {e}")

        # Check for text full_text field
        full_text = document.get('full_text')
        if full_text:
            return {
                'available': True,
                'text': full_text,
                'tab_label': 'Full Text'
            }

        # No full text available
        return {
            'available': False,
            'text': 'Full text not available for this document.',
            'tab_label': 'Full Text'
        }

    def _extract_text_from_pdf(self, pdf_path: Path) -> Optional[str]:
        """
        Extract text content from a PDF file.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Extracted text or None if extraction fails
        """
        try:
            # Try PyPDF2 first
            try:
                import PyPDF2
                with open(pdf_path, 'rb') as pdf_file:
                    pdf_reader = PyPDF2.PdfReader(pdf_file)
                    text_parts = []
                    for page in pdf_reader.pages:
                        text_parts.append(page.extract_text())
                    return '\n\n'.join(text_parts)
            except ImportError:
                pass

            # Try pdfplumber as fallback
            try:
                import pdfplumber
                with pdfplumber.open(pdf_path) as pdf:
                    text_parts = []
                    for page in pdf.pages:
                        text = page.extract_text()
                        if text:
                            text_parts.append(text)
                    return '\n\n'.join(text_parts)
            except ImportError:
                pass

            # If no PDF libraries available, return placeholder
            return f"[PDF file available at: {pdf_path}]\n\nPDF text extraction requires PyPDF2 or pdfplumber library.\nInstall with: pip install PyPDF2"

        except Exception as e:
            print(f"Error extracting text from PDF: {e}")
            return None


def create_document_display_simple(
    page: ft.Page,
    initial_title: str = "No document loaded",
    width: int = 500,
    abstract_height: int = 300
) -> Dict[str, Any]:
    """
    Convenience function to create a complete document display with default labels.

    Args:
        page: Flet page instance
        initial_title: Initial title text (default: "No document loaded")
        width: Width of document panel (default: 500)
        abstract_height: Height of content containers (default: 300)

    Returns:
        Dictionary with widget references and update function
    """
    factory = DocumentDisplayFactory(page)

    title_label = ft.Text(
        initial_title,
        size=16,
        weight=ft.FontWeight.BOLD,
        color=ft.Colors.GREY_700
    )

    metadata_label = ft.Text(
        "",
        size=12,
        color=ft.Colors.GREY_600
    )

    return factory.create_document_display(
        title_label=title_label,
        metadata_label=metadata_label,
        width=width,
        abstract_height=abstract_height
    )
