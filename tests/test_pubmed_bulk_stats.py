"""Regression test for DownloadTracker.get_stats().

Guards against the crash where get_stats() summed an ``articles_count``
column that does not exist in the ``pubmed_download_log`` schema (the
class's own docstrings say it is not stored), making
``pubmed_bulk_cli.py status`` raise UndefinedColumn on every invocation.

Hermetic: uses a fake connection; no PostgreSQL required.
"""

from contextlib import contextmanager
from typing import Any, Iterator, List, Optional, Tuple

from bmlibrarian.importers.pubmed_bulk_importer import DownloadTracker

# Columns that actually exist in pubmed_download_log (see
# DownloadTracker._ensure_tracking_table)
EXISTING_COLUMNS = {
    "id", "file_name", "file_type", "download_date", "processed",
    "process_date", "file_size", "checksum", "status",
}


class _FakeCursor:
    """Cursor stand-in recording queries; returns an all-zero stats row."""

    def __init__(self, executed: List[str]) -> None:
        self._executed = executed

    def execute(self, query: str, params: Optional[tuple] = None) -> None:
        self._executed.append(query)

    def fetchone(self) -> Tuple[int, ...]:
        # One value per selected column; generous length so the test fails
        # on the SQL contents, not on tuple unpacking.
        return (0, 0, 0, 0, 0, 0, 0, 0)

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *args: Any) -> None:
        return None


class _FakeDBManager:
    """DatabaseManager stand-in exposing get_connection() as a context manager."""

    def __init__(self) -> None:
        self.executed: List[str] = []

    @contextmanager
    def get_connection(self) -> Iterator["_FakeDBManager"]:
        yield self

    def cursor(self, *args: Any, **kwargs: Any) -> _FakeCursor:
        return _FakeCursor(self.executed)


def test_get_stats_only_references_existing_columns() -> None:
    """get_stats() must not query columns absent from pubmed_download_log."""
    tracker = DownloadTracker.__new__(DownloadTracker)
    tracker.db_manager = _FakeDBManager()

    stats = tracker.get_stats()

    executed = "\n".join(tracker.db_manager.executed)
    assert "articles_count" not in executed, (
        "get_stats() references articles_count, which does not exist in "
        "pubmed_download_log - pubmed_bulk_cli.py status crashes on this"
    )
    # The CLI formats these with ':,' so they must all be ints
    for key in (
        "total_files", "processed_files", "baseline_files",
        "update_files", "total_size_bytes", "total_articles",
    ):
        assert isinstance(stats[key], int), f"{key} must be an int"
