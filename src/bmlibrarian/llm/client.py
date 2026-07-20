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
    BatchEmbeddingResponse,
    Provider,
)
from .model_resolver import parse_model_string, qualify_model_string
from .token_tracker import get_token_tracker, TokenTracker
from .constants import (
    DEFAULT_ANTHROPIC_MAX_TOKENS,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_OLLAMA_HOST,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    DEFAULT_MAX_RETRIES,
    OLLAMA_UNLIMITED_MAX_TOKENS,
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
            # Providers without reasoning support omit this attribute.
            thinking=getattr(bmlib_resp, "thinking", None),
        )

    @staticmethod
    def _resolve_max_tokens(
        max_tokens: Optional[int],
        provider: Provider,
    ) -> int:
        """
        Choose the generation ceiling to send to bmlib.

        bmlib always forwards max_tokens to the provider, so omitting a limit
        is not an option — a value must be chosen. Ollama accepts a sentinel
        meaning "generate until the model stops", which preserves the previous
        behaviour of leaving num_predict unset. Providers that require a
        positive integer (Anthropic) fall back to the documented default.

        Args:
            max_tokens: Explicitly requested limit, or None
            provider: Resolved provider for the request

        Returns:
            Token ceiling to pass to bmlib
        """
        if max_tokens is not None:
            return max_tokens
        if provider == Provider.OLLAMA:
            return OLLAMA_UNLIMITED_MAX_TOKENS
        return DEFAULT_ANTHROPIC_MAX_TOKENS

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
        think: Optional[bool | str | int] = None,
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
            think: Request a reasoning trace. True/False toggles it,
                "low"/"medium"/"high" sets effort, an int sets a token
                budget. Left as None the option is not sent at all —
                whether a model accepts it is the provider's business,
                and Ollama rejects it outright for models without
                thinking support.

        Returns:
            LLMResponse with generated content, and thinking set when the
            model returned a trace. A thinking-enabled request is not
            guaranteed to return one.

        Raises:
            ConnectionError: If all providers fail
        """
        # Prepend system prompt as a system message if provided
        effective_messages = list(messages)
        if system_prompt:
            effective_messages.insert(0, LLMMessage(role="system", content=system_prompt))

        return self._chat_with_fallback(
            effective_messages, model, temperature, top_p, max_tokens,
            json_mode, fallback_model, max_retries, retry_delay,
            operation="chat", think=think,
        )

    def _chat_with_fallback(
        self,
        messages: list[LLMMessage],
        model: str,
        temperature: float,
        top_p: float,
        max_tokens: Optional[int],
        json_mode: bool,
        fallback_model: Optional[str],
        max_retries: int,
        retry_delay: float,
        operation: str,
        think: Optional[bool | str | int] = None,
    ) -> LLMResponse:
        """
        Execute a chat request with retries, then Ollama fallback.

        Args:
            messages: Chat messages, system prompt already prepended
            model: Model string with optional provider prefix
            temperature: Sampling temperature
            top_p: Top-p sampling
            max_tokens: Maximum tokens to generate
            json_mode: Request JSON output
            fallback_model: Model to use on failure (Ollama)
            max_retries: Maximum retry attempts
            retry_delay: Initial delay between retries
            operation: Label recorded against token usage ("chat"/"generate")
            think: Reasoning-trace option, omitted when None

        Returns:
            LLMResponse from the primary provider or the fallback

        Raises:
            ConnectionError: If both primary and fallback fail
        """
        # Try primary provider with retries
        try:
            response = self._chat_with_retry(
                messages, model, temperature, top_p,
                max_tokens, json_mode, max_retries, retry_delay, think,
            )
            self._record_usage(response, operation)
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
                        messages, fb_model_str, temperature, top_p,
                        max_tokens, json_mode, max_retries, retry_delay, think,
                    )
                    self._record_usage(response, operation)
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
        think: Optional[bool | str | int] = None,
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
            think: Reasoning-trace option, omitted when None

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
        # Only send think when asked. Providers reject the option on models
        # without thinking support, so an explicit False is not harmless.
        if think is not None:
            kwargs["think"] = think

        # bmlib splits on the first colon without checking for a known provider
        # prefix, so an Ollama tag like "gpt-oss:20b" must be qualified first.
        qualified_model = qualify_model_string(model)
        effective_max_tokens = self._resolve_max_tokens(
            max_tokens, parse_model_string(model).provider,
        )

        for attempt in range(max_retries):
            try:
                start_time = time.time()
                bmlib_resp = self._bmlib.chat(
                    messages=messages,
                    model=qualified_model,
                    temperature=temperature,
                    max_tokens=effective_max_tokens,
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

        Wraps the prompt as a single user message and shares chat()'s retry
        and fallback path, but records usage against the "generate" operation
        so cost reporting can distinguish the two.

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
        return self._chat_with_fallback(
            messages, model, temperature, top_p, max_tokens,
            json_mode, fallback_model, max_retries, retry_delay,
            operation="generate",
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
        # Always use Ollama for embeddings (consistency + free). The prefix is
        # forced rather than merely added: embedding model names carry tags
        # (e.g. "snowflake-arctic-embed2:latest") that bmlib would otherwise
        # read as a provider name.
        embed_model = f"{Provider.OLLAMA.value}:{parse_model_string(model).model_name}"
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

    def embed_batch(
        self,
        texts: list[str],
        model: str = DEFAULT_EMBEDDING_MODEL,
        max_batch_size: Optional[int] = None,
    ) -> BatchEmbeddingResponse:
        """
        Generate embeddings for many texts per provider round-trip.

        Several times faster than looping :meth:`embed` for bulk work:
        measured against a local Ollama server, 32 chunks cost 0.59s
        batched versus 4.48s looped.

        Like :meth:`embed`, this always uses Ollama. Embedding locally is
        not a cost preference — pgvector dimensions are fixed by the
        stored corpus, so rerouting an embedding request to another
        provider would produce vectors that cannot be compared against it.

        Not atomic: if a later batch fails, vectors already computed for
        earlier batches are discarded with the exception.

        Args:
            texts: Texts to embed. An empty list returns an empty response
                without contacting the provider.
            model: Embedding model (Ollama only)
            max_batch_size: Maximum texts per provider request. None uses
                bmlib's provider default.

        Returns:
            BatchEmbeddingResponse with one vector per input, in order

        Raises:
            ConnectionError: If the provider request fails
            ValueError: If the provider returns a mismatched vector count
        """
        if not texts:
            return BatchEmbeddingResponse(
                embeddings=[],
                model=model,
                provider=Provider.OLLAMA,
            )

        # The prefix is forced rather than merely added, for the reason
        # documented on embed(): embedding model names carry tags such as
        # "snowflake-arctic-embed2:latest" that bmlib would otherwise split
        # on and read as a provider name.
        embed_model = f"{Provider.OLLAMA.value}:{parse_model_string(model).model_name}"

        kwargs: dict[str, Any] = {}
        if max_batch_size is not None:
            kwargs["max_batch_size"] = max_batch_size

        bmlib_resp = self._bmlib.embed_batch(
            texts=texts,
            model=embed_model,
            **kwargs,
        )

        response = BatchEmbeddingResponse(
            embeddings=bmlib_resp.embeddings,
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
            # Given a provider name, bmlib's client returns a plain bool.
            # (Its provider objects return (ok, message); its client does not.)
            return self._bmlib.test_connection(provider_type.value)
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

        # Deliberately not bmlib's client.list_models(): that enriches every
        # entry by calling ollama.show() per model, so listing costs one
        # request plus one per model. Against a server holding 139 models
        # that measured 3.53s versus 0.04s for the plain listing — an 82x
        # cost paid every time a picker is populated, which is all this
        # helper is for. None of the metadata it fetches is used here.
        #
        # This module is the LLM layer, the one place permitted to talk to
        # a provider directly, so the plain call belongs here rather than
        # in the callers. Revert to bmlib once it offers a names-only
        # listing.
        import ollama

        response = ollama.Client(host=host).list()
        return [
            name
            for entry in (getattr(response, "models", None) or [])
            if (name := getattr(entry, "model", "") or "")
        ]

    except Exception as e:
        logger.warning(f"Failed to list Ollama models: {e}")
        return []
