# Multi-Model Query Generation Architecture

## Overview

This document provides technical architecture documentation for the multi-model query generation system in BMLibrarian. The system enables using multiple AI models to generate diverse database queries, improving document retrieval quality through query diversity.

**Key Design Principles**:
- Serial execution (not parallel) for local Ollama + PostgreSQL instances
- ID-only queries first for performance
- Backward compatibility via feature flags
- Type-safe data structures
- Comprehensive error handling

## Architecture Components

### 1. Configuration Layer

**Location**: `src/bmlibrarian/config.py`

**Purpose**: Centralized configuration management for multi-model query generation

**Schema**:
```python
DEFAULT_CONFIG = {
    "query_generation": {
        "multi_model_enabled": False,  # Feature flag
        "models": ["medgemma-27b-text-it-Q8_0:latest"],
        "queries_per_model": 1,  # 1-3
        "execution_mode": "serial",  # Always serial
        "deduplicate_results": True,
        "show_all_queries_to_user": True,
        "allow_query_selection": True
    }
}
```

**Validation**: Handled by `BMLibrarianConfig` class (if using pydantic) or runtime validation

**Access Pattern**:
```python
from bmlibrarian.config import get_query_generation_config

config = get_query_generation_config()
models = config['models']
enabled = config['multi_model_enabled']
```

### 2. Data Types Layer

**Location**: `src/bmlibrarian/agents/query_generation/data_types.py`

**Purpose**: Type-safe data structures for query generation results

**Classes**:

#### QueryGenerationResult
```python
@dataclass
class QueryGenerationResult:
    """Result from a single query generation attempt by one model."""
    model: str                      # Model name
    query: str                      # Generated query (may be empty if error)
    generation_time: float          # Time taken (seconds)
    temperature: float              # Temperature used
    attempt_number: int             # Attempt number (1-indexed)
    error: Optional[str] = None     # Error message if generation failed
```

**Usage**:
- Tracks individual query generation attempts
- Contains error information for debugging
- Includes timing for performance analysis

#### MultiModelQueryResult
```python
@dataclass
class MultiModelQueryResult:
    """Aggregated result from multiple models generating queries."""
    all_queries: List[QueryGenerationResult]  # All attempts (including duplicates)
    unique_queries: List[str]                  # De-duplicated queries
    model_count: int                           # Number of models used
    total_queries: int                         # Total queries generated
    total_generation_time: float               # Cumulative time
    question: str                              # Original user question
```

**Usage**:
- Aggregates results from all models
- Tracks both raw and de-duplicated queries
- Provides performance metrics

### 3. Query Generator Layer

**Location**: `src/bmlibrarian/agents/query_generation/generator.py`

**Purpose**: Core logic for multi-model query generation

**Class**: `MultiModelQueryGenerator`

**Key Methods**:

#### generate_queries()
```python
def generate_queries(
    self,
    question: str,
    system_prompt: str,
    models: List[str],
    queries_per_model: int,
    temperature: float = 0.1
) -> MultiModelQueryResult:
    """
    Generate multiple queries using multiple models (SERIAL execution).

    Args:
        question: User's research question
        system_prompt: System prompt for query generation
        models: List of model names to use
        queries_per_model: Number of queries to generate per model (1-3)
        temperature: Temperature for LLM generation

    Returns:
        MultiModelQueryResult with all queries and metadata

    Execution Flow:
        1. For each model (SERIAL):
           - For each attempt (SERIAL):
             - Generate query via Ollama
             - Track timing and errors
        2. De-duplicate queries (case-insensitive)
        3. Return aggregated result
    """
```

**Serial Execution Pattern**:
```python
# Simple for-loops, no threading
for model in models:
    for attempt in range(queries_per_model):
        result = self._generate_single_query(
            model, question, system_prompt, temperature, attempt
        )
        all_results.append(result)
```

#### _deduplicate_queries()
```python
def _deduplicate_queries(self, queries: List[str]) -> List[str]:
    """
    Remove duplicate queries (case-insensitive).
    Preserves first occurrence's case.
    Filters out empty strings.

    Args:
        queries: List of generated queries (may contain duplicates)

    Returns:
        List of unique queries

    Algorithm:
        1. Normalize to lowercase for comparison
        2. Track seen queries in set
        3. Keep first occurrence (preserves original case)
        4. Filter out empty/whitespace-only strings
    """
    seen = set()
    unique = []
    for q in queries:
        normalized = q.lower().strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique.append(q)  # Preserve original case
    return unique
```

**Error Handling**:
- Model failures are captured in `QueryGenerationResult.error`
- Generation continues with remaining models
- Empty queries are filtered during de-duplication
- No complete failure unless all models fail

