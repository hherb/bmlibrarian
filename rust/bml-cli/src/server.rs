//! `bml server …`: manage the private PostgreSQL server.

use std::path::{Path, PathBuf};
use std::process::ExitCode;

use bml_pgserver::autostart;
use bml_pgserver::control::{restart, start, status, stop, ServerStatus};
use bml_pgserver::envfile::{read_conn_info, APP_ENV_FILE_NAME};
use bml_pgserver::error::PgServerError;
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

/// Exit code: the server is running and healthy.
pub const EXIT_HEALTHY: u8 = 0;
/// Exit code: the server is stopped, unhealthy, or a command failed.
pub const EXIT_FAILED: u8 = 1;
/// Exit code: no server has been set up in this configuration folder.
pub const EXIT_NOT_SET_UP: u8 = 2;

/// Extension listed first in status output.
const PRIMARY_EXTENSION: &str = "vector";

/// `bml server …` subcommands.
#[derive(Subcommand)]
pub enum ServerCommand {
    /// Set up the private server (safe to run again).
    Init {
        /// Folder with the PostgreSQL 18 tools.
        #[arg(long, value_name = "DIR")]
        bindir: PathBuf,
        /// Where the database lives (a new or empty folder).
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
            autostart::enable(&std::env::current_exe()?, config_dir)?;
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

/// The message for a configuration folder with no server.
fn not_set_up() -> &'static str {
    "Server: not set up (run \"bml server init\")"
}

/// Print the server's status and return the matching exit code.
fn show_status(config_dir: &Path) -> Result<ExitCode, PgServerError> {
    let Some(state) = load_state(config_dir)? else {
        say!("{}", not_set_up());
        return Ok(ExitCode::from(EXIT_NOT_SET_UP));
    };
    let running = status(&state)? == ServerStatus::Running;
    if running {
        say!("Server: running on {HOST}:{}", state.port);
    } else {
        say!("Server: stopped");
    }
    say!("Data: {}", state.data_dir.display());
    if !running {
        return Ok(ExitCode::from(EXIT_FAILED));
    }
    match extensions(config_dir) {
        Ok(names) => {
            say!("Extensions: {}", names.join(", "));
            Ok(ExitCode::from(EXIT_HEALTHY))
        }
        Err(e) => {
            say!("Health: cannot connect: {e}");
            Ok(ExitCode::from(EXIT_FAILED))
        }
    }
}

/// Extensions installed in the app database, `vector` first.
fn extensions(config_dir: &Path) -> Result<Vec<String>, PgServerError> {
    let env = config_dir.join(APP_ENV_FILE_NAME);
    let info = read_conn_info(&env)?.ok_or_else(|| {
        std::io::Error::other(format!(
            "{} is missing; run \"bml server init\"",
            env.display()
        ))
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
