"""
Token usage and cost tracking for LLM API calls.

This module provides thread-safe tracking of token usage across all LLM
providers, with cost estimation based on current provider pricing.

Usage:
    tracker = get_token_tracker()
    tracker.record_usage(Provider.ANTHROPIC, "claude-3-opus", 1000, 500)
    print(tracker.format_report())
"""

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .data_types import Provider

logger = logging.getLogger(__name__)

# Cost per 1M tokens (input/output) in USD
# Updated periodically - check provider pricing pages for current rates
PROVIDER_COSTS: dict[Provider, dict[str, dict[str, float]]] = {
    Provider.OLLAMA: {},  # Local, free - no per-model costs
    Provider.ANTHROPIC: {
        "claude-3-opus": {"input": 15.0, "output": 75.0},
        "claude-3-sonnet": {"input": 3.0, "output": 15.0},
        "claude-3-haiku": {"input": 0.25, "output": 1.25},
        "claude-3-5-sonnet": {"input": 3.0, "output": 15.0},
        "claude-3-5-haiku": {"input": 0.80, "output": 4.0},
        "claude-sonnet-4": {"input": 3.0, "output": 15.0},
        "claude-opus-4": {"input": 15.0, "output": 75.0},
    },
    Provider.OPENAI: {
        "gpt-4": {"input": 30.0, "output": 60.0},
        "gpt-4-turbo": {"input": 10.0, "output": 30.0},
        "gpt-4o": {"input": 2.50, "output": 10.0},
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "gpt-4.1": {"input": 2.0, "output": 8.0},
        "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
        "gpt-4.1-nano": {"input": 0.10, "output": 0.40},
        "o1": {"input": 15.0, "output": 60.0},
        "o1-mini": {"input": 1.10, "output": 4.40},
        "o1-pro": {"input": 150.0, "output": 600.0},
        "o3-mini": {"input": 1.10, "output": 4.40},
    },
}


@dataclass
class UsageRecord:
    """
    Single usage record for an LLM API call.

    Attributes:
        timestamp: When the call was made
        provider: Which provider handled the call
        model: Model name used
        prompt_tokens: Tokens in the prompt
        completion_tokens: Tokens in the completion
        cost_usd: Estimated cost in USD
        operation: Type of operation ("chat", "generate", "embed")
    """

    timestamp: datetime
    provider: Provider
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    operation: str


@dataclass
class UsageSummary:
    """
    Aggregated usage statistics.

    Attributes:
        total_prompt_tokens: Sum of all prompt tokens
        total_completion_tokens: Sum of all completion tokens
        total_tokens: Total tokens across all calls
        total_cost_usd: Estimated total cost
        request_count: Number of API calls
        by_provider: Breakdown by provider
        by_model: Breakdown by model
    """

    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    request_count: int = 0

    # Per-provider breakdown
    by_provider: dict[str, dict[str, float | int]] = field(default_factory=dict)
    # Per-model breakdown
    by_model: dict[str, dict[str, float | int]] = field(default_factory=dict)


