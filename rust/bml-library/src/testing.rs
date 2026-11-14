//! Test helpers: an in-memory [`HttpClient`] serving fixed answers.

use std::collections::BTreeMap;
use std::sync::{Arc, Mutex};

use bmlib::publications::fetchers::{FetchError, HttpClient, HttpResponse};

/// Routed URL → (status, body).
type Routes = BTreeMap<String, (u16, Vec<u8>)>;

/// An [`HttpClient`] answering each routed URL with a fixed status and body;
/// any other URL fails as if no answer came. Records every URL asked for.
#[derive(Default, Clone)]
pub struct FakeHttp {
    routes: Arc<Mutex<Routes>>,
    seen: Arc<Mutex<Vec<String>>>,
}

impl FakeHttp {
    /// A client with no routes.
    #[must_use]
    pub fn new() -> Self {
        FakeHttp::default()
    }

    /// Answer `url` with `status` and `body` (replacing an earlier route).
    #[must_use]
    pub fn route(self, url: &str, status: u16, body: impl Into<Vec<u8>>) -> Self {
        self.set(url, status, body);
        self
    }

    /// [`FakeHttp::route`] on a shared client.
    pub fn set(&self, url: &str, status: u16, body: impl Into<Vec<u8>>) {
        self.routes
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .insert(url.to_string(), (status, body.into()));
    }

    /// Every URL asked for, in order.
    #[must_use]
    pub fn seen(&self) -> Arc<Mutex<Vec<String>>> {
        self.seen.clone()
    }
}

impl HttpClient for FakeHttp {
    fn get(&self, url: &str) -> Result<HttpResponse, FetchError> {
        self.seen
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .push(url.to_string());
        match self
            .routes
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .get(url)
        {
            Some((status, body)) => Ok(HttpResponse::from_bytes(*status, body.clone())),
            None => Err(FetchError::Transport(format!("timed out (GET {url})"))),
        }
    }
}
