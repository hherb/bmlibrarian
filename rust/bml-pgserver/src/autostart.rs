//! Starting the private server once at user login, without admin rights.
//!
//! macOS: a per-user LaunchAgent (enabling it also starts the server right
//! away). Linux: a `systemd --user` unit, which also stops the server when
//! the user's session manager stops at logout. Windows: the per-user `Run`
//! registry key (a logon Scheduled Task needs admin rights).
//! Nothing keeps the server alive or restarts it, so an import-profile
//! restart never fights a supervisor.
//!
//! There is one entry per user: enabling for another configuration folder
//! replaces it. The entry records the running `bml` executable, so enable it
//! from an installed `bml`, not a `cargo run` build that may move.

use std::ffi::OsString;
#[cfg(any(target_os = "macos", target_os = "linux"))]
use std::fs;
use std::path::Path;
#[cfg(any(target_os = "macos", target_os = "linux"))]
use std::path::PathBuf;
#[cfg(any(target_os = "macos", target_os = "linux", windows))]
use std::process::Command;

#[cfg(any(target_os = "macos", target_os = "linux", windows))]
use crate::control::run;
#[cfg(any(target_os = "macos", target_os = "linux"))]
use crate::error::file_error;
use crate::error::PgServerError;

/// The LaunchAgent label (macOS).
pub const LAUNCH_AGENT_LABEL: &str = "org.bmlibrarian.pgserver";

/// The `systemd --user` unit name (Linux).
pub const SYSTEMD_UNIT_NAME: &str = "bml-pgserver.service";

/// The user's systemd unit folder, relative to the home folder (Linux).
#[cfg(target_os = "linux")]
const SYSTEMD_USER_DIR: &str = ".config/systemd/user";

/// The folder `systemctl --user enable` links the unit into (the unit has
/// `WantedBy=default.target`), relative to [`SYSTEMD_USER_DIR`].
#[cfg(any(target_os = "linux", test))]
const SYSTEMD_WANTS_DIR: &str = "default.target.wants";

/// The value name under the per-user `Run` key (Windows).
pub const WINDOWS_RUN_VALUE: &str = "BMLibrarianPgServer";

/// Where the macOS login start writes its output, in the configuration
/// folder (launchd would otherwise discard it).
pub const AUTOSTART_LOG_NAME: &str = "bml-autostart.log";

/// `launchctl bootout` exit codes that mean the job was not loaded (ESRCH,
/// "could not find service", or 112 "could not find domain", as over SSH
/// without a GUI login) or is already unloading (EINPROGRESS).
#[cfg(any(target_os = "macos", test))]
const BOOTOUT_NOT_LOADED_CODES: [i32; 4] = [3, 113, 112, 36];

/// `launchctl bootstrap` exit code for "Input/output error", which it
/// returns while a job just booted out is still being unloaded.
#[cfg(any(target_os = "macos", test))]
const BOOTSTRAP_BUSY_CODE: i32 = 5;

/// How many times a busy `bootstrap` is retried (10 × 200 ms = 2 s).
#[cfg(any(target_os = "macos", test))]
const BOOTSTRAP_RETRIES: u32 = 10;
/// The wait between `bootstrap` retries.
#[cfg(target_os = "macos")]
const BOOTSTRAP_RETRY_DELAY: std::time::Duration = std::time::Duration::from_millis(200);

/// The per-user `Run` registry key (Windows).
pub const WINDOWS_RUN_KEY: &str = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run";

/// The command that starts the server: `bml --config-dir <dir> server <action>`.
fn bml_args(exe: &Path, config_dir: &Path, action: &str) -> Vec<OsString> {
    vec![
        exe.as_os_str().to_owned(),
        "--config-dir".into(),
        config_dir.as_os_str().to_owned(),
        "server".into(),
        action.into(),
    ]
}

/// The login command: `bml --config-dir <dir> server start`.
pub fn start_args(exe: &Path, config_dir: &Path) -> Vec<OsString> {
    bml_args(exe, config_dir, "start")
}

