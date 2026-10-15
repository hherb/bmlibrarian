# Phase 0a findings — PubMed ingest (2026-10-12)

Machine: Apple M3 Max (12 performance + 4 efficiency cores), PostgreSQL 16.15
(Postgres.app, local). Input: 8 modern 2025-baseline files, `pubmed25n1101`–`1108`
(240 000 records, 239 916 distinct PMIDs). Target: `spike_ingest` in
`bmlibrarian_dev`, a copy of `public.document` + `transparency.document_metadata`
with all 10 indexes, the generated `search_vector` and the
`update_all_keywords` trigger. Raw data: `results/run_*.jsonl`.

## 1. Parity

The Rust parser (`rust/src/parse.rs`) matches the production Python parser
**field for field on 100 %** of articles. Checked: file 0001, 30 000 old
records; file 1101, 29 993 modern PMIDs with structured abstracts, inline
markup and grants.

Loaded tables, compared by checksum (`all_keywords` compared as a set; see
§5.4):

- The **same design gives byte-identical tables in Python and Rust**:
  P2 = R1 and P3 = R2, cold and warm.
- Across designs, all 239 850 non-duplicated PMIDs are identical, metadata
  included.
- The only differences are the 66 PMIDs that occur more than once with
  different content (PubMed revisions; 50 repeat within a file, 16 across
  files). Each write pattern resolves revisions differently (§5.5).

## 2. Parse throughput (no database)

| Variant | articles/s | vs Python |
|---|---|---|
| Python `_parse_article` (ET.iterparse), 1 core | 2 730 | 1× |
| Rust, 1 thread | 17 034 | 6.2× |
| Rust, 4 threads | 41 582 | 15× |
| Rust, 8 threads | 94 922 | 35× |
| Rust, 12 threads (capped by 8 files) | 99 940 | 37× |

Peak RSS, one file: Python 93 MB; Rust 265 MB (whole file decompressed in
memory, by design).

## 3. End-to-end load (parse + write + indexes + trigger)

| Variant | Design | Cold articles/s | Warm (update path) articles/s |
|---|---|---|---|
| P1 | production: SELECT + INSERT/UPDATE per row, commit per 100, per-row metadata upsert | 1 098 | 1 008 |
| P2 | Python, COPY → staging → set-based merge, 1 process | 1 469 | 1 154 |
| P3 | as P2, 8 processes | 6 386 | 4 712 |
| R1 | Rust, binary COPY → same merge SQL, 1 thread | 2 872 | 1 843 |
| R2 | as R1, 8 threads | **9 274** | **6 116** |
| R2 bare | R2 into a table without secondary indexes, trigger or `search_vector` | **35 813** | — |

The bare variant needs indexes and derived columns rebuilt afterwards:
`all_keywords` in 4.7 s, `search_vector` added (a table rewrite) in 36.6 s,
the 8 indexes plus trigger in 14.2 s. That is 62 s in total versus 25.9 s
for the indexed R2 load, so **deferring indexes does not pay at this size**.
The generated `to_tsvector` column is the single largest database cost; in
an indexed parallel load it is computed across the 8 backends at once.

### Projection to the full baseline (1 274 files ≈ 38.2 M records)

Linear extrapolation from 240 k rows into an empty table. Optimistic: index
depth grows with the table.

