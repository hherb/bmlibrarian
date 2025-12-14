"""Tests for BMLibrarian Lite utilities.

This module tests:
- Exception classes and their hierarchy
- Retry logic with exponential backoff and jitter
- Thread-safe MetricsCollector
- Validation caching in LiteConfig
"""

import os
import random
import stat
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from bmlibrarian.lite.constants import CONFIG_FILE_PERMISSIONS
from bmlibrarian.lite.exceptions import (
    ChromaDBError,
    ConfigurationError,
    EmbeddingError,
    LiteError,
    LiteStorageError,
    LLMError,
    NetworkError,
    RetryExhaustedError,
    SQLiteError,
)
from bmlibrarian.lite.utils import (
    MetricsCollector,
    _calculate_delay_with_jitter,
    get_metrics,
    reset_metrics,
    retry_with_backoff,
)
from bmlibrarian.lite.config import LiteConfig


# =============================================================================
# Exception Classes Tests
# =============================================================================


class TestExceptionHierarchy:
    """Test the exception class hierarchy."""

    def test_lite_error_is_base(self) -> None:
        """Test that LiteError is the base exception."""
        assert issubclass(LiteStorageError, LiteError)
        assert issubclass(EmbeddingError, LiteError)
        assert issubclass(ConfigurationError, LiteError)
        assert issubclass(NetworkError, LiteError)
        assert issubclass(LLMError, LiteError)

    def test_storage_error_hierarchy(self) -> None:
        """Test storage exception subclasses."""
        assert issubclass(ChromaDBError, LiteStorageError)
        assert issubclass(SQLiteError, LiteStorageError)
        assert issubclass(ChromaDBError, LiteError)
        assert issubclass(SQLiteError, LiteError)

    def test_network_error_hierarchy(self) -> None:
        """Test network exception subclasses."""
        assert issubclass(RetryExhaustedError, NetworkError)
        assert issubclass(RetryExhaustedError, LiteError)

    def test_catching_base_exception(self) -> None:
        """Test that catching LiteError catches all subclasses."""
        exceptions = [
            ChromaDBError("test"),
            SQLiteError("test"),
            EmbeddingError("test"),
            ConfigurationError("test"),
            NetworkError("test"),
            LLMError("test"),
            RetryExhaustedError("test"),
        ]
        for exc in exceptions:
            try:
                raise exc
            except LiteError:
                pass  # Expected

    def test_catching_storage_error(self) -> None:
        """Test that catching LiteStorageError catches storage subclasses."""
        for exc_class in [ChromaDBError, SQLiteError]:
            try:
                raise exc_class("test")
            except LiteStorageError:
                pass  # Expected


class TestRetryExhaustedError:
    """Test the RetryExhaustedError exception."""

    def test_basic_creation(self) -> None:
        """Test basic exception creation."""
        exc = RetryExhaustedError("Operation failed")
        assert str(exc) == "Operation failed"
        assert exc.attempts == 0
        assert exc.last_error is None

    def test_with_attempts(self) -> None:
        """Test exception with attempt count."""
        exc = RetryExhaustedError("Failed after retries", attempts=5)
        assert exc.attempts == 5

    def test_with_last_error(self) -> None:
        """Test exception with last error."""
        original_error = ConnectionError("Connection refused")
        exc = RetryExhaustedError(
            "Failed after retries",
            attempts=3,
            last_error=original_error
        )
        assert exc.attempts == 3
        assert exc.last_error is original_error


# =============================================================================
# Retry Logic Tests
# =============================================================================


class TestDelayWithJitter:
    """Test delay calculation with jitter."""

    def test_no_jitter(self) -> None:
        """Test delay without jitter."""
        delay = _calculate_delay_with_jitter(
            base_delay=1.0,
            attempt=0,
            exponential_base=2.0,
            max_delay=10.0,
            jitter_factor=0.0
        )
        assert delay == 1.0

    def test_exponential_backoff(self) -> None:
        """Test exponential delay increase."""
        delays = []
        for attempt in range(5):
            delay = _calculate_delay_with_jitter(
                base_delay=1.0,
                attempt=attempt,
                exponential_base=2.0,
                max_delay=100.0,
                jitter_factor=0.0
            )
            delays.append(delay)

        assert delays == [1.0, 2.0, 4.0, 8.0, 16.0]

    def test_max_delay_cap(self) -> None:
        """Test that delay is capped at max_delay."""
        delay = _calculate_delay_with_jitter(
            base_delay=1.0,
            attempt=10,  # Would be 1024 without cap
            exponential_base=2.0,
            max_delay=5.0,
            jitter_factor=0.0
        )
        assert delay == 5.0

    def test_jitter_range(self) -> None:
        """Test that jitter stays within expected range."""
        random.seed(42)  # For reproducibility
        base = 10.0
        jitter_factor = 0.2  # +/- 20%

        delays = []
        for _ in range(100):
            delay = _calculate_delay_with_jitter(
                base_delay=base,
                attempt=0,
                exponential_base=2.0,
                max_delay=100.0,
                jitter_factor=jitter_factor
            )
            delays.append(delay)

        # All delays should be within range
        min_expected = base * (1 - jitter_factor)
        max_expected = base * (1 + jitter_factor)
        assert all(min_expected <= d <= max_expected for d in delays)

        # With enough samples, we should see variation
        assert min(delays) != max(delays)


