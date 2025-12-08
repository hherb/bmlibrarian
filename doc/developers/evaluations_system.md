# Unified Evaluation System Architecture

This document describes the technical architecture of the BMLibrarian Evaluation System, which provides database-backed evaluation tracking to replace in-memory state management in agents.

## Purpose

The evaluation system addresses several problems with the previous architecture:

1. **Memory Issues**: Large `_scored_papers` lists consuming excessive memory
2. **Lost State**: Evaluations lost on crashes or restarts
3. **No Comparison**: Difficult to compare evaluations from different models
4. **Inconsistent Storage**: Different agents storing evaluations differently
5. **Resumability**: No standard way to resume interrupted evaluations

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      Agent Layer                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ ScoringAgent │  │ QualityAgent │  │ PRISMAAgent  │ ...  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
│         │                 │                 │               │
└─────────┼─────────────────┼─────────────────┼───────────────┘
          │                 │                 │
          └─────────────────┼─────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   EvaluationStore                           │
│  ┌──────────────────┐  ┌─────────────────┐                 │
│  │ EvaluatorRegistry│  │ Schema Validation│                 │
│  └──────────────────┘  └─────────────────┘                 │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 PostgreSQL (evaluations schema)             │
│  ┌────────────────┐  ┌─────────────────────┐               │
│  │evaluation_runs │  │document_evaluations │               │
│  └────────────────┘  └─────────────────────┘               │
│  ┌────────────────┐  ┌─────────────────────┐               │
│  │run_checkpoints │  │evaluation_comparisons│              │
│  └────────────────┘  └─────────────────────┘               │
└─────────────────────────────────────────────────────────────┘
```

## Components

### schemas.py

Defines all types, constants, and validation:

```python
# Constants (no magic numbers)
PARAMETER_DECIMAL_PRECISION: int = 4
DEFAULT_RELEVANCE_THRESHOLD: float = 3.0
RELEVANCE_SCORE_MIN: float = 1.0
RELEVANCE_SCORE_MAX: float = 5.0
# ... etc

# Enums
class EvaluationType(Enum):
    RELEVANCE_SCORE = "relevance_score"
    QUALITY_ASSESSMENT = "quality_assessment"
    # ...

# TypedDict schemas for validation
class RelevanceScoreData(TypedDict, total=False):
    score: float  # 1-5 scale
    rationale: str
    inclusion_decision: str
    # ...

# Validation functions
def validate_evaluation_data(evaluation_type: str, data: Dict) -> tuple[bool, str]:
    """Validate data against schema."""
```

### evaluator_registry.py

Manages evaluator records with caching:

```python
class EvaluatorRegistry:
    """Get-or-create pattern for evaluator management."""

    def get_or_create_model_evaluator(
        self,
        model_name: str,
        temperature: float = 0.0,
        top_p: float = 1.0,
        prompt: Optional[str] = None
    ) -> int:
        """Get existing or create new model evaluator."""

    def get_or_create_human_evaluator(
        self,
        user_id: int,
        name: Optional[str] = None
    ) -> int:
        """Get existing or create new human evaluator."""
```

Key features:
- **Caching**: Avoids repeated database lookups
- **Parameter Normalization**: Uses `PARAMETER_DECIMAL_PRECISION` for consistent rounding
- **Error Handling**: All methods raise `RuntimeError` on database failures

### store.py

Main interface for evaluation storage:

```python
class EvaluationStore:
    """Database-backed evaluation storage."""

    # Run management
    def create_run(...) -> EvaluationRun
    def get_run(run_id) -> Optional[EvaluationRun]
    def get_or_resume_run(...) -> Tuple[EvaluationRun, bool]
    def complete_run(run_id, status) -> None

    # Evaluations
    def save_evaluation(...) -> int
    def save_evaluations_batch(...) -> List[int]
    def get_evaluations_for_run(...) -> List[DocumentEvaluation]
    def get_unevaluated_documents(...) -> List[int]

    # Checkpoints
    def save_checkpoint(...) -> int
    def get_latest_checkpoint(...) -> Optional[Checkpoint]
    def resume_from_checkpoint(...) -> Tuple[str, Dict]

    # Analysis
    def compare_evaluators(...) -> List[Dict]
    def get_run_statistics(...) -> Dict