### 4. Database Layer

**Location**: `src/bmlibrarian/database.py`

**Purpose**: Efficient database operations for multi-query execution

**Key Functions**:

#### find_abstract_ids()
```python
def find_abstract_ids(
    ts_query_str: str,
    max_rows: int = 100,
    use_pubmed: bool = True,
    use_medrxiv: bool = True,
    use_others: bool = True,
    plain: bool = False,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    offset: int = 0
) -> set[int]:
    """
    Execute ID-only query for fast document lookup.

    Returns:
        set[int]: Document IDs matching the query

    Performance:
        - No JOINs (documents table only)
        - No text columns (ID only)
        - ~10x faster than full document fetch
        - Enables fast query execution and de-duplication

    SQL Pattern:
        SELECT DISTINCT d.id
        FROM documents d
        WHERE d.tsv @@ to_tsquery('english', %s)
        ORDER BY ts_rank(...) DESC
        LIMIT %s
    """
```

#### fetch_documents_by_ids()
```python
def fetch_documents_by_ids(
    document_ids: set[int],
    batch_size: int = 50
) -> list[Dict[str, Any]]:
    """
    Fetch full documents by ID set with batching.

    Args:
        document_ids: Set of document IDs to fetch
        batch_size: Batch size for query (default 50)

    Returns:
        list[Dict]: Full document dictionaries

    Batching:
        - PostgreSQL has parameter limit (~32767)
        - Batching prevents hitting limits
        - Default batch_size=50 is conservative
        - Processes batches serially

    SQL Pattern:
        SELECT d.*, a.name as author_name, ...
        FROM documents d
        LEFT JOIN authors a ON ...
        WHERE d.id = ANY(%s)
    """
```

**Performance Benefits**:
- ID-only queries: ~0.1-0.5 seconds each
- Set operations: Nearly instant
- Bulk fetch: Only done once after de-duplication
- Total database time: Similar to single-query mode

### 5. Agent Integration Layer

**Location**: `src/bmlibrarian/agents/query_agent.py`

**Purpose**: Integration of multi-model generation into QueryAgent

**Key Methods**:

#### convert_question_multi_model()
```python
def convert_question_multi_model(
    self,
    user_question: str
) -> MultiModelQueryResult:
    """
    Convert user question to multiple database queries using multiple models.

    Behavior:
        - If multi_model_enabled=False: Falls back to single model
        - If multi_model_enabled=True: Uses MultiModelQueryGenerator

    Returns:
        MultiModelQueryResult (even in fallback mode for consistency)

    Fallback Logic:
        When disabled, wraps single query in MultiModelQueryResult:
        - model_count = 1
        - total_queries = 1
        - unique_queries = [single_query]
    """
```

#### find_abstracts_multi_query()
```python
def find_abstracts_multi_query(
    self,
    question: str,
    max_rows: int = 100,
    use_pubmed: bool = True,
    use_medrxiv: bool = True,
    use_others: bool = True,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    human_in_the_loop: bool = False,
    human_query_modifier: Optional[Callable[[list[str]], list[str]]] = None
) -> Generator[Dict, None, None]:
    """
    Complete multi-query document search workflow.

    Workflow Steps:
        1. Generate queries using convert_question_multi_model()
        2. Human review (optional):
           - Display all queries
           - Allow selection/editing via human_query_modifier callback
        3. Execute queries serially:
           - For each query:
             - Call find_abstract_ids() to get ID set
             - Merge IDs into cumulative set
        4. Fetch documents:
           - Call fetch_documents_by_ids() with merged ID set
           - Fetches each document only once
        5. Yield documents:
           - Stream documents via generator
           - Same interface as find_abstracts()

    Returns:
        Generator yielding document dictionaries

    Backward Compatibility:
        - Generator interface matches find_abstracts()
        - Can be used as drop-in replacement
        - Falls back to single query if disabled
    """
```

**Human-in-the-Loop**:
```python
if human_in_the_loop and human_query_modifier:
    # Callback receives list of queries
    # Returns modified list (user can remove/edit queries)
    queries = human_query_modifier(query_result.unique_queries)
```

### 6. CLI Integration Layer

**Location**: `src/bmlibrarian/cli/query_processing.py` (future implementation)

**Purpose**: User interface integration for query review and selection

**Planned Components**:
- Query display formatting
- Query selection interface
- Query editing interface
- Progress indicators

**Note**: CLI UI integration is deferred from Phase 4 and can be added when ready for user testing.

## Design Decisions

### Serial vs Parallel Execution

**Decision**: Serial execution only

