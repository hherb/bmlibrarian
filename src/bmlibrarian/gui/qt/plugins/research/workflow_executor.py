"""
Qt-specific workflow executor for BMLibrarian research workflow.

Adapts the agent-based workflow to Qt's signal/slot architecture.
"""

from typing import Dict, Any, Optional
from PySide6.QtCore import QObject, Signal, QRunnable, Slot
import logging


class WorkflowSignals(QObject):
    """
    Signals for workflow execution progress and results.

    These signals allow background workflow execution to communicate
    with the main Qt GUI thread.
    """

    # Progress signals
    progress = Signal(int)  # Progress percentage (0-100)
    status = Signal(str)  # Status message
    step_started = Signal(str)  # Workflow step name
    step_completed = Signal(str)  # Workflow step name

    # Result signals
    workflow_completed = Signal(dict)  # Final results
    workflow_error = Signal(Exception)  # Error occurred

    # Step-specific data signals
    query_generated = Signal(str)  # SQL query generated
    documents_found = Signal(list)  # List of documents
    documents_scored = Signal(list)  # List of (doc, score) tuples
    citations_extracted = Signal(list)  # List of citations
    preliminary_report_generated = Signal(str)  # Markdown report
    counterfactual_analysis_complete = Signal(dict)  # Analysis results
    final_report_generated = Signal(str)  # Markdown report


