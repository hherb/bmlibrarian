"""Tests for SummaryGenerator's chunked summarization when chunks fail."""

from typing import List, Tuple
from unittest.mock import MagicMock

import pytest

from bmlibrarian.agents.paper_reviewer.summarizer import SummaryGenerator
from bmlibrarian.agents.paper_reviewer.text_utils import chunk_text

LONG_TEXT = ("Sentence number one. " * 40 + "\n\n") * 50  # 5 chunks
MERGED_CONFIDENCE = 0.8


def _generator(chunk_results: List[Tuple[str, float]]) -> Tuple[SummaryGenerator, list]:
    """A SummaryGenerator with mocked LLM steps; returns it and its callback log."""
    events: list = []
    generator = object.__new__(SummaryGenerator)
    generator.callback = lambda step, data: events.append((step, data))
    generator._summarize_chunk = MagicMock(side_effect=chunk_results)
    generator._merge_summaries = MagicMock(return_value=("merged", MERGED_CONFIDENCE))
    return generator, events


def test_all_chunks_summarized_keeps_confidence() -> None:
    """With no failures the merged confidence is unchanged."""
    n = len(chunk_text(LONG_TEXT))
    generator, events = _generator([("s", 0.9)] * n)

    summary, confidence = generator._generate_summary_chunked({}, LONG_TEXT, "T")

    assert (summary, confidence) == ("merged", MERGED_CONFIDENCE)
    assert events[-1] == (
        "summary_completed",
        f"Generated summary from {n} chunks (confidence: 80%)",
    )


def test_failed_chunks_are_reported_and_lower_confidence(caplog: pytest.LogCaptureFixture) -> None:
    """A dropped chunk is named in the log and callback; confidence is scaled."""
    n = len(chunk_text(LONG_TEXT))
    assert n == 5
    generator, events = _generator(
        [("s", 0.9), ("", 0.0), ("s", 0.9), ("", 0.0), ("s", 0.9)]
    )

    with caplog.at_level("WARNING"):
        summary, confidence = generator._generate_summary_chunked({}, LONG_TEXT, "T")

    assert summary == "merged"
    assert confidence == pytest.approx(MERGED_CONFIDENCE * 3 / 5)
    assert len(generator._merge_summaries.call_args.args[0]) == 3
    assert "omits chunk(s) [2, 4] of 5" in caplog.text
    step, message = events[-1]
    assert step == "summary_completed"
    assert "3 of 5 chunks (chunk(s) [2, 4] failed)" in message


def test_all_chunks_failed_returns_failure() -> None:
    """Nothing to merge: an explicit failure, not an empty summary."""
    n = len(chunk_text(LONG_TEXT))
    generator, _ = _generator([("", 0.0)] * n)

    assert generator._generate_summary_chunked({}, LONG_TEXT, "T") == (
        "Failed to generate summaries from document chunks.", 0.0
    )
    generator._merge_summaries.assert_not_called()
