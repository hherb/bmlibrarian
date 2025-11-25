"""
Paper Weight Laboratory - Search Tab

Tab widget for searching and selecting documents.
Includes PDF/full-text availability indicators and full-text discovery.
"""

import logging
from pathlib import Path
from typing import Optional, List, Dict

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QTreeWidget, QTreeWidgetItem,
    QMessageBox, QGroupBox, QApplication,
)
from PySide6.QtCore import Signal

from bmlibrarian.gui.qt.resources.styles.dpi_scale import get_font_scale
from bmlibrarian.gui.qt.resources.styles.stylesheet_generator import get_stylesheet_generator
from bmlibrarian.gui.qt.qt_document_card_factory import PDFDiscoveryProgressDialog
from bmlibrarian.agents.paper_weight import (
    search_documents,
    semantic_search_documents,
    get_recent_assessments,
)

from ..utils import format_recent_assessment_display


logger = logging.getLogger(__name__)

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

        self._setup_ui()

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

        recent = get_recent_assessments()
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
        if search_type == "semantic":
            self.search_results = semantic_search_documents(query)
        else:
            self.search_results = search_documents(query)

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
                parts.append("  → Click 'Find Full Text' to search online")

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

    def _find_full_text_online(self, doc_data: Dict) -> None:
        """
        Find full text online using PDF discovery.

        Shows progress dialog and handles download + ingestion.

        Args:
            doc_data: Document dictionary with identifiers
        """
        from bmlibrarian.discovery import FullTextFinder, DocumentIdentifiers
        from bmlibrarian.discovery.resolvers import CrossRefTitleResolver
        from bmlibrarian.config import get_config
        from pathlib import Path

        document_id = doc_data['id']
        title = doc_data.get('title') or "Unknown"

        # Create and show progress dialog
        progress_dialog = PDFDiscoveryProgressDialog(
            doc_id=document_id,
            title=title,
            parent=self.window()
        )
        progress_dialog.show()
        QApplication.processEvents()

        try:
            # Get configuration
            config = get_config()
            discovery_config = config.get('discovery') or {}

            # Track discovered DOI (from CrossRef title search)
            discovered_doi = doc_data.get('doi')

            # If no DOI but we have a title, try CrossRef title search first
            if not doc_data.get('doi') and doc_data.get('title'):
                progress_dialog.add_step('crossref_title', 'resolving')

                try:
                    title_resolver = CrossRefTitleResolver(
                        timeout=discovery_config.get('timeout', 30),
                        min_similarity=discovery_config.get('crossref_min_similarity', 0.85)
                    )

                    identifiers = DocumentIdentifiers(
                        doc_id=document_id,
                        title=doc_data.get('title')
                    )

                    result = title_resolver.resolve(identifiers)

                    if result.status.value == 'success' and result.metadata.get('discovered_doi'):
                        discovered_doi = result.metadata['discovered_doi']
                        progress_dialog.add_step('crossref_title', 'found')
                        logger.info(f"Discovered DOI {discovered_doi} for document {document_id}")

                        # Update database with discovered DOI
                        self._update_doi_in_database(document_id, discovered_doi)
                    else:
                        progress_dialog.add_step('crossref_title', 'not_found')

                except Exception as e:
                    progress_dialog.add_step('crossref_title', 'error')
                    logger.warning(f"CrossRef title search error: {e}")

            # Get PDF base directory from config
            pdf_config = config.get('pdf') or {}
            pdf_base_dir_str = pdf_config.get('base_dir', '~/knowledgebase/pdf') if isinstance(pdf_config, dict) else '~/knowledgebase/pdf'
            pdf_base_dir = Path(pdf_base_dir_str).expanduser()
            pdf_base_dir.mkdir(parents=True, exist_ok=True)

            # Get unpaywall email from config
            unpaywall_email = config.get('unpaywall_email')
            unpaywall_email_str = str(unpaywall_email) if unpaywall_email else None

            # Create finder
            finder = FullTextFinder(
                unpaywall_email=unpaywall_email_str,
                timeout=int(discovery_config.get('timeout', 30)),
                prefer_open_access=bool(discovery_config.get('prefer_open_access', True)),
            )

            # Build document dictionary
            document = {
                'id': document_id,
                'doi': discovered_doi,
                'pmid': doc_data.get('pmid'),
                'pdf_url': doc_data.get('pdf_url'),
                'title': doc_data.get('title'),
                'year': doc_data.get('year'),
            }

            # Progress callback
            def progress_callback(stage: str, status: str) -> None:
                progress_dialog.add_step(stage, status)

            # Execute discovery and download
            result = finder.download_for_document(
                document=document,
                output_dir=pdf_base_dir,
                use_browser_fallback=discovery_config.get('use_browser_fallback', True),
                progress_callback=progress_callback
            )

            # Check if we got full text (from NXML) or PDF
            # NXML is superior to PDF - structured XML with clean text extraction
            has_full_text = bool(result.full_text)
            has_pdf = bool(result.file_path)

            if has_full_text or has_pdf:
                # Success - we got content (full text from NXML, PDF, or both)

                if has_pdf:
                    pdf_path = Path(result.file_path)
                    progress_dialog.set_success(pdf_path)

                    # Update database with pdf_filename
                    self._update_pdf_in_database(document_id, pdf_path, doc_data.get('year'))

                    # Update local search results
                    doc_data['has_pdf'] = True
                    doc_data['pdf_filename'] = pdf_path.name

                    logger.info(f"Successfully downloaded PDF for document {document_id}: {pdf_path}")
                else:
                    # NXML only (no PDF) - this is still a success!
                    progress_dialog.set_success(None, message="Full text extracted from NXML")
                    logger.info(f"Successfully extracted full text from NXML for document {document_id}")

                # If we got full text from PMC NXML, update database
                if has_full_text:
                    self._update_full_text_in_database(document_id, result.full_text)
                    doc_data['has_full_text'] = True
                    logger.info(f"Full text available for document {document_id} ({len(result.full_text)} chars)")

                # Update tree item status
                self._update_tree_item_status(document_id, doc_data)

                # Close dialog after delay then emit signal
                from PySide6.QtCore import QTimer
                QTimer.singleShot(1500, progress_dialog.accept)

                # Emit signal to trigger ingestion (chunking and embedding)
                # For NXML-only, pass None as pdf_path - the full_text is already in DB
                if has_pdf:
                    self.full_text_downloaded.emit(document_id, Path(result.file_path))
                else:
                    # Full text already saved to DB, just need to create embeddings
                    # Emit with None to indicate no PDF to process, just embedding needed
                    self.full_text_downloaded.emit(document_id, None)

            else:
                progress_dialog.set_failure(result.error_message or "No PDF or full text sources found")
                logger.warning(f"PDF/full text discovery failed for document {document_id}")

                # Close dialog after delay
                from PySide6.QtCore import QTimer
                QTimer.singleShot(2000, progress_dialog.reject)

                # Still emit document_selected so user can proceed without full text
                QMessageBox.information(
                    self,
                    "Full Text Not Found",
                    "Could not find PDF or full text for this document online.\n\n"
                    "The assessment will proceed using only the abstract."
                )
                self.document_selected.emit(document_id)

        except Exception as e:
            progress_dialog.set_failure(str(e))
            logger.error(f"Error during PDF discovery for document {document_id}: {e}")

            from PySide6.QtCore import QTimer
            QTimer.singleShot(2000, progress_dialog.reject)

            QMessageBox.warning(
                self,
                "Discovery Error",
                f"Error finding PDF:\n{str(e)}\n\n"
                "The assessment will proceed using only the abstract."
            )
            self.document_selected.emit(document_id)

    def _update_doi_in_database(self, doc_id: int, doi: str) -> None:
        """
        Update document DOI in database.

        Args:
            doc_id: Document ID
            doi: DOI to set
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
                    conn.commit()
                    logger.info(f"Updated DOI for document {doc_id}: {doi}")

        except Exception as e:
            logger.error(f"Failed to update DOI for document {doc_id}: {e}")

    def _update_pdf_in_database(self, doc_id: int, pdf_path: Path, year: Optional[int]) -> None:
        """
        Update document PDF filename in database.

        Args:
            doc_id: Document ID
            pdf_path: Path to PDF file
            year: Publication year for relative path calculation
        """
        try:
            from bmlibrarian.database import get_db_manager
            db_manager = get_db_manager()

            # Calculate relative path (year/filename.pdf)
            if year:
                relative_path = f"{year}/{pdf_path.name}"
            else:
                relative_path = pdf_path.name

            with db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE document SET pdf_filename = %s WHERE id = %s",
                        (relative_path, doc_id)
                    )
                    conn.commit()
                    logger.info(f"Updated pdf_filename for document {doc_id}: {relative_path}")

        except Exception as e:
            logger.error(f"Failed to update pdf_filename for document {doc_id}: {e}")

    def _update_full_text_in_database(self, doc_id: int, full_text: str) -> None:
        """
        Update document full text in database.

        Args:
            doc_id: Document ID
            full_text: Full text content
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
                    logger.info(f"Updated full_text for document {doc_id} ({len(full_text)} chars)")

        except Exception as e:
            logger.error(f"Failed to update full_text for document {doc_id}: {e}")

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
