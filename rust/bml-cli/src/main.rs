//! `bml`: the BMLibrarian command-line tool.

mod server;

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
}

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
    });
    result.unwrap_or_else(|e| {
        eprintln!("error: {e}");
        ExitCode::from(server::EXIT_FAILED)
    })
}
