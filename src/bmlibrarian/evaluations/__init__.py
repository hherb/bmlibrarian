"""
Unified Evaluation Tracking System for BMLibrarian.

This module provides database-backed evaluation storage that replaces
in-memory state tracking in agents. It supports:

- Multiple evaluation types (scoring, quality assessment, PRISMA, PICO, etc.)
- Run-based organization for grouping evaluations
- Checkpoint support for resumability
- Multi-evaluator comparison
- Progress tracking with automatic updates

Quick Start:
    from bmlibrarian.database import DatabaseManager
    from bmlibrarian.evaluations import (
        EvaluationStore, EvaluatorRegistry,
        EvaluationType, RunType, CheckpointType
    )

    # Initialize
    db = DatabaseManager()
    store = EvaluationStore(db)

    # Get or create evaluator
    registry = store.evaluator_registry
    evaluator_id = registry.get_or_create_model_evaluator(
        model_name="gpt-oss:20b",
        temperature=0.1
    )

    # Create a run
    run = store.create_run(
        run_type=RunType.RELEVANCE_SCORING,
        research_question="What are the cardiovascular benefits of exercise?",
        evaluator_id=evaluator_id,
        config={"threshold": 3.0}
    )

    # Save evaluations
    store.save_evaluation(
        run_id=run.run_id,
        document_id=123,
        evaluation_type=EvaluationType.RELEVANCE_SCORE,
        evaluation_data={"score": 4.5, "rationale": "Highly relevant..."}
    )

    # Get evaluated documents
    evaluations = store.get_evaluations_for_run(
        run_id=run.run_id,
        min_score=3.0
    )

    # Save checkpoint for resumability
    store.save_checkpoint(
        run_id=run.run_id,
        checkpoint_type=CheckpointType.RELEVANCE_SCORING,
        checkpoint_data={"document_ids": [1, 2, 3], "processed_count": 3}
    )

    # Complete the run
    store.complete_run(run.run_id)

Author: BMLibrarian
Date: 2025-12-07
"""

# Schema definitions and enums
from .schemas import (
    # Enums
    EvaluationType,
    RunType,
    RunStatus,
    CheckpointType,
    UserDecision,

    # TypedDict schemas
    RelevanceScoreData,
    QualityAssessmentData,
    PRISMASuitabilityData,
    PRISMAAssessmentData,
    PICOExtractionData,
    PaperWeightData,
    InclusionDecisionData,

    # Schema registry and validation
    EVALUATION_SCHEMAS,
    validate_evaluation_data,
    get_primary_score_field,
    extract_primary_score,
)

# Evaluator registry
from .evaluator_registry import (
    EvaluatorInfo,
    EvaluatorRegistry,
)

# Evaluation store
from .store import (
    EvaluationRun,
    DocumentEvaluation,
    Checkpoint,
    EvaluationStore,
)

__all__ = [
    # Enums
    "EvaluationType",
    "RunType",
    "RunStatus",
    "CheckpointType",
    "UserDecision",

    # TypedDict schemas
    "RelevanceScoreData",
    "QualityAssessmentData",
    "PRISMASuitabilityData",
    "PRISMAAssessmentData",
    "PICOExtractionData",
    "PaperWeightData",
    "InclusionDecisionData",

    # Schema utilities
    "EVALUATION_SCHEMAS",
    "validate_evaluation_data",
    "get_primary_score_field",
    "extract_primary_score",

    # Evaluator registry
    "EvaluatorInfo",
    "EvaluatorRegistry",

    # Evaluation store
    "EvaluationRun",
    "DocumentEvaluation",
    "Checkpoint",
    "EvaluationStore",
]
