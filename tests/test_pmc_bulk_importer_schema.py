"""Regression tests ensuring PMCBulkImporter DB queries match baseline_schema.sql.

These tests are hermetic: they use a fake database connection/cursor to capture
the exact SQL strings executed by ``PMCBulkImporter._upsert_article`` and verify
that every column name referenced by those queries actually exists in the
``public.document`` table as defined in ``baseline_schema.sql``.

No live PostgreSQL connection and no Ollama service are required.
"""

import re
from pathlib import Path
from typing import Any, List, Optional, Set, Tuple

import pytest

from bmlibrarian.importers.pmc_bulk_importer import ArticleMetadata, PMCBulkImporter

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "baseline_schema.sql"


def _load_document_columns() -> Set[str]:
    """Parse the ``public.document`` column names out of baseline_schema.sql.

    Returns:
        The set of column names declared in the ``CREATE TABLE public.document``
        statement of the real database schema.
    """
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    match = re.search(
        r"CREATE TABLE public\.document \((.*?)\n\);", schema_sql, re.DOTALL
    )
    assert match, "Could not find 'CREATE TABLE public.document' in baseline_schema.sql"

    columns: Set[str] = set()
    for line in match.group(1).splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        # Each column definition occupies its own line: "<name> <type> ...[,]"
        name = stripped.split()[0]
        columns.add(name)

    # Sanity check that parsing actually worked and picked up real columns.
    assert {"external_id", "source_id", "publication", "added_date"} <= columns
    assert "pmcid" not in columns
    assert "journal" not in columns
    assert "created_at" not in columns
    return columns


DOCUMENT_COLUMNS = _load_document_columns()


class _RecordingCursor:
    """Fake DB cursor that records executed SQL and returns queued fetchone() results."""

    def __init__(self, fetchone_results: List[Optional[Tuple[Any, ...]]]) -> None:
        """Initialize with a queue of values to return from fetchone().

        Args:
            fetchone_results: Values returned by successive fetchone() calls,
                in call order.
        """
        self._fetchone_results = list(fetchone_results)
        self.queries: List[Tuple[str, Any]] = []

    def execute(self, sql: str, params: Any = None) -> None:
        """Record an executed SQL statement together with its parameters."""
        self.queries.append((sql, params))

    def fetchone(self) -> Optional[Tuple[Any, ...]]:
        """Return the next queued fetchone() result, or None if exhausted."""
        if self._fetchone_results:
            return self._fetchone_results.pop(0)
        return None

    def __enter__(self) -> "_RecordingCursor":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        return None


class _FakeConnection:
    """Fake DB connection that hands out a single recording cursor."""

    def __init__(self, cursor: _RecordingCursor) -> None:
        """Initialize with the cursor this connection will yield.

        Args:
            cursor: The recording cursor to return from cursor().
        """
        self._cursor = cursor
        self.committed = False

    def cursor(self) -> _RecordingCursor:
        """Return the recording cursor (mimics psycopg connection.cursor())."""
        return self._cursor

    def commit(self) -> None:
        """Record that commit() was called (no-op otherwise)."""
        self.committed = True

    def __enter__(self) -> "_FakeConnection":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        return None


class _FakeDBManager:
    """Fake DatabaseManager exposing only get_connection(), like the real one."""

    def __init__(self, cursor: _RecordingCursor) -> None:
        """Initialize with the cursor the connection should expose.

        Args:
            cursor: The recording cursor to wire up behind get_connection().
        """
        self._connection = _FakeConnection(cursor)

    def get_connection(self) -> _FakeConnection:
        """Return the fake connection (mimics DatabaseManager.get_connection())."""
        return self._connection


def _sample_metadata() -> ArticleMetadata:
    """Build a representative ArticleMetadata instance for upsert tests."""
    return ArticleMetadata(
        pmcid="PMC1234567",
        pmid="98765432",
        doi="10.1234/example",
        title="Example Title",
        abstract="Example abstract text.",
        authors=["Doe J", "Smith A"],
        journal="Example Journal",
        publication_date="2024-01-01",
        year=2024,
        full_text="Full article text.",
        pdf_filename="2024/PMC1234567.pdf",
    )


def _extract_insert_columns(sql: str) -> List[str]:
    """Extract column names from an ``INSERT INTO document (...)`` statement."""
    match = re.search(r"INSERT INTO document\s*\((.*?)\)\s*VALUES", sql, re.DOTALL)
    assert match, f"Could not parse INSERT column list from SQL:\n{sql}"
    return [c.strip() for c in match.group(1).split(",") if c.strip()]


def _extract_update_set_columns(sql: str) -> List[str]:
    """Extract assignment target column names from an ``UPDATE document SET ... WHERE`` statement."""
    match = re.search(r"UPDATE document\s+SET\s+(.*?)\s+WHERE", sql, re.DOTALL)
    assert match, f"Could not parse UPDATE SET clause from SQL:\n{sql}"
    set_clause = match.group(1)
    return re.findall(r"(?:^|,)\s*(\w+)\s*=", set_clause)


