# BMLibrarian in Rust — implementation plan

Status: **draft for approval**, 2026-10-13. Based on the feasibility study and
Phase 0 measurements in `rust_port_planning.md` and `spikes/*/FINDINGS.md`.
Every number below was measured on the M3 Max / Postgres.app 16 machine unless
it is marked *projected*.

## 0. Constraints this plan is built on

Decided by the owner. Everything below follows from them.

1. **256-d vectors**: arctic-embed-l-v2.0, truncated and renormalised.
   Non-inferior to 1024 d on every evaluation set with ≥ 300 queries.
2. **PostgreSQL is the only data and index system.** No external search engine.
3. **Every long-running step is stoppable and resumable**, even at the cost of
   speed. No all-or-nothing step longer than minutes.
4. **RAM is borrowed only during imports.** Day-to-day RAM is reserved for
   model inference.
5. **bmlib (Python and Rust) owns shared functionality.** BMLibrarian uses it,
   and contributes generic pieces back to it.

## 1. What Phase 0 established

| Question | Answer |
|---|---|
| Rust vs Python for ingest | Design gives 5.8× in either language (COPY + set-based merge + parallelism). Rust adds 1.3–1.45× on top; its parser is 6× faster single-threaded and 35× with 8 threads. The port is justified by architecture (one process, a real pipeline, a single binary, bmlib Rust), not by raw speed. |
| Resumable ingest | Works. One transaction per source file, including its ledger row: SIGKILL mid-run → resume → identical PMID set, no duplicates. |
| Slowdown past a few million rows | Not reproduced with set-based writes, up to 30 M rows. The real culprits were (a) GIN `fastupdate` pending-list flushes (one file took 52 min) and (b) a checkpoint every 2–3 s on default server settings. Fixes: `fastupdate = off` (~14 % faster overall, no stalls) and an import-time server profile. |
| Import-time server profile | Works: `shared_buffers` 32 GB and `max_wal_size` 64 GB during the import, restored afterwards; a state file keeps it across a kill and resume. Forced checkpoints dropped from ~6 per minute to 1–2 per 5 M rows. |
| Vector indexing without multi-week builds | **Measured at full scale:** all 37.5 M production vectors (`halfvec(256)`) in 10 × 4 M partitions, built in 62 min as 10 restartable units (29 GB of HNSW, against 286 GB built in ~3 weeks before). Queries at `ef_search` 400 reach recall@100 0.984 at p50 145 ms / p95 210 ms (§9). Incremental inserts into an indexed partition run at only ~200 rows/s, so new vectors go to a small unindexed *open* partition. |
| Vector type | `halfvec(256)` matches `vector(256)` on recall at 60 % of the index size. |
| Embedding inference | Precision matters, language does not: fp16 PyTorch MPS 32.7 docs/s, Ollama F16 26.7, candle f32 10.5. Embedding stays an external service; the existing 37.5 M vectors are truncated, not recomputed (cosine 0.9987 against the HF model at 256 d). |
| Production importer defects | Author keywords always dropped (69 % of modern records have them), retraction cross-references never read, DOI lookup can return a reference's DOI, revision handling depends on arrival order, `all_keywords` unordered. |

## 2. Target architecture

```
                     ┌──────────────── bmlibrarian-rs (one binary) ────────────────┐
 PubMed FTP/HTTPS ──▶│ ingest: fetch → parse (rayon) → COPY+merge (tokio) → ledger │
 medRxiv API ───────▶│        per-file transaction · import profile on/off          │
 Europe PMC / PMC OA▶│ fulltext: bmlib FullTextService (JATS first, then PDF)       │
                     │ index:  chunk queue → embed service → open partition → seal  │
                     │ search: hybrid SQL (BM25/tsvector + halfvec HNSW, RRF)       │
                     │ grade:  relevance (LLM) + bmlib quality tiers + transparency │
                     │ review: systematic-review workflow, reports (Typst)          │
                     │ api:    CLI · MCP server (rmcp) · later Tauri GUI            │
                     └───────────────┬──────────────────────────────┬──────────────┘
                                     │ SQL only                     │ HTTP
                               PostgreSQL 16/18              embedding service
                         (document, ledger, chunks,       (Ollama F16 or fp16 PyTorch
                          partitioned halfvec, FTS)           sidecar), LLMs
```

### Workspace layout

A Cargo workspace at `rust/` **in this repository**, so that SQL migrations,
the Python app (which keeps running during the migration) and the Rust code
change together.

