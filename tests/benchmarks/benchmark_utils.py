"""
Benchmark Utilities for SystematicReviewAgent Validation

Provides data models and utilities for comparing the agent's output
against published systematic reviews (ground truth).

Key Components:
- GroundTruthPaper: Single paper from a Cochrane review's reference list
- CochraneGroundTruth: Complete ground truth dataset from a Cochrane review
- BenchmarkResult: Results of comparing agent output against ground truth
- Matching utilities: PMID, DOI, and fuzzy title matching

Target Metric:
- 100% recall: Every paper cited in the Cochrane review must be found
  and scored as relevant by our agent (be in included_papers list)
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Minimum title similarity threshold for fuzzy matching (0-1 scale)
# 0.85 allows for minor variations in formatting, abbreviations
MIN_TITLE_SIMILARITY_THRESHOLD = 0.85

# Target recall rate (100% - all Cochrane papers must be found)
TARGET_RECALL_RATE = 1.0

# Minimum acceptable precision rate
MIN_ACCEPTABLE_PRECISION_RATE = 0.60


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class GroundTruthPaper:
    """
    Single paper from a Cochrane review's reference list.

    Represents one study that the Cochrane review included.
    Used as ground truth for validation.

    Attributes:
        pmid: PubMed ID (primary identifier for matching)
        doi: Digital Object Identifier (secondary identifier)
        title: Paper title (fallback for fuzzy matching)
        authors: List of author names (optional, for display)
        year: Publication year (optional, for display)
        cochrane_ref_id: Reference ID within the Cochrane review
        notes: Any notes about this paper (e.g., why it was included)
    """

    pmid: Optional[str] = None
    doi: Optional[str] = None
    title: Optional[str] = None
    authors: Optional[List[str]] = None
    year: Optional[int] = None
    cochrane_ref_id: Optional[str] = None
    notes: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate that at least one identifier is present."""
        if not self.pmid and not self.doi and not self.title:
            raise ValueError(
                "GroundTruthPaper must have at least one identifier "
                "(pmid, doi, or title)"
            )
        # Normalize DOI to lowercase
        if self.doi:
            self.doi = self.doi.lower().strip()
        # Normalize PMID (remove leading zeros, whitespace)
        if self.pmid:
            self.pmid = str(self.pmid).strip().lstrip("0") or "0"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "pmid": self.pmid,
            "doi": self.doi,
            "title": self.title,
            "authors": self.authors,
            "year": self.year,
            "cochrane_ref_id": self.cochrane_ref_id,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GroundTruthPaper":
        """Create from dictionary."""
        return cls(
            pmid=data.get("pmid"),
            doi=data.get("doi"),
            title=data.get("title"),
            authors=data.get("authors"),
            year=data.get("year"),
            cochrane_ref_id=data.get("cochrane_ref_id"),
            notes=data.get("notes"),
        )

    def get_display_name(self) -> str:
        """Get a human-readable name for this paper."""
        if self.title:
            short_title = self.title[:60] + "..." if len(self.title) > 60 else self.title
            return short_title
        if self.pmid:
            return f"PMID:{self.pmid}"
        if self.doi:
            return f"DOI:{self.doi}"
        return "Unknown paper"


