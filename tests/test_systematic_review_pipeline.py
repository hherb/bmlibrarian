"""
Tests for the SystematicReviewAgent review pipeline and checkpoint resume.

Fresh runs (``run_review``) and resumes (``run_review_from_checkpoint``)
share one pipeline (``pipeline.py``). These tests drive the real agent with
an in-memory evaluation store and fake search/scoring/quality workers, and
resume from checkpoint files the agent itself wrote, to pin:

- a resume from any checkpoint reports what the uninterrupted run reports;
- evaluations already saved in the run are reused, never re-run;
- failed evaluations are never saved: their papers are flagged for manual
  review and a resume retries them;
- the configured search strategy (phased or standard) is used on resume;
- the quality-gate threshold decides final inclusion on every path;
- evaluation runs end completed / paused / failed, and resumes reopen them;
- a rejected checkpoint yields a result marked as aborted, not an empty
  finding;
- a resume that cannot restore its data fails loudly and leaves the agent
  unchanged.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, Iterator, List, Optional, Set, Tuple
from unittest.mock import MagicMock, create_autospec, patch

import pytest

from bmlibrarian.agents.systematic_review import (
    EVENT_REVIEW_WARNING,
    DatabaseConnectionError,
    EvaluationSaveError,
    LLMConnectionError,
    ResumeError,
    ScoringError,
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
    SystematicReviewResult,
)
from bmlibrarian.agents.systematic_review.documenter import (
    CHECKPOINT_INITIAL_RESULTS,
    CHECKPOINT_QUALITY_ASSESSMENT,
    CHECKPOINT_SCORING_COMPLETE,
    CHECKPOINT_SEARCH_STRATEGY,
)
from bmlibrarian.agents.systematic_review.executor import (
    SearchExecutor,
    build_paper_sources,
    collect_phase1_document_ids,
)
from bmlibrarian.agents.systematic_review.filters import InitialFilter
from bmlibrarian.agents.systematic_review.pipeline import (
    ASSESSMENT_FAILED_REASON,
    RESUME_STAGE_BY_CHECKPOINT,
    SCORING_FAILED_REASON,
    PipelineComponents,
    ReviewStage,
    abort_reason,
    average_relevance,
    find_unevaluated,
    flag_unassessed,
    flag_unscored,
    markdown_report_path,
)
from bmlibrarian.agents.systematic_review.quality import (
    QualityAssessor,
    assessment_error,
)
from bmlibrarian.agents.systematic_review.reporter import Reporter
from bmlibrarian.agents.systematic_review.resume_mixin import (
    load_checkpoint_file,
    parse_checkpoint,
    parse_document_ids,
    parse_evaluation_run_id,
    parse_rejected_entries,
)
from bmlibrarian.agents.systematic_review.scorer import CompositeScorer, RelevanceScorer
from bmlibrarian.evaluations import EvaluationType
from bmlibrarian.evaluations.store import (
    DocumentEvaluation,
    EvaluationRun,
    EvaluationStore,
)

RESEARCH_QUESTION = "Do statins reduce cardiovascular events?"
RELEVANCE_THRESHOLD = 2.5
QUALITY_THRESHOLD = 4.0

# Paper 4 is rejected by the initial filter; paper 3 scores below the
# relevance threshold; paper 2 passes relevance but fails the quality gate.
PAPER_IDS = [1, 2, 3, 4]
REJECTED_BY_FILTER = {4}
RELEVANCE = {1: 4.0, 2: 3.0, 3: 1.0}
QUALITY = {1: 8.0, 2: 2.0}

# Statistics that legitimately differ between runs of the same review
VOLATILE_STATISTICS = ("processing_time_seconds", "total_llm_calls", "total_tokens_used")

ALL_CHECKPOINTS = list(RESUME_STAGE_BY_CHECKPOINT)


# =============================================================================
# Fakes
# =============================================================================

class FakeEvaluationStore:
    """In-memory stand-in for EvaluationStore."""

    def __init__(self) -> None:
        """Create an empty store."""
        self.runs: Dict[int, EvaluationRun] = {}
        self.evaluations: List[DocumentEvaluation] = []
        self.fail_status_updates = False

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
        # Hand out a copy, as the real store does: the agent's object must
        # not see later database changes unless it is refreshed.
        return EvaluationRun(**run.__dict__)

    def get_run(self, run_id: int) -> Optional[EvaluationRun]:
        """Return a copy of a run by ID."""
        run = self.runs.get(run_id)
        return EvaluationRun(**run.__dict__) if run else None

    def reopen_run(self, run_id: int) -> Optional[EvaluationRun]:
        """Put a run back in progress; return it as it now is."""
        if run_id not in self.runs:
            return None
        self.runs[run_id].status = "in_progress"
        self.runs[run_id].error_message = None
        return self.get_run(run_id)

    def pause_run(self, run_id: int) -> None:
        """Pause a run."""
        self._check_status_update()
        self.runs[run_id].status = "paused"

    def complete_run(
        self, run_id: int, status: Any = None, error_message: Optional[str] = None,
    ) -> None:
        """Complete a run with a final status."""
        self._check_status_update()
        self.runs[run_id].status = status.value
        self.runs[run_id].error_message = error_message

    def _check_status_update(self) -> None:
        """Simulate a database failure on status updates when configured to."""
        if self.fail_status_updates:
            raise RuntimeError("database went away")

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


def make_executed_queries(plan: SearchPlan, found_ids: List[int]) -> List[ExecutedQuery]:
    """Semantic query finds papers 1-3, keyword query finds 3-4 (of ``found_ids``)."""
    sem, kw = plan.queries
    sem_ids = [i for i in (1, 2, 3) if i in found_ids]
    kw_ids = [i for i in (3, 4) if i in found_ids]
    return [
        ExecutedQuery(planned_query=sem, document_ids=sem_ids,
                      execution_time_seconds=0.1, actual_results=len(sem_ids)),
        ExecutedQuery(planned_query=kw, document_ids=kw_ids,
                      execution_time_seconds=0.1, actual_results=len(kw_ids)),
    ]


def make_scored(doc_id: int, score: float = 3.0) -> ScoredPaper:
    """A scored paper with an included screening decision."""
    return ScoredPaper(
        paper=make_paper(doc_id), relevance_score=score, relevance_rationale="",
        inclusion_decision=InclusionDecision.create_included(
            stage=ExclusionStage.RELEVANCE_SCORING, rationale="", criteria_matched=[],
        ),
    )


@dataclass
class FakeWorkers:
    """
    Fake pipeline workers that record what they were asked to do.

    The scorer and assessor honour the real batch contract: a failed
    evaluation is returned in ``failed_papers`` and never saved.
    """

    standard_searches: int = 0
    phased_searches: int = 0
    found_ids: List[int] = field(default_factory=lambda: list(PAPER_IDS))
    rejected_ids: Set[int] = field(default_factory=lambda: set(REJECTED_BY_FILTER))
    scored_ids: List[int] = field(default_factory=list)
    assessed_ids: List[int] = field(default_factory=list)
    relevance: Dict[int, float] = field(default_factory=lambda: dict(RELEVANCE))
    quality: Dict[int, float] = field(default_factory=lambda: dict(QUALITY))
    scoring_error: Optional[BaseException] = None
    fail_scoring_ids: Set[int] = field(default_factory=set)
    fail_assessment_ids: Set[int] = field(default_factory=set)
    query_feedback_calls: int = 0
    uncertain_ids: Set[int] = field(default_factory=set)

    # --- executor -----------------------------------------------------------

    def execute_plan(self, plan: SearchPlan) -> SimpleNamespace:
        """Standard search."""
        self.standard_searches += 1
        executed = make_executed_queries(plan, self.found_ids)
        return SimpleNamespace(
            executed_queries=executed,
            papers=[make_paper(i) for i in self.found_ids],
            paper_sources=build_paper_sources(executed),
            total_before_dedup=sum(len(q.document_ids) for q in executed),
            count=len(self.found_ids),
            deduplication_rate=0.2,
        )

    def execute_phased_plan(self, plan: SearchPlan, max_phase2_no_overlap: int = 10) -> SimpleNamespace:
        """Phased search."""
        self.phased_searches += 1
        executed = make_executed_queries(plan, self.found_ids)
        phase1 = collect_phase1_document_ids(executed)
        return SimpleNamespace(
            executed_queries=executed,
            all_papers=[make_paper(i) for i in self.found_ids],
            paper_sources=build_paper_sources(executed),
            phase1_document_ids=phase1,
            total_count=len(self.found_ids),
            phase1_count=len(phase1),
            phase2_new_count=len(self.found_ids) - len(phase1),
        )

    # --- initial filter -------------------------------------------------------

    def filter_batch(self, papers: List[PaperData]) -> SimpleNamespace:
        """Reject ``rejected_ids``."""
        return SimpleNamespace(
            passed=[p for p in papers if p.document_id not in self.rejected_ids],
            rejected=[(p, "Wrong study type") for p in papers if p.document_id in self.rejected_ids],
        )

    # --- relevance scorer -------------------------------------------------------

    def score_batch(
        self,
        papers: List[PaperData],
        evaluate_inclusion: bool,
        paper_sources: Dict[int, List[str]],
        save_callback: Callable[[ScoredPaper], Any],
    ) -> SimpleNamespace:
        """Score each paper from ``relevance`` and save it (failures are not saved)."""
        if self.scoring_error:
            raise self.scoring_error
        scored = []
        failed = []
        for paper in papers:
            self.scored_ids.append(paper.document_id)
            if paper.document_id in self.fail_scoring_ids:
                failed.append((paper, "LLM unavailable"))
                continue
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
            failed_papers=failed,
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
        """Assess each paper from ``quality`` and save it (failures are not saved)."""
        assessed = []
        failed = []
        for sp in papers:
            self.assessed_ids.append(sp.paper.document_id)
            if sp.paper.document_id in self.fail_assessment_ids:
                failed.append((sp, "LLM unavailable"))
                continue
            ap = AssessedPaper(
                scored_paper=sp,
                study_assessment={"study_design": "rct"},
                paper_weight={},
                composite_score=self.quality[sp.paper.document_id],
            )
            save_callback(ap)
            assessed.append(ap)
        return SimpleNamespace(assessed_papers=assessed, failed_papers=failed, assessment_statistics={})

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
    """Deterministic config: no synthesis or results cache, explicit thresholds."""
    return SystematicReviewConfig(
        relevance_threshold=RELEVANCE_THRESHOLD,
        quality_threshold=QUALITY_THRESHOLD,
        enable_evidence_synthesis=False,
        use_phased_search=use_phased_search,
        enable_query_feedback=True,
        use_results_cache=False,
    )


class EventRecorder:
    """Agent progress callback that records events."""

    def __init__(self) -> None:
        """Start with no events."""
        self.events: List[Tuple[str, str]] = []

    def __call__(self, event: str, data: str) -> None:
        """Record one event."""
        self.events.append((event, data))

    def of(self, event: str) -> List[str]:
        """Data of every recorded ``event``."""
        return [data for name, data in self.events if name == event]


def checked_against(real_class: type, fake: FakeWorkers) -> Any:
    """
    Wrap ``fake`` so every call is checked against ``real_class``'s signatures.

    The pipeline is driven through autospecced mocks that delegate to the
    fake, so a call the real worker would reject (renamed method, wrong
    keyword) fails the tests instead of only production.

    Args:
        real_class: The worker class the fake stands in for.
        fake: The fake implementation.

    Returns:
        An autospec of ``real_class`` delegating to ``fake``.
    """
    mock = create_autospec(real_class, instance=True)
    for name in dir(real_class):
        if not name.startswith("_") and callable(getattr(fake, name, None)):
            getattr(mock, name).side_effect = getattr(fake, name)
    return mock


def make_agent(
    store: FakeEvaluationStore,
    workers: FakeWorkers,
    config: Optional[SystematicReviewConfig] = None,
    callback: Optional[Callable[[str, str], None]] = None,
) -> SystematicReviewAgent:
    """A real agent wired to the fake store and workers."""

    def install_store(self: SystematicReviewAgent) -> None:
        """Replace the database-backed store with the fake one."""
        self._evaluation_store = store
        self._evaluation_run = None
        self._evaluator_id = 1

    with patch.object(SystematicReviewAgent, "_init_evaluation_store", install_store):
        agent = SystematicReviewAgent(
            db_manager=MagicMock(),
            config=config or make_config(),
            callback=callback,
            show_model_info=False,
        )

    def build_components() -> PipelineComponents:
        """The fake workers (signature-checked), plus a real reporter."""
        return PipelineComponents(
            initial_filter=checked_against(InitialFilter, workers),
            scorer=checked_against(RelevanceScorer, workers),
            quality_assessor=checked_against(QualityAssessor, workers),
            composite_scorer=checked_against(CompositeScorer, workers),
            reporter=Reporter(
                documenter=agent.documenter,
                criteria=agent._active_criteria(),
                weights=agent._active_weights(),
            ),
        )

    agent._build_pipeline_components = build_components  # type: ignore[method-assign]
    agent._build_search_executor = (  # type: ignore[method-assign]
        lambda: checked_against(SearchExecutor, workers)
    )
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
        """Every requested document exists."""
        return [paper_row(i) for i in sorted(ids)]

    with patch("bmlibrarian.agents.systematic_review.planner.Planner", return_value=planner), \
            patch("bmlibrarian.database.fetch_documents_by_ids", side_effect=fetch):
        yield


def find_checkpoint(tmp_path: Path, checkpoint_type: str) -> Path:
    """The single checkpoint file of ``checkpoint_type`` under ``tmp_path``."""
    files = list((tmp_path / "checkpoints").glob(f"*_{checkpoint_type}.json"))
    assert len(files) == 1
    return files[0]


def run_and_stop(
    tmp_path: Path,
    store: FakeEvaluationStore,
    checkpoint_type: str,
    config: Optional[SystematicReviewConfig] = None,
    workers: Optional[FakeWorkers] = None,
) -> Tuple[FakeWorkers, Path]:
    """Run a fresh review that is rejected at ``checkpoint_type``; return its checkpoint file."""
    workers = workers or FakeWorkers()
    agent = make_agent(store, workers, config)
    result = agent.run_review(
        make_criteria(),
        interactive=True,
        output_path=str(tmp_path / "review.json"),
        checkpoint_callback=stop_at(checkpoint_type),
    )
    assert result.aborted
    return workers, find_checkpoint(tmp_path, checkpoint_type)


def rewrite_checkpoint(checkpoint: Path, **changes: Any) -> None:
    """Edit fields of a checkpoint file (a key set to ``...`` is removed)."""
    data = json.loads(checkpoint.read_text())
    for key, value in changes.items():
        if value is ...:
            data.pop(key, None)
        else:
            data[key] = value
    checkpoint.write_text(json.dumps(data))


def included_ids(result: Any) -> List[int]:
    """Document IDs of the included papers of a result."""
    return [p["document_id"] for p in result.included_papers]


def uncertain_ids(result: Any) -> List[int]:
    """Document IDs of the papers flagged for manual review."""
    return sorted(p["document_id"] for p in result.uncertain_papers)


def summarize(result: SystematicReviewResult) -> Dict[str, Any]:
    """Everything a review reports, minus timing and token counts."""
    stats = result.statistics.to_dict()
    for key in VOLATILE_STATISTICS:
        stats.pop(key)
    return {
        "included": included_ids(result),
        "excluded": sorted(
            (p["document_id"], p["exclusion_stage"]) for p in result.excluded_papers
        ),
        "uncertain": uncertain_ids(result),
        "statistics": stats,
    }


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
        assert not result.aborted
        stats = result.statistics
        assert stats.total_considered == 4
        assert stats.passed_initial_filter == 3
        assert stats.passed_relevance_threshold == 2
        assert stats.passed_quality_gate == 1
        assert stats.final_excluded == 3
        assert sorted(workers.scored_ids) == [1, 2, 3]
        assert sorted(workers.assessed_ids) == [1, 2]
        assert store.runs[1].status == "completed"
        assert agent.evaluation_run is not None
        assert agent.evaluation_run.status == "completed"

    def test_checkpoints_are_passed_in_resume_map_order(self) -> None:
        """Each checkpoint comes just before the stage a resume from it starts at."""
        seen: List[str] = []

        def record(checkpoint_type: str, state: Dict) -> bool:
            """Approve every checkpoint, noting its type."""
            seen.append(checkpoint_type)
            return True

        make_agent(FakeEvaluationStore(), FakeWorkers()).run_review(
            make_criteria(), interactive=True, checkpoint_callback=record,
        )
        assert seen == ALL_CHECKPOINTS
        stages = [RESUME_STAGE_BY_CHECKPOINT[cp] for cp in seen]
        assert stages == sorted(stages) == list(ReviewStage)

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

    def test_search_finding_nothing_completes_with_an_empty_report(self) -> None:
        """Zero papers is a real (empty) finding, not an error or an abort."""
        store = FakeEvaluationStore()
        workers = FakeWorkers(found_ids=[])
        result = make_agent(store, workers).run_review(make_criteria(), interactive=False)
        assert not result.aborted
        assert result.statistics.total_considered == 0
        assert (workers.scored_ids, workers.assessed_ids) == ([], [])
        assert store.runs[1].status == "completed"

    def test_filter_rejecting_everything_reports_every_paper_excluded(self) -> None:
        """No paper reaches scoring; all are excluded at the initial filter."""
        workers = FakeWorkers(rejected_ids=set(PAPER_IDS))
        result = make_agent(FakeEvaluationStore(), workers).run_review(
            make_criteria(), interactive=False,
        )
        assert workers.scored_ids == []
        assert {p["exclusion_stage"] for p in result.excluded_papers} == {"initial_filter"}
        assert result.statistics.final_excluded == len(PAPER_IDS)
        assert result.statistics.passed_initial_filter == 0

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
        assert uncertain_ids(result) == [1]
        assert result.statistics.uncertain_for_review == 1

    def test_rejected_checkpoint_returns_an_aborted_result_and_pauses_the_run(self) -> None:
        """An aborted review says so (it is not an empty finding) and pauses its run."""
        store = FakeEvaluationStore()
        workers = FakeWorkers()
        result = make_agent(store, workers).run_review(
            make_criteria(), interactive=True,
            checkpoint_callback=stop_at(CHECKPOINT_SCORING_COMPLETE),
        )
        assert result.aborted
        assert result.abort_reason == abort_reason(CHECKPOINT_SCORING_COMPLETE)
        assert result.to_dict()["abort_reason"] == result.abort_reason
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

    @pytest.mark.parametrize("raised, expected", [
        (ConnectionError("db down"), DatabaseConnectionError),
        (TimeoutError("llm slow"), LLMConnectionError),
        (ValueError("bad value"), SystematicReviewError),
        (ScoringError("scorer broke"), ScoringError),
        (EvaluationSaveError("save broke"), EvaluationSaveError),
    ])
    def test_errors_are_mapped_and_fail_the_run(
        self, raised: Exception, expected: type,
    ) -> None:
        """Each error class surfaces as its SystematicReviewError type."""
        store = FakeEvaluationStore()
        with pytest.raises(SystematicReviewError) as excinfo:
            make_agent(store, FakeWorkers(scoring_error=raised)).run_review(
                make_criteria(), interactive=False,
            )
        assert type(excinfo.value) is expected
        assert store.runs[1].status == "failed"

    def test_keyboard_interrupt_pauses_the_run(self) -> None:
        """An interrupted review can be resumed: its run is paused, not failed."""
        store = FakeEvaluationStore()
        with pytest.raises(KeyboardInterrupt):
            make_agent(store, FakeWorkers(scoring_error=KeyboardInterrupt())).run_review(
                make_criteria(), interactive=False,
            )
        assert store.runs[1].status == "paused"

    def test_writes_json_and_markdown_reports(self, tmp_path: Path) -> None:
        """output_path produces both report files."""
        output = tmp_path / "review.json"
        make_agent(FakeEvaluationStore(), FakeWorkers()).run_review(
            make_criteria(), interactive=False, output_path=str(output),
        )
        assert output.exists()
        assert (tmp_path / "review.md").exists()

    def test_checkpoint_records_thresholds_and_baseline(self, tmp_path: Path) -> None:
        """A checkpoint carries what a resume needs beyond the papers."""
        store = FakeEvaluationStore()
        _, checkpoint = run_and_stop(
            tmp_path, store, CHECKPOINT_INITIAL_RESULTS, make_config(use_phased_search=True),
        )
        data = json.loads(checkpoint.read_text())
        assert data["relevance_threshold"] == RELEVANCE_THRESHOLD
        assert data["quality_threshold"] == QUALITY_THRESHOLD
        assert data["semantic_baseline_ids"] == [1, 2, 3]
        assert data["evaluation_run_id"] == 1


class TestFailedEvaluations:
    """Failed evaluations are flagged for review, never saved, and retried on resume."""

    def test_failed_scoring_is_flagged_for_review_with_a_warning(self) -> None:
        """A paper that could not be scored is in the uncertain list, not lost."""
        events = EventRecorder()
        store = FakeEvaluationStore()
        workers = FakeWorkers(fail_scoring_ids={2})
        result = make_agent(store, workers, callback=events).run_review(
            make_criteria(), interactive=False,
        )

        assert uncertain_ids(result) == [2]
        assert SCORING_FAILED_REASON in result.uncertain_papers[0]["rationale"]
        assert 2 not in store.get_evaluated_document_ids(1, EvaluationType.RELEVANCE_SCORE)
        warnings = events.of(EVENT_REVIEW_WARNING)
        assert len(warnings) == 1 and "could not be scored" in warnings[0]
        assert store.runs[1].status == "completed"

    def test_resume_retries_papers_whose_scoring_failed(self, tmp_path: Path) -> None:
        """Nothing was saved for the failed paper, so a resume scores it again."""
        store = FakeEvaluationStore()
        workers = FakeWorkers(fail_scoring_ids={2})
        make_agent(store, workers).run_review(
            make_criteria(), interactive=True, output_path=str(tmp_path / "review.json"),
        )
        checkpoint = find_checkpoint(tmp_path, CHECKPOINT_INITIAL_RESULTS)

        retry = FakeWorkers()
        result = make_agent(store, retry).run_review_from_checkpoint(
            str(checkpoint), interactive=False,
        )
        assert retry.scored_ids == [2]
        assert uncertain_ids(result) == []
        assert included_ids(result) == [1]

    def test_failed_assessment_is_flagged_and_retried_on_resume(self, tmp_path: Path) -> None:
        """A relevant paper that could not be assessed is flagged; a late resume retries it."""
        events = EventRecorder()
        store = FakeEvaluationStore()
        workers = FakeWorkers(fail_assessment_ids={1})
        result = make_agent(store, workers, callback=events).run_review(
            make_criteria(), interactive=True, output_path=str(tmp_path / "review.json"),
        )
        assert included_ids(result) == []
        assert uncertain_ids(result) == [1]
        assert ASSESSMENT_FAILED_REASON in result.uncertain_papers[0]["rationale"]
        assert any("could not be quality-assessed" in w for w in events.of(EVENT_REVIEW_WARNING))

        retry = FakeWorkers()
        resumed = make_agent(store, retry).run_review_from_checkpoint(
            str(find_checkpoint(tmp_path, CHECKPOINT_QUALITY_ASSESSMENT)), interactive=False,
        )
        assert retry.assessed_ids == [1]
        assert included_ids(resumed) == [1]
        assert uncertain_ids(resumed) == []


# =============================================================================
# Resume
# =============================================================================

class TestResume:
    """run_review_from_checkpoint, from checkpoint files the agent wrote."""

    @pytest.mark.parametrize("checkpoint_type", ALL_CHECKPOINTS)
    @pytest.mark.parametrize("use_phased_search", [False, True])
    def test_resume_reports_what_an_uninterrupted_run_reports(
        self, tmp_path: Path, checkpoint_type: str, use_phased_search: bool,
    ) -> None:
        """Every list and count of a resumed review matches the uninterrupted one."""
        config = make_config(use_phased_search=use_phased_search)
        expected = make_agent(
            FakeEvaluationStore(), FakeWorkers(uncertain_ids={1}), config,
        ).run_review(make_criteria(), interactive=False)

        store = FakeEvaluationStore()
        run_and_stop(tmp_path, store, checkpoint_type, config, FakeWorkers(uncertain_ids={1}))
        resumed = make_agent(store, FakeWorkers(uncertain_ids={1}), config).run_review_from_checkpoint(
            str(find_checkpoint(tmp_path, checkpoint_type)), interactive=False,
        )

        assert summarize(resumed) == summarize(expected)

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
        first, _ = run_and_stop(tmp_path, store, CHECKPOINT_QUALITY_ASSESSMENT)
        assert sorted(first.assessed_ids) == [1, 2]
        # Pretend the run died after scoring with paper 1 already assessed.
        store.evaluations = [
            e for e in store.evaluations
            if not (e.evaluation_type == EvaluationType.QUALITY_ASSESSMENT.value and e.document_id == 2)
        ]
        scoring_checkpoint = find_checkpoint(tmp_path, CHECKPOINT_SCORING_COMPLETE)

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

    @pytest.mark.parametrize("use_phased_search", [False, True])
    def test_resume_from_search_strategy_uses_the_configured_search(
        self, tmp_path: Path, use_phased_search: bool,
    ) -> None:
        """Resume runs the search the configuration asks for, phased or standard."""
        config = make_config(use_phased_search=use_phased_search)
        store = FakeEvaluationStore()
        _, checkpoint = run_and_stop(tmp_path, store, CHECKPOINT_SEARCH_STRATEGY, config)

        workers = FakeWorkers()
        result = make_agent(store, workers, config).run_review_from_checkpoint(
            str(checkpoint), interactive=False,
        )

        expected = (0, 1) if use_phased_search else (1, 0)
        assert (workers.standard_searches, workers.phased_searches) == expected
        assert workers.query_feedback_calls == (1 if use_phased_search else 0)
        assert included_ids(result) == [1]

    def test_resume_restores_provenance_and_baseline(self, tmp_path: Path) -> None:
        """Paper sources come from executed queries; the baseline from the checkpoint."""
        config = make_config(use_phased_search=True)
        store = FakeEvaluationStore()
        _, checkpoint = run_and_stop(tmp_path, store, CHECKPOINT_INITIAL_RESULTS, config)

        workers = FakeWorkers()
        agent = make_agent(store, workers, config)
        agent.run_review_from_checkpoint(str(checkpoint), interactive=False)

        assert agent._paper_sources[3] == ["q-sem", "q-kw"]
        assert agent._semantic_baseline_ids == {1, 2, 3}
        assert workers.query_feedback_calls == 1

    def test_recorded_baseline_wins_over_current_search_mode(self, tmp_path: Path) -> None:
        """A standard search's (empty) baseline is kept even if phased search is on now."""
        store = FakeEvaluationStore()
        _, checkpoint = run_and_stop(tmp_path, store, CHECKPOINT_INITIAL_RESULTS)

        agent = make_agent(store, FakeWorkers(), make_config(use_phased_search=True))
        agent.run_review_from_checkpoint(str(checkpoint), interactive=False)
        assert agent._semantic_baseline_ids == set()

    def test_legacy_checkpoint_derives_the_baseline(self, tmp_path: Path) -> None:
        """Checkpoints without a recorded baseline fall back to deriving it."""
        config = make_config(use_phased_search=True)
        store = FakeEvaluationStore()
        _, checkpoint = run_and_stop(tmp_path, store, CHECKPOINT_INITIAL_RESULTS, config)
        rewrite_checkpoint(checkpoint, semantic_baseline_ids=...)

        agent = make_agent(store, FakeWorkers(), config)
        agent.run_review_from_checkpoint(str(checkpoint), interactive=False)
        assert agent._semantic_baseline_ids == {1, 2, 3}

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
        store.runs[1].error_message = "earlier crash"

        agent = make_agent(store, FakeWorkers())
        agent.run_review_from_checkpoint(str(checkpoint), interactive=False)
        assert store.runs[1].status == "completed"
        # The agent's run object reflects the database, not the pre-reopen copy
        assert agent.evaluation_run is not None
        assert agent.evaluation_run.status == "completed"
        assert agent.evaluation_run.error_message is None

    def test_failure_during_resume_fails_the_reopened_run(self, tmp_path: Path) -> None:
        """Errors once the resumed pipeline runs are recorded on the run."""
        store = FakeEvaluationStore()
        _, checkpoint = run_and_stop(tmp_path, store, CHECKPOINT_INITIAL_RESULTS)
        with pytest.raises(SystematicReviewError, match="LLM exploded"):
            make_agent(store, FakeWorkers(scoring_error=RuntimeError("LLM exploded"))) \
                .run_review_from_checkpoint(str(checkpoint), interactive=False)
        assert store.runs[1].status == "failed"

    def test_chained_resume(self, tmp_path: Path) -> None:
        """A resume rejected at a later checkpoint can itself be resumed."""
        store = FakeEvaluationStore()
        run_and_stop(tmp_path, store, CHECKPOINT_INITIAL_RESULTS)
        first_checkpoint = find_checkpoint(tmp_path, CHECKPOINT_INITIAL_RESULTS)

        aborted = make_agent(store, FakeWorkers()).run_review_from_checkpoint(
            str(first_checkpoint), interactive=True,
            output_path=str(tmp_path / "review.json"),
            checkpoint_callback=stop_at(CHECKPOINT_SCORING_COMPLETE),
        )
        assert aborted.aborted
        assert store.runs[1].status == "paused"

        second_checkpoint = find_checkpoint(tmp_path, CHECKPOINT_SCORING_COMPLETE)
        first, second = (json.loads(p.read_text()) for p in (first_checkpoint, second_checkpoint))
        assert second["review_id"] == first["review_id"]
        assert second["evaluation_run_id"] == 1
        # Filtering ran during the first resume; its rejections are carried on
        assert first["rejected_initial_filter"] == []
        assert second["rejected_initial_filter"] == [
            {"document_id": 4, "reason": "Wrong study type"},
        ]

        workers = FakeWorkers()
        result = make_agent(store, workers).run_review_from_checkpoint(
            str(second_checkpoint), interactive=False,
        )
        assert workers.scored_ids == []
        assert included_ids(result) == [1]
        assert store.runs[1].status == "completed"

    def test_resume_does_not_keep_state_from_a_previous_review(self, tmp_path: Path) -> None:
        """Restoring replaces all state on a reused agent instance."""
        store = FakeEvaluationStore()
        _, checkpoint = run_and_stop(tmp_path, store, CHECKPOINT_SCORING_COMPLETE)

        agent = make_agent(store, FakeWorkers())
        agent._rejected_initial_filter = [(make_paper(99), "stale")]
        agent.run_review_from_checkpoint(str(checkpoint), interactive=False)

        assert [p.document_id for p, _ in agent._rejected_initial_filter] == [4]

    def test_missing_weights_fall_back_to_configured_weights(self, tmp_path: Path) -> None:
        """A checkpoint without weights resumes with the configured ones."""
        store = FakeEvaluationStore()
        _, checkpoint = run_and_stop(tmp_path, store, CHECKPOINT_SCORING_COMPLETE)
        rewrite_checkpoint(checkpoint, weights=None)

        config = make_config()
        agent = make_agent(store, FakeWorkers(), config)
        agent.run_review_from_checkpoint(str(checkpoint), interactive=False)
        assert agent.weights == config.scoring_weights

    def test_restored_progress_is_reported(self, tmp_path: Path) -> None:
        """The UI is told what was done before the checkpoint."""
        store = FakeEvaluationStore()
        _, checkpoint = run_and_stop(tmp_path, store, CHECKPOINT_QUALITY_ASSESSMENT)

        events = EventRecorder()
        make_agent(store, FakeWorkers(), callback=events).run_review_from_checkpoint(
            str(checkpoint), interactive=False,
        )
        restored = [name for name, data in events.events if data.startswith("[RESTORED]")]
        assert restored == [
            "execution_completed", "filtering_complete", "scoring_complete",
            "scoring_progress", "quality_complete", "quality_progress",
        ]
        assert events.of("scoring_progress")[0] == "[RESTORED] 3/3"

    def test_papers_missing_from_the_database_are_reported(self, tmp_path: Path) -> None:
        """Papers that cannot be restored are named in a warning, not silently dropped."""
        store = FakeEvaluationStore()
        _, checkpoint = run_and_stop(tmp_path, store, CHECKPOINT_INITIAL_RESULTS)

        def fetch_without_3(ids: Set[int]) -> List[Dict[str, Any]]:
            """Document 3 was deleted."""
            return [paper_row(i) for i in sorted(ids) if i != 3]

        events = EventRecorder()
        with patch("bmlibrarian.database.fetch_documents_by_ids", side_effect=fetch_without_3):
            result = make_agent(store, FakeWorkers(), callback=events).run_review_from_checkpoint(
                str(checkpoint), interactive=False,
            )
        warnings = events.of(EVENT_REVIEW_WARNING)
        assert len(warnings) == 1 and "[3]" in warnings[0]
        assert result.statistics.total_considered == 3

    def test_missing_run_id_at_an_early_checkpoint_starts_a_new_run(self, tmp_path: Path) -> None:
        """Nothing needs to be reused, so a fresh run is fine (with a warning)."""
        store = FakeEvaluationStore()
        _, checkpoint = run_and_stop(tmp_path, store, CHECKPOINT_INITIAL_RESULTS)
        rewrite_checkpoint(checkpoint, evaluation_run_id=None)

        events = EventRecorder()
        result = make_agent(store, FakeWorkers(), callback=events).run_review_from_checkpoint(
            str(checkpoint), interactive=False,
        )
        assert included_ids(result) == [1]
        assert store.runs[2].status == "completed"
        assert any("new evaluation run" in w for w in events.of(EVENT_REVIEW_WARNING))


