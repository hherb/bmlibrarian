//! `bml library …` paths that need no database.

use std::path::Path;
use std::process::{Command, Output};

use bml_db::library::{ensure_library, Library};
use bml_library::try_lock_worker;

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

fn text(bytes: &[u8]) -> String {
    String::from_utf8_lossy(bytes).into_owned()
}

/// A config folder with a library recorded (and no database).
fn with_library(cfg: &Path) -> Library {
    let library = Library {
        dir: cfg.join("library"),
    };
    ensure_library(cfg, &library).unwrap();
    library
}

#[test]
fn update_and_status_without_a_library_exit_2() {
    let cfg = tempfile::tempdir().unwrap();
    for args in [&["library", "update"][..], &["library", "status"]] {
        let out = bml(cfg.path(), args);
        let err = text(&out.stderr);
        assert_eq!(out.status.code(), Some(2), "{args:?}: {err}");
        assert!(err.contains("bml setup"), "{err}");
    }
}

#[test]
fn update_without_a_database_exits_2() {
    let cfg = tempfile::tempdir().unwrap();
    with_library(cfg.path());
    let out = bml(cfg.path(), &["library", "update"]);
    let err = text(&out.stderr);
    assert_eq!(out.status.code(), Some(2), "{err}");
    assert!(err.contains("No database"), "{err}");
}

#[test]
fn a_second_update_exits_quietly_while_one_runs() {
    let cfg = tempfile::tempdir().unwrap();
    let library = with_library(cfg.path());
    let _held = try_lock_worker(&library.dir).unwrap().unwrap();
    let out = bml(cfg.path(), &["library", "update"]);
    assert_eq!(out.status.code(), Some(0), "{}", text(&out.stderr));
    assert!(
        text(&out.stdout).contains("already running"),
        "{}",
        text(&out.stdout)
    );
}

#[test]
fn a_bad_from_date_is_refused() {
    let cfg = tempfile::tempdir().unwrap();
    let out = bml(cfg.path(), &["library", "update", "--from", "2024-13-01"]);
    assert_eq!(out.status.code(), Some(2), "clap usage error");
}

#[test]
fn schedule_every_needs_a_number_of_days_in_range() {
    let cfg = tempfile::tempdir().unwrap();
    with_library(cfg.path());
    for days in ["0", "366", "x"] {
        let out = bml(cfg.path(), &["library", "schedule", "every", days]);
        assert_eq!(out.status.code(), Some(2), "{days}: clap usage error");
    }
}
