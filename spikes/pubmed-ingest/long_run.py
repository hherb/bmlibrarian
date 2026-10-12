#!/usr/bin/env python3
"""
Phase 0c: does incremental, resumable ingest stay fast past a few million rows?

Loads baseline files in production order with the Rust loader in ``--resume``
mode (each file is one transaction that also writes its ``ingest_ledger`` row),
then reports throughput per million rows loaded, from the ledger timestamps.

Table variants:
    --fts     production shape (generated search_vector + GIN), as today
    (default) target shape: no Postgres FTS (BM25 moves to tantivy)

Modes:
    run       load --files N from --first (resumes if the ledger has entries)
    curve     print the throughput curve from the ledger only
    killtest  load, SIGKILL the loader after --kill-after seconds, resume, and
              verify nothing was lost or duplicated

Usage:
    uv run python spikes/pubmed-ingest/long_run.py run --files 334 --fresh
    uv run python spikes/pubmed-ingest/long_run.py killtest --files 40 --kill-after 20
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional, Sequence

SPIKE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SPIKE_DIR))
import bench_python as b  # noqa: E402

RUST_BIN = SPIKE_DIR / "rust" / "target" / "release" / "pubmed-ingest-spike"
BUCKET_ROWS = 1_000_000
SEARCH_VECTOR = """ALTER TABLE spike_ingest.document ADD COLUMN IF NOT EXISTS search_vector tsvector
    GENERATED ALWAYS AS (setweight(to_tsvector('english'::regconfig, COALESCE(title, '')), 'A') ||
    setweight(to_tsvector('english'::regconfig, COALESCE(abstract, '')), 'B')) STORED"""
FTS_INDEX = "CREATE INDEX IF NOT EXISTS spike_doc_fts ON spike_ingest.document USING gin (search_vector)"
ID_SET = """SELECT count(*), count(DISTINCT external_id),
    md5(string_agg(external_id, ',' ORDER BY external_id)) FROM spike_ingest.document"""


def prepare(fts: bool, fresh: bool) -> None:
    """Shape the table for the variant; optionally empty it (and the ledger)."""
    with b.connect() as conn:
        conn.autocommit = True
        conn.execute((SPIKE_DIR / "sql" / "schema.sql").read_text(encoding="utf-8"))
        if fresh:
            conn.execute("TRUNCATE spike_ingest.document, spike_ingest.document_metadata, "
                         "spike_ingest.ingest_ledger RESTART IDENTITY")
        if fts:
            conn.execute(SEARCH_VECTOR)
            conn.execute(FTS_INDEX)
        else:
            conn.execute("ALTER TABLE spike_ingest.document DROP COLUMN IF EXISTS search_vector")


def loader_cmd(args: argparse.Namespace) -> List[str]:
    """The Rust loader in resume mode; schema is prepared here, not by the loader."""
    return [str(RUST_BIN), "load", "--resume", "--first", str(args.first), "--files", str(args.files),
            "--threads", str(args.threads)]


def loader_env() -> dict:
    """Environment telling the loader to leave the prepared table shape alone."""
    return {**os.environ, "SPIKE_SKIP_SCHEMA": "1"}


def curve() -> List[dict]:
    """Throughput per BUCKET_ROWS committed rows, from ledger commit timestamps."""
    with b.connect() as conn:
        rows = conn.execute("SELECT articles, extract(epoch FROM finished_at) FROM "
                            "spike_ingest.ingest_ledger ORDER BY finished_at").fetchall()
    out, cum, bucket_start_rows, bucket_start_t = [], 0, 0, None
    first_t = rows[0][1] if rows else None
    for articles, t in rows:
        if bucket_start_t is None:
            bucket_start_t = first_t
        cum += articles
        if cum - bucket_start_rows >= BUCKET_ROWS:
            secs = float(t) - float(bucket_start_t)
            out.append({"rows_from": bucket_start_rows, "rows_to": cum,
                        "articles_per_s": round((cum - bucket_start_rows) / max(secs, 1e-9))})
            bucket_start_rows, bucket_start_t = cum, t
    if rows:
        total = float(rows[-1][1]) - float(first_t)
        out.append({"total_rows": cum, "files": len(rows), "wall_seconds_first_to_last_commit": round(total),
                    "overall_articles_per_s": round(cum / max(total, 1e-9))})
    return out


def table_size() -> str:
    """Pretty size of the spike tables (data + indexes)."""
    with b.connect() as conn:
        return conn.execute("SELECT pg_size_pretty(pg_total_relation_size('spike_ingest.document') + "
                            "pg_total_relation_size('spike_ingest.document_metadata'))").fetchone()[0]


def id_set() -> tuple:
    """(rows, distinct PMIDs, md5 of the sorted PMID list)."""
    with b.connect() as conn:
        return tuple(conn.execute(ID_SET).fetchone())


def ledger_files() -> int:
    """Number of committed files."""
    with b.connect() as conn:
        return conn.execute("SELECT count(*) FROM spike_ingest.ingest_ledger").fetchone()[0]


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point."""
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("mode", choices=("run", "curve", "killtest"))
    p.add_argument("--first", type=int, default=1)
    p.add_argument("--files", type=int, default=334)
    p.add_argument("--threads", type=int, default=8)
    p.add_argument("--fts", action="store_true", help="production shape with search_vector + GIN")
    p.add_argument("--fresh", action="store_true", help="empty table and ledger first")
    p.add_argument("--kill-after", type=float, default=20.0)
    args = p.parse_args(argv)

    if args.mode == "curve":
        for row in curve():
            print(json.dumps(row))
        return 0

    if args.mode == "run":
        prepare(args.fts, args.fresh)
        started = time.perf_counter()
        subprocess.run(loader_cmd(args), check=True, env=loader_env())
        for row in curve():
            print(json.dumps(row))
        print(json.dumps({"variant": "fts" if args.fts else "no-fts", "size": table_size(),
                          "wall_seconds": round(time.perf_counter() - started)}))
        return 0

    # killtest: reference run, then an interrupted + resumed run of the same files.
    prepare(args.fts, fresh=True)
    subprocess.run(loader_cmd(args), check=True, env=loader_env(), stdout=subprocess.DEVNULL)
    reference = id_set()
    prepare(args.fts, fresh=True)
    proc = subprocess.Popen(loader_cmd(args), env=loader_env(), stdout=subprocess.DEVNULL)
    time.sleep(args.kill_after)
    proc.send_signal(signal.SIGKILL)
    proc.wait()
    committed_at_kill = ledger_files()
    rows_at_kill = id_set()
    subprocess.run(loader_cmd(args), check=True, env=loader_env(), stdout=subprocess.DEVNULL)
    resumed = id_set()
    result = {"files": args.files, "committed_files_at_kill": committed_at_kill,
              "rows_at_kill": rows_at_kill[0], "reference": reference, "after_resume": resumed,
              "no_loss_no_duplicates": resumed == reference and resumed[0] == resumed[1],
              "ledger_files_after_resume": ledger_files()}
    print(json.dumps(result))
    return 0 if result["no_loss_no_duplicates"] else 1


if __name__ == "__main__":
    sys.exit(main())
