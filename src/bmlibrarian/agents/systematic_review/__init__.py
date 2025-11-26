"""
SystematicReviewAgent Module

This module provides an AI-assisted systematic literature review agent that
automates the process of finding, filtering, evaluating, and ranking
scientific papers based on user-defined research criteria.

Main Components:
- SystematicReviewAgent: The main agent class for conducting systematic reviews
- SearchCriteria: Input specification for what papers to find
- ScoringWeights: User-configurable weights for composite scoring
- Documenter: Audit trail logging component for reproducibility
- Planner: LLM-based search strategy planning (Phase 2)
- SearchExecutor: Search query execution and result aggregation (Phase 2)
- InitialFilter: Fast heuristic-based paper filtering (Phase 3)
- InclusionEvaluator: LLM-based inclusion/exclusion evaluation (Phase 3)
- RelevanceScorer: Relevance scoring with batch support (Phase 3)
- CompositeScorer: Weighted composite scoring for ranking (Phase 3)

Data Models:
- PaperData: Core paper metadata
- ScoredPaper: Paper with relevance scoring
- AssessedPaper: Paper with full quality assessment
- PlannedQuery, SearchPlan, ExecutedQuery: Search planning models
- InclusionDecision: Inclusion/exclusion decision records
- ProcessStep, Checkpoint: Audit trail models
- ReviewStatistics, SystematicReviewResult: Output models
- PICOComponents: PICO framework extraction results (Phase 2)
- SearchResult, AggregatedResults: Search execution results (Phase 2)
- FilterResult, BatchFilterResult: Filtering results (Phase 3)
- ScoringResult, BatchScoringResult: Scoring results (Phase 3)

Configuration:
- SystematicReviewConfig: Configuration container
- get_systematic_review_config(): Load configuration from BMLibrarian config

Enums:
- StudyTypeFilter: Allowed study types for filtering
- QueryType: Types of search queries
- InclusionStatus: Paper inclusion status
- ExclusionStage: Stage at which paper was excluded

Example:
    from bmlibrarian.agents.systematic_review import (
        SystematicReviewAgent,
        SearchCriteria,
        ScoringWeights,
        StudyTypeFilter,
    )

    # Define what papers to find
    criteria = SearchCriteria(
        research_question="What is the efficacy of statins for CVD prevention?",
        purpose="Systematic review for clinical guidelines",
        inclusion_criteria=[
            "Human studies",
            "Statin intervention",
            "Cardiovascular disease outcomes"
        ],
        exclusion_criteria=[
            "Animal studies",
            "Pediatric-only populations",
            "Case reports"
        ],
        target_study_types=[
            StudyTypeFilter.RCT,
            StudyTypeFilter.META_ANALYSIS,
            StudyTypeFilter.SYSTEMATIC_REVIEW
        ],
        date_range=(2010, 2024)
    )

    # Optionally customize scoring weights
    weights = ScoringWeights(
        relevance=0.35,
        study_quality=0.25,
        methodological_rigor=0.20,
        sample_size=0.10,
        recency=0.05,
        replication_status=0.05
    )

    # Run the review
    agent = SystematicReviewAgent()
    result = agent.run_review(
        criteria=criteria,
        weights=weights,
        interactive=True,  # Pause at checkpoints for approval
        output_path="systematic_review_results.json"
    )

    # Access results
    print(f"Included papers: {result.statistics.final_included}")
    print(f"Excluded papers: {result.statistics.final_excluded}")
    for paper in result.included_papers:
        print(f"  - {paper['title']} (score: {paper['scores']['composite_score']})")
"""

from .agent import SystematicReviewAgent

from .config import (
    SystematicReviewConfig,
    get_systematic_review_config,
    get_default_config,
    DEFAULT_SYSTEMATIC_REVIEW_CONFIG,
)

from .data_models import (
    # Type aliases
    DocumentId,
    QueryId,
    RelevanceScore,
    QualityScore,
    CompositeScore,
    Confidence,
    # Enums
    StudyTypeFilter,
    QueryType,
    InclusionStatus,
    ExclusionStage,
    # Input models
    SearchCriteria,
    ScoringWeights,
    # Search planning models
    PlannedQuery,
    SearchPlan,
    ExecutedQuery,
    # Paper data models
    PaperData,
    InclusionDecision,
    ScoredPaper,
    AssessedPaper,
    # Process documentation models
    ProcessStep,
    Checkpoint,
    # Output models
    ReviewStatistics,
    SystematicReviewResult,
    # Validation functions
    validate_search_criteria,
    validate_scoring_weights,
    # Constants
    MIN_RELEVANCE_SCORE,
    MAX_RELEVANCE_SCORE,
    MIN_QUALITY_SCORE,
    MAX_QUALITY_SCORE,
    MIN_CONFIDENCE,
    MAX_CONFIDENCE,
)

