"""
Qt implementation of the document card factory.

This module provides a Qt-specific implementation of the DocumentCardFactoryBase,
integrating with existing Qt document card classes and adding PDF button functionality
that matches the Flet implementation.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFrame, QLabel
)
from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QIcon, QDesktopServices
from PySide6.QtCore import QUrl
from typing import Optional, Callable, Dict, Any, Union
from pathlib import Path
import logging

from bmlibrarian.gui.document_card_factory_base import (
    DocumentCardFactoryBase,
    DocumentCardData,
    PDFButtonConfig,
    PDFButtonState,
    CardContext
)

logger = logging.getLogger(__name__)


class PDFButtonWidget(QPushButton):
    """
    Qt PDF button with three states: View, Fetch, Upload.

    Signals:
        pdf_viewed: Emitted when PDF is viewed
        pdf_fetched: Emitted when PDF is fetched (returns path)
        pdf_uploaded: Emitted when PDF is uploaded (returns path)
    """

    pdf_viewed = Signal()
    pdf_fetched = Signal(Path)
    pdf_uploaded = Signal(Path)

    def __init__(self, config: PDFButtonConfig, parent: Optional[QWidget] = None):
        """
        Initialize PDF button.

        Args:
            config: Button configuration
            parent: Optional parent widget
        """
        super().__init__(parent)
        self.config = config
        self._update_button_appearance()

        # Connect click handler
        self.clicked.connect(self._handle_click)

    def _update_button_appearance(self):
        """Update button text, icon, and style based on state."""
        if self.config.state == PDFButtonState.VIEW:
            self.setText("📄 View Full Text")
            self.setStyleSheet("""
                QPushButton {
                    background-color: #1976D2;
                    color: white;
                    border: none;
                    padding: 8px 12px;
                    border-radius: 4px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #1565C0;
                }
            """)
        elif self.config.state == PDFButtonState.FETCH:
            self.setText("⬇️ Fetch Full Text")
            self.setStyleSheet("""
                QPushButton {
                    background-color: #F57C00;
                    color: white;
                    border: none;
                    padding: 8px 12px;
                    border-radius: 4px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #EF6C00;
                }
            """)
        elif self.config.state == PDFButtonState.UPLOAD:
            self.setText("📤 Upload Full Text")
            self.setStyleSheet("""
                QPushButton {
                    background-color: #388E3C;
                    color: white;
                    border: none;
                    padding: 8px 12px;
                    border-radius: 4px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #2E7D32;
                }
            """)

        self.setMinimumHeight(40)
        self.setCursor(Qt.PointingHandCursor)

    def _handle_click(self):
        """Handle button click based on current state."""
        if self.config.state == PDFButtonState.VIEW:
            self._handle_view()
        elif self.config.state == PDFButtonState.FETCH:
            self._handle_fetch()
        elif self.config.state == PDFButtonState.UPLOAD:
            self._handle_upload()

    def _handle_view(self):
        """Handle view PDF action."""
        if self.config.on_view:
            self.config.on_view()
        elif self.config.pdf_path and self.config.pdf_path.exists():
            # Default behavior: open in system PDF viewer
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.config.pdf_path)))
        else:
            logger.error("PDF file not found")

        self.pdf_viewed.emit()

    def _handle_fetch(self):
        """Handle fetch PDF action."""
        if self.config.on_fetch:
            result = self.config.on_fetch()
            if result:
                # Callback should return the downloaded path
                if isinstance(result, Path):
                    self._transition_to_view(result)
                    self.pdf_fetched.emit(result)
        else:
            logger.warning("No fetch handler configured")

    def _handle_upload(self):
        """Handle upload PDF action."""
        if self.config.on_upload:
            result = self.config.on_upload()
            if result:
                # Callback should return the uploaded path
                if isinstance(result, Path):
                    self._transition_to_view(result)
                    self.pdf_uploaded.emit(result)
        else:
            # Default behavior: show file dialog
            from PySide6.QtWidgets import QFileDialog
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Upload PDF",
                str(Path.home()),
                "PDF Files (*.pdf)"
            )
            if file_path:
                path = Path(file_path)
                self._transition_to_view(path)
                self.pdf_uploaded.emit(path)

    def _transition_to_view(self, pdf_path: Path):
        """Transition button to VIEW state after successful fetch/upload."""
        self.config.pdf_path = pdf_path
        self.config.state = PDFButtonState.VIEW
        self._update_button_appearance()


class QtDocumentCardFactory(DocumentCardFactoryBase):
    """
    Qt-specific document card factory.

    This class provides Qt widgets for document cards with integrated PDF button
    functionality, matching the Flet implementation's three-state PDF buttons.
    """

    def __init__(
        self,
        pdf_manager=None,
        base_pdf_dir: Optional[Path] = None
    ):
        """
        Initialize Qt document card factory.

        Args:
            pdf_manager: PDFManager instance for handling PDF operations
            base_pdf_dir: Base directory for PDF files
        """
        super().__init__(base_pdf_dir)
        self.pdf_manager = pdf_manager

    def create_card(self, card_data: DocumentCardData) -> QFrame:
        """
        Create a Qt document card.

        Args:
            card_data: Data and configuration for the card

        Returns:
            QFrame widget for the document
        """
        from .widgets.collapsible_document_card import CollapsibleDocumentCard

        # Prepare document dictionary for Qt card
        doc = {
            'id': card_data.doc_id,
            'title': card_data.title,
            'abstract': card_data.abstract or "No abstract available",
            'authors': card_data.authors or [],
            'journal': card_data.journal,
            'year': card_data.year,
            'pmid': card_data.pmid,
            'doi': card_data.doi,
            'source': card_data.source,
            'relevance_score': card_data.relevance_score or card_data.human_score
        }

        # Create the base card
        card = CollapsibleDocumentCard(doc)

        # Add PDF button if requested
        if card_data.show_pdf_button:
            pdf_button = self._create_pdf_button_for_card(card_data)
            if pdf_button:
                # Add button to the card's details section
                # We'll insert it after the card's existing layout
                card.details_layout.addWidget(pdf_button)

        return card

    def _create_pdf_button_for_card(self, card_data: DocumentCardData) -> Optional[QWidget]:
        """Create and configure PDF button for a document card."""
        # Determine PDF state
        pdf_state = self.determine_pdf_state(
            card_data.doc_id,
            card_data.pdf_path,
            card_data.pdf_url
        )

        if pdf_state == PDFButtonState.HIDDEN:
            return None

        # Get actual PDF path if available
        pdf_path = self.get_pdf_path(card_data.doc_id, card_data.pdf_path)

        # Create button configuration
        config = PDFButtonConfig(
            state=pdf_state,
            pdf_path=pdf_path,
            pdf_url=card_data.pdf_url,
            on_view=self._create_view_handler(card_data),
            on_fetch=self._create_fetch_handler(card_data),
            on_upload=self._create_upload_handler(card_data),
            show_notifications=True
        )

        # Create the button widget
        return self.create_pdf_button(config)

    def create_pdf_button(self, config: PDFButtonConfig) -> Optional[QWidget]:
        """
        Create a Qt PDF button widget.

        Args:
            config: Configuration for the PDF button

        Returns:
            QWidget with the PDF button, or None if hidden
        """
        if config.state == PDFButtonState.HIDDEN:
            return None

        # Create button
        button = PDFButtonWidget(config)

        # Wrap in container for consistent layout
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.addWidget(button)
        layout.addStretch()

        return container

    def _create_view_handler(self, card_data: DocumentCardData) -> Callable:
        """Create handler for viewing PDF."""
        def handler():
            if card_data.on_pdf_action:
                card_data.on_pdf_action('view', card_data.doc_id)

            pdf_path = self.get_pdf_path(card_data.doc_id, card_data.pdf_path)
            if pdf_path and pdf_path.exists():
                # Open in Qt PDF viewer or system default
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(pdf_path)))
                logger.info(f"Opened PDF for document {card_data.doc_id}")
            else:
                logger.error(f"PDF not found for document {card_data.doc_id}")

        return handler

    def _create_fetch_handler(self, card_data: DocumentCardData) -> Callable:
        """Create handler for fetching PDF."""
        def handler() -> Optional[Path]:
            if card_data.on_pdf_action:
                result = card_data.on_pdf_action('fetch', card_data.doc_id, card_data.pdf_url)
                if isinstance(result, Path):
                    return result

            # Default fetch behavior
            if self.pdf_manager and card_data.pdf_url:
                try:
                    pdf_path = self.pdf_manager.download_pdf(
                        card_data.doc_id,
                        card_data.pdf_url
                    )
                    logger.info(f"Downloaded PDF for document {card_data.doc_id}")
                    return pdf_path
                except Exception as e:
                    logger.error(f"Failed to download PDF: {e}")

            return None

        return handler

    def _create_upload_handler(self, card_data: DocumentCardData) -> Callable:
        """Create handler for uploading PDF."""
        def handler() -> Optional[Path]:
            if card_data.on_pdf_action:
                result = card_data.on_pdf_action('upload', card_data.doc_id)
                if isinstance(result, Path):
                    return result

            # Default upload behavior handled by PDFButtonWidget
            return None

        return handler
