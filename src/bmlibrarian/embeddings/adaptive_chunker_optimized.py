"""
Adaptive Text Chunker - Optimized Pure Function Implementation

This module provides a pure function for adaptive text chunking that handles
documents of different sizes efficiently with proper sentence boundaries.

Optimized for speed with:
- Single-pass regex sentence splitting
- Position tracking (no re-searching)
- List-based string building (no repeated concatenation)

Functions:
    adaptive_chunker: Returns list of chunk strings
    adaptive_chunker_with_positions: Returns list of (start, end, text) tuples
"""

import re
from dataclasses import dataclass
from typing import List, Tuple

# Compile regex once at module level for performance
# Matches sentence endings: . ! ? followed by whitespace or newline
# Protects common abbreviations with fixed-width lookbehinds
SENTENCE_BOUNDARY = re.compile(
    r'(?<!\bDr)'     # Not after "Dr"
    r'(?<!\bMr)'     # Not after "Mr"
    r'(?<!\bMs)'     # Not after "Ms"
    r'(?<!Mrs)'      # Not after "Mrs"
    r'(?<!Fig)'      # Not after "Fig"
    r'(?<!Tab)'      # Not after "Tab"
    r'(?<!vol)'      # Not after "vol"
    r'(?<!\bno)'     # Not after "no"
    r'(?<!\bpp)'     # Not after "pp"
    r'(?<!\bal)'     # Not after "al" (et al.)
    r'(?<!Jr)'       # Not after "Jr"
    r'(?<!Sr)'       # Not after "Sr"
    r'(?<!\bvs)'     # Not after "vs"
    r'(?<!\bca)'     # Not after "ca"
    r'([.!?])'       # capture the punctuation
    r'(\s+|\n+)',    # followed by whitespace
    re.IGNORECASE
)


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
        >>> len(chunks) >= 1
        True

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

    Uses position tracking and list building for optimal performance.

    Args:
        text: The text to chunk
        max_chars: Maximum size of each chunk in characters
        overlap_chars: Number of characters to overlap between chunks

    Returns:
        List of chunk strings
    """
    # Find all sentence boundaries (returns list of match objects)
    matches = list(SENTENCE_BOUNDARY.finditer(text))
    
    if not matches:
        # No sentence boundaries found, fall back to simple splitting
        return _simple_chunk_split(text, max_chars)
    
    # Build list of sentence end positions
    sentence_ends = [0]  # Start of text
    for match in matches:
        sentence_ends.append(match.end())
    sentence_ends.append(len(text))  # End of text
    
    # Build chunks by grouping sentences
    chunks = []
    chunk_start_idx = 0  # Index in sentence_ends array
    
    while chunk_start_idx < len(sentence_ends) - 1:
        chunk_start_pos = sentence_ends[chunk_start_idx]
        chunk_end_idx = chunk_start_idx + 1
        
        # Add sentences until we exceed max_chars
        while chunk_end_idx < len(sentence_ends):
            chunk_end_pos = sentence_ends[chunk_end_idx]
            chunk_len = chunk_end_pos - chunk_start_pos
            
            if chunk_len > max_chars:
                # This sentence would make chunk too large
                if chunk_end_idx == chunk_start_idx + 1:
                    # First sentence itself is too large, include it anyway
                    chunk_end_idx += 1
                break
            chunk_end_idx += 1
        
        # Extract chunk
        chunk_text = text[chunk_start_pos:sentence_ends[chunk_end_idx - 1]].strip()
        if chunk_text:
            chunks.append(chunk_text)
        
        # Calculate overlap for next chunk
        if chunk_end_idx < len(sentence_ends):
            # Find where to start next chunk (with overlap)
            overlap_target = sentence_ends[chunk_end_idx - 1] - overlap_chars
            
            # Find the sentence boundary closest to our overlap target
            next_start_idx = chunk_start_idx
            for i in range(chunk_start_idx, chunk_end_idx):
                if sentence_ends[i] >= overlap_target:
                    next_start_idx = i
                    break
            
            # Ensure we make progress (don't get stuck)
            if next_start_idx == chunk_start_idx:
                next_start_idx = chunk_end_idx - 1
            
            chunk_start_idx = next_start_idx
        else:
            break
    
    return chunks if chunks else [text.strip()]


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


# =============================================================================
# Position-aware chunking for database storage
# =============================================================================

@dataclass
class ChunkWithPosition:
    """
    Represents a chunk with its position in the source text.

    Attributes:
        chunk_no: Sequential chunk number (0-indexed).
        start_pos: Start position in source text (0-indexed).
        end_pos: End position in source text (inclusive).
        text: The chunk text content.
    """

    chunk_no: int
    start_pos: int
    end_pos: int
    text: str

    @property
    def length(self) -> int:
        """Return the length of the chunk in characters."""
        return self.end_pos - self.start_pos + 1


def adaptive_chunker_with_positions(
    text: str, max_chars: int = 1800, overlap_chars: int = 320
) -> List[ChunkWithPosition]:
    """
    Split text into chunks with position tracking for database storage.

    This function extends adaptive_chunker to return position information,
    enabling storage in semantic.chunks where text is extracted on-the-fly
    from document.full_text using start_pos and end_pos.

    Args:
        text: The text to chunk.
        max_chars: Maximum size of each chunk in characters.
        overlap_chars: Number of characters to overlap between chunks.

    Returns:
        List of ChunkWithPosition objects containing chunk_no, start_pos,
        end_pos (inclusive), and the text content.

    Examples:
        >>> text = "First sentence. Second sentence. Third sentence."
        >>> chunks = adaptive_chunker_with_positions(text, max_chars=30, overlap_chars=10)
        >>> chunks[0].start_pos
        0
        >>> text[chunks[0].start_pos:chunks[0].end_pos + 1] == chunks[0].text
        True
    """
    if not text or len(text.strip()) == 0:
        return []

    # For short texts, create a single chunk
    if len(text) <= max_chars:
        stripped = text.strip()
        if not stripped:
            return []
        # Find actual position of stripped content
        start = text.find(stripped[0])
        end = start + len(stripped) - 1
        return [ChunkWithPosition(chunk_no=0, start_pos=start, end_pos=end, text=stripped)]

    # For longer texts, chunk with sentence boundaries and position tracking
    return _chunk_with_boundaries_and_positions(text, max_chars, overlap_chars)


def _chunk_with_boundaries_and_positions(
    text: str, max_chars: int, overlap_chars: int
) -> List[ChunkWithPosition]:
    """
    Split text into chunks with proper sentence boundaries and position tracking.

    Args:
        text: The text to chunk.
        max_chars: Maximum size of each chunk in characters.
        overlap_chars: Number of characters to overlap between chunks.

    Returns:
        List of ChunkWithPosition objects.
    """
    # Find all sentence boundaries
    matches = list(SENTENCE_BOUNDARY.finditer(text))

    if not matches:
        # No sentence boundaries found, fall back to simple splitting
        return _simple_chunk_split_with_positions(text, max_chars)

    # Build list of sentence end positions
    sentence_ends = [0]  # Start of text
    for match in matches:
        sentence_ends.append(match.end())
    sentence_ends.append(len(text))  # End of text

    # Build chunks by grouping sentences
    chunks: List[ChunkWithPosition] = []
    chunk_no = 0
    chunk_start_idx = 0  # Index in sentence_ends array

    while chunk_start_idx < len(sentence_ends) - 1:
        chunk_start_pos = sentence_ends[chunk_start_idx]
        chunk_end_idx = chunk_start_idx + 1

        # Add sentences until we exceed max_chars
        while chunk_end_idx < len(sentence_ends):
            chunk_end_pos = sentence_ends[chunk_end_idx]
            chunk_len = chunk_end_pos - chunk_start_pos

            if chunk_len > max_chars:
                # This sentence would make chunk too large
                if chunk_end_idx == chunk_start_idx + 1:
                    # First sentence itself is too large, include it anyway
                    chunk_end_idx += 1
                break
            chunk_end_idx += 1

        # Extract chunk positions and text
        actual_end_pos = sentence_ends[chunk_end_idx - 1]
        chunk_text = text[chunk_start_pos:actual_end_pos].strip()

        if chunk_text:
            # Find actual stripped positions within the chunk range
            stripped_start = chunk_start_pos
            stripped_end = actual_end_pos - 1

            # Adjust for leading whitespace
            while stripped_start < actual_end_pos and text[stripped_start].isspace():
                stripped_start += 1

            # Adjust for trailing whitespace
            while stripped_end > stripped_start and text[stripped_end].isspace():
                stripped_end -= 1

            chunks.append(
                ChunkWithPosition(
                    chunk_no=chunk_no,
                    start_pos=stripped_start,
                    end_pos=stripped_end,
                    text=chunk_text,
                )
            )
            chunk_no += 1

        # Calculate overlap for next chunk
        if chunk_end_idx < len(sentence_ends):
            # Find where to start next chunk (with overlap)
            overlap_target = sentence_ends[chunk_end_idx - 1] - overlap_chars

            # Find the sentence boundary closest to our overlap target
            next_start_idx = chunk_start_idx
            for i in range(chunk_start_idx, chunk_end_idx):
                if sentence_ends[i] >= overlap_target:
                    next_start_idx = i
                    break

            # Ensure we make progress (don't get stuck)
            if next_start_idx == chunk_start_idx:
                next_start_idx = chunk_end_idx - 1

            chunk_start_idx = next_start_idx
        else:
            break

    if not chunks:
        # Fallback if no chunks were created
        return _simple_chunk_split_with_positions(text, max_chars)

    return chunks


def _simple_chunk_split_with_positions(
    text: str, max_chars: int
) -> List[ChunkWithPosition]:
    """
    Fallback: simple character-based chunking with position tracking.

    Args:
        text: The text to chunk.
        max_chars: Maximum size of each chunk in characters.

    Returns:
        List of ChunkWithPosition objects.
    """
    chunks: List[ChunkWithPosition] = []
    chunk_no = 0

    for i in range(0, len(text), max_chars):
        chunk_end = min(i + max_chars, len(text))
        chunk_content = text[i:chunk_end].strip()

        if chunk_content:
            # Find actual positions of stripped content
            start_pos = i
            end_pos = chunk_end - 1

            # Adjust for leading whitespace
            while start_pos < chunk_end and text[start_pos].isspace():
                start_pos += 1

            # Adjust for trailing whitespace
            while end_pos > start_pos and text[end_pos].isspace():
                end_pos -= 1

            chunks.append(
                ChunkWithPosition(
                    chunk_no=chunk_no,
                    start_pos=start_pos,
                    end_pos=end_pos,
                    text=chunk_content,
                )
            )
            chunk_no += 1

    return chunks
