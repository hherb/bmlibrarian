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
import re
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
DEFAULT_MIN_CITATION_RELEVANCE: float = 0.7

# Counter-report generation constants
DEFAULT_REPORT_TEMPERATURE: float = 0.3
DEFAULT_REPORT_MAX_TOKENS: int = 4000
DEFAULT_MIN_REPORT_LENGTH: int = 50
REPORT_PREFIXES_TO_STRIP: tuple = (
    "Summary:",
    "Report:",
    "Counter-Evidence Summary:",
    "Here is the summary:",
    "Here's the summary:",
    "**Summary:**",
    "**Report:**",
)

# Report validation constants
CITATION_REFERENCE_PATTERN: str = r'\[\d+\]'
MIN_SENTENCE_LENGTH: int = 10
MIN_WORDS_FOR_DIVERSITY_CHECK: int = 20
MIN_LEXICAL_DIVERSITY_RATIO: float = 0.3
MAX_MARKDOWN_ISSUES_TO_REPORT: int = 3
# Patterns for detecting unclosed markdown at end of lines
# These are checked after stripping closed markers from each line
UNCLOSED_MARKDOWN_PATTERNS: tuple = (
    # Pattern, description for error message
    # Note: We only check for code blocks here, other markers are checked by counting
    (r'^\s*```\w*\s*$', 'code block opener without closer'),
)


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
        progress_callback: Optional[Callable[[str, float], None]] = None,
        data_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None
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
            data_callback: Optional callback(step_name, data_dict)
                          Called with intermediate results for audit trail/debugging.
                          data_dict contains step-specific data like extracted statements,
                          counter-statements, search results, etc.

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

            # Emit extracted statements data
            self._report_data(data_callback, "Extracting statements", {
                "statements": [
                    {"text": s.text, "type": s.statement_type, "index": i}
                    for i, s in enumerate(statements)
                ],
                "count": len(statements)
            })

            # Step 2: Generate counter-statements
            self._report_progress(progress_callback, "Generating counter-statements", 0.2)
            counter_statements = self._generate_counter_statements(statements)

            # Emit counter-statements data
            self._report_data(data_callback, "Generating counter-statements", {
                "counter_statements": [
                    {
                        "original": cs.original_statement.text,
                        "negated": cs.negated_text,
                        "keywords": cs.keywords[:5] if cs.keywords else [],
                        "hyde_count": len(cs.hyde_abstracts),
                        "index": i
                    }
                    for i, cs in enumerate(counter_statements)
                ],
                "count": len(counter_statements)
            })

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

                # Emit search results data
                self._report_data(data_callback, "Searching for counter-evidence", {
                    "statement_index": i,
                    "semantic_count": len(search_results.semantic_docs),
                    "hyde_count": len(search_results.hyde_docs),
                    "keyword_count": len(search_results.keyword_docs),
                    "deduplicated_count": len(search_results.deduplicated_docs),
                    "counter_statement": counter_stmt.negated_text[:100] + "..."
                    if len(counter_stmt.negated_text) > 100 else counter_stmt.negated_text
                })

                # Step 4: Score documents
                self._report_progress(
                    progress_callback,
                    f"Scoring documents ({i+1}/{num_statements})",
                    base_progress + 0.2
                )
                scored_docs = self._score_documents(counter_stmt, search_results)
                scored_docs_list.append(scored_docs)

                # Emit scoring results data
                self._report_data(data_callback, "Scoring documents", {
                    "statement_index": i,
                    "documents_scored": len(search_results.deduplicated_docs),
                    "documents_above_threshold": len(scored_docs),
                    "threshold": self.score_threshold,
                    "top_scores": [
                        {"doc_id": d.doc_id, "score": d.score, "title": d.document.get("title", "")[:50]}
                        for d in scored_docs[:5]
                    ] if scored_docs else []
                })

                # Step 5: Extract citations
                self._report_progress(
                    progress_callback,
                    f"Extracting citations ({i+1}/{num_statements})",
                    base_progress + 0.3
                )
                citations = self._extract_citations(counter_stmt, scored_docs)

                # Emit citations data
                self._report_data(data_callback, "Extracting citations", {
                    "statement_index": i,
                    "citations_extracted": len(citations),
                    "citations": [
                        {
                            "doc_id": c.doc_id,
                            "passage": c.passage[:150] + "..." if len(c.passage) > 150 else c.passage,
                            "score": c.relevance_score
                        }
                        for c in citations[:5]
                    ] if citations else []
                })

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

                # Emit counter-report data
                self._report_data(data_callback, "Generating counter-report", {
                    "statement_index": i,
                    "summary_length": len(counter_report.summary),
                    "num_citations": counter_report.num_citations,
                    "summary_preview": counter_report.summary[:200] + "..."
                    if len(counter_report.summary) > 200 else counter_report.summary
                })

                # Step 7: Analyze verdict
                self._report_progress(
                    progress_callback,
                    f"Analyzing verdict ({i+1}/{num_statements})",
                    base_progress + 0.5
                )
                verdict = self._analyze_verdict(stmt, counter_report)
                verdicts_list.append(verdict)

                # Emit verdict data
                self._report_data(data_callback, "Analyzing verdict", {
                    "statement_index": i,
                    "original_statement": stmt.text[:100] + "..." if len(stmt.text) > 100 else stmt.text,
                    "verdict": verdict.verdict,
                    "confidence": verdict.confidence,
                    "rationale": verdict.rationale
                })

            # Step 8: Overall assessment
            self._report_progress(progress_callback, "Generating overall assessment", 0.95)
            overall_assessment = self._generate_overall_assessment(
                statements, verdicts_list
            )

            # Emit overall assessment data
            self._report_data(data_callback, "Generating overall assessment", {
                "assessment": overall_assessment,
                "verdict_summary": {
                    "supports": sum(1 for v in verdicts_list if v.verdict == "supports"),
                    "contradicts": sum(1 for v in verdicts_list if v.verdict == "contradicts"),
                    "undecided": sum(1 for v in verdicts_list if v.verdict == "undecided")
                }
            })

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
        Step 5: Extract citations from high-scoring documents.

        Uses CitationFinderAgent to extract specific passages that support
        the counter-statement. Only documents above the min_citation_score
        are processed.

        Args:
            counter_stmt: CounterStatement being supported
            scored_docs: List of ScoredDocument objects (sorted by score descending)

        Returns:
            List of ExtractedCitation objects (ordered by relevance)

        Raises:
            RuntimeError: If citation extraction fails unrecoverably
        """
        logger.info(
            f"Extracting citations from {len(scored_docs)} scored documents "
            f"(min score: {self.min_citation_score})"
        )

        # Filter to documents above min_citation_score
        eligible_docs = [
            doc for doc in scored_docs
            if doc.score >= self.min_citation_score
        ]

        logger.info(f"{len(eligible_docs)} documents eligible for citation extraction")

        if not eligible_docs:
            logger.warning("No documents above min_citation_score for citation extraction")
            return []

        # Prepare for citation extraction
        extraction_question = self._build_extraction_question(counter_stmt)

        # Convert to format expected by CitationFinderAgent
        # CitationFinderAgent expects: List[Tuple[Dict, Dict]] where Dict is (document, scoring_result)
        scored_tuples = [
            (doc.document, {"score": doc.score, "reasoning": doc.explanation})
            for doc in eligible_docs
        ]

        # Cache citation config to avoid repeated property access
        citation_config = self.citation_config

        # Get max_citations limit from config
        max_citations = citation_config.get(
            "max_citations_per_statement", DEFAULT_MAX_CITATIONS_PER_STATEMENT
        )

        # Extract citations using CitationFinderAgent
        try:
            # Get min_relevance from config or use default
            min_relevance = citation_config.get(
                "min_relevance", DEFAULT_MIN_CITATION_RELEVANCE
            )

            # Use existing agent's batch extraction capability
            citation_results = self.citation_agent.process_scored_documents_for_citations(
                user_question=extraction_question,
                scored_documents=scored_tuples,
                score_threshold=self.min_citation_score,
                min_relevance=min_relevance
            )

            # Convert to ExtractedCitation objects
            citations: List[ExtractedCitation] = []

            # Pre-build doc_id → ScoredDocument mapping for O(1) lookup
            # This avoids O(n²) complexity when processing many citations
            scored_docs_map = {doc.doc_id: doc for doc in eligible_docs}

            for i, citation_obj in enumerate(citation_results, 1):
                # Find corresponding ScoredDocument for metadata
                doc_id = int(citation_obj.document_id)
                scored_doc = scored_docs_map.get(doc_id)

                if not scored_doc:
                    # This can happen if CitationFinderAgent returns a document_id
                    # that wasn't in our eligible_docs list (e.g., due to ID mismatch
                    # or if the agent hallucinated a document ID). The citation is
                    # skipped to maintain data integrity.
                    logger.warning(
                        f"Citation {i} references doc_id={doc_id} which is not in the "
                        f"eligible documents list ({len(eligible_docs)} docs). "
                        "This may indicate an ID mismatch or hallucinated reference. "
                        "Skipping this citation."
                    )
                    continue

                # Create ExtractedCitation
                citation = ExtractedCitation(
                    doc_id=doc_id,
                    passage=citation_obj.passage,
                    relevance_score=scored_doc.score,
                    full_citation=self._format_citation(scored_doc.document),
                    metadata=self._extract_metadata(scored_doc.document),
                    citation_order=len(citations) + 1
                )

                citations.append(citation)

                # Respect max_citations limit
                if len(citations) >= max_citations:
                    logger.info(f"Reached max_citations limit ({max_citations})")
                    break

            logger.info(f"Extracted {len(citations)} citations from {len(eligible_docs)} eligible documents")

            return citations

        except Exception as e:
            logger.error(f"Citation extraction failed: {e}", exc_info=True)
            raise RuntimeError(f"Failed to extract citations: {e}") from e

    def _build_extraction_question(self, counter_stmt: CounterStatement) -> str:
        """
        Build question for citation extraction in counter-evidence context.

        Frames the extraction to focus on passages that support the counter-claim.

        Args:
            counter_stmt: CounterStatement object

        Returns:
            Question string for CitationFinderAgent
        """
        return (
            f"Extract specific passages that provide evidence for this claim: "
            f"{counter_stmt.negated_text}. "
            f"We are looking for evidence that contradicts the statement: "
            f"{counter_stmt.original_statement.text}"
        )

    def _format_citation(self, document: Dict[str, Any]) -> str:
        """
        Format document as AMA-style citation.

        AMA (American Medical Association) format:
        Authors. Title. Journal. Year;Volume(Issue):Pages. DOI

        Args:
            document: Document data dict

        Returns:
            Formatted citation string
        """
        parts: List[str] = []

        # Authors (limit to first 3, then et al)
        authors = document.get("authors")
        if authors:
            if isinstance(authors, list):
                if len(authors) <= 3:
                    authors_str = ", ".join(authors)
                else:
                    authors_str = ", ".join(authors[:3]) + ", et al"
            else:
                authors_str = str(authors)
            parts.append(authors_str)

        # Title
        title = document.get("title")
        if title:
            parts.append(title)

        # Journal
        journal = document.get("journal") or document.get("publication")
        if journal:
            parts.append(journal)

        # Year (from publication_date)
        pub_date = document.get("publication_date")
        if pub_date:
            # Extract year from publication_date (could be "2023", "2023-01-15", etc.)
            year_str = str(pub_date)[:4] if pub_date else None
            if year_str and year_str.isdigit():
                parts.append(year_str)

        # DOI (if available)
        doi = document.get("doi")
        if doi:
            parts.append(f"doi:{doi}")

        # Join parts with periods
        if parts:
            return ". ".join(parts) + "."
        else:
            return "Citation information unavailable."

    def _extract_metadata(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract metadata from document for citation tracking.

        Args:
            document: Document data dict

        Returns:
            Metadata dict with pmid, doi, authors, year, journal, etc.
        """
        # Extract year from publication_date
        pub_date = document.get("publication_date")
        year = None
        if pub_date:
            year_str = str(pub_date)[:4]
            if year_str.isdigit():
                year = int(year_str)

        return {
            "pmid": document.get("pmid"),
            "doi": document.get("doi"),
            "authors": document.get("authors", []),
            "year": year,
            "journal": document.get("journal") or document.get("publication"),
            "title": document.get("title"),
            "source": document.get("source_id")
        }

    def _generate_counter_report(
        self,
        counter_stmt: CounterStatement,
        citations: List[ExtractedCitation],
        search_results: SearchResults,
        scored_docs: List[ScoredDocument]
    ) -> CounterReport:
        """
        Step 6: Generate counter-evidence report from citations.

        Synthesizes extracted citations into a coherent prose report that
        summarizes evidence supporting the counter-statement. Uses LLM to
        generate professional medical-style writing with inline citations.

        Args:
            counter_stmt: CounterStatement being reported on
            citations: List of ExtractedCitation objects to synthesize
            search_results: SearchResults for statistics (documents found per strategy)
            scored_docs: List of ScoredDocument for statistics (scoring results)

        Returns:
            CounterReport with prose summary, citations, and search statistics

        Raises:
            RuntimeError: If report generation fails after retries
        """
        logger.info(
            f"Generating counter-report from {len(citations)} citations"
        )

        if not citations:
            logger.warning("No citations available for report generation")
            return self._generate_empty_report(counter_stmt, search_results, scored_docs)

        # Build prompt for report generation
        prompt = self._build_report_prompt(counter_stmt, citations)

        try:
            # Generate report using LLM (via BaseAgent's ollama integration)
            response = self._call_llm_for_report(prompt)

            # Parse and clean response
            report_text = self._parse_report_response(response)

            # Calculate search statistics
            search_stats = self._calculate_search_stats(
                search_results, scored_docs, citations
            )

            # Create CounterReport
            counter_report = CounterReport(
                summary=report_text,
                num_citations=len(citations),
                citations=citations,
                search_stats=search_stats,
                generation_metadata={
                    "model": self.model,
                    "temperature": self.agent_config.get("temperature", DEFAULT_REPORT_TEMPERATURE),
                    "timestamp": datetime.now().isoformat()
                }
            )

            logger.info(
                f"Counter-report generated: {len(report_text)} characters, "
                f"{len(citations)} citations"
            )

            return counter_report

        except Exception as e:
            logger.error(f"Counter-report generation failed: {e}", exc_info=True)
            raise RuntimeError(f"Failed to generate counter-report: {e}") from e

    def _build_report_prompt(
        self,
        counter_stmt: CounterStatement,
        citations: List[ExtractedCitation]
    ) -> str:
        """
        Build prompt for counter-report generation.

        Constructs a detailed prompt that instructs the LLM to synthesize
        citations into a cohesive medical-style narrative with proper
        inline references.

        Args:
            counter_stmt: CounterStatement containing the claim to report on
            citations: List of ExtractedCitation objects with passages

        Returns:
            Formatted prompt string for LLM generation
        """
        # Format citations for prompt
        formatted_citations = []
        for i, citation in enumerate(citations, 1):
            formatted_citations.append(
                f"[{i}] {citation.passage}\n"
                f"    Source: {citation.full_citation}"
            )

        citations_text = "\n\n".join(formatted_citations)

        return f"""You are an expert medical researcher writing a systematic review section.

**Task:**
Write a concise summary (200-300 words) of the evidence that supports or relates to the following claim:

**Claim:** {counter_stmt.negated_text}

**Context:**
This claim is the counter-position to: "{counter_stmt.original_statement.text}"
You are summarizing evidence that may contradict or provide an alternative perspective on the original statement.

**Evidence Citations:**
{citations_text}

**Instructions:**
1. Synthesize the evidence into a coherent narrative
2. Reference citations using [1], [2], etc. inline
3. Use professional medical writing style
4. Include specific findings, statistics, and years when mentioned in citations
5. Do NOT use vague temporal references ("recent study") - use specific years
6. Do NOT overstate the evidence beyond what citations support
7. Do NOT add information not present in the citations
8. Organize by themes or study types if relevant
9. Note any limitations or contradictions within the evidence

**Writing Style:**
- Professional and objective tone
- Evidence-based assertions only
- Clear and concise
- Focus on findings, not methodology (unless crucial)
- Use present tense for established findings, past tense for specific studies

**Output Format:**
Write ONLY the summary text in markdown format. Do not include headers, do not add "Summary:" prefix. Just the prose with inline citations.

**Summary:**"""

    def _call_llm_for_report(self, prompt: str) -> str:
        """
        Call Ollama API for report generation using BaseAgent's method.

        Uses the inherited _generate_from_prompt method which properly
        interfaces with the Ollama library (following project guidelines).

        Args:
            prompt: The formatted prompt for report generation

        Returns:
            Raw response string from the LLM

        Raises:
            ConnectionError: If unable to connect to Ollama
            ValueError: If response is empty or invalid
        """
        try:
            # Use BaseAgent's _generate_from_prompt which uses ollama library
            response = self._generate_from_prompt(
                prompt,
                num_predict=self.agent_config.get(
                    "report_max_tokens", DEFAULT_REPORT_MAX_TOKENS
                ),
                temperature=self.agent_config.get(
                    "temperature", DEFAULT_REPORT_TEMPERATURE
                )
            )
            return response

        except (ConnectionError, ValueError) as e:
            logger.error(f"LLM call failed: {e}")
            raise RuntimeError(f"Report generation LLM call failed: {e}") from e

    def _parse_report_response(self, response: str) -> str:
        """
        Parse and clean LLM report response.

        Removes common prefixes, markdown code blocks, and validates
        that the report meets minimum length requirements, contains
        inline citations, has basic coherence, and has valid markdown.

        Args:
            response: Raw response string from LLM

        Returns:
            Cleaned report text

        Raises:
            ValueError: If generated report is too short, empty, or malformed
        """
        report = response.strip()

        # Remove common prefixes that LLMs sometimes add
        for prefix in REPORT_PREFIXES_TO_STRIP:
            if report.startswith(prefix):
                report = report[len(prefix):].strip()

        # Remove markdown code blocks if present
        if report.startswith("```markdown"):
            report = report[len("```markdown"):].strip()
            if report.endswith("```"):
                report = report[:-3].strip()
        elif report.startswith("```"):
            report = report[3:].strip()
            if report.endswith("```"):
                report = report[:-3].strip()

        # Validate minimum length
        if len(report) < DEFAULT_MIN_REPORT_LENGTH:
            raise ValueError(
                f"Generated report too short ({len(report)} chars, "
                f"minimum: {DEFAULT_MIN_REPORT_LENGTH})"
            )

        # Validate inline citation format presence
        self._validate_citation_format(report)

        # Basic coherence check
        self._validate_coherence(report)

        # Malformed markdown detection
        self._validate_markdown(report)

        return report

    def _validate_citation_format(self, report: str) -> None:
        """
        Validate that the report contains inline citations in [N] format.

        This is a warning-level validation because a report could potentially
        be valid without explicit citations (e.g., when summarizing general
        findings), but the absence of citations should be logged.

        Args:
            report: The report text to validate
        """
        citation_matches = re.findall(CITATION_REFERENCE_PATTERN, report)

        if not citation_matches:
            logger.warning(
                "Generated report does not contain inline citations [N] format. "
                "This may indicate the LLM did not follow formatting instructions."
            )
        else:
            # Validate citation numbers are sequential starting from 1
            citation_numbers = sorted(set(
                int(match[1:-1]) for match in citation_matches
            ))
            expected_numbers = list(range(1, len(citation_numbers) + 1))

            if citation_numbers != expected_numbers:
                missing = set(expected_numbers) - set(citation_numbers)
                if missing:
                    logger.warning(
                        f"Report citation numbers are not sequential. "
                        f"Missing: {sorted(missing)}. Found: {citation_numbers}"
                    )

    def _validate_coherence(self, report: str) -> None:
        """
        Perform basic coherence checks on the report.

        Validates that the report:
        - Contains complete sentences (ends with punctuation)
        - Has reasonable sentence structure
        - Is not just a fragment or list of keywords

        Args:
            report: The report text to validate

        Raises:
            ValueError: If report fails basic coherence checks
        """
        # Check for sentence-ending punctuation
        sentence_endings = re.findall(r'[.!?]', report)
        if not sentence_endings:
            raise ValueError(
                "Generated report appears to lack complete sentences. "
                "No sentence-ending punctuation (., !, ?) found."
            )

        # Split into sentences and check minimum structure
        sentences = re.split(r'[.!?]+', report)
        valid_sentences = [
            s.strip() for s in sentences
            if len(s.strip()) >= MIN_SENTENCE_LENGTH
        ]

        if len(valid_sentences) < 1:
            raise ValueError(
                f"Generated report lacks substantive sentences. "
                f"Found {len(sentences)} fragments but none meeting "
                f"minimum length ({MIN_SENTENCE_LENGTH} chars)."
            )

        # Check for excessive repetition (potential LLM loop)
        words = report.lower().split()
        if len(words) > MIN_WORDS_FOR_DIVERSITY_CHECK:
            unique_words = set(words)
            uniqueness_ratio = len(unique_words) / len(words)
            if uniqueness_ratio < MIN_LEXICAL_DIVERSITY_RATIO:
                logger.warning(
                    f"Generated report has low lexical diversity "
                    f"({uniqueness_ratio:.1%} unique words, threshold: "
                    f"{MIN_LEXICAL_DIVERSITY_RATIO:.0%}). "
                    "This may indicate repetitive or low-quality content."
                )

    def _validate_markdown(self, report: str) -> None:
        """
        Detect malformed markdown in the report.

        Checks for unclosed formatting that could cause rendering issues:
        - Unclosed bold (**text)
        - Unclosed italic (*text)
        - Unclosed inline code (`code)
        - Unclosed code blocks (```)

        Args:
            report: The report text to validate

        Raises:
            ValueError: If malformed markdown is detected
        """
        # Check each line for unclosed patterns
        lines = report.split('\n')
        issues: List[str] = []

        for line_num, line in enumerate(lines, 1):
            for pattern, description in UNCLOSED_MARKDOWN_PATTERNS:
                if re.search(pattern, line):
                    issues.append(f"Line {line_num}: {description}")

        # Check for overall unclosed code blocks
        code_block_count = report.count('```')
        if code_block_count % 2 != 0:
            issues.append(
                f"Mismatched code block delimiters: found {code_block_count} "
                "``` markers (should be even)"
            )

        if issues:
            # Log all issues for debugging before truncating for error message
            logger.debug(f"All markdown issues found: {issues}")
            # Limit error message to first N issues for readability
            issues_str = "; ".join(issues[:MAX_MARKDOWN_ISSUES_TO_REPORT])
            if len(issues) > MAX_MARKDOWN_ISSUES_TO_REPORT:
                issues_str += f" (and {len(issues) - MAX_MARKDOWN_ISSUES_TO_REPORT} more)"
            raise ValueError(f"Malformed markdown detected: {issues_str}")

    def _generate_empty_report(
        self,
        counter_stmt: CounterStatement,
        search_results: SearchResults,
        scored_docs: List[ScoredDocument]
    ) -> CounterReport:
        """
        Generate minimal report when no citations are available.

        Creates a structured report explaining that no substantial evidence
        was found while still providing search statistics.

        Args:
            counter_stmt: CounterStatement that was searched for
            search_results: SearchResults with document counts
            scored_docs: ScoredDocument list (may be empty)

        Returns:
            CounterReport with empty citations but populated statistics
        """
        search_stats = self._calculate_search_stats(
            search_results, scored_docs, []
        )

        summary = (
            f"No substantial evidence was found in the literature database to support "
            f"the counter-claim: \"{counter_stmt.negated_text}\". "
            f"The search identified {search_stats['documents_found']} potentially relevant "
            f"documents, but none scored above the relevance threshold of {self.score_threshold}."
        )

        return CounterReport(
            summary=summary,
            num_citations=0,
            citations=[],
            search_stats=search_stats,
            generation_metadata={
                "model": self.model,
                "timestamp": datetime.now().isoformat(),
                "empty_report": True
            }
        )

    def _calculate_search_stats(
        self,
        search_results: SearchResults,
        scored_docs: List[ScoredDocument],
        citations: List[ExtractedCitation]
    ) -> Dict[str, Any]:
        """
        Calculate search statistics for report metadata.

        Computes document counts across different pipeline stages
        and search strategies for transparency and reproducibility.

        Args:
            search_results: SearchResults with strategy-specific counts
            scored_docs: List of scored documents
            citations: List of extracted citations

        Returns:
            Dictionary with document counts and search strategy breakdown
        """
        return {
            "documents_found": len(search_results.deduplicated_docs),
            "documents_scored": len(scored_docs),
            "documents_cited": len(set(c.doc_id for c in citations)),
            "citations_extracted": len(citations),
            "search_strategies": {
                "semantic": len(search_results.semantic_docs),
                "hyde": len(search_results.hyde_docs),
                "keyword": len(search_results.keyword_docs)
            }
        }

    def _analyze_verdict(
        self, statement: Statement, counter_report: CounterReport
    ) -> Verdict:
        """
        Step 7: Analyze verdict based on counter-evidence.

        Uses VerdictAnalyzer to determine whether counter-evidence supports,
        contradicts, or is undecided about the original statement. The analyzer
        evaluates the counter-report's evidence and generates a verdict with
        confidence level and rationale.

        Args:
            statement: Original statement being checked
            counter_report: Counter-evidence report with summary and citations

        Returns:
            Verdict object with:
                - verdict: Classification ("supports", "contradicts", "undecided")
                - confidence: Evidence strength ("high", "medium", "low")
                - rationale: 2-3 sentence explanation
                - counter_report: Reference to analyzed report
                - analysis_metadata: Model and timing information

        Raises:
            RuntimeError: If verdict analysis fails after retries
        """
        try:
            verdict = self.verdict_analyzer.analyze(statement, counter_report)

            logger.info(
                f"Verdict: {verdict.verdict} ({verdict.confidence} confidence)\n"
                f"Rationale: {verdict.rationale}"
            )

            return verdict

        except RuntimeError as e:
            logger.error(f"Verdict analysis failed: {e}")
            raise
        except ValueError as e:
            logger.error(f"Verdict validation failed: {e}")
            raise RuntimeError(f"Verdict analysis validation failed: {e}") from e

    def _generate_overall_assessment(
        self, statements: List[Statement], verdicts: List[Verdict]
    ) -> str:
        """
        Step 8: Generate overall assessment across all statements.

        Uses VerdictAnalyzer to aggregate individual verdicts into a comprehensive
        assessment of the abstract's factual accuracy. The assessment considers:
        - Number of statements in each verdict category
        - Confidence levels of individual verdicts
        - Distribution of supports/contradicts/undecided

        Args:
            statements: All extracted Statement objects from the abstract
            verdicts: List of Verdict objects (one per statement)

        Returns:
            Overall assessment string summarizing findings across all statements

        Raises:
            ValueError: If statements and verdicts have different lengths
        """
        try:
            overall_assessment = self.verdict_analyzer.generate_overall_assessment(
                statements, verdicts
            )

            logger.info(f"Overall assessment generated: {overall_assessment[:100]}...")

            return overall_assessment

        except ValueError as e:
            logger.error(f"Overall assessment generation failed: {e}")
            raise

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

    def _report_data(
        self,
        callback: Optional[Callable[[str, Dict[str, Any]], None]],
        step_name: str,
        data: Dict[str, Any]
    ) -> None:
        """
        Report intermediate data to callback if provided.

        Used for audit trail and debugging - emits step-specific data
        that can be displayed in the GUI for visual debugging.

        Args:
            callback: Optional data callback function
            step_name: Name of current processing step
            data: Dictionary containing step-specific intermediate results
        """
        if callback:
            callback(step_name, data)
        logger.debug(f"Data: {step_name} - {list(data.keys())}")

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
            "max_citations_per_statement": DEFAULT_MAX_CITATIONS_PER_STATEMENT,
            "min_relevance": DEFAULT_MIN_CITATION_RELEVANCE
        })
