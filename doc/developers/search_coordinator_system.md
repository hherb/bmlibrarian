# SearchCoordinator System - Developer Documentation

## Overview

The SearchCoordinator is a core component of the PaperChecker fact-checking system that implements multi-strategy document search. It executes three parallel search strategies (semantic, HyDE, and keyword) to find counter-evidence in the literature database, then deduplicates results while tracking provenance.

## Architecture

### Component Location

```
src/bmlibrarian/paperchecker/
├── components/
│   └── search_coordinator.py  # Main implementation
├── data_models.py             # CounterStatement, SearchResults
└── agent.py                   # PaperCheckerAgent integration
```

### Design Principles

The SearchCoordinator follows BMLibrarian's golden programming rules:

1. **Database access via DatabaseManager** (Rule 5): Uses `get_db_manager()` for all database operations
2. **Ollama library for embeddings** (Rule 4): Uses `ollama.embeddings()` instead of raw HTTP requests
3. **Named constants** (Rule 2): All limits defined as module-level constants
4. **Type hints** (Rule 6): All parameters and return types fully typed
5. **Comprehensive docstrings** (Rule 7): All methods documented
6. **Error handling** (Rule 8): Graceful degradation on partial failures

## Search Strategies

### 1. Semantic Search

Embedding-based similarity search using pgvector:

```python
def search_semantic(self, text: str, limit: int) -> List[int]:
    """
    1. Generate embedding for counter-statement text using Ollama
    2. Query emb_1024 table using cosine distance (<=> operator)
    3. Return document IDs ordered by similarity
    """
```

**Database Query:**
```sql
SELECT DISTINCT c.document_id,
       MIN(e.embedding <=> %s::vector) AS distance
FROM emb_1024 e
JOIN chunks c ON e.chunk_id = c.id
WHERE e.embedding IS NOT NULL
GROUP BY c.document_id
ORDER BY distance ASC
LIMIT %s
```

### 2. HyDE Search

Hypothetical Document Embedding search using generated abstracts:

```python
def search_hyde(self, hyde_abstracts: List[str], limit: int) -> List[int]:
    """
    1. For each hypothetical abstract:
       - Generate embedding using Ollama
       - Query database for similar documents
    2. Deduplicate results across all abstracts
    3. Return unique document IDs (first occurrence wins)
    """
```

**Key Features:**
- Processes multiple HyDE abstracts (typically 2)
- Continues on partial failure (some abstracts may fail)
- Raises `RuntimeError` only if ALL abstracts fail

### 3. Keyword Search

Full-text search using PostgreSQL ts_vector:

```python
def search_keyword(self, keywords: List[str], limit: int) -> List[int]:
    """
    1. Escape and format keywords for tsquery
    2. Combine keywords with OR operator
    3. Query using ts_rank_cd for relevance ranking
    """
```

**Database Query:**
```sql
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
```

## Data Flow

```
CounterStatement
    ├── negated_text ─────────→ Semantic Search
    ├── hyde_abstracts ───────→ HyDE Search
    └── keywords ─────────────→ Keyword Search
                                     │
                                     ▼
                              Combine Results
                                     │
                                     ▼
                              Deduplicate
                                     │
                                     ▼
                              Track Provenance
                                     │
                                     ▼
                              Limit Results
                                     │
                                     ▼
                              SearchResults
```

## Configuration

### Search Limits

```python
# Default values (in search_coordinator.py)
DEFAULT_SEMANTIC_LIMIT: int = 50
DEFAULT_HYDE_LIMIT: int = 50
DEFAULT_KEYWORD_LIMIT: int = 50
DEFAULT_MAX_DEDUPLICATED: int = 100
DEFAULT_EMBEDDING_MODEL: str = "snowflake-arctic-embed2:latest"
```

### Config File Integration

In `~/.bmlibrarian/config.json`:

```json
{
  "paper_checker": {
    "search": {
      "semantic_limit": 50,
      "hyde_limit": 50,
      "keyword_limit": 50,
      "max_deduplicated": 100,
      "embedding_model": "snowflake-arctic-embed2:latest"
    }
  }
}
```

## Provenance Tracking

The SearchResults object tracks which strategies found each document:

```python
@dataclass
class SearchResults:
    semantic_docs: List[int]      # IDs from semantic search
    hyde_docs: List[int]          # IDs from HyDE search
    keyword_docs: List[int]       # IDs from keyword search
    deduplicated_docs: List[int]  # Unique IDs
    provenance: Dict[int, List[str]]  # doc_id -> ["semantic", "hyde", "keyword"]
    search_metadata: Dict[str, Any]   # Timing, limits, errors
```

### Provenance Values

```python
VALID_SEARCH_STRATEGIES = {"semantic", "hyde", "keyword"}
```

## Prioritization Algorithm

