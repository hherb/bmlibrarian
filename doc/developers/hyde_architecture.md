# HyDE Search Architecture - Developer Documentation

## Overview

This document describes the technical architecture of the HyDE (Hypothetical Document Embeddings) search implementation in BMLibrarian.

## Architecture Principles

### Design Goals

1. **Modular**: Cleanly separated from existing search infrastructure
2. **Consistent**: Follows BaseAgent patterns and conventions
3. **Database-agnostic**: Uses database manager abstraction
4. **LLM-library-based**: All AI operations via ollama library
5. **Testable**: Functions designed for unit testing with mocks

### Key Design Decisions

**No Direct Database Access:**
- All database queries through `database.py` functions
- Prevents SQL injection and maintains abstraction
- Enables easy database backend swapping

**Ollama Library Integration:**
- Uses `ollama.Client` for all LLM operations
- No direct HTTP requests to Ollama server
- Consistent with BaseAgent embedding generation

**Functional Decomposition:**
- Each step (generate, embed, search, fuse) is a separate function
- Enables testing individual components
- Allows reuse in different contexts

## Module Structure

### File Location

```
src/bmlibrarian/agents/utils/hyde_search.py
```

### Module-Level Constants

```python
DEFAULT_RRF_K = 60  # RRF constant from literature
DEFAULT_GENERATION_TEMPERATURE = 0.3  # Low for consistency
DEFAULT_ABSTRACT_LENGTH = 300  # Typical abstract length
DEFAULT_NUM_HYPOTHETICAL_DOCS = 3  # Balance coverage/speed
DEFAULT_EMBEDDING_MODEL_ID = 1  # snowflake-arctic-embed2:latest
```

**Rationale for Values:**
- **RRF_K=60**: Standard value from Cormack et al. (2009)
- **Temperature=0.3**: Low enough for consistency, high enough for variation
- **Abstract Length=300**: Typical PubMed abstract is 250-350 tokens
- **Num Docs=3**: Empirically good balance between coverage and speed

## Core Functions

### 1. generate_hypothetical_documents()

**Purpose**: Generate hypothetical research abstracts using LLM.

**Implementation**:
```python
def generate_hypothetical_documents(
    question: str,
    client: Any,  # ollama.Client
    model: str,
    num_docs: int = DEFAULT_NUM_HYPOTHETICAL_DOCS,
    temperature: float = DEFAULT_GENERATION_TEMPERATURE,
    callback: Optional[callable] = None
) -> List[str]
```

**Key Features:**
- Varied prompts for diversity (research/clinical/scientific)
- System prompt enforces PubMed abstract style
- Error handling per document (continues on failure)
- Progress callbacks for UI integration

**Prompt Engineering:**
```python
system_prompt = """You are a medical research expert. Generate realistic biomedical research abstracts...
- Study design and methods
- Key findings
- Clinical implications
- Specific numerical results when appropriate
"""

# Varied user prompts for diversity:
prompts = [
    f"Write a research abstract that answers: {question}",
    f"Write a clinical study abstract addressing: {question}",
    f"Write a scientific abstract with findings on: {question}"
]
```

**Error Recovery:**
- Continues generating remaining documents if one fails
- Returns partial results (better than complete failure)
- Logs warnings for debugging

### 2. embed_documents()

**Purpose**: Generate embedding vectors for text documents.

**Implementation**:
```python
def embed_documents(
    documents: List[str],
    client: Any,  # ollama.Client
    embedding_model: str,
    callback: Optional[callable] = None
) -> List[List[float]]
```

**Key Features:**
- Sequential embedding generation (simple, reliable)
- Progress tracking per document
- Fails fast on embedding errors (embeddings must be consistent)

**Error Handling:**
- Raises `ConnectionError` on Ollama communication failure
- Validates non-empty embeddings
- Logs embedding dimensions for debugging

### 3. search_with_embedding()

**Purpose**: Search database using vector similarity.

**Implementation**:
```python
def search_with_embedding(
    embedding: List[float],
    max_results: int
) -> List[Tuple[int, str, float]]
```

**Key Features:**
- Uses `database.search_by_embedding()` (no direct SQL)
- Hardcoded `model_id=1` (snowflake-arctic-embed2:latest)
- Converts dict results to tuple format for RRF compatibility

