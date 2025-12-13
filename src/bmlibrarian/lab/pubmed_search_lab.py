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

from bmlibrarian.config import get_config
from bmlibrarian.gui.qt.resources.styles.dpi_scale import get_font_scale
from bmlibrarian.gui.qt.resources.constants import DefaultLimits
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
    QUERY_PREVIEW_CHARS: Final[int] = 100
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
    finished = Signal(list)  # List[ArticleMetadata]
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
                message=f"Query: {query.query_string[:PubMedLabConstants.QUERY_PREVIEW_CHARS]}...",
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
            existing_count = 0
            if self.check_existing and articles:
                self.progress.emit(SearchProgress(
                    step="check_existing",
                    message="Checking for existing documents in database...",
                    percent=80
                ))

                try:
                    existing_count = self._count_existing_documents(articles)
                except Exception as e:
                    logger.warning(f"Failed to check existing documents: {e}")

                self.existing_count.emit(existing_count, len(articles))

            # Complete
            self.progress.emit(SearchProgress(
                step="complete",
                message=f"Retrieved {len(articles)} articles ({existing_count} already in database)",
                percent=100
            ))

            self.finished.emit(articles)

        except Exception as e:
            logger.exception("PubMed search failed")
            self.error.emit(str(e))

    def _count_existing_documents(self, articles: List) -> int:
        """
        Count how many articles already exist in the local database.

        Args:
            articles: List of ArticleMetadata objects

        Returns:
            Count of existing documents
        """
        try:
            from bmlibrarian.database import get_db_manager

            db_manager = get_db_manager()
            pmids = [a.pmid for a in articles if a.pmid]

            if not pmids:
                return 0

            with db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    # Check by PMID
                    placeholders = ','.join(['%s'] * len(pmids))
                    cur.execute(
                        f"SELECT COUNT(*) FROM document WHERE pmid IN ({placeholders})",
                        pmids
                    )
                    result = cur.fetchone()
                    return result[0] if result else 0

        except Exception as e:
            logger.warning(f"Database check failed: {e}")
            return 0


