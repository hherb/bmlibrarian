"""
Integration test of the EvaluationStore run lifecycle against real SQL (#287).

Opt-in: set BMLIBRARIAN_TEST_DB_ENV to an env file for a *development* database
with the BMLibrarian schema (e.g. ~/.bmlibrarian/.env_pg18_dev). Refuses any
database the test guard protects. The test deletes the run it creates (its
evaluations go with it, ON DELETE CASCADE).
"""

import os
from pathlib import Path
from typing import Iterator

import pytest
from dotenv import dotenv_values

from bmlibrarian.db_test_guard import is_protected_database
from bmlibrarian.evaluations import EvaluationStore, EvaluationType, RunStatus, RunType

pytestmark = pytest.mark.requires_database

TEST_DB_ENV_VARIABLE = "BMLIBRARIAN_TEST_DB_ENV"
TEST_QUESTION = "bmlibrarian test #287: evaluation run lifecycle"
TEST_DOCUMENT_ID = 990000287


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> Iterator[EvaluationStore]:
    """EvaluationStore bound to the opt-in development database; deletes its test runs."""
    env_file = os.environ.get(TEST_DB_ENV_VARIABLE)
    if not env_file:
        pytest.skip(f"{TEST_DB_ENV_VARIABLE} not set")
    cfg = dotenv_values(Path(env_file).expanduser())
    if is_protected_database(cfg.get("POSTGRES_DB")):
        pytest.fail(f"refusing to run against {cfg.get('POSTGRES_DB')!r}")
    for key in ("POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"):
        monkeypatch.setenv(key, cfg[key])
    from bmlibrarian.database import DatabaseManager

    db = DatabaseManager(auto_migrate=True)

    def cleanup() -> None:
        with db.get_connection() as conn:
            conn.execute("DELETE FROM evaluations.evaluation_runs WHERE research_question_text = %s",
                         (TEST_QUESTION,))

    try:
        with db.get_connection() as conn:
            assert conn.execute("SELECT current_database()").fetchone()[0] == cfg["POSTGRES_DB"]
        cleanup()
        yield EvaluationStore(db)
        cleanup()
    finally:
        db.close()


def test_run_lifecycle_failed_reopened_paused_completed(store: EvaluationStore) -> None:
    """failed -> reopen -> paused -> resumed -> completed, as stored in the database."""
    run = store.create_run(RunType.SYSTEMATIC_REVIEW, TEST_QUESTION, documents_total=1)
    assert store.get_run(run.run_id).status == RunStatus.IN_PROGRESS.value

    store.complete_run(run.run_id, status=RunStatus.FAILED, error_message="LLM unreachable")
    failed = store.get_run(run.run_id)
    assert failed.status == RunStatus.FAILED.value
    assert failed.completed_at is not None
    assert failed.error_message == "LLM unreachable"

    reopened = store.reopen_run(run.run_id)
    assert reopened is not None
    assert reopened.run_id == run.run_id
    assert reopened.run_type == RunType.SYSTEMATIC_REVIEW.value
    assert reopened.research_question_text == TEST_QUESTION
    assert reopened.documents_total == 1
    assert reopened.started_at == failed.started_at
    assert (reopened.status, reopened.completed_at, reopened.error_message) == (
        RunStatus.IN_PROGRESS.value, None, None)
    assert store.get_run(run.run_id) == reopened

    store.pause_run(run.run_id)
    assert store.get_run(run.run_id).status == RunStatus.PAUSED.value
    store.resume_run(run.run_id)
    assert store.get_run(run.run_id).status == RunStatus.IN_PROGRESS.value

    store.complete_run(run.run_id)
    completed = store.get_run(run.run_id)
    assert completed.status == RunStatus.COMPLETED.value
    assert completed.completed_at is not None
    assert completed.error_message is None


def test_reopen_unknown_run_returns_none(store: EvaluationStore) -> None:
    """Reopening a run id that does not exist returns None."""
    run = store.create_run(RunType.SYSTEMATIC_REVIEW, TEST_QUESTION)
    assert store.reopen_run(run.run_id + 1_000_000) is None


def test_save_evaluation_overwrites_same_run_document_and_type(store: EvaluationStore) -> None:
    """Re-saving an evaluation replaces it: a resume can overwrite a stale row."""
    run = store.create_run(RunType.SYSTEMATIC_REVIEW, TEST_QUESTION)
    for score, rationale in ((0.0, "Scoring failed: timeout"), (4.0, "Directly relevant")):
        store.save_evaluation(run.run_id, TEST_DOCUMENT_ID, EvaluationType.RELEVANCE_SCORE,
                              {"score": score, "rationale": rationale},
                              primary_score=score, reasoning=rationale)
    [saved] = store.get_evaluations_for_run(run.run_id, EvaluationType.RELEVANCE_SCORE)
    assert (saved.document_id, saved.primary_score, saved.reasoning) == (
        TEST_DOCUMENT_ID, 4.0, "Directly relevant")
    assert store.get_run(run.run_id).documents_processed == 1
