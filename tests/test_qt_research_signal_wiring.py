"""Research-tab signal wiring: step results reach the tab from WorkflowThread.

(The executor used to emit the same step signals as the thread, and
connecting both ran every handler twice — July 2026 review, P1. The executor
no longer has signals at all, #332.)
"""

from unittest.mock import MagicMock

import pytest

# The settings/configuration tabs list Ollama models when built.
pytestmark = pytest.mark.usefixtures("offline_model_list")

try:
    from PySide6.QtWidgets import QApplication
    HAS_QT = True
except ImportError:  # pragma: no cover - Qt missing
    HAS_QT = False


@pytest.fixture
def app():
    """Provide a QApplication instance."""
    return QApplication.instance() or QApplication([])


@pytest.mark.skipif(not HAS_QT, reason="Qt not available")
def test_citation_summary_reaches_citations_tab(app):
    """The thread's extraction summary replaces the plain count in the Citations tab (#292)."""
    from bmlibrarian.gui.qt.plugins.research.research_tab import ResearchTabWidget
    from bmlibrarian.gui.qt.plugins.research.workflow_thread import WorkflowThread

    widget = ResearchTabWidget(agents={'query_agent': MagicMock()})
    thread = WorkflowThread(executor=MagicMock(), question="q")
    try:
        widget.workflow_thread = thread
        widget._connect_workflow_thread_signals()
        thread.citations_extracted.emit([])
        thread.citation_summary.emit("Extracted 0 citations from 1 documents (1 rejected: x ×1)")
        assert widget.citations_refs.widgets['summary_label'].text() == (
            "Extracted 0 citations from 1 documents (1 rejected: x ×1)"
        )
    finally:
        widget.workflow_thread = None
        thread.deleteLater()
        widget.deleteLater()
