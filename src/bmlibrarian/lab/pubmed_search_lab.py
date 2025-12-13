"""
PubMed Search Lab - Experimental GUI for PubMed API Search.

Provides an interactive interface for searching PubMed directly via the NCBI
E-utilities API. Shows results as document cards without storing in database.
"""

import sys
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, Final
from dataclasses import dataclass

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QTextEdit, QPushButton, QScrollArea, QFrame,
    QProgressBar, QSpinBox, QCheckBox, QGroupBox, QSplitter,
    QMessageBox, QComboBox
)
from PySide6.QtCore import Qt, Signal, QThread, QObject
from PySide6.QtGui import QFont

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from psycopg import sql

from bmlibrarian.config import get_config
from bmlibrarian.gui.qt.resources.styles.dpi_scale import get_font_scale
from bmlibrarian.pubmed_search.constants import DEFAULT_MAX_RESULTS

logger = logging.getLogger(__name__)


# =============================================================================
# Lab-Specific Constants
# =============================================================================

class PubMedLabConstants:
    """Constants specific to PubMed Search Lab."""

    # Window dimensions (minimum)
    MIN_WINDOW_WIDTH: Final[int] = 900
    MIN_WINDOW_HEIGHT: Final[int] = 700

    # Search options
    MIN_SEARCH_RESULTS: Final[int] = 10
    MAX_SEARCH_RESULTS: Final[int] = 1000
    SEARCH_RESULTS_STEP: Final[int] = 50

    # Display limits
    MAX_MESH_TERMS_DISPLAY: Final[int] = 10
    MAX_KEYWORDS_DISPLAY: Final[int] = 10
    ERROR_MESSAGE_TRUNCATE: Final[int] = 50
    DATE_YEAR_CHARS: Final[int] = 4

    # Thread timeouts (milliseconds)
    WORKER_ABORT_TIMEOUT_MS: Final[int] = 2000


@dataclass
class SearchProgress:
    """Progress update during PubMed search."""

    step: str
    message: str
    percent: int = 0


