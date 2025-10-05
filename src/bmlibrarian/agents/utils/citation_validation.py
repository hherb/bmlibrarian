"""
Citation validation utilities for counterfactual analysis.

This module provides functions for validating that citations actually support
counterfactual claims and assessing the strength of counter-evidence.
"""

import logging
from typing import Dict, List, Any, Optional, Callable

logger = logging.getLogger(__name__)


def validate_citation_supports_counterfactual(
    passage: str,
    summary: str,
    counterfactual_statement: str,
    original_claim: str,
    llm_request_func: Callable,
    json_parser_func: Callable
) -> tuple[bool, str]:
    """
    Validate that a citation actually SUPPORTS the counterfactual statement.

    This is critical because the citation agent might extract passages that are merely
    topically related rather than actually supporting the counterfactual claim.

    Args:
        passage: The actual quoted text from the document
        summary: The LLM's interpretation of the passage
        counterfactual_statement: The claim we're trying to find support for
        original_claim: The original claim (for context)
        llm_request_func: Function to make LLM requests (from BaseAgent)
        json_parser_func: Function to parse JSON responses (from BaseAgent)

    Returns:
        Tuple of (supports: bool, reasoning: str)
    """
    validation_prompt = f"""You are validating whether a passage from medical literature actually SUPPORTS a specific claim.

COUNTERFACTUAL CLAIM (what we're trying to prove):
{counterfactual_statement}

ORIGINAL CLAIM (for context - we want evidence AGAINST this):
{original_claim}

PASSAGE FROM DOCUMENT:
{passage}

TASK: Does this passage actually SUPPORT the counterfactual claim above?

IMPORTANT:
- Return "YES" ONLY if the passage provides evidence that SUPPORTS the counterfactual claim
- Return "NO" if the passage:
  * Contradicts the counterfactual claim (supports the original claim instead)
  * Is merely topically related without taking a position
  * Discusses the topic but doesn't provide evidence for the counterfactual

Response Format - Return ONLY valid JSON:
{{
    "supports_counterfactual": true/false,
    "reasoning": "Brief explanation of why the passage does or doesn't support the counterfactual claim"
}}

Example 1:
Counterfactual: "Drug X does not cause side effect Y"
Passage: "In our study, Drug X showed no significant increase in side effect Y compared to placebo"
Answer: {{"supports_counterfactual": true, "reasoning": "Passage provides direct evidence of no significant increase"}}

Example 2:
Counterfactual: "Drug X does not cause side effect Y"
Passage: "Drug X caused a 3-fold increase in side effect Y in 15% of patients"
Answer: {{"supports_counterfactual": false, "reasoning": "Passage shows Drug X DOES cause side effect Y, contradicting counterfactual"}}

Return ONLY the JSON object, no other text."""

    try:
        messages = [{'role': 'user', 'content': validation_prompt}]
        response = llm_request_func(
            messages,
            system_prompt="You are a medical literature validation expert. Analyze passages carefully to determine if they support specific claims.",
            num_predict=300,
            temperature=0.1  # Low temperature for consistent validation
        )

        result = json_parser_func(response)

        if not isinstance(result, dict) or 'supports_counterfactual' not in result:
            logger.warning(f"Invalid validation response format, defaulting to False")
            return False, "Invalid validation response format"

        supports = result['supports_counterfactual']
        reasoning = result.get('reasoning', 'No reasoning provided')

        logger.debug(f"Citation validation: {supports} - {reasoning}")

        return supports, reasoning

    except Exception as e:
        logger.warning(f"Citation validation failed: {e}, defaulting to False for safety")
        return False, f"Validation error: {str(e)}"


def assess_counter_evidence_strength(
    original_claim: str,
    counterfactual_statement: str,
    citations: List[Dict[str, Any]]
) -> str:
    """
    Assess whether the counter-evidence is sufficient to challenge or reject the original claim.

    Args:
        original_claim: The original claim being challenged
        counterfactual_statement: The counterfactual research question
        citations: List of contradictory citations found

    Returns:
        Critical assessment string explaining the strength of counter-evidence
    """
    if not citations:
        return "No contradictory evidence found."

    num_citations = len(citations)
    avg_document_score = sum(c.get('document_score', 0) for c in citations) / num_citations
    avg_relevance_score = sum(c.get('relevance_score', 0) for c in citations) / num_citations
    high_quality_citations = sum(1 for c in citations if c.get('document_score', 0) >= 4)

    # Build assessment based on quantity and quality
    assessment_parts = []

    # Quantity assessment
    if num_citations >= 3:
        assessment_parts.append(f"**Multiple sources ({num_citations} citations)** provide contradictory evidence.")
    elif num_citations == 2:
        assessment_parts.append(f"**Two independent sources** provide contradictory evidence.")
    else:
        assessment_parts.append(f"**Single source** provides contradictory evidence.")

    # Quality assessment
    if avg_document_score >= 4.0:
        assessment_parts.append(f"The counter-evidence is **highly relevant** (avg. relevance: {avg_document_score:.1f}/5).")
    elif avg_document_score >= 3.0:
        assessment_parts.append(f"The counter-evidence is **moderately relevant** (avg. relevance: {avg_document_score:.1f}/5).")
    else:
        assessment_parts.append(f"The counter-evidence is **weakly relevant** (avg. relevance: {avg_document_score:.1f}/5).")

    # Strength conclusion
    if num_citations >= 3 and avg_document_score >= 4.0:
        conclusion = "**STRONG CHALLENGE**: The contradictory evidence is substantial and highly relevant, significantly undermining confidence in the original claim."
    elif num_citations >= 2 and avg_document_score >= 3.5:
        conclusion = "**MODERATE CHALLENGE**: The contradictory evidence raises important questions about the original claim's validity and warrants careful consideration."
    elif num_citations >= 1 and avg_document_score >= 3.0:
        conclusion = "**WEAK CHALLENGE**: The contradictory evidence suggests alternative interpretations exist, but is insufficient to reject the original claim."
    else:
        conclusion = "**MINIMAL CHALLENGE**: The contradictory evidence is limited in quantity or relevance, providing only marginal challenges to the original claim."

    assessment_parts.append(conclusion)

    return " ".join(assessment_parts)
