# HANDOVER

Working notes for picking up in-flight work. Each section is one
self-contained slice: what's known, where to start, and how to verify.
Remove a section once its slice has landed; add a new section when handing
off new work. Longer-term structural items live in
[ROADMAP.md](ROADMAP.md) — pull one in here once you're about to start it.

---

## Recently landed (context)

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
  the network goes. This closes #460 (its short-walk item was settled by the
  #790 re-pin). Verified: `cargo test -- --include-ignored` 361 passed with
  pg_search, `-p bml-app -- --include-ignored` 25, Python 4872 passed.

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

- **bmlib #790 re-pin and two #460 items** (2026-11-16, branch
  `chore/bmlib-790-repin`). `rust/Cargo.toml` pins bmlib main at #790's
  merge, `6465096`. Its review changed the Europe PMC walk: days are the
  first-index day (`FIRST_IDATE`), the settle period is 3 days, a walk short
  of `hitCount` or holding a record not indexed on the day fails the day, and
  an empty day costs one more request (an undated probe). The pipeline test
  fixtures gained `firstIndexDate` and the probe route. A 200 HTML page in
  place of JATS/PDF (`RequestOutcome::WebPage`, a Wi-Fi sign-in page,
  XHTML included) reaches bmlib as an error, so it is never parsed or cached
  as full text; the paper is passing, not lasting (30 days), and three in a
  row end the phase as no network (`NO_ANSWER_LIMIT`). The app's `open_db` runs the `bml-db`
  migrations, as the CLI does. bml-app tests no longer race for a port
  (`SERIAL`). Verified: `cargo
  test -- --include-ignored` 357 passed with pg_search, `-p bml-app` 22
  passed six runs in a row; live, a fresh "Depression & anxiety" library
  with `--skip fulltext --skip index` for 3 minutes fetched 187 papers,
  67 days complete, 0 failed (Ctrl-C, exit 4). Not checked: Windows build
  with the lockfile's re-picked `windows-sys` versions.

- **Demo polish from #460** (2026-11-16, PR #461). The
  app's search screen loads the search model in the background
  (`warm_search` → `Ask::Warm`), so the first search no longer waits
  seconds. ⌘Q and closing the window end in `RunEvent::Exit`, where
  `pause_before_exit` hides the window and waits up to 15 s
  (`Update::pause_and_wait`) for the update to stop after the paper in
  flight; before, the process exited mid-paper (the old `CloseRequested`
  pause never got the time to act). A recorded library with no papers and no
  topic reopens on screen 4 (`LibraryCounts::needs_topic`), and an update
  started there anyway is refused (`CHOOSE_TOPIC_FIRST`) rather than filling
  it with medRxiv papers, after which no topic can be chosen. Verified:
  `cargo test -p bml-app -- --include-ignored` 22 passed; the dev app opened
  on the prepared library had the GGUF open and ~40 s of CPU before any
  search. **Not verified by hand:** ⌘Q during an update and the screen-4
  return (osascript may not send keystrokes here); both are rehearsal checks
  in `doc/users/investor_demo_runbook.md`.

- **Failed settings load no longer lets Save overwrite settings, #437**
  (2026-11-15). If `_sync_from_database` fails at login, login goes on with
  JSON/default settings, but `sync_to_database` raises `RuntimeError` until
  a later load succeeds (`_db_load_failed`, public `settings_load_failed()`).
  A failure anywhere in the load, including the merge of a malformed reply,
  sets the block. `_sync_from_database` now raises, so the "load from
  database" buttons report failures, and the Qt app shows a warning toast at
  login. The Qt callers (config tab Save and Sync, profile widget, JSON
  import offer) and `import_from_json` check the `False` that
  `sync_to_database` returns on a partial failure; a config-tab Save whose
  database part fails shows "Saved Locally Only", not "Success". Tests in
  `tests/test_config_user_context.py` and
  `tests/test_gui_db_settings_integration.py`. Not run against a live
  database. #438 (seed defaults override config.json/env after login) is
  still open.

