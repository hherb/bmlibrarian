"""
Storage of ``Citation.widened_from`` (issue #310).

A passage widened from a quoted fragment to its complete sentence(s) keeps the
fragment in the citation audit trail and in fact-check evidence (migration
035), in SQLite review packages and JSON exports, and is marked where
reviewers see the passage.

Hermetic: PostgreSQL access goes through mocked connections; the SQLite
review package is a temporary file built from the shipped schema.
"""

import importlib.util
import json
import sqlite3
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from bmlibrarian.agents.citation_agent import Citation, CitationFinderAgent
from bmlibrarian.audit.citation_tracker import CitationTracker
from bmlibrarian.factchecker.agent.fact_checker_agent import (
    EvidenceReference,
    FactCheckerAgent,
    FactCheckResult,
)
from bmlibrarian.factchecker.db.database import Evidence, FactCheckerDB
from bmlibrarian.factchecker.db.sqlite_db import SQLiteFactCheckerDB
from bmlibrarian.gui.qt.widgets.card_utils import widened_note

REPO = Path(__file__).parent.parent
MIGRATION = REPO / "migrations" / "035_citation_widened_from.sql"
SQLITE_SCHEMA = REPO / "src" / "bmlibrarian" / "factchecker" / "db" / "sqlite_schema.sql"
EXPORT_SCRIPT = REPO / "scripts" / "export_review_package.py"
SQLITE_COLUMN = (
    "    created_at TEXT,  -- ISO 8601 timestamp\n"
    "    widened_from TEXT  -- quoted fragment, when citation_text was widened to its sentence(s)\n"
)
SQLITE_BEFORE_035 = "    created_at TEXT  -- ISO 8601 timestamp\n"

FRAGMENT = "reduced mortality"
PASSAGE = "Aspirin reduced mortality in the treatment group."


def _citation(widened_from: Optional[str]) -> Citation:
    """A citation for document 101, widened from FRAGMENT or quoted whole."""
    return Citation(
        passage=PASSAGE, summary="s", relevance_score=0.9, document_id="101",
        document_title="t", authors=["A"], publication_date="2020",
        widened_from=widened_from,
    )


def _mock_conn(fetchone: tuple) -> tuple[MagicMock, MagicMock]:
    """A psycopg-like connection mock; returns (conn, cursor)."""
    cursor = MagicMock()
    cursor.fetchone.return_value = fetchone
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    return conn, cursor


# ---- migration --------------------------------------------------------------


def test_migration_adds_both_columns_idempotently() -> None:
    """Golden rules 15/16: idempotent, guarded per schema, no tracking code."""
    sql = MIGRATION.read_text()

    assert sql.count("ADD COLUMN IF NOT EXISTS widened_from TEXT") == 2
    assert "table_schema = 'audit' AND table_name = 'extracted_citations'" in sql
    assert "table_schema = 'factcheck' AND table_name = 'evidence'" in sql
    assert "schema_migrations" not in sql
    assert "bmlibrarian_migrations" not in sql


# ---- citation audit trail ---------------------------------------------------


@pytest.mark.parametrize("widened_from", [FRAGMENT, None])
def test_audit_trail_records_the_fragment(widened_from: Optional[str]) -> None:
    """record_citation stores the fragment (NULL for a passage quoted whole)."""
    conn, cursor = _mock_conn(fetchone=(7,))

    citation_id = CitationTracker(conn).record_citation(
        research_question_id=1, document_id=101, session_id=2, scoring_id=3,
        evaluator_id=4, passage=PASSAGE, summary="s", relevance_confidence=0.9,
        widened_from=widened_from,
    )

    sql, params = cursor.execute.call_args.args
    assert citation_id == 7
    assert "widened_from" in sql
    assert sql.count("%s") == len(params)
    assert params[-1] == widened_from


def test_citation_agent_records_the_fragment_in_the_audit_trail() -> None:
    """extract_citations_with_audit hands the fragment to the tracker."""
    agent = CitationFinderAgent()
    agent._citation_tracker = MagicMock()
    agent._citation_tracker.record_citation.return_value = 7
    agent._evaluator_id = 4

    with patch.object(agent, "extract_citation_from_document", return_value=_citation(FRAGMENT)):
        results = agent.extract_citations_with_audit(
            research_question_id=1, session_id=2, user_question="q",
            scored_documents_with_ids=[({"id": 101}, {"score": 4}, 3)],
        )

    assert [cid for _, cid in results] == [7]
    assert agent._citation_tracker.record_citation.call_args.kwargs["widened_from"] == FRAGMENT