class TestResumeFailsLoudly:
    """A resume that cannot restore its data must fail, and leave the agent as it was."""

    def test_missing_run_id_at_a_late_checkpoint_raises(self, tmp_path: Path) -> None:
        """Scores live in the run: without it, a late resume cannot continue."""
        store = FakeEvaluationStore()
        _, checkpoint = run_and_stop(tmp_path, store, CHECKPOINT_SCORING_COMPLETE)
        rewrite_checkpoint(checkpoint, evaluation_run_id=None)
        with pytest.raises(ResumeError, match="no evaluation run"):
            make_agent(store, FakeWorkers()).run_review_from_checkpoint(str(checkpoint))

    def test_unknown_run_id_raises(self, tmp_path: Path) -> None:
        """A run ID absent from the database (wrong database?) raises."""
        store = FakeEvaluationStore()
        _, checkpoint = run_and_stop(tmp_path, store, CHECKPOINT_SCORING_COMPLETE)
        rewrite_checkpoint(checkpoint, evaluation_run_id=999)
        with pytest.raises(ResumeError, match="999"):
            make_agent(store, FakeWorkers()).run_review_from_checkpoint(str(checkpoint))

    def test_run_of_another_question_raises(self, tmp_path: Path) -> None:
        """A run ID pointing at a different review raises."""
        store = FakeEvaluationStore()
        _, checkpoint = run_and_stop(tmp_path, store, CHECKPOINT_SCORING_COMPLETE)
        store.runs[1].research_question_text = "Something else entirely?"
        with pytest.raises(ResumeError, match="different research question"):
            make_agent(store, FakeWorkers()).run_review_from_checkpoint(str(checkpoint))

    def test_run_deleted_before_reopen_raises(self, tmp_path: Path) -> None:
        """A run that vanishes between lookup and reopen is reported."""
        store = FakeEvaluationStore()
        _, checkpoint = run_and_stop(tmp_path, store, CHECKPOINT_SCORING_COMPLETE)
        store.reopen_run = lambda run_id: None  # type: ignore[method-assign]
        with pytest.raises(ResumeError, match="deleted"):
            make_agent(store, FakeWorkers()).run_review_from_checkpoint(str(checkpoint))

    def test_no_paper_restorable_raises(self, tmp_path: Path) -> None:
        """A checkpoint none of whose papers exist (wrong database?) raises."""
        store = FakeEvaluationStore()
        _, checkpoint = run_and_stop(tmp_path, store, CHECKPOINT_INITIAL_RESULTS)
        with patch("bmlibrarian.database.fetch_documents_by_ids", return_value=[]), \
                pytest.raises(ResumeError, match="None of the 4 papers"):
            make_agent(store, FakeWorkers()).run_review_from_checkpoint(str(checkpoint))

    @pytest.mark.parametrize("checkpoint_type, changes, message", [
        (CHECKPOINT_SCORING_COMPLETE, {"evaluation_run_id": "1; DROP TABLE"}, "evaluation_run_id"),
        (CHECKPOINT_SCORING_COMPLETE, {"criteria": ...}, "missing required 'criteria'"),
        (CHECKPOINT_SCORING_COMPLETE, {"criteria": {"research_question": "q?"}}, "malformed 'criteria'"),
        (CHECKPOINT_SCORING_COMPLETE, {"criteria": "not a dict"}, "missing required 'criteria'"),
        (CHECKPOINT_SCORING_COMPLETE, {"weights": {"relevance": -5.0}}, "'weights'"),
        (CHECKPOINT_SEARCH_STRATEGY, {"search_plan": None}, "no 'search_plan'"),
        (CHECKPOINT_SCORING_COMPLETE, {"executed_queries": [{"nope": 1}]}, "malformed 'executed_queries'"),
        (CHECKPOINT_SCORING_COMPLETE, {"rejected_initial_filter": ["x"]}, "rejected_initial_filter"),
        (CHECKPOINT_SCORING_COMPLETE, {"rejected_initial_filter": [{"document_id": "4"}]},
         "rejected_initial_filter"),
        (CHECKPOINT_SCORING_COMPLETE, {"paper_document_ids": "1,2"}, "paper_document_ids"),
        (CHECKPOINT_SCORING_COMPLETE, {"review_id": 42}, "review_id"),
    ])
    def test_malformed_checkpoint_raises_value_error(
        self, tmp_path: Path, checkpoint_type: str, changes: Dict[str, Any], message: str,
    ) -> None:
        """Untrusted file data is validated; bad data is a ValueError naming the field."""
        store = FakeEvaluationStore()
        _, checkpoint = run_and_stop(tmp_path, store, checkpoint_type)
        rewrite_checkpoint(checkpoint, **changes)
        with pytest.raises(ValueError, match=message):
            make_agent(store, FakeWorkers()).run_review_from_checkpoint(str(checkpoint))

    def test_failed_resume_leaves_the_agent_unchanged(self, tmp_path: Path) -> None:
        """A resume rejected during setup does not half-restore the agent."""
        store = FakeEvaluationStore()
        _, checkpoint = run_and_stop(tmp_path / "old", store, CHECKPOINT_SCORING_COMPLETE)
        rewrite_checkpoint(checkpoint, evaluation_run_id=999)

        agent = make_agent(store, FakeWorkers())
        agent.run_review(make_criteria("Does aspirin prevent strokes?"), interactive=False)
        before = (agent.criteria, agent.weights, agent.documenter, agent.evaluation_run,
                  list(agent._all_papers))

        with pytest.raises(ResumeError):
            agent.run_review_from_checkpoint(str(checkpoint))

        after = (agent.criteria, agent.weights, agent.documenter, agent.evaluation_run,
                 list(agent._all_papers))
        assert after == before


