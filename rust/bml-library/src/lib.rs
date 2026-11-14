//! The BMLibrarian library pipeline: medRxiv metadata, full text and the
//! search index, each a resumable phase driven by database state alone, so a
//! killed run loses at most the paper in flight.
//!
//! [`Pipeline::update`] runs the phases in order: [`metadata`], [`fulltext`],
//! [`index`]. A phase that fails is reported and the next still runs. One
//! worker at a time holds [`try_lock_worker`].

pub mod fulltext;
pub mod index;
pub mod metadata;
pub mod polite_client;
pub mod status;
pub mod testing;

use std::fs::{File, OpenOptions};
use std::path::{Path, PathBuf};
use std::sync::atomic::AtomicBool;
use std::sync::Arc;
use std::time::Duration;

use bml_db::LIBRARY_STATE;
use bmlib::db::{execute, fetch_one, Db, DbError, Value};
use bmlib::fulltext::cache::FullTextCache;
use bmlib::http::UreqClient;
use bmlib::publications::fetchers::biorxiv::RATE_LIMIT_SECONDS;
use bmlib::publications::fetchers::HttpClient;
use bmlib::publications::sync::SyncError;
use chrono::{DateTime, NaiveDate, Utc};

use crate::fulltext::{FulltextEnd, FulltextReport};
use crate::index::{ChunkEmbedder, IndexReport};
use crate::metadata::MetadataReport;
use crate::polite_client::PoliteClient;

/// The bmlib source the metadata phase syncs (`/details/`, every version).
pub const MEDRXIV_SOURCE: &str = "medrxiv-details";
/// The `fulltext_sources.source` of medRxiv's own JATS and PDF links.
pub const MEDRXIV_SERVER: &str = "medrxiv";
/// medRxiv's first posting day (BMLibrarian's Python importer's
/// `MEDRXIV_LAUNCH_DATE`); the default start of the metadata phase.
pub const MEDRXIV_FIRST_DAY: &str = "2019-06-06";
/// The spacing between requests to `www.medrxiv.org`: the rate measured as
/// safe on 2026-11-14 (at 1.5 s medRxiv answered 429 after 7 papers).
pub const MEDRXIV_REQUEST_DELAY: Duration = Duration::from_secs(30);
/// The worker lock's file name inside the library folder.
pub const WORKER_LOCK_FILE: &str = ".bml-library.lock";

/// [`MEDRXIV_FIRST_DAY`] as a date.
///
/// # Panics
///
/// Never: the constant is a valid date (a unit test checks it).
#[must_use]
pub fn medrxiv_first_day() -> NaiveDate {
    NaiveDate::parse_from_str(MEDRXIV_FIRST_DAY, "%Y-%m-%d").expect("a valid constant date")
}

/// Why a phase could not finish.
#[derive(Debug, thiserror::Error)]
pub enum PipelineError {
    /// The database failed.
    #[error("the library's database failed: {0}")]
    Db(#[from] DbError),
    /// The embedding model failed or is missing (with the setup hint).
    #[error("{0}")]
    Embed(String),
    /// Anything else, in plain words.
    #[error("{0}")]
    Other(String),
}

impl From<SyncError> for PipelineError {
    fn from(error: SyncError) -> Self {
        match error {
            SyncError::Db(e) => PipelineError::Db(e),
            other => PipelineError::Other(other.to_string()),
        }
    }
}

/// A phase of [`Pipeline::update`].
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Phase {
    /// medRxiv metadata, day by day.
    Metadata,
    /// Full text, paper by paper.
    Fulltext,
    /// Chunks and embeddings.
    Index,
}

impl Phase {
    /// The phase's name as the CLI spells it.
    #[must_use]
    pub fn as_str(self) -> &'static str {
        match self {
            Phase::Metadata => "metadata",
            Phase::Fulltext => "fulltext",
            Phase::Index => "index",
        }
    }
}

/// Which phases to run.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct PhaseSet {
    /// Run the metadata phase.
    pub metadata: bool,
    /// Run the full-text phase.
    pub fulltext: bool,
    /// Run the index phase.
    pub index: bool,
}

impl PhaseSet {
    /// Every phase.
    #[must_use]
    pub fn all() -> Self {
        PhaseSet {
            metadata: true,
            fulltext: true,
            index: true,
        }
    }

    /// This set without `phase`.
    #[must_use]
    pub fn without(mut self, phase: Phase) -> Self {
        match phase {
            Phase::Metadata => self.metadata = false,
            Phase::Fulltext => self.fulltext = false,
            Phase::Index => self.index = false,
        }
        self
    }
}

/// What [`Pipeline::update`] is asked to do.
pub struct UpdateOptions<'a> {
    /// The first posting day to sync (default [`MEDRXIV_FIRST_DAY`]).
    pub from: Option<NaiveDate>,
    /// The phases to run.
    pub phases: PhaseSet,
    /// Set to stop after the paper (or day window) in flight.
    pub stop: &'a AtomicBool,
}

