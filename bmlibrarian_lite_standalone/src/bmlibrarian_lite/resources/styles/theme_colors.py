"""
Centralized theme colors for BMLibrarian Qt GUI.

Provides a single source of truth for all UI colors, following Material Design
color palette conventions. This eliminates hardcoded colors scattered throughout
the codebase and makes theme switching easier.

Usage:
    from bmlibrarian_lite.resources.styles.theme_colors import ThemeColors

    # Use colors in stylesheets
    style = f"background-color: {ThemeColors.SUCCESS_BG};"

    # Or use the get_color function for named access
    color = ThemeColors.get_color('success_bg')
"""

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class MaterialColors:
    """
    Material Design color palette constants.

    Reference: https://m2.material.io/design/color/the-color-system.html
    """
    # Primary colors
    PRIMARY_50 = "#e3f2fd"
    PRIMARY_100 = "#bbdefb"
    PRIMARY_200 = "#90caf9"
    PRIMARY_300 = "#64b5f6"
    PRIMARY_400 = "#42a5f5"
    PRIMARY_500 = "#2196f3"  # Standard Blue
    PRIMARY_600 = "#1e88e5"
    PRIMARY_700 = "#1976d2"
    PRIMARY_800 = "#1565c0"
    PRIMARY_900 = "#0d47a1"

    # Success colors (Green)
    SUCCESS_50 = "#e8f5e9"
    SUCCESS_100 = "#c8e6c9"
    SUCCESS_200 = "#a5d6a7"
    SUCCESS_300 = "#81c784"
    SUCCESS_400 = "#66bb6a"
    SUCCESS_500 = "#4caf50"  # Standard Green
    SUCCESS_600 = "#43a047"
    SUCCESS_700 = "#388e3c"
    SUCCESS_800 = "#2e7d32"
    SUCCESS_900 = "#1b5e20"

    # Warning colors (Orange)
    WARNING_50 = "#fff3e0"
    WARNING_100 = "#ffe0b2"
    WARNING_200 = "#ffcc80"
    WARNING_300 = "#ffb74d"
    WARNING_400 = "#ffa726"
    WARNING_500 = "#ff9800"  # Standard Orange
    WARNING_600 = "#fb8c00"
    WARNING_700 = "#f57c00"
    WARNING_800 = "#ef6c00"
    WARNING_900 = "#e65100"

    # Error colors (Red)
    ERROR_50 = "#ffebee"
    ERROR_100 = "#ffcdd2"
    ERROR_200 = "#ef9a9a"
    ERROR_300 = "#e57373"
    ERROR_400 = "#ef5350"
    ERROR_500 = "#f44336"  # Standard Red
    ERROR_600 = "#e53935"
    ERROR_700 = "#d32f2f"
    ERROR_800 = "#c62828"
    ERROR_900 = "#b71c1c"

    # Grey colors
    GREY_50 = "#fafafa"
    GREY_100 = "#f5f5f5"
    GREY_200 = "#eeeeee"
    GREY_300 = "#e0e0e0"
    GREY_400 = "#bdbdbd"
    GREY_500 = "#9e9e9e"
    GREY_600 = "#757575"
    GREY_700 = "#616161"
    GREY_800 = "#424242"
    GREY_900 = "#212121"


