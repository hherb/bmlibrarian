"""
Tests for scripts/migrate_factchecker_sqlite_to_postgres.py (#376).

All AI evaluations of a statement must be stored together with their evidence
through ``FactCheckerDB.store_verdicts`` (one transaction), so a failed
evidence row never leaves a verdict without its evidence, nor an older version
as the latest verdict. PostgreSQL is replaced by a fake; the atomicity of
``store_verdicts`` itself is tested in ``test_factcheck_audit_transactions_db.py``.
"""

import sqlite3
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import psycopg
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
# PostgreSQL ids differ from the SQLite ones, so mixing them up fails the tests
PG_ID_OFFSET = 1000
# An unrelated, already evaluated PostgreSQL statement whose id equals SQLite statement 1
UNRELATED_EVALUATED_PG_ID = 1


class FakeFactCheckerDB:
    """Records writes; ``store_verdicts`` fails like PostgreSQL on a missing document."""

    def __init__(self) -> None:
        """Start with one unrelated evaluated statement and no migrated verdicts."""
        self.statement_ids: Dict[str, int] = {}
        self.verdicts: List[Tuple[Statement, AIEvaluation, List[Evidence]]] = []
        self.evaluated: Set[int] = {UNRELATED_EVALUATED_PG_ID}
        self.missing_documents: Set[int] = {MISSING_DOCUMENT_ID}
        self.failing_statements: Set[str] = set()
        # review_status by PostgreSQL id; insert_statement never sets it, like the real one
        self.review_statuses: Dict[int, str] = {}

    def insert_statement(self, statement: Statement, conn: Any = None) -> int:
        """Return the existing id for the text, or a new one."""
        if statement.statement_text in self.failing_statements:
            raise RuntimeError("statement insert failed")
        return self.statement_ids.setdefault(statement.statement_text, PG_ID_OFFSET + len(self.statement_ids) + 1)

    def get_statement(self, statement_id: int) -> Optional[Statement]:
        """Return the statement with its PostgreSQL review status ('pending' unless set)."""
        text = next((t for t, i in self.statement_ids.items() if i == statement_id), None)
        if text is None:
            return None
        return Statement(statement_text=text, statement_id=statement_id,
                         review_status=self.review_statuses.get(statement_id, "pending"))

    def update_statement_review_status(self, statement_id: int, status: str) -> None:
        """Record the status."""
        self.review_statuses[statement_id] = status

    def store_verdicts(self, statement: Statement,
                       verdicts: List[Tuple[AIEvaluation, List[Evidence]]]) -> Tuple[int, List[int]]:
        """Store all or nothing, like the real single-transaction method."""
        for _, evidence in verdicts:
            if any(item.document_id in self.missing_documents for item in evidence):
                raise psycopg.errors.ForeignKeyViolation("violates foreign key constraint evidence_document_id_fkey")
        statement_id = self.insert_statement(statement)
        ids = []
        for evaluation, evidence in verdicts:
            self.verdicts.append((statement, evaluation, evidence))
            ids.append(len(self.verdicts))
        self.evaluated.add(statement_id)
        return statement_id, ids

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
    """
    Create a legacy fact-checker SQLite file.

    Statement 1 has two good versions (one evidence row without a document id);
    statement 2's second version cites a missing document; statement 3's only
    evaluation is a failed check; evidence 400 belongs to no evaluation.
    """
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
         (11, 1, "Maybe", "re-run", 2),
         (20, 2, "no", "fine", 1),
         (21, 2, "yes", "bad evidence", 2),
         (30, 3, "error", "LLM timeout", 1)],
    )
    conn.executemany(
        "INSERT INTO evidence (id, ai_evaluation_id, citation_text, document_id) VALUES (?, ?, ?, ?)",
        [(100, 10, "Aspirin reduced MI.", "42"),
         (101, 10, "No document.", None),
         (110, 11, "Second look.", "46"),
         (200, 20, "Exists.", "43"),
         (201, 21, "Not in public.document.", str(MISSING_DOCUMENT_ID)),
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


def _stored(fake: FakeFactCheckerDB) -> List[Tuple[str, str, List[int]]]:
    """(statement text, verdict, evidence document ids) of every stored evaluation."""
    return [(s.statement_text, e.evaluation, [i.document_id for i in ev]) for s, e, ev in fake.verdicts]


def test_versions_stored_in_order_with_their_evidence(legacy_db: Path, fake_db: FakeFactCheckerDB) -> None:
    """Statement 1's versions are stored with their evidence; evidence without a document id is dropped."""
    migrator = _run(legacy_db)

    assert _stored(fake_db) == [("Aspirin prevents MI", "yes", [42]), ("Aspirin prevents MI", "maybe", [46])]
    assert migrator.stats["ai_evaluations"] == {"total": 5, "migrated": 2, "skipped": 1, "errors": 2}
    # 100, 110 migrated; 101 dropped; 300 (error verdict), 400 (orphan) skipped; 200 + 201 rolled back
    assert migrator.stats["evidence"] == {"total": 7, "migrated": 2, "dropped": 1, "skipped": 2, "errors": 2}


def test_failed_newer_version_rolls_back_the_older_one(legacy_db: Path, fake_db: FakeFactCheckerDB) -> None:
    """Version 2 fails, so version 1 is not left as the latest verdict: the statement stays unevaluated."""
    migrator = _run(legacy_db)

    assert all(text != "Vitamin C cures colds" for text, _, _ in _stored(fake_db))
    assert fake_db.statement_ids["Vitamin C cures colds"] not in fake_db.evaluated
    assert migrator.failed_statements == [2]


def test_error_evaluation_is_not_a_verdict(legacy_db: Path, fake_db: FakeFactCheckerDB) -> None:
    """An 'error' evaluation is skipped; its statement stays unevaluated."""
    _run(legacy_db)

    assert all(verdict != "error" for _, verdict, _ in _stored(fake_db))
    assert fake_db.statement_ids["Failed check"] not in fake_db.evaluated


def test_rerun_with_skip_existing_retries_only_the_failed_statement(
    legacy_db: Path, fake_db: FakeFactCheckerDB
) -> None:
    """Once the missing document exists, a --skip-existing re-run stores statement 2 and nothing twice."""
    _run(legacy_db)
    fake_db.missing_documents.clear()
    migrator = _run(legacy_db, skip_existing=True)

    assert _stored(fake_db)[2:] == [("Vitamin C cures colds", "no", [43]),
                                    ("Vitamin C cures colds", "yes", [MISSING_DOCUMENT_ID])]
    # 10 + 11 skipped by --skip-existing, 30 as an error evaluation
    assert migrator.stats["ai_evaluations"] == {"total": 5, "migrated": 2, "skipped": 3, "errors": 0}
    assert migrator.failed_statements == []


def test_skip_existing_uses_the_postgres_statement_id(legacy_db: Path, fake_db: FakeFactCheckerDB) -> None:
    """An evaluated PostgreSQL statement whose id equals SQLite id 1 does not make statement 1 skipped."""
    _run(legacy_db, skip_existing=True)

    assert [v for t, v, _ in _stored(fake_db) if t == "Aspirin prevents MI"] == ["yes", "maybe"]


def test_unmigrated_statement_skips_its_evaluations(legacy_db: Path, fake_db: FakeFactCheckerDB) -> None:
    """If a statement fails to migrate, its evaluations and evidence are skipped, not stored."""
    fake_db.failing_statements.add("Aspirin prevents MI")
    migrator = _run(legacy_db)

    assert _stored(fake_db) == []
    assert migrator.stats["statements"]["errors"] == 1
    assert migrator.stats["ai_evaluations"]["skipped"] == 3  # 10, 11 and the error evaluation 30
    assert migrator.stats["evidence"]["skipped"] == 5  # 100, 101, 110, 300, 400


def test_systemic_error_aborts_the_run(legacy_db: Path, fake_db: FakeFactCheckerDB,
                                       monkeypatch: pytest.MonkeyPatch) -> None:
    """A lost connection is not counted per statement: it stops the migration."""
    def lost(*args: Any) -> None:
        """Fail like a dropped database connection."""
        raise psycopg.OperationalError("server closed the connection")
    monkeypatch.setattr(fake_db, "store_verdicts", lost)

    with pytest.raises(psycopg.OperationalError):
        _run(legacy_db)


def test_dry_run_writes_nothing(legacy_db: Path, fake_db: FakeFactCheckerDB) -> None:
    """A dry run counts verdicts (an upper bound) without storing any."""
    migrator = _run(legacy_db, dry_run=True)

    assert fake_db.verdicts == []
    assert migrator.stats["ai_evaluations"]["migrated"] == 4


def test_migrate_all_and_exit_code_report_errors(legacy_db: Path, fake_db: FakeFactCheckerDB,
                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    """A run with a failed statement returns False and the CLI exits 1; a clean run exits 0."""
    monkeypatch.setattr("sys.argv", ["migrate", "--sqlite-db", str(legacy_db)])
    with pytest.raises(SystemExit) as exited:
        migrate.main()
    assert exited.value.code == 1

    fake_db.missing_documents.clear()
    assert migrate.SQLiteToPostgresMigrator(str(legacy_db), skip_existing=True).migrate_all() is True


def test_evaluation_and_evidence_fields_are_mapped() -> None:
    """Every legacy column lands in the right field; the verdict is normalised."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT 'Yes ' AS evaluation, 'r' AS reason, 'high' AS confidence, 5 AS documents_reviewed, "
        "3 AS supporting_citations, 1 AS contradicting_citations, NULL AS neutral_citations, "
        "0 AS matches_expected, 'm' AS model_used, 'v1' AS model_version, '{}' AS agent_config, "
        "'s' AS session_id, 4 AS version"
    ).fetchone()
    evaluation = migrate.evaluation_from_row(row)
    assert (evaluation.evaluation, evaluation.reason, evaluation.confidence, evaluation.documents_reviewed,
            evaluation.supporting_citations, evaluation.contradicting_citations, evaluation.neutral_citations,
            evaluation.matches_expected, evaluation.model_used, evaluation.model_version,
            evaluation.agent_config, evaluation.session_id) == (
        "yes", "r", "high", 5, 3, 1, 0, False, "m", "v1", "{}", "s")

    ev_row = conn.execute(
        "SELECT 1 AS id, 'c' AS citation_text, '7' AS document_id, '123' AS pmid, '10.1/x' AS doi, "
        "0.8 AS relevance_score, 'supports' AS supports_statement"
    ).fetchone()
    item = migrate.evidence_from_row(ev_row)
    assert (item.citation_text, item.document_id, item.pmid, item.doi, item.relevance_score,
            item.supports_statement) == ("c", 7, "123", "10.1/x", 0.8, "supports")


@pytest.mark.parametrize("raw, expected", [
    ("42", 42), (42, 42), (" 7 ", 7), (None, None), ("", None), ("abc", None),
    ("1.5", None), (1.5, None), (0, None), ("-3", None), ("²", None),
])
def test_evidence_document_id_parsing(raw: Any, expected: Optional[int]) -> None:
    """Only positive integers (or decimal digit strings) become a document_id."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT 1 AS id, 'x' AS citation_text, ? AS document_id, NULL AS pmid, "
                       "NULL AS doi, NULL AS relevance_score, NULL AS supports_statement", (raw,)).fetchone()
    item = migrate.evidence_from_row(row)
    assert (item.document_id if item else None) == expected


def _set_legacy_status(path: Path, sqlite_id: int, status: Optional[str]) -> None:
    """Set a legacy statement's review_status."""
    conn = sqlite3.connect(path)
    conn.execute("UPDATE statements SET review_status = ? WHERE id = ?", (status, sqlite_id))
    conn.commit()
    conn.close()


def test_legacy_review_status_is_restored(legacy_db: Path, fake_db: FakeFactCheckerDB) -> None:
    """A non-default legacy status reaches PostgreSQL (normalised); NULL stays 'pending' (#392)."""
    _set_legacy_status(legacy_db, 1, " Flagged ")
    _set_legacy_status(legacy_db, 2, "pending")
    migrator = _run(legacy_db)

    assert fake_db.review_statuses == {fake_db.statement_ids["Aspirin prevents MI"]: "flagged"}
    assert migrator.stats["statements"]["errors"] == 0


def test_status_set_in_postgres_is_kept(legacy_db: Path, fake_db: FakeFactCheckerDB) -> None:
    """A re-run does not overwrite a review status set in PostgreSQL since the first run."""
    _set_legacy_status(legacy_db, 1, "in_review")
    _run(legacy_db)
    pg_id = fake_db.statement_ids["Aspirin prevents MI"]
    fake_db.review_statuses[pg_id] = "completed"
    _run(legacy_db, skip_existing=True)

    assert fake_db.review_statuses[pg_id] == "completed"


def test_invalid_status_is_an_error_but_verdicts_migrate(legacy_db: Path, fake_db: FakeFactCheckerDB) -> None:
    """A status PostgreSQL rejects counts as an error; the statement's verdicts still migrate."""
    _set_legacy_status(legacy_db, 1, "reviewed")
    migrator = _run(legacy_db)

    assert migrator.stats["statements"] == {"total": 3, "migrated": 3, "skipped": 0, "errors": 1}
    assert fake_db.review_statuses == {}
    assert [v for t, v, _ in _stored(fake_db) if t == "Aspirin prevents MI"] == ["yes", "maybe"]


def test_invalid_status_is_ignored_once_set_in_postgres(legacy_db: Path, fake_db: FakeFactCheckerDB) -> None:
    """An invalid legacy status is no error when PostgreSQL already holds a reviewed status."""
    _set_legacy_status(legacy_db, 1, "reviewed")
    _run(legacy_db)
    pg_id = fake_db.statement_ids["Aspirin prevents MI"]
    fake_db.review_statuses[pg_id] = "completed"
    migrator = _run(legacy_db, skip_existing=True)

    assert migrator.stats["statements"]["errors"] == 0
    assert fake_db.review_statuses[pg_id] == "completed"


def test_dry_run_reports_invalid_status(legacy_db: Path, fake_db: FakeFactCheckerDB) -> None:
    """A dry run flags an invalid status without touching PostgreSQL."""
    _set_legacy_status(legacy_db, 1, "reviewed")
    _set_legacy_status(legacy_db, 2, "flagged")
    migrator = _run(legacy_db, dry_run=True)

    assert migrator.stats["statements"]["errors"] == 1
    assert fake_db.review_statuses == {} and fake_db.statement_ids == {}


@pytest.mark.parametrize("raw, expected", [
    (None, "pending"), ("", "pending"), ("  ", "pending"), (" Flagged ", "flagged"),
    ("IN_REVIEW", "in_review"), (3, "3"), (1.5, "1.5"), (0, "0"), (0.0, "0.0"),
])
def test_legacy_review_status_never_raises(raw: Any, expected: str) -> None:
    """Untyped legacy values are normalised, never raised on, so the statement is still mapped."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT ? AS review_status", (raw,)).fetchone()
    assert migrate.legacy_review_status(row) == expected
