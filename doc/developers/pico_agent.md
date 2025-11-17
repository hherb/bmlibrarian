# PICO Agent Developer Documentation

## Overview

The `PICOAgent` is a specialized agent that extracts structured PICO (Population, Intervention, Comparison, Outcome) components from biomedical research papers. It follows the standard BaseAgent architecture and provides robust extraction with confidence scoring and retry logic.

## Architecture

### Class Hierarchy

```
BaseAgent (base.py)
    ↓
PICOAgent (pico_agent.py)
```

### Core Components

1. **PICOExtraction** (dataclass): Represents extracted PICO components with metadata
2. **PICOAgent** (class): Main agent for extraction logic
3. **Statistics Tracking**: Built-in extraction performance monitoring

## API Reference

### PICOExtraction Dataclass

```python
@dataclass
class PICOExtraction:
    """Represents extracted PICO components from a study."""

    # Core PICO components (required)
    population: str
    intervention: str
    comparison: str
    outcome: str

    # Metadata (required)
    document_id: str
    document_title: str
    extraction_confidence: float  # 0-1 overall confidence

    # Optional enrichment fields
    study_type: Optional[str] = None  # e.g., "RCT", "cohort study"
    sample_size: Optional[str] = None  # e.g., "N=150"
    pmid: Optional[str] = None
    doi: Optional[str] = None

    # Component-level confidence scores
    population_confidence: Optional[float] = None
    intervention_confidence: Optional[float] = None
    comparison_confidence: Optional[float] = None
    outcome_confidence: Optional[float] = None

    # Timestamp
    created_at: Optional[datetime] = None  # Auto-set in __post_init__
```

### PICOAgent Class

#### Constructor

```python
def __init__(
    self,
    model: str = "gpt-oss:20b",
    host: str = "http://localhost:11434",
    temperature: float = 0.1,
    top_p: float = 0.9,
    max_tokens: int = 2000,
    callback: Optional[Callable[[str, str], None]] = None,
    orchestrator=None,
    show_model_info: bool = True,
    max_retries: int = 3
)
```

**Parameters**:
- `model`: Ollama model name (default: gpt-oss:20b for high accuracy)
- `host`: Ollama server URL
- `temperature`: Low value (0.1) for consistent, factual extraction
- `top_p`: Nucleus sampling parameter
- `max_tokens`: Maximum response length (2000 sufficient for detailed PICO)
- `callback`: Progress callback function(step: str, data: str)
- `orchestrator`: Optional orchestrator for queue-based processing
- `show_model_info`: Display initialization info
- `max_retries`: Retry attempts for failed extractions

#### Core Methods

##### extract_pico_from_document()

```python
def extract_pico_from_document(
    self,
    document: Dict[str, Any],
    min_confidence: float = 0.5
) -> Optional[PICOExtraction]
```

**Purpose**: Extract PICO components from a single document

**Parameters**:
- `document`: Dictionary with keys:
  - `id` (required): Document identifier
  - `title` (required): Paper title
  - `abstract` (required if no full_text): Paper abstract
  - `full_text` (optional): Complete paper text (preferred over abstract)
  - `pmid` (optional): PubMed ID
  - `doi` (optional): Digital Object Identifier
  - `publication_date` (optional): Publication date

- `min_confidence`: Minimum overall confidence threshold (0.0-1.0)
  - 0.8-1.0: High confidence (systematic reviews)
  - 0.5-0.7: Medium confidence (screening)
  - 0.3-0.5: Low confidence (exploratory)

**Returns**:
- `PICOExtraction` object if successful and confidence >= threshold
- `None` if extraction failed, confidence too low, or no text available

**Process Flow**:
1. Validate Ollama connection
2. Get document text (prefer full_text, fall back to abstract)
3. Truncate text if > 8000 characters (preserve context limits)
4. Build extraction prompt with detailed instructions
5. Call LLM with retry logic (via `_generate_and_parse_json()`)
6. Parse JSON response
7. Validate required fields
8. Check confidence threshold
9. Create and return `PICOExtraction` object
10. Update statistics

