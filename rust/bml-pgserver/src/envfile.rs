//! The owner-only files holding the server's connection credentials.
//!
//! `bml.env` holds the app role, `bml-admin.env` the superuser. Passwords are
//! generated here and never typed by the user.

use std::fs;
use std::io::{self, Write};
use std::path::{Path, PathBuf};

/// File holding the app role's connection.
pub const APP_ENV_FILE_NAME: &str = "bml.env";

/// File holding the superuser's connection.
pub const ADMIN_ENV_FILE_NAME: &str = "bml-admin.env";

/// Random bytes per generated password (64 hex characters).
pub const PASSWORD_BYTES: usize = 32;

/// Owner read/write only.
#[cfg(unix)]
const PRIVATE_MODE: u32 = 0o600;

const KEY_HOST: &str = "POSTGRES_HOST";
const KEY_PORT: &str = "POSTGRES_PORT";
const KEY_DB: &str = "POSTGRES_DB";
const KEY_USER: &str = "POSTGRES_USER";
const KEY_PASSWORD: &str = "POSTGRES_PASSWORD";

/// One PostgreSQL connection's parameters.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ConnInfo {
    /// Host name or address.
    pub host: String,
    /// TCP port.
    pub port: u16,
    /// Database name.
    pub dbname: String,
    /// Role name.
    pub user: String,
    /// Role password.
    pub password: String,
}

/// Why an env file could not be read.
#[derive(Debug, thiserror::Error)]
pub enum EnvFileError {
    /// The file exists but could not be read.
    #[error("cannot read {path}: {source}")]
    Io {
        /// The file.
        path: PathBuf,
        /// The underlying error.
        source: io::Error,
    },
    /// A required key is missing.
    #[error("missing {key}")]
    MissingKey {
        /// The key.
        key: &'static str,
    },
    /// `POSTGRES_PORT` is not a port number.
    #[error("invalid POSTGRES_PORT {value:?}")]
    BadPort {
        /// The value found.
        value: String,
    },
    /// A file failed to parse.
    #[error("{path}: {source}")]
    Invalid {
        /// The file.
        path: PathBuf,
        /// What was wrong.
        source: Box<EnvFileError>,
    },
}

/// A new random password: lowercase hex, so it needs no quoting in SQL
/// string literals or env files.
pub fn generate_password() -> String {
    let mut bytes = [0u8; PASSWORD_BYTES];
    getrandom::fill(&mut bytes).expect("the OS random number generator is unavailable");
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

/// The env-file text for `info`.
pub fn render_env(info: &ConnInfo) -> String {
    format!(
        "{KEY_HOST}={}\n{KEY_PORT}={}\n{KEY_DB}={}\n{KEY_USER}={}\n{KEY_PASSWORD}={}\n",
        info.host, info.port, info.dbname, info.user, info.password
    )
}

/// Parse env-file text written by [`render_env`].
pub fn parse_env(text: &str) -> Result<ConnInfo, EnvFileError> {
    let pairs: Vec<(&str, &str)> = text
        .lines()
        .map(str::trim)
        .filter(|l| !l.is_empty() && !l.starts_with('#'))
        .filter_map(|l| l.split_once('='))
        .collect();
    let get = |key: &'static str| {
        pairs
            .iter()
            .rev()
            .find(|(k, _)| k.trim() == key)
            .map(|(_, v)| v.trim().to_owned())
            .ok_or(EnvFileError::MissingKey { key })
    };
    let port_text = get(KEY_PORT)?;
    let port = port_text
        .parse()
        .map_err(|_| EnvFileError::BadPort { value: port_text })?;
    Ok(ConnInfo {
        host: get(KEY_HOST)?,
        port,
        dbname: get(KEY_DB)?,
        user: get(KEY_USER)?,
        password: get(KEY_PASSWORD)?,
    })
}

