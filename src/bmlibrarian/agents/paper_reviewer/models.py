"""
Paper Reviewer Data Models

This module contains the dataclasses for representing paper review results:
- PaperReviewResult: Complete review with all assessments
- ContradictoryPaper: Paper potentially contradicting the hypothesis
- StudyTypeResult: Study type detection results
- ReviewStep: Workflow step tracking
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any, TYPE_CHECKING
import json

from .constants import VERSION, DATETIME_FORMAT

if TYPE_CHECKING:
    from ..pico_agent import PICOExtraction
    from ..prisma2020_agent import PRISMA2020Assessment
    from ..paper_weight.models import PaperWeightResult
    from ..study_assessment_agent import StudyAssessment


class ReviewStepStatus(Enum):
    """Status of a review workflow step."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


class SourceType(Enum):
    """Source type for the input document."""
    DATABASE = "database"
    DOI_FETCH = "doi_fetch"
    PMID_FETCH = "pmid_fetch"
    PDF = "pdf"
    TEXT = "text"
    FILE = "file"


class SearchMethod(Enum):
    """Search method used to find contradictory papers."""
    SEMANTIC = "semantic"
    HYDE = "hyde"
    KEYWORD = "keyword"
    PUBMED = "pubmed"


class SearchSource(Enum):
    """Source of search results."""
    LOCAL = "local"
    EXTERNAL = "external"


@dataclass
class ReviewStep:
    """
    Represents a single step in the review workflow.

    Used for tracking progress and providing feedback to the UI.
    """
    name: str
    display_name: str
    status: ReviewStepStatus = ReviewStepStatus.PENDING
    progress: float = 0.0  # 0.0 to 1.0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    result_summary: Optional[str] = None
    result_data: Optional[Dict[str, Any]] = None

    def start(self) -> None:
        """Mark step as started."""
        self.status = ReviewStepStatus.IN_PROGRESS
        self.started_at = datetime.now(timezone.utc)
        self.progress = 0.0

    def complete(self, summary: Optional[str] = None, data: Optional[Dict] = None) -> None:
        """Mark step as completed."""
        self.status = ReviewStepStatus.COMPLETED
        self.completed_at = datetime.now(timezone.utc)
        self.progress = 1.0
        self.result_summary = summary
        self.result_data = data

    def skip(self, reason: str) -> None:
        """Mark step as skipped."""
        self.status = ReviewStepStatus.SKIPPED
        self.completed_at = datetime.now(timezone.utc)
        self.result_summary = reason

    def fail(self, error: str) -> None:
        """Mark step as failed."""
        self.status = ReviewStepStatus.FAILED
        self.completed_at = datetime.now(timezone.utc)
        self.error_message = error

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate step duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'name': self.name,
            'display_name': self.display_name,
            'status': self.status.value,
            'progress': self.progress,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'duration_seconds': self.duration_seconds,
            'error_message': self.error_message,
            'result_summary': self.result_summary,
        }


@dataclass
class StudyTypeResult:
    """
    Result of study type detection.

    Determines which assessments (PICO, PRISMA) are applicable.
    """
    study_type: str  # e.g., "RCT", "systematic review", "cohort study"
    study_type_detailed: str  # More detailed description
    is_clinical_study: bool  # Intervention study → PICO applicable
    is_systematic_review: bool  # → PRISMA applicable
    is_meta_analysis: bool  # → PRISMA applicable
    is_observational: bool  # Cohort, case-control, etc.
    is_case_report: bool  # Case report/series
    is_laboratory: bool  # In vitro, animal study
    confidence: float  # 0-1
    rationale: str  # Explanation for classification

    @property
    def pico_applicable(self) -> bool:
        """Check if PICO extraction is applicable."""
        return self.is_clinical_study

    @property
    def prisma_applicable(self) -> bool:
        """Check if PRISMA assessment is applicable."""
        return self.is_systematic_review or self.is_meta_analysis

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'study_type': self.study_type,
            'study_type_detailed': self.study_type_detailed,
            'is_clinical_study': self.is_clinical_study,
            'is_systematic_review': self.is_systematic_review,
            'is_meta_analysis': self.is_meta_analysis,
            'is_observational': self.is_observational,
            'is_case_report': self.is_case_report,
            'is_laboratory': self.is_laboratory,
            'confidence': self.confidence,
            'rationale': self.rationale,
            'pico_applicable': self.pico_applicable,
            'prisma_applicable': self.prisma_applicable,
        }


