"""
Formatting utilities for counterfactual analysis reports.

This module provides functions for formatting counterfactual analysis results
into structured reports and research protocols.
"""

import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


def generate_research_protocol(analysis: 'CounterfactualAnalysis') -> str:
    """
    Generate a structured research protocol for investigating the counterfactual questions.

    Args:
        analysis: CounterfactualAnalysis object

    Returns:
        Formatted research protocol as a string
    """
    protocol = f"""# Counterfactual Research Protocol
Document: {analysis.document_title}
Generated: {analysis.created_at.strftime('%Y-%m-%d %H:%M:%S') if analysis.created_at else 'Unknown'}
Confidence in Original Claims: {analysis.confidence_level}

## Main Claims to Verify
"""
    for i, claim in enumerate(analysis.main_claims, 1):
        protocol += f"{i}. {claim}\n"

    protocol += f"\n## Overall Assessment\n{analysis.overall_assessment}\n\n"

    # Group questions by priority
    high_priority = [q for q in analysis.counterfactual_questions if q.priority == "HIGH"]
    medium_priority = [q for q in analysis.counterfactual_questions if q.priority == "MEDIUM"]
    low_priority = [q for q in analysis.counterfactual_questions if q.priority == "LOW"]

    for priority_group, priority_name in [(high_priority, "HIGH PRIORITY"),
                                        (medium_priority, "MEDIUM PRIORITY"),
                                        (low_priority, "LOW PRIORITY")]:
        if priority_group:
            protocol += f"## {priority_name} Research Questions\n\n"
            for i, question in enumerate(priority_group, 1):
                protocol += f"### Question {i}\n"
                protocol += f"**Counterfactual Statement:** {question.counterfactual_statement}\n\n"
                protocol += f"**Research Question:** {question.question}\n\n"
                protocol += f"**Target Claim:** {question.target_claim}\n\n"
                protocol += f"**Reasoning:** {question.reasoning}\n\n"
                protocol += f"**Search Keywords:** {', '.join(question.search_keywords)}\n\n"
                protocol += "---\n\n"

    return protocol


