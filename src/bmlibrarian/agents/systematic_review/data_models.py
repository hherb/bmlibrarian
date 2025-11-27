"""
Data Models for SystematicReviewAgent

This module provides all the dataclasses and type definitions used by the
SystematicReviewAgent for systematic literature review workflows.

The models are organized into the following categories:
- Input Models: SearchCriteria, ScoringWeights
- Search Planning: PlannedQuery, SearchPlan, ExecutedQuery
- Paper Data: PaperData, InclusionDecision, ScoredPaper, AssessedPaper
- Process Documentation: ProcessStep, Checkpoint
- Output: ReviewStatistics, SystematicReviewResult

All models provide:
- Type hints for all attributes
- to_dict() methods for JSON serialization
- from_dict() class methods for deserialization
- Validation where appropriate
"""

from __future__ import annotations

import json
import uuid
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional, TypeAlias

logger = logging.getLogger(__name__)


# =============================================================================
# Type Aliases for Clear Intent
# =============================================================================

DocumentId: TypeAlias = int
QueryId: TypeAlias = str
RelevanceScore: TypeAlias = float  # 1-5 scale
QualityScore: TypeAlias = float    # 0-10 scale
CompositeScore: TypeAlias = float  # 0-10 scale
Confidence: TypeAlias = float      # 0-1 scale


# =============================================================================
# Constants
# =============================================================================

# Score validation ranges
MIN_RELEVANCE_SCORE = 1.0
MAX_RELEVANCE_SCORE = 5.0
MIN_QUALITY_SCORE = 0.0
MAX_QUALITY_SCORE = 10.0
MIN_CONFIDENCE = 0.0
MAX_CONFIDENCE = 1.0

# Weight validation
WEIGHT_SUM_EXPECTED = 1.0
WEIGHT_SUM_TOLERANCE = 0.01  # Allow for floating point precision issues

# Default limits
DEFAULT_MAX_RESULTS = 500

# Default scoring weights (balanced profile - sum to 1.0)
# These weights combine both Cochrane and BMLibrarian dimensions
DEFAULT_WEIGHT_RELEVANCE = 0.25
DEFAULT_WEIGHT_STUDY_QUALITY = 0.20
DEFAULT_WEIGHT_METHODOLOGICAL_RIGOR = 0.15
DEFAULT_WEIGHT_SAMPLE_SIZE = 0.05
DEFAULT_WEIGHT_RECENCY = 0.10
DEFAULT_WEIGHT_REPLICATION_STATUS = 0.05
DEFAULT_WEIGHT_PAPER_WEIGHT = 0.15
DEFAULT_WEIGHT_SOURCE_RELIABILITY = 0.05


# =============================================================================
# Enums
# =============================================================================

class StudyTypeFilter(Enum):
    """
    Allowed study types for filtering in systematic reviews.

    Based on evidence hierarchy commonly used in biomedical research.
    Values are lowercase strings for JSON serialization compatibility.
    """

    RCT = "rct"
    COHORT_PROSPECTIVE = "cohort_prospective"
    COHORT_RETROSPECTIVE = "cohort_retrospective"
    CASE_CONTROL = "case_control"
    CROSS_SECTIONAL = "cross_sectional"
    SYSTEMATIC_REVIEW = "systematic_review"
    META_ANALYSIS = "meta_analysis"
    CASE_SERIES = "case_series"
    CASE_REPORT = "case_report"
    QUASI_EXPERIMENTAL = "quasi_experimental"
    PILOT_FEASIBILITY = "pilot_feasibility"
    ANY = "any"

    @classmethod
    def from_string(cls, value: str) -> "StudyTypeFilter":
        """
        Create enum from string value.

        Args:
            value: String representation of study type

        Returns:
            Corresponding StudyTypeFilter enum

        Raises:
            ValueError: If value doesn't match any study type
        """
        value_lower = value.lower().strip()
        for member in cls:
            if member.value == value_lower:
                return member
        raise ValueError(f"Unknown study type: {value}")


class QueryType(Enum):
    """
    Type of search query for systematic review searches.

    Attributes:
        SEMANTIC: Embedding-based semantic similarity search
        KEYWORD: Traditional full-text keyword search
        HYBRID: Combined semantic and keyword search
        SQL: Generated PostgreSQL query via QueryAgent
        HYDE: Hypothetical Document Embeddings approach
    """

    SEMANTIC = "semantic"
    KEYWORD = "keyword"
    HYBRID = "hybrid"
    SQL = "sql"
    HYDE = "hyde"


