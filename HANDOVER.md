# HANDOVER

Working notes for picking up in-flight work. Each section is one
self-contained slice: what's known, where to start, and how to verify.
Remove a section once its slice has landed; add a new section when handing
off new work. Longer-term structural items live in
[ROADMAP.md](ROADMAP.md) — pull one in here once you're about to start it.

---

## Recently landed (context)

- **Archive-extraction path-traversal hardening** (2026-07-23, PR #259): the
  "zip/tar slip" P1 from the 2026-07-19 review. Factored the existing
  `_is_safe_zip_member` guard into one shared pure function
  `utils/path_utils.py::is_safe_archive_member(member_name)` (rejects absolute
  paths and any `..` component; normalizes `\`→`/` so Windows-style traversal
  is caught on POSIX — the *old* inline guard did **not**, which is partly why
  the europe tests were red). Wired it into all three archive extractors:
  `europe_pmc_pdf_downloader._is_safe_zip_member` now delegates (no behavior
  change); `pmc_bulk_importer._extract_package` validates each tar member and
  adds `filter='data'` (defence-in-depth + silences the 3.14 deprecation);
  `medrxiv_meca_importer.extract_package` replaced a blanket `zf.extractall()`
  with a validated member-by-member loop. Also **fixed 7 pre-existing red
  tests** in `test_europe_pmc_pdf_downloader.py` — they targeted a removed
  tar-based API (`_is_safe_tar_member`, tar.gz packages) when the real format
  is `PMC#######.zip`; rewrote them against the actual zip path. New hermetic
  tests: `test_path_utils.py` (the pure guard) + `test_importer_extraction_
  security.py` (both importers, real malicious archives). No new ruff/mypy
  (removed 2 stale F401s in the test file while there). Assistant guidance:
  `doc/llm/archive_extraction_safety.md`.
- **Dependabot cleanup: drop unused marker-pdf/chromadb/fastembed, major dep
  bumps** (2026-07-22, PR #256): resolves 23/24 alerts. Removed three direct
  deps that were imported nowhere in this repo (`chromadb`/`fastembed` were
  BMLibrarian Lite strays; `marker-pdf` only fed one converter option in
  `scripts/pdflab.py`, now stripped). This unblocked `pillow` 10→**12.3.0** and
  `transformers` 4→**5.14.1** (both now purely transitive — no direct
  `import transformers`/`PIL` anywhere), plus `pymupdf` 1.28.0 / `fonttools`
  4.63.0. **transformers 5.x validated at runtime**, not just at import: loaded
  `Snowflake/snowflake-arctic-embed-l-v2.0` through `SentenceTransformerEmbedder`
  (`embeddings/sentence_transformer_embedder.py`) and confirmed 1024-dim single
  + batch embeddings — this is the only real consumer of `sentence-transformers`
  (an opt-in, non-default embedding backend). Also collapsed a pre-existing
  duplicate `pymupdf-layout` dep (kept `>=1.26.6`). Remaining alert: `diskcache`
  (transitive via `llama-cpp-python`, no upstream patch yet). Change is
  metadata-only (pyproject + uv.lock); all 3218 tests collect.
  - **Heads-up — two pre-existing broken test groups surfaced during
    verification** (NOT caused by this PR; both patch attributes removed by
    earlier refactors): `tests/paperchecker/test_search_coordinator.py::`
    `TestEmbeddingGeneration` (×3) patches `search_coordinator.ollama.embeddings`
    — `ollama` was removed from that module by the PR #249 LLM-layer migration;
    `tests/test_paper_weight_persistence.py::TestLLMJSONParsing` (×5 errors) mocks
    `PaperWeightAssessmentAgent._get_db_connection`, removed by the paper_weight
    package reorg. Both need their mock targets updated to the LLM-layer APIs.
- **Injection-surface hardening: shared conninfo helper + bound LIMIT/OFFSET**
  (2026-07-22): two top P1 findings from the 2026-07-19 review. New pure module
  `db_conninfo.py` exposes `build_conninfo(**params)` (delegates to
  `psycopg.conninfo.make_conninfo` — quotes/escapes every value, drops
  `None`/empty; no import-time side effects so GUI login code can use it before
  a `DatabaseManager` exists). All **six** hand-concatenated connection strings
  now route through it: `database.py` `_init_pool`, `gui/qt/core/application.py`
  auto-login, `login_dialog.py` ×2 (`_on_test_connection` + `_get_db_connection`
  — the review said ×3, missed the second login_dialog site), plus two more the
  PR-255 review caught (`paperchecker/database.py` `_create_connection` and
  `migrate_config_to_db.py` `get_db_connection`) — `build_conninfo` is now the
  single sanctioned way to build a libpq string.
  `find_abstracts` no longer f-string-interpolates `max_rows`/`offset`;
  it uses the pure `build_pagination_clause()` helper returning `%s`
  placeholders + bound params (matches sibling `find_abstract_ids`). 11 new
  hermetic unit tests in `tests/test_db_conninfo.py` (escaping, injection
  attempt, None-dropping, pagination branches). No new ruff/mypy errors
  (the `query_params: List[Any]` annotation actually cleared 2 pre-existing
  mypy errors). Assistant guidance: `doc/llm/db_conninfo.md`.
- **LLM-layer polish: BaseAgent per-call overrides + 2 migrations**
  (2026-07-22): `base.py` `_make_llm_request`/`_generate_from_prompt` now take
  optional `model`/`temperature`/`top_p` overrides (default `None` → `self.*`,
  so existing calls are byte-for-byte unchanged), and `_make_llm_request`
  forwards a `think` option to the chat client instead of dropping it. On top
  of that, `PDFMatcher` and `SemanticQueryAgent` were migrated off
  hand-constructed `LLMClient`s onto `BaseAgent` — `PDFMatcher` now activates
  its previously-dead `FALLBACK_MODEL`; `SemanticQueryAgent`'s keyword
  expansion uses the new per-call temperature override. The `import ollama`
  boundary was already clean (PR #249); this was consistency polish, not a
  correctness fix. Design spec:
  `docs/superpowers/specs/2026-07-22-baseagent-percall-overrides-design.md`.
  Review follow-up: the four LLM error-path log records in `base.py` now
  report `effective_model` (they still reported `self.model`, mislabelling
  failures that used a per-call model override).
- **Connection/concurrency P1 fixes** (2026-07-21): six findings from the
  2026-07-19 review. `queue_manager.py` — dequeue is now a single atomic
  `UPDATE … WHERE id = (SELECT … LIMIT 1) RETURNING *` (no cross-process
  double-claim); construction now guards `sqlite3.sqlite_version >= 3.35.0`
  (RETURNING) and file-based queue DBs run WAL + a 30 s `busy_timeout` so
  concurrent claims block-and-retry instead of raising "database is locked".
  The SIGINT/SIGTERM handler no longer takes the
  non-reentrant lock, and handlers register only on the main thread (fixes
  off-main-thread `ValueError`). `thesaurus/expander.py` routes through the
  shared `get_db_manager()` instead of leaking a fresh pool per term.
  `pubmed_bulk_importer._store_article_batch` now stores transparency
  metadata on a fresh connection (passing `None` instead of the returned-to-
  pool `conn`), and the metadata method's own-connection path was fixed to
  return the pooled connection instead of leaking it; `pdf_matcher`'s
  long-lived `PDFManager` no
  longer retains a returned-to-pool connection (it only needs `base_dir`).
  `database.py` source-ID caches are now keyed per-conninfo so a second
  manager against a different DB can't reuse the first's IDs. The GUI
  raw-connection item was deferred to ROADMAP §5 (structural; acute risk
  already mitigated).
- **LLM-layer consolidation** (through PR #249): the LLM abstraction is now
  fully delegated to `bmlib.llm` (pinned `bmlib[ollama]>=0.5.1,<0.6.0` in
  `pyproject.toml`). Every remaining raw `ollama` call site was routed
  through the LLM layer (#249); `tests/test_llm_layer_boundary.py` enforces
  the boundary with a shrinking allowlist. A test that queried the
  production DB was repaired (#247).
- **Test-suite hang fixes** (2026-07-20): three blockers that made
  `pytest tests/` never complete are fixed — a Playwright script marked
  `integration`, a production-DB query marked `requires_database`, and a Qt
  modal stubbed via autouse fixture. `pytest-timeout` (120s) added in
  `pyproject.toml`. Gotcha: the signal timeout does NOT interrupt a Qt
  modal. ~6 pre-existing "'bmlibrarian' is not a package" collection errors
  still abort a plain run unless `--continue-on-collection-errors` is
  passed; still no CI workflow.
- **Whole-project code review, P0 fixes** (2026-07-19, PR #229): broken CLI
  login, settings-category drift, non-functional PMC bulk import, PDF
  magic-byte validation, per-record `SAVEPOINT` semantics, `bmlibrarian.cli`
  name-collision fix, deprecated Flet paper-checker lab removed. Follow-ups
  in 75aba14 (atomic downloads, validated browser fallback, honest stats).
  Remaining P1/P2 findings in `doc/TODO_code_review_2026-07.md` and
  [ROADMAP.md](ROADMAP.md).
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

- **f-string source_id filters** — `database.py`
  `search_with_bm25`/`search_with_fulltext_function` still interpolate
  `source_id = {id}` / `ANY(ARRAY{others})`. Not injectable today (IDs are
  DB-sourced ints), but the same class as the now-fixed LIMIT/OFFSET item —
  bind them (or build an array param) for consistency.
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
  `doc/users/queue_system_guide.md`); ClinicalTrials matching does
  a per-trial leading-wildcard `LIKE` over full text — needs an indexed
  strategy at scale.

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
  2026-07-21 on `master`+this branch with DB/Ollama/GUI-free markers
  deselected (`.venv/bin/python -m pytest tests/ -m "not integration and not
  requires_database and not requires_ollama and not slow"
  --continue-on-collection-errors`): **178 failed, 2885 passed, 43 errors**.
  Do NOT eyeball the count — it's meaningless against that baseline. To check
  for regressions, capture the failing node-ID set (`grep -E '^(FAILED|ERROR)
  tests/'`), `git stash`, re-run, and `diff` the two sets: the gate is **zero
  nodes failing in your tree that pass on `master`**. (This is why ROADMAP §2
  "make the test suite protect you" matters — there is no CI and the baseline
  is badly broken.) Pre-existing clusters: `prisma2020_lab`, `paperchecker/
  search_coordinator`, `paper_weight*`, `reporting_agent`, `citation_agent`,
  `fact_checker_agent`, `qt_*`, `ollama_migration`, `openathens_auth`,
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
  database — use `bmlibrarian_dev` (see CLAUDE.md "Database Safety").