from .documenter import (
    Documenter,
    StepTimer,
    # Checkpoint type constants
    CHECKPOINT_SEARCH_STRATEGY,
    CHECKPOINT_INITIAL_RESULTS,
    CHECKPOINT_SCORING_COMPLETE,
    CHECKPOINT_QUALITY_ASSESSMENT,
    CHECKPOINT_FINAL_REVIEW,
    # Action name constants
    ACTION_INITIALIZE,
    ACTION_GENERATE_SEARCH_PLAN,
    ACTION_EXECUTE_SEARCH,
    ACTION_DEDUPLICATE,
    ACTION_INITIAL_FILTER,
    ACTION_SCORE_RELEVANCE,
    ACTION_EVALUATE_INCLUSION,
    ACTION_ASSESS_QUALITY,
    ACTION_CALCULATE_COMPOSITE,
    ACTION_RANK_PAPERS,
    ACTION_GENERATE_REPORT,
)

# Phase 2: Planner and SearchExecutor
from .planner import (
    Planner,
    PICOComponents,
)

from .executor import (
    SearchExecutor,
    SearchResult,
    AggregatedResults,
)

# Phase 3: Filtering and Scoring
from .filters import (
    InitialFilter,
    InclusionEvaluator,
    FilterResult,
    BatchFilterResult,
    STUDY_TYPE_KEYWORDS,
    DEFAULT_EXCLUSION_KEYWORDS,
)

from .scorer import (
    RelevanceScorer,
    CompositeScorer,
    ScoringResult,
    BatchScoringResult,
)

__all__ = [
    # Main agent
    "SystematicReviewAgent",
    # Configuration
    "SystematicReviewConfig",
    "get_systematic_review_config",
    "get_default_config",
    "DEFAULT_SYSTEMATIC_REVIEW_CONFIG",
    # Type aliases
    "DocumentId",
    "QueryId",
    "RelevanceScore",
    "QualityScore",
    "CompositeScore",
    "Confidence",
    # Enums
    "StudyTypeFilter",
    "QueryType",
    "InclusionStatus",
    "ExclusionStage",
    # Input models
    "SearchCriteria",
    "ScoringWeights",
    # Search planning models
    "PlannedQuery",
    "SearchPlan",
    "ExecutedQuery",
    # Paper data models
    "PaperData",
    "InclusionDecision",
    "ScoredPaper",
    "AssessedPaper",
    # Process documentation models
    "ProcessStep",
    "Checkpoint",
    # Output models
    "ReviewStatistics",
    "SystematicReviewResult",
    # Validation functions
    "validate_search_criteria",
    "validate_scoring_weights",
    # Documenter
    "Documenter",
    "StepTimer",
    # Checkpoint type constants
    "CHECKPOINT_SEARCH_STRATEGY",
    "CHECKPOINT_INITIAL_RESULTS",
    "CHECKPOINT_SCORING_COMPLETE",
    "CHECKPOINT_QUALITY_ASSESSMENT",
    "CHECKPOINT_FINAL_REVIEW",
    # Action name constants
    "ACTION_INITIALIZE",
    "ACTION_GENERATE_SEARCH_PLAN",
    "ACTION_EXECUTE_SEARCH",
    "ACTION_DEDUPLICATE",
    "ACTION_INITIAL_FILTER",
    "ACTION_SCORE_RELEVANCE",
    "ACTION_EVALUATE_INCLUSION",
    "ACTION_ASSESS_QUALITY",
    "ACTION_CALCULATE_COMPOSITE",
    "ACTION_RANK_PAPERS",
    "ACTION_GENERATE_REPORT",
    # Constants
    "MIN_RELEVANCE_SCORE",
    "MAX_RELEVANCE_SCORE",
    "MIN_QUALITY_SCORE",
    "MAX_QUALITY_SCORE",
    "MIN_CONFIDENCE",
    "MAX_CONFIDENCE",
    # Phase 2: Planner
    "Planner",
    "PICOComponents",
    # Phase 2: SearchExecutor
    "SearchExecutor",
    "SearchResult",
    "AggregatedResults",
    # Phase 3: Filtering
    "InitialFilter",
    "InclusionEvaluator",
    "FilterResult",
    "BatchFilterResult",
    "STUDY_TYPE_KEYWORDS",
    "DEFAULT_EXCLUSION_KEYWORDS",
    # Phase 3: Scoring
    "RelevanceScorer",
    "CompositeScorer",
    "ScoringResult",
    "BatchScoringResult",
]
