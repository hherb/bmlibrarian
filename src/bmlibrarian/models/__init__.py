"""Data models for BMLibrarian.

Provides TypedDict definitions and validation utilities for standard data structures
used throughout the BMLibrarian system.
"""

from .document import (
    DocumentDict,
    ScoreResult,
    ScoredDocument,
    validate_document,
    validate_score_result,
    get_document_year,
    format_authors,
    truncate_abstract,
    create_document_summary
)

__all__ = [
    # Document models
    'DocumentDict',
    'ScoreResult',
    'ScoredDocument',
    # Validation functions
    'validate_document',
    'validate_score_result',
    # Utility functions
    'get_document_year',
    'format_authors',
    'truncate_abstract',
    'create_document_summary',
]
