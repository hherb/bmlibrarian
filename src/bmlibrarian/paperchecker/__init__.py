"""
PaperChecker module for fact-checking medical abstracts.

This module provides sophisticated fact-checking capabilities for medical abstracts
by systematically searching for and analyzing contradictory evidence. It combines
multi-strategy search (semantic, HyDE, keyword), document scoring, citation
extraction, and evidence synthesis to generate verdicts on research claims.

Main components:
    - Data models: Type-safe dataclasses for the entire workflow
    - Agent: PaperCheckerAgent orchestrating the fact-checking process
    - Database: PostgreSQL schema for storing results
    - CLI: Batch processing interface
    - Lab: Interactive testing interface
"""

from .data_models import (
    Statement,
    CounterStatement,
    SearchResults,
    ScoredDocument,
    ExtractedCitation,
    CounterReport,
    Verdict,
    PaperCheckResult
)

__all__ = [
    "Statement",
    "CounterStatement",
    "SearchResults",
    "ScoredDocument",
    "ExtractedCitation",
    "CounterReport",
    "Verdict",
    "PaperCheckResult"
]

__version__ = "0.1.0"
