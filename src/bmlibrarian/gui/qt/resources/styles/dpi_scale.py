"""
DPI-aware font scaling system for Qt UI.

Provides centralized font-relative dimension calculation based on system
default font to ensure consistent, readable UI across all display densities.
"""

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QFontMetrics
from typing import Dict


class FontScale:
    """
    Singleton class for DPI-aware font-relative scaling dimensions.

    Queries the OS for system default font and calculates all UI dimensions
    relative to font metrics (line height, character width) to ensure
    proper scaling across different DPI settings.
    """

    _instance = None
    _scale_dict: Dict = None

    def __new__(cls):
        """Singleton pattern to ensure consistent scaling across application."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._calculate_scale()
        return cls._instance

    def _calculate_scale(self):
        """Calculate font-relative scaling dimensions from system default font."""
        # Get system default font
        default_font = QApplication.font()
        base_font_size = default_font.pointSize()
        if base_font_size <= 0:
            base_font_size = 10  # Fallback to 10pt if system font size unavailable

        # Calculate font metrics for precise measurements
        metrics = QFontMetrics(default_font)
        base_line_height = metrics.lineSpacing()
        char_width = metrics.averageCharWidth()

        # Create scaling dictionary with font-relative dimensions
        # All dimensions are multiples of base font size or line height
        self._scale_dict = {
            # Base measurements
            'base_font_size': base_font_size,
            'base_line_height': base_line_height,
            'char_width': char_width,

            # Font sizes (in points, DPI-independent)
            'font_tiny': max(7, int(base_font_size * 0.7)),       # Very small text
            'font_small': max(8, int(base_font_size * 0.85)),     # Slightly smaller
            'font_normal': base_font_size,                         # System default
            'font_medium': max(10, int(base_font_size * 1.1)),    # Slightly larger
            'font_large': max(12, int(base_font_size * 1.2)),     # Headers
            'font_xlarge': max(14, int(base_font_size * 1.4)),    # Large headers
            'font_icon': max(16, int(base_font_size * 1.8)),      # Icons

            # Spacing (in pixels, relative to line height)
            'spacing_tiny': max(2, int(base_line_height * 0.15)),    # 2-3px
            'spacing_small': max(4, int(base_line_height * 0.25)),   # 4-6px
            'spacing_medium': max(6, int(base_line_height * 0.4)),   # 6-10px
            'spacing_large': max(8, int(base_line_height * 0.5)),    # 8-12px
            'spacing_xlarge': max(12, int(base_line_height * 0.75)), # 12-18px

            # Padding (in pixels, relative to line height)
            'padding_tiny': max(2, int(base_line_height * 0.15)),
            'padding_small': max(4, int(base_line_height * 0.3)),
            'padding_medium': max(6, int(base_line_height * 0.4)),
            'padding_large': max(8, int(base_line_height * 0.6)),
            'padding_xlarge': max(12, int(base_line_height * 0.9)),

            # Control heights (in pixels, relative to line height)
            'control_height_small': max(24, int(base_line_height * 1.8)),
            'control_height_medium': max(30, int(base_line_height * 2.2)),
            'control_height_large': max(40, int(base_line_height * 2.8)),
            'control_height_xlarge': max(50, int(base_line_height * 3.5)),

            # Border radius (in pixels, relative to line height)
            'radius_tiny': max(2, int(base_line_height * 0.15)),
            'radius_small': max(4, int(base_line_height * 0.3)),
            'radius_medium': max(8, int(base_line_height * 0.5)),
            'radius_large': max(12, int(base_line_height * 0.9)),

            # Chat bubble dimensions (character-width based)
            'bubble_margin_large': max(24, int(char_width * 3.5)),  # More padding side
            'bubble_margin_small': max(6, int(char_width * 0.8)),   # Less padding side
            'bubble_padding': max(10, int(base_line_height * 0.7)),
            'bubble_max_width': max(500, int(char_width * 70)),     # ~70 characters wide
            'bubble_radius': max(12, int(base_line_height * 0.9)),

            # Icon sizes (in pixels, relative to line height)
            'icon_tiny': max(12, int(base_line_height * 0.8)),
            'icon_small': max(16, int(base_line_height * 1.0)),
            'icon_medium': max(24, int(base_line_height * 1.5)),
            'icon_large': max(32, int(base_line_height * 2.0)),
            'icon_xlarge': max(48, int(base_line_height * 3.0)),
        }

    def get(self, key: str, default=None):
        """Get a scale value by key."""
        return self._scale_dict.get(key, default)

    def __getitem__(self, key: str):
        """Allow dictionary-style access to scale values."""
        return self._scale_dict[key]

    def to_dict(self) -> Dict:
        """Return the entire scale dictionary."""
        return self._scale_dict.copy()

    def refresh(self):
        """Recalculate scale values (call if system font changes)."""
        self._calculate_scale()


def get_font_scale() -> Dict:
    """
    Get font-relative scaling dimensions based on system default font.

    This is a convenience function that returns a dictionary of scaling
    values. For repeated access, consider using the FontScale singleton
    directly for better performance.

    Returns:
        dict: Scaling factors and base dimensions for DPI-independent layout
    """
    return FontScale().to_dict()


def get_scale_value(key: str, default=None):
    """
    Get a single scale value by key.

    Args:
        key: Scale value key (e.g., 'font_medium', 'spacing_large')
        default: Default value if key not found

    Returns:
        Scaled value or default
    """
    return FontScale().get(key, default)