| Crate | Responsibility | Depends on |
|---|---|---|
| `bml-db` | Pool (`deadpool-postgres`/`tokio-postgres`), migrations runner (reads `migrations/`), binary COPY helpers, import-profile switcher | pgvector crate |
| `bml-ingest` | Source adapters (PubMed baseline/updates, medRxiv, Europe PMC, PMC OA), parsers, ledger, revision-aware merge | `bml-db`, bmlib `publications`, `fulltext` |
| `bml-index` | Chunking, embedding-service client, vector partition manager (open/seal), FTS maintenance | `bml-db`, bmlib `llm` |
| `bml-search` | Hybrid query builder (BM25 or tsvector + vectors + RRF), filters (date, type, source) | `bml-db` |
| `bml-grade` | Relevance scoring, study-design/quality tiers, transparency/bias | bmlib `quality`, `transparency`, `agents` |
| `bml-review` | Review workflow (planner → search → screen → grade → synthesise → report), audit trail, checkpoints | the above, bmlib `citations`, `context_processor` |
| `bml-cli` | `bml import …`, `bml index …`, `bml search …`, `bml review …`, `bml db profile …` | all |
| `bml-mcp` | MCP server over the same services (`rmcp`) | `bml-search`, `bml-grade`, `bml-review` |

Concurrency: tokio for I/O; a rayon pool for parsing and chunking; bounded
channels between stages. bmlib Rust is synchronous by design, so its calls run
under `spawn_blocking`. PDFium is not thread-safe, so PDF work runs in worker
processes.

## 3. Database design

All schema changes are **idempotent migrations** in `migrations/`, applied
with `bmlibrarian_dev` first, then `knowledgebase` with approval.

### 3.1 Documents (`public.document`, kept)

Measured: no partitioning is needed for the document table. Ingest stayed
flat to 30 M rows.

- `ALTER INDEX idx_document_fts SET (fastupdate = off)`.
- Keep the generated `search_vector`. With `fastupdate = off`, ingest with full
  FTS ran at ~9.9 k rows/s (≈ 1.1 h for the baseline, *projected*), with no
  stalls.
- Add `date_revised date` (from `MedlineCitation/DateRevised`). The merge
  updates only when `EXCLUDED.date_revised >= document.date_revised`, so the
  newest revision wins whatever the arrival order.
- Fix `update_all_keywords_trigger` to `ORDER BY` its output.

### 3.2 Ingest bookkeeping (new schema `ingest`)

- `ingest.ledger(source, file, sha256, records, started_at, finished_at, seconds)`:
  written **in the same transaction** as the file's data. Re-running a file is
  idempotent (ON CONFLICT merge).
- `ingest.profile_state`: mirrors the import-profile state file, so the server
  itself shows whether the import profile is active.

### 3.3 Vectors (new: `semantic.emb256`)

- `halfvec(256)`, `PARTITION BY RANGE (chunk_id)`, organised in **tiers**
  (measured basis in §9):
  - **Major** partitions of 4 M rows with HNSW (`m = 16`,
    `ef_construction = 64`, `halfvec_cosine_ops`). Building one takes ~6–8
    min and is restartable.
  - **One open** partition of ≤ 250 k rows without HNSW. New embeddings land
    here at COPY speed, and queries scan it exactly.
  - **Minor** partitions: a full open partition is sealed (`VACUUM ANALYZE`,
    then HNSW, ≤ ~30 s) and a new open partition is created.
  - **Compaction:** when minors total 4 M rows, a new major is built offline
    in a separate table, then swapped in one transaction (DETACH the minors,
    ATTACH the major). Queries never see a half-built index; an interrupted
    seal or compaction is restarted.
- **The seal and compaction rule is to `VACUUM (ANALYZE)` before
  `CREATE INDEX`.** Insert-triggered autovacuum colliding with a build made
  one build 14× slower in the full-scale run.
- `semantic.emb256_partitions(name, lo, hi, tier major|minor|open, state, rows, built_at)`
  is the partition manager's state.
- **Query:** one SQL statement over the parent with `hnsw.ef_search ≥ k`
  (pgvector returns at most `ef_search` rows per index scan). Postgres merges
  the per-partition scans.
- **Migration of the existing 37.5 M vectors.** Truncated copy from
  `emb_1024` by `chunk_id` range: `(embedding::real[])[1:256]`, renormalised,
  one range per transaction, resumable. Then seal partition by partition.
  `emb_1024` (484 GB) stays until the new path is validated; dropping it needs
  approval.
- Query embedding moves out of the plpython3u `ollama_embedding()` into the
  application.

### 3.4 Full-text ranking

- **Baseline (works on PG 16 today):** `tsvector` + GIN (`fastupdate = off`),
  `ts_rank_cd`, fused with vector ranks by RRF in SQL.
