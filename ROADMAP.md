# ROADMAP

Longer-term structural direction. This is not a task list for the next
session — see [HANDOVER.md](HANDOVER.md) for that. Items here are pulled
from [doc/TODO_code_review_2026-07.md](doc/TODO_code_review_2026-07.md)
(whole-project review, 2026-07-19) and reorganized by theme; re-read that
document for exact file/line references before starting one, since line
numbers drift.

Move an item to HANDOVER.md's "Next up" when you're about to start it: this
file tracks *what* and *why*, HANDOVER tracks *in-flight, right now*.

---

## 1. Close the remaining Qt gaps left by the Flet retirement

The Flet GUI was deleted on 2026-10-16 (flet 1.0's event-model change would
have meant a behavioural rewrite; see HANDOVER). Relocation, launcher
repointing, SQLite review packages, `--user`/`--blind`/`--incremental` in the
Qt review tab are done. Features that existed only in Flet and are now gone:

1. **Qt fact-checker review tab**: no confidence dropdown, no
   agreement-statistics dialog (AI/original/human agreement %; the Qt
   Statistics box only shows annotated/remaining counts), no `session_id`
   stamping on annotations (the Flet review app stamped
   `gui_session_YYYYMMDD`; the Qt tab does not). (The "unclear" option was
   added in PR #277.)
2. **Citation lab** (`lab/citation_lab.py`, deleted) had no Qt port —
   port it as a `gui/qt/plugins/` tab if still wanted (git history has the
   Flet version).
3. **Research GUI automation flags** (`--auto "question"`, `--quick`,
   `--max-results`, `--score-threshold`) and browser mode (`--web/--port`)
   of `bmlibrarian_research_gui.py` have no Qt equivalent; `bmlibrarian_cli.py`
   covers headless runs.
4. **Multi-model query generation is unwired.** `QueryAgent.find_abstracts_multi_query`
   (config `query_generation.multi_model_enabled`, plus query performance
   tracking) was only called by the Flet research workflow; the Qt research
   tab (`WorkflowThread` → `executor.generate_query`) uses single-model
   `convert_question`. Wire it into the Qt executor (and the CLI) or drop it.
5. **Citation accept/refuse review and approve/override controls** existed
   only in the Flet research GUI (backend `human_edit_logger.py` remains).

## 2. Make the test suite protect you

- **Route the remaining direct `psycopg.connect()` callers through
  `DatabaseManager`** so the pytest production guard (`db_test_guard.py`,
  PR #270) covers them: `db_import_profile.py` (ALTER SYSTEM / restart),
  `app.py`, `fulltext_discovery_cli.py`, `paperchecker/database.py`, the Qt
  login in `gui/qt/core/application.py`, and ~10 more. Today the guard only
  makes `DatabaseManager` / `MigrationManager` connections read-only; these
  paths could still write to production under pytest. Also golden rule 5.
- Fix 5 files with unconditional pytest collection errors (manual scripts
  masquerading as `test_*` functions with required args).
- Adopt `requires_database`/`requires_ollama` markers project-wide (only
  5/145 files use them today) so `pytest -m "not requires_database"` is a
  hermetic default.
- Add real asserts to assert-free tests.
- Add per-importer write-path smoke tests against a throwaway schema.
- Reconcile the ">95% coverage" claim in CLAUDE.md with the actual
  `--cov-fail-under=80` baseline.
- **Gate on `ruff check --select F821` (undefined names).** The LLM
  migration (PR #249) shipped two `NameError` crashes on untested paths —
  one of which killed the whole semantic chunking pipeline. `ruff` had
  flagged both as `F821`, but they were invisible among ~1,745
  pre-existing lint errors. A narrow gate on the always-a-bug rules
  (F821, F811, E999) pays for itself immediately without waiting for the
  wider backlog to be cleared.

## 3. Consolidate the 29 top-level entry scripts

- Convert to `[project.scripts]` backed by a shared `cli_common` helper
  (env/config loading, logging, DB access via `DatabaseManager`) to kill
  duplicated `sys.path.insert` boilerplate.
- Eliminate the `src.bmlibrarian.*` import style (loads a second copy of
  the package with its own config/DB-pool singletons — breaks test
  monkeypatching).
- Fix `cli/config.py` defaults-loading dead code and the `--quick`
  vs. explicit-flag override bug.

## 4. Extract shared helpers (each is a live drift source)

- One LLM call-with-retry + JSON-repair helper (4 near-identical
  implementations in `paperchecker/components/`) — move into
  `BaseAgent`/`llm/`.
- One DOI-normalization function (copy-pasted 4×).
- One DOI→filename sanitizer (reuse `utils/validation.py`
  `sanitize_filename()`).
- One Cloudflare detector (3 divergent indicator lists in
  `utils/browser_downloader.py`).
- One User-Agent constant (duplicated in 5 files).
- Shared XML-parsing helpers across the 5 importers.

## 5. Split / clean god modules & misc debt

- Split `config.py` (1,625 lines): extract paper-weight validation and
  OpenAthens URL validation; replace debug `print()` with logger calls.
- Split `utils/browser_downloader.py` (2,402 lines) per download strategy.
- Delete or de-duplicate the dormant `gui/qt/plugins/settings/` +
  `gui/qt/tabs/*` mirror of `gui/qt/plugins/configuration/`.
- **Pool the Qt GUI session's DB connection.** Login (`gui/qt/core/
  application.py` + `dialogs/login_dialog.py`) keeps the raw
  `psycopg.connect()` it opens for authentication as `self._db_connection`
  and reuses it for every settings operation for the whole session,
  bypassing the pool. The dialog *must* connect raw (it runs before any
  `DatabaseManager` exists and the user picks DB params in the dialog), and
  the acute aborted-transaction wedge is already mitigated by the July 2026
  rollback guard in `UserSettingsManager` — so this is cleanup, not a live
  bug. Doing it right means: after login succeeds, stand up a
  `DatabaseManager` for the chosen params (today it reads only env vars —
  needs explicit-conninfo support or setting env first), acquire a
  `PersistentConnection`, thread it through `config.set_user_context()`, and
  release it on logout/shutdown. Structural; interacts with Qt startup
  ordering and the fragile Qt test suite.
- Backfill idempotency (golden rule 15) on migrations 004, 008, 012, 013,
  022.
- Golden-rule sweeps: inline `setStyleSheet()` calls (rule 9), hardcoded
  pixel dimensions (rule 10), `print()` in library code (rule 8),
  `embeddings/embedding_server.py` raw-HTTP Ollama backend (rule 4).
- Named constants for hardcoded paths/timeouts (queue DB path, discovery
  timeouts).
- **Revisit `DEFAULT_ANTHROPIC_MAX_TOKENS` (4096).** Anthropic requires a
  positive `max_tokens`, so `LLMClient._resolve_max_tokens` substitutes
  this default wherever a call site passes `None` — which most do, since
  under Ollama `None` means "generate until the model stops". Every such
  site is therefore silently capped at 4096 tokens on an `anthropic:`
  model. Fine for extraction and scoring; likely too low for report
  synthesis and long HyDE abstracts. Needs a per-call-site audit now that
  PR #249 has made `anthropic:` models actually reachable everywhere.
- Fix OpenAthens session file TOCTOU (write-then-chmod → `os.open(...,
  0o600)`).
- Decide the fate of `source_reliability` scoring (currently a no-op
  neutral 5.0), `validation/ExperimentService`, and `benchmarking/` if
  their sole callers are removed.
- **Move `TransparencyAssessment` invariants into the type.** Validation
  of LLM output lives only in `TransparencyAgent._validate_assessment_data`;
  any other constructor (CLI reload, tests) bypasses it. Add a cheap
  `__post_init__` that normalizes `data_availability` through the enum and
  derives `risk_level` from `classify_risk()` (today it is set by mutation
  after construction), type `data_availability`/`risk_level` with their
  `str` enums, and make the distribution buckets a small enum so
  `get_score_distribution()` cannot `KeyError` on a typo. Related:
  `paper_weight/db.py`'s `pmid_select_expr()` relies on callers placing the
  PubMed id at the matching positional `%s` — switch to a named
  placeholder or return `(expr, params)` like `build_source_filter_clause`.

## Tracked separately on GitHub

- [#230](https://github.com/hherb/bmlibrarian/issues/230) — Fact-checker
  `insert_ai_evaluation` MAX(version)+1 race under concurrent writers.
- [#231](https://github.com/hherb/bmlibrarian/issues/231) — Settings
  categories: Python whitelist and SQL CHECK constraints can drift, no
  hermetic guard.
- [#250](https://github.com/hherb/bmlibrarian/issues/250) — Three model
  pickers reach Ollama over raw HTTP, which the AST-based LLM boundary
  guard cannot see. Extend the guard to the REST endpoints too.
- [#251](https://github.com/hherb/bmlibrarian/issues/251) — Unmarked tests
  hitting a live database and a live Ollama; two more collection-error
  files; assert-free tests that cannot fail. Overlaps §2 above.
- [#252](https://github.com/hherb/bmlibrarian/issues/252) —
  `SemanticChunkProcessor` still speaks the old ollama API and is
  unreachable: wire it onto `LLMClient` or delete it.
- [#273](https://github.com/hherb/bmlibrarian/issues/273) — Fact-checker
  records infrastructure failures (DB/Ollama down) as `maybe` verdicts.
- [#274](https://github.com/hherb/bmlibrarian/issues/274) —
  TransparencyAgent failure reasons and batch failures are not surfaced to
  callers.
- [#275](https://github.com/hherb/bmlibrarian/issues/275) — `paper_weight/db.py`
  query helpers return `[]`/`None` on database errors.

## Out of scope for now

- Anything requiring a rewrite of the multi-agent workflow orchestration
  itself (`cli/workflow_steps.py`) — it works; only the legacy
  `agents/orchestrator.py` API needs a decision (fix or deprecate/remove,
  see HANDOVER).
