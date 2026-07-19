"""
Tests for the "poisoned transaction" batch data-loss bug class and its fix.

Bulk importers process many records inside a single database transaction.
Without per-record isolation, one bad record can destroy or discard a whole
batch that was already partially counted as imported:

- Calling ``conn.rollback()`` from inside the per-record error handler
  discards every record written earlier in the same transaction (already
  counted as a success).
- Doing nothing on error leaves the connection in an aborted-transaction
  state, so every subsequent record fails too, and the final
  ``conn.commit()`` silently discards the whole transaction.

``bmlibrarian.importers.transaction_utils.record_savepoint`` fixes this by
wrapping each record's writes in a SQL SAVEPOINT. These tests are fully
hermetic (no PostgreSQL required):

- The helper itself is exercised against a real in-memory ``sqlite3``
  connection, which supports the same SAVEPOINT / RELEASE SAVEPOINT /
  ROLLBACK TO SAVEPOINT syntax as PostgreSQL.
- Each of the five fixed importer functions is exercised against a fake
  DB-API connection/cursor that records executed SQL and can simulate a
  PostgreSQL "current transaction is aborted" state, so the tests fail
  meaningfully against the pre-fix code and pass after the fix.
"""

import csv
import sqlite3
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

from bmlibrarian.importers.transaction_utils import (
    DEFAULT_SAVEPOINT_NAME,
    record_savepoint,
)


# ──────────────────────────────────────────────────────────────────────────
# Helper unit tests (hermetic, real sqlite3 -- no PostgreSQL required)
# ──────────────────────────────────────────────────────────────────────────


class TestRecordSavepointHelper:
    """Unit tests for record_savepoint against a real SQLite connection."""

    def _connect(self) -> sqlite3.Connection:
        """Create an in-memory SQLite connection with an existing table."""
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE records (value TEXT)")
        conn.commit()
        return conn

    def test_failed_record_is_rolled_back_but_neighbors_persist(self) -> None:
        """Insert A, fail B inside a savepoint, insert C, commit -> A and C persist, B does not."""
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("BEGIN")

        with record_savepoint(cur):
            cur.execute("INSERT INTO records (value) VALUES ('A')")

        with pytest.raises(RuntimeError, match="boom"):
            with record_savepoint(cur):
                cur.execute("INSERT INTO records (value) VALUES ('B')")
                raise RuntimeError("boom")

        with record_savepoint(cur):
            cur.execute("INSERT INTO records (value) VALUES ('C')")

        conn.commit()

        cur.execute("SELECT value FROM records ORDER BY value")
        rows = [r[0] for r in cur.fetchall()]
        assert rows == ["A", "C"]

        conn.close()

    def test_savepoint_name_is_reusable_across_iterations(self) -> None:
        """The same savepoint name can be reused sequentially without error."""
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("BEGIN")

        for i, value in enumerate(["A", "B", "C"]):
            should_fail = value == "B"
            try:
                with record_savepoint(cur, "loop_record"):
                    cur.execute("INSERT INTO records (value) VALUES (?)", (value,))
                    if should_fail:
                        raise ValueError("simulated failure")
            except ValueError:
                continue

        conn.commit()
        cur.execute("SELECT value FROM records ORDER BY value")
        rows = [r[0] for r in cur.fetchall()]
        assert rows == ["A", "C"]
        conn.close()

    def test_default_savepoint_name_is_valid_identifier(self) -> None:
        """The default savepoint name must itself pass validation."""
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("BEGIN")
        with record_savepoint(cur, DEFAULT_SAVEPOINT_NAME):
            cur.execute("INSERT INTO records (value) VALUES ('X')")
        conn.commit()
        conn.close()

    @pytest.mark.parametrize(
        "bad_name",
        [
            "record; DROP TABLE records;--",
            "record name with spaces",
            "1_starts_with_digit",
            "",
            "a" * 100,
        ],
    )
    def test_invalid_savepoint_name_raises_before_touching_db(self, bad_name: str) -> None:
        """Non-identifier savepoint names are rejected without ever hitting the cursor."""
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("BEGIN")

        with pytest.raises(ValueError):
            with record_savepoint(cur, bad_name):
                cur.execute("INSERT INTO records (value) VALUES ('should-not-run')")

        conn.rollback()
        conn.close()