/// One progress line.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Progress {
    /// The phase it is about.
    pub phase: Phase,
    /// What happened, in plain words.
    pub message: String,
}

/// What [`Pipeline::update`] did; a phase not run is `None`.
#[derive(Debug, Default)]
pub struct UpdateReport {
    /// The metadata phase.
    pub metadata: Option<MetadataReport>,
    /// The full-text phase.
    pub fulltext: Option<FulltextReport>,
    /// The index phase.
    pub index: Option<IndexReport>,
    /// Phases that could not finish, and why.
    pub failures: Vec<(Phase, String)>,
}

impl UpdateReport {
    /// Whether a phase failed, a day of metadata could not be fetched or a
    /// paper could not be indexed.
    #[must_use]
    pub fn failed(&self) -> bool {
        !self.failures.is_empty()
            || self.metadata.as_ref().is_some_and(|m| !m.errors.is_empty())
            || self.index.as_ref().is_some_and(|i| !i.failed.is_empty())
    }

    /// Whether a phase stopped before its work was done (`stop`, or medRxiv
    /// rate-limiting the full-text phase).
    #[must_use]
    pub fn stopped_early(&self) -> bool {
        self.metadata.as_ref().is_some_and(|m| m.stopped)
            || self
                .fulltext
                .as_ref()
                .is_some_and(|f| f.end != FulltextEnd::Done)
            || self.index.as_ref().is_some_and(|i| i.stopped)
    }
}

/// Loads the embedder when the index phase starts.
pub type EmbedderLoader = Box<dyn Fn() -> Result<Box<dyn ChunkEmbedder>, String>>;

/// The pipeline's outside world: HTTP clients, the documents cache, the
/// embedding model and the clock. Tests replace each one.
pub struct Pipeline {
    /// The library's documents cache.
    pub cache: FullTextCache,
    /// The client for `api.biorxiv.org` (metadata).
    pub api: Arc<dyn HttpClient + Send + Sync>,
    /// The spacing between metadata requests.
    pub api_delay: Duration,
    /// The client for `www.medrxiv.org` (JATS and PDFs).
    pub web: Arc<dyn HttpClient + Send + Sync>,
    /// The spacing between full-text requests.
    pub web_delay: Duration,
    /// Loads the embedder.
    pub embedder: EmbedderLoader,
    /// The clock (UTC).
    pub clock: Box<dyn Fn() -> DateTime<Utc>>,
}

impl Pipeline {
    /// The real pipeline for `cache`, embedding with the model at `model_path`.
    #[must_use]
    pub fn new(cache: FullTextCache, model_path: PathBuf) -> Self {
        let client: Arc<dyn HttpClient + Send + Sync> = Arc::new(UreqClient::new());
        Pipeline {
            cache,
            api: client.clone(),
            api_delay: Duration::from_secs_f64(RATE_LIMIT_SECONDS),
            web: client,
            web_delay: MEDRXIV_REQUEST_DELAY,
            embedder: Box::new(move || index::load_model_embedder(&model_path)),
            clock: Box::new(Utc::now),
        }
    }

    /// Run the phases in `options` (see the crate docs). A phase failure is
    /// in [`UpdateReport::failures`]; the phases after it still run.
    pub fn update(
        &self,
        db: &mut dyn Db,
        options: &UpdateOptions<'_>,
        progress: &mut dyn FnMut(Progress),
    ) -> UpdateReport {
        let mut report = UpdateReport::default();
        let phases = options.phases;
        if phases.metadata {
            let api = Arc::new(PoliteClient::new(self.api.clone(), self.api_delay));
            let synced = start_day(db, options.from).and_then(|from| {
                metadata::run(db, api, from, options.stop, &*self.clock, progress)
            });
            match synced {
                Ok(r) => report.metadata = Some(r),
                Err(e) => report.failures.push((Phase::Metadata, e.to_string())),
            }
        }
        // Loaded once, when the index phase first runs; it runs before full
        // text (new abstracts are searchable within the hour, not after a
        // full-text backlog of weeks) and again after it (the new full texts).
        let mut embedder: Option<Box<dyn ChunkEmbedder>> = None;
        let mut index =
            |db: &mut dyn Db, report: &mut UpdateReport, progress: &mut dyn FnMut(Progress)| {
                if report.failures.iter().any(|(p, _)| *p == Phase::Index) {
                    return;
                }
                if embedder.is_none() {
                    match (self.embedder)() {
                        Ok(e) => embedder = Some(e),
                        Err(e) => {
                            report.failures.push((Phase::Index, e));
                            return;
                        }
                    }
                }
                let Some(model) = embedder.as_mut() else {
                    return;
                };
                match index::run(db, &self.cache, model.as_mut(), options.stop, progress) {
                    Ok(r) => report.index.get_or_insert_with(IndexReport::default).add(r),
                    Err(e) => report.failures.push((Phase::Index, e.to_string())),
                }
            };
        if phases.index {
            index(db, &mut report, progress);
        }
        if phases.fulltext {
            match fulltext::run(
                db,
                self.web.clone(),
                self.web_delay,
                &self.cache,
                options.stop,
                progress,
            ) {
                Ok(r) => report.fulltext = Some(r),
                Err(e) => report.failures.push((Phase::Fulltext, e.to_string())),
            }
            if phases.index {
                index(db, &mut report, progress);
            }
        }
        // Only a complete update counts, so a scheduled `--if-older-than` run
        // carries on an unfinished one (a backlog, a rate limit, a failure).
        if !report.failed() && !report.stopped_early() {
            if let Err(e) = execute(
                db,
                &format!(
                    "INSERT INTO {LIBRARY_STATE} (id, last_update_at) VALUES (1, now()) \
                     ON CONFLICT (id) DO UPDATE SET last_update_at = excluded.last_update_at"
                ),
                &[],
            ) {
                report.failures.push((
                    Phase::Index,
                    format!("recording the update's time failed: {e}"),
                ));
            }
        }
        report
    }
}