class TestRetryWithBackoff:
    """Test the retry_with_backoff decorator."""

    def test_success_no_retry(self) -> None:
        """Test successful call without retry."""
        call_count = 0

        @retry_with_backoff(max_retries=3, jitter_factor=0.0)
        def succeeds() -> str:
            nonlocal call_count
            call_count += 1
            return "success"

        result = succeeds()
        assert result == "success"
        assert call_count == 1

    def test_retry_then_success(self) -> None:
        """Test retry followed by success."""
        call_count = 0

        @retry_with_backoff(
            max_retries=3,
            base_delay=0.01,
            jitter_factor=0.0
        )
        def fails_twice() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Failed")
            return "success"

        result = fails_twice()
        assert result == "success"
        assert call_count == 3

    def test_exhaust_retries(self) -> None:
        """Test exhausting all retry attempts."""
        call_count = 0

        @retry_with_backoff(
            max_retries=2,
            base_delay=0.01,
            jitter_factor=0.0
        )
        def always_fails() -> str:
            nonlocal call_count
            call_count += 1
            raise ConnectionError("Always fails")

        with pytest.raises(RetryExhaustedError) as exc_info:
            always_fails()

        assert call_count == 3  # Initial + 2 retries
        assert exc_info.value.attempts == 3
        assert isinstance(exc_info.value.last_error, ConnectionError)

    def test_non_retryable_exception(self) -> None:
        """Test that non-retryable exceptions are not retried."""
        call_count = 0

        @retry_with_backoff(
            max_retries=3,
            retryable_exceptions=(ConnectionError,)
        )
        def raises_value_error() -> None:
            nonlocal call_count
            call_count += 1
            raise ValueError("Not retryable")

        with pytest.raises(ValueError):
            raises_value_error()

        assert call_count == 1  # No retries

    def test_on_retry_callback(self) -> None:
        """Test the on_retry callback is called."""
        callbacks = []

        def on_retry(attempt: int, error: Exception, delay: float) -> None:
            callbacks.append((attempt, str(error), delay))

        @retry_with_backoff(
            max_retries=2,
            base_delay=0.01,
            jitter_factor=0.0,
            on_retry=on_retry
        )
        def fails_then_succeeds() -> str:
            if len(callbacks) < 2:
                raise ConnectionError(f"Attempt {len(callbacks) + 1}")
            return "success"

        result = fails_then_succeeds()
        assert result == "success"
        assert len(callbacks) == 2
        assert callbacks[0][0] == 1  # First retry
        assert callbacks[1][0] == 2  # Second retry


# =============================================================================
# Thread-Safe Metrics Tests
# =============================================================================