# ──────────────────────────────────────────────────────────────────────────
# Shared fake DB-API layer for importer-level tests
#
# Simulates PostgreSQL SAVEPOINT / aborted-transaction semantics closely
# enough to prove the "poisoned transaction" bug fails without the fix:
# once a statement raises, the connection is marked aborted and every
# further statement raises too, *except* ROLLBACK / ROLLBACK TO SAVEPOINT,
# which is exactly what record_savepoint uses to recover.
# ──────────────────────────────────────────────────────────────────────────


class SimulatedTransactionAbortedError(Exception):
    """Mirrors psycopg's errors.InFailedSqlTransaction for hermetic testing."""


class FakeConnection:
    """Minimal DB-API connection simulating PostgreSQL transaction state."""

    def __init__(self) -> None:
        self.aborted = False
        self.active_savepoints: set = set()
        self.rollback_calls = 0
        self.commit_calls = 0
        self.cur = FakeCursor(self)

    @contextmanager
    def cursor(self):
        yield self.cur

    def rollback(self) -> None:
        """Full ROLLBACK: clears the aborted flag and any open savepoints."""
        self.rollback_calls += 1
        self.aborted = False
        self.active_savepoints.clear()

    def commit(self) -> None:
        """COMMIT. On a real PostgreSQL connection, COMMIT of an aborted
        transaction is executed as ROLLBACK, silently discarding
        everything -- this mirrors that behavior."""
        self.commit_calls += 1
        if self.aborted:
            self.aborted = False
            self.active_savepoints.clear()


class FakeCursor:
    """Minimal DB-API cursor recording SQL and simulating abort semantics.

    ``record_handler(upper_sql, raw_sql, params) -> fetch_value`` is called
    for any statement that isn't SAVEPOINT/RELEASE SAVEPOINT/ROLLBACK; it
    may raise to simulate a record-level DB failure (e.g. a constraint
    violation), which marks the connection aborted exactly like PostgreSQL.
    """

    def __init__(self, conn: FakeConnection, record_handler=None) -> None:
        self.conn = conn
        self.record_handler = record_handler
        self.executed: List[Tuple[str, Any]] = []
        self.rowcount = 0
        self._next_fetch = None

    def execute(self, query: str, params: Any = None) -> None:
        raw = query.strip()
        upper = raw.upper()
        self.executed.append((raw, params))

        is_rollback_to_savepoint = upper.startswith("ROLLBACK TO SAVEPOINT")
        is_full_rollback = upper == "ROLLBACK"

        if self.conn.aborted:
            if is_rollback_to_savepoint:
                name = raw.split()[-1]
                if name not in self.conn.active_savepoints:
                    raise SimulatedTransactionAbortedError(f"no such savepoint {name!r}")
                self.conn.aborted = False
            elif is_full_rollback:
                self.conn.aborted = False
                self.conn.active_savepoints.clear()
            else:
                raise SimulatedTransactionAbortedError(
                    "current transaction is aborted, commands ignored "
                    "until end of transaction block"
                )
            self._next_fetch = None
            return

        if upper.startswith("SAVEPOINT"):
            self.conn.active_savepoints.add(raw.split()[-1])
            self._next_fetch = None
            return
        if upper.startswith("RELEASE SAVEPOINT"):
            self.conn.active_savepoints.discard(raw.split()[-1])
            self._next_fetch = None
            return
        if is_rollback_to_savepoint:
            self._next_fetch = None
            return
        if is_full_rollback:
            self.conn.active_savepoints.clear()
            self._next_fetch = None
            return

        try:
            self._next_fetch = (
                self.record_handler(upper, raw, params) if self.record_handler else None
            )
        except Exception:
            self.conn.aborted = True
            raise

    def fetchone(self):
        return self._next_fetch

    def close(self) -> None:
        pass


