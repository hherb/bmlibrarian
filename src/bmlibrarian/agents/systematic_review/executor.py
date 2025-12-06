"""
SearchExecutor Component for SystematicReviewAgent

Executes search queries from a SearchPlan and aggregates results with deduplication.
Supports multiple search strategies: semantic, keyword, hybrid, and HyDE.

Features:
- Multi-strategy query execution
- Automatic result deduplication
- Source tracking per document
- Progress callbacks
- Batch processing support
- Error handling and recovery
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set, TYPE_CHECKING

from .data_models import (
    SearchPlan,
    PlannedQuery,
    ExecutedQuery,
    QueryType,
    PaperData,
    QueryEffectiveness,
    QueryFeedback,
)
from .config import (
    SystematicReviewConfig,
    get_systematic_review_config,
    DEFAULT_MAX_SEARCH_RESULTS,
)

if TYPE_CHECKING:
    from ...database import DatabaseManager

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Search result limits
DEFAULT_RESULTS_PER_QUERY = 100
MAX_RESULTS_PER_QUERY = 500
MIN_RESULTS_PER_QUERY = 10

# Similarity threshold for semantic search
DEFAULT_SIMILARITY_THRESHOLD = 0.3

# Retry configuration
MAX_QUERY_RETRIES = 3
RETRY_DELAY_SECONDS = 1.0


# =============================================================================
# Data Types
# =============================================================================

@dataclass
class SearchResult:
    """
    Result of executing a single search query.

    Attributes:
        query_id: ID of the executed query
        documents: List of documents found
        document_ids: Set of document IDs found
        execution_time_seconds: Time taken to execute
        success: Whether the query executed successfully
        error_message: Error message if query failed
    """

    query_id: str
    documents: List[Dict[str, Any]] = field(default_factory=list)
    document_ids: Set[int] = field(default_factory=set)
    execution_time_seconds: float = 0.0
    success: bool = True
    error_message: str = ""

    @property
    def count(self) -> int:
        """Number of documents found."""
        return len(self.document_ids)


@dataclass
class AggregatedResults:
    """
    Aggregated results from executing all queries in a search plan.

    Attributes:
        papers: Deduplicated list of papers
        paper_sources: Mapping of document_id to query_ids that found it
        total_before_dedup: Total results before deduplication
        executed_queries: List of ExecutedQuery records
        execution_time_seconds: Total execution time
    """

    papers: List[PaperData] = field(default_factory=list)
    paper_sources: Dict[int, List[str]] = field(default_factory=dict)
    total_before_dedup: int = 0
    executed_queries: List[ExecutedQuery] = field(default_factory=list)
    execution_time_seconds: float = 0.0

    @property
    def count(self) -> int:
        """Number of unique papers found."""
        return len(self.papers)

    @property
    def deduplication_rate(self) -> float:
        """Percentage of duplicates removed."""
        if self.total_before_dedup == 0:
            return 0.0
        return 1.0 - (self.count / self.total_before_dedup)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "total_papers": self.count,
            "total_before_dedup": self.total_before_dedup,
            "deduplication_rate": round(self.deduplication_rate * 100, 2),
            "execution_time_seconds": round(self.execution_time_seconds, 2),
            "queries_executed": len(self.executed_queries),
            "paper_sources": {
                str(doc_id): sources
                for doc_id, sources in self.paper_sources.items()
            },
        }


@dataclass
class PhasedSearchResults:
    """
    Results from two-phase search execution.

    Phase 1: Semantic/HyDE queries (high precision baseline)
    Phase 2: Keyword queries (deduped against Phase 1)

    Attributes:
        phase1_papers: Papers found by semantic/HyDE queries
        phase1_document_ids: Document IDs from Phase 1 (baseline set)
        phase2_papers: Papers found by keyword queries (after deduplication)
        phase2_new_ids: Document IDs from Phase 2 not in Phase 1
        all_papers: Combined deduplicated papers
        paper_sources: Which queries found each document
        executed_queries: All executed query records
        query_overlap_stats: Overlap statistics per keyword query
        execution_time_seconds: Total execution time
    """

    phase1_papers: List[PaperData] = field(default_factory=list)
    phase1_document_ids: Set[int] = field(default_factory=set)
    phase2_papers: List[PaperData] = field(default_factory=list)
    phase2_new_ids: Set[int] = field(default_factory=set)
    all_papers: List[PaperData] = field(default_factory=list)
    paper_sources: Dict[int, List[str]] = field(default_factory=dict)
    executed_queries: List[ExecutedQuery] = field(default_factory=list)
    query_overlap_stats: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    execution_time_seconds: float = 0.0

    @property
    def phase1_count(self) -> int:
        """Number of papers from Phase 1."""
        return len(self.phase1_papers)

    @property
    def phase2_new_count(self) -> int:
        """Number of new papers from Phase 2 (not in Phase 1)."""
        return len(self.phase2_new_ids)

    @property
    def total_count(self) -> int:
        """Total unique papers found."""
        return len(self.all_papers)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "phase1_count": self.phase1_count,
            "phase1_document_ids": list(self.phase1_document_ids),
            "phase2_new_count": self.phase2_new_count,
            "phase2_new_ids": list(self.phase2_new_ids),
            "total_count": self.total_count,
            "execution_time_seconds": round(self.execution_time_seconds, 2),
            "queries_executed": len(self.executed_queries),
            "query_overlap_stats": self.query_overlap_stats,
        }


# =============================================================================
# SearchExecutor Class
# =============================================================================

class SearchExecutor:
    """
    Executes search plans and aggregates results.

    Supports multiple search strategies including semantic, keyword,
    hybrid, and HyDE searches. Handles deduplication and source tracking.

    Attributes:
        config: Full agent configuration
        results_per_query: Maximum results to retrieve per query
        similarity_threshold: Minimum similarity for semantic searches

    Example:
        >>> executor = SearchExecutor()
        >>> plan = planner.generate_search_plan(criteria)
        >>> results = executor.execute_plan(plan)
        >>> print(f"Found {results.count} unique papers")
    """

    def __init__(
        self,
        config: Optional[SystematicReviewConfig] = None,
        results_per_query: int = DEFAULT_RESULTS_PER_QUERY,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        callback: Optional[Callable[[str, str], None]] = None,
        db_manager: Optional["DatabaseManager"] = None,
    ) -> None:
        """
        Initialize the SearchExecutor.

        Args:
            config: Optional full configuration. If None, loads from config system.
            results_per_query: Maximum results per query (default: 100)
            similarity_threshold: Minimum similarity for semantic search (default: 0.3)
            callback: Optional callback for progress updates
            db_manager: Optional database manager instance
        """
        self.config = config or get_systematic_review_config()
        self.results_per_query = max(
            MIN_RESULTS_PER_QUERY,
            min(results_per_query, MAX_RESULTS_PER_QUERY)
        )
        self.similarity_threshold = similarity_threshold
        self.callback = callback
        self._db_manager = db_manager

        # Lazy-loaded database manager
        self._initialized_db = False

        logger.info(
            f"SearchExecutor initialized: results_per_query={self.results_per_query}, "
            f"similarity_threshold={self.similarity_threshold}"
        )

    def _call_callback(self, event: str, data: str) -> None:
        """Call progress callback if registered."""
        if self.callback:
            try:
                self.callback(event, data)
            except Exception as e:
                logger.warning(f"Callback error: {e}")

    def _get_db_manager(self) -> "DatabaseManager":
        """
        Get or initialize database manager.

        Returns:
            DatabaseManager instance

        Raises:
            ConnectionError: If unable to connect to database
        """
        if self._db_manager is not None:
            return self._db_manager

        if not self._initialized_db:
            try:
                from bmlibrarian.database import get_db_manager
                self._db_manager = get_db_manager()
                self._initialized_db = True
            except ImportError as e:
                raise ConnectionError(f"Unable to import database module: {e}") from e
            except Exception as e:
                raise ConnectionError(f"Unable to connect to database: {e}") from e

        return self._db_manager

    # =========================================================================
    # Main Execution Methods
    # =========================================================================

    def execute_plan(
        self,
        plan: SearchPlan,
        use_pubmed: bool = True,
        use_medrxiv: bool = True,
        use_others: bool = True,
    ) -> AggregatedResults:
        """
        Execute all queries in a search plan.

        Args:
            plan: SearchPlan containing queries to execute
            use_pubmed: Include PubMed sources
            use_medrxiv: Include medRxiv sources
            use_others: Include other sources

        Returns:
            AggregatedResults with deduplicated papers and metadata

        Raises:
            ConnectionError: If unable to connect to database
        """
        self._call_callback("execution_started", f"Executing {len(plan.queries)} queries")
        start_time = time.time()

        # Track all results
        all_document_ids: Set[int] = set()
        paper_sources: Dict[int, List[str]] = {}
        executed_queries: List[ExecutedQuery] = []
        total_before_dedup = 0

        # Execute each query
        for i, query in enumerate(plan.queries):
            self._call_callback(
                "query_started",
                f"{query.query_text}"
            )

            result = self._execute_single_query(
                query,
                use_pubmed=use_pubmed,
                use_medrxiv=use_medrxiv,
                use_others=use_others,
            )

            # Track results
            total_before_dedup += result.count

            # Track which queries found which documents
            for doc_id in result.document_ids:
                if doc_id not in paper_sources:
                    paper_sources[doc_id] = []
                paper_sources[doc_id].append(query.query_id)

            # Add new document IDs
            new_docs = result.document_ids - all_document_ids
            all_document_ids.update(new_docs)

            # Record execution
            executed_queries.append(ExecutedQuery(
                planned_query=query,
                document_ids=list(result.document_ids),
                execution_time_seconds=result.execution_time_seconds,
                actual_results=result.count,
                error=result.error_message if not result.success else None,
            ))

            self._call_callback(
                "query_completed",
                f"Found {result.count} docs ({len(new_docs)} new)"
            )

        # Fetch full paper data for unique document IDs
        papers = self._fetch_paper_data(all_document_ids)

        execution_time = time.time() - start_time

        self._call_callback(
            "execution_completed",
            f"Found {len(papers)} unique papers in {execution_time:.2f}s"
        )

        logger.info(
            f"Search execution complete: {len(papers)} unique papers "
            f"from {total_before_dedup} total results "
            f"({len(plan.queries)} queries, {execution_time:.2f}s)"
        )

        return AggregatedResults(
            papers=papers,
            paper_sources=paper_sources,
            total_before_dedup=total_before_dedup,
            executed_queries=executed_queries,
            execution_time_seconds=execution_time,
        )

    def execute_single_query(
        self,
        query: PlannedQuery,
        use_pubmed: bool = True,
        use_medrxiv: bool = True,
        use_others: bool = True,
    ) -> SearchResult:
        """
        Execute a single query.

        Public method for executing individual queries outside of a plan.

        Args:
            query: PlannedQuery to execute
            use_pubmed: Include PubMed sources
            use_medrxiv: Include medRxiv sources
            use_others: Include other sources

        Returns:
            SearchResult with documents found
        """
        return self._execute_single_query(
            query,
            use_pubmed=use_pubmed,
            use_medrxiv=use_medrxiv,
            use_others=use_others,
        )

    def execute_phased_plan(
        self,
        plan: SearchPlan,
        use_pubmed: bool = True,
        use_medrxiv: bool = True,
        use_others: bool = True,
        max_phase2_no_overlap: int = 10,
    ) -> PhasedSearchResults:
        """
        Execute search plan in two phases for better relevance filtering.

        Phase 1: Execute semantic and HyDE queries first to establish a
                 high-quality baseline set of documents.

        Phase 2: Execute keyword queries, comparing results against Phase 1.
                 Queries with no overlap and no high-scoring results can be
                 flagged as ineffective.

        Args:
            plan: SearchPlan containing queries to execute
            use_pubmed: Include PubMed sources
            use_medrxiv: Include medRxiv sources
            use_others: Include other sources
            max_phase2_no_overlap: For keyword queries with no Phase 1 overlap,
                                   only fetch this many documents for scoring

        Returns:
            PhasedSearchResults with separated phase results and overlap stats
        """
        self._call_callback("phased_execution_started", f"Executing phased search")
        start_time = time.time()

        # Separate queries by type
        phase1_types = {QueryType.SEMANTIC, QueryType.HYDE, QueryType.HYBRID}
        phase2_types = {QueryType.KEYWORD}

        phase1_queries = [q for q in plan.queries if q.query_type in phase1_types]
        phase2_queries = [q for q in plan.queries if q.query_type in phase2_types]

        logger.info(
            f"Phased execution: {len(phase1_queries)} Phase 1 queries, "
            f"{len(phase2_queries)} Phase 2 queries"
        )

        # Track all results
        all_document_ids: Set[int] = set()
        paper_sources: Dict[int, List[str]] = {}
        executed_queries: List[ExecutedQuery] = []
        query_overlap_stats: Dict[str, Dict[str, Any]] = {}

        # =====================================================================
        # Phase 1: Semantic/HyDE queries (baseline)
        # =====================================================================
        self._call_callback("phase1_started", f"Phase 1: {len(phase1_queries)} semantic/HyDE queries")

        phase1_document_ids: Set[int] = set()

        for query in phase1_queries:
            self._call_callback("query_started", f"{query.query_text}")

            result = self._execute_single_query(
                query,
                use_pubmed=use_pubmed,
                use_medrxiv=use_medrxiv,
                use_others=use_others,
            )

            # Track Phase 1 document IDs (baseline)
            phase1_document_ids.update(result.document_ids)

            # Track which queries found which documents
            for doc_id in result.document_ids:
                if doc_id not in paper_sources:
                    paper_sources[doc_id] = []
                paper_sources[doc_id].append(query.query_id)

            all_document_ids.update(result.document_ids)

            executed_queries.append(ExecutedQuery(
                planned_query=query,
                document_ids=list(result.document_ids),
                execution_time_seconds=result.execution_time_seconds,
                actual_results=result.count,
                error=result.error_message if not result.success else None,
            ))

            self._call_callback(
                "query_completed",
                f"Found {result.count} docs"
            )

        # Fetch Phase 1 paper data
        phase1_papers = self._fetch_paper_data(phase1_document_ids)

        self._call_callback(
            "phase1_completed",
            f"Phase 1 complete: {len(phase1_document_ids)} unique documents"
        )

        # =====================================================================
        # Phase 2: Keyword queries (compare against baseline)
        # =====================================================================
        self._call_callback("phase2_started", f"Phase 2: {len(phase2_queries)} keyword queries")

        phase2_new_ids: Set[int] = set()

        for query in phase2_queries:
            self._call_callback("query_started", f"{query.query_text}")

            result = self._execute_single_query(
                query,
                use_pubmed=use_pubmed,
                use_medrxiv=use_medrxiv,
                use_others=use_others,
            )

            # Calculate overlap with Phase 1
            overlap_ids = result.document_ids & phase1_document_ids
            new_ids = result.document_ids - phase1_document_ids
            overlap_ratio = len(overlap_ids) / len(result.document_ids) if result.document_ids else 0.0

            # Store overlap statistics
            query_overlap_stats[query.query_id] = {
                "query_text": query.query_text,
                "total_found": len(result.document_ids),
                "overlap_with_phase1": len(overlap_ids),
                "new_documents": len(new_ids),
                "overlap_ratio": overlap_ratio,
                "has_overlap": len(overlap_ids) > 0,
            }

            # For queries with no overlap, we may want to limit how many we add
            # This implements the "only analyze top 10" for no-overlap queries
            if len(overlap_ids) == 0 and len(new_ids) > max_phase2_no_overlap:
                # Limit new IDs to avoid processing too many irrelevant documents
                # The caller can score these and determine if query is useful
                limited_new_ids = set(list(new_ids)[:max_phase2_no_overlap])
                query_overlap_stats[query.query_id]["limited_to"] = max_phase2_no_overlap
                query_overlap_stats[query.query_id]["warning"] = "No Phase 1 overlap - limited results"
                logger.info(
                    f"Query '{query.query_text}' has no Phase 1 overlap, "
                    f"limiting to {max_phase2_no_overlap} documents for scoring"
                )
                new_ids = limited_new_ids

            # Track new Phase 2 documents
            phase2_new_ids.update(new_ids)

            # Track sources for all documents
            for doc_id in result.document_ids:
                if doc_id not in paper_sources:
                    paper_sources[doc_id] = []
                paper_sources[doc_id].append(query.query_id)

            # Only add new IDs not already in Phase 1
            all_document_ids.update(new_ids)

            executed_queries.append(ExecutedQuery(
                planned_query=query,
                document_ids=list(result.document_ids),
                execution_time_seconds=result.execution_time_seconds,
                actual_results=result.count,
                error=result.error_message if not result.success else None,
            ))

            self._call_callback(
                "query_completed",
                f"Found {result.count} docs ({len(overlap_ids)} overlap, {len(new_ids)} new)"
            )

        # Fetch Phase 2 paper data (only new documents)
        phase2_papers = self._fetch_paper_data(phase2_new_ids)

        self._call_callback(
            "phase2_completed",
            f"Phase 2 complete: {len(phase2_new_ids)} new documents"
        )

        # Combine all papers
        all_papers = self._fetch_paper_data(all_document_ids)

        execution_time = time.time() - start_time

        self._call_callback(
            "phased_execution_completed",
            f"Total: {len(all_papers)} unique papers in {execution_time:.2f}s"
        )

        logger.info(
            f"Phased search complete: {len(phase1_document_ids)} Phase 1, "
            f"{len(phase2_new_ids)} new Phase 2, {len(all_papers)} total "
            f"({execution_time:.2f}s)"
        )

        return PhasedSearchResults(
            phase1_papers=phase1_papers,
            phase1_document_ids=phase1_document_ids,
            phase2_papers=phase2_papers,
            phase2_new_ids=phase2_new_ids,
            all_papers=all_papers,
            paper_sources=paper_sources,
            executed_queries=executed_queries,
            query_overlap_stats=query_overlap_stats,
            execution_time_seconds=execution_time,
        )

    # =========================================================================
    # Query Execution by Type
    # =========================================================================

    def _execute_single_query(
        self,
        query: PlannedQuery,
        use_pubmed: bool,
        use_medrxiv: bool,
        use_others: bool,
    ) -> SearchResult:
        """
        Execute a single query based on its type.

        Args:
            query: PlannedQuery to execute
            use_pubmed: Include PubMed sources
            use_medrxiv: Include medRxiv sources
            use_others: Include other sources

        Returns:
            SearchResult with documents found
        """
        start_time = time.time()

        try:
            if query.query_type == QueryType.SEMANTIC:
                result = self._execute_semantic_query(
                    query, use_pubmed, use_medrxiv, use_others
                )
            elif query.query_type == QueryType.KEYWORD:
                result = self._execute_keyword_query(
                    query, use_pubmed, use_medrxiv, use_others
                )
            elif query.query_type == QueryType.HYBRID:
                result = self._execute_hybrid_query(
                    query, use_pubmed, use_medrxiv, use_others
                )
            elif query.query_type == QueryType.HYDE:
                result = self._execute_hyde_query(
                    query, use_pubmed, use_medrxiv, use_others
                )
            else:
                logger.warning(f"Unknown query type: {query.query_type}")
                result = SearchResult(
                    query_id=query.query_id,
                    success=False,
                    error_message=f"Unknown query type: {query.query_type}",
                )

            result.execution_time_seconds = time.time() - start_time
            return result

        except Exception as e:
            logger.error(f"Query execution failed: {e}", exc_info=True)
            return SearchResult(
                query_id=query.query_id,
                success=False,
                error_message=str(e),
                execution_time_seconds=time.time() - start_time,
            )

    def _execute_semantic_query(
        self,
        query: PlannedQuery,
        use_pubmed: bool,
        use_medrxiv: bool,
        use_others: bool,
    ) -> SearchResult:
        """Execute a semantic similarity search."""
        try:
            from bmlibrarian.database import search_with_semantic

            # Perform semantic search
            # Note: search_with_semantic doesn't support source filtering
            # so we filter results after retrieval
            results = list(search_with_semantic(
                search_text=query.query_text,
                threshold=self.similarity_threshold,
                max_results=self.results_per_query,
            ))

            # Filter by source if specified
            if not (use_pubmed and use_medrxiv and use_others):
                results = self._filter_results_by_source(
                    results, use_pubmed, use_medrxiv, use_others
                )

            document_ids = {r.get('id') for r in results if r.get('id')}

            return SearchResult(
                query_id=query.query_id,
                documents=results,
                document_ids=document_ids,
                success=True,
            )

        except ImportError:
            logger.warning("search_with_semantic not available, falling back to hybrid")
            return self._execute_hybrid_query(
                query, use_pubmed, use_medrxiv, use_others
            )
        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return SearchResult(
                query_id=query.query_id,
                success=False,
                error_message=str(e),
            )

    def _execute_keyword_query(
        self,
        query: PlannedQuery,
        use_pubmed: bool,
        use_medrxiv: bool,
        use_others: bool,
    ) -> SearchResult:
        """Execute a keyword (tsquery) search."""
        try:
            from bmlibrarian.database import find_abstracts
            from bmlibrarian.agents.utils.query_syntax import fix_tsquery_syntax

            # Fix any syntax issues in the query
            fixed_query = fix_tsquery_syntax(query.query_text)

            # Perform keyword search
            results = list(find_abstracts(
                ts_query_str=fixed_query,
                max_rows=self.results_per_query,
                use_pubmed=use_pubmed,
                use_medrxiv=use_medrxiv,
                use_others=use_others,
                plain=False,  # Use to_tsquery format
            ))

            document_ids = {r.get('id') for r in results if r.get('id')}

            return SearchResult(
                query_id=query.query_id,
                documents=results,
                document_ids=document_ids,
                success=True,
            )

        except Exception as e:
            logger.error(f"Keyword search failed: {e}")
            return SearchResult(
                query_id=query.query_id,
                success=False,
                error_message=str(e),
            )

    def _execute_hybrid_query(
        self,
        query: PlannedQuery,
        use_pubmed: bool,
        use_medrxiv: bool,
        use_others: bool,
    ) -> SearchResult:
        """Execute a hybrid (semantic + keyword) search."""
        try:
            from bmlibrarian.database import search_hybrid
            from bmlibrarian.agents.utils.query_syntax import fix_tsquery_syntax

            # Fix query syntax for keyword component
            fixed_query = fix_tsquery_syntax(query.query_text)

            # Perform hybrid search
            results, _ = search_hybrid(
                search_text=query.query_text,  # Semantic search
                query_text=fixed_query,  # Keyword search
                use_pubmed=use_pubmed,
                use_medrxiv=use_medrxiv,
                use_others=use_others,
            )

            # Limit results
            results = results[:self.results_per_query]

            document_ids = {r.get('id') for r in results if r.get('id')}

            return SearchResult(
                query_id=query.query_id,
                documents=results,
                document_ids=document_ids,
                success=True,
            )

        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            return SearchResult(
                query_id=query.query_id,
                success=False,
                error_message=str(e),
            )

    def _execute_hyde_query(
        self,
        query: PlannedQuery,
        use_pubmed: bool,
        use_medrxiv: bool,
        use_others: bool,
    ) -> SearchResult:
        """Execute a HyDE (Hypothetical Document Embeddings) search."""
        try:
            from bmlibrarian.agents.utils.hyde_search import hyde_search
            import ollama as ollama_client

            # Create ollama client
            client = ollama_client

            # Perform HyDE search
            results = hyde_search(
                question=query.query_text,
                client=client,
                generation_model=self.config.model,
                embedding_model=self.config.embedding_model,
                max_results=self.results_per_query,
                num_hypothetical_docs=3,
                similarity_threshold=self.similarity_threshold,
            )

            document_ids = {r.get('id') for r in results if r.get('id')}

            return SearchResult(
                query_id=query.query_id,
                documents=results,
                document_ids=document_ids,
                success=True,
            )

        except ImportError:
            logger.warning("HyDE search not available, falling back to semantic")
            # Fall back to semantic search
            return self._execute_semantic_query(
                query, use_pubmed, use_medrxiv, use_others
            )
        except Exception as e:
            logger.error(f"HyDE search failed: {e}")
            return SearchResult(
                query_id=query.query_id,
                success=False,
                error_message=str(e),
            )

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _filter_results_by_source(
        self,
        results: List[Dict[str, Any]],
        use_pubmed: bool,
        use_medrxiv: bool,
        use_others: bool,
    ) -> List[Dict[str, Any]]:
        """
        Filter search results by source type.

        Args:
            results: List of document dictionaries
            use_pubmed: Include PubMed sources
            use_medrxiv: Include medRxiv sources
            use_others: Include other sources

        Returns:
            Filtered list of documents
        """
        if use_pubmed and use_medrxiv and use_others:
            return results

        filtered = []
        for doc in results:
            source_name = doc.get('source_name', '').lower()
            source_id = doc.get('source_id', 0)

            # PubMed source (source_id=1 or source_name contains 'pubmed')
            is_pubmed = source_id == 1 or 'pubmed' in source_name

            # medRxiv source (source_id=2 or source_name contains 'medrxiv')
            is_medrxiv = source_id == 2 or 'medrxiv' in source_name

            # Check if this document should be included
            if is_pubmed and use_pubmed:
                filtered.append(doc)
            elif is_medrxiv and use_medrxiv:
                filtered.append(doc)
            elif not is_pubmed and not is_medrxiv and use_others:
                filtered.append(doc)

        return filtered

    # =========================================================================
    # Data Retrieval
    # =========================================================================

    def _fetch_paper_data(
        self,
        document_ids: Set[int],
    ) -> List[PaperData]:
        """
        Fetch full paper data for document IDs.

        Args:
            document_ids: Set of document IDs to fetch

        Returns:
            List of PaperData objects
        """
        if not document_ids:
            return []

        try:
            from bmlibrarian.database import fetch_documents_by_ids

            documents = fetch_documents_by_ids(document_ids)

            papers = []
            for doc in documents:
                try:
                    paper = PaperData.from_database_row(doc)
                    papers.append(paper)
                except Exception as e:
                    logger.warning(
                        f"Failed to convert document {doc.get('id')}: {e}"
                    )

            return papers

        except Exception as e:
            logger.error(f"Failed to fetch paper data: {e}")
            return []

    def get_paper_by_id(
        self,
        document_id: int,
    ) -> Optional[PaperData]:
        """
        Fetch a single paper by document ID.

        Args:
            document_id: Document ID to fetch

        Returns:
            PaperData if found, None otherwise
        """
        papers = self._fetch_paper_data({document_id})
        return papers[0] if papers else None

    # =========================================================================
    # Statistics and Reporting
    # =========================================================================

    def get_execution_summary(
        self,
        results: AggregatedResults,
    ) -> str:
        """
        Generate human-readable execution summary.

        Args:
            results: AggregatedResults to summarize

        Returns:
            Formatted summary string
        """
        lines = [
            "Search Execution Summary",
            "=" * 40,
            f"Total unique papers: {results.count}",
            f"Total before deduplication: {results.total_before_dedup}",
            f"Deduplication rate: {results.deduplication_rate * 100:.1f}%",
            f"Total execution time: {results.execution_time_seconds:.2f}s",
            f"Queries executed: {len(results.executed_queries)}",
            "",
            "Query Results:",
        ]

        for eq in results.executed_queries:
            status = "✓" if eq.success else "✗"
            query_id = eq.planned_query.query_id
            lines.append(
                f"  {status} {query_id}: {eq.actual_results} results "
                f"({len(eq.document_ids)} unique) in {eq.execution_time_seconds:.2f}s"
            )
            if not eq.success:
                lines.append(f"      Error: {eq.error}")

        # Source coverage
        lines.append("")
        lines.append("Source Coverage:")
        multi_source = sum(1 for sources in results.paper_sources.values() if len(sources) > 1)
        single_source = results.count - multi_source
        lines.append(f"  Found by single query: {single_source}")
        lines.append(f"  Found by multiple queries: {multi_source}")

        return "\n".join(lines)