class PubMedSearchWorker(QThread):
    """
    Worker thread for PubMed search operations.

    Runs the search off the main thread to keep the GUI responsive.

    Signals:
        progress: Emitted with SearchProgress updates
        finished: Emitted when search completes with list of ArticleMetadata
        error: Emitted on error with error message
        existing_count: Emitted with count of existing documents in database
    """

    progress = Signal(SearchProgress)
    finished = Signal(list, dict)  # List[ArticleMetadata], Dict[str, int] mapping PMID -> doc_id
    error = Signal(str)
    existing_count = Signal(int, int)  # (existing_count, total_fetched)

    def __init__(
        self,
        question: str,
        max_results: int = 200,
        check_existing: bool = True,
        parent: Optional[QObject] = None
    ):
        """
        Initialize the search worker.

        Args:
            question: Research question to search
            max_results: Maximum results to retrieve
            check_existing: Whether to check for existing documents
            parent: Parent QObject
        """
        super().__init__(parent)
        self.question = question
        self.max_results = max_results
        self.check_existing = check_existing
        self._abort = False

    def abort(self) -> None:
        """Request abort of the current operation."""
        self._abort = True

    def run(self) -> None:
        """Execute the PubMed search."""
        try:
            # Import here to avoid circular imports
            from bmlibrarian.pubmed_search import (
                QueryConverter, PubMedSearchClient, PubMedQuery
            )
            from bmlibrarian.pubmed_search.constants import DEFAULT_QUERY_MODEL

            if self._abort:
                return

            # Step 1: Convert question to PubMed query
            self.progress.emit(SearchProgress(
                step="convert",
                message="Converting question to PubMed query...",
                percent=10
            ))

            converter = QueryConverter(
                validate_mesh=True,
                expand_keywords=True
            )

            conversion_result = converter.convert(self.question)

            if self._abort:
                return

            query = conversion_result.primary_query

            self.progress.emit(SearchProgress(
                step="query_ready",
                message=f"Query: {query.query_string}",
                percent=30
            ))

            # Step 2: Search PubMed
            self.progress.emit(SearchProgress(
                step="search",
                message="Searching PubMed...",
                percent=40
            ))

            config = get_config()
            pubmed_config = config.get('pubmed_api', {}) or {}

            client = PubMedSearchClient(
                email=pubmed_config.get('email'),
                api_key=pubmed_config.get('api_key')
            )

            search_result = client.search(query, max_results=self.max_results)

            if self._abort:
                return

            self.progress.emit(SearchProgress(
                step="found",
                message=f"Found {search_result.total_count} articles, retrieving {search_result.retrieved_count}...",
                percent=50
            ))

            if not search_result.pmids:
                self.progress.emit(SearchProgress(
                    step="complete",
                    message="No results found",
                    percent=100
                ))
                self.finished.emit([])
                return

            # Step 3: Fetch article metadata
            self.progress.emit(SearchProgress(
                step="fetch",
                message=f"Fetching metadata for {len(search_result.pmids)} articles...",
                percent=60
            ))

            articles = client.fetch_articles(search_result.pmids)

            if self._abort:
                return

            # Step 4: Check for existing documents if requested
            existing_pmid_to_docid: Dict[str, int] = {}
            if self.check_existing and articles:
                self.progress.emit(SearchProgress(
                    step="check_existing",
                    message="Checking for existing documents in database...",
                    percent=80
                ))

                try:
                    existing_pmid_to_docid = self._get_existing_pmids(articles)
                except Exception as e:
                    logger.warning(f"Failed to check existing documents: {e}")

                self.existing_count.emit(len(existing_pmid_to_docid), len(articles))

            # Complete
            new_count = len(articles) - len(existing_pmid_to_docid)
            self.progress.emit(SearchProgress(
                step="complete",
                message=f"Retrieved {len(articles)} articles ({new_count} new, {len(existing_pmid_to_docid)} already in database)",
                percent=100
            ))

            self.finished.emit(articles, existing_pmid_to_docid)

        except Exception as e:
            logger.exception("PubMed search failed")
            self.error.emit(str(e))

    def _get_existing_pmids(self, articles: List) -> Dict[str, int]:
        """
        Get PMIDs of articles that already exist in the local database.

        Args:
            articles: List of ArticleMetadata objects

        Returns:
            Dictionary mapping PMIDs to document IDs
        """
        try:
            from bmlibrarian.database import get_db_manager

            db_manager = get_db_manager()
            pmids = [a.pmid for a in articles if a.pmid]

            if not pmids:
                return {}

            with db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    # Get existing PMIDs and their doc IDs (source_id=1 is PubMed)
                    query = sql.SQL(
                        "SELECT external_id, id FROM document WHERE source_id = 1 AND external_id IN ({})"
                    ).format(
                        sql.SQL(',').join(sql.Placeholder() for _ in pmids)
                    )
                    cur.execute(query, pmids)
                    results = cur.fetchall()
                    return {row[0]: row[1] for row in results}

        except Exception as e:
            logger.warning(f"Database check failed: {e}")
            return {}


