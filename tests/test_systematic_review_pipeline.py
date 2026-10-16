"""
Tests for the SystematicReviewAgent review pipeline and checkpoint resume.

Fresh runs (``run_review``) and resumes (``run_review_from_checkpoint``)
share one pipeline (``pipeline.py``). These tests drive the real agent with
an in-memory evaluation store and fake search/scoring/quality workers, and
resume from checkpoint files the agent itself wrote, to pin:

- evaluations already saved in the run are reused, never re-run;
- the configured search strategy (phased or standard) is used on resume;
- the quality-gate threshold decides final inclusion on every path;
- evaluation runs end completed / paused / failed, and resumes reopen them;
- a resume that cannot find its evaluation run fails loudly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, Iterator, List, Optional, Set, Tuple
from unittest.mock import MagicMock, patch

import pytest

from bmlibrarian.agents.systematic_review import (
    ResumeError,
    SearchCriteria,
    SystematicReviewAgent,
    SystematicReviewConfig,
    SystematicReviewError,
)
from bmlibrarian.agents.systematic_review.data_models import (
    AssessedPaper,
    ExclusionStage,
    ExecutedQuery,
    InclusionDecision,
    InclusionStatus,
    PaperData,
    PlannedQuery,
    QueryType,
    ScoredPaper,
    SearchPlan,
)
from bmlibrarian.agents.systematic_review.documenter import (
    CHECKPOINT_INITIAL_RESULTS,
    CHECKPOINT_QUALITY_ASSESSMENT,
    CHECKPOINT_SCORING_COMPLETE,
    CHECKPOINT_SEARCH_STRATEGY,
)
from bmlibrarian.agents.systematic_review.executor import (
    build_paper_sources,
    collect_phase1_document_ids,
)
from bmlibrarian.agents.systematic_review.pipeline import (
    PipelineComponents,
    average_relevance,
    markdown_report_path,
)
from bmlibrarian.agents.systematic_review.reporter import Reporter
from bmlibrarian.agents.systematic_review.scorer import RelevanceScorer
from bmlibrarian.agents.systematic_review.resume_mixin import (
    load_checkpoint_file,
    parse_document_ids,
    parse_evaluation_run_id,
)
from bmlibrarian.evaluations import EvaluationType
from bmlibrarian.evaluations.store import DocumentEvaluation, EvaluationRun

RESEARCH_QUESTION = "Do statins reduce cardiovascular events?"
RELEVANCE_THRESHOLD = 2.5
QUALITY_THRESHOLD = 4.0

# Paper 4 is rejected by the initial filter; paper 3 scores below the
# relevance threshold; paper 2 passes relevance but fails the quality gate.
PAPER_IDS = [1, 2, 3, 4]
REJECTED_BY_FILTER = {4}
RELEVANCE = {1: 4.0, 2: 3.0, 3: 1.0}
QUALITY = {1: 8.0, 2: 2.0}


# =============================================================================
# Fakes
# =============================================================================

class FakeEvaluationStore:
    """In-memory stand-in for EvaluationStore."""

    def __init__(self) -> None:
        """Create an empty store."""
        self.runs: Dict[int, EvaluationRun] = {}
        self.evaluations: List[DocumentEvaluation] = []

    def create_run(
        self,
        run_type: Any,
        research_question: str,
        evaluator_id: Optional[int] = None,
        config: Optional[Dict[str, Any]] = None,
        documents_total: int = 0,
        **_: Any,
    ) -> EvaluationRun:
        """Create an in-progress run."""
        run_id = len(self.runs) + 1
        run = EvaluationRun(
            run_id=run_id,
            run_type="systematic_review",
            research_question_id=None,
            research_question_text=research_question,
            evaluator_id=evaluator_id,
            status="in_progress",
            config_snapshot=config,
            documents_total=documents_total,
            documents_processed=0,
            started_at=datetime.now(),
            completed_at=None,
        )
        self.runs[run_id] = run
        return run

    def get_run(self, run_id: int) -> Optional[EvaluationRun]:
        """Return a run by ID."""
        return self.runs.get(run_id)

    def reopen_run(self, run_id: int) -> None:
        """Put a run back in progress."""
        self.runs[run_id].status = "in_progress"
        self.runs[run_id].error_message = None

    def pause_run(self, run_id: int) -> None:
        """Pause a run."""
        self.runs[run_id].status = "paused"

    def complete_run(
        self, run_id: int, status: Any = None, error_message: Optional[str] = None,
    ) -> None:
        """Complete a run with a final status."""
        self.runs[run_id].status = status.value
        self.runs[run_id].error_message = error_message

    def save_evaluation(
        self,
        run_id: int,
        document_id: int,
        evaluation_type: EvaluationType,
        evaluation_data: Dict[str, Any],
        primary_score: Optional[float] = None,
        evaluator_id: Optional[int] = None,
        reasoning: Optional[str] = None,
        processing_time_ms: Optional[int] = None,
        **_: Any,
    ) -> int:
        """Store one evaluation."""
        evaluation_id = len(self.evaluations) + 1
        self.evaluations.append(DocumentEvaluation(
            evaluation_id=evaluation_id,
            run_id=run_id,
            document_id=document_id,
            evaluator_id=evaluator_id,
            evaluation_type=evaluation_type.value,
            primary_score=primary_score,
            confidence=None,
            evaluation_data=evaluation_data,
            reasoning=reasoning,
            processing_time_ms=processing_time_ms,
            evaluated_at=datetime.now(),
        ))
        return evaluation_id

    def _select(self, run_id: int, evaluation_type: Optional[EvaluationType]) -> List[DocumentEvaluation]:
        """Evaluations of a run, optionally of one type."""
        return [
            e for e in self.evaluations
            if e.run_id == run_id
            and (evaluation_type is None or e.evaluation_type == evaluation_type.value)
        ]

    def get_evaluated_document_ids(
        self, run_id: int, evaluation_type: Optional[EvaluationType] = None, **_: Any,
    ) -> List[int]:
        """Document IDs evaluated in a run."""
        return [e.document_id for e in self._select(run_id, evaluation_type)]

    def get_evaluations_for_run(
        self, run_id: int, evaluation_type: Optional[EvaluationType] = None, **_: Any,
    ) -> List[DocumentEvaluation]:
        """Evaluations of a run."""
        return self._select(run_id, evaluation_type)

    def get_evaluations_for_multiple_types(
        self, run_id: int, evaluation_types: List[EvaluationType], **_: Any,
    ) -> Dict[str, List[DocumentEvaluation]]:
        """Evaluations of a run keyed by type value."""
        return {t.value: self._select(run_id, t) for t in evaluation_types}

    def seed_score(self, run_id: int, document_id: int, score: float) -> None:
        """Pre-populate a relevance score (as a crashed run would have left)."""
        self.save_evaluation(
            run_id=run_id,
            document_id=document_id,
            evaluation_type=EvaluationType.RELEVANCE_SCORE,
            evaluation_data={"score": score, "inclusion_decision": "included"},
            primary_score=score,
            reasoning="seeded",
        )


def make_paper(doc_id: int) -> PaperData:
    """A minimal paper."""
    return PaperData(document_id=doc_id, title=f"Paper {doc_id}", authors=["Author A"], year=2020)


def paper_row(doc_id: int) -> Dict[str, Any]:
    """A database row for ``make_paper(doc_id)``."""
    return {"id": doc_id, "title": f"Paper {doc_id}", "authors": ["Author A"], "year": 2020}


def make_plan() -> SearchPlan:
    """A two-query plan: one semantic (phase 1), one keyword (phase 2)."""
    return SearchPlan(
        queries=[
            PlannedQuery(
                query_id="q-sem", query_text="statins cardiovascular",
                query_type=QueryType.SEMANTIC, purpose="baseline", expected_coverage="core",
            ),
            PlannedQuery(
                query_id="q-kw", query_text="statin & mi",
                query_type=QueryType.KEYWORD, purpose="keyword", expected_coverage="core",
            ),
        ],
        total_estimated_yield=len(PAPER_IDS),
        search_rationale="test",
    )


def make_executed_queries(plan: SearchPlan) -> List[ExecutedQuery]:
    """Semantic query finds papers 1-3, keyword query finds 3-4."""
    sem, kw = plan.queries
    return [
        ExecutedQuery(planned_query=sem, document_ids=[1, 2, 3],
                      execution_time_seconds=0.1, actual_results=3),
        ExecutedQuery(planned_query=kw, document_ids=[3, 4],
                      execution_time_seconds=0.1, actual_results=2),
    ]


@dataclass
class FakeWorkers:
    """Fake pipeline workers that record what they were asked to do."""

    standard_searches: int = 0
    phased_searches: int = 0
    scored_ids: List[int] = field(default_factory=list)
    assessed_ids: List[int] = field(default_factory=list)
    relevance: Dict[int, float] = field(default_factory=lambda: dict(RELEVANCE))
    quality: Dict[int, float] = field(default_factory=lambda: dict(QUALITY))
    scoring_error: Optional[Exception] = None
    query_feedback_calls: int = 0
    uncertain_ids: Set[int] = field(default_factory=set)

    # --- executor -----------------------------------------------------------

    def execute_plan(self, plan: SearchPlan) -> SimpleNamespace:
        """Standard search."""
        self.standard_searches += 1
        executed = make_executed_queries(plan)
        return SimpleNamespace(
            executed_queries=executed,
            papers=[make_paper(i) for i in PAPER_IDS],
            paper_sources=build_paper_sources(executed),
            total_before_dedup=5,
            count=len(PAPER_IDS),
            deduplication_rate=0.2,
        )

    def execute_phased_plan(self, plan: SearchPlan, max_phase2_no_overlap: int = 10) -> SimpleNamespace:
        """Phased search."""
        self.phased_searches += 1
        executed = make_executed_queries(plan)
        return SimpleNamespace(
            executed_queries=executed,
            all_papers=[make_paper(i) for i in PAPER_IDS],
            paper_sources=build_paper_sources(executed),
            phase1_document_ids={1, 2, 3},
            total_count=len(PAPER_IDS),
            phase1_count=3,
            phase2_new_count=1,
        )

    # --- initial filter -------------------------------------------------------

    def filter_batch(self, papers: List[PaperData]) -> SimpleNamespace:
        """Reject REJECTED_BY_FILTER."""
        return SimpleNamespace(
            passed=[p for p in papers if p.document_id not in REJECTED_BY_FILTER],
            rejected=[(p, "Wrong study type") for p in papers if p.document_id in REJECTED_BY_FILTER],
        )

    # --- relevance scorer -------------------------------------------------------

    def score_batch(
        self,
        papers: List[PaperData],
        evaluate_inclusion: bool,
        paper_sources: Dict[int, List[str]],
        save_callback: Callable[[ScoredPaper], Any],
    ) -> SimpleNamespace:
        """Score each paper from ``relevance`` and save it."""
        if self.scoring_error:
            raise self.scoring_error
        scored = []
        for paper in papers:
            self.scored_ids.append(paper.document_id)
            sp = ScoredPaper(
                paper=paper,
                relevance_score=self.relevance[paper.document_id],
                relevance_rationale="fake",
                inclusion_decision=(
                    InclusionDecision(
                        status=InclusionStatus.UNCERTAIN,
                        stage=ExclusionStage.RELEVANCE_SCORING,
                        reasons=["unclear"],
                        rationale="needs human review",
                    )
                    if paper.document_id in self.uncertain_ids
                    else InclusionDecision.create_included(
                        stage=ExclusionStage.RELEVANCE_SCORING,
                        rationale="meets criteria",
                        criteria_matched=[],
                    )
                ),
            )
            save_callback(sp)
            scored.append(sp)
        return SimpleNamespace(
            scored_papers=scored,
            failed_papers=[],
            average_score=average_relevance(scored),
        )

    def apply_relevance_threshold(
        self, scored_papers: List[ScoredPaper], threshold: float,
    ) -> Tuple[List[ScoredPaper], List[ScoredPaper]]:
        """The real RelevanceScorer split (it also re-labels excluded papers)."""
        return RelevanceScorer.apply_relevance_threshold(
            self, scored_papers, threshold=threshold  # type: ignore[arg-type]
        )

    def evaluate_query_effectiveness(self, **_: Any) -> SimpleNamespace:
        """Record a query-feedback evaluation."""
        self.query_feedback_calls += 1
        return SimpleNamespace(
            total_effective_queries=1, total_queries_executed=2, effective_ratio=0.5,
            effective_queries=[], ineffective_queries=[],
        )

    # --- quality assessor ---------------------------------------------------------

    def assess_batch(
        self, papers: List[ScoredPaper], save_callback: Callable[[AssessedPaper], Any],
    ) -> SimpleNamespace:
        """Assess each paper from ``quality`` and save it."""
        assessed = []
        for sp in papers:
            self.assessed_ids.append(sp.paper.document_id)
            ap = AssessedPaper(
                scored_paper=sp,
                study_assessment={"study_design": "rct"},
                paper_weight={},
                composite_score=self.quality[sp.paper.document_id],
            )
            save_callback(ap)
            assessed.append(ap)
        return SimpleNamespace(assessed_papers=assessed, failed_papers=[], assessment_statistics={})

    # --- composite scorer -----------------------------------------------------------

    def score_and_rank(self, papers: List[AssessedPaper]) -> List[AssessedPaper]:
        """Rank by the saved composite score."""
        ranked = sorted(papers, key=lambda p: p.composite_score or 0.0, reverse=True)
        for rank, paper in enumerate(ranked, start=1):
            paper.final_rank = rank
        return ranked

    def apply_quality_gate(
        self, papers: List[AssessedPaper], threshold: float,
    ) -> Tuple[List[AssessedPaper], List[AssessedPaper]]:
        """Split by composite score."""
        passed = [p for p in papers if (p.composite_score or 0.0) >= threshold]
        failed = [p for p in papers if (p.composite_score or 0.0) < threshold]
        return passed, failed


def make_config(use_phased_search: bool = False) -> SystematicReviewConfig:
    """Deterministic config: no synthesis, explicit thresholds."""
    return SystematicReviewConfig(
        relevance_threshold=RELEVANCE_THRESHOLD,
        quality_threshold=QUALITY_THRESHOLD,
        enable_evidence_synthesis=False,
        use_phased_search=use_phased_search,
        enable_query_feedback=True,
    )


def make_agent(
    store: FakeEvaluationStore,
    workers: FakeWorkers,
    config: Optional[SystematicReviewConfig] = None,
) -> SystematicReviewAgent:
    """A real agent wired to the fake store and workers."""

    def install_store(self: SystematicReviewAgent) -> None:
        self._evaluation_store = store
        self._evaluation_run = None
        self._evaluator_id = 1

    with patch.object(SystematicReviewAgent, "_init_evaluation_store", install_store):
        agent = SystematicReviewAgent(
            db_manager=MagicMock(),
            config=config or make_config(),
            show_model_info=False,
        )

    def build_components(include_executor: bool) -> PipelineComponents:
        return PipelineComponents(
            executor=workers if include_executor else None,
            initial_filter=workers,
            scorer=workers,
            quality_assessor=workers,
            composite_scorer=workers,
            reporter=Reporter(
                documenter=agent.documenter,
                criteria=agent._criteria,
                weights=agent._weights,
            ),
        )

    agent._build_pipeline_components = build_components  # type: ignore[method-assign]
    return agent


def make_criteria(question: str = RESEARCH_QUESTION) -> SearchCriteria:
    """Valid search criteria."""
    return SearchCriteria(
        research_question=question,
        purpose="testing",
        inclusion_criteria=["Human studies"],
        exclusion_criteria=["Animal studies"],
    )


def stop_at(checkpoint_type: str) -> Callable[[str, Dict], bool]:
    """Checkpoint callback that rejects ``checkpoint_type`` and approves others."""
    return lambda cp_type, state: cp_type != checkpoint_type


@pytest.fixture(autouse=True)
def fake_planner_and_database() -> Iterator[None]:
    """Offline planner and document fetches."""
    planner = MagicMock()
    planner.generate_search_plan.return_value = make_plan()

    def fetch(ids: Set[int]) -> List[Dict[str, Any]]:
        return [paper_row(i) for i in sorted(ids)]

    with patch("bmlibrarian.agents.systematic_review.planner.Planner", return_value=planner), \
            patch("bmlibrarian.database.fetch_documents_by_ids", side_effect=fetch):
        yield


def run_and_stop(
    tmp_path: Path,
    store: FakeEvaluationStore,
    checkpoint_type: str,
    config: Optional[SystematicReviewConfig] = None,
) -> Tuple[FakeWorkers, Path]:
    """Run a fresh review that is rejected at ``checkpoint_type``; return its checkpoint file."""
    workers = FakeWorkers()
    agent = make_agent(store, workers, config)
    result = agent.run_review(
        make_criteria(),
        interactive=True,
        output_path=str(tmp_path / "review.json"),
        checkpoint_callback=stop_at(checkpoint_type),
    )
    assert result.statistics.final_included == 0
    files = list((tmp_path / "checkpoints").glob(f"*_{checkpoint_type}.json"))
    assert len(files) == 1
    return workers, files[0]


def included_ids(result: Any) -> List[int]:
    """Document IDs of the included papers of a result."""
    return [p["document_id"] for p in result.included_papers]


# =============================================================================
# Fresh runs
# =============================================================================

class TestFreshRun:
    """run_review end to end."""

    def test_complete_run_applies_every_gate_and_completes_the_run(self) -> None:
        """Filter, relevance threshold and quality gate each exclude one paper."""
        store = FakeEvaluationStore()
        workers = FakeWorkers()
        agent = make_agent(store, workers)

        result = agent.run_review(make_criteria(), interactive=False)

        assert included_ids(result) == [1]
        stats = result.statistics
        assert stats.total_considered == 4
        assert stats.passed_initial_filter == 3
        assert stats.passed_relevance_threshold == 2
        assert stats.passed_quality_gate == 1
        assert stats.final_excluded == 3
        assert sorted(workers.scored_ids) == [1, 2, 3]
        assert sorted(workers.assessed_ids) == [1, 2]
        assert store.runs[1].status == "completed"

    def test_standard_search_when_phased_disabled(self) -> None:
        """use_phased_search=False runs the standard search, no query feedback."""
        workers = FakeWorkers()
        make_agent(FakeEvaluationStore(), workers).run_review(make_criteria(), interactive=False)
        assert (workers.standard_searches, workers.phased_searches) == (1, 0)
        assert workers.query_feedback_calls == 0

    def test_phased_search_runs_query_feedback(self) -> None:
        """use_phased_search=True runs the phased search and query feedback."""
        workers = FakeWorkers()
        agent = make_agent(FakeEvaluationStore(), workers, make_config(use_phased_search=True))
        agent.run_review(make_criteria(), interactive=False)
        assert (workers.standard_searches, workers.phased_searches) == (0, 1)
        assert workers.query_feedback_calls == 1

    def test_no_paper_above_relevance_threshold_does_not_crash(self) -> None:
        """Nothing to assess used to leave the quality result unbound."""
        store = FakeEvaluationStore()
        workers = FakeWorkers(relevance={1: 1.0, 2: 1.0, 3: 1.0})
        result = make_agent(store, workers).run_review(make_criteria(), interactive=False)
        assert included_ids(result) == []
        assert workers.assessed_ids == []
        assert result.statistics.passed_relevance_threshold == 0
        assert store.runs[1].status == "completed"

    def test_zero_score_counts_as_excluded(self) -> None:
        """A 0.0 relevance score is a below-threshold exclusion, not dropped."""
        workers = FakeWorkers(relevance={1: 4.0, 2: 3.0, 3: 0.0})
        result = make_agent(FakeEvaluationStore(), workers).run_review(make_criteria(), interactive=False)
        excluded = {p["document_id"] for p in result.excluded_papers}
        assert {2, 3, 4} <= excluded

    def test_uncertain_screening_decisions_are_reported(self) -> None:
        """Above-threshold papers with an uncertain screening decision are flagged."""
        workers = FakeWorkers(uncertain_ids={1})
        result = make_agent(FakeEvaluationStore(), workers).run_review(
            make_criteria(), interactive=False,
        )
        assert [p["document_id"] for p in result.uncertain_papers] == [1]
        assert result.statistics.uncertain_for_review == 1

    def test_rejected_checkpoint_pauses_the_run(self) -> None:
        """An aborted review returns an empty result and pauses its run."""
        store = FakeEvaluationStore()
        workers = FakeWorkers()
        result = make_agent(store, workers).run_review(
            make_criteria(), interactive=True,
            checkpoint_callback=stop_at(CHECKPOINT_SCORING_COMPLETE),
        )
        assert result.statistics.final_included == 0
        assert workers.assessed_ids == []
        assert store.runs[1].status == "paused"

    def test_failure_marks_the_run_failed(self) -> None:
        """A worker error fails the run and surfaces as SystematicReviewError."""
        store = FakeEvaluationStore()
        workers = FakeWorkers(scoring_error=RuntimeError("LLM exploded"))
        with pytest.raises(SystematicReviewError, match="LLM exploded"):
            make_agent(store, workers).run_review(make_criteria(), interactive=False)
        assert store.runs[1].status == "failed"
        assert "LLM exploded" in (store.runs[1].error_message or "")

    def test_writes_json_and_markdown_reports(self, tmp_path: Path) -> None:
        """output_path produces both report files."""
        output = tmp_path / "review.json"
        make_agent(FakeEvaluationStore(), FakeWorkers()).run_review(
            make_criteria(), interactive=False, output_path=str(output),
        )
        assert output.exists()
        assert (tmp_path / "review.md").exists()


# =============================================================================
# Resume
# =============================================================================

class TestResume:
    """run_review_from_checkpoint, from checkpoint files the agent wrote."""

    def test_resume_from_initial_results_skips_already_scored_papers(self, tmp_path: Path) -> None:
        """Papers scored before the interruption are not re-scored."""
        store = FakeEvaluationStore()
        _, checkpoint = run_and_stop(tmp_path, store, CHECKPOINT_INITIAL_RESULTS)
        store.seed_score(run_id=1, document_id=1, score=RELEVANCE[1])

        workers = FakeWorkers()
        result = make_agent(store, workers).run_review_from_checkpoint(
            str(checkpoint), interactive=False,
        )

        assert sorted(workers.scored_ids) == [2, 3]
        assert included_ids(result) == [1]
        assert result.statistics.total_considered == 4
        assert result.statistics.passed_initial_filter == 3
        assert store.runs[1].status == "completed"

    def test_resume_from_scoring_complete_skips_already_assessed_papers(self, tmp_path: Path) -> None:
        """Only above-threshold papers not yet assessed are assessed."""
        store = FakeEvaluationStore()
        first, checkpoint = run_and_stop(tmp_path, store, CHECKPOINT_QUALITY_ASSESSMENT)
        assert sorted(first.assessed_ids) == [1, 2]
        # Pretend the run died after scoring with paper 1 already assessed.
        store.evaluations = [
            e for e in store.evaluations
            if not (e.evaluation_type == EvaluationType.QUALITY_ASSESSMENT.value and e.document_id == 2)
        ]
        scoring_checkpoint = checkpoint.with_name(
            checkpoint.name.replace(CHECKPOINT_QUALITY_ASSESSMENT, CHECKPOINT_SCORING_COMPLETE)
        )
        assert scoring_checkpoint.exists()

        workers = FakeWorkers()
        result = make_agent(store, workers).run_review_from_checkpoint(
            str(scoring_checkpoint), interactive=False,
        )

        assert workers.scored_ids == []
        assert workers.assessed_ids == [2]
        assert included_ids(result) == [1]

    def test_resume_applies_the_quality_gate(self, tmp_path: Path) -> None:
        """Paper 2 passed screening but fails the gate: it must stay excluded."""
        store = FakeEvaluationStore()
        _, checkpoint = run_and_stop(tmp_path, store, CHECKPOINT_QUALITY_ASSESSMENT)

        workers = FakeWorkers()
        result = make_agent(store, workers).run_review_from_checkpoint(
            str(checkpoint), interactive=False,
        )

        assert included_ids(result) == [1]
        assert result.statistics.passed_quality_gate == 1
        assert workers.scored_ids == [] and workers.assessed_ids == []
        excluded = {p["document_id"] for p in result.excluded_papers}
        assert excluded == {2, 3, 4}

    def test_resume_from_search_strategy_uses_phased_search(self, tmp_path: Path) -> None:
        """Resume honours use_phased_search instead of always running the standard search."""
        config = make_config(use_phased_search=True)
        store = FakeEvaluationStore()
        _, checkpoint = run_and_stop(tmp_path, store, CHECKPOINT_SEARCH_STRATEGY, config)

        workers = FakeWorkers()
        result = make_agent(store, workers, config).run_review_from_checkpoint(
            str(checkpoint), interactive=False,
        )

        assert (workers.standard_searches, workers.phased_searches) == (0, 1)
        assert workers.query_feedback_calls == 1
        assert included_ids(result) == [1]

    def test_resume_restores_provenance_and_baseline(self, tmp_path: Path) -> None:
        """Paper sources and the phase-1 baseline are rebuilt from executed queries."""
        config = make_config(use_phased_search=True)
        store = FakeEvaluationStore()
        _, checkpoint = run_and_stop(tmp_path, store, CHECKPOINT_INITIAL_RESULTS, config)

        workers = FakeWorkers()
        agent = make_agent(store, workers, config)
        agent.run_review_from_checkpoint(str(checkpoint), interactive=False)

        assert agent._paper_sources[3] == ["q-sem", "q-kw"]
        assert agent._semantic_baseline_ids == {1, 2, 3}
        assert workers.query_feedback_calls == 1

    def test_resume_with_raised_relevance_threshold(self, tmp_path: Path) -> None:
        """An assessed paper now below the threshold is excluded, never also included."""
        store = FakeEvaluationStore()
        _, checkpoint = run_and_stop(tmp_path, store, CHECKPOINT_QUALITY_ASSESSMENT)

        config = make_config()
        config.relevance_threshold = 3.5  # paper 2 (3.0) drops below
        workers = FakeWorkers(quality={1: 8.0, 2: 9.0})
        result = make_agent(store, workers, config).run_review_from_checkpoint(
            str(checkpoint), interactive=False,
        )

        included = included_ids(result)
        excluded = [p["document_id"] for p in result.excluded_papers]
        assert included == [1]
        assert sorted(excluded) == [2, 3, 4]
        stats = result.statistics
        assert stats.passed_relevance_threshold == 1
        assert stats.final_included + stats.final_excluded == stats.total_considered

    def test_resume_with_lowered_relevance_threshold(self, tmp_path: Path) -> None:
        """A paper newly above the threshold is assessed, not dropped from the report."""
        store = FakeEvaluationStore()
        _, checkpoint = run_and_stop(tmp_path, store, CHECKPOINT_QUALITY_ASSESSMENT)

        config = make_config()
        config.relevance_threshold = 0.5  # paper 3 (1.0) rises above
        workers = FakeWorkers(quality={1: 8.0, 2: 2.0, 3: 7.0})
        result = make_agent(store, workers, config).run_review_from_checkpoint(
            str(checkpoint), interactive=False,
        )

        assert workers.assessed_ids == [3]
        assert sorted(included_ids(result)) == [1, 3]
        stats = result.statistics
        assert stats.passed_relevance_threshold == 3
        assert stats.final_included + stats.final_excluded == stats.total_considered

    def test_resume_reopens_a_failed_run(self, tmp_path: Path) -> None:
        """A run that failed after its checkpoint is reopened and completed."""
        store = FakeEvaluationStore()
        _, checkpoint = run_and_stop(tmp_path, store, CHECKPOINT_SCORING_COMPLETE)
        store.runs[1].status = "failed"

        make_agent(store, FakeWorkers()).run_review_from_checkpoint(
            str(checkpoint), interactive=False,
        )
        assert store.runs[1].status == "completed"

    def test_resume_does_not_keep_state_from_a_previous_review(self, tmp_path: Path) -> None:
        """Restoring replaces all state on a reused agent instance."""
        store = FakeEvaluationStore()
        _, checkpoint = run_and_stop(tmp_path, store, CHECKPOINT_SCORING_COMPLETE)

        agent = make_agent(store, FakeWorkers())
        agent._rejected_initial_filter = [(make_paper(99), "stale")]
        agent.run_review_from_checkpoint(str(checkpoint), interactive=False)

        assert [p.document_id for p, _ in agent._rejected_initial_filter] == [4]


class TestResumeFailsLoudly:
    """A resume that cannot restore its evaluations must not report nothing."""

    def _rewrite(self, checkpoint: Path, **changes: Any) -> None:
        """Edit fields of a checkpoint file."""
        data = json.loads(checkpoint.read_text())
        data.update(changes)
        checkpoint.write_text(json.dumps(data))

    def test_missing_run_id_at_a_late_checkpoint_raises(self, tmp_path: Path) -> None:
        """Scores live in the run: without it, a late resume cannot continue."""
        store = FakeEvaluationStore()
        _, checkpoint = run_and_stop(tmp_path, store, CHECKPOINT_SCORING_COMPLETE)
        self._rewrite(checkpoint, evaluation_run_id=None)
        with pytest.raises(ResumeError, match="no evaluation run"):
            make_agent(store, FakeWorkers()).run_review_from_checkpoint(str(checkpoint))

    def test_unknown_run_id_raises(self, tmp_path: Path) -> None:
        """A run ID absent from the database (wrong database?) raises."""
        store = FakeEvaluationStore()
        _, checkpoint = run_and_stop(tmp_path, store, CHECKPOINT_SCORING_COMPLETE)
        self._rewrite(checkpoint, evaluation_run_id=999)
        with pytest.raises(ResumeError, match="999"):
            make_agent(store, FakeWorkers()).run_review_from_checkpoint(str(checkpoint))

    def test_run_of_another_question_raises(self, tmp_path: Path) -> None:
        """A run ID pointing at a different review raises."""
        store = FakeEvaluationStore()
        _, checkpoint = run_and_stop(tmp_path, store, CHECKPOINT_SCORING_COMPLETE)
        store.runs[1].research_question_text = "Something else entirely?"
        with pytest.raises(ResumeError, match="different research question"):
            make_agent(store, FakeWorkers()).run_review_from_checkpoint(str(checkpoint))

    def test_missing_run_id_at_an_early_checkpoint_starts_a_new_run(self, tmp_path: Path) -> None:
        """Nothing was evaluated yet, so a fresh run is fine."""
        store = FakeEvaluationStore()
        _, checkpoint = run_and_stop(tmp_path, store, CHECKPOINT_INITIAL_RESULTS)
        self._rewrite(checkpoint, evaluation_run_id=None)

        workers = FakeWorkers()
        result = make_agent(store, workers).run_review_from_checkpoint(
            str(checkpoint), interactive=False,
        )
        assert included_ids(result) == [1]
        assert store.runs[2].status == "completed"

    def test_malformed_run_id_raises_value_error(self, tmp_path: Path) -> None:
        """Untrusted file data is validated."""
        store = FakeEvaluationStore()
        _, checkpoint = run_and_stop(tmp_path, store, CHECKPOINT_SCORING_COMPLETE)
        self._rewrite(checkpoint, evaluation_run_id="1; DROP TABLE")
        with pytest.raises(ValueError, match="evaluation_run_id"):
            make_agent(store, FakeWorkers()).run_review_from_checkpoint(str(checkpoint))


# =============================================================================
# Pure helpers
# =============================================================================

class TestHelpers:
    """Pure functions used by the pipeline and resume."""

    def test_build_paper_sources_keeps_execution_order(self) -> None:
        """Each document lists the queries that found it, in order."""
        sources = build_paper_sources(make_executed_queries(make_plan()))
        assert sources == {1: ["q-sem"], 2: ["q-sem"], 3: ["q-sem", "q-kw"], 4: ["q-kw"]}

    def test_phase1_ids_come_from_semantic_queries_only(self) -> None:
        """Keyword results are not part of the semantic baseline."""
        assert collect_phase1_document_ids(make_executed_queries(make_plan())) == {1, 2, 3}

    @pytest.mark.parametrize("path, expected", [
        ("out/review.json", "out/review.md"),
        ("out/review", "out/review.md"),
        ("out/review.json.bak", "out/review.json.bak.md"),
    ])
    def test_markdown_report_path(self, path: str, expected: str) -> None:
        """Only a trailing .json is replaced."""
        assert markdown_report_path(path) == expected

    def test_average_relevance(self) -> None:
        """Mean score, 0.0 for nothing."""
        papers = [
            ScoredPaper(
                paper=make_paper(i), relevance_score=s, relevance_rationale="",
                inclusion_decision=InclusionDecision(
                    status=InclusionStatus.UNCERTAIN, stage=ExclusionStage.RELEVANCE_SCORING,
                    reasons=[], rationale="",
                ),
            )
            for i, s in ((1, 2.0), (2, 4.0))
        ]
        assert average_relevance(papers) == 3.0
        assert average_relevance([]) == 0.0

    def test_parse_document_ids(self) -> None:
        """Lists of ints pass; anything else is rejected."""
        assert parse_document_ids([1, 2], "f") == [1, 2]
        assert parse_document_ids(None, "f") == []
        for bad in ("1,2", [1, "2"], [True], {"a": 1}):
            with pytest.raises(ValueError, match="'f'"):
                parse_document_ids(bad, "f")

    def test_parse_evaluation_run_id(self) -> None:
        """Integers or None pass; anything else is rejected."""
        assert parse_evaluation_run_id(7) == 7
        assert parse_evaluation_run_id(None) is None
        for bad in ("7", 7.0, True):
            with pytest.raises(ValueError):
                parse_evaluation_run_id(bad)


class TestLoadCheckpointFile:
    """Checkpoint file validation."""

    def test_missing_file(self, tmp_path: Path) -> None:
        """A missing file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_checkpoint_file(str(tmp_path / "nope.json"))

    @pytest.mark.parametrize("content, message", [
        ("{not json", "Invalid checkpoint file format"),
        ("[1, 2]", "expected a JSON object"),
        (json.dumps({"metadata": {}, "search_strategy": {}}), "final report file"),
        (json.dumps({"criteria": {}}), "missing 'checkpoint_type'"),
        (json.dumps({"checkpoint_type": "final_review"}), "Unknown checkpoint type"),
    ])
    def test_invalid_files(self, tmp_path: Path, content: str, message: str) -> None:
        """Each kind of invalid file gets a specific ValueError."""
        path = tmp_path / "cp.json"
        path.write_text(content)
        with pytest.raises(ValueError, match=message):
            load_checkpoint_file(str(path))


class TestReopenRun:
    """EvaluationStore.reopen_run reopens a run whatever its status."""

    def test_reopen_run_sql(self) -> None:
        """No status filter; completion time and error are cleared."""
        from bmlibrarian.evaluations.store import EvaluationStore

        cursor = MagicMock()
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cursor
        db = MagicMock()
        db.get_connection.return_value.__enter__.return_value = conn

        store = EvaluationStore.__new__(EvaluationStore)
        store.db = db
        store.reopen_run(42)

        sql, params = cursor.execute.call_args.args
        assert params == (42,)
        assert "status = 'in_progress'" in sql
        assert "completed_at = NULL" in sql
        assert "error_message = NULL" in sql
        assert "AND status" not in sql
        conn.commit.assert_called_once()
