# HANDOVER

Working notes for picking up in-flight work. Each section is one
self-contained slice: what's known, where to start, and how to verify.
Remove a section once its slice has landed; add a new section when handing
off new work. Longer-term structural items live in
[ROADMAP.md](ROADMAP.md) — pull one in here once you're about to start it.

---

## Recently landed (context)

- **Secret-save failures, browser cookies, #472** (2026-11-26, branch
  `fix/472-secret-save-cookie-scope`). `OpenAthensAuth._save_session()`
  returns whether it wrote the file; after a login whose save failed,
  `session_saved` is False and an error says the session lasts for this run
  only. `bmlibrarian_cli --save-session` prints a warning when the token
  could not be saved. The setup wizard's API-keys page creates a missing
  `.env` (0600) instead of writing nothing, and a failed save keeps the page
  open with the reason shown (clear the fields to go on without keys). The
  browser fallback (Playwright, persistent context, undetected Chrome) drops
  cookies without a domain (`scoped_browser_cookies()`, also used by
  `cookie_jar_from_browser_cookies`). **Not fixed (item 5):** host-only
  cookies still reach subdomains on the `requests` path, because
  `http.cookiejar`'s default policy has no host-only cookies and `requests`
  copies the jar into a default-policy one on every request (`shortcut:` in
  `cookie_jar_from_browser_cookies`). Verified: suite 5076 passed, 78
  skipped; the 7 new tests fail on the old code. Not run against a live
  OpenAthens login or in the wizard by hand.

- **Stale abstract chunks, #475** (2026-11-26, branch
  `fix/475-stale-abstract-chunks`). Migration 040 adds
  `trg_drop_stale_abstract_chunks` (AFTER UPDATE OF abstract on `document`,
  only when the value changes): it deletes the embeddings of the document's
  `abstract`-type chunks and the chunks no `public.evaluations` row
  references (no cascade there). This covers every importer, and the
  embedder's "no embedding" query picks the document up again. If
  `DocumentEmbedder` reuses its own chunk 0 with different text, it replaces
  the text and drops that chunk's embeddings. Pre-existing bug fixed:
  the embedder's `ON CONFLICT` upserts on `embedding_provider`,
  `chunking_strategies` and `chunktypes` failed on every database (no unique
  key on those columns), so `embed` could not start; it now selects, then
  inserts (`_get_or_insert_id`). Finding: `knowledgebase` abstract chunks
  are legacy `adaptive_text_chunker_1500` (several per abstract,
  `<title>` prefix), not the embedder's `abstract_single_chunk`; staleness
  from before 040 is not backfilled (vectors are re-embedded from scratch at
  256 d anyway). 040 applied to `bmlibrarian_dev`; it installs on
  `knowledgebase` at its next non-test connection.

- **Configuration tab Ollama URL, #480** (2026-11-26, branch
  `fix/480-ollama-url-host`). The General settings field reads and writes
  `ollama.host` (it edited `ollama.base_url`, which nothing reads). **Save
  As** writes `BMLibrarianConfig.without_env_overrides(collected values)`,
  so a `BMLIB_OLLAMA_HOST` value is not saved to the file (new public method;
  `_persistable_config()` uses it). **Save** and **Sync to Database** apply
  the tab's values through `_apply_collected_config()`: stripped, then set
  inside `_env_overrides_lifted()`, so after Reset or Load the env value
  still applies in memory (review finding). The Ollama parts of
  `doc/users/configuration_guide.md` now name `ollama.host` and
  `BMLIB_OLLAMA_HOST`; the rest of its schema section is still out of date.
  Verified: suite 5066 passed, 73 skipped; the widget test fails on the old
  code. Not run in the Qt app.

- **Env overrides no longer saved, #477** (2026-11-26, branch
  `fix/477-env-overrides-not-saved`). `BMLibrarianConfig` records each
  applied `BMLIB_*` override with the value underneath it
  (`_env_applied`); `sync_to_database()`, `save_config()` and
  `export_to_json()` save `_persistable_config()` (env values put back, a
  key the override created dropped; a key the user changed since is saved
  as is; told apart by value, so a value set equal to the env value is not
  saved). `_sync_from_database()`, `import_from_json()`,
  `reset_to_defaults()` and the Settings tab's Reset change the config
  inside `_env_overrides_lifted()` (overrides out, then applied again, also
  on failure); that Reset no longer aliases `DEFAULT_CONFIG`. Verified:
  suite 5050 passed, 73 skipped. Not run in the Qt app.

