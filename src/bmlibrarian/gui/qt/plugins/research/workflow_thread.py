"""
Background workflow execution thread for Qt GUI.

Provides threaded workflow execution with cancellation support and detailed progress updates.
"""

from typing import Dict, Any, Optional, List, Tuple
from PySide6.QtCore import QThread, Signal
import logging


class WorkflowThread(QThread):
    """
    Background thread for executing BMLibrarian research workflow.

    This thread runs the complete workflow (query generation, document search,
    scoring, citation extraction, reporting, and optional counterfactual analysis)
    in the background without blocking the Qt GUI.

    Features:
    - Cancellable execution (check _should_cancel flag periodically)
    - Detailed progress signals for each workflow step
    - Error handling with signal emission
    - Clean thread lifecycle management
    """

    # Progress signals
    step_started = Signal(str, str)  # (step_name, step_description)
    step_progress = Signal(str, int, int)  # (step_name, current, total)
    step_completed = Signal(str)  # step_name
    status_message = Signal(str)  # status text

    # Result signals
    query_generated = Signal(str)  # SQL query
    documents_found = Signal(list)  # List of documents
    documents_scored = Signal(list)  # List of (doc, score) tuples
    citations_extracted = Signal(list)  # List of citations
    preliminary_report_generated = Signal(str)  # Markdown report
    counterfactual_analysis_complete = Signal(dict)  # Analysis results
    final_report_generated = Signal(str)  # Markdown report

    # Completion signals
    workflow_completed = Signal(dict)  # Final results dictionary
    workflow_error = Signal(Exception)  # Error occurred
    workflow_cancelled = Signal()  # Workflow was cancelled

    def __init__(
        self,
        executor: 'QtWorkflowExecutor',
        question: str,
        max_results: int = 100,
        score_threshold: float = 3.0,
        enable_counterfactual: bool = False,
        parent: Optional[QThread] = None
    ):
        """
        Initialize workflow thread.

        Args:
            executor: The QtWorkflowExecutor with configured agents
            question: Research question to answer
            max_results: Maximum number of documents to retrieve
            score_threshold: Minimum relevance score for citation extraction
            enable_counterfactual: Whether to run counterfactual analysis
            parent: Optional parent QObject
        """
        super().__init__(parent)

        self.logger = logging.getLogger("bmlibrarian.gui.qt.WorkflowThread")

        # Store executor reference (contains all agents)
        self.executor = executor

        # Workflow parameters
        self.question = question
        self.max_results = max_results
        self.score_threshold = score_threshold
        self.enable_counterfactual = enable_counterfactual

        # Cancellation flag (checked periodically during execution)
        self._should_cancel = False

        # Workflow results (accumulated during execution)
        self.query: str = ""
        self.documents: List[Dict[str, Any]] = []
        self.scored_documents: List[Tuple[Dict, Dict]] = []
        self.citations: List[Dict[str, Any]] = []
        self.preliminary_report: str = ""
        self.counterfactual_results: Optional[Dict[str, Any]] = None
        self.final_report: str = ""

    def cancel(self) -> None:
        """
        Request workflow cancellation.

        Sets the cancellation flag. The workflow will check this flag
        between steps and exit gracefully.
        """
        self.logger.info("Workflow cancellation requested")
        self._should_cancel = True
        self.status_message.emit("🛑 Cancelling workflow...")

    def _check_cancellation(self, step_name: str) -> bool:
        """
        Check if workflow should be cancelled.

        Args:
            step_name: Current workflow step (for logging)

        Returns:
            True if should cancel, False otherwise
        """
        if self._should_cancel:
            self.logger.info(f"Workflow cancelled during step: {step_name}")
            self.workflow_cancelled.emit()
            return True
        return False

    def run(self) -> None:
        """
        Execute the complete workflow in background thread.

        This is the main thread execution method. It orchestrates all
        workflow steps and emits progress signals along the way.

        Workflow Steps:
        1. Generate database query from question
        2. Search for relevant documents
        3. Score documents for relevance
        4. Extract citations from high-scoring documents
        5. Generate preliminary report
        6. [Optional] Perform counterfactual analysis
        7. [Optional] Search for contradictory evidence
        8. [Optional] Generate comprehensive final report
        """
        try:
            self.logger.info(f"Workflow thread started: {self.question[:100]}")

            # ==================================================================
            # Step 1: Generate Query
            # ==================================================================
            step_name = "generate_query"
            self.step_started.emit(step_name, "Generating database query from your question")
            self.status_message.emit("🔍 Generating database query...")

            if self._check_cancellation(step_name):
                return

            self.query = self.executor.generate_query()
            self.query_generated.emit(self.query)
            self.step_completed.emit(step_name)

            if not self.query or not self.query.strip():
                raise ValueError("Query generation failed - no query returned")

            # ==================================================================
            # Step 2: Search Documents
            # ==================================================================
            step_name = "search_documents"
            self.step_started.emit(step_name, f"Searching database with query: {self.query[:50]}...")
            self.status_message.emit(f"📚 Searching database...")

            if self._check_cancellation(step_name):
                return

            self.documents = self.executor.search_documents(self.query)
            self.documents_found.emit(self.documents)
            self.step_completed.emit(step_name)

            if not self.documents:
                self.status_message.emit("⚠️ No documents found")
                self._emit_completion_no_documents()
                return

            self.status_message.emit(f"✓ Found {len(self.documents)} documents")

            # ==================================================================
            # Step 3: Score Documents
            # ==================================================================
            step_name = "score_documents"
            self.step_started.emit(step_name, f"Scoring {len(self.documents)} documents for relevance")
            self.status_message.emit(f"📊 Scoring {len(self.documents)} documents...")

            if self._check_cancellation(step_name):
                return

            self.scored_documents = []
            total = len(self.documents)

            for i, doc in enumerate(self.documents, 1):
                if self._check_cancellation(step_name):
                    return

                # Emit progress
                self.step_progress.emit(step_name, i, total)

                # Score document
                score_result = self.executor.scoring_agent.evaluate_document(
                    self.question, doc
                )

                if score_result:
                    self.scored_documents.append((doc, score_result))

            self.documents_scored.emit(self.scored_documents)
            self.step_completed.emit(step_name)

            if not self.scored_documents:
                self.status_message.emit("⚠️ No documents could be scored")
                self._emit_completion_no_scores()
                return

            high_scoring_count = len([
                (d, s) for d, s in self.scored_documents
                if isinstance(s.get('score'), (int, float)) and s.get('score', 0) >= self.score_threshold
            ])
            self.status_message.emit(
                f"✓ Scored {len(self.scored_documents)} documents "
                f"({high_scoring_count} above threshold {self.score_threshold})"
            )

            # ==================================================================
            # Step 4: Extract Citations
            # ==================================================================
            step_name = "extract_citations"
            self.step_started.emit(step_name, f"Extracting citations from {high_scoring_count} high-scoring documents")
            self.status_message.emit(f"💬 Extracting citations...")

            if self._check_cancellation(step_name):
                return

            self.citations = self.executor.extract_citations(
                self.scored_documents,
                score_threshold=self.score_threshold
            )
            self.citations_extracted.emit(self.citations)
            self.step_completed.emit(step_name)

            if not self.citations:
                self.status_message.emit("⚠️ No citations could be extracted")
                self._emit_completion_no_citations()
                return

            self.status_message.emit(f"✓ Extracted {len(self.citations)} citations")

            # ==================================================================
            # Step 5: Generate Preliminary Report
            # ==================================================================
            step_name = "generate_preliminary_report"
            self.step_started.emit(step_name, f"Generating preliminary report from {len(self.citations)} citations")
            self.status_message.emit(f"📄 Generating preliminary report...")

            if self._check_cancellation(step_name):
                return

            self.preliminary_report = self.executor.generate_preliminary_report(self.citations)
            self.preliminary_report_generated.emit(self.preliminary_report)
            self.step_completed.emit(step_name)

            report_word_count = len(self.preliminary_report.split())
            self.status_message.emit(f"✓ Generated preliminary report ({report_word_count} words)")

            # ==================================================================
            # Step 6: Counterfactual Analysis (Optional)
            # ==================================================================
            if self.enable_counterfactual and self.executor.counterfactual_agent:
                step_name = "counterfactual_analysis"
                self.step_started.emit(step_name, "Performing counterfactual analysis")
                self.status_message.emit(f"🔄 Analyzing for contradictory evidence...")

                if self._check_cancellation(step_name):
                    return

                # TODO: Implement counterfactual analysis
                # This will be added after basic threading is working
                self.counterfactual_results = {
                    'status': 'not_implemented',
                    'message': 'Counterfactual analysis coming in later milestone'
                }
                self.counterfactual_analysis_complete.emit(self.counterfactual_results)
                self.step_completed.emit(step_name)

            # ==================================================================
            # Final: Emit Completion
            # ==================================================================
            self.status_message.emit(
                f"✅ Workflow complete! {len(self.citations)} citations, "
                f"{report_word_count} word report"
            )

            results = {
                'milestone': 4,
                'status': 'completed',
                'question': self.question,
                'query': self.query,
                'documents': self.documents,
                'scored_documents': self.scored_documents,
                'citations': self.citations,
                'preliminary_report': self.preliminary_report,
                'counterfactual_results': self.counterfactual_results,
                'final_report': self.final_report,
                'document_count': len(self.documents),
                'high_scoring_count': high_scoring_count,
                'citation_count': len(self.citations),
                'report_length': len(self.preliminary_report)
            }

            self.workflow_completed.emit(results)

        except Exception as e:
            self.logger.error(f"Workflow execution failed: {e}", exc_info=True)
            self.status_message.emit(f"❌ Error: {str(e)}")
            self.workflow_error.emit(e)

    def _emit_completion_no_documents(self) -> None:
        """Emit completion signal when no documents are found."""
        results = {
            'milestone': 4,
            'status': 'no_documents',
            'question': self.question,
            'query': self.query,
            'documents': [],
            'scored_documents': [],
            'citations': [],
            'preliminary_report': '',
            'counterfactual_results': None,
            'final_report': '',
            'document_count': 0
        }
        self.workflow_completed.emit(results)

    def _emit_completion_no_scores(self) -> None:
        """Emit completion signal when documents can't be scored."""
        results = {
            'milestone': 4,
            'status': 'no_scores',
            'question': self.question,
            'query': self.query,
            'documents': self.documents,
            'scored_documents': [],
            'citations': [],
            'preliminary_report': '',
            'counterfactual_results': None,
            'final_report': '',
            'document_count': len(self.documents)
        }
        self.workflow_completed.emit(results)

    def _emit_completion_no_citations(self) -> None:
        """Emit completion signal when no citations can be extracted."""
        high_scoring_count = len([
            (d, s) for d, s in self.scored_documents
            if isinstance(s.get('score'), (int, float)) and s.get('score', 0) >= self.score_threshold
        ])

        results = {
            'milestone': 4,
            'status': 'no_citations',
            'question': self.question,
            'query': self.query,
            'documents': self.documents,
            'scored_documents': self.scored_documents,
            'citations': [],
            'preliminary_report': '',
            'counterfactual_results': None,
            'final_report': '',
            'document_count': len(self.documents),
            'high_scoring_count': high_scoring_count
        }
        self.workflow_completed.emit(results)
