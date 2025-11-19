#!/usr/bin/env python3
"""
Export Fact-Checker Review Package

Creates a self-contained SQLite database for distributing fact-check results
to external reviewers. The package includes:
- Statements with AI evaluations
- Evidence/citations with full document abstracts
- No human annotations from other reviewers (clean slate)

Usage:
    python export_review_package.py --output review_package.db
    python export_review_package.py --output package.db --session-id abc123
"""

import argparse
import sys
import sqlite3
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Set, Dict, Any
import json

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from bmlibrarian.factchecker.db.database import FactCheckerDB
from bmlibrarian.database import get_db_manager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def read_schema_file() -> str:
    """Read the SQLite schema file."""
    schema_path = Path(__file__).parent / 'src' / 'bmlibrarian' / 'factchecker' / 'db' / 'sqlite_schema.sql'
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    with open(schema_path, 'r') as f:
        return f.read()


def create_sqlite_database(db_path: Path):
    """Create and initialize SQLite database with schema."""
    logger.info(f"Creating SQLite database: {db_path}")

    # Remove existing file if present
    if db_path.exists():
        logger.warning(f"Removing existing database: {db_path}")
        db_path.unlink()

    # Create database
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Read and execute schema
    schema_sql = read_schema_file()
    cursor.executescript(schema_sql)

    conn.commit()
    logger.info("SQLite database created and initialized")

    return conn


def export_statements_and_evaluations(pg_db: FactCheckerDB, sqlite_conn: sqlite3.Connection, session_id: str = None) -> tuple:
    """
    Export statements and AI evaluations from PostgreSQL to SQLite.

    Returns:
        Tuple of (statement_count, evaluation_count, evaluation_ids)
    """
    logger.info("Exporting statements and AI evaluations...")

    with pg_db.db_manager.get_connection() as pg_conn:
        with pg_conn.cursor() as pg_cursor:
            # Query statements with their latest AI evaluations
            query = """
                SELECT DISTINCT
                    s.statement_id,
                    s.statement_text,
                    s.input_statement_id,
                    s.expected_answer,
                    s.context,
                    s.long_answer,
                    s.created_at,
                    s.source_file,
                    s.review_status,
                    ae.evaluation_id,
                    ae.evaluation,
                    ae.reason,
                    ae.confidence,
                    ae.documents_reviewed,
                    ae.supporting_citations,
                    ae.contradicting_citations,
                    ae.neutral_citations,
                    ae.matches_expected,
                    ae.evaluated_at,
                    ae.model_used,
                    ae.model_version,
                    ae.agent_config,
                    ae.session_id,
                    ae.version
                FROM factcheck.statements s
                LEFT JOIN factcheck.ai_evaluations ae ON s.statement_id = ae.statement_id
                LEFT JOIN (
                    SELECT statement_id, MAX(version) as max_version
                    FROM factcheck.ai_evaluations
                    GROUP BY statement_id
                ) latest ON ae.statement_id = latest.statement_id AND ae.version = latest.max_version
            """

            # Add session filter if specified
            if session_id:
                query += " WHERE ae.session_id = %s"
                pg_cursor.execute(query, (session_id,))
            else:
                query += " ORDER BY s.statement_id"
                pg_cursor.execute(query)

            results = pg_cursor.fetchall()

            if not results:
                raise ValueError("No statements found to export")

            sqlite_cursor = sqlite_conn.cursor()
            statement_count = 0
            evaluation_count = 0
            evaluation_ids = set()

            for row in results:
                (stmt_id, stmt_text, input_id, expected_ans, context, long_answer, created_at, source_file, review_status,
                 eval_id, evaluation, reason, confidence, docs_reviewed, supp_citations, contra_citations,
                 neutral_citations, matches_expected, evaluated_at, model_used, model_version,
                 agent_config, eval_session_id, version) = row

                # Insert statement
                sqlite_cursor.execute("""
                    INSERT OR IGNORE INTO statements (
                        statement_id, statement_text, input_statement_id, expected_answer,
                        context, long_answer, created_at, source_file, review_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    stmt_id, stmt_text, input_id, expected_ans, context, long_answer,
                    created_at.isoformat() if created_at else None,
                    source_file, review_status
                ))

                if sqlite_cursor.rowcount > 0:
                    statement_count += 1

                # Insert AI evaluation if exists
                if eval_id:
                    # Convert agent_config JSONB to JSON string
                    agent_config_str = json.dumps(agent_config) if agent_config else None

                    sqlite_cursor.execute("""
                        INSERT OR IGNORE INTO ai_evaluations (
                            evaluation_id, statement_id, evaluation, reason, confidence,
                            documents_reviewed, supporting_citations, contradicting_citations,
                            neutral_citations, matches_expected, evaluated_at, model_used,
                            model_version, agent_config, session_id, version
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        eval_id, stmt_id, evaluation, reason, confidence,
                        docs_reviewed, supp_citations, contra_citations, neutral_citations,
                        1 if matches_expected else 0 if matches_expected is not None else None,
                        evaluated_at.isoformat() if evaluated_at else None,
                        model_used, model_version, agent_config_str, eval_session_id, version
                    ))

                    if sqlite_cursor.rowcount > 0:
                        evaluation_count += 1
                        evaluation_ids.add(eval_id)

            sqlite_conn.commit()
            logger.info(f"Exported {statement_count} statements and {evaluation_count} AI evaluations")

            return statement_count, evaluation_count, evaluation_ids


