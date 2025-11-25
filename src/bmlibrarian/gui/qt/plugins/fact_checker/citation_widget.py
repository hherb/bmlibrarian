"""
Citation Widget for Fact-Checker Review.

Displays citation cards using the standard CitationCard widget with data conversion.
"""

from typing import Optional, List, Dict, Any
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt
from pathlib import Path
import os

# Import document card factory
from ...qt_document_card_factory import QtDocumentCardFactory
from bmlibrarian.gui.document_card_factory_base import DocumentCardData

# Import PDF manager
from bmlibrarian.utils.pdf_manager import PDFManager

# Import DPI-aware styling
from ...resources.styles import get_font_scale


class CitationListWidget(QWidget):
    """Widget for displaying a list of citations using standard CitationCard widgets."""

    def __init__(self, parent: Optional[QWidget] = None, pdf_base_dir: Optional[Path] = None):
        """
        Initialize citation list widget.

        Args:
            parent: Optional parent widget
            pdf_base_dir: Base directory for PDF files (defaults to PDF_BASE_DIR env var)
        """
        super().__init__(parent)

        # DPI-aware scaling
        self.scale = get_font_scale()

        # Get PDF base directory from parameter or environment
        if pdf_base_dir is None:
            pdf_dir_str = os.getenv('PDF_BASE_DIR', '~/knowledgebase/pdf')
            pdf_base_dir = Path(pdf_dir_str).expanduser()

        # Initialize PDF manager for handling PDF downloads and storage
        self.pdf_manager = PDFManager(base_dir=str(pdf_base_dir))

        # Initialize document card factory with PDF manager and base directory
        self.card_factory = QtDocumentCardFactory(
            pdf_manager=self.pdf_manager,
            base_pdf_dir=pdf_base_dir
        )

        self._setup_ui()

    def _setup_ui(self):
        """Setup the user interface."""
        s = self.scale

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(s['spacing_medium'])

        # Empty state message (initially shown)
        self.empty_label = QLabel("No citations available")
        self.empty_label.setAlignment(Qt.AlignCenter)
        # Using scale values for font and padding
        self.empty_label.setStyleSheet(
            f"color: #999; font-style: italic; "
            f"font-size: {s['font_normal']}pt; "
            f"padding: {s['padding_xlarge']}px;"
        )
        self.layout.addWidget(self.empty_label)

    def set_citations(self, citations: List[Dict[str, Any]], db=None):
        """
        Set the list of citations to display.

        Args:
            citations: List of citation dictionaries (fact-checker format)
            db: Optional database connection for enriching citation data
        """
        s = self.scale

        # Clear existing citations
        while self.layout.count() > 0:
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add new citations
        if not citations:
            # Re-create empty label
            self.empty_label = QLabel("No citations available")
            self.empty_label.setAlignment(Qt.AlignCenter)
            self.empty_label.setStyleSheet(
                f"color: #999; font-style: italic; "
                f"font-size: {s['font_normal']}pt; "
                f"padding: {s['padding_xlarge']}px;"
            )
            self.layout.addWidget(self.empty_label)
        else:
            # Create citation cards using document card factory
            for index, citation in enumerate(citations, start=1):
                # Enrich citation with database data if needed
                enriched_citation = self._enrich_citation(citation, db)

                # Convert to DocumentCardData format
                card_data = self._convert_to_card_data(enriched_citation)

                # Create and add card using factory
                card = self.card_factory.create_card(card_data)
                self.layout.addWidget(card)

            # Add stretch at the end
            self.layout.addStretch()

    def _convert_to_card_data(self, citation: Dict[str, Any]) -> DocumentCardData:
        """
        Convert fact-checker citation format to DocumentCardData.

        Fact-checker format:
            - title, authors, journal, pub_year, pmid, doi
            - abstract, passage (citation_text)
            - document_id

        Args:
            citation: Citation in fact-checker format

        Returns:
            DocumentCardData instance
        """
        # Parse authors
        authors = citation.get('authors', 'Unknown authors')
        if isinstance(authors, str):
            authors_list = [a.strip() for a in authors.split(',')]
        else:
            authors_list = authors if isinstance(authors, list) else []

        # Get year
        pub_year = citation.get('pub_year')
        year = None
        if pub_year and pub_year not in ('Unknown', 'N/A', None):
            try:
                if isinstance(pub_year, (int, float)):
                    year = int(pub_year)
                else:
                    # Try to extract year from string (first 4 digits)
                    year_str = str(pub_year)[:4]
                    if year_str.isdigit():
                        year = int(year_str)
            except (ValueError, TypeError):
                year = None

        # Get PDF path if available
        doc_id = citation.get('document_id')
        pdf_path = None
        if doc_id and self.card_factory.base_pdf_dir:
            # Check if database has pdf_filename (e.g., "2023/paper.pdf")
            pdf_filename = citation.get('pdf_filename')
            if pdf_filename:
                # Use the pdf_filename from database
                potential_path = self.card_factory.base_pdf_dir / pdf_filename
                if potential_path.exists():
                    pdf_path = potential_path
            else:
                # Fallback: try direct doc_id.pdf in base dir (old style)
                potential_path = self.card_factory.base_pdf_dir / f"{doc_id}.pdf"
                if potential_path.exists():
                    pdf_path = potential_path

        # Get PDF URL for download capability
        pdf_url = citation.get('pdf_url', '')

        return DocumentCardData(
            doc_id=doc_id,
            title=citation.get('title', 'Untitled'),
            authors=authors_list,
            journal=citation.get('journal', 'Unknown journal'),
            year=year,
            abstract=citation.get('abstract', 'No abstract available'),
            pmid=citation.get('pmid', ''),
            doi=citation.get('doi', ''),
            pdf_path=pdf_path,
            pdf_url=pdf_url,
            pdf_filename=citation.get('pdf_filename'),  # Relative path from database (e.g., "2022/paper.pdf")
            show_pdf_button=True  # Show PDF button if available
        )

    def _enrich_citation(self, citation: Dict[str, Any], db) -> Dict[str, Any]:
        """
        Enrich citation with data from database if fields are missing.

        Args:
            citation: Citation dictionary
            db: Database connection

        Returns:
            Enriched citation dictionary
        """
        # If no database or document_id, return as-is
        if not db or 'document_id' not in citation:
            return citation

        # Check if we need to enrich (missing any important fields)
        needs_enrichment = (
            not citation.get('abstract') or
            citation.get('abstract') in ('No abstract', 'No abstract available', None) or
            not citation.get('pmid') or
            citation.get('pmid') in ('N/A', None) or
            not citation.get('title') or
            citation.get('title') in ('No title', None) or
            not citation.get('authors') or
            citation.get('authors') in ('Unknown', 'Unknown authors', None) or
            not citation.get('journal') or
            citation.get('journal') in ('Unknown', 'Unknown journal', None) or
            not citation.get('pub_year') or
            citation.get('pub_year') in ('N/A', None, 'Unknown')
        )

        if not needs_enrichment:
            return citation

        try:
            # Determine if we're using PostgreSQL or SQLite
            is_sqlite = hasattr(db, 'conn') and hasattr(db.conn, 'cursor')

            if is_sqlite:
                # SQLite: Query from the local documents table
                cursor = db.conn.cursor()
                cursor.execute("""
                    SELECT
                        id, title, abstract, authors,
                        publication, publication_date, external_id, doi, pdf_url, pdf_filename
                    FROM documents
                    WHERE id = ?
                """, (citation.get('document_id'),))
                row = cursor.fetchone()
            else:
                # PostgreSQL: Query from the main document table
                from bmlibrarian.database import get_db_manager
                db_manager = get_db_manager()

                with db_manager.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            SELECT
                                d.id, d.title, d.abstract, d.authors,
                                d.publication, d.publication_date, d.external_id, d.doi, d.pdf_url, d.pdf_filename
                            FROM document d
                            WHERE d.id = %s
                        """, (citation.get('document_id'),))
                        row = cur.fetchone()

            if row:
                # Handle both SQLite (dict-like) and PostgreSQL (tuple) rows
                if is_sqlite:
                    # SQLite returns dict-like rows
                    doc_id = row['id']
                    title = row['title']
                    abstract = row['abstract']
                    authors_data = row['authors']
                    publication = row['publication']
                    pub_date = row['publication_date']
                    external_id = row['external_id']
                    doi = row['doi']
                    pdf_url = row['pdf_url']
                    pdf_filename = row['pdf_filename']

                    # Parse JSON authors if it's a string
                    import json
                    if authors_data and isinstance(authors_data, str):
                        try:
                            authors_list = json.loads(authors_data)
                            authors = ', '.join(authors_list) if isinstance(authors_list, list) else authors_data
                        except json.JSONDecodeError:
                            authors = authors_data
                    else:
                        authors = authors_data
                else:
                    # PostgreSQL returns tuple rows
                    doc_id = row[0]
                    title = row[1]
                    abstract = row[2]
                    authors_data = row[3]
                    publication = row[4]
                    pub_date = row[5]
                    external_id = row[6]
                    doi = row[7]
                    pdf_url = row[8]
                    pdf_filename = row[9]

                    # Convert array to string if needed
                    if isinstance(authors_data, list):
                        authors = ', '.join(authors_data) if authors_data else 'Unknown authors'
                    else:
                        authors = authors_data or 'Unknown authors'

                # Update missing fields
                enriched = citation.copy()
                if not enriched.get('abstract') or enriched.get('abstract') in ('No abstract', None):
                    enriched['abstract'] = abstract or 'No abstract available'
                if not enriched.get('pmid') or enriched.get('pmid') in ('N/A', None):
                    enriched['pmid'] = external_id or 'N/A'
                if not enriched.get('doi') or enriched.get('doi') is None:
                    enriched['doi'] = doi or ''
                if not enriched.get('pdf_url') or enriched.get('pdf_url') is None:
                    enriched['pdf_url'] = pdf_url or ''
                if not enriched.get('pdf_filename') or enriched.get('pdf_filename') is None:
                    enriched['pdf_filename'] = pdf_filename or ''
                if not enriched.get('title') or enriched.get('title') in ('No title', None):
                    enriched['title'] = title or 'No title'
                if not enriched.get('authors') or enriched.get('authors') in ('Unknown', None):
                    enriched['authors'] = authors or 'Unknown authors'
                if not enriched.get('journal') or enriched.get('journal') in ('Unknown', None):
                    enriched['journal'] = publication or 'Unknown journal'
                if not enriched.get('pub_year') or enriched.get('pub_year') in ('N/A', None):
                    # Extract year from publication_date
                    if pub_date:
                        # Handle both datetime objects and ISO date strings
                        if hasattr(pub_date, 'year'):
                            enriched['pub_year'] = pub_date.year
                        else:
                            enriched['pub_year'] = str(pub_date)[:4]
                    else:
                        enriched['pub_year'] = 'N/A'

                return enriched

        except Exception as e:
            print(f"Warning: Failed to enrich citation from database: {e}")
            import traceback
            traceback.print_exc()

        return citation

    def clear(self):
        """Clear all citations."""
        self.set_citations([])
