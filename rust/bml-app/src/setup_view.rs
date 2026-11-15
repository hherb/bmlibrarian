//! Screens 1–4 in plain Rust (no Tauri), so they are unit-tested: the `bml`
//! beside the app, setup's events as status lines, and the topic counts.

use std::path::{Path, PathBuf};
use std::sync::mpsc::channel;
use std::sync::Arc;
use std::time::{Duration, Instant};

use bml_library::topics::{count_url, parse_hit_count, TOPICS};
use bml_setup::{StepEvent, StepId, StepOutcome};
use bmlib::publications::fetchers::HttpClient;
use serde::Serialize;

/// How long screen 4 waits for Europe PMC's live counts before showing the
/// stored ones (a slow phone connection must not hold the screen).
pub const TOPIC_COUNT_TIMEOUT: Duration = Duration::from_secs(5);

/// Disk a paper takes in the library (documents and database), measured on
/// the demo library on 2026-11-15 (HANDOVER, investor demo).
pub const MB_PER_PAPER: f64 = 1.2;

/// Screen 2's rough estimate for the largest preset, in bytes.
#[must_use]
pub fn largest_topic_bytes() -> u64 {
    let papers = TOPICS.iter().map(|t| t.stored_count).max().unwrap_or(0);
    // A few GB at most; the cast cannot lose anything that matters here.
    #[allow(clippy::cast_possible_truncation, clippy::cast_sign_loss)]
    let bytes = (f64::from(papers) * MB_PER_PAPER * 1024.0 * 1024.0) as u64;
    bytes
}

/// The `bml` program next to `app_exe`, which login entries and scheduled
/// updates must run (the app's own executable would open a window).
#[must_use]
pub fn bml_beside(app_exe: &Path) -> Option<PathBuf> {
    let bml = app_exe
        .parent()?
        .join(format!("bml{}", std::env::consts::EXE_SUFFIX));
    bml.is_file().then_some(bml)
}

/// Where a step stands, for its status line's colour.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum StepState {
    /// Running.
    Working,
    /// Finished (or nothing to do, or left out).
    Done,
    /// Finished with something to read.
    Warning,
    /// Failed; "Try again" is offered.
    Failed,
}

/// One status line on screen 3.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct StepLine {
    /// The step's stable key (`database`, `models`, …).
    pub step: &'static str,
    /// The step's name as people read it.
    pub label: &'static str,
    /// Where it stands.
    pub state: StepState,
    /// What it is doing or did, in plain words.
    pub text: String,
}

/// A step's stable key for the front end.
fn step_key(step: StepId) -> &'static str {
    match step {
        StepId::Hardware => "hardware",
        StepId::Database => "database",
        StepId::Library => "library",
        StepId::Autostart => "autostart",
        StepId::Ollama => "ollama",
        StepId::Models => "models",
        StepId::EmbeddingModel => "embedding",
    }
}

/// Bytes in a megabyte, for download progress.
const MB: u64 = 1024 * 1024;

/// One setup event as a status line.
#[must_use]
pub fn step_line(event: &StepEvent) -> StepLine {
    let line = |step: StepId, state, text: String| StepLine {
        step: step_key(step),
        label: step.label(),
        state,
        text,
    };
    match event {
        StepEvent::Started(step) => line(*step, StepState::Working, "Working…".into()),
        StepEvent::Progress {
            step,
            detail,
            done,
            total,
        } => {
            let text = if *total > 0 {
                format!(
                    "{detail}: {}% ({} of {} MB)",
                    done.saturating_mul(100) / total,
                    done / MB,
                    total / MB
                )
            } else {
                detail.clone()
            };
            line(*step, StepState::Working, text)
        }
        StepEvent::Notice { step, message } => line(*step, StepState::Working, message.clone()),
        StepEvent::Warning { step, message } => line(*step, StepState::Warning, message.clone()),
        StepEvent::Finished(step, outcome) => {
            let (state, text) = match outcome {
                StepOutcome::AlreadyPresent => (StepState::Done, "Already in place".to_string()),
                StepOutcome::Installed => (StepState::Done, "Done".to_string()),
                StepOutcome::Started => (StepState::Done, "Started".to_string()),
                StepOutcome::Warnings(w) => (StepState::Warning, w.join(" ")),
                StepOutcome::Skipped { reason } => (StepState::Done, format!("Left out: {reason}")),
                StepOutcome::Failed(message) => (StepState::Failed, message.clone()),
            };
            line(*step, state, text)
        }
    }
}

/// A topic on screen 4 and its paper count.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct TopicCount {
    /// The preset's id.
    pub id: &'static str,
    /// Its name.
    pub name: &'static str,
    /// Papers matching (live, or as measured when offline).
    pub count: u64,
    /// Whether `count` came from Europe PMC just now.
    pub live: bool,
}

