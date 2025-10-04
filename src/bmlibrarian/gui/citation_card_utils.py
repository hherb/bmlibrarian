"""
Citation Card Utilities Module

Contains reusable functions for creating citation display cards.
Each function has a single, focused purpose.
"""

import flet as ft
from typing import List, Dict, Any, Optional
from .ui_builder import (
    create_relevance_badge, create_expandable_card,
    create_metadata_section, create_text_content_section,
    truncate_text, extract_year_from_date, format_authors_list
)


def extract_citation_data(citation: Any) -> Dict[str, Any]:
    """Extract data from citation object or dictionary."""
    if hasattr(citation, 'document_title'):
        # Citation object
        return {
            'title': citation.document_title,
            'summary': citation.summary,
            'passage': citation.passage,
            'authors': getattr(citation, 'authors', []),
            'publication_date': getattr(citation, 'publication_date', 'Unknown'),
            'publication': getattr(citation, 'publication', None),
            'relevance_score': getattr(citation, 'relevance_score', 0),
            'document_id': getattr(citation, 'document_id', 'Unknown'),
            'pmid': getattr(citation, 'pmid', None),
            'doi': getattr(citation, 'doi', None)
        }
    elif isinstance(citation, dict):
        # Dictionary - handle multiple possible field names
        title = (citation.get('document_title') or
                citation.get('title') or
                'Untitled Document')

        summary = (citation.get('summary') or
                  citation.get('citation_summary') or
                  'No summary available')

        passage = (citation.get('passage') or
                  citation.get('text') or
                  citation.get('content') or
                  'No passage available')

        authors = citation.get('authors', [])
        if isinstance(authors, str):
            authors = [authors] if authors else []

        return {
            'title': title,
            'summary': summary,
            'passage': passage,
            'authors': authors,
            'publication_date': citation.get('publication_date', 'Unknown'),
            'publication': citation.get('publication', None),
            'relevance_score': citation.get('relevance_score', 0),
            'document_id': citation.get('document_id', 'Unknown'),
            'pmid': citation.get('pmid', None),
            'doi': citation.get('doi', None)
        }
    else:
        # Fallback
        citation_str = str(citation)
        return {
            'title': 'Unknown Citation',
            'summary': citation_str[:200] + "..." if len(citation_str) > 200 else citation_str,
            'passage': citation_str[:200] + "..." if len(citation_str) > 200 else citation_str,
            'authors': [],
            'publication_date': 'Unknown',
            'publication': None,
            'relevance_score': 0,
            'document_id': 'Unknown',
            'pmid': None,
            'doi': None
        }


def create_citation_publication_info(citation_data: Dict[str, Any]) -> str:
    """Create publication info string for citation."""
    pub_info_parts = []

    if citation_data['publication'] and citation_data['publication'].strip():
        pub_info_parts.append(citation_data['publication'].strip())

    year_only = extract_year_from_date(str(citation_data['publication_date']))
    if year_only != 'Unknown':
        pub_info_parts.append(year_only)

    return ' • '.join(pub_info_parts) if pub_info_parts else 'Unknown publication'


def create_citation_title_section(title: str) -> ft.Container:
    """Create title section for citation card."""
    return ft.Container(
        content=ft.Text(
            f"Title: {title}",
            size=11,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.BLUE_900
        ),
        padding=ft.padding.only(bottom=8)
    )


def create_citation_authors_section(authors: List[str]) -> ft.Container:
    """Create authors section for citation card."""
    authors_str = ', '.join(authors) if authors else 'Unknown'
    return ft.Container(
        content=ft.Text(
            f"Authors: {authors_str}",
            size=10,
            color=ft.Colors.GREY_700
        ),
        padding=ft.padding.only(bottom=8)
    )


def create_citation_metadata(citation_data: Dict[str, Any]) -> List[tuple]:
    """Create metadata items list for citation."""
    year_display = extract_year_from_date(str(citation_data['publication_date']))
    metadata_items = [
        ("Relevance Score", f"{citation_data['relevance_score']:.3f}"),
        ("Publication", citation_data['publication'] if citation_data['publication'] else 'Unknown'),
        ("Year", year_display if citation_data['publication_date'] and citation_data['publication_date'] != 'Unknown' else 'Unknown'),
        ("Document ID", citation_data['document_id'])
    ]

    if citation_data['pmid']:
        metadata_items.append(("PMID", citation_data['pmid']))
    if citation_data['doi']:
        metadata_items.append(("DOI", citation_data['doi']))

    return metadata_items


def create_citation_content_sections(citation_data: Dict[str, Any]) -> List[ft.Control]:
    """Create content sections for citation card."""
    sections = []

    # Full title
    sections.append(create_citation_title_section(citation_data['title']))

    # Authors
    sections.append(create_citation_authors_section(citation_data['authors']))

    # Citation metadata
    metadata_items = create_citation_metadata(citation_data)
    sections.append(create_metadata_section(metadata_items, ft.Colors.BLUE_50))

    # Summary
    sections.append(create_text_content_section(
        "Summary:",
        citation_data['summary'],
        ft.Colors.GREEN_50
    ))

    # Passage
    sections.append(create_text_content_section(
        "Extracted Passage:",
        citation_data['passage'],
        ft.Colors.GREY_100,
        italic=True
    ))

    return sections


def create_citation_card(index: int, citation: Any) -> ft.ExpansionTile:
    """Create an expandable card for a citation."""
    # Extract citation data
    citation_data = extract_citation_data(citation)

    # Create title and badges
    display_title = truncate_text(citation_data['title'], 80)
    title_text = f"{index + 1}. {display_title}"

    badges = [create_relevance_badge(citation_data['relevance_score'])]

    # Create subtitle
    authors_str = format_authors_list(citation_data['authors'])
    pub_info = create_citation_publication_info(citation_data)
    subtitle_text = f"{authors_str} | {pub_info}"

    # Create content sections
    content_sections = create_citation_content_sections(citation_data)

    return create_expandable_card(title_text, subtitle_text, content_sections, badges)


def create_citation_cards_list(citations: List[Any]) -> List[ft.Control]:
    """Create a list of citation cards."""
    return [create_citation_card(i, citation) for i, citation in enumerate(citations)]


class CitationCardCreator:
    """Wrapper class for backward compatibility."""

    def create_citation_cards_list(self, citations: List[Any]) -> List[ft.Control]:
        """Create a list of citation cards."""
        return create_citation_cards_list(citations)

    def create_citation_card(self, index: int, citation: Any) -> ft.ExpansionTile:
        """Create an expandable card for a citation."""
        return create_citation_card(index, citation)

    def _extract_citation_data(self, citation: Any) -> Dict[str, Any]:
        """Extract data from citation object or dictionary."""
        return extract_citation_data(citation)
