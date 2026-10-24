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

from bmlibrarian.agents.systematic_review.data_models import (
    REPLICATION_NONE_RECORDED_SCORE,
    ScoringWeights,
    is_paper_weight_placeholder,
    paper_weight_score,
)
from bmlibrarian.agents.systematic_review.scorer import (
    BIAS_RISK_FIELDS,
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
        document_id=1,
        scored_paper=SimpleNamespace(
            relevance_score=relevance,
            paper=SimpleNamespace(year=year),
        ),
        study_assessment=study_assessment,
        paper_weight=paper_weight,
    )


def _real_paper_weight(
    final_weight: float, replication: float, others: float = 7.0
) -> dict:
    """PaperWeightResult.to_dict() output, as QualityAssessor stores it."""
    from datetime import datetime

    from bmlibrarian.agents.paper_weight.models import DimensionScore, PaperWeightResult

    def dim(name: str, score: float) -> DimensionScore:
        return DimensionScore(name, score)

    return PaperWeightResult(
        document_id=1,
        assessor_version="1.0.0",
        assessed_at=datetime.now(),
        study_design=dim("study_design", others),
        sample_size=dim("sample_size", others),
        methodological_quality=dim("methodological_quality", others),
        risk_of_bias=dim("risk_of_bias", others),
        replication_status=dim("replication_status", replication),
        final_weight=final_weight,
        dimension_weights={},
    ).to_dict()


def _real_study_assessment(**overrides) -> dict:
    """StudyAssessment.to_dict() output, as QualityAssessor stores it."""
    from bmlibrarian.agents.study_assessment_agent import StudyAssessment

    fields = dict(
        study_type="RCT",
        study_design="prospective, double-blinded",
        quality_score=10.0,
        strengths=[],
        limitations=[],
        overall_confidence=0.9,
        confidence_explanation="",
        evidence_level="Level 1 (high)",
        document_id="1",
        document_title="Study",
    )
    fields.update(overrides)
    return StudyAssessment(**fields).to_dict()


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
        study_assessment=_real_study_assessment(
            sample_size="N=5000 participants",
            **{f: "low" for f in BIAS_RISK_FIELDS},
        ),
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
    # Failure placeholder saved before #349: every score 0.0, no error key
    _real_paper_weight(final_weight=0.0, replication=0.0, others=0.0),
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


_PAPER_WEIGHT_ONLY = ScoringWeights(
    relevance=0.5,
    study_quality=0.0,
    methodological_rigor=0.0,
    sample_size=0.0,
    recency=0.0,
    replication_status=0.25,
    paper_weight=0.25,
    source_reliability=0.0,
)


def test_no_replication_on_record_is_left_out() -> None:
    """0.0 replication means "nothing entered", so it must not cost points."""
    scorer = CompositeScorer(weights=_PAPER_WEIGHT_ONLY)
    paper = _make_paper(
        relevance=5.0,
        paper_weight=_real_paper_weight(
            final_weight=4.0, replication=REPLICATION_NONE_RECORDED_SCORE
        ),
    )

    # relevance 10.0 and paper weight 4.0 rescaled from 0.75 to the full 1.0
    assert scorer.score(paper) == pytest.approx((0.5 * 10.0 + 0.25 * 4.0) / 0.75)


def test_no_replication_score_matches_check_replication_status(monkeypatch) -> None:
    """The scorer's "no data" value is what check_replication_status gives for no rows."""
    from unittest.mock import MagicMock

    from bmlibrarian.agents.paper_weight import db

    manager = MagicMock()
    cursor = manager.get_connection.return_value.__enter__.return_value \
        .cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = []
    monkeypatch.setattr(db, "get_db_manager", lambda: manager)

    assert db.check_replication_status(1).score == REPLICATION_NONE_RECORDED_SCORE


def test_no_weighted_dimension_scored_gives_neutral_score() -> None:
    """All weight on paper weight, none present: neutral, not a 0.0 that fails the gate."""
    weights = ScoringWeights(
        relevance=0.0,
        study_quality=0.0,
        methodological_rigor=0.0,
        sample_size=0.0,
        recency=0.0,
        replication_status=0.5,
        paper_weight=0.5,
        source_reliability=0.0,
    )
    scorer = CompositeScorer(weights=weights)

    assert scorer.score(_make_paper(paper_weight=None)) == NEUTRAL_SCORE


