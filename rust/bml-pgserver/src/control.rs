//! Running the server's tools: version check, start, stop, restart, status;
//! plus reading the machine's RAM for the import profile.

use std::path::{Path, PathBuf};
use std::process::{Command, Output, Stdio};

use crate::error::{file_error, PgServerError};
use crate::state::ServerState;

/// Oldest supported PostgreSQL major version.
pub const MIN_PG_MAJOR: u32 = 18;

/// The server's log file, inside the data directory.
pub const SERVER_LOG_NAME: &str = "bml-server.log";

/// What `pg_ctl start` itself prints, inside the data directory. A file, not
/// a pipe: the server `pg_ctl` starts inherits these handles (on Windows), so
/// a pipe would not reach end-of-file until the server stops.
pub const PG_CTL_OUTPUT_NAME: &str = "bml-pg_ctl.out";

/// Seconds `pg_ctl` waits for the server to start or stop.
pub const PG_CTL_WAIT_SECONDS: u32 = 60;

/// `pg_ctl status` exit codes.
const PG_CTL_STATUS_RUNNING: i32 = 0;
const PG_CTL_STATUS_STOPPED: i32 = 3;
const PG_CTL_STATUS_NO_DATA_DIR: i32 = 4;

/// Lines of the server log quoted when the server fails to start.
const LOG_TAIL_LINES: usize = 15;

/// The marker before the version number in `postgres --version` output.
const VERSION_MARKER: &str = "(PostgreSQL) ";

/// Whether the server is running.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ServerStatus {
    /// The server is running.
    Running,
    /// The data directory exists, but no server is running on it.
    Stopped,
    /// The data directory is missing, unreadable, or not initialised.
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
pub(crate) fn run(mut command: Command) -> Result<Output, PgServerError> {
    let program = command.get_program().to_string_lossy().into_owned();
    let output = command.output().map_err(|source| PgServerError::Spawn {
        program: PathBuf::from(&program),
        source,
    })?;
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

/// Run `command` with its output going to the file `output` instead of a
/// pipe, for a program that leaves a child running on its handles; a failed
/// exit becomes [`PgServerError::Command`] quoting that file.
fn run_to_file(mut command: Command, output: &Path) -> Result<(), PgServerError> {
    let program = command.get_program().to_string_lossy().into_owned();
    let file = std::fs::File::create(output).map_err(file_error(output))?;
    let stderr = file.try_clone().map_err(file_error(output))?;
    let status = command
        .stdin(Stdio::null())
        .stdout(file)
        .stderr(stderr)
        .status()
        .map_err(|source| PgServerError::Spawn {
            program: PathBuf::from(&program),
            source,
        })?;
    if status.success() {
        return Ok(());
    }
    let printed = std::fs::read_to_string(output)
        .unwrap_or_else(|e| format!("(cannot read {}: {e})", output.display()));
    Err(PgServerError::Command {
        program,
        status: status.code(),
        stderr: printed.trim().to_owned(),
    })
}

/// The major version of the PostgreSQL in `bindir`, if supported.
pub fn pg_major_version(bindir: &Path) -> Result<u32, PgServerError> {
    let program = tool(bindir, "postgres");
    let mut command = Command::new(&program);
    command.arg("--version");
    let output = run(command)?;
    let text = String::from_utf8_lossy(&output.stdout);
    let found =
        parse_postgres_version(&text).ok_or_else(|| PgServerError::UnrecognisedVersion {
            program: program.clone(),
            output: text.trim().to_owned(),
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
    let output = command.output().map_err(|source| PgServerError::Spawn {
        program: tool(&state.bindir, "pg_ctl"),
        source,
    })?;
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

/// The status of `state`'s server, refusing a data folder that is gone.
fn status_of_existing(state: &ServerState) -> Result<ServerStatus, PgServerError> {
    match status(state)? {
        ServerStatus::NotInitialised => Err(PgServerError::DataDirUnavailable {
            path: state.data_dir.clone(),
        }),
        other => Ok(other),
    }
}

/// The last `n` lines of `text`.
fn last_lines(text: &str, n: usize) -> String {
    let lines: Vec<&str> = text.lines().collect();
    lines[lines.len().saturating_sub(n)..].join("\n")
}

/// Start the server; does nothing if it is already running. A failure
/// quotes the end of the server log, where PostgreSQL says why.
pub fn start(state: &ServerState) -> Result<(), PgServerError> {
    if status_of_existing(state)? == ServerStatus::Running {
        return Ok(());
    }
    let log = state.data_dir.join(SERVER_LOG_NAME);
    let mut command = pg_ctl(state);
    command
        .arg("start")
        .arg("-D")
        .arg(&state.data_dir)
        .arg("-l")
        .arg(&log)
        .arg("-w")
        .arg("-t")
        .arg(PG_CTL_WAIT_SECONDS.to_string());
    run_to_file(command, &state.data_dir.join(PG_CTL_OUTPUT_NAME)).map_err(|source| {
        let tail = std::fs::read_to_string(&log)
            .map(|text| last_lines(&text, LOG_TAIL_LINES))
            .unwrap_or_else(|e| format!("(cannot read it: {e})"));
        PgServerError::StartFailed {
            log,
            tail,
            source: Box::new(source),
        }
    })
}

/// Stop the server (fast shutdown); does nothing if it is not running.
pub fn stop(state: &ServerState) -> Result<(), PgServerError> {
    if status_of_existing(state)? != ServerStatus::Running {
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

/// Stop, then start. Not `pg_ctl restart`, so a restart uses the same
/// `pg_ctl start` arguments (log file, wait timeout) as [`start`] rather
/// than whatever `postmaster.opts` recorded.
pub fn restart(state: &ServerState) -> Result<(), PgServerError> {
    stop(state)?;
    start(state)
}

/// Total physical memory of this machine, in bytes; an error when the
/// system does not report it (sysinfo then says 0).
pub fn total_memory_bytes() -> Result<u64, PgServerError> {
    let mut system = sysinfo::System::new();
    system.refresh_memory();
    match system.total_memory() {
        0 => Err(PgServerError::Io(std::io::Error::other(
            "cannot read this machine's total memory",
        ))),
        bytes => Ok(bytes),
    }
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
    fn missing_bindir_names_path() {
        let err = pg_major_version(Path::new("/nonexistent/pg bin")).unwrap_err();
        assert!(err.to_string().contains("/nonexistent/pg bin"), "{err}");
    }

    #[test]
    fn last_lines_keeps_the_end() {
        assert_eq!(last_lines("a\nb\nc\n", 2), "b\nc");
        assert_eq!(last_lines("a", 5), "a");
        assert_eq!(last_lines("", 5), "");
    }

    #[test]
    fn memory_positive() {
        assert!(total_memory_bytes().unwrap() > 0);
    }

    #[cfg(windows)]
    #[test]
    fn tool_has_exe() {
        assert!(tool(Path::new(r"C:\pg\bin"), "pg_ctl")
            .to_string_lossy()
            .ends_with("pg_ctl.exe"));
    }
}
