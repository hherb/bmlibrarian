"""
Data types for LLM communication.

Provides type-safe dataclasses for messages and responses.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Literal


@dataclass
class LLMMessage:
    """
    A message in an LLM conversation.

    Attributes:
        role: The role of the message sender (system, user, or assistant)
        content: The text content of the message
    """
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass
class LLMResponse:
    """
    Response from an LLM request.

    Attributes:
        content: The text response from the model
        model: The model that generated the response
        input_tokens: Number of input tokens used
        output_tokens: Number of output tokens generated
        total_tokens: Total tokens used (input + output)
        stop_reason: Why the model stopped generating
    """
    content: str
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    stop_reason: Optional[str] = None

    def __post_init__(self) -> None:
        """Calculate total tokens if not provided."""
        if self.total_tokens == 0:
            self.total_tokens = self.input_tokens + self.output_tokens


@dataclass
class ModelInfo:
    """
    Information about an LLM model.

    Attributes:
        provider: The provider name (anthropic, ollama)
        model: The model name/ID
        display_name: Human-readable name
        input_cost_per_million: Cost per million input tokens (USD)
        output_cost_per_million: Cost per million output tokens (USD)
    """
    provider: str
    model: str
    display_name: str = ""
    input_cost_per_million: float = 0.0
    output_cost_per_million: float = 0.0

    def __post_init__(self) -> None:
        """Set display name if not provided."""
        if not self.display_name:
            self.display_name = f"{self.provider}:{self.model}"


# Model cost configuration (USD per million tokens)
# Anthropic pricing as of 2024
MODEL_COSTS = {
    # Claude 4 models
    "claude-sonnet-4-20250514": ModelInfo(
        provider="anthropic",
        model="claude-sonnet-4-20250514",
        display_name="Claude Sonnet 4",
        input_cost_per_million=3.0,
        output_cost_per_million=15.0,
    ),
    "claude-opus-4-20250514": ModelInfo(
        provider="anthropic",
        model="claude-opus-4-20250514",
        display_name="Claude Opus 4",
        input_cost_per_million=15.0,
        output_cost_per_million=75.0,
    ),
    # Claude 3.5 models
    "claude-3-5-sonnet-20241022": ModelInfo(
        provider="anthropic",
        model="claude-3-5-sonnet-20241022",
        display_name="Claude 3.5 Sonnet",
        input_cost_per_million=3.0,
        output_cost_per_million=15.0,
    ),
    "claude-3-5-haiku-20241022": ModelInfo(
        provider="anthropic",
        model="claude-3-5-haiku-20241022",
        display_name="Claude 3.5 Haiku",
        input_cost_per_million=1.0,
        output_cost_per_million=5.0,
    ),
    # Claude 3 models
    "claude-3-opus-20240229": ModelInfo(
        provider="anthropic",
        model="claude-3-opus-20240229",
        display_name="Claude 3 Opus",
        input_cost_per_million=15.0,
        output_cost_per_million=75.0,
    ),
    "claude-3-sonnet-20240229": ModelInfo(
        provider="anthropic",
        model="claude-3-sonnet-20240229",
        display_name="Claude 3 Sonnet",
        input_cost_per_million=3.0,
        output_cost_per_million=15.0,
    ),
    "claude-3-haiku-20240307": ModelInfo(
        provider="anthropic",
        model="claude-3-haiku-20240307",
        display_name="Claude 3 Haiku",
        input_cost_per_million=0.25,
        output_cost_per_million=1.25,
    ),
}


def get_model_info(model: str) -> ModelInfo:
    """
    Get model information for cost calculation.

    Args:
        model: Model name (with or without provider prefix)

    Returns:
        ModelInfo for the model, or default info for unknown models
    """
    # Strip provider prefix if present
    if ":" in model:
        _, model_name = model.split(":", 1)
    else:
        model_name = model

    # Look up model info
    if model_name in MODEL_COSTS:
        return MODEL_COSTS[model_name]

    # Default for unknown models (Ollama models are free)
    return ModelInfo(
        provider="unknown",
        model=model_name,
        display_name=model_name,
        input_cost_per_million=0.0,
        output_cost_per_million=0.0,
    )
