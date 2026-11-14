//! What the library holds: papers, full-text forms, abstract-only papers by
//! reason, the index, and the state of the last update.

use bml_db::{CACHE_DELETIONS, CHUNKS, LIBRARY_STATE, PUBLICATION_FULLTEXT, PUBLICATION_INDEX};
use bmlib::db::{fetch_all, fetch_one, fetch_scalar, Db, Value};
use bmlib::fulltext::cache::FullTextCache;

use crate::fulltext::{known_cache_keys, rate_limited_until, unreferenced_cache_keys};
use crate::PipelineError;

/// How many abstract-only reasons [`library_status`] lists.
pub const REASONS_SHOWN: i64 = 10;

/// One reason papers are abstract-only.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AbstractReason {
    /// `lasting` or `passing`.
    pub kind: String,
    /// The reason, as stored.
    pub reason: String,
    /// How many papers.
    pub papers: i64,
}

/// See the module docs.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct LibraryStatus {
    /// Publications held.
    pub papers: i64,
    /// With JATS full text.
    pub jats: i64,
    /// With PDF full text.
    pub pdf: i64,
    /// Abstract-only after trying.
    pub abstract_only: i64,
    /// Not tried for full text yet.
    pub not_tried: i64,
    /// The most common abstract-only reasons, most papers first.
    pub reasons: Vec<AbstractReason>,
    /// Papers whose index is complete.
    pub indexed: i64,
    /// Papers not (or no longer) indexed.
    pub to_index: i64,
    /// Chunks stored.
    pub chunks: i64,
    /// Days of metadata recorded complete.
    pub days_complete: i64,
    /// Days of metadata recorded failed (fetched again next run).
    pub days_failed: i64,
    /// When the last complete update finished (database time, as text).
    pub last_update: Option<String>,
    /// When the full-text phase may run again after a 429.
    pub rate_limited_until: Option<String>,
    /// Old cache entries queued for deletion (a crash interrupted it; the
    /// next update finishes it).
    pub pending_deletions: i64,
    /// Cache entries no paper refers to (kept; listed for information).
    pub unreferenced_files: usize,
}

fn count(db: &mut dyn Db, sql: &str) -> Result<i64, PipelineError> {
    Ok(fetch_scalar(db, sql, &[])?
        .and_then(|v| v.as_i64())
        .unwrap_or(0))
}

/// Read the library's status.
///
/// # Errors
///
/// A query fails.
pub fn library_status(
    db: &mut dyn Db,
    cache: &FullTextCache,
) -> Result<LibraryStatus, PipelineError> {
    let form = |f: &str| format!("SELECT count(*) FROM {PUBLICATION_FULLTEXT} WHERE form = '{f}'");
    let papers = count(db, "SELECT count(*) FROM publications")?;
    let tried = count(db, &format!("SELECT count(*) FROM {PUBLICATION_FULLTEXT}"))?;
    let indexed = count(
        db,
        &format!("SELECT count(*) FROM {PUBLICATION_INDEX} WHERE status = 'complete'"),
    )?;
    let reasons = fetch_all(
        db,
        &format!(
            "SELECT COALESCE(last_error_kind, '') AS kind, COALESCE(last_error, '') AS reason, \
             count(*) AS papers FROM {PUBLICATION_FULLTEXT} WHERE form = 'abstract' \
             GROUP BY 1, 2 ORDER BY 3 DESC, 2 LIMIT ?"
        ),
        &[Value::Int(REASONS_SHOWN)],
    )?
    .iter()
    .map(|r| {
        Ok(AbstractReason {
            kind: r.get_str("kind")?.to_string(),
            reason: r.get_str("reason")?.to_string(),
            papers: r.get_i64("papers")?,
        })
    })
    .collect::<Result<Vec<_>, PipelineError>>()?;
    let days = |status: &str| {
        format!(
            "SELECT count(*) FROM download_days WHERE source = '{}' AND status = '{status}'",
            crate::MEDRXIV_SOURCE
        )
    };
    let last_update = fetch_one(
        db,
        &format!("SELECT CAST(last_update_at AS TEXT) AS at FROM {LIBRARY_STATE} WHERE id = 1"),
        &[],
    )?
    .and_then(|r| {
        r.get("at")
            .ok()
            .and_then(|v| v.as_str().map(str::to_string))
    });
    Ok(LibraryStatus {
        papers,
        jats: count(db, &form("jats"))?,
        pdf: count(db, &form("pdf"))?,
        abstract_only: count(db, &form("abstract"))?,
        not_tried: papers - tried,
        reasons,
        indexed,
        to_index: papers - indexed,
        chunks: count(db, &format!("SELECT count(*) FROM {CHUNKS}"))?,
        days_complete: count(db, &days("completed"))?,
        days_failed: count(db, &days("failed"))?,
        last_update,
        rate_limited_until: rate_limited_until(db)?,
        pending_deletions: count(db, &format!("SELECT count(*) FROM {CACHE_DELETIONS}"))?,
        unreferenced_files: unreferenced_cache_keys(cache, &known_cache_keys(db)?).len(),
    })
}
