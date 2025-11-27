# SystematicReviewAgent Data Models

This document defines all data structures used by the SystematicReviewAgent.

## Input Models

### SearchCriteria

The primary input specification for a systematic review:

```python
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import date
from enum import Enum


class StudyTypeFilter(Enum):
    """Allowed study types for filtering."""

    RCT = "rct"
    COHORT_PROSPECTIVE = "cohort_prospective"
    COHORT_RETROSPECTIVE = "cohort_retrospective"
    CASE_CONTROL = "case_control"
    CROSS_SECTIONAL = "cross_sectional"
    SYSTEMATIC_REVIEW = "systematic_review"
    META_ANALYSIS = "meta_analysis"
    CASE_SERIES = "case_series"
    CASE_REPORT = "case_report"
    ANY = "any"


@dataclass
class SearchCriteria:
    """
    Input specification for systematic review paper finding.

    This is the primary input the user provides to configure the search.

    Attributes:
        research_question: The main research question to investigate
        purpose: Brief explanation of why this review is being conducted
        inclusion_criteria: List of criteria that papers MUST meet
        exclusion_criteria: List of criteria that DISQUALIFY papers
        target_study_types: Allowed study designs (None = all types)
        date_range: Optional (start_year, end_year) filter
        language: Optional language filter (default: English only)
        min_sample_size: Optional minimum sample size requirement
        max_results: Optional cap on total papers to include
        custom_search_terms: Optional additional search terms
        mesh_terms: Optional MeSH terms to include in search
    """

    research_question: str
    purpose: str
    inclusion_criteria: List[str]
    exclusion_criteria: List[str]
    target_study_types: Optional[List[StudyTypeFilter]] = None
    date_range: Optional[tuple[int, int]] = None
    language: str = "English"
    min_sample_size: Optional[int] = None
    max_results: Optional[int] = None
    custom_search_terms: Optional[List[str]] = None
    mesh_terms: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "research_question": self.research_question,
            "purpose": self.purpose,
            "inclusion_criteria": self.inclusion_criteria,
            "exclusion_criteria": self.exclusion_criteria,
            "target_study_types": (
                [st.value for st in self.target_study_types]
                if self.target_study_types
                else None
            ),
            "date_range": self.date_range,
            "language": self.language,
            "min_sample_size": self.min_sample_size,
            "max_results": self.max_results,
            "custom_search_terms": self.custom_search_terms,
            "mesh_terms": self.mesh_terms,
        }


@dataclass
class ScoringWeights:
    """
    User-configurable weights for composite score calculation.

    This comprehensive scoring system supports both:
    - Cochrane-style systematic review dimensions: methodological_rigor,
      sample_size, replication_status
    - BMLibrarian practical evidence dimensions: paper_weight,
      source_reliability

    All weights should sum to 1.0 for normalized scoring. Users can choose
    which dimensions to emphasize based on their review type using presets
    or custom configurations.

    Attributes:
        relevance: Weight for relevance to research question (default: 0.25)
        study_quality: Weight for study design quality (default: 0.20)
        methodological_rigor: Weight for methodological quality (default: 0.15)
        sample_size: Weight for sample size adequacy (default: 0.05)
        recency: Weight for publication recency (default: 0.10)
        replication_status: Weight for replication evidence (default: 0.05)
        paper_weight: Weight for BMLibrarian paper weight assessment (default: 0.15)
        source_reliability: Weight for source/journal reliability (default: 0.05)
    """

    relevance: float = 0.25
    study_quality: float = 0.20
    methodological_rigor: float = 0.15
    sample_size: float = 0.05
    recency: float = 0.10
    replication_status: float = 0.05
    paper_weight: float = 0.15
    source_reliability: float = 0.05

    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary."""
        return {
            "relevance": self.relevance,
            "study_quality": self.study_quality,
            "methodological_rigor": self.methodological_rigor,
            "sample_size": self.sample_size,
            "recency": self.recency,
            "replication_status": self.replication_status,
            "paper_weight": self.paper_weight,
            "source_reliability": self.source_reliability,
        }

    @classmethod
    def cochrane_focused(cls) -> "ScoringWeights":
        """Create weights emphasizing Cochrane-style systematic review dimensions."""
        return cls(
            relevance=0.30, study_quality=0.20, methodological_rigor=0.20,
            sample_size=0.10, recency=0.10, replication_status=0.10,
            paper_weight=0.0, source_reliability=0.0,
        )

    @classmethod
    def practical_focused(cls) -> "ScoringWeights":
        """Create weights emphasizing BMLibrarian practical evidence dimensions."""
        return cls(
            relevance=0.30, study_quality=0.25, methodological_rigor=0.0,
            sample_size=0.0, recency=0.10, replication_status=0.0,
            paper_weight=0.25, source_reliability=0.10,
        )

    def validate(self) -> bool:
        """Check that weights sum to approximately 1.0."""
        total = sum(self.to_dict().values())
        return 0.99 <= total <= 1.01
```

