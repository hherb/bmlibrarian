"""
Tests for scripts/migrate_factchecker_sqlite_to_postgres.py (#376).

All AI evaluations of a statement must be stored together with their evidence
through ``FactCheckerDB.store_verdicts`` (one transaction), so a failed
evidence row never leaves a verdict without its evidence, nor an older version
as the latest verdict. PostgreSQL is replaced by a fake; the atomicity of
``store_verdicts`` itself is tested in ``test_factcheck_audit_transactions_db.py``.
"""

import sqlite3
from contextlib import contextmanager, nullcontext
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

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
# Optional in legacy files: the migrator skips the step when the table is missing
EXPORT_HISTORY_SCHEMA = """
CREATE TABLE export_history (id INTEGER PRIMARY KEY, export_date TEXT, export_type TEXT,
    output_file TEXT, statement_count INTEGER, requested_by TEXT, filters_applied TEXT);
"""

# Document id the fake treats as missing from public.document (FK violation)
MISSING_DOCUMENT_ID = 999
# PostgreSQL ids differ from the SQLite ones, so mixing them up fails the tests
PG_ID_OFFSET = 1000
# An unrelated, already evaluated PostgreSQL statement whose id equals SQLite statement 1
UNRELATED_EVALUATED_PG_ID = 1


class FakeConnection:
    """Records how the dry run uses its transaction."""

    def __init__(self) -> None:
        """No transaction opened yet."""
        self.force_rollback: List[bool] = []
        self.savepoints = 0
        self.open = False
        # (sql, params) of every execute() on this connection's cursors
        self.executed: List[Tuple[str, Any]] = []

    def cursor(self) -> Any:
        """A cursor is this connection itself (only ``execute`` is used)."""
        return nullcontext(self)

    def execute(self, sql: str, params: Any = None) -> None:
        """Record the statement."""
        self.executed.append((sql, params))

    @contextmanager
    def transaction(self, force_rollback: bool = False) -> Iterator[None]:
        """The first call is the dry run's outer transaction, later ones savepoints."""
        if self.open:
            self.savepoints += 1
            yield
            return
        self.force_rollback.append(force_rollback)
        self.open = True
        try:
            yield
        finally:
            self.open = False


class FakeDBManager:
    """Hands out one fake connection."""

    def __init__(self) -> None:
        """Create the connection."""
        self.conn = FakeConnection()

    @contextmanager
    def get_connection(self) -> Iterator[FakeConnection]:
        """Yield the connection."""
        yield self.conn


class FakeFactCheckerDB:
    """Records writes; ``store_verdicts`` fails like PostgreSQL on a missing document."""

    def __init__(self) -> None:
        """Start with one unrelated evaluated statement and no migrated verdicts."""
        self.db_manager = FakeDBManager()
        # the conn= of every call: None in a real run, the dry run's connection otherwise
        self.conns: List[Any] = []
        self.statement_ids: Dict[str, int] = {}
        self.verdicts: List[Tuple[Statement, AIEvaluation, List[Evidence]]] = []
        self.evaluated: Set[int] = {UNRELATED_EVALUATED_PG_ID}
        self.missing_documents: Set[int] = {MISSING_DOCUMENT_ID}
        self.failing_statements: Set[str] = set()
        # review_status by PostgreSQL id; insert_statement never sets it, like the real one
        self.review_statuses: Dict[int, str] = {}

    def insert_statement(self, statement: Statement, conn: Any = None) -> int:
        """Return the existing id for the text, or a new one."""
        self.conns.append(conn)
        if statement.statement_text in self.failing_statements:
            raise psycopg.errors.CheckViolation("statement insert failed")
        return self.statement_ids.setdefault(statement.statement_text, PG_ID_OFFSET + len(self.statement_ids) + 1)

    def get_statement(self, statement_id: int, conn: Any = None) -> Optional[Statement]:
        """Return the statement with its PostgreSQL review status ('pending' unless set)."""
        self.conns.append(conn)
        text = next((t for t, i in self.statement_ids.items() if i == statement_id), None)
        if text is None:
            return None
        return Statement(statement_text=text, statement_id=statement_id,
                         review_status=self.review_statuses.get(statement_id, "pending"))

    def update_statement_review_status(self, statement_id: int, status: str, conn: Any = None) -> None:
        """Record the status."""
        self.conns.append(conn)
        self.review_statuses[statement_id] = status

    def store_verdicts(self, statement: Statement,
                       verdicts: List[Tuple[AIEvaluation, List[Evidence]]],
                       conn: Any = None) -> Tuple[int, List[int]]:
        """Store all or nothing, like the real single-transaction method."""
        self.conns.append(conn)
        for _, evidence in verdicts:
            if any(item.document_id in self.missing_documents for item in evidence):
                raise psycopg.errors.ForeignKeyViolation("violates foreign key constraint evidence_document_id_fkey")
        statement_id = self.insert_statement(statement, conn=conn)
        ids = []
        for evaluation, evidence in verdicts:
            self.verdicts.append((statement, evaluation, evidence))
            ids.append(len(self.verdicts))
        self.evaluated.add(statement_id)
        return statement_id, ids

    def get_latest_ai_evaluation(self, statement_id: int, conn: Any = None) -> Optional[str]:
        """Return a marker when the statement has a verdict."""
        self.conns.append(conn)
        return "evaluated" if statement_id in self.evaluated else None

    def insert_or_get_annotator(self, annotator: Any, conn: Any = None) -> int:
        """Not exercised beyond returning an id."""
        self.conns.append(conn)
        return 1

    def insert_human_annotation(self, annotation: Any, conn: Any = None) -> int:
        """Not exercised beyond returning an id."""
        self.conns.append(conn)
        return 1

    def insert_processing_session(self, session_data: Dict[str, Any], overwrite: bool = False,
                                  conn: Any = None) -> int:
        """Not exercised beyond returning an id."""
        self.conns.append(conn)
        return 1

    @contextmanager
    def _connection(self, conn: Any) -> Iterator[FakeConnection]:
        """``conn`` if given, else the pooled connection, like the real method."""
        self.conns.append(conn)
        yield conn if conn is not None else self.db_manager.conn


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


