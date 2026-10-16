"""Per-host HTTP rate limiting with 429 / Retry-After handling.

PDF discovery fans out to several external services per document (NCBI,
Unpaywall, CrossRef, doi.org, publisher hosts). Without pacing, a batch run
fires these back-to-back and gets throttled or blocked. This module provides:

- Pure helpers: :func:`host_key`, :func:`parse_retry_after`,
  :func:`backoff_delay`.
- :class:`HostRateLimiter`: a thread-safe limiter that enforces a minimum
  interval between requests to the same host and lets callers push a host's
  next slot back (e.g. after a ``Retry-After``).
- :class:`RateLimitedSession`: a ``requests.Session`` that paces every request
  through a limiter and retries ``429`` (and ``503`` carrying ``Retry-After``)
  responses, honouring the server-provided delay.
- :func:`get_shared_rate_limiter`: the process-wide limiter, so pacing holds
  across all resolver/finder instances (they are created per document in
  several call sites).

Only the host of the initial request URL is paced; redirect hops followed
internally by ``requests`` are not.
"""

from __future__ import annotations

import email.utils
import logging
import random
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Mapping, Optional
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

# Minimum seconds between requests to a host with no specific entry below.
DEFAULT_MIN_INTERVAL_SECONDS = 1.0

# NCBI allows 3 requests/second without an API key.
NCBI_MIN_INTERVAL_SECONDS = 0.34
# Unpaywall asks for at most ~10 requests/second.
UNPAYWALL_MIN_INTERVAL_SECONDS = 0.1
# CrossRef's public pool is limited to ~5 requests/second.
CROSSREF_MIN_INTERVAL_SECONDS = 0.2
DOI_ORG_MIN_INTERVAL_SECONDS = 0.2

# Per-host minimum intervals (seconds), keyed by lower-case hostname.
DEFAULT_HOST_INTERVALS: Dict[str, float] = {
    "eutils.ncbi.nlm.nih.gov": NCBI_MIN_INTERVAL_SECONDS,
    "www.ncbi.nlm.nih.gov": NCBI_MIN_INTERVAL_SECONDS,
    "pmc.ncbi.nlm.nih.gov": NCBI_MIN_INTERVAL_SECONDS,
    "ftp.ncbi.nlm.nih.gov": NCBI_MIN_INTERVAL_SECONDS,
    "api.unpaywall.org": UNPAYWALL_MIN_INTERVAL_SECONDS,
    "api.crossref.org": CROSSREF_MIN_INTERVAL_SECONDS,
    "doi.org": DOI_ORG_MIN_INTERVAL_SECONDS,
}

# HTTP status codes that signal throttling.
HTTP_TOO_MANY_REQUESTS = 429
HTTP_SERVICE_UNAVAILABLE = 503

# How many times a throttled request is retried before the throttled
# response is handed back to the caller.
DEFAULT_MAX_RATE_LIMIT_RETRIES = 3
# Longest Retry-After we are willing to sleep for inside one request. Longer
# waits are not slept; the response is returned and the host is deferred.
DEFAULT_MAX_RETRY_AFTER_SECONDS = 60.0
# Exponential backoff used when a 429 carries no usable Retry-After.
DEFAULT_BACKOFF_BASE_SECONDS = 2.0
DEFAULT_BACKOFF_CAP_SECONDS = 30.0
DEFAULT_JITTER_FACTOR = 0.25

# Key used when a URL has no parseable hostname.
UNKNOWN_HOST_KEY = ""


def host_key(url: str) -> str:
    """Return the lower-case hostname of ``url`` for rate-limit bookkeeping.

    Args:
        url: Any URL (http, https, ftp, ...).

    Returns:
        The hostname in lower case, or :data:`UNKNOWN_HOST_KEY` if the URL
        has none or cannot be parsed.
    """
    try:
        return (urlparse(url).hostname or UNKNOWN_HOST_KEY).lower()
    except (ValueError, AttributeError):
        return UNKNOWN_HOST_KEY


