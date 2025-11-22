# PaperChecker Document Scoring Integration

## Overview

The document scoring integration provides relevance scoring for documents found during counter-evidence search in the PaperChecker workflow. It uses the existing `DocumentScoringAgent` from BMLibrarian to evaluate how well each document supports the counter-statement.

## Architecture

### Integration with Existing Components

The document scoring step (Step 4 in the workflow) integrates with:

1. **DocumentScoringAgent**: Reuses the existing BMLibrarian agent for consistent scoring
2. **DatabaseManager**: Fetches document data using the project's database abstraction
3. **SearchResults**: Receives document IDs and provenance from multi-strategy search
4. **ScoredDocument**: Produces dataclass objects with scores and provenance

```
SearchResults (from Step 3)
         │
         ▼
    _fetch_documents()  ─── DatabaseManager
         │
         ▼
  _build_scoring_question()
         │
         ▼
   DocumentScoringAgent.evaluate_document()
         │
         ▼
  _get_score_explanation()
         │
         ▼
     ScoredDocument (to Step 5)
```

## Methods

### `_score_documents(counter_stmt, search_results) -> List[ScoredDocument]`

Main scoring method that processes all documents from search results.

**Parameters:**
- `counter_stmt`: CounterStatement containing original and negated claims
- `search_results`: SearchResults with deduplicated document IDs and provenance

**Returns:**
- List of `ScoredDocument` objects for documents above the score threshold, sorted by score (descending)

**Features:**
- Batch processing for efficiency
- Early stopping when enough high-scoring documents found
- Error recovery (continues on individual document failures)
- Provenance preservation from search strategies

### `_fetch_documents(doc_ids) -> Dict[int, Dict[str, Any]]`

Fetches full document data from the database.

**Parameters:**
- `doc_ids`: List of document IDs to fetch

**Returns:**
- Dictionary mapping document ID to document data

**Database Query:**
```sql
SELECT id, title, abstract, authors, publication_date,
       publication AS journal, pmid, doi, source_id
FROM document
WHERE id = ANY(%s)
```

### `_build_scoring_question(counter_stmt) -> str`

Constructs the scoring question for the DocumentScoringAgent.

The question frames scoring in terms of:
1. Finding evidence that SUPPORTS the counter-statement
2. Finding evidence that CONTRADICTS the original claim

**Example output:**
```
Does this document provide evidence that supports or relates to
the following claim: GLP-1 agonists are superior or equivalent to metformin?
We are looking for evidence that contradicts:
Metformin is superior to GLP-1 agonists for type 2 diabetes
```

### `_get_score_explanation(score, document, reasoning) -> str`

Generates human-readable explanation for a document's score.

Combines:
- Reasoning from DocumentScoringAgent
- Document title (truncated if > 100 chars)

## Configuration

Add to `~/.bmlibrarian/config.json`:

```json
{
  "paper_checker": {
    "score_threshold": 3.0,
    "scoring": {
      "batch_size": 20,
      "early_stop_count": 20
    }
  }
}
```

### Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `score_threshold` | 3.0 | Minimum score for document inclusion (1-5 scale) |
| `scoring.batch_size` | 20 | Documents processed per batch for logging |
| `scoring.early_stop_count` | 20 | Stop after finding this many high-scoring docs (0=disabled) |

## Data Flow

### Input: SearchResults

```python
SearchResults(
    semantic_docs=[1, 2, 3],
    hyde_docs=[2, 3, 4],
    keyword_docs=[3, 4, 5],
    deduplicated_docs=[1, 2, 3, 4, 5],
    provenance={
        1: ["semantic"],
        2: ["semantic", "hyde"],
        3: ["semantic", "hyde", "keyword"],
        4: ["hyde", "keyword"],
        5: ["keyword"]
    },
    search_metadata={...}
)
```

### Output: List[ScoredDocument]

```python
[
    ScoredDocument(
        doc_id=3,
        document={"id": 3, "title": "...", "abstract": "..."},
        score=5,
        explanation="Highly relevant - directly addresses...",
        supports_counter=True,
        found_by=["semantic", "hyde", "keyword"]
    ),
    ScoredDocument(
        doc_id=2,
        document={"id": 2, "title": "...", "abstract": "..."},
        score=4,
        explanation="Very relevant - provides strong evidence...",
        supports_counter=True,
        found_by=["semantic", "hyde"]
    ),
    # ... more documents sorted by score descending
]
```

## Performance Considerations

### Expected Performance

| Scenario | Time |
|----------|------|
| Per-document scoring | ~1-2 seconds (Ollama) |
| 50 documents (serial) | ~50-100 seconds |
| 50 documents (with early stopping) | ~20-40 seconds |

### Optimization Strategies

1. **Early Stopping**: Stop scoring when `early_stop_count` documents found
2. **Batch Logging**: Progress tracking per batch
3. **Error Recovery**: Continue on individual failures

## Error Handling

The implementation follows graceful degradation:

1. **Empty search results**: Returns empty list (no error)
2. **Database fetch failure**: Returns empty dict (logs error)
3. **Individual document scoring failure**: Logs error, continues with other docs
4. **All documents below threshold**: Returns empty list (normal operation)

## Testing

Tests are located in `tests/test_paperchecker_agent.py` under `TestPaperCheckerDocumentScoring`:

- `test_build_scoring_question`: Verifies question construction
- `test_get_score_explanation_with_title`: Tests explanation generation
- `test_get_score_explanation_long_title_truncated`: Tests title truncation
- `test_fetch_documents_empty_list`: Empty input handling
- `test_score_documents_empty_search_results`: Empty search results
- `test_score_documents_filters_below_threshold`: Threshold filtering
- `test_score_documents_sorted_descending`: Sort order verification
- `test_score_documents_preserves_provenance`: Provenance preservation

## Golden Rules Compliance

1. **Database through DatabaseManager**: Uses `get_db_manager()` (Rule 5)
2. **No magic numbers**: Uses constants like `DEFAULT_SCORING_BATCH_SIZE` (Rule 2)
3. **Type hints**: All methods have complete type annotations (Rule 6)
4. **Docstrings**: All methods documented (Rule 7)
5. **Error handling**: All exceptions caught, logged, and handled (Rule 8)

## Related Documentation

- [Architecture Overview](../planning/paperchecker/00_ARCHITECTURE_OVERVIEW.md)
- [Document Scoring Planning](../planning/paperchecker/07_DOCUMENT_SCORING.md)
- [Search Coordinator System](search_coordinator_system.md)
- [Agent Module](agent_module.md)
