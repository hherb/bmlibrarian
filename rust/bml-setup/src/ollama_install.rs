//! Installing and starting Ollama from pinned, checksum-verified installers.

use std::ffi::OsString;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

use bmlib::publications::fetchers::registry::HttpClient;

use crate::ollama::{ollama_version, OllamaHost};
use crate::{SetupError, StepEvent, StepId, StepOutcome};

/// The Ollama release setup installs.
pub const OLLAMA_VERSION: &str = "0.40.10";
/// Where the pinned release's files are downloaded from.
const RELEASE_BASE_URL: &str = "https://github.com/ollama/ollama/releases/download/v0.40.10/";
/// How often to ask a starting Ollama whether it answers.
pub const OLLAMA_POLL_INTERVAL: Duration = Duration::from_secs(1);
/// How long to wait for Ollama to answer after install or start.
pub const OLLAMA_START_TIMEOUT: Duration = Duration::from_secs(120);
/// How many closing lines of a failed program's stderr go in the error.
const STDERR_TAIL_LINES: usize = 4;
/// Where setup keeps downloads, under the config folder.
const DOWNLOADS_DIR: &str = "downloads";

/// The pinned installer file for this platform.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct InstallerAsset {
    /// File name in the release.
    pub file: &'static str,
    /// Exact size in bytes.
    pub size: u64,
    /// Lower-case hex SHA-256.
    pub sha256: &'static str,
}

/// A program to run, with extra environment.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProgramCall {
    /// The program.
    pub program: PathBuf,
    /// Its arguments.
    pub args: Vec<OsString>,
    /// Environment variables added to the inherited ones.
    pub env: Vec<(OsString, OsString)>,
}

fn call(program: impl Into<PathBuf>, args: &[&std::ffi::OsStr]) -> ProgramCall {
    ProgramCall {
        program: program.into(),
        args: args.iter().map(|a| (*a).to_os_string()).collect(),
        env: vec![],
    }
}

/// The installer for the platform this was built for.
#[must_use]
pub fn installer_asset() -> InstallerAsset {
    #[cfg(target_os = "macos")]
    return InstallerAsset {
        file: "Ollama-darwin.zip",
        size: 220_350_228,
        sha256: "0c8ac7dc394a7b6171d8531bdaba60dd8dd2d8ed525ebc6c4526a91497a029ee",
    };
    #[cfg(windows)]
    return InstallerAsset {
        file: "OllamaSetup.exe",
        size: 1_661_645_848,
        sha256: "051556bec8d51d65a5e81e46aa9c238fff4fff0d47ce164fb25203ae48ed1c99",
    };
    #[cfg(not(any(target_os = "macos", windows)))]
    InstallerAsset {
        file: "install.sh",
        size: 15_902,
        sha256: "25f64b810b947145095956533e1bdf56eacea2673c55a7e586be4515fc882c9f",
    }
}

/// Download URL of `asset` in the pinned release.
#[must_use]
pub fn installer_url(asset: &InstallerAsset) -> String {
    format!("{RELEASE_BASE_URL}{}", asset.file)
}

/// Programs that install the downloaded file. Pure.
// shortcut: the Windows Inno Setup flags are unverified; tick #397's Windows checklist.
#[must_use]
pub fn install_calls(downloaded: &Path, home: &Path) -> Vec<ProgramCall> {
    #[cfg(target_os = "macos")]
    {
        let apps = home.join("Applications");
        let app = apps.join("Ollama.app");
        vec![
            call(
                "ditto",
                &[
                    "-x".as_ref(),
                    "-k".as_ref(),
                    downloaded.as_os_str(),
                    apps.as_os_str(),
                ],
            ),
            call("open", &["-g".as_ref(), app.as_os_str()]),
        ]
    }
    #[cfg(windows)]
    {
        let _ = home;
        vec![call(
            downloaded,
            &[
                "/VERYSILENT".as_ref(),
                "/SUPPRESSMSGBOXES".as_ref(),
                "/NORESTART".as_ref(),
                "/SP-".as_ref(),
            ],
        )]
    }
    #[cfg(not(any(target_os = "macos", windows)))]
    {
        let _ = home;
        let mut c = call("sh", &[downloaded.as_os_str()]);
        c.env = vec![("OLLAMA_VERSION".into(), OLLAMA_VERSION.into())];
        vec![c]
    }
}