@dataclass
class CochraneGroundTruth:
    """
    Complete ground truth dataset from a Cochrane review.

    Contains all papers that the Cochrane review included as evidence,
    along with metadata about the review itself.

    Attributes:
        cochrane_id: Cochrane review identifier (e.g., "CD012345")
        title: Title of the Cochrane review
        research_question: The research question addressed
        pico: PICO components if available
        inclusion_criteria: List of inclusion criteria from the review
        exclusion_criteria: List of exclusion criteria from the review
        included_studies: List of papers included in the review
        authors_conclusion: The review's conclusion (for future verdict comparison)
        date_range: Publication date range covered by the review
        notes: Any notes about this ground truth dataset
        source_url: URL to the original Cochrane review
    """

    cochrane_id: str
    title: str
    research_question: str
    included_studies: List[GroundTruthPaper]
    pico: Optional[Dict[str, str]] = None
    inclusion_criteria: Optional[List[str]] = None
    exclusion_criteria: Optional[List[str]] = None
    authors_conclusion: Optional[str] = None
    date_range: Optional[Tuple[int, int]] = None
    notes: Optional[str] = None
    source_url: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate the ground truth dataset."""
        if not self.cochrane_id:
            raise ValueError("Cochrane ID is required")
        if not self.included_studies:
            raise ValueError("At least one included study is required")

    @property
    def study_count(self) -> int:
        """Get the number of included studies."""
        return len(self.included_studies)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "cochrane_id": self.cochrane_id,
            "title": self.title,
            "research_question": self.research_question,
            "pico": self.pico,
            "inclusion_criteria": self.inclusion_criteria,
            "exclusion_criteria": self.exclusion_criteria,
            "included_studies": [s.to_dict() for s in self.included_studies],
            "authors_conclusion": self.authors_conclusion,
            "date_range": list(self.date_range) if self.date_range else None,
            "notes": self.notes,
            "source_url": self.source_url,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CochraneGroundTruth":
        """Create from dictionary."""
        studies = [
            GroundTruthPaper.from_dict(s)
            for s in data.get("included_studies", [])
        ]

        date_range = None
        if data.get("date_range"):
            date_range = tuple(data["date_range"])

        return cls(
            cochrane_id=data["cochrane_id"],
            title=data["title"],
            research_question=data["research_question"],
            included_studies=studies,
            pico=data.get("pico"),
            inclusion_criteria=data.get("inclusion_criteria"),
            exclusion_criteria=data.get("exclusion_criteria"),
            authors_conclusion=data.get("authors_conclusion"),
            date_range=date_range,
            notes=data.get("notes"),
            source_url=data.get("source_url"),
        )

    def to_search_criteria_dict(self) -> Dict[str, Any]:
        """
        Convert to SearchCriteria-compatible dictionary.

        This allows running the SystematicReviewAgent with the same
        criteria as the original Cochrane review.
        """
        criteria = {
            "research_question": self.research_question,
            "purpose": f"Benchmark validation against Cochrane review {self.cochrane_id}",
            "inclusion_criteria": self.inclusion_criteria or [],
            "exclusion_criteria": self.exclusion_criteria or [],
        }

        if self.date_range:
            criteria["date_range"] = list(self.date_range)

        return criteria


@dataclass
class PaperMatch:
    """
    Result of matching a ground truth paper against agent output.

    Attributes:
        ground_truth: The ground truth paper being matched
        matched_document_id: Document ID from agent output (if found)
        matched_title: Title from agent output (if found)
        match_method: How the match was made (pmid, doi, title_fuzzy)
        match_confidence: Confidence of the match (1.0 for exact, <1 for fuzzy)
        is_in_included: Whether the paper is in agent's included list
        relevance_score: Agent's relevance score for this paper (if available)
    """

    ground_truth: GroundTruthPaper
    matched_document_id: Optional[int] = None
    matched_title: Optional[str] = None
    match_method: Optional[str] = None
    match_confidence: float = 0.0
    is_in_included: bool = False
    relevance_score: Optional[float] = None

    @property
    def found(self) -> bool:
        """Check if the ground truth paper was found in agent output."""
        return self.matched_document_id is not None

    @property
    def found_and_included(self) -> bool:
        """Check if paper was found AND included in final results."""
        return self.found and self.is_in_included

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for reporting."""
        return {
            "ground_truth": self.ground_truth.to_dict(),
            "matched_document_id": self.matched_document_id,
            "matched_title": self.matched_title,
            "match_method": self.match_method,
            "match_confidence": self.match_confidence,
            "is_in_included": self.is_in_included,
            "relevance_score": self.relevance_score,
            "found": self.found,
            "found_and_included": self.found_and_included,
        }


