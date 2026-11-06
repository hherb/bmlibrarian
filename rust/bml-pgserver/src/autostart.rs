//! Starting the private server once at user login, without admin rights.
//!
//! macOS: a per-user LaunchAgent. Linux: a `systemd --user` unit. Windows: the
//! per-user `Run` registry key (a logon Scheduled Task needs admin rights).
//! Nothing keeps the server alive: `bml-pgserver` is the only thing that
//! stops or restarts it, so an import-profile restart never fights a
//! supervisor.

use std::ffi::OsString;
#[cfg(any(target_os = "macos", target_os = "linux"))]
use std::fs;
use std::path::Path;
#[cfg(any(target_os = "macos", target_os = "linux", windows))]
use std::path::PathBuf;
#[cfg(any(target_os = "macos", target_os = "linux", windows))]
use std::process::Command;

#[cfg(any(target_os = "macos", target_os = "linux", windows))]
use crate::control::run;
use crate::error::PgServerError;

/// The LaunchAgent label (macOS).
pub const LAUNCH_AGENT_LABEL: &str = "org.bmlibrarian.pgserver";

/// The `systemd --user` unit name (Linux).
pub const SYSTEMD_UNIT_NAME: &str = "bml-pgserver.service";

/// The value name under the per-user `Run` key (Windows).
pub const WINDOWS_RUN_VALUE: &str = "BMLibrarianPgServer";

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

/// The LaunchAgent plist: runs the start command once at login.
pub fn render_launch_agent(exe: &Path, config_dir: &Path) -> String {
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
</dict>
</plist>
"#
    )
}

/// One argument as a double-quoted systemd command-line word.
fn systemd_quote(arg: &OsString) -> String {
    let text = arg
        .to_string_lossy()
        .replace('\\', "\\\\")
        .replace('"', "\\\"")
        .replace('%', "%%");
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

/// The command stored under the Windows `Run` key, every argument quoted
/// (Windows paths cannot contain `"`).
pub fn windows_run_command(exe: &Path, config_dir: &Path) -> String {
    start_args(exe, config_dir)
        .iter()
        .map(|a| format!("\"{}\"", a.to_string_lossy()))
        .collect::<Vec<_>>()
        .join(" ")
}

/// The user's home folder.
#[cfg(any(target_os = "macos", target_os = "linux"))]
fn home() -> Result<PathBuf, PgServerError> {
    std::env::home_dir().ok_or(PgServerError::State(crate::state::StateError::NoHome))
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

/// Start the server at every login of this user.
pub fn enable(exe: &Path, config_dir: &Path) -> Result<(), PgServerError> {
    #[cfg(target_os = "macos")]
    {
        let plist = launch_agent_path()?;
        fs::create_dir_all(plist.parent().expect("plist path has a parent"))?;
        fs::write(&plist, render_launch_agent(exe, config_dir))?;
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
        fs::create_dir_all(&unit_dir)?;
        fs::write(
            unit_dir.join(SYSTEMD_UNIT_NAME),
            render_systemd_unit(exe, config_dir),
        )?;
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
        Err(std::io::Error::other("autostart is not supported on this platform").into())
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
        match fs::remove_file(launch_agent_path()?) {
            Err(e) if e.kind() != std::io::ErrorKind::NotFound => Err(e.into()),
            _ => Ok(()),
        }
    }
    #[cfg(target_os = "linux")]
    {
        let unit = home()?.join(".config/systemd/user").join(SYSTEMD_UNIT_NAME);
        if unit.exists() {
            let mut disable = Command::new("systemctl");
            disable.args(["--user", "disable", SYSTEMD_UNIT_NAME]);
            run(disable)?;
            fs::remove_file(unit)?;
        }
        Ok(())
    }
    #[cfg(windows)]
    {
        let present = Command::new("reg")
            .args(["query", WINDOWS_RUN_KEY, "/v", WINDOWS_RUN_VALUE])
            .output()?
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
        Err(std::io::Error::other("autostart is not supported on this platform").into())
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
