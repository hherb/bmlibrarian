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
    assert params == (PUBMED_ID, "aspirin", "aspirin", 3)
    assert results[0]['pmid'] == "12345"


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


def test_fact_checker_document_metadata_binds_pubmed_source_id():
    """The PostgreSQL fact-checker wrapper labels a PMID only for PubMed rows."""
    from bmlibrarian.factchecker.db.postgresql_db import PostgreSQLFactCheckerDB

    db = _FakeDbManager((5, "Title", "12345", "10.1/x", "12345"))
    wrapper = PostgreSQLFactCheckerDB.__new__(PostgreSQLFactCheckerDB)
    wrapper.db = type('Inner', (), {'db_manager': db})()

    metadata = wrapper.get_document_metadata(5)

    sql, params = _first(db)
    assert pmid_select_expr() in sql
    assert params == (PUBMED_ID, 5)
    assert metadata['pmid'] == "PMID:12345"

    db.row = (6, "Preprint", "10.1101/x", "10.1101/x", None)
    assert PostgreSQLFactCheckerDB.get_document_metadata(wrapper, 6)['pmid'] == ''


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
