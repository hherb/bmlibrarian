"""
Database search utilities with retry and query reformulation.

This module provides robust database search functionality with automatic
retry mechanisms and progressive query simplification.
"""

import logging
from typing import Dict, List, Callable, Optional

from .query_syntax import simplify_query_for_retry, extract_keywords_from_question, fix_tsquery_syntax

logger = logging.getLogger(__name__)


def search_with_retry(
    query_info: Dict[str, str],
    max_results: int,
    max_retries: int,
    auto_fix_syntax: bool,
    callback: Optional[Callable[[str, str], None]] = None
) -> List[Dict]:
    """
    Search database with automatic retry and query reformulation on syntax errors.

    Args:
        query_info: Dictionary containing 'db_query', 'question', and 'target_claim'
        max_results: Maximum number of results to return
        max_retries: Maximum number of retry attempts
        auto_fix_syntax: Whether to automatically fix syntax errors
        callback: Optional callback function for progress updates

    Returns:
        List of document dictionaries, or empty list if all attempts fail
    """
    try:
        from ...database import find_abstracts
    except ImportError:
        logger.error("Database module not available")
        return []

    original_query = query_info['db_query']
    question = query_info['question']
    target_claim = query_info['target_claim']

    def _call_callback(event: str, message: str):
        """Helper to call callback if provided."""
        if callback:
            try:
                callback(event, message)
            except Exception as e:
                logger.warning(f"Callback error: {e}")

    # Pre-process the original query to fix obvious quote mismatches
    # This handles cases where LLM generates malformed queries like: Alzheimer's disease'
    original_query_before = original_query
    original_query = fix_tsquery_syntax(original_query)
    if original_query != original_query_before:
        logger.info(f"Query preprocessed: '{original_query_before}' -> '{original_query}'")

    for attempt in range(max_retries + 1):  # +1 for the original attempt
        try:
            if attempt == 0:
                # First attempt: use pre-processed original query
                current_query = original_query
                _call_callback("database_search", f"Attempting search: {target_claim[:50]}...")
            else:
                # Retry attempts: reformulate query
                if auto_fix_syntax:
                    current_query = simplify_query_for_retry(original_query, attempt)
                else:
                    # Fallback to keywords if no auto-fix
                    current_query = extract_keywords_from_question(question)

                _call_callback(
                    "database_search",
                    f"Retry {attempt}/{max_retries}: Reformulated query for '{target_claim[:40]}...'"
                )
                logger.info(f"Query retry {attempt}: '{original_query}' -> '{current_query}'")

            # Attempt database search
            results_generator = find_abstracts(
                current_query,
                max_rows=max_results,
                plain=False  # Use advanced to_tsquery syntax
            )

            # Convert generator to list
            results = list(results_generator)

            if results:
                # Success! Log and return results
                if attempt > 0:
                    logger.info(f"Query retry {attempt} succeeded with {len(results)} results")
                    _call_callback("database_search", f"Retry {attempt} succeeded: {len(results)} results found")
                else:
                    logger.debug(f"Query succeeded on first attempt: {len(results)} results")

                return results
            else:
                # No results, but no error - this is not a syntax error
                if attempt == 0:
                    logger.info(f"Query returned no results: '{current_query}'")
                continue

        except Exception as e:
            error_msg = str(e).lower()

            # Check if this is a tsquery syntax error
            if 'syntax error in tsquery' in error_msg or 'tsquery' in error_msg:
                if attempt < max_retries:
                    logger.warning(f"tsquery syntax error on attempt {attempt + 1}: {e}")
                    _call_callback(
                        "database_search",
                        f"Query syntax error, attempting reformulation (attempt {attempt + 1}/{max_retries})..."
                    )
                    continue  # Try next reformulation
                else:
                    # Final attempt failed with syntax error
                    logger.error(f"Query failed after {max_retries} retries with syntax error: {e}")
                    _call_callback(
                        "database_search",
                        f"Query failed after {max_retries} retries: {str(e)[:100]}..."
                    )
                    break
            else:
                # Non-syntax error (database connection, etc.)
                logger.error(f"Database search failed with non-syntax error: {e}")
                _call_callback("database_search", f"Database error: {str(e)[:100]}...")
                break

    # All attempts failed
    logger.warning(f"All {max_retries + 1} search attempts failed for question: '{question[:100]}...'")
    return []
