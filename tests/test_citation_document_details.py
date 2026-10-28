"""Tests for citation enrichment via get_document_details (golden rule 18).

Covers the pure PMID extraction used by ``database.get_document_details``,
the SQLite review-package ``get_document_details``, and the fact-checker
citation widget's enrichment helpers (which replaced inline SQL that queried
a non-existent SQLite ``pdf_filename`` column and labelled every
``external_id`` as a PMID).
"""

import importlib.util
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from bmlibrarian.database import extract_pmid
from bmlibrarian.factchecker.db.sqlite_db import (
    PUBMED_SOURCE_ID,
    SQLiteFactCheckerDB,
    parse_authors_json,
    year_from_iso_date,
)

SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent
    / "src" / "bmlibrarian" / "factchecker" / "db" / "sqlite_schema.sql"
)
EXPORT_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "export_review_package.py"
MEDRXIV_SOURCE_ID = PUBMED_SOURCE_ID + 1
# PubMed's id in a database not seeded by the setup wizard (#280)
OTHER_PUBMED_SOURCE_ID = 5
SOURCE_NAME_COLUMN = "    source_name TEXT,"


class TestExtractPmid:
    """extract_pmid only reports PMIDs for PubMed (or explicit PMID: ids)."""

    def test_pubmed_numeric_id_is_pmid(self):
        assert extract_pmid("12345678", "PubMed") == "12345678"

    def test_pubmed_source_name_case_insensitive(self):
        assert extract_pmid("12345678", "pubmed baseline") == "12345678"

    def test_numeric_id_from_other_source_is_not_pmid(self):
        assert extract_pmid("12345678", "medRxiv") is None
        assert extract_pmid("12345678", None) is None

    def test_explicit_pmid_prefix_any_source(self):
        assert extract_pmid("PMID:987654", "Europe PMC") == "987654"
        assert extract_pmid("pmid: 42", None) == "42"

    def test_empty_external_id(self):
        assert extract_pmid(None, "PubMed") is None
        assert extract_pmid("", "PubMed") is None

    def test_non_numeric_pubmed_id_rejected(self):
        assert extract_pmid("10.1101/2020.01.01", "PubMed") is None


class TestSqliteHelpers:
    """Pure helpers used by the SQLite review-package backend."""

    def test_parse_authors_json_list(self):
        assert parse_authors_json('["Smith J", "Doe A"]') == ["Smith J", "Doe A"]

    def test_parse_authors_json_plain_text(self):
        assert parse_authors_json("Smith J") == ["Smith J"]

    def test_parse_authors_json_empty(self):
        assert parse_authors_json(None) == []
        assert parse_authors_json("[]") == []

    def test_year_from_iso_date(self):
        assert year_from_iso_date("2023-05-01") == 2023
        assert year_from_iso_date("2023") == 2023
        assert year_from_iso_date("May 2023") is None
        assert year_from_iso_date(None) is None


