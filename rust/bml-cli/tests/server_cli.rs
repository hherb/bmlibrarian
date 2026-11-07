//! `bml server …` end to end, through the built binary.

use std::process::{Command, Output};

fn bml(config_dir: &std::path::Path, args: &[&str]) -> Output {
    Command::new(env!("CARGO_BIN_EXE_bml"))
        .arg("--config-dir")
        .arg(config_dir)
        .args(args)
        .output()
        .unwrap()
}

fn text(bytes: &[u8]) -> String {
    String::from_utf8_lossy(bytes).into_owned()
}

/// Runs `bml server stop` for a configuration folder when the test ends,
/// pass or fail; declared after the temp folder so it drops first.
struct StopOnDrop(std::path::PathBuf);

impl Drop for StopOnDrop {
    fn drop(&mut self) {
        let _ = bml(&self.0, &["server", "stop"]);
    }
}

#[test]
fn status_not_set_up() {
    let cfg = tempfile::tempdir().unwrap();
    let out = bml(cfg.path(), &["server", "status"]);
    assert_eq!(out.status.code(), Some(2));
    assert!(
        text(&out.stdout).contains("not set up"),
        "{}",
        text(&out.stdout)
    );
}

#[test]
fn corrupt_state_errors() {
    let cfg = tempfile::tempdir().unwrap();
    std::fs::write(cfg.path().join("bml-pgserver.json"), "{x").unwrap();
    let out = bml(cfg.path(), &["server", "status"]);
    assert_eq!(out.status.code(), Some(1));
    assert!(
        text(&out.stderr).contains("bml-pgserver.json"),
        "{}",
        text(&out.stderr)
    );
}

#[test]
fn commands_without_setup_exit_2() {
    let cfg = tempfile::tempdir().unwrap();
    for args in [
        &["server", "start"][..],
        &["server", "stop"][..],
        &["server", "restart"][..],
        &["server", "autostart", "enable"][..],
    ] {
        let out = bml(cfg.path(), args);
        assert_eq!(out.status.code(), Some(2), "{args:?}");
        assert!(text(&out.stdout).contains("not set up"), "{args:?}");
    }
}

#[test]
fn init_failure_exits_1_with_message() {
    let tmp = tempfile::tempdir().unwrap();
    let missing = tmp.path().join("no pg here");
    let out = bml(
        &tmp.path().join("config"),
        &[
            "server",
            "init",
            "--bindir",
            &missing.to_string_lossy(),
            "--data-dir",
            &tmp.path().join("data").to_string_lossy(),
        ],
    );
    assert_eq!(out.status.code(), Some(1));
    assert!(
        text(&out.stderr).contains("no pg here"),
        "{}",
        text(&out.stderr)
    );
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn init_status_stop() {
    let Some(bindir) = std::env::var_os("BML_TEST_PG_BINDIR").filter(|v| !v.is_empty()) else {
        return;
    };
    let tmp = tempfile::tempdir().unwrap();
    let cfg = tmp.path().join("config");
    let data = tmp.path().join("data dir");
    let _stop = StopOnDrop(cfg.clone());
    let mut init = vec![
        "server".to_owned(),
        "init".to_owned(),
        "--bindir".to_owned(),
        bindir.to_string_lossy().into_owned(),
        "--data-dir".to_owned(),
        data.to_string_lossy().into_owned(),
    ];
    if let Some(dirs) = std::env::var_os("BML_TEST_PG_EXTENSION_DIRS") {
        for dir in std::env::split_paths(&dirs).filter(|d| !d.as_os_str().is_empty()) {
            init.push("--extension-dir".to_owned());
            init.push(dir.to_string_lossy().into_owned());
        }
    }
    let init: Vec<&str> = init.iter().map(String::as_str).collect();

    let out = bml(&cfg, &init);
    assert_eq!(out.status.code(), Some(0), "{}", text(&out.stderr));
    let out = bml(&cfg, &["server", "status"]);
    assert_eq!(
        out.status.code(),
        Some(0),
        "{}{}",
        text(&out.stdout),
        text(&out.stderr)
    );
    assert!(
        text(&out.stdout).contains("Extensions: vector"),
        "{}",
        text(&out.stdout)
    );
    let out = bml(&cfg, &["server", "stop"]);
    assert_eq!(out.status.code(), Some(0), "{}", text(&out.stderr));
    let out = bml(&cfg, &["server", "status"]);
    assert_eq!(out.status.code(), Some(3), "stopped");
    assert!(text(&out.stdout).contains("Server: stopped"));
}

#[cfg(unix)]
#[test]
fn closed_stdout_does_not_panic() {
    let cfg = tempfile::tempdir().unwrap();
    let (reader, writer) = std::io::pipe().unwrap();
    drop(reader);
    let out = Command::new(env!("CARGO_BIN_EXE_bml"))
        .arg("--config-dir")
        .arg(cfg.path())
        .args(["server", "status"])
        .stdout(writer)
        .output()
        .unwrap();
    assert!(
        !text(&out.stderr).contains("panicked"),
        "{}",
        text(&out.stderr)
    );
    assert_eq!(out.status.code(), Some(2));
}
