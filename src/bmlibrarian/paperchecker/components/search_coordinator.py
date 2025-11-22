"""
Multi-strategy search coordinator for PaperChecker.

This module implements the SearchCoordinator component that executes semantic,
HyDE, and keyword-based search strategies for finding counter-evidence in the
literature database.

The component coordinates three parallel search strategies:
1. Semantic search: Embedding-based similarity search using pgvector
2. HyDE search: Match against hypothetical document embeddings
3. Keyword search: Traditional full-text search using PostgreSQL ts_vector

Results are deduplicated across strategies and provenance is tracked to show
which strategy found each document.

Example:
    >>> from bmlibrarian.paperchecker.components import SearchCoordinator
    >>> config = {"semantic_limit": 50, "hyde_limit": 50, "keyword_limit": 50}
    >>> coordinator = SearchCoordinator(config=config)
    >>> results = coordinator.search(counter_statement)
    >>> print(f"Found {len(results.deduplicated_docs)} unique documents")
"""

import logging
import time
from typing import Any, Dict, List, Optional, Set

from bmlibrarian.database import get_db_manager, DatabaseManager

from ..data_models import CounterStatement, SearchResults

logger = logging.getLogger(__name__)


# Configuration Constants (Golden Rule 2 - No magic numbers)
DEFAULT_SEMANTIC_LIMIT: int = 50
DEFAULT_HYDE_LIMIT: int = 50
DEFAULT_KEYWORD_LIMIT: int = 50
DEFAULT_MAX_DEDUPLICATED: int = 100
DEFAULT_EMBEDDING_MODEL: str = "snowflake-arctic-embed2:latest"
DEFAULT_SIMILARITY_THRESHOLD: float = 0.0  # Minimum similarity for semantic search
KEYWORD_SEARCH_OPERATOR: str = "|"  # OR operator for keyword search
# Database query timeout in milliseconds (5 minutes default)
# This prevents queries from hanging indefinitely on large embedding tables
DEFAULT_QUERY_TIMEOUT_MS: int = 300000  # 5 minutes


