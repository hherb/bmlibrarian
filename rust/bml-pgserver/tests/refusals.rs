//! `init`'s refusals and `initdb` cleanup, without a real PostgreSQL: a fake
//! bin folder whose `postgres` only prints a version and whose `initdb`
//! fails. Everything checked here happens before a server would start.
#![cfg(unix)]

use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};

use bml_pgserver::conf::BML_CONF_NAME;
use bml_pgserver::envfile::ADMIN_ENV_FILE_NAME;
use bml_pgserver::error::PgServerError;
use bml_pgserver::init::{init, InitRequest};
use bml_pgserver::state::{save_state, ServerState};

/// Write an executable shell script `name` into `bindir`.
fn script(bindir: &Path, name: &str, body: &str) {
    let path = bindir.join(name);
    std::fs::write(&path, format!("#!/bin/sh\n{body}\n")).unwrap();
    std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o755)).unwrap();
}

/// A fake bin folder reporting PostgreSQL `version`, with a failing `initdb`.
fn fake_bindir(root: &Path, version: &str) -> PathBuf {
    let bindir = root.join(format!("bin-{version}"));
    std::fs::create_dir_all(&bindir).unwrap();
    script(
        &bindir,
        "postgres",
        &format!("echo 'postgres (PostgreSQL) {version}'"),
    );
    script(
        &bindir,
        "initdb",
        "echo 'initdb: simulated failure' >&2; exit 1",
    );
    bindir
}

/// A data folder holding `files`.
fn data_dir_with(root: &Path, name: &str, files: &[&str]) -> PathBuf {
    let dir = root.join(name);
    std::fs::create_dir_all(&dir).unwrap();
    for file in files {
        std::fs::write(dir.join(file), "x").unwrap();
    }
    dir
}

/// A state file in `config_dir` naming `bindir` and `data_dir`.
fn save(config_dir: &Path, bindir: &Path, data_dir: &Path) {
    save_state(
        config_dir,
        &ServerState {
            bindir: bindir.to_owned(),
            data_dir: data_dir.to_owned(),
            port: 5418,
            extension_dirs: vec![],
        },
    )
    .unwrap();
}

fn request(bindir: &Path, data_dir: &Path) -> InitRequest {
    InitRequest {
        bindir: bindir.to_owned(),
        data_dir: data_dir.to_owned(),
        extension_dirs: vec![],
    }
}

/// One test, so no other thread forks while a script is being written
/// (Linux would then fail to run it with "text file busy").
#[test]
fn refusals_need_no_server() {
    let tmp = tempfile::tempdir().unwrap();
    let root = tmp.path();
    let bin18 = fake_bindir(root, "18.0");

    // Too old.
    let bin17 = fake_bindir(root, "17.5");
    let config = root.join("cfg-old");
    let err = init(&request(&bin17, &root.join("d-old")), &config).unwrap_err();
    assert!(
        matches!(err, PgServerError::UnsupportedVersion { found: 17 }),
        "{err}"
    );
    assert!(!config.exists());

    // Another server's data folder, nothing of ours names it.
    let data = data_dir_with(root, "d-foreign", &["PG_VERSION"]);
    let err = init(&request(&bin18, &data), &root.join("cfg-foreign")).unwrap_err();
    assert!(matches!(err, PgServerError::ForeignDataDir { .. }), "{err}");

    // The state file manages a different data folder.
    let config = root.join("cfg-mismatch");
    save(&config, &bin18, &root.join("d-saved"));
    let err = init(&request(&bin18, &root.join("d-other")), &config).unwrap_err();
    assert!(
        matches!(
            err,
            PgServerError::StateMismatch {
                field: "data folder",
                ..
            }
        ),
        "{err}"
    );

    // Set up by us, but the admin credentials are gone.
    let config = root.join("cfg-admin-lost");
    let data = data_dir_with(root, "d-admin-lost", &["PG_VERSION", BML_CONF_NAME]);
    save(&config, &bin18, &data);
    let err = init(&request(&bin18, &data), &config).unwrap_err();
    assert!(
        matches!(err, PgServerError::AdminCredentialsLost { .. }),
        "{err}"
    );

    // Our first run was killed during initdb, leaving its password file.
    let config = root.join("cfg-incomplete");
    let data = data_dir_with(root, "d-incomplete", &["PG_VERSION"]);
    save(&config, &bin18, &data);
    std::fs::write(config.join(".pwfile.tmp"), "secret").unwrap();
    let err = init(&request(&bin18, &data), &config).unwrap_err();
    assert!(
        matches!(err, PgServerError::IncompleteDataDir { .. }),
        "{err}"
    );
    assert!(!config.join(".pwfile.tmp").exists(), "leftover removed");

    // initdb fails: its error is reported and the password file is removed,
    // while the admin credentials stay for the next run.
    let config = root.join("cfg-initdb");
    let err = init(&request(&bin18, &root.join("d-initdb")), &config).unwrap_err();
    assert!(matches!(err, PgServerError::Command { .. }), "{err}");
    assert!(err.to_string().contains("simulated failure"), "{err}");
    assert!(!config.join(".pwfile.tmp").exists());
    assert!(config.join(ADMIN_ENV_FILE_NAME).is_file());
}
