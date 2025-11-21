"""
PaperChecker module for fact-checking medical abstracts.

This module provides sophisticated fact-checking capabilities for medical abstracts
by systematically searching for and analyzing contradictory evidence. It combines
multi-strategy search (semantic, HyDE, keyword), document scoring, citation
extraction, and evidence synthesis to generate verdicts on research claims.

Main components:
    - PaperCheckerAgent: Main agent orchestrating the fact-checking workflow
    - Data models: Type-safe dataclasses for the entire workflow
    - Components: Modular workflow components (StatementExtractor, etc.)
    - Agent: PaperCheckerAgent orchestrating the fact-checking process
    - Database: PostgreSQL schema for storing results
    - Components: Sub-components for each workflow step

Example:
    >>> from bmlibrarian.paperchecker import PaperCheckerAgent
    >>> agent = PaperCheckerAgent()
    >>> result = agent.check_abstract(
    ...     abstract="Metformin shows superior efficacy...",
    ...     source_metadata={"pmid": 12345678}
    ... )
    >>> print(result.overall_assessment)
"""

from .data_models import (
    # Data models
    Statement,
    CounterStatement,
    SearchResults,
    ScoredDocument,
    ExtractedCitation,
    CounterReport,
    Verdict,
    PaperCheckResult,
    # Constants
    MIN_CONFIDENCE,
    MAX_CONFIDENCE,
    MIN_SCORE,
    MAX_SCORE,
    MIN_ORDER,
    MIN_DOC_ID,
    VALID_STATEMENT_TYPES,
    VALID_SEARCH_STRATEGIES,
    VALID_VERDICT_VALUES,
    VALID_CONFIDENCE_LEVELS,
    DEFAULT_DOCUMENTS_FOUND,
    DEFAULT_DOCUMENTS_SCORED,
)

from .agent import PaperCheckerAgent

from .database import PaperCheckDB

from .components import (
    StatementExtractor,
# STILL TO BE IMPLEMENTED - uncomment once done
#    CounterStatementGenerator,
#    HyDEGenerator,
#    SearchCoordinator,
#    VerdictAnalyzer,
)

__all__ = [
    # Main Agent
    "PaperCheckerAgent",
    # Database
    "PaperCheckDB",
    # Components
    "StatementExtractor",
    "CounterStatementGenerator",
    "HyDEGenerator",
    "SearchCoordinator",
    "VerdictAnalyzer",
    # Data models
    "Statement",
    "CounterStatement",
    "SearchResults",
    "ScoredDocument",
    "ExtractedCitation",
    "CounterReport",
    "Verdict",
    "PaperCheckResult",
    # Components
    "StatementExtractor",
    # Constants
    "MIN_CONFIDENCE",
    "MAX_CONFIDENCE",
    "MIN_SCORE",
    "MAX_SCORE",
    "MIN_ORDER",
    "MIN_DOC_ID",
    "VALID_STATEMENT_TYPES",
    "VALID_SEARCH_STRATEGIES",
    "VALID_VERDICT_VALUES",
    "VALID_CONFIDENCE_LEVELS",
    "DEFAULT_DOCUMENTS_FOUND",
    "DEFAULT_DOCUMENTS_SCORED",
]

__version__ = "0.1.0"
