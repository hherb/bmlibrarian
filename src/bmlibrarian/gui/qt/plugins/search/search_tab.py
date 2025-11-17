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
import re
from datetime import datetime

from bmlibrarian.config import get_config
from bmlibrarian.agents.query_agent import QueryAgent
from bmlibrarian.database import search_hybrid
from ...widgets.document_card import DocumentCard


# ============================================================================
# Configuration Constants - Algorithm Parameters
# ============================================================================
# These constants define default parameters for search algorithms.
# They can be overridden through configuration files or UI controls.

# BM25 ranking algorithm parameters (Best Match 25)
# See: Robertson & Zaragoza (2009) "The Probabilistic Relevance Framework: BM25 and Beyond"
DEFAULT_BM25_K1 = 1.2  # Term frequency saturation parameter (typical range: 1.2-2.0)
DEFAULT_BM25_B = 0.75  # Length normalization parameter (typical range: 0.5-0.8)

# Reciprocal Rank Fusion (RRF) parameter
# See: Cormack, Clarke & Buettcher (2009) "Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods"
DEFAULT_RRF_K = 60  # RRF constant (typical range: 20-100)

# Default weights for hybrid search fusion
# Higher weights give more importance to that search strategy
DEFAULT_FUSION_WEIGHTS = {
    'keyword': 1.0,     # PostgreSQL full-text search
    'bm25': 1.5,        # BM25 probabilistic ranking
    'semantic': 2.0,    # Vector similarity search
    'hyde': 2.0         # Hypothetical Document Embeddings
}

# Semantic search parameters
DEFAULT_SEMANTIC_THRESHOLD = 0.7  # Minimum cosine similarity score (0.0-1.0)
DEFAULT_EMBEDDING_MODEL = 'snowflake-arctic-embed2:latest'

# HyDE (Hypothetical Document Embeddings) parameters
DEFAULT_HYDE_NUM_DOCS = 3  # Number of hypothetical documents to generate
DEFAULT_HYDE_GENERATION_MODEL = 'medgemma-27b-text-it-Q8_0:latest'
DEFAULT_HYDE_THRESHOLD = 0.7  # Minimum similarity threshold

# Worker shutdown parameters
WORKER_GRACEFUL_SHUTDOWN_TIMEOUT_MS = 3000  # 3 seconds before force termination

# Input validation parameters
MAX_SEARCH_TEXT_LENGTH = 2000  # Maximum length for search input
SUSPICIOUS_SQL_PATTERNS = [
    r';[\s]*DROP', r';[\s]*DELETE', r';[\s]*UPDATE', r';[\s]*INSERT',
    r'--', r'/\*', r'\*/', r'xp_', r'sp_', r'EXEC', r'EXECUTE'
]


# ============================================================================
# Utility Functions - Input Validation and Type Safety
# ============================================================================

def validate_search_input(search_text: str) -> tuple[bool, str]:
    """
    Validate user search input for security and safety.

    Checks for:
    - Empty or whitespace-only input
    - Excessive length
    - Suspicious SQL injection patterns

    Args:
        search_text: User-provided search text

    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if input passes validation
        - error_message: Empty string if valid, error description if invalid
    """
    # Check for empty input
    if not search_text or not search_text.strip():
        return False, "Search text cannot be empty"

    # Check length
    if len(search_text) > MAX_SEARCH_TEXT_LENGTH:
        return False, f"Search text too long (max {MAX_SEARCH_TEXT_LENGTH} characters)"

    # Check for suspicious SQL patterns
    # Note: QueryAgent generates PostgreSQL tsquery, not raw SQL, but defense in depth
    search_upper = search_text.upper()
    for pattern in SUSPICIOUS_SQL_PATTERNS:
        if re.search(pattern, search_upper, re.IGNORECASE):
            return False, "Search text contains potentially unsafe characters"

    return True, ""


def extract_year_from_value(value: Any) -> Optional[int]:
    """
    Safely extract year as integer from various input types.

    Handles:
    - None values (returns None)
    - Integer values (returns directly)
    - String values (attempts to parse)
    - Date/datetime objects (extracts year)
    - Invalid values (returns None)

    Args:
        value: Value to extract year from (can be None, int, str, date, datetime)

    Returns:
        Integer year if successfully extracted, None otherwise

    Examples:
        >>> extract_year_from_value(2024)
        2024
        >>> extract_year_from_value("2024")
        2024
        >>> extract_year_from_value("2024-03-15")
        2024
        >>> extract_year_from_value(datetime(2024, 3, 15))
        2024
        >>> extract_year_from_value(None)
        None
        >>> extract_year_from_value("invalid")
        None
    """
    if value is None:
        return None

    # Handle integer
    if isinstance(value, int):
        # Sanity check for reasonable year range
        if 1800 <= value <= 2200:
            return value
        return None

    # Handle string
    if isinstance(value, str):
        # Try direct conversion first
        try:
            year = int(value)
            if 1800 <= year <= 2200:
                return year
        except ValueError:
            pass

        # Try extracting first 4 digits (for ISO date strings like "2024-03-15")
        try:
            if len(value) >= 4:
                year = int(value[:4])
                if 1800 <= year <= 2200:
                    return year
        except ValueError:
            pass

    # Handle date/datetime objects
    if hasattr(value, 'year'):
        try:
            year = int(value.year)
            if 1800 <= year <= 2200:
                return year
        except (ValueError, TypeError):
            pass

    return None


