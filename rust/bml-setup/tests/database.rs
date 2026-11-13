//! The database step against a real PostgreSQL 18 (`BML_TEST_PG_BINDIR`),
//! using only servers started here in temp folders. The Autostart step is
//! never run for a private server: it would register a real login item.

mod common;

use std::collections::BTreeSet;
use std::path::PathBuf;

use bml_db::library::{load_library, resolve_library, LIBRARY_FILE_NAME};
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
        home: Some(config_dir.join("home")),
        config_dir,
        database,
        ollama_host: parse_ollama_host(None).unwrap(),
        skip: BTreeSet::new(),
        library_dir: None,
    }
}

fn step_library(plan: &SetupPlan) -> StepOutcome {
    run_step(StepId::Library, plan, &NoHttp, &mut |_| {})
}

fn step_database(plan: &SetupPlan) -> StepOutcome {
    run_step(StepId::Database, plan, &NoHttp, &mut |_| {})
}

/// `outcome` is `expected`, or, when the run supplies no pg_search, the
/// warning about it.
fn assert_database(outcome: StepOutcome, expected: StepOutcome) {
    if !common::test_provides_pg_search() {
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
    let lib_dir = tmp.path().join("My Library");
    let library = resolve_library(&cfg, Some(&lib_dir), None).unwrap();
    let req = InitRequest {
        bindir,
        data_dir: library.database_dir(),
        extension_dirs: common::test_extension_dirs(),
    };
    let new = SetupPlan {
        library_dir: Some(lib_dir.clone()),
        ..plan(cfg.clone(), Some(DatabasePlan::Private(req)))
    };
    assert_database(step_database(&new), StepOutcome::Installed);
    // The new server's library is recorded with it.
    assert_eq!(load_library(&cfg).unwrap(), Some(library.clone()));
    assert_eq!(
        load_state(&cfg).unwrap().unwrap().data_dir,
        library.database_dir()
    );
    assert_eq!(step_library(&new), StepOutcome::Installed);
    assert!(library.documents_dir().is_dir());
    // A first run that failed after `init` saved the server left no record;
    // resuming the server records its library again.
    std::fs::remove_file(cfg.join(LIBRARY_FILE_NAME)).unwrap();
    let resume = plan(cfg.clone(), None);
    assert_database(step_database(&resume), StepOutcome::AlreadyPresent);
    assert_eq!(load_library(&cfg).unwrap(), Some(library));
    assert_eq!(step_library(&resume), StepOutcome::AlreadyPresent);
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
    // Not required, so not installed even when the server has it.
    let existing = plan(dir_b.clone(), Some(DatabasePlan::Existing(req)));
    let outcome = step_database(&existing);
    assert!(
        matches!(&outcome, StepOutcome::Warnings(w) if w.iter().any(|m| m.contains("pg_search"))),
        "{outcome:?}"
    );
    assert_eq!(step_library(&existing), StepOutcome::Installed);
    let resume = plan(dir_b, None);
    // Resume rebuilds the request with pg_search required (off Windows); the
    // temp server only has it when the run's extension folders supply it.
    let outcome = step_database(&resume);
    if !common::test_provides_pg_search() && !cfg!(windows) {
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
