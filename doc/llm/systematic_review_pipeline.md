# Systematic review: one pipeline for fresh runs and resumes

- Review phases after search planning exist **once**, in
  `agents/systematic_review/pipeline.py`. `run_review()` and
  `run_review_from_checkpoint()` both call `_execute_pipeline(start, options)`
  with a different `ReviewStage`. Never add phase logic to `resume_mixin.py`
  or `agent.py`; a copied resume path drifted badly before (re-scoring,
  ignored phased search and quality gate, silent empty results).
- Stages after search read evaluations back from the evaluation store and
  skip documents already evaluated in the run. Keep it that way: it is what
  makes resume cheap and correct.
- Never save a failed evaluation (it would be reused as real by every
  resume), and never let a save failure pass silently (the paper would
  vanish): batch scorers raise `EvaluationSaveError`. Papers without a saved
  evaluation are flagged *uncertain* in the report.
- A resume that cannot restore its papers or evaluation run must raise
  (`ResumeError` / `ValueError`), not continue with nothing, and must do so
  before replacing agent state (`parse_checkpoint` → fetch/find → apply).
- A rejected checkpoint returns a result with `abort_reason` set; callers
  must check `result.aborted` instead of treating it as an empty review.
- Problems the review continues despite go through `_warn()`
  (`EVENT_REVIEW_WARNING`), never only to the log.
- `RESUME_STAGE_BY_CHECKPOINT` is the only list of the checkpoint order.
- New agent state must be declared on `ReviewHost` (pipeline.py), set in
  `SystematicReviewAgent.__init__`, reset in `run_review()` and `reset()`,
  saved in `_save_checkpoint_file()`, and parsed in `parse_checkpoint()` /
  applied in `_apply_checkpoint()` (resume_mixin.py). The evaluation run is
  the exception: `run_review()` replaces it via `_start_evaluation_run()`,
  a resume via `_attach_evaluation_run()`.
- Developer doc: `doc/developers/systematic_review_pipeline.md`.
