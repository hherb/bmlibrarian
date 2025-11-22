"""
PaperChecker Agent for medical abstract fact-checking.

This module implements PaperCheckerAgent, a sophisticated fact-checking system
for medical abstracts that validates research claims by systematically searching
for and analyzing contradictory evidence.

The agent orchestrates a multi-step workflow:
1. Extract core statements from abstracts
2. Generate counter-statements and search materials
3. Multi-strategy search (semantic + HyDE + keyword)
4. Score documents for relevance
5. Extract supporting citations
6. Generate counter-evidence reports
7. Analyze verdicts
"""

from typing import Dict, List, Optional, Any, Callable
import logging
from datetime import datetime

from psycopg.rows import dict_row

from bmlibrarian.agents.base import BaseAgent
from bmlibrarian.database import get_db_manager
from bmlibrarian.agents.orchestrator import AgentOrchestrator
from bmlibrarian.agents.scoring_agent import DocumentScoringAgent
from bmlibrarian.agents.citation_agent import CitationFinderAgent
from bmlibrarian.config import get_config, get_model, get_agent_config, get_ollama_host

from .data_models import (
    Statement, CounterStatement, SearchResults, ScoredDocument,
    ExtractedCitation, CounterReport, Verdict, PaperCheckResult
)
from .database import PaperCheckDB
from .components import (
    StatementExtractor,
    CounterStatementGenerator,
    HyDEGenerator,
    SearchCoordinator,
    VerdictAnalyzer
)


logger = logging.getLogger(__name__)


# Constants for configuration defaults
DEFAULT_MAX_STATEMENTS: int = 2
DEFAULT_TEMPERATURE: float = 0.3
DEFAULT_TOP_P: float = 0.9
DEFAULT_SCORE_THRESHOLD: float = 3.0
DEFAULT_MIN_CITATION_SCORE: int = 3
DEFAULT_HYDE_NUM_ABSTRACTS: int = 2
DEFAULT_HYDE_MAX_KEYWORDS: int = 10
DEFAULT_SEMANTIC_LIMIT: int = 50
DEFAULT_HYDE_LIMIT: int = 50
DEFAULT_KEYWORD_LIMIT: int = 50
DEFAULT_MAX_DEDUPLICATED: int = 100
DEFAULT_MAX_CITATIONS_PER_STATEMENT: int = 10
DEFAULT_SCORING_BATCH_SIZE: int = 20
DEFAULT_EARLY_STOP_COUNT: int = 20
DEFAULT_EXPLANATION_TITLE_MAX_LEN: int = 100


