"""
Paper Weight Laboratory - PDF Upload Tab

Tab widget for uploading PDFs and matching/creating documents.
Uses the new PDFIngestor for full PDF processing (storage, text extraction, embedding).
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QGroupBox, QFileDialog, QMessageBox,
    QTreeWidget, QTreeWidgetItem, QFormLayout, QCheckBox,
)
from PySide6.QtCore import Signal, QThread
from PySide6.QtGui import QCloseEvent

from bmlibrarian.gui.qt.resources.styles.dpi_scale import get_font_scale
from bmlibrarian.gui.qt.resources.styles.stylesheet_generator import get_stylesheet_generator
from bmlibrarian.database import get_db_manager

from ..constants import (
    SOURCE_ID_OTHER,
    TITLE_SIMILARITY_THRESHOLD,
    ALTERNATIVE_MATCHES_LIMIT,
)
from ..widgets import StatusSpinnerWidget
from ..constants import WORKER_TERMINATE_TIMEOUT_MS
from ..validators import (
    validate_pmid,
    validate_doi,
    validate_year,
    validate_pdf_file_size,
    validate_title,
)

logger = logging.getLogger(__name__)


class PDFAnalysisWorker(QThread):
    """
    Worker thread for PDF analysis and matching.

    Performs PDF text extraction, metadata extraction via LLM,
    and database matching in background.
    """

    analysis_complete = Signal(dict)
    analysis_error = Signal(str)
    status_update = Signal(str)

    def __init__(
        self,
        pdf_path: Path,
        parent: Optional[object] = None
    ):
        """
        Initialize worker.

        Args:
            pdf_path: Path to PDF file
            parent: Parent object
        """
        super().__init__(parent)
        self.pdf_path = pdf_path

    def run(self) -> None:
        """Run PDF analysis in background."""
        try:
            # Import here to avoid circular imports
            from bmlibrarian.importers.pdf_matcher import PDFMatcher

            self.status_update.emit("Initializing PDF matcher...")

            matcher = PDFMatcher()

            # Extract text from first page
            self.status_update.emit("Extracting text from PDF...")
            text = matcher.extract_first_page_text(self.pdf_path)

            if not text:
                self.analysis_error.emit(
                    "Could not extract text from PDF. "
                    "The file may be scanned or corrupted."
                )
                return

            # Extract metadata with LLM
            self.status_update.emit("Extracting metadata with AI...")
            metadata = matcher.extract_metadata_with_llm(text)

            # Find matching documents
            self.status_update.emit("Searching for matching documents...")
            match = matcher.find_matching_document(metadata)

            # Also get alternative matches by title similarity
            alternatives = []
            if metadata.get('title'):
                alternatives = self._find_alternative_matches(metadata['title'])

            result = {
                'pdf_path': str(self.pdf_path),
                'metadata': metadata,
                'match': match,
                'alternatives': alternatives,
            }

            self.analysis_complete.emit(result)

        except Exception as e:
            logger.exception(f"PDF analysis error: {e}")
            self.analysis_error.emit(str(e))

    def _find_alternative_matches(
        self,
        title: str,
        limit: int = ALTERNATIVE_MATCHES_LIMIT
    ) -> List[Dict[str, Any]]:
        """
        Find alternative document matches by title similarity.

        Args:
            title: Title to search for
            limit: Maximum number of alternatives

        Returns:
            List of potential matching documents
        """
        try:
            db_manager = get_db_manager()
            with db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT id, doi, title, external_id,
                               EXTRACT(YEAR FROM publication_date) as year,
                               similarity(title, %s) AS sim
                        FROM document
                        WHERE similarity(title, %s) > %s
                        ORDER BY sim DESC
                        LIMIT %s
                    """, (title, title, TITLE_SIMILARITY_THRESHOLD, limit))

                    results = []
                    for row in cur.fetchall():
                        results.append({
                            'id': row[0],
                            'doi': row[1],
                            'title': row[2],
                            'pmid': row[3],
                            'year': row[4],
                            'similarity': row[5],
                        })
                    return results

        except Exception as e:
            logger.error(f"Error finding alternatives: {e}")
            return []


