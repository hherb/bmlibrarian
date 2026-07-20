"""
Tests for reasoning-trace support on bmlibrarian's LLM client.

Whether a model accepts ``think`` is the provider's business, not
something callers can infer from the model name. Ollama rejects it with
`ResponseError: "<model>" does not support thinking (status code: 400)`
— verified against a local server — so the interesting cases here are
the failure and absent-trace paths, not the happy one.

Patched at ``bmlib.llm.client.LLMClient.chat``, the provider boundary,
so bmlibrarian's own qualification and adaptation stay live.
"""

from unittest.mock import patch

import pytest
import bmlib.llm.client as _bmlib_llm_client
from bmlib.llm import LLMResponse as BmlibLLMResponse

from bmlibrarian.llm import LLMClient, LLMMessage

MODEL = "gpt-oss:20b"


@pytest.fixture
def client() -> LLMClient:
    """An LLM client whose provider transport is patched per-test."""
    return LLMClient(track_usage=False)


def _response(content: str, thinking: str | None = None) -> BmlibLLMResponse:
    """Build a provider response, optionally carrying a reasoning trace."""
    return BmlibLLMResponse(content=content, model=MODEL, thinking=thinking)


class TestThinkPassthrough:
    """Tests for forwarding the think option."""

    def test_think_is_forwarded_to_the_provider(self, client: LLMClient) -> None:
        """The option reaches the provider rather than being swallowed."""
        with patch.object(
            _bmlib_llm_client.LLMClient, "chat", return_value=_response("hi", "because")
        ) as mock_chat:
            client.chat(
                messages=[LLMMessage(role="user", content="q")],
                model=MODEL,
                think=True,
            )

        assert mock_chat.call_args.kwargs["think"] is True

    def test_think_is_omitted_when_not_requested(self, client: LLMClient) -> None:
        """
        No think key is sent unless asked for.

        Sending think=False to a model without thinking support is still
        an error on some providers, so the option must be absent rather
        than falsy.
        """
        with patch.object(
            _bmlib_llm_client.LLMClient, "chat", return_value=_response("hi")
        ) as mock_chat:
            client.chat(
                messages=[LLMMessage(role="user", content="q")], model=MODEL
            )

        assert "think" not in mock_chat.call_args.kwargs

    def test_effort_string_is_forwarded(self, client: LLMClient) -> None:
        """bmlib accepts low/medium/high as an effort level."""
        with patch.object(
            _bmlib_llm_client.LLMClient, "chat", return_value=_response("hi", "t")
        ) as mock_chat:
            client.chat(
                messages=[LLMMessage(role="user", content="q")],
                model=MODEL,
                think="high",
            )

        assert mock_chat.call_args.kwargs["think"] == "high"


class TestThinkingOnResponse:
    """Tests for surfacing the reasoning trace."""

    def test_trace_is_exposed(self, client: LLMClient) -> None:
        """A returned trace reaches the caller."""
        with patch.object(
            _bmlib_llm_client.LLMClient,
            "chat",
            return_value=_response("answer", "the reasoning"),
        ):
            response = client.chat(
                messages=[LLMMessage(role="user", content="q")],
                model=MODEL,
                think=True,
            )

        assert response.thinking == "the reasoning"
        assert response.content == "answer"

    def test_absent_trace_is_none_not_an_error(self, client: LLMClient) -> None:
        """
        A model may answer without emitting a trace.

        Callers must treat that as normal rather than assuming every
        thinking-enabled request returns one.
        """
        with patch.object(
            _bmlib_llm_client.LLMClient, "chat", return_value=_response("answer")
        ):
            response = client.chat(
                messages=[LLMMessage(role="user", content="q")],
                model=MODEL,
                think=True,
            )

        assert response.thinking is None
        assert response.content == "answer"

    def test_adapter_does_not_invent_a_trace(self, client: LLMClient) -> None:
        """
        The trace reflects the provider, nothing more.

        Not a claim that an unasked request never carries one: gpt-oss
        returns a trace even without think=True, and that is passed
        through as-is. This pins that the adapter neither fabricates nor
        drops it.
        """
        with patch.object(
            _bmlib_llm_client.LLMClient, "chat", return_value=_response("answer")
        ):
            response = client.chat(
                messages=[LLMMessage(role="user", content="q")], model=MODEL
            )

        assert response.thinking is None
