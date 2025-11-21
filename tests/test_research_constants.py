"""
Tests for Research Tab Constants Module.

Tests UIConstants initialization and StyleSheets generation with DPI-aware scaling.
"""

import unittest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path
import pytest

# Ensure src is in path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Check if Qt is available (may fail in headless environments)
try:
    from bmlibrarian.gui.qt.plugins.research.constants import UIConstants, StyleSheets
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False
    UIConstants = None
    StyleSheets = None

pytestmark = pytest.mark.skipif(not QT_AVAILABLE, reason="Qt/PySide6 not available in this environment")


class TestUIConstants(unittest.TestCase):
    """Test cases for UIConstants initialization and values."""

    def setUp(self):
        """Set up test fixtures with mock scale dictionary."""
        self.scale_dict = {
            'font_xlarge': 14,
            'font_large': 12,
            'font_medium': 11,
            'font_normal': 10,
            'font_small': 9,
            'spacing_large': 20,
            'spacing_medium': 10,
            'spacing_small': 5,
            'padding_small': 5,
            'padding_medium': 10,
            'radius_medium': 8,
            'radius_small': 4,
            'control_height_large': 40,
            'control_height_xlarge': 60,
        }
        self.ui = UIConstants(self.scale_dict)

    # ========================================================================
    # Font Size Tests
    # ========================================================================

    def test_font_sizes_initialized(self):
        """Test that font sizes are initialized from scale_dict."""
        self.assertEqual(self.ui.TITLE_FONT_SIZE, 14)
        self.assertEqual(self.ui.SUBTITLE_FONT_SIZE, 10)
        self.assertEqual(self.ui.TAB_HEADER_FONT_SIZE, 12)
        self.assertEqual(self.ui.CARD_TITLE_FONT_SIZE, 11)
        self.assertEqual(self.ui.CARD_BODY_FONT_SIZE, 10)
        self.assertEqual(self.ui.CARD_LABEL_FONT_SIZE, 9)

    def test_font_sizes_are_integers(self):
        """Test that all font sizes are integers."""
        self.assertIsInstance(self.ui.TITLE_FONT_SIZE, int)
        self.assertIsInstance(self.ui.SUBTITLE_FONT_SIZE, int)
        self.assertIsInstance(self.ui.TAB_HEADER_FONT_SIZE, int)
        self.assertIsInstance(self.ui.CARD_TITLE_FONT_SIZE, int)
        self.assertIsInstance(self.ui.CARD_BODY_FONT_SIZE, int)
        self.assertIsInstance(self.ui.CARD_LABEL_FONT_SIZE, int)

    # ========================================================================
    # Color Tests
    # ========================================================================

    def test_color_values_are_hex_strings(self):
        """Test that color values are valid hex color strings."""
        color_attrs = [
            'COLOR_PRIMARY_BLUE', 'COLOR_PRIMARY_BLUE_HOVER',
            'COLOR_SUCCESS_GREEN', 'COLOR_ERROR_RED',
            'COLOR_DISABLED_GREY', 'COLOR_TEXT_GREY',
            'COLOR_BACKGROUND_GREY', 'COLOR_BORDER_GREY',
            'COLOR_HIGHLIGHT_YELLOW', 'COLOR_HIGHLIGHT_BLUE',
        ]
        for attr in color_attrs:
            color = getattr(self.ui, attr)
            self.assertIsInstance(color, str, f"{attr} should be a string")
            self.assertTrue(
                color.startswith('#') or color in ('white',),
                f"{attr} should be a hex color or named color"
            )

    def test_priority_colors_dictionary(self):
        """Test that PRIORITY_COLORS is a properly structured dictionary."""
        self.assertIsInstance(self.ui.PRIORITY_COLORS, dict)
        self.assertIn('HIGH', self.ui.PRIORITY_COLORS)
        self.assertIn('MEDIUM', self.ui.PRIORITY_COLORS)
        self.assertIn('LOW', self.ui.PRIORITY_COLORS)

        # All values should be hex colors
        for key, value in self.ui.PRIORITY_COLORS.items():
            self.assertTrue(value.startswith('#'), f"PRIORITY_COLORS[{key}] should be hex color")

    # ========================================================================
    # Spacing Tests
    # ========================================================================

    def test_spacing_values_initialized(self):
        """Test that spacing values are initialized from scale_dict."""
        self.assertEqual(self.ui.MAIN_LAYOUT_MARGIN, 20)
        self.assertEqual(self.ui.MAIN_LAYOUT_SPACING, 10)
        self.assertEqual(self.ui.HEADER_SPACING, 5)

    def test_spacing_values_are_positive(self):
        """Test that all spacing values are positive integers."""
        spacing_attrs = [
            'MAIN_LAYOUT_MARGIN', 'MAIN_LAYOUT_SPACING', 'CONTROLS_SPACING',
            'HEADER_BOTTOM_MARGIN', 'HEADER_SPACING', 'TAB_WIDGET_MARGIN',
            'CARD_SPACING', 'SECTION_SPACING', 'BUTTON_SPACING',
        ]
        for attr in spacing_attrs:
            value = getattr(self.ui, attr)
            self.assertIsInstance(value, int, f"{attr} should be an integer")
            self.assertGreater(value, 0, f"{attr} should be positive")

    # ========================================================================
    # Widget Size Tests
    # ========================================================================

    def test_widget_sizes_are_positive(self):
        """Test that widget sizes are positive integers."""
        size_attrs = [
            'QUESTION_INPUT_MIN_HEIGHT', 'QUESTION_INPUT_MAX_HEIGHT',
            'START_BUTTON_MIN_HEIGHT', 'START_BUTTON_MIN_WIDTH',
            'CANCEL_BUTTON_MIN_WIDTH', 'NEW_BUTTON_MIN_WIDTH',
            'SPINBOX_WIDTH', 'QUERY_DISPLAY_MAX_HEIGHT',
            'PROGRESS_BAR_HEIGHT', 'STATUS_BAR_HEIGHT',
        ]
        for attr in size_attrs:
            value = getattr(self.ui, attr)
            self.assertIsInstance(value, int, f"{attr} should be an integer")
            self.assertGreater(value, 0, f"{attr} should be positive")

    # ========================================================================
    # Score Threshold Tests
    # ========================================================================

    def test_score_thresholds_are_floats(self):
        """Test that score thresholds are floats in valid range."""
        self.assertIsInstance(self.ui.SCORE_THRESHOLD_HIGH_RELEVANCE, float)
        self.assertIsInstance(self.ui.SCORE_THRESHOLD_RELEVANT, float)
        self.assertIsInstance(self.ui.SCORE_THRESHOLD_SOMEWHAT_RELEVANT, float)

        # Thresholds should be in 1-5 range
        self.assertGreaterEqual(self.ui.SCORE_THRESHOLD_HIGH_RELEVANCE, 1.0)
        self.assertLessEqual(self.ui.SCORE_THRESHOLD_HIGH_RELEVANCE, 5.0)

    def test_score_thresholds_are_ordered(self):
        """Test that score thresholds are properly ordered."""
        self.assertGreater(
            self.ui.SCORE_THRESHOLD_HIGH_RELEVANCE,
            self.ui.SCORE_THRESHOLD_RELEVANT
        )
        self.assertGreater(
            self.ui.SCORE_THRESHOLD_RELEVANT,
            self.ui.SCORE_THRESHOLD_SOMEWHAT_RELEVANT
        )

    # ========================================================================
    # Spinbox Range Tests
    # ========================================================================

    def test_spinbox_ranges_are_valid(self):
        """Test that spinbox ranges are valid."""
        self.assertLess(self.ui.MAX_RESULTS_MIN, self.ui.MAX_RESULTS_MAX)
        self.assertLess(self.ui.MIN_RELEVANT_MIN, self.ui.MIN_RELEVANT_MAX)

        # Default should be within range
        self.assertGreaterEqual(self.ui.MAX_RESULTS_DEFAULT, self.ui.MAX_RESULTS_MIN)
        self.assertLessEqual(self.ui.MAX_RESULTS_DEFAULT, self.ui.MAX_RESULTS_MAX)

    # ========================================================================
    # Border Radius Tests
    # ========================================================================

    def test_border_radii_are_positive(self):
        """Test that border radii are positive integers."""
        radius_attrs = [
            'CONTROLS_BORDER_RADIUS', 'BUTTON_BORDER_RADIUS',
            'INPUT_BORDER_RADIUS', 'CARD_BORDER_RADIUS',
            'PROGRESS_BAR_RADIUS', 'PROGRESS_BAR_CHUNK_RADIUS',
        ]
        for attr in radius_attrs:
            value = getattr(self.ui, attr)
            self.assertIsInstance(value, int, f"{attr} should be an integer")
            self.assertGreater(value, 0, f"{attr} should be positive")


