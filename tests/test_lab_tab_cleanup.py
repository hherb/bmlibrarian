"""Lab tabs stop their orchestrator on cleanup (#331).

They used to call ``AgentOrchestrator.shutdown()``, which does not exist; the
AttributeError was caught and printed, so the orchestrator was never stopped.
"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from bmlibrarian.agents import AgentOrchestrator
from bmlibrarian.gui.qt.plugins.pico_lab.pico_lab_tab import PICOLabTabWidget
from bmlibrarian.gui.qt.plugins.prisma2020_lab.prisma2020_lab_tab import (
    PRISMA2020LabTabWidget,
)
from bmlibrarian.gui.qt.plugins.study_assessment.study_assessment_tab import (
    StudyAssessmentTabWidget,
)


@pytest.mark.parametrize(
    "tab_class",
    [PICOLabTabWidget, StudyAssessmentTabWidget, PRISMA2020LabTabWidget],
)
def test_cleanup_stops_orchestrator(tab_class: type) -> None:
    """cleanup() calls a method the real orchestrator has."""
    orchestrator = Mock(spec=AgentOrchestrator)
    tab = SimpleNamespace(worker=None, orchestrator=orchestrator)

    tab_class.cleanup(tab)

    orchestrator.stop_processing.assert_called_once()
