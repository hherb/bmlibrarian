# HANDOVER

Working notes for picking up in-flight work. Each section is one
self-contained slice: what's known, where to start, and how to verify.
Remove a section once its slice has landed; add a new section when handing
off new work. Longer-term structural items live in
[ROADMAP.md](ROADMAP.md) — pull one in here once you're about to start it.

---

## Recently landed (context)

- **Whole-project code review, P0 fixes** (2026-07-19, PR #229): broken CLI
  login, settings-category drift, non-functional PMC bulk import fixed
  (2f4a8a9); PDF downloads now validated by magic bytes with cleanup of
  partial downloads (09d69e5); per-record `SAVEPOINT` semantics added to
  batch importers so one bad record doesn't abort a whole batch (b99af11);
  `bmlibrarian.cli` name collision resolved and the deprecated Flet
  paper-checker lab removed (f3d542b). Remaining P1/P2 findings captured in
  `doc/TODO_code_review_2026-07.md` and reorganized into
  [ROADMAP.md](ROADMAP.md).
- **PR review follow-ups** (2026-07-19, 75aba14): atomic downloads,
  validated browser fallback, honest stats reporting — closed out review
  comments from PR #229 before merge.
- Dead legacy fact-checker modules (`agents/fact_checker_db.py`,
  `agents/fact_checker_agent.py`) noted as unused (superseded by
  `bmlibrarian.factchecker`) but **not yet deleted** — see ROADMAP §5. Two
  pre-existing test failures unrelated to the July fixes are documented in
  the TODO doc (`test_resolvers.py::test_construct_proxy_url`,
  `test_medrxiv_importer.py::test_initialization_with_custom_pdf_dir`) —
  don't treat these as regressions from your own changes.

## Next up (imminent — from the 2026-07-19 review, P1)

Pick items in whichever order matches what you're touching; they're
independent unless noted.

- **Queue task-claiming race** — `agents/queue_manager.py:487-523`:
  SELECT-then-UPDATE dequeue isn't atomic across processes. Fix with a
  single `UPDATE … WHERE id = (SELECT … ORDER BY priority DESC, created_at
  ASC LIMIT 1) RETURNING *`, or `BEGIN IMMEDIATE`.
- **Signal-handler deadlock** — `agents/queue_manager.py:88,101-103,
  175-196`: SIGINT/SIGTERM handler acquires the same non-reentrant lock the
  interrupted code may already hold. Don't take the lock in the handler;
  only register handlers on the main thread (also fixes the
  off-main-thread `ValueError` from `signal.signal()`).
- **ThesaurusExpander pool leak** — `thesaurus/expander.py:120-136`: builds
  a fresh `DatabaseManager()` per uncached term, never closed. Use
  `get_db_manager()`.
- **Connections used after return-to-pool** —
  `importers/pubmed_bulk_importer.py:1048-1127` and
  `importers/pdf_matcher.py:136-137`. Use `PersistentConnection`
  (`database.py:242`) or restructure to per-operation acquisition.
- **GUI session rides one raw unpooled psycopg connection** —
  `gui/qt/core/application.py:281-387` + `login_dialog.py`. Should come
  from the pool, as the CLI now does via `acquire_persistent_connection()`.
- **Class-level source-ID cache** — `database.py:34-36,147-171`: a second
  `DatabaseManager` against a different database silently reuses the first
  database's source IDs. Key per-conninfo or make instance-level.
- **Conninfo built by unescaped string concatenation** (×3) —
  `database.py:71`, `gui/qt/core/application.py:274-280`,
  `login_dialog.py:607-613`. Use `psycopg.conninfo.make_conninfo(**kwargs)`
  in one shared helper.
- **f-string LIMIT/OFFSET** — `database.py:453-461` (`find_abstracts`);
  sibling `find_abstract_ids` already binds params properly — match it.
- **"Find PDF" freezes the UI** —
  `gui/qt/qt_document_card_factory.py:1053-1177`: synchronous network
  discovery in the click slot. The `PDFFetchWorker` QThread pattern already
  exists in the same file — use it here too.
- **Duplicate signal wiring** —
  `gui/qt/plugins/research/research_tab.py:150-164` vs.
  `workflow_handlers.py:175-208`: fires twice per search. Remove one
  connection site.
- **`citation_widget` hand-rolled document SQL** —
  `gui/qt/plugins/fact_checker/citation_widget.py:224-297`: violates golden
  rule 18. Replace with `get_document_details()`.
- **No rate limiting / 429 handling in discovery** —
  `discovery/resolvers.py` + `full_text_finder.py`. Add a shared rate
  limiter + Retry-After handling before running batch PDF discovery again.
- **Multiplicative FTP retries** —
  `discovery/pmc_package_downloader.py:1067-1105`: outer retry wraps an
  inner retry, up to 9 attempts per package. Collapse to one level.
- **Counterfactual scoring loop unguarded** —
  `agents/counterfactual_agent.py:546-558`: no per-document try/except;
  match `batch_evaluate_documents`'s pattern.
- **Citation fuzzy-match hotspot** — `agents/citation_agent.py:156-225`:
  O(passage×abstract) `SequenceMatcher` × retries × every doc above
  threshold. Cap lengths or bound the approximate match.
- **Systematic-review resume correctness**: resume paths skip
  `already_evaluated_ids` filtering (`resume_mixin.py:1197-1214,719-731`),
  ignore `use_phased_search` (`:487-546`), never mark evaluation runs
  complete (`agent.py:680-703`), and silently return empty results if a run
  can't be restored (`resume_mixin.py:471-485` — raise instead of warn).
  There's also a dead legacy checkpoint branch reading `"scored_papers"`
  (`:451-469`) to remove or document.
- **Fact-checker / assessment agents**: falsy-default bug in
  `fact_checker_agent.py:253-255` (`or` swallows explicit `0`/`0.0` — use
  `is not None`); transparency risk thresholds diverge between
  `transparency_data.py:220-231` and `transparency_agent.py:768-795`;
  `TransparencyAgent` bare `float()` on LLM fields aborts the whole batch on
  bad data (port PRISMA2020Agent's `_validate_assessment_data()` pattern);
  `paper_weight/db.py` mislabels `external_id as pmid` at `:552,625,712`
  (correct `CASE WHEN source_id…` pattern already exists at `:496`); old
  `agents/orchestrator.py` `Workflow.execute_workflow` wedges forever on a
  failed dependency (superseded by `cli/workflow_steps.py` but still
  exported/documented — fix or deprecate + update
  `doc/users/queue_system_guide.md`); archive extraction without
  path-traversal guards in `pmc_bulk_importer.py:688-696` (tar) and
  `medrxiv_meca_importer.py:456-459` (zip) — reuse `_is_safe_zip_member()`
  from `europe_pmc_pdf_downloader.py:778-810`; ClinicalTrials matching does
  a per-trial leading-wildcard `LIKE` over full text — needs an indexed
  strategy at scale; multi-model query generator hardcodes `num_predict:
  100` (retriggers the documented gpt-oss:20b empty-response bug) and
  bypasses `BaseAgent`/`LLMClient`.

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

### Verify

- `uv run python -m pytest tests/` → check for **no new failures** (two
  pre-existing ones are expected and unrelated — see above).
- `ruff check .` / `mypy src/` carry pre-existing debt; the gate is **no
  new errors**, not a clean baseline.
- `uv run python bmlibrarian_cli.py --quick` still runs end-to-end for a
  manual smoke check when touching the core agent workflow.
- Never run destructive tests against the production `knowledgebase`
  database — use `bmlibrarian_dev` (see CLAUDE.md "Database Safety").
