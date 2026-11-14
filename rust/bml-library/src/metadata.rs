//! The metadata phase: bmlib's `medrxiv-details` source, synced day by day.
//! bmlib's day ledger (`download_days`) is the checkpoint, so a stopped or
//! failed run resumes at the first day not yet recorded complete.

use std::collections::BTreeMap;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

use bmlib::db::Db;
use bmlib::publications::fetchers::registry::builtin_registry;
use bmlib::publications::fetchers::HttpClient;
use bmlib::publications::sync::{sync, SyncRequest};
use chrono::{DateTime, Days, NaiveDate, Utc};

use crate::{Phase, PipelineError, Progress, MEDRXIV_SOURCE};

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
    /// `stop` was set before every window was synced.
    pub stopped: bool,
}

/// Sync `medrxiv-details` from `from` to `clock()`'s date, one window at a time.
///
/// # Errors
///
/// A database failure outside one day, or a window bmlib refuses.
pub fn run(
    db: &mut dyn Db,
    client: Arc<dyn HttpClient + Send + Sync>,
    from: NaiveDate,
    stop: &AtomicBool,
    clock: &dyn Fn() -> DateTime<Utc>,
    progress: &mut dyn FnMut(Progress),
) -> Result<MetadataReport, PipelineError> {
    let registry = builtin_registry(client).map_err(|e| PipelineError::Other(e.to_string()))?;
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
        let request = SyncRequest {
            sources: vec![MEDRXIV_SOURCE.to_string()],
            date_from: start,
            date_to: end,
            recheck_days: 0,
            configs: &configs,
        };
        let synced = sync(db, &registry, &request, clock)?;
        if synced.days_processed > 0 {
            progress(Progress {
                phase: Phase::Metadata,
                message: format!(
                    "{start} to {end}: {} day(s), {} new, {} updated",
                    synced.days_processed, synced.records_added, synced.records_merged
                ),
            });
        }
        report.days += synced.days_processed;
        report.added += synced.records_added;
        report.merged += synced.records_merged;
        report.failed += synced.records_failed;
        report.errors.extend(synced.errors);
        start = match end.succ_opt() {
            Some(next) => next,
            None => break,
        };
    }
    Ok(report)
}
