# PaperChecker Verdict Analysis System

## Overview

The verdict analysis system provides the final evaluation step in the PaperChecker workflow. It analyzes counter-evidence reports to determine whether the evidence supports, contradicts, or is undecided about the original research claims. The system uses LLM-based analysis with three-level classification and confidence scoring.

## Architecture

### Component Design

The `VerdictAnalyzer` is a standalone component in `src/bmlibrarian/paperchecker/components/verdict_analyzer.py` that:

1. **Analyzes Individual Verdicts**: Evaluates each counter-report against its original statement
2. **Generates Overall Assessment**: Aggregates individual verdicts into a comprehensive summary
3. **Maintains Objectivity**: Uses structured prompts to ensure evidence-based conclusions

```
CounterReport (from Step 6)
         │
         ▼
   _validate_inputs()
         │
         ▼
   _build_verdict_prompt()
         │
         ▼
    _call_llm() ─── Ollama Client
         │
         ▼
   _parse_response()
         │
         ▼
   _validate_verdict_data()
         │
         ▼
      Verdict (to Step 8)
```

### Integration with PaperCheckerAgent

The VerdictAnalyzer integrates with `PaperCheckerAgent` through two methods:

1. **`_analyze_verdict(statement, counter_report)`**: Delegates to `VerdictAnalyzer.analyze()`
2. **`_generate_overall_assessment(statements, verdicts)`**: Delegates to `VerdictAnalyzer.generate_overall_assessment()`

## Verdict Classification

### Three-Level Verdict Categories

| Verdict | Description | When to Use |
|---------|-------------|-------------|
| **contradicts** | Counter-evidence contradicts the original statement | Multiple studies or high-quality evidence supports the counter-claim |
| **supports** | Counter-evidence supports the original statement | Counter-search failed to find contradictory evidence; found studies confirm original |
| **undecided** | Evidence is mixed, insufficient, or unclear | Mixed results, too few studies, significant limitations |

### Three-Level Confidence Scoring

| Confidence | Description | Indicators |
|------------|-------------|------------|
| **high** | Strong, consistent evidence | Multiple high-quality sources, consistent findings |
| **medium** | Moderate evidence | Some limitations or minor inconsistencies |
| **low** | Weak or limited evidence | Few studies, significant limitations, uncertain |

## Methods

### `analyze(statement, counter_report) -> Verdict`

Main analysis method that evaluates counter-evidence against an original statement.

**Parameters:**
- `statement`: Original `Statement` being fact-checked
- `counter_report`: `CounterReport` containing counter-evidence summary and citations

**Returns:**
- `Verdict` object with classification, confidence, and rationale

**Process:**
1. Validate inputs (non-empty statement text and summary)
2. Build verdict prompt with evidence context
3. Call LLM via Ollama library
4. Parse and validate JSON response
5. Create Verdict object with metadata

### `generate_overall_assessment(statements, verdicts) -> str`

Generates aggregate assessment across all analyzed statements.

**Parameters:**
- `statements`: List of all `Statement` objects
- `verdicts`: List of `Verdict` objects (one per statement)

**Returns:**
- Human-readable assessment string

**Assessment Logic:**

| Scenario | Assessment |
|----------|------------|
| All supported | "All N statement(s) were supported..." |
| All contradicted | "All N statement(s) were contradicted..." |
| All undecided | "Evidence for all N statement(s) was mixed..." |
| Majority contradicted | "The majority of statements (X/N) were contradicted..." |
| Majority supported | "The majority of statements (X/N) were supported..." |
| Mixed (no majority) | "Mixed results across N statements: X supported, Y contradicted, Z undecided..." |

### Private Methods

#### `_build_verdict_prompt(statement, counter_report) -> str`

Constructs the LLM prompt for verdict analysis. The prompt includes:
- Original statement text and type
- Counter-evidence summary
- Search statistics (documents found, scored, cited)
- Detailed classification instructions
- JSON output format specification

#### `_call_llm(prompt, max_retries, retry_delay) -> str`

Calls Ollama API with exponential backoff retry logic.

