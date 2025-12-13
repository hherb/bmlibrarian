# LLM Backend Abstraction Implementation Plan

## Overview

Abstract LLM calls to support multiple backends (Ollama, Anthropic, OpenAI, etc.) with:
- Model string prefix for provider selection (`anthropic:claude-3-opus`)
- Singleton client per provider (connection reuse)
- Automatic fallback to Ollama (cost prevention)
- API keys via environment variables
- Token usage tracking for cost estimates

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Provider identification | Model string prefix | Backward compatible, intuitive |
| Client management | Singleton per provider | Connection reuse, low latency |
| Default provider | Ollama | Local, free, existing behavior |
| Fallback strategy | Always Ollama | Prevent unexpected costs |
| API key storage | Environment variables | Security, 12-factor app |
| Token tracking | Per-provider, per-model | Cost estimation |

## File Structure

```
src/bmlibrarian/llm/
├── __init__.py              # Public API exports
├── client.py                # LLMClient - unified interface
├── model_resolver.py        # Parse "provider:model" strings
├── token_tracker.py         # Usage and cost tracking
├── providers/
│   ├── __init__.py          # Provider registry
│   ├── base.py              # LLMProvider ABC
│   ├── ollama_provider.py   # Ollama implementation
│   ├── anthropic_provider.py # Anthropic implementation
│   └── openai_provider.py   # OpenAI implementation (future)
└── data_types.py            # Shared dataclasses
```

## Phase 1: Core Infrastructure

### 1.1 Data Types (`data_types.py`)

```python
from dataclasses import dataclass, field
from typing import Optional, Any
from enum import Enum

class Provider(Enum):
    """Supported LLM providers."""
    OLLAMA = "ollama"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"

@dataclass
class ModelSpec:
    """Parsed model specification."""
    provider: Provider
    model_name: str
    raw: str  # Original string for error messages

@dataclass
class LLMMessage:
    """Unified message format."""
    role: str  # "system", "user", "assistant"
    content: str

@dataclass
class LLMResponse:
    """Unified response from any provider."""
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
    raw_response: Optional[dict] = None

@dataclass
class EmbeddingResponse:
    """Unified embedding response."""
    embedding: list[float]
    model: str
    provider: Provider
    dimensions: int = 0
    prompt_tokens: int = 0

@dataclass
class GenerationParams:
    """Parameters for text generation."""
    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: Optional[int] = None
    stop_sequences: Optional[list[str]] = None
    json_mode: bool = False

    # Provider-specific overrides (passed through)
    extra: dict = field(default_factory=dict)
```

### 1.2 Model Resolver (`model_resolver.py`)

```python
import re
from .data_types import Provider, ModelSpec

# Default provider when no prefix specified
DEFAULT_PROVIDER = Provider.OLLAMA

# Provider prefix patterns
PROVIDER_PREFIXES = {
    "ollama": Provider.OLLAMA,
    "anthropic": Provider.ANTHROPIC,
    "openai": Provider.OPENAI,
}

def parse_model_string(model_string: str) -> ModelSpec:
    """
    Parse model string with optional provider prefix.

    Examples:
        "medgemma-27b" → ModelSpec(OLLAMA, "medgemma-27b")
        "ollama:medgemma-27b" → ModelSpec(OLLAMA, "medgemma-27b")
        "anthropic:claude-3-opus" → ModelSpec(ANTHROPIC, "claude-3-opus")
        "openai:gpt-4" → ModelSpec(OPENAI, "gpt-4")

    Args:
        model_string: Model identifier, optionally prefixed with provider

    Returns:
        ModelSpec with resolved provider and model name
    """
    if ":" in model_string:
        # Check if it's a provider prefix or part of model name (e.g., "gpt-oss:20b")
        prefix, remainder = model_string.split(":", 1)
        prefix_lower = prefix.lower()

        if prefix_lower in PROVIDER_PREFIXES:
            return ModelSpec(
                provider=PROVIDER_PREFIXES[prefix_lower],
                model_name=remainder,
                raw=model_string
            )

    # No recognized prefix - default to Ollama
    return ModelSpec(
        provider=DEFAULT_PROVIDER,
        model_name=model_string,
        raw=model_string
    )

def format_model_string(provider: Provider, model_name: str) -> str:
    """Format provider and model name into canonical string."""
    if provider == DEFAULT_PROVIDER:
        return model_name  # No prefix needed for default
    return f"{provider.value}:{model_name}"
```

