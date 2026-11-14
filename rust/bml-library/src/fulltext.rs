//! The full-text phase: for one paper at a time, the newest version's JATS
//! XML (or, without JATS, its PDF) from medRxiv into the library's
//! documents folder, recorded in `publication_fulltext`.
//!
//! Only the paper's own sources are asked (bmlib's Tier 0): the request
//! carries no DOI, PMID or PMC ID, so no Europe PMC, PMC, Unpaywall or DOI
//! tier runs. Every request goes through a [`PoliteClient`], so requests are
//! spaced, and the first 429 ends the phase without charging the paper.
//! A replaced version's files are queued in `cache_deletions` in the same
//! transaction and deleted after it commits; no file is deleted only
//! because no row names it.

use std::collections::HashSet;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Duration;

use bml_db::{CACHE_DELETIONS, LIBRARY_STATE, PUBLICATION_FULLTEXT, PUBLICATION_INDEX};
use bmlib::db::{execute, fetch_all, fetch_one, Db, Row, Value};
use bmlib::fulltext::cache::{safe_filename, sanitize_identifier, FullTextCache};
use bmlib::fulltext::service::{FullTextError, FullTextRequest, FullTextService};
use bmlib::fulltext::{ContentKind, FullTextResult, FullTextSourceEntry, MupdfPdfExtractor};
use bmlib::publications::fetchers::HttpClient;

use crate::polite_client::{PoliteClient, RequestOutcome, RequestRecord};
use crate::{Phase, PipelineError, Progress, MEDRXIV_SERVER};

/// The first wait after a passing failure; each further one doubles it.
pub const RETRY_BASE: Duration = Duration::from_secs(60 * 60);
/// The longest wait after a passing failure.
pub const RETRY_MAX: Duration = Duration::from_secs(7 * 24 * 60 * 60);
/// The wait after a lasting failure (a 404, a refused PDF): such a paper is
/// still tried again, rarely, since abstract-only is never final.
pub const LASTING_RETRY: Duration = Duration::from_secs(30 * 24 * 60 * 60);
/// How long the full-text phase is skipped after medRxiv answered 429 (the
/// 2026-11-14 measurement: refusals lasted minutes; an hour's rest worked).
pub const RATE_LIMIT_BACKOFF: Duration = Duration::from_secs(60 * 60);

/// bmlib's `pdf_download_failure` for a PDF that arrived but could not be
/// saved in the library folder (a full or read-only disk).
pub const PDF_WRITE_FAILED: &str = "write-failed";

/// Whether a failure may pass on its own (try again soon) or not.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FailureKind {
    /// The same request will most likely get the same answer (404, 403).
    Lasting,
    /// A later try may succeed (timeout, 5xx).
    Passing,
}

impl FailureKind {
    /// The `last_error_kind` value.
    #[must_use]
    pub fn as_str(self) -> &'static str {
        match self {
            FailureKind::Lasting => "lasting",
            FailureKind::Passing => "passing",
        }
    }
}

/// How long to wait before trying a paper again after its `attempts`-th
/// failure (1 for the first).
#[must_use]
pub fn retry_delay(kind: FailureKind, attempts: u32) -> Duration {
    match kind {
        FailureKind::Lasting => LASTING_RETRY,
        FailureKind::Passing => {
            let doublings = attempts.saturating_sub(1).min(u32::BITS - 1);
            RETRY_BASE
                .checked_mul(1u32 << doublings)
                .map_or(RETRY_MAX, |d| d.min(RETRY_MAX))
        }
    }
}

/// What one paper's fetch came to.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Classified {
    /// The JATS XML was fetched (or found in the cache) with an article body.
    Jats,
    /// The PDF was fetched and its text extracted.
    Pdf,
    /// No full text; only the abstract.
    Failed {
        /// Why, in plain words.
        reason: String,
        /// Lasting or passing.
        kind: FailureKind,
    },
}