/// `text` with the five XML special characters escaped.
fn xml_escape(text: &str) -> String {
    text.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&apos;")
}

/// The LaunchAgent plist: runs the start command once at login, logging to
/// [`AUTOSTART_LOG_NAME`] in `config_dir`.
pub fn render_launch_agent(exe: &Path, config_dir: &Path) -> String {
    let log = xml_escape(&config_dir.join(AUTOSTART_LOG_NAME).to_string_lossy());
    let args: String = start_args(exe, config_dir)
        .iter()
        .map(|a| {
            format!(
                "        <string>{}</string>\n",
                xml_escape(&a.to_string_lossy())
            )
        })
        .collect();
    format!(
        r#"<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LAUNCH_AGENT_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
{args}    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{log}</string>
    <key>StandardErrorPath</key>
    <string>{log}</string>
</dict>
</plist>
"#
    )
}

/// One argument as a double-quoted systemd command-line word (systemd
/// expands `%` specifiers and `$` variables even inside quotes).
fn systemd_quote(arg: &OsString) -> String {
    let text = arg
        .to_string_lossy()
        .replace('\\', "\\\\")
        .replace('"', "\\\"")
        .replace('%', "%%")
        .replace('$', "$$");
    format!("\"{text}\"")
}

/// The `systemd --user` unit: starts once at login, stops at logout.
pub fn render_systemd_unit(exe: &Path, config_dir: &Path) -> String {
    let line = |action: &str| {
        bml_args(exe, config_dir, action)
            .iter()
            .map(systemd_quote)
            .collect::<Vec<_>>()
            .join(" ")
    };
    format!(
        "[Unit]\nDescription=BMLibrarian private PostgreSQL server\n\n\
         [Service]\nType=oneshot\nRemainAfterExit=yes\nExecStart={}\nExecStop={}\n\n\
         [Install]\nWantedBy=default.target\n",
        line("start"),
        line("stop")
    )
}

/// `arg` double-quoted for a Windows command line. Windows paths cannot
/// contain `"`, but trailing backslashes (`D:\`) must be doubled, or the
/// closing quote would read as an escaped one.
fn windows_quote(arg: &OsString) -> String {
    let text = arg.to_string_lossy();
    let trailing = text.len() - text.trim_end_matches('\\').len();
    format!("\"{text}{}\"", "\\".repeat(trailing))
}

/// The command stored under the Windows `Run` key, every argument quoted.
pub fn windows_run_command(exe: &Path, config_dir: &Path) -> String {
    start_args(exe, config_dir)
        .iter()
        .map(windows_quote)
        .collect::<Vec<_>>()
        .join(" ")
}

/// The user's home folder.
#[cfg(any(target_os = "macos", target_os = "linux"))]
fn home() -> Result<PathBuf, PgServerError> {
    std::env::home_dir().ok_or_else(|| {
        PgServerError::Io(std::io::Error::other(
            "cannot find the home directory, where the login start entry is kept",
        ))
    })
}

/// Where the LaunchAgent plist lives.
#[cfg(target_os = "macos")]
fn launch_agent_path() -> Result<PathBuf, PgServerError> {
    Ok(home()?
        .join("Library/LaunchAgents")
        .join(format!("{LAUNCH_AGENT_LABEL}.plist")))
}

/// The `gui/<uid>` launchd domain of the current user.
#[cfg(target_os = "macos")]
fn launchd_domain() -> Result<String, PgServerError> {
    let mut id = Command::new("id");
    id.arg("-u");
    let output = run(id)?;
    Ok(format!(
        "gui/{}",
        String::from_utf8_lossy(&output.stdout).trim()
    ))
}

/// Whether a `launchctl bootout` exit code means the job is (being) gone.
#[cfg(any(target_os = "macos", test))]
fn bootout_succeeded(code: Option<i32>) -> bool {
    code.is_some_and(|c| c == 0 || BOOTOUT_NOT_LOADED_CODES.contains(&c))
}

