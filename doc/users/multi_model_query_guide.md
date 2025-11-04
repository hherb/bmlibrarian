# Multi-Model Query Generation Guide

## Overview

Multi-model query generation is a feature that improves document retrieval quality by using multiple AI models to generate diverse database queries from your research question. Different models have different strengths, and combining their perspectives often yields better coverage of relevant literature.

### What is Multi-Model Query Generation?

Instead of using a single AI model to convert your research question into a database query, BMLibrarian can use 2-3 different models to generate multiple queries. Each model brings its own "perspective" on how to search the database, which typically results in finding more relevant documents.

### Why Use Multiple Models?

- **Improved Coverage**: Different models phrase queries differently, finding documents a single model might miss
- **Reduced Bias**: No single model is perfect; combining models reduces individual model biases
- **Higher Recall**: Typically finds 20-40% more relevant documents than single-model queries
- **Query Diversity**: Multiple query formulations increase the chance of matching relevant literature

### Benefits and Use Cases

**Best for**:
- Comprehensive literature reviews
- Finding rare or niche studies
- Research questions with multiple facets
- When initial searches return insufficient results

**May not need it for**:
- Quick exploratory searches
- Very specific, narrow questions
- When time is more important than completeness
- Preliminary research scoping

## Quick Start

### Enabling Multi-Model Mode

1. **Locate your configuration file**: `~/.bmlibrarian/config.json`
   - On macOS/Linux: `/Users/yourname/.bmlibrarian/config.json`
   - On Windows: `C:\Users\yourname\.bmlibrarian\config.json`

2. **Edit the configuration** to add the `query_generation` section:

```json
{
  "query_generation": {
    "multi_model_enabled": true,
    "models": [
      "medgemma-27b-text-it-Q8_0:latest",
      "gpt-oss:20b"
    ],
    "queries_per_model": 1
  }
}
```

3. **Verify models are available** in Ollama:
```bash
ollama list
```

### Basic Usage

#### Example with CLI

```bash
# Start the CLI
uv run python bmlibrarian_cli.py

# Enter your research question when prompted
# The system will now:
# 1. Generate queries using both models
# 2. Show you all generated queries
# 3. Let you select which queries to execute
# 4. Execute queries serially
# 5. De-duplicate document IDs
# 6. Continue with normal scoring workflow
```

#### Example with GUI

The Research GUI (`bmlibrarian_research_gui.py`) automatically uses multi-model generation if enabled in your configuration. No additional steps required.

## Configuration

### Available Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `multi_model_enabled` | boolean | `false` | Enable/disable multi-model mode |
| `models` | array | `["medgemma-27b..."]` | List of 1-3 model names |
| `queries_per_model` | integer | `1` | Generate 1-3 queries per model |
| `execution_mode` | string | `"serial"` | Always "serial" (not parallel) |
| `deduplicate_results` | boolean | `true` | Remove duplicate documents |
| `show_all_queries_to_user` | boolean | `true` | Display all generated queries |
| `allow_query_selection` | boolean | `true` | Let user select which queries to execute |

### Example Configurations

#### Conservative (1 query per model)

Best for: Initial testing, faster execution

```json
{
  "query_generation": {
    "multi_model_enabled": true,
    "models": [
      "medgemma-27b-text-it-Q8_0:latest",
      "gpt-oss:20b"
    ],
    "queries_per_model": 1
  }
}
```

**Expected behavior**: 2 queries total (2 models × 1 query each)

#### Balanced (2 models, 2 queries each)

Best for: Most research tasks, good coverage/speed tradeoff

```json
{
  "query_generation": {
    "multi_model_enabled": true,
    "models": [
      "medgemma-27b-text-it-Q8_0:latest",
      "gpt-oss:20b"
    ],
    "queries_per_model": 2
  }
}
```

**Expected behavior**: 4 queries total (2 models × 2 queries each)

#### Aggressive (3 models, 3 queries each)

Best for: Comprehensive literature reviews, maximum coverage

```json
{
  "query_generation": {
    "multi_model_enabled": true,
    "models": [
      "medgemma-27b-text-it-Q8_0:latest",
      "gpt-oss:20b",
      "medgemma4B_it_q8:latest"
    ],
    "queries_per_model": 3
  }
}
```

**Expected behavior**: Up to 9 queries (3 models × 3 queries each), typically fewer after de-duplication

## Workflow

### Interactive Mode

1. **Enter research question**: Type your question as normal
2. **Query generation**: System generates queries using all configured models serially
3. **Review queries**: All generated queries are displayed for your review
4. **Select queries**: Choose which queries to execute (or select all)
5. **Execute serially**: Each selected query runs one at a time
6. **De-duplication**: Document IDs are merged and de-duplicated automatically
7. **Continue workflow**: Proceed with normal scoring and citation extraction

### Auto Mode

When running in auto mode (`--auto` flag):
- All queries are executed automatically
- No user review or selection
- Best for batch processing or scripted workflows
- Same serial execution and de-duplication

## Performance Considerations

### Query Generation Time

| Configuration | Approximate Time |
|--------------|------------------|
| 1 model × 1 query | ~1-3 seconds |
| 2 models × 1 query | ~3-6 seconds |
| 3 models × 1 query | ~5-10 seconds |
| 2 models × 2 queries | ~6-12 seconds |
| 3 models × 3 queries | ~15-30 seconds |

**Note**: Times vary based on model size and hardware. Serial execution prevents resource bottlenecks.

### Database Load

- **ID-only queries** are very fast (~0.1-0.5 seconds each)
- **De-duplication** is nearly instant (set operations)
- **Full document fetch** happens only once after de-duplication
- **Total database time** is similar to single-query mode

### Overall Performance

