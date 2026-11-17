//! The metadata phase: a bmlib source synced day by day (`medrxiv-details`,
//! or `europepmc` with a topic's search, through [`run_window`]).
//! bmlib's day ledger (`download_days`) is the checkpoint, so a stopped or
//! failed run resumes at the first day not yet recorded complete.

use std::collections::BTreeMap;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

use bmlib::db::Db;
use bmlib::publications::fetchers::registry::builtin_registry;
use bmlib::publications::sync::{sync, SyncRequest};
use chrono::{DateTime, Days, NaiveDate, Utc};

use crate::polite_client::PoliteClient;
use crate::{FulltextSource, Phase, PipelineError, Progress};

/// How many days one `sync` call covers; `stop` is checked between calls.
pub const METADATA_WINDOW_DAYS: u64 = 30;

/// What the metadata phase did.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct MetadataReport {
    /// Days fetched (completed or failed).
    pub days: i64,
    /// Papers (versions) added as new publications.
    pub added: i64,
    /// Records merged into publications already held (a new version, say).
    pub merged: i64,
    /// Records that could not be stored.
    pub failed: i64,
    /// One line per failed day; a failed day is fetched again next run.
    pub errors: Vec<String>,
    /// `stop` was set, or the API rate-limited us, before every window was
    /// synced.
    pub stopped: bool,
    /// The API answered 429: the phase stopped, and the days of that window
    /// are fetched again next run (their errors are not listed).
    pub rate_limited: bool,
}

impl MetadataReport {
    /// Fold one window's report into this one.
    pub fn add(&mut self, window: MetadataReport) {
        self.days += window.days;
        self.added += window.added;
        self.merged += window.merged;
        self.failed += window.failed;
        self.errors.extend(window.errors);
        self.stopped |= window.stopped;
        self.rate_limited |= window.rate_limited;
    }
}

/// Sync `medrxiv-details` from `from` to `clock()`'s date, one window at a time.
///
/// # Errors
///
/// A database failure outside one day, or a window bmlib refuses.
pub fn run(
    db: &mut dyn Db,
    client: Arc<PoliteClient>,
    from: NaiveDate,
    stop: &AtomicBool,
    clock: &dyn Fn() -> DateTime<Utc>,
    progress: &mut dyn FnMut(Progress),
) -> Result<MetadataReport, PipelineError> {
    let configs = BTreeMap::new();
    let today = clock().date_naive();
    let mut report = MetadataReport::default();
    let mut start = from;
    while start <= today {
        if stop.load(Ordering::Relaxed) {
            report.stopped = true;
            break;
        }
        let end = start
            .checked_add_days(Days::new(METADATA_WINDOW_DAYS - 1))
            .map_or(today, |d| d.min(today));
        let window = run_window(
            db,
            client.clone(),
            FulltextSource::Medrxiv,
            &configs,
            start,
            end,
            stop,
            clock,
            progress,
        )?;
        let rate_limited = window.rate_limited;
        report.add(window);
        if rate_limited {
            break;
        }
        start = match end.succ_opt() {
            Some(next) => next,
            None => break,
        };
    }
    Ok(report)
}

/// Sync one window, `from` to `to` (inclusive), of `source`'s details, with
/// `configs` as each source's settings (a topic library's `query`).
///
/// # Errors
///
/// A database failure outside one day, or a window bmlib refuses.
#[allow(clippy::too_many_arguments)]
pub fn run_window(
    db: &mut dyn Db,
    client: Arc<PoliteClient>,
    source: FulltextSource,
    configs: &BTreeMap<String, BTreeMap<String, String>>,
    from: NaiveDate,
    to: NaiveDate,
    stop: &AtomicBool,
    clock: &dyn Fn() -> DateTime<Utc>,
    progress: &mut dyn FnMut(Progress),
) -> Result<MetadataReport, PipelineError> {
    let mut report = MetadataReport::default();
    if stop.load(Ordering::Relaxed) {
        report.stopped = true;
        return Ok(report);
    }
    let registry =
        builtin_registry(client.clone()).map_err(|e| PipelineError::Other(e.to_string()))?;
    let request = SyncRequest {
        sources: vec![source.metadata_source().to_string()],
        date_from: from,
        date_to: to,
        recheck_days: 0,
        configs,
    };
    let synced = sync(db, &registry, &request, clock)?;
    if client.rate_limited() {
        // bmlib recorded the window's days failed, so they come again.
        progress(Progress {
            phase: Phase::Metadata,
            message: format!(
                "{} asked us to slow down at {from} to {to}; the metadata carries on next run",
                source.name()
            ),
        });
        report.stopped = true;
        report.rate_limited = true;
        return Ok(report);
    }
    if synced.days_processed > 0 {
        progress(Progress {
            phase: Phase::Metadata,
            message: format!(
                "{from} to {to}: {} day(s), {} new, {} updated",
                synced.days_processed, synced.records_added, synced.records_merged
            ),
        });
    }
    report.days = synced.days_processed;
    report.added = synced.records_added;
    report.merged = synced.records_merged;
    report.failed = synced.records_failed;
    report.errors = synced.errors;
    Ok(report)
}
