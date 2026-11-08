//! `bml setup` argument handling and the steps that need no network.

use std::process::{Command, Output};

fn bml(config_dir: &std::path::Path, args: &[&str], password: Option<&str>) -> Output {
    let mut cmd = Command::new(env!("CARGO_BIN_EXE_bml"));
    cmd.arg("--config-dir")
        .arg(config_dir)
        .args(args)
        .env_remove("BML_PG_SUPERUSER_PASSWORD");
    if let Some(p) = password {
        cmd.env("BML_PG_SUPERUSER_PASSWORD", p);
    }
    cmd.output().unwrap()
}

fn text(bytes: &[u8]) -> String {
    String::from_utf8_lossy(bytes).into_owned()
}

const SKIP_ALL: [&str; 10] = [
    "--skip",
    "database",
    "--skip",
    "autostart",
    "--skip",
    "ollama",
    "--skip",
    "models",
    "--skip",
    "embedding-model",
];

#[test]
fn existing_server_needs_superuser() {
    let cfg = tempfile::tempdir().unwrap();
    let out = bml(
        cfg.path(),
        &["setup", "--existing-server", "127.0.0.1:5432"],
        None,
    );
    let err = text(&out.stderr);
    assert_eq!(out.status.code(), Some(2), "{err}");
    assert!(err.contains("--pg-superuser"), "{err}");
}

#[test]
fn existing_server_password_not_in_argv() {
    let cfg = tempfile::tempdir().unwrap();
    let out = bml(
        cfg.path(),
        &[
            "setup",
            "--existing-server",
            "127.0.0.1:5432",
            "--pg-superuser",
            "postgres",
        ],
        None,
    );
    assert_eq!(out.status.code(), Some(1));
    assert!(text(&out.stderr).contains("BML_PG_SUPERUSER_PASSWORD"));
}

#[test]
fn pg_bindir_conflicts_with_existing_server() {
    let cfg = tempfile::tempdir().unwrap();
    let out = bml(
        cfg.path(),
        &[
            "setup",
            "--existing-server",
            "127.0.0.1:5432",
            "--pg-superuser",
            "postgres",
            "--pg-bindir",
            "/x",
        ],
        Some("pw"),
    );
    let err = text(&out.stderr);
    assert_eq!(out.status.code(), Some(2), "{err}");
    assert!(
        err.contains("--pg-bindir") && err.contains("--existing-server"),
        "{err}"
    );
}

#[test]
fn data_and_extension_dirs_need_pg_bindir() {
    let cfg = tempfile::tempdir().unwrap();
    for flag in ["--data-dir", "--extension-dir"] {
        let out = bml(cfg.path(), &["setup", flag, "/x"], None);
        assert_eq!(out.status.code(), Some(2), "{flag}");
        assert!(text(&out.stderr).contains("--pg-bindir"), "{flag}");
    }
}

#[test]
fn remote_existing_server_refused() {
    let cfg = tempfile::tempdir().unwrap();
    let args = vec![
        "setup",
        "--existing-server",
        "db.example:5432",
        "--pg-superuser",
        "postgres",
        "--skip",
        "autostart",
        "--skip",
        "ollama",
        "--skip",
        "models",
        "--skip",
        "embedding-model",
    ];
    let out = bml(cfg.path(), &args, Some("pw"));
    assert_eq!(out.status.code(), Some(1));
    let err = text(&out.stderr);
    assert!(err.contains("must run on this computer"), "{err}");
    // Refused before any step ran.
    let so = text(&out.stdout);
    assert!(!so.contains("Hardware check"), "{so}");
    assert_eq!(std::fs::read_dir(cfg.path()).unwrap().count(), 0);
}

#[test]
fn empty_stdin_password_refused_before_any_step() {
    use std::io::Write as _;
    let cfg = tempfile::tempdir().unwrap();
    let mut child = Command::new(env!("CARGO_BIN_EXE_bml"))
        .arg("--config-dir")
        .arg(cfg.path())
        .args([
            "setup",
            "--existing-server",
            "127.0.0.1:5432",
            "--pg-superuser",
            "postgres",
            "--password-stdin",
        ])
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .unwrap();
    child.stdin.take().unwrap().write_all(b"\n").unwrap();
    let out = child.wait_with_output().unwrap();
    assert_eq!(out.status.code(), Some(1));
    let err = text(&out.stderr);
    assert!(err.contains("password cannot be stored"), "{err}");
    assert!(!text(&out.stdout).contains("Hardware check"));
}

#[test]
fn skip_all_but_hardware_succeeds() {
    let cfg = tempfile::tempdir().unwrap();
    let mut args = vec!["setup"];
    args.extend(SKIP_ALL);
    let out = bml(cfg.path(), &args, None);
    let so = text(&out.stdout);
    assert_eq!(out.status.code(), Some(0), "{so}{}", text(&out.stderr));
    for label in [
        "Hardware check",
        "Database",
        "Start at login",
        "Ollama",
        "Language models",
        "Embedding model",
    ] {
        assert!(so.contains(label), "missing {label}: {so}");
    }
    assert_eq!(std::fs::read_dir(cfg.path()).unwrap().count(), 0);
}
