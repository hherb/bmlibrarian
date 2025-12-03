"""
Scoring Components for SystematicReviewAgent

This module provides relevance scoring and composite score calculation:
1. RelevanceScorer: Wrapper around DocumentScoringAgent with batch support
2. CompositeScorer: Weighted composite score calculation for final ranking

Features:
- Batch processing with progress callbacks
- Integration with DocumentScoringAgent
- Relevance threshold filtering
- Composite score calculation with configurable weights
- Quality gate filtering
- Detailed scoring statistics
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple, TYPE_CHECKING

from .data_models import (
    SearchCriteria,
    ScoringWeights,
    PaperData,
    ScoredPaper,
    AssessedPaper,
    InclusionDecision,
    InclusionStatus,
    ExclusionStage,
    MIN_RELEVANCE_SCORE,
    MAX_RELEVANCE_SCORE,
)
from .config import (
    SystematicReviewConfig,
    get_systematic_review_config,
    DEFAULT_RELEVANCE_THRESHOLD,
    DEFAULT_QUALITY_THRESHOLD,
    DEFAULT_BATCH_SIZE,
)
from .filters import InclusionEvaluator

if TYPE_CHECKING:
    from ..scoring_agent import DocumentScoringAgent
    from ..orchestrator import AgentOrchestrator

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Score normalization
RELEVANCE_SCORE_MIN = 1
RELEVANCE_SCORE_MAX = 5
QUALITY_SCORE_MAX = 10

# Recency calculation
RECENCY_BASE_YEAR = 2000  # Papers before this get minimum recency score
RECENCY_CURRENT_YEAR = datetime.now().year


# =============================================================================
# Data Types
# =============================================================================

@dataclass
class ScoringResult:
    """
    Result of scoring a single paper.

    Attributes:
        paper: The paper that was scored
        relevance_score: Relevance score (1-5)
        rationale: Explanation for the score
        execution_time_seconds: Time taken to score
        success: Whether scoring succeeded
        error_message: Error message if scoring failed
    """

    paper: PaperData
    relevance_score: float
    rationale: str
    execution_time_seconds: float = 0.0
    success: bool = True
    error_message: str = ""

    def to_scored_paper(
        self,
        inclusion_decision: InclusionDecision,
        search_provenance: Optional[List[str]] = None,
    ) -> ScoredPaper:
        """
        Convert to ScoredPaper with inclusion decision.

        Args:
            inclusion_decision: Decision on paper inclusion
            search_provenance: Optional list of query IDs that found this paper

        Returns:
            ScoredPaper instance
        """
        return ScoredPaper(
            paper=self.paper,
            relevance_score=self.relevance_score,
            relevance_rationale=self.rationale,
            inclusion_decision=inclusion_decision,
            search_provenance=search_provenance,
        )


@dataclass
class BatchScoringResult:
    """
    Result of scoring a batch of papers.

    Attributes:
        scored_papers: List of scored papers
        failed_papers: Papers that failed scoring
        total_processed: Total papers attempted
        execution_time_seconds: Total time taken
        average_score: Mean relevance score
    """

    scored_papers: List[ScoredPaper] = field(default_factory=list)
    failed_papers: List[Tuple[PaperData, str]] = field(default_factory=list)
    total_processed: int = 0
    execution_time_seconds: float = 0.0
    average_score: float = 0.0

    @property
    def success_rate(self) -> float:
        """Percentage of papers successfully scored."""
        if self.total_processed == 0:
            return 0.0
        return len(self.scored_papers) / self.total_processed

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "scored_count": len(self.scored_papers),
            "failed_count": len(self.failed_papers),
            "total_processed": self.total_processed,
            "success_rate_percent": round(self.success_rate * 100, 2),
            "average_score": round(self.average_score, 2),
            "execution_time_seconds": round(self.execution_time_seconds, 2),
        }


# =============================================================================
# RelevanceScorer Class
# =============================================================================

class RelevanceScorer:
    """
    Wrapper around DocumentScoringAgent with batch support.

    Provides systematic review-specific functionality including:
    - Batch processing with progress tracking
    - Integration with inclusion/exclusion evaluation
    - Relevance threshold filtering
    - Source provenance tracking

    Attributes:
        config: Full agent configuration
        research_question: Current research question
        scoring_agent: Underlying DocumentScoringAgent

    Example:
        >>> scorer = RelevanceScorer(research_question="Effect of statins on CVD?")
        >>> result = scorer.score_batch(papers)
        >>> print(f"Average score: {result.average_score:.2f}")
    """

    def __init__(
        self,
        research_question: str,
        config: Optional[SystematicReviewConfig] = None,
        callback: Optional[Callable[[str, str], None]] = None,
        orchestrator: Optional["AgentOrchestrator"] = None,
        criteria: Optional[SearchCriteria] = None,
    ) -> None:
        """
        Initialize the RelevanceScorer.

        Args:
            research_question: Question to score papers against
            config: Optional full configuration
            callback: Optional progress callback
            orchestrator: Optional orchestrator for queue-based processing
            criteria: Optional full search criteria for inclusion evaluation
        """
        self.research_question = research_question
        self.callback = callback
        self.orchestrator = orchestrator
        self.criteria = criteria

        # Load config
        self._config = config or get_systematic_review_config()

        # Lazy-loaded scoring agent
        self._scoring_agent: Optional["DocumentScoringAgent"] = None

        # Optional inclusion evaluator
        self._inclusion_evaluator: Optional[InclusionEvaluator] = None
        if criteria:
            self._inclusion_evaluator = InclusionEvaluator(
                criteria=criteria,
                config=self._config,
                callback=callback,
            )

        logger.info(
            f"RelevanceScorer initialized: "
            f"threshold={self._config.relevance_threshold}, "
            f"batch_size={self._config.batch_size}"
        )

    def _call_callback(self, event: str, data: str) -> None:
        """Call progress callback if registered."""
        if self.callback:
            try:
                self.callback(event, data)
            except Exception as e:
                logger.warning(f"Callback error: {e}")

    def _get_scoring_agent(self) -> "DocumentScoringAgent":
        """
        Get or create DocumentScoringAgent.

        Returns:
            DocumentScoringAgent instance
        """
        if self._scoring_agent is None:
            from ..scoring_agent import DocumentScoringAgent
            from ...config import get_model, get_ollama_host, get_agent_config

            # Use scoring agent model from config
            model = get_model("scoring_agent")
            host = get_ollama_host()
            agent_config = get_agent_config("scoring")

            self._scoring_agent = DocumentScoringAgent(
                model=model,
                host=host,
                temperature=agent_config.get("temperature", 0.1),
                top_p=agent_config.get("top_p", 0.9),
                callback=self.callback,
                orchestrator=self.orchestrator,
                show_model_info=False,
            )

        return self._scoring_agent

    # =========================================================================
    # Main Scoring Methods
    # =========================================================================

    def score_paper(
        self,
        paper: PaperData,
        evaluate_inclusion: bool = True,
    ) -> ScoredPaper:
        """
        Score a single paper for relevance.

        Args:
            paper: Paper to score
            evaluate_inclusion: Whether to run inclusion/exclusion evaluation

        Returns:
            ScoredPaper with relevance score and inclusion decision

        Raises:
            ValueError: If paper data is invalid
        """
        self._call_callback(
            "scoring_started",
            f"Scoring: {paper.title[:50]}..."
        )

        start_time = time.time()

        # Get the scoring agent
        agent = self._get_scoring_agent()

        # Convert PaperData to document dict for scoring agent
        document = self._paper_to_document(paper)

        try:
            # Score with DocumentScoringAgent
            result = agent.evaluate_document(
                user_question=self.research_question,
                document=document,
            )

            relevance_score = float(result["score"])
            rationale = result["reasoning"]
            execution_time = time.time() - start_time

            # Determine inclusion decision
            if evaluate_inclusion and self._inclusion_evaluator:
                inclusion_decision = self._inclusion_evaluator.evaluate(
                    paper=paper,
                    relevance_score=relevance_score,
                )
            else:
                # Create default decision based on score
                inclusion_decision = self._create_score_based_decision(
                    relevance_score=relevance_score,
                    threshold=self._config.relevance_threshold,
                )

            scored_paper = ScoredPaper(
                paper=paper,
                relevance_score=relevance_score,
                relevance_rationale=rationale,
                inclusion_decision=inclusion_decision,
            )

            self._call_callback(
                "scoring_completed",
                f"Score: {relevance_score}/5"
            )

            return scored_paper

        except Exception as e:
            logger.error(f"Scoring failed for paper {paper.document_id}: {e}")
            self._call_callback("scoring_failed", str(e))

            # Return paper with error score
            return ScoredPaper(
                paper=paper,
                relevance_score=0.0,
                relevance_rationale=f"Scoring failed: {e}",
                inclusion_decision=InclusionDecision(
                    status=InclusionStatus.UNCERTAIN,
                    stage=ExclusionStage.RELEVANCE_SCORING,
                    reasons=[f"Scoring error: {e}"],
                    rationale="Unable to score due to error",
                    confidence=0.0,
                ),
            )

    def score_batch(
        self,
        papers: List[PaperData],
        evaluate_inclusion: bool = True,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        paper_sources: Optional[Dict[int, List[str]]] = None,
    ) -> BatchScoringResult:
        """
        Score a batch of papers for relevance.

        Args:
            papers: List of papers to score
            evaluate_inclusion: Whether to run inclusion/exclusion evaluation
            progress_callback: Optional callback(current, total) for progress
            paper_sources: Optional dict mapping document_id to query_ids

        Returns:
            BatchScoringResult with all scored papers
        """
        self._call_callback(
            "batch_scoring_started",
            f"Scoring {len(papers)} papers"
        )

        start_time = time.time()
        scored_papers: List[ScoredPaper] = []
        failed_papers: List[Tuple[PaperData, str]] = []
        total_score = 0.0

        for i, paper in enumerate(papers):
            try:
                scored_paper = self.score_paper(paper, evaluate_inclusion)

                # Add source provenance if available
                if paper_sources and paper.document_id in paper_sources:
                    scored_paper.search_provenance = paper_sources[paper.document_id]

                scored_papers.append(scored_paper)
                total_score += scored_paper.relevance_score

            except Exception as e:
                logger.error(f"Failed to score paper {paper.document_id}: {e}")
                failed_papers.append((paper, str(e)))

            if progress_callback:
                progress_callback(i + 1, len(papers))

        execution_time = time.time() - start_time
        average_score = total_score / len(scored_papers) if scored_papers else 0.0

        self._call_callback(
            "batch_scoring_completed",
            f"Scored {len(scored_papers)}, failed {len(failed_papers)}"
        )

        logger.info(
            f"Batch scoring complete: {len(scored_papers)} scored, "
            f"{len(failed_papers)} failed, avg={average_score:.2f} "
            f"({execution_time:.2f}s)"
        )

        return BatchScoringResult(
            scored_papers=scored_papers,
            failed_papers=failed_papers,
            total_processed=len(papers),
            execution_time_seconds=execution_time,
            average_score=average_score,
        )

    # =========================================================================
    # Threshold Filtering
    # =========================================================================

    def apply_relevance_threshold(
        self,
        scored_papers: List[ScoredPaper],
        threshold: Optional[float] = None,
    ) -> Tuple[List[ScoredPaper], List[ScoredPaper]]:
        """
        Split papers by relevance threshold.

        Args:
            scored_papers: Papers to filter
            threshold: Score threshold (uses config default if not provided)

        Returns:
            Tuple of (above_threshold, below_threshold) papers
        """
        if threshold is None:
            threshold = self._config.relevance_threshold

        above_threshold: List[ScoredPaper] = []
        below_threshold: List[ScoredPaper] = []

        for paper in scored_papers:
            if paper.relevance_score >= threshold:
                above_threshold.append(paper)
            else:
                # Update inclusion decision for papers below threshold
                if paper.inclusion_decision.status != InclusionStatus.EXCLUDED:
                    paper.inclusion_decision = InclusionDecision.create_excluded(
                        stage=ExclusionStage.RELEVANCE_SCORING,
                        reasons=[f"Below relevance threshold ({paper.relevance_score} < {threshold})"],
                        rationale=f"Paper scored {paper.relevance_score}/5, below threshold of {threshold}",
                        confidence=1.0,
                    )
                below_threshold.append(paper)

        logger.info(
            f"Threshold filter: {len(above_threshold)} above, "
            f"{len(below_threshold)} below threshold {threshold}"
        )

        return above_threshold, below_threshold

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _paper_to_document(self, paper: PaperData) -> Dict[str, Any]:
        """
        Convert PaperData to document dict for scoring agent.

        Args:
            paper: PaperData instance

        Returns:
            Document dictionary compatible with DocumentScoringAgent
        """
        return {
            "id": paper.document_id,
            "title": paper.title,
            "abstract": paper.abstract or "",
            "authors": paper.authors,
            "publication": paper.journal,
            "publication_date": str(paper.year),
            "doi": paper.doi,
            "pmid": paper.pmid,
        }

    def _create_score_based_decision(
        self,
        relevance_score: float,
        threshold: float,
    ) -> InclusionDecision:
        """
        Create inclusion decision based on relevance score.

        Args:
            relevance_score: Paper's relevance score
            threshold: Minimum score for inclusion

        Returns:
            InclusionDecision based on score threshold
        """
        if relevance_score >= threshold:
            return InclusionDecision.create_included(
                stage=ExclusionStage.RELEVANCE_SCORING,
                rationale=f"Score {relevance_score}/5 meets threshold {threshold}",
                criteria_matched=[f"Relevance score >= {threshold}"],
                confidence=min(relevance_score / MAX_RELEVANCE_SCORE, 1.0),
            )
        else:
            return InclusionDecision.create_excluded(
                stage=ExclusionStage.RELEVANCE_SCORING,
                reasons=[f"Below threshold ({relevance_score} < {threshold})"],
                rationale=f"Score {relevance_score}/5 below threshold {threshold}",
                confidence=1.0 - (relevance_score / threshold) if threshold > 0 else 1.0,
            )

    # =========================================================================
    # Statistics
    # =========================================================================

    def get_scoring_statistics(
        self,
        result: BatchScoringResult,
    ) -> Dict[str, Any]:
        """
        Get detailed statistics about scoring results.

        Args:
            result: BatchScoringResult to analyze

        Returns:
            Dictionary with detailed statistics
        """
        # Score distribution
        score_distribution = {i: 0 for i in range(6)}  # 0-5
        for paper in result.scored_papers:
            score_bucket = int(paper.relevance_score)
            score_bucket = max(0, min(5, score_bucket))
            score_distribution[score_bucket] += 1

        # Inclusion status counts
        status_counts = {
            "included": 0,
            "excluded": 0,
            "uncertain": 0,
        }
        for paper in result.scored_papers:
            status_key = paper.inclusion_decision.status.value
            status_counts[status_key] = status_counts.get(status_key, 0) + 1

        return {
            "total_papers": result.total_processed,
            "successfully_scored": len(result.scored_papers),
            "failed": len(result.failed_papers),
            "average_score": round(result.average_score, 2),
            "score_distribution": score_distribution,
            "inclusion_status": status_counts,
            "execution_time_seconds": round(result.execution_time_seconds, 2),
            "papers_per_second": round(
                len(result.scored_papers) / result.execution_time_seconds, 2
            ) if result.execution_time_seconds > 0 else 0,
        }


# =============================================================================
# CompositeScorer Class
# =============================================================================

class CompositeScorer:
    """
    Calculates weighted composite scores for paper ranking.

    Uses configurable weights to combine multiple scoring dimensions
    into a single composite score for final ranking.

    Dimensions:
    - relevance: Relevance to research question (1-5, normalized)
    - study_quality: Study design and methodology quality (0-10)
    - methodological_rigor: Methodological rigor score (0-10)
    - sample_size: Sample size adequacy (0-10)
    - recency: Publication recency (0-10)
    - replication_status: Replication evidence (0-10)

    Attributes:
        weights: ScoringWeights for composite calculation

    Example:
        >>> scorer = CompositeScorer(weights)
        >>> papers = scorer.score_and_rank(assessed_papers)
        >>> for paper in papers[:10]:
        ...     print(f"{paper.title}: {paper.composite_score:.2f}")
    """

    def __init__(
        self,
        weights: Optional[ScoringWeights] = None,
    ) -> None:
        """
        Initialize the CompositeScorer.

        Args:
            weights: Optional weights. Uses default if not provided.
        """
        self.weights = weights or ScoringWeights()

        # Validate weights
        if not self.weights.validate():
            logger.warning(
                f"Scoring weights do not sum to 1.0. "
                f"Scores may be incorrectly scaled."
            )

    # =========================================================================
    # Scoring Methods
    # =========================================================================

    def score(
        self,
        paper: AssessedPaper,
    ) -> float:
        """
        Calculate composite score for a single paper.

        Args:
            paper: AssessedPaper with all assessment data

        Returns:
            Composite score (0-10 scale)
        """
        weights_dict = self.weights.to_dict()

        # Extract individual scores
        relevance = self._normalize_relevance_score(
            paper.scored_paper.relevance_score
        )

        study_quality = self._extract_study_quality(paper.study_assessment)
        methodological_rigor = self._extract_methodological_rigor(paper.study_assessment)
        sample_size = self._extract_sample_size_score(paper.study_assessment)
        recency = self._calculate_recency_score(paper.scored_paper.paper.year)
        replication = self._extract_replication_score(paper.paper_weight)

        # Calculate weighted composite
        composite = (
            weights_dict["relevance"] * relevance +
            weights_dict["study_quality"] * study_quality +
            weights_dict["methodological_rigor"] * methodological_rigor +
            weights_dict["sample_size"] * sample_size +
            weights_dict["recency"] * recency +
            weights_dict["replication_status"] * replication
        )

        # Normalize to 0-10 scale
        return min(max(composite, 0.0), QUALITY_SCORE_MAX)

    def score_batch(
        self,
        papers: List[AssessedPaper],
    ) -> List[AssessedPaper]:
        """
        Calculate composite scores for all papers.

        Args:
            papers: List of assessed papers

        Returns:
            Same papers with composite_score set
        """
        for paper in papers:
            paper.composite_score = self.score(paper)

        return papers

    def rank(
        self,
        papers: List[AssessedPaper],
    ) -> List[AssessedPaper]:
        """
        Sort papers by composite score (highest first).

        Also sets the final_rank attribute on each paper.

        Args:
            papers: List of papers to rank

        Returns:
            Sorted list of papers
        """
        # Calculate scores if not already done
        for paper in papers:
            if paper.composite_score is None:
                paper.composite_score = self.score(paper)

        # Sort by composite score (descending)
        sorted_papers = sorted(
            papers,
            key=lambda p: p.composite_score or 0.0,
            reverse=True,
        )

        # Set ranks
        for i, paper in enumerate(sorted_papers):
            paper.final_rank = i + 1

        return sorted_papers

    def score_and_rank(
        self,
        papers: List[AssessedPaper],
    ) -> List[AssessedPaper]:
        """
        Score and rank papers in one operation.

        Args:
            papers: List of papers to process

        Returns:
            Sorted list with scores and ranks
        """
        self.score_batch(papers)
        return self.rank(papers)

    # =========================================================================
    # Quality Gate
    # =========================================================================

    def apply_quality_gate(
        self,
        papers: List[AssessedPaper],
        threshold: float = DEFAULT_QUALITY_THRESHOLD,
    ) -> Tuple[List[AssessedPaper], List[AssessedPaper]]:
        """
        Filter papers by quality threshold.

        Updates inclusion decision for both passed and failed papers to ensure
        the rationale reflects the final decision (not the initial screening).

        Args:
            papers: Papers to filter (must have composite_score set)
            threshold: Minimum composite score for inclusion

        Returns:
            Tuple of (passed, failed) papers
        """
        passed: List[AssessedPaper] = []
        failed: List[AssessedPaper] = []

        for paper in papers:
            score = paper.composite_score
            if score is None:
                score = self.score(paper)
                paper.composite_score = score

            if score >= threshold:
                # Update inclusion decision to reflect final inclusion
                # This overwrites any previous screening rationale to avoid
                # contradictory messages like "excluded because... " for included papers
                paper.scored_paper.inclusion_decision = InclusionDecision.create_included(
                    stage=ExclusionStage.QUALITY_GATE,
                    rationale=self._build_inclusion_rationale(paper, score, threshold),
                    criteria_matched=paper.scored_paper.inclusion_decision.criteria_matched or [],
                    confidence=min(1.0, score / 10.0),  # Higher score = higher confidence
                )
                passed.append(paper)
            else:
                # Update inclusion decision for exclusion
                paper.scored_paper.inclusion_decision = InclusionDecision.create_excluded(
                    stage=ExclusionStage.QUALITY_GATE,
                    reasons=[f"Below quality threshold ({score:.2f} < {threshold})"],
                    rationale=f"Composite score {score:.2f} below quality threshold {threshold}",
                    confidence=1.0,
                )
                failed.append(paper)

        logger.info(
            f"Quality gate: {len(passed)} passed, {len(failed)} failed "
            f"(threshold={threshold})"
        )

        return passed, failed

    def _build_inclusion_rationale(
        self,
        paper: AssessedPaper,
        score: float,
        threshold: float,
    ) -> str:
        """
        Build a meaningful inclusion rationale for papers passing quality gate.

        Args:
            paper: The assessed paper
            score: Composite score
            threshold: Quality threshold

        Returns:
            Human-readable rationale string
        """
        parts = []

        # Start with overall score
        parts.append(f"Composite score {score:.2f} exceeds threshold {threshold:.1f}.")

        # Add relevance info
        relevance = paper.scored_paper.relevance_score
        parts.append(f"Relevance score: {relevance:.1f}/5.")

        # Add study type info if available
        if paper.study_assessment:
            study_type = paper.study_assessment.get("study_type", "")
            if study_type:
                parts.append(f"Study type: {study_type}.")

            quality = paper.study_assessment.get("quality_score", 0)
            if quality > 0:
                parts.append(f"Study quality: {quality:.1f}/10.")

        # Add paper weight info if available
        if paper.paper_weight:
            weight = paper.paper_weight.get("composite_score", 0)
            if weight > 0:
                parts.append(f"Paper weight: {weight:.1f}/10.")

        return " ".join(parts)

    # =========================================================================
    # Score Extraction Helpers
    # =========================================================================

    def _normalize_relevance_score(self, score: float) -> float:
        """
        Normalize relevance score from 1-5 to 0-10 scale.

        Args:
            score: Relevance score (1-5)

        Returns:
            Normalized score (0-10)
        """
        # Convert 1-5 to 0-10
        normalized = (score - RELEVANCE_SCORE_MIN) / (RELEVANCE_SCORE_MAX - RELEVANCE_SCORE_MIN) * QUALITY_SCORE_MAX
        return max(0.0, min(QUALITY_SCORE_MAX, normalized))

    def _extract_study_quality(self, study_assessment: Dict[str, Any]) -> float:
        """
        Extract study quality score from assessment.

        Args:
            study_assessment: StudyAssessmentAgent output

        Returns:
            Quality score (0-10)
        """
        # Try various keys that might contain quality scores
        for key in ["overall_quality", "quality_score", "study_quality", "design_quality"]:
            if key in study_assessment:
                value = study_assessment[key]
                if isinstance(value, (int, float)):
                    return min(max(float(value), 0.0), QUALITY_SCORE_MAX)

        # Default to moderate quality if not found
        return 5.0

    def _extract_methodological_rigor(self, study_assessment: Dict[str, Any]) -> float:
        """
        Extract methodological rigor score from assessment.

        Args:
            study_assessment: StudyAssessmentAgent output

        Returns:
            Rigor score (0-10)
        """
        for key in ["methodological_rigor", "rigor_score", "methodology_quality"]:
            if key in study_assessment:
                value = study_assessment[key]
                if isinstance(value, (int, float)):
                    return min(max(float(value), 0.0), QUALITY_SCORE_MAX)

        # Try to derive from bias risk
        if "bias_risk" in study_assessment:
            bias = study_assessment["bias_risk"]
            if isinstance(bias, str):
                # Convert bias risk to score
                bias_scores = {"low": 8.0, "moderate": 5.0, "high": 2.0}
                return bias_scores.get(bias.lower(), 5.0)

        return 5.0

    def _extract_sample_size_score(self, study_assessment: Dict[str, Any]) -> float:
        """
        Extract sample size adequacy score from assessment.

        Args:
            study_assessment: StudyAssessmentAgent output

        Returns:
            Sample size score (0-10)
        """
        for key in ["sample_size_score", "sample_adequacy", "statistical_power"]:
            if key in study_assessment:
                value = study_assessment[key]
                if isinstance(value, (int, float)):
                    return min(max(float(value), 0.0), QUALITY_SCORE_MAX)

        # Try to get raw sample size and estimate score
        if "sample_size" in study_assessment:
            n = study_assessment["sample_size"]
            if isinstance(n, int):
                # Simple heuristic: log scale scoring
                if n < 30:
                    return 2.0
                elif n < 100:
                    return 4.0
                elif n < 500:
                    return 6.0
                elif n < 1000:
                    return 8.0
                else:
                    return 10.0

        return 5.0

    def _calculate_recency_score(self, year: int) -> float:
        """
        Calculate recency score based on publication year.

        More recent papers get higher scores.

        Args:
            year: Publication year

        Returns:
            Recency score (0-10)
        """
        if year >= RECENCY_CURRENT_YEAR:
            return QUALITY_SCORE_MAX

        years_old = RECENCY_CURRENT_YEAR - year

        if years_old <= 2:
            return 9.0
        elif years_old <= 5:
            return 7.0
        elif years_old <= 10:
            return 5.0
        elif years_old <= 20:
            return 3.0
        else:
            return 1.0

    def _extract_replication_score(self, paper_weight: Dict[str, Any]) -> float:
        """
        Extract replication status score from paper weight assessment.

        Args:
            paper_weight: PaperWeightAssessmentAgent output

        Returns:
            Replication score (0-10)
        """
        for key in ["replication_status", "replication_score", "reproducibility"]:
            if key in paper_weight:
                value = paper_weight[key]
                if isinstance(value, (int, float)):
                    return min(max(float(value), 0.0), QUALITY_SCORE_MAX)
                elif isinstance(value, str):
                    # Convert status to score
                    status_scores = {
                        "replicated": 10.0,
                        "partially_replicated": 7.0,
                        "not_replicated": 3.0,
                        "not_attempted": 5.0,
                        "unknown": 5.0,
                    }
                    return status_scores.get(value.lower(), 5.0)

        # Default: assume no replication data
        return 5.0

    # =========================================================================
    # Statistics
    # =========================================================================

    def get_scoring_statistics(
        self,
        papers: List[AssessedPaper],
    ) -> Dict[str, Any]:
        """
        Get statistics about composite scores.

        Args:
            papers: List of assessed papers

        Returns:
            Dictionary with score statistics
        """
        if not papers:
            return {"total": 0, "message": "No papers to analyze"}

        scores = [
            p.composite_score for p in papers
            if p.composite_score is not None
        ]

        if not scores:
            return {"total": len(papers), "scored": 0}

        return {
            "total": len(papers),
            "scored": len(scores),
            "min_score": round(min(scores), 2),
            "max_score": round(max(scores), 2),
            "mean_score": round(sum(scores) / len(scores), 2),
            "median_score": round(sorted(scores)[len(scores) // 2], 2),
            "weights_used": self.weights.to_dict(),
        }
