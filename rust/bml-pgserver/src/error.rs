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
    #[error("database error: {0}")]
    Postgres(#[from] postgres::Error),
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
