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
    Compact design with minimal height matching text.

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
            self.setText("📄 View")
            self.setObjectName("pdf_view_button")
        elif self.config.state == PDFButtonState.FETCH:
            self.setText("⬇️ Fetch")
            self.setObjectName("pdf_fetch_button")
        elif self.config.state == PDFButtonState.UPLOAD:
            self.setText("📤 Upload")
            self.setObjectName("pdf_upload_button")

        # Compact sizing - only slightly taller than text
        self.setFixedHeight(ButtonSizes.MIN_HEIGHT)
        self.setCursor(Qt.PointingHandCursor)

        # Apply compact styling directly
        self.setStyleSheet(f"""
            QPushButton {{
                padding: {ButtonSizes.PADDING_VERTICAL}px {ButtonSizes.PADDING_HORIZONTAL}px;
                border-radius: {ButtonSizes.BORDER_RADIUS}px;
            }}
        """)

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
        """Handle fetch PDF action with progress feedback and error handling."""
        try:
            if self.config.on_fetch:
                # Show progress indicator
                original_text = self.text()
                self.setText("Downloading...")
                self.setEnabled(False)

                try:
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
                finally:
                    # Always restore button state
                    self.setEnabled(True)
                    if self.config.state != PDFButtonState.VIEW:
                        self.setText(original_text)
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
            result = None
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
                        return  # Successfully handled by callback
                    else:
                        raise TypeError(
                            f"Upload handler returned invalid type: {type(result)}"
                        )

            # If no callback, or callback returned None, use default file dialog
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
    - Discovery-based PDF download with browser fallback support
    """

    def __init__(
        self,
        pdf_manager=None,
        base_pdf_dir: Optional[Path] = None,
        use_discovery: bool = True,
        unpaywall_email: Optional[str] = None
    ):
        """
        Initialize Qt document card factory.

        Args:
            pdf_manager: PDFManager instance for handling PDF operations
            base_pdf_dir: Base directory for PDF files
            use_discovery: If True, use discovery-first workflow for PDF downloads.
                This leverages PMC, Unpaywall, and DOI resolution to find the best
                available PDF source, with browser-based fallback for protected sites.
            unpaywall_email: Email for Unpaywall API requests (optional)

        Raises:
            ValueError: If base_pdf_dir is invalid or not writable
        """
        super().__init__(base_pdf_dir)
        self.pdf_manager = pdf_manager
        self.use_discovery = use_discovery
        self.unpaywall_email = unpaywall_email
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
            'relevance_score': card_data.relevance_score or card_data.human_score,
            'ai_reasoning': card_data.ai_reasoning,
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
            show_notifications=True,
            doc_id=card_data.doc_id
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

        # Connect error signal for user feedback
        button.error_occurred.connect(
            lambda msg, doc_id=config.doc_id: self._handle_pdf_button_error(msg, doc_id)
        )

        # Wrap in container for consistent layout
        container = self._create_button_container(button)

        return container

    def _handle_pdf_button_error(self, error_msg: str, doc_id: int):
        """
        Handle PDF button errors with appropriate user feedback.

        Args:
            error_msg: Error message from PDF operation
            doc_id: Document ID
        """
        from PySide6.QtWidgets import QMessageBox

        logger.error(f"PDF button error for document {doc_id}: {error_msg}")

        # Check if this is an expected error (access denied, not found, etc.)
        expected_errors = [
            "403",  # Forbidden (paywall/access restriction)
            "404",  # Not found
            "401",  # Unauthorized
            "HTTP 403",
            "HTTP 404",
            "HTTP 401",
        ]

        is_expected_error = any(err in error_msg for err in expected_errors)

        # Only show dialog for unexpected errors
        if not is_expected_error:
            # Show error dialog for unexpected failures
            msg_box = QMessageBox()
            msg_box.setIcon(QMessageBox.Warning)
            msg_box.setWindowTitle("PDF Download Failed")
            msg_box.setText(f"Failed to download PDF for document {doc_id}")
            msg_box.setInformativeText(error_msg)
            msg_box.setStandardButtons(QMessageBox.Ok)
            msg_box.exec()
        # For expected errors (403, 404), just log - user can see button didn't change state

    def _create_button_container(self, button: PDFButtonWidget) -> QWidget:
        """
        Create container widget for PDF button(s).

        If the primary button is View or Fetch, adds a secondary Upload button
        to allow PDF replacement.

        Args:
            button: The primary PDF button widget

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
        layout.setSpacing(8)  # Spacing between buttons

        # Add primary button
        layout.addWidget(button)

        # Add secondary upload button if primary is View or Fetch
        if button.config.state in (PDFButtonState.VIEW, PDFButtonState.FETCH):
            secondary_config = PDFButtonConfig(
                state=PDFButtonState.UPLOAD,
                pdf_path=button.config.pdf_path,
                pdf_url=button.config.pdf_url,
                on_upload=button.config.on_upload,
                show_notifications=button.config.show_notifications,
                doc_id=button.config.doc_id
            )
            secondary_button = PDFButtonWidget(secondary_config)
            secondary_button.setText("📤 Replace")  # Different text for clarity

            # Connect secondary button's uploaded signal to update primary button
            def on_secondary_upload(path: Path, primary: PDFButtonWidget = button) -> None:
                """Handle secondary upload by transitioning primary to VIEW."""
                primary._transition_to_view(path)

            secondary_button.pdf_uploaded.connect(on_secondary_upload)

            # Connect error signal - use doc_id or fallback to 0
            doc_id_for_error = button.config.doc_id if button.config.doc_id is not None else 0
            secondary_button.error_occurred.connect(
                lambda msg, did=doc_id_for_error: self._handle_pdf_button_error(msg, did)
            )

            layout.addWidget(secondary_button)

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

        Uses discovery-first workflow if enabled, which:
        1. Discovers available sources (PMC, Unpaywall, DOI, direct URL)
        2. Tries direct HTTP download from each source
        3. Falls back to browser-based download for protected sites

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

                # Create document dictionary for download methods
                document = {
                    'id': card_data.doc_id,
                    'doi': card_data.doi,
                    'pmid': card_data.pmid,
                    'pdf_url': card_data.pdf_url,
                    'title': card_data.title,
                    'authors': card_data.authors,
                    'publication_date': str(card_data.year) if card_data.year else None,
                }

                # Use discovery-first workflow if enabled and PDFManager supports it
                if self.use_discovery and self.pdf_manager:
                    if hasattr(self.pdf_manager, 'download_pdf_with_discovery'):
                        logger.info(f"Using discovery workflow for document {card_data.doc_id}")
                        pdf_path = self.pdf_manager.download_pdf_with_discovery(
                            document,
                            use_browser_fallback=True,
                            unpaywall_email=self.unpaywall_email
                        )

                        if pdf_path and pdf_path.exists():
                            # Update database with pdf_filename
                            self._update_pdf_filename_in_database(card_data.doc_id, pdf_path, document)
                            # Update cache
                            self._pdf_path_cache[card_data.doc_id] = pdf_path
                            logger.info(f"Downloaded PDF via discovery for document {card_data.doc_id}: {pdf_path}")
                            return pdf_path
                        # Discovery failed, will fall through to direct download below

                # Fall back to direct download if discovery not available/failed
                if self.pdf_manager and card_data.pdf_url:
                    pdf_path = self.pdf_manager.download_pdf(document)

                    if not pdf_path or not pdf_path.exists():
                        # Provide a helpful error message
                        error_msg = f"Failed to download PDF for document {card_data.doc_id}"
                        if card_data.pdf_url:
                            if "oup.com" in card_data.pdf_url or "springer" in card_data.pdf_url:
                                error_msg += " (HTTP 403 - Access restricted, likely requires institutional subscription)"
                            else:
                                error_msg += f" from {card_data.pdf_url}"
                        raise FileNotFoundError(error_msg)

                    # Update database with pdf_filename
                    self._update_pdf_filename_in_database(card_data.doc_id, pdf_path, document)

                    # Update cache
                    self._pdf_path_cache[card_data.doc_id] = pdf_path

                    logger.info(f"Downloaded PDF for document {card_data.doc_id}: {pdf_path}")
                    return pdf_path

                raise ValueError("No PDF manager or URL configured for fetch")

            except (FileNotFoundError, ValueError, RuntimeError, OSError) as e:
                logger.error(f"Failed to fetch PDF for document {card_data.doc_id}: {e}")
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

    def _update_pdf_filename_in_database(self, doc_id: int, pdf_path: Path, document: Dict[str, Any]) -> None:
        """
        Update the pdf_filename in the database after downloading a PDF.

        Args:
            doc_id: Document ID
            pdf_path: Path to the downloaded PDF file
            document: Document dictionary (for PDFManager's get_relative_pdf_path)
        """
        try:
            # Get relative path using PDFManager's method
            # Update document dict with the actual pdf_filename for relative path calculation
            document['pdf_filename'] = pdf_path.name
            relative_path = self.pdf_manager.get_relative_pdf_path(document)

            if not relative_path:
                logger.error(f"PDFManager.get_relative_pdf_path returned None for document {doc_id}")
                # Fallback: calculate manually
                if self.base_pdf_dir and pdf_path.is_relative_to(self.base_pdf_dir):
                    relative_path = str(pdf_path.relative_to(self.base_pdf_dir))
                else:
                    relative_path = pdf_path.name

            logger.info(f"[PDF DEBUG] Document ID: {doc_id}")
            logger.info(f"[PDF DEBUG] PDF saved to absolute path: {pdf_path}")
            logger.info(f"[PDF DEBUG] Relative path for database: {relative_path}")

            # Update database using PDFManager's method if it has db connection
            if hasattr(self.pdf_manager, 'db_conn') and self.pdf_manager.db_conn:
                success = self.pdf_manager.update_database_pdf_path(doc_id, relative_path)
                if success:
                    logger.info(f"[PDF DEBUG] Successfully updated document.pdf_filename in database via PDFManager")
                else:
                    logger.error(f"[PDF DEBUG] PDFManager.update_database_pdf_path failed for document {doc_id}")
            else:
                # Fallback: update directly
                from bmlibrarian.database import get_db_manager
                db_manager = get_db_manager()

                with db_manager.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE document SET pdf_filename = %s WHERE id = %s",
                            (relative_path, doc_id)
                        )
                        conn.commit()
                        logger.info(f"[PDF DEBUG] Successfully updated document.pdf_filename in database directly")

        except Exception as e:
            logger.error(f"[PDF DEBUG] Failed to update pdf_filename in database for document {doc_id}: {e}")
            import traceback
            traceback.print_exc()
            # Don't raise - the PDF was successfully downloaded, database update is secondary