def _add_every_other_table(path: Path) -> None:
    """Give the legacy file one row in each table _make_legacy_db leaves empty."""
    with sqlite3.connect(path) as conn:
        conn.executescript(EXPORT_HISTORY_SCHEMA)
        conn.execute("INSERT INTO annotators (id, username) VALUES (5, 'alice')")
        conn.execute("INSERT INTO human_annotations (id, statement_id, annotator_id, annotation) "
                     "VALUES (50, 1, 5, 'yes')")
        conn.execute("INSERT INTO processing_metadata (session_id, input_file, start_time) "
                     "VALUES ('s', 'in.json', '2026-01-01T00:00:00+00:00')")
        conn.execute("INSERT INTO export_history (id, export_date, export_type, statement_count) "
                     "VALUES (60, '2026-01-02T00:00:00+00:00', 'full', 3)")


@pytest.fixture
def fake_db(monkeypatch: pytest.MonkeyPatch) -> FakeFactCheckerDB:
    """
    Replace the script's FactCheckerDB with one shared fake.

    ``fake.managers`` records the DatabaseManager the migrator passed: None
    (the shared one) or the kwargs of the one it opened itself.
    """
    fake = FakeFactCheckerDB()
    fake.managers = []

    def open_db(db_manager: Any) -> FakeFactCheckerDB:
        """Record the manager, return the fake."""
        fake.managers.append(db_manager)
        return fake
    monkeypatch.setattr(migrate, "FactCheckerDB", open_db)
    monkeypatch.setattr(migrate, "DatabaseManager", lambda **kwargs: kwargs)
    return fake


def _run(sqlite_path: Path, **kwargs: Any) -> Any:
    """Migrate statements and verdicts only (a dry run inside its rolled-back transaction)."""
    migrator = migrate.SQLiteToPostgresMigrator(str(sqlite_path), **kwargs)
    with migrator.dry_run_transaction() if migrator.dry_run else nullcontext():
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
    def lost(*args: Any, **kwargs: Any) -> None:
        """Fail like a dropped database connection."""
        raise psycopg.OperationalError("server closed the connection")
    monkeypatch.setattr(fake_db, "store_verdicts", lost)

    with pytest.raises(psycopg.OperationalError):
        _run(legacy_db)


def _dry_run_rolled_back(fake: FakeFactCheckerDB) -> bool:
    """Every call went to the dry run's connection, whose one transaction was forced to roll back."""
    conn = fake.db_manager.conn
    return bool(fake.conns) and all(c is conn for c in fake.conns) and conn.force_rollback == [True]


def _evaluated_statement_1(fake: FakeFactCheckerDB) -> FakeFactCheckerDB:
    """Mark statement 1 as already evaluated in PostgreSQL, so --skip-existing skips it."""
    pg_id = fake.statement_ids.setdefault("Aspirin prevents MI", PG_ID_OFFSET + 1)
    fake.evaluated.add(pg_id)
    return fake