### 1.3 Token Tracker (`token_tracker.py`)

```python
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from .data_types import Provider

# Cost per 1M tokens (input/output) - updated periodically
PROVIDER_COSTS = {
    Provider.OLLAMA: {"input": 0.0, "output": 0.0},  # Local, free
    Provider.ANTHROPIC: {
        "claude-3-opus": {"input": 15.0, "output": 75.0},
        "claude-3-sonnet": {"input": 3.0, "output": 15.0},
        "claude-3-haiku": {"input": 0.25, "output": 1.25},
        "claude-3-5-sonnet": {"input": 3.0, "output": 15.0},
    },
    Provider.OPENAI: {
        "gpt-4": {"input": 30.0, "output": 60.0},
        "gpt-4-turbo": {"input": 10.0, "output": 30.0},
        "gpt-4o": {"input": 5.0, "output": 15.0},
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    },
}

@dataclass
class UsageRecord:
    """Single usage record."""
    timestamp: datetime
    provider: Provider
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    operation: str  # "chat", "generate", "embed"

@dataclass
class UsageSummary:
    """Aggregated usage statistics."""
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    request_count: int = 0

    # Per-provider breakdown
    by_provider: dict = field(default_factory=dict)
    # Per-model breakdown
    by_model: dict = field(default_factory=dict)

class TokenTracker:
    """
    Thread-safe token usage and cost tracker.

    Tracks all LLM API calls for cost estimation and monitoring.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._records: list[UsageRecord] = []
        self._session_start = datetime.now()

    def record_usage(
        self,
        provider: Provider,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        operation: str = "chat"
    ) -> float:
        """
        Record token usage and calculate cost.

        Returns:
            Estimated cost in USD
        """
        cost = self._calculate_cost(provider, model, prompt_tokens, completion_tokens)

        record = UsageRecord(
            timestamp=datetime.now(),
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost,
            operation=operation
        )

        with self._lock:
            self._records.append(record)

        return cost

    def _calculate_cost(
        self,
        provider: Provider,
        model: str,
        prompt_tokens: int,
        completion_tokens: int
    ) -> float:
        """Calculate cost in USD based on provider pricing."""
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
            # Unknown model - return 0 but log warning
            return 0.0

        input_cost = (prompt_tokens / 1_000_000) * model_costs["input"]
        output_cost = (completion_tokens / 1_000_000) * model_costs["output"]

        return input_cost + output_cost

    def get_summary(self) -> UsageSummary:
        """Get aggregated usage summary."""
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
                        "tokens": 0, "cost_usd": 0.0, "requests": 0
                    }
                summary.by_provider[pkey]["tokens"] += record.prompt_tokens + record.completion_tokens
                summary.by_provider[pkey]["cost_usd"] += record.cost_usd
                summary.by_provider[pkey]["requests"] += 1

                # By model
                mkey = f"{record.provider.value}:{record.model}"
                if mkey not in summary.by_model:
                    summary.by_model[mkey] = {
                        "tokens": 0, "cost_usd": 0.0, "requests": 0
                    }
                summary.by_model[mkey]["tokens"] += record.prompt_tokens + record.completion_tokens
                summary.by_model[mkey]["cost_usd"] += record.cost_usd
                summary.by_model[mkey]["requests"] += 1

        return summary

    def format_report(self) -> str:
        """Format usage report as human-readable string."""
        summary = self.get_summary()

        lines = [
            "=" * 60,
            "LLM Usage Report",
            "=" * 60,
            f"Session started: {self._session_start.isoformat()}",
            f"Total requests: {summary.request_count}",
            f"Total tokens: {summary.total_tokens:,}",
            f"  - Prompt: {summary.total_prompt_tokens:,}",
            f"  - Completion: {summary.total_completion_tokens:,}",
            f"Estimated cost: ${summary.total_cost_usd:.4f}",
            "",
            "By Provider:",
        ]

        for provider, stats in summary.by_provider.items():
            lines.append(f"  {provider}: {stats['requests']} requests, "
                        f"{stats['tokens']:,} tokens, ${stats['cost_usd']:.4f}")

        if summary.by_model:
            lines.append("")
            lines.append("By Model:")
            for model, stats in summary.by_model.items():
                lines.append(f"  {model}: {stats['requests']} requests, "
                            f"{stats['tokens']:,} tokens, ${stats['cost_usd']:.4f}")

        lines.append("=" * 60)
        return "\n".join(lines)

    def reset(self):
        """Reset all tracking data."""
        with self._lock:
            self._records.clear()
            self._session_start = datetime.now()

# Global tracker instance
_global_tracker: Optional[TokenTracker] = None
_tracker_lock = threading.Lock()

def get_token_tracker() -> TokenTracker:
    """Get or create the global token tracker."""
    global _global_tracker
    with _tracker_lock:
        if _global_tracker is None:
            _global_tracker = TokenTracker()
        return _global_tracker
```

