//! `bml`: the BMLibrarian command-line tool.

use std::path::PathBuf;

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
    Server(ServerCommand),
}

/// `bml server …` subcommands.
#[derive(Subcommand)]
enum ServerCommand {
    /// Show whether the private server is set up and running.
    Status,
}

fn main() {
    let cli = Cli::parse();
    match cli.command {
        Command::Server(ServerCommand::Status) => {}
    }
}
