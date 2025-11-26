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
)
from .config import (
    SystematicReviewConfig,
    get_systematic_review_config,
    DEFAULT_MAX_SEARCH_RESULTS,
    DEFAULT_MIN_SIMILARITY_THRESHOLD,
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
        similarity_threshold: float = DEFAULT_MIN_SIMILARITY_THRESHOLD,
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
                f"Query {i + 1}/{len(plan.queries)}: {query.query_type.value}"
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
                query_id=query.query_id,
                actual_query_text=query.query_text,
                results_count=result.count,
                new_documents_found=len(new_docs),
                execution_time_seconds=result.execution_time_seconds,
                success=result.success,
                error_message=result.error_message,
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
            from bmlibrarian.database import semantic_search

            # Perform semantic search
            results = semantic_search(
                search_text=query.query_text,
                threshold=self.similarity_threshold,
                max_results=self.results_per_query,
                use_pubmed=use_pubmed,
                use_medrxiv=use_medrxiv,
                use_others=use_others,
            )

            document_ids = {r.get('id') for r in results if r.get('id')}

            return SearchResult(
                query_id=query.query_id,
                documents=results,
                document_ids=document_ids,
                success=True,
            )

        except ImportError:
            logger.warning("semantic_search not available, falling back to hybrid")
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
            lines.append(
                f"  {status} {eq.query_id}: {eq.results_count} results "
                f"({eq.new_documents_found} new) in {eq.execution_time_seconds:.2f}s"
            )
            if not eq.success:
                lines.append(f"      Error: {eq.error_message}")

        # Source coverage
        lines.append("")
        lines.append("Source Coverage:")
        multi_source = sum(1 for sources in results.paper_sources.values() if len(sources) > 1)
        single_source = results.count - multi_source
        lines.append(f"  Found by single query: {single_source}")
        lines.append(f"  Found by multiple queries: {multi_source}")

        return "\n".join(lines)
