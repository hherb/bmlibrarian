"""
Unified LLM client supporting Anthropic and Ollama providers.

This module provides a single interface for communicating with different
LLM providers, abstracting away the differences in their APIs.

Usage:
    from bmlibrarian_lite.llm import LLMClient, LLMMessage

    # Using Anthropic (default)
    client = LLMClient()
    response = client.chat(
        messages=[LLMMessage(role="user", content="Hello")],
        model="anthropic:claude-sonnet-4-20250514",
    )

    # Using Ollama
    response = client.chat(
        messages=[LLMMessage(role="user", content="Hello")],
        model="ollama:llama3.2",
    )
"""

import json
import logging
import os
from typing import Optional, List

from .data_types import LLMMessage, LLMResponse, get_model_info
from .token_tracker import get_token_tracker

logger = logging.getLogger(__name__)

# Default models for each provider
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-20250514"
DEFAULT_OLLAMA_MODEL = "llama3.2"
DEFAULT_OLLAMA_HOST = "http://localhost:11434"

# Provider prefixes
PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_OLLAMA = "ollama"


class LLMClient:
    """
    Unified LLM client supporting multiple providers.

    Automatically routes requests to the appropriate provider based on
    the model string format: "provider:model_name".

    Supported providers:
    - anthropic: Claude models via Anthropic API
    - ollama: Local models via Ollama server

    Attributes:
        default_provider: Default provider if not specified in model string
        ollama_host: URL of the Ollama server
    """

    def __init__(
        self,
        default_provider: str = PROVIDER_ANTHROPIC,
        ollama_host: Optional[str] = None,
        anthropic_api_key: Optional[str] = None,
    ) -> None:
        """
        Initialize the LLM client.

        Args:
            default_provider: Default provider (anthropic or ollama)
            ollama_host: Ollama server URL (uses OLLAMA_HOST env var or default)
            anthropic_api_key: Anthropic API key (uses ANTHROPIC_API_KEY env var if not provided)
        """
        self.default_provider = default_provider
        self.ollama_host = ollama_host or os.environ.get(
            "OLLAMA_HOST", DEFAULT_OLLAMA_HOST
        )
        self._anthropic_api_key = anthropic_api_key or os.environ.get(
            "ANTHROPIC_API_KEY"
        )

        # Lazy-loaded provider clients
        self._anthropic_client = None
        self._ollama_client = None

        logger.debug(
            f"LLMClient initialized: default_provider={default_provider}, "
            f"ollama_host={self.ollama_host}"
        )

    def _get_anthropic_client(self):
        """Get or create Anthropic client."""
        if self._anthropic_client is None:
            try:
                import anthropic
                self._anthropic_client = anthropic.Anthropic(
                    api_key=self._anthropic_api_key
                )
            except ImportError:
                raise ImportError(
                    "Anthropic package not installed. "
                    "Install with: pip install anthropic"
                )
        return self._anthropic_client

    def _get_ollama_client(self):
        """Get or create Ollama client."""
        if self._ollama_client is None:
            try:
                import ollama
                self._ollama_client = ollama.Client(host=self.ollama_host)
            except ImportError:
                raise ImportError(
                    "Ollama package not installed. "
                    "Install with: pip install ollama"
                )
        return self._ollama_client

    def _parse_model_string(self, model: str) -> tuple[str, str]:
        """
        Parse a model string into provider and model name.

        Args:
            model: Model string, optionally with provider prefix

        Returns:
            Tuple of (provider, model_name)
        """
        if ":" in model:
            provider, model_name = model.split(":", 1)
            return provider.lower(), model_name
        return self.default_provider, model

    def chat(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        top_p: Optional[float] = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        """
        Send a chat request to the LLM.

        Args:
            messages: List of conversation messages
            model: Model string with optional provider prefix
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate
            top_p: Nucleus sampling parameter (optional)
            json_mode: Request JSON-formatted output

        Returns:
            LLMResponse with the model's reply

        Raises:
            ValueError: If provider is not supported
            Exception: If API call fails
        """
        # Parse model string
        if model is None:
            provider = self.default_provider
            model_name = (
                DEFAULT_ANTHROPIC_MODEL if provider == PROVIDER_ANTHROPIC
                else DEFAULT_OLLAMA_MODEL
            )
        else:
            provider, model_name = self._parse_model_string(model)

        logger.debug(f"Chat request: provider={provider}, model={model_name}")

        # Route to appropriate provider
        if provider == PROVIDER_ANTHROPIC:
            response = self._chat_anthropic(
                messages=messages,
                model=model_name,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                json_mode=json_mode,
            )
        elif provider == PROVIDER_OLLAMA:
            response = self._chat_ollama(
                messages=messages,
                model=model_name,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                json_mode=json_mode,
            )
        else:
            raise ValueError(f"Unsupported provider: {provider}")

        # Track token usage
        tracker = get_token_tracker()
        tracker.record_usage(
            model=f"{provider}:{model_name}",
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )

        return response

    def _chat_anthropic(
        self,
        messages: List[LLMMessage],
        model: str,
        temperature: float,
        max_tokens: int,
        top_p: Optional[float],
        json_mode: bool,
    ) -> LLMResponse:
        """
        Send chat request to Anthropic Claude.

        Args:
            messages: Conversation messages
            model: Model name
            temperature: Sampling temperature
            max_tokens: Maximum tokens
            top_p: Nucleus sampling parameter
            json_mode: Request JSON output

        Returns:
            LLMResponse with Claude's reply
        """
        client = self._get_anthropic_client()

        # Convert messages to Anthropic format
        anthropic_messages = []
        system_message = None

        for msg in messages:
            if msg.role == "system":
                system_message = msg.content
            else:
                anthropic_messages.append({
                    "role": msg.role,
                    "content": msg.content,
                })

        # Build request kwargs
        kwargs = {
            "model": model,
            "messages": anthropic_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if system_message:
            kwargs["system"] = system_message

        if top_p is not None:
            kwargs["top_p"] = top_p

        # Make API call
        response = client.messages.create(**kwargs)

        # Extract content
        content = ""
        if response.content:
            for block in response.content:
                if hasattr(block, "text"):
                    content += block.text

        # Handle JSON mode (parse and re-serialize if needed)
        if json_mode:
            try:
                # Try to parse as JSON to validate
                json.loads(content)
            except json.JSONDecodeError:
                # Try to extract JSON from response
                content = self._extract_json(content)

        return LLMResponse(
            content=content,
            model=model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            stop_reason=response.stop_reason,
        )

    def _chat_ollama(
        self,
        messages: List[LLMMessage],
        model: str,
        temperature: float,
        max_tokens: int,
        top_p: Optional[float],
        json_mode: bool,
    ) -> LLMResponse:
        """
        Send chat request to Ollama.

        Args:
            messages: Conversation messages
            model: Model name
            temperature: Sampling temperature
            max_tokens: Maximum tokens
            top_p: Nucleus sampling parameter
            json_mode: Request JSON output

        Returns:
            LLMResponse with Ollama's reply
        """
        client = self._get_ollama_client()

        # Convert messages to Ollama format
        ollama_messages = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]

        # Build options
        options = {
            "temperature": temperature,
            "num_predict": max_tokens,
        }

        if top_p is not None:
            options["top_p"] = top_p

        # Build request kwargs
        kwargs = {
            "model": model,
            "messages": ollama_messages,
            "options": options,
        }

        if json_mode:
            kwargs["format"] = "json"

        # Make API call
        response = client.chat(**kwargs)

        content = response.get("message", {}).get("content", "")

        # Estimate token counts (Ollama may not provide exact counts)
        input_tokens = response.get("prompt_eval_count", 0)
        output_tokens = response.get("eval_count", 0)

        return LLMResponse(
            content=content,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            stop_reason="stop",
        )

    def _extract_json(self, text: str) -> str:
        """
        Extract JSON from text that may contain markdown or other content.

        Args:
            text: Text that may contain JSON

        Returns:
            Extracted JSON string
        """
        import re

        # Try to find JSON in code blocks
        code_block_match = re.search(
            r"```(?:json)?\s*\n?(.*?)\n?```",
            text,
            re.DOTALL
        )
        if code_block_match:
            candidate = code_block_match.group(1).strip()
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                pass

        # Try to find raw JSON object
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            candidate = brace_match.group(0)
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                pass

        # Return original text if no valid JSON found
        return text

    def test_connection(self, provider: Optional[str] = None) -> bool:
        """
        Test connection to an LLM provider.

        Args:
            provider: Provider to test (uses default if not specified)

        Returns:
            True if connection successful
        """
        provider = provider or self.default_provider

        try:
            if provider == PROVIDER_ANTHROPIC:
                client = self._get_anthropic_client()
                # Simple test - just create a minimal request
                response = client.messages.create(
                    model="claude-3-haiku-20240307",
                    max_tokens=10,
                    messages=[{"role": "user", "content": "Hi"}],
                )
                return bool(response.content)

            elif provider == PROVIDER_OLLAMA:
                client = self._get_ollama_client()
                # List models to test connection
                models = client.list()
                return True

            else:
                logger.warning(f"Unknown provider: {provider}")
                return False

        except Exception as e:
            logger.warning(f"Connection test failed for {provider}: {e}")
            return False

    def list_models(self, provider: Optional[str] = None) -> List[str]:
        """
        List available models for a provider.

        Args:
            provider: Provider to query (uses default if not specified)

        Returns:
            List of available model names
        """
        provider = provider or self.default_provider

        try:
            if provider == PROVIDER_ANTHROPIC:
                # Anthropic doesn't have a list endpoint, return known models
                return [
                    "claude-sonnet-4-20250514",
                    "claude-opus-4-20250514",
                    "claude-3-5-sonnet-20241022",
                    "claude-3-5-haiku-20241022",
                    "claude-3-opus-20240229",
                    "claude-3-sonnet-20240229",
                    "claude-3-haiku-20240307",
                ]

            elif provider == PROVIDER_OLLAMA:
                client = self._get_ollama_client()
                response = client.list()
                return [model["name"] for model in response.get("models", [])]

            else:
                return []

        except Exception as e:
            logger.warning(f"Failed to list models for {provider}: {e}")
            return []


# Global client instance
_global_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """
    Get the global LLM client instance.

    Creates a new instance if one doesn't exist.

    Returns:
        Global LLMClient instance
    """
    global _global_client
    if _global_client is None:
        _global_client = LLMClient()
    return _global_client
