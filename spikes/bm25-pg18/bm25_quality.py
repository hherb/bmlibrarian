#!/usr/bin/env python3
"""
Phase 0f: ParadeDB pg_search BM25 vs Postgres ts_rank_cd, alone and in hybrid
with the 256-d arctic vectors, on BMLibrarian's own evaluation sets (PG 18).

Corpus: the 48 629-abstract corpus shared by the BMLibrarian evaluation sets
(benchmarks/embedding_dimension/build_bmlibrarian_eval.py). Queries + qrels:
pubmedqa_source, pubmedqa_graded, research_questions. Vectors: the arctic
embeddings already cached by run_benchmark.py (no re-embedding), truncated to
256 d.

Methods (top 100 each):
    tsrank      tsvector + GIN, OR of the query lexemes, ts_rank_cd (today's FTS)
    bm25        pg_search, default tokenizer (no stemming)
    bm25_stem   pg_search, simple tokenizer + English stemmer + English stopwords
    vector      exact cosine on 256-d vectors
    hybrid_*    reciprocal rank fusion (k = 60) of a lexical method and vector

Writes only to schema bm25_eval in bmlibrarian_dev on the PG 18 server (:5532).

Usage:
    uv run python spikes/bm25-pg18/bm25_quality.py load
    uv run python spikes/bm25-pg18/bm25_quality.py eval
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import psycopg

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "benchmarks" / "embedding_dimension"))
import beir_data  # noqa: E402
import retrieval_metrics as rm  # noqa: E402
import run_benchmark as rb  # noqa: E402

PG_PORT = 5532
PG_USER = "hherb"
DB = "bmlibrarian_dev"
EVAL_ROOT = rb.DEFAULT_CACHE_DIR / "bmlibrarian_eval"
SETS = ("pubmedqa_source", "pubmedqa_graded", "research_questions")
ARCTIC = "Snowflake/snowflake-arctic-embed-l-v2.0"
DOC_PROMPT = "none"
QUERY_PROMPT = "model prompt 'query': 'query: '"
DIM = 256
TOP_K = 100
RRF_K = 60
VECTOR_WEIGHTS = (2.0, 3.0)
RESULTS = Path(__file__).resolve().parent / "results"
STEM_TOKENIZER = "pdb.simple('stemmer=english', 'stopwords_language=English')"


def connect() -> psycopg.Connection:
    """The PG 18 dev database only."""
    return psycopg.connect(dbname=DB, host="localhost", port=PG_PORT, user=PG_USER, autocommit=True)


def dataset(name: str) -> beir_data.BeirDataset:
    """Load one evaluation set (all share the same corpus)."""
    return beir_data.load_beir_dataset(EVAL_ROOT / name / "eval", name="custom:eval")


def cached_embeddings(role: str, prompt: str, texts: List[str]) -> np.ndarray:
    """Arctic embeddings from run_benchmark's cache, truncated to 256 d."""
    path = rb.cache_path(rb.DEFAULT_CACHE_DIR, ARCTIC, "custom:eval", role, prompt, None, texts)
    if not path.exists():
        raise SystemExit(f"no cached {role} embeddings at {path}; run run_benchmark.py on this set first")
    return rm.truncate_and_normalize(np.load(path), DIM)


def cmd_load(args: argparse.Namespace) -> None:
    """Three tables over the same corpus: tsvector+GIN, bm25 plain, bm25 stemmed."""
    ds = dataset(SETS[0])
    rows = [(int(k), v) for k, v in ds.corpus.items()]
    with connect() as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS pg_search CASCADE")
        conn.execute("DROP SCHEMA IF EXISTS bm25_eval CASCADE")
        conn.execute("CREATE SCHEMA bm25_eval")
        conn.execute("""CREATE TABLE bm25_eval.docs (id bigint PRIMARY KEY, body text NOT NULL,
            tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', body)) STORED)""")
        with conn.cursor() as cur, cur.copy("COPY bm25_eval.docs (id, body) FROM STDIN") as cp:
            for r in rows:
                cp.write_row(r)
        timings = {}
        for label, sql in (
            ("gin", "CREATE INDEX docs_tsv ON bm25_eval.docs USING gin (tsv) WITH (fastupdate = off)"),
            ("bm25_plain", "CREATE TABLE bm25_eval.plain AS SELECT id, body FROM bm25_eval.docs; "
                           "ALTER TABLE bm25_eval.plain ADD PRIMARY KEY (id); "
                           "CREATE INDEX plain_bm25 ON bm25_eval.plain USING bm25 (id, body) WITH (key_field = 'id')"),
            ("bm25_stem", "CREATE TABLE bm25_eval.stem AS SELECT id, body FROM bm25_eval.docs; "
                          "ALTER TABLE bm25_eval.stem ADD PRIMARY KEY (id); "
                          f"CREATE INDEX stem_bm25 ON bm25_eval.stem USING bm25 (id, (body::{STEM_TOKENIZER})) "
                          "WITH (key_field = 'id')"),
        ):
            started = time.perf_counter()
            for stmt in sql.split("; "):
                conn.execute(stmt)
            timings[label] = round(time.perf_counter() - started, 2)
        sizes = {r[0]: r[1] for r in conn.execute(
            "SELECT relname, pg_size_pretty(pg_relation_size(c.oid)) FROM pg_class c JOIN pg_namespace n "
            "ON n.oid = c.relnamespace WHERE n.nspname = 'bm25_eval' AND relkind = 'i'").fetchall()}
    print(json.dumps({"step": "load", "docs": len(rows), "index_build_s": timings, "index_sizes": sizes}))


