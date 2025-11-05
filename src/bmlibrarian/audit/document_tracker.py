"""
Document Tracker for managing query results, document scores, and processing status.

Provides critical resumption functionality by tracking which documents have
already been scored for a research question.
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
import psycopg
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)


class DocumentTracker:
    """
    Tracks documents discovered, scored, and processed for research questions.

    Provides methods for:
    - Recording query → document relationships
    - Recording document relevance scores
    - Checking if document already scored (resumption)
    - Getting unscored documents
    - Querying document processing status
    """

    def __init__(self, conn: psycopg.Connection):
        """
        Initialize document tracker.

        Args:
            conn: Active psycopg connection to PostgreSQL database
        """
        self.conn = conn

    def record_query_documents(
        self,
        research_question_id: int,
        query_id: int,
        document_ids: List[int]
    ) -> None:
        """
        Record which documents were found by a query.

        Args:
            research_question_id: ID of the research question
            query_id: ID of the generated query
            document_ids: List of document IDs found
        """
        if not document_ids:
            return

        with self.conn.cursor() as cur:
            # Prepare batch insert data
            insert_data = [
                (research_question_id, query_id, doc_id, rank)
                for rank, doc_id in enumerate(document_ids, 1)
            ]

            # Batch insert with ON CONFLICT DO NOTHING (avoid duplicates)
            cur.executemany("""
                INSERT INTO audit.query_documents (
                    research_question_id, query_id, document_id, rank_in_results
                ) VALUES (%s, %s, %s, %s)
                ON CONFLICT (query_id, document_id) DO NOTHING
            """, insert_data)

            self.conn.commit()
            logger.debug(f"Recorded {len(document_ids)} documents for query {query_id}")

    def is_document_scored(
        self,
        research_question_id: int,
        document_id: int,
        evaluator_id: int
    ) -> bool:
        """
        Check if document already scored for this research question BY THIS EVALUATOR.

        CRITICAL for resumption - avoids re-scoring same documents with same evaluator.

        Args:
            research_question_id: ID of the research question
            document_id: ID of the document
            evaluator_id: ID of the evaluator (from public.evaluators)

        Returns:
            True if already scored by this evaluator, False otherwise
        """
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT audit.is_document_scored(%s, %s, %s)",
                (research_question_id, document_id, evaluator_id)
            )
            return cur.fetchone()[0]

    def get_unscored_documents(
        self,
        research_question_id: int,
        evaluator_id: int
    ) -> List[int]:
        """
        Get list of document IDs that need scoring BY THIS EVALUATOR.

        CRITICAL for resumption - only process documents not yet scored by this evaluator.

        Args:
            research_question_id: ID of the research question
            evaluator_id: ID of the evaluator (from public.evaluators)

        Returns:
            List of document IDs that haven't been scored by this evaluator yet
        """
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM audit.get_unscored_document_ids(%s, %s)",
                (research_question_id, evaluator_id)
            )
            return [row[0] for row in cur.fetchall()]

    def record_document_score(
        self,
        research_question_id: int,
        document_id: int,
        session_id: int,
        first_query_id: int,
        evaluator_id: int,
        relevance_score: int,
        reasoning: Optional[str] = None
    ) -> int:
        """
        Record a document relevance score.

        Uses ON CONFLICT to handle deduplication - only ONE score per
        research_question_id + document_id + evaluator_id combination.

        Args:
            research_question_id: ID of the research question
            document_id: ID of the document
            session_id: ID of the session
            first_query_id: ID of the query that first found this document
            evaluator_id: ID of the evaluator (from public.evaluators)
            relevance_score: Relevance score (0-5)
            reasoning: Optional explanation for score

        Returns:
            scoring_id (BIGINT)
        """
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO audit.document_scores (
                    research_question_id, document_id, session_id, first_query_id,
                    evaluator_id, relevance_score, reasoning
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (research_question_id, document_id, evaluator_id) DO UPDATE
                SET relevance_score = EXCLUDED.relevance_score,
                    reasoning = EXCLUDED.reasoning,
                    last_updated_at = NOW()
                RETURNING scoring_id
            """, (
                research_question_id, document_id, session_id, first_query_id,
                evaluator_id, relevance_score, reasoning
            ))
            scoring_id = cur.fetchone()[0]
            self.conn.commit()

            logger.debug(f"Recorded score {relevance_score} for document {document_id} by evaluator {evaluator_id}, scoring_id={scoring_id}")
            return scoring_id

    def update_score(
        self,
        scoring_id: int,
        new_score: int,
        new_reasoning: Optional[str] = None
    ) -> None:
        """
        Update an existing score (e.g., after human review).

        Args:
            scoring_id: ID of the scoring record
            new_score: Updated relevance score (0-5)
            new_reasoning: Optional updated reasoning
        """
        with self.conn.cursor() as cur:
            if new_reasoning:
                cur.execute("""
                    UPDATE audit.document_scores
                    SET relevance_score = %s,
                        reasoning = %s,
                        last_updated_at = NOW()
                    WHERE scoring_id = %s
                """, (new_score, new_reasoning, scoring_id))
            else:
                cur.execute("""
                    UPDATE audit.document_scores
                    SET relevance_score = %s,
                        last_updated_at = NOW()
                    WHERE scoring_id = %s
                """, (new_score, scoring_id))
            self.conn.commit()

            logger.info(f"Updated scoring {scoring_id}: new score={new_score}")

    def get_document_score(
        self,
        research_question_id: int,
        document_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get existing score for a document.

        Args:
            research_question_id: ID of the research question
            document_id: ID of the document

        Returns:
            Dictionary with scoring data, or None if not scored
        """
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT * FROM audit.document_scores
                WHERE research_question_id = %s AND document_id = %s
            """, (research_question_id, document_id))
            return cur.fetchone()

    def get_high_scoring_documents(
        self,
        research_question_id: int,
        min_score: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Get all documents with score >= min_score.

        Args:
            research_question_id: ID of the research question
            min_score: Minimum relevance score (default: 3)

        Returns:
            List of dictionaries with scoring data
        """
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT * FROM audit.document_scores
                WHERE research_question_id = %s
                  AND relevance_score >= %s
                ORDER BY relevance_score DESC, scored_at ASC
            """, (research_question_id, min_score))
            return cur.fetchall()

    def get_document_processing_status(
        self,
        research_question_id: int
    ) -> List[Dict[str, Any]]:
        """
        Get processing status for all documents.

        Uses the v_document_processing_status view to show which documents
        have been discovered, scored, and had citations extracted.

        Args:
            research_question_id: ID of the research question

        Returns:
            List of dictionaries with processing status
        """
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT * FROM audit.v_document_processing_status
                WHERE research_question_id = %s
                ORDER BY discovered_at DESC
            """, (research_question_id,))
            return cur.fetchall()

    def count_documents_by_score(
        self,
        research_question_id: int
    ) -> Dict[int, int]:
        """
        Get count of documents for each score (0-5).

        Useful for reporting statistics.

        Args:
            research_question_id: ID of the research question

        Returns:
            Dictionary mapping score -> count
        """
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT relevance_score, COUNT(*) as count
                FROM audit.document_scores
                WHERE research_question_id = %s
                GROUP BY relevance_score
                ORDER BY relevance_score DESC
            """, (research_question_id,))

            result = {score: 0 for score in range(6)}  # Initialize all scores to 0
            for row in cur.fetchall():
                result[row[0]] = row[1]

            return result
