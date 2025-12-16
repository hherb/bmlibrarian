"""
Utility functions for BMLibrarian Lite.

Provides common utilities including:
- Retry logic with exponential backoff for network operations
- Performance metrics collection
- Timing utilities

Usage:
    from bmlibrarian_lite.utils import retry_with_backoff, MetricsCollector

    # Retry decorator
    @retry_with_backoff(max_retries=3)
    def fetch_data():
        return requests.get(url)

    # Metrics collection
    metrics = MetricsCollector()
    with metrics.timer("operation"):
        do_something()
    print(metrics.get_statistics())
"""

import functools
import logging
import random
import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Generator, TypeVar

from .constants import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_BASE_DELAY,
    DEFAULT_RETRY_MAX_DELAY,
    DEFAULT_RETRY_JITTER_FACTOR,
)
from .exceptions import NetworkError, RetryExhaustedError

logger = logging.getLogger(__name__)

T = TypeVar("T")


# =============================================================================
# Retry Logic
# =============================================================================


def _calculate_delay_with_jitter(
    base_delay: float,
    attempt: int,
    exponential_base: float,
    max_delay: float,
    jitter_factor: float,
) -> float:
    """
    Calculate retry delay with exponential backoff and jitter.

    Jitter adds randomness to prevent thundering herd effects when
    multiple clients retry simultaneously after a failure.

    Args:
        base_delay: Initial delay in seconds
        attempt: Current attempt number (0-indexed)
        exponential_base: Multiplier for delay increase
        max_delay: Maximum delay cap
        jitter_factor: Amount of randomness (0.0 to 1.0)

    Returns:
        Calculated delay in seconds with jitter applied
    """
    # Calculate base exponential delay
    delay = min(base_delay * (exponential_base ** attempt), max_delay)

    # Apply jitter: delay * (1 - jitter_factor) to delay * (1 + jitter_factor)
    jitter_range = delay * jitter_factor
    jitter = random.uniform(-jitter_range, jitter_range)

    return max(0.0, delay + jitter)


