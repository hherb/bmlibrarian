#!/usr/bin/env python3
"""
Phase 0e: the vector design at full production scale (all ~37.5 M chunk vectors).

Question: with every production vector at 256 d (halfvec), what do partition
size and partition count do to build time, query latency and recall — and
does an unindexed "open" partition keep queries fast?

Every step is resumable, as the real importer must be:
    extract   keyset-paginated 1 M-row shards from knowledgebase (READ ONLY),
              sliced to 256 d in SQL, renormalised, saved as float16 shards;
              existing shards are skipped
    load      COPY BINARY each shard into each layout table; one transaction per
              shard, recorded in spike_vec.full_ledger (skipped when present)
    build     CREATE INDEX hnsw per partition, skipped if it already exists
    recall    exact top-100 over all shards (numpy) vs each layout, per ef_search
    openscan  attach an unindexed 200 k "open" partition and re-measure latency

Layouts: spike_vec.full_1m (1 M rows per partition) and spike_vec.full_4m (4 M).

Usage:
    uv run python spikes/vector-partitions/full_scale.py extract
    uv run python spikes/vector-partitions/full_scale.py load
    uv run python spikes/vector-partitions/full_scale.py build
    uv run python spikes/vector-partitions/full_scale.py recall
    uv run python spikes/vector-partitions/full_scale.py openscan
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

SPIKE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SPIKE_DIR))
import vector_bench as vb  # noqa: E402

SHARD_DIR = vb.RESULTS / "full"
SHARD_ROWS = 1_000_000
LAYOUTS: Dict[str, int] = {"full_1m": 1_000_000, "full_4m": 4_000_000}
OPEN_ROWS = 200_000
EF_SEARCH = (100, 200, 400)
TOP_K = 100
QUERY_BLOCK = 300


def shard_paths(i: int) -> Tuple[Path, Path]:
    """(vectors, chunk ids) file pair of shard ``i``."""
    return SHARD_DIR / f"shard_{i:05d}.npy", SHARD_DIR / f"ids_{i:05d}.npy"


def shards() -> List[int]:
    """Indices of complete shards on disk, in order."""
    return sorted(int(p.stem.split("_")[1]) for p in SHARD_DIR.glob("shard_*.npy")
                  if shard_paths(int(p.stem.split("_")[1]))[1].exists())


def cmd_extract(args: argparse.Namespace) -> None:
    """Keyset pagination by chunk_id (indexed); each shard is its own resumable unit."""
    SHARD_DIR.mkdir(parents=True, exist_ok=True)
    done = shards()
    i = (done[-1] + 1) if done else 0
    last = int(np.load(shard_paths(done[-1])[1])[-1]) if done else -1
    with vb.connect(vb.SOURCE_DB) as conn, conn.cursor() as cur:
        cur.execute(f"SET statement_timeout = '{vb.EXTRACT_TIMEOUT}'")
        while args.max_shards is None or i < args.max_shards:
            started = time.perf_counter()
            ids = np.empty(SHARD_ROWS, dtype=np.int64)
            out = np.empty((SHARD_ROWS, vb.DIM), dtype=np.float32)
            n = 0
            sql = (f"COPY (SELECT chunk_id, ((embedding::real[])[1:{vb.DIM}])::text FROM emb_1024 "
                   f"WHERE model_id = {vb.PRODUCTION_MODEL_ID} AND chunk_id > {last} "
                   f"ORDER BY chunk_id LIMIT {SHARD_ROWS}) TO STDOUT")
            with cur.copy(sql) as cp:
                for cid, arr in cp.rows():
                    ids[n] = int(cid)
                    out[n] = np.fromstring(arr[1:-1], sep=",", dtype=np.float32)
                    n += 1
            if n == 0:
                break
            vpath, ipath = shard_paths(i)
            np.save(vpath, vb.normalise(out[:n]).astype(np.float16))
            np.save(ipath, ids[:n])          # written last: marks the shard complete
            last = int(ids[n - 1])
            vb.record({"step": "full-extract", "shard": i, "rows": n,
                       "seconds": round(time.perf_counter() - started, 1)})
            i += 1
            if n < SHARD_ROWS:
                break


def ensure_layout(conn, table: str, part_rows: int, total: int) -> None:
    """Partitioned halfvec table with ``part_rows`` rows per partition."""
    conn.execute(f"CREATE TABLE IF NOT EXISTS spike_vec.{table} (rn bigint NOT NULL, src_id bigint NOT NULL, "
                 f"embedding halfvec({vb.DIM}) NOT NULL) PARTITION BY RANGE (rn)")
    for p in range((total + part_rows - 1) // part_rows):
        conn.execute(f"CREATE TABLE IF NOT EXISTS spike_vec.{table}_p{p:03d} PARTITION OF spike_vec.{table} "
                     f"FOR VALUES FROM ({p * part_rows}) TO ({(p + 1) * part_rows})")


def cmd_load(args: argparse.Namespace) -> None:
    """COPY every shard into every layout; the ledger row commits with the shard."""
    ids_all = shards()
    total = sum(len(np.load(shard_paths(i)[1], mmap_mode="r")) for i in ids_all)
    with vb.connect(vb.TARGET_DB) as conn:
        conn.autocommit = True
        conn.execute("CREATE TABLE IF NOT EXISTS spike_vec.full_ledger (layout text, shard int, rows int, "
                     "seconds real, PRIMARY KEY (layout, shard))")
        for table, part_rows in LAYOUTS.items():
            ensure_layout(conn, table, part_rows, total)
            done = {r[0] for r in conn.execute("SELECT shard FROM spike_vec.full_ledger WHERE layout = %s",
                                               (table,)).fetchall()}
            offset = 0
            for i in ids_all:
                vecs = np.load(shard_paths(i)[0], mmap_mode="r")
                n = len(vecs)
                if i not in done:
                    started = time.perf_counter()
                    conn.autocommit = False
                    with conn.transaction():
                        vb.copy_binary(conn, f"spike_vec.{table}", np.arange(offset, offset + n, dtype=np.int64),
                                       np.load(shard_paths(i)[1]), np.asarray(vecs, dtype=np.float32), half=True)
                        conn.execute("INSERT INTO spike_vec.full_ledger VALUES (%s, %s, %s, %s)",
                                     (table, i, n, time.perf_counter() - started))
                    conn.autocommit = True
                offset += n
            vb.record({"step": "full-load", "layout": table, "rows": total})


def partition_names(conn, table: str) -> List[str]:
    """Partitions of ``table`` in range order."""
    return sorted(r[0] for r in conn.execute(
        "SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid "
        "JOIN pg_class p ON p.oid = i.inhparent WHERE p.relname = %s AND c.relname <> %s",
        (table, f"{table}_open")).fetchall())


def cmd_build(args: argparse.Namespace) -> None:
    """One HNSW per partition; an existing index means that unit is done."""
    with vb.connect(vb.TARGET_DB) as conn:
        conn.autocommit = True
        conn.execute(f"SET maintenance_work_mem = '{args.maintenance_work_mem}'")
        conn.execute(f"SET max_parallel_maintenance_workers = {args.workers}")
        for table in LAYOUTS:
            for part in partition_names(conn, table):
                idx = f"{part}_hnsw"
                if conn.execute("SELECT to_regclass(%s)", (f"spike_vec.{idx}",)).fetchone()[0]:
                    continue
                rows = conn.execute(f"SELECT count(*) FROM spike_vec.{part}").fetchone()[0]
                started = time.perf_counter()
                conn.execute(f"CREATE INDEX {idx} ON spike_vec.{part} USING hnsw (embedding halfvec_cosine_ops) "
                             f"WITH (m = {vb.HNSW_M}, ef_construction = {vb.HNSW_EF_CONSTRUCTION})")
                vb.record({"step": "full-build", "layout": table, "partition": part, "rows": rows,
                           "seconds": round(time.perf_counter() - started, 1),
                           "index_mb": conn.execute("SELECT pg_relation_size(%s) / 1048576",
                                                    (f"spike_vec.{idx}",)).fetchone()[0]})


def exact_topk(queries: np.ndarray) -> np.ndarray:
    """Global exact top-K row numbers (rn) over all shards, merged shard by shard."""
    best_s = np.full((len(queries), TOP_K), -np.inf, dtype=np.float32)
    best_i = np.zeros((len(queries), TOP_K), dtype=np.int64)
    offset = 0
    for i in shards():
        vecs = np.asarray(np.load(shard_paths(i)[0], mmap_mode="r"), dtype=np.float32)
        sims = queries @ vecs.T
        top = np.argpartition(-sims, TOP_K, axis=1)[:, :TOP_K]
        cand_s = np.concatenate([best_s, np.take_along_axis(sims, top, axis=1)], axis=1)
        cand_i = np.concatenate([best_i, top + offset], axis=1)
        keep = np.argsort(-cand_s, axis=1)[:, :TOP_K]
        best_s, best_i = np.take_along_axis(cand_s, keep, axis=1), np.take_along_axis(cand_i, keep, axis=1)
        offset += len(vecs)
    return best_i


def measure(conn, table: str, queries: np.ndarray, exact: Optional[np.ndarray], ef: int) -> Dict:
    """Recall@10/@100 (if exact given) and latency for one table at one ef_search."""
    conn.execute(f"SET hnsw.ef_search = {ef}")
    lat, r10, r100 = [], [], []
    for qi, q in enumerate(queries):
        sql = (f"SELECT rn FROM spike_vec.{table} ORDER BY embedding <=> '{vb.vec_text(q)}'::halfvec({vb.DIM}) "
               f"LIMIT {TOP_K}")
        started = time.perf_counter()
        got = [r[0] for r in conn.execute(sql).fetchall()]
        lat.append(time.perf_counter() - started)
        if exact is not None:
            r10.append(len(set(got[:10]) & set(exact[qi, :10].tolist())) / 10)
            r100.append(len(set(got) & set(exact[qi].tolist())) / TOP_K)
    row = {"table": table, "ef_search": ef, "p50_ms": round(float(np.median(lat)) * 1000, 1),
           "p95_ms": round(float(np.quantile(lat, 0.95)) * 1000, 1)}
    if exact is not None:
        row.update({"recall@10": round(float(np.mean(r10)), 4), "recall@100": round(float(np.mean(r100)), 4)})
    return row


def cmd_recall(args: argparse.Namespace) -> None:
    """Recall and latency for each layout against exact search over everything."""
    queries = np.load(vb.QUERIES)[:args.queries]
    started = time.perf_counter()
    exact = exact_topk(queries)
    vb.record({"step": "full-exact", "queries": len(queries), "seconds": round(time.perf_counter() - started, 1)})
    with vb.connect(vb.TARGET_DB) as conn:
        for table in LAYOUTS:
            parts = len(partition_names(conn, table))
            for q in queries[:5]:   # warm-up per layout
                conn.execute(f"SELECT rn FROM spike_vec.{table} ORDER BY embedding <=> "
                             f"'{vb.vec_text(q)}'::halfvec({vb.DIM}) LIMIT {TOP_K}").fetchall()
            for ef in EF_SEARCH:
                vb.record({"step": "full-recall", "partitions": parts, **measure(conn, table, queries, exact, ef)})


def cmd_openscan(args: argparse.Namespace) -> None:
    """An unindexed open partition attached to the 1 M layout: what does it add to a query?"""
    queries = np.load(vb.QUERIES)[:args.queries]
    rng = np.random.default_rng(11)
    with vb.connect(vb.TARGET_DB) as conn:
        conn.autocommit = True
        # The open partition starts where the last sealed partition's range ends
        # (not at max(rn) + 1, which still lies inside the last sealed range).
        rows = conn.execute("SELECT max(rn) + 1 FROM spike_vec.full_1m").fetchone()[0]
        part_rows = LAYOUTS["full_1m"]
        top = ((rows + part_rows - 1) // part_rows) * part_rows
        conn.execute(f"CREATE TABLE IF NOT EXISTS spike_vec.full_1m_open PARTITION OF spike_vec.full_1m "
                     f"FOR VALUES FROM ({top}) TO ({top + 10_000_000})")
        if conn.execute("SELECT count(*) FROM spike_vec.full_1m_open").fetchone()[0] == 0:
            src = np.asarray(np.load(shard_paths(shards()[0])[0], mmap_mode="r")[:OPEN_ROWS], dtype=np.float32)
            extra = vb.normalise(src + rng.normal(0, 0.02, src.shape).astype(np.float32))
            conn.autocommit = False
            vb.copy_binary(conn, "spike_vec.full_1m_open", np.arange(top, top + OPEN_ROWS, dtype=np.int64),
                           np.full(OPEN_ROWS, -1, dtype=np.int64), extra, half=True)
            conn.autocommit = True
            conn.execute("ANALYZE spike_vec.full_1m_open")
        plan = " / ".join(r[0].strip() for r in conn.execute(
            f"EXPLAIN SELECT rn FROM spike_vec.full_1m_open ORDER BY embedding <=> "
            f"'{vb.vec_text(queries[0])}'::halfvec({vb.DIM}) LIMIT {TOP_K}").fetchall()[:3])
        vb.record({"step": "open-only", **measure(conn, "full_1m_open", queries, None, 100), "plan": plan[:200]})
        for ef in (100, 200):
            vb.record({"step": "sealed+open", **measure(conn, "full_1m", queries, None, ef)})


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point."""
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("extract")
    s.add_argument("--max-shards", type=int)
    sub.add_parser("load")
    s = sub.add_parser("build")
    s.add_argument("--maintenance-work-mem", default="8GB")
    s.add_argument("--workers", type=int, default=8)
    for name in ("recall", "openscan"):
        s = sub.add_parser(name)
        s.add_argument("--queries", type=int, default=QUERY_BLOCK)
    args = p.parse_args(argv)
    vb.RESULTS.mkdir(parents=True, exist_ok=True)
    {"extract": cmd_extract, "load": cmd_load, "build": cmd_build, "recall": cmd_recall,
     "openscan": cmd_openscan}[args.cmd](args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
