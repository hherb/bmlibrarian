# Library pipeline (`rust/bml-library`)

Installer piece 3: `bml library update` brings the library up to date with
medRxiv. Plan: `docs/superpowers/plans/2026-11-14-library-pipeline.md`;
spec: `docs/superpowers/specs/2026-11-11-installer-walking-skeleton-design.md`
(Goal C). User guide: `doc/users/library_updates_guide.md`.

## Shape

`Pipeline::update(db, options, progress)` runs metadata, index, full text,
then index again. The first index run makes new abstracts searchable within
the hour instead of after a full-text backlog that takes weeks at 30 s per
request; the second indexes the new full texts. The embedder is loaded once.
Each phase picks its next piece of work from table state alone, so `kill -9`
at any point loses at most the paper (or day window) in flight. A phase that
fails lands in `UpdateReport::failures`; the phases after it still run.
`library_state.last_update_at` is stamped only by a complete update (nothing
failed, nothing stopped early), which is what `--if-older-than` reads.

| Phase | Module | Checkpoint | Unit of work |
|---|---|---|---|
| Metadata | `metadata.rs` | bmlib's `download_days` ledger | one day (synced in 30-day windows, `METADATA_WINDOW_DAYS`) |
| Full text | `fulltext.rs` | `publication_fulltext` | one paper |
| Index | `index.rs` | `publication_index` and its label | one paper, one transaction |

`stop` (an `AtomicBool`, set by Ctrl-C in the CLI) is checked between day
windows and between papers. One worker at a time: `try_lock_worker` takes
`<library>/.bml-library.lock` with `File::try_lock`; a second
`bml library update` prints that one is running and exits 4 (stopped early:
run it again later). SIGTERM stops a run as Ctrl-C does (ctrlc's
`termination` feature).

`Pipeline` holds the outside world as public fields (HTTP clients and their
spacing, the documents cache, the embedder loader, the clock), so the tests
replace each one (`bml_library::testing::FakeHttp`, a stub `ChunkEmbedder`).

## Metadata

