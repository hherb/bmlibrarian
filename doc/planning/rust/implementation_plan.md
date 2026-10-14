# BMLibrarian in Rust — implementation plan

Status: **approved in principle** (2026-10-13), with the decision to require
**PostgreSQL 18**. Based on the feasibility study and
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
6. **PostgreSQL 18 is the minimum version** (decided 2026-10-13). A local
   Postgres.app 18.1 server runs on port 5532.

## 1. What Phase 0 established

| Question | Answer |
|---|---|
| Rust vs Python for ingest | Design gives 5.8× in either language (COPY + set-based merge + parallelism). Rust adds 1.3–1.45× on top; its parser is 6× faster single-threaded and 35× with 8 threads. The port is justified by architecture (one process, a real pipeline, a single binary, bmlib Rust), not by raw speed. |
| Resumable ingest | Works. One transaction per source file, including its ledger row: SIGKILL mid-run → resume → identical PMID set, no duplicates. |
| Slowdown past a few million rows | Not reproduced with set-based writes, up to 30 M rows. The real culprits were (a) GIN `fastupdate` pending-list flushes (one file took 52 min) and (b) a checkpoint every 2–3 s on default server settings. Fixes: `fastupdate = off` (~14 % faster overall, no stalls) and an import-time server profile. |
| Import-time server profile | Works: `shared_buffers` 32 GB and `max_wal_size` 64 GB during the import, restored afterwards; a state file keeps it across a kill and resume. Forced checkpoints dropped from ~6 per minute to 1–2 per 5 M rows. |
| Vector indexing without multi-week builds | **Measured at full scale:** all 37.5 M production vectors (`halfvec(256)`) in 10 × 4 M partitions, built in 62 min as 10 restartable units (29 GB of HNSW, against 286 GB built in ~3 weeks before). Queries at `ef_search` 400 reach recall@100 0.984 at p50 145 ms / p95 210 ms (§9). Incremental inserts into an indexed partition run at only ~200 rows/s, so new vectors go to a small unindexed *open* partition. |
| Vector type | `halfvec(256)` matches `vector(256)` on recall at 60 % of the index size. |
| Embedding inference | Precision matters, language does not. **Rust in-process llama.cpp (`llama-cpp-2`, Metal, F16 GGUF) matches PyTorch MPS fp16**: ~31 against ~30 docs/s over 4 alternating runs, 256-d cosine 0.99999 against sentence-transformers. Both beat Ollama over HTTP (26.7); candle f32 is 10.5. The existing 37.5 M vectors are truncated, not recomputed (cosine 0.9987 against the HF model at 256 d). |
| Lexical search (PG 18) | **pg_search BM25 (stemmed)**: nDCG@10 0.74–0.77 against 0.38–0.40 for `ts_rank_cd` on the PubMedQA sets, ~20× faster queries. Ingest is 3.7× cheaper than tsvector + GIN (17.1 k against 4.6 k rows/s) at 35 % less space, and the index stays consistent through SIGKILL/resume. Vectors stay the best single method; BM25 adds candidates (`spikes/bm25-pg18/FINDINGS.md`). |
| Production importer defects | Author keywords always dropped (69 % of modern records have them), retraction cross-references never read, DOI lookup can return a reference's DOI, revision handling depends on arrival order, `all_keywords` unordered. |

## 2. Target architecture

```
                     ┌──────────────── bmlibrarian-rs (one binary) ────────────────┐
 PubMed FTP/HTTPS ──▶│ ingest: fetch → parse (rayon) → COPY+merge (tokio) → ledger │
 medRxiv API ───────▶│        per-file transaction · import profile on/off          │
 Europe PMC / PMC OA▶│ fulltext: bmlib FullTextService (JATS first, then PDF)       │
                     │ index:  chunk queue → embed (llama.cpp) → open part. → seal  │
                     │ search: hybrid SQL (pg_search BM25 + halfvec HNSW)           │
                     │ grade:  relevance (LLM) + bmlib quality tiers + transparency │
                     │ review: systematic-review workflow, reports (Typst)          │
                     │ api:    CLI · MCP server (rmcp) · later Tauri GUI            │
                     └───────────────┬──────────────────────────────┬──────────────┘
                                     │ SQL only                     │ HTTP
                               PostgreSQL 18 (:5532)              LLMs (bmlib)
                         (document, ledger, chunks,       embeddings run in-process
                          partitioned halfvec, BM25)       (llama.cpp, Metal/CUDA)
```

### Workspace layout

A Cargo workspace at `rust/` **in this repository** (decided 2026-10-13), so that SQL migrations,
the Python app (which keeps running during the migration) and the Rust code
change together.

