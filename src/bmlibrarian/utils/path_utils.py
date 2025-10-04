"""Path utilities for file system operations.

This module provides reusable utilities for:
- Path expansion (~ and environment variables)
- Directory creation with error handling
- Standard configuration directory locations
- OS-agnostic path handling
"""

import os
import logging
from pathlib import Path
from typing import Union

logger = logging.getLogger(__name__)


def expand_path(path: Union[str, Path]) -> Path:
    """Expand ~ and environment variables in path.

    Args:
        path: File path with potential ~ or env vars

    Returns:
        Fully expanded Path object

    Examples:
        >>> expand_path("~/config.json")
        PosixPath('/Users/username/config.json')

        >>> expand_path("$HOME/.config/app.json")
        PosixPath('/Users/username/.config/app.json')
    """
    if isinstance(path, str):
        # Expand both ~ and environment variables
        expanded = os.path.expanduser(os.path.expandvars(path))
        return Path(expanded)
    return path.expanduser()


def ensure_directory(file_path: Union[str, Path]) -> Path:
    """Ensure parent directory exists for file path.

    Creates all intermediate directories as needed. Safe to call
    multiple times (idempotent).

    Args:
        file_path: Path to file (directory will be created for its parent)

    Returns:
        Expanded Path object with guaranteed parent directory

    Raises:
        OSError: If directory creation fails due to permissions

    Examples:
        >>> path = ensure_directory("~/.bmlibrarian/config.json")
        >>> path.parent.exists()
        True
    """
    expanded_path = expand_path(file_path)
    parent_dir = expanded_path.parent

    if not parent_dir.exists():
        try:
            parent_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Created directory: {parent_dir}")
        except OSError as e:
            logger.error(f"Failed to create directory {parent_dir}: {e}")
            raise

    return expanded_path


def get_config_dir() -> Path:
    """Get standard configuration directory (~/.bmlibrarian).

    Returns:
        Path to configuration directory (may not exist yet)

    Examples:
        >>> get_config_dir()
        PosixPath('/Users/username/.bmlibrarian')
    """
    return Path.home() / ".bmlibrarian"


def get_default_config_path() -> Path:
    """Get default configuration file path.

    Returns:
        Path to primary config file location (~/.bmlibrarian/config.json)

    Examples:
        >>> get_default_config_path()
        PosixPath('/Users/username/.bmlibrarian/config.json')
    """
    return get_config_dir() / "config.json"


def get_legacy_config_path() -> Path:
    """Get legacy configuration file path.

    Legacy location is bmlibrarian_config.json in current directory.
    This is maintained for backward compatibility.

    Returns:
        Path to legacy config file in current working directory

    Examples:
        >>> get_legacy_config_path()
        PosixPath('/current/dir/bmlibrarian_config.json')
    """
    return Path.cwd() / "bmlibrarian_config.json"


def ensure_config_directory() -> Path:
    """Ensure configuration directory exists.

    Creates ~/.bmlibrarian directory if it doesn't exist.

    Returns:
        Path to configuration directory (guaranteed to exist)

    Raises:
        OSError: If directory creation fails

    Examples:
        >>> config_dir = ensure_config_directory()
        >>> config_dir.exists()
        True
    """
    config_dir = get_config_dir()

    if not config_dir.exists():
        try:
            config_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created configuration directory: {config_dir}")
        except OSError as e:
            logger.error(f"Failed to create config directory {config_dir}: {e}")
            raise

    return config_dir
