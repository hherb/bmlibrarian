//! The state file recording where the private server lives, and the
//! configuration folder that holds it.

use std::ffi::OsString;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

use crate::envfile::write_private_file;

/// The state file's name inside the configuration folder.
pub const STATE_FILE_NAME: &str = "bml-pgserver.json";

/// Environment variable overriding the configuration folder.
pub const CONFIG_DIR_ENV: &str = "BML_CONFIG_DIR";

/// The configuration folder's name under the home directory.
pub const CONFIG_DIR_NAME: &str = ".bmlibrarian";

/// Where the private server's binaries, data and port are.
#[derive(Serialize, Deserialize, Debug, Clone, PartialEq, Eq)]
pub struct ServerState {
    /// Folder with `postgres`, `pg_ctl`, `initdb`.
    pub bindir: PathBuf,
    /// The server's data directory.
    pub data_dir: PathBuf,
    /// TCP port on `127.0.0.1`.
    pub port: u16,
    /// Extension folders (each with `lib/postgresql`, `share/postgresql`).
    pub extension_dirs: Vec<PathBuf>,
}

/// Why the state file or configuration folder could not be used.
#[derive(Debug, thiserror::Error)]
pub enum StateError {
    /// The state file exists but is not valid.
    #[error("{path} is corrupt: {source}")]
    Corrupt {
        /// The state file.
        path: PathBuf,
        /// The parse error.
        source: serde_json::Error,
    },
    /// Reading or writing failed.
    #[error("{path}: {source}")]
    Io {
        /// The file or folder.
        path: PathBuf,
        /// The underlying error.
        source: io::Error,
    },
    /// No configuration folder was given and no home directory is known.
    #[error("cannot find the home directory; pass --config-dir or set {CONFIG_DIR_ENV}")]
    NoHome,
}

/// The JSON file `file_name` in `config_dir`; `Ok(None)` only when absent.
pub(crate) fn load_json<T: serde::de::DeserializeOwned>(
    config_dir: &Path,
    file_name: &str,
) -> Result<Option<T>, StateError> {
    let path = config_dir.join(file_name);
    match fs::read_to_string(&path) {
        Ok(text) => serde_json::from_str(&text)
            .map(Some)
            .map_err(|source| StateError::Corrupt { path, source }),
        Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(None),
        Err(source) => Err(StateError::Io { path, source }),
    }
}

/// Save `value` as the owner-only JSON file `file_name` in `config_dir`,
/// creating the folder if needed.
pub(crate) fn save_json<T: Serialize>(
    config_dir: &Path,
    file_name: &str,
    value: &T,
) -> Result<(), StateError> {
    fs::create_dir_all(config_dir).map_err(|source| StateError::Io {
        path: config_dir.to_owned(),
        source,
    })?;
    let path = config_dir.join(file_name);
    let text = serde_json::to_string_pretty(value).map_err(|e| StateError::Io {
        path: path.clone(),
        source: io::Error::other(e),
    })?;
    write_private_file(&path, &text).map_err(|source| StateError::Io { path, source })
}

/// The state saved in `config_dir`; `Ok(None)` only when there is none.
pub fn load_state(config_dir: &Path) -> Result<Option<ServerState>, StateError> {
    load_json(config_dir, STATE_FILE_NAME)
}

/// Save `state` in `config_dir`, creating the folder if needed.
pub fn save_state(config_dir: &Path, state: &ServerState) -> Result<(), StateError> {
    save_json(config_dir, STATE_FILE_NAME, state)
}

/// The configuration folder: `flag`, else `env` (if non-empty), else
/// `home/.bmlibrarian`; made absolute, because it is recorded in the login
/// start entry, which runs from another working directory.
pub fn resolve_config_dir(
    flag: Option<PathBuf>,
    env: Option<OsString>,
    home: Option<PathBuf>,
) -> Result<PathBuf, StateError> {
    let dir = flag
        .or_else(|| env.filter(|v| !v.is_empty()).map(PathBuf::from))
        .or_else(|| home.map(|h| h.join(CONFIG_DIR_NAME)))
        .ok_or(StateError::NoHome)?;
    std::path::absolute(&dir).map_err(|source| StateError::Io { path: dir, source })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample() -> ServerState {
        ServerState {
            bindir: "/Applications/Postgres 2.app/Contents/Versions/18/bin".into(),
            data_dir: "/Volumes/Big Disk/bml data".into(),
            port: 5418,
            extension_dirs: vec!["/ext/pg_search-0.26.1".into()],
        }
    }

    #[test]
    fn roundtrip() {
        let dir = tempfile::tempdir().unwrap();
        let cfg = dir.path().join("cfg");
        save_state(&cfg, &sample()).unwrap();
        assert_eq!(load_state(&cfg).unwrap(), Some(sample()));
    }

    #[test]
    fn state_with_retired_pg_major_field_loads() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(
            dir.path().join(STATE_FILE_NAME),
            r#"{"pg_major":18,"bindir":"/b","data_dir":"/d","port":5418,"extension_dirs":[]}"#,
        )
        .unwrap();
        assert_eq!(load_state(dir.path()).unwrap().unwrap().port, 5418);
    }

    #[test]
    fn missing_is_none() {
        let dir = tempfile::tempdir().unwrap();
        assert_eq!(load_state(dir.path()).unwrap(), None);
    }

    #[test]
    fn corrupt_is_error_with_path() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join(STATE_FILE_NAME), "{not json").unwrap();
        let err = load_state(dir.path()).unwrap_err();
        assert!(matches!(err, StateError::Corrupt { .. }));
        assert!(err.to_string().contains("bml-pgserver.json"));
    }

    #[test]
    fn resolve_precedence() {
        let flag = Some(PathBuf::from("/flag"));
        let env = Some(OsString::from("/env"));
        let home = Some(PathBuf::from("/home/u"));
        assert_eq!(
            resolve_config_dir(flag, env.clone(), home.clone()).unwrap(),
            std::path::absolute("/flag").unwrap()
        );
        assert_eq!(
            resolve_config_dir(None, env, home.clone()).unwrap(),
            std::path::absolute("/env").unwrap()
        );
        assert_eq!(
            resolve_config_dir(None, None, home).unwrap(),
            std::path::absolute("/home/u/.bmlibrarian").unwrap()
        );
        assert!(matches!(
            resolve_config_dir(None, None, None),
            Err(StateError::NoHome)
        ));
        let relative = resolve_config_dir(Some("rel/cfg".into()), None, None).unwrap();
        assert!(relative.is_absolute(), "{}", relative.display());
        assert!(relative.ends_with("rel/cfg"));
    }
}
