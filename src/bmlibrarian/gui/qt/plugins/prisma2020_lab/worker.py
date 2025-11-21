"""
Worker thread for PRISMA 2020 assessment.

Executes PRISMA 2020 compliance assessment in a background thread
to prevent UI blocking during long-running LLM operations.
"""

import logging
from typing import Any, Dict

from PySide6.QtCore import QThread, Signal

from bmlibrarian.agents import PRISMA2020Agent
from bmlibrarian.agents.prisma2020_agent import PRISMA2020Assessment
from .constants import MIN_CONFIDENCE_LAB_MODE

logger = logging.getLogger(__name__)


class PRISMA2020AssessmentWorker(QThread):
    """
    Worker thread for PRISMA 2020 assessment to prevent UI blocking.

    Signals:
        result_ready: Emitted when assessment completes successfully
        error_occurred: Emitted when assessment fails with error message
    """

    result_ready = Signal(object)  # PRISMA2020Assessment object
    error_occurred = Signal(str)

    def __init__(self, prisma_agent: PRISMA2020Agent, document: Dict[str, Any]):
        """
        Initialize worker thread.

        Args:
            prisma_agent: PRISMA2020Agent instance to use for assessment
            document: Document dictionary with at least 'id', 'title', 'abstract' fields
        """
        super().__init__()
        self.prisma_agent = prisma_agent
        self.document = document

    def run(self) -> None:
        """
        Execute PRISMA 2020 assessment in background thread.

        Emits result_ready signal on success or error_occurred on failure.
        """
        doc_id = self.document.get('id', 'unknown')
        logger.info(f"Starting PRISMA 2020 assessment for document {doc_id}")

        try:
            assessment = self.prisma_agent.assess_prisma_compliance(
                document=self.document,
                min_confidence=MIN_CONFIDENCE_LAB_MODE  # Show all assessments in lab mode
            )
            if assessment:
                logger.info(
                    f"PRISMA 2020 assessment completed for document {doc_id} - "
                    f"{assessment.overall_compliance_percentage:.1f}% compliance"
                )
                self.result_ready.emit(assessment)
            else:
                logger.warning(
                    f"PRISMA 2020 assessment returned no results for document {doc_id}"
                )
                self.error_occurred.emit(
                    "PRISMA 2020 assessment returned no results "
                    "(document may not be a systematic review)"
                )
        except Exception as e:
            logger.error(
                f"PRISMA 2020 assessment failed for document {doc_id}: {e}",
                exc_info=True
            )
            self.error_occurred.emit(str(e))
