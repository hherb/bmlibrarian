//! Talking to Ollama over HTTP: host parsing, version, model list, pull, copy.

use std::collections::BTreeMap;
use std::io::{BufRead, BufReader, Read};

use bmlib::http::UreqClient;
use bmlib::publications::fetchers::registry::{FetchError, HttpClient};

use crate::SetupError;

/// Where Ollama listens unless `OLLAMA_HOST` says otherwise.
pub const DEFAULT_OLLAMA_HOST: &str = "http://127.0.0.1:11434";
/// The environment variable Ollama itself reads for its address.
pub const OLLAMA_HOST_ENV: &str = "OLLAMA_HOST";
/// Port Ollama uses when the address names none over `http`.
const DEFAULT_HTTP_PORT: u16 = 11434;
/// Port used when the address names none over `https`.
const DEFAULT_HTTPS_PORT: u16 = 443;
/// A 13.8 GB pull outlasts the 600 s default read timeout (6 hours).
pub const PULL_STREAM_TIMEOUT_SECONDS: u64 = 6 * 3600;

/// Most of an error body worth reading.
const ERROR_BODY_LIMIT: u64 = 64 * 1024;

/// A parsed Ollama address.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OllamaHost {
    /// `scheme://host:port`, no trailing slash.
    pub base_url: String,
    /// Whether the host is this computer.
    pub loopback: bool,
}

/// One progress report from `/api/pull`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PullEvent {
    /// A download with sizes.
    Progress {
        /// Ollama's status text.
        status: String,
        /// Bytes done.
        completed: u64,
        /// Bytes expected.
        total: u64,
    },
    /// A status line without sizes.
    Status(String),
    /// The pull finished.
    Success,
    /// Ollama reported a failure.
    Error(String),
}

/// An HTTP client whose streams may run for hours, for model pulls.
#[must_use]
pub fn pull_http_client() -> UreqClient {
    UreqClient {
        stream_timeout_seconds: PULL_STREAM_TIMEOUT_SECONDS,
        ..UreqClient::default()
    }
}

/// An Ollama error with `message` as its text.
fn ollama_err(message: String) -> SetupError {
    SetupError::Ollama { message }
}

/// Parse `OLLAMA_HOST` (or any address) into a URL and loopback flag.
pub fn parse_ollama_host(raw: Option<&str>) -> Result<OllamaHost, SetupError> {
    let raw = raw.map(str::trim).filter(|r| !r.is_empty());
    let Some(raw) = raw else {
        return parse_ollama_host(Some(DEFAULT_OLLAMA_HOST));
    };
    let bad = |why: &str| {
        ollama_err(format!(
            "The Ollama address {raw:?} (from --ollama-host or OLLAMA_HOST) {why}. Use a form like http://127.0.0.1:11434."
        ))
    };
    let (scheme, rest) = match raw.split_once("://") {
        Some((s, r)) => (s.to_ascii_lowercase(), r),
        None => ("http".to_string(), raw),
    };
    if scheme != "http" && scheme != "https" {
        return Err(bad("must start with http:// or https://"));
    }
    let authority = rest.split('/').next().unwrap_or_default();
    let (host, port) = if let Some(inner) = authority.strip_prefix('[') {
        let (h, after) = inner
            .split_once(']')
            .ok_or_else(|| bad("has an unclosed ["))?;
        (format!("[{h}]"), after.strip_prefix(':'))
    } else if authority.matches(':').count() > 1 {
        (format!("[{authority}]"), None) // bare IPv6, no port
    } else {
        match authority.split_once(':') {
            Some((h, p)) => (h.to_string(), Some(p)),
            None => (authority.to_string(), None),
        }
    };
    if host.is_empty() || host == "[]" {
        return Err(bad("has no host name"));
    }
    let port = match port {
        Some(p) => p.parse::<u16>().map_err(|_| bad("has an invalid port"))?,
        None if scheme == "https" => DEFAULT_HTTPS_PORT,
        None => DEFAULT_HTTP_PORT,
    };
    let host = match host.as_str() {
        "0.0.0.0" => "127.0.0.1".to_string(),
        "[::]" => "[::1]".to_string(),
        _ => host,
    };
    Ok(OllamaHost {
        base_url: format!("{scheme}://{host}:{port}"),
        loopback: bml_pgserver::external::is_loopback_host(&host),
    })
}

