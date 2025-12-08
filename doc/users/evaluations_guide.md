# Unified Evaluation System User Guide

The BMLibrarian Evaluation System provides a centralized, database-backed way to track and manage document evaluations across all agents. This guide explains how to use the evaluation system for scoring documents, tracking progress, and comparing results.

## Overview

The evaluation system replaces in-memory tracking with persistent database storage, providing:

- **Persistent Storage**: Evaluations survive restarts and can be resumed
- **Progress Tracking**: Real-time tracking of evaluation progress
- **Multi-Evaluator Comparison**: Compare results from different models or human evaluators
- **Checkpoint Support**: Save and resume long-running evaluation jobs

## Evaluation Types

The system supports seven evaluation types:

| Type | Description | Primary Score |
|------|-------------|---------------|
| `relevance_score` | Document relevance to research question | 1-5 scale |
| `quality_assessment` | Study quality and methodology | 0-100 composite |
| `prisma_suitability` | PRISMA checklist applicability | 0-1 confidence |
| `prisma_assessment` | Full PRISMA compliance check | 0-100% compliance |
| `pico_extraction` | PICO element extraction | N/A |
| `paper_weight` | Evidential weight calculation | 0-10 scale |
| `inclusion_decision` | Study inclusion/exclusion | N/A |

## Basic Usage

### Running Relevance Scoring

```python
from bmlibrarian.database import DatabaseManager
from bmlibrarian.evaluations import (
    EvaluationStore, EvaluationType, RunType
)

# Initialize
db = DatabaseManager()
store = EvaluationStore(db)

# Register your evaluator (AI model)
evaluator_id = store.evaluator_registry.get_or_create_model_evaluator(
    model_name="gpt-oss:20b",
    temperature=0.1
)

# Create an evaluation run
run = store.create_run(
    run_type=RunType.RELEVANCE_SCORING,
    research_question="What are the cardiovascular benefits of exercise?",
    evaluator_id=evaluator_id,
    documents_total=100  # Total documents to score
)

# Save evaluations as you process
for doc in documents:
    store.save_evaluation(
        run_id=run.run_id,
        document_id=doc['id'],
        evaluation_type=EvaluationType.RELEVANCE_SCORE,
        evaluation_data={
            "score": 4.5,
            "rationale": "Highly relevant study on exercise and heart health",
            "inclusion_decision": "include"
        }
    )

# Complete the run
store.complete_run(run.run_id)
```

### Querying Results

```python
# Get all evaluations above threshold
high_relevance = store.get_evaluations_for_run(
    run_id=run.run_id,
    min_score=3.0  # Default threshold
)

# Get document IDs only
doc_ids = store.get_evaluated_document_ids(
    run_id=run.run_id,
    min_score=3.5
)

# Get run statistics
stats = store.get_run_statistics(run.run_id)
print(f"Average score: {stats['avg_score']:.2f}")
print(f"Above threshold: {stats['above_threshold_count']}")
```

## Checkpoint and Resume

For long-running jobs, save checkpoints to enable resumption:

```python
from bmlibrarian.evaluations import CheckpointType

# Save checkpoint during processing
store.save_checkpoint(
    run_id=run.run_id,
    checkpoint_type=CheckpointType.RELEVANCE_SCORING,
    checkpoint_data={
        "last_document_id": 500,
        "processed_count": 50,
        "document_ids": [1, 2, 3, ...]  # IDs to process
    }
)

# Later: Resume from checkpoint
checkpoint_type, checkpoint_data = store.resume_from_checkpoint(run.run_id)
if checkpoint_type:
    last_doc = checkpoint_data.get("last_document_id")
    # Continue from where you left off
```

## Comparing Evaluators

Compare results from different models or human vs AI:

```python
# Register multiple evaluators
model1_id = store.evaluator_registry.get_or_create_model_evaluator(
    model_name="gpt-oss:20b", temperature=0.1
)
model2_id = store.evaluator_registry.get_or_create_model_evaluator(
    model_name="medgemma4B_it_q8:latest", temperature=0.0
)

# Compare their evaluations
comparison = store.compare_evaluators(
    document_ids=[1, 2, 3, 4, 5],
    research_question="What are the cardiovascular benefits of exercise?",
    evaluation_type=EvaluationType.RELEVANCE_SCORE
)

for result in comparison:
    print(f"Doc {result['document_id']}: {result['evaluator_name']} scored {result['primary_score']}")
```

## Constants and Thresholds

The system uses configurable constants (defined in `schemas.py`):

| Constant | Default | Description |
|----------|---------|-------------|
| `DEFAULT_RELEVANCE_THRESHOLD` | 3.0 | Default score threshold for "above threshold" queries |
| `RELEVANCE_SCORE_MIN` | 1.0 | Minimum relevance score |
| `RELEVANCE_SCORE_MAX` | 5.0 | Maximum relevance score |
| `QUALITY_SCORE_MIN` | 0.0 | Minimum quality score |
| `QUALITY_SCORE_MAX` | 100.0 | Maximum quality score |
| `PAPER_WEIGHT_MIN` | 0.0 | Minimum paper weight |
| `PAPER_WEIGHT_MAX` | 10.0 | Maximum paper weight |
| `CONFIDENCE_MIN` | 0.0 | Minimum confidence score |
| `CONFIDENCE_MAX` | 1.0 | Maximum confidence score |

## Error Handling

All database operations may raise `RuntimeError` on failure:

```python
try:
    store.save_evaluation(...)
except ValueError as e:
    print(f"Validation error: {e}")
except RuntimeError as e:
    print(f"Database error: {e}")
```

## See Also

- [Evaluation System Architecture](../developers/evaluations_system.md) - Technical documentation
- [Study Assessment Guide](study_assessment_guide.md) - Quality assessment details
- [PRISMA 2020 Guide](prisma2020_guide.md) - PRISMA compliance assessment