class PDFIngestWorker(QThread):
    """
    Worker thread for PDF ingestion.

    Performs PDF storage, text extraction, and embedding in background.
    """

    ingest_complete = Signal(object)  # IngestResult
    ingest_error = Signal(str)
    status_update = Signal(str)

    def __init__(
        self,
        document_id: int,
        pdf_path: Path,
        parent: Optional[object] = None
    ):
        """
        Initialize worker.

        Args:
            document_id: Database document ID
            pdf_path: Path to PDF file
            parent: Parent object
        """
        super().__init__(parent)
        self.document_id = document_id
        self.pdf_path = pdf_path

    def run(self) -> None:
        """Run PDF ingestion in background."""
        try:
            from bmlibrarian.importers.pdf_ingestor import PDFIngestor

            self.status_update.emit("Initializing PDF ingestor...")

            ingestor = PDFIngestor()

            def progress_callback(stage: str, current: int, total: int) -> None:
                """Handle progress updates."""
                if total > 0:
                    self.status_update.emit(f"{stage}: {current}/{total}")
                else:
                    self.status_update.emit(stage)

            self.status_update.emit("Ingesting PDF...")

            result = ingestor.ingest_pdf_immediate(
                document_id=self.document_id,
                pdf_path=self.pdf_path,
                progress_callback=progress_callback,
            )

            self.ingest_complete.emit(result)

        except Exception as e:
            logger.exception(f"PDF ingestion error: {e}")
            self.ingest_error.emit(str(e))


