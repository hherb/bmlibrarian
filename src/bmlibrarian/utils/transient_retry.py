"""
Retry recoverable failures with exponential backoff.

A network timeout, a dropped database connection or an LLM server that is
restarting may succeed on a later attempt; a bug or an invalid response will
not. ``is_transient_error`` tells the two apart, and ``call_with_backoff``
retries only the first kind, waiting exponentially longer between attempts
(``backoff_delay`` from ``rate_limit``, with jitter and a cap).

Both functions are pure apart from the wait between attempts, which goes
through ``_sleep`` unless a ``sleep`` function is passed (the test suite
replaces ``_sleep`` so retries never wait).
"""

import logging
import time
from typing import Callable, Optional, Tuple, Type, TypeVar

import psycopg

from .rate_limit import backoff_delay

logger = logging.getLogger(__name__)

_T = TypeVar("_T")

# Attempts in total (not retries) when a caller passes no setting.
DEFAULT_TRANSIENT_ATTEMPTS = 3
# Wait before the first retry, and the longest un-jittered wait, in seconds.
DEFAULT_TRANSIENT_BASE_SECONDS = 2.0
DEFAULT_TRANSIENT_CAP_SECONDS = 30.0
# How many explicit causes (``raise ... from``) are followed when deciding
# whether a wrapped error is transient.
MAX_CAUSE_DEPTH = 10


def _transient_types() -> Tuple[Type[BaseException], ...]:
    """
    Collect the exception types that signal a recoverable outage.

    Builtin ``ConnectionError`` (raised by the LLM layer when every provider
    failed) and ``TimeoutError``, psycopg's ``OperationalError`` (connection
    lost, server shutting down, statement timeout) and, when installed, the
    transport errors of ``requests`` and ``httpx`` (used by the Ollama client).

    Returns:
        The exception types.
    """
    types: list[Type[BaseException]] = [ConnectionError, TimeoutError, psycopg.OperationalError]
    try:
        import requests

        types += [requests.exceptions.ConnectionError, requests.exceptions.Timeout]
    except ImportError:
        pass
    try:
        import httpx

        types.append(httpx.TransportError)
    except ImportError:
        pass
    return tuple(types)


TRANSIENT_ERROR_TYPES: Tuple[Type[BaseException], ...] = _transient_types()


def _sleep(seconds: float) -> None:
    """
    Wait between attempts (the default ``sleep`` of ``call_with_backoff``).

    Args:
        seconds: How long to wait.
    """
    time.sleep(seconds)


def is_transient_error(error: BaseException) -> bool:
    """
    Whether ``error`` is an outage that a later attempt may get past.

    The error itself and its explicit causes (``raise X from cause``) are
    checked. An error merely raised while another was being handled
    (``__context__``) is not treated as transient: a bug in an ``except``
    block is still a bug.

    Args:
        error: The exception raised by the operation.

    Returns:
        True for network/database/LLM-connection outages and timeouts.
    """
    current: Optional[BaseException] = error
    for _ in range(MAX_CAUSE_DEPTH):
        if current is None:
            return False
        if isinstance(current, TRANSIENT_ERROR_TYPES):
            return True
        current = current.__cause__
    return False


def _check_settings(max_attempts: int, base_delay: float, max_delay: float) -> None:
    """
    Validate retry settings (they come from config files).

    Args:
        max_attempts: Attempts in total.
        base_delay: Wait before the first retry, in seconds.
        max_delay: Longest un-jittered wait, in seconds.

    Raises:
        TypeError: If ``max_attempts`` is not an int or a delay is not a number.
        ValueError: If ``max_attempts < 1`` or a delay is negative.
    """
    if not isinstance(max_attempts, int) or isinstance(max_attempts, bool):
        raise TypeError(f"max_attempts must be an int, got {type(max_attempts).__name__}")
    if max_attempts < 1:
        raise ValueError(f"max_attempts must be >= 1, got {max_attempts}")
    for name, value in (("base_delay", base_delay), ("max_delay", max_delay)):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise TypeError(f"{name} must be a number, got {type(value).__name__}")
        if value < 0:
            raise ValueError(f"{name} must be >= 0, got {value}")


def call_with_backoff(
    operation: Callable[[], _T],
    *,
    description: str,
    max_attempts: int = DEFAULT_TRANSIENT_ATTEMPTS,
    base_delay: float = DEFAULT_TRANSIENT_BASE_SECONDS,
    max_delay: float = DEFAULT_TRANSIENT_CAP_SECONDS,
    is_retryable: Callable[[BaseException], bool] = is_transient_error,
    sleep: Optional[Callable[[float], None]] = None,
) -> _T:
    """
    Run ``operation``, retrying recoverable failures with exponential backoff.

    Args:
        operation: The call to make; it must be safe to repeat.
        description: What the operation is, for log messages.
        max_attempts: Attempts in total; 1 turns retrying off.
        base_delay: Wait before the first retry, in seconds; doubled for each
            further retry.
        max_delay: Longest un-jittered wait, in seconds.
        is_retryable: Decides whether an error is worth another attempt.
        sleep: Waits the given number of seconds; ``None`` uses ``_sleep``.

    Returns:
        What ``operation`` returned.

    Raises:
        TypeError, ValueError: If the settings are invalid.
        BaseException: The error of the final attempt, or a non-recoverable
            error at once.
    """
    _check_settings(max_attempts, base_delay, max_delay)
    wait = _sleep if sleep is None else sleep
    for attempt in range(1, max_attempts + 1):
        try:
            return operation()
        except Exception as error:
            if attempt == max_attempts or not is_retryable(error):
                if attempt > 1:
                    logger.error(f"{description} failed after {attempt} attempts: {error}")
                raise
            delay = backoff_delay(attempt - 1, base=base_delay, cap=max_delay)
            logger.warning(
                f"{description} failed (attempt {attempt}/{max_attempts}): {error}; "
                f"retrying in {delay:.1f}s"
            )
            wait(delay)
    raise AssertionError("unreachable: the loop returns or raises")
