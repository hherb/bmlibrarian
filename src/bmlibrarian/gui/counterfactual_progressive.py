"""
Counterfactual Progressive Display Module

Creates progressive audit trail sections for the counterfactual workflow.
Displays claims, questions, searches, results, scoring, and citations as they happen.
"""

import flet as ft
from typing import List, Dict, Any, Optional


def create_section_container(title: str, icon: str, color: str, controls: List[ft.Control]) -> ft.Container:
    """Create a styled section container for audit trail."""
    return ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Icon(icon, size=18, color=color),
                ft.Text(
                    title,
                    size=14,
                    weight=ft.FontWeight.BOLD,
                    color=color
                )
            ], spacing=8),
            ft.Container(height=8),
            *controls
        ], spacing=6),
        padding=ft.padding.all(12),
        bgcolor=ft.Colors.with_opacity(0.05, color),
        border_radius=8,
        border=ft.border.all(1, ft.Colors.with_opacity(0.2, color))
    )


def create_claims_display(claims: List[Any]) -> ft.Container:
    """Create display for identified claims."""
    controls = []

    for i, claim in enumerate(claims, 1):
        claim_text = claim.claim if hasattr(claim, 'claim') else str(claim)
        confidence = claim.confidence_level if hasattr(claim, 'confidence_level') else "Unknown"

        controls.append(
            ft.Container(
                content=ft.Column([
                    ft.Text(
                        f"{i}. {claim_text}",
                        size=12,
                        weight=ft.FontWeight.W_500,
                        selectable=True
                    ),
                    ft.Text(
                        f"Confidence: {confidence}",
                        size=10,
                        color=ft.Colors.GREY_600,
                        italic=True,
                        selectable=True
                    )
                ], spacing=4),
                padding=ft.padding.only(left=8, top=4, bottom=4)
            )
        )

    return create_section_container(
        "📋 Identified Claims",
        ft.Icons.FACT_CHECK,
        ft.Colors.BLUE_700,
        controls
    )


def create_questions_display(questions: List[Any]) -> ft.Container:
    """Create display for generated research questions."""
    controls = []

    for i, question in enumerate(questions, 1):
        q_text = question.question if hasattr(question, 'question') else str(question)
        priority = question.priority if hasattr(question, 'priority') else "Unknown"
        target_claim = question.target_claim if hasattr(question, 'target_claim') else ""

        priority_color = {
            "HIGH": ft.Colors.RED_600,
            "MEDIUM": ft.Colors.ORANGE_600,
            "LOW": ft.Colors.GREY_600
        }.get(priority, ft.Colors.GREY_600)

        controls.append(
            ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Container(
                            content=ft.Text(
                                priority,
                                size=9,
                                weight=ft.FontWeight.BOLD,
                                color=ft.Colors.WHITE
                            ),
                            padding=ft.padding.symmetric(horizontal=6, vertical=2),
                            bgcolor=priority_color,
                            border_radius=3
                        ),
                        ft.Text(
                            q_text,
                            size=11,
                            weight=ft.FontWeight.W_500,
                            selectable=True,
                            expand=True
                        )
                    ], spacing=8),
                    ft.Text(
                        f"Target: {target_claim[:100]}..." if len(target_claim) > 100 else f"Target: {target_claim}",
                        size=9,
                        color=ft.Colors.GREY_600,
                        italic=True,
                        selectable=True
                    ) if target_claim else ft.Container()
                ], spacing=4),
                padding=ft.padding.only(left=8, top=4, bottom=4)
            )
        )

    return create_section_container(
        "❓ Counterfactual Research Questions",
        ft.Icons.PSYCHOLOGY,
        ft.Colors.PURPLE_700,
        controls
    )