class TestStyleSheets(unittest.TestCase):
    """Test cases for StyleSheets class methods."""

    def setUp(self):
        """Set up test fixtures."""
        self.scale_dict = {
            'font_xlarge': 14,
            'font_large': 12,
            'font_medium': 11,
            'font_normal': 10,
            'font_small': 9,
            'spacing_large': 20,
            'spacing_medium': 10,
            'spacing_small': 5,
            'padding_small': 5,
            'padding_medium': 10,
            'radius_medium': 8,
            'radius_small': 4,
            'control_height_large': 40,
            'control_height_xlarge': 60,
        }
        self.ui = UIConstants(self.scale_dict)

    # ========================================================================
    # Stylesheet Return Type Tests
    # ========================================================================

    def test_controls_frame_returns_string(self):
        """Test that controls_frame returns a non-empty string."""
        result = StyleSheets.controls_frame(self.ui)
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_start_button_returns_string(self):
        """Test that start_button returns a non-empty string."""
        result = StyleSheets.start_button(self.ui, self.scale_dict)
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_text_input_returns_string(self):
        """Test that text_input returns a non-empty string."""
        result = StyleSheets.text_input(self.ui, self.scale_dict)
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_cancel_button_returns_string(self):
        """Test that cancel_button returns a non-empty string."""
        result = StyleSheets.cancel_button(self.ui)
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_new_button_returns_string(self):
        """Test that new_button returns a non-empty string."""
        result = StyleSheets.new_button(self.ui)
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_save_button_returns_string(self):
        """Test that save_button returns a non-empty string."""
        result = StyleSheets.save_button(self.ui)
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_export_button_returns_string(self):
        """Test that export_button returns a non-empty string."""
        result = StyleSheets.export_button(self.ui)
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_status_bar_returns_string(self):
        """Test that status_bar returns a non-empty string."""
        result = StyleSheets.status_bar(self.ui)
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_progress_bar_returns_string(self):
        """Test that progress_bar returns a non-empty string."""
        result = StyleSheets.progress_bar(self.ui)
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    # ========================================================================
    # Stylesheet Content Tests
    # ========================================================================

    def test_controls_frame_contains_qframe(self):
        """Test that controls_frame stylesheet contains QFrame selector."""
        result = StyleSheets.controls_frame(self.ui)
        self.assertIn('QFrame', result)
        self.assertIn('background-color', result)
        self.assertIn('border-radius', result)

    def test_button_stylesheet_contains_states(self):
        """Test that button stylesheets contain hover/disabled states."""
        result = StyleSheets.start_button(self.ui, self.scale_dict)
        self.assertIn('QPushButton', result)
        self.assertIn('hover', result)
        self.assertIn('disabled', result)

    def test_cancel_button_contains_pressed_state(self):
        """Test that cancel_button stylesheet contains pressed state."""
        result = StyleSheets.cancel_button(self.ui)
        self.assertIn('pressed', result)

    def test_progress_bar_contains_chunk(self):
        """Test that progress_bar stylesheet contains chunk styling."""
        result = StyleSheets.progress_bar(self.ui)
        self.assertIn('QProgressBar', result)
        self.assertIn('chunk', result)

    # ========================================================================
    # Stylesheet Color Integration Tests
    # ========================================================================

    def test_button_uses_ui_colors(self):
        """Test that button stylesheets use colors from UIConstants."""
        result = StyleSheets.start_button(self.ui, self.scale_dict)
        self.assertIn(self.ui.COLOR_PRIMARY_BLUE, result)
        self.assertIn(self.ui.COLOR_PRIMARY_BLUE_HOVER, result)

    def test_cancel_button_uses_error_colors(self):
        """Test that cancel_button uses error colors."""
        result = StyleSheets.cancel_button(self.ui)
        self.assertIn(self.ui.COLOR_ERROR_RED, result)
        self.assertIn(self.ui.COLOR_ERROR_RED_HOVER, result)

    def test_save_button_uses_success_colors(self):
        """Test that save_button uses success colors."""
        result = StyleSheets.save_button(self.ui)
        self.assertIn(self.ui.COLOR_SUCCESS_GREEN, result)
        self.assertIn(self.ui.COLOR_SUCCESS_GREEN_HOVER, result)

    # ========================================================================
    # Stylesheet Spacing Integration Tests
    # ========================================================================

    def test_stylesheets_use_scaled_values(self):
        """Test that stylesheets use scaled pixel values."""
        result = StyleSheets.controls_frame(self.ui)
        # Should contain pixel values with 'px' suffix
        self.assertIn('px', result)

    def test_empty_state_label_returns_string(self):
        """Test that empty_state_label returns a non-empty string."""
        result = StyleSheets.empty_state_label(self.ui)
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)
        self.assertIn(self.ui.COLOR_TEXT_GREY, result)

    def test_error_label_returns_static_string(self):
        """Test that error_label returns a static string (no UIConstants needed)."""
        result = StyleSheets.error_label()
        self.assertIsInstance(result, str)
        self.assertIn('red', result)


