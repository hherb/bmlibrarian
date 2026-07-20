"""
Tests for the shared LLM helper behind the PaperChecker components.

These tests patch ``LLMClient.chat`` — a real method on a real client —
rather than substituting a component's ``client`` attribute with a
``Mock()``. Substituting the client stubs out exactly the layer being
tested: PR #247 shipped a component calling a removed ollama API with all
of its tests passing, because the fixture replaced the client wholesale
and fed it response dicts in the old shape. Patching a named method keeps
the signature honest, so the same drift would fail here.

The seam is deliberately ``LLMClient.chat`` and not the lower
``bmlib.llm.client.LLMClient.chat`` that :mod:`tests.llm_test_support`
uses. What is under test in this module is the helper's own behaviour
*above* the client — how many times it calls out, what it passes, and
which failures it retries. Patching one layer lower would leave
``LLMClient``'s transport retries inside the assertions, so a call count
would measure the client's loop rather than the helper's.

Tests that exercise a component end to end should use
:func:`tests.llm_test_support.patch_llm` instead, which patches below
``LLMClient`` and therefore keeps model-string qualification, retry,
fallback and response adaptation live.
"""

from unittest.mock import patch

import pytest
from bmlib.llm import LLMResponse as BmlibLLMResponse

from bmlibrarian.paperchecker.components.llm_support import (
    call_llm,
    probe_llm_connection,
)
from bmlibrarian.llm import LLMClient

MODEL = "gpt-oss:20b"


@pytest.fixture
def client() -> LLMClient:
    """An LLM client whose transport is patched per-test."""
    return LLMClient(track_usage=False)


def _response(content: str) -> BmlibLLMResponse:
    """Build a bmlib response carrying the given content."""
    return BmlibLLMResponse(content=content, model=MODEL)


class TestCallLlm:
    """Tests for call_llm."""

    def test_returns_stripped_content(self, client: LLMClient) -> None:
        """Content is returned with surrounding whitespace removed."""
        with patch.object(
            LLMClient, "chat", return_value=_response("  hello  ")
        ) as mock_chat:
            assert call_llm(client, MODEL, "prompt", 0.3, "test") == "hello"

        assert mock_chat.call_count == 1

    def test_passes_prompt_model_and_temperature_through(
        self, client: LLMClient
    ) -> None:
        """The prompt reaches the client as a single user message."""
        with patch.object(
            LLMClient, "chat", return_value=_response("ok")
        ) as mock_chat:
            call_llm(client, MODEL, "the prompt", 0.7, "test")

        kwargs = mock_chat.call_args.kwargs
        assert kwargs["model"] == MODEL
        assert kwargs["temperature"] == 0.7
        assert [(m.role, m.content) for m in kwargs["messages"]] == [
            ("user", "the prompt")
        ]

    def test_retries_empty_responses_then_raises(self, client: LLMClient) -> None:
        """An empty response is retried, and exhaustion raises RuntimeError."""
        with patch.object(
            LLMClient, "chat", return_value=_response("   ")
        ) as mock_chat:
            with pytest.raises(RuntimeError, match="Failed to get response"):
                call_llm(client, MODEL, "prompt", 0.3, "test", retry_delay=0.0)

        assert mock_chat.call_count == 3

    def test_recovers_when_a_later_attempt_returns_content(
        self, client: LLMClient
    ) -> None:
        """An empty first response does not abort the call."""
        with patch.object(
            LLMClient,
            "chat",
            side_effect=[_response(""), _response("recovered")],
        ) as mock_chat:
            result = call_llm(client, MODEL, "prompt", 0.3, "test", retry_delay=0.0)

        assert result == "recovered"
        assert mock_chat.call_count == 2

    def test_transport_failure_is_not_retried_by_the_helper(
        self, client: LLMClient
    ) -> None:
        """
        Retrying transport errors is LLMClient's job, not the helper's.

        Retrying in both places would multiply attempts (3 x 3), so the
        helper lets the exception propagate as a RuntimeError after a
        single call.
        """
        with patch.object(
            LLMClient, "chat", side_effect=ConnectionError("refused")
        ) as mock_chat:
            with pytest.raises(RuntimeError, match="refused"):
                call_llm(client, MODEL, "prompt", 0.3, "test", retry_delay=0.0)

        assert mock_chat.call_count == 1


class TestProbeLlmConnection:
    """Tests for probe_llm_connection."""

    def test_true_when_provider_reachable(self, client: LLMClient) -> None:
        """A reachable provider reports success."""
        with patch.object(LLMClient, "test_provider", return_value=True):
            assert probe_llm_connection(client, MODEL) is True

    def test_false_when_provider_unreachable(self, client: LLMClient) -> None:
        """An unreachable provider reports failure rather than raising."""
        with patch.object(LLMClient, "test_provider", return_value=False):
            assert probe_llm_connection(client, MODEL) is False

    def test_false_when_probe_raises(self, client: LLMClient) -> None:
        """An exception from the probe is contained."""
        with patch.object(
            LLMClient, "test_provider", side_effect=OSError("no route")
        ):
            assert probe_llm_connection(client, MODEL) is False

    def test_probes_the_provider_the_model_names(self, client: LLMClient) -> None:
        """An anthropic: model is probed against Anthropic, not Ollama."""
        from bmlibrarian.llm import Provider

        with patch.object(
            LLMClient, "test_provider", return_value=True
        ) as mock_probe:
            probe_llm_connection(client, "anthropic:claude-sonnet-5")

        assert mock_probe.call_args.args[0] == Provider.ANTHROPIC
