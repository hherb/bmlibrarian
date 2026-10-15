"""Tests for citation enrichment via get_document_details (golden rule 18).

Covers the pure PMID extraction used by ``database.get_document_details``,
the SQLite review-package ``get_document_details``, and the fact-checker
citation widget's enrichment helpers (which replaced inline SQL that queried
a non-existent SQLite ``pdf_filename`` column and labelled every
``external_id`` as a PMID).
"""

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
MEDRXIV_SOURCE_ID = PUBMED_SOURCE_ID + 1


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
    """A review-package SQLite DB with one PubMed and one medRxiv document."""
    db_path = tmp_path / "review.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_PATH.read_text())
    conn.executemany(
        """INSERT INTO documents (id, source_id, external_id, doi, title, abstract,
               authors, publication, publication_date, url, pdf_url)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (1, PUBMED_SOURCE_ID, "11111111", "10.1/a", "PubMed paper", "Abstract A",
             '["Smith J", "Doe A"]', "J Med", "2021-03-04", None, None),
            (2, MEDRXIV_SOURCE_ID, "22222222", "10.1101/b", "Preprint", "Abstract B",
             '["Roe R"]', "medRxiv", "2022-01-01", None, "https://x/b.pdf"),
        ],
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
        assert doc['pdf_filename'] is None

    def test_non_pubmed_document_has_no_pmid(self, review_db):
        doc = review_db.get_document_details(2)
        assert doc['pmid'] is None
        assert doc['external_id'] == "22222222"
        assert doc['pdf_url'] == "https://x/b.pdf"

    def test_missing_document(self, review_db):
        assert review_db.get_document_details(999) is None


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
        enriched = CitationListWidget._enrich_citation(
            MagicMock(), {'document_id': 2}, review_db
        )
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
        assert CitationListWidget._enrich_citation(MagicMock(), citation, db) is citation
