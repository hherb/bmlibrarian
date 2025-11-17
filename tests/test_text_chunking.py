"""
Tests for text chunking utilities.

Tests the TextChunker class and chunk_text function for proper
sliding window text splitting with configurable overlap.
"""

import pytest
from bmlibrarian.agents.text_chunking import (
    TextChunker,
    TextChunk,
    chunk_text,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_CHUNK_OVERLAP
)


class TestTextChunk:
    """Test TextChunk dataclass."""

    def test_text_chunk_creation(self):
        """Test creating a TextChunk."""
        chunk = TextChunk(
            content="Test content",
            start_pos=0,
            end_pos=12,
            chunk_index=0,
            total_chunks=1
        )

        assert chunk.content == "Test content"
        assert chunk.start_pos == 0
        assert chunk.end_pos == 12
        assert chunk.chunk_index == 0
        assert chunk.total_chunks == 1
        assert chunk.size == 12

    def test_text_chunk_size_property(self):
        """Test TextChunk.size property."""
        chunk = TextChunk(
            content="A" * 100,
            start_pos=0,
            end_pos=100,
            chunk_index=0,
            total_chunks=1
        )
        assert chunk.size == 100


class TestTextChunker:
    """Test TextChunker class."""

    def test_initialization_default(self):
        """Test TextChunker initialization with defaults."""
        chunker = TextChunker()
        assert chunker.chunk_size == DEFAULT_CHUNK_SIZE
        assert chunker.overlap == DEFAULT_CHUNK_OVERLAP
        assert chunker.stride == DEFAULT_CHUNK_SIZE - DEFAULT_CHUNK_OVERLAP

    def test_initialization_custom(self):
        """Test TextChunker initialization with custom values."""
        chunker = TextChunker(chunk_size=1000, overlap=100)
        assert chunker.chunk_size == 1000
        assert chunker.overlap == 100
        assert chunker.stride == 900

    def test_initialization_invalid_chunk_size(self):
        """Test TextChunker rejects invalid chunk_size."""
        with pytest.raises(ValueError, match="chunk_size must be positive"):
            TextChunker(chunk_size=0, overlap=50)

        with pytest.raises(ValueError, match="chunk_size must be positive"):
            TextChunker(chunk_size=-100, overlap=50)

    def test_initialization_invalid_overlap(self):
        """Test TextChunker rejects invalid overlap."""
        with pytest.raises(ValueError, match="overlap must be non-negative"):
            TextChunker(chunk_size=100, overlap=-10)

    def test_initialization_overlap_exceeds_chunk_size(self):
        """Test TextChunker rejects overlap >= chunk_size."""
        with pytest.raises(ValueError, match="overlap .* must be less than chunk_size"):
            TextChunker(chunk_size=100, overlap=100)

        with pytest.raises(ValueError, match="overlap .* must be less than chunk_size"):
            TextChunker(chunk_size=100, overlap=150)

    def test_chunk_empty_text(self):
        """Test chunking empty text."""
        chunker = TextChunker(chunk_size=100, overlap=20)
        chunks = chunker.chunk_text("")
        assert chunks == []

    def test_chunk_short_text(self):
        """Test chunking text shorter than chunk_size."""
        chunker = TextChunker(chunk_size=100, overlap=20)
        text = "Short text"
        chunks = chunker.chunk_text(text)

        assert len(chunks) == 1
        assert chunks[0].content == text
        assert chunks[0].start_pos == 0
        assert chunks[0].end_pos == len(text)
        assert chunks[0].chunk_index == 0
        assert chunks[0].total_chunks == 1

    def test_chunk_exact_size(self):
        """Test chunking text exactly equal to chunk_size."""
        chunker = TextChunker(chunk_size=100, overlap=20)
        text = "A" * 100
        chunks = chunker.chunk_text(text)

        assert len(chunks) == 1
        assert chunks[0].content == text
        assert chunks[0].size == 100

    def test_chunk_two_chunks(self):
        """Test chunking text that requires two chunks."""
        chunker = TextChunker(chunk_size=100, overlap=20)
        text = "A" * 150  # Needs 2 chunks with overlap

        chunks = chunker.chunk_text(text)

        assert len(chunks) == 2

        # First chunk
        assert chunks[0].chunk_index == 0
        assert chunks[0].total_chunks == 2
        assert chunks[0].start_pos == 0
        assert chunks[0].end_pos == 100
        assert chunks[0].size == 100

        # Second chunk
        assert chunks[1].chunk_index == 1
        assert chunks[1].total_chunks == 2
        assert chunks[1].start_pos == 80  # 100 - 20 (overlap)
        assert chunks[1].end_pos == 150
        assert chunks[1].size == 70

    def test_chunk_overlap_correct(self):
        """Test that overlap between chunks is correct."""
        chunker = TextChunker(chunk_size=100, overlap=20)
        text = "A" * 150

        chunks = chunker.chunk_text(text)

        # Check overlap content
        overlap_from_first = chunks[0].content[-20:]
        overlap_from_second = chunks[1].content[:20]
        assert overlap_from_first == overlap_from_second
        assert overlap_from_first == "A" * 20

    def test_chunk_multiple_chunks(self):
        """Test chunking text that requires multiple chunks."""
        chunker = TextChunker(chunk_size=100, overlap=20)
        text = "A" * 350  # Should create 4 chunks

        chunks = chunker.chunk_text(text)

        # Verify number of chunks
        assert len(chunks) >= 3
        assert all(c.total_chunks == len(chunks) for c in chunks)

        # Verify chunk indices
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

        # Verify positions are sequential
        for i in range(len(chunks) - 1):
            assert chunks[i].end_pos > chunks[i + 1].start_pos  # Overlap
            assert chunks[i].start_pos < chunks[i + 1].start_pos  # Progress

    def test_chunk_preserves_content(self):
        """Test that chunking preserves all content when reassembled."""
        chunker = TextChunker(chunk_size=100, overlap=20)
        text = "ABCDEFGHIJ" * 50  # 500 chars

        chunks = chunker.chunk_text(text)

        # Reassemble without overlap (using stride)
        reassembled_parts = []
        for i, chunk in enumerate(chunks):
            if i == 0:
                # First chunk: take all
                reassembled_parts.append(chunk.content)
            else:
                # Subsequent chunks: skip overlap
                reassembled_parts.append(chunk.content[chunker.overlap:])

        reassembled = ''.join(reassembled_parts)
        assert reassembled == text

    def test_get_chunk_info_empty(self):
        """Test get_chunk_info with empty text."""
        chunker = TextChunker(chunk_size=100, overlap=20)
        info = chunker.get_chunk_info("")

        assert info['text_length'] == 0
        assert info['num_chunks'] == 0
        assert info['chunk_size'] == 100
        assert info['overlap'] == 20
        assert info['stride'] == 80
        assert info['avg_chunk_size'] == 0
        assert info['last_chunk_size'] == 0

    def test_get_chunk_info_single_chunk(self):
        """Test get_chunk_info with text that fits in one chunk."""
        chunker = TextChunker(chunk_size=100, overlap=20)
        text = "Short text"
        info = chunker.get_chunk_info(text)

        assert info['text_length'] == len(text)
        assert info['num_chunks'] == 1
        assert info['avg_chunk_size'] == len(text)
        assert info['last_chunk_size'] == len(text)

    def test_get_chunk_info_multiple_chunks(self):
        """Test get_chunk_info with text requiring multiple chunks."""
        chunker = TextChunker(chunk_size=100, overlap=20)
        text = "A" * 250
        info = chunker.get_chunk_info(text)

        assert info['text_length'] == 250
        assert info['num_chunks'] >= 2
        assert info['chunk_size'] == 100
        assert info['overlap'] == 20
        assert info['stride'] == 80

    def test_chunk_info_matches_actual_chunks(self):
        """Test that get_chunk_info matches actual chunking."""
        chunker = TextChunker(chunk_size=100, overlap=20)
        text = "A" * 350

        info = chunker.get_chunk_info(text)
        chunks = chunker.chunk_text(text)

        assert info['num_chunks'] == len(chunks)
        assert info['text_length'] == len(text)