class TestRunStatusBookkeeping:
    """Run status updates that fail, and reset()."""

    def test_status_update_failure_is_reported_but_not_fatal(self) -> None:
        """The review result survives; the user is told the run status is stale."""
        events = EventRecorder()
        store = FakeEvaluationStore()
        agent = make_agent(store, FakeWorkers(), callback=events)
        store.fail_status_updates = True

        result = agent.run_review(make_criteria(), interactive=False)

        assert included_ids(result) == [1]
        warnings = events.of(EVENT_REVIEW_WARNING)
        assert len(warnings) == 1 and "could not be marked completed" in warnings[0]
        assert store.runs[1].status == "in_progress"

    def test_reset_keeps_a_completed_run_completed(self) -> None:
        """Resetting after a finished review must not mark its run failed."""
        store = FakeEvaluationStore()
        agent = make_agent(store, FakeWorkers())
        agent.run_review(make_criteria(), interactive=False)
        agent.reset()
        assert store.runs[1].status == "completed"
        assert agent.evaluation_run is None

    def test_reset_keeps_a_paused_run_resumable(self) -> None:
        """A paused run stays paused (it can be resumed from its checkpoint)."""
        store = FakeEvaluationStore()
        agent = make_agent(store, FakeWorkers())
        agent.run_review(
            make_criteria(), interactive=True,
            checkpoint_callback=stop_at(CHECKPOINT_INITIAL_RESULTS),
        )
        agent.reset()
        assert store.runs[1].status == "paused"

    def test_reset_fails_an_abandoned_run(self) -> None:
        """A run still in progress when the agent is reset is marked failed."""
        store = FakeEvaluationStore()
        agent = make_agent(store, FakeWorkers())
        agent._criteria = make_criteria()
        agent._start_evaluation_run()
        agent.reset()
        assert store.runs[1].status == "failed"


