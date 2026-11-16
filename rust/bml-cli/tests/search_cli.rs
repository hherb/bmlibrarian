//! `bml search` from the command line.

use std::path::Path;
use std::process::{Command, Output};

fn bml(config_dir: &Path, args: &[&str]) -> Output {
    Command::new(env!("CARGO_BIN_EXE_bml"))
        .arg("--config-dir")
        .arg(config_dir)
        .args(args)
        .env("HOME", config_dir)
        .env("USERPROFILE", config_dir)
        .output()
        .unwrap()
}

#[test]
fn search_without_setup_exits_2() {
    let cfg = tempfile::tempdir().unwrap();
    let out = bml(cfg.path(), &["search", "exercise for depression"]);
    let err = String::from_utf8_lossy(&out.stderr);
    assert_eq!(out.status.code(), Some(2), "{err}");
    assert!(err.contains("bml setup"), "{err}");
}

#[test]
fn search_needs_a_query() {
    let cfg = tempfile::tempdir().unwrap();
    let out = bml(cfg.path(), &["search"]);
    assert_eq!(out.status.code(), Some(2));
}
