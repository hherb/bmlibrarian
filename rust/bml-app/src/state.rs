//! Where the app's configuration is and which screen it opens on: plain Rust,
//! no Tauri, so it is unit-tested.

use std::ffi::OsString;
use std::path::{Path, PathBuf};

use bml_db::library::load_library;
use bml_pgserver::state::{resolve_config_dir, CONFIG_DIR_ENV};
use serde::Serialize;

/// The screen the window opens on.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum StartScreen {
    /// Nothing set up yet: the wizard's first screen.
    Welcome,
    /// A library is recorded: straight to search (spec: re-opening after
    /// setup goes to screen 6), or to topic choice when none is chosen yet
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

/// [`StartScreen::Search`] when `config_dir` records a library, else
/// [`StartScreen::Welcome`] (an unreadable record is treated as none, so the
/// wizard runs and setup reports the problem in plain words).
#[must_use]
pub fn start_screen(config_dir: &Path) -> StartScreen {
    match load_library(config_dir) {
        Ok(Some(_)) => StartScreen::Search,
        _ => StartScreen::Welcome,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use bml_db::library::{ensure_library, Library};
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
    fn recorded_library_starts_at_search() {
        let cfg = tempfile::tempdir().unwrap();
        let library = Library {
            dir: cfg.path().join("library"),
        };
        ensure_library(cfg.path(), &library).unwrap();
        assert_eq!(start_screen(cfg.path()), StartScreen::Search);
    }
}