## Phase 2: Provider Implementations

### 2.1 Base Provider (`providers/base.py`)

```python
from abc import ABC, abstractmethod
from typing import Optional
from ..data_types import (
    LLMMessage, LLMResponse, EmbeddingResponse,
    GenerationParams, Provider
)

class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.

    Each provider implementation handles:
    - Client initialization and connection management
    - Request formatting for the specific API
    - Response parsing into unified format
    - Error handling and retries
    """

    @property
    @abstractmethod
    def provider_type(self) -> Provider:
        """Return the provider enum value."""
        pass

    @abstractmethod
    def chat(
        self,
        messages: list[LLMMessage],
        model: str,
        params: GenerationParams,
        system_prompt: Optional[str] = None
    ) -> LLMResponse:
        """
        Send a chat completion request.

        Args:
            messages: Conversation history
            model: Model name (without provider prefix)
            params: Generation parameters
            system_prompt: Optional system message

        Returns:
            Unified LLMResponse
        """
        pass

    @abstractmethod
    def generate(
        self,
        prompt: str,
        model: str,
        params: GenerationParams
    ) -> LLMResponse:
        """
        Send a simple text generation request.

        Args:
            prompt: Text prompt
            model: Model name (without provider prefix)
            params: Generation parameters

        Returns:
            Unified LLMResponse
        """
        pass

    @abstractmethod
    def embed(
        self,
        text: str,
        model: str
    ) -> EmbeddingResponse:
        """
        Generate embeddings for text.

        Args:
            text: Text to embed
            model: Embedding model name

        Returns:
            Unified EmbeddingResponse
        """
        pass

    @abstractmethod
    def test_connection(self) -> bool:
        """
        Test if the provider is available.

        Returns:
            True if connection is healthy
        """
        pass

    @abstractmethod
    def list_models(self) -> list[str]:
        """
        List available models.

        Returns:
            List of model names
        """
        pass
```

### 2.2 Ollama Provider (`providers/ollama_provider.py`)