# ---- fact-check evidence ----------------------------------------------------


def test_evidence_reference_carries_the_fragment() -> None:
    """The fact-checker keeps the fragment on its evidence and in JSON exports."""
    agent = FactCheckerAgent.__new__(FactCheckerAgent)
    refs = agent._citations_to_evidence_refs(
        [_citation(FRAGMENT), _citation(None)],
        [({"id": 101}, {"score": 4})],
        {"1": "supports", "2": "neutral"},
    )

    assert [r.widened_from for r in refs] == [FRAGMENT, None]
    assert refs[0].to_dict()["widened_from"] == FRAGMENT
    assert "widened_from" not in refs[1].to_dict()


def test_fact_checker_stores_the_fragment_with_its_evidence() -> None:
    """A checked statement's widened evidence reaches insert_evidence."""
    agent = FactCheckerAgent(model="test-model", show_model_info=False, max_citations=None)
    agent.db = MagicMock()
    agent.db.insert_statement.return_value = 1
    agent.db.insert_ai_evaluation.return_value = 2
    result = FactCheckResult(
        statement="s", evaluation="yes", reason="r", confidence="low",
        evidence_list=[EvidenceReference(
            citation_text=PASSAGE, document_id="101", widened_from=FRAGMENT,
        )],
    )

    assert agent._store_result_in_database(result, None)

    stored = agent.db.insert_evidence.call_args.args[0]
    assert stored.citation_text == PASSAGE
    assert stored.widened_from == FRAGMENT


def test_insert_evidence_stores_the_fragment() -> None:
    """insert_evidence writes the widened_from column."""
    conn, cursor = _mock_conn(fetchone=(9,))
    db = FactCheckerDB.__new__(FactCheckerDB)
    db.db_manager = MagicMock()
    db.db_manager.get_connection.return_value.__enter__.return_value = conn

    evidence_id = db.insert_evidence(Evidence(
        evaluation_id=1, citation_text=PASSAGE, document_id=101, widened_from=FRAGMENT,
    ))

    sql, params = cursor.execute.call_args.args
    assert evidence_id == 9
    assert "widened_from" in sql
    assert sql.count("%s") == len(params)
    assert params[-1] == FRAGMENT


def test_evidence_is_read_back_with_the_fragment() -> None:
    """get_evidence_for_evaluation returns widened_from."""
    conn, cursor = _mock_conn(fetchone=None)
    cursor.fetchall.return_value = [
        (9, 1, PASSAGE, 101, "123", None, 4.0, "supports", None, FRAGMENT),
    ]
    db = FactCheckerDB.__new__(FactCheckerDB)
    db.db_manager = MagicMock()
    db.db_manager.get_connection.return_value.__enter__.return_value = conn

    [evidence] = db.get_evidence_for_evaluation(1)

    assert evidence.citation_text == PASSAGE
    assert evidence.widened_from == FRAGMENT


def test_json_import_keeps_the_fragment(tmp_path: Path) -> None:
    """Re-importing an exported result keeps which evidence was widened."""
    results = [{
        "statement": "s", "evaluation": "yes", "reason": "r", "confidence": "low",
        "evidence_list": [EvidenceReference(
            citation_text=PASSAGE, document_id="101", widened_from=FRAGMENT,
        ).to_dict()],
    }]
    json_file = tmp_path / "results.json"
    json_file.write_text(json.dumps(results))
    conn, _ = _mock_conn(fetchone=None)  # statement not in the database yet
    db = FactCheckerDB.__new__(FactCheckerDB)
    db.db_manager = MagicMock()
    db.db_manager.get_connection.return_value.__enter__.return_value = conn
    db.insert_statement = MagicMock(return_value=1)
    db.insert_ai_evaluation = MagicMock(return_value=2)
    db.insert_evidence = MagicMock(return_value=3)

    db.import_json_results(str(json_file))

    stored = db.insert_evidence.call_args.args[0]
    assert stored.citation_text == PASSAGE
    assert stored.widened_from == FRAGMENT


# ---- SQLite review packages -------------------------------------------------


