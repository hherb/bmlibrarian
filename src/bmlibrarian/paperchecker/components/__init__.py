"""
PaperChecker workflow components.

This package contains the modular components that implement each step
of the PaperChecker workflow:

- StatementExtractor: Extracts core research claims from medical abstracts
- CounterStatementGenerator: Generates semantically precise negations of claims
- HyDEGenerator: Generates hypothetical abstracts and keywords for search
- SearchCoordinator: Coordinates multi-strategy search (stub - Step 07)
- VerdictAnalyzer: Analyzes evidence and generates verdicts (stub - Step 11)

Each component is designed to be independently testable and reusable.
"""

from .statement_extractor import StatementExtractor
from .counter_statement_generator import CounterStatementGenerator
from .hyde_generator import HyDEGenerator
from .search_coordinator import SearchCoordinator
from .verdict_analyzer import VerdictAnalyzer

__all__ = [
    "StatementExtractor",
    "CounterStatementGenerator",
    "HyDEGenerator",
    "SearchCoordinator",
    "VerdictAnalyzer",
]
