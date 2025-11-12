"""
Fact Checker Module for BMLibrarian

Provides biomedical statement fact-checking against literature database with:
- AI-powered evaluation using FactCheckerAgent
- SQLite database for persistent storage
- Multi-user human annotation support
- CLI and GUI interfaces
"""

from .agent.fact_checker_agent import FactCheckerAgent
from .db.database import (
    FactCheckerDB,
    Statement,
    Annotator,
    AIEvaluation,
    Evidence,
    HumanAnnotation
)

__all__ = [
    'FactCheckerAgent',
    'FactCheckerDB',
    'Statement',
    'Annotator',
    'AIEvaluation',
    'Evidence',
    'HumanAnnotation'
]