class TestEvidenceSynthesis:
    """Optional synthesis never fails the review."""

    def test_synthesis_failure_is_reported_and_the_review_completes(self) -> None:
        """A synthesis error leaves the review without a synthesis, and says so."""
        config = make_config()
        config.enable_evidence_synthesis = True
        events = EventRecorder()
        store = FakeEvaluationStore()
        synthesizer = MagicMock()
        synthesizer.synthesize.side_effect = RuntimeError("synthesis LLM down")

        with patch(
            "bmlibrarian.agents.systematic_review.synthesizer.EvidenceSynthesizer",
            return_value=synthesizer,
        ):
            result = make_agent(store, FakeWorkers(), config, callback=events).run_review(
                make_criteria(), interactive=False,
            )

        assert included_ids(result) == [1]
        assert result.evidence_synthesis is None
        assert events.of("synthesis_failed") == ["Evidence synthesis failed: synthesis LLM down"]
        assert store.runs[1].status == "completed"


class TestComponentWiring:
    """The real worker construction (the other tests replace it with fakes)."""

    def test_build_pipeline_components_constructs_the_real_workers(self) -> None:
        """Every worker is built with arguments its constructor accepts."""
        agent = make_agent(FakeEvaluationStore(), FakeWorkers())
        agent._criteria = make_criteria()
        agent._weights = agent.config.scoring_weights

        components = SystematicReviewAgent._build_pipeline_components(agent)

        assert isinstance(components.initial_filter, InitialFilter)
        assert isinstance(components.scorer, RelevanceScorer)
        assert isinstance(components.quality_assessor, QualityAssessor)
        assert isinstance(components.composite_scorer, CompositeScorer)
        assert isinstance(components.reporter, Reporter)

    def test_search_executor_uses_the_agent_database(self) -> None:
        """Search runs against the agent's database, not the default one."""
        agent = make_agent(FakeEvaluationStore(), FakeWorkers())
        executor = SystematicReviewAgent._build_search_executor(agent)
        assert isinstance(executor, SearchExecutor)
        assert executor._db_manager is agent._db_manager