**Error Handling**:
- Returns `None` on Ollama connection failure
- Returns `None` on missing text
- Returns `None` on parse failure after max retries
- Returns `None` on missing required PICO fields
- Returns `None` on confidence below threshold
- Logs all failures for debugging

##### extract_pico_batch()

```python
def extract_pico_batch(
    self,
    documents: List[Dict[str, Any]],
    min_confidence: float = 0.5,
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> List[PICOExtraction]
```

**Purpose**: Extract PICO from multiple documents with progress tracking

**Parameters**:
- `documents`: List of document dictionaries
- `min_confidence`: Minimum confidence threshold
- `progress_callback`: Optional callback(current: int, total: int, title: str)

**Returns**: List of successful `PICOExtraction` objects (excludes failures)

**Usage Example**:
```python
def show_progress(current, total, doc_title):
    print(f"[{current}/{total}] {doc_title[:50]}...")

extractions = agent.extract_pico_batch(
    documents=docs,
    progress_callback=show_progress
)
```

##### get_extraction_stats()

```python
def get_extraction_stats(self) -> Dict[str, Any]
```

**Purpose**: Get extraction performance statistics

**Returns**: Dictionary with:
- `total_extractions`: Total attempted
- `successful_extractions`: Successfully extracted
- `failed_extractions`: Failed to extract
- `low_confidence_extractions`: Below confidence threshold
- `parse_failures`: JSON parse errors
- `success_rate`: successful / total (0.0-1.0)

##### format_pico_summary()

```python
def format_pico_summary(self, extraction: PICOExtraction) -> str
```

**Purpose**: Format PICO extraction as human-readable text

**Returns**: Multi-line formatted string with all PICO components

##### export_to_json()

```python
def export_to_json(
    self,
    extractions: List[PICOExtraction],
    output_file: str
) -> None
```

**Purpose**: Export extractions to JSON file with metadata

**Output Structure**:
```json
{
  "extractions": [
    {
      "population": "...",
      "intervention": "...",
      "comparison": "...",
      "outcome": "...",
      "extraction_confidence": 0.95,
      "document_id": "12345",
      "document_title": "...",
      "study_type": "RCT",
      "sample_size": "N=150",
      "pmid": "12345",
      "doi": "10.1000/x",
      "population_confidence": 0.9,
      "intervention_confidence": 0.95,
      "comparison_confidence": 0.9,
      "outcome_confidence": 0.95,
      "created_at": "2025-01-15T10:30:00Z"
    }
  ],
  "metadata": {
    "total_extractions": 1,
    "extraction_date": "2025-01-15T10:30:00Z",
    "agent_model": "gpt-oss:20b",
    "statistics": {...}
  }
}
```

##### export_to_csv()

```python
def export_to_csv(
    self,
    extractions: List[PICOExtraction],
    output_file: str
) -> None
```

**Purpose**: Export extractions to CSV for systematic review tools

**CSV Columns**:
- `document_id`, `document_title`, `pmid`, `doi`
- `study_type`, `sample_size`
- `population`, `intervention`, `comparison`, `outcome`
- `population_confidence`, `intervention_confidence`, `comparison_confidence`, `outcome_confidence`
- `extraction_confidence`, `created_at`

## Prompt Engineering

### Extraction Prompt Structure

The agent uses a carefully crafted prompt with:

1. **Role Definition**: "You are a medical research expert..."
2. **Task Description**: Extract PICO components
3. **Detailed Instructions**: For each PICO component with examples
4. **Confidence Scoring**: Guidelines for 0.0-1.0 scale
5. **Critical Requirements**:
   - Extract ONLY information actually present in text
   - DO NOT invent or fabricate information
   - Use "Not clearly stated" for missing components
   - Calculate overall_confidence as average of component confidences
6. **Response Format**: JSON schema with all required fields
7. **Strict Output**: "Respond ONLY with valid JSON"

### Confidence Scoring Guidelines

The prompt instructs the LLM to score each component:

