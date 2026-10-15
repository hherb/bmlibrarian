"""Regression test: research-tab step handlers must be wired exactly once.

WorkflowThread drives the QtWorkflowExecutor and re-emits each step's result
itself, while some executor helpers it calls (generate_query, search_documents)
emit the same step signals. Connecting both sources ran every step handler
twice per search (July 2026 review, P1).
"""

from unittest.mock import MagicMock

import pytest

try:
    from PySide6.QtCore import SIGNAL
    from PySide6.QtWidgets import QApplication
    HAS_QT = True
except ImportError:  # pragma: no cover - Qt missing
    HAS_QT = False

# Executor step-data signals that WorkflowThread also emits
DUPLICATED_STEP_SIGNALS = (
    "query_generated(QString)",
    "documents_found(QVariantList)",
    "documents_scored(QVariantList)",
    "citations_extracted(QVariantList)",
    "preliminary_report_generated(QString)",
    "scoring_progress(int,int)",
)


@pytest.fixture
def app():
    """Provide a QApplication instance."""
    return QApplication.instance() or QApplication([])


@pytest.mark.skipif(not HAS_QT, reason="Qt not available")
def test_executor_step_signals_not_connected_to_tab(app):
    """The tab listens to step results from WorkflowThread only."""
    from bmlibrarian.gui.qt.plugins.research.research_tab import ResearchTabWidget

    widget = ResearchTabWidget(agents={'query_agent': MagicMock()})
    try:
        executor = widget.workflow_executor
        assert executor is not None
        for signature in DUPLICATED_STEP_SIGNALS:
            # A renamed signal would make the receiver count vacuously 0
            assert hasattr(executor, signature.split("(")[0]), signature
            assert executor.receivers(SIGNAL(signature)) == 0, signature
        # Executor-level lifecycle signals remain connected
        assert executor.receivers(SIGNAL("status_message(QString)")) == 1
    finally:
        widget.deleteLater()
