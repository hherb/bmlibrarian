# HANDOVER

Working notes for picking up in-flight work. Each section is one
self-contained slice: what's known, where to start, and how to verify.
Remove a section once its slice has landed; add a new section when handing
off new work. Longer-term structural items live in
[ROADMAP.md](ROADMAP.md) — pull one in here once you're about to start it.

---

## Recently landed (context)

- **Migration row errors; queue reused-PID check** (2026-11-08, closes
  #395, #388). `scripts/migrate_factchecker_sqlite_to_postgres.py` catches
  only `ROW_ERRORS` (`IntegrityError`/`DataError`/`ValueError`) per row in
  every step (statements, annotators, human annotations, processing
  metadata, export history), so a lost connection stops the run as
  `MIGRATION_GUIDE.md` says; `FactCheckerDB.update_statement_review_status`
  raises `ValueError` when no row matched. Queue: `_process_alive(pid,
  process_started)` also compares the process's start marker with the one
  the claiming worker stored in the new `queue_tasks.process_started` column
  (`_process_start_marker`: ticks since boot on Linux, so clock steps do not
  make a live worker read as dead; added to old queue files on open), so a PID reused after a crash
  or reboot no longer blocks `recover`/`cleanup-dead`; access denied or a
  NULL `process_started` (claimed before the column) fall back to the PID check. `cleanup_dead_process_tasks`
  and the `orphaned_tasks` count check per task (cleanup re-checks the claim
  in its UPDATE). Tests:
  `test_queue_ownership.py::TestReusedPid`, `test_migrate_factchecker_sqlite.py`
  (`*another_step*`), opt-in `test_factcheck_audit_transactions_db.py`.
- **Rust one-click installer, part 1: `bml-pgserver`** (2026-11-07,
  PR #396). First Rust code: `rust/` Cargo workspace + CI
  (`.github/workflows/rust.yml`), `bml-pgserver` library (private per-user
  PG18 on 127.0.0.1, default port 5418, scram, resumable `init`, owner-only
  `bml.env`/`bml-admin.env`/`bml-pgserver.json`, autostart at login) and
  `bml server init|start|stop|restart|status|autostart` CLI. Design:
  `docs/superpowers/specs/2026-11-07-one-click-installer-design.md`
  ("Pieces of work, in order": 1–2 done). Docs:
  `doc/users/private_postgres_server.md`, `doc/developers/rust_pgserver.md`.
  Portable PG18/pgvector/pg_search binaries are not yet sourced (`--bindir`
  points at an existing install).
- **Rust one-click installer, part 3: `bml-setup` + `bml setup`**
  (2026-11-07, PR #402). New `rust/bml-setup` crate (hardware
  check, database, autostart, Ollama, models, embedding GGUF; resumable,
  failures don't stop independent steps) and `bml setup` front end; plan
  `docs/superpowers/plans/2026-11-07-bml-setup.md`, docs
  `doc/users/bml_setup_guide.md`, `doc/developers/rust_setup.md`. Owner
  decisions: Ollama pinned to v0.40.10 with checksum-verified installers
  (Linux `install.sh` pulls its tarball unchecked, documented);
  `medgemma4B_it_q8:latest` is not in Ollama's registry, so setup pulls
  `medgemma1.5:4b-it-q8_0` and `/api/copy`s it; `bml-pgserver` can adopt an
  existing loopback PG18 (`--existing-server`, password via
  `BML_PG_SUPERUSER_PASSWORD`/`--password-stdin`, only role `bml_app` + db
  `bmlibrarian`); the GGUF download uses bmlib's llama-free `model-download`
  feature, a git dependency pinned at rev 9670f4e (bmlib PR hherb/bmlib#703;
  switch to crates.io 0.3.1 once published). Verified by hand on macOS
  only (private server + Ollama present + GGUF twice); the Windows/Linux
  Ollama installs and Windows Inno flags are unverified (#397). The Phase B
  import profile and any server restart must refuse when `bml-external.json`
  exists (an existing server is never restarted by bml). Portable
  PG18 binaries remain a separate future plan (`--pg-bindir` meanwhile).
- **`bml setup` review follow-ups** (2026-11-08, PR #404, closes #403,
  most of #401). Library API changes ahead of piece 4:
  `bml_pgserver::external::check_request` (loopback host, storable
  password/superuser; the CLI calls it before any step, so a remote
  `--existing-server` or empty `--password-stdin` line exits 1 at once);
  `adopt` drops `[::1]` brackets itself; new errors `ExistingServerMismatch`
  and `AutostartLeftover` (a login entry that could not be removed or put
  back after a failed enable is reported, not left silently); new
  `StepOutcome::Warnings(Vec<String>)` (Hardware, Database, Ollama via
  `report_warnings`; the CLI summary repeats them). The Models step tries both models and joins their
  errors. Hardware: "unknown free space" warning for a disk not in the mount
  list, no Ollama-disk check for a remote `OLLAMA_HOST`, Linux checks
  `/usr/share/ollama/.ollama/models`. Ollama detection: `app_candidates`
  (macOS user/system `Applications`; Windows `%LOCALAPPDATA%` then
  `%ProgramFiles%`, unverified, #397) then `ollama` on `PATH` (Homebrew); a
  found command is not started, setup says how. macOS unpacks into
  `~/Applications/.bml-ollama-extract` and renames, so no partial app.
  Downloads run under an OS file lock (`.bml-setup-download.lock`,
  `File::try_lock`; workspace MSRV now 1.89); after taking it the Ollama and
  Embedding steps re-check, so a second setup never downloads twice. macOS
  deletes the installer only after the app is moved into place. `parse_ollama_host` refuses
  userinfo, port 0, text after `]`, `?`/`#`. CLI failures and warnings go to
  stderr; a remote `--existing-server` is refused before the password is read. Still open on #401: bmlib-side items (README count, tests, CI
  guard, crates.io 0.3.1 — only 0.3.0 is published), an existing-server
  `bml server status` exit-0 test and `pg_search` adopt in CI (#399),
  Windows drive-letter case (#397), installed-Ollama version never checked.
- **macOS autostart re-enable keeps the old login entry** (2026-11-08,
  closes #405). `autostart::enable` reads the old plist before `bootout`;
  a failed write or `bootstrap` writes it back and `bootstrap`s it again
  (`restore_launch_agent`, unit-tested with a fake reload), or removes the
  new plist when there was none; a failed reload is `AutostartNotReloaded`
  (entry intact, loads at next login), a failed restore `AutostartLeftover`.
  Not exercised against a real failing `launchctl`.
- **`bml-pgserver` follow-ups** (2026-11-07, closes #398): app-role login
  check and password reset on `28P01`, richer connect/DB errors, `bml server
  status` exits 3 when stopped, stricter launchctl error handling, fake-bin
  tests, CI `integration-macos`. Open: #397 (Windows), #399 (port-moved
  decision, Linux disable test, `pg_search` in CI).

- **SQLite → PostgreSQL migration keeps statements' `review_status`**
  (2026-11-06, closes #392). `insert_statement` never writes the status,
  so every migrated statement used to become `pending`.
  `migrate_statements` now calls `restore_review_status`: a legacy
  `in_review`/`completed`/`flagged` (normalised) is set with
  `update_statement_review_status` only while the PostgreSQL row is still
  `pending` (`pending` counts as unset); any other value is a statement
  error (exit 1) unless PostgreSQL already holds a reviewed status; the
  statement still counts as migrated and its verdicts migrate;
  `--dry-run` reports it too. Broad per-row `except` in the migration
  (lost connection doesn't stop it): #395. Docs:
  `scripts/MIGRATION_GUIDE.md`, `fact_checker_system.md`. Tests:
  `tests/test_migrate_factchecker_sqlite.py` (`test_*status*`).

- **SQLite → PostgreSQL fact-checker migration stores verdicts with their
  evidence** (2026-11-06, closes #376).
  `scripts/migrate_factchecker_sqlite_to_postgres.py` no longer migrates
  `ai_evaluations` and `evidence` as separate passes: `migrate_verdicts()`
  stores all evaluations of a statement with their evidence through the new
  `FactCheckerDB.store_verdicts` (one transaction per statement;
  `store_verdict` now wraps it). If any insert fails (e.g. a `document_id`
  not in `public.document`), none of the statement's evaluations is stored,
  so an older version is never left as the latest; they count as errors,
  the summary lists the statement, and a statement not evaluated before
  stays unevaluated, so `--incremental` re-checks it. Only
  `IntegrityError`/`DataError`/`ValueError` count per statement; anything
  else aborts the run. The script now exits 1 when any record failed.
  Evidence without a usable `document_id` is dropped (own "Dropped"
  count, as in `import_json_results`); `error` evaluations are skipped;
  verdicts are normalised (`'Yes '` → `yes`). `--skip-existing` used to do
  nothing (a re-run stored every verdict again as a new version); it now
  skips statements that already had a verdict in PostgreSQL before the run.
  The script imports `bmlibrarian.…` instead of `src.bmlibrarian.…`. Docs:
  `scripts/MIGRATION_GUIDE.md`, `fact_checker_system.md`. Tests:
  `tests/test_migrate_factchecker_sqlite.py` (fake `FactCheckerDB`),
  `test_factcheck_audit_transactions_db.py` (real SQL, opt-in).

- **Concurrent fact-check evaluations no longer collide** (2026-11-06,
  closes #230). `FactCheckerDB.insert_ai_evaluation` locks the statement
  row (`SELECT … FOR NO KEY UPDATE`) in its transaction before assigning
  `MAX(version) + 1`, so a second writer for the same statement waits and
  gets the next version instead of a `UniqueViolation` (the lock does not
  block FK inserts referencing the statement). Test (opt-in dev DB):
  `tests/test_factcheck_audit_transactions_db.py::test_concurrent_evaluations_get_consecutive_versions`
  (fails on the old code). Also: `tests/test_toast.py` polls for the toast
  timer instead of a fixed 200 ms wait, which flaked in the full suite.
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
- **Queue worker robustness** (2026-11-05, closes #294). The orchestrator
  worker (`_process_agent_tasks(agent_type)` → `_run_task`) looks the agent
  up per task, so re-registering a type takes effect on its next task. An
  exception from the agent method is retried (`Task execution failed:
  <Type>: <msg>`, traceback logged), and so is an `sqlite3.Error` while
  storing the result; a result json cannot serialise
  (`ResultNotSerializableError` from `complete_task`, raised before any
  write) fails the task without retry, so side effects are not repeated.
  Any other error after a claim goes to `_abandon_task` (FAILED, `Worker
  error: ...`; if that write fails too, a `task_stuck` event), so a claimed
  task never stays PROCESSING silently. A worker whose queue file is deleted
  stops (`worker_stopped`). `QueueManager` installs one `atexit` hook and one
  SIGINT/SIGTERM handler per process (weak registry of live managers;
  signals only from the main thread); a signal exits `128 + signum`, waits
  at most 1 s for the SQLite lock (atexit retries), cleanup errors go to
  stderr, a deleted queue file is skipped; `db_path` is stored absolute.
  `recover_stuck_tasks(mark_as_failed=False)` counts the reset as a retry and
  fails a task out of retries (dead-process tasks are failed in either
  mode). Docs: `queue_recovery.md`, `queue_system_architecture.md`,
  `doc/users/queue_management_guide.md`, `queue_system_guide.md`. Tests:
  `tests/test_queue_worker_robustness.py`. Follow-ups #384–#386: done
  (entry above).
- **A migration that fails after startup is fatal too; no direct
  `DatabaseManager()` callers left** (2026-11-05, closes #381; owner
  decision: central fatal handler). `database.set_migration_failure_handler()`
  registers a function that `get_db_manager()` calls (outside its lock,
  handler errors logged) the first time it remembers a `MigrationError`.
  `check_schema_current()` installs a Qt handler whenever it lets the window
  start: a `QObject` notifier created in the GUI thread queues the same
  "Database Migration Failed" dialog onto it, calls
  `QApplication.closeAllWindows()` (the main window stops plugin workers in
  `closeEvent`) and `QApplication.exit(MIGRATION_FAILED_EXIT_CODE)` (1), and
  re-posts the exit with `QTimer.singleShot(0, …)` (an `exit()` from a
  modal's loop before `app.exec()` is otherwise lost). `run_pubmed_search_lab()`
  now returns `app.exec()` (it dropped the exit code). `audit_validation_gui.py`
  no longer calls the nonexistent `plugin.initialize()` (it crashed every
  start). `audit_validation_gui.py`
  (reviewer lookup), the audit validation plugin (its `cleanup()` no longer
  closes the shared pool), `scripts/pdflab.py` and `thesaurus_import_cli.py`
  use `get_db_manager()`; the GUIs skip their own error message on
  `MigrationError`. `tests/conftest.py::isolate_tests` resets the handler.
  Tests: `tests/test_auto_migration_failure.py`
  (`TestLateMigrationFailureIsFatal`, `TestDirectCallersUseSharedManager`).
- **Failed auto-migration is fatal** (2026-11-04, closes #342, #378,
  #379): a pending migration that fails raises `MigrationError`
  (a `RuntimeError`), `get_db_manager()` remembers and re-raises it, and
  Qt entry points run `gui/qt/core/schema_check.check_schema_current()`
  (critical dialog, exit 1; skipped by `fact_checker_review_gui.py
  --db-file`). Other manager construction errors are not remembered, and
  failing to *check* for migrations is not fatal. Docs: `architecture.md` "Failed
  auto-migration is fatal", `SETUP_GUIDE.md`, `troubleshooting.md`. Tests:
  `tests/test_auto_migration_failure.py`.
- **Early November / October 2026 slices** (details in git history and the
  linked docs): fact-check verdicts stored with their evidence in one
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

- Rust installer: a plan for obtaining portable PG18 + pgvector + pg_search
  binaries (ROADMAP); then piece 4, the Tauri first-run screen driving
  `bml-setup` (the "before piece 4" API items of #401 are done; call
  `check_request` before `run_setup`). `bml-pgserver` leftovers: #397 (needs Windows), #399 (owner
  decision on a port taken after init).

- Remaining citation rejections: 10 of the 106 #303 pairs are below the
  similarity threshold (long multi-sentence quotes that drift). Known sentence-bounds misses: lost text with a single
  space (`8.8%) MAE rates`), multi-word fused labels.
- Widening decisions from the PR #306 review: #308 (widen one-word quotes,
  or require a minimum fragment size?), #309 (fragments still lost at text
  end without a full stop, inside broken-off sentences, past 400 chars).
- #320 — after rejecting every discovered source, the doi.org fallback may
  fetch the same PDF again (owner decision needed: skip fallback, compare
  redirect target, or document).
- #357 (unmarked pre-#349 paper-weight placeholders still served from the
  cache) and #358 (`find_sample_size` misreads "1,234"); both hinge on
  whether to bump `PaperWeightAssessmentAgent.VERSION` (full re-run).
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

## Also tracked on GitHub (not yet started)

- [#231](https://github.com/hherb/bmlibrarian/issues/231) — Settings
  categories: Python whitelist and SQL CHECK constraints can drift, no
  hermetic guard.

### Verify

- **The full suite is green** since PR #336: `QT_QPA_PLATFORM=offscreen uv
  run python -m pytest tests/ -p no:cacheprovider --no-cov -q` on 2026-11-08
  (#395/#388 branch, PR #407): **4809 passed, 57 skipped** in 7–17 min. Without
  `offscreen`, `test_annotation_widget.py::...::test_explanation_field_typing`
  can fail when another app holds OS focus (`qWaitForWindowActive`). No `--continue-on-collection-errors` or marker deselection needed;
  any other failure is a regression. Save the
  output to a file in the scratchpad (don't just tail it), and don't edit or
  `git stash` the tree while it runs.
- `ruff check .` / `mypy src/` carry pre-existing debt (~1,745 ruff findings);
  the gate is **no new errors**, not a clean baseline. Quick regression check:
  `git stash`, run `ruff check --select F401,F811,F821,F841 <touched files>`,
  compare to your tree (normalize away line numbers).
- `uv run python bmlibrarian_cli.py --quick` still runs end-to-end for a
  manual smoke check when touching the core agent workflow.
- Never run destructive tests against the production `knowledgebase`
  database — use `bmlibrarian_dev` (see CLAUDE.md
  "Database Safety"). Opt-in DB tests: `BMLIBRARIAN_ENV_FILE=~/.bmlibrarian/.env_pg18_dev
  BMLIBRARIAN_TEST_DB_ENV=~/.bmlibrarian/.env_pg18_dev uv run python -m pytest …`.