- **1.0**: Explicitly stated, no ambiguity
- **0.8**: Clearly stated but some details missing
- **0.6**: Can be inferred but not explicit
- **0.4**: Partially mentioned, significant uncertainty
- **0.2**: Barely mentioned, high uncertainty
- **0.0**: Not found in text

### Handling Missing Information

The agent explicitly instructs the LLM to:
- Write "Not clearly stated" for missing PICO components
- Give low confidence scores (0.0-0.4) for uncertain extractions
- Never fabricate or assume information

This ensures extractions are truthful and verifiable.

## Internal Implementation Details

### Text Preprocessing

```python
# Prefer full text if available
text_to_analyze = full_text if full_text else abstract

# Truncate to avoid context limit issues
if len(text_to_analyze) > 8000:
    text_to_analyze = text_to_analyze[:8000] + "..."
```

**Rationale**:
- 8000 characters ≈ 2000 tokens (safe for most models)
- Preserves complete introduction/methods sections
- Prevents out-of-memory errors

### JSON Parsing with Retry

Uses `BaseAgent._generate_and_parse_json()`:

```python
pico_data = self._generate_and_parse_json(
    prompt,
    max_retries=self.max_retries,
    retry_context=f"PICO extraction (doc {doc_id})",
    num_predict=self.max_tokens
)
```

**Features**:
- Automatic retry on JSON parse failures
- Regenerates LLM response (not just re-parse)
- Detailed logging of retry attempts
- Raises `JSONDecodeError` after max retries exhausted

### Statistics Tracking

```python
self._extraction_stats = {
    'total_extractions': 0,
    'successful_extractions': 0,
    'failed_extractions': 0,
    'low_confidence_extractions': 0,
    'parse_failures': 0
}
```

Updated throughout extraction lifecycle:
- `total_extractions`: Incremented on every attempt
- `successful_extractions`: Incremented on successful extraction
- `failed_extractions`: Incremented on errors/exceptions
- `low_confidence_extractions`: Incremented when confidence < threshold
- `parse_failures`: Incremented on JSON parse errors

## Integration with BMLibrarian

### Configuration System

The agent integrates with BMLibrarian's configuration:

```python
from bmlibrarian.config import get_model, get_agent_config

# Get configured model
model = get_model('pico_agent')  # Returns "gpt-oss:20b" by default

# Get agent configuration
config = get_agent_config('pico')
agent = PICOAgent(
    model=model,
    **config  # temperature, top_p, max_tokens, etc.
)
```

### Factory Pattern

Create via AgentFactory:

```python
from bmlibrarian.agents import AgentFactory

agent = AgentFactory.create_agent('pico')
```

### Database Integration

Extract PICO from documents in database:

```python
from bmlibrarian.database import get_db_manager

db_manager = get_db_manager()
with db_manager.get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT id, title, abstract FROM document LIMIT 100")
        documents = [
            {
                'id': row[0],
                'title': row[1],
                'abstract': row[2]
            }
            for row in cur.fetchall()
        ]

extractions = agent.extract_pico_batch(documents)
```

## Testing

### Unit Tests

See `tests/test_pico_agent.py` for comprehensive test suite:

- Initialization tests
- Successful extraction tests
- Error handling tests (low confidence, missing fields, parse errors)
- Batch processing tests
- Export tests (JSON, CSV)
- Statistics tracking tests
- Callback integration tests

### Running Tests

```bash
uv run python -m pytest tests/test_pico_agent.py -v
```

### Test Coverage

The test suite covers:
- ✓ Agent initialization
- ✓ PICO extraction success path
- ✓ Low confidence filtering
- ✓ Missing abstract/text handling
- ✓ Incomplete PICO fields
- ✓ JSON parse errors
- ✓ Connection failures
- ✓ Batch processing
- ✓ Progress callbacks
- ✓ Statistics tracking
- ✓ Export to JSON
- ✓ Export to CSV
- ✓ Text truncation
- ✓ Dataclass methods

## Performance Considerations

### Extraction Speed