fn status_reason(status: u16) -> String {
    match status {
        403 => "refused (HTTP 403)".into(),
        404 => "not found (HTTP 404)".into(),
        other => format!("HTTP {other}"),
    }
}

/// A JATS request's failure: lasting for 404, 403 or a body that is not
/// usable XML; passing for no answer, a 408 or a 5xx.
fn jats_failure(
    outcome: &RequestOutcome,
    result_kind: Option<ContentKind>,
) -> (String, FailureKind) {
    match outcome {
        RequestOutcome::Status(200) => {
            if result_kind == Some(ContentKind::Abstract) {
                (
                    "the JATS XML holds no article body".into(),
                    FailureKind::Lasting,
                )
            } else {
                (
                    "the JATS XML could not be read".into(),
                    FailureKind::Lasting,
                )
            }
        }
        RequestOutcome::Status(status) => {
            let kind = if *status == 408 || (500..600).contains(status) {
                FailureKind::Passing
            } else {
                FailureKind::Lasting
            };
            (status_reason(*status), kind)
        }
        RequestOutcome::NoResponse(message) => {
            (format!("no answer ({message})"), FailureKind::Passing)
        }
        RequestOutcome::NotSent => ("not sent (rate limited)".into(), FailureKind::Passing),
    }
}

fn pdf_cause_reason(cause: &str) -> String {
    match cause
        .strip_prefix("http-")
        .and_then(|s| s.parse::<u16>().ok())
    {
        Some(status) => status_reason(status),
        None => match cause {
            "not-a-pdf" => "the answer was not a PDF".into(),
            "request-failed" => "no answer".into(),
            PDF_WRITE_FAILED => "could not be saved in the library folder".into(),
            other => other.into(),
        },
    }
}

/// Classify one paper's fetch from the service's result and the requests the
/// [`PoliteClient`] recorded for it. `pdf_urls` are the paper's PDF sources,
/// which tell its PDF request from its JATS one. The paper's failure kind is
/// the PDF's when a PDF was requested, else the JATS one.
#[must_use]
pub fn classify(
    result: &Result<FullTextResult, FullTextError>,
    records: &[RequestRecord],
    pdf_urls: &[String],
) -> Classified {
    let ok = result.as_ref().ok();
    if let Some(r) = ok {
        if r.content_kind == ContentKind::Fulltext && r.jats_xml.is_some() {
            return Classified::Jats;
        }
        if r.file_path.is_some() && r.pdf_download_failure.is_none() {
            return match r.pdf_extraction_failure.as_deref() {
                None if r.content_kind == ContentKind::Extracted => Classified::Pdf,
                None => Classified::Failed {
                    reason: "PDF: it holds no text to read (a scan?)".into(),
                    kind: FailureKind::Lasting,
                },
                Some(cause @ ("encrypted" | "unreadable")) => Classified::Failed {
                    reason: format!("PDF: it cannot be read ({cause})"),
                    kind: FailureKind::Lasting,
                },
                Some(cause) => Classified::Failed {
                    reason: format!("PDF: reading it failed ({cause})"),
                    kind: FailureKind::Passing,
                },
            };
        }
    }
    let is_pdf = |r: &&RequestRecord| pdf_urls.contains(&r.url);
    let mut parts = Vec::new();
    let mut kind = None;
    if let Some(jats) = records.iter().rev().find(|r| !is_pdf(r)) {
        let (reason, k) = jats_failure(&jats.outcome, ok.map(|r| r.content_kind));
        parts.push(format!("JATS: {reason}"));
        kind = Some(k);
    }
    if let Some(pdf) = records.iter().rev().find(is_pdf) {
        let (reason, k) = match ok.and_then(|r| r.pdf_download_failure.as_deref().map(|c| (r, c))) {
            Some((r, cause)) => (
                pdf_cause_reason(cause),
                // A full disk is ours to fix, not the paper's: bmlib counts
                // it final, the library tries again.
                if r.pdf_failure_may_pass() || cause == PDF_WRITE_FAILED {
                    FailureKind::Passing
                } else {
                    FailureKind::Lasting
                },
            ),
            None => jats_failure(&pdf.outcome, None),
        };
        parts.push(format!("PDF: {reason}"));
        kind = Some(k);
    }
    match kind {
        Some(kind) => Classified::Failed {
            reason: parts.join("; "),
            kind,
        },
        None => Classified::Failed {
            reason: match result {
                Err(e) => format!("no full text could be asked for ({e})"),
                Ok(_) => "no full-text source was asked".into(),
            },
            kind: FailureKind::Passing,
        },
    }
}

