"""
Worker thread for PRISMA 2020 assessment.

Executes PRISMA 2020 compliance assessment in a background thread
to prevent UI blocking during long-running LLM operations.

Supports enhanced assessment with semantic search:
1. Checks if document has full-text embeddings
2. Creates embeddings if needed and full-text is available
3. Uses two-pass assessment with semantic search for low-scoring items
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

    This worker implements an enhanced assessment workflow:
    1. Check document text status (abstract, full-text, embeddings)
    2. If full-text exists but no embeddings, create them
    3. Run two-pass PRISMA assessment with semantic search for unclear items

    Signals:
        result_ready: Emitted when assessment completes successfully
        error_occurred: Emitted when assessment fails with error message
        status_update: Emitted with progress messages during processing
    """

    result_ready = Signal(object)  # PRISMA2020Assessment object
    error_occurred = Signal(str)
    status_update = Signal(str)  # Progress messages

    def __init__(
        self,
        prisma_agent: PRISMA2020Agent,
        document: Dict[str, Any],
        use_semantic_search: bool = True
    ):
        """
        Initialize worker thread.

        Args:
            prisma_agent: PRISMA2020Agent instance to use for assessment
            document: Document dictionary with at least 'id', 'title', 'abstract' fields
            use_semantic_search: If True, use enhanced assessment with semantic search
        """
        super().__init__()
        self.prisma_agent = prisma_agent
        self.document = document
        self.use_semantic_search = use_semantic_search

    def run(self) -> None:
        """
        Execute PRISMA 2020 assessment in background thread.

        Workflow:
        1. Check document text status
        2. Embed full-text if available but not yet embedded
        3. Run assessment (enhanced with semantic search if available)

        Emits result_ready signal on success or error_occurred on failure.
        """
        doc_id = self.document.get('id')
        logger.info(f"Starting PRISMA 2020 assessment for document {doc_id}")

        try:
            # Step 1: Check document status (only if we have a valid document ID)
            status = None
            if doc_id is not None and isinstance(doc_id, int):
                self.status_update.emit("Checking document status...")
                status = self.prisma_agent.get_document_text_status(doc_id)
            else:
                logger.warning(f"Invalid document ID: {doc_id}, skipping status check")

            if status:
                logger.info(
                    f"Document {doc_id} status: "
                    f"abstract={status.has_abstract} ({status.abstract_length} chars), "
                    f"fulltext={status.has_fulltext} ({status.fulltext_length} chars), "
                    f"chunks={status.has_fulltext_chunks}"
                )

                # Step 2: Embed if needed
                if self.use_semantic_search and status.has_fulltext and not status.has_fulltext_chunks:
                    self.status_update.emit("Creating full-text embeddings...")
                    logger.info(f"Embedding full-text for document {doc_id}")

                    embedding_success = self.prisma_agent.ensure_document_embedded(doc_id)
                    if embedding_success:
                        self.status_update.emit("Embeddings created successfully")
                        logger.info(f"Successfully embedded document {doc_id}")
                    else:
                        self.status_update.emit("Embedding failed, continuing with basic assessment")
                        logger.warning(f"Failed to embed document {doc_id}")

            # Step 3: Run assessment
            if self.use_semantic_search:
                self.status_update.emit("Running enhanced PRISMA assessment...")
                assessment = self.prisma_agent.assess_prisma_compliance_with_semantic_search(
                    document=self.document,
                    min_confidence=MIN_CONFIDENCE_LAB_MODE,
                    re_assess_low_scores=True
                )
            else:
                self.status_update.emit("Running PRISMA assessment...")
                assessment = self.prisma_agent.assess_prisma_compliance(
                    document=self.document,
                    min_confidence=MIN_CONFIDENCE_LAB_MODE
                )

            if assessment:
                enhanced_note = " (enhanced)" if "[Enhanced" in assessment.suitability_rationale else ""
                logger.info(
                    f"PRISMA 2020 assessment{enhanced_note} completed for document {doc_id} - "
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