def export_evidence(pg_db: FactCheckerDB, sqlite_conn: sqlite3.Connection, evaluation_ids: Set[int]) -> tuple:
    """
    Export evidence/citations from PostgreSQL to SQLite.

    Returns:
        Tuple of (evidence_count, document_ids)
    """
    if not evaluation_ids:
        logger.warning("No evaluations found, skipping evidence export")
        return 0, set()

    logger.info(f"Exporting evidence for {len(evaluation_ids)} evaluations...")

    with pg_db.db_manager.get_connection() as pg_conn:
        with pg_conn.cursor() as pg_cursor:
            # Query evidence for the evaluations
            pg_cursor.execute("""
                SELECT
                    evidence_id, evaluation_id, citation_text, document_id,
                    pmid, doi, relevance_score, supports_statement, created_at
                FROM factcheck.evidence
                WHERE evaluation_id = ANY(%s)
            """, (list(evaluation_ids),))

            evidence_rows = pg_cursor.fetchall()

            if not evidence_rows:
                logger.warning("No evidence found for evaluations")
                return 0, set()

            sqlite_cursor = sqlite_conn.cursor()
            evidence_count = 0
            document_ids = set()

            for row in evidence_rows:
                (ev_id, eval_id, citation, doc_id, pmid, doi, score, stance, created_at) = row

                sqlite_cursor.execute("""
                    INSERT OR IGNORE INTO evidence (
                        evidence_id, evaluation_id, citation_text, document_id,
                        pmid, doi, relevance_score, supports_statement, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    ev_id, eval_id, citation, doc_id, pmid, doi, score, stance,
                    created_at.isoformat() if created_at else None
                ))

                if sqlite_cursor.rowcount > 0:
                    evidence_count += 1
                    document_ids.add(doc_id)

            sqlite_conn.commit()
            logger.info(f"Exported {evidence_count} evidence citations")
            logger.info(f"Found {len(document_ids)} unique documents to export")

            return evidence_count, document_ids


def export_documents(pg_db: FactCheckerDB, sqlite_conn: sqlite3.Connection, document_ids: Set[int]) -> int:
    """
    Export full document data (including abstracts) from PostgreSQL to SQLite.

    This is critical - the review package must include full abstracts for review!

    Returns:
        Number of documents exported
    """
    if not document_ids:
        logger.warning("No documents to export")
        return 0

    logger.info(f"Exporting {len(document_ids)} documents with full abstracts...")

    with pg_db.db_manager.get_connection() as pg_conn:
        with pg_conn.cursor() as pg_cursor:
            # Query documents from public.document table
            pg_cursor.execute("""
                SELECT
                    id, source_id, external_id, doi, title, abstract,
                    authors, publication, publication_date, url, pdf_url,
                    added_date, updated_date
                FROM document
                WHERE id = ANY(%s)
            """, (list(document_ids),))

            document_rows = pg_cursor.fetchall()

            if not document_rows:
                logger.error("Failed to fetch documents from database!")
                return 0

            sqlite_cursor = sqlite_conn.cursor()
            document_count = 0

            for row in document_rows:
                (doc_id, source_id, external_id, doi, title, abstract,
                 authors, publication, pub_date, url, pdf_url,
                 added_date, updated_date) = row

                # Convert authors array to JSON string
                authors_json = json.dumps(authors) if authors else None

                sqlite_cursor.execute("""
                    INSERT OR IGNORE INTO documents (
                        id, source_id, external_id, doi, title, abstract, authors,
                        publication, publication_date, url, pdf_url, added_date, updated_date
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    doc_id, source_id, external_id, doi, title, abstract, authors_json,
                    publication,
                    pub_date.isoformat() if pub_date else None,
                    url, pdf_url,
                    added_date.isoformat() if added_date else None,
                    updated_date.isoformat() if updated_date else None
                ))

                if sqlite_cursor.rowcount > 0:
                    document_count += 1

            sqlite_conn.commit()
            logger.info(f"Exported {document_count} documents with full abstracts")

            return document_count


