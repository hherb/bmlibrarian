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
