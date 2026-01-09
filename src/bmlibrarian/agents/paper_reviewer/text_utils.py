"""
Text Processing Utilities for Paper Reviewer

Provides utilities for handling long texts without truncation.
Implements chunking and map-reduce strategies to process all content.
"""

import logging
from typing import List, Tuple, Optional, Callable, Any

from .constants import MAX_TEXT_LENGTH

logger = logging.getLogger(__name__)


# Chunk processing constants
CHUNK_OVERLAP = 200  # Characters of overlap between chunks
MIN_CHUNK_SIZE = 500  # Minimum chunk size to avoid tiny chunks


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

    chunks = []
    start = 0

    while start < len(text):
        # Calculate end position
        end = start + max_chunk_size

        if end >= len(text):
            # Last chunk - take everything remaining
            chunks.append(text[start:])
            break

        # Try to find a good break point (paragraph or sentence)
        chunk = text[start:end]

        # Look for paragraph break first
        para_break = chunk.rfind('\n\n')
        if para_break > MIN_CHUNK_SIZE:
            end = start + para_break + 2  # Include the double newline
        else:
            # Look for sentence break
            sentence_breaks = [
                chunk.rfind('. '),
                chunk.rfind('.\n'),
                chunk.rfind('? '),
                chunk.rfind('! '),
            ]
            best_break = max(b for b in sentence_breaks if b > MIN_CHUNK_SIZE) if any(b > MIN_CHUNK_SIZE for b in sentence_breaks) else -1
            if best_break > 0:
                end = start + best_break + 2  # Include the period and space

        chunks.append(text[start:end])

        # Move start position, accounting for overlap
        start = end - overlap if end - overlap > start else end

        # Prevent infinite loop
        if start >= len(text):
            break

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

    First maps each chunk to intermediate results, then reduces
    all intermediate results into a final result.

    Args:
        text: The full text to process
        map_fn: Function to process each chunk -> intermediate result
        reduce_fn: Function to combine intermediate results -> final result
        max_chunk_size: Maximum chunk size

    Returns:
        Final reduced result
    """
    if len(text) <= max_chunk_size:
        return map_fn(text)

    chunks = chunk_text(text, max_chunk_size)

    # Map phase: process each chunk
    intermediate_results = []
    for i, chunk in enumerate(chunks):
        logger.debug(f"Processing chunk {i+1}/{len(chunks)} ({len(chunk):,} chars)")
        result = map_fn(chunk)
        intermediate_results.append(result)

    # Reduce phase: combine results
    final_result = reduce_fn(intermediate_results)

    return final_result


def process_with_rolling_summary(
    text: str,
    process_fn: Callable[[str, Optional[str]], Tuple[Any, str]],
    max_chunk_size: int = MAX_TEXT_LENGTH,
    summary_max_length: int = 500,
) -> Any:
    """
    Process long text using rolling summaries.

    Each chunk is processed with context from previous chunk's summary.
    The final result includes all accumulated information.

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

    rolling_summary = None
    result = None

    for i, chunk in enumerate(chunks):
        logger.debug(f"Processing chunk {i+1}/{len(chunks)} ({len(chunk):,} chars)")
        result, rolling_summary = process_fn(chunk, rolling_summary)

        # Ensure summary doesn't grow unbounded
        if rolling_summary and len(rolling_summary) > summary_max_length:
            rolling_summary = rolling_summary[:summary_max_length] + "..."

    return result


def get_text_with_priority(
    document: dict,
    prefer_full_text: bool = True,
) -> Tuple[str, str]:
    """
    Get the best available text from a document.

    Returns the full text available, never truncates.

    Args:
        document: Document dictionary with various text fields
        prefer_full_text: Whether to prefer full_text over abstract

    Returns:
        Tuple of (text, source_field_name)
    """
    full_text = document.get('full_text', '') or ''
    abstract = document.get('abstract', '') or ''
    content = document.get('content', '') or ''
    text_field = document.get('text', '') or ''

    if prefer_full_text and full_text:
        return full_text, 'full_text'
    elif abstract:
        return abstract, 'abstract'
    elif full_text:
        return full_text, 'full_text'
    elif content:
        return content, 'content'
    elif text_field:
        return text_field, 'text'
    else:
        return '', 'none'


def combine_title_and_text(
    title: str,
    text: str,
    max_title_length: int = 500,
) -> str:
    """
    Combine title and text for analysis.

    Args:
        title: Document title
        text: Document text (abstract or full text)
        max_title_length: Maximum title length (titles are rarely long)

    Returns:
        Combined text with title prefix
    """
    if title and len(title) > max_title_length:
        # Titles should never be this long, but handle edge case
        title = title[:max_title_length]

    if title and text:
        return f"Title: {title}\n\n{text}"
    elif title:
        return f"Title: {title}"
    else:
        return text


__all__ = [
    'chunk_text',
    'process_with_map_reduce',
    'process_with_rolling_summary',
    'get_text_with_priority',
    'combine_title_and_text',
    'CHUNK_OVERLAP',
    'MIN_CHUNK_SIZE',
]
