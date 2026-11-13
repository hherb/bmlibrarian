//! The library folder: where a person's papers live (`documents/`, a bmlib
//! [`FullTextCache`]) and, for a private server set up by bml, its database
//! (`database/`). Its path is recorded once in the configuration folder.

use std::io;
use std::path::{Path, PathBuf};

use bmlib::fulltext::cache::FullTextCache;
use serde::{Deserialize, Serialize};

/// The record of the library folder, inside the configuration folder.
pub const LIBRARY_FILE_NAME: &str = "bml-library.json";
/// The default library folder's name under the home folder.
pub const DEFAULT_LIBRARY_DIR_NAME: &str = "BMLibrarian";
/// The private server's data folder inside the library.
pub const DATABASE_DIR_NAME: &str = "database";
/// The document cache inside the library.
pub const DOCUMENTS_DIR_NAME: &str = "documents";

/// Where the library lives.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Library {
    /// The library folder (absolute).
    pub dir: PathBuf,
}

/// Why the library folder could not be chosen or set up.
#[derive(Debug, thiserror::Error)]
pub enum LibraryError {
    /// No home folder, no saved library and none requested.
    #[error("cannot find your home folder to put the library in; choose a library folder with --library-dir")]
    NoHome,
    /// A different folder was asked for than the saved library.
    #[error("your library is already in {saved}, so it cannot be set up in {requested}; moving a library is not supported yet. Leave out --library-dir to keep using it.")]
    Mismatch {
        /// The saved library folder.
        saved: PathBuf,
        /// The folder asked for.
        requested: PathBuf,
    },
    /// The library path exists but is not a folder.
    #[error("{0} is a file, not a folder; choose another library folder")]
    NotAFolder(PathBuf),
    /// Reading or writing failed.
    #[error("could not use {path}: {source}")]
    Io {
        /// The path concerned.
        path: PathBuf,
        /// What went wrong.
        #[source]
        source: io::Error,
    },
    /// The library record cannot be read.
    #[error("the library record {path} is damaged ({message}); delete it and run setup again with --library-dir")]
    Corrupt {
        /// The record file.
        path: PathBuf,
        /// What is wrong with it.
        message: String,
    },
}

impl Library {
    /// The private server's data folder (created by `initdb`, not here).
    #[must_use]
    pub fn database_dir(&self) -> PathBuf {
        self.dir.join(DATABASE_DIR_NAME)
    }

    /// The document cache's root.
    #[must_use]
    pub fn documents_dir(&self) -> PathBuf {
        self.dir.join(DOCUMENTS_DIR_NAME)
    }

    /// The bmlib full-text cache rooted at [`Library::documents_dir`].
    #[must_use]
    pub fn cache(&self) -> FullTextCache {
        FullTextCache {
            cache_dir: self.documents_dir(),
        }
    }
}

fn absolute(path: &Path) -> Result<PathBuf, LibraryError> {
    std::path::absolute(path).map_err(|source| LibraryError::Io {
        path: path.to_path_buf(),
        source,
    })
}

/// The saved library, if any.
///
/// # Errors
///
/// The record cannot be read, or is damaged.
pub fn load_library(config_dir: &Path) -> Result<Option<Library>, LibraryError> {
    let path = config_dir.join(LIBRARY_FILE_NAME);
    let text = match std::fs::read_to_string(&path) {
        Ok(text) => text,
        Err(e) if e.kind() == io::ErrorKind::NotFound => return Ok(None),
        Err(source) => return Err(LibraryError::Io { path, source }),
    };
    serde_json::from_str(&text)
        .map(Some)
        .map_err(|e| LibraryError::Corrupt {
            path,
            message: e.to_string(),
        })
}