class FakeDBManager:
    """Minimal stand-in for bmlibrarian.database.DatabaseManager.

    Mirrors the real get_connection(): auto-commits are implicit (tests
    inspect executed SQL directly), and only rolls back if an exception
    propagates all the way out of the `with` block -- exactly like the
    real DatabaseManager.get_connection().
    """

    def __init__(self, conn: FakeConnection) -> None:
        self._conn = conn

    @contextmanager
    def get_connection(self):
        try:
            yield self._conn
        except Exception:
            self._conn.rollback()
            raise


def savepoint_statements(cursor: FakeCursor) -> List[str]:
    """Return executed SAVEPOINT statements."""
    return [q for q, _ in cursor.executed if q.upper().startswith("SAVEPOINT")]


def rollback_to_savepoint_statements(cursor: FakeCursor) -> List[str]:
    """Return executed ROLLBACK TO SAVEPOINT statements."""
    return [q for q, _ in cursor.executed if q.upper().startswith("ROLLBACK TO SAVEPOINT")]


# ──────────────────────────────────────────────────────────────────────────
# 1. medrxiv_importer.MedRxivImporter._process_papers
# ──────────────────────────────────────────────────────────────────────────


class TestMedRxivProcessPapers:
    """Tests for MedRxivImporter._process_papers savepoint isolation."""

    def _make_handler(self, fail_doi: str):
        state = {"insert_id": 0}

        def handler(upper: str, raw: str, params: Any):
            if upper.startswith("SELECT ID FROM DOCUMENT"):
                return None  # not found -> proceed to insert
            if upper.startswith("INSERT INTO DOCUMENT"):
                doi = params[1]
                if doi == fail_doi:
                    raise RuntimeError(f"simulated constraint violation for {doi}")
                state["insert_id"] += 1
                return (state["insert_id"],)
            return None

        return handler

    def _make_importer(self, cursor_conn: FakeConnection):
        from bmlibrarian.importers.medrxiv_importer import MedRxivImporter

        importer = object.__new__(MedRxivImporter)
        importer.db_manager = FakeDBManager(cursor_conn)
        importer.source_id = 1
        importer.extraction_strategy = "pdf_only"  # skip network/PDF extraction paths
        return importer

    def test_one_bad_paper_does_not_discard_the_batch(self) -> None:
        fail_doi = "10.1101/doi-2"
        conn = FakeConnection()
        conn.cur.record_handler = self._make_handler(fail_doi)
        importer = self._make_importer(conn)

        papers = [
            {
                "doi": "10.1101/doi-1", "title": "Paper 1", "abstract": "Abstract 1",
                "authors": [], "date": "2024-01-01", "category": "cat", "version": "1",
            },
            {
                "doi": fail_doi, "title": "Paper 2", "abstract": "Abstract 2",
                "authors": [], "date": "2024-01-02", "category": "cat", "version": "1",
            },
            {
                "doi": "10.1101/doi-3", "title": "Paper 3", "abstract": "Abstract 3",
                "authors": [], "date": "2024-01-03", "category": "cat", "version": "1",
            },
        ]

        success_count = importer._process_papers(papers, download_pdfs=False)

        assert success_count == 2
        assert conn.rollback_calls == 0, "full conn.rollback() must never be used per-record"
        assert len(savepoint_statements(conn.cur)) == 3
        assert len(rollback_to_savepoint_statements(conn.cur)) == 1

        # All three INSERT attempts are executed (the middle one raises and
        # is caught) -- proving processing continued past the failure.
        inserted_dois = [
            params[1] for q, params in conn.cur.executed if q.upper().startswith("INSERT INTO DOCUMENT")
        ]
        assert inserted_dois == ["10.1101/doi-1", fail_doi, "10.1101/doi-3"]


