"""
Paper Weight Laboratory - Assessment Worker Thread

Background worker thread for paper weight assessment to keep GUI responsive.
"""

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QThread, Signal

from bmlibrarian.agents.paper_weight import ALL_DIMENSIONS
from .constants import PROGRESS_ANALYZING

if TYPE_CHECKING:
    from bmlibrarian.agents.paper_weight import PaperWeightAssessmentAgent
    from bmlibrarian.agents.paper_weight import PaperWeightResult


logger = logging.getLogger(__name__)


class AssessmentWorker(QThread):
    """
    Background worker thread for paper weight assessment.

    Runs assessment in a separate thread to keep GUI responsive during
    LLM calls which can take several seconds.

    Signals:
        progress_update: Emitted when a dimension assessment starts (dimension_name, status)
        assessment_complete: Emitted with PaperWeightResult when done
        assessment_error: Emitted with error message on failure
    """

    # Signals for thread-safe GUI updates
    progress_update = Signal(str, str)  # (dimension_name, status)
    assessment_complete = Signal(object)  # PaperWeightResult
    assessment_error = Signal(str)  # error_message

    def __init__(
        self,
        agent: "PaperWeightAssessmentAgent",
        document_id: int,
        force_reassess: bool = False
    ):
        """
        Initialize assessment worker.

        Args:
            agent: PaperWeightAssessmentAgent instance
            document_id: Database ID of document to assess
            force_reassess: If True, skip cache and re-assess
        """
        super().__init__()
        self.agent = agent
        self.document_id = document_id
        self.force_reassess = force_reassess

    def run(self) -> None:
        """Run assessment in background thread."""
        try:
            # Emit progress for each dimension as we start
            for dim in ALL_DIMENSIONS:
                self.progress_update.emit(dim, PROGRESS_ANALYZING)

            # Perform assessment
            result = self.agent.assess_paper(
                self.document_id,
                force_reassess=self.force_reassess
            )

            # Emit completion signal
            self.assessment_complete.emit(result)

        except Exception as e:
            logger.error(f"Assessment worker error: {e}")
            self.assessment_error.emit(str(e))


__all__ = ['AssessmentWorker']
