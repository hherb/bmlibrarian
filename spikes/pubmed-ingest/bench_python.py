#!/usr/bin/env python3
"""
Phase 0a ingest spike — Python variants.

Reuses the production parser (``PubMedBulkImporter._parse_article``) unchanged,
then loads into ``spike_ingest`` in ``bmlibrarian_dev`` with one of:

- ``parse``  parse only (optionally ``--dump`` JSONL for the parity check)
- ``p1``     production write pattern: SELECT + INSERT/UPDATE per row, commit per
             100, then per-row transparency lookup + upsert on a second connection
- ``p2``     COPY into TEMP staging + set-based merge (sql/merge.sql), one process
- ``p3``     p2 in a process pool, one file per task

Throwaway measurement code: it connects with psycopg directly, because
``DatabaseManager`` would run the BMLibrarian migrations on the target database.
It refuses any database other than ``bmlibrarian_dev``.

Usage:
    uv run python spikes/pubmed-ingest/bench_python.py p2 --files 4 --reset
"""

import argparse
import gzip
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ProcessPoolExecutor
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

import psycopg
from dotenv import load_dotenv
from psycopg.types.json import Jsonb

SPIKE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SPIKE_DIR.parents[1] / "src"))
from bmlibrarian.importers.pubmed_bulk_importer import PubMedBulkImporter  # noqa: E402

ALLOWED_DATABASE = "bmlibrarian_dev"
DEFAULT_BASELINE_DIR = Path.home() / "knowledgebase" / "pubmed_data" / "baseline"
ENV_FILE = Path.home() / ".bmlibrarian" / ".env"
P1_BATCH_SIZE = 100  # production batch size (pubmed_bulk_importer.import_file)
SOURCE_ID = 1
STATEMENT_SEPARATOR = "-- ;;"
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

DOC_COLUMNS = ("ord", "external_id", "doi", "title", "abstract", "authors", "publication",
               "publication_date", "url", "mesh_terms", "keywords")
META_COLUMNS = ("ord", "external_id", "grants", "publication_types", "is_retracted",
                "author_affiliations")


def connect() -> psycopg.Connection:
    """Open a connection to the dev database, refusing anything else."""
    load_dotenv(ENV_FILE)
    dbname = os.environ.get("SPIKE_DB", ALLOWED_DATABASE)
    if dbname != ALLOWED_DATABASE:
        raise SystemExit(f"refusing to run against {dbname!r}; only {ALLOWED_DATABASE} is allowed")
    return psycopg.connect(dbname=dbname, host=os.environ.get("POSTGRES_HOST", "localhost"),
                           port=os.environ.get("POSTGRES_PORT", "5432"),
                           user=os.environ.get("POSTGRES_USER"),
                           password=os.environ.get("POSTGRES_PASSWORD"))


def sql_statements(name: str) -> List[str]:
    """Read a shared SQL file and split it into statements."""
    text = (SPIKE_DIR / "sql" / name).read_text(encoding="utf-8")
    return [s.strip() for s in text.split(STATEMENT_SEPARATOR) if s.strip()]


def parser() -> PubMedBulkImporter:
    """The production importer object without __init__ (which opens the production DB)."""
    return PubMedBulkImporter.__new__(PubMedBulkImporter)


def iter_articles(path: Path) -> Iterator[Dict[str, Any]]:
    """Yield parsed articles exactly as PubMedBulkImporter.import_file does."""
    imp = parser()
    with gzip.open(path, "rb") as fh:
        for _, elem in ET.iterparse(fh, events=("end",)):
            if elem.tag == "PubmedArticle":
                article = imp._parse_article(elem)
                if article:
                    yield article
                elem.clear()


def valid_date(value: Optional[str]) -> Optional[str]:
    """Return ``value`` if it is a real ISO date, else None (COPY needs valid dates)."""
    if not value or not DATE_PATTERN.match(value):
        return None
    try:
        date.fromisoformat(value)
    except ValueError:
        return None
    return value


