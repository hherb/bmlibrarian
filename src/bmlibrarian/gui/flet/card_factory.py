"""Card Factory - Simplified Interface for Unified Document Cards

Provides a simple factory interface for creating document cards across all contexts.
This module acts as a bridge between existing code and the new unified card system.
"""

import flet as ft
from typing import Dict, List, Any, Optional, Callable
from .unified_document_card import UnifiedDocumentCard, DocumentCardContext


class CardFactory:
    """Factory for creating unified document cards with simplified interface."""

    def __init__(self, page: ft.Page, pdf_manager=None):
        """Initialize card factory.

        Args:
            page: Flet page instance
            pdf_manager: Optional PDFManager instance
        """
        self.page = page
        self.card_creator = UnifiedDocumentCard(page, pdf_manager=pdf_manager)

    # Literature/Search Results Cards

    def create_search_results_cards(self, documents: List[Dict]) -> List[ft.Control]:
        """Create cards for search results / literature tab.

        Args:
            documents: List of document dictionaries

        Returns:
            List of ExpansionTile widgets
        """
        return [
            self.card_creator.create_card(
                index=i,
                doc=doc,
                context=DocumentCardContext.LITERATURE
            )
            for i, doc in enumerate(documents)
        ]

    # Scoring Cards

    def create_scoring_cards(
        self,
        scored_documents: List[tuple],
        show_controls: bool = False,
        on_score_change: Optional[Callable] = None,
        on_score_approve: Optional[Callable] = None
    ) -> List[ft.Control]:
        """Create cards for document scoring tab.

        Args:
            scored_documents: List of (doc, scoring_result) tuples
                             scoring_result should have 'score' and 'reasoning'
            show_controls: Whether to show human override controls
            on_score_change: Callback for score changes (index, score, type)
            on_score_approve: Callback for approving AI scores (index)

        Returns:
            List of ExpansionTile widgets
        """
        cards = []
        for i, (doc, scoring_result) in enumerate(scored_documents):
            score = scoring_result.get('score', 0) if isinstance(scoring_result, dict) else scoring_result
            reasoning = scoring_result.get('reasoning', 'No reasoning provided') if isinstance(scoring_result, dict) else None

            card = self.card_creator.create_card(
                index=i,
                doc=doc,
                context=DocumentCardContext.SCORING,
                ai_score=score,
                scoring_reasoning=reasoning,
                show_scoring_controls=show_controls,
                on_score_change=on_score_change,
                on_score_approve=on_score_approve
            )
            cards.append(card)

        return cards

    def create_scored_cards_with_overrides(
        self,
        documents: List[Dict],
        ai_scores: List[float],
        human_scores: List[Optional[float]],
        reasoning: List[str]
    ) -> List[ft.Control]:
        """Create cards showing both AI and human scores.

        Args:
            documents: List of document dicts
            ai_scores: List of AI scores (same length as documents)
            human_scores: List of human scores (None if not overridden)
            reasoning: List of AI reasoning strings

        Returns:
            List of ExpansionTile widgets
        """
        cards = []
        for i, doc in enumerate(documents):
            ai_score = ai_scores[i] if i < len(ai_scores) else None
            human_score = human_scores[i] if i < len(human_scores) else None
            reason = reasoning[i] if i < len(reasoning) else None

            card = self.card_creator.create_card(
                index=i,
                doc=doc,
                context=DocumentCardContext.SCORING,
                ai_score=ai_score,
                human_score=human_score,
                scoring_reasoning=reason,
                show_scoring_controls=False
            )
            cards.append(card)

        return cards

    # Citation Cards

    def create_citation_cards(self, citations: List[Any]) -> List[ft.Control]:
        """Create cards for citations tab.

        Args:
            citations: List of citation objects or dicts with:
                      - document_title / title
                      - summary / citation_summary
                      - passage / text
                      - relevance_score
                      - authors, publication_date, etc.

        Returns:
            List of ExpansionTile widgets
        """
        cards = []
        for i, citation in enumerate(citations):
            # Extract citation data
            if hasattr(citation, '__dict__'):
                # Citation object
                doc = {
                    'id': getattr(citation, 'document_id', f'cit_{i}'),
                    'title': getattr(citation, 'document_title', 'Unknown'),
                    'authors': getattr(citation, 'authors', []),
                    'publication': getattr(citation, 'publication', 'Unknown'),
                    'publication_date': getattr(citation, 'publication_date', 'Unknown'),
                    'year': getattr(citation, 'year', 'Unknown'),
                    'abstract': getattr(citation, 'abstract', ''),
                    'pmid': getattr(citation, 'pmid', None),
                    'doi': getattr(citation, 'doi', None),
                    'pdf_path': getattr(citation, 'pdf_path', None),
                    'pdf_url': getattr(citation, 'pdf_url', None),
                }
                citation_data = {
                    'summary': getattr(citation, 'summary', ''),
                    'passage': getattr(citation, 'passage', ''),
                    'relevance_score': getattr(citation, 'relevance_score', 0)
                }
            else:
                # Dictionary
                doc = {
                    'id': citation.get('document_id', f'cit_{i}'),
                    'title': citation.get('document_title') or citation.get('title', 'Unknown'),
                    'authors': citation.get('authors', []),
                    'publication': citation.get('publication', 'Unknown'),
                    'publication_date': citation.get('publication_date', 'Unknown'),
                    'year': citation.get('year', 'Unknown'),
                    'abstract': citation.get('abstract', ''),
                    'pmid': citation.get('pmid'),
                    'doi': citation.get('doi'),
                    'pdf_path': citation.get('pdf_path'),
                    'pdf_url': citation.get('pdf_url'),
                }
                citation_data = {
                    'summary': citation.get('summary') or citation.get('citation_summary', ''),
                    'passage': citation.get('passage') or citation.get('text', ''),
                    'relevance_score': citation.get('relevance_score', 0)
                }

            card = self.card_creator.create_card(
                index=i,
                doc=doc,
                context=DocumentCardContext.CITATIONS,
                citation_data=citation_data,
                relevance_score=citation_data['relevance_score']
            )
            cards.append(card)

        return cards

    # Counterfactual Cards

    def create_counterfactual_cards(
        self,
        documents: List[Dict],
        scores: Optional[List[float]] = None
    ) -> List[ft.Control]:
        """Create cards for counterfactual evidence tab.

        Args:
            documents: List of document dictionaries
            scores: Optional list of relevance scores

        Returns:
            List of ExpansionTile widgets
        """
        cards = []
        for i, doc in enumerate(documents):
            score = scores[i] if scores and i < len(scores) else None

            card = self.card_creator.create_card(
                index=i,
                doc=doc,
                context=DocumentCardContext.COUNTERFACTUAL,
                ai_score=score
            )
            cards.append(card)

        return cards

    # Single Card Creation (for dynamic updates)

    def create_single_document_card(
        self,
        index: int,
        doc: Dict,
        context: str = DocumentCardContext.LITERATURE,
        **kwargs
    ) -> ft.ExpansionTile:
        """Create a single document card with custom parameters.

        Args:
            index: Document index
            doc: Document dictionary
            context: Context type (use DocumentCardContext constants)
            **kwargs: Additional parameters passed to card creator

        Returns:
            ExpansionTile widget
        """
        return self.card_creator.create_card(
            index=index,
            doc=doc,
            context=context,
            **kwargs
        )