def add_package_metadata(
    sqlite_conn: sqlite3.Connection,
    statement_count: int,
    evaluation_count: int,
    evidence_count: int,
    document_count: int,
    exported_by: str = None
):
    """Add package metadata to SQLite database."""
    logger.info("Adding package metadata...")

    cursor = sqlite_conn.cursor()

    # Get PostgreSQL database info
    cursor.execute("""
        INSERT INTO package_metadata (
            export_date, source_database, postgresql_version, bmlibrarian_version,
            total_statements, total_evaluations, total_evidence, total_documents,
            exported_by, package_version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.now(timezone.utc).isoformat(),
        "knowledgebase @ PostgreSQL",  # Could query actual connection info
        "PostgreSQL 16+",  # Could query actual version
        "1.0.0",  # Could import from bmlibrarian.__version__
        statement_count,
        evaluation_count,
        evidence_count,
        document_count,
        exported_by or "system",
        1
    ))

    sqlite_conn.commit()
    logger.info("Package metadata added")


def optimize_database(sqlite_conn: sqlite3.Connection):
    """Optimize SQLite database for distribution."""
    logger.info("Optimizing database...")

    cursor = sqlite_conn.cursor()

    # Run ANALYZE to update query planner statistics
    cursor.execute("ANALYZE")

    # Run VACUUM to reclaim unused space and defragment
    cursor.execute("VACUUM")

    sqlite_conn.commit()
    logger.info("Database optimized")


def main():
    parser = argparse.ArgumentParser(
        description="Export fact-checker review package as self-contained SQLite database"
    )
    parser.add_argument(
        '--output',
        '-o',
        type=str,
        required=True,
        help='Output SQLite database file path (e.g., review_package.db)'
    )
    parser.add_argument(
        '--session-id',
        type=str,
        help='Export only statements from specific session ID'
    )
    parser.add_argument(
        '--exported-by',
        type=str,
        help='Username of person creating the export'
    )

    args = parser.parse_args()

    # Validate output path
    output_path = Path(args.output)
    if output_path.suffix != '.db':
        logger.error("Output file must have .db extension")
        sys.exit(1)

    # Create parent directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Connect to PostgreSQL
        logger.info("Connecting to PostgreSQL...")
        pg_db = FactCheckerDB()

        # Create SQLite database
        sqlite_conn = create_sqlite_database(output_path)

        # Export data
        statement_count, evaluation_count, evaluation_ids = export_statements_and_evaluations(
            pg_db, sqlite_conn, args.session_id
        )

        evidence_count, document_ids = export_evidence(
            pg_db, sqlite_conn, evaluation_ids
        )

        document_count = export_documents(
            pg_db, sqlite_conn, document_ids
        )

        # Add metadata
        add_package_metadata(
            sqlite_conn,
            statement_count,
            evaluation_count,
            evidence_count,
            document_count,
            args.exported_by
        )

        # Optimize
        optimize_database(sqlite_conn)

        # Close connection
        sqlite_conn.close()

        # Success
        logger.info("=" * 60)
        logger.info("✓ Export complete!")
        logger.info(f"  Output file: {output_path}")
        logger.info(f"  File size: {output_path.stat().st_size / 1024 / 1024:.2f} MB")
        logger.info(f"  Statements: {statement_count}")
        logger.info(f"  AI Evaluations: {evaluation_count}")
        logger.info(f"  Evidence Citations: {evidence_count}")
        logger.info(f"  Documents (with full abstracts): {document_count}")
        logger.info("=" * 60)
        logger.info("Package ready for distribution to external reviewers!")

    except Exception as e:
        logger.error(f"Export failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
