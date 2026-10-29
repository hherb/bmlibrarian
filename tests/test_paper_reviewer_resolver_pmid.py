"""Paper reviewer stores PMIDs with a "PMID:" marker (#361).

`extract_pmid` only reads bare digits as a PMID for PubMed sources, so a
document imported under the `paper_reviewer` source must carry the marker.
"""

import re
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


@pytest.mark.parametrize("external_id, matches", [
    ("PMID:12345", True),
    ("pmid: 12345", True),
    ("10.1/x; PMID:12345", True),
    ("PMID:123456", False),
    ("PMID:1234", False),
])
def test_local_pmid_lookup_pattern(
    monkeypatch: pytest.MonkeyPatch, external_id: str, matches: bool
) -> None:
    """The lookup matches the exact marker, case-insensitively (POSIX ~* semantics)."""
    db = _FakeDbManager()
    monkeypatch.setattr("bmlibrarian.database.get_db_manager", lambda: db)

    DocumentResolver()._search_local_by_pmid("12345")

    sql, params = db.executed[0]
    assert "~*" in sql
    assert params[0] == "12345"
    assert bool(re.search(params[1], external_id, re.IGNORECASE)) is matches
