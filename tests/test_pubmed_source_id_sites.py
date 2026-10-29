"""PMID lookups use the database's PubMed source id, never a hardcoded 1 (#344).

On a database where PubMed is not ``sources.id = 1`` (e.g. the clean PG18
import), a hardcoded 1 labels another source's ``external_id`` as a PMID and
misses real PubMed rows. Each site must bind ``pubmed_source_id(db_manager)``.
"""

from contextlib import contextmanager
from typing import Any, List, Optional, Tuple
from unittest.mock import patch

from bmlibrarian.database import pmid_select_expr

PUBMED_ID = 7


class _FakeDbManager:
    """Records executed SQL and returns canned rows."""

    def __init__(self, row: Optional[Tuple[Any, ...]] = None) -> None:
        """Store the row every fetch returns."""
        self.row = row
        self.executed: List[Tuple[str, Any]] = []

    def get_cached_source_ids(self) -> dict:
        """PubMed is not source 1 in this database."""
        return {'pubmed': PUBMED_ID, 'medrxiv': 1, 'others': [2]}

    @contextmanager
    def get_connection(self):
        """Yield a connection whose cursor records executions."""
        yield _FakeConn(self)


class _FakeConn:
    """Connection stub."""

    def __init__(self, manager: _FakeDbManager) -> None:
        """Keep the owning manager."""
        self.manager = manager

    @contextmanager
    def cursor(self):
        """Yield a recording cursor."""
        yield _FakeCursor(self.manager)


class _FakeCursor:
    """Cursor stub."""

    def __init__(self, manager: _FakeDbManager) -> None:
        """Keep the owning manager."""
        self.manager = manager

    def execute(self, sql: str, params: Any = None) -> None:
        """Record the statement."""
        self.manager.executed.append((str(sql), params))

    def fetchone(self) -> Optional[Tuple[Any, ...]]:
        """Return the canned row."""
        return self.manager.row

    def fetchall(self) -> List[Tuple[Any, ...]]:
        """Return the canned row as a list."""
        return [self.manager.row] if self.manager.row else []


def _first(manager: _FakeDbManager) -> Tuple[str, Any]:
    """Return the first executed statement."""
    assert manager.executed, "no SQL executed"
    return manager.executed[0]


def test_reference_builder_binds_pubmed_source_id():
    """ReferenceBuilder reads the PMID through the PubMed id of its database."""
    from bmlibrarian.writing.reference_builder import ReferenceBuilder

    db = _FakeDbManager(
        (5, "Title", None, None, "J", 2020, None, "12345", "Smith J")
    )
    builder = ReferenceBuilder()
    builder._db_manager = db

    metadata = builder._fetch_document_metadata([5])

    sql, params = _first(db)
    assert pmid_select_expr('d') in sql
    assert params == (PUBMED_ID, [5])
    assert metadata[5].pmid == "12345"


def test_citation_search_panel_keyword_search_binds_pubmed_source_id():
    """The citation editor's keyword search binds the PubMed id."""
    from bmlibrarian.gui.qt.widgets.citation_editor.search_panel import SearchWorker

    db = _FakeDbManager((5, "Title", "12345", None, 2020, "J", 0.5))
    worker = SearchWorker("aspirin", "keyword", 3)
    with patch('bmlibrarian.database.get_db_manager', return_value=db), \
            patch.object(SearchWorker, '_enrich_results', side_effect=lambda r: r):
        results = worker._keyword_search()

    sql, params = _first(db)
    assert pmid_select_expr('d') in sql
    # The document table has no journal column
    assert "d.publication AS journal" in sql
    assert params == (PUBMED_ID, "aspirin", "aspirin", 3)
    assert results[0]['pmid'] == "12345"


def test_pubmed_search_lab_existing_pmids_binds_pubmed_source_id():
    """The lab's existing-PMID check binds the PubMed id before the PMIDs."""
    from types import SimpleNamespace

    from bmlibrarian.lab.pubmed_search_lab import PubMedSearchWorker

    db = _FakeDbManager(("111", 5))
    worker = PubMedSearchWorker.__new__(PubMedSearchWorker)
    articles = [SimpleNamespace(pmid="111"), SimpleNamespace(pmid="222")]
    with patch('bmlibrarian.database.get_db_manager', return_value=db):
        existing = worker._get_existing_pmids(articles)

    assert db.executed[0][1] == [PUBMED_ID, "111", "222"]
    assert existing == {"111": 5}


def test_document_processor_maps_pmid_and_later_columns():
    """DocumentProcessor binds the PubMed id and keeps the column mapping."""
    from bmlibrarian.gui.qt.core.document_processor import DocumentProcessor

    row = (5, "Title", "Abstract", "10.1/x", "12345", "http://u", "f.pdf", "Full", 2020)
    db = _FakeDbManager(row)
    processor = DocumentProcessor.__new__(DocumentProcessor)
    processor.db_manager = db

    info = processor.get_document_info(5)

    sql, params = _first(db)
    assert pmid_select_expr('d') in sql
    assert params == (PUBMED_ID, 5)
    assert (info.pmid, info.pdf_url, info.pdf_filename, info.full_text, info.year) == (
        "12345", "http://u", "f.pdf", "Full", 2020
    )


def test_fact_checker_document_metadata_uses_extract_pmid():
    """The PostgreSQL fact-checker derives the PMID like the SQLite backend (#363)."""
    from bmlibrarian.factchecker.db.postgresql_db import PostgreSQLFactCheckerDB

    db = _FakeDbManager((5, "Title", "12345", "10.1/x", "PubMed"))
    wrapper = PostgreSQLFactCheckerDB.__new__(PostgreSQLFactCheckerDB)
    wrapper.db = type('Inner', (), {'db_manager': db})()

    metadata = wrapper.get_document_metadata(5)

    sql, params = _first(db)
    assert "JOIN sources" in sql
    assert params == (5,)
    assert metadata['pmid'] == "PMID:12345"
    assert metadata['doi'] == "DOI:10.1/x"

    cases = [
        ("10.1101/x", "medRxiv", ''),          # non-PubMed DOI
        ("12345", "medRxiv", ''),              # bare digits only count for PubMed
        ("abc", "PubMed", ''),                 # non-numeric PubMed id is no PMID
        ("PMID:777", "paper_reviewer", "PMID:777"),  # marker honoured for any source
        ("12345", None, ''),                   # source row missing (LEFT JOIN)
    ]
    for external_id, source_name, expected in cases:
        db.row = (6, "Doc", external_id, None, source_name)
        assert wrapper.get_document_metadata(6)['pmid'] == expected, (external_id, source_name)


def test_systematic_review_source_filter_uses_source_name_not_id():
    """Results are classified by source name; source_id 1 is not PubMed."""
    from bmlibrarian.agents.systematic_review.executor import SearchExecutor

    executor = SearchExecutor.__new__(SearchExecutor)
    results = [
        {'id': 1, 'source_id': 1, 'source_name': 'medRxiv'},
        {'id': 2, 'source_id': PUBMED_ID, 'source_name': 'PubMed'},
        {'id': 3, 'source_id': 2, 'source_name': None},
    ]

    pubmed_only = executor._filter_results_by_source(results, True, False, False)
    medrxiv_only = executor._filter_results_by_source(results, False, True, False)
    others_only = executor._filter_results_by_source(results, False, False, True)

    assert [d['id'] for d in pubmed_only] == [2]
    assert [d['id'] for d in medrxiv_only] == [1]
    assert [d['id'] for d in others_only] == [3]
