"""Regression test for the fact-checker "latest evaluation" query.

Guards against the no-op LEFT JOIN bug: the ``latest`` (MAX(version))
subquery was joined but never filtered on, so a statement with N evaluation
versions produced N duplicate rows in the review GUI, JSON exports, and
distributed SQLite review packages, instead of one row with the latest
evaluation.

Runs against a real temporary SQLite database built from the shipped
sqlite_schema.sql — hermetic, no PostgreSQL required.
"""

import sqlite3
from pathlib import Path

import pytest

from bmlibrarian.factchecker.db.sqlite_db import SQLiteFactCheckerDB

SCHEMA_PATH = (
    Path(__file__).parent.parent
    / "src" / "bmlibrarian" / "factchecker" / "db" / "sqlite_schema.sql"
)


@pytest.fixture
def review_db(tmp_path: Path) -> SQLiteFactCheckerDB:
    """Create a temp SQLite review package with one statement, two eval versions."""
    db_file = tmp_path / "review_package.db"
    conn = sqlite3.connect(db_file)
    conn.executescript(SCHEMA_PATH.read_text())
    conn.execute(
        "INSERT INTO statements (statement_id, statement_text) VALUES (1, 'Aspirin cures headaches')"
    )
    conn.execute(
        """INSERT INTO ai_evaluations
           (evaluation_id, statement_id, evaluation, reason, version)
           VALUES (10, 1, 'no', 'first pass', 1)"""
    )
    conn.execute(
        """INSERT INTO ai_evaluations
           (evaluation_id, statement_id, evaluation, reason, version)
           VALUES (11, 1, 'yes', 'second pass with better evidence', 2)"""
    )
    # A second statement with no evaluation at all must still appear (LEFT JOIN)
    conn.execute(
        "INSERT INTO statements (statement_id, statement_text) VALUES (2, 'Water is wet')"
    )
    conn.commit()
    conn.close()

    db = SQLiteFactCheckerDB(str(db_file))
    yield db
    db.conn.close()


def test_returns_one_row_per_statement_with_latest_version(review_db) -> None:
    """A re-evaluated statement must appear once, with its newest evaluation."""
    results = review_db.get_all_statements_with_evaluations()

    rows_for_stmt_1 = [r for r in results if r["id"] == 1]
    assert len(rows_for_stmt_1) == 1, (
        f"statement 1 appears {len(rows_for_stmt_1)} times - the latest-version "
        "join is not filtering (one row per evaluation version)"
    )
    assert rows_for_stmt_1[0]["eval_id"] == 11
    assert rows_for_stmt_1[0]["evaluation"] == "yes"


def test_statement_without_evaluation_still_returned(review_db) -> None:
    """LEFT JOIN semantics must be preserved for unevaluated statements."""
    results = review_db.get_all_statements_with_evaluations()

    rows_for_stmt_2 = [r for r in results if r["id"] == 2]
    assert len(rows_for_stmt_2) == 1
    assert rows_for_stmt_2[0]["eval_id"] is None
