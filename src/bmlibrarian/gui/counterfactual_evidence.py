"""
Counterfactual Evidence Display Functions

Contains functions for displaying contradictory evidence and citations.
"""

import flet as ft
from typing import List, Dict, Any, Optional
from .ui_builder import truncate_text, extract_year_from_date
from .citation_card_utils import extract_citation_data
from .unified_document_card import UnifiedDocumentCard, DocumentCardContext


def extract_document_data(doc: dict) -> Dict[str, str]:
    """Extract and normalize document data."""
    if isinstance(doc, dict):
        title = doc.get('title') or doc.get('document_title', 'Untitled Document')
        authors = doc.get('authors', 'Unknown authors')
        year = doc.get('year') or doc.get('publication_date', 'Unknown year')
        abstract = doc.get('abstract', 'No abstract available')

        # If authors is a list, join it
        if isinstance(authors, list):
            authors = ', '.join(authors)

        # Extract year from publication date if needed
        if year and year != 'Unknown year' and '-' in str(year):
            year = str(year).split('-')[0]

        return {
            'title': title,
            'authors': authors,
            'year': year,
            'abstract': abstract
        }
    else:
        # Fallback for non-dict items
        return {
            'title': str(doc),
            'authors': 'Unknown authors',
            'year': 'Unknown year',
            'abstract': str(doc)
        }


def create_evidence_card(index: int, doc: dict, page: Optional[ft.Page] = None) -> ft.ExpansionTile:
    """Create a single evidence card using unified document card.

    Args:
        index: Document index (1-based)
        doc: Document dictionary
        page: Flet page instance (optional, enables PDF functionality)

    Returns:
        ExpansionTile widget using unified card design
    """
    # Use page if provided, otherwise create minimal placeholder
    if page is None:
        page = ft.Page()  # Minimal placeholder for backwards compatibility

    # Create unified card creator with PDF manager
    from ..utils.pdf_manager import PDFManager
    pdf_manager = PDFManager()
    card_creator = UnifiedDocumentCard(page, pdf_manager=pdf_manager)

    # Create card with counterfactual context
    return card_creator.create_card(
        index=index - 1,  # Convert from 1-based to 0-based
        doc=doc,
        context=DocumentCardContext.COUNTERFACTUAL
    )


def create_contradictory_evidence_section(evidence: List[dict], page: Optional[ft.Page] = None) -> ft.Container:
    """Create contradictory evidence section.

    Args:
        evidence: List of evidence documents
        page: Flet page instance (optional, enables PDF functionality)

    Returns:
        Container with evidence cards
    """
    evidence_cards = [create_evidence_card(i + 1, doc, page) for i, doc in enumerate(evidence)]

    return ft.Container(
        content=ft.Column([
            ft.Text(
                f"🚫 Contradictory Evidence Found ({len(evidence)} studies)",
                size=16,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.RED_700
            ),
            ft.Text(
                "These studies present evidence that potentially contradicts the original claims:",
                size=11,
                color=ft.Colors.GREY_600,
                italic=True
            ),
            ft.Container(
                content=ft.Column(evidence_cards, spacing=8),
                margin=ft.margin.only(top=10)
            )
        ], spacing=8),
        padding=ft.padding.all(15),
        bgcolor=ft.Colors.RED_50,
        border_radius=8,
        border=ft.border.all(1, ft.Colors.RED_200)
    )


def create_contradictory_citation_card(index: int, citation: Any, page: Optional[ft.Page] = None) -> ft.ExpansionTile:
    """Create a single contradictory citation card using unified card.

    Args:
        index: Citation index (1-based)
        citation: Citation object or dictionary
        page: Flet page instance (optional, enables PDF functionality)

    Returns:
        ExpansionTile widget using unified card design
    """
    # Extract citation data first
    citation_data = extract_citation_data(citation)

    # Use page if provided, otherwise create minimal placeholder
    if page is None:
        page = ft.Page()  # Minimal placeholder for backwards compatibility

    # Create unified card creator with PDF manager
    from ..utils.pdf_manager import PDFManager
    pdf_manager = PDFManager()
    card_creator = UnifiedDocumentCard(page, pdf_manager=pdf_manager)

    # Build document dictionary from citation data
    doc = {
        'id': citation_data.get('document_id', f'cit_{index}'),
        'title': citation_data['title'],
        'authors': citation_data['authors'],
        'publication': citation_data.get('publication', 'Unknown'),
        'publication_date': citation_data.get('publication_date', 'Unknown'),
        'year': citation_data.get('publication_date', 'Unknown'),
        'abstract': citation_data.get('abstract', ''),
        'pmid': citation_data.get('pmid'),
        'doi': citation_data.get('doi'),
        'pdf_path': citation_data.get('pdf_path'),
        'pdf_url': citation_data.get('pdf_url')
    }

    # Build citation-specific data
    cit_data = {
        'summary': citation_data['summary'],
        'passage': citation_data['passage'],
        'relevance_score': citation_data['relevance_score']
    }

    # Create card with citation context
    return card_creator.create_card(
        index=index - 1,  # Convert from 1-based to 0-based
        doc=doc,
        context=DocumentCardContext.CITATIONS,
        citation_data=cit_data,
        relevance_score=citation_data['relevance_score']
    )


def create_contradictory_citations_section(citations: List[Any], page: Optional[ft.Page] = None) -> ft.Container:
    """Create contradictory citations section.

    Args:
        citations: List of citation objects
        page: Flet page instance (optional, enables PDF functionality)

    Returns:
        Container with citation cards
    """
    citation_cards = [create_contradictory_citation_card(i + 1, citation, page) for i, citation in enumerate(citations)]

    return ft.Container(
        content=ft.Column([
            ft.Text(
                f"📖 Contradictory Citations ({len(citations)} extracts)",
                size=16,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.DEEP_ORANGE_700
            ),
            ft.Text(
                "Key passages extracted from contradictory studies that challenge the original findings:",
                size=11,
                color=ft.Colors.GREY_600,
                italic=True
            ),
            ft.Container(
                content=ft.Column(citation_cards, spacing=8),
                margin=ft.margin.only(top=10)
            )
        ], spacing=8),
        padding=ft.padding.all(15),
        bgcolor=ft.Colors.DEEP_ORANGE_50,
        border_radius=8,
        border=ft.border.all(1, ft.Colors.DEEP_ORANGE_200)
    )
