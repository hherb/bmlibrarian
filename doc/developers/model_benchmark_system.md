# Model Benchmark System - Developer Documentation

This document describes the architecture and implementation of the Model Benchmarking system for document scoring models.

## Overview

The Model Benchmarking system evaluates document scoring models by comparing their scores against an authoritative model. It measures both accuracy (alignment with authoritative scores) and performance (scoring time).

## Architecture

```
src/bmlibrarian/benchmarking/
├── __init__.py           # Module exports
├── data_types.py         # Type-safe dataclasses
├── database.py           # Database operations
└── runner.py             # Benchmark orchestration

migrations/
└── 024_create_benchmarking_schema.sql  # Database schema

model_benchmark_cli.py    # CLI entry point
```

## Components

### Data Types (`data_types.py`)

Type-safe dataclasses for all benchmark data:

```python
from bmlibrarian.benchmarking import (
    EvaluatorConfig,      # Model configuration
    DocumentScore,        # Single document score
    AlignmentMetrics,     # MAE, RMSE, correlation, match rates
    ModelBenchmarkResult, # Complete result for one model
    BenchmarkRun,         # Complete benchmark session
    BenchmarkSummary,     # Summary statistics
    BenchmarkStatus,      # Enum: running, completed, failed, cancelled
)
```

### Constants

```python
from bmlibrarian.benchmarking import (
    SEMANTIC_THRESHOLD,     # 0.5 - default threshold for semantic search
    BEST_REASONING_MODEL,   # "gpt-oss:120B" - default authoritative model
    DEFAULT_TEMPERATURE,    # 0.1 - consistent scoring
    DEFAULT_TOP_P,          # 0.9 - nucleus sampling
)
```

### Database (`database.py`)

The `BenchmarkDatabase` class handles all database operations:

```python
from bmlibrarian.benchmarking import BenchmarkDatabase

db = BenchmarkDatabase(conn)

# Research questions
question_id = db.get_or_create_question(
    question_text="What are the benefits of exercise?",
    semantic_threshold=0.5,
    created_by="username"
)

# Evaluators
evaluator_id = db.get_or_create_evaluator(EvaluatorConfig(
    model_name="gpt-oss:20b",
    temperature=0.1,
    top_p=0.9
))

# Scoring
db.record_score(
    question_id=question_id,
    evaluator_id=evaluator_id,
    document_id=123,
    score=4,
    reasoning="Document addresses question well",
    scoring_time_ms=1250.5
)

# Metrics calculation
metrics = db.calculate_and_store_alignment_metrics(
    run_id=run_id,
    evaluator_id=evaluator_id,
    authoritative_evaluator_id=auth_evaluator_id
)
```

### Runner (`runner.py`)

The `BenchmarkRunner` class orchestrates benchmark execution:

```python
from bmlibrarian.benchmarking import BenchmarkRunner

runner = BenchmarkRunner(
    conn=conn,
    ollama_host="http://localhost:11434",
    temperature=0.1,
    top_p=0.9,
    authoritative_model="gpt-oss:120B",
    semantic_threshold=0.5,
    progress_callback=lambda status, current, total: print(f"{status}: {current}/{total}")
)

# Run benchmark
result = runner.run_benchmark(
    question_text="What are the cardiovascular benefits of exercise?",
    models=["gpt-oss:20b", "medgemma4B_it_q8:latest"],
    max_documents=50,
    created_by="developer"
)

# Get summary
summary = runner.get_summary(result.run_id)

# Export to JSON
runner.export_results_json(result, Path("results.json"))

# Print formatted summary
print(runner.print_summary(result))
```

## Database Schema

### Tables

#### `benchmarking.research_questions`
Stores research questions used for benchmarking.

| Column | Type | Description |
|--------|------|-------------|
| question_id | BIGSERIAL | Primary key |
| question_text | TEXT | Research question (unique) |
| semantic_threshold | REAL | Threshold used for search |
| documents_found | INTEGER | Documents found by search |
| created_at | TIMESTAMPTZ | Creation timestamp |
| created_by | TEXT | Username of creator |
| description | TEXT | Optional description |

#### `benchmarking.evaluators`
Stores model configurations.