## Search Planning Models

### PlannedQuery

Represents a single search query in the plan:

```python
class QueryType(Enum):
    """Type of search query."""

    SEMANTIC = "semantic"          # Embedding-based similarity
    KEYWORD = "keyword"            # Full-text search
    HYBRID = "hybrid"              # Combined semantic + keyword
    SQL = "sql"                    # Generated PostgreSQL query
    HYDE = "hyde"                  # Hypothetical document embedding


@dataclass
class PlannedQuery:
    """
    A single query in the search plan.

    Each query targets a specific aspect of the research question
    using a particular search strategy.

    Attributes:
        query_id: Unique identifier for this query
        query_text: The actual query string
        query_type: Type of search to perform
        purpose: Why this query was generated
        expected_coverage: What aspect of the question it addresses
        priority: Execution priority (1 = highest)
        estimated_results: Expected number of results (for planning)
    """

    query_id: str
    query_text: str
    query_type: QueryType
    purpose: str
    expected_coverage: str
    priority: int = 1
    estimated_results: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query_id": self.query_id,
            "query_text": self.query_text,
            "query_type": self.query_type.value,
            "purpose": self.purpose,
            "expected_coverage": self.expected_coverage,
            "priority": self.priority,
            "estimated_results": self.estimated_results,
        }


@dataclass
class SearchPlan:
    """
    Generated strategy for finding papers.

    Contains all planned queries and the rationale for the strategy.

    Attributes:
        queries: List of queries to execute
        total_estimated_yield: Expected total papers before deduplication
        search_rationale: LLM-generated explanation of the strategy
        iteration: Which iteration of planning this is (1 = initial)
        coverage_analysis: How well queries cover the research question
    """

    queries: List[PlannedQuery]
    total_estimated_yield: int
    search_rationale: str
    iteration: int = 1
    coverage_analysis: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "queries": [q.to_dict() for q in self.queries],
            "total_estimated_yield": self.total_estimated_yield,
            "search_rationale": self.search_rationale,
            "iteration": self.iteration,
            "coverage_analysis": self.coverage_analysis,
        }
```

### ExecutedQuery

Records the results of an executed query:

```python
@dataclass
class ExecutedQuery:
    """
    Result of executing a single query.

    Tracks what happened when the query was run.

    Attributes:
        planned_query: The original planned query
        document_ids: List of document IDs returned
        execution_time_seconds: How long the query took
        actual_results: Number of results returned
        error: Error message if query failed
        timestamp: When the query was executed
    """

    planned_query: PlannedQuery
    document_ids: List[int]
    execution_time_seconds: float
    actual_results: int
    error: Optional[str] = None
    timestamp: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "planned_query": self.planned_query.to_dict(),
            "document_ids": self.document_ids,
            "execution_time_seconds": self.execution_time_seconds,
            "actual_results": self.actual_results,
            "error": self.error,
            "timestamp": self.timestamp,
        }
```

## Paper Data Models

### PaperData

Core paper metadata:

```python
@dataclass
class PaperData:
    """
    Core paper metadata from database.

    Attributes:
        document_id: Database primary key
        title: Paper title
        authors: List of author names
        year: Publication year
        journal: Journal name
        abstract: Paper abstract
        doi: Digital Object Identifier
        pmid: PubMed ID
        pmc_id: PubMed Central ID
        full_text: Full text if available
        pdf_path: Path to local PDF if available
        source: Data source (pubmed, medrxiv, etc.)
    """

    document_id: int
    title: str
    authors: List[str]
    year: int
    journal: Optional[str] = None
    abstract: Optional[str] = None
    doi: Optional[str] = None
    pmid: Optional[str] = None
    pmc_id: Optional[str] = None
    full_text: Optional[str] = None
    pdf_path: Optional[str] = None
    source: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "title": self.title,
            "authors": self.authors,
            "year": self.year,
            "journal": self.journal,
            "doi": self.doi,
            "pmid": self.pmid,
            "pmc_id": self.pmc_id,
            "source": self.source,
            "has_full_text": self.full_text is not None,
            "has_pdf": self.pdf_path is not None,
        }
```