def has_metadata(meta: Dict[str, Any]) -> bool:
    """Same filter as _store_transparency_metadata_batch."""
    return bool(meta.get("grants") or meta.get("publication_types") or meta.get("is_retracted")
                or meta.get("author_affiliations"))


def staging_rows(articles: Sequence[Dict[str, Any]]) -> Tuple[list, list]:
    """Convert parsed articles to staging rows (empty strings -> NULL, as production does)."""
    docs, metas = [], []
    for ord_, a in enumerate(articles):
        docs.append((ord_, a["pmid"], a.get("doi") or None, a["title"], a.get("abstract") or None,
                     a.get("authors", []), a.get("publication") or None,
                     valid_date(a.get("publication_date")), a.get("url"),
                     a.get("mesh_terms", []), a.get("keywords", [])))
        meta = a.get("transparency_metadata") or {}
        if has_metadata(meta):
            metas.append((ord_, a["pmid"],
                          Jsonb(meta["grants"]) if meta.get("grants") else None,
                          meta.get("publication_types"), bool(meta.get("is_retracted", False)),
                          Jsonb(meta["author_affiliations"]) if meta.get("author_affiliations") else None))
    return docs, metas


def load_copy(conn: psycopg.Connection, articles: Sequence[Dict[str, Any]]) -> None:
    """COPY one file's articles into staging and merge, in one transaction."""
    docs, metas = staging_rows(articles)
    with conn.cursor() as cur:
        for stmt in sql_statements("staging.sql"):
            cur.execute(stmt)
        with cur.copy(f"COPY stage_document ({', '.join(DOC_COLUMNS)}) FROM STDIN") as cp:
            for row in docs:
                cp.write_row(row)
        with cur.copy(f"COPY stage_metadata ({', '.join(META_COLUMNS)}) FROM STDIN") as cp:
            for row in metas:
                cp.write_row(row)
        for stmt in sql_statements("merge.sql"):
            cur.execute(stmt)
    conn.commit()