/// Unload our LaunchAgent from `domain`; not being loaded is fine.
#[cfg(target_os = "macos")]
fn bootout(domain: &str) -> Result<(), PgServerError> {
    let output = Command::new("launchctl")
        .arg("bootout")
        .arg(format!("{domain}/{LAUNCH_AGENT_LABEL}"))
        .output()
        .map_err(|source| PgServerError::Spawn {
            program: "launchctl".into(),
            source,
        })?;
    if bootout_succeeded(output.status.code()) {
        Ok(())
    } else {
        Err(PgServerError::Command {
            program: "launchctl bootout".to_owned(),
            status: output.status.code(),
            stderr: String::from_utf8_lossy(&output.stderr).trim().to_owned(),
        })
    }
}

/// Load `plist` into `domain`, retrying while a previous load of the job is
/// still being unloaded (`bootout` returns before it finishes).
#[cfg(target_os = "macos")]
fn bootstrap(domain: &str, plist: &Path) -> Result<(), PgServerError> {
    retry_while_busy(BOOTSTRAP_RETRY_DELAY, || {
        let mut command = Command::new("launchctl");
        command.arg("bootstrap").arg(domain).arg(plist);
        run(command).map(drop)
    })
}

/// Run `attempt`, repeating it after `delay` while it fails with
/// [`BOOTSTRAP_BUSY_CODE`], at most [`BOOTSTRAP_RETRIES`] times; the last
/// result is returned unchanged.
#[cfg(any(target_os = "macos", test))]
fn retry_while_busy(
    delay: std::time::Duration,
    mut attempt: impl FnMut() -> Result<(), PgServerError>,
) -> Result<(), PgServerError> {
    let mut retries = 0;
    loop {
        match attempt() {
            Err(PgServerError::Command {
                status: Some(BOOTSTRAP_BUSY_CODE),
                ..
            }) if retries < BOOTSTRAP_RETRIES => {
                retries += 1;
                std::thread::sleep(delay);
            }
            other => return other,
        }
    }
}

/// Start the server at every login of this user (on macOS, also now).
pub fn enable(exe: &Path, config_dir: &Path) -> Result<(), PgServerError> {
    #[cfg(target_os = "macos")]
    {
        let plist = launch_agent_path()?;
        let domain = launchd_domain()?;
        // Unload a previous registration first, so enable can be repeated;
        // before writing, so a failure leaves no new login entry behind.
        bootout(&domain)?;
        let agents = plist.parent().expect("plist path has a parent");
        fs::create_dir_all(agents).map_err(file_error(agents))?;
        fs::write(&plist, render_launch_agent(exe, config_dir)).map_err(file_error(&plist))?;
        let loaded = bootstrap(&domain, &plist);
        if loaded.is_err() {
            // Not enabled after all, so no login entry either; best effort,
            // as the bootstrap error is the one to report.
            let _ = fs::remove_file(&plist);
        }
        loaded
    }
    #[cfg(target_os = "linux")]
    {
        let unit_dir = home()?.join(SYSTEMD_USER_DIR);
        let unit = unit_dir.join(SYSTEMD_UNIT_NAME);
        fs::create_dir_all(&unit_dir).map_err(file_error(&unit_dir))?;
        fs::write(&unit, render_systemd_unit(exe, config_dir)).map_err(file_error(&unit))?;
        let enabled = (|| {
            let mut reload = Command::new("systemctl");
            reload.args(["--user", "daemon-reload"]);
            run(reload)?;
            let mut enable = Command::new("systemctl");
            enable.args(["--user", "enable", SYSTEMD_UNIT_NAME]);
            run(enable).map(drop)
        })();
        if enabled.is_err() {
            // Not enabled after all, so no unit file either (as on macOS);
            // best effort, the systemctl error is the one to report.
            let _ = fs::remove_file(&unit);
        }
        enabled
    }
    #[cfg(windows)]
    {
        let mut reg = Command::new("reg");
        reg.args([
            "add",
            WINDOWS_RUN_KEY,
            "/v",
            WINDOWS_RUN_VALUE,
            "/t",
            "REG_SZ",
            "/d",
        ])
        .arg(windows_run_command(exe, config_dir))
        .arg("/f");
        run(reg).map(drop)
    }
    #[cfg(not(any(target_os = "macos", target_os = "linux", windows)))]
    {
        let _ = (exe, config_dir);
        Err(PgServerError::Io(std::io::Error::other(
            "autostart is not supported on this platform",
        )))
    }
}

