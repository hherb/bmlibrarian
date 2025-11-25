"""
Adaptive Text Chunker - Optimized Pure Function Implementation

This module provides a pure function for adaptive text chunking that handles
documents of different sizes efficiently with proper sentence boundaries.

Optimized for speed with:
- Single-pass regex sentence splitting
- Position tracking (no re-searching)
- List-based string building (no repeated concatenation)
"""

import re
from typing import List

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