class TestUIConstantsEdgeCases(unittest.TestCase):
    """Edge case tests for UIConstants."""

    def test_handles_zero_scale_values(self):
        """Test that UIConstants handles zero values gracefully."""
        scale_dict = {
            'font_xlarge': 0,
            'font_large': 0,
            'font_medium': 0,
            'font_normal': 0,
            'font_small': 0,
            'spacing_large': 0,
            'spacing_medium': 0,
            'spacing_small': 0,
            'padding_small': 0,
            'padding_medium': 0,
            'radius_medium': 0,
            'radius_small': 0,
            'control_height_large': 0,
            'control_height_xlarge': 0,
        }
        # Should not raise exception
        ui = UIConstants(scale_dict)
        self.assertEqual(ui.TITLE_FONT_SIZE, 0)

    def test_handles_large_scale_values(self):
        """Test that UIConstants handles large scale values."""
        scale_dict = {
            'font_xlarge': 100,
            'font_large': 80,
            'font_medium': 60,
            'font_normal': 50,
            'font_small': 40,
            'spacing_large': 200,
            'spacing_medium': 100,
            'spacing_small': 50,
            'padding_small': 50,
            'padding_medium': 100,
            'radius_medium': 80,
            'radius_small': 40,
            'control_height_large': 400,
            'control_height_xlarge': 600,
        }
        # Should not raise exception
        ui = UIConstants(scale_dict)
        self.assertEqual(ui.TITLE_FONT_SIZE, 100)
        self.assertEqual(ui.MAIN_LAYOUT_MARGIN, 200)


if __name__ == '__main__':
    unittest.main()
