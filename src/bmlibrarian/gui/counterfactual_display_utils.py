"""
Counterfactual Display Utilities Module

Main orchestrator for counterfactual analysis displays.
Routes to appropriate specialized display functions.
"""

import flet as ft
from typing import List, Dict, Any
from .counterfactual_report import create_formatted_report_display
from .counterfactual_sections import (
    create_claims_section, create_questions_section,
    create_assessment_section, create_summary_section
)
from .counterfactual_evidence import (
    create_contradictory_evidence_section,
    create_contradictory_citations_section
)


def create_basic_analysis_sections(analysis: Any, research_queries: List[Dict] = None, contradictory_evidence: List[Dict] = None) -> List[ft.Control]:
    """Create sections for basic counterfactual analysis."""
    sections = []

    # Main claims section
    if hasattr(analysis, 'main_claims') and analysis.main_claims:
        sections.append(create_claims_section(analysis.main_claims))

    # Research questions section
    if hasattr(analysis, 'counterfactual_questions') and analysis.counterfactual_questions:
        sections.append(create_questions_section(analysis.counterfactual_questions, research_queries, contradictory_evidence))

    # Assessment section
    sections.append(create_assessment_section(analysis))

    return sections


def create_comprehensive_analysis_sections(analysis_dict: Dict) -> List[ft.Control]:
    """Create sections for comprehensive counterfactual analysis."""
    sections = []

    summary = analysis_dict.get('summary', {})
    analysis_obj = analysis_dict.get('analysis')
    contradictory_evidence = analysis_dict.get('contradictory_evidence', [])
    contradictory_citations = analysis_dict.get('contradictory_citations', [])
    research_queries = analysis_dict.get('research_queries', [])

    # Original analysis section (if exists)
    if analysis_obj:
        sections.extend(create_basic_analysis_sections(analysis_obj, research_queries, contradictory_evidence))

    # Summary section
    if summary:
        sections.append(create_summary_section(summary))

    # Contradictory evidence section
    if contradictory_evidence:
        sections.append(create_contradictory_evidence_section(contradictory_evidence))

    # Contradictory citations section
    if contradictory_citations:
        sections.append(create_contradictory_citations_section(contradictory_citations))

    return sections


def extract_clean_evidence_and_citations(corrupted_analysis: Dict) -> tuple[List[Any], List[Any]]:
    """Extract actual evidence and citations from corrupted wrapper structures."""
    contradictory_evidence = corrupted_analysis.get('contradictory_evidence', [])
    contradictory_citations = corrupted_analysis.get('contradictory_citations', [])

    actual_evidence = []
    for evidence_item in contradictory_evidence:
        if isinstance(evidence_item, dict) and 'document' in evidence_item:
            actual_evidence.append(evidence_item['document'])
        else:
            actual_evidence.append(evidence_item)

    actual_citations = []
    for citation_item in contradictory_citations:
        if isinstance(citation_item, dict) and 'citation' in citation_item:
            actual_citations.append(citation_item['citation'])
        else:
            actual_citations.append(citation_item)

    return actual_evidence, actual_citations


def create_debug_info_section(actual_evidence_count: int, actual_citations_count: int) -> ft.Container:
    """Create debug information section for corrupted analysis."""
    return ft.Container(
        content=ft.Column([
            ft.Text(
                "🔧 Debug Information",
                size=14,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.ORANGE_700,
                selectable=True
            ),
            ft.Text(
                "The counterfactual analysis returned a database document record with nested analysis fields.",
                size=11,
                color=ft.Colors.GREY_700,
                selectable=True
            ),
            ft.Text(
                f"✅ Successfully extracted {actual_evidence_count} documents and {actual_citations_count} citations from nested structure.",
                size=10,
                color=ft.Colors.GREEN_600,
                selectable=True
            ),
            ft.Text(
                "Evidence structure: document + score + reasoning + query_info",
                size=10,
                color=ft.Colors.GREY_600,
                selectable=True
            ),
            ft.Text(
                "Citation structure: citation + original_claim + counterfactual_question + scores",
                size=10,
                color=ft.Colors.GREY_600,
                selectable=True
            )
        ], spacing=5),
        padding=ft.padding.all(12),
        bgcolor=ft.Colors.ORANGE_50,
        border_radius=6,
        border=ft.border.all(1, ft.Colors.ORANGE_200)
    )