/// The first posting day to sync: `from` when given (and remembered as the
/// library's start), else the one remembered, else [`MEDRXIV_FIRST_DAY`].
///
/// # Errors
///
/// The database fails, or the remembered day cannot be read.
pub fn start_day(db: &mut dyn Db, from: Option<NaiveDate>) -> Result<NaiveDate, PipelineError> {
    if let Some(day) = from {
        execute(
            db,
            &format!(
                "INSERT INTO {LIBRARY_STATE} (id, from_day) VALUES (1, ?) \
                 ON CONFLICT (id) DO UPDATE SET from_day = excluded.from_day"
            ),
            &[Value::Text(day.to_string())],
        )?;
        return Ok(day);
    }
    let saved = fetch_one(
        db,
        &format!("SELECT from_day FROM {LIBRARY_STATE} WHERE id = 1 AND from_day IS NOT NULL"),
        &[],
    )?;
    match saved {
        Some(row) => {
            let text = row.get_str("from_day")?;
            NaiveDate::parse_from_str(text, "%Y-%m-%d").map_err(|e| {
                PipelineError::Other(format!(
                    "the library's start day {text:?} cannot be read ({e}); pass --from"
                ))
            })
        }
        None => Ok(medrxiv_first_day()),
    }
}

/// How much earlier than a whole number of days a daily trigger may fire and
/// still count (it fires at the same hour, a little before or after).
pub const SCHEDULE_SLACK_HOURS: i64 = 2;

/// Whether the last complete update finished less than `days` days ago
/// (less [`SCHEDULE_SLACK_HOURS`]), for a scheduled `--if-older-than` run.
///
/// # Errors
///
/// The query fails.
pub fn updated_within(db: &mut dyn Db, days: u32) -> Result<bool, PipelineError> {
    Ok(fetch_one(
        db,
        &format!(
            "SELECT 1 AS recent FROM {LIBRARY_STATE} WHERE id = 1 AND last_update_at > \
             now() - (make_interval(days => ?) - make_interval(hours => ?))"
        ),
        &[Value::Int(days.into()), Value::Int(SCHEDULE_SLACK_HOURS)],
    )?
    .is_some())
}

/// Take the library's worker lock (`<library>/`[`WORKER_LOCK_FILE`]); `None`
/// when another worker holds it. Held until the returned file is dropped.
///
/// # Errors
///
/// The lock file cannot be opened or locked for another reason.
pub fn try_lock_worker(library_dir: &Path) -> std::io::Result<Option<File>> {
    let file = OpenOptions::new()
        .create(true)
        .truncate(false)
        .write(true)
        .open(library_dir.join(WORKER_LOCK_FILE))?;
    match file.try_lock() {
        Ok(()) => Ok(Some(file)),
        Err(std::fs::TryLockError::WouldBlock) => Ok(None),
        Err(std::fs::TryLockError::Error(e)) => Err(e),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_first_day_parses() {
        assert_eq!(medrxiv_first_day().to_string(), MEDRXIV_FIRST_DAY);
    }

    #[test]
    fn a_second_worker_finds_the_lock_held() {
        let dir = tempfile::tempdir().unwrap();
        let first = try_lock_worker(dir.path()).unwrap();
        assert!(first.is_some());
        assert!(try_lock_worker(dir.path()).unwrap().is_none());
        drop(first);
        assert!(try_lock_worker(dir.path()).unwrap().is_some());
    }
}
