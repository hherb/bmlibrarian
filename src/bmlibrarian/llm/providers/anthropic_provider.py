"""
Anthropic Claude provider implementation.

This module provides integration with Anthropic's Claude API
for cloud-based LLM inference.
"""

import logging
import os
import time
from typing import Optional, Any, TYPE_CHECKING

from .base import LLMProvider
from ..data_types import (
    LLMMessage,
    LLMResponse,
    EmbeddingResponse,
    GenerationParams,
    Provider,
)

if TYPE_CHECKING:
    import anthropic

logger = logging.getLogger(__name__)


class AnthropicProvider(LLMProvider):
    """
    Anthropic Claude provider implementation.

    Uses the anthropic Python SDK for Claude API access.
    Requires ANTHROPIC_API_KEY environment variable.

    Note: Anthropic does not provide embedding models.
    Embedding requests will raise NotImplementedError.

    Attributes:
        api_key: Anthropic API key
        timeout: Request timeout in seconds
    """

    DEFAULT_MAX_TOKENS = 4096
    DEFAULT_MODEL = "claude-sonnet-4-20250514"

    # Known Anthropic models
    KNOWN_MODELS = [
        "claude-opus-4-20250514",
        "claude-sonnet-4-20250514",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229",
        "claude-3-sonnet-20240229",
        "claude-3-haiku-20240307",
    ]

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: float = 120.0,
    ) -> None:
        """
        Initialize Anthropic provider.

        Args:
            api_key: API key (default: from ANTHROPIC_API_KEY env var)
            timeout: Request timeout in seconds
        """
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.timeout = timeout
        self._client: Optional["anthropic.Anthropic"] = None

        if not self.api_key:
            logger.warning(
                "ANTHROPIC_API_KEY not set - Anthropic provider unavailable"
            )

    @property
    def provider_type(self) -> Provider:
        """Return the provider enum value."""
        return Provider.ANTHROPIC

    @property
    def client(self) -> "anthropic.Anthropic":
        """
        Lazy initialization of Anthropic client.

        Returns:
            Configured anthropic.Anthropic instance

        Raises:
            ImportError: If anthropic package is not installed
            ValueError: If API key is not set
        """
        if self._client is None:
            if not self.api_key:
                raise ValueError(
                    "Anthropic API key not set. "
                    "Set ANTHROPIC_API_KEY environment variable."
                )
            try:
                import anthropic

                self._client = anthropic.Anthropic(
                    api_key=self.api_key,
                    timeout=self.timeout,
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
        system_prompt: Optional[str] = None,
    ) -> LLMResponse:
        """
        Send chat completion to Anthropic.

        Args:
            messages: Conversation history
            model: Model name (e.g., "claude-3-opus-20240229")
            params: Generation parameters
            system_prompt: Optional system message

        Returns:
            LLMResponse with generated content
        """
        start_time = time.perf_counter()

        # Build message list (Anthropic format)
        # Anthropic requires alternating user/assistant messages
        anthropic_messages: list[dict[str, str]] = []
        for msg in messages:
            # Anthropic doesn't support system role in messages
            role = msg.role if msg.role != "system" else "user"
            anthropic_messages.append({
                "role": role,
                "content": msg.content,
            })

        # Build request kwargs
        max_tokens = params.max_tokens or self.DEFAULT_MAX_TOKENS

        kwargs: dict[str, Any] = {
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

        # Add any extra parameters
        kwargs.update(params.extra)

        try:
            response = self.client.messages.create(**kwargs)
        except Exception as e:
            logger.error(f"Anthropic chat error: {e}")
            raise ConnectionError(f"Anthropic request failed: {e}") from e

        duration = time.perf_counter() - start_time

        # Extract content from response blocks
        content = ""
        for block in response.content:
            if hasattr(block, "text"):
                content += block.text

        # Build raw response dict
        raw_response: Optional[dict[str, Any]] = None
        if hasattr(response, "model_dump"):
            raw_response = response.model_dump()

        return LLMResponse(
            content=content,
            model=model,
            provider=Provider.ANTHROPIC,
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
            total_tokens=response.usage.input_tokens + response.usage.output_tokens,
            duration_seconds=duration,
            raw_response=raw_response,
        )

    def generate(
        self,
        prompt: str,
        model: str,
        params: GenerationParams,
    ) -> LLMResponse:
        """
        Send text generation to Anthropic.

        Anthropic doesn't have a separate generate endpoint,
        so we wrap the prompt in a chat message.

        Args:
            prompt: Text prompt
            model: Model name
            params: Generation parameters

        Returns:
            LLMResponse with generated content
        """
        messages = [LLMMessage(role="user", content=prompt)]
        return self.chat(messages, model, params)

    def embed(
        self,
        text: str,
        model: str,
    ) -> EmbeddingResponse:
        """
        Generate embeddings.

        Note: Anthropic does not provide embedding models.

        Args:
            text: Text to embed
            model: Model name (unused)

        Raises:
            NotImplementedError: Always, as Anthropic doesn't support embeddings
        """
        raise NotImplementedError(
            "Anthropic does not provide embedding models. "
            "Use Ollama or OpenAI for embeddings."
        )

    def supports_embeddings(self) -> bool:
        """Anthropic does not support embeddings."""
        return False

    def test_connection(self) -> bool:
        """
        Test Anthropic API connectivity.

        Makes a minimal API call to verify the API key is valid.

        Returns:
            True if API is accessible and key is valid
        """
        if not self.api_key:
            return False
        try:
            # Minimal API call to verify key
            self.client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=1,
                messages=[{"role": "user", "content": "Hi"}],
            )
            return True
        except Exception as e:
            logger.warning(f"Anthropic connection test failed: {e}")
            return False

    def list_models(self) -> list[str]:
        """
        List available Anthropic models.

        Anthropic doesn't have a model list API, so we return known models.

        Returns:
            List of known Claude model names
        """
        return self.KNOWN_MODELS.copy()

    def get_default_model(self) -> Optional[str]:
        """Get the default Anthropic model."""
        return self.DEFAULT_MODEL

    def supports_json_mode(self) -> bool:
        """
        Check JSON mode support.

        Anthropic supports JSON output via prompting but doesn't have
        a dedicated JSON mode like some other providers.

        Returns:
            True (JSON can be requested via prompting)
        """
        return True