def _extract_where_columns(sql: str) -> List[str]:
    """Extract column names referenced in a trailing ``WHERE`` clause."""
    match = re.search(r"WHERE\s+(.*?)\s*$", sql, re.DOTALL)
    assert match, f"Could not parse WHERE clause from SQL:\n{sql}"
    return re.findall(r"(\w+)\s*=", match.group(1))


class TestUpsertArticleSchemaCompliance:
    """Verify PMCBulkImporter._upsert_article only references real document columns."""

    def _make_importer(self, tmp_path: Path) -> PMCBulkImporter:
        """Create a PMCBulkImporter rooted at a throwaway temp directory."""
        return PMCBulkImporter(output_dir=tmp_path)

    def test_insert_path_uses_real_columns(self, tmp_path: Path) -> None:
        """When no existing row is found, the INSERT must reference only real columns."""
        cursor = _RecordingCursor(fetchone_results=[None])  # no existing row -> INSERT
        db_manager = _FakeDBManager(cursor)
        importer = self._make_importer(tmp_path)

        importer._upsert_article(db_manager, 1, _sample_metadata())

        insert_queries = [q for q, _ in cursor.queries if "INSERT INTO document" in q]
        assert insert_queries, "Expected _upsert_article to issue an INSERT when no row exists"

        for sql in insert_queries:
            referenced = _extract_insert_columns(sql)
            unknown = [c for c in referenced if c not in DOCUMENT_COLUMNS]
            assert not unknown, (
                f"INSERT references unknown column(s) {unknown} not present in "
                f"public.document (baseline_schema.sql). SQL was:\n{sql}"
            )

    def test_update_path_uses_real_columns(self, tmp_path: Path) -> None:
        """When an existing row is found, the UPDATE must reference only real columns."""
        cursor = _RecordingCursor(fetchone_results=[(42,)])  # existing row -> UPDATE
        db_manager = _FakeDBManager(cursor)
        importer = self._make_importer(tmp_path)

        importer._upsert_article(db_manager, 1, _sample_metadata())

        update_queries = [q for q, _ in cursor.queries if "UPDATE document" in q]
        assert update_queries, "Expected _upsert_article to issue an UPDATE when a row exists"

        for sql in update_queries:
            set_cols = _extract_update_set_columns(sql)
            where_cols = _extract_where_columns(sql)
            unknown = [c for c in set_cols + where_cols if c not in DOCUMENT_COLUMNS]
            assert not unknown, (
                f"UPDATE references unknown column(s) {unknown} not present in "
                f"public.document (baseline_schema.sql). SQL was:\n{sql}"
            )

    def test_existence_check_uses_real_columns(self, tmp_path: Path) -> None:
        """The existence-check SELECT must filter on real columns (source_id/
        external_id), never a nonexistent 'pmcid' column."""
        cursor = _RecordingCursor(fetchone_results=[None])
        db_manager = _FakeDBManager(cursor)
        importer = self._make_importer(tmp_path)

        importer._upsert_article(db_manager, 1, _sample_metadata())

        select_queries = [
            q for q, _ in cursor.queries if q.strip().upper().startswith("SELECT")
        ]
        assert select_queries, "Expected _upsert_article to check for an existing row via SELECT"

        for sql in select_queries:
            where_cols = _extract_where_columns(sql)
            unknown = [c for c in where_cols if c not in DOCUMENT_COLUMNS]
            assert not unknown, (
                f"SELECT existence-check references unknown column(s) {unknown}. "
                f"SQL was:\n{sql}"
            )

        # The lookup must scope by source_id so PMCID collisions across
        # sources cannot cause cross-source overwrites.
        assert any("source_id" in sql for sql in select_queries)

    @pytest.mark.parametrize("existing_row", [None, (42,)])
    def test_no_query_references_known_nonexistent_columns(
        self, tmp_path: Path, existing_row: Optional[Tuple[int]]
    ) -> None:
        """Regression guard for the specific bogus columns the old code used.

        'pmcid', 'pmid', 'journal', 'source', 'created_at' and 'updated_at' do
        not exist on public.document. PMCID must be stored in external_id
        (scoped by source_id), journal name in 'publication', and timestamps
        must use added_date/updated_date.
        """
        cursor = _RecordingCursor(fetchone_results=[existing_row])
        db_manager = _FakeDBManager(cursor)
        importer = self._make_importer(tmp_path)

        importer._upsert_article(db_manager, 1, _sample_metadata())

        assert cursor.queries, "_upsert_article did not execute any SQL"
        for sql, _ in cursor.queries:
            for bogus_column in ("pmcid", "pmid", "journal", "created_at", "updated_at"):
                assert not re.search(rf"\b{bogus_column}\b", sql), (
                    f"Query references nonexistent column '{bogus_column}':\n{sql}"
                )
            # 'source' (singular, a plain text column) must not appear as a
            # bare column reference; the real table only has 'source_id'.
            assert not re.search(r"\bsource\b(?!_id)", sql), (
                f"Query references nonexistent column 'source' (did you mean "
                f"'source_id'?):\n{sql}"
            )
