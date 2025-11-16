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

    # Step-specific signals for UI updates
    query_generated = Signal(str)  # Emitted when query is generated
    documents_found = Signal(list)  # Emitted when documents are retrieved
    scoring_progress = Signal(int, int)  # Emitted during scoring (current, total)
    documents_scored = Signal(list)  # Emitted when all documents are scored

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

        # Lifecycle state tracking
        self._is_active: bool = True  # False after cleanup() is called

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

            # Phase 3: Execute the actual workflow
            self.execute_workflow()

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
                assert hasattr(self.query_agent, 'convert_question'), "QueryAgent missing convert_question method"
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
        """
        Execute the workflow (Milestone 2: Add document scoring).

        This method orchestrates the workflow steps in sequence.
        For Milestone 2, we implement:
        1. Query generation
        2. Document search
        3. Document scoring (NEW)
        4. Display results

        Later milestones will add citations and reports.
        """
        try:
            # Step 1: Generate query
            self.status_message.emit("🔍 Generating database query from your question...")
            query = self.generate_query()

            if not query:
                raise ValueError("Query generation failed - no query returned")

            # Step 2: Search for documents
            self.status_message.emit(f"📚 Searching database with query: {query[:100]}...")
            documents = self.search_documents(query)

            if not documents:
                self.status_message.emit("⚠️ No documents found")
                self.workflow_completed.emit({
                    'phase': 3,
                    'milestone': 2,
                    'status': 'no_documents',
                    'question': self.current_question,
                    'query': query,
                    'documents': [],
                    'scored_documents': [],
                    'document_count': 0
                })
                return

            # Step 3: Score documents for relevance (NEW in Milestone 2)
            self.status_message.emit(f"📊 Scoring {len(documents)} documents for relevance...")
            scored_documents = self.score_documents(documents)

            # Step 4: Emit results
            high_scoring = len([d for d, s in scored_documents if s.get('score', 0) >= 3])
            self.status_message.emit(
                f"✅ Scored {len(scored_documents)} documents ({high_scoring} highly relevant)"
            )

            # Emit completion with results including scores
            self.workflow_completed.emit({
                'phase': 3,
                'milestone': 2,
                'status': 'scoring_completed',
                'question': self.current_question,
                'query': query,
                'documents': documents,
                'scored_documents': scored_documents,
                'document_count': len(documents),
                'high_scoring_count': high_scoring
            })

        except Exception as e:
            self.logger.error(f"Workflow execution failed: {e}", exc_info=True)
            self.workflow_error.emit(e)

    def generate_query(self) -> str:
        """
        Generate PostgreSQL tsquery from research question.

        Returns:
            str: The generated tsquery string

        Raises:
            RuntimeError: If QueryAgent is not initialized or executor has been cleaned up
            ValueError: If query generation returns empty/invalid result
            Exception: If query generation fails
        """
        if not self._is_active:
            raise RuntimeError("Workflow executor has been cleaned up - cannot generate query")

        if not self.query_agent:
            raise RuntimeError("QueryAgent not initialized")

        if not self.current_question or not self.current_question.strip():
            raise ValueError("Cannot generate query from empty research question")

        try:
            # Call the query agent to convert natural language to tsquery
            query: Optional[str] = self.query_agent.convert_question(self.current_question)

            # Validate query result
            if query is None:
                raise ValueError("QueryAgent returned None - query generation failed")

            if not isinstance(query, str):
                raise TypeError(f"QueryAgent returned invalid type: {type(query)}, expected str")

            if not query.strip():
                raise ValueError("QueryAgent returned empty query string")

            self.logger.info(f"Generated query: {query}")

            # Emit query_generated signal for UI update
            self.query_generated.emit(query)

            return query

        except Exception as e:
            self.logger.error(f"Query generation failed: {e}", exc_info=True)
            raise

    def search_documents(self, query: str) -> list:
        """
        Execute database search with the generated query.

        Args:
            query: PostgreSQL tsquery string

        Returns:
            list: List of document dictionaries

        Raises:
            RuntimeError: If QueryAgent is not initialized
            Exception: If search fails
        """
        if not self.query_agent:
            raise RuntimeError("QueryAgent not initialized")

        try:
            # Use find_abstracts to execute the search
            # This returns a generator, so we convert to list
            documents = list(self.query_agent.find_abstracts(
                question=self.current_question,
                max_rows=self.max_results,
                use_pubmed=True,
                use_medrxiv=True,
                use_others=True
            ))

            self.logger.info(f"Found {len(documents)} documents")

            # Store documents in workflow state
            self.documents = documents

            # Emit documents_found signal for UI update
            self.documents_found.emit(documents)

            return documents

        except Exception as e:
            self.logger.error(f"Document search failed: {e}", exc_info=True)
            raise

    def score_documents(self, documents: list) -> list:
        """
        Score documents for relevance using DocumentScoringAgent.

        Args:
            documents: List of document dictionaries to score

        Returns:
            list: List of (document, score_result) tuples

        Raises:
            RuntimeError: If ScoringAgent is not initialized
            Exception: If scoring fails
        """
        if not self.scoring_agent:
            raise RuntimeError("ScoringAgent not initialized")

        if not documents:
            self.logger.warning("No documents to score")
            return []

        try:
            self.logger.info(f"Scoring {len(documents)} documents for relevance...")

            scored_documents = []
            total = len(documents)

            for i, doc in enumerate(documents, 1):
                # Score this document
                score_result = self.scoring_agent.evaluate_document(
                    user_question=self.current_question,
                    document=doc
                )

                if score_result:
                    scored_documents.append((doc, score_result))

                    # Emit progress for every document
                    self.scoring_progress.emit(i, total)

                    # Log progress every 10 documents or at end
                    if i % 10 == 0 or i == total:
                        self.status_message.emit(f"📊 Scored {i}/{total} documents...")
                        self.logger.debug(f"Progress: {i}/{total} documents scored")

            self.logger.info(f"Successfully scored {len(scored_documents)} documents")

            # Store in workflow state
            self.scored_documents = scored_documents

            # Emit signal for UI update
            self.documents_scored.emit(scored_documents)

            return scored_documents

        except Exception as e:
            self.logger.error(f"Document scoring failed: {e}", exc_info=True)
            raise

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

    def cleanup(self) -> None:
        """
        Cleanup workflow executor resources.

        This method:
        - Marks executor as inactive (prevents further method calls)
        - Clears workflow state (documents, citations, reports)
        - Clears agent references
        - Should be called when the plugin is unloaded or the workflow is reset
        """
        try:
            self.logger.info("Cleaning up workflow executor resources...")

            # Mark as inactive to prevent further method calls
            self._is_active = False

            # Clear workflow state
            self.current_question = ""
            self.documents = []
            self.scored_documents = []
            self.citations = []
            self.preliminary_report = ""
            self.counterfactual_analysis = None
            self.final_report = ""

            # Clear agent references (but don't destroy agents - they're managed elsewhere)
            # Agents dictionary is kept for potential reuse, but individual references cleared
            self.query_agent = None
            self.scoring_agent = None
            self.citation_agent = None
            self.reporting_agent = None
            self.counterfactual_agent = None
            self.editor_agent = None
            self.orchestrator = None

            self.logger.info("✅ Workflow executor cleanup complete")

        except Exception as e:
            self.logger.error(f"Error during workflow executor cleanup: {e}", exc_info=True)

    def cancel_workflow(self) -> None:
        """
        Cancel ongoing workflow execution.

        This method will be implemented in Phase 3 when workflow threading is added.
        For now, it's a placeholder for future cancellation logic.
        """
        # TODO Phase 3: Implement workflow cancellation
        # - Set cancellation flag
        # - Stop background threads/workers
        # - Emit workflow_error signal with cancellation exception
        self.logger.warning("Workflow cancellation not yet implemented (Phase 3)")
        pass
