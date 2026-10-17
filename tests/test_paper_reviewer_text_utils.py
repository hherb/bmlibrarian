"""
Golden tests for the paper reviewer's text chunking utilities.

``agents/paper_reviewer/text_utils.py`` delegates its chunking to
``bmlib.llm.text_utils``. These tests pin the chunks it produced before that
delegation (values captured from the pre-bmlib implementation), so an upstream
change to the boundary rules or ``DEFAULT_MIN_CHUNK_SIZE`` -- or dropping
``boundary_aware=True`` here -- fails loudly instead of silently changing what
the summarizer and study detector send to the LLM.
"""

from typing import List

import pytest

from bmlibrarian.agents.paper_reviewer.constants import MAX_TEXT_LENGTH
from bmlibrarian.agents.paper_reviewer.text_utils import (
    CHUNK_OVERLAP,
    MIN_CHUNK_SIZE,
    chunk_text,
    process_with_map_reduce,
    process_with_rolling_summary,
)


def _assert_contiguous_slices(text: str, chunks: List[str], overlap: int) -> None:
    """Assert each chunk is the slice that starts ``overlap`` before the last end.

    Together with the chunk lengths this fixes every chunk exactly.
    """
    start = 0
    for chunk in chunks:
        assert chunk == text[start:start + len(chunk)]
        start = start + len(chunk) - overlap
    assert chunks[-1] == text[-len(chunks[-1]):]


# (text, max_chunk_size, overlap, expected chunk lengths from the old code)
GOLDEN_CASES = {
    "paragraph_break_past_min": (
        "A" * 600 + "\n\n" + "B" * 700 + "\n\n" + "C" * 900, 1000, 200,
        [602, 902, 1000, 300],
    ),
    "paragraph_break_before_min_falls_back_to_sentence": (
        "A" * 300 + "\n\n" + ("Word word. " * 120), 1000, 200,
        [995, 827],
    ),
    "sentence_breaks_only": (
        "Aspirin reduced events? Yes! Mostly so.\n" * 80, 1000, 150,
        [1000, 990, 990, 670],
    ),
    "no_breaks_hard_cut": (
        "x" * 3500, 1000, 200,
        [1000, 1000, 1000, 1000, 300],
    ),
    "unicode": (
        ("Ärzte prüfen β-Blocker. " * 30 + "\n\n") * 6, 1200, 100,
        [722, 822, 822, 822, 822, 822],
    ),
}


class TestChunkTextGolden:
    """chunk_text must reproduce the pre-bmlib chunks exactly."""

    def test_constants_unchanged(self) -> None:
        """The chunk geometry the golden values were captured with."""
        assert CHUNK_OVERLAP == 200
        assert MIN_CHUNK_SIZE == 500
        assert MAX_TEXT_LENGTH == 10000

    @pytest.mark.parametrize("name", sorted(GOLDEN_CASES))
    def test_golden_chunks(self, name: str) -> None:
        """Chunk lengths and positions match the old implementation."""
        text, size, overlap, expected_lengths = GOLDEN_CASES[name]

        chunks = chunk_text(text, size, overlap)

        assert [len(c) for c in chunks] == expected_lengths
        _assert_contiguous_slices(text, chunks, overlap)

    def test_short_and_empty_text_returned_whole(self) -> None:
        """Text that fits in one chunk, including '', comes back as [text]."""
        assert chunk_text("") == [""]
        assert chunk_text("short", 100, 10) == ["short"]

    def test_overlap_not_smaller_than_chunk_raises(self) -> None:
        """bmlib validates the geometry once the text needs chunking."""
        with pytest.raises(ValueError):
            chunk_text("a" * 1000, max_chunk_size=600, overlap=600)

    def test_overlap_ignored_when_text_fits(self) -> None:
        """Validation only applies when chunking actually happens."""
        assert chunk_text("a" * 500, max_chunk_size=600, overlap=600) == ["a" * 500]


class TestMapReduceHelpersUseLocalChunking:
    """The helpers chunk with the paper reviewer's geometry, not bmlib's."""

    TEXT = ("Sentence number one. " * 40 + "\n\n") * 50  # 42,100 characters

    def test_map_reduce_chunks_match_chunk_text(self) -> None:
        """map_fn sees exactly chunk_text's chunks (old lengths pinned)."""
        seen: List[str] = []

        result = process_with_map_reduce(
            self.TEXT, map_fn=lambda c: seen.append(c) or len(c), reduce_fn=sum
        )

        assert seen == chunk_text(self.TEXT)
        assert [len(c) for c in seen] == [9262, 9462, 9462, 9462, 5252]
        assert result == sum(len(c) for c in seen)

    def test_map_reduce_short_text_bypasses_chunking(self) -> None:
        """Short text goes straight to map_fn; reduce_fn is not called."""
        def reduce_fn(results: List[int]) -> int:
            """Fail if called."""
            raise AssertionError("reduce_fn must not be called for short text")

        assert process_with_map_reduce("abc", map_fn=len, reduce_fn=reduce_fn) == 3

    def test_rolling_summary_chunks_and_truncation(self) -> None:
        """Chunks match chunk_text and the carried summary is bounded."""
        seen: List[str] = []
        contexts: List[object] = []

        def process_fn(chunk: str, previous: object) -> tuple:
            """Record inputs; return an over-long summary."""
            seen.append(chunk)
            contexts.append(previous)
            return len(seen), "s" * 1000

        result = process_with_rolling_summary(
            self.TEXT, process_fn, summary_max_length=10
        )

        assert seen == chunk_text(self.TEXT)
        assert result == len(seen)
        assert contexts[0] is None
        assert all(c == "s" * 10 + "..." for c in contexts[1:])