/// How the full-text phase ended.
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub enum FulltextEnd {
    /// Every paper due was tried.
    #[default]
    Done,
    /// `stop` was set; the paper in flight was finished first.
    Stopped,
    /// medRxiv answered 429; the phase is skipped until the time given.
    RateLimited {
        /// When the phase may run again (database time, as text).
        until: String,
    },
}

/// What the full-text phase did.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct FulltextReport {
    /// Papers tried this run.
    pub tried: u64,
    /// JATS full texts stored.
    pub jats: u64,
    /// PDF full texts stored.
    pub pdf: u64,
    /// New versions that replaced a held full text.
    pub replaced: u64,
    /// Papers left abstract-only by a lasting failure.
    pub lasting: u64,
    /// Papers left abstract-only by a passing failure.
    pub passing: u64,
    /// Old cache entries a crash left queued for deletion, deleted first.
    pub old_files_removed: u64,
    /// How the phase ended.
    pub end: FulltextEnd,
}

/// One paper due for full text.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Paper {
    /// `publications.id`.
    pub id: i64,
    /// The paper's DOI.
    pub doi: String,
    /// The newest version among its medRxiv sources.
    pub version: i64,
    /// The full-text form held (`None`: no row yet).
    pub form: Option<String>,
    /// The cache key of the held full text, if any.
    pub cache_key: Option<String>,
    /// Failed attempts so far.
    pub attempts: i64,
}

impl Paper {
    /// Whether a full text (not just the abstract) is held.
    #[must_use]
    pub fn holds_fulltext(&self) -> bool {
        self.form.as_deref().is_some_and(|f| f != "abstract")
    }

    /// The cache key for this paper's newest version: `<doi>v<version>`,
    /// sanitised as bmlib's service does.
    #[must_use]
    pub fn new_cache_key(&self) -> String {
        sanitize_identifier(&self.identifier())
    }

    fn identifier(&self) -> String {
        format!("{}v{}", self.doi, self.version)
    }
}

/// The version as an integer where the text is digits only (no cast error).
const VERSION_INT: &str = "CASE WHEN version ~ '^[0-9]{1,9}$' THEN CAST(version AS INTEGER) END";

fn text(row: &Row, name: &str) -> Result<Option<String>, PipelineError> {
    Ok(row.get(name)?.as_str().map(str::to_string))
}

/// The next paper due: no full-text row yet; or its retry time has passed and
/// it is abstract-only or a newer version than the one held is posted.
/// Newest posting first, so updates are not starved by the backlog.
///
/// # Errors
///
/// The query fails.
pub fn next_paper(db: &mut dyn Db) -> Result<Option<Paper>, PipelineError> {
    let sql = format!(
        "WITH current AS (\
           SELECT publication_id, max({VERSION_INT}) AS version FROM fulltext_sources \
           WHERE source = ? AND format IN ('xml', 'pdf') GROUP BY publication_id) \
         SELECT p.id AS id, p.doi AS doi, c.version AS version, f.form AS form, \
                f.cache_key AS cache_key, COALESCE(f.attempts, 0) AS attempts \
         FROM current c \
         JOIN publications p ON p.id = c.publication_id \
         LEFT JOIN {PUBLICATION_FULLTEXT} f ON f.publication_id = p.id \
         WHERE c.version IS NOT NULL AND p.doi IS NOT NULL AND p.doi <> '' \
           AND (f.publication_id IS NULL \
                OR ((f.retry_after IS NULL OR f.retry_after <= now()) \
                    AND (f.form = 'abstract' OR f.version_held IS NULL \
                         OR CAST(f.version_held AS INTEGER) < c.version))) \
         ORDER BY p.publication_date DESC NULLS LAST, p.id DESC LIMIT 1"
    );
    let Some(row) = fetch_one(db, &sql, &[Value::Text(MEDRXIV_SERVER.into())])? else {
        return Ok(None);
    };
    Ok(Some(Paper {
        id: row.get_i64("id")?,
        doi: row.get_str("doi")?.to_string(),
        version: row.get_i64("version")?,
        form: text(&row, "form")?,
        cache_key: text(&row, "cache_key")?,
        attempts: row.get_i64("attempts")?,
    }))
}

