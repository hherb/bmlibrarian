"""
Citation Tracker for managing extracted citations and human review.

Tracks all citations extracted from documents, enabling reuse across
sessions and tracking human review status.
"""

import logging
from typing import Optional, List, Dict, Any
import psycopg
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)


class CitationTracker:
    """
    Tracks citations extracted from documents for research questions.

    Provides methods for:
    - Recording extracted citations
    - Updating human review status
    - Getting accepted citations for reuse
    - Querying citations by document
    """

    def __init__(self, conn: psycopg.Connection):
        """
        Initialize citation tracker.

        Args:
            conn: Active psycopg connection to PostgreSQL database
        """
        self.conn = conn

    def record_citation(
        self,
        research_question_id: int,
        document_id: int,
        session_id: int,
        scoring_id: int,
        evaluator_id: int,
        passage: str,
        summary: str,
        relevance_confidence: Optional[float] = None
    ) -> int:
        """
        Record an extracted citation.

        Args:
            research_question_id: ID of the research question
            document_id: ID of the source document
            session_id: ID of the session
            scoring_id: ID of the document score that triggered extraction
            evaluator_id: ID of the evaluator (from public.evaluators) that extracted this
            passage: Extracted passage text
            summary: AI-generated summary
            relevance_confidence: Optional confidence score (0.0-1.0)

        Returns:
            citation_id (BIGINT)
        """
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO audit.extracted_citations (
                    research_question_id, document_id, session_id, scoring_id,
                    evaluator_id, passage, summary, relevance_confidence
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING citation_id
            """, (
                research_question_id, document_id, session_id, scoring_id,
                evaluator_id, passage, summary, relevance_confidence
            ))
            citation_id = cur.fetchone()[0]
            self.conn.commit()

            logger.debug(f"Recorded citation {citation_id} from document {document_id} by evaluator {evaluator_id}")
            return citation_id

    def update_human_review_status(
        self,
        citation_id: int,
        status: str
    ) -> None:
        """
        Update human review status for a citation.

        Args:
            citation_id: ID of the citation
            status: Review status ('accepted', 'rejected', 'modified')
        """
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE audit.extracted_citations
                SET human_review_status = %s
                WHERE citation_id = %s
            """, (status, citation_id))
            self.conn.commit()

            logger.info(f"Updated citation {citation_id} review status: {status}")

    def get_accepted_citations(
        self,
        research_question_id: int
    ) -> List[Dict[str, Any]]:
        """
        Get all accepted citations for a research question.

        Useful for reusing citations across sessions.

        Args:
            research_question_id: ID of the research question

        Returns:
            List of dictionaries with citation data
        """
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT * FROM audit.extracted_citations
                WHERE research_question_id = %s
                  AND human_review_status = 'accepted'
                ORDER BY extracted_at
            """, (research_question_id,))
            return cur.fetchall()

    def get_all_citations(
        self,
        research_question_id: int,
        session_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all citations for a research question.

        Args:
            research_question_id: ID of the research question
            session_id: Optional filter by session

        Returns:
            List of dictionaries with citation data
        """
        with self.conn.cursor(row_factory=dict_row) as cur:
            if session_id is not None:
                cur.execute("""
                    SELECT * FROM audit.extracted_citations
                    WHERE research_question_id = %s AND session_id = %s
                    ORDER BY extracted_at
                """, (research_question_id, session_id))
            else:
                cur.execute("""
                    SELECT * FROM audit.extracted_citations
                    WHERE research_question_id = %s
                    ORDER BY extracted_at
                """, (research_question_id,))

            return cur.fetchall()

    def get_citations_for_document(
        self,
        research_question_id: int,
        document_id: int
    ) -> List[Dict[str, Any]]:
        """
        Get all citations extracted from a specific document.

        Args:
            research_question_id: ID of the research question
            document_id: ID of the document

        Returns:
            List of dictionaries with citation data
        """
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT * FROM audit.extracted_citations
                WHERE research_question_id = %s AND document_id = %s
                ORDER BY extracted_at
            """, (research_question_id, document_id))
            return cur.fetchall()

    def count_citations(
        self,
        research_question_id: int,
        by_status: bool = True
    ) -> Dict[str, int]:
        """
        Count citations by review status.

        Args:
            research_question_id: ID of the research question
            by_status: If True, group by review status

        Returns:
            Dictionary with counts
        """
        if by_status:
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        COALESCE(human_review_status, 'unreviewed') as status,
                        COUNT(*) as count
                    FROM audit.extracted_citations
                    WHERE research_question_id = %s
                    GROUP BY human_review_status
                """, (research_question_id,))

                result = {'accepted': 0, 'rejected': 0, 'modified': 0, 'unreviewed': 0}
                for row in cur.fetchall():
                    result[row[0]] = row[1]

                return result
        else:
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) as total
                    FROM audit.extracted_citations
                    WHERE research_question_id = %s
                """, (research_question_id,))

                return {'total': cur.fetchone()[0]}

    def get_citation_info(
        self,
        citation_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get full information about a citation.

        Args:
            citation_id: ID of the citation

        Returns:
            Dictionary with citation data, or None if not found
        """
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT * FROM audit.extracted_citations
                WHERE citation_id = %s
            """, (citation_id,))
            return cur.fetchone()
