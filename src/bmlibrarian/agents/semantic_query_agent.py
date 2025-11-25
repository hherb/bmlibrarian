"""
Semantic Query Agent for BMLibrarian.

Provides adaptive semantic search with:
- Progressive threshold adjustment (lower on no results, higher on too many)
- Query rephrasing when initial queries fail to find relevant content
- Configurable retry limits and threshold bounds

This agent is designed to be reusable across modules that need semantic search,
including document Q&A, citation finding, and literature search.

Example usage:
    from bmlibrarian.agents.semantic_query_agent import SemanticQueryAgent

    agent = SemanticQueryAgent()

    # Search with adaptive threshold and query rephrasing
    results = agent.search_document(
        document_id=12345,
        query="How was quality assessment performed?",
        min_results=1,
        max_results=5,
    )

    if results.success:
        for chunk in results.chunks:
            print(f"Score {chunk.score:.3f}: {chunk.text[:100]}...")
    else:
        print(f"Search failed: {results.message}")
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from bmlibrarian.database import DatabaseManager

logger = logging.getLogger(__name__)

# Default configuration constants
DEFAULT_INITIAL_THRESHOLD = 0.5
DEFAULT_MIN_THRESHOLD = 0.2  # Don't go below this - results become noise
DEFAULT_MAX_THRESHOLD = 0.8  # Don't go above this - too restrictive
DEFAULT_THRESHOLD_STEP = 0.1  # How much to adjust threshold each iteration
DEFAULT_MAX_RESULTS = 5
DEFAULT_MIN_RESULTS = 1
DEFAULT_MAX_THRESHOLD_ITERATIONS = 5  # Max attempts to adjust threshold
DEFAULT_MAX_QUERY_REPHRASINGS = 3  # Max query variations to try

# LLM configuration for query rephrasing
DEFAULT_REPHRASING_MODEL = "medgemma4B_it_q8:latest"  # Fast model for rephrasing
DEFAULT_REPHRASING_TEMPERATURE = 0.7  # Some creativity for variations


@dataclass
class ChunkResult:
    """A single chunk returned from semantic search."""

    chunk_id: int
    chunk_no: int
    score: float
    text: str

    def __repr__(self) -> str:
        """Return a concise representation."""
        preview = self.text[:50] + "..." if len(self.text) > 50 else self.text
        return f"ChunkResult(no={self.chunk_no}, score={self.score:.3f}, text='{preview}')"


@dataclass
class SemanticSearchResult:
    """Result from adaptive semantic search."""

    success: bool
    chunks: List[ChunkResult] = field(default_factory=list)
    query_used: str = ""
    threshold_used: float = 0.0
    iterations: int = 0
    queries_tried: List[str] = field(default_factory=list)
    thresholds_tried: List[float] = field(default_factory=list)
    message: str = ""

    @property
    def chunk_count(self) -> int:
        """Number of chunks found."""
        return len(self.chunks)

    def __repr__(self) -> str:
        """Return a concise representation."""
        return (
            f"SemanticSearchResult(success={self.success}, "
            f"chunks={self.chunk_count}, threshold={self.threshold_used:.2f}, "
            f"iterations={self.iterations})"
        )


class SemanticQueryAgent:
    """
    Adaptive semantic search agent.

    Handles progressive threshold adjustment and query rephrasing to maximize
    the chances of finding relevant content while maintaining result quality.

    Strategy:
    1. Start with initial threshold
    2. If no results: lower threshold and retry
    3. If too many results: raise threshold and retry
    4. If threshold adjustments exhausted: try rephrasing the query
    5. Repeat until success or all retries exhausted
    """

    def __init__(
        self,
        initial_threshold: float = DEFAULT_INITIAL_THRESHOLD,
        min_threshold: float = DEFAULT_MIN_THRESHOLD,
        max_threshold: float = DEFAULT_MAX_THRESHOLD,
        threshold_step: float = DEFAULT_THRESHOLD_STEP,
        max_threshold_iterations: int = DEFAULT_MAX_THRESHOLD_ITERATIONS,
        max_query_rephrasings: int = DEFAULT_MAX_QUERY_REPHRASINGS,
        rephrasing_model: Optional[str] = None,
        rephrasing_temperature: float = DEFAULT_REPHRASING_TEMPERATURE,
        ollama_host: Optional[str] = None,
    ) -> None:
        """
        Initialize the semantic query agent.

        Args:
            initial_threshold: Starting similarity threshold (0.0-1.0).
            min_threshold: Lowest threshold to try.
            max_threshold: Highest threshold to try.
            threshold_step: Amount to adjust threshold per iteration.
            max_threshold_iterations: Max threshold adjustment attempts per query.
            max_query_rephrasings: Max query variations to generate and try.
            rephrasing_model: LLM model for query rephrasing.
            rephrasing_temperature: Temperature for rephrasing generation.
            ollama_host: Ollama server URL.
        """
        self.initial_threshold = initial_threshold
        self.min_threshold = min_threshold
        self.max_threshold = max_threshold
        self.threshold_step = threshold_step
        self.max_threshold_iterations = max_threshold_iterations
        self.max_query_rephrasings = max_query_rephrasings
        self.rephrasing_model = rephrasing_model or DEFAULT_REPHRASING_MODEL
        self.rephrasing_temperature = rephrasing_temperature

        # Load config defaults
        try:
            from bmlibrarian.config import get_config
            config = get_config()
            ollama_config = config.get("ollama", {})
            self.ollama_host = ollama_host or ollama_config.get(
                "host", "http://localhost:11434"
            )
        except ImportError:
            self.ollama_host = ollama_host or "http://localhost:11434"

        logger.info(
            f"SemanticQueryAgent initialized: threshold={initial_threshold}, "
            f"range=[{min_threshold}, {max_threshold}], "
            f"max_rephrasings={max_query_rephrasings}"
        )

    def search_document(
        self,
        document_id: int,
        query: str,
        min_results: int = DEFAULT_MIN_RESULTS,
        max_results: int = DEFAULT_MAX_RESULTS,
        use_fulltext: bool = True,
        db_manager: Optional["DatabaseManager"] = None,
    ) -> SemanticSearchResult:
        """
        Search a document with adaptive threshold and query rephrasing.

        Args:
            document_id: Database ID of the document to search.
            query: The search query.
            min_results: Minimum acceptable results (triggers threshold lowering).
            max_results: Maximum results to return (triggers threshold raising).
            use_fulltext: If True, search semantic.chunks; if False, search emb_1024.
            db_manager: Database manager instance. If None, will be obtained.

        Returns:
            SemanticSearchResult with chunks found and search metadata.
        """
        if db_manager is None:
            try:
                from bmlibrarian.database import get_db_manager
                db_manager = get_db_manager()
            except ImportError:
                return SemanticSearchResult(
                    success=False,
                    message="Database manager not available",
                )

        # Track all attempts
        queries_tried: List[str] = []
        thresholds_tried: List[float] = []
        total_iterations = 0

        # Start with original query
        current_queries = [query]

        for query_attempt in range(self.max_query_rephrasings + 1):
            current_query = current_queries[query_attempt] if query_attempt < len(current_queries) else query

            # Try threshold adjustments for this query
            result = self._search_with_threshold_adjustment(
                document_id=document_id,
                query=current_query,
                min_results=min_results,
                max_results=max_results,
                use_fulltext=use_fulltext,
                db_manager=db_manager,
            )

            queries_tried.append(current_query)
            thresholds_tried.extend(result.thresholds_tried)
            total_iterations += result.iterations

            if result.success and result.chunk_count >= min_results:
                # Success!
                result.queries_tried = queries_tried
                result.iterations = total_iterations
                logger.info(
                    f"[SemanticQueryAgent] Success after {query_attempt + 1} query attempts, "
                    f"{total_iterations} threshold iterations. "
                    f"Found {result.chunk_count} chunks at threshold {result.threshold_used:.2f}"
                )
                return result

            # Need to try rephrased query
            if query_attempt < self.max_query_rephrasings:
                logger.info(
                    f"[SemanticQueryAgent] Query attempt {query_attempt + 1} failed. "
                    f"Generating rephrased query..."
                )
                rephrased = self._generate_query_variation(
                    original_query=query,
                    attempt_number=query_attempt + 1,
                    previous_queries=queries_tried,
                )
                if rephrased and rephrased not in queries_tried:
                    current_queries.append(rephrased)
                    logger.info(f"[SemanticQueryAgent] Trying rephrased query: '{rephrased}'")
                else:
                    logger.warning(
                        f"[SemanticQueryAgent] Could not generate unique rephrased query"
                    )
                    break

        # All attempts exhausted
        logger.warning(
            f"[SemanticQueryAgent] All {len(queries_tried)} query attempts exhausted. "
            f"Best result: {result.chunk_count} chunks"
        )

        return SemanticSearchResult(
            success=False,
            chunks=result.chunks if result else [],
            query_used=queries_tried[-1] if queries_tried else query,
            threshold_used=result.threshold_used if result else self.initial_threshold,
            iterations=total_iterations,
            queries_tried=queries_tried,
            thresholds_tried=thresholds_tried,
            message=f"Could not find {min_results}+ results after {len(queries_tried)} query attempts",
        )

    def _search_with_threshold_adjustment(
        self,
        document_id: int,
        query: str,
        min_results: int,
        max_results: int,
        use_fulltext: bool,
        db_manager: "DatabaseManager",
    ) -> SemanticSearchResult:
        """
        Search with progressive threshold adjustment.

        Lowers threshold if no results, raises if too many.
        """
        threshold = self.initial_threshold
        thresholds_tried: List[float] = []
        best_result: Optional[SemanticSearchResult] = None
        direction = 0  # -1 = lowering, +1 = raising, 0 = undetermined

        for iteration in range(self.max_threshold_iterations):
            thresholds_tried.append(threshold)

            # Perform the search
            chunks = self._execute_search(
                document_id=document_id,
                query=query,
                threshold=threshold,
                max_results=max_results * 2,  # Get extra to check if we have too many
                use_fulltext=use_fulltext,
                db_manager=db_manager,
            )

            result = SemanticSearchResult(
                success=len(chunks) >= min_results,
                chunks=chunks[:max_results],  # Trim to max_results
                query_used=query,
                threshold_used=threshold,
                iterations=iteration + 1,
                thresholds_tried=thresholds_tried.copy(),
            )

            # Track best result
            if best_result is None or len(chunks) > len(best_result.chunks):
                best_result = result

            # Check result count
            if len(chunks) == 0:
                # No results - lower threshold
                if threshold <= self.min_threshold:
                    logger.debug(
                        f"[SemanticQueryAgent] No results at min threshold {threshold:.2f}"
                    )
                    break
                if direction == 1:  # Was raising, now need to lower - stop
                    break
                direction = -1
                threshold = max(threshold - self.threshold_step, self.min_threshold)
                logger.debug(
                    f"[SemanticQueryAgent] No results, lowering threshold to {threshold:.2f}"
                )

            elif len(chunks) < min_results:
                # Too few results - lower threshold
                if threshold <= self.min_threshold:
                    logger.debug(
                        f"[SemanticQueryAgent] Only {len(chunks)} results at min threshold"
                    )
                    break
                if direction == 1:  # Was raising, now need to lower - stop
                    break
                direction = -1
                threshold = max(threshold - self.threshold_step, self.min_threshold)
                logger.debug(
                    f"[SemanticQueryAgent] Only {len(chunks)} results, "
                    f"lowering threshold to {threshold:.2f}"
                )

            elif len(chunks) > max_results * 2:
                # Way too many results - raise threshold
                if threshold >= self.max_threshold:
                    logger.debug(
                        f"[SemanticQueryAgent] Too many results at max threshold"
                    )
                    # Return with max_results trimmed
                    result.success = True
                    return result
                if direction == -1:  # Was lowering, now need to raise - stop
                    result.success = True
                    return result
                direction = 1
                threshold = min(threshold + self.threshold_step, self.max_threshold)
                logger.debug(
                    f"[SemanticQueryAgent] Too many results ({len(chunks)}), "
                    f"raising threshold to {threshold:.2f}"
                )

            else:
                # Good number of results
                logger.debug(
                    f"[SemanticQueryAgent] Found {len(chunks)} results at threshold {threshold:.2f}"
                )
                result.success = True
                return result

        # Return best result found
        return best_result or SemanticSearchResult(
            success=False,
            query_used=query,
            iterations=len(thresholds_tried),
            thresholds_tried=thresholds_tried,
            message="Threshold adjustment exhausted",
        )

    def _execute_search(
        self,
        document_id: int,
        query: str,
        threshold: float,
        max_results: int,
        use_fulltext: bool,
        db_manager: "DatabaseManager",
    ) -> List[ChunkResult]:
        """
        Execute the actual semantic search query.

        Args:
            document_id: Document to search.
            query: Search query.
            threshold: Similarity threshold.
            max_results: Maximum results.
            use_fulltext: True for semantic.chunks, False for emb_1024.
            db_manager: Database manager.

        Returns:
            List of ChunkResult objects.
        """
        try:
            with db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    if use_fulltext:
                        # Search semantic.chunks (full-text)
                        cur.execute(
                            """
                            SELECT chunk_id, chunk_no, score, chunk_text
                            FROM semantic.chunksearch_document(%s, %s, %s, %s)
                            ORDER BY score DESC
                            """,
                            (document_id, query, threshold, max_results),
                        )
                    else:
                        # Search emb_1024 (abstract)
                        cur.execute(
                            """
                            SELECT chunk_id, chunk_no, score, chunk_text
                            FROM semantic_search_document(%s, %s, %s, %s)
                            ORDER BY score DESC
                            """,
                            (document_id, query, threshold, max_results),
                        )

                    rows = cur.fetchall()
                    return [
                        ChunkResult(
                            chunk_id=row[0],
                            chunk_no=row[1],
                            score=row[2],
                            text=row[3],
                        )
                        for row in rows
                    ]

        except Exception as e:
            logger.error(f"Semantic search failed: {e}", exc_info=True)
            return []

    def _generate_query_variation(
        self,
        original_query: str,
        attempt_number: int,
        previous_queries: List[str],
    ) -> Optional[str]:
        """
        Generate a rephrased version of the query using LLM.

        Args:
            original_query: The original search query.
            attempt_number: Which rephrasing attempt this is (1, 2, 3...).
            previous_queries: Queries already tried (to avoid duplicates).

        Returns:
            Rephrased query string, or None if generation fails.
        """
        try:
            import ollama

            # Build prompt for query rephrasing
            previous_list = "\n".join(f"- {q}" for q in previous_queries)

            prompt = f"""You are helping improve a semantic search query. The original query did not find good results in a biomedical document.