```python
import os
import time
import logging
from typing import Optional

import ollama

from .base import LLMProvider
from ..data_types import (
    LLMMessage, LLMResponse, EmbeddingResponse,
    GenerationParams, Provider
)

logger = logging.getLogger(__name__)

class OllamaProvider(LLMProvider):
    """
    Ollama provider implementation.

    Uses the official ollama Python library for local LLM inference.
    """

    DEFAULT_HOST = "http://localhost:11434"
    DEFAULT_EMBEDDING_MODEL = "snowflake-arctic-embed2:latest"

    def __init__(
        self,
        host: Optional[str] = None,
        timeout: float = 120.0
    ):
        """
        Initialize Ollama provider.

        Args:
            host: Ollama server URL (default: http://localhost:11434)
            timeout: Request timeout in seconds
        """
        self.host = host or os.environ.get("OLLAMA_HOST", self.DEFAULT_HOST)
        self.timeout = timeout
        self._client: Optional[ollama.Client] = None

    @property
    def provider_type(self) -> Provider:
        return Provider.OLLAMA

    @property
    def client(self) -> ollama.Client:
        """Lazy initialization of Ollama client."""
        if self._client is None:
            self._client = ollama.Client(host=self.host)
        return self._client

    def chat(
        self,
        messages: list[LLMMessage],
        model: str,
        params: GenerationParams,
        system_prompt: Optional[str] = None
    ) -> LLMResponse:
        """Send chat completion to Ollama."""
        start_time = time.perf_counter()

        # Build message list
        ollama_messages = []
        if system_prompt:
            ollama_messages.append({"role": "system", "content": system_prompt})

        for msg in messages:
            ollama_messages.append({"role": msg.role, "content": msg.content})

        # Build options
        options = {
            "temperature": params.temperature,
            "top_p": params.top_p,
        }
        if params.max_tokens:
            options["num_predict"] = params.max_tokens
        if params.stop_sequences:
            options["stop"] = params.stop_sequences

        # Make request
        format_opt = "json" if params.json_mode else None

        response = self.client.chat(
            model=model,
            messages=ollama_messages,
            options=options,
            format=format_opt
        )

        duration = time.perf_counter() - start_time

        # Extract token counts from response
        prompt_tokens = response.get("prompt_eval_count", 0)
        completion_tokens = response.get("eval_count", 0)

        return LLMResponse(
            content=response["message"]["content"],
            model=model,
            provider=Provider.OLLAMA,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            duration_seconds=duration,
            raw_response=response
        )

    def generate(
        self,
        prompt: str,
        model: str,
        params: GenerationParams
    ) -> LLMResponse:
        """Send text generation to Ollama."""
        start_time = time.perf_counter()

        options = {
            "temperature": params.temperature,
            "top_p": params.top_p,
        }
        if params.max_tokens:
            options["num_predict"] = params.max_tokens
        if params.stop_sequences:
            options["stop"] = params.stop_sequences

        format_opt = "json" if params.json_mode else None

        response = self.client.generate(
            model=model,
            prompt=prompt,
            options=options,
            format=format_opt
        )

        duration = time.perf_counter() - start_time

        prompt_tokens = response.get("prompt_eval_count", 0)
        completion_tokens = response.get("eval_count", 0)

        return LLMResponse(
            content=response["response"],
            model=model,
            provider=Provider.OLLAMA,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            duration_seconds=duration,
            raw_response=response
        )

    def embed(
        self,
        text: str,
        model: Optional[str] = None
    ) -> EmbeddingResponse:
        """Generate embeddings using Ollama."""
        model = model or self.DEFAULT_EMBEDDING_MODEL

        response = self.client.embeddings(
            model=model,
            prompt=text
        )

        embedding = response["embedding"]

        return EmbeddingResponse(
            embedding=embedding,
            model=model,
            provider=Provider.OLLAMA,
            dimensions=len(embedding),
            prompt_tokens=response.get("prompt_eval_count", 0)
        )

    def test_connection(self) -> bool:
        """Test Ollama server connectivity."""
        try:
            self.client.list()
            return True
        except Exception as e:
            logger.warning(f"Ollama connection test failed: {e}")
            return False

    def list_models(self) -> list[str]:
        """List available Ollama models."""
        try:
            response = self.client.list()
            return [m["name"] for m in response.get("models", [])]
        except Exception:
            return []
```

### 2.3 Anthropic Provider (`providers/anthropic_provider.py`)

