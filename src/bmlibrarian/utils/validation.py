"""
Shared validation utilities for BMLibrarian.

This module provides common validation functions for configuration,
data types, URLs, paths, and user inputs. It consolidates validation
logic that was previously duplicated across multiple modules.
"""

import re
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# Configuration Validation
# ============================================================================

def validate_config_dict(
    config: Dict[str, Any],
    required_keys: List[str],
    optional_keys: Optional[List[str]] = None,
    strict: bool = False
) -> bool:
    """Validate that a configuration dictionary has required keys.

    Args:
        config: Configuration dictionary to validate
        required_keys: List of required key names
        optional_keys: List of optional key names
        strict: If True, raises ValueError on validation failure.
                If False, logs warning and returns False.

    Returns:
        True if valid, False otherwise

    Raises:
        ValueError: If strict=True and validation fails

    Examples:
        >>> config = {"host": "localhost", "port": 5432}
        >>> validate_config_dict(config, ["host", "port"])
        True

        >>> validate_config_dict({}, ["host"], strict=True)
        Traceback (most recent call last):
        ...
        ValueError: Missing required config key: host
    """
    if not isinstance(config, dict):
        msg = f"Config must be a dictionary, got {type(config).__name__}"
        if strict:
            raise ValueError(msg)
        logger.warning(msg)
        return False

    # Check required keys
    for key in required_keys:
        if key not in config:
            msg = f"Missing required config key: {key}"
            if strict:
                raise ValueError(msg)
            logger.warning(msg)
            return False

    # If optional_keys is provided, check for unknown keys
    if optional_keys is not None:
        all_valid_keys = set(required_keys) | set(optional_keys)
        unknown_keys = set(config.keys()) - all_valid_keys
        if unknown_keys:
            msg = f"Unknown config keys: {unknown_keys}"
            if strict:
                raise ValueError(msg)
            logger.warning(msg)

    return True


def validate_ollama_config(config: Dict[str, Any], strict: bool = False) -> bool:
    """Validate Ollama configuration dictionary.

    Args:
        config: Ollama configuration to validate
        strict: If True, raises ValueError on failure

    Returns:
        True if valid, False otherwise

    Expected keys:
        - host (required): Ollama server URL
        - timeout (optional): Request timeout in seconds
        - max_retries (optional): Maximum retry attempts
    """
    required = ['host']
    optional = ['timeout', 'max_retries']

    if not validate_config_dict(config, required, optional, strict):
        return False

    # Validate host URL
    if not validate_url(config['host'], strict=strict):
        return False

    # Validate timeout if present
    if 'timeout' in config:
        if not validate_positive_int(config['timeout'], min_value=1, max_value=600, strict=strict):
            if strict:
                raise ValueError(f"Invalid timeout: {config['timeout']} (must be 1-600)")
            return False

    # Validate max_retries if present
    if 'max_retries' in config:
        if not validate_positive_int(config['max_retries'], min_value=0, max_value=10, strict=strict):
            if strict:
                raise ValueError(f"Invalid max_retries: {config['max_retries']} (must be 0-10)")
            return False

    return True


def validate_agent_config(config: Dict[str, Any], agent_type: str, strict: bool = False) -> bool:
    """Validate agent configuration dictionary.

    Args:
        config: Agent configuration to validate
        agent_type: Type of agent (query, scoring, citation, etc.)
        strict: If True, raises ValueError on failure

    Returns:
        True if valid, False otherwise

    Expected keys:
        - model (optional): Model name
        - temperature (optional): Temperature parameter (0.0-2.0)
        - top_p (optional): Top-p parameter (0.0-1.0)
        - max_tokens (optional): Maximum tokens
    """
    optional = ['model', 'temperature', 'top_p', 'max_tokens']

    if not validate_config_dict(config, [], optional, strict):
        return False

    # Validate temperature if present
    if 'temperature' in config:
        if not validate_float_range(config['temperature'], 0.0, 2.0, strict=strict):
            if strict:
                raise ValueError(f"Invalid temperature: {config['temperature']} (must be 0.0-2.0)")
            return False

    # Validate top_p if present
    if 'top_p' in config:
        if not validate_float_range(config['top_p'], 0.0, 1.0, strict=strict):
            if strict:
                raise ValueError(f"Invalid top_p: {config['top_p']} (must be 0.0-1.0)")
            return False

    # Validate max_tokens if present
    if 'max_tokens' in config:
        if not validate_positive_int(config['max_tokens'], min_value=1, max_value=100000, strict=strict):
            if strict:
                raise ValueError(f"Invalid max_tokens: {config['max_tokens']}")
            return False

    return True