/// Where Ollama is already installed, if anywhere.
#[must_use]
pub fn installed_app(
    home: &Path,
    local_app_data: Option<&Path>,
    path_var: Option<&std::ffi::OsStr>,
) -> Option<PathBuf> {
    #[cfg(target_os = "macos")]
    {
        let _ = (local_app_data, path_var);
        [
            home.join("Applications/Ollama.app"),
            PathBuf::from("/Applications/Ollama.app"),
        ]
        .into_iter()
        .find(|p| p.exists())
    }
    #[cfg(windows)]
    {
        let _ = (home, path_var);
        Some(local_app_data?.join("Programs/Ollama/ollama app.exe")).filter(|p| p.exists())
    }
    #[cfg(not(any(target_os = "macos", windows)))]
    {
        let _ = (home, local_app_data);
        std::env::split_paths(path_var?)
            .map(|d| d.join("ollama"))
            .find(|p| p.is_file())
    }
}

/// Programs that start an installed Ollama; `None` where setup cannot (Linux).
#[must_use]
pub fn start_calls(app: &Path) -> Option<Vec<ProgramCall>> {
    #[cfg(target_os = "macos")]
    return Some(vec![call("open", &["-g".as_ref(), app.as_os_str()])]);
    #[cfg(windows)]
    return Some(vec![call(app, &[])]);
    #[cfg(not(any(target_os = "macos", windows)))]
    {
        let _ = app;
        None
    }
}

/// Poll until Ollama answers; returns its version.
pub fn wait_until_running(
    http: &dyn HttpClient,
    host: &OllamaHost,
    timeout: Duration,
) -> Result<String, SetupError> {
    let start = Instant::now();
    loop {
        if let Some(v) = ollama_version(http, host)? {
            return Ok(v);
        }
        if start.elapsed() >= timeout {
            return Err(SetupError::Ollama {
                message: format!(
                    "Ollama did not start within {} seconds. Open Ollama yourself, then run `bml setup` again.",
                    timeout.as_secs()
                ),
            });
        }
        std::thread::sleep(OLLAMA_POLL_INTERVAL);
    }
}

fn last_lines(text: &str) -> String {
    let lines: Vec<&str> = text.lines().collect();
    lines[lines.len().saturating_sub(STDERR_TAIL_LINES)..].join("\n")
}

fn run_call(c: &ProgramCall, wait: bool) -> Result<(), SetupError> {
    let name = c.program.display().to_string();
    let fail = |message: String| SetupError::Install {
        program: name.clone(),
        message,
    };
    let mut cmd = Command::new(&c.program);
    cmd.args(&c.args)
        .envs(c.env.iter().map(|(k, v)| (k, v)))
        .stdin(Stdio::null());
    if !wait {
        cmd.stdout(Stdio::null()).stderr(Stdio::null());
        return cmd.spawn().map(drop).map_err(|e| fail(e.to_string()));
    }
    let out = cmd.output().map_err(|e| fail(e.to_string()))?;
    if out.status.success() {
        return Ok(());
    }
    let tail = last_lines(&String::from_utf8_lossy(&out.stderr));
    Err(fail(format!("{}: {tail}", out.status)))
}

