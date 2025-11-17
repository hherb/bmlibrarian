"""
Flet implementation of the document card factory.

This module provides a Flet-specific implementation of the DocumentCardFactoryBase,
wrapping the existing UnifiedDocumentCard class and providing the standardized
factory interface.
"""

import flet as ft
from typing import Optional, Callable, Dict, Any, List
from pathlib import Path
import logging

from .document_card_factory_base import (
    DocumentCardFactoryBase,
    DocumentCardData,
    PDFButtonConfig,
    PDFButtonState,
    CardContext
)
from .unified_document_card import UnifiedDocumentCard, DocumentCardContext

logger = logging.getLogger(__name__)


class FletDocumentCardFactory(DocumentCardFactoryBase):
    """
    Flet-specific document card factory.

    This class wraps the existing UnifiedDocumentCard implementation and provides
    the standardized factory interface for creating document cards in Flet applications.
    """

    def __init__(
        self,
        page: ft.Page,
        pdf_manager=None,
        on_pdf_status_change: Optional[Callable[[int, str], None]] = None,
        base_pdf_dir: Optional[Path] = None
    ):
        """
        Initialize Flet document card factory.

        Args:
            page: Flet page instance for dialogs
            pdf_manager: PDFManager instance for handling PDF operations
            on_pdf_status_change: Callback when PDF status changes (doc_id, status)
            base_pdf_dir: Base directory for PDF files
        """
        super().__init__(base_pdf_dir)
        self.page = page
        self.pdf_manager = pdf_manager
        self.on_pdf_status_change = on_pdf_status_change

        # Create the underlying UnifiedDocumentCard instance
        self._card_creator = UnifiedDocumentCard(
            page=page,
            pdf_manager=pdf_manager,
            on_pdf_status_change=on_pdf_status_change
        )

    def create_card(self, card_data: DocumentCardData) -> ft.ExpansionTile:
        """
        Create a Flet document card.

        Args:
            card_data: Data and configuration for the card

        Returns:
            ft.ExpansionTile widget for the document
        """
        # Convert CardContext to DocumentCardContext
        context_mapping = {
            CardContext.LITERATURE: DocumentCardContext.LITERATURE,
            CardContext.SCORING: DocumentCardContext.SCORING,
            CardContext.CITATIONS: DocumentCardContext.CITATIONS,
            CardContext.COUNTERFACTUAL: DocumentCardContext.COUNTERFACTUAL,
            CardContext.REPORT: DocumentCardContext.REPORT,
            CardContext.SEARCH: DocumentCardContext.LITERATURE,
            CardContext.REVIEW: DocumentCardContext.LITERATURE
        }
        flet_context = context_mapping.get(card_data.context, DocumentCardContext.LITERATURE)

        # Prepare document dictionary for UnifiedDocumentCard
        doc = {
            'id': card_data.doc_id,
            'document_id': card_data.doc_id,
            'title': card_data.title,
            'abstract': card_data.abstract or "No abstract available",
            'authors': self.format_authors(card_data.authors) if card_data.authors else "Unknown authors",
            'publication': card_data.journal or "Unknown",
            'year': card_data.year,
            'pmid': card_data.pmid,
            'doi': card_data.doi,
            'source': card_data.source
        }

        # Add PDF information if available
        pdf_path = self.get_pdf_path(card_data.doc_id, card_data.pdf_path)
        if pdf_path:
            doc['pdf_path'] = str(pdf_path)
        if card_data.pdf_url:
            doc['pdf_url'] = card_data.pdf_url

        # Determine which score to use
        ai_score = None
        human_score = None
        relevance_score = None

        if card_data.context == CardContext.SCORING:
            ai_score = card_data.relevance_score
            human_score = card_data.human_score
        elif card_data.context == CardContext.CITATIONS:
            relevance_score = card_data.relevance_score
        else:
            ai_score = card_data.relevance_score

        # Create the card using UnifiedDocumentCard
        return self._card_creator.create_card(
            index=0,  # Index not used in factory pattern
            doc=doc,
            context=flet_context,
            ai_score=ai_score,
            human_score=human_score,
            relevance_score=relevance_score,
            citation_data={'citations': card_data.citations} if card_data.citations else None,
            on_score_change=card_data.on_score_change,
            show_scoring_controls=(card_data.context == CardContext.SCORING)
        )

    def create_pdf_button(self, config: PDFButtonConfig) -> ft.Container:
        """
        Create a Flet PDF button widget.

        Args:
            config: Configuration for the PDF button

        Returns:
            ft.Container with the appropriate button
        """
        if config.state == PDFButtonState.HIDDEN:
            return ft.Container()

        # Create button based on state
        if config.state == PDFButtonState.VIEW:
            button = ft.ElevatedButton(
                "📄 View Full Text",
                icon=ft.Icons.PICTURE_AS_PDF,
                on_click=lambda e: self._handle_view(config),
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.BLUE_600,
                    color=ft.Colors.WHITE
                ),
                height=40
            )
        elif config.state == PDFButtonState.FETCH:
            button = ft.ElevatedButton(
                "⬇️ Fetch Full Text",
                icon=ft.Icons.DOWNLOAD,
                on_click=lambda e: self._handle_fetch(config, button),
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.ORANGE_600,
                    color=ft.Colors.WHITE
                ),
                height=40
            )
        else:  # UPLOAD
            button = ft.ElevatedButton(
                "📤 Upload Full Text",
                icon=ft.Icons.UPLOAD_FILE,
                on_click=lambda e: self._handle_upload(config, button),
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.GREEN_600,
                    color=ft.Colors.WHITE
                ),
                height=40
            )

        return ft.Container(
            content=ft.Row([button], alignment=ft.MainAxisAlignment.START),
            padding=ft.padding.only(top=8)
        )

    def _handle_view(self, config: PDFButtonConfig):
        """Handle view PDF action."""
        if config.on_view:
            config.on_view()
        elif config.pdf_path and config.pdf_path.exists():
            # Default behavior: open in PDF viewer
            from .pdf_viewer_dialog import PDFViewerDialog
            viewer = PDFViewerDialog(self.page)
            doc = {'pdf_path': str(config.pdf_path)}
            viewer.show_pdf(config.pdf_path, doc)
        else:
            self._show_notification("PDF file not found", is_error=True)

    def _handle_fetch(self, config: PDFButtonConfig, button: ft.ElevatedButton):
        """Handle fetch PDF action."""
        if config.on_fetch:
            # Call custom handler
            success = config.on_fetch()
            if success and config.show_notifications:
                self._show_notification("PDF downloaded successfully")
                # Update button to View state
                button.text = "📄 View Full Text"
                button.icon = ft.Icons.PICTURE_AS_PDF
                button.on_click = lambda _: self._handle_view(config)
                button.style = ft.ButtonStyle(
                    bgcolor=ft.Colors.BLUE_600,
                    color=ft.Colors.WHITE
                )
                self.page.update()
        elif config.pdf_url:
            # Default behavior: download from URL
            from .pdf_viewer_dialog import PDFViewerDialog
            viewer = PDFViewerDialog(self.page)
            doc = {'pdf_url': config.pdf_url, 'id': 'unknown'}
            viewer.download_and_show_pdf(
                doc,
                on_success=lambda path: self._on_pdf_success(path, button, config),
                on_error=lambda msg: self._show_notification(msg, is_error=True)
            )
        else:
            self._show_notification("No PDF URL available", is_error=True)

    def _handle_upload(self, config: PDFButtonConfig, button: ft.ElevatedButton):
        """Handle upload PDF action."""
        if config.on_upload:
            # Call custom handler
            success = config.on_upload()
            if success and config.show_notifications:
                self._show_notification("PDF uploaded successfully")
                # Update button to View state
                button.text = "📄 View Full Text"
                button.icon = ft.Icons.PICTURE_AS_PDF
                button.on_click = lambda _: self._handle_view(config)
                button.style = ft.ButtonStyle(
                    bgcolor=ft.Colors.BLUE_600,
                    color=ft.Colors.WHITE
                )
                self.page.update()
        else:
            # Default behavior: show file picker
            from .pdf_viewer_dialog import PDFViewerDialog
            viewer = PDFViewerDialog(self.page)
            doc = {'id': 'unknown'}
            viewer.import_pdf(
                doc,
                on_success=lambda path: self._on_pdf_success(path, button, config),
                on_error=lambda msg: self._show_notification(msg, is_error=True)
            )

    def _on_pdf_success(self, pdf_path: Path, button: ft.ElevatedButton, config: PDFButtonConfig):
        """Handle successful PDF download/upload."""
        logger.info(f"PDF operation successful: {pdf_path}")

        # Update config
        config.pdf_path = pdf_path
        config.state = PDFButtonState.VIEW

        # Update button
        button.text = "📄 View Full Text"
        button.icon = ft.Icons.PICTURE_AS_PDF
        button.on_click = lambda _: self._handle_view(config)
        button.style = ft.ButtonStyle(
            bgcolor=ft.Colors.BLUE_600,
            color=ft.Colors.WHITE
        )

        if config.show_notifications:
            self._show_notification("✅ PDF ready! Click 'View Full Text' to open it.")

        self.page.update()

    def _show_notification(self, message: str, is_error: bool = False):
        """Show notification snackbar."""
        if not self.page:
            return

        snack_bar = ft.SnackBar(
            content=ft.Text(message),
            bgcolor=ft.Colors.RED_700 if is_error else ft.Colors.GREEN_700,
            duration=5000
        )
        self.page.open(snack_bar)
