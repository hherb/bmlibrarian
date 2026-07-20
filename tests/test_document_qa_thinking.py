"""
Tests for document Q&A answer generation and its thinking fallback.

Whether a model accepts ``think`` is the provider's business. Ollama
rejects it with `"<model>" does not support thinking (status code: 400)`,
so asking for a trace must not turn a perfectly answerable question into
a failed one. These tests pin that retry, and the two ways a trace can
arrive (a separate field, or inlined in the content).

Patched at ``bmlib.llm.client.LLMClient.chat`` so bmlibrarian's own LLM
layer stays live inside the test.
"""

from unittest.mock import patch

import pytest
import bmlib.llm.client as _bmlib_llm_client
from bmlib.llm import LLMResponse as BmlibLLMResponse

from bmlibrarian.qa.document_qa import _generate_answer

MODEL = "gpt-oss:20b"
HOST = "http://localhost:11434"


def _response(content: str, thinking: str | None = None) -> BmlibLLMResponse:
    """Build a provider response, optionally carrying a reasoning trace."""
    return BmlibLLMResponse(content=content, model=MODEL, thinking=thinking)


def _answer(**kwargs):
    """Call _generate_answer with the fixed arguments these tests share."""
    return _generate_answer(
        question="What was the sample size?",
        context="We enrolled 4,731 patients.",
        model=MODEL,
        temperature=0.3,
        host=HOST,
        **kwargs,
    )


class TestThinkingFallback:
    """Tests for the provider-rejects-think path."""

    def test_retries_without_think_when_unsupported(self) -> None:
        """
        A refusal is retried plainly rather than failing the answer.

        This is the case a name-based allowlist got wrong in both
        directions, so it is asserted on the provider call itself.

        Exactly two provider calls: the refusal is deterministic, so the
        speculative attempt must not spend the client's retry budget on
        it before falling back.
        """
        rejection = RuntimeError(
            '"medgemma" does not support thinking (status code: 400)'
        )
        with patch.object(
            _bmlib_llm_client.LLMClient,
            "chat",
            side_effect=[rejection, _response("4,731 patients")],
        ) as mock_chat:
            answer, thinking, error = _answer(use_thinking=True)

        assert error is None
        assert "4,731" in answer
        assert mock_chat.call_count == 2
        # First attempt asks, second does not.
        assert mock_chat.call_args_list[0].kwargs.get("think") is True
        assert "think" not in mock_chat.call_args_list[1].kwargs

    def test_persistent_failure_is_reported(self) -> None:
        """A failure that survives the fallback is reported, not swallowed."""
        with patch.object(
            _bmlib_llm_client.LLMClient,
            "chat",
            side_effect=ConnectionError("connection refused"),
        ) as mock_chat:
            answer, thinking, error = _answer(use_thinking=True)

        assert answer == ""
        assert error is not None and "connection refused" in error
        # One un-retried thinking attempt, then a fallback that does get
        # the client's normal retries, so a transient fault still recovers.
        assert mock_chat.call_count > 1

    def test_think_not_requested_when_disabled(self) -> None:
        """use_thinking=False must not send the option at all."""
        with patch.object(
            _bmlib_llm_client.LLMClient, "chat", return_value=_response("4,731")
        ) as mock_chat:
            _answer(use_thinking=False)

        assert "think" not in mock_chat.call_args.kwargs


class TestTraceHandling:
    """Tests for how a reasoning trace is surfaced."""

    def test_separate_trace_is_returned(self) -> None:
        """A provider-separated trace is passed through."""
        with patch.object(
            _bmlib_llm_client.LLMClient,
            "chat",
            return_value=_response("4,731 patients", "counted the enrolled"),
        ):
            answer, thinking, error = _answer(use_thinking=True)

        assert error is None
        assert answer == "4,731 patients"
        assert thinking == "counted the enrolled"

    def test_inline_think_block_is_extracted(self) -> None:
        """A model that inlines <think> still yields a clean answer."""
        inline = "<think>counting the enrolled</think>4,731 patients"
        with patch.object(
            _bmlib_llm_client.LLMClient, "chat", return_value=_response(inline)
        ):
            answer, thinking, error = _answer(use_thinking=True)

        assert error is None
        assert answer == "4,731 patients"
        assert thinking == "counting the enrolled"

    def test_missing_trace_is_not_an_error(self) -> None:
        """No trace is normal; the answer still comes back."""
        with patch.object(
            _bmlib_llm_client.LLMClient, "chat", return_value=_response("4,731")
        ):
            answer, thinking, error = _answer(use_thinking=True)

        assert error is None
        assert answer == "4,731"
        assert thinking is None
