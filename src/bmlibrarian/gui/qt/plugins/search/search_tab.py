"""
Search Tab Widget for BMLibrarian Qt GUI.

Advanced document search interface with filters and results visualization.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QGroupBox, QScrollArea, QComboBox, QSpinBox,
    QCheckBox, QMessageBox, QFormLayout
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QFont
from typing import Optional, List, Dict, Any
import psycopg

from bmlibrarian.config import get_config
from ...widgets.document_card import DocumentCard


class SearchWorker(QThread):
    """Worker thread for database search to prevent UI blocking."""

    results_ready = Signal(list)
    error_occurred = Signal(str)

    def __init__(self, search_params: Dict[str, Any], db_config: Dict[str, str]):
        """
        Initialize search worker.

        Args:
            search_params: Search parameters (query, filters, limits)
            db_config: Database configuration
        """
        super().__init__()
        self.search_params = search_params
        self.db_config = db_config

    def run(self):
        """Execute search in background thread."""
        try:
            # Connect to database
            conn = psycopg.connect(**self.db_config)
            cursor = conn.cursor()

            # Build query based on search parameters
            query = self._build_query()
            params = self._build_params()

            # Execute search
            cursor.execute(query, params)
            rows = cursor.fetchall()

            # Convert to document dictionaries
            results = []
            for row in rows:
                doc = {
                    'id': row[0],
                    'title': row[1],
                    'authors': row[2],
                    'journal': row[3],  # publication
                    'year': row[4],  # extracted year from publication_date
                    'pmid': row[5],  # external_id
                    'doi': row[6],
                    'abstract': row[7] if len(row) > 7 else None,
                    'source': row[8] if len(row) > 8 else None  # source name
                }
                results.append(doc)

            cursor.close()
            conn.close()

            self.results_ready.emit(results)

        except Exception as e:
            self.error_occurred.emit(str(e))

    def _build_query(self) -> str:
        """Build SQL query based on search parameters."""
        # Base query with joins to get source name
        query = """
            SELECT d.id, d.title, d.authors, d.publication,
                   EXTRACT(YEAR FROM d.publication_date)::integer as pub_year,
                   d.external_id, d.doi, d.abstract, s.name as source_name
            FROM document d
            LEFT JOIN sources s ON d.source_id = s.id
            WHERE 1=1
        """

        # Add text search filter
        if self.search_params.get('text_query'):
            query += " AND (d.title ILIKE %s OR d.abstract ILIKE %s)"

        # Add year range filter
        if self.search_params.get('year_from'):
            query += " AND EXTRACT(YEAR FROM d.publication_date) >= %s"
        if self.search_params.get('year_to'):
            query += " AND EXTRACT(YEAR FROM d.publication_date) <= %s"

        # Add publication (journal) filter
        if self.search_params.get('journal'):
            query += " AND d.publication ILIKE %s"

        # Add source filter
        if self.search_params.get('source'):
            query += " AND s.name = %s"

        # Order by
        query += " ORDER BY d.publication_date DESC NULLS LAST, d.id DESC"

        # Limit
        query += f" LIMIT {self.search_params.get('limit', 100)}"

        return query

    def _build_params(self) -> tuple:
        """Build query parameters."""
        params = []

        # Text search
        if self.search_params.get('text_query'):
            search_term = f"%{self.search_params['text_query']}%"
            params.extend([search_term, search_term])

        # Year range
        if self.search_params.get('year_from'):
            params.append(self.search_params['year_from'])
        if self.search_params.get('year_to'):
            params.append(self.search_params['year_to'])

        # Journal
        if self.search_params.get('journal'):
            params.append(f"%{self.search_params['journal']}%")

        # Source
        if self.search_params.get('source'):
            params.append(self.search_params['source'])

        return tuple(params)


class SearchTabWidget(QWidget):
    """Main Document Search tab widget."""

    status_message = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize Search tab.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)

        self.config = get_config()
        self.worker: Optional[SearchWorker] = None
        self.current_results: List[Dict[str, Any]] = []

        # UI Components
        self.text_query_edit: Optional[QLineEdit] = None
        self.year_from_spin: Optional[QSpinBox] = None
        self.year_to_spin: Optional[QSpinBox] = None
        self.journal_edit: Optional[QLineEdit] = None
        self.source_combo: Optional[QComboBox] = None
        self.limit_spin: Optional[QSpinBox] = None
        self.results_scroll: Optional[QScrollArea] = None
        self.results_container: Optional[QWidget] = None
        self.result_count_label: Optional[QLabel] = None

        self._setup_ui()

    def _setup_ui(self):
        """Setup the user interface."""
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # Title
        title = QLabel("Document Search")
        title_font = QFont("", 16, QFont.Bold)
        title.setFont(title_font)
        main_layout.addWidget(title)

        # Search panel
        search_panel = self._create_search_panel()
        main_layout.addWidget(search_panel)

        # Results panel
        results_panel = self._create_results_panel()
        main_layout.addWidget(results_panel, stretch=1)

    def _create_search_panel(self) -> QGroupBox:
        """
        Create search filters panel.

        Returns:
            Search panel group box
        """
        group = QGroupBox("Search Filters")
        layout = QVBoxLayout(group)
        layout.setSpacing(10)

        # Text search
        text_layout = QFormLayout()
        self.text_query_edit = QLineEdit()
        self.text_query_edit.setPlaceholderText("Search in title or abstract...")
        self.text_query_edit.returnPressed.connect(self._on_search)
        text_layout.addRow("Text Search:", self.text_query_edit)
        layout.addLayout(text_layout)

        # Filters row 1: Year range and Journal
        filters_layout1 = QHBoxLayout()

        # Year from
        year_from_layout = QHBoxLayout()
        year_from_layout.addWidget(QLabel("Year From:"))
        self.year_from_spin = QSpinBox()
        self.year_from_spin.setRange(1900, 2100)
        self.year_from_spin.setValue(2000)
        self.year_from_spin.setSpecialValueText("Any")
        self.year_from_spin.setMinimum(0)
        year_from_layout.addWidget(self.year_from_spin)
        filters_layout1.addLayout(year_from_layout)

        # Year to
        year_to_layout = QHBoxLayout()
        year_to_layout.addWidget(QLabel("Year To:"))
        self.year_to_spin = QSpinBox()
        self.year_to_spin.setRange(1900, 2100)
        self.year_to_spin.setValue(2025)
        self.year_to_spin.setSpecialValueText("Any")
        self.year_to_spin.setMinimum(0)
        year_to_layout.addWidget(self.year_to_spin)
        filters_layout1.addLayout(year_to_layout)

        # Journal
        journal_layout = QHBoxLayout()
        journal_layout.addWidget(QLabel("Journal:"))
        self.journal_edit = QLineEdit()
        self.journal_edit.setPlaceholderText("Any journal")
        journal_layout.addWidget(self.journal_edit)
        filters_layout1.addLayout(journal_layout)

        layout.addLayout(filters_layout1)

        # Filters row 2: Source and Limit
        filters_layout2 = QHBoxLayout()

        # Source
        source_layout = QHBoxLayout()
        source_layout.addWidget(QLabel("Source:"))
        self.source_combo = QComboBox()
        self.source_combo.addItems(["All", "pubmed", "medrxiv"])
        source_layout.addWidget(self.source_combo)
        filters_layout2.addLayout(source_layout)

        # Limit
        limit_layout = QHBoxLayout()
        limit_layout.addWidget(QLabel("Max Results:"))
        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(10, 1000)
        self.limit_spin.setValue(100)
        self.limit_spin.setSingleStep(10)
        limit_layout.addWidget(self.limit_spin)
        filters_layout2.addLayout(limit_layout)

        filters_layout2.addStretch()
        layout.addLayout(filters_layout2)

        # Search button
        button_layout = QHBoxLayout()
        search_btn = QPushButton("Search Documents")
        search_btn.setStyleSheet(
            "background-color: #3498db; color: white; padding: 10px 30px; font-weight: bold;"
        )
        search_btn.clicked.connect(self._on_search)
        button_layout.addWidget(search_btn)

        clear_btn = QPushButton("Clear Filters")
        clear_btn.clicked.connect(self._on_clear_filters)
        button_layout.addWidget(clear_btn)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        return group

    def _create_results_panel(self) -> QGroupBox:
        """
        Create results display panel.

        Returns:
            Results panel group box
        """
        group = QGroupBox("Search Results")
        layout = QVBoxLayout(group)

        # Result count
        self.result_count_label = QLabel("No search performed yet")
        self.result_count_label.setStyleSheet("color: gray; font-style: italic;")
        layout.addWidget(self.result_count_label)

        # Scroll area for results
        self.results_scroll = QScrollArea()
        self.results_scroll.setWidgetResizable(True)
        self.results_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # Container for document cards
        self.results_container = QWidget()
        self.results_layout = QVBoxLayout(self.results_container)
        self.results_layout.setSpacing(10)
        self.results_layout.addStretch()

        self.results_scroll.setWidget(self.results_container)
        layout.addWidget(self.results_scroll)

        return group

    def _on_search(self):
        """Execute search with current filters."""
        # Get search parameters
        search_params = {
            'text_query': self.text_query_edit.text().strip(),
            'year_from': self.year_from_spin.value() if self.year_from_spin.value() > 0 else None,
            'year_to': self.year_to_spin.value() if self.year_to_spin.value() > 0 else None,
            'journal': self.journal_edit.text().strip() or None,
            'source': self.source_combo.currentText() if self.source_combo.currentText() != "All" else None,
            'limit': self.limit_spin.value()
        }

        # Validate at least one search criterion
        if not any([
            search_params['text_query'],
            search_params['year_from'],
            search_params['year_to'],
            search_params['journal'],
            search_params['source']
        ]):
            QMessageBox.warning(
                self,
                "Warning",
                "Please specify at least one search criterion."
            )
            return

        # Get database configuration
        db_config = {
            'dbname': self.config.get('database', {}).get('name', 'knowledgebase'),
            'user': self.config.get('database', {}).get('user', 'postgres'),
            'password': self.config.get('database', {}).get('password', ''),
            'host': self.config.get('database', {}).get('host', 'localhost'),
            'port': self.config.get('database', {}).get('port', 5432)
        }

        # Update status
        self.result_count_label.setText("Searching...")
        self.result_count_label.setStyleSheet("color: blue; font-weight: bold;")
        self.status_message.emit("Searching database...")

        # Run search in background
        self.worker = SearchWorker(search_params, db_config)
        self.worker.results_ready.connect(self._on_results)
        self.worker.error_occurred.connect(self._on_error)
        self.worker.start()

    def _on_results(self, results: List[Dict[str, Any]]):
        """
        Handle search results.

        Args:
            results: List of document dictionaries
        """
        self.current_results = results

        # Clear previous results
        while self.results_layout.count() > 1:  # Keep the stretch at the end
            item = self.results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add new results
        for doc in results:
            card = DocumentCard(doc)
            card.clicked.connect(self._on_document_clicked)
            self.results_layout.insertWidget(self.results_layout.count() - 1, card)

        # Update count
        count = len(results)
        self.result_count_label.setText(f"Found {count} document(s)")
        self.result_count_label.setStyleSheet("color: green; font-weight: bold;")
        self.status_message.emit(f"Found {count} documents")

    def _on_error(self, error: str):
        """
        Handle search error.

        Args:
            error: Error message
        """
        self.result_count_label.setText("Search failed")
        self.result_count_label.setStyleSheet("color: red; font-weight: bold;")
        self.status_message.emit(f"Search failed: {error}")

        QMessageBox.critical(
            self,
            "Search Error",
            f"Search failed:\n\n{error}\n\nPlease check your database connection and configuration."
        )

    def _on_document_clicked(self, document_data: Dict[str, Any]):
        """
        Handle document card click.

        Args:
            document_data: Clicked document data
        """
        # Show document details
        title = document_data.get('title', 'Untitled')
        authors = document_data.get('authors', 'Unknown')
        if isinstance(authors, list):
            authors = ', '.join(authors)

        journal = document_data.get('journal', 'Unknown')
        year = document_data.get('year', 'Unknown')
        pmid = document_data.get('pmid', 'N/A')
        doi = document_data.get('doi', 'N/A')
        abstract = document_data.get('abstract', 'No abstract available')

        details = f"""
<h2>{title}</h2>
<p><b>Authors:</b> {authors}</p>
<p><b>Journal:</b> {journal} ({year})</p>
<p><b>PMID:</b> {pmid} | <b>DOI:</b> {doi}</p>
<hr>
<p><b>Abstract:</b></p>
<p>{abstract}</p>
        """

        msg = QMessageBox(self)
        msg.setWindowTitle("Document Details")
        msg.setText(details)
        msg.setTextFormat(Qt.RichText)
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec()

    def _on_clear_filters(self):
        """Clear all search filters."""
        self.text_query_edit.clear()
        self.year_from_spin.setValue(0)
        self.year_to_spin.setValue(0)
        self.journal_edit.clear()
        self.source_combo.setCurrentIndex(0)
        self.limit_spin.setValue(100)

        # Clear results
        while self.results_layout.count() > 1:
            item = self.results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.result_count_label.setText("Filters cleared")
        self.result_count_label.setStyleSheet("color: gray; font-style: italic;")
        self.status_message.emit("Filters cleared")

    def cleanup(self):
        """Cleanup resources when tab is closed."""
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait()