/// Whether the file at `path` exists with exactly the text `expected`.
#[cfg(any(target_os = "macos", target_os = "linux", test))]
fn file_has_text(path: &Path, expected: &str) -> Result<bool, PgServerError> {
    match std::fs::read_to_string(path) {
        Ok(text) => Ok(text == expected),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(false),
        Err(e) => Err(PgServerError::File {
            path: path.to_owned(),
            source: e,
        }),
    }
}

/// Whether the unit in `unit_dir` matches `expected` and `systemctl enable`
/// linked it into the wants folder (a unit file alone is a failed enable).
#[cfg(any(target_os = "linux", test))]
fn systemd_enabled(unit_dir: &Path, expected: &str) -> Result<bool, PgServerError> {
    let link = unit_dir.join(SYSTEMD_WANTS_DIR).join(SYSTEMD_UNIT_NAME);
    Ok(file_has_text(&unit_dir.join(SYSTEMD_UNIT_NAME), expected)?
        && link.symlink_metadata().is_ok())
}

/// Whether `reg query` output (`    NAME    REG_SZ    VALUE`) holds `command`.
#[cfg(any(windows, test))]
fn reg_output_has(stdout: &str, command: &str) -> bool {
    stdout
        .lines()
        .filter_map(|l| l.split_once("REG_SZ"))
        .any(|(_, value)| value.trim() == command)
}

/// Whether the login entry exists and is exactly what [`enable`] would write
/// for `exe` and `config_dir`.
pub fn is_enabled(exe: &Path, config_dir: &Path) -> Result<bool, PgServerError> {
    #[cfg(target_os = "macos")]
    {
        file_has_text(&launch_agent_path()?, &render_launch_agent(exe, config_dir))
    }
    #[cfg(target_os = "linux")]
    {
        systemd_enabled(
            &home()?.join(SYSTEMD_USER_DIR),
            &render_systemd_unit(exe, config_dir),
        )
    }
    #[cfg(windows)]
    {
        let out = Command::new("reg")
            .args(["query", WINDOWS_RUN_KEY, "/v", WINDOWS_RUN_VALUE])
            .output()
            .map_err(|source| PgServerError::Spawn {
                program: "reg".into(),
                source,
            })?;
        Ok(out.status.success()
            && reg_output_has(
                &String::from_utf8_lossy(&out.stdout),
                &windows_run_command(exe, config_dir),
            ))
    }
    #[cfg(not(any(target_os = "macos", target_os = "linux", windows)))]
    {
        let _ = (exe, config_dir);
        Ok(false)
    }
}

