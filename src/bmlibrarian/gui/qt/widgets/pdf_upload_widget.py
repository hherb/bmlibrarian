"""
Reusable PDF Upload Widget for BMLibrarian Qt GUI.

Provides a complete PDF upload and document matching interface with:
- Split view: PDF viewer (left) | Metadata panel (right)
- Fast regex-based identifier extraction
- Quick database lookup with fallback to LLM extraction
- Multiple match display with user selection
- Document creation for unmatched PDFs

Usage:
    from bmlibrarian.gui.qt.widgets import PDFUploadWidget

    widget = PDFUploadWidget()
    widget.document_selected.connect(on_document_selected)
    widget.document_created.connect(on_document_created)
"""

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QLabel,
    QPushButton,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QGroupBox,
    QCheckBox,
    QFileDialog,
    QMessageBox,
    QFrame,
    QDialog,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent

from ..resources.styles import get_font_scale, StylesheetGenerator
from ..resources.styles.theme_colors import ThemeColors
from .pdf_viewer import PDFViewerWidget
from .pdf_upload_workers import (
    QuickExtractWorker,
    LLMExtractWorker,
    QuickMatchResult,
    LLMExtractResult,
)
from .validators import (
    validate_pdf_file,
    classify_extraction_error,
    ValidationStatus,
    WORKER_TERMINATE_TIMEOUT_MS,
)
from .document_create_dialog import DocumentCreateDialog

logger = logging.getLogger(__name__)


# =============================================================================
# UI Layout Constants
# =============================================================================
SPLITTER_RATIO_PDF = 60  # PDF viewer gets 60% width
SPLITTER_RATIO_METADATA = 40  # Metadata panel gets 40% width
DEFAULT_WINDOW_WIDTH = 1200
DEFAULT_WINDOW_HEIGHT = 800

# =============================================================================
# Worker Cleanup Constants
# =============================================================================
WORKER_FORCE_TERMINATE_TIMEOUT_MS = 1000  # Timeout before forcing terminate


