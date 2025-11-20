# Step 3: Core PaperCheckerAgent Structure

## Context

Data models (Step 1) and database schema (Step 2) are now defined. We need to create the core PaperCheckerAgent class that orchestrates the entire workflow.

## Objective

Create the foundational PaperCheckerAgent class that:
- Inherits from BaseAgent (BMLibrarian standard)
- Integrates with configuration system
- Provides public API for abstract checking
- Coordinates workflow steps
- Handles error recovery
- Supports queue-based batch processing

## Requirements

- Inherit from `bmlibrarian.agents.base.BaseAgent`
- Use configuration system (`get_model()`, `get_agent_config()`)
- Integrate with `AgentOrchestrator` for queue processing
- Implement connection testing
- Comprehensive logging
- Type hints throughout

## Implementation Location

Create: `src/bmlibrarian/paperchecker/agent.py`

## Class Structure

```python
"""
PaperChecker Agent for medical abstract fact-checking

This module implements PaperCheckerAgent, a sophisticated fact-checking system
for medical abstracts that validates research claims by systematically searching
for and analyzing contradictory evidence.
"""

from typing import Dict, List, Optional, Any, Callable
import logging
from datetime import datetime

from bmlibrarian.agents.base import BaseAgent
from bmlibrarian.agents.orchestrator import AgentOrchestrator
from bmlibrarian.agents.scoring_agent import DocumentScoringAgent
from bmlibrarian.agents.citation_agent import CitationFinderAgent
from bmlibrarian.cli.config import get_config, get_model, get_agent_config

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


class PaperCheckerAgent(BaseAgent):
    """
    Agent for fact-checking medical abstracts through systematic counter-evidence search

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

    Args:
        orchestrator: Optional AgentOrchestrator for queue-based processing
        config: Optional configuration dict (uses ~/.bmlibrarian/config.json if None)
        db_connection: Optional database connection (creates new if None)

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
        db_connection = None
    ):
        """Initialize PaperCheckerAgent with configuration and dependencies"""

        # Load configuration
        self.config = config or get_config()
        self.agent_config = get_agent_config("paper_checker", self.config)

        # Initialize base agent
        super().__init__(
            orchestrator=orchestrator,
            model=get_model("paper_checker", self.config),
            **self._filter_agent_params(self.agent_config)
        )

        # Database connection
        self.db = db_connection or PaperCheckDB()

        # Initialize sub-components
        self._init_components()

        # Initialize existing BMLibrarian agents
        self._init_bmlibrarian_agents()

        logger.info(
            f"Initialized PaperCheckerAgent with model={self.model}, "
            f"max_statements={self.max_statements}"
        )

    def _filter_agent_params(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Filter config to only include BaseAgent-supported parameters"""
        supported = {"temperature", "top_p", "max_tokens", "timeout"}
        return {k: v for k, v in config.items() if k in supported}

    def _init_components(self):
        """Initialize PaperChecker sub-components"""
        self.statement_extractor = StatementExtractor(
            model=self.model,
            max_statements=self.agent_config.get("max_statements", 2),
            temperature=self.agent_config.get("temperature", 0.3)
        )

        self.counter_generator = CounterStatementGenerator(
            model=self.model,
            temperature=self.agent_config.get("temperature", 0.3)
        )

        self.hyde_generator = HyDEGenerator(
            model=self.model,
            num_abstracts=self.agent_config.get("hyde", {}).get("num_abstracts", 2),
            max_keywords=self.agent_config.get("hyde", {}).get("max_keywords", 10),
            temperature=self.agent_config.get("temperature", 0.3)
        )

        self.search_coordinator = SearchCoordinator(
            config=self.agent_config.get("search", {}),
            db_connection=self.db.conn
        )

        self.verdict_analyzer = VerdictAnalyzer(
            model=self.model,
            temperature=self.agent_config.get("temperature", 0.3)
        )

    def _init_bmlibrarian_agents(self):
        """Initialize existing BMLibrarian agents for reuse"""
        self.scoring_agent = DocumentScoringAgent(
            orchestrator=self.orchestrator
        )

        self.citation_agent = CitationFinderAgent(
            orchestrator=self.orchestrator
        )

        # Get scoring threshold from config
        self.score_threshold = self.agent_config.get("score_threshold", 3.0)
        self.min_citation_score = self.agent_config.get("citation", {}).get("min_score", 3)

    # ==================== PUBLIC API ====================

    def check_abstract(
        self,
        abstract: str,
        source_metadata: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable[[str, float], None]] = None
    ) -> PaperCheckResult:
        """
        Check a single abstract for factual accuracy

        Args:
            abstract: The abstract text to check
            source_metadata: Optional metadata (pmid, doi, title, etc.)
            progress_callback: Optional callback(step_name, progress_fraction)

        Returns:
            PaperCheckResult with complete analysis

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
            search_results_list = []
            scored_docs_list = []
            counter_reports_list = []
            verdicts_list = []

            for i, (stmt, counter_stmt) in enumerate(zip(statements, counter_statements)):
                logger.info(f"Processing statement {i+1}/{len(statements)}")
                base_progress = 0.2 + (i / len(statements)) * 0.7

                # Step 3: Multi-strategy search
                self._report_progress(
                    progress_callback,
                    f"Searching for counter-evidence ({i+1}/{len(statements)})",
                    base_progress + 0.1
                )
                search_results = self._search_counter_evidence(counter_stmt)
                search_results_list.append(search_results)

                # Step 4: Score documents
                self._report_progress(
                    progress_callback,
                    f"Scoring documents ({i+1}/{len(statements)})",
                    base_progress + 0.2
                )
                scored_docs = self._score_documents(counter_stmt, search_results)
                scored_docs_list.append(scored_docs)

                # Step 5: Extract citations
                self._report_progress(
                    progress_callback,
                    f"Extracting citations ({i+1}/{len(statements)})",
                    base_progress + 0.3
                )
                citations = self._extract_citations(counter_stmt, scored_docs)

                # Step 6: Generate counter-report
                self._report_progress(
                    progress_callback,
                    f"Generating counter-report ({i+1}/{len(statements)})",
                    base_progress + 0.4
                )
                counter_report = self._generate_counter_report(
                    counter_stmt, citations, search_results, scored_docs
                )
                counter_reports_list.append(counter_report)

                # Step 7: Analyze verdict
                self._report_progress(
                    progress_callback,
                    f"Analyzing verdict ({i+1}/{len(statements)})",
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
        Check multiple abstracts in batch (queue-based processing)

        Args:
            abstracts: List of dicts with 'abstract' and optional 'metadata' keys
            progress_callback: Optional callback(completed, total)

        Returns:
            List of PaperCheckResult objects
        """
        logger.info(f"Starting batch check of {len(abstracts)} abstracts")
        results = []

        for i, item in enumerate(abstracts, 1):
            try:
                result = self.check_abstract(
                    abstract=item["abstract"],
                    source_metadata=item.get("metadata", {})
                )
                results.append(result)

                if progress_callback:
                    progress_callback(i, len(abstracts))

            except Exception as e:
                logger.error(f"Failed to check abstract {i}: {e}")
                # Continue with next abstract
                continue

        logger.info(f"Batch check complete: {len(results)}/{len(abstracts)} successful")
        return results

    def test_connection(self) -> bool:
        """Test connectivity to all required services"""
        try:
            # Test Ollama connection
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

    # ==================== WORKFLOW STEPS ====================
    # These methods will be implemented in subsequent steps (04-11)

    def _extract_statements(self, abstract: str) -> List[Statement]:
        """Step 1: Extract core statements from abstract (see Step 04)"""
        raise NotImplementedError("Implemented in Step 04")

    def _generate_counter_statements(
        self, statements: List[Statement]
    ) -> List[CounterStatement]:
        """Step 2: Generate counter-statements (see Step 05)"""
        raise NotImplementedError("Implemented in Step 05")

    def _search_counter_evidence(
        self, counter_stmt: CounterStatement
    ) -> SearchResults:
        """Step 3: Multi-strategy search (see Step 07)"""
        raise NotImplementedError("Implemented in Step 07")

    def _score_documents(
        self, counter_stmt: CounterStatement, search_results: SearchResults
    ) -> List[ScoredDocument]:
        """Step 4: Score documents for relevance (see Step 08)"""
        raise NotImplementedError("Implemented in Step 08")

    def _extract_citations(
        self, counter_stmt: CounterStatement, scored_docs: List[ScoredDocument]
    ) -> List[ExtractedCitation]:
        """Step 5: Extract supporting citations (see Step 09)"""
        raise NotImplementedError("Implemented in Step 09")

    def _generate_counter_report(
        self,
        counter_stmt: CounterStatement,
        citations: List[ExtractedCitation],
        search_results: SearchResults,
        scored_docs: List[ScoredDocument]
    ) -> CounterReport:
        """Step 6: Generate counter-evidence report (see Step 10)"""
        raise NotImplementedError("Implemented in Step 10")

    def _analyze_verdict(
        self, statement: Statement, counter_report: CounterReport
    ) -> Verdict:
        """Step 7: Analyze verdict (see Step 11)"""
        raise NotImplementedError("Implemented in Step 11")

    def _generate_overall_assessment(
        self, statements: List[Statement], verdicts: List[Verdict]
    ) -> str:
        """Step 8: Generate overall assessment (see Step 11)"""
        raise NotImplementedError("Implemented in Step 11")

    # ==================== UTILITIES ====================

    def _report_progress(
        self,
        callback: Optional[Callable[[str, float], None]],
        step_name: str,
        progress: float
    ):
        """Report progress to callback if provided"""
        if callback:
            callback(step_name, progress)
        logger.debug(f"Progress: {step_name} ({progress*100:.0f}%)")

    @property
    def max_statements(self) -> int:
        """Maximum statements to extract from abstract"""
        return self.agent_config.get("max_statements", 2)
```