```python
import os
import time
import logging
from typing import Optional

from .base import LLMProvider
from ..data_types import (
    LLMMessage, LLMResponse, EmbeddingResponse,
    GenerationParams, Provider
)

logger = logging.getLogger(__name__)

class AnthropicProvider(LLMProvider):
    """
    Anthropic Claude provider implementation.

    Uses the anthropic Python SDK.
    """

    DEFAULT_MAX_TOKENS = 4096

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: float = 120.0
    ):
        """
        Initialize Anthropic provider.

        Args:
            api_key: API key (default: from ANTHROPIC_API_KEY env var)
            timeout: Request timeout in seconds
        """
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.timeout = timeout
        self._client = None

        if not self.api_key:
            logger.warning("ANTHROPIC_API_KEY not set - Anthropic provider unavailable")

    @property
    def provider_type(self) -> Provider:
        return Provider.ANTHROPIC

    @property
    def client(self):
        """Lazy initialization of Anthropic client."""
        if self._client is None:
            try:
                import anthropic
                self._client = anthropic.Anthropic(
                    api_key=self.api_key,
                    timeout=self.timeout
                )
            except ImportError:
                raise ImportError(
                    "anthropic package not installed. "
                    "Install with: uv add anthropic"
                )
        return self._client

    def chat(
        self,
        messages: list[LLMMessage],
        model: str,
        params: GenerationParams,
        system_prompt: Optional[str] = None
    ) -> LLMResponse:
        """Send chat completion to Anthropic."""
        start_time = time.perf_counter()

        # Build message list (Anthropic format)
        anthropic_messages = []
        for msg in messages:
            anthropic_messages.append({
                "role": msg.role if msg.role != "system" else "user",
                "content": msg.content
            })

        # Make request
        max_tokens = params.max_tokens or self.DEFAULT_MAX_TOKENS

        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": anthropic_messages,
            "temperature": params.temperature,
            "top_p": params.top_p,
        }

        if system_prompt:
            kwargs["system"] = system_prompt

        if params.stop_sequences:
            kwargs["stop_sequences"] = params.stop_sequences

        response = self.client.messages.create(**kwargs)

        duration = time.perf_counter() - start_time

        # Extract content
        content = ""
        for block in response.content:
            if hasattr(block, "text"):
                content += block.text

        return LLMResponse(
            content=content,
            model=model,
            provider=Provider.ANTHROPIC,
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
            total_tokens=response.usage.input_tokens + response.usage.output_tokens,
            duration_seconds=duration,
            raw_response=response.model_dump() if hasattr(response, "model_dump") else None
        )

    def generate(
        self,
        prompt: str,
        model: str,
        params: GenerationParams
    ) -> LLMResponse:
        """
        Send text generation to Anthropic.

        Anthropic doesn't have a separate generate endpoint,
        so we wrap the prompt in a chat message.
        """
        messages = [LLMMessage(role="user", content=prompt)]
        return self.chat(messages, model, params)

    def embed(
        self,
        text: str,
        model: Optional[str] = None
    ) -> EmbeddingResponse:
        """
        Generate embeddings.

        NOTE: Anthropic does not provide embedding models.
        This will fall back to Ollama for embeddings.
        """
        raise NotImplementedError(
            "Anthropic does not provide embedding models. "
            "Use Ollama or OpenAI for embeddings."
        )

    def test_connection(self) -> bool:
        """Test Anthropic API connectivity."""
        if not self.api_key:
            return False
        try:
            # Minimal API call to verify key
            self.client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=1,
                messages=[{"role": "user", "content": "Hi"}]
            )
            return True
        except Exception as e:
            logger.warning(f"Anthropic connection test failed: {e}")
            return False

    def list_models(self) -> list[str]:
        """List available Anthropic models."""
        # Anthropic doesn't have a list endpoint, return known models
        return [
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307",
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
        ]
```

### 2.4 Provider Registry (`providers/__init__.py`)

```python
import threading
from typing import Optional
from ..data_types import Provider

# Provider instances (singleton pattern)
_providers: dict[Provider, "LLMProvider"] = {}
_lock = threading.Lock()

def get_provider(provider_type: Provider, **kwargs) -> "LLMProvider":
    """
    Get or create a provider instance.

    Uses singleton pattern - one instance per provider type.

    Args:
        provider_type: Which provider to get
        **kwargs: Provider-specific configuration

    Returns:
        Provider instance
    """
    with _lock:
        if provider_type not in _providers:
            _providers[provider_type] = _create_provider(provider_type, **kwargs)
        return _providers[provider_type]

def _create_provider(provider_type: Provider, **kwargs) -> "LLMProvider":
    """Create a new provider instance."""
    if provider_type == Provider.OLLAMA:
        from .ollama_provider import OllamaProvider
        return OllamaProvider(**kwargs)

    elif provider_type == Provider.ANTHROPIC:
        from .anthropic_provider import AnthropicProvider
        return AnthropicProvider(**kwargs)

    elif provider_type == Provider.OPENAI:
        from .openai_provider import OpenAIProvider
        return OpenAIProvider(**kwargs)

    else:
        raise ValueError(f"Unknown provider: {provider_type}")

def reset_providers():
    """Reset all provider instances (for testing)."""
    global _providers
    with _lock:
        _providers.clear()
```

## Phase 3: Unified Client

### 3.1 LLM Client (`client.py`)

