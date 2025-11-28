"""
Unit Tests for Model Benchmarking Module

Tests data types, validation, and core functionality of the
benchmarking system for document scoring models.
"""

import pytest
from datetime import datetime
from typing import Dict, Any

from src.bmlibrarian.benchmarking.data_types import (
    BenchmarkStatus,
    EvaluatorConfig,
    DocumentScore,
    AlignmentMetrics,
    ModelBenchmarkResult,
    BenchmarkRun,
    BenchmarkSummary,
    SEMANTIC_THRESHOLD,
    BEST_REASONING_MODEL,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    DEFAULT_OLLAMA_HOST,
    DEFAULT_DOCUMENT_LIMIT,
    MIN_SCORE,
    MAX_SCORE,
)


class TestConstants:
    """Test that constants are properly defined."""

    def test_semantic_threshold_value(self) -> None:
        """Test semantic threshold is reasonable."""
        assert SEMANTIC_THRESHOLD == 0.5
        assert 0.0 <= SEMANTIC_THRESHOLD <= 1.0

    def test_best_reasoning_model_value(self) -> None:
        """Test authoritative model is defined."""
        assert BEST_REASONING_MODEL == "gpt-oss:120B"
        assert len(BEST_REASONING_MODEL) > 0

    def test_default_temperature_value(self) -> None:
        """Test default temperature is reasonable."""
        assert DEFAULT_TEMPERATURE == 0.1
        assert 0.0 <= DEFAULT_TEMPERATURE <= 2.0

    def test_default_top_p_value(self) -> None:
        """Test default top_p is reasonable."""
        assert DEFAULT_TOP_P == 0.9
        assert 0.0 <= DEFAULT_TOP_P <= 1.0

    def test_default_ollama_host_value(self) -> None:
        """Test default Ollama host is defined."""
        assert DEFAULT_OLLAMA_HOST == "http://localhost:11434"
        assert DEFAULT_OLLAMA_HOST.startswith("http")

    def test_default_document_limit_value(self) -> None:
        """Test default document limit is positive."""
        assert DEFAULT_DOCUMENT_LIMIT == 100
        assert DEFAULT_DOCUMENT_LIMIT > 0

    def test_score_range_values(self) -> None:
        """Test score range is correct."""
        assert MIN_SCORE == 0
        assert MAX_SCORE == 5
        assert MIN_SCORE < MAX_SCORE


class TestBenchmarkStatus:
    """Test BenchmarkStatus enum."""

    def test_all_statuses_exist(self) -> None:
        """Test that all expected statuses exist."""
        assert BenchmarkStatus.RUNNING.value == "running"
        assert BenchmarkStatus.COMPLETED.value == "completed"
        assert BenchmarkStatus.FAILED.value == "failed"
        assert BenchmarkStatus.CANCELLED.value == "cancelled"

    def test_status_count(self) -> None:
        """Test correct number of statuses."""
        assert len(BenchmarkStatus) == 4


