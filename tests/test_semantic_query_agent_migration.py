"""SemanticQueryAgent BaseAgent-migration tests.

SemanticQueryAgent was migrated onto BaseAgent. It varies temperature per
call (a creative temperature for rephrasing, a low one for keyword
expansion), which relies on BaseAgent's per-call override support. These
tests pin the migration and that each call still uses its intended
temperature.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from bmlibrarian.agents import BaseAgent
from bmlibrarian.agents.semantic_query_agent import (
    SemanticQueryAgent,
    DEFAULT_EXPANSION_TEMPERATURE,
    DEFAULT_REPHRASING_TEMPERATURE,
)


def _fake_response(content: str) -> SimpleNamespace:
    return SimpleNamespace(
        content=content,
        prompt_tokens=1,
        completion_tokens=1,
        duration_seconds=0.0,
        model="stub",
        provider=SimpleNamespace(value="ollama"),
    )


@pytest.fixture
def agent() -> SemanticQueryAgent:
    return SemanticQueryAgent()


def test_semantic_agent_is_base_agent(agent):
    """SemanticQueryAgent inherits the shared agent plumbing."""
    assert isinstance(agent, BaseAgent)


def test_semantic_agent_type(agent):
    """SemanticQueryAgent exposes a stable agent-type identifier."""
    assert agent.get_agent_type() == "semantic_query_agent"


def test_rephrase_uses_rephrasing_temperature(agent):
    """Query rephrasing uses the (creative) rephrasing temperature."""
    with patch(
        "bmlibrarian.llm.client.LLMClient.generate",
        return_value=_fake_response("an alternative phrasing of the query"),
    ) as mock_generate:
        agent._generate_query_variation("original query", 1, [])

    assert mock_generate.call_args.kwargs["temperature"] == DEFAULT_REPHRASING_TEMPERATURE


def test_expand_uses_expansion_temperature(agent):
    """Keyword expansion uses the low expansion temperature (per-call override)."""
    with patch(
        "bmlibrarian.llm.client.LLMClient.generate",
        return_value=_fake_response("KEYWORDS: a, b\nNUMBERS:\nEXPANDED: a b"),
    ) as mock_generate:
        agent.expand_query("some query")

    assert mock_generate.call_args.kwargs["temperature"] == DEFAULT_EXPANSION_TEMPERATURE
