"""
Qt implementation of the document card factory.

This module provides a Qt-specific implementation of the DocumentCardFactoryBase,
integrating with existing Qt document card classes and adding PDF button functionality
that matches the Flet implementation.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFrame, QLabel,
    QDialog, QApplication
)
from PySide6.QtCore import Qt, Signal, QObject, QMutex, QMutexLocker, QThread, QTimer
from PySide6.QtGui import QDesktopServices, QFont
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
    FileSystemDefaults,
    PDFButtonColors
)
from bmlibrarian.utils.error_messages import format_pdf_download_error

logger = logging.getLogger(__name__)


class PDFFetchWorker(QThread):
    """
    Worker thread for PDF fetch operations.

    Runs long-running PDF discovery and download operations off the main
    thread to prevent UI blocking and ensure responsive button states.

    Signals:
        finished: Emitted when operation completes successfully (returns Path)
        error: Emitted when operation fails (returns error message)
        progress: Emitted for progress updates (returns status message)
    """

    finished = Signal(Path)
    error = Signal(str)
    progress = Signal(str)

    def __init__(
        self,
        fetch_handler: Callable,
        parent: Optional[QObject] = None
    ):
        """
        Initialize PDF fetch worker.

        Args:
            fetch_handler: Callable that performs the actual fetch operation
            parent: Optional parent QObject
        """
        super().__init__(parent)
        self._fetch_handler = fetch_handler
        self._mutex = QMutex()
        self._abort = False

    def abort(self) -> None:
        """Request abort of the current operation."""
        with QMutexLocker(self._mutex):
            self._abort = True

    def run(self) -> None:
        """Execute the fetch operation in the worker thread."""
        try:
            # Check for early abort
            with QMutexLocker(self._mutex):
                if self._abort:
                    self.error.emit("Operation cancelled")
                    return

            self.progress.emit("Starting download...")

            result = self._fetch_handler()

            # Check for abort after long operation
            with QMutexLocker(self._mutex):
                if self._abort:
                    self.error.emit("Operation cancelled")
                    return

            if result and isinstance(result, Path):
                self.finished.emit(result)
            else:
                self.error.emit("Download failed. No PDF was retrieved.")

        except Exception as e:
            # Use standardized user-friendly error messages
            friendly_error = format_pdf_download_error(e)
            friendly_error.log()  # Log technical details
            self.error.emit(friendly_error.user_message)


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
        pdf_discovered: Emitted when PDF is discovered (returns path)
        error_occurred: Emitted when an error occurs (returns error message)
    """

    pdf_viewed = Signal()
    pdf_fetched = Signal(Path)
    pdf_uploaded = Signal(Path)
    pdf_discovered = Signal(Path)
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
        self._fetch_worker: Optional[PDFFetchWorker] = None  # Track running fetch
        self._update_button_appearance()

        # Connect click handler
        self.clicked.connect(self._handle_click)

    def _update_button_appearance(self):
        """Update button text and object name for stylesheet styling.

        Relies entirely on centralized stylesheets (theme_generator.py) for sizing
        and appearance. Object names are used to match the CSS selectors.
        """
        # Import DPI scaler for runtime-scaled dimensions
        from bmlibrarian.gui.qt.resources.styles.dpi_scale import get_font_scale

        # Use object names to apply centralized stylesheet styles
        if self.config.state == PDFButtonState.VIEW:
            self.setText("📄 View")
            self.setObjectName("pdf_view_button")
        elif self.config.state == PDFButtonState.FETCH:
            # Changed from "Fetch" to "Find" - now uses discovery workflow
            # which searches PMC, Unpaywall, DOI, etc. with content verification
            self.setText("🔍 Find")
            self.setObjectName("pdf_fetch_button")
        elif self.config.state == PDFButtonState.UPLOAD:
            self.setText("📤 Upload")
            self.setObjectName("pdf_upload_button")

        # Get DPI-scaled dimensions
        s = get_font_scale()

        # Apply DPI-scaled sizing constraints
        # Height uses control_height_small for compact buttons
        # Width uses control_width_small for visual consistency
        self.setFixedHeight(s['control_height_small'])
        self.setMinimumWidth(s['control_width_small'])
        self.setCursor(Qt.PointingHandCursor)

        # NO inline stylesheet - rely entirely on centralized theme_generator.py styles
        # The object names (pdf_view_button, etc.) map to CSS selectors in the theme

        # Force stylesheet refresh to pick up centralized styles
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
        """Handle fetch PDF action using background thread.

        Uses PDFFetchWorker to run long-running PDF discovery and download
        operations off the main thread, preventing UI blocking.
        """
        if not self.config.on_fetch:
            error_msg = "No fetch handler configured"
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            return

        # Check if a fetch is already in progress
        if self._fetch_worker is not None and self._fetch_worker.isRunning():
            logger.warning("Fetch already in progress, ignoring click")
            return

        # Show progress indicator
        self._original_text = self.text()
        self.setText("Downloading...")
        self.setEnabled(False)

        # Create and configure worker thread
        self._fetch_worker = PDFFetchWorker(self.config.on_fetch, parent=self)
        self._fetch_worker.finished.connect(self._on_fetch_success)
        self._fetch_worker.error.connect(self._on_fetch_error)
        self._fetch_worker.progress.connect(self._on_fetch_progress)

        # Start the background operation
        self._fetch_worker.start()

    def _on_fetch_success(self, pdf_path: Path) -> None:
        """Handle successful PDF fetch.

        Args:
            pdf_path: Path to the downloaded PDF file
        """
        try:
            if not pdf_path.exists():
                raise FileNotFoundError(f"Downloaded PDF not found: {pdf_path}")

            self._transition_to_view(pdf_path)
            self.pdf_fetched.emit(pdf_path)
            logger.info(f"Successfully fetched PDF: {pdf_path}")

        except (FileNotFoundError, OSError) as e:
            self._on_fetch_error(str(e))

        finally:
            self._cleanup_fetch_worker()

    def _on_fetch_error(self, error_msg: str) -> None:
        """Handle fetch error.

        Args:
            error_msg: Error message describing the failure
        """
        logger.error(f"Failed to fetch PDF: {error_msg}")
        self.error_occurred.emit(f"Failed to fetch PDF: {error_msg}")

        # Restore button state
        self.setEnabled(True)
        if hasattr(self, '_original_text'):
            self.setText(self._original_text)

        self._cleanup_fetch_worker()

    def _on_fetch_progress(self, status: str) -> None:
        """Handle progress update from fetch worker.

        Args:
            status: Status message
        """
        self.setText(status)

    def _cleanup_fetch_worker(self) -> None:
        """Clean up the fetch worker after completion."""
        if self._fetch_worker is not None:
            # Wait for thread to finish if still running
            if self._fetch_worker.isRunning():
                self._fetch_worker.abort()
                self._fetch_worker.wait(1000)  # Wait up to 1 second

            self._fetch_worker.deleteLater()
            self._fetch_worker = None

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
        """
        Default upload handler using file dialog.

        Note: This method only handles file selection and validation.
        The actual copying and database update is handled by the factory's
        upload handler callback (on_upload), which is set in _create_upload_handler.
        """
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