# ──────────────────────────────────────────────────────────────────────────
# 2. pubmed_importer.PubMedImporter._store_articles
# ──────────────────────────────────────────────────────────────────────────


class TestPubMedStoreArticles:
    """Tests for PubMedImporter._store_articles savepoint isolation."""

    def _make_handler(self, fail_pmid: str):
        state = {"insert_id": 0}

        def handler(upper: str, raw: str, params: Any):
            if upper.startswith("SELECT ID FROM DOCUMENT"):
                return None
            if upper.startswith("INSERT INTO DOCUMENT"):
                pmid = params[1]
                if pmid == fail_pmid:
                    raise RuntimeError(f"simulated constraint violation for {pmid}")
                state["insert_id"] += 1
                return (state["insert_id"],)
            return None

        return handler

    def _make_importer(self, cursor_conn: FakeConnection):
        from bmlibrarian.importers.pubmed_importer import PubMedImporter

        importer = object.__new__(PubMedImporter)
        importer.db_manager = FakeDBManager(cursor_conn)
        importer.source_id = 1
        return importer

    def test_one_bad_article_does_not_discard_the_batch(self) -> None:
        fail_pmid = "222"
        conn = FakeConnection()
        conn.cur.record_handler = self._make_handler(fail_pmid)
        importer = self._make_importer(conn)

        articles = [
            {
                "pmid": "111", "doi": None, "title": "Article 1", "abstract": "Abstract 1",
                "authors": [], "publication": "Journal A", "publication_date": "2024-01-01",
                "url": "https://pubmed/111", "mesh_terms": [], "keywords": [],
            },
            {
                "pmid": fail_pmid, "doi": None, "title": "Article 2", "abstract": "Abstract 2",
                "authors": [], "publication": "Journal A", "publication_date": "2024-01-02",
                "url": "https://pubmed/222", "mesh_terms": [], "keywords": [],
            },
            {
                "pmid": "333", "doi": None, "title": "Article 3", "abstract": "Abstract 3",
                "authors": [], "publication": "Journal A", "publication_date": "2024-01-03",
                "url": "https://pubmed/333", "mesh_terms": [], "keywords": [],
            },
        ]

        success_count = importer._store_articles(articles)

        assert success_count == 2
        assert conn.rollback_calls == 0, "full conn.rollback() must never be used per-record"
        assert len(savepoint_statements(conn.cur)) == 3
        assert len(rollback_to_savepoint_statements(conn.cur)) == 1

        # All three INSERT attempts are executed (the middle one raises and
        # is caught) -- proving processing continued past the failure.
        inserted_pmids = [
            params[1] for q, params in conn.cur.executed if q.upper().startswith("INSERT INTO DOCUMENT")
        ]
        assert inserted_pmids == ["111", fail_pmid, "333"]


# ──────────────────────────────────────────────────────────────────────────
# 3. europe_pmc_importer.EuropePMCImporter._upsert_batch
# ──────────────────────────────────────────────────────────────────────────


