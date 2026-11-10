//! Runs the setup steps in order, reporting progress and carrying on past
//! failures (skipping only the steps that depend on a failed one).

use std::collections::BTreeSet;
use std::path::PathBuf;

use bml_pgserver::external::ExternalRequest;
use bml_pgserver::init::InitRequest;
use bmlib::publications::fetchers::registry::HttpClient;

use crate::ollama::OllamaHost;
use crate::{steps, StepEvent, StepId, StepOutcome};

/// Every step, in the order they run.
pub const ALL_STEPS: [StepId; 6] = [
    StepId::Hardware,
    StepId::Database,
    StepId::Autostart,
    StepId::Ollama,
    StepId::Models,
    StepId::EmbeddingModel,
];

/// The steps that must succeed before `step` makes sense.
#[must_use]
pub fn depends_on(step: StepId) -> &'static [StepId] {
    match step {
        StepId::Autostart => &[StepId::Database],
        StepId::Models => &[StepId::Ollama],
        _ => &[],
    }
}

/// Which database to set up.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum DatabasePlan {
    /// A private server managed by bml.
    Private(InitRequest),
    /// A PostgreSQL server that already exists.
    Existing(ExternalRequest),
    /// The saved server if there is one, otherwise a private server from the
    /// bundled PostgreSQL (`pgdist`), with its data in `data_dir`.
    Bundled {
        /// Where the private database lives.
        data_dir: PathBuf,
    },
}

/// What to set up.
#[derive(Debug, Clone)]
pub struct SetupPlan {
    /// Where bml keeps its files.
    pub config_dir: PathBuf,
    /// The database to use; `None` resumes from the saved state.
    pub database: Option<DatabasePlan>,
    /// Where Ollama is.
    pub ollama_host: OllamaHost,
    /// Steps to leave out.
    pub skip: BTreeSet<StepId>,
}

/// `Ok` if `step` should run; otherwise the reason it must not.
pub fn should_run(
    step: StepId,
    skip: &BTreeSet<StepId>,
    failed: &BTreeSet<StepId>,
) -> Result<(), String> {
    if skip.contains(&step) {
        return Err("skipped by request".into());
    }
    for dep in depends_on(step) {
        if failed.contains(dep) || skip.contains(dep) {
            let why = if failed.contains(dep) {
                "did not finish"
            } else {
                "was skipped"
            };
            return Err(format!("{} {why}", dep.label()));
        }
    }
    Ok(())
}

/// Run one step (for "retry"); it ignores `skip` and dependencies, and sends
/// `Started` but no `Finished` (the caller reports the returned outcome).
pub fn run_step(
    step: StepId,
    plan: &SetupPlan,
    http: &dyn HttpClient,
    report: &mut dyn FnMut(StepEvent),
) -> StepOutcome {
    report(StepEvent::Started(step));
    steps::run(step, plan, http, report).unwrap_or_else(|e| StepOutcome::Failed(e.to_string()))
}

/// Run every step in order; a failure never stops the later ones, except
/// that steps depending on a failed or skipped step are skipped.
pub fn run_setup(
    plan: &SetupPlan,
    http: &dyn HttpClient,
    report: &mut dyn FnMut(StepEvent),
) -> Vec<(StepId, StepOutcome)> {
    let mut failed = BTreeSet::new();
    let mut results = Vec::new();
    for step in ALL_STEPS {
        let outcome = match should_run(step, &plan.skip, &failed) {
            Ok(()) => run_step(step, plan, http, report),
            Err(reason) => StepOutcome::Skipped { reason },
        };
        report(StepEvent::Finished(step, outcome.clone()));
        if matches!(outcome, StepOutcome::Failed(_)) {
            failed.insert(step);
        }
        results.push((step, outcome));
    }
    results
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ollama::parse_ollama_host;
    use crate::test_support::Fake;

    fn set(steps: &[StepId]) -> BTreeSet<StepId> {
        steps.iter().copied().collect()
    }

    #[test]
    fn should_run_skips_dependents_of_failed() {
        let none = set(&[]);
        assert!(should_run(StepId::Models, &none, &set(&[StepId::Ollama])).is_err());
        assert!(should_run(StepId::Autostart, &none, &set(&[StepId::Database])).is_err());
        assert!(should_run(StepId::Models, &none, &set(&[StepId::Database])).is_ok());
        assert!(should_run(StepId::EmbeddingModel, &none, &set(&[StepId::Ollama])).is_ok());
    }

    #[test]
    fn should_run_skip_database_skips_autostart_not_models() {
        let skip = set(&[StepId::Database]);
        assert!(should_run(StepId::Database, &skip, &set(&[])).is_err());
        assert!(should_run(StepId::Autostart, &skip, &set(&[])).is_err());
        assert!(should_run(StepId::Models, &skip, &set(&[])).is_ok());
    }

    #[test]
    fn runner_continues_after_a_failure() {
        let dir = tempfile::tempdir().unwrap();
        let plan = SetupPlan {
            config_dir: dir.path().to_path_buf(),
            database: None,
            ollama_host: parse_ollama_host(Some("http://gpu-box:11434")).unwrap(),
            skip: set(&[StepId::EmbeddingModel]),
        };
        let mut events = Vec::new();
        let out = run_setup(&plan, &Fake::new(), &mut |e| events.push(e));
        let ids: Vec<StepId> = out.iter().map(|(s, _)| *s).collect();
        assert_eq!(ids, ALL_STEPS);
        // Warnings on small machines (CI runners), never a failure.
        assert!(
            matches!(
                out[0].1,
                StepOutcome::AlreadyPresent | StepOutcome::Warnings(_)
            ),
            "{:?}",
            out[0]
        );
        assert!(
            matches!(&out[1].1, StepOutcome::Failed(m) if m.contains("no database chosen")),
            "{:?}",
            out[1]
        );
        assert!(matches!(out[2].1, StepOutcome::Skipped { .. }));
        assert!(
            matches!(&out[3].1, StepOutcome::Failed(m) if m.contains("not on this computer")),
            "{:?}",
            out[3]
        );
        assert!(matches!(out[4].1, StepOutcome::Skipped { .. }));
        assert!(matches!(out[5].1, StepOutcome::Skipped { .. }));
        assert!(events.contains(&StepEvent::Started(StepId::Hardware)));
        let finished = events
            .iter()
            .filter(|e| matches!(e, StepEvent::Finished(..)))
            .count();
        assert_eq!(finished, ALL_STEPS.len());
    }

    #[test]
    fn bundled_without_asset_fails_database_and_skips_autostart() {
        let dir = tempfile::tempdir().unwrap();
        let plan = SetupPlan {
            config_dir: dir.path().to_path_buf(),
            database: Some(DatabasePlan::Bundled {
                data_dir: dir.path().join("pgdata"),
            }),
            ollama_host: parse_ollama_host(Some("http://gpu-box:11434")).unwrap(),
            skip: set(&[StepId::Ollama, StepId::Models, StepId::EmbeddingModel]),
        };
        let out = run_setup(&plan, &Fake::new(), &mut |_| {});
        assert!(!matches!(out[0].1, StepOutcome::Failed(_)), "{:?}", out[0]);
        assert!(
            matches!(&out[1].1, StepOutcome::Failed(m) if m.contains("--pg-bindir")),
            "{:?}",
            out[1]
        );
        assert!(
            matches!(out[2].1, StepOutcome::Skipped { .. }),
            "{:?}",
            out[2]
        );
    }
}
