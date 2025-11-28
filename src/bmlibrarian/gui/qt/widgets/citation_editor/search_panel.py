"""
Search panel for finding citations.

Provides:
- Search bar for keyword/semantic search
- Document card list with search results
- Integration with semantic search for context-aware results
"""

import logging
from typing import Optional, List, Dict, Any, Callable

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QScrollArea, QFrame, QLabel, QComboBox, QProgressBar
)
from PySide6.QtCore import Signal, Qt, QThread, QTimer

from ...resources.styles import get_font_scale, StylesheetGenerator
from ..document_card import DocumentCard

logger = logging.getLogger(__name__)


# Constants
DEFAULT_SEARCH_LIMIT = 20
SEMANTIC_SEARCH_THRESHOLD = 0.5


class SearchWorker(QThread):
    """Background worker for search operations."""

    results_ready = Signal(list)  # List of document dicts
    error_occurred = Signal(str)  # Error message

    def __init__(
        self,
        query: str,
        search_type: str = "semantic",
        limit: int = DEFAULT_SEARCH_LIMIT,
        parent: Optional[QWidget] = None
    ) -> None:
        """
        Initialize search worker.

        Args:
            query: Search query
            search_type: "semantic" or "keyword"
            limit: Maximum results
            parent: Parent widget
        """
        super().__init__(parent)
        self.query = query
        self.search_type = search_type
        self.limit = limit

    def run(self) -> None:
        """Execute search in background."""
        try:
            if self.search_type == "semantic":
                results = self._semantic_search()
            else:
                results = self._keyword_search()

            self.results_ready.emit(results)

        except Exception as e:
            logger.error(f"Search failed: {e}")
            self.error_occurred.emit(str(e))

    def _semantic_search(self) -> List[Dict[str, Any]]:
        """Perform semantic search."""
        from bmlibrarian.agents.paper_weight.db import semantic_search_documents

        results = semantic_search_documents(
            query=self.query,
            limit=self.limit,
            threshold=SEMANTIC_SEARCH_THRESHOLD
        )

        # Add additional metadata for document cards
        return self._enrich_results(results)

    def _keyword_search(self) -> List[Dict[str, Any]]:
        """Perform keyword search."""
        from bmlibrarian.database import get_db_manager

        db = get_db_manager()

        with db.get_connection() as conn:
            with conn.cursor() as cur:
                # Full-text search on title and abstract
                cur.execute(
                    """
                    SELECT
                        d.id,
                        d.title,
                        CASE WHEN d.source_id = 1 THEN d.external_id ELSE NULL END as pmid,
                        d.doi,
                        EXTRACT(YEAR FROM d.publication_date)::INTEGER as year,
                        d.journal,
                        ts_rank(
                            to_tsvector('english', COALESCE(d.title, '') || ' ' || COALESCE(d.abstract, '')),
                            plainto_tsquery('english', %s)
                        ) as relevance
                    FROM public.document d
                    WHERE to_tsvector('english', COALESCE(d.title, '') || ' ' || COALESCE(d.abstract, ''))
                          @@ plainto_tsquery('english', %s)
                    ORDER BY relevance DESC
                    LIMIT %s
                    """,
                    (self.query, self.query, self.limit)
                )
                rows = cur.fetchall()

        results = [
            {
                'id': row[0],
                'document_id': row[0],
                'title': row[1],
                'pmid': row[2],
                'doi': row[3],
                'year': row[4],
                'journal': row[5],
                'relevance_score': float(row[6]) if row[6] else None
            }
            for row in rows
        ]

        return self._enrich_results(results)

    def _enrich_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Add author information to results."""
        if not results:
            return results

        from bmlibrarian.database import get_db_manager

        db = get_db_manager()
        doc_ids = [r['id'] for r in results]

        with db.get_connection() as conn:
            with conn.cursor() as cur:
                # Authors are stored as text[] array in document table
                cur.execute(
                    """
                    SELECT
                        id,
                        array_to_string(authors, ', ') as authors_str
                    FROM public.document
                    WHERE id = ANY(%s)
                    """,
                    (doc_ids,)
                )
                author_map = {row[0]: row[1] for row in cur.fetchall()}

        for result in results:
            result['authors'] = author_map.get(result['id'], '')
            result['document_id'] = result['id']

        return results


class CitationSearchPanel(QWidget):
    """
    Search panel for finding citations.

    Signals:
        document_selected: Emitted when a document card is clicked
        document_double_clicked: Emitted when a document card is double-clicked
    """

    document_selected = Signal(dict)  # Document data
    document_double_clicked = Signal(dict)  # Document data

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize search panel.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        self.scale = get_font_scale()
        self.style_gen = StylesheetGenerator()

        self._search_worker: Optional[SearchWorker] = None
        self._search_results: List[Dict[str, Any]] = []
        self._document_cards: List[DocumentCard] = []

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        s = self.scale

        layout = QVBoxLayout(self)
        layout.setContentsMargins(s['padding_small'], s['padding_small'],
                                  s['padding_small'], s['padding_small'])
        layout.setSpacing(s['spacing_small'])

        # Search bar area
        search_layout = QHBoxLayout()
        search_layout.setSpacing(s['spacing_small'])

        # Search input
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search for citations...")
        self.search_input.setStyleSheet(self.style_gen.input_stylesheet())
        search_layout.addWidget(self.search_input, 1)

        # Search type dropdown
        self.search_type = QComboBox()
        self.search_type.addItems(["Semantic", "Keyword"])
        self.search_type.setToolTip("Search type: Semantic uses AI similarity, Keyword uses text matching")
        self.search_type.setStyleSheet(self.style_gen.combo_stylesheet())
        search_layout.addWidget(self.search_type)

        # Search button
        self.search_btn = QPushButton("Search")
        self.search_btn.setStyleSheet(
            self.style_gen.button_stylesheet(
                bg_color="#2196F3",
                hover_color="#1976D2"
            )
        )
        search_layout.addWidget(self.search_btn)

        layout.addLayout(search_layout)

        # Progress bar (hidden by default)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        # Results count label
        self.results_label = QLabel("Enter a search query to find citations")
        self.results_label.setStyleSheet(
            self.style_gen.label_stylesheet(font_size_key='font_small', color='#666')
        )
        layout.addWidget(self.results_label)

        # Scrollable results area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Container for document cards
        self.results_container = QWidget()
        self.results_layout = QVBoxLayout(self.results_container)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        self.results_layout.setSpacing(s['spacing_small'])
        self.results_layout.addStretch()

        self.scroll_area.setWidget(self.results_container)
        layout.addWidget(self.scroll_area, 1)

    def _connect_signals(self) -> None:
        """Connect signal handlers."""
        self.search_btn.clicked.connect(self._on_search)
        self.search_input.returnPressed.connect(self._on_search)

    def _on_search(self) -> None:
        """Handle search button click."""
        query = self.search_input.text().strip()
        if not query:
            return

        self.search(query)

    def search(self, query: str, search_type: Optional[str] = None) -> None:
        """
        Perform a search.

        Args:
            query: Search query
            search_type: Override search type ("semantic" or "keyword")
        """
        if not query.strip():
            return

        # Cancel any existing search
        if self._search_worker and self._search_worker.isRunning():
            self._search_worker.terminate()
            self._search_worker.wait()

        # Determine search type
        if search_type is None:
            search_type = "semantic" if self.search_type.currentIndex() == 0 else "keyword"

        # Update UI
        self.progress_bar.show()
        self.results_label.setText("Searching...")
        self.search_btn.setEnabled(False)

        # Start search worker
        self._search_worker = SearchWorker(query, search_type)
        self._search_worker.results_ready.connect(self._on_results_ready)
        self._search_worker.error_occurred.connect(self._on_search_error)
        self._search_worker.start()

    def _on_results_ready(self, results: List[Dict[str, Any]]) -> None:
        """
        Handle search results.

        Deduplicates by document ID and sorts by similarity score (highest first).

        Args:
            results: List of document dictionaries
        """
        self.progress_bar.hide()
        self.search_btn.setEnabled(True)

        # Deduplicate by document ID, keeping highest similarity
        deduped = self._deduplicate_results(results)

        self._search_results = deduped
        self._display_results(deduped)

        # Update label
        count = len(deduped)
        original_count = len(results)
        if count == 0:
            self.results_label.setText("No results found")
        elif count == 1:
            self.results_label.setText("1 result found")
        elif count < original_count:
            self.results_label.setText(f"{count} unique results (from {original_count})")
        else:
            self.results_label.setText(f"{count} results found")

    def _deduplicate_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Deduplicate results by document ID, keeping highest similarity score.

        Args:
            results: List of document dictionaries

        Returns:
            Deduplicated list sorted by similarity (highest first)
        """
        if not results:
            return results

        # Track best result for each document ID
        best_by_id: Dict[int, Dict[str, Any]] = {}

        for result in results:
            doc_id = result.get('id') or result.get('document_id')
            if doc_id is None:
                continue

            # Get similarity score (semantic) or relevance_score (keyword)
            score = result.get('similarity') or result.get('relevance_score') or 0

            if doc_id not in best_by_id:
                best_by_id[doc_id] = result
            else:
                existing_score = (
                    best_by_id[doc_id].get('similarity') or
                    best_by_id[doc_id].get('relevance_score') or 0
                )
                if score > existing_score:
                    best_by_id[doc_id] = result

        # Sort by similarity/relevance score (highest first)
        deduped = list(best_by_id.values())
        deduped.sort(
            key=lambda x: x.get('similarity') or x.get('relevance_score') or 0,
            reverse=True
        )

        return deduped

    def _on_search_error(self, error: str) -> None:
        """
        Handle search error.

        Args:
            error: Error message
        """
        self.progress_bar.hide()
        self.search_btn.setEnabled(True)
        self.results_label.setText(f"Search error: {error}")
        logger.error(f"Search error: {error}")

    def _display_results(self, results: List[Dict[str, Any]]) -> None:
        """
        Display search results as document cards.

        Args:
            results: List of document dictionaries
        """
        # Clear existing cards
        self._clear_results()

        s = self.scale

        # Create cards for each result
        for doc_data in results:
            try:
                card = DocumentCard(doc_data)
                card.clicked.connect(self._on_card_clicked)
                card.setProperty("document_id", doc_data.get('id'))

                # Enable double-click
                card.mouseDoubleClickEvent = lambda e, d=doc_data: self._on_card_double_clicked(d)

                self._document_cards.append(card)

                # Insert before the stretch
                count = self.results_layout.count()
                self.results_layout.insertWidget(count - 1, card)

            except Exception as e:
                logger.error(f"Failed to create document card: {e}")

    def _clear_results(self) -> None:
        """Clear all result cards."""
        for card in self._document_cards:
            self.results_layout.removeWidget(card)
            card.deleteLater()
        self._document_cards = []

    def _on_card_clicked(self, doc_data: Dict[str, Any]) -> None:
        """
        Handle card click.

        Args:
            doc_data: Document data dictionary
        """
        self.document_selected.emit(doc_data)

    def _on_card_double_clicked(self, doc_data: Dict[str, Any]) -> None:
        """
        Handle card double-click.

        Args:
            doc_data: Document data dictionary
        """
        self.document_double_clicked.emit(doc_data)

    def set_search_query(self, query: str) -> None:
        """
        Set the search query text.

        Args:
            query: Search query to set
        """
        self.search_input.setText(query)

    def get_results(self) -> List[Dict[str, Any]]:
        """
        Get current search results.

        Returns:
            List of document dictionaries
        """
        return self._search_results.copy()

    def clear(self) -> None:
        """Clear search results and input."""
        self.search_input.clear()
        self._clear_results()
        self._search_results = []
        self.results_label.setText("Enter a search query to find citations")