/// The paper's medRxiv sources for `version`.
fn sources(db: &mut dyn Db, paper: &Paper) -> Result<Vec<FullTextSourceEntry>, PipelineError> {
    let rows = fetch_all(
        db,
        &format!(
            "SELECT url, format FROM fulltext_sources WHERE publication_id = ? AND source = ? \
             AND format IN ('xml', 'pdf') AND {VERSION_INT} = ? ORDER BY id"
        ),
        &[
            Value::Int(paper.id),
            Value::Text(MEDRXIV_SERVER.into()),
            Value::Int(paper.version),
        ],
    )?;
    rows.iter()
        .map(|row| {
            Ok(FullTextSourceEntry {
                url: row.get_str("url")?.to_string(),
                format: row.get_str("format")?.to_string(),
                source: MEDRXIV_SERVER.to_string(),
                open_access: true,
                version: Some(paper.version.to_string()),
            })
        })
        .collect()
}

/// When the full-text phase may run again, if medRxiv rate-limited an
/// earlier run and that time has not passed.
///
/// # Errors
///
/// The query fails.
pub fn rate_limited_until(db: &mut dyn Db) -> Result<Option<String>, PipelineError> {
    let row = fetch_one(
        db,
        &format!(
            "SELECT CAST(rate_limited_until AS TEXT) AS until FROM {LIBRARY_STATE} \
             WHERE id = 1 AND rate_limited_until > now()"
        ),
        &[],
    )?;
    match row {
        Some(row) => text(&row, "until"),
        None => Ok(None),
    }
}

fn record_rate_limit(db: &mut dyn Db) -> Result<String, PipelineError> {
    execute(
        db,
        &format!(
            "INSERT INTO {LIBRARY_STATE} (id, rate_limited_until) \
             VALUES (1, now() + make_interval(secs => ?)) \
             ON CONFLICT (id) DO UPDATE SET rate_limited_until = excluded.rate_limited_until"
        ),
        &[Value::Int(secs(RATE_LIMIT_BACKOFF))],
    )?;
    Ok(rate_limited_until(db)?.unwrap_or_default())
}

fn secs(d: Duration) -> i64 {
    i64::try_from(d.as_secs()).unwrap_or(i64::MAX)
}

/// Cache keys of entries in `cache` that are not in `known` (for `status`;
/// nothing is deleted for this alone: the database may be another one, or
/// the entry a fetch whose commit a crash prevented, which the cache
/// serves on the next try). Only regular entries (`<key>.html`, `<key>.xml`,
/// `<key>.pdf`) are looked at.
#[must_use]
pub fn unreferenced_cache_keys(cache: &FullTextCache, known: &HashSet<String>) -> Vec<String> {
    let mut orphans = std::collections::BTreeSet::new();
    for (dir, ext) in [
        (cache.html_dir(), "html"),
        (cache.abstract_dir(), "html"),
        (cache.jats_dir(), "xml"),
        (cache.pdf_dir(), "pdf"),
    ] {
        let Ok(entries) = std::fs::read_dir(&dir) else {
            continue;
        };
        for entry in entries.flatten() {
            let name = entry.file_name();
            let Some(name) = name.to_str() else { continue };
            if name.starts_with('.') {
                continue;
            }
            if let Some(stem) = name.strip_suffix(&format!(".{ext}")) {
                if !known.contains(stem) {
                    orphans.insert(stem.to_string());
                }
            }
        }
    }
    orphans.into_iter().collect()
}

