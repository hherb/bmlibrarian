# HANDOVER

Working notes for picking up in-flight work. Each section is one
self-contained slice: what's known, where to start, and how to verify.
Remove a section once its slice has landed; add a new section when handing
off new work. Longer-term structural items live in
[ROADMAP.md](ROADMAP.md) — pull one in here once you're about to start it.

---

## Recently landed (context)

- **Import/embedding fixes #442, #444, #446** (2026-11-25, branch
  `fix/import-embed-442-444-446`). `DocumentEmbedder.embed_documents` pages
  by document ID in `batch_size` pages and no longer selects `full_text`, so
  a full-source run without `--limit` holds one page in memory (#442; the
  tqdm-without-total truthiness crash this exposed is fixed too). The
  Europe PMC importer reads IDs from `front/article-meta` only (no more
  eLife `….sa1` sub-article DOIs) and matches existing records by DOI
  (exact/lower/upper variants, so `idx_document_doi` is still used; a
  mixed-case-only mismatch waits on #333), then by PMID against the PubMed
  source, before inserting; a guarded UPDATE that changes no row now
  reports `skipped` (#444). The medRxiv importer updates a stored preprint
  when the API offers a newer version (title, abstract, authors, `pdf_url`;
  full text and PDF only if the new ones were fetched), PDFs for v2+ are
  saved as `<doi>v<n>.pdf`, and `fetch-pdfs` no longer blanks existing full
  text when the PDF was already on disk (#446). Verified: suite 5012
  passed, 75 skipped; no new ruff/mypy findings. Not run against a live
  database or the medRxiv/Europe PMC services.

- **PubMed import fixes #445, #440, #441** (2026-11-25, branch
  `fix/pubmed-import-445-440-441`). `pubmed_bulk_cli` `download-baseline`,
  `download-updates`, `import` and `sync` exit 1 when any file failed
  (`import`/`sync` also when a record could not be parsed);
  `download_baseline`/`download_updates` return
  `DownloadCounts(downloaded, failed)` so sync counts failed downloads too
  (#445). The import profile accepts `1.5GB`/`2 GB`/`100B`, and `apply`
  refuses before changing anything (`ImportProfileError`) when a current
  `postgresql.auto.conf` value could not be restored later (#440). The setup
  wizard's `download_and_import_baseline` is now `download_baseline` then
  `import_all_files('baseline')`; `ImportQueue` and `_import_worker` are
  gone (#441). **Trade-off:** the wizard no longer imports while
  downloading, so a from-scratch baseline takes download + import time
  instead of overlapping them (one worker, as before). Review follow-ups:
  the wizard reports failed downloads/imports instead of "completed
  successfully" and its completion page shows bulk article counts;
  `pubmed_repair_cli.py repair --reimport` exits 1 on import errors; a
  failed ALTER/restart in `apply`, or an unrestorable old state file,
  raises `ImportProfileError` naming the state file. Verified: suite 4984
  passed, 75 skipped; the new tests fail on the old code (the old wizard
  path hangs). Not run against a live NCBI download or a real server.

- **Security audit fixes #434, #449, #450** (2026-11-25, branch
  `fix/security-434-449-450`). OpenAthens cookies go to `requests` as a
  `RequestsCookieJar` keeping each cookie's domain, path and secure flag
  (`openathens_auth.cookie_jar_from_browser_cookies`, `get_cookie_jar()`),
  in `PDFManager.download_pdf` and `FullTextFinder._download_from_source`;
  a cookie without a domain is dropped (it would go to every host) (#434).
  `utils/path_utils.write_private_text` creates files 0600, or narrows an
  existing one before truncating, and raises if it can't; used for the
  OpenAthens session file, the CLI session token and the setup wizard's
  `.env` writes (#450; the wizard files hold DB passwords and API keys, the
  same bug). Password hashes are `pbkdf2_sha256$<iters>$<salt>$<hash>`;
  old `salt$hash` rows verify at 100,000 (`LEGACY_HASH_ITERATIONS`), counts
  above `MAX_HASH_ITERATIONS` fail (#449). No re-hash on login and
  `HASH_ITERATIONS` is unchanged. Checkouts older than this branch can't
  read the new format: a user registered here can't log in from one
  ("Invalid password"). Verified: suite 4941 passed; the new caller and
  malformed-hash tests fail on the old code. Not run against a live
  OpenAthens login. The browser fallback still gets the raw cookie list,
  not the jar (#472).

- **Migration runner: one transaction, one process at a time, #439**
  (2026-11-24, branch `fix/439-migration-lock`). `MigrationManager` runs each
  migration's SQL and its `bmlibrarian_migrations` record in one transaction
  on one connection, holding a session advisory lock (`MIGRATION_LOCK_KEY`,
  polled with `pg_try_advisory_lock`) and re-checking each pending file
  under it, so two processes starting at once no longer both apply a
  migration (the second used to fail on `UNIQUE(filename)`), and a failed
  record rolls back the file's SQL. The exception is a file with
  `CREATE INDEX CONCURRENTLY`: its other SQL commits first and re-runs on a
  retry. Lines that are only `BEGIN;`/`COMMIT;` are dropped, and
  `RESET ALL` follows each file (the pg_dump baseline empties `search_path`
  for the session). `CREATE [UNIQUE] INDEX CONCURRENTLY` runs afterwards:
  its index must be named (checked before any of the file runs), an INVALID
  leftover is dropped first, and the migration is recorded only once its
  indexes are valid. No lock is taken when nothing is pending; failing to
  take it (lost connection, or held for over an hour) is a `MigrationError`,
  so startup stops. Verified: `tests/test_migrations_live.py` (scratch
  databases on PG18 :5532; four runners contending for the lock, a failed
  record rolled back, INVALID index rebuilt, settings leak) passes; baseline
  plus all 35 migrations applied to a fresh scratch database, a second run
  applied none, HNSW index valid. Two first-ever runs racing on
  `CREATE TABLE IF NOT EXISTS bmlibrarian_migrations` are covered by the
  existing fall-through (the loser's create fails once the winner commits;
  it then reads the table).

- **Investor demo, 2026-11-23**: held, went fine, no follow-ups. Runbook
  `doc/users/investor_demo_runbook.md`; the prepared library (`~/.bml-demo`,
  `~/BMLibrarian-demo`, server :5418) is still being built by the runbook's
  retry loop (log `~/.bml-demo/build.log`). Spec and plan:
  `docs/superpowers/specs/2026-11-15-investor-demo-europepmc-design.md`,
  `docs/superpowers/plans/2026-11-15-investor-demo.md`. Open from that work:
  #469 (topic rounds re-fetch unsettled days), #467 (DMG login item).

- **Signed, notarized macOS DMG of the Tauri app** (PR #466, merged
  2026-11-21).
  `scripts/build_bmlibrarianV2_installer.sh [--unsigned]` ships `bml` as an
  `externalBin` (`Contents/MacOS/bml`, where `bml_beside` looks), signs with
  the first Developer ID (or `DEVELOPER_ID`), notarizes and staples through
  the Keychain profile `bmlibrarian-notarize`. The app has BMLibrarian Lite's
  icon. Final-check fixes (2026-11-20): `CARGO_TARGET_DIR` is honoured
  (before, a set one bundled a stale `rust/target/release/bml`), the
  preflights test-sign a scratch file and print notarytool's own error,
  `APPLE_SIGNING_IDENTITY`/`APPLE_CERTIFICATE` are unset for Tauri, only a
  `bundle_dmg.sh` failure is retried (first log kept), leftover `rw.*.dmg`
  images are deleted, `notary.log` is kept beside the DMG and a rejection
  prints Apple's log; the user guide gained "Installing" (drag to Applications
  before setup, since setup records the app's path). Verified: `shellcheck`,
  both preflight failures, an `--unsigned` build with a relative
  `CARGO_TARGET_DIR`; the signed run was done before these fixes (notarization
  Accepted, `spctl` Notarized Developer ID). Second final check (2026-11-21):
  the DMG is named `….incomplete.dmg` until every check passes and
  `--unsigned` writes `…_unsigned.dmg`, so no failed or test build carries the
  release name; a stapling failure prints the retry command; leftover-image
  cleanup touches only this build's images. **Not done:** the setup wizard
  from the installed DMG app (owner), Intel/universal builds. The demo runbook
  still runs the cargo-built `bml-app`; the DMG is an option, not a change.

- **#460 leftovers: `FulltextSource`, topic years, "none offered"**
  (2026-11-17, branch `chore/460-leftovers`). `bml_library::FulltextSource
  { Medrxiv, EuropePmc }` (from `LibrarySource`) replaces the source strings
  in `Paper.source`, `fulltext::run`/`next_paper`, `metadata::run_window` and
  `status`. `topics::TOPIC_FIRST_YEAR`/`TOPIC_LAST_YEAR` (2021, 2026) build
  the query's `PUB_YEAR` range and `europepmc_first_day()`
  (`EUROPEPMC_FIRST_DAY` is gone); a `bml-app` test checks screen 4 names the
  same years (static text, `shortcut:`). `library status` counts papers with
  no full-text link apart ("N none offered", `LibraryStatus::no_link`) by the
  same condition `next_paper` reads (`fulltext::offers_link`), so "not tried
  yet" reaches 0. New tests: `update_topic` with full text down
  mid-rounds, a complete topic update stamps `last_update_at`, the status
  split, and (PR #465 review) the medRxiv split and a full text indexed before
  the network goes. Final check: one shared format constant per source in
  `fulltext.rs`, `offers_link` is `pub(crate)`, `status` errors instead of
  counting a non-integer as 0, and the medRxiv split test also covers a NULL
  DOI, an html-only link and a NULL or non-numeric version. This closes #460
  (its short-walk item was settled by the #790 re-pin). Verified: `cargo test
  -- --include-ignored` 360 passed with pg_search, `-p bml-app --
  --include-ignored` 25, Python 4871 passed (the one failure,
  `test_browser_download.py::test_simple_pdf`, a live-URL timeout, passed on
  rerun).

- **A window closed mid-setup reopens the wizard, #462** (2026-11-16,
  branch `fix/462-reopen-mid-setup`). `bml-app` `state::start_screen` opens
  on Search only when a library is recorded **and** the embedding GGUF is at
  `bml_setup::gguf_path` (setup records the library in step 2 but downloads
  the GGUF last; bmlib renames the download into place only once verified).
  Otherwise it opens on Welcome and setup, re-run, skips the steps already
  done (a cut-off download starts again). The prepared demo config
  `~/.bml-demo` has the GGUF, so it still opens on Search. Verified:
  `cargo test -- --include-ignored` 357 passed with pg_search,
  `cargo test -p bml-app -- --include-ignored` 24 passed (tests for a
  leftover `.part` file and an unreadable library record added in review);
  Python suite 4872 passed. Not checked by hand in the app. Screen 2
  (`library_folder`) now shows the saved library folder when setup already
  recorded one (a CLI setup with `--library-dir` that stopped before the
  GGUF), not always `~/BMLibrarian`.

- **bmlib #790 re-pin and two #460 items** (2026-11-16). bmlib pinned at
  `6465096` (Europe PMC walk by `FIRST_IDATE`, 3-day settle, short walks
  fail the day); a 200 HTML page in place of JATS/PDF
  (`RequestOutcome::WebPage`) is never cached as full text, three in a row
  end the phase as no network; `open_db` runs the `bml-db` migrations. Not
  checked: Windows build with the re-picked `windows-sys` versions.

- **Demo polish from #460** (2026-11-16, PR #461): search model warms in
  the background (`warm_search`); ⌘Q/close waits up to 15 s for the update
  to stop after the paper in flight (`pause_before_exit`); an empty
  topic-less library reopens on screen 4 (`LibraryCounts::needs_topic`).
  **Not verified by hand:** ⌘Q during an update and the screen-4 return
  (rehearsal checks in `doc/users/investor_demo_runbook.md`).

- **Mid-November audit fixes** (2026-11-15; details in git history and the
  issues): a failed settings load at login blocks `sync_to_database` until a
  load succeeds (#437; #438 still open); `ChunkEmbedder` keeps old chunks
  until the new ones are embedded (#435); `pdf_matcher` never replaces a
  different PDF at the target and the DOI/PMID fast path works (#443, #436;
  follow-ups #456); `bml server init`/`setup` accept a moved PostgreSQL bin
  folder, re-download a missing bundle, and handle the superuser password
  more carefully (#447, #448, #452).

- **bml-library minors from the piece 3 review** (2026-11-14, #428). bml-db
  **migration 3** adds `publication_fulltext.version_tried`: a newly posted
  version is tried at once with its attempts counted from 0, not after the
  old version's `retry_after` (up to 30 days). A request with no answer is
  stored as "no answer" (the transport message goes to the progress line),
  so `bml library status` groups the papers under one reason. Linux
  `schedule`: a failed unit write puts both files back
  (`restore_update_units`, each file not put back named), the undo reloads
  systemd only if it had read the new units (a failed reload only is "not
  loaded again", not a leftover), and `manual` runs `daemon-reload`; the
  leftover / not-reloaded error texts no longer say "start at login".
  `bml_library::testing` sits behind a `test-support` feature. Items 3, 4,
  5, 7 and 9 had already landed with #429. Review follow-ups: #433 (a
  half-done `enable --now` symlink), Windows schedule log on #397.
  Verified: `cargo test -- --include-ignored` 305 passed with pg_search;
  Linux and Windows clippy pass for `bml-pgserver` (cross-target checks,
  not run there).

- **Library pipeline, piece 3 of the installer milestone** (2026-11-14, PR
  #429; plan `docs/superpowers/plans/2026-11-14-library-pipeline.md`). bmlib
  is pinned by **git rev** (now `6465096`, see the #790 entry). New crate
  `rust/bml-library`: metadata (`medrxiv-details`, 30-day windows), full text
  (Tier 0 through `PoliteClient`, 30 s spacing, the first 429 ends the phase
  and sets `library_state.rate_limited_until`), index (abstract plus JATS/PDF
  chunks, `halfvec` embeddings, one transaction per paper); bml-db migration 2
  `library_state`; CLI `bml library update|status|schedule`. The workspace
  keeps `[profile.dev.package.mupdf-sys] opt-level = 2` (MSVC runtime clash
  with llama.cpp). Design details and review fixes:
  `doc/developers/library_pipeline.md`, `doc/users/library_updates_guide.md`.
  Deferred: #430 (#428 since fixed). **Finding:** medRxiv JATS `<body>` often
  holds only `<supplementary-material>`, so the PDF is fetched; the plan's "28
  of 30 JATS" counted downloads, not article text. Not run: Linux/Windows
  schedulers (cross-target clippy only).

- **`bml-db` + schema, piece 2 of the installer milestone** (2026-11-13,
  plan `docs/superpowers/plans/2026-11-13-bml-db-schema.md`; owner
  decisions: all Goal B tables now, `--library-dir` **replaces** `bml setup
  --data-dir`, a new setup step `Library`). New crate `rust/bml-db`:
  `library` (record `bml-library.json`; default `~/BMLibrarian` with
  `documents/` = bmlib `FullTextCache` root and `database/` for a new private
  server; a different `--library-dir` later is refused) and `migrate()`
  (session advisory lock — two concurrent `CREATE TABLE IF NOT EXISTS`
  collide in `pg_class` without it — then bmlib `ensure_schema` every run,
  then `run_migrations`). Migration 1 creates `publication_fulltext`
  (`form` + retry state; a full-text form needs `cache_path`), `chunks`,
  `chunk_embeddings` (`halfvec(256)` + HNSW m 16 / ef 64),
  `publication_index` (`ChunkSetLabel` fields; `complete` needs them all) and
  a BM25 index (pg_search) or `text_tsv` + GIN; `lexical_index()` says which.
  Migrations run as `bml_app` (owns the database, so no GRANTs). Setup order
  is now Hardware, Database, Library, Autostart, …; a new private server
  records its library once `init` succeeds; servers saved earlier keep their
  folder (`<config>/pgdata`), also with `--pg-bindir`. Docs:
  `doc/developers/rust_db_schema.md`, `rust_setup.md`, `bml_setup_guide.md`.
  Verified: `cargo test -- --include-ignored` 245 passed with pg_search and
  without; hand run on the owner's Mac with the real pgdist bundle (12
  tables owned by `bml_app`, BM25 + HNSW indexes, second run "already in
  place").
  Not covered: pg_search installed after migration 1 keeps tsvector
  (`shortcut:` in `schema.rs`); BM25 is not tested in the `rust` CI workflow
  (#399), only in the `pgdist` PR build (its paths include `rust/bml-db/**`).
  Review follow-ups: #424.

- **Bundled PostgreSQL (pgdist), piece 1 of the installer milestone**
  (2026-11-11 to 11-13, PRs #417, #420, #422; closes #416, #418, #419,
  #421). Release **`pgdist-18.6-r1`** (theseus PG 18.6.1, pgvector v0.8.7,
  pg_search 0.26.6 on macOS arm64/Linux) is pinned in
  `rust/bml-setup/pgdist-release.json` with OS floors (`requires`: macOS 15,
  glibc 2.36, checked before download). Design
  `docs/superpowers/specs/2026-11-11-installer-walking-skeleton-design.md`;
  docs `doc/developers/pgdist.md`, `doc/users/bml_setup_guide.md`. Verified
  by hand on macOS arm64 only. Open: #397 (Windows).

- **Early-to-mid November 2026, Python side** (details in git history and
  the linked docs): paper-weight sample sizes read thousands separators and
  placeholder rows are no longer served from the cache
  (`failure_placeholder_reason`; #358, #357; open: #414); plain `pytest
  tests/` is hermetic (`--run-live` / `BMLIBRARIAN_TEST_DB_ENV`,
  `_block_live_services`; #334, #251; `test_database_guard.md`); the SQL
  settings-category lists are tested against `VALID_SETTINGS_CATEGORIES`
  (migrations 036/037; #231); research-tab messages are toasts
  (`gui/qt/widgets/toast.py`; #332; other modals: ROADMAP §5); queue Ctrl-C,
  task ownership (`worker_id`) and recovery counts (#384–#386, #388, #294;
  `queue_recovery.md`); failed migrations are fatal (#342, #378, #379, #381).
- **Installer pieces before 2026-11-11** (PRs #396, #402, #404, #407;
  closes #398, #403, #405, most of #401): `bml-pgserver` (private per-user
  PG18 on 127.0.0.1:5418, `bml server init|start|stop|restart|status|
  autostart`; docs `doc/users/private_postgres_server.md`,
  `doc/developers/rust_pgserver.md`) and `bml-setup` + `bml setup`
  (hardware, database, autostart, Ollama pinned v0.40.10 with
  checksum-verified installers, models — `medgemma1.5:4b-it-q8_0` pulled and
  `/api/copy`'d to `medgemma4B_it_q8:latest` — and the embedding GGUF; docs
  `doc/users/bml_setup_guide.md`, `doc/developers/rust_setup.md`). An
  existing server is never restarted by bml (`bml-external.json`). Still
  open on #401: bmlib-side items and crates.io 0.3.1, an existing-server
  `status` test, installed-Ollama version never checked; Windows/Linux
  installs unverified (#397); #399 (port moved after init, `pg_search` in
  CI).

- **Early November / October 2026 slices** (details in git history and the
  linked docs): fact-checker SQLite → PostgreSQL migrator hardened (verdicts
  stored with their evidence per statement, `review_status` kept, whole
  processing sessions, per-row `ROW_ERRORS` only, `--dry-run` writes inside a
  forced-rollback transaction; #376, #392, #395, #408, #410;
  `scripts/MIGRATION_GUIDE.md`); concurrent fact-check evaluations lock the
  statement row (#230); queue reused-PID check via `process_started` (#388);
  fact-check verdicts stored with their evidence in one
  transaction (`FactCheckerDB.store_verdict`), audit queries in
  `audit_cursor` (#340, #341, #376); PRISMA semantic-chunk
  consolidation calls `LLMClient.chat`, LLM boundary test also flags raw
  Ollama REST literals (#252, #250); settings saved in other tabs publish
  `AGENTS_NEED_REINIT_EVENT` so the research tab rebuilds its agents, Chrome
  fallback promotes PDFs by content (#372, #329, #335);
  lab `cleanup()` stops the orchestrator, research tab rebuilds stale agents
  on the next Start (#331, #370, #330); TransparencyAgent failures raise
  `TransparencyAssessmentError`, batches return `TransparencyBatchResult`,
  the CLI `assess` no longer crashes before saving (#274;
  `tests/test_transparency_*`); paper-weight sub-agent uses the review's
  `db_manager`, `assess_full_paper` raises without full text, chunk inserts
  use savepoints (#366; `systematic_review_pipeline.md`);
  systematic-review search, resume and paper-weight steps take the agent's
  `db_manager` (#285, #366; `systematic_review_pipeline.md`); evaluation-run
  lifecycle tested on real SQL (#287); PMIDs come from the PubMed source id
  (`pmid_select_expr`, `pubmed_source_id`, `extract_pmid`; #344, #280, #361,
  #363); composite scorer uses real paper weight, rigor (worst bias domain)
  and sample size, leaving unscored dimensions out (#348, #351, #356;
  **rankings changed**); paper-weight failures raise instead of becoming
  scores (#345, #347, #275); fact-checker review GUI shows cited passages
  and `Citation.widened_from` is stored (**migration 035**; #338, #310);
  citation rejection counts reach the Qt research tab and CLI (#292); full
  suite green (PR #336); Find PDF hardening (PRs #313–#328; open: #320);
  fragments widened to complete sentences (PRs #306/#311, #304;
  `doc/llm/sentence_bounds.md`); fact-check token budget scales with
  citations and the 76 fallback verdicts were re-run on `knowledgebase`
  (PR #300); citation quality policy (PRs #288, #297–#299; **migration
  034**; `search_hybrid` reports `strategies_failed` but the Qt tabs don't
  show it yet; `DocumentScoringAgent`'s regex score fallback and HyDE in
  `search_hybrid` still open); bmlib 0.10 adopted (PR #295); Flet retired
  (PR #277; gaps ROADMAP §1); PMC discovery via the PMC Cloud Service
  (PR #282; `pmc_bulk_cli` still broken → #283). `~/.bmlibrarian/config.json`
  uses `gpt-oss:20b` for query/scoring/citation.
- **Database state** (2026-10-15): the clean PubMed import (41.2 M records)
  is PG18 **`bmlibrarian_dev`** (:5532); PG18 `bmlibrarian` was dropped.
  `knowledgebase` (:5432) holds user data (factcheck, audit, paper weights),
  Europe PMC full texts and the running apps. Vectors will be embedded from
  scratch, 256 d (`doc/planning/rust/implementation_plan.md`). Document IDs
  differ between databases; carry-over must remap by PMID/DOI. PubMed
  withdrawals are marked in `document.withdrawn_date` (migrations 032/033;
  033 drops an empty column in `knowledgebase` on its next non-test
  connection). `db_test_guard.py` makes every non-dev/test DB read-only under
  pytest; direct `psycopg.connect()` callers are not covered (ROADMAP §2).
- **July 2026 review follow-ups**: see `doc/TODO_code_review_2026-07.md`.
  LLM calls go through `bmlibrarian.llm` only (`tests/test_llm_layer_boundary.py`);
  `db_conninfo.build_conninfo()` builds libpq strings; archive extraction is
  guarded by `utils/path_utils.is_safe_archive_member()`.
## Next up

The 2026-07-19 review's imminent P1 items are done or deferred to
ROADMAP. Candidates, in rough order of
value — pick one, or pull an item from ROADMAP.md:

- **Rust installer**, design
  `docs/superpowers/specs/2026-11-11-installer-walking-skeleton-design.md`:
  pieces 1 (pgdist), 2 (`bml-db`) and 3 (library pipeline) are done.
  1. Measure how many medRxiv JATS files carry the article body (the hand
     run's two had only supplementary material), since that decides how
     often the Cloudflare-blocked PDF is needed. Rates between 1.5 s and 30 s
     are still unmeasured too.
  2. In progress: **3c, MECA bulk**, the main full-text route for the
     backlog (plan `docs/superpowers/plans/2026-11-14-meca-bulk.md`; owner
     decisions 2026-11-14: hand-written SigV4, small paid measurement
     requests allowed).
     - **bmlib Tasks B1–B3 merged** (bmlib PR #775, 2026-11-14;
       `bmlib.fulltext.meca` / `bmlib::fulltext::meca`, feature `meca`):
       SigV4, ListObjectsV2, plain-language S3 errors, verified atomic
       download, Rust `HttpClient::get_with_headers_stream`, ureq ≥ 3.5.
     - **Blocked on the owner, Task M0** (re-checked 2026-11-15): both AWS
       profiles (`bmlibrarian` project, `medrxiv` account 775221585284) are
       region-locked to ap-southeast-2 (an SCP, confirmed for the project,
       presumed for the medrxiv account), so no signed S3 read in
       us-east-1 (where `medrxiv-src-monthly` lives) can succeed; IAM
       policies won't fix it. Ways out: activate advanced features on the
       project and edit the SCP, or use a separate standard AWS account.
       Then measure: count, size, manifest shape, JATS body rate (the first
       half of item 1) and licensed fixture packages. B4 (the package
       reader) waits for M0.
       `scripts/download_medrxiv_meca_sample.py` (untracked) is the owner's;
       leave it alone.
     - Then L1–L5: the bulk route in `bml-library` (pin past B4, migration 4
       `meca_packages`, AWS keys file, bulk phase only for an "All of
       medRxiv" library, CLI).
     After 3c: 3b (medRxiv HTML page, bmlib). Pieces 4 (`bml search`),
     5 (Tauri app) and 6 (signed Mac DMG) have landed.
  3. bmlib is pinned by git rev; move to a tagged release (or crates.io,
     #401) once one contains #760 and #770 (v0.13.0 has neither).
  `bml-pgserver` leftovers: #397 (needs Windows), #399 (owner decision on a
  port taken after init); bml-db review follow-ups: #424;
  bml-library: #430, #433.

- **2026-11-13 repo audit issues #434–#453** (filed 2026-11-14; #434–#437,
  #439–#450, #452 fixed). Installer: #451 (setup replaces another config
  folder's login entry), #453 (rust.yml permissions, SHA-pinned checkout).
  Broken: #438 (seed defaults override config.json/env after login). Also
  #472 (secret-save failures only logged, browser-fallback cookies).

- Remaining citation rejections: 10 of the 106 #303 pairs are below the
  similarity threshold (long multi-sentence quotes that drift). Known sentence-bounds misses: lost text with a single
  space (`8.8%) MAE rates`), multi-word fused labels.
- Widening decisions from the PR #306 review: #308 (widen one-word quotes,
  or require a minimum fragment size?), #309 (fragments still lost at text
  end without a full stop, inside broken-off sentences, past 400 chars).
- #320 — after rejecting every discovered source, the doi.org fallback may
  fetch the same PDF again (owner decision needed: skip fallback, compare
  redirect target, or document).
- #414 — paper weight lab's Recent Assessments list: label placeholder /
  old-version assessments (small; reuse `db.failure_placeholder_reason`).
- #283 — rebuild `pmc_bulk_cli` list/download/sync on the PMC Cloud
  Service S3 inventory (structural; discovery side already ported).

## LLM-layer polish follow-up (from 2026-07-22 slice)

The BaseAgent per-call-override work (PR #254) unblocks two
more standalone-agent migrations that were deferred to keep that slice's
regression signal clean. Both are optional consistency polish — they already
route through the LLM layer correctly:

- **`agents/query_generation/generator.py`** (`MultiModelQueryGenerator`):
  a multi-model fan-out that builds its own `LLMClient`. Now migratable via
  the new per-call `model`/`temperature` overrides (each `.chat(model=…)`
  call becomes `self._make_llm_request(..., model=m, temperature=t)`), which
  would roll all models' token usage into one metrics object. `num_predict`
  is already fixed (`QUERY_GENERATION_MAX_TOKENS = 800`); it does **not**
  hardcode 100 as older notes claimed.
- **`qa/document_qa.py:answer_question`**: a module-level function using
  `think=`. The `think` passthrough now exists on `_make_llm_request`, so
  converting it to a small QA agent is possible — but that's a caller-facing
  API change (callers pass `model`/`host`/`temperature` directly), so weigh
  the churn before doing it.

Re-verify all line numbers against current `HEAD` before fixing — they will
have drifted since the 2026-07-19 review. Full details, including the
"Known accepted trade-offs" reasoning behind some of these, are in
`doc/TODO_code_review_2026-07.md`.

### Verify

- **The full suite is green** since PR #336: `QT_QPA_PLATFORM=offscreen uv
  run python -m pytest tests/ -p no:cacheprovider --no-cov -q` on 2026-11-25:
  **5012 passed, 75 skipped** in about 3 min (hermetic since #334;
  add `--run-live` for the live tests, which read the configured database). Without
  `offscreen`, `test_annotation_widget.py::...::test_explanation_field_typing`
  can fail when another app holds OS focus (`qWaitForWindowActive`). No `--continue-on-collection-errors` or marker deselection needed;
  any other failure is a regression. Save the
  output to a file in the scratchpad (don't just tail it), and don't edit or
  `git stash` the tree while it runs.
- `ruff check .` / `mypy src/` carry pre-existing debt (~1,745 ruff findings);
  the gate is **no new errors**, not a clean baseline. Quick regression check:
  `git stash`, run `ruff check --select F401,F811,F821,F841 <touched files>`,
  compare to your tree (normalize away line numbers).
- Rust: `cd rust && cargo test`; with a real PG18 (and pg_search for the BM25
  branch) add `-- --include-ignored` (env vars in CLAUDE.md, memory
  `reference-local-pg18-bindir`): 307 passed on 2026-11-15 with pg_search
  (305 after #428). The first build
  compiles llama.cpp and MuPDF (about 1.5 min on the owner's Mac).
- `uv run python bmlibrarian_cli.py --quick` still runs end-to-end for a
  manual smoke check when touching the core agent workflow.
- Never run destructive tests against the production `knowledgebase`
  database — use `bmlibrarian_dev` (see CLAUDE.md
  "Database Safety"). Opt-in DB tests: `BMLIBRARIAN_ENV_FILE=~/.bmlibrarian/.env_pg18_dev
  BMLIBRARIAN_TEST_DB_ENV=~/.bmlibrarian/.env_pg18_dev uv run python -m pytest …`.
