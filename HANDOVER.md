# HANDOVER

Working notes for picking up in-flight work. Each section is one
self-contained slice: what's known, where to start, and how to verify.
Remove a section once its slice has landed; add a new section when handing
off new work. Longer-term structural items live in
[ROADMAP.md](ROADMAP.md) — pull one in here once you're about to start it.

---

## Recently landed (context)

- **Systematic-review resume rebuilt on one shared pipeline** (2026-10-16,
  branch `fix/systematic-review-resume`): the review phases after search
  planning now exist once, in `agents/systematic_review/pipeline.py`;
  `run_review()` enters at the search stage, `run_review_from_checkpoint()`
  at the stage after the checkpoint (`RESUME_STAGE_BY_CHECKPOINT`). Stages
  read evaluations back from the store and skip documents already evaluated
  in the run, so resume no longer re-scores; resume runs the configured
  (phased) search and applies the quality-gate threshold; runs end
  `completed`/`paused`/`failed` and resume reopens them
  (`EvaluationStore.reopen_run`); an unrestorable run raises `ResumeError`;
  relevance thresholds changed between stop and resume are honoured (GUI
  applies its overrides on resume).
  Also fixed: fresh-run `UnboundLocalError` when everything was cached or
  nothing passed relevance, 0.0 scores missing from exclusions, resume
  statistics double-counting, `systematic_review_cli.py` never passing
  `db_manager`. Agent-level tests: `tests/test_systematic_review_pipeline.py`;
  docs: `doc/developers/systematic_review_pipeline.md`.
  Review follow-up (same PR #284): failed LLM evaluations are no longer
  saved as real scores (flagged *uncertain*, retried on resume); a failed
  save stops the review (`EvaluationSaveError`); a rejected checkpoint returns
  `result.aborted`/`abort_reason` (CLI prints REVIEW STOPPED, writes no
  report); resume validates the whole checkpoint (`parse_checkpoint`) before
  touching agent state; `reopen_run` returns the refreshed run; `reset()` only
  fails in-progress runs; CLI `--resume` honours the threshold flags (default:
  the checkpoint's) and no longer crashes on `result.criteria`; warnings reach
  the GUI activity log (`EVENT_REVIEW_WARNING`). Deferred: #285 (agent's
  `db_manager` ignored by fetches/searches), #286 (legacy runs holding saved
  failure placeholders), #287 (DB-backed run-lifecycle test).
- **PMC discovery moved to the PMC Cloud Service** (2026-10-16, PR #282):
  PMC removed the FTP `oa_package`/`oa_pdf` trees **and** the OA Web
  Service (`oa.fcgi`, now 404) in August 2026, so `PMCResolver`'s main path
  had silently found nothing since. New `discovery/pmc_cloud.py` looks the
  PMCID up in the `pmc-oa-opendata` bucket over HTTPS (S3 listing →
  per-version metadata JSON → prefer non-retracted, published over
  manuscript, highest version) and emits a `SourceType.PMC_CLOUD` source
  (replaces `PMC_PACKAGE`); `PMCCloudDownloader` fetches the PDF and the
  JATS XML (saved as `fulltext/<year>/<stem>.nxml`, parsed into
  `DownloadResult.full_text`) with MD5 verification and one retry loop per
  file. The tar.gz/FTP package code is gone; `NXMLParser` moved to
  `discovery/nxml_parser.py` (importers updated). Remaining
  `ftp://ftp.ncbi.nlm.nih.gov` URLs are rewritten to HTTPS. Verified live
  (PMC5334499: PDF + 31.7 k chars of full text). **`pmc_bulk_cli`
  list/download/sync are broken for the same reason → #283** (structural;
  rebuild on the S3 inventory).
