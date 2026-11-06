//! The error type of every server operation.

use std::io;

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
    /// The PostgreSQL binaries are older than required.
    #[error("PostgreSQL {found} found; version {min} or newer is required", min = crate::control::MIN_PG_MAJOR)]
    UnsupportedVersion {
        /// The major version found.
        found: u32,
    },
}