| Variant | Hours |
|---|---|
| P1 (today's importer) | 9.7 |
| P3 Python, COPY, 8 processes | 1.7 |
| R2 Rust, COPY, 8 threads | 1.1 |
| R2 without Postgres FTS (BM25 moved to tantivy) | 0.3 |
| Rust parse only | 0.1 |

## 4. Verdict

- **Design gives 5.8× at equal language** (P1 → P3). This is available in
  Python today: COPY, a set-based merge, a process pool.
- **Rust adds 1.45× cold and 1.3× warm** on the best design (P3 → R2). That
  is **below the 2× go/no-go threshold** set in the plan. Once writes are
  set-based and parallel, Postgres (to_tsvector, GIN, btree, trigger) is the
  bottleneck, not the client language.
- **Rust's parse advantage is large** (6× single-thread, 35× with threads),
  but parsing is only ~10 % of the end-to-end time once the database work is
  included.
- **The biggest single lever is architectural:** take BM25 out of Postgres
  (tantivy) and drop the generated tsvector + GIN. The relational load then
  runs at ~36 k articles/s (0.3 h for the baseline). That pays off in
  whichever language builds the tantivy index, and is natural in Rust, where
  tantivy is native.

**For Phase 1:** a Rust ingest is justified less by raw speed than by the
pipeline it makes easy. One process can parse in parallel, COPY into
Postgres and feed tantivy, with backpressure and no GIL or multiprocessing
workarounds. If the port were not planned, ~6× is available in Python today
by fixing the write pattern.

## 5. Defects found in the production importer (`pubmed_bulk_importer.py`)

These are reproduced in the spike on purpose (for parity) and should be fixed
in both the Python importer and any port:

1. **Author keywords are always dropped.** `_parse_article` searches
   `article.findall('.//KeywordList/Keyword')`, but `KeywordList` is a child of
   `MedlineCitation`, not of `Article`. In file 1101, 20 709 of 30 000 records
   (69 %) have keywords; the database stores none.
2. **Retraction cross-references are never read.** `CommentsCorrectionsList`
   is searched under `PubmedData`, but it lives under `MedlineCitation`. In
   file 1101, 118 records have `RetractionIn`/`RetractionOf` entries that are
   missed. Only the `PublicationType` check fires.
3. **The DOI lookup can return a cited reference's DOI.** It searches
   `.//ArticleIdList/ArticleId` under `PubmedData`, which includes
   `ReferenceList/Reference/ArticleIdList`. It is latent in file 1101 (0
   cases), but any record without its own DOI and with DOI-bearing references
   gets a wrong DOI.
4. **`all_keywords` order is nondeterministic.** The trigger builds it with
   `SELECT DISTINCT … ` and no `ORDER BY`; 156 472 of 239 916 rows came out
   unsorted. This is harmless for set use but breaks naive comparisons; add
   `ORDER BY 1`.
5. **Revision handling is implicit.** A PMID that appears again (a revised
   record) is resolved by write order plus COALESCE, so the result depends on
   the write pattern. Phase 1 should pick the winner explicitly (e.g. by
   `DateRevised`/`Version`) rather than by arrival order.

## 6. Caveats

- One machine, a local Postgres with default settings. No tuning of
  `synchronous_commit`, `maintenance_work_mem`, WAL or checkpoints. Tuning
  helps all COPY variants roughly equally.
- 8 files into an empty table. Warm runs update the same 240 k rows; they do
  not model a 38 M-row table.
- The Rust parser decompresses whole files into memory (~265 MB per worker).
  A streaming `quick-xml` reader would cut that if needed.

## 7. Phase 0c — long, resumable run with production FTS (2026-10-12)

Run with `long_run.py --fts`: the Rust loader with 8 threads, one transaction
per file that also writes the `ingest_ledger` row. Table shape as production
(generated tsvector + GIN, 9 other indexes, keyword trigger). Server: Postgres.app
defaults (`shared_buffers` 128 MB, `max_wal_size` 1 GB).

**Kill/resume test passed.** The loader was SIGKILLed after 28 of 80 files
(840 k rows) had committed; the in-flight files rolled back. The resumed run
finished with exactly the same 2 400 000 distinct PMIDs as an uninterrupted
reference run (PMID-set md5 equal), with no duplicates.

**Throughput while the table grew from 0 to 20 M rows** (ledger
timestamps):

| Stage | Files | Rows in table | Throughput |
|---|---|---|---|
| Baseline files 1–334 (1950s–2000s, many without abstracts) | 334 | 0 → 10 M | 30–46 k/s (overall 36.8 k/s; 4.6 min) |
| Modern files 941–1274, appended | 333 of 334 | 10 M → 20 M | **~15 k/s, flat** (40 files per 62–85 s, drifting slightly slower) |
| `pubmed25n0941` (first file of the appended run) | 1 | — | **3 112 s** (median file 14 s) |

**There is no steady degradation.** With set-based COPY merges, throughput
tracks record content (abstract length), not table size, up to 20 M rows,
even on default server settings. The full run took 101 GB on disk.

**The one stall points to GIN `fastupdate`.** At 16:20:11, autovacuum was
flushing the GIN pending list of `spike_doc_fts` and was cancelled when the run
started: `prepare()` takes a conflicting lock even for a no-op `ALTER TABLE …
IF NOT EXISTS`. Two seconds later, file 941 was the first insert. In
`fastupdate` mode the inserting backend that crosses
`gin_pending_list_limit` flushes the pending list itself, single-threaded,
while the other workers keep adding to it. Re-running file 941 alone against
the 20 M-row table took 21.5 s, so the file itself is not slow. This is a
known GIN failure mode, and it matches the historical "it slows down
considerably" experience. Not yet proven by a controlled rerun.

**Checkpoint pressure:** the server log shows **735 WAL-triggered checkpoints**
in about 2 h of loading, typically 2–3 s apart, each followed by "consider
increasing max_wal_size".

### Implications

- A resumable, incremental import is viable at this scale, if writes are
  set-based. Per-file transactions with the ledger in the same transaction
  give at-most-one-file-per-worker loss on any interruption, with no
  separate bookkeeping step.
- GIN needs explicit handling. Options:
  1. `fastupdate = off`: steady per-row cost, no spikes.
  2. A larger `gin_pending_list_limit` plus a scheduled `VACUUM` between
     batches, so no inserter pays the flush.
  3. Fill the tsvector from a resumable queue behind ingest.

  Measure option 1 against the current behaviour before choosing.
- Server tuning (`max_wal_size` ≥ 16 GB, `shared_buffers` 16–32 GB,
  `checkpoint_timeout` 15 min) should remove most checkpoint churn. It is
  server-wide (it also affects `knowledgebase`) and needs the owner's
  approval.
- None of this involves vectors. HNSW maintenance during import is a separate
  and probably larger cost; it is the next measurement.

## 8. Controlled GIN test and the import profile (2026-10-12)

Both arms were appended to the same table (20 M → 25 M → 30 M rows), each
under the server **import profile** (`pg_import_profile.py`:
`shared_buffers` 32 GB, `max_wal_size` 64 GB, `min_wal_size` 4 GB, applied by
`ALTER SYSTEM` plus a restart, restored afterwards). Each arm started with
`gin_clean_pending_list()`, timed separately.

| Arm | Files | `fastupdate` | Throughput | Median file | p95 | Worst file | Forced checkpoints |
|---|---|---|---|---|---|---|---|
| A | 607–773 (5.0 M) | on (default) | 11 359/s (441 s) | 17 s | 32 s | **176 s** | 1 |
| B | 774–940 (5.0 M) | off | 9 880/s (507 s) | 22 s | 34 s | **51 s** | 2 |

**A's lead is borrowed.** Before arm B, flushing the pending list that A left
behind took **148 s (846 536 pages ≈ 6.6 GB)**. Counting that, A cost
441 + 148 = 589 s against B's 507 s. **`fastupdate = off` is ~14 % faster in
total, has no stalls (worst file 51 s against 176 s here and 3 112 s in §7),
and leaves no backlog** for the next writer or reader to pay.

**The import profile removes the checkpoint storm**: 1–2 forced checkpoints
per arm, against ~6 per minute on default settings (§7). The apply → restart →
restore cycle was verified, and `postgresql.auto.conf` came back unchanged.
Between-run throughput comparisons with §7 are not clean: the files are from a
different era, the table is larger, the cache is cold after the restart, and
an accidental read-only production query overlapped arm A for ~2 min.

**For the port:** create the FTS GIN index with `fastupdate = off` (at least
for the import path). Run imports inside the import profile, applied and
restored by the importer itself; a state file keeps the profile across a
killed and resumed run, and a `restore` command handles abandoned runs.
