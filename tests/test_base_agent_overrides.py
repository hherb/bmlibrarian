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


def _fake_response(
    content: str = "ok", model: str = "stub-model", stop_reason: str = "stop"
) -> SimpleNamespace:
    """Build a minimal object with the attributes BaseAgent reads off a response."""
    return SimpleNamespace(
        content=content,
        prompt_tokens=1,
        completion_tokens=1,
        duration_seconds=0.0,
        stop_reason=stop_reason,
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


# --- truncation at max_tokens (#296) ---------------------------------------

@pytest.mark.parametrize("stop_reason", ["length", "max_tokens"])
@patch("bmlibrarian.llm.client.LLMClient.chat")
def test_chat_empty_truncated_response_names_the_limit(mock_chat, agent, stop_reason):
    """A model that spent max_tokens on reasoning is reported as such, not as 'empty'."""
    mock_chat.return_value = _fake_response(content="", stop_reason=stop_reason)

    with pytest.raises(ValueError, match=r"max_tokens limit \(2000\)"):
        agent._make_llm_request([{"role": "user", "content": "hi"}], num_predict=2000)


@patch("bmlibrarian.llm.client.LLMClient.generate")
def test_generate_empty_response_without_truncation(mock_generate, agent):
    """An empty answer that was not cut off keeps the plain message."""
    mock_generate.return_value = _fake_response(content="  ")

    with pytest.raises(ValueError, match="Empty response from model"):
        agent._generate_from_prompt("hello")


@patch("bmlibrarian.llm.client.LLMClient.chat")
def test_chat_truncated_answer_is_returned_with_a_warning(mock_chat, agent, caplog):
    """A partial answer is passed on (callers validate it), but the cut-off is logged."""
    mock_chat.return_value = _fake_response(content='{"a": 1', stop_reason="length")

    with caplog.at_level("WARNING", logger="bmlibrarian.agents"):
        content = agent._make_llm_request(
            [{"role": "user", "content": "hi"}], num_predict=50
        )

    assert content == '{"a": 1'
    assert "cut off at the max_tokens limit (50)" in caplog.text
