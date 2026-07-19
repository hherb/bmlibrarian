"""Regression tests for ReportingAgent.iterative_synthesis().

Guards against the bug where the JSON-parsing/content-building block was
nested inside an ``except`` clause after an unconditional ``continue``,
making it unreachable so the method always returned ``None`` even when the
LLM produced valid responses.

These tests are hermetic: no Ollama or PostgreSQL required.
"""

from unittest.mock import Mock

import pytest

from bmlibrarian.agents.citation_agent import Citation
from bmlibrarian.agents.reporting_agent import ReportingAgent


def _make_agent() -> ReportingAgent:
    """Create a ReportingAgent instance without running __init__ (hermetic)."""
    return ReportingAgent.__new__(ReportingAgent)


def _make_citation(doc_id: str, passage: str, score: float) -> Citation:
    """Build a minimal Citation for synthesis tests."""
    return Citation(
        passage=passage,
        summary=f"Summary of {doc_id}",
        relevance_score=score,
        document_id=doc_id,
        document_title=f"Title {doc_id}",
        authors=["Smith J"],
        publication_date="2023-01-01",
    )


def test_iterative_synthesis_builds_content_from_successful_llm_responses() -> None:
    """When every LLM call succeeds, the synthesized content must be returned."""
    agent = _make_agent()
    agent._generate_from_prompt = Mock(side_effect=["raw1", "raw2"])
    agent._parse_json_response = Mock(
        side_effect=[
            {"content": "Statement one [1].", "addresses_question": "yes"},
            {"action": "add_new", "content": "Statement two [2].", "reasoning": "new info"},
        ]
    )
    # final_formatting returning None must fall back to the accumulated content
    agent.final_formatting = Mock(return_value=None)

    citations = [
        _make_citation("doc1", "Passage one", 0.9),
        _make_citation("doc2", "Passage two", 0.8),
    ]
    doc_to_ref = {"doc1": 1, "doc2": 2}

    result = agent.iterative_synthesis("Does exercise help?", citations, doc_to_ref)

    assert result == "Statement one [1]. Statement two [2]."
    assert agent._generate_from_prompt.call_count == 2
    assert agent._parse_json_response.call_count == 2


def test_iterative_synthesis_skips_failed_llm_calls_but_keeps_the_rest() -> None:
    """A ConnectionError on one citation must not discard the others."""
    agent = _make_agent()
    agent._generate_from_prompt = Mock(
        side_effect=[ConnectionError("ollama down"), "raw2"]
    )
    agent._parse_json_response = Mock(
        return_value={"content": "Only statement [2].", "addresses_question": "yes"}
    )
    agent.final_formatting = Mock(return_value=None)

    citations = [
        _make_citation("doc1", "Passage one", 0.9),
        _make_citation("doc2", "Passage two", 0.8),
    ]
    doc_to_ref = {"doc1": 1, "doc2": 2}

    result = agent.iterative_synthesis("Does exercise help?", citations, doc_to_ref)

    assert result == "Only statement [2]."


def test_iterative_synthesis_returns_none_when_all_llm_calls_fail() -> None:
    """If no citation can be processed, None is the documented outcome."""
    agent = _make_agent()
    agent._generate_from_prompt = Mock(side_effect=ConnectionError("ollama down"))
    agent._parse_json_response = Mock()
    agent.final_formatting = Mock(return_value=None)

    result = agent.iterative_synthesis(
        "Does exercise help?", [_make_citation("doc1", "P", 0.9)], {"doc1": 1}
    )

    assert result is None
    agent._parse_json_response.assert_not_called()
