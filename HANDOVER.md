# HANDOVER

Working notes for picking up in-flight work. Each section is one
self-contained slice: what's known, where to start, and how to verify.
Remove a section once its slice has landed; add a new section when handing
off new work. Longer-term structural items live in
[ROADMAP.md](ROADMAP.md) — pull one in here once you're about to start it.

---

## Recently landed (context)

- **Fragments are widened to their complete sentence(s)** (2026-10-20,
  branch `feat/widen-fragment-citations`, closes #304). Owner decision
  (2026-10-19): a verbatim fragment is cited as the abstract's enclosing
  sentence(s) instead of being rejected, and marked: `Citation.widened_from`
  holds the fragment, `get_validation_stats()['widened_passages']` counts
  them, each is logged and the batch summary reports them. No fact-checker
  degradation note (those mean evidence not examined) and no DB column: the
  stored `factcheck.evidence.citation_text` does not say it was widened.
  Still rejected: a fragment that occurs more than once in the abstract, no
  boundary within `MAX_WIDENING_CHARS` (400), a sentence the source broke off.
  Two owner-approved sentence-start rules for damaged source text: one-word
  labels fused onto the next word (`unclear.ObjectiveThis`, #304) and
  lost-text gaps (double space or `( ` before a capitalised word, where
  PubMed dropped a formula). 500-abstract sample: no fragment newly
  accepted; 2,206 of 2,229 comma-cut fragments widen to exactly their
  sentence. Docs: `doc/llm/sentence_bounds.md`, `citation_system.md`
  "Widening fragments". LLM re-run of the 106 #303 pairs: see the PR
  (results were pending when this was written).
- **Sentence bounds stop rejecting real sentences** (2026-10-19, PR #305,
  merged, closes #302, #303): invisible `Cf` characters are whitespace;
  single-capital designators, all-caps tokens before a capital, "et al."
  before a capital, time units and glued text are boundaries (details and
  accepted trade-offs in `doc/llm/sentence_bounds.md`). LLM re-run of the
  106 pairs that lost every passage in the #296 re-run: 64 accepted (were
  0), 31 fragments, 10 below the similarity threshold, 1 irrelevant.
- **Citation retries quote the rejected passage; passage matching folds
  Unicode** (2026-10-18, PR #301, merged, closes #290, #291): `_retry_note`
  quotes the previous passage (≤ 200 chars) and its similarity;
  `passage_match.fold_char()` folds quotes, dashes, NFKD, accents (not
  negation overlays), soft hyphens and zero-width characters.
- **Fact-check evaluation scales its token budget** (2026-10-18, PR #300,
  closes #296): `evaluation_token_budget(max_tokens, n)` = `max_tokens` + 100
  per citation (`gpt-oss:20b` thinks inside `num_predict`);
  `BaseAgent._checked_content` reports "Model hit the max_tokens limit (N)";
  `DocumentScoringAgent` honours `agents.scoring.max_tokens` (default 1000).
  **The 76 deleted fallback verdicts were re-run on `knowledgebase`**
  (owner-approved, ~13 h): all stored (39 maybe, 25 yes, 12 no; 35 match the
  expected answer); 42 carry degradation notes (106 of 1,153 cited documents
  had every passage rejected → the slice above). `~/.bmlibrarian/config.json`
  now uses `gpt-oss:20b` for query/scoring/citation (MedGemma models not
  installed; backup `~/.bmlibrarian/backups/config.json.2026-10-18.bak`). One
  in-progress session row from an aborted attempt remains in
  `factcheck.processing_metadata`.
- **Citation quality policy** (PRs #288, #297–#299, 2026-10-16…18): passages
  are validated by `utils/passage_match.find_passage()` and must be complete
  sentences (`utils/sentence_bounds.py`, `REJECT_INCOMPLETE_SENTENCE`); the
  fact-checker never stores failures as verdicts (`FactCheckStageError`,
  failed results not stored so `--incremental` retries them), stores partial
  failures as `degradation_notes` (**migration 034**), retries transient
  failures (`utils/transient_retry.py`). `search_hybrid` returns empty (not a
  silent fulltext search) when every enabled strategy fails and reports
  `strategies_failed`; the Qt research/search tabs and systematic review do
  not show that yet. Not done: `DocumentScoringAgent`'s regex score fallback
  for invalid JSON, HyDE logged as enabled but never run in `search_hybrid`.
  Docs: `doc/developers/citation_system.md`, `fact_checker_system.md`
  "Failure handling", `doc/llm/sentence_bounds.md`, `doc/llm/passage_match.md`.
- **Earlier October 2026 slices** (details in git history and the linked
  docs): bmlib 0.10 adopted with re-export shims (PR #295,
  `doc/planning/bmlib_alignment_2026-09.md`); legacy orchestrator `Workflow`
  no longer wedges (`tests/test_orchestrator_workflow.py`; follow-ups ROADMAP
  §5, #294); systematic-review resume on one shared pipeline (PR #284,
  `doc/developers/systematic_review_pipeline.md`; follow-ups #285–#287); PMC
  discovery via the PMC Cloud Service + per-host rate limiting (PR #282;
  `pmc_bulk_cli` still broken → #283); Flet GUI retired (PR #277, guarded by
  `tests/test_no_flet.py`; gaps in ROADMAP §1); P1 GUI and backend batches
  (PRs #272, #276; follow-ups #278–#280).
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
- **Known pre-existing red tests** (mock targets removed by refactors, not
  regressions): `tests/paperchecker/test_search_coordinator.py::`
  `TestEmbeddingGeneration`, `tests/test_paper_weight_persistence.py::TestLLMJSONParsing`,
  `test_medrxiv_importer.py::test_initialization_with_custom_pdf_dir`.

## Next up

The 2026-07-19 review's imminent P1 items are done or deferred to
ROADMAP. Candidates, in rough order of
value — pick one, or pull an item from ROADMAP.md:

- Remaining citation rejections: 10 of the 106 #303 pairs are below the
  similarity threshold (long multi-sentence quotes that drift), plus
  whatever the widening re-run leaves (see the PR). Known sentence-bounds
  misses: lost text with a single space (`8.8%) MAE rates`), multi-word
  fused labels.
- #292 — show citation rejection counts in the Qt research tab and CLI
  (and mark widened citations, `Citation.widened_from`).
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