```python
import logging
import time
from typing import Optional, Callable

from .data_types import (
    LLMMessage, LLMResponse, EmbeddingResponse,
    GenerationParams, Provider, ModelSpec
)
from .model_resolver import parse_model_string
from .token_tracker import get_token_tracker
from .providers import get_provider
from .providers.base import LLMProvider

logger = logging.getLogger(__name__)

class LLMClient:
    """
    Unified LLM client supporting multiple providers.

    Provides a simple interface for chat, generation, and embeddings
    with automatic provider selection based on model string prefix.

    Example:
        client = LLMClient()

        # Ollama (default)
        response = client.chat(messages, model="medgemma-27b")

        # Anthropic
        response = client.chat(messages, model="anthropic:claude-3-opus")

        # With fallback to Ollama
        response = client.chat(messages, model="anthropic:claude-3-opus",
                               fallback_model="medgemma-27b")
    """

    def __init__(
        self,
        default_provider: Provider = Provider.OLLAMA,
        fallback_provider: Provider = Provider.OLLAMA,
        fallback_model: Optional[str] = None,
        track_usage: bool = True,
        ollama_host: Optional[str] = None
    ):
        """
        Initialize LLM client.

        Args:
            default_provider: Provider for unprefixed model names
            fallback_provider: Provider to use on primary failure (always Ollama)
            fallback_model: Model to use on fallback
            track_usage: Whether to track token usage
            ollama_host: Ollama server URL
        """
        self.default_provider = default_provider
        self.fallback_provider = fallback_provider
        self.fallback_model = fallback_model
        self.track_usage = track_usage
        self.ollama_host = ollama_host

        self._token_tracker = get_token_tracker() if track_usage else None

    def _get_provider(self, provider_type: Provider) -> LLMProvider:
        """Get provider instance with configuration."""
        kwargs = {}
        if provider_type == Provider.OLLAMA and self.ollama_host:
            kwargs["host"] = self.ollama_host
        return get_provider(provider_type, **kwargs)

    def _record_usage(self, response: LLMResponse, operation: str = "chat"):
        """Record token usage for cost tracking."""
        if self._token_tracker:
            self._token_tracker.record_usage(
                provider=response.provider,
                model=response.model,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                operation=operation
            )

    def chat(
        self,
        messages: list[LLMMessage],
        model: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        top_p: float = 0.9,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
        fallback_model: Optional[str] = None,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ) -> LLMResponse:
        """
        Send a chat completion request.

        Args:
            messages: Conversation history
            model: Model name with optional provider prefix
            system_prompt: Optional system message
            temperature: Sampling temperature
            top_p: Top-p sampling
            max_tokens: Maximum tokens to generate
            json_mode: Request JSON output
            fallback_model: Model to use on failure (Ollama)
            max_retries: Number of retry attempts
            retry_delay: Initial retry delay (exponential backoff)

        Returns:
            LLMResponse with generated content
        """
        spec = parse_model_string(model)
        params = GenerationParams(
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            json_mode=json_mode
        )

        # Try primary provider
        try:
            provider = self._get_provider(spec.provider)
            response = self._chat_with_retry(
                provider, messages, spec.model_name, params,
                system_prompt, max_retries, retry_delay
            )
            self._record_usage(response, "chat")
            return response

        except Exception as e:
            logger.warning(f"Primary provider {spec.provider.value} failed: {e}")

            # Fallback to Ollama
            fb_model = fallback_model or self.fallback_model
            if fb_model and spec.provider != self.fallback_provider:
                logger.info(f"Falling back to {self.fallback_provider.value}:{fb_model}")
                try:
                    fallback = self._get_provider(self.fallback_provider)
                    response = self._chat_with_retry(
                        fallback, messages, fb_model, params,
                        system_prompt, max_retries, retry_delay
                    )
                    self._record_usage(response, "chat")
                    return response
                except Exception as fb_error:
                    logger.error(f"Fallback also failed: {fb_error}")

            raise

    def _chat_with_retry(
        self,
        provider: LLMProvider,
        messages: list[LLMMessage],
        model: str,
        params: GenerationParams,
        system_prompt: Optional[str],
        max_retries: int,
        retry_delay: float
    ) -> LLMResponse:
        """Execute chat with retry logic."""
        last_error = None
        current_delay = retry_delay

        for attempt in range(max_retries):
            try:
                return provider.chat(messages, model, params, system_prompt)
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Attempt {attempt + 1}/{max_retries} failed: {e}. "
                        f"Retrying in {current_delay:.1f}s..."
                    )
                    time.sleep(current_delay)
                    current_delay *= 2  # Exponential backoff

        raise last_error

    def generate(
        self,
        prompt: str,
        model: str,
        temperature: float = 0.7,
        top_p: float = 0.9,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
        fallback_model: Optional[str] = None,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ) -> LLMResponse:
        """
        Send a text generation request.

        Args:
            prompt: Text prompt
            model: Model name with optional provider prefix
            temperature: Sampling temperature
            top_p: Top-p sampling
            max_tokens: Maximum tokens to generate
            json_mode: Request JSON output
            fallback_model: Model to use on failure (Ollama)
            max_retries: Number of retry attempts
            retry_delay: Initial retry delay

        Returns:
            LLMResponse with generated content
        """
        spec = parse_model_string(model)
        params = GenerationParams(
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            json_mode=json_mode
        )

        try:
            provider = self._get_provider(spec.provider)

            last_error = None
            current_delay = retry_delay

            for attempt in range(max_retries):
                try:
                    response = provider.generate(prompt, spec.model_name, params)
                    self._record_usage(response, "generate")
                    return response
                except Exception as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        time.sleep(current_delay)
                        current_delay *= 2

            raise last_error

        except Exception as e:
            logger.warning(f"Primary provider failed: {e}")

            fb_model = fallback_model or self.fallback_model
            if fb_model and spec.provider != self.fallback_provider:
                logger.info(f"Falling back to Ollama:{fb_model}")
                fallback = self._get_provider(self.fallback_provider)
                response = fallback.generate(prompt, fb_model, params)
                self._record_usage(response, "generate")
                return response

            raise

    def embed(
        self,
        text: str,
        model: str = "snowflake-arctic-embed2:latest"
    ) -> EmbeddingResponse:
        """
        Generate embeddings for text.

        NOTE: Embeddings always use Ollama (local).
        Anthropic doesn't provide embeddings, and using
        OpenAI for embeddings would affect pgvector compatibility.

        Args:
            text: Text to embed
            model: Embedding model (Ollama only)

        Returns:
            EmbeddingResponse with embedding vector
        """
        # Always use Ollama for embeddings (consistency + free)
        provider = self._get_provider(Provider.OLLAMA)
        response = provider.embed(text, model)

        if self._token_tracker:
            self._token_tracker.record_usage(
                provider=Provider.OLLAMA,
                model=model,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=0,
                operation="embed"
            )

        return response

    def get_usage_report(self) -> str:
        """Get formatted token usage report."""
        if self._token_tracker:
            return self._token_tracker.format_report()
        return "Usage tracking disabled"

    def test_provider(self, provider_type: Provider) -> bool:
        """Test if a provider is available."""
        try:
            provider = self._get_provider(provider_type)
            return provider.test_connection()
        except Exception:
            return False

# Convenience function
def get_llm_client(**kwargs) -> LLMClient:
    """Get a configured LLM client instance."""
    from ..config import get_ollama_host

    if "ollama_host" not in kwargs:
        kwargs["ollama_host"] = get_ollama_host()

    return LLMClient(**kwargs)
```

