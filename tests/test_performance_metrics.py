"""
Tests for Performance Metrics functionality in BaseAgent.

Tests the PerformanceMetrics dataclass and related methods in BaseAgent
for tracking token usage, timing, and request statistics.
"""

import time
import pytest
from unittest.mock import MagicMock, patch

from bmlibrarian.agents import PerformanceMetrics
from bmlibrarian.agents.base import BaseAgent, NANOSECONDS_PER_SECOND


class ConcreteAgent(BaseAgent):
    """Concrete implementation of BaseAgent for testing."""

    def get_agent_type(self) -> str:
        return "TestAgent"


class TestPerformanceMetrics:
    """Tests for the PerformanceMetrics dataclass."""

    def test_initial_state(self) -> None:
        """Test that PerformanceMetrics initializes with zeros."""
        metrics = PerformanceMetrics()
        assert metrics.total_prompt_tokens == 0
        assert metrics.total_completion_tokens == 0
        assert metrics.total_tokens == 0
        assert metrics.total_requests == 0
        assert metrics.total_retries == 0
        assert metrics.total_wall_time_seconds == 0.0
        assert metrics.total_model_time_seconds == 0.0
        assert metrics.total_prompt_eval_seconds == 0.0
        assert metrics.start_time is None
        assert metrics.end_time is None

    def test_add_request_metrics(self) -> None:
        """Test adding metrics from a single request."""
        metrics = PerformanceMetrics()

        metrics.add_request_metrics(
            prompt_tokens=100,
            completion_tokens=50,
            wall_time_seconds=1.5,
            model_time_ns=1_000_000_000,  # 1 second
            prompt_eval_ns=500_000_000,   # 0.5 seconds
            retries=0
        )

        assert metrics.total_prompt_tokens == 100
        assert metrics.total_completion_tokens == 50
        assert metrics.total_tokens == 150
        assert metrics.total_requests == 1
        assert metrics.total_retries == 0
        assert metrics.total_wall_time_seconds == 1.5
        assert metrics.total_model_time_seconds == 1.0
        assert metrics.total_prompt_eval_seconds == 0.5

    def test_add_multiple_requests(self) -> None:
        """Test accumulating metrics from multiple requests."""
        metrics = PerformanceMetrics()

        # First request
        metrics.add_request_metrics(
            prompt_tokens=100,
            completion_tokens=50,
            wall_time_seconds=1.5,
            model_time_ns=1_000_000_000,
            prompt_eval_ns=500_000_000,
            retries=0
        )

        # Second request with retries
        metrics.add_request_metrics(
            prompt_tokens=200,
            completion_tokens=100,
            wall_time_seconds=2.0,
            model_time_ns=1_500_000_000,
            prompt_eval_ns=750_000_000,
            retries=2
        )

        assert metrics.total_prompt_tokens == 300
        assert metrics.total_completion_tokens == 150
        assert metrics.total_tokens == 450
        assert metrics.total_requests == 2
        assert metrics.total_retries == 2
        assert metrics.total_wall_time_seconds == 3.5
        assert metrics.total_model_time_seconds == 2.5
        assert metrics.total_prompt_eval_seconds == 1.25

    def test_mark_start_and_end(self) -> None:
        """Test marking start and end times."""
        metrics = PerformanceMetrics()

        metrics.mark_start()
        assert metrics.start_time is not None
        assert metrics.end_time is None

        time.sleep(0.05)  # Small delay

        metrics.mark_end()
        assert metrics.end_time is not None
        assert metrics.end_time > metrics.start_time

    def test_elapsed_time_with_start_end(self) -> None:
        """Test elapsed time calculation with start and end."""
        metrics = PerformanceMetrics()

        metrics.mark_start()
        time.sleep(0.1)
        metrics.mark_end()

        elapsed = metrics.elapsed_time_seconds
        assert elapsed >= 0.1
        assert elapsed < 0.2  # Should be close to 0.1

    def test_elapsed_time_no_start(self) -> None:
        """Test elapsed time when not started returns 0."""
        metrics = PerformanceMetrics()
        assert metrics.elapsed_time_seconds == 0.0

    def test_elapsed_time_running(self) -> None:
        """Test elapsed time while still running (no end)."""
        metrics = PerformanceMetrics()

        metrics.mark_start()
        time.sleep(0.05)

        # Should return current elapsed time
        elapsed = metrics.elapsed_time_seconds
        assert elapsed >= 0.05

    def test_tokens_per_second(self) -> None:
        """Test tokens per second calculation."""
        metrics = PerformanceMetrics()

        metrics.add_request_metrics(
            prompt_tokens=100,
            completion_tokens=100,
            wall_time_seconds=1.0,
            model_time_ns=2_000_000_000,  # 2 seconds
            prompt_eval_ns=0,
            retries=0
        )

        # 100 completion tokens / 2 seconds = 50 tokens/sec
        assert metrics.tokens_per_second == 50.0

    def test_tokens_per_second_zero_time(self) -> None:
        """Test tokens per second with zero model time returns 0."""
        metrics = PerformanceMetrics()
        assert metrics.tokens_per_second == 0.0

    def test_average_tokens_per_request(self) -> None:
        """Test average tokens per request calculation."""
        metrics = PerformanceMetrics()

        metrics.add_request_metrics(
            prompt_tokens=100,
            completion_tokens=100,
            wall_time_seconds=1.0,
            model_time_ns=1_000_000_000,
            prompt_eval_ns=0,
            retries=0
        )

        metrics.add_request_metrics(
            prompt_tokens=200,
            completion_tokens=200,
            wall_time_seconds=1.0,
            model_time_ns=1_000_000_000,
            prompt_eval_ns=0,
            retries=0
        )

        # Total 600 tokens / 2 requests = 300 avg
        assert metrics.average_tokens_per_request == 300.0

    def test_average_tokens_per_request_zero_requests(self) -> None:
        """Test average tokens with no requests returns 0."""
        metrics = PerformanceMetrics()
        assert metrics.average_tokens_per_request == 0.0

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        metrics = PerformanceMetrics()
        metrics.add_request_metrics(
            prompt_tokens=100,
            completion_tokens=50,
            wall_time_seconds=1.5,
            model_time_ns=1_000_000_000,
            prompt_eval_ns=500_000_000,
            retries=1
        )
        metrics.mark_start()
        metrics.mark_end()

        d = metrics.to_dict()

        assert 'total_prompt_tokens' in d
        assert 'total_completion_tokens' in d
        assert 'total_tokens' in d
        assert 'total_requests' in d
        assert 'total_retries' in d
        assert 'total_wall_time_seconds' in d
        assert 'total_model_time_seconds' in d
        assert 'elapsed_time_seconds' in d
        assert 'tokens_per_second' in d
        assert 'average_tokens_per_request' in d

        assert d['total_prompt_tokens'] == 100
        assert d['total_completion_tokens'] == 50
        assert d['total_tokens'] == 150
        assert d['total_requests'] == 1
        assert d['total_retries'] == 1

    def test_reset(self) -> None:
        """Test resetting metrics to initial state."""
        metrics = PerformanceMetrics()

        metrics.add_request_metrics(
            prompt_tokens=100,
            completion_tokens=50,
            wall_time_seconds=1.5,
            model_time_ns=1_000_000_000,
            prompt_eval_ns=500_000_000,
            retries=1
        )
        metrics.mark_start()
        metrics.mark_end()

        metrics.reset()

        assert metrics.total_prompt_tokens == 0
        assert metrics.total_completion_tokens == 0
        assert metrics.total_tokens == 0
        assert metrics.total_requests == 0
        assert metrics.total_retries == 0
        assert metrics.total_wall_time_seconds == 0.0
        assert metrics.total_model_time_seconds == 0.0
        assert metrics.start_time is None
        assert metrics.end_time is None


