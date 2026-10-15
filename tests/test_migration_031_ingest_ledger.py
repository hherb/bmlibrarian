"""
Integration tests for migrations/031_ingest_ledger_and_revisions.sql.

Opt-in: set BMLIBRARIAN_TEST_DB_ENV to an env file for a *development* database
that already has the BMLibrarian schema (e.g. ~/.bmlibrarian/.env_pg18_dev).
The tests refuse to run against any database the test guard protects (production).
Data written by a test is rolled back; the migration itself is applied (twice,
to prove idempotency) and stays applied, as migrations do.
"""

import os
from pathlib import Path
from typing import Iterator

import psycopg
import pytest
from dotenv import dotenv_values

from bmlibrarian.db_test_guard import is_protected_database

pytestmark = pytest.mark.requires_database

MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "031_ingest_ledger_and_revisions.sql"
TEST_DB_ENV_VARIABLE = "BMLIBRARIAN_TEST_DB_ENV"


@pytest.fixture
def dev_conn() -> Iterator[psycopg.Connection]:
    """Connection to the opt-in development database (skips if not configured)."""
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
        yield conn
    finally:
        conn.rollback()
        conn.close()


@pytest.fixture
def migrated(dev_conn: psycopg.Connection) -> psycopg.Connection:
    """Apply the migration twice (idempotency) and commit it."""
    sql = MIGRATION.read_text(encoding="utf-8")
    for _ in range(2):
        dev_conn.execute(sql)
        dev_conn.commit()
    return dev_conn


def test_document_has_date_revised(migrated: psycopg.Connection) -> None:
    row = migrated.execute("SELECT data_type FROM information_schema.columns WHERE table_schema = 'public' "
                           "AND table_name = 'document' AND column_name = 'date_revised'").fetchone()
    assert row == ("date",)


def test_ingest_ledger_keyed_by_source_and_file(migrated: psycopg.Connection) -> None:
    cols = migrated.execute("""SELECT a.attname FROM pg_index i JOIN pg_attribute a
        ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
        WHERE i.indrelid = 'ingest.ledger'::regclass AND i.indisprimary ORDER BY a.attname""").fetchall()
    assert [c[0] for c in cols] == ["file", "source"]


def test_fts_gin_has_fastupdate_off(migrated: psycopg.Connection) -> None:
    opts = migrated.execute("SELECT reloptions FROM pg_class WHERE oid = 'public.idx_document_fts'::regclass").fetchone()[0]
    assert "fastupdate=off" in (opts or [])


def test_all_keywords_is_sorted_and_deduplicated(migrated: psycopg.Connection) -> None:
    # A throwaway source row (rolled back with the rest of the test's data).
    source_id = migrated.execute(
        "INSERT INTO sources (id, name) SELECT coalesce(max(id), 0) + 1, 'migration-031-test' FROM sources "
        "RETURNING id").fetchone()[0]
    all_kw = migrated.execute(
        "INSERT INTO document (source_id, external_id, title, keywords, mesh_terms) "
        "VALUES (%s, 'migration-031-test', 't', ARRAY['zeta','Alpha','alpha'], ARRAY['Mu']) RETURNING all_keywords",
        (source_id,)).fetchone()[0]
    assert all_kw == ["alpha", "mu", "zeta"]