class PDFDiscoveryProgressDialog(QDialog):
    """
    Modal dialog showing PDF discovery progress.

    Displays real-time progress through discovery resolvers (PMC, Unpaywall, DOI, etc.)
    and download status.
    """

    # Discovery steps with display names
    RESOLVER_NAMES = {
        'crossref_title': 'CrossRef Title Search',
        'pmc': 'PubMed Central',
        'unpaywall': 'Unpaywall',
        'doi': 'DOI Resolution',
        'direct_url': 'Direct URL',
        'openathens': 'OpenAthens Proxy',
        'discovery': 'Discovery',
        'download': 'HTTP Download',
        'browser_download': 'Browser Download',
        'ftp_download': 'FTP Download',
    }

    STATUS_ICONS = {
        'resolving': '🔍',
        'starting': '▶️',
        'found': '✅',
        'found_oa': '✅',
        'not_found': '❌',
        'success': '✅',
        'failed': '❌',
        'error': '⚠️',
        'skipped': '⏭️',
    }

    def __init__(self, doc_id: int, title: str, parent: Optional[QWidget] = None):
        """
        Initialize progress dialog.

        Args:
            doc_id: Document ID being processed
            title: Document title for display
            parent: Optional parent widget
        """
        super().__init__(parent)
        self.doc_id = doc_id
        self.doc_title = title[:60] + "..." if len(title) > 60 else title

        self.setWindowTitle("Finding PDF")
        self.setModal(True)
        self.setMinimumWidth(400)
        self.setMinimumHeight(300)

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup the user interface."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Title
        title_label = QLabel(f"Finding PDF for document {self.doc_id}")
        title_label.setFont(QFont("", 11, QFont.Bold))
        layout.addWidget(title_label)

        # Document title
        doc_label = QLabel(self.doc_title)
        doc_label.setStyleSheet("color: #666; font-style: italic;")
        doc_label.setWordWrap(True)
        layout.addWidget(doc_label)

        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: #ddd;")
        layout.addWidget(line)

        # Status header
        status_header = QLabel("Progress:")
        status_header.setFont(QFont("", 10, QFont.Bold))
        layout.addWidget(status_header)

        # Progress log area
        self.progress_container = QVBoxLayout()
        self.progress_container.setSpacing(4)
        layout.addLayout(self.progress_container)

        # Stretch to push content up
        layout.addStretch()

        # Current status label
        self.status_label = QLabel("Starting discovery...")
        self.status_label.setStyleSheet("font-weight: bold; color: #2196F3;")
        layout.addWidget(self.status_label)

        # Store step widgets for updating
        self._step_widgets: Dict[str, QLabel] = {}

    def add_step(self, step_name: str, status: str) -> None:
        """
        Add or update a progress step.

        Args:
            step_name: Internal name of the step (e.g., 'pmc', 'download')
            status: Status string (e.g., 'resolving', 'found', 'not_found')
        """
        display_name = self.RESOLVER_NAMES.get(step_name, step_name.title())
        icon = self.STATUS_ICONS.get(status, '•')

        # Color based on status
        if status in ('found', 'found_oa', 'success'):
            color = '#4CAF50'  # Green
        elif status in ('not_found', 'failed', 'error'):
            color = '#f44336'  # Red
        elif status in ('skipped',):
            color = '#9E9E9E'  # Grey
        else:
            color = '#2196F3'  # Blue (in progress)

        text = f"{icon} {display_name}: {status.replace('_', ' ').title()}"

        if step_name in self._step_widgets:
            # Update existing step
            label = self._step_widgets[step_name]
            label.setText(text)
            label.setStyleSheet(f"color: {color};")
        else:
            # Add new step
            label = QLabel(text)
            label.setStyleSheet(f"color: {color};")
            self.progress_container.addWidget(label)
            self._step_widgets[step_name] = label

        # Update current status
        if status in ('resolving', 'starting'):
            self.status_label.setText(f"Trying {display_name}...")
            self.status_label.setStyleSheet("font-weight: bold; color: #2196F3;")
        elif status in ('found', 'found_oa'):
            self.status_label.setText(f"Found PDF via {display_name}!")
            self.status_label.setStyleSheet("font-weight: bold; color: #4CAF50;")

        # Process events to update UI
        QApplication.processEvents()

    def set_downloading(self, source: str) -> None:
        """
        Update status to show downloading.

        Args:
            source: Source being downloaded from
        """
        display_name = self.RESOLVER_NAMES.get(source, source.title())
        self.status_label.setText(f"Downloading from {display_name}...")
        self.status_label.setStyleSheet("font-weight: bold; color: #FF9800;")
        QApplication.processEvents()

    def set_success(self, file_path: Optional[Path], message: Optional[str] = None) -> None:
        """
        Update status to show success.

        Args:
            file_path: Path to downloaded file (may be None for NXML-only extraction)
            message: Optional custom success message (used when no file_path)
        """
        if file_path:
            self.status_label.setText(f"✅ Downloaded: {file_path.name}")
        elif message:
            self.status_label.setText(f"✅ {message}")
        else:
            self.status_label.setText("✅ Success")
        self.status_label.setStyleSheet("font-weight: bold; color: #4CAF50;")
        QApplication.processEvents()

    def set_failure(self, error_msg: str) -> None:
        """
        Update status to show failure.

        Args:
            error_msg: Error message to display
        """
        # Truncate long error messages
        if len(error_msg) > 80:
            error_msg = error_msg[:77] + "..."
        self.status_label.setText(f"❌ {error_msg}")
        self.status_label.setStyleSheet("font-weight: bold; color: #f44336;")
        QApplication.processEvents()


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
        pdf_path = self._get_pdf_path_cached(card_data.doc_id, card_data.pdf_path, card_data.pdf_filename)

        # Create button configuration
        config = self._create_pdf_button_config(card_data, pdf_state, pdf_path)

        # Create the button widget with card_data for Find PDF functionality
        return self.create_pdf_button(config, card_data)

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
            card_data.pdf_url,
            card_data.pdf_filename
        )

    def _get_pdf_path_cached(
        self,
        doc_id: int,
        pdf_path: Optional[Path] = None,
        pdf_filename: Optional[str] = None
    ) -> Optional[Path]:
        """
        Get PDF path with caching for performance.

        Args:
            doc_id: Document ID
            pdf_path: Explicit PDF path if known
            pdf_filename: Relative PDF path from database (e.g., "2022/paper.pdf")

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
        result = self.get_pdf_path(doc_id, pdf_path, pdf_filename)

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

    def create_pdf_button(
        self,
        config: PDFButtonConfig,
        card_data: Optional[DocumentCardData] = None
    ) -> Optional[QWidget]:
        """
        Create a Qt PDF button widget.

        Args:
            config: Configuration for the PDF button
            card_data: Optional document card data (enables "Find PDF" functionality)

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
        container = self._create_button_container(button, card_data)

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

    def _create_button_container(
        self,
        button: PDFButtonWidget,
        card_data: Optional[DocumentCardData] = None
    ) -> QWidget:
        """
        Create container widget for PDF button(s).

        If the primary button is View or Fetch, adds a secondary Upload button
        to allow PDF replacement.

        If the primary button is Upload, adds a "Find PDF" button to trigger
        PDF discovery using PMC, Unpaywall, DOI, and optionally OpenAthens.

        Args:
            button: The primary PDF button widget
            card_data: Optional document card data (needed for Find PDF functionality)

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

        # Connect primary button's pdf_uploaded signal to handle database updates
        if card_data is not None:
            button.pdf_uploaded.connect(
                lambda path, cd=card_data: self._handle_pdf_uploaded(path, cd)
            )

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

            # Connect secondary button's uploaded signal to update primary button and database
            def on_secondary_upload(path: Path, primary: PDFButtonWidget = button, cd: DocumentCardData = card_data) -> None:
                """Handle secondary upload by transitioning primary to VIEW and updating database."""
                primary._transition_to_view(path)
                if cd is not None:
                    self._handle_pdf_uploaded(path, cd)

            secondary_button.pdf_uploaded.connect(on_secondary_upload)

            # Connect error signal - use doc_id or fallback to 0
            doc_id_for_error = button.config.doc_id if button.config.doc_id is not None else 0
            secondary_button.error_occurred.connect(
                lambda msg, did=doc_id_for_error: self._handle_pdf_button_error(msg, did)
            )

            layout.addWidget(secondary_button)

        # Add "Find PDF" button if primary is Upload (no PDF available yet)
        if button.config.state == PDFButtonState.UPLOAD and card_data is not None:
            find_pdf_button = self._create_find_pdf_button(button, card_data)
            if find_pdf_button:
                layout.addWidget(find_pdf_button)

        layout.addStretch()

        return container

    def _create_find_pdf_button(
        self,
        primary_button: PDFButtonWidget,
        card_data: DocumentCardData
    ) -> Optional[QPushButton]:
        """
        Create a "Find PDF" button that triggers PDF discovery.

        Uses FullTextFinder to search PMC, Unpaywall, DOI, and optionally
        OpenAthens to locate and download the PDF.

        Args:
            primary_button: The primary PDF button to update on success
            card_data: Document card data with identifiers (DOI, PMID, etc.)

        Returns:
            QPushButton for finding PDF, or None if no identifiers available
        """
        # Check if document has any discoverable identifiers
        # Include title - we can search CrossRef by title to discover DOI
        has_identifiers = any([
            card_data.doi,
            card_data.pmid,
            card_data.pdf_url,
            card_data.title  # Can search CrossRef by title
        ])

        if not has_identifiers:
            logger.debug(
                f"Document {card_data.doc_id} has no discoverable identifiers"
            )
            return None

        find_button = QPushButton("🔍 Find PDF")
        find_button.setFixedHeight(ButtonSizes.MIN_HEIGHT)
        find_button.setMinimumWidth(ButtonSizes.MIN_WIDTH)
        find_button.setCursor(Qt.PointingHandCursor)
        find_button.setToolTip(
            "Search PMC, Unpaywall, CrossRef, and DOI.org for this paper's PDF.\n"
            "Can discover DOI from title if not in database."
        )

        # Apply styling using constants from PDFButtonColors
        find_button.setStyleSheet(f"""
            QPushButton {{
                padding: {ButtonSizes.PADDING_VERTICAL}px {ButtonSizes.PADDING_HORIZONTAL}px;
                border-radius: {ButtonSizes.BORDER_RADIUS}px;
                background-color: {PDFButtonColors.FIND_BG};
                color: {PDFButtonColors.TEXT_COLOR};
                border: none;
            }}
            QPushButton:hover {{
                background-color: {PDFButtonColors.FIND_BG_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {PDFButtonColors.FIND_BG_PRESSED};
            }}
            QPushButton:disabled {{
                background-color: {PDFButtonColors.DISABLED_BG};
                color: {PDFButtonColors.DISABLED_TEXT};
            }}
        """)

        # Connect click handler
        def on_find_clicked() -> None:
            self._handle_find_pdf_click(find_button, primary_button, card_data)

        find_button.clicked.connect(on_find_clicked)

        return find_button

    def _handle_find_pdf_click(
        self,
        find_button: QPushButton,
        primary_button: PDFButtonWidget,
        card_data: DocumentCardData
    ) -> None:
        """
        Handle click on the "Find PDF" button.

        Shows a progress dialog and initiates PDF discovery and download.

        Args:
            find_button: The "Find PDF" button (to disable during operation)
            primary_button: The primary PDF button to update on success
            card_data: Document card data with identifiers
        """
        # Disable button
        find_button.setEnabled(False)
        original_text = find_button.text()
        find_button.setText("🔍 Searching...")

        # Create and show progress dialog
        progress_dialog = PDFDiscoveryProgressDialog(
            doc_id=card_data.doc_id,
            title=card_data.title or "Unknown",
            parent=find_button.window()
        )
        progress_dialog.show()
        QApplication.processEvents()

        try:
            # Execute discovery with progress callback
            def progress_callback(stage: str, status: str) -> None:
                progress_dialog.add_step(stage, status)

            result = self._execute_pdf_discovery(card_data, progress_callback)

            if result and result.exists():
                # Success - update progress dialog
                progress_dialog.set_success(result)

                # Update primary button to VIEW state
                primary_button._transition_to_view(result)

                # Update database with pdf_filename
                document = {
                    'id': card_data.doc_id,
                    'doi': card_data.doi,
                    'pmid': card_data.pmid,
                    'pdf_url': card_data.pdf_url,
                    'title': card_data.title,
                    'authors': card_data.authors,
                    'year': card_data.year,
                    'pdf_filename': result.name,
                }
                self._update_pdf_filename_in_database(card_data.doc_id, result, document)

                # Update cache
                self._pdf_path_cache[card_data.doc_id] = result

                logger.info(
                    f"Successfully found and downloaded PDF for document "
                    f"{card_data.doc_id}: {result}"
                )

                # Emit signal
                primary_button.pdf_discovered.emit(result)

                # Update button to indicate success
                find_button.setText("✓ Found")
                find_button.setEnabled(False)

                # Close dialog after a short delay
                QTimer.singleShot(1500, progress_dialog.accept)

            else:
                # Discovery failed
                progress_dialog.set_failure("No PDF sources found")
                logger.warning(
                    f"PDF discovery failed for document {card_data.doc_id}"
                )
                find_button.setText("✗ Not Found")

                # Close dialog after a delay
                QTimer.singleShot(2000, progress_dialog.reject)

                # Re-enable button after a delay
                QTimer.singleShot(
                    PDFOperationSettings.BUTTON_RESET_DELAY_MS,
                    lambda: self._reset_find_button(find_button, original_text)
                )

        except Exception as e:
            error_msg = str(e)
            progress_dialog.set_failure(error_msg)
            logger.error(
                f"Error during PDF discovery for document {card_data.doc_id}: {e}"
            )
            find_button.setText("✗ Error")

            # Close dialog after a delay
            QTimer.singleShot(2000, progress_dialog.reject)

            # Re-enable button after a delay
            QTimer.singleShot(
                PDFOperationSettings.BUTTON_RESET_DELAY_MS,
                lambda: self._reset_find_button(find_button, original_text)
            )

            # Emit error signal through primary button
            primary_button.error_occurred.emit(error_msg)

    def _reset_find_button(self, button: QPushButton, original_text: str) -> None:
        """Reset the Find PDF button to its original state."""
        button.setText(original_text)
        button.setEnabled(True)

    def _execute_pdf_discovery(
        self,
        card_data: DocumentCardData,
        progress_callback: Optional[Callable[[str, str], None]] = None
    ) -> Optional[Path]:
        """
        Execute PDF discovery for a document.

        Uses FullTextFinder to discover and download PDFs from:
        1. CrossRef title search (to discover DOI if missing)
        2. PMC (PubMed Central)
        3. Unpaywall
        4. DOI resolution
        5. Direct URL
        6. OpenAthens (if enabled in config)

        Args:
            card_data: Document card data with identifiers
            progress_callback: Optional callback(stage, status) for progress updates

        Returns:
            Path to downloaded PDF if successful, None otherwise
        """
        from bmlibrarian.discovery import FullTextFinder, DocumentIdentifiers
        from bmlibrarian.discovery.resolvers import CrossRefTitleResolver
        from bmlibrarian.config import get_config, get_openathens_config

        # Get configuration
        config = get_config()
        openathens_config = get_openathens_config()
        discovery_config = config.get('discovery', {}) or {}

        # Track discovered DOI (from CrossRef title search)
        discovered_doi = card_data.doi

        # If no DOI but we have a title, try CrossRef title search first
        if not card_data.doi and card_data.title:
            if progress_callback:
                progress_callback('crossref_title', 'resolving')

            try:
                title_resolver = CrossRefTitleResolver(
                    timeout=discovery_config.get('timeout', 30),
                    min_similarity=discovery_config.get('crossref_min_similarity', 0.85)
                )

                identifiers = DocumentIdentifiers(
                    doc_id=card_data.doc_id,
                    title=card_data.title
                )

                result = title_resolver.resolve(identifiers)

                if result.status.value == 'success' and result.metadata.get('discovered_doi'):
                    discovered_doi = result.metadata['discovered_doi']
                    similarity = result.metadata.get('similarity', 0)

                    if progress_callback:
                        progress_callback('crossref_title', 'found')

                    logger.info(
                        f"Discovered DOI {discovered_doi} (similarity: {similarity:.2f}) "
                        f"for document {card_data.doc_id}"
                    )

                    # Update the database with discovered DOI
                    self._update_doi_in_database(card_data.doc_id, discovered_doi)
                else:
                    if progress_callback:
                        progress_callback('crossref_title', 'not_found')
                    logger.debug(
                        f"CrossRef title search did not find DOI for document {card_data.doc_id}"
                    )

            except Exception as e:
                if progress_callback:
                    progress_callback('crossref_title', 'error')
                logger.warning(f"CrossRef title search error: {e}")

        # Determine if OpenAthens should be used for discovery
        use_openathens_for_discovery = discovery_config.get(
            'use_openathens_proxy', False
        )

        # Build skip_resolvers list
        skip_resolvers = []
        if not use_openathens_for_discovery or not openathens_config.get('enabled', False):
            skip_resolvers.append('openathens')

        # Create finder with appropriate configuration
        finder = FullTextFinder(
            unpaywall_email=self.unpaywall_email or config.get('unpaywall_email'),
            openathens_proxy_url=(
                openathens_config.get('institution_url')
                if use_openathens_for_discovery and openathens_config.get('enabled', False)
                else None
            ),
            timeout=discovery_config.get('timeout', 30),
            prefer_open_access=discovery_config.get('prefer_open_access', True),
            skip_resolvers=skip_resolvers if skip_resolvers else None
        )

        # Set browser fallback config
        finder._browser_fallback_config = {
            'enabled': discovery_config.get('use_browser_fallback', True),
            'headless': discovery_config.get('browser_headless', True),
            'timeout': discovery_config.get('browser_timeout', 60000)
        }

        # Build document dictionary
        # Include both 'year' (int) and 'publication_date' (str) for compatibility
        # Use discovered_doi if we found one via CrossRef title search
        document = {
            'id': card_data.doc_id,
            'doi': discovered_doi,  # May be discovered from title search
            'pmid': card_data.pmid,
            'pdf_url': card_data.pdf_url,
            'title': card_data.title,
            'year': card_data.year,  # Pass as int for reliable year extraction
            'publication_date': str(card_data.year) if card_data.year else None,  # For backwards compat
        }

        # Execute discovery and download with progress callback
        # Enable content verification by default to catch wrong PDFs
        result = finder.download_for_document(
            document=document,
            output_dir=self.base_pdf_dir,
            use_browser_fallback=discovery_config.get('use_browser_fallback', True),
            progress_callback=progress_callback,
            verify_content=discovery_config.get('verify_content', True),
            delete_on_mismatch=discovery_config.get('delete_on_mismatch', False)
        )

        # Check for verification failure
        if result.verified is False:
            logger.warning(
                f"PDF verification FAILED for document {card_data.doc_id}: "
                f"{result.verification_warnings}"
            )
            # Still return the path but log the mismatch
            # The file is kept for manual review unless delete_on_mismatch is True

        if result.success and result.file_path:
            # If we got full text from a PMC package, store it in the database
            if result.full_text:
                self._update_full_text_in_database(card_data.doc_id, result.full_text)

            return Path(result.file_path)

        logger.warning(
            f"PDF discovery failed for document {card_data.doc_id}: "
            f"{result.error_message}"
        )
        return None

    def _update_doi_in_database(self, doc_id: int, doi: str) -> None:
        """
        Update the DOI in the database after discovering it via CrossRef.

        Args:
            doc_id: Document ID
            doi: Discovered DOI
        """
        try:
            from bmlibrarian.database import get_db_manager
            db_manager = get_db_manager()

            with db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE document SET doi = %s WHERE id = %s AND doi IS NULL",
                        (doi, doc_id)
                    )
                    if cur.rowcount > 0:
                        conn.commit()
                        logger.info(
                            f"Updated document.doi for doc {doc_id}: {doi}"
                        )
                    else:
                        logger.debug(
                            f"Document {doc_id} already has a DOI, not updating"
                        )

        except Exception as e:
            logger.error(
                f"Failed to update DOI in database for document {doc_id}: {e}"
            )
            # Don't raise - the discovery can still continue

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
                    card_data.pdf_path,
                    card_data.pdf_filename
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

                # Always use discovery workflow - it includes direct URL as a source
                # and provides content verification to catch wrong PDFs
                if self.pdf_manager and hasattr(self.pdf_manager, 'download_pdf_with_discovery'):
                    logger.info(f"Using discovery workflow for document {card_data.doc_id}")

                    # Get parent widget for GUI dialogs
                    parent_widget = self._parent if hasattr(self, '_parent') else None

                    pdf_path = self.pdf_manager.download_pdf_with_discovery(
                        document,
                        use_browser_fallback=True,
                        unpaywall_email=self.unpaywall_email,
                        verify_content=True,  # Verify PDF matches expected document
                        delete_on_mismatch=False,  # Don't auto-delete, prompt user instead
                        prompt_on_mismatch=True,  # Show verification dialog on mismatch
                        parent_widget=parent_widget,  # Parent for GUI dialog
                        max_retries=3  # Allow user to retry up to 3 times
                    )

                    if pdf_path and pdf_path.exists():
                        # Update database with pdf_filename
                        self._update_pdf_filename_in_database(card_data.doc_id, pdf_path, document)
                        # Update cache
                        self._pdf_path_cache[card_data.doc_id] = pdf_path
                        logger.info(f"Downloaded PDF via discovery for document {card_data.doc_id}: {pdf_path}")
                        return pdf_path

                    # Discovery failed or user rejected - provide helpful error message
                    error_msg = f"Failed to download PDF for document {card_data.doc_id}"
                    if card_data.pdf_url:
                        if "oup.com" in card_data.pdf_url or "springer" in card_data.pdf_url:
                            error_msg += " (Access restricted, likely requires institutional subscription)"
                        else:
                            error_msg += f" - no sources found, all failed, or user rejected"
                    raise FileNotFoundError(error_msg)

                raise ValueError("No PDF manager configured for fetch")

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

    def _handle_pdf_uploaded(self, source_path: Path, card_data: DocumentCardData) -> None:
        """
        Handle PDF upload by copying to library directory and updating database.

        This method is called when a PDF is uploaded via the file dialog. It:
        1. Copies the PDF to the year-organized directory structure (YYYY/filename.pdf)
        2. Updates the database pdf_filename column with the relative path

        Args:
            source_path: Path to the uploaded PDF file (user's original location)
            card_data: Document card data with doc_id, year, etc.
        """
        import shutil

        try:
            doc_id = card_data.doc_id
            year = card_data.year

            # Determine target directory (year-based organization)
            if year:
                year_dir = self.base_pdf_dir / str(year)
            else:
                year_dir = self.base_pdf_dir / "unknown_year"

            year_dir.mkdir(parents=True, exist_ok=True)

            # Generate target filename - use the original filename
            target_filename = source_path.name
            target_path = year_dir / target_filename

            # Handle filename collisions by adding doc_id suffix
            if target_path.exists() and target_path != source_path:
                stem = source_path.stem
                suffix = source_path.suffix
                target_filename = f"{stem}_{doc_id}{suffix}"
                target_path = year_dir / target_filename

            # Copy the file (don't move, user might want to keep their original)
            logger.info(f"[PDF UPLOAD] Copying {source_path} to {target_path}")
            shutil.copy2(source_path, target_path)

            # Calculate relative path for database
            relative_path = f"{year or 'unknown_year'}/{target_filename}"

            # Update database
            logger.info(f"[PDF UPLOAD] Updating database for doc {doc_id}: pdf_filename = {relative_path}")

            document = {
                'id': doc_id,
                'pdf_filename': target_filename,
                'year': year,
            }
            self._update_pdf_filename_in_database(doc_id, target_path, document)

            # Update cache
            self._pdf_path_cache[doc_id] = target_path

            logger.info(f"[PDF UPLOAD] Successfully uploaded and registered PDF for document {doc_id}")

        except Exception as e:
            logger.error(f"[PDF UPLOAD] Failed to process uploaded PDF for document {card_data.doc_id}: {e}")
            import traceback
            traceback.print_exc()
            # Re-raise so the error signal is emitted
            raise

    def _update_full_text_in_database(self, doc_id: int, full_text: str) -> None:
        """
        Update the full_text column in the database after extracting from NXML.

        Args:
            doc_id: Document ID
            full_text: Extracted full text content from NXML
        """
        try:
            from bmlibrarian.database import get_db_manager
            db_manager = get_db_manager()

            with db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE document SET full_text = %s WHERE id = %s",
                        (full_text, doc_id)
                    )
                    conn.commit()
                    logger.info(
                        f"Updated document.full_text for doc {doc_id} "
                        f"({len(full_text)} chars)"
                    )

        except Exception as e:
            logger.error(
                f"Failed to update full_text in database for document {doc_id}: {e}"
            )
            # Don't raise - the PDF was successfully downloaded, database update is secondary

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
