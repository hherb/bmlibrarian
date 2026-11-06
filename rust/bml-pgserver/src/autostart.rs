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

/// The value name under the per-user `Run` key (Windows).
pub const WINDOWS_RUN_VALUE: &str = "BMLibrarianPgServer";

/// Where the macOS login start writes its output, in the configuration
/// folder (launchd would otherwise discard it).
pub const AUTOSTART_LOG_NAME: &str = "bml-autostart.log";

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

/// Start the server at every login of this user (on macOS, also now).
pub fn enable(exe: &Path, config_dir: &Path) -> Result<(), PgServerError> {
    #[cfg(target_os = "macos")]
    {
        let plist = launch_agent_path()?;
        let agents = plist.parent().expect("plist path has a parent");
        fs::create_dir_all(agents).map_err(file_error(agents))?;
        fs::write(&plist, render_launch_agent(exe, config_dir)).map_err(file_error(&plist))?;
        let domain = launchd_domain()?;
        // Unload a previous registration first, so enable can be repeated;
        // failure just means it was not loaded.
        let _ = Command::new("launchctl")
            .arg("bootout")
            .arg(format!("{domain}/{LAUNCH_AGENT_LABEL}"))
            .output();
        let mut bootstrap = Command::new("launchctl");
        bootstrap.arg("bootstrap").arg(&domain).arg(&plist);
        run(bootstrap).map(drop)
    }
    #[cfg(target_os = "linux")]
    {
        let unit_dir = home()?.join(".config/systemd/user");
        let unit = unit_dir.join(SYSTEMD_UNIT_NAME);
        fs::create_dir_all(&unit_dir).map_err(file_error(&unit_dir))?;
        fs::write(&unit, render_systemd_unit(exe, config_dir)).map_err(file_error(&unit))?;
        let mut reload = Command::new("systemctl");
        reload.args(["--user", "daemon-reload"]);
        run(reload)?;
        let mut enable = Command::new("systemctl");
        enable.args(["--user", "enable", SYSTEMD_UNIT_NAME]);
        run(enable).map(drop)
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

/// Stop starting the server at login (the running server is left alone).
pub fn disable() -> Result<(), PgServerError> {
    #[cfg(target_os = "macos")]
    {
        let domain = launchd_domain()?;
        let _ = Command::new("launchctl")
            .arg("bootout")
            .arg(format!("{domain}/{LAUNCH_AGENT_LABEL}"))
            .output();
        let plist = launch_agent_path()?;
        match fs::remove_file(&plist) {
            Err(e) if e.kind() != std::io::ErrorKind::NotFound => Err(file_error(&plist)(e)),
            _ => Ok(()),
        }
    }
    #[cfg(target_os = "linux")]
    {
        let unit = home()?.join(".config/systemd/user").join(SYSTEMD_UNIT_NAME);
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
