//! `bml server …`: manage the private PostgreSQL server.

use std::path::{Path, PathBuf};
use std::process::ExitCode;

use bml_pgserver::autostart;
use bml_pgserver::control::{restart, start, status, stop, ServerStatus};
use bml_pgserver::envfile::{read_conn_info, APP_ENV_FILE_NAME};
use bml_pgserver::error::PgServerError;
use bml_pgserver::external::{load_external_state, ExternalState};
use bml_pgserver::init::{connect, init, InitRequest, HOST};
use bml_pgserver::state::{load_state, ServerState};
use clap::Subcommand;

/// Print a line to stdout, ignoring a closed pipe (`bml server status | head`)
/// rather than panicking as `println!` does.
macro_rules! say {
    ($($arg:tt)*) => {{
        use std::io::Write as _;
        let _ = writeln!(std::io::stdout(), $($arg)*);
    }};
}
pub(crate) use say;

/// Exit code: the server is running and healthy.
pub const EXIT_HEALTHY: u8 = 0;
/// Exit code: a command failed, the server is running but unhealthy, or its
/// data folder is missing or unreadable.
pub const EXIT_FAILED: u8 = 1;
/// Exit code: no server has been set up in this configuration folder.
pub const EXIT_NOT_SET_UP: u8 = 2;
/// Exit code of `status`: the server is set up but stopped (as `pg_ctl
/// status` reports it).
pub const EXIT_STOPPED: u8 = 3;

/// Extension listed first in status output.
const PRIMARY_EXTENSION: &str = "vector";

/// `bml server …` subcommands.
#[derive(Subcommand)]
pub enum ServerCommand {
    /// Set up the private server (safe to run again).
    Init {
        /// Folder with the PostgreSQL tools (version 18 or newer).
        #[arg(long, value_name = "DIR")]
        bindir: PathBuf,
        /// Where the database lives (a new or empty folder, or the one set up before).
        #[arg(long, value_name = "DIR")]
        data_dir: PathBuf,
        /// An extension folder (with lib/postgresql and share/postgresql); repeatable.
        #[arg(long = "extension-dir", value_name = "DIR")]
        extension_dirs: Vec<PathBuf>,
    },
    /// Start the server (does nothing if running).
    Start,
    /// Stop the server (does nothing if stopped).
    Stop,
    /// Stop and start the server.
    Restart,
    /// Show whether the server is set up, running and healthy.
    Status,
    /// Start the server automatically at login.
    #[command(subcommand)]
    Autostart(AutostartCommand),
}

/// `bml server autostart …` subcommands.
#[derive(Subcommand)]
pub enum AutostartCommand {
    /// Start the server at every login.
    Enable,
    /// Stop starting the server at login.
    Disable,
}

/// Run `command` with configuration in `config_dir`.
pub fn run(command: ServerCommand, config_dir: &Path) -> Result<ExitCode, PgServerError> {
    match command {
        ServerCommand::Init {
            bindir,
            data_dir,
            extension_dirs,
        } => {
            let req = InitRequest {
                bindir,
                data_dir,
                extension_dirs,
            };
            let outcome = init(&req, config_dir)?;
            if outcome.app_password_reset {
                say!(
                    "Note: the server refused the password in {APP_ENV_FILE_NAME}, so it was \
                     reset; other copies of the old password no longer work."
                );
            }
            say!(
                "Server ready on {HOST}:{} (data: {}){}",
                outcome.state.port,
                outcome.state.data_dir.display(),
                if outcome.pg_search {
                    ""
                } else {
                    "; pg_search not installed"
                }
            );
            Ok(ExitCode::from(EXIT_HEALTHY))
        }
        ServerCommand::Start => with_state(config_dir, start),
        ServerCommand::Stop => with_state(config_dir, stop),
        ServerCommand::Restart => with_state(config_dir, restart),
        ServerCommand::Status => show_status(config_dir),
        ServerCommand::Autostart(AutostartCommand::Enable) => {
            if load_external_state(config_dir)?.is_some() {
                return Ok(refuse_external());
            }
            if load_state(config_dir)?.is_none() {
                say!("{}", not_set_up());
                return Ok(ExitCode::from(EXIT_NOT_SET_UP));
            }
            let exe = std::env::current_exe().map_err(PgServerError::Io)?;
            autostart::enable(&exe, config_dir)?;
            say!("The server will start at login.");
            Ok(ExitCode::from(EXIT_HEALTHY))
        }
        ServerCommand::Autostart(AutostartCommand::Disable) => {
            autostart::disable()?;
            say!("The server will no longer start at login.");
            Ok(ExitCode::from(EXIT_HEALTHY))
        }
    }
}

