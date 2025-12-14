"""
Utility functions for the Setup Wizard module.

Contains shared pure functions used across wizard pages.
"""

import logging
from pathlib import Path

from ..resources.styles.stylesheet_generator import StylesheetGenerator

logger = logging.getLogger(__name__)

# File permission constant for secure .env files (owner read/write only)
ENV_FILE_PERMISSIONS = 0o600

# Default database name and application user
DEFAULT_DATABASE_NAME = "bmlibrarian"
DEFAULT_APP_USER = "bmlibrarian"


def find_project_root() -> Path:
    """
    Find the project root directory by looking for pyproject.toml.

    Searches from the current file's location upward through parent directories
    until it finds a directory containing pyproject.toml or reaches the
    filesystem root.

    Returns:
        Path: The project root directory, or current working directory if not found.
    """
    current = Path(__file__).parent
    while current != current.parent:
        if (current / "pyproject.toml").exists():
            return current
        current = current.parent
    # Fallback to current working directory
    return Path.cwd()


def create_frame_stylesheet(
    scale: dict, bg_color: str, border_color: str, object_name: str
) -> str:
    """
    Create a stylesheet for a colored frame using StylesheetGenerator.

    Args:
        scale: Font scale dictionary from dpi_scale.get_font_scale()
        bg_color: Background color hex code
        border_color: Border color hex code
        object_name: QFrame object name for CSS selector

    Returns:
        str: Generated stylesheet string
    """
    gen = StylesheetGenerator(scale)
    # Use double braces for CSS syntax, single braces for format placeholders
    # Note: f-string is NOT used here to avoid conflicts with .format()
    template = """
        QFrame#OBJECT_NAME {{
            background-color: BG_COLOR;
            border: 1px solid BORDER_COLOR;
            border-radius: {radius_small}px;
            padding: {padding_medium}px;
        }}
    """
    # First substitute scale values, then replace our placeholders
    styled = gen.custom(template)
    return (
        styled
        .replace("OBJECT_NAME", object_name)
        .replace("BG_COLOR", bg_color)
        .replace("BORDER_COLOR", border_color)
    )


def format_authors_short(authors: list | str | None, max_authors: int = 3) -> str:
    """
    Format author list for display, truncating with 'et al.' if needed.

    Args:
        authors: List of author names, string, or None
        max_authors: Maximum number of authors to show before truncating

    Returns:
        Formatted author string
    """
    if not authors:
        return "Unknown"

    if isinstance(authors, str):
        return authors

    if isinstance(authors, list):
        if len(authors) > max_authors:
            return ", ".join(authors[:max_authors]) + " et al."
        return ", ".join(authors) if authors else "Unknown"

    return str(authors)


def format_date_short(date_value: object) -> str:
    """
    Format a date value for display (YYYY-MM-DD format).

    Args:
        date_value: Date object or string

    Returns:
        Formatted date string or 'No date' if None
    """
    if date_value is None:
        return "No date"
    return str(date_value)[:10]


def create_muted_label_stylesheet(color: str) -> str:
    """
    Create a stylesheet for muted/italicized label text.

    Args:
        color: Text color hex code

    Returns:
        str: Generated stylesheet string
    """
    return f"color: {color}; font-style: italic;"


def create_metadata_label_stylesheet(scale: dict, bg_color: str) -> str:
    """
    Create a stylesheet for metadata display labels.

    Args:
        scale: Font scale dictionary from dpi_scale.get_font_scale()
        bg_color: Background color hex code

    Returns:
        str: Generated stylesheet string
    """
    gen = StylesheetGenerator(scale)
    template = """
        QLabel {{
            background-color: BG_COLOR;
            padding: {padding_medium}px;
            border-radius: {radius_small}px;
        }}
    """
    styled = gen.custom(template)
    return styled.replace("BG_COLOR", bg_color)


def calculate_splitter_sizes(
    total_width: int, list_ratio: int, preview_ratio: int
) -> list:
    """
    Calculate splitter sizes based on ratios.

    Args:
        total_width: Total available width
        list_ratio: Percentage for list panel (0-100)
        preview_ratio: Percentage for preview panel (0-100)

    Returns:
        List of sizes for splitter.setSizes()
    """
    list_size = int(total_width * list_ratio / 100)
    preview_size = int(total_width * preview_ratio / 100)
    return [list_size, preview_size]