@dataclass
class BenchmarkResult:
    """
    Results of comparing agent output against ground truth.

    Contains detailed metrics and per-paper matching results.

    Attributes:
        ground_truth: The Cochrane ground truth used
        total_ground_truth_papers: Number of papers in ground truth
        total_agent_included: Number of papers agent included
        papers_found: Ground truth papers found in agent's database
        papers_found_and_included: Papers found AND in included list
        papers_not_found: Ground truth papers NOT found in database
        papers_found_but_excluded: Papers found but NOT included
        recall: Fraction of ground truth papers found and included
        precision: Fraction of agent's included papers in ground truth
        matches: Detailed matching results for each ground truth paper
        passed: Whether benchmark passed (recall >= target)
        failure_reasons: List of reasons for failure (if any)
    """

    ground_truth: CochraneGroundTruth
    total_ground_truth_papers: int
    total_agent_included: int
    papers_found: int
    papers_found_and_included: int
    papers_not_found: int
    papers_found_but_excluded: int
    recall: float
    precision: float
    matches: List[PaperMatch]
    passed: bool
    failure_reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "cochrane_id": self.ground_truth.cochrane_id,
            "total_ground_truth_papers": self.total_ground_truth_papers,
            "total_agent_included": self.total_agent_included,
            "papers_found": self.papers_found,
            "papers_found_and_included": self.papers_found_and_included,
            "papers_not_found": self.papers_not_found,
            "papers_found_but_excluded": self.papers_found_but_excluded,
            "recall": round(self.recall, 4),
            "precision": round(self.precision, 4),
            "passed": self.passed,
            "failure_reasons": self.failure_reasons,
            "matches": [m.to_dict() for m in self.matches],
        }

    def get_summary(self) -> str:
        """Get human-readable summary of results."""
        status = "PASSED" if self.passed else "FAILED"
        lines = [
            f"Benchmark Result: {status}",
            f"  Cochrane ID: {self.ground_truth.cochrane_id}",
            f"  Ground Truth Papers: {self.total_ground_truth_papers}",
            f"  Agent Included Papers: {self.total_agent_included}",
            f"  Papers Found in DB: {self.papers_found}",
            f"  Papers Found & Included: {self.papers_found_and_included}",
            f"  Papers Not Found: {self.papers_not_found}",
            f"  Papers Found but Excluded: {self.papers_found_but_excluded}",
            f"  Recall: {self.recall:.1%} (target: {TARGET_RECALL_RATE:.0%})",
            f"  Precision: {self.precision:.1%}",
        ]

        if self.failure_reasons:
            lines.append("  Failure Reasons:")
            for reason in self.failure_reasons:
                lines.append(f"    - {reason}")

        return "\n".join(lines)

    def get_missing_papers_report(self) -> str:
        """Get detailed report of papers not found or not included."""
        lines = ["Missing Papers Report:"]

        not_found = [m for m in self.matches if not m.found]
        found_not_included = [m for m in self.matches if m.found and not m.is_in_included]

        if not_found:
            lines.append("\n  Papers NOT FOUND in database:")
            for match in not_found:
                gt = match.ground_truth
                lines.append(f"    - {gt.get_display_name()}")
                if gt.pmid:
                    lines.append(f"      PMID: {gt.pmid}")
                if gt.doi:
                    lines.append(f"      DOI: {gt.doi}")

        if found_not_included:
            lines.append("\n  Papers FOUND but NOT INCLUDED:")
            for match in found_not_included:
                gt = match.ground_truth
                lines.append(f"    - {gt.get_display_name()}")
                lines.append(f"      Document ID: {match.matched_document_id}")
                if match.relevance_score is not None:
                    lines.append(f"      Relevance Score: {match.relevance_score}")

        if not not_found and not found_not_included:
            lines.append("  All ground truth papers were found and included!")

        return "\n".join(lines)


# =============================================================================
# Matching Functions
# =============================================================================

def normalize_doi(doi: Optional[str]) -> Optional[str]:
    """
    Normalize a DOI for comparison.

    Removes URL prefix, converts to lowercase, strips whitespace.

    Args:
        doi: DOI string (may include URL prefix)

    Returns:
        Normalized DOI or None
    """
    if not doi:
        return None

    doi = doi.strip().lower()

    # Remove common URL prefixes
    prefixes = [
        "https://doi.org/",
        "http://doi.org/",
        "doi.org/",
        "doi:",
    ]
    for prefix in prefixes:
        if doi.startswith(prefix):
            doi = doi[len(prefix):]
            break

    return doi.strip() if doi else None


