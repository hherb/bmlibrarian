"""Tests for bmlibrarian.utils.rate_limit (per-host pacing + 429 handling)."""

import io
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from unittest.mock import patch

import pytest
import requests

from bmlibrarian.utils import rate_limit
from bmlibrarian.utils.rate_limit import (
    HostRateLimiter,
    RateLimitedSession,
    backoff_delay,
    get_shared_rate_limiter,
    host_key,
    parse_retry_after,
    throttle_delay,
)


class FakeClock:
    """Monotonic clock whose sleep advances time instead of blocking."""

    def __init__(self) -> None:
        """Start at t=0 with no sleeps recorded."""
        self.now = 0.0
        self.sleeps: List[float] = []

    def clock(self) -> float:
        """Return the current fake time."""
        return self.now

    def sleep(self, seconds: float) -> None:
        """Record the sleep and advance the clock."""
        self.sleeps.append(seconds)
        self.now += seconds


def make_response(status: int, retry_after: Optional[str] = None) -> requests.Response:
    """Build a bare requests.Response with a status and optional Retry-After."""
    response = requests.Response()
    response.status_code = status
    response.raw = io.BytesIO(b"")
    if retry_after is not None:
        response.headers["Retry-After"] = retry_after
    return response


# --- pure helpers ---------------------------------------------------------


class TestHostKey:
    """host_key() normalises URLs to a lower-case hostname."""

    def test_lowercases_host(self) -> None:
        """Hostnames are case-insensitive."""
        assert host_key("https://API.Unpaywall.org/v2/x") == "api.unpaywall.org"

    def test_ftp_url(self) -> None:
        """FTP URLs are keyed by host too."""
        assert host_key("ftp://ftp.ncbi.nlm.nih.gov/pub/x.tar.gz") == "ftp.ncbi.nlm.nih.gov"

    def test_no_host(self) -> None:
        """A URL without a host maps to the unknown-host key."""
        assert host_key("not a url") == rate_limit.UNKNOWN_HOST_KEY


class TestParseRetryAfter:
    """parse_retry_after() handles both RFC 9110 forms and junk."""

    def test_delay_seconds(self) -> None:
        """Integer seconds are returned as float."""
        assert parse_retry_after("120") == 120.0

    def test_negative_clamped(self) -> None:
        """Negative delays never mean 'wait less than zero'."""
        assert parse_retry_after("-5") == 0.0

    def test_http_date(self) -> None:
        """HTTP-dates are converted relative to 'now'."""
        now = datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)
        header = "Fri, 16 Oct 2026 12:00:30 GMT"
        assert parse_retry_after(header, now=now) == pytest.approx(30.0)

    def test_http_date_in_past(self) -> None:
        """A date already passed means no wait."""
        now = datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)
        past = now - timedelta(minutes=5)
        header = past.strftime("%a, %d %b %Y %H:%M:%S GMT")
        assert parse_retry_after(header, now=now) == 0.0

    @pytest.mark.parametrize("value", [None, "", "   ", "soon", "nan", "inf"])
    def test_unparseable(self, value: Optional[str]) -> None:
        """Missing or malformed headers yield None, not an exception."""
        assert parse_retry_after(value) is None


class TestBackoffDelay:
    """backoff_delay() is exponential, capped and jittered."""

    def test_exponential_without_jitter(self) -> None:
        """Delay doubles per attempt."""
        assert [backoff_delay(a, base=1.0, cap=100.0, random_value=0.0) for a in range(4)] == [
            1.0, 2.0, 4.0, 8.0
        ]

    def test_cap(self) -> None:
        """Un-jittered delay never exceeds the cap."""
        assert backoff_delay(20, base=1.0, cap=5.0, random_value=0.0) == 5.0

    def test_jitter_bounds(self) -> None:
        """Jitter adds at most jitter_factor of the delay."""
        assert backoff_delay(0, base=2.0, jitter_factor=0.25, random_value=0.999) < 2.5
        assert backoff_delay(0, base=2.0, jitter_factor=0.25, random_value=0.0) == 2.0


class TestThrottleDelay:
    """throttle_delay() identifies throttling responses."""

    def test_ok_response(self) -> None:
        """Successful responses are not throttled."""
        assert throttle_delay(make_response(200), 0) is None

    def test_429_with_retry_after(self) -> None:
        """Retry-After wins over backoff."""
        assert throttle_delay(make_response(429, "7"), 0) == 7.0

    def test_429_without_retry_after_uses_backoff(self) -> None:
        """Without Retry-After a positive backoff delay is used."""
        assert throttle_delay(make_response(429), 0) >= rate_limit.DEFAULT_BACKOFF_BASE_SECONDS

    def test_503_only_with_retry_after(self) -> None:
        """A bare 503 is a server error, not throttling."""
        assert throttle_delay(make_response(503), 0) is None
        assert throttle_delay(make_response(503, "3"), 0) == 3.0


# --- HostRateLimiter --------------------------------------------------------