/// Stop starting the server at login (the running server is left alone).
pub fn disable() -> Result<(), PgServerError> {
    #[cfg(target_os = "macos")]
    {
        // The plist goes first: it is what starts the server at login, so a
        // failure to unload the current job must not keep it.
        let plist = launch_agent_path()?;
        match fs::remove_file(&plist) {
            Err(e) if e.kind() != std::io::ErrorKind::NotFound => {
                return Err(file_error(&plist)(e))
            }
            _ => {}
        }
        bootout(&launchd_domain()?)
    }
    #[cfg(target_os = "linux")]
    {
        let unit = home()?.join(SYSTEMD_USER_DIR).join(SYSTEMD_UNIT_NAME);
        if unit.try_exists().map_err(file_error(&unit))? {
            let mut disable = Command::new("systemctl");
            disable.args(["--user", "disable", SYSTEMD_UNIT_NAME]);
            run(disable)?;
            fs::remove_file(&unit).map_err(file_error(&unit))?;
        }
        Ok(())
    }
    #[cfg(windows)]
    {
        let present = Command::new("reg")
            .args(["query", WINDOWS_RUN_KEY, "/v", WINDOWS_RUN_VALUE])
            .output()
            .map_err(|source| PgServerError::Spawn {
                program: "reg".into(),
                source,
            })?
            .status
            .success();
        if present {
            let mut reg = Command::new("reg");
            reg.args(["delete", WINDOWS_RUN_KEY, "/v", WINDOWS_RUN_VALUE, "/f"]);
            run(reg)?;
        }
        Ok(())
    }
    #[cfg(not(any(target_os = "macos", target_os = "linux", windows)))]
    {
        Err(PgServerError::Io(std::io::Error::other(
            "autostart is not supported on this platform",
        )))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const EXE: &str = "/Applications/BML App/bml";
    const CONFIG: &str = "/Users/a b/.bmlibrarian";

    #[test]
    fn plist_runs_once() {
        let plist = render_launch_agent(Path::new(EXE), Path::new(CONFIG));
        let compact: String = plist.split_whitespace().collect();
        assert!(compact.contains("<key>RunAtLoad</key><true/>"));
        assert!(plist.contains("<string>/Users/a b/.bmlibrarian</string>"));
        assert!(plist.contains("<string>org.bmlibrarian.pgserver</string>"));
        assert!(!plist.contains("KeepAlive"));
        let log = format!(
            "<string>{}</string>",
            Path::new(CONFIG).join(AUTOSTART_LOG_NAME).display()
        );
        assert!(compact_has(&plist, "<key>StandardErrorPath</key>", &log));
        assert!(compact_has(&plist, "<key>StandardOutPath</key>", &log));
    }

    /// Whether `key` is directly followed by `value` in `plist`.
    fn compact_has(plist: &str, key: &str, value: &str) -> bool {
        let lines: Vec<&str> = plist.lines().map(str::trim).collect();
        lines.windows(2).any(|w| w[0] == key && w[1] == value)
    }

    #[test]
    fn bootout_accepts_only_not_loaded() {
        for code in [0, 3, 36, 112, 113] {
            assert!(bootout_succeeded(Some(code)), "{code}");
        }
        for code in [Some(1), Some(5), Some(37), None] {
            assert!(!bootout_succeeded(code), "{code:?}");
        }
    }

    /// A failed `launchctl` with exit code `status`.
    fn launchctl_failed(status: i32) -> PgServerError {
        PgServerError::Command {
            program: "launchctl".to_owned(),
            status: Some(status),
            stderr: format!("attempt failed with {status}"),
        }
    }

    /// Run [`retry_while_busy`] over `results`; returns its result and the
    /// number of attempts.
    fn retry(results: Vec<Result<(), PgServerError>>) -> (Result<(), PgServerError>, usize) {
        let mut results = results.into_iter();
        let mut calls = 0;
        let result = retry_while_busy(std::time::Duration::ZERO, || {
            calls += 1;
            results.next().expect("no more attempts expected")
        });
        (result, calls)
    }

    #[test]
    fn bootstrap_retries_while_busy() {
        let busy = || Err(launchctl_failed(BOOTSTRAP_BUSY_CODE));
        let (result, calls) = retry(vec![busy(), busy(), busy(), Ok(())]);
        assert!(result.is_ok());
        assert_eq!(calls, 4);

        let always_busy = (0..=BOOTSTRAP_RETRIES).map(|_| busy()).collect();
        let (result, calls) = retry(always_busy);
        assert_eq!(calls, BOOTSTRAP_RETRIES as usize + 1);
        assert!(result
            .unwrap_err()
            .to_string()
            .contains("attempt failed with 5"));

        let (result, calls) = retry(vec![Err(launchctl_failed(1))]);
        assert_eq!(calls, 1);
        assert!(result
            .unwrap_err()
            .to_string()
            .contains("attempt failed with 1"));
    }

    #[cfg(target_os = "macos")]
    #[test]
    fn plist_passes_plutil_lint() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("agent.plist");
        std::fs::write(
            &path,
            render_launch_agent(Path::new(EXE), Path::new("/Users/R&D/<cfg> 'q\"")),
        )
        .unwrap();
        let out = Command::new("plutil")
            .arg("-lint")
            .arg(&path)
            .output()
            .unwrap();
        assert!(
            out.status.success(),
            "{}",
            String::from_utf8_lossy(&out.stdout)
        );
    }

    #[test]
    fn plist_escapes_xml() {
        let plist = render_launch_agent(Path::new(EXE), Path::new("/Users/R&D/<cfg>"));
        assert!(plist.contains("<string>/Users/R&amp;D/&lt;cfg&gt;</string>"));
    }

    #[test]
    fn unit_oneshot_no_restart() {
        let unit = render_systemd_unit(Path::new(EXE), Path::new(CONFIG));
        assert!(unit.contains("Type=oneshot"));
        assert!(unit.contains("RemainAfterExit=yes"));
        assert!(!unit.contains("Restart="));
        assert!(unit.contains(
            "ExecStart=\"/Applications/BML App/bml\" \"--config-dir\" \"/Users/a b/.bmlibrarian\" \"server\" \"start\""
        ));
        assert!(unit.contains("\"server\" \"stop\""));
        assert!(unit.contains("WantedBy=default.target"));
    }

    #[test]
    fn unit_escapes_percent() {
        let unit = render_systemd_unit(Path::new(EXE), Path::new("/data/100%"));
        assert!(unit.contains("\"/data/100%%\""));
    }

    #[test]
    fn unit_escapes_dollar_quote_backslash() {
        let unit = render_systemd_unit(Path::new(EXE), Path::new("/d/$HOME \"q\" a\\b"));
        assert!(unit.contains(r#""/d/$$HOME \"q\" a\\b""#), "{unit}");
    }

    #[test]
    fn windows_cmd_doubles_trailing_backslashes() {
        assert_eq!(
            windows_run_command(Path::new(r"C:\bml.exe"), Path::new(r"D:\")),
            r#""C:\bml.exe" "--config-dir" "D:\\" "server" "start""#
        );
    }

    #[test]
    fn file_has_text_compares_whole_file() {
        let dir = tempfile::tempdir().unwrap();
        let f = dir.path().join("x");
        assert!(!file_has_text(&f, "a").unwrap());
        std::fs::write(&f, "a").unwrap();
        assert!(file_has_text(&f, "a").unwrap());
        assert!(!file_has_text(&f, "b").unwrap());
    }

    #[test]
    fn systemd_needs_unit_and_wants_link() {
        let dir = tempfile::tempdir().unwrap();
        let unit = dir.path().join(SYSTEMD_UNIT_NAME);
        assert!(!systemd_enabled(dir.path(), "u").unwrap());
        std::fs::write(&unit, "u").unwrap();
        assert!(!systemd_enabled(dir.path(), "u").unwrap());
        let wants = dir.path().join(SYSTEMD_WANTS_DIR);
        std::fs::create_dir(&wants).unwrap();
        std::fs::write(wants.join(SYSTEMD_UNIT_NAME), "").unwrap();
        assert!(systemd_enabled(dir.path(), "u").unwrap());
        assert!(!systemd_enabled(dir.path(), "other").unwrap());
    }

    #[test]
    fn reg_output_matches_value_exactly() {
        let out =
            "\r\nHKEY\\Run\r\n    BMLibrarianPgServer    REG_SZ    \"C:\\bml.exe\" \"server\"\r\n";
        assert!(reg_output_has(out, "\"C:\\bml.exe\" \"server\""));
        assert!(!reg_output_has(out, "\"C:\\other.exe\""));
    }

    #[test]
    fn windows_cmd_quotes() {
        assert_eq!(
            windows_run_command(
                Path::new(r"C:\Program Files\BML\bml.exe"),
                Path::new(r"C:\Users\a b\.bmlibrarian")
            ),
            "\"C:\\Program Files\\BML\\bml.exe\" \"--config-dir\" \"C:\\Users\\a b\\.bmlibrarian\" \"server\" \"start\""
        );
    }
}