- **Discovery rate limiting** (2026-10-16, same PR #282): new `utils/rate_limit.py` —
  process-wide per-host `HostRateLimiter` (NCBI 0.34 s, Unpaywall 0.1 s,
  CrossRef/doi.org 0.2 s, other hosts 1 s) and `RateLimitedSession`, which
  retries 429 / 503+Retry-After honouring the server delay (≤ 60 s, 3
  retries) and defers the host for every caller. All resolvers, the
  finder's download session, both FTP paths and PMC's `curl` fallback are
  paced; `_download_from_source` no longer re-retries a throttled
  response and uses jittered backoff. Also fixed: `OpenAthensResolver`
  rewrote EZproxy-style URLs (`https://proxy.example.com`) into Redirector
  URLs although `FullTextFinder` admitted them as proxies — both now share
  `is_traditional_proxy_url()`; four stale browser-fallback tests in
  `test_pdf_discovery_download.py` patched a non-existent module attribute.
- **Flet GUI retired** (2026-10-16, PR #277, merged): Flet 1.0 would have
  needed a ~25k-line behavioural rewrite, and every Flet app except the
  Citation lab had a Qt equivalent. `fact_checker_review_gui.py` and
  `scripts/{query,pico,prisma2020,study_assessment}_lab.py` now open Qt
  plugins (`gui/qt/core/standalone.py`); `lab/__init__` is lazy;
  `tests/test_no_flet.py` guards against Flet coming back. Remaining
  Flet-only features (notably multi-model query generation, now unwired) →
  ROADMAP §1. Note: `--blind` really hides AI/original columns only since
  this PR — rerun any blind annotation done with the Qt tab before it.
- **P1 GUI batch** (2026-10-16, PR #276, merged): "Find PDF" runs on
  `PDFDiscoveryWorker` (`FindPdfOutcome` reports the real reason);
  research-tab step handlers no longer run twice; `citation_widget` uses
  `AbstractFactCheckerDB.get_document_details()`; `extract_pmid()` stops
  reporting non-PubMed ids as PMIDs. Pre-existing issues filed: #278
  (FETCH verification prompt on a worker thread), #279 (CrossRef DOI
  written before verification), #280 (review packages assume PubMed is
  source id 1).

- **P1 backend correctness batch** (2026-10-15, PR #272): parameterised
  source filters, per-document guards in counterfactual + transparency
  batches, explicit `0` overrides honoured in the fact-checker, PubMed-only
  PMIDs in `paper_weight`, validated TransparencyAgent LLM output; dead
  legacy `agents/fact_checker_*` deleted.

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
  `test_medrxiv_importer.py::test_initialization_with_custom_pdf_dir`.

## Next up (imminent — from the 2026-07-19 review, P1)

Pick items in whichever order matches what you're touching; they're
independent unless noted.

- **Citation fuzzy-match hotspot** — `agents/citation_agent.py:156-225`:
  O(passage×abstract) `SequenceMatcher` × retries × every doc above
  threshold. Cap lengths or bound the approximate match.
- **Orchestrator / importer leftovers**: old `agents/orchestrator.py`
  `Workflow.execute_workflow` wedges forever on a failed dependency
  (superseded by `cli/workflow_steps.py` but still exported/documented — fix
  or deprecate + update `doc/users/queue_system_guide.md`); ClinicalTrials
  matching does a per-trial leading-wildcard `LIKE` over full text — needs
  an indexed strategy at scale.

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

### Verify

- The suite has a **large pre-existing failure baseline**, not "two". Measured
  2026-10-16 with DB/Ollama/GUI-free markers deselected
  (`.venv/bin/python -m pytest tests/ -m "not integration and not
  requires_database and not requires_ollama and not slow"
  --continue-on-collection-errors -p no:cacheprovider --no-cov`): master
  after PR #282 **156 failed, 3492 passed, 19 errors**;
  `fix/systematic-review-resume` the same 156 failed + 19 errors nodes,
  3527 passed (new pipeline tests; 0 regressions). An unfiltered run
  (`pytest tests/ --continue-on-collection-errors`, ~13 min) after the review
  follow-up: 162 failed + 19 errors, identical node set to the PR's first
  commit, 3647 passed. Most failures are Qt test files that
  died at collection before the Flet removal and are stale against the
  current API (e.g.
  `test_qt_research_tab.py` targets `_update_citations_tab`, `query_input`;
  `test_prisma2020_lab_plugin.py`, `test_qt_workflow_thread.py`,
  `test_ollama_migration.py`). Compare against a `git worktree` of master run
  with `PYTHONPATH=<worktree>/src` (the editable install otherwise imports
  your tree).
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
