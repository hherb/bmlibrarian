"""
Text Processing Utilities for Paper Reviewer

Utilities for handling long texts without truncation: chunking and
map-reduce strategies that process all content.

The chunking implementation lives in ``bmlib.llm.text_utils``, which was
consolidated from this module and ``agents/text_chunking.py``. This module
keeps the paper reviewer's own geometry: chunks of ``MAX_TEXT_LENGTH``
characters with a 200-character overlap, returned as strings. The
paragraph/sentence-aware splitting is bmlib's, and is the same rule this
module always used. ``process_with_map_reduce`` and
``process_with_rolling_summary`` are kept here (not re-exported from bmlib)
so that they chunk with this geometry too; bmlib's versions use its own
defaults (250-character overlap, ``DEFAULT_CHUNK_SIZE``).
"""

import logging
from typing import Any, Callable, List, Optional, Tuple

from bmlib.llm.text_utils import (
    DEFAULT_MIN_CHUNK_SIZE,
    combine_title_and_text,
    get_text_with_priority,
)
from bmlib.llm.text_utils import chunk_text as _bmlib_chunk_text

from .constants import MAX_TEXT_LENGTH

logger = logging.getLogger(__name__)


# Chunk processing constants
CHUNK_OVERLAP = 200  # Characters of overlap between chunks
# A paragraph/sentence break ends a chunk only if it lies more than this many
# characters into the chunk window; otherwise the chunk is cut at
# max_chunk_size.
MIN_CHUNK_SIZE = DEFAULT_MIN_CHUNK_SIZE
ROLLING_SUMMARY_MAX_LENGTH = 500  # Characters of rolling summary carried forward


def chunk_text(
    text: str,
    max_chunk_size: int = MAX_TEXT_LENGTH,
    overlap: int = CHUNK_OVERLAP,
) -> List[str]:
    """
    Split text into overlapping chunks for processing.

    Ends each chunk at a paragraph break, else a sentence break, if one lies
    beyond ``MIN_CHUNK_SIZE`` in the window; otherwise cuts at
    ``max_chunk_size``. Never discards any text - all content is preserved
    across chunks.

    Args:
        text: The full text to chunk
        max_chunk_size: Maximum size of each chunk in characters
        overlap: Number of overlapping characters between chunks

    Returns:
        List of text chunks covering the entire input (``[text]`` when the
        text fits in one chunk, including empty text)

    Raises:
        ValueError: If the text needs chunking and ``max_chunk_size <= 0``,
            ``overlap < 0`` or ``overlap >= max_chunk_size``
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


def process_with_map_reduce(
    text: str,
    map_fn: Callable[[str], Any],
    reduce_fn: Callable[[List[Any]], Any],
    max_chunk_size: int = MAX_TEXT_LENGTH,
) -> Any:
    """
    Process long text using map-reduce pattern.

    First maps each chunk (from :func:`chunk_text`) to intermediate results,
    then reduces all intermediate results into a final result.

    Args:
        text: The full text to process
        map_fn: Function to process each chunk -> intermediate result
        reduce_fn: Function to combine intermediate results -> final result
        max_chunk_size: Maximum chunk size

    Returns:
        Final reduced result (or ``map_fn(text)`` when the text fits in one
        chunk)
    """
    if len(text) <= max_chunk_size:
        return map_fn(text)

    chunks = chunk_text(text, max_chunk_size)
    intermediate_results = []
    for i, chunk in enumerate(chunks):
        logger.debug(f"Processing chunk {i+1}/{len(chunks)} ({len(chunk):,} chars)")
        intermediate_results.append(map_fn(chunk))

    return reduce_fn(intermediate_results)


def process_with_rolling_summary(
    text: str,
    process_fn: Callable[[str, Optional[str]], Tuple[Any, str]],
    max_chunk_size: int = MAX_TEXT_LENGTH,
    summary_max_length: int = ROLLING_SUMMARY_MAX_LENGTH,
) -> Any:
    """
    Process long text using rolling summaries.

    Each chunk (from :func:`chunk_text`) is processed with context from the
    previous chunk's summary, which is truncated to ``summary_max_length``.

    Args:
        text: The full text to process
        process_fn: Function(chunk, previous_summary) -> (result, new_summary)
        max_chunk_size: Maximum chunk size
        summary_max_length: Maximum length of rolling summary

    Returns:
        Result from processing the final chunk (with all accumulated context)
    """
    if len(text) <= max_chunk_size:
        result, _ = process_fn(text, None)
        return result

    chunks = chunk_text(text, max_chunk_size)
    rolling_summary: Optional[str] = None
    result = None
    for i, chunk in enumerate(chunks):
        logger.debug(f"Processing chunk {i+1}/{len(chunks)} ({len(chunk):,} chars)")
        result, rolling_summary = process_fn(chunk, rolling_summary)
        # Ensure summary doesn't grow unbounded
        if rolling_summary and len(rolling_summary) > summary_max_length:
            rolling_summary = rolling_summary[:summary_max_length] + "..."

    return result


__all__ = [
    'chunk_text',
    'process_with_map_reduce',
    'process_with_rolling_summary',
    'get_text_with_priority',
    'combine_title_and_text',
    'CHUNK_OVERLAP',
    'MIN_CHUNK_SIZE',
    'ROLLING_SUMMARY_MAX_LENGTH',
]