/// Apply `action` to the saved server, or report that none is set up.
fn with_state(
    config_dir: &Path,
    action: fn(&ServerState) -> Result<(), PgServerError>,
) -> Result<ExitCode, PgServerError> {
    if load_external_state(config_dir)?.is_some() {
        return Ok(refuse_external());
    }
    match load_state(config_dir)? {
        Some(state) => {
            action(&state)?;
            Ok(ExitCode::from(EXIT_HEALTHY))
        }
        None => {
            say!("{}", not_set_up());
            Ok(ExitCode::from(EXIT_NOT_SET_UP))
        }
    }
}

/// Explain that bml does not control an existing server.
fn refuse_external() -> ExitCode {
    say!(
        "This configuration uses an existing PostgreSQL server, which bml does not start, \
         stop or autostart. Manage that server with its own tools; run `bml setup` to \
         repair bml's connection to it."
    );
    ExitCode::from(EXIT_FAILED)
}

/// Print the health of an existing server and return the matching exit code.
fn show_external_status(config_dir: &Path, external: &ExternalState) -> ExitCode {
    say!(
        "Server: existing PostgreSQL at {}:{} (not managed by bml)",
        external.host,
        external.port
    );
    report_extensions(config_dir)
}

/// Print the extension health check and return its exit code.
fn report_extensions(config_dir: &Path) -> ExitCode {
    match extensions(config_dir) {
        Ok(names) => {
            say!("Extensions: {}", names.join(", "));
            ExitCode::from(EXIT_HEALTHY)
        }
        Err(e) => {
            say!("Health: check failed: {e}");
            ExitCode::from(EXIT_FAILED)
        }
    }
}

/// The message for a configuration folder with no server.
fn not_set_up() -> &'static str {
    "Server: not set up (run \"bml server init\")"
}

/// Print the server's status and return the matching exit code.
fn show_status(config_dir: &Path) -> Result<ExitCode, PgServerError> {
    if let Some(external) = load_external_state(config_dir)? {
        return Ok(show_external_status(config_dir, &external));
    }
    let Some(state) = load_state(config_dir)? else {
        say!("{}", not_set_up());
        return Ok(ExitCode::from(EXIT_NOT_SET_UP));
    };
    let not_running_code = match status(&state)? {
        ServerStatus::Running => {
            say!("Server: running on {HOST}:{}", state.port);
            None
        }
        ServerStatus::Stopped => {
            say!("Server: stopped");
            Some(EXIT_STOPPED)
        }
        ServerStatus::NotInitialised => {
            say!(
                "Server: data folder missing, unreadable or not set up (is its disk mounted? \
                 if setup was interrupted, run \"bml server init\" again)"
            );
            Some(EXIT_FAILED)
        }
    };
    say!("Data: {}", state.data_dir.display());
    if let Some(code) = not_running_code {
        return Ok(ExitCode::from(code));
    }
    Ok(report_extensions(config_dir))
}

/// Extensions installed in the app database, `vector` first.
fn extensions(config_dir: &Path) -> Result<Vec<String>, PgServerError> {
    let env = config_dir.join(APP_ENV_FILE_NAME);
    let fix = if load_external_state(config_dir)?.is_some() {
        "bml setup"
    } else {
        "bml server init"
    };
    let info = read_conn_info(&env)?.ok_or_else(|| {
        PgServerError::Io(std::io::Error::other(format!(
            "{} is missing; run \"{fix}\"",
            env.display()
        )))
    })?;
    let mut client = connect(&info)?;
    let mut names: Vec<String> = client
        .query(
            "SELECT extname::text FROM pg_extension WHERE extname <> 'plpgsql'",
            &[],
        )?
        .iter()
        .map(|row| row.get(0))
        .collect();
    names.sort_by_key(|n| (n != PRIMARY_EXTENSION, n.clone()));
    Ok(names)
}
