"""
Database module for Fact Checker

Provides database operations for storing:
- Biomedical statements for fact-checking
- AI-generated evaluations with evidence
- Human annotations from multiple reviewers
- Processing metadata and export history

Supports both PostgreSQL (main database) and SQLite (portable review packages)
via an abstract database interface.
"""

from pathlib import Path
from typing import Union

from .database import (
    FactCheckerDB,
    Statement,
    Annotator,
    AIEvaluation,
    Evidence,
    HumanAnnotation,
    SCHEMA_VERSION
)

from .abstract_db import AbstractFactCheckerDB
from .postgresql_db import PostgreSQLFactCheckerDB
from .sqlite_db import SQLiteFactCheckerDB


def get_fact_checker_db(db_path: Union[str, Path, None] = None) -> AbstractFactCheckerDB:
    """
    Factory function to create appropriate fact-checker database instance.

    Args:
        db_path: Path to SQLite database file, or None for PostgreSQL

    Returns:
        AbstractFactCheckerDB instance (PostgreSQL or SQLite)

    Examples:
        # Use PostgreSQL (default)
        db = get_fact_checker_db()

        # Use SQLite review package
        db = get_fact_checker_db("review_package.db")
    """
    if db_path is None:
        # Use PostgreSQL
        return PostgreSQLFactCheckerDB()
    else:
        # Use SQLite
        db_path = Path(db_path)
        if not db_path.exists():
            raise FileNotFoundError(f"SQLite database not found: {db_path}")
        if db_path.suffix != '.db':
            raise ValueError(f"Invalid SQLite database file (expected .db): {db_path}")
        return SQLiteFactCheckerDB(str(db_path))


__all__ = [
    # Legacy exports (for backward compatibility)
    'FactCheckerDB',
    'Statement',
    'Annotator',
    'AIEvaluation',
    'Evidence',
    'HumanAnnotation',
    'SCHEMA_VERSION',
    # Abstraction layer
    'AbstractFactCheckerDB',
    'PostgreSQLFactCheckerDB',
    'SQLiteFactCheckerDB',
    'get_fact_checker_db'
]