| Column | Type | Description |
|--------|------|-------------|
| evaluator_id | BIGSERIAL | Primary key |
| model_name | TEXT | Ollama model name |
| temperature | REAL | Temperature parameter |
| top_p | REAL | Top-p parameter |
| is_authoritative | BOOLEAN | Whether this is ground truth |
| ollama_host | TEXT | Ollama server URL |
| created_at | TIMESTAMPTZ | Creation timestamp |

#### `benchmarking.scoring`
Stores individual document scores.

| Column | Type | Description |
|--------|------|-------------|
| scoring_id | BIGSERIAL | Primary key |
| question_id | BIGINT | FK to research_questions |
| evaluator_id | BIGINT | FK to evaluators |
| document_id | INTEGER | FK to public.document |
| score | INTEGER | Relevance score (0-5) |
| reasoning | TEXT | Score reasoning |
| scoring_time_ms | REAL | Time to score in ms |
| scored_at | TIMESTAMPTZ | Scoring timestamp |

#### `benchmarking.benchmark_runs`
Tracks benchmark sessions.

| Column | Type | Description |
|--------|------|-------------|
| run_id | BIGSERIAL | Primary key |
| question_id | BIGINT | FK to research_questions |
| started_at | TIMESTAMPTZ | Start timestamp |
| completed_at | TIMESTAMPTZ | Completion timestamp |
| status | TEXT | running/completed/failed/cancelled |
| error_message | TEXT | Error details if failed |
| models_evaluated | TEXT[] | Array of model names |
| authoritative_model | TEXT | Authoritative model name |
| total_documents | INTEGER | Documents scored |
| config_snapshot | JSONB | Configuration snapshot |

#### `benchmarking.benchmark_results`
Aggregated results per model per run.

| Column | Type | Description |
|--------|------|-------------|
| result_id | BIGSERIAL | Primary key |
| run_id | BIGINT | FK to benchmark_runs |
| evaluator_id | BIGINT | FK to evaluators |
| documents_scored | INTEGER | Count of documents |
| total_scoring_time_ms | REAL | Total time |
| avg_scoring_time_ms | REAL | Generated: total/count |
| mean_absolute_error | REAL | MAE vs authoritative |
| root_mean_squared_error | REAL | RMSE vs authoritative |
| score_correlation | REAL | Pearson correlation |
| exact_match_rate | REAL | % exact matches |
| within_one_rate | REAL | % within 1 point |
| alignment_rank | INTEGER | Rank by alignment |
| performance_rank | INTEGER | Rank by speed |
| final_rank | INTEGER | Combined rank |

### Views

- `v_scoring_comparison`: Compare scores with authoritative
- `v_model_performance`: Aggregate performance across runs
- `v_latest_run_results`: Results from most recent run

### Functions

- `get_or_create_question()`: Upsert research question
- `get_or_create_evaluator()`: Upsert evaluator
- `calculate_alignment_metrics()`: Calculate MAE, RMSE, correlation
- `update_rankings()`: Update all rankings for a run

## Alignment Metrics

### Mean Absolute Error (MAE)

```
MAE = (1/n) * Σ|model_score - authoritative_score|
```

Lower is better. An MAE of 0.5 means on average the model differs by half a point from the authoritative model.

### Root Mean Squared Error (RMSE)

```
RMSE = √[(1/n) * Σ(model_score - authoritative_score)²]
```

Penalizes larger errors more than MAE. Useful when large deviations are particularly problematic.

### Score Correlation

Pearson correlation coefficient between model scores and authoritative scores. Values range from -1 to 1, with 1 indicating perfect positive correlation.

### Exact Match Rate

```
Exact Match % = (count of exact matches / total documents) * 100
```

Percentage of documents where the model gave the exact same score as the authoritative model.

### Within-1 Rate

```
Within-1 % = (count of |diff| <= 1 / total documents) * 100
```

Percentage of documents where the model's score was within 1 point of the authoritative score.

## Ranking Algorithm

Models are ranked using a two-level sort:

1. **Primary**: Alignment with authoritative model (lower MAE = better rank)
2. **Secondary**: Speed (lower avg_scoring_time_ms = better rank)

This ensures models are primarily evaluated on accuracy, with speed as a tiebreaker for equally accurate models.

```sql
RANK() OVER (
    ORDER BY mean_absolute_error ASC NULLS LAST,
             avg_scoring_time_ms ASC NULLS LAST
) as final_rank
```