When results exceed `max_deduplicated`, documents are prioritized by:

1. **Number of strategies that found the document** (descending)
   - Documents found by all 3 strategies rank highest
   - Documents found by 2 strategies rank next
   - Documents found by 1 strategy rank lowest
2. **Document ID** (ascending, for stable ordering)

```python
def _prioritize_multi_strategy_docs(
    self,
    doc_ids: List[int],
    provenance: Dict[int, List[str]],
    limit: int
) -> List[int]:
    sorted_docs = sorted(
        doc_ids,
        key=lambda doc_id: (-len(provenance.get(doc_id, [])), doc_id)
    )
    return sorted_docs[:limit]
```

## Error Handling

### Graceful Degradation

The search method continues when individual strategies fail:

```python
def search(self, counter_stmt: CounterStatement) -> SearchResults:
    errors = []

    try:
        semantic_docs = self.search_semantic(...)
    except Exception as e:
        errors.append(f"Semantic search failed: {e}")

    # Continue with other strategies...

    # Only raise if ALL strategies fail
    if not (semantic_docs or hyde_docs or keyword_docs):
        raise RuntimeError("All search strategies failed")
```

### Embedding Failures

The `_generate_embedding` method returns empty list on failure (doesn't raise):

```python
def _generate_embedding(self, text: str) -> List[float]:
    try:
        response = ollama.embeddings(model=self.embedding_model, prompt=text)
        return response.get("embedding", [])
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        return []  # Graceful degradation
```

## Integration with PaperCheckerAgent

The SearchCoordinator is used in Step 3 of the PaperChecker workflow:

```python
class PaperCheckerAgent(BaseAgent):
    def _init_components(self) -> None:
        search_config = self.agent_config.get("search", {})
        self.search_coordinator = SearchCoordinator(
            config=search_config,
            db_connection=self.db.get_connection()  # Legacy, ignored
        )

    def _search_counter_evidence(
        self, counter_stmt: CounterStatement
    ) -> SearchResults:
        search_results = self.search_coordinator.search(counter_stmt)
        return search_results
```

## Testing

### Unit Tests

Location: `tests/test_search_coordinator.py`

Test categories:
- Initialization tests
- Semantic search tests
- HyDE search tests
- Keyword search tests
- Full search integration
- Provenance tracking
- Prioritization logic
- Error handling

### Running Tests

```bash
# Run all SearchCoordinator tests
uv run python -m pytest tests/test_search_coordinator.py -v

# Run with coverage
uv run python -m pytest tests/test_search_coordinator.py --cov=bmlibrarian.paperchecker.components.search_coordinator

# Run integration tests (requires live services)
uv run python -m pytest tests/test_search_coordinator.py -v -m integration
```

### Mocking Pattern

```python
@patch("bmlibrarian.paperchecker.components.search_coordinator.get_db_manager")
@patch("bmlibrarian.paperchecker.components.search_coordinator.ollama")
def test_semantic_search(self, mock_ollama, mock_get_db, ...):
    mock_get_db.return_value = MagicMock()
    mock_ollama.embeddings.return_value = {"embedding": [0.1] * 1024}

    coordinator = SearchCoordinator(config=config)
    # Test...
```

## Performance Considerations

### Embedding Generation

- Each embedding request takes ~1-3 seconds
- HyDE search with 2 abstracts = 2 embedding calls
- Total embedding time: ~3-9 seconds per search

### Database Queries

- Semantic/HyDE: Uses pgvector index on emb_1024.embedding
- Keyword: Uses GIN index on document.search_vector
- Typical query time: <100ms with indexes

### Optimization Tips

1. **Reduce HyDE abstracts**: Use 1 instead of 2 for faster search
2. **Lower limits**: Use smaller limits for testing/development
3. **Embedding model**: Consider smaller models for faster embeddings

## Extending the Component

### Adding a New Search Strategy

1. Add strategy name to `VALID_SEARCH_STRATEGIES` in data_models.py
2. Create search method in SearchCoordinator:
   ```python
   def search_new_strategy(self, ..., limit: int) -> List[int]:
       # Implementation
       return doc_ids
   ```
3. Add to `search()` method alongside other strategies
4. Update provenance tracking

### Customizing Prioritization

Override `_prioritize_multi_strategy_docs()`:

```python
class CustomSearchCoordinator(SearchCoordinator):
    def _prioritize_multi_strategy_docs(self, doc_ids, provenance, limit):
        # Custom prioritization logic
        return sorted_docs[:limit]
```

## Related Documentation

- [PaperChecker Architecture Overview](../planning/paperchecker/00_ARCHITECTURE_OVERVIEW.md)
- [Multi-Strategy Search Planning](../planning/paperchecker/06_MULTI_STRATEGY_SEARCH.md)
- [Data Models Reference](../llm/paperchecker_data_models.md)
