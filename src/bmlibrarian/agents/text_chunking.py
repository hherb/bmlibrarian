"""
Text Chunking Utilities for Document Processing

Sliding-window text chunking for documents that exceed LLM context limits.

The implementation lives in ``bmlib.llm.text_utils``. bmlib's chunker is
boundary-aware by default (it pulls a chunk's end back to a paragraph or
sentence break); bmlibrarian's has always cut at fixed widths. The document
interrogation agent embeds and scores these chunks when given raw text, so
moving a chunk boundary changes which passages it returns. This module
therefore pins ``boundary_aware=False`` so existing callers keep exactly the
chunks they had. Adopting boundary-aware chunking is a separate, deliberate
change that must re-baseline anything downstream of the chunk boundaries.
"""

from typing import Any, Dict, List

from bmlib.llm.text_utils import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    TextChunk,
)
from bmlib.llm.text_utils import TextChunker as _BmlibTextChunker


class TextChunker(_BmlibTextChunker):
    """
    Fixed-width sliding window chunker (bmlib's chunker, boundary-unaware).

    Uses overlapping chunks so no information is lost at chunk boundaries.

    Example:
        >>> chunker = TextChunker(chunk_size=10000, overlap=250)
        >>> chunks = chunker.chunk_text(long_document)
        >>> for chunk in chunks:
        ...     process_chunk(chunk.content)
    """

    def __init__(self, chunk_size: int = DEFAULT_CHUNK_SIZE,
                 overlap: int = DEFAULT_CHUNK_OVERLAP) -> None:
        """
        Initialize the text chunker.

        Args:
            chunk_size: Maximum size of each chunk in characters (default: 10000)
            overlap: Number of characters to overlap between chunks (default: 250)

        Raises:
            ValueError: If chunk_size <= 0 or overlap < 0 or overlap >= chunk_size
        """
        super().__init__(chunk_size=chunk_size, overlap=overlap, boundary_aware=False)

    @property
    def stride(self) -> int:
        """How far each chunk's start advances past the previous one's."""
        return self.chunk_size - self.overlap

    def get_chunk_info(self, text: str) -> Dict[str, Any]:
        """
        Chunk the text and summarise the result (count, sizes, stride).

        This chunks the whole text, so a caller that already holds the chunks
        pays for chunking twice (cheap next to any LLM call on them).

        Args:
            text: The text to analyze

        Returns:
            Dictionary with chunking statistics, including ``stride``
        """
        info = super().get_chunk_info(text)
        info['stride'] = self.stride
        return info


def chunk_text(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE,
               overlap: int = DEFAULT_CHUNK_OVERLAP) -> List[TextChunk]:
    """
    Chunk text at fixed widths with default or custom parameters.

    Args:
        text: The text to chunk
        chunk_size: Maximum size of each chunk in characters (default: 10000)
        overlap: Number of characters to overlap between chunks (default: 250)

    Returns:
        List of TextChunk objects
    """
    return TextChunker(chunk_size=chunk_size, overlap=overlap).chunk_text(text)


__all__ = [
    'DEFAULT_CHUNK_OVERLAP',
    'DEFAULT_CHUNK_SIZE',
    'TextChunk',
    'TextChunker',
    'chunk_text',
]