- **Login settings order #438, pdf_matcher #456** (2026-11-25, branch
  `fix/settings-pdfmatcher-438-456`). At login `_sync_from_database` merges
  only the user's own `bmlsettings.user_settings` rows
  (`UserSettingsManager.get_own_settings()`) and then re-applies the
  `BMLIB_*` env overrides; the seeded `default_settings` rows no longer
  override `config.json`/env (owner decision 2026-11-25: order is env > user
  rows > JSON > `DEFAULT_CONFIG`; CLAUDE.md and both settings docs updated).
  Saved rows of a category missing from `DEFAULT_CONFIG` (e.g. `gui`) are
  merged too. The blocking Qt "import your JSON config?" modal (it came back
  on every login, a "No" was never remembered) is now an INFO toast pointing
  at Configuration → Sync to Database; `migrate_config_to_db.py`
  merge/`--export --user` use the user's rows only; the CLI warns when the
  saved settings failed to load. `pdf_matcher`: a PDF at the target while
  the document has no working `pdf_filename` (interrupted import) is linked,
  status `linked` (`would_link` in dry runs; the CLI exits 0, the directory
  summary counts it). `check_document_status`, `quick_database_lookup` and
  `find_alternative_matches` re-raise `psycopg.Error`;
  `match_and_import_pdf` reports any error as `failed` for that file
  instead of falling back to title matching or ending a directory batch.
  Title matches now pick the best score, not the lowest document id; a
  dry-run directory import no longer counts `would_import` as failed. Not
  run against a live login or a real PDF import.

- **Import/embedding fixes #442, #444, #446** (2026-11-25, branch
  `fix/import-embed-442-444-446`). `DocumentEmbedder.embed_documents` pages
  by document ID in `batch_size` pages and no longer selects `full_text`, so
  a full-source run without `--limit` holds one page in memory (#442; the
  tqdm-without-total truthiness crash this exposed is fixed too). The
  Europe PMC importer reads IDs from `front/article-meta` only (no more
  eLife `….sa1` sub-article DOIs) and matches existing records by DOI
  (case-insensitive), then by PMID against the PubMed source, before
  inserting; a guarded UPDATE that changes no row now reports `skipped`
  (#444). Migration 038 adds `idx_document_doi_lower` (`CONCURRENTLY`; 183 s
  on `bmlibrarian_dev`) and 039 runs `ANALYZE document`: without expression
  statistics the planner estimated 206 k matches and walked the primary key
  for `LOWER(doi) = … ORDER BY id LIMIT 1`. Every `LOWER(doi)` lookup
  (pdf_matcher, verification prompt, paper reviewer, benchmark test) now
  uses the index; the DOI part of #333 is done. Both migrations run on the
  next connection to `knowledgebase` too (owner approved, 2026-11-25). The
  medRxiv importer updates a stored preprint when the API offers a newer
  version (title, abstract, authors, `pdf_url`; full text only if the new
  one was fetched, else the old is kept with a warning; the old PDF is
  unlinked so `fetch-pdfs` fetches the new one). Rows without a `pdf_url`
  (MECA) have an unknown version and are never overwritten; a new paper with
  an invalid version is stored as v1. PDFs for v2+ are saved as
  `<doi with / → _>v<n>.pdf`, and `fetch-pdfs` no longer blanks existing full
  text when the PDF was already on disk (#446). Stale abstract chunks:
  fixed since by migration 040 (#475). Verified: suite 5026 passed, 75
  skipped; no new ruff/mypy findings; 038/039 applied on `bmlibrarian_dev`
  (index valid, re-run applies nothing, plans checked). Importers not run
  against medRxiv/Europe PMC.

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

- **Security audit fixes #434, #449, #450 and migration lock #439**
  (2026-11-24/25; details in git history): OpenAthens cookies go to
  `requests` as a domain-scoped `RequestsCookieJar`; `write_private_text`
  creates secret files 0600 (session file, CLI token, wizard `.env`);
  password hashes are `pbkdf2_sha256$<iters>$<salt>$<hash>` (old rows verify
  at 100,000; older checkouts can't read the new format). `MigrationManager`
  runs each migration and its record in one transaction under a session
  advisory lock (`MIGRATION_LOCK_KEY`); `CREATE INDEX CONCURRENTLY` files run
  their other SQL first and are recorded once the indexes are valid
  (`tests/test_migrations_live.py`).

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

- **Mid-November Rust app/library slices** (2026-11-16/17; details in git
  history, `doc/developers/library_pipeline.md`, `bml_app.md`):
  `bml_library::FulltextSource`, topic years from `TOPIC_FIRST_YEAR`/
  `TOPIC_LAST_YEAR`, `library status` counts "none offered" apart (closes
  #460); a window closed mid-setup reopens the wizard until the GGUF is in
  place (#462); bmlib pinned at `6465096` (#790 Europe PMC walk; a 200 HTML
  page is never cached as full text); search model warms in the background,
  ⌘Q waits up to 15 s for the update (PR #461). **Not verified by hand:** ⌘Q
  during an update, the screen-4 return, the Windows build.

- **Mid-November audit fixes** (2026-11-15; details in git history and the
  issues): a failed settings load at login blocks `sync_to_database` until a
  load succeeds (#437); `ChunkEmbedder` keeps old chunks
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

- **2026-11-13 repo audit issues #434–#453** (filed 2026-11-14; all but two
  fixed). Installer: #451 (setup replaces another config folder's login
  entry), #453 (rust.yml permissions, SHA-pinned checkout).

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
  run python -m pytest tests/ -p no:cacheprovider --no-cov -q` on 2026-11-26:
  **5076 passed, 78 skipped** in about 2 min (hermetic since #334;
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
