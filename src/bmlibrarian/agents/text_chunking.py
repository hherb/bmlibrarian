"""
Text Chunking Utilities for Document Processing

Provides sliding window text chunking with configurable parameters
for processing large documents that exceed LLM context limits.
"""

from typing import List, Tuple
from dataclasses import dataclass


# Default configuration constants
DEFAULT_CHUNK_SIZE = 10000  # characters
DEFAULT_CHUNK_OVERLAP = 250  # characters


@dataclass
class TextChunk:
    """Represents a chunk of text with metadata."""
    content: str
    start_pos: int
    end_pos: int
    chunk_index: int
    total_chunks: int

    @property
    def size(self) -> int:
        """Get the size of this chunk in characters."""
        return len(self.content)


class TextChunker:
    """
    Sliding window text chunker for processing large documents.

    Uses overlapping chunks to ensure no information is lost at
    chunk boundaries. This is particularly important for citation
    extraction and question-answering tasks.

    Example:
        >>> chunker = TextChunker(chunk_size=10000, overlap=250)
        >>> chunks = chunker.chunk_text(long_document)
        >>> for chunk in chunks:
        ...     process_chunk(chunk.content)
    """

    def __init__(self, chunk_size: int = DEFAULT_CHUNK_SIZE,
                 overlap: int = DEFAULT_CHUNK_OVERLAP):
        """
        Initialize the text chunker.

        Args:
            chunk_size: Maximum size of each chunk in characters (default: 10000)
            overlap: Number of characters to overlap between chunks (default: 250)

        Raises:
            ValueError: If chunk_size <= 0 or overlap < 0 or overlap >= chunk_size
        """
        if chunk_size <= 0:
            raise ValueError(f"chunk_size must be positive, got {chunk_size}")
        if overlap < 0:
            raise ValueError(f"overlap must be non-negative, got {overlap}")
        if overlap >= chunk_size:
            raise ValueError(f"overlap ({overlap}) must be less than chunk_size ({chunk_size})")

        self.chunk_size = chunk_size
        self.overlap = overlap
        self.stride = chunk_size - overlap  # How far to move for each chunk

    def chunk_text(self, text: str) -> List[TextChunk]:
        """
        Split text into overlapping chunks.

        Args:
            text: The text to chunk

        Returns:
            List of TextChunk objects with metadata

        Example:
            >>> chunker = TextChunker(chunk_size=100, overlap=20)
            >>> text = "A" * 250
            >>> chunks = chunker.chunk_text(text)
            >>> len(chunks)
            3
            >>> chunks[0].size
            100
            >>> chunks[1].start_pos
            80
        """
        if not text:
            return []

        text_length = len(text)

        # If text fits in a single chunk, return it as-is
        if text_length <= self.chunk_size:
            return [TextChunk(
                content=text,
                start_pos=0,
                end_pos=text_length,
                chunk_index=0,
                total_chunks=1
            )]

        chunks = []
        position = 0
        chunk_index = 0

        # Calculate total number of chunks needed
        # Last chunk may be smaller than chunk_size
        total_chunks = max(1, (text_length - self.overlap + self.stride - 1) // self.stride)

        while position < text_length:
            # Calculate end position for this chunk
            end_pos = min(position + self.chunk_size, text_length)

            # Extract chunk content
            chunk_content = text[position:end_pos]

            # Create chunk object
            chunk = TextChunk(
                content=chunk_content,
                start_pos=position,
                end_pos=end_pos,
                chunk_index=chunk_index,
                total_chunks=total_chunks
            )
            chunks.append(chunk)

            # Move to next chunk position
            # For the last chunk, we're done
            if end_pos >= text_length:
                break

            position += self.stride
            chunk_index += 1

        return chunks

    def get_chunk_info(self, text: str) -> dict:
        """
        Get information about how the text would be chunked without actually chunking it.

        Args:
            text: The text to analyze

        Returns:
            Dictionary with chunking statistics

        Example:
            >>> chunker = TextChunker(chunk_size=10000, overlap=250)
            >>> info = chunker.get_chunk_info(document_text)
            >>> print(f"Will create {info['num_chunks']} chunks")
        """
        text_length = len(text)

        if text_length == 0:
            return {
                'text_length': 0,
                'num_chunks': 0,
                'chunk_size': self.chunk_size,
                'overlap': self.overlap,
                'stride': self.stride,
                'avg_chunk_size': 0,
                'last_chunk_size': 0
            }

        if text_length <= self.chunk_size:
            return {
                'text_length': text_length,
                'num_chunks': 1,
                'chunk_size': self.chunk_size,
                'overlap': self.overlap,
                'stride': self.stride,
                'avg_chunk_size': text_length,
                'last_chunk_size': text_length
            }

        num_chunks = max(1, (text_length - self.overlap + self.stride - 1) // self.stride)

        # Calculate last chunk size
        last_chunk_start = (num_chunks - 1) * self.stride
        last_chunk_size = text_length - last_chunk_start

        # Calculate average chunk size
        total_chars = (num_chunks - 1) * self.chunk_size + last_chunk_size
        avg_chunk_size = total_chars / num_chunks

        return {
            'text_length': text_length,
            'num_chunks': num_chunks,
            'chunk_size': self.chunk_size,
            'overlap': self.overlap,
            'stride': self.stride,
            'avg_chunk_size': int(avg_chunk_size),
            'last_chunk_size': last_chunk_size
        }


def chunk_text(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE,
               overlap: int = DEFAULT_CHUNK_OVERLAP) -> List[TextChunk]:
    """
    Convenience function to chunk text with default or custom parameters.

    Args:
        text: The text to chunk
        chunk_size: Maximum size of each chunk in characters (default: 10000)
        overlap: Number of characters to overlap between chunks (default: 250)

    Returns:
        List of TextChunk objects

    Example:
        >>> chunks = chunk_text(long_document, chunk_size=5000, overlap=100)
        >>> for chunk in chunks:
        ...     print(f"Chunk {chunk.chunk_index + 1}/{chunk.total_chunks}: {chunk.size} chars")
    """
    chunker = TextChunker(chunk_size=chunk_size, overlap=overlap)
    return chunker.chunk_text(text)
