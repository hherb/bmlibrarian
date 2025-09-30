"""
Display Utilities Module for Research GUI

Contains helper classes and functions for creating complex display components.
"""

import flet as ft
from typing import List, Any, Dict, Optional
from .ui_builder import (
    create_score_badge, create_relevance_badge, create_priority_badge,
    create_metadata_section, create_text_content_section, create_expandable_card,
    truncate_text, extract_year_from_date, format_authors_list
)


class DocumentCardCreator:
    """Creates document display cards."""
    
    def create_document_cards_list(self, documents: List[dict], show_score: bool = False) -> List[ft.Control]:
        """Create a list of document cards."""
        doc_cards = []
        
        for i, doc in enumerate(documents):
            doc_card = self.create_document_card(i, doc, show_score=show_score)
            doc_cards.append(doc_card)
        
        return doc_cards
    
    def create_scored_document_cards_list(self, scored_documents: List[tuple]) -> List[ft.Control]:
        """Create a list of scored document cards."""
        doc_cards = []
        
        for i, (doc, scoring_result) in enumerate(scored_documents):
            doc_card = self.create_document_card(i, doc, show_score=True, scoring_result=scoring_result)
            doc_cards.append(doc_card)
        
        return doc_cards
    
    def create_document_card(self, index: int, doc: dict, show_score: bool = False, scoring_result: Optional[dict] = None) -> ft.ExpansionTile:
        """Create an expandable card for a document."""
        title = doc.get('title', 'Untitled Document')
        authors = doc.get('authors', 'Unknown authors')
        publication = doc.get('publication', None)
        year = self._get_document_year(doc)
        
        # Create title and badges
        display_title = truncate_text(title, 80)
        title_text = f"{index + 1}. {display_title}"
        
        badges = []
        if show_score and scoring_result:
            score = scoring_result.get('score', 0)
            badges.append(create_score_badge(score))
        
        # Create subtitle
        subtitle_text = self._create_document_subtitle(publication, year, show_score, scoring_result)
        
        # Create content sections
        content_sections = self._create_document_content_sections(doc, show_score, scoring_result)
        
        return create_expandable_card(title_text, subtitle_text, content_sections, badges)
    
    def _get_document_year(self, doc: dict) -> str:
        """Extract year from document data."""
        publication_date = doc.get('publication_date', None)
        if publication_date and str(publication_date).strip() and str(publication_date) != 'Unknown':
            return extract_year_from_date(str(publication_date).strip())
        return doc.get('year', 'Unknown year')
    
    def _create_document_subtitle(self, publication: Optional[str], year: str, show_score: bool, scoring_result: Optional[dict]) -> str:
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
    
    def _create_document_content_sections(self, doc: dict, show_score: bool, scoring_result: Optional[dict]) -> List[ft.Control]:
        """Create content sections for document card."""
        sections = []
        
        # Full title
        title = doc.get('title', 'Untitled Document')
        sections.append(
            ft.Container(
                content=ft.Text(
                    f"Title: {title}",
                    size=11,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.BLUE_900
                ),
                padding=ft.padding.only(bottom=8)
            )
        )
        
        # Authors
        authors = doc.get('authors', 'Unknown authors')
        sections.append(
            ft.Container(
                content=ft.Text(
                    f"Authors: {authors}",
                    size=10,
                    color=ft.Colors.GREY_700
                ),
                padding=ft.padding.only(bottom=8)
            )
        )
        
        # Metadata
        metadata_items = [
            ("Publication", doc.get('publication', 'Unknown')),
            ("Year", self._get_document_year(doc)),
        ]
        
        if doc.get('pmid'):
            metadata_items.append(("PMID", doc.get('pmid')))
        if doc.get('doi'):
            metadata_items.append(("DOI", doc.get('doi')))
        
        sections.append(create_metadata_section(metadata_items))
        
        # Scoring details (if available)
        if show_score and scoring_result:
            sections.append(self._create_scoring_section(scoring_result))
        
        # Abstract
        abstract = doc.get('abstract', 'No abstract available')
        sections.append(create_text_content_section("Abstract:", abstract))
        
        return sections
    
    def _create_scoring_section(self, scoring_result: dict) -> ft.Container:
        """Create scoring information section."""
        score = scoring_result.get('score', 0)
        reasoning = scoring_result.get('reasoning', 'No reasoning provided')
        
        return ft.Container(
            content=ft.Column([
                ft.Text(
                    f"AI Score: {score:.1f}/5.0",
                    size=11,
                    weight=ft.FontWeight.BOLD,
                    color=self._get_score_color(score)
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
    
    def _get_score_color(self, score: float) -> str:
        """Get color based on score value."""
        if score >= 4.5:
            return ft.Colors.GREEN_700
        elif score >= 3.5:
            return ft.Colors.BLUE_700
        elif score >= 2.5:
            return ft.Colors.ORANGE_700
        else:
            return ft.Colors.RED_700


class CitationCardCreator:
    """Creates citation display cards."""
    
    def create_citation_cards_list(self, citations: List[Any]) -> List[ft.Control]:
        """Create a list of citation cards."""
        citation_cards = []
        
        for i, citation in enumerate(citations):
            citation_card = self.create_citation_card(i, citation)
            citation_cards.append(citation_card)
        
        return citation_cards
    
    def create_citation_card(self, index: int, citation: Any) -> ft.ExpansionTile:
        """Create an expandable card for a citation."""
        # Extract citation data
        citation_data = self._extract_citation_data(citation)
        
        # Create title and badges
        display_title = truncate_text(citation_data['title'], 80)
        title_text = f"{index + 1}. {display_title}"
        
        badges = [create_relevance_badge(citation_data['relevance_score'])]
        
        # Create subtitle
        authors_str = format_authors_list(citation_data['authors'])
        pub_info = self._create_citation_publication_info(citation_data)
        subtitle_text = f"{authors_str} | {pub_info}"
        
        # Create content sections
        content_sections = self._create_citation_content_sections(citation_data)
        
        return create_expandable_card(title_text, subtitle_text, content_sections, badges)
    
    def _extract_citation_data(self, citation: Any) -> Dict[str, Any]:
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
            # Dictionary
            return {
                'title': citation.get('document_title', 'Untitled Document'),
                'summary': citation.get('summary', 'No summary available'),
                'passage': citation.get('passage', 'No passage available'),
                'authors': citation.get('authors', []),
                'publication_date': citation.get('publication_date', 'Unknown'),
                'publication': citation.get('publication', None),
                'relevance_score': citation.get('relevance_score', 0),
                'document_id': citation.get('document_id', 'Unknown'),
                'pmid': citation.get('pmid', None),
                'doi': citation.get('doi', None)
            }
        else:
            # Fallback
            return {
                'title': 'Unknown Citation',
                'summary': str(citation),
                'passage': str(citation),
                'authors': [],
                'publication_date': 'Unknown',
                'publication': None,
                'relevance_score': 0,
                'document_id': 'Unknown',
                'pmid': None,
                'doi': None
            }
    
    def _create_citation_publication_info(self, citation_data: Dict[str, Any]) -> str:
        """Create publication info string for citation."""
        pub_info_parts = []
        
        if citation_data['publication'] and citation_data['publication'].strip():
            pub_info_parts.append(citation_data['publication'].strip())
        
        year_only = extract_year_from_date(str(citation_data['publication_date']))
        if year_only != 'Unknown':
            pub_info_parts.append(year_only)
        
        return ' • '.join(pub_info_parts) if pub_info_parts else 'Unknown publication'
    
    def _create_citation_content_sections(self, citation_data: Dict[str, Any]) -> List[ft.Control]:
        """Create content sections for citation card."""
        sections = []
        
        # Full title
        sections.append(
            ft.Container(
                content=ft.Text(
                    f"Title: {citation_data['title']}",
                    size=11,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.BLUE_900
                ),
                padding=ft.padding.only(bottom=8)
            )
        )
        
        # Authors
        authors_str = ', '.join(citation_data['authors']) if citation_data['authors'] else 'Unknown'
        sections.append(
            ft.Container(
                content=ft.Text(
                    f"Authors: {authors_str}",
                    size=10,
                    color=ft.Colors.GREY_700
                ),
                padding=ft.padding.only(bottom=8)
            )
        )
        
        # Citation metadata
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


class CounterfactualDisplayCreator:
    """Creates counterfactual analysis displays."""
    
    def create_counterfactual_display(self, analysis: Any) -> List[ft.Control]:
        """Create display components for counterfactual analysis."""
        # Check analysis type and create appropriate display
        if isinstance(analysis, dict):
            # Check if this looks like a corrupted database document mixed with analysis
            if 'id' in analysis and 'source_id' in analysis and 'summary' in analysis:
                # This is a database document with analysis fields - extract clean analysis
                return self._create_corrupted_analysis_components(analysis)
            elif 'summary' in analysis:
                # Clean comprehensive analysis with search results
                return self._create_comprehensive_analysis_components(analysis)
            else:
                # Fallback for unknown dict format
                return self._create_fallback_analysis_components(analysis)
        elif hasattr(analysis, 'main_claims') or hasattr(analysis, 'counterfactual_questions'):
            # Basic counterfactual analysis object
            return self._create_basic_analysis_components(analysis)
        else:
            # Fallback for unknown format
            return self._create_fallback_analysis_components(analysis)
    
    def _create_corrupted_analysis_components(self, corrupted_analysis: Dict) -> List[ft.Control]:
        """Create components for corrupted analysis (database document mixed with analysis fields)."""
        components = []
        
        # Extract the actual analysis parts from the corrupted structure
        summary = corrupted_analysis.get('summary', {})
        contradictory_evidence = corrupted_analysis.get('contradictory_evidence', [])
        contradictory_citations = corrupted_analysis.get('contradictory_citations', [])
        
        # Debug the actual contents
        print(f"🔍 DEBUG: contradictory_evidence type: {type(contradictory_evidence)}")
        if contradictory_evidence:
            print(f"🔍 DEBUG: contradictory_evidence[0] type: {type(contradictory_evidence[0])}")
            print(f"🔍 DEBUG: contradictory_evidence[0] keys: {list(contradictory_evidence[0].keys()) if isinstance(contradictory_evidence[0], dict) else 'Not a dict'}")
            print(f"🔍 DEBUG: contradictory_evidence[0] content sample: {str(contradictory_evidence[0])[:200]}...")
        
        print(f"🔍 DEBUG: contradictory_citations type: {type(contradictory_citations)}")
        if contradictory_citations:
            print(f"🔍 DEBUG: contradictory_citations[0] type: {type(contradictory_citations[0])}")
            print(f"🔍 DEBUG: contradictory_citations[0] content sample: {str(contradictory_citations[0])[:200]}...")
        
        # Header explaining the issue and what we found
        components.append(
            ft.Text(
                f"📚 Counterfactual Analysis Results (Data Structure Issue Detected)",
                size=15,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.DEEP_PURPLE_700,
                selectable=True
            )
        )
        
        components.append(
            ft.Text(
                f"Found {len(contradictory_evidence)} contradictory studies and {len(contradictory_citations)} citations. Note: The analysis result has a data structure issue that's being worked around.",
                size=12,
                color=ft.Colors.GREY_600,
                italic=True,
                selectable=True
            )
        )
        
        # Create a clean analysis structure from the corrupted data
        clean_analysis = {
            'summary': summary,
            'contradictory_evidence': contradictory_evidence,
            'contradictory_citations': contradictory_citations
        }
        
        # Extract the actual documents and citations from the wrapper structures
        actual_evidence = []
        for i, evidence_item in enumerate(contradictory_evidence):
            if isinstance(evidence_item, dict) and 'document' in evidence_item:
                # Extract the nested document
                doc = evidence_item['document']
                actual_evidence.append(doc)
                print(f"🔍 DEBUG: Extracted evidence {i}: {doc.get('title', 'No title')[:60]}...")
            else:
                # Fallback for unexpected structure
                actual_evidence.append(evidence_item)
                print(f"🔍 DEBUG: Evidence {i} unexpected structure: {type(evidence_item)}")
        
        actual_citations = []
        for i, citation_item in enumerate(contradictory_citations):
            if isinstance(citation_item, dict) and 'citation' in citation_item:
                # Extract the nested citation
                citation = citation_item['citation']
                actual_citations.append(citation)
                print(f"🔍 DEBUG: Extracted citation {i}: {getattr(citation, 'document_title', 'No title')[:60]}...")
            else:
                # Fallback for unexpected structure
                actual_citations.append(citation_item)
                print(f"🔍 DEBUG: Citation {i} unexpected structure: {type(citation_item)}")
        
        # Create a clean analysis structure with extracted data
        clean_analysis = {
            'summary': summary,
            'contradictory_evidence': actual_evidence,
            'contradictory_citations': actual_citations
        }
        
        # Use the comprehensive analysis display for the cleaned data
        components.extend(self._create_comprehensive_sections(clean_analysis))
        
        # Add debug info about the corruption
        components.append(
            ft.Container(
                content=ft.Column([
                    ft.Text(
                        "🔧 Debug Information",
                        size=14,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.ORANGE_700,
                        selectable=True
                    ),
                    ft.Text(
                        f"The counterfactual analysis returned a database document record with nested analysis fields.",
                        size=11,
                        color=ft.Colors.GREY_700,
                        selectable=True
                    ),
                    ft.Text(
                        f"✅ Successfully extracted {len(actual_evidence)} documents and {len(actual_citations)} citations from nested structure.",
                        size=10,
                        color=ft.Colors.GREEN_600,
                        selectable=True
                    ),
                    ft.Text(
                        f"Evidence structure: document + score + reasoning + query_info",
                        size=10,
                        color=ft.Colors.GREY_600,
                        selectable=True
                    ),
                    ft.Text(
                        f"Citation structure: citation + original_claim + counterfactual_question + scores",
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
        )
        
        return components
    
    def _create_comprehensive_analysis_components(self, analysis_dict: Dict) -> List[ft.Control]:
        """Create components for comprehensive counterfactual analysis."""
        components = []
        
        summary = analysis_dict.get('summary', {})
        analysis_obj = analysis_dict.get('analysis')
        contradictory_evidence = analysis_dict.get('contradictory_evidence', [])
        contradictory_citations = analysis_dict.get('contradictory_citations', [])
        
        # Header
        components.append(
            ft.Text(
                f"📚 Comprehensive Counterfactual Analysis with Literature Search Completed",
                size=15,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.PURPLE_700
            )
        )
        
        components.append(
            ft.Text(
                f"Found {len(contradictory_evidence)} contradictory studies and extracted {len(contradictory_citations)} citations that challenge the original claims.",
                size=12,
                color=ft.Colors.GREY_600,
                italic=True
            )
        )
        
        # Add comprehensive analysis sections
        components.extend(self._create_comprehensive_sections(analysis_dict))
        
        return components
    
    def _create_basic_analysis_components(self, analysis: Any) -> List[ft.Control]:
        """Create components for basic counterfactual analysis."""
        components = []
        
        questions_count = len(getattr(analysis, 'counterfactual_questions', []))
        claims_count = len(getattr(analysis, 'main_claims', []))
        
        # Header
        components.append(
            ft.Text(
                f"📋 Basic Counterfactual Analysis Completed",
                size=15,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.ORANGE_700
            )
        )
        
        components.append(
            ft.Text(
                f"Analyzed {claims_count} claims and generated {questions_count} research questions for finding contradictory evidence.",
                size=12,
                color=ft.Colors.GREY_600,
                italic=True
            )
        )
        
        # Add basic analysis sections
        components.extend(self._create_basic_sections(analysis))
        
        return components
    
    def _create_fallback_analysis_components(self, analysis: Any) -> List[ft.Control]:
        """Create fallback components for unknown analysis format."""
        components = []
        
        components.append(
            ft.Text(
                f"⚠️ Counterfactual Analysis (Unknown Format)",
                size=15,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.GREY_700
            )
        )
        
        analysis_str = str(analysis)
        if len(analysis_str) > 500:
            analysis_str = analysis_str[:500] + "..."
        
        components.append(
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
        )
        
        return components
    
    def _create_comprehensive_sections(self, analysis_dict: Dict) -> List[ft.Control]:
        """Create sections for comprehensive analysis."""
        sections = []
        
        summary = analysis_dict.get('summary', {})
        analysis_obj = analysis_dict.get('analysis')
        contradictory_evidence = analysis_dict.get('contradictory_evidence', [])
        contradictory_citations = analysis_dict.get('contradictory_citations', [])
        
        # Original analysis section (if exists)
        if analysis_obj:
            sections.extend(self._create_basic_sections(analysis_obj))
        
        # Summary section
        if summary:
            sections.append(self._create_summary_section(summary))
        
        # Contradictory evidence section
        if contradictory_evidence:
            sections.append(self._create_contradictory_evidence_section(contradictory_evidence))
        
        # Contradictory citations section  
        if contradictory_citations:
            sections.append(self._create_contradictory_citations_section(contradictory_citations))
        
        return sections
    
    def _create_basic_sections(self, analysis: Any) -> List[ft.Control]:
        """Create sections for basic analysis."""
        sections = []
        
        # Main claims section
        if hasattr(analysis, 'main_claims') and analysis.main_claims:
            sections.append(self._create_claims_section(analysis.main_claims))
        
        # Research questions section
        if hasattr(analysis, 'counterfactual_questions') and analysis.counterfactual_questions:
            sections.append(self._create_questions_section(analysis.counterfactual_questions))
        
        # Assessment section
        sections.append(self._create_assessment_section(analysis))
        
        return sections
    
    def _create_claims_section(self, claims: List[str]) -> ft.Container:
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
    
    def _create_questions_section(self, questions: List[Any]) -> ft.Container:
        """Create research questions section."""
        question_cards = []
        
        for i, question in enumerate(questions, 1):
            priority = getattr(question, 'priority', 'MEDIUM')
            priority_badge = create_priority_badge(priority)
            
            question_text = getattr(question, 'question', 'Unknown question')
            
            question_cards.append(
                ft.ExpansionTile(
                    title=ft.Row([
                        ft.Text(
                            f"{i}. {truncate_text(question_text, 70)}",
                            size=12,
                            weight=ft.FontWeight.W_500,
                            color=ft.Colors.ORANGE_800
                        ),
                        priority_badge
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    controls=[
                        ft.Container(
                            content=ft.Column([
                                ft.Text(
                                    f"Full Question: {question_text}",
                                    size=11,
                                    weight=ft.FontWeight.BOLD,
                                    color=ft.Colors.GREY_800
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
                            ], spacing=4),
                            padding=ft.padding.all(12)
                        )
                    ]
                )
            )
        
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
    
    def _create_assessment_section(self, analysis: Any) -> ft.Container:
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
    
    def _create_summary_section(self, summary: Dict) -> ft.Container:
        """Create summary section for comprehensive analysis."""
        summary_items = []
        
        # Handle different summary formats - the new format has different keys
        if summary.get('claims_analyzed'):
            summary_items.append(
                ft.Text(
                    f"📋 Claims Analyzed: {summary['claims_analyzed']}",
                    size=12,
                    weight=ft.FontWeight.W_500,
                    color=ft.Colors.PURPLE_700,
                    selectable=True
                )
            )
        elif summary.get('hypotheses_contested'):
            summary_items.append(
                ft.Text(
                    f"📋 Hypotheses Contested: {summary['hypotheses_contested']}",
                    size=12,
                    weight=ft.FontWeight.W_500,
                    color=ft.Colors.PURPLE_700
                )
            )
        
        if summary.get('questions_generated'):
            summary_items.append(
                ft.Text(
                    f"🔍 Research Questions Generated: {summary['questions_generated']}",
                    size=12,
                    weight=ft.FontWeight.W_500,
                    color=ft.Colors.PURPLE_700
                )
            )
        elif summary.get('literature_search_queries'):
            summary_items.append(
                ft.Text(
                    f"🔍 Literature Search Queries: {summary['literature_search_queries']}",
                    size=12,
                    weight=ft.FontWeight.W_500,
                    color=ft.Colors.PURPLE_700
                )
            )
        
        if summary.get('high_priority_questions'):
            summary_items.append(
                ft.Text(
                    f"⚡ High Priority Questions: {summary['high_priority_questions']}",
                    size=12,
                    weight=ft.FontWeight.W_500,
                    color=ft.Colors.PURPLE_700
                )
            )
        
        if summary.get('database_searches'):
            summary_items.append(
                ft.Text(
                    f"🗄️ Database Searches Performed: {summary['database_searches']}",
                    size=12,
                    weight=ft.FontWeight.W_500,
                    color=ft.Colors.PURPLE_700
                )
            )
        
        if summary.get('contradictory_documents_found'):
            summary_items.append(
                ft.Text(
                    f"📚 Contradictory Documents Found: {summary['contradictory_documents_found']}",
                    size=12,
                    weight=ft.FontWeight.W_500,
                    color=ft.Colors.PURPLE_700
                )
            )
        elif summary.get('contradictory_studies_found'):
            summary_items.append(
                ft.Text(
                    f"📚 Contradictory Studies Found: {summary['contradictory_studies_found']}",
                    size=12,
                    weight=ft.FontWeight.W_500,
                    color=ft.Colors.PURPLE_700
                )
            )
        
        if summary.get('contradictory_citations_extracted'):
            summary_items.append(
                ft.Text(
                    f"📝 Contradictory Citations Extracted: {summary['contradictory_citations_extracted']}",
                    size=12,
                    weight=ft.FontWeight.W_500,
                    color=ft.Colors.PURPLE_700
                )
            )
        elif summary.get('citations_extracted'):
            summary_items.append(
                ft.Text(
                    f"📝 Citations Extracted: {summary['citations_extracted']}",
                    size=12,
                    weight=ft.FontWeight.W_500,
                    color=ft.Colors.PURPLE_700
                )
            )
        
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
            summary_items.append(
                ft.Text(
                    f"🗄️ Database Status: {availability}",
                    size=12,
                    weight=ft.FontWeight.W_500,
                    color=ft.Colors.GREEN_700 if summary['database_available'] else ft.Colors.RED_700
                )
            )
        
        if summary.get('overall_strength'):
            summary_items.append(
                ft.Text(
                    f"⚖️ Overall Strength of Contradictory Evidence: {summary['overall_strength']}",
                    size=12,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.RED_700 if 'Strong' in summary['overall_strength'] else ft.Colors.ORANGE_700
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
    
    def _create_contradictory_evidence_section(self, evidence: List[dict]) -> ft.Container:
        """Create contradictory evidence section."""
        evidence_cards = []
        
        for i, doc in enumerate(evidence, 1):
            # Handle different document formats
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
            else:
                # Fallback for non-dict items
                title = str(doc)
                authors = 'Unknown authors'
                year = 'Unknown year'
                abstract = str(doc)
            
            evidence_cards.append(
                ft.ExpansionTile(
                    title=ft.Text(
                        f"{i}. {truncate_text(title, 80)}",
                        size=12,
                        weight=ft.FontWeight.W_500,
                        color=ft.Colors.RED_800
                    ),
                    subtitle=ft.Text(
                        f"{authors} • {year}",
                        size=10,
                        color=ft.Colors.GREY_600
                    ),
                    controls=[
                        ft.Container(
                            content=ft.Column([
                                ft.Text(
                                    f"Title: {title}",
                                    size=11,
                                    weight=ft.FontWeight.BOLD,
                                    color=ft.Colors.RED_900
                                ),
                                ft.Text(
                                    f"Authors: {authors}",
                                    size=10,
                                    color=ft.Colors.GREY_700
                                ),
                                ft.Text(
                                    f"Abstract: {abstract}",
                                    size=10,
                                    color=ft.Colors.GREY_700
                                )
                            ], spacing=4),
                            padding=ft.padding.all(12)
                        )
                    ]
                )
            )
        
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
    
    def _create_contradictory_citations_section(self, citations: List[Any]) -> ft.Container:
        """Create contradictory citations section."""
        citation_cards = []
        
        for i, citation in enumerate(citations, 1):
            citation_data = self._extract_citation_data(citation)
            
            citation_cards.append(
                ft.ExpansionTile(
                    title=ft.Text(
                        f"{i}. {truncate_text(citation_data['title'], 80)}",
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
            )
        
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
    
    def _extract_citation_data(self, citation: Any) -> Dict[str, Any]:
        """Extract data from citation object or dictionary (CounterfactualDisplayCreator version)."""
        # Debug the citation structure
        print(f"🔍 DEBUG: Extracting citation data from type: {type(citation)}")
        if isinstance(citation, dict):
            print(f"🔍 DEBUG: Citation dict keys: {list(citation.keys())}")
        
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
                # Convert string to list if needed
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
            return {
                'title': 'Unknown Citation',
                'summary': str(citation)[:200] + "..." if len(str(citation)) > 200 else str(citation),
                'passage': str(citation)[:200] + "..." if len(str(citation)) > 200 else str(citation),
                'authors': [],
                'publication_date': 'Unknown',
                'publication': None,
                'relevance_score': 0,
                'document_id': 'Unknown',
                'pmid': None,
                'doi': None
            }