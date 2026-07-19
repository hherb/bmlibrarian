"""Regression tests for QueryAgent.find_abstracts() pagination.

Guards against the bug where ``max_rows`` was applied *before* ``offset``
(``documents[:max_rows][offset:]``), which returned an empty page whenever
``offset >= max_rows`` — silently starving iterative retrieval after the
first batch.

Hermetic: no Ollama or PostgreSQL required.
"""

from unittest.mock import Mock

import pytest

import bmlibrarian.agents.query_agent as query_agent_module
from bmlibrarian.agents.query_agent import QueryAgent


def _make_agent() -> QueryAgent:
    """Create a QueryAgent without running __init__ (hermetic)."""
    agent = QueryAgent.__new__(QueryAgent)
    agent.use_thesaurus = False
    agent.convert_question = Mock(return_value="exercise & cardiovascular")
    agent._call_callback = Mock()
    return agent


def _fake_documents(count: int) -> list:
    """Build a list of fake document dicts with sequential ids."""
    return [{"id": i, "title": f"Doc {i}"} for i in range(count)]


@pytest.fixture
def hybrid_search(monkeypatch):
    """Patch search_hybrid to return 10 fake documents."""
    docs = _fake_documents(10)
    mock = Mock(return_value=(docs, {"strategies_used": ["bm25"]}))
    monkeypatch.setattr(query_agent_module, "search_hybrid", mock)
    return docs


def test_first_page_returns_first_max_rows(hybrid_search) -> None:
    """offset=0 with max_rows=3 yields documents 0..2."""
    agent = _make_agent()

    result = list(agent.find_abstracts("q?", max_rows=3, offset=0))

    assert [d["id"] for d in result] == [0, 1, 2]


def test_second_page_returns_next_slice_not_empty(hybrid_search) -> None:
    """offset=3 with max_rows=3 must yield documents 3..5, not an empty page."""
    agent = _make_agent()

    result = list(agent.find_abstracts("q?", max_rows=3, offset=3))

    assert [d["id"] for d in result] == [3, 4, 5]


def test_offset_beyond_available_returns_empty(hybrid_search) -> None:
    """Paging past the end of the result set yields nothing (loop terminator)."""
    agent = _make_agent()

    result = list(agent.find_abstracts("q?", max_rows=5, offset=10))

    assert result == []


def test_offset_without_max_rows(hybrid_search) -> None:
    """offset alone skips the first documents and returns the rest."""
    agent = _make_agent()

    result = list(agent.find_abstracts("q?", max_rows=0, offset=8))

    assert [d["id"] for d in result] == [8, 9]
