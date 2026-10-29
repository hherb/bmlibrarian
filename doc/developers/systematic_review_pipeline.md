# Systematic Review Pipeline and Checkpoint Resume

`SystematicReviewAgent` (`src/bmlibrarian/agents/systematic_review/`) runs a
review in two entry points that share one implementation of the review
phases:

| Entry point | Module | Does |
|---|---|---|
| `run_review()` | `agent.py` | Validates input, starts an evaluation run, plans the search, passes the *search strategy* checkpoint, then enters the pipeline at its first stage |
| `run_review_from_checkpoint()` | `resume_mixin.py` | Loads and validates a checkpoint file, fetches its papers and finds its evaluation run, then replaces the agent's state and enters the pipeline at the stage after the checkpoint |

The phases themselves live only in `pipeline.py` (`ReviewPipelineMixin`).
Before October 2026 the resume mixin carried its own copy of the later
phases, which drifted: it re-scored papers that were already scored, always
ran the standard search even with `use_phased_search`, ignored the
quality-gate threshold, mis-counted statistics, never marked runs complete,
and silently returned an empty report when the evaluation run could not be
restored. Keep one implementation.

## Class layout

```
SystematicReviewAgent(CheckpointResumeMixin, BaseAgent)
    CheckpointResumeMixin(ReviewPipelineMixin)   # resume_mixin.py
        ReviewPipelineMixin(ReviewHost)          # pipeline.py
            ReviewHost                           # declarations + shared accessors
```