/// Make sure Ollama is running: use it, start it, or install and start it.
pub fn ensure_ollama(
    http: &dyn HttpClient,
    host: &OllamaHost,
    config_dir: &Path,
    report: &mut dyn FnMut(StepEvent),
) -> Result<StepOutcome, SetupError> {
    if ollama_version(http, host)?.is_some() {
        return Ok(StepOutcome::AlreadyPresent);
    }
    if !host.loopback {
        return Err(SetupError::NotLoopback {
            host: host.base_url.clone(),
        });
    }
    let step = StepId::Ollama;
    let home = dirs_home()?;
    let local = std::env::var_os("LOCALAPPDATA").map(PathBuf::from);
    let path_var = std::env::var_os("PATH");
    if let Some(app) = installed_app(&home, local.as_deref(), path_var.as_deref()) {
        let Some(calls) = start_calls(&app) else {
            return Err(SetupError::Ollama {
                message: "Ollama is installed but not running. Start it with `sudo systemctl start ollama`, then run `bml setup` again.".into(),
            });
        };
        for c in &calls {
            run_call(c, false)?;
        }
        wait_until_running(http, host, OLLAMA_START_TIMEOUT)?;
        return Ok(StepOutcome::Started);
    }
    #[cfg(not(any(target_os = "macos", windows)))]
    report(StepEvent::Notice {
        step,
        message: "Ollama's install script will ask for your password (sudo). It also downloads Ollama's own files, which setup cannot checksum; only the script itself is verified.".into(),
    });
    let asset = installer_asset();
    let dir = config_dir.join(DOWNLOADS_DIR);
    std::fs::create_dir_all(&dir).map_err(|source| SetupError::Io {
        path: dir.clone(),
        source,
    })?;
    crate::sweep_stale_parts(&dir, asset.file)?;
    let file = bmlib::embed::download_verified(
        &installer_url(&asset),
        asset.file,
        asset.size,
        asset.sha256,
        &dir,
        &mut |done, total| {
            report(StepEvent::Progress {
                step,
                detail: "Downloading Ollama".into(),
                done,
                total,
            });
            true
        },
    )?;
    #[cfg(target_os = "macos")]
    {
        let apps = home.join("Applications");
        std::fs::create_dir_all(&apps).map_err(|source| SetupError::Io { path: apps, source })?;
    }
    for c in install_calls(&file, &home) {
        run_call(&c, true)?;
    }
    // Up to 1.6 GB that is no longer needed.
    match std::fs::remove_file(&file) {
        Ok(()) => {}
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {}
        Err(source) => return Err(SetupError::Io { path: file, source }),
    }
    wait_until_running(http, host, OLLAMA_START_TIMEOUT)?;
    Ok(StepOutcome::Installed)
}