bmlib `publications::sync` with the `medrxiv-details` source (`/details/`,
every posted version, bmlib PR #760) from the start day to today. The start
day (`start_day`) is `--from` when given, which is then remembered in
`library_state.from_day`, else the remembered day, else
`MEDRXIV_FIRST_DAY` (2019-06-06). So a library begun "from date X" is not
widened to all of medRxiv by a later or scheduled run. Records keep `source =
"medrxiv"`, so versions dedupe onto one publication per DOI; each version's
`jatsxml` and PDF land in `fulltext_sources` with `version` set. Requests
to `api.biorxiv.org` go through a `PoliteClient` spaced by bmlib's
`RATE_LIMIT_SECONDS` (bmlib defines it but does not sleep). A failed day is
recorded `failed` by bmlib and fetched again next run; days within
`DETAILS_SETTLE_DAYS` (7) are re-fetched until settled. A 429 from the API
ends the phase after its window (`MetadataReport::rate_limited`, stopped
early, exit 4); bmlib has recorded that window's days `failed`, so they
come again next run, and their errors are not listed.

## Full text

Work query (`next_paper`): the newest medRxiv version among a paper's
`xml`/`pdf` sources (`version` compared as an integer, guarded by a regex so
no cast can fail), and either no `publication_fulltext` row, or a passed (or
null) `retry_after` with the row abstract-only or holding an older version.
Newest posting first, so updates are not starved by the backlog.

Per paper, one `FullTextService` call with only the paper's own sources of
that version (`doi: None`, `pmc_id: None`, `pmid: ""`), so only bmlib's Tier
0 runs, and `identifier = "<doi>v<version>"` (the cache key is bmlib's
`sanitize_identifier` of it). `fetch_pdf_with_jats` is off: a PDF is asked
for only when the JATS has no article body or failed. The service extracts
the PDF's text (MuPDF) so a scan is told apart.

`PoliteClient` (`polite_client.rs`) wraps bmlib's `UreqClient`: one request
at a time (the lock is held while sleeping), `MEDRXIV_REQUEST_DELAY` (30 s)
from the end of one request to the start of the next, every request's URL
and status recorded, and after the first 429 every further request fails
unsent.

`classify` (pure) maps the result and the recorded requests:

| Outcome | Form | Kind |
|---|---|---|
| JATS with a body (or a cache hit of one) | `jats` | – |
| PDF downloaded and its text extracted | `pdf` | – |
| PDF with no text (scan), `encrypted`, `unreadable` | abstract | lasting |
| PDF extraction `engine`/`cancelled`/`timed-out` | abstract | passing |
| PDF requested and failed | abstract | bmlib's `pdf_failure_may_pass` |
| JATS only: 404, 403, other 4xx, not readable, no body | abstract | lasting |
| JATS only: no answer, 408, 5xx | abstract | passing |

The paper's kind is the PDF's when a PDF was requested. The reason names
both requests ("JATS: not found (HTTP 404); PDF: refused (HTTP 403)").
Back-off (`retry_delay`): passing doubles from `RETRY_BASE` (1 h) to
`RETRY_MAX` (7 days); lasting waits `LASTING_RETRY` (30 days). Abstract-only
is never final.

**A 429** ends the phase at once: `library_state.rate_limited_until = now() +
RATE_LIMIT_BACKOFF` (1 h), the paper's row is left as it was, and later runs
skip the phase until then.

**Recording** (`record`): a full text is recorded only if its file is in the
cache (else a passing failure). Success, in one transaction: upsert the row
(`version_held`, `cache_key`, `cache_path` relative to `documents/`,
attempts and errors cleared) and set `publication_index.status = 'pending'`;
the paper's old chunks stay searchable until the index phase replaces them. After the commit the old
version's cache entry is deleted (`FullTextCache::delete`): its key is
queued in `cache_deletions` inside the transaction, and the file and the
queue row are removed after the commit. A failure on a
paper that already holds full text (a new version failing) updates only
`attempts`, `last_error`, `last_error_kind` and `retry_after`: the old
version's row, file and chunks stay.

**Old files**: queued deletions a crash interrupted are finished at the
start of each full-text phase (`finish_cache_deletions`; a key a row uses
again is not deleted). A file is never deleted only because no row names it:
the database may have been recreated, and a fetch whose commit a crash
prevented is served from the cache on the next try. `bml library status`
counts queued deletions and unreferenced files (kept).

## Index

Work query (`next_due`, SQL only): no `publication_index` row, `pending`, or
a label field differing from the running embedder (`model_sha256`), bmlib's
`EMBEDDING_RECIPE_VERSION`, `CHUNKER_VERSION`, or the converter implied by
the full-text form (`jats-N`, `pdf-N`, else `abstract`). A changed model or
chunker re-indexes with no flag.

Per paper: an abstract chunk (title + abstract, `kind = 'abstract'`,
ordinal 0) always, plus, for a full text, bmlib's canonical text (JATS via
`jats_reader::parse` + `canonical_from_jats`; PDF via `MupdfExtractor` +
`SectionSegmenter` + `canonical_from_segmented`) cut by `chunk_canonical`
(`DEFAULT_MAX_CHARS` 1000, `DEFAULT_OVERLAP_CHARS` 100; headings are not
chunked). Embedded in batches of `EMBED_BATCH_SIZE` before the transaction;
then, in one transaction: delete the paper's chunks, insert chunks and
`halfvec` embeddings, mark the row `complete` with its label and
`chunk_count`. NUL characters are dropped from chunk text (PostgreSQL text
cannot hold them). A full text that is the file's fault (missing, not
UTF-8, does not parse, an encrypted or unreadable PDF, no text) turns the
paper abstract-only (lasting, cache entry queued for deletion) instead of
being picked again forever. One that is not (an I/O error, the PDF engine,
`PDF_READ_DEADLINE` (10 min) passing, a chunker error) keeps the file and
its row and is an index failure: the paper is tried again next run. The work query walks papers by id with a cursor
(`p.id > last`), so it does not rescan finished papers and a paper whose
indexing fails (a model or database error on its text) is reported in
`IndexReport::failed`, left due for the next run, and passed over; after
`MAX_FAILURES_IN_A_ROW` (3) failures in a row the phase stops, since the
cause is then likely the model or the database. The model is checked with `verify_model` (sha256)
before loading; a missing or damaged file fails the index phase in its
first pass (right after metadata) with the `bml setup` hint; full text
still runs and the second pass is skipped.

## Schema

