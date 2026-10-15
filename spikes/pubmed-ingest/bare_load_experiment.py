#!/usr/bin/env python3
"""
Phase 0a follow-up: how much of the load time is index/trigger maintenance?

1. Strip spike_ingest.document to a bare table (drop secondary indexes, the
   keyword trigger and the generated search_vector column; keep the unique key
   the merge needs).
2. Time the Rust R2 load into it.
3. Time rebuilding everything set-based: all_keywords in one UPDATE, re-add
   search_vector (a table rewrite), re-run schema.sql (indexes + trigger).
4. Checksum the result, to compare with the indexed-load checksum.

Usage (after run_all.sh, which leaves the table in its normal shape):
    uv run python spikes/pubmed-ingest/bare_load_experiment.py --first 1101 --files 8 --threads 8
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

SPIKE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SPIKE_DIR))
import bench_python as b  # noqa: E402

RUST_BIN = SPIKE_DIR / "rust" / "target" / "release" / "pubmed-ingest-spike"
SECONDARY_INDEXES = ("spike_doc_publication_date", "spike_doc_added_date", "spike_doc_updated_date",
                     "spike_doc_doi", "spike_doc_external_id", "spike_doc_fts",
                     "spike_doc_source_pubdate", "spike_doc_source_doi")
SEARCH_VECTOR = """ALTER TABLE spike_ingest.document ADD COLUMN search_vector tsvector GENERATED ALWAYS AS (
    setweight(to_tsvector('english'::regconfig, COALESCE(title, '')), 'A') ||
    setweight(to_tsvector('english'::regconfig, COALESCE(abstract, '')), 'B')) STORED"""
ALL_KEYWORDS = """UPDATE spike_ingest.document SET all_keywords = ARRAY(
    SELECT DISTINCT LOWER(e) FROM unnest(coalesce(keywords, '{}') || coalesce(augmented_keywords, '{}')
    || coalesce(mesh_terms, '{}')) e WHERE e IS NOT NULL)"""
CHECKSUM = """SELECT count(*), md5(string_agg(concat_ws('|', external_id, doi, title, abstract,
    authors::text, publication, publication_date::text, mesh_terms::text, keywords::text,
    (SELECT array_agg(k ORDER BY k) FROM unnest(all_keywords) k)::text), E'\\n' ORDER BY external_id))
    FROM spike_ingest.document"""


def timed(label: str, fn) -> float:
    """Run fn, print and return elapsed seconds."""
    started = time.perf_counter()
    fn()
    seconds = time.perf_counter() - started
    print(json.dumps({"step": label, "seconds": round(seconds, 2)}))
    return seconds


def main() -> int:
    """Run the experiment."""
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--first", type=int, default=1101)
    p.add_argument("--files", type=int, default=8)
    p.add_argument("--threads", type=int, default=8)
    args = p.parse_args()

    with b.connect() as conn:
        conn.autocommit = True
        conn.execute("TRUNCATE spike_ingest.document, spike_ingest.document_metadata, spike_ingest.ingest_ledger RESTART IDENTITY")
        conn.execute("DROP TRIGGER IF EXISTS spike_update_all_keywords ON spike_ingest.document")
        for idx in SECONDARY_INDEXES:
            conn.execute(f"DROP INDEX IF EXISTS spike_ingest.{idx}")
        conn.execute("ALTER TABLE spike_ingest.document DROP COLUMN IF EXISTS search_vector")

    # The Rust binary would re-apply schema.sql (recreating indexes + trigger), so
    # it is run with SPIKE_SKIP_SCHEMA=1.
    load = timed("r2-load-bare", lambda: subprocess.run(
        [str(RUST_BIN), "load", "--first", str(args.first), "--files", str(args.files),
         "--threads", str(args.threads)], check=True, env={**__import__("os").environ, "SPIKE_SKIP_SCHEMA": "1"}))

    with b.connect() as conn:
        conn.autocommit = True
        kw = timed("all_keywords-update", lambda: conn.execute(ALL_KEYWORDS))
        sv = timed("search_vector-add", lambda: conn.execute(SEARCH_VECTOR))
        idx = timed("indexes+trigger", lambda: conn.execute((SPIKE_DIR / "sql" / "schema.sql").read_text()))
        count, md5 = conn.execute(CHECKSUM).fetchone()
    print(json.dumps({"total_seconds": round(load + kw + sv + idx, 2), "docs": count, "doc_md5": md5}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
