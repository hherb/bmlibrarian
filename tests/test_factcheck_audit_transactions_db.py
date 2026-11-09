"""
Real-SQL checks that failed writes leave nothing behind (#340, #341) and that
concurrent evaluations of one statement do not collide (#230).

Opt-in: set BMLIBRARIAN_TEST_DB_ENV to an env file for a *development* database
with the BMLibrarian schema (e.g. ~/.bmlibrarian/.env_pg18_dev). Refuses any
database the test guard protects. Most tests make a write fail on a foreign
key; the test statement is deleted before and after each test.
"""

import os
from pathlib import Path
from typing import Iterator

import psycopg
import pytest
from dotenv import dotenv_values

from bmlibrarian.db_test_guard import is_protected_database

pytestmark = pytest.mark.requires_database

TEST_DB_ENV_VARIABLE = "BMLIBRARIAN_TEST_DB_ENV"
TEST_STATEMENT = "bmlibrarian test #340: verdict stored without its evidence"
CONNECTION_DEFAULTS = {"POSTGRES_HOST": "localhost", "POSTGRES_PORT": "5432"}
# public.document ids and audit ids are positive serials, so no row has this id
NONEXISTENT_ID = -340
TEST_SESSION_ID = "bmlibrarian-test-408"
# Largest INTEGER (public.document.id's type): a positive id no imported document has
UNUSED_DOCUMENT_ID = 2**31 - 1


@pytest.fixture
def db_manager(monkeypatch: pytest.MonkeyPatch) -> Iterator["DatabaseManager"]:  # noqa: F821
    """DatabaseManager bound to the opt-in development database."""
    env_file = os.environ.get(TEST_DB_ENV_VARIABLE)
    if not env_file:
        pytest.skip(f"{TEST_DB_ENV_VARIABLE} not set")
    cfg = dotenv_values(Path(env_file).expanduser())
    if is_protected_database(cfg.get("POSTGRES_DB")):
        pytest.fail(f"refusing to run against {cfg.get('POSTGRES_DB')!r}")
    for key in ("POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"):
        value = cfg.get(key) or CONNECTION_DEFAULTS.get(key)
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    from bmlibrarian.database import DatabaseManager

    db = DatabaseManager(auto_migrate=True)

    def cleanup() -> None:
        with db.get_connection() as conn:
            conn.execute("DELETE FROM factcheck.statements WHERE statement_text = %s", (TEST_STATEMENT,))

    try:
        with db.get_connection() as conn:
            assert conn.execute("SELECT current_database()").fetchone()[0] == cfg["POSTGRES_DB"]
        cleanup()
        yield db
        cleanup()
    finally:
        db.close()


def test_failed_evidence_insert_leaves_no_verdict(db_manager) -> None:
    """An evidence row that cannot be inserted rolls back its statement and evaluation."""
    from bmlibrarian.factchecker.db.database import AIEvaluation, Evidence, FactCheckerDB, Statement

    db = FactCheckerDB.__new__(FactCheckerDB)
    db.db_manager = db_manager

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        db.store_verdict(
            Statement(statement_text=TEST_STATEMENT, source_file="test"),
            AIEvaluation(evaluation="yes", reason="r", model_used="test"),
            [Evidence(citation_text="c", document_id=NONEXISTENT_ID)],
        )

    with db_manager.get_connection() as conn:
        rows = conn.execute(
            "SELECT count(*) FROM factcheck.statements s "
            "JOIN factcheck.ai_evaluations e USING (statement_id) WHERE s.statement_text = %s",
            (TEST_STATEMENT,),
        ).fetchone()[0]
        statements = conn.execute(
            "SELECT count(*) FROM factcheck.statements WHERE statement_text = %s", (TEST_STATEMENT,)
        ).fetchone()[0]
    assert (rows, statements) == (0, 0)


def test_failed_verdict_keeps_an_existing_statement_unevaluated(db_manager) -> None:
    """A statement already stored (e.g. imported) stays, with no evaluation, so incremental mode re-checks it."""
    from bmlibrarian.factchecker.db.database import AIEvaluation, Evidence, FactCheckerDB, Statement

    db = FactCheckerDB.__new__(FactCheckerDB)
    db.db_manager = db_manager
    statement_id = db.insert_statement(Statement(statement_text=TEST_STATEMENT, source_file="test"))

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        db.store_verdict(
            Statement(statement_text=TEST_STATEMENT, source_file="test"),
            AIEvaluation(evaluation="yes", reason="r", model_used="test"),
            [Evidence(citation_text="c", document_id=NONEXISTENT_ID)],
        )

    with db_manager.get_connection() as conn:
        evaluations = conn.execute(
            "SELECT count(*) FROM factcheck.ai_evaluations WHERE statement_id = %s", (statement_id,)
        ).fetchone()[0]
        statements = conn.execute(
            "SELECT count(*) FROM factcheck.statements WHERE statement_id = %s", (statement_id,)
        ).fetchone()[0]
    assert (evaluations, statements) == (0, 1)


