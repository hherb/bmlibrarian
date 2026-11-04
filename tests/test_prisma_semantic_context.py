"""
The PRISMA agent's second pass consolidates semantic chunks through
SemanticChunkProcessor (#252).

That call used to fail on every request and fall back to a single chunk with
only a log warning, so the feature was broken without a red test. These tests
drive the real agent -> processor -> LLMClient path, patched only at the
provider boundary.
"""

from unittest.mock import Mock, patch

import pytest

from bmlibrarian.agents.prisma2020_agent import (
    PRISMA2020Agent,
    SEMANTIC_CONTEXT_MAX_CHARS,
)
from tests.llm_test_support import patch_llm

# Enough chunks that together they exceed the direct-context limit.
CHUNK_COUNT = 3
LARGE_CHUNKS = [
    (f"Chunk {i} " + "x" * SEMANTIC_CONTEXT_MAX_CHARS, 0.9 - i / 10)
    for i in range(CHUNK_COUNT)
]


@pytest.fixture
def agent() -> PRISMA2020Agent:
    """A PRISMA agent with a recording callback."""
    with patch("bmlibrarian.config.get_config"):
        prisma = PRISMA2020Agent(model="gpt-oss:20b", show_model_info=False)
    prisma.callback = Mock()
    return prisma


def _context(agent: PRISMA2020Agent, title: str | None = "A review") -> str:
    """Run the second-pass context step for one item."""
    return agent._process_semantic_chunks_for_context(
        chunks=LARGE_CHUNKS,
        item_name="search_strategy",
        item_description="Full search strategy for at least one database",
        original_score=0.0,
        original_explanation="Not reported in abstract",
        document_title=title,
        query="search strategy",
    )


def _error_callbacks(agent: PRISMA2020Agent) -> list:
    """Callback calls reporting a second-pass failure."""
    return [
        c for c in agent.callback.call_args_list
        if c.args[0] == "prisma_second_pass_error"
    ]


def test_large_chunk_set_is_consolidated_by_the_model(agent: PRISMA2020Agent) -> None:
    """Chunks over the limit go through the model and its output comes back."""
    with patch_llm(content="EVIDENCE: PubMed and Embase were searched") as chat:
        context = _context(agent)

    assert chat.called
    assert "EVIDENCE" in context
    assert not _error_callbacks(agent)


def test_null_title_does_not_disable_consolidation(agent: PRISMA2020Agent) -> None:
    """A document with a NULL title still gets full consolidation."""
    with patch_llm(content="EVIDENCE"):
        context = _context(agent, title=None)

    assert "EVIDENCE" in context
    assert not _error_callbacks(agent)


def test_failed_consolidation_skips_reassessment_and_reports(
    agent: PRISMA2020Agent,
) -> None:
    """An empty model reply yields no context (keep the first-pass score), reported."""
    with patch_llm(content=""):
        context = _context(agent)

    assert context == ""
    errors = _error_callbacks(agent)
    assert len(errors) == 1
    assert "search_strategy" in errors[0].args[1]
