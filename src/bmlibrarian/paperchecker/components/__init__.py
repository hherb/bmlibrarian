"""
PaperChecker workflow components.

This package contains the modular components that implement each step
of the PaperChecker workflow:

- StatementExtractor: Extracts core research claims from medical abstracts

Each component is designed to be independently testable and reusable.
"""

from .statement_extractor import StatementExtractor

__all__ = [
    "StatementExtractor",
]
