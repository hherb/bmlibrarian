# PaperChecker Counter-Report Generation

## Overview

The counter-report generation system synthesizes extracted citations into coherent prose reports that summarize evidence supporting counter-statements. It uses LLM-based text generation to create professional medical-style writing with inline citations.

## Architecture

### Integration with Existing Components

The report generation step (Step 6 in the workflow) integrates with:

1. **BaseAgent**: Inherits `_generate_from_prompt()` for Ollama integration
2. **ExtractedCitation**: Receives citations from citation extraction step
3. **CounterReport**: Produces dataclass with summary, citations, and statistics
4. **SearchResults**: Uses statistics for transparency metadata

```
ExtractedCitation[] (from Step 5)
         │
         ▼
    _build_report_prompt()
         │
         ▼
   _call_llm_for_report()  ─── BaseAgent._generate_from_prompt()
         │
         ▼
  _parse_report_response()
         │
         ▼
 _calculate_search_stats()
         │
         ▼
     CounterReport (to Step 7)
```

## Methods

### `_generate_counter_report(counter_stmt, citations, search_results, scored_docs) -> CounterReport`

Main report generation method that synthesizes citations into prose.

**Parameters:**
- `counter_stmt`: CounterStatement being reported on
- `citations`: List of ExtractedCitation objects to synthesize
- `search_results`: SearchResults for statistics (documents found per strategy)
- `scored_docs`: List of ScoredDocument for statistics (scoring results)

**Returns:**
- `CounterReport` with prose summary, citations, and search statistics

**Raises:**
- `RuntimeError`: If report generation fails after retries

**Features:**
- Handles empty citations gracefully (generates empty report)
- Includes search statistics for transparency
- Records generation metadata (model, timestamp)

### `_build_report_prompt(counter_stmt, citations) -> str`

Constructs the LLM prompt for report generation.

**Parameters:**
- `counter_stmt`: CounterStatement containing the claim to report on
- `citations`: List of ExtractedCitation objects with passages

**Returns:**
- Formatted prompt string for LLM generation

**Prompt Structure:**
1. Task description (200-300 word summary)
2. Claim context (counter-statement and original)
3. Evidence citations (numbered with passages and sources)
4. Detailed instructions (9 guidelines)
5. Writing style requirements
6. Output format specification

### `_call_llm_for_report(prompt) -> str`

Calls Ollama API using BaseAgent's infrastructure.

**Parameters:**
- `prompt`: The formatted prompt for report generation

**Returns:**
- Raw response string from the LLM

**Configuration:**
- Uses `report_max_tokens` from config (default: 4000)
- Uses `temperature` from config (default: 0.3)

**Note:** Uses `_generate_from_prompt()` from BaseAgent, which interfaces with the `ollama` library as per project guidelines.

### `_parse_report_response(response) -> str`

Parses and cleans LLM report response.

**Parameters:**
- `response`: Raw response string from LLM

**Returns:**
- Cleaned report text

**Raises:**
- `ValueError`: If generated report is too short (< 50 chars)

**Cleaning Operations:**
1. Strips whitespace
2. Removes common prefixes (Summary:, Report:, etc.)
3. Removes markdown code block wrappers
4. Validates minimum length

### `_generate_empty_report(counter_stmt, search_results, scored_docs) -> CounterReport`

Generates minimal report when no citations are available.

**Parameters:**
- `counter_stmt`: CounterStatement that was searched for
- `search_results`: SearchResults with document counts
- `scored_docs`: ScoredDocument list (may be empty)

**Returns:**
- CounterReport with empty citations but populated statistics

**Output:**
Creates explanatory message noting no substantial evidence was found, including the score threshold used and number of documents searched.

### `_calculate_search_stats(search_results, scored_docs, citations) -> Dict[str, Any]`

Calculates search statistics for report metadata.

**Parameters:**
- `search_results`: SearchResults with strategy-specific counts
- `scored_docs`: List of scored documents
- `citations`: List of extracted citations

**Returns:**
- Dictionary with document counts and search strategy breakdown:
  - `documents_found`: Total deduplicated documents
  - `documents_scored`: Documents that were scored
  - `documents_cited`: Unique documents with citations
  - `citations_extracted`: Total citation count
  - `search_strategies`: Breakdown by semantic/hyde/keyword

## Configuration

Add to `~/.bmlibrarian/config.json`:

```json
{
  "agents": {
    "paper_checker": {
      "temperature": 0.3,
      "report_max_tokens": 4000
    }
  }
}
```

### Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `temperature` | 0.3 | LLM creativity (lower = more consistent) |
| `report_max_tokens` | 4000 | Maximum tokens for report generation |

## Constants

Defined in `src/bmlibrarian/paperchecker/agent.py`:

```python
DEFAULT_REPORT_TEMPERATURE = 0.3
DEFAULT_REPORT_MAX_TOKENS = 4000
DEFAULT_MIN_REPORT_LENGTH = 50

REPORT_PREFIXES_TO_STRIP = (
    "Summary:",
    "Report:",
    "Counter-Evidence Summary:",
    "Here is the summary:",
    "Here's the summary:",
    "**Summary:**",
    "**Report:**",
)
```

## Data Flow

### Input: ExtractedCitation[]

