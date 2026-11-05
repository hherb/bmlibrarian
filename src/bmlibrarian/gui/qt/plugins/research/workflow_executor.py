"""
Qt-specific workflow executor for BMLibrarian research workflow.

Adapts the agent-based workflow to Qt's signal/slot architecture.
"""

from typing import Dict, Any, Optional
from PySide6.QtCore import QObject
import logging

# Default threshold constants
DEFAULT_SCORING_THRESHOLD = 3.0  # Minimum score for citation extraction
DEFAULT_CITATION_EXTRACTION_THRESHOLD = 0.7  # Citation relevance threshold


class QtWorkflowExecutor(QObject):
    """
    Qt-specific workflow executor using real BMLibrarian agents.

    The executor holds the agents and the run's state (question, query,
    documents, scored documents) and runs the query, search and report
    steps; ``WorkflowThread`` drives the steps and emits every
    progress/result signal to the tab.

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

            return documents

        except Exception as e:
            self.logger.error(f"Document search failed: {e}", exc_info=True)
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
