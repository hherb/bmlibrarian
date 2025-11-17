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
from bmlibrarian.agents.query_agent import QueryAgent
from bmlibrarian.database import search_hybrid
from ...widgets.document_card import DocumentCard


class SearchWorker(QThread):
    """Worker thread for database search to prevent UI blocking."""

    results_ready = Signal(list)
    error_occurred = Signal(str)

    def __init__(self, search_params: Dict[str, Any]):
        """
        Initialize search worker.

        Args:
            search_params: Search parameters including search strategies
        """
        super().__init__()
        self.search_params = search_params

    def run(self):
        """Execute search in background thread."""
        try:
            # Get search text
            search_text = self.search_params.get('text_query', '')
            if not search_text:
                self.results_ready.emit([])
                return

            # Generate PostgreSQL tsquery using QueryAgent
            query_agent = QueryAgent()
            query_text = query_agent.generate_query(search_text)

            # Build search configuration from UI settings
            search_config = {
                'keyword': {
                    'enabled': self.search_params.get('keyword_enabled', True),
                    'max_results': self.search_params.get('limit', 100)
                },
                'bm25': {
                    'enabled': self.search_params.get('bm25_enabled', False),
                    'max_results': self.search_params.get('limit', 100),
                    'k1': 1.2,
                    'b': 0.75
                },
                'semantic': {
                    'enabled': self.search_params.get('semantic_enabled', False),
                    'max_results': self.search_params.get('limit', 100),
                    'embedding_model': 'snowflake-arctic-embed2:latest',
                    'similarity_threshold': 0.7
                },
                'hyde': {
                    'enabled': self.search_params.get('hyde_enabled', False),
                    'max_results': self.search_params.get('limit', 100),
                    'generation_model': 'medgemma-27b-text-it-Q8_0:latest',
                    'embedding_model': 'snowflake-arctic-embed2:latest',
                    'num_hypothetical_docs': 3,
                    'similarity_threshold': 0.7
                },
                'reranking': {
                    'method': self.search_params.get('reranking_method', 'sum_scores'),
                    'rrf_k': 60,
                    'weights': {
                        'keyword': 1.0,
                        'bm25': 1.5,
                        'semantic': 2.0,
                        'hyde': 2.0
                    }
                }
            }

            # Determine source filters
            use_pubmed = self.search_params.get('source') in [None, 'pubmed']
            use_medrxiv = self.search_params.get('source') in [None, 'medrxiv']
            use_others = self.search_params.get('source') is None

            # Execute hybrid search
            documents, strategy_metadata = search_hybrid(
                search_text=search_text,
                query_text=query_text,
                search_config=search_config,
                use_pubmed=use_pubmed,
                use_medrxiv=use_medrxiv,
                use_others=use_others
            )

            # Apply additional filters (year, journal) if specified
            filtered_docs = self._apply_filters(documents)

            # Sort by combined score (descending) if available, otherwise by date
            if filtered_docs and '_combined_score' in filtered_docs[0]:
                filtered_docs.sort(key=lambda x: x.get('_combined_score', 0), reverse=True)
            else:
                # Sort by publication date if no score available
                filtered_docs.sort(
                    key=lambda x: (x.get('publication_date') or '', x.get('id', 0)),
                    reverse=True
                )

            # Limit results
            limit = self.search_params.get('limit', 100)
            filtered_docs = filtered_docs[:limit]

            self.results_ready.emit(filtered_docs)

        except Exception as e:
            import traceback
            error_msg = f"{str(e)}\n\n{traceback.format_exc()}"
            self.error_occurred.emit(error_msg)

    def _apply_filters(self, documents: List[Dict]) -> List[Dict]:
        """Apply year and journal filters to documents."""
        filtered = []

        year_from = self.search_params.get('year_from')
        year_to = self.search_params.get('year_to')
        journal_filter = self.search_params.get('journal', '').strip().lower()

        for doc in documents:
            # Year filter
            if year_from or year_to:
                doc_year = doc.get('year')
                if doc_year is None:
                    # Try to extract from publication_date
                    pub_date = doc.get('publication_date')
                    if pub_date:
                        if isinstance(pub_date, str):
                            try:
                                doc_year = int(pub_date[:4])
                            except (ValueError, IndexError):
                                continue
                        else:
                            doc_year = pub_date.year

                if year_from and (doc_year is None or doc_year < year_from):
                    continue
                if year_to and (doc_year is None or doc_year > year_to):
                    continue

            # Journal filter
            if journal_filter:
                doc_journal = (doc.get('journal') or doc.get('publication') or '').lower()
                if journal_filter not in doc_journal:
                    continue

            filtered.append(doc)

        return filtered


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

        # Load search strategy settings from config
        search_strategy_config = self.config.get('search_strategy', {})
        self.keyword_enabled = search_strategy_config.get('keyword', {}).get('enabled', True)
        self.bm25_enabled = search_strategy_config.get('bm25', {}).get('enabled', False)
        self.semantic_enabled = search_strategy_config.get('semantic', {}).get('enabled', False)
        self.hyde_enabled = search_strategy_config.get('hyde', {}).get('enabled', False)
        self.reranking_method = search_strategy_config.get('reranking', {}).get('method', 'sum_scores')

        # UI Components
        self.text_query_edit: Optional[QLineEdit] = None
        self.year_from_spin: Optional[QSpinBox] = None
        self.year_to_spin: Optional[QSpinBox] = None
        self.journal_edit: Optional[QLineEdit] = None
        self.source_combo: Optional[QComboBox] = None
        self.limit_spin: Optional[QSpinBox] = None
        self.keyword_check: Optional[QCheckBox] = None
        self.bm25_check: Optional[QCheckBox] = None
        self.semantic_check: Optional[QCheckBox] = None
        self.hyde_check: Optional[QCheckBox] = None
        self.reranking_combo: Optional[QComboBox] = None
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

        # Search Strategies section
        strategies_layout = self._create_search_strategies_section()
        layout.addLayout(strategies_layout)

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

    def _create_search_strategies_section(self) -> QVBoxLayout:
        """
        Create search strategies and re-ranking section.

        Returns:
            Layout containing strategy checkboxes and re-ranking dropdown
        """
        section_layout = QVBoxLayout()

        # Title
        title = QLabel("Search Strategies & Re-ranking")
        title.setStyleSheet("font-weight: bold; color: #555; font-size: 11px;")
        section_layout.addWidget(title)

        # Checkboxes and dropdown row
        controls_layout = QHBoxLayout()

        # Keyword checkbox
        self.keyword_check = QCheckBox("Keyword")
        self.keyword_check.setChecked(self.keyword_enabled)
        self.keyword_check.setToolTip("PostgreSQL full-text search")
        self.keyword_check.stateChanged.connect(self._on_keyword_changed)
        controls_layout.addWidget(self.keyword_check)

        # BM25 checkbox
        self.bm25_check = QCheckBox("BM25")
        self.bm25_check.setChecked(self.bm25_enabled)
        self.bm25_check.setToolTip("Probabilistic ranking (BM25)")
        self.bm25_check.stateChanged.connect(self._on_bm25_changed)
        controls_layout.addWidget(self.bm25_check)

        # Semantic checkbox
        self.semantic_check = QCheckBox("Semantic")
        self.semantic_check.setChecked(self.semantic_enabled)
        self.semantic_check.setToolTip("Vector similarity search using embeddings")
        self.semantic_check.stateChanged.connect(self._on_semantic_changed)
        controls_layout.addWidget(self.semantic_check)

        # HyDE checkbox
        self.hyde_check = QCheckBox("HyDE")
        self.hyde_check.setChecked(self.hyde_enabled)
        self.hyde_check.setToolTip("Hypothetical Document Embeddings search")
        self.hyde_check.stateChanged.connect(self._on_hyde_changed)
        controls_layout.addWidget(self.hyde_check)

        # Spacer
        controls_layout.addSpacing(20)

        # Re-ranking dropdown
        controls_layout.addWidget(QLabel("Re-ranking:"))
        self.reranking_combo = QComboBox()
        self.reranking_combo.addItem("Sum Scores", "sum_scores")
        self.reranking_combo.addItem("RRF (Reciprocal Rank Fusion)", "rrf")
        self.reranking_combo.addItem("Max Score", "max_score")
        self.reranking_combo.addItem("Weighted Fusion", "weighted")
        self.reranking_combo.setToolTip("Method for combining results from multiple strategies")
        self.reranking_combo.setCurrentText(self._get_reranking_display_name(self.reranking_method))
        self.reranking_combo.currentIndexChanged.connect(self._on_reranking_changed)
        controls_layout.addWidget(self.reranking_combo)

        controls_layout.addStretch()
        section_layout.addLayout(controls_layout)

        return section_layout

    def _get_reranking_display_name(self, method: str) -> str:
        """Get display name for re-ranking method."""
        mapping = {
            'sum_scores': 'Sum Scores',
            'rrf': 'RRF (Reciprocal Rank Fusion)',
            'max_score': 'Max Score',
            'weighted': 'Weighted Fusion'
        }
        return mapping.get(method, 'Sum Scores')

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

    def _on_keyword_changed(self, state):
        """Handle keyword search checkbox change."""
        self.keyword_enabled = self.keyword_check.isChecked()

    def _on_bm25_changed(self, state):
        """Handle BM25 search checkbox change."""
        self.bm25_enabled = self.bm25_check.isChecked()

    def _on_semantic_changed(self, state):
        """Handle semantic search checkbox change."""
        self.semantic_enabled = self.semantic_check.isChecked()

    def _on_hyde_changed(self, state):
        """Handle HyDE search checkbox change."""
        self.hyde_enabled = self.hyde_check.isChecked()

    def _on_reranking_changed(self, index):
        """Handle re-ranking method dropdown change."""
        self.reranking_method = self.reranking_combo.itemData(index)

    def _on_search(self):
        """Execute search with current filters."""
        # Get search parameters
        search_params = {
            'text_query': self.text_query_edit.text().strip(),
            'year_from': self.year_from_spin.value() if self.year_from_spin.value() > 0 else None,
            'year_to': self.year_to_spin.value() if self.year_to_spin.value() > 0 else None,
            'journal': self.journal_edit.text().strip() or None,
            'source': self.source_combo.currentText() if self.source_combo.currentText() != "All" else None,
            'limit': self.limit_spin.value(),
            # Search strategy settings
            'keyword_enabled': self.keyword_enabled,
            'bm25_enabled': self.bm25_enabled,
            'semantic_enabled': self.semantic_enabled,
            'hyde_enabled': self.hyde_enabled,
            'reranking_method': self.reranking_method
        }

        # Validate at least one search criterion
        if not search_params['text_query']:
            QMessageBox.warning(
                self,
                "Warning",
                "Please enter a search query."
            )
            return

        # Validate at least one search strategy is enabled
        if not any([
            self.keyword_enabled,
            self.bm25_enabled,
            self.semantic_enabled,
            self.hyde_enabled
        ]):
            QMessageBox.warning(
                self,
                "Warning",
                "Please enable at least one search strategy."
            )
            return

        # Update status
        self.result_count_label.setText("Searching...")
        self.result_count_label.setStyleSheet("color: blue; font-weight: bold;")
        self.status_message.emit("Searching database...")

        # Run search in background
        self.worker = SearchWorker(search_params)
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