def validate_database_config(config: Dict[str, Any], strict: bool = False) -> bool:
    """Validate database configuration dictionary.

    Args:
        config: Database configuration to validate
        strict: If True, raises ValueError on failure

    Returns:
        True if valid, False otherwise

    Expected keys:
        - max_results_per_query (optional): Maximum results per query
        - batch_size (optional): Processing batch size
        - use_ranking (optional): Enable ranking
    """
    optional = ['max_results_per_query', 'batch_size', 'use_ranking']

    if not validate_config_dict(config, [], optional, strict):
        return False

    # Validate max_results_per_query if present
    if 'max_results_per_query' in config:
        if not validate_positive_int(config['max_results_per_query'], min_value=1, max_value=10000, strict=strict):
            if strict:
                raise ValueError(f"Invalid max_results_per_query: {config['max_results_per_query']}")
            return False

    # Validate batch_size if present
    if 'batch_size' in config:
        if not validate_positive_int(config['batch_size'], min_value=1, max_value=1000, strict=strict):
            if strict:
                raise ValueError(f"Invalid batch_size: {config['batch_size']}")
            return False

    return True


# ============================================================================
# Data Type Validation
# ============================================================================

def validate_url(url: str, strict: bool = False, allow_localhost: bool = True) -> bool:
    """Validate URL format.

    Args:
        url: URL string to validate
        strict: If True, raises ValueError on failure
        allow_localhost: Allow localhost URLs

    Returns:
        True if valid URL, False otherwise

    Examples:
        >>> validate_url("http://localhost:11434")
        True

        >>> validate_url("not-a-url")
        False
    """
    if not isinstance(url, str) or not url.strip():
        msg = "URL must be a non-empty string"
        if strict:
            raise ValueError(msg)
        logger.warning(msg)
        return False

    try:
        parsed = urlparse(url)

        # Check scheme
        if parsed.scheme not in ['http', 'https']:
            msg = f"Invalid URL scheme: {parsed.scheme} (must be http or https)"
            if strict:
                raise ValueError(msg)
            logger.warning(msg)
            return False

        # Check netloc
        if not parsed.netloc:
            msg = "URL missing netloc (host)"
            if strict:
                raise ValueError(msg)
            logger.warning(msg)
            return False

        # Check localhost if not allowed
        if not allow_localhost and 'localhost' in parsed.netloc.lower():
            msg = "Localhost URLs not allowed"
            if strict:
                raise ValueError(msg)
            logger.warning(msg)
            return False

        return True

    except Exception as e:
        msg = f"Invalid URL format: {e}"
        if strict:
            raise ValueError(msg)
        logger.warning(msg)
        return False


def validate_port(port: Union[int, str], strict: bool = False) -> bool:
    """Validate port number.

    Args:
        port: Port number (int or string)
        strict: If True, raises ValueError on failure

    Returns:
        True if valid port (1-65535), False otherwise

    Examples:
        >>> validate_port(5432)
        True

        >>> validate_port(99999)
        False
    """
    try:
        port_int = int(port)
        if 1 <= port_int <= 65535:
            return True

        msg = f"Port must be between 1 and 65535, got {port_int}"
        if strict:
            raise ValueError(msg)
        logger.warning(msg)
        return False

    except (ValueError, TypeError) as e:
        msg = f"Invalid port: {port} ({e})"
        if strict:
            raise ValueError(msg)
        logger.warning(msg)
        return False


