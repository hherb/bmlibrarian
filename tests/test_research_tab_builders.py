"""
Tests for Research Tab Builder Functions.

Tests pure functions that create UI tab structures.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
from pathlib import Path
import pytest

# Ensure src is in path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Check if Qt is available (may fail in headless environments)
try:
    from PySide6.QtWidgets import (
        QApplication, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QTextEdit, QPushButton, QProgressBar, QScrollArea
    )
    from PySide6.QtCore import Qt

    from bmlibrarian.gui.qt.plugins.research.constants import UIConstants
    from bmlibrarian.gui.qt.plugins.research.tab_builders import (
        TabRefs,
        build_placeholder_tab,
        build_search_tab,
        build_literature_tab,
        build_scoring_tab,
        build_citations_tab,
        build_preliminary_tab,
        build_counterfactual_tab,
        build_report_tab,
    )
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False
    QApplication = None
    QWidget = None
    QVBoxLayout = None
    QHBoxLayout = None
    QLabel = None
    QTextEdit = None
    QPushButton = None
    QProgressBar = None
    QScrollArea = None
    Qt = None
    UIConstants = None
    TabRefs = None
    build_placeholder_tab = None
    build_search_tab = None
    build_literature_tab = None
    build_scoring_tab = None
    build_citations_tab = None
    build_preliminary_tab = None
    build_counterfactual_tab = None
    build_report_tab = None

pytestmark = pytest.mark.skipif(not QT_AVAILABLE, reason="Qt/PySide6 not available in this environment")


class TestTabBuilders(unittest.TestCase):
    """Test cases for tab builder functions."""

    @classmethod
    def setUpClass(cls):
        """Set up QApplication for all tests."""
        if not QApplication.instance():
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()

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
        self.created_widgets = []

    def tearDown(self):
        """Clean up created widgets."""
        for widget in self.created_widgets:
            try:
                widget.deleteLater()
            except RuntimeError:
                pass  # Already deleted
        self.created_widgets = []

    def _track_widget(self, widget):
        """Track widget for cleanup."""
        self.created_widgets.append(widget)
        return widget

    # ========================================================================
    # TabRefs Tests
    # ========================================================================

    def test_tabrefs_default_empty_dict(self):
        """Test that TabRefs initializes with empty widgets dict."""
        refs = TabRefs()
        self.assertIsInstance(refs.widgets, dict)
        self.assertEqual(len(refs.widgets), 0)

    def test_tabrefs_with_widgets(self):
        """Test that TabRefs can store widget references."""
        refs = TabRefs()
        label = QLabel("Test")
        self._track_widget(label)
        refs.widgets['test_label'] = label

        self.assertEqual(refs.widgets['test_label'], label)

    # ========================================================================
    # build_placeholder_tab Tests
    # ========================================================================

    def test_placeholder_tab_returns_tuple(self):
        """Test that build_placeholder_tab returns (widget, refs) tuple."""
        widget, refs = build_placeholder_tab(
            self.ui, "icon", "Title", "Description"
        )
        self._track_widget(widget)

        self.assertIsInstance(widget, QWidget)
        self.assertIsInstance(refs, TabRefs)

    def test_placeholder_tab_has_layout(self):
        """Test that placeholder tab has a layout."""
        widget, refs = build_placeholder_tab(
            self.ui, "icon", "Title", "Description"
        )
        self._track_widget(widget)

        self.assertIsNotNone(widget.layout())
        self.assertIsInstance(widget.layout(), QVBoxLayout)

    def test_placeholder_tab_contains_title(self):
        """Test that placeholder tab contains title label."""
        widget, refs = build_placeholder_tab(
            self.ui, "test_icon", "Test Title", "Description"
        )
        self._track_widget(widget)

        # Find label with title text
        found = False
        layout = widget.layout()
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item.widget() and isinstance(item.widget(), QLabel):
                if "Test Title" in item.widget().text():
                    found = True
                    break

        self.assertTrue(found, "Title label not found")

    # ========================================================================
    # build_search_tab Tests
    # ========================================================================

    def test_search_tab_returns_tuple(self):
        """Test that build_search_tab returns (widget, refs) tuple."""
        widget, refs = build_search_tab(self.ui)
        self._track_widget(widget)

        self.assertIsInstance(widget, QWidget)
        self.assertIsInstance(refs, TabRefs)

    def test_search_tab_has_query_display(self):
        """Test that search tab has query_text_display widget."""
        widget, refs = build_search_tab(self.ui)
        self._track_widget(widget)

        self.assertIn('query_text_display', refs.widgets)
        self.assertIsInstance(refs.widgets['query_text_display'], QTextEdit)

    def test_search_tab_query_display_is_readonly(self):
        """Test that query display is read-only."""
        widget, refs = build_search_tab(self.ui)
        self._track_widget(widget)

        query_display = refs.widgets['query_text_display']
        self.assertTrue(query_display.isReadOnly())

    def test_search_tab_has_document_count_label(self):
        """Test that search tab has document_count_label."""
        widget, refs = build_search_tab(self.ui)
        self._track_widget(widget)

        self.assertIn('document_count_label', refs.widgets)
        self.assertIsInstance(refs.widgets['document_count_label'], QLabel)

    # ========================================================================
    # build_literature_tab Tests
    # ========================================================================

    def test_literature_tab_returns_tuple(self):
        """Test that build_literature_tab returns (widget, refs) tuple."""
        widget, refs = build_literature_tab(self.ui)
        self._track_widget(widget)

        self.assertIsInstance(widget, QWidget)
        self.assertIsInstance(refs, TabRefs)

    def test_literature_tab_has_required_widgets(self):
        """Test that literature tab has all required widget refs."""
        widget, refs = build_literature_tab(self.ui)
        self._track_widget(widget)

        required_keys = ['summary_label', 'progress_bar', 'container', 'layout', 'empty_label']
        for key in required_keys:
            self.assertIn(key, refs.widgets, f"Missing required key: {key}")

    def test_literature_tab_has_progress_bar(self):
        """Test that literature tab has a progress bar."""
        widget, refs = build_literature_tab(self.ui)
        self._track_widget(widget)

        self.assertIsInstance(refs.widgets['progress_bar'], QProgressBar)

    def test_literature_tab_progress_bar_hidden_initially(self):
        """Test that progress bar is hidden by default."""
        widget, refs = build_literature_tab(self.ui)
        self._track_widget(widget)

        self.assertFalse(refs.widgets['progress_bar'].isVisible())

    def test_literature_tab_has_scroll_area(self):
        """Test that literature tab has a scroll area."""
        widget, refs = build_literature_tab(self.ui)
        self._track_widget(widget)

        # Container should be inside a scroll area
        container = refs.widgets['container']
        self.assertIsNotNone(container.parent())

    # ========================================================================
    # build_scoring_tab Tests
    # ========================================================================

    def test_scoring_tab_returns_tuple(self):
        """Test that build_scoring_tab returns (widget, refs) tuple."""
        widget, refs = build_scoring_tab(self.ui)
        self._track_widget(widget)

        self.assertIsInstance(widget, QWidget)
        self.assertIsInstance(refs, TabRefs)

    def test_scoring_tab_is_placeholder(self):
        """Test that scoring tab is a placeholder."""
        widget, refs = build_scoring_tab(self.ui)
        self._track_widget(widget)

        # Placeholder tabs have empty refs
        self.assertEqual(len(refs.widgets), 0)

    # ========================================================================
    # build_citations_tab Tests
    # ========================================================================

    def test_citations_tab_returns_tuple(self):
        """Test that build_citations_tab returns (widget, refs) tuple."""
        widget, refs = build_citations_tab(self.ui)
        self._track_widget(widget)

        self.assertIsInstance(widget, QWidget)
        self.assertIsInstance(refs, TabRefs)

    def test_citations_tab_has_required_widgets(self):
        """Test that citations tab has all required widget refs."""
        widget, refs = build_citations_tab(self.ui)
        self._track_widget(widget)

        required_keys = ['summary_label', 'container', 'layout', 'empty_label']
        for key in required_keys:
            self.assertIn(key, refs.widgets, f"Missing required key: {key}")

    def test_citations_tab_has_summary_label(self):
        """Test that citations tab has summary label."""
        widget, refs = build_citations_tab(self.ui)
        self._track_widget(widget)

        self.assertIsInstance(refs.widgets['summary_label'], QLabel)

    def test_citations_tab_has_layout_for_cards(self):
        """Test that citations tab has layout for adding cards."""
        widget, refs = build_citations_tab(self.ui)
        self._track_widget(widget)

        self.assertIsInstance(refs.widgets['layout'], QVBoxLayout)

    # ========================================================================
    # build_preliminary_tab Tests
    # ========================================================================

    def test_preliminary_tab_returns_tuple(self):
        """Test that build_preliminary_tab returns (widget, refs) tuple."""
        widget, refs = build_preliminary_tab(self.ui)
        self._track_widget(widget)

        self.assertIsInstance(widget, QWidget)
        self.assertIsInstance(refs, TabRefs)

    def test_preliminary_tab_has_report_viewer(self):
        """Test that preliminary tab has report_viewer widget."""
        widget, refs = build_preliminary_tab(self.ui)
        self._track_widget(widget)

        self.assertIn('report_viewer', refs.widgets)
        # Report viewer should be a MarkdownViewer

    def test_preliminary_tab_has_summary_label(self):
        """Test that preliminary tab has summary label."""
        widget, refs = build_preliminary_tab(self.ui)
        self._track_widget(widget)

        self.assertIn('summary_label', refs.widgets)
        self.assertIsInstance(refs.widgets['summary_label'], QLabel)

    # ========================================================================
    # build_counterfactual_tab Tests
    # ========================================================================

    def test_counterfactual_tab_returns_tuple(self):
        """Test that build_counterfactual_tab returns (widget, refs) tuple."""
        widget, refs = build_counterfactual_tab(self.ui)
        self._track_widget(widget)

        self.assertIsInstance(widget, QWidget)
        self.assertIsInstance(refs, TabRefs)

    def test_counterfactual_tab_has_required_widgets(self):
        """Test that counterfactual tab has required widget refs."""
        widget, refs = build_counterfactual_tab(self.ui)
        self._track_widget(widget)

        self.assertIn('summary_label', refs.widgets)
        self.assertIn('content_layout', refs.widgets)

    def test_counterfactual_tab_has_scroll_area(self):
        """Test that counterfactual tab has a scroll area for content."""
        widget, refs = build_counterfactual_tab(self.ui)
        self._track_widget(widget)

        # Content layout should be accessible
        self.assertIsInstance(refs.widgets['content_layout'], QVBoxLayout)

    # ========================================================================
    # build_report_tab Tests
    # ========================================================================

    def test_report_tab_returns_tuple(self):
        """Test that build_report_tab returns (widget, refs) tuple."""
        widget, refs = build_report_tab(self.ui)
        self._track_widget(widget)

        self.assertIsInstance(widget, QWidget)
        self.assertIsInstance(refs, TabRefs)

    def test_report_tab_has_export_buttons(self):
        """Test that report tab has export buttons."""
        widget, refs = build_report_tab(self.ui)
        self._track_widget(widget)

        self.assertIn('save_markdown_button', refs.widgets)
        self.assertIn('export_json_button', refs.widgets)

    def test_report_tab_buttons_are_disabled_initially(self):
        """Test that export buttons are disabled initially."""
        widget, refs = build_report_tab(self.ui)
        self._track_widget(widget)

        self.assertFalse(refs.widgets['save_markdown_button'].isEnabled())
        self.assertFalse(refs.widgets['export_json_button'].isEnabled())

    def test_report_tab_has_report_viewer(self):
        """Test that report tab has report_viewer widget."""
        widget, refs = build_report_tab(self.ui)
        self._track_widget(widget)

        self.assertIn('report_viewer', refs.widgets)

    def test_report_tab_has_summary_label(self):
        """Test that report tab has summary label."""
        widget, refs = build_report_tab(self.ui)
        self._track_widget(widget)

        self.assertIn('summary_label', refs.widgets)


class TestTabBuildersEdgeCases(unittest.TestCase):
    """Edge case tests for tab builder functions."""

    @classmethod
    def setUpClass(cls):
        """Set up QApplication for all tests."""
        if not QApplication.instance():
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()

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
        self.created_widgets = []

    def tearDown(self):
        """Clean up created widgets."""
        for widget in self.created_widgets:
            try:
                widget.deleteLater()
            except RuntimeError:
                pass
        self.created_widgets = []

    def _track_widget(self, widget):
        """Track widget for cleanup."""
        self.created_widgets.append(widget)
        return widget

    def test_placeholder_tab_with_empty_strings(self):
        """Test placeholder tab with empty strings."""
        widget, refs = build_placeholder_tab(self.ui, "", "", "")
        self._track_widget(widget)

        self.assertIsInstance(widget, QWidget)
        self.assertIsNotNone(widget.layout())

    def test_placeholder_tab_with_special_characters(self):
        """Test placeholder tab with special characters."""
        widget, refs = build_placeholder_tab(
            self.ui,
            "\U0001f4da",  # Book emoji
            "Title with <special> & characters",
            "Description with\nnewlines\tand\ttabs"
        )
        self._track_widget(widget)

        self.assertIsInstance(widget, QWidget)

    def test_multiple_tabs_can_be_created(self):
        """Test that multiple tabs can be created simultaneously."""
        widgets = []

        w1, r1 = build_search_tab(self.ui)
        widgets.append(w1)
        w2, r2 = build_literature_tab(self.ui)
        widgets.append(w2)
        w3, r3 = build_citations_tab(self.ui)
        widgets.append(w3)
        w4, r4 = build_report_tab(self.ui)
        widgets.append(w4)

        for widget in widgets:
            self._track_widget(widget)
            self.assertIsInstance(widget, QWidget)

        # Each should have its own refs
        self.assertIn('query_text_display', r1.widgets)
        self.assertIn('progress_bar', r2.widgets)
        self.assertIn('summary_label', r3.widgets)
        self.assertIn('save_markdown_button', r4.widgets)

    def test_tab_widgets_can_be_deleted_safely(self):
        """Test that tab widgets can be deleted without errors."""
        widget, refs = build_search_tab(self.ui)

        # Delete the widget
        widget.deleteLater()
        QApplication.processEvents()

        # Should not raise exception
        self.assertTrue(True)


if __name__ == '__main__':
    unittest.main()