/// Every preset's count, asked of Europe PMC through `client` at once, each
/// falling back to its stored count when no answer arrives within `timeout`.
#[must_use]
pub fn topic_counts_with(
    client: Arc<dyn HttpClient + Send + Sync>,
    timeout: Duration,
) -> Vec<TopicCount> {
    let (tx, rx) = channel();
    for (index, topic) in TOPICS.iter().enumerate() {
        let (tx, client) = (tx.clone(), client.clone());
        std::thread::spawn(move || {
            let count = client
                .get(&count_url(topic))
                .ok()
                .filter(|r| r.is_success())
                .and_then(|r| r.text().ok().and_then(parse_hit_count));
            let _ = tx.send((index, count));
        });
    }
    drop(tx);
    let mut live: Vec<Option<u64>> = vec![None; TOPICS.len()];
    let deadline = Instant::now() + timeout;
    while let Some(left) = deadline.checked_duration_since(Instant::now()) {
        match rx.recv_timeout(left) {
            Ok((index, count)) => live[index] = count,
            Err(_) => break,
        }
    }
    TOPICS
        .iter()
        .zip(live)
        .map(|(topic, count)| TopicCount {
            id: topic.id,
            name: topic.name,
            count: count.unwrap_or(u64::from(topic.stored_count)),
            live: count.is_some(),
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use bml_setup::{StepEvent, StepId, StepOutcome};
    use bmlib::publications::fetchers::{FetchError, HttpClient, HttpResponse};
    use std::sync::Arc;
    use std::time::Duration;

    #[test]
    fn bml_beside_finds_the_sibling_program() {
        let dir = tempfile::tempdir().unwrap();
        let app = dir
            .path()
            .join(format!("bml-app{}", std::env::consts::EXE_SUFFIX));
        assert_eq!(bml_beside(&app), None);
        let bml = dir
            .path()
            .join(format!("bml{}", std::env::consts::EXE_SUFFIX));
        std::fs::write(&bml, b"").unwrap();
        assert_eq!(bml_beside(&app), Some(bml));
    }

    #[test]
    fn step_line_says_what_each_step_did() {
        let started = step_line(&StepEvent::Started(StepId::Database));
        assert_eq!(started.step, "database");
        assert_eq!(started.state, StepState::Working);
        let progress = step_line(&StepEvent::Progress {
            step: StepId::EmbeddingModel,
            detail: "Downloading the embedding model".into(),
            done: 512 * 1024 * 1024,
            total: 1024 * 1024 * 1024,
        });
        assert_eq!(progress.state, StepState::Working);
        assert!(progress.text.contains("50%"), "{}", progress.text);
        let done = step_line(&StepEvent::Finished(
            StepId::Models,
            StepOutcome::AlreadyPresent,
        ));
        assert_eq!(done.state, StepState::Done);
        assert_eq!(done.text, "Already in place");
        let failed = step_line(&StepEvent::Finished(
            StepId::Ollama,
            StepOutcome::Failed("Ollama did not start".into()),
        ));
        assert_eq!(failed.state, StepState::Failed);
        assert_eq!(failed.text, "Ollama did not start");
        let warning = step_line(&StepEvent::Warning {
            step: StepId::Hardware,
            message: "Less than 16 GB of memory".into(),
        });
        assert_eq!(warning.state, StepState::Warning);
    }

    /// Never answers within the test's time limit.
    struct Slow;
    impl HttpClient for Slow {
        fn get(&self, _url: &str) -> Result<HttpResponse, FetchError> {
            std::thread::sleep(Duration::from_millis(500));
            Ok(HttpResponse::ok_text(r#"{"hitCount": 1}"#))
        }
    }

    /// Fails at once, as with no network.
    struct Offline;
    impl HttpClient for Offline {
        fn get(&self, url: &str) -> Result<HttpResponse, FetchError> {
            Err(FetchError::Transport(format!("no network ({url})")))
        }
    }

    /// Answers every count with 1234.
    struct Online;
    impl HttpClient for Online {
        fn get(&self, _url: &str) -> Result<HttpResponse, FetchError> {
            Ok(HttpResponse::ok_text(r#"{"hitCount": 1234}"#))
        }
    }

    #[test]
    fn topic_counts_fall_back_when_offline() {
        for client in [
            Arc::new(Offline) as Arc<dyn HttpClient + Send + Sync>,
            Arc::new(Slow),
        ] {
            let counts = topic_counts_with(client, Duration::from_millis(50));
            assert_eq!(counts.len(), bml_library::topics::TOPICS.len());
            assert_eq!(counts[0].id, "depression-anxiety");
            assert_eq!(counts[0].count, 8372);
            assert!(counts.iter().all(|c| !c.live));
        }
        let live = topic_counts_with(Arc::new(Online), Duration::from_secs(2));
        assert!(live.iter().all(|c| c.live && c.count == 1234));
    }
}