class PDFUploadWidget(QWidget):
    """
    Reusable PDF upload widget with split PDF viewer and metadata panel.

    Provides a complete workflow for:
    1. PDF selection and viewing
    2. Fast identifier extraction (regex)
    3. Quick database lookup
    4. LLM-based fallback extraction
    5. Document matching and selection
    6. New document creation

    Signals:
        document_selected: Emitted when user selects an existing document (doc_id: int)
        document_created: Emitted when a new document is created (doc_id: int)
        pdf_loaded: Emitted when a PDF is loaded (path: str)
        cancelled: Emitted when user cancels the operation
    """

    document_selected = Signal(int)
    document_created = Signal(int)
    pdf_loaded = Signal(str)
    cancelled = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize the PDF upload widget.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)

        # Get scaling and style utilities
        self.scale = get_font_scale()
        self.style_gen = StylesheetGenerator()

        # State
        self._pdf_path: Optional[Path] = None
        self._extracted_text: Optional[str] = None
        self._current_metadata: Optional[dict] = None
        self._selected_document: Optional[dict] = None
        self._quick_worker: Optional[QuickExtractWorker] = None
        self._llm_worker: Optional[LLMExtractWorker] = None

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        """Setup the user interface."""
        s = self.scale

        layout = QVBoxLayout(self)
        layout.setContentsMargins(s['padding_medium'], s['padding_medium'],
                                  s['padding_medium'], s['padding_medium'])
        layout.setSpacing(s['spacing_medium'])

        # Main splitter
        self.splitter = QSplitter(Qt.Horizontal)

        # Left panel: PDF Viewer
        self.pdf_viewer = PDFViewerWidget()
        self.splitter.addWidget(self.pdf_viewer)

        # Right panel: Metadata and controls
        right_panel = self._create_metadata_panel()
        self.splitter.addWidget(right_panel)

        # Set splitter proportions (60/40)
        self.splitter.setSizes([SPLITTER_RATIO_PDF, SPLITTER_RATIO_METADATA])

        layout.addWidget(self.splitter, stretch=1)

    def _create_metadata_panel(self) -> QWidget:
        """Create the right-side metadata panel."""
        s = self.scale

        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(s['spacing_medium'])

        # File selection section
        file_group = QGroupBox("PDF File")
        file_layout = QHBoxLayout(file_group)

        self.file_path_edit = QLineEdit()
        self.file_path_edit.setReadOnly(True)
        self.file_path_edit.setPlaceholderText("No file selected")
        file_layout.addWidget(self.file_path_edit, stretch=1)

        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self._on_browse_clicked)
        file_layout.addWidget(self.browse_btn)

        layout.addWidget(file_group)

        # Status section
        status_group = QGroupBox("Status")
        status_layout = QVBoxLayout(status_group)

        self.status_label = QLabel("Select a PDF file to begin")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            self.style_gen.label_stylesheet(
                font_size_key='font_small',
                color=ThemeColors.TEXT_MUTED
            )
        )
        status_layout.addWidget(self.status_label)

        # Quick match result frame
        self.quick_match_frame = QFrame()
        self.quick_match_frame.setFrameStyle(QFrame.Box | QFrame.Plain)
        self.quick_match_frame.setStyleSheet(
            self.style_gen.custom(
                f"QFrame {{ "
                f"background-color: {ThemeColors.SUCCESS_BG}; "
                f"border: 1px solid {ThemeColors.SUCCESS_BORDER}; "
                f"border-radius: {{radius_small}}px; "
                f"padding: {{padding_small}}px; "
                f"}}"
            )
        )
        quick_match_layout = QVBoxLayout(self.quick_match_frame)

        self.quick_match_label = QLabel("Quick match found!")
        self.quick_match_label.setStyleSheet(
            self.style_gen.label_stylesheet(
                font_size_key='font_medium',
                color=ThemeColors.SUCCESS_TEXT,
                bold=True
            )
        )
        quick_match_layout.addWidget(self.quick_match_label)

        self.quick_match_title = QLabel("")
        self.quick_match_title.setWordWrap(True)
        quick_match_layout.addWidget(self.quick_match_title)

        quick_match_btns = QHBoxLayout()
        self.accept_quick_btn = QPushButton("Use This Match")
        self.accept_quick_btn.clicked.connect(self._on_accept_quick_match)
        quick_match_btns.addWidget(self.accept_quick_btn)

        self.try_llm_btn = QPushButton("Search for More Matches")
        self.try_llm_btn.clicked.connect(self._on_try_llm)
        quick_match_btns.addWidget(self.try_llm_btn)

        quick_match_layout.addLayout(quick_match_btns)
        self.quick_match_frame.hide()
        status_layout.addWidget(self.quick_match_frame)

        layout.addWidget(status_group)

        # Extracted metadata section
        metadata_group = QGroupBox("Extracted Metadata")
        metadata_layout = QVBoxLayout(metadata_group)

        # Title
        metadata_layout.addWidget(QLabel("Title:"))
        self.title_edit = QLineEdit()
        self.title_edit.setReadOnly(True)
        metadata_layout.addWidget(self.title_edit)

        # Authors
        metadata_layout.addWidget(QLabel("Authors:"))
        self.authors_edit = QLineEdit()
        self.authors_edit.setReadOnly(True)
        metadata_layout.addWidget(self.authors_edit)

        # DOI and PMID in a row
        doi_pmid_layout = QHBoxLayout()

        doi_layout = QVBoxLayout()
        doi_layout.addWidget(QLabel("DOI:"))
        self.doi_edit = QLineEdit()
        self.doi_edit.setReadOnly(True)
        doi_layout.addWidget(self.doi_edit)
        doi_pmid_layout.addLayout(doi_layout)

        pmid_layout = QVBoxLayout()
        pmid_layout.addWidget(QLabel("PMID:"))
        self.pmid_edit = QLineEdit()
        self.pmid_edit.setReadOnly(True)
        pmid_layout.addWidget(self.pmid_edit)
        doi_pmid_layout.addLayout(pmid_layout)

        metadata_layout.addLayout(doi_pmid_layout)

        layout.addWidget(metadata_group)

        # Database matches section
        matches_group = QGroupBox("Database Matches")
        matches_layout = QVBoxLayout(matches_group)

        self.matches_tree = QTreeWidget()
        self.matches_tree.setHeaderLabels(["Title", "DOI/PMID", "Year", "Similarity"])
        self.matches_tree.setColumnCount(4)
        self.matches_tree.setRootIsDecorated(False)
        self.matches_tree.setAlternatingRowColors(True)
        self.matches_tree.itemSelectionChanged.connect(self._on_match_selection_changed)
        matches_layout.addWidget(self.matches_tree)

        layout.addWidget(matches_group, stretch=1)

        # Options section
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout(options_group)

        self.ingest_checkbox = QCheckBox("Ingest PDF (store and create embeddings)")
        self.ingest_checkbox.setChecked(False)
        self.ingest_checkbox.setToolTip(
            "If checked, the PDF will be stored in the library and text embeddings "
            "will be created for semantic search."
        )
        options_layout.addWidget(self.ingest_checkbox)

        layout.addWidget(options_group)

        # Action buttons
        btn_layout = QHBoxLayout()

        self.use_match_btn = QPushButton("Use Selected Match")
        self.use_match_btn.setEnabled(False)
        self.use_match_btn.clicked.connect(self._on_use_match)
        btn_layout.addWidget(self.use_match_btn)

        self.create_new_btn = QPushButton("Create New Document")
        self.create_new_btn.setEnabled(False)
        self.create_new_btn.clicked.connect(self._on_create_new)
        btn_layout.addWidget(self.create_new_btn)

        btn_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self.cancel_btn)

        layout.addLayout(btn_layout)

        return panel

    def _connect_signals(self):
        """Connect internal signals."""
        pass  # Workers are connected when created

    def _on_browse_clicked(self):
        """Handle browse button click."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select PDF File",
            "",
            "PDF Files (*.pdf);;All Files (*)"
        )

        if file_path:
            self.load_pdf(file_path)

    def load_pdf(self, pdf_path: str | Path):
        """
        Load a PDF file for analysis.

        Validates the file before loading and warns about large files.

        Args:
            pdf_path: Path to PDF file
        """
        self._pdf_path = Path(pdf_path)

        # Validate PDF file (returns 3-tuple with status)
        is_valid, message, status = validate_pdf_file(self._pdf_path)

        if status == ValidationStatus.ERROR:
            if message and "does not exist" in message:
                QMessageBox.critical(self, "Error", f"File not found: {pdf_path}")
            else:
                QMessageBox.critical(self, "Invalid File", message or "Unknown error")
            return

        # Show warning for large files but allow proceeding
        if status == ValidationStatus.WARNING:
            reply = QMessageBox.warning(
                self,
                "Large File Warning",
                f"{message}\n\nDo you want to continue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            if reply != QMessageBox.Yes:
                return

        # Update UI
        self.file_path_edit.setText(str(self._pdf_path))
        self._clear_results()

        # Load PDF in viewer
        self.pdf_viewer.load_pdf(self._pdf_path)
        self.pdf_loaded.emit(str(self._pdf_path))

        # Start quick extraction
        self._start_quick_extraction()

    def _start_quick_extraction(self):
        """Start the quick extraction worker."""
        if not self._pdf_path:
            return

        self._update_status("Extracting text and searching for identifiers...")

        # Create and start worker
        self._quick_worker = QuickExtractWorker(self._pdf_path)
        self._quick_worker.quick_match_found.connect(self._on_quick_match_found)
        self._quick_worker.no_quick_match.connect(self._on_no_quick_match)
        self._quick_worker.error_occurred.connect(self._on_extraction_error)
        self._quick_worker.status_update.connect(self._update_status)
        self._quick_worker.start()

    def _start_llm_extraction(self):
        """Start the LLM extraction worker."""
        if not self._extracted_text:
            self._update_status("No text available for LLM extraction")
            return

        self._update_status("Extracting metadata with LLM (this may take a moment)...")
        self.quick_match_frame.hide()

        # Create and start worker
        self._llm_worker = LLMExtractWorker(self._extracted_text)
        self._llm_worker.extraction_complete.connect(self._on_llm_extraction_complete)
        self._llm_worker.error_occurred.connect(self._on_extraction_error)
        self._llm_worker.status_update.connect(self._update_status)
        self._llm_worker.start()

    def _on_quick_match_found(self, result: QuickMatchResult):
        """Handle quick match found."""
        self._extracted_text = result.extracted_text

        if result.identifiers:
            self.doi_edit.setText(result.identifiers.doi or "")
            self.pmid_edit.setText(result.identifiers.pmid or "")

        if result.document:
            self._selected_document = result.document
            self._show_quick_match(result.document)
            self._update_status("Quick match found! Review and confirm below.")
        else:
            self._on_no_quick_match(result)

    def _on_no_quick_match(self, result: QuickMatchResult):
        """Handle no quick match - proceed to LLM extraction."""
        self._extracted_text = result.extracted_text

        if result.identifiers:
            self.doi_edit.setText(result.identifiers.doi or "")
            self.pmid_edit.setText(result.identifiers.pmid or "")

            if result.identifiers.has_identifiers():
                self._update_status(
                    f"Found identifiers (DOI: {result.identifiers.doi or 'None'}, "
                    f"PMID: {result.identifiers.pmid or 'None'}) but no database match. "
                    "Proceeding with LLM extraction..."
                )

        # Automatically proceed to LLM extraction
        self._start_llm_extraction()

    def _on_llm_extraction_complete(self, result: LLMExtractResult):
        """Handle LLM extraction completion."""
        if not result.success:
            self._update_status(f"Extraction failed: {result.error or 'Unknown error'}")
            self.create_new_btn.setEnabled(True)
            return

        self._current_metadata = result.metadata

        # Update metadata fields
        if result.metadata:
            self.title_edit.setText(result.metadata.get('title') or "")
            authors = result.metadata.get('authors', [])
            self.authors_edit.setText(", ".join(authors) if authors else "")

            # Only update DOI/PMID if not already set by regex
            if not self.doi_edit.text() and result.metadata.get('doi'):
                self.doi_edit.setText(result.metadata.get('doi'))
            if not self.pmid_edit.text() and result.metadata.get('pmid'):
                self.pmid_edit.setText(result.metadata.get('pmid'))

        # Populate matches tree
        self.matches_tree.clear()

        if result.document:
            self._add_match_to_tree(result.document, is_best=True)

        if result.alternatives:
            for alt in result.alternatives:
                self._add_match_to_tree(alt, is_best=False)

        # Update status
        match_count = (1 if result.document else 0) + len(result.alternatives or [])
        if match_count > 0:
            self._update_status(f"Found {match_count} potential match(es). Select one or create new.")
        else:
            self._update_status("No matches found. You can create a new document.")

        self.create_new_btn.setEnabled(True)

    def _on_extraction_error(self, error: str):
        """
        Handle extraction error with user-friendly messages.

        Classifies the error type and provides specific guidance to the user.
        """
        # Classify the error for better user guidance
        error_category, user_message = classify_extraction_error(Exception(error))

        self._update_status(f"Error ({error_category}): {error}")

        QMessageBox.warning(
            self,
            "Extraction Error",
            f"{user_message}\n\n"
            "You can still manually enter metadata using the 'Create New Document' button."
        )

        # Enable manual entry as fallback
        self.create_new_btn.setEnabled(True)

    def _show_quick_match(self, document: dict):
        """Show the quick match result."""
        title = document.get('title', 'Unknown title')
        doc_id = document.get('id', '?')

        self.quick_match_title.setText(
            f"<b>{title[:100]}{'...' if len(title) > 100 else ''}</b><br>"
            f"<small>Document ID: {doc_id}</small>"
        )
        self.quick_match_frame.show()

    def _add_match_to_tree(self, document: dict, is_best: bool = False):
        """Add a document match to the tree widget."""
        item = QTreeWidgetItem()

        # Title
        title = document.get('title', 'Unknown')
        if len(title) > 80:
            title = title[:77] + "..."
        item.setText(0, title)

        # DOI/PMID
        identifier = document.get('doi') or document.get('external_id') or ""
        item.setText(1, identifier)

        # Year
        year = document.get('year')
        if not year and document.get('publication_date'):
            try:
                year = document['publication_date'].year
            except AttributeError:
                pass
        item.setText(2, str(year) if year else "")

        # Similarity score
        similarity = document.get('similarity')
        if similarity is not None:
            item.setText(3, f"{similarity:.2f}")

        # Store document data
        item.setData(0, Qt.UserRole, document)

        # Highlight best match
        if is_best:
            for col in range(4):
                item.setBackground(col, Qt.green)

        self.matches_tree.addTopLevelItem(item)

        # Resize columns
        for col in range(4):
            self.matches_tree.resizeColumnToContents(col)

    def _on_match_selection_changed(self):
        """Handle match selection change."""
        selected = self.matches_tree.selectedItems()
        if selected:
            document = selected[0].data(0, Qt.UserRole)
            self._selected_document = document
            self.use_match_btn.setEnabled(True)
        else:
            self._selected_document = None
            self.use_match_btn.setEnabled(False)

    def _on_accept_quick_match(self):
        """Accept the quick match."""
        if self._selected_document:
            doc_id = self._selected_document.get('id')
            if doc_id:
                self.document_selected.emit(doc_id)

    def _on_try_llm(self):
        """Try LLM extraction for more matches."""
        self._start_llm_extraction()

    def _on_use_match(self):
        """Use the selected match."""
        if self._selected_document:
            doc_id = self._selected_document.get('id')
            if doc_id:
                self.document_selected.emit(doc_id)

    def _on_create_new(self):
        """
        Create a new document with pre-filled metadata.

        Opens a dialog pre-populated with extracted metadata (DOI, PMID, title,
        authors, etc.) allowing the user to review and edit before saving.
        """
        # Gather all extracted metadata
        metadata = {}

        # From LLM extraction
        if self._current_metadata:
            metadata.update(self._current_metadata)

        # From UI fields (may override/supplement LLM extraction)
        if self.title_edit.text().strip():
            metadata['title'] = self.title_edit.text().strip()
        if self.authors_edit.text().strip():
            metadata['authors'] = self.authors_edit.text().strip()
        if self.doi_edit.text().strip():
            metadata['doi'] = self.doi_edit.text().strip()
        if self.pmid_edit.text().strip():
            metadata['pmid'] = self.pmid_edit.text().strip()

        # Create and show the dialog
        dialog = DocumentCreateDialog(
            parent=self,
            metadata=metadata,
            pdf_path=self._pdf_path,
        )

        if dialog.exec() == QDialog.Accepted:
            doc_id = dialog.get_document_id()
            if doc_id:
                self._update_status(f"Document created successfully (ID: {doc_id})")
                self.document_created.emit(doc_id)

    def _on_cancel(self):
        """Cancel the operation."""
        self._cleanup_workers()
        self.cancelled.emit()

    def _update_status(self, message: str):
        """Update the status label."""
        self.status_label.setText(message)
        logger.debug(f"PDF Upload status: {message}")

    def _clear_results(self):
        """Clear all result fields."""
        self._extracted_text = None
        self._current_metadata = None
        self._selected_document = None

        self.title_edit.clear()
        self.authors_edit.clear()
        self.doi_edit.clear()
        self.pmid_edit.clear()
        self.matches_tree.clear()

        self.quick_match_frame.hide()
        self.use_match_btn.setEnabled(False)
        self.create_new_btn.setEnabled(False)

        self._update_status("Processing...")

    def _cleanup_workers(self):
        """
        Safely terminate any running worker threads.

        Uses a two-stage termination approach:
        1. Request thread termination via requestInterruption()
        2. Wait for graceful shutdown
        3. If still running, force terminate via terminate()

        Clears worker references after termination for garbage collection.
        """
        workers = [
            ('quick_worker', self._quick_worker),
            ('llm_worker', self._llm_worker),
        ]

        for name, worker in workers:
            if worker is not None and worker.isRunning():
                logger.info(f"Requesting {name} thread interruption...")

                # Stage 1: Request graceful interruption
                worker.requestInterruption()

                # Wait for graceful termination
                if worker.wait(WORKER_TERMINATE_TIMEOUT_MS):
                    logger.debug(f"{name} terminated gracefully")
                    continue

                # Stage 2: Force termination if still running
                logger.warning(
                    f"{name} did not respond to interruption within "
                    f"{WORKER_TERMINATE_TIMEOUT_MS}ms, forcing termination"
                )
                worker.terminate()

                # Give it a short time to actually terminate
                if not worker.wait(WORKER_FORCE_TERMINATE_TIMEOUT_MS):
                    logger.error(
                        f"{name} could not be terminated. "
                        "This may indicate a thread that is stuck in a blocking "
                        "system call. The application may need to be restarted."
                    )

        # Clear references for garbage collection
        self._quick_worker = None
        self._llm_worker = None

    def should_ingest(self) -> bool:
        """Check if PDF ingestion is requested."""
        return self.ingest_checkbox.isChecked()

    def get_pdf_path(self) -> Optional[Path]:
        """Get the current PDF path."""
        return self._pdf_path

    def get_selected_document(self) -> Optional[dict]:
        """Get the currently selected document."""
        return self._selected_document

    def get_extracted_metadata(self) -> Optional[dict]:
        """Get the extracted metadata."""
        return self._current_metadata

    def closeEvent(self, event: QCloseEvent):
        """
        Handle widget close event.

        Ensures worker threads are properly terminated before closing.

        Args:
            event: The close event
        """
        self._cleanup_workers()
        super().closeEvent(event)