class TestEvaluatorConfig:
    """Test EvaluatorConfig dataclass."""

    def test_create_with_defaults(self) -> None:
        """Test creating config with default values."""
        config = EvaluatorConfig(model_name="test-model")
        assert config.model_name == "test-model"
        assert config.temperature == DEFAULT_TEMPERATURE
        assert config.top_p == DEFAULT_TOP_P
        assert config.is_authoritative is False
        assert config.ollama_host == DEFAULT_OLLAMA_HOST
        assert config.evaluator_id is None

    def test_create_with_custom_values(self) -> None:
        """Test creating config with custom values."""
        config = EvaluatorConfig(
            model_name="gpt-oss:20b",
            temperature=0.2,
            top_p=0.8,
            is_authoritative=True,
            ollama_host="http://other:11434",
            evaluator_id=42
        )
        assert config.model_name == "gpt-oss:20b"
        assert config.temperature == 0.2
        assert config.top_p == 0.8
        assert config.is_authoritative is True
        assert config.ollama_host == "http://other:11434"
        assert config.evaluator_id == 42

    def test_to_dict(self) -> None:
        """Test converting config to dictionary."""
        config = EvaluatorConfig(
            model_name="test-model",
            temperature=0.15,
            evaluator_id=10
        )
        d = config.to_dict()
        assert d["model_name"] == "test-model"
        assert d["temperature"] == 0.15
        assert d["top_p"] == DEFAULT_TOP_P
        assert d["is_authoritative"] is False
        assert d["ollama_host"] == DEFAULT_OLLAMA_HOST
        assert d["evaluator_id"] == 10

    def test_from_dict_with_all_fields(self) -> None:
        """Test creating config from dict with all fields."""
        data = {
            "model_name": "gpt-oss:20b",
            "temperature": 0.2,
            "top_p": 0.85,
            "is_authoritative": True,
            "ollama_host": "http://custom:11434",
            "evaluator_id": 5
        }
        config = EvaluatorConfig.from_dict(data)
        assert config.model_name == "gpt-oss:20b"
        assert config.temperature == 0.2
        assert config.top_p == 0.85
        assert config.is_authoritative is True
        assert config.ollama_host == "http://custom:11434"
        assert config.evaluator_id == 5

    def test_from_dict_with_minimal_fields(self) -> None:
        """Test creating config from dict with only required fields."""
        data = {"model_name": "minimal-model"}
        config = EvaluatorConfig.from_dict(data)
        assert config.model_name == "minimal-model"
        assert config.temperature == DEFAULT_TEMPERATURE
        assert config.top_p == DEFAULT_TOP_P
        assert config.is_authoritative is False
        assert config.ollama_host == DEFAULT_OLLAMA_HOST
        assert config.evaluator_id is None

    def test_from_dict_missing_model_name_raises(self) -> None:
        """Test that missing model_name raises KeyError."""
        data: Dict[str, Any] = {"temperature": 0.1}
        with pytest.raises(KeyError) as exc_info:
            EvaluatorConfig.from_dict(data)
        assert "model_name" in str(exc_info.value)

    def test_roundtrip_to_dict_from_dict(self) -> None:
        """Test that to_dict and from_dict are inverses."""
        original = EvaluatorConfig(
            model_name="roundtrip-model",
            temperature=0.3,
            top_p=0.7,
            is_authoritative=True,
            ollama_host="http://test:11434",
            evaluator_id=99
        )
        d = original.to_dict()
        restored = EvaluatorConfig.from_dict(d)
        assert restored.model_name == original.model_name
        assert restored.temperature == original.temperature
        assert restored.top_p == original.top_p
        assert restored.is_authoritative == original.is_authoritative
        assert restored.ollama_host == original.ollama_host
        assert restored.evaluator_id == original.evaluator_id


class TestDocumentScore:
    """Test DocumentScore dataclass."""

    def test_create_document_score(self) -> None:
        """Test creating a document score."""
        now = datetime.now()
        score = DocumentScore(
            document_id=123,
            score=4,
            reasoning="Highly relevant document",
            scoring_time_ms=1500.5,
            scored_at=now,
            document_title="Test Paper"
        )
        assert score.document_id == 123
        assert score.score == 4
        assert score.reasoning == "Highly relevant document"
        assert score.scoring_time_ms == 1500.5
        assert score.scored_at == now
        assert score.document_title == "Test Paper"

    def test_to_dict(self) -> None:
        """Test converting score to dictionary."""
        now = datetime.now()
        score = DocumentScore(
            document_id=456,
            score=3,
            reasoning="Moderately relevant",
            scoring_time_ms=800.0,
            scored_at=now
        )
        d = score.to_dict()
        assert d["document_id"] == 456
        assert d["score"] == 3
        assert d["reasoning"] == "Moderately relevant"
        assert d["scoring_time_ms"] == 800.0
        assert d["scored_at"] == now.isoformat()
        assert d["document_title"] is None

    def test_to_dict_without_scored_at(self) -> None:
        """Test converting score without scored_at timestamp."""
        score = DocumentScore(
            document_id=789,
            score=5,
            reasoning="Perfect match",
            scoring_time_ms=500.0
        )
        d = score.to_dict()
        assert d["scored_at"] is None