**Rationale**:

1. **Local Ollama Instance**:
   - Single GPU
   - One model loaded at a time
   - Parallel requests queue anyway
   - No performance benefit from threading

2. **Local PostgreSQL Instance**:
   - Single database instance
   - Connection pooling already handles concurrency
   - Parallel queries don't improve performance
   - May create connection bottlenecks

3. **Code Simplicity**:
   - Simple for-loops are easier to understand
   - No threading/async complexity
   - Easier debugging
   - No race conditions

4. **Resource Management**:
   - No memory spikes from parallel execution
   - Predictable resource usage
   - No connection pool exhaustion

**Implementation**:
```python
# Simple serial execution
for model in models:
    result = generate_query(model)  # Blocks until complete
    results.append(result)
```

### ID-Only Queries First

**Decision**: Fetch document IDs first, then bulk fetch full documents

**Rationale**:

1. **Performance**:
   - ID queries are ~10x faster (no JOINs, no text)
   - Enables fast query execution
   - Fast de-duplication with Set[int]

2. **De-duplication**:
   - Set operations on integers are nearly instant
   - Easy to merge ID sets from multiple queries
   - Fetch each document only once

3. **Database Load**:
   - Reduces number of expensive full-document queries
   - Single bulk fetch instead of N full queries

**SQL Comparison**:
```sql
-- ID-only query (fast)
SELECT DISTINCT d.id FROM documents d WHERE ...

-- Full document query (slower)
SELECT d.*, a.name, ... FROM documents d
LEFT JOIN authors a ... WHERE ...
```

**Data Flow**:
```
Query 1 → {101, 102, 103}
Query 2 → {102, 103, 104}
Query 3 → {103, 104, 105}
              ↓
Merge → {101, 102, 103, 104, 105}
              ↓
Fetch full documents once
```

### Backward Compatibility

**Decision**: Feature flag with fallback to original behavior

**Rationale**:

1. **No Breaking Changes**:
   - All existing code continues to work
   - Original methods preserved
   - Default behavior unchanged

2. **Opt-In**:
   - Users choose to enable multi-model
   - Can disable if issues arise
   - Gradual adoption path

3. **Consistent Interface**:
   - New methods return same types (or compatible)
   - Generator pattern preserved
   - Same workflow integration

**Implementation**:
```python
# Original method still works
query = agent.convert_question(question)

# New method available
result = agent.convert_question_multi_model(question)

# Automatic fallback when disabled
if not config['multi_model_enabled']:
    # Use original single-model logic
    return wrap_in_multi_model_result(single_query)
```

### Type Safety

**Decision**: Use dataclasses for all results

**Rationale**:
- Explicit field types
- IDE autocomplete support
- Runtime type checking (optional)
- Self-documenting code

**Benefits**:
```python
# Type-safe access
result: MultiModelQueryResult = generate_queries(...)
queries: List[str] = result.unique_queries  # IDE knows type
time: float = result.total_generation_time  # Type-checked
```

## Data Flow

### Complete Workflow

```
User Question: "What are the cardiovascular benefits of aspirin?"
    ↓
┌─────────────────────────────────────┐
│ convert_question_multi_model()      │
│ - Check if multi_model_enabled      │
│ - Load configuration                │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ MultiModelQueryGenerator            │
│ generate_queries()                  │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ SERIAL Query Generation             │
│                                     │
│ Model 1: medgemma-27b               │
│   → "aspirin & cardiovascular"      │
│                                     │
│ Model 2: gpt-oss:20b                │
│   → "aspirin & heart & benefit"     │
│                                     │
│ Model 3: medgemma4B                 │
│   → "aspirin & cardiovascular"      │ (duplicate)
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ De-duplicate Queries                │
│ - "aspirin & cardiovascular"        │
│ - "aspirin & heart & benefit"       │
│ (3 queries → 2 unique)              │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ find_abstracts_multi_query()        │
│ - Human review (optional)           │
│ - Query selection                   │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ SERIAL Query Execution              │
│                                     │
│ Query 1: find_abstract_ids()        │
│   → {101, 102, 103, 105}            │
│                                     │
│ Query 2: find_abstract_ids()        │
│   → {102, 104, 105, 106}            │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ Merge ID Sets                       │
│ {101, 102, 103, 105} ∪              │
│ {102, 104, 105, 106}                │
│ = {101, 102, 103, 104, 105, 106}    │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ fetch_documents_by_ids()            │
│ - Batch 1: IDs 101-150              │
│ - Fetch full documents with JOINs   │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ Stream Documents                    │
│ - Generator yields each document    │
│ - Continue with scoring workflow    │
└─────────────────────────────────────┘
```