class QtWorkflowExecutor(QObject):
    """
    Qt-specific workflow executor using real BMLibrarian agents.

    This class wraps the agent-based workflow to work with Qt's
    signal/slot architecture and threading model.

    Workflow Steps:
    1. COLLECT_RESEARCH_QUESTION - Already have from UI
    2. GENERATE_AND_EDIT_QUERY - QueryAgent
    3. SEARCH_DOCUMENTS - Execute query
    4. REVIEW_SEARCH_RESULTS - Display documents
    5. SCORE_DOCUMENTS - DocumentScoringAgent
    6. EXTRACT_CITATIONS - CitationFinderAgent
    7. GENERATE_REPORT - ReportingAgent
    8. PERFORM_COUNTERFACTUAL_ANALYSIS - CounterfactualAgent (optional)
    9. SEARCH_CONTRADICTORY_EVIDENCE - Query contradictory docs
    10. EDIT_COMPREHENSIVE_REPORT - EditorAgent
    11. EXPORT_REPORT - Save to file
    """

    # Signals
    workflow_started = Signal()
    workflow_completed = Signal(dict)
    workflow_error = Signal(Exception)
    status_message = Signal(str)

    def __init__(self, agents: Optional[Dict[str, Any]] = None, parent: Optional[QObject] = None):
        """
        Initialize Qt workflow executor.

        Args:
            agents: Dictionary of initialized BMLibrarian agents
            parent: Optional parent QObject
        """
        super().__init__(parent)

        self.logger = logging.getLogger("bmlibrarian.gui.qt.plugins.research.QtWorkflowExecutor")

        # Agent references
        self.agents = agents or {}
        self.query_agent = self.agents.get('query_agent')
        self.scoring_agent = self.agents.get('scoring_agent')
        self.citation_agent = self.agents.get('citation_agent')
        self.reporting_agent = self.agents.get('reporting_agent')
        self.counterfactual_agent = self.agents.get('counterfactual_agent')
        self.editor_agent = self.agents.get('editor_agent')
        self.orchestrator = self.agents.get('orchestrator')

        # Workflow state
        self.current_question: str = ""
        self.documents: list = []
        self.scored_documents: list = []
        self.citations: list = []
        self.preliminary_report: str = ""
        self.counterfactual_analysis: Optional[dict] = None
        self.final_report: str = ""

        # Workflow parameters
        self.max_results: int = 100
        self.min_relevant: int = 10
        self.interactive_mode: bool = False
        self.counterfactual_enabled: bool = True

        # Log agent status
        self._log_agent_status()

    def _log_agent_status(self) -> None:
        """Log which agents are available."""
        if not self.agents:
            self.logger.warning("No agents initialized!")
            return

        self.logger.info("Agent status:")
        agent_names = [
            'query_agent', 'scoring_agent', 'citation_agent',
            'reporting_agent', 'counterfactual_agent', 'editor_agent', 'orchestrator'
        ]

        for name in agent_names:
            agent = self.agents.get(name)
            if agent:
                model = getattr(agent, 'model', 'N/A')
                self.logger.info(f"  ✓ {name}: {model}")
            else:
                self.logger.warning(f"  ✗ {name}: NOT INITIALIZED")

    def check_agents_ready(self) -> bool:
        """
        Check if all required agents are initialized.

        Returns:
            True if agents are ready, False otherwise
        """
        required_agents = [
            'query_agent', 'scoring_agent', 'citation_agent',
            'reporting_agent', 'editor_agent'
        ]

        for agent_name in required_agents:
            if not self.agents.get(agent_name):
                self.logger.error(f"Required agent '{agent_name}' not initialized")
                return False

        return True

    def start_workflow(
        self,
        question: str,
        max_results: int = 100,
        min_relevant: int = 10,
        interactive: bool = False,
        counterfactual: bool = True
    ) -> None:
        """
        Start the research workflow (Phase 2: just validate, don't execute).

        Args:
            question: Research question
            max_results: Maximum documents to retrieve
            min_relevant: Minimum relevant documents to find
            interactive: Enable interactive mode
            counterfactual: Enable counterfactual analysis
        """
        try:
            # Validate agents
            if not self.check_agents_ready():
                error = RuntimeError("Agents not properly initialized")
                self.workflow_error.emit(error)
                return

            # Store parameters
            self.current_question = question
            self.max_results = max_results
            self.min_relevant = min_relevant
            self.interactive_mode = interactive
            self.counterfactual_enabled = counterfactual

            # Log workflow start
            self.logger.info(f"Workflow started: {question[:100]}")
            self.logger.debug(
                f"Parameters: max_results={max_results}, min_relevant={min_relevant}, "
                f"interactive={interactive}, counterfactual={counterfactual}"
            )

            # Emit started signal
            self.workflow_started.emit()

            # Phase 2: Just confirm agents are working
            # Don't actually run the workflow yet (that's Phase 3)
            self._test_agent_connection()

        except Exception as e:
            self.logger.error(f"Error starting workflow: {e}", exc_info=True)
            self.workflow_error.emit(e)

    def _test_agent_connection(self) -> None:
        """
        Test that agents can be called (Phase 2 only).

        This is a lightweight test to confirm agents are initialized
        and can respond to method calls.
        """
        try:
            self.status_message.emit("Testing agent connections...")

            # Test QueryAgent
            if self.query_agent:
                # Just check the agent has required methods
                assert hasattr(self.query_agent, 'generate_query'), "QueryAgent missing generate_query method"
                self.status_message.emit("✓ QueryAgent ready")
            else:
                raise RuntimeError("QueryAgent not initialized")

            # Test ScoringAgent
            if self.scoring_agent:
                assert hasattr(self.scoring_agent, 'evaluate_document'), "ScoringAgent missing evaluate_document method"
                self.status_message.emit("✓ ScoringAgent ready")
            else:
                raise RuntimeError("ScoringAgent not initialized")

            # Test CitationAgent
            if self.citation_agent:
                assert hasattr(self.citation_agent, 'process_scored_documents_for_citations'), \
                    "CitationAgent missing citation method"
                self.status_message.emit("✓ CitationAgent ready")
            else:
                raise RuntimeError("CitationAgent not initialized")

            # Test ReportingAgent
            if self.reporting_agent:
                assert hasattr(self.reporting_agent, 'generate_citation_based_report'), \
                    "ReportingAgent missing report method"
                self.status_message.emit("✓ ReportingAgent ready")
            else:
                raise RuntimeError("ReportingAgent not initialized")

            # Test EditorAgent
            if self.editor_agent:
                assert hasattr(self.editor_agent, 'edit_comprehensive_report'), \
                    "EditorAgent missing edit method"
                self.status_message.emit("✓ EditorAgent ready")
            else:
                raise RuntimeError("EditorAgent not initialized")

            # Test CounterfactualAgent (optional)
            if self.counterfactual_enabled:
                if self.counterfactual_agent:
                    assert hasattr(self.counterfactual_agent, 'generate_counterfactual_questions'), \
                        "CounterfactualAgent missing counterfactual method"
                    self.status_message.emit("✓ CounterfactualAgent ready")
                else:
                    self.logger.warning("CounterfactualAgent not initialized (optional)")

            # All agents passed
            self.status_message.emit("✅ All agents connected and ready!")

            # Emit success (Phase 2: no actual results yet)
            self.workflow_completed.emit({
                'phase': 2,
                'status': 'agents_connected',
                'question': self.current_question,
                'agents_ready': True
            })

        except Exception as e:
            self.logger.error(f"Agent connection test failed: {e}", exc_info=True)
            self.workflow_error.emit(e)

    # ========================================================================
    # Phase 3+ Methods (to be implemented later)
    # ========================================================================

    def execute_workflow(self) -> None:
        """Execute the full workflow in a background thread (Phase 3)."""
        # TODO Phase 3: Implement full workflow execution
        pass

    def generate_query(self) -> None:
        """Generate SQL query from research question (Phase 3)."""
        # TODO Phase 3: Call query_agent.generate_query()
        pass

    def search_documents(self, query: str) -> None:
        """Execute database search (Phase 3)."""
        # TODO Phase 3: Execute SQL query against database
        pass

    def score_documents(self, documents: list) -> None:
        """Score documents for relevance (Phase 3)."""
        # TODO Phase 3: Call scoring_agent.evaluate_document() for each doc
        pass

    def extract_citations(self, scored_documents: list) -> None:
        """Extract citations from high-scoring documents (Phase 3)."""
        # TODO Phase 3: Call citation_agent.process_scored_documents_for_citations()
        pass

    def generate_preliminary_report(self, citations: list) -> None:
        """Generate preliminary report (Phase 3)."""
        # TODO Phase 3: Call reporting_agent.generate_citation_based_report()
        pass

    def perform_counterfactual_analysis(self, report: str) -> None:
        """Perform counterfactual analysis (Phase 3)."""
        # TODO Phase 3: Call counterfactual_agent.generate_counterfactual_questions()
        pass

    def generate_final_report(self, preliminary: str, counterfactual: Optional[dict]) -> None:
        """Generate final comprehensive report (Phase 3)."""
        # TODO Phase 3: Call editor_agent.edit_comprehensive_report()
        pass