/// The cache keys `publication_fulltext` refers to.
///
/// # Errors
///
/// The query fails.
pub fn known_cache_keys(db: &mut dyn Db) -> Result<HashSet<String>, PipelineError> {
    let rows = fetch_all(
        db,
        &format!("SELECT cache_key FROM {PUBLICATION_FULLTEXT} WHERE cache_key IS NOT NULL"),
        &[],
    )?;
    rows.iter()
        .map(|r| Ok(r.get_str("cache_key")?.to_string()))
        .collect()
}

/// Where the stored full text for `key` is, relative to the cache folder
/// (so the record survives the library folder moving), if the cache holds it.
fn cached_path(cache: &FullTextCache, key: &str, classified: &Classified) -> Option<String> {
    let path = match classified {
        Classified::Jats => cache.jats_dir().join(format!("{}.xml", safe_filename(key))),
        Classified::Pdf => cache.pdf_dir().join(format!("{}.pdf", safe_filename(key))),
        Classified::Failed { .. } => return None,
    };
    let relative = path.strip_prefix(&cache.cache_dir).ok()?;
    path.is_file().then(|| relative.display().to_string())
}

/// Record `classified` for `paper` (see the module docs for the rules).
/// Returns whether a held full text was replaced by a new version.
///
/// # Errors
///
/// A database failure. Before the commit nothing of the paper's state has
/// changed; after it (finishing the queued deletions) the paper stays
/// recorded and the next run finishes the deletions.
pub fn record(
    db: &mut dyn Db,
    cache: &FullTextCache,
    paper: &Paper,
    classified: &Classified,
) -> Result<bool, PipelineError> {
    let key = paper.new_cache_key();
    let classified = match (classified, cached_path(cache, &key, classified)) {
        (Classified::Failed { .. }, _) | (_, Some(_)) => classified.clone(),
        (_, None) => Classified::Failed {
            reason: "the full text was fetched but is not in the library folder".into(),
            kind: FailureKind::Passing,
        },
    };
    let form = match classified {
        Classified::Jats => "jats",
        Classified::Pdf => "pdf",
        Classified::Failed { reason, kind } => {
            let attempts = paper.attempts.saturating_add(1);
            let wait = retry_delay(kind, u32::try_from(attempts).unwrap_or(u32::MAX));
            // In statement order: the paper id goes last in the UPDATE, first in the INSERT.
            let failure = [
                Value::Int(attempts),
                Value::Text(reason),
                Value::Text(kind.as_str().into()),
                Value::Int(secs(wait)),
            ];
            let id = Value::Int(paper.id);
            if paper.holds_fulltext() {
                // A new version failed: the old version's row, file and chunks stay.
                execute(
                    db,
                    &format!(
                        "UPDATE {PUBLICATION_FULLTEXT} SET attempts = ?, last_error = ?, \
                         last_error_kind = ?, retry_after = now() + make_interval(secs => ?), \
                         updated_at = now() WHERE publication_id = ?"
                    ),
                    &[failure.as_slice(), &[id]].concat(),
                )?;
            } else {
                execute(
                    db,
                    &format!(
                        "INSERT INTO {PUBLICATION_FULLTEXT} (publication_id, form, attempts, \
                         last_error, last_error_kind, retry_after) \
                         VALUES (?, 'abstract', ?, ?, ?, now() + make_interval(secs => ?)) \
                         ON CONFLICT (publication_id) DO UPDATE SET form = 'abstract', \
                         version_held = NULL, cache_key = NULL, cache_path = NULL, \
                         attempts = excluded.attempts, last_error = excluded.last_error, \
                         last_error_kind = excluded.last_error_kind, \
                         retry_after = excluded.retry_after, updated_at = now()"
                    ),
                    &[&[id][..], failure.as_slice()].concat(),
                )?;
            }
            return Ok(false);
        }
    };
    let path = cached_path(cache, &key, &classified).unwrap_or_default();
    let mut tx = db.begin()?;
    let old = fetch_one(
        &mut *tx,
        &format!(
            "SELECT cache_key FROM {PUBLICATION_FULLTEXT} WHERE publication_id = ? FOR UPDATE"
        ),
        &[Value::Int(paper.id)],
    )?
    .map(|row| row.get("cache_key").map(|v| v.as_str().map(str::to_string)))
    .transpose()?
    .flatten();
    execute(
        &mut *tx,
        &format!(
            "INSERT INTO {PUBLICATION_FULLTEXT} (publication_id, form, version_held, cache_key, \
             cache_path, attempts, last_error, last_error_kind, retry_after) \
             VALUES (?, ?, ?, ?, ?, 0, NULL, NULL, NULL) \
             ON CONFLICT (publication_id) DO UPDATE SET form = excluded.form, \
             version_held = excluded.version_held, cache_key = excluded.cache_key, \
             cache_path = excluded.cache_path, attempts = 0, last_error = NULL, \
             last_error_kind = NULL, retry_after = NULL, updated_at = now()"
        ),
        &[
            Value::Int(paper.id),
            Value::Text(form.into()),
            Value::Text(paper.version.to_string()),
            Value::Text(key.clone()),
            Value::Text(path),
        ],
    )?;
    execute(
        &mut *tx,
        &format!(
            "INSERT INTO {PUBLICATION_INDEX} (publication_id, status) VALUES (?, 'pending') \
             ON CONFLICT (publication_id) DO UPDATE SET status = 'pending', updated_at = now()"
        ),
        &[Value::Int(paper.id)],
    )?;
    let replaced = old.filter(|old| *old != key);
    if let Some(old) = &replaced {
        queue_cache_deletion(&mut *tx, old)?;
    }
    tx.commit()?;
    // After the commit; a crash here is finished by the next run.
    finish_cache_deletions(db, cache)?;
    Ok(replaced.is_some())
}

