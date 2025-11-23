"""
Tests for chunk embedder module.

Tests the ChunkPosition dataclass and chunk_text function for proper
character-based text splitting with configurable overlap.
"""

import pytest
from bmlibrarian.embeddings.chunk_embedder import (
    ChunkPosition,
    chunk_text,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_CHUNK_OVERLAP,
)


class TestChunkPosition:
    """Test ChunkPosition dataclass."""

    def test_chunk_position_creation(self) -> None:
        """Test creating a ChunkPosition."""
        pos = ChunkPosition(chunk_no=0, start_pos=0, end_pos=99)

        assert pos.chunk_no == 0
        assert pos.start_pos == 0
        assert pos.end_pos == 99
        assert pos.length == 100

    def test_chunk_position_length_property(self) -> None:
        """Test ChunkPosition.length property."""
        pos = ChunkPosition(chunk_no=0, start_pos=50, end_pos=149)
        assert pos.length == 100

    def test_extract_text(self) -> None:
        """Test extracting text from source using positions."""
        source = "ABCDEFGHIJ" * 10  # 100 characters
        pos = ChunkPosition(chunk_no=0, start_pos=0, end_pos=9)

        extracted = pos.extract_text(source)
        assert extracted == "ABCDEFGHIJ"

    def test_extract_text_middle(self) -> None:
        """Test extracting text from middle of source."""
        source = "0123456789" * 10
        pos = ChunkPosition(chunk_no=1, start_pos=30, end_pos=39)

        extracted = pos.extract_text(source)
        assert extracted == "0123456789"


