"""
Token usage tracking for LLM operations.

Tracks cumulative token usage and estimated costs across all LLM calls
during a session.

Usage:
    from bmlibrarian_lite.llm import get_token_tracker

    tracker = get_token_tracker()
    tracker.record_usage(model="claude-3-sonnet", input_tokens=100, output_tokens=50)

    summary = tracker.get_summary()
    print(f"Total tokens: {summary.total_tokens}")
    print(f"Estimated cost: ${summary.total_cost_usd:.4f}")
"""

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from .data_types import get_model_info

logger = logging.getLogger(__name__)


@dataclass
class TokenUsageRecord:
    """
    Record of a single LLM call's token usage.

    Attributes:
        model: Model that was used
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        timestamp: When the call was made
        cost_usd: Estimated cost in USD
    """
    model: str
    input_tokens: int
    output_tokens: int
    timestamp: datetime = field(default_factory=datetime.now)
    cost_usd: float = 0.0

    def __post_init__(self) -> None:
        """Calculate cost if not provided."""
        if self.cost_usd == 0.0:
            model_info = get_model_info(self.model)
            input_cost = (
                self.input_tokens * model_info.input_cost_per_million / 1_000_000
            )
            output_cost = (
                self.output_tokens * model_info.output_cost_per_million / 1_000_000
            )
            self.cost_usd = input_cost + output_cost


@dataclass
class TokenUsageSummary:
    """
    Summary of token usage.

    Attributes:
        total_input_tokens: Total input tokens used
        total_output_tokens: Total output tokens generated
        total_tokens: Total tokens (input + output)
        total_cost_usd: Total estimated cost in USD
        call_count: Number of LLM calls made
        by_model: Breakdown by model
    """
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    call_count: int = 0
    by_model: Dict[str, Dict] = field(default_factory=dict)


class TokenTracker:
    """
    Thread-safe token usage tracker.

    Maintains a running total of token usage and costs for the session.
    """

    def __init__(self) -> None:
        """Initialize the token tracker."""
        self._records: List[TokenUsageRecord] = []
        self._lock = threading.Lock()
        self._total_input = 0
        self._total_output = 0
        self._total_cost = 0.0

    def record_usage(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """
        Record token usage from an LLM call.

        Args:
            model: Model that was used
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
        """
        record = TokenUsageRecord(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

        with self._lock:
            self._records.append(record)
            self._total_input += input_tokens
            self._total_output += output_tokens
            self._total_cost += record.cost_usd

        logger.debug(
            f"Recorded usage: {model}, "
            f"in={input_tokens}, out={output_tokens}, "
            f"cost=${record.cost_usd:.6f}"
        )

    def get_summary(self) -> TokenUsageSummary:
        """
        Get a summary of token usage.

        Returns:
            TokenUsageSummary with aggregate statistics
        """
        with self._lock:
            # Build by-model breakdown
            by_model: Dict[str, Dict] = {}
            for record in self._records:
                if record.model not in by_model:
                    by_model[record.model] = {
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "cost_usd": 0.0,
                        "calls": 0,
                    }
                by_model[record.model]["input_tokens"] += record.input_tokens
                by_model[record.model]["output_tokens"] += record.output_tokens
                by_model[record.model]["cost_usd"] += record.cost_usd
                by_model[record.model]["calls"] += 1

            return TokenUsageSummary(
                total_input_tokens=self._total_input,
                total_output_tokens=self._total_output,
                total_tokens=self._total_input + self._total_output,
                total_cost_usd=self._total_cost,
                call_count=len(self._records),
                by_model=by_model,
            )

    def reset(self) -> None:
        """Reset all usage tracking."""
        with self._lock:
            self._records.clear()
            self._total_input = 0
            self._total_output = 0
            self._total_cost = 0.0

        logger.debug("Token tracker reset")

    def get_recent_records(self, count: int = 10) -> List[TokenUsageRecord]:
        """
        Get recent usage records.

        Args:
            count: Number of recent records to return

        Returns:
            List of recent TokenUsageRecords
        """
        with self._lock:
            return list(self._records[-count:])


# Global tracker instance
_global_tracker: Optional[TokenTracker] = None
_tracker_lock = threading.Lock()


def get_token_tracker() -> TokenTracker:
    """
    Get the global token tracker instance.

    Creates a new instance if one doesn't exist.

    Returns:
        Global TokenTracker instance
    """
    global _global_tracker
    with _tracker_lock:
        if _global_tracker is None:
            _global_tracker = TokenTracker()
        return _global_tracker
