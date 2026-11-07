//! Guided first-run setup for BMLibrarian: hardware checks, Ollama and the
//! approved models; the step runner and `bml setup` pieces come later.

pub mod hardware;
pub mod models;
pub mod ollama;

use std::path::PathBuf;

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
    #[error("Ollama at {host} is not on this computer, so setup will not install or start it. Start it there, or unset OLLAMA_HOST to use a local one.")]
    NotLoopback {
        /// The configured host.
        host: String,
    },
}