def create_searches_display(research_queries: List[Dict[str, Any]]) -> ft.Container:
    """Create display for database search queries."""
    controls = []

    for i, query_info in enumerate(research_queries, 1):
        question = query_info.get('question', 'No question')
        db_query = query_info.get('db_query', query_info.get('query', 'No query'))
        claim = query_info.get('target_claim', '')

        controls.append(
            ft.Container(
                content=ft.Column([
                    ft.Text(
                        f"Search #{i}",
                        size=11,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.GREEN_700
                    ),
                    ft.Text(
                        f"Question: {question}",
                        size=10,
                        selectable=True
                    ),
                    ft.Container(
                        content=ft.Text(
                            db_query,
                            size=9,
                            font_family="monospace",
                            color=ft.Colors.GREY_700,
                            selectable=True
                        ),
                        padding=ft.padding.all(8),
                        bgcolor=ft.Colors.GREY_100,
                        border_radius=4
                    ),
                    ft.Text(
                        f"Targeting claim: {claim[:80]}..." if len(claim) > 80 else f"Targeting claim: {claim}",
                        size=9,
                        color=ft.Colors.GREY_600,
                        italic=True,
                        selectable=True
                    ) if claim else ft.Container()
                ], spacing=4),
                padding=ft.padding.only(left=8, top=6, bottom=6),
                border=ft.border.only(left=ft.BorderSide(2, ft.Colors.GREEN_200))
            )
        )

    return create_section_container(
        "🔍 Database Searches",
        ft.Icons.SEARCH,
        ft.Colors.GREEN_700,
        controls
    )


def create_document_card(doc: Dict[str, Any], score: float, reasoning: str, index: int) -> ft.Container:
    """Create a document card for search results."""
    title = doc.get('title', 'No title')
    authors = doc.get('authors', [])
    year = doc.get('publication_year', 'Unknown')

    # Color-code by score
    score_color = ft.Colors.RED_600 if score >= 4 else ft.Colors.ORANGE_600 if score >= 3 else ft.Colors.GREY_600

    return ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Container(
                    content=ft.Text(
                        f"{score}/5",
                        size=12,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.WHITE
                    ),
                    padding=ft.padding.all(6),
                    bgcolor=score_color,
                    border_radius=4
                ),
                ft.Column([
                    ft.Text(
                        f"{index}. {title}",
                        size=11,
                        weight=ft.FontWeight.W_500,
                        selectable=True
                    ),
                    ft.Text(
                        f"{', '.join(authors[:3])} ({year})",
                        size=9,
                        color=ft.Colors.GREY_600,
                        selectable=True
                    )
                ], spacing=2, expand=True)
            ], spacing=10),
            ft.Text(
                f"Reasoning: {reasoning}",
                size=9,
                color=ft.Colors.GREY_700,
                italic=True,
                selectable=True
            ) if reasoning else ft.Container()
        ], spacing=6),
        padding=ft.padding.all(10),
        bgcolor=ft.Colors.WHITE,
        border_radius=6,
        border=ft.border.all(1, ft.Colors.GREY_300)
    )


def create_results_display(contradictory_evidence: List[Dict[str, Any]]) -> ft.Container:
    """Create display for search results with scoring."""
    controls = []

    if not contradictory_evidence:
        controls.append(
            ft.Text(
                "No contradictory documents found",
                size=11,
                color=ft.Colors.GREY_600,
                italic=True
            )
        )
    else:
        # Sort by score
        sorted_evidence = sorted(contradictory_evidence, key=lambda x: x.get('score', 0), reverse=True)

        controls.append(
            ft.Text(
                f"Found {len(contradictory_evidence)} documents above relevance threshold",
                size=11,
                weight=ft.FontWeight.W_500,
                color=ft.Colors.ORANGE_700
            )
        )
        controls.append(ft.Container(height=8))

        for i, evidence in enumerate(sorted_evidence[:10], 1):  # Show top 10
            doc = evidence.get('document', {})
            score = evidence.get('score', 0)
            reasoning = evidence.get('reasoning', '')

            controls.append(create_document_card(doc, score, reasoning, i))

    return create_section_container(
        "📊 Search Results & Scoring",
        ft.Icons.ANALYTICS,
        ft.Colors.ORANGE_700,
        controls
    )