/// Queue `key`'s cache entry for deletion, inside the caller's transaction.
///
/// # Errors
///
/// The insert fails.
pub fn queue_cache_deletion(db: &mut dyn Db, key: &str) -> Result<(), PipelineError> {
    execute(
        db,
        &format!(
            "INSERT INTO {CACHE_DELETIONS} (cache_key) VALUES (?) \
             ON CONFLICT (cache_key) DO NOTHING"
        ),
        &[Value::Text(key.into())],
    )?;
    Ok(())
}

/// Delete the files of every queued cache entry no paper uses any more,
/// then the queue rows; returns how many entries were deleted.
///
/// # Errors
///
/// A query fails (files already deleted stay deleted; their rows are
/// removed by the next call).
pub fn finish_cache_deletions(
    db: &mut dyn Db,
    cache: &FullTextCache,
) -> Result<u64, PipelineError> {
    let queued = fetch_all(
        db,
        &format!(
            "SELECT d.cache_key AS cache_key, EXISTS (SELECT 1 FROM {PUBLICATION_FULLTEXT} f \
             WHERE f.cache_key = d.cache_key) AS in_use FROM {CACHE_DELETIONS} d"
        ),
        &[],
    )?;
    let mut deleted = 0;
    for row in &queued {
        let key = row.get_str("cache_key")?.to_string();
        if row.get_i64("in_use")? == 0 {
            cache.delete(&key);
            deleted += 1;
        }
        execute(
            db,
            &format!("DELETE FROM {CACHE_DELETIONS} WHERE cache_key = ?"),
            &[Value::Text(key)],
        )?;
    }
    Ok(deleted)
}

