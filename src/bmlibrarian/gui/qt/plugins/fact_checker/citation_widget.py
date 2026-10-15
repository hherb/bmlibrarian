"""
Citation Widget for Fact-Checker Review.

Displays citation cards using the standard CitationCard widget with data conversion.
"""

import logging
from typing import Optional, List, Dict, Any, Tuple
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

logger = logging.getLogger(__name__)

# Placeholder values the fact-checker uses for missing citation fields; a
# field holding one of these is treated as missing and enriched from the DB.
CITATION_PLACEHOLDERS: Dict[str, Tuple[str, ...]] = {
    'abstract': ('No abstract', 'No abstract available'),
    'pmid': ('N/A',),
    'title': ('No title',),
    'authors': ('Unknown', 'Unknown authors'),
    'journal': ('Unknown', 'Unknown journal'),
    'pub_year': ('N/A', 'Unknown'),
}


def _is_missing(citation: Dict[str, Any], field: str) -> bool:
    """Return True if a citation field is empty or holds a placeholder."""
    value = citation.get(field)
    return not value or value in CITATION_PLACEHOLDERS.get(field, ())


def citation_needs_enrichment(citation: Dict[str, Any]) -> bool:
    """Return True if any displayable citation field is missing.

    Args:
        citation: Citation in fact-checker format

    Returns:
        Whether database enrichment would fill something in
    """
    return any(_is_missing(citation, field) for field in CITATION_PLACEHOLDERS)


def merge_document_details(
    citation: Dict[str, Any],
    details: Dict[str, Any]
) -> Dict[str, Any]:
    """Fill a citation's missing fields from document details.

    Fields the citation already has are kept; only missing or placeholder
    values are replaced.

    Args:
        citation: Citation in fact-checker format
        details: Document details as returned by ``get_document_details``

    Returns:
        A new, enriched citation dictionary
    """
    authors_list = details.get('authors_list') or []
    year = details.get('year')
    fills = {
        'abstract': details.get('abstract') or 'No abstract available',
        'pmid': details.get('pmid') or 'N/A',
        'doi': details.get('doi') or '',
        'pdf_url': details.get('pdf_url') or '',
        'pdf_filename': details.get('pdf_filename') or '',
        'title': details.get('title') or 'No title',
        'authors': ', '.join(authors_list) if authors_list else 'Unknown authors',
        'journal': details.get('journal') or 'Unknown journal',
        'pub_year': year if year else 'N/A',
    }
    enriched = citation.copy()
    for field, value in fills.items():
        if _is_missing(enriched, field):
            enriched[field] = value
    return enriched


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

        Document metadata comes from the fact-checker DB backend's
        ``get_document_details`` (the canonical
        ``bmlibrarian.database.get_document_details`` for PostgreSQL, the
        review package for SQLite) — no inline SQL here (golden rule 18).

        Args:
            citation: Citation dictionary
            db: Fact-checker database (AbstractFactCheckerDB) or None

        Returns:
            Enriched citation dictionary (the input unchanged on failure)
        """
        doc_id = citation.get('document_id')
        if not db or doc_id is None or not citation_needs_enrichment(citation):
            return citation

        try:
            details = db.get_document_details(doc_id)
        except Exception as e:
            logger.warning(
                f"Failed to enrich citation for document {doc_id} from database: {e}",
                exc_info=True
            )
            return citation

        if not details:
            logger.debug(f"Document {doc_id} not found while enriching citation")
            return citation
        return merge_document_details(citation, details)

    def clear(self):
        """Clear all citations."""
        self.set_citations([])
