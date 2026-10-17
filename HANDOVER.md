# HANDOVER

Working notes for picking up in-flight work. Each section is one
self-contained slice: what's known, where to start, and how to verify.
Remove a section once its slice has landed; add a new section when handing
off new work. Longer-term structural items live in
[ROADMAP.md](ROADMAP.md) — pull one in here once you're about to start it.

---

## Recently landed (context)

- **Fact-check evaluation no longer starves on large evidence sets**
  (2026-10-18, PR #300, closes #296). Root
  cause, reproduced on the backed-up evidence: `gpt-oss:20b` reasons within
  `num_predict`, and on 49 citations it spent the flat 2,000 tokens on
  thinking and returned empty content (the prompt is only ~4 k tokens;
  context is 64 k, so not a context problem). The evaluation budget is now
  `evaluation_token_budget(max_tokens, n)` = `max_tokens` + 100 per citation;
  the three largest #296 sets (48–50 citations) now evaluate in 42–69 s.
  bmlibrarian's `LLMResponse` now carries bmlib's `stop_reason`, and
  `BaseAgent._checked_content` reports "Model hit the max_tokens limit (N)"
  instead of "Empty response", and logs a warning for an answer cut off at
  the limit (`TRUNCATION_STOP_REASONS`). **Still to do (owner's call,
  writes to `knowledgebase`):** re-run `fact_checker_cli.py --incremental`
  for the 76 statements whose fallback verdicts were deleted.
- **Citations must be complete sentences** (2026-10-17, branch
  `fix/citation-complete-sentences`, stacked on #297, closes #289; owner
  policy: fragments risk out-of-context quoting). The new pure module
  `utils/sentence_bounds.py` (`complete_sentence_span`, `is_sentence_start`,
  `is_sentence_end`) knows biomedical abbreviations, decimals, "et al." and
  structured-abstract labels. `CitationFinderAgent._check_response` rejects
  spans that aren't complete sentences with `REJECT_INCOMPLETE_SENTENCE`
  (retried like other validation failures), and only appends closing
  punctuation the model omitted. The prompt now demands complete sentences.
  On 500 random PubMed abstracts it accepted 0 of 6,768 fragments and
  rejected 0.6% of naive sentences, mostly correctly (first version of the
  rules; not re-measured after the review changes below). Docs:
  `doc/llm/sentence_bounds.md`, `citation_system.md`, `citation_guide.md`.
  Candidate for upstreaming to bmlib.
- **PR #298 review fixes** (2026-10-18, PR #299, merged):
  - *Sentence rules*: only `.`/`!`/`?` end a sentence (no line-break or
    end-of-text ends); a single line break starts one only after a sentence
    end or a heading/label line; initials ("J.", "U.S.") and more
    abbreviations are not ends; "ET AL." in any case; gene/molecule names
    ("p53", "mRNA", "β-…") may start a sentence; label-only and one-word
    spans are rejected; borrowed closing marks must balance.
  - *Citation agent*: connection failures retried with backoff;
    `errored_documents` stat; retry prompt names the rejection reason;
    batch summary broken down by reason.
  - *Fact-checker*: no citations with any errored **or rejected** document
    is now a `STAGE_CITATIONS` failure (it was stored as "insufficient
    evidence"); recoverable failures retried with exponential backoff
    (`utils/transient_retry.py`, `doc/developers/transient_retry.md`);
    partial failures stored as `degradation_notes` (**migration 034**,
    nullable JSONB on `factcheck.ai_evaluations`; SQLite packages, JSON
    export and review GUI show them); citation stances validated, not
    coerced to neutral; `FactCheckStage` StrEnum, picklable
    `FactCheckStageError`; `FactCheckResult` validates verdict/error shape,
    `FactCheckResult.failed()`; storage refuses error results; JSON import
    skips `"error"` evaluations; `max_citations` validated; malformed batch
    items fail alone; session `failed` when nothing was stored.
  - *search_hybrid*: per-strategy retry (`search_strategy.retry`), partial
    rows of a failed strategy discarded, fulltext fallback only when nothing
    is enabled (`fallback_used`). Behaviour change for every caller: when
    the enabled strategies all fail, the result is now empty instead of a
    silent fulltext search. `QueryAgent.find_abstracts` logs a warning and
    fires a `search_strategies_failed` callback, but the Qt research tab,
    search tab and systematic review do not show it yet (follow-up).
  - *CLI*: failed statements listed with their stage; real stored count;
    failed `-o` export or session write exits 1; partial-evidence verdicts
    flagged.
  - Not done (pre-existing, outside this PR): `DocumentScoringAgent`'s regex
    score fallback for invalid JSON, HyDE logged as enabled but never run in
    `search_hybrid`, a failed thesaurus expansion not recorded in metadata.
- **76 fallback fact-check verdicts deleted from `knowledgebase`**
  (2026-10-17, owner-approved, #296): their evidence rows went with them via
  cascade; CSV backup in
  `~/.bmlibrarian/backups/factcheck_fallback_verdicts_2026-10-17/`. The 76
  statements are unevaluated again (`--incremental` re-checks them); the
  root cause is fixed (see above).
- **Fact-checker no longer records failures as `maybe`** (2026-10-17, branch
  `fix/factchecker-infra-failures`, closes #273): each stage of
  `FactCheckerAgent.check_statement` now raises `FactCheckStageError`
  (`stage`, `detail`) instead of returning an "Insufficient evidence" maybe
  when it could not look. That covers search errors, scoring or citation
  stages that came up empty while some documents failed, LLM/JSON failures,
  and invalid verdicts (re-requested, never coerced). `_fallback_evaluation`
  is gone. `check_batch` returns `EVALUATION_ERROR` results
  (`result.is_error`), counts `check_failures`, **does not store them** (so
  `--incremental` retries them), and notes them in the session's
  `error_message`. The CLI exits 1 on check or storage failures. The
  `CitationFinderAgent` `errors` stat now also counts connection/LLM/JSON
  failures. `search_hybrid` swallows per-strategy errors, so its metadata
  now carries `strategies_failed` (`{'strategy', 'error'}`); an empty search
  with failed strategies is a stage error. Other `search_hybrid` callers
  (research tab, systematic review, search tab) could use the same signal
  but do not yet. Also fixed: the CLI summary crashed on zero results. Docs:
  `doc/developers/fact_checker_system.md` "Failure handling". **Follow-up
  #296**: 76 of 1,000 production verdicts were such fallbacks (all with 17–50
  citations, so evaluation probably fails on large evidence sets); they were
  deleted (see above); root cause fixed (see above).
- **bmlib 0.10 adopted** (2026-10-17, PR #295, merged): pin
  `bmlib[ollama,pdf]>=0.10.0,<0.11.0`; `json_repair`, `agents/text_chunking`
  (`boundary_aware=False`), `paper_reviewer/text_utils` and
  `importers/pdf_converter` are re-export shims over bmlib. Plan and next
  steps: `doc/planning/bmlib_alignment_2026-09.md` (*Progress* table).
- **Legacy orchestrator `Workflow` fixed** (2026-10-17, branch
  `fix/orchestrator-workflow-wedge`): `AgentOrchestrator.execute_workflow`
  looped forever when a step failed (its dependents never became ready),
  and resubmitted every in-flight step on each poll. Now a failed, cancelled
  or vanished task fails its step and transitively skips its dependents
  (`Workflow.skipped_steps`, `workflow_step_skipped` event); unknown
  dependencies, cycles and unregistered agent types raise `ValueError`
  before submitting; each execution resets state, and a concurrent second
  run of the same workflow raises `RuntimeError`; optional `timeout` raises
  `WorkflowTimeoutError` (unfinished steps, partial results, steps still
  running); a timeout or queue error cancels the run's pending tasks
  (`QueueManager.cancel_task`) and no new ones are submitted after the
  deadline. `register_agent` after `start_processing()` now starts that
  agent's thread (it used to hang the workflow silently).
  `workflow_completed` carries `success`. The `mark_*` methods reject
  unknown/finished steps. Follow-ups: ROADMAP §5 "Orchestrator `Workflow`:
  one state map and a per-run result"; queue-worker robustness →
  issue #294.
  No app calls it (the CLI/Qt use `cli/workflow_steps.py`); kept because it
  is exported and documented. Tests: `tests/test_orchestrator_workflow.py`.
  The other half of that "Next up" item, ClinicalTrials matching
  (per-trial unindexed `LIKE` over all full texts), turned out structural →
  ROADMAP §5 "Indexed ClinicalTrials.gov ↔ document matching"; the limit is
  documented in the module docstring and `doc/users/clinicaltrials_import_guide.md`.
- **Citation passage matching rewritten** (2026-10-16, PR #288, merged): `CitationFinderAgent` validated LLM
  passages with a sliding-window `SequenceMatcher` (31 s on one 1 kB
  abstract, × retries × every document). It now calls the pure
  `utils/passage_match.find_passage()`: an exact match on normalised text,
  then seed voting plus word-boundary refinement around a `SequenceMatcher`
  alignment. A sentence-length fuzzy quote takes a few ms, a 1 kB quote
  about 0.1 s, 2 kB up to ~2 s. A seeded test compares it with exhaustive
  search (`test_matches_exhaustive_search_on_random_edits`); ad-hoc runs of
  1,600 edits, a third on repetitive text, found no misses and no wrong
  spans. Rejections now carry a `reason`, and unexpected errors are logged
  with a traceback and counted. Review follow-ups: #289 (short or mid-word
  exact matches), #290 (retry prompt feedback), #291 (Unicode folding),
  #292 (show rejection counts in Qt/CLI). Also fixed: the matched span drifted one character per preceding
  word, whole extra sentences were appended to fuzzy matches, and a
  non-string `relevant_passage` aborted extraction without a retry. The
  4 stale `test_citation_agent.py` tests (mocking the removed ollama dict
  API) are fixed, and 2 tests that only passed because the connection was
  missing now drive `patch_llm`. Docs: `doc/developers/citation_system.md`
  "Passage Validation", `doc/llm/passage_match.md`.
- **Systematic-review resume rebuilt on one shared pipeline** (2026-10-16,
  PR #284, merged): the review phases after search
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

## Next up

The 2026-07-19 review's imminent P1 items are done or deferred to
ROADMAP. Candidates, in rough order of
value — pick one, or pull an item from ROADMAP.md:

- Re-run `fact_checker_cli.py --incremental` on `knowledgebase` for the 76
  statements of #296 (needs the owner's go-ahead: production write).
- Citation follow-ups: #290 (retry prompt should say *why* the last passage
  was rejected, now including "not a complete sentence"), #291 (Unicode
  folding), #292 (rejection counts in Qt/CLI).
- Open bugs from recent slices: #279 / #278 (Find PDF / FETCH
  paths), #285–#287 (systematic review follow-ups), #274 / #275 (the same
  "failure looks like no result" pattern in TransparencyAgent and
  `paper_weight/db.py`).
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

### Verify

- The suite has a **large pre-existing failure baseline**, not "two". Measured
  2026-10-16 with DB/Ollama/GUI-free markers deselected
  (`.venv/bin/python -m pytest tests/ -m "not integration and not
  requires_database and not requires_ollama and not slow"
  --continue-on-collection-errors -p no:cacheprovider --no-cov`): master
  after PR #284 **156 failed, 3598 passed, 19 errors**;
  `perf/citation-fuzzy-match` **152 failed + 19 errors, 3629 passed**
  (the 4 stale `test_citation_agent.py` tests fixed; 0 regressions). After
  the PR #288 review fixes (2026-10-17, `pytest tests/ --no-cov`):
  **160 failed + 19 errors, 3713 passed**; the same 179 nodes fail when run
  against the branch's previous code, so the 8 extra failures are
  environment drift, not regressions. An unfiltered run
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
  search_coordinator`, `paper_weight*`, `reporting_agent`,
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