# =============================================================================
# Batch workers: failed evaluations are never saved
# =============================================================================

class TestRelevanceScorerBatch:
    """RelevanceScorer.score_batch with a save callback."""

    def _scorer(self, outcomes: List[Any]) -> RelevanceScorer:
        """A scorer whose LLM returns (or raises) ``outcomes`` in turn."""
        llm = MagicMock()
        llm.evaluate_document.side_effect = outcomes
        scorer = RelevanceScorer(research_question=RESEARCH_QUESTION, config=make_config())
        scorer._get_scoring_agent = lambda: llm  # type: ignore[method-assign]
        return scorer

    def test_failed_scores_are_not_saved(self) -> None:
        """A scoring error is listed as failed and never reaches the store."""
        scorer = self._scorer([
            {"score": 4, "reasoning": "relevant"},
            RuntimeError("LLM down"),
            {"score": 2, "reasoning": "marginal"},
        ])
        saved: List[int] = []
        result = scorer.score_batch(
            [make_paper(1), make_paper(2), make_paper(3)],
            evaluate_inclusion=False,
            save_callback=lambda sp: saved.append(sp.paper.document_id),
        )
        assert saved == [1, 3]
        assert [p.document_id for p, _ in result.failed_papers] == [2]
        assert "LLM down" in result.failed_papers[0][1]

    def test_save_failure_stops_the_batch(self) -> None:
        """An unsaved score would drop its paper: the batch raises instead."""
        scorer = self._scorer([{"score": 4, "reasoning": "relevant"}] * 2)

        def broken_save(scored_paper: ScoredPaper) -> None:
            """The database rejects the write."""
            raise RuntimeError("disk full")

        with pytest.raises(EvaluationSaveError, match="disk full"):
            scorer.score_batch(
                [make_paper(1), make_paper(2)], evaluate_inclusion=False,
                save_callback=broken_save,
            )

    def test_score_paper_still_returns_an_uncertain_placeholder(self) -> None:
        """The single-paper API keeps its never-raise contract."""
        scorer = self._scorer([RuntimeError("LLM down")])
        scored = scorer.score_paper(make_paper(1), evaluate_inclusion=False)
        assert scored.relevance_score == 0.0
        assert scored.inclusion_decision.status == InclusionStatus.UNCERTAIN