def create_corrupted_analysis_components(corrupted_analysis: Dict) -> List[ft.Control]:
    """Create components for corrupted analysis (database document mixed with analysis fields)."""
    components = []

    # Extract the actual analysis parts
    summary = corrupted_analysis.get('summary', {})
    actual_evidence, actual_citations = extract_clean_evidence_and_citations(corrupted_analysis)

    # Header explaining the issue
    components.append(
        ft.Text(
            "📚 Counterfactual Analysis Results (Data Structure Issue Detected)",
            size=15,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.DEEP_PURPLE_700,
            selectable=True
        )
    )

    components.append(
        ft.Text(
            f"Found {len(actual_evidence)} contradictory studies and {len(actual_citations)} citations. Note: The analysis result has a data structure issue that's being worked around.",
            size=12,
            color=ft.Colors.GREY_600,
            italic=True,
            selectable=True
        )
    )

    # Create clean analysis structure
    clean_analysis = {
        'summary': summary,
        'contradictory_evidence': actual_evidence,
        'contradictory_citations': actual_citations
    }

    # Use comprehensive analysis display for cleaned data
    components.extend(create_comprehensive_analysis_sections(clean_analysis))

    # Add debug info
    components.append(create_debug_info_section(len(actual_evidence), len(actual_citations)))

    return components


def create_basic_analysis_header(questions_count: int, claims_count: int) -> List[ft.Control]:
    """Create header for basic counterfactual analysis."""
    return [
        ft.Text(
            "📋 Basic Counterfactual Analysis Completed",
            size=15,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.ORANGE_700
        ),
        ft.Text(
            f"Analyzed {claims_count} claims and generated {questions_count} research questions for finding contradictory evidence.",
            size=12,
            color=ft.Colors.GREY_600,
            italic=True
        )
    ]


def create_comprehensive_analysis_header(evidence_count: int, citations_count: int) -> List[ft.Control]:
    """Create header for comprehensive counterfactual analysis."""
    return [
        ft.Text(
            "📚 Comprehensive Counterfactual Analysis with Literature Search Completed",
            size=15,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.PURPLE_700
        ),
        ft.Text(
            f"Found {evidence_count} contradictory studies and extracted {citations_count} citations that challenge the original claims.",
            size=12,
            color=ft.Colors.GREY_600,
            italic=True
        )
    ]


def create_fallback_analysis_components(analysis: Any) -> List[ft.Control]:
    """Create fallback components for unknown analysis format."""
    analysis_str = str(analysis)
    if len(analysis_str) > 500:
        analysis_str = analysis_str[:500] + "..."

    return [
        ft.Text(
            "⚠️ Counterfactual Analysis (Unknown Format)",
            size=15,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.GREY_700
        ),
        ft.Container(
            content=ft.Text(
                f"Raw analysis data:\n{analysis_str}",
                size=11,
                color=ft.Colors.GREY_800
            ),
            padding=ft.padding.all(10),
            bgcolor=ft.Colors.GREY_50,
            border_radius=5
        )
    ]


def create_counterfactual_display(analysis: Any) -> List[ft.Control]:
    """
    Create display components for counterfactual analysis.
    Routes to appropriate display function based on analysis format.
    """
    # Check analysis type and create appropriate display
    if isinstance(analysis, dict):
        # Check for new formatted report structure
        if 'formatted_report' in analysis:
            return create_formatted_report_display(analysis['formatted_report'])

        # Check if this looks like a corrupted database document mixed with analysis
        if 'id' in analysis and 'source_id' in analysis and 'summary' in analysis:
            return create_corrupted_analysis_components(analysis)

        # Clean comprehensive analysis with search results
        if 'summary' in analysis:
            components = []
            evidence_count = len(analysis.get('contradictory_evidence', []))
            citations_count = len(analysis.get('contradictory_citations', []))
            components.extend(create_comprehensive_analysis_header(evidence_count, citations_count))
            components.extend(create_comprehensive_analysis_sections(analysis))
            return components

        # Fallback for unknown dict format
        return create_fallback_analysis_components(analysis)

    elif hasattr(analysis, 'main_claims') or hasattr(analysis, 'counterfactual_questions'):
        # Basic counterfactual analysis object
        components = []
        questions_count = len(getattr(analysis, 'counterfactual_questions', []))
        claims_count = len(getattr(analysis, 'main_claims', []))
        components.extend(create_basic_analysis_header(questions_count, claims_count))
        components.extend(create_basic_analysis_sections(analysis))
        return components

    else:
        # Fallback for unknown format
        return create_fallback_analysis_components(analysis)


class CounterfactualDisplayCreator:
    """Wrapper class for backward compatibility."""

    def create_counterfactual_display(self, analysis: Any) -> List[ft.Control]:
        """Create display components for counterfactual analysis."""
        return create_counterfactual_display(analysis)