def format_counterfactual_report(
    analysis: 'CounterfactualAnalysis',
    research_queries: List[Dict[str, str]],
    contradictory_citations: List[Dict[str, Any]],
    contradictory_evidence: List[Dict[str, Any]],
    assess_evidence_func: callable
) -> Dict[str, Any]:
    """
    Format counterfactual analysis results into the structured claim/statement/evidence format.

    Args:
        analysis: CounterfactualAnalysis object with original claims
        research_queries: List of query information with target claims
        contradictory_citations: List of contradictory citations found
        contradictory_evidence: List of contradictory documents found
        assess_evidence_func: Function to assess evidence strength

    Returns:
        Structured format with claims, counterfactual statements, evidence, critical assessment, and summary
    """
    formatted_items = []

    # Create a mapping from claims to their counterfactual statements and questions
    claim_to_counterfactual = {}
    for query_info in research_queries:
        target_claim = query_info.get('target_claim', '')
        counterfactual_statement = query_info.get('counterfactual_statement', '')
        counterfactual_question = query_info.get('question', '')
        if target_claim:
            claim_to_counterfactual[target_claim] = {
                'statement': counterfactual_statement,
                'question': counterfactual_question
            }

    # Group citations by their original claims
    claims_with_evidence = {}
    for citation_item in contradictory_citations:
        original_claim = citation_item.get('original_claim', 'Unknown claim')
        if original_claim not in claims_with_evidence:
            # Get the counterfactual info from our mapping
            counterfactual_info = claim_to_counterfactual.get(original_claim, {})
            claims_with_evidence[original_claim] = {
                'claim': original_claim,
                'counterfactual_statement': counterfactual_info.get('statement', ''),
                'counterfactual_question': counterfactual_info.get('question', ''),
                'citations': []
            }

        citation = citation_item.get('citation')
        if citation:
            claims_with_evidence[original_claim]['citations'].append({
                'title': getattr(citation, 'document_title', 'Unknown title'),
                'passage': getattr(citation, 'passage', 'No passage extracted'),  # ACTUAL quoted text
                'summary': getattr(citation, 'summary', 'No summary available'),  # LLM summary
                'authors': getattr(citation, 'authors', []),
                'publication_date': getattr(citation, 'publication_date', 'Unknown date'),
                'pmid': getattr(citation, 'pmid', None),
                'doi': getattr(citation, 'doi', None),
                'publication': getattr(citation, 'publication', None),
                'relevance_score': getattr(citation, 'relevance_score', 0),
                'document_score': citation_item.get('document_score', 0),
                'score_reasoning': citation_item.get('score_reasoning', '')
            })

    # Process ALL claims from the original analysis (not just those with evidence)
    for main_claim in analysis.main_claims:
        # Check if we found evidence for this claim
        if main_claim in claims_with_evidence:
            # We have contradictory evidence
            claim_data = claims_with_evidence[main_claim]
            citations = claim_data['citations']

            # Critical assessment based on evidence strength
            assessment = assess_evidence_func(
                main_claim,
                claim_data['counterfactual_statement'],
                citations
            )

            formatted_item = {
                'claim': main_claim,
                'counterfactual_statement': claim_data['counterfactual_statement'],
                'counterfactual_question': claim_data['counterfactual_question'],
                'counterfactual_evidence': citations,
                'evidence_found': True,
                'critical_assessment': assessment
            }
        else:
            # No contradictory evidence found for this claim
            counterfactual_info = claim_to_counterfactual.get(main_claim, {})
            counterfactual_statement = counterfactual_info.get('statement', 'No counterfactual statement generated')
            counterfactual_question = counterfactual_info.get('question', 'No counterfactual question generated')

            formatted_item = {
                'claim': main_claim,
                'counterfactual_statement': counterfactual_statement,
                'counterfactual_question': counterfactual_question,
                'counterfactual_evidence': [],
                'evidence_found': False,
                'critical_assessment': 'No contradictory evidence found in the database. This claim appears well-supported or lacks available counter-evidence in the current literature database.'
            }

        formatted_items.append(formatted_item)

    # Generate overall summary
    total_claims = len(analysis.main_claims)
    claims_with_evidence_count = len([item for item in formatted_items if item['evidence_found']])
    total_citations = sum(len(item['counterfactual_evidence']) for item in formatted_items)

    confidence_assessment = analysis.confidence_level
    if total_citations > 0:
        if total_citations >= 3:
            confidence_assessment = "LOW - Multiple contradictory studies found"
        elif total_citations >= 1:
            confidence_assessment = "MEDIUM-LOW - Some contradictory evidence found"

    summary_statement = f"""
Counterfactual Analysis Summary:
- Original report confidence: {analysis.confidence_level}
- Claims analyzed: {total_claims}
- Claims with contradictory evidence: {claims_with_evidence_count}
- Claims without contradictory evidence: {total_claims - claims_with_evidence_count}
- Total contradictory citations found: {total_citations}
- Revised confidence assessment: {confidence_assessment}

{f"WARNING: Found {total_citations} citations that contradict {claims_with_evidence_count} of {total_claims} key claims in the original report. " if total_citations > 0 else "No contradictory evidence found for any claims. "}
{"The original conclusions should be interpreted with caution given the contradictory evidence." if total_citations >= 2 else ""}
    """.strip()

    return {
        'items': formatted_items,
        'summary_statement': summary_statement,
        'statistics': {
            'total_claims_analyzed': total_claims,
            'claims_with_contradictory_evidence': claims_with_evidence_count,
            'claims_without_contradictory_evidence': total_claims - claims_with_evidence_count,
            'total_contradictory_citations': total_citations,
            'original_confidence': analysis.confidence_level,
            'revised_confidence': confidence_assessment
        }
    }