@pytest.mark.parametrize("skip_existing", [False, True])
def test_dry_run_counts_like_a_real_run_and_rolls_back(legacy_db: Path, fake_db: FakeFactCheckerDB,
                                                       skip_existing: bool) -> None:
    """A dry run makes every step's real writes in one rolled-back transaction, so it reports the real run's counts (#410)."""
    _add_every_other_table(legacy_db)
    _evaluated_statement_1(fake_db)
    real = migrate.SQLiteToPostgresMigrator(str(legacy_db), skip_existing=skip_existing)
    assert real.migrate_all() is False
    real_stats = {table: dict(counts) for table, counts in real.stats.items()}
    dry_fake = _evaluated_statement_1(FakeFactCheckerDB())
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(migrate, "FactCheckerDB", lambda _manager: dry_fake)
        dry = migrate.SQLiteToPostgresMigrator(str(legacy_db), skip_existing=skip_existing, dry_run=True)
        assert dry.migrate_all() is False

    assert dry.stats == real_stats
    assert all(dry.stats[t]["migrated"] == 1 for t in
               ("annotators", "human_annotations", "processing_metadata", "export_history"))
    assert dry.stats["ai_evaluations"]["errors"] == 2  # statement 2's missing document, as in the real run
    # the failed check, plus statement 1's two versions with --skip-existing
    assert dry.stats["ai_evaluations"]["skipped"] == (3 if skip_existing else 1)
    assert dry.failed_statements == real.failed_statements == [2]
    assert _dry_run_rolled_back(dry_fake)
    assert len(dry_fake.db_manager.conn.executed) == 1  # the export row, on the dry run's connection
    assert all(c is None for c in fake_db.conns)  # the real run commits each call itself


def test_dry_run_lists_pending_migrations_instead_of_applying_them(legacy_db: Path,
                                                                   fake_db: FakeFactCheckerDB) -> None:
    """Applied migrations would be committed outside the rolled-back transaction, so a dry run only lists them."""
    migrate.SQLiteToPostgresMigrator(str(legacy_db))
    migrate.SQLiteToPostgresMigrator(str(legacy_db), dry_run=True)

    assert fake_db.managers == [None, {"dry_run_migrations": True}]