**Database Integration:**
```python
from ...database import search_by_embedding

results_dicts = search_by_embedding(
    embedding=embedding,
    max_results=max_results,
    model_id=DEFAULT_EMBEDDING_MODEL_ID  # Must match database embeddings
)
```

### 4. reciprocal_rank_fusion()

**Purpose**: Fuse multiple ranked lists using RRF algorithm.

**Algorithm**:
```
For each document d in any result list:
    rrf_score(d) = Σ(1 / (k + rank_i))

Where rank_i is the position of d in result list i
```

**Implementation**:
```python
def reciprocal_rank_fusion(
    ranked_lists: List[List[Tuple[int, str, float]]],
    k: int = DEFAULT_RRF_K
) -> List[Tuple[int, str, float]]
```

**Key Features:**
- O(n*m) complexity (n=lists, m=avg_docs_per_list)
- Uses `defaultdict(float)` for efficient accumulation
- Preserves document titles for final results
- Sorts by RRF score descending

**Why RRF?**
- Simple and effective (better than average or max)
- No parameter tuning needed (k=60 is standard)
- Robust to result list length differences
- Well-studied in IR literature

### 5. hyde_search()

**Purpose**: Main entry point orchestrating full HyDE pipeline.

**Implementation**:
```python
def hyde_search(
    question: str,
    client: Any,
    generation_model: str,
    embedding_model: str,
    max_results: int = 100,
    num_hypothetical_docs: int = DEFAULT_NUM_HYPOTHETICAL_DOCS,
    similarity_threshold: float = 0.7,
    callback: Optional[callable] = None
) -> List[Dict[str, Any]]
```

**Pipeline Steps:**

1. **Generate** hypothetical documents (LLM)
2. **Embed** hypothetical documents (embedding model)
3. **Search** with each embedding (database)
4. **Fuse** results with RRF
5. **Filter** and normalize scores

**Score Normalization:**
```python
# Min-max normalization to 0-1 range
max_score = fused_results[0][2]
min_score = fused_results[-1][2]
score_range = max_score - min_score if max_score > min_score else 1.0

normalized_score = (rrf_score - min_score) / score_range
```

**Rationale**: Makes RRF scores comparable across queries and enables threshold filtering.

## Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│                      User Question                          │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│         generate_hypothetical_documents()                    │
│  • Uses: ollama.Client.generate()                           │
│  • Model: generation_model (medgemma-27b, etc.)             │
│  • Output: List[str] (3 hypothetical abstracts)             │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│              embed_documents()                               │
│  • Uses: ollama.Client.embeddings()                         │
│  • Model: embedding_model (snowflake-arctic-embed2)         │
│  • Output: List[List[float]] (3 x 1024-dim vectors)         │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│        search_with_embedding() x3                            │
│  • Uses: database.search_by_embedding()                     │
│  • Query: pgvector cosine similarity                        │
│  • Output: 3 x List[Tuple] (3 ranked lists)                 │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│         reciprocal_rank_fusion()                             │
│  • Algorithm: RRF with k=60                                  │
│  • Input: 3 ranked lists                                     │
│  • Output: Single fused ranked list                          │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│      Normalize & Filter                                      │
│  • Min-max normalization to 0-1                              │
│  • Apply similarity_threshold (default: 0.7)                 │
│  • Format as List[Dict]                                      │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│                  Final Results                               │
│  [{'id': int, 'title': str, 'score': float, ...}]          │
└─────────────────────────────────────────────────────────────┘
```

## Database Integration

### Vector Search Function

**Location**: `src/bmlibrarian/database.py:search_by_embedding()`

**Optimized Query** (after code review fixes):
```sql
SELECT DISTINCT c.document_id AS id,
       d.title,
       1 - (e.embedding <=> %s::vector) AS similarity
FROM emb_1024 e
JOIN chunks c ON e.chunk_id = c.id
JOIN document d ON c.document_id = d.id
WHERE e.model_id = %s
ORDER BY similarity DESC  -- More intuitive than distance ASC
LIMIT %s
```

**Parameters**: `(embedding, model_id, max_results)`

**Changes from Original:**
- Removed duplicate embedding parameter
- Changed ORDER BY to computed similarity column
- Simpler, faster, more maintainable

### Model ID Mapping

**Critical**: `model_id` must match database embedding model:

```python
# Database configuration
model_id = 1  # snowflake-arctic-embed2:latest