```

## Database Schema

### evaluations.evaluation_runs

```sql
CREATE TABLE evaluations.evaluation_runs (
    run_id SERIAL PRIMARY KEY,
    run_type VARCHAR(50) NOT NULL,
    research_question_text TEXT,
    research_question_id INTEGER REFERENCES audit.research_questions(id),
    evaluator_id INTEGER REFERENCES public.evaluators(id),
    session_id INTEGER,
    status VARCHAR(20) DEFAULT 'in_progress',
    config_snapshot JSONB,
    documents_total INTEGER DEFAULT 0,
    documents_processed INTEGER DEFAULT 0,
    started_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    error_message TEXT
);
```

### evaluations.document_evaluations

```sql
CREATE TABLE evaluations.document_evaluations (
    evaluation_id SERIAL PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES evaluations.evaluation_runs(run_id),
    document_id INTEGER NOT NULL,
    evaluator_id INTEGER REFERENCES public.evaluators(id),
    evaluation_type VARCHAR(50) NOT NULL,
    primary_score DECIMAL(10,4),
    confidence DECIMAL(5,4),
    evaluation_data JSONB NOT NULL,
    reasoning TEXT,
    processing_time_ms INTEGER,
    evaluated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(run_id, document_id, evaluation_type)  -- Upsert support
);
```

### Helper Functions

The schema includes PostgreSQL functions for common operations:

```sql
-- Save evaluation with upsert
evaluations.save_evaluation(
    p_run_id, p_document_id, p_evaluation_type,
    p_primary_score, p_evaluation_data, p_evaluator_id,
    p_confidence, p_reasoning, p_processing_time_ms
) RETURNS INTEGER

-- Get documents not yet evaluated
evaluations.get_unevaluated_documents(
    p_run_id, p_document_ids, p_evaluation_type
) RETURNS SETOF INTEGER

-- Save checkpoint
evaluations.save_checkpoint(
    p_run_id, p_checkpoint_type, p_checkpoint_data,
    p_user_decision, p_user_feedback
) RETURNS INTEGER

-- Compare evaluators
evaluations.compare_evaluators(
    p_document_ids, p_research_question, p_evaluation_type
) RETURNS TABLE(...)
```

## Migration to EvaluationStore

To migrate an agent from in-memory tracking:

### Before

```python
class ScoringAgent:
    def __init__(self):
        self._scored_papers = []  # In-memory tracking

    def score_document(self, doc, question):
        score = self._evaluate(doc, question)
        self._scored_papers.append({
            "document_id": doc["id"],
            "score": score,
            "rationale": "..."
        })
```

### After

```python
class ScoringAgent:
    def __init__(self, db_manager):
        self.store = EvaluationStore(db_manager)
        self.run: Optional[EvaluationRun] = None

    def start_run(self, question, evaluator_id):
        self.run = self.store.create_run(
            run_type=RunType.RELEVANCE_SCORING,
            research_question=question,
            evaluator_id=evaluator_id
        )

    def score_document(self, doc, question):
        score = self._evaluate(doc, question)
        self.store.save_evaluation(
            run_id=self.run.run_id,
            document_id=doc["id"],
            evaluation_type=EvaluationType.RELEVANCE_SCORE,
            evaluation_data={
                "score": score,
                "rationale": "..."
            }
        )

    @property
    def scored_papers(self):
        """Backward-compatible access to scored papers."""
        return self.store.get_evaluations_for_run(self.run.run_id)
```

## Error Handling

All database operations use consistent error handling:

```python
try:
    with self.db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            result = cur.fetchone()
        conn.commit()
except Exception as e:
    logger.error(f"Failed to {operation}: {e}")
    raise RuntimeError(f"Database error {operation}: {e}") from e
```

## Type Safety

The module uses:
- `TYPE_CHECKING` for forward references without circular imports
- Proper type hints for all parameters
- `Optional` for nullable values
- `Dict[str, Any]` for JSONB data (with TypedDict schemas for validation)

## Testing

Unit tests are in `tests/test_evaluations.py`:

```bash
uv run python -m pytest tests/test_evaluations.py -v
```

Tests cover:
- All enums and their values
- Schema validation
- Score extraction
- Registry caching
- Store operations (mocked database)
- Workflow scenarios

## Golden Rules Compliance

This module follows all golden rules:

1. **No magic numbers**: All constants in `schemas.py`
2. **No hardcoded paths**: N/A
3. **Ollama via library**: N/A (database module)
4. **Database via DatabaseManager**: All operations use `self.db`
5. **Type hints**: All parameters typed
6. **Docstrings**: All public methods documented
7. **Error handling**: All DB operations wrapped in try/except
8. **No inline stylesheets**: N/A
9. **No hardcoded pixels**: N/A
10. **Pure functions**: Schema validation functions are pure
11. **Documentation**: This file and user guide
12. **Idempotent migrations**: All CREATE IF NOT EXISTS
13. **No migration tracking code**: Handled by MigrationManager

## See Also

- [User Guide](../users/evaluations_guide.md) - End-user documentation
- Migration file: `migrations/026_create_unified_evaluations_schema.sql`
- Source: `src/bmlibrarian/evaluations/`