## Configuration Integration

Add to `~/.bmlibrarian/config.json`:

```json
{
  "paper_checker": {
    "model": "gpt-oss:20b",
    "temperature": 0.3,
    "top_p": 0.9,
    "max_statements": 2,
    "score_threshold": 3.0,
    "search": {
      "semantic_limit": 50,
      "hyde_limit": 50,
      "keyword_limit": 50,
      "max_deduplicated": 100
    },
    "citation": {
      "min_score": 3,
      "max_citations_per_statement": 10
    },
    "hyde": {
      "num_abstracts": 2,
      "max_keywords": 10
    }
  }
}
```

## Module Exports

Update `src/bmlibrarian/paperchecker/__init__.py`:

```python
"""
PaperChecker module for medical abstract fact-checking

This module provides sophisticated fact-checking for medical abstracts through
systematic counter-evidence search and analysis.
"""

from .agent import PaperCheckerAgent
from .data_models import (
    Statement, CounterStatement, SearchResults, ScoredDocument,
    ExtractedCitation, CounterReport, Verdict, PaperCheckResult
)
from .database import PaperCheckDB

__all__ = [
    "PaperCheckerAgent",
    "Statement",
    "CounterStatement",
    "SearchResults",
    "ScoredDocument",
    "ExtractedCitation",
    "CounterReport",
    "Verdict",
    "PaperCheckResult",
    "PaperCheckDB"
]

__version__ = "0.1.0"
```