fn dirs_home() -> Result<PathBuf, SetupError> {
    let var = if cfg!(windows) { "USERPROFILE" } else { "HOME" };
    std::env::var_os(var)
        .map(PathBuf::from)
        .ok_or_else(|| SetupError::Ollama {
            message: format!(
                "The {var} environment variable is not set, so setup cannot find your home folder."
            ),
        })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::test_support::Fake;

    #[test]
    fn installer_asset_matches_pins() {
        let a = installer_asset();
        #[cfg(target_os = "macos")]
        assert_eq!(
            (a.file, a.size, a.sha256),
            (
                "Ollama-darwin.zip",
                220_350_228,
                "0c8ac7dc394a7b6171d8531bdaba60dd8dd2d8ed525ebc6c4526a91497a029ee"
            )
        );
        #[cfg(windows)]
        assert_eq!(
            (a.file, a.size, a.sha256),
            (
                "OllamaSetup.exe",
                1_661_645_848,
                "051556bec8d51d65a5e81e46aa9c238fff4fff0d47ce164fb25203ae48ed1c99"
            )
        );
        #[cfg(not(any(target_os = "macos", windows)))]
        assert_eq!(
            (a.file, a.size, a.sha256),
            (
                "install.sh",
                15_902,
                "25f64b810b947145095956533e1bdf56eacea2673c55a7e586be4515fc882c9f"
            )
        );
    }

    #[test]
    fn installer_url_is_pinned_release() {
        let a = installer_asset();
        assert_eq!(
            installer_url(&a),
            format!(
                "https://github.com/ollama/ollama/releases/download/v0.40.10/{}",
                a.file
            )
        );
    }

    #[test]
    fn install_calls_shape() {
        let calls = install_calls(Path::new("/dl/file"), Path::new("/home/u"));
        #[cfg(target_os = "macos")]
        {
            assert_eq!(calls.len(), 2);
            assert_eq!(calls[0].program, PathBuf::from("ditto"));
            assert_eq!(
                calls[0].args,
                ["-x", "-k", "/dl/file", "/home/u/Applications"]
            );
            assert_eq!(calls[1].program, PathBuf::from("open"));
            assert_eq!(calls[1].args, ["-g", "/home/u/Applications/Ollama.app"]);
        }
        #[cfg(windows)]
        {
            assert_eq!(calls.len(), 1);
            assert_eq!(calls[0].program, PathBuf::from("/dl/file"));
            assert_eq!(
                calls[0].args,
                ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-"]
            );
        }
        #[cfg(not(any(target_os = "macos", windows)))]
        {
            assert_eq!(calls.len(), 1);
            assert_eq!(calls[0].program, PathBuf::from("sh"));
            assert_eq!(calls[0].args, ["/dl/file"]);
            assert_eq!(
                calls[0].env,
                [(OsString::from("OLLAMA_VERSION"), OsString::from("0.40.10"))]
            );
        }
    }

    #[test]
    fn start_calls_shape() {
        let c = start_calls(Path::new("/x/Ollama.app"));
        #[cfg(target_os = "macos")]
        assert_eq!(c.unwrap()[0].args, ["-g", "/x/Ollama.app"]);
        #[cfg(windows)]
        assert_eq!(c.unwrap()[0].program, PathBuf::from("/x/Ollama.app"));
        #[cfg(not(any(target_os = "macos", windows)))]
        assert!(c.is_none());
    }

    #[cfg(target_os = "macos")]
    #[test]
    fn installed_app_prefers_user_applications() {
        let home = tempfile::tempdir().unwrap();
        let user_app = home.path().join("Applications/Ollama.app");
        std::fs::create_dir_all(&user_app).unwrap();
        assert_eq!(installed_app(home.path(), None, None), Some(user_app));
    }

    #[cfg(not(any(target_os = "macos", windows)))]
    #[test]
    fn installed_app_finds_ollama_on_path() {
        let dir = tempfile::tempdir().unwrap();
        let bin = dir.path().join("ollama");
        std::fs::write(&bin, "").unwrap();
        let path = std::env::join_paths([dir.path()]).unwrap();
        assert_eq!(installed_app(Path::new("/h"), None, Some(&path)), Some(bin));
        assert_eq!(installed_app(Path::new("/h"), None, None), None);
    }

    #[test]
    fn tail_keeps_last_lines() {
        assert_eq!(last_lines("a\nb\nc\nd\ne\nf\n"), "c\nd\ne\nf");
    }

    #[test]
    fn wait_until_running_times_out() {
        let f = Fake::new();
        let host = crate::ollama::parse_ollama_host(None).unwrap();
        let e = wait_until_running(&f, &host, Duration::ZERO).unwrap_err();
        assert!(e.to_string().contains("did not start"), "{e}");
    }

    #[test]
    fn wait_until_running_returns_version() {
        let mut f = Fake::new();
        f.get = Ok((200, r#"{"version":"0.40.10"}"#.into()));
        let host = crate::ollama::parse_ollama_host(None).unwrap();
        assert_eq!(
            wait_until_running(&f, &host, Duration::ZERO).unwrap(),
            "0.40.10"
        );
    }

    #[test]
    fn ensure_running_is_already_present() {
        let mut f = Fake::new();
        f.get = Ok((200, r#"{"version":"0.40.10"}"#.into()));
        let host = crate::ollama::parse_ollama_host(None).unwrap();
        let out = ensure_ollama(&f, &host, Path::new("/nonexistent"), &mut |_| {}).unwrap();
        assert_eq!(out, crate::StepOutcome::AlreadyPresent);
    }

    #[test]
    fn ensure_remote_host_refuses() {
        let f = Fake::new();
        let host = crate::ollama::parse_ollama_host(Some("gpu-box")).unwrap();
        let e = ensure_ollama(&f, &host, Path::new("/nonexistent"), &mut |_| {}).unwrap_err();
        assert!(matches!(e, SetupError::NotLoopback { .. }), "{e}");
    }
}