def validate_positive_int(
    value: Union[int, str],
    min_value: int = 1,
    max_value: Optional[int] = None,
    strict: bool = False
) -> bool:
    """Validate positive integer within optional range.

    Args:
        value: Value to validate (int or string)
        min_value: Minimum allowed value (default 1)
        max_value: Maximum allowed value (None for unlimited)
        strict: If True, raises ValueError on failure

    Returns:
        True if valid, False otherwise

    Examples:
        >>> validate_positive_int(10, min_value=1, max_value=100)
        True

        >>> validate_positive_int(-5)
        False
    """
    try:
        int_val = int(value)

        if int_val < min_value:
            msg = f"Value must be >= {min_value}, got {int_val}"
            if strict:
                raise ValueError(msg)
            logger.warning(msg)
            return False

        if max_value is not None and int_val > max_value:
            msg = f"Value must be <= {max_value}, got {int_val}"
            if strict:
                raise ValueError(msg)
            logger.warning(msg)
            return False

        return True

    except (ValueError, TypeError) as e:
        msg = f"Invalid integer: {value} ({e})"
        if strict:
            raise ValueError(msg)
        logger.warning(msg)
        return False


def validate_float_range(
    value: Union[float, int, str],
    min_value: float,
    max_value: float,
    strict: bool = False
) -> bool:
    """Validate float value within range.

    Args:
        value: Value to validate (float, int, or string)
        min_value: Minimum allowed value
        max_value: Maximum allowed value
        strict: If True, raises ValueError on failure

    Returns:
        True if valid, False otherwise

    Examples:
        >>> validate_float_range(0.5, 0.0, 1.0)
        True

        >>> validate_float_range(1.5, 0.0, 1.0)
        False
    """
    try:
        float_val = float(value)

        if float_val < min_value or float_val > max_value:
            msg = f"Value must be between {min_value} and {max_value}, got {float_val}"
            if strict:
                raise ValueError(msg)
            logger.warning(msg)
            return False

        return True

    except (ValueError, TypeError) as e:
        msg = f"Invalid float: {value} ({e})"
        if strict:
            raise ValueError(msg)
        logger.warning(msg)
        return False


def validate_file_path(path: Union[str, Path], must_exist: bool = False, strict: bool = False) -> bool:
    """Validate file path.

    Args:
        path: File path to validate
        must_exist: If True, file must exist
        strict: If True, raises ValueError on failure

    Returns:
        True if valid, False otherwise

    Examples:
        >>> validate_file_path("/tmp/test.txt", must_exist=False)
        True
    """
    try:
        path_obj = Path(path)

        if must_exist and not path_obj.exists():
            msg = f"File does not exist: {path}"
            if strict:
                raise ValueError(msg)
            logger.warning(msg)
            return False

        if path_obj.exists() and not path_obj.is_file():
            msg = f"Path is not a file: {path}"
            if strict:
                raise ValueError(msg)
            logger.warning(msg)
            return False

        return True

    except Exception as e:
        msg = f"Invalid file path: {path} ({e})"
        if strict:
            raise ValueError(msg)
        logger.warning(msg)
        return False


def validate_directory_path(path: Union[str, Path], must_exist: bool = False, strict: bool = False) -> bool:
    """Validate directory path.

    Args:
        path: Directory path to validate
        must_exist: If True, directory must exist
        strict: If True, raises ValueError on failure

    Returns:
        True if valid, False otherwise

    Examples:
        >>> validate_directory_path("/tmp", must_exist=True)
        True
    """
    try:
        path_obj = Path(path)

        if must_exist and not path_obj.exists():
            msg = f"Directory does not exist: {path}"
            if strict:
                raise ValueError(msg)
            logger.warning(msg)
            return False

        if path_obj.exists() and not path_obj.is_dir():
            msg = f"Path is not a directory: {path}"
            if strict:
                raise ValueError(msg)
            logger.warning(msg)
            return False

        return True

    except Exception as e:
        msg = f"Invalid directory path: {path} ({e})"
        if strict:
            raise ValueError(msg)
        logger.warning(msg)
        return False


# ============================================================================
# Input Sanitization
# ============================================================================

def sanitize_string(
    value: str,
    max_length: Optional[int] = None,
    allow_newlines: bool = True,
    strip: bool = True
) -> str:
    """Sanitize string input.

    Args:
        value: String to sanitize
        max_length: Maximum length (None for unlimited)
        allow_newlines: Allow newline characters
        strip: Strip leading/trailing whitespace

    Returns:
        Sanitized string

    Examples:
        >>> sanitize_string("  hello  ")
        'hello'

        >>> sanitize_string("hello\\nworld", allow_newlines=False)
        'hello world'
    """
    if not isinstance(value, str):
        value = str(value)

    if strip:
        value = value.strip()

    if not allow_newlines:
        value = value.replace('\n', ' ').replace('\r', ' ')
        # Collapse multiple spaces
        value = re.sub(r'\s+', ' ', value)

    if max_length is not None and len(value) > max_length:
        value = value[:max_length]

    return value


