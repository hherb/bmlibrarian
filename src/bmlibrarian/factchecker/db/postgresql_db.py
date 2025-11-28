"""
PostgreSQL implementation wrapper for fact-checker database.

This module wraps the existing FactCheckerDB to conform to the
AbstractFactCheckerDB interface, enabling seamless switching between
PostgreSQL and SQLite backends.
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import asdict

from .abstract_db import (
    AbstractFactCheckerDB, Statement, Annotator, HumanAnnotation
)
from .database import FactCheckerDB as BaseFactCheckerDB

logger = logging.getLogger(__name__)


class PostgreSQLFactCheckerDB(AbstractFactCheckerDB):
    """
    PostgreSQL implementation of fact-checker database operations.

    This wrapper delegates to the existing FactCheckerDB class while
    implementing the AbstractFactCheckerDB interface for compatibility
    with the database abstraction layer.
    """

    def __init__(self):
        """Initialize PostgreSQL database connection."""
        self.db = BaseFactCheckerDB()
        logger.info("PostgreSQL database initialized")

    @property
    def db_manager(self):
        """
        Provide access to the underlying database manager.

        This property delegates to the wrapped FactCheckerDB's db_manager,
        allowing direct database access when needed (e.g., for custom queries).
        """
        return self.db.db_manager

    def get_all_statements_with_evaluations(self) -> List[Dict[str, Any]]:
        """
        Get all statements with their latest AI evaluations and evidence.

        Returns:
            List of dictionaries containing complete statement data
        """
        return self.db.get_all_statements_with_evaluations()

    def insert_human_annotation(self, annotation: HumanAnnotation) -> int:
        """
        Insert or update a human annotation.

        Args:
            annotation: HumanAnnotation object

        Returns:
            Annotation ID
        """
        return self.db.insert_human_annotation(annotation)

    def get_human_annotations(self, statement_id: int) -> List[HumanAnnotation]:
        """
        Get all human annotations for a statement.

        Args:
            statement_id: Statement ID

        Returns:
            List of HumanAnnotation objects
        """
        return self.db.get_human_annotations(statement_id)

    def insert_or_get_annotator(self, annotator: Annotator) -> int:
        """
        Insert a new annotator or return existing ID.

        Args:
            annotator: Annotator object

        Returns:
            Annotator ID
        """
        return self.db.insert_or_get_annotator(annotator)

    def get_annotator(self, username: str) -> Optional[Annotator]:
        """
        Get an annotator by username.

        Args:
            username: Annotator username

        Returns:
            Annotator object or None if not found
        """
        return self.db.get_annotator(username)

    def get_document_abstract(self, document_id: int) -> Optional[str]:
        """
        Get full abstract text for a document.

        This queries the public.document table in PostgreSQL.

        Args:
            document_id: Document ID

        Returns:
            Full abstract text or None if not found
        """
        # Query public.document table directly
        with self.db.db_manager.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT abstract FROM document WHERE id = %s",
                    (document_id,)
                )
                result = cursor.fetchone()
                return result[0] if result else None

    def get_document_metadata(self, document_id: int) -> Optional[Dict[str, Any]]:
        """
        Get document metadata (title, pmid, doi, etc.).

        This queries the public.document table in PostgreSQL.

        Args:
            document_id: Document ID

        Returns:
            Dictionary with document metadata or None if not found
        """
        with self.db.db_manager.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """SELECT id, title, external_id, doi, source_id
                       FROM document WHERE id = %s""",
                    (document_id,)
                )
                result = cursor.fetchone()
                if result:
                    doc_id, title, external_id, doi, source_id = result
                    # For PubMed (source_id=1), external_id is the PMID
                    pmid = external_id if source_id == 1 else None
                    return {
                        'id': doc_id,
                        'title': title,
                        'pmid': f"PMID:{pmid}" if pmid else '',
                        'doi': f"DOI:{doi}" if doi else '',
                        'external_id': external_id
                    }
                return None

    def calculate_statistics(self) -> Dict[str, Any]:
        """
        Calculate review statistics.

        Returns:
            Dictionary with statistics
        """
        with self.db.db_manager.get_connection() as conn:
            with conn.cursor() as cursor:
                stats = {}

                # Total statements
                cursor.execute("SELECT COUNT(*) FROM factcheck.statements")
                stats['total_statements'] = cursor.fetchone()[0]

                # AI evaluated count
                cursor.execute("SELECT COUNT(DISTINCT statement_id) FROM factcheck.ai_evaluations")
                stats['ai_evaluated_count'] = cursor.fetchone()[0]

                # Human annotated count
                cursor.execute("SELECT COUNT(DISTINCT statement_id) FROM factcheck.human_annotations")
                stats['human_annotated_count'] = cursor.fetchone()[0]

                # Evidence count
                cursor.execute("SELECT COUNT(*) FROM factcheck.evidence")
                stats['evidence_count'] = cursor.fetchone()[0]

                # Document count (documents referenced in evidence)
                cursor.execute("""
                    SELECT COUNT(DISTINCT document_id)
                    FROM factcheck.evidence
                """)
                stats['documents_count'] = cursor.fetchone()[0]

                return stats

    def get_database_info(self) -> Dict[str, Any]:
        """
        Get information about the database backend.

        Returns:
            Dictionary with database information
        """
        with self.db.db_manager.get_connection() as conn:
            with conn.cursor() as cursor:
                # Get PostgreSQL version
                cursor.execute("SELECT version()")
                pg_version = cursor.fetchone()[0]

                # Get connection info
                cursor.execute("SELECT current_database(), current_user")
                db_name, db_user = cursor.fetchone()

                return {
                    'type': 'postgresql',
                    'path': f"postgresql://{db_user}@.../{db_name}",  # Sanitized connection string
                    'version': pg_version,
                    'metadata': {
                        'database': db_name,
                        'user': db_user
                    }
                }

    def close(self):
        """Close database connections and clean up resources."""
        # The centralized DatabaseManager handles connection pooling,
        # so we don't need to explicitly close connections here
        logger.info("PostgreSQL database cleanup complete")
