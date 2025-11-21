"""
Counterfactual Formatted Report Display Functions

Contains functions for displaying the new formatted counterfactual report structure.
"""

import flet as ft
from typing import List, Dict, Any


def format_authors_metadata(authors: List[str], max_authors: int = 3) -> str:
    """Format author list with et al. if needed."""
    if not authors:
        return ""
    author_str = ', '.join(authors[:max_authors])
    if len(authors) > max_authors:
        author_str += ' et al.'
    return author_str


def build_citation_metadata(evidence: Dict[str, Any]) -> str:
    """Build citation metadata line from evidence dictionary."""
    metadata_parts = []

    authors = evidence.get('authors', [])
    if authors:
        metadata_parts.append(format_authors_metadata(authors))

    pub_date = evidence.get('publication_date', 'Unknown date')
    if pub_date and pub_date != 'Unknown date':
        metadata_parts.append(f"({pub_date})")

    publication = evidence.get('publication')
    if publication:
        metadata_parts.append(publication)

    pmid = evidence.get('pmid')
    if pmid:
        metadata_parts.append(f"PMID: {pmid}")

    doi = evidence.get('doi')
    if doi:
        metadata_parts.append(f"DOI: {doi}")

    return ' | '.join(metadata_parts) if metadata_parts else 'Metadata unavailable'


def create_evidence_passage_element(passage: str) -> List[ft.Control]:
    """Create passage display elements."""
    if passage and passage != 'No passage extracted':
        return [
            ft.Text(
                "Passage:",
                size=10,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.BLACK87,
                selectable=True
            ),
            ft.Text(
                f'"{passage}"',
                size=11,
                color=ft.Colors.BLACK87,
                italic=True,
                selectable=True
            )
        ]
    return []


def create_evidence_summary_element(summary: str) -> List[ft.Control]:
    """Create summary display elements."""
    if summary and summary != 'No summary available':
        return [
            ft.Text(
                "Summary:",
                size=10,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.GREY_700,
                selectable=True
            ),
            ft.Text(
                summary,
                size=10,
                color=ft.Colors.GREY_700,
                selectable=True
            )
        ]
    return []


def create_evidence_scoring_element(relevance_score: float, document_score: float, score_reasoning: str) -> List[ft.Control]:
    """Create scoring information elements."""
    elements = [
        ft.Row([
            ft.Text(
                f"Relevance: {relevance_score}/5",
                size=10,
                color=ft.Colors.GREY_600,
                selectable=True
            ),
            ft.Text(
                f"Document Score: {document_score}/5",
                size=10,
                color=ft.Colors.GREY_600,
                selectable=True
            )
        ], spacing=20)
    ]

    if score_reasoning:
        elements.append(ft.Text(
            f"Reasoning: {score_reasoning}",
            size=10,
            color=ft.Colors.GREY_700,
            italic=True,
            selectable=True
        ))

    return elements


def create_evidence_container(index: int, evidence: Dict[str, Any]) -> ft.Container:
    """Create a single evidence citation container."""
    title = evidence.get('title', 'Unknown title')
    passage = evidence.get('passage', '')
    summary = evidence.get('summary', '')
    relevance_score = evidence.get('relevance_score', 0)
    document_score = evidence.get('document_score', 0)
    score_reasoning = evidence.get('score_reasoning', '')

    citation_metadata = build_citation_metadata(evidence)

    # Build evidence display elements
    evidence_elements = [
        ft.Text(
            f"Evidence {index}: {title}",
            size=12,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.ORANGE_800,
            selectable=True
        ),
        ft.Text(
            citation_metadata,
            size=10,
            color=ft.Colors.GREY_700,
            italic=True,
            selectable=True
        )
    ]

    # Add passage if available
    evidence_elements.extend(create_evidence_passage_element(passage))

    # Add summary if available
    evidence_elements.extend(create_evidence_summary_element(summary))

    # Add scoring information
    evidence_elements.extend(create_evidence_scoring_element(relevance_score, document_score, score_reasoning))

    return ft.Container(
        content=ft.Column(evidence_elements, spacing=5),
        padding=ft.padding.all(12),
        margin=ft.margin.only(left=20, top=5, bottom=5),
        bgcolor=ft.Colors.ORANGE_50,
        border_radius=6,
        border=ft.border.all(1, ft.Colors.ORANGE_200)
    )


