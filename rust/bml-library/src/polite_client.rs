//! [`PoliteClient`]: an [`HttpClient`] that sends one request at a time,
//! spaced by a fixed delay, records what each request got, and stops sending
//! after the first 429 or after [`NO_ANSWER_LIMIT`] requests in a row without
//! an answer (no answer at all, or a web page in the data's place).

use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use bmlib::publications::fetchers::{FetchError, HttpClient, HttpResponse};

/// The HTTP status a server sends when it rate-limits us.
pub const HTTP_TOO_MANY_REQUESTS: u16 = 429;

/// Requests in a row with no answer (or a web page, see
/// [`RequestOutcome::WebPage`]) after which the network is taken to be down:
/// every later request fails unsent, so a dead phone link costs a few requests
/// (and, when they hang, a few time-outs) rather than one per day or paper
/// left.
pub const NO_ANSWER_LIMIT: u32 = 3;

/// What one request got.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RequestOutcome {
    /// The server answered with this status.
    Status(u16),
    /// A 200 whose body is an HTML page (a Wi-Fi sign-in page, a challenge
    /// page), where data was asked for. The caller gets an error instead of
    /// the page, so bmlib never parses or caches it (its JATS reader takes an
    /// XHTML page's `<body><p>` for an article), and it counts towards
    /// [`NO_ANSWER_LIMIT`]: a sign-in page means there is no internet yet.
    WebPage,
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
    no_answer_in_a_row: u32,
    gave_up: bool,
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
                no_answer_in_a_row: 0,
                gave_up: false,
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

    /// Whether [`NO_ANSWER_LIMIT`] requests in a row got no answer or a web
    /// page; every later request fails unsent.
    pub fn gave_up(&self) -> bool {
        self.state().gave_up
    }
}

impl HttpClient for PoliteClient {
    fn get(&self, url: &str) -> Result<HttpResponse, FetchError> {
        let mut state = self.state();
        if state.rate_limited || state.gave_up {
            state.records.push(RequestRecord {
                url: url.to_string(),
                outcome: RequestOutcome::NotSent,
            });
            let why = if state.rate_limited {
                "the server rate-limited an earlier request"
            } else {
                "the last requests got no answer or a sign-in page (no network)"
            };
            return Err(FetchError::Transport(format!(
                "not sent: {why} (GET {url})"
            )));
        }
        if let Some(end) = state.last_request_end {
            let waited = end.elapsed();
            if waited < self.delay {
                (self.sleep)(self.delay - waited);
            }
        }
        let mut result = self.inner.get(url);
        state.last_request_end = Some(Instant::now());
        let outcome = match &result {
            Ok(response) if response.status == 200 && is_web_page(&response.body) => {
                RequestOutcome::WebPage
            }
            Ok(response) => RequestOutcome::Status(response.status),
            Err(FetchError::HttpStatus { status, .. }) => RequestOutcome::Status(*status),
            Err(error) => RequestOutcome::NoResponse(error.to_string()),
        };
        if outcome == RequestOutcome::Status(HTTP_TOO_MANY_REQUESTS) {
            state.rate_limited = true;
        }
        if outcome == RequestOutcome::WebPage {
            result = Err(FetchError::Malformed(format!(
                "a web page came back instead of the data (a Wi-Fi sign-in page?) (GET {url})"
            )));
        }
        if matches!(
            outcome,
            RequestOutcome::NoResponse(_) | RequestOutcome::WebPage
        ) {
            state.no_answer_in_a_row += 1;
            state.gave_up |= state.no_answer_in_a_row >= NO_ANSWER_LIMIT;
        } else {
            state.no_answer_in_a_row = 0;
        }
        state.records.push(RequestRecord {
            url: url.to_string(),
            outcome,
        });
        result
    }
}

