//! Installing and starting Ollama from pinned, checksum-verified installers.

use std::ffi::OsString;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

use bmlib::publications::fetchers::registry::HttpClient;

use crate::ollama::{ollama_answer, ollama_version, OllamaHost};
use crate::{SetupError, StepEvent, StepId, StepOutcome};

/// The pinned Ollama release, as a literal so `concat!` can use it.
macro_rules! pinned_ollama_version {
    () => {
        "0.40.10"
    };
}
/// The Ollama release setup installs.
pub const OLLAMA_VERSION: &str = pinned_ollama_version!();
/// Where the pinned release's files are downloaded from.
const RELEASE_BASE_URL: &str = concat!(
    "https://github.com/ollama/ollama/releases/download/v",
    pinned_ollama_version!(),
    "/"
);
/// How often to ask a starting Ollama whether it answers.
pub const OLLAMA_POLL_INTERVAL: Duration = Duration::from_secs(1);
/// How long to wait for Ollama to answer after install or start.
pub const OLLAMA_START_TIMEOUT: Duration = Duration::from_secs(120);
/// How many closing lines of a failed program's stderr go in the error.
const STDERR_TAIL_LINES: usize = 4;
/// Where setup keeps downloads, under the config folder.
const DOWNLOADS_DIR: &str = "downloads";
/// The per-user applications folder on macOS, under the home folder.
#[cfg(target_os = "macos")]
const USER_APPS_DIR: &str = "Applications";
/// The machine-wide applications folder on macOS.
#[cfg(target_os = "macos")]
const SYSTEM_APPS_DIR: &str = "/Applications";
/// Ollama's app bundle on macOS, inside an applications folder.
#[cfg(target_os = "macos")]
const OLLAMA_APP_BUNDLE: &str = "Ollama.app";
/// Folder in the applications folder that the zip is unpacked into before
/// the app is moved into place, so a failed unpack leaves no partial app.
#[cfg(target_os = "macos")]
const EXTRACT_STAGING_DIR: &str = ".bml-ollama-extract";
/// Ollama's app on Windows, under `%LOCALAPPDATA%` (per-user install).
#[cfg(windows)]
const WINDOWS_USER_OLLAMA_APP: &str = "Programs/Ollama/ollama app.exe";
/// Ollama's app on Windows, under `%ProgramFiles%` (machine-wide install).
#[cfg(windows)]
const WINDOWS_SYSTEM_OLLAMA_APP: &str = "Ollama/ollama app.exe";
/// File name of the `ollama` command on the program search path.
const OLLAMA_COMMAND: &str = if cfg!(windows) {
    "ollama.exe"
} else {
    "ollama"
};
/// Windows' per-user program data folder variable.
const LOCAL_APP_DATA_ENV: &str = "LOCALAPPDATA";
/// Windows' machine-wide programs folder variable.
const PROGRAM_FILES_ENV: &str = "ProgramFiles";
/// The program search path variable.
const PATH_ENV: &str = "PATH";

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