def sanitize_filename(filename: str, replacement: str = '_') -> str:
    """Sanitize filename by removing invalid characters.

    Args:
        filename: Filename to sanitize
        replacement: Character to replace invalid chars with

    Returns:
        Sanitized filename safe for filesystem use

    Examples:
        >>> sanitize_filename("my file?.txt")
        'my_file_.txt'

        >>> sanitize_filename("report/draft.pdf")
        'report_draft.pdf'
    """
    # Remove invalid filename characters
    invalid_chars = r'[<>:"/\\|?*\x00-\x1f]'
    sanitized = re.sub(invalid_chars, replacement, filename)

    # Remove leading/trailing dots and spaces
    sanitized = sanitized.strip('. ')

    # Ensure not empty
    if not sanitized:
        sanitized = 'unnamed'

    # Limit length (max 255 chars on most filesystems)
    if len(sanitized) > 255:
        name, ext = os.path.splitext(sanitized)
        max_name_len = 255 - len(ext)
        sanitized = name[:max_name_len] + ext

    return sanitized


def sanitize_sql_identifier(identifier: str) -> str:
    """Sanitize SQL identifier (table/column name).

    Args:
        identifier: SQL identifier to sanitize

    Returns:
        Sanitized identifier safe for SQL queries

    Examples:
        >>> sanitize_sql_identifier("my_table")
        'my_table'

        >>> sanitize_sql_identifier("table; DROP TABLE users;")
        'table_DROP_TABLE_users'
    """
    # Only allow alphanumeric and underscores
    sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', identifier)

    # Ensure starts with letter or underscore
    if sanitized and not sanitized[0].isalpha() and sanitized[0] != '_':
        sanitized = '_' + sanitized

    # Ensure not empty
    if not sanitized:
        sanitized = 'unnamed'

    return sanitized


# ============================================================================
# Type Coercion Helpers
# ============================================================================

def ensure_list(value: Any) -> List:
    """Ensure value is a list.

    Args:
        value: Value to convert to list

    Returns:
        List containing the value(s)

    Examples:
        >>> ensure_list([1, 2, 3])
        [1, 2, 3]

        >>> ensure_list("hello")
        ['hello']

        >>> ensure_list(None)
        []
    """
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return list(value)
    return [value]


def ensure_dict(value: Any) -> Dict:
    """Ensure value is a dictionary.

    Args:
        value: Value to convert to dict

    Returns:
        Dictionary

    Examples:
        >>> ensure_dict({"key": "value"})
        {'key': 'value'}

        >>> ensure_dict(None)
        {}
    """
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    return {}


def ensure_string(value: Any, default: str = "") -> str:
    """Ensure value is a string.

    Args:
        value: Value to convert to string
        default: Default value if None

    Returns:
        String value

    Examples:
        >>> ensure_string("hello")
        'hello'

        >>> ensure_string(123)
        '123'

        >>> ensure_string(None)
        ''
    """
    if value is None:
        return default
    if isinstance(value, str):
        return value
    return str(value)


def ensure_int(value: Any, default: int = 0) -> int:
    """Ensure value is an integer.

    Args:
        value: Value to convert to int
        default: Default value if conversion fails

    Returns:
        Integer value

    Examples:
        >>> ensure_int(123)
        123

        >>> ensure_int("456")
        456

        >>> ensure_int("invalid")
        0
    """
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def ensure_float(value: Any, default: float = 0.0) -> float:
    """Ensure value is a float.

    Args:
        value: Value to convert to float
        default: Default value if conversion fails

    Returns:
        Float value

    Examples:
        >>> ensure_float(1.23)
        1.23

        >>> ensure_float("4.56")
        4.56

        >>> ensure_float("invalid")
        0.0
    """
    if isinstance(value, float):
        return value
    try:
        return float(value)
    except (ValueError, TypeError):
        return default
