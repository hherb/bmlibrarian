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
- A resume that cannot restore its evaluation run must raise `ResumeError`,
  not continue with nothing.
- New agent state must be declared on `ReviewHost` (pipeline.py), set in
  `SystematicReviewAgent.__init__`, cleared in `run_review()` and `reset()`,
  and restored (or rebuilt) in `_restore_state_from_checkpoint()`.
- Developer doc: `doc/developers/systematic_review_pipeline.md`.
