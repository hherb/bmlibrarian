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
import contextlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence

SPIKE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SPIKE_DIR))
import bench_python as b  # noqa: E402
import pg_import_profile  # noqa: E402

RUST_BIN = SPIKE_DIR / "rust" / "target" / "release" / "pubmed-ingest-spike"
BUCKET_ROWS = 1_000_000
SEARCH_VECTOR = """ALTER TABLE spike_ingest.document ADD COLUMN IF NOT EXISTS search_vector tsvector
    GENERATED ALWAYS AS (setweight(to_tsvector('english'::regconfig, COALESCE(title, '')), 'A') ||
    setweight(to_tsvector('english'::regconfig, COALESCE(abstract, '')), 'B')) STORED"""
FTS_INDEX = "CREATE INDEX IF NOT EXISTS spike_doc_fts ON spike_ingest.document USING gin (search_vector)"
ID_SET = """SELECT count(*), count(DISTINCT external_id),
    md5(string_agg(external_id, ',' ORDER BY external_id)) FROM spike_ingest.document"""


def has_search_vector(conn) -> bool:
    """Whether the table currently has the generated search_vector column."""
    return conn.execute("SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE "
                        "table_schema = 'spike_ingest' AND table_name = 'document' AND "
                        "column_name = 'search_vector')").fetchone()[0]


def prepare(fts: bool, fresh: bool, fastupdate: Optional[str]) -> None:
    """Shape the table for the variant; optionally empty it (and the ledger).

    DDL runs only when something actually changes: even a no-op
    ``ALTER TABLE … IF NOT EXISTS`` takes an ACCESS EXCLUSIVE lock, which cancels
    a running autovacuum (that is what preceded the 52-min stall in run 0c).
    """
    with b.connect() as conn:
        conn.autocommit = True
        conn.execute((SPIKE_DIR / "sql" / "schema.sql").read_text(encoding="utf-8"))
        if fresh:
            conn.execute("TRUNCATE spike_ingest.document, spike_ingest.document_metadata, "
                         "spike_ingest.ingest_ledger RESTART IDENTITY")
        present = has_search_vector(conn)
        if fts and not present:
            conn.execute(SEARCH_VECTOR)
            conn.execute(FTS_INDEX)
        elif not fts and present:
            conn.execute("ALTER TABLE spike_ingest.document DROP COLUMN search_vector")
        if fts and fastupdate is not None:
            conn.execute(f"ALTER INDEX spike_ingest.spike_doc_fts SET (fastupdate = {fastupdate})")
        if fts:
            # Start every run with an empty GIN pending list, so variants are comparable.
            started = time.perf_counter()
            flushed = conn.execute("SELECT gin_clean_pending_list('spike_ingest.spike_doc_fts')").fetchone()[0]
            print(json.dumps({"pending_list_pages_flushed": flushed,
                              "flush_seconds": round(time.perf_counter() - started, 1)}))


def checkpoints() -> Dict[str, int]:
    """Cumulative checkpoint counters (requested = forced by WAL volume)."""
    with b.connect() as conn:
        timed, req = conn.execute("SELECT checkpoints_timed, checkpoints_req FROM pg_stat_bgwriter").fetchone()
    return {"timed": timed, "requested": req}


def per_file_stats(first: int, count: int) -> Dict[str, float]:
    """Distribution of per-file seconds for the files of this run (stall detection)."""
    names = [f"pubmed25n{n:04d}.xml.gz" for n in range(first, first + count)]
    with b.connect() as conn:
        secs = sorted(r[0] for r in conn.execute(
            "SELECT seconds FROM spike_ingest.ingest_ledger WHERE file = ANY(%s)", (names,)).fetchall())
    if not secs:
        return {}
    return {"files": len(secs), "median_s": secs[len(secs) // 2], "p95_s": secs[int(len(secs) * 0.95)],
            "max_s": secs[-1]}


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
    p.add_argument("--fastupdate", choices=("on", "off"), help="GIN fastupdate for spike_doc_fts")
    p.add_argument("--import-profile", action="store_true",
                   help="apply the server import profile for the run, then restore it")
    args = p.parse_args(argv)

    if args.mode == "curve":
        for row in curve():
            print(json.dumps(row))
        return 0

    if args.mode == "run":
        profile = pg_import_profile.import_profile() if args.import_profile else contextlib.nullcontext()
        with profile:
            prepare(args.fts, args.fresh, args.fastupdate)
            cp_before = checkpoints()
            started = time.perf_counter()
            subprocess.run(loader_cmd(args), check=True, env=loader_env())
            wall = time.perf_counter() - started
            cp_after = checkpoints()
            print(json.dumps({"variant": "fts" if args.fts else "no-fts", "fastupdate": args.fastupdate,
                              "import_profile": args.import_profile, "first": args.first,
                              "files": args.files, "wall_seconds": round(wall),
                              "checkpoints_timed": cp_after["timed"] - cp_before["timed"],
                              "checkpoints_requested": cp_after["requested"] - cp_before["requested"],
                              "per_file": per_file_stats(args.first, args.files), "size": table_size()}))
        return 0

    # killtest: reference run, then an interrupted + resumed run of the same files.
    prepare(args.fts, fresh=True, fastupdate=None)
    subprocess.run(loader_cmd(args), check=True, env=loader_env(), stdout=subprocess.DEVNULL)
    reference = id_set()
    prepare(args.fts, fresh=True, fastupdate=None)
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