@pytest.fixture
def review_db(tmp_path):
    """A review-package SQLite DB with one PubMed and one medRxiv document.

    PubMed is deliberately not source_id 1: the exported source name decides.
    """
    db_path = tmp_path / "review.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_PATH.read_text())
    conn.executemany(
        """INSERT INTO documents (id, source_id, source_name, external_id, doi, title,
               abstract, authors, publication, publication_date, url, pdf_url)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (1, OTHER_PUBMED_SOURCE_ID, "PubMed", "11111111", "10.1/a", "PubMed paper",
             "Abstract A", '["Smith J", "Doe A"]', "J Med", "2021-03-04", None, None),
            (2, PUBMED_SOURCE_ID, "medRxiv", "22222222", "10.1101/b", "Preprint",
             "Abstract B", '["Roe R"]', "medRxiv", "2022-01-01", None, "https://x/b.pdf"),
        ],
    )
    conn.commit()
    conn.close()
    db = SQLiteFactCheckerDB(str(db_path))
    yield db
    db.close()


@pytest.fixture
def legacy_review_db(tmp_path):
    """A package exported before #280: no documents.source_name column."""
    db_path = tmp_path / "legacy.db"
    schema = SCHEMA_PATH.read_text()
    assert SOURCE_NAME_COLUMN in schema
    conn = sqlite3.connect(db_path)
    conn.executescript(schema.replace(SOURCE_NAME_COLUMN, ""))
    conn.executemany(
        "INSERT INTO documents (id, source_id, external_id) VALUES (?, ?, ?)",
        [(1, PUBMED_SOURCE_ID, "11111111"), (2, MEDRXIV_SOURCE_ID, "22222222")],
    )
    conn.commit()
    conn.close()
    db = SQLiteFactCheckerDB(str(db_path))
    yield db
    db.close()


class TestSqliteGetDocumentDetails:
    """SQLite get_document_details mirrors the canonical keys."""

    def test_pubmed_document(self, review_db):
        doc = review_db.get_document_details(1)
        assert doc['title'] == "PubMed paper"
        assert doc['authors_list'] == ["Smith J", "Doe A"]
        assert doc['journal'] == "J Med"
        assert doc['year'] == 2021
        assert doc['pmid'] == "11111111"
        assert doc['source_name'] == "PubMed"
        assert doc['pdf_filename'] is None

    def test_non_pubmed_document_has_no_pmid(self, review_db):
        """A medRxiv document with source_id 1 is not taken for PubMed."""
        doc = review_db.get_document_details(2)
        assert doc['pmid'] is None
        assert doc['external_id'] == "22222222"
        assert doc['pdf_url'] == "https://x/b.pdf"

    def test_missing_document(self, review_db):
        assert review_db.get_document_details(999) is None

    def test_metadata_pmid_from_source_name(self, review_db):
        """get_document_metadata agrees with get_document_details."""
        assert review_db.get_document_metadata(1)['pmid'] == "PMID:11111111"
        assert review_db.get_document_metadata(2)['pmid'] == ''

    def test_legacy_package_assumes_pubmed_is_source_1(self, legacy_review_db):
        """Packages without source names keep the old id-1 convention."""
        assert legacy_review_db.get_document_details(1)['pmid'] == "11111111"
        assert legacy_review_db.get_document_details(1)['source_name'] is None
        assert legacy_review_db.get_document_details(2)['pmid'] is None
        assert legacy_review_db.get_document_metadata(1)['pmid'] == "PMID:11111111"
        assert legacy_review_db.get_document_metadata(2)['pmid'] == ''


def test_export_script_writes_source_names(tmp_path):
    """export_review_package.py stores sources.name, so PMIDs survive any source id."""
    spec = importlib.util.spec_from_file_location("export_review_package", EXPORT_SCRIPT)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    db_file = tmp_path / "package.db"
    sqlite_conn = script.create_sqlite_database(db_file)
    pg_cursor = MagicMock()
    pg_cursor.fetchall.return_value = [
        (101, OTHER_PUBMED_SOURCE_ID, "pubmed", "123", None, "t", "a", ["A B"],
         None, None, None, None, None, None),
    ]
    pg_db = MagicMock()
    pg_conn = pg_db.db_manager.get_connection.return_value.__enter__.return_value
    pg_conn.cursor.return_value.__enter__.return_value = pg_cursor

    assert script.export_documents(pg_db, sqlite_conn, {101}) == 1
    sqlite_conn.close()

    assert "JOIN sources" in pg_cursor.execute.call_args.args[0]
    db = SQLiteFactCheckerDB(str(db_file))
    try:
        assert db.get_document_details(101)['pmid'] == "123"
    finally:
        db.close()


class TestCitationEnrichment:
    """Citation widget enrichment helpers."""

    def test_needs_enrichment_detects_placeholders(self):
        from bmlibrarian.gui.qt.plugins.fact_checker.citation_widget import (
            citation_needs_enrichment,
        )
        complete = {
            'abstract': 'a', 'pmid': '1', 'title': 't', 'authors': 'x',
            'journal': 'j', 'pub_year': 2020,
        }
        assert not citation_needs_enrichment(complete)
        assert citation_needs_enrichment({**complete, 'journal': 'Unknown journal'})
        assert citation_needs_enrichment({**complete, 'pmid': 'N/A'})
        assert citation_needs_enrichment({**complete, 'abstract': ''})

    def test_merge_fills_only_missing_fields(self):
        from bmlibrarian.gui.qt.plugins.fact_checker.citation_widget import (
            merge_document_details,
        )
        citation = {'document_id': 1, 'title': 'Kept title', 'pmid': 'N/A',
                    'authors': 'Unknown authors', 'pub_year': 'N/A'}
        details = {'title': 'DB title', 'pmid': '123', 'authors_list': ['A B', 'C D'],
                   'journal': 'J', 'year': 2020, 'abstract': 'abs', 'doi': '10.1/x',
                   'pdf_url': None, 'pdf_filename': '2020/x.pdf'}
        merged = merge_document_details(citation, details)
        assert merged['title'] == 'Kept title'
        assert merged['pmid'] == '123'
        assert merged['authors'] == 'A B, C D'
        assert merged['pub_year'] == 2020
        assert merged['journal'] == 'J'
        assert merged['pdf_filename'] == '2020/x.pdf'
        assert merged['pdf_url'] == ''
        assert citation['pmid'] == 'N/A'  # input not mutated

    def test_merge_non_pubmed_keeps_na_pmid(self):
        from bmlibrarian.gui.qt.plugins.fact_checker.citation_widget import (
            merge_document_details,
        )
        merged = merge_document_details({'pmid': None}, {'pmid': None})
        assert merged['pmid'] == 'N/A'

    def test_enrich_citation_uses_backend_details(self, review_db):
        """_enrich_citation reads through db.get_document_details, no SQL."""
        from bmlibrarian.gui.qt.plugins.fact_checker.citation_widget import (
            CitationListWidget,
        )
        enriched, failed = CitationListWidget._enrich_citation(
            MagicMock(), {'document_id': 2}, review_db
        )
        assert not failed
        assert enriched['title'] == 'Preprint'
        assert enriched['pmid'] == 'N/A'
        assert enriched['authors'] == 'Roe R'
        assert enriched['pub_year'] == 2022

    def test_enrich_citation_backend_error_returns_input(self):
        from bmlibrarian.gui.qt.plugins.fact_checker.citation_widget import (
            CitationListWidget,
        )
        db = MagicMock()
        db.get_document_details.side_effect = RuntimeError("db down")
        citation = {'document_id': 5}
        enriched, failed = CitationListWidget._enrich_citation(MagicMock(), citation, db)
        assert enriched is citation
        assert failed  # reported, not mistaken for "no details"

    def test_enrich_citation_skips_complete_citation(self):
        """A complete citation never queries the database."""
        from bmlibrarian.gui.qt.plugins.fact_checker.citation_widget import (
            CitationListWidget,
        )
        db = MagicMock()
        citation = {
            'document_id': 5, 'abstract': 'A', 'pmid': '1', 'title': 'T',
            'authors': 'X Y', 'journal': 'J', 'pub_year': 2020,
        }
        enriched, failed = CitationListWidget._enrich_citation(MagicMock(), citation, db)
        assert enriched is citation and not failed
        db.get_document_details.assert_not_called()

    def test_identifier_placeholders_are_not_identifiers(self):
        """'N/A' must not reach PDF discovery as a PMID."""
        from bmlibrarian.gui.qt.plugins.fact_checker.citation_widget import (
            identifier_or_none,
        )
        assert identifier_or_none({'pmid': 'N/A'}, 'pmid') is None
        assert identifier_or_none({'pmid': ''}, 'pmid') is None
        assert identifier_or_none({'pmid': 123}, 'pmid') == '123'
        assert identifier_or_none({'doi': '10.1/x'}, 'doi') == '10.1/x'


class _FakeCursor:
    """Minimal psycopg cursor stand-in returning one dict row."""

    def __init__(self, row):
        """Store the row to return."""
        self._row = row
        self.executed = []

    def __enter__(self):
        """Enter the cursor context."""
        return self

    def __exit__(self, *exc):
        """Leave the cursor context without suppressing errors."""
        return False

    def execute(self, sql, params=None):
        """Record the executed statement."""
        self.executed.append((sql, params))

    def fetchone(self):
        """Return the configured row."""
        return self._row


class _FakeDbManager:
    """DatabaseManager stand-in whose connection yields ``_FakeCursor``."""

    def __init__(self, row=None, error=None):
        """Configure the row to return or the error to raise."""
        self.cursor = _FakeCursor(row)
        self._error = error

    def get_connection(self):
        """Return a context manager like DatabaseManager.get_connection."""
        from contextlib import contextmanager

        @contextmanager
        def connection():
            """Yield a connection whose cursor is the fake cursor (or raise)."""
            if self._error:
                raise self._error
            conn = MagicMock()
            conn.cursor.return_value = self.cursor
            yield conn
        return connection()


def _document_row(**overrides):
    """A document row as the canonical query returns it."""
    row = {
        'id': 9, 'title': 'T', 'abstract': 'A', 'authors': ['A B'],
        'journal': 'J', 'publication_date': None, 'year': 2020, 'doi': None,
        'external_id': '123', 'source_id': 7, 'url': None, 'pdf_url': None,
        'pdf_filename': None, 'full_text': None, 'keywords': None,
        'mesh_terms': None, 'source_name': 'pubmed',
    }
    row.update(overrides)
    return row


class TestCanonicalDocumentDetails:
    """``database.fetch_document_details`` / ``get_document_details``."""

    def test_pmid_derived_from_source_name(self):
        """The joined source name (not source_id) decides the PMID."""
        from bmlibrarian.database import fetch_document_details
        doc = fetch_document_details(9, _FakeDbManager(_document_row()))
        assert doc['pmid'] == '123'

        doc = fetch_document_details(
            9, _FakeDbManager(_document_row(source_name='medrxiv', source_id=1))
        )
        assert doc['pmid'] is None

    def test_null_title_is_still_found(self):
        """A NULL title used to raise inside a debug f-string -> None."""
        from bmlibrarian.database import fetch_document_details
        doc = fetch_document_details(9, _FakeDbManager(_document_row(title=None)))
        assert doc is not None and doc['title'] is None

    def test_missing_document_is_none(self):
        """Missing document is none."""
        from bmlibrarian.database import fetch_document_details
        assert fetch_document_details(9, _FakeDbManager(None)) is None

    def test_fetch_raises_but_get_returns_none_on_db_error(self, monkeypatch):
        """Only the raising variant lets callers tell an outage from a miss."""
        import bmlibrarian.database as database
        failing = _FakeDbManager(error=RuntimeError("connection refused"))
        with pytest.raises(RuntimeError):
            database.fetch_document_details(9, failing)

        monkeypatch.setattr(database, 'get_db_manager', lambda: failing)
        assert database.get_document_details(9) is None

    def test_postgres_backend_uses_own_connection_and_raises(self):
        """The fact-checker backend queries self.db.db_manager and raises."""
        from bmlibrarian.factchecker.db.postgresql_db import PostgreSQLFactCheckerDB
        backend = PostgreSQLFactCheckerDB.__new__(PostgreSQLFactCheckerDB)
        backend.db = MagicMock()
        backend.db.db_manager = _FakeDbManager(_document_row())
        assert backend.get_document_details(9)['pmid'] == '123'

        backend.db.db_manager = _FakeDbManager(error=RuntimeError("down"))
        with pytest.raises(RuntimeError):
            backend.get_document_details(9)
