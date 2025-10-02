"""
Data models for counterfactual analysis.

This module defines the data structures used in counterfactual checking
and analysis workflows.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class CounterfactualQuestion:
    """Represents a research question designed to find contradictory evidence."""
    counterfactual_statement: str  # The opposite claim as a declarative statement
    question: str  # Research question for human understanding
    reasoning: str
    target_claim: str  # The specific claim this question targets
    search_keywords: List[str]  # Suggested keywords for literature search
    priority: str  # HIGH, MEDIUM, LOW based on importance of the claim
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)


@dataclass
class CounterfactualAnalysis:
    """Complete analysis of a document with suggested counterfactual questions."""
    document_title: str
    main_claims: List[str]
    counterfactual_questions: List[CounterfactualQuestion]
    overall_assessment: str
    confidence_level: str  # HIGH, MEDIUM, LOW - how confident we are in the document's claims
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)