class TestEuropePMCUpsertBatch:
    """Tests for EuropePMCImporter._upsert_batch savepoint isolation.

    This file's pre-fix bug is the "no rollback at all" variant: once one
    article raises, the fake connection is left aborted and (without the
    fix) every subsequent article's SELECT/INSERT also raises
    SimulatedTransactionAbortedError, proving the poisoned-transaction bug.
    """

    def _make_handler(self, fail_pmcid: str):
        def handler(upper: str, raw: str, params: Any):
            if upper.startswith("SELECT ID, FULL_TEXT FROM DOCUMENT"):
                return None  # no existing record by external_id
            if upper.startswith("SELECT ID FROM DOCUMENT WHERE DOI"):
                return None  # no cross-source DOI match
            if upper.startswith("INSERT INTO DOCUMENT"):
                pmcid = params[1]
                if pmcid == fail_pmcid:
                    raise RuntimeError(f"simulated constraint violation for {pmcid}")
                return None
            return None

        return handler

    def _make_importer(self, tmp_path: Path):
        from bmlibrarian.importers.europe_pmc_importer import EuropePMCImporter

        return EuropePMCImporter(packages_dir=tmp_path)

    def test_one_bad_article_does_not_poison_the_rest_of_the_batch(self, tmp_path: Path) -> None:
        from bmlibrarian.importers.europe_pmc_importer import ArticleMetadata

        fail_pmcid = "PMC2"
        conn = FakeConnection()
        conn.cur.record_handler = self._make_handler(fail_pmcid)
        db_manager = FakeDBManager(conn)
        importer = self._make_importer(tmp_path)

        articles = [
            ArticleMetadata(pmcid="PMC1", title="Article 1"),
            ArticleMetadata(pmcid=fail_pmcid, title="Article 2"),
            ArticleMetadata(pmcid="PMC3", title="Article 3"),
        ]

        stats = importer._upsert_batch(articles, db_manager, source_id=1)

        assert stats["inserted"] == 2
        assert stats["failed"] == 1
        assert conn.rollback_calls == 0, "full conn.rollback() must never be used per-record"
        assert len(savepoint_statements(conn.cur)) == 3
        assert len(rollback_to_savepoint_statements(conn.cur)) == 1

        # Crucially, PMC3 must have been attempted (and inserted) -- i.e. the
        # connection was NOT left in an aborted state after PMC2 failed.
        inserted_pmcids = [
            params[1] for q, params in conn.cur.executed if q.upper().startswith("INSERT INTO DOCUMENT")
        ]
        assert inserted_pmcids == ["PMC1", fail_pmcid, "PMC3"]
        assert not conn.aborted


# ──────────────────────────────────────────────────────────────────────────
# 4. clinicaltrials_importer.ClinicalTrialsBulkImporter.import_trials
# ──────────────────────────────────────────────────────────────────────────

_TRIAL_XML_TEMPLATE = """<?xml version="1.0"?>
<clinical_study>
  <id_info><nct_id>{nct_id}</nct_id></id_info>
  <brief_title>Trial {nct_id}</brief_title>
  <sponsors>
    <lead_sponsor><agency>Sponsor Org</agency><agency_class>Other</agency_class></lead_sponsor>
  </sponsors>
  <overall_status>Completed</overall_status>
</clinical_study>
"""


class TestClinicalTrialsImportTrials:
    """Tests for ClinicalTrialsBulkImporter.import_trials savepoint isolation."""

    def _make_handler(self, fail_nct_id: str):
        def handler(upper: str, raw: str, params: Any):
            if upper.startswith("SELECT EXISTS"):
                return (True,)  # schema exists
            if upper.startswith("INSERT INTO TRANSPARENCY.DOCUMENT_METADATA"):
                nct_id = params[0]
                if nct_id == fail_nct_id:
                    raise RuntimeError(f"simulated constraint violation for {nct_id}")
                return None
            return None

        return handler

    def _make_zip(self, tmp_path: Path, nct_ids: List[str]) -> Path:
        zip_path = tmp_path / "AllPublicXML.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            for nct_id in nct_ids:
                zf.writestr(f"{nct_id}.xml", _TRIAL_XML_TEMPLATE.format(nct_id=nct_id))
        return zip_path

    def test_one_bad_trial_does_not_discard_the_run(self, tmp_path: Path, monkeypatch) -> None:
        from bmlibrarian.importers.clinicaltrials_importer import ClinicalTrialsBulkImporter

        fail_nct_id = "NCT00000002"
        conn = FakeConnection()
        conn.cur.record_handler = self._make_handler(fail_nct_id)
        db_manager = FakeDBManager(conn)

        monkeypatch.setattr("bmlibrarian.database.get_db_manager", lambda: db_manager)

        importer = ClinicalTrialsBulkImporter(data_dir=tmp_path)
        zip_path = self._make_zip(
            tmp_path, ["NCT00000001", fail_nct_id, "NCT00000003"]
        )

        stats = importer.import_trials(zip_path=zip_path)

        assert stats["parsed"] == 3
        assert stats["errors"] == 1
        assert conn.rollback_calls == 0, "full conn.rollback() must never be used per-record"
        assert len(savepoint_statements(conn.cur)) == 3
        assert len(rollback_to_savepoint_statements(conn.cur)) == 1

        inserted_nct_ids = [
            params[0]
            for q, params in conn.cur.executed
            if q.upper().startswith("INSERT INTO TRANSPARENCY.DOCUMENT_METADATA")
        ]
        assert inserted_nct_ids == ["NCT00000001", fail_nct_id, "NCT00000003"]
        assert not conn.aborted


