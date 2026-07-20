"""
LLM Provider registry — delegates to bmlib's provider registry.

This module provides a bmlibrarian-compatible interface using the Provider enum
while delegating actual provider management to bmlib.llm.providers.

Usage:
    from bmlibrarian.llm.providers import get_provider, Provider

    ollama = get_provider(Provider.OLLAMA)
    anthropic = get_provider(Provider.ANTHROPIC)
"""

import logging
import threading
from typing import Any

from bmlib.llm.providers import (
    BaseProvider as LLMProvider,
    get_provider as _bmlib_get_provider,
)

from ..data_types import Provider

logger = logging.getLogger(__name__)

# Provider instances (singleton pattern per provider type)
_providers: dict[Provider, LLMProvider] = {}
_lock = threading.Lock()


def get_provider(
    provider_type: Provider,
    **kwargs: Any,
) -> LLMProvider:
    """
    Get or create a provider instance.

    Uses singleton pattern — one instance per provider type.
    Delegates to bmlib's provider registry for actual instantiation.

    Args:
        provider_type: Which provider to get
        **kwargs: Provider-specific configuration (host, api_key, etc.)

    Returns:
        Provider instance

    Raises:
        ValueError: If provider type is unknown
    """
    with _lock:
        if provider_type not in _providers:
            # Map bmlibrarian kwargs to bmlib kwargs
            bmlib_kwargs: dict[str, Any] = {}
            if "host" in kwargs:
                bmlib_kwargs["base_url"] = kwargs["host"]
            if "api_key" in kwargs:
                bmlib_kwargs["api_key"] = kwargs["api_key"]
            # Pass through any other kwargs
            for k, v in kwargs.items():
                if k not in ("host", "api_key"):
                    bmlib_kwargs[k] = v

            _providers[provider_type] = _bmlib_get_provider(
                provider_type.value, **bmlib_kwargs
            )
            logger.debug(f"Created {provider_type.value} provider via bmlib")
        return _providers[provider_type]


def reset_provider(provider_type: Provider) -> None:
    """
    Reset a specific provider instance.

    Args:
        provider_type: Which provider to reset
    """
    with _lock:
        if provider_type in _providers:
            del _providers[provider_type]
            logger.debug(f"Reset {provider_type.value} provider")


def reset_all_providers() -> None:
    """Reset all provider instances."""
    with _lock:
        _providers.clear()
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

    Args:
        provider_type: Which provider to check

    Returns:
        True if provider is available and can connect
    """
    try:
        provider = get_provider(provider_type)
        # bmlib's BaseProvider.test_connection returns (ok, message)
        connected, _message = provider.test_connection()
        return connected
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
