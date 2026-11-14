//! Running `bml library update` every few days, per user, without admin
//! rights, beside the login entry of [`crate::autostart`].
//!
//! macOS: a LaunchAgent with `StartInterval` (launchd runs a missed interval
//! when the Mac wakes). Linux: a `systemd --user` timer with `Persistent`
//! (a missed run happens at the next login). Windows: a per-user Scheduled
//! Task (unverified, #397). There is one entry per user; scheduling again
//! replaces it. Like the login entry it records the running `bml`, so
//! schedule from an installed `bml`, not a `cargo run` build.

use std::ffi::OsString;
#[cfg(any(target_os = "macos", target_os = "linux"))]
use std::fs;
use std::path::Path;
#[cfg(any(target_os = "linux", windows))]
use std::process::Command;

#[cfg(target_os = "macos")]
use crate::autostart::{
    bootout, bootstrap, launch_agent_path, launchd_domain, read_previous, restore_launch_agent,
};
#[cfg(target_os = "linux")]
use crate::autostart::{home, read_previous, restore_file, undo_on_failure, SYSTEMD_USER_DIR};
use crate::autostart::{systemd_quote, windows_quote, xml_escape};
#[cfg(any(target_os = "linux", windows))]
use crate::control::run;
#[cfg(any(target_os = "macos", target_os = "linux"))]
use crate::error::file_error;
use crate::error::PgServerError;

/// The LaunchAgent label (macOS).
pub const UPDATE_AGENT_LABEL: &str = "org.bmlibrarian.library-update";
/// The `systemd --user` service running the update (Linux).
pub const UPDATE_SERVICE_NAME: &str = "bml-library-update.service";
/// The `systemd --user` timer starting [`UPDATE_SERVICE_NAME`] (Linux).
pub const UPDATE_TIMER_NAME: &str = "bml-library-update.timer";
/// The Scheduled Task's name (Windows).
pub const UPDATE_TASK_NAME: &str = "BMLibrarian Library Update";
/// Where a scheduled update writes its output, in the configuration folder.
pub const UPDATE_LOG_NAME: &str = "bml-library-update.log";
/// The default schedule: once a week.
pub const WEEKLY_DAYS: u32 = 7;
/// Seconds in a day (launchd counts intervals in seconds).
const SECONDS_PER_DAY: u64 = 24 * 60 * 60;

/// The scheduled command: `bml --config-dir <dir> library update`.
pub fn update_args(exe: &Path, config_dir: &Path) -> Vec<OsString> {
    vec![
        exe.as_os_str().to_owned(),
        "--config-dir".into(),
        config_dir.as_os_str().to_owned(),
        "library".into(),
        "update".into(),
    ]
}

/// The LaunchAgent plist: runs the update every `days` days, logging to
/// [`UPDATE_LOG_NAME`] in `config_dir`.
// shortcut: launchd's interval restarts when the agent loads (each login),
// so a Mac restarted more often than every `days` days never runs it; use
// StartCalendarInterval (weekday/hour) if that turns out to matter.
pub fn render_update_agent(exe: &Path, config_dir: &Path, days: u32) -> String {
    let log = xml_escape(&config_dir.join(UPDATE_LOG_NAME).to_string_lossy());
    let args: String = update_args(exe, config_dir)
        .iter()
        .map(|a| {
            format!(
                "        <string>{}</string>\n",
                xml_escape(&a.to_string_lossy())
            )
        })
        .collect();
    let interval = u64::from(days) * SECONDS_PER_DAY;
    format!(
        r#"<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{UPDATE_AGENT_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
{args}    </array>
    <key>StartInterval</key>
    <integer>{interval}</integer>
    <key>StandardOutPath</key>
    <string>{log}</string>
    <key>StandardErrorPath</key>
    <string>{log}</string>
</dict>
</plist>
"#
    )
}

/// The `systemd --user` service the timer starts.
pub fn render_update_service(exe: &Path, config_dir: &Path) -> String {
    let line = update_args(exe, config_dir)
        .iter()
        .map(systemd_quote)
        .collect::<Vec<_>>()
        .join(" ");
    format!(
        "[Unit]\nDescription=Update the BMLibrarian library\n\n\
         [Service]\nType=oneshot\nExecStart={line}\n"
    )
}

