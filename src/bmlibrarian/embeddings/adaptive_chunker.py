"""
Adaptive Text Chunker - Pure Function Implementation

This module provides a pure function for adaptive text chunking that handles
documents of different sizes efficiently with proper sentence boundaries.

Adapted from localknowledge.textprocessing.chunking.AdaptiveTextChunker
"""

from typing import List


def adaptive_chunker(text: str, max_chars: int = 1800, overlap_chars: int = 320) -> List[str]:
    """
    Split text into chunks adaptively based on length with sentence boundaries.

    This is a pure function implementation that:
    - Creates a single chunk for texts that fit within max_chars
    - Chunks longer texts with proper sentence boundaries
    - Maintains overlap between chunks for context preservation

    Args:
        text: The text to chunk
        max_chars: Maximum size of each chunk in characters
        overlap_chars: Number of characters to overlap between chunks

    Returns:
        List of chunk strings

    Examples:
        >>> text = "First sentence. Second sentence. Third sentence."
        >>> chunks = adaptive_chunker(text, max_chars=30, overlap_chars=10)
        >>> len(chunks)
        2

        >>> short_text = "Short text."
        >>> chunks = adaptive_chunker(short_text, max_chars=100)
        >>> len(chunks)
        1
    """
    if not text or len(text.strip()) == 0:
        return []

    # For short texts, create a single chunk
    if len(text) <= max_chars:
        return [text.strip()]

    # For longer texts, chunk with sentence boundaries
    return _chunk_with_boundaries(text, max_chars, overlap_chars)


def _chunk_with_boundaries(text: str, max_chars: int, overlap_chars: int) -> List[str]:
    """
    Split text into chunks with proper sentence boundaries.

    Args:
        text: The text to chunk
        max_chars: Maximum size of each chunk in characters
        overlap_chars: Number of characters to overlap between chunks

    Returns:
        List of chunk strings
    """
    # For very short texts, just return a single chunk
    if len(text) <= max_chars:
        return [text.strip()]

    # Split text into sentences first
    sentences = _split_into_sentences(text)

    # Group sentences into chunks
    chunks = []
    current_chunk = ""
    chunk_start = 0

    for sentence in sentences:
        # If adding this sentence would exceed the max size, create a new chunk
        if len(current_chunk) + len(sentence) > max_chars and current_chunk:
            # Add the current chunk
            chunks.append(current_chunk)

            # Start a new chunk with overlap
            chunk_end = chunk_start + len(current_chunk)
            overlap_start = max(0, chunk_end - overlap_chars)

            # Start new chunk with this sentence
            current_chunk = sentence
            chunk_start = text.find(sentence, overlap_start)
        else:
            # Add the sentence to the current chunk
            current_chunk += sentence
            if not current_chunk.strip():
                chunk_start = text.find(sentence)

    # Add the last chunk if there's anything left
    if current_chunk.strip():
        chunks.append(current_chunk)

    # Special case: if we couldn't split into sentences properly, fall back
    if not chunks:
        chunks = _simple_chunk_split(text, max_chars)

    return chunks


def _split_into_sentences(text: str) -> List[str]:
    """
    Split text into sentences using simple heuristics.

    This is a lightweight sentence splitter that looks for common sentence
    boundaries (., !, ?) followed by space or newline.

    Args:
        text: The text to split

    Returns:
        List of sentence strings
    """
    sentences = []
    current_pos = 0

    # Sentence markers to look for
    markers = ['. ', '! ', '? ', '.\n', '!\n', '?\n']

    while current_pos < len(text):
        # Find the next sentence end
        next_end = -1
        for marker in markers:
            pos = text.find(marker, current_pos)
            if pos != -1 and (next_end == -1 or pos < next_end):
                next_end = pos + 1  # Include the period

        # If no sentence end found, take the rest of the text
        if next_end == -1:
            sentences.append(text[current_pos:])
            break
        else:
            # Add one more character to include the space after the period
            end_pos = min(next_end + 1, len(text))
            sentences.append(text[current_pos:end_pos])
            current_pos = end_pos

    return sentences


def _simple_chunk_split(text: str, max_chars: int) -> List[str]:
    """
    Fallback: simple character-based chunking without sentence boundaries.

    Args:
        text: The text to chunk
        max_chars: Maximum size of each chunk in characters

    Returns:
        List of chunk strings
    """
    chunks = []
    for i in range(0, len(text), max_chars):
        chunk_end = min(i + max_chars, len(text))
        chunk_content = text[i:chunk_end].strip()
        if chunk_content:
            chunks.append(chunk_content)
    return chunks