## Phase 4: BaseAgent Integration

### 4.1 Modify BaseAgent

Changes to `src/bmlibrarian/agents/base.py`:

```python
# Add import at top
from bmlibrarian.llm import LLMClient, get_llm_client, LLMMessage

class BaseAgent(ABC):
    def __init__(
        self,
        model: str = "medgemma4B_it_q8:latest",
        host: str = "http://localhost:11434",
        temperature: float = 0.7,
        top_p: float = 0.9,
        # ... existing parameters ...
        fallback_model: Optional[str] = None,  # NEW
    ):
        # Replace ollama.Client with LLMClient
        self._llm_client = get_llm_client(
            ollama_host=host,
            fallback_model=fallback_model or "medgemma4B_it_q8:latest"
        )

        # Keep model for backward compatibility
        self.model = model
        self.temperature = temperature
        self.top_p = top_p
        # ... rest of init ...

    def _make_ollama_request(
        self,
        messages: list,
        system_prompt: Optional[str] = None,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ) -> str:
        """
        Make LLM request (renamed internally but API preserved).

        Now routes through LLMClient with provider abstraction.
        """
        # Convert to LLMMessage format
        llm_messages = [
            LLMMessage(role=m["role"], content=m["content"])
            for m in messages
        ]

        response = self._llm_client.chat(
            messages=llm_messages,
            model=self.model,
            system_prompt=system_prompt,
            temperature=self.temperature,
            top_p=self.top_p,
            max_retries=max_retries,
            retry_delay=retry_delay
        )

        # Update metrics
        self._update_metrics(response)

        return response.content

    def _generate_from_prompt(
        self,
        prompt: str,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ) -> str:
        """Generate from prompt using LLMClient."""
        response = self._llm_client.generate(
            prompt=prompt,
            model=self.model,
            temperature=self.temperature,
            top_p=self.top_p,
            max_retries=max_retries,
            retry_delay=retry_delay
        )

        self._update_metrics(response)
        return response.content

    def _generate_embedding(
        self,
        text: str,
        model: Optional[str] = None
    ) -> list[float]:
        """Generate embeddings using LLMClient."""
        response = self._llm_client.embed(
            text=text,
            model=model or "snowflake-arctic-embed2:latest"
        )
        return response.embedding

    def _update_metrics(self, response: "LLMResponse"):
        """Update performance metrics from response."""
        self._metrics.total_prompt_tokens += response.prompt_tokens
        self._metrics.total_completion_tokens += response.completion_tokens
        self._metrics.total_tokens += response.total_tokens
        self._metrics.total_requests += 1
        self._metrics.total_wall_time_seconds += response.duration_seconds
```

