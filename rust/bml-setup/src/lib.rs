//! Guided first-run setup for BMLibrarian: the hardware check, database,
//! start at login, Ollama, the approved models and the embedding model, run
//! in order by [`runner::run_setup`] (the engine behind `bml setup`).

pub mod hardware;
pub mod models;
pub mod ollama;
pub mod ollama_install;
pub mod runner;
mod steps;

use std::path::{Path, PathBuf};

/// The lock file setup holds in the configuration folder while it downloads.
pub const DOWNLOAD_LOCK_FILE_NAME: &str = ".bml-setup-download.lock";

/// Lock downloads into `config_dir` for as long as the returned file is open,
/// so two setups (the CLI and the first-run screen) never sweep or overwrite
/// each other's downloads. Fails at once if another setup holds it; the
/// operating system releases it when a setup exits, even by a crash.
pub(crate) fn lock_downloads(config_dir: &Path) -> Result<std::fs::File, SetupError> {
    let path = config_dir.join(DOWNLOAD_LOCK_FILE_NAME);
    let io = |source| SetupError::Io {
        path: path.clone(),
        source,
    };
    std::fs::create_dir_all(config_dir).map_err(io)?;
    let file = std::fs::OpenOptions::new()
        .create(true)
        .truncate(false)
        .write(true)
        .open(&path)
        .map_err(io)?;
    match file.try_lock() {
        Ok(()) => Ok(file),
        Err(std::fs::TryLockError::WouldBlock) => Err(SetupError::Other {
            message: format!(
                "Another `bml setup` is downloading into {}; wait for it to finish, then run `bml setup` again.",
                config_dir.display()
            ),
        }),
        Err(std::fs::TryLockError::Error(e)) => Err(io(e)),
    }
}

/// Remove part files that an interrupted `download_verified` left in `dir`
/// for `file` (`.{file}.<id>.part`); returns how many. A missing `dir` is
/// fine. Call it only while holding [`lock_downloads`].
pub(crate) fn sweep_stale_parts(dir: &Path, file: &str) -> Result<usize, SetupError> {
    let io = |source| SetupError::Io {
        path: dir.to_path_buf(),
        source,
    };
    let entries = match std::fs::read_dir(dir) {
        Ok(entries) => entries,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(0),
        Err(e) => return Err(io(e)),
    };
    let prefix = format!(".{file}.");
    let mut removed = 0;
    for entry in entries {
        let entry = entry.map_err(io)?;
        let name = entry.file_name();
        let name = name.to_string_lossy();
        if name.starts_with(&prefix) && name.ends_with(".part") {
            std::fs::remove_file(entry.path()).map_err(io)?;
            removed += 1;
        }
    }
    Ok(removed)
}

/// One stage of setup, in the order they run.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum StepId {
    /// Memory and disk check.
    Hardware,
    /// The PostgreSQL database.
    Database,
    /// Start the database at login.
    Autostart,
    /// The Ollama runtime.
    Ollama,
    /// The language models.
    Models,
    /// The embedding model.
    EmbeddingModel,
}

impl StepId {
    /// The name shown to people for this step.
    #[must_use]
    pub fn label(self) -> &'static str {
        match self {
            Self::Hardware => "Hardware check",
            Self::Database => "Database",
            Self::Autostart => "Start at login",
            Self::Ollama => "Ollama",
            Self::Models => "Language models",
            Self::EmbeddingModel => "Embedding model",
        }
    }
}

/// Something a running step tells the user.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum StepEvent {
    /// The step began.
    Started(StepId),
    /// The step ended (also reported for steps that were skipped).
    Finished(StepId, StepOutcome),
    /// Work is under way; `total` is 0 when unknown.
    Progress {
        /// The step reporting.
        step: StepId,
        /// What is being done.
        detail: String,
        /// Bytes (or units) finished.
        done: u64,
        /// Bytes (or units) expected.
        total: u64,
    },
    /// Information worth reading.
    Notice {
        /// The step reporting.
        step: StepId,
        /// The text.
        message: String,
    },
    /// Something that may need attention but does not stop setup.
    Warning {
        /// The step reporting.
        step: StepId,
        /// The text.
        message: String,
    },
}

/// How a step ended.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum StepOutcome {
    /// There was nothing to do.
    AlreadyPresent,
    /// The step installed or downloaded what was missing.
    Installed,
    /// The step started something that was installed but not running.
    Started,
    /// The step finished but found problems worth reading (repeated here
    /// from its `Warning` events, for the summary).
    Warnings(Vec<String>),
    /// The step was left out on purpose.
    Skipped {
        /// Why.
        reason: String,
    },
    /// The step failed; the text says what to do.
    Failed(String),
}

