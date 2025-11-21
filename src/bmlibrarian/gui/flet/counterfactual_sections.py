"""
Counterfactual Analysis Section Builders

Contains functions for building individual sections of counterfactual displays.
Each function creates a specific section type.
"""

import flet as ft
from typing import List, Dict, Any
from .ui_builder import truncate_text, create_priority_badge


def create_claims_section(claims: List[str]) -> ft.Container:
    """Create main claims section."""
    claims_items = []

    for i, claim in enumerate(claims, 1):
        claims_items.append(
            ft.Container(
                content=ft.Text(
                    f"{i}. {claim}",
                    size=12,
                    color=ft.Colors.GREY_800
                ),
                padding=ft.padding.symmetric(horizontal=15, vertical=5),
                bgcolor=ft.Colors.BLUE_50,
                border_radius=5,
                margin=ft.margin.only(bottom=4)
            )
        )

    return ft.Container(
        content=ft.Column([
            ft.Text(
                "📋 Hypotheses Being Contested",
                size=16,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.BLUE_700
            ),
            ft.Text(
                "Original Claims from Report:",
                size=13,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.BLUE_800
            ),
            *claims_items
        ], spacing=6),
        padding=ft.padding.all(15),
        bgcolor=ft.Colors.BLUE_50,
        border_radius=8,
        border=ft.border.all(1, ft.Colors.BLUE_200)
    )


