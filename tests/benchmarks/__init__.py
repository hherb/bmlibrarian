"""
Benchmark Suite for SystematicReviewAgent

This module provides validation tools to compare the SystematicReviewAgent's
output against published systematic reviews (e.g., Cochrane reviews).

Key Metrics:
- Recall: Percentage of ground truth papers found by the agent
- Precision: Percentage of agent's included papers that are in ground truth
- Target: 100% recall (all Cochrane-cited papers must be found and scored relevant)

Usage:
    pytest tests/benchmarks/ -v
"""

from .benchmark_utils import (
    GroundTruthPaper,
    CochraneGroundTruth,
    BenchmarkResult,
    calculate_recall_precision,
    match_papers,
    load_ground_truth,
)

__all__ = [
    "GroundTruthPaper",
    "CochraneGroundTruth",
    "BenchmarkResult",
    "calculate_recall_precision",
    "match_papers",
    "load_ground_truth",
]