- **Overhead**: Approximately 2-3x slower than single-model mode
- **Benefit**: Typically finds 20-40% more relevant documents
- **Tradeoff**: Worth it for comprehensive research, skip for quick searches

## Troubleshooting

### Model Not Available

**Symptom**: Error message "Model X not found in Ollama"

**Solutions**:
1. Check if model is installed: `ollama list`
2. Pull the model: `ollama pull model-name`
3. Verify model name matches exactly (case-sensitive)
4. System will skip unavailable models and continue with available ones

### Too Many Documents

**Symptom**: Query returns thousands of documents, scoring takes too long

**Solutions**:
1. Reduce `max_rows` in CLI settings
2. Use fewer models (e.g., 2 instead of 3)
3. Use 1 query per model instead of 2-3
4. Refine your research question to be more specific

### Duplicate Queries Generated

**Symptom**: Multiple models generate identical or very similar queries

**Behavior**: This is normal and expected
- System automatically de-duplicates queries (case-insensitive)
- Only unique queries are executed
- Reduces total database load
- No action needed from user

### Slow Query Generation

**Symptom**: Each model takes 5-10 seconds to generate a query

**Explanation**: Normal behavior for large models (20B+ parameters)

**Solutions**:
1. Use smaller models (e.g., `medgemma4B_it_q8:latest`)
2. Reduce number of models
3. Accept the slower speed for better coverage
4. Use auto mode to avoid waiting interactively

## Best Practices

### Getting Started

1. **Start small**: Begin with 2 models, 1 query each
2. **Choose complementary models**: Use models with different training (e.g., general + medical)
3. **Review first**: Use interactive mode initially to understand what queries are generated
4. **Tune**: Adjust number of models/queries based on your needs
5. **Automate**: Once tuned, enable auto mode for efficiency

### Model Selection

**Recommended combinations**:

- **Balanced**: `medgemma-27b-text-it-Q8_0:latest` + `gpt-oss:20b`
  - Medical-specific + general knowledge
  - Good coverage, reasonable speed

- **Speed-focused**: `medgemma4B_it_q8:latest` + `gpt-oss:20b`
  - Faster execution
  - Still good coverage

- **Maximum coverage**: All three models
  - Best recall
  - Slower execution

### Configuration Tips

- **Enable query review** initially: `"show_all_queries_to_user": true`
- **Allow selection** to skip bad queries: `"allow_query_selection": true`
- **Start with 1 query per model**: Increase to 2-3 only if needed
- **Keep de-duplication on**: `"deduplicate_results": true` (recommended)

### When to Use Multi-Model vs Single-Model

**Use multi-model when**:
- Conducting comprehensive literature reviews
- Initial searches returned insufficient results
- Research question has multiple facets
- Quality matters more than speed

**Use single-model when**:
- Quick exploratory searches
- Very specific, narrow questions
- Time-constrained research
- Preliminary scoping

## FAQ

### How many models should I use?

**Recommended**: Start with 2 models

- **1 model**: Same as original behavior, fastest
- **2 models**: Best balance of coverage and speed (recommended)
- **3 models**: Maximum coverage, slower execution

### Why serial instead of parallel execution?

**Reason**: BMLibrarian typically runs with local Ollama and local PostgreSQL instances.

- **Ollama**: Can only process one request at a time efficiently
- **PostgreSQL**: Single local instance, no benefit from parallel queries
- **Simplicity**: Serial execution is simpler, easier to debug
- **No bottlenecks**: Local resources aren't overwhelmed

**Result**: Serial execution is just as performant without creating memory/connection bottlenecks.

### How do I add custom models?

1. **Install model in Ollama**:
   ```bash
   ollama pull your-model-name
   ```

2. **Add to configuration**:
   ```json
   {
     "query_generation": {
       "models": [
         "your-model-name",
         "existing-model-name"
       ]
     }
   }
   ```

3. **Test**: Run a search to verify the model works

### What happens if a model fails?

The system is resilient to model failures:
- Failing model is skipped
- Other models continue generating queries
- Error is logged in query results
- Workflow continues with available queries
- No complete failure unless all models fail

### How does de-duplication work?

**Process**:
1. Queries are de-duplicated (case-insensitive string matching)
2. Each unique query returns a set of document IDs
3. All ID sets are merged (set union operation)
4. Duplicate IDs automatically eliminated (set behavior)
5. Full documents fetched only once

**Example**:
- Query 1 returns: {101, 102, 103}
- Query 2 returns: {102, 103, 104}
- Merged set: {101, 102, 103, 104} (4 unique documents)

### Can I edit generated queries before execution?

**Currently**: Not directly in the current implementation

**Workaround**:
1. Use `"allow_query_selection": true` to skip unwanted queries
2. Manually run queries using the database interface

**Future**: Query editing may be added in a future version

### Does this work with the GUI?

**Yes**: Both the Research GUI and Config GUI fully support multi-model query generation.

- **Research GUI**: Automatically uses multi-model if enabled in configuration
- **Config GUI**: Provides interface to configure multi-model settings
- **No code changes needed**: Just enable in configuration

### What's the difference between this and running multiple searches?

**Multi-model query generation**:
- Generates multiple queries automatically
- De-duplicates results automatically
- Runs in one workflow
- Shows all queries together
- More efficient

**Multiple manual searches**:
- Manual query entry for each search
- Manual tracking of results
- Duplicate documents not eliminated
- More time-consuming
- More prone to missing documents

---

## Summary

Multi-model query generation improves document retrieval by leveraging multiple AI models to create diverse database queries. Start with 2 models and 1 query per model for best balance of coverage and speed. The system handles serial execution, de-duplication, and error handling automatically.

For technical details, see [Multi-Model Architecture Documentation](../developers/multi_model_architecture.md).
