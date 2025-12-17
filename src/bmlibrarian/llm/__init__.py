"""
LLM abstraction layer for BMLibrarian.

This module provides a unified interface for interacting with multiple
LLM providers (Ollama, Anthropic, OpenAI) with automatic fallback,
token tracking, and cost estimation.

Quick Start:
    from bmlibrarian.llm import LLMClient, LLMMessage

    # Create client
    client = LLMClient()

    # Chat with Ollama (default)
    response = client.chat(
        messages=[LLMMessage(role="user", content="Hello!")],
        model="medgemma-27b"
    )
    print(response.content)

    # Chat with Anthropic (with Ollama fallback)
    response = client.chat(
        messages=[LLMMessage(role="user", content="Hello!")],
        model="anthropic:claude-3-opus",
        fallback_model="medgemma-27b"
    )

    # Get usage report
    print(client.get_usage_report())

Model String Format:
    - "model-name" - Uses default provider (Ollama)
    - "ollama:model-name" - Explicit Ollama
    - "anthropic:claude-3-opus" - Anthropic Claude
    - "openai:gpt-4" - OpenAI (future)

Configuration:
    - OLLAMA_HOST: Ollama server URL (default: http://localhost:11434)
    - ANTHROPIC_API_KEY: Anthropic API key (required for anthropic: models)
    - OPENAI_API_KEY: OpenAI API key (required for openai: models)
"""

# Data types
from .data_types import (
    Provider,
    ModelSpec,
    LLMMessage,
    LLMResponse,
    EmbeddingResponse,
    GenerationParams,
    ProviderConfig,
)

# Model resolver
from .model_resolver import (
    parse_model_string,
    format_model_string,
    is_provider_prefix,
    get_supported_providers,
)

# Token tracking
from .token_tracker import (
    TokenTracker,
    UsageRecord,
    UsageSummary,
    get_token_tracker,
    reset_global_tracker,
)

# Constants
from .constants import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_OLLAMA_HOST,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_DELAY,
)

# Client
from .client import (
    LLMClient,
    get_llm_client,
    list_ollama_models,
)

# Provider access (for advanced use cases)
from .providers import (
    LLMProvider,
    get_provider,
    reset_provider,
    reset_all_providers,
    get_available_providers,
    is_provider_available,
)

__all__ = [
    # Data types
    "Provider",
    "ModelSpec",
    "LLMMessage",
    "LLMResponse",
    "EmbeddingResponse",
    "GenerationParams",
    "ProviderConfig",
    # Model resolver
    "parse_model_string",
    "format_model_string",
    "is_provider_prefix",
    "get_supported_providers",
    # Token tracking
    "TokenTracker",
    "UsageRecord",
    "UsageSummary",
    "get_token_tracker",
    "reset_global_tracker",
    # Constants
    "DEFAULT_EMBEDDING_MODEL",
    "DEFAULT_OLLAMA_HOST",
    "DEFAULT_TEMPERATURE",
    "DEFAULT_TOP_P",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_RETRY_DELAY",
    # Client (primary interface)
    "LLMClient",
    "get_llm_client",
    "list_ollama_models",
    # Providers (advanced)
    "LLMProvider",
    "get_provider",
    "reset_provider",
    "reset_all_providers",
    "get_available_providers",
    "is_provider_available",
]
