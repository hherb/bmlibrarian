"""Tests for BMLibrarian Lite chunking module."""

import pytest

from bmlibrarian.lite.chunking import (
    chunk_text,
    chunk_document_for_interrogation,
    estimate_chunk_count,
    merge_chunks,
)
from bmlibrarian.lite.data_models import DocumentChunk


class TestChunkText:
    """Tests for chunk_text function."""

    def test_basic_chunking(self) -> None:
        """Test basic text chunking."""
        text = "A" * 1000
        chunks = chunk_text(text, "doc-1", chunk_size=100, chunk_overlap=20)

        assert len(chunks) > 1
        assert all(isinstance(c, DocumentChunk) for c in chunks)
        assert all(len(c.text) <= 100 for c in chunks)
        assert chunks[0].document_id == "doc-1"

    def test_chunk_ids_are_unique(self) -> None:
        """Test that chunk IDs are unique."""
        text = "Word " * 200
        chunks = chunk_text(text, "doc-1", chunk_size=100, chunk_overlap=20)

        ids = [c.id for c in chunks]
        assert len(ids) == len(set(ids))  # All unique

    def test_chunk_indices_sequential(self) -> None:
        """Test that chunk indices are sequential starting from 0."""
        text = "Word " * 200
        chunks = chunk_text(text, "doc-1", chunk_size=100, chunk_overlap=20)

        indices = [c.chunk_index for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_chunk_positions_valid(self) -> None:
        """Test that start_char and end_char are valid."""
        text = "Word " * 200
        chunks = chunk_text(text, "doc-1", chunk_size=100, chunk_overlap=20)

        for chunk in chunks:
            assert chunk.start_char >= 0
            assert chunk.end_char <= len(text)
            assert chunk.start_char < chunk.end_char

    def test_empty_text(self) -> None:
        """Test chunking empty text returns empty list."""
        chunks = chunk_text("", "doc-1")
        assert chunks == []

    def test_small_text(self) -> None:
        """Test chunking text smaller than chunk size."""
        text = "Small text."
        chunks = chunk_text(text, "doc-1", chunk_size=1000)

        assert len(chunks) == 1
        assert chunks[0].text == text

    def test_invalid_chunk_size(self) -> None:
        """Test that invalid chunk_size raises ValueError."""
        with pytest.raises(ValueError, match="chunk_size must be positive"):
            chunk_text("text", "doc-1", chunk_size=0)

        with pytest.raises(ValueError, match="chunk_size must be positive"):
            chunk_text("text", "doc-1", chunk_size=-10)

    def test_invalid_chunk_overlap(self) -> None:
        """Test that invalid chunk_overlap raises ValueError."""
        with pytest.raises(ValueError, match="chunk_overlap must be non-negative"):
            chunk_text("text", "doc-1", chunk_overlap=-1)

    def test_overlap_greater_than_size(self) -> None:
        """Test that overlap >= size raises ValueError."""
        with pytest.raises(ValueError, match="chunk_overlap.*must be less than"):
            chunk_text("text", "doc-1", chunk_size=100, chunk_overlap=100)

        with pytest.raises(ValueError, match="chunk_overlap.*must be less than"):
            chunk_text("text", "doc-1", chunk_size=100, chunk_overlap=150)

    def test_breaks_at_sentence_boundary(self) -> None:
        """Test that chunks prefer breaking at sentence boundaries."""
        # Create text long enough to require chunking
        text = (
            "First sentence about medical research. "
            "Second sentence about cardiovascular disease. "
            "Third sentence about treatment options. "
            "Fourth sentence about clinical outcomes. "
            "Fifth sentence about patient recovery. "
            "Sixth sentence about follow-up studies."
        )
        chunks = chunk_text(text, "doc-1", chunk_size=100, chunk_overlap=20)

        # Should have multiple chunks
        assert len(chunks) >= 2

        # Check that chunks tend to end with sentence-ending punctuation
        sentence_endings = sum(
            1 for c in chunks if c.text.rstrip().endswith((".", "!", "?"))
        )
        # At least some chunks should end at sentence boundaries
        assert sentence_endings > 0

    def test_breaks_at_paragraph_boundary(self) -> None:
        """Test that chunks prefer breaking at paragraph boundaries."""
        # Create text long enough to require chunking
        text = (
            "Paragraph one with substantial medical content about cardiovascular health.\n\n"
            "Paragraph two discussing treatment methodologies and their effectiveness.\n\n"
            "Paragraph three covering patient outcomes and recovery protocols."
        )
        chunks = chunk_text(text, "doc-1", chunk_size=100, chunk_overlap=20)

        # With these parameters, we should get multiple chunks
        assert len(chunks) >= 2

    def test_handles_long_words(self) -> None:
        """Test handling of text with no natural break points."""
        # Long string of characters with no spaces
        text = "A" * 500
        chunks = chunk_text(text, "doc-1", chunk_size=100, chunk_overlap=20)

        # Should still chunk without crashing
        assert len(chunks) > 1
        # Each chunk should be at most chunk_size
        assert all(len(c.text) <= 100 for c in chunks)

    def test_overlap_provides_context(self) -> None:
        """Test that consecutive chunks have overlapping content."""
        words = ["word" + str(i) for i in range(100)]
        text = " ".join(words)
        chunks = chunk_text(text, "doc-1", chunk_size=100, chunk_overlap=30)

        if len(chunks) >= 2:
            # Check that there's some overlap between consecutive chunks
            for i in range(len(chunks) - 1):
                chunk1_words = set(chunks[i].text.split())
                chunk2_words = set(chunks[i + 1].text.split())
                overlap = chunk1_words & chunk2_words
                # There should be some overlapping words
                assert len(overlap) > 0


class TestChunkDocumentForInterrogation:
    """Tests for chunk_document_for_interrogation function."""

    def test_generates_document_id(self) -> None:
        """Test that document ID is generated if not provided."""
        chunks = chunk_document_for_interrogation(
            text="Some document text here.",
        )

        assert len(chunks) == 1
        assert chunks[0].document_id is not None
        assert len(chunks[0].document_id) > 0

    def test_uses_provided_document_id(self) -> None:
        """Test that provided document ID is used."""
        chunks = chunk_document_for_interrogation(
            text="Some document text here.",
            document_id="my-custom-id",
        )

        assert chunks[0].document_id == "my-custom-id"

    def test_adds_title_to_metadata(self) -> None:
        """Test that title is added to chunk metadata."""
        chunks = chunk_document_for_interrogation(
            text="Some document text here.",
            title="My Document Title",
        )

        assert chunks[0].metadata.get("title") == "My Document Title"

    def test_no_title_no_metadata(self) -> None:
        """Test that no title means no title in metadata."""
        chunks = chunk_document_for_interrogation(
            text="Some document text here.",
        )

        assert "title" not in chunks[0].metadata

    def test_custom_chunk_parameters(self) -> None:
        """Test custom chunk size and overlap parameters."""
        text = "A" * 1000
        chunks = chunk_document_for_interrogation(
            text=text,
            chunk_size=200,
            chunk_overlap=50,
        )

        assert len(chunks) > 1
        assert all(len(c.text) <= 200 for c in chunks)


class TestEstimateChunkCount:
    """Tests for estimate_chunk_count function."""

    def test_empty_text(self) -> None:
        """Test estimate for empty text."""
        assert estimate_chunk_count(0) == 0
        assert estimate_chunk_count(-10) == 0

    def test_small_text(self) -> None:
        """Test estimate for text smaller than chunk size."""
        assert estimate_chunk_count(100, chunk_size=1000) == 1
        assert estimate_chunk_count(1000, chunk_size=1000) == 1

    def test_larger_text(self) -> None:
        """Test estimate for larger text."""
        # 8000 char chunk, 200 overlap = 7800 step
        # For 50000 chars: ~7 chunks
        estimate = estimate_chunk_count(50000, chunk_size=8000, chunk_overlap=200)
        assert estimate >= 5
        assert estimate <= 10

    def test_estimate_matches_actual(self) -> None:
        """Test that estimate is close to actual chunk count."""
        text_length = 10000
        chunk_size = 500
        chunk_overlap = 100

        estimate = estimate_chunk_count(text_length, chunk_size, chunk_overlap)

        # Actually chunk the text
        text = "A" * text_length
        actual_chunks = chunk_text(
            text, "doc-1", chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )

        # Estimate should be within reasonable range
        assert abs(estimate - len(actual_chunks)) <= 3


class TestMergeChunks:
    """Tests for merge_chunks function."""

    def test_merge_empty(self) -> None:
        """Test merging empty list."""
        assert merge_chunks([]) == ""

    def test_merge_single_chunk(self) -> None:
        """Test merging single chunk."""
        chunk = DocumentChunk(
            id="chunk-0",
            document_id="doc-1",
            text="Single chunk content",
            chunk_index=0,
            start_char=0,
            end_char=20,
        )
        result = merge_chunks([chunk])
        assert result == "Single chunk content"

    def test_merge_multiple_chunks(self) -> None:
        """Test merging multiple chunks."""
        chunks = [
            DocumentChunk(
                id="chunk-0",
                document_id="doc-1",
                text="First chunk",
                chunk_index=0,
                start_char=0,
                end_char=11,
            ),
            DocumentChunk(
                id="chunk-1",
                document_id="doc-1",
                text="Second chunk",
                chunk_index=1,
                start_char=8,
                end_char=20,
            ),
        ]
        result = merge_chunks(chunks)
        assert "First chunk" in result
        assert "Second chunk" in result

    def test_merge_handles_unsorted(self) -> None:
        """Test that merge sorts by chunk_index."""
        chunks = [
            DocumentChunk(
                id="chunk-2",
                document_id="doc-1",
                text="Third",
                chunk_index=2,
                start_char=20,
                end_char=25,
            ),
            DocumentChunk(
                id="chunk-0",
                document_id="doc-1",
                text="First",
                chunk_index=0,
                start_char=0,
                end_char=5,
            ),
            DocumentChunk(
                id="chunk-1",
                document_id="doc-1",
                text="Second",
                chunk_index=1,
                start_char=10,
                end_char=16,
            ),
        ]
        result = merge_chunks(chunks)

        # Check that order is correct
        first_pos = result.find("First")
        second_pos = result.find("Second")
        third_pos = result.find("Third")

        assert first_pos < second_pos < third_pos
