"""
Abstract database interface for Fact Checker.

Defines the common interface that both PostgreSQL and SQLite implementations
must provide, enabling the GUI and scripts to work with either backend.
"""

import json
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Characters of an unreadable stored value quoted in a log message.
UNREADABLE_VALUE_LOGGED_CHARS = 100


def parse_degradation_notes(value: Any) -> Optional[List[str]]:
    """
    Read a stored ``degradation_notes`` value (evidence a verdict could not examine).

    Args:
        value: The column value: a list (PostgreSQL JSONB), a JSON string
            (SQLite), or None.

    Returns:
        The notes as a list of strings, or None if there are none or the
        value is not a JSON list.
    """
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            logger.warning(
                f"Ignoring unreadable degradation_notes: "
                f"{value[:UNREADABLE_VALUE_LOGGED_CHARS]!r}"
            )
            return None
    if not isinstance(value, list) or not value:
        return None
    return [str(note) for note in value]


@dataclass
class Statement:
    """Represents a biomedical statement to be fact-checked."""
    statement_id: Optional[int] = None
    statement_text: str = ""
    input_statement_id: Optional[str] = None
    expected_answer: Optional[str] = None
    created_at: Optional[str] = None
    source_file: Optional[str] = None
    review_status: str = "pending"


@dataclass
class Annotator:
    """Represents a human annotator."""
    annotator_id: Optional[int] = None
    username: str = ""
    full_name: Optional[str] = None
    email: Optional[str] = None
    expertise_level: Optional[str] = None
    institution: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class HumanAnnotation:
    """Represents a human reviewer's annotation."""
    annotation_id: Optional[int] = None
    statement_id: int = 0
    annotator_id: int = 0
    annotation: str = ""
    explanation: Optional[str] = None
    confidence: Optional[str] = None
    review_duration_seconds: Optional[int] = None
    review_date: Optional[str] = None
    session_id: Optional[str] = None


class AbstractFactCheckerDB(ABC):
    """
    Abstract base class for fact-checker database operations.

    This interface defines the common operations needed by the GUI and scripts,
    allowing seamless switching between PostgreSQL (main database) and SQLite
    (portable review packages).
    """

    @abstractmethod
    def get_all_statements_with_evaluations(self) -> List[Dict[str, Any]]:
        """
        Get all statements with their latest AI evaluations and evidence.

        Returns:
            List of dictionaries containing statement, evaluation, and evidence data.
            Each dictionary should have the structure:
            {
                'id': statement_id,
                'statement_text': str,
                'input_statement_id': str,
                'expected_answer': str,
                'created_at': str,
                'source_file': str,
                'review_status': str,
                'eval_id': evaluation_id,
                'evaluation': str,
                'reason': str,
                'confidence': str,
                'documents_reviewed': int,
                'supporting_citations': int,
                'contradicting_citations': int,
                'neutral_citations': int,
                'matches_expected': bool,
                'model_used': str,
                'evidence': List[Dict],  # List of evidence dictionaries
                'human_annotations': List[Dict]  # List of human annotation dictionaries
            }
        """
        pass

    @abstractmethod
    def insert_human_annotation(self, annotation: HumanAnnotation) -> int:
        """
        Insert or update a human annotation.

        Args:
            annotation: HumanAnnotation object

        Returns:
            Annotation ID
        """
        pass

    @abstractmethod
    def get_human_annotations(self, statement_id: int) -> List[HumanAnnotation]:
        """
        Get all human annotations for a statement.

        Args:
            statement_id: Statement ID

        Returns:
            List of HumanAnnotation objects
        """
        pass

    @abstractmethod
    def insert_or_get_annotator(self, annotator: Annotator) -> int:
        """
        Insert a new annotator or return existing ID.

        Args:
            annotator: Annotator object

        Returns:
            Annotator ID
        """
        pass

    @abstractmethod
    def get_annotator(self, username: str) -> Optional[Annotator]:
        """
        Get an annotator by username.

        Args:
            username: Annotator username

        Returns:
            Annotator object or None if not found
        """
        pass

    @abstractmethod
    def get_document_abstract(self, document_id: int) -> Optional[str]:
        """
        Get full abstract text for a document.

        Args:
            document_id: Document ID

        Returns:
            Full abstract text or None if not found
        """
        pass

    @abstractmethod
    def get_document_metadata(self, document_id: int) -> Optional[Dict[str, Any]]:
        """
        Get document metadata (title, pmid, doi, etc.).

        Args:
            document_id: Document ID

        Returns:
            Dictionary with keys: id, title, pmid, doi, external_id
            or None if not found
        """
        pass

    @abstractmethod
    def get_document_details(self, document_id: int) -> Optional[Dict[str, Any]]:
        """
        Get full display metadata for a document (citation cards, enrichment).

        Args:
            document_id: Document ID

        Returns:
            Dictionary with at least these keys (a subset of
            ``bmlibrarian.database.get_document_details``'s): id, title,
            abstract, authors_list, journal, year, publication_date, doi,
            pmid (None when no PMID is known), external_id, pdf_url,
            pdf_filename. None if the document is not found.

        Raises:
            Exception: On database errors. Implementations must not report a
                failed lookup as a missing document.
        """
        pass

    @abstractmethod
    def calculate_statistics(self) -> Dict[str, Any]:
        """
        Calculate review statistics.

        Returns:
            Dictionary with statistics including:
            - total_statements: Total number of statements
            - ai_evaluated_count: Number with AI evaluations
            - human_annotated_count: Number with human annotations
            - etc.
        """
        pass

    @abstractmethod
    def get_database_info(self) -> Dict[str, Any]:
        """
        Get information about the database backend.

        Returns:
            Dictionary with keys:
            - type: 'postgresql' or 'sqlite'
            - path: Database file path (SQLite) or connection string (PostgreSQL)
            - version: Database/schema version
            - metadata: Additional backend-specific metadata
        """
        pass

    @abstractmethod
    def close(self):
        """Close database connections and clean up resources."""
        pass