def normalize_pmid(pmid: Optional[str]) -> Optional[str]:
    """
    Normalize a PMID for comparison.

    Extracts numeric portion, removes leading zeros.

    Args:
        pmid: PMID string

    Returns:
        Normalized PMID or None
    """
    if not pmid:
        return None

    # Extract numeric portion
    pmid = str(pmid).strip()
    match = re.search(r'\d+', pmid)
    if match:
        # Remove leading zeros but keep at least one digit
        return str(int(match.group()))
    return None


def normalize_title(title: Optional[str]) -> Optional[str]:
    """
    Normalize a title for fuzzy comparison.

    Converts to lowercase, removes punctuation and extra whitespace.

    Args:
        title: Paper title

    Returns:
        Normalized title or None
    """
    if not title:
        return None

    # Convert to lowercase
    title = title.lower()

    # Remove common punctuation
    title = re.sub(r'[^\w\s]', ' ', title)

    # Collapse multiple spaces
    title = ' '.join(title.split())

    return title.strip() if title else None


def calculate_title_similarity(title1: str, title2: str) -> float:
    """
    Calculate similarity between two titles.

    Uses SequenceMatcher for fuzzy string matching.

    Args:
        title1: First title
        title2: Second title

    Returns:
        Similarity score (0-1, where 1 is identical)
    """
    norm1 = normalize_title(title1)
    norm2 = normalize_title(title2)

    if not norm1 or not norm2:
        return 0.0

    return SequenceMatcher(None, norm1, norm2).ratio()


def match_paper_to_result(
    ground_truth: GroundTruthPaper,
    agent_papers: List[Dict[str, Any]],
    included_doc_ids: Set[int],
) -> PaperMatch:
    """
    Match a ground truth paper against agent results.

    Attempts matching in order: PMID > DOI > Title (fuzzy).

    Args:
        ground_truth: Paper to find
        agent_papers: List of papers from agent (included + excluded)
        included_doc_ids: Set of document IDs that were included

    Returns:
        PaperMatch with matching results
    """
    norm_gt_pmid = normalize_pmid(ground_truth.pmid)
    norm_gt_doi = normalize_doi(ground_truth.doi)
    norm_gt_title = normalize_title(ground_truth.title)

    best_match: Optional[Dict[str, Any]] = None
    best_method: Optional[str] = None
    best_confidence: float = 0.0

    for paper in agent_papers:
        doc_id = paper.get("document_id")

        # Try PMID match (highest priority)
        if norm_gt_pmid:
            paper_pmid = normalize_pmid(paper.get("pmid"))
            if paper_pmid and paper_pmid == norm_gt_pmid:
                best_match = paper
                best_method = "pmid"
                best_confidence = 1.0
                break  # Exact match, stop searching

        # Try DOI match
        if norm_gt_doi:
            paper_doi = normalize_doi(paper.get("doi"))
            if paper_doi and paper_doi == norm_gt_doi:
                best_match = paper
                best_method = "doi"
                best_confidence = 1.0
                break  # Exact match, stop searching

        # Try title fuzzy match (only if no exact match yet)
        if norm_gt_title and best_confidence < MIN_TITLE_SIMILARITY_THRESHOLD:
            paper_title = paper.get("title", "")
            similarity = calculate_title_similarity(ground_truth.title, paper_title)
            if similarity >= MIN_TITLE_SIMILARITY_THRESHOLD and similarity > best_confidence:
                best_match = paper
                best_method = "title_fuzzy"
                best_confidence = similarity

    # Build result
    if best_match:
        doc_id = best_match.get("document_id")
        return PaperMatch(
            ground_truth=ground_truth,
            matched_document_id=doc_id,
            matched_title=best_match.get("title"),
            match_method=best_method,
            match_confidence=best_confidence,
            is_in_included=doc_id in included_doc_ids,
            relevance_score=best_match.get("relevance_score"),
        )
    else:
        return PaperMatch(ground_truth=ground_truth)


def match_papers(
    ground_truth: CochraneGroundTruth,
    agent_included: List[Dict[str, Any]],
    agent_excluded: List[Dict[str, Any]],
) -> List[PaperMatch]:
    """
    Match all ground truth papers against agent results.

    Args:
        ground_truth: Cochrane ground truth with included studies
        agent_included: Papers included by agent
        agent_excluded: Papers excluded by agent

    Returns:
        List of PaperMatch for each ground truth paper
    """
    # Combine all agent papers for searching
    all_agent_papers = agent_included + agent_excluded

    # Get set of included document IDs
    included_doc_ids = {
        p.get("document_id") for p in agent_included
        if p.get("document_id") is not None
    }

    # Match each ground truth paper
    matches = []
    for gt_paper in ground_truth.included_studies:
        match = match_paper_to_result(gt_paper, all_agent_papers, included_doc_ids)
        matches.append(match)

    return matches


