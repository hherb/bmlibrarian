"""
Qt-specific workflow executor for BMLibrarian research workflow.

Adapts the agent-based workflow to Qt's signal/slot architecture.
"""

from typing import Dict, Any, Optional
from PySide6.QtCore import QObject, Signal, QRunnable, Slot
import logging

# Default threshold constants
DEFAULT_SCORING_THRESHOLD = 3.0  # Minimum score for citation extraction
DEFAULT_CITATION_EXTRACTION_THRESHOLD = 0.7  # Citation relevance threshold


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
    citations_extracted = Signal(list)  # Emitted when citations are extracted
    preliminary_report_generated = Signal(str)  # Emitted when preliminary report is generated

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
        self.generated_query: str = ""  # Store the generated query for methodology
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
        self.scoring_threshold: float = DEFAULT_SCORING_THRESHOLD
        self.citation_extraction_threshold: float = DEFAULT_CITATION_EXTRACTION_THRESHOLD

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
        counterfactual: bool = True,
        scoring_threshold: float = DEFAULT_SCORING_THRESHOLD,
        citation_extraction_threshold: float = DEFAULT_CITATION_EXTRACTION_THRESHOLD
    ) -> None:
        """
        Start the research workflow (Phase 2: just validate, don't execute).

        Args:
            question: Research question
            max_results: Maximum documents to retrieve
            min_relevant: Minimum relevant documents to find
            interactive: Enable interactive mode
            counterfactual: Enable counterfactual analysis
            scoring_threshold: Minimum score for citation extraction
            citation_extraction_threshold: Citation relevance threshold
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
            self.scoring_threshold = scoring_threshold
            self.citation_extraction_threshold = citation_extraction_threshold

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
                # Use explicit runtime checks instead of assertions
                if not hasattr(self.query_agent, 'convert_question'):
                    raise RuntimeError("QueryAgent missing convert_question method")
                self.status_message.emit("✓ QueryAgent ready")
            else:
                raise RuntimeError("QueryAgent not initialized")

            # Test ScoringAgent
            if self.scoring_agent:
                if not hasattr(self.scoring_agent, 'evaluate_document'):
                    raise RuntimeError("ScoringAgent missing evaluate_document method")
                self.status_message.emit("✓ ScoringAgent ready")
            else:
                raise RuntimeError("ScoringAgent not initialized")

            # Test CitationAgent
            if self.citation_agent:
                if not hasattr(self.citation_agent, 'process_scored_documents_for_citations'):
                    raise RuntimeError("CitationAgent missing citation method")
                self.status_message.emit("✓ CitationAgent ready")
            else:
                raise RuntimeError("CitationAgent not initialized")

            # Test ReportingAgent
            if self.reporting_agent:
                if not hasattr(self.reporting_agent, 'generate_citation_based_report'):
                    raise RuntimeError("ReportingAgent missing report method")
                self.status_message.emit("✓ ReportingAgent ready")
            else:
                raise RuntimeError("ReportingAgent not initialized")

            # Test EditorAgent
            if self.editor_agent:
                if not hasattr(self.editor_agent, 'edit_comprehensive_report'):
                    raise RuntimeError("EditorAgent missing edit method")
                self.status_message.emit("✓ EditorAgent ready")
            else:
                raise RuntimeError("EditorAgent not initialized")

            # Test CounterfactualAgent (optional)
            if self.counterfactual_enabled:
                if self.counterfactual_agent:
                    if not hasattr(self.counterfactual_agent, 'generate_counterfactual_questions'):
                        raise RuntimeError("CounterfactualAgent missing counterfactual method")
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
        Execute the workflow (Milestone 3: Add citations and preliminary report).

        This method orchestrates the workflow steps in sequence.
        For Milestone 3, we implement:
        1. Query generation
        2. Document search
        3. Document scoring
        4. Citation extraction (NEW)
        5. Preliminary report generation (NEW)
        6. Display results

        Later milestones will add counterfactual analysis and final report.
        """
        try:
            # Early check: if executor has been cleaned up, return silently
            # This prevents errors when user closes tab during workflow execution
            if not self._is_active:
                self.logger.warning("Workflow executor is not active - aborting workflow")
                return

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
                    'milestone': 3,
                    'status': 'no_documents',
                    'question': self.current_question,
                    'query': query,
                    'documents': [],
                    'scored_documents': [],
                    'citations': [],
                    'preliminary_report': '',
                    'document_count': 0
                })
                return

            # Step 3: Score documents for relevance
            self.status_message.emit(f"📊 Scoring {len(documents)} documents for relevance...")
            scored_documents = self.score_documents(documents)

            if not scored_documents:
                self.status_message.emit("⚠️ No documents could be scored")
                self.workflow_completed.emit({
                    'phase': 3,
                    'milestone': 3,
                    'status': 'no_scores',
                    'question': self.current_question,
                    'query': query,
                    'documents': documents,
                    'scored_documents': [],
                    'citations': [],
                    'preliminary_report': '',
                    'document_count': len(documents)
                })
                return

            # Step 4: Extract citations from high-scoring documents (NEW in Milestone 3)
            high_scoring = len([
                d for d, s in scored_documents
                if isinstance(s.get('score'), (int, float)) and s.get('score', 0) >= self.scoring_threshold
            ])
            self.status_message.emit(
                f"💬 Extracting citations from {high_scoring} high-scoring documents..."
            )
            citations = self.extract_citations(scored_documents, score_threshold=self.scoring_threshold)

            # Emit citations signal for UI update
            self.citations_extracted.emit(citations)

            if not citations:
                self.status_message.emit("⚠️ No citations could be extracted")
                self.workflow_completed.emit({
                    'phase': 3,
                    'milestone': 3,
                    'status': 'no_citations',
                    'question': self.current_question,
                    'query': query,
                    'documents': documents,
                    'scored_documents': scored_documents,
                    'citations': [],
                    'preliminary_report': '',
                    'document_count': len(documents),
                    'high_scoring_count': high_scoring
                })
                return

            # Step 5: Generate preliminary report (NEW in Milestone 3)
            self.status_message.emit(
                f"📄 Generating preliminary report from {len(citations)} citations..."
            )
            preliminary_report = self.generate_preliminary_report(citations)

            # Emit preliminary report signal for UI update
            self.preliminary_report_generated.emit(preliminary_report)

            # Step 6: Emit completion with all results
            self.status_message.emit(
                f"✅ Workflow complete! {len(citations)} citations, "
                f"{len(preliminary_report)} character report"
            )

            self.workflow_completed.emit({
                'phase': 3,
                'milestone': 3,
                'status': 'preliminary_report_completed',
                'question': self.current_question,
                'query': query,
                'documents': documents,
                'scored_documents': scored_documents,
                'citations': citations,
                'preliminary_report': preliminary_report,
                'document_count': len(documents),
                'high_scoring_count': high_scoring,
                'citation_count': len(citations),
                'report_length': len(preliminary_report)
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

        Note:
            If executor has been cleaned up (e.g., user closed tab), this will log a warning
            and raise RuntimeError. Callers should check _is_active before calling this method
            to avoid unnecessary errors.
        """
        if not self._is_active:
            # This should be caught by execute_workflow's early check
            # If we reach here, it means the method was called directly
            self.logger.warning("Attempted to generate query after executor cleanup")
            raise RuntimeError(
                "Workflow executor is not active - cannot generate query. "
                "The workflow may have been cancelled or the tab closed."
            )

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

            # Store query for methodology metadata
            self.generated_query = query

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

    def extract_citations(self, scored_documents: list, score_threshold: float = 3.0) -> list:
        """
        Extract citations from high-scoring documents.

        Args:
            scored_documents: List of (document, score_result) tuples
            score_threshold: Minimum score to include for citation extraction

        Returns:
            list: List of citations extracted from documents

        Raises:
            RuntimeError: If CitationAgent is not initialized
            Exception: If citation extraction fails
        """
        if not self.citation_agent:
            raise RuntimeError("CitationAgent not initialized")

        if not scored_documents:
            self.logger.warning("No scored documents to extract citations from")
            return []

        try:
            # Filter documents above threshold
            high_scoring = [
                (doc, score_result) for doc, score_result in scored_documents
                if isinstance(score_result.get('score'), (int, float)) and score_result.get('score', 0) >= score_threshold
            ]

            self.logger.info(
                f"Extracting citations from {len(high_scoring)} documents (score >= {score_threshold})"
            )

            if not high_scoring:
                self.logger.warning(f"No documents meet the threshold of {score_threshold}")
                return []

            # Call citation agent to extract citations
            citations = self.citation_agent.process_scored_documents_for_citations(
                user_question=self.current_question,
                scored_documents=high_scoring,
                score_threshold=score_threshold
            )

            self.logger.info(f"Successfully extracted {len(citations)} citations")

            # Store in workflow state
            self.citations = citations

            return citations

        except Exception as e:
            self.logger.error(f"Citation extraction failed: {e}", exc_info=True)
            raise

    def _generate_methodology_metadata(self) -> Optional['MethodologyMetadata']:
        """
        Generate methodology metadata for the report.

        Returns:
            MethodologyMetadata object or None if insufficient data
        """
        # Import here to avoid circular imports
        from bmlibrarian.agents.reporting_agent import MethodologyMetadata

        if not self.current_question:
            return None

        # Calculate documents by score distribution
        documents_by_score = {}
        for doc, score_result in self.scored_documents:
            score_value = score_result.get('score', 0)
            if isinstance(score_value, (int, float)):
                score_int = int(score_value)
                documents_by_score[score_int] = documents_by_score.get(score_int, 0) + 1

        # Calculate documents above threshold
        documents_above_threshold = sum(
            count for score, count in documents_by_score.items()
            if score >= self.scoring_threshold
        )

        # Get model names from agents
        query_model = getattr(self.query_agent, 'model', None) if self.query_agent else None
        scoring_model = getattr(self.scoring_agent, 'model', None) if self.scoring_agent else None
        citation_model = getattr(self.citation_agent, 'model', None) if self.citation_agent else None
        reporting_model = getattr(self.reporting_agent, 'model', None) if self.reporting_agent else None
        counterfactual_model = getattr(self.counterfactual_agent, 'model', None) if self.counterfactual_agent else None
        editor_model = getattr(self.editor_agent, 'model', None) if self.editor_agent else None

        # Get model parameters (temperature, top_p) from reporting agent
        model_temperature = getattr(self.reporting_agent, 'temperature', None) if self.reporting_agent else None
        model_top_p = getattr(self.reporting_agent, 'top_p', None) if self.reporting_agent else None

        # Create metadata
        metadata = MethodologyMetadata(
            human_question=self.current_question,
            generated_query=self.generated_query,
            total_documents_found=len(self.documents),
            scoring_threshold=self.scoring_threshold,
            documents_by_score=documents_by_score,
            documents_above_threshold=documents_above_threshold,
            documents_processed_for_citations=len([
                d for d, s in self.scored_documents
                if isinstance(s.get('score'), (int, float)) and s.get('score', 0) >= self.scoring_threshold
            ]),
            citation_extraction_threshold=self.citation_extraction_threshold,
            counterfactual_performed=False,
            counterfactual_queries_generated=0,
            counterfactual_documents_found=0,
            counterfactual_citations_extracted=0,
            iterative_processing_used=True,
            context_window_management=True,
            # Model information
            query_model=query_model,
            scoring_model=scoring_model,
            citation_model=citation_model,
            reporting_model=reporting_model,
            counterfactual_model=counterfactual_model,
            editor_model=editor_model,
            model_temperature=model_temperature,
            model_top_p=model_top_p
        )

        return metadata

    def generate_preliminary_report(self, citations: list) -> str:
        """
        Generate preliminary report from citations.

        Args:
            citations: List of citations to include in report

        Returns:
            str: Markdown-formatted preliminary report

        Raises:
            RuntimeError: If ReportingAgent is not initialized
            Exception: If report generation fails
        """
        if not self.reporting_agent:
            raise RuntimeError("ReportingAgent not initialized")

        if not citations:
            self.logger.warning("No citations available for report generation")
            return "# Preliminary Report\n\nNo citations available.\n"

        try:
            self.logger.info(f"Generating preliminary report from {len(citations)} citations")

            # Generate methodology metadata with model information
            methodology_metadata = self._generate_methodology_metadata()

            # Call reporting agent to generate report with metadata
            report = self.reporting_agent.generate_citation_based_report(
                user_question=self.current_question,
                citations=citations,
                format_output=True,  # Get markdown formatted output
                methodology_metadata=methodology_metadata
            )

            if not report or not isinstance(report, str):
                raise ValueError("Report generation returned invalid result")

            self.logger.info(f"Successfully generated preliminary report ({len(report)} characters)")

            # Store in workflow state
            self.preliminary_report = report

            return report

        except Exception as e:
            self.logger.error(f"Preliminary report generation failed: {e}", exc_info=True)
            raise

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
            self.generated_query = ""
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
