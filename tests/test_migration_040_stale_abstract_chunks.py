"""
Integration tests for migration 040: an abstract change drops the document's
abstract chunks and their embeddings (#475).

Opt-in: set BMLIBRARIAN_TEST_DB_ENV to an env file for a *development* database
with the BMLibrarian schema (e.g. ~/.bmlibrarian/.env_pg18_dev). Refuses any
database the test guard protects. The migration is applied twice to prove
idempotency and stays applied, as migrations do; the data tests run in a
transaction that is rolled back.
"""

import os
from pathlib import Path
from typing import Iterator, Tuple

import psycopg
import pytest
from dotenv import dotenv_values

from bmlibrarian.db_test_guard import is_protected_database
from bmlibrarian.embeddings.document_embedder import _get_or_insert_id

pytestmark = pytest.mark.requires_database

MIGRATION_040 = Path(__file__).resolve().parents[1] / "migrations" / "040_drop_stale_abstract_chunks.sql"
TEST_DB_ENV_VARIABLE = "BMLIBRARIAN_TEST_DB_ENV"
EMBEDDING_DIMENSION = 1024


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
        sql = MIGRATION_040.read_text(encoding="utf-8")
        for _ in range(2):
            conn.execute(sql)
            conn.commit()
        yield conn
    finally:
        conn.rollback()
        conn.close()


def _chunk_with_embedding(conn: psycopg.Connection, doc_id: int, chunk_no: int, chunktype: str) -> int:
    """Insert a chunk of ``chunktype`` for ``doc_id`` with one emb_1024 row; return the chunk ID."""
    cur = conn.cursor()
    chunktype_id = _get_or_insert_id(cur, "chunktypes", "chunktype", {"chunktype": chunktype})
    strategy_id = _get_or_insert_id(cur, "chunking_strategies", "strategy_name", {"strategy_name": "test_040"})
    chunk_id = conn.execute("INSERT INTO chunks (document_id, chunking_strategy_id, chunktype_id, text, chunk_no) "
                            "VALUES (%s, %s, %s, 'old text', %s) RETURNING id",
                            (doc_id, strategy_id, chunktype_id, chunk_no)).fetchone()[0]
    vector = "[" + ",".join(["0.1"] * EMBEDDING_DIMENSION) + "]"
    conn.execute("INSERT INTO emb_1024 (chunk_id, model_id, embedding) VALUES (%s, NULL, %s)", (chunk_id, vector))
    return chunk_id


def _counts(conn: psycopg.Connection, chunk_id: int) -> Tuple[int, int]:
    """Return (chunk rows, embedding rows) for ``chunk_id``."""
    chunks = conn.execute("SELECT count(*) FROM chunks WHERE id = %s", (chunk_id,)).fetchone()[0]
    embeddings = conn.execute("SELECT count(*) FROM embedding_base WHERE chunk_id = %s", (chunk_id,)).fetchone()[0]
    return chunks, embeddings


@pytest.fixture
def document(migrated: psycopg.Connection) -> int:
    """ID of a development-database document to modify inside the test's transaction."""
    row = migrated.execute("SELECT id FROM document WHERE abstract IS NOT NULL LIMIT 1").fetchone()
    if row is None:
        pytest.skip("development database has no documents")
    return row[0]


def test_trigger_is_installed_once(migrated: psycopg.Connection) -> None:
    """Running 040 twice leaves one trigger on public.document."""
    count = migrated.execute("SELECT count(*) FROM pg_trigger WHERE tgrelid = 'public.document'::regclass "
                             "AND tgname = 'trg_drop_stale_abstract_chunks'").fetchone()[0]
    assert count == 1


def test_get_or_insert_id_works_without_unique_constraint(migrated: psycopg.Connection) -> None:
    """The embedder's lookup-table setup runs on the real schema (no unique key) and reuses the row."""
    cur = migrated.cursor()
    first = _get_or_insert_id(cur, "chunktypes", "chunktype", {"chunktype": "test_040_lookup"})
    assert _get_or_insert_id(cur, "chunktypes", "chunktype", {"chunktype": "test_040_lookup"}) == first
    migrated.rollback()


def test_abstract_change_drops_abstract_chunks_and_embeddings(migrated: psycopg.Connection, document: int) -> None:
    """A changed abstract removes its chunks and embeddings; other chunk types stay."""
    abstract_chunk = _chunk_with_embedding(migrated, document, 900, "abstract")
    other_chunk = _chunk_with_embedding(migrated, document, 901, "test_040_other")

    migrated.execute("UPDATE document SET abstract = abstract || ' (revised)' WHERE id = %s", (document,))

    assert _counts(migrated, abstract_chunk) == (0, 0)
    assert _counts(migrated, other_chunk) == (1, 1)
    migrated.rollback()


def test_unchanged_abstract_keeps_chunks(migrated: psycopg.Connection, document: int) -> None:
    """An UPDATE that writes the same abstract (an upsert) leaves the chunks alone."""
    chunk = _chunk_with_embedding(migrated, document, 900, "abstract")

    migrated.execute("UPDATE document SET abstract = abstract WHERE id = %s", (document,))

    assert _counts(migrated, chunk) == (1, 1)
    migrated.rollback()


def test_evaluated_chunk_keeps_its_row_but_loses_embeddings(migrated: psycopg.Connection, document: int) -> None:
    """A chunk an evaluation references is kept (no cascade) without its stale embedding."""
    chunk = _chunk_with_embedding(migrated, document, 900, "abstract")
    question = migrated.execute("INSERT INTO research_questions (question) VALUES ('test 040') "
                                "RETURNING id").fetchone()[0]
    evaluator = migrated.execute("INSERT INTO evaluators (name) VALUES ('test 040') RETURNING id").fetchone()[0]
    migrated.execute("INSERT INTO evaluations (research_question_id, chunk_id, evaluator_id, document_id, rating, "
                     "confidence_level) VALUES (%s, %s, %s, %s, 3, 0.5)", (question, chunk, evaluator, document))

    migrated.execute("UPDATE document SET abstract = abstract || ' (revised)' WHERE id = %s", (document,))

    assert _counts(migrated, chunk) == (1, 0)
    migrated.rollback()
