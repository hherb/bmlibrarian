"""
Data types for the LLM abstraction layer.

This module defines the unified data structures used across all LLM providers,
ensuring consistent interfaces regardless of the underlying provider.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any


class Provider(Enum):
    """Supported LLM providers."""

    OLLAMA = "ollama"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"


@dataclass
class ModelSpec:
    """
    Parsed model specification.

    Represents a model identifier that has been parsed to extract
    the provider and model name.

    Attributes:
        provider: The LLM provider to use
        model_name: The model name without provider prefix
        raw: Original string for error messages
    """

    provider: Provider
    model_name: str
    raw: str


@dataclass
class LLMMessage:
    """
    Unified message format for chat completions.

    Attributes:
        role: Message role - "system", "user", or "assistant"
        content: The message content
    """

    role: str
    content: str


@dataclass
class LLMResponse:
    """
    Unified response from any LLM provider.

    Provides a consistent interface for responses regardless of
    which provider generated them.

    Attributes:
        content: The generated text content
        model: Model name that generated the response
        provider: Provider that handled the request
        prompt_tokens: Number of tokens in the prompt
        completion_tokens: Number of tokens in the completion
        total_tokens: Total tokens used
        duration_seconds: Time taken for the request
        raw_response: Provider-specific response data
    """

    content: str
    model: str
    provider: Provider

    # Token usage (for cost tracking)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    # Timing
    duration_seconds: float = 0.0

    # Provider-specific metadata
    raw_response: Optional[dict[str, Any]] = None


@dataclass
class EmbeddingResponse:
    """
    Unified embedding response.

    Attributes:
        embedding: The embedding vector
        model: Model name that generated the embedding
        provider: Provider that handled the request
        dimensions: Number of dimensions in the embedding
        prompt_tokens: Number of tokens in the input
    """

    embedding: list[float]
    model: str
    provider: Provider
    dimensions: int = 0
    prompt_tokens: int = 0


@dataclass
class GenerationParams:
    """
    Parameters for text generation.

    Encapsulates all generation parameters in a unified format
    that can be translated to provider-specific options.

    Attributes:
        temperature: Sampling temperature (0.0-2.0)
        top_p: Top-p (nucleus) sampling parameter
        max_tokens: Maximum tokens to generate
        stop_sequences: Sequences that stop generation
        json_mode: Request JSON-formatted output
        extra: Provider-specific parameters passed through
    """

    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: Optional[int] = None
    stop_sequences: Optional[list[str]] = None
    json_mode: bool = False

    # Provider-specific overrides (passed through)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderConfig:
    """
    Configuration for a specific provider.

    Attributes:
        api_key: API key for authenticated providers
        host: Server URL for self-hosted providers
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts
        extra: Provider-specific configuration
    """

    api_key: Optional[str] = None
    host: Optional[str] = None
    timeout: float = 120.0
    max_retries: int = 3

    # Provider-specific configuration
    extra: dict[str, Any] = field(default_factory=dict)
