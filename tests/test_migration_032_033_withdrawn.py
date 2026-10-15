"""
Integration tests for migrations 032 (withdrawn PMIDs) and 033 (fold the first
revision's document.withdrawn column into the baseline withdrawn_date).

Opt-in: set BMLIBRARIAN_TEST_DB_ENV to an env file for a *development* database
with the BMLibrarian schema (e.g. ~/.bmlibrarian/.env_pg18_dev). Refuses any
database the test guard protects. Each migration is applied twice to prove
idempotency and stays applied, as migrations do; the 033 data test runs in a
transaction that is rolled back.
"""

import os
from pathlib import Path
from typing import Iterator

import psycopg
import pytest
from dotenv import dotenv_values

from bmlibrarian.db_test_guard import is_protected_database

pytestmark = pytest.mark.requires_database

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
MIGRATION_032 = MIGRATIONS_DIR / "032_withdrawn_documents.sql"
MIGRATION_033 = MIGRATIONS_DIR / "033_fold_withdrawn_into_withdrawn_date.sql"
TEST_DB_ENV_VARIABLE = "BMLIBRARIAN_TEST_DB_ENV"
TEST_PMID = "990000099"


@pytest.fixture
def migrated() -> Iterator[psycopg.Connection]:
    """Connection to the opt-in development database with the migration applied twice."""
    env_file = os.environ.get(TEST_DB_ENV_VARIABLE)
    if not env_file:
        pytest.skip(f"{TEST_DB_ENV_VARIABLE} not set")
    cfg = dotenv_values(Path(env_file).expanduser())
    if is_protected_database(cfg.get("POSTGRES_DB")):
        pytest.fail(f"refusing to run migration tests against {cfg.get('POSTGRES_DB')!r}")
    conn = psycopg.connect(host=cfg.get("POSTGRES_HOST", "localhost"), port=cfg.get("POSTGRES_PORT", "5432"),
                           dbname=cfg["POSTGRES_DB"], user=cfg.get("POSTGRES_USER"),
                           password=cfg.get("POSTGRES_PASSWORD"))
    try:
        for migration in (MIGRATION_032, MIGRATION_033):
            sql = migration.read_text(encoding="utf-8")
            for _ in range(2):
                conn.execute(sql)
                conn.commit()
        yield conn
    finally:
        conn.rollback()
        conn.close()


def document_columns(conn: psycopg.Connection) -> set:
    """Column names of public.document."""
    return {r[0] for r in conn.execute("SELECT column_name FROM information_schema.columns "
                                       "WHERE table_schema = 'public' AND table_name = 'document'").fetchall()}


def test_withdrawals_use_baseline_columns_only(migrated: psycopg.Connection) -> None:
    """After 032 + 033, withdrawals live in withdrawn_date / withdrawn_reason only."""
    columns = document_columns(migrated)
    assert {"withdrawn_date", "withdrawn_reason"} <= columns
    assert "withdrawn" not in columns


def test_033_copies_first_revision_marks_before_dropping(migrated: psycopg.Connection) -> None:
    """Recreate the first-revision column with one mark, re-run 033, then roll everything back."""
    row = migrated.execute("SELECT id FROM document WHERE withdrawn_date IS NULL LIMIT 1").fetchone()
    if row is None:
        pytest.skip("development database has no documents")
    doc_id = row[0]
    try:
        migrated.execute("ALTER TABLE document ADD COLUMN withdrawn date")
        migrated.execute("UPDATE document SET withdrawn = DATE '2026-10-01', external_id = %s WHERE id = %s",
                         (TEST_PMID, doc_id))
        migrated.execute("INSERT INTO ingest.withdrawn_pmid (pmid, file, withdrawn) "
                         "VALUES (%s, 'test.xml.gz', DATE '2026-10-01') ON CONFLICT DO NOTHING", (TEST_PMID,))
        migrated.execute(MIGRATION_033.read_text(encoding="utf-8"))
        mark = migrated.execute("SELECT withdrawn_date::date::text, withdrawn_reason FROM document WHERE id = %s",
                                (doc_id,)).fetchone()
        assert mark == ("2026-10-01", "PubMed DeleteCitation")
        assert "withdrawn" not in document_columns(migrated)
    finally:
        migrated.rollback()


def test_withdrawn_pmid_table_exists_with_primary_key(migrated: psycopg.Connection) -> None:
    """ingest.withdrawn_pmid has the expected columns and a primary key on pmid."""
    cols = [r[0] for r in migrated.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = 'ingest' "
        "AND table_name = 'withdrawn_pmid' ORDER BY ordinal_position").fetchall()]
    assert cols == ["pmid", "file", "withdrawn"]
    pk = migrated.execute("SELECT count(*) FROM pg_index i JOIN pg_class c ON c.oid = i.indrelid "
                          "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'ingest' "
                          "AND c.relname = 'withdrawn_pmid' AND i.indisprimary").fetchone()[0]
    assert pk == 1