| Crate | Responsibility | Depends on |
|---|---|---|
| `bml-db` | Pool (`deadpool-postgres`/`tokio-postgres`), migrations runner (reads `migrations/`), binary COPY helpers, import-profile switcher | pgvector crate |
| `bml-ingest` | Source adapters (PubMed baseline/updates, medRxiv, Europe PMC, PMC OA), parsers, ledger, revision-aware merge | `bml-db`, bmlib `publications`, `fulltext` |
| `bml-index` | Chunking, in-process embedder (`llama-cpp-2`, F16 GGUF pinned by sha256; `metal` / `cuda` features) behind a trait, vector partition manager (open/seal/compact) | `bml-db`, `llama-cpp-2` |
| `bml-search` | Hybrid retrieval: vector top-K ∪ pg_search BM25 top-K as candidates, ordered by weighted RRF (vector 2×); filters (date, type, source) | `bml-db` |
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

- In the current Python app (Phase A, until cutover):
  `ALTER INDEX idx_document_fts SET (fastupdate = off)`.
- **Drop the generated `search_vector` and its GIN**; lexical search moves to
  a `pg_search` index on `(id, title, abstract)`, stemmed (§3.4). Measured on
  PG 18: 17.1 k rows/s ingest with BM25 against 4.6 k with tsvector + GIN. If
  a generated column is ever needed, remember that **PG 18 makes generated
  columns VIRTUAL by default**; write `STORED` explicitly.
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

### 3.4 Lexical search: pg_search BM25 (measured, recommended)

- **ParadeDB `pg_search` 0.26.1**, installed on :5532 (the Postgres.app
  package) and preloaded via `shared_preload_libraries = 'pg_search'` in the
  server's `postgresql.conf`, which Postgres.app merges into its launch flags.
- **Index:** `CREATE INDEX … USING bm25 (id, (title::pdb.simple('stemmer=english',
  'stopwords_language=English')), (abstract::…)) WITH (key_field = 'id')`.
- **Query:** `WHERE abstract ||| :q ORDER BY pdb.score(id) DESC LIMIT k`, plus
  the same on title.
- **Measured** (`spikes/bm25-pg18/FINDINGS.md`):
  - **Quality:** nDCG@10 0.74–0.77 against 0.38–0.40 for `ts_rank_cd` on
    the PubMedQA sets; 0.32 against 0.06 on the research questions.
  - **Speed:** queries take 3–6 ms against 60–112 ms.
  - **Ingest:** 17.1 k rows/s against 4.6 k for tsvector + GIN (3.7×); 8.4
    against 13 GB for 2.4 M rows.
  - **Resumability:** after SIGKILL and resume, the index rows equal the
    table rows.
- **Retrieval design:** vectors are the best single method on every set, so
  BM25 **adds candidates**. The candidate set for LLM scoring is vector top-K
  ∪ BM25 top-K; display order is weighted RRF (vector 2×, measured +0.013
  nDCG@10 on PubMedQA-source and neutral on the graded set). BM25 also covers
  exact terms (gene and drug names, trial IDs).
- `ts_rank_cd` / tsvector are retired. Their only advantage is that they need
  no extension.

### 3.5 Server (Postgres.app 18.1 on :5532)

- **pgvector 0.8.1 is available** (`halfvec`, `subvector`, `l2_normalize`,
  iterative scans).
- `pg_prewarm` is available. `io_method = worker` (PG 18 async I/O; io_uring
  is Linux-only).
- **Settings are defaults:** `shared_buffers` 128 MB, `max_wal_size` 1 GB,
  `maintenance_work_mem` 64 MB, `max_parallel_maintenance_workers` 2. The
  import profile (`bml db profile`) raises them during imports and restores
  them afterwards. `maintenance_work_mem` and parallel workers are set per
  session by the seal and compaction commands (the measured builds used 8 GB
  and 8 workers).
- **Roles:** the superuser is `hherb`; `rwbadmin` (used on :5432) does not
  exist. Create an application role, or point the configuration
  (`POSTGRES_PORT=5532`, user) at the PG 18 server.
- The server hosts other projects' databases, so the import profile's restart
  affects them too. The importer must show that warning.

### 3.6 Moving to PG 18: target database and data carry-over

**State today:**
- **:5432 (PG 16), `knowledgebase`, 1.07 TB:** the live database of the
  Python app. Contents: documents with full texts (Europe PMC 0.73 M, ~15 %
  of PubMed), 37.5 M 1024-d chunk vectors, user data (audit, factcheck,
  evaluations, paper weights, settings), MeSH, unpaywall.
- **:5532 (PG 18), `bmlibrarian`, 115 GB:** a December 2025 test import by
  the current Python importer. 38.35 M PubMed + 83 k medRxiv records with all
  27 migrations applied; **no keywords** (importer defect), no full texts, no
  chunks, no vectors. Update files downloaded to `pubmed25n1585`, the newest
  not yet imported.

