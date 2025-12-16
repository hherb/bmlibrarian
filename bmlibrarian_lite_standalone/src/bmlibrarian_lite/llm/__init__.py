"""
LLM client module for BMLibrarian Lite.

Provides a unified interface for LLM communication supporting both:
- Anthropic Claude API (online)
- Ollama local models (offline)

Usage:
    from bmlibrarian_lite.llm import LLMClient, LLMMessage, get_llm_client

    client = get_llm_client()
    response = client.chat(
        messages=[LLMMessage(role="user", content="Hello")],
        model="anthropic:claude-sonnet-4-20250514",
    )
    print(response.content)
"""

from .client import LLMClient, get_llm_client
from .data_types import LLMMessage, LLMResponse
from .token_tracker import TokenTracker, TokenUsageSummary, get_token_tracker

__all__ = [
    "LLMClient",
    "get_llm_client",
    "LLMMessage",
    "LLMResponse",
    "TokenTracker",
    "TokenUsageSummary",
    "get_token_tracker",
]