/// The `systemd --user` timer: weekly, daily, or every `days` days.
// shortcut: other intervals step through the days of each month
// (`*-*-01/<days>`), so the gap at a month's end is shorter; a calendar
// expression has no "every n days", and a monotonic timer forgets its
// last run at logout.
pub fn render_update_timer(days: u32) -> String {
    let calendar = match days {
        1 => "daily".to_string(),
        WEEKLY_DAYS => "weekly".to_string(),
        n => format!("*-*-01/{n} 00:00:00"),
    };
    format!(
        "[Unit]\nDescription=Update the BMLibrarian library every {days} day(s)\n\n\
         [Timer]\nOnCalendar={calendar}\nPersistent=true\n\n\
         [Install]\nWantedBy=timers.target\n"
    )
}

/// The command the Windows Scheduled Task runs, every argument quoted.
pub fn windows_task_command(exe: &Path, config_dir: &Path) -> String {
    update_args(exe, config_dir)
        .iter()
        .map(windows_quote)
        .collect::<Vec<_>>()
        .join(" ")
}

/// Run `bml library update` every `days` days (replacing an earlier schedule).
///
/// # Errors
///
/// `days` is 0, or the scheduler refused the entry; a failed macOS re-schedule
/// puts the old entry back.
pub fn schedule_updates(exe: &Path, config_dir: &Path, days: u32) -> Result<(), PgServerError> {
    if days == 0 {
        return Err(PgServerError::Io(std::io::Error::other(
            "updates cannot be scheduled every 0 days",
        )));
    }
    #[cfg(target_os = "macos")]
    {
        let plist = launch_agent_path(UPDATE_AGENT_LABEL)?;
        let domain = launchd_domain()?;
        let previous = read_previous(&plist)?;
        bootout(&domain, UPDATE_AGENT_LABEL)?;
        let agents = plist.parent().expect("plist path has a parent");
        fs::create_dir_all(agents)
            .map_err(file_error(agents))
            .and_then(|()| {
                fs::write(&plist, render_update_agent(exe, config_dir, days))
                    .map_err(file_error(&plist))
            })
            .and_then(|()| bootstrap(&domain, &plist))
            .map_err(|error| {
                restore_launch_agent(&plist, previous, error, |old| bootstrap(&domain, old))
            })
    }
    #[cfg(target_os = "linux")]
    {
        let unit_dir = home()?.join(SYSTEMD_USER_DIR);
        fs::create_dir_all(&unit_dir).map_err(file_error(&unit_dir))?;
        let service = unit_dir.join(UPDATE_SERVICE_NAME);
        let timer = unit_dir.join(UPDATE_TIMER_NAME);
        let (old_service, old_timer) = (read_previous(&service)?, read_previous(&timer)?);
        fs::write(&service, render_update_service(exe, config_dir))
            .map_err(file_error(&service))?;
        fs::write(&timer, render_update_timer(days)).map_err(file_error(&timer))?;
        let enabled = (|| {
            let mut reload = Command::new("systemctl");
            reload.args(["--user", "daemon-reload"]);
            run(reload)?;
            let mut enable = Command::new("systemctl");
            enable.args(["--user", "enable", "--now", UPDATE_TIMER_NAME]);
            run(enable).map(drop)
        })();
        undo_on_failure(enabled, &timer, || {
            restore_file(&service, old_service).and(restore_file(&timer, old_timer))
        })
    }
    #[cfg(windows)]
    {
        let mut schtasks = Command::new("schtasks");
        schtasks
            .args(["/Create", "/SC", "DAILY", "/MO"])
            .arg(days.to_string())
            .args(["/TN", UPDATE_TASK_NAME, "/TR"])
            .arg(windows_task_command(exe, config_dir))
            .arg("/F");
        run(schtasks).map(drop)
    }
    #[cfg(not(any(target_os = "macos", target_os = "linux", windows)))]
    {
        let _ = (exe, config_dir);
        Err(PgServerError::Io(std::io::Error::other(
            "scheduled updates are not supported on this platform",
        )))
    }
}