class ArticleCardWidget(QFrame):
    """
    A card widget displaying PubMed article metadata.

    Uses CollapsibleDocumentCard for consistent display with scrollable abstract.
    Shows Import button for new articles (not yet in database).
    Shows PDF buttons for existing articles in the database.

    Signals:
        import_requested: Emitted when user clicks Import button with article data
    """

    import_requested = Signal(object)  # Emits ArticleMetadata

    def __init__(
        self,
        article: Any,
        is_new: bool = True,
        doc_id: Optional[int] = None,
        parent: Optional[QWidget] = None
    ):
        """
        Initialize article card.

        Args:
            article: ArticleMetadata object from PubMed API
            is_new: Whether this article is NOT in the local database (highlighted if True)
            doc_id: Database document ID if article exists in database
            parent: Parent widget
        """
        super().__init__(parent)
        self.article = article
        self.is_new = is_new
        self.doc_id = doc_id
        self._setup_ui()

    def _article_to_document_dict(self) -> Dict[str, Any]:
        """
        Convert ArticleMetadata to document dictionary for CollapsibleDocumentCard.

        Returns:
            Dictionary compatible with CollapsibleDocumentCard
        """
        # Extract year from publication_date
        year = None
        if self.article.publication_date:
            try:
                year = int(str(self.article.publication_date)[:4])
            except (ValueError, TypeError):
                pass

        return {
            'id': self.doc_id,  # Database ID if exists
            'title': self.article.title or "No title",
            'abstract': self.article.abstract or "",
            'authors': self.article.authors or [],
            'journal': self.article.publication,
            'year': year,
            'pmid': self.article.pmid,
            'doi': self.article.doi,
            'pmc_id': self.article.pmc_id,
            'mesh_terms': self.article.mesh_terms or [],
            'keywords': self.article.keywords or [],
        }

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        from bmlibrarian.gui.qt.widgets.collapsible_document_card import CollapsibleDocumentCard

        self.setFrameStyle(QFrame.Shape.NoFrame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Create CollapsibleDocumentCard with article data
        doc_dict = self._article_to_document_dict()
        self.document_card = CollapsibleDocumentCard(doc_dict)
        layout.addWidget(self.document_card)

        # Add Import button for new articles (in the card's details section)
        if self.is_new:
            self.import_btn = QPushButton("Import to Database")
            self.import_btn.setStyleSheet(
                "QPushButton { background-color: #4CAF50; color: white; font-weight: bold; "
                "padding: 6px 12px; border-radius: 4px; border: none; }"
                "QPushButton:hover { background-color: #388E3C; }"
                "QPushButton:pressed { background-color: #2E7D32; }"
                "QPushButton:disabled { background-color: #A5D6A7; color: #666; }"
            )
            self.import_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.import_btn.clicked.connect(self._on_import_clicked)
            # Add to the document card's details layout
            self.document_card.details_layout.addWidget(self.import_btn)
        else:
            # For existing articles, add PDF buttons
            self._add_pdf_buttons()

        # Apply container styling - highlight new articles with green left border
        if self.is_new:
            self.setStyleSheet("""
                ArticleCardWidget {
                    background-color: #F1F8E9;
                    border-left: 4px solid #4CAF50;
                    margin-bottom: 4px;
                }
            """)
        else:
            self.setStyleSheet("""
                ArticleCardWidget {
                    background-color: transparent;
                    margin-bottom: 4px;
                }
            """)

    def _on_import_clicked(self) -> None:
        """Handle import button click."""
        self.import_btn.setEnabled(False)
        self.import_btn.setText("Importing...")
        self.import_requested.emit(self.article)

    def _add_pdf_buttons(self) -> None:
        """Add PDF buttons for existing articles using QtDocumentCardFactory."""
        if not self.doc_id:
            return

        try:
            from bmlibrarian.gui.qt.qt_document_card_factory import QtDocumentCardFactory
            from bmlibrarian.gui.document_card_factory_base import DocumentCardData, CardContext
            from bmlibrarian.utils.pdf_manager import PDFManager
            from bmlibrarian.config import get_config

            config = get_config()

            # Create PDF manager and factory
            pdf_manager = PDFManager()
            unpaywall_email = config.get('unpaywall_email') if config else None
            factory = QtDocumentCardFactory(
                pdf_manager=pdf_manager,
                base_pdf_dir=pdf_manager.base_dir,
                use_discovery=True,
                unpaywall_email=str(unpaywall_email) if unpaywall_email else None
            )

            # Get document details from database for PDF path
            doc_details = self._get_document_details()

            # Extract year from publication_date
            year = None
            if self.article.publication_date:
                try:
                    year = int(str(self.article.publication_date)[:4])
                except (ValueError, TypeError):
                    pass

            # Create card data for PDF button
            card_data = DocumentCardData(
                doc_id=self.doc_id,
                title=self.article.title or "No title",
                authors=self.article.authors or [],
                year=year,
                doi=self.article.doi,
                pmid=self.article.pmid,
                pdf_path=doc_details.get('pdf_path') if doc_details else None,
                pdf_filename=doc_details.get('pdf_filename') if doc_details else None,
                pdf_url=None,  # PubMed doesn't provide direct PDF URLs
                context=CardContext.LITERATURE,
                show_pdf_button=True
            )

            # Create PDF button widget
            pdf_button_widget = factory._create_pdf_button_for_card(card_data)
            if pdf_button_widget:
                self.document_card.details_layout.addWidget(pdf_button_widget)

        except Exception as e:
            logger.warning(f"Failed to add PDF buttons for article {self.doc_id}: {e}")

    def _get_document_details(self) -> Optional[Dict[str, Any]]:
        """
        Get document details from database for PDF path lookup.

        Returns:
            Dictionary with pdf_filename and pdf_path, or None if not found
        """
        if not self.doc_id:
            return None

        try:
            from bmlibrarian.database import get_db_manager
            db_manager = get_db_manager()

            with db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT pdf_filename FROM document WHERE id = %s",
                        (self.doc_id,)
                    )
                    result = cur.fetchone()
                    if result and result[0]:
                        return {'pdf_filename': result[0]}
            return None
        except Exception as e:
            logger.warning(f"Failed to get document details for {self.doc_id}: {e}")
            return None

    def mark_imported(self, doc_id: int) -> None:
        """
        Mark this article as successfully imported.

        Args:
            doc_id: The database ID assigned to the imported document
        """
        self.is_new = False
        if hasattr(self, 'import_btn'):
            self.import_btn.setText(f"Imported (ID: {doc_id})")
            self.import_btn.setStyleSheet(
                "QPushButton { background-color: #81C784; color: white; "
                "padding: 8px 16px; border-radius: 4px; border: none; }"
            )
        # Update styling to remove green highlight
        self.setStyleSheet("""
            ArticleCardWidget {
                background-color: transparent;
            }
        """)


