"""
Database module for Fact Checker

Provides SQLite database schema and operations for storing:
- Biomedical statements for fact-checking
- AI-generated evaluations with evidence
- Human annotations from multiple reviewers
- Processing metadata and export history
"""

from .database import (
    FactCheckerDB,
    Statement,
    Annotator,
    AIEvaluation,
    Evidence,
    HumanAnnotation,
    create_database_from_input_file,
    SCHEMA_VERSION
)

__all__ = [
    'FactCheckerDB',
    'Statement',
    'Annotator',
    'AIEvaluation',
    'Evidence',
    'HumanAnnotation',
    'create_database_from_input_file',
    'SCHEMA_VERSION'
]
