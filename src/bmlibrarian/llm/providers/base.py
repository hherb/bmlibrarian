"""
Abstract base class for LLM providers.

This module defines the interface that all LLM provider implementations
must follow, ensuring consistent behavior across different backends.
"""

from abc import ABC, abstractmethod
from typing import Optional

from ..data_types import (
    LLMMessage,
    LLMResponse,
    EmbeddingResponse,
    GenerationParams,
    Provider,
)


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.

    Each provider implementation handles:
    - Client initialization and connection management
    - Request formatting for the specific API
    - Response parsing into unified format
    - Error handling and retries

    Implementations must be thread-safe for use in multi-threaded applications.
    """

    @property
    @abstractmethod
    def provider_type(self) -> Provider:
        """
        Return the provider enum value.

        Returns:
            Provider enum identifying this provider
        """
        pass

    @abstractmethod
    def chat(
        self,
        messages: list[LLMMessage],
        model: str,
        params: GenerationParams,
        system_prompt: Optional[str] = None,
    ) -> LLMResponse:
        """
        Send a chat completion request.

        Args:
            messages: Conversation history as list of LLMMessage
            model: Model name (without provider prefix)
            params: Generation parameters
            system_prompt: Optional system message

        Returns:
            Unified LLMResponse with generated content

        Raises:
            ConnectionError: If the provider is unavailable
            ValueError: If the request is invalid
        """
        pass

    @abstractmethod
    def generate(
        self,
        prompt: str,
        model: str,
        params: GenerationParams,
    ) -> LLMResponse:
        """
        Send a simple text generation request.

        For providers that don't have a separate generate endpoint,
        this should wrap the prompt in a chat message.

        Args:
            prompt: Text prompt
            model: Model name (without provider prefix)
            params: Generation parameters

        Returns:
            Unified LLMResponse with generated content

        Raises:
            ConnectionError: If the provider is unavailable
            ValueError: If the request is invalid
        """
        pass

    @abstractmethod
    def embed(
        self,
        text: str,
        model: str,
    ) -> EmbeddingResponse:
        """
        Generate embeddings for text.

        Args:
            text: Text to embed
            model: Embedding model name

        Returns:
            Unified EmbeddingResponse with embedding vector

        Raises:
            ConnectionError: If the provider is unavailable
            NotImplementedError: If the provider doesn't support embeddings
        """
        pass

    @abstractmethod
    def test_connection(self) -> bool:
        """
        Test if the provider is available.

        This should be a lightweight check that verifies connectivity
        without making expensive API calls.

        Returns:
            True if connection is healthy, False otherwise
        """
        pass

    @abstractmethod
    def list_models(self) -> list[str]:
        """
        List available models.

        For providers with a model list API, this queries available models.
        For providers without such an API, this returns known/supported models.

        Returns:
            List of model names available from this provider
        """
        pass

    def supports_embeddings(self) -> bool:
        """
        Check if this provider supports embeddings.

        Override in providers that don't support embeddings to return False.

        Returns:
            True if embeddings are supported
        """
        return True

    def supports_json_mode(self) -> bool:
        """
        Check if this provider supports JSON output mode.

        Override in providers that don't support JSON mode to return False.

        Returns:
            True if JSON mode is supported
        """
        return True

    def get_default_model(self) -> Optional[str]:
        """
        Get the default model for this provider.

        Override to provide a sensible default model.

        Returns:
            Default model name, or None if no default
        """
        return None