@dataclass
class ContradictoryPaper:
    """
    Paper potentially contradicting the reviewed paper's hypothesis.

    Found through semantic, HyDE, keyword, or PubMed search.
    """
    # Identifiers
    document_id: Optional[int]  # Local database ID if available
    pmid: Optional[str]
    doi: Optional[str]

    # Metadata
    title: str
    authors: List[str]
    year: Optional[int]
    journal: Optional[str]
    abstract: str

    # Search and relevance
    relevance_score: float  # 0-1, relevance to counter-statement
    search_method: SearchMethod
    source: SearchSource

    # Evidence
    contradictory_excerpt: Optional[str] = None  # Key text that contradicts
    contradiction_explanation: Optional[str] = None  # Why this contradicts

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'document_id': self.document_id,
            'pmid': self.pmid,
            'doi': self.doi,
            'title': self.title,
            'authors': self.authors,
            'year': self.year,
            'journal': self.journal,
            'abstract': self.abstract,
            'relevance_score': self.relevance_score,
            'search_method': self.search_method.value,
            'source': self.source.value,
            'contradictory_excerpt': self.contradictory_excerpt,
            'contradiction_explanation': self.contradiction_explanation,
        }

    @property
    def formatted_citation(self) -> str:
        """Format as citation string."""
        authors_str = ", ".join(self.authors[:3])
        if len(self.authors) > 3:
            authors_str += " et al."
        year_str = f" ({self.year})" if self.year else ""
        return f"{authors_str}{year_str}. {self.title}"