# Must match BaseAgent default
embedding_model = "snowflake-arctic-embed2:latest"
```

**Verification Query**:
```sql
SELECT id, model_name FROM embedding_models;
-- Should show: 1 | snowflake-arctic-embed2:latest
```

## Performance Characteristics

### Time Complexity

| Operation | Complexity | Notes |
|-----------|------------|-------|
| Document generation | O(n*m) | n=num_docs, m=avg_tokens |
| Embedding generation | O(n*d) | n=num_docs, d=embedding_dim |
| Vector search | O(n*log(k)) | n=num_docs, k=db_size (with index) |
| RRF fusion | O(n*m) | n=num_lists, m=docs_per_list |
| Total | O(n*m + n*d + n*log(k)) | Dominated by LLM generation |

### Space Complexity

| Component | Space | Notes |
|-----------|-------|-------|
| Hypothetical docs | O(n*m) | n=3, m~=300 tokens (~3KB) |
| Embeddings | O(n*d) | n=3, d=1024 floats (~12KB) |
| Search results | O(n*k) | n=3, k=100 docs (~30KB) |
| Fused results | O(k) | k=max_results (~10KB) |
| Total | ~55KB | Minimal memory footprint |

### Bottlenecks

1. **LLM Generation** (5-15s): Slowest operation
   - Sequential document generation
   - Network roundtrip to Ollama
   - Model inference time

2. **Embedding Generation** (1-3s/doc): Moderate
   - Sequential embedding calls
   - Could be parallelized for speed

3. **Vector Search** (<1s/query): Fast
   - pgvector with proper indexes is very efficient
   - Multiple queries still complete quickly

## Error Handling

### Exception Hierarchy

```
ConnectionError
├── Ollama server unreachable
├── Model not available
└── Empty response from model

ValueError
├── Empty hypothetical documents
├── Invalid embedding dimensions
└── Malformed search results

RuntimeError
└── Database connection failures
```

### Recovery Strategies

**Document Generation Failures:**
```python
try:
    doc = generate_one_document(...)
    hypothetical_docs.append(doc)
except Exception as e:
    logger.error(f"Failed document {i}: {e}")
    # Continue with other documents (partial success OK)
```

**Embedding Failures:**
```python
try:
    embedding = generate_embedding(doc)
except Exception as e:
    # FAIL FAST - embeddings must be consistent
    raise ConnectionError(f"Failed to generate embedding: {e}")
```

**Search Failures:**
- Handled by database manager
- Raises clear exceptions
- No partial result recovery (all-or-nothing)

## Testing Strategy

### Unit Tests

**Test File**: `tests/test_hyde_search.py`

**Coverage Areas:**

1. **Document Generation**
   ```python
   def test_generate_hypothetical_documents_success(mock_client):
       mock_client.generate.return_value = {'response': 'Abstract text...'}
       docs = generate_hypothetical_documents(...)
       assert len(docs) == 3
   ```

2. **Embedding Generation**
   ```python
   def test_embed_documents_success(mock_client):
       mock_client.embeddings.return_value = {'embedding': [0.1] * 1024}
       embeddings = embed_documents(...)
       assert len(embeddings[0]) == 1024
   ```

3. **RRF Algorithm**
   ```python
   def test_reciprocal_rank_fusion():
       list1 = [(1, "Doc 1", 0.9), (2, "Doc 2", 0.8)]
       list2 = [(2, "Doc 2", 0.95), (3, "Doc 3", 0.7)]
       fused = reciprocal_rank_fusion([list1, list2], k=60)
       # Doc 2 should rank highest (appears in both)
       assert fused[0][0] == 2
   ```

4. **Score Normalization**
   ```python
   def test_score_normalization():
       results = hyde_search(..., similarity_threshold=0.7)
       for doc in results:
           assert 0 <= doc['score'] <= 1
           assert doc['score'] >= 0.7  # Threshold applied
   ```

### Integration Tests

**With Real Ollama** (optional, slower):
```python
@pytest.mark.integration
def test_hyde_search_end_to_end():
    client = ollama.Client(host="http://localhost:11434")
    results = hyde_search(
        "What are cardiovascular benefits of exercise?",
        client,
        "medgemma-27b-text-it-Q8_0:latest",
        "snowflake-arctic-embed2:latest"
    )
    assert len(results) > 0
    assert all('id' in doc for doc in results)
