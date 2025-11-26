# Map-Reduce Synthesis System

## Architecture Overview

The map-reduce synthesis system in `ReportingAgent` addresses context window limitations when processing large citation sets. It implements a classic map-reduce pattern adapted for LLM-based text synthesis, enhanced with UUID-based reference tracking for reliable citation preservation.

## Problem Statement

When the ReportingAgent attempts to synthesize many citations (e.g., 30+) into a report, all citations are typically packed into a single prompt. This can:

1. Exceed the model's context window
2. Cause empty responses or truncated output
3. Degrade report quality due to attention dilution
4. **Reference confusion**: Sequential reference numbers can be confused between batches

The error manifests as:
```
ERROR - Generate request failed after 72791.66ms (attempt 3/3): Empty response from model
ERROR - Failed to generate structured report: Empty response from model
```

## Solution: Map-Reduce Pattern with UUID References

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
| `_map_phase_summarize_batch()` | Extracts themes from a citation batch using UUID refs |
| `_reduce_phase_synthesize()` | Synthesizes all themes into final report using UUID refs |
| `map_reduce_synthesis()` | Orchestrates the full map-reduce workflow |
| `_validate_reference_numbers()` | Validates sequential reference numbers (direct synthesis) |
| `_validate_uuid_references()` | Validates UUID reference IDs (map-reduce synthesis) |
| `_convert_uuid_refs_to_sequential()` | Converts UUID refs to sequential numbers in final output |

### CitationRef Dataclass

```python
@dataclass
class CitationRef:
    """Reference identifier for tracking citations through map-reduce synthesis."""
    ref_id: str                    # Unique ID (format: REF_XXXXXXXX)
    document_id: str               # Database document ID
    citation: Citation             # Original Citation object
    final_number: Optional[int]    # Sequential number (assigned in post-processing)

    @classmethod
    def generate_ref_id(cls) -> str:
        """Generate UUID-based ref_id like 'REF_a7b3c2d1'."""

    @classmethod
    def from_citation(cls, citation: Citation) -> 'CitationRef':
        """Create CitationRef from a Citation object."""
```

### Flow Diagram

