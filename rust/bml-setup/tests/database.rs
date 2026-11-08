//! The database step against a real PostgreSQL 18 (`BML_TEST_PG_BINDIR`),
//! using only servers started here in temp folders. The Autostart step is
//! never run for a private server: it would register a real login item.

mod common;

use std::collections::BTreeSet;
use std::path::PathBuf;

use bml_pgserver::control::stop;
use bml_pgserver::envfile::{read_conn_info, ADMIN_ENV_FILE_NAME};
use bml_pgserver::external::ExternalRequest;
use bml_pgserver::init::{connect, init, InitRequest, APP_ROLE, DATABASE};
use bml_pgserver::state::load_state;
use bml_setup::ollama::parse_ollama_host;
use bml_setup::runner::{run_step, DatabasePlan, SetupPlan};
use bml_setup::{StepId, StepOutcome};
use bmlib::publications::fetchers::registry::{FetchError, HttpClient, HttpResponse, HttpStream};
use std::collections::BTreeMap;

/// The database steps never touch HTTP.
struct NoHttp;
impl HttpClient for NoHttp {
    fn get(&self, _: &str) -> Result<HttpResponse, FetchError> {
        Err(FetchError::Transport("no network in this test".into()))
    }
    fn post_json(
        &self,
        _: &str,
        _: &serde_json::Value,
        _: &BTreeMap<String, String>,
    ) -> Result<HttpResponse, FetchError> {
        Err(FetchError::Transport("no network in this test".into()))
    }
    fn post_json_stream(
        &self,
        _: &str,
        _: &serde_json::Value,
        _: &BTreeMap<String, String>,
    ) -> Result<HttpStream, FetchError> {
        Err(FetchError::Transport("no network in this test".into()))
    }
}

/// Stops the server of the config dir when the test ends, pass or fail.
struct StopOnDrop(PathBuf);
impl Drop for StopOnDrop {
    fn drop(&mut self) {
        if let Ok(Some(state)) = load_state(&self.0) {
            let _ = stop(&state);
        }
    }
}

fn plan(config_dir: PathBuf, database: Option<DatabasePlan>) -> SetupPlan {
    SetupPlan {
        config_dir,
        database,
        ollama_host: parse_ollama_host(None).unwrap(),
        skip: BTreeSet::new(),
    }
}

fn step_database(plan: &SetupPlan) -> StepOutcome {
    run_step(StepId::Database, plan, &NoHttp, &mut |_| {})
}

/// `outcome` is `expected`, or, when the run supplies no pg_search, the
/// warning about it.
fn assert_database(outcome: StepOutcome, expected: StepOutcome) {
    if common::test_extension_dirs().is_empty() {
        assert!(
            matches!(&outcome, StepOutcome::Warnings(w) if w.iter().any(|m| m.contains("pg_search"))),
            "{outcome:?}"
        );
    } else {
        assert_eq!(outcome, expected);
    }
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn setup_database_private_then_resume() {
    let Some(bindir) = common::test_bindir() else {
        return;
    };
    let _guard = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let cfg = tmp.path().join("cfg");
    let _stop = StopOnDrop(cfg.clone());
    let req = InitRequest {
        bindir,
        data_dir: tmp.path().join("data"),
        extension_dirs: common::test_extension_dirs(),
    };
    assert_database(
        step_database(&plan(cfg.clone(), Some(DatabasePlan::Private(req)))),
        StepOutcome::Installed,
    );
    assert_database(step_database(&plan(cfg, None)), StepOutcome::AlreadyPresent);
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn setup_database_existing_then_resume() {
    let Some(bindir) = common::test_bindir() else {
        return;
    };
    let _guard = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let (dir_a, dir_b) = (tmp.path().join("a"), tmp.path().join("b"));
    let _stop = StopOnDrop(dir_a.clone());
    init(
        &InitRequest {
            bindir,
            data_dir: tmp.path().join("data"),
            extension_dirs: common::test_extension_dirs(),
        },
        &dir_a,
    )
    .unwrap();
    let admin = read_conn_info(&dir_a.join(ADMIN_ENV_FILE_NAME))
        .unwrap()
        .unwrap();
    let mut maintenance = admin.clone();
    maintenance.dbname = "postgres".into();
    let mut client = connect(&maintenance).unwrap();
    client
        .batch_execute(&format!("DROP DATABASE {DATABASE}"))
        .unwrap();
    client
        .batch_execute(&format!("DROP ROLE {APP_ROLE}"))
        .unwrap();

    let req = ExternalRequest {
        host: admin.host,
        port: admin.port,
        superuser: admin.user,
        password: admin.password,
        needs_pg_search: false,
    };
    assert_database(
        step_database(&plan(dir_b.clone(), Some(DatabasePlan::Existing(req)))),
        StepOutcome::Installed,
    );
    let resume = plan(dir_b, None);
    // Resume rebuilds the request with pg_search required (off Windows); the
    // temp server only has it when the run supplies extension folders.
    let outcome = step_database(&resume);
    if common::test_extension_dirs().is_empty() && !cfg!(windows) {
        assert!(
            matches!(&outcome, StepOutcome::Failed(m) if m.contains("pg_search")),
            "{outcome:?}"
        );
    } else {
        assert_database(outcome, StepOutcome::AlreadyPresent);
    }
    assert!(matches!(
        run_step(StepId::Autostart, &resume, &NoHttp, &mut |_| {}),
        StepOutcome::Skipped { .. }
    ));
}
