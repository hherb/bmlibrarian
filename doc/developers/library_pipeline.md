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
replace each one (`bml_library::testing::FakeHttp`, behind the crate's
`test-support` feature, which its own dev-dependency turns on; a stub
`ChunkEmbedder`).

## Topic libraries (Europe PMC)

`library_state.topic_id`/`topic_query` (migration 4) name a library's
Europe PMC topic; null is medRxiv, so every older library reads as before.
`topics.rs` holds the presets (`TOPICS`: id, name, terms, the count measured
on 2026-11-15), `topic_query` (quality filter + terms in title or abstract +
trial/review/meta-analysis types), `count_url`/`parse_hit_count` (the app's
live count) and `set_topic`, which refuses a library that already holds
another topic or medRxiv papers.

For a topic library `update` runs `update_topic` instead of the three
phases: **rounds**, newest first, from the clock's day back to
`options.from` (else `europepmc_first_day()`, 1 January of
`topics::TOPIC_FIRST_YEAR`, not remembered). The first round is
`EUROPEPMC_FIRST_ROUND_DAYS` (7), so a new library is searchable within
minutes; the rest are `EUROPEPMC_ROUND_DAYS` (30). Each round is
`metadata::run_window` for the bmlib `europepmc` source (config `query`),
then an index run (the new abstracts), then `fulltext::run(…,
FulltextSource::EuropePmc, …)`, then another index run (the new full texts).
So a round's papers are searchable before the next round starts. The
checkpoints are the usual ones: bmlib's day ledger and the full-text and index rows. Since bmlib PR
#790's review (pinned at `6465096`), a day is the day a record was first
indexed by Europe PMC (`FIRST_IDATE`), not its publication day; the settle
period is 3 days (`EUROPEPMC_SETTLE_DAYS`); a walk that ends short of the
first page's `hitCount`, or returns a record not first indexed on the day,
fails the day; and an empty day completes only if the query without its date
clause finds something (one more request per empty day). A topic's
`PUB_YEAR` range still applies, so a paper published in 2021 but first
indexed before `europepmc_first_day()` is not fetched. `stop` is checked
between rounds and inside each phase as before.

No network is caught two ways. `PoliteClient` gives up after
`NO_ANSWER_LIMIT` (3) requests in a row that got no answer or a web page
(below), after which every request fails unsent. And a round whose every day failed (`errors` ≥
`days`, nothing added or merged) is read as no network too; a captive portal
answering every day with an HTML page counts. Either way the update records
the metadata phase as stopped, says `WAITING_FOR_INTERNET` and ends, instead
of failing its way through every older round. The full-text phase ends as
`FulltextEnd::NoNetwork` without recording the paper in flight; the round
indexes what arrived and the rounds end. Days not fetched stay unfinished in
bmlib's ledger, so the next run fetches them. `last_update_at` is stamped
only for a complete update, as before. `--from` is remembered for a topic
library as for medRxiv (`start_day_or`, default `europepmc_first_day()`).

The topic years are `topics::TOPIC_FIRST_YEAR` and `TOPIC_LAST_YEAR` (2021
and 2026): the query's `PUB_YEAR` range and the first day come from them,
and a `bml-app` test checks that screen 4 names the same years. Changing them
changes the query of new libraries only (a library keeps the query recorded
when its topic was chosen), but the default first day is computed on every
run, so it moves for an existing library without a remembered `--from` too.

`FulltextSource` (`Medrxiv`, `EuropePmc`, mapped from `LibrarySource`) names
the source for `metadata::run_window`, `fulltext::run`/`next_paper` and
`library status`: its metadata source, its `fulltext_sources.source` and its
name in progress lines.