/// The error for an Ollama at `host` that answered wrongly (`detail` says how).
fn not_answering(host: &OllamaHost, detail: &str) -> SetupError {
    ollama_err(format!(
        "Ollama at {} did not answer: {detail}. Check that Ollama is running, then run `bml setup` again.",
        host.base_url
    ))
}

/// The `error` text of an Ollama JSON reply, if it has one.
fn body_error(body: &[u8]) -> Option<String> {
    let v: serde_json::Value = serde_json::from_slice(body).ok()?;
    v.get("error")?.as_str().map(str::to_string)
}

/// Ollama's version, or `None` when nothing answers.
pub fn ollama_version(
    http: &dyn HttpClient,
    host: &OllamaHost,
) -> Result<Option<String>, SetupError> {
    Ok(ollama_answer(http, host)?.ok())
}

/// Ollama's version, or `Err` with the connection error when nothing answers.
pub fn ollama_answer(
    http: &dyn HttpClient,
    host: &OllamaHost,
) -> Result<Result<String, String>, SetupError> {
    let resp = match http.get(&format!("{}/api/version", host.base_url)) {
        Ok(r) => r,
        Err(FetchError::Transport(m)) => return Ok(Err(m)),
        Err(e) => return Err(not_answering(host, &e.to_string())),
    };
    if resp.status != 200 {
        return Err(not_answering(host, &format!("HTTP {}", resp.status)));
    }
    serde_json::from_slice::<serde_json::Value>(&resp.body)
        .ok()
        .and_then(|v| v.get("version")?.as_str().map(str::to_string))
        .map(Ok)
        .ok_or_else(|| not_answering(host, "the reply was not a version"))
}

/// Names of the models Ollama has.
pub fn installed_models(
    http: &dyn HttpClient,
    host: &OllamaHost,
) -> Result<Vec<String>, SetupError> {
    let resp = http
        .get(&format!("{}/api/tags", host.base_url))
        .map_err(|e| not_answering(host, &e.to_string()))?;
    if resp.status != 200 {
        return Err(not_answering(host, &format!("HTTP {}", resp.status)));
    }
    let value: serde_json::Value = serde_json::from_slice(&resp.body)
        .map_err(|e| not_answering(host, &format!("the model list was not JSON ({e})")))?;
    bmlib::llm::read_model_listing("ollama", &value)
        .map(|page| page.ids)
        .map_err(|e| not_answering(host, &e.to_string()))
}

/// Whether two model names are the same (case-insensitive, default tag `latest`).
#[must_use]
pub fn same_model(a: &str, b: &str) -> bool {
    let norm = |n: &str| {
        let n = n.to_ascii_lowercase();
        if n.contains(':') {
            n
        } else {
            format!("{n}:latest")
        }
    };
    norm(a) == norm(b)
}

/// Parse one NDJSON line of a pull stream.
pub fn parse_pull_line(line: &str) -> Result<PullEvent, SetupError> {
    let v: serde_json::Value = serde_json::from_str(line).map_err(|e| {
        ollama_err(format!(
            "Ollama sent a pull line that is not JSON ({e}): {line}"
        ))
    })?;
    if let Some(e) = v.get("error").and_then(|e| e.as_str()) {
        return Ok(PullEvent::Error(e.to_string()));
    }
    let status = v
        .get("status")
        .and_then(|s| s.as_str())
        .ok_or_else(|| ollama_err(format!("Ollama sent a pull line without a status: {line}")))?
        .to_string();
    if status == "success" {
        return Ok(PullEvent::Success);
    }
    Ok(match v.get("total").and_then(|t| t.as_u64()) {
        Some(total) => PullEvent::Progress {
            status,
            completed: v.get("completed").and_then(|c| c.as_u64()).unwrap_or(0),
            total,
        },
        None => PullEvent::Status(status),
    })
}

