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
    paper = _make_paper(paper_weight={"final_weight": 10.0})

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
            "final_weight": 10.0,
            "replication_status_score": 10.0,
        },
        year=RECENCY_CURRENT_YEAR,
    )

    score = scorer.score(paper)

    assert score > 8.0


def test_none_study_assessment_does_not_crash() -> None:
    """None study assessment / paper weight must not raise (#348: no paper weight is left out)."""
    scorer = CompositeScorer()
    paper = _make_paper(study_assessment=None, paper_weight=None)

    score = scorer.score(paper)

    assert isinstance(score, float)
    assert 0.0 <= score <= 10.0


def _real_paper_weight(final_weight: float, replication: float) -> dict:
    """PaperWeightResult.to_dict() output, as QualityAssessor stores it."""
    from datetime import datetime

    from bmlibrarian.agents.paper_weight.models import DimensionScore, PaperWeightResult

    def dim(name: str, score: float) -> DimensionScore:
        return DimensionScore(name, score)

    return PaperWeightResult(
        document_id=1,
        assessor_version="1.0.0",
        assessed_at=datetime.now(),
        study_design=dim("study_design", 8.0),
        sample_size=dim("sample_size", 6.0),
        methodological_quality=dim("methodological_quality", 7.0),
        risk_of_bias=dim("risk_of_bias", 7.0),
        replication_status=dim("replication_status", replication),
        final_weight=final_weight,
        dimension_weights={},
    ).to_dict()


def test_scorer_reads_real_paper_weight_result() -> None:
    """The scorer reads the keys PaperWeightResult.to_dict() emits (#348)."""
    scorer = CompositeScorer()
    pw = _real_paper_weight(final_weight=9.0, replication=8.0)

    assert scorer._extract_paper_weight_score(pw) == 9.0
    assert scorer._extract_replication_score(pw) == 8.0


@pytest.mark.parametrize("paper_weight", [
    None,
    {"document_id": 1, "error": "LLM timeout"},
    {"document_id": 1, "note": "Assessment disabled in configuration"},
    # Saved before #348 fixed the keys: carries no score the scorer reads
    {"document_id": 1, "composite_score": 5.0, "dimensions": [], "error": "x"},
])
def test_missing_paper_weight_is_left_out_and_reweighted(paper_weight) -> None:
    """No paper weight score: the dimension neither raises nor lowers the score."""
    weights = ScoringWeights(
        relevance=0.5,
        study_quality=0.0,
        methodological_rigor=0.0,
        sample_size=0.0,
        recency=0.0,
        replication_status=0.25,
        paper_weight=0.25,
        source_reliability=0.0,
    )
    scorer = CompositeScorer(weights=weights)
    paper = _make_paper(relevance=5.0, paper_weight=paper_weight)

    # Only relevance (normalised 10.0) is left, scaled up to the full weight
    assert scorer.score(paper) == pytest.approx(10.0)


def test_present_paper_weight_counts_at_its_weight() -> None:
    """With every dimension scored, nothing is reweighted."""
    weights = ScoringWeights(
        relevance=0.5,
        study_quality=0.0,
        methodological_rigor=0.0,
        sample_size=0.0,
        recency=0.0,
        replication_status=0.25,
        paper_weight=0.25,
        source_reliability=0.0,
    )
    scorer = CompositeScorer(weights=weights)
    paper = _make_paper(
        relevance=5.0, paper_weight=_real_paper_weight(final_weight=2.0, replication=4.0)
    )

    assert scorer.score(paper) == pytest.approx(0.5 * 10.0 + 0.25 * 4.0 + 0.25 * 2.0)