@pytest.mark.parametrize("value, expected", [
    (7.5, 7.5),
    (7, 7.0),
    (12.0, 10.0),
    (-1.0, 0.0),
    (float("nan"), None),
    (float("inf"), None),
    (True, None),
    ("7.0", None),
    (None, None),
])
def test_paper_weight_score_values(value, expected) -> None:
    """Finite numbers are clamped to 0-10; anything else is no score."""
    assert paper_weight_score({"final_weight": value}) == expected


def test_paper_weight_score_error_key_with_empty_message() -> None:
    """An error entry marks a failure even when its message is empty."""
    assert paper_weight_score({"final_weight": 7.0, "error": ""}) is None


def test_placeholder_needs_every_score_zero() -> None:
    """A real assessment with a 0.0 final weight but other scores is not a placeholder."""
    assert is_paper_weight_placeholder(_real_paper_weight(0.0, 0.0, others=0.0))
    assert not is_paper_weight_placeholder(_real_paper_weight(0.0, 0.0, others=1.0))
    assert not is_paper_weight_placeholder({"note": "Assessment disabled"})


def test_real_paper_weight_ranks_papers() -> None:
    """Otherwise identical papers are ranked by their final weight (#348)."""
    scorer = CompositeScorer(weights=_PAPER_WEIGHT_ONLY)
    low = _make_paper(paper_weight=_real_paper_weight(final_weight=3.0, replication=5.0))
    high = _make_paper(paper_weight=_real_paper_weight(final_weight=9.0, replication=5.0))

    assert scorer.score(high) > scorer.score(low)


@pytest.mark.parametrize("risks, expected", [
    ({"selection_bias_risk": "low", "detection_bias_risk": "moderate",
      "reporting_bias_risk": "high"}, 2.0),
    ({"selection_bias_risk": "low", "attrition_bias_risk": "unclear"}, 8.0),
    ({"performance_bias_risk": " Moderate "}, 5.0),
    ({"selection_bias_risk": "unclear"}, None),
    ({}, None),
])
def test_rigor_is_worst_rated_bias_domain(risks, expected) -> None:
    """Rigor comes from StudyAssessment's bias ratings: the worst rated domain (#356)."""
    scorer = CompositeScorer()

    assert scorer._extract_methodological_rigor(_real_study_assessment(**risks)) == expected


@pytest.mark.parametrize("sample_size, expected", [
    ("N=25 participants", 2.0),
    ("N=120 participants", 6.0),
    ("850 patients", 8.0),
    ("1,234 patients", 10.0),
    ("450", 6.0),
    (450, 6.0),
    ("not reported", None),
    (None, None),
])
def test_sample_size_is_parsed_from_assessment_text(sample_size, expected) -> None:
    """Sample size comes from StudyAssessment's free-text count (#356)."""
    scorer = CompositeScorer()
    assessment = _real_study_assessment(sample_size=sample_size)

    assert scorer._extract_sample_size_score(assessment) == expected


def test_unrated_rigor_and_sample_size_are_left_out() -> None:
    """An assessment rating neither dimension neither raises nor lowers the score."""
    weights = ScoringWeights(
        relevance=0.5,
        study_quality=0.0,
        methodological_rigor=0.25,
        sample_size=0.25,
        recency=0.0,
        replication_status=0.0,
        paper_weight=0.0,
        source_reliability=0.0,
    )
    scorer = CompositeScorer(weights=weights)
    paper = _make_paper(
        relevance=5.0,
        study_assessment=_real_study_assessment(selection_bias_risk="unclear"),
    )

    assert scorer.score(paper) == pytest.approx(10.0)


def test_bias_ratings_rank_papers() -> None:
    """Otherwise identical papers are ranked by their worst bias rating (#356)."""
    weights = ScoringWeights(
        relevance=0.5,
        study_quality=0.0,
        methodological_rigor=0.5,
        sample_size=0.0,
        recency=0.0,
        replication_status=0.0,
        paper_weight=0.0,
        source_reliability=0.0,
    )
    scorer = CompositeScorer(weights=weights)
    low = _make_paper(study_assessment=_real_study_assessment(selection_bias_risk="low"))
    high = _make_paper(study_assessment=_real_study_assessment(selection_bias_risk="high"))

    assert scorer.score(low) > scorer.score(high)
