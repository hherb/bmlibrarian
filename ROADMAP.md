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

## 1. Finish the Flet → Qt migration, then delete Flet (~20k lines)

The Qt GUI (`gui/qt/`) has superseded the older Flet GUI (`gui/flet/` +
`factchecker/gui/`), but Flet cannot be deleted yet — several features
are Qt-incomplete:

1. **Qt fact-checker review tab is a partial port**: no SQLite
   review-package support, blind mode dead, `--incremental` label-only, no
   confidence dropdown, no inter-rater agreement dialog, missing "unclear"
   annotation option.
2. **`lab/citation_lab.py` has no Qt port.**
3. **Relocate framework-agnostic modules** Qt still imports out of
   `gui/flet/` (`report_builder.py`, `document_card_factory_base.py`) into
   e.g. `gui/shared/`.
4. **Remove the eager `from .flet import …`** in `gui/__init__.py` so the
   Qt app doesn't require flet installed.
5. **Repoint the four Flet lab launchers** (`scripts/{pico,prisma2020,
   query,study_assessment}_lab.py`) to the Qt plugins.
6. Then delete `gui/flet/` (minus relocated files), `factchecker/gui/`,
   the Flet shims in `gui/` root, Flet `lab/*` modules, the two Flet-only
   entry points, and drop `flet[all]` from pyproject. Accept the loss of
   `--web`/`--port` browser mode and `--auto`/`--quick` (consider porting
   auto-run flags to `bmlibrarian_qt.py` first).

## 2. Make the test suite protect you

- Fix 5 files with unconditional pytest collection errors (manual scripts
  masquerading as `test_*` functions with required args).
- Adopt `requires_database`/`requires_ollama` markers project-wide (only
  5/145 files use them today) so `pytest -m "not requires_database"` is a
  hermetic default.
- Add real asserts to assert-free tests.
- Add per-importer write-path smoke tests against a throwaway schema.
- Reconcile the ">95% coverage" claim in CLAUDE.md with the actual
  `--cov-fail-under=80` baseline.

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
- Backfill idempotency (golden rule 15) on migrations 004, 008, 012, 013,
  022.
- Golden-rule sweeps: inline `setStyleSheet()` calls (rule 9), hardcoded
  pixel dimensions (rule 10), `print()` in library code (rule 8),
  `embeddings/embedding_server.py` raw-HTTP Ollama backend (rule 4).
- Named constants for hardcoded paths/timeouts (queue DB path, discovery
  timeouts).
- Fix OpenAthens session file TOCTOU (write-then-chmod → `os.open(...,
  0o600)`).
- Decide the fate of `source_reliability` scoring (currently a no-op
  neutral 5.0), `validation/ExperimentService`, and `benchmarking/` if
  their sole callers are removed.

## Tracked separately on GitHub

- [#230](https://github.com/hherb/bmlibrarian/issues/230) — Fact-checker
  `insert_ai_evaluation` MAX(version)+1 race under concurrent writers.
- [#231](https://github.com/hherb/bmlibrarian/issues/231) — Settings
  categories: Python whitelist and SQL CHECK constraints can drift, no
  hermetic guard.

## Out of scope for now

- Anything requiring a rewrite of the multi-agent workflow orchestration
  itself (`cli/workflow_steps.py`) — it works; only the legacy
  `agents/orchestrator.py` API needs a decision (fix or deprecate/remove,
  see HANDOVER).