/// Read the env file at `path`; `Ok(None)` only when it does not exist.
pub fn read_conn_info(path: &Path) -> Result<Option<ConnInfo>, EnvFileError> {
    match fs::read_to_string(path) {
        Ok(text) => parse_env(&text)
            .map(Some)
            .map_err(|e| EnvFileError::Invalid {
                path: path.to_owned(),
                source: Box::new(e),
            }),
        Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(None),
        Err(source) => Err(EnvFileError::Io {
            path: path.to_owned(),
            source,
        }),
    }
}

/// Write `contents` to `path` so only the owner can read it, atomically
/// (a temporary file renamed over the target).
pub fn write_private_file(path: &Path, contents: &str) -> io::Result<()> {
    let mut tmp_name = path.as_os_str().to_owned();
    tmp_name.push(".tmp");
    let tmp = PathBuf::from(tmp_name);
    // A leftover from an interrupted write keeps its old mode; start fresh.
    match fs::remove_file(&tmp) {
        Ok(()) => {}
        Err(e) if e.kind() == io::ErrorKind::NotFound => {}
        Err(e) => return Err(e),
    }
    let mut options = fs::OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(PRIVATE_MODE);
    }
    let mut file = options.open(&tmp)?;
    file.write_all(contents.as_bytes())?;
    file.sync_all()?;
    drop(file);
    fs::rename(&tmp, path)?;
    #[cfg(windows)]
    restrict_to_owner(path)?;
    Ok(())
}

/// Remove inherited access and grant only the current user (Windows ACLs).
#[cfg(windows)]
fn restrict_to_owner(path: &Path) -> io::Result<()> {
    let user = std::env::var("USERNAME")
        .map_err(|_| io::Error::other("USERNAME is not set; cannot restrict file access"))?;
    let status = std::process::Command::new("icacls")
        .arg(path)
        .args(["/inheritance:r", "/grant:r"])
        .arg(format!("{user}:F"))
        .stdout(std::process::Stdio::null())
        .status()?;
    if status.success() {
        Ok(())
    } else {
        Err(io::Error::other(format!(
            "icacls failed on {}: {status}",
            path.display()
        )))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample() -> ConnInfo {
        ConnInfo {
            host: "127.0.0.1".into(),
            port: 5418,
            dbname: "bmlibrarian".into(),
            user: "bml_app".into(),
            password: generate_password(),
        }
    }

    #[test]
    fn password_is_64_hex() {
        let p = generate_password();
        assert_eq!(p.len(), 64);
        assert!(p.chars().all(|c| matches!(c, '0'..='9' | 'a'..='f')));
        assert_ne!(p, generate_password());
    }

    #[test]
    fn env_roundtrip() {
        let info = sample();
        assert_eq!(parse_env(&render_env(&info)).unwrap(), info);
    }

    #[test]
    fn env_missing_key_errors() {
        let text = render_env(&sample())
            .lines()
            .filter(|l| !l.starts_with("POSTGRES_PASSWORD"))
            .collect::<Vec<_>>()
            .join("\n");
        assert!(parse_env(&text).is_err());
    }

    #[test]
    fn read_missing_is_none() {
        let dir = tempfile::tempdir().unwrap();
        assert_eq!(read_conn_info(&dir.path().join("bml.env")).unwrap(), None);
    }

    #[test]
    fn read_garbage_is_err() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("bml.env");
        std::fs::write(&path, "not an env file").unwrap();
        assert!(read_conn_info(&path).is_err());
    }

    #[cfg(unix)]
    #[test]
    fn private_file_mode() {
        use std::os::unix::fs::PermissionsExt;
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("bml.env");
        write_private_file(&path, "a").unwrap();
        assert_eq!(
            std::fs::metadata(&path).unwrap().permissions().mode() & 0o777,
            0o600
        );

        let loose = dir.path().join("loose.env");
        std::fs::write(&loose, "old").unwrap();
        std::fs::set_permissions(&loose, std::fs::Permissions::from_mode(0o644)).unwrap();
        write_private_file(&loose, "new").unwrap();
        assert_eq!(
            std::fs::metadata(&loose).unwrap().permissions().mode() & 0o777,
            0o600
        );
        assert_eq!(std::fs::read_to_string(&loose).unwrap(), "new");
    }
}
