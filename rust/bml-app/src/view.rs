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
    let step = match progress.phase {
        Phase::Metadata => "Finding papers",
        Phase::Fulltext => "Downloading full text",
        Phase::Index => "Making papers searchable",
    };
    format!("{step}: {}", progress.message)
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
