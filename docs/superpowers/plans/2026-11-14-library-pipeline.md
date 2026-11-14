# Library Pipeline (Installer Piece 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `bml library update` brings the library up to date with medRxiv:
metadata for every posting day by day, full text (JATS XML, then PDF) into
`<library>/documents/`, a new version replacing the old one, and every paper
chunked and embedded into the piece-2 tables. It resumes after a crash with
at most the paper in flight lost. `bml library schedule` installs a per-user
scheduler entry that runs the same command.

**Architecture:** A new UI-free crate `rust/bml-library` holds three
resumable phases, each driven by database state alone:

1. **Metadata**: bmlib `publications::sync_source` with the
   `medrxiv-details` source (Task 0), which reads `/details/`. The day
   ledger (`download_days`) is the checkpoint.
2. **Full text**: one paper at a time through `FullTextService` restricted
   to Tier 0 (the record's own `jatsxml`/PDF sources), over a pipeline-owned
   `HttpClient` that spaces every request. The checkpoint is
   `publication_fulltext`.
3. **Index**: canonical text, then bmlib's chunker, then in-process
   `Embedder`, then `chunks` + `chunk_embeddings` (`halfvec`) in one
   transaction per paper. The checkpoint is `publication_index` and its
   `ChunkSetLabel` fields.

`bml-cli` gains `bml library update|status|schedule`. One worker at a time,
held by an OS file lock.

**Tech Stack:** Rust 1.89 workspace `rust/`. bmlib pin bumped past Task 0,
with features `embed` (Metal on macOS by default) and `pdf` added.
`postgres` 0.19.

**Spec:** `docs/superpowers/specs/2026-11-11-installer-walking-skeleton-design.md`
(Goal C, piece 3).

## Owner decisions (2026-11-14)

- **bmlib adds `/details/` sources; `biorxiv`/`medrxiv` keep `/pubs/`.**
  `/pubs/` lists only preprints that were later published in a journal,
  under the publication date (10 of 28 medRxiv records on 2024-01-15), and
  carries no `jatsxml` or `version`. bmlib adds **separate sources
  `biorxiv-details` and `medrxiv-details`**, read by the same
  `BiorxivFetcher` from `/details/`, in Python and Rust together (bmlib
  #341, PR #760, merged 2026-11-14, not yet in a release). The owner first
  chose "replace", then changed this to separate sources on 2026-11-14.
  BMLibrarian syncs `medrxiv-details` and bumps its pin once a bmlib
  release contains #760.
- **MECA bulk is the main full-text route for the backlog.** Piece 3c (MECA
  reader + requester-pays S3) moves up and follows piece 3 directly. Without
  AWS keys the backlog stays abstract-only, with full text trickled in slowly
  in the background. Paper by paper is the route for updates.
- **Measure a polite request rate** before fixing the delay constant
  (below).

## Measurements (2026-11-14, owner's Mac, bmlib's `UreqClient`, UA `bmlib/<ver>`)

- `api.biorxiv.org/details/medrxiv/<day>/<day>/0` answered in full on
  2026-11-14 (`messages[0].total` present). A page holds 30 records; bmlib
  measured 55–99 medRxiv postings per weekday near 2026-11-13 (its
  `DETAILS_BASE_URL` doc), so a day takes several pages. It returns one
  record per posted **version**: 2024-01-15 had 21 new papers and 7 new
  versions.
- `jatsxml` points at
  `https://www.medrxiv.org/content/early/…/<id>.source.xml`, on the same
  Cloudflare-fronted host as the PDFs.
- **At one request every 1.5 s, medRxiv answered 429 after the first 7
  papers** (a JATS and a PDF request each) and kept refusing for the rest of
  the run (several minutes). Of those 7: JATS 5 downloaded (the other 2 were
  404, meaning no JATS), and PDFs 2 downloaded, with 5 blocked by a
  Cloudflare 403 ("Sorry, you have been blocked").
- Not worked around (spec: no browser automation; we send our own user agent).
- **At one request every 30 s** (after a one-hour cool-down; 30 papers,
  5 from each of 6 days, 2020–2025; 60 requests over 30 minutes) there
  were **no 429s**. JATS: 28 of 30 downloaded, and the 2 others were 404 (no
  JATS for that paper). PDF: 4 of 30 downloaded, and 26 were blocked by a
  Cloudflare 403.
- Consequences:
  - `MEDRXIV_REQUEST_DELAY = 30 s`, the rate measured as safe. Rates between
    1.5 s and 30 s were not measured; a faster rate is a later measurement,
    not a guess.
  - A PDF is requested only when the paper has no JATS (Tier 0 with
    `fetch_pdf_with_jats` off). Most of those requests will get a 403, and
    the paper becomes abstract-only with a `lasting` reason.
  - At 30 s, 2,880 requests a day: as many papers when each has JATS (one
    request), half as many when none has (JATS 404, then the PDF). A weekly
    update (roughly 300–500 postings, at 55–99 a weekday) takes 2.5–4.2
    hours of mostly idle waiting when every paper has JATS (28 of 30 did),
    up to twice that when none has. The backlog (every posting since
    medRxiv opened in June 2019, not counted here) takes weeks at this
    rate, which is why MECA (3c) follows.

## Global Constraints

- All progress lives in the database. Each phase picks its next work from
  table state, so `kill -9` at any point loses at most the paper in flight.
- **Polite requests:** one request at a time to `www.medrxiv.org`, spaced by
  `MEDRXIV_REQUEST_DELAY` (named constant). The spacing lives in a
  pipeline-owned `HttpClient` wrapper (`PoliteClient`) handed to
  `FullTextService::new`, not between papers: Tier 0
  (`try_known_sources`) requests the PDF straight after a failed JATS
  request within one call, so a paper without JATS costs two spaced
  requests. The wrapper records each response's URL and status for the
  paper in flight, which is how JATS failures are classified (below).
- **A 429 ends the full-text phase for this run** (no retry loop against a
  rate limit). After the first 429 the wrapper fails every further request
  at once without sending it, so the PDF request that would follow a JATS
  429 never reaches the host. The phase records `rate_limited_until` = now
  + `RATE_LIMIT_BACKOFF` in the `library_state` table (bml-db migration 2,
  Task 3). The next run, scheduled or manual, skips the phase until then.
  The 429 is not counted against the paper: its row is left as it was.
- **Failure kinds** (spec "abstract-only is never final"), stored in
  `publication_fulltext.last_error` (the reason, plain words) and
  `last_error_kind`, with `attempts` and `retry_after`. A 429 is caught by
  the wrapper before either classifier runs. PDF: reuse bmlib's
  `FullTextResult::pdf_failure_may_pass` (`passing` also covers its
  `request-failed` and checksum-mismatch cases). JATS: bmlib reports no
  cause for a JATS failure, so the pipeline maps the wrapper's recorded
  status: `lasting` = 404, 403, not-XML; `passing` = timeout, 5xx, 408, no
  response. The paper's kind is the PDF's when a PDF was requested, else
  the JATS one. Back-off per paper: `passing` doubles from `RETRY_BASE` up
  to `RETRY_MAX`; `lasting` waits `LASTING_RETRY`. A PDF 403 is expected
  (most PDFs are blocked, see Measurements) and is `lasting` for the paper.
  `bml library status` shows abstract-only counts by reason rather than
  raising an alarm.
- **Version replacement:** the cache key is `<doi>v<version>`. When
  `fulltext_sources.version` for a paper is newer than
  `publication_fulltext.version_held`, the full-text phase fetches the new
  version, then **in one transaction** writes the new row, deletes the
  paper's chunks (embeddings cascade) and sets `publication_index.status =
  'pending'`. After the commit it deletes the old cache entry with
  `FullTextCache::delete`. A crash between commit and delete leaves an
  orphan file, which `bml library status` reports and a later run removes.
- **A new version that fails** keeps the old version's row, file and chunks
  untouched (old full text beats an abstract) and records only the failure:
  `last_error`, `last_error_kind`, `attempts` and `retry_after` on that
  row, with the same back-off as above. The work query retries the new
  version only once `retry_after` has passed.
- **Every paper is indexed:** an abstract chunk (title + abstract, ordinal 0,
  `kind = 'abstract'`) always, plus full-text chunks when full text is held.
  Abstract-only papers are `complete` with `converter_version = 'abstract'`.
  When full text arrives later, the label changes, so the paper is
  re-indexed.
- Chunking: `chunk_canonical(canonical, DEFAULT_MAX_CHARS, DEFAULT_OVERLAP_CHARS)`
  (1000/100, bmlib's defaults). Vectors come from `Embedder::embed_documents`,
  already 256-d and normalised. Never write the literal 256.
- The `ChunkSetLabel` (`model_sha256`, `recipe_version`, `chunker_version`,
  `converter_version`, `text_sha256`) decides "already indexed". A changed
  model or chunker re-indexes on the next run, with no flag needed.
- No Europe PMC, PMC, Unpaywall or DOI tiers: requests carry only
  `fulltext_sources` + `identifier` (`doi: None`, `pmc_id: None`,
  `pmid: ""`). No contact email.
- No magic numbers or hard-coded paths. Every error reaches the user as plain
  words. `missing_docs` is on.

## Order

0. **bmlib (own repo, own PR, Python + Rust, shared fixtures):** `/details/`
   sources. Merged 2026-11-14 (#760); BMLibrarian work starts once a bmlib
   release contains it.
1. Pin bump + features + `bml-library` skeleton.
2. Metadata phase.
3. Full-text phase.
4. Index phase.
5. Worker lock, `bml library update|status`.
6. `bml library schedule` (scheduler entry).
7. Docs.

Pieces 3b (medRxiv HTML page, bmlib) and 3c (MECA, bmlib + here) follow,
3c first.

## Review Focus

1. Kill during each phase (after the day commit, between full-text commit and
   cache delete, mid-index transaction): the next run finishes the work with
   no duplicate chunks and no paper marked complete without its chunks.
   Tasks 2–4, `resume_after_*` tests.
2. A 429 stops the full-text phase at once (no PDF request after a JATS
   429) and is not charged to the paper. Task 3,
   `rate_limit_ends_phase_without_charging_paper`.
3. v1 held, v2 posted: the v2 file is cached, v1's file is gone, the chunks
   come from v2, and v1's chunks are gone. Task 3,
   `new_version_replaces_old`.
4. Two `bml library update` at once: the second exits quietly, saying a run
   is in progress. Task 5.
5. The embedding model file is missing or wrong: the index phase fails with
   the setup hint, and the metadata and full-text phases still ran. Task 4.

---

### Task 0 (bmlib): `biorxiv-details` / `medrxiv-details` sources (PR #760)

**Repo:** `hherb/bmlib`, PR #760 (merged 2026-11-14 as `3fd7d560`, not yet
in a release; the newest tag, v0.13.0, predates it). What BMLibrarian relies
on, all delivered by #760:

- [x] Source `medrxiv-details` (its own `download_days` ledger). Its records
      keep `source = "medrxiv"`, so they dedupe onto one publication row per
      DOI.
- [x] One record per posted version. `fulltext_sources.version` holds
      `"1"`, `"2"`, and so on, and a v2's sources are added beside v1's
      because the URLs differ. **The current version is the highest
      `version` among the paper's sources whose `source` is `medrxiv`.**
- [x] `jatsxml` is an `xml` source; the PDF URL uses the record's version.
      `extras["published"]` is `""` where `/details/` sends `"NA"`.
- [x] `settle_days` = 7, a bound rather than a measurement (bmlib #759).
- [x] Polite spacing for `www.medrxiv.org` is **not** in bmlib. It is this
      plan's `MEDRXIV_REQUEST_DELAY`.
- [ ] A bmlib release containing #760 is cut: then Task 1's pin bump.

### Task 1: Pin bump, features, `bml-library` skeleton

**Files:** `rust/Cargo.toml`, `rust/bml-library/{Cargo.toml,src/lib.rs}`.

- [ ] Bump the bmlib rev past Task 0. `sync()`/`sync_source()` now return
      `SyncError` (not used by bml-db/bml-setup). Rebuild and run
      `cargo test -- --include-ignored`.
- [ ] **Owner decision before Task 3:** the bump also brings bmlib #763
      (merged 2026-11-14): `FullTextService::with_library` and the shared
      `bmlib::library`, where downloads go into write-once per-paper
      folders instead of the cache. Either `<library>/documents` stays a
      `FullTextCache` (this plan as written: `.with_cache`, `<doi>v<version>`
      keys, `FullTextCache::delete`), or it becomes a bmlib library, which
      rules out deleting an old version's file and changes the version
      replacement rule and the orphan-file check. Record the answer here.
- [ ] Add features `pdf` and `embed` (Metal on macOS by default, so no
      target-specific entry). Check CI build time on all three OSes. MuPDF
      needs libclang.
- [ ] `bml-library` exposes `pub struct Pipeline { db, client, cache, embedder_path }`
      and `pub fn update(&self, opts: &UpdateOptions, progress: &dyn Fn(Progress)) -> Result<UpdateReport, LibraryError>`.
      `UpdateOptions { from: Option<NaiveDate>, phases: PhaseSet, stop: &AtomicBool }`.

### Task 2: Metadata phase

- [ ] `sync_source(db, "medrxiv-details", &fetcher, request, clock, report, settle_days)`
      with the registry's `medrxiv-details` fetcher and its settle days
      from `from` (default: medRxiv's first posting day, a named constant)
      to today. Report days fetched/failed and records added/merged.
- [ ] Tests (live PG, `#[ignore]`): fake `HttpClient` serving `/details/`
      fixture pages; resume after a failed day; a v2 record updates the
      source version. `resume_after_day_commit`.

### Task 3: Full-text phase

**Files:** `rust/bml-library/src/{fulltext.rs,polite_client.rs}`,
`rust/bml-db/src/schema.rs` (migration 2).

- [ ] bml-db migration 2: `CREATE TABLE IF NOT EXISTS library_state` (one
      row, `rate_limited_until TIMESTAMPTZ`), idempotent like migration 1.
- [ ] Work query: publications with an `xml`/`pdf` source and either no
      `publication_fulltext` row, or a `version_held` older than the
      highest source `version` (compared as integers; only that version's
      sources go into the `FullTextRequest`) with `retry_after` null or
      passed, or `form = 'abstract'` with `retry_after <= now()`. Ordered
      newest posting first, so updates are not starved by the backlog.
- [ ] `PoliteClient` (Global Constraints): wraps bmlib's `UreqClient`,
      sleeps out `MEDRXIV_REQUEST_DELAY` since the last request, records
      URL and status per request, and fails fast after a 429.
- [ ] Per paper: `FullTextService::new(PoliteClient, …)` with
      `.with_cache(library cache)`, `.with_pdf_extractor(MupdfPdfExtractor)`,
      Tier 0 only. Map the result and the recorded statuses to `form`
      (`jats` / `pdf` / `abstract`) plus `last_error`, `last_error_kind`,
      `attempts` and `retry_after`.
- [ ] Version replacement transaction, and a failed new version keeping
      the old one (Global Constraints).
- [ ] The rate limit and the blocked share, as in Global Constraints. `stop`
      checked between papers.
- [ ] Tests: fake client for JATS 200, JATS 404 then PDF 200, PDF 403,
      timeout, 429 on JATS (no PDF request sent); requests spaced by the
      delay within one paper; `new_version_replaces_old`;
      `failed_new_version_keeps_old`;
      `rate_limit_ends_phase_without_charging_paper`;
      `resume_after_fulltext_commit_before_cache_delete`.

### Task 4: Index phase

- [ ] Work query, in SQL only (no text is canonicalised to decide):
      publications whose `publication_index` row is missing, `pending`, or
      whose `model_sha256`, `recipe_version` or `chunker_version` differs
      from the running embedder and chunker, or whose `converter_version`
      differs from the one implied by `publication_fulltext.form`.
      `text_sha256` is not compared: a new form or version already sets
      `status = 'pending'` (Global Constraints), and the hash is written
      when the paper is indexed.
- [ ] Canonical text: JATS via `jats_reader::parse` + `canonical_from_jats`;
      PDF via `MupdfExtractor` + `SectionSegmenter` + `canonical_from_segmented`.
- [ ] Chunks + embeddings + `publication_index` complete, in one transaction
      per paper (delete old chunks first). Embed in batches
      (`EMBED_BATCH_SIZE`).
- [ ] Chunk text goes into `chunks.text`, so BM25/tsvector index it with no
      extra step.
- [ ] Tests: a stub `ChunkEmbedder` for unit tests (no model);
      `resume_after_index_crash` (rolled-back transaction leaves `pending`);
      `changed_label_reindexes`; one gated test with the real GGUF.

### Task 5: Worker lock and `bml library update|status`

- [ ] `<library>/.bml-library.lock` via `File::try_lock`, as `bml-setup`'s
      download lock does. A second run prints "an update is already running"
      and exits 0.
- [ ] `bml library update [--from DATE] [--skip metadata|fulltext|index]`:
      progress lines, Ctrl-C sets `stop` (finish the paper in flight; needs
      a signal-handling crate such as `ctrlc`, new to the workspace), exit
      codes 0 done / 1 failed / 2 library not set up (as `bml server`) /
      4 stopped early (rate limited or Ctrl-C).
- [ ] `bml library status`: papers, full-text forms, abstract-only by reason,
      indexed/pending, last update, `rate_limited_until`, orphan cache files.

### Task 6: `bml library schedule weekly|every <n>|manual`

`<n>` is a number of hours (`every 24` is daily).

- [ ] Extend `bml-pgserver`'s autostart module with an interval entry: a
      LaunchAgent with `StartInterval` (macOS), a `systemd --user` timer
      (Linux), and a per-user Scheduled Task (Windows, unverified, #397). It
      runs `bml library update` from the installed executable.
- [ ] `manual` removes the entry. Re-running with a new interval rewrites it.
      The macOS restore-on-failure path is reused (#405).

### Task 7: Docs and handover

- [ ] `doc/users/library_updates_guide.md` (update, status, schedule, what
      abstract-only means, why medRxiv full text is slow without AWS keys).
- [ ] `doc/developers/library_pipeline.md` (phases, tables, failure kinds,
      version replacement, the rate-limit rule, measurements).
- [ ] CLAUDE.md commands, HANDOVER, spec piece 3 marked done.