class TestBaseAgentMetrics:
    """Tests for metrics methods on BaseAgent."""

    @patch('bmlibrarian.agents.base.ollama.Client')
    def test_agent_has_metrics(self, mock_client: MagicMock) -> None:
        """Test that agent initializes with metrics."""
        agent = ConcreteAgent(model="test-model", show_model_info=False)

        assert hasattr(agent, '_metrics')
        assert isinstance(agent._metrics, PerformanceMetrics)

    @patch('bmlibrarian.agents.base.ollama.Client')
    def test_get_performance_metrics_returns_copy(self, mock_client: MagicMock) -> None:
        """Test that get_performance_metrics returns a copy."""
        agent = ConcreteAgent(model="test-model", show_model_info=False)

        # Manually add some metrics
        agent._metrics.add_request_metrics(
            prompt_tokens=100,
            completion_tokens=50,
            wall_time_seconds=1.0,
            model_time_ns=0,
            prompt_eval_ns=0,
            retries=0
        )

        metrics = agent.get_performance_metrics()

        # Should be a copy, not the same object
        assert metrics is not agent._metrics
        assert metrics.total_tokens == 150

        # Modifying the copy shouldn't affect the original
        metrics.total_tokens = 999
        assert agent._metrics.total_tokens == 150

    @patch('bmlibrarian.agents.base.ollama.Client')
    def test_reset_metrics(self, mock_client: MagicMock) -> None:
        """Test resetting metrics on agent."""
        agent = ConcreteAgent(model="test-model", show_model_info=False)

        agent._metrics.add_request_metrics(
            prompt_tokens=100,
            completion_tokens=50,
            wall_time_seconds=1.0,
            model_time_ns=0,
            prompt_eval_ns=0,
            retries=0
        )

        agent.reset_metrics()

        assert agent._metrics.total_tokens == 0
        assert agent._metrics.total_requests == 0

    @patch('bmlibrarian.agents.base.ollama.Client')
    def test_start_stop_metrics(self, mock_client: MagicMock) -> None:
        """Test start and stop metrics methods."""
        agent = ConcreteAgent(model="test-model", show_model_info=False)

        agent.start_metrics()
        assert agent._metrics.start_time is not None

        time.sleep(0.05)

        agent.stop_metrics()
        assert agent._metrics.end_time is not None
        assert agent._metrics.elapsed_time_seconds >= 0.05

    @patch('bmlibrarian.agents.base.ollama.Client')
    def test_format_metrics_report(self, mock_client: MagicMock) -> None:
        """Test formatted metrics report generation."""
        agent = ConcreteAgent(model="test-model", show_model_info=False)

        agent._metrics.add_request_metrics(
            prompt_tokens=1000,
            completion_tokens=500,
            wall_time_seconds=2.5,
            model_time_ns=2_000_000_000,  # 2 seconds
            prompt_eval_ns=500_000_000,
            retries=1
        )

        report = agent.format_metrics_report()

        assert "=== TestAgent Performance Metrics ===" in report
        assert "Requests:" in report
        assert "1" in report  # 1 request
        assert "1 retries" in report
        assert "Tokens:" in report
        assert "1,500 total" in report
        assert "1,000 prompt" in report
        assert "500 completion" in report
        assert "Time:" in report
        assert "Speed:" in report
        assert "tokens/sec" in report

    @patch('bmlibrarian.agents.base.ollama.Client')
    def test_format_metrics_report_no_header(self, mock_client: MagicMock) -> None:
        """Test formatted report without header."""
        agent = ConcreteAgent(model="test-model", show_model_info=False)

        agent._metrics.add_request_metrics(
            prompt_tokens=100,
            completion_tokens=50,
            wall_time_seconds=1.0,
            model_time_ns=1_000_000_000,
            prompt_eval_ns=0,
            retries=0
        )

        report = agent.format_metrics_report(include_header=False)

        assert "=== TestAgent Performance Metrics ===" not in report
        assert "Requests:" in report

    @patch('bmlibrarian.agents.base.ollama.Client')
    def test_get_metrics_dict(self, mock_client: MagicMock) -> None:
        """Test getting metrics as dictionary with agent metadata."""
        agent = ConcreteAgent(model="test-model", show_model_info=False)

        agent._metrics.add_request_metrics(
            prompt_tokens=100,
            completion_tokens=50,
            wall_time_seconds=1.0,
            model_time_ns=1_000_000_000,
            prompt_eval_ns=0,
            retries=0
        )

        d = agent.get_metrics_dict()

        assert d['agent_type'] == "TestAgent"
        assert d['model'] == "test-model"
        assert d['total_tokens'] == 150
        assert d['total_requests'] == 1


