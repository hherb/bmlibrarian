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

/// One PostgreSQL connection's parameters (`Debug` hides the password).
#[derive(Clone, PartialEq, Eq)]
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

impl std::fmt::Debug for ConnInfo {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("ConnInfo")
            .field("host", &self.host)
            .field("port", &self.port)
            .field("dbname", &self.dbname)
            .field("user", &self.user)
            .field("password", &"<redacted>")
            .finish()
    }
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
    /// `POSTGRES_PASSWORD` is not the hex we generate. It is pasted into SQL
    /// string literals, so nothing else is accepted (the value is not shown).
    #[error("invalid POSTGRES_PASSWORD (expected hexadecimal digits only)")]
    BadPassword,
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
    let password = get(KEY_PASSWORD)?;
    if !is_valid_password(&password) {
        return Err(EnvFileError::BadPassword);
    }
    Ok(ConnInfo {
        host: get(KEY_HOST)?,
        port,
        dbname: get(KEY_DB)?,
        user: get(KEY_USER)?,
        password,
    })
}

/// Whether `password` is non-empty hex, the only form safe inside a SQL
/// string literal without quoting.
pub fn is_valid_password(password: &str) -> bool {
    !password.is_empty() && password.bytes().all(|b| b.is_ascii_hexdigit())
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
/// (a temporary file, made owner-only before it is renamed over the target).
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
    // Restricted before the rename, so the target never has loose access
    // and a failure leaves it unchanged (and retried by the next write).
    #[cfg(windows)]
    if let Err(e) = restrict_to_owner(&tmp) {
        let _ = fs::remove_file(&tmp);
        return Err(e);
    }
    fs::rename(&tmp, path)
}

/// Remove inherited access and grant only the current user (Windows ACLs).
#[cfg(windows)]
fn restrict_to_owner(path: &Path) -> io::Result<()> {
    let name = std::env::var("USERNAME")
        .map_err(|_| io::Error::other("USERNAME is not set; cannot restrict file access"))?;
    // Qualified, so a local account with the same name is never picked.
    let user = match std::env::var("USERDOMAIN") {
        Ok(domain) if !domain.is_empty() => format!("{domain}\\{name}"),
        _ => name,
    };
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
    fn password_must_be_hex() {
        let with = |password: &str| {
            format!(
                "POSTGRES_HOST=127.0.0.1\nPOSTGRES_PORT=5418\nPOSTGRES_DB=bmlibrarian\n\
                 POSTGRES_USER=bml_app\nPOSTGRES_PASSWORD={password}\n"
            )
        };
        assert!(matches!(
            parse_env(&with("x' OR '1")),
            Err(EnvFileError::BadPassword)
        ));
        assert!(matches!(
            parse_env(&with("")),
            Err(EnvFileError::BadPassword)
        ));
        assert_eq!(parse_env(&with("00ff")).unwrap().password, "00ff");
    }

    #[test]
    fn debug_hides_password() {
        let info = sample();
        let shown = format!("{info:?}");
        assert!(!shown.contains(&info.password), "{shown}");
        assert!(shown.contains("<redacted>"));
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

        // A world-readable temp file left by an interrupted write.
        let fresh = dir.path().join("fresh.env");
        let stale_tmp = dir.path().join("fresh.env.tmp");
        std::fs::write(&stale_tmp, "stale").unwrap();
        std::fs::set_permissions(&stale_tmp, std::fs::Permissions::from_mode(0o644)).unwrap();
        write_private_file(&fresh, "secret").unwrap();
        assert_eq!(
            std::fs::metadata(&fresh).unwrap().permissions().mode() & 0o777,
            0o600
        );
        assert!(!stale_tmp.exists());
    }
}