### Timing Breakdown (Example)

```
Query Generation:      ~6 seconds  (2 models × ~3 sec each)
De-duplication:        ~0.01 sec   (set operations)
ID Query 1:            ~0.2 sec    (fast, no JOINs)
ID Query 2:            ~0.2 sec    (fast, no JOINs)
ID Merge:              ~0.01 sec   (set union)
Document Fetch:        ~1.5 sec    (bulk fetch with JOINs)
────────────────────────────────────────────────────
Total:                 ~8 seconds

Compare to single-model:
Single Query Gen:      ~3 sec
Single ID Query:       ~0.2 sec
Document Fetch:        ~1.5 sec
────────────────────────────────────────────────────
Total:                 ~5 seconds

Overhead: ~3 seconds for ~30% more documents
```

## Extension Points

### Adding New Models

**Steps**:
1. Install model in Ollama: `ollama pull model-name`
2. Add to configuration:
   ```json
   {
     "query_generation": {
       "models": ["existing-model", "new-model-name"]
     }
   }
   ```
3. System automatically uses it (no code changes)

**Requirements**:
- Model must be compatible with Ollama API
- Model must accept system prompts
- Model should return text (not structured output)

### Custom Query Strategies

Extend `MultiModelQueryGenerator` for custom behavior:

```python
class CustomQueryGenerator(MultiModelQueryGenerator):
    """Custom query generation with quality filtering."""

    def generate_queries(
        self,
        question: str,
        system_prompt: str,
        models: List[str],
        queries_per_model: int,
        temperature: float = 0.1
    ) -> MultiModelQueryResult:
        # Call parent method
        result = super().generate_queries(...)

        # Add custom filtering
        filtered_queries = self._filter_by_quality(result.unique_queries)

        # Return modified result
        return MultiModelQueryResult(
            all_queries=result.all_queries,
            unique_queries=filtered_queries,
            ...
        )

    def _filter_by_quality(self, queries: List[str]) -> List[str]:
        """Custom quality filtering logic."""
        # Example: Filter queries that are too short
        return [q for q in queries if len(q.split('&')) >= 2]
```

### Query Quality Metrics

Extend `QueryGenerationResult` to track quality:

```python
@dataclass
class QueryGenerationResult:
    # Existing fields
    model: str
    query: str
    generation_time: float
    temperature: float
    attempt_number: int
    error: Optional[str] = None

    # New fields
    quality_score: Optional[float] = None
    term_count: Optional[int] = None
    complexity_score: Optional[float] = None
```

Then implement quality scoring in generator:

```python
def _score_query_quality(self, query: str) -> float:
    """Score query based on various metrics."""
    terms = query.split('&')
    term_count = len(terms)

    # Simple heuristic: 2-5 terms is good
    if term_count < 2:
        return 0.3  # Too simple
    elif term_count > 5:
        return 0.6  # Too complex
    else:
        return 1.0  # Good
```

### Custom De-duplication

Override `_deduplicate_queries()` for custom logic:

```python
class SemanticQueryGenerator(MultiModelQueryGenerator):
    """De-duplicate based on semantic similarity instead of exact match."""

    def _deduplicate_queries(self, queries: List[str]) -> List[str]:
        """Semantic de-duplication using embeddings."""
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer('all-MiniLM-L6-v2')
        embeddings = model.encode(queries)

        # Cluster similar queries
        unique_indices = self._cluster_similar(embeddings, threshold=0.85)

        return [queries[i] for i in unique_indices]
```

## Testing Strategy

### Unit Tests

**Coverage Target**: >95% for new code

**Test Files**:
- `tests/test_query_generation_data_types.py` - Data structures
- `tests/test_multi_model_generator.py` - Query generation logic
- `tests/test_database_multi_query.py` - Database functions
- `tests/test_query_agent_multi_model.py` - Agent integration

**Testing Without External Dependencies**:

```python
# Test without Ollama
def test_deduplication():
    generator = MultiModelQueryGenerator("http://localhost:11434")
    queries = ["Query 1", "query 1", "Query 2"]
    unique = generator._deduplicate_queries(queries)
    assert len(unique) == 2

# Test without database
def test_fetch_empty_set():
    docs = fetch_documents_by_ids(set())
    assert docs == []
```

### Integration Tests

**Purpose**: Test complete workflow end-to-end

**Requirements**:
- Ollama running with required models
- Database connection available
- Test data in database