- **Option, to be decided:** real BM25 inside Postgres with ParadeDB
  `pg_search`. Prebuilt packages exist for **Postgres.app on PostgreSQL 18
  only** (macOS 15/26, arm64); it needs `shared_preload_libraries`, and from
  0.25 it depends on pgvector. It stays inside Postgres (no second system, kept
  in sync by Postgres itself), but it requires upgrading the 1.07 TB server
  from 16 to 18 (`pg_upgrade --link`), and its index adds RAM and disk use.
  **Recommendation:** ship on the baseline; evaluate `pg_search` on a PG 18
  copy of the dev data before deciding (§8).

### 3.5 Server

- Update pgvector 0.5.1 → 0.8.6 (`ALTER EXTENSION vector UPDATE`; the binaries
  are already installed). This is needed for `halfvec` and `subvector`.
- The import profile is built into `bml db profile apply|restore|status`, and
  every bulk command applies and restores it automatically. It costs RAM only
  while an import runs. Per-session settings (`maintenance_work_mem`,
  `synchronous_commit`) need no restart.

## 4. Phased delivery

Each phase ends usable on its own; the Python app keeps working against the
same database throughout.

| Phase | Depends on | Relative size | Delivers |
|---|---|---|---|
| A — Python quick wins | — | S | correct, ~6× faster, resumable PubMed import today |
| B — Rust ingest | A (parity baseline) | M–L | `bml import …`, resumable, all sources |
| C — vectors + search | B (schema), pgvector update | M | 256-d tiered vector index, hybrid search, CLI + MCP |
| D — grading | C | M | relevance + quality/bias grading via bmlib |
| E — review workflow | C, D | L | checkpointed systematic reviews, reports |
| F — GUI | E | L | Tauri desktop app |

### Phase A — quick wins in the current Python app (independent of the port)

1. Fix the four importer defects (keywords, retraction cross-refs, DOI lookup,
   revision order) in `pubmed_bulk_importer.py`, with tests.
2. Migration: GIN `fastupdate = off`; ordered `all_keywords`.
3. Switch the importer to COPY + set-based merge + per-file ledger (≈ 6×).
4. Add the import profile (port `pg_import_profile.py` into `src/`).

Exit criterion: a re-import of the 2025 baseline + updates into
`bmlibrarian_dev` with the fixed importer; keyword coverage ~69 %.

### Phase B — Rust ingest (workspace, `bml-db`, `bml-ingest`, `bml-cli`)

1. Workspace, CI (fmt, clippy, tests), and the migrations runner reading
   `migrations/`.
2. PubMed baseline + daily updates: download with checksums (resumable), the
   parser (from the spike, defects fixed), revision-aware merge, ledger,
   import profile.
3. **Parity harness:** Rust vs the fixed Python parser on a sample of files,
   field for field. This uses bmlib's oracle pattern: committed JSON cases plus
   a regeneration script.
4. medRxiv (bmlib `publications` fetchers) and Europe PMC / PMC OA (bmlib JATS
   reader).

Exit criterion: the full baseline + updates imported into `bmlibrarian_dev`
with a kill/resume test in the middle; checksum parity with Phase A's
importer.

### Phase C — vectors and search (`bml-index`, `bml-search`, `bml-mcp`)

1. pgvector update in dev; `semantic.emb256` + partition manager.
2. A resumable truncated copy of the existing 37.5 M vectors; seal all
   partitions.
3. Chunk queue → embedding service (Ollama F16 now, behind a trait) → open
   partition → seal.
4. Hybrid search SQL (tsvector + halfvec + RRF), filters; CLI `bml search` and
   MCP tools.
5. Recall regression test: fixed query set + exact ground truth, run after
   each seal.

Exit criterion: on the PubMedQA query set over all production vectors,
recall@100 ≥ 0.98 and warm p95 ≤ 250 ms for the vector leg (measured in the
spike: 0.984 and 210 ms), with the old `emb_1024` untouched.

### Phase D — grading (`bml-grade`)

Relevance scoring through the bmlib LLM client; bmlib `quality` tiers and
`transparency` for design, bias and disclosure. Validated against the Python
agents on held-out sets (scoring agreement, quality-tier agreement).

### Phase E — review workflow (`bml-review`)

Systematic-review orchestration with checkpoints and resume; audit trail
compatible with the existing `audit` schema; reports via Typst. Exit
criterion: reproduces a reference review's included-study set (recall
target from `tests/benchmarks`).

### Phase F — GUI

Tauri 2 (web view: pdf.js, markdown, charts). Ports the research, review and
fact-checker plugins. Starts only after E.

### Production cutover

After Phase C, in this order:
1. Apply the migrations to `knowledgebase`.
2. Upgrade pgvector.
3. Build `emb256`.
4. Switch search to the new path.
5. Run old and new side by side for a period.
6. Drop `emb_1024` (frees ~480 GB).

Steps 1–3 and 6 each need explicit approval.

## 5. Testing strategy

- **Parsers:** differential oracles against the Python parsers (bmlib's
  pattern); committed cases; the parity rate is reported, not assumed.
