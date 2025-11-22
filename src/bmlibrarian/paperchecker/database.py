"""
Database module for PaperChecker result persistence.

This module provides the PaperCheckDB class for storing and retrieving
fact-checking results in PostgreSQL. It manages the papercheck schema
and all related tables.

Tables managed:
    - papercheck.abstracts_checked: Main abstracts being checked
    - papercheck.statements: Extracted statements
    - papercheck.counter_statements: Counter-claims with search materials
    - papercheck.search_results: Multi-strategy search results
    - papercheck.scored_documents: Documents with relevance scores
    - papercheck.citations: Extracted citation passages
    - papercheck.counter_reports: Synthesized evidence reports
    - papercheck.verdicts: Final verdicts on statements
"""

from typing import Any, Dict, List, Optional
import logging
import os
import psycopg
from psycopg.rows import dict_row

from .data_models import PaperCheckResult


logger = logging.getLogger(__name__)


# Default database configuration
DEFAULT_DB_NAME: str = "knowledgebase"
DEFAULT_DB_HOST: str = "localhost"
DEFAULT_DB_PORT: str = "5432"


class PaperCheckDB:
    """
    Database interface for PaperChecker result persistence.

    Manages connections to PostgreSQL and provides methods for storing
    and retrieving fact-checking results in the papercheck schema.

    Attributes:
        conn: Active database connection
        schema: Schema name (default: 'papercheck')
        db_name: Database name
        db_host: Database host
        db_port: Database port

    Example:
        >>> db = PaperCheckDB()
        >>> if db.test_connection():
        ...     abstract_id = db.save_complete_result(result)
        ...     print(f"Saved as {abstract_id}")
    """

    def __init__(
        self,
        connection: Optional[psycopg.Connection] = None,
        db_name: Optional[str] = None,
        db_user: Optional[str] = None,
        db_password: Optional[str] = None,
        db_host: Optional[str] = None,
        db_port: Optional[str] = None
    ):
        """
        Initialize PaperCheckDB with database connection.

        If connection is not provided, creates a new connection using
        environment variables or default values.

        Args:
            connection: Optional existing psycopg connection
            db_name: Database name (default: from env or 'knowledgebase')
            db_user: Database user (default: from env)
            db_password: Database password (default: from env)
            db_host: Database host (default: from env or 'localhost')
            db_port: Database port (default: from env or '5432')
        """
        self.schema = "papercheck"

        # Store connection parameters
        self.db_name = db_name or os.getenv("POSTGRES_DB", DEFAULT_DB_NAME)
        self.db_host = db_host or os.getenv("POSTGRES_HOST", DEFAULT_DB_HOST)
        self.db_port = db_port or os.getenv("POSTGRES_PORT", DEFAULT_DB_PORT)
        self._db_user = db_user or os.getenv("POSTGRES_USER")
        self._db_password = db_password or os.getenv("POSTGRES_PASSWORD")

        if connection is not None:
            self.conn = connection
            self._owns_connection = False
        else:
            self.conn = self._create_connection()
            self._owns_connection = True

        logger.info(
            f"Initialized PaperCheckDB: {self.db_host}:{self.db_port}/{self.db_name}"
        )

    def _create_connection(self) -> psycopg.Connection:
        """
        Create a new database connection.

        Returns:
            New psycopg connection

        Raises:
            psycopg.Error: If connection fails
        """
        conninfo = f"dbname={self.db_name} host={self.db_host} port={self.db_port}"
        if self._db_user:
            conninfo += f" user={self._db_user}"
        if self._db_password:
            conninfo += f" password={self._db_password}"

        return psycopg.connect(conninfo, row_factory=dict_row)

    def get_connection(self) -> psycopg.Connection:
        """
        Get the database connection.

        Returns:
            Active psycopg connection
        """
        return self.conn

    def test_connection(self) -> bool:
        """
        Test the database connection.

        Verifies that:
        1. Connection is active
        2. papercheck schema exists
        3. Required tables exist

        Returns:
            True if connection is working and schema is ready
        """
        try:
            with self.conn.cursor() as cur:
                # Test basic connectivity
                cur.execute("SELECT 1")
                cur.fetchone()

                # Check schema exists
                cur.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.schemata
                        WHERE schema_name = %s
                    )
                """, (self.schema,))
                result = cur.fetchone()
                schema_exists = result["exists"] if result else False

                if not schema_exists:
                    logger.warning(
                        f"Schema '{self.schema}' does not exist. "
                        "Run schema creation script first."
                    )
                    return False

                logger.info("Database connection test successful")
                return True

        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False

    def ensure_schema(self) -> bool:
        """
        Ensure the papercheck schema and tables exist.

        Creates the schema and all required tables if they don't exist.
        This is idempotent and safe to call multiple times.

        Returns:
            True if schema is ready, False if creation failed
        """
        try:
            with self.conn.cursor() as cur:
                # Create schema
                cur.execute(f"CREATE SCHEMA IF NOT EXISTS {self.schema}")

                # Create tables (using Step 2 schema from 02_DATABASE_SCHEMA.md)
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self.schema}.abstracts_checked (
                        id SERIAL PRIMARY KEY,
                        abstract_text TEXT NOT NULL,
                        source_pmid INTEGER,
                        source_doi TEXT,
                        source_title TEXT,
                        source_metadata JSONB DEFAULT '{{}}',
                        checked_at TIMESTAMP DEFAULT NOW(),
                        model_used VARCHAR(100),
                        config JSONB,
                        overall_assessment TEXT,
                        processing_time_seconds FLOAT
                    )
                """)

                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self.schema}.statements (
                        id SERIAL PRIMARY KEY,
                        abstract_id INTEGER REFERENCES {self.schema}.abstracts_checked(id)
                            ON DELETE CASCADE,
                        statement_text TEXT NOT NULL,
                        context TEXT,
                        statement_type VARCHAR(50),
                        extraction_confidence FLOAT,
                        statement_order INTEGER
                    )
                """)

                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self.schema}.counter_statements (
                        id SERIAL PRIMARY KEY,
                        statement_id INTEGER REFERENCES {self.schema}.statements(id)
                            ON DELETE CASCADE,
                        negated_text TEXT NOT NULL,
                        hyde_abstracts TEXT[],
                        keywords TEXT[],
                        generation_metadata JSONB DEFAULT '{{}}'
                    )
                """)

                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self.schema}.search_results (
                        id SERIAL PRIMARY KEY,
                        counter_statement_id INTEGER REFERENCES {self.schema}.counter_statements(id)
                            ON DELETE CASCADE,
                        doc_id INTEGER NOT NULL,
                        search_strategy VARCHAR(20) NOT NULL,
                        search_rank INTEGER,
                        search_score FLOAT
                    )
                """)

                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self.schema}.scored_documents (
                        id SERIAL PRIMARY KEY,
                        counter_statement_id INTEGER REFERENCES {self.schema}.counter_statements(id)
                            ON DELETE CASCADE,
                        doc_id INTEGER NOT NULL,
                        relevance_score INTEGER CHECK (relevance_score BETWEEN 1 AND 5),
                        explanation TEXT,
                        supports_counter BOOLEAN,
                        found_by TEXT[]
                    )
                """)

                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self.schema}.citations (
                        id SERIAL PRIMARY KEY,
                        counter_statement_id INTEGER REFERENCES {self.schema}.counter_statements(id)
                            ON DELETE CASCADE,
                        doc_id INTEGER NOT NULL,
                        passage TEXT NOT NULL,
                        relevance_score INTEGER,
                        full_citation TEXT,
                        metadata JSONB DEFAULT '{{}}',
                        citation_order INTEGER
                    )
                """)

                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self.schema}.counter_reports (
                        id SERIAL PRIMARY KEY,
                        counter_statement_id INTEGER REFERENCES {self.schema}.counter_statements(id)
                            ON DELETE CASCADE,
                        report_text TEXT NOT NULL,
                        num_citations INTEGER,
                        search_stats JSONB DEFAULT '{{}}',
                        generation_metadata JSONB DEFAULT '{{}}',
                        generated_at TIMESTAMP DEFAULT NOW()
                    )
                """)

                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self.schema}.verdicts (
                        id SERIAL PRIMARY KEY,
                        statement_id INTEGER REFERENCES {self.schema}.statements(id)
                            ON DELETE CASCADE,
                        verdict VARCHAR(20) CHECK (verdict IN ('supports', 'contradicts', 'undecided')),
                        rationale TEXT NOT NULL,
                        confidence VARCHAR(20) CHECK (confidence IN ('high', 'medium', 'low')),
                        analysis_metadata JSONB DEFAULT '{{}}',
                        generated_at TIMESTAMP DEFAULT NOW()
                    )
                """)

                # Create indexes for common queries
                cur.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_abstracts_pmid
                    ON {self.schema}.abstracts_checked(source_pmid)
                """)
                cur.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_abstracts_doi
                    ON {self.schema}.abstracts_checked(source_doi)
                """)
                cur.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_statements_abstract
                    ON {self.schema}.statements(abstract_id)
                """)
                cur.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_search_results_counter
                    ON {self.schema}.search_results(counter_statement_id)
                """)
                cur.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_verdicts_statement
                    ON {self.schema}.verdicts(statement_id)
                """)

                self.conn.commit()
                logger.info(f"Schema '{self.schema}' created/verified successfully")
                return True

        except Exception as e:
            logger.error(f"Failed to create schema: {e}")
            self.conn.rollback()
            return False

    def save_complete_result(self, result: PaperCheckResult) -> int:
        """
        Save a complete PaperCheckResult to the database.

        Saves all components of the result in a single transaction:
        abstract, statements, counter-statements, search results,
        scored documents, citations, counter-reports, and verdicts.

        Args:
            result: Complete PaperCheckResult to save

        Returns:
            ID of the saved abstract record

        Raises:
            psycopg.Error: If database operation fails
        """
        try:
            with self.conn.cursor() as cur:
                # Save main abstract record
                cur.execute(f"""
                    INSERT INTO {self.schema}.abstracts_checked
                    (abstract_text, source_pmid, source_doi, source_title,
                     source_metadata, model_used, config, overall_assessment,
                     processing_time_seconds)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    result.original_abstract,
                    result.source_metadata.get("pmid"),
                    result.source_metadata.get("doi"),
                    result.source_metadata.get("title"),
                    psycopg.types.json.Json(result.source_metadata),
                    result.processing_metadata.get("model"),
                    psycopg.types.json.Json(result.processing_metadata.get("config", {})),
                    result.overall_assessment,
                    result.processing_metadata.get("processing_time_seconds")
                ))
                abstract_id = cur.fetchone()["id"]

                # Save each statement and its related data
                for i, stmt in enumerate(result.statements):
                    # Save statement
                    cur.execute(f"""
                        INSERT INTO {self.schema}.statements
                        (abstract_id, statement_text, context, statement_type,
                         extraction_confidence, statement_order)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (
                        abstract_id,
                        stmt.text,
                        stmt.context,
                        stmt.statement_type,
                        stmt.confidence,
                        stmt.statement_order
                    ))
                    statement_id = cur.fetchone()["id"]

                    # Save counter-statement
                    counter_stmt = result.counter_statements[i]
                    cur.execute(f"""
                        INSERT INTO {self.schema}.counter_statements
                        (statement_id, negated_text, hyde_abstracts, keywords,
                         generation_metadata)
                        VALUES (%s, %s, %s, %s, %s)
                        RETURNING id
                    """, (
                        statement_id,
                        counter_stmt.negated_text,
                        counter_stmt.hyde_abstracts,
                        counter_stmt.keywords,
                        psycopg.types.json.Json(counter_stmt.generation_metadata)
                    ))
                    counter_stmt_id = cur.fetchone()["id"]

                    # Save search results
                    search_results = result.search_results[i]
                    for rank, doc_id in enumerate(search_results.semantic_docs, 1):
                        cur.execute(f"""
                            INSERT INTO {self.schema}.search_results
                            (counter_statement_id, doc_id, search_strategy, search_rank)
                            VALUES (%s, %s, %s, %s)
                        """, (counter_stmt_id, doc_id, "semantic", rank))

                    for rank, doc_id in enumerate(search_results.hyde_docs, 1):
                        cur.execute(f"""
                            INSERT INTO {self.schema}.search_results
                            (counter_statement_id, doc_id, search_strategy, search_rank)
                            VALUES (%s, %s, %s, %s)
                        """, (counter_stmt_id, doc_id, "hyde", rank))

                    for rank, doc_id in enumerate(search_results.keyword_docs, 1):
                        cur.execute(f"""
                            INSERT INTO {self.schema}.search_results
                            (counter_statement_id, doc_id, search_strategy, search_rank)
                            VALUES (%s, %s, %s, %s)
                        """, (counter_stmt_id, doc_id, "keyword", rank))

                    # Save scored documents
                    for scored_doc in result.scored_documents[i]:
                        cur.execute(f"""
                            INSERT INTO {self.schema}.scored_documents
                            (counter_statement_id, doc_id, relevance_score,
                             explanation, supports_counter, found_by)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """, (
                            counter_stmt_id,
                            scored_doc.doc_id,
                            scored_doc.score,
                            scored_doc.explanation,
                            scored_doc.supports_counter,
                            scored_doc.found_by
                        ))

                    # Save counter-report
                    counter_report = result.counter_reports[i]
                    cur.execute(f"""
                        INSERT INTO {self.schema}.counter_reports
                        (counter_statement_id, report_text, num_citations,
                         search_stats, generation_metadata)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (
                        counter_stmt_id,
                        counter_report.summary,
                        counter_report.num_citations,
                        psycopg.types.json.Json(counter_report.search_stats),
                        psycopg.types.json.Json(counter_report.generation_metadata)
                    ))

                    # Save citations
                    for citation in counter_report.citations:
                        cur.execute(f"""
                            INSERT INTO {self.schema}.citations
                            (counter_statement_id, doc_id, passage, relevance_score,
                             full_citation, metadata, citation_order)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """, (
                            counter_stmt_id,
                            citation.doc_id,
                            citation.passage,
                            citation.relevance_score,
                            citation.full_citation,
                            psycopg.types.json.Json(citation.metadata),
                            citation.citation_order
                        ))

                    # Save verdict
                    verdict = result.verdicts[i]
                    cur.execute(f"""
                        INSERT INTO {self.schema}.verdicts
                        (statement_id, verdict, rationale, confidence,
                         analysis_metadata)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (
                        statement_id,
                        verdict.verdict,
                        verdict.rationale,
                        verdict.confidence,
                        psycopg.types.json.Json(verdict.analysis_metadata)
                    ))

                self.conn.commit()
                logger.info(f"Saved complete result as abstract_id={abstract_id}")
                return abstract_id

        except Exception as e:
            logger.error(f"Failed to save result: {e}")
            self.conn.rollback()
            raise

    def get_result_by_id(self, abstract_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve a complete result by abstract ID.

        Args:
            abstract_id: ID of the abstract to retrieve

        Returns:
            Dictionary with complete result data, or None if not found
        """
        try:
            with self.conn.cursor() as cur:
                # Get main abstract
                cur.execute(f"""
                    SELECT * FROM {self.schema}.abstracts_checked
                    WHERE id = %s
                """, (abstract_id,))
                abstract = cur.fetchone()

                if not abstract:
                    return None

                # Get statements with related data
                cur.execute(f"""
                    SELECT s.*, cs.*, v.*
                    FROM {self.schema}.statements s
                    LEFT JOIN {self.schema}.counter_statements cs ON cs.statement_id = s.id
                    LEFT JOIN {self.schema}.verdicts v ON v.statement_id = s.id
                    WHERE s.abstract_id = %s
                    ORDER BY s.statement_order
                """, (abstract_id,))
                statements = cur.fetchall()

                return {
                    "abstract": dict(abstract),
                    "statements": [dict(s) for s in statements]
                }

        except Exception as e:
            logger.error(f"Failed to retrieve result: {e}")
            return None

    def get_results_by_pmid(self, pmid: int) -> List[Dict[str, Any]]:
        """
        Retrieve all results for a given PMID.

        Args:
            pmid: PubMed ID to search for

        Returns:
            List of result dictionaries
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"""
                    SELECT id, checked_at, overall_assessment
                    FROM {self.schema}.abstracts_checked
                    WHERE source_pmid = %s
                    ORDER BY checked_at DESC
                """, (pmid,))
                return [dict(row) for row in cur.fetchall()]

        except Exception as e:
            logger.error(f"Failed to retrieve results by PMID: {e}")
            return []

    def list_recent_checks(
        self,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        List recent abstract checks with summary information.

        Args:
            limit: Maximum number of results to return (default: 100)
            offset: Number of results to skip for pagination (default: 0)

        Returns:
            List of dictionaries with summary information including:
            - id: Abstract check ID
            - source_pmid: PubMed ID if available
            - source_doi: DOI if available
            - source_title: Paper title if available
            - checked_at: Timestamp of check
            - num_statements: Number of statements extracted
            - overall_assessment: Overall assessment text
            - model_used: Model used for analysis
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"""
                    SELECT
                        a.id,
                        a.source_pmid,
                        a.source_doi,
                        a.source_title,
                        a.checked_at,
                        a.overall_assessment,
                        a.model_used,
                        a.processing_time_seconds,
                        COUNT(s.id) as num_statements
                    FROM {self.schema}.abstracts_checked a
                    LEFT JOIN {self.schema}.statements s ON s.abstract_id = a.id
                    GROUP BY a.id
                    ORDER BY a.checked_at DESC
                    LIMIT %s OFFSET %s
                """, (limit, offset))
                return [dict(row) for row in cur.fetchall()]

        except Exception as e:
            logger.error(f"Failed to list recent checks: {e}")
            return []

    def get_verdicts_summary(self, abstract_id: int) -> List[Dict[str, Any]]:
        """
        Get summary of verdicts for an abstract check.

        Args:
            abstract_id: ID of the abstract to get verdicts for

        Returns:
            List of verdict summaries with statement text, verdict, and confidence
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"""
                    SELECT
                        s.statement_text,
                        s.statement_type,
                        s.statement_order,
                        v.verdict,
                        v.rationale,
                        v.confidence,
                        cr.num_citations,
                        cr.report_text
                    FROM {self.schema}.statements s
                    LEFT JOIN {self.schema}.verdicts v ON v.statement_id = s.id
                    LEFT JOIN {self.schema}.counter_statements cs ON cs.statement_id = s.id
                    LEFT JOIN {self.schema}.counter_reports cr ON cr.counter_statement_id = cs.id
                    WHERE s.abstract_id = %s
                    ORDER BY s.statement_order
                """, (abstract_id,))
                return [dict(row) for row in cur.fetchall()]

        except Exception as e:
            logger.error(f"Failed to get verdicts summary: {e}")
            return []

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get overall statistics for the papercheck database.

        Returns:
            Dictionary containing:
            - total_abstracts: Total number of abstracts checked
            - total_statements: Total number of statements extracted
            - verdicts_breakdown: Count by verdict type
            - confidence_breakdown: Count by confidence level
            - recent_activity: Abstracts checked in last 24 hours
        """
        try:
            with self.conn.cursor() as cur:
                # Total abstracts
                cur.execute(f"""
                    SELECT COUNT(*) as count FROM {self.schema}.abstracts_checked
                """)
                total_abstracts = cur.fetchone()["count"]

                # Total statements
                cur.execute(f"""
                    SELECT COUNT(*) as count FROM {self.schema}.statements
                """)
                total_statements = cur.fetchone()["count"]

                # Verdicts breakdown
                cur.execute(f"""
                    SELECT verdict, COUNT(*) as count
                    FROM {self.schema}.verdicts
                    GROUP BY verdict
                """)
                verdicts_breakdown = {
                    row["verdict"]: row["count"]
                    for row in cur.fetchall()
                }

                # Confidence breakdown
                cur.execute(f"""
                    SELECT confidence, COUNT(*) as count
                    FROM {self.schema}.verdicts
                    GROUP BY confidence
                """)
                confidence_breakdown = {
                    row["confidence"]: row["count"]
                    for row in cur.fetchall()
                }

                # Recent activity (last 24 hours)
                cur.execute(f"""
                    SELECT COUNT(*) as count
                    FROM {self.schema}.abstracts_checked
                    WHERE checked_at >= NOW() - INTERVAL '24 hours'
                """)
                recent_activity = cur.fetchone()["count"]

                return {
                    "total_abstracts": total_abstracts,
                    "total_statements": total_statements,
                    "verdicts_breakdown": verdicts_breakdown,
                    "confidence_breakdown": confidence_breakdown,
                    "recent_activity": recent_activity
                }

        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return {
                "total_abstracts": 0,
                "total_statements": 0,
                "verdicts_breakdown": {},
                "confidence_breakdown": {},
                "recent_activity": 0
            }

    def delete_result(self, abstract_id: int) -> bool:
        """
        Delete a complete result and all related data.

        Uses CASCADE delete to remove all related statements, counter-statements,
        search results, scored documents, citations, counter-reports, and verdicts.

        Args:
            abstract_id: ID of the abstract to delete

        Returns:
            True if deletion was successful, False otherwise
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"""
                    DELETE FROM {self.schema}.abstracts_checked
                    WHERE id = %s
                """, (abstract_id,))
                self.conn.commit()
                deleted = cur.rowcount > 0
                if deleted:
                    logger.info(f"Deleted abstract_id={abstract_id} and all related data")
                else:
                    logger.warning(f"No abstract found with id={abstract_id}")
                return deleted

        except Exception as e:
            logger.error(f"Failed to delete result: {e}")
            self.conn.rollback()
            return False

    def close(self) -> None:
        """Close the database connection if owned by this instance."""
        if self._owns_connection and self.conn:
            self.conn.close()
            logger.info("Database connection closed")

    def __enter__(self) -> "PaperCheckDB":
        """
        Context manager entry.

        Returns:
            Self for use in 'with' statement
        """
        return self

    def __exit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[Any]
    ) -> None:
        """
        Context manager exit.

        Closes the database connection when exiting the context.

        Args:
            exc_type: Exception type if an exception was raised
            exc_val: Exception value if an exception was raised
            exc_tb: Exception traceback if an exception was raised
        """
        self.close()