```
structured_synthesis()
        │
        ▼
_should_use_map_reduce(citations)
        │
        ├─── False ──► Direct synthesis (sequential refs)
        │
        └─── True ───► map_reduce_synthesis()
                              │
                              ▼
                ┌─────────────────────────────┐
                │  CREATE UUID REFERENCES     │
                │  CitationRef.from_citation  │
                │  for each citation          │
                │  (e.g., REF_a7b3c2d1)       │
                └─────────────────────────────┘
                              │
                              ▼
                      Split into batches
                              │
                              ▼
                ┌─────────────────────────────┐
                │      MAP PHASE              │
                │  For each batch:            │
                │  _map_phase_summarize_batch │
                │  Extract themes with UUIDs  │
                │  [REF_a7b3c2d1], etc.       │
                └─────────────────────────────┘
                              │
                              ▼
                ┌─────────────────────────────┐
                │     REDUCE PHASE            │
                │  _reduce_phase_synthesize   │
                │  Combine themes into report │
                │  Using UUID references      │
                └─────────────────────────────┘
                              │
                              ▼
                ┌─────────────────────────────┐
                │    POST-PROCESSING          │
                │  _convert_uuid_refs_to_     │
                │  sequential()               │
                │  [REF_abc] → [1], [2], etc. │
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

Each batch produces (with UUID references):
```json
{
    "themes": [
        {
            "theme": "Brief theme description",
            "key_finding": "One sentence summary",
            "supporting_refs": ["REF_a7b3c2d1", "REF_e4f5g6h7"],
            "evidence_strength": "strong/moderate/limited"
        }
    ],
    "contradictions": ["Any contradictory findings"],
    "batch_relevance": "high/medium/low",
    "batch_number": 1,
    "citation_count": 8,
    "ref_ids": ["REF_a7b3c2d1", "REF_e4f5g6h7", "REF_i8j9k0l1", ...]
}
```

### REDUCE Phase Output Schema

```json
{
    "introduction": "2-3 sentences answering the research question",
    "evidence_discussion": "3-4 paragraphs with [REF_XXXXXXXX] citations",
    "conclusion": "1-2 sentences summarizing findings",
    "themes_integrated": ["List of theme topics covered"]
}
```

### Post-Processing Output

The `_convert_uuid_refs_to_sequential()` method:
1. Finds all UUID references in order of first appearance
2. Assigns sequential numbers (1, 2, 3, ...)
3. Replaces `[REF_a7b3c2d1]` with `[1]`, etc.
4. Updates `CitationRef.final_number` for each reference
5. Returns converted content and mapping dictionary

## Reference Number Preservation (UUID-Based System)

A critical requirement is that reference numbers must be preserved throughout the map-reduce process. The UUID-based system solves the reference confusion problem by using unique identifiers that cannot be mixed up between batches.

### Why UUIDs?

With sequential numbers, processing batches independently caused confusion:
- Batch 1 uses references [1], [2], [3]
- Batch 2 uses references [4], [5], [6]
- LLM might confuse [1] in batch 1 with [1] in batch 2 during REDUCE

UUID-based refs like `[REF_a7b3c2d1]` are:
- **Unique**: No two citations share the same identifier
- **Non-sequential**: Cannot be confused between batches
- **Traceable**: Easy to map back to original citations

### 1. UUID Reference Creation
- `CitationRef` objects are created at the start of `map_reduce_synthesis()`
- Each citation gets a unique `ref_id` like `REF_a7b3c2d1`
- The same `CitationRef` objects are used throughout MAP and REDUCE phases

### 2. Reference List in REDUCE Prompt
The REDUCE phase receives a complete reference list with UUID identifiers:
```
Available References (use these exact reference IDs in your citations):
[REF_a7b3c2d1] Smith et al. Study of cardiovascular effects... (2023)
[REF_e4f5g6h7] Johnson et al. Long-term outcomes in... (2022)
[REF_i8j9k0l1] Williams et al. Meta-analysis of... (2024)
```

### 3. Reference Validation
After the REDUCE phase generates content, `_validate_uuid_references()` checks:
- All `[REF_XXXXXXXX]` patterns in the content are extracted
- Invalid reference IDs (not in the valid set) trigger warnings
- Missing references are logged at debug level

```python
# Example validation output
logger.info("UUID reference validation: 8 unique refs used, 0 invalid, 8 valid")
logger.warning("Generated content contains invalid reference IDs: ['REF_invalid1']. Expected IDs from: ['REF_a7b3c2d1', ...]...")
```

### 4. Post-Processing Conversion
After REDUCE phase, `_convert_uuid_refs_to_sequential()` converts:
- `[REF_a7b3c2d1]` → `[1]`
- `[REF_e4f5g6h7]` → `[2]`
- Numbers assigned in order of first appearance in text
- Final output uses familiar sequential numbering

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
5. `CitationRef.generate_ref_id()` - Returns valid format `REF_XXXXXXXX`
6. `CitationRef.from_citation()` - Creates valid CitationRef from Citation
7. `_validate_uuid_references()` - Detects invalid UUID refs
8. `_convert_uuid_refs_to_sequential()` - Correctly converts UUIDs to numbers

### Example Tests

```python
from bmlibrarian.agents.reporting_agent import ReportingAgent, CitationRef, Citation

agent = ReportingAgent(show_model_info=False)

# Test small set
small_citations = [Citation(...) for _ in range(5)]
assert agent._should_use_map_reduce(small_citations) == False

# Test large set
large_citations = [Citation(...) for _ in range(20)]
assert agent._should_use_map_reduce(large_citations) == True

# Test CitationRef generation
ref_id = CitationRef.generate_ref_id()
assert ref_id.startswith('REF_')
assert len(ref_id) == 12  # REF_ + 8 hex chars

# Test UUID reference conversion
content = "Study [REF_a1b2c3d4] found that [REF_e5f6g7h8] confirmed results."
citation_refs = [
    CitationRef(ref_id='REF_a1b2c3d4', document_id='doc1', citation=mock_citation1),
    CitationRef(ref_id='REF_e5f6g7h8', document_id='doc2', citation=mock_citation2),
]
converted, mapping = agent._convert_uuid_refs_to_sequential(content, citation_refs)
assert converted == "Study [1] found that [2] confirmed results."
assert mapping == {'REF_a1b2c3d4': 1, 'REF_e5f6g7h8': 2}
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