def create_claim_header(claim: str, counterfactual_statement: str, counterfactual_question: str) -> List[ft.Control]:
    """Create header elements for a claim."""
    elements = [
        ft.Text(
            claim,
            size=12,
            color=ft.Colors.BLACK87,
            selectable=True
        ),
        ft.Text(
            "Counterfactual Statement:",
            size=13,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.RED_700,
            selectable=True
        ),
        ft.Text(
            counterfactual_statement if counterfactual_statement else "(No counterfactual statement generated - claim may be too complex or lack specificity)",
            size=12,
            color=ft.Colors.RED_800 if counterfactual_statement else ft.Colors.GREY_600,
            italic=True,
            selectable=True
        ),
    ]

    # Add research question if present
    if counterfactual_question:
        elements.extend([
            ft.Text(
                "Research Question:",
                size=13,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.PURPLE_700,
                selectable=True
            ),
            ft.Text(
                counterfactual_question,
                size=12,
                color=ft.Colors.PURPLE_800,
                italic=True,
                selectable=True
            ),
        ])

    return elements


def create_claim_section(index: int, item: Dict[str, Any]) -> List[ft.Control]:
    """Create display section for a single claim with its counterfactual evidence."""
    claim = item.get('claim', 'Unknown claim')
    counterfactual_statement = item.get('counterfactual_statement', '')
    counterfactual_question = item.get('counterfactual_question', '')
    evidence_list = item.get('counterfactual_evidence', [])

    # Build column contents
    column_contents = [
        ft.Text(
            f"Claim {index}:",
            size=14,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.BLUE_700,
            selectable=True
        )
    ]

    # Add claim header
    column_contents.extend(create_claim_header(claim, counterfactual_statement, counterfactual_question))

    # Add evidence count
    column_contents.append(
        ft.Text(
            f"Counterfactual Evidence ({len(evidence_list)} citations):",
            size=13,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.ORANGE_700,
            selectable=True
        )
    )

    # Claim container
    claim_container = ft.Container(
        content=ft.Column(column_contents, spacing=8),
        padding=ft.padding.all(15),
        bgcolor=ft.Colors.BLUE_GREY_50,
        border_radius=8,
        border=ft.border.all(1, ft.Colors.BLUE_GREY_200)
    )

    # Build complete section
    section_components = [claim_container]

    # Add evidence citations
    for j, evidence in enumerate(evidence_list, 1):
        section_components.append(create_evidence_container(j, evidence))

    return section_components


def create_summary_statement_section(summary_statement: str) -> ft.Container:
    """Create final summary statement section."""
    return ft.Container(
        content=ft.Column([
            ft.Text(
                "📊 Final Summary Statement",
                size=15,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.PURPLE_700,
                selectable=True
            ),
            ft.Text(
                summary_statement,
                size=12,
                color=ft.Colors.BLACK87,
                selectable=True
            )
        ], spacing=8),
        padding=ft.padding.all(15),
        bgcolor=ft.Colors.PURPLE_50,
        border_radius=8,
        border=ft.border.all(2, ft.Colors.PURPLE_300)
    )


def create_formatted_report_header(items_count: int) -> List[ft.Control]:
    """Create header for formatted report display."""
    header = [
        ft.Text(
            "🎯 Counterfactual Evidence Analysis",
            size=18,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.DEEP_PURPLE_700,
            selectable=True
        )
    ]

    if items_count == 0:
        header.append(
            ft.Text(
                "No contradictory evidence found. The original report claims appear to be well-supported by the literature.",
                size=12,
                color=ft.Colors.GREEN_600,
                italic=True,
                selectable=True
            )
        )
    else:
        header.append(
            ft.Text(
                f"Found {items_count} claims with contradictory evidence requiring careful consideration.",
                size=12,
                color=ft.Colors.ORANGE_700,
                italic=True,
                selectable=True
            )
        )

    return header


def create_formatted_report_display(formatted_report: Dict[str, Any]) -> List[ft.Control]:
    """Create display components for the new formatted counterfactual report."""
    components = []

    items = formatted_report.get('items', [])
    summary_statement = formatted_report.get('summary_statement', '')

    # Header
    components.extend(create_formatted_report_header(len(items)))

    # Display each claim with its counterfactual evidence
    for i, item in enumerate(items, 1):
        components.extend(create_claim_section(i, item))

    # Summary section
    if summary_statement:
        components.append(create_summary_statement_section(summary_statement))

    return components
