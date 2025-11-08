"""
Counterfactual Progressive Display Module

Creates progressive audit trail sections for the counterfactual workflow.
Displays claims, questions, searches, results, scoring, and citations as they happen.
"""

import flet as ft
from typing import List, Dict, Any, Optional
from .unified_document_card import UnifiedDocumentCard, DocumentCardContext


def extract_citation_data_from_object(citation: Any) -> Dict[str, Any]:
    """Extract citation data from citation object or dictionary.

    Args:
        citation: Citation object or dictionary

    Returns:
        Dictionary with standardized citation data
    """
    if hasattr(citation, '__dict__'):
        # Citation object
        return {
            'document_id': getattr(citation, 'document_id', 'Unknown'),
            'title': getattr(citation, 'document_title', 'Unknown Document'),
            'summary': getattr(citation, 'summary', ''),
            'passage': getattr(citation, 'passage', ''),
            'abstract': getattr(citation, 'abstract', ''),
            'authors': getattr(citation, 'authors', []),
            'publication': getattr(citation, 'publication', 'Unknown'),
            'publication_date': getattr(citation, 'publication_date', 'Unknown'),
            'year': getattr(citation, 'year', 'Unknown'),
            'relevance_score': getattr(citation, 'relevance_score', 0),
            'pmid': getattr(citation, 'pmid', None),
            'doi': getattr(citation, 'doi', None),
            'pdf_path': getattr(citation, 'pdf_path', None),
            'pdf_url': getattr(citation, 'pdf_url', None)
        }
    elif isinstance(citation, dict):
        # Dictionary
        return {
            'document_id': citation.get('document_id', 'Unknown'),
            'title': citation.get('document_title') or citation.get('title', 'Unknown Document'),
            'summary': citation.get('summary', ''),
            'passage': citation.get('passage', ''),
            'abstract': citation.get('abstract', ''),
            'authors': citation.get('authors', []),
            'publication': citation.get('publication', 'Unknown'),
            'publication_date': citation.get('publication_date', 'Unknown'),
            'year': citation.get('year', 'Unknown'),
            'relevance_score': citation.get('relevance_score', 0),
            'pmid': citation.get('pmid'),
            'doi': citation.get('doi'),
            'pdf_path': citation.get('pdf_path'),
            'pdf_url': citation.get('pdf_url')
        }
    else:
        # Fallback
        return {
            'document_id': 'Unknown',
            'title': str(citation),
            'summary': '',
            'passage': str(citation)[:200],
            'abstract': '',
            'authors': [],
            'publication': 'Unknown',
            'publication_date': 'Unknown',
            'year': 'Unknown',
            'relevance_score': 0,
            'pmid': None,
            'doi': None,
            'pdf_path': None,
            'pdf_url': None
        }


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


def create_document_card(doc: Dict[str, Any], score: float, reasoning: str, index: int, page: ft.Page = None) -> ft.Control:
    """Create a unified document card for search results.

    Args:
        doc: Document dictionary
        score: Relevance score (1-5 scale)
        reasoning: AI scoring reasoning
        index: Document index (1-based for display)
        page: Flet page instance (optional, for PDF functionality)

    Returns:
        ExpansionTile widget using unified card design
    """
    # Use page if provided, otherwise create a minimal placeholder
    # This allows PDF functionality when page is available
    if page is None:
        # Create a minimal page placeholder for backwards compatibility
        # Note: PDF features won't work without a real page
        import warnings
        warnings.warn("Creating counterfactual document card without page - PDF features will not be available")
        page = ft.Page()  # Minimal placeholder

    # Create unified card creator with PDF manager
    from ..utils.pdf_manager import PDFManager
    pdf_manager = PDFManager()
    card_creator = UnifiedDocumentCard(page, pdf_manager=pdf_manager)

    # Create card with counterfactual context
    # Note: index is 1-based from the loop, but create_card expects 0-based
    return card_creator.create_card(
        index=index - 1,  # Convert to 0-based index
        doc=doc,
        context=DocumentCardContext.COUNTERFACTUAL,
        ai_score=score,
        scoring_reasoning=reasoning
    )


def create_results_display(contradictory_evidence: List[Dict[str, Any]], page: ft.Page = None) -> ft.Container:
    """Create display for search results with scoring.

    Args:
        contradictory_evidence: List of evidence dictionaries with document, score, reasoning
        page: Flet page instance (optional, enables PDF functionality in cards)

    Returns:
        Container with search results section
    """
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

        # Show ALL documents (not just top 10) using unified cards
        for i, evidence in enumerate(sorted_evidence, 1):
            doc = evidence.get('document', {})
            score = evidence.get('score', 0)
            reasoning = evidence.get('reasoning', '')

            controls.append(create_document_card(doc, score, reasoning, i, page))

    return create_section_container(
        "📊 Search Results & Scoring",
        ft.Icons.ANALYTICS,
        ft.Colors.ORANGE_700,
        controls
    )