## Usage Example

```python
import psycopg
from bmlibrarian.benchmarking import BenchmarkRunner

# Connect to database
conn = psycopg.connect(
    host="localhost",
    port="5432",
    user="hherb",
    password="password",
    dbname="knowledgebase"
)

# Create runner
runner = BenchmarkRunner(
    conn=conn,
    authoritative_model="gpt-oss:120B",
    semantic_threshold=0.5
)

# Run benchmark
result = runner.run_benchmark(
    question_text="What are the mechanisms of insulin resistance?",
    models=[
        "gpt-oss:20b",
        "medgemma4B_it_q8:latest",
        "qwen2.5:32b"
    ],
    max_documents=50
)

# Access results
for model_result in result.get_ranked_results():
    print(f"Rank {model_result.final_rank}: {model_result.evaluator.model_name}")
    if model_result.alignment_metrics:
        print(f"  MAE: {model_result.alignment_metrics.mean_absolute_error:.3f}")
        print(f"  Exact Match: {model_result.alignment_metrics.exact_match_rate:.1f}%")
    print(f"  Avg Time: {model_result.avg_scoring_time_ms:.1f}ms")

# Export results
runner.export_results_json(result, Path("benchmark_results.json"))
```

## Integration with DocumentScoringAgent

The benchmark system uses `DocumentScoringAgent` from `bmlibrarian.agents` for scoring:

```python
from bmlibrarian.agents.scoring_agent import DocumentScoringAgent

agent = DocumentScoringAgent(
    model="gpt-oss:20b",
    host="http://localhost:11434",
    temperature=0.1,
    top_p=0.9
)

result = agent.evaluate_document(
    user_question="What are the benefits of exercise?",
    document={"title": "...", "abstract": "..."}
)
# Returns: {"score": 4, "reasoning": "..."}
```

The benchmark runner wraps this with timing:

```python
import time

start = time.perf_counter()
result = agent.evaluate_document(question, document)
elapsed_ms = (time.perf_counter() - start) * 1000
```

## Error Handling

### Document Scoring Errors

If scoring fails for a document, the error is recorded and scoring continues:

```python
except Exception as e:
    logger.error(f"Error scoring document {doc['document_id']}: {e}")
    score = DocumentScore(
        document_id=doc["document_id"],
        score=0,
        reasoning=f"Scoring failed: {e}",
        scoring_time_ms=elapsed_ms
    )
```

### Benchmark Run Errors

If the entire benchmark fails, the run is marked as failed:

```python
except Exception as e:
    benchmark_run.status = BenchmarkStatus.FAILED
    benchmark_run.error_message = str(e)
    db.update_benchmark_run_status(run_id, BenchmarkStatus.FAILED, str(e))
    raise
```

## Testing

### Unit Tests

```python
import pytest
from bmlibrarian.benchmarking import (
    EvaluatorConfig,
    DocumentScore,
    AlignmentMetrics,
)

def test_evaluator_config_to_dict():
    config = EvaluatorConfig(
        model_name="test-model",
        temperature=0.1,
        top_p=0.9
    )
    d = config.to_dict()
    assert d["model_name"] == "test-model"
    assert d["temperature"] == 0.1

def test_alignment_metrics():
    metrics = AlignmentMetrics(
        mean_absolute_error=0.5,
        root_mean_squared_error=0.7,
        score_correlation=0.9,
        exact_match_rate=60.0,
        within_one_rate=95.0
    )
    d = metrics.to_dict()
    assert d["mean_absolute_error"] == 0.5
```

### Integration Tests

```python
def test_benchmark_run(db_connection):
    runner = BenchmarkRunner(conn=db_connection)
    result = runner.run_benchmark(
        question_text="Test question",
        models=["test-model"],
        max_documents=5
    )
    assert result.status == BenchmarkStatus.COMPLETED
    assert len(result.model_results) == 1
```

## Future Enhancements

1. **Parallel Model Scoring**: Score with multiple models concurrently
2. **Statistical Significance Testing**: Add t-tests for comparing models
3. **Cross-Validation**: Run benchmarks on multiple questions automatically
4. **Visualization**: Add plotting capabilities for score distributions
5. **Model Recommendations**: Suggest optimal models based on constraints