def retry_with_backoff(
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_RETRY_BASE_DELAY,
    max_delay: float = DEFAULT_RETRY_MAX_DELAY,
    exponential_base: float = 2.0,
    jitter_factor: float = DEFAULT_RETRY_JITTER_FACTOR,
    retryable_exceptions: tuple[type[Exception], ...] = (
        ConnectionError,
        TimeoutError,
        OSError,
    ),
    on_retry: Callable[[int, Exception, float], None] | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator for retrying operations with exponential backoff and jitter.

    Automatically retries failed operations with increasing delays between
    attempts. Useful for network operations that may fail due to transient
    issues.

    Jitter is applied to prevent thundering herd effects when multiple
    clients retry simultaneously after a shared failure (e.g., server restart).

    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        base_delay: Initial delay in seconds (default: 1.0)
        max_delay: Maximum delay between retries (default: 10.0)
        exponential_base: Multiplier for delay increase (default: 2.0)
        jitter_factor: Amount of randomness to add to delays (default: 0.2)
                      Value of 0.2 means delay varies by +/- 20%
        retryable_exceptions: Tuple of exceptions that trigger retry
        on_retry: Optional callback called on each retry (attempt, error, delay)

    Returns:
        Decorated function with retry logic

    Raises:
        RetryExhaustedError: When all retry attempts fail

    Example:
        @retry_with_backoff(max_retries=3, base_delay=1.0)
        def fetch_pubmed_articles(pmids: list[str]) -> list[dict]:
            '''Fetch articles with automatic retry on network errors.'''
            return client.fetch_details(pmids)

        # Custom retry callback for logging
        def log_retry(attempt, error, delay):
            print(f"Attempt {attempt} failed: {error}, retrying in {delay}s")

        @retry_with_backoff(max_retries=5, on_retry=log_retry)
        def fetch_with_logging():
            ...

        # Disable jitter for deterministic behavior in tests
        @retry_with_backoff(jitter_factor=0.0)
        def fetch_deterministic():
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Exception | None = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e

                    if attempt < max_retries:
                        # Calculate delay with exponential backoff and jitter
                        delay = _calculate_delay_with_jitter(
                            base_delay=base_delay,
                            attempt=attempt,
                            exponential_base=exponential_base,
                            max_delay=max_delay,
                            jitter_factor=jitter_factor,
                        )

                        logger.warning(
                            f"{func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}), "
                            f"retrying in {delay:.1f}s: {e}"
                        )

                        # Call optional retry callback
                        if on_retry:
                            on_retry(attempt + 1, e, delay)

                        time.sleep(delay)
                    else:
                        logger.error(
                            f"{func.__name__} failed after {max_retries + 1} attempts: {e}"
                        )

            # All retries exhausted
            raise RetryExhaustedError(
                f"{func.__name__} failed after {max_retries + 1} attempts",
                attempts=max_retries + 1,
                last_error=last_exception,
            )

        return wrapper
    return decorator


def retry_async_with_backoff(
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_RETRY_BASE_DELAY,
    max_delay: float = DEFAULT_RETRY_MAX_DELAY,
    exponential_base: float = 2.0,
    jitter_factor: float = DEFAULT_RETRY_JITTER_FACTOR,
    retryable_exceptions: tuple[type[Exception], ...] = (
        ConnectionError,
        TimeoutError,
        OSError,
    ),
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Async version of retry_with_backoff decorator.

    Same functionality as retry_with_backoff but for async functions.
    Includes jitter to prevent thundering herd effects.

    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        base_delay: Initial delay in seconds (default: 1.0)
        max_delay: Maximum delay between retries (default: 10.0)
        exponential_base: Multiplier for delay increase (default: 2.0)
        jitter_factor: Amount of randomness to add to delays (default: 0.2)
        retryable_exceptions: Tuple of exceptions that trigger retry

    Example:
        @retry_async_with_backoff(max_retries=3)
        async def fetch_data():
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    return await response.json()
    """
    import asyncio

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Exception | None = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e

                    if attempt < max_retries:
                        # Calculate delay with exponential backoff and jitter
                        delay = _calculate_delay_with_jitter(
                            base_delay=base_delay,
                            attempt=attempt,
                            exponential_base=exponential_base,
                            max_delay=max_delay,
                            jitter_factor=jitter_factor,
                        )

                        logger.warning(
                            f"{func.__name__} failed (attempt {attempt + 1}), "
                            f"retrying in {delay:.1f}s: {e}"
                        )

                        await asyncio.sleep(delay)

            raise RetryExhaustedError(
                f"{func.__name__} failed after {max_retries + 1} attempts",
                attempts=max_retries + 1,
                last_error=last_exception,
            )

        return wrapper
    return decorator


# =============================================================================
# Performance Metrics
# =============================================================================


@dataclass
class TimingMetric:
    """Individual timing measurement."""

    name: str
    start_time: float
    end_time: float | None = None
    duration: float | None = None

    def stop(self) -> float:
        """Stop the timer and return duration."""
        self.end_time = time.perf_counter()
        self.duration = self.end_time - self.start_time
        return self.duration


@dataclass
class MetricStats:
    """Statistics for a collection of measurements."""

    count: int = 0
    total: float = 0.0
    min_value: float = float("inf")
    max_value: float = float("-inf")
    values: list[float] = field(default_factory=list)

    @property
    def mean(self) -> float:
        """Calculate mean value."""
        return self.total / self.count if self.count > 0 else 0.0

    @property
    def median(self) -> float:
        """Calculate median value."""
        if not self.values:
            return 0.0
        sorted_values = sorted(self.values)
        n = len(sorted_values)
        mid = n // 2
        if n % 2 == 0:
            return (sorted_values[mid - 1] + sorted_values[mid]) / 2
        return sorted_values[mid]

    def add(self, value: float) -> None:
        """Add a new measurement."""
        self.count += 1
        self.total += value
        self.min_value = min(self.min_value, value)
        self.max_value = max(self.max_value, value)
        self.values.append(value)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "count": self.count,
            "mean": round(self.mean, 4),
            "min": round(self.min_value, 4) if self.count > 0 else None,
            "max": round(self.max_value, 4) if self.count > 0 else None,
            "median": round(self.median, 4) if self.count > 0 else None,
            "total": round(self.total, 4),
        }


class MetricsCollector:
    """
    Thread-safe metrics collector for performance monitoring.

    Provides timing measurements, counters, and statistics for
    monitoring application performance. All operations are thread-safe,
    making it suitable for use in multi-threaded or concurrent applications.

    Thread Safety:
        All public methods are protected by a reentrant lock, ensuring
        safe access from multiple threads. The lock is reentrant to allow
        nested timer contexts without deadlocking.

    Usage:
        metrics = MetricsCollector()

        # Time an operation
        with metrics.timer("pubmed_search"):
            results = search_agent.search(question)

        # Record a count
        metrics.increment("documents_processed", len(documents))

        # Record a value
        metrics.record("relevance_score", 4.5)

        # Get statistics
        stats = metrics.get_statistics()
        print(stats["pubmed_search"])  # {'count': 1, 'mean': 2.3, ...}

    Example:
        # Real-world usage in a search workflow
        metrics = MetricsCollector()

        with metrics.timer("total_workflow"):
            with metrics.timer("query_conversion"):
                query = convert_query(question)

            with metrics.timer("pubmed_search"):
                results = search_pubmed(query)
            metrics.increment("documents_found", len(results))

            with metrics.timer("scoring"):
                for doc in results:
                    score = score_document(doc)
                    metrics.record("document_score", score)

        # Report
        print(metrics.summary())

    Thread-safe example:
        import threading

        metrics = MetricsCollector()

        def worker(worker_id: int):
            with metrics.timer(f"worker_{worker_id}"):
                # Do work
                metrics.increment("tasks_completed")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        print(metrics.get_counter("tasks_completed"))  # 10
    """

    def __init__(self) -> None:
        """Initialize the thread-safe metrics collector."""
        # Use RLock for reentrant locking (allows nested timer contexts)
        self._lock = threading.RLock()
        self._timers: dict[str, MetricStats] = defaultdict(MetricStats)
        self._counters: dict[str, int] = defaultdict(int)
        self._values: dict[str, MetricStats] = defaultdict(MetricStats)
        self._active_timers: dict[str, TimingMetric] = {}
        self._start_time = datetime.now()

    @contextmanager
    def timer(self, name: str) -> Generator[TimingMetric, None, None]:
        """
        Context manager for timing operations.

        Thread-safe: Uses internal locking for concurrent access.

        Args:
            name: Name of the operation being timed

        Yields:
            TimingMetric object (can be ignored)

        Example:
            with metrics.timer("embedding_generation"):
                embeddings = embed(texts)
        """
        metric = TimingMetric(name=name, start_time=time.perf_counter())

        with self._lock:
            self._active_timers[name] = metric

        try:
            yield metric
        finally:
            duration = metric.stop()
            with self._lock:
                self._timers[name].add(duration)
                if name in self._active_timers:
                    del self._active_timers[name]

            logger.debug(f"[METRICS] {name}: {duration:.3f}s")

    def start_timer(self, name: str) -> None:
        """
        Start a named timer manually.

        Thread-safe: Uses internal locking for concurrent access.
        Use stop_timer() to end the timing.

        Args:
            name: Name of the timer
        """
        with self._lock:
            self._active_timers[name] = TimingMetric(
                name=name,
                start_time=time.perf_counter()
            )

    def stop_timer(self, name: str) -> float:
        """
        Stop a named timer and record the duration.

        Thread-safe: Uses internal locking for concurrent access.

        Args:
            name: Name of the timer

        Returns:
            Duration in seconds

        Raises:
            KeyError: If timer was not started
        """
        with self._lock:
            if name not in self._active_timers:
                raise KeyError(f"Timer '{name}' was not started")

            metric = self._active_timers[name]
            duration = metric.stop()
            self._timers[name].add(duration)
            del self._active_timers[name]

        logger.debug(f"[METRICS] {name}: {duration:.3f}s")
        return duration

    def increment(self, name: str, value: int = 1) -> None:
        """
        Increment a counter.

        Thread-safe: Uses internal locking for concurrent access.

        Args:
            name: Counter name
            value: Amount to increment (default: 1)

        Example:
            metrics.increment("documents_processed")
            metrics.increment("api_calls", 3)
        """
        with self._lock:
            self._counters[name] += value
            current = self._counters[name]
        logger.debug(f"[METRICS] {name} += {value} (total: {current})")

    def decrement(self, name: str, value: int = 1) -> None:
        """
        Decrement a counter.

        Thread-safe: Uses internal locking for concurrent access.

        Args:
            name: Counter name
            value: Amount to decrement (default: 1)
        """
        with self._lock:
            self._counters[name] -= value

    def record(self, name: str, value: float) -> None:
        """
        Record a numerical value for statistics.

        Thread-safe: Uses internal locking for concurrent access.

        Args:
            name: Metric name
            value: Value to record

        Example:
            metrics.record("relevance_score", 4.5)
            metrics.record("embedding_dimension", 384)
        """
        with self._lock:
            self._values[name].add(value)
        logger.debug(f"[METRICS] {name} = {value}")

    def get_counter(self, name: str) -> int:
        """
        Get current counter value.

        Thread-safe: Uses internal locking for concurrent access.
        """
        with self._lock:
            return self._counters.get(name, 0)

    def get_timer_stats(self, name: str) -> dict[str, Any] | None:
        """
        Get statistics for a timer.

        Thread-safe: Uses internal locking for concurrent access.
        """
        with self._lock:
            if name in self._timers:
                return self._timers[name].to_dict()
            return None

    def get_value_stats(self, name: str) -> dict[str, Any] | None:
        """
        Get statistics for a recorded value.

        Thread-safe: Uses internal locking for concurrent access.
        """
        with self._lock:
            if name in self._values:
                return self._values[name].to_dict()
            return None

    def get_statistics(self) -> dict[str, Any]:
        """
        Get all collected statistics.

        Thread-safe: Uses internal locking for concurrent access.
        Returns a snapshot of current statistics.

        Returns:
            Dictionary with all metrics organized by type

        Example:
            stats = metrics.get_statistics()
            # {
            #     'timers': {'pubmed_search': {'count': 5, 'mean': 2.3, ...}},
            #     'counters': {'documents_processed': 150},
            #     'values': {'relevance_score': {'count': 50, 'mean': 3.2, ...}},
            #     'duration_seconds': 45.2
            # }
        """
        with self._lock:
            return {
                "timers": {k: v.to_dict() for k, v in self._timers.items()},
                "counters": dict(self._counters),
                "values": {k: v.to_dict() for k, v in self._values.items()},
                "duration_seconds": (datetime.now() - self._start_time).total_seconds(),
            }

    def summary(self) -> str:
        """
        Generate a human-readable summary.

        Thread-safe: Uses internal locking for concurrent access.

        Returns:
            Formatted string with all metrics

        Example:
            print(metrics.summary())
            # === Performance Metrics ===
            # Timers:
            #   pubmed_search: 5 calls, mean=2.34s, min=1.2s, max=4.5s
            # Counters:
            #   documents_processed: 150
            # ...
        """
        with self._lock:
            lines = ["=== Performance Metrics ==="]

            # Timers
            if self._timers:
                lines.append("\nTimers:")
                for name, stats in sorted(self._timers.items()):
                    lines.append(
                        f"  {name}: {stats.count} calls, "
                        f"mean={stats.mean:.3f}s, "
                        f"min={stats.min_value:.3f}s, "
                        f"max={stats.max_value:.3f}s"
                    )

            # Counters
            if self._counters:
                lines.append("\nCounters:")
                for name, value in sorted(self._counters.items()):
                    lines.append(f"  {name}: {value}")

            # Values
            if self._values:
                lines.append("\nRecorded Values:")
                for name, stats in sorted(self._values.items()):
                    lines.append(
                        f"  {name}: {stats.count} samples, "
                        f"mean={stats.mean:.3f}, "
                        f"min={stats.min_value:.3f}, "
                        f"max={stats.max_value:.3f}"
                    )

            # Duration
            duration = (datetime.now() - self._start_time).total_seconds()
            lines.append(f"\nTotal Duration: {duration:.1f}s")

            return "\n".join(lines)

    def reset(self) -> None:
        """
        Reset all metrics.

        Thread-safe: Uses internal locking for concurrent access.
        """
        with self._lock:
            self._timers.clear()
            self._counters.clear()
            self._values.clear()
            self._active_timers.clear()
            self._start_time = datetime.now()


# Global metrics instance for convenience
_global_metrics = MetricsCollector()


def get_metrics() -> MetricsCollector:
    """
    Get the global metrics collector instance.

    Returns:
        Global MetricsCollector instance

    Example:
        from bmlibrarian_lite.utils import get_metrics

        metrics = get_metrics()
        with metrics.timer("operation"):
            do_something()
    """
    return _global_metrics


def reset_metrics() -> None:
    """Reset the global metrics collector."""
    _global_metrics.reset()