Full text for a Europe PMC paper (`next_europepmc_paper`: a `europepmc`
`xml` source, and no row or an abstract-only row past its retry time;
version always 1) goes through bmlib's **Tier 0** with only the paper's own
`fullTextXML` URL: no PMC ID, DOI or PMID is passed, so exactly one request
is made per paper and no NCBI or PDF-render fallback runs. The cache key is
the PMC ID. Requests are spaced by `EUROPEPMC_REQUEST_DELAY` (1 s) through
`Pipeline::europepmc`. The index phase is unchanged and source-agnostic; a
run that indexed anything ends with one progress line, "N paper(s) ready to
search (…)".

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
no cast can fail), and either no `publication_fulltext` row, or a version
newer than `version_tried` (the version the last try fetched; its URLs are
new, so it is tried at once with `attempts` counted from 0), or a passed (or
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
| JATS only: no answer, 408, 5xx, a web page | abstract | passing |

The paper's kind is the PDF's when a PDF was requested. The reason names
both requests ("JATS: not found (HTTP 404); PDF: refused (HTTP 403)"). A
request with no answer is stored as "no answer" only; the transport message
(which names the URL) goes to the progress line, so `bml library status`
groups the papers under one reason. A 200 whose body is an HTML page
(`polite_client::is_web_page`: `<!doctype html` or `<html` after any XML
declaration and comments; none of the sources answers with HTML) is
recorded as `RequestOutcome::WebPage`, and bmlib gets an error instead of
the page, so it never parses or caches it (its JATS reader would take an
XHTML page's `<body><p>` for an article body and store the sign-in text as
the paper's full text). The paper's failure is passing, for JATS and for a
PDF alike, with the reason "a web page came back instead". A web page counts
towards `NO_ANSWER_LIMIT` like no answer: behind a Wi-Fi sign-in page the
phase ends as `FulltextEnd::NoNetwork` after three requests, and the papers
tried wait the usual passing back-off, not 30 days.

Back-off (`retry_delay`): passing doubles from `RETRY_BASE` (1 h) to
`RETRY_MAX` (7 days); lasting waits `LASTING_RETRY` (30 days). Abstract-only
is never final.

**A 429** ends the phase at once: `library_state.rate_limited_until = now() +
RATE_LIMIT_BACKOFF` (1 h), the paper's row is left as it was, and later runs
skip the phase until then.

**Recording** (`record`): a full text is recorded only if its file is in the
cache (else a passing failure). Every outcome sets `version_tried`. Success,
in one transaction: upsert the row (`version_held`, `cache_key`,
`cache_path` relative to `documents/`, attempts and errors cleared) and set
`publication_index.status = 'pending'`; the paper's old chunks stay
searchable until the index phase replaces them. After the commit the old
version's cache entry is deleted (`FullTextCache::delete`): its key is
queued in `cache_deletions` inside the transaction, and the file and the
queue row are removed after the commit. A failure on a paper that already
holds full text (a new version failing) updates only `attempts`,
`last_error`, `last_error_kind`, `retry_after` and `version_tried`: the old
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
`rate_limited_until`, `last_update_at`, `from_day`) and `cache_deletions`;
migration 3 adds `publication_fulltext.version_tried`. See
`rust_db_schema.md`. bmlib's `Db` over PostgreSQL binds only text, integers
and booleans, so timestamps and vectors are passed as text and cast in SQL.

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
`Persistent`, output appended to the log; a failed schedule puts back both
unit files (`restore_update_units`, each file not put back named) and, if
systemd had read the new ones, reloads it (a failed reload only is reported
as not loaded again, not as a file to delete); `manual` reloads it after
removing them. Windows: a Scheduled Task `/SC DAILY /ST 12:00` (unverified,
#397; a day missed while off is not caught up, marked `shortcut:`; no log,
so a scheduled run's "no answer" causes are lost there too). Output goes to
`bml-library-update.log` in the configuration folder (`update_log_path`).

## CLI

`bml library update [--from YYYY-MM-DD] [--skip metadata|fulltext|index]...`
(exit 0 done, 1 failed, 2 not set up, 4 stopped early: Ctrl-C, SIGTERM,
rate limited, or another update running; `--if-older-than <days>` exits 0
at once while the last complete update is younger; a run with `--skip` is
never a complete update); `bml library status` (its "none offered" counts
the papers not yet tried that `fulltext::offers_link` rejects, the condition
`next_paper` also reads: no full-text link from the library's source, such
as a Europe PMC paper without `fullTextXML`, a medRxiv record without a DOI
or medRxiv links whose version is not a whole number; they are not tried, so
"not tried yet" can reach 0); `bml library schedule weekly|every
<days>|manual` (days 1–365). The update runs `bml_db::migrate` first, so an
older library gains migrations 2 and 3.

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