class TestAlignmentMetrics:
    """Test AlignmentMetrics dataclass."""

    def test_create_alignment_metrics(self) -> None:
        """Test creating alignment metrics."""
        metrics = AlignmentMetrics(
            mean_absolute_error=0.5,
            root_mean_squared_error=0.7,
            score_correlation=0.92,
            exact_match_rate=65.0,
            within_one_rate=95.0
        )
        assert metrics.mean_absolute_error == 0.5
        assert metrics.root_mean_squared_error == 0.7
        assert metrics.score_correlation == 0.92
        assert metrics.exact_match_rate == 65.0
        assert metrics.within_one_rate == 95.0

    def test_to_dict(self) -> None:
        """Test converting metrics to dictionary."""
        metrics = AlignmentMetrics(
            mean_absolute_error=0.3,
            root_mean_squared_error=0.4,
            score_correlation=0.95,
            exact_match_rate=70.0,
            within_one_rate=98.0
        )
        d = metrics.to_dict()
        assert d["mean_absolute_error"] == 0.3
        assert d["root_mean_squared_error"] == 0.4
        assert d["score_correlation"] == 0.95
        assert d["exact_match_rate"] == 70.0
        assert d["within_one_rate"] == 98.0

    def test_correlation_can_be_none(self) -> None:
        """Test that correlation can be None."""
        metrics = AlignmentMetrics(
            mean_absolute_error=1.0,
            root_mean_squared_error=1.2,
            score_correlation=None,
            exact_match_rate=50.0,
            within_one_rate=75.0
        )
        assert metrics.score_correlation is None
        assert metrics.to_dict()["score_correlation"] is None


class TestModelBenchmarkResult:
    """Test ModelBenchmarkResult dataclass."""

    def test_create_with_scores(self) -> None:
        """Test creating result with scores."""
        evaluator = EvaluatorConfig(model_name="test-model")
        scores = [
            DocumentScore(document_id=1, score=4, reasoning="Good", scoring_time_ms=100.0),
            DocumentScore(document_id=2, score=3, reasoning="OK", scoring_time_ms=120.0),
        ]
        result = ModelBenchmarkResult(
            evaluator=evaluator,
            documents_scored=2,
            total_scoring_time_ms=220.0,
            avg_scoring_time_ms=110.0,
            scores=scores
        )
        assert result.evaluator.model_name == "test-model"
        assert result.documents_scored == 2
        assert result.total_scoring_time_ms == 220.0
        assert result.avg_scoring_time_ms == 110.0
        assert len(result.scores) == 2
        assert result.alignment_metrics is None
        assert result.final_rank is None

    def test_to_dict(self) -> None:
        """Test converting result to dictionary."""
        evaluator = EvaluatorConfig(model_name="test-model")
        result = ModelBenchmarkResult(
            evaluator=evaluator,
            documents_scored=1,
            total_scoring_time_ms=100.0,
            avg_scoring_time_ms=100.0,
            final_rank=1
        )
        d = result.to_dict()
        assert d["evaluator"]["model_name"] == "test-model"
        assert d["documents_scored"] == 1
        assert d["final_rank"] == 1
        assert d["scores"] == []


