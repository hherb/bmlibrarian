"""
Counterfactual Evidence Display Functions

Contains functions for displaying contradictory evidence and citations.
"""

import flet as ft
from typing import List, Dict, Any
from .ui_builder import truncate_text, extract_year_from_date
from .citation_card_utils import extract_citation_data


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


def create_evidence_card(index: int, doc: dict) -> ft.ExpansionTile:
    """Create a single evidence card."""
    doc_data = extract_document_data(doc)

    return ft.ExpansionTile(
        title=ft.Text(
            f"{index}. {truncate_text(doc_data['title'], 80)}",
            size=12,
            weight=ft.FontWeight.W_500,
            color=ft.Colors.RED_800
        ),
        subtitle=ft.Text(
            f"{doc_data['authors']} • {doc_data['year']}",
            size=10,
            color=ft.Colors.GREY_600
        ),
        controls=[
            ft.Container(
                content=ft.Column([
                    ft.Text(
                        f"Title: {doc_data['title']}",
                        size=11,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.RED_900
                    ),
                    ft.Text(
                        f"Authors: {doc_data['authors']}",
                        size=10,
                        color=ft.Colors.GREY_700
                    ),
                    ft.Text(
                        f"Abstract: {doc_data['abstract']}",
                        size=10,
                        color=ft.Colors.GREY_700
                    )
                ], spacing=4),
                padding=ft.padding.all(12)
            )
        ]
    )


def create_contradictory_evidence_section(evidence: List[dict]) -> ft.Container:
    """Create contradictory evidence section."""
    evidence_cards = [create_evidence_card(i + 1, doc) for i, doc in enumerate(evidence)]

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


def create_contradictory_citation_card(index: int, citation: Any) -> ft.ExpansionTile:
    """Create a single contradictory citation card."""
    citation_data = extract_citation_data(citation)

    return ft.ExpansionTile(
        title=ft.Text(
            f"{index}. {truncate_text(citation_data['title'], 80)}",
            size=12,
            weight=ft.FontWeight.W_500,
            color=ft.Colors.DEEP_ORANGE_800
        ),
        subtitle=ft.Text(
            f"Relevance: {citation_data['relevance_score']:.3f}",
            size=10,
            color=ft.Colors.GREY_600
        ),
        controls=[
            ft.Container(
                content=ft.Column([
                    ft.Text(
                        f"Summary: {citation_data['summary']}",
                        size=11,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.DEEP_ORANGE_900
                    ),
                    ft.Text(
                        f"Extracted Passage: {citation_data['passage']}",
                        size=10,
                        color=ft.Colors.GREY_700,
                        italic=True
                    )
                ], spacing=4),
                padding=ft.padding.all(12)
            )
        ]
    )


def create_contradictory_citations_section(citations: List[Any]) -> ft.Container:
    """Create contradictory citations section."""
    citation_cards = [create_contradictory_citation_card(i + 1, citation) for i, citation in enumerate(citations)]

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
