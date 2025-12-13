"""
Model string resolver for provider-prefixed model identifiers.

This module handles parsing of model strings in the format "provider:model"
and resolves them to a provider and model name. Unprefixed model names
default to Ollama for backward compatibility.

Examples:
    "medgemma-27b" → Ollama provider, model "medgemma-27b"
    "ollama:medgemma-27b" → Ollama provider, model "medgemma-27b"
    "anthropic:claude-3-opus" → Anthropic provider, model "claude-3-opus"
    "gpt-oss:20b" → Ollama provider, model "gpt-oss:20b" (colon in model name)
"""

from .data_types import Provider, ModelSpec

# Default provider when no prefix specified (backward compatibility)
DEFAULT_PROVIDER = Provider.OLLAMA

# Provider prefix patterns (lowercase for case-insensitive matching)
PROVIDER_PREFIXES: dict[str, Provider] = {
    "ollama": Provider.OLLAMA,
    "anthropic": Provider.ANTHROPIC,
    "openai": Provider.OPENAI,
}


def parse_model_string(model_string: str) -> ModelSpec:
    """
    Parse model string with optional provider prefix.

    The format is "provider:model" where provider is optional.
    If no recognized provider prefix is found, defaults to Ollama.

    Handles model names that contain colons (e.g., "gpt-oss:20b")
    by only recognizing known provider prefixes.

    Args:
        model_string: Model identifier, optionally prefixed with provider.
                      Examples: "medgemma-27b", "anthropic:claude-3-opus"

    Returns:
        ModelSpec with resolved provider and model name

    Examples:
        >>> parse_model_string("medgemma-27b")
        ModelSpec(provider=Provider.OLLAMA, model_name="medgemma-27b", ...)

        >>> parse_model_string("anthropic:claude-3-opus")
        ModelSpec(provider=Provider.ANTHROPIC, model_name="claude-3-opus", ...)

        >>> parse_model_string("gpt-oss:20b")  # Colon in model name
        ModelSpec(provider=Provider.OLLAMA, model_name="gpt-oss:20b", ...)
    """
    if not model_string:
        raise ValueError("Model string cannot be empty")

    if ":" in model_string:
        # Check if it's a provider prefix or part of model name
        prefix, remainder = model_string.split(":", 1)
        prefix_lower = prefix.lower()

        if prefix_lower in PROVIDER_PREFIXES:
            if not remainder:
                raise ValueError(
                    f"Model name cannot be empty after provider prefix: {model_string}"
                )
            return ModelSpec(
                provider=PROVIDER_PREFIXES[prefix_lower],
                model_name=remainder,
                raw=model_string,
            )

    # No recognized prefix - default to Ollama
    return ModelSpec(
        provider=DEFAULT_PROVIDER,
        model_name=model_string,
        raw=model_string,
    )


def format_model_string(provider: Provider, model_name: str) -> str:
    """
    Format provider and model name into canonical string.

    For the default provider (Ollama), returns just the model name
    for backward compatibility. For other providers, returns
    "provider:model" format.

    Args:
        provider: The LLM provider
        model_name: The model name

    Returns:
        Formatted model string

    Examples:
        >>> format_model_string(Provider.OLLAMA, "medgemma-27b")
        "medgemma-27b"

        >>> format_model_string(Provider.ANTHROPIC, "claude-3-opus")
        "anthropic:claude-3-opus"
    """
    if provider == DEFAULT_PROVIDER:
        return model_name  # No prefix needed for default
    return f"{provider.value}:{model_name}"


def is_provider_prefix(prefix: str) -> bool:
    """
    Check if a string is a recognized provider prefix.

    Args:
        prefix: String to check

    Returns:
        True if the prefix is a known provider
    """
    return prefix.lower() in PROVIDER_PREFIXES


def get_supported_providers() -> list[str]:
    """
    Get list of supported provider names.

    Returns:
        List of provider prefix strings
    """
    return list(PROVIDER_PREFIXES.keys())