/// Whether `body` starts like an HTML page: `<!doctype html` or `<html`,
/// after a byte-order mark, white space, an XML declaration and comments (an
/// XHTML page starts `<?xml …?>`). None of the library's sources answers with
/// HTML: they send JSON, JATS XML (`<!DOCTYPE article`, `<article`) or a PDF.
#[must_use]
pub fn is_web_page(body: &[u8]) -> bool {
    let starts_with = |head: &[u8], prefix: &[u8]| {
        head.len() >= prefix.len() && head[..prefix.len()].eq_ignore_ascii_case(prefix)
    };
    let mut head = body.strip_prefix(b"\xEF\xBB\xBF").unwrap_or(body);
    loop {
        head = head.trim_ascii_start();
        let skip = [(b"<?".as_slice(), b"?>".as_slice()), (b"<!--", b"-->")]
            .into_iter()
            .find(|(open, _)| head.starts_with(open))
            .map(|(_, close)| {
                head.windows(close.len())
                    .position(|w| w == close)
                    .map_or(head.len(), |at| at + close.len())
            });
        match skip {
            Some(end) => head = &head[end..],
            None => break,
        }
    }
    starts_with(head, b"<!doctype html") || starts_with(head, b"<html")
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
    fn an_html_page_is_told_from_data() {
        assert!(is_web_page(b"<!DOCTYPE html><html>Sign in</html>"));
        assert!(is_web_page(
            b"\xEF\xBB\xBF \n<HTML><body>Wi-Fi</body></HTML>"
        ));
        assert!(!is_web_page(b"<?xml version=\"1.0\"?><article/>"));
        assert!(!is_web_page(b"{\"hitCount\": 1}"));
        assert!(!is_web_page(b"%PDF-1.7"));
        assert!(!is_web_page(b"<htm"));
        assert!(!is_web_page(b""));
        // XHTML, and a page that starts with a comment.
        assert!(is_web_page(
            b"<?xml version=\"1.0\"?>\n<!DOCTYPE html PUBLIC \"-//W3C//DTD XHTML 1.0//EN\"><html/>"
        ));
        assert!(is_web_page(b"<!-- portal --><html><body/></html>"));
        assert!(!is_web_page(
            b"<?xml version=\"1.0\"?><!-- c --><!DOCTYPE article PUBLIC \"-//NLM//DTD JATS\"><article/>"
        ));
        assert!(!is_web_page(b"<?xml unclosed"));
    }

    #[test]
    fn a_200_web_page_is_an_error_and_counts_as_no_answer() {
        let fake = FakeHttp::new()
            .route("https://x/j.xml", 200, "<html>Sign in</html>")
            .route("https://x/ok", 200, "ok");
        let (client, _) = client(fake, Duration::ZERO);
        let error = client.get("https://x/j.xml").unwrap_err();
        assert!(matches!(error, FetchError::Malformed(_)), "{error:?}");
        assert_eq!(client.take_records()[0].outcome, RequestOutcome::WebPage);
        // A web page and no answer mix in one run of NO_ANSWER_LIMIT.
        assert!(client.get("https://x/down").is_err());
        assert!(!client.gave_up());
        assert!(client.get("https://x/j.xml").is_err());
        assert!(client.gave_up());
        assert!(
            client.get("https://x/ok").is_err(),
            "not sent once given up"
        );
    }

    #[test]
    fn an_error_status_with_an_html_body_keeps_its_status() {
        let page = "<!DOCTYPE html><html>Error</html>";
        let fake =
            FakeHttp::new()
                .route("https://x/gone", 404, page)
                .route("https://x/slow", 429, page);
        let (client, _) = client(fake, Duration::ZERO);
        assert_eq!(client.get("https://x/gone").unwrap().status, 404);
        assert_eq!(client.get("https://x/slow").unwrap().status, 429);
        assert!(client.rate_limited(), "an HTML 429 still rate-limits");
        let outcomes: Vec<_> = client
            .take_records()
            .into_iter()
            .map(|r| r.outcome)
            .collect();
        assert_eq!(
            outcomes,
            [RequestOutcome::Status(404), RequestOutcome::Status(429)]
        );
    }

    #[test]
    fn no_answer_in_a_row_stops_every_later_request_unsent() {
        // No routes: every request is a transport error (the network is down).
        let fake = FakeHttp::new().route("https://x/ok", 200, "ok");
        let seen = fake.seen();
        let (client, _) = client(fake, Duration::ZERO);
        for _ in 0..NO_ANSWER_LIMIT - 1 {
            assert!(client.get("https://x/down").is_err());
        }
        // An answer resets the count.
        client.get("https://x/ok").unwrap();
        assert!(!client.gave_up());
        for _ in 0..NO_ANSWER_LIMIT {
            assert!(client.get("https://x/down").is_err());
        }
        assert!(client.gave_up());
        let sent = seen.lock().unwrap().len();
        assert!(
            client.get("https://x/ok").is_err(),
            "not sent once given up"
        );
        assert_eq!(seen.lock().unwrap().len(), sent);
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
