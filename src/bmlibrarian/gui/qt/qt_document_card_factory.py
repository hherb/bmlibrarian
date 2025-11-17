"""
Qt implementation of the document card factory.

This module provides a Qt-specific implementation of the DocumentCardFactoryBase,
integrating with existing Qt document card classes and adding PDF button functionality
that matches the Flet implementation.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFrame, QLabel
)
from PySide6.QtCore import Qt, Signal, QObject, QMutex, QMutexLocker
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from typing import Optional, Callable, Dict, Any
from pathlib import Path
import logging

from bmlibrarian.gui.document_card_factory_base import (
    DocumentCardFactoryBase,
    DocumentCardData,
    PDFButtonConfig,
    PDFButtonState,
    CardContext
)
from bmlibrarian.gui.qt.resources.constants import (
    ButtonSizes,
    LayoutSpacing,
    PDFOperationSettings,
    FileSystemDefaults
)

logger = logging.getLogger(__name__)


class PDFButtonWidget(QPushButton):
    """
    Qt PDF button with three states: View, Fetch, Upload.

    This widget uses centralized stylesheet styling via object names and
    includes comprehensive error handling for all PDF operations.

    Signals:
        pdf_viewed: Emitted when PDF is viewed
        pdf_fetched: Emitted when PDF is fetched (returns path)
        pdf_uploaded: Emitted when PDF is uploaded (returns path)
        error_occurred: Emitted when an error occurs (returns error message)
    """

    pdf_viewed = Signal()
    pdf_fetched = Signal(Path)
    pdf_uploaded = Signal(Path)
    error_occurred = Signal(str)

    def __init__(self, config: PDFButtonConfig, parent: Optional[QWidget] = None):
        """
        Initialize PDF button.

        Args:
            config: Button configuration
            parent: Optional parent widget
        """
        super().__init__(parent)
        self.config = config
        self._state_mutex = QMutex()  # Thread-safe state transitions
        self._update_button_appearance()

        # Connect click handler
        self.clicked.connect(self._handle_click)

    def _update_button_appearance(self):
        """Update button text and object name for stylesheet styling."""
        # Use object names to apply centralized stylesheet styles
        if self.config.state == PDFButtonState.VIEW:
            self.setText("📄 View Full Text")
            self.setObjectName("pdf_view_button")
        elif self.config.state == PDFButtonState.FETCH:
            self.setText("⬇️ Fetch Full Text")
            self.setObjectName("pdf_fetch_button")
        elif self.config.state == PDFButtonState.UPLOAD:
            self.setText("📤 Upload Full Text")
            self.setObjectName("pdf_upload_button")

        # Apply consistent sizing from constants
        self.setMinimumHeight(ButtonSizes.MIN_HEIGHT)
        self.setCursor(Qt.PointingHandCursor)

        # Force stylesheet refresh
        self.style().unpolish(self)
        self.style().polish(self)

    def _handle_click(self):
        """Handle button click based on current state."""
        try:
            if self.config.state == PDFButtonState.VIEW:
                self._handle_view()
            elif self.config.state == PDFButtonState.FETCH:
                self._handle_fetch()
            elif self.config.state == PDFButtonState.UPLOAD:
                self._handle_upload()
        except Exception as e:
            error_msg = f"PDF operation failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.error_occurred.emit(error_msg)

    def _handle_view(self):
        """Handle view PDF action with comprehensive error handling."""
        try:
            if self.config.on_view:
                self.config.on_view()
            elif self.config.pdf_path:
                # Validate path exists before attempting to open
                if not self.config.pdf_path.exists():
                    raise FileNotFoundError(
                        f"PDF file not found: {self.config.pdf_path}"
                    )

                # Validate path is a file
                if not self.config.pdf_path.is_file():
                    raise ValueError(
                        f"PDF path is not a file: {self.config.pdf_path}"
                    )

                # Attempt to open in system PDF viewer
                url = QUrl.fromLocalFile(str(self.config.pdf_path))
                if not QDesktopServices.openUrl(url):
                    raise RuntimeError(
                        f"Failed to open PDF with system viewer: {self.config.pdf_path}"
                    )

                logger.info(f"Opened PDF: {self.config.pdf_path}")
            else:
                raise ValueError("No PDF path configured for view operation")

            self.pdf_viewed.emit()

        except (FileNotFoundError, ValueError, RuntimeError, OSError) as e:
            error_msg = f"Failed to view PDF: {str(e)}"
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            raise

    def _handle_fetch(self):
        """Handle fetch PDF action with error handling and retry logic."""
        try:
            if self.config.on_fetch:
                result = self.config.on_fetch()
                if result:
                    # Callback should return the downloaded path
                    if isinstance(result, Path):
                        if not result.exists():
                            raise FileNotFoundError(
                                f"Downloaded PDF not found: {result}"
                            )
                        self._transition_to_view(result)
                        self.pdf_fetched.emit(result)
                        logger.info(f"Successfully fetched PDF: {result}")
                    else:
                        raise TypeError(
                            f"Fetch handler returned invalid type: {type(result)}"
                        )
                else:
                    raise RuntimeError("Fetch operation returned no result")
            else:
                raise ValueError("No fetch handler configured")

        except (FileNotFoundError, TypeError, RuntimeError, ValueError, OSError) as e:
            error_msg = f"Failed to fetch PDF: {str(e)}"
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            # Don't transition state on error
            raise

    def _handle_upload(self):
        """Handle upload PDF action with validation."""
        try:
            if self.config.on_upload:
                result = self.config.on_upload()
                if result:
                    # Callback should return the uploaded path
                    if isinstance(result, Path):
                        if not result.exists():
                            raise FileNotFoundError(
                                f"Uploaded PDF not found: {result}"
                            )
                        self._transition_to_view(result)
                        self.pdf_uploaded.emit(result)
                        logger.info(f"Successfully uploaded PDF: {result}")
                    else:
                        raise TypeError(
                            f"Upload handler returned invalid type: {type(result)}"
                        )
            else:
                # Default behavior: show file dialog
                self._default_upload_handler()

        except (FileNotFoundError, TypeError, RuntimeError, OSError) as e:
            error_msg = f"Failed to upload PDF: {str(e)}"
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            raise

    def _default_upload_handler(self):
        """Default upload handler using file dialog."""
        from PySide6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Upload PDF",
            str(Path.home()),
            FileSystemDefaults.PDF_FILE_FILTER
        )

        if file_path:
            path = Path(file_path)
            if not path.exists():
                raise FileNotFoundError(f"Selected file not found: {path}")

            if not path.is_file():
                raise ValueError(f"Selected path is not a file: {path}")

            if path.suffix.lower() != FileSystemDefaults.PDF_EXTENSION:
                raise ValueError(f"Selected file is not a PDF: {path}")

            self._transition_to_view(path)
            self.pdf_uploaded.emit(path)
            logger.info(f"Uploaded PDF via file dialog: {path}")

    def _transition_to_view(self, pdf_path: Path):
        """
        Transition button to VIEW state after successful fetch/upload.

        Thread-safe state transition using mutex.

        Args:
            pdf_path: Path to the PDF file
        """
        with QMutexLocker(self._state_mutex):
            self.config.pdf_path = pdf_path
            self.config.state = PDFButtonState.VIEW
            self._update_button_appearance()
            logger.debug(f"Transitioned to VIEW state for: {pdf_path}")


class QtDocumentCardFactory(DocumentCardFactoryBase):
    """
    Qt-specific document card factory.

    This class provides Qt widgets for document cards with integrated PDF button
    functionality, matching the Flet implementation's three-state PDF buttons.

    Features:
    - Centralized stylesheet styling (no inline styles)
    - Comprehensive error handling for all PDF operations
    - PDF path caching for performance
    - Thread-safe operations
    - Modular method design for maintainability
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

        Raises:
            ValueError: If base_pdf_dir is invalid or not writable
        """
        super().__init__(base_pdf_dir)
        self.pdf_manager = pdf_manager
        self._pdf_path_cache: Dict[int, Optional[Path]] = {}  # Performance optimization

    def create_card(self, card_data: DocumentCardData) -> QFrame:
        """
        Create a Qt document card.

        This method has been refactored to be more modular and maintainable.

        Args:
            card_data: Data and configuration for the card

        Returns:
            QFrame widget for the document
        """
        # Prepare document data
        doc = self._prepare_document_dict(card_data)

        # Create the base card
        card = self._create_base_card(doc)

        # Add PDF button if requested
        if card_data.show_pdf_button:
            self._add_pdf_button_to_card(card, card_data)

        return card

    def _prepare_document_dict(self, card_data: DocumentCardData) -> Dict[str, Any]:
        """
        Prepare document dictionary for Qt card.

        Args:
            card_data: Document card data

        Returns:
            Dictionary with document information
        """
        return {
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

    def _create_base_card(self, doc: Dict[str, Any]) -> QFrame:
        """
        Create the base collapsible document card.

        Args:
            doc: Document dictionary

        Returns:
            CollapsibleDocumentCard widget
        """
        from .widgets.collapsible_document_card import CollapsibleDocumentCard
        return CollapsibleDocumentCard(doc)

    def _add_pdf_button_to_card(
        self,
        card: QFrame,
        card_data: DocumentCardData
    ) -> None:
        """
        Add PDF button to an existing card.

        Args:
            card: The card widget to add the button to
            card_data: Document card data
        """
        pdf_button = self._create_pdf_button_for_card(card_data)
        if pdf_button:
            # Add button to the card's details section
            card.details_layout.addWidget(pdf_button)

    def _create_pdf_button_for_card(
        self,
        card_data: DocumentCardData
    ) -> Optional[QWidget]:
        """
        Create and configure PDF button for a document card.

        Args:
            card_data: Document card data

        Returns:
            PDF button widget or None if hidden
        """
        # Determine PDF state (uses cached paths for performance)
        pdf_state = self._determine_pdf_state_cached(card_data)

        if pdf_state == PDFButtonState.HIDDEN:
            return None

        # Get actual PDF path if available (from cache)
        pdf_path = self._get_pdf_path_cached(card_data.doc_id, card_data.pdf_path)

        # Create button configuration
        config = self._create_pdf_button_config(card_data, pdf_state, pdf_path)

        # Create the button widget
        return self.create_pdf_button(config)

    def _determine_pdf_state_cached(self, card_data: DocumentCardData) -> PDFButtonState:
        """
        Determine PDF state using cached paths for performance.

        Args:
            card_data: Document card data

        Returns:
            PDFButtonState
        """
        return self.determine_pdf_state(
            card_data.doc_id,
            card_data.pdf_path,
            card_data.pdf_url
        )

    def _get_pdf_path_cached(
        self,
        doc_id: int,
        pdf_path: Optional[Path] = None
    ) -> Optional[Path]:
        """
        Get PDF path with caching for performance.

        Args:
            doc_id: Document ID
            pdf_path: Explicit PDF path if known

        Returns:
            Path to PDF file if it exists, None otherwise
        """
        # Check cache first
        if doc_id in self._pdf_path_cache:
            cached_path = self._pdf_path_cache[doc_id]
            # Validate cached path still exists
            if cached_path and cached_path.exists():
                return cached_path
            elif not cached_path:
                # Cached as None (known not to exist)
                return None
            # Cached path no longer exists, invalidate cache

        # Get path using parent method
        result = self.get_pdf_path(doc_id, pdf_path)

        # Update cache
        self._pdf_path_cache[doc_id] = result

        return result

    def _create_pdf_button_config(
        self,
        card_data: DocumentCardData,
        pdf_state: PDFButtonState,
        pdf_path: Optional[Path]
    ) -> PDFButtonConfig:
        """
        Create PDF button configuration.

        Args:
            card_data: Document card data
            pdf_state: PDF button state
            pdf_path: Path to PDF file if available

        Returns:
            PDFButtonConfig
        """
        return PDFButtonConfig(
            state=pdf_state,
            pdf_path=pdf_path,
            pdf_url=card_data.pdf_url,
            on_view=self._create_view_handler(card_data),
            on_fetch=self._create_fetch_handler(card_data),
            on_upload=self._create_upload_handler(card_data),
            show_notifications=True
        )

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

        # Connect error signal for logging
        button.error_occurred.connect(
            lambda msg: logger.error(f"PDF button error: {msg}")
        )

        # Wrap in container for consistent layout
        container = self._create_button_container(button)

        return container

    def _create_button_container(self, button: QPushButton) -> QWidget:
        """
        Create container widget for PDF button.

        Args:
            button: The PDF button widget

        Returns:
            Container widget with proper layout
        """
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(
            LayoutSpacing.CONTAINER_MARGIN,
            LayoutSpacing.PDF_BUTTON_TOP_MARGIN,
            LayoutSpacing.CONTAINER_MARGIN,
            LayoutSpacing.CONTAINER_MARGIN
        )
        layout.addWidget(button)
        layout.addStretch()

        return container

    def _create_view_handler(self, card_data: DocumentCardData) -> Callable:
        """
        Create handler for viewing PDF.

        Args:
            card_data: Document card data

        Returns:
            Callable handler function
        """
        def handler():
            try:
                # Call custom callback if provided
                if card_data.on_pdf_action:
                    card_data.on_pdf_action('view', card_data.doc_id)

                # Get PDF path (from cache)
                pdf_path = self._get_pdf_path_cached(
                    card_data.doc_id,
                    card_data.pdf_path
                )

                if not pdf_path or not pdf_path.exists():
                    raise FileNotFoundError(
                        f"PDF not found for document {card_data.doc_id}"
                    )

                # Validate it's a file
                if not pdf_path.is_file():
                    raise ValueError(
                        f"PDF path is not a file: {pdf_path}"
                    )

                # Open in Qt PDF viewer or system default
                url = QUrl.fromLocalFile(str(pdf_path))
                if not QDesktopServices.openUrl(url):
                    raise RuntimeError(
                        f"Failed to open PDF with system viewer: {pdf_path}"
                    )

                logger.info(f"Opened PDF for document {card_data.doc_id}: {pdf_path}")

            except (FileNotFoundError, ValueError, RuntimeError, OSError) as e:
                logger.error(f"Failed to view PDF for document {card_data.doc_id}: {e}")
                raise

        return handler

    def _create_fetch_handler(self, card_data: DocumentCardData) -> Callable:
        """
        Create handler for fetching PDF.

        Args:
            card_data: Document card data

        Returns:
            Callable handler function that returns Optional[Path]
        """
        def handler() -> Optional[Path]:
            try:
                # Call custom callback if provided
                if card_data.on_pdf_action:
                    result = card_data.on_pdf_action(
                        'fetch',
                        card_data.doc_id,
                        card_data.pdf_url
                    )
                    if isinstance(result, Path):
                        # Update cache
                        self._pdf_path_cache[card_data.doc_id] = result
                        return result

                # Default fetch behavior using pdf_manager
                if self.pdf_manager and card_data.pdf_url:
                    pdf_path = self.pdf_manager.download_pdf(
                        card_data.doc_id,
                        card_data.pdf_url
                    )

                    if not pdf_path or not pdf_path.exists():
                        raise FileNotFoundError(
                            f"Downloaded PDF not found for document {card_data.doc_id}"
                        )

                    # Update cache
                    self._pdf_path_cache[card_data.doc_id] = pdf_path

                    logger.info(
                        f"Downloaded PDF for document {card_data.doc_id}: {pdf_path}"
                    )
                    return pdf_path

                raise ValueError("No PDF manager or URL configured for fetch")

            except (FileNotFoundError, ValueError, RuntimeError, OSError) as e:
                logger.error(
                    f"Failed to fetch PDF for document {card_data.doc_id}: {e}"
                )
                raise

        return handler

    def _create_upload_handler(self, card_data: DocumentCardData) -> Callable:
        """
        Create handler for uploading PDF.

        Args:
            card_data: Document card data

        Returns:
            Callable handler function that returns Optional[Path]
        """
        def handler() -> Optional[Path]:
            try:
                # Call custom callback if provided
                if card_data.on_pdf_action:
                    result = card_data.on_pdf_action('upload', card_data.doc_id)
                    if isinstance(result, Path):
                        # Update cache
                        self._pdf_path_cache[card_data.doc_id] = result
                        return result

                # Default upload behavior handled by PDFButtonWidget
                return None

            except (ValueError, RuntimeError, OSError) as e:
                logger.error(
                    f"Failed to upload PDF for document {card_data.doc_id}: {e}"
                )
                raise

        return handler

    def clear_pdf_cache(self) -> None:
        """Clear the PDF path cache."""
        self._pdf_path_cache.clear()
        logger.debug("Cleared PDF path cache")

    def invalidate_pdf_cache(self, doc_id: int) -> None:
        """
        Invalidate cache entry for a specific document.

        Args:
            doc_id: Document ID to invalidate
        """
        if doc_id in self._pdf_path_cache:
            del self._pdf_path_cache[doc_id]
            logger.debug(f"Invalidated PDF cache for document {doc_id}")