- **Chunk embedder keeps old chunks on failure, #435** (2026-11-15).
  `ChunkEmbedder.chunk_and_embed` embeds every chunk first, then deletes the
  old chunks and inserts the new ones in one transaction; a missing embedding
  or a failed insert raises `ChunkEmbeddingError` (the per-chunk savepoints
  from #366 are gone). The stored chunks stay only if their positions still
  match the current `full_text`; chunks are offsets into the text, so after
  a text change they are deleted (`_settle_old_chunks`; a same-length edit
  that keeps every boundary is not detected). `process_queue` keeps the
  document queued with the error; `rechunk_all`/`chunk_document_list` return
  `failed_ids`, printed by `scripts/rechunk_semantic_chunks.py`. Every other
  caller already caught exceptions. Tests in `tests/test_chunk_embedder.py`;
  not run against a live database or Ollama.

- **pdf_matcher fixes #443, #436** (2026-11-15). `import_pdf_for_document`
  never replaces a different PDF already at the target (status `skipped`,
  reason names the stored file; it used to keep the newer file by mtime, so
  supplementary material carrying the article's DOI could replace the
  article). The same holds when the document's recorded `pdf_filename` is a
  different file at another path. The copy goes to `<name>.partial` and is
  renamed into place. A failure removes only our own copy, never one the
  database already points at, and a failed delete is logged, not raised.
  `check_document_status` no longer selects the nonexistent `document.pmid`
  column, so the regex DOI/PMID fast path works instead of failing silently.
  Tests are in `tests/test_pdf_matcher_agent.py`. Not run against a live
  database. The missing `lower(doi)` index is still #333. Follow-ups from
  the review (an orphan file reads as `duplicate`, the status lookup
  swallows SQL errors) are in #456.

- **Installer audit fixes #447, #448, #452** (2026-11-15). `bml server init`
  / `bml setup --pg-bindir` accept a moved PostgreSQL bin folder whose major
  version equals the data folder's `PG_VERSION` and save it (another major
  is `DataDirVersion`); re-running with a saved bin folder that is gone is
  `BinDirGone`, whose message says to pass the new one and repeat
  `--extension-dir`; `server start/stop/status` report it too (#447). The
  Database step moves a resumed server onto the pinned bundle (downloading
  it) when the bundle folder it ran from is gone, whatever its version
  (`bundle_missing`; a folder still present is left to `init`) (#448).
  `bml setup` removes `BML_PG_SUPERUSER_PASSWORD` from its environment once
  read, refuses `--password-stdin` from a terminal and says when the
  variable is not UTF-8 (#452). Verified: `cargo test
  -- --include-ignored` 307 passed with pg_search; by hand with the real
  bundle in a temp config folder: deleted `pgdist/18.6-r1` → setup
  downloaded it again and resumed (status exit 0, vector + pg_search);
  moved the bundle → `server init --bindir <moved>` started the old data
  and saved the new path. Not run: Linux/Windows; the terminal refusal
  (no tty in tests).

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

- **Library pipeline, piece 3 of the installer milestone** (2026-11-14,
  branch `feat/library-pipeline`; plan
  `docs/superpowers/plans/2026-11-14-library-pipeline.md`; owner decisions
  this session: bmlib pinned by **git rev**, without waiting for a release, to
  `c5f6236`: bmlib PR #770 (the Rust `pdf` feature did not compile on
  Windows) on top of main with #760 `medrxiv-details` and #763; #770 was
  merged into bmlib main on 2026-11-14, so the pin is on main, and
  `<library>/documents` stays a `FullTextCache`). PR #429 merged 2026-11-14.
  The workspace keeps `[profile.dev.package.mupdf-sys] opt-level = 2` (MSVC
  would not link MuPDF's Debug runtime beside llama.cpp's Release one).
  New crate `rust/bml-library` (bmlib features `pdf` + `embed`): metadata
  (bmlib sync of `medrxiv-details`, 30-day windows), full text (Tier 0 only through
  `PoliteClient`: 30 s spacing, the first 429 ends the phase uncharged and
  sets `library_state.rate_limited_until`; lasting/passing back-off; a new
  version replaces the old in one transaction, a failed new version keeps
  the old; replaced versions' files deleted via the `cache_deletions`
  queue, unreferenced files kept), index (abstract chunk always plus
  canonical JATS/PDF chunks, `halfvec` embeddings and the `ChunkSetLabel`
  in one transaction per paper). bml-db migration 2: `library_state`. CLI:
  `bml library update [--from] [--skip]` (worker lock, Ctrl-C, exit 0/1/2/4),
  `status`, `schedule weekly|every <days>|manual` (`bml_pgserver::schedule`:
  a daily LaunchAgent / systemd timer / Scheduled Task running `update
  --if-older-than <days>`; only a complete update stamps `last_update_at`).
  Final-review fixes: the index runs before and after full text (abstracts
  searchable within the hour), `--from` is remembered (`from_day`), replaced
  files go through a `cache_deletions` queue (no sweep of unreferenced
  files), a paper failing to index no longer blocks the others (cursor; 3 in
  a row stop the phase), Linux logs to the file. PR #429 review fixes: an
  index read failure that may pass (I/O, PDF engine, `PDF_READ_DEADLINE`)
  keeps the file and retries instead of demoting the paper; fetching a full
  text no longer deletes the paper's chunks; a run with `--skip` is not a
  complete update; a metadata 429 stops early (exit 4); a PDF that could not
  be saved is passing; a busy lock exits 4; SIGTERM stops like Ctrl-C; the
  Linux update unit runs `After=bml-pgserver.service`. Deferred: #430
  (backlog stalls metadata, fetch-phase PDF deadline needs bmlib, macOS
  login race) and #428.
  `bml_setup::gguf_path` is public. Docs: `doc/developers/library_pipeline.md`,
  `doc/users/library_updates_guide.md`, `rust_db_schema.md` (migration 2).
  Verified: `cargo test -- --include-ignored` 300 passed with and without
  pg_search; macOS schedule hand-checked with `launchctl print` (removed
  by `manual`; that check predates the daily `StartCalendarInterval` design
  and was not repeated); hand run against the real API and model on
  a temp server: 3 days, 153 papers indexed in 88 s, two papers' full text
  (both PDFs), Ctrl-C stopped after the paper in flight with exit 4.
  **Finding:** those papers' medRxiv JATS `<body>` held only
  `<supplementary-material>`, so bmlib reports no body and the PDF is
  fetched; the plan's "28 of 30 JATS" counted downloads, not article text.
  Not run: Linux/Windows schedulers (cross-target clippy only).

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

- **Investor demo (current focus, meeting 2026-11-23)**: spec
  `docs/superpowers/specs/2026-11-15-investor-demo-europepmc-design.md`,
  plan `docs/superpowers/plans/2026-11-15-investor-demo.md`. PR #459
  (Europe PMC topic libraries, `bml search`, the Tauri app) merged
  2026-11-16. It replaces the MECA route: both AWS accounts are
  region-locked "projects" that cannot read us-east-1 S3. **Left: the
  owner's rehearsal** (plan Task 16, by 2026-11-22), following
  `doc/users/investor_demo_runbook.md` and its rehearsal checks.
  - **Measured 2026-11-15** (demo Mac, Europe PMC from Australia, topic
    "Depression & anxiety", trials and reviews 2021–2026, 8,372 papers): the
    paper-details search takes ~3.5 s per day (2,140 days, ~0.9 s per paper).
    Full text came back as JATS for 46 of 46 papers, ~6 s each. Each paper
    makes ~93 passages, embedded at ~30 passages/s (~3.1 s per paper). That
    is ~10 s per paper in all, **~23 h for the whole topic**. Disk: ~0.2 MB
    of documents and ~1 MB of database per paper.
  - The prepared library: config `~/.bml-demo`, library `~/BMLibrarian-demo`,
    server on :5418, no login items, schedule manual. Built detached
    (`nohup caffeinate -i ~/.bml-demo-bin/bml --config-dir ~/.bml-demo
    library update`, log `~/.bml-demo/build.log`); if it stops, run the same
    command again; it resumes. It stopped on 2026-11-16 15:43 when the
    network dropped (4,954 papers, all indexed, 4,883 JATS, 45 failed days
    back to 2023-10) and was resumed on 2026-11-17 08:31 AEST; a DNS drop-out
    stopped it again minutes later and it was restarted. Under the new walk
    2026-11-01/02 fail the 50% floor against counts stored by the old walk,
    so they show as failed days for up to 33 days (bmlib #793).
  - `~/.bml-demo-bin/bml` was rebuilt from master on 2026-11-17 (release, at
    `d4403f6`: bmlib `6465096`, first-index-day walk, `library status`
    counting the topic's days); the 2026-11-15 binary is kept beside it as
    `bml.2026-11-15`. The day ledger keeps the days completed under the old
    walk (bmlib #793, query-blind ledger). The app is built separately
    (runbook step 2). It predates PR #465, so it prints no "none offered"
    and counts those papers under "not tried yet": rebuild it from master
    once #465 is merged.
  - #460 (PR #459 review follow-ups) is closed by `chore/460-leftovers`
    (above).
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
     - **Blocked on the owner, Task M0** (re-checked 2026-11-15): the
       `medrxiv` profile (IAM user `bmlib`, account 775221585284) still gets
       `AccessDenied` on `medrxiv-src-monthly`, and also on arXiv's public
       requester-pays bucket `arxiv`, so the cause is on our account, not
       medRxiv's. S3 answered with `x-amz-request-charged: requester`. The
       user cannot read its own IAM policies either. Fix: attach a policy
       allowing `s3:ListBucket` on `arn:aws:s3:::medrxiv-src-monthly` and
       `s3:GetObject` on `.../*`, and check that the account has a payment
       method. Then measure: count, size, manifest shape, JATS body rate
       (the first half of item 1) and licensed fixture packages. B4 (the
       package reader) waits for M0.
       `scripts/download_medrxiv_meca_sample.py` (untracked) is the owner's;
       leave it alone.
     - Then L1–L5: the bulk route in `bml-library` (pin past B4, migration 4
       `meca_packages`, AWS keys file, bulk phase only for an "All of
       medRxiv" library, CLI).
     After 3c: 3b (medRxiv HTML page, bmlib), piece 4 (hybrid search,
     `bml search`), 5 (Tauri wizard), 6 (signed Mac `.dmg`).
  3. bmlib is pinned by git rev; move to a tagged release (or crates.io,
     #401) once one contains #760 and #770 (v0.13.0 has neither).
  `bml-pgserver` leftovers: #397 (needs Windows), #399 (owner decision on a
  port taken after init); bml-db review follow-ups: #424;
  bml-library: #430, #433.

- **2026-11-13 repo audit issues #434–#453** (filed 2026-11-14; #435, #436,
  #437, #443, #447, #448, #452 fixed). Installer: #451 (setup replaces
  another config folder's login entry), #453 (rust.yml permissions,
  SHA-pinned checkout). Data loss: #439 (MigrationManager commit/lock).
  Security: #434 (session cookies sent to any host), #450 (token files
  restricted after writing), #449 (PBKDF2 iteration count).
  Broken: #441, #445, #446, #438, #440, #442, #444.

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
  run python -m pytest tests/ -p no:cacheprovider --no-cov -q` on 2026-11-15:
  **4872 passed, 71 skipped** in about 3.5 min (hermetic since #334;
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
