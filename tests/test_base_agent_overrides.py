"""Per-call override tests for BaseAgent LLM helpers.

BaseAgent's ``_make_llm_request`` and ``_generate_from_prompt`` historically
hardcoded ``self.model`` / ``self.temperature`` / ``self.top_p`` and dropped
any leftover kwargs. These tests pin the additive behavior that lets a caller
vary those per call (defaulting to ``self.*`` when omitted) and forward the
``think`` provider option to the chat client.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from bmlibrarian.agents import BaseAgent


def _fake_response(content: str = "ok", model: str = "stub-model") -> SimpleNamespace:
    """Build a minimal object with the attributes BaseAgent reads off a response."""
    return SimpleNamespace(
        content=content,
        prompt_tokens=1,
        completion_tokens=1,
        duration_seconds=0.0,
        model=model,
        provider=SimpleNamespace(value="ollama"),
    )


class _StubAgent(BaseAgent):
    """Concrete BaseAgent for exercising the shared helpers."""

    def get_agent_type(self) -> str:
        return "stub_agent"


@pytest.fixture
def agent() -> _StubAgent:
    """A stub agent with distinctive instance defaults for override assertions."""
    return _StubAgent(
        model="instance-model",
        temperature=0.3,
        top_p=0.8,
        show_model_info=False,
    )


# --- _generate_from_prompt -------------------------------------------------

@patch("bmlibrarian.llm.client.LLMClient.generate")
def test_generate_uses_instance_defaults_when_no_override(mock_generate, agent):
    """Omitting overrides falls back to the instance's model/temperature/top_p."""
    mock_generate.return_value = _fake_response()

    agent._generate_from_prompt("hello")

    kwargs = mock_generate.call_args.kwargs
    assert kwargs["model"] == "instance-model"
    assert kwargs["temperature"] == 0.3
    assert kwargs["top_p"] == 0.8


@patch("bmlibrarian.llm.client.LLMClient.generate")
def test_generate_temperature_override_is_applied(mock_generate, agent):
    """A per-call temperature overrides the instance temperature."""
    mock_generate.return_value = _fake_response()

    agent._generate_from_prompt("hello", temperature=0.95)

    assert mock_generate.call_args.kwargs["temperature"] == 0.95


@patch("bmlibrarian.llm.client.LLMClient.generate")
def test_generate_model_override_is_applied(mock_generate, agent):
    """A per-call model overrides the instance model."""
    mock_generate.return_value = _fake_response()

    agent._generate_from_prompt("hello", model="other-model")

    assert mock_generate.call_args.kwargs["model"] == "other-model"


@patch("bmlibrarian.llm.client.LLMClient.generate")
def test_generate_top_p_override_is_applied(mock_generate, agent):
    """A per-call top_p overrides the instance top_p."""
    mock_generate.return_value = _fake_response()

    agent._generate_from_prompt("hello", top_p=0.2)

    assert mock_generate.call_args.kwargs["top_p"] == 0.2


# --- _make_llm_request -----------------------------------------------------

@patch("bmlibrarian.llm.client.LLMClient.chat")
def test_chat_uses_instance_defaults_when_no_override(mock_chat, agent):
    """Omitting overrides falls back to the instance's model/temperature/top_p."""
    mock_chat.return_value = _fake_response()

    agent._make_llm_request([{"role": "user", "content": "hi"}])

    kwargs = mock_chat.call_args.kwargs
    assert kwargs["model"] == "instance-model"
    assert kwargs["temperature"] == 0.3
    assert kwargs["top_p"] == 0.8


@patch("bmlibrarian.llm.client.LLMClient.chat")
def test_chat_overrides_are_applied(mock_chat, agent):
    """Per-call model/temperature/top_p override the instance values."""
    mock_chat.return_value = _fake_response()

    agent._make_llm_request(
        [{"role": "user", "content": "hi"}],
        model="other-model",
        temperature=0.95,
        top_p=0.2,
    )

    kwargs = mock_chat.call_args.kwargs
    assert kwargs["model"] == "other-model"
    assert kwargs["temperature"] == 0.95
    assert kwargs["top_p"] == 0.2


@patch("bmlibrarian.llm.client.LLMClient.chat")
def test_chat_forwards_think_when_set(mock_chat, agent):
    """think is forwarded to the chat client when provided."""
    mock_chat.return_value = _fake_response()

    agent._make_llm_request([{"role": "user", "content": "hi"}], think=True)

    assert mock_chat.call_args.kwargs.get("think") is True


@patch("bmlibrarian.llm.client.LLMClient.chat")
def test_chat_omits_think_by_default(mock_chat, agent):
    """think is not sent to the client when the caller does not set it."""
    mock_chat.return_value = _fake_response()

    agent._make_llm_request([{"role": "user", "content": "hi"}])

    # Either absent, or explicitly None (provider treats None as "don't send").
    assert mock_chat.call_args.kwargs.get("think") is None


# --- error-path observability ----------------------------------------------

def _error_model(caplog) -> object:
    """Pull the model recorded on the first ``agent_llm_error`` log record."""
    for record in caplog.records:
        data = getattr(record, "structured_data", {})
        if data.get("event_type") == "agent_llm_error":
            return data.get("model")
    raise AssertionError("no agent_llm_error record was logged")


@patch("bmlibrarian.llm.client.LLMClient.chat")
def test_chat_error_logs_effective_model(mock_chat, agent, caplog):
    """On failure the error log reports the overridden model, not self.model."""
    mock_chat.side_effect = ConnectionError("boom")

    with caplog.at_level("ERROR", logger="bmlibrarian.agents"):
        with pytest.raises(ConnectionError):
            agent._make_llm_request(
                [{"role": "user", "content": "hi"}], model="other-model"
            )

    assert _error_model(caplog) == "other-model"


@patch("bmlibrarian.llm.client.LLMClient.generate")
def test_generate_error_logs_effective_model(mock_generate, agent, caplog):
    """On failure the error log reports the overridden model, not self.model."""
    mock_generate.side_effect = ConnectionError("boom")

    with caplog.at_level("ERROR", logger="bmlibrarian.agents"):
        with pytest.raises(ConnectionError):
            agent._generate_from_prompt("hello", model="other-model")

    assert _error_model(caplog) == "other-model"
