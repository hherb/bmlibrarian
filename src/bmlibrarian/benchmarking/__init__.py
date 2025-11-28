"""
Model Benchmarking System for BMLibrarian

Provides tools for benchmarking document scoring models against
an authoritative model to evaluate accuracy and performance.

Key Components:
- BenchmarkRunner: Orchestrates benchmark runs
- BenchmarkDatabase: Database operations for benchmark data
- Data types: Type-safe dataclasses for benchmark results

Usage Example:
    >>> import psycopg
    >>> from bmlibrarian.benchmarking import BenchmarkRunner
    >>>
    >>> conn = psycopg.connect(dbname="knowledgebase", user="hherb")
    >>> runner = BenchmarkRunner(conn, authoritative_model="gpt-oss:120B")
    >>>
    >>> result = runner.run_benchmark(
    ...     question_text="What are the benefits of exercise?",
    ...     models=["gpt-oss:20b", "medgemma4B_it_q8:latest"]
    ... )
    >>>
    >>> print(runner.print_summary(result))
"""

from .data_types import (
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

from .database import BenchmarkDatabase

from .runner import BenchmarkRunner


__all__ = [
    # Data types
    "BenchmarkStatus",
    "EvaluatorConfig",
    "DocumentScore",
    "AlignmentMetrics",
    "ModelBenchmarkResult",
    "BenchmarkRun",
    "BenchmarkSummary",
    # Constants
    "SEMANTIC_THRESHOLD",
    "BEST_REASONING_MODEL",
    "DEFAULT_TEMPERATURE",
    "DEFAULT_TOP_P",
    "DEFAULT_OLLAMA_HOST",
    "DEFAULT_DOCUMENT_LIMIT",
    "MIN_SCORE",
    "MAX_SCORE",
    # Database
    "BenchmarkDatabase",
    # Runner
    "BenchmarkRunner",
]