def tsrank_query(conn, text: str) -> List[str]:
    """OR of the query's English lexemes, ranked by ts_rank_cd."""
    lexemes = conn.execute("SELECT coalesce(array_agg(lexeme), '{}') FROM unnest(to_tsvector('english', %s))",
                           (text,)).fetchone()[0]
    if not lexemes:
        return []
    tsq = " | ".join("'" + lx.replace("'", "''") + "'" for lx in lexemes)
    return [str(r[0]) for r in conn.execute(
        "SELECT id FROM bm25_eval.docs, to_tsquery('simple', %s) q WHERE tsv @@ q "
        "ORDER BY ts_rank_cd(tsv, q) DESC LIMIT %s", (tsq, TOP_K)).fetchall()]


def bm25_query(conn, table: str, text: str) -> List[str]:
    """pg_search match disjunction, ordered by BM25 score."""
    return [str(r[0]) for r in conn.execute(
        f"SELECT id FROM bm25_eval.{table} WHERE body ||| %s ORDER BY pdb.score(id) DESC LIMIT %s",
        (text, TOP_K)).fetchall()]


def rrf(*lists: List[str], weights: Optional[Sequence[float]] = None) -> List[str]:
    """(Weighted) reciprocal rank fusion of ranked id lists."""
    scores: Dict[str, float] = {}
    for ranked, w in zip(lists, weights or [1.0] * len(lists)):
        for rank, doc in enumerate(ranked):
            scores[doc] = scores.get(doc, 0.0) + w / (RRF_K + rank + 1)
    return [d for d, _ in sorted(scores.items(), key=lambda kv: -kv[1])][:TOP_K]


def cmd_eval(args: argparse.Namespace) -> None:
    """Rank every query of every set with every method; metrics + paired bootstrap."""
    RESULTS.mkdir(parents=True, exist_ok=True)
    out_rows = []
    doc_ids: Optional[List[str]] = None
    doc_emb: Optional[np.ndarray] = None
    with connect() as conn:
        for name in SETS:
            ds = dataset(name)
            if doc_emb is None:
                doc_ids = list(ds.corpus)
                doc_emb = cached_embeddings("document", DOC_PROMPT, list(ds.corpus.values()))
            qids = list(ds.queries)
            q_emb = cached_embeddings("query", QUERY_PROMPT, list(ds.queries.values()))
            ranked: Dict[str, List[List[str]]] = {m: [] for m in ("tsrank", "bm25", "bm25_stem", "vector")}
            latency: Dict[str, List[float]] = {m: [] for m in ("tsrank", "bm25", "bm25_stem")}
            for i, qid in enumerate(qids):
                text = ds.queries[qid]
                for method, fn in (("tsrank", lambda: tsrank_query(conn, text)),
                                   ("bm25", lambda: bm25_query(conn, "plain", text)),
                                   ("bm25_stem", lambda: bm25_query(conn, "stem", text))):
                    started = time.perf_counter()
                    ranked[method].append(fn())
                    latency[method].append(time.perf_counter() - started)
                sims = doc_emb @ q_emb[i]
                top = np.argpartition(-sims, TOP_K)[:TOP_K]
                ranked["vector"].append([doc_ids[j] for j in top[np.argsort(-sims[top])]])
            for lex in ("tsrank", "bm25", "bm25_stem"):
                ranked[f"hybrid_{lex}"] = [rrf(a, b) for a, b in zip(ranked[lex], ranked["vector"])]
            for w in VECTOR_WEIGHTS:   # lexical weight 1, vector weight w
                ranked[f"hybrid_bm25_stem_v{w:g}"] = [rrf(a, b, weights=(1.0, w))
                                                      for a, b in zip(ranked["bm25_stem"], ranked["vector"])]
            metrics = {m: rm.evaluate_rankings(r, qids, ds.qrels) for m, r in ranked.items()}
            for method, pm in metrics.items():
                row = {"set": name, "queries": len(qids), "method": method,
                       **{k: round(v, 4) for k, v in pm.means().items()}}
                if method != "tsrank":
                    b = rm.paired_bootstrap(pm.ndcg, metrics["tsrank"].ndcg)
                    row["delta_ndcg10_vs_tsrank"] = [round(b.mean_diff, 4), round(b.ci_low, 4), round(b.ci_high, 4)]
                if method.startswith("hybrid"):
                    b = rm.paired_bootstrap(pm.ndcg, metrics["vector"].ndcg)
                    row["delta_ndcg10_vs_vector"] = [round(b.mean_diff, 4), round(b.ci_low, 4), round(b.ci_high, 4)]
                if method in latency:
                    row["p50_ms"] = round(float(np.median(latency[method])) * 1000, 1)
                    row["p95_ms"] = round(float(np.quantile(latency[method], 0.95)) * 1000, 1)
                out_rows.append(row)
                print(json.dumps(row), flush=True)
    with open(RESULTS / "quality.jsonl", "w", encoding="utf-8") as fh:
        for row in out_rows:
            fh.write(json.dumps(row) + "\n")


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point."""
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("cmd", choices=("load", "eval"))
    args = p.parse_args(argv)
    {"load": cmd_load, "eval": cmd_eval}[args.cmd](args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
