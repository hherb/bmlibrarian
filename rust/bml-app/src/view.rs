//! What the screens show, computed from the crates' own types: plain Rust, no
//! Tauri, so it is unit-tested.

use bml_library::status::LibraryStatus;
use bml_library::{Phase, Progress, WAITING_FOR_INTERNET};
use serde::Serialize;

/// Seconds one paper takes from search to searchable, measured on the demo
/// Mac on 2026-11-15 (Europe PMC from Australia): ~0.9 s of day searches,
/// ~6 s of full text and ~3.1 s of embedding (HANDOVER, investor demo).
pub const SECONDS_PER_PAPER: f64 = 10.0;

/// The counts screen 5 shows.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
pub struct LibraryCounts {
    /// Papers found so far.
    pub found: i64,
    /// Papers with their full text downloaded.
    pub full_text: i64,
    /// Papers kept with their abstract only.
    pub abstract_only: i64,
    /// Papers that search can find.
    pub searchable: i64,
}

/// Screen 5's counts from the library's status.
#[must_use]
pub fn counts_from_status(status: &LibraryStatus) -> LibraryCounts {
    LibraryCounts {
        found: status.papers,
        full_text: status.jats + status.pdf,
        abstract_only: status.abstract_only,
        searchable: status.indexed,
    }
}

/// One progress event as a line a non-technical reader follows.
#[must_use]
pub fn progress_line(progress: &Progress) -> String {
    if progress.message == WAITING_FOR_INTERNET {
        return progress.message.clone();
    }
    format!("{}: {}", step_name(progress.phase), progress.message)
}

/// A phase as a non-technical reader names the step.
fn step_name(phase: Phase) -> &'static str {
    match phase {
        Phase::Metadata => "Finding papers",
        Phase::Fulltext => "Downloading full text",
        Phase::Index => "Making papers searchable",
    }
}

/// How an update ended, for the window.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Finished {
    /// Every paper found so far is downloaded and searchable.
    pub complete: bool,
    /// It stopped because the network is down; the window retries.
    pub waiting: bool,
    /// One plain-language line.
    pub message: String,
}

/// How an update ended: `waited` says a [`WAITING_FOR_INTERNET`] line came
/// during it, so a stop then is the network, not the Pause button. A failure
/// is named before anything else, then the network, a rate limit and a pause.
#[must_use]
pub fn finished(result: &Result<bml_library::UpdateReport, String>, waited: bool) -> Finished {
    let ended = |complete, waiting, message: String| Finished {
        complete,
        waiting,
        message,
    };
    let report = match result {
        Ok(report) => report,
        Err(e) => return ended(false, false, e.clone()),
    };
    if let Some((phase, why)) = report.failures.first() {
        return ended(
            false,
            false,
            format!("{} stopped: {why}", step_name(*phase)),
        );
    }
    if let Some(why) = &report.last_update_error {
        return ended(false, false, why.clone());
    }
    if waited && report.stopped_early() {
        return ended(false, true, WAITING_FOR_INTERNET.to_string());
    }
    if let Some(until) = rate_limited_until(report) {
        let when = until.map_or_else(
            || "at the next update".to_string(),
            |until| format!("after {until}"),
        );
        return ended(
            false,
            false,
            format!("Europe PMC asked us to slow down; downloading carries on {when}."),
        );
    }
    if report.stopped_early() {
        return ended(
            false,
            false,
            "Paused. Press Resume to carry on.".to_string(),
        );
    }
    if report.failed() {
        return ended(
            false,
            false,
            "Some papers could not be downloaded or made searchable; they are tried again next time."
                .to_string(),
        );
    }
    ended(true, false, "Your library is up to date.".to_string())
}

/// `Some` when Europe PMC rate-limited the update, with the time full text
/// may resume when it is known.
fn rate_limited_until(report: &bml_library::UpdateReport) -> Option<Option<String>> {
    if let Some(bml_library::fulltext::FulltextEnd::RateLimited { until }) =
        report.fulltext.as_ref().map(|f| &f.end)
    {
        return Some(Some(until.clone()));
    }
    report
        .metadata
        .as_ref()
        .is_some_and(|m| m.rate_limited)
        .then_some(None)
}

/// Minutes until every paper found so far is searchable, rounded up; `None`
/// when nothing is left.
#[must_use]
pub fn minutes_left(counts: &LibraryCounts) -> Option<u64> {
    let left = counts.found.saturating_sub(counts.searchable);
    if left <= 0 {
        return None;
    }
    let seconds = f64::from(u32::try_from(left).unwrap_or(u32::MAX)) * SECONDS_PER_PAPER;
    // Whole minutes, at least one; the value is small and non-negative.
    #[allow(clippy::cast_possible_truncation, clippy::cast_sign_loss)]
    Some((seconds / 60.0).ceil() as u64)
}

#[cfg(test)]
mod tests {
    use super::*;
    use bml_library::status::LibraryStatus;
    use bml_library::{Phase, Progress, WAITING_FOR_INTERNET};

    #[test]
    fn a_rate_limit_is_not_a_pause() {
        use bml_library::fulltext::{FulltextEnd, FulltextReport};
        use bml_library::metadata::MetadataReport;
        use bml_library::UpdateReport;
        let metadata = UpdateReport {
            metadata: Some(MetadataReport {
                stopped: true,
                rate_limited: true,
                ..MetadataReport::default()
            }),
            ..UpdateReport::default()
        };
        let ended = finished(&Ok(metadata), false);
        assert!(
            ended.message.contains("asked us to slow down"),
            "{}",
            ended.message
        );
        assert!(!ended.message.starts_with("Paused"));
        let fulltext = UpdateReport {
            fulltext: Some(FulltextReport {
                end: FulltextEnd::RateLimited {
                    until: "2026-11-16 10:00".into(),
                },
                ..FulltextReport::default()
            }),
            ..UpdateReport::default()
        };
        let ended = finished(&Ok(fulltext), false);
        assert!(
            ended.message.contains("2026-11-16 10:00"),
            "{}",
            ended.message
        );
    }