/// The library to use, without writing anything: the saved one (which a
/// different `requested` folder may not replace), else `requested`, else
/// `home/`[`DEFAULT_LIBRARY_DIR_NAME`]. The folder is always absolute, and a
/// path that exists as a file is refused here, before anything is set up.
///
/// # Errors
///
/// [`LibraryError::Mismatch`], [`LibraryError::NoHome`],
/// [`LibraryError::NotAFolder`], or the record cannot be read.
pub fn resolve_library(
    config_dir: &Path,
    requested: Option<&Path>,
    home: Option<PathBuf>,
) -> Result<Library, LibraryError> {
    let requested = requested.map(absolute).transpose()?;
    if let Some(saved) = load_library(config_dir)? {
        return match requested {
            Some(requested) if !same_folder(&requested, &saved.dir) => {
                Err(LibraryError::Mismatch {
                    saved: saved.dir,
                    requested,
                })
            }
            _ => checked(saved),
        };
    }
    let dir = match requested {
        Some(dir) => dir,
        None => absolute(
            &home
                .ok_or(LibraryError::NoHome)?
                .join(DEFAULT_LIBRARY_DIR_NAME),
        )?,
    };
    checked(Library { dir })
}

/// Whether `a` and `b` name one folder: equal paths, or both existing and
/// equal once symlinks and `..` are resolved (macOS's `/var` is
/// `/private/var`).
fn same_folder(a: &Path, b: &Path) -> bool {
    a == b
        || matches!(
            (std::fs::canonicalize(a), std::fs::canonicalize(b)),
            (Ok(x), Ok(y)) if x == y
        )
}

/// `library`, unless its folder exists as something other than a folder.
fn checked(library: Library) -> Result<Library, LibraryError> {
    if library.dir.exists() && !library.dir.is_dir() {
        return Err(LibraryError::NotAFolder(library.dir));
    }
    Ok(library)
}

