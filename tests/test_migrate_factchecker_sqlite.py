"""
Tests for scripts/migrate_factchecker_sqlite_to_postgres.py (#376).

Each AI evaluation must be stored together with its evidence through
``FactCheckerDB.store_verdict`` (one transaction), so a failed evidence row
never leaves a verdict without its evidence. PostgreSQL is replaced by a fake;
the atomicity of ``store_verdict`` itself is tested in
``test_factcheck_audit_transactions*.py``.
"""

import sqlite3
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

from bmlibrarian.factchecker.db.database import AIEvaluation, Evidence, Statement

SCRIPT = Path(__file__).parent.parent / "scripts" / "migrate_factchecker_sqlite_to_postgres.py"
_spec = spec_from_file_location("migrate_factchecker_sqlite_to_postgres", SCRIPT)
migrate = module_from_spec(_spec)
_spec.loader.exec_module(migrate)

LEGACY_SCHEMA = """
CREATE TABLE statements (id INTEGER PRIMARY KEY, statement_text TEXT, input_statement_id TEXT,
    expected_answer TEXT, source_file TEXT, review_status TEXT);
CREATE TABLE annotators (id INTEGER PRIMARY KEY, username TEXT, full_name TEXT, email TEXT,
    expertise_level TEXT, institution TEXT);
CREATE TABLE ai_evaluations (id INTEGER PRIMARY KEY, statement_id INTEGER, evaluation TEXT,
    reason TEXT, confidence TEXT, documents_reviewed INTEGER, supporting_citations INTEGER,
    contradicting_citations INTEGER, neutral_citations INTEGER, matches_expected INTEGER,
    model_used TEXT, model_version TEXT, agent_config TEXT, session_id TEXT, version INTEGER);
CREATE TABLE evidence (id INTEGER PRIMARY KEY, ai_evaluation_id INTEGER, citation_text TEXT,
    document_id TEXT, pmid TEXT, doi TEXT, relevance_score REAL, supports_statement TEXT);
CREATE TABLE human_annotations (id INTEGER PRIMARY KEY, statement_id INTEGER, annotator_id INTEGER,
    annotation TEXT, explanation TEXT, confidence TEXT, review_duration_seconds INTEGER, session_id TEXT);
CREATE TABLE processing_metadata (id INTEGER PRIMARY KEY, session_id TEXT, input_file TEXT,
    total_statements INTEGER, start_time TEXT, status TEXT, config_snapshot TEXT, end_time TEXT,
    output_file TEXT, processed_statements INTEGER, error_message TEXT);
"""

# Document id the fake treats as missing from public.document (FK violation)
MISSING_DOCUMENT_ID = 999


class FakeFactCheckerDB:
    """Records writes; ``store_verdict`` fails like PostgreSQL on a missing document."""

    def __init__(self) -> None:
        """Start with no statements and no verdicts."""
        self.statement_ids: Dict[str, int] = {}
        self.verdicts: List[Tuple[Statement, AIEvaluation, List[Evidence]]] = []
        self.evaluated: set = set()

    def insert_statement(self, statement: Statement, conn: Any = None) -> int:
        """Return the existing id for the text, or a new one."""
        return self.statement_ids.setdefault(statement.statement_text, len(self.statement_ids) + 1)

    def store_verdict(self, statement: Statement, evaluation: AIEvaluation,
                      evidence: List[Evidence]) -> Tuple[int, int]:
        """Store all or nothing, like the real single-transaction method."""
        if any(item.document_id == MISSING_DOCUMENT_ID for item in evidence):
            raise RuntimeError("violates foreign key constraint evidence_document_id_fkey")
        statement_id = self.insert_statement(statement)
        self.verdicts.append((statement, evaluation, evidence))
        self.evaluated.add(statement_id)
        return statement_id, len(self.verdicts)

    def get_latest_ai_evaluation(self, statement_id: int) -> Optional[str]:
        """Return a marker when the statement has a verdict."""
        return "evaluated" if statement_id in self.evaluated else None

    def insert_or_get_annotator(self, annotator: Any) -> int:
        """Not exercised beyond returning an id."""
        return 1

    def insert_human_annotation(self, annotation: Any) -> int:
        """Not exercised beyond returning an id."""
        return 1


def _make_legacy_db(path: Path) -> None:
    """Create a legacy fact-checker SQLite file with three statements."""
    conn = sqlite3.connect(path)
    conn.executescript(LEGACY_SCHEMA)
    conn.executemany(
        "INSERT INTO statements (id, statement_text, expected_answer, review_status) VALUES (?, ?, ?, ?)",
        [(1, "Aspirin prevents MI", "yes", None),
         (2, "Vitamin C cures colds", "no", None),
         (3, "Failed check", "maybe", None)],
    )
    conn.executemany(
        "INSERT INTO ai_evaluations (id, statement_id, evaluation, reason, version) VALUES (?, ?, ?, ?, ?)",
        [(10, 1, "yes", "good evidence", 1),
         (20, 2, "no", "bad evidence", 1),
         (30, 3, "error", "LLM timeout", 1)],
    )
    conn.executemany(
        "INSERT INTO evidence (id, ai_evaluation_id, citation_text, document_id) VALUES (?, ?, ?, ?)",
        [(100, 10, "Aspirin reduced MI.", "42"),
         (101, 10, "No document.", None),
         (200, 20, "Exists.", "43"),
         (201, 20, "Not in public.document.", str(MISSING_DOCUMENT_ID)),
         (300, 30, "From the failed check.", "44"),
         (400, 77, "Orphan evidence.", "45")],
    )
    conn.commit()
    conn.close()


