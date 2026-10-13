# BMLibrarian in Rust — feasibility and port plan

Status: **exploration**, started 2026-10-12. The resulting plan:
[`implementation_plan.md`](implementation_plan.md). Phase 0 measurements were
completed on 2026-10-12; see [Phase 0 results](#phase-0-results-2026-10-12)
and `spikes/*/FINDINGS.md`.

## Goal

A from-scratch Rust implementation of BMLibrarian, built on the Rust port of
bmlib (`bmlib` crate, `/Users/hherb/src/bmlib/rust/bmlib`), with three
priorities:

1. **A local mirror** of PubMed, medRxiv and Europe PMC abstracts, plus as many
   full texts as possible, kept current.
2. **Hybrid indexing** (BM25 + dense vectors), fast enough for comprehensive
   literature reviews.
3. **Grading** of matched papers for relevance and quality/risk of bias.

The rest of the current BMLibrarian features are then ported, and improved,
one step at a time.

## Decided constraints

Set by the project owner (2026-10-12). They override any recommendation below
that conflicts with them.

1. **Embeddings are stored at 256 dimensions**: arctic-embed-l-v2.0 truncated
   and L2-renormalised, for disk and indexing reasons.
2. **PostgreSQL is the only data and index system.** No external search engine
   (tantivy, OpenSearch, a separate vector DB). A second index means another
   process needing RAM, keeping two copies in sync, losing the Postgres
   ecosystem, and giving up single-SQL queries. BM25 and vectors both live in
   Postgres.
3. **Every long-running step can be stopped and resumed at any time**, even if
   that makes it slower. There must be no multi-day, all-or-nothing step: a
   bulk index build after import was abandoned because it took close to three
   weeks with 1024-d vectors and could not be interrupted. Throughput is also
   known to degrade badly after the first few million rows with indexes
   maintained during import.

## Verdict

**Feasible.** Nothing in BMLibrarian's core needs Python. The obstacles are
the size of the job, a few ecosystem gaps (GUI, stealth browser automation,
ML layout analysis of PDFs, plotting), and one important caveat: **most of
today's import and indexing slowness is architectural, not a matter of
language.** A Rust rewrite pays off only if it also fixes the architecture.
Phase 0 measures how much of the gain is due to Rust itself, before any
commitment to a rewrite.

## 1. Where the time goes today

Measured or documented in the current system (2026-10-12):

| Bottleneck | Evidence | Language-bound? |
|---|---|---|
| Row-at-a-time writes | `pubmed_bulk_importer._store_article_batch`: SELECT + INSERT/UPDATE per article, commit per 100; transparency metadata adds a second per-row lookup + insert. No COPY or `executemany` in any importer. | No. Python can use COPY too. |
| Embedding throughput (inference cost is the same at 256 d) | arctic-embed-l-v2.0 on Apple-Silicon MPS: 48 629 abstracts in ~53 min (~15 docs/s) during the 2026-10-12 benchmark. At that rate, 38 M abstracts take **~29 days**, and full-text chunks come on top. 6.7 M documents wait in `semantic.chunk_queue`. Ollama on CPU: 5–10 embeddings/s. | No. GPU/model-bound. |
| Vector index | 37.5 M × 1024-d vectors: `emb_1024` 484 GB, of which HNSW 286 GB. A documented 263 s query (m=6), and 4–8 h index rebuilds. pgvector is still 0.5.1. | No. Storage design (see 256-d truncation, `doc/EMBEDDING_MODEL_EVALUATION_2026-10.md`). |
| Query embedding inside Postgres | `ollama_embedding()` is plpython3u, with a hard-coded model. | No, but this is a design smell. Embed in the application. |
| Politeness limits | PMC/Europe PMC packages: configurable delays (default 2 min). NCBI rate limits. | No. |
| CPU parsing | `ET.iterparse` + per-element Python objects; one import thread. | **Yes**. The GIL prevents parallel parsing in one process. |

The existing **37.5 M chunk vectors can be reused**: they match the
HuggingFace arctic model (median cosine 0.9985, measured 2026-10-12), so a new
system can truncate them to 256 d instead of re-embedding.

Database snapshot (2026-10-12): 1.07 TB. PubMed ≈ 40.2 M documents (last import
2025-12-27, ~15 % with full text). Europe PMC ≈ 0.73 M (58 % with full text).
medRxiv ≈ 65 k (last added 2025-07-14). The mirror is ~10 months stale.

## 2. What exists to build on

### bmlib Rust port (crate `bmlib` 0.2.0 on crates.io, ~44.5 k lines, ~1 000 tests)

- **Ported and current:**
  - `quality/`: all four tiers (metadata filter, LLM study classifier,
    quality agent, Cochrane assessor), with the regex extractors.
  - `transparency/`: CrossRef, Europe PMC, OpenAlex, ClinicalTrials.gov and
    PubMed enrichment.
  - `citations/`, `context_processor/`, `agents/` base.
  - `db/`: SQLite always; PostgreSQL behind a feature flag.
- **Ported, lagging Python by about ten issues:**
  - `fulltext/`: tier chain Europe PMC → NCBI PMC → Europe PMC PDF →
    Unpaywall → doi.org, plus the JATS reader and PDFium-based PDF text with
    section segmentation.
  - `publications/`: date-window sync fetchers for PubMed, bioRxiv/medRxiv
    and OpenAlex.
- **LLM:** an OpenAI-compatible protocol (OpenAI, DeepSeek, Mistral, Gemini,
  Ollama) plus Anthropic `/v1/messages`, with tools, `json_mode` and `think`.
  No streaming, no embeddings, no model listing.
- **Architecture:** fully synchronous (`ureq`, blocking `postgres`). The
  db-async spike concluded: keep `Db` sync, and bridge it with a pool plus
  `spawn_blocking`. There is no internal parallelism and no logging crate.
- **Missing in both languages:** embeddings generation, vector search,
  BM25/FTS, bulk import (PubMed baseline, MECA), query-driven PubMed search, a
  Europe PMC fetcher, OpenAthens and browser automation. bmlib's own porting
  analysis says "do not port" for the browser downloader and OpenAthens.

**Grading (relevance + quality/bias) is the best-supported part of the plan.
The mirror and the index, which are the new system's focus, have to be built
from scratch.**

### Scope already covered by bmlib (Python 0.10 and Rust)

Much of BMLibrarian's functionality now lives in the shared **bmlib** library,
in both its Python and its Rust versions. A Rust BMLibrarian **uses** these
modules instead of porting them:

| BMLibrarian feature | bmlib module (Python and Rust) |
|---|---|
| Study design / quality grading, Cochrane risk-of-bias assessor, paper-weight extractors and rubrics | `quality/` (metadata filter → LLM classifier → quality agent → Cochrane assessor) |
| Transparency / undisclosed-bias analysis | `transparency/` |
| Full-text retrieval tiers, JATS → structured text, PDF text + section segmentation | `fulltext/` |
| Citation formatting / parsing | `citations/` |
| Map-reduce over long documents | `context_processor/` |
| LLM providers, JSON repair, token/cost tracking, agent base | `llm/`, `agents/` |
| Date-window sync of PubMed, bioRxiv/medRxiv, OpenAlex; Retraction Watch | `publications/` |

Still BMLibrarian-only (and not yet in bmlib in either language), so the new
port has to write them:

- bulk ingest (PubMed baseline/updates, Europe PMC / PMC OA packages)
- embeddings and the hybrid index
- the PDF-discovery stack (bmlib porting analysis #12)
- live PubMed search (#13)
- ClinicalTrials.gov (#14) and MeSH (#21/#24)
- the prompt-driven agents (#18: query, scoring, citation, reporting,
  counterfactual, editor, PICO, PRISMA 2020)
- the systematic-review orchestration
- audit trail, users/settings
- the GUI

Where a piece is generic, the preferred home is **bmlib itself**, behind
bmlib's parity-oracle discipline, rather than the new app. Candidates are the
discovery stack, PubMed search, MeSH, ClinicalTrials.gov, embeddings in the LLM
client, and possibly the bulk PubMed parser. Python consumers (BioMedicalNews,
bmlibrarian_lite) then benefit as well.

### Current BMLibrarian (Python)

| | Size |
|---|---|
| `src/bmlibrarian` | ~207 k lines, of which ~43 k are Flet GUI already slated for deletion |
| Qt GUI | ~47 k lines (QWidgets + QtPdf; no QtWebEngine/QtCharts) |
| Agents | 19, incl. the systematic-review package (17.9 k lines) |
| Tests | 161 files, ~65 k lines, ~3 200 tests |
| Database | 16 schemas, 27 migrations, 92 SQL functions |
| bmlib usage | the LLM layer only; ~7 k lines duplicate code now in bmlib 0.10 |

Unused direct dependencies found along the way: opencv-python, torchvision
(added 2026-10-12 for EmbeddingGemma 2, which was then rejected), qtawesome,
`transformers` as a direct pin, and pymupdf-layout (scripts only).

## 3. Rust ecosystem (as of 2026-10)

### Production-ready, and better than or equal to Python

| Need | Crate(s) |
|---|---|
| Streaming XML (PubMed, JATS) | `quick-xml` 0.42 (pull parser), `roxmltree` 0.21 (DOM; ~2× libxml2 on one core) + `flate2`/zlib-rs, `rayon` |
| Postgres bulk load | `tokio-postgres` 0.7 `BinaryCopyInWriter`, `pgvector` 0.4 (Vector, HalfVector, Bit) |
| BM25 | `tantivy` 0.26: **excluded by constraint 2**; the in-Postgres equivalent is ParadeDB `pg_search` (built on tantivy) |
| Embedded vector stores | `lancedb` 0.40, `usearch` 2.26 |
| HTTP / concurrency | `tokio`, `reqwest`, `governor` (rate limiting), `rayon` |
| LLM | `ollama-rs` 0.3, `async-openai` 0.42; bmlib's own Anthropic client |
| MCP server | `rmcp` 3.5 (official SDK) |
| Reports | `typst` 0.15 as a library (better typography than ReportLab) |
| Tokenizers | HF `tokenizers` (the Python package wraps this crate) |

### Usable with gaps, or needing a bridge

| Capability | Status | Bridge |
|---|---|---|
| Desktop GUI with a PDF pane, HTML and charts | No Rust QWidgets bindings. cxx-qt 0.10 is QML-only. egui, iced, slint and gpui have no HTML and no real PDF viewer. | **Tauri 2** (web view, pdf.js, JS charts), or cxx-qt + QML (QtPdf) |
| Stealth / Cloudflare browser automation | `chromiumoxide`/`headless_chrome` handle the CDP basics. Stealth crates are small and unproven. | Python/Node sidecar (Playwright + stealth), or drop the feature. A headful Chrome over CDP is fine for the OpenAthens login. |
| ML layout analysis of PDFs (docling-grade) | docling.rs 2.15 and xberg 1.3 exist, but are very new and run ONNX Runtime (C++) underneath | `ort`, or a Python sidecar. Prefer JATS XML wherever possible. |
| PDF text with fonts | PDFium (`pdfium-render`, already in bmlib) or MuPDF (`mupdf` 0.8, AGPL). Neither is thread-safe. | One process per worker for throughput |
| arctic-embed on Metal | candle 0.11 has `xlm_roberta`; throughput vs PyTorch MPS is **unmeasured** | Ollama/llama.cpp, or HF text-embeddings-inference (Rust, candle-based) as a server |
| Statistics plots (seaborn-grade) | `plotters` has stalled; `statrs` has no contingency tests or kappa (easy to write) | Vega/ECharts in the web view, or Typst |
| Anthropic API | No official Rust SDK. Several community crates name `anthropics/*` repos that 404; **do not use them**. | bmlib's own client, or rig-core |
| Biomedical NLP (scispaCy-class) | Nothing | ONNX models via `ort`, or skip |

### Not realistically doable in pure Rust today

1. A QWidgets-style native GUI at PySide6 parity, including the PDF pane.
2. Anti-bot/Cloudflare-resistant browser automation.
3. ML layout analysis without a C++ runtime (ONNX Runtime).
4. matplotlib/seaborn-quality publication plots.

Everything else has a production-ready Rust path.

## 4. Barriers, ranked

1. **Size of the job.** BMLibrarian has about 164 k live Python lines and
   about 3 200 tests, but **a large share is already covered by bmlib**
   (section 2): grading, transparency, full text, citations, LLM. What
   remains is the ingest/index core (new code, and the focus anyway), the
   agents and review orchestration, the discovery stack, and the GUI. bmlib's
   port ran close to 1:1 in lines (41.6 k → 44.5 k) and needed a
   differential-oracle harness to prove parity. Expect the same discipline for
   anything that must match the Python behaviour. Parity-proofing, not typing,
   is the dominant cost.
2. **bmlib Rust is missing the new system's focus**: async I/O, embeddings,
   search and bulk ingest. Its synchronous design is deliberate, so the new
   app adds a tokio layer with `spawn_blocking` around bmlib calls. Dual
   maintenance (Python bmlib ↔ Rust bmlib ↔ new app) needs the oracle
   discipline bmlib already uses.
3. **GUI**: a rewrite, not a port.
4. **Full-text acquisition behind paywalls**: see the stealth gap above.
5. **PDF-only full texts** need layout analysis. Mitigate by getting full text
   from JATS first (Europe PMC / PMC OA), with PDFs as the fallback.
6. **Embedding throughput** is a hardware question in any language.
   Truncating to 256 d cuts storage and index cost, but not inference time.
7. **Infrastructure**: pgvector 0.5.1 has no `subvector`, `l2_normalize` or
   `halfvec` (0.7+). PostgreSQL TLS is not implemented in bmlib Rust. The
   mirror is stale.

## 5. Recommended architecture (target)

- **System of record: PostgreSQL**, keeping the current schema during
  migration. Upgrade pgvector to ≥ 0.8 and rebuild HNSW.
- **Embedding size: 256 dimensions (decided 2026-10-12).** Disk and indexing
  constraints rule out the full 1024-d vectors. Arctic-embed-l-v2.0, truncated
  to its first 256 dims and L2-renormalised, was non-inferior to 1024 d on
  every evaluation set with ≥ 300 queries
  (`doc/EMBEDDING_MODEL_EVALUATION_2026-10.md`). The existing 37.5 M vectors
  are truncated in place, not re-embedded. Every new vector is stored at
  256 d, document and query alike; 1024-d vectors are never persisted.
  `halfvec(256)` is an optional further 2×, to be benchmarked first.
- **BM25 inside Postgres.** Today that is `tsvector` + GIN with
  `ts_rank_cd`. A real BM25 extension (ParadeDB `pg_search`, `pg_textsearch`,
  VectorChord-BM25) would keep everything in Postgres, but none ships with
  Postgres.app, so each would have to be built and installed; evaluate before
  committing. Hybrid fusion (RRF) runs in SQL, as `semantic.hybrid_chunksearch_document`
  already does.
- **Resumable everything (constraint 3):**
  - *Ingest:* one transaction per source file, holding the COPY, the
    set-based merge **and** the file's ledger row. A kill at any moment loses
    at most the files in flight; a restart skips committed files. Verified in
    Phase 0c (SIGKILL mid-run, then resume: identical PMID set, no
    duplicates).
  - *Indexes:* never one big deferred build. Keep each index small enough to
    stay in RAM by **partitioning**:
    - `document` by source and publication year (or PMID range);
    - vectors in partitions of a few million rows, each with its own HNSW
      index.

    A partition's index build is then a bounded unit of work (~90 s per 1 M
    `halfvec(256)`, measured), and it can be redone alone. New vectors go
    into one small **open** partition without an HNSW index (COPY speed;
    queried exactly). When it fills, it is **sealed** by building its index.
    Measured: inserting into an indexed partition runs at only ~200 rows/s,
    against ~10 k/s for a build. pgvector queries over a partitioned table
    merge the per-partition index scans (`Merge Append`), which also raises
    recall.
  - *Derived data* (tsvector, chunks, embeddings) are filled from work
    queues (`semantic.chunk_queue` style). Each batch commits with its queue
    rows, so these steps are resumable and can run behind ingest.
- **An import-time server profile, not permanent tuning.** The server runs
  on Postgres.app defaults (`shared_buffers` 128 MB on a 128 GB machine,
  `max_wal_size` 1 GB), which caused a checkpoint every 2–3 s during
  loading. Day-to-day RAM is reserved for model inference, so the importer
  applies an import profile (large `shared_buffers` and WAL) at start and
  restores the day-to-day profile at the end. A state file keeps the profile
  through a killed and resumed import, and a `restore` command cleans up
  after an abandoned one. Approved 2026-10-12; implemented in the spike as
  `pg_import_profile.py`.
- **Ingest pipeline**: tokio for I/O, a rayon pool for parsing, bounded
  channels for backpressure. Use binary COPY into staging tables, then a
  set-based merge (`INSERT … ON CONFLICT`).
- **Embeddings**: behind a trait, with backends chosen by Phase 0 (candle,
  Ollama, TEI). One GPU actor batches requests. Query embedding moves out of
  plpython3u.
- **Full text**: JATS bulk (Europe PMC OA, PMC OA) → bmlib `FullTextService`
  tier chain → OA PDFs via PDFium in worker processes → optional institutional
  sidecar.
- **Grading**: bmlib `quality` tiers + `transparency`, plus relevance scoring
  through the bmlib LLM client.
- **Interfaces**: CLI and an MCP server (`rmcp`) first; Tauri GUI last.

## 6. Phased plan

**Migrate gradually instead of rewriting everything at once.** The Rust
backend writes the existing schema, so the Python GUI and agents keep working
throughout.

| Phase | Scope | Exit criterion |
|---|---|---|
| **0 — measure** | Ingest spike, embedding spike (below) | Go/no-go numbers recorded in FINDINGS.md |
| 1 — mirror + index | PubMed baseline + updates, medRxiv, Europe PMC (JATS first); pgvector upgrade; existing vectors truncated to `vector(256)`, new vectors embedded straight to 256 d; Postgres BM25 (tsvector/GIN, or a BM25 extension if adopted); partitioned tables and vector partitions; resumable ingest ledger; hybrid search CLI + MCP server | Fresh mirror; hybrid search latency < 1 s at top-100 |
| 2 — grading | Relevance scoring; bmlib quality tiers; transparency | Agreement with the Python agents on a held-out set |
| 3 — review workflow | Systematic-review agent, reporting (Typst), audit trail | Reproduces a reference review |
| 4 — GUI | Tauri 2 | Feature parity for research + review plugins |

## Phase 0 — measure before rewriting

Two spikes, under `spikes/` in this repository. Each has a `FINDINGS.md`.
**Never touch `knowledgebase`.** Writes go only to schema `spike_ingest` in
`bmlibrarian_dev`.

### 0a. PubMed ingest (`spikes/pubmed-ingest/`)

Input: local 2025 baseline files (`~/knowledgebase/pubmed_data/baseline`,
1 274 files, 46 GB). A sample of N consecutive files, starting with 4, then
more.

What each variant does, so that language and design are measured separately:

| Variant | Parse | Load |
|---|---|---|
| P1 Python as-is | `PubMedBulkImporter._parse_article` (ET.iterparse) | current pattern: SELECT + INSERT per row, commit per 100, per-row transparency lookup + insert |
| P2 Python + COPY | same parser | psycopg3 COPY into staging + set-based merge |
| P3 Python, process pool | parser in N processes | COPY as P2 |
| R1 Rust, 1 thread | quick-xml port of `_parse_article` | binary COPY into staging + same set-based merge |
| R2 Rust, rayon | as R1, N threads | as R1 |

The target table is a copy of `public.document`'s columns, indexes, generated
`search_vector` and `update_all_keywords` trigger, plus
`transparency.document_metadata`. The FK to `sources`/`categories` is
replaced by plain integers. Each variant runs into a freshly truncated table,
both as a cold insert and as a second pass that exercises the update path.

Measured: parse-only articles/s, end-to-end articles/s, peak RSS, CPU
utilisation. **Parity check**: the Rust output and P1's parsed dicts must agree
field by field on the sample; the mismatch rate is reported.

Go/no-go: the Rust share of the speed-up is R2 vs P3 (both on the best
design). If it is < 2×, Rust is not justified *for ingest* alone.

### 0b. Embedding throughput (`spikes/embedding-throughput/`)

Same 2 000 abstracts (drawn from the 2026-10-12 evaluation corpus) for every
backend, on this Mac:

- sentence-transformers on MPS (current reference; batch sizes 16/32/64)
- Ollama `snowflake-arctic-embed2` via `bmlibrarian.llm` (batch embed)
- Rust candle `xlm_roberta` on Metal (CLS pooling, normalise, 256-d truncation)

All backends are compared at the production size: the first 256 dims, then
L2-renormalised. Measured: docs/s, tokens/s, and 256-d cosine agreement with
sentence-transformers (must be ≥ 0.99 median). TEI is candle-based, so the candle number stands in
for it; installing TEI is optional.

Go/no-go: pick the embedding backend for Phase 1, and project wall-clock time
for the 38 M-abstract backlog.

## Phase 0 results (2026-10-12)

Details: `spikes/pubmed-ingest/FINDINGS.md`, `spikes/embedding-throughput/FINDINGS.md`.

### 0a ingest: design gives 5.8×, Rust a further 1.3–1.45×

8 modern baseline files (240 k records) loaded into a copy of `document` with
all indexes, the generated tsvector and the keyword trigger. The Rust parser
matches the Python one field for field on 100 % of articles. Given the same
design, both languages write byte-identical tables.

| Variant | articles/s (cold) | Full baseline, projected |
|---|---|---|
| Today's importer (row at a time) | 1 098 | 9.7 h |
| Python, COPY + set-based merge, 8 processes | 6 386 | 1.7 h |
| Rust, binary COPY + same merge, 8 threads | 9 274 | 1.1 h |
| Rust, no Postgres FTS (tsvector/GIN dropped) | 35 813 | 0.3 h |
| Rust parse only, 8 threads (Python: 2 730/s) | 94 922 | 0.1 h |

**The go/no-go criterion (Rust ≥ 2× over the best Python design) is not
met for ingest alone: 1.45× cold, 1.3× warm.** Once writes are set-based,
Postgres's own work (to_tsvector, GIN, btree, trigger) dominates. Without the
generated tsvector + GIN, the relational load runs ~4× faster. With BM25
staying in Postgres (constraint 2), that cost has to be managed inside
Postgres: compute the tsvector from a resumable queue behind ingest,
partition so each GIN stays small, and tune the server.

### 0b embeddings: precision matters, language does not

arctic-embed-l-v2.0 on the M3 Max, 2 000 abstracts, compared at 256 d. Every
backend agrees to cosine ≥ 0.9995.

| Backend | docs/s |
|---|---|
| PyTorch MPS f16 (sentence-transformers) | **32.7** |
| Ollama F16 GGUF | 26.7 |
| PyTorch MPS f32 | 16.9 |
| Rust candle Metal f32 (f16 unsupported for XLM-R) | 10.5 |

### Recommendations from Phase 0 (pending your approval; 256 d is already decided)

1. **The port proceeds for its architecture, not for raw speed.** That means
   one process with parallel parsing, COPY, resumable work queues and
   backpressure, a single binary, and bmlib Rust for grading. The measured
   speed-ups are modest once the Python design is fixed. If the port stalls,
   the same 5.8× is available in Python by changing the write pattern.
2. **Keep FTS in Postgres** (per constraint 2; the earlier tantivy idea is
   superseded). After the GIN test, keep the generated `search_vector` and set
   the GIN to `fastupdate = off`: ingest with full FTS ran at ~9.9 k rows/s
   without stalls, so a queue-filled tsvector is unnecessary. Real BM25 via
   ParadeDB `pg_search` is possible only on Postgres.app 18, so it is an open
   decision (see `implementation_plan.md` §3.4).
3. **Embedding stays a service behind a trait**, in half precision: Ollama now
   (already F16), or an fp16 PyTorch sidecar if throughput matters more.
   candle is revisited only if it gains f16 for XLM-R. Vectors are stored at
   256 d; the existing 37.5 M are truncated, not recomputed.
4. **Revision semantics become explicit.** When a PMID reappears, the newest
   revision (`DateRevised`/`Version`) wins, instead of whichever arrives
   last.
5. **Fix the production importer's parse defects** in Python now and in any
   port: author keywords always dropped (69 % of modern records have them),
   retraction cross-references never read, DOI lookup able to pick up a cited
   reference's DOI, unordered `all_keywords`.

### Next measurements (before Phase 1 code)

- **0c, long run: done.** See `spikes/pubmed-ingest/FINDINGS.md` §7.
  - The kill/resume test passed (SIGKILL after 28/80 files; the resumed run
    had an identical PMID set and no duplicates).
  - 0 → 10 M rows (old baseline files) loaded at 30–46 k/s. 10 → 20 M rows
    (modern files appended) loaded at a **flat ~15 k/s**, with production FTS
    on default server settings. No steady degradation.
  - One file stalled for 52 min, most likely a GIN `fastupdate`
    pending-list flush paid by one inserter.
  - The server log shows 735 WAL-triggered checkpoints in ~2 h.
- **Controlled GIN test and import profile: done** (FINDINGS §8).
  - `fastupdate = off` is ~14 % faster in total once the pending-list
    flush that `on` defers is counted (148 s, 6.6 GB). The worst file was
    51 s, against 176 s with `on` and 3 112 s in §7. **Use
    `fastupdate = off` for the FTS GIN.**
  - The server **import profile** (`spikes/pubmed-ingest/pg_import_profile.py`:
    `shared_buffers` 32 GB, `max_wal_size` 64 GB, applied with
    `ALTER SYSTEM` plus a restart, restored afterwards, kept across a killed
    and resumed run through a state file) cuts forced checkpoints from ~6 per
    minute to 1–2 per 5 M rows.
  - RAM is only borrowed while an import runs (owner requirement:
    day-to-day RAM goes to inference).
- Partitioning: the same long run into a `document` partitioned by
  PMID range, to see whether bounded indexes keep throughput flat.
- Queue-driven tsvector fill behind ingest: throughput and resumability.
- **Vector partitions: done** (`spikes/vector-partitions/FINDINGS.md`).
  5 M production vectors at 256 d, pgvector 0.8.6 in `bmlibrarian_dev`:
  - **Builds:** one HNSW per 1 M partition takes ~90 s (`halfvec`) to
    ~105 s (`vector`). Projected for 37.5 M: ~1 h of index builds in total,
    as 38 independent, restartable units, against ~3 weeks for the old 1024-d
    build. The old build most likely outgrew `maintenance_work_mem`.
  - **Recall** with 5 partitions at `ef_search` 200: recall@100 0.973 at a
    p50 of 36–39 ms. `halfvec` gives the same recall as `vector` with a 40 %
    smaller index.
  - **Incremental inserts** into an indexed partition run at only ~200
    rows/s, 46× slower than building, which leads to the design below.
  - **Design: "open + sealed" partitions.** New vectors go into a small,
    unindexed open partition, which queries scan exactly. When it fills, it
    is sealed with its own bounded index build.
  - **Still to measure:** query latency at the full partition count, and the
    best partition size (1–4 M).
