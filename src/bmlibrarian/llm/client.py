"""
Unified LLM client supporting multiple providers.

This module provides a high-level interface for interacting with LLMs,
handling provider selection, fallback logic, retries, and usage tracking.

Internally delegates to bmlib.llm.LLMClient for actual provider communication.

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

from bmlib.llm import LLMClient as BmlibLLMClient
from bmlib.llm import LLMMessage
from bmlib.llm import EmbeddingResponse as BmlibEmbeddingResponse

from .data_types import (
    LLMResponse,
    EmbeddingResponse,
    Provider,
)
from .model_resolver import parse_model_string
from .token_tracker import get_token_tracker, TokenTracker
from .constants import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_OLLAMA_HOST,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_DELAY,
)

logger = logging.getLogger(__name__)


class LLMClient:
    """
    Unified LLM client supporting multiple providers.

    Wraps bmlib.llm.LLMClient and adds bmlibrarian-specific features:
    - Provider enum integration
    - Retry logic with exponential backoff
    - Fallback to Ollama on external provider failure
    - Token usage tracking with Provider-aware cost estimation
    - System prompt handling

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

        # Create the underlying bmlib client
        self._bmlib = BmlibLLMClient(
            default_provider=default_provider.value,
            ollama_host=ollama_host,
        )

        self._token_tracker: Optional[TokenTracker] = (
            get_token_tracker() if track_usage else None
        )

    def _adapt_response(
        self,
        bmlib_resp: Any,
        model_str: str,
        start_time: float,
    ) -> LLMResponse:
        """
        Convert a bmlib LLMResponse to bmlibrarian's LLMResponse format.

        Args:
            bmlib_resp: Response from bmlib.llm.LLMClient
            model_str: Original model string for provider resolution
            start_time: Wall-clock start time for duration calculation

        Returns:
            bmlibrarian LLMResponse with Provider enum and field name mapping
        """
        spec = parse_model_string(model_str)
        duration = time.time() - start_time

        return LLMResponse(
            content=bmlib_resp.content,
            model=bmlib_resp.model or spec.model_name,
            provider=spec.provider,
            prompt_tokens=bmlib_resp.input_tokens,
            completion_tokens=bmlib_resp.output_tokens,
            total_tokens=bmlib_resp.total_tokens,
            duration_seconds=duration,
        )

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
            system_prompt: Optional system message (prepended to messages)
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
        # Prepend system prompt as a system message if provided
        effective_messages = list(messages)
        if system_prompt:
            effective_messages.insert(0, LLMMessage(role="system", content=system_prompt))

        # Try primary provider with retries
        try:
            response = self._chat_with_retry(
                effective_messages, model, temperature, top_p,
                max_tokens, json_mode, max_retries, retry_delay,
            )
            self._record_usage(response, "chat")
            return response

        except Exception as e:
            logger.warning(f"Primary provider failed for model {model}: {e}")

            # Fallback to Ollama
            fb_model = fallback_model or self.fallback_model
            spec = parse_model_string(model)
            if fb_model and spec.provider != self.fallback_provider:
                fb_model_str = f"{self.fallback_provider.value}:{fb_model}"
                logger.info(f"Falling back to {fb_model_str}")
                try:
                    response = self._chat_with_retry(
                        effective_messages, fb_model_str, temperature, top_p,
                        max_tokens, json_mode, max_retries, retry_delay,
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
        messages: list[LLMMessage],
        model: str,
        temperature: float,
        top_p: float,
        max_tokens: Optional[int],
        json_mode: bool,
        max_retries: int,
        retry_delay: float,
    ) -> LLMResponse:
        """
        Execute chat with retry logic and exponential backoff.

        Args:
            messages: Chat messages
            model: Model string with optional provider prefix
            temperature: Sampling temperature
            top_p: Top-p sampling
            max_tokens: Maximum tokens to generate
            json_mode: Request JSON output
            max_retries: Maximum retry attempts
            retry_delay: Initial delay between retries

        Returns:
            LLMResponse from successful call

        Raises:
            Exception: Last error if all retries fail
        """
        last_error: Optional[Exception] = None
        current_delay = retry_delay

        # Build kwargs for bmlib
        kwargs: dict[str, Any] = {}
        if top_p is not None:
            kwargs["top_p"] = top_p
        if json_mode:
            kwargs["json_mode"] = True

        for attempt in range(max_retries):
            try:
                start_time = time.time()
                bmlib_resp = self._bmlib.chat(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens or 4096,
                    **kwargs,
                )
                return self._adapt_response(bmlib_resp, model, start_time)
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

        Wraps the prompt as a single user message and delegates to chat().

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
        messages = [LLMMessage(role="user", content=prompt)]
        return self.chat(
            messages=messages,
            model=model,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            json_mode=json_mode,
            fallback_model=fallback_model,
            max_retries=max_retries,
            retry_delay=retry_delay,
        )

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
        embed_model = f"ollama:{model}" if ":" not in model else model
        bmlib_resp: BmlibEmbeddingResponse = self._bmlib.embed(text=text, model=embed_model)

        response = EmbeddingResponse(
            embedding=bmlib_resp.embedding,
            model=model,
            provider=Provider.OLLAMA,
            dimensions=bmlib_resp.dimensions,
            prompt_tokens=bmlib_resp.input_tokens,
        )

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
            result = self._bmlib.test_connection(provider_type.value)
            if isinstance(result, bool):
                return result
            # bmlib returns tuple (bool, str) for single provider
            return result[0] if isinstance(result, tuple) else bool(result)
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

        if provider_type:
            try:
                models = self._bmlib.list_models(provider_type.value)
                # bmlib returns list[str] for single provider
                result[provider_type.value] = list(models) if models else []
            except Exception as e:
                logger.debug(f"Could not list models for {provider_type.value}: {e}")
                result[provider_type.value] = []
        else:
            for ptype in Provider:
                try:
                    models = self._bmlib.list_models(ptype.value)
                    result[ptype.value] = list(models) if models else []
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

    Centralized utility function for listing Ollama models.
    Delegates to bmlib's LLMClient.

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
    try:
        # Get configured host if not provided
        if host is None:
            try:
                from ..config import get_ollama_host
                host = get_ollama_host()
            except ImportError:
                host = DEFAULT_OLLAMA_HOST

        client = BmlibLLMClient(
            default_provider="ollama",
            ollama_host=host,
        )
        models = client.list_models("ollama")
        return list(models) if models else []

    except Exception as e:
        logger.warning(f"Failed to list Ollama models: {e}")
        return []
