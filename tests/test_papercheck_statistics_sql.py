"""Regression test for PaperCheckDB.get_statistics().

Guards against the psycopg placeholder-in-quotes bug: ``INTERVAL '%s hours'``
puts the ``%s`` inside a SQL string literal, so psycopg never substitutes it
and PostgreSQL rejects the query. The blanket except then returned the
all-zeros fallback dict on every call, so statistics were silently always 0.

Hermetic: uses a fake connection that records executed SQL; no PostgreSQL.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from bmlibrarian.paperchecker.database import PaperCheckDB

# A %s placeholder inside single quotes is never substituted by psycopg
QUOTED_PLACEHOLDER = re.compile(r"'[^']*%s[^']*'")


class _FakeCursor:
    """Cursor stand-in that records queries and returns empty results."""

    def __init__(self, executed: List[Tuple[str, Optional[tuple]]]) -> None:
        self._executed = executed

    def execute(self, query: str, params: Optional[tuple] = None) -> None:
        self._executed.append((query, params))

    def fetchone(self) -> Dict[str, Any]:
        return {"count": 0}

    def fetchall(self) -> List[Dict[str, Any]]:
        return []

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *args: Any) -> None:
        return None


class _FakeConnection:
    """Connection stand-in exposing cursor() like psycopg with dict rows."""

    def __init__(self) -> None:
        self.executed: List[Tuple[str, Optional[tuple]]] = []

    def cursor(self, *args: Any, **kwargs: Any) -> _FakeCursor:
        return _FakeCursor(self.executed)


def test_get_statistics_queries_contain_no_quoted_placeholders() -> None:
    """No executed query may hide a %s placeholder inside a string literal."""
    db = PaperCheckDB.__new__(PaperCheckDB)
    db.conn = _FakeConnection()
    db.schema = "papercheck"

    stats = db.get_statistics()

    assert db.conn.executed, "get_statistics() executed no queries"
    offenders = [q for q, _ in db.conn.executed if QUOTED_PLACEHOLDER.search(q)]
    assert offenders == [], (
        "quoted %s placeholder found (psycopg will not substitute it): "
        f"{offenders}"
    )
    # With all queries succeeding, the method must return real (zero) counts,
    # i.e. it must not have fallen into the exception path.
    assert stats["recent_activity"] == 0