**Target:** `bmlibrarian` on :5532, **re-imported** with the fixed importer
(Phase A/B) from the 2026 baseline plus updates. The existing rows were
written by the defective importer, and re-merging all of them is no cheaper
than a resumable re-import (~1–2 h, *projected*).

**Carried over from :5432, read-only and resumable**, each stream in
transactional ranges with a ledger:

| Data | How | Note |
|---|---|---|
| 37.5 M chunk vectors | `(embedding::real[])[1:256]` → `halfvec(256)` into tiered partitions | measured: 20 min extract, ~1 h builds |
| Chunks (definitions/offsets) | copied with their document mapping | needed by the vectors |
| Full texts | `document.full_text` / PDF paths | ~6 M PubMed + 0.42 M Europe PMC records |
| User data (audit, factcheck, evaluations, paper weights, settings, users) | per-schema copy | small; the owner's work |
| MeSH, thesaurus, unpaywall | re-import from source or copy | unpaywall 158 GB: copy only if still used |

**Document IDs differ between the two databases.** Every carried-over row is
remapped through `(source, external_id)` (PMID/DOI) to the PG 18 `document.id`.
Rows that cannot be mapped are counted and reported, never silently dropped.

**Disk budget** (one 7.3 TB volume; **523 GiB free** on 2026-10-13, after the
Phase 0 spike data was deleted):

| Item | Size |
|---|---|
| :5432 `knowledgebase` (stays until cutover) | 1.07 TB |
| :5532 `bmlibrarian` today (rebuilt in place) | 115 GB |
| Phase 0 spike data | deleted 2026-10-13 (~290 GB freed) |
| **Target `bmlibrarian` (*projected*):** documents with full text (~230 GB) + chunks + `halfvec` vectors (~50 GB) + MeSH/user data (small), + unpaywall only if copied (158 GB) | ~300–450 GB |

The target (~300–450 GB) fits in the 523 GiB free, with little headroom, and
unpaywall (158 GB) does not fit on top unless more space is freed. Freeing more means dropping `emb_1024` (484 GB) on
:5432, which only becomes possible once the Python app no longer depends on it
(§ cutover). If unpaywall is needed, plan an external volume or that order.

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

**Status (2026-10-13): items 1–4 implemented and committed.**
- Parse defects fixed (keywords 0 % → 68–69 %, retraction cross-references,
  own DOI only, `date_revised`).
- Migration 031: `ingest.ledger`, `date_revised`, ordered `all_keywords`,
  GIN `fastupdate = off`.
- Write path: COPY + revision-aware merge, one transaction per file,
  resumable.
- Parallel workers (`--workers`): measured 2 729 articles/s with 8 workers
  against 782/s single-process, on PG 18 with default settings.
- Import profile (`--import-profile`, `profile status|apply|restore`).
- `BMLIBRARIAN_ENV_FILE` env selection.
- Docs: `doc/users/pubmed_bulk_import_guide.md`,
  `doc/developers/pubmed_bulk_import_system.md`.

**Baseline exit run (2026-10-13/14), PG 18 :5532, `bmlibrarian_dev`:**
- All 1 334 baseline files are in `ingest.ledger`: 39 994 988 records,
  10.5 h summed import time (8 workers, import profile active), 0 import
  errors.
- **Imports ran while files were still downloading**, in 30-minute rounds that
  each skipped committed files, so the import was effectively stopped and
  resumed about 20 times. The final run restored the day-to-day settings
  (shared_buffers 128 MB, max_wal_size 1 GB).
- Keywords: 70.5 % of records from 2020 on, 38.5 % for the 2010s, 1–2 % for
  the 1990s and 2000s (author keywords were rare then). 32.3 % overall.
- 59 958 records flagged as retracted; `date_revised` on 100 %.
- **Downloads moved from FTP to HTTPS** (`importers/ncbi_https.py`). The NCBI
  FTP stream was found to rewind mid-transfer and deliver oversized or
  corrupted files; HTTPS with `.part` + Range resume + NCBI MD5 checks
  downloaded all 1 334 files (51 GB) without a single checksum failure.
  **Phase B's downloader must also use HTTPS with MD5 checks, not FTP.**

**Updates (2026-10-14):** all 347 update files (pubmed26n1335–1681), 6.9 M
records, 0 errors; 41 246 334 PubMed documents, revisions up to 2026-10-13.
Without the import profile, so no server restart.

**Withdrawals (migration 032):** `DeleteCitation` was never handled before.
Withdrawn PMIDs are now recorded in `ingest.withdrawn_pmid` and marked in
`document.withdrawn`, not deleted, so references stay valid. The
`database.py` searches exclude them, and marking works in any file order. The
backfill over the 2026 update files recorded 10 930 PMIDs and marked 7 622
documents. **Phase B must carry the same semantics.**