### InclusionDecision

Records the inclusion/exclusion decision:

```python
class InclusionStatus(Enum):
    """Paper inclusion status."""

    INCLUDED = "included"
    EXCLUDED = "excluded"
    UNCERTAIN = "uncertain"  # Needs human review


class ExclusionStage(Enum):
    """At which stage the paper was excluded."""

    INITIAL_FILTER = "initial_filter"      # Fast heuristic filter
    RELEVANCE_SCORING = "relevance_scoring"  # LLM relevance check
    INCLUSION_CRITERIA = "inclusion_criteria"  # Failed inclusion
    EXCLUSION_CRITERIA = "exclusion_criteria"  # Matched exclusion
    QUALITY_GATE = "quality_gate"          # Below quality threshold
    MANUAL_REVIEW = "manual_review"        # Human excluded


@dataclass
class InclusionDecision:
    """
    Decision on whether to include a paper.

    All decisions include rationale for audit trail.

    Attributes:
        status: Include, exclude, or uncertain
        stage: At which stage the decision was made
        reasons: List of specific reasons (criteria matched/failed)
        rationale: LLM-generated explanation
        confidence: Confidence in the decision (0-1)
        criteria_matched: Which inclusion criteria were met
        criteria_failed: Which inclusion criteria were not met
        exclusion_matched: Which exclusion criteria triggered
    """

    status: InclusionStatus
    stage: ExclusionStage
    reasons: List[str]
    rationale: str
    confidence: float = 1.0
    criteria_matched: Optional[List[str]] = None
    criteria_failed: Optional[List[str]] = None
    exclusion_matched: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "stage": self.stage.value,
            "reasons": self.reasons,
            "rationale": self.rationale,
            "confidence": self.confidence,
            "criteria_matched": self.criteria_matched,
            "criteria_failed": self.criteria_failed,
            "exclusion_matched": self.exclusion_matched,
        }
```

### ScoredPaper

Paper with relevance scoring:

```python
@dataclass
class ScoredPaper:
    """
    Paper with relevance scoring applied.

    Attributes:
        paper: Base paper data
        relevance_score: Score from DocumentScoringAgent (1-5)
        relevance_rationale: LLM explanation of score
        inclusion_decision: Include/exclude decision
        relevant_citations: Extracted supporting passages
        search_provenance: Which queries found this paper
    """

    paper: PaperData
    relevance_score: float
    relevance_rationale: str
    inclusion_decision: InclusionDecision
    relevant_citations: Optional[List[Dict[str, Any]]] = None
    search_provenance: Optional[List[str]] = None  # query_ids

    @property
    def is_included(self) -> bool:
        return self.inclusion_decision.status == InclusionStatus.INCLUDED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "paper": self.paper.to_dict(),
            "relevance_score": self.relevance_score,
            "relevance_rationale": self.relevance_rationale,
            "inclusion_decision": self.inclusion_decision.to_dict(),
            "relevant_citations": self.relevant_citations,
            "search_provenance": self.search_provenance,
        }
```

### AssessedPaper

Paper with full quality assessment:

```python
@dataclass
class AssessedPaper:
    """
    Paper with full quality assessment.

    This is the final form of a paper after all evaluations.

    Attributes:
        scored_paper: Base scored paper data
        study_assessment: StudyAssessmentAgent output
        paper_weight: PaperWeightAssessmentAgent output
        pico_components: PICOAgent output (if applicable)
        prisma_assessment: PRISMA2020Agent output (if applicable)
        composite_score: Final weighted score
        final_rank: Position in final ranking
    """

    scored_paper: ScoredPaper
    study_assessment: Dict[str, Any]  # StudyAssessment.to_dict()
    paper_weight: Dict[str, Any]  # PaperWeightResult.to_dict()
    pico_components: Optional[Dict[str, Any]] = None
    prisma_assessment: Optional[Dict[str, Any]] = None
    composite_score: Optional[float] = None
    final_rank: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scored_paper": self.scored_paper.to_dict(),
            "study_assessment": self.study_assessment,
            "paper_weight": self.paper_weight,
            "pico_components": self.pico_components,
            "prisma_assessment": self.prisma_assessment,
            "composite_score": self.composite_score,
            "final_rank": self.final_rank,
        }
```

