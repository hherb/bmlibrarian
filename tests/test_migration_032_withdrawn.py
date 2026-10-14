"""
Integration tests for migrations/032_withdrawn_documents.sql.

Opt-in: set BMLIBRARIAN_TEST_DB_ENV to an env file for a *development* database
with the BMLibrarian schema (e.g. ~/.bmlibrarian/.env_pg18_dev). Refuses the
production database `knowledgebase`. The migration is applied twice to prove
idempotency and stays applied, as migrations do.
"""

import os
from pathlib import Path
from typing import Iterator

import psycopg
import pytest
from dotenv import dotenv_values

pytestmark = pytest.mark.requires_database

MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "032_withdrawn_documents.sql"
TEST_DB_ENV_VARIABLE = "BMLIBRARIAN_TEST_DB_ENV"
PRODUCTION_DATABASE = "knowledgebase"


@pytest.fixture
def migrated() -> Iterator[psycopg.Connection]:
    """Connection to the opt-in development database with the migration applied twice."""
    env_file = os.environ.get(TEST_DB_ENV_VARIABLE)
    if not env_file:
        pytest.skip(f"{TEST_DB_ENV_VARIABLE} not set")
    cfg = dotenv_values(Path(env_file).expanduser())
    if cfg.get("POSTGRES_DB") in (None, PRODUCTION_DATABASE):
        pytest.fail(f"refusing to run migration tests against {cfg.get('POSTGRES_DB')!r}")
    conn = psycopg.connect(host=cfg.get("POSTGRES_HOST", "localhost"), port=cfg.get("POSTGRES_PORT", "5432"),
                           dbname=cfg["POSTGRES_DB"], user=cfg.get("POSTGRES_USER"),
                           password=cfg.get("POSTGRES_PASSWORD"))
    try:
        sql = MIGRATION.read_text(encoding="utf-8")
        for _ in range(2):
            conn.execute(sql)
            conn.commit()
        yield conn
    finally:
        conn.rollback()
        conn.close()


def test_document_has_withdrawn_date(migrated: psycopg.Connection) -> None:
    row = migrated.execute("SELECT data_type FROM information_schema.columns WHERE table_schema = 'public' "
                           "AND table_name = 'document' AND column_name = 'withdrawn'").fetchone()
    assert row == ("date",)


def test_withdrawn_pmid_table_exists_with_primary_key(migrated: psycopg.Connection) -> None:
    cols = [r[0] for r in migrated.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = 'ingest' "
        "AND table_name = 'withdrawn_pmid' ORDER BY ordinal_position").fetchall()]
    assert cols == ["pmid", "file", "withdrawn"]
    pk = migrated.execute("SELECT count(*) FROM pg_index i JOIN pg_class c ON c.oid = i.indrelid "
                          "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'ingest' "
                          "AND c.relname = 'withdrawn_pmid' AND i.indisprimary").fetchone()[0]
    assert pk == 1