def test_dry_run_systemic_error_aborts_and_rolls_back(legacy_db: Path, fake_db: FakeFactCheckerDB,
                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    """A lost connection aborts a dry run too; its transaction is still rolled back and released."""
    def lost(*args: Any, **kwargs: Any) -> None:
        """Fail like a dropped connection."""
        raise psycopg.OperationalError("server closed the connection")
    monkeypatch.setattr(fake_db, "store_verdicts", lost)

    migrator = migrate.SQLiteToPostgresMigrator(str(legacy_db), dry_run=True)
    with pytest.raises(psycopg.OperationalError):
        migrator.migrate_all()
    assert migrator._dry_conn is None
    assert fake_db.db_manager.conn.force_rollback == [True]


def test_dry_run_step_outside_its_transaction_refuses(legacy_db: Path, fake_db: FakeFactCheckerDB) -> None:
    """A dry-run step called on its own would commit its writes, so it raises before the first one."""
    migrator = migrate.SQLiteToPostgresMigrator(str(legacy_db), dry_run=True)

    with pytest.raises(RuntimeError, match="dry_run_transaction"):
        migrator.migrate_statements()
    assert fake_db.conns == []


def test_dry_run_counts_rows_postgres_refuses_in_other_steps(
        legacy_db: Path, fake_db: FakeFactCheckerDB, monkeypatch: pytest.MonkeyPatch) -> None:
    """The #410 example: a session PostgreSQL refuses is an error in the dry run, not 'migrated'."""
    with sqlite3.connect(legacy_db) as conn:
        conn.execute("INSERT INTO processing_metadata (session_id, input_file, start_time, end_time) "
                     "VALUES ('s', 'in.json', '2026-01-01', 'not a time')")

    def insert(session_data: Dict[str, Any], overwrite: bool = False, conn: Any = None) -> int:
        """Refuse the end time like PostgreSQL's TIMESTAMPTZ cast."""
        fake_db.conns.append(conn)
        raise psycopg.errors.InvalidDatetimeFormat("invalid input syntax for type timestamp")
    monkeypatch.setattr(fake_db, "insert_processing_session", insert, raising=False)

    migrator = migrate.SQLiteToPostgresMigrator(str(legacy_db), dry_run=True)
    with migrator.dry_run_transaction():
        migrator.migrate_processing_metadata()

    assert migrator.stats["processing_metadata"] == {"total": 1, "migrated": 0, "skipped": 0, "errors": 1}
    assert _dry_run_rolled_back(fake_db)


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
    """A dry run flags an invalid status; its status writes are rolled back with the rest."""
    _set_legacy_status(legacy_db, 1, "reviewed")
    _set_legacy_status(legacy_db, 2, "flagged")
    migrator = _run(legacy_db, dry_run=True)

    assert migrator.stats["statements"]["errors"] == 1
    assert _dry_run_rolled_back(fake_db)


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


def _add_annotators(path: Path, *usernames: str) -> None:
    """Add legacy annotator rows (the default legacy file has none)."""
    with sqlite3.connect(path) as conn:
        conn.executemany("INSERT INTO annotators (username) VALUES (?)", [(u,) for u in usernames])


def test_row_error_in_another_step_is_counted_and_the_run_continues(
        legacy_db: Path, fake_db: FakeFactCheckerDB, monkeypatch: pytest.MonkeyPatch) -> None:
    """A row the database refuses (e.g. a CHECK violation) is one error; later rows still migrate (#395)."""
    _add_annotators(legacy_db, "bad", "good")

    def insert(annotator: Any, conn: Any = None) -> int:
        """Refuse the 'bad' annotator like a CHECK constraint."""
        if annotator.username == "bad":
            raise psycopg.errors.CheckViolation("violates check constraint")
        return 1
    monkeypatch.setattr(fake_db, "insert_or_get_annotator", insert)

    migrator = migrate.SQLiteToPostgresMigrator(str(legacy_db))
    migrator.migrate_annotators()

    assert migrator.stats["annotators"] == {"total": 2, "migrated": 1, "skipped": 0, "errors": 1}


def test_lost_connection_in_another_step_aborts_the_run(
        legacy_db: Path, fake_db: FakeFactCheckerDB, monkeypatch: pytest.MonkeyPatch) -> None:
    """A dropped connection is not counted per row in the non-verdict steps either: it stops the migration (#395)."""
    _add_annotators(legacy_db, "first", "second")
    calls: List[str] = []

    def lost(annotator: Any, conn: Any = None) -> int:
        """Fail like a dropped database connection."""
        calls.append(annotator.username)
        raise psycopg.OperationalError("server closed the connection")
    monkeypatch.setattr(fake_db, "insert_or_get_annotator", lost)

    migrator = migrate.SQLiteToPostgresMigrator(str(legacy_db))
    with pytest.raises(psycopg.OperationalError):
        migrator.migrate_annotators()
    assert calls == ["first"]


def test_processing_session_is_written_whole_in_one_upsert(
        legacy_db: Path, fake_db: FakeFactCheckerDB, monkeypatch: pytest.MonkeyPatch) -> None:
    """End fields go in the same write as the session, never a separate update (#408)."""
    with sqlite3.connect(legacy_db) as conn:
        conn.executemany(
            "INSERT INTO processing_metadata (session_id, input_file, total_statements, start_time, status, "
            "end_time, output_file, processed_statements, error_message) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [("bad", "in.json", 2, "2026-01-01", "completed", "not a time", None, 2, None),
             ("good", "in.json", 3, "2026-01-01", "failed", "2026-01-02", "out.json", 1, "boom"),
             ("blank", "in.json", 1, "2026-01-01", "running", "", "", None, "")])
    calls: List[Tuple[Dict[str, Any], bool]] = []
    updates: List[Any] = []

    def insert(session_data: Dict[str, Any], overwrite: bool = False, conn: Any = None) -> int:
        """Refuse a malformed or empty end time like PostgreSQL's TIMESTAMPTZ cast."""
        calls.append((session_data, overwrite))
        if session_data["end_time"] in ("not a time", ""):
            raise psycopg.errors.InvalidDatetimeFormat("invalid input syntax for type timestamp")
        return 1
    monkeypatch.setattr(fake_db, "insert_processing_session", insert, raising=False)
    monkeypatch.setattr(fake_db, "update_processing_session", lambda *a: updates.append(a), raising=False)

    migrator = migrate.SQLiteToPostgresMigrator(str(legacy_db))
    migrator.migrate_processing_metadata()

    assert migrator.stats["processing_metadata"] == {"total": 3, "migrated": 2, "skipped": 0, "errors": 1}
    assert len(calls) == 3 and updates == []
    assert all(overwrite is True for _, overwrite in calls)
    end_fields = [(s["end_time"], s["output_file"], s["processed_statements"], s["error_message"])
                  for s, _ in calls[1:]]
    # an empty legacy end field is unset (NULL), not a value PostgreSQL refuses
    assert end_fields == [("2026-01-02", "out.json", 1, "boom"), (None, None, None, None)]