class TestMetricsIntegration:
    """Integration tests for metrics tracking in LLM calls."""

    @patch('bmlibrarian.agents.base.ollama.Client')
    def test_make_ollama_request_tracks_metrics(self, mock_client: MagicMock) -> None:
        """Test that _make_ollama_request captures token metrics."""
        # Setup mock response with token counts
        mock_response = {
            'message': {'content': 'test response'},
            'prompt_eval_count': 100,
            'eval_count': 50,
            'eval_duration': 1_000_000_000,  # 1 second in ns
            'prompt_eval_duration': 500_000_000  # 0.5 seconds
        }
        mock_client.return_value.chat.return_value = mock_response

        agent = ConcreteAgent(model="test-model", show_model_info=False)

        # Make a request
        result = agent._make_ollama_request(
            messages=[{'role': 'user', 'content': 'test'}]
        )

        # Verify metrics were captured
        metrics = agent.get_performance_metrics()
        assert metrics.total_prompt_tokens == 100
        assert metrics.total_completion_tokens == 50
        assert metrics.total_tokens == 150
        assert metrics.total_requests == 1
        assert metrics.total_model_time_seconds == 1.0
        assert metrics.total_prompt_eval_seconds == 0.5

    @patch('bmlibrarian.agents.base.ollama.Client')
    def test_generate_from_prompt_tracks_metrics(self, mock_client: MagicMock) -> None:
        """Test that _generate_from_prompt captures token metrics."""
        # Setup mock response with token counts
        mock_response = {
            'response': 'test response',
            'prompt_eval_count': 200,
            'eval_count': 100,
            'eval_duration': 2_000_000_000,  # 2 seconds
            'prompt_eval_duration': 1_000_000_000  # 1 second
        }
        mock_client.return_value.generate.return_value = mock_response

        agent = ConcreteAgent(model="test-model", show_model_info=False)

        # Make a request
        result = agent._generate_from_prompt("test prompt")

        # Verify metrics were captured
        metrics = agent.get_performance_metrics()
        assert metrics.total_prompt_tokens == 200
        assert metrics.total_completion_tokens == 100
        assert metrics.total_tokens == 300
        assert metrics.total_requests == 1
        assert metrics.total_model_time_seconds == 2.0
        assert metrics.total_prompt_eval_seconds == 1.0

    @patch('bmlibrarian.agents.base.ollama.Client')
    def test_multiple_requests_accumulate_metrics(self, mock_client: MagicMock) -> None:
        """Test that multiple requests accumulate metrics."""
        mock_client.return_value.chat.return_value = {
            'message': {'content': 'response'},
            'prompt_eval_count': 100,
            'eval_count': 50,
            'eval_duration': 500_000_000,
            'prompt_eval_duration': 250_000_000
        }

        agent = ConcreteAgent(model="test-model", show_model_info=False)

        # Make multiple requests
        for _ in range(3):
            agent._make_ollama_request(
                messages=[{'role': 'user', 'content': 'test'}]
            )

        # Verify accumulated metrics
        metrics = agent.get_performance_metrics()
        assert metrics.total_prompt_tokens == 300  # 100 * 3
        assert metrics.total_completion_tokens == 150  # 50 * 3
        assert metrics.total_tokens == 450  # 150 * 3
        assert metrics.total_requests == 3

    @patch('bmlibrarian.agents.base.ollama.Client')
    def test_metrics_with_missing_fields(self, mock_client: MagicMock) -> None:
        """Test that metrics handles responses with missing fields gracefully."""
        # Response without token count fields
        mock_response = {
            'message': {'content': 'test response'}
            # No token count fields
        }
        mock_client.return_value.chat.return_value = mock_response

        agent = ConcreteAgent(model="test-model", show_model_info=False)

        # Should not raise an error
        result = agent._make_ollama_request(
            messages=[{'role': 'user', 'content': 'test'}]
        )

        # Metrics should have zeros for missing fields
        metrics = agent.get_performance_metrics()
        assert metrics.total_prompt_tokens == 0
        assert metrics.total_completion_tokens == 0
        assert metrics.total_requests == 1  # Still counts as a request