**Features:**
- Uses `ollama.Client.chat()` (per golden rule #4)
- Retry on transient errors (timeout, connection)
- Exponential backoff (1s, 2s, 4s)
- Response time logging

#### `_parse_response(response) -> Dict[str, str]`

Parses LLM response into structured data. Handles:
- Pure JSON responses
- JSON in ```json code blocks
- JSON in ``` code blocks
- JSON embedded in surrounding text

#### `_extract_json(response) -> str`

Extracts JSON from various LLM response formats.

**Extraction Order:**
1. Look for ```json code block
2. Look for ``` code block
3. Find first `{` to last `}` in text
4. Return as-is (let JSON parser handle)

#### `_validate_verdict_data(data) -> None`

Validates parsed verdict data against schema:
- Required fields: verdict, confidence, rationale
- Valid verdict values: supports, contradicts, undecided
- Valid confidence values: high, medium, low
- Minimum rationale length: 20 characters

## Configuration

The VerdictAnalyzer uses configuration from `~/.bmlibrarian/config.json`:

```json
{
  "paper_checker": {
    "model": "gpt-oss:20b",
    "temperature": 0.3
  }
}
```

### Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `model` | "gpt-oss:20b" | Ollama model name for analysis |
| `temperature` | 0.3 | LLM temperature (lower = more deterministic) |

## Data Flow

### Input: Statement + CounterReport

```python
Statement(
    text="Metformin is superior to GLP-1 agonists",
    context="...",
    statement_type="finding",
    confidence=0.9,
    statement_order=1
)

CounterReport(
    summary="Multiple RCTs show GLP-1 superior to metformin...",
    num_citations=3,
    citations=[...],
    search_stats={
        "documents_found": 50,
        "documents_scored": 25,
        "citations_extracted": 3
    },
    generation_metadata={...}
)
```

### Output: Verdict

```python
Verdict(
    verdict="contradicts",
    rationale="Multiple high-quality RCTs demonstrate superior glycemic control with GLP-1 agonists compared to metformin. The meta-analysis shows consistent results (p<0.001).",
    confidence="high",
    counter_report=<CounterReport>,
    analysis_metadata={
        "model": "gpt-oss:20b",
        "temperature": 0.3,
        "timestamp": "2024-01-15T10:30:00",
        "statement_order": 1
    }
)
```

## LLM Prompt Structure

The verdict prompt follows this structure:

```
[Expert Role]
You are an expert medical researcher evaluating scientific evidence.

[Task Description]
Analyze whether the counter-evidence found supports, contradicts, or is undecided...

[Original Statement]
"{statement.text}"
Type: {statement.statement_type}

[Counter-Evidence Summary]
{counter_report.summary}

[Search Statistics]
- Documents found: X
- Documents scored: Y
- Citations extracted: Z

[Classification Instructions]
1. Determine Verdict (with examples)
2. Determine Confidence Level (with criteria)
3. Write Rationale (2-3 sentences)

[Important Guidelines]
- Base verdict ONLY on provided evidence
- Do NOT add external knowledge
- Use "undecided" when genuinely uncertain

[Output Format]
Return ONLY valid JSON: {"verdict": "...", "confidence": "...", "rationale": "..."}
```

## Error Handling

### Validation Errors (ValueError)
- Empty statement text
- Empty counter-report summary
- Invalid verdict value
- Invalid confidence value
- Rationale too short (<20 chars)
- Missing required JSON fields

### Runtime Errors (RuntimeError)
- LLM connection failure
- Empty LLM response
- All retries exhausted
- JSON parsing failure (after extraction attempts)

### Graceful Degradation
- Individual LLM failures trigger retries
- Validation errors are logged and re-raised
- Connection errors provide helpful error messages

## Testing

Tests are located in `tests/test_verdict_analyzer.py`:

### Test Categories

| Category | Tests |
|----------|-------|
| Initialization | 3 tests for constructor options |
| Prompt Building | 6 tests for prompt content |
| JSON Extraction | 6 tests for various formats |
| Validation | 11 tests for data validation |
| Response Parsing | 5 tests for parse logic |
| Overall Assessment | 10 tests for aggregation logic |
| Full Analysis | 5 tests with mocked LLM |
| Connection Test | 3 tests for connectivity |
| Input Validation | 4 tests for input checks |
| Edge Cases | 8 tests for boundary conditions |

**Total: 60 tests**

### Running Tests

```bash
# Run all verdict analyzer tests
uv run python -m pytest tests/test_verdict_analyzer.py -v

# Run specific test class
uv run python -m pytest tests/test_verdict_analyzer.py::TestGenerateOverallAssessment -v
```

## Performance Considerations

### Expected Performance

| Operation | Time |
|-----------|------|
| Single verdict analysis | ~2-5 seconds (Ollama) |
| LLM retry (on failure) | +1s, +2s, +4s |
| Overall assessment | <1ms (no LLM call) |

### Optimization Notes

1. **Low Temperature**: Uses 0.3 for deterministic outputs
2. **Structured Output**: JSON format reduces parsing complexity
3. **No Retries for Validation**: Validation errors fail immediately
4. **Cached Assessment**: Overall assessment computed locally, no LLM

## Golden Rules Compliance

| Rule | Implementation |
|------|----------------|
| #2 No magic numbers | Uses constants: `MIN_RATIONALE_LENGTH`, `DEFAULT_TEMPERATURE` |
| #4 Ollama library | Uses `ollama.Client.chat()`, not HTTP requests |
| #6 Type hints | All parameters and returns annotated |
| #7 Docstrings | All methods documented |
| #8 Error handling | All errors logged and raised appropriately |
| #13 Tests | 60 unit tests with full coverage |

## Related Documentation

- [Architecture Overview](../planning/paperchecker/00_ARCHITECTURE_OVERVIEW.md)
- [Verdict Analysis Planning](../planning/paperchecker/10_VERDICT_ANALYSIS.md)
- [Counter Report Generation](paperchecker_counter_report_generation.md)
- [Document Scoring](paperchecker_document_scoring.md)
- [Data Models](paperchecker_data_models.md)
