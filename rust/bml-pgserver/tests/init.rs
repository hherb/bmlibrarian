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

/// Fields drop in order: the server is stopped before its folder is deleted.
struct Fixture {
    _stop: StopOnDrop,
    config_dir: PathBuf,
    req: InitRequest,
    _tmp: tempfile::TempDir,
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
        _stop: stop,
        config_dir,
        req,
        _tmp: tmp,
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
    assert!(!f.config_dir.join(".pwfile.tmp").exists());
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
fn app_env_lost_resets_password() {
    let Some(bindir) = common::test_bindir() else {
        return;
    };
    let _guard = common::serial();
    let f = fixture(bindir);

    init(&f.req, &f.config_dir).unwrap();
    let app_env = f.config_dir.join(APP_ENV_FILE_NAME);
    let old = read_conn_info(&app_env).unwrap().unwrap();
    std::fs::remove_file(&app_env).unwrap();

    let outcome = init(&f.req, &f.config_dir).unwrap();
    assert!(outcome.created);
    assert!(outcome.app_password_reset);
    let new = read_conn_info(&app_env).unwrap().unwrap();
    assert_ne!(new.password, old.password);
    connect(&new).expect("the role was given the new password");
    assert!(connect(&old).is_err());
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn app_password_mismatch_is_repaired() {
    let Some(bindir) = common::test_bindir() else {
        return;
    };
    let _guard = common::serial();
    let f = fixture(bindir);

    init(&f.req, &f.config_dir).unwrap();
    // As if the data folder came from another machine: the role's password
    // no longer matches the bml.env kept here.
    let mut admin = read_conn_info(&f.config_dir.join(ADMIN_ENV_FILE_NAME))
        .unwrap()
        .unwrap();
    admin.dbname = "postgres".into();
    connect(&admin)
        .unwrap()
        .batch_execute(&format!("ALTER ROLE {APP_ROLE} PASSWORD 'elsewhere'"))
        .unwrap();
    let app_env = f.config_dir.join(APP_ENV_FILE_NAME);
    let app = read_conn_info(&app_env).unwrap().unwrap();
    assert!(connect(&app).is_err());

    let outcome = init(&f.req, &f.config_dir).unwrap();
    assert!(outcome.created, "the password reset is reported");
    assert!(outcome.app_password_reset);
    assert_eq!(read_conn_info(&app_env).unwrap().unwrap(), app);
    connect(&app).expect("bml.env's password works again");
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn missing_data_dir_refused() {
    let Some(bindir) = common::test_bindir() else {
        return;
    };
    let _guard = common::serial();
    let f = fixture(bindir);

    init(&f.req, &f.config_dir).unwrap();
    stop(&state_of(&f.config_dir)).unwrap();
    // As if its disk were not mounted.
    let away = f.req.data_dir.with_file_name("moved away");
    std::fs::rename(&f.req.data_dir, &away).unwrap();

    let err = init(&f.req, &f.config_dir).unwrap_err();
    assert!(matches!(err, PgServerError::DataDirMissing { .. }), "{err}");
    assert!(!f.req.data_dir.exists(), "no new server was created");
    let err = bml_pgserver::control::start(&state_of(&f.config_dir)).unwrap_err();
    assert!(
        matches!(err, PgServerError::DataDirUnavailable { .. }),
        "{err}"
    );
    std::fs::rename(&away, &f.req.data_dir).unwrap();
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn admin_password_reused_when_initdb_never_ran() {
    let Some(bindir) = common::test_bindir() else {
        return;
    };
    let _guard = common::serial();
    let f = fixture(bindir);

    init(&f.req, &f.config_dir).unwrap();
    stop(&state_of(&f.config_dir)).unwrap();
    // As if the first run was killed after saving its state and admin
    // credentials, before initdb: no data folder, no bml.env.
    std::fs::remove_dir_all(&f.req.data_dir).unwrap();
    std::fs::remove_file(f.config_dir.join(APP_ENV_FILE_NAME)).unwrap();
    let admin_env = f.config_dir.join(ADMIN_ENV_FILE_NAME);
    let before = std::fs::read(&admin_env).unwrap();

    init(&f.req, &f.config_dir).unwrap();
    assert_eq!(std::fs::read(&admin_env).unwrap(), before);
    let mut admin = read_conn_info(&admin_env).unwrap().unwrap();
    admin.dbname = "postgres".into();
    connect(&admin).expect("initdb used the saved admin password");
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

#[cfg(unix)]
#[test]
fn unsafe_path_refused() {
    let tmp = tempfile::tempdir().unwrap();
    let config_dir = tmp.path().join("config");
    let req = InitRequest {
        bindir: tmp.path().join("bin"),
        data_dir: tmp.path().join("data $USER \"q\""),
        extension_dirs: vec![],
    };
    let err = init(&req, &config_dir).unwrap_err();
    assert!(matches!(err, PgServerError::UnsafePath { .. }), "{err}");
    assert!(!req.data_dir.exists());
    assert!(!config_dir.exists());
}

#[test]
fn bad_extension_dir_refused() {
    let tmp = tempfile::tempdir().unwrap();
    let config_dir = tmp.path().join("config");
    let req = InitRequest {
        bindir: tmp.path().join("bin"),
        data_dir: tmp.path().join("data"),
        extension_dirs: vec![tmp.path().join("no such extension folder")],
    };
    let err = init(&req, &config_dir).unwrap_err();
    assert!(
        matches!(err, PgServerError::BadExtensionDir { .. }),
        "{err}"
    );
    assert!(!req.data_dir.exists());
    assert!(!config_dir.exists());
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn foreign_cluster_untouched() {
    let Some(bindir) = common::test_bindir() else {
        return;
    };
    let _guard = common::serial();
    let f = fixture(bindir.clone());

    let ok = std::process::Command::new(bml_pgserver::control::tool(&bindir, "initdb"))
        .arg("-D")
        .arg(&f.req.data_dir)
        .output()
        .unwrap();
    assert!(ok.status.success());
    let hba = f.req.data_dir.join("pg_hba.conf");
    let marker = format!(
        "{}# someone else's cluster\n",
        std::fs::read_to_string(&hba).unwrap()
    );
    std::fs::write(&hba, &marker).unwrap();
    let conf_before = std::fs::read(f.req.data_dir.join("postgresql.conf")).unwrap();
    // A leftover admin file from an earlier failed run must not make it "ours".
    std::fs::create_dir_all(&f.config_dir).unwrap();
    std::fs::write(
        f.config_dir.join(ADMIN_ENV_FILE_NAME),
        "POSTGRES_HOST=127.0.0.1\nPOSTGRES_PORT=5418\nPOSTGRES_DB=bmlibrarian\nPOSTGRES_USER=bml_admin\nPOSTGRES_PASSWORD=00\n",
    )
    .unwrap();

    let err = init(&f.req, &f.config_dir).unwrap_err();
    assert!(matches!(err, PgServerError::ForeignDataDir { .. }), "{err}");
    assert_eq!(std::fs::read_to_string(&hba).unwrap(), marker);
    assert_eq!(
        std::fs::read(f.req.data_dir.join("postgresql.conf")).unwrap(),
        conf_before
    );
    assert!(!f.req.data_dir.join("bml.conf").exists());
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn db_error_is_descriptive() {
    let Some(bindir) = common::test_bindir() else {
        return;
    };
    let _guard = common::serial();
    let f = fixture(bindir);

    init(&f.req, &f.config_dir).unwrap();
    let mut app = read_conn_info(&f.config_dir.join(APP_ENV_FILE_NAME))
        .unwrap()
        .unwrap();
    app.password = "wrong".into();
    let err = match connect(&app) {
        Ok(_) => panic!("connected with a wrong password"),
        Err(e) => e,
    };
    let text = err.to_string();
    assert!(text.contains("password authentication failed"), "{text}");
    for part in [
        APP_ROLE,
        DATABASE,
        &format!(":{}", app.port),
        "SQLSTATE 28P01",
    ] {
        assert!(text.contains(part), "{part} missing from: {text}");
    }
}
