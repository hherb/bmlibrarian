"""
Paper Weight Lab GUI: database errors are reported, not shown as "no results" (#275).

QMessageBox is patched in every test: a real modal dialog would block the
Qt test suite.
"""

from typing import TYPE_CHECKING, Optional
from unittest.mock import patch

import pytest

try:
    from PySide6.QtWidgets import QApplication
    HAS_QT = True
except ImportError:  # pragma: no cover - Qt missing
    HAS_QT = False

if TYPE_CHECKING:
    from bmlibrarian.lab.paper_weight_lab.tabs.search_tab import SearchTab

pytestmark = pytest.mark.skipif(not HAS_QT, reason="Qt not available")

PKG = 'bmlibrarian.lab.paper_weight_lab'
DB_ERROR = Exception('Database connection failed')


@pytest.fixture
def app() -> "QApplication":
    """Provide a QApplication instance."""
    return QApplication.instance() or QApplication([])


@pytest.fixture
def search_tab(app: "QApplication") -> "SearchTab":
    """A SearchTab built with an empty recent-assessments list."""
    from bmlibrarian.lab.paper_weight_lab.tabs.search_tab import SearchTab
    with patch(f'{PKG}.tabs.search_tab.get_recent_assessments', return_value=[]):
        return SearchTab()


def test_recent_assessments_error_marks_combo_without_dialog(app: "QApplication") -> None:
    """A failure while building the tab marks the combo instead of opening a modal."""
    from bmlibrarian.lab.paper_weight_lab.tabs.search_tab import SearchTab
    with patch(f'{PKG}.tabs.search_tab.get_recent_assessments', side_effect=DB_ERROR), \
         patch(f'{PKG}.tabs.search_tab.QMessageBox') as box:
        tab = SearchTab()

    assert 'Could not load recent assessments' in tab.recent_combo.itemText(0)
    assert tab.recent_combo.count() == 1
    assert tab.recent_combo.currentData() is None
    assert not box.method_calls


@pytest.mark.parametrize('search_type, func', [
    ('keyword', 'search_documents'),
    ('semantic', 'semantic_search_documents'),
])
def test_search_tab_error_shows_failure_not_no_results(
    search_tab: "SearchTab", search_type: str, func: str
) -> None:
    """A failed search says so, rather than "No Results"."""
    search_tab.search_type_combo.setCurrentIndex(search_tab.search_type_combo.findData(search_type))
    search_tab.search_input.setText('aspirin')
    with patch(f'{PKG}.tabs.search_tab.{func}', side_effect=DB_ERROR), \
         patch(f'{PKG}.tabs.search_tab.QMessageBox') as box:
        search_tab._do_search()

    box.critical.assert_called_once()
    assert 'Database connection failed' in box.critical.call_args.args[2]
    box.information.assert_not_called()
    assert search_tab.search_results == []
    assert search_tab.results_tree.topLevelItemCount() == 0


def test_search_dialog_error_shows_failure(app: "QApplication") -> None:
    """The document search dialog reports a failed search."""
    from bmlibrarian.lab.paper_weight_lab.dialogs import DocumentSearchDialog
    dialog = DocumentSearchDialog()
    dialog.search_input.setText('aspirin')
    with patch(f'{PKG}.dialogs.search_documents', side_effect=DB_ERROR), \
         patch(f'{PKG}.dialogs.semantic_search_documents', side_effect=DB_ERROR), \
         patch(f'{PKG}.dialogs.QMessageBox') as box:
        dialog._do_search()

    box.critical.assert_called_once()
    box.information.assert_not_called()


@pytest.mark.parametrize('side_effect, return_value, dialog', [
    (DB_ERROR, None, 'critical'),
    (None, None, 'warning'),
], ids=['load_error', 'not_found'])
def test_failed_load_does_not_keep_previous_document(
    app: "QApplication",
    side_effect: Optional[Exception],
    return_value: Optional[dict],
    dialog: str,
) -> None:
    """After a failed load, Assess must not act on the previously loaded paper."""
    from bmlibrarian.lab.paper_weight_lab.tabs.results_tab import ResultsTab
    tab = ResultsTab(agent=None)
    previous = {'title': 'Old paper', 'authors': None, 'year': 2020,
                'pmid': None, 'doi': None, 'abstract': 'old'}
    with patch(f'{PKG}.tabs.results_tab.get_document_metadata', return_value=previous):
        tab.load_document(1)
    assert tab.current_document_id == 1

    with patch(f'{PKG}.tabs.results_tab.get_document_metadata',
               side_effect=side_effect, return_value=return_value), \
         patch(f'{PKG}.tabs.results_tab.QMessageBox') as box:
        tab.load_document(2)

    getattr(box, dialog).assert_called_once()
    assert tab.current_document_id is None
    assert tab.current_document_meta is None