```python
[
    ExtractedCitation(
        doc_id=1,
        passage="GLP-1 agonists demonstrated superior HbA1c reduction...",
        relevance_score=5,
        full_citation="Smith J, et al. Diabetes Care. 2023. doi:...",
        metadata={"pmid": 12345678, "year": 2023},
        citation_order=1
    ),
    ExtractedCitation(
        doc_id=2,
        passage="Meta-analysis of 20 trials showed...",
        relevance_score=4,
        full_citation="Jones A, et al. JAMA. 2022. doi:...",
        metadata={"pmid": 23456789, "year": 2022},
        citation_order=2
    )
]
```

### Output: CounterReport

```python
CounterReport(
    summary="Evidence from multiple studies supports the efficacy of "
            "GLP-1 agonists. In a 2023 study, Smith et al. demonstrated "
            "superior HbA1c reduction [1]. Furthermore, a meta-analysis by "
            "Jones et al. in 2022 showed improved cardiovascular outcomes [2].",
    num_citations=2,
    citations=[...],  # Original ExtractedCitation objects
    search_stats={
        "documents_found": 50,
        "documents_scored": 30,
        "documents_cited": 2,
        "citations_extracted": 2,
        "search_strategies": {
            "semantic": 20,
            "hyde": 25,
            "keyword": 15
        }
    },
    generation_metadata={
        "model": "gpt-oss:20b",
        "temperature": 0.3,
        "timestamp": "2024-01-15T10:30:00"
    }
)
```

## Prompt Engineering

The report prompt follows specific guidelines for medical writing:

### Instructions Given to LLM

1. Synthesize evidence into coherent narrative
2. Reference citations using [1], [2], etc. inline
3. Use professional medical writing style
4. Include specific findings, statistics, and years
5. Do NOT use vague temporal references (use specific years)
6. Do NOT overstate evidence beyond citations
7. Do NOT add information not in citations
8. Organize by themes or study types if relevant
9. Note any limitations or contradictions

### Writing Style Requirements

- Professional and objective tone
- Evidence-based assertions only
- Clear and concise
- Focus on findings, not methodology
- Present tense for established findings, past tense for specific studies

## Performance Considerations

### Expected Performance

| Scenario | Time |
|----------|------|
| Report generation | ~5-10 seconds (Ollama) |
| Empty report generation | ~1 ms (no LLM call) |

### Token Budget

- Typical prompt: ~1000-2000 tokens (depending on citation count)
- Typical response: ~300-500 tokens
- Maximum response: 4000 tokens (configurable)

## Error Handling

The implementation follows graceful degradation:

1. **Empty citations**: Generates empty report with statistics (no error)
2. **LLM connection failure**: Raises RuntimeError with original exception
3. **Too short response**: Raises ValueError with length details
4. **Parse failure**: Attempts cleanup before validation

## Testing

Tests are located in `tests/test_paperchecker_agent.py` under `TestPaperCheckerCounterReportGeneration`:

- `test_build_report_prompt`: Verifies prompt construction
- `test_parse_report_response_clean`: Clean response parsing
- `test_parse_report_response_with_prefix`: Prefix removal
- `test_parse_report_response_with_code_blocks`: Code block unwrapping
- `test_parse_report_response_too_short_raises`: Validation
- `test_generate_empty_report`: Empty report generation
- `test_calculate_search_stats`: Statistics calculation
- `test_generate_counter_report_with_citations`: Full report generation
- `test_generate_counter_report_empty_citations`: Empty citation handling
- `test_counter_report_to_markdown`: Markdown conversion

## Golden Rules Compliance

1. **Ollama through library**: Uses `_generate_from_prompt()` from BaseAgent (Rule 4)
2. **No magic numbers**: Uses constants like `DEFAULT_REPORT_MAX_TOKENS` (Rule 2)
3. **Type hints**: All methods have complete type annotations (Rule 6)
4. **Docstrings**: All methods documented (Rule 7)
5. **Error handling**: All exceptions caught, logged, and handled (Rule 8)
6. **No hardcoded paths**: No file paths in report generation (Rule 3)

## Markdown Output

The `CounterReport.to_markdown()` method generates formatted output:

```markdown
## Counter-Evidence Summary

Evidence from multiple studies supports the efficacy of GLP-1 agonists.
In a 2023 study, Smith et al. demonstrated superior HbA1c reduction [1].
Furthermore, a meta-analysis by Jones et al. in 2022 showed improved
cardiovascular outcomes [2].

### References

1. Smith J, et al. GLP-1 vs Metformin Study. Diabetes Care. 2023. doi:10.1234/example
2. Jones A, et al. GLP-1 Meta-Analysis. JAMA. 2022. doi:10.1234/another

---
*Search Statistics: 50 documents found, 30 scored, 2 cited*
*Generated with gpt-oss:20b at 2024-01-15T10:30:00*
```

## Related Documentation

- [Architecture Overview](../planning/paperchecker/00_ARCHITECTURE_OVERVIEW.md)
- [Counter Report Generation Planning](../planning/paperchecker/09_COUNTER_REPORT_GENERATION.md)
- [Citation Extraction System](paperchecker_citation_extraction.md)
- [Document Scoring Integration](paperchecker_document_scoring.md)
- [Agent Module](agent_module.md)
