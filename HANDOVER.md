# HANDOVER

Working notes for picking up in-flight work. Each section is one
self-contained slice: what's known, where to start, and how to verify.
Remove a section once its slice has landed; add a new section when handing
off new work. Longer-term structural items live in
[ROADMAP.md](ROADMAP.md) — pull one in here once you're about to start it.

---

## Recently landed (context)

- **Lab cleanup, transparency batches, research-tab settings** (2026-10-30,
  closes #331, #370, #330). The PICO, Study Assessment and PRISMA labs'
  `cleanup()` calls `orchestrator.stop_processing()` (PICO/Study called a
  nonexistent `shutdown()`, PRISMA called nothing; the GUI never starts
  orchestrator processing, so this is hygiene). `TransparencyAgent.assess_batch`
  checks the LLM connection once per batch (was 2 requests per document);
  if it fails, every document is recorded as failed with that reason
  (stats += N). Research tab: a settings change marks the agents stale and
  the **next Start** rebuilds them via `AgentFactory.create_all_agents`
  (keeping the main window's `_audit_conn`/`_db_manager`) and replaces the
  workflow executor (it used to rebuild agents inline without audit tracking
  and keep running the old executor); a failed rebuild aborts that start
  with the error and is retried next time (only the research tab uses the
  main window's agents). Tests: `tests/test_lab_tab_cleanup.py`,
  `tests/test_qt_research_tab.py`, `tests/test_transparency_agent.py`.
- **TransparencyAgent failures are surfaced** (2026-10-30, closes #274).
  `assess_transparency` raises `TransparencyAssessmentError` (reason in the
  message: no Ollama, no text, unparseable/invalid LLM reply, request
  failure) instead of returning `None`; `assess_batch` returns
  `TransparencyBatchResult(assessments, failures=[(doc_id, reason)])`;
  `total_assessments` counts every attempt (body moved to
  `_assess_document`). `TransparencyAssessment.low_confidence` is set below
  `min_confidence` (summary shows "LOW CONFIDENCE"; not a DB column).
  Unrated `funding_disclosure_quality` / `coi_disclosure_quality` /
  `industry_funding_confidence` are `None` ("not assessed", NULL in the DB;
  CLI reloads no longer turn NULL into 0.0; older rows hold 0.0). CLI
  `assess` prints "FAILED: N of M" plus each reason and exits 1; the lab
  shows the reason. Also fixed: `enrich_with_metadata` and the lab's
  document loader imported a nonexistent `bmlibrarian.database.get_db_connection`,
  so **every CLI `assess` crashed after the batch, before saving**, and
  the lab could not load any document; both use
  `get_db_manager().get_connection()` now. Review follow-ups: an enrichment
  DB error raises (was debug, "table may not exist"; migration 029 creates
  it) and the CLI skips saving that document, since its upsert would reset
  a stored `is_retracted`; non-`TransparencyAssessmentError` exceptions
  (LLM timeouts etc.) are wrapped into it; a failed save rolls back, is
  listed as "NOT SAVED" and exits 1; `export` now reads
  `industry_funding_confidence` (was never selected); `show`/`export`
  rebuild `low_confidence`; JSON export lists failures. Tests:
  `tests/test_transparency_agent.py`, `tests/test_transparency_analyzer_cli.py`,
  `tests/test_transparency_lab_worker.py`.
- **Paper-weight sub-agent reads the review's database** (2026-10-30,
  closes #366). `PaperWeightAssessmentAgent(db_manager=)` (from
  `QualityAssessor`) reaches every DB step of `assess_paper`/
  `assess_full_paper`: `get_cached_assessment`, `store_assessment`,
  `get_document`, `check_replication_status`, `search_chunks_by_query`,
  `get_all_document_chunks`, the two `validate_*_extraction`s, both
  `extract_*_llm`s, `ensure_document_embeddings`, `_search_document_chunks`,
  and new optional
  `db_manager` on `ChunkEmbedder` and `PDFIngestor` (None → global, so the
  lab is unchanged). PRISMA needs nothing (the review calls only
  `assess_prisma_compliance` on the document dict). The remaining helpers in
  `paper_weight/db.py` (`search_documents`, `semantic_search_documents`,
  `get_recent_assessments`, …), used by the Paper Weight Lab and the citation
  editor, still use the global manager. Review follow-ups: `assess_full_paper`
  raises when ingestion stores no full text (it used to score and cache the
  abstract); `ChunkEmbedder.chunk_and_embed` inserts each chunk in its own
  savepoint (one failed INSERT used to abort the transaction and lose every
  chunk at COMMIT while still counting them); the dead, uncallable
  `SystematicReviewAgent._get_paper_weight_agent` was removed. Docs: `systematic_review_pipeline.md`.
  Tests: `tests/test_paper_weight_db_manager.py`.
- **Systematic review reads the agent's database** (2026-10-29, closes
  #285). `find_abstracts`, `fetch_documents_by_ids`, `search_with_semantic`,
  `search_with_bm25`, `search_with_fulltext_function`, `search_hybrid`,
  `search_by_embedding` and `hyde_search` take an optional `db_manager`
  (None → global `get_db_manager()`; source ids are resolved through the
  same manager). `SearchExecutor` (all query types incl. HyDE), the resume
  path's `_fetch_papers` and `QualityAssessor`'s `ResultsCacheManager` pass
  the agent's manager; the paper-weight sub-agent too since #366 (entry
  above). Tests:
  `tests/test_systematic_review_db_manager.py` (global manager made to
  fail); the pipeline test's fetch fake asserts it gets a manager.
- **Evaluation-run lifecycle tested against real SQL** (2026-10-29, closes
  #287). `tests/test_evaluation_run_lifecycle_db.py` (opt-in,
  `BMLIBRARIAN_TEST_DB_ENV`) walks a run failed → `reopen_run` → paused →
  resumed → completed, checking `get_run` each step, and checks that
  `save_evaluation` overwrites the same run/document/type. #286 (pre-#284
  failure placeholders in saved runs) closed as moot: a read-only check found
  none in `knowledgebase` or `bmlibrarian_dev`.
- **PMID parity: PostgreSQL fact-checker and paper reviewer** (2026-10-29,
  closes #363, #361). `PostgreSQLFactCheckerDB.get_document_metadata` joins
  `sources` and uses `extract_pmid` (was `pmid_select_expr`), matching the
  SQLite backend. `DocumentResolver.import_document` stores a PMID-only
  paper as `PMID:<digits>` under the `paper_reviewer` source; its duplicate
  check also matches bare-digit rows from before (`knowledgebase` has one
  `paper_reviewer` row, none bare-digit, so no migration). Its local PMID
  lookup is an indexed exact match on `<digits>` / `PMID:<digits>`, kept
  only where `extract_pmid` agrees (the old `LIKE '%pmid:…%'` scanned the
  whole table, missed `PMID:` and matched `pmid:1234` for `123`; no
  `knowledgebase` row embeds a marker in a longer id). `_db_row_to_doc`
  derives its PMID with `extract_pmid` too.
  Tests: `tests/test_paper_reviewer_resolver_pmid.py`,
  `test_pubmed_source_id_sites.py`.
- **Review packages carry source names** (2026-10-29, closes #280).
  `export_review_package.py` joins `sources` and stores `sources.name` in the
  package's new `documents.source_name` column (`sqlite_schema.sql`);
  `SQLiteFactCheckerDB.get_document_details` / `get_document_metadata` derive
  the PMID with `extract_pmid(external_id, source_name)` (metadata also honours
  `PMID:` markers now) and `get_document_details` returns `source_name`.
  Packages exported before this have no column and keep the old guess
  (`PUBMED_SOURCE_ID = 1`, logged on open). Docs:
  `document_fetching_system.md` "PMID Extraction". Tests:
  `tests/test_citation_document_details.py`. Side note split out as #361
  (paper reviewer stores a bare PMID as `external_id`).
- **PMID lookups use the database's PubMed source id** (2026-10-28, closes
  #344). `pmid_select_expr()` and `pubmed_source_id(db_manager)` moved from
  `agents/paper_weight/db.py` into `bmlibrarian.database` (public; the
  private `_pubmed_source_id` is gone). Used by the citation editor's
  keyword search, `ReferenceBuilder`, the PubMed Search Lab's PMID lookups,
  `DocumentProcessor.get_document_info`, the PostgreSQL fact-checker's
  `get_document_metadata`, and `scripts/find_pdf_mismatches.py` /
  `pdf_verification_gui.py` (their `PUBMED_SOURCE_ID = 1` is gone). The
  systematic-review source filter (`SearchExecutor._filter_results_by_source`)
  classifies by `source_name` only (it also treated ids 1/2 as
  PubMed/medRxiv; a NULL `source_name` no longer crashes it). Review
  packages: entry above (#280). Docs: `document_fetching_system.md` "PMID Extraction".
  Tests: `tests/test_pubmed_source_id_sites.py`. Review follow-ups fixed in
  the same PR: the citation editor's keyword search selected a nonexistent
  `d.journal` (now `d.publication AS journal`; every keyword search had
  failed), and the PubMed Search Lab imported a nonexistent `generate_theme`
  (now `generate_default_theme`; the swallowed ImportError meant it never
  got the theme).
- **Systematic-review rigor and sample size score real study assessments**
  (2026-10-24, closes #356; owner decision this session: rigor = worst rated
  domain). `CompositeScorer._extract_methodological_rigor` now uses the
  worst rated of `StudyAssessment`'s five `*_bias_risk` fields
  (`BIAS_RISK_SCORES` low 8 / moderate 5 / high 2; other ratings skipped,
  unexpected ones logged); `_extract_sample_size_score` parses the
  free-text `sample_size` with `paper_weight/extractors.find_sample_size`
  (thousands separators stripped first, a scorer-side workaround for #358;
  `find_sample_size` itself unchanged; bare number or JSON int accepted;
  N from 1 to 10^9) and scores it in `SAMPLE_SIZE_SCORE_STEPS` (<30: 2,
  <100: 4, <500: 6, <1000: 8, else 10). A count of studies ("N=8 studies",
  18/196 cached assessments in `knowledgebase`) is not scored. Nothing rated
  or parsable → None → left out and rescaled like paper weight (rigor is
  left out for ~60% of cached assessments: all domains "unclear"). Before,
  both read keys `StudyAssessment` never had and were a constant 5.0 (20%
  of default weight). A missing, empty, failed or disabled study assessment
  gives `NEUTRAL_SCORE` for all three study dimensions
  (`data_models.has_study_assessment`). **Rankings of new and resumed
  systematic reviews change again.** Docs: `systematic_review_pipeline.md`
  "Study assessment in the composite score", `systematic_review_guide.md`
  §6. Tests: `test_composite_scorer_weights.py` (built from a real
  `StudyAssessment(...).to_dict()`).
- **Paper weight counts in systematic-review rankings; stale placeholders
  are re-assessed** (2026-10-24, closes #348, #351; owner decisions in this
  session). The scorer reads `final_weight` / `replication_status_score`
  (what `PaperWeightResult.to_dict()` emits), the reporter and results cache
  `final_weight`, via `systematic_review/data_models.paper_weight_score()`
  (clamped 0-10, NaN rejected); before, every paper got a neutral 5.0 for
  both dimensions. A paper with no paper-weight score (missing, disabled, or
  a saved pre-#349 placeholder with every score 0.0:
  `is_paper_weight_placeholder`, warned) has those dimensions **left out and
  the other weights scaled up** (`CompositeScorer.score`); so does a
  replication score of 0.0 (`REPLICATION_NONE_RECORDED_SCORE`: no
  replication on record, the table is hand-filled). No scored weighted
  dimension → `NEUTRAL_SCORE` with a warning. A paper-weight assessment that
  fails in the run still puts the paper in `failed_papers`; an exception
  with an empty message now counts too (`quality.error_message`). `get_cached_assessment`
  treats rows whose audit trail carries a pre-#349 failure marker
  (`paper_weight/db.is_failure_placeholder`) as not cached, so they are
  re-assessed and overwritten; `QualityAssessor` no longer reads
  `results_cache.paper_weight_cache` (a flat dict can't reveal a
  placeholder; `ResultsCacheManager.get_paper_weight` is removed) and passes `force_recompute` on as `force_reassess`. The
  methodology version is now the class attribute
  `PaperWeightAssessmentAgent.VERSION` (still `1.0.0`; no full re-run), read
  by the agent and `QualityAssessor._get_agent_version`; the
  `paper_weight_assessment.version` config key is gone (a saved one is
  ignored with a warning). **Rankings of new
  and resumed systematic reviews change.** Saved evaluation runs from before
  #349 can still hold paper-weight placeholders (`final_weight` 0.0, no
  `error` key; now skipped as above) → #286. Unmarked placeholders in
  `paper_weights.assessments` → #357; scorer's rigor/sample-size dimensions
  were a constant 5.0 (same bug class) → #356, done (entry above). Docs: `systematic_review_pipeline.md` "Paper weight
  in the composite score". Tests: `test_composite_scorer_weights.py`,
  `test_paper_weight_persistence.py::TestPlaceholderCacheRows`,
  `test_systematic_review_quality.py::...::test_paper_weight_comes_from_agent_not_results_cache`.
- **Paper-weight failures raise instead of becoming scores; DB helpers
  raise instead of returning `[]`/`None`** (2026-10-23, closes #345, #347,
  #275). Nothing failed is stored or cached, so a re-run retries; the lab
  shows "Assessment Error" / "Search Failed" / "Could Not Load Document".
  Details in git history; tests in `tests/test_paper_weight_*.py`.
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
  on `bmlibrarian_dev`; auto-applied to `knowledgebase` on 2026-10-23). Writers: `CitationTracker.record_citation`,
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
  docs): sentence bounds stop rejecting real sentences (PR #305,
  `doc/llm/sentence_bounds.md`); citation retries quote the rejected passage
  and passage matching folds Unicode (PR #301, `passage_match.fold_char()`); bmlib 0.10 adopted with re-export shims (PR #295,
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
- #357 (unmarked pre-#349 paper-weight placeholders still served from the
  cache) and #358 (`find_sample_size` misreads "1,234"); both hinge on
  whether to bump `PaperWeightAssessmentAgent.VERSION` (full re-run).
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

- **The full suite is green** since PR #336: `QT_QPA_PLATFORM=offscreen uv
  run python -m pytest tests/ -p no:cacheprovider --no-cov -q` on 2026-10-30
  (#331/#370/#330 branch): **4613 passed, 50 skipped** in 9–17 min. Without
  `offscreen`, `test_annotation_widget.py::...::test_explanation_field_typing`
  can fail when another app holds OS focus (`qWaitForWindowActive`). No `--continue-on-collection-errors` or marker deselection needed;
  any other failure is a regression. Save the
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