class TestHostRateLimiter:
    """Per-host minimum-interval pacing."""

    def make(self, default: float = 1.0, **hosts: float) -> "tuple[HostRateLimiter, FakeClock]":
        """Build a limiter on a fake clock."""
        fake = FakeClock()
        limiter = HostRateLimiter(
            default_interval=default,
            host_intervals={h.replace("_", "."): v for h, v in hosts.items()},
            clock=fake.clock,
            sleep=fake.sleep,
        )
        return limiter, fake

    def test_first_request_is_immediate(self) -> None:
        """No wait before the first request to a host."""
        limiter, fake = self.make()
        assert limiter.acquire("https://a.example/x") == 0.0
        assert fake.sleeps == []

    def test_same_host_is_spaced(self) -> None:
        """Back-to-back requests to one host wait the interval."""
        limiter, fake = self.make(default=1.0)
        limiter.acquire("https://a.example/1")
        assert limiter.acquire("https://a.example/2") == pytest.approx(1.0)

    def test_different_hosts_independent(self) -> None:
        """Pacing is per host."""
        limiter, fake = self.make(default=1.0)
        limiter.acquire("https://a.example/1")
        assert limiter.acquire("https://b.example/1") == 0.0

    def test_host_specific_interval(self) -> None:
        """Configured host intervals override the default."""
        limiter, _ = self.make(default=5.0, fast_example=0.25)
        limiter.acquire("https://fast.example/1")
        assert limiter.acquire("https://fast.example/2") == pytest.approx(0.25)

    def test_elapsed_time_counts(self) -> None:
        """Time already passed reduces the wait."""
        limiter, fake = self.make(default=1.0)
        limiter.acquire("https://a.example/1")
        fake.now += 0.6
        assert limiter.acquire("https://a.example/2") == pytest.approx(0.4)

    def test_defer_pushes_host_back(self) -> None:
        """defer() makes every caller wait for that host."""
        limiter, fake = self.make(default=1.0)
        limiter.acquire("https://a.example/1")
        limiter.defer("https://a.example/anything", 30.0)
        assert limiter.acquire("https://a.example/2") == pytest.approx(30.0)

    def test_defer_never_shortens(self) -> None:
        """A shorter defer can't pull an existing reservation forward."""
        limiter, _ = self.make(default=10.0)
        limiter.acquire("https://a.example/1")
        limiter.defer("https://a.example/1", 1.0)
        assert limiter.acquire("https://a.example/2") == pytest.approx(10.0)

    def test_negative_default_rejected(self) -> None:
        """A negative interval is a configuration error."""
        with pytest.raises(ValueError):
            HostRateLimiter(default_interval=-1.0)

    def test_default_host_table_used(self) -> None:
        """Without overrides the documented API limits apply."""
        limiter = HostRateLimiter()
        assert limiter.interval_for("eutils.ncbi.nlm.nih.gov") == rate_limit.NCBI_MIN_INTERVAL_SECONDS
        assert limiter.interval_for("unknown.example") == rate_limit.DEFAULT_MIN_INTERVAL_SECONDS


def test_shared_limiter_is_singleton() -> None:
    """All default sessions share one limiter, so pacing spans instances."""
    assert get_shared_rate_limiter() is get_shared_rate_limiter()
    assert RateLimitedSession().rate_limiter is get_shared_rate_limiter()


# --- RateLimitedSession -----------------------------------------------------


class TestRateLimitedSession:
    """Pacing and throttling retries inside the session."""

    def make_session(self, max_retries: int = 3, max_retry_after: float = 60.0
                     ) -> "tuple[RateLimitedSession, FakeClock]":
        """Session on a zero-interval fake-clock limiter."""
        fake = FakeClock()
        limiter = HostRateLimiter(default_interval=0.0, host_intervals={},
                                  clock=fake.clock, sleep=fake.sleep)
        return RateLimitedSession(limiter, max_retries=max_retries,
                                  max_retry_after=max_retry_after), fake

    def test_success_passes_through(self) -> None:
        """A 200 is returned after one call."""
        session, fake = self.make_session()
        with patch.object(requests.Session, "request", return_value=make_response(200)) as req:
            assert session.get("https://a.example/x").status_code == 200
        assert req.call_count == 1
        assert fake.sleeps == []

    def test_429_retried_after_retry_after(self) -> None:
        """A 429 sleeps for Retry-After, then retries and succeeds."""
        session, fake = self.make_session()
        responses = [make_response(429, "5"), make_response(200)]
        with patch.object(requests.Session, "request", side_effect=responses) as req:
            assert session.get("https://a.example/x").status_code == 200
        assert req.call_count == 2
        assert fake.sleeps == [pytest.approx(5.0)]

    def test_gives_up_after_max_retries(self) -> None:
        """Persistent 429s are returned to the caller after max_retries."""
        session, _ = self.make_session(max_retries=2)
        with patch.object(requests.Session, "request",
                          side_effect=lambda *a, **k: make_response(429, "1")) as req:
            assert session.get("https://a.example/x").status_code == 429
        assert req.call_count == 3  # first try + 2 retries

    def test_long_retry_after_not_slept(self) -> None:
        """A Retry-After beyond the cap returns immediately and defers the host."""
        session, fake = self.make_session(max_retry_after=10.0)
        with patch.object(requests.Session, "request",
                          return_value=make_response(429, "3600")) as req:
            assert session.get("https://a.example/x").status_code == 429
        assert req.call_count == 1
        assert fake.sleeps == []
        # Host is deferred by the capped amount for the next caller
        assert session.rate_limiter.acquire("https://a.example/y") == pytest.approx(10.0)

    def test_plain_503_not_retried(self) -> None:
        """A 503 without Retry-After is left to the caller's error handling."""
        session, _ = self.make_session()
        with patch.object(requests.Session, "request", return_value=make_response(503)) as req:
            assert session.get("https://a.example/x").status_code == 503
        assert req.call_count == 1