def create_question_card(index: int, question: Any, query_map: Dict, query_stats: Dict) -> ft.ExpansionTile:
    """Create a single research question card."""
    priority = getattr(question, 'priority', 'MEDIUM')
    priority_badge = create_priority_badge(priority)

    question_text = getattr(question, 'question', 'Unknown question')
    counterfactual_statement = getattr(question, 'counterfactual_statement', '')

    # Find matching query info for this question
    query_info = query_map.get(counterfactual_statement)

    # Build the content sections
    content_items = [
        ft.Text(
            f"Full Question: {question_text}",
            size=11,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.GREY_800
        ),
        ft.Text(
            f"Counterfactual Statement: {counterfactual_statement}",
            size=10,
            color=ft.Colors.PURPLE_700,
            weight=ft.FontWeight.W_500
        ),
        ft.Text(
            f"Target Claim: {getattr(question, 'target_claim', 'Unknown')}",
            size=10,
            color=ft.Colors.ORANGE_700,
            weight=ft.FontWeight.W_500
        ),
        ft.Text(
            f"Reasoning: {getattr(question, 'reasoning', 'Unknown')}",
            size=10,
            color=ft.Colors.GREY_700
        )
    ]

    # Add database query information if available
    if query_info:
        db_query = query_info.get('db_query', 'N/A')
        stats = query_stats.get(counterfactual_statement, {})
        total_docs = stats.get('total_docs', 0)
        scores = stats.get('scores', [])

        # Calculate scoring statistics
        stats_text = f"Documents found: {total_docs}"
        if scores:
            avg_score = sum(scores) / len(scores)
            min_score = min(scores)
            max_score = max(scores)
            stats_text += f" | Relevance scores: min={min_score:.1f}, avg={avg_score:.1f}, max={max_score:.1f}"

        content_items.append(
            ft.Container(
                content=ft.Column([
                    ft.Text(
                        "📊 Literature Search Results:",
                        size=10,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.BLUE_800
                    ),
                    ft.Container(
                        content=ft.Text(
                            f"PostgreSQL Query: {db_query}",
                            size=9,
                            color=ft.Colors.GREY_700,
                            selectable=True
                        ),
                        padding=ft.padding.all(8),
                        bgcolor=ft.Colors.GREY_100,
                        border_radius=4
                    ),
                    ft.Text(
                        stats_text,
                        size=9,
                        color=ft.Colors.BLUE_700,
                        weight=ft.FontWeight.W_500
                    )
                ], spacing=4),
                margin=ft.margin.only(top=8)
            )
        )

    return ft.ExpansionTile(
        title=ft.Row([
            ft.Text(
                f"{index + 1}. {truncate_text(question_text, 70)}",
                size=12,
                weight=ft.FontWeight.W_500,
                color=ft.Colors.ORANGE_800
            ),
            priority_badge
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        controls=[
            ft.Container(
                content=ft.Column(content_items, spacing=4),
                padding=ft.padding.all(12)
            )
        ]
    )


def build_query_map(research_queries: List[Dict]) -> Dict:
    """Build mapping from counterfactual_statement to query info."""
    query_map = {}
    if research_queries:
        for query_info in research_queries:
            stmt = query_info.get('counterfactual_statement', '')
            query_map[stmt] = query_info
    return query_map


def calculate_query_statistics(contradictory_evidence: List[Dict]) -> Dict:
    """Calculate statistics per query from contradictory evidence."""
    query_stats = {}
    if contradictory_evidence:
        for evidence_item in contradictory_evidence:
            if isinstance(evidence_item, dict) and 'query_info' in evidence_item:
                stmt = evidence_item['query_info'].get('counterfactual_statement', '')
                if stmt not in query_stats:
                    query_stats[stmt] = {
                        'total_docs': 0,
                        'scores': []
                    }
                query_stats[stmt]['total_docs'] += 1
                if 'score' in evidence_item:
                    query_stats[stmt]['scores'].append(evidence_item['score'])
    return query_stats


def create_questions_section(questions: List[Any], research_queries: List[Dict] = None, contradictory_evidence: List[Dict] = None) -> ft.Container:
    """Create research questions section with optional database query information and search statistics."""
    query_map = build_query_map(research_queries or [])
    query_stats = calculate_query_statistics(contradictory_evidence or [])

    question_cards = [
        create_question_card(i, question, query_map, query_stats)
        for i, question in enumerate(questions)
    ]

    return ft.Container(
        content=ft.Column([
            ft.Text(
                f"🔍 Research Questions for Finding Contradictory Evidence ({len(questions)})",
                size=16,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.ORANGE_700
            ),
            ft.Text(
                "These research questions were generated to systematically search for evidence that might contradict the original claims:",
                size=11,
                color=ft.Colors.GREY_600,
                italic=True
            ),
            ft.Container(
                content=ft.Column(question_cards, spacing=8),
                margin=ft.margin.only(top=10)
            )
        ], spacing=8),
        padding=ft.padding.all(15),
        bgcolor=ft.Colors.ORANGE_50,
        border_radius=8,
        border=ft.border.all(1, ft.Colors.ORANGE_200)
    )


def create_assessment_section(analysis: Any) -> ft.Container:
    """Create preliminary assessment section."""
    assessment_items = []

    if hasattr(analysis, 'overall_assessment') and analysis.overall_assessment:
        assessment_items.extend([
            ft.Text(
                "Initial Analysis:",
                size=13,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.GREEN_800
            ),
            ft.Container(
                content=ft.Text(
                    analysis.overall_assessment,
                    size=12,
                    color=ft.Colors.GREY_800
                ),
                padding=ft.padding.all(10),
                bgcolor=ft.Colors.GREEN_50,
                border_radius=5
            )
        ])

    return ft.Container(
        content=ft.Column([
            ft.Text(
                "⚖️ Preliminary Assessment (Before Literature Search)",
                size=16,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.GREEN_700
            ),
            *assessment_items
        ], spacing=8),
        padding=ft.padding.all(15),
        bgcolor=ft.Colors.GREEN_50,
        border_radius=8,
        border=ft.border.all(1, ft.Colors.GREEN_200)
    )


def create_summary_metadata_item(label: str, value: Any, color: str = ft.Colors.PURPLE_700) -> ft.Text:
    """Create a single summary metadata item."""
    return ft.Text(
        f"{label}: {value}",
        size=12,
        weight=ft.FontWeight.W_500,
        color=color,
        selectable=True
    )


def create_summary_section(summary: Dict) -> ft.Container:
    """Create summary section for comprehensive analysis."""
    summary_items = []

    # Handle different summary formats
    if summary.get('claims_analyzed'):
        summary_items.append(create_summary_metadata_item("📋 Claims Analyzed", summary['claims_analyzed']))
    elif summary.get('hypotheses_contested'):
        summary_items.append(create_summary_metadata_item("📋 Hypotheses Contested", summary['hypotheses_contested']))

    if summary.get('questions_generated'):
        summary_items.append(create_summary_metadata_item("🔍 Research Questions Generated", summary['questions_generated']))
    elif summary.get('literature_search_queries'):
        summary_items.append(create_summary_metadata_item("🔍 Literature Search Queries", summary['literature_search_queries']))

    if summary.get('high_priority_questions'):
        summary_items.append(create_summary_metadata_item("⚡ High Priority Questions", summary['high_priority_questions']))

    if summary.get('database_searches'):
        summary_items.append(create_summary_metadata_item("🗄️ Database Searches Performed", summary['database_searches']))

    if summary.get('contradictory_documents_found'):
        summary_items.append(create_summary_metadata_item("📚 Contradictory Documents Found", summary['contradictory_documents_found']))
    elif summary.get('contradictory_studies_found'):
        summary_items.append(create_summary_metadata_item("📚 Contradictory Studies Found", summary['contradictory_studies_found']))

    if summary.get('contradictory_citations_extracted'):
        summary_items.append(create_summary_metadata_item("📝 Contradictory Citations Extracted", summary['contradictory_citations_extracted']))
    elif summary.get('citations_extracted'):
        summary_items.append(create_summary_metadata_item("📝 Citations Extracted", summary['citations_extracted']))

    if summary.get('original_confidence') and summary.get('revised_confidence'):
        summary_items.append(
            ft.Text(
                f"📊 Confidence: {summary['original_confidence']} → {summary['revised_confidence']}",
                size=12,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.DEEP_ORANGE_700
            )
        )

    if summary.get('database_available'):
        availability = "✅ Available" if summary['database_available'] else "❌ Unavailable"
        color = ft.Colors.GREEN_700 if summary['database_available'] else ft.Colors.RED_700
        summary_items.append(create_summary_metadata_item("🗄️ Database Status", availability, color))

    if summary.get('overall_strength'):
        color = ft.Colors.RED_700 if 'Strong' in summary['overall_strength'] else ft.Colors.ORANGE_700
        summary_items.append(
            ft.Text(
                f"⚖️ Overall Strength of Contradictory Evidence: {summary['overall_strength']}",
                size=12,
                weight=ft.FontWeight.BOLD,
                color=color
            )
        )

    return ft.Container(
        content=ft.Column([
            ft.Text(
                "📊 Counterfactual Analysis Summary",
                size=16,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.PURPLE_700
            ),
            *summary_items
        ], spacing=8),
        padding=ft.padding.all(15),
        bgcolor=ft.Colors.PURPLE_50,
        border_radius=8,
        border=ft.border.all(1, ft.Colors.PURPLE_200)
    )
