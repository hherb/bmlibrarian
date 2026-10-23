"""
Paper Weight Laboratory - Search Tab

Tab widget for searching and selecting documents.
Includes PDF/full-text availability indicators and full-text discovery.
"""

import logging
from pathlib import Path
from typing import Any, Optional, List, Dict, Set

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QTreeWidget, QTreeWidgetItem,
    QMessageBox, QGroupBox,
)
from PySide6.QtCore import Signal, QTimer
from PySide6.QtGui import QCloseEvent
from shiboken6 import isValid as is_widget_valid

from bmlibrarian.gui.qt.resources.styles.dpi_scale import get_font_scale
from bmlibrarian.gui.qt.resources.styles.stylesheet_generator import get_stylesheet_generator
from bmlibrarian.gui.document_card_factory_base import DocumentCardData
from bmlibrarian.gui.qt.qt_document_card_factory import (
    FindPDFSession,
    FindPdfStatus,
    PDFDiscoveryProgressDialog,
    PDFDiscoveryWorker,
    QtDocumentCardFactory,
    describe_discovery_error,
    stop_qthread,
)
from bmlibrarian.gui.qt.resources.constants import PDFOperationSettings
from bmlibrarian.agents.paper_weight import (
    search_documents,
    semantic_search_documents,
    get_recent_assessments,
)

from ..utils import format_recent_assessment_display


logger = logging.getLogger(__name__)

# Outcomes the user chose in the verification prompt (not errors)
USER_CHOICE_STATUSES = frozenset({
    FindPdfStatus.DECLINED, FindPdfStatus.REASSIGNED, FindPdfStatus.SAVED_COPY,
})

# Status tag constants
TAG_PDF = "📄"       # Has PDF file
TAG_FULLTEXT = "📝"  # Has full text
TAG_NONE = "⚪"      # No PDF or full text