class ThemeColors:
    """
    Application theme colors built on Material Design palette.

    Groups colors by semantic meaning for easy use throughout the application.
    All colors are class attributes for direct access without instantiation.
    """

    # ==========================================================================
    # Success State Colors (Green theme)
    # ==========================================================================
    SUCCESS_BG = MaterialColors.SUCCESS_50           # Light green background
    SUCCESS_BORDER = MaterialColors.SUCCESS_500      # Green border
    SUCCESS_TEXT = MaterialColors.SUCCESS_800        # Dark green text
    SUCCESS_HOVER_BG = MaterialColors.SUCCESS_100    # Hover background

    # ==========================================================================
    # Warning State Colors (Orange theme)
    # ==========================================================================
    WARNING_BG = MaterialColors.WARNING_50           # Light orange background
    WARNING_BORDER = MaterialColors.WARNING_500      # Orange border
    WARNING_TEXT = MaterialColors.WARNING_800        # Dark orange text
    WARNING_HOVER_BG = MaterialColors.WARNING_100    # Hover background

    # ==========================================================================
    # Error State Colors (Red theme)
    # ==========================================================================
    ERROR_BG = MaterialColors.ERROR_50               # Light red background
    ERROR_BORDER = MaterialColors.ERROR_500          # Red border
    ERROR_TEXT = MaterialColors.ERROR_700            # Dark red text
    ERROR_HOVER_BG = MaterialColors.ERROR_100        # Hover background

    # ==========================================================================
    # Primary/Info State Colors (Blue theme)
    # ==========================================================================
    PRIMARY_BG = MaterialColors.PRIMARY_50           # Light blue background
    PRIMARY_BORDER = MaterialColors.PRIMARY_500      # Blue border
    PRIMARY_TEXT = MaterialColors.PRIMARY_800        # Dark blue text
    PRIMARY_HOVER_BG = MaterialColors.PRIMARY_100    # Hover background

    # ==========================================================================
    # Neutral Colors
    # ==========================================================================
    TEXT_PRIMARY = MaterialColors.GREY_900           # Main text color
    TEXT_SECONDARY = MaterialColors.GREY_700         # Secondary text
    TEXT_MUTED = MaterialColors.GREY_600             # Muted/disabled text
    TEXT_DISABLED = MaterialColors.GREY_400          # Disabled text

    BACKGROUND = MaterialColors.GREY_50              # Page background
    SURFACE = "#ffffff"                              # Card/surface background
    DIVIDER = MaterialColors.GREY_300                # Dividers and borders

    # ==========================================================================
    # Button Colors
    # ==========================================================================
    BUTTON_PRIMARY = MaterialColors.PRIMARY_700      # Primary button
    BUTTON_PRIMARY_HOVER = MaterialColors.PRIMARY_800
    BUTTON_SUCCESS = MaterialColors.SUCCESS_700      # Success/confirm button
    BUTTON_SUCCESS_HOVER = MaterialColors.SUCCESS_800
    BUTTON_WARNING = MaterialColors.WARNING_700      # Warning button
    BUTTON_WARNING_HOVER = MaterialColors.WARNING_800
    BUTTON_DANGER = MaterialColors.ERROR_700         # Danger/delete button
    BUTTON_DANGER_HOVER = MaterialColors.ERROR_800

    # ==========================================================================
    # PDF Button Colors (specific to document card system)
    # ==========================================================================
    PDF_VIEW_BG = MaterialColors.PRIMARY_700         # Blue - view local PDF
    PDF_VIEW_HOVER = MaterialColors.PRIMARY_800
    PDF_FETCH_BG = MaterialColors.WARNING_700        # Orange - download PDF
    PDF_FETCH_HOVER = MaterialColors.WARNING_800
    PDF_UPLOAD_BG = MaterialColors.SUCCESS_700       # Green - upload PDF
    PDF_UPLOAD_HOVER = MaterialColors.SUCCESS_800

    # ==========================================================================
    # Score/Rating Colors
    # ==========================================================================
    SCORE_HIGH = MaterialColors.SUCCESS_500          # High score (4-5)
    SCORE_MEDIUM = MaterialColors.WARNING_500        # Medium score (2-3)
    SCORE_LOW = MaterialColors.ERROR_500             # Low score (1)

    # ==========================================================================
    # Color Lookup Dictionary
    # ==========================================================================
    _color_map: Dict[str, str] = {}

    @classmethod
    def get_color(cls, name: str) -> Optional[str]:
        """
        Get a color by its name (case-insensitive).

        Args:
            name: Color name (e.g., 'success_bg', 'error_text')

        Returns:
            Hex color string or None if not found
        """
        # Build map on first access
        if not cls._color_map:
            cls._color_map = {
                key.lower(): value
                for key, value in vars(cls).items()
                if isinstance(value, str) and value.startswith('#')
            }

        return cls._color_map.get(name.lower())

    @classmethod
    def get_all_colors(cls) -> Dict[str, str]:
        """
        Get all theme colors as a dictionary.

        Returns:
            Dict mapping color names to hex values
        """
        return {
            key: value
            for key, value in vars(cls).items()
            if isinstance(value, str) and value.startswith('#')
        }


# =============================================================================
# Backwards Compatibility Aliases
# =============================================================================
# These match the hardcoded values that were previously in pdf_upload_widget.py
COLOR_SUCCESS_BG = ThemeColors.SUCCESS_BG
COLOR_SUCCESS_BORDER = ThemeColors.SUCCESS_BORDER
COLOR_SUCCESS_TEXT = ThemeColors.SUCCESS_TEXT
COLOR_TEXT_MUTED = ThemeColors.TEXT_MUTED