def create_citations_display(contradictory_citations: List[Dict[str, Any]],
                            rejected_citations: List[Dict[str, Any]] = None,
                            no_citation_extracted: List[Dict[str, Any]] = None) -> ft.Container:
    """Create display for citation extraction results."""
    controls = []

    # Validated citations
    if contradictory_citations:
        controls.append(
            ft.Text(
                f"✅ {len(contradictory_citations)} Validated Citations",
                size=12,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.GREEN_700
            )
        )

        for i, cit_info in enumerate(contradictory_citations[:5], 1):  # Show top 5
            citation = cit_info.get('citation')
            if citation:
                doc_title = citation.document_title if hasattr(citation, 'document_title') else 'Unknown'
                passage = citation.passage if hasattr(citation, 'passage') else ''

                controls.append(
                    ft.Container(
                        content=ft.Column([
                            ft.Text(
                                f"{i}. {doc_title}",
                                size=10,
                                weight=ft.FontWeight.W_500,
                                selectable=True
                            ),
                            ft.Container(
                                content=ft.Text(
                                    f'"{passage[:150]}..."' if len(passage) > 150 else f'"{passage}"',
                                    size=9,
                                    italic=True,
                                    color=ft.Colors.GREY_700,
                                    selectable=True
                                ),
                                padding=ft.padding.only(left=12, top=4)
                            )
                        ], spacing=4),
                        padding=ft.padding.all(8),
                        bgcolor=ft.Colors.GREEN_50,
                        border_radius=4,
                        border=ft.border.all(1, ft.Colors.GREEN_200)
                    )
                )

    # Rejected citations
    if rejected_citations:
        controls.append(ft.Container(height=12))
        controls.append(
            ft.Text(
                f"⚠️  {len(rejected_citations)} Rejected Citations",
                size=12,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.ORANGE_700
            )
        )
        controls.append(
            ft.Text(
                "These citations were extracted but failed validation (don't support the counterfactual claim)",
                size=9,
                color=ft.Colors.GREY_600,
                italic=True
            )
        )

    # No citation extracted
    if no_citation_extracted:
        controls.append(ft.Container(height=12))
        controls.append(
            ft.Text(
                f"📭 {len(no_citation_extracted)} Documents - No Citation Extracted",
                size=12,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.GREY_600
            )
        )
        controls.append(
            ft.Text(
                "No relevant passages could be extracted from these documents",
                size=9,
                color=ft.Colors.GREY_600,
                italic=True
            )
        )

    if not controls:
        controls.append(
            ft.Text(
                "No citations extracted yet",
                size=11,
                color=ft.Colors.GREY_600,
                italic=True
            )
        )

    return create_section_container(
        "📝 Citation Extraction",
        ft.Icons.FORMAT_QUOTE,
        ft.Colors.TEAL_700,
        controls
    )


def create_summary_display(summary: Dict[str, Any]) -> ft.Container:
    """Create summary display for final counterfactual analysis."""
    controls = []

    stats = [
        ("Claims Analyzed", summary.get('claims_analyzed', 0)),
        ("Questions Generated", summary.get('questions_generated', 0)),
        ("High Priority Questions", summary.get('high_priority_questions', 0)),
        ("Database Searches", summary.get('database_searches', 0)),
        ("Documents Found", summary.get('contradictory_documents_found', 0)),
        ("Citations Extracted", summary.get('contradictory_citations_extracted', 0))
    ]

    for label, value in stats:
        controls.append(
            ft.Row([
                ft.Text(
                    f"{label}:",
                    size=11,
                    weight=ft.FontWeight.W_500,
                    color=ft.Colors.GREY_700
                ),
                ft.Text(
                    str(value),
                    size=11,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.BLUE_700
                )
            ], spacing=8)
        )

    # Confidence assessment
    original_confidence = summary.get('original_confidence', 'Unknown')
    revised_confidence = summary.get('revised_confidence', original_confidence)

    if original_confidence != revised_confidence:
        controls.append(ft.Container(height=8))
        controls.append(
            ft.Container(
                content=ft.Column([
                    ft.Text(
                        "Confidence Assessment",
                        size=12,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.AMBER_700
                    ),
                    ft.Text(
                        f"Original: {original_confidence} → Revised: {revised_confidence}",
                        size=11,
                        color=ft.Colors.GREY_700
                    ),
                    ft.Text(
                        "Contradictory evidence found - consider revising confidence level",
                        size=10,
                        color=ft.Colors.ORANGE_600,
                        italic=True
                    )
                ], spacing=4),
                padding=ft.padding.all(10),
                bgcolor=ft.Colors.AMBER_50,
                border_radius=4,
                border=ft.border.all(1, ft.Colors.AMBER_200)
            )
        )

    return create_section_container(
        "📈 Summary",
        ft.Icons.SUMMARIZE,
        ft.Colors.INDIGO_700,
        controls
    )