bml-db migration 2 adds `library_state` (one row, `id = 1`:
`rate_limited_until`, `last_update_at`, `from_day`) and `cache_deletions`.
See `rust_db_schema.md`. bmlib's
`Db` over PostgreSQL binds only text, integers and booleans, so timestamps
and vectors are passed as text and cast in SQL.

## Schedule

`bml_pgserver::schedule` (beside `autostart`, sharing its helpers):
`schedule_updates(exe, config_dir, days)` / `unschedule_updates()`. Every
scheduler fires **daily** at `DAILY_RUN_HOUR` (12:00) and runs `bml library
update --if-older-than <days>`, which does nothing while the last complete
update is younger than `days` (less `SCHEDULE_SLACK_HOURS`, 2, for a trigger
firing a little early). So the interval survives restarts, and an
unfinished update (backlog, rate limit, failure) carries on the next day.
macOS: a LaunchAgent `org.bmlibrarian.library-update` with
`StartCalendarInterval` and `RunAtLoad` (so it also runs at login and when
scheduled; a failed re-schedule restores the old entry, as #405). Linux:
`bml-library-update.{service,timer}`, `OnCalendar=*-*-* 12:00:00` +
`Persistent`, output appended to the log. Windows: a Scheduled Task `/SC
DAILY /ST 12:00` (unverified, #397; a day missed while off is not caught up,
marked `shortcut:`; no log). Output goes to `bml-library-update.log` in the
configuration folder (`update_log_path`).

## CLI

`bml library update [--from YYYY-MM-DD] [--skip metadata|fulltext|index]...`
(exit 0 done, 1 failed, 2 not set up, 4 stopped early: Ctrl-C, SIGTERM,
rate limited, or another update running; `--if-older-than <days>` exits 0
at once while the last complete update is younger; a run with `--skip` is
never a complete update); `bml library status`; `bml library schedule weekly|every
<days>|manual` (days 1–365). The update runs `bml_db::migrate` first, so an
older library gains migration 2.

## Measurements and findings

- 2026-11-14 (plan "Measurements"): at 1.5 s spacing medRxiv answered 429
  after 7 papers; at 30 s, 60 requests met no 429; 28 of 30 JATS
  *downloaded*; 26 of 30 PDFs got a Cloudflare 403.
- 2026-11-14 hand run (this branch, real API and model, a temporary
  server): 3 days, 153 papers, all indexed (abstract chunks) in 88 s. Both
  papers tried for full text (posted 2026-11-11/13) had a JATS
  `source.xml` whose `<body>` holds only `<supplementary-material>`, so bmlib
  reports no body and the pipeline fell back to the PDF, which downloaded
  (2 of 2). **The measurement counted JATS downloads, not JATS with a body**;
  how many medRxiv JATS files carry the article text is not yet measured.

## Build

bmlib features `pdf` (MuPDF, needs libclang) and `embed` (llama.cpp, needs
cmake and a C++ compiler); the first build takes about 1.5 min on the
owner's Mac. `rust/Cargo.toml` sets `[profile.dev.package.mupdf-sys]
opt-level = 2`: below that, mupdf-sys builds MuPDF's Debug configuration,
whose MSVC runtime (`MDd`) will not link beside llama.cpp's (`MD`) on
Windows. The Windows `pdf` build itself needed bmlib #770.

## Tests

- Unit: `cargo test -p bml-library` (PoliteClient spacing and 429,
  `classify`, back-off, orphans, worker lock).
- Real PG18 (`#[ignore]`d, own temp server each):
  `BML_TEST_PG_BINDIR=<PG18 bin> cargo test -p bml-library -- --include-ignored`
  (`tests/pipeline.rs`: resume after a day commit, a v2 record, JATS, JATS
  404 then PDF, refused PDF, timeout, 429 uncharged, version replacement,
  failed new version, orphan cleanup, abstract-only then full text, changed
  label, index crash, missing model, remembered start day, abstracts
  indexed before full text, a failing paper not blocking the others,
  failures in a row ending the phase, only complete updates stamped).
- CLI: `cargo test -p bml-cli --test library_cli` (exit codes, lock, argument
  checks); `bml-pgserver` `schedule` unit tests (plist lint on macOS).
- Not covered by tests: the real GGUF (hand run only), the Linux and Windows
  schedulers (cross-target clippy only).