# =============================================================================
# Recall/Precision Calculation
# =============================================================================

def calculate_recall_precision(
    ground_truth: CochraneGroundTruth,
    agent_included: List[Dict[str, Any]],
    agent_excluded: List[Dict[str, Any]],
) -> BenchmarkResult:
    """
    Calculate recall and precision against ground truth.

    Recall = (Ground truth papers found AND included) / (Total ground truth papers)
    Precision = (Agent included papers in ground truth) / (Total agent included)

    Target: 100% recall (all Cochrane papers found and included)

    Args:
        ground_truth: Cochrane ground truth dataset
        agent_included: Papers included by agent (from SystematicReviewResult)
        agent_excluded: Papers excluded by agent

    Returns:
        BenchmarkResult with detailed metrics
    """
    # Match papers
    matches = match_papers(ground_truth, agent_included, agent_excluded)

    # Count outcomes
    total_gt = len(ground_truth.included_studies)
    total_included = len(agent_included)

    papers_found = sum(1 for m in matches if m.found)
    papers_found_and_included = sum(1 for m in matches if m.found_and_included)
    papers_not_found = sum(1 for m in matches if not m.found)
    papers_found_but_excluded = sum(1 for m in matches if m.found and not m.is_in_included)

    # Calculate recall: what fraction of ground truth did we find AND include
    recall = papers_found_and_included / total_gt if total_gt > 0 else 0.0

    # Calculate precision: what fraction of our included papers are in ground truth
    # For this, we need to count how many agent_included are ground truth papers
    matched_doc_ids = {m.matched_document_id for m in matches if m.found_and_included}
    agent_included_in_gt = sum(
        1 for p in agent_included
        if p.get("document_id") in matched_doc_ids
    )
    precision = agent_included_in_gt / total_included if total_included > 0 else 0.0

    # Determine pass/fail
    passed = recall >= TARGET_RECALL_RATE

    # Collect failure reasons
    failure_reasons = []
    if recall < TARGET_RECALL_RATE:
        failure_reasons.append(
            f"Recall {recall:.1%} below target {TARGET_RECALL_RATE:.0%}"
        )
    if papers_not_found > 0:
        failure_reasons.append(
            f"{papers_not_found} ground truth paper(s) not found in database"
        )
    if papers_found_but_excluded > 0:
        failure_reasons.append(
            f"{papers_found_but_excluded} ground truth paper(s) found but not included"
        )

    return BenchmarkResult(
        ground_truth=ground_truth,
        total_ground_truth_papers=total_gt,
        total_agent_included=total_included,
        papers_found=papers_found,
        papers_found_and_included=papers_found_and_included,
        papers_not_found=papers_not_found,
        papers_found_but_excluded=papers_found_but_excluded,
        recall=recall,
        precision=precision,
        matches=matches,
        passed=passed,
        failure_reasons=failure_reasons,
    )


# =============================================================================
# File I/O
# =============================================================================

def load_ground_truth(path: str) -> CochraneGroundTruth:
    """
    Load ground truth from JSON file.

    Args:
        path: Path to JSON file

    Returns:
        CochraneGroundTruth instance

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file format is invalid
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Ground truth file not found: {path}")

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return CochraneGroundTruth.from_dict(data)


def save_ground_truth(ground_truth: CochraneGroundTruth, path: str) -> None:
    """
    Save ground truth to JSON file.

    Args:
        ground_truth: Ground truth to save
        path: Output file path
    """
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(ground_truth.to_dict(), f, indent=2, ensure_ascii=False)

    logger.info(f"Saved ground truth to: {path}")


def save_benchmark_result(result: BenchmarkResult, path: str) -> None:
    """
    Save benchmark result to JSON file.

    Args:
        result: Benchmark result to save
        path: Output file path
    """
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)

    logger.info(f"Saved benchmark result to: {path}")
