"""
JSON repair utilities for handling malformed LLM responses.

LLMs often produce JSON with common syntax errors like:
- Missing commas between array elements or object properties
- Trailing commas before closing brackets
- Single quotes instead of double quotes
- Unescaped newlines or tabs in strings
- Truncated JSON (missing closing brackets)

This module provides utilities to repair these common issues before parsing.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Configuration constants
MAX_REPAIR_ATTEMPTS: int = 3
MAX_JSON_LENGTH: int = 1_000_000  # 1MB max


class JSONRepairError(Exception):
    """Raised when JSON cannot be repaired."""

    pass


def repair_json(json_str: str, max_attempts: int = MAX_REPAIR_ATTEMPTS) -> str:
    """
    Attempt to repair malformed JSON from LLM responses.

    Applies a series of fixes for common LLM JSON errors. If the JSON
    is already valid, returns it unchanged.

    Args:
        json_str: Potentially malformed JSON string
        max_attempts: Maximum repair iterations (default: 3)

    Returns:
        Repaired JSON string

    Raises:
        JSONRepairError: If JSON cannot be repaired after all attempts
        ValueError: If input is empty or too large
    """
    if not json_str or not json_str.strip():
        raise ValueError("Cannot repair empty JSON string")

    if len(json_str) > MAX_JSON_LENGTH:
        raise ValueError(f"JSON string too large (max {MAX_JSON_LENGTH} bytes)")

    original_str = json_str

    # First, try to parse as-is
    try:
        json.loads(json_str)
        return json_str  # Already valid
    except json.JSONDecodeError:
        pass  # Need repairs

    # Apply repair strategies iteratively
    for attempt in range(max_attempts):
        try:
            repaired = _apply_repairs(json_str)

            # Try to parse the repaired JSON
            json.loads(repaired)

            if repaired != original_str:
                logger.debug(f"JSON repaired successfully on attempt {attempt + 1}")

            return repaired

        except json.JSONDecodeError as e:
            if attempt < max_attempts - 1:
                # Use the repaired version for next iteration
                json_str = repaired
                logger.debug(
                    f"JSON repair attempt {attempt + 1} failed: {e}, retrying"
                )
            else:
                logger.warning(
                    f"JSON repair failed after {max_attempts} attempts: {e}"
                )
                raise JSONRepairError(
                    f"Cannot repair JSON after {max_attempts} attempts: {e}"
                ) from e

    # Should not reach here, but just in case
    raise JSONRepairError("JSON repair failed unexpectedly")


def _apply_repairs(json_str: str) -> str:
    """
    Apply all repair strategies to a JSON string.

    Args:
        json_str: JSON string to repair

    Returns:
        Repaired JSON string
    """
    # Order matters - some repairs depend on others
    repairs = [
        _fix_single_quotes,
        _fix_unescaped_newlines,
        _fix_unescaped_tabs,
        _fix_unescaped_control_chars,
        _fix_trailing_commas,
        _fix_missing_commas,
        _fix_truncated_json,
        _fix_unquoted_keys,
    ]

    result = json_str

    for repair_func in repairs:
        try:
            result = repair_func(result)
        except Exception as e:
            logger.debug(f"Repair function {repair_func.__name__} failed: {e}")
            # Continue with other repairs

    return result


def _fix_single_quotes(json_str: str) -> str:
    """
    Replace single quotes with double quotes for JSON string values.

    Handles the common LLM error of using single quotes instead of double.
    Carefully avoids replacing apostrophes within strings.

    Args:
        json_str: JSON string with potential single quotes

    Returns:
        JSON string with double quotes
    """
    # This is tricky because we don't want to replace apostrophes inside strings
    # Use a state machine approach

    result = []
    in_double_string = False
    in_single_string = False
    i = 0

    while i < len(json_str):
        char = json_str[i]
        prev_char = json_str[i - 1] if i > 0 else ""

        # Handle escape sequences
        if prev_char == "\\" and not (i >= 2 and json_str[i - 2] == "\\"):
            result.append(char)
            i += 1
            continue

        if char == '"' and not in_single_string:
            in_double_string = not in_double_string
            result.append(char)
        elif char == "'" and not in_double_string:
            if in_single_string:
                # Closing single quote - convert to double
                result.append('"')
                in_single_string = False
            else:
                # Check if this looks like the start of a JSON string
                # Valid contexts: after : or [ or , or { or after a closing string quote
                # (missing comma case: 'value1' 'value2' should become "value1" "value2")
                preceding = json_str[:i].rstrip()
                if preceding and preceding[-1] in ":,[{'\"":
                    result.append('"')
                    in_single_string = True
                else:
                    # Might be an apostrophe - keep as is
                    result.append(char)
        else:
            result.append(char)

        i += 1

    return "".join(result)


def _fix_unescaped_newlines(json_str: str) -> str:
    """
    Fix unescaped newlines within JSON string values.

    Args:
        json_str: JSON string with potential unescaped newlines

    Returns:
        JSON string with properly escaped newlines
    """
    # Find strings and escape newlines within them
    result = []
    in_string = False
    i = 0

    while i < len(json_str):
        char = json_str[i]
        prev_char = json_str[i - 1] if i > 0 else ""

        # Check for escaped backslash
        is_escaped = prev_char == "\\" and not (i >= 2 and json_str[i - 2] == "\\")

        if char == '"' and not is_escaped:
            in_string = not in_string
            result.append(char)
        elif char == "\n" and in_string:
            result.append("\\n")
        elif char == "\r" and in_string:
            result.append("\\r")
        else:
            result.append(char)

        i += 1

    return "".join(result)


def _fix_unescaped_tabs(json_str: str) -> str:
    """
    Fix unescaped tabs within JSON string values.

    Args:
        json_str: JSON string with potential unescaped tabs

    Returns:
        JSON string with properly escaped tabs
    """
    result = []
    in_string = False
    i = 0

    while i < len(json_str):
        char = json_str[i]
        prev_char = json_str[i - 1] if i > 0 else ""

        is_escaped = prev_char == "\\" and not (i >= 2 and json_str[i - 2] == "\\")

        if char == '"' and not is_escaped:
            in_string = not in_string
            result.append(char)
        elif char == "\t" and in_string:
            result.append("\\t")
        else:
            result.append(char)

        i += 1

    return "".join(result)


def _fix_unescaped_control_chars(json_str: str) -> str:
    """
    Remove or escape control characters that are invalid in JSON strings.

    Args:
        json_str: JSON string with potential control characters

    Returns:
        JSON string with control characters handled
    """
    # Control characters (0x00-0x1F except tab/newline/cr which are handled separately)
    control_char_pattern = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

    result = []
    in_string = False
    i = 0

    while i < len(json_str):
        char = json_str[i]
        prev_char = json_str[i - 1] if i > 0 else ""

        is_escaped = prev_char == "\\" and not (i >= 2 and json_str[i - 2] == "\\")

        if char == '"' and not is_escaped:
            in_string = not in_string
            result.append(char)
        elif in_string and control_char_pattern.match(char):
            # Replace control char with escaped unicode
            result.append(f"\\u{ord(char):04x}")
        else:
            result.append(char)

        i += 1

    return "".join(result)


def _fix_trailing_commas(json_str: str) -> str:
    """
    Remove trailing commas before closing brackets/braces.

    Args:
        json_str: JSON string with potential trailing commas

    Returns:
        JSON string without trailing commas
    """
    # Pattern: comma followed by optional whitespace and closing bracket
    # Be careful not to match within strings

    result = []
    in_string = False
    i = 0

    while i < len(json_str):
        char = json_str[i]
        prev_char = json_str[i - 1] if i > 0 else ""

        is_escaped = prev_char == "\\" and not (i >= 2 and json_str[i - 2] == "\\")

        if char == '"' and not is_escaped:
            in_string = not in_string
            result.append(char)
        elif char == "," and not in_string:
            # Look ahead to see if there's a closing bracket
            rest = json_str[i + 1 :].lstrip()
            if rest and rest[0] in "]}":
                # Skip this trailing comma
                pass
            else:
                result.append(char)
        else:
            result.append(char)

        i += 1

    return "".join(result)


def _fix_missing_commas(json_str: str) -> str:
    """
    Add missing commas between array elements or object properties.

    This is one of the most common LLM JSON errors. Handles cases like:
    - "value1" "value2" -> "value1", "value2"
    - } { -> }, {
    - ] [ -> ], [
    - "key": "value" "next": -> "key": "value", "next":

    Args:
        json_str: JSON string with potential missing commas

    Returns:
        JSON string with commas added where needed
    """
    result = []
    in_string = False
    i = 0

    while i < len(json_str):
        char = json_str[i]
        prev_char = json_str[i - 1] if i > 0 else ""

        is_escaped = prev_char == "\\" and not (i >= 2 and json_str[i - 2] == "\\")

        if char == '"' and not is_escaped:
            # Check if we need to add a comma before this quote
            if not in_string:
                # Look back to see what preceded this quote
                preceding = "".join(result).rstrip()
                if preceding and preceding[-1] in '"}]0123456789':
                    # Need to check if this is a value or key
                    # A key would have no colon after, a value would
                    rest = json_str[i:]
                    # Find the closing quote
                    close_quote = _find_closing_quote(rest, 0)
                    if close_quote > 0:
                        after_close = rest[close_quote + 1 :].lstrip()
                        if after_close and after_close[0] != ":":
                            # This is a value, needs comma before
                            result.append(",")
                        elif after_close and after_close[0] == ":":
                            # This is a key, needs comma before
                            result.append(",")

            in_string = not in_string
            result.append(char)

        elif char in "{[" and not in_string:
            # Check if we need comma before opening bracket
            preceding = "".join(result).rstrip()
            if preceding and preceding[-1] in '"}]0123456789':
                result.append(",")
            result.append(char)

        elif char in "}]" and not in_string:
            result.append(char)

        else:
            result.append(char)

        i += 1

    return "".join(result)


def _find_closing_quote(s: str, start: int) -> int:
    """
    Find the position of the closing quote in a string.

    Args:
        s: String to search
        start: Position of opening quote

    Returns:
        Position of closing quote, or -1 if not found
    """
    i = start + 1
    while i < len(s):
        if s[i] == '"':
            # Check if escaped
            num_backslashes = 0
            j = i - 1
            while j >= start + 1 and s[j] == "\\":
                num_backslashes += 1
                j -= 1
            if num_backslashes % 2 == 0:
                return i
        i += 1
    return -1


def _fix_truncated_json(json_str: str) -> str:
    """
    Attempt to close truncated JSON by adding missing brackets.

    Args:
        json_str: Potentially truncated JSON string

    Returns:
        JSON string with closing brackets added if needed
    """
    # Count brackets
    open_braces = 0
    open_brackets = 0
    in_string = False

    for i, char in enumerate(json_str):
        prev_char = json_str[i - 1] if i > 0 else ""
        is_escaped = prev_char == "\\" and not (i >= 2 and json_str[i - 2] == "\\")

        if char == '"' and not is_escaped:
            in_string = not in_string
        elif not in_string:
            if char == "{":
                open_braces += 1
            elif char == "}":
                open_braces -= 1
            elif char == "[":
                open_brackets += 1
            elif char == "]":
                open_brackets -= 1

    # Add missing closers
    result = json_str.rstrip()

    # If we're in a string, close it
    if in_string:
        result += '"'

    # Remove any trailing comma before adding closers
    result = result.rstrip(",")

    # Add missing brackets
    result += "]" * open_brackets
    result += "}" * open_braces

    return result


def _fix_unquoted_keys(json_str: str) -> str:
    """
    Quote unquoted object keys.

    Handles JavaScript-style object literals with unquoted keys:
    {key: "value"} -> {"key": "value"}

    Args:
        json_str: JSON string with potential unquoted keys

    Returns:
        JSON string with quoted keys
    """
    # Pattern for unquoted key: { or , followed by whitespace and word chars, then :
    pattern = r'([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)(\s*:)'

    def quote_key(match: re.Match) -> str:
        return f'{match.group(1)}"{match.group(2)}"{match.group(3)}'

    # Only apply outside of strings - this is a simple approach
    # For more robust handling, we'd need a proper parser
    result = []
    in_string = False
    i = 0

    # Find all strings first
    string_ranges: List[Tuple[int, int]] = []
    while i < len(json_str):
        if json_str[i] == '"':
            if i == 0 or json_str[i - 1] != "\\":
                start = i
                end = _find_closing_quote(json_str, i)
                if end > 0:
                    string_ranges.append((start, end))
                    i = end + 1
                    continue
        i += 1

    # Apply pattern only to non-string portions
    i = 0
    last_end = 0
    for start, end in string_ranges:
        # Process portion before this string
        portion = json_str[last_end:start]
        portion = re.sub(pattern, quote_key, portion)
        result.append(portion)
        # Add the string unchanged
        result.append(json_str[start : end + 1])
        last_end = end + 1

    # Process remaining portion
    if last_end < len(json_str):
        portion = json_str[last_end:]
        portion = re.sub(pattern, quote_key, portion)
        result.append(portion)

    return "".join(result)


def safe_json_loads(
    json_str: str, repair: bool = True, max_attempts: int = MAX_REPAIR_ATTEMPTS
) -> Any:
    """
    Safely parse JSON with optional automatic repair.

    Convenience function that combines JSON extraction, repair, and parsing.

    Args:
        json_str: JSON string to parse
        repair: Whether to attempt repair on parse failure (default: True)
        max_attempts: Maximum repair attempts if repair is True

    Returns:
        Parsed JSON data (dict, list, or primitive)

    Raises:
        ValueError: If JSON cannot be parsed (even after repair if enabled)
    """
    if not json_str or not json_str.strip():
        raise ValueError("Cannot parse empty JSON string")

    # First try direct parsing
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        if not repair:
            raise ValueError(f"Invalid JSON: {e}") from e

    # Try repair
    try:
        repaired = repair_json(json_str, max_attempts)
        return json.loads(repaired)
    except (JSONRepairError, json.JSONDecodeError) as e:
        raise ValueError(f"Cannot parse JSON even after repair: {e}") from e


def extract_and_repair_json(
    response: str, repair: bool = True
) -> Tuple[str, bool]:
    """
    Extract JSON from an LLM response and optionally repair it.

    Handles responses that contain:
    - Pure JSON
    - JSON in markdown code blocks
    - JSON embedded in explanatory text

    Args:
        response: Raw LLM response string
        repair: Whether to attempt repair (default: True)

    Returns:
        Tuple of (extracted_json_string, was_repaired)

    Raises:
        ValueError: If no JSON found in response
    """
    if not response or not response.strip():
        raise ValueError("Cannot extract JSON from empty response")

    response = response.strip()
    json_str: Optional[str] = None

    # Try to extract from ```json code block
    if "```json" in response:
        match = re.search(r"```json\s*([\s\S]*?)\s*```", response)
        if match:
            json_str = match.group(1).strip()

    # Try to extract from ``` code block
    if not json_str and "```" in response:
        match = re.search(r"```\s*([\s\S]*?)\s*```", response)
        if match:
            content = match.group(1).strip()
            if content.startswith("{") or content.startswith("["):
                json_str = content

    # Try to find JSON object/array directly
    if not json_str:
        start_idx = -1
        for i, char in enumerate(response):
            if char in "{[":
                start_idx = i
                break

        if start_idx >= 0:
            # Find matching closing bracket
            open_char = response[start_idx]
            close_char = "}" if open_char == "{" else "]"
            count = 0
            in_string = False

            for i, char in enumerate(response[start_idx:], start_idx):
                prev = response[i - 1] if i > 0 else ""
                is_escaped = prev == "\\" and not (i >= 2 and response[i - 2] == "\\")

                if char == '"' and not is_escaped:
                    in_string = not in_string
                elif not in_string:
                    if char == open_char:
                        count += 1
                    elif char == close_char:
                        count -= 1
                        if count == 0:
                            json_str = response[start_idx : i + 1]
                            break

    if not json_str:
        raise ValueError("No JSON found in response")

    # Try to parse as-is first
    try:
        json.loads(json_str)
        return json_str, False
    except json.JSONDecodeError:
        if not repair:
            raise

    # Try repair
    try:
        repaired = repair_json(json_str)
        json.loads(repaired)  # Validate it parses
        return repaired, True
    except (JSONRepairError, json.JSONDecodeError) as e:
        raise ValueError(f"Cannot parse extracted JSON: {e}") from e
