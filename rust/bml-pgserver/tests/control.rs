//! Start/stop/restart against a real PostgreSQL 18 (`BML_TEST_PG_BINDIR`).

mod common;

use std::process::Command;

use bml_pgserver::conf::{ensure_include, render_bml_conf, ServerConfig, BML_CONF_NAME};
use bml_pgserver::control::{restart, start, status, stop, tool, ServerStatus};
use bml_pgserver::port::{choose_port, port_is_free, DEFAULT_PORT};
use bml_pgserver::state::ServerState;

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn start_stop_idempotent() {
    let Some(bindir) = common::test_bindir() else {
        return;
    };
    let _guard = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let data_dir = tmp.path().join("data");
    let ok = Command::new(tool(&bindir, "initdb"))
        .arg("-D")
        .arg(&data_dir)
        .args(["-U", "bml_admin", "--auth=trust"])
        .output()
        .unwrap();
    assert!(
        ok.status.success(),
        "{}",
        String::from_utf8_lossy(&ok.stderr)
    );

    let port = choose_port(DEFAULT_PORT, port_is_free).unwrap();
    let cfg = ServerConfig {
        port,
        extension_dirs: vec![],
        preload_pg_search: false,
    };
    std::fs::write(data_dir.join(BML_CONF_NAME), render_bml_conf(&cfg)).unwrap();
    let conf = data_dir.join("postgresql.conf");
    let text = ensure_include(&std::fs::read_to_string(&conf).unwrap()).unwrap();
    std::fs::write(&conf, text).unwrap();

    let state = ServerState {
        pg_major: 18,
        bindir,
        data_dir,
        port,
        extension_dirs: vec![],
    };
    assert_eq!(status(&state).unwrap(), ServerStatus::Stopped);
    start(&state).unwrap();
    start(&state).unwrap();
    assert_eq!(status(&state).unwrap(), ServerStatus::Running);
    stop(&state).unwrap();
    stop(&state).unwrap();
    assert_eq!(status(&state).unwrap(), ServerStatus::Stopped);
    restart(&state).unwrap();
    assert_eq!(status(&state).unwrap(), ServerStatus::Running);
    stop(&state).unwrap();
}