class PDFUploadTab(QWidget):
    """
    Tab widget for PDF upload and document matching.

    Allows users to upload PDFs, view extracted metadata,
    select matching documents, or create new documents.

    Signals:
        document_selected: Emitted when a document is selected/created.
            Args: document_id (int)
    """

    document_selected = Signal(int)

    def __init__(self, parent: Optional[object] = None):
        """
        Initialize PDF upload tab.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        self.scale = get_font_scale()
        self.styles = get_stylesheet_generator()

        self.current_pdf_path: Optional[Path] = None
        self.current_metadata: Optional[Dict] = None
        self.current_match: Optional[Dict] = None
        self.analysis_worker: Optional[PDFAnalysisWorker] = None
        self.ingest_worker: Optional[PDFIngestWorker] = None
        self._pending_document_id: Optional[int] = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup tab user interface."""
        layout = QVBoxLayout(self)
        layout.setSpacing(self.scale['spacing_medium'])

        # Upload section
        upload_group = QGroupBox("Upload PDF")
        upload_layout = QVBoxLayout()

        # File selection row
        file_layout = QHBoxLayout()

        self.file_path_label = QLabel("No file selected")
        self.file_path_label.setStyleSheet(self.styles.label_stylesheet(
            font_size_key='font_normal',
            color='#666'
        ))
        file_layout.addWidget(self.file_path_label, stretch=1)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_pdf)
        browse_btn.setStyleSheet(self.styles.button_stylesheet(
            bg_color="#2196F3"
        ))
        file_layout.addWidget(browse_btn)

        upload_layout.addLayout(file_layout)

        # Status spinner
        self.status_spinner = StatusSpinnerWidget()
        upload_layout.addWidget(self.status_spinner)

        upload_group.setLayout(upload_layout)
        layout.addWidget(upload_group)

        # Extracted metadata section
        metadata_group = QGroupBox("Extracted Metadata")
        metadata_layout = QFormLayout()

        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Paper title")
        metadata_layout.addRow("Title:", self.title_edit)

        self.authors_edit = QLineEdit()
        self.authors_edit.setPlaceholderText("Author names (comma separated)")
        metadata_layout.addRow("Authors:", self.authors_edit)

        self.doi_edit = QLineEdit()
        self.doi_edit.setPlaceholderText("10.xxxx/...")
        metadata_layout.addRow("DOI:", self.doi_edit)

        self.pmid_edit = QLineEdit()
        self.pmid_edit.setPlaceholderText("PubMed ID")
        metadata_layout.addRow("PMID:", self.pmid_edit)

        self.year_edit = QLineEdit()
        self.year_edit.setPlaceholderText("Publication year")
        metadata_layout.addRow("Year:", self.year_edit)

        metadata_group.setLayout(metadata_layout)
        layout.addWidget(metadata_group)

        # Matching results section
        match_group = QGroupBox("Document Matching")
        match_layout = QVBoxLayout()

        # Match status
        self.match_status_label = QLabel("Upload a PDF to find matching documents")
        self.match_status_label.setWordWrap(True)
        match_layout.addWidget(self.match_status_label)

        # Alternatives tree
        self.alternatives_tree = QTreeWidget()
        self.alternatives_tree.setHeaderLabels(
            ["ID", "Title", "PMID", "Similarity"]
        )
        self.alternatives_tree.setColumnWidth(0, self.scale['char_width'] * 8)
        self.alternatives_tree.setColumnWidth(1, self.scale['char_width'] * 50)
        self.alternatives_tree.setColumnWidth(2, self.scale['char_width'] * 12)
        self.alternatives_tree.setAlternatingRowColors(True)
        self.alternatives_tree.itemDoubleClicked.connect(
            self._on_alternative_double_clicked
        )
        match_layout.addWidget(self.alternatives_tree)

        match_group.setLayout(match_layout)
        layout.addWidget(match_group, stretch=1)

        # Ingestion options
        options_layout = QHBoxLayout()

        self.ingest_checkbox = QCheckBox("Ingest PDF (extract text & create embeddings)")
        self.ingest_checkbox.setChecked(True)
        self.ingest_checkbox.setToolTip(
            "Store PDF, convert to text, and create semantic embeddings.\n"
            "This enables full-text analysis for the Paper Weight assessment."
        )
        options_layout.addWidget(self.ingest_checkbox)
        options_layout.addStretch()
        layout.addLayout(options_layout)

        # Action buttons
        button_layout = QHBoxLayout()

        self.use_match_btn = QPushButton("Use Selected Match")
        self.use_match_btn.clicked.connect(self._use_selected_match)
        self.use_match_btn.setStyleSheet(self.styles.button_stylesheet(
            bg_color="#4CAF50"
        ))
        self.use_match_btn.setEnabled(False)
        button_layout.addWidget(self.use_match_btn)

        self.create_new_btn = QPushButton("Create New Document")
        self.create_new_btn.clicked.connect(self._create_new_document)
        self.create_new_btn.setStyleSheet(self.styles.button_stylesheet(
            bg_color="#FF9800"
        ))
        self.create_new_btn.setEnabled(False)
        button_layout.addWidget(self.create_new_btn)

        button_layout.addStretch()

        layout.addLayout(button_layout)

        # Connect tree selection
        self.alternatives_tree.itemSelectionChanged.connect(
            self._on_selection_changed
        )

    def _browse_pdf(self) -> None:
        """Open file dialog to select PDF."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select PDF File",
            "",
            "PDF Files (*.pdf)"
        )

        if file_path:
            pdf_path = Path(file_path)

            # Validate file size
            is_valid_size, size_warning = validate_pdf_file_size(pdf_path)
            if not is_valid_size and size_warning:
                reply = QMessageBox.warning(
                    self,
                    "Large File Warning",
                    f"{size_warning}\n\nDo you want to continue anyway?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                if reply != QMessageBox.Yes:
                    return

            self.current_pdf_path = pdf_path
            self.file_path_label.setText(self.current_pdf_path.name)
            self._analyze_pdf()

    def _analyze_pdf(self) -> None:
        """Start PDF analysis in background."""
        if not self.current_pdf_path:
            return

        # Clear previous results
        self._clear_results()

        # Start spinner
        self.status_spinner.start_spinner()
        self.status_spinner.set_status("Analyzing PDF...")

        # Create and start worker
        self.analysis_worker = PDFAnalysisWorker(self.current_pdf_path, self)
        self.analysis_worker.status_update.connect(self._on_status_update)
        self.analysis_worker.analysis_complete.connect(self._on_analysis_complete)
        self.analysis_worker.analysis_error.connect(self._on_analysis_error)
        self.analysis_worker.start()

    def _clear_results(self) -> None:
        """Clear all result fields."""
        self.title_edit.clear()
        self.authors_edit.clear()
        self.doi_edit.clear()
        self.pmid_edit.clear()
        self.year_edit.clear()
        self.alternatives_tree.clear()
        self.match_status_label.setText("Analyzing...")
        self.use_match_btn.setEnabled(False)
        self.create_new_btn.setEnabled(False)
        self.current_metadata = None
        self.current_match = None

    def _on_status_update(self, status: str) -> None:
        """Handle status update from worker."""
        self.status_spinner.set_status(status)

    def _on_analysis_complete(self, result: Dict) -> None:
        """Handle completed analysis."""
        self.status_spinner.set_complete("Analysis complete")

        self.current_metadata = result['metadata']
        self.current_match = result['match']

        # Populate metadata fields
        if self.current_metadata:
            self.title_edit.setText(self.current_metadata.get('title') or '')
            authors = self.current_metadata.get('authors', [])
            if authors:
                self.authors_edit.setText(', '.join(authors))
            self.doi_edit.setText(self.current_metadata.get('doi') or '')
            self.pmid_edit.setText(str(self.current_metadata.get('pmid') or ''))

        # Populate alternatives tree
        alternatives = result.get('alternatives', [])

        # Add exact match at top if found
        if self.current_match:
            match_item = QTreeWidgetItem([
                str(self.current_match['id']),
                self.current_match['title'] or 'No title',
                str(self.current_match.get('external_id') or ''),
                "EXACT MATCH"
            ])
            match_item.setToolTip(1, self.current_match['title'] or 'No title')
            self.alternatives_tree.addTopLevelItem(match_item)
            self.alternatives_tree.setCurrentItem(match_item)

        # Add alternatives
        for alt in alternatives:
            # Skip if same as exact match
            if self.current_match and alt['id'] == self.current_match['id']:
                continue

            item = QTreeWidgetItem([
                str(alt['id']),
                alt['title'] or 'No title',
                str(alt.get('pmid') or ''),
                f"{alt['similarity']:.2f}"
            ])
            item.setToolTip(1, alt['title'] or 'No title')
            self.alternatives_tree.addTopLevelItem(item)

        # Update status
        if self.current_match:
            self.match_status_label.setText(
                f"Found exact match: {self.current_match['title'][:80]}..."
            )
        elif alternatives:
            self.match_status_label.setText(
                f"Found {len(alternatives)} potential matches. "
                "Select one or create a new document."
            )
        else:
            self.match_status_label.setText(
                "No matching documents found. "
                "Edit metadata above and create a new document."
            )

        # Enable buttons
        self.create_new_btn.setEnabled(True)
        self._on_selection_changed()

    def _on_analysis_error(self, error: str) -> None:
        """
        Handle analysis error with granular error messages.

        Provides specific guidance based on the type of error encountered.
        """
        error_lower = error.lower()

        # Determine error type and provide specific guidance
        if "text extraction" in error_lower or "extract text" in error_lower:
            status_msg = "Could not extract text - PDF may be scanned"
            guidance = (
                "The PDF may be a scanned document without embedded text.\n\n"
                "Suggestions:\n"
                "- Use OCR software to convert the scanned PDF to text\n"
                "- Try a different version of the document if available"
            )
        elif "metadata" in error_lower or "llm" in error_lower or "model" in error_lower:
            status_msg = "AI metadata extraction failed"
            guidance = (
                "The AI model could not extract metadata from the PDF.\n\n"
                "Possible causes:\n"
                "- Ollama service may not be running\n"
                "- The configured model may not be available\n"
                "- The PDF text may be in an unexpected format\n\n"
                "Try:\n"
                "- Check that Ollama is running\n"
                "- Enter metadata manually in the fields above"
            )
        elif "connection" in error_lower or "timeout" in error_lower:
            status_msg = "Connection error"
            guidance = (
                "Could not connect to required services.\n\n"
                "Please check:\n"
                "- Database connection\n"
                "- Ollama service is running\n"
                "- Network connectivity"
            )
        elif "permission" in error_lower or "access" in error_lower:
            status_msg = "File access error"
            guidance = (
                "Could not access the PDF file.\n\n"
                "Please check:\n"
                "- File permissions\n"
                "- File is not locked by another application"
            )
        elif "corrupt" in error_lower or "invalid" in error_lower:
            status_msg = "Invalid PDF file"
            guidance = (
                "The file does not appear to be a valid PDF.\n\n"
                "Please check:\n"
                "- File is not corrupted\n"
                "- File has a .pdf extension but is actually a PDF"
            )
        else:
            status_msg = "Analysis failed"
            guidance = f"An unexpected error occurred:\n\n{error}"

        self.status_spinner.set_error(status_msg)
        self.match_status_label.setText(f"Error: {status_msg}")

        # Enable manual entry as fallback
        self.create_new_btn.setEnabled(True)

        QMessageBox.critical(
            self,
            "Analysis Error",
            f"{guidance}\n\nYou can still enter metadata manually and create a new document."
        )

    def _on_selection_changed(self) -> None:
        """Enable/disable use match button based on selection."""
        has_selection = len(self.alternatives_tree.selectedItems()) > 0
        self.use_match_btn.setEnabled(has_selection)

    def _on_alternative_double_clicked(
        self,
        item: QTreeWidgetItem,
        column: int
    ) -> None:
        """Handle double-click to use match."""
        self._use_selected_match()

    def _use_selected_match(self) -> None:
        """Use selected document match and optionally ingest PDF."""
        current = self.alternatives_tree.currentItem()
        if current:
            document_id = int(current.text(0))

            # If ingest checkbox is checked, ingest the PDF
            if self.ingest_checkbox.isChecked() and self.current_pdf_path:
                self._ingest_pdf(document_id)
            else:
                self.document_selected.emit(document_id)

    def _create_new_document(self) -> None:
        """Create new document from extracted metadata."""
        # Validate title (required field)
        title = self.title_edit.text().strip()
        is_valid_title, title_error = validate_title(title)
        if not is_valid_title:
            QMessageBox.warning(self, "Invalid Title", title_error)
            return

        # Validate PMID (optional field)
        pmid_text = self.pmid_edit.text().strip()
        is_valid_pmid, pmid_error = validate_pmid(pmid_text)
        if not is_valid_pmid:
            QMessageBox.warning(self, "Invalid PMID", pmid_error)
            return

        # Validate DOI (optional field)
        doi_text = self.doi_edit.text().strip()
        is_valid_doi, doi_error = validate_doi(doi_text)
        if not is_valid_doi:
            QMessageBox.warning(self, "Invalid DOI", doi_error)
            return

        # Validate year (optional field)
        year_text = self.year_edit.text().strip()
        is_valid_year, year_error = validate_year(year_text)
        if not is_valid_year:
            QMessageBox.warning(self, "Invalid Year", year_error)
            return

        # Confirm creation
        reply = QMessageBox.question(
            self,
            "Create New Document",
            f"Create new document:\n\n{title[:100]}...\n\n"
            "This will add a new entry to the database.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        try:
            # Parse metadata
            authors_text = self.authors_edit.text().strip()
            authors = [a.strip() for a in authors_text.split(',') if a.strip()]
            doi = self.doi_edit.text().strip() or None
            pmid = self.pmid_edit.text().strip() or None
            year = self.year_edit.text().strip()

            # Create external_id (use PMID, DOI hash, or generated)
            if pmid:
                external_id = pmid
            elif doi:
                # Use DOI as external_id
                external_id = doi.replace('/', '_')
            else:
                # Generate unique ID
                import uuid
                external_id = f"other_{uuid.uuid4().hex[:12]}"

            # Insert into database
            db_manager = get_db_manager()
            with db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    # First ensure source "other" exists
                    cur.execute("""
                        INSERT INTO public.sources (id, name, is_reputable, is_free)
                        VALUES (%s, 'other', false, true)
                        ON CONFLICT (name) DO NOTHING
                    """, (SOURCE_ID_OTHER,))

                    # Insert document
                    cur.execute("""
                        INSERT INTO document (
                            source_id, external_id, doi, title, authors,
                            publication_date
                        )
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (
                        SOURCE_ID_OTHER,
                        external_id,
                        doi,
                        title,
                        authors if authors else None,
                        f"{year}-01-01" if year else None,
                    ))

                    document_id = cur.fetchone()[0]
                    conn.commit()

            logger.info(f"Created new document with ID: {document_id}")

            # If ingest checkbox is checked, ingest the PDF
            if self.ingest_checkbox.isChecked() and self.current_pdf_path:
                self._ingest_pdf(document_id)
            else:
                QMessageBox.information(
                    self,
                    "Document Created",
                    f"New document created with ID: {document_id}"
                )
                self.document_selected.emit(document_id)

        except Exception as e:
            logger.exception(f"Error creating document: {e}")
            QMessageBox.critical(
                self,
                "Creation Error",
                f"Failed to create document:\n{e}"
            )

    def _ingest_pdf(self, document_id: int) -> None:
        """
        Ingest PDF for a document.

        Args:
            document_id: Database document ID
        """
        if not self.current_pdf_path:
            self.document_selected.emit(document_id)
            return

        # Disable buttons during ingestion
        self.use_match_btn.setEnabled(False)
        self.create_new_btn.setEnabled(False)

        # Start spinner
        self.status_spinner.start_spinner()
        self.status_spinner.set_status("Ingesting PDF...")

        # Store document_id for completion handler
        self._pending_document_id = document_id

        # Create and start ingest worker
        self.ingest_worker = PDFIngestWorker(
            document_id,
            self.current_pdf_path,
            self
        )
        self.ingest_worker.status_update.connect(self._on_status_update)
        self.ingest_worker.ingest_complete.connect(self._on_ingest_complete)
        self.ingest_worker.ingest_error.connect(self._on_ingest_error)
        self.ingest_worker.start()

    def _on_ingest_complete(self, result: Any) -> None:
        """Handle completed PDF ingestion."""
        document_id = self._pending_document_id

        if result.success:
            self.status_spinner.set_complete(
                f"Ingestion complete: {result.chunks_created} chunks, "
                f"{result.char_count:,} chars"
            )

            QMessageBox.information(
                self,
                "PDF Ingested",
                f"PDF successfully ingested:\n"
                f"- Text extracted: {result.char_count:,} characters\n"
                f"- Pages: {result.page_count}\n"
                f"- Chunks created: {result.chunks_created}"
            )
        else:
            self.status_spinner.set_error("Ingestion failed")

            # Show warning but still proceed
            QMessageBox.warning(
                self,
                "Ingestion Warning",
                f"PDF ingestion completed with errors:\n{result.error_message}\n\n"
                "The document was still associated, but full-text analysis "
                "may not be available."
            )

        # Re-enable buttons
        self.use_match_btn.setEnabled(True)
        self.create_new_btn.setEnabled(True)

        # Emit document selected signal
        self.document_selected.emit(document_id)

    def _on_ingest_error(self, error: str) -> None:
        """Handle ingestion error."""
        document_id = self._pending_document_id

        self.status_spinner.set_error("Ingestion failed")

        # Re-enable buttons
        self.use_match_btn.setEnabled(True)
        self.create_new_btn.setEnabled(True)

        # Show error but still proceed
        reply = QMessageBox.question(
            self,
            "Ingestion Error",
            f"Failed to ingest PDF:\n{error}\n\n"
            "Do you want to continue without PDF ingestion?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )

        if reply == QMessageBox.Yes:
            self.document_selected.emit(document_id)

    def _terminate_workers(self) -> None:
        """
        Safely terminate any running worker threads.

        Waits up to WORKER_TERMINATE_TIMEOUT_MS for each worker to finish.
        """
        workers = [
            ('analysis_worker', self.analysis_worker),
            ('ingest_worker', self.ingest_worker),
        ]

        for name, worker in workers:
            if worker is not None and worker.isRunning():
                logger.info(f"Terminating {name} thread...")
                worker.terminate()
                if not worker.wait(WORKER_TERMINATE_TIMEOUT_MS):
                    logger.warning(
                        f"{name} did not terminate within "
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
        # Clear worker references for garbage collection
        self.analysis_worker = None
        self.ingest_worker = None
        super().closeEvent(event)


__all__ = ['PDFUploadTab']
