# Systematic Review Pipeline and Checkpoint Resume

`SystematicReviewAgent` (`src/bmlibrarian/agents/systematic_review/`) runs a
review in two entry points that share one implementation of the review
phases:

| Entry point | Module | Does |
|---|---|---|
| `run_review()` | `agent.py` | Validates input, starts an evaluation run, plans the search, passes the *search strategy* checkpoint, then enters the pipeline at its first stage |
| `run_review_from_checkpoint()` | `resume_mixin.py` | Loads and validates a checkpoint file, restores state and the evaluation run, then enters the pipeline at the stage after the checkpoint |

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
            ReviewHost                           # annotations only
```

`ReviewHost` declares the agent state and methods the mixins use, for the
type checker; it defines nothing at runtime except the `_active_criteria()`
and `_active_weights()` accessors, which raise `SystematicReviewError` when
no review is in progress.

## Stages

```
ReviewStage.EXECUTE_SEARCH  ──► checkpoint initial_results
ReviewStage.SCORE_RELEVANCE ──► checkpoint scoring_complete      (initial filter + scoring + threshold + query feedback)
ReviewStage.ASSESS_QUALITY  ──► checkpoint quality_assessment
ReviewStage.FINALIZE                                             (rank, quality gate, synthesis, report)
```

`RESUME_STAGE_BY_CHECKPOINT` maps a checkpoint type to the stage a resume
starts at (a checkpoint is written after its phase finished). Initial
filtering is deterministic and cheap, so it is re-run rather than
checkpointed.

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
its threshold overrides in resume mode), so no stage may assume the
threshold the earlier stages used.

Workers (`SearchExecutor`, `InitialFilter`, `RelevanceScorer`,
`QualityAssessor`, `CompositeScorer`, `Reporter`) are built by
`_build_pipeline_components()`; tests replace that method to inject fakes.

## Run outcome and evaluation-run status

`_run_guarded(body)` wraps both entry points:

| Outcome | Evaluation run | Caller sees |
|---|---|---|
| Success | `completed` | the result |
| Checkpoint rejected (`ReviewAborted`) | `paused` | an empty result with the abort reason |
| `KeyboardInterrupt` | `paused` | the interrupt |
| Any error | `failed` (with message) | a `SystematicReviewError` subclass (`DatabaseConnectionError` for `ConnectionError`, `LLMConnectionError` for `TimeoutError`) |

Status updates that themselves fail are logged and never mask the review's
own outcome.

## Resume

1. `load_checkpoint_file()` validates the file (JSON object, known
   `checkpoint_type`, not a final report).
2. `_restore_state_from_checkpoint()` replaces *all* review state — nothing
   from a previous review on the same agent instance survives. Document IDs
   are validated (`parse_document_ids`), papers are re-fetched in one batch,
   and search provenance (`_paper_sources`) and the phased-search baseline
   (`_semantic_baseline_ids`) are rebuilt from the executed queries with the
   pure helpers `build_paper_sources()` / `collect_phase1_document_ids()` in
   `executor.py`, so the checkpoint format did not change.
3. `_restore_evaluation_run()` reattaches the run:
   - run ID present and found, same research question → `reopen_run()`
     (back to `in_progress` whatever its status, completion time and error
     cleared);
   - run ID present but not found, or another question → `ResumeError`;
   - no run ID → `ResumeError` if the resume starts at `ASSESS_QUALITY` or
     `FINALIZE` (`STAGES_REQUIRING_SAVED_EVALUATIONS`), otherwise a new run
     is started.

## Tests

`tests/test_systematic_review_pipeline.py` drives the real agent with an
in-memory `FakeEvaluationStore` and fake workers, and resumes from
checkpoint files the agent wrote itself. It pins cache reuse, phased-search
resume, the quality gate on every path, run statuses, the loud-failure
cases, and the pure helpers.
