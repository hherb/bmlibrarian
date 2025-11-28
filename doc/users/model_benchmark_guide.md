# Model Benchmark Guide

This guide explains how to use the Model Benchmarking tool to evaluate and compare document scoring models.

## Overview

The Model Benchmarking tool allows you to:

1. **Benchmark multiple models** against an authoritative model (default: `gpt-oss:120B`)
2. **Measure scoring accuracy** using Mean Absolute Error (MAE), exact match rate, and within-1 rate
3. **Measure performance** in milliseconds per document
4. **Rank models** by alignment with the authoritative model, with speed as a tiebreaker
5. **Track results** in a PostgreSQL database for historical analysis

## Quick Start

### Basic Benchmark

```bash
# Benchmark two models on a research question
uv run python model_benchmark_cli.py benchmark \
    "What are the cardiovascular benefits of exercise?" \
    --models gpt-oss:20b medgemma4B_it_q8:latest
```

### With Custom Authoritative Model

```bash
# Use a specific authoritative model
uv run python model_benchmark_cli.py benchmark \
    "CRISPR gene editing mechanisms" \
    --models gpt-oss:20b qwen2.5:32b \
    --authoritative gpt-oss:120B
```

### Export Results to JSON

```bash
# Export results for further analysis
uv run python model_benchmark_cli.py benchmark \
    "COVID-19 vaccine efficacy" \
    --models gpt-oss:20b medgemma4B_it_q8:latest \
    --output results.json
```

### Limit Documents

```bash
# Limit to 20 documents for quick testing
uv run python model_benchmark_cli.py benchmark \
    "insulin resistance treatment" \
    --models gpt-oss:20b medgemma4B_it_q8:latest \
    --max-docs 20
```

## Commands

### benchmark

Run a benchmark comparing models against an authoritative model.

**Arguments:**
- `question` (required): Research question for semantic search
- `--models`, `-m` (required): One or more model names to benchmark
- `--authoritative`, `-a`: Authoritative model (default: `gpt-oss:120B`)
- `--threshold`, `-t`: Semantic search threshold (default: 0.5)
- `--max-docs`: Maximum documents to score (default: all found)
- `--temperature`: Model temperature (default: 0.1)
- `--top-p`: Model top-p (default: 0.9)
- `--ollama-host`: Ollama server URL (default: `http://localhost:11434`)
- `--user`: Username for tracking
- `-o`, `--output`: Output JSON file for results

### history

Show benchmark history.

```bash
# View last 20 benchmark runs
uv run python model_benchmark_cli.py history

# View last 50 runs
uv run python model_benchmark_cli.py history --limit 50
```

### show

Show details for a specific benchmark run.

```bash
# View run details
uv run python model_benchmark_cli.py show --run-id 5

# Export summary to JSON
uv run python model_benchmark_cli.py show --run-id 5 --output summary.json
```

### compare

Compare score distributions between models for a run.

```bash
# Compare score distributions
uv run python model_benchmark_cli.py compare --run-id 5
```

## How It Works

### Workflow

1. **Semantic Search**: The tool performs a semantic search using your research question with the configured threshold (default: 0.5).

2. **Authoritative Scoring**: The authoritative model (e.g., `gpt-oss:120B`) scores all found documents. These scores become the "ground truth" for comparison.

3. **Model Scoring**: Each test model scores the same documents. Scoring time is recorded for each document.

4. **Alignment Calculation**: For each model, the tool calculates:
   - **Mean Absolute Error (MAE)**: Average absolute difference from authoritative scores
   - **Root Mean Squared Error (RMSE)**: Square root of average squared differences
   - **Exact Match Rate**: Percentage of scores exactly matching the authoritative score
   - **Within-1 Rate**: Percentage of scores within 1 point of the authoritative score
   - **Score Correlation**: Pearson correlation with authoritative scores

5. **Ranking**: Models are ranked by:
   - **Primary**: Alignment with authoritative model (lower MAE = better)
   - **Tiebreaker**: Speed (faster = better)

### Scoring Scale

All models use the same 0-5 scoring scale:
- **0**: Document is not related to the question at all
- **1**: Document is tangentially related
- **2**: Document is somewhat related with minimal information
- **3**: Document contributes significantly
- **4**: Document addresses the question well
- **5**: Document completely answers the question