/// Stop scheduled updates (an update running now is left alone).
///
/// # Errors
///
/// The scheduler entry could not be removed.
pub fn unschedule_updates() -> Result<(), PgServerError> {
    #[cfg(target_os = "macos")]
    {
        let plist = launch_agent_path(UPDATE_AGENT_LABEL)?;
        match fs::remove_file(&plist) {
            Err(e) if e.kind() != std::io::ErrorKind::NotFound => {
                return Err(file_error(&plist)(e))
            }
            _ => {}
        }
        bootout(&launchd_domain()?, UPDATE_AGENT_LABEL)
    }
    #[cfg(target_os = "linux")]
    {
        let unit_dir = home()?.join(SYSTEMD_USER_DIR);
        let timer = unit_dir.join(UPDATE_TIMER_NAME);
        if timer.try_exists().map_err(file_error(&timer))? {
            let mut disable = Command::new("systemctl");
            disable.args(["--user", "disable", "--now", UPDATE_TIMER_NAME]);
            run(disable)?;
            fs::remove_file(&timer).map_err(file_error(&timer))?;
        }
        let service = unit_dir.join(UPDATE_SERVICE_NAME);
        match fs::remove_file(&service) {
            Err(e) if e.kind() != std::io::ErrorKind::NotFound => Err(file_error(&service)(e)),
            _ => Ok(()),
        }
    }
    #[cfg(windows)]
    {
        let present = Command::new("schtasks")
            .args(["/Query", "/TN", UPDATE_TASK_NAME])
            .output()
            .map_err(|source| PgServerError::Spawn {
                program: "schtasks".into(),
                source,
            })?
            .status
            .success();
        if present {
            let mut schtasks = Command::new("schtasks");
            schtasks.args(["/Delete", "/TN", UPDATE_TASK_NAME, "/F"]);
            run(schtasks)?;
        }
        Ok(())
    }
    #[cfg(not(any(target_os = "macos", target_os = "linux", windows)))]
    {
        Err(PgServerError::Io(std::io::Error::other(
            "scheduled updates are not supported on this platform",
        )))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    fn exe() -> PathBuf {
        PathBuf::from("/Apps/My bml/bml")
    }

    #[test]
    fn the_agent_runs_the_update_every_n_days() {
        let plist = render_update_agent(&exe(), Path::new("/cfg & co"), WEEKLY_DAYS);
        assert!(plist.contains("<integer>604800</integer>"), "{plist}");
        assert!(plist.contains("<string>library</string>\n        <string>update</string>"));
        assert!(plist.contains("/cfg &amp; co"), "escaped");
        assert!(!plist.contains("RunAtLoad"), "not run when scheduled");
    }

    #[test]
    fn the_timer_names_weekly_daily_and_other_intervals() {
        assert!(render_update_timer(WEEKLY_DAYS).contains("OnCalendar=weekly\n"));
        assert!(render_update_timer(1).contains("OnCalendar=daily\n"));
        assert!(render_update_timer(3).contains("OnCalendar=*-*-01/3 00:00:00\n"));
        assert!(render_update_timer(3).contains("Persistent=true"));
    }

    #[test]
    fn the_service_quotes_its_arguments() {
        let unit = render_update_service(&exe(), Path::new("/cfg"));
        assert!(
            unit.contains(
                r#"ExecStart="/Apps/My bml/bml" "--config-dir" "/cfg" "library" "update""#
            ),
            "{unit}"
        );
    }

    #[test]
    fn the_task_command_quotes_every_argument() {
        assert_eq!(
            windows_task_command(Path::new(r"C:\bml.exe"), Path::new(r"D:\")),
            r#""C:\bml.exe" "--config-dir" "D:\\" "library" "update""#
        );
    }

    #[test]
    fn zero_days_is_refused() {
        assert!(schedule_updates(&exe(), Path::new("/cfg"), 0).is_err());
    }

    #[cfg(target_os = "macos")]
    #[test]
    fn plist_passes_plutil_lint() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("agent.plist");
        std::fs::write(&path, render_update_agent(&exe(), dir.path(), 3)).unwrap();
        let out = std::process::Command::new("plutil")
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
}
