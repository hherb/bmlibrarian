"""
Unified LLM client supporting multiple providers.

This module provides a high-level interface for interacting with LLMs,
handling provider selection, fallback logic, retries, and usage tracking.

Usage:
    from bmlibrarian.llm import LLMClient, LLMMessage

    client = LLMClient()

    # Ollama (default)
    response = client.chat([LLMMessage("user", "Hello")], model="medgemma-27b")

    # Anthropic
    response = client.chat([LLMMessage("user", "Hello")], model="anthropic:claude-3-opus")

    # With fallback
    response = client.chat(
        [LLMMessage("user", "Hello")],
        model="anthropic:claude-3-opus",
        fallback_model="medgemma-27b"
    )
"""

import logging
import time
from typing import Optional, Any

from .data_types import (
    LLMMessage,
    LLMResponse,
    EmbeddingResponse,
    GenerationParams,
    Provider,
)
from .model_resolver import parse_model_string
from .token_tracker import get_token_tracker, TokenTracker
from .providers import get_provider
from .providers.base import LLMProvider
from .constants import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_DELAY,
)

logger = logging.getLogger(__name__)


class LLMClient:
    """
    Unified LLM client supporting multiple providers.

    Provides a simple interface for chat, generation, and embeddings
    with automatic provider selection based on model string prefix.

    Features:
        - Automatic provider selection from model string
        - Fallback to Ollama on external provider failure
        - Token usage tracking for cost estimation
        - Retry logic with exponential backoff
        - Thread-safe design

    Attributes:
        default_provider: Provider for unprefixed model names
        fallback_provider: Provider to use on primary failure
        fallback_model: Model to use on fallback
        track_usage: Whether to track token usage
        ollama_host: Ollama server URL
    """

    def __init__(
        self,
        default_provider: Provider = Provider.OLLAMA,
        fallback_provider: Provider = Provider.OLLAMA,
        fallback_model: Optional[str] = None,
        track_usage: bool = True,
        ollama_host: Optional[str] = None,
    ) -> None:
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

        self._token_tracker: Optional[TokenTracker] = (
            get_token_tracker() if track_usage else None
        )

    def _get_provider(self, provider_type: Provider) -> LLMProvider:
        """
        Get provider instance with configuration.

        Args:
            provider_type: Which provider to get

        Returns:
            Configured provider instance
        """
        kwargs: dict[str, Any] = {}
        if provider_type == Provider.OLLAMA and self.ollama_host:
            kwargs["host"] = self.ollama_host
        return get_provider(provider_type, **kwargs)

    def _record_usage(
        self,
        response: LLMResponse,
        operation: str = "chat",
    ) -> None:
        """
        Record token usage for cost tracking.

        Args:
            response: LLM response with token counts
            operation: Type of operation
        """
        if self._token_tracker:
            self._token_tracker.record_usage(
                provider=response.provider,
                model=response.model,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                operation=operation,
            )

    def chat(
        self,
        messages: list[LLMMessage],
        model: str,
        system_prompt: Optional[str] = None,
        temperature: float = DEFAULT_TEMPERATURE,
        top_p: float = DEFAULT_TOP_P,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
        fallback_model: Optional[str] = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_delay: float = DEFAULT_RETRY_DELAY,
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

        Raises:
            ConnectionError: If all providers fail
        """
        spec = parse_model_string(model)
        params = GenerationParams(
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            json_mode=json_mode,
        )

        # Try primary provider
        try:
            provider = self._get_provider(spec.provider)
            response = self._chat_with_retry(
                provider,
                messages,
                spec.model_name,
                params,
                system_prompt,
                max_retries,
                retry_delay,
            )
            self._record_usage(response, "chat")
            return response

        except Exception as e:
            logger.warning(f"Primary provider {spec.provider.value} failed: {e}")

            # Fallback to Ollama
            fb_model = fallback_model or self.fallback_model
            if fb_model and spec.provider != self.fallback_provider:
                logger.info(
                    f"Falling back to {self.fallback_provider.value}:{fb_model}"
                )
                try:
                    fallback = self._get_provider(self.fallback_provider)
                    response = self._chat_with_retry(
                        fallback,
                        messages,
                        fb_model,
                        params,
                        system_prompt,
                        max_retries,
                        retry_delay,
                    )
                    self._record_usage(response, "chat")
                    return response
                except Exception as fb_error:
                    logger.error(f"Fallback also failed: {fb_error}")
                    raise ConnectionError(
                        f"All providers failed. Primary: {e}, Fallback: {fb_error}"
                    ) from fb_error

            raise

    def _chat_with_retry(
        self,
        provider: LLMProvider,
        messages: list[LLMMessage],
        model: str,
        params: GenerationParams,
        system_prompt: Optional[str],
        max_retries: int,
        retry_delay: float,
    ) -> LLMResponse:
        """
        Execute chat with retry logic.

        Args:
            provider: Provider instance
            messages: Chat messages
            model: Model name
            params: Generation parameters
            system_prompt: System prompt
            max_retries: Maximum retry attempts
            retry_delay: Initial delay between retries

        Returns:
            LLMResponse from successful call

        Raises:
            Exception: Last error if all retries fail
        """
        last_error: Optional[Exception] = None
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

        if last_error:
            raise last_error
        raise RuntimeError("Unexpected state: no error but no response")

    def generate(
        self,
        prompt: str,
        model: str,
        temperature: float = DEFAULT_TEMPERATURE,
        top_p: float = DEFAULT_TOP_P,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
        fallback_model: Optional[str] = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_delay: float = DEFAULT_RETRY_DELAY,
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

        Raises:
            ConnectionError: If all providers fail
        """
        spec = parse_model_string(model)
        params = GenerationParams(
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            json_mode=json_mode,
        )

        try:
            provider = self._get_provider(spec.provider)
            response = self._generate_with_retry(
                provider,
                prompt,
                spec.model_name,
                params,
                max_retries,
                retry_delay,
            )
            self._record_usage(response, "generate")
            return response

        except Exception as e:
            logger.warning(f"Primary provider failed: {e}")

            fb_model = fallback_model or self.fallback_model
            if fb_model and spec.provider != self.fallback_provider:
                logger.info(f"Falling back to Ollama:{fb_model}")
                try:
                    fallback = self._get_provider(self.fallback_provider)
                    response = self._generate_with_retry(
                        fallback,
                        prompt,
                        fb_model,
                        params,
                        max_retries,
                        retry_delay,
                    )
                    self._record_usage(response, "generate")
                    return response
                except Exception as fb_error:
                    logger.error(f"Fallback also failed: {fb_error}")
                    raise ConnectionError(
                        f"All providers failed. Primary: {e}, Fallback: {fb_error}"
                    ) from fb_error

            raise

    def _generate_with_retry(
        self,
        provider: LLMProvider,
        prompt: str,
        model: str,
        params: GenerationParams,
        max_retries: int,
        retry_delay: float,
    ) -> LLMResponse:
        """
        Execute generation with retry logic.

        Args:
            provider: Provider instance
            prompt: Text prompt
            model: Model name
            params: Generation parameters
            max_retries: Maximum retry attempts
            retry_delay: Initial delay between retries

        Returns:
            LLMResponse from successful call
        """
        last_error: Optional[Exception] = None
        current_delay = retry_delay

        for attempt in range(max_retries):
            try:
                return provider.generate(prompt, model, params)
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Attempt {attempt + 1}/{max_retries} failed: {e}. "
                        f"Retrying in {current_delay:.1f}s..."
                    )
                    time.sleep(current_delay)
                    current_delay *= 2

        if last_error:
            raise last_error
        raise RuntimeError("Unexpected state: no error but no response")

    def embed(
        self,
        text: str,
        model: str = DEFAULT_EMBEDDING_MODEL,
    ) -> EmbeddingResponse:
        """
        Generate embeddings for text.

        Note: Embeddings always use Ollama (local) for consistency
        with pgvector dimensions and to avoid costs.

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
                operation="embed",
            )

        return response

    def get_usage_report(self) -> str:
        """
        Get formatted token usage report.

        Returns:
            Human-readable usage report string
        """
        if self._token_tracker:
            return self._token_tracker.format_report()
        return "Usage tracking disabled"

    def get_usage_summary(self) -> Optional[dict[str, Any]]:
        """
        Get usage summary as dictionary.

        Returns:
            Dictionary with usage statistics, or None if tracking disabled
        """
        if self._token_tracker:
            summary = self._token_tracker.get_summary()
            return {
                "total_tokens": summary.total_tokens,
                "total_prompt_tokens": summary.total_prompt_tokens,
                "total_completion_tokens": summary.total_completion_tokens,
                "total_cost_usd": summary.total_cost_usd,
                "request_count": summary.request_count,
                "by_provider": summary.by_provider,
                "by_model": summary.by_model,
            }
        return None

    def test_provider(self, provider_type: Provider) -> bool:
        """
        Test if a provider is available.

        Args:
            provider_type: Provider to test

        Returns:
            True if provider is available and connected
        """
        try:
            provider = self._get_provider(provider_type)
            return provider.test_connection()
        except Exception:
            return False

    def list_models(self, provider_type: Optional[Provider] = None) -> dict[str, list[str]]:
        """
        List available models.

        Args:
            provider_type: Specific provider to query, or None for all

        Returns:
            Dictionary mapping provider names to model lists
        """
        result: dict[str, list[str]] = {}

        providers_to_check = (
            [provider_type] if provider_type else list(Provider)
        )

        for ptype in providers_to_check:
            try:
                provider = self._get_provider(ptype)
                result[ptype.value] = provider.list_models()
            except Exception as e:
                logger.debug(f"Could not list models for {ptype.value}: {e}")
                result[ptype.value] = []

        return result


def get_llm_client(**kwargs: Any) -> LLMClient:
    """
    Get a configured LLM client instance.

    Convenience function that configures the client using
    BMLibrarian's configuration system.

    Args:
        **kwargs: Override default configuration

    Returns:
        Configured LLMClient instance
    """
    # Import here to avoid circular imports
    try:
        from ..config import get_ollama_host

        if "ollama_host" not in kwargs:
            kwargs["ollama_host"] = get_ollama_host()
    except ImportError:
        pass  # Config not available, use defaults

    return LLMClient(**kwargs)


def list_ollama_models(host: Optional[str] = None) -> list[str]:
    """
    List available Ollama models.

    Centralized utility function for listing Ollama models that handles
    both old and new Ollama library API formats.

    Args:
        host: Ollama server URL. If None, uses configured default.

    Returns:
        List of model names available on the server.
        Returns empty list on connection failure.

    Examples:
        >>> models = list_ollama_models()
        >>> print(models[:3])
        ['gpt-oss:20b', 'medgemma4B_it_q8:latest', 'qwen3:8b']

        >>> models = list_ollama_models("http://192.168.1.100:11434")
    """
    import ollama

    try:
        # Get configured host if not provided
        if host is None:
            try:
                from ..config import get_ollama_host
                host = get_ollama_host()
            except ImportError:
                host = DEFAULT_OLLAMA_HOST

        client = ollama.Client(host=host)
        response = client.list()

        # Ollama library >= 0.4.0 uses ListResponse with .models attribute
        # containing Model objects with .model attribute
        if hasattr(response, 'models'):
            return [m.model for m in response.models]

        # Fallback for older ollama library versions (dict-based response)
        if isinstance(response, dict) and 'models' in response:
            return [m["name"] for m in response.get("models", [])]

        logger.warning("Unexpected Ollama list response format")
        return []

    except Exception as e:
        logger.warning(f"Failed to list Ollama models: {e}")
        return []