## Process Documentation Models

### ProcessStep

Records a single workflow step:

```python
@dataclass
class ProcessStep:
    """
    Documentation of a single step in the process.

    Every action is logged for complete audit trail.

    Attributes:
        step_number: Sequential step number
        action: What action was performed
        tool_used: Which tool/agent was invoked
        input_summary: Summary of inputs
        output_summary: Summary of outputs
        decision_rationale: Why this action was taken
        timestamp: When the step occurred
        duration_seconds: How long it took
        metrics: Quantitative metrics (papers processed, etc.)
        error: Error message if step failed
    """

    step_number: int
    action: str
    tool_used: Optional[str]
    input_summary: str
    output_summary: str
    decision_rationale: str
    timestamp: str
    duration_seconds: float
    metrics: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_number": self.step_number,
            "action": self.action,
            "tool_used": self.tool_used,
            "input_summary": self.input_summary,
            "output_summary": self.output_summary,
            "decision_rationale": self.decision_rationale,
            "timestamp": self.timestamp,
            "duration_seconds": self.duration_seconds,
            "metrics": self.metrics,
            "error": self.error,
        }
```

### Checkpoint

Records a workflow checkpoint for resumability:

```python
@dataclass
class Checkpoint:
    """
    Checkpoint for workflow resumability.

    Allows the review to be paused and resumed.

    Attributes:
        checkpoint_id: Unique identifier
        checkpoint_type: Type of checkpoint
        timestamp: When checkpoint was created
        phase: Current workflow phase
        state_snapshot: Serialized state at this point
        user_decision: User's decision at checkpoint (if interactive)
        notes: Any notes from user or system
    """

    checkpoint_id: str
    checkpoint_type: str
    timestamp: str
    phase: str
    state_snapshot: Dict[str, Any]
    user_decision: Optional[str] = None
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "checkpoint_type": self.checkpoint_type,
            "timestamp": self.timestamp,
            "phase": self.phase,
            "user_decision": self.user_decision,
            "notes": self.notes,
            # state_snapshot excluded for size
        }
```

## Output Models

### SystematicReviewResult

The complete output of the review:

```python
@dataclass
class ReviewStatistics:
    """Summary statistics for the review."""

    total_considered: int
    passed_initial_filter: int
    passed_relevance_threshold: int
    passed_quality_gate: int
    final_included: int
    final_excluded: int
    uncertain_for_review: int
    processing_time_seconds: float
    total_llm_calls: int
    total_tokens_used: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_considered": self.total_considered,
            "passed_initial_filter": self.passed_initial_filter,
            "passed_relevance_threshold": self.passed_relevance_threshold,
            "passed_quality_gate": self.passed_quality_gate,
            "final_included": self.final_included,
            "final_excluded": self.final_excluded,
            "uncertain_for_review": self.uncertain_for_review,
            "processing_time_seconds": self.processing_time_seconds,
            "total_llm_calls": self.total_llm_calls,
            "total_tokens_used": self.total_tokens_used,
        }


@dataclass
class SystematicReviewResult:
    """
    Complete output of the systematic review.

    This is the final JSON output file.

    Attributes:
        metadata: Review metadata and configuration
        search_strategy: Search plan and execution details
        scoring_config: Weights used for scoring
        included_papers: Papers that passed all criteria
        excluded_papers: Papers that were rejected (with reasons)
        uncertain_papers: Papers needing human review
        process_log: Complete audit trail
        statistics: Summary statistics
    """

    metadata: Dict[str, Any]
    search_strategy: Dict[str, Any]
    scoring_config: Dict[str, Any]
    included_papers: List[Dict[str, Any]]
    excluded_papers: List[Dict[str, Any]]
    uncertain_papers: List[Dict[str, Any]]
    process_log: List[Dict[str, Any]]
    statistics: ReviewStatistics

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metadata": self.metadata,
            "search_strategy": self.search_strategy,
            "scoring_config": self.scoring_config,
            "included_papers": self.included_papers,
            "excluded_papers": self.excluded_papers,
            "uncertain_papers": self.uncertain_papers,
            "process_log": self.process_log,
            "statistics": self.statistics.to_dict(),
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        import json
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def save(self, path: str) -> None:
        """Save to JSON file."""
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json())
```

## JSON Schema

