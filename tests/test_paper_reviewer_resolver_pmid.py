"""Paper reviewer stores PMIDs with a "PMID:" marker (#361).

`extract_pmid` only reads bare digits as a PMID for PubMed sources, so a
document imported under the `paper_reviewer` source must carry the marker.
"""

from contextlib import contextmanager
from typing import Any, List, Optional, Tuple

import pytest

from bmlibrarian.agents.paper_reviewer.resolver import DocumentResolver
from bmlibrarian.database import extract_pmid

SOURCE_ID = 9
NEW_DOC_ID = 42


class _FakeDbManager:
    """Answers the resolver's queries in order and records them."""

    def __init__(self, existing_id: Optional[int] = None) -> None:
        """Set the id the "already exists" check returns (None: not found)."""
        self.existing_id = existing_id
        self.lookup_rows: List[dict] = []
        self.executed: List[Tuple[str, Any]] = []

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
    def cursor(self, row_factory: Any = None):
        """Yield a recording cursor."""
        yield _FakeCursor(self.manager)

    def commit(self) -> None:
        """No-op commit."""


class _FakeCursor:
    """Cursor stub returning a canned row per statement kind."""

    def __init__(self, manager: _FakeDbManager) -> None:
        """Keep the owning manager."""
        self.manager = manager
        self.last_sql = ""

    def execute(self, sql: str, params: Any = None) -> None:
        """Record the statement."""
        self.last_sql = sql
        self.manager.executed.append((sql, params))

    def fetchone(self) -> Optional[Tuple[Any, ...]]:
        """Return the row for the last statement."""
        if "FROM sources" in self.last_sql:
            return (SOURCE_ID,)
        if "INSERT INTO document" in self.last_sql:
            return (NEW_DOC_ID,)
        if "FROM document" in self.last_sql:
            return (self.manager.existing_id,) if self.manager.existing_id else None
        return None

    def fetchall(self) -> List[dict]:
        """Return the rows the PMID lookup finds."""
        return self.manager.lookup_rows


@pytest.fixture
def fake_db(monkeypatch: pytest.MonkeyPatch) -> _FakeDbManager:
    """Route the resolver's get_db_manager() to a fake."""
    db = _FakeDbManager()
    monkeypatch.setattr("bmlibrarian.database.get_db_manager", lambda: db)
    return db


def _insert_params(db: _FakeDbManager) -> Tuple[Any, ...]:
    """Return the parameters of the INSERT statement."""
    return next(p for sql, p in db.executed if "INSERT INTO document" in sql)


def _exists_params(db: _FakeDbManager) -> Tuple[Any, ...]:
    """Return the parameters of the "already exists" check."""
    return next(p for sql, p in db.executed if "external_id = ANY" in sql)


def test_pmid_only_document_stored_with_marker(fake_db: _FakeDbManager) -> None:
    """A PMID without a DOI is stored as PMID:<digits>, which extract_pmid reads."""
    doc_id = DocumentResolver().import_document({'title': 'T', 'pmid': '12345'})

    assert doc_id == NEW_DOC_ID
    external_id = _insert_params(fake_db)[1]
    assert external_id == "PMID:12345"
    assert extract_pmid(external_id, "paper_reviewer") == "12345"
    # The dedup check also matches rows stored before #361 (bare digits)
    assert _exists_params(fake_db) == (SOURCE_ID, ["PMID:12345", "12345"])


def test_legacy_bare_pmid_row_is_reused(fake_db: _FakeDbManager) -> None:
    """An existing bare-digit row is found, not inserted again."""
    fake_db.existing_id = 7

    assert DocumentResolver().import_document({'title': 'T', 'pmid': '12345'}) == 7
    assert not any("INSERT INTO document" in sql for sql, _ in fake_db.executed)


def test_doi_stays_external_id(fake_db: _FakeDbManager) -> None:
    """A DOI is still the external_id, and only it is checked for duplicates."""
    DocumentResolver().import_document({'title': 'T', 'doi': '10.1/x', 'pmid': '12345'})

    assert _insert_params(fake_db)[1] == "10.1/x"
    assert _exists_params(fake_db) == (SOURCE_ID, ["10.1/x"])


def test_local_pmid_lookup_uses_exact_indexed_match(fake_db: _FakeDbManager) -> None:
    """The lookup matches bare and marked PMIDs exactly, without a table scan."""
    fake_db.lookup_rows = [{'external_id': 'PMID:12345', 'source_name': 'paper_reviewer'}]

    doc = DocumentResolver()._search_local_by_pmid("12345")

    sql, params = fake_db.executed[0]
    assert "external_id = ANY" in sql and "~" not in sql
    assert params == (["12345", "PMID:12345"],)
    assert doc['pmid'] == "12345"


def test_local_pmid_lookup_skips_bare_digits_from_other_sources(fake_db: _FakeDbManager) -> None:
    """A numeric external_id outside PubMed is not taken for the PMID."""
    fake_db.lookup_rows = [
        {'external_id': '12345', 'source_name': 'medrxiv'},
        {'external_id': '12345', 'source_name': 'pubmed', 'title': 'Hit'},
    ]
    assert DocumentResolver()._search_local_by_pmid("12345")['title'] == 'Hit'

    fake_db.lookup_rows = fake_db.lookup_rows[:1]
    assert DocumentResolver()._search_local_by_pmid("12345") is None


@pytest.mark.parametrize("external_id, source_name, expected", [
    ("12345", "pubmed", "12345"),
    ("12345", "medrxiv", None),
    ("PMID: 12345", "paper_reviewer", "12345"),
    ("10.1/x", "paper_reviewer", None),
])
def test_db_row_to_doc_derives_pmid_with_extract_pmid(
    external_id: str, source_name: str, expected: Optional[str]
) -> None:
    """Rows are labelled with a PMID exactly as extract_pmid would."""
    row = {'external_id': external_id, 'source_name': source_name}
    assert DocumentResolver()._db_row_to_doc(row)['pmid'] == expected
