//! `adopt` against a real PostgreSQL 18 (`BML_TEST_PG_BINDIR`): a private
//! server started in a temp folder plays the "existing" server.

mod common;

use std::path::{Path, PathBuf};

use bml_pgserver::control::stop;
use bml_pgserver::envfile::{
    read_conn_info, render_env, write_private_file, ConnInfo, ADMIN_ENV_FILE_NAME,
    APP_ENV_FILE_NAME,
};
use bml_pgserver::error::PgServerError;
use bml_pgserver::external::{
    adopt, save_external_state, ExternalRequest, ExternalState, EXTERNAL_STATE_FILE_NAME,
};
use bml_pgserver::init::{connect, init, InitRequest, APP_ROLE, DATABASE, HOST};
use bml_pgserver::state::{load_state, STATE_FILE_NAME};

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
    /// The private server standing in for an existing one.
    dir_a: PathBuf,
    /// The folder `adopt` writes to.
    dir_b: PathBuf,
    /// The request naming server A as the existing server.
    req: ExternalRequest,
    admin: ConnInfo,
    _tmp: tempfile::TempDir,
}

fn fixture(bindir: PathBuf) -> Fixture {
    let tmp = tempfile::tempdir().unwrap();
    let dir_a = tmp.path().join("a");
    let dir_b = tmp.path().join("b");
    let stop = StopOnDrop(dir_a.clone());
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
    let req = ExternalRequest {
        host: admin.host.clone(),
        port: admin.port,
        superuser: admin.user.clone(),
        password: admin.password.clone(),
        needs_pg_search: false,
    };
    Fixture {
        _stop: stop,
        dir_a,
        dir_b,
        req,
        admin,
        _tmp: tmp,
    }
}

/// Drop the app database and role of server A, as if never created.
fn drop_app_objects(admin: &ConnInfo) {
    let mut maintenance = admin.clone();
    maintenance.dbname = "postgres".into();
    let mut client = connect(&maintenance).unwrap();
    client
        .batch_execute(&format!("DROP DATABASE {DATABASE}"))
        .unwrap();
    client
        .batch_execute(&format!("DROP ROLE {APP_ROLE}"))
        .unwrap();
}

fn files_in(dir: &Path) -> Vec<String> {
    std::fs::read_dir(dir)
        .map(|entries| {
            entries
                .map(|e| e.unwrap().file_name().to_string_lossy().into_owned())
                .collect()
        })
        .unwrap_or_default()
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn adopt_refuses_names_it_did_not_create() {
    let Some(bindir) = common::test_bindir() else {
        return;
    };
    let _guard = common::serial();
    let f = fixture(bindir);

    let err = adopt(&f.req, &f.dir_b).unwrap_err();
    assert!(
        matches!(err, PgServerError::NameTaken { kind: "role", .. }),
        "{err}"
    );
    assert!(files_in(&f.dir_b).is_empty(), "{:?}", files_in(&f.dir_b));
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn adopt_creates_role_database_and_vector() {
    let Some(bindir) = common::test_bindir() else {
        return;
    };
    let _guard = common::serial();
    let f = fixture(bindir);
    drop_app_objects(&f.admin);

    let outcome = adopt(&f.req, &f.dir_b).unwrap();
    assert!(outcome.created);
    assert_eq!(outcome.state.port, f.admin.port);
    assert_eq!(outcome.state.host, HOST);

    let app = read_conn_info(&f.dir_b.join(APP_ENV_FILE_NAME))
        .unwrap()
        .unwrap();
    let mut client = connect(&app).expect("bml.env connects");
    let extensions: Vec<String> = client
        .query("SELECT extname::text FROM pg_extension", &[])
        .unwrap()
        .iter()
        .map(|row| row.get(0))
        .collect();
    assert!(extensions.iter().any(|e| e == "vector"), "{extensions:?}");

    let admin_b = read_conn_info(&f.dir_b.join(ADMIN_ENV_FILE_NAME))
        .unwrap()
        .unwrap();
    assert_eq!(admin_b.dbname, DATABASE);
    #[cfg(unix)]
    for name in [
        ADMIN_ENV_FILE_NAME,
        APP_ENV_FILE_NAME,
        EXTERNAL_STATE_FILE_NAME,
    ] {
        use std::os::unix::fs::PermissionsExt;
        let mode = std::fs::metadata(f.dir_b.join(name))
            .unwrap()
            .permissions()
            .mode();
        assert_eq!(mode & 0o777, 0o600, "{name}");
    }

    let again = adopt(&f.req, &f.dir_b).unwrap();
    assert!(!again.created);
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn adopt_resumes_after_state_saved_before_objects() {
    let Some(bindir) = common::test_bindir() else {
        return;
    };
    let _guard = common::serial();
    let f = fixture(bindir);
    drop_app_objects(&f.admin);

    std::fs::create_dir_all(&f.dir_b).unwrap();
    save_external_state(
        &f.dir_b,
        &ExternalState {
            host: f.req.host.clone(),
            port: f.req.port,
            superuser: f.req.superuser.clone(),
        },
    )
    .unwrap();
    write_private_file(&f.dir_b.join(ADMIN_ENV_FILE_NAME), &render_env(&f.admin)).unwrap();

    let outcome = adopt(&f.req, &f.dir_b).unwrap();
    assert!(outcome.created);
    let app = read_conn_info(&f.dir_b.join(APP_ENV_FILE_NAME))
        .unwrap()
        .unwrap();
    connect(&app).unwrap();
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn adopt_refuses_when_private_server_configured() {
    let Some(bindir) = common::test_bindir() else {
        return;
    };
    let _guard = common::serial();
    let f = fixture(bindir);

    let err = adopt(&f.req, &f.dir_a).unwrap_err();
    assert!(
        matches!(err, PgServerError::PrivateServerConfigured { .. }),
        "{err}"
    );
    assert!(f.dir_a.join(STATE_FILE_NAME).exists());
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn init_refuses_when_external_configured() {
    let Some(bindir) = common::test_bindir() else {
        return;
    };
    let _guard = common::serial();
    let f = fixture(bindir.clone());
    drop_app_objects(&f.admin);
    adopt(&f.req, &f.dir_b).unwrap();

    let err = init(
        &InitRequest {
            bindir,
            data_dir: f.dir_b.join("data"),
            extension_dirs: vec![],
        },
        &f.dir_b,
    )
    .unwrap_err();
    assert!(
        matches!(err, PgServerError::ExternalServerConfigured { .. }),
        "{err}"
    );
    assert!(!f.dir_b.join("data").exists());
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn adopt_refuses_other_address_than_saved() {
    let Some(bindir) = common::test_bindir() else {
        return;
    };
    let _guard = common::serial();
    let f = fixture(bindir);
    drop_app_objects(&f.admin);
    adopt(&f.req, &f.dir_b).unwrap();
    // The same server, reached under another name, is a different address.
    let other = ExternalRequest {
        host: "localhost".into(),
        ..f.req.clone()
    };
    let err = adopt(&other, &f.dir_b).unwrap_err();
    assert!(matches!(err, PgServerError::StateMismatch { .. }), "{err}");
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn adopt_refuses_wrong_password() {
    let Some(bindir) = common::test_bindir() else {
        return;
    };
    let _guard = common::serial();
    let f = fixture(bindir);

    let wrong = ExternalRequest {
        password: "not the password".into(),
        ..f.req.clone()
    };
    let err = adopt(&wrong, &f.dir_b).unwrap_err();
    assert!(matches!(err, PgServerError::Connect { .. }), "{err}");
    assert!(files_in(&f.dir_b).is_empty());
}
