# HANDOVER

Working notes for picking up in-flight work. Each section is one
self-contained slice: what's known, where to start, and how to verify.
Remove a section once its slice has landed; add a new section when handing
off new work. Longer-term structural items live in
[ROADMAP.md](ROADMAP.md) — pull one in here once you're about to start it.

---

## Recently landed (context)

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

- **pgdist: OS floor checked before download; #420 review follow-ups**
  (2026-11-13, closes #419, #421). `pgdist-release.json` gains `requires`
  (`macos` 15.0, `glibc` 2.36; the test `release_floors_match_the_build_inputs`
  ties them to `inputs.json`'s new `macos_build.min_os` and
  `linux_build.glibc`, and `build.sh` fails when theseus's `postgres`
  minimum macOS differs from `macos_build.min_os`). `pgdist::system_too_old`
  (macOS via `sysinfo`, glibc via `getconf GNU_LIBC_VERSION`; unreadable =
  let through) fails the Database step before `ensure_pgdist`. The "no
  pg_search build for this computer" reason now comes from the bundle's
  `pgdist.json` `pg_search: false` (`built_without_pg_search`), not from
  "runs from a bundle". `ensure_pgdist` deletes (or warns again about) a
  leftover archive whenever it finds the bundle installed (only reached
  while no server is saved; a saved server is resumed first), and
  `private_database` reports earlier warnings even when `init` fails.
  `build.sh` saves a `make -n` dry run of pgvector and fails on
  `-march=native` (macOS/Linux). The macOS/Linux `build.sh` changes run
  only in the `pgdist` workflow's PR build; not run locally.

- **Bundled PostgreSQL (pgdist), piece 1 of the installer milestone**
  (2026-11-11, PRs #417, #420, #422; closes #416, #418). Design:
  `docs/superpowers/specs/2026-11-11-installer-walking-skeleton-design.md`
  (Mac-first GUI wizard → private PG18 → medRxiv download/full text/chunk
  embedding → test search; owner decisions recorded there); plan
  `docs/superpowers/plans/2026-11-11-pgdist.md`. Release **`pgdist-18.6-r1`**
  is published (5 targets, built from `04edd55`) and pinned in
  `rust/bml-setup/pgdist-release.json` (`release_pins_every_target` checks
  that every `inputs.json` target has an asset), so `bml setup` with no
  database options downloads and installs it into
  `<config>/pgdist/18.6-r1/` (a saved server always wins; an explicit
  `--data-dir` must match a saved private server; `--data-dir` was since
  replaced by `--library-dir`, piece 2). Inputs: theseus-rs PG
  18.6.1, pgvector v0.8.7 from source (`OPTFLAGS=`, no `-march=native`;
  Linux built in pinned bookworm), ParadeDB pg_search 0.26.6 (macOS arm64,
  Linux only). Floors: macOS 15, glibc 2.36 (Ubuntu 22.04/RHEL 9 out);
  `build.sh` checks both, Windows `dumpbin` checks for pruned LLVM/Python.
  Windows rename retried on `PermissionDenied`; `jit = off`; `pg_ctl start`
  writes to `bml-pg_ctl.out` (a pipe hung Windows). The CLI test
  `failed_step_goes_to_stderr` now fails the Database step with a missing
  `--pg-bindir` (with assets pinned it would have downloaded the bundle).
  Verified by hand on the owner's Mac (macOS arm64, 2026-11-11): fresh
  `--config-dir`, `bml setup --skip autostart --skip ollama --skip models
  --skip embedding-model` downloaded the release asset, installed it,
  `server status` exit 0, `\dx` shows vector 0.8.7 + pg_search 0.26.6, a
  second run is "already in place" with no download.
  Docs: `doc/developers/pgdist.md` (Releasing, Bumping an input),
  `doc/users/bml_setup_guide.md`. Open: #397 (Windows).

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
  plan `docs/superpowers/plans/2026-11-15-investor-demo.md`, branch
  `feat/investor-demo-europepmc`. It replaces the MECA route: both AWS
  accounts are region-locked "projects" that cannot read us-east-1 S3.
  - **Measured 2026-11-15** (demo Mac, Europe PMC from Australia, topic
    "Depression & anxiety", trials and reviews 2021–2026, 8,372 papers): the
    paper-details search takes ~3.5 s per day (2,140 days, ~0.9 s per paper).
    Full text came back as JATS for 46 of 46 papers, ~6 s each. Each paper
    makes ~93 passages, embedded at ~30 passages/s (~3.1 s per paper). That
    is ~10 s per paper in all, **~23 h for the whole topic**. Disk: ~0.2 MB
    of documents and ~1 MB of database per paper.
  - The prepared library: config `~/.bml-demo`, library `~/BMLibrarian-demo`,
    server on :5418, no login items, schedule manual. Its full build started
    2026-11-15 23:10 AEDT, detached (`nohup caffeinate -i
    ~/.bml-demo-bin/bml --config-dir ~/.bml-demo library update`, log
    `~/.bml-demo/build.log`). If it stops, run the same command again; it
    resumes.
  - bmlib `feat/europepmc-sync` (worktree `../bmlib-europepmc`) is bmlib
    PR #790. `rust/Cargo.toml` pins its head, `25ab665`. Re-pin to the
    merged commit once #790 lands (ROADMAP, investor-demo follow-ups).
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
