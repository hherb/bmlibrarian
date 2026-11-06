//! `init` against a real PostgreSQL 18 (`BML_TEST_PG_BINDIR`, plus
//! `BML_TEST_PG_EXTENSION_DIRS` to exercise `pg_search`).

mod common;

use std::net::TcpListener;
use std::path::{Path, PathBuf};

use bml_pgserver::conf::provides_pg_search;
use bml_pgserver::control::{status, stop, ServerStatus};
use bml_pgserver::envfile::{read_conn_info, ADMIN_ENV_FILE_NAME, APP_ENV_FILE_NAME};
use bml_pgserver::error::PgServerError;
use bml_pgserver::init::{connect, init, InitRequest, APP_ROLE, DATABASE};
use bml_pgserver::port::{choose_port, is_avoided, port_is_free, DEFAULT_PORT};
use bml_pgserver::state::{load_state, ServerState};

/// Name with a space, a non-ASCII letter and a single quote.
const AWKWARD_DIR_NAME: &str = "data dir ü'q";

/// Stops the server of the config dir when the test ends, pass or fail.
struct StopOnDrop(PathBuf);

impl Drop for StopOnDrop {
    fn drop(&mut self) {
        if let Ok(Some(state)) = load_state(&self.0) {
            let _ = stop(&state);
        }
    }
}

struct Fixture {
    _tmp: tempfile::TempDir,
    config_dir: PathBuf,
    req: InitRequest,
    _stop: StopOnDrop,
}

fn fixture(bindir: PathBuf) -> Fixture {
    let tmp = tempfile::tempdir().unwrap();
    let config_dir = tmp.path().join("config");
    let req = InitRequest {
        bindir,
        data_dir: tmp.path().join(AWKWARD_DIR_NAME),
        extension_dirs: common::test_extension_dirs(),
    };
    let stop = StopOnDrop(config_dir.clone());
    Fixture {
        _tmp: tmp,
        config_dir,
        req,
        _stop: stop,
    }
}

fn state_of(config_dir: &Path) -> ServerState {
    load_state(config_dir).unwrap().expect("state saved")
}

fn installed_extensions(config_dir: &Path) -> Vec<String> {
    let app = read_conn_info(&config_dir.join(APP_ENV_FILE_NAME))
        .unwrap()
        .unwrap();
    let mut client = connect(&app).unwrap();
    client
        .query("SELECT extname::text FROM pg_extension", &[])
        .unwrap()
        .iter()
        .map(|row| row.get(0))
        .collect()
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn fresh_init() {
    let Some(bindir) = common::test_bindir() else {
        return;
    };
    let _guard = common::serial();
    let f = fixture(bindir);

    let outcome = init(&f.req, &f.config_dir).unwrap();
    assert!(outcome.created);
    assert_eq!(status(&outcome.state).unwrap(), ServerStatus::Running);
    assert!(!is_avoided(outcome.state.port));

    let app = read_conn_info(&f.config_dir.join(APP_ENV_FILE_NAME))
        .unwrap()
        .unwrap();
    assert_eq!(
        (app.user.as_str(), app.dbname.as_str()),
        (APP_ROLE, DATABASE)
    );
    let extensions = installed_extensions(&f.config_dir);
    assert!(extensions.iter().any(|e| e == "vector"), "{extensions:?}");
    let expect_pg_search = f.req.extension_dirs.iter().any(|d| provides_pg_search(d));
    assert_eq!(outcome.pg_search, expect_pg_search);
    assert_eq!(
        extensions.iter().any(|e| e == "pg_search"),
        expect_pg_search,
        "{extensions:?}"
    );

    #[cfg(unix)]
    for name in [APP_ENV_FILE_NAME, ADMIN_ENV_FILE_NAME] {
        use std::os::unix::fs::PermissionsExt;
        let mode = std::fs::metadata(f.config_dir.join(name))
            .unwrap()
            .permissions()
            .mode();
        assert_eq!(mode & 0o777, 0o600, "{name}");
    }
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn rerun_is_noop() {
    let Some(bindir) = common::test_bindir() else {
        return;
    };
    let _guard = common::serial();
    let f = fixture(bindir);

    let first = init(&f.req, &f.config_dir).unwrap();
    let read = |name| std::fs::read(f.config_dir.join(name)).unwrap();
    let (app, admin) = (read(APP_ENV_FILE_NAME), read(ADMIN_ENV_FILE_NAME));
    let second = init(&f.req, &f.config_dir).unwrap();
    assert!(!second.created);
    assert_eq!(second.state.port, first.state.port);
    assert_eq!(read(APP_ENV_FILE_NAME), app);
    assert_eq!(read(ADMIN_ENV_FILE_NAME), admin);
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn resumes_after_kill() {
    let Some(bindir) = common::test_bindir() else {
        return;
    };
    let _guard = common::serial();
    let f = fixture(bindir);

    init(&f.req, &f.config_dir).unwrap();
    // Simulate a kill after initdb but before the role, database and app
    // credentials existed.
    let mut admin = read_conn_info(&f.config_dir.join(ADMIN_ENV_FILE_NAME))
        .unwrap()
        .unwrap();
    admin.dbname = "postgres".into();
    let mut client = connect(&admin).unwrap();
    client.batch_execute("DROP DATABASE bmlibrarian").unwrap();
    client.batch_execute("DROP ROLE bml_app").unwrap();
    drop(client);
    std::fs::remove_file(f.config_dir.join(APP_ENV_FILE_NAME)).unwrap();
    stop(&state_of(&f.config_dir)).unwrap();

    let outcome = init(&f.req, &f.config_dir).unwrap();
    assert!(outcome.created);
    assert!(installed_extensions(&f.config_dir)
        .iter()
        .any(|e| e == "vector"));
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn admin_lost_refuses() {
    let Some(bindir) = common::test_bindir() else {
        return;
    };
    let _guard = common::serial();
    let f = fixture(bindir);

    init(&f.req, &f.config_dir).unwrap();
    stop(&state_of(&f.config_dir)).unwrap();
    std::fs::remove_file(f.config_dir.join(ADMIN_ENV_FILE_NAME)).unwrap();
    let err = init(&f.req, &f.config_dir).unwrap_err();
    assert!(
        matches!(err, PgServerError::AdminCredentialsLost { .. }),
        "{err}"
    );
    assert!(f.req.data_dir.join("PG_VERSION").is_file());
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn foreign_dir_refused() {
    let Some(bindir) = common::test_bindir() else {
        return;
    };
    let _guard = common::serial();
    let f = fixture(bindir);

    std::fs::create_dir_all(&f.req.data_dir).unwrap();
    let keep = f.req.data_dir.join("keep.txt");
    std::fs::write(&keep, "mine").unwrap();
    let err = init(&f.req, &f.config_dir).unwrap_err();
    assert!(
        matches!(err, PgServerError::DataDirNotEmpty { .. }),
        "{err}"
    );
    assert_eq!(std::fs::read_to_string(&keep).unwrap(), "mine");
    assert_eq!(std::fs::read_dir(&f.req.data_dir).unwrap().count(), 1);
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn port_taken_moves_on() {
    let Some(bindir) = common::test_bindir() else {
        return;
    };
    let _guard = common::serial();
    let f = fixture(bindir);

    let taken = choose_port(DEFAULT_PORT, port_is_free).unwrap();
    let _holder = TcpListener::bind(("127.0.0.1", taken)).unwrap();
    let outcome = init(&f.req, &f.config_dir).unwrap();
    assert_ne!(outcome.state.port, taken);
    assert!(!is_avoided(outcome.state.port));
}
