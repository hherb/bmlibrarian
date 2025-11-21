# Step 6: Multi-Strategy Search Implementation

## Context

Counter-statements with HyDE abstracts and keywords (Step 5) are now generated. We need to implement the SearchCoordinator that performs three parallel search strategies.

## Objective

Implement SearchCoordinator component that:
- Executes semantic search (embedding-based)
- Executes HyDE search (hypothetical document matching)
- Executes keyword search (traditional text matching)
- Deduplicates results across strategies
- Tracks provenance (which strategy found each document)
- Returns SearchResults with full metadata

## Requirements

- Database integration (PostgreSQL + pgvector)
- Embedding generation for semantic/HyDE search
- Full-text search for keyword search
- Result deduplication
- Provenance tracking
- Configurable limits per strategy

## Implementation Location

Create: `src/bmlibrarian/paperchecker/components/search_coordinator.py`

## Component Design

```python
"""
Multi-strategy search coordinator for PaperChecker

Implements semantic, HyDE, and keyword-based search strategies for finding
counter-evidence in the literature database.
"""

import logging
from typing import List, Dict, Any, Tuple
import psycopg
from psycopg.rows import dict_row
import requests

from ..data_models import CounterStatement, SearchResults

logger = logging.getLogger(__name__)


class SearchCoordinator:
    """
    Coordinates multiple search strategies for finding counter-evidence

    Implements three parallel strategies:
    1. Semantic search: Embedding-based similarity search
    2. HyDE search: Match against hypothetical document embeddings
    3. Keyword search: Traditional full-text search

    Results are deduplicated and provenance is tracked.
    """

    def __init__(
        self,
        config: Dict[str, Any],
        db_connection,
        ollama_url: str = "http://localhost:11434",
        embedding_model: str = "nomic-embed-text"
    ):
        """
        Initialize SearchCoordinator

        Args:
            config: Search configuration dict with limits
            db_connection: psycopg connection object
            ollama_url: Ollama server URL for embeddings
            embedding_model: Model for generating embeddings
        """
        self.config = config
        self.conn = db_connection
        self.ollama_url = ollama_url
        self.embedding_model = embedding_model

        # Get limits from config
        self.semantic_limit = config.get("semantic_limit", 50)
        self.hyde_limit = config.get("hyde_limit", 50)
        self.keyword_limit = config.get("keyword_limit", 50)
        self.max_deduplicated = config.get("max_deduplicated", 100)

    def search(self, counter_stmt: CounterStatement) -> SearchResults:
        """
        Execute all search strategies and combine results

        Args:
            counter_stmt: CounterStatement with negated text, HyDE, keywords

        Returns:
            SearchResults with deduplicated docs and provenance

        Raises:
            RuntimeError: If all search strategies fail
        """
        logger.info("Executing multi-strategy search")

        semantic_docs = []
        hyde_docs = []
        keyword_docs = []

        # Strategy 1: Semantic search
        try:
            semantic_docs = self._semantic_search(
                counter_stmt.negated_text,
                limit=self.semantic_limit
            )
            logger.info(f"Semantic search found {len(semantic_docs)} documents")
        except Exception as e:
            logger.error(f"Semantic search failed: {e}")

        # Strategy 2: HyDE search
        try:
            hyde_docs = self._hyde_search(
                counter_stmt.hyde_abstracts,
                limit=self.hyde_limit
            )
            logger.info(f"HyDE search found {len(hyde_docs)} documents")
        except Exception as e:
            logger.error(f"HyDE search failed: {e}")

        # Strategy 3: Keyword search
        try:
            keyword_docs = self._keyword_search(
                counter_stmt.keywords,
                limit=self.keyword_limit
            )
            logger.info(f"Keyword search found {len(keyword_docs)} documents")
        except Exception as e:
            logger.error(f"Keyword search failed: {e}")

        # Check that at least one strategy succeeded
        if not (semantic_docs or hyde_docs or keyword_docs):
            raise RuntimeError("All search strategies failed")

        # Create SearchResults with provenance
        results = SearchResults.from_strategy_results(
            semantic=semantic_docs,
            hyde=hyde_docs,
            keyword=keyword_docs,
            metadata={
                "semantic_limit": self.semantic_limit,
                "hyde_limit": self.hyde_limit,
                "keyword_limit": self.keyword_limit,
                "total_found": len(set(semantic_docs + hyde_docs + keyword_docs))
            }
        )

        # Limit deduplicated results
        if len(results.deduplicated_docs) > self.max_deduplicated:
            logger.info(
                f"Limiting results from {len(results.deduplicated_docs)} "
                f"to {self.max_deduplicated}"
            )
            # Keep docs found by multiple strategies first
            deduplicated = self._prioritize_multi_strategy_docs(
                results.deduplicated_docs,
                results.provenance,
                self.max_deduplicated
            )
            results.deduplicated_docs = deduplicated

        logger.info(
            f"Search complete: {len(results.deduplicated_docs)} unique documents "
            f"from {len(results.semantic_docs) + len(results.hyde_docs) + len(results.keyword_docs)} total"
        )

        return results

    def _semantic_search(self, text: str, limit: int) -> List[int]:
        """
        Perform semantic search using embeddings

        Args:
            text: Counter-statement text
            limit: Maximum results

        Returns:
            List of document IDs
        """
        # Generate embedding for counter-statement
        embedding = self._generate_embedding(text)

        # Query database for similar documents
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT id, 1 - (embedding <=> %s::vector) AS similarity
                FROM public.documents
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """, (embedding, embedding, limit))

            results = cur.fetchall()

        return [row["id"] for row in results]

    def _hyde_search(self, hyde_abstracts: List[str], limit: int) -> List[int]:
        """
        Perform HyDE search using hypothetical document embeddings

        Args:
            hyde_abstracts: List of hypothetical abstracts
            limit: Maximum results per HyDE abstract

        Returns:
            List of document IDs (deduplicated across HyDE abstracts)
        """
        all_docs = []

        for i, hyde_abstract in enumerate(hyde_abstracts, 1):
            logger.debug(f"HyDE search {i}/{len(hyde_abstracts)}")

            # Generate embedding for HyDE abstract
            embedding = self._generate_embedding(hyde_abstract)

            # Query database
            with self.conn.cursor(row_factory=dict_row) as cur:
                cur.execute("""
                    SELECT id, 1 - (embedding <=> %s::vector) AS similarity
                    FROM public.documents
                    WHERE embedding IS NOT NULL
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                """, (embedding, embedding, limit))

                results = cur.fetchall()

            all_docs.extend([row["id"] for row in results])

        # Deduplicate (keep unique doc IDs)
        return list(dict.fromkeys(all_docs))  # Preserves order

    def _keyword_search(self, keywords: List[str], limit: int) -> List[int]:
        """
        Perform keyword search using full-text search

        Args:
            keywords: List of search keywords
            limit: Maximum results

        Returns:
            List of document IDs
        """
        # Build tsquery from keywords
        query_parts = " | ".join(keywords)  # OR logic

        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT id,
                       ts_rank_cd(
                           to_tsvector('english',
                               COALESCE(title, '') || ' ' || COALESCE(abstract, '')
                           ),
                           to_tsquery('english', %s)
                       ) AS rank
                FROM public.documents
                WHERE to_tsvector('english',
                    COALESCE(title, '') || ' ' || COALESCE(abstract, '')
                ) @@ to_tsquery('english', %s)
                ORDER BY rank DESC
                LIMIT %s
            """, (query_parts, query_parts, limit))

            results = cur.fetchall()

        return [row["id"] for row in results]

    def _generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding using Ollama

        Args:
            text: Text to embed

        Returns:
            Embedding vector

        Raises:
            RuntimeError: If embedding generation fails
        """
        try:
            response = requests.post(
                f"{self.ollama_url}/api/embeddings",
                json={
                    "model": self.embedding_model,
                    "prompt": text
                },
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            return data["embedding"]

        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            raise RuntimeError(f"Failed to generate embedding: {e}") from e

    def _prioritize_multi_strategy_docs(
        self,
        doc_ids: List[int],
        provenance: Dict[int, List[str]],
        limit: int
    ) -> List[int]:
        """
        Prioritize documents found by multiple strategies

        Args:
            doc_ids: All document IDs
            provenance: Doc ID → strategies that found it
            limit: Maximum to return

        Returns:
            Limited list of doc IDs, prioritizing multi-strategy matches
        """
        # Sort by number of strategies that found each doc (descending)
        sorted_docs = sorted(
            doc_ids,
            key=lambda doc_id: len(provenance[doc_id]),
            reverse=True
        )

        return sorted_docs[:limit]
```

