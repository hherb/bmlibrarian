"""
Qt UI styling system with DPI-aware font-relative dimensions.

This module provides centralized styling utilities that ensure consistent
appearance across different screen DPIs and user font preferences.

Usage:
    from bmlibrarian.gui.qt.resources.styles import get_font_scale, StylesheetGenerator

    # Get scaling dictionary
    scale = get_font_scale()

    # Use in f-strings
    widget.setStyleSheet(f"font-size: {scale['font_medium']}pt;")

    # Or use StylesheetGenerator for common patterns
    gen = StylesheetGenerator()
    button.setStyleSheet(gen.button_stylesheet())
"""

from .dpi_scale import (
    FontScale,
    get_font_scale,
    get_scale_value,
)

from .stylesheet_generator import (
    StylesheetGenerator,
    get_stylesheet_generator,
    apply_button_style,
    apply_input_style,
    apply_header_style,
)

__all__ = [
    # DPI scaling
    'FontScale',
    'get_font_scale',
    'get_scale_value',

    # Stylesheet generation
    'StylesheetGenerator',
    'get_stylesheet_generator',
    'apply_button_style',
    'apply_input_style',
    'apply_header_style',
]