**Example**:
```python
def test_multi_model_workflow_integration():
    """Test complete multi-model workflow (requires Ollama + DB)."""
    agent = QueryAgent()

    # Enable multi-model in test config
    with override_config(multi_model_enabled=True):
        docs = list(agent.find_abstracts_multi_query(
            "test question",
            max_rows=10
        ))

        assert len(docs) > 0
        assert all('id' in doc for doc in docs)
```

### Backward Compatibility Tests

**Purpose**: Ensure original behavior preserved

```python
def test_original_methods_still_work():
    """Verify all original methods function correctly."""
    agent = QueryAgent()

    # Original methods
    query = agent.convert_question("test")
    assert isinstance(query, str)

    docs = list(agent.find_abstracts("test", max_rows=5))
    assert len(docs) <= 5
```

## Performance Benchmarks

### Single Model (Baseline)

| Operation | Time |
|-----------|------|
| Query generation | ~1-3 seconds |
| ID query | ~0.2 seconds |
| Document fetch | ~1.5 seconds |
| **Total** | **~2-5 seconds** |

### Multi-Model (2 models, 1 query each)

| Operation | Time |
|-----------|------|
| Query generation | ~3-6 seconds (2 × ~2-3 sec) |
| De-duplication | ~0.01 seconds |
| ID query 1 | ~0.2 seconds |
| ID query 2 | ~0.2 seconds |
| ID merge | ~0.01 seconds |
| Document fetch | ~1.5 seconds |
| **Total** | **~5-8 seconds** |

**Overhead**: ~2-3 seconds (~50% slower)
**Benefit**: ~20-40% more relevant documents

### Multi-Model (3 models, 2 queries each)

| Operation | Time |
|-----------|------|
| Query generation | ~12-18 seconds (6 × ~2-3 sec) |
| De-duplication | ~0.02 seconds |
| ID queries (avg 4 unique) | ~0.8 seconds (4 × ~0.2 sec) |
| ID merge | ~0.01 seconds |
| Document fetch | ~2 seconds (more docs) |
| **Total** | **~15-21 seconds** |

**Overhead**: ~10-15 seconds (~3-4x slower)
**Benefit**: ~40-60% more relevant documents

### Optimization Opportunities

1. **Model caching**: Keep models loaded in Ollama
2. **Query caching**: Cache generated queries for similar questions
3. **Database indexing**: Ensure proper indexes on documents.tsv
4. **Batch size tuning**: Adjust fetch_documents_by_ids batch_size

## Error Handling

### Model Failures

**Scenario**: Ollama model not available or crashes

**Handling**:
```python
try:
    response = ollama_client.generate(model=model, ...)
except Exception as e:
    # Log error
    logger.error(f"Model {model} failed: {e}")

    # Create error result
    result = QueryGenerationResult(
        model=model,
        query="",
        error=str(e),
        ...
    )

    # Continue with other models
    continue
```

**Behavior**: System continues with available models

### Database Failures

**Scenario**: PostgreSQL connection lost

**Handling**:
```python
try:
    ids = find_abstract_ids(query)
except psycopg.OperationalError as e:
    logger.error(f"Database connection failed: {e}")
    # Re-raise (cannot continue without database)
    raise
```

**Behavior**: Fails fast with clear error message

### Invalid Configuration

**Scenario**: Invalid model names or parameters

**Handling**:
```python
def validate_config(config):
    if not config['models']:
        raise ValueError("At least one model required")

    if config['queries_per_model'] < 1 or config['queries_per_model'] > 3:
        raise ValueError("queries_per_model must be 1-3")
```

**Behavior**: Fail at startup with validation error

## Migration Guide

### From Single-Model to Multi-Model

**Step 1**: Enable feature flag
```json
{
  "query_generation": {
    "multi_model_enabled": true
  }
}
```

**Step 2**: Add second model
```json
{
  "query_generation": {
    "models": [
      "medgemma-27b-text-it-Q8_0:latest",
      "gpt-oss:20b"
    ]
  }
}
```

**Step 3**: Test with interactive mode
- Review generated queries
- Verify quality
- Measure performance

**Step 4**: Tune configuration
- Adjust number of models
- Adjust queries per model
- Configure selection options

**Step 5**: Enable auto mode
- Once satisfied with query quality
- For production workflows

### Rollback Strategy

If issues arise, rollback is simple:

```json
{
  "query_generation": {
    "multi_model_enabled": false
  }
}
```

All original functionality is preserved.

---

## Summary

The multi-model query generation architecture provides improved document retrieval through query diversity while maintaining backward compatibility and performance. Key design decisions favor simplicity (serial execution) and efficiency (ID-only queries first) over complexity.

For user-facing documentation, see [Multi-Model Query Generation Guide](../users/multi_model_query_guide.md).