    #[test]
    fn a_failure_says_what_failed() {
        use bml_library::UpdateReport;
        let report = UpdateReport {
            failures: vec![(
                Phase::Index,
                "the embedding model is missing or damaged; run `bml setup`".into(),
            )],
            ..UpdateReport::default()
        };
        // Even with a waiting line seen, the failure is what the user needs.
        let ended = finished(&Ok(report), true);
        assert!(!ended.waiting && !ended.complete);
        assert!(
            ended.message.contains("embedding model is missing"),
            "{}",
            ended.message
        );
        let stamp = UpdateReport {
            last_update_error: Some("recording the update's time failed: disk full".into()),
            ..UpdateReport::default()
        };
        assert!(finished(&Ok(stamp), false).message.contains("disk full"));
    }

    #[test]
    fn a_real_offline_report_reads_waiting() {
        use bml_library::fulltext::{FulltextEnd, FulltextReport};
        use bml_library::metadata::MetadataReport;
        use bml_library::UpdateReport;
        // As a_round_with_no_network_stops_cleanly leaves it: errors and stopped.
        let metadata = UpdateReport {
            metadata: Some(MetadataReport {
                days: 7,
                errors: vec!["day failed".into(); 7],
                stopped: true,
                ..MetadataReport::default()
            }),
            ..UpdateReport::default()
        };
        assert!(finished(&Ok(metadata), true).waiting);
        let fulltext = UpdateReport {
            fulltext: Some(FulltextReport {
                end: FulltextEnd::NoNetwork,
                ..FulltextReport::default()
            }),
            ..UpdateReport::default()
        };
        assert!(finished(&Ok(fulltext), true).waiting);
    }

    #[test]
    fn how_an_update_ended_reads_plainly() {
        use bml_library::metadata::MetadataReport;
        use bml_library::UpdateReport;
        let done = finished(&Ok(UpdateReport::default()), false);
        assert!(done.complete && !done.waiting);
        let stopped = || UpdateReport {
            metadata: Some(MetadataReport {
                stopped: true,
                ..MetadataReport::default()
            }),
            ..UpdateReport::default()
        };
        let offline = finished(&Ok(stopped()), true);
        assert!(offline.waiting && !offline.complete);
        assert_eq!(offline.message, WAITING_FOR_INTERNET);
        let paused = finished(&Ok(stopped()), false);
        assert!(!paused.waiting && !paused.complete);
        assert!(paused.message.starts_with("Paused"), "{}", paused.message);
        let failed = finished(
            &Ok(UpdateReport {
                failures: vec![(Phase::Fulltext, "x".into())],
                ..UpdateReport::default()
            }),
            false,
        );
        assert!(!failed.complete && !failed.waiting);
        let broken = finished(&Err("the database would not start".into()), false);
        assert_eq!(broken.message, "the database would not start");
    }

    #[test]
    fn counts_from_status_maps_the_library() {
        let status = LibraryStatus {
            papers: 120,
            jats: 70,
            pdf: 5,
            abstract_only: 15,
            not_tried: 30,
            indexed: 90,
            to_index: 30,
            ..LibraryStatus::default()
        };
        assert_eq!(
            counts_from_status(&status),
            LibraryCounts {
                found: 120,
                full_text: 75,
                abstract_only: 15,
                searchable: 90,
            }
        );
    }

    #[test]
    fn offline_failure_reads_waiting_for_internet() {
        let line = progress_line(&Progress {
            phase: Phase::Metadata,
            message: WAITING_FOR_INTERNET.to_string(),
        });
        assert_eq!(
            line,
            "Waiting for the internet. Downloading carries on when it's back."
        );
    }

    #[test]
    fn progress_lines_name_the_step_in_plain_words() {
        let line = progress_line(&Progress {
            phase: Phase::Fulltext,
            message: "PMC123: JATS full text".to_string(),
        });
        assert_eq!(line, "Downloading full text: PMC123: JATS full text");
        let line = progress_line(&Progress {
            phase: Phase::Index,
            message: "3 paper(s) ready to search (2 with full text, 40 passages)".to_string(),
        });
        assert!(line.starts_with("Making papers searchable: "), "{line}");
        let line = progress_line(&Progress {
            phase: Phase::Metadata,
            message: "2026-10-17 to 2026-11-15: 30 day(s), 46 new, 0 updated".to_string(),
        });
        assert!(line.starts_with("Finding papers: "), "{line}");
    }

    #[test]
    fn minutes_left_counts_the_papers_not_yet_searchable() {
        let counts = LibraryCounts {
            found: 100,
            full_text: 40,
            abstract_only: 0,
            searchable: 40,
        };
        // 60 papers at SECONDS_PER_PAPER each, rounded up to whole minutes.
        let expected = (60.0 * SECONDS_PER_PAPER / 60.0_f64).ceil() as u64;
        assert_eq!(minutes_left(&counts), Some(expected));
        let done = LibraryCounts {
            searchable: 100,
            ..counts
        };
        assert_eq!(minutes_left(&done), None);
    }
}