class TokenTracker:
    """
    Thread-safe token usage and cost tracker.

    Tracks all LLM API calls for cost estimation and monitoring.
    Uses a singleton pattern via get_token_tracker() for global tracking.

    Example:
        tracker = TokenTracker()
        cost = tracker.record_usage(
            Provider.ANTHROPIC, "claude-3-opus", 1000, 500, "chat"
        )
        print(f"This call cost ${cost:.4f}")
        print(tracker.format_report())
    """

    def __init__(self) -> None:
        """Initialize the token tracker."""
        self._lock = threading.Lock()
        self._records: list[UsageRecord] = []
        self._session_start = datetime.now()

    def record_usage(
        self,
        provider: Provider,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        operation: str = "chat",
    ) -> float:
        """
        Record token usage and calculate cost.

        Args:
            provider: Which provider handled the request
            model: Model name (without provider prefix)
            prompt_tokens: Number of tokens in the prompt
            completion_tokens: Number of tokens in the completion
            operation: Type of operation ("chat", "generate", "embed")

        Returns:
            Estimated cost in USD for this call
        """
        cost = self._calculate_cost(provider, model, prompt_tokens, completion_tokens)

        record = UsageRecord(
            timestamp=datetime.now(),
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost,
            operation=operation,
        )

        with self._lock:
            self._records.append(record)

        if cost > 0:
            logger.debug(
                f"Recorded usage: {provider.value}:{model} - "
                f"{prompt_tokens + completion_tokens} tokens, ${cost:.4f}"
            )

        return cost

    def _calculate_cost(
        self,
        provider: Provider,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> float:
        """
        Calculate cost in USD based on provider pricing.

        Args:
            provider: The LLM provider
            model: Model name
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens

        Returns:
            Estimated cost in USD
        """
        if provider == Provider.OLLAMA:
            return 0.0  # Local, free

        provider_costs = PROVIDER_COSTS.get(provider, {})

        # Try exact model match first
        model_costs = provider_costs.get(model)

        # Fall back to partial match (e.g., "claude-3-opus-20240229" → "claude-3-opus")
        if model_costs is None:
            for known_model, costs in provider_costs.items():
                if known_model in model or model.startswith(known_model):
                    model_costs = costs
                    break

        if model_costs is None:
            # Unknown model - log warning and return 0
            logger.warning(
                f"Unknown model for cost calculation: {provider.value}:{model}"
            )
            return 0.0

        input_cost = (prompt_tokens / 1_000_000) * model_costs["input"]
        output_cost = (completion_tokens / 1_000_000) * model_costs["output"]

        return input_cost + output_cost

    def get_summary(self) -> UsageSummary:
        """
        Get aggregated usage summary.

        Returns:
            UsageSummary with totals and breakdowns
        """
        summary = UsageSummary()

        with self._lock:
            for record in self._records:
                summary.total_prompt_tokens += record.prompt_tokens
                summary.total_completion_tokens += record.completion_tokens
                summary.total_tokens += record.prompt_tokens + record.completion_tokens
                summary.total_cost_usd += record.cost_usd
                summary.request_count += 1

                # By provider
                pkey = record.provider.value
                if pkey not in summary.by_provider:
                    summary.by_provider[pkey] = {
                        "tokens": 0,
                        "cost_usd": 0.0,
                        "requests": 0,
                    }
                summary.by_provider[pkey]["tokens"] += (
                    record.prompt_tokens + record.completion_tokens
                )
                summary.by_provider[pkey]["cost_usd"] += record.cost_usd
                summary.by_provider[pkey]["requests"] += 1

                # By model
                mkey = f"{record.provider.value}:{record.model}"
                if mkey not in summary.by_model:
                    summary.by_model[mkey] = {
                        "tokens": 0,
                        "cost_usd": 0.0,
                        "requests": 0,
                    }
                summary.by_model[mkey]["tokens"] += (
                    record.prompt_tokens + record.completion_tokens
                )
                summary.by_model[mkey]["cost_usd"] += record.cost_usd
                summary.by_model[mkey]["requests"] += 1

        return summary

    def get_records(self) -> list[UsageRecord]:
        """
        Get a copy of all usage records.

        Returns:
            List of UsageRecord objects
        """
        with self._lock:
            return list(self._records)

    def format_report(self) -> str:
        """
        Format usage report as human-readable string.

        Returns:
            Formatted multi-line report string
        """
        summary = self.get_summary()
        session_duration = datetime.now() - self._session_start

        lines = [
            "=" * 60,
            "LLM Usage Report",
            "=" * 60,
            f"Session started: {self._session_start.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Session duration: {session_duration}",
            f"Total requests: {summary.request_count}",
            f"Total tokens: {summary.total_tokens:,}",
            f"  - Prompt: {summary.total_prompt_tokens:,}",
            f"  - Completion: {summary.total_completion_tokens:,}",
            f"Estimated cost: ${summary.total_cost_usd:.4f}",
        ]

        if summary.by_provider:
            lines.append("")
            lines.append("By Provider:")
            for provider, stats in sorted(summary.by_provider.items()):
                lines.append(
                    f"  {provider}: {stats['requests']} requests, "
                    f"{stats['tokens']:,} tokens, ${stats['cost_usd']:.4f}"
                )

        if summary.by_model:
            lines.append("")
            lines.append("By Model:")
            for model, stats in sorted(summary.by_model.items()):
                lines.append(
                    f"  {model}: {stats['requests']} requests, "
                    f"{stats['tokens']:,} tokens, ${stats['cost_usd']:.4f}"
                )

        lines.append("=" * 60)
        return "\n".join(lines)

    def reset(self) -> None:
        """Reset all tracking data and start a new session."""
        with self._lock:
            self._records.clear()
            self._session_start = datetime.now()
        logger.info("Token tracker reset")

    def get_session_start(self) -> datetime:
        """Get the session start time."""
        return self._session_start


# Global tracker instance (singleton pattern)
_global_tracker: Optional[TokenTracker] = None
_tracker_lock = threading.Lock()


def get_token_tracker() -> TokenTracker:
    """
    Get or create the global token tracker.

    Uses singleton pattern to ensure all usage is tracked in one place.

    Returns:
        The global TokenTracker instance
    """
    global _global_tracker
    with _tracker_lock:
        if _global_tracker is None:
            _global_tracker = TokenTracker()
        return _global_tracker


def reset_global_tracker() -> None:
    """
    Reset the global token tracker.

    Creates a new tracker instance, discarding all previous records.
    Useful for testing or starting fresh sessions.
    """
    global _global_tracker
    with _tracker_lock:
        _global_tracker = TokenTracker()