class TestBenchmarkRun:
    """Test BenchmarkRun dataclass."""

    def test_create_benchmark_run(self) -> None:
        """Test creating a benchmark run."""
        now = datetime.now()
        run = BenchmarkRun(
            run_id=1,
            question_id=10,
            question_text="What are the benefits of exercise?",
            semantic_threshold=0.5,
            documents_found=50,
            status=BenchmarkStatus.RUNNING,
            started_at=now
        )
        assert run.run_id == 1
        assert run.question_id == 10
        assert run.question_text == "What are the benefits of exercise?"
        assert run.status == BenchmarkStatus.RUNNING
        assert run.started_at == now
        assert run.completed_at is None
        assert run.model_results == []

    def test_get_ranked_results(self) -> None:
        """Test getting ranked results sorted by final rank."""
        evaluator1 = EvaluatorConfig(model_name="model-a")
        evaluator2 = EvaluatorConfig(model_name="model-b")
        evaluator3 = EvaluatorConfig(model_name="model-c")

        result1 = ModelBenchmarkResult(
            evaluator=evaluator1,
            documents_scored=10,
            total_scoring_time_ms=1000.0,
            avg_scoring_time_ms=100.0,
            final_rank=2
        )
        result2 = ModelBenchmarkResult(
            evaluator=evaluator2,
            documents_scored=10,
            total_scoring_time_ms=800.0,
            avg_scoring_time_ms=80.0,
            final_rank=1
        )
        result3 = ModelBenchmarkResult(
            evaluator=evaluator3,
            documents_scored=10,
            total_scoring_time_ms=1200.0,
            avg_scoring_time_ms=120.0,
            final_rank=3
        )

        run = BenchmarkRun(
            run_id=1,
            question_id=1,
            question_text="Test question",
            semantic_threshold=0.5,
            documents_found=10,
            status=BenchmarkStatus.COMPLETED,
            started_at=datetime.now(),
            model_results=[result1, result3, result2]  # Intentionally out of order
        )

        ranked = run.get_ranked_results()
        assert len(ranked) == 3
        assert ranked[0].evaluator.model_name == "model-b"  # Rank 1
        assert ranked[1].evaluator.model_name == "model-a"  # Rank 2
        assert ranked[2].evaluator.model_name == "model-c"  # Rank 3

    def test_to_dict(self) -> None:
        """Test converting run to dictionary."""
        now = datetime.now()
        run = BenchmarkRun(
            run_id=5,
            question_id=15,
            question_text="Test question",
            semantic_threshold=0.6,
            documents_found=25,
            status=BenchmarkStatus.COMPLETED,
            started_at=now,
            completed_at=now
        )
        d = run.to_dict()
        assert d["run_id"] == 5
        assert d["question_id"] == 15
        assert d["semantic_threshold"] == 0.6
        assert d["status"] == "completed"
        assert d["started_at"] == now.isoformat()
        assert d["completed_at"] == now.isoformat()


class TestBenchmarkSummary:
    """Test BenchmarkSummary dataclass."""

    def test_create_summary(self) -> None:
        """Test creating a benchmark summary."""
        summary = BenchmarkSummary(
            run_id=1,
            question_text="Test question",
            total_documents=50,
            models_evaluated=3,
            authoritative_model="gpt-oss:120B",
            best_model="gpt-oss:20b",
            best_model_mae=0.4,
            best_model_exact_match_rate=70.0,
            fastest_model="medgemma4B_it_q8:latest",
            fastest_model_avg_time_ms=500.0,
            rankings=[
                {"rank": 1, "model_name": "gpt-oss:20b", "mae": 0.4},
                {"rank": 2, "model_name": "qwen2.5:32b", "mae": 0.5},
            ]
        )
        assert summary.run_id == 1
        assert summary.total_documents == 50
        assert summary.models_evaluated == 3
        assert summary.best_model == "gpt-oss:20b"
        assert summary.best_model_mae == 0.4
        assert len(summary.rankings) == 2

    def test_to_dict(self) -> None:
        """Test converting summary to dictionary."""
        summary = BenchmarkSummary(
            run_id=2,
            question_text="Another question",
            total_documents=30,
            models_evaluated=2,
            authoritative_model="gpt-oss:120B",
            best_model="model-a",
            best_model_mae=0.35,
            best_model_exact_match_rate=75.0,
            fastest_model="model-b",
            fastest_model_avg_time_ms=400.0
        )
        d = summary.to_dict()
        assert d["run_id"] == 2
        assert d["total_documents"] == 30
        assert d["best_model_mae"] == 0.35
        assert d["rankings"] == []


class TestInputValidation:
    """Test input validation in runner (requires mocking)."""

    def test_evaluator_config_requires_model_name(self) -> None:
        """Test that EvaluatorConfig.from_dict requires model_name."""
        with pytest.raises(KeyError):
            EvaluatorConfig.from_dict({})

    def test_evaluator_config_from_dict_with_empty_model_name(self) -> None:
        """Test creating config with empty model name still works (validation at usage)."""
        config = EvaluatorConfig.from_dict({"model_name": ""})
        assert config.model_name == ""
