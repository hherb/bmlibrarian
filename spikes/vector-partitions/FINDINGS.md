# Phase 0d findings — resumable vector indexing, 256 d (2026-10-12)

Data: the first 5 000 000 production chunk vectors (`emb_1024`, model_id 1,
ordered by `chunk_id`), read from `knowledgebase` read-only, sliced to 256
dims in SQL (`(embedding::real[])[1:256]`), L2-renormalised. Queries: 300
PubMedQA questions embedded with arctic's `query: ` prompt (sentence-transformers)
and truncated the same way. Target: `spike_vec` in `bmlibrarian_dev`, where
the pgvector extension was updated 0.5.1 → 0.8.6. HNSW `m = 16`,
`ef_construction = 64`, `maintenance_work_mem` 8 GB, 8 parallel maintenance
workers. Sanity check: top-1 cosine for real queries 0.52–0.85, random pairs
median 0.12. Raw data: `results/timings.jsonl`.

## 1. Build: bounded, restartable units

| Index | Rows | Build | Index size |
|---|---|---|---|
| `vector(256)`, per partition | 1 M | 102–107 s | 1.30 GB |
| `halfvec(256)`, per partition | 1 M | 87–94 s | 0.79 GB |
| `vector(256)`, one unpartitioned index | 5 M | 551 s | — |

- Builds are near-linear up to 5 M (5.3× one partition).
- **Projection for the 37.5 M production chunk vectors:** 38 partitions ×
  ~90–105 s ≈ **1 h of index builds**. Each partition is an independent unit
  of under 2 minutes, so an interruption loses at most one build.
- The previous 1024-d build took close to **three weeks**. The likely reason:
  37.5 M × 1024 float4 ≈ 150 GB of vectors, far beyond `maintenance_work_mem`.
  Once the HNSW graph no longer fits in memory, pgvector's build slows by
  orders of magnitude. At 256 d, and above all per partition, every build
  stays in memory. (The 1024-d cause is inferred, not re-measured.)
- Loading via COPY BINARY: 5 M rows in 20 s (`vector`) / 12 s (`halfvec`).
  The read-only extraction from production took 161 s for 5 M.

## 2. Recall and latency vs exact search

| Layout | `ef_search` | recall@10 | recall@100 | p50 | p95 |
|---|---|---|---|---|---|
| 5 × 1 M partitions, `vector` | 100 | 0.969 | 0.950 | 27 ms | 44 ms |
| 5 × 1 M partitions, `vector` | 200 | 0.982 | 0.973 | 39 ms | 54 ms |
| 5 × 1 M partitions, `vector` | 400 | 0.991 | 0.987 | 70 ms | 91 ms |
| 5 × 1 M partitions, `halfvec` | 100 | 0.965 | 0.951 | 20 ms | 29 ms |
| 5 × 1 M partitions, `halfvec` | 200 | 0.981 | 0.973 | 36 ms | 48 ms |
| 5 × 1 M partitions, `halfvec` | 400 | 0.993 | 0.987 | 63 ms | 85 ms |
| one 5 M index, `vector` | 200 | 0.960 | 0.926 | 7 ms | 13 ms |
| one 5 M index, `vector` | 400 | 0.973 | 0.957 | 12 ms | 19 ms |

- **Partitioning raises recall.** Postgres plans a `Merge Append` over the
  per-partition HNSW scans, and each partition contributes up to `ef_search`
  candidates.
- **Latency grows with the number of partitions** (~5–8 ms per partition
  at `ef_search` 100–200).
- **`halfvec` gives the same recall as `vector`**, with a 40 % smaller index
  and slightly lower latency. `halfvec` is fine for 256-d arctic vectors.
- **`ef_search` must be ≥ the requested k.** pgvector returns at most
  `ef_search` rows per index scan; with `ef_search = 40` the single index gave
  recall@100 of 0.37 (it returned 40 rows), while 5 partitions returned 5 × 40.

## 3. Incremental inserts into an indexed partition are slow

| Path | Throughput |
|---|---|
| COPY into an indexed 1 M partition, one connection, commit per 50 k | **206 rows/s** (`vector`), **187 rows/s** (`halfvec`) |
| Building a 1 M partition's index from scratch | ~9 500–11 500 vectors/s |

Building is about 46× faster than inserting into an existing HNSW graph.
Parallel inserting connections were not measured; HNSW supports concurrent
inserts, but a large factor is unlikely to close the gap.

## 4. Design that follows: "open + sealed" partitions

- **Sealed partitions** (~1–4 M vectors each) carry an HNSW index built
  once, in one bounded, restartable step (minutes).
- **One open partition** receives new vectors **without** an HNSW index, so
  inserts run at COPY speed and commit in small, resumable batches. Queries
  scan it exactly; keep it small, e.g. ≤ 200 k rows, so the exact scan stays
  cheap.
- **When the open partition fills**, it is sealed (index build) and a new open
  partition is created. An interrupted seal just restarts. Nothing ever needs
  a multi-hour, all-or-nothing step.
- **Partition size is the trade-off** between build-unit length and query
  latency (more partitions mean more index scans per query). With 37.5 M
  vectors: 1 M per partition gives 38 partitions, estimated ~150–300 ms per
  top-100 query (extrapolated, not measured); 4 M gives ~10 partitions with
  ~7–9 min builds. Measure at full scale before fixing the size.

## 5. Storage at 256 d (37.5 M vectors, extrapolated)

| | Today (1024-d `vector`) | 256-d `halfvec`, partitioned |
|---|---|---|
| HNSW index | 286 GB | ~30 GB |
| Table | ~194 GB heap | ~20 GB |

## Caveats

- 5 M of 37.5 M vectors, and the first 5 M by `chunk_id` (the oldest chunks).
  Latency and recall at 38 partitions are extrapolated.
- One machine, default server settings (no import profile for these builds).
  HNSW builds use `maintenance_work_mem` (8 GB, session-level), not
  `shared_buffers`.
- Query latency was measured on a warm cache, from one client, serially.
