//! `bml server status` exit codes for a server that is not running, without
//! a real PostgreSQL: a fake `pg_ctl` returns each `pg_ctl status` code.
#![cfg(unix)]

use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::process::Output;

use bml_pgserver::state::{save_state, ServerState};

/// A configuration folder whose server's `pg_ctl` exits with `code`.
fn config_with_pg_ctl_exit(root: &Path, code: i32) -> PathBuf {
    let bindir = root.join(format!("bin-{code}"));
    std::fs::create_dir_all(&bindir).unwrap();
    let pg_ctl = bindir.join("pg_ctl");
    std::fs::write(&pg_ctl, format!("#!/bin/sh\nexit {code}\n")).unwrap();
    std::fs::set_permissions(&pg_ctl, std::fs::Permissions::from_mode(0o755)).unwrap();
    let config = root.join(format!("cfg-{code}"));
    save_state(
        &config,
        &ServerState {
            bindir,
            data_dir: root.join(format!("data-{code}")),
            port: 5418,
            extension_dirs: vec![],
        },
    )
    .unwrap();
    config
}

/// Run `bml server status`; returns its exit code, stdout and stderr.
fn status(config_dir: &Path) -> (Option<i32>, String, String) {
    let Output {
        status,
        stdout,
        stderr,
    } = std::process::Command::new(env!("CARGO_BIN_EXE_bml"))
        .arg("--config-dir")
        .arg(config_dir)
        .args(["server", "status"])
        .output()
        .unwrap();
    (
        status.code(),
        String::from_utf8_lossy(&stdout).into_owned(),
        String::from_utf8_lossy(&stderr).into_owned(),
    )
}

/// One test, with every script written before anything is spawned, so no
/// fork happens while a script is open for writing (Linux would then fail
/// to run it with "text file busy").
#[test]
fn status_exit_codes_without_a_server() {
    let tmp = tempfile::tempdir().unwrap();
    let stopped = config_with_pg_ctl_exit(tmp.path(), 3);
    let no_data = config_with_pg_ctl_exit(tmp.path(), 4);
    let unexpected = config_with_pg_ctl_exit(tmp.path(), 7);

    let (code, out, _) = status(&stopped);
    assert_eq!(code, Some(3), "{out}");
    assert!(out.contains("Server: stopped"), "{out}");
    assert!(out.contains("Data: "), "{out}");

    let (code, out, _) = status(&no_data);
    assert_eq!(code, Some(1), "{out}");
    assert!(out.contains("data folder missing"), "{out}");

    let (code, out, err) = status(&unexpected);
    assert_eq!(code, Some(1), "{out}");
    assert!(err.contains("pg_ctl status"), "{err}");
}