class SearchTab(QWidget):
    """
    Tab widget for document search and selection.

    Provides keyword and semantic search capabilities with
    a results list and recent assessments dropdown.

    Shows PDF/full-text availability status for each document and
    offers to find full text online when selecting documents without it.

    Signals:
        document_selected: Emitted when a document is selected.
            Args: document_id (int)
        full_text_downloaded: Emitted when full text has been downloaded and needs ingestion.
            Args: document_id (int), pdf_path (Path)
    """

    document_selected = Signal(int)
    full_text_downloaded = Signal(int, object)  # document_id, pdf_path (Path)

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize search tab.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        self.scale = get_font_scale()
        self.styles = get_stylesheet_generator()

        self.search_results: List[Dict] = []
        # Running full-text discovery sessions, kept referenced until done
        self._discovery_sessions: Set[FindPDFSession] = set()
        # Created on first Find (it touches the PDF directory)
        self._card_factory: Optional[QtDocumentCardFactory] = None

        self._setup_ui()

    def _terminate_workers(self) -> None:
        """Stop running full-text discovery threads (tab or window closing).

        Destroying a running QThread aborts the process; late results are
        dropped instead of opening dialogs on a closed window.
        """
        for session in list(self._discovery_sessions):
            session.cancel()
            stop_qthread(session.worker, "Full-text discovery worker")
        self._discovery_sessions.clear()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Stop discovery threads before the tab closes.

        Args:
            event: The close event
        """
        self._terminate_workers()
        super().closeEvent(event)

    def _setup_ui(self) -> None:
        """Setup tab user interface."""
        layout = QVBoxLayout(self)
        layout.setSpacing(self.scale['spacing_medium'])

        # Recent assessments section
        recent_group = QGroupBox("Recent Assessments")
        recent_layout = QHBoxLayout()

        self.recent_combo = QComboBox()
        self.recent_combo.setMinimumWidth(self.scale['control_width_xlarge'])
        self.recent_combo.currentIndexChanged.connect(
            self._on_recent_selection_changed
        )
        recent_layout.addWidget(self.recent_combo, stretch=1)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.load_recent_assessments)
        recent_layout.addWidget(refresh_btn)

        recent_group.setLayout(recent_layout)
        layout.addWidget(recent_group)

        # Search section
        search_group = QGroupBox("Search Documents")
        search_layout = QVBoxLayout()

        # Search type selector
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Search type:"))

        self.search_type_combo = QComboBox()
        self.search_type_combo.addItem("Semantic (natural language)", "semantic")
        self.search_type_combo.addItem("Title/PMID/DOI (keyword)", "keyword")
        self.search_type_combo.currentIndexChanged.connect(
            self._on_search_type_changed
        )
        type_layout.addWidget(self.search_type_combo)
        type_layout.addStretch()
        search_layout.addLayout(type_layout)

        # Search input
        input_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Enter natural language query (e.g., 'effect of telmisartan on vascular stiffness')..."
        )
        self.search_input.returnPressed.connect(self._do_search)
        input_layout.addWidget(self.search_input, stretch=1)

        search_btn = QPushButton("Search")
        search_btn.clicked.connect(self._do_search)
        search_btn.setStyleSheet(self.styles.button_stylesheet(
            bg_color="#2196F3"
        ))
        input_layout.addWidget(search_btn)
        search_layout.addLayout(input_layout)

        search_group.setLayout(search_layout)
        layout.addWidget(search_group)

        # Results section
        results_group = QGroupBox("Search Results")
        results_layout = QVBoxLayout()

        # Legend for status icons
        legend_layout = QHBoxLayout()
        legend_layout.addWidget(QLabel(f"{TAG_PDF} PDF  {TAG_FULLTEXT} Full Text  {TAG_NONE} None"))
        legend_layout.addStretch()
        results_layout.addLayout(legend_layout)

        self.results_tree = QTreeWidget()
        self.results_tree.setHeaderLabels(["ID", "Title", "PMID", "Year", "Status"])
        self.results_tree.setColumnWidth(0, self.scale['char_width'] * 8)
        self.results_tree.setColumnWidth(1, self.scale['char_width'] * 50)
        self.results_tree.setColumnWidth(2, self.scale['char_width'] * 12)
        self.results_tree.setColumnWidth(3, self.scale['char_width'] * 12)
        self.results_tree.setColumnWidth(4, self.scale['char_width'] * 8)
        self.results_tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.results_tree.setAlternatingRowColors(True)
        results_layout.addWidget(self.results_tree)

        # Select button
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.select_btn = QPushButton("Select Document")
        self.select_btn.clicked.connect(self._select_document)
        self.select_btn.setStyleSheet(self.styles.button_stylesheet(
            bg_color="#4CAF50"
        ))
        self.select_btn.setEnabled(False)
        button_layout.addWidget(self.select_btn)

        results_layout.addLayout(button_layout)
        results_group.setLayout(results_layout)
        layout.addWidget(results_group, stretch=1)

        # Connect selection change to enable/disable select button
        self.results_tree.itemSelectionChanged.connect(
            self._on_selection_changed
        )

        # Load recent assessments on init
        self.load_recent_assessments()

    def load_recent_assessments(self) -> None:
        """Load recent assessments into dropdown."""
        self.recent_combo.clear()
        self.recent_combo.addItem("-- Select recent assessment --", None)

        try:
            recent = get_recent_assessments()
        except Exception as e:
            logger.error(f"Could not load recent assessments: {e}")
            # Non-modal: this runs at startup and after every selection.
            self.recent_combo.setItemText(0, "-- Could not load recent assessments (see log) --")
            return
        for item in recent:
            display_text = format_recent_assessment_display(
                item['title'], item['final_weight']
            )
            self.recent_combo.addItem(display_text, item['document_id'])

    def _on_recent_selection_changed(self, index: int) -> None:
        """Handle selection change in recent assessments dropdown."""
        document_id = self.recent_combo.currentData()
        if document_id:
            self.document_selected.emit(document_id)

    def _on_search_type_changed(self, index: int) -> None:
        """Update placeholder text based on search type."""
        search_type = self.search_type_combo.currentData()
        if search_type == "semantic":
            self.search_input.setPlaceholderText(
                "Enter natural language query (e.g., 'effect of telmisartan on vascular stiffness')..."
            )
        else:
            self.search_input.setPlaceholderText(
                "Enter PMID, DOI, or title keywords..."
            )

    def _do_search(self) -> None:
        """Perform document search using selected search type."""
        query = self.search_input.text().strip()
        if not query:
            return

        self.results_tree.clear()
        self.select_btn.setEnabled(False)

        search_type = self.search_type_combo.currentData()
        try:
            if search_type == "semantic":
                self.search_results = semantic_search_documents(query)
            else:
                self.search_results = search_documents(query)
        except Exception as e:
            logger.error(f"Document search failed: {e}")
            self.search_results = []
            QMessageBox.critical(self, "Search Failed", f"The search failed:\n{e}")
            return

        for doc in self.search_results:
            # Add similarity score for semantic search results
            similarity = doc.get('similarity')
            if similarity is not None:
                year_text = f"{doc['year'] or ''} ({similarity:.2f})"
            else:
                year_text = str(doc['year'] or '')

            # Build status string
            status_text = self._build_status_text(doc)

            item = QTreeWidgetItem([
                str(doc['id']),
                doc['title'] or 'No title',
                str(doc['pmid'] or ''),
                year_text,
                status_text
            ])
            # Set full title as tooltip for truncated display
            item.setToolTip(1, doc['title'] or 'No title')
            # Set status tooltip
            item.setToolTip(4, self._build_status_tooltip(doc))
            self.results_tree.addTopLevelItem(item)

        if not self.search_results:
            QMessageBox.information(
                self,
                "No Results",
                f"No documents found matching: {query}"
            )

    def _build_status_text(self, doc: Dict) -> str:
        """
        Build status indicator text for a document.

        Args:
            doc: Document dictionary with has_pdf and has_full_text keys

        Returns:
            Status text with emoji indicators
        """
        has_pdf = doc.get('has_pdf', False)
        has_full_text = doc.get('has_full_text', False)

        if has_full_text:
            return TAG_FULLTEXT
        elif has_pdf:
            return TAG_PDF
        else:
            return TAG_NONE

    def _build_status_tooltip(self, doc: Dict) -> str:
        """
        Build status tooltip for a document.

        Args:
            doc: Document dictionary

        Returns:
            Detailed status tooltip
        """
        has_pdf = doc.get('has_pdf', False)
        has_full_text = doc.get('has_full_text', False)

        parts = []
        if has_full_text:
            parts.append("✓ Full text available (ready for analysis)")
        elif has_pdf:
            parts.append("✓ PDF available (needs text extraction)")
        else:
            parts.append("✗ No PDF or full text")
            if doc.get('doi') or doc.get('pmid'):
                parts.append("  → Select it to search online for full text")

        return "\n".join(parts)

    def _on_selection_changed(self) -> None:
        """Enable/disable select button based on selection."""
        has_selection = len(self.results_tree.selectedItems()) > 0
        self.select_btn.setEnabled(has_selection)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle double-click on result item."""
        self._select_document()

    def _select_document(self) -> None:
        """Select current document and emit signal.

        If the document has no full text, offers to find it online.
        """
        current = self.results_tree.currentItem()
        if not current:
            QMessageBox.warning(
                self,
                "No Selection",
                "Please select a document from the list."
            )
            return

        document_id = int(current.text(0))

        # Find the document data in search results
        doc_data = self._get_document_from_results(document_id)
        if not doc_data:
            # Not found in results, just emit signal
            self.document_selected.emit(document_id)
            return

        has_full_text = doc_data.get('has_full_text', False)
        has_pdf = doc_data.get('has_pdf', False)

        # If document has full text, proceed directly
        if has_full_text:
            self.document_selected.emit(document_id)
            return

        # Check if we can find full text online
        has_identifiers = any([
            doc_data.get('doi'),
            doc_data.get('pmid'),
            doc_data.get('pdf_url'),
            doc_data.get('title'),
        ])

        if not has_identifiers:
            # No identifiers to search with
            if has_pdf:
                msg = ("This document has a PDF but no extracted full text.\n\n"
                       "It will be processed when you run the assessment.")
            else:
                msg = ("This document has no PDF or full text available,\n"
                       "and no identifiers to search online.")
            QMessageBox.information(self, "Limited Data", msg)
            self.document_selected.emit(document_id)
            return

        # Offer to find full text online
        if has_pdf:
            msg = ("This document has a PDF but no extracted full text.\n\n"
                   "Would you like to:\n"
                   "• Yes - Use existing PDF (will be processed)\n"
                   "• No - Search online for a better version")
            reply = QMessageBox.question(
                self,
                "Full Text Not Extracted",
                msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes
            )
            if reply == QMessageBox.StandardButton.Cancel:
                return
            elif reply == QMessageBox.StandardButton.Yes:
                self.document_selected.emit(document_id)
                return
            # Continue to find online
        else:
            reply = QMessageBox.question(
                self,
                "No Full Text Available",
                "This document has no full text available.\n\n"
                "Would you like to search online for the PDF?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            if reply != QMessageBox.StandardButton.Yes:
                self.document_selected.emit(document_id)
                return

        # Start full text discovery
        self._find_full_text_online(doc_data)

    def _get_document_from_results(self, document_id: int) -> Optional[Dict]:
        """
        Get document data from search results by ID.

        Args:
            document_id: Document ID to find

        Returns:
            Document dictionary or None if not found
        """
        for doc in self.search_results:
            if doc.get('id') == document_id:
                return doc
        return None

    def _get_card_factory(self) -> QtDocumentCardFactory:
        """
        Return the document card factory whose Find PDF flow this tab
        reuses, creating it on first use.

        Returns:
            The factory, writing PDFs to the configured ``pdf.base_dir``

        Raises:
            ValueError: If the PDF directory cannot be created or is not a
                directory
            TypeError: If the configured ``pdf.base_dir`` is not a path
        """
        if self._card_factory is None:
            from bmlibrarian.config import get_config
            from bmlibrarian.importers.pdf_ingestor import DEFAULT_PDF_BASE_DIR
            from bmlibrarian.utils.pdf_manager import PDFManager

            pdf_config = get_config().get('pdf') or {}
            base_dir_str = (
                pdf_config.get('base_dir', DEFAULT_PDF_BASE_DIR)
                if isinstance(pdf_config, dict) else DEFAULT_PDF_BASE_DIR
            )
            base_dir = Path(base_dir_str).expanduser()
            self._card_factory = QtDocumentCardFactory(
                pdf_manager=PDFManager(base_dir=str(base_dir)),
                base_pdf_dir=base_dir,
            )
        return self._card_factory

    def _find_full_text_online(self, doc_data: Dict) -> None:
        """
        Find full text online using the document cards' Find PDF flow.

        Shows a progress dialog and runs discovery on a ``PDFDiscoveryWorker``
        thread so the UI stays responsive; the outcome (including the
        verification prompt for a mismatched PDF) is handled on the GUI
        thread by ``_on_full_text_result`` / ``_on_full_text_error``.

        Args:
            doc_data: Document dictionary with identifiers
        """
        document_id = doc_data['id']
        try:
            factory = self._get_card_factory()
        except Exception as e:
            # Config values are untrusted (e.g. "base_dir": null)
            logger.error(f"Cannot set up full-text discovery: {e}", exc_info=True)
            self._on_full_text_error(
                document_id, None,
                f"Cannot use the configured PDF directory: {str(e) or type(e).__name__}"
            )
            return

        pmid = doc_data.get('pmid')
        card_data = DocumentCardData(
            doc_id=document_id,
            title=doc_data.get('title') or "",
            doi=doc_data.get('doi'),
            pmid=str(pmid) if pmid else None,
            pdf_url=doc_data.get('pdf_url'),
            year=doc_data.get('year'),
        )

        progress_dialog = PDFDiscoveryProgressDialog(
            doc_id=document_id,
            title=card_data.title or "Unknown",
            parent=self.window()
        )
        progress_dialog.show()

        def on_progress(stage: str, status: str) -> None:
            if is_widget_valid(progress_dialog):
                progress_dialog.add_step(stage, status)

        worker = PDFDiscoveryWorker(
            lambda progress_cb: factory.discover_and_download(card_data, progress_cb)
        )
        session = FindPDFSession(
            worker,
            on_progress=on_progress,
            on_discovered=lambda result: self._on_full_text_result(
                doc_data, card_data, progress_dialog, result
            ),
            on_failed=lambda error_msg: self._on_full_text_error(
                document_id, progress_dialog, describe_discovery_error(error_msg)
            ),
            on_done=self._discovery_sessions.discard,
        )
        self._discovery_sessions.add(session)

        def on_dialog_closed() -> None:
            """Closed before the result arrived: abandon the search (no late
            verification prompt or database writes) and use the abstract."""
            if not session.outcome_delivered:
                session.cancel()
                logger.info(f"Find full text for document {document_id} cancelled by the user")
                self.document_selected.emit(document_id)

        progress_dialog.rejected.connect(on_dialog_closed)
        session.start()

    def _on_full_text_result(
        self,
        doc_data: Dict,
        card_data: DocumentCardData,
        progress_dialog: PDFDiscoveryProgressDialog,
        result: Any
    ) -> None:
        """
        Apply a finished discovery (GUI thread): prompt, update DB, tree and dialog.

        A PDF that failed verification is only attached if the user accepts
        it (or uploads their own file instead); a CrossRef-discovered DOI is
        saved only for a verified PDF.

        Args:
            doc_data: Document dictionary (updated in place)
            card_data: The document as passed to ``discover_and_download``
            progress_dialog: The discovery progress dialog
            result: Download result from ``discover_and_download``
        """
        document_id = doc_data['id']
        factory = self._get_card_factory()
        try:
            outcome = factory.finalize_discovery_result(card_data, result)
        except Exception as e:
            logger.error(
                f"Error applying discovery result for document {document_id}: {e}",
                exc_info=True
            )
            self._on_full_text_error(
                document_id, progress_dialog,
                describe_discovery_error(str(e) or type(e).__name__)
            )
            return
        outcome = factory.record_find_pdf_outcome(card_data, result, outcome)
        logger.info(
            f"Find full text for document {document_id}: "
            f"{outcome.status.value} - {outcome.message}"
        )

        pdf_path = outcome.pdf_path
        if outcome.status in USER_CHOICE_STATUSES:
            # Declined, reassigned or copied by the user: no error to log
            self._continue_with_abstract(document_id, progress_dialog, outcome.message)
            return
        if outcome.status != FindPdfStatus.ATTACHED or pdf_path is None:
            # Not found or not saved: this document has no new full text
            self._on_full_text_error(document_id, progress_dialog, outcome.message)
            return

        if is_widget_valid(progress_dialog):
            progress_dialog.set_success(None, f"{outcome.message}: {pdf_path.name}")
            QTimer.singleShot(
                PDFOperationSettings.DIALOG_CLOSE_SUCCESS_DELAY_MS,
                progress_dialog.accept
            )
        doc_data['has_pdf'] = True
        doc_data['pdf_filename'] = pdf_path.name
        if outcome.full_text_stored:
            doc_data['has_full_text'] = True
        self._update_tree_item_status(document_id, doc_data)

        # Trigger ingestion (chunking and embedding)
        self.full_text_downloaded.emit(document_id, pdf_path)

    def _on_full_text_error(
        self,
        document_id: int,
        progress_dialog: Optional[PDFDiscoveryProgressDialog],
        error_msg: str
    ) -> None:
        """
        Report a failed (or unrecorded) discovery (GUI thread) and continue
        with the abstract.

        Args:
            document_id: Document being processed
            progress_dialog: The discovery progress dialog, None if discovery
                never started
            error_msg: Error message
        """
        logger.error(f"Full text not available for document {document_id}: {error_msg}")
        self._continue_with_abstract(document_id, progress_dialog, error_msg)

    def _continue_with_abstract(
        self,
        document_id: int,
        progress_dialog: Optional[PDFDiscoveryProgressDialog],
        message: str
    ) -> None:
        """
        Tell the user no new full text was attached and select the document
        so the assessment proceeds with the abstract (GUI thread).

        Args:
            document_id: Document being processed
            progress_dialog: The discovery progress dialog, None if discovery
                never started
            message: Why no full text was attached
        """
        if progress_dialog is not None and is_widget_valid(progress_dialog):
            progress_dialog.set_failure(message)
            QTimer.singleShot(
                PDFOperationSettings.DIALOG_CLOSE_FAILURE_DELAY_MS,
                progress_dialog.reject
            )
        QMessageBox.warning(
            self,
            "Full Text Not Available",
            f"Full text is not available:\n{message}\n\n"
            "The assessment will proceed using only the abstract."
        )
        self.document_selected.emit(document_id)

    def _update_tree_item_status(self, document_id: int, doc_data: Dict) -> None:
        """
        Update tree item status after PDF download.

        Args:
            document_id: Document ID
            doc_data: Updated document data
        """
        # Find the tree item
        for i in range(self.results_tree.topLevelItemCount()):
            item = self.results_tree.topLevelItem(i)
            if item and int(item.text(0)) == document_id:
                # Update status column
                status_text = self._build_status_text(doc_data)
                item.setText(4, status_text)
                item.setToolTip(4, self._build_status_tooltip(doc_data))
                break


__all__ = ['SearchTab']
