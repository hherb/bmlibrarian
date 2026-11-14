# HANDOVER

Working notes for picking up in-flight work. Each section is one
self-contained slice: what's known, where to start, and how to verify.
Remove a section once its slice has landed; add a new section when handing
off new work. Longer-term structural items live in
[ROADMAP.md](ROADMAP.md) — pull one in here once you're about to start it.

---

## Recently landed (context)

- **Library pipeline, piece 3 of the installer milestone** (2026-11-14,
  branch `feat/library-pipeline`; plan
  `docs/superpowers/plans/2026-11-14-library-pipeline.md`; owner decisions
  this session: bmlib pinned by **git rev**, without waiting for a release, to
  `f13b607`: bmlib PR #770 (the Rust `pdf` feature did not compile on
  Windows) on top of main with #760 `medrxiv-details` and #763 (**#770 must
  be merged into bmlib main**, or the pin points at an unmerged branch), and
  `<library>/documents` stays a `FullTextCache`). New crate
  `rust/bml-library` (bmlib features `pdf` + `embed`): metadata (bmlib sync
  of `medrxiv-details`, 30-day windows), full text (Tier 0 only through
  `PoliteClient`: 30 s spacing, the first 429 ends the phase uncharged and
  sets `library_state.rate_limited_until`; lasting/passing back-off; a new
  version replaces the old in one transaction, a failed new version keeps
  the old; orphan cache entries removed), index (abstract chunk always plus
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
  a row stop the phase), Linux logs to the file.
  `bml_setup::gguf_path` is public. Docs: `doc/developers/library_pipeline.md`,
  `doc/users/library_updates_guide.md`, `rust_db_schema.md` (migration 2).
  Verified: `cargo test -- --include-ignored` 290 passed with and without
  pg_search; macOS schedule hand-checked with `launchctl print` (interval
  259200 s, removed by `manual`); hand run against the real API and model on
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