class ArticleCardWidget(QFrame):
    """
    A card widget displaying article metadata.

    Shows title, authors, journal, year, abstract preview, and identifiers.
    Similar to CollapsibleDocumentCard but for PubMed articles (not database documents).
    """

    def __init__(self, article: Any, parent: Optional[QWidget] = None):
        """
        Initialize article card.

        Args:
            article: ArticleMetadata object
            parent: Parent widget
        """
        super().__init__(parent)
        self.article = article
        self._expanded = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        self.setLineWidth(1)

        # Get DPI-scaled values
        s = get_font_scale()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            s['layout_spacing_medium'],
            s['layout_spacing_medium'],
            s['layout_spacing_medium'],
            s['layout_spacing_medium']
        )
        layout.setSpacing(s['layout_spacing_small'])

        # Header row with title and expand button
        header_layout = QHBoxLayout()

        # Title
        title_label = QLabel(self.article.title or "No title")
        title_label.setWordWrap(True)
        title_label.setFont(QFont("", s['font_size_medium'], QFont.Bold))
        title_label.setStyleSheet("color: #1565C0;")  # Blue
        header_layout.addWidget(title_label, 1)

        # Expand/collapse button
        self.expand_btn = QPushButton("Show details")
        self.expand_btn.setFixedWidth(s['control_width_small'])
        self.expand_btn.clicked.connect(self._toggle_expanded)
        header_layout.addWidget(self.expand_btn)

        layout.addLayout(header_layout)

        # Authors (truncated for display)
        if self.article.authors:
            max_authors = DefaultLimits.MAX_AUTHORS_DISPLAY
            authors_text = ", ".join(self.article.authors[:max_authors])
            if len(self.article.authors) > max_authors:
                authors_text += f" ... (+{len(self.article.authors) - max_authors} more)"
            authors_label = QLabel(authors_text)
            authors_label.setStyleSheet("color: #666;")
            layout.addWidget(authors_label)

        # Journal and year
        meta_parts = []
        if self.article.publication:
            meta_parts.append(self.article.publication)
        if self.article.publication_date:
            meta_parts.append(str(self.article.publication_date)[:PubMedLabConstants.DATE_YEAR_CHARS])
        if meta_parts:
            meta_label = QLabel(" | ".join(meta_parts))
            meta_label.setStyleSheet("color: #888; font-style: italic;")
            layout.addWidget(meta_label)

        # Identifiers row
        id_parts = []
        if self.article.pmid:
            id_parts.append(f"PMID: {self.article.pmid}")
        if self.article.doi:
            id_parts.append(f"DOI: {self.article.doi}")
        if self.article.pmc_id:
            id_parts.append(f"PMC: {self.article.pmc_id}")
        if id_parts:
            id_label = QLabel(" | ".join(id_parts))
            id_label.setStyleSheet("color: #999; font-size: 11px;")
            layout.addWidget(id_label)

        # Expandable details section
        self.details_widget = QWidget()
        self.details_widget.setVisible(False)
        details_layout = QVBoxLayout(self.details_widget)
        details_layout.setContentsMargins(0, s['layout_spacing_medium'], 0, 0)

        # Abstract
        if self.article.abstract:
            abstract_label = QLabel("Abstract:")
            abstract_label.setFont(QFont("", s['font_size_small'], QFont.Bold))
            details_layout.addWidget(abstract_label)

            abstract_text = QLabel(self.article.abstract)
            abstract_text.setWordWrap(True)
            abstract_text.setStyleSheet("color: #333; background-color: #f9f9f9; padding: 8px; border-radius: 4px;")
            details_layout.addWidget(abstract_text)

        # MeSH terms
        if self.article.mesh_terms:
            mesh_label = QLabel("MeSH Terms:")
            mesh_label.setFont(QFont("", s['font_size_small'], QFont.Bold))
            details_layout.addWidget(mesh_label)

            mesh_text = QLabel(", ".join(
                self.article.mesh_terms[:PubMedLabConstants.MAX_MESH_TERMS_DISPLAY]
            ))
            mesh_text.setWordWrap(True)
            mesh_text.setStyleSheet("color: #666;")
            details_layout.addWidget(mesh_text)

        # Keywords
        if self.article.keywords:
            kw_label = QLabel("Keywords:")
            kw_label.setFont(QFont("", s['font_size_small'], QFont.Bold))
            details_layout.addWidget(kw_label)

            kw_text = QLabel(", ".join(
                self.article.keywords[:PubMedLabConstants.MAX_KEYWORDS_DISPLAY]
            ))
            kw_text.setWordWrap(True)
            kw_text.setStyleSheet("color: #666;")
            details_layout.addWidget(kw_text)

        layout.addWidget(self.details_widget)

        # Styling
        self.setStyleSheet("""
            ArticleCardWidget {
                background-color: white;
                border: 1px solid #ddd;
                border-radius: 8px;
            }
            ArticleCardWidget:hover {
                border-color: #2196F3;
            }
        """)

    def _toggle_expanded(self) -> None:
        """Toggle the expanded state."""
        self._expanded = not self._expanded
        self.details_widget.setVisible(self._expanded)
        self.expand_btn.setText("Hide details" if self._expanded else "Show details")


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
            s['layout_spacing_large'],
            s['layout_spacing_large'],
            s['layout_spacing_large'],
            s['layout_spacing_large']
        )

        # Title
        title_label = QLabel("PubMed API Search Laboratory")
        title_label.setFont(QFont("", s['font_size_xlarge'], QFont.Bold))
        title_label.setStyleSheet("color: #1565C0;")
        main_layout.addWidget(title_label)

        subtitle_label = QLabel(
            "Search PubMed directly via NCBI E-utilities API. "
            "Results are displayed without storing in the database."
        )
        subtitle_label.setStyleSheet("color: #666;")
        main_layout.addWidget(subtitle_label)

        main_layout.addSpacing(s['layout_spacing_medium'])

        # Search input section
        search_group = QGroupBox("Research Question")
        search_layout = QVBoxLayout(search_group)

        # Question input
        self.question_input = QTextEdit()
        self.question_input.setPlaceholderText(
            "Enter your research question in natural language...\n\n"
            "Example: What are the cardiovascular benefits of exercise in elderly patients?"
        )
        self.question_input.setMaximumHeight(100)
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

        options_layout.addSpacing(s['layout_spacing_large'])

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

        # Query preview section
        self.query_group = QGroupBox("Generated PubMed Query")
        query_layout = QVBoxLayout(self.query_group)

        self.query_preview = QTextEdit()
        self.query_preview.setReadOnly(True)
        self.query_preview.setMaximumHeight(80)
        self.query_preview.setStyleSheet("background-color: #f5f5f5;")
        query_layout.addWidget(self.query_preview)

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
        self.results_layout.setSpacing(s['layout_spacing_medium'])

        scroll_area.setWidget(self.results_container)
        results_layout.addWidget(scroll_area, 1)

        main_layout.addWidget(results_group, 1)

    def _setup_connections(self) -> None:
        """Set up signal connections."""
        self.search_btn.clicked.connect(self._on_search_clicked)
        self.clear_btn.clicked.connect(self._clear_results)

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

    def _on_search_finished(self, articles: List) -> None:
        """Handle search completion."""
        self.search_btn.setEnabled(True)
        self.progress_widget.setVisible(False)
        self.current_articles = articles

        # Update results count
        self.results_count_label.setText(f"{len(articles)} articles found")
        self.clear_btn.setEnabled(len(articles) > 0)

        # Add article cards
        for article in articles:
            card = ArticleCardWidget(article)
            self.results_layout.addWidget(card)

        # Add stretch at the end
        self.results_layout.addStretch()

        self.status_label.setText(f"Search complete. Retrieved {len(articles)} articles.")

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