class InclusionStatus(Enum):
    """
    Paper inclusion/exclusion status in systematic review.

    Attributes:
        INCLUDED: Paper meets all criteria and is included
        EXCLUDED: Paper fails one or more criteria
        UNCERTAIN: Borderline case requiring human review
    """

    INCLUDED = "included"
    EXCLUDED = "excluded"
    UNCERTAIN = "uncertain"


class ExclusionStage(Enum):
    """
    Stage at which a paper was excluded from the review.

    Tracks where in the workflow papers are filtered out
    for PRISMA flow diagram generation.
    """

    INITIAL_FILTER = "initial_filter"      # Fast heuristic filter
    RELEVANCE_SCORING = "relevance_scoring"  # LLM relevance check
    INCLUSION_CRITERIA = "inclusion_criteria"  # Failed inclusion
    EXCLUSION_CRITERIA = "exclusion_criteria"  # Matched exclusion
    QUALITY_GATE = "quality_gate"          # Below quality threshold
    MANUAL_REVIEW = "manual_review"        # Human excluded


# =============================================================================
# Input Models
# =============================================================================

@dataclass
class SearchCriteria:
    """
    Input specification for systematic review paper finding.

    This is the primary input the user provides to configure the search.
    Defines the research question, what papers to include/exclude, and
    search constraints.

    Attributes:
        research_question: The main research question to investigate
        purpose: Brief explanation of why this review is being conducted
        inclusion_criteria: List of criteria that papers MUST meet
        exclusion_criteria: List of criteria that DISQUALIFY papers
        target_study_types: Allowed study designs (None = all types)
        date_range: Optional (start_year, end_year) filter
        language: Language filter (default: English only)
        min_sample_size: Optional minimum sample size requirement
        max_results: Optional cap on total papers to include
        custom_search_terms: Optional additional search terms
        mesh_terms: Optional MeSH terms to include in search

    Example:
        >>> criteria = SearchCriteria(
        ...     research_question="What is the efficacy of statins for CVD prevention?",
        ...     purpose="Systematic review for clinical guidelines",
        ...     inclusion_criteria=["Human studies", "Statin intervention", "CVD outcomes"],
        ...     exclusion_criteria=["Animal studies", "Pediatric only", "Case reports"],
        ...     target_study_types=[StudyTypeFilter.RCT, StudyTypeFilter.META_ANALYSIS],
        ...     date_range=(2010, 2024)
        ... )
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
        """
        Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation suitable for JSON encoding
        """
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
            "date_range": list(self.date_range) if self.date_range else None,
            "language": self.language,
            "min_sample_size": self.min_sample_size,
            "max_results": self.max_results,
            "custom_search_terms": self.custom_search_terms,
            "mesh_terms": self.mesh_terms,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SearchCriteria":
        """
        Create SearchCriteria from dictionary.

        Args:
            data: Dictionary with SearchCriteria fields

        Returns:
            New SearchCriteria instance
        """
        # Convert study types from strings to enums
        study_types = None
        if data.get("target_study_types"):
            study_types = [
                StudyTypeFilter.from_string(st)
                for st in data["target_study_types"]
            ]

        # Convert date_range from list to tuple
        date_range = None
        if data.get("date_range"):
            date_range = tuple(data["date_range"])

        return cls(
            research_question=data["research_question"],
            purpose=data["purpose"],
            inclusion_criteria=data["inclusion_criteria"],
            exclusion_criteria=data.get("exclusion_criteria", []),
            target_study_types=study_types,
            date_range=date_range,
            language=data.get("language", "English"),
            min_sample_size=data.get("min_sample_size"),
            max_results=data.get("max_results"),
            custom_search_terms=data.get("custom_search_terms"),
            mesh_terms=data.get("mesh_terms"),
        )


@dataclass
class ScoringWeights:
    """
    User-configurable weights for composite score calculation.

    This comprehensive scoring system supports both:
    - **Cochrane-style systematic review dimensions**: methodological_rigor,
      sample_size, replication_status
    - **BMLibrarian practical evidence dimensions**: paper_weight,
      source_reliability

    Weights should sum to 1.0 for normalized scoring. The validate()
    method checks this constraint with tolerance for floating point precision.

    Users can choose which dimensions to emphasize based on their review type:
    - Formal systematic reviews may emphasize Cochrane dimensions
    - Practical evidence synthesis may emphasize paper_weight dimensions
    - Both can be combined for comprehensive assessment

    Attributes:
        relevance: Weight for relevance to research question (default: 0.25)
        study_quality: Weight for study design quality (default: 0.20)
        methodological_rigor: Weight for methodological quality (default: 0.15)
        sample_size: Weight for sample size adequacy (default: 0.05)
        recency: Weight for publication recency (default: 0.10)
        replication_status: Weight for replication evidence (default: 0.05)
        paper_weight: Weight for BMLibrarian paper weight assessment (default: 0.15)
        source_reliability: Weight for source/journal reliability (default: 0.05)

    Example:
        >>> # Cochrane-focused weights
        >>> weights = ScoringWeights(
        ...     relevance=0.30, methodological_rigor=0.25, sample_size=0.15,
        ...     paper_weight=0.0, source_reliability=0.0
        ... )
        >>> # BMLibrarian practical weights
        >>> weights = ScoringWeights(
        ...     relevance=0.30, paper_weight=0.25, source_reliability=0.10,
        ...     methodological_rigor=0.0, sample_size=0.0
        ... )
        >>> weights.validate()  # Returns False if weights don't sum to 1.0
    """

    relevance: float = DEFAULT_WEIGHT_RELEVANCE
    study_quality: float = DEFAULT_WEIGHT_STUDY_QUALITY
    methodological_rigor: float = DEFAULT_WEIGHT_METHODOLOGICAL_RIGOR
    sample_size: float = DEFAULT_WEIGHT_SAMPLE_SIZE
    recency: float = DEFAULT_WEIGHT_RECENCY
    replication_status: float = DEFAULT_WEIGHT_REPLICATION_STATUS
    paper_weight: float = DEFAULT_WEIGHT_PAPER_WEIGHT
    source_reliability: float = DEFAULT_WEIGHT_SOURCE_RELIABILITY

    def to_dict(self) -> Dict[str, float]:
        """
        Convert to dictionary for serialization.

        Returns:
            Dictionary with weight names and values
        """
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
    def from_dict(cls, data: Dict[str, float]) -> "ScoringWeights":
        """
        Create ScoringWeights from dictionary.

        Args:
            data: Dictionary with weight values

        Returns:
            New ScoringWeights instance
        """
        return cls(
            relevance=data.get("relevance", DEFAULT_WEIGHT_RELEVANCE),
            study_quality=data.get("study_quality", DEFAULT_WEIGHT_STUDY_QUALITY),
            methodological_rigor=data.get("methodological_rigor", DEFAULT_WEIGHT_METHODOLOGICAL_RIGOR),
            sample_size=data.get("sample_size", DEFAULT_WEIGHT_SAMPLE_SIZE),
            recency=data.get("recency", DEFAULT_WEIGHT_RECENCY),
            replication_status=data.get("replication_status", DEFAULT_WEIGHT_REPLICATION_STATUS),
            paper_weight=data.get("paper_weight", DEFAULT_WEIGHT_PAPER_WEIGHT),
            source_reliability=data.get("source_reliability", DEFAULT_WEIGHT_SOURCE_RELIABILITY),
        )

    @classmethod
    def cochrane_focused(cls) -> "ScoringWeights":
        """
        Create weights emphasizing Cochrane-style systematic review dimensions.

        Returns:
            ScoringWeights with Cochrane-focused distribution
        """
        return cls(
            relevance=0.30,
            study_quality=0.20,
            methodological_rigor=0.20,
            sample_size=0.10,
            recency=0.10,
            replication_status=0.10,
            paper_weight=0.0,
            source_reliability=0.0,
        )

    @classmethod
    def practical_focused(cls) -> "ScoringWeights":
        """
        Create weights emphasizing BMLibrarian practical evidence dimensions.

        Returns:
            ScoringWeights with practical-focused distribution
        """
        return cls(
            relevance=0.30,
            study_quality=0.25,
            methodological_rigor=0.0,
            sample_size=0.0,
            recency=0.10,
            replication_status=0.0,
            paper_weight=0.25,
            source_reliability=0.10,
        )

    def validate(self) -> bool:
        """
        Check that weights sum to approximately 1.0.

        Uses WEIGHT_SUM_TOLERANCE to allow for floating point precision issues
        that may occur during JSON serialization/deserialization.

        Returns:
            True if weights sum to 1.0 (within tolerance)
        """
        total = sum(self.to_dict().values())
        lower_bound = WEIGHT_SUM_EXPECTED - WEIGHT_SUM_TOLERANCE
        upper_bound = WEIGHT_SUM_EXPECTED + WEIGHT_SUM_TOLERANCE
        return lower_bound <= total <= upper_bound

    def get_validation_errors(self) -> List[str]:
        """
        Get list of validation errors for these weights.

        Returns:
            List of error messages, empty if valid
        """
        errors = []
        weight_dict = self.to_dict()

        # Check for negative weights
        for name, value in weight_dict.items():
            if value < 0:
                errors.append(f"Weight '{name}' cannot be negative: {value}")

        # Check sum
        if not self.validate():
            total = sum(weight_dict.values())
            errors.append(f"Weights must sum to 1.0, got {total:.4f}")

        return errors


# =============================================================================
# Search Planning Models
# =============================================================================

@dataclass
class PlannedQuery:
    """
    A single query in the search plan.

    Each query targets a specific aspect of the research question
    using a particular search strategy. The planner generates multiple
    queries to ensure comprehensive coverage.

    Attributes:
        query_id: Unique identifier for this query
        query_text: The actual query string
        query_type: Type of search to perform
        purpose: Why this query was generated
        expected_coverage: What aspect of the question it addresses
        priority: Execution priority (1 = highest)
        estimated_results: Expected number of results (for planning)

    Example:
        >>> query = PlannedQuery(
        ...     query_id="q1_semantic",
        ...     query_text="cardiovascular disease prevention statins",
        ...     query_type=QueryType.SEMANTIC,
        ...     purpose="Find papers about statin efficacy",
        ...     expected_coverage="Primary intervention studies"
        ... )
    """

    query_id: str
    query_text: str
    query_type: QueryType
    purpose: str
    expected_coverage: str
    priority: int = 1
    estimated_results: Optional[int] = None

    def __post_init__(self) -> None:
        """Generate query_id if not provided."""
        if not self.query_id:
            self.query_id = f"{self.query_type.value}_{uuid.uuid4().hex[:8]}"

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for serialization.

        Returns:
            Dictionary representation
        """
        return {
            "query_id": self.query_id,
            "query_text": self.query_text,
            "query_type": self.query_type.value,
            "purpose": self.purpose,
            "expected_coverage": self.expected_coverage,
            "priority": self.priority,
            "estimated_results": self.estimated_results,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlannedQuery":
        """
        Create PlannedQuery from dictionary.

        Args:
            data: Dictionary with query fields

        Returns:
            New PlannedQuery instance
        """
        return cls(
            query_id=data.get("query_id", ""),
            query_text=data["query_text"],
            query_type=QueryType(data["query_type"]),
            purpose=data["purpose"],
            expected_coverage=data["expected_coverage"],
            priority=data.get("priority", 1),
            estimated_results=data.get("estimated_results"),
        )


@dataclass
class SearchPlan:
    """
    Generated strategy for finding papers.

    Contains all planned queries and the rationale for the strategy.
    The planner generates this based on the research question and criteria.

    Attributes:
        queries: List of queries to execute
        total_estimated_yield: Expected total papers before deduplication
        search_rationale: LLM-generated explanation of the strategy
        iteration: Which iteration of planning this is (1 = initial)
        coverage_analysis: How well queries cover the research question

    Example:
        >>> plan = SearchPlan(
        ...     queries=[query1, query2, query3],
        ...     total_estimated_yield=500,
        ...     search_rationale="Using semantic search for broad coverage...",
        ...     iteration=1
        ... )
    """

    queries: List[PlannedQuery]
    total_estimated_yield: int
    search_rationale: str
    iteration: int = 1
    coverage_analysis: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for serialization.

        Returns:
            Dictionary representation
        """
        return {
            "queries": [q.to_dict() for q in self.queries],
            "total_estimated_yield": self.total_estimated_yield,
            "search_rationale": self.search_rationale,
            "iteration": self.iteration,
            "coverage_analysis": self.coverage_analysis,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SearchPlan":
        """
        Create SearchPlan from dictionary.

        Args:
            data: Dictionary with plan fields

        Returns:
            New SearchPlan instance
        """
        return cls(
            queries=[PlannedQuery.from_dict(q) for q in data["queries"]],
            total_estimated_yield=data["total_estimated_yield"],
            search_rationale=data["search_rationale"],
            iteration=data.get("iteration", 1),
            coverage_analysis=data.get("coverage_analysis"),
        )


@dataclass
class ExecutedQuery:
    """
    Result of executing a single query.

    Tracks what happened when the query was run, including
    timing, results count, and any errors.

    Attributes:
        planned_query: The original planned query
        document_ids: List of document IDs returned
        execution_time_seconds: How long the query took
        actual_results: Number of results returned
        error: Error message if query failed
        timestamp: When the query was executed (ISO format)
    """

    planned_query: PlannedQuery
    document_ids: List[int]
    execution_time_seconds: float
    actual_results: int
    error: Optional[str] = None
    timestamp: Optional[str] = None

    def __post_init__(self) -> None:
        """Set timestamp if not provided."""
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    @property
    def success(self) -> bool:
        """Check if query executed successfully."""
        return self.error is None

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for serialization.

        Returns:
            Dictionary representation
        """
        return {
            "planned_query": self.planned_query.to_dict(),
            "document_ids": self.document_ids,
            "execution_time_seconds": self.execution_time_seconds,
            "actual_results": self.actual_results,
            "error": self.error,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutedQuery":
        """
        Create ExecutedQuery from dictionary.

        Args:
            data: Dictionary with execution fields

        Returns:
            New ExecutedQuery instance
        """
        return cls(
            planned_query=PlannedQuery.from_dict(data["planned_query"]),
            document_ids=data["document_ids"],
            execution_time_seconds=data["execution_time_seconds"],
            actual_results=data["actual_results"],
            error=data.get("error"),
            timestamp=data.get("timestamp"),
        )


# =============================================================================
# Paper Data Models
# =============================================================================

@dataclass
class PaperData:
    """
    Core paper metadata from database.

    Represents a single paper with all its bibliographic information.
    This is the basic unit that flows through the review pipeline.

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
        """
        Convert to dictionary for serialization.

        Note: full_text is excluded to reduce size, represented by has_full_text flag.

        Returns:
            Dictionary representation
        """
        return {
            "document_id": self.document_id,
            "title": self.title,
            "authors": self.authors,
            "year": self.year,
            "journal": self.journal,
            "abstract": self.abstract,
            "doi": self.doi,
            "pmid": self.pmid,
            "pmc_id": self.pmc_id,
            "source": self.source,
            "has_full_text": self.full_text is not None,
            "has_pdf": self.pdf_path is not None,
        }

    def to_full_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary including full_text.

        Use when you need the complete data, not just metadata.

        Returns:
            Dictionary representation with full_text
        """
        data = self.to_dict()
        data["full_text"] = self.full_text
        data["pdf_path"] = self.pdf_path
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PaperData":
        """
        Create PaperData from dictionary.

        Args:
            data: Dictionary with paper fields

        Returns:
            New PaperData instance
        """
        return cls(
            document_id=data["document_id"],
            title=data["title"],
            authors=data.get("authors", []),
            year=data["year"],
            journal=data.get("journal"),
            abstract=data.get("abstract"),
            doi=data.get("doi"),
            pmid=data.get("pmid"),
            pmc_id=data.get("pmc_id"),
            full_text=data.get("full_text"),
            pdf_path=data.get("pdf_path"),
            source=data.get("source"),
        )

    @classmethod
    def from_database_row(cls, row: Dict[str, Any]) -> "PaperData":
        """
        Create PaperData from a database row.

        Handles column name mapping from database schema.

        Args:
            row: Database row as dictionary

        Returns:
            New PaperData instance
        """
        # Handle author parsing (may be string or list)
        authors = row.get("authors", [])
        if isinstance(authors, str):
            # Try to parse as JSON list
            try:
                authors = json.loads(authors)
            except (json.JSONDecodeError, TypeError):
                # Fall back to simple split
                authors = [a.strip() for a in authors.split(",") if a.strip()]

        return cls(
            document_id=row.get("id") or row.get("document_id"),
            title=row.get("title", ""),
            authors=authors,
            year=row.get("year") or row.get("publication_year", 0),
            journal=row.get("journal") or row.get("journal_name"),
            abstract=row.get("abstract"),
            doi=row.get("doi"),
            pmid=row.get("pmid"),
            pmc_id=row.get("pmc_id") or row.get("pmcid"),
            full_text=row.get("full_text") or row.get("fulltext"),
            pdf_path=row.get("pdf_path") or row.get("local_pdf_path"),
            source=row.get("source") or row.get("data_source"),
        )


@dataclass
class InclusionDecision:
    """
    Decision on whether to include a paper.

    All decisions include rationale for audit trail. This enables
    complete transparency in the review process.

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
        """
        Convert to dictionary for serialization.

        Returns:
            Dictionary representation
        """
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

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InclusionDecision":
        """
        Create InclusionDecision from dictionary.

        Args:
            data: Dictionary with decision fields

        Returns:
            New InclusionDecision instance
        """
        return cls(
            status=InclusionStatus(data["status"]),
            stage=ExclusionStage(data["stage"]),
            reasons=data["reasons"],
            rationale=data["rationale"],
            confidence=data.get("confidence", 1.0),
            criteria_matched=data.get("criteria_matched"),
            criteria_failed=data.get("criteria_failed"),
            exclusion_matched=data.get("exclusion_matched"),
        )

    @classmethod
    def create_excluded(
        cls,
        stage: ExclusionStage,
        reasons: List[str],
        rationale: str,
        confidence: float = 1.0,
        exclusion_matched: Optional[List[str]] = None,
    ) -> "InclusionDecision":
        """
        Factory method for creating exclusion decisions.

        Args:
            stage: Stage at which paper was excluded
            reasons: Reasons for exclusion
            rationale: Explanation of decision
            confidence: Confidence level
            exclusion_matched: Specific exclusion criteria matched

        Returns:
            New InclusionDecision with EXCLUDED status
        """
        return cls(
            status=InclusionStatus.EXCLUDED,
            stage=stage,
            reasons=reasons,
            rationale=rationale,
            confidence=confidence,
            exclusion_matched=exclusion_matched,
        )

    @classmethod
    def create_included(
        cls,
        stage: ExclusionStage,
        rationale: str,
        criteria_matched: List[str],
        confidence: float = 1.0,
    ) -> "InclusionDecision":
        """
        Factory method for creating inclusion decisions.

        Args:
            stage: Stage at which decision was made
            rationale: Explanation of decision
            criteria_matched: Inclusion criteria that were met
            confidence: Confidence level

        Returns:
            New InclusionDecision with INCLUDED status
        """
        return cls(
            status=InclusionStatus.INCLUDED,
            stage=stage,
            reasons=["Meets all inclusion criteria"],
            rationale=rationale,
            confidence=confidence,
            criteria_matched=criteria_matched,
        )


@dataclass
class ScoredPaper:
    """
    Paper with relevance scoring applied.

    Represents a paper after the scoring phase, containing both
    the paper data and relevance assessment.

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
        """Check if paper is included in the review."""
        return self.inclusion_decision.status == InclusionStatus.INCLUDED

    @property
    def is_excluded(self) -> bool:
        """Check if paper is excluded from the review."""
        return self.inclusion_decision.status == InclusionStatus.EXCLUDED

    @property
    def needs_review(self) -> bool:
        """Check if paper needs human review."""
        return self.inclusion_decision.status == InclusionStatus.UNCERTAIN

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for serialization.

        Returns:
            Dictionary representation
        """
        return {
            "paper": self.paper.to_dict(),
            "relevance_score": self.relevance_score,
            "relevance_rationale": self.relevance_rationale,
            "inclusion_decision": self.inclusion_decision.to_dict(),
            "relevant_citations": self.relevant_citations,
            "search_provenance": self.search_provenance,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScoredPaper":
        """
        Create ScoredPaper from dictionary.

        Args:
            data: Dictionary with scored paper fields

        Returns:
            New ScoredPaper instance
        """
        return cls(
            paper=PaperData.from_dict(data["paper"]),
            relevance_score=data["relevance_score"],
            relevance_rationale=data["relevance_rationale"],
            inclusion_decision=InclusionDecision.from_dict(data["inclusion_decision"]),
            relevant_citations=data.get("relevant_citations"),
            search_provenance=data.get("search_provenance"),
        )


@dataclass
class AssessedPaper:
    """
    Paper with full quality assessment.

    This is the final form of a paper after all evaluations including
    study quality, methodological rigor, and optional PICO/PRISMA.

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

    @property
    def document_id(self) -> int:
        """Get the document ID for convenience."""
        return self.scored_paper.paper.document_id

    @property
    def title(self) -> str:
        """Get the title for convenience."""
        return self.scored_paper.paper.title

    @property
    def is_included(self) -> bool:
        """Check if paper is included."""
        return self.scored_paper.is_included

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for serialization.

        Returns:
            Dictionary representation
        """
        return {
            "scored_paper": self.scored_paper.to_dict(),
            "study_assessment": self.study_assessment,
            "paper_weight": self.paper_weight,
            "pico_components": self.pico_components,
            "prisma_assessment": self.prisma_assessment,
            "composite_score": self.composite_score,
            "final_rank": self.final_rank,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AssessedPaper":
        """
        Create AssessedPaper from dictionary.

        Args:
            data: Dictionary with assessed paper fields

        Returns:
            New AssessedPaper instance
        """
        return cls(
            scored_paper=ScoredPaper.from_dict(data["scored_paper"]),
            study_assessment=data["study_assessment"],
            paper_weight=data["paper_weight"],
            pico_components=data.get("pico_components"),
            prisma_assessment=data.get("prisma_assessment"),
            composite_score=data.get("composite_score"),
            final_rank=data.get("final_rank"),
        )


# =============================================================================
# Process Documentation Models
# =============================================================================

@dataclass
class ProcessStep:
    """
    Documentation of a single step in the process.

    Every action is logged for complete audit trail, enabling
    reproducibility and transparency.

    Attributes:
        step_number: Sequential step number
        action: What action was performed
        tool_used: Which tool/agent was invoked
        input_summary: Summary of inputs
        output_summary: Summary of outputs
        decision_rationale: Why this action was taken
        timestamp: When the step occurred (ISO format)
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

    @property
    def success(self) -> bool:
        """Check if step completed successfully."""
        return self.error is None

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for serialization.

        Returns:
            Dictionary representation
        """
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

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProcessStep":
        """
        Create ProcessStep from dictionary.

        Args:
            data: Dictionary with step fields

        Returns:
            New ProcessStep instance
        """
        return cls(
            step_number=data["step_number"],
            action=data["action"],
            tool_used=data.get("tool_used"),
            input_summary=data["input_summary"],
            output_summary=data["output_summary"],
            decision_rationale=data["decision_rationale"],
            timestamp=data["timestamp"],
            duration_seconds=data["duration_seconds"],
            metrics=data.get("metrics", {}),
            error=data.get("error"),
        )


@dataclass
class Checkpoint:
    """
    Checkpoint for workflow resumability.

    Allows the review to be paused and resumed at key decision points.
    Stores complete state for recovery.

    Attributes:
        checkpoint_id: Unique identifier
        checkpoint_type: Type of checkpoint (e.g., "search_strategy", "scoring")
        timestamp: When checkpoint was created (ISO format)
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

    def __post_init__(self) -> None:
        """Generate checkpoint_id if not provided."""
        if not self.checkpoint_id:
            self.checkpoint_id = f"cp_{uuid.uuid4().hex[:12]}"

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for serialization.

        Note: state_snapshot is excluded for size in summary views.

        Returns:
            Dictionary representation (without state_snapshot)
        """
        return {
            "checkpoint_id": self.checkpoint_id,
            "checkpoint_type": self.checkpoint_type,
            "timestamp": self.timestamp,
            "phase": self.phase,
            "user_decision": self.user_decision,
            "notes": self.notes,
            # state_snapshot excluded for size
        }

    def to_full_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary including state_snapshot.

        Use when saving checkpoint for resumability.

        Returns:
            Full dictionary representation
        """
        data = self.to_dict()
        data["state_snapshot"] = self.state_snapshot
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Checkpoint":
        """
        Create Checkpoint from dictionary.

        Args:
            data: Dictionary with checkpoint fields

        Returns:
            New Checkpoint instance
        """
        return cls(
            checkpoint_id=data.get("checkpoint_id", ""),
            checkpoint_type=data["checkpoint_type"],
            timestamp=data["timestamp"],
            phase=data["phase"],
            state_snapshot=data.get("state_snapshot", {}),
            user_decision=data.get("user_decision"),
            notes=data.get("notes"),
        )


# =============================================================================
# Output Models
# =============================================================================

@dataclass
class ReviewStatistics:
    """
    Summary statistics for the review.

    Provides quantitative overview of the review process,
    useful for PRISMA flow diagrams and quality assessment.

    Attributes:
        total_considered: Total papers found before filtering
        passed_initial_filter: Papers passing fast heuristic filter
        passed_relevance_threshold: Papers meeting relevance score
        passed_quality_gate: Papers meeting quality threshold
        final_included: Final included paper count
        final_excluded: Final excluded paper count
        uncertain_for_review: Papers needing human review
        processing_time_seconds: Total processing time
        total_llm_calls: Number of LLM API calls made
        total_tokens_used: Total tokens consumed
    """

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
        """
        Convert to dictionary for serialization.

        Returns:
            Dictionary representation
        """
        return {
            "total_considered": self.total_considered,
            "passed_initial_filter": self.passed_initial_filter,
            "passed_relevance_threshold": self.passed_relevance_threshold,
            "passed_quality_gate": self.passed_quality_gate,
            "final_included": self.final_included,
            "final_excluded": self.final_excluded,
            "uncertain_for_review": self.uncertain_for_review,
            "processing_time_seconds": round(self.processing_time_seconds, 2),
            "total_llm_calls": self.total_llm_calls,
            "total_tokens_used": self.total_tokens_used,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReviewStatistics":
        """
        Create ReviewStatistics from dictionary.

        Args:
            data: Dictionary with statistics fields

        Returns:
            New ReviewStatistics instance
        """
        return cls(
            total_considered=data["total_considered"],
            passed_initial_filter=data["passed_initial_filter"],
            passed_relevance_threshold=data["passed_relevance_threshold"],
            passed_quality_gate=data["passed_quality_gate"],
            final_included=data["final_included"],
            final_excluded=data["final_excluded"],
            uncertain_for_review=data.get("uncertain_for_review", 0),
            processing_time_seconds=data["processing_time_seconds"],
            total_llm_calls=data.get("total_llm_calls", 0),
            total_tokens_used=data.get("total_tokens_used", 0),
        )

    @classmethod
    def create_empty(cls) -> "ReviewStatistics":
        """
        Create empty statistics object.

        Useful for initializing before processing begins.

        Returns:
            New ReviewStatistics with all zeros
        """
        return cls(
            total_considered=0,
            passed_initial_filter=0,
            passed_relevance_threshold=0,
            passed_quality_gate=0,
            final_included=0,
            final_excluded=0,
            uncertain_for_review=0,
            processing_time_seconds=0.0,
            total_llm_calls=0,
            total_tokens_used=0,
        )


@dataclass
class SystematicReviewResult:
    """
    Complete output of the systematic review.

    This is the final JSON output file containing all results,
    process documentation, and statistics.

    Attributes:
        metadata: Review metadata and configuration
        search_strategy: Search plan and execution details
        scoring_config: Weights used for scoring
        included_papers: Papers that passed all criteria
        excluded_papers: Papers that were rejected (with reasons)
        uncertain_papers: Papers needing human review
        process_log: Complete audit trail
        statistics: Summary statistics

    Example:
        >>> result = SystematicReviewResult(...)
        >>> result.save("/path/to/output.json")
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
        """
        Convert to dictionary for serialization.

        Returns:
            Dictionary representation
        """
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

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SystematicReviewResult":
        """
        Create SystematicReviewResult from dictionary.

        Args:
            data: Dictionary with result fields

        Returns:
            New SystematicReviewResult instance
        """
        return cls(
            metadata=data["metadata"],
            search_strategy=data["search_strategy"],
            scoring_config=data["scoring_config"],
            included_papers=data["included_papers"],
            excluded_papers=data["excluded_papers"],
            uncertain_papers=data.get("uncertain_papers", []),
            process_log=data["process_log"],
            statistics=ReviewStatistics.from_dict(data["statistics"]),
        )

    def to_json(self, indent: int = 2) -> str:
        """
        Serialize to JSON string.

        Args:
            indent: Indentation level for pretty printing

        Returns:
            JSON string representation
        """
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def save(self, path: str) -> None:
        """
        Save to JSON file.

        Args:
            path: Output file path
        """
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json())
        logger.info(f"Saved systematic review results to: {path}")

    @classmethod
    def load(cls, path: str) -> "SystematicReviewResult":
        """
        Load from JSON file.

        Args:
            path: Input file path

        Returns:
            Loaded SystematicReviewResult instance
        """
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)


# =============================================================================
# Validation Functions
# =============================================================================

def validate_search_criteria(criteria: SearchCriteria) -> List[str]:
    """
    Validate search criteria, returning list of errors.

    Checks:
    - Research question is not empty
    - At least one inclusion criterion
    - Date range is valid (if provided)
    - Study types are valid (if provided)

    Args:
        criteria: SearchCriteria to validate

    Returns:
        List of error messages, empty if valid
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
        if start < 1900:
            errors.append(f"Start year {start} is unrealistically early")

    if criteria.min_sample_size is not None and criteria.min_sample_size < 0:
        errors.append(f"Minimum sample size cannot be negative: {criteria.min_sample_size}")

    if criteria.max_results is not None and criteria.max_results < 1:
        errors.append(f"Maximum results must be at least 1: {criteria.max_results}")

    return errors


def validate_scoring_weights(weights: ScoringWeights) -> List[str]:
    """
    Validate scoring weights, returning list of errors.

    Checks:
    - All weights are non-negative
    - Weights sum to approximately 1.0

    Args:
        weights: ScoringWeights to validate

    Returns:
        List of error messages, empty if valid
    """
    return weights.get_validation_errors()