Approximate times (with gpt-oss:20b on M1 Mac):
- Single document: 3-5 seconds
- Batch of 10: 30-50 seconds
- Batch of 100: 5-8 minutes

**Optimization Tips**:
1. Use batch processing (`extract_pico_batch()` not individual calls)
2. Use smaller models for initial screening (medgemma-27b)
3. Process documents in parallel (future enhancement)
4. Filter documents before extraction (e.g., by study type metadata)

### Memory Usage

- Minimal memory overhead (~10 MB per agent instance)
- Document text truncated to 8000 chars (prevents OOM)
- Batch processing handles lists of any size
- Export methods write incrementally (no memory bottleneck)

### Model Selection

| Model | Speed | Accuracy | Use Case |
|-------|-------|----------|----------|
| gpt-oss:20b | Slow | High | Systematic reviews, meta-analyses |
| medgemma-27b | Medium | Medium-High | General screening |
| medgemma4B | Fast | Medium | Initial filtering only |

## Extension Points

### Custom Extraction Schema

Extend `PICOExtraction` for specialized fields:

```python
from dataclasses import dataclass
from bmlibrarian.agents import PICOExtraction

@dataclass
class ExtendedPICOExtraction(PICOExtraction):
    """Extended PICO with additional fields."""
    study_duration: Optional[str] = None
    funding_source: Optional[str] = None
    registration_number: Optional[str] = None  # ClinicalTrials.gov
```

### Custom Prompts

Subclass `PICOAgent` to customize prompts:

```python
class CustomPICOAgent(PICOAgent):
    def extract_pico_from_document(self, document, min_confidence=0.5):
        # Custom prompt engineering
        custom_prompt = self._build_custom_prompt(document)
        # ... rest of implementation
```

### Integration with Orchestrator

Submit PICO extraction as queue tasks:

```python
from bmlibrarian.agents import AgentOrchestrator, PICOAgent

orchestrator = AgentOrchestrator(max_workers=4)
agent = PICOAgent(orchestrator=orchestrator)

# Submit batch tasks (future enhancement)
task_ids = agent.submit_pico_extraction_tasks(
    documents=documents,
    priority=TaskPriority.NORMAL
)

# Wait for completion
results = orchestrator.wait_for_completion(task_ids)
```

## Common Pitfalls

### 1. Using Abstracts Instead of Full Text

**Problem**: Abstracts often lack detailed PICO components

**Solution**: Extract full text from PDFs when available

### 2. Setting Confidence Too High

**Problem**: `min_confidence=0.9` rejects most extractions

**Solution**: Use 0.5-0.7 for initial screening, manually verify high-impact papers

### 3. Not Checking Statistics

**Problem**: Low success rate goes unnoticed

**Solution**: Always check `get_extraction_stats()` after batch processing

### 4. Ignoring Component Confidence

**Problem**: Using overall confidence but missing low-quality individual components

**Solution**: Check individual component confidences for critical analyses

### 5. Processing Too Many Documents at Once

**Problem**: Long batch processing times without feedback

**Solution**: Use `progress_callback` and process in smaller batches (10-50 documents)

## Future Enhancements

Planned features:

1. **Parallel Processing**: Process documents concurrently
2. **Queue Integration**: Submit PICO tasks to AgentOrchestrator
3. **Incremental Export**: Stream results to CSV/JSON during processing
4. **PICO Validation**: Cross-check extracted components against metadata
5. **Enhanced Confidence**: Machine learning model for confidence calibration
6. **Multi-Model Extraction**: Use ensemble of models for improved accuracy
7. **Interactive Refinement**: Allow users to refine extractions iteratively

## Related Documentation

- [BaseAgent Architecture](agent_module.md)
- [Configuration System](../users/configuration.md)
- [User Guide](../users/pico_agent_guide.md)
- [Testing Guide](testing.md)

## References

1. [PICO Framework - Cochrane](https://www.cochrane.org/glossary/5#letterpico)
2. [Evidence-Based Medicine Toolkit](https://guides.mclibrary.duke.edu/ebm/pico)
3. [BMLibrarian Architecture](agent_module.md)