class PaperCheckerAgent(BaseAgent):
    """
    Agent for fact-checking medical abstracts through systematic counter-evidence search.

    PaperCheckerAgent analyzes medical abstracts, extracts core claims, searches for
    contradictory evidence, and generates verdicts on whether counter-evidence supports,
    contradicts, or is undecided about the original claims.

    Workflow:
        1. Extract statements from abstract
        2. Generate counter-statements and search materials
        3. Multi-strategy search (semantic + HyDE + keyword)
        4. Score documents for relevance
        5. Extract supporting citations
        6. Generate counter-evidence reports
        7. Analyze verdicts

    Attributes:
        config: Full configuration dictionary
        agent_config: Paper checker specific configuration
        db: Database connection for result persistence
        statement_extractor: Component for extracting statements from abstracts
        counter_generator: Component for generating counter-statements
        hyde_generator: Component for HyDE abstract and keyword generation
        search_coordinator: Component for multi-strategy search coordination
        verdict_analyzer: Component for verdict analysis
        scoring_agent: BMLibrarian DocumentScoringAgent for relevance scoring
        citation_agent: BMLibrarian CitationFinderAgent for citation extraction
        score_threshold: Minimum score for document inclusion
        min_citation_score: Minimum score for citation extraction

    Example:
        >>> agent = PaperCheckerAgent()
        >>> result = agent.check_abstract(
        ...     abstract="Metformin shows superior efficacy...",
        ...     source_metadata={"pmid": 12345678}
        ... )
        >>> print(result.overall_assessment)
    """

    def __init__(
        self,
        orchestrator: Optional[AgentOrchestrator] = None,
        config: Optional[Dict[str, Any]] = None,
        db_connection=None,
        show_model_info: bool = True
    ):
        """
        Initialize PaperCheckerAgent with configuration and dependencies.

        Args:
            orchestrator: Optional AgentOrchestrator for queue-based processing
            config: Optional configuration dict (uses ~/.bmlibrarian/config.json if None)
            db_connection: Optional database connection (creates new if None)
            show_model_info: Whether to display model information on initialization
        """
        # Load configuration
        self.config = config or get_config()._config
        self.agent_config = get_agent_config("paper_checker")

        # Get model and host from configuration
        model = get_model("paper_checker_agent", default="gpt-oss:20b")
        host = get_ollama_host()

        # Extract agent parameters from config
        agent_params = self._filter_agent_params(self.agent_config)

        # Initialize base agent
        super().__init__(
            model=model,
            host=host,
            orchestrator=orchestrator,
            show_model_info=show_model_info,
            **agent_params
        )

        # Database connection
        self.db = db_connection if db_connection is not None else PaperCheckDB()

        # Initialize sub-components
        self._init_components()

        # Initialize existing BMLibrarian agents
        self._init_bmlibrarian_agents()

        logger.info(
            f"Initialized PaperCheckerAgent with model={self.model}, "
            f"max_statements={self.max_statements}"
        )

    def _filter_agent_params(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Filter config to only include BaseAgent-supported parameters.

        Args:
            config: Agent configuration dictionary

        Returns:
            Filtered dictionary with only supported parameters
        """
        supported = {"temperature", "top_p"}
        return {k: v for k, v in config.items() if k in supported}

    def _init_components(self) -> None:
        """Initialize PaperChecker sub-components."""
        temperature = self.agent_config.get("temperature", DEFAULT_TEMPERATURE)

        self.statement_extractor = StatementExtractor(
            model=self.model,
            host=self.host,
            max_statements=self.agent_config.get("max_statements", DEFAULT_MAX_STATEMENTS),
            temperature=temperature
        )

        self.counter_generator = CounterStatementGenerator(
            model=self.model,
            host=self.host,
            temperature=temperature
        )

        hyde_config = self.agent_config.get("hyde", {})
        self.hyde_generator = HyDEGenerator(
            model=self.model,
            host=self.host,
            num_abstracts=hyde_config.get("num_abstracts", DEFAULT_HYDE_NUM_ABSTRACTS),
            max_keywords=hyde_config.get("max_keywords", DEFAULT_HYDE_MAX_KEYWORDS),
            temperature=temperature
        )

        search_config = self.agent_config.get("search", {})
        self.search_coordinator = SearchCoordinator(
            config=search_config,
            db_connection=self.db.get_connection()
        )

        self.verdict_analyzer = VerdictAnalyzer(
            model=self.model,
            host=self.host,
            temperature=temperature
        )

    def _init_bmlibrarian_agents(self) -> None:
        """Initialize existing BMLibrarian agents for reuse."""
        self.scoring_agent = DocumentScoringAgent(
            orchestrator=self.orchestrator,
            model=get_model("scoring_agent"),
            host=self.host,
            show_model_info=False
        )

        self.citation_agent = CitationFinderAgent(
            orchestrator=self.orchestrator,
            model=get_model("citation_agent"),
            host=self.host,
            show_model_info=False
        )

        # Get scoring threshold from config
        self.score_threshold = self.agent_config.get("score_threshold", DEFAULT_SCORE_THRESHOLD)
        citation_config = self.agent_config.get("citation", {})
        self.min_citation_score = citation_config.get("min_score", DEFAULT_MIN_CITATION_SCORE)

    def get_agent_type(self) -> str:
        """
        Get the type/name of this agent.

        Returns:
            String identifier for the agent type
        """
        return "PaperCheckerAgent"

    # ==================== PUBLIC API ====================

    def check_abstract(
        self,
        abstract: str,
        source_metadata: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable[[str, float], None]] = None
    ) -> PaperCheckResult:
        """
        Check a single abstract for factual accuracy.

        This is the main entry point for fact-checking a medical abstract.
        It orchestrates the full workflow from statement extraction through
        verdict generation.

        Args:
            abstract: The abstract text to check
            source_metadata: Optional metadata (pmid, doi, title, etc.)
            progress_callback: Optional callback(step_name, progress_fraction)
                             Called with progress updates during processing

        Returns:
            PaperCheckResult with complete analysis including:
                - Extracted statements
                - Counter-statements with search materials
                - Search results from all strategies
                - Scored documents
                - Counter-evidence reports
                - Verdicts for each statement
                - Overall assessment

        Raises:
            ValueError: If abstract is empty or invalid
            RuntimeError: If processing fails unrecoverably
        """
        logger.info("Starting abstract check")
        start_time = datetime.now()

        # Validate input
        if not abstract or len(abstract.strip()) == 0:
            raise ValueError("Abstract cannot be empty")

        source_metadata = source_metadata or {}

        try:
            # Step 1: Extract statements
            self._report_progress(progress_callback, "Extracting statements", 0.1)
            statements = self._extract_statements(abstract)
            logger.info(f"Extracted {len(statements)} statements")

            # Step 2: Generate counter-statements
            self._report_progress(progress_callback, "Generating counter-statements", 0.2)
            counter_statements = self._generate_counter_statements(statements)

            # Process each statement
            search_results_list: List[SearchResults] = []
            scored_docs_list: List[List[ScoredDocument]] = []
            counter_reports_list: List[CounterReport] = []
            verdicts_list: List[Verdict] = []

            num_statements = len(statements)
            for i, (stmt, counter_stmt) in enumerate(zip(statements, counter_statements)):
                logger.info(f"Processing statement {i+1}/{num_statements}")
                base_progress = 0.2 + (i / num_statements) * 0.7

                # Step 3: Multi-strategy search
                self._report_progress(
                    progress_callback,
                    f"Searching for counter-evidence ({i+1}/{num_statements})",
                    base_progress + 0.1
                )
                search_results = self._search_counter_evidence(counter_stmt)
                search_results_list.append(search_results)

                # Step 4: Score documents
                self._report_progress(
                    progress_callback,
                    f"Scoring documents ({i+1}/{num_statements})",
                    base_progress + 0.2
                )
                scored_docs = self._score_documents(counter_stmt, search_results)
                scored_docs_list.append(scored_docs)

                # Step 5: Extract citations
                self._report_progress(
                    progress_callback,
                    f"Extracting citations ({i+1}/{num_statements})",
                    base_progress + 0.3
                )
                citations = self._extract_citations(counter_stmt, scored_docs)

                # Step 6: Generate counter-report
                self._report_progress(
                    progress_callback,
                    f"Generating counter-report ({i+1}/{num_statements})",
                    base_progress + 0.4
                )
                counter_report = self._generate_counter_report(
                    counter_stmt, citations, search_results, scored_docs
                )
                counter_reports_list.append(counter_report)

                # Step 7: Analyze verdict
                self._report_progress(
                    progress_callback,
                    f"Analyzing verdict ({i+1}/{num_statements})",
                    base_progress + 0.5
                )
                verdict = self._analyze_verdict(stmt, counter_report)
                verdicts_list.append(verdict)

            # Step 8: Overall assessment
            self._report_progress(progress_callback, "Generating overall assessment", 0.95)
            overall_assessment = self._generate_overall_assessment(
                statements, verdicts_list
            )

            # Create result object
            processing_time = (datetime.now() - start_time).total_seconds()
            result = PaperCheckResult(
                original_abstract=abstract,
                source_metadata=source_metadata,
                statements=statements,
                counter_statements=counter_statements,
                search_results=search_results_list,
                scored_documents=scored_docs_list,
                counter_reports=counter_reports_list,
                verdicts=verdicts_list,
                overall_assessment=overall_assessment,
                processing_metadata={
                    "model": self.model,
                    "config": self.agent_config,
                    "timestamp": datetime.now().isoformat(),
                    "processing_time_seconds": processing_time
                }
            )

            # Save to database
            self._report_progress(progress_callback, "Saving results", 0.99)
            abstract_id = self.db.save_complete_result(result)
            result.processing_metadata["abstract_id"] = abstract_id

            self._report_progress(progress_callback, "Complete", 1.0)
            logger.info(
                f"Abstract check complete in {processing_time:.2f}s, "
                f"saved as abstract_id={abstract_id}"
            )

            return result

        except Exception as e:
            logger.error(f"Abstract check failed: {e}", exc_info=True)
            raise RuntimeError(f"Failed to check abstract: {e}") from e

    def check_abstracts_batch(
        self,
        abstracts: List[Dict[str, Any]],
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> List[PaperCheckResult]:
        """
        Check multiple abstracts in batch (queue-based processing).

        Processes each abstract sequentially, continuing even if individual
        abstracts fail. Failed abstracts are logged but don't stop the batch.

        Args:
            abstracts: List of dicts with 'abstract' and optional 'metadata' keys
                      Example: [{"abstract": "...", "metadata": {"pmid": 123}}]
            progress_callback: Optional callback(completed, total)
                              Called after each abstract is processed

        Returns:
            List of PaperCheckResult objects (only successful checks)
        """
        logger.info(f"Starting batch check of {len(abstracts)} abstracts")
        results: List[PaperCheckResult] = []
        total = len(abstracts)

        for i, item in enumerate(abstracts, 1):
            try:
                result = self.check_abstract(
                    abstract=item["abstract"],
                    source_metadata=item.get("metadata", {})
                )
                results.append(result)

                if progress_callback:
                    progress_callback(i, total)

            except Exception as e:
                logger.error(f"Failed to check abstract {i}: {e}")
                # Continue with next abstract
                continue

        logger.info(f"Batch check complete: {len(results)}/{total} successful")
        return results

    def test_connection(self) -> bool:
        """
        Test connectivity to all required services.

        Verifies that:
        1. Ollama server is reachable and model is available
        2. Database connection is working
        3. Sub-agents can connect to their services

        Returns:
            True if all connections are successful, False otherwise
        """
        try:
            # Test Ollama connection (uses BaseAgent method)
            if not self._test_ollama_connection():
                logger.error("Ollama connection failed")
                return False

            # Test database connection
            if not self.db.test_connection():
                logger.error("Database connection failed")
                return False

            # Test sub-agents
            if not self.scoring_agent.test_connection():
                logger.error("ScoringAgent connection failed")
                return False

            if not self.citation_agent.test_connection():
                logger.error("CitationAgent connection failed")
                return False

            logger.info("All connections successful")
            return True

        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False

    def _test_ollama_connection(self) -> bool:
        """
        Test Ollama connection and model availability.

        Returns:
            True if Ollama is reachable and model is available
        """
        try:
            # Use parent class test_connection method
            return super().test_connection()
        except Exception as e:
            logger.error(f"Ollama connection test failed: {e}")
            return False

    # ==================== WORKFLOW STEPS ====================
    # These methods will be implemented in subsequent steps (04-11)

    def _extract_statements(self, abstract: str) -> List[Statement]:
        """
        Step 1: Extract core statements from abstract.

        Uses the StatementExtractor component to analyze the abstract and
        identify the most important research claims, hypotheses, and conclusions.

        Args:
            abstract: The abstract text to extract statements from

        Returns:
            List of Statement objects extracted from the abstract

        Raises:
            ValueError: If abstract is invalid or too short
            RuntimeError: If extraction fails
        """
        logger.info(f"Extracting statements from abstract ({len(abstract)} chars)")

        try:
            statements = self.statement_extractor.extract(abstract)
            logger.info(f"Extracted {len(statements)} statements")
            return statements

        except Exception as e:
            logger.error(f"Statement extraction failed: {e}", exc_info=True)
            raise RuntimeError(f"Failed to extract statements: {e}") from e

    def _generate_counter_statements(
        self, statements: List[Statement]
    ) -> List[CounterStatement]:
        """
        Step 2: Generate counter-statements for all extracted statements.

        For each statement, generates:
        - Semantically precise negation
        - HyDE abstracts that would support the counter-claim
        - Keywords for literature search

        Args:
            statements: List of extracted Statement objects

        Returns:
            List of CounterStatement objects with search materials

        Raises:
            RuntimeError: If counter-statement generation fails
        """
        counter_statements = []

        for i, statement in enumerate(statements, 1):
            logger.info(f"Generating counter-statement {i}/{len(statements)}")

            try:
                # Generate negation using CounterStatementGenerator
                negated_text = self.counter_generator.generate(statement)

                # Generate HyDE materials using HyDEGenerator
                hyde_materials = self.hyde_generator.generate(statement, negated_text)

                # Create CounterStatement object
                counter_stmt = CounterStatement(
                    original_statement=statement,
                    negated_text=negated_text,
                    hyde_abstracts=hyde_materials["hyde_abstracts"],
                    keywords=hyde_materials["keywords"],
                    generation_metadata={
                        "model": self.model,
                        "temperature": self.agent_config.get("temperature", DEFAULT_TEMPERATURE),
                        "timestamp": datetime.now().isoformat()
                    }
                )

                counter_statements.append(counter_stmt)

                logger.info(
                    f"Counter-statement generated: {negated_text[:50]}... "
                    f"({len(hyde_materials['hyde_abstracts'])} HyDE abstracts, "
                    f"{len(hyde_materials['keywords'])} keywords)"
                )

            except Exception as e:
                logger.error(
                    f"Failed to generate counter-statement for statement {i}: {e}",
                    exc_info=True
                )
                raise RuntimeError(
                    f"Counter-statement generation failed for statement {i}: {e}"
                ) from e

        return counter_statements

    def _search_counter_evidence(
        self, counter_stmt: CounterStatement
    ) -> SearchResults:
        """
        Step 3: Multi-strategy search for counter-evidence.

        Executes three parallel search strategies:
        1. Semantic search (embedding-based)
        2. HyDE search (hypothetical document matching)
        3. Keyword search (full-text)

        Args:
            counter_stmt: CounterStatement with search materials including:
                - negated_text: The counter-claim for semantic search
                - hyde_abstracts: Hypothetical abstracts for HyDE search
                - keywords: Search keywords for full-text search

        Returns:
            SearchResults with deduplicated docs and provenance tracking

        Raises:
            RuntimeError: If search fails (all strategies fail)
        """
        try:
            search_results = self.search_coordinator.search(counter_stmt)

            logger.info(
                f"Search found {len(search_results.deduplicated_docs)} unique documents:\n"
                f"  Semantic: {len(search_results.semantic_docs)}\n"
                f"  HyDE: {len(search_results.hyde_docs)}\n"
                f"  Keyword: {len(search_results.keyword_docs)}"
            )

            return search_results

        except RuntimeError as e:
            logger.error(f"Counter-evidence search failed: {e}")
            raise

    def _score_documents(
        self, counter_stmt: CounterStatement, search_results: SearchResults
    ) -> List[ScoredDocument]:
        """
        Step 4: Score documents for counter-statement support.

        Uses DocumentScoringAgent to evaluate how useful each document is
        for supporting the counter-claim. Documents are scored 1-5, and only
        those above the configured threshold are kept.

        Args:
            counter_stmt: CounterStatement to evaluate against
            search_results: SearchResults with document IDs and provenance

        Returns:
            List of ScoredDocument objects (only those above threshold),
            sorted by score descending
        """
        doc_count = len(search_results.deduplicated_docs)
        logger.info(
            f"Scoring {doc_count} documents for counter-statement support"
        )

        if doc_count == 0:
            logger.warning("No documents to score")
            return []

        # Fetch full document data
        documents = self._fetch_documents(search_results.deduplicated_docs)

        if not documents:
            logger.warning("Failed to fetch any documents")
            return []

        # Build scoring question focused on counter-evidence
        scoring_question = self._build_scoring_question(counter_stmt)

        # Get configuration for batch processing
        scoring_config = self.agent_config.get("scoring", {})
        batch_size = scoring_config.get("batch_size", DEFAULT_SCORING_BATCH_SIZE)
        early_stop_count = scoring_config.get("early_stop_count", DEFAULT_EARLY_STOP_COUNT)

        # Score documents in batches
        scored_docs: List[ScoredDocument] = []
        doc_items = list(documents.items())
        total_batches = (len(doc_items) - 1) // batch_size + 1

        for batch_idx in range(0, len(doc_items), batch_size):
            batch = doc_items[batch_idx:batch_idx + batch_size]
            current_batch_num = batch_idx // batch_size + 1

            logger.debug(f"Scoring batch {current_batch_num}/{total_batches}")

            for doc_id, document in batch:
                try:
                    # Get provenance for this document
                    found_by = search_results.provenance.get(doc_id, [])

                    # Score using DocumentScoringAgent
                    scoring_result = self.scoring_agent.evaluate_document(
                        user_question=scoring_question,
                        document=document
                    )

                    score = scoring_result['score']
                    reasoning = scoring_result['reasoning']

                    # Skip if below threshold
                    if score < self.score_threshold:
                        logger.debug(
                            f"Doc {doc_id}: score={score} (below threshold {self.score_threshold})"
                        )
                        continue

                    # Create ScoredDocument
                    scored_doc = ScoredDocument(
                        doc_id=doc_id,
                        document=document,
                        score=score,
                        explanation=self._get_score_explanation(
                            score=score,
                            document=document,
                            reasoning=reasoning
                        ),
                        supports_counter=True,  # score >= threshold
                        found_by=found_by
                    )

                    scored_docs.append(scored_doc)

                    logger.debug(
                        f"Doc {doc_id}: score={score}, found_by={found_by}"
                    )

                except Exception as e:
                    logger.error(f"Failed to score document {doc_id}: {e}")
                    # Continue with other documents
                    continue

            # Early stopping if we have enough high-scoring documents
            if early_stop_count > 0 and len(scored_docs) >= early_stop_count:
                logger.info(
                    f"Early stopping: found {len(scored_docs)} documents "
                    f"above threshold (target: {early_stop_count})"
                )
                break

        logger.info(
            f"Scoring complete: {len(scored_docs)}/{len(documents)} documents "
            f"above threshold ({self.score_threshold})"
        )

        # Sort by score (descending)
        scored_docs.sort(key=lambda x: x.score, reverse=True)

        return scored_docs

    def _fetch_documents(self, doc_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        """
        Fetch full document data from database.

        Uses the DatabaseManager to retrieve document metadata including
        title, abstract, authors, publication year, journal, identifiers,
        and source information.

        Args:
            doc_ids: List of document IDs to fetch

        Returns:
            Dict mapping doc_id → document data dictionary
        """
        if not doc_ids:
            return {}

        try:
            db_manager = get_db_manager()
            with db_manager.get_connection() as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    # Use ANY for efficient batch query
                    cur.execute("""
                        SELECT
                            id, title, abstract, authors, publication_date,
                            publication AS journal, pmid, doi, source_id
                        FROM document
                        WHERE id = ANY(%s)
                    """, (doc_ids,))

                    results = cur.fetchall()

            # Convert to dict keyed by ID
            documents: Dict[int, Dict[str, Any]] = {}
            for row in results:
                doc_dict = dict(row)
                doc_id = doc_dict['id']
                documents[doc_id] = doc_dict

            logger.debug(f"Fetched {len(documents)}/{len(doc_ids)} documents from database")

            return documents

        except Exception as e:
            logger.error(f"Failed to fetch documents: {e}")
            # Return empty dict rather than raising to allow graceful degradation
            return {}

    def _build_scoring_question(self, counter_stmt: CounterStatement) -> str:
        """
        Build question for scoring documents in counter-evidence context.

        The question frames the scoring in terms of finding evidence that
        SUPPORTS the counter-statement (i.e., contradicts the original claim).

        Args:
            counter_stmt: CounterStatement object

        Returns:
            Question string for DocumentScoringAgent
        """
        return (
            f"Does this document provide evidence that supports or relates to "
            f"the following claim: {counter_stmt.negated_text}? "
            f"We are looking for evidence that contradicts: "
            f"{counter_stmt.original_statement.text}"
        )

    def _get_score_explanation(
        self,
        score: int,
        document: Dict[str, Any],
        reasoning: str
    ) -> str:
        """
        Generate explanation for document score.

        Combines the model's reasoning with the document title for context.

        Args:
            score: The relevance score (1-5)
            document: Document data dictionary
            reasoning: Reasoning from DocumentScoringAgent

        Returns:
            Explanation string
        """
        # Use the model's reasoning as the primary explanation
        explanation = reasoning

        # Add title context if not already mentioned
        title = document.get("title", "")
        if title and len(title) > 0:
            # Truncate long titles for readability
            display_title = title[:DEFAULT_EXPLANATION_TITLE_MAX_LEN]
            if len(title) > DEFAULT_EXPLANATION_TITLE_MAX_LEN:
                display_title += "..."

            explanation = f"{reasoning} (Title: \"{display_title}\")"

        return explanation

    def _extract_citations(
        self, counter_stmt: CounterStatement, scored_docs: List[ScoredDocument]
    ) -> List[ExtractedCitation]:
        """
        Step 5: Extract supporting citations from scored documents.

        Uses CitationFinderAgent to extract relevant passages.

        Args:
            counter_stmt: Counter-statement to find citations for
            scored_docs: Documents above score threshold

        Returns:
            List of ExtractedCitation objects

        Note:
            Full implementation in Step 09 (09_CITATION_EXTRACTION.md)
        """
        raise NotImplementedError("Implemented in Step 09")

    def _generate_counter_report(
        self,
        counter_stmt: CounterStatement,
        citations: List[ExtractedCitation],
        search_results: SearchResults,
        scored_docs: List[ScoredDocument]
    ) -> CounterReport:
        """
        Step 6: Generate counter-evidence report from citations.

        Synthesizes citations into a coherent counter-evidence report.

        Args:
            counter_stmt: Counter-statement being reported on
            citations: Extracted citations to include
            search_results: Original search results (for statistics)
            scored_docs: Scored documents (for statistics)

        Returns:
            CounterReport with synthesized evidence

        Note:
            Full implementation in Step 10 (10_COUNTER_REPORT_GENERATION.md)
        """
        raise NotImplementedError("Implemented in Step 10")

    def _analyze_verdict(
        self, statement: Statement, counter_report: CounterReport
    ) -> Verdict:
        """
        Step 7: Analyze verdict based on counter-evidence.

        Determines whether counter-evidence supports, contradicts,
        or is undecided about the original statement.

        Args:
            statement: Original statement being checked
            counter_report: Counter-evidence report

        Returns:
            Verdict with classification and rationale

        Note:
            Full implementation in Step 11 (11_VERDICT_ANALYSIS.md)
        """
        raise NotImplementedError("Implemented in Step 11")

    def _generate_overall_assessment(
        self, statements: List[Statement], verdicts: List[Verdict]
    ) -> str:
        """
        Step 8: Generate overall assessment across all statements.

        Aggregates individual verdicts into an overall assessment
        of the abstract's factual accuracy.

        Args:
            statements: All extracted statements
            verdicts: Verdicts for each statement

        Returns:
            Overall assessment text

        Note:
            Full implementation in Step 11 (11_VERDICT_ANALYSIS.md)
        """
        raise NotImplementedError("Implemented in Step 11")

    # ==================== UTILITIES ====================

    def _report_progress(
        self,
        callback: Optional[Callable[[str, float], None]],
        step_name: str,
        progress: float
    ) -> None:
        """
        Report progress to callback if provided.

        Args:
            callback: Optional progress callback function
            step_name: Name of current processing step
            progress: Progress fraction (0.0 to 1.0)
        """
        if callback:
            callback(step_name, progress)
        logger.debug(f"Progress: {step_name} ({progress*100:.0f}%)")

    @property
    def max_statements(self) -> int:
        """
        Maximum statements to extract from abstract.

        Returns:
            Configured maximum statements value
        """
        return self.agent_config.get("max_statements", DEFAULT_MAX_STATEMENTS)

    @property
    def search_config(self) -> Dict[str, Any]:
        """
        Search configuration for multi-strategy search.

        Returns:
            Search configuration dictionary with limits and parameters
        """
        return self.agent_config.get("search", {
            "semantic_limit": DEFAULT_SEMANTIC_LIMIT,
            "hyde_limit": DEFAULT_HYDE_LIMIT,
            "keyword_limit": DEFAULT_KEYWORD_LIMIT,
            "max_deduplicated": DEFAULT_MAX_DEDUPLICATED
        })

    @property
    def citation_config(self) -> Dict[str, Any]:
        """
        Citation extraction configuration.

        Returns:
            Citation configuration dictionary
        """
        return self.agent_config.get("citation", {
            "min_score": DEFAULT_MIN_CITATION_SCORE,
            "max_citations_per_statement": DEFAULT_MAX_CITATIONS_PER_STATEMENT
        })
