"""DocumentScoringAgent honours its configured generation ceiling.

It used to send a hardcoded 500 tokens (plus 100 per retry), ignoring
``agents.scoring.max_tokens``; gpt-oss:20b then sometimes used the whole
budget on reasoning and the document could not be scored.
"""

from unittest.mock import patch

from bmlibrarian.agents import AgentFactory, DocumentScoringAgent
from bmlibrarian.agents.scoring_agent import (
    DEFAULT_SCORING_MAX_TOKENS,
    SCORING_RETRY_TOKEN_INCREMENT,
)

VALID_RESPONSE = '{"score": 3, "reasoning": "Relevant cohort study."}'
DOCUMENT = {"id": 1, "title": "A study", "abstract": "Findings."}


def _agent(**kwargs) -> DocumentScoringAgent:
    """A scoring agent that never contacts a model on construction."""
    return DocumentScoringAgent(model="gpt-oss:20b", show_model_info=False, **kwargs)


def test_configured_max_tokens_is_sent() -> None:
    """The ceiling given to the agent reaches the LLM request."""
    agent = _agent(max_tokens=1234)
    with patch.object(agent, "_make_ollama_request", return_value=VALID_RESPONSE) as request:
        agent.evaluate_document("Does it work?", DOCUMENT)

    assert request.call_args.kwargs["num_predict"] == 1234


def test_retries_raise_the_ceiling() -> None:
    """An incomplete response is retried with more room."""
    agent = _agent()
    with patch.object(
        agent, "_make_ollama_request", side_effect=["{", VALID_RESPONSE]
    ) as request:
        agent.evaluate_document("Does it work?", DOCUMENT)

    budgets = [call.kwargs["num_predict"] for call in request.call_args_list]
    assert budgets == [
        DEFAULT_SCORING_MAX_TOKENS,
        DEFAULT_SCORING_MAX_TOKENS + SCORING_RETRY_TOKEN_INCREMENT,
    ]


def test_factory_passes_max_tokens_to_the_scoring_agent() -> None:
    """agents.scoring.max_tokens survives the factory's parameter filter."""
    filtered = AgentFactory.filter_agent_config({"max_tokens": 1000, "bogus": 1}, "scoring")
    assert filtered == {"max_tokens": 1000}