@dataclass
class PaperReviewResult:
    """
    Complete paper review result with all assessments.

    This is the main output of the PaperReviewerAgent.
    """

    # Input metadata
    document_id: Optional[int]
    doi: Optional[str]
    pmid: Optional[str]
    title: str
    authors: List[str]
    year: Optional[int]
    journal: Optional[str]
    source_type: SourceType

    # Summary
    brief_summary: str  # 2-3 sentences
    summary_confidence: float

    # Core statement
    core_hypothesis: str
    hypothesis_confidence: float

    # Study type detection
    study_type_result: StudyTypeResult

    # PICO (if applicable) - using forward reference
    pico_extraction: Optional[Any] = None  # PICOExtraction
    pico_applicable: bool = False

    # PRISMA (if applicable) - using forward reference
    prisma_assessment: Optional[Any] = None  # PRISMA2020Assessment
    prisma_applicable: bool = False

    # Paper Weight Assessment - using forward reference
    paper_weight: Optional[Any] = None  # PaperWeightResult

    # Study Assessment - using forward reference
    study_assessment: Optional[Any] = None  # StudyAssessment

    # Synthesized strengths/weaknesses
    strengths_summary: List[str] = field(default_factory=list)
    weaknesses_summary: List[str] = field(default_factory=list)

    # Contradictory evidence
    counter_statement: str = ""
    contradictory_papers: List[ContradictoryPaper] = field(default_factory=list)
    search_sources_used: List[str] = field(default_factory=list)

    # Workflow tracking
    steps: List[ReviewStep] = field(default_factory=list)

    # Metadata
    reviewed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    reviewer_version: str = VERSION
    total_processing_time_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            # Input metadata
            'document_id': self.document_id,
            'doi': self.doi,
            'pmid': self.pmid,
            'title': self.title,
            'authors': self.authors,
            'year': self.year,
            'journal': self.journal,
            'source_type': self.source_type.value,

            # Summary
            'brief_summary': self.brief_summary,
            'summary_confidence': self.summary_confidence,

            # Hypothesis
            'core_hypothesis': self.core_hypothesis,
            'hypothesis_confidence': self.hypothesis_confidence,

            # Study type
            'study_type_result': self.study_type_result.to_dict(),

            # PICO
            'pico_applicable': self.pico_applicable,
            'pico_extraction': self.pico_extraction.to_dict() if self.pico_extraction else None,

            # PRISMA
            'prisma_applicable': self.prisma_applicable,
            'prisma_assessment': self.prisma_assessment.to_dict() if self.prisma_assessment else None,

            # Paper Weight
            'paper_weight': self.paper_weight.to_dict() if self.paper_weight else None,

            # Study Assessment
            'study_assessment': self.study_assessment.to_dict() if self.study_assessment else None,

            # Strengths/Weaknesses
            'strengths_summary': self.strengths_summary,
            'weaknesses_summary': self.weaknesses_summary,

            # Contradictory evidence
            'counter_statement': self.counter_statement,
            'contradictory_papers': [p.to_dict() for p in self.contradictory_papers],
            'search_sources_used': self.search_sources_used,

            # Workflow
            'steps': [s.to_dict() for s in self.steps],

            # Metadata
            'reviewed_at': self.reviewed_at.isoformat(),
            'reviewer_version': self.reviewer_version,
            'total_processing_time_seconds': self.total_processing_time_seconds,
        }
        return result

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_markdown(self) -> str:
        """
        Format review as comprehensive Markdown report.

        Returns:
            Markdown-formatted review report
        """
        lines = [
            "# Paper Review Report",
            "",
            f"**Reviewed:** {self.reviewed_at.strftime(DATETIME_FORMAT)}",
            f"**Reviewer Version:** {self.reviewer_version}",
            f"**Processing Time:** {self.total_processing_time_seconds:.1f} seconds",
            "",
            "---",
            "",
            "## Paper Information",
            "",
            f"**Title:** {self.title}",
            f"**Authors:** {', '.join(self.authors[:5])}" + (" et al." if len(self.authors) > 5 else ""),
        ]

        if self.year:
            lines.append(f"**Year:** {self.year}")
        if self.journal:
            lines.append(f"**Journal:** {self.journal}")
        if self.doi:
            lines.append(f"**DOI:** {self.doi}")
        if self.pmid:
            lines.append(f"**PMID:** {self.pmid}")

        lines.extend([
            "",
            "---",
            "",
            "## Summary",
            "",
            self.brief_summary,
            "",
            "---",
            "",
            "## Core Hypothesis",
            "",
            f"> {self.core_hypothesis}",
            "",
            f"*Confidence: {self.hypothesis_confidence:.0%}*",
            "",
            "---",
            "",
            "## Study Classification",
            "",
            f"**Study Type:** {self.study_type_result.study_type}",
            f"**Detailed:** {self.study_type_result.study_type_detailed}",
            "",
            f"**Classification Confidence:** {self.study_type_result.confidence:.0%}",
            "",
            f"*{self.study_type_result.rationale}*",
            "",
        ])

        # PICO section
        if self.pico_applicable and self.pico_extraction:
            lines.extend([
                "---",
                "",
                "## PICO Analysis",
                "",
                f"**Population:** {self.pico_extraction.population}",
                "",
                f"**Intervention:** {self.pico_extraction.intervention}",
                "",
                f"**Comparison:** {self.pico_extraction.comparison}",
                "",
                f"**Outcome:** {self.pico_extraction.outcome}",
                "",
            ])
        elif self.pico_applicable:
            lines.extend([
                "---",
                "",
                "## PICO Analysis",
                "",
                "*PICO extraction was applicable but could not be completed.*",
                "",
            ])

        # PRISMA section
        if self.prisma_applicable and self.prisma_assessment:
            lines.extend([
                "---",
                "",
                "## PRISMA 2020 Assessment",
                "",
                f"**Overall Compliance:** {getattr(self.prisma_assessment, 'overall_score', 'N/A')}",
                "",
            ])
        elif self.prisma_applicable:
            lines.extend([
                "---",
                "",
                "## PRISMA 2020 Assessment",
                "",
                "*PRISMA assessment was applicable but could not be completed.*",
                "",
            ])

        # Paper Weight section
        if self.paper_weight:
            lines.extend([
                "---",
                "",
                "## Paper Weight Assessment",
                "",
                f"**Final Weight:** {self.paper_weight.final_weight:.2f}/10",
                "",
                "| Dimension | Score |",
                "|-----------|-------|",
                f"| Study Design | {self.paper_weight.study_design.score:.1f}/10 |",
                f"| Sample Size | {self.paper_weight.sample_size.score:.1f}/10 |",
                f"| Methodological Quality | {self.paper_weight.methodological_quality.score:.1f}/10 |",
                f"| Risk of Bias | {self.paper_weight.risk_of_bias.score:.1f}/10 |",
                f"| Replication Status | {self.paper_weight.replication_status.score:.1f}/10 |",
                "",
            ])

        # Study Assessment section
        if self.study_assessment:
            lines.extend([
                "---",
                "",
                "## Study Quality Assessment",
                "",
                f"**Quality Score:** {self.study_assessment.quality_score:.1f}/10",
                f"**Evidence Level:** {self.study_assessment.evidence_level}",
                f"**Overall Confidence:** {self.study_assessment.overall_confidence:.0%}",
                "",
                f"*{self.study_assessment.confidence_explanation}*",
                "",
            ])

        # Strengths and Weaknesses
        lines.extend([
            "---",
            "",
            "## Strengths and Weaknesses",
            "",
            "### Strengths",
            "",
        ])
        for strength in self.strengths_summary:
            lines.append(f"- {strength}")

        lines.extend([
            "",
            "### Weaknesses",
            "",
        ])
        for weakness in self.weaknesses_summary:
            lines.append(f"- {weakness}")

        # Contradictory Evidence
        lines.extend([
            "",
            "---",
            "",
            "## Contradictory Evidence Search",
            "",
            "### Counter-Statement",
            "",
            f"> {self.counter_statement}",
            "",
            f"**Search Sources:** {', '.join(self.search_sources_used)}",
            "",
        ])

        if self.contradictory_papers:
            lines.extend([
                "### Potentially Contradicting Papers",
                "",
            ])
            for i, paper in enumerate(self.contradictory_papers[:10], 1):
                lines.extend([
                    f"#### {i}. {paper.title}",
                    "",
                    f"**Authors:** {', '.join(paper.authors[:3])}" + (" et al." if len(paper.authors) > 3 else ""),
                    f"**Year:** {paper.year or 'N/A'}",
                    f"**Relevance Score:** {paper.relevance_score:.0%}",
                    f"**Found via:** {paper.search_method.value} ({paper.source.value})",
                    "",
                ])
                if paper.contradictory_excerpt:
                    lines.extend([
                        "**Contradictory Evidence:**",
                        f"> {paper.contradictory_excerpt}",
                        "",
                    ])
                    if paper.contradiction_explanation:
                        lines.append(f"*{paper.contradiction_explanation}*")
                else:
                    # No contradictory evidence found in this paper
                    lines.append("**Contradictory Evidence:** *No contradictory evidence found in this paper*")
                    if paper.contradiction_explanation:
                        lines.append(f"*Reason: {paper.contradiction_explanation}*")
                lines.append("")
        else:
            lines.append("*No contradicting papers found in the search.*")
            lines.append("")

        # Workflow summary
        lines.extend([
            "---",
            "",
            "## Processing Summary",
            "",
            "| Step | Status | Duration |",
            "|------|--------|----------|",
        ])
        for step in self.steps:
            duration = f"{step.duration_seconds:.1f}s" if step.duration_seconds else "-"
            lines.append(f"| {step.display_name} | {step.status.value} | {duration} |")

        lines.append("")

        return "\n".join(lines)


# Workflow step definitions
REVIEW_STEPS = [
    ("resolve_input", "Resolving Input"),
    ("generate_summary", "Generating Summary"),
    ("extract_hypothesis", "Extracting Hypothesis"),
    ("detect_study_type", "Detecting Study Type"),
    ("pico_assessment", "PICO Analysis"),
    ("prisma_assessment", "PRISMA Assessment"),
    ("paper_weight", "Paper Weight Assessment"),
    ("study_assessment", "Study Quality Assessment"),
    ("synthesize_strengths", "Synthesizing Strengths/Weaknesses"),
    ("search_contradictory", "Searching for Contradictory Evidence"),
    ("compile_report", "Compiling Final Report"),
]


def create_review_steps() -> List[ReviewStep]:
    """Create a fresh list of review steps in pending state."""
    return [ReviewStep(name=name, display_name=display) for name, display in REVIEW_STEPS]


__all__ = [
    'ReviewStepStatus',
    'SourceType',
    'SearchMethod',
    'SearchSource',
    'ReviewStep',
    'StudyTypeResult',
    'ContradictoryPaper',
    'PaperReviewResult',
    'REVIEW_STEPS',
    'create_review_steps',
    'VERSION',
]