## Testing Criteria

Create `tests/test_paperchecker_agent.py`:

1. **Test initialization**:
   - Agent initializes with default config
   - Agent initializes with custom config
   - Sub-components initialized correctly
   - BMLibrarian agents initialized

2. **Test configuration**:
   - Loads config from file correctly
   - Filters agent parameters correctly
   - Configuration values accessible

3. **Test connection testing**:
   - test_connection() works
   - Detects Ollama failures
   - Detects database failures

4. **Test public API**:
   - check_abstract() raises ValueError on empty input
   - check_abstracts_batch() processes multiple abstracts
   - Progress callbacks invoked correctly

5. **Test error handling**:
   - Graceful degradation on component failures
   - Proper exception propagation
   - Logging of errors

## Success Criteria

- [ ] PaperCheckerAgent class created inheriting from BaseAgent
- [ ] Configuration integration working
- [ ] All sub-components initialized
- [ ] BMLibrarian agents (scoring, citation) integrated
- [ ] Public API defined (check_abstract, check_abstracts_batch)
- [ ] Connection testing implemented
- [ ] Progress reporting functional
- [ ] Error handling comprehensive
- [ ] Module exports configured
- [ ] All unit tests passing

## Next Steps

After completing this step, proceed to:
- **Step 4**: Statement Extraction (04_STATEMENT_EXTRACTION.md)
- Implement the `_extract_statements()` method and StatementExtractor component
