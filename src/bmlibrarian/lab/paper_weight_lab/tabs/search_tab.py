"""
Paper Weight Laboratory - Search Tab

Tab widget for searching and selecting documents.
"""

from typing import Optional, List, Dict

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QTreeWidget, QTreeWidgetItem,
    QMessageBox, QGroupBox,
)
from PySide6.QtCore import Signal

from bmlibrarian.gui.qt.resources.styles.dpi_scale import get_font_scale
from bmlibrarian.gui.qt.resources.styles.stylesheet_generator import get_stylesheet_generator
from bmlibrarian.agents.paper_weight import (
    search_documents,
    semantic_search_documents,
    get_recent_assessments,
)

from ..utils import format_recent_assessment_display


class SearchTab(QWidget):
    """
    Tab widget for document search and selection.

    Provides keyword and semantic search capabilities with
    a results list and recent assessments dropdown.

    Signals:
        document_selected: Emitted when a document is selected.
            Args: document_id (int)
    """

    document_selected = Signal(int)

    def __init__(self, parent: Optional[object] = None):
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
        self.search_type_combo.addItem("Title/PMID/DOI (keyword)", "keyword")
        self.search_type_combo.addItem("Semantic (natural language)", "semantic")
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
            "Enter PMID, DOI, or title keywords..."
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

        self.results_tree = QTreeWidget()
        self.results_tree.setHeaderLabels(["ID", "Title", "PMID", "Year"])
        self.results_tree.setColumnWidth(0, self.scale['char_width'] * 8)
        self.results_tree.setColumnWidth(1, self.scale['char_width'] * 60)
        self.results_tree.setColumnWidth(2, self.scale['char_width'] * 12)
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

            item = QTreeWidgetItem([
                str(doc['id']),
                doc['title'] or 'No title',
                str(doc['pmid'] or ''),
                year_text
            ])
            # Set full title as tooltip for truncated display
            item.setToolTip(1, doc['title'] or 'No title')
            self.results_tree.addTopLevelItem(item)

        if not self.search_results:
            QMessageBox.information(
                self,
                "No Results",
                f"No documents found matching: {query}"
            )

    def _on_selection_changed(self) -> None:
        """Enable/disable select button based on selection."""
        has_selection = len(self.results_tree.selectedItems()) > 0
        self.select_btn.setEnabled(has_selection)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle double-click on result item."""
        self._select_document()

    def _select_document(self) -> None:
        """Select current document and emit signal."""
        current = self.results_tree.currentItem()
        if current:
            document_id = int(current.text(0))
            self.document_selected.emit(document_id)
        else:
            QMessageBox.warning(
                self,
                "No Selection",
                "Please select a document from the list."
            )


__all__ = ['SearchTab']