class SearchWorker(QThread):
    """Worker thread for database search to prevent UI blocking."""

    results_ready = Signal(list)
    error_occurred = Signal(str)
    strategy_info = Signal(dict)  # New signal for search strategy feedback

    def __init__(self, search_params: Dict[str, Any]):
        """
        Initialize search worker.

        Args:
            search_params: Search parameters including search strategies
        """
        super().__init__()
        self.search_params = search_params
        self._interrupt_requested = False

    def requestInterruption(self):
        """Request graceful interruption of the search."""
        self._interrupt_requested = True
        super().requestInterruption()

    def run(self):
        """Execute search in background thread."""
        try:
            # Get search text
            search_text = self.search_params.get('text_query', '')
            if not search_text:
                self.results_ready.emit([])
                return

            # Validate search input before processing
            is_valid, error_msg = validate_search_input(search_text)
            if not is_valid:
                self.error_occurred.emit(f"Invalid search input: {error_msg}")
                return

            # Check for interruption
            if self._interrupt_requested:
                return

            # Build search configuration from UI settings
            # Uses constants defined at module level for algorithm parameters
            search_config = {
                'keyword': {
                    'enabled': self.search_params.get('keyword_enabled', True),
                    'max_results': self.search_params.get('limit', 100)
                },
                'bm25': {
                    'enabled': self.search_params.get('bm25_enabled', False),
                    'max_results': self.search_params.get('limit', 100),
                    'k1': DEFAULT_BM25_K1,
                    'b': DEFAULT_BM25_B
                },
                'semantic': {
                    'enabled': self.search_params.get('semantic_enabled', False),
                    'max_results': self.search_params.get('limit', 100),
                    'embedding_model': DEFAULT_EMBEDDING_MODEL,
                    'similarity_threshold': DEFAULT_SEMANTIC_THRESHOLD
                },
                'hyde': {
                    'enabled': self.search_params.get('hyde_enabled', False),
                    'max_results': self.search_params.get('limit', 100),
                    'generation_model': DEFAULT_HYDE_GENERATION_MODEL,
                    'embedding_model': DEFAULT_EMBEDDING_MODEL,
                    'num_hypothetical_docs': DEFAULT_HYDE_NUM_DOCS,
                    'similarity_threshold': DEFAULT_HYDE_THRESHOLD
                },
                'reranking': {
                    'method': self.search_params.get('reranking_method', 'sum_scores'),
                    'rrf_k': DEFAULT_RRF_K,
                    'weights': DEFAULT_FUSION_WEIGHTS.copy()
                }
            }

            # Only generate PostgreSQL tsquery if keyword or BM25 search is enabled
            # Semantic and HyDE search work directly with search_text embeddings
            query_text = None
            needs_fulltext_query = (
                search_config['keyword']['enabled'] or
                search_config['bm25']['enabled']
            )

            if needs_fulltext_query:
                # Generate PostgreSQL tsquery using QueryAgent
                # Note: QueryAgent.convert_question() already performs additional validation
                query_agent = QueryAgent()
                query_text = query_agent.convert_question(search_text)

                # Check for interruption after query generation
                if self._interrupt_requested:
                    return

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

            # Emit strategy information for user feedback
            # Extract strategy-specific result counts from metadata
            strategy_info = {
                'total_before_filters': len(documents),
                'strategies_used': [],
                'strategy_counts': {}
            }

            if strategy_metadata:
                for strategy_name, metadata in strategy_metadata.items():
                    if isinstance(metadata, dict) and metadata.get('documents_found', 0) > 0:
                        strategy_info['strategies_used'].append(strategy_name)
                        strategy_info['strategy_counts'][strategy_name] = metadata.get('documents_found', 0)

            # Apply additional filters (year, journal) if specified
            # Early filtering for memory efficiency
            filtered_docs = self._apply_filters(documents)
            strategy_info['after_filters'] = len(filtered_docs)

            # Sort by combined score (descending) if available, otherwise by date
            if filtered_docs and '_combined_score' in filtered_docs[0]:
                filtered_docs.sort(key=lambda x: x.get('_combined_score', 0), reverse=True)
            else:
                # Sort by publication date if no score available
                filtered_docs.sort(
                    key=lambda x: (x.get('publication_date') or '', x.get('id', 0)),
                    reverse=True
                )

            # Limit results (already filtered, so this is efficient)
            limit = self.search_params.get('limit', 100)
            filtered_docs = filtered_docs[:limit]
            strategy_info['final_count'] = len(filtered_docs)

            # Emit strategy information before results
            self.strategy_info.emit(strategy_info)

            # Emit results
            self.results_ready.emit(filtered_docs)

        except Exception as e:
            import traceback
            error_msg = f"{str(e)}\n\n{traceback.format_exc()}"
            self.error_occurred.emit(error_msg)

    def _apply_filters(self, documents: List[Dict]) -> List[Dict]:
        """
        Apply year filters to documents.

        Uses type-safe year extraction to handle various date formats robustly.

        Args:
            documents: List of document dictionaries

        Returns:
            Filtered list of documents matching year criteria
        """
        filtered = []

        year_from = self.search_params.get('year_from')
        year_to = self.search_params.get('year_to')

        for doc in documents:
            # Year filter with type-safe extraction
            if year_from or year_to:
                # Try to get year from 'year' field first
                doc_year = extract_year_from_value(doc.get('year'))

                # If no year field, try publication_date
                if doc_year is None:
                    pub_date = doc.get('publication_date')
                    if pub_date:
                        doc_year = extract_year_from_value(pub_date)

                # Apply year range filters
                if year_from and (doc_year is None or doc_year < year_from):
                    continue
                if year_to and (doc_year is None or doc_year > year_to):
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

        # Main search box - prominent and wide
        search_box_layout = QHBoxLayout()
        search_label = QLabel("Search for:")
        search_label.setMinimumWidth(80)
        search_box_layout.addWidget(search_label)

        self.text_query_edit = QLineEdit()
        self.text_query_edit.setPlaceholderText("Enter your research question or search query...")
        self.text_query_edit.setMinimumWidth(400)
        self.text_query_edit.returnPressed.connect(self._on_search)
        search_box_layout.addWidget(self.text_query_edit, stretch=1)  # Expand to fill available space

        search_btn = QPushButton("Search")
        search_btn.setStyleSheet(
            "background-color: #3498db; color: white; padding: 8px 20px; font-weight: bold;"
        )
        search_btn.setMinimumWidth(100)
        search_btn.clicked.connect(self._on_search)
        search_box_layout.addWidget(search_btn)

        layout.addLayout(search_box_layout)

        # Filters row 1: Year range
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

        filters_layout1.addStretch()
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

        # Clear button
        button_layout = QHBoxLayout()
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
        self.worker.strategy_info.connect(self._on_strategy_info)
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

    def _on_strategy_info(self, strategy_info: Dict[str, Any]):
        """
        Handle search strategy feedback information.

        Displays which strategies were used and how many documents each found.

        Args:
            strategy_info: Dictionary containing strategy metadata
                - strategies_used: List of strategy names
                - strategy_counts: Dict mapping strategy names to document counts
                - total_before_filters: Total docs before filtering
                - after_filters: Docs after year/journal filters
                - final_count: Final doc count after limit
        """
        # Build strategy feedback message
        strategies = strategy_info.get('strategies_used', [])
        counts = strategy_info.get('strategy_counts', {})

        if strategies:
            strategy_details = []
            for strategy in strategies:
                count = counts.get(strategy, 0)
                strategy_details.append(f"{strategy}: {count}")

            strategy_msg = " | ".join(strategy_details)

            # Show filtering impact if applicable
            total_before = strategy_info.get('total_before_filters', 0)
            after_filter = strategy_info.get('after_filters', 0)
            final = strategy_info.get('final_count', 0)

            if after_filter < total_before:
                strategy_msg += f" → {after_filter} after filters → {final} final"
            elif final < total_before:
                strategy_msg += f" → {final} after limit"

            self.status_message.emit(f"Search strategies: {strategy_msg}")
        else:
            self.status_message.emit("Search completed with no strategy results")

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
        """
        Cleanup resources when tab is closed.

        Implements graceful shutdown with timeout to prevent resource leaks.
        """
        if self.worker and self.worker.isRunning():
            # Request graceful interruption first
            self.worker.requestInterruption()

            # Wait for graceful shutdown with timeout
            if not self.worker.wait(WORKER_GRACEFUL_SHUTDOWN_TIMEOUT_MS):
                # If graceful shutdown times out, force termination as last resort
                self.worker.terminate()
                self.worker.wait()  # Wait for termination to complete