def _review_package(tmp_path: Path, with_column: bool) -> SQLiteFactCheckerDB:
    """A review package with one widened evidence row (or an old-format one)."""
    db_file = tmp_path / "review.db"
    conn = sqlite3.connect(db_file)
    schema = SQLITE_SCHEMA.read_text()
    assert SQLITE_COLUMN in schema
    if not with_column:
        schema = schema.replace(SQLITE_COLUMN, SQLITE_BEFORE_035)
    conn.executescript(schema)
    conn.execute("INSERT INTO statements (statement_id, statement_text) VALUES (1, 's')")
    conn.execute(
        "INSERT INTO ai_evaluations (evaluation_id, statement_id, evaluation, reason, version) "
        "VALUES (10, 1, 'yes', 'r', 1)"
    )
    conn.execute("INSERT INTO documents (id, external_id, title) VALUES (101, '123', 't')")
    columns, values = "evidence_id, evaluation_id, citation_text, document_id", [5, 10, PASSAGE, 101]
    if with_column:
        columns += ", widened_from"
        values.append(FRAGMENT)
    conn.execute(
        f"INSERT INTO evidence ({columns}) VALUES ({', '.join('?' * len(values))})", values
    )
    conn.commit()
    conn.close()
    return SQLiteFactCheckerDB(str(db_file))


def _load_export_script():
    """Import scripts/export_review_package.py as a module."""
    spec = importlib.util.spec_from_file_location("export_review_package", EXPORT_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_export_script_writes_the_fragment_into_the_package(tmp_path: Path) -> None:
    """export_review_package.py copies widened_from into a package that reads it back."""
    script = _load_export_script()
    db_file = tmp_path / "package.db"
    sqlite_conn = script.create_sqlite_database(db_file)
    sqlite_conn.execute("INSERT INTO statements (statement_id, statement_text) VALUES (1, 's')")
    sqlite_conn.execute(
        "INSERT INTO ai_evaluations (evaluation_id, statement_id, evaluation, reason, version) "
        "VALUES (10, 1, 'yes', 'r', 1)"
    )
    sqlite_conn.execute("INSERT INTO documents (id, external_id, title) VALUES (101, '123', 't')")
    pg_cursor = MagicMock()
    pg_cursor.fetchall.return_value = [
        (5, 10, PASSAGE, 101, "123", None, 4.0, "supports", None, FRAGMENT),
    ]
    pg_db = MagicMock()
    pg_conn = pg_db.db_manager.get_connection.return_value.__enter__.return_value
    pg_conn.cursor.return_value.__enter__.return_value = pg_cursor

    count, document_ids = script.export_evidence(pg_db, sqlite_conn, {10})
    sqlite_conn.close()

    assert (count, document_ids) == (1, {101})
    db = SQLiteFactCheckerDB(str(db_file))
    try:
        [evidence] = db._get_evidence_for_evaluation(10)
    finally:
        db.conn.close()
    assert evidence["widened_from"] == FRAGMENT


@pytest.mark.parametrize("with_column, expected", [(True, FRAGMENT), (False, None)])
def test_review_package_reads_the_fragment(
    tmp_path: Path, with_column: bool, expected: Optional[str]
) -> None:
    """Packages carry the fragment; ones exported before migration 035 still open."""
    db = _review_package(tmp_path, with_column=with_column)
    try:
        [evidence] = db._get_evidence_for_evaluation(10)
    finally:
        db.conn.close()

    assert evidence["citation_text"] == PASSAGE
    assert evidence["widened_from"] == expected


# ---- display ----------------------------------------------------------------


def test_widened_note_quotes_the_fragment() -> None:
    """Reviewers see that the passage was widened and what the model quoted."""
    note = widened_note(FRAGMENT)

    assert "widened" in note.lower()
    assert f'"{FRAGMENT}"' in note


@pytest.mark.parametrize("as_dict", [False, True])
@pytest.mark.parametrize("widened_from", [FRAGMENT, None])
def test_citation_card_marks_a_widened_passage(
    widened_from: Optional[str], as_dict: bool
) -> None:
    """The research tab's citation card shows the note only for a widened passage.

    The research tab passes plain dicts (workflow_thread); other callers pass
    Citation objects.
    """
    from PySide6.QtWidgets import QApplication, QLabel

    from bmlibrarian.gui.qt.widgets.citation_card import CitationCard

    _app = QApplication.instance() or QApplication([])
    citation = _citation(widened_from)
    card = CitationCard(vars(citation) if as_dict else citation, index=1)
    try:
        texts = [label.text() for label in card.findChildren(QLabel)]
    finally:
        card.deleteLater()

    assert (widened_note(FRAGMENT) in texts) == (widened_from is not None)
