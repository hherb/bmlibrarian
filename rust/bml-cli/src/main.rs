//! `bml`: the BMLibrarian command-line tool.

mod library;
mod server;
mod setup;

use std::path::PathBuf;
use std::process::ExitCode;

use bml_pgserver::state::{resolve_config_dir, CONFIG_DIR_ENV};
use clap::{Parser, Subcommand};

/// BMLibrarian command-line tool.
#[derive(Parser)]
#[command(name = "bml", version, about)]
struct Cli {
    /// Configuration folder (default: $BML_CONFIG_DIR, else ~/.bmlibrarian).
    #[arg(long, global = true, value_name = "PATH")]
    config_dir: Option<PathBuf>,

    #[command(subcommand)]
    command: Command,
}

/// Top-level command groups.
#[derive(Subcommand)]
enum Command {
    /// Manage the private PostgreSQL server.
    #[command(subcommand)]
    Server(server::ServerCommand),
    /// Check this computer and install what BMLibrarian needs (safe to run again).
    Setup(setup::SetupArgs),
    /// Download, update and index the medRxiv library.
    #[command(subcommand)]
    Library(library::LibraryCommand),
}

/// Parse the command line, run the command and map errors to exit code 1.
fn main() -> ExitCode {
    let cli = Cli::parse();
    let result = resolve_config_dir(
        cli.config_dir,
        std::env::var_os(CONFIG_DIR_ENV),
        std::env::home_dir(),
    )
    .map_err(Into::into)
    .and_then(|config_dir| match cli.command {
        Command::Server(command) => server::run(command, &config_dir),
        Command::Setup(args) => setup::run(args, &config_dir),
        Command::Library(command) => Ok(library::run(command, &config_dir).unwrap_or_else(|e| {
            eprintln!("error: {e}");
            ExitCode::from(server::EXIT_FAILED)
        })),
    });
    result.unwrap_or_else(|e| {
        eprintln!("error: {e}");
        ExitCode::from(server::EXIT_FAILED)
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::Path;

    /// The command lines the schedulers store must still parse, or every
    /// scheduled run would fail with a usage error into a log nobody reads.
    #[test]
    fn the_scheduled_command_lines_parse() {
        let (exe, cfg) = (Path::new("/opt/bml"), Path::new("/home/u/.bmlibrarian"));
        let cli = Cli::try_parse_from(bml_pgserver::schedule::update_args(exe, cfg, 7)).unwrap();
        assert_eq!(cli.config_dir.as_deref(), Some(cfg));
        assert!(matches!(
            cli.command,
            Command::Library(library::LibraryCommand::Update {
                if_older_than: Some(7),
                ..
            })
        ));
        let cli = Cli::try_parse_from(bml_pgserver::autostart::start_args(exe, cfg)).unwrap();
        assert_eq!(cli.config_dir.as_deref(), Some(cfg));
        assert!(matches!(
            cli.command,
            Command::Server(server::ServerCommand::Start)
        ));
    }
}
