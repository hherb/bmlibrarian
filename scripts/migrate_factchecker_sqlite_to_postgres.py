#!/usr/bin/env python3
"""
Migration Script: SQLite Fact-Checker Database to PostgreSQL

Migrates all fact-checker data from legacy SQLite database to PostgreSQL factcheck schema.

Usage:
    uv run python scripts/migrate_factchecker_sqlite_to_postgres.py --sqlite-db /path/to/factchecker.db
    uv run python scripts/migrate_factchecker_sqlite_to_postgres.py --sqlite-db /path/to/factchecker.db --skip-existing
    uv run python scripts/migrate_factchecker_sqlite_to_postgres.py --sqlite-db /path/to/factchecker.db --dry-run

Options:
    --sqlite-db PATH     Path to SQLite database file (required)
    --skip-existing      Don't migrate evaluations for statements already evaluated in PostgreSQL
    --dry-run           Count what would be migrated (an upper bound: --skip-existing
                        and PostgreSQL constraint checks are not applied)
    --verbose           Also log skipped already-evaluated statements

Exits 1 if any record failed to migrate; the summary lists the failed statements.
"""

import argparse
import sqlite3
import logging
import sys
from itertools import groupby
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import psycopg

from bmlibrarian.factchecker.db.database import (
    STORABLE_VERDICTS,
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

# Log a progress line every this many migrated rows
PROGRESS_INTERVAL = 100

# Errors caused by one row's data, caught per row in every step (#395);
# anything else (connection lost, schema mismatch, bugs) aborts the run instead
# of failing every remaining row the same way. ValueError covers malformed
# agent_config/config_snapshot JSON and a statement row that has disappeared.
ROW_ERRORS = (psycopg.IntegrityError, psycopg.DataError, ValueError)

# Statuses factcheck.statements accepts (CHECK constraint, migration 008)
REVIEW_STATUSES = ('pending', 'in_review', 'completed', 'flagged')
DEFAULT_REVIEW_STATUS = 'pending'


def legacy_verdict(row: sqlite3.Row) -> str:
    """Return the row's evaluation normalised like the PostgreSQL verdicts ('Yes ' -> 'yes')."""
    return (row['evaluation'] or '').strip().lower()


def legacy_review_status(row: sqlite3.Row) -> str:
    """
    Return the row's review status normalised (' Flagged ' -> 'flagged'; NULL/blank -> 'pending').

    Never raises: SQLite columns are untyped, so a non-text value (even 0) is
    stringified and then rejected by ``restore_review_status`` after the statement is mapped.
    """
    raw = row['review_status']
    return ('' if raw is None else str(raw)).strip().lower() or DEFAULT_REVIEW_STATUS


def evaluation_from_row(row: sqlite3.Row) -> AIEvaluation:
    """
    Build an AIEvaluation from a legacy SQLite ``ai_evaluations`` row.

    ``statement_id`` is left unset; ``FactCheckerDB.store_verdicts`` fills it in.

    Args:
        row: Row with the legacy column names.

    Returns:
        The evaluation (its version is reassigned on insert).
    """
    return AIEvaluation(
        evaluation=legacy_verdict(row),
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


def evidence_from_row(row: sqlite3.Row) -> Optional[Evidence]:
    """
    Build an Evidence item from a legacy SQLite ``evidence`` row.

    ``evaluation_id`` is left unset; ``FactCheckerDB.store_verdicts`` fills it in.

    Args:
        row: Row with the legacy column names.

    Returns:
        The evidence, or None if ``document_id`` is missing, not an integer
        or not positive (evidence must reference a ``public.document`` row).
    """
    raw = row['document_id']
    # isdecimal, not isdigit: '²' is a digit that int() rejects
    if isinstance(raw, str) and raw.strip().isdecimal():
        document_id = int(raw)
    elif isinstance(raw, int) and not isinstance(raw, bool):
        document_id = raw
    else:
        return None
    if document_id <= 0:
        return None
    return Evidence(
        citation_text=row['citation_text'] or '',
        document_id=document_id,
        pmid=row['pmid'],
        doi=row['doi'],
        relevance_score=row['relevance_score'],
        supports_statement=row['supports_statement']
    )


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
            skip_existing: Don't migrate evaluations for statements that already
                had one in PostgreSQL (without it, a re-run stores them as new versions)
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
            # dropped: no usable document_id, so its verdict is stored without it (as in #340)
            'evidence': {'total': 0, 'migrated': 0, 'dropped': 0, 'skipped': 0, 'errors': 0},
            'human_annotations': {'total': 0, 'migrated': 0, 'skipped': 0, 'errors': 0},
            'processing_metadata': {'total': 0, 'migrated': 0, 'skipped': 0, 'errors': 0},
            'export_history': {'total': 0, 'migrated': 0, 'skipped': 0, 'errors': 0},
        }

        # Map SQLite statement IDs to PostgreSQL statement IDs
        self.statement_id_map: Dict[int, int] = {}

        # Map SQLite annotator IDs to PostgreSQL annotator IDs
        self.annotator_id_map: Dict[int, int] = {}

        # SQLite statement IDs -> the Statement migrated for them (store_verdicts reuses it)
        self.statements: Dict[int, Statement] = {}

        # SQLite statement IDs none of whose evaluations could be migrated
        self.failed_statements: List[int] = []

    def get_sqlite_connection(self):
        """Get SQLite database connection."""
        conn = sqlite3.connect(str(self.sqlite_path))
        conn.row_factory = sqlite3.Row
        return conn

    def migrate_all(self) -> bool:
        """
        Run complete migration.

        Returns:
            True if no record failed to migrate.
        """
        logger.info(f"Starting migration from {self.sqlite_path}")
        logger.info(f"Dry run: {self.dry_run}")
        logger.info(f"Skip existing: {self.skip_existing}")
        logger.info("-" * 80)

        try:
            # Order matters due to foreign key constraints
            self.migrate_statements()
            self.migrate_annotators()
            self.migrate_verdicts()
            self.migrate_human_annotations()
            self.migrate_processing_metadata()
            self.migrate_export_history()

            self.print_summary()
            ok = sum(s['errors'] for s in self.stats.values()) == 0

            if self.dry_run:
                logger.info("\n⚠️  DRY RUN - No data was actually migrated")
            elif ok:
                logger.info("\n✅ Migration completed successfully!")
            else:
                logger.error("\n❌ Migration finished with errors (see the summary above)")
            return ok

        except Exception as e:
            self.print_summary()
            logger.error(f"Migration aborted: {e}. Rows counted as migrated above are "
                         f"already committed; re-run with --skip-existing so their "
                         f"evaluations are not stored again as new versions.",
                         exc_info=True)
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
                        review_status=legacy_review_status(row)
                    )

                    pg_id = None
                    if not self.dry_run:
                        # This will return existing ID if statement already exists
                        pg_id = self.pg_db.insert_statement(statement)
                        # Mapped before the status, so its verdicts migrate even if the status fails
                        self.statement_id_map[sqlite_id] = pg_id
                        self.statements[sqlite_id] = statement
                    self.stats['statements']['migrated'] += 1
                    try:
                        self.restore_review_status(pg_id, statement.review_status)
                    except ROW_ERRORS as e:
                        logger.error(f"Statement {sqlite_id} migrated, but its review_status was not restored: {e}")
                        self.stats['statements']['errors'] += 1

                    if self.stats['statements']['migrated'] % PROGRESS_INTERVAL == 0:
                        logger.info(f"  Migrated {self.stats['statements']['migrated']} statements...")

                except ROW_ERRORS as e:
                    logger.error(f"Error migrating statement {row['id']}: {e}")
                    self.stats['statements']['errors'] += 1

        logger.info(f"✓ Statements: {self.stats['statements']['migrated']}/{self.stats['statements']['total']}")

    def restore_review_status(self, pg_id: Optional[int], status: str) -> None:
        """
        Give the PostgreSQL statement its legacy review status (#392).

        ``insert_statement`` never writes ``review_status``, so a new statement
        starts as 'pending'. A non-pending status already set in PostgreSQL is
        kept (and the legacy value then not checked), so a re-run does not undo
        a review done there since; 'pending' counts as unset, so a statement
        reset to 'pending' in PostgreSQL gets the legacy status again.

        Args:
            pg_id: PostgreSQL statement id (None in a dry run: only validate)
            status: Normalised legacy review status

        Raises:
            ValueError: ``status`` is not one factcheck.statements accepts and
                the PostgreSQL statement is still 'pending'
        """
        if status == DEFAULT_REVIEW_STATUS:
            return
        if pg_id is not None:
            current = self.pg_db.get_statement(pg_id)
            if current is not None and current.review_status != DEFAULT_REVIEW_STATUS:
                if current.review_status != status:
                    logger.info(f"Statement {pg_id}: kept PostgreSQL review_status "
                                f"{current.review_status!r} (legacy: {status!r})")
                return
        if status not in REVIEW_STATUSES:
            raise ValueError(f"invalid review_status {status!r} (allowed: {', '.join(REVIEW_STATUSES)})")
        if pg_id is not None:
            self.pg_db.update_statement_review_status(pg_id, status)

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

                except ROW_ERRORS as e:
                    logger.error(f"Error migrating annotator {row['id']}: {e}")
                    self.stats['annotators']['errors'] += 1

        logger.info(f"✓ Annotators: {self.stats['annotators']['migrated']}/{self.stats['annotators']['total']}")

    def migrate_verdicts(self) -> None:
        """
        Migrate AI evaluations with their evidence, one transaction per statement.

        All evaluations of a statement are stored with
        ``FactCheckerDB.store_verdicts`` (#376), so a verdict is never
        committed without its evidence and an older version is never left as
        the latest when a newer one fails: if any insert fails, nothing of the
        statement's evaluations is stored, they count as errors and the
        statement id is listed in the summary. A statement first evaluated by
        this run then stays unevaluated, so ``fact_checker_cli.py
        --incremental`` checks it again; one that already had verdicts in
        PostgreSQL keeps them. 'error' evaluations (failed checks) are not
        verdicts and are skipped. Evidence without a usable ``document_id``
        cannot be stored; it is dropped (counted as such) and its verdict is
        stored without it, as ``import_json_results`` does.
        """
        logger.info("Migrating AI evaluations with their evidence...")

        with self.get_sqlite_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM ai_evaluations ORDER BY statement_id, version, id")
            rows = cursor.fetchall()
            cursor.execute("SELECT * FROM evidence ORDER BY id")
            evidence_by_eval: Dict[int, List[sqlite3.Row]] = {}
            for ev_row in cursor.fetchall():
                evidence_by_eval.setdefault(ev_row['ai_evaluation_id'], []).append(ev_row)

        eval_stats = self.stats['ai_evaluations']
        ev_stats = self.stats['evidence']
        eval_stats['total'] = len(rows)
        ev_stats['total'] = sum(len(v) for v in evidence_by_eval.values())
        known_eval_ids = {row['id'] for row in rows}
        orphans = sum(len(v) for k, v in evidence_by_eval.items() if k not in known_eval_ids)
        if orphans:
            logger.warning(f"Skipping {orphans} evidence rows whose evaluation does not exist")
            ev_stats['skipped'] += orphans
        if self.dry_run:
            logger.info("  Dry run: counts are an upper bound (--skip-existing and "
                        "PostgreSQL constraints are not checked)")

        # PostgreSQL statements given verdicts by this run (two legacy ids can share one)
        stored_this_run: Set[int] = set()

        for sqlite_stmt_id, group in groupby(rows, key=lambda r: r['statement_id']):
            verdict_rows = []
            for row in group:
                if legacy_verdict(row) in STORABLE_VERDICTS:
                    verdict_rows.append(row)
                else:
                    logger.warning(f"Skipping evaluation {row['id']}: {row['evaluation']!r} is not a verdict")
                    eval_stats['skipped'] += 1
                    ev_stats['skipped'] += len(evidence_by_eval.get(row['id'], []))
            if not verdict_rows:
                continue
            n_evidence = sum(len(evidence_by_eval.get(r['id'], [])) for r in verdict_rows)

            statement = self.statements.get(sqlite_stmt_id)
            if statement is None and not self.dry_run:
                logger.warning(f"Skipping {len(verdict_rows)} evaluation(s): statement {sqlite_stmt_id} not migrated")
                eval_stats['skipped'] += len(verdict_rows)
                ev_stats['skipped'] += n_evidence
                continue

            if self.skip_existing and not self.dry_run:
                pg_stmt_id = self.statement_id_map[sqlite_stmt_id]
                if pg_stmt_id not in stored_this_run and self.pg_db.get_latest_ai_evaluation(pg_stmt_id) is not None:
                    logger.debug(f"Skipping statement {sqlite_stmt_id}: already evaluated in PostgreSQL")
                    eval_stats['skipped'] += len(verdict_rows)
                    ev_stats['skipped'] += n_evidence
                    continue

            verdicts: List[Tuple[AIEvaluation, List[Evidence]]] = []
            for row in verdict_rows:
                evidence = []
                for ev_row in evidence_by_eval.get(row['id'], []):
                    item = evidence_from_row(ev_row)
                    if item is None:
                        logger.warning(f"Dropping evidence {ev_row['id']}: invalid document_id {ev_row['document_id']!r}")
                        ev_stats['dropped'] += 1
                    else:
                        evidence.append(item)
                verdicts.append((evaluation_from_row(row), evidence))
            n_usable = sum(len(evidence) for _, evidence in verdicts)

            if self.dry_run:
                eval_stats['migrated'] += len(verdicts)
                ev_stats['migrated'] += n_usable
                continue
            assert statement is not None  # only a dry run gets past the check above without one

            try:
                pg_stmt_id, _ = self.pg_db.store_verdicts(statement, verdicts)
            except ROW_ERRORS as e:
                logger.error(f"Statement {sqlite_stmt_id}: none of its {len(verdicts)} evaluation(s) "
                             f"migrated, rolled back with their evidence: {e}")
                self.failed_statements.append(sqlite_stmt_id)
                eval_stats['errors'] += len(verdicts)
                ev_stats['errors'] += n_usable
                continue

            stored_this_run.add(pg_stmt_id)
            before = eval_stats['migrated']
            eval_stats['migrated'] += len(verdicts)
            ev_stats['migrated'] += n_usable
            if eval_stats['migrated'] // PROGRESS_INTERVAL > before // PROGRESS_INTERVAL:
                logger.info(f"  Migrated {eval_stats['migrated']} evaluations...")

        logger.info(f"✓ AI Evaluations: {eval_stats['migrated']}/{eval_stats['total']}")
        logger.info(f"✓ Evidence: {ev_stats['migrated']}/{ev_stats['total']}")

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

                except ROW_ERRORS as e:
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

                except ROW_ERRORS as e:
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

                except ROW_ERRORS as e:
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
                if 'dropped' in stats:
                    logger.info(f"  Dropped:  {stats['dropped']}")
                logger.info(f"  Errors:   {stats['errors']}")

        # Calculate totals
        total_records = sum(s['total'] for s in self.stats.values())
        total_migrated = sum(s['migrated'] for s in self.stats.values())
        total_errors = sum(s['errors'] for s in self.stats.values())

        logger.info("\n" + "-" * 80)
        logger.info(f"TOTAL RECORDS:  {total_records}")
        logger.info(f"TOTAL MIGRATED: {total_migrated}")
        logger.info(f"TOTAL ERRORS:   {total_errors}")
        if self.failed_statements:
            logger.info(f"STATEMENTS WITHOUT MIGRATED EVALUATIONS (SQLite ids): "
                        f"{', '.join(map(str, self.failed_statements))}")
        logger.info("=" * 80)


def main() -> None:
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
        help="Don't migrate evaluations for statements already evaluated in PostgreSQL"
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Count what would be migrated without migrating (an upper bound)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Also log skipped already-evaluated statements'
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
        ok = migrator.migrate_all()

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)
    if not ok:
        sys.exit(1)


if __name__ == '__main__':
    main()
