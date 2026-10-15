#!/usr/bin/env python3
"""
Phase 0d: resumable vector indexing with 256-d arctic vectors in pgvector.

Can vector indexing be done in bounded, restartable units (one HNSW index per
partition of ~1 M vectors) instead of one multi-week build, and what do the
partitions cost in recall and latency?

Subcommands (run in order; each is restartable on its own):
    extract   read N production chunk vectors (by chunk_id) from `knowledgebase` (read-only),
              sliced to 256 dims in SQL, L2-renormalised -> results/vectors.npy
    queries   embed PubMedQA questions with the arctic query prompt, 256 d
    load      COPY into bmlibrarian_dev: spike_vec.emb (vector) and spike_vec.emb_half
              (halfvec), both partitioned by id range
    build     CREATE INDEX hnsw on each partition (vector and halfvec), timed,
              plus one unpartitioned build over everything for comparison
    insert    insert extra rows into an already-indexed partition, timed
    recall    recall@10/@100 and latency vs exact numpy search, per ef_search

Writes only to schema `spike_vec` in bmlibrarian_dev. Reads `knowledgebase`
in a READ ONLY transaction.

Usage:
    uv run python spikes/vector-partitions/vector_bench.py extract --n 5000000
"""

import argparse
import io
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import psycopg
from dotenv import load_dotenv

SPIKE_DIR = Path(__file__).resolve().parent
RESULTS = SPIKE_DIR / "results"
VECTORS = RESULTS / "vectors.npy"
IDS = RESULTS / "ids.npy"
QUERIES = RESULTS / "queries.npy"
TIMINGS = RESULTS / "timings.jsonl"
ENV_FILE = Path.home() / ".bmlibrarian" / ".env"
SOURCE_DB = "knowledgebase"
TARGET_DB = "bmlibrarian_dev"
PRODUCTION_MODEL_ID = 1          # emb_1024.model_id of snowflake-arctic-embed2
EXTRACT_TIMEOUT = "2h"           # guard for the read-only production scan
DIM = 256
PARTITION_ROWS = 1_000_000
INSERT_EXTRA = 200_000
HNSW_M = 16
HNSW_EF_CONSTRUCTION = 64
EF_SEARCH = (40, 100, 200, 400)
TOP_K = (10, 100)
COPY_BATCH = 50_000
QUERY_PROMPT = "query: "
HF_MODEL = "Snowflake/snowflake-arctic-embed-l-v2.0"
DEFAULT_QUERY_FILE = (Path.home() / ".cache" / "bmlibrarian" / "embedding_benchmark" / "bmlibrarian_eval"
                      / "pubmedqa_source" / "eval" / "queries.jsonl")
DEFAULT_QUERIES = 300


def connect(dbname: str, read_only: bool = False) -> psycopg.Connection:
    """Connect; the only writable database is bmlibrarian_dev."""
    load_dotenv(ENV_FILE)
    if dbname not in (SOURCE_DB, TARGET_DB):
        raise SystemExit(f"unexpected database {dbname!r}")
    conn = psycopg.connect(dbname=dbname, host=os.environ.get("POSTGRES_HOST", "localhost"),
                           port=os.environ.get("POSTGRES_PORT", "5432"),
                           user=os.environ.get("POSTGRES_USER"), password=os.environ.get("POSTGRES_PASSWORD"))
    if dbname == SOURCE_DB or read_only:
        conn.read_only = True   # every transaction on knowledgebase is READ ONLY
    return conn


