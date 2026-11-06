//! The error type of every server operation.

use std::io;
use std::path::PathBuf;

use crate::envfile::EnvFileError;
use crate::port::PortError;
use crate::state::StateError;

/// Anything that can go wrong managing the private server.
#[derive(Debug, thiserror::Error)]
pub enum PgServerError {
    /// No port could be chosen.
    #[error(transparent)]
    Port(#[from] PortError),
    /// A credentials file could not be read.
    #[error(transparent)]
    EnvFile(#[from] EnvFileError),
    /// The state file or configuration folder could not be used.
    #[error(transparent)]
    State(#[from] StateError),
    /// A file or process operation failed.
    #[error(transparent)]
    Io(#[from] io::Error),
    /// A database operation failed.
    #[error("database error: {}", describe_postgres_error(.0))]
    Postgres(#[from] postgres::Error),
    /// A program could not be run at all (usually a wrong `--bindir`).
    #[error("cannot run {program}: {source}")]
    Spawn {
        /// The program.
        program: PathBuf,
        /// Why it could not start.
        source: io::Error,
    },
    /// A file could not be read or written.
    #[error("{path}: {source}")]
    File {
        /// The file.
        path: PathBuf,
        /// The underlying error.
        source: io::Error,
    },
    /// A PostgreSQL tool exited unsuccessfully.
    #[error("{program} failed (exit {status:?}): {stderr}")]
    Command {
        /// The tool that ran.
        program: String,
        /// Its exit code, if it had one.
        status: Option<i32>,
        /// What it printed on stderr.
        stderr: String,
    },
    /// The data folder has files in it that are not a PostgreSQL data
    /// directory, so it is not ours to use.
    #[error(
        "{path} is not empty and is not a PostgreSQL data folder; choose an empty or new folder"
    )]
    DataDirNotEmpty {
        /// The folder.
        path: PathBuf,
    },
    /// The folder is a PostgreSQL data directory that this configuration
    /// did not set up, so it belongs to another server and is left alone.
    #[error("{path} is another PostgreSQL server's data folder; choose an empty or new folder (nothing was changed)")]
    ForeignDataDir {
        /// The folder.
        path: PathBuf,
    },
    /// A path contains a character `pg_ctl` cannot pass through the shell
    /// it uses to start the server.
    #[error("{path} contains the character {ch:?}, which PostgreSQL's server tools cannot handle; choose a folder without it")]
    UnsafePath {
        /// The path.
        path: PathBuf,
        /// The offending character.
        ch: char,
    },
    /// The data directory is initialised but its superuser password file is
    /// gone, so the server can no longer be managed.
    #[error("{data_dir} is set up, but its admin credentials file {admin_env} is missing; restore it from a backup (the server is left untouched)")]
    AdminCredentialsLost {
        /// The data directory.
        data_dir: PathBuf,
        /// The missing credentials file.
        admin_env: PathBuf,
    },
    /// A required extension is not installed for this PostgreSQL.
    #[error("the PostgreSQL extension {name} is not available on this server")]
    ExtensionUnavailable {
        /// The extension.
        name: &'static str,
    },
    /// The state file describes a different server than the one requested.
    #[error("this configuration folder already manages a server with a different {field}")]
    StateMismatch {
        /// The differing field.
        field: &'static str,
    },
    /// The PostgreSQL binaries are older than required.
    #[error("PostgreSQL {found} found; version {min} or newer is required", min = crate::control::MIN_PG_MAJOR)]
    UnsupportedVersion {
        /// The major version found.
        found: u32,
    },
}

/// The server's own message for a database error (`postgres::Error`'s
/// `Display` is only "db error"), else the whole cause chain.
fn describe_postgres_error(error: &postgres::Error) -> String {
    if let Some(db) = error.as_db_error() {
        return match db.detail() {
            Some(detail) => format!("{} ({detail})", db.message()),
            None => db.message().to_owned(),
        };
    }
    let mut text = error.to_string();
    let mut source = std::error::Error::source(error);
    while let Some(cause) = source {
        text.push_str(&format!(": {cause}"));
        source = cause.source();
    }
    text
}