def parse_retry_after(
    value: Optional[str],
    now: Optional[datetime] = None,
) -> Optional[float]:
    """Parse an HTTP ``Retry-After`` header into seconds to wait.

    Accepts both forms defined by RFC 9110: delay-seconds (``"120"``) and an
    HTTP-date (``"Wed, 21 Oct 2026 07:28:00 GMT"``).

    Args:
        value: Raw header value (may be None or malformed).
        now: Current time for HTTP-date arithmetic; defaults to UTC now.

    Returns:
        Non-negative seconds to wait, or None if the header is absent or
        unparseable.
    """
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None

    try:
        seconds = float(text)
    except ValueError:
        pass
    else:
        if seconds != seconds or seconds in (float("inf"), float("-inf")):
            return None  # NaN / infinity
        return max(0.0, seconds)

    try:
        when = email.utils.parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    reference = now or datetime.now(timezone.utc)
    return max(0.0, (when - reference).total_seconds())


def backoff_delay(
    attempt: int,
    base: float = DEFAULT_BACKOFF_BASE_SECONDS,
    cap: float = DEFAULT_BACKOFF_CAP_SECONDS,
    jitter_factor: float = DEFAULT_JITTER_FACTOR,
    random_value: Optional[float] = None,
) -> float:
    """Exponential backoff delay with proportional jitter.

    Args:
        attempt: Zero-based retry number (0 = first retry).
        base: Delay for the first retry, in seconds.
        cap: Upper bound for the un-jittered delay, in seconds.
        jitter_factor: Fraction of the delay added as random jitter.
        random_value: Value in [0, 1) used for jitter; drawn from
            :func:`random.random` when None (inject for deterministic tests).

    Returns:
        Seconds to wait before the retry.
    """
    delay = min(cap, base * (2 ** max(0, attempt)))
    rnd = random.random() if random_value is None else random_value
    return delay + delay * jitter_factor * rnd