/// Pull `name`, reporting each event; succeeds only on Ollama's `success`.
pub fn pull_model(
    http: &dyn HttpClient,
    host: &OllamaHost,
    name: &str,
    progress: &mut dyn FnMut(&PullEvent),
) -> Result<(), SetupError> {
    let fail = |message: String| SetupError::Pull {
        model: name.to_string(),
        message,
    };
    let body = serde_json::json!({"model": name, "stream": true});
    let stream = http
        .post_json_stream(
            &format!("{}/api/pull", host.base_url),
            &body,
            &BTreeMap::new(),
        )
        .map_err(|e| not_answering(host, &e.to_string()))?;
    if !stream.is_success() {
        let mut text = Vec::new();
        let _ = stream.body.take(ERROR_BODY_LIMIT).read_to_end(&mut text);
        return Err(fail(
            body_error(&text).unwrap_or_else(|| format!("HTTP {}", stream.status)),
        ));
    }
    for line in BufReader::new(stream.body).lines() {
        let line = line.map_err(|e| fail(format!("the download stream broke ({e})")))?;
        if line.trim().is_empty() {
            continue;
        }
        let event = parse_pull_line(&line).map_err(|e| fail(e.to_string()))?;
        progress(&event);
        match event {
            PullEvent::Success => return Ok(()),
            PullEvent::Error(m) => return Err(fail(m)),
            _ => {}
        }
    }
    Err(fail(
        "the download ended before Ollama said it finished".into(),
    ))
}