For validation and documentation, here's the JSON schema for the output:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "SystematicReviewResult",
  "type": "object",
  "required": [
    "metadata",
    "search_strategy",
    "scoring_config",
    "included_papers",
    "excluded_papers",
    "process_log",
    "statistics"
  ],
  "properties": {
    "metadata": {
      "type": "object",
      "required": ["research_question", "purpose", "inclusion_criteria", "exclusion_criteria"],
      "properties": {
        "research_question": {"type": "string"},
        "purpose": {"type": "string"},
        "inclusion_criteria": {"type": "array", "items": {"type": "string"}},
        "exclusion_criteria": {"type": "array", "items": {"type": "string"}},
        "generated_at": {"type": "string", "format": "date-time"},
        "agent_version": {"type": "string"}
      }
    },
    "included_papers": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["document_id", "title", "inclusion_rationale", "scores"],
        "properties": {
          "document_id": {"type": "integer"},
          "title": {"type": "string"},
          "authors": {"type": "array", "items": {"type": "string"}},
          "year": {"type": "integer"},
          "journal": {"type": "string"},
          "doi": {"type": "string"},
          "pmid": {"type": "string"},
          "inclusion_rationale": {"type": "string"},
          "scores": {
            "type": "object",
            "properties": {
              "relevance": {"type": "number", "minimum": 1, "maximum": 5},
              "study_quality": {"type": "number", "minimum": 0, "maximum": 10},
              "methodological_rigor": {"type": "number", "minimum": 0, "maximum": 10},
              "composite_score": {"type": "number", "minimum": 0, "maximum": 10}
            }
          }
        }
      }
    },
    "excluded_papers": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["document_id", "title", "exclusion_stage", "exclusion_reasons"],
        "properties": {
          "document_id": {"type": "integer"},
          "title": {"type": "string"},
          "exclusion_stage": {
            "type": "string",
            "enum": ["initial_filter", "relevance_scoring", "inclusion_criteria", "exclusion_criteria", "quality_gate"]
          },
          "exclusion_reasons": {"type": "array", "items": {"type": "string"}},
          "exclusion_rationale": {"type": "string"}
        }
      }
    },
    "statistics": {
      "type": "object",
      "properties": {
        "total_considered": {"type": "integer"},
        "passed_initial_filter": {"type": "integer"},
        "passed_relevance_threshold": {"type": "integer"},
        "passed_quality_gate": {"type": "integer"},
        "final_included": {"type": "integer"},
        "final_excluded": {"type": "integer"},
        "processing_time_seconds": {"type": "number"}
      }
    }
  }
}
```

## Type Aliases

For convenience in type hints:

```python
from typing import TypeAlias

# Document identifiers
DocumentId: TypeAlias = int
QueryId: TypeAlias = str

# Score types
RelevanceScore: TypeAlias = float  # 1-5 scale
QualityScore: TypeAlias = float    # 0-10 scale
CompositeScore: TypeAlias = float  # 0-10 scale
Confidence: TypeAlias = float      # 0-1 scale

# Collections
DocumentIdSet: TypeAlias = set[DocumentId]
PaperList: TypeAlias = list[PaperData]
ScoredPaperList: TypeAlias = list[ScoredPaper]
```

## Validation Functions

```python
def validate_search_criteria(criteria: SearchCriteria) -> list[str]:
    """
    Validate search criteria, returning list of errors.

    Checks:
    - Research question is not empty
    - At least one inclusion criterion
    - Date range is valid (if provided)
    - Study types are valid (if provided)
    """
    errors = []

    if not criteria.research_question.strip():
        errors.append("Research question cannot be empty")

    if not criteria.inclusion_criteria:
        errors.append("At least one inclusion criterion is required")

    if criteria.date_range:
        start, end = criteria.date_range
        if start > end:
            errors.append(f"Invalid date range: {start} > {end}")
        if end > date.today().year:
            errors.append(f"End year {end} is in the future")

    return errors


def validate_scoring_weights(weights: ScoringWeights) -> list[str]:
    """
    Validate scoring weights, returning list of errors.

    Checks:
    - All weights are non-negative
    - Weights sum to approximately 1.0
    """
    errors = []

    weight_dict = weights.to_dict()
    for name, value in weight_dict.items():
        if value < 0:
            errors.append(f"Weight '{name}' cannot be negative: {value}")

    if not weights.validate():
        total = sum(weight_dict.values())
        errors.append(f"Weights must sum to 1.0, got {total:.3f}")

    return errors
```
