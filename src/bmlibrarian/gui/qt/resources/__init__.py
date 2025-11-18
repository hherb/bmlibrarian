"""
Qt resources for BMLibrarian GUI.

Provides centralized access to styles, icons, and other UI resources.
"""

from .styles import (
    FontScale,
    get_font_scale,
    get_scale_value,
    StylesheetGenerator,
    get_stylesheet_generator,
    apply_button_style,
    apply_input_style,
    apply_header_style,
)

__all__ = [
    # DPI-aware styling
    'FontScale',
    'get_font_scale',
    'get_scale_value',
    'StylesheetGenerator',
    'get_stylesheet_generator',
    'apply_button_style',
    'apply_input_style',
    'apply_header_style',
]
