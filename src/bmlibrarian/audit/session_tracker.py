"""
Session Tracker for managing research questions and sessions.

Handles creation and resumption of research questions and sessions,
enabling users to continue work from where they left off.
"""

import hashlib
import logging
from typing import Optional, Dict, Any
from datetime import datetime
import psycopg
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)


class SessionTracker:
    """
    Tracks research questions and sessions in the audit schema.

    Provides methods for:
    - Getting or creating research questions (with deduplication)
    - Starting new sessions
    - Resuming existing sessions
    - Querying session status
    """

    def __init__(self, conn: psycopg.Connection):
        """
        Initialize session tracker.

        Args:
            conn: Active psycopg connection to PostgreSQL database
        """
        self.conn = conn

    def get_or_create_research_question(
        self,
        question_text: str,
        user_id: Optional[int] = None
    ) -> int:
        """
        Get existing or create new research question.

        Uses question hash for deduplication - identical questions return
        same research_question_id.

        Args:
            question_text: The research question text
            user_id: Optional user ID

        Returns:
            research_question_id (BIGINT)
        """
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT audit.get_or_create_research_question(%s, %s)",
                (question_text, user_id)
            )
            result = cur.fetchone()
            self.conn.commit()
            return result[0]

    def start_session(
        self,
        research_question_id: int,
        session_type: str = 'initial',
        config_snapshot: Optional[Dict[str, Any]] = None,
        user_notes: Optional[str] = None
    ) -> int:
        """
        Start a new research session.

        Args:
            research_question_id: ID of the research question
            session_type: Type of session ('initial', 'expansion', 'reanalysis', 'counterfactual_only')
            config_snapshot: Configuration at session start (JSONB)
            user_notes: Optional notes about why this session was started

        Returns:
            session_id (BIGINT)
        """
        import json

        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO audit.research_sessions (
                    research_question_id, session_type, config_snapshot, user_notes
                ) VALUES (%s, %s, %s, %s)
                RETURNING session_id
            """, (
                research_question_id,
                session_type,
                json.dumps(config_snapshot) if config_snapshot else None,
                user_notes
            ))
            session_id = cur.fetchone()[0]
            self.conn.commit()

            logger.info(f"Started session {session_id} for research question {research_question_id} (type: {session_type})")
            return session_id

    def complete_session(
        self,
        session_id: int,
        status: str = 'completed'
    ) -> None:
        """
        Mark a session as completed, failed, or cancelled.

        Args:
            session_id: ID of the session
            status: Final status ('completed', 'failed', 'cancelled')
        """
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE audit.research_sessions
                SET completed_at = NOW(),
                    workflow_status = %s
                WHERE session_id = %s
            """, (status, session_id))
            self.conn.commit()

            logger.info(f"Completed session {session_id} with status: {status}")

    def get_latest_session(
        self,
        research_question_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get the most recent session for a research question.

        Args:
            research_question_id: ID of the research question

        Returns:
            Dictionary with session data, or None if no sessions exist
        """
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT * FROM audit.v_latest_sessions
                WHERE research_question_id = %s
            """, (research_question_id,))
            return cur.fetchone()

    def find_research_question(
        self,
        question_text: str
    ) -> Optional[int]:
        """
        Find existing research question ID by text.

        Args:
            question_text: The research question text

        Returns:
            research_question_id if found, None otherwise
        """
        question_hash = hashlib.md5(question_text.lower().strip().encode()).hexdigest()

        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT research_question_id
                FROM audit.research_questions
                WHERE question_hash = %s
            """, (question_hash,))
            result = cur.fetchone()
            return result[0] if result else None

    def get_research_question_info(
        self,
        research_question_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get full information about a research question.

        Args:
            research_question_id: ID of the research question

        Returns:
            Dictionary with question data, or None if not found
        """
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT * FROM audit.research_questions
                WHERE research_question_id = %s
            """, (research_question_id,))
            return cur.fetchone()

    def get_session_info(
        self,
        session_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get full information about a session.

        Args:
            session_id: ID of the session

        Returns:
            Dictionary with session data, or None if not found
        """
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT * FROM audit.research_sessions
                WHERE session_id = %s
            """, (session_id,))
            return cur.fetchone()

    def list_recent_questions(
        self,
        limit: int = 10,
        user_id: Optional[int] = None,
        status: str = 'active'
    ) -> list[Dict[str, Any]]:
        """
        List recent research questions.

        Args:
            limit: Maximum number of questions to return
            user_id: Filter by user ID (None = all users)
            status: Filter by status ('active', 'archived', 'superseded')

        Returns:
            List of dictionaries with question data
        """
        with self.conn.cursor(row_factory=dict_row) as cur:
            if user_id is not None:
                cur.execute("""
                    SELECT * FROM audit.research_questions
                    WHERE user_id = %s AND status = %s
                    ORDER BY last_activity_at DESC
                    LIMIT %s
                """, (user_id, status, limit))
            else:
                cur.execute("""
                    SELECT * FROM audit.research_questions
                    WHERE status = %s
                    ORDER BY last_activity_at DESC
                    LIMIT %s
                """, (status, limit))

            return cur.fetchall()

    def archive_research_question(
        self,
        research_question_id: int
    ) -> None:
        """
        Archive a research question (set status to 'archived').

        Args:
            research_question_id: ID of the research question
        """
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE audit.research_questions
                SET status = 'archived'
                WHERE research_question_id = %s
            """, (research_question_id,))
            self.conn.commit()

            logger.info(f"Archived research question {research_question_id}")
