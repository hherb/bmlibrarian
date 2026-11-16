//! Where the app's configuration is and which screen it opens on: plain Rust,
//! no Tauri, so it is unit-tested.

use std::ffi::OsString;
use std::path::{Path, PathBuf};

use bml_db::library::load_library;
use bml_pgserver::state::{resolve_config_dir, CONFIG_DIR_ENV};
use bml_setup::gguf_path;
use serde::Serialize;

/// The screen the window opens on.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum StartScreen {
    /// Nothing set up yet: the wizard's first screen.
    Welcome,
    /// Setup reached its last step (a library is recorded and the embedding
    /// model is in place): straight to search (spec: re-opening after setup
    /// goes to screen 6), or to topic choice when none is chosen yet
    /// (`LibraryCounts::needs_topic`).
    Search,
}

/// The configuration folder from `env` (the value of [`CONFIG_DIR_ENV`]),
/// else `home`'s default, as `bml` resolves it.
///
/// # Errors
///
/// Neither is given, or the path cannot be made absolute.
pub fn config_dir_from(env: Option<OsString>, home: Option<PathBuf>) -> Result<PathBuf, String> {
    resolve_config_dir(None, env, home).map_err(|e| e.to_string())
}

/// The configuration folder for this run: `$BML_CONFIG_DIR`, else
/// `~/.bmlibrarian`. The demo opens the prepared library with the variable;
/// the live install uses the default.
///
/// # Errors
///
/// As [`config_dir_from`].
pub fn config_dir() -> Result<PathBuf, String> {
    config_dir_from(std::env::var_os(CONFIG_DIR_ENV), std::env::home_dir())
}

/// [`StartScreen::Search`] when `config_dir` records a library and holds the
/// embedding model, else [`StartScreen::Welcome`] (an unreadable record is
/// treated as none, so the wizard runs and setup reports the problem in plain
/// words).
///
/// Setup records the library early but downloads the model last, so a window
/// closed mid-setup must reopen the wizard (safe to re-run), not a library
/// that cannot update or search (#462). The model download is
/// atomic (verified, then renamed into place), so its presence means the last
/// step got there.
#[must_use]
pub fn start_screen(config_dir: &Path) -> StartScreen {
    match load_library(config_dir) {
        Ok(Some(_)) if gguf_path(config_dir).is_file() => StartScreen::Search,
        _ => StartScreen::Welcome,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use bml_db::library::{ensure_library, Library, LIBRARY_FILE_NAME};
    use std::ffi::OsString;
    use std::path::PathBuf;

    #[test]
    fn config_dir_comes_from_env_then_default() {
        let home = PathBuf::from("/Users/demo");
        assert_eq!(
            config_dir_from(Some(OsString::from("/tmp/live-demo")), Some(home.clone())).unwrap(),
            PathBuf::from("/tmp/live-demo")
        );
        assert_eq!(
            config_dir_from(None, Some(home.clone())).unwrap(),
            home.join(".bmlibrarian")
        );
        // An empty variable is no setting.
        assert_eq!(
            config_dir_from(Some(OsString::new()), Some(home.clone())).unwrap(),
            home.join(".bmlibrarian")
        );
        assert!(config_dir_from(None, None).is_err());
    }

    #[test]
    fn fresh_config_starts_at_welcome() {
        let cfg = tempfile::tempdir().unwrap();
        assert_eq!(start_screen(cfg.path()), StartScreen::Welcome);
    }

    #[test]
    fn finished_setup_starts_at_search() {
        let cfg = tempfile::tempdir().unwrap();
        let library = Library {
            dir: cfg.path().join("library"),
        };
        ensure_library(cfg.path(), &library).unwrap();
        // Library recorded, model not yet downloaded: setup stopped midway.
        assert_eq!(start_screen(cfg.path()), StartScreen::Welcome);
        let gguf = gguf_path(cfg.path());
        std::fs::create_dir_all(gguf.parent().unwrap()).unwrap();
        std::fs::write(&gguf, b"").unwrap();
        assert_eq!(start_screen(cfg.path()), StartScreen::Search);
    }

    #[test]
    fn cut_off_model_download_starts_at_welcome() {
        let cfg = tempfile::tempdir().unwrap();
        let library = Library {
            dir: cfg.path().join("library"),
        };
        ensure_library(cfg.path(), &library).unwrap();
        // A download stopped midway leaves only its hidden part file.
        let gguf = gguf_path(cfg.path());
        let name = gguf.file_name().unwrap().to_string_lossy();
        std::fs::create_dir_all(gguf.parent().unwrap()).unwrap();
        std::fs::write(gguf.with_file_name(format!(".{name}.1.part")), b"").unwrap();
        assert_eq!(start_screen(cfg.path()), StartScreen::Welcome);
    }

    #[test]
    fn unreadable_library_record_starts_at_welcome() {
        let cfg = tempfile::tempdir().unwrap();
        let gguf = gguf_path(cfg.path());
        std::fs::create_dir_all(gguf.parent().unwrap()).unwrap();
        std::fs::write(&gguf, b"").unwrap();
        std::fs::write(cfg.path().join(LIBRARY_FILE_NAME), b"{not json").unwrap();
        assert_eq!(start_screen(cfg.path()), StartScreen::Welcome);
    }
}
