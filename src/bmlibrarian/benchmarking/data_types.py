"""
Data Types for Model Benchmarking System

Type-safe dataclasses for document scoring model benchmarking,
including scoring results, alignment metrics, and benchmark summaries.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Final
from enum import Enum


# Constants for benchmarking - defined at module level for use in defaults
SEMANTIC_THRESHOLD: Final[float] = 0.5
BEST_REASONING_MODEL: Final[str] = "gpt-oss:120B"
DEFAULT_TEMPERATURE: Final[float] = 0.1
DEFAULT_TOP_P: Final[float] = 0.9
DEFAULT_OLLAMA_HOST: Final[str] = "http://localhost:11434"
DEFAULT_DOCUMENT_LIMIT: Final[int] = 100
MIN_SCORE: Final[int] = 0
MAX_SCORE: Final[int] = 5


class BenchmarkStatus(Enum):
    """Status of a benchmark run."""
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class EvaluatorConfig:
    """Configuration for a model evaluator."""
    model_name: str
    temperature: float = DEFAULT_TEMPERATURE
    top_p: float = DEFAULT_TOP_P
    is_authoritative: bool = False
    ollama_host: str = DEFAULT_OLLAMA_HOST
    evaluator_id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "model_name": self.model_name,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "is_authoritative": self.is_authoritative,
            "ollama_host": self.ollama_host,
            "evaluator_id": self.evaluator_id
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvaluatorConfig":
        """
        Create from dictionary.

        Args:
            data: Dictionary with evaluator configuration

        Returns:
            EvaluatorConfig instance

        Raises:
            KeyError: If required 'model_name' key is missing
        """
        if "model_name" not in data:
            raise KeyError("Required key 'model_name' missing from data")
        return cls(
            model_name=data["model_name"],
            temperature=data.get("temperature", DEFAULT_TEMPERATURE),
            top_p=data.get("top_p", DEFAULT_TOP_P),
            is_authoritative=data.get("is_authoritative", False),
            ollama_host=data.get("ollama_host", DEFAULT_OLLAMA_HOST),
            evaluator_id=data.get("evaluator_id")
        )


@dataclass
class DocumentScore:
    """Score for a single document from a single evaluator."""
    document_id: int
    score: int
    reasoning: str
    scoring_time_ms: float
    scored_at: Optional[datetime] = None
    document_title: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "document_id": self.document_id,
            "score": self.score,
            "reasoning": self.reasoning,
            "scoring_time_ms": self.scoring_time_ms,
            "scored_at": self.scored_at.isoformat() if self.scored_at else None,
            "document_title": self.document_title
        }


@dataclass
class AlignmentMetrics:
    """Alignment metrics comparing a model to the authoritative model."""
    mean_absolute_error: float
    root_mean_squared_error: float
    score_correlation: Optional[float]
    exact_match_rate: float  # Percentage of exact matches
    within_one_rate: float  # Percentage within 1 point

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "mean_absolute_error": self.mean_absolute_error,
            "root_mean_squared_error": self.root_mean_squared_error,
            "score_correlation": self.score_correlation,
            "exact_match_rate": self.exact_match_rate,
            "within_one_rate": self.within_one_rate
        }


@dataclass
class ModelBenchmarkResult:
    """Benchmark result for a single model."""
    evaluator: EvaluatorConfig
    documents_scored: int
    total_scoring_time_ms: float
    avg_scoring_time_ms: float
    scores: List[DocumentScore] = field(default_factory=list)
    alignment_metrics: Optional[AlignmentMetrics] = None
    alignment_rank: Optional[int] = None
    performance_rank: Optional[int] = None
    final_rank: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "evaluator": self.evaluator.to_dict(),
            "documents_scored": self.documents_scored,
            "total_scoring_time_ms": self.total_scoring_time_ms,
            "avg_scoring_time_ms": self.avg_scoring_time_ms,
            "scores": [s.to_dict() for s in self.scores],
            "alignment_metrics": self.alignment_metrics.to_dict() if self.alignment_metrics else None,
            "alignment_rank": self.alignment_rank,
            "performance_rank": self.performance_rank,
            "final_rank": self.final_rank
        }


@dataclass
class BenchmarkRun:
    """Complete benchmark run with all model results."""
    run_id: Optional[int]
    question_id: int
    question_text: str
    semantic_threshold: float
    documents_found: int
    status: BenchmarkStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    authoritative_result: Optional[ModelBenchmarkResult] = None
    model_results: List[ModelBenchmarkResult] = field(default_factory=list)
    config_snapshot: Optional[Dict[str, Any]] = None

    def get_ranked_results(self) -> List[ModelBenchmarkResult]:
        """
        Get model results sorted by final rank.

        Returns:
            List of ModelBenchmarkResult sorted by final_rank (ascending).
        """
        return sorted(
            self.model_results,
            key=lambda r: (r.final_rank or float('inf'), r.avg_scoring_time_ms)
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "run_id": self.run_id,
            "question_id": self.question_id,
            "question_text": self.question_text,
            "semantic_threshold": self.semantic_threshold,
            "documents_found": self.documents_found,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message,
            "authoritative_result": self.authoritative_result.to_dict() if self.authoritative_result else None,
            "model_results": [r.to_dict() for r in self.model_results],
            "config_snapshot": self.config_snapshot
        }


@dataclass
class BenchmarkSummary:
    """Summary statistics for a benchmark run."""
    run_id: int
    question_text: str
    total_documents: int
    models_evaluated: int
    authoritative_model: str
    best_model: str
    best_model_mae: float
    best_model_exact_match_rate: float
    fastest_model: str
    fastest_model_avg_time_ms: float
    rankings: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "run_id": self.run_id,
            "question_text": self.question_text,
            "total_documents": self.total_documents,
            "models_evaluated": self.models_evaluated,
            "authoritative_model": self.authoritative_model,
            "best_model": self.best_model,
            "best_model_mae": self.best_model_mae,
            "best_model_exact_match_rate": self.best_model_exact_match_rate,
            "fastest_model": self.fastest_model,
            "fastest_model_avg_time_ms": self.fastest_model_avg_time_ms,
            "rankings": self.rankings
        }
