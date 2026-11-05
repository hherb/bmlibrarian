# HANDOVER

Working notes for picking up in-flight work. Each section is one
self-contained slice: what's known, where to start, and how to verify.
Remove a section once its slice has landed; add a new section when handing
off new work. Longer-term structural items live in
[ROADMAP.md](ROADMAP.md) — pull one in here once you're about to start it.

---

## Recently landed (context)

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
  `cleanup_dead_process_tasks` and `get_queue_health`. A reused PID still
  reads as alive: #388. `task_failed` carries `will_retry`. Docs: `queue_recovery.md`,
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

- **A failed migration is remembered; standalone windows check the schema
  too** (2026-11-04, closes #379, #378). `get_db_manager()` stores the
  `MigrationError` (`database._db_manager_error`) and re-raises it on every
  later call without re-running the migration; `close_database()` clears
  it. Other construction errors are not remembered. The Qt startup check is
  now `gui/qt/core/schema_check.check_schema_current()` (the main app's
  `_check_schema_current` delegates), called by `run_plugin_standalone`,
  `run_widget_standalone` (new `check_schema=`; `fact_checker_review_gui.py`
  passes False with `--db-file`), `systematic_review_gui.py`,
  `audit_validation_gui.py`, `scripts/pdf_verification_gui.py`,
  `scripts/pdflab.py` and the Paper Weight / Paper Checker / Paper
  Reviewer / Transparency / PubMed Search lab entry points. Creating the
  manager is serialised by a lock (one migration run per process). Docs: `architecture.md` "Failed
  auto-migration is fatal". Tests: `tests/test_auto_migration_failure.py`
  (`TestGetDbManagerRemembersFailure`, `TestStandaloneWindowsCheckSchema`).

- **A failed auto-migration stops startup** (2026-11-04, closes #342; owner
  decision: fatal). A pending migration that fails while being applied
  raises `bmlibrarian.migrations.MigrationError` (a `RuntimeError`, so
  existing `except RuntimeError` callers still work); `DatabaseManager`
  closes its pool and re-raises (it used to log "Auto-migration check
  failed" and run on the outdated schema). An unreadable pending file is a
  `MigrationError` too. Failing to *check* (no migrations dir, no
  `MigrationManager`, tracking table neither creatable nor readable) is not
  fatal; if only `CREATE TABLE IF NOT EXISTS bmlibrarian_migrations` fails
  (no CREATE on the schema) but the table reads, pending files still run.
  The Qt app creates the manager right after login
  (`BMLibrarianApplication._check_schema_current`): on `MigrationError` it
  shows a critical dialog (no window exists yet for a toast) and exits 1;
  other manager errors are left to the tabs, as before.
  `bmlibrarian_cli.py` no longer runs its own swallowing migration pass and
  stops in agent setup; other CLIs fail at their first DB use (not checked
  per CLI). The SETUP_GUIDE manual-recovery recipe uses
  `psql -v ON_ERROR_STOP=1 -U <owner>` so a failed statement is never
  marked applied. Docs:
  `doc/developers/architecture.md` "Failed auto-migration is fatal",
  `SETUP_GUIDE.md` + `doc/users/troubleshooting.md` "Database Migration
  Failed". Tests: `tests/test_auto_migration_failure.py`.
- **A fact-check verdict is stored with its evidence or not at all; a
  failed audit write no longer poisons the shared audit connection**
  (2026-11-04, closes #340, #341). `FactCheckerDB.store_verdict(statement,
  evaluation, evidence)` runs all inserts on one pooled connection in one
  transaction (the three `insert_*` take an optional `conn`); used by
  `FactCheckerAgent._store_result_in_database` and `import_json_results`
  (same bug). When an imported verdict fails, `import_json_results` stores
  the statement alone (`errors`) so `--incremental` still re-checks it;
  evidence without a usable `document_id` is logged and counted
  (`dropped_evidence`); both reach the import progress message
  (`import_problems_suffix`). Every query on an audit connection — the
  trackers and `AuditValidationDataManager` — runs in
  `audit/connection.audit_cursor(conn)`, which rolls back on any
  exception (including Ctrl-C) and re-raises; `tests/test_audit_cursor.py`
  fails on any bare `conn.cursor(` there. Not done:
  `extract_citations_with_audit` still drops a citation whose audit write
  failed (no production callers); the SQLite→PostgreSQL migration script
  is still not atomic (#376). Tests: `tests/test_audit_cursor.py`,
  `tests/test_fact_checker_failure_handling.py`, opt-in real SQL
  `tests/test_factcheck_audit_transactions_db.py` (passes on
  `bmlibrarian_dev`). Docs: `fact_checker_system.md` "Failure handling",
  `AUDIT_SYSTEM_DESIGN.md` "Connection handling".
- **PRISMA chunk consolidation works; the LLM boundary guard sees raw
  Ollama HTTP** (2026-11-04, closes #252, #250). `SemanticChunkProcessor`
  called its client with ollama's API (`options=`, `response["message"]`),
  so whenever a low-scoring PRISMA item's semantic chunks exceeded
  `SEMANTIC_CONTEXT_MAX_CHARS`, every batch raised and
  `PRISMA2020Agent._process_semantic_chunks_for_context` fell back to the
  single best-scoring chunk (#252 called it unreachable; it is not). It now
  calls `LLMClient.chat(messages=[LLMMessage], temperature=, max_tokens=)`;
  the PRISMA factory escapes braces in title/description/explanation (a `{`
  in a title broke `.format()`; a NULL title is treated as empty). Review
  follow-ups: an empty model reply fails the batch (shared
  `bmlibrarian.llm.checked_content`, which `BaseAgent._checked_content` now
  delegates to; a truncated reply is kept with a warning), and a failed
  consolidation no longer re-scores on a fallback chunk — the item keeps its
  first-pass score and a `prisma_second_pass_error` callback reports it
  (`_fallback_first_chunk` removed). The PICO lab model picker uses
  `list_ollama_models(host)` (was `requests.get(/api/tags)`; the other two
  #250 sites went with Flet) and reports failures in its status line, not a
  modal (the refresh runs during tab construction).
  `tests/test_llm_layer_boundary.py` also flags non-docstring string
  literals naming Ollama REST endpoints; allowlist
  `KNOWN_RAW_OLLAMA_HTTP_MODULES` = `embeddings/embedding_server.py` (batch
  `/api/embed`; its `/api/tags` check is remaining debt). Tests:
  `tests/test_semantic_chunk_processor.py` (now a real `LLMClient` patched
  at the provider boundary; 11 of them fail on the old code),
  `tests/test_prisma_semantic_context.py` (agent -> processor -> LLMClient),
  `tests/test_pico_lab_model_refresh.py`.
- **Settings saved in other tabs reach the research tab; Chrome fallback
  takes PDFs by content; medRxiv test stays out of `~`** (2026-11-04,
  closes #372, #329, #335). The main Settings tab (Apply, Save, Save As,
  Load, Reset: each changes the live config) and the Configuration tab's
  save publish `AGENTS_NEED_REINIT_EVENT` on the `EventBus`
  (`core/event_bus.py`); `ResearchTabWidget` listens and marks its agents
  stale, so the next Start rebuilds them (disconnected in `cleanup()`). The
  Configuration tab's "Save As" announces too (harmless rebuild, same
  config). `promote_downloaded_pdf` considers every finished file
  (`finished_downloads()`: not `*.crdownload`, not hidden, e.g. macOS
  `.com.google.Chrome.*` temporaries) and relies on `is_pdf_file`,
  so a PDF saved as `fulltext`/`article.PDF` is promoted; the "not a valid
  PDF" error uses the same list. `test_initialization_with_env_var` points
  `HOME` at `tmp_path` (an empty `~/test_pdfs` from March was removed).
  Tests: `tests/test_qt_research_tab.py`,
  `tests/test_undetected_chrome_download_dir.py`.
- **October 2026 slices** (details in git history and the linked docs):
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

- #332 — research tab still uses modal `QMessageBox`es and "Phase 2" /
  "Milestone 3" wording; switch to toasts, drop dead `QtWorkflowExecutor`
  / `tab_updaters` code (no owner decision needed).
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

- [#230](https://github.com/hherb/bmlibrarian/issues/230) — Fact-checker
  `insert_ai_evaluation` MAX(version)+1 race under concurrent writers.
- [#231](https://github.com/hherb/bmlibrarian/issues/231) — Settings
  categories: Python whitelist and SQL CHECK constraints can drift, no
  hermetic guard.
- #376 — `migrate_factchecker_sqlite_to_postgres.py` migrates table by
  table, so a verdict can still be committed without its evidence; migrate
  per evaluation with `FactCheckerDB.store_verdict` (one-off script).

### Verify

- **The full suite is green** since PR #336: `QT_QPA_PLATFORM=offscreen uv
  run python -m pytest tests/ -p no:cacheprovider --no-cov -q` on 2026-11-05
  (#384–#386 branch): **4729 passed, 53 skipped** in 7–17 min. Without
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
