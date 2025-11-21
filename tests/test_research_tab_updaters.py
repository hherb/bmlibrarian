"""
Tests for Research Tab Updater Functions.

Tests functions that update tab content with data.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import logging
from pathlib import Path
import pytest

# Ensure src is in path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Check if Qt is available (may fail in headless environments)
try:
    from PySide6.QtWidgets import (
        QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
    )
    from PySide6.QtCore import Qt

    from bmlibrarian.gui.qt.plugins.research.constants import UIConstants
    from bmlibrarian.gui.qt.plugins.research.tab_updaters import (
        clear_layout_widgets,
        populate_unscored_documents,
        update_literature_tab,
        update_citations_tab,
        update_counterfactual_tab,
    )
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False
    QApplication = None
    QWidget = None
    QVBoxLayout = None
    QHBoxLayout = None
    QLabel = None
    QFrame = None
    Qt = None
    UIConstants = None
    clear_layout_widgets = None
    populate_unscored_documents = None
    update_literature_tab = None
    update_citations_tab = None
    update_counterfactual_tab = None

pytestmark = pytest.mark.skipif(not QT_AVAILABLE, reason="Qt/PySide6 not available in this environment")


class MockCardFactory:
    """Mock card factory for testing."""

    def __init__(self):
        self.cards_created = []

    def create_card(self, card_data):
        """Create a mock card widget."""
        frame = QFrame()
        layout = QVBoxLayout(frame)
        label = QLabel(f"Mock Card: {card_data.title if hasattr(card_data, 'title') else 'Unknown'}")
        layout.addWidget(label)
        self.cards_created.append(card_data)
        return frame


class TestClearLayoutWidgets(unittest.TestCase):
    """Test cases for clear_layout_widgets function."""

    @classmethod
    def setUpClass(cls):
        """Set up QApplication for all tests."""
        if not QApplication.instance():
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()

    def setUp(self):
        """Set up test fixtures."""
        self.container = QWidget()
        self.layout = QVBoxLayout(self.container)

    def tearDown(self):
        """Clean up widgets."""
        self.container.deleteLater()

    def test_clears_all_widgets_from_layout(self):
        """Test that all widgets are removed from layout."""
        # Add widgets
        for i in range(5):
            self.layout.addWidget(QLabel(f"Label {i}"))

        self.assertEqual(self.layout.count(), 5)

        # Clear
        clear_layout_widgets(self.layout)

        self.assertEqual(self.layout.count(), 0)

    def test_handles_empty_layout(self):
        """Test that empty layout is handled gracefully."""
        self.assertEqual(self.layout.count(), 0)

        # Should not raise exception
        clear_layout_widgets(self.layout)

        self.assertEqual(self.layout.count(), 0)

    def test_handles_nested_layouts(self):
        """Test that nested layouts are cleared."""
        # Add nested layout with widgets
        nested_layout = QHBoxLayout()
        nested_layout.addWidget(QLabel("Nested 1"))
        nested_layout.addWidget(QLabel("Nested 2"))
        self.layout.addLayout(nested_layout)

        # Add regular widget
        self.layout.addWidget(QLabel("Regular"))

        initial_count = self.layout.count()
        self.assertGreater(initial_count, 0)

        # Clear
        clear_layout_widgets(self.layout)

        self.assertEqual(self.layout.count(), 0)

    def test_handles_stretch_items(self):
        """Test that stretch items are handled."""
        self.layout.addWidget(QLabel("Before stretch"))
        self.layout.addStretch()
        self.layout.addWidget(QLabel("After stretch"))

        self.assertEqual(self.layout.count(), 3)

        clear_layout_widgets(self.layout)

        self.assertEqual(self.layout.count(), 0)


class TestPopulateUnscoredDocuments(unittest.TestCase):
    """Test cases for populate_unscored_documents function."""

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
        self.container = QWidget()
        self.layout = QVBoxLayout(self.container)
        self.card_factory = MockCardFactory()
        self.logger = logging.getLogger('test')

    def tearDown(self):
        """Clean up widgets."""
        self.container.deleteLater()

    def test_returns_count_of_documents_added(self):
        """Test that function returns number of documents added."""
        documents = [
            {"doc_id": 1, "title": "Doc 1", "abstract": "Abstract 1"},
            {"doc_id": 2, "title": "Doc 2", "abstract": "Abstract 2"},
        ]

        count = populate_unscored_documents(
            self.layout, documents, self.card_factory, self.ui, self.logger
        )

        self.assertEqual(count, 2)

    def test_adds_widgets_to_layout(self):
        """Test that widgets are added to layout."""
        documents = [
            {"doc_id": 1, "title": "Doc 1", "abstract": "Abstract 1"},
        ]

        populate_unscored_documents(
            self.layout, documents, self.card_factory, self.ui, self.logger
        )

        self.assertGreater(self.layout.count(), 0)

    def test_handles_empty_document_list(self):
        """Test that empty list is handled."""
        count = populate_unscored_documents(
            self.layout, [], self.card_factory, self.ui, self.logger
        )

        self.assertEqual(count, 0)

    def test_creates_cards_for_each_document(self):
        """Test that card factory is called for each document."""
        documents = [
            {"doc_id": 1, "title": "Doc 1", "abstract": "Abstract 1"},
            {"doc_id": 2, "title": "Doc 2", "abstract": "Abstract 2"},
            {"doc_id": 3, "title": "Doc 3", "abstract": "Abstract 3"},
        ]

        populate_unscored_documents(
            self.layout, documents, self.card_factory, self.ui, self.logger
        )

        self.assertEqual(len(self.card_factory.cards_created), 3)


class TestUpdateLiteratureTab(unittest.TestCase):
    """Test cases for update_literature_tab function."""

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
        self.container = QWidget()
        self.layout = QVBoxLayout(self.container)
        self.card_factory = MockCardFactory()
        self.logger = logging.getLogger('test')

    def tearDown(self):
        """Clean up widgets."""
        self.container.deleteLater()

    def test_returns_count_of_documents(self):
        """Test that function returns document count."""
        scored_docs = [
            ({"doc_id": 1, "title": "Doc 1"}, {"score": 4.5, "reasoning": "Good"}),
            ({"doc_id": 2, "title": "Doc 2"}, {"score": 3.0, "reasoning": "OK"}),
        ]

        count = update_literature_tab(
            self.layout, scored_docs, self.card_factory, self.ui, self.logger
        )

        self.assertEqual(count, 2)

    def test_adds_widgets_for_scored_documents(self):
        """Test that widgets are added for scored documents."""
        scored_docs = [
            ({"doc_id": 1, "title": "Doc 1"}, {"score": 4.5, "reasoning": "Good"}),
        ]

        update_literature_tab(
            self.layout, scored_docs, self.card_factory, self.ui, self.logger
        )

        self.assertGreater(self.layout.count(), 0)

    def test_handles_empty_scored_list(self):
        """Test that empty scored list is handled."""
        count = update_literature_tab(
            self.layout, [], self.card_factory, self.ui, self.logger
        )

        self.assertEqual(count, 0)

    def test_clears_existing_content_first(self):
        """Test that existing content is cleared before adding new."""
        # Add initial content
        self.layout.addWidget(QLabel("Existing"))

        scored_docs = [
            ({"doc_id": 1, "title": "Doc 1"}, {"score": 4.5, "reasoning": "Good"}),
        ]

        update_literature_tab(
            self.layout, scored_docs, self.card_factory, self.ui, self.logger
        )

        # Should not contain "Existing" label anymore
        found_existing = False
        for i in range(self.layout.count()):
            item = self.layout.itemAt(i)
            if item.widget() and isinstance(item.widget(), QLabel):
                if "Existing" in item.widget().text():
                    found_existing = True

        self.assertFalse(found_existing)


class TestUpdateCitationsTab(unittest.TestCase):
    """Test cases for update_citations_tab function."""

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
        self.container = QWidget()
        self.layout = QVBoxLayout(self.container)
        self.logger = logging.getLogger('test')

    def tearDown(self):
        """Clean up widgets."""
        self.container.deleteLater()

    def test_returns_count_of_citations(self):
        """Test that function returns citation count."""
        citations = [
            {"citation_id": 1, "doc_id": 1, "title": "Paper 1", "passage": "Text 1"},
            {"citation_id": 2, "doc_id": 2, "title": "Paper 2", "passage": "Text 2"},
        ]

        count = update_citations_tab(
            self.layout, citations, self.ui, self.logger
        )

        self.assertEqual(count, 2)

    def test_adds_widgets_for_citations(self):
        """Test that widgets are added for citations."""
        citations = [
            {"citation_id": 1, "doc_id": 1, "title": "Paper 1", "passage": "Text 1", "reasoning": "Relevant"},
        ]

        update_citations_tab(self.layout, citations, self.ui, self.logger)

        self.assertGreater(self.layout.count(), 0)

    def test_handles_empty_citation_list(self):
        """Test that empty citation list shows empty state."""
        count = update_citations_tab(
            self.layout, [], self.ui, self.logger
        )

        self.assertEqual(count, 0)

    def test_handles_citations_with_missing_fields(self):
        """Test that citations with missing fields are handled."""
        citations = [
            {"citation_id": 1},  # Missing most fields
        ]

        # Should not raise exception
        count = update_citations_tab(
            self.layout, citations, self.ui, self.logger
        )

        self.assertIsInstance(count, int)


class TestUpdateCounterfactualTab(unittest.TestCase):
    """Test cases for update_counterfactual_tab function."""

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
        self.container = QWidget()
        self.layout = QVBoxLayout(self.container)
        self.summary_label = QLabel("Summary")
        self.card_factory = MockCardFactory()
        self.logger = logging.getLogger('test')

    def tearDown(self):
        """Clean up widgets."""
        self.container.deleteLater()
        self.summary_label.deleteLater()

    def test_updates_summary_label(self):
        """Test that summary label is updated."""
        results = {
            "questions": [
                {"question": "Q1", "priority": "HIGH", "rationale": "Test"},
            ],
            "summary": "Test summary",
        }

        update_counterfactual_tab(
            self.layout, self.summary_label, results,
            self.card_factory, self.ui, self.logger
        )

        # Summary label should be updated
        self.assertNotEqual(self.summary_label.text(), "Summary")

    def test_handles_empty_results(self):
        """Test that empty results are handled."""
        update_counterfactual_tab(
            self.layout, self.summary_label, {},
            self.card_factory, self.ui, self.logger
        )

        # Should not raise exception
        self.assertTrue(True)

    def test_handles_none_results(self):
        """Test that None results are handled."""
        update_counterfactual_tab(
            self.layout, self.summary_label, None,
            self.card_factory, self.ui, self.logger
        )

        # Should not raise exception
        self.assertTrue(True)

    def test_adds_question_cards(self):
        """Test that question cards are added."""
        results = {
            "questions": [
                {"question": "Q1", "priority": "HIGH", "rationale": "Test 1"},
                {"question": "Q2", "priority": "MEDIUM", "rationale": "Test 2"},
            ],
        }

        update_counterfactual_tab(
            self.layout, self.summary_label, results,
            self.card_factory, self.ui, self.logger
        )

        # Should have cards in layout
        self.assertGreater(self.layout.count(), 0)


class TestTabUpdatersEdgeCases(unittest.TestCase):
    """Edge case tests for tab updater functions."""

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
        self.container = QWidget()
        self.layout = QVBoxLayout(self.container)
        self.card_factory = MockCardFactory()
        self.logger = logging.getLogger('test')

    def tearDown(self):
        """Clean up widgets."""
        self.container.deleteLater()

    def test_handles_documents_with_unicode(self):
        """Test that documents with unicode are handled."""
        documents = [
            {"doc_id": 1, "title": "Unicode \u00e9\u00e0\u00fc", "abstract": "\u4e2d\u6587\u6587\u672c"},
        ]

        count = populate_unscored_documents(
            self.layout, documents, self.card_factory, self.ui, self.logger
        )

        self.assertEqual(count, 1)

    def test_handles_documents_with_very_long_text(self):
        """Test that documents with very long text are handled."""
        documents = [
            {"doc_id": 1, "title": "A" * 1000, "abstract": "B" * 10000},
        ]

        count = populate_unscored_documents(
            self.layout, documents, self.card_factory, self.ui, self.logger
        )

        self.assertEqual(count, 1)

    def test_handles_large_number_of_documents(self):
        """Test that large number of documents is handled."""
        documents = [
            {"doc_id": i, "title": f"Doc {i}", "abstract": f"Abstract {i}"}
            for i in range(100)
        ]

        count = populate_unscored_documents(
            self.layout, documents, self.card_factory, self.ui, self.logger
        )

        self.assertEqual(count, 100)

    def test_handles_citations_with_html_content(self):
        """Test that citations with HTML-like content are handled."""
        citations = [
            {
                "citation_id": 1,
                "doc_id": 1,
                "title": "<script>alert('xss')</script>",
                "passage": "Text with <b>bold</b> tags",
                "reasoning": "Test & reason"
            },
        ]

        # Should not raise exception and should handle safely
        count = update_citations_tab(
            self.layout, citations, self.ui, self.logger
        )

        self.assertEqual(count, 1)

    def test_handles_score_edge_values(self):
        """Test that edge score values are handled."""
        scored_docs = [
            ({"doc_id": 1, "title": "Min score"}, {"score": 0.0, "reasoning": "Min"}),
            ({"doc_id": 2, "title": "Max score"}, {"score": 5.0, "reasoning": "Max"}),
            ({"doc_id": 3, "title": "Negative score"}, {"score": -1.0, "reasoning": "Neg"}),
            ({"doc_id": 4, "title": "Above max"}, {"score": 10.0, "reasoning": "High"}),
        ]

        count = update_literature_tab(
            self.layout, scored_docs, self.card_factory, self.ui, self.logger
        )

        self.assertEqual(count, 4)


if __name__ == '__main__':
    unittest.main()
