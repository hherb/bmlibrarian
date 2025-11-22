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
from bmlibrarian.config import get_ollama_host

from ..data_models import CounterStatement, SearchResults

# Import ollama library for embeddings (Golden Rule 4)
try:
    import ollama
except ImportError:
    ollama = None

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
        embedding_model: Optional[str] = None,
        ollama_host: Optional[str] = None
    ) -> None:
        """
        Initialize SearchCoordinator.

        Args:
            config: Search configuration with limits and parameters.
                   Expected keys: semantic_limit, hyde_limit, keyword_limit,
                                 max_deduplicated, embedding_model
            db_connection: Legacy parameter, ignored. Uses DatabaseManager.
            embedding_model: Ollama embedding model name (optional).
                           Defaults to config value or snowflake-arctic-embed2.
            ollama_host: Ollama server URL (optional).
                        Defaults to config value.

        Raises:
            ImportError: If ollama library is not installed
        """
        if ollama is None:
            raise ImportError(
                "ollama package required for SearchCoordinator. "
                "Install with: pip install ollama"
            )

        self.config = config

        # Get database manager (Golden Rule 5 - Use DatabaseManager)
        self.db_manager: DatabaseManager = get_db_manager()

        # Get Ollama configuration
        self.ollama_host = ollama_host or get_ollama_host()
        self.embedding_model = (
            embedding_model or
            config.get("embedding_model", DEFAULT_EMBEDDING_MODEL)
        )

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

        Generates an embedding for the input text using Ollama, then
        queries the database for documents with similar embeddings
        using pgvector cosine distance.

        Args:
            text: Query text to embed and search for
            limit: Maximum number of document IDs to return

        Returns:
            List of document IDs ordered by similarity (highest first)

        Raises:
            RuntimeError: If embedding generation or database query fails
        """
        logger.debug(f"Semantic search: text length={len(text)}, limit={limit}")

        # Generate embedding using ollama library (Golden Rule 4)
        embedding = self._generate_embedding(text)

        if not embedding:
            logger.warning("Failed to generate embedding, returning empty results")
            return []

        # Query database using DatabaseManager (Golden Rule 5)
        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    # Set statement timeout to prevent indefinite hangs
                    # This is critical for large embedding tables
                    cur.execute(
                        "SET LOCAL statement_timeout = %s",
                        (self.query_timeout_ms,)
                    )
                    logger.debug(
                        f"Set statement_timeout to {self.query_timeout_ms}ms "
                        f"for semantic search"
                    )

                    # Use pgvector cosine distance operator
                    # <=> returns cosine distance (0=identical, 2=opposite)
                    # We look for chunks with embeddings, then get distinct documents
                    cur.execute("""
                        SELECT DISTINCT c.document_id,
                               MIN(e.embedding <=> %s::vector) AS distance
                        FROM emb_1024 e
                        JOIN chunks c ON e.chunk_id = c.id
                        WHERE e.embedding IS NOT NULL
                        GROUP BY c.document_id
                        ORDER BY distance ASC
                        LIMIT %s
                    """, (embedding, limit))

                    results = cur.fetchall()
                    doc_ids = [row[0] for row in results]

                    logger.debug(f"Semantic search returned {len(doc_ids)} documents")
                    return doc_ids

        except Exception as e:
            error_str = str(e).lower()
            if "statement timeout" in error_str or "canceling statement" in error_str:
                logger.warning(
                    f"Semantic search query timed out after {self.query_timeout_ms}ms. "
                    "Consider optimizing the emb_1024 table with proper indexes "
                    "(e.g., CREATE INDEX ON emb_1024 USING ivfflat (embedding vector_cosine_ops))."
                )
                # Return empty results on timeout - don't fail the entire search
                return []
            logger.error(f"Semantic search database query failed: {e}")
            raise RuntimeError(f"Semantic search failed: {e}") from e

    def search_hyde(self, hyde_abstracts: List[str], limit: int) -> List[int]:
        """
        Execute HyDE (hypothetical document embedding) search.

        For each hypothetical abstract, generates an embedding and searches
        for similar documents. Results are deduplicated across all HyDE
        abstracts while preserving order.

        Args:
            hyde_abstracts: List of hypothetical abstracts to search with
            limit: Maximum documents to return per HyDE abstract

        Returns:
            List of unique document IDs found across all HyDE searches

        Raises:
            RuntimeError: If all HyDE searches fail
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
                # Generate embedding for HyDE abstract
                embedding = self._generate_embedding(hyde_abstract)

                if not embedding:
                    logger.warning(f"Failed to generate embedding for HyDE abstract {i}")
                    continue

                # Query database
                with self.db_manager.get_connection() as conn:
                    with conn.cursor() as cur:
                        # Set statement timeout to prevent indefinite hangs
                        cur.execute(
                            "SET LOCAL statement_timeout = %s",
                            (self.query_timeout_ms,)
                        )

                        cur.execute("""
                            SELECT DISTINCT c.document_id,
                                   MIN(e.embedding <=> %s::vector) AS distance
                            FROM emb_1024 e
                            JOIN chunks c ON e.chunk_id = c.id
                            WHERE e.embedding IS NOT NULL
                            GROUP BY c.document_id
                            ORDER BY distance ASC
                            LIMIT %s
                        """, (embedding, limit))

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

    def _generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for text using Ollama.

        Uses the ollama library for embedding generation (Golden Rule 4).

        Args:
            text: Text to embed

        Returns:
            Embedding vector as list of floats, or empty list on failure

        Note:
            Does not raise exceptions - returns empty list on failure
            to allow graceful degradation.
        """
        if not text or not text.strip():
            logger.warning("Empty text provided for embedding")
            return []

        try:
            # Use ollama library (Golden Rule 4 - no raw HTTP requests)
            response = ollama.embeddings(
                model=self.embedding_model,
                prompt=text
            )

            if "embedding" in response:
                embedding = response["embedding"]
                logger.debug(
                    f"Generated embedding with {len(embedding)} dimensions"
                )
                return embedding
            else:
                logger.error(f"Unexpected response format from Ollama: {response}")
                return []

        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            return []

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
        2. Ollama is reachable and embedding model is available

        Returns:
            True if all connections are successful, False otherwise
        """
        try:
            # Test database connection
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
                    logger.debug("Database connection test passed")

            # Test Ollama connection
            test_embedding = self._generate_embedding("test connection")
            if not test_embedding:
                logger.error("Ollama embedding test failed")
                return False

            logger.info("SearchCoordinator connection test passed")
            return True

        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False