class TestMetricsCollectorThreadSafety:
    """Test MetricsCollector thread safety."""

    def test_concurrent_increments(self) -> None:
        """Test concurrent counter increments."""
        metrics = MetricsCollector()
        num_threads = 10
        increments_per_thread = 1000

        def worker() -> None:
            for _ in range(increments_per_thread):
                metrics.increment("counter")

        threads = [threading.Thread(target=worker) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        expected = num_threads * increments_per_thread
        assert metrics.get_counter("counter") == expected

    def test_concurrent_records(self) -> None:
        """Test concurrent value recording."""
        metrics = MetricsCollector()
        num_threads = 10
        records_per_thread = 100

        def worker(thread_id: int) -> None:
            for i in range(records_per_thread):
                metrics.record("values", float(thread_id * 1000 + i))

        threads = [
            threading.Thread(target=worker, args=(i,))
            for i in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        stats = metrics.get_value_stats("values")
        expected_count = num_threads * records_per_thread
        assert stats["count"] == expected_count

    def test_concurrent_timers(self) -> None:
        """Test concurrent timer operations."""
        metrics = MetricsCollector()
        num_threads = 10

        def worker(thread_id: int) -> None:
            with metrics.timer(f"operation_{thread_id}"):
                time.sleep(0.001)  # Small delay
            metrics.increment("completed")

        threads = [
            threading.Thread(target=worker, args=(i,))
            for i in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert metrics.get_counter("completed") == num_threads
        stats = metrics.get_statistics()
        assert len(stats["timers"]) == num_threads

    def test_nested_timer_contexts(self) -> None:
        """Test nested timer contexts (RLock allows reentrant locking)."""
        metrics = MetricsCollector()

        with metrics.timer("outer"):
            time.sleep(0.001)
            with metrics.timer("inner"):
                time.sleep(0.001)

        outer_stats = metrics.get_timer_stats("outer")
        inner_stats = metrics.get_timer_stats("inner")

        assert outer_stats is not None
        assert inner_stats is not None
        assert outer_stats["count"] == 1
        assert inner_stats["count"] == 1


class TestMetricsCollectorBasic:
    """Test basic MetricsCollector functionality."""

    def test_timer_context_manager(self) -> None:
        """Test timer context manager records duration."""
        metrics = MetricsCollector()

        with metrics.timer("test_operation"):
            time.sleep(0.01)

        stats = metrics.get_timer_stats("test_operation")
        assert stats is not None
        assert stats["count"] == 1
        assert stats["mean"] > 0.01

    def test_start_stop_timer(self) -> None:
        """Test manual start/stop timer."""
        metrics = MetricsCollector()

        metrics.start_timer("manual")
        time.sleep(0.01)
        duration = metrics.stop_timer("manual")

        assert duration > 0.01
        stats = metrics.get_timer_stats("manual")
        assert stats["count"] == 1

    def test_stop_nonexistent_timer(self) -> None:
        """Test stopping a timer that wasn't started."""
        metrics = MetricsCollector()

        with pytest.raises(KeyError):
            metrics.stop_timer("nonexistent")

    def test_increment_decrement(self) -> None:
        """Test counter increment and decrement."""
        metrics = MetricsCollector()

        metrics.increment("counter", 5)
        assert metrics.get_counter("counter") == 5

        metrics.increment("counter")  # +1
        assert metrics.get_counter("counter") == 6

        metrics.decrement("counter", 2)
        assert metrics.get_counter("counter") == 4

    def test_record_values(self) -> None:
        """Test recording values and statistics."""
        metrics = MetricsCollector()

        for v in [1.0, 2.0, 3.0, 4.0, 5.0]:
            metrics.record("values", v)

        stats = metrics.get_value_stats("values")
        assert stats["count"] == 5
        assert stats["mean"] == 3.0
        assert stats["min"] == 1.0
        assert stats["max"] == 5.0
        assert stats["median"] == 3.0

    def test_get_statistics(self) -> None:
        """Test getting all statistics."""
        metrics = MetricsCollector()

        metrics.increment("counter", 10)
        metrics.record("value", 5.0)
        with metrics.timer("operation"):
            pass

        stats = metrics.get_statistics()

        assert "timers" in stats
        assert "counters" in stats
        assert "values" in stats
        assert "duration_seconds" in stats

        assert stats["counters"]["counter"] == 10
        assert "operation" in stats["timers"]
        assert "value" in stats["values"]

    def test_reset(self) -> None:
        """Test resetting all metrics."""
        metrics = MetricsCollector()

        metrics.increment("counter", 10)
        metrics.record("value", 5.0)

        metrics.reset()

        assert metrics.get_counter("counter") == 0
        assert metrics.get_value_stats("value") is None


class TestGlobalMetrics:
    """Test global metrics functions."""

    def test_get_metrics(self) -> None:
        """Test getting global metrics instance."""
        metrics = get_metrics()
        assert isinstance(metrics, MetricsCollector)

    def test_reset_metrics(self) -> None:
        """Test resetting global metrics."""
        metrics = get_metrics()
        metrics.increment("test_global", 10)

        reset_metrics()

        assert metrics.get_counter("test_global") == 0


# =============================================================================
# Config Validation Caching Tests
# =============================================================================


class TestConfigValidationCaching:
    """Test config validation caching."""

    def test_validation_is_cached(self) -> None:
        """Test that validation results are cached."""
        config = LiteConfig()

        # First validation
        errors1 = config.validate()

        # Second validation should return cached result
        errors2 = config.validate()

        assert errors1 == errors2

    def test_cache_invalidated_on_change(self) -> None:
        """Test that cache is invalidated when config changes."""
        config = LiteConfig()

        # Validate once
        errors1 = config.validate()
        assert len(errors1) == 0

        # Change config
        config.llm.temperature = 2.0  # Invalid value

        # Should get fresh validation
        errors2 = config.validate()
        assert len(errors2) > 0
        assert any("temperature" in e for e in errors2)

    def test_invalidate_cache_manually(self) -> None:
        """Test manual cache invalidation."""
        config = LiteConfig()

        # Validate once
        config.validate()

        # Manual invalidation
        config.invalidate_validation_cache()

        # Should work without errors
        errors = config.validate()
        assert isinstance(errors, list)

    def test_save_invalidates_cache(self) -> None:
        """Test that save invalidates validation cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = LiteConfig()
            config.storage.data_dir = Path(tmpdir)

            # Validate and populate cache
            config.validate()
            assert len(config._validation_cache) > 0

            # Save should clear cache
            config.save()
            assert len(config._validation_cache) == 0


# =============================================================================
# Config File Permissions Tests
# =============================================================================


class TestConfigFilePermissions:
    """Test config file permissions."""

    def test_save_sets_permissions(self) -> None:
        """Test that save sets secure file permissions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = LiteConfig()
            config_path = Path(tmpdir) / "test_config.json"
            config.storage.data_dir = Path(tmpdir)

            config.save(config_path)

            # Check file permissions (Unix only)
            if os.name != 'nt':  # Not Windows
                file_stat = os.stat(config_path)
                mode = stat.S_IMODE(file_stat.st_mode)
                assert mode == CONFIG_FILE_PERMISSIONS

    def test_config_still_readable_after_permissions(self) -> None:
        """Test that config can be read after permissions are set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = LiteConfig()
            config_path = Path(tmpdir) / "test_config.json"
            config.storage.data_dir = Path(tmpdir)
            config.llm.model = "test-model"

            config.save(config_path)

            # Should be able to load it back
            loaded = LiteConfig.load(config_path)
            assert loaded.llm.model == "test-model"


# =============================================================================
# Config Validation Edge Cases
# =============================================================================


class TestConfigValidationEdgeCases:
    """Test config validation edge cases."""

    def test_empty_email_is_valid(self) -> None:
        """Test that empty email is valid (optional field)."""
        config = LiteConfig()
        config.pubmed.email = ""
        errors = config.validate()
        assert not any("email" in e for e in errors)

    def test_valid_email(self) -> None:
        """Test valid email passes validation."""
        config = LiteConfig()
        config.pubmed.email = "user@example.com"
        errors = config.validate()
        assert not any("email" in e for e in errors)

    def test_invalid_email(self) -> None:
        """Test invalid email fails validation."""
        config = LiteConfig()
        config.pubmed.email = "invalid-email"
        errors = config.validate()
        assert any("email" in e.lower() for e in errors)

    def test_temperature_boundary_values(self) -> None:
        """Test temperature boundary values."""
        config = LiteConfig()

        # Valid boundaries
        for temp in [0.0, 0.5, 1.0]:
            config.llm.temperature = temp
            config.invalidate_validation_cache()
            errors = config.validate()
            assert not any("temperature" in e for e in errors)

        # Invalid values
        for temp in [-0.1, 1.1, 2.0]:
            config.llm.temperature = temp
            config.invalidate_validation_cache()
            errors = config.validate()
            assert any("temperature" in e for e in errors)

    def test_similarity_threshold_boundary_values(self) -> None:
        """Test similarity threshold boundary values."""
        config = LiteConfig()

        # Valid boundaries
        for thresh in [0.0, 0.5, 1.0]:
            config.search.similarity_threshold = thresh
            config.invalidate_validation_cache()
            errors = config.validate()
            assert not any("threshold" in e.lower() for e in errors)

        # Invalid values
        for thresh in [-0.1, 1.1]:
            config.search.similarity_threshold = thresh
            config.invalidate_validation_cache()
            errors = config.validate()
            assert any("threshold" in e.lower() for e in errors)

    def test_chunk_overlap_less_than_size(self) -> None:
        """Test that chunk overlap must be less than chunk size."""
        config = LiteConfig()

        # Valid: overlap < size
        config.search.chunk_size = 1000
        config.search.chunk_overlap = 100
        config.invalidate_validation_cache()
        errors = config.validate()
        assert not any("overlap" in e.lower() for e in errors)

        # Invalid: overlap >= size
        config.search.chunk_overlap = 1000
        config.invalidate_validation_cache()
        errors = config.validate()
        assert any("overlap" in e.lower() for e in errors)

    def test_invalid_llm_provider(self) -> None:
        """Test that invalid LLM provider fails validation."""
        config = LiteConfig()
        config.llm.provider = "invalid_provider"
        errors = config.validate()
        assert any("provider" in e.lower() for e in errors)

    def test_invalid_embedding_model(self) -> None:
        """Test that invalid embedding model fails validation."""
        config = LiteConfig()
        config.embeddings.model = "invalid/model"
        errors = config.validate()
        assert any("embedding" in e.lower() for e in errors)

    def test_is_valid_convenience_method(self) -> None:
        """Test is_valid() convenience method."""
        config = LiteConfig()
        assert config.is_valid()

        config.llm.temperature = 2.0  # Invalid
        assert not config.is_valid()