# Standalone convenience functions for backward compatibility

def create_document_cards_for_tab(
    page: ft.Page,
    documents: List[Dict],
    tab_type: str,
    **kwargs
) -> List[ft.Control]:
    """Create document cards for a specific tab type.

    Args:
        page: Flet page instance
        documents: List of document dictionaries
        tab_type: Tab type ('literature', 'scoring', 'citations', 'counterfactual')
        **kwargs: Additional parameters (scores, citations, etc.)

    Returns:
        List of card widgets
    """
    # Always instantiate PDF manager for full functionality
    from ..utils.pdf_manager import PDFManager
    pdf_manager = PDFManager()
    factory = CardFactory(page, pdf_manager=pdf_manager)

    if tab_type == 'literature':
        return factory.create_search_results_cards(documents)

    elif tab_type == 'scoring':
        scored_docs = kwargs.get('scored_documents')
        if scored_docs:
            return factory.create_scoring_cards(
                scored_docs,
                show_controls=kwargs.get('show_controls', False),
                on_score_change=kwargs.get('on_score_change'),
                on_score_approve=kwargs.get('on_score_approve')
            )
        else:
            # Fallback: create basic cards
            return factory.create_search_results_cards(documents)

    elif tab_type == 'citations':
        citations = kwargs.get('citations', [])
        return factory.create_citation_cards(citations)

    elif tab_type == 'counterfactual':
        scores = kwargs.get('scores')
        return factory.create_counterfactual_cards(documents, scores)

    else:
        # Default: literature-style cards
        return factory.create_search_results_cards(documents)