**Phase A exit criterion: met.**

1. Fix the four importer defects (keywords, retraction cross-refs, DOI lookup,
   revision order) in `pubmed_bulk_importer.py`, with tests.
2. Migration (for the Python app's current schema on :5432 until cutover):
   GIN `fastupdate = off`; ordered `all_keywords`.
3. Switch the importer to COPY + set-based merge + per-file ledger (≈ 6×).
4. Add the import profile (port `pg_import_profile.py` into `src/`).

Exit criterion: a re-import of the baseline + updates with the fixed importer
into a dev database **on the PG 18 server** (:5532); keyword coverage ~69 % of
modern records.

### Phase B — Rust ingest (workspace, `bml-db`, `bml-ingest`, `bml-cli`)

1. Workspace, CI (fmt, clippy, tests), and the migrations runner reading
   `migrations/`.
2. PubMed baseline + daily updates: HTTPS download with NCBI MD5 checks (resumable, no FTP), the
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
3. Chunk queue → in-process embedder (`llama-cpp-2`, F16 GGUF, behind a trait)
   → open partition → seal.
4. Hybrid retrieval (pg_search BM25 ∪ halfvec HNSW candidates, weighted RRF
   order), filters; CLI `bml search` and MCP tools.
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

### Production cutover (PG 16 :5432 → PG 18 :5532)

After Phase C, in this order:
1. ~~Delete the Phase 0 spike data~~ (done 2026-10-13, ~290 GB freed).
2. Rebuild `bmlibrarian` on :5532 with the Rust importer (Phase B).
3. Carry over vectors, chunks, full texts and user data from `knowledgebase`
   (read-only, remapped, resumable; §3.6).
4. Point the Python app's configuration at :5532/`bmlibrarian`. Its query
   embedding must then produce 256-d query vectors (replacing
   `ollama_embedding()` 1024-d).
5. Run old and new side by side, read-only on :5432, for a period.
6. Retire `knowledgebase` on :5432 (frees ~1.07 TB).

Steps 4 and 6 need explicit approval.

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
| BM25 index cost at 40 M+ rows | Measured flat to 2.4 M on PG 18 (relational ingest was flat to 30 M on PG 16); verify on the full re-import; partition `document` only if degradation appears. |
| Embedding throughput (13.5 days for 38 M abstracts at fp16) | Reuse the existing 37.5 M vectors; embed only new chunks; a CUDA box optional. |
| Disk space during the move (both databases on one volume; 523 GiB free) | Spike data already deleted; carry data over without unpaywall unless space is freed; consider an external volume; retire :5432 only after validation. |
| ID remapping errors when carrying data to PG 18 | Map by `(source, external_id)`; count and report unmapped rows; checksum carried-over vectors against the source. |
| `pg_search` maturity (pre-1.0; index format changes between versions) | Pin the version; reindex is a bounded, resumable job per table; tsvector + GIN remains a measured fallback. |
| llama.cpp API and GGUF churn (Ollama's old GGUF no longer loads in current llama.cpp) | Pin `llama-cpp-2` and the GGUF (repository + revision + sha256); re-verify cosine against the reference on every upgrade. |
| The import profile's restart affects other databases on :5532 | The importer warns, refuses while other databases have active sessions unless `--force`, and runs imports in scheduled windows. |
| bmlib Rust lag (~10 issues behind Python) | Follow bmlib's "port in the same PR" rule for anything the app depends on. |

## 8. Decisions

**Decided (2026-10-13):**
- **PostgreSQL 18 (:5532)** is the target and minimum.
- **Rust code** lives in a `rust/` workspace in this repository.
- **Lexical search:** `pg_search` BM25 is the only lexical index;
  tsvector + GIN are dropped from the new schema (§3.4). It is installed and
  preloaded on :5532.
- **Embeddings** run in-process via `llama-cpp-2` (F16 GGUF, pinned) (§2,
  `bml-index`).
- **Vectors:** the resumable tiered partition layout (§3.3).
- **Order:** start with **Phase A** (fix the Python importer), targeting
  PG 18.
- **Unpaywall:** refresh from a current snapshot if obtainable (newer OA
  locations, no ID remapping needed); otherwise carry it over from :5432.
- **Database role:** use the existing `bmlibrarian` role on :5532, created by
  the setup wizard; credentials are in `~/.bmlibrarian/.env_pg18` (mode 600,
  git-ignored copy in the repo). It is currently a **superuser**. Before
  production, split it into an unprivileged application role and an admin
  connection for the import profile and `CREATE EXTENSION`.

**Still open:** none blocking Phase A.

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