class TestQualityAssessorBatch:
    """QualityAssessor.assess_batch with a save callback."""

    def _assessor(self, assessments: List[AssessedPaper]) -> QualityAssessor:
        """An assessor whose single-paper assessment returns ``assessments`` in turn."""
        assessor = QualityAssessor(config=make_config())
        assessor._assess_single = MagicMock(side_effect=assessments)  # type: ignore[method-assign]
        return assessor

    def test_placeholder_assessments_are_not_saved(self) -> None:
        """A runner's error placeholder is a failure, not a mid-range score."""
        good = AssessedPaper(
            scored_paper=make_scored(1), study_assessment={"quality_score": 8.0},
            paper_weight={"composite_score": 7.0},
        )
        placeholder = AssessedPaper(
            scored_paper=make_scored(2),
            study_assessment={"quality_score": 5.0, "error": "LLM down"},
            paper_weight={"composite_score": 7.0},
        )
        saved: List[int] = []
        result = self._assessor([good, placeholder]).assess_batch(
            [make_scored(1), make_scored(2)],
            save_callback=lambda ap: saved.append(ap.scored_paper.paper.document_id),
        )
        assert saved == [1]
        assert [sp.paper.document_id for sp, _ in result.failed_papers] == [2]
        assert "study assessment: LLM down" in result.failed_papers[0][1]

    def test_save_failure_stops_the_batch(self) -> None:
        """An unsaved assessment would drop its paper: the batch raises instead."""
        good = AssessedPaper(
            scored_paper=make_scored(1), study_assessment={}, paper_weight={},
        )

        def broken_save(assessed_paper: AssessedPaper) -> None:
            """The database rejects the write."""
            raise RuntimeError("disk full")

        with pytest.raises(EvaluationSaveError, match="disk full"):
            self._assessor([good]).assess_batch([make_scored(1)], save_callback=broken_save)