/// Why a setup step could not finish.
#[derive(Debug, thiserror::Error)]
pub enum SetupError {
    /// Ollama did not behave.
    #[error("{message}")]
    Ollama {
        /// What happened and what to do next.
        message: String,
    },
    /// Setup itself could not go on (not an Ollama or database-layer error).
    #[error("{message}")]
    Other {
        /// What happened and what to do next.
        message: String,
    },
    /// A model pull failed.
    #[error("Pulling the model {model} failed: {message}. Check your network and free disk space, then run `bml setup` again; the download resumes.")]
    Pull {
        /// The model being pulled.
        model: String,
        /// What Ollama said.
        message: String,
    },
    /// The embedding model download failed.
    #[error("Downloading the embedding model failed: {0}. Check your network, then run `bml setup` again.")]
    Download(#[from] bmlib::embed::ModelError),
    /// The database layer failed.
    #[error("{0}")]
    PgServer(#[from] bml_pgserver::error::PgServerError),
    /// A file could not be read or written.
    #[error("Could not access {}: {source}. Check the folder exists and is writable, then run `bml setup` again.", path.display())]
    Io {
        /// The file or folder.
        path: PathBuf,
        /// The operating system's error.
        source: std::io::Error,
    },
    /// An installer program failed.
    #[error(
        "Running {program} failed: {message}. Install it by hand, then run `bml setup` again."
    )]
    Install {
        /// The program that failed.
        program: String,
        /// What happened.
        message: String,
    },
    /// Setup refuses to install or start Ollama on another machine.
    #[error("Ollama at {host} did not answer ({detail}), and it is not on this computer, so setup will not install or start it. Start it there, or drop --ollama-host and unset OLLAMA_HOST to use a local one.")]
    NotLoopback {
        /// The configured host.
        host: String,
        /// The connection error.
        detail: String,
    },
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sweep_removes_only_stale_parts_of_that_file() {
        let dir = tempfile::tempdir().unwrap();
        for name in [
            "x.bin",
            ".x.bin.123-456-0.part",
            ".other.part",
            ".x.bin.1.tmp",
        ] {
            std::fs::write(dir.path().join(name), b"1").unwrap();
        }
        assert_eq!(sweep_stale_parts(dir.path(), "x.bin").unwrap(), 1);
        let mut left: Vec<_> = std::fs::read_dir(dir.path())
            .unwrap()
            .map(|e| e.unwrap().file_name().to_string_lossy().into_owned())
            .collect();
        left.sort();
        assert_eq!(left, [".other.part", ".x.bin.1.tmp", "x.bin"]);
    }

    #[test]
    fn download_lock_is_exclusive_until_dropped() {
        let dir = tempfile::tempdir().unwrap();
        let cfg = dir.path().join("cfg");
        let held = lock_downloads(&cfg).unwrap();
        let e = lock_downloads(&cfg).unwrap_err();
        assert!(e.to_string().contains("Another `bml setup`"), "{e}");
        drop(held);
        lock_downloads(&cfg).unwrap();
    }

    #[test]
    fn sweep_missing_dir_is_ok() {
        let dir = tempfile::tempdir().unwrap();
        assert_eq!(sweep_stale_parts(&dir.path().join("none"), "x").unwrap(), 0);
    }
}

#[cfg(test)]
pub(crate) mod test_support {
    use bmlib::publications::fetchers::registry::{
        FetchError, HttpClient, HttpResponse, HttpStream,
    };
    use std::cell::RefCell;
    use std::collections::BTreeMap;

    /// Scripted client: one canned answer for every call, recording URLs.
    pub struct Fake {
        pub get: Result<(u16, String), String>,
        pub post: Option<(u16, String)>,
        pub stream: Option<(u16, String)>,
        pub urls: RefCell<Vec<String>>,
        /// Bodies of the POSTs, in order.
        pub bodies: RefCell<Vec<serde_json::Value>>,
        /// Answers for the first GETs, in order; `get` answers after that.
        pub get_script: RefCell<std::collections::VecDeque<(u16, String)>>,
    }
    impl Fake {
        pub fn new() -> Self {
            Fake {
                get: Err("refused".into()),
                post: None,
                stream: None,
                urls: RefCell::new(vec![]),
                bodies: RefCell::new(vec![]),
                get_script: RefCell::new(Default::default()),
            }
        }
    }
    impl HttpClient for Fake {
        fn get(&self, url: &str) -> Result<HttpResponse, FetchError> {
            self.urls.borrow_mut().push(url.to_string());
            if let Some((status, body)) = self.get_script.borrow_mut().pop_front() {
                return Ok(HttpResponse {
                    status,
                    body: body.into_bytes(),
                });
            }
            match &self.get {
                Ok((status, body)) => Ok(HttpResponse {
                    status: *status,
                    body: body.clone().into_bytes(),
                }),
                Err(m) => Err(FetchError::Transport(m.clone())),
            }
        }
        fn post_json(
            &self,
            url: &str,
            b: &serde_json::Value,
            _h: &BTreeMap<String, String>,
        ) -> Result<HttpResponse, FetchError> {
            self.urls.borrow_mut().push(url.to_string());
            self.bodies.borrow_mut().push(b.clone());
            let (status, body) = self.post.clone().unwrap();
            Ok(HttpResponse {
                status,
                body: body.into_bytes(),
            })
        }
        fn post_json_stream(
            &self,
            url: &str,
            _b: &serde_json::Value,
            _h: &BTreeMap<String, String>,
        ) -> Result<HttpStream, FetchError> {
            self.urls.borrow_mut().push(url.to_string());
            let (status, body) = self.stream.clone().unwrap();
            Ok(HttpStream {
                status,
                body: Box::new(std::io::Cursor::new(body.into_bytes())),
            })
        }
    }
}
