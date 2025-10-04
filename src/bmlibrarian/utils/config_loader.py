"""Configuration file loading utilities.

This module provides reusable utilities for:
- Finding configuration files in standard locations
- Loading JSON configuration with error handling
- Saving JSON configuration with validation
- Configuration file path searching and fallback logic
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

from .path_utils import (
    expand_path,
    ensure_directory,
    get_default_config_path,
    get_legacy_config_path
)

logger = logging.getLogger(__name__)


def get_standard_config_paths() -> List[Path]:
    """Get standard configuration file search paths.

    Returns paths in priority order:
    1. ~/.bmlibrarian/config.json (primary/recommended)
    2. ./bmlibrarian_config.json (legacy fallback in current directory)

    Returns:
        List of Path objects in search priority order

    Examples:
        >>> paths = get_standard_config_paths()
        >>> len(paths)
        2
        >>> paths[0].name
        'config.json'
    """
    return [
        get_default_config_path(),  # Primary location
        get_legacy_config_path(),   # Legacy fallback
    ]


def find_config_file(custom_path: Optional[Path] = None) -> Optional[Path]:
    """Search for configuration file in standard locations.

    Searches in priority order:
    1. Custom path (if provided)
    2. ~/.bmlibrarian/config.json
    3. ./bmlibrarian_config.json (legacy)

    Args:
        custom_path: Optional custom path to check first

    Returns:
        Path to first existing config file, or None if not found

    Examples:
        >>> config_path = find_config_file()
        >>> config_path.exists() if config_path else False
        True

        >>> custom = Path("/tmp/my_config.json")
        >>> find_config_file(custom)
        PosixPath('/tmp/my_config.json')  # if exists
    """
    search_paths = []

    # Add custom path first if provided
    if custom_path:
        search_paths.append(expand_path(custom_path))

    # Add standard paths
    search_paths.extend(get_standard_config_paths())

    # Return first existing path
    for config_path in search_paths:
        if config_path.exists():
            logger.debug(f"Found config file: {config_path}")
            return config_path

    logger.debug("No config file found in standard locations")
    return None


def load_json_config(file_path: Path) -> Dict[str, Any]:
    """Load JSON configuration file with error handling.

    Provides comprehensive error handling for:
    - File not found
    - Invalid JSON syntax
    - IO errors
    - Permission errors

    Args:
        file_path: Path to JSON configuration file

    Returns:
        Dictionary containing configuration data

    Raises:
        FileNotFoundError: If config file doesn't exist
        json.JSONDecodeError: If JSON is invalid
        IOError: If file cannot be read

    Examples:
        >>> config = load_json_config(Path("~/.bmlibrarian/config.json"))
        >>> isinstance(config, dict)
        True
    """
    expanded_path = expand_path(file_path)

    if not expanded_path.exists():
        raise FileNotFoundError(f"Config file not found: {expanded_path}")

    try:
        with open(expanded_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        logger.info(f"Loaded configuration from: {expanded_path}")
        return config

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in config file {expanded_path}: {e}")
        raise

    except IOError as e:
        logger.error(f"Failed to read config file {expanded_path}: {e}")
        raise


def save_json_config(config: Dict[str, Any], file_path: Path,
                     indent: int = 2, create_dirs: bool = True) -> None:
    """Save configuration to JSON file with error handling.

    Features:
    - Automatic directory creation (optional)
    - Pretty-printed JSON with configurable indentation
    - Comprehensive error handling
    - UTF-8 encoding

    Args:
        config: Configuration dictionary to save
        file_path: Target file path
        indent: JSON indentation spaces (default: 2)
        create_dirs: Create parent directories if needed (default: True)

    Raises:
        IOError: If file cannot be written
        OSError: If directory creation fails

    Examples:
        >>> config = {"ollama": {"host": "http://localhost:11434"}}
        >>> save_json_config(config, Path("~/.bmlibrarian/config.json"))
    """
    if create_dirs:
        expanded_path = ensure_directory(file_path)
    else:
        expanded_path = expand_path(file_path)

    try:
        with open(expanded_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=indent, ensure_ascii=False)

        logger.info(f"Saved configuration to: {expanded_path}")

    except IOError as e:
        logger.error(f"Failed to save config to {expanded_path}: {e}")
        raise


def load_config_with_fallback(custom_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Load configuration file with automatic fallback to standard locations.

    Convenience function that combines find_config_file() and load_json_config().
    Searches standard locations and loads the first valid config found.

    Args:
        custom_path: Optional custom path to try first

    Returns:
        Configuration dictionary, or None if no valid config found

    Examples:
        >>> config = load_config_with_fallback()
        >>> config is not None
        True

        >>> config = load_config_with_fallback(Path("/custom/config.json"))
        >>> config.get("ollama", {}).get("host")
        'http://localhost:11434'
    """
    config_path = find_config_file(custom_path)

    if not config_path:
        logger.warning("No configuration file found")
        return None

    try:
        return load_json_config(config_path)
    except (FileNotFoundError, json.JSONDecodeError, IOError) as e:
        logger.error(f"Failed to load config from {config_path}: {e}")
        return None


def merge_configs(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge two configuration dictionaries.

    Override values take precedence. Nested dictionaries are merged recursively.

    Args:
        base: Base configuration dictionary
        override: Override configuration dictionary

    Returns:
        Merged configuration dictionary

    Examples:
        >>> base = {"ollama": {"host": "localhost", "port": 11434}}
        >>> override = {"ollama": {"port": 8080}, "new": "value"}
        >>> merged = merge_configs(base, override)
        >>> merged["ollama"]["host"]
        'localhost'
        >>> merged["ollama"]["port"]
        8080
        >>> merged["new"]
        'value'
    """
    result = base.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            # Recursively merge nested dictionaries
            result[key] = merge_configs(result[key], value)
        else:
            # Override value
            result[key] = value

    return result
