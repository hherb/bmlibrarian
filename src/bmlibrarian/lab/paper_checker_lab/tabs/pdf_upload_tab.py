"""
PaperChecker Laboratory - PDF Upload Tab

Tab widget for uploading PDFs and extracting abstracts for fact-checking.
Features a split view with PDF viewer on the left and extraction controls on the right.
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QGroupBox,
    QMessageBox,
    QFileDialog,
    QSizePolicy,
    QProgressBar,
    QSplitter,
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QCloseEvent

from bmlibrarian.gui.qt.resources.styles.dpi_scale import get_font_scale
from bmlibrarian.gui.qt.resources.styles.stylesheet_generator import get_stylesheet_generator
from bmlibrarian.gui.qt.widgets import PDFViewerWidget, validate_pdf_file, ValidationStatus

from ..constants import (
    COLOR_PRIMARY,
    COLOR_SUCCESS,
    COLOR_GREY_600,
    COLOR_METADATA_BG,
    SPLITTER_RATIO_PDF,
    SPLITTER_RATIO_CONTROLS,
    WORKER_TERMINATE_TIMEOUT_MS,
)
from ..widgets import StatusSpinnerWidget
from ..worker import PDFAnalysisWorker


logger = logging.getLogger(__name__)


class PDFUploadTab(QWidget):
    """
    Tab widget for PDF upload and abstract extraction.

    Features a split-view layout with:
    - Left panel: PDF viewer for visual inspection
    - Right panel: Extraction controls, metadata display, and abstract editing

    Allows users to upload a PDF, extract the abstract using LLM,
    review/edit the extracted text, and proceed to fact-checking.

    Signals:
        abstract_extracted: Emitted when abstract is extracted from PDF.
            Args: abstract (str), metadata (dict)
        check_requested: Emitted when user requests direct check.
            Args: abstract (str), metadata (dict)
    """

    abstract_extracted = Signal(str, dict)  # (abstract, metadata)
    check_requested = Signal(str, dict)  # (abstract, metadata)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize PDF upload tab.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        self.scale = get_font_scale()
        self.styles = get_stylesheet_generator()
        self._current_pdf_path: Optional[Path] = None
        self._extracted_metadata: Dict[str, Any] = {}
        self._analysis_worker: Optional[PDFAnalysisWorker] = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup tab user interface with split view."""
        layout = QVBoxLayout(self)
        layout.setSpacing(self.scale['spacing_small'])
        layout.setContentsMargins(
            self.scale['padding_medium'],
            self.scale['padding_medium'],
            self.scale['padding_medium'],
            self.scale['padding_medium']
        )

        # Main splitter for PDF viewer and controls
        self._splitter = QSplitter(Qt.Horizontal)

        # Left panel: PDF Viewer
        self._pdf_viewer = PDFViewerWidget()
        self._splitter.addWidget(self._pdf_viewer)

        # Right panel: Controls
        right_panel = self._create_controls_panel()
        self._splitter.addWidget(right_panel)

        # Set splitter proportions (50/50)
        self._splitter.setSizes([SPLITTER_RATIO_PDF, SPLITTER_RATIO_CONTROLS])

        layout.addWidget(self._splitter, stretch=1)

    def _create_controls_panel(self) -> QWidget:
        """
        Create the right-side controls panel.

        Returns:
            QWidget: The controls panel widget
        """
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(self.scale['spacing_medium'])
        layout.setContentsMargins(0, 0, 0, 0)

        # File selection section
        file_group = QGroupBox("PDF File")
        file_layout = QVBoxLayout()

        # Instructions
        instructions = QLabel(
            "Upload a PDF of a medical research paper. The abstract will be "
            "automatically extracted using AI, and you can review/edit it "
            "before fact-checking."
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet(self.styles.label_stylesheet(color=COLOR_GREY_600))
        file_layout.addWidget(instructions)

        # File path row
        path_layout = QHBoxLayout()

        self._path_label = QLabel("No file selected")
        self._path_label.setStyleSheet(self.styles.label_stylesheet(color=COLOR_GREY_600))
        path_layout.addWidget(self._path_label, stretch=1)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_file)
        path_layout.addWidget(browse_btn)

        file_layout.addLayout(path_layout)

        # Analyze button
        self._analyze_btn = QPushButton("Analyze PDF")
        self._analyze_btn.setToolTip("Extract abstract and metadata from PDF using AI")
        self._analyze_btn.clicked.connect(self._analyze_pdf)
        self._analyze_btn.setEnabled(False)
        self._analyze_btn.setStyleSheet(self.styles.button_stylesheet(bg_color=COLOR_PRIMARY))
        file_layout.addWidget(self._analyze_btn)

        file_group.setLayout(file_layout)
        layout.addWidget(file_group)

        # Status section
        status_group = QGroupBox("Analysis Status")
        status_layout = QVBoxLayout()

        self._status_spinner = StatusSpinnerWidget(self)
        status_layout.addWidget(self._status_spinner)

        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)
        status_layout.addWidget(self._progress_bar)

        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        # Extracted content section
        content_group = QGroupBox("Extracted Content")
        content_layout = QVBoxLayout()

        # Metadata display
        # Note: Using inline stylesheet as StylesheetGenerator doesn't support
        # panel labels with backgrounds. All values are from constants/DPI scale.
        self._metadata_label = QLabel("")
        self._metadata_label.setWordWrap(True)
        self._metadata_label.setVisible(False)
        self._metadata_label.setStyleSheet(
            f"QLabel {{ "
            f"background-color: {COLOR_METADATA_BG}; "
            f"padding: {self.scale['padding_medium']}px; "
            f"border-radius: {self.scale['border_radius']}px; "
            f"}}"
        )
        content_layout.addWidget(self._metadata_label)

        # Abstract text (editable)
        abstract_label = QLabel("Extracted Abstract (you can edit before checking):")
        content_layout.addWidget(abstract_label)

        self._abstract_edit = QTextEdit()
        self._abstract_edit.setPlaceholderText(
            "The extracted abstract will appear here after PDF analysis..."
        )
        self._abstract_edit.setMinimumHeight(self.scale['line_height'] * 6)
        self._abstract_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        content_layout.addWidget(self._abstract_edit, stretch=1)

        content_group.setLayout(content_layout)
        layout.addWidget(content_group, stretch=1)

        # Action buttons
        button_layout = QHBoxLayout()

        self._use_in_input_btn = QPushButton("Use in Input Tab")
        self._use_in_input_btn.setToolTip("Copy extracted abstract to the Input tab for further editing")
        self._use_in_input_btn.clicked.connect(self._use_in_input_tab)
        self._use_in_input_btn.setEnabled(False)
        button_layout.addWidget(self._use_in_input_btn)

        self._check_btn = QPushButton("Check Abstract")
        self._check_btn.setToolTip("Start fact-checking the extracted abstract")
        self._check_btn.clicked.connect(self._on_check_clicked)
        self._check_btn.setEnabled(False)
        self._check_btn.setStyleSheet(self.styles.button_stylesheet(bg_color=COLOR_SUCCESS))
        self._check_btn.setMinimumHeight(self.scale['control_height_large'])
        button_layout.addWidget(self._check_btn)

        self._clear_btn = QPushButton("Clear")
        self._clear_btn.clicked.connect(self._clear_all)
        button_layout.addWidget(self._clear_btn)

        button_layout.addStretch()

        layout.addLayout(button_layout)

        return panel

    def _browse_file(self) -> None:
        """Open file browser for PDF selection."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select PDF File",
            "",
            "PDF Files (*.pdf);;All Files (*)"
        )

        if file_path:
            self._load_pdf(file_path)

    def _load_pdf(self, file_path: str) -> None:
        """
        Load a PDF file for analysis.

        Validates the file and loads it into the viewer.

        Args:
            file_path: Path to the PDF file
        """
        pdf_path = Path(file_path)

        # Validate PDF file
        is_valid, message, status = validate_pdf_file(pdf_path)

        if status == ValidationStatus.ERROR:
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

        # Store path and update UI
        self._current_pdf_path = pdf_path
        self._path_label.setText(pdf_path.name)
        self._path_label.setToolTip(str(pdf_path))

        # Load PDF into viewer
        self._pdf_viewer.load_pdf(pdf_path)

        # Enable analyze button
        self._analyze_btn.setEnabled(True)
        self._status_spinner.reset()

        logger.info(f"PDF loaded: {file_path}")

    def _analyze_pdf(self) -> None:
        """Start PDF analysis."""
        if not self._current_pdf_path:
            return

        # Disable controls during analysis
        self._analyze_btn.setEnabled(False)
        self._check_btn.setEnabled(False)
        self._use_in_input_btn.setEnabled(False)

        # Start spinner and show progress
        self._status_spinner.start_spinner()
        self._status_spinner.set_status("Starting PDF analysis...")
        self._progress_bar.setVisible(True)
        self._progress_bar.setRange(0, 0)  # Indeterminate

        # Start worker
        self._analysis_worker = PDFAnalysisWorker(str(self._current_pdf_path))
        self._analysis_worker.progress_update.connect(self._on_progress_update)
        self._analysis_worker.analysis_complete.connect(self._on_analysis_complete)
        self._analysis_worker.analysis_error.connect(self._on_analysis_error)
        self._analysis_worker.start()

    def _on_progress_update(self, status: str) -> None:
        """
        Handle progress update from worker.

        Args:
            status: Status message
        """
        self._status_spinner.set_status(status)

    def _on_analysis_complete(self, result: dict) -> None:
        """
        Handle successful PDF analysis.

        Args:
            result: Analysis result dictionary
        """
        self._progress_bar.setVisible(False)
        self._status_spinner.set_complete("Analysis complete")

        # Store extracted metadata
        self._extracted_metadata = {
            'title': result.get('title', ''),
            'authors': result.get('authors', []),
            'year': result.get('year'),
            'pmid': result.get('pmid'),
            'doi': result.get('doi'),
            'journal': result.get('journal', ''),
            'pdf_path': str(self._current_pdf_path) if self._current_pdf_path else '',
        }

        # Display metadata
        self._show_metadata(result)

        # Populate abstract
        abstract = result.get('abstract', '')
        if abstract:
            self._abstract_edit.setPlainText(abstract)
            self._check_btn.setEnabled(True)
            self._use_in_input_btn.setEnabled(True)
            logger.info(f"Extracted abstract ({len(abstract)} chars) from PDF")
        else:
            self._abstract_edit.setPlainText("")
            QMessageBox.warning(
                self,
                "No Abstract Found",
                "The PDF was analyzed but no abstract could be identified.\n\n"
                "You can manually enter the abstract text."
            )

        self._analyze_btn.setEnabled(True)

    def _on_analysis_error(self, error: str) -> None:
        """
        Handle analysis error.

        Args:
            error: Error message
        """
        self._progress_bar.setVisible(False)
        self._status_spinner.set_error(f"Error: {error}")
        self._analyze_btn.setEnabled(True)

        QMessageBox.critical(
            self,
            "Analysis Error",
            f"Failed to analyze PDF:\n{error}"
        )
        logger.error(f"PDF analysis error: {error}")

    def _show_metadata(self, result: dict) -> None:
        """
        Display extracted metadata.

        Args:
            result: Analysis result dictionary
        """
        parts = []

        if result.get('title'):
            parts.append(f"<b>Title:</b> {result['title']}")

        if result.get('authors'):
            authors = result['authors']
            if isinstance(authors, list):
                authors = ', '.join(authors[:5])
                if len(result['authors']) > 5:
                    authors += ' et al.'
            parts.append(f"<b>Authors:</b> {authors}")

        if result.get('journal'):
            parts.append(f"<b>Journal:</b> {result['journal']}")

        if result.get('year'):
            parts.append(f"<b>Year:</b> {result['year']}")

        if result.get('pmid'):
            parts.append(f"<b>PMID:</b> {result['pmid']}")

        if result.get('doi'):
            parts.append(f"<b>DOI:</b> {result['doi']}")

        if result.get('extracted_text_length'):
            parts.append(f"<b>PDF Text:</b> {result['extracted_text_length']:,} characters")

        if parts:
            self._metadata_label.setText('<br>'.join(parts))
            self._metadata_label.setVisible(True)
        else:
            self._metadata_label.setVisible(False)

    def _use_in_input_tab(self) -> None:
        """Emit signal to use extracted abstract in input tab."""
        abstract = self._abstract_edit.toPlainText().strip()
        if abstract:
            self.abstract_extracted.emit(abstract, self._extracted_metadata.copy())

    def _on_check_clicked(self) -> None:
        """Handle check button click."""
        abstract = self._abstract_edit.toPlainText().strip()

        if not abstract:
            QMessageBox.warning(
                self,
                "No Abstract",
                "Please provide an abstract to check."
            )
            return

        # Emit check requested signal
        self.check_requested.emit(abstract, self._extracted_metadata.copy())

    def _clear_all(self) -> None:
        """Clear all inputs and results."""
        self._current_pdf_path = None
        self._extracted_metadata.clear()
        self._path_label.setText("No file selected")
        self._path_label.setToolTip("")
        self._abstract_edit.clear()
        self._metadata_label.setVisible(False)
        self._status_spinner.reset()
        self._progress_bar.setVisible(False)
        self._analyze_btn.setEnabled(False)
        self._check_btn.setEnabled(False)
        self._use_in_input_btn.setEnabled(False)

        # Clear PDF viewer
        self._pdf_viewer.clear()

    def set_enabled(self, enabled: bool) -> None:
        """
        Enable or disable the tab controls.

        Args:
            enabled: Whether controls should be enabled
        """
        self._analyze_btn.setEnabled(enabled and self._current_pdf_path is not None)
        self._check_btn.setEnabled(enabled and bool(self._abstract_edit.toPlainText().strip()))
        self._use_in_input_btn.setEnabled(enabled and bool(self._abstract_edit.toPlainText().strip()))
        self._clear_btn.setEnabled(enabled)

    def _terminate_workers(self) -> None:
        """
        Safely terminate any running worker threads.

        Waits up to WORKER_TERMINATE_TIMEOUT_MS for workers to finish.
        """
        if self._analysis_worker is not None and self._analysis_worker.isRunning():
            logger.info("Terminating analysis worker thread...")
            self._analysis_worker.cancel()
            if not self._analysis_worker.wait(WORKER_TERMINATE_TIMEOUT_MS):
                logger.warning(
                    f"Analysis worker did not terminate within "
                    f"{WORKER_TERMINATE_TIMEOUT_MS}ms"
                )

    def closeEvent(self, event: QCloseEvent) -> None:
        """
        Handle widget close event.

        Ensures worker threads are properly terminated before closing.

        Args:
            event: The close event
        """
        self._terminate_workers()
        # Clear worker reference for garbage collection
        self._analysis_worker = None
        super().closeEvent(event)


__all__ = ['PDFUploadTab']