def test_failed_newer_version_rolls_back_the_older_one(db_manager) -> None:
    """store_verdicts is one transaction: version 2 failing leaves no version 1 as the latest (#376)."""
    from bmlibrarian.factchecker.db.database import AIEvaluation, Evidence, FactCheckerDB, Statement

    db = FactCheckerDB.__new__(FactCheckerDB)
    db.db_manager = db_manager
    statement_id = db.insert_statement(Statement(statement_text=TEST_STATEMENT, source_file="test"))

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        db.store_verdicts(Statement(statement_text=TEST_STATEMENT, source_file="test"), [
            (AIEvaluation(evaluation="no", reason="v1", model_used="test"), []),
            (AIEvaluation(evaluation="yes", reason="v2", model_used="test"),
             [Evidence(citation_text="c", document_id=NONEXISTENT_ID)]),
        ])

    with db_manager.get_connection() as conn:
        evaluations = conn.execute(
            "SELECT count(*) FROM factcheck.ai_evaluations WHERE statement_id = %s", (statement_id,)
        ).fetchone()[0]
    assert evaluations == 0


def test_failed_audit_write_does_not_poison_the_connection(db_manager) -> None:
    """After a tracker write fails, the shared audit connection still works."""
    from bmlibrarian.audit import CitationTracker

    conn = db_manager._pool.getconn()
    try:
        tracker = CitationTracker(conn)
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            tracker.record_citation(
                research_question_id=NONEXISTENT_ID, document_id=NONEXISTENT_ID,
                session_id=NONEXISTENT_ID, scoring_id=NONEXISTENT_ID,
                evaluator_id=NONEXISTENT_ID, passage="p", summary="s", relevance_confidence=0.5,
            )

        # Was InFailedSqlTransaction before #341
        assert tracker.get_citations_for_document(NONEXISTENT_ID, NONEXISTENT_ID) == []
    finally:
        conn.rollback()
        db_manager._pool.putconn(conn)


# How long the second writer is given to show it waits for the first (#230)
BLOCKED_WRITER_WAIT_S = 1.0


def test_concurrent_evaluations_get_consecutive_versions(db_manager) -> None:
    """A writer whose first evaluation is still uncommitted makes a second writer wait, not collide (#230)."""
    import threading

    from bmlibrarian.factchecker.db.database import AIEvaluation, FactCheckerDB, Statement

    db = FactCheckerDB.__new__(FactCheckerDB)
    db.db_manager = db_manager
    statement_id = db.insert_statement(Statement(statement_text=TEST_STATEMENT, source_file="test"))
    errors: list[BaseException] = []

    def second_writer() -> None:
        """Insert an evaluation on its own pooled connection."""
        try:
            db.insert_ai_evaluation(AIEvaluation(statement_id=statement_id, evaluation="no", reason="r"))
        except BaseException as exc:  # reported by the assertion below
            errors.append(exc)

    with db_manager.get_connection() as first:
        db.insert_ai_evaluation(AIEvaluation(statement_id=statement_id, evaluation="yes", reason="r"), conn=first)
        writer = threading.Thread(target=second_writer)
        writer.start()
        writer.join(BLOCKED_WRITER_WAIT_S)
        assert writer.is_alive(), "second writer did not wait for the first transaction"
    writer.join()

    assert errors == []
    with db_manager.get_connection() as conn:
        versions = conn.execute(
            "SELECT evaluation, version FROM factcheck.ai_evaluations WHERE statement_id = %s ORDER BY version",
            (statement_id,),
        ).fetchall()
    assert versions == [("yes", 1), ("no", 2)]


def test_review_status_update_of_a_missing_statement_raises(db_manager) -> None:
    """An update that matches no statement is an error, not a silent no-op (#395)."""
    from bmlibrarian.factchecker.db.database import FactCheckerDB

    db = FactCheckerDB.__new__(FactCheckerDB)
    db.db_manager = db_manager

    with pytest.raises(ValueError):
        db.update_statement_review_status(NONEXISTENT_ID, "completed")


def test_review_status_update_of_an_existing_statement_is_stored(db_manager) -> None:
    """The rowcount check does not reject a real update (#395)."""
    from bmlibrarian.factchecker.db.database import FactCheckerDB, Statement

    db = FactCheckerDB.__new__(FactCheckerDB)
    db.db_manager = db_manager
    statement_id = db.insert_statement(Statement(statement_text=TEST_STATEMENT, source_file="test"))

    db.update_statement_review_status(statement_id, "completed")

    with db_manager.get_connection() as conn:
        status = conn.execute(
            "SELECT review_status FROM factcheck.statements WHERE statement_id = %s", (statement_id,)
        ).fetchone()
    assert status == ("completed",)