/// Run the full-text phase (see the module docs).
///
/// # Errors
///
/// A database failure; papers already recorded keep their state.
pub fn run(
    db: &mut dyn Db,
    web: Arc<dyn HttpClient + Send + Sync>,
    delay: Duration,
    cache: &FullTextCache,
    stop: &AtomicBool,
    progress: &mut dyn FnMut(Progress),
) -> Result<FulltextReport, PipelineError> {
    let mut report = FulltextReport::default();
    if let Some(until) = rate_limited_until(db)? {
        report.end = FulltextEnd::RateLimited { until };
        return Ok(report);
    }
    report.old_files_removed = finish_cache_deletions(db, cache)?;
    let polite = Arc::new(PoliteClient::new(web, delay));
    let service = FullTextService::new(polite.clone(), "")
        .with_cache(Some(cache.clone()))
        .with_pdf_extractor(Arc::new(MupdfPdfExtractor::new()))
        .with_fetch_pdf_with_jats(false);
    while let Some(paper) = next_paper(db)? {
        if stop.load(Ordering::Relaxed) {
            report.end = FulltextEnd::Stopped;
            break;
        }
        let sources = sources(db, &paper)?;
        let pdf_urls: Vec<String> = sources
            .iter()
            .filter(|s| s.format == "pdf")
            .map(|s| s.url.clone())
            .collect();
        let request = FullTextRequest {
            fulltext_sources: sources,
            pmc_id: None,
            doi: None,
            pmid: String::new(),
            identifier: Some(paper.identifier()),
        };
        let result = service.fetch_fulltext(&request);
        service.clear_log();
        let records = polite.take_records();
        if polite.rate_limited() {
            let until = record_rate_limit(db)?;
            progress(Progress {
                phase: Phase::Fulltext,
                message: format!("medRxiv asked us to slow down; full text resumes after {until}"),
            });
            report.end = FulltextEnd::RateLimited { until };
            break;
        }
        let classified = classify(&result, &records, &pdf_urls);
        let replaced = record(db, cache, &paper, &classified)?;
        report.tried += 1;
        let line = match &classified {
            Classified::Jats => {
                report.jats += 1;
                "JATS full text".to_string()
            }
            Classified::Pdf => {
                report.pdf += 1;
                "PDF full text".to_string()
            }
            Classified::Failed { reason, kind } => {
                match kind {
                    FailureKind::Lasting => report.lasting += 1,
                    FailureKind::Passing => report.passing += 1,
                }
                format!("abstract only: {reason}")
            }
        };
        if replaced {
            report.replaced += 1;
        }
        progress(Progress {
            phase: Phase::Fulltext,
            message: format!("{} v{}: {line}", paper.doi, paper.version),
        });
    }
    Ok(report)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn rec(url: &str, outcome: RequestOutcome) -> RequestRecord {
        RequestRecord {
            url: url.into(),
            outcome,
        }
    }

    fn pdf_urls() -> Vec<String> {
        vec!["https://m/p.pdf".into()]
    }

    fn ok(r: FullTextResult) -> Result<FullTextResult, FullTextError> {
        Ok(r)
    }

    fn empty() -> FullTextResult {
        serde_json::from_value(serde_json::json!({"source": "medrxiv"})).unwrap()
    }

    #[test]
    fn passing_waits_double_up_to_the_cap() {
        assert_eq!(retry_delay(FailureKind::Passing, 1), RETRY_BASE);
        assert_eq!(retry_delay(FailureKind::Passing, 2), RETRY_BASE * 2);
        assert_eq!(retry_delay(FailureKind::Passing, 3), RETRY_BASE * 4);
        assert_eq!(retry_delay(FailureKind::Passing, 1000), RETRY_MAX);
        assert_eq!(retry_delay(FailureKind::Lasting, 1), LASTING_RETRY);
    }

    #[test]
    fn jats_with_a_body_is_jats() {
        let r = FullTextResult {
            content_kind: ContentKind::Fulltext,
            jats_xml: Some(b"<article/>".to_vec()),
            ..empty()
        };
        assert_eq!(classify(&ok(r), &[], &pdf_urls()), Classified::Jats);
    }

    #[test]
    fn an_extracted_pdf_is_pdf_and_a_scan_is_lasting() {
        let pdf = FullTextResult {
            file_path: Some("/c/p.pdf".into()),
            content_kind: ContentKind::Extracted,
            ..empty()
        };
        assert_eq!(
            classify(&ok(pdf.clone()), &[], &pdf_urls()),
            Classified::Pdf
        );
        let scan = FullTextResult {
            content_kind: ContentKind::None,
            ..pdf
        };
        assert!(matches!(
            classify(&ok(scan), &[], &pdf_urls()),
            Classified::Failed {
                kind: FailureKind::Lasting,
                ..
            }
        ));
    }

    #[test]
    fn jats_404_then_pdf_403_is_lasting_and_names_both() {
        let r = FullTextResult {
            pdf_url: Some("https://m/p.pdf".into()),
            pdf_download_failure: Some("http-403".into()),
            ..empty()
        };
        let records = [
            rec("https://m/j.xml", RequestOutcome::Status(404)),
            rec("https://m/p.pdf", RequestOutcome::Status(403)),
        ];
        let Classified::Failed { reason, kind } = classify(&ok(r), &records, &pdf_urls()) else {
            panic!("not a failure")
        };
        assert_eq!(kind, FailureKind::Lasting);
        assert_eq!(
            reason,
            "JATS: not found (HTTP 404); PDF: refused (HTTP 403)"
        );
    }

    #[test]
    fn the_pdf_decides_the_kind_when_one_was_requested() {
        let r = FullTextResult {
            pdf_download_failure: Some("http-503".into()),
            ..empty()
        };
        let records = [
            rec("https://m/j.xml", RequestOutcome::Status(404)),
            rec("https://m/p.pdf", RequestOutcome::Status(503)),
        ];
        assert!(matches!(
            classify(&ok(r), &records, &pdf_urls()),
            Classified::Failed {
                kind: FailureKind::Passing,
                ..
            }
        ));
    }

    #[test]
    fn a_pdf_that_could_not_be_saved_is_passing() {
        let r = FullTextResult {
            pdf_download_failure: Some(PDF_WRITE_FAILED.into()),
            ..empty()
        };
        let records = [
            rec("https://m/j.xml", RequestOutcome::Status(404)),
            rec("https://m/p.pdf", RequestOutcome::Status(200)),
        ];
        assert!(matches!(
            classify(&ok(r), &records, &pdf_urls()),
            Classified::Failed {
                kind: FailureKind::Passing,
                ..
            }
        ));
    }

    #[test]
    fn jats_only_failures_map_by_status() {
        let only_jats = |outcome| classify(&ok(empty()), &[rec("https://m/j.xml", outcome)], &[]);
        for (outcome, want) in [
            (RequestOutcome::Status(404), FailureKind::Lasting),
            (RequestOutcome::Status(403), FailureKind::Lasting),
            (RequestOutcome::Status(200), FailureKind::Lasting),
            (RequestOutcome::Status(408), FailureKind::Passing),
            (RequestOutcome::Status(502), FailureKind::Passing),
            (
                RequestOutcome::NoResponse("timed out".into()),
                FailureKind::Passing,
            ),
        ] {
            let got = only_jats(outcome.clone());
            assert!(
                matches!(&got, Classified::Failed { kind, .. } if *kind == want),
                "{outcome:?} gave {got:?}"
            );
        }
    }

    #[test]
    fn unreferenced_entries_are_those_no_row_names() {
        let dir = tempfile::tempdir().unwrap();
        let cache = FullTextCache {
            cache_dir: dir.path().to_path_buf(),
        };
        cache.save_jats(b"<a/>", "kept").unwrap();
        cache.save_jats(b"<a/>", "orphan").unwrap();
        cache.save_pdf(b"%PDF-1.4\n", "orphan2").unwrap();
        let known: HashSet<String> = ["kept".to_string()].into();
        assert_eq!(
            unreferenced_cache_keys(&cache, &known),
            vec!["orphan", "orphan2"]
        );
    }
}