Original query: "{original_query}"

Previous attempts that didn't work well:
{previous_list}

Generate a single alternative query that:
1. Asks the same question but with different wording
2. Uses synonyms or related terms
3. Is concise (under 20 words)
4. Is different from all previous attempts

Respond with ONLY the new query, nothing else."""

            response = ollama.generate(
                model=self.rephrasing_model,
                prompt=prompt,
                options={
                    "temperature": self.rephrasing_temperature,
                    "num_predict": 50,  # Short response
                },
            )

            rephrased = response.get("response", "").strip()

            # Clean up the response
            rephrased = rephrased.strip('"\'')
            if rephrased and len(rephrased) > 5:
                return rephrased

            return None

        except Exception as e:
            logger.warning(f"Query rephrasing failed: {e}")
            return None


# Convenience function for simple use cases
def adaptive_semantic_search(
    document_id: int,
    query: str,
    min_results: int = 1,
    max_results: int = 5,
    use_fulltext: bool = True,
) -> SemanticSearchResult:
    """
    Convenience function for adaptive semantic search.

    Creates a SemanticQueryAgent with default settings and performs a search.

    Args:
        document_id: Document to search.
        query: Search query.
        min_results: Minimum acceptable results.
        max_results: Maximum results to return.
        use_fulltext: True for full-text chunks, False for abstract.

    Returns:
        SemanticSearchResult with chunks and metadata.
    """
    agent = SemanticQueryAgent()
    return agent.search_document(
        document_id=document_id,
        query=query,
        min_results=min_results,
        max_results=max_results,
        use_fulltext=use_fulltext,
    )


__all__ = [
    "SemanticQueryAgent",
    "SemanticSearchResult",
    "ChunkResult",
    "adaptive_semantic_search",
    "DEFAULT_INITIAL_THRESHOLD",
    "DEFAULT_MIN_THRESHOLD",
    "DEFAULT_MAX_THRESHOLD",
    "DEFAULT_MAX_QUERY_REPHRASINGS",
]