## Understanding Results

### Summary Output

```
======================================================================
MODEL BENCHMARK RESULTS
======================================================================

Question: What are the cardiovascular benefits of exercise?
Documents scored: 47
Authoritative model: gpt-oss:120B
Status: completed

----------------------------------------------------------------------
RANKED RESULTS (by alignment with authoritative, then speed)
----------------------------------------------------------------------

Rank #1: gpt-oss:20b
  Mean Absolute Error: 0.425
  Exact Match Rate: 68.1%
  Within-1 Rate: 95.7%
  Avg Time/Doc: 1250.3ms
  Documents Scored: 47

Rank #2: medgemma4B_it_q8:latest
  Mean Absolute Error: 0.553
  Exact Match Rate: 61.7%
  Within-1 Rate: 91.5%
  Avg Time/Doc: 850.2ms
  Documents Scored: 47
```

### Interpreting Metrics

| Metric | Good Value | Interpretation |
|--------|------------|----------------|
| MAE | < 0.5 | Model closely matches authoritative |
| Exact Match | > 60% | Model often agrees exactly |
| Within-1 | > 90% | Model rarely disagrees by more than 1 point |
| Avg Time | Lower is better | Faster scoring |

### JSON Output Format

```json
{
  "run_id": 5,
  "question_text": "What are the cardiovascular benefits of exercise?",
  "semantic_threshold": 0.5,
  "documents_found": 47,
  "status": "completed",
  "started_at": "2025-11-28T10:30:00",
  "completed_at": "2025-11-28T10:45:23",
  "authoritative_result": {
    "evaluator": {
      "model_name": "gpt-oss:120B",
      "temperature": 0.1,
      "top_p": 0.9,
      "is_authoritative": true
    },
    "documents_scored": 47,
    "avg_scoring_time_ms": 3500.5
  },
  "model_results": [
    {
      "evaluator": {
        "model_name": "gpt-oss:20b",
        "temperature": 0.1,
        "top_p": 0.9
      },
      "documents_scored": 47,
      "avg_scoring_time_ms": 1250.3,
      "alignment_metrics": {
        "mean_absolute_error": 0.425,
        "exact_match_rate": 68.1,
        "within_one_rate": 95.7
      },
      "final_rank": 1
    }
  ]
}
```

## Database Schema

Benchmark results are stored in the `benchmarking` schema:

- **research_questions**: Questions used for benchmarking
- **evaluators**: Models and their parameters
- **scoring**: Individual document scores with timing
- **benchmark_runs**: Benchmark sessions
- **benchmark_results**: Aggregated results per model per run

### Useful Queries

```sql
-- View model performance across all runs
SELECT * FROM benchmarking.v_model_performance;

-- View latest run results
SELECT * FROM benchmarking.v_latest_run_results;

-- Compare scores between models
SELECT * FROM benchmarking.v_scoring_comparison
WHERE question_id = 1;
```

## Best Practices

### Choosing Models to Benchmark

- Test models you're considering for production use
- Include a range of model sizes for comparison
- Use consistent parameters (temperature, top_p) across models

### Choosing Questions

- Use questions representative of your actual use case
- Avoid overly broad or vague questions
- Test multiple questions to get a comprehensive view

### Semantic Threshold

- Default threshold (0.5) provides good balance
- Lower threshold (0.3-0.4) finds more documents but with less relevance
- Higher threshold (0.6-0.7) finds fewer but more relevant documents

### Performance Considerations

- Larger authoritative models take longer but provide better ground truth
- Consider running benchmarks during off-peak hours
- Use `--max-docs` for quick tests before full benchmarks

## Troubleshooting

### No Documents Found

If semantic search returns no documents:
1. Check that embeddings exist for your database
2. Lower the threshold (e.g., `--threshold 0.3`)
3. Verify the question is related to your document corpus

### Model Connection Errors

If models fail to connect:
1. Verify Ollama is running: `curl http://localhost:11434/api/tags`
2. Check the model is available: `ollama list`
3. Pull missing models: `ollama pull model_name`

### Slow Benchmarks

For faster benchmarks:
1. Use `--max-docs` to limit documents
2. Use smaller authoritative model for testing
3. Run multiple benchmarks in parallel (different questions)
