"""
Document browser page for the Setup Wizard.

Contains the page for browsing imported documents to verify import success.
"""

import logging
import re
from typing import Optional, List, Dict, Any, TYPE_CHECKING

from PySide6.QtWidgets import (
    QWizardPage,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTextBrowser,
    QPushButton,
    QSplitter,
    QWidget,
    QListWidget,
    QListWidgetItem,
)
from PySide6.QtCore import Qt

from ..resources.styles.dpi_scale import get_font_scale
from .utils import (
    format_authors_short,
    format_date_short,
    create_metadata_label_stylesheet,
    calculate_splitter_sizes,
)
from .constants import (
    FRAME_METADATA_BG,
    SPLITTER_LIST_RATIO,
    SPLITTER_PREVIEW_RATIO,
)

if TYPE_CHECKING:
    from .wizard import SetupWizard

logger = logging.getLogger(__name__)


class DocumentBrowserPage(QWizardPage):
    """
    Page for browsing imported documents to verify import success.

    Displays a list of recently imported documents with title, authors,
    date, and journal. Selecting a document shows its abstract in a
    Markdown-rendered preview panel.
    """

    # Number of documents to display
    DOCUMENTS_PER_PAGE = 20

    def __init__(self, parent: Optional["SetupWizard"] = None):
        """Initialize document browser page."""
        super().__init__(parent)
        self._wizard = parent
        self._documents: List[Dict[str, Any]] = []
        self._current_page = 0
        self._total_documents = 0
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the document browser UI."""
        scale = get_font_scale()

        self.setTitle("Verify Imported Documents")
        self.setSubTitle("Browse recently imported documents to verify the import was successful.")

        layout = QVBoxLayout(self)
        layout.setSpacing(scale["spacing_medium"])

        # Create splitter for list and preview
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel: Document list
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Document count label
        self.count_label = QLabel("Loading documents...")
        left_layout.addWidget(self.count_label)

        # Document list
        self.doc_list = QListWidget()
        self.doc_list.setAlternatingRowColors(True)
        self.doc_list.currentItemChanged.connect(self._on_document_selected)
        left_layout.addWidget(self.doc_list)

        # Pagination controls
        pagination_layout = QHBoxLayout()
        self.prev_btn = QPushButton("← Previous")
        self.prev_btn.clicked.connect(self._prev_page)
        self.prev_btn.setEnabled(False)
        pagination_layout.addWidget(self.prev_btn)

        self.page_label = QLabel("Page 1")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pagination_layout.addWidget(self.page_label)

        self.next_btn = QPushButton("Next →")
        self.next_btn.clicked.connect(self._next_page)
        pagination_layout.addWidget(self.next_btn)

        left_layout.addLayout(pagination_layout)

        splitter.addWidget(left_panel)

        # Right panel: Abstract preview
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Document metadata
        self.metadata_label = QLabel("Select a document to view details")
        self.metadata_label.setWordWrap(True)
        self.metadata_label.setStyleSheet(
            create_metadata_label_stylesheet(scale, FRAME_METADATA_BG)
        )
        right_layout.addWidget(self.metadata_label)

        # Abstract preview (using QTextBrowser for Markdown rendering)
        abstract_label = QLabel("Abstract:")
        right_layout.addWidget(abstract_label)

        self.abstract_browser = QTextBrowser()
        self.abstract_browser.setOpenExternalLinks(True)
        self.abstract_browser.setPlaceholderText("Select a document to view its abstract")
        right_layout.addWidget(self.abstract_browser)

        splitter.addWidget(right_panel)

        # Set initial splitter stretch factors (40% list, 60% preview)
        splitter.setStretchFactor(0, SPLITTER_LIST_RATIO)
        splitter.setStretchFactor(1, SPLITTER_PREVIEW_RATIO)

        layout.addWidget(splitter)

    def initializePage(self) -> None:
        """Initialize the page when it becomes visible."""
        self._current_page = 0
        self._load_documents()

    def _load_documents(self) -> None:
        """Load documents from the database."""
        try:
            from bmlibrarian.database import get_db_manager

            db_manager = get_db_manager()
            offset = self._current_page * self.DOCUMENTS_PER_PAGE

            with db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    # Get total count
                    cur.execute("SELECT COUNT(*) FROM document")
                    self._total_documents = cur.fetchone()[0]

                    # Get documents for current page
                    cur.execute("""
                        SELECT id, title, authors, publication_date, publication, abstract
                        FROM document
                        ORDER BY id DESC
                        LIMIT %s OFFSET %s
                    """, (self.DOCUMENTS_PER_PAGE, offset))

                    self._documents = []
                    for row in cur.fetchall():
                        self._documents.append({
                            'id': row[0],
                            'title': row[1] or 'Untitled',
                            'authors': row[2] or [],
                            'date': row[3],
                            'journal': row[4] or 'Unknown',
                            'abstract': row[5] or 'No abstract available',
                        })

            self._update_document_list()
            self._update_pagination()

        except Exception as e:
            logger.error(f"Error loading documents: {e}")
            self.count_label.setText(f"Error loading documents: {e}")
            self._documents = []

    def _update_document_list(self) -> None:
        """Update the document list widget."""
        self.doc_list.clear()

        if not self._documents:
            self.count_label.setText("No documents found")
            return

        start = self._current_page * self.DOCUMENTS_PER_PAGE + 1
        end = min(start + len(self._documents) - 1, self._total_documents)
        self.count_label.setText(f"Showing {start}-{end} of {self._total_documents} documents")

        for doc in self._documents:
            # Format authors using utility function
            author_str = format_authors_short(doc['authors'])

            # Format date using utility function
            date_str = format_date_short(doc['date'])

            # Create list item text
            title = doc['title'][:80] + '...' if len(doc['title']) > 80 else doc['title']
            item_text = f"{title}\n{author_str} • {date_str} • {doc['journal']}"

            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, doc)
            self.doc_list.addItem(item)

    def _update_pagination(self) -> None:
        """Update pagination controls."""
        total_pages = max(1, (self._total_documents + self.DOCUMENTS_PER_PAGE - 1) // self.DOCUMENTS_PER_PAGE)
        self.page_label.setText(f"Page {self._current_page + 1} of {total_pages}")
        self.prev_btn.setEnabled(self._current_page > 0)
        self.next_btn.setEnabled((self._current_page + 1) * self.DOCUMENTS_PER_PAGE < self._total_documents)

    def _prev_page(self) -> None:
        """Go to previous page."""
        if self._current_page > 0:
            self._current_page -= 1
            self._load_documents()

    def _next_page(self) -> None:
        """Go to next page."""
        if (self._current_page + 1) * self.DOCUMENTS_PER_PAGE < self._total_documents:
            self._current_page += 1
            self._load_documents()

    def _on_document_selected(self, current: QListWidgetItem, previous: QListWidgetItem) -> None:
        """Handle document selection."""
        if current is None:
            return

        doc = current.data(Qt.ItemDataRole.UserRole)
        if not doc:
            return

        # Update metadata display
        authors = doc['authors']
        if isinstance(authors, list):
            author_str = ', '.join(authors) if authors else 'Unknown'
        else:
            author_str = str(authors) if authors else 'Unknown'

        date_str = format_date_short(doc['date'])

        metadata_html = f"""
        <h3>{doc['title']}</h3>
        <p><b>Authors:</b> {author_str}</p>
        <p><b>Journal:</b> {doc['journal']}</p>
        <p><b>Date:</b> {date_str}</p>
        <p><b>ID:</b> {doc['id']}</p>
        """
        self.metadata_label.setText(metadata_html)

        # Update abstract display with Markdown rendering
        abstract_html = self._convert_abstract_to_html(doc['abstract'])
        self.abstract_browser.setHtml(abstract_html)

    def _convert_abstract_to_html(self, abstract: str) -> str:
        """
        Convert Markdown-style formatting in abstract to HTML.

        Args:
            abstract: Abstract text with potential Markdown formatting

        Returns:
            HTML-formatted abstract string
        """
        # Bold: **text** -> <b>text</b>
        abstract_html = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', abstract)
        # Italic: *text* -> <i>text</i>
        abstract_html = re.sub(r'\*([^*]+)\*', r'<i>\1</i>', abstract_html)
        # Superscript: ^text^ -> <sup>text</sup>
        abstract_html = re.sub(r'\^([^^]+)\^', r'<sup>\1</sup>', abstract_html)
        # Subscript: ~text~ -> <sub>text</sub>
        abstract_html = re.sub(r'~([^~]+)~', r'<sub>\1</sub>', abstract_html)
        # Paragraph breaks
        abstract_html = abstract_html.replace('\n\n', '</p><p>')
        return f"<p>{abstract_html}</p>"
