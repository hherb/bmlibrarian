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

## 6. Full production scale (2026-10-13): all 37 478 552 vectors, `halfvec(256)`

Run with `full_scale.py`, every step resumable:
- **Extraction:** keyset-paginated 1 M shards from `knowledgebase`, READ ONLY,
  in 1 177 s (≈ 20 min).
- **Load:** COPY BINARY, one transaction per shard plus a ledger row; about
  5 min for both layouts.
- **Builds:** one `CREATE INDEX` per partition; a partition is skipped if its
  index already exists.

Queries: the same 300 real PubMedQA questions; exact top-100 over all 37.5 M
computed with numpy in 104 s. Server on day-to-day settings (`shared_buffers`
128 MB), so index pages come from the OS page cache.

### Builds

| Layout | Partitions | Total build | Median per partition | Max | HNSW total |
|---|---|---|---|---|---|
| 1 M rows/partition | 38 | 4 685 s (78 min) | 90.5 s | 1 296 s* | 29.0 GB |
| 4 M rows/partition | 10 | 3 717 s (62 min) | 380 s | 487 s | 29.0 GB |

\* Partition p017 took 1 296 s once, but **88 s when rebuilt alone**. pg_stat
shows insert-triggered autovacuum on the freshly loaded partitions at the
same moment. **Seal step rule: `VACUUM (ANALYZE)` the partition explicitly
before `CREATE INDEX`**, so no autovacuum competes with the build.

Compared with the old 1024-d index: 286 GB, built in ~3 weeks in one
uninterruptible step. Now: 29 GB, ~1 h, in 10–38 units that can each be
redone.

### Recall and latency (warm)

| Layout | `ef_search` | recall@10 | recall@100 | p50 | p95 |
|---|---|---|---|---|---|
| 38 × 1 M | 200 | 0.993 | 0.985 | 265 ms | 355 ms |
| 38 × 1 M | 400 | 0.997 | 0.992 | 451 ms | 581 ms |
| 10 × 4 M | 200 | 0.979 | 0.971 | 123 ms | 194 ms |
| **10 × 4 M** | **400** | **0.989** | **0.984** | **145 ms** | **210 ms** |

The first `ef_search` series for each layout (not shown) ran on a cold cache:
p95 of 1.2–3.3 s. With 29 GB of index and RAM given to inference,
**cold-cache latency is the practical risk**; `pg_prewarm` before a review
session is an option.

The historical reference is a documented 263 s query on the 1024-d index.

### Open partition (unindexed, 200 k rows, attached to the 1 M layout)

| Query | p50 | p95 |
|---|---|---|
| Open partition alone (exact, parallel seq scan) | 26 ms | 29 ms |
| 38 sealed + open, `ef_search` 200 | 357 ms | 453 ms (vs 265 / 355 without) |

Attached under the partitioned parent, the open partition adds ~90 ms: it is
scanned without the parallel plan it gets on its own. Keep it small.

### Conclusion: tiered partitions

1. **Major partitions of 4 M rows** with HNSW (build ~6–8 min each, bounded
   and restartable). Query with `ef_search = 400`: recall@100 0.984 at p50
   145 ms over all 37.5 M vectors.
2. **One open partition of ≤ 250 k rows** without an index (exact scan; new
   embeddings land here at COPY speed).
3. **When the open partition is full**, seal it as a *minor* partition
   (`VACUUM ANALYZE`, then HNSW build: ≤ ~30 s at 250 k, by linear scaling
   from the measured 1 M build).
4. **Compaction:** when minors add up to 4 M rows, build one new 4 M major
   offline (a separate table, ~6–8 min, restartable), then swap it in a
   single transaction (DETACH the minors, ATTACH the major). Queries never
   see a half-built index; an interrupted compaction is simply restarted.