- **Paper weight: thousands separators; unmarked placeholders not cached**
  (2026-11-10, closes #358, #357; owner decision: no `VERSION` bump, so no
  full re-run). `extractors.SAMPLE_SIZE_NUMBER` (`(?<!\d)(\d{1,3}(?:,\d{3})+(?!\d)|\d+)`)
  is group 1 of every `SAMPLE_SIZE_PATTERNS`, so `find_sample_size` reads
  "1,234 patients" / "N=1,234" whole; the systematic-review scorer's
  `THOUSANDS_SEPARATOR_PATTERN` workaround is gone (`BARE_COUNT_PATTERN`
  accepts a bare "1,234"). `get_cached_assessment` now calls
  `db.failure_placeholder_reason(details, study_types)` (logged): besides the #351
  markers it refuses a `study_type` outside `DEFAULT_STUDY_TYPE_HIERARCHY`,
  the configured hierarchy (the agent passes `study_type_hierarchy`) and
  `'unknown'`, an assessment with no MQ rows, and an MQ/RoB dimension whose
  non-empty component set differs from `MQ_COMPONENTS`/`ROB_COMPONENTS` (a
  dimension with any row whose reasoning starts "Extracted/Estimated from
  StudyAssessmentAgent" is exempt). Still served: pre-#349 replies missing
  the `study_type`/`sample_size` key or every `score` (look genuine) and
  sample sizes cut at a comma by the keyword path (`find_sample_size` runs
  only with `use_llm_extraction=False`, the default before 2025-11-24). The lab's Recent
  Assessments list still shows placeholder weights: #414. The persistence
  test fixture was itself a malformed shape (`'RCT'`, partial MQ/RoB) and is
  now realistic. Tests: `test_paper_weight_extractors.py::...thousands_separators`,
  `test_paper_weight_persistence.py::TestPlaceholderCacheRows`.

- **Plain `pytest tests/` is hermetic** (2026-11-10, closes #334, #251).
  `tests/conftest.py` skips `requires_database`/`requires_ollama` tests
  unless `--run-live` is passed or `BMLIBRARIAN_TEST_DB_ENV` is set, and
  `_block_live_services` fails any other test that opens a PostgreSQL
  connection (`psycopg.connect`, `Connection.connect`, `psycopg_pool`) or
  connects to the local Ollama port, naming the marker it needs. Shared
  fixture `offline_model_list` stubs `list_ollama_models` for GUI tabs whose
  model pickers ask Ollama when built (research/settings/configuration tab
  tests use it). Found and fixed on the way: tests that passed only because a
  live server was up or for the wrong reason offline
  (`test_verify_document_exists` asserted an always-truthy tuple; paperchecker
  `test_connection_db_failure` and two study-assessment tests returned
  False/None because Ollama was unreachable; the systematic-review workflow
  test searched production); bool-returning "tests" that could not fail now
  assert (`test_human_edit_logging.py`, `test_hyde.py`, `test_editor_agent_fix.py`,
  `test_fallback_formatting.py`, `test_template_system.py`;
  `test_reference_fix.py` → `test_reporting_methodology.py`;
  `test_citation_data_flow.py` is a marked live test); `conftest.py` no longer
  puts `tests/` on `sys.path` (`from tests.llm_test_support import ...`).
  The guard is session-scoped (in place before module/class fixtures) and
  records trips, so one swallowed by a Qt slot, thread or `except
  BaseException` still fails the test; `tests/test_live_service_guard.py`
  checks it. `BMLIBRARIAN_TEST_DB_ENV` also sets `BMLIBRARIAN_ENV_FILE` (if
  unset), so every live test uses that dev database. The benchmark recall
  tests are marked live; `test_papercheck_database.py`'s mocked tests run
  again (only the integration class is marked).
  Docs: `doc/developers/test_database_guard.md` "Live tests are opt-in".
  Not caught: a remote/non-default `OLLAMA_HOST`, other LLM providers,
  psycopg async, child processes.
- **Settings categories: SQL lists guarded against drift** (2026-11-09,
  closes #231). `tests/test_settings_categories_sql_sync.py` reads
  `migrations/*.sql` (no database) and checks that the latest definition of
  each of the four SQL category lists — the `user_settings`/`default_settings`
  CHECK constraints, the `v_user_complete_settings` view and the
  `get_all_user_settings()` function — equals
  `config.VALID_SETTINGS_CATEGORIES` (whitespace/case-insensitive, follows
  DROPs, ignores comments). The view and the function still listed only the
  original 10 categories. The function is what `UserSettingsManager.get_all()`
  calls on login, so per-user `document_qa`/`discovery`/`embeddings` settings
  were saved but never loaded back. **Migrations 036** (view) **and 037**
  (function) recreate them with all 13. Both are applied on `bmlibrarian_dev`,
  and 037 was verified there in a rolled-back transaction. `knowledgebase`
  gets them on its next non-test connection; both are `CREATE OR REPLACE`
  only. Checklist for a new category: `db_settings_architecture.md`
  "Database Schema".
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

- **Research tab: toasts instead of modals; dead executor path removed**
  (2026-11-06, closes #332). New shared `gui/qt/widgets/toast.py`:
  `show_toast(widget, message, ToastLevel.INFO|SUCCESS|WARNING|ERROR)`
  overlays a plain-text, dismissable toast at the bottom right of the
  widget's window (stacked, follows resizes; errors stay until dismissed,
  others time out per `TOAST_TIMEOUT_MS`); styled by
  `StylesheetGenerator.toast_stylesheet`. The research tab's start
  validation, agent-rebuild failure, workflow error and export
  success/failure messages use it (`research_tab.py`,
  `workflow_handlers.py`, `export_utils.py`); only the "Start New
  Research" Yes/No stays modal. Removed (no callers): the executor's
  `start_workflow`/`execute_workflow`/`_test_agent_connection`/
  `score_documents`/`extract_citations`/`check_agents_ready`, all its
  signals and `WorkflowSignals`; the tab's `_on_workflow_started/
  _completed/_error` and the "Phase 2"/"Milestone 3"
  `_show_completion_message`; `tab_updaters.update_literature_tab`/
  `update_citations_tab`. Bug fixed on the way: the thread now copies the
  scored documents and threshold onto the executor, so the preliminary
  report's methodology section no longer shows an empty score
  distribution and 0 documents processed for citations. PR #389 review
  fixes: toasts are never taller than the window (messages over
  `TOAST_MAX_MESSAGE_CHARS` are cut off on screen, full text in the
  tooltip and log; older toasts that don't fit are dropped), messages use
  `error_text(e)` (`"TypeName: message"`); `WorkflowThread.workflow_warning`
  → WARNING toast for a failed counterfactual analysis or final report
  (the preliminary report is then emitted as final, so export never sees a
  stale report; the tab also clears `final_report_markdown` at start and
  on New); missing scoring/citation agents fail the run instead of looking
  like "no citations"; early-ending runs (`no_documents`/`no_scores`/
  `no_citations`) explain why; `QueryAgent.find_abstracts(ts_query=)` lets
  the executor search the query it showed instead of converting the
  question again. The other ~39
  modules with non-decision modals: ROADMAP §5. Docs:
  `gui_architecture.md` "User Notifications", `PLUGIN_DEVELOPER_MANUAL.md`
  error handling, `qt_gui_user_guide.md` "Notifications". Tests:
  `tests/test_toast.py`, `test_qt_workflow_thread.py::...methodology`,
  `test_qt_workflow_executor.py`, `test_qt_research_tab.py`,
  `test_qt_integration.py`, `test_research_export_utils.py`.
- **Queue follow-ups: Ctrl-C, task ownership, recovery reporting**
  (2026-11-05, closes #384, #385, #386). QueueManager installs a SIGTERM
  handler only; SIGINT is left alone, so Ctrl-C stays `KeyboardInterrupt`
  (CLI `except KeyboardInterrupt` / session-end logging work again) and an
  uncaught one fails in-flight tasks through the `atexit` hook.
  `complete_task(…, worker_id=)` / `fail_task(…, worker_id=)` write only
  while that worker still holds the task (PROCESSING, same `worker_id`); the
  orchestrator passes `task.worker_id`, and a late result/failure is
  discarded with a warning naming the task's current status/worker and a
  `task_discarded` event (`complete_task` → bool, `fail_task` →
  `TaskStatus.PENDING`/`FAILED`/None; a missing row is logged). Without
  `worker_id` a finished (completed/failed/cancelled) task is never touched.
  `recover_stuck_tasks(force=False)` skips tasks whose process is alive (also
  with `mark_as_failed`) and returns `RecoveryCounts(reset, failed,
  skipped_running)`; its UPDATEs re-check status/`worker_id`/`started_at`, so
  a task finished by another process mid-recovery is not overwritten.
  `queue_cli recover` prints each count and has `--force`; its hints print
  runnable `python -m bmlibrarian.queue_cli …` commands. `_process_alive` is
  `psutil.pid_exists` (Windows-safe; EPERM = alive) and is used by recover,
  `cleanup_dead_process_tasks` and `get_queue_health`; it also compares the
  process start time with `started_at` (#388, PR #407). `task_failed` carries `will_retry`. Docs: `queue_recovery.md`,
  `queue_system_architecture.md`, `queue_management_guide.md`,
  `queue_system_guide.md`. Tests: `tests/test_queue_ownership.py`.
- **Queue worker robustness** (2026-11-05, #294): per-task agent lookup,
  retries vs. `ResultNotSerializableError`, `_abandon_task`, one
  atexit/signal hook per process. Docs `queue_recovery.md`; tests
  `tests/test_queue_worker_robustness.py`.
- **Failed migrations are fatal, at startup and later** (2026-11-04/05,
  #342, #378, #379, #381): `MigrationError`, `set_migration_failure_handler()`,
  Qt `check_schema_current()`; no direct `DatabaseManager()` callers left.
  Tests `tests/test_auto_migration_failure.py`.
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

- **Rust installer (current focus)**, design
  `docs/superpowers/specs/2026-11-11-installer-walking-skeleton-design.md`:
  pieces 1 (pgdist), 2 (`bml-db`) and 3 (library pipeline) are done.
  1. Merge bmlib PR #770 (Windows `pdf` build fix) before merging #429; the
     pin `f13b607` is that PR's commit. On #429 the `rust` CI built MuPDF and
     llama.cpp on all five runners; only Windows failed, on that bmlib bug.
  2. Measure how many medRxiv JATS files carry the article body (the hand
     run's two had only supplementary material), since that decides how
     often the Cloudflare-blocked PDF is needed. Rates between 1.5 s and 30 s
     are still unmeasured too.
  3. Next piece: **3c, MECA bulk** (bmlib, Python + Rust: MECA reader and
     requester-pays S3), the main full-text route for the backlog (owner
     2026-11-14); then the bulk route in `bml-library`. Then 3b (medRxiv HTML
     page, bmlib), piece 4 (hybrid search, `bml search`), 5 (Tauri wizard),
     6 (signed Mac `.dmg`).
  4. bmlib is pinned by git rev; move to a tagged release (or crates.io,
     #401) once one contains #760.
  `bml-pgserver` leftovers: #397 (needs Windows), #399 (owner decision on a
  port taken after init); bml-db review follow-ups: #424;
  bml-library review minors: #428.

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
  run python -m pytest tests/ -p no:cacheprovider --no-cov -q` on 2026-11-13
  (bml-db branch): **4843 passed, 71 skipped** in about 2 min (hermetic since #334;
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
  `reference-local-pg18-bindir`): 290 passed on 2026-11-14 (with and
  without pg_search). The first build compiles llama.cpp and MuPDF
  (about 1.5 min on the owner's Mac).
- `uv run python bmlibrarian_cli.py --quick` still runs end-to-end for a
  manual smoke check when touching the core agent workflow.
- Never run destructive tests against the production `knowledgebase`
  database — use `bmlibrarian_dev` (see CLAUDE.md
  "Database Safety"). Opt-in DB tests: `BMLIBRARIAN_ENV_FILE=~/.bmlibrarian/.env_pg18_dev
  BMLIBRARIAN_TEST_DB_ENV=~/.bmlibrarian/.env_pg18_dev uv run python -m pytest …`.