# ──────────────────────────────────────────────────────────────────────────
# 5. retraction_watch_importer.RetractionWatchImporter.import_csv
# ──────────────────────────────────────────────────────────────────────────


class TestRetractionWatchImportCsv:
    """Tests for RetractionWatchImporter.import_csv savepoint isolation."""

    def _make_handler(self, fail_marker: str):
        def handler(upper: str, raw: str, params: Any):
            if upper.startswith("SELECT EXISTS"):
                return (True,)  # schema exists
            if upper.startswith("SELECT ID FROM PUBLIC.DOCUMENT WHERE DOI"):
                return (1,)  # always matches by DOI
            if upper.startswith("INSERT INTO TRANSPARENCY.DOCUMENT_METADATA"):
                reason = params[1]
                if reason == fail_marker:
                    raise RuntimeError("simulated constraint violation")
                return None
            if upper.startswith("UPDATE PUBLIC.DOI_METADATA"):
                return None
            return None

        return handler

    def _make_csv(self, tmp_path: Path, rows: List[Dict[str, str]]) -> Path:
        csv_path = tmp_path / "retraction_watch.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["DOI", "Reason"])
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        return csv_path

    def test_one_bad_row_does_not_discard_the_run(self, tmp_path: Path, monkeypatch) -> None:
        from bmlibrarian.importers.retraction_watch_importer import RetractionWatchImporter

        fail_marker = "FAIL_ROW"
        conn = FakeConnection()
        conn.cur.record_handler = self._make_handler(fail_marker)
        db_manager = FakeDBManager(conn)

        monkeypatch.setattr("bmlibrarian.database.get_db_manager", lambda: db_manager)

        importer = RetractionWatchImporter()
        csv_path = self._make_csv(
            tmp_path,
            [
                {"DOI": "10.1/a", "Reason": "reason-1"},
                {"DOI": "10.1/b", "Reason": fail_marker},
                {"DOI": "10.1/c", "Reason": "reason-3"},
            ],
        )

        stats = importer.import_csv(csv_path)

        assert stats["total_rows"] == 3
        assert stats["errors"] == 1
        assert stats["matched_by_doi"] == 2
        assert conn.rollback_calls == 0, "full conn.rollback() must never be used per-record"
        assert len(savepoint_statements(conn.cur)) == 3
        assert len(rollback_to_savepoint_statements(conn.cur)) == 1

        # All three INSERT attempts are executed (the middle one raises and
        # is caught) -- proving processing continued past the failure and
        # the connection was NOT left aborted for row 3.
        inserted_reasons = [
            params[1]
            for q, params in conn.cur.executed
            if q.upper().startswith("INSERT INTO TRANSPARENCY.DOCUMENT_METADATA")
        ]
        assert inserted_reasons == ["reason-1", fail_marker, "reason-3"]
        assert not conn.aborted