class SearchCoordinator:
    """
    Component for coordinating multi-strategy document search.

    Executes three parallel search strategies (semantic, HyDE, keyword)
    and combines results with deduplication and provenance tracking.

    The coordinator uses the bmlibrarian database manager for all database
    operations and the ollama library for embedding generation, following
    the project's golden rules.

    Attributes:
        config: Search configuration dictionary with limits
        db_manager: DatabaseManager instance for database operations
        embedding_model: Ollama model for generating embeddings
        ollama_host: Ollama server host URL
        semantic_limit: Maximum documents from semantic search
        hyde_limit: Maximum documents from HyDE search (per abstract)
        keyword_limit: Maximum documents from keyword search
        max_deduplicated: Maximum total deduplicated results

    Example:
        >>> config = {
        ...     "semantic_limit": 50,
        ...     "hyde_limit": 50,
        ...     "keyword_limit": 50,
        ...     "max_deduplicated": 100
        ... }
        >>> coordinator = SearchCoordinator(config=config)
        >>> results = coordinator.search(counter_statement)
    """

    def __init__(
        self,
        config: Dict[str, Any],
        db_connection: Optional[Any] = None,  # Legacy parameter, not used
        embedding_model: Optional[str] = None,  # Legacy - embedding done server-side
        ollama_host: Optional[str] = None  # Legacy - embedding done server-side
    ) -> None:
        """
        Initialize SearchCoordinator.

        Args:
            config: Search configuration with limits and parameters.
                   Expected keys: semantic_limit, hyde_limit, keyword_limit,
                                 max_deduplicated, query_timeout_ms
            db_connection: Legacy parameter, ignored. Uses DatabaseManager.
            embedding_model: Legacy parameter. Embedding is now done server-side
                           by PostgreSQL's ollama_embedding() function.
            ollama_host: Legacy parameter. Embedding is now done server-side.

        Note:
            Semantic and HyDE searches now use PostgreSQL's semantic_docsearch()
            function which handles embedding generation server-side using the
            HNSW index for fast approximate nearest neighbor search.
        """
        self.config = config

        # Get database manager (Golden Rule 5 - Use DatabaseManager)
        self.db_manager: DatabaseManager = get_db_manager()

        # Store embedding model for reference (actual model used by server-side function)
        self.embedding_model = config.get("embedding_model", DEFAULT_EMBEDDING_MODEL)

        # Extract limits from config with defaults (Golden Rule 2)
        self.semantic_limit: int = config.get("semantic_limit", DEFAULT_SEMANTIC_LIMIT)
        self.hyde_limit: int = config.get("hyde_limit", DEFAULT_HYDE_LIMIT)
        self.keyword_limit: int = config.get("keyword_limit", DEFAULT_KEYWORD_LIMIT)
        self.max_deduplicated: int = config.get("max_deduplicated", DEFAULT_MAX_DEDUPLICATED)
        self.query_timeout_ms: int = config.get("query_timeout_ms", DEFAULT_QUERY_TIMEOUT_MS)

        logger.info(
            f"Initialized SearchCoordinator with limits: "
            f"semantic={self.semantic_limit}, hyde={self.hyde_limit}, "
            f"keyword={self.keyword_limit}, max_deduplicated={self.max_deduplicated}, "
            f"query_timeout={self.query_timeout_ms}ms"
        )

    def search(self, counter_stmt: CounterStatement) -> SearchResults:
        """
        Execute multi-strategy search for counter-evidence.

        Runs semantic, HyDE, and keyword searches, then combines
        and deduplicates results with provenance tracking.

        Args:
            counter_stmt: Counter-statement with negated_text, hyde_abstracts,
                         and keywords for search.

        Returns:
            SearchResults with:
                - semantic_docs: Document IDs from semantic search
                - hyde_docs: Document IDs from HyDE search
                - keyword_docs: Document IDs from keyword search
                - deduplicated_docs: Unique IDs across all strategies
                - provenance: Map of doc_id -> strategies that found it
                - search_metadata: Timing and configuration info

        Raises:
            RuntimeError: If all search strategies fail
        """
        logger.info("Executing multi-strategy search")
        start_time = time.time()

        semantic_docs: List[int] = []
        hyde_docs: List[int] = []
        keyword_docs: List[int] = []
        errors: List[str] = []

        # Strategy 1: Semantic search
        try:
            semantic_start = time.time()
            semantic_docs = self.search_semantic(
                text=counter_stmt.negated_text,
                limit=self.semantic_limit
            )
            semantic_time = time.time() - semantic_start
            logger.info(
                f"Semantic search found {len(semantic_docs)} documents "
                f"in {semantic_time:.2f}s"
            )
        except Exception as e:
            error_msg = f"Semantic search failed: {e}"
            logger.error(error_msg)
            errors.append(error_msg)

        # Strategy 2: HyDE search
        try:
            hyde_start = time.time()
            hyde_docs = self.search_hyde(
                hyde_abstracts=counter_stmt.hyde_abstracts,
                limit=self.hyde_limit
            )
            hyde_time = time.time() - hyde_start
            logger.info(
                f"HyDE search found {len(hyde_docs)} documents "
                f"in {hyde_time:.2f}s"
            )
        except Exception as e:
            error_msg = f"HyDE search failed: {e}"
            logger.error(error_msg)
            errors.append(error_msg)

        # Strategy 3: Keyword search
        try:
            keyword_start = time.time()
            keyword_docs = self.search_keyword(
                keywords=counter_stmt.keywords,
                limit=self.keyword_limit
            )
            keyword_time = time.time() - keyword_start
            logger.info(
                f"Keyword search found {len(keyword_docs)} documents "
                f"in {keyword_time:.2f}s"
            )
        except Exception as e:
            error_msg = f"Keyword search failed: {e}"
            logger.error(error_msg)
            errors.append(error_msg)

        # Check that at least one strategy succeeded
        if not (semantic_docs or hyde_docs or keyword_docs):
            error_details = "; ".join(errors) if errors else "No results from any strategy"
            raise RuntimeError(f"All search strategies failed: {error_details}")

        # Create SearchResults with provenance tracking
        total_time = time.time() - start_time
        metadata = {
            "semantic_limit": self.semantic_limit,
            "hyde_limit": self.hyde_limit,
            "keyword_limit": self.keyword_limit,
            "embedding_model": self.embedding_model,
            "total_search_time_seconds": total_time,
            "errors": errors if errors else None
        }

        results = SearchResults.from_strategy_results(
            semantic=semantic_docs,
            hyde=hyde_docs,
            keyword=keyword_docs,
            metadata=metadata
        )

        # Apply deduplication limit with prioritization
        if len(results.deduplicated_docs) > self.max_deduplicated:
            logger.info(
                f"Limiting results from {len(results.deduplicated_docs)} "
                f"to {self.max_deduplicated}"
            )
            prioritized = self._prioritize_multi_strategy_docs(
                doc_ids=results.deduplicated_docs,
                provenance=results.provenance,
                limit=self.max_deduplicated
            )
            # Update results with prioritized list
            results = self._create_limited_results(
                results, prioritized
            )

        logger.info(
            f"Search complete: {len(results.deduplicated_docs)} unique documents "
            f"from {len(semantic_docs) + len(hyde_docs) + len(keyword_docs)} total "
            f"in {total_time:.2f}s"
        )

        return results

    def search_semantic(self, text: str, limit: int) -> List[int]:
        """
        Execute semantic (embedding-based) search.

        Uses the PostgreSQL semantic_docsearch() function which generates
        embeddings server-side and leverages the HNSW index for fast
        approximate nearest neighbor search.

        Args:
            text: Query text to search for
            limit: Maximum number of document IDs to return

        Returns:
            List of document IDs ordered by similarity (highest first)

        Raises:
            RuntimeError: If database query fails
        """
        logger.debug(f"Semantic search: text length={len(text)}, limit={limit}")

        # Use the PostgreSQL semantic_docsearch function which:
        # 1. Generates embeddings server-side via ollama_embedding()
        # 2. Uses HNSW index for fast search (sub-second)
        # 3. Returns document metadata directly
        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    # Set statement timeout to prevent indefinite hangs
                    cur.execute(
                        "SET LOCAL statement_timeout = %s",
                        (self.query_timeout_ms,)
                    )
                    logger.debug(
                        f"Set statement_timeout to {self.query_timeout_ms}ms "
                        f"for semantic search"
                    )

                    # Use semantic_docsearch function which handles embedding
                    # generation and uses HNSW index for fast search
                    # threshold=0.0 to get all results up to limit, sorted by score
                    cur.execute("""
                        SELECT DISTINCT document_id
                        FROM semantic_docsearch(%s, %s, %s)
                        ORDER BY score DESC
                    """, (text, DEFAULT_SIMILARITY_THRESHOLD, limit))

                    results = cur.fetchall()
                    doc_ids = [row[0] for row in results]

                    logger.debug(f"Semantic search returned {len(doc_ids)} documents")
                    return doc_ids

        except Exception as e:
            error_str = str(e).lower()
            if "statement timeout" in error_str or "canceling statement" in error_str:
                logger.warning(
                    f"Semantic search query timed out after {self.query_timeout_ms}ms"
                )
                # Return empty results on timeout - don't fail the entire search
                return []
            if "failed to generate embedding" in error_str:
                logger.warning(
                    f"Failed to generate embedding for semantic search: {e}"
                )
                return []
            logger.error(f"Semantic search database query failed: {e}")
            raise RuntimeError(f"Semantic search failed: {e}") from e

    def search_hyde(self, hyde_abstracts: List[str], limit: int) -> List[int]:
        """
        Execute HyDE (hypothetical document embedding) search.

        Uses the PostgreSQL semantic_docsearch() function for each hypothetical
        abstract. Results are deduplicated across all HyDE abstracts while
        preserving order.

        Args:
            hyde_abstracts: List of hypothetical abstracts to search with
            limit: Maximum documents to return per HyDE abstract

        Returns:
            List of unique document IDs found across all HyDE searches
        """
        if not hyde_abstracts:
            logger.warning("No HyDE abstracts provided, returning empty results")
            return []

        logger.debug(
            f"HyDE search: {len(hyde_abstracts)} abstracts, limit={limit} each"
        )

        all_docs: List[int] = []
        successful_searches = 0

        for i, hyde_abstract in enumerate(hyde_abstracts, 1):
            logger.debug(f"HyDE search {i}/{len(hyde_abstracts)}")

            try:
                # Use semantic_docsearch which handles embedding generation
                # server-side and uses HNSW index for fast search
                with self.db_manager.get_connection() as conn:
                    with conn.cursor() as cur:
                        # Set statement timeout to prevent indefinite hangs
                        cur.execute(
                            "SET LOCAL statement_timeout = %s",
                            (self.query_timeout_ms,)
                        )

                        cur.execute("""
                            SELECT DISTINCT document_id
                            FROM semantic_docsearch(%s, %s, %s)
                            ORDER BY score DESC
                        """, (hyde_abstract, DEFAULT_SIMILARITY_THRESHOLD, limit))

                        results = cur.fetchall()
                        doc_ids = [row[0] for row in results]
                        all_docs.extend(doc_ids)
                        successful_searches += 1

                        logger.debug(
                            f"HyDE search {i} returned {len(doc_ids)} documents"
                        )

            except Exception as e:
                error_str = str(e).lower()
                if "statement timeout" in error_str or "canceling statement" in error_str:
                    logger.warning(
                        f"HyDE search {i} timed out after {self.query_timeout_ms}ms, "
                        "continuing with next abstract"
                    )
                    continue
                if "failed to generate embedding" in error_str:
                    logger.warning(
                        f"Failed to generate embedding for HyDE abstract {i}"
                    )
                    continue
                logger.error(f"HyDE search {i} failed: {e}")
                continue

        if successful_searches == 0:
            logger.warning(
                "All HyDE searches failed or timed out. "
                "Returning empty results for HyDE strategy."
            )
            # Don't raise - continue with other strategies

        # Deduplicate while preserving order (first occurrence wins)
        seen: Set[int] = set()
        deduplicated: List[int] = []
        for doc_id in all_docs:
            if doc_id not in seen:
                seen.add(doc_id)
                deduplicated.append(doc_id)

        logger.debug(
            f"HyDE search found {len(deduplicated)} unique documents "
            f"from {successful_searches}/{len(hyde_abstracts)} successful searches"
        )

        return deduplicated

    def search_keyword(self, keywords: List[str], limit: int) -> List[int]:
        """
        Execute keyword (full-text) search.

        Uses PostgreSQL's full-text search capabilities with ts_vector
        and ts_rank_cd for relevance ranking.

        Args:
            keywords: List of search keywords (combined with OR logic)
            limit: Maximum number of document IDs to return

        Returns:
            List of document IDs ordered by relevance (highest first)

        Raises:
            RuntimeError: If database query fails
        """
        if not keywords:
            logger.warning("No keywords provided, returning empty results")
            return []

        logger.debug(f"Keyword search: {len(keywords)} keywords, limit={limit}")

        # Build ts_query from keywords using OR logic
        # Escape special characters and filter out invalid terms
        escaped_keywords = [
            self._escape_tsquery_term(kw) for kw in keywords
            if kw and kw.strip()
        ]
        # Filter out fallback terms that won't match anything useful
        escaped_keywords = [kw for kw in escaped_keywords if kw != "dummy_search_term"]

        if not escaped_keywords:
            logger.warning("No valid keywords after escaping, returning empty results")
            return []

        query_expression = f" {KEYWORD_SEARCH_OPERATOR} ".join(escaped_keywords)

        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    # Set statement timeout to prevent indefinite hangs
                    cur.execute(
                        "SET LOCAL statement_timeout = %s",
                        (self.query_timeout_ms,)
                    )

                    # Use full-text search with ts_rank_cd for ranking
                    cur.execute("""
                        SELECT id,
                               ts_rank_cd(
                                   search_vector,
                                   to_tsquery('english', %s)
                               ) AS rank
                        FROM document
                        WHERE search_vector @@ to_tsquery('english', %s)
                          AND abstract IS NOT NULL
                          AND abstract != ''
                        ORDER BY rank DESC
                        LIMIT %s
                    """, (query_expression, query_expression, limit))

                    results = cur.fetchall()
                    doc_ids = [row[0] for row in results]

                    logger.debug(f"Keyword search returned {len(doc_ids)} documents")
                    return doc_ids

        except Exception as e:
            error_str = str(e).lower()
            if "statement timeout" in error_str or "canceling statement" in error_str:
                logger.warning(
                    f"Keyword search query timed out after {self.query_timeout_ms}ms"
                )
                # Return empty results on timeout - don't fail the entire search
                return []
            logger.error(f"Keyword search failed: {e}")
            raise RuntimeError(f"Keyword search failed: {e}") from e

    def _escape_tsquery_term(self, term: str) -> str:
        """
        Escape and format a term for PostgreSQL tsquery.

        Handles special characters and multi-word terms.

        Args:
            term: Raw search term

        Returns:
            Escaped term safe for tsquery
        """
        # Remove special tsquery characters
        clean = term.strip()
        # Replace problematic characters
        clean = clean.replace("'", "")
        clean = clean.replace("&", "")
        clean = clean.replace("|", "")
        clean = clean.replace("!", "")
        clean = clean.replace("(", "")
        clean = clean.replace(")", "")
        clean = clean.replace(":", "")

        # Handle multi-word terms by converting spaces to AND
        if " " in clean:
            words = clean.split()
            # Filter out empty words
            words = [w for w in words if w]
            if words:
                return " & ".join(words)

        return clean if clean else "dummy_search_term"

    def _prioritize_multi_strategy_docs(
        self,
        doc_ids: List[int],
        provenance: Dict[int, List[str]],
        limit: int
    ) -> List[int]:
        """
        Prioritize documents found by multiple strategies.

        Documents found by more strategies are ranked higher, as they
        are more likely to be relevant across different search approaches.

        Args:
            doc_ids: All document IDs
            provenance: Mapping of doc_id -> list of strategies that found it
            limit: Maximum documents to return

        Returns:
            Limited list of doc IDs, prioritized by multi-strategy matches
        """
        # Sort by number of strategies (descending), then by doc_id for stability
        sorted_docs = sorted(
            doc_ids,
            key=lambda doc_id: (-len(provenance.get(doc_id, [])), doc_id)
        )

        return sorted_docs[:limit]

    def _create_limited_results(
        self,
        original: SearchResults,
        limited_docs: List[int]
    ) -> SearchResults:
        """
        Create a new SearchResults with limited deduplicated docs.

        Preserves the original strategy results but updates the
        deduplicated_docs and provenance to reflect the limit.

        Args:
            original: Original SearchResults object
            limited_docs: Limited list of document IDs

        Returns:
            New SearchResults with updated deduplicated_docs and provenance
        """
        limited_set = set(limited_docs)

        # Filter provenance to only include limited docs
        limited_provenance = {
            doc_id: strategies
            for doc_id, strategies in original.provenance.items()
            if doc_id in limited_set
        }

        return SearchResults(
            semantic_docs=original.semantic_docs,
            hyde_docs=original.hyde_docs,
            keyword_docs=original.keyword_docs,
            deduplicated_docs=limited_docs,
            provenance=limited_provenance,
            search_metadata={
                **original.search_metadata,
                "was_limited": True,
                "original_count": len(original.deduplicated_docs),
                "limited_count": len(limited_docs)
            }
        )

    def test_connection(self) -> bool:
        """
        Test connectivity to required services.

        Verifies that:
        1. Database connection is working
        2. semantic_docsearch function is available and working
           (tests both Ollama and pgvector integration)

        Returns:
            True if all connections are successful, False otherwise
        """
        try:
            # Test database connection and semantic_docsearch function
            # This tests: database, ollama_embedding(), and HNSW index
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    # Basic connection test
                    cur.execute("SELECT 1")
                    cur.fetchone()
                    logger.debug("Database connection test passed")

                    # Test semantic_docsearch function (tests Ollama + pgvector)
                    # Use a very short timeout for the test
                    cur.execute("SET LOCAL statement_timeout = '30s'")
                    cur.execute("""
                        SELECT document_id FROM semantic_docsearch(
                            'test connection', 0.9, 1
                        ) LIMIT 1
                    """)
                    cur.fetchall()  # Result doesn't matter, just verify no error
                    logger.debug("semantic_docsearch function test passed")

            logger.info("SearchCoordinator connection test passed")
            return True

        except Exception as e:
            error_str = str(e).lower()
            if "failed to generate embedding" in error_str:
                logger.error(
                    "Ollama embedding generation failed. "
                    "Check that Ollama is running and the embedding model is available."
                )
            elif "function semantic_docsearch" in error_str:
                logger.error(
                    "semantic_docsearch function not found. "
                    "Run migration 007_create_semantic_docsearch.sql"
                )
            else:
                logger.error(f"Connection test failed: {e}")
            return False