/// A call of `program` with `args` and no extra environment.
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
/// On macOS they unpack into a staging folder; [`ensure_ollama`] then moves
/// the app into `~/Applications` and starts it.
#[must_use]
pub fn install_calls(downloaded: &Path, home: &Path) -> Vec<ProgramCall> {
    #[cfg(target_os = "macos")]
    {
        let staging = home.join(USER_APPS_DIR).join(EXTRACT_STAGING_DIR);
        vec![call(
            "ditto",
            &[
                "-x".as_ref(),
                "-k".as_ref(),
                downloaded.as_os_str(),
                staging.as_os_str(),
            ],
        )]
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

/// Where this platform's Ollama app may be installed, preferred first: the
/// per-user place, then the machine-wide one (none on Linux).
#[must_use]
pub fn app_candidates(
    home: &Path,
    local_app_data: Option<&Path>,
    program_files: Option<&Path>,
) -> Vec<PathBuf> {
    #[cfg(target_os = "macos")]
    {
        let _ = (local_app_data, program_files);
        vec![
            home.join(USER_APPS_DIR).join(OLLAMA_APP_BUNDLE),
            Path::new(SYSTEM_APPS_DIR).join(OLLAMA_APP_BUNDLE),
        ]
    }
    #[cfg(windows)]
    {
        let _ = home;
        [
            local_app_data.map(|d| d.join(WINDOWS_USER_OLLAMA_APP)),
            program_files.map(|d| d.join(WINDOWS_SYSTEM_OLLAMA_APP)),
        ]
        .into_iter()
        .flatten()
        .collect()
    }
    #[cfg(not(any(target_os = "macos", windows)))]
    {
        let _ = (home, local_app_data, program_files);
        vec![]
    }
}

/// Where Ollama is already installed: the first of `candidates` that exists,
/// else an `ollama` command on `path_var` (Homebrew, Linux, a manual install).
#[must_use]
pub fn installed_app(
    candidates: &[PathBuf],
    path_var: Option<&std::ffi::OsStr>,
) -> Option<PathBuf> {
    candidates.iter().find(|p| p.exists()).cloned().or_else(|| {
        std::env::split_paths(path_var?)
            .map(|d| d.join(OLLAMA_COMMAND))
            .find(|p| p.is_file())
    })
}

/// Programs that start the installed Ollama `app`; `None` for an `ollama`
/// command, which setup does not run as a background service itself.
#[must_use]
pub fn start_calls(app: &Path) -> Option<Vec<ProgramCall>> {
    if app.file_name() == Some(OLLAMA_COMMAND.as_ref()) {
        return None;
    }
    #[cfg(target_os = "macos")]
    return Some(vec![call("open", &["-g".as_ref(), app.as_os_str()])]);
    #[cfg(windows)]
    return Some(vec![call(app, &[])]);
    #[cfg(not(any(target_os = "macos", windows)))]
    None
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

/// The last [`STDERR_TAIL_LINES`] lines of `text`.
fn last_lines(text: &str) -> String {
    let lines: Vec<&str> = text.lines().collect();
    lines[lines.len().saturating_sub(STDERR_TAIL_LINES)..].join("\n")
}

/// Run `c`. With `wait`, wait for it and fail with its stderr tail on a
/// non-zero exit; without, only check that it started (output discarded).
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
    let detail = match ollama_answer(http, host)? {
        Ok(_) => return Ok(StepOutcome::AlreadyPresent),
        Err(detail) => detail,
    };
    if !host.loopback {
        return Err(SetupError::NotLoopback {
            host: host.base_url.clone(),
            detail,
        });
    }
    let step = StepId::Ollama;
    report(StepEvent::Notice {
        step,
        message: format!("Ollama at {} did not answer ({detail}).", host.base_url),
    });
    let home = dirs_home()?;
    let env_dir = |var| std::env::var_os(var).map(PathBuf::from);
    let candidates = app_candidates(
        &home,
        env_dir(LOCAL_APP_DATA_ENV).as_deref(),
        env_dir(PROGRAM_FILES_ENV).as_deref(),
    );
    let path_var = std::env::var_os(PATH_ENV);
    let installed = || installed_app(&candidates, path_var.as_deref());
    if let Some(app) = installed() {
        start(http, host, &app)?;
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
    let _lock = crate::lock_downloads(config_dir)?;
    // Another setup may have installed it while this one waited.
    if let Some(app) = installed() {
        start(http, host, &app)?;
        return Ok(StepOutcome::Started);
    }
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
    let staging = {
        let apps = home.join(USER_APPS_DIR);
        std::fs::create_dir_all(&apps).map_err(|source| SetupError::Io {
            path: apps.clone(),
            source,
        })?;
        let staging = apps.join(EXTRACT_STAGING_DIR);
        remove_dir_if_present(&staging)?;
        staging
    };
    for c in install_calls(&file, &home) {
        run_call(&c, true)?;
    }
    let mut warnings = Vec::new();
    #[cfg(target_os = "macos")]
    let app = {
        let app = home.join(USER_APPS_DIR).join(OLLAMA_APP_BUNDLE);
        warnings.extend(place_unpacked_app(&staging, &app)?);
        app
    };
    // Deleted only once the app is in place, so a failed move can reuse it.
    // Up to 1.6 GB that is no longer needed; a leftover only costs space.
    match std::fs::remove_file(&file) {
        Ok(()) => {}
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {}
        Err(e) => warnings.push(format!(
            "Ollama is installed, but its installer {} could not be deleted ({e}); delete it to free the space.",
            file.display()
        )),
    }
    #[cfg(target_os = "macos")]
    start(http, host, &app)?;
    #[cfg(not(target_os = "macos"))]
    wait_until_running(http, host, OLLAMA_START_TIMEOUT)?;
    Ok(crate::report_warnings(
        step,
        warnings,
        StepOutcome::Installed,
        report,
    ))
}

/// Move the app bundle `ditto` unpacked into `staging` to `app`, then
/// delete `staging`; a staging folder left behind is only a warning.
#[cfg(target_os = "macos")]
fn place_unpacked_app(staging: &Path, app: &Path) -> Result<Option<String>, SetupError> {
    let unpacked = staging.join(OLLAMA_APP_BUNDLE);
    std::fs::rename(&unpacked, app).map_err(|source| SetupError::Io {
        path: unpacked.clone(),
        source,
    })?;
    Ok(match std::fs::remove_dir_all(staging) {
        Err(e) if e.kind() != std::io::ErrorKind::NotFound => Some(format!(
            "Ollama is installed, but the folder it was unpacked into, {}, could not be deleted ({e}); delete it to free the space.",
            staging.display()
        )),
        _ => None,
    })
}

/// Start the installed Ollama `app` and wait until it answers.
fn start(http: &dyn HttpClient, host: &OllamaHost, app: &Path) -> Result<(), SetupError> {
    let Some(calls) = start_calls(app) else {
        return Err(SetupError::Ollama {
            message: format!(
                "Ollama is installed ({}) but not running. Start it (for example `ollama serve`, `brew services start ollama`, or `sudo systemctl start ollama` where it runs as a system service), then run `bml setup` again.",
                app.display()
            ),
        });
    };
    // macOS `open` returns at once, so wait for it to see a damaged app's
    // error; the Windows app keeps running, so only check that it started.
    for c in &calls {
        run_call(c, cfg!(target_os = "macos"))?;
    }
    wait_until_running(http, host, OLLAMA_START_TIMEOUT)?;
    Ok(())
}

/// Delete the folder `dir` and its contents; a missing one is fine.
#[cfg(target_os = "macos")]
fn remove_dir_if_present(dir: &Path) -> Result<(), SetupError> {
    match std::fs::remove_dir_all(dir) {
        Err(e) if e.kind() != std::io::ErrorKind::NotFound => Err(SetupError::Io {
            path: dir.to_path_buf(),
            source: e,
        }),
        _ => Ok(()),
    }
}

/// The home folder, from `USERPROFILE` on Windows and `HOME` elsewhere.
fn dirs_home() -> Result<PathBuf, SetupError> {
    let var = if cfg!(windows) { "USERPROFILE" } else { "HOME" };
    std::env::var_os(var)
        .map(PathBuf::from)
        .ok_or_else(|| SetupError::Other {
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
    fn installer_url_uses_the_pinned_version() {
        assert!(RELEASE_BASE_URL.contains(&format!("/v{OLLAMA_VERSION}/")));
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
            assert_eq!(calls.len(), 1);
            assert_eq!(calls[0].program, PathBuf::from("ditto"));
            assert_eq!(
                calls[0].args,
                [
                    "-x",
                    "-k",
                    "/dl/file",
                    "/home/u/Applications/.bml-ollama-extract"
                ]
            );
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
        // A command found on PATH is never started by setup.
        assert!(start_calls(&Path::new("/opt/bin").join(OLLAMA_COMMAND)).is_none());
    }

    #[test]
    fn app_candidates_list_user_then_machine_wide() {
        let c = app_candidates(
            Path::new("/home/u"),
            Some(Path::new("/local")),
            Some(Path::new("/pf")),
        );
        #[cfg(target_os = "macos")]
        assert_eq!(
            c,
            [
                PathBuf::from("/home/u/Applications/Ollama.app"),
                PathBuf::from("/Applications/Ollama.app")
            ]
        );
        #[cfg(windows)]
        assert_eq!(
            c,
            [
                Path::new("/local").join(WINDOWS_USER_OLLAMA_APP),
                Path::new("/pf").join(WINDOWS_SYSTEM_OLLAMA_APP)
            ]
        );
        #[cfg(not(any(target_os = "macos", windows)))]
        assert!(c.is_empty());
    }

    #[test]
    fn installed_app_order_and_absence() {
        let tmp = tempfile::tempdir().unwrap();
        let user = tmp.path().join("user/Ollama.app");
        let system = tmp.path().join("system/Ollama.app");
        let bin_dir = tmp.path().join("bin");
        let command = bin_dir.join(OLLAMA_COMMAND);
        let candidates = [user.clone(), system.clone()];
        let path = std::env::join_paths([&bin_dir]).unwrap();
        assert_eq!(installed_app(&candidates, Some(&path)), None);
        assert_eq!(installed_app(&candidates, None), None);
        std::fs::create_dir_all(&bin_dir).unwrap();
        std::fs::write(&command, "").unwrap();
        assert_eq!(installed_app(&candidates, Some(&path)), Some(command));
        std::fs::create_dir_all(&system).unwrap();
        assert_eq!(installed_app(&candidates, Some(&path)), Some(system));
        std::fs::create_dir_all(&user).unwrap();
        assert_eq!(installed_app(&candidates, Some(&path)), Some(user));
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

    #[cfg(target_os = "macos")]
    #[test]
    fn place_unpacked_app_moves_the_bundle_and_clears_staging() {
        let tmp = tempfile::tempdir().unwrap();
        let staging = tmp.path().join(EXTRACT_STAGING_DIR);
        let app = tmp.path().join(OLLAMA_APP_BUNDLE);
        std::fs::create_dir_all(staging.join(OLLAMA_APP_BUNDLE).join("Contents")).unwrap();
        assert_eq!(place_unpacked_app(&staging, &app).unwrap(), None);
        assert!(app.join("Contents").is_dir());
        assert!(!staging.exists());

        // A zip without Ollama.app at its top: the error names what is missing.
        std::fs::create_dir_all(staging.join("Other.app")).unwrap();
        let e = place_unpacked_app(&staging, &tmp.path().join("New.app")).unwrap_err();
        let text = e.to_string();
        assert!(
            text.contains(&staging.join(OLLAMA_APP_BUNDLE).display().to_string()),
            "{text}"
        );
    }
}
