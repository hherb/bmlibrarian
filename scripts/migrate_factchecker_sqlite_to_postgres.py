#!/usr/bin/env python3
"""
Migration Script: SQLite Fact-Checker Database to PostgreSQL

Migrates all fact-checker data from legacy SQLite database to PostgreSQL factcheck schema.

Usage:
    python scripts/migrate_factchecker_sqlite_to_postgres.py --sqlite-db /path/to/factchecker.db
    python scripts/migrate_factchecker_sqlite_to_postgres.py --sqlite-db /path/to/factchecker.db --skip-existing
    python scripts/migrate_factchecker_sqlite_to_postgres.py --sqlite-db /path/to/factchecker.db --dry-run

Options:
    --sqlite-db PATH     Path to SQLite database file (required)
    --skip-existing      Skip statements that already exist in PostgreSQL
    --dry-run           Show what would be migrated without actually migrating
    --verbose           Show detailed progress information
"""

import argparse
import sqlite3
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.bmlibrarian.factchecker.db.database import (
    FactCheckerDB,
    Statement,
    Annotator,
    AIEvaluation,
    Evidence,
    HumanAnnotation
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SQLiteToPostgresMigrator:
    """
    Migrates fact-checker data from SQLite to PostgreSQL.

    Handles all tables:
    - statements
    - annotators
    - ai_evaluations
    - evidence
    - human_annotations
    - processing_metadata
    - export_history
    """

    def __init__(self, sqlite_path: str, skip_existing: bool = False, dry_run: bool = False):
        """
        Initialize migrator.

        Args:
            sqlite_path: Path to SQLite database file
            skip_existing: Skip statements that already exist in PostgreSQL
            dry_run: Show what would be migrated without actually migrating
        """
        self.sqlite_path = Path(sqlite_path)
        self.skip_existing = skip_existing
        self.dry_run = dry_run

        if not self.sqlite_path.exists():
            raise FileNotFoundError(f"SQLite database not found: {sqlite_path}")

        self.pg_db = FactCheckerDB()
        self.stats = {
            'statements': {'total': 0, 'migrated': 0, 'skipped': 0, 'errors': 0},
            'annotators': {'total': 0, 'migrated': 0, 'skipped': 0, 'errors': 0},
            'ai_evaluations': {'total': 0, 'migrated': 0, 'skipped': 0, 'errors': 0},
            'evidence': {'total': 0, 'migrated': 0, 'skipped': 0, 'errors': 0},
            'human_annotations': {'total': 0, 'migrated': 0, 'skipped': 0, 'errors': 0},
            'processing_metadata': {'total': 0, 'migrated': 0, 'skipped': 0, 'errors': 0},
            'export_history': {'total': 0, 'migrated': 0, 'skipped': 0, 'errors': 0},
        }

        # Map SQLite statement IDs to PostgreSQL statement IDs
        self.statement_id_map: Dict[int, int] = {}

        # Map SQLite annotator IDs to PostgreSQL annotator IDs
        self.annotator_id_map: Dict[int, int] = {}

        # Map SQLite ai_evaluation IDs to PostgreSQL evaluation IDs
        self.evaluation_id_map: Dict[int, int] = {}

    def get_sqlite_connection(self):
        """Get SQLite database connection."""
        conn = sqlite3.connect(str(self.sqlite_path))
        conn.row_factory = sqlite3.Row
        return conn

    def migrate_all(self):
        """Run complete migration."""
        logger.info(f"Starting migration from {self.sqlite_path}")
        logger.info(f"Dry run: {self.dry_run}")
        logger.info(f"Skip existing: {self.skip_existing}")
        logger.info("-" * 80)

        try:
            # Order matters due to foreign key constraints
            self.migrate_statements()
            self.migrate_annotators()
            self.migrate_ai_evaluations()
            self.migrate_evidence()
            self.migrate_human_annotations()
            self.migrate_processing_metadata()
            self.migrate_export_history()

            self.print_summary()

            if self.dry_run:
                logger.info("\n⚠️  DRY RUN - No data was actually migrated")
            else:
                logger.info("\n✅ Migration completed successfully!")

        except Exception as e:
            logger.error(f"Migration failed: {e}", exc_info=True)
            raise

    def migrate_statements(self):
        """Migrate statements table."""
        logger.info("Migrating statements...")

        with self.get_sqlite_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM statements")
            rows = cursor.fetchall()

            self.stats['statements']['total'] = len(rows)

            for row in rows:
                try:
                    sqlite_id = row['id']

                    statement = Statement(
                        statement_text=row['statement_text'],
                        input_statement_id=row['input_statement_id'],
                        expected_answer=row['expected_answer'],
                        source_file=row['source_file'],
                        review_status=row['review_status'] or 'pending'
                    )

                    if not self.dry_run:
                        # This will return existing ID if statement already exists
                        pg_id = self.pg_db.insert_statement(statement)
                        self.statement_id_map[sqlite_id] = pg_id
                        self.stats['statements']['migrated'] += 1
                    else:
                        self.stats['statements']['migrated'] += 1

                    if self.stats['statements']['migrated'] % 100 == 0:
                        logger.info(f"  Migrated {self.stats['statements']['migrated']} statements...")

                except Exception as e:
                    logger.error(f"Error migrating statement {row['id']}: {e}")
                    self.stats['statements']['errors'] += 1

        logger.info(f"✓ Statements: {self.stats['statements']['migrated']}/{self.stats['statements']['total']}")

    def migrate_annotators(self):
        """Migrate annotators table."""
        logger.info("Migrating annotators...")

        with self.get_sqlite_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM annotators")
            rows = cursor.fetchall()

            self.stats['annotators']['total'] = len(rows)

            for row in rows:
                try:
                    sqlite_id = row['id']

                    annotator = Annotator(
                        username=row['username'],
                        full_name=row['full_name'],
                        email=row['email'],
                        expertise_level=row['expertise_level'],
                        institution=row['institution']
                    )

                    if not self.dry_run:
                        pg_id = self.pg_db.insert_or_get_annotator(annotator)
                        self.annotator_id_map[sqlite_id] = pg_id
                        self.stats['annotators']['migrated'] += 1
                    else:
                        self.stats['annotators']['migrated'] += 1

                except Exception as e:
                    logger.error(f"Error migrating annotator {row['id']}: {e}")
                    self.stats['annotators']['errors'] += 1

        logger.info(f"✓ Annotators: {self.stats['annotators']['migrated']}/{self.stats['annotators']['total']}")

    def migrate_ai_evaluations(self):
        """Migrate ai_evaluations table."""
        logger.info("Migrating AI evaluations...")

        with self.get_sqlite_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM ai_evaluations ORDER BY statement_id, version")
            rows = cursor.fetchall()

            self.stats['ai_evaluations']['total'] = len(rows)

            for row in rows:
                try:
                    sqlite_eval_id = row['id']
                    sqlite_stmt_id = row['statement_id']

                    # Skip if statement wasn't migrated
                    if sqlite_stmt_id not in self.statement_id_map and not self.dry_run:
                        logger.warning(f"Skipping evaluation {sqlite_eval_id}: statement {sqlite_stmt_id} not found")
                        self.stats['ai_evaluations']['skipped'] += 1
                        continue

                    pg_stmt_id = self.statement_id_map.get(sqlite_stmt_id, sqlite_stmt_id)

                    evaluation = AIEvaluation(
                        statement_id=pg_stmt_id,
                        evaluation=row['evaluation'],
                        reason=row['reason'] or '',
                        confidence=row['confidence'],
                        documents_reviewed=row['documents_reviewed'] or 0,
                        supporting_citations=row['supporting_citations'] or 0,
                        contradicting_citations=row['contradicting_citations'] or 0,
                        neutral_citations=row['neutral_citations'] or 0,
                        matches_expected=bool(row['matches_expected']) if row['matches_expected'] is not None else None,
                        model_used=row['model_used'],
                        model_version=row['model_version'],
                        agent_config=row['agent_config'],
                        session_id=row['session_id'],
                        version=row['version'] or 1
                    )

                    if not self.dry_run:
                        pg_eval_id = self.pg_db.insert_ai_evaluation(evaluation)
                        self.evaluation_id_map[sqlite_eval_id] = pg_eval_id
                        self.stats['ai_evaluations']['migrated'] += 1
                    else:
                        self.stats['ai_evaluations']['migrated'] += 1

                    if self.stats['ai_evaluations']['migrated'] % 100 == 0:
                        logger.info(f"  Migrated {self.stats['ai_evaluations']['migrated']} evaluations...")

                except Exception as e:
                    logger.error(f"Error migrating evaluation {row['id']}: {e}")
                    self.stats['ai_evaluations']['errors'] += 1

        logger.info(f"✓ AI Evaluations: {self.stats['ai_evaluations']['migrated']}/{self.stats['ai_evaluations']['total']}")

    def migrate_evidence(self):
        """Migrate evidence table."""
        logger.info("Migrating evidence citations...")

        with self.get_sqlite_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM evidence")
            rows = cursor.fetchall()

            self.stats['evidence']['total'] = len(rows)

            for row in rows:
                try:
                    sqlite_eval_id = row['ai_evaluation_id']

                    # Skip if evaluation wasn't migrated
                    if sqlite_eval_id not in self.evaluation_id_map and not self.dry_run:
                        logger.warning(f"Skipping evidence {row['id']}: evaluation {sqlite_eval_id} not found")
                        self.stats['evidence']['skipped'] += 1
                        continue

                    pg_eval_id = self.evaluation_id_map.get(sqlite_eval_id, sqlite_eval_id)

                    # Handle document_id - in SQLite it might be stored as string
                    document_id_raw = row['document_id']
                    if document_id_raw:
                        try:
                            document_id = int(document_id_raw) if isinstance(document_id_raw, str) else document_id_raw
                        except (ValueError, TypeError):
                            logger.warning(f"Invalid document_id for evidence {row['id']}: {document_id_raw}")
                            self.stats['evidence']['skipped'] += 1
                            continue
                    else:
                        logger.warning(f"Missing document_id for evidence {row['id']}")
                        self.stats['evidence']['skipped'] += 1
                        continue

                    evidence = Evidence(
                        evaluation_id=pg_eval_id,
                        citation_text=row['citation_text'] or '',
                        document_id=document_id,
                        pmid=row['pmid'],
                        doi=row['doi'],
                        relevance_score=row['relevance_score'],
                        supports_statement=row['supports_statement']
                    )

                    if not self.dry_run:
                        self.pg_db.insert_evidence(evidence)
                        self.stats['evidence']['migrated'] += 1
                    else:
                        self.stats['evidence']['migrated'] += 1

                    if self.stats['evidence']['migrated'] % 100 == 0:
                        logger.info(f"  Migrated {self.stats['evidence']['migrated']} evidence citations...")

                except Exception as e:
                    logger.error(f"Error migrating evidence {row['id']}: {e}")
                    self.stats['evidence']['errors'] += 1

        logger.info(f"✓ Evidence: {self.stats['evidence']['migrated']}/{self.stats['evidence']['total']}")

    def migrate_human_annotations(self):
        """Migrate human_annotations table."""
        logger.info("Migrating human annotations...")

        with self.get_sqlite_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM human_annotations")
            rows = cursor.fetchall()

            self.stats['human_annotations']['total'] = len(rows)

            for row in rows:
                try:
                    sqlite_stmt_id = row['statement_id']
                    sqlite_annotator_id = row['annotator_id']

                    # Skip if references weren't migrated
                    if sqlite_stmt_id not in self.statement_id_map and not self.dry_run:
                        logger.warning(f"Skipping annotation {row['id']}: statement {sqlite_stmt_id} not found")
                        self.stats['human_annotations']['skipped'] += 1
                        continue

                    if sqlite_annotator_id not in self.annotator_id_map and not self.dry_run:
                        logger.warning(f"Skipping annotation {row['id']}: annotator {sqlite_annotator_id} not found")
                        self.stats['human_annotations']['skipped'] += 1
                        continue

                    pg_stmt_id = self.statement_id_map.get(sqlite_stmt_id, sqlite_stmt_id)
                    pg_annotator_id = self.annotator_id_map.get(sqlite_annotator_id, sqlite_annotator_id)

                    annotation = HumanAnnotation(
                        statement_id=pg_stmt_id,
                        annotator_id=pg_annotator_id,
                        annotation=row['annotation'],
                        explanation=row['explanation'],
                        confidence=row['confidence'],
                        review_duration_seconds=row['review_duration_seconds'],
                        session_id=row['session_id']
                    )

                    if not self.dry_run:
                        self.pg_db.insert_human_annotation(annotation)
                        self.stats['human_annotations']['migrated'] += 1
                    else:
                        self.stats['human_annotations']['migrated'] += 1

                except Exception as e:
                    logger.error(f"Error migrating human annotation {row['id']}: {e}")
                    self.stats['human_annotations']['errors'] += 1

        logger.info(f"✓ Human Annotations: {self.stats['human_annotations']['migrated']}/{self.stats['human_annotations']['total']}")

    def migrate_processing_metadata(self):
        """Migrate processing_metadata table."""
        logger.info("Migrating processing metadata...")

        with self.get_sqlite_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM processing_metadata")
            rows = cursor.fetchall()

            self.stats['processing_metadata']['total'] = len(rows)

            for row in rows:
                try:
                    session_data = {
                        'session_id': row['session_id'],
                        'input_file': row['input_file'],
                        'total_statements': row['total_statements'] or 0,
                        'start_time': row['start_time'],
                        'status': row['status'] or 'completed',
                        'config_snapshot': row['config_snapshot']
                    }

                    if not self.dry_run:
                        self.pg_db.insert_processing_session(session_data)

                        # Update end_time and other fields if present
                        updates = {}
                        if row['end_time']:
                            updates['end_time'] = row['end_time']
                        if row['output_file']:
                            updates['output_file'] = row['output_file']
                        if row['processed_statements']:
                            updates['processed_statements'] = row['processed_statements']
                        if row['error_message']:
                            updates['error_message'] = row['error_message']

                        if updates:
                            self.pg_db.update_processing_session(row['session_id'], updates)

                        self.stats['processing_metadata']['migrated'] += 1
                    else:
                        self.stats['processing_metadata']['migrated'] += 1

                except Exception as e:
                    logger.error(f"Error migrating processing metadata {row['id']}: {e}")
                    self.stats['processing_metadata']['errors'] += 1

        logger.info(f"✓ Processing Metadata: {self.stats['processing_metadata']['migrated']}/{self.stats['processing_metadata']['total']}")

    def migrate_export_history(self):
        """Migrate export_history table."""
        logger.info("Migrating export history...")

        with self.get_sqlite_connection() as conn:
            cursor = conn.cursor()

            # Check if export_history table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='export_history'")
            if not cursor.fetchone():
                logger.info("  No export_history table found in SQLite database")
                return

            cursor.execute("SELECT * FROM export_history")
            rows = cursor.fetchall()

            self.stats['export_history']['total'] = len(rows)

            if len(rows) == 0:
                logger.info("  No export history records to migrate")
                return

            for row in rows:
                try:
                    if not self.dry_run:
                        # Insert directly using database manager
                        with self.pg_db.db_manager.get_connection() as pg_conn:
                            with pg_conn.cursor() as cur:
                                cur.execute("""
                                    INSERT INTO factcheck.export_history
                                    (export_date, export_type, output_file, statement_count, requested_by, filters_applied)
                                    VALUES (%s, %s, %s, %s, %s, %s)
                                """, (
                                    row['export_date'],
                                    row['export_type'],
                                    row['output_file'],
                                    row['statement_count'],
                                    row['requested_by'],
                                    row['filters_applied']
                                ))
                        self.stats['export_history']['migrated'] += 1
                    else:
                        self.stats['export_history']['migrated'] += 1

                except Exception as e:
                    logger.error(f"Error migrating export history {row['id']}: {e}")
                    self.stats['export_history']['errors'] += 1

        logger.info(f"✓ Export History: {self.stats['export_history']['migrated']}/{self.stats['export_history']['total']}")

    def print_summary(self):
        """Print migration summary."""
        logger.info("\n" + "=" * 80)
        logger.info("MIGRATION SUMMARY")
        logger.info("=" * 80)

        for table_name, stats in self.stats.items():
            if stats['total'] > 0:
                logger.info(f"\n{table_name.upper()}:")
                logger.info(f"  Total:    {stats['total']}")
                logger.info(f"  Migrated: {stats['migrated']}")
                logger.info(f"  Skipped:  {stats['skipped']}")
                logger.info(f"  Errors:   {stats['errors']}")

        # Calculate totals
        total_records = sum(s['total'] for s in self.stats.values())
        total_migrated = sum(s['migrated'] for s in self.stats.values())
        total_errors = sum(s['errors'] for s in self.stats.values())

        logger.info("\n" + "-" * 80)
        logger.info(f"TOTAL RECORDS:  {total_records}")
        logger.info(f"TOTAL MIGRATED: {total_migrated}")
        logger.info(f"TOTAL ERRORS:   {total_errors}")
        logger.info("=" * 80)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Migrate fact-checker data from SQLite to PostgreSQL',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        '--sqlite-db',
        required=True,
        help='Path to SQLite database file'
    )
    parser.add_argument(
        '--skip-existing',
        action='store_true',
        help='Skip statements that already exist in PostgreSQL'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be migrated without actually migrating'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Show detailed progress information'
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        migrator = SQLiteToPostgresMigrator(
            sqlite_path=args.sqlite_db,
            skip_existing=args.skip_existing,
            dry_run=args.dry_run
        )
        migrator.migrate_all()

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
