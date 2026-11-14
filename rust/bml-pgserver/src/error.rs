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
    /// A credentials file could not be read or parsed.
    #[error(transparent)]
    EnvFile(#[from] EnvFileError),
    /// The state file or configuration folder could not be used.
    #[error(transparent)]
    State(#[from] StateError),
    /// An operation not tied to one file failed (no `From`, so that file
    /// errors must name their file through [`PgServerError::File`]).
    #[error(transparent)]
    Io(io::Error),
    /// A database operation failed.
    #[error("database error: {}", describe_postgres_error(.0))]
    Postgres(#[from] postgres::Error),
    /// Connecting to the server failed.
    #[error("cannot connect to database {dbname} as {user} on {host}:{port}: {}", describe_postgres_error(.source))]
    Connect {
        /// The role.
        user: String,
        /// The database.
        dbname: String,
        /// The server address.
        host: String,
        /// The server port.
        port: u16,
        /// Why it failed.
        source: postgres::Error,
    },
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
    #[error("{program} failed ({}){}", describe_exit(*.status), describe_stderr(.stderr))]
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
    /// The folder is a PostgreSQL data directory that our state file does
    /// not name and that holds no `bml.conf`, so it belongs to another server
    /// and is left alone.
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
    /// gone, so `init` can no longer repair or finish the setup (start, stop
    /// and status still work).
    #[error("{data_dir} is set up, but its admin credentials file {admin_env} is missing; restore it from a backup (the server is left untouched)")]
    AdminCredentialsLost {
        /// The data directory.
        data_dir: PathBuf,
        /// The missing credentials file.
        admin_env: PathBuf,
    },
    /// A required extension is not installed for this PostgreSQL.
    #[error("the PostgreSQL extension {name} is not available on this server; install it for this PostgreSQL or pass --extension-dir")]
    ExtensionUnavailable {
        /// The extension.
        name: &'static str,
    },
    /// The state file describes a different server than the one requested.
    #[error("this configuration folder already manages a server with {field} {saved}, not {requested}; use that path, or a different --config-dir")]
    StateMismatch {
        /// The differing field.
        field: &'static str,
        /// The value saved in the state file.
        saved: PathBuf,
        /// The value requested.
        requested: PathBuf,
    },
    /// Start at login or the update schedule failed, and its file could not
    /// be put back as it was.
    #[error("{error}. Also, {} could not be put back as it was ({source}); check or delete it by hand, or the next run may think it is set up", path.display())]
    AutostartLeftover {
        /// Why start at login failed.
        error: Box<PgServerError>,
        /// The login entry file left behind.
        path: PathBuf,
        /// Why it could not be removed or restored.
        source: io::Error,
    },
    /// Start at login or the update schedule failed; its file was put back
    /// on disk as it was but could not be loaded again now.
    #[error("{error}. {} was put back as it was, but could not be loaded again now ({source}); that happens at the next login, or run the command again", path.display())]
    AutostartNotReloaded {
        /// Why start at login failed.
        error: Box<PgServerError>,
        /// The restored login entry file.
        path: PathBuf,
        /// Why loading it again failed.
        source: Box<PgServerError>,
    },
    /// The configuration folder already uses another existing server.
    #[error("this configuration folder already uses the existing PostgreSQL at {saved}, not {requested}; pass --existing-server {saved}, or use a different --config-dir for the other server")]
    ExistingServerMismatch {
        /// `host:port` saved in the state file.
        saved: String,
        /// `host:port` requested.
        requested: String,
    },
    /// The server set up before is gone: its data folder is missing or
    /// empty (an unmounted disk, or deleted).
    #[error("the server's data folder {path} is missing or empty (is its disk mounted?); nothing was changed. To set up a new server there instead, delete {state_file} and run init again")]
    DataDirMissing {
        /// The data folder.
        path: PathBuf,
        /// The state file naming it.
        state_file: PathBuf,
    },
    /// A first `init` was interrupted while `initdb` ran, leaving a
    /// half-written data folder that cannot be resumed.
    #[error("{path} was left half set up by an interrupted first init; if you have not stored anything in it, delete it and run init again (nothing was changed)")]
    IncompleteDataDir {
        /// The data folder.
        path: PathBuf,
    },
    /// The data folder `pg_ctl` was pointed at is missing, unreadable or not
    /// a PostgreSQL data folder.
    #[error("the data folder {path} is missing, unreadable or not a PostgreSQL data folder (is its disk mounted?)")]
    DataDirUnavailable {
        /// The data folder.
        path: PathBuf,
    },
    /// The server did not start; its log usually says why.
    #[error("{source}\nlast lines of the server log {log}:\n{tail}")]
    StartFailed {
        /// The server log.
        log: PathBuf,
        /// Its last lines (empty if it could not be read).
        tail: String,
        /// What `pg_ctl start` reported.
        source: Box<PgServerError>,
    },
    /// A path is not valid Unicode, so it cannot be written into the
    /// server's configuration or the state file.
    #[error("{path} is not valid Unicode; choose a folder whose name is")]
    NonUnicodePath {
        /// The path.
        path: PathBuf,
    },
    /// An `--extension-dir` cannot be used.
    #[error("extension folder {path}: {reason}")]
    BadExtensionDir {
        /// The folder.
        path: PathBuf,
        /// What is wrong with it.
        reason: String,
    },
    /// `postgres --version` printed something we do not understand.
    #[error("{program} --version printed unrecognised output: {output}")]
    UnrecognisedVersion {
        /// The program.
        program: PathBuf,
        /// What it printed.
        output: String,
    },
    /// The PostgreSQL binaries are older than required.
    #[error("PostgreSQL {found} found; version {min} or newer is required", min = crate::control::MIN_PG_MAJOR)]
    UnsupportedVersion {
        /// The major version found.
        found: u32,
    },
    /// Adopting an existing server is only allowed on this computer.
    #[error("The PostgreSQL server at {host} is not on this computer. The database must run on this computer (127.0.0.1, ::1 or localhost); install or start PostgreSQL here, or use --pg-bindir instead")]
    NotLoopback {
        /// The refused host.
        host: String,
    },
    /// The existing server lacks something bml needs.
    #[error("This PostgreSQL can't be used: {}", join_problems(.problems))]
    Unusable {
        /// Everything that is wrong, in one list.
        problems: Vec<crate::external::Unusable>,
    },
    /// The role or database bml would create is already there.
    #[error("the {kind} {name} already exists on that server and was not created by bml; bml never reuses or changes it")]
    NameTaken {
        /// `"role"` or `"database"`.
        kind: &'static str,
        /// Its name.
        name: &'static str,
    },
    /// This configuration folder already manages a private server.
    #[error("this configuration folder already manages a private server ({state_file}); use a different --config-dir for the other server")]
    PrivateServerConfigured {
        /// The private server's state file.
        state_file: PathBuf,
    },
    /// This configuration folder already uses an existing server.
    #[error("this configuration folder already uses an existing PostgreSQL ({state_file}); use a different --config-dir for the other server")]
    ExternalServerConfigured {
        /// The existing-server state file.
        state_file: PathBuf,
    },
    /// The password cannot be kept in the credentials files.
    #[error("that password cannot be stored: it must not be empty, contain a control character such as a line break or tab, or start or end with whitespace")]
    PasswordNotStorable,
    /// The superuser name cannot be kept in the credentials files.
    #[error("that superuser name cannot be stored: it must not be empty, contain a control character such as a line break or tab, or start or end with whitespace")]
    SuperuserNotStorable,
    /// The credentials file already holds another server's superuser.
    #[error("{admin_env} holds the credentials of another PostgreSQL server ({host}:{port}, user {user}); bml will not overwrite them. Use a different --config-dir for the existing server")]
    AdminCredentialsInUse {
        /// The credentials file.
        admin_env: PathBuf,
        /// The host it names.
        host: String,
        /// The port it names.
        port: u16,
        /// The user it names.
        user: String,
    },
}

/// Joins the problems of an unusable server for [`PgServerError::Unusable`].
fn join_problems(problems: &[crate::external::Unusable]) -> String {
    problems
        .iter()
        .map(ToString::to_string)
        .collect::<Vec<_>>()
        .join("; ")
}

/// A process exit for messages: the code, or that a signal killed it.
fn describe_exit(status: Option<i32>) -> String {
    match status {
        Some(code) => format!("exit code {code}"),
        None => "killed by a signal".to_owned(),
    }
}

/// `": <stderr>"`, or nothing when the tool printed nothing.
fn describe_stderr(stderr: &str) -> String {
    if stderr.is_empty() {
        String::new()
    } else {
        format!(": {stderr}")
    }
}

/// A `map_err` adapter turning an IO error on `path` into
/// [`PgServerError::File`].
pub(crate) fn file_error(path: &std::path::Path) -> impl FnOnce(io::Error) -> PgServerError + '_ {
    move |source| PgServerError::File {
        path: path.to_owned(),
        source,
    }
}

/// The server's own message for a database error (`postgres::Error`'s
/// `Display` is only "db error") with its detail, SQLSTATE and hint, else
/// the whole cause chain.
fn describe_postgres_error(error: &postgres::Error) -> String {
    if let Some(db) = error.as_db_error() {
        let mut text = db.message().to_owned();
        if let Some(detail) = db.detail() {
            text.push_str(&format!(" ({detail})"));
        }
        text.push_str(&format!(" [SQLSTATE {}]", db.code().code()));
        if let Some(hint) = db.hint() {
            text.push_str(&format!("; hint: {hint}"));
        }
        return text;
    }
    let mut text = error.to_string();
    let mut source = std::error::Error::source(error);
    while let Some(cause) = source {
        text.push_str(&format!(": {cause}"));
        source = cause.source();
    }
    text
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn command_error_reads_well() {
        let killed = PgServerError::Command {
            program: "pg_ctl".into(),
            status: None,
            stderr: String::new(),
        };
        assert_eq!(killed.to_string(), "pg_ctl failed (killed by a signal)");
        let failed = PgServerError::Command {
            program: "pg_ctl".into(),
            status: Some(1),
            stderr: "boom".into(),
        };
        assert_eq!(failed.to_string(), "pg_ctl failed (exit code 1): boom");
    }
}
