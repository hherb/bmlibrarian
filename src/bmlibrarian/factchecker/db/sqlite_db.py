"""
SQLite implementation of fact-checker database for portable review packages.

This module provides a SQLite backend for the fact-checker review GUI,
enabling distribution of self-contained review packages without PostgreSQL dependency.
"""

import sqlite3
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import asdict
from datetime import datetime

from .abstract_db import (
    AbstractFactCheckerDB, Statement, Annotator, HumanAnnotation
)

logger = logging.getLogger(__name__)


class SQLiteFactCheckerDB(AbstractFactCheckerDB):
    """
    SQLite implementation of fact-checker database operations.

    Provides a portable, self-contained database for reviewing fact-check
    results without requiring PostgreSQL. Designed for distribution to
    external reviewers.
    """

    def __init__(self, db_path: str):
        """
        Initialize SQLite database connection.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(f"SQLite database not found: {db_path}")

        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row  # Access columns by name

        # Enable foreign keys (SQLite default is OFF!)
        self.conn.execute("PRAGMA foreign_keys = ON")

        # Use WAL mode for better concurrency
        self.conn.execute("PRAGMA journal_mode = WAL")

        logger.info(f"SQLite database opened: {db_path}")

    def get_all_statements_with_evaluations(self) -> List[Dict[str, Any]]:
        """
        Get all statements with their latest AI evaluations and evidence.

        Returns:
            List of dictionaries containing complete statement data
        """
        cursor = self.conn.cursor()

        # Query statements with their latest AI evaluations
        cursor.execute("""
            SELECT
                s.statement_id as id,
                s.statement_text,
                s.input_statement_id,
                s.expected_answer,
                s.created_at,
                s.source_file,
                s.review_status,
                ae.evaluation_id as eval_id,
                ae.evaluation,
                ae.reason,
                ae.confidence,
                ae.documents_reviewed,
                ae.supporting_citations,
                ae.contradicting_citations,
                ae.neutral_citations,
                ae.matches_expected,
                ae.model_used
            FROM statements s
            LEFT JOIN ai_evaluations ae ON s.statement_id = ae.statement_id
            LEFT JOIN (
                SELECT statement_id, MAX(version) as max_version
                FROM ai_evaluations
                GROUP BY statement_id
            ) latest ON ae.statement_id = latest.statement_id AND ae.version = latest.max_version
            ORDER BY s.statement_id
        """)

        results = []
        for row in cursor.fetchall():
            row_dict = {
                'id': row['id'],
                'statement_text': row['statement_text'],
                'input_statement_id': row['input_statement_id'],
                'expected_answer': row['expected_answer'],
                'created_at': row['created_at'],
                'source_file': row['source_file'],
                'review_status': row['review_status'],
                'eval_id': row['eval_id'],
                'evaluation': row['evaluation'],
                'reason': row['reason'],
                'confidence': row['confidence'],
                'documents_reviewed': row['documents_reviewed'],
                'supporting_citations': row['supporting_citations'],
                'contradicting_citations': row['contradicting_citations'],
                'neutral_citations': row['neutral_citations'],
                'matches_expected': bool(row['matches_expected']) if row['matches_expected'] is not None else None,
                'model_used': row['model_used']
            }

            # Get evidence if evaluation exists
            if row_dict['eval_id']:
                row_dict['evidence'] = self._get_evidence_for_evaluation(row_dict['eval_id'])
            else:
                row_dict['evidence'] = []

            # Get human annotations
            row_dict['human_annotations'] = self._get_human_annotations_dict(row_dict['id'])

            results.append(row_dict)

        return results

    def _get_evidence_for_evaluation(self, evaluation_id: int) -> List[Dict[str, Any]]:
        """Get evidence for an AI evaluation."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT
                evidence_id, evaluation_id, citation_text, document_id,
                pmid, doi, relevance_score, supports_statement, created_at
            FROM evidence
            WHERE evaluation_id = ?
        """, (evaluation_id,))

        evidence_list = []
        for row in cursor.fetchall():
            evidence_list.append({
                'evidence_id': row['evidence_id'],
                'evaluation_id': row['evaluation_id'],
                'citation_text': row['citation_text'],
                'document_id': row['document_id'],
                'pmid': row['pmid'],
                'doi': row['doi'],
                'relevance_score': row['relevance_score'],
                'supports_statement': row['supports_statement'],
                'created_at': row['created_at']
            })

        return evidence_list

    def _get_human_annotations_dict(self, statement_id: int) -> List[Dict[str, Any]]:
        """Get human annotations as dictionaries."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT
                annotation_id, statement_id, annotator_id, annotation,
                explanation, confidence, review_duration_seconds,
                review_date, session_id
            FROM human_annotations
            WHERE statement_id = ?
        """, (statement_id,))

        annotations = []
        for row in cursor.fetchall():
            annotations.append({
                'annotation_id': row['annotation_id'],
                'statement_id': row['statement_id'],
                'annotator_id': row['annotator_id'],
                'annotation': row['annotation'],
                'explanation': row['explanation'],
                'confidence': row['confidence'],
                'review_duration_seconds': row['review_duration_seconds'],
                'review_date': row['review_date'],
                'session_id': row['session_id']
            })

        return annotations

    def insert_human_annotation(self, annotation: HumanAnnotation) -> int:
        """
        Insert or update a human annotation.

        Args:
            annotation: HumanAnnotation object

        Returns:
            Annotation ID
        """
        cursor = self.conn.cursor()

        # Upsert using INSERT OR REPLACE
        cursor.execute("""
            INSERT INTO human_annotations (
                statement_id, annotator_id, annotation, explanation, confidence,
                review_duration_seconds, review_date, session_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (statement_id, annotator_id)
            DO UPDATE SET
                annotation = excluded.annotation,
                explanation = excluded.explanation,
                confidence = excluded.confidence,
                review_duration_seconds = excluded.review_duration_seconds,
                review_date = datetime('now'),
                session_id = excluded.session_id
        """, (
            annotation.statement_id,
            annotation.annotator_id,
            annotation.annotation,
            annotation.explanation,
            annotation.confidence,
            annotation.review_duration_seconds,
            annotation.review_date or datetime.now().isoformat(),
            annotation.session_id
        ))

        self.conn.commit()

        # Get the annotation_id
        cursor.execute("""
            SELECT annotation_id FROM human_annotations
            WHERE statement_id = ? AND annotator_id = ?
        """, (annotation.statement_id, annotation.annotator_id))

        result = cursor.fetchone()
        return result['annotation_id'] if result else None

    def get_human_annotations(self, statement_id: int) -> List[HumanAnnotation]:
        """
        Get all human annotations for a statement.

        Args:
            statement_id: Statement ID

        Returns:
            List of HumanAnnotation objects
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT
                annotation_id, statement_id, annotator_id, annotation,
                explanation, confidence, review_duration_seconds,
                review_date, session_id
            FROM human_annotations
            WHERE statement_id = ?
        """, (statement_id,))

        annotations = []
        for row in cursor.fetchall():
            annotations.append(HumanAnnotation(
                annotation_id=row['annotation_id'],
                statement_id=row['statement_id'],
                annotator_id=row['annotator_id'],
                annotation=row['annotation'],
                explanation=row['explanation'],
                confidence=row['confidence'],
                review_duration_seconds=row['review_duration_seconds'],
                review_date=row['review_date'],
                session_id=row['session_id']
            ))

        return annotations

    def insert_or_get_annotator(self, annotator: Annotator) -> int:
        """
        Insert a new annotator or return existing ID.

        Args:
            annotator: Annotator object

        Returns:
            Annotator ID
        """
        cursor = self.conn.cursor()

        # Try to get existing annotator
        cursor.execute("""
            SELECT annotator_id FROM annotators WHERE username = ?
        """, (annotator.username,))

        result = cursor.fetchone()
        if result:
            # Update existing annotator info
            cursor.execute("""
                UPDATE annotators SET
                    full_name = ?,
                    email = ?,
                    expertise_level = ?,
                    institution = ?
                WHERE annotator_id = ?
            """, (
                annotator.full_name,
                annotator.email,
                annotator.expertise_level,
                annotator.institution,
                result['annotator_id']
            ))
            self.conn.commit()
            return result['annotator_id']

        # Insert new annotator
        cursor.execute("""
            INSERT INTO annotators (username, full_name, email, expertise_level, institution, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            annotator.username,
            annotator.full_name,
            annotator.email,
            annotator.expertise_level,
            annotator.institution,
            datetime.now().isoformat()
        ))

        self.conn.commit()
        return cursor.lastrowid

    def get_annotator(self, username: str) -> Optional[Annotator]:
        """
        Get an annotator by username.

        Args:
            username: Annotator username

        Returns:
            Annotator object or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT annotator_id, username, full_name, email, expertise_level, institution, created_at
            FROM annotators
            WHERE username = ?
        """, (username,))

        row = cursor.fetchone()
        if row:
            return Annotator(
                annotator_id=row['annotator_id'],
                username=row['username'],
                full_name=row['full_name'],
                email=row['email'],
                expertise_level=row['expertise_level'],
                institution=row['institution'],
                created_at=row['created_at']
            )
        return None

    def get_document_abstract(self, document_id: int) -> Optional[str]:
        """
        Get full abstract text for a document.

        Args:
            document_id: Document ID

        Returns:
            Full abstract text or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT abstract FROM documents WHERE id = ?
        """, (document_id,))

        result = cursor.fetchone()
        return result['abstract'] if result else None

    def get_document_metadata(self, document_id: int) -> Optional[Dict[str, Any]]:
        """
        Get document metadata (title, pmid, doi, etc.).

        Args:
            document_id: Document ID

        Returns:
            Dictionary with document metadata or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, title, external_id, doi, source_id
            FROM documents
            WHERE id = ?
        """, (document_id,))

        result = cursor.fetchone()
        if result:
            # For PubMed (source_id=1), external_id is the PMID
            pmid = result['external_id'] if result['source_id'] == 1 else None
            return {
                'id': result['id'],
                'title': result['title'],
                'pmid': f"PMID:{pmid}" if pmid else '',
                'doi': f"DOI:{result['doi']}" if result['doi'] else '',
                'external_id': result['external_id']
            }
        return None

    def calculate_statistics(self) -> Dict[str, Any]:
        """
        Calculate review statistics.

        Returns:
            Dictionary with statistics
        """
        cursor = self.conn.cursor()

        stats = {}

        # Total statements
        cursor.execute("SELECT COUNT(*) as count FROM statements")
        stats['total_statements'] = cursor.fetchone()['count']

        # AI evaluated count
        cursor.execute("SELECT COUNT(DISTINCT statement_id) as count FROM ai_evaluations")
        stats['ai_evaluated_count'] = cursor.fetchone()['count']

        # Human annotated count
        cursor.execute("SELECT COUNT(DISTINCT statement_id) as count FROM human_annotations")
        stats['human_annotated_count'] = cursor.fetchone()['count']

        # Evidence count
        cursor.execute("SELECT COUNT(*) as count FROM evidence")
        stats['evidence_count'] = cursor.fetchone()['count']

        # Document count
        cursor.execute("SELECT COUNT(*) as count FROM documents")
        stats['documents_count'] = cursor.fetchone()['count']

        return stats

    def get_database_info(self) -> Dict[str, Any]:
        """
        Get information about the database backend.

        Returns:
            Dictionary with database information
        """
        cursor = self.conn.cursor()

        # Get package metadata if available
        cursor.execute("""
            SELECT
                export_date, source_database, postgresql_version,
                bmlibrarian_version, total_statements, total_evaluations,
                total_evidence, total_documents, exported_by, package_version
            FROM package_metadata
            LIMIT 1
        """)

        metadata_row = cursor.fetchone()
        metadata = {}
        if metadata_row:
            metadata = {
                'export_date': metadata_row['export_date'],
                'source_database': metadata_row['source_database'],
                'postgresql_version': metadata_row['postgresql_version'],
                'bmlibrarian_version': metadata_row['bmlibrarian_version'],
                'total_statements': metadata_row['total_statements'],
                'total_evaluations': metadata_row['total_evaluations'],
                'total_evidence': metadata_row['total_evidence'],
                'total_documents': metadata_row['total_documents'],
                'exported_by': metadata_row['exported_by'],
                'package_version': metadata_row['package_version']
            }

        # Get schema version
        cursor.execute("SELECT version, applied_at, description FROM schema_version ORDER BY version DESC LIMIT 1")
        schema_row = cursor.fetchone()
        schema_version = schema_row['version'] if schema_row else None

        return {
            'type': 'sqlite',
            'path': str(self.db_path),
            'version': schema_version,
            'metadata': metadata
        }

    def close(self):
        """Close database connection and clean up resources."""
        if self.conn:
            self.conn.close()
            logger.info(f"SQLite database closed: {self.db_path}")