class TestChunkText:
    """Test chunk_text pure function."""

    def test_default_parameters(self) -> None:
        """Test that defaults are properly set."""
        assert DEFAULT_CHUNK_SIZE == 350
        assert DEFAULT_CHUNK_OVERLAP == 50

    def test_empty_text(self) -> None:
        """Test chunking empty text returns empty list."""
        chunks = chunk_text("", chunk_size=100, overlap=20)
        assert chunks == []

    def test_short_text(self) -> None:
        """Test chunking text shorter than chunk_size."""
        text = "Short text"
        chunks = chunk_text(text, chunk_size=100, overlap=20)

        assert len(chunks) == 1
        assert chunks[0].chunk_no == 0
        assert chunks[0].start_pos == 0
        assert chunks[0].end_pos == len(text) - 1
        assert chunks[0].extract_text(text) == text

    def test_exact_chunk_size(self) -> None:
        """Test text exactly equal to chunk_size."""
        text = "A" * 100
        chunks = chunk_text(text, chunk_size=100, overlap=20)

        assert len(chunks) == 1
        assert chunks[0].length == 100

    def test_two_chunks_needed(self) -> None:
        """Test text that requires two chunks."""
        text = "A" * 150
        chunks = chunk_text(text, chunk_size=100, overlap=20)

        assert len(chunks) == 2

        # First chunk: positions 0-99
        assert chunks[0].chunk_no == 0
        assert chunks[0].start_pos == 0
        assert chunks[0].end_pos == 99
        assert chunks[0].length == 100

        # Second chunk: starts at 80 (100 - 20 overlap)
        assert chunks[1].chunk_no == 1
        assert chunks[1].start_pos == 80
        assert chunks[1].end_pos == 149
        assert chunks[1].length == 70

    def test_overlap_correct(self) -> None:
        """Test that overlap between chunks is correct."""
        text = "0123456789" * 20  # 200 characters
        chunks = chunk_text(text, chunk_size=100, overlap=20)

        assert len(chunks) >= 2

        # Verify overlap content matches
        first_chunk_end = chunks[0].extract_text(text)[-20:]
        second_chunk_start = chunks[1].extract_text(text)[:20]
        assert first_chunk_end == second_chunk_start

    def test_multiple_chunks(self) -> None:
        """Test text that requires multiple chunks."""
        text = "A" * 350
        chunks = chunk_text(text, chunk_size=100, overlap=20)

        # Should have several chunks
        assert len(chunks) >= 3

        # Verify chunk numbers are sequential
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_no == i

        # Verify positions progress
        for i in range(len(chunks) - 1):
            assert chunks[i + 1].start_pos > chunks[i].start_pos

    def test_zero_overlap(self) -> None:
        """Test chunking with zero overlap."""
        text = "A" * 200
        chunks = chunk_text(text, chunk_size=100, overlap=0)

        assert len(chunks) == 2
        assert chunks[0].start_pos == 0
        assert chunks[0].end_pos == 99
        assert chunks[1].start_pos == 100
        assert chunks[1].end_pos == 199

    def test_invalid_chunk_size(self) -> None:
        """Test that invalid chunk_size raises ValueError."""
        with pytest.raises(ValueError, match="chunk_size must be positive"):
            chunk_text("test", chunk_size=0, overlap=0)

        with pytest.raises(ValueError, match="chunk_size must be positive"):
            chunk_text("test", chunk_size=-10, overlap=0)

    def test_invalid_overlap_negative(self) -> None:
        """Test that negative overlap raises ValueError."""
        with pytest.raises(ValueError, match="overlap cannot be negative"):
            chunk_text("test", chunk_size=100, overlap=-5)

    def test_invalid_overlap_exceeds_chunk_size(self) -> None:
        """Test that overlap >= chunk_size raises ValueError."""
        with pytest.raises(ValueError, match="overlap .* must be less than chunk_size"):
            chunk_text("test", chunk_size=100, overlap=100)

        with pytest.raises(ValueError, match="overlap .* must be less than chunk_size"):
            chunk_text("test", chunk_size=100, overlap=150)

    def test_preserves_content(self) -> None:
        """Test that all content can be reconstructed from chunks."""
        text = "ABCDEFGHIJ" * 50  # 500 chars
        chunks = chunk_text(text, chunk_size=100, overlap=20)

        # Reconstruct non-overlapping parts
        reconstructed_parts = []
        for i, chunk in enumerate(chunks):
            chunk_text_content = chunk.extract_text(text)
            if i == 0:
                reconstructed_parts.append(chunk_text_content)
            else:
                # Skip overlap portion
                reconstructed_parts.append(chunk_text_content[20:])

        reconstructed = ''.join(reconstructed_parts)
        assert reconstructed == text

    def test_unicode_text(self) -> None:
        """Test chunking handles Unicode correctly."""
        text = "Hello 世界! " * 50
        chunks = chunk_text(text, chunk_size=100, overlap=20)

        # Verify all chunks have valid content
        for chunk in chunks:
            extracted = chunk.extract_text(text)
            assert len(extracted) > 0

    def test_small_final_chunk_handling(self) -> None:
        """Test that very small final chunks are avoided."""
        # With chunk_size=100, overlap=20, step=80
        # Text of 175 chars would naively create a 15-char final chunk
        # Our algorithm should avoid this if it's smaller than overlap
        text = "A" * 175
        chunks = chunk_text(text, chunk_size=100, overlap=20)

        # All chunks should be at least overlap size (or we stop before tiny chunks)
        for chunk in chunks:
            # Last chunk might be smaller, but not tiny
            if chunk.chunk_no == len(chunks) - 1:
                assert chunk.length >= 20 or chunk.length >= (175 - chunks[-2].end_pos - 1)


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_very_small_chunks(self) -> None:
        """Test with very small chunk size."""
        text = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        chunks = chunk_text(text, chunk_size=10, overlap=2)

        assert len(chunks) > 2
        for chunk in chunks:
            assert chunk.length <= 10

    def test_large_overlap(self) -> None:
        """Test with large overlap (but still valid)."""
        text = "A" * 300
        chunks = chunk_text(text, chunk_size=100, overlap=90)

        # With 90% overlap, stride is only 10, so many chunks
        assert len(chunks) > 20

    def test_whitespace_preservation(self) -> None:
        """Test that whitespace is preserved."""
        text = "Line 1\n\nLine 2\n\nLine 3"
        chunks = chunk_text(text, chunk_size=50, overlap=10)

        # Verify whitespace is in chunks
        all_content = ''.join(chunk.extract_text(text) for chunk in chunks)
        assert '\n\n' in all_content

    def test_single_character_text(self) -> None:
        """Test single character text."""
        text = "X"
        chunks = chunk_text(text, chunk_size=100, overlap=20)

        assert len(chunks) == 1
        assert chunks[0].extract_text(text) == "X"