def _session(**fields: object) -> dict:
    """A test processing session; ``fields`` override the defaults."""
    return {"session_id": TEST_SESSION_ID, "input_file": "in.json", "total_statements": 2,
            "start_time": "2026-01-01T00:00:00+00:00", "status": "completed", "config_snapshot": None,
            **fields}


@pytest.fixture
def session_db(db_manager) -> Iterator["FactCheckerDB"]:  # noqa: F821
    """FactCheckerDB on the dev database; the test session is deleted before and after."""
    from bmlibrarian.factchecker.db.database import FactCheckerDB

    db = FactCheckerDB.__new__(FactCheckerDB)
    db.db_manager = db_manager

    def cleanup() -> None:
        with db_manager.get_connection() as conn:
            conn.execute("DELETE FROM factcheck.processing_metadata WHERE session_id = %s", (TEST_SESSION_ID,))

    cleanup()
    yield db
    cleanup()


def _stored_session(db_manager) -> list:
    """(end_time is set, output_file, processed_statements, error_message) of the test session rows."""
    with db_manager.get_connection() as conn:
        return conn.execute(
            "SELECT end_time IS NOT NULL, output_file, processed_statements, error_message "
            "FROM factcheck.processing_metadata WHERE session_id = %s", (TEST_SESSION_ID,)).fetchall()


def test_session_with_a_bad_end_time_leaves_no_row(session_db, db_manager) -> None:
    """The end fields are in the session's own INSERT, so a bad one stores nothing (#408)."""
    with pytest.raises(psycopg.errors.InvalidDatetimeFormat):
        session_db.insert_processing_session(_session(end_time="not a time"), overwrite=True)
    assert _stored_session(db_manager) == []


def test_overwrite_completes_a_half_migrated_session(session_db, db_manager) -> None:
    """A re-run upserts over a row an older migration left without its end fields (#408)."""
    session_db.insert_processing_session(_session(status="running", processed_statements=None))
    # NULL processed_statements gets the column's default, 0 (the column is NOT NULL)
    assert _stored_session(db_manager) == [(False, None, 0, None)]
    with pytest.raises(psycopg.errors.UniqueViolation):
        session_db.insert_processing_session(_session())

    session_db.insert_processing_session(
        _session(total_statements=3, end_time="2026-01-02T00:00:00+00:00", output_file="out.json",
                 processed_statements=2, error_message="boom"), overwrite=True)

    assert _stored_session(db_manager) == [(True, "out.json", 2, "boom")]
    with db_manager.get_connection() as conn:
        assert conn.execute("SELECT status, total_statements FROM factcheck.processing_metadata "
                            "WHERE session_id = %s", (TEST_SESSION_ID,)).fetchall() == [("completed", 3)]


def test_dry_run_reports_refused_rows_and_keeps_nothing(session_db, db_manager, tmp_path: Path,
                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    """The migrator's dry run writes for real, so PostgreSQL refuses what the real run would; then it rolls back (#410)."""
    import sqlite3

    from tests.test_migrate_factchecker_sqlite import LEGACY_SCHEMA, migrate

    legacy = tmp_path / "factchecker.db"
    with sqlite3.connect(legacy) as conn:
        conn.executescript(LEGACY_SCHEMA)
        conn.execute("INSERT INTO statements (id, statement_text) VALUES (1, ?)", (TEST_STATEMENT,))
        conn.execute("INSERT INTO ai_evaluations (id, statement_id, evaluation, version) VALUES (10, 1, 'yes', 1)")
        conn.execute("INSERT INTO evidence (id, ai_evaluation_id, citation_text, document_id) VALUES (100, 10, 'c', ?)",
                     (str(UNUSED_DOCUMENT_ID),))  # positive, so the migrator keeps it
        conn.execute("INSERT INTO processing_metadata (session_id, input_file, start_time, end_time) "
                     "VALUES (?, 'in.json', '2026-01-01T00:00:00+00:00', 'not a time')", (TEST_SESSION_ID,))
    with db_manager.get_connection() as conn:
        assert conn.execute("SELECT count(*) FROM document WHERE id = %s", (UNUSED_DOCUMENT_ID,)).fetchone() == (0,)
    monkeypatch.setattr(migrate, "FactCheckerDB", lambda: session_db)

    migrator = migrate.SQLiteToPostgresMigrator(str(legacy), dry_run=True)
    assert migrator.migrate_all() is False

    assert migrator.stats["statements"]["migrated"] == 1
    assert migrator.stats["ai_evaluations"]["errors"] == 1  # evidence foreign key
    assert migrator.stats["processing_metadata"]["errors"] == 1  # TIMESTAMPTZ cast
    with db_manager.get_connection() as conn:
        assert conn.execute("SELECT count(*) FROM factcheck.statements WHERE statement_text = %s",
                            (TEST_STATEMENT,)).fetchone() == (0,)
    assert _stored_session(db_manager) == []
