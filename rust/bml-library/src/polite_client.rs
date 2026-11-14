//! [`PoliteClient`]: an [`HttpClient`] that sends one request at a time,
//! spaced by a fixed delay, records what each request got, and stops sending
//! after the first 429.

use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use bmlib::publications::fetchers::{FetchError, HttpClient, HttpResponse};

/// The HTTP status a server sends when it rate-limits us.
pub const HTTP_TOO_MANY_REQUESTS: u16 = 429;

/// What one request got.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RequestOutcome {
    /// The server answered with this status.
    Status(u16),
    /// No answer: a timeout, a reset, DNS (the transport error's message).
    NoResponse(String),
    /// Not sent, because the host rate-limited an earlier request.
    NotSent,
}

/// One request and what it got.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RequestRecord {
    /// The URL asked for.
    pub url: String,
    /// What it got.
    pub outcome: RequestOutcome,
}

struct State {
    last_request_end: Option<Instant>,
    rate_limited: bool,
    records: Vec<RequestRecord>,
}

/// Sleeps for a duration (replaced in tests).
pub type Sleeper = Box<dyn Fn(Duration) + Send + Sync>;

/// See the module docs. The spacing is measured from the end of one request
/// to the start of the next, and the lock is held while sleeping, so two
/// threads sharing the client still send one request at a time.
pub struct PoliteClient {
    inner: Arc<dyn HttpClient + Send + Sync>,
    delay: Duration,
    sleep: Sleeper,
    state: Mutex<State>,
}

impl PoliteClient {
    /// Wrap `inner`, spacing requests by `delay`.
    #[must_use]
    pub fn new(inner: Arc<dyn HttpClient + Send + Sync>, delay: Duration) -> Self {
        PoliteClient {
            inner,
            delay,
            sleep: Box::new(std::thread::sleep),
            state: Mutex::new(State {
                last_request_end: None,
                rate_limited: false,
                records: Vec::new(),
            }),
        }
    }

    /// The same client sleeping through `sleep` (tests record the waits).
    #[must_use]
    pub fn with_sleeper(mut self, sleep: Sleeper) -> Self {
        self.sleep = sleep;
        self
    }

    fn state(&self) -> std::sync::MutexGuard<'_, State> {
        self.state.lock().unwrap_or_else(|e| e.into_inner())
    }

    /// The requests since the last call, oldest first.
    pub fn take_records(&self) -> Vec<RequestRecord> {
        std::mem::take(&mut self.state().records)
    }

    /// Whether a request got a 429; every later request fails unsent.
    pub fn rate_limited(&self) -> bool {
        self.state().rate_limited
    }
}

impl HttpClient for PoliteClient {
    fn get(&self, url: &str) -> Result<HttpResponse, FetchError> {
        let mut state = self.state();
        if state.rate_limited {
            state.records.push(RequestRecord {
                url: url.to_string(),
                outcome: RequestOutcome::NotSent,
            });
            return Err(FetchError::Transport(format!(
                "not sent: the server rate-limited an earlier request (GET {url})"
            )));
        }
        if let Some(end) = state.last_request_end {
            let waited = end.elapsed();
            if waited < self.delay {
                (self.sleep)(self.delay - waited);
            }
        }
        let result = self.inner.get(url);
        state.last_request_end = Some(Instant::now());
        let outcome = match &result {
            Ok(response) => RequestOutcome::Status(response.status),
            Err(FetchError::HttpStatus { status, .. }) => RequestOutcome::Status(*status),
            Err(error) => RequestOutcome::NoResponse(error.to_string()),
        };
        if outcome == RequestOutcome::Status(HTTP_TOO_MANY_REQUESTS) {
            state.rate_limited = true;
        }
        state.records.push(RequestRecord {
            url: url.to_string(),
            outcome,
        });
        result
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::testing::FakeHttp;

    fn client(fake: FakeHttp, delay: Duration) -> (PoliteClient, Arc<Mutex<Vec<Duration>>>) {
        let waits = Arc::new(Mutex::new(Vec::new()));
        let recorded = waits.clone();
        let client = PoliteClient::new(Arc::new(fake), delay)
            .with_sleeper(Box::new(move |d| recorded.lock().unwrap().push(d)));
        (client, waits)
    }

    #[test]
    fn requests_after_the_first_wait_out_the_delay() {
        let delay = Duration::from_secs(30);
        let fake = FakeHttp::new()
            .route("https://x/a", 200, "a")
            .route("https://x/b", 404, "");
        let (client, waits) = client(fake, delay);
        client.get("https://x/a").unwrap();
        client.get("https://x/b").unwrap();
        let waits = waits.lock().unwrap();
        assert_eq!(waits.len(), 1, "only the second request waits");
        assert!(waits[0] > delay - Duration::from_secs(1), "{waits:?}");
        assert_eq!(
            client.take_records(),
            vec![
                RequestRecord {
                    url: "https://x/a".into(),
                    outcome: RequestOutcome::Status(200)
                },
                RequestRecord {
                    url: "https://x/b".into(),
                    outcome: RequestOutcome::Status(404)
                },
            ]
        );
        assert!(
            client.take_records().is_empty(),
            "taking empties the record"
        );
    }

    #[test]
    fn a_429_stops_every_later_request_unsent() {
        let fake = FakeHttp::new().route("https://x/a", 429, "");
        let seen = fake.seen();
        let (client, _) = client(fake, Duration::ZERO);
        assert_eq!(client.get("https://x/a").unwrap().status, 429);
        assert!(client.rate_limited());
        assert!(client.get("https://x/b").is_err());
        assert_eq!(
            seen.lock().unwrap().as_slice(),
            ["https://x/a"],
            "b never reached the host"
        );
        assert_eq!(client.take_records()[1].outcome, RequestOutcome::NotSent);
    }

    #[test]
    fn a_transport_failure_is_recorded_as_no_response() {
        let (client, _) = client(FakeHttp::new(), Duration::ZERO);
        assert!(client.get("https://x/unrouted").is_err());
        assert!(matches!(
            client.take_records()[0].outcome,
            RequestOutcome::NoResponse(_)
        ));
        assert!(!client.rate_limited());
    }
}