# =============================================================================
# Pure helpers
# =============================================================================

class TestHelpers:
    """Pure functions used by the pipeline and resume."""

    def test_build_paper_sources_keeps_execution_order(self) -> None:
        """Each document lists the queries that found it, in order."""
        sources = build_paper_sources(make_executed_queries(make_plan(), PAPER_IDS))
        assert sources == {1: ["q-sem"], 2: ["q-sem"], 3: ["q-sem", "q-kw"], 4: ["q-kw"]}

    def test_phase1_ids_come_from_semantic_queries_only(self) -> None:
        """Keyword results are not part of the semantic baseline."""
        executed = make_executed_queries(make_plan(), PAPER_IDS)
        assert collect_phase1_document_ids(executed) == {1, 2, 3}

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
        papers = [make_scored(1, 2.0), make_scored(2, 4.0)]
        assert average_relevance(papers) == 3.0
        assert average_relevance([]) == 0.0

    def test_abort_reason_names_the_checkpoint(self) -> None:
        """The reason is readable and says where the review stopped."""
        assert abort_reason(CHECKPOINT_SCORING_COMPLETE) == (
            "Review stopped at the scoring complete checkpoint"
        )

    def test_find_unevaluated(self) -> None:
        """Unscored = passed the filter but no score; unassessed = above but no assessment."""
        above = [make_scored(1), make_scored(2)]
        unscored, unassessed = find_unevaluated(
            all_papers=[make_paper(i) for i in PAPER_IDS],
            rejected_ids={4},
            scored_ids={1, 2},
            above_threshold=above,
            assessed_ids={1},
        )
        assert [p.document_id for p in unscored] == [3]
        assert [sp.paper.document_id for sp in unassessed] == [2]

    def test_flags_mark_papers_uncertain(self) -> None:
        """Flagged papers need manual review, at the stage that failed."""
        unscored = flag_unscored(make_paper(1))
        assert unscored.inclusion_decision.status == InclusionStatus.UNCERTAIN
        assert unscored.inclusion_decision.reasons == [SCORING_FAILED_REASON]

        original = make_scored(2, 4.0)
        unassessed = flag_unassessed(original)
        assert unassessed.relevance_score == 4.0
        assert unassessed.inclusion_decision.stage == ExclusionStage.QUALITY_GATE
        assert unassessed.inclusion_decision.reasons == [ASSESSMENT_FAILED_REASON]
        assert original.inclusion_decision.status == InclusionStatus.INCLUDED

    def test_assessment_error(self) -> None:
        """Error placeholders from either required runner are detected."""
        def assessed(study: Dict[str, Any], weight: Dict[str, Any]) -> AssessedPaper:
            """An assessment with the given parts."""
            return AssessedPaper(scored_paper=make_scored(1), study_assessment=study, paper_weight=weight)

        assert assessment_error(assessed({"quality_score": 8}, {"composite_score": 7})) is None
        assert assessment_error(assessed({"error": "a"}, {})) == "study assessment: a"
        assert assessment_error(assessed({"error": "a"}, {"error": "b"})) == (
            "study assessment: a; paper weight: b"
        )

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

    def test_parse_rejected_entries(self) -> None:
        """Entries need an integer ID; a missing reason gets a placeholder."""
        assert parse_rejected_entries(None) == ()
        assert parse_rejected_entries([{"document_id": 4, "reason": "animal"}, {"document_id": 5}]) == (
            (4, "animal"), (5, "Unknown reason"),
        )
        for bad in ({"document_id": 4}, [4], [{"document_id": None}]):
            with pytest.raises(ValueError, match="rejected_initial_filter"):
                parse_rejected_entries(bad)

    def test_parse_checkpoint_maps_the_stage(self, tmp_path: Path) -> None:
        """Each checkpoint type resumes at its mapped stage."""
        store = FakeEvaluationStore()
        _, checkpoint = run_and_stop(tmp_path, store, CHECKPOINT_SCORING_COMPLETE)
        parsed = parse_checkpoint(load_checkpoint_file(str(checkpoint)))
        assert parsed.stage == ReviewStage.ASSESS_QUALITY
        assert parsed.paper_ids == tuple(PAPER_IDS)
        assert parsed.rejected == ((4, "Wrong study type"),)
        assert parsed.evaluation_run_id == 1


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