class TestChunkTextFunction:
    """Test the convenience chunk_text function."""

    def test_chunk_text_default_params(self):
        """Test chunk_text with default parameters."""
        text = "A" * 5000
        chunks = chunk_text(text)

        assert len(chunks) > 0
        assert all(isinstance(c, TextChunk) for c in chunks)

    def test_chunk_text_custom_params(self):
        """Test chunk_text with custom parameters."""
        text = "A" * 500
        chunks = chunk_text(text, chunk_size=100, overlap=20)

        assert len(chunks) > 1
        assert chunks[0].size == 100
        # Verify overlap
        assert chunks[0].content[-20:] == chunks[1].content[:20]

    def test_chunk_text_zero_overlap(self):
        """Test chunk_text with zero overlap."""
        text = "A" * 200
        chunks = chunk_text(text, chunk_size=100, overlap=0)

        # With zero overlap, should have exactly 2 chunks
        assert len(chunks) == 2
        assert chunks[0].size == 100
        assert chunks[1].size == 100
        # No overlap
        assert chunks[0].end_pos == chunks[1].start_pos


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_very_small_chunks(self):
        """Test with very small chunk size."""
        chunker = TextChunker(chunk_size=10, overlap=2)
        text = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

        chunks = chunker.chunk_text(text)

        assert len(chunks) > 2
        assert all(c.size <= 10 for c in chunks)

    def test_very_large_overlap(self):
        """Test with large overlap (but still valid)."""
        chunker = TextChunker(chunk_size=100, overlap=95)
        text = "A" * 300

        chunks = chunker.chunk_text(text)

        # With 95% overlap, stride is only 5, so many chunks
        assert len(chunks) > 10

    def test_unicode_text(self):
        """Test chunking with Unicode text."""
        chunker = TextChunker(chunk_size=100, overlap=20)
        text = "Hello 世界! " * 50  # Mix ASCII and Unicode

        chunks = chunker.chunk_text(text)

        # Reassemble to verify no corruption
        reassembled_parts = []
        for i, chunk in enumerate(chunks):
            if i == 0:
                reassembled_parts.append(chunk.content)
            else:
                reassembled_parts.append(chunk.content[chunker.overlap:])

        reassembled = ''.join(reassembled_parts)
        assert reassembled == text

    def test_whitespace_preservation(self):
        """Test that whitespace is preserved in chunks."""
        chunker = TextChunker(chunk_size=50, overlap=10)
        text = "Line 1\n\nLine 2\n\nLine 3\n\nLine 4"

        chunks = chunker.chunk_text(text)

        # Verify whitespace is preserved
        all_content = ''.join(c.content for c in chunks)
        assert '\n\n' in all_content