def create_citations_display(contradictory_citations: List[Dict[str, Any]],
                            rejected_citations: List[Dict[str, Any]] = None,
                            no_citation_extracted: List[Dict[str, Any]] = None,
                            page: ft.Page = None) -> ft.Container:
    """Create display for citation extraction results using unified citation cards.

    Args:
        contradictory_citations: List of validated citation dictionaries
        rejected_citations: List of rejected citation dictionaries (optional)
        no_citation_extracted: List of documents with no citations (optional)
        page: Flet page instance (optional, enables PDF functionality)

    Returns:
        Container with citation sections
    """
    controls = []

    # Use page if provided, otherwise create minimal placeholder
    if page is None:
        page = ft.Page()  # Minimal placeholder for backwards compatibility

    # Create unified card creator with PDF manager
    from ..utils.pdf_manager import PDFManager
    pdf_manager = PDFManager()
    card_creator = UnifiedDocumentCard(page, pdf_manager=pdf_manager)

    # Validated citations - use unified citation cards
    if contradictory_citations:
        controls.append(
            ft.Text(
                f"✅ {len(contradictory_citations)} Validated Citations",
                size=12,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.GREEN_700
            )
        )
        controls.append(ft.Container(height=8))

        # Show ALL validated citations (not just top 5) using unified cards
        for i, cit_info in enumerate(contradictory_citations, 1):
            citation = cit_info.get('citation')
            if citation:
                # Extract citation data
                citation_data = extract_citation_data_from_object(citation)

                # Build document dictionary
                doc = {
                    'id': citation_data.get('document_id', f'cit_{i}'),
                    'title': citation_data['title'],
                    'authors': citation_data.get('authors', []),
                    'publication': citation_data.get('publication', 'Unknown'),
                    'publication_date': citation_data.get('publication_date', 'Unknown'),
                    'year': citation_data.get('year', 'Unknown'),
                    'abstract': citation_data.get('abstract', ''),
                    'pmid': citation_data.get('pmid'),
                    'doi': citation_data.get('doi'),
                    'pdf_path': citation_data.get('pdf_path'),
                    'pdf_url': citation_data.get('pdf_url')
                }

                # Build citation-specific data
                cit_data = {
                    'summary': citation_data.get('summary', ''),
                    'passage': citation_data.get('passage', ''),
                    'relevance_score': citation_data.get('relevance_score', 0)
                }

                # Create unified citation card
                citation_card = card_creator.create_card(
                    index=i - 1,  # 0-based index
                    doc=doc,
                    context=DocumentCardContext.CITATIONS,
                    citation_data=cit_data,
                    relevance_score=cit_data['relevance_score']
                )
                controls.append(citation_card)

    # Rejected citations - show full details for audit trail
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
        controls.append(ft.Container(height=8))

        # Show ALL rejected citations with full details using unified cards
        for i, rejected_info in enumerate(rejected_citations, 1):
            citation = rejected_info.get('citation')
            if citation:
                # Extract citation data
                citation_data = extract_citation_data_from_object(citation)

                # Build document dictionary
                doc = {
                    'id': citation_data.get('document_id', f'rejected_{i}'),
                    'title': citation_data['title'],
                    'authors': citation_data.get('authors', []),
                    'publication': citation_data.get('publication', 'Unknown'),
                    'publication_date': citation_data.get('publication_date', 'Unknown'),
                    'year': citation_data.get('year', 'Unknown'),
                    'abstract': citation_data.get('abstract', ''),
                    'pmid': citation_data.get('pmid'),
                    'doi': citation_data.get('doi'),
                    'pdf_path': citation_data.get('pdf_path'),
                    'pdf_url': citation_data.get('pdf_url')
                }

                # Build citation-specific data including rejection reasoning
                cit_data = {
                    'summary': citation_data.get('summary', ''),
                    'passage': citation_data.get('passage', ''),
                    'relevance_score': citation_data.get('relevance_score', 0),
                    'rejection_reasoning': rejected_info.get('rejection_reasoning', 'No reason provided'),
                    'original_claim': rejected_info.get('original_claim', ''),
                    'counterfactual_statement': rejected_info.get('counterfactual_statement', ''),
                    'document_score': rejected_info.get('document_score', 0),
                    'score_reasoning': rejected_info.get('score_reasoning', '')
                }

                # Create unified citation card with rejection context
                rejected_card = card_creator.create_card(
                    index=i - 1,  # 0-based index
                    doc=doc,
                    context=DocumentCardContext.CITATIONS,
                    citation_data=cit_data,
                    relevance_score=cit_data['relevance_score']
                )

                # Wrap card in a container with orange/warning styling to indicate rejection
                styled_card = ft.Container(
                    content=rejected_card,
                    border=ft.border.all(2, ft.Colors.ORANGE_300),
                    border_radius=8,
                    bgcolor=ft.Colors.with_opacity(0.02, ft.Colors.ORANGE_700)
                )
                controls.append(styled_card)

    # No citation extracted - summary only
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