def load_p1(conn: psycopg.Connection, meta_conn: psycopg.Connection,
            articles: Sequence[Dict[str, Any]]) -> None:
    """Production write pattern (pubmed_bulk_importer._store_article_batch), batch by batch."""
    for start in range(0, len(articles), P1_BATCH_SIZE):
        batch = articles[start:start + P1_BATCH_SIZE]
        with conn.cursor() as cur:
            for a in batch:
                cur.execute("SELECT id FROM spike_ingest.document WHERE source_id = %s AND external_id = %s",
                            (SOURCE_ID, a["pmid"]))
                existing = cur.fetchone()
                values = (a.get("doi") or None, a["title"], a.get("abstract") or None,
                          a.get("authors", []), a.get("publication") or None,
                          valid_date(a.get("publication_date")))
                if existing:
                    cur.execute("""UPDATE spike_ingest.document SET doi = COALESCE(%s, doi), title = %s,
                        abstract = COALESCE(%s, abstract), authors = %s,
                        publication = COALESCE(%s, publication),
                        publication_date = COALESCE(%s, publication_date),
                        mesh_terms = %s, keywords = %s, updated_date = CURRENT_TIMESTAMP WHERE id = %s""",
                                values + (a.get("mesh_terms", []), a.get("keywords", []), existing[0]))
                else:
                    cur.execute("""INSERT INTO spike_ingest.document (source_id, external_id, doi, title,
                        abstract, authors, publication, publication_date, url, mesh_terms, keywords)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                                (SOURCE_ID, a["pmid"]) + values
                                + (a.get("url"), a.get("mesh_terms", []), a.get("keywords", [])))
        conn.commit()
        with meta_conn.cursor() as cur:
            for a in batch:
                meta = a.get("transparency_metadata") or {}
                if not has_metadata(meta):
                    continue
                cur.execute("SELECT id FROM spike_ingest.document WHERE source_id = %s AND external_id = %s",
                            (SOURCE_ID, a["pmid"]))
                row = cur.fetchone()
                if not row:
                    continue
                cur.execute("""INSERT INTO spike_ingest.document_metadata (document_id, grants,
                    publication_types, is_retracted, author_affiliations, source)
                    VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (document_id) DO UPDATE SET
                    grants = COALESCE(EXCLUDED.grants, spike_ingest.document_metadata.grants),
                    publication_types = COALESCE(EXCLUDED.publication_types,
                                                 spike_ingest.document_metadata.publication_types),
                    is_retracted = EXCLUDED.is_retracted OR spike_ingest.document_metadata.is_retracted,
                    author_affiliations = COALESCE(EXCLUDED.author_affiliations,
                                                   spike_ingest.document_metadata.author_affiliations),
                    imported_at = NOW()""",
                            (row[0], json.dumps(meta["grants"]) if meta.get("grants") else None,
                             meta.get("publication_types"), bool(meta.get("is_retracted", False)),
                             json.dumps(meta["author_affiliations"]) if meta.get("author_affiliations")
                             else None, "pubmed_bulk"))
        meta_conn.commit()


def process_file_copy(path: str) -> int:
    """Process-pool task: parse one file and COPY+merge it on a private connection."""
    articles = list(iter_articles(Path(path)))
    with connect() as conn:
        load_copy(conn, articles)
    return len(articles)


def setup_schema(reset: bool) -> None:
    """Apply sql/schema.sql (idempotent); optionally truncate the spike tables."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute((SPIKE_DIR / "sql" / "schema.sql").read_text(encoding="utf-8"))
        if reset:
            cur.execute("TRUNCATE spike_ingest.document, spike_ingest.document_metadata, spike_ingest.ingest_ledger RESTART IDENTITY")
        conn.commit()


def pick_files(baseline_dir: Path, first: int, count: int) -> List[Path]:
    """Return ``count`` baseline files starting at file number ``first``."""
    files = sorted(baseline_dir.glob("pubmed*n*.xml.gz"))
    chosen = files[first - 1:first - 1 + count]
    if len(chosen) < count:
        raise SystemExit(f"only {len(chosen)} files available from #{first} in {baseline_dir}")
    return chosen


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point."""
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("variant", choices=("parse", "p1", "p2", "p3"))
    p.add_argument("--baseline-dir", type=Path, default=DEFAULT_BASELINE_DIR)
    p.add_argument("--first", type=int, default=1, help="first file number (1-based)")
    p.add_argument("--files", type=int, default=4)
    p.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    p.add_argument("--reset", action="store_true", help="truncate spike tables first")
    p.add_argument("--dump", type=Path, help="parse: write parsed articles as JSONL")
    args = p.parse_args(argv)

    files = pick_files(args.baseline_dir, args.first, args.files)
    if args.variant != "parse":
        setup_schema(args.reset)

    started = time.perf_counter()
    total = 0
    if args.variant == "parse":
        out = open(args.dump, "w", encoding="utf-8") if args.dump else None
        for f in files:
            for a in iter_articles(f):
                total += 1
                if out:
                    out.write(json.dumps(a, ensure_ascii=False, sort_keys=True) + "\n")
        if out:
            out.close()
    elif args.variant == "p1":
        with connect() as conn, connect() as meta_conn:
            for f in files:
                articles = list(iter_articles(f))
                load_p1(conn, meta_conn, articles)
                total += len(articles)
    elif args.variant == "p2":
        with connect() as conn:
            for f in files:
                articles = list(iter_articles(f))
                load_copy(conn, articles)
                total += len(articles)
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            total = sum(pool.map(process_file_copy, [str(f) for f in files]))
    seconds = time.perf_counter() - started
    print(json.dumps({"variant": f"python-{args.variant}", "files": len(files),
                      "workers": args.workers if args.variant == "p3" else 1,
                      "articles": total, "seconds": round(seconds, 2),
                      "articles_per_s": round(total / seconds, 1)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
