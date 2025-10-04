"""
Document Card Utilities Module

Contains reusable functions for creating document display cards.
Each function has a single, focused purpose.
"""

import flet as ft
from typing import List, Dict, Optional
from .ui_builder import (
    create_score_badge, create_expandable_card,
    create_metadata_section, create_text_content_section,
    truncate_text, extract_year_from_date
)


def get_document_year(doc: dict) -> str:
    """Extract year from document data."""
    publication_date = doc.get('publication_date', None)
    if publication_date and str(publication_date).strip() and str(publication_date) != 'Unknown':
        return extract_year_from_date(str(publication_date).strip())
    return doc.get('year', 'Unknown year')


def create_document_subtitle(publication: Optional[str], year: str, show_score: bool, scoring_result: Optional[dict]) -> str:
    """Create document subtitle text."""
    pub_info_parts = []
    if publication and publication.strip():
        pub_info_parts.append(publication.strip())
    if year and year != 'Unknown year':
        pub_info_parts.append(str(year))

    subtitle_text = ' • '.join(pub_info_parts) if pub_info_parts else 'Unknown publication'

    if show_score and scoring_result:
        reasoning = scoring_result.get('reasoning', 'No reasoning provided')[:50] + "..."
        subtitle_text += f" | {reasoning}"

    return subtitle_text


def get_score_color(score: float) -> str:
    """Get color based on score value."""
    if score >= 4.5:
        return ft.Colors.GREEN_700
    elif score >= 3.5:
        return ft.Colors.BLUE_700
    elif score >= 2.5:
        return ft.Colors.ORANGE_700
    else:
        return ft.Colors.RED_700


def create_document_title_section(title: str) -> ft.Container:
    """Create title section for document card."""
    return ft.Container(
        content=ft.Text(
            f"Title: {title}",
            size=11,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.BLUE_900
        ),
        padding=ft.padding.only(bottom=8)
    )


def create_document_authors_section(authors: str) -> ft.Container:
    """Create authors section for document card."""
    return ft.Container(
        content=ft.Text(
            f"Authors: {authors}",
            size=10,
            color=ft.Colors.GREY_700
        ),
        padding=ft.padding.only(bottom=8)
    )


def create_document_metadata(doc: dict) -> List[tuple]:
    """Create metadata items list for document."""
    metadata_items = [
        ("Publication", doc.get('publication', 'Unknown')),
        ("Year", get_document_year(doc)),
    ]

    if doc.get('pmid'):
        metadata_items.append(("PMID", doc.get('pmid')))
    if doc.get('doi'):
        metadata_items.append(("DOI", doc.get('doi')))

    return metadata_items


def create_scoring_section(scoring_result: dict) -> ft.Container:
    """Create scoring information section."""
    score = scoring_result.get('score', 0)
    reasoning = scoring_result.get('reasoning', 'No reasoning provided')

    return ft.Container(
        content=ft.Column([
            ft.Text(
                f"AI Score: {score:.1f}/5.0",
                size=11,
                weight=ft.FontWeight.BOLD,
                color=get_score_color(score)
            ),
            ft.Text(
                f"Reasoning: {reasoning}",
                size=10,
                color=ft.Colors.GREY_700
            )
        ], spacing=4),
        padding=ft.padding.only(bottom=8),
        bgcolor=ft.Colors.BLUE_50,
        border_radius=5
    )


def create_document_content_sections(doc: dict, show_score: bool, scoring_result: Optional[dict]) -> List[ft.Control]:
    """Create all content sections for document card."""
    sections = []

    # Full title
    title = doc.get('title', 'Untitled Document')
    sections.append(create_document_title_section(title))

    # Authors
    authors = doc.get('authors', 'Unknown authors')
    sections.append(create_document_authors_section(authors))

    # Metadata
    metadata_items = create_document_metadata(doc)
    sections.append(create_metadata_section(metadata_items))

    # Scoring details (if available)
    if show_score and scoring_result:
        sections.append(create_scoring_section(scoring_result))

    # Abstract
    abstract = doc.get('abstract', 'No abstract available')
    sections.append(create_text_content_section("Abstract:", abstract))

    return sections


def create_document_card(index: int, doc: dict, show_score: bool = False, scoring_result: Optional[dict] = None) -> ft.ExpansionTile:
    """Create an expandable card for a document."""
    title = doc.get('title', 'Untitled Document')
    publication = doc.get('publication', None)
    year = get_document_year(doc)

    # Create title and badges
    display_title = truncate_text(title, 80)
    title_text = f"{index + 1}. {display_title}"

    badges = []
    if show_score and scoring_result:
        score = scoring_result.get('score', 0)
        badges.append(create_score_badge(score))

    # Create subtitle
    subtitle_text = create_document_subtitle(publication, year, show_score, scoring_result)

    # Create content sections
    content_sections = create_document_content_sections(doc, show_score, scoring_result)

    return create_expandable_card(title_text, subtitle_text, content_sections, badges)


def create_document_cards_list(documents: List[dict], show_score: bool = False) -> List[ft.Control]:
    """Create a list of document cards."""
    return [create_document_card(i, doc, show_score=show_score) for i, doc in enumerate(documents)]


def create_scored_document_cards_list(scored_documents: List[tuple]) -> List[ft.Control]:
    """Create a list of scored document cards."""
    return [
        create_document_card(i, doc, show_score=True, scoring_result=scoring_result)
        for i, (doc, scoring_result) in enumerate(scored_documents)
    ]


class DocumentCardCreator:
    """Wrapper class for backward compatibility."""

    def create_document_cards_list(self, documents: List[dict], show_score: bool = False) -> List[ft.Control]:
        """Create a list of document cards."""
        return create_document_cards_list(documents, show_score)

    def create_scored_document_cards_list(self, scored_documents: List[tuple]) -> List[ft.Control]:
        """Create a list of scored document cards."""
        return create_scored_document_cards_list(scored_documents)

    def create_document_card(self, index: int, doc: dict, show_score: bool = False, scoring_result: Optional[dict] = None) -> ft.ExpansionTile:
        """Create an expandable card for a document."""
        return create_document_card(index, doc, show_score, scoring_result)
