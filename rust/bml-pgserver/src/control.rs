//! Running the server's tools: version check, start, stop, restart, status;
//! plus reading the machine's RAM for the import profile.

use std::path::{Path, PathBuf};
use std::process::{Command, Output};

use crate::error::PgServerError;
use crate::state::ServerState;

/// Oldest supported PostgreSQL major version.
pub const MIN_PG_MAJOR: u32 = 18;

/// The server's log file, inside the data directory.
pub const SERVER_LOG_NAME: &str = "bml-server.log";

/// Seconds `pg_ctl` waits for the server to start or stop.
pub const PG_CTL_WAIT_SECONDS: u32 = 60;

/// `pg_ctl status` exit codes.
const PG_CTL_STATUS_RUNNING: i32 = 0;
const PG_CTL_STATUS_STOPPED: i32 = 3;
const PG_CTL_STATUS_NO_DATA_DIR: i32 = 4;

/// The marker before the version number in `postgres --version` output.
const VERSION_MARKER: &str = "(PostgreSQL) ";

/// Whether the server is running.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ServerStatus {
    /// The server is running.
    Running,
    /// The data directory exists, but no server is running on it.
    Stopped,
    /// There is no initialised data directory.
    NotInitialised,
}

/// The path of PostgreSQL tool `name` in `bindir`.
pub fn tool(bindir: &Path, name: &str) -> PathBuf {
    bindir.join(format!("{name}{}", std::env::consts::EXE_SUFFIX))
}

/// The major version in `postgres --version` output.
pub fn parse_postgres_version(output: &str) -> Option<u32> {
    let rest = &output[output.find(VERSION_MARKER)? + VERSION_MARKER.len()..];
    let digits: String = rest.chars().take_while(char::is_ascii_digit).collect();
    digits.parse().ok()
}

/// Run `command`, turning a failed exit into [`PgServerError::Command`].
fn run(mut command: Command) -> Result<Output, PgServerError> {
    let program = command.get_program().to_string_lossy().into_owned();
    let output = command.output()?;
    if output.status.success() {
        Ok(output)
    } else {
        Err(PgServerError::Command {
            program,
            status: output.status.code(),
            stderr: String::from_utf8_lossy(&output.stderr).trim().to_owned(),
        })
    }
}

/// The major version of the PostgreSQL in `bindir`, if supported.
pub fn pg_major_version(bindir: &Path) -> Result<u32, PgServerError> {
    let program = tool(bindir, "postgres");
    let mut command = Command::new(&program);
    command.arg("--version");
    let output = run(command)?;
    let text = String::from_utf8_lossy(&output.stdout);
    let found = parse_postgres_version(&text).ok_or_else(|| PgServerError::Command {
        program: program.to_string_lossy().into_owned(),
        status: Some(0),
        stderr: format!("unrecognised version output: {}", text.trim()),
    })?;
    if found < MIN_PG_MAJOR {
        return Err(PgServerError::UnsupportedVersion { found });
    }
    Ok(found)
}

/// `pg_ctl` for `state`'s binaries.
fn pg_ctl(state: &ServerState) -> Command {
    Command::new(tool(&state.bindir, "pg_ctl"))
}

/// Whether the server of `state` is running.
pub fn status(state: &ServerState) -> Result<ServerStatus, PgServerError> {
    let mut command = pg_ctl(state);
    command.arg("status").arg("-D").arg(&state.data_dir);
    let output = command.output()?;
    match output.status.code() {
        Some(PG_CTL_STATUS_RUNNING) => Ok(ServerStatus::Running),
        Some(PG_CTL_STATUS_STOPPED) => Ok(ServerStatus::Stopped),
        Some(PG_CTL_STATUS_NO_DATA_DIR) => Ok(ServerStatus::NotInitialised),
        code => Err(PgServerError::Command {
            program: "pg_ctl status".to_owned(),
            status: code,
            stderr: String::from_utf8_lossy(&output.stderr).trim().to_owned(),
        }),
    }
}

/// Start the server; does nothing if it is already running.
pub fn start(state: &ServerState) -> Result<(), PgServerError> {
    if status(state)? == ServerStatus::Running {
        return Ok(());
    }
    let mut command = pg_ctl(state);
    command
        .arg("start")
        .arg("-D")
        .arg(&state.data_dir)
        .arg("-l")
        .arg(state.data_dir.join(SERVER_LOG_NAME))
        .arg("-w")
        .arg("-t")
        .arg(PG_CTL_WAIT_SECONDS.to_string());
    run(command).map(drop)
}

/// Stop the server (fast shutdown); does nothing if it is not running.
pub fn stop(state: &ServerState) -> Result<(), PgServerError> {
    if status(state)? != ServerStatus::Running {
        return Ok(());
    }
    let mut command = pg_ctl(state);
    command
        .arg("stop")
        .arg("-D")
        .arg(&state.data_dir)
        .args(["-m", "fast", "-w", "-t"])
        .arg(PG_CTL_WAIT_SECONDS.to_string());
    run(command).map(drop)
}

/// Stop, then start. Not `pg_ctl restart`: that replays `postmaster.opts`
/// through a shell, which mangles paths with special characters.
pub fn restart(state: &ServerState) -> Result<(), PgServerError> {
    stop(state)?;
    start(state)
}

/// Total physical memory of this machine, in bytes.
pub fn total_memory_bytes() -> u64 {
    let mut system = sysinfo::System::new();
    system.refresh_memory();
    system.total_memory()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_postgres_app() {
        assert_eq!(
            parse_postgres_version("postgres (PostgreSQL) 18.1 (Postgres.app)"),
            Some(18)
        );
    }

    #[test]
    fn parses_debian() {
        assert_eq!(
            parse_postgres_version("postgres (PostgreSQL) 18.0 (Debian 18.0-1.pgdg24.04+1)"),
            Some(18)
        );
    }

    #[test]
    fn parses_beta() {
        assert_eq!(
            parse_postgres_version("postgres (PostgreSQL) 19beta1"),
            Some(19)
        );
    }

    #[test]
    fn rejects_garbage() {
        assert_eq!(parse_postgres_version("hello"), None);
    }

    #[test]
    fn memory_positive() {
        assert!(total_memory_bytes() > 0);
    }

    #[cfg(windows)]
    #[test]
    fn tool_has_exe() {
        assert!(tool(Path::new(r"C:\pg\bin"), "pg_ctl")
            .to_string_lossy()
            .ends_with("pg_ctl.exe"));
    }
}