```

### Mocking Strategy

**Mock Ollama Client:**
```python
@pytest.fixture
def mock_ollama_client():
    client = Mock()
    client.generate.return_value = {
        'response': 'Hypothetical abstract text...'
    }
    client.embeddings.return_value = {
        'embedding': [0.1] * 1024
    }
    return client
```

**Mock Database:**
```python
@patch('bmlibrarian.agents.utils.hyde_search.search_by_embedding')
def test_search_with_embedding(mock_search):
    mock_search.return_value = [
        {'id': 1, 'title': 'Doc 1', 'similarity': 0.9}
    ]
    results = search_with_embedding([0.1] * 1024, 100)
    assert len(results) == 1
```

## Configuration Integration

### Config File Structure

```json
{
  "search_strategy": {
    "hyde": {
      "enabled": true,
      "max_results": 100,
      "generation_model": "medgemma-27b-text-it-Q8_0:latest",
      "embedding_model": "snowflake-arctic-embed2:latest",
      "num_hypothetical_docs": 3,
      "similarity_threshold": 0.7
    }
  }
}
```

### Loading Configuration

```python
from bmlibrarian.config import BMLibrarianConfig

config = BMLibrarianConfig()
hyde_config = config.get_search_strategy_config('hyde')

if hyde_config.get('enabled', False):
    results = hyde_search(
        question,
        client,
        hyde_config['generation_model'],
        hyde_config['embedding_model'],
        max_results=hyde_config['max_results'],
        num_hypothetical_docs=hyde_config['num_hypothetical_docs'],
        similarity_threshold=hyde_config['similarity_threshold']
    )
```

## Future Enhancements

### Parallel Embedding Generation

**Current**: Sequential embedding calls
**Proposed**: Parallel calls with `asyncio` or `ThreadPoolExecutor`

```python
from concurrent.futures import ThreadPoolExecutor

def embed_documents_parallel(documents, client, model):
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [
            executor.submit(client.embeddings, model=model, prompt=doc)
            for doc in documents
        ]
        return [f.result()['embedding'] for f in futures]
```

**Benefit**: 2-3x faster embedding generation

### Caching

**Query Cache**: Store hypothetical documents for repeated queries
```python
@lru_cache(maxsize=100)
def generate_hypothetical_documents_cached(question, ...):
    return generate_hypothetical_documents(question, ...)
```

**Benefit**: Instant results for repeated queries

### Adaptive RRF

**Current**: Fixed k=60
**Proposed**: Adapt k based on result list similarity

```python
def adaptive_rrf(ranked_lists):
    overlap = calculate_list_overlap(ranked_lists)
    k = 30 if overlap > 0.5 else 60  # Lower k when lists agree
    return reciprocal_rank_fusion(ranked_lists, k=k)
```

**Benefit**: Better fusion when lists have high/low overlap

### Quality Metrics

**Track and log**:
- Hypothetical document diversity (TF-IDF distance)
- Result list overlap (Jaccard similarity)
- RRF score distribution

**Purpose**: Helps tune parameters and diagnose issues

## Related Documentation

- [User Guide](../users/hyde_guide.md) - End-user documentation
- [Query Agent](../users/query_agent_guide.md) - Natural language query processing
- [Database Schema](database_schema.md) - Vector storage and indexing

## References

- Gao, L., et al. (2022). "Precise Zero-Shot Dense Retrieval without Relevance Labels." arXiv:2212.10496.
- Cormack, G. V., et al. (2009). "Reciprocal rank fusion outperforms condorcet and individual rank learning methods." SIGIR 2009.
- Xiong, L., et al. (2021). "Approximate Nearest Neighbor Negative Contrastive Learning for Dense Text Retrieval." ICLR 2021.
