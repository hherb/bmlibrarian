# Map-Reduce Synthesis System

## Architecture Overview

The map-reduce synthesis system in `ReportingAgent` addresses context window limitations when processing large citation sets. It implements a classic map-reduce pattern adapted for LLM-based text synthesis.

## Problem Statement

When the ReportingAgent attempts to synthesize many citations (e.g., 30+) into a report, all citations are typically packed into a single prompt. This can:

1. Exceed the model's context window
2. Cause empty responses or truncated output
3. Degrade report quality due to attention dilution

The error manifests as:
```
ERROR - Generate request failed after 72791.66ms (attempt 3/3): Empty response from model
ERROR - Failed to generate structured report: Empty response from model
```

## Solution: Map-Reduce Pattern

### Class Constants and Configuration

```python
# Class-level defaults (reporting_agent.py)
MAP_REDUCE_CITATION_THRESHOLD = 15  # Citation count trigger
MAP_BATCH_SIZE = 8                   # Citations per batch
MAP_PASSAGE_MAX_LENGTH = 500         # Max chars per passage in MAP phase
```

Instance attributes are loaded from `config.json` via `_load_map_reduce_config()`:
- `map_reduce_citation_threshold`
- `map_batch_size`
- `effective_context_limit`
- `map_passage_max_length`

### Method Overview

| Method | Purpose |
|--------|---------|
| `_estimate_citation_tokens()` | Estimates token count using ~4 chars/token heuristic |
| `_should_use_map_reduce()` | Determines if map-reduce is needed |
| `_map_phase_summarize_batch()` | Extracts themes from a citation batch |
| `_reduce_phase_synthesize()` | Synthesizes all themes into final report |
| `map_reduce_synthesis()` | Orchestrates the full map-reduce workflow |

### Flow Diagram

```
structured_synthesis()
        │
        ▼
_should_use_map_reduce(citations)
        │
        ├─── False ──► Direct synthesis (existing code)
        │
        └─── True ───► map_reduce_synthesis()
                              │
                              ▼
                      Split into batches
                              │
                              ▼
                ┌─────────────────────────────┐
                │      MAP PHASE              │
                │  For each batch:            │
                │  _map_phase_summarize_batch │
                │  Extract themes, findings   │
                └─────────────────────────────┘
                              │
                              ▼
                ┌─────────────────────────────┐
                │     REDUCE PHASE            │
                │  _reduce_phase_synthesize   │
                │  Combine all themes into    │
                │  coherent report            │
                └─────────────────────────────┘
                              │
                              ▼
                      Return report content
```

## Implementation Details

### Token Estimation

```python
def _estimate_citation_tokens(self, citations: List[Citation]) -> int:
    total_chars = 0
    for citation in citations:
        total_chars += len(citation.document_title or "")
        total_chars += len(citation.summary or "")
        total_chars += len(citation.passage or "")
        total_chars += 100  # Template overhead
    return total_chars // 4  # ~4 chars per token
```

### Trigger Conditions

Map-reduce activates when either:
1. `len(citations) > map_reduce_citation_threshold` (default: 15)
2. `estimated_tokens > effective_context_limit` (default: 6000)

### MAP Phase Output Schema

Each batch produces:
```json
{
    "themes": [
        {
            "theme": "Brief theme description",
            "key_finding": "One sentence summary",
            "supporting_refs": [1, 2, 3],
            "evidence_strength": "strong/moderate/limited"
        }
    ],
    "contradictions": ["Any contradictory findings"],
    "batch_relevance": "high/medium/low",
    "batch_number": 1,
    "citation_count": 8,
    "reference_numbers": [1, 2, 3, 4, 5, 6, 7, 8]
}
```

### REDUCE Phase Output Schema

```json
{
    "introduction": "2-3 sentences answering the research question",
    "evidence_discussion": "3-4 paragraphs with [X] citations",
    "conclusion": "1-2 sentences summarizing findings",
    "themes_integrated": ["List of theme topics covered"]
}
```

## Error Handling

### Batch Failures
If a batch fails during MAP phase, processing continues with remaining batches:
```python
if batch_summary:
    batch_summaries.append(batch_summary)
else:
    logger.warning(f"Batch {batch_num} failed, continuing with remaining batches")
```

### Complete Failure
If all batches fail, returns `None`:
```python
if not batch_summaries:
    logger.error("All batches failed in map phase")
    return None
```

## Callbacks

The system emits callbacks for progress tracking:

| Callback Event | Message |
|----------------|---------|
| `map_reduce_started` | "Large citation set (N), using map-reduce synthesis" |
| `map_phase_progress` | "Processing citation batch X/Y" |
| `reduce_phase_started` | "Synthesizing evidence themes" |

## Configuration Integration

Settings are loaded from `config.json`:
```json
{
    "agents": {
        "reporting": {
            "map_reduce_citation_threshold": 15,
            "map_batch_size": 8,
            "effective_context_limit": 6000,
            "map_passage_max_length": 500
        }
    }
}
```

## Testing

### Unit Test Coverage

Test the following:
1. `_estimate_citation_tokens()` - Returns positive integer
2. `_should_use_map_reduce()` - Correctly triggers above threshold
3. `_should_use_map_reduce()` - Correctly skips below threshold
4. Configuration loading - Falls back to defaults on error

### Example Test

```python
from bmlibrarian.agents.reporting_agent import ReportingAgent, Citation

agent = ReportingAgent(show_model_info=False)

# Test small set
small_citations = [Citation(...) for _ in range(5)]
assert agent._should_use_map_reduce(small_citations) == False

# Test large set
large_citations = [Citation(...) for _ in range(20)]
assert agent._should_use_map_reduce(large_citations) == True
```

## Golden Rules Compliance

| Rule | Compliance |
|------|------------|
| No magic numbers | All thresholds use named constants/config |
| Type hints | All new methods fully typed |
| Docstrings | All new methods documented |
| Ollama library | Uses `_generate_from_prompt()` only |
| Error handling | All exceptions logged |
| No data truncation | Passage truncation is configurable, not hardcoded |

## Future Improvements

1. **Adaptive batch sizing**: Automatically adjust batch size based on passage lengths
2. **Parallel MAP phase**: Process batches concurrently (requires thread safety)
3. **Hierarchical reduction**: For very large sets (100+ citations), reduce in multiple stages
4. **Theme deduplication**: Merge similar themes before REDUCE phase

## See Also

- [reporting_agent.py](../../src/bmlibrarian/agents/reporting_agent.py) - Implementation
- [config.py](../../src/bmlibrarian/config.py) - Configuration defaults
- [User Guide](../users/map_reduce_synthesis_guide.md) - End-user documentation