- **Loads:** table checksums (with set-valued columns compared as sets)
  identical between implementations of the same semantics.
- **Resumability:** an automated kill/resume test for every long-running
  command (ingest, vector copy, seal), asserting no loss and no duplicates.
- **Search quality:** the recall regression suite (§4C.5) and the BMLibrarian
  evaluation sets (`benchmarks/embedding_dimension/build_bmlibrarian_eval.py`).
- **Database safety:** tests and spikes write only to `bmlibrarian_dev`; production
  reads are READ ONLY with `statement_timeout`, and every production query is
  checked with `EXPLAIN` first (lesson from §7 of the ingest findings).

## 6. Operational runbook (target CLI)

```
bml db profile status|apply|restore        # import profile (RAM only while importing)
bml import pubmed --baseline|--updates     # resumable; re-run to continue
bml import medrxiv|europepmc|pmc-oa
bml index embed                            # drains the chunk queue into the open partition
bml index seal [--all]                     # VACUUM ANALYZE + HNSW for full open partitions; restartable
bml index compact                          # minors → new 4 M major, swapped in one transaction
bml db prewarm                             # load the HNSW majors into cache before a review session
bml index status                           # partitions, open-partition fill, queue depth
bml search "…" [--from 2015] [--type rct]
bml review run plan.toml                   # checkpointed; re-run resumes
```

## 7. Risks

| Risk | Mitigation |
|---|---|
| Dual maintenance Python ↔ Rust ↔ bmlib | Strangler order; the Python app reads the same schema; parity oracles; generic pieces go to bmlib. |
| Query latency grows with partition count | Measured: 10 × 4 M at p50 145 ms, against 38 × 1 M at p50 265 ms. Tiers plus compaction keep the count low; the open partition stays ≤ 250 k (+~90 ms at 200 k). |
| Cold-cache latency (29 GB of HNSW; RAM goes to inference) | Measured first-pass p95 of 1.2–3.3 s. `pg_prewarm` the majors before review sessions; optionally include them in the import or review profile. |
| GIN cost at 40 M+ rows | `fastupdate = off` measured; partition `document` only if a full-scale import shows degradation. |
| Embedding throughput (13.5 days for 38 M abstracts at fp16) | Reuse the existing 37.5 M vectors; embed only new chunks; a CUDA box optional. |
| PG 16 → 18 upgrade, if `pg_search` is adopted | Rehearse on a copy; `pg_upgrade --link`; keep PG 16 data until validated. |
| bmlib Rust lag (~10 issues behind Python) | Follow bmlib's "port in the same PR" rule for anything the app depends on. |

## 8. Decisions needed from the owner

1. **Repository layout:** a `rust/` workspace in this repo (recommended), or a
   new repository.
2. **Phase A first?** Fixing the Python importer now (recommended: it repairs
   data quality and gives the parity baseline).
3. **BM25:** stay on tsvector (PG 16), or plan a PG 18 + `pg_search` evaluation.
4. **Embedding service:** Ollama F16 (simplest), or an fp16 PyTorch sidecar
   (~20 % faster).
5. **Partition design:** tiers with 4 M majors, a ≤ 250 k open partition and
   compaction, as proposed in §9 (measured). Approve, or prefer 1 M partitions:
   higher recall per `ef_search`, but ~2× latency.
6. **Production steps:** pgvector update, new tables, eventually dropping
   `emb_1024`.

## 9. Full-scale vector run (all 37 478 552 production vectors, measured 2026-10-13)

Source: `spikes/vector-partitions/FINDINGS.md` §6. `halfvec(256)`, HNSW `m = 16`,
`ef_construction = 64`, 300 real PubMedQA queries, exact top-100 ground truth.

| Layout | Build (total, restartable units) | `ef_search` | recall@100 | p50 | p95 |
|---|---|---|---|---|---|
| 38 × 1 M | 78 min (median 90 s each) | 200 | 0.985 | 265 ms | 355 ms |
| 38 × 1 M | | 400 | 0.992 | 451 ms | 581 ms |
| 10 × 4 M | 62 min (median 380 s each) | 200 | 0.971 | 123 ms | 194 ms |
| **10 × 4 M** | | **400** | **0.984** | **145 ms** | **210 ms** |

- **The whole pipeline is resumable.** The read-only extraction from
  production took 20 min, the load 5 min, and the builds about 1 h, against
  ~3 weeks for the old single 1024-d build.
- **Index size:** 29 GB, against 286 GB today.
- **Open partition:** 200 k unindexed rows are scanned exactly in 26 ms on
  their own, and add ~90 ms when attached under the parent.
- **Proposed:** 4 M majors, `ef_search` 400, an open partition of ≤ 250 k
  rows, minor seals, and compaction into new majors (§3.3).
