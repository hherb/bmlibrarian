//! `start` must return once `pg_ctl` exits, even though the server it starts
//! lives on holding the handles `pg_ctl` was given (as the postmaster does on
//! Windows), and must still quote `pg_ctl`'s error output when it fails.
//! A fake `pg_ctl` plays both parts.
#![cfg(unix)]

use std::os::unix::fs::PermissionsExt;
use std::path::Path;
use std::sync::Mutex;
use std::time::{Duration, Instant};

use bml_pgserver::control::start;
use bml_pgserver::state::ServerState;

/// How long the fake server outlives the fake `pg_ctl`.
const SERVER_LINGERS_SECONDS: u64 = 20;
/// Far less than that, but plenty for `pg_ctl` itself.
const START_RETURNS_WITHIN: Duration = Duration::from_secs(10);

/// One test at a time: writing a script while another thread forks can make
/// running it fail with "text file busy".
static SERIAL: Mutex<()> = Mutex::new(());

/// A server state whose `pg_ctl` reports "stopped" and runs `start_body` on
/// `start`.
fn fake_server(root: &Path, start_body: &str) -> ServerState {
    let bindir = root.join("bin");
    let data_dir = root.join("data");
    std::fs::create_dir_all(&bindir).unwrap();
    std::fs::create_dir_all(&data_dir).unwrap();
    let pg_ctl = bindir.join("pg_ctl");
    std::fs::write(
        &pg_ctl,
        format!("#!/bin/sh\ncase \"$1\" in\n  status) exit 3 ;;\n  start) {start_body} ;;\nesac\n"),
    )
    .unwrap();
    std::fs::set_permissions(&pg_ctl, std::fs::Permissions::from_mode(0o755)).unwrap();
    ServerState {
        bindir,
        data_dir,
        port: 5418,
        extension_dirs: vec![],
    }
}

#[test]
fn start_returns_while_the_server_keeps_pg_ctls_output() {
    let _serial = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let tmp = tempfile::tempdir().unwrap();
    let state = fake_server(
        tmp.path(),
        &format!("sleep {SERVER_LINGERS_SECONDS} & exit 0"),
    );
    let began = Instant::now();
    start(&state).unwrap();
    assert!(
        began.elapsed() < START_RETURNS_WITHIN,
        "start waited {:?} for the server to close pg_ctl's output",
        began.elapsed()
    );
}

#[test]
fn failed_start_quotes_pg_ctl() {
    let _serial = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
    let tmp = tempfile::tempdir().unwrap();
    let state = fake_server(tmp.path(), "echo 'pg_ctl: simulated failure' >&2; exit 1");
    let err = format!("{:?}", start(&state).unwrap_err());
    assert!(err.contains("simulated failure"), "{err}");
}
