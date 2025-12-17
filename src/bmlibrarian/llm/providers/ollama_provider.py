"""
Ollama provider implementation.

This module provides integration with Ollama for local LLM inference.
Uses the official ollama Python library as per project guidelines.
"""

import logging
import os
import time
from typing import Optional, Any

import ollama

from .base import LLMProvider
from ..data_types import (
    LLMMessage,
    LLMResponse,
    EmbeddingResponse,
    GenerationParams,
    Provider,
)
from ..constants import (
    DEFAULT_OLLAMA_HOST,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_REQUEST_TIMEOUT,
)

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    """
    Ollama provider implementation.

    Uses the official ollama Python library for local LLM inference.
    Supports chat, generation, and embeddings.

    Attributes:
        host: Ollama server URL
        timeout: Request timeout in seconds
    """

    def __init__(
        self,
        host: Optional[str] = None,
        timeout: float = DEFAULT_REQUEST_TIMEOUT,
    ) -> None:
        """
        Initialize Ollama provider.

        Args:
            host: Ollama server URL (default: http://localhost:11434 or OLLAMA_HOST env var)
            timeout: Request timeout in seconds
        """
        self.host = host or os.environ.get("OLLAMA_HOST", DEFAULT_OLLAMA_HOST)
        self.timeout = timeout
        self._client: Optional[ollama.Client] = None

    @property
    def provider_type(self) -> Provider:
        """Return the provider enum value."""
        return Provider.OLLAMA

    @property
    def client(self) -> ollama.Client:
        """
        Lazy initialization of Ollama client.

        Returns:
            Configured ollama.Client instance
        """
        if self._client is None:
            self._client = ollama.Client(host=self.host)
        return self._client

    def chat(
        self,
        messages: list[LLMMessage],
        model: str,
        params: GenerationParams,
        system_prompt: Optional[str] = None,
    ) -> LLMResponse:
        """
        Send chat completion to Ollama.

        Args:
            messages: Conversation history
            model: Model name
            params: Generation parameters
            system_prompt: Optional system message

        Returns:
            LLMResponse with generated content
        """
        start_time = time.perf_counter()

        # Build message list
        ollama_messages: list[dict[str, str]] = []
        if system_prompt:
            ollama_messages.append({"role": "system", "content": system_prompt})

        for msg in messages:
            ollama_messages.append({"role": msg.role, "content": msg.content})

        # Build options
        options: dict[str, Any] = {
            "temperature": params.temperature,
            "top_p": params.top_p,
        }
        if params.max_tokens:
            options["num_predict"] = params.max_tokens
        if params.stop_sequences:
            options["stop"] = params.stop_sequences

        # Add any extra options
        options.update(params.extra)

        # Make request
        format_opt: Optional[str] = "json" if params.json_mode else None

        try:
            response = self.client.chat(
                model=model,
                messages=ollama_messages,
                options=options,
                format=format_opt,
            )
        except ollama.ResponseError as e:
            logger.error(f"Ollama chat error: {e}")
            raise ConnectionError(f"Ollama request failed: {e}") from e

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
            raw_response=dict(response),
        )

    def generate(
        self,
        prompt: str,
        model: str,
        params: GenerationParams,
    ) -> LLMResponse:
        """
        Send text generation to Ollama.

        Args:
            prompt: Text prompt
            model: Model name
            params: Generation parameters

        Returns:
            LLMResponse with generated content
        """
        start_time = time.perf_counter()

        # Build options
        options: dict[str, Any] = {
            "temperature": params.temperature,
            "top_p": params.top_p,
        }
        if params.max_tokens:
            options["num_predict"] = params.max_tokens
        if params.stop_sequences:
            options["stop"] = params.stop_sequences

        # Add any extra options
        options.update(params.extra)

        format_opt: Optional[str] = "json" if params.json_mode else None

        try:
            response = self.client.generate(
                model=model,
                prompt=prompt,
                options=options,
                format=format_opt,
            )
        except ollama.ResponseError as e:
            logger.error(f"Ollama generate error: {e}")
            raise ConnectionError(f"Ollama request failed: {e}") from e

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
            raw_response=dict(response),
        )

    def embed(
        self,
        text: str,
        model: Optional[str] = None,
    ) -> EmbeddingResponse:
        """
        Generate embeddings using Ollama.

        Args:
            text: Text to embed
            model: Embedding model (default: snowflake-arctic-embed2:latest)

        Returns:
            EmbeddingResponse with embedding vector
        """
        model = model or DEFAULT_EMBEDDING_MODEL

        try:
            response = self.client.embeddings(
                model=model,
                prompt=text,
            )
        except ollama.ResponseError as e:
            logger.error(f"Ollama embedding error: {e}")
            raise ConnectionError(f"Ollama embedding failed: {e}") from e

        embedding = response["embedding"]

        return EmbeddingResponse(
            embedding=embedding,
            model=model,
            provider=Provider.OLLAMA,
            dimensions=len(embedding),
            prompt_tokens=response.get("prompt_eval_count", 0),
        )

    def test_connection(self) -> bool:
        """
        Test Ollama server connectivity.

        Returns:
            True if Ollama server is accessible
        """
        try:
            self.client.list()
            return True
        except Exception as e:
            logger.warning(f"Ollama connection test failed: {e}")
            return False

    def list_models(self) -> list[str]:
        """
        List available Ollama models.

        Returns:
            List of model names installed on the server
        """
        try:
            response = self.client.list()
            # Ollama library >= 0.4.0 uses ListResponse with .models attribute
            # containing Model objects with .model attribute (not 'name' dict key)
            if hasattr(response, 'models'):
                return [m.model for m in response.models]
            # Fallback for older ollama library versions (dict-based response)
            return [m["name"] for m in response.get("models", [])]
        except Exception as e:
            logger.warning(f"Failed to list Ollama models: {e}")
            return []

    def get_default_model(self) -> Optional[str]:
        """
        Get the default model for Ollama.

        Returns the first available model, or None if no models are installed.
        """
        models = self.list_models()
        return models[0] if models else None

    def pull_model(self, model: str) -> bool:
        """
        Pull a model from the Ollama registry.

        Args:
            model: Model name to pull

        Returns:
            True if pull succeeded
        """
        try:
            logger.info(f"Pulling Ollama model: {model}")
            self.client.pull(model)
            return True
        except Exception as e:
            logger.error(f"Failed to pull model {model}: {e}")
            return False
