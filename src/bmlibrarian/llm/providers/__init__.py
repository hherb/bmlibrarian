"""
LLM Provider registry and factory.

This module provides a singleton registry for LLM provider instances,
ensuring efficient connection reuse across the application.

Usage:
    from bmlibrarian.llm.providers import get_provider, Provider

    ollama = get_provider(Provider.OLLAMA)
    anthropic = get_provider(Provider.ANTHROPIC)
"""

import logging
import threading
from typing import Optional, Any

from ..data_types import Provider
from .base import LLMProvider

logger = logging.getLogger(__name__)

# Provider instances (singleton pattern per provider type)
_providers: dict[Provider, LLMProvider] = {}
_lock = threading.Lock()

# Provider configuration cache (for recreating providers with same config)
_provider_configs: dict[Provider, dict[str, Any]] = {}


def get_provider(
    provider_type: Provider,
    **kwargs: Any,
) -> LLMProvider:
    """
    Get or create a provider instance.

    Uses singleton pattern - one instance per provider type.
    Configuration is cached, so subsequent calls with different
    kwargs will NOT update the provider configuration.

    To change provider configuration, use reset_provider() first.

    Args:
        provider_type: Which provider to get
        **kwargs: Provider-specific configuration (host, api_key, etc.)

    Returns:
        Provider instance

    Raises:
        ValueError: If provider type is unknown
        ImportError: If required package is not installed

    Example:
        # Get Ollama provider with custom host
        ollama = get_provider(Provider.OLLAMA, host="http://gpu-server:11434")

        # Get Anthropic provider (uses ANTHROPIC_API_KEY env var)
        anthropic = get_provider(Provider.ANTHROPIC)
    """
    with _lock:
        if provider_type not in _providers:
            _providers[provider_type] = _create_provider(provider_type, **kwargs)
            _provider_configs[provider_type] = kwargs
            logger.debug(f"Created {provider_type.value} provider")
        return _providers[provider_type]


def _create_provider(provider_type: Provider, **kwargs: Any) -> LLMProvider:
    """
    Create a new provider instance.

    Args:
        provider_type: Which provider to create
        **kwargs: Provider-specific configuration

    Returns:
        New provider instance

    Raises:
        ValueError: If provider type is unknown
    """
    if provider_type == Provider.OLLAMA:
        from .ollama_provider import OllamaProvider

        return OllamaProvider(**kwargs)

    elif provider_type == Provider.ANTHROPIC:
        from .anthropic_provider import AnthropicProvider

        return AnthropicProvider(**kwargs)

    elif provider_type == Provider.OPENAI:
        # OpenAI provider not yet implemented
        raise NotImplementedError(
            "OpenAI provider not yet implemented. "
            "Use ollama or anthropic providers."
        )

    else:
        raise ValueError(f"Unknown provider: {provider_type}")


def reset_provider(provider_type: Provider) -> None:
    """
    Reset a specific provider instance.

    This removes the cached provider instance, allowing a new one
    to be created with different configuration on the next get_provider() call.

    Args:
        provider_type: Which provider to reset
    """
    with _lock:
        if provider_type in _providers:
            del _providers[provider_type]
            logger.debug(f"Reset {provider_type.value} provider")
        if provider_type in _provider_configs:
            del _provider_configs[provider_type]


def reset_all_providers() -> None:
    """
    Reset all provider instances.

    Clears all cached providers, useful for testing or
    reconfiguration scenarios.
    """
    global _providers, _provider_configs
    with _lock:
        _providers.clear()
        _provider_configs.clear()
        logger.debug("Reset all providers")


def get_available_providers() -> list[Provider]:
    """
    Get list of available (initialized) providers.

    Returns:
        List of Provider enums for currently initialized providers
    """
    with _lock:
        return list(_providers.keys())


def is_provider_available(provider_type: Provider) -> bool:
    """
    Check if a provider is available and properly configured.

    This creates the provider if not already created and tests
    the connection.

    Args:
        provider_type: Which provider to check

    Returns:
        True if provider is available and can connect
    """
    try:
        provider = get_provider(provider_type)
        return provider.test_connection()
    except Exception as e:
        logger.debug(f"Provider {provider_type.value} not available: {e}")
        return False


# Re-export for convenience
__all__ = [
    "LLMProvider",
    "get_provider",
    "reset_provider",
    "reset_all_providers",
    "get_available_providers",
    "is_provider_available",
]