/// Copy a model to a new name.
pub fn copy_model(
    http: &dyn HttpClient,
    host: &OllamaHost,
    source: &str,
    destination: &str,
) -> Result<(), SetupError> {
    let body = serde_json::json!({"source": source, "destination": destination});
    let resp = http
        .post_json(
            &format!("{}/api/copy", host.base_url),
            &body,
            &BTreeMap::new(),
        )
        .map_err(|e| not_answering(host, &e.to_string()))?;
    if resp.status == 200 {
        return Ok(());
    }
    let why = body_error(&resp.body).unwrap_or_else(|| format!("HTTP {}", resp.status));
    Err(ollama_err(format!(
        "Copying the model {source} to {destination} failed: {why}. Run `bml setup` again."
    )))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::test_support::Fake;

    fn host() -> OllamaHost {
        parse_ollama_host(None).unwrap()
    }

    #[test]
    fn parse_ollama_host_table() {
        let cases = [
            (None, "http://127.0.0.1:11434", true),
            (Some(""), "http://127.0.0.1:11434", true),
            (Some("0.0.0.0"), "http://127.0.0.1:11434", true),
            (Some("127.0.0.1:11434"), "http://127.0.0.1:11434", true),
            (Some("localhost"), "http://localhost:11434", true),
            (
                Some("http://localhost:11434/"),
                "http://localhost:11434",
                true,
            ),
            (Some("[::1]:11434"), "http://[::1]:11434", true),
            (Some("[::]"), "http://[::1]:11434", true),
            (Some("https://gpu-box:443"), "https://gpu-box:443", false),
            (Some("https://gpu-box"), "https://gpu-box:443", false),
            (Some("gpu-box"), "http://gpu-box:11434", false),
        ];
        for (raw, url, loopback) in cases {
            let h = parse_ollama_host(raw).unwrap();
            assert_eq!(
                (h.base_url.as_str(), h.loopback),
                (url, loopback),
                "{raw:?}"
            );
        }
        assert!(parse_ollama_host(Some("ftp://x")).is_err());
        assert!(parse_ollama_host(Some("host:notaport")).is_err());
    }

    #[test]
    fn same_model_rules() {
        assert!(same_model("MedGemma4B_it_q8", "medgemma4B_it_q8:latest"));
        assert!(!same_model("gpt-oss:20b", "gpt-oss:120b"));
    }

    #[test]
    fn pull_line_forms() {
        assert_eq!(
            parse_pull_line(
                r#"{"status":"pulling abc","digest":"sha256:abc","total":100,"completed":40}"#
            )
            .unwrap(),
            PullEvent::Progress {
                status: "pulling abc".into(),
                completed: 40,
                total: 100
            }
        );
        assert_eq!(
            parse_pull_line(r#"{"status":"pulling manifest"}"#).unwrap(),
            PullEvent::Status("pulling manifest".into())
        );
        assert_eq!(
            parse_pull_line(r#"{"status":"success"}"#).unwrap(),
            PullEvent::Success
        );
        assert_eq!(
            parse_pull_line(r#"{"error":"pull model manifest: file does not exist"}"#).unwrap(),
            PullEvent::Error("pull model manifest: file does not exist".into())
        );
        assert!(parse_pull_line("not json").is_err());
    }

    #[test]
    fn pull_success_reports_progress() {
        let mut f = Fake::new();
        f.stream = Some((200, "{\"status\":\"pulling manifest\"}\n\n{\"status\":\"x\",\"total\":10,\"completed\":5}\n{\"status\":\"success\"}\n".into()));
        let mut seen = vec![];
        pull_model(&f, &host(), "m:1", &mut |e| seen.push(e.clone())).unwrap();
        assert_eq!(seen.len(), 3);
        assert_eq!(seen[2], PullEvent::Success);
        assert_eq!(f.urls.borrow()[0], "http://127.0.0.1:11434/api/pull");
    }

    #[test]
    fn pull_without_success_fails() {
        let mut f = Fake::new();
        f.stream = Some((200, "{\"status\":\"pulling manifest\"}\n".into()));
        let e = pull_model(&f, &host(), "m:1", &mut |_| {}).unwrap_err();
        assert!(matches!(e, SetupError::Pull { .. }), "{e}");
    }

    #[test]
    fn pull_error_line_fails() {
        let mut f = Fake::new();
        f.stream = Some((200, "{\"error\":\"disk full\"}\n".into()));
        let e = pull_model(&f, &host(), "m:1", &mut |_| {}).unwrap_err();
        assert!(e.to_string().contains("disk full"), "{e}");
        f.stream = Some((404, "{\"error\":\"no such model\"}".into()));
        let e = pull_model(&f, &host(), "m:1", &mut |_| {}).unwrap_err();
        assert!(e.to_string().contains("no such model"), "{e}");
    }

    #[test]
    fn version_transport_error_is_not_running() {
        let f = Fake::new();
        assert_eq!(ollama_version(&f, &host()).unwrap(), None);
        assert_eq!(ollama_answer(&f, &host()).unwrap(), Err("refused".into()));
        let mut f = Fake::new();
        f.get = Ok((200, r#"{"version":"0.40.10"}"#.into()));
        assert_eq!(
            ollama_version(&f, &host()).unwrap().as_deref(),
            Some("0.40.10")
        );
        f.get = Ok((500, "".into()));
        assert!(ollama_version(&f, &host()).is_err());
        f.get = Ok((200, "junk".into()));
        assert!(ollama_version(&f, &host()).is_err());
    }

    #[test]
    fn installed_models_reads_tags() {
        let mut f = Fake::new();
        f.get = Ok((200, r#"{"models":[{"model":"gpt-oss:20b"}]}"#.into()));
        assert_eq!(installed_models(&f, &host()).unwrap(), vec!["gpt-oss:20b"]);
    }

    #[test]
    fn copy_non_200_fails() {
        let mut f = Fake::new();
        f.post = Some((404, r#"{"error":"model not found"}"#.into()));
        assert!(copy_model(&f, &host(), "a", "b").is_err());
        f.post = Some((200, String::new()));
        copy_model(&f, &host(), "a", "b").unwrap();
    }
}