`ReviewHost` declares the agent state and methods the mixins use, for the
type checker. At runtime it defines only small shared methods:
`_active_criteria()`, `_active_weights()` and `_active_run()` (each raises
`SystematicReviewError` when no review or run is active) and `_warn()`
(see [Warnings](#warnings)).

## Stages

```
ReviewStage.EXECUTE_SEARCH  ──► checkpoint initial_results
ReviewStage.SCORE_RELEVANCE ──► checkpoint scoring_complete      (initial filter + scoring + threshold + query feedback)
ReviewStage.ASSESS_QUALITY  ──► checkpoint quality_assessment
ReviewStage.FINALIZE                                             (rank, quality gate, synthesis, report)
```

`RESUME_STAGE_BY_CHECKPOINT` maps a checkpoint type to the stage a resume
starts at (a checkpoint is written after its phase finished). It is the
single source of the checkpoint order: the CLI's `find_checkpoint_file`
ranks checkpoint files with it, and a test pins that a fresh run passes the
checkpoints in exactly this order. Initial filtering is deterministic and
cheap, so it is re-run rather than checkpointed.

`_execute_pipeline(start, options)` runs every stage `>= start`. Each stage
after search **reads scored and assessed papers back from the evaluation
store**, never from in-memory results of an earlier stage. That is what
makes the stages independent of how the review reached them, and what lets
an interrupted run reuse its saved work:

- `_stage_score_relevance` scores only papers whose document ID has no
  `RELEVANCE_SCORE` evaluation in the run yet;
- `_stage_assess_quality` assesses only above-threshold papers with no
  `QUALITY_ASSESSMENT` evaluation yet;
- `_stage_finalize` re-applies both thresholds to the saved evaluations and
  ranks only assessed papers above the *current* relevance threshold;
- a resume that starts at `FINALIZE` first runs the assessment step without
  its checkpoint, so papers admitted by a relevance threshold lowered since
  the checkpoint are assessed instead of vanishing (a no-op otherwise).

Thresholds can change between a stopped run and its resume (the GUI applies
its threshold fields, the CLI its flags), so no stage may assume the
threshold the earlier stages used. Checkpoint files record the thresholds in
force; the CLI uses them as the resume default.

The post-search workers (`InitialFilter`, `RelevanceScorer`,
`QualityAssessor`, `CompositeScorer`, `Reporter`) are built by
`_build_pipeline_components()` into a frozen `PipelineComponents`; the search
stage builds its own `SearchExecutor` with `_build_search_executor()` (using
the agent's `db_manager`). Tests replace both methods to inject fakes, and
call the real ones in a wiring smoke test.

Every read of the review's own data uses the agent's `db_manager`, never the
global `get_db_manager()`: searches and paper fetches pass it as `db_manager=`
to `find_abstracts`, `search_with_semantic`, `search_hybrid`, `hyde_search`
and `fetch_documents_by_ids` (which default to the global manager when it is
None), and `QualityAssessor` hands it to `ResultsCacheManager`. Before #285 a
review built for one database searched the default `.env`'s. A search that
missed it would be worse than before: its document IDs, which differ between
databases, are fetched from the agent's.

`QualityAssessor` also hands it to `PaperWeightAssessmentAgent(db_manager=)`
(#366), which passes it to every database step of `assess_paper`: the
`paper_weights` cache and store (`get_cached_assessment`, `store_assessment`),
`get_document`, `check_replication_status`, the chunk helpers in
`validators.py`, and `ensure_document_embeddings` → `ChunkEmbedder(db_manager=)`
(`assess_full_paper` also gives it to `PDFIngestor`). Each defaults to the
global manager when it is None, so the Paper Weight Lab is unchanged.
`PRISMA2020Agent` needs nothing: the review calls `assess_prisma_compliance`
with the document dict; only the semantic-search variant reads the database.

## Failed evaluations are never saved

Because later stages read papers back from the store, what is saved decides
what the report contains:

- **A failed evaluation is not saved.** `RelevanceScorer.score_batch` scores
  through `_score_paper_strict` (which raises `ScoringError`), and
  `QualityAssessor.assess_batch` rejects assessments whose required runners
  returned an error placeholder (`assessment_error()`). Both list such papers
  in `failed_papers` and never pass them to the save callback. (The public
  `score_paper()` keeps its never-raise contract and still returns an
  UNCERTAIN zero-score paper.)
- **A save failure stops the review.** A save callback error is raised as
  `EvaluationSaveError` out of the batch, so `_run_guarded` marks the run
  failed — an unsaved evaluation would otherwise drop its paper silently.
- **Papers with no saved evaluation are flagged, not lost.** `_stage_finalize`
  uses the pure `find_unevaluated()` to find papers that passed the filter
  but have no score, and above-threshold papers with no assessment, adds
  them to the *uncertain* list (`flag_unscored()` / `flag_unassessed()`,
  reasons `SCORING_FAILED_REASON` / `ASSESSMENT_FAILED_REASON`) and warns.
  This is derived from the store, so it also covers failures from an earlier
  session of a resumed review. A resume retries them, since nothing was
  saved: scoring failures from a search-strategy or initial-results resume,
  assessment failures from any later resume.

## Study assessment in the composite score

`AssessedPaper.study_assessment` is `StudyAssessment.to_dict()`. Study
quality reads `quality_score`. Methodological rigor is the worst rated of
the five `*_bias_risk` fields (`BIAS_RISK_SCORES`: low 8, moderate 5,
high 2; any other rating, e.g. "unclear", is skipped and an unexpected
one logged). Sample size parses the free-text `sample_size` with the
paper-weight `find_sample_size()` patterns (thousands separators stripped
first; a bare number or JSON integer is accepted; counts from
`SAMPLE_SIZE_MIN_N` 1 to `SAMPLE_SIZE_MAX_N` 10^9) and scores it in
`SAMPLE_SIZE_SCORE_STEPS`. A count of studies (`STUDY_COUNT_PATTERN`:
"N=8 studies", "18 RCTs", as reviews report) is not a participant count
and is not scored. Each of rigor and sample size is None (left out, as
below) when nothing is rated or parsable; before #356 they read keys
`StudyAssessment` never had and were always 5.0. A missing, empty, failed
(`error` key) or disabled (`study_type` `STUDY_NOT_ASSESSED`) study
assessment gives `NEUTRAL_SCORE` for all three (`has_study_assessment()`).
The dimensions left out of a paper's score are logged at debug level.

## Paper weight in the composite score

`AssessedPaper.paper_weight` is `PaperWeightResult.to_dict()` (or a
failed/disabled placeholder). The scorer reads its `final_weight` and
`replication_status_score`, the reporter and results cache its
`final_weight`, all through `data_models.paper_weight_score()`. It clamps to
0-10 and returns None for a missing, failed (`error` key), disabled or
pre-#349 placeholder assessment (every score 0.0 and no `error` key, as saved
evaluation runs from before #349 may hold; `is_paper_weight_placeholder`,
logged as a warning when scored), and for a non-finite value. The scorer also
treats a replication score of 0.0 as no data: `check_replication_status`
gives 0.0 only when `paper_weights.replications` (filled by hand) has no
confirming row (`REPLICATION_NONE_RECORDED_SCORE`).

`CompositeScorer.score` leaves None dimensions out and scales the remaining
weights up to the configured total (#348). That counts the missing
dimensions as the weighted mean of the scored ones, with no pull toward 5.0.
A paper with no score on any weighted dimension gets `NEUTRAL_SCORE` (with a
warning). The inclusion rationale says when a paper was ranked without paper
weight. A paper whose paper-weight assessment *fails* during the run is not
ranked at all: `assessment_error` moves it to `failed_papers`.

`QualityAssessor._run_paper_weight_assessment` writes
`results_cache.paper_weight_cache` but never reads it back: its flat result
dict can't tell placeholder scores (stored before #349) from real ones. The
paper weight agent's own cache (`paper_weights.assessments`, keyed by
`PaperWeightAssessmentAgent.VERSION`) is used instead; `get_cached_assessment`
treats rows whose audit trail carries a failure marker
(`db.is_failure_placeholder`) as not cached, so they are re-assessed and
overwritten (#351). `force_recompute` is passed on as `force_reassess`.
`ResultsCacheManager` has no paper-weight getter. A placeholder without such
a marker (written before #349's scoring fixes under the same version) is
still served: #357.

## Run outcome and evaluation-run status

`_run_guarded(body)` wraps the pipeline part of both entry points. Setup
before it (input validation and starting the run in `run_review`; reading
the checkpoint, fetching papers, finding and reopening the run in a resume)
is not guarded: its errors propagate as they are and touch no run status.

| Outcome | Evaluation run | Caller sees |
|---|---|---|
| Success | `completed` | the result |
| Checkpoint rejected (`ReviewAborted`) | `paused` | an empty result with `aborted == True` and `abort_reason` set |
| `KeyboardInterrupt` | `paused` | the interrupt |
| Any error | `failed` (with message) | a `SystematicReviewError`, or the subclass already raised: `DatabaseConnectionError` for `ConnectionError`, `LLMConnectionError` for `TimeoutError`, plain `SystematicReviewError` for `ValueError` and unexpected errors |

The agent's in-memory `evaluation_run` follows each status change.
A status update that itself fails never masks the review's own outcome, but
it is reported (`_report_run_status_failure`: a warning plus an audit step).
`reset()` marks a run failed only if it is still `in_progress`; completed,
failed and paused runs keep their status.

## Warnings

Problems a review continues despite are reported with `_warn()`: a logged
warning plus a progress callback event `EVENT_REVIEW_WARNING`
(`"review_warning"`), which the Qt tab shows in its activity log. Used for
papers flagged by failed evaluations, checkpoint papers missing from the
database, a checkpoint file that could not be saved, a run status that could
not be recorded, and a resume that has to start a new evaluation run.
Evidence synthesis failures keep their own `synthesis_failed` event.

## Resume

1. `load_checkpoint_file()` checks the file is a JSON object with a known
   `checkpoint_type` (and not a final report).
2. `parse_checkpoint()` (pure) validates every field into a frozen
   `ResumeCheckpoint`: criteria and weights are parsed and validated (any
   malformed part is a `ValueError` naming the field), document IDs and the
   run ID must be integers, the search plan must be present for a
   search-stage resume.
3. Still without touching the agent: papers are fetched in one batch
   (`ResumeError` if none of them exist), rejected papers restored, and
   `_find_evaluation_run()` looks up the run:
   - run ID present and found, same research question → that run;
   - run ID present but not found, or another question → `ResumeError`;
   - no run ID → `ResumeError` if the resume starts at `ASSESS_QUALITY` or
     `FINALIZE` (`STAGES_REQUIRING_SAVED_EVALUATIONS`), otherwise a new run
     will be started (with a warning).
4. `_apply_checkpoint()` replaces all review state and the documenter;
   nothing from a previous review on the same instance survives. Search
   provenance (`_paper_sources`) is rebuilt from the executed queries with
   `build_paper_sources()` (`executor.py`); the phased-search baseline comes
   from the checkpoint's `semantic_baseline_ids` (older checkpoints: derived
   with `collect_phase1_document_ids()` when phased search is configured).
5. `_attach_evaluation_run()` calls `EvaluationStore.reopen_run()` (back to
   `in_progress` whatever its status, completion time and error cleared;
   returns the refreshed run, or None if it vanished → `ResumeError`) or
   starts a new run.
6. Restored progress is reported and the pipeline runs, both inside
   `_run_guarded`.

So a resume rejected for bad or missing data leaves the agent as it was.

## Tests

`tests/test_systematic_review_pipeline.py` drives the real agent with an
in-memory `FakeEvaluationStore` and fake workers, and resumes from
checkpoint files the agent wrote itself. It pins: a resume from every
checkpoint (phased and standard) reports exactly what the uninterrupted run
reports; cache reuse; failed evaluations flagged and retried; save failures
stopping the batch; the quality gate on every path; run statuses, error
mapping, interrupts and `reset()`; chained resumes; malformed checkpoints;
an unchanged agent after a failed resume; the CLI resume (thresholds,
stopped reviews); and the pure helpers. `tests/test_systematic_review_tab_events.py`
covers how the Qt tab shows warnings.
