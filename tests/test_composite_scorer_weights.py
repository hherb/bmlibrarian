"""Regression tests for systematic_review CompositeScorer.

Guards against two confirmed bugs:

1. The composite formula silently ignored the ``paper_weight`` and
   ``source_reliability`` weights (2 of the 8 validated dimensions), capping
   every score at 80% of intent and breaking ``ScoringWeights.practical_focused()``.
2. A ``None`` study assessment (a legitimate QualityAssessor outcome when a
   document has no abstract or the LLM confidence is too low) raised
   ``TypeError`` inside the extraction helpers, aborting an entire review.

Hermetic: no Ollama or PostgreSQL required.
"""

from types import SimpleNamespace

import pytest

from bmlibrarian.agents.systematic_review.data_models import ScoringWeights
from bmlibrarian.agents.systematic_review.scorer import (
    NEUTRAL_SCORE,
    RECENCY_CURRENT_YEAR,
    CompositeScorer,
)


def _make_paper(
    relevance: float = 5.0,
    study_assessment=None,
    paper_weight=None,
    year: int = RECENCY_CURRENT_YEAR,
) -> SimpleNamespace:
    """Build a minimal AssessedPaper-shaped object for scoring."""
    return SimpleNamespace(
        scored_paper=SimpleNamespace(
            relevance_score=relevance,
            paper=SimpleNamespace(year=year),
        ),
        study_assessment=study_assessment,
        paper_weight=paper_weight,
    )


def test_paper_weight_and_source_reliability_weights_are_applied() -> None:
    """A weights profile concentrated on the two forgotten dimensions must score > 0."""
    weights = ScoringWeights(
        relevance=0.0,
        study_quality=0.0,
        methodological_rigor=0.0,
        sample_size=0.0,
        recency=0.0,
        replication_status=0.0,
        paper_weight=0.5,
        source_reliability=0.5,
    )
    assert weights.validate()

    scorer = CompositeScorer(weights=weights)
    paper = _make_paper(paper_weight={"composite_score": 10.0})

    score = scorer.score(paper)

    # paper_weight dimension: 10.0 * 0.5; source_reliability has no data
    # producer yet and contributes the neutral score.
    assert score == pytest.approx(0.5 * 10.0 + 0.5 * NEUTRAL_SCORE)


def test_perfect_paper_with_default_weights_exceeds_old_cap() -> None:
    """With default weights a top paper must score above the old 8.0 ceiling."""
    scorer = CompositeScorer()  # default weights sum to 1.0 across 8 dims
    paper = _make_paper(
        relevance=5.0,
        study_assessment={
            "overall_quality": 10.0,
            "methodological_rigor": 10.0,
            "sample_size_score": 10.0,
        },
        paper_weight={
            "composite_score": 10.0,
            "replication_status": "replicated",
        },
        year=RECENCY_CURRENT_YEAR,
    )

    score = scorer.score(paper)

    assert score > 8.0


def test_none_study_assessment_does_not_crash() -> None:
    """None study assessment / paper weight must degrade to neutral, not raise."""
    scorer = CompositeScorer()
    paper = _make_paper(study_assessment=None, paper_weight=None)

    score = scorer.score(paper)

    assert isinstance(score, float)
    assert 0.0 <= score <= 10.0