## Phase 5: Configuration Updates

### 5.1 Config Schema Extension

Add to `~/.bmlibrarian/config.json`:

```json
{
  "llm": {
    "default_provider": "ollama",
    "fallback_model": "medgemma4B_it_q8:latest",
    "track_usage": true,
    "providers": {
      "anthropic": {
        "api_key_env": "ANTHROPIC_API_KEY",
        "default_max_tokens": 4096
      },
      "openai": {
        "api_key_env": "OPENAI_API_KEY"
      }
    }
  },
  "models": {
    "query_agent": "ollama:medgemma-27b-text-it-Q8_0:latest",
    "scoring_agent": "anthropic:claude-3-haiku",
    "citation_agent": "ollama:gpt-oss:20b"
  }
}
```

### 5.2 Config Module Updates

Add to `src/bmlibrarian/config.py`:

```python
def get_llm_config() -> dict:
    """Get LLM client configuration."""
    return get_config().get("llm", {
        "default_provider": "ollama",
        "fallback_model": "medgemma4B_it_q8:latest",
        "track_usage": True
    })
```

## Implementation Order

### Week 1: Core Infrastructure
1. Create `src/bmlibrarian/llm/` directory structure
2. Implement `data_types.py` with all dataclasses
3. Implement `model_resolver.py` with tests
4. Implement `token_tracker.py` with tests

### Week 2: Provider Implementations
1. Implement `providers/base.py` (ABC)
2. Implement `providers/ollama_provider.py` with full test coverage
3. Implement `providers/anthropic_provider.py`
4. Implement provider registry

### Week 3: Client and Integration
1. Implement `client.py` (LLMClient)
2. Add comprehensive tests for fallback scenarios
3. Update `BaseAgent` to use `LLMClient`
4. Update configuration schema

### Week 4: Migration and Testing
1. Update PaperChecker components to use shared client
2. Update any remaining direct `ollama` imports
3. Full integration testing
4. Documentation updates

## Testing Strategy

### Unit Tests
- Model string parsing (all formats)
- Token tracking accuracy
- Cost calculation correctness
- Provider-specific response parsing

### Integration Tests
- Ollama provider with real server
- Fallback from Anthropic to Ollama
- Multi-provider workflow
- Token tracking across providers

### Compatibility Tests
- Existing agent tests pass unchanged
- CLI behavior unchanged
- GUI behavior unchanged

## Backward Compatibility

All changes are backward compatible:
- Existing model strings work (`medgemma-27b` → Ollama)
- Existing agent instantiation works
- Existing configuration works
- No changes to public APIs

## Future Extensions

Ready to add without architecture changes:
- OpenAI provider
- Azure OpenAI provider
- Local vLLM provider
- Streaming support
- Tool/function calling abstraction