@pytest.fixture
def legacy_db(tmp_path: Path) -> Path:
    """Path to a populated legacy SQLite file."""
    path = tmp_path / "factchecker.db"
    _make_legacy_db(path)
    return path


@pytest.fixture
def fake_db(monkeypatch: pytest.MonkeyPatch) -> FakeFactCheckerDB:
    """Replace the script's FactCheckerDB with one shared fake."""
    fake = FakeFactCheckerDB()
    monkeypatch.setattr(migrate, "FactCheckerDB", lambda: fake)
    return fake


def _run(sqlite_path: Path, **kwargs: Any) -> Any:
    """Migrate statements and verdicts only."""
    migrator = migrate.SQLiteToPostgresMigrator(str(sqlite_path), **kwargs)
    migrator.migrate_statements()
    migrator.migrate_verdicts()
    return migrator


def test_verdict_stored_with_its_evidence(legacy_db: Path, fake_db: FakeFactCheckerDB) -> None:
    """Evaluation 10 is stored once, with its valid evidence; bad document_id is dropped."""
    migrator = _run(legacy_db)

    assert len(fake_db.verdicts) == 1
    statement, evaluation, evidence = fake_db.verdicts[0]
    assert statement.statement_text == "Aspirin prevents MI"
    assert evaluation.evaluation == "yes"
    assert [e.document_id for e in evidence] == [42]
    assert migrator.stats["ai_evaluations"] == {"total": 3, "migrated": 1, "skipped": 1, "errors": 1}
    # 100 migrated; 101 (no doc id), 300 (error verdict), 400 (orphan) skipped; 200+201 rolled back
    assert migrator.stats["evidence"] == {"total": 6, "migrated": 1, "skipped": 3, "errors": 2}


def test_failed_evidence_leaves_statement_unevaluated(legacy_db: Path, fake_db: FakeFactCheckerDB) -> None:
    """A verdict whose evidence fails is not stored, but its statement is, so it is retried."""
    _run(legacy_db)

    stored = {s.statement_text for s, _, _ in fake_db.verdicts}
    assert "Vitamin C cures colds" not in stored
    assert fake_db.statement_ids["Vitamin C cures colds"] not in fake_db.evaluated


def test_error_evaluation_is_not_a_verdict(legacy_db: Path, fake_db: FakeFactCheckerDB) -> None:
    """An 'error' evaluation is skipped; its statement stays unevaluated."""
    _run(legacy_db)

    assert all(e.evaluation != "error" for _, e, _ in fake_db.verdicts)
    assert fake_db.statement_ids["Failed check"] not in fake_db.evaluated


def test_rerun_with_skip_existing_adds_no_versions(legacy_db: Path, fake_db: FakeFactCheckerDB) -> None:
    """--skip-existing skips statements that already had a verdict before the run."""
    _run(legacy_db)
    migrator = _run(legacy_db, skip_existing=True)

    assert len(fake_db.verdicts) == 1
    assert migrator.stats["ai_evaluations"]["skipped"] == 2


def test_skip_existing_keeps_all_versions_of_a_new_statement(
    legacy_db: Path, fake_db: FakeFactCheckerDB
) -> None:
    """Version 2 of a statement first seen in this run is not skipped by its own version 1."""
    conn = sqlite3.connect(legacy_db)
    conn.execute(
        "INSERT INTO ai_evaluations (id, statement_id, evaluation, reason, version) "
        "VALUES (11, 1, 'maybe', 're-run', 2)"
    )
    conn.commit()
    conn.close()

    _run(legacy_db, skip_existing=True)

    assert [e.evaluation for _, e, _ in fake_db.verdicts] == ["yes", "maybe"]


def test_dry_run_writes_nothing(legacy_db: Path, fake_db: FakeFactCheckerDB) -> None:
    """A dry run counts verdicts without storing any."""
    migrator = _run(legacy_db, dry_run=True)

    assert fake_db.verdicts == []
    assert migrator.stats["ai_evaluations"]["migrated"] == 2


@pytest.mark.parametrize("raw, expected", [
    ("42", 42), (42, 42), (" 7 ", 7), (None, None), ("", None), ("abc", None),
    ("1.5", None), (1.5, None), (0, None), ("-3", None),
])
def test_evidence_document_id_parsing(raw: Any, expected: Optional[int]) -> None:
    """Only positive integers (or digit strings) become a document_id."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT 1 AS id, 'x' AS citation_text, ? AS document_id, NULL AS pmid, "
                       "NULL AS doi, NULL AS relevance_score, NULL AS supports_statement", (raw,)).fetchone()
    item = migrate.evidence_from_row(row)
    assert (item.document_id if item else None) == expected
