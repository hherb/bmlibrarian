# HANDOVER

Working notes for picking up in-flight work. Each section is one
self-contained slice: what's known, where to start, and how to verify.
Remove a section once its slice has landed; add a new section when handing
off new work. Longer-term structural items live in
[ROADMAP.md](ROADMAP.md) — pull one in here once you're about to start it.

---

## Recently landed (context)

- **P1 backend correctness batch** (2026-10-15, branch
  `fix/p1-backend-correctness`): six items from the 2026-07-19 review.
  `database.py` BM25/fulltext search now bind source ids via the pure
  `build_source_filter_clause()` (one `ANY(%s)` array param);
  `CounterfactualAgent.find_contradictory_literature` guards each document's
  scoring (`scoring_error` callback) so one bad doc no longer aborts the
  search; `factchecker/agent/fact_checker_agent.py` honours explicit
  `0`/`0.0` overrides; `paper_weight/db.py` labels `external_id` as `pmid`
  only for PubMed rows (`pmid_select_expr()`, PubMed id from the per-DB
  source cache) and numeric PMID search is restricted to PubMed;
  `TransparencyAgent` validates LLM output (`_validate_assessment_data()` +
  pure `coerce_bounded_float`/`coerce_str_list`), guards each document in
  `assess_batch`, and its score buckets now share `classify_risk()`'s
  thresholds (labels `0-3`/`3-6`/`6-10`). Deleted the dead legacy
  `agents/fact_checker_agent.py` + `agents/fact_checker_db.py`, and rewrote
  the 7 red `tests/test_fact_checker_agent.py` tests that still targeted the
  legacy API (one, `_generate_summary`, had no live equivalent and was
  dropped).

- **Database state and embedding decision** (2026-10-15): the clean Phase A
  PubMed import (HTTPS + MD5, 41.2 M records, ledger, withdrawals) lives in
  PG18 **`bmlibrarian_dev`** (:5532). The December 2025 legacy import in PG18
  `bmlibrarian` was **dropped** (owner-approved; `~/.bmlibrarian/.env_pg18`
  now names a missing database), as were the spike schemas `spike_ingest` and
  `bm25_eval` in dev. `knowledgebase` (:5432) is kept for now: it holds user
  data (factcheck, audit, paper weights, …), Europe PMC full texts and the
  running apps. **Vectors will be embedded from scratch** from the clean
  import (no legacy-vector copy), resumable and partitioned, 256 d unless a
  pre-run gate shows a major gain for 512 d — see
  `doc/planning/rust/implementation_plan.md` §0, §3.3, Phase C. Document IDs
  differ between all databases; carry-over must remap by PMID/DOI.

- **PubMed withdrawals + pytest production guard** (2026-10-15, PR #270):
  DeleteCitation PMIDs are recorded in `ingest.withdrawn_pmid` (migration 032)
  and marked in the baseline `document.withdrawn_date` / `withdrawn_reason`,
  which every SQL search function already excludes. 032's first revision used
  a separate `document.withdrawn` column that the search functions ignored;
  migration 033 copies marks into `withdrawn_date` and drops the column. The
  7 622 marks were in `bmlibrarian_dev` and 033 is already applied there.
  `knowledgebase` has the empty first-revision column and no marks: 033 will
  just drop it on the next non-test connection. `db_test_guard.py` is now an
  allow-list: under pytest every DB without a `dev`/`test*` name token is
  protected (no migrations, read-only conninfo, also in spawned import
  workers).
  `tests/test_withdrawn_search_filters.py` pins the search filters.
  Remaining gap: direct `psycopg.connect()` callers (ROADMAP §2).

- **July 2026 review follow-ups** (details in `doc/TODO_code_review_2026-07.md`
  and git history): P0 fixes (PR #229); test-suite hang fixes +
  `pytest-timeout`; LLM layer fully delegated to `bmlib.llm`, boundary
  enforced by `tests/test_llm_layer_boundary.py` (PR #249) and BaseAgent
  per-call `model`/`temperature`/`top_p`/`think` overrides; connection and
  concurrency fixes (atomic queue dequeue, pooled-connection leaks, per-DB
  source-id cache); `db_conninfo.build_conninfo()` as the only way to build a
  libpq string + bound pagination (`doc/llm/db_conninfo.md`); archive
  path-traversal guard `utils/path_utils.is_safe_archive_member()`
  (`doc/llm/archive_extraction_safety.md`); dependabot cleanup (PR #256,
  only the `diskcache` alert remains).
- **Known pre-existing red tests** (mock targets removed by refactors, not
  regressions): `tests/paperchecker/test_search_coordinator.py::`
  `TestEmbeddingGeneration` patches the removed `search_coordinator.ollama`;
  `tests/test_paper_weight_persistence.py::TestLLMJSONParsing` mocks the
  removed `PaperWeightAssessmentAgent._get_db_connection`;
  `test_resolvers.py::test_construct_proxy_url`,
  `test_medrxiv_importer.py::test_initialization_with_custom_pdf_dir`.

## Next up (imminent — from the 2026-07-19 review, P1)

Pick items in whichever order matches what you're touching; they're
independent unless noted.

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
- **Orchestrator / importer leftovers**: old `agents/orchestrator.py`
  `Workflow.execute_workflow` wedges forever on a failed dependency
  (superseded by `cli/workflow_steps.py` but still exported/documented — fix
  or deprecate + update `doc/users/queue_system_guide.md`); ClinicalTrials
  matching does a per-trial leading-wildcard `LIKE` over full text — needs
  an indexed strategy at scale.

## LLM-layer polish follow-up (from 2026-07-22 slice)

The BaseAgent per-call-override work (see "Recently landed") unblocks two
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

### Verify

- The suite has a **large pre-existing failure baseline**, not "two". Measured
  2026-10-15 on `fix/p1-backend-correctness` with DB/Ollama/GUI-free markers
  deselected (`.venv/bin/python -m pytest tests/ -m "not integration and not
  requires_database and not requires_ollama and not slow"
  --continue-on-collection-errors -p no:cacheprovider --no-cov`): **98
  failed, 2818 passed, 38 errors** (master before it: 105 failed).
  Do NOT eyeball the count — it's meaningless against that baseline. To check
  for regressions, capture the failing node-ID set (`grep -E '^(FAILED|ERROR)
  tests/'`), `git stash`, re-run, and `diff` the two sets: the gate is **zero
  nodes failing in your tree that pass on `master`**. (This is why ROADMAP §2
  "make the test suite protect you" matters — there is no CI and the baseline
  is badly broken.) Pre-existing clusters: `prisma2020_lab`, `paperchecker/
  search_coordinator`, `paper_weight*`, `reporting_agent`, `citation_agent`,
  `qt_*`, `ollama_migration`, `openathens_auth`,
  `europe_pmc_pdf_downloader`.
- Full-tree runs need `--continue-on-collection-errors` (still ~6 collection
  errors) and, per the 2026-07-20 fix, avoid the `requires_database`/
  `integration` hangs by keeping those markers deselected.
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
