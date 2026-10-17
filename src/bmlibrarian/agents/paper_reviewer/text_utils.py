"""
Text Processing Utilities for Paper Reviewer

Utilities for handling long texts without truncation: chunking and
map-reduce strategies that process all content.

The implementation lives in ``bmlib.llm.text_utils``, which was consolidated
from this module and ``agents/text_chunking.py``. This module keeps the paper
reviewer's own defaults (200-character overlap, chunks returned as strings);
the paragraph/sentence-aware splitting is bmlib's, and is the same rule this
module always used.
"""

import logging
from typing import List

from bmlib.llm.text_utils import (
    DEFAULT_MIN_CHUNK_SIZE,
    combine_title_and_text,
    get_text_with_priority,
    process_with_map_reduce,
    process_with_rolling_summary,
)
from bmlib.llm.text_utils import chunk_text as _bmlib_chunk_text

from .constants import MAX_TEXT_LENGTH

logger = logging.getLogger(__name__)


# Chunk processing constants
CHUNK_OVERLAP = 200  # Characters of overlap between chunks
MIN_CHUNK_SIZE = DEFAULT_MIN_CHUNK_SIZE  # Minimum offset for a boundary break


def chunk_text(
    text: str,
    max_chunk_size: int = MAX_TEXT_LENGTH,
    overlap: int = CHUNK_OVERLAP,
) -> List[str]:
    """
    Split text into overlapping chunks for processing.

    Uses paragraph-aware splitting to avoid breaking sentences.
    Never discards any text - all content is preserved across chunks.

    Args:
        text: The full text to chunk
        max_chunk_size: Maximum size of each chunk in characters
        overlap: Number of overlapping characters between chunks

    Returns:
        List of text chunks covering the entire input
    """
    if len(text) <= max_chunk_size:
        return [text]

    chunks = [
        chunk.content
        for chunk in _bmlib_chunk_text(
            text,
            chunk_size=max_chunk_size,
            overlap=overlap,
            boundary_aware=True,
            min_chunk_size=MIN_CHUNK_SIZE,
        )
    ]
    logger.info(f"Split {len(text):,} characters into {len(chunks)} chunks")
    return chunks


__all__ = [
    'chunk_text',
    'process_with_map_reduce',
    'process_with_rolling_summary',
    'get_text_with_priority',
    'combine_title_and_text',
    'CHUNK_OVERLAP',
    'MIN_CHUNK_SIZE',
]
