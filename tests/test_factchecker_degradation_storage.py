"""
Storage of "partial evidence" flags (``degradation_notes``) for fact-check verdicts.

A verdict reached although part of the evidence could not be examined is
stored with notes saying what is missing (migration 034), shown to reviewers,
and carried into SQLite review packages and JSON exports. A failed check
(evaluation ``'error'``) is never imported as a verdict.

Hermetic: PostgreSQL access goes through a mocked DatabaseManager; the SQLite
review package is a temporary file built from the shipped schema.
"""

import json
import sqlite3
from pathlib import Path
from typing import Any, List, Optional
from unittest.mock import MagicMock, patch

import pytest
from psycopg.types.json import Jsonb

from bmlibrarian.factchecker.db.database import AIEvaluation, FactCheckerDB
from bmlibrarian.factchecker.db.sqlite_db import SQLiteFactCheckerDB
from bmlibrarian.gui.qt.plugins.fact_checker.fact_checker_tab import format_ai_rationale

REPO = Path(__file__).parent.parent
MIGRATION = REPO / "migrations" / "034_factcheck_degradation_notes.sql"
SQLITE_SCHEMA = REPO / "src" / "bmlibrarian" / "factchecker" / "db" / "sqlite_schema.sql"


def _pg_db(fetchone: Any = None) -> tuple[FactCheckerDB, MagicMock]:
    """A FactCheckerDB whose connection is a mock; returns (db, cursor)."""
    db = FactCheckerDB.__new__(FactCheckerDB)
    cursor = MagicMock()
    cursor.fetchone.return_value = fetchone
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    db.db_manager = MagicMock()
    db.db_manager.get_connection.return_value.__enter__.return_value = conn
    return db, cursor


# ---- migration --------------------------------------------------------------


def test_migration_adds_the_column_idempotently() -> None:
    """Golden rules 15/16: idempotent, no tracking code of its own."""
    sql = MIGRATION.read_text()

    assert "ADD COLUMN IF NOT EXISTS degradation_notes JSONB" in sql
    assert "schema_migrations" not in sql
    assert "bmlibrarian_migrations" not in sql


# ---- PostgreSQL -------------------------------------------------------------


@pytest.mark.parametrize("notes", [["bm25 search failed: timeout"], None])
def test_insert_stores_the_notes_as_jsonb(notes: Optional[List[str]]) -> None:
    """The notes go into the degradation_notes column (NULL for a complete check)."""
    db, cursor = _pg_db(fetchone=(5,))

    db.insert_ai_evaluation(AIEvaluation(
        statement_id=1, evaluation="yes", reason="r", confidence="low",
        degradation_notes=notes,
    ))

    sql, params = cursor.execute.call_args.args
    assert "degradation_notes" in sql
    stored = [p for p in params if isinstance(p, Jsonb)]
    if notes is None:
        assert stored == []
    else:
        assert [p.obj for p in stored] == [notes]


def test_latest_evaluation_reads_the_notes() -> None:
    """Reading a verdict back keeps its notes."""
    row = (
        3, 1, "maybe", "r", "low", 4, 0, 0, 0, None, None, "m", None, None, "sess", 1,
        ["1 of 4 documents could not be scored"],
    )
    db, _ = _pg_db(fetchone=row)

    evaluation = db.get_latest_ai_evaluation(1)

    assert evaluation is not None
    assert evaluation.degradation_notes == ["1 of 4 documents could not be scored"]


def test_json_import_never_stores_a_failed_check(tmp_path: Path) -> None:
    """An exported 'error' result is a statement to re-check, not a verdict."""
    results = [
        {"statement": "failed", "evaluation": "error", "reason": "search failed"},
        {"statement": "partial", "evaluation": "yes", "reason": "r", "confidence": "low",
         "degradation_notes": ["semantic search failed"]},
    ]
    json_file = tmp_path / "results.json"
    json_file.write_text(json.dumps(results))
    db, _ = _pg_db(fetchone=None)

    with patch.object(db, "insert_statement", return_value=1) as insert_statement, patch.object(
        db, "insert_ai_evaluation", return_value=2
    ) as insert_evaluation:
        stats = db.import_json_results(str(json_file))

    assert insert_statement.call_count == 2
    imported = [c.args[0] for c in insert_evaluation.call_args_list]
    assert [e.evaluation for e in imported] == ["yes"]
    assert imported[0].degradation_notes == ["semantic search failed"]
    assert stats["imported_evaluations"] == 1


# ---- SQLite review packages -------------------------------------------------


def _review_package(tmp_path: Path, with_column: bool) -> SQLiteFactCheckerDB:
    """A review package with one partial-evidence verdict (or an old-format one)."""
    db_file = tmp_path / "review.db"
    conn = sqlite3.connect(db_file)
    schema = SQLITE_SCHEMA.read_text()
    if not with_column:
        schema = schema.replace("    degradation_notes TEXT,  -- JSON list of strings\n", "")
    conn.executescript(schema)
    conn.execute("INSERT INTO statements (statement_id, statement_text) VALUES (1, 's')")
    if with_column:
        conn.execute(
            "INSERT INTO ai_evaluations (evaluation_id, statement_id, evaluation, reason, "
            "version, degradation_notes) VALUES (10, 1, 'maybe', 'r', 1, ?)",
            (json.dumps(["bm25 search failed"]),),
        )
    else:
        conn.execute(
            "INSERT INTO ai_evaluations (evaluation_id, statement_id, evaluation, reason, "
            "version) VALUES (10, 1, 'maybe', 'r', 1)"
        )
    conn.commit()
    conn.close()
    return SQLiteFactCheckerDB(str(db_file))


def test_review_package_returns_the_notes(tmp_path: Path) -> None:
    """Reviewers working from a package see which verdicts are partial."""
    db = _review_package(tmp_path, with_column=True)
    try:
        rows = db.get_all_statements_with_evaluations()
    finally:
        db.conn.close()

    assert rows[0]["degradation_notes"] == ["bm25 search failed"]


def test_old_review_package_without_the_column_still_opens(tmp_path: Path) -> None:
    """Packages exported before migration 034 are read with no notes."""
    db = _review_package(tmp_path, with_column=False)
    try:
        rows = db.get_all_statements_with_evaluations()
    finally:
        db.conn.close()

    assert rows[0]["degradation_notes"] == []


# ---- review GUI -------------------------------------------------------------


def test_rationale_shows_partial_evidence_notes() -> None:
    """The AI rationale panel flags a verdict based on partial evidence."""
    text = format_ai_rationale("Supported by two trials.", ["1 of 5 documents could not be scored"])

    assert text.startswith("Supported by two trials.")
    assert "partial evidence" in text.lower()
    assert "1 of 5 documents could not be scored" in text


def test_rationale_without_notes_is_unchanged() -> None:
    """A complete check shows only its rationale."""
    assert format_ai_rationale("Supported.", []) == "Supported."
    assert format_ai_rationale(None, None) == "No rationale provided"