class HostRateLimiter:
    """Thread-safe per-host minimum-interval rate limiter.

    Each call to :meth:`acquire` reserves the next free slot for the URL's
    host and sleeps until it arrives. Slots are reserved under a lock but the
    sleep happens outside it, so threads waiting on different hosts never
    block each other.
    """

    def __init__(
        self,
        default_interval: float = DEFAULT_MIN_INTERVAL_SECONDS,
        host_intervals: Optional[Mapping[str, float]] = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Initialize the limiter.

        Args:
            default_interval: Minimum seconds between requests to a host not
                listed in ``host_intervals``.
            host_intervals: Per-host minimum intervals (lower-case hostnames).
                Defaults to :data:`DEFAULT_HOST_INTERVALS`.
            clock: Monotonic clock (injectable for tests).
            sleep: Sleep function (injectable for tests).
        """
        if default_interval < 0:
            raise ValueError("default_interval must be >= 0")
        self.default_interval = default_interval
        intervals = DEFAULT_HOST_INTERVALS if host_intervals is None else host_intervals
        self.host_intervals: Dict[str, float] = {
            host.lower(): max(0.0, float(interval))
            for host, interval in intervals.items()
        }
        self._clock = clock
        self._sleep = sleep
        self._next_allowed: Dict[str, float] = {}
        self._lock = threading.Lock()

    def interval_for(self, host: str) -> float:
        """Return the minimum interval configured for ``host``.

        Args:
            host: Lower-case hostname.

        Returns:
            Minimum seconds between requests to that host.
        """
        return self.host_intervals.get(host, self.default_interval)

    def acquire(self, url: str) -> float:
        """Block until a request to ``url``'s host may be sent.

        Args:
            url: URL about to be requested.

        Returns:
            Seconds actually waited (0.0 if no wait was needed).
        """
        host = host_key(url)
        with self._lock:
            now = self._clock()
            slot = max(now, self._next_allowed.get(host, now))
            self._next_allowed[host] = slot + self.interval_for(host)
        wait = slot - now
        if wait > 0:
            logger.debug("Rate limit: waiting %.2fs before request to %s", wait, host)
            self._sleep(wait)
            return wait
        return 0.0

    def defer(self, url: str, seconds: float) -> None:
        """Push the next allowed request to ``url``'s host at least ``seconds`` out.

        Used after a throttling response so that *all* callers sharing this
        limiter back off from that host, not only the one that was throttled.

        Args:
            url: URL whose host should be deferred.
            seconds: Minimum seconds from now before the next request.
        """
        host = host_key(url)
        with self._lock:
            until = self._clock() + max(0.0, seconds)
            if until > self._next_allowed.get(host, float("-inf")):
                self._next_allowed[host] = until


class RateLimitedSession(requests.Session):
    """``requests.Session`` that paces requests and retries throttled ones.

    Every request first waits for its host's slot on the limiter. A ``429``
    response (or a ``503`` carrying ``Retry-After``) defers the host on the
    shared limiter and is retried up to ``max_retries`` times. When retries
    run out, or the server asks for a wait longer than ``max_retry_after``,
    the throttled response is returned unchanged so the caller's normal
    error handling (``raise_for_status`` / status checks) reports it.
    """

    def __init__(
        self,
        rate_limiter: Optional[HostRateLimiter] = None,
        max_retries: int = DEFAULT_MAX_RATE_LIMIT_RETRIES,
        max_retry_after: float = DEFAULT_MAX_RETRY_AFTER_SECONDS,
    ) -> None:
        """Initialize the session.

        Args:
            rate_limiter: Limiter to pace requests with; defaults to the
                process-wide :func:`get_shared_rate_limiter`.
            max_retries: Retries for a throttled request before giving up.
            max_retry_after: Longest server-requested wait (seconds) that is
                slept inside a single request.
        """
        super().__init__()
        self.rate_limiter = rate_limiter or get_shared_rate_limiter()
        self.max_retries = max(0, max_retries)
        self.max_retry_after = max(0.0, max_retry_after)

    def request(  # type: ignore[override]
        self, method: str, url: str, *args: Any, **kwargs: Any
    ) -> requests.Response:
        """Send a paced request, retrying throttled responses.

        Args:
            method: HTTP method.
            url: Request URL.
            *args: Positional arguments forwarded to ``requests.Session.request``.
            **kwargs: Keyword arguments forwarded to ``requests.Session.request``.

        Returns:
            The final response (possibly still a throttling response).
        """
        attempt = 0
        while True:
            self.rate_limiter.acquire(url)
            response = super().request(method, url, *args, **kwargs)
            delay = throttle_delay(response, attempt)
            if delay is None:
                return response

            host = host_key(url)
            if attempt >= self.max_retries or delay > self.max_retry_after:
                self.rate_limiter.defer(url, min(delay, self.max_retry_after))
                logger.warning(
                    "Throttled by %s (HTTP %s); giving up after %d retr%s "
                    "(server asked to wait %.1fs)",
                    host, response.status_code, attempt,
                    "y" if attempt == 1 else "ies", delay,
                )
                return response

            logger.info(
                "Throttled by %s (HTTP %s); retrying in %.1fs (retry %d/%d)",
                host, response.status_code, delay, attempt + 1, self.max_retries,
            )
            response.close()
            self.rate_limiter.defer(url, delay)
            attempt += 1


def throttle_delay(response: requests.Response, attempt: int) -> Optional[float]:
    """Return how long to wait before retrying a throttled response.

    Args:
        response: HTTP response to inspect.
        attempt: Zero-based retry number, used for backoff when the server
            gave no usable ``Retry-After``.

    Returns:
        Seconds to wait, or None if the response is not a throttling
        response (only ``429``, or ``503`` with a ``Retry-After``, are).
    """
    retry_after = parse_retry_after(response.headers.get("Retry-After"))
    if response.status_code == HTTP_TOO_MANY_REQUESTS:
        return retry_after if retry_after is not None else backoff_delay(attempt)
    if response.status_code == HTTP_SERVICE_UNAVAILABLE and retry_after is not None:
        return retry_after
    return None


_shared_limiter: Optional[HostRateLimiter] = None
_shared_limiter_lock = threading.Lock()


def get_shared_rate_limiter() -> HostRateLimiter:
    """Return the process-wide :class:`HostRateLimiter`, creating it on first use.

    Returns:
        The shared limiter instance.
    """
    global _shared_limiter
    with _shared_limiter_lock:
        if _shared_limiter is None:
            _shared_limiter = HostRateLimiter()
        return _shared_limiter