class PubMedSearchLabWindow(QMainWindow):
    """
    Main window for PubMed Search Lab.

    Provides an interface to:
    1. Enter a research question
    2. Search PubMed directly via API
    3. View results as cards (without storing in database)
    4. See feedback on existing documents
    """

    def __init__(self):
        """Initialize the main window."""
        super().__init__()
        self.config = get_config()
        self.search_worker: Optional[PubMedSearchWorker] = None
        self.current_articles: List[Any] = []

        self._setup_ui()
        self._setup_connections()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        self.setWindowTitle("PubMed Search Lab - BMLibrarian")
        self.setMinimumSize(
            PubMedLabConstants.MIN_WINDOW_WIDTH,
            PubMedLabConstants.MIN_WINDOW_HEIGHT
        )

        # Get DPI-scaled values
        s = get_font_scale()

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(
            s['spacing_large'],
            s['spacing_large'],
            s['spacing_large'],
            s['spacing_large']
        )

        # Title
        title_label = QLabel("PubMed API Search Laboratory")
        title_label.setFont(QFont("", s['font_xlarge'], QFont.Bold))
        title_label.setStyleSheet("color: #1565C0;")
        main_layout.addWidget(title_label)

        subtitle_label = QLabel(
            "Search PubMed directly via NCBI E-utilities API. "
            "Results are displayed without storing in the database."
        )
        subtitle_label.setStyleSheet("color: #666;")
        main_layout.addWidget(subtitle_label)

        main_layout.addSpacing(s['spacing_medium'])

        # Search input section
        search_group = QGroupBox("Research Question")
        search_layout = QVBoxLayout(search_group)

        # Question input - compact single line entry
        self.question_input = QTextEdit()
        self.question_input.setPlaceholderText(
            "Enter your research question (e.g., What are the cardiovascular benefits of exercise?)"
        )
        self.question_input.setMaximumHeight(s['control_height_large'])  # ~40px, compact
        self.question_input.setMinimumHeight(s['control_height_large'])
        search_layout.addWidget(self.question_input)

        # Options row
        options_layout = QHBoxLayout()

        # Max results
        options_layout.addWidget(QLabel("Max results:"))
        self.max_results_spin = QSpinBox()
        self.max_results_spin.setRange(
            PubMedLabConstants.MIN_SEARCH_RESULTS,
            PubMedLabConstants.MAX_SEARCH_RESULTS
        )
        self.max_results_spin.setValue(DEFAULT_MAX_RESULTS)
        self.max_results_spin.setSingleStep(PubMedLabConstants.SEARCH_RESULTS_STEP)
        options_layout.addWidget(self.max_results_spin)

        options_layout.addSpacing(s['spacing_large'])

        # Check existing checkbox
        self.check_existing_cb = QCheckBox("Check for existing documents")
        self.check_existing_cb.setChecked(True)
        self.check_existing_cb.setToolTip(
            "Check if retrieved articles already exist in your local database"
        )
        options_layout.addWidget(self.check_existing_cb)

        options_layout.addStretch()

        # Search button
        self.search_btn = QPushButton("Search PubMed")
        self.search_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                padding: 8px 24px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:pressed {
                background-color: #1565C0;
            }
            QPushButton:disabled {
                background-color: #BDBDBD;
            }
        """)
        options_layout.addWidget(self.search_btn)

        search_layout.addLayout(options_layout)
        main_layout.addWidget(search_group)

        # Progress section
        self.progress_widget = QWidget()
        progress_layout = QVBoxLayout(self.progress_widget)
        progress_layout.setContentsMargins(0, 0, 0, 0)

        self.progress_label = QLabel("Ready")
        self.progress_label.setStyleSheet("color: #666;")
        progress_layout.addWidget(self.progress_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)

        self.progress_widget.setVisible(False)
        main_layout.addWidget(self.progress_widget)

        # Status/feedback section
        self.status_widget = QWidget()
        status_layout = QHBoxLayout(self.status_widget)
        status_layout.setContentsMargins(0, 0, 0, 0)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #666; font-style: italic;")
        status_layout.addWidget(self.status_label, 1)

        self.existing_label = QLabel("")
        self.existing_label.setStyleSheet(
            "color: #4CAF50; font-weight: bold; background-color: #E8F5E9; "
            "padding: 4px 12px; border-radius: 4px;"
        )
        self.existing_label.setVisible(False)
        status_layout.addWidget(self.existing_label)

        main_layout.addWidget(self.status_widget)

        # Query preview section - collapsible, initially collapsed
        self.query_group = QGroupBox("Generated PubMed Query (click to expand)")
        self.query_group.setCheckable(True)
        self.query_group.setChecked(False)  # Start collapsed
        query_layout = QVBoxLayout(self.query_group)
        query_layout.setContentsMargins(s['spacing_small'], 0, s['spacing_small'], s['spacing_small'])

        self.query_preview = QTextEdit()
        self.query_preview.setReadOnly(True)
        self.query_preview.setStyleSheet("background-color: #f5f5f5;")
        self.query_preview.setMaximumHeight(s['control_height_xlarge'] * 2)  # Limit height
        self.query_preview.setVisible(False)  # Hidden when collapsed
        query_layout.addWidget(self.query_preview)

        # Connect checkbox to toggle visibility
        self.query_group.toggled.connect(self._on_query_group_toggled)

        self.query_group.setVisible(False)
        main_layout.addWidget(self.query_group)

        # Results section
        results_group = QGroupBox("Search Results")
        results_layout = QVBoxLayout(results_group)

        # Results header
        results_header = QHBoxLayout()
        self.results_count_label = QLabel("No results yet")
        self.results_count_label.setStyleSheet("color: #666;")
        results_header.addWidget(self.results_count_label)

        results_header.addStretch()

        # Clear button
        self.clear_btn = QPushButton("Clear Results")
        self.clear_btn.setEnabled(False)
        results_header.addWidget(self.clear_btn)

        results_layout.addLayout(results_header)

        # Scrollable results area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.results_container = QWidget()
        self.results_layout = QVBoxLayout(self.results_container)
        self.results_layout.setAlignment(Qt.AlignTop)
        self.results_layout.setSpacing(s['spacing_medium'])

        scroll_area.setWidget(self.results_container)
        results_layout.addWidget(scroll_area, 1)

        main_layout.addWidget(results_group, 1)

    def _setup_connections(self) -> None:
        """Set up signal connections."""
        self.search_btn.clicked.connect(self._on_search_clicked)
        self.clear_btn.clicked.connect(self._clear_results)

    def _on_query_group_toggled(self, checked: bool) -> None:
        """Handle query group checkbox toggle."""
        self.query_preview.setVisible(checked)
        if checked:
            self.query_group.setTitle("Generated PubMed Query (click to collapse)")
        else:
            self.query_group.setTitle("Generated PubMed Query (click to expand)")

    def _on_search_clicked(self) -> None:
        """Handle search button click."""
        question = self.question_input.toPlainText().strip()

        if not question:
            QMessageBox.warning(
                self,
                "Empty Question",
                "Please enter a research question."
            )
            return

        # Disable UI during search
        self.search_btn.setEnabled(False)
        self.progress_widget.setVisible(True)
        self.query_group.setVisible(False)
        self.existing_label.setVisible(False)

        # Clear previous results
        self._clear_results()

        # Create and start worker
        self.search_worker = PubMedSearchWorker(
            question=question,
            max_results=self.max_results_spin.value(),
            check_existing=self.check_existing_cb.isChecked(),
            parent=self
        )

        self.search_worker.progress.connect(self._on_progress)
        self.search_worker.finished.connect(self._on_search_finished)
        self.search_worker.error.connect(self._on_search_error)
        self.search_worker.existing_count.connect(self._on_existing_count)

        self.search_worker.start()

    def _on_progress(self, progress: SearchProgress) -> None:
        """Handle progress updates."""
        self.progress_label.setText(progress.message)
        self.progress_bar.setValue(progress.percent)

        # Show query preview when ready
        if progress.step == "query_ready":
            self.query_preview.setPlainText(progress.message.replace("Query: ", ""))
            self.query_group.setVisible(True)

    def _on_search_finished(self, articles: List, existing_pmid_to_docid: Dict[str, int]) -> None:
        """Handle search completion."""
        self.search_btn.setEnabled(True)
        self.progress_widget.setVisible(False)
        self.current_articles = articles

        # Count new vs existing
        new_count = sum(1 for a in articles if a.pmid not in existing_pmid_to_docid)

        # Update results count
        self.results_count_label.setText(
            f"{len(articles)} articles found ({new_count} new)"
        )
        self.clear_btn.setEnabled(len(articles) > 0)

        # Add article cards - new articles first, then existing
        new_articles = [a for a in articles if a.pmid not in existing_pmid_to_docid]
        existing_articles = [a for a in articles if a.pmid in existing_pmid_to_docid]

        for article in new_articles:
            card = ArticleCardWidget(article, is_new=True)
            card.import_requested.connect(self._on_import_requested)
            self.results_layout.addWidget(card)

        for article in existing_articles:
            doc_id = existing_pmid_to_docid.get(article.pmid)
            card = ArticleCardWidget(article, is_new=False, doc_id=doc_id)
            self.results_layout.addWidget(card)

        # Add stretch at the end
        self.results_layout.addStretch()

        self.status_label.setText(
            f"Search complete. {new_count} new articles, {len(existing_pmid_to_docid)} already in database."
        )

    def _on_search_error(self, error_msg: str) -> None:
        """Handle search error."""
        self.search_btn.setEnabled(True)
        self.progress_widget.setVisible(False)

        QMessageBox.critical(
            self,
            "Search Error",
            f"Search failed:\n\n{error_msg}"
        )

        self.status_label.setText(
            f"Error: {error_msg[:PubMedLabConstants.ERROR_MESSAGE_TRUNCATE]}..."
        )

    def _on_existing_count(self, existing: int, total: int) -> None:
        """Handle existing document count update."""
        if existing > 0:
            self.existing_label.setText(
                f"{existing}/{total} already in database"
            )
            self.existing_label.setVisible(True)
        else:
            self.existing_label.setText("All articles are new")
            self.existing_label.setStyleSheet(
                "color: #2196F3; font-weight: bold; background-color: #E3F2FD; "
                "padding: 4px 12px; border-radius: 4px;"
            )
            self.existing_label.setVisible(True)

    def _on_import_requested(self, article: Any) -> None:
        """
        Handle import request for a PubMed article.

        Args:
            article: ArticleMetadata object to import
        """
        try:
            from bmlibrarian.importers.pubmed_importer import PubMedImporter

            self.status_label.setText(f"Importing PMID {article.pmid}...")

            # Create importer and import by PMID
            importer = PubMedImporter()
            result = importer.import_by_pmids([article.pmid])

            if result.get('imported', 0) > 0:
                # Look up the document ID that was just created
                doc_id = self._get_doc_id_by_pmid(article.pmid)
                if doc_id is not None:
                    self.status_label.setText(f"Imported PMID {article.pmid} as document {doc_id}")

                    # Find the card widget and mark it as imported
                    for i in range(self.results_layout.count()):
                        item = self.results_layout.itemAt(i)
                        if item and item.widget():
                            card = item.widget()
                            if isinstance(card, ArticleCardWidget) and card.article.pmid == article.pmid:
                                card.mark_imported(doc_id)
                                break
                else:
                    self.status_label.setText(f"Imported PMID {article.pmid} but could not retrieve ID")
            else:
                self.status_label.setText(f"PMID {article.pmid} may already exist in database")
                # Check if it already exists
                doc_id = self._get_doc_id_by_pmid(article.pmid)
                if doc_id:
                    for i in range(self.results_layout.count()):
                        item = self.results_layout.itemAt(i)
                        if item and item.widget():
                            card = item.widget()
                            if isinstance(card, ArticleCardWidget) and card.article.pmid == article.pmid:
                                card.mark_imported(doc_id)
                                break
                else:
                    # Re-enable the import button
                    self._reset_import_button(article.pmid)

        except Exception as e:
            logger.exception(f"Failed to import article PMID {article.pmid}")
            self.status_label.setText(f"Error importing: {str(e)[:50]}...")
            self._reset_import_button(article.pmid)

            QMessageBox.warning(
                self,
                "Import Failed",
                f"Failed to import article:\n\n{str(e)}"
            )

    def _get_doc_id_by_pmid(self, pmid: str) -> Optional[int]:
        """
        Look up document ID by PMID.

        Args:
            pmid: PubMed ID

        Returns:
            Document ID or None if not found
        """
        try:
            from bmlibrarian.database import get_db_manager
            db_manager = get_db_manager()

            with db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id FROM document WHERE source_id = 1 AND external_id = %s",
                        (pmid,)
                    )
                    result = cur.fetchone()
                    return result[0] if result else None
        except Exception as e:
            logger.warning(f"Failed to look up document by PMID {pmid}: {e}")
            return None

    def _reset_import_button(self, pmid: str) -> None:
        """
        Reset the import button for an article to its original state.

        Args:
            pmid: PubMed ID of the article
        """
        for i in range(self.results_layout.count()):
            item = self.results_layout.itemAt(i)
            if item and item.widget():
                card = item.widget()
                if isinstance(card, ArticleCardWidget) and card.article.pmid == pmid:
                    if hasattr(card, 'import_btn'):
                        card.import_btn.setEnabled(True)
                        card.import_btn.setText("Import to Database")
                    break

    def _clear_results(self) -> None:
        """Clear all results."""
        # Remove all widgets from results layout
        while self.results_layout.count():
            item = self.results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.current_articles = []
        self.results_count_label.setText("No results yet")
        self.clear_btn.setEnabled(False)
        self.existing_label.setVisible(False)
        self.status_label.setText("")

    def closeEvent(self, event) -> None:
        """Handle window close."""
        if self.search_worker and self.search_worker.isRunning():
            self.search_worker.abort()
            self.search_worker.wait(PubMedLabConstants.WORKER_ABORT_TIMEOUT_MS)
        super().closeEvent(event)


def run_pubmed_search_lab() -> None:
    """Run the PubMed Search Lab application."""
    app = QApplication.instance() or QApplication(sys.argv)

    # Apply stylesheet
    try:
        from bmlibrarian.gui.qt.resources.styles.theme_generator import generate_theme
        app.setStyleSheet(generate_theme())
    except ImportError:
        pass  # Use default styling

    window = PubMedSearchLabWindow()
    window.show()

    app.exec()


if __name__ == "__main__":
    run_pubmed_search_lab()
