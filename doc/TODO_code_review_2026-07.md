# Code Review TODO — July 2026

Remaining findings from the whole-project review of 2026-07-19. The P0 items
(broken features, silent data loss) were fixed on this branch — see the
commit history. Everything below is confirmed against the code as of the
review; re-verify line numbers before fixing, they will drift.

## P1 — Reliability under load

### Concurrency / resources
- [x] **Queue task-claiming race** — `agents/queue_manager.py`: dequeue is now a single atomic `UPDATE … WHERE id = (SELECT … ORDER BY priority DESC, created_at ASC LIMIT 1) RETURNING *`. (2026-07-21)
- [x] **Signal-handler deadlock** — `agents/queue_manager.py`: handler no longer acquires the non-reentrant lock (`acquire_lock=False` path); handlers register only on the main thread. (2026-07-21)
- [x] **ThesaurusExpander pool leak** — `thesaurus/expander.py`: now uses `get_db_manager()` instead of a fresh `DatabaseManager()` per term. (2026-07-21)
- [x] **Connections used after return-to-pool** — `importers/pubmed_bulk_importer.py` stores transparency metadata inside the live `with` block; `importers/pdf_matcher.py`'s long-lived `PDFManager` no longer holds a pooled conn (only needs `base_dir`). (2026-07-21)
- [ ] **GUI session rides one raw unpooled psycopg connection** — `gui/qt/core/application.py:281-387` + `gui/qt/dialogs/login_dialog.py`: login's raw `psycopg.connect()` is kept as `self._db_connection` and used for all settings operations for the whole session, bypassing `DatabaseManager`. (The rollback-on-error guard added to `UserSettingsManager` in July 2026 mitigates the aborted-transaction wedge, but the connection should come from the pool, as the CLI now does via `acquire_persistent_connection()`.) **Deferred to ROADMAP §5 (2026-07-21): structural, acute risk already mitigated.**
- [x] **Class-level source-ID cache** — `database.py`: `_source_id_caches`/`_source_ids_by_conninfo` are now keyed per-conninfo. (2026-07-21)
- [x] **Conninfo built by unescaped string concatenation** (×4, one more than the review's ×3 — `login_dialog.py` had two sites) — `database.py`, `gui/qt/core/application.py`, `gui/qt/dialogs/login_dialog.py` (`_on_test_connection` + `_get_db_connection`): all now route through the shared `bmlibrarian.db_conninfo.build_conninfo()` helper, which delegates to `psycopg.conninfo.make_conninfo` (quotes/escapes every value; drops `None`/empty). A password containing a space or quote is now safe. (2026-07-22)
- [x] **f-string LIMIT/OFFSET** — `database.py` `find_abstracts`: now uses the pure `build_pagination_clause(max_rows, offset)` helper, which returns `%s` placeholders + bound params (matching the sibling `find_abstract_ids`). Unit-tested in `tests/test_db_conninfo.py`. (2026-07-22)
- [x] **f-string source_id filters** — `database.py` `search_with_bm25`/`search_with_fulltext_function`: build `source_id = {id}` / `ANY(ARRAY{others})` clauses via f-string interpolation. Not injectable today (IDs are DB-sourced ints resolved from the source cache), but same class as the LIMIT/OFFSET item — bind them (or build the array param) once the shared query helper lands. **Done 2026-10-15:** pure `build_source_filter_clause()` binds all selected ids as one `source_id = ANY(%s)` array param; tests in `tests/test_db_conninfo.py`. Review follow-up: semantics now match `find_abstracts` (all selected → no filter; selection resolving to nothing → no rows instead of all sources).

### Qt / GUI
- [x] **"Find PDF" freezes the UI** — `gui/qt/qt_document_card_factory.py:1053-1177`: full network discovery (CrossRef/Unpaywall + optional 60 s browser automation) runs synchronously in the click slot. Wrap in a QThread worker — the correct pattern (`PDFFetchWorker`) already exists in the same file. **Done 2026-10-16 (PR #276):** `PDFDiscoveryWorker` + `FindPDFSession`; outcomes reported via `FindPdfOutcome`; sessions stopped on quit.
- [x] **Duplicate signal wiring** — `gui/qt/plugins/research/research_tab.py:150-164` vs `workflow_handlers.py:175-208`: `_on_query_generated`/`_on_documents_found` fire twice per search (executor signals AND the thread's re-emitted signals are both connected). Currently masked by idempotent handlers; remove one connection site. **Done 2026-10-16 (PR #276):** WorkflowThread is the single source.
- [x] **citation_widget hand-rolled document SQL** — `gui/qt/plugins/fact_checker/citation_widget.py:224-297`: inline SELECT with positional tuple unpacking violates golden rule 18; 8 other GUI files correctly use `get_document_details()`. Column reorder silently swaps fields. **Done 2026-10-16 (PR #276):** `AbstractFactCheckerDB.get_document_details()`; DB errors are reported, not shown as missing data.

### External-API behavior
- [x] **No rate limiting / 429 handling in discovery** — `discovery/resolvers.py` + `full_text_finder.py`: up to ~8 external requests per document against Unpaywall/CrossRef/PMC/doi.org with no delay and no 429 handling, while bulk CLIs carefully expose `--delay`. Add a shared rate limiter + Retry-After handling before batch PDF discovery burns API goodwill. **Done 2026-10-16:** `utils/rate_limit.py` — process-wide per-host `HostRateLimiter` + `RateLimitedSession` (429 / 503+Retry-After retried, server delay honoured, capped at 60 s); all resolvers, the finder's download session, both FTP paths and the PMC `curl` fallback are paced; `_download_from_source` no longer re-retries a 429.
- [x] **Multiplicative FTP retries** — `discovery/pmc_package_downloader.py:1067-1105` outer retry loop wraps `_download_ftp()`'s own retry loop (`:1139-1200`) → up to 9 attempts per package against NCBI. Collapse to one level. **Done 2026-10-16, then superseded:** PMC removed the FTP packages in August 2026, so the package downloader was replaced by `discovery/pmc_cloud.py` (PMC Cloud Service over HTTPS, one MD5-verified retry loop per file).
- [x] **Counterfactual scoring loop unguarded** — `agents/counterfactual_agent.py:546-558`: no per-document try/except although `evaluate_document()` raises; one bad document aborts the whole contradictory-evidence search and discards accumulated evidence. Match the `batch_evaluate_documents` pattern. **Done 2026-10-15:** per-document try/except, `scoring_error` callback, failed count in the `scoring_complete` message. Review follow-up: `ConnectionError` still aborts; the summary reports `documents_failed_scoring` / `scoring_incomplete`, and `revised_confidence` is `UNVERIFIED` when every found document failed to score (not a false all-clear).
- [ ] **Citation fuzzy-match hotspot** — `agents/citation_agent.py:156-225`: sliding-window `SequenceMatcher` is O(passage×abstract) × up to 4 retries × every doc above threshold. Cap lengths or use a bounded approximate-matching approach.

### Systematic-review resume correctness (beyond the fixed scorer)
- [ ] **Resume re-runs LLM scoring/quality from scratch** — `agents/systematic_review/resume_mixin.py:1197-1214, 719-731`: `_continue_from_*` paths skip the `already_evaluated_ids` filtering `run_review()` does; with temperature 0.2 inclusion decisions can change across a crash/resume.
- [ ] **Resume ignores `use_phased_search`** — `resume_mixin.py:487-546`: always calls `execute_plan()`; phased search + query-effectiveness feedback silently dropped for every resumed run.
- [ ] **Evaluation runs never marked complete** — `agent.py:680-703`: `_complete_evaluation_run()` only called from `reset()`; every run row stays `in_progress` forever. Call it on success and in the failure handlers.
- [ ] **Silent empty result when evaluation run can't be restored** — `resume_mixin.py:471-485`: missing run only logs a warning; all getters then return `[]` and the review "succeeds" empty. Raise a clear resume error instead.
- [ ] Dead legacy checkpoint branch reading `"scored_papers"` — `resume_mixin.py:451-469`; remove or document.

### Fact-checker / assessment agents
- [x] **Falsy-default bug** — `agents/fact_checker_agent.py:253-255`: `max_documents or …` / `score_threshold or …` ignores explicit `0`/`0.0`; use `is not None`. **Done 2026-10-15:** fixed in the live `factchecker/agent/fact_checker_agent.py` (`is None`); the legacy `agents/` copy was deleted.
- [x] **Transparency thresholds diverge** — `agents/transparency_data.py:220-231` (LOW risk ≥ 6.0) vs `agents/transparency_agent.py:768-795` (stats bucket ≥ 7.0): derive both from the same constants. **Done 2026-10-15:** `get_score_distribution()` buckets via `score_distribution_label()`, which uses the same constants as `classify_risk()` (bucket labels now `0-<3` / `3-<6` / `6-10`).
- [x] **TransparencyAgent bare `float()` on LLM fields** — `transparency_agent.py:204-264`: null/non-numeric LLM values raise and abort the whole batch; port PRISMA2020Agent's `_validate_assessment_data()` pattern. **Done 2026-10-15:** `_validate_assessment_data()` + pure `coerce_bounded_float()`/`coerce_str_list()`; invalid required numbers fail just that document, optional ones default/clamp; `assess_batch` also guards each document. Review follow-up: out-of-range required numbers fail (no silent clamp of a 0-100 answer to 10); booleans via `coerce_optional_bool()` (`"false"` is no longer `True`); `data_availability` normalized to the enum; LLM registry IDs format-checked.
- [x] **paper_weight/db.py mislabels external_id as pmid** — `:552, :625, :712`: unconditional `external_id as pmid` for non-PubMed sources; the correct `CASE WHEN source_id…` pattern exists at `:496` in the same file (rule 18: prefer `get_document_details()`). **Done 2026-10-15:** all four queries use `pmid_select_expr()` with the PubMed source id resolved from the per-DB cache; numeric search filters to PubMed rows.
- [ ] **Old orchestrator `Workflow.execute_workflow` wedges forever on a failed dependency** — `agents/orchestrator.py:61-81, 256-306`: superseded by `cli/workflow_steps.py` but still exported and documented as the primary API in `doc/users/queue_system_guide.md`. Fix (cascade-fail + timeout) or deprecate/remove and update the doc.
- [ ] **Archive extraction without path-traversal guards** — `importers/pmc_bulk_importer.py:688-696` (tar), `importers/medrxiv_meca_importer.py:456-459` (zip): reuse `_is_safe_zip_member()` from `europe_pmc_pdf_downloader.py:778-810` as a shared helper.
- [ ] **ClinicalTrials matching design unusable at scale** — `importers/clinicaltrials_importer.py:280-306`: per-trial leading-wildcard `LIKE` over `full_text`/`abstract` = O(trials × full-table-scan) over ~hundreds of thousands of trials. Needs an indexed strategy (NCT-ID extraction into a column, trigram index, or tsvector).
- [ ] **Multi-model query generator** — `agents/query_generation/generator.py:168-176`: hardcodes `num_predict: 100` (re-triggers the documented gpt-oss:20b empty-response bug; QueryAgent enforces ≥400) and bypasses `BaseAgent`/`LLMClient` (own raw `ollama.Client`, no metrics). Also `QueryAgent.max_tokens` is dead config for `convert_question()`/`_generate_broader_query()` (`query_agent.py:155-159, 929-933`) — thread `num_predict=self.max_tokens` through.

## P2 — Structural debt (highest leverage first)

### 1. Finish the Flet → Qt migration, then delete Flet (~20k lines)
**Status 2026-10-16: done — Flet deleted and `flet` dropped from the dependencies** (flet 1.0 changed its event model). The Qt fact-checker tab now takes `--db-file`/blind/incremental and has the "unclear" option, but still no confidence dropdown (ROADMAP §1); `citation_lab.py` was removed without a Qt port (loss accepted); `report_builder.py` moved to `gui/qt/plugins/research/`, `document_card_factory_base.py` to `gui/`; the four lab launchers open the Qt plugins. Not ported: the inter-rater agreement statistics dialog, `session_id` stamping, and the Flet `--web`/`--port` and `--auto`/`--quick` launch options. The list below is kept as the original gap analysis.

Gap analysis (2026-07-19) found these must be closed BEFORE deleting:
1. **Qt fact-checker review tab is a partial port** (`gui/qt/plugins/fact_checker/`):
   - No SQLite review-package support: `fact_checker_tab.py` `_auto_load_data()` (~line 812) hardcodes `db_file=None`/postgresql; backend support exists (`factchecker/db/sqlite_db.py`) — add a package picker / `--db-file` path.
   - Blind mode dead: `self.blind_mode = False` never settable; add a toggle/flag.
   - `--incremental` is label-only: `_load_from_database()` never filters out already-annotated statements (Flet's `data_manager.load_from_database()` does).
   - No confidence dropdown (always saves `""`); DB column exists.
   - No inter-rater agreement statistics dialog (Flet has AI-vs-Original / Human-vs-AI / all-agree percentages).
   - Missing "unclear" annotation option; no `session_id` stamping on annotations.
2. **`lab/citation_lab.py` has no Qt port** (CitationFinderAgent prompt-tuning lab) — port or accept the loss.
3. **Relocate framework-agnostic modules Qt imports out of `gui/flet/`**: `gui/flet/report_builder.py` (used by `qt/plugins/research/workflow_thread.py`) and `gui/flet/document_card_factory_base.py` (used by `qt_document_card_factory.py`) → e.g. `gui/shared/`.
4. **Remove the eager `from .flet import …` block in `gui/__init__.py`** — currently the Qt app cannot start without flet installed.
5. Repoint/remove the four Flet lab launchers (`scripts/{pico,prisma2020,query,study_assessment}_lab.py`) to the Qt plugins. (Manual diff `lab/query_lab.py` 766 lines vs Qt 590 first.)
6. Then delete: `gui/flet/` (minus relocated files), `factchecker/gui/`, the Flet shims in `gui/` root (`research_app.py`, `workflow.py`, `ui_builder.py`, `ui_components.py`, `components.py`, `config_app.py`, `dialogs.py`, `card_factory.py`, `flet_document_card_factory.py`, `text_highlighting.py`, `unified_document_card.py`, `citation_card_utils.py`), Flet `lab/*` modules + `lab/document_display_factory.py`, entry points `bmlibrarian_research_gui.py` + `fact_checker_review_gui.py`, update `tests/test_gui_minimal.py` + `tests/test_document_card_factory.py`, and finally drop `flet[all]` from pyproject.
   Note: Flet-only features that will be lost (probably acceptable): `--web`/`--port` browser mode, `--auto`/`--quick` auto-run on launch. Consider adding auto-run flags to `bmlibrarian_qt.py`.

### 2. Make the test suite protect you
- [ ] Fix the 5 unconditional collection errors: `tests/test_ef_search.py`, `test_chunker_comparison.py`, `test_adaptive_chunker_performance.py`, `test_fast_chunker_performance.py`, `test_spacy_chunker_performance.py` define `test_*` functions with required positional args (they are manual scripts). Rename functions or move to `scripts/`.
- [ ] Mark live-service tests with the existing `requires_database`/`requires_ollama` markers (only 5/145 files use them; 74/145 are `__main__`-style scripts) so `pytest -m "not requires_database"` gives a hermetic suite.
- [ ] Add asserts to assert-free tests (`test_hybrid_search.py`, `test_reference_fix.py` uses `return True/False` which pytest ignores, `test_hyde.py`, `test_fallback_formatting.py`).
- [ ] Add per-importer write-path smoke tests against a throwaway schema (would have caught the PMC schema mismatch and the poisoned-transaction class).
- [ ] Reconcile the ">95% coverage" claim in CLAUDE.md with reality (`--cov-fail-under=80`, suite currently far below).

### 3. Consolidate the 29 top-level entry scripts
- [ ] Convert to `[project.scripts]` entries backed by a shared `cli_common` helper (env/config loading, logging setup, DB access via DatabaseManager). Kills the `sys.path.insert` boilerplate duplicated in 88 files.
- [ ] Eliminate the `src.bmlibrarian.*` import style (24 of 29 scripts + 7 test files): it loads a second copy of the package with separate config/DB-pool singletons, and test monkeypatching misses half the code. `model_benchmark_cli.py:43` is the worst case (also bypasses DatabaseManager at `:95`, as do `transparency_analyzer_cli.py:61-88` and `migrate_config_to_db.py:73`).
- [ ] `cli/config.py:47-59`: the `hasattr(self, '_from_defaults')` check is never true → CLI defaults never load from config.json's `search` section. Also `--quick` silently overrides explicit `--max-results` (`:191-207`) — warn or respect explicit flags.

### 4. Extract shared helpers (each is a current drift source)
- [ ] LLM call-with-retry + JSON-repair: 4 near-identical ~100-line `_call_llm` implementations in `paperchecker/components/` (statement_extractor, counter_statement_generator, hyde_generator, verdict_analyzer) + 3 different `_extract_json` variants; only hyde uses `repair_json`. Move into `BaseAgent`/`llm/`.
- [ ] DOI normalization: copy-pasted 4× (`discovery/resolvers.py:179-186, 593-597, 1052-1058`, `full_text_finder.py:953-959`), prefix lists already drifting.
- [ ] DOI→filename sanitization: `full_text_finder.py:1110-1114` + `pdf_manager.py:761-767` should use `utils/validation.py` `sanitize_filename()`.
- [ ] One Cloudflare detector: three divergent indicator lists inside `utils/browser_downloader.py` (~636, ~1675, ~1977).
- [ ] One User-Agent constant (currently duplicated in 5 files).
- [ ] Shared XML-parsing helpers for the importers (`_get_element_text_with_formatting`, `_format_abstract_markdown`, `_extract_date`, `_get_source_id` are copy-pasted across 5 importers).

### 5. Split / clean god modules & misc
- [ ] `config.py` (1,625 lines): extract the ~400-line paper-weight validation subsystem and OpenAthens URL validation; replace `print()` debug output (`:894, :907, :927, :929`) with logger calls.
- [ ] `utils/browser_downloader.py` (2,402 lines): three download strategies + SSO flow in one file; split per strategy.
- [ ] Delete or de-duplicate the dormant `gui/qt/plugins/settings/` + `gui/qt/tabs/*` mirror of `gui/qt/plugins/configuration/` (~1,145 lines of self-documented "mirrors functionality" duplication).
- [ ] Backfill idempotency on migrations 004, 008, 012, 013, 022 (bare `CREATE TABLE`/`CREATE INDEX`, INSERTs without `ON CONFLICT`) per golden rule 15.
- [ ] Golden-rule sweeps: 516 `setStyleSheet()` calls in `gui/qt` (rule 9 — route through `stylesheet_generator.py`; worst: `fact_checker_tab.py` ×37 with a private hex palette duplicating `theme_colors.py`); 59 hardcoded pixel dimensions (rule 10 — `dpi_scale.py`); 1,411 `print()` calls in `src/` library code (rule 8); `embeddings/embedding_server.py` raw-HTTP Ollama backend (rule 4) — either bless it as a documented exception or port to the ollama client.
- [ ] Hardcoded default queue DB path `Path.cwd()/"agent_queue.db"` (`queue_manager.py:83-85`) → config, absolute path.
- [ ] OpenAthens session file TOCTOU: write with default umask then chmod 600 (`utils/openathens_auth.py:318-341`) → open with `os.open(..., 0o600)`.
- [ ] `discovery`/`browser_downloader` magic timeout numbers → named constants.
- [ ] `InclusionEvaluator.evaluate()` docstring claims `Raises:` but swallows everything returning UNCERTAIN (`systematic_review/filters.py:935-1002`) — align docs and behavior.
- [ ] `source_reliability` scoring dimension now contributes a neutral 5.0 (no producer exists); implement a real source-reliability signal or set its default weight to 0.
- [ ] `validation/ExperimentService` is only used by `scripts/rechunk_semantic_chunks.py`; `benchmarking/` only by `model_benchmark_cli.py` — confirm still wanted, or fold/remove.
- [x] Delete dead legacy fact-checker modules `agents/fact_checker_db.py` + `agents/fact_checker_agent.py` (removed from `agents.__init__` exports with "moved to bmlibrarian.factchecker" comment; nothing imports them). Note: its `insert_ai_evaluation` hardcoded `version` — do NOT resurrect without porting the MAX(version)+1 fix from `factchecker/db/database.py`. **Done 2026-10-15.**
- [ ] Two pre-existing test failures unrelated to the 2026-07 fixes: `tests/discovery/test_resolvers.py::TestOpenAthensResolver::test_construct_proxy_url` (fails on main too) and `tests/test_medrxiv_importer.py::TestMedRxivImporter::test_initialization_with_custom_pdf_dir` (tries to mkdir at filesystem root).