# =============================================================================
# EvaluationStore.reopen_run (SQL layer, mocked connection)
# =============================================================================

RUN_ROW = (
    42, "systematic_review", None, RESEARCH_QUESTION, 1, "in_progress", None,
    10, 5, datetime(2026, 10, 16), None, None,
)


def make_store(cursor: MagicMock) -> EvaluationStore:
    """An EvaluationStore whose connection yields ``cursor``."""
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    db = MagicMock()
    db.get_connection.return_value.__enter__.return_value = conn
    store = EvaluationStore.__new__(EvaluationStore)
    store.db = db
    return store


class TestReopenRun:
    """EvaluationStore.reopen_run reopens a run whatever its status."""

    def test_reopen_returns_the_run_as_it_now_is(self) -> None:
        """The refreshed row is returned, so callers never hold the pre-reopen status."""
        cursor = MagicMock()
        cursor.fetchone.return_value = RUN_ROW
        run = make_store(cursor).reopen_run(42)

        assert run is not None
        assert (run.run_id, run.status, run.completed_at, run.error_message) == (
            42, "in_progress", None, None,
        )
        sql, params = cursor.execute.call_args.args
        assert params == (42,)
        assert "status = 'in_progress'" in sql
        assert "AND status" not in sql  # any status is reopened
        assert "RETURNING" in sql

    def test_unknown_run_returns_none(self) -> None:
        """No row updated means no such run."""
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        assert make_store(cursor).reopen_run(42) is None

    def test_database_error_is_wrapped(self) -> None:
        """Like its sibling methods, a database error becomes RuntimeError."""
        cursor = MagicMock()
        cursor.execute.side_effect = Exception("connection reset")
        with pytest.raises(RuntimeError, match="reopening run"):
            make_store(cursor).reopen_run(42)


# =============================================================================
# CLI resume
# =============================================================================

class TestCliResume:
    """systematic_review_cli.resume_review and its helpers."""

    def test_resolve_threshold(self) -> None:
        """Flag, else a finite recorded number, else the configured value."""
        from systematic_review_cli import resolve_threshold

        assert resolve_threshold(4.0, 3.5, 2.5) == 4.0
        assert resolve_threshold(None, 3.5, 2.5) == 3.5
        for recorded in (None, "3.5", True, float("nan"), float("inf")):
            assert resolve_threshold(None, recorded, 2.5) == 2.5

    def _resume(
        self, tmp_path: Path, result: SystematicReviewResult, **flags: Any,
    ) -> Tuple[int, MagicMock]:
        """Run resume_review on a real checkpoint with a mocked agent."""
        import systematic_review_cli as cli

        _, checkpoint = run_and_stop(tmp_path / "run", FakeEvaluationStore(), CHECKPOINT_SCORING_COMPLETE)
        rewrite_checkpoint(checkpoint, relevance_threshold=3.5)
        out = tmp_path / "out"
        args = argparse.Namespace(
            resume=str(checkpoint), auto=True, output_dir=str(out),
            relevance_threshold=flags.get("relevance_threshold"),
            quality_threshold=flags.get("quality_threshold"),
        )
        agent_class = MagicMock()
        agent_class.return_value.run_review_from_checkpoint.return_value = result
        with patch.object(cli, "SystematicReviewAgent", agent_class), \
                patch.object(cli, "get_db_manager"), \
                patch.object(cli, "get_systematic_review_config", return_value=make_config()):
            code = cli.resume_review(args)
        return code, agent_class

    def _aborted_result(self) -> SystematicReviewResult:
        """An aborted result as the agent returns it."""
        return SystematicReviewResult(
            metadata={}, search_strategy={}, scoring_config={}, included_papers=[],
            excluded_papers=[], uncertain_papers=[], process_log=[],
            statistics=MagicMock(), abort_reason=abort_reason(CHECKPOINT_QUALITY_ASSESSMENT),
        )

    def test_aborted_resume_writes_no_report(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """A rejected checkpoint is reported as stopped, with no empty reports written."""
        code, _ = self._resume(tmp_path, self._aborted_result())
        assert code == 0
        assert "REVIEW STOPPED" in capsys.readouterr().out
        assert not list((tmp_path / "out").glob("*_prisma.json"))

    def test_thresholds_default_to_the_checkpoint_and_flags_override(self, tmp_path: Path) -> None:
        """Without flags the checkpoint's thresholds apply; a flag replaces one."""
        _, agent_class = self._resume(tmp_path, self._aborted_result(), quality_threshold=6.0)
        config = agent_class.call_args.kwargs["config"]
        assert config.relevance_threshold == 3.5  # recorded in the checkpoint
        assert config.quality_threshold == 6.0  # from the flag