def record(row: Dict) -> None:
    """Append a timing row and echo it."""
    RESULTS.mkdir(parents=True, exist_ok=True)
    with open(TIMINGS, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    print(json.dumps(row), flush=True)


def normalise(m: np.ndarray) -> np.ndarray:
    """Row-wise L2 normalisation."""
    return (m / np.maximum(np.linalg.norm(m, axis=1, keepdims=True), 1e-12)).astype(np.float32)


def vec_text(row: np.ndarray) -> str:
    """pgvector text literal (used for query vectors only)."""
    return "[" + ",".join(f"{x:.7g}" for x in row) + "]"


COPY_HEADER = b"PGCOPY\n\xff\r\n\x00" + (0).to_bytes(4, "big") + (0).to_bytes(4, "big")
COPY_TRAILER = (-1).to_bytes(2, "big", signed=True)


def binary_copy_rows(rn: np.ndarray, src: np.ndarray, vecs: np.ndarray, half: bool) -> bytes:
    """Rows (rn bigint, src_id bigint, embedding vector|halfvec) in COPY BINARY format.

    pgvector's binary form is int16 dim, int16 unused, then dim big-endian floats
    (float4 for vector, float2 for halfvec). Built with numpy, not per value.
    """
    elem = ">f2" if half else ">f4"
    esize = 2 if half else 4
    dt = np.dtype([("nf", ">i2"), ("l1", ">i4"), ("rn", ">i8"), ("l2", ">i4"), ("src", ">i8"),
                   ("l3", ">i4"), ("dim", ">i2"), ("unused", ">i2"), ("v", elem, (DIM,))])
    buf = np.zeros(len(rn), dtype=dt)
    buf["nf"], buf["l1"], buf["l2"] = 3, 8, 8
    buf["l3"] = 4 + DIM * esize
    buf["rn"], buf["src"], buf["dim"] = rn, src, DIM
    buf["v"] = vecs.astype(np.float16 if half else np.float32)
    return buf.tobytes()


def copy_binary(conn: psycopg.Connection, table: str, rn: np.ndarray, src: np.ndarray,
                vecs: np.ndarray, half: bool) -> None:
    """Stream rows into ``table`` with COPY BINARY, in batches, one transaction per call."""
    with conn.transaction(), conn.cursor() as cur, \
            cur.copy(f"COPY {table} (rn, src_id, embedding) FROM STDIN (FORMAT BINARY)") as cp:
        cp.write(COPY_HEADER)
        for s in range(0, len(rn), COPY_BATCH):
            e = s + COPY_BATCH
            cp.write(binary_copy_rows(rn[s:e], src[s:e], vecs[s:e], half))
        cp.write(COPY_TRAILER)


def cmd_extract(args: argparse.Namespace) -> None:
    """Stream the first N production vectors (by id), sliced to 256 dims server-side."""
    started = time.perf_counter()
    ids = np.empty(args.n, dtype=np.int64)
    out = np.empty((args.n, DIM), dtype=np.float32)
    got = 0
    with connect(SOURCE_DB) as conn, conn.cursor() as cur:
        # ORDER BY chunk_id, not id: emb_1024 has no index on id, so ORDER BY id
        # sorts the whole 484 GB table. chunk_id is indexed (checked with EXPLAIN).
        cur.execute(f"SET statement_timeout = '{EXTRACT_TIMEOUT}'")
        sql = (f"COPY (SELECT chunk_id, ((embedding::real[])[1:{DIM}])::text FROM emb_1024 "
               f"WHERE model_id = {PRODUCTION_MODEL_ID} ORDER BY chunk_id LIMIT {args.n}) TO STDOUT")
        with cur.copy(sql) as cp:
            for rid, arr in cp.rows():
                ids[got] = int(rid)
                out[got] = np.fromstring(arr[1:-1], sep=",", dtype=np.float32)
                got += 1
                if got % 500_000 == 0:
                    print(f"  {got:,} vectors", file=sys.stderr, flush=True)
    ids, out = ids[:got], normalise(out[:got])
    RESULTS.mkdir(parents=True, exist_ok=True)
    np.save(IDS, ids)
    np.save(VECTORS, out)
    record({"step": "extract", "vectors": got, "seconds": round(time.perf_counter() - started, 1)})


def cmd_queries(args: argparse.Namespace) -> None:
    """Real questions, embedded the way production embeds queries, truncated to 256 d."""
    import torch
    from sentence_transformers import SentenceTransformer

    with open(args.query_file, encoding="utf-8") as fh:
        texts = [json.loads(line)["text"] for line in fh][:args.n]
    model = SentenceTransformer(HF_MODEL, device="mps" if torch.backends.mps.is_available() else "cpu")
    emb = model.encode([QUERY_PROMPT + t for t in texts], batch_size=32, convert_to_numpy=True)
    np.save(QUERIES, normalise(emb[:, :DIM]))
    record({"step": "queries", "queries": len(texts)})


def partition_ddl(table: str, typ: str, n_rows: int) -> List[str]:
    """Partitioned table by row number, PARTITION_ROWS per partition."""
    stmts = [f"CREATE TABLE IF NOT EXISTS spike_vec.{table} (rn bigint NOT NULL, src_id bigint NOT NULL, "
             f"embedding {typ}({DIM}) NOT NULL) PARTITION BY RANGE (rn)"]
    for p in range((n_rows + PARTITION_ROWS - 1) // PARTITION_ROWS):
        lo, hi = p * PARTITION_ROWS, (p + 1) * PARTITION_ROWS
        stmts.append(f"CREATE TABLE IF NOT EXISTS spike_vec.{table}_p{p} PARTITION OF spike_vec.{table} "
                     f"FOR VALUES FROM ({lo}) TO ({hi})")
    return stmts


def cmd_load(args: argparse.Namespace) -> None:
    """COPY the vectors into a vector and a halfvec partitioned table (idempotent per table)."""
    vecs, ids = np.load(VECTORS), np.load(IDS)
    with connect(TARGET_DB) as conn:
        conn.autocommit = True
        conn.execute("ALTER EXTENSION vector UPDATE")
        version = conn.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'").fetchone()[0]
        conn.execute("CREATE SCHEMA IF NOT EXISTS spike_vec")
        for table, typ in (("emb", "vector"), ("emb_half", "halfvec")):
            for stmt in partition_ddl(table, typ, len(vecs)):
                conn.execute(stmt)
            if conn.execute(f"SELECT count(*) FROM spike_vec.{table}").fetchone()[0] == len(vecs):
                continue
            conn.execute(f"TRUNCATE spike_vec.{table}")
            started = time.perf_counter()
            conn.autocommit = False
            copy_binary(conn, f"spike_vec.{table}", np.arange(len(vecs), dtype=np.int64), ids, vecs,
                        half=(typ == "halfvec"))
            conn.autocommit = True
            record({"step": f"load-{table}", "pgvector": version, "rows": len(vecs),
                    "seconds": round(time.perf_counter() - started, 1)})


def partitions(conn: psycopg.Connection, table: str) -> List[str]:
    """Partition names of a partitioned table, in order."""
    rows = conn.execute("SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid "
                        "JOIN pg_class p ON p.oid = i.inhparent WHERE p.relname = %s ORDER BY c.relname",
                        (table,)).fetchall()
    return sorted((r[0] for r in rows), key=lambda n: int(n.rsplit("_p", 1)[1]))


def cmd_build(args: argparse.Namespace) -> None:
    """One HNSW per partition (each a separate, restartable unit), then one big build."""
    ops = {"emb": "vector_cosine_ops", "emb_half": "halfvec_cosine_ops"}
    with connect(TARGET_DB) as conn:
        conn.autocommit = True
        conn.execute(f"SET maintenance_work_mem = '{args.maintenance_work_mem}'")
        conn.execute(f"SET max_parallel_maintenance_workers = {args.workers}")
        for table, op in ops.items():
            for part in partitions(conn, table):
                idx = f"{part}_hnsw"
                if conn.execute("SELECT to_regclass(%s)", (f"spike_vec.{idx}",)).fetchone()[0]:
                    continue  # already built: resumable at partition granularity
                started = time.perf_counter()
                conn.execute(f"CREATE INDEX {idx} ON spike_vec.{part} USING hnsw (embedding {op}) "
                             f"WITH (m = {HNSW_M}, ef_construction = {HNSW_EF_CONSTRUCTION})")
                size = conn.execute("SELECT pg_size_pretty(pg_relation_size(%s))", (f"spike_vec.{idx}",)).fetchone()[0]
                record({"step": "build-partition", "table": table, "partition": part,
                        "seconds": round(time.perf_counter() - started, 1), "index_size": size,
                        "maintenance_work_mem": args.maintenance_work_mem, "workers": args.workers})
        if args.whole:
            conn.execute(f"CREATE TABLE IF NOT EXISTS spike_vec.emb_whole AS SELECT * FROM spike_vec.emb")
            if not conn.execute("SELECT to_regclass('spike_vec.emb_whole_hnsw')").fetchone()[0]:
                started = time.perf_counter()
                conn.execute(f"CREATE INDEX emb_whole_hnsw ON spike_vec.emb_whole USING hnsw "
                             f"(embedding vector_cosine_ops) WITH (m = {HNSW_M}, "
                             f"ef_construction = {HNSW_EF_CONSTRUCTION})")
                record({"step": "build-whole", "rows": conn.execute("SELECT count(*) FROM spike_vec.emb_whole").fetchone()[0],
                        "seconds": round(time.perf_counter() - started, 1),
                        "maintenance_work_mem": args.maintenance_work_mem, "workers": args.workers})


def cmd_insert(args: argparse.Namespace) -> None:
    """Throughput of inserting into an already-indexed partition (the incremental path)."""
    vecs = np.load(VECTORS)
    rng = np.random.default_rng(7)
    extra = normalise(vecs[rng.integers(0, len(vecs), INSERT_EXTRA)]
                      + rng.normal(0, 0.01, (INSERT_EXTRA, DIM)).astype(np.float32))
    with connect(TARGET_DB) as conn:
        conn.autocommit = True
        for table in ("emb", "emb_half"):
            last = partitions(conn, table)[-1]
            base = conn.execute(f"SELECT coalesce(max(rn), 0) + 1 FROM spike_vec.{table}").fetchone()[0]
            conn.execute(f"ALTER TABLE spike_vec.{table} DETACH PARTITION spike_vec.{last}")
            conn.execute(f"ALTER TABLE spike_vec.{last} DROP CONSTRAINT IF EXISTS {last}_rn_check")
            started = time.perf_counter()
            conn.autocommit = False
            done = 0
            for s in range(0, INSERT_EXTRA, COPY_BATCH):   # one commit per batch: resumable unit
                e = min(s + COPY_BATCH, INSERT_EXTRA)
                copy_binary(conn, f"spike_vec.{last}", np.arange(base + s, base + e, dtype=np.int64),
                            np.full(e - s, -1, dtype=np.int64), extra[s:e], half=(table == "emb_half"))
                done = e
            conn.autocommit = True
            seconds = time.perf_counter() - started
            conn.execute(f"DELETE FROM spike_vec.{last} WHERE src_id = -1")
            lo = int(last.rsplit("_p", 1)[1]) * PARTITION_ROWS
            conn.execute(f"ALTER TABLE spike_vec.{table} ATTACH PARTITION spike_vec.{last} "
                         f"FOR VALUES FROM ({lo}) TO ({lo + PARTITION_ROWS})")
            record({"step": "insert-into-indexed", "table": table, "partition": last, "rows": done,
                    "seconds": round(seconds, 1), "rows_per_s": round(done / seconds)})


def cmd_recall(args: argparse.Namespace) -> None:
    """Recall vs exact search, for the partitioned tables and the whole-table index."""
    vecs, queries = np.load(VECTORS), np.load(QUERIES)
    k_max = max(TOP_K)
    exact = np.empty((len(queries), k_max), dtype=np.int64)          # rn == row index
    for s in range(0, len(queries), 25):                              # 25 x 5 M floats per block
        sims = queries[s:s + 25] @ vecs.T
        top = np.argpartition(-sims, k_max, axis=1)[:, :k_max]
        order = np.argsort(-np.take_along_axis(sims, top, axis=1), axis=1)
        exact[s:s + 25] = np.take_along_axis(top, order, axis=1)
    targets = [("emb", "vector"), ("emb_half", "halfvec")]
    with connect(TARGET_DB) as conn:
        if conn.execute("SELECT to_regclass('spike_vec.emb_whole_hnsw')").fetchone()[0]:
            targets.append(("emb_whole", "vector"))
        for table, typ in targets:
            for ef in EF_SEARCH:
                conn.execute(f"SET hnsw.ef_search = {ef}")
                recalls = {k: [] for k in TOP_K}
                latencies = []
                plan = None
                for qi, q in enumerate(queries):
                    lit = vec_text(q)
                    sql = (f"SELECT rn FROM spike_vec.{table} ORDER BY embedding <=> '{lit}'::{typ}({DIM}) "
                           f"LIMIT {max(TOP_K)}")
                    if plan is None:
                        plan = " / ".join(r[0].strip() for r in conn.execute("EXPLAIN " + sql).fetchall()[:4])
                    started = time.perf_counter()
                    got = [r[0] for r in conn.execute(sql).fetchall()]
                    latencies.append(time.perf_counter() - started)
                    for k in TOP_K:
                        recalls[k].append(len(set(got[:k]) & set(exact[qi, :k].tolist())) / k)
                record({"step": "recall", "table": table, "ef_search": ef,
                        **{f"recall@{k}": round(float(np.mean(v)), 4) for k, v in recalls.items()},
                        "p50_ms": round(float(np.median(latencies)) * 1000, 1),
                        "p95_ms": round(float(np.quantile(latencies, 0.95)) * 1000, 1), "plan": plan[:200]})


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point."""
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("extract")
    s.add_argument("--n", type=int, default=5 * PARTITION_ROWS)
    s = sub.add_parser("queries")
    s.add_argument("--query-file", type=Path, default=DEFAULT_QUERY_FILE)
    s.add_argument("--n", type=int, default=DEFAULT_QUERIES)
    sub.add_parser("load")
    s = sub.add_parser("build")
    s.add_argument("--maintenance-work-mem", default="8GB")
    s.add_argument("--workers", type=int, default=8)
    s.add_argument("--whole", action="store_true", help="also build one index over all rows")
    sub.add_parser("insert")   # run after `recall`: it leaves dead index entries behind
    sub.add_parser("recall")
    args = p.parse_args(argv)
    RESULTS.mkdir(parents=True, exist_ok=True)
    {"extract": cmd_extract, "queries": cmd_queries, "load": cmd_load, "build": cmd_build,
     "insert": cmd_insert, "recall": cmd_recall}[args.cmd](args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
