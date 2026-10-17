"""
Tests for retrying recoverable failures with exponential backoff.

A network timeout or a dropped connection may succeed on a later attempt; a
bug or a bad response will not. ``call_with_backoff`` retries only the first
kind and waits exponentially longer between attempts. Sleeping is injected,
so no test waits.
"""

from typing import List

import psycopg
import pytest

from bmlibrarian.utils.transient_retry import (
    call_with_backoff,
    is_transient_error,
)


class _Flaky:
    """An operation that raises the given errors in turn, then returns 'ok'."""

    def __init__(self, *errors: BaseException) -> None:
        """Remember the errors to raise, one per call."""
        self.errors = list(errors)
        self.calls = 0

    def __call__(self) -> str:
        """Raise the next error, or return 'ok' once they are used up."""
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return "ok"


def _no_sleep(delays: List[float]):
    """A sleep function that records the requested delays instead of waiting."""
    return delays.append


@pytest.mark.parametrize("error", [
    ConnectionError("refused"),
    ConnectionRefusedError("refused"),
    TimeoutError("timed out"),
    psycopg.OperationalError("server closed the connection unexpectedly"),
])
def test_network_and_database_outages_are_transient(error: BaseException) -> None:
    """Errors a later attempt can get past are recoverable."""
    assert is_transient_error(error)


@pytest.mark.parametrize("error", [
    ValueError("bad response"),
    KeyError("score"),
    TypeError("bug"),
    RuntimeError("bug"),
    psycopg.ProgrammingError("syntax error"),
    FileNotFoundError("missing"),
])
def test_bugs_and_bad_data_are_not_transient(error: BaseException) -> None:
    """Retrying cannot fix a bug or an invalid response."""
    assert not is_transient_error(error)


def test_a_wrapped_outage_is_transient() -> None:
    """An error raised ``from`` a timeout is recoverable too."""
    try:
        try:
            raise TimeoutError("read timed out")
        except TimeoutError as cause:
            raise RuntimeError("search failed") from cause
    except RuntimeError as wrapped:
        assert is_transient_error(wrapped)


def test_an_error_merely_raised_while_handling_an_outage_is_not_transient() -> None:
    """Only an explicit cause counts; a bug in an except block is still a bug."""
    try:
        try:
            raise TimeoutError("read timed out")
        except TimeoutError:
            raise KeyError("bug in handler")
    except KeyError as error:
        assert not is_transient_error(error)


def test_a_recoverable_failure_is_retried_until_it_succeeds() -> None:
    """Two timeouts, then success: three calls and the result is returned."""
    operation = _Flaky(TimeoutError("t1"), TimeoutError("t2"))
    delays: List[float] = []

    result = call_with_backoff(
        operation, description="test op", max_attempts=3, base_delay=1.0,
        max_delay=60.0, sleep=_no_sleep(delays),
    )

    assert result == "ok"
    assert operation.calls == 3
    assert len(delays) == 2


def test_backoff_delays_grow_exponentially() -> None:
    """Each wait is at least twice the previous one's un-jittered base."""
    operation = _Flaky(*(ConnectionError("down") for _ in range(4)))
    delays: List[float] = []

    call_with_backoff(
        operation, description="test op", max_attempts=5, base_delay=1.0,
        max_delay=60.0, sleep=_no_sleep(delays),
    )

    # backoff_delay adds up to 25% jitter to 1, 2, 4, 8 seconds.
    for attempt, delay in enumerate(delays):
        assert 2 ** attempt <= delay <= 2 ** attempt * 1.25


def test_backoff_delay_is_capped() -> None:
    """No wait exceeds the cap (plus its jitter)."""
    operation = _Flaky(*(ConnectionError("down") for _ in range(5)))
    delays: List[float] = []

    call_with_backoff(
        operation, description="test op", max_attempts=6, base_delay=1.0,
        max_delay=3.0, sleep=_no_sleep(delays),
    )

    assert max(delays) <= 3.0 * 1.25


def test_the_last_error_is_raised_when_attempts_run_out() -> None:
    """A failure that persists is not swallowed."""
    operation = _Flaky(*(TimeoutError(f"t{i}") for i in range(3)))
    delays: List[float] = []

    with pytest.raises(TimeoutError, match="t2"):
        call_with_backoff(
            operation, description="test op", max_attempts=3, base_delay=1.0,
            max_delay=60.0, sleep=_no_sleep(delays),
        )

    assert operation.calls == 3
    assert len(delays) == 2  # no wait after the final attempt


def test_a_non_recoverable_error_is_raised_at_once() -> None:
    """A bug is not retried."""
    operation = _Flaky(ValueError("bad"))
    delays: List[float] = []

    with pytest.raises(ValueError):
        call_with_backoff(
            operation, description="test op", max_attempts=3, base_delay=1.0,
            max_delay=60.0, sleep=_no_sleep(delays),
        )

    assert operation.calls == 1
    assert delays == []


def test_a_single_attempt_never_waits() -> None:
    """max_attempts=1 turns retrying off."""
    operation = _Flaky(TimeoutError("t"))
    delays: List[float] = []

    with pytest.raises(TimeoutError):
        call_with_backoff(
            operation, description="test op", max_attempts=1, sleep=_no_sleep(delays),
        )

    assert delays == []


@pytest.mark.parametrize("kwargs", [
    {"max_attempts": 0},
    {"max_attempts": True},
    {"max_attempts": 1.5},
    {"base_delay": -1.0},
    {"max_delay": -1.0},
])
def test_invalid_settings_are_rejected(kwargs: dict) -> None:
    """Retry settings come from config files and are checked."""
    with pytest.raises((TypeError, ValueError)):
        call_with_backoff(lambda: "ok", description="test op", **kwargs)
