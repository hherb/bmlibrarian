# HANDOVER

Working notes for picking up in-flight work. Each section is one
self-contained slice: what's known, where to start, and how to verify.
Remove a section once its slice has landed; add a new section when handing
off new work. Longer-term structural items live in
[ROADMAP.md](ROADMAP.md) — pull one in here once you're about to start it.

---

## Recently landed (context)

- **Fact-checker review GUI shows the cited passage** (2026-10-23, closes
  #338). `CitationListWidget` now renders each evidence row as a
  `widgets/citation_card.CitationCard` (passage highlighted in the abstract,
  `widened_note()` when `widened_from` is set; `fact_checker_tab.py` passes
  it through) with the factory's PDF buttons
  (`_create_pdf_button_for_card`). Pure helper `citation_card_fields()`;
  a placeholder abstract shows the passage on its own. The AI's stance
  (`supports_statement`) and relevance score are shown as badges only while
  the AI column is (`_show_citations`: never in blind mode, re-rendered on
  the Show/Hide Review toggle). Tests in
  `tests/test_citation_widened_storage.py`, `tests/test_fact_checker_tab.py`.
- **`Citation.widened_from` is persisted and shown** (2026-10-23, closes
  #310). **Migration 035** adds nullable `widened_from TEXT` to
  `audit.extracted_citations` and `factcheck.evidence` (applied and re-run
  on `bmlibrarian_dev`; it reaches `knowledgebase` on the app's next
  connection, like 034). Writers: `CitationTracker.record_citation`,
  `EvidenceReference` → `Evidence` → `insert_evidence`; read back by
  `get_evidence_for_evaluation`, fact-checker JSON (`to_dict`
  omits `"widened_from"` when NULL; DB `export_to_json` writes `null`), SQLite review packages
  (`export_review_package.py`; older packages read as NULL) and the CLI
  citation CSV/JSON exports. Marked via `card_utils.widened_note()` on the
  research tab's citation cards and in the audit validation GUI. The
  fact-checker review GUI: see the #338 entry above. Tests:
  `tests/test_citation_widened_storage.py`.
- **Citation rejection counts reach the Qt research tab and CLI**
  (2026-10-22, closes #292). `CitationFinderAgent.extraction_summary()` is
  public; `WorkflowThread._extract_citations_progressive` snapshots
  `failed_citations`/`errors` before its per-document loop and stores the
  summary in `citation_summary_text`; the `citation_summary` signal sets the
  Citations tab's summary label, and the progress line shows it ("⚠️
  Extracted 3 citations from 5 documents (2 rejected: …)" — ✓ only when
  nothing was rejected or failed — or "⚠️ No citations could be extracted:
  …"). A failure in the thread's own per-document code is counted via the
  now-public `record_error()`. The CLI prints the summary after
  extraction and lists rejected passages among the "Possible reasons". Also
  fixed: the CLI's citation progress callback took 2 arguments but the agent
  passes 3 (`current, total, title`), so **every CLI citation extraction
  failed** with "Error in citation extraction" (same bug fixed in
  `examples/citation_demo.py`).
- **Full test suite green** (2026-10-22, PR #336): the 160 failures + 19
  errors were stale tests left by refactors, plus two production fixes
  (`gui/qt/widgets/validators.classify_extraction_error`,
  `writing/models.DocumentMetadata.from_dict` author splitting).
- **Find PDF / PDF download hardening** (2026-10-21/22, PRs #313, #316,
  #318, #321, #324, #326, #328; closes #278, #279, #312, #314, #315, #317,
  #319, #322, #323, #325, #327). One shared verified flow for card
  FETCH/Find and the Paper Weight Lab (`discover_and_download()` →
  `finalize_discovery_result()` → `record_find_pdf_outcome()`); unchecked
  PDFs (verification raised) go to the prompt; RETRY/REJECT exclude that
  source URL on the next search (in memory, per factory); a cancelled
  search deletes its download unless it changed (`file_mtime_ns`). Downloads
  never overwrite: `unused_download_path` reserves `<stem>_<n>.pdf`
  atomically (`O_CREAT | O_EXCL`), empty reservations are discarded.
  DocumentQA links its downloads and stores `full_text` (`FulltextOutcome`).
  The undetected-Chrome fallback downloads into its own
  `.chrome-download-*` temp dir, promotes only a valid PDF, and waits for
  slow downloads (`wait_for_chrome_download`, `download_unfinished`). Docs:
  `pdf_verification_guide.md`, `pdf_verification_system.md`,
  `document_card_factory_system.md`. Open: #320 (doi.org fallback after
  rejecting every source; owner decision).
- **Fragments are widened to their complete sentence(s)** (2026-10-20,
  PRs #306/#311, merged, closes #304). Owner decision
  (2026-10-19): a verbatim fragment is cited as the abstract's enclosing
  sentence(s) instead of being rejected, and marked: `Citation.widened_from`
  holds the fragment, `get_validation_stats()['widened_passages']` counts
  them, each is logged and the batch summary reports them. No fact-checker
  degradation note (those mean evidence not examined) and no DB column: the
  stored `factcheck.evidence.citation_text` does not say it was widened.
  Still rejected: a fragment that occurs more than once in the abstract
  (`REJECT_AMBIGUOUS_FRAGMENT`, counted like the matcher compares:
  `passage_match.occurs_once`), no boundary within `MAX_WIDENING_CHARS`
  (400), a sentence the source broke off. PR #306 review fixes: symbol-led
  sentences ("≥50% of…") no longer widen into the previous sentence, an
  empty span widens to nothing, `widened_from` survives the queue path.
  Two owner-approved sentence-start rules for damaged source text: one-word
  labels fused onto the next word (`unclear.ObjectiveThis`, #304) and
  lost-text gaps (double space or `( ` before a capitalised word, where
  PubMed dropped a formula). 500-abstract sample: no fragment newly
  accepted; 2,206 of 2,229 comma-cut fragments widen to exactly their
  sentence. Docs: `doc/llm/sentence_bounds.md`, `citation_system.md`
  "Widening fragments". LLM re-run of the 106 #303 pairs (`gpt-oss:20b`,
  read-only on `knowledgebase`): **96 accepted** (were 64), 0 fragment
  rejections (were 31), 10 still below the similarity threshold. 6 accepted
  passages contain a sentence broken off by lost text; the owner accepts
  them as they are (#307 closed: rejecting would lose evidence).
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
## Next up

The 2026-07-19 review's imminent P1 items are done or deferred to
ROADMAP. Candidates, in rough order of
value — pick one, or pull an item from ROADMAP.md:

- Remaining citation rejections: 10 of the 106 #303 pairs are below the
  similarity threshold (long multi-sentence quotes that drift). Known sentence-bounds misses: lost text with a single
  space (`8.8%) MAE rates`), multi-word fused labels.
- Widening decisions from the PR #306 review: #308 (widen one-word quotes,
  or require a minimum fragment size?), #309 (fragments still lost at text
  end without a full stop, inside broken-off sentences, past 400 chars).
- #320 — after rejecting every discovered source, the doi.org fallback may
  fetch the same PDF again (owner decision needed: skip fallback, compare
  redirect target, or document).
- Open bugs from recent slices: #285–#287 (systematic review follow-ups), #274 / #275 (the same
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
- #340–#342 (from the PR #339 review; matter only if a migration fails to
  apply): fact-checker stores a verdict without its evidence when an
  evidence insert fails; audit trackers never roll back a failed write;
  a failed auto-migration is only a log warning.

### Verify

- **The full suite is green** since PR #336: `uv run python -m pytest tests/
  -p no:cacheprovider --no-cov -q` on 2026-10-23 (#338 branch): **4421 passed, 47
  skipped, 0 failed** in ~10 min (no `--continue-on-collection-errors` or
  marker deselection needed). Any failure is now a regression. Save the
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
