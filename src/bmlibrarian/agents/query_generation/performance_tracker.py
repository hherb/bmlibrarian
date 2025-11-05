"""Query performance tracker for multi-model query generation.

Tracks which models with which parameters found which documents,
enabling analysis of model performance over time.
"""

import sqlite3
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class QueryPerformanceStats:
    """Statistics for a single query's performance.

    Attributes:
        model: Model name used for query generation
        temperature: Temperature parameter used
        query: The generated SQL query
        total_documents: Total number of documents found
        unique_documents: Number of documents unique to this query
        high_scoring_documents: Number of documents with score >= threshold
        unique_high_scoring: Number of high-scoring docs unique to this query
        execution_time: Time to execute query (seconds)
    """
    model: str
    temperature: float
    query: str
    total_documents: int
    unique_documents: int
    high_scoring_documents: int
    unique_high_scoring: int
    execution_time: float


class QueryPerformanceTracker:
    """Tracks query-document relationships and model performance in SQLite.

    Uses a temporary SQLite database to track:
    - Which models found which documents
    - Model parameters (temperature, top_p, etc.)
    - Document scores for each query
    - Performance statistics over time
    """

    def __init__(self, db_path: Optional[str] = None):
        """Initialize the query performance tracker.

        Args:
            db_path: Path to SQLite database. If None, uses in-memory database.
        """
        if db_path is None:
            # Use in-memory database for temporary tracking
            self.db_path = ":memory:"
            self._persistent_conn = sqlite3.connect(self.db_path, check_same_thread=False)
        else:
            self.db_path = str(Path(db_path))
            self._persistent_conn = None

        self._init_database()

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        if self._persistent_conn:
            return self._persistent_conn
        return sqlite3.connect(self.db_path)

    def _init_database(self):
        """Initialize SQLite database with tracking tables."""
        conn = self._get_connection()
        needs_close = not self._persistent_conn

        try:
            # Table for query metadata
            conn.execute("""
                CREATE TABLE IF NOT EXISTS query_metadata (
                    query_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    model TEXT NOT NULL,
                    query_text TEXT NOT NULL,
                    temperature REAL NOT NULL,
                    top_p REAL,
                    attempt_number INTEGER NOT NULL,
                    execution_time REAL NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            # Table for query-document relationships
            conn.execute("""
                CREATE TABLE IF NOT EXISTS query_documents (
                    query_id TEXT NOT NULL,
                    document_id INTEGER NOT NULL,
                    document_score REAL,
                    PRIMARY KEY (query_id, document_id),
                    FOREIGN KEY (query_id) REFERENCES query_metadata(query_id)
                )
            """)

            # Indexes for performance
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_session_id
                ON query_metadata(session_id, created_at DESC)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_model
                ON query_metadata(model)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_document_id
                ON query_documents(document_id)
            """)

            conn.commit()
        finally:
            if needs_close:
                conn.close()

    def start_session(self, session_id: str) -> str:
        """Start a new tracking session.

        Args:
            session_id: Unique identifier for this session (e.g., research question hash)

        Returns:
            The session ID
        """
        logger.info(f"Started query performance tracking session: {session_id}")
        return session_id

    def track_query(
        self,
        query_id: str,
        session_id: str,
        model: str,
        query_text: str,
        temperature: float,
        top_p: float,
        attempt_number: int,
        execution_time: float,
        document_ids: List[int],
        document_scores: Optional[Dict[int, float]] = None
    ):
        """Track a query execution and its results.

        Args:
            query_id: Unique identifier for this query
            session_id: Session this query belongs to
            model: Model name used
            query_text: The SQL query text
            temperature: Temperature parameter
            top_p: Top-p parameter
            attempt_number: Which attempt (1, 2, 3)
            execution_time: Time to execute query (seconds)
            document_ids: List of document IDs found
            document_scores: Optional dict mapping document_id -> relevance_score
        """
        conn = self._get_connection()
        needs_close = not self._persistent_conn

        try:
            # Insert query metadata
            created_at = datetime.now(timezone.utc).isoformat()
            conn.execute("""
                INSERT INTO query_metadata (
                    query_id, session_id, model, query_text, temperature, top_p,
                    attempt_number, execution_time, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (query_id, session_id, model, query_text, temperature, top_p,
                  attempt_number, execution_time, created_at))

            # Insert query-document relationships
            if document_ids:
                relationships = []
                for doc_id in document_ids:
                    score = document_scores.get(doc_id) if document_scores else None
                    relationships.append((query_id, doc_id, score))

                conn.executemany("""
                    INSERT INTO query_documents (query_id, document_id, document_score)
                    VALUES (?, ?, ?)
                """, relationships)

            conn.commit()
            logger.debug(f"Tracked query {query_id}: {len(document_ids)} documents")

        finally:
            if needs_close:
                conn.close()

    def update_document_scores(
        self,
        session_id: str,
        document_scores: Dict[int, float]
    ):
        """Update document scores after scoring agent has processed them.

        Args:
            session_id: Session to update
            document_scores: Dict mapping document_id -> relevance_score
        """
        import time
        start_time = time.time()

        conn = self._get_connection()
        needs_close = not self._persistent_conn

        try:
            # First, get all query_ids for this session (single query)
            cursor = conn.execute("""
                SELECT query_id FROM query_metadata WHERE session_id = ?
            """, (session_id,))
            query_ids = [row[0] for row in cursor.fetchall()]

            if not query_ids:
                logger.warning(f"No queries found for session {session_id}")
                return

            # Build a batch update using CASE statement (much faster)
            if document_scores:
                # Build parameterized query for batch update
                placeholders = ','.join(['?'] * len(query_ids))

                # Update scores in batches for efficiency
                batch_size = 100
                doc_items = list(document_scores.items())

                for i in range(0, len(doc_items), batch_size):
                    batch = doc_items[i:i + batch_size]

                    # Build CASE statement for batch
                    case_parts = []
                    params = []
                    doc_ids_in_batch = []

                    for doc_id, score in batch:
                        case_parts.append("WHEN document_id = ? THEN ?")
                        params.extend([doc_id, score])
                        doc_ids_in_batch.append(doc_id)

                    if case_parts:
                        case_sql = " ".join(case_parts)
                        doc_id_placeholders = ','.join(['?'] * len(doc_ids_in_batch))

                        # Single UPDATE for entire batch
                        query = f"""
                            UPDATE query_documents
                            SET document_score = CASE {case_sql} END
                            WHERE document_id IN ({doc_id_placeholders})
                            AND query_id IN ({placeholders})
                        """

                        conn.execute(query, params + doc_ids_in_batch + query_ids)

            conn.commit()
            elapsed = time.time() - start_time
            logger.debug(f"Updated scores for {len(document_scores)} documents in {elapsed:.2f}s")

        finally:
            if needs_close:
                conn.close()

    def get_query_statistics(
        self,
        session_id: str,
        score_threshold: float = 3.0
    ) -> List[QueryPerformanceStats]:
        """Calculate performance statistics for all queries in a session.

        Args:
            session_id: Session to analyze
            score_threshold: Threshold for "high-scoring" documents

        Returns:
            List of QueryPerformanceStats, one per query
        """
        import time
        start_time = time.time()

        conn = self._get_connection()
        needs_close = not self._persistent_conn

        try:
            # Get all queries in session
            cursor = conn.execute("""
                SELECT query_id, model, query_text, temperature, execution_time
                FROM query_metadata
                WHERE session_id = ?
                ORDER BY created_at
            """, (session_id,))

            queries = cursor.fetchall()
            if not queries:
                return []

            query_ids = [q[0] for q in queries]

            # Calculate all statistics in bulk for efficiency
            stats_data = self._calculate_all_query_stats_bulk(
                conn, query_ids, session_id, score_threshold
            )

            # Build QueryPerformanceStats objects
            statistics = []
            for query_id, model, query_text, temperature, execution_time in queries:
                data = stats_data.get(query_id, {})
                stats = QueryPerformanceStats(
                    model=model,
                    temperature=temperature,
                    query=query_text,
                    total_documents=data.get('total', 0),
                    unique_documents=data.get('unique', 0),
                    high_scoring_documents=data.get('high_scoring', 0),
                    unique_high_scoring=data.get('unique_high', 0),
                    execution_time=execution_time
                )
                statistics.append(stats)

            elapsed = time.time() - start_time
            logger.debug(f"Calculated statistics for {len(statistics)} queries in {elapsed:.3f}s")
            return statistics

        finally:
            if needs_close:
                conn.close()

    def _calculate_all_query_stats_bulk(
        self,
        conn: sqlite3.Connection,
        query_ids: List[str],
        session_id: str,
        score_threshold: float
    ) -> Dict[str, Dict[str, int]]:
        """Calculate statistics for all queries in bulk (much faster).

        Returns:
            Dict mapping query_id to stats dict with keys: total, unique, high_scoring, unique_high
        """
        from collections import defaultdict

        # Initialize result dict
        result = {qid: {'total': 0, 'unique': 0, 'high_scoring': 0, 'unique_high': 0} for qid in query_ids}

        # Get all document-query relationships for this session
        placeholders = ','.join(['?'] * len(query_ids))
        cursor = conn.execute(f"""
            SELECT qd.query_id, qd.document_id, qd.document_score
            FROM query_documents qd
            WHERE qd.query_id IN ({placeholders})
        """, query_ids)

        # Build document -> queries mapping
        doc_to_queries = defaultdict(list)
        for query_id, doc_id, score in cursor.fetchall():
            doc_to_queries[doc_id].append((query_id, score))
            result[query_id]['total'] += 1
            if score and score >= score_threshold:
                result[query_id]['high_scoring'] += 1

        # Calculate unique documents
        for doc_id, query_score_pairs in doc_to_queries.items():
            if len(query_score_pairs) == 1:  # Document found by only one query
                query_id, score = query_score_pairs[0]
                result[query_id]['unique'] += 1
                if score and score >= score_threshold:
                    result[query_id]['unique_high'] += 1

        return result

    def _calculate_query_stats(
        self,
        conn: sqlite3.Connection,
        query_id: str,
        session_id: str,
        model: str,
        query_text: str,
        temperature: float,
        execution_time: float,
        score_threshold: float
    ) -> QueryPerformanceStats:
        """Calculate statistics for a single query.

        Returns:
            QueryPerformanceStats for this query
        """
        # Total documents found by this query
        cursor = conn.execute("""
            SELECT COUNT(*) FROM query_documents WHERE query_id = ?
        """, (query_id,))
        total_documents = cursor.fetchone()[0]

        # High-scoring documents found by this query
        cursor = conn.execute("""
            SELECT COUNT(*) FROM query_documents
            WHERE query_id = ? AND document_score >= ?
        """, (query_id, score_threshold))
        high_scoring_documents = cursor.fetchone()[0]

        # Unique documents (not found by any other query in session)
        cursor = conn.execute("""
            SELECT COUNT(DISTINCT qd1.document_id)
            FROM query_documents qd1
            WHERE qd1.query_id = ?
            AND NOT EXISTS (
                SELECT 1 FROM query_documents qd2
                INNER JOIN query_metadata qm2 ON qd2.query_id = qm2.query_id
                WHERE qd2.document_id = qd1.document_id
                AND qm2.session_id = ?
                AND qd2.query_id != ?
            )
        """, (query_id, session_id, query_id))
        unique_documents = cursor.fetchone()[0]

        # Unique high-scoring documents
        cursor = conn.execute("""
            SELECT COUNT(DISTINCT qd1.document_id)
            FROM query_documents qd1
            WHERE qd1.query_id = ?
            AND qd1.document_score >= ?
            AND NOT EXISTS (
                SELECT 1 FROM query_documents qd2
                INNER JOIN query_metadata qm2 ON qd2.query_id = qm2.query_id
                WHERE qd2.document_id = qd1.document_id
                AND qm2.session_id = ?
                AND qd2.query_id != ?
            )
        """, (query_id, score_threshold, session_id, query_id))
        unique_high_scoring = cursor.fetchone()[0]

        return QueryPerformanceStats(
            model=model,
            temperature=temperature,
            query=query_text,
            total_documents=total_documents,
            unique_documents=unique_documents,
            high_scoring_documents=high_scoring_documents,
            unique_high_scoring=unique_high_scoring,
            execution_time=execution_time
        )

    def get_model_performance_summary(
        self,
        session_id: Optional[str] = None,
        score_threshold: float = 3.0
    ) -> Dict[str, Dict[str, Any]]:
        """Get aggregated performance statistics by model.

        Args:
            session_id: Optional session to filter by (None = all sessions)
            score_threshold: Threshold for "high-scoring" documents

        Returns:
            Dict mapping model name to performance metrics:
            {
                "model_name": {
                    "queries_executed": int,
                    "avg_documents": float,
                    "avg_unique_documents": float,
                    "avg_high_scoring": float,
                    "avg_execution_time": float,
                    "total_unique_found": int
                }
            }
        """
        conn = self._get_connection()
        needs_close = not self._persistent_conn

        try:
            where_clause = "WHERE session_id = ?" if session_id else ""
            params = (session_id,) if session_id else ()

            cursor = conn.execute(f"""
                SELECT model, COUNT(*) as query_count, AVG(execution_time) as avg_time
                FROM query_metadata
                {where_clause}
                GROUP BY model
            """, params)

            summary = {}
            for model, query_count, avg_time in cursor.fetchall():
                # Get detailed stats for this model
                stats_list = []
                if session_id:
                    query_filter = "AND qm.session_id = ?"
                    query_params = (model, session_id)
                else:
                    query_filter = ""
                    query_params = (model,)

                cursor2 = conn.execute(f"""
                    SELECT qm.query_id
                    FROM query_metadata qm
                    WHERE qm.model = ? {query_filter}
                """, query_params)

                query_ids = [row[0] for row in cursor2.fetchall()]

                total_docs = 0
                total_unique = 0
                total_high_scoring = 0

                for qid in query_ids:
                    # Get stats for this query
                    cursor3 = conn.execute("""
                        SELECT COUNT(*) FROM query_documents WHERE query_id = ?
                    """, (qid,))
                    total_docs += cursor3.fetchone()[0]

                    cursor3 = conn.execute("""
                        SELECT COUNT(*) FROM query_documents
                        WHERE query_id = ? AND document_score >= ?
                    """, (qid, score_threshold))
                    total_high_scoring += cursor3.fetchone()[0]

                summary[model] = {
                    "queries_executed": query_count,
                    "avg_documents": total_docs / query_count if query_count > 0 else 0,
                    "avg_high_scoring": total_high_scoring / query_count if query_count > 0 else 0,
                    "avg_execution_time": avg_time,
                    "total_documents_found": total_docs
                }

            return summary

        finally:
            if needs_close:
                conn.close()

    def close(self):
        """Close the database connection."""
        if self._persistent_conn:
            self._persistent_conn.close()
            self._persistent_conn = None