/// Create the library folder and its `documents/`, and record it when no
/// library is recorded yet; returns whether anything was created or saved.
///
/// # Errors
///
/// The folder is a file ([`LibraryError::NotAFolder`]), or it or the record
/// cannot be written.
pub fn ensure_library(config_dir: &Path, library: &Library) -> Result<bool, LibraryError> {
    if library.dir.exists() && !library.dir.is_dir() {
        return Err(LibraryError::NotAFolder(library.dir.clone()));
    }
    let documents = library.documents_dir();
    let mut changed = !documents.is_dir();
    std::fs::create_dir_all(&documents).map_err(|source| LibraryError::Io {
        path: documents,
        source,
    })?;
    if load_library(config_dir)?.is_none() {
        let io_err = |path: &Path| {
            let path = path.to_path_buf();
            move |source| LibraryError::Io { path, source }
        };
        std::fs::create_dir_all(config_dir).map_err(io_err(config_dir))?;
        let path = config_dir.join(LIBRARY_FILE_NAME);
        let text = serde_json::to_string_pretty(library).map_err(|e| LibraryError::Io {
            path: path.clone(),
            source: io::Error::other(e),
        })?;
        bmlib::atomic::atomic_write(&path, text.as_bytes()).map_err(io_err(&path))?;
        changed = true;
    }
    Ok(changed)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn dirs() -> (tempfile::TempDir, PathBuf, PathBuf) {
        let tmp = tempfile::tempdir().unwrap();
        let cfg = tmp.path().join("config");
        let home = tmp.path().join("home");
        (tmp, cfg, home)
    }

    #[test]
    fn default_is_home_bmlibrarian() {
        let (_t, cfg, home) = dirs();
        let lib = resolve_library(&cfg, None, Some(home.clone())).unwrap();
        assert_eq!(lib.dir, home.join(DEFAULT_LIBRARY_DIR_NAME));
        assert_eq!(load_library(&cfg).unwrap(), None);
    }

    #[test]
    fn requested_wins_without_record() {
        let (t, cfg, home) = dirs();
        let wanted = t.path().join("lib");
        let lib = resolve_library(&cfg, Some(&wanted), Some(home)).unwrap();
        assert_eq!(lib.dir, wanted);
    }

    #[test]
    fn saved_record_wins_over_default() {
        let (t, cfg, home) = dirs();
        let saved = Library {
            dir: t.path().join("saved"),
        };
        ensure_library(&cfg, &saved).unwrap();
        assert_eq!(resolve_library(&cfg, None, Some(home)).unwrap(), saved);
    }

    #[test]
    fn requested_differing_from_saved_is_mismatch() {
        let (t, cfg, home) = dirs();
        let saved = Library {
            dir: t.path().join("saved"),
        };
        ensure_library(&cfg, &saved).unwrap();
        let other = t.path().join("other");
        let err = resolve_library(&cfg, Some(&other), Some(home.clone())).unwrap_err();
        assert!(matches!(err, LibraryError::Mismatch { .. }), "{err}");
        // The same folder, given relative to the current folder, is no
        // mismatch. Changing the current folder is safe here: no other test in
        // this crate resolves a relative path.
        let cwd = std::env::current_dir().unwrap();
        std::env::set_current_dir(t.path()).unwrap();
        let relative = resolve_library(&cfg, Some(Path::new("saved")), Some(home));
        std::env::set_current_dir(cwd).unwrap();
        assert_eq!(relative.unwrap(), saved);
        assert_eq!(
            resolve_library(&cfg, Some(&saved.dir), None).unwrap(),
            saved
        );
    }

    #[test]
    fn ensure_creates_documents_and_saves_once() {
        let (t, cfg, _home) = dirs();
        let lib = Library {
            dir: t.path().join("lib"),
        };
        assert!(ensure_library(&cfg, &lib).unwrap());
        assert!(lib.documents_dir().is_dir());
        assert!(!lib.database_dir().exists());
        assert_eq!(load_library(&cfg).unwrap(), Some(lib.clone()));
        assert!(!ensure_library(&cfg, &lib).unwrap());
        assert_eq!(lib.cache().cache_dir, lib.documents_dir());
    }

    #[test]
    fn file_as_library_is_refused() {
        let (t, cfg, _home) = dirs();
        let file = t.path().join("a-file");
        std::fs::write(&file, b"x").unwrap();
        let err = ensure_library(&cfg, &Library { dir: file.clone() }).unwrap_err();
        assert!(
            matches!(err, LibraryError::NotAFolder(ref p) if *p == file),
            "{err}"
        );
        assert_eq!(load_library(&cfg).unwrap(), None);
    }

    #[test]
    fn resolve_refuses_a_file_before_anything_is_set_up() {
        let (t, cfg, home) = dirs();
        let file = t.path().join("a-file");
        std::fs::write(&file, b"x").unwrap();
        let err = resolve_library(&cfg, Some(&file), Some(home)).unwrap_err();
        assert!(
            matches!(err, LibraryError::NotAFolder(ref p) if *p == file),
            "{err}"
        );
        assert_eq!(load_library(&cfg).unwrap(), None);
    }

    #[test]
    fn library_path_with_space_and_umlaut_round_trips() {
        let (t, cfg, _home) = dirs();
        let lib = Library {
            dir: t.path().join("My Library ü"),
        };
        assert!(ensure_library(&cfg, &lib).unwrap());
        assert!(lib.documents_dir().is_dir());
        assert_eq!(load_library(&cfg).unwrap(), Some(lib));
    }

    #[test]
    fn corrupt_record_is_reported() {
        let (_t, cfg, _home) = dirs();
        std::fs::create_dir_all(&cfg).unwrap();
        std::fs::write(cfg.join(LIBRARY_FILE_NAME), b"{not json").unwrap();
        let err = load_library(&cfg).unwrap_err();
        assert!(
            matches!(err, LibraryError::Corrupt { ref path, .. } if path.ends_with(LIBRARY_FILE_NAME)),
            "{err}"
        );
    }

    #[test]
    fn no_home_without_record_or_request() {
        let (_t, cfg, _home) = dirs();
        assert!(matches!(
            resolve_library(&cfg, None, None),
            Err(LibraryError::NoHome)
        ));
    }
}