## Integration with PaperCheckerAgent

Update `src/bmlibrarian/paperchecker/agent.py`:

```python
def _search_counter_evidence(
    self, counter_stmt: CounterStatement
) -> SearchResults:
    """
    Step 3: Multi-strategy search for counter-evidence

    Executes three parallel search strategies:
    1. Semantic search (embedding-based)
    2. HyDE search (hypothetical document matching)
    3. Keyword search (full-text)

    Args:
        counter_stmt: CounterStatement with search materials

    Returns:
        SearchResults with deduplicated docs and provenance

    Raises:
        RuntimeError: If search fails
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
```

## Testing Strategy

Create `tests/test_search_coordinator.py`:

```python
"""Tests for SearchCoordinator"""

import pytest
from bmlibrarian.paperchecker.components import SearchCoordinator
from bmlibrarian.paperchecker.data_models import Statement, CounterStatement


@pytest.fixture
def search_config():
    """Search configuration"""
    return {
        "semantic_limit": 50,
        "hyde_limit": 50,
        "keyword_limit": 50,
        "max_deduplicated": 100
    }


@pytest.fixture
def counter_statement():
    """Sample counter-statement"""
    original = Statement(
        text="Metformin is superior to GLP-1",
        context="",
        statement_type="finding",
        confidence=0.9,
        statement_order=1
    )

    return CounterStatement(
        original_statement=original,
        negated_text="GLP-1 is superior or equivalent to metformin",
        hyde_abstracts=[
            "Background: GLP-1 agonists show promise. Methods: RCT with 1000 patients. Results: GLP-1 reduced HbA1c by 1.8% vs metformin 1.2% (p<0.001). Conclusion: GLP-1 superior.",
            "Objective: Compare GLP-1 and metformin. Design: Meta-analysis of 20 trials. Findings: GLP-1 associated with better outcomes (OR 1.45). Conclusion: GLP-1 preferred."
        ],
        keywords=[
            "GLP-1", "metformin", "type 2 diabetes",
            "glycemic control", "HbA1c", "semaglutide",
            "liraglutide", "randomized controlled trial"
        ],
        generation_metadata={}
    )


def test_search_coordinator_init(search_config, db_connection):
    """Test SearchCoordinator initialization"""
    coordinator = SearchCoordinator(
        config=search_config,
        db_connection=db_connection
    )

    assert coordinator.semantic_limit == 50
    assert coordinator.hyde_limit == 50
    assert coordinator.keyword_limit == 50


def test_semantic_search(search_config, db_connection, counter_statement):
    """Test semantic search returns results"""
    coordinator = SearchCoordinator(
        config=search_config,
        db_connection=db_connection
    )

    results = coordinator._semantic_search(
        counter_statement.negated_text,
        limit=10
    )

    assert isinstance(results, list)
    assert len(results) <= 10
    assert all(isinstance(doc_id, int) for doc_id in results)


def test_hyde_search(search_config, db_connection, counter_statement):
    """Test HyDE search returns results"""
    coordinator = SearchCoordinator(
        config=search_config,
        db_connection=db_connection
    )

    results = coordinator._hyde_search(
        counter_statement.hyde_abstracts,
        limit=10
    )

    assert isinstance(results, list)
    assert all(isinstance(doc_id, int) for doc_id in results)


def test_keyword_search(search_config, db_connection, counter_statement):
    """Test keyword search returns results"""
    coordinator = SearchCoordinator(
        config=search_config,
        db_connection=db_connection
    )

    results = coordinator._keyword_search(
        counter_statement.keywords,
        limit=10
    )

    assert isinstance(results, list)
    assert len(results) <= 10
    assert all(isinstance(doc_id, int) for doc_id in results)


def test_full_search(search_config, db_connection, counter_statement):
    """Test full multi-strategy search"""
    coordinator = SearchCoordinator(
        config=search_config,
        db_connection=db_connection
    )

    results = coordinator.search(counter_statement)

    # Verify structure
    assert isinstance(results.semantic_docs, list)
    assert isinstance(results.hyde_docs, list)
    assert isinstance(results.keyword_docs, list)
    assert isinstance(results.deduplicated_docs, list)
    assert isinstance(results.provenance, dict)

    # Verify deduplication
    assert len(results.deduplicated_docs) <= len(
        results.semantic_docs + results.hyde_docs + results.keyword_docs
    )

    # Verify provenance
    for doc_id in results.deduplicated_docs:
        assert doc_id in results.provenance
        assert len(results.provenance[doc_id]) > 0


def test_provenance_tracking(search_config, db_connection, counter_statement):
    """Test that provenance is tracked correctly"""
    coordinator = SearchCoordinator(
        config=search_config,
        db_connection=db_connection
    )

    results = coordinator.search(counter_statement)

    # Check that provenance matches actual results
    for doc_id in results.deduplicated_docs:
        strategies = results.provenance[doc_id]

        if "semantic" in strategies:
            assert doc_id in results.semantic_docs
        if "hyde" in strategies:
            assert doc_id in results.hyde_docs
        if "keyword" in strategies:
            assert doc_id in results.keyword_docs
```

## Success Criteria

- [ ] SearchCoordinator component implemented
- [ ] Semantic search working with embeddings
- [ ] HyDE search working with multiple abstracts
- [ ] Keyword search working with full-text search
- [ ] Deduplication logic correct
- [ ] Provenance tracking accurate
- [ ] Integration with PaperCheckerAgent complete
- [ ] All unit tests passing
- [ ] Performance acceptable (<30 seconds for typical search)
- [ ] Error handling for failed strategies

## Next Steps

After completing this step, proceed to:
- **Step 7**: Document Scoring Integration (07_DOCUMENT_SCORING.md)
- Adapt existing DocumentScoringAgent for counter-statement scoring
