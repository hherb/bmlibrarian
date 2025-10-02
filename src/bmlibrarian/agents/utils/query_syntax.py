"""
PostgreSQL tsquery syntax utilities for query validation and fixing.

This module provides functions for cleaning, validating, and fixing PostgreSQL
to_tsquery syntax errors while preserving query complexity and structure.
"""

import re
import logging

logger = logging.getLogger(__name__)


def fix_tsquery_syntax(query: str) -> str:
    """
    Fix PostgreSQL tsquery syntax errors without oversimplifying queries.

    Focuses on quote escaping and malformed syntax patterns that cause
    "syntax error in tsquery" without reducing query complexity.

    Args:
        query: The original tsquery string

    Returns:
        Fixed tsquery string with corrected syntax but preserved complexity
    """
    # Basic cleanup - remove function prefixes
    query = query.strip()
    if query.startswith(('to_tsquery:', 'tsquery:')):
        query = re.sub(r'^[a-z_]+:\s*', '', query, flags=re.IGNORECASE)

    # Remove outer quotes that wrap the entire query
    if (query.startswith('"') and query.endswith('"')) or (query.startswith("'") and query.endswith("'")):
        query = query[1:-1]

    # CRITICAL FIX: Handle the specific malformed quote patterns causing errors
    # Fix patterns like: '(''phrase''' -> 'phrase'
    query = re.sub(r"'\(\s*''([^']+)''\s*'", r"'\1'", query)
    query = re.sub(r"'\(\s*''([^']+)'''\s*'", r"'\1'", query)

    # Fix patterns like: '''phrase''' -> 'phrase'
    query = re.sub(r"'''([^']+)'''", r"'\1'", query)
    query = re.sub(r"''([^']+)''", r"'\1'", query)

    # Fix quotes around operators: '&' -> &, '|' -> |
    query = re.sub(r"'(\s*[&|]\s*)'", r'\1', query)

    # Fix quotes around parentheses: '(' -> (, ')' -> )
    query = re.sub(r"'\s*\(\s*'", '(', query)
    query = re.sub(r"'\s*\)\s*'", ')', query)

    # Convert double quotes to single quotes consistently
    query = re.sub(r'"([^"]*)"', r"'\1'", query)

    # Handle operator syntax
    query = re.sub(r'\sOR\s', ' | ', query, flags=re.IGNORECASE)
    query = re.sub(r'\sAND\s', ' & ', query, flags=re.IGNORECASE)

    # Clean up spacing around operators (preserve structure)
    query = re.sub(r'\s*\|\s*', ' | ', query)
    query = re.sub(r'\s*&\s*', ' & ', query)
    query = re.sub(r'\s*\(\s*', '(', query)
    query = re.sub(r'\s*\)\s*', ')', query)

    # Fix phrase quoting: add quotes to multi-word phrases, remove from single words
    def fix_phrase_quoting(text):
        # Split on operators and parentheses while preserving them
        parts = re.split(r'(\s*[&|()]\s*)', text)
        fixed_parts = []

        for part in parts:
            part = part.strip()
            # Skip operators and parentheses
            if not part or part in ['&', '|', '(', ')'] or re.match(r'^\s*[&|()]+\s*$', part):
                fixed_parts.append(part)
                continue

            # Clean existing quotes
            clean_part = part.strip("'\"")

            # Quote multi-word phrases (including hyphenated terms), leave single words unquoted
            if ' ' in clean_part or '-' in clean_part:
                # Escape internal quotes and wrap in quotes
                escaped = clean_part.replace("'", "''")
                fixed_parts.append(f"'{escaped}'")
            else:
                fixed_parts.append(clean_part)

        return ''.join(fixed_parts)

    query = fix_phrase_quoting(query)

    # Fix empty quoted strings
    query = re.sub(r"'\s*'", '', query)

    # Clean up extra spaces
    query = re.sub(r'\s+', ' ', query).strip()

    return query


def simplify_query_for_retry(query: str, attempt: int) -> str:
    """
    Fix tsquery syntax errors with progressive approaches while preserving query complexity.

    Args:
        query: The query to fix
        attempt: The retry attempt number (1, 2, 3, etc.)

    Returns:
        Query string with syntax fixes applied
    """
    if attempt == 1:
        # First retry: Apply comprehensive syntax fixes but preserve structure
        query = fix_tsquery_syntax(query)

        # Additional fix for specific problematic patterns seen in errors
        # Fix patterns like: & '('"phrase"')' -> & 'phrase'
        query = re.sub(r"&\s*'\(\s*['\"]([^'\"]+)['\"]?\s*\)\s*'", r"& '\1'", query)
        query = re.sub(r"\|\s*'\(\s*['\"]([^'\"]+)['\"]?\s*\)\s*'", r"| '\1'", query)

        # Fix standalone quotes around complex expressions
        query = re.sub(r"'\s*\(([^)]+)\)\s*'", r'(\1)', query)

    elif attempt == 2:
        # Second retry: More aggressive quote fixing while preserving logic
        query = fix_tsquery_syntax(query)

        # Handle nested quote issues more aggressively
        # Fix pattern: (phrase1 | phrase2) & '('"phrase3"')'
        query = re.sub(r"'\(\s*['\"]([^'\"]+)['\"]?\s*\)'", r"'\1'", query)

        # Ensure proper phrase quoting - multi-word phrases get quotes, single words don't
        def fix_phrase_quoting(text):
            # Split on operators and parentheses while preserving them
            parts = re.split(r'(\s*[&|()]\s*)', text)
            fixed_parts = []

            for part in parts:
                part = part.strip()
                # Skip operators and parentheses
                if not part or part in ['&', '|', '(', ')'] or re.match(r'^\s*[&|()]+\s*$', part):
                    fixed_parts.append(part)
                    continue

                # Clean existing quotes
                clean_part = part.strip("'\"")

                # Quote multi-word phrases, leave single words unquoted
                if ' ' in clean_part:
                    # Escape internal quotes and wrap in quotes
                    escaped = clean_part.replace("'", "''")
                    fixed_parts.append(f"'{escaped}'")
                else:
                    fixed_parts.append(clean_part)

            return ''.join(fixed_parts)

        query = fix_phrase_quoting(query)

    elif attempt >= 3:
        # Final retry: Preserve original query but ensure basic syntax correctness
        query = fix_tsquery_syntax(query)

        # Last resort fixes for any remaining syntax issues
        # Remove any malformed quote combinations
        query = re.sub(r"['\"]+'", "'", query)  # Multiple quotes become single quote
        query = re.sub(r"'+['\"]", "'", query)  # Mixed quotes become single quote

        # Ensure no empty quoted expressions
        query = re.sub(r"'\s*'", "", query)

        # Final operator cleanup
        query = re.sub(r'\s*&\s*', ' & ', query)
        query = re.sub(r'\s*\|\s*', ' | ', query)

    return query.strip()


def extract_keywords_from_question(question: str) -> str:
    """
    Extract main keywords from a research question as fallback query.

    Args:
        question: Research question text

    Returns:
        Simple keyword-based tsquery
    """
    # Remove common question words
    stop_words = {'are', 'is', 'was', 'were', 'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'there', 'studies', 'showing', 'compared'}

    # Extract meaningful words (3+ characters, not stop words)
    words = re.findall(r'\b[a-zA-Z]{3,}\b', question.lower())
    keywords = [word for word in words if word not in stop_words]

    # Take first 4-5 most relevant keywords
    return ' & '.join(keywords[:5]) if keywords else 'medical'
