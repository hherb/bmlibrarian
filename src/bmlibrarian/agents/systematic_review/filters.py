"""
Filtering Components for SystematicReviewAgent

This module provides paper filtering at two levels:
1. InitialFilter: Fast heuristic-based filtering using date ranges, keywords, etc.
2. InclusionEvaluator: LLM-based evaluation against inclusion/exclusion criteria

The two-tier approach ensures expensive LLM evaluations are only applied to
papers that pass fast heuristics first.

Features:
- Date range filtering
- Study type keyword detection
- Exclusion keyword matching
- Language filtering
- LLM-based criteria evaluation
- Detailed rationale for all decisions
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from functools import lru_cache
from typing import Any, Callable, Dict, List, Optional, Pattern, Set, Tuple, TYPE_CHECKING

import ollama

from .data_models import (
    SearchCriteria,
    PaperData,
    InclusionDecision,
    InclusionStatus,
    ExclusionStage,
    ScoredPaper,
    StudyTypeFilter,
)
from .config import (
    SystematicReviewConfig,
    get_systematic_review_config,
    DEFAULT_TEMPERATURE,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Minimum abstract length to consider for evaluation
MIN_ABSTRACT_LENGTH = 50

# Keywords that often indicate specific study types (lowercase)
STUDY_TYPE_KEYWORDS: Dict[StudyTypeFilter, List[str]] = {
    StudyTypeFilter.RCT: [
        "randomized controlled trial", "randomised controlled trial",
        "rct", "randomized trial", "randomised trial",
        "double-blind", "double blind", "placebo-controlled",
        "randomized clinical trial", "randomised clinical trial",
    ],
    StudyTypeFilter.COHORT_PROSPECTIVE: [
        "prospective cohort", "prospective study", "follow-up study",
        "longitudinal study", "prospective analysis",
    ],
    StudyTypeFilter.COHORT_RETROSPECTIVE: [
        "retrospective cohort", "retrospective study", "retrospective analysis",
        "chart review", "medical records review",
    ],
    StudyTypeFilter.CASE_CONTROL: [
        "case-control", "case control", "matched controls",
    ],
    StudyTypeFilter.CROSS_SECTIONAL: [
        "cross-sectional", "cross sectional", "survey study",
        "prevalence study",
    ],
    StudyTypeFilter.SYSTEMATIC_REVIEW: [
        "systematic review", "systematic literature review",
        "scoping review", "umbrella review",
    ],
    StudyTypeFilter.META_ANALYSIS: [
        "meta-analysis", "meta analysis", "pooled analysis",
        "quantitative synthesis",
    ],
    StudyTypeFilter.CASE_SERIES: [
        "case series", "consecutive cases",
    ],
    StudyTypeFilter.CASE_REPORT: [
        "case report", "clinical case", "single case",
    ],
    StudyTypeFilter.QUASI_EXPERIMENTAL: [
        "quasi-experimental", "quasi experimental", "natural experiment",
        "interrupted time series",
    ],
    StudyTypeFilter.PILOT_FEASIBILITY: [
        "pilot study", "feasibility study", "pilot trial",
        "preliminary study",
    ],
}

# Common exclusion keyword patterns (lowercase)
DEFAULT_EXCLUSION_KEYWORDS: List[str] = [
    "animal study", "animal model", "mouse model", "rat model",
    "in vitro", "cell culture", "in vivo",
    "veterinary", "canine", "feline", "bovine", "porcine",
    "editorial", "letter to editor", "commentary",
    "protocol only", "study protocol",
    "erratum", "corrigendum", "retracted",
    "case report", "case reports", "case series",
]

# Title patterns that definitively indicate excluded study types
# These are high-confidence patterns found at the start or as labels in titles
# Stored as (pattern_string, description) tuples for better error messages
_DEFINITIVE_TITLE_PATTERN_DEFS: List[Tuple[str, str]] = [
    # Case reports - explicit labeling in title
    (r"^case report[:\s]", "case report"),
    (r"\bcase report[:\s]", "case report"),
    (r"^a case of\b", "case report"),
    (r"^a case report\b", "case report"),
    (r"\[case report\]", "case report"),
    # Animal studies - explicit labeling
    (r"^animal study[:\s]", "animal study"),
    (r"\bin rats\b", "animal study"),
    (r"\bin mice\b", "animal study"),
    (r"\bin vivo study\b", "in vitro/in vivo study"),
    (r"\bin vitro study\b", "in vitro/in vivo study"),
    (r"\bmouse model[:\s]", "animal study"),
    (r"\brat model[:\s]", "animal study"),
    # Editorials and non-research
    (r"^editorial[:\s]", "editorial"),
    (r"^letter to the editor\b", "letter to editor"),
    (r"^commentary[:\s]", "commentary"),
    (r"^erratum[:\s]", "erratum/corrigendum"),
    (r"^corrigendum[:\s]", "erratum/corrigendum"),
    (r"^retracted[:\s]", "retracted article"),
    (r"\bretracted\b$", "retracted article"),
]

# Pre-compile title patterns for performance
DEFINITIVE_TITLE_PATTERNS: List[Tuple[Pattern, str]] = [
    (re.compile(pattern), description)
    for pattern, description in _DEFINITIVE_TITLE_PATTERN_DEFS
]

# Context patterns that indicate exclusion keywords are NOT describing the paper itself
# e.g., "we excluded case reports" should NOT exclude the paper
NEGATIVE_CONTEXT_PATTERNS: List[str] = [
    # Exclusion statements in methods (with optional words between)
    r"(?:we |were |was )?exclud(?:ed|ing)\s+(?:\w+\s+)*{keyword}",
    r"(?:we |were |was )?not includ(?:ed|ing)\s+(?:\w+\s+)*{keyword}",
    r"{keyword}\s+(?:\w+\s+)?(?:were|was)\s+(?:\w+\s+)?excluded",
    r"except(?:ing)?\s+(?:for\s+)?(?:\w+\s+)*{keyword}",
    r"excluding\s+(?:\w+\s+)*{keyword}",
    # Comparative statements
    r"unlike\s+(?:\w+\s+)*{keyword}",
    r"(?:in\s+)?contrast\s+to\s+(?:\w+\s+)*{keyword}",
    r"(?:prior|previous|earlier)\s+(?:\w+\s+)*{keyword}",
    r"{keyword}\s+(?:have|has)\s+shown\s+(?:that\s+)?(?:but|however)",
    r"differ(?:s|ed|ing|ent)?\s+(?:from\s+)?(?:\w+\s+)*{keyword}",
    # Literature review references
    r"review(?:ed|ing)?\s+(?:\w+\s+)*{keyword}",
    r"{keyword}\s+(?:literature|studies|publications)",
    # Limitation/comparison discussions
    r"limit(?:ed|ation)s?\s+(?:of\s+)?(?:\w+\s+)*{keyword}",
    r"(?:compared|comparing)\s+(?:to|with)\s+(?:\w+\s+)*{keyword}",
    # Predictions/results from other study types
    r"{keyword}\s+(?:prediction|finding|result|outcome)s?",
]

# Confidence thresholds
HIGH_CONFIDENCE_THRESHOLD = 0.85
MEDIUM_CONFIDENCE_THRESHOLD = 0.6
LOW_CONFIDENCE_THRESHOLD = 0.4

# Confidence values for different filter types (aligned with threshold categories)
STUDY_TYPE_KEYWORD_CONFIDENCE = MEDIUM_CONFIDENCE_THRESHOLD  # Keyword-based study type checks
EXCLUSION_KEYWORD_CONFIDENCE = HIGH_CONFIDENCE_THRESHOLD  # Exclusion keyword matches

# LLM response limits
LLM_MAX_TOKENS = 800  # Maximum tokens for LLM response

# Display limits for prompts
MAX_AUTHORS_TO_DISPLAY = 5  # Maximum authors to include in evaluation prompts


# =============================================================================
# Cached Pattern Compilation Helpers
# =============================================================================

@lru_cache(maxsize=256)
def _compile_negative_context_pattern(pattern_template: str, keyword: str) -> Pattern:
    """
    Compile a negative context pattern with keyword substitution.

    Results are cached to avoid recompiling patterns for common keywords.

    Args:
        pattern_template: Pattern template with {keyword} placeholder
        keyword: Keyword to substitute (will be escaped)

    Returns:
        Compiled regex pattern

    Raises:
        re.error: If pattern compilation fails
    """
    escaped_keyword = re.escape(keyword)
    pattern_str = pattern_template.replace("{keyword}", escaped_keyword)
    return re.compile(pattern_str)


# =============================================================================
# Data Types
# =============================================================================

@dataclass
class FilterResult:
    """
    Result of filtering a single paper.

    Attributes:
        paper: The paper that was filtered
        passed: Whether the paper passed the filter
        reason: Reason for the decision
        stage: Which filtering stage made the decision
        confidence: Confidence in the decision (0-1)
    """

    paper: PaperData
    passed: bool
    reason: str
    stage: ExclusionStage
    confidence: float = 1.0

    def to_inclusion_decision(self) -> InclusionDecision:
        """Convert to InclusionDecision for downstream processing."""
        if self.passed:
            return InclusionDecision.create_included(
                stage=self.stage,
                rationale=self.reason,
                criteria_matched=["Passed initial filter"],
                confidence=self.confidence,
            )
        else:
            return InclusionDecision.create_excluded(
                stage=self.stage,
                reasons=[self.reason],
                rationale=self.reason,
                confidence=self.confidence,
            )


@dataclass
class BatchFilterResult:
    """
    Result of filtering a batch of papers.

    Attributes:
        passed: Papers that passed the filter
        rejected: Papers rejected with reasons
        total_processed: Total number of papers processed
        execution_time_seconds: Time taken for filtering
    """

    passed: List[PaperData] = field(default_factory=list)
    rejected: List[Tuple[PaperData, str]] = field(default_factory=list)
    total_processed: int = 0
    execution_time_seconds: float = 0.0

    @property
    def pass_rate(self) -> float:
        """Percentage of papers that passed."""
        if self.total_processed == 0:
            return 0.0
        return len(self.passed) / self.total_processed

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "passed_count": len(self.passed),
            "rejected_count": len(self.rejected),
            "total_processed": self.total_processed,
            "pass_rate": round(self.pass_rate * 100, 2),
            "execution_time_seconds": round(self.execution_time_seconds, 2),
        }


# =============================================================================
# InitialFilter Class
# =============================================================================

class InitialFilter:
    """
    Fast heuristic-based paper filtering.

    Applies quick checks to eliminate obviously irrelevant papers before
    expensive LLM-based evaluation. Checks include:
    - Date range compliance
    - Study type keywords
    - Exclusion keyword matching
    - Language compatibility
    - Minimum content requirements

    Attributes:
        criteria: SearchCriteria defining filter rules
        custom_exclusion_keywords: Additional exclusion keywords

    Example:
        >>> filter = InitialFilter(criteria)
        >>> result = filter.filter_batch(papers)
        >>> print(f"Passed: {len(result.passed)}, Rejected: {len(result.rejected)}")
    """

    def __init__(
        self,
        criteria: SearchCriteria,
        custom_exclusion_keywords: Optional[List[str]] = None,
        callback: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        """
        Initialize the InitialFilter.

        Args:
            criteria: SearchCriteria with filter rules
            custom_exclusion_keywords: Additional keywords to exclude
            callback: Optional progress callback
        """
        self.criteria = criteria
        self.callback = callback

        # Build exclusion keyword set
        self._exclusion_keywords: Set[str] = set(DEFAULT_EXCLUSION_KEYWORDS)
        if custom_exclusion_keywords:
            self._exclusion_keywords.update(
                kw.lower().strip() for kw in custom_exclusion_keywords
            )

        # Add exclusion criteria as keywords
        for criterion in criteria.exclusion_criteria:
            # Convert criteria to keyword patterns
            keywords = self._extract_keywords_from_criterion(criterion)
            self._exclusion_keywords.update(keywords)

        # Build study type keyword lookup if filtering is enabled
        self._allowed_study_keywords: Set[str] = set()
        if criteria.target_study_types:
            for study_type in criteria.target_study_types:
                if study_type != StudyTypeFilter.ANY:
                    keywords = STUDY_TYPE_KEYWORDS.get(study_type, [])
                    self._allowed_study_keywords.update(keywords)

        logger.info(
            f"InitialFilter initialized: "
            f"{len(self._exclusion_keywords)} exclusion keywords, "
            f"date_range={criteria.date_range}, "
            f"study_types={len(criteria.target_study_types or [])} types"
        )

    def _call_callback(self, event: str, data: str) -> None:
        """Call progress callback if registered."""
        if self.callback:
            try:
                self.callback(event, data)
            except Exception as e:
                logger.warning(f"Callback error: {e}")

    def _extract_keywords_from_criterion(self, criterion: str) -> Set[str]:
        """
        Extract keywords from an exclusion criterion string.

        Parses complex criteria like "No animal studies or case reports" into
        individual meaningful keywords.

        Args:
            criterion: Exclusion criterion text

        Returns:
            Set of lowercase keyword phrases
        """
        keywords: Set[str] = set()
        criterion_lower = criterion.lower().strip()

        # Remove common negative prefixes (no, exclude, without, etc.)
        criterion_lower = re.sub(
            r'^(?:no|exclude|excluding|without|not including)\s+',
            '',
            criterion_lower
        )

        # Split on common conjunctions (or, and, commas)
        # e.g., "animal studies or case reports" -> ["animal studies", "case reports"]
        parts = re.split(r'\s+(?:or|and)\s+|,\s*', criterion_lower)

        for part in parts:
            part = part.strip()
            if not part:
                continue

            # Add the full phrase
            keywords.add(part)

            # Extract known study type patterns
            for study_type_keywords in STUDY_TYPE_KEYWORDS.values():
                for keyword in study_type_keywords:
                    if keyword in part:
                        keywords.add(keyword)

            # Extract known exclusion patterns
            for exclusion_keyword in DEFAULT_EXCLUSION_KEYWORDS:
                if exclusion_keyword in part:
                    keywords.add(exclusion_keyword)

            # Handle common patterns like "X studies" -> also add "X study"
            if part.endswith(" studies"):
                singular = part[:-7] + "study"
                keywords.add(singular)
            elif part.endswith(" study"):
                plural = part[:-4] + "studies"
                keywords.add(plural)

            # Handle "X reports" -> "X report"
            if part.endswith(" reports"):
                singular = part[:-7] + "report"
                keywords.add(singular)
            elif part.endswith(" report"):
                plural = part[:-6] + "reports"
                keywords.add(plural)

        # Filter out very short or generic keywords
        keywords = {
            kw for kw in keywords
            if len(kw) >= 3 and kw not in {"the", "and", "or", "not"}
        }

        return keywords

    # =========================================================================
    # Main Filtering Methods
    # =========================================================================

    def filter_paper(self, paper: PaperData) -> FilterResult:
        """
        Apply all filter checks to a single paper.

        Args:
            paper: Paper to filter

        Returns:
            FilterResult with pass/fail status and reason
        """
        # Check date range
        date_result = self._check_date_range(paper)
        if date_result:
            return FilterResult(
                paper=paper,
                passed=False,
                reason=date_result,
                stage=ExclusionStage.INITIAL_FILTER,
            )

        # Check study type keywords
        if self._allowed_study_keywords:
            study_result = self._check_study_type_keywords(paper)
            if study_result:
                return FilterResult(
                    paper=paper,
                    passed=False,
                    reason=study_result,
                    stage=ExclusionStage.INITIAL_FILTER,
                    confidence=STUDY_TYPE_KEYWORD_CONFIDENCE,
                )

        # Check exclusion keywords
        exclusion_result = self._check_exclusion_keywords(paper)
        if exclusion_result:
            return FilterResult(
                paper=paper,
                passed=False,
                reason=exclusion_result,
                stage=ExclusionStage.INITIAL_FILTER,
                confidence=EXCLUSION_KEYWORD_CONFIDENCE,
            )

        # Check minimum content
        content_result = self._check_minimum_content(paper)
        if content_result:
            return FilterResult(
                paper=paper,
                passed=False,
                reason=content_result,
                stage=ExclusionStage.INITIAL_FILTER,
            )

        # Paper passed all checks
        return FilterResult(
            paper=paper,
            passed=True,
            reason="Passed all initial filter checks",
            stage=ExclusionStage.INITIAL_FILTER,
        )

    def filter_batch(
        self,
        papers: List[PaperData],
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> BatchFilterResult:
        """
        Apply filtering to a batch of papers.

        Args:
            papers: List of papers to filter
            progress_callback: Optional callback(current, total) for progress

        Returns:
            BatchFilterResult with passed and rejected papers
        """
        self._call_callback("filter_started", f"Filtering {len(papers)} papers")
        start_time = time.time()

        passed: List[PaperData] = []
        rejected: List[Tuple[PaperData, str]] = []

        for i, paper in enumerate(papers):
            result = self.filter_paper(paper)

            if result.passed:
                passed.append(paper)
            else:
                rejected.append((paper, result.reason))

            if progress_callback:
                progress_callback(i + 1, len(papers))

        execution_time = time.time() - start_time

        self._call_callback(
            "filter_completed",
            f"Passed: {len(passed)}, Rejected: {len(rejected)}"
        )

        logger.info(
            f"Initial filter: {len(passed)} passed, {len(rejected)} rejected "
            f"({execution_time:.2f}s)"
        )

        return BatchFilterResult(
            passed=passed,
            rejected=rejected,
            total_processed=len(papers),
            execution_time_seconds=execution_time,
        )

    # =========================================================================
    # Individual Filter Checks
    # =========================================================================

    def _check_date_range(self, paper: PaperData) -> Optional[str]:
        """
        Check if paper is within date range.

        Args:
            paper: Paper to check

        Returns:
            Error message if paper fails check, None if passes
        """
        if not self.criteria.date_range:
            return None  # No date filter

        start_year, end_year = self.criteria.date_range

        if paper.year < start_year:
            return f"Publication year {paper.year} before range start {start_year}"

        if paper.year > end_year:
            return f"Publication year {paper.year} after range end {end_year}"

        return None

    def _check_study_type_keywords(self, paper: PaperData) -> Optional[str]:
        """
        Check if paper mentions allowed study type keywords.

        This is a heuristic check - papers without study type keywords
        may still be relevant and will be evaluated by LLM later.

        Args:
            paper: Paper to check

        Returns:
            Warning message if no study type keywords found, None otherwise
        """
        if not self._allowed_study_keywords:
            return None  # No study type filter

        # Check title and abstract for study type keywords
        text_to_check = f"{paper.title} {paper.abstract or ''}".lower()

        for keyword in self._allowed_study_keywords:
            if keyword in text_to_check:
                return None  # Found a matching study type keyword

        # No study type keyword found - but this is a soft filter
        # We return None to pass the paper through for LLM evaluation
        # because many valid papers don't explicitly state study type
        logger.debug(
            f"Paper {paper.document_id} has no obvious study type keywords "
            f"(will proceed to LLM evaluation)"
        )
        return None  # Pass through for LLM evaluation

    def _check_exclusion_keywords(self, paper: PaperData) -> Optional[str]:
        """
        Check if paper matches any exclusion keywords using context-aware filtering.

        Uses a multi-tier approach:
        1. Check title for definitive patterns (high confidence exclusion)
        2. Check for exclusion keywords with negative context patterns
        3. Only exclude if keyword appears without protective context

        Args:
            paper: Paper to check

        Returns:
            Error message with matched keyword if excluded, None if passes
        """
        title_lower = paper.title.lower()
        abstract_lower = (paper.abstract or "").lower()

        # Tier 1: Check for definitive title patterns (high confidence)
        title_match = self._check_definitive_title_patterns(title_lower)
        if title_match:
            return f"Title indicates excluded study type: '{title_match}'"

        # Tier 2: Context-aware keyword checking
        full_text = f"{title_lower} {abstract_lower}"

        for keyword in self._exclusion_keywords:
            if keyword not in full_text:
                continue

            # Check if keyword appears in title (strong signal)
            in_title = keyword in title_lower
            # Check if keyword has protective/negative context
            has_negative_context = self._has_negative_context(full_text, keyword)

            if in_title and not has_negative_context:
                # Keyword in title without protective context - high confidence exclusion
                return f"Matches exclusion keyword in title: '{keyword}'"
            elif not in_title and not has_negative_context:
                # Keyword in abstract only without protective context
                # This is a softer signal - log but still exclude
                # The InclusionEvaluator can review if needed
                logger.debug(
                    f"Paper {paper.document_id} has exclusion keyword '{keyword}' "
                    f"in abstract without clear context - excluding with lower confidence"
                )
                return f"Matches exclusion keyword: '{keyword}'"
            else:
                # Keyword has protective context - likely a reference/comparison
                logger.debug(
                    f"Paper {paper.document_id} mentions '{keyword}' in protected "
                    f"context (e.g., 'excluded case reports') - allowing paper to pass"
                )

        return None

    def _check_definitive_title_patterns(self, title: str) -> Optional[str]:
        """
        Check if title matches definitive exclusion patterns.

        These patterns indicate with high confidence that the paper itself
        is of an excluded type (not just mentioning it).

        Args:
            title: Lowercase title to check

        Returns:
            Matched pattern description if excluded, None if passes
        """
        for compiled_pattern, description in DEFINITIVE_TITLE_PATTERNS:
            if compiled_pattern.search(title):
                return description
        return None

    def _has_negative_context(self, text: str, keyword: str) -> bool:
        """
        Check if keyword appears in a protective/negative context.

        Negative context indicates the paper is NOT of that type, but merely
        mentions excluding or comparing to such papers.

        Uses cached compiled patterns for performance.

        Args:
            text: Full text to check (lowercase)
            keyword: Exclusion keyword to check context for

        Returns:
            True if keyword has protective context, False otherwise
        """
        for pattern_template in NEGATIVE_CONTEXT_PATTERNS:
            try:
                # Use cached pattern compilation
                compiled_pattern = _compile_negative_context_pattern(
                    pattern_template, keyword
                )
                if compiled_pattern.search(text):
                    logger.debug(
                        f"Found negative context for '{keyword}' matching pattern: {pattern_template}"
                    )
                    return True
            except re.error as e:
                logger.warning(
                    f"Invalid regex pattern template '{pattern_template}' "
                    f"with keyword '{keyword}': {e}"
                )

        return False

    def _check_minimum_content(self, paper: PaperData) -> Optional[str]:
        """
        Check if paper has minimum required content.

        Args:
            paper: Paper to check

        Returns:
            Error message if insufficient content, None if passes
        """
        # Check title exists
        if not paper.title or not paper.title.strip():
            return "Missing title"

        # Check abstract length (if present)
        abstract = paper.abstract or ""
        if abstract and len(abstract.strip()) < MIN_ABSTRACT_LENGTH:
            return f"Abstract too short ({len(abstract.strip())} chars)"

        # If no abstract, paper can still pass if it has other content
        if not abstract and not paper.full_text:
            logger.debug(
                f"Paper {paper.document_id} has no abstract - will need full text"
            )

        return None

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def get_filter_statistics(
        self,
        result: BatchFilterResult,
    ) -> Dict[str, Any]:
        """
        Get detailed statistics about filtering results.

        Args:
            result: BatchFilterResult to analyze

        Returns:
            Dictionary with detailed statistics
        """
        # Categorize rejections by reason
        reason_counts: Dict[str, int] = {}
        for _, reason in result.rejected:
            # Extract reason category
            if "date" in reason.lower() or "year" in reason.lower():
                category = "date_range"
            elif "exclusion keyword" in reason.lower():
                category = "exclusion_keyword"
            elif "study type" in reason.lower():
                category = "study_type"
            elif "content" in reason.lower() or "short" in reason.lower():
                category = "insufficient_content"
            else:
                category = "other"

            reason_counts[category] = reason_counts.get(category, 0) + 1

        return {
            "total_papers": result.total_processed,
            "passed": len(result.passed),
            "rejected": len(result.rejected),
            "pass_rate_percent": round(result.pass_rate * 100, 2),
            "execution_time_seconds": round(result.execution_time_seconds, 2),
            "rejection_reasons": reason_counts,
        }


# =============================================================================
# InclusionEvaluator Class
# =============================================================================

class InclusionEvaluator:
    """
    LLM-based evaluation against inclusion/exclusion criteria.

    Uses an LLM to evaluate papers against explicit criteria that are
    too complex for keyword matching. Provides detailed rationale and
    confidence scores.

    Attributes:
        criteria: SearchCriteria with inclusion/exclusion rules
        model: Ollama model for evaluation
        host: Ollama server URL

    Example:
        >>> evaluator = InclusionEvaluator(criteria)
        >>> decision = evaluator.evaluate(paper, relevance_score=4.0)
        >>> print(f"Status: {decision.status}, Rationale: {decision.rationale}")
    """

    def __init__(
        self,
        criteria: SearchCriteria,
        model: Optional[str] = None,
        host: Optional[str] = None,
        temperature: float = DEFAULT_TEMPERATURE,
        config: Optional[SystematicReviewConfig] = None,
        callback: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        """
        Initialize the InclusionEvaluator.

        Args:
            criteria: SearchCriteria with inclusion/exclusion rules
            model: Ollama model name (optional, loaded from config if not provided)
            host: Ollama server URL (optional, loaded from config if not provided)
            temperature: LLM temperature for consistency
            config: Optional full configuration
            callback: Optional progress callback
        """
        self.criteria = criteria
        self.callback = callback
        self.temperature = temperature

        # Load config if not provided
        if config:
            self._config = config
        else:
            self._config = get_systematic_review_config()

        # Set model and host
        self.model = model or self._config.model
        self.host = host or self._config.host

        # System prompt for inclusion evaluation
        self._system_prompt = self._build_system_prompt()

        logger.info(
            f"InclusionEvaluator initialized: model={self.model}, "
            f"inclusion_criteria={len(criteria.inclusion_criteria)}, "
            f"exclusion_criteria={len(criteria.exclusion_criteria)}"
        )

    def _build_system_prompt(self) -> str:
        """Build the system prompt for inclusion evaluation."""
        inclusion_list = "\n".join(
            f"  - {criterion}"
            for criterion in self.criteria.inclusion_criteria
        )
        exclusion_list = "\n".join(
            f"  - {criterion}"
            for criterion in self.criteria.exclusion_criteria
        )

        return f"""You are a systematic review expert evaluating papers for inclusion.

RESEARCH QUESTION:
{self.criteria.research_question}

PURPOSE:
{self.criteria.purpose}

INCLUSION CRITERIA (paper MUST meet ALL of these):
{inclusion_list}

EXCLUSION CRITERIA (paper is EXCLUDED if it matches ANY of these):
{exclusion_list}

INSTRUCTIONS:
1. Carefully analyze the paper's title and abstract
2. Evaluate each inclusion criterion - does the paper meet it?
3. Check each exclusion criterion - does the paper match any?
4. Determine the overall decision: INCLUDE, EXCLUDE, or UNCERTAIN
5. Provide clear rationale for your decision

DECISION GUIDELINES:
- INCLUDE: Paper clearly meets all inclusion criteria and no exclusion criteria
- EXCLUDE: Paper fails at least one inclusion criterion OR matches an exclusion criterion
- UNCERTAIN: Borderline case needing human review (rare - use only when truly ambiguous)

RESPONSE FORMAT:
Return ONLY valid JSON with this exact structure:
{{
    "decision": "INCLUDE" | "EXCLUDE" | "UNCERTAIN",
    "confidence": <float 0.0-1.0>,
    "inclusion_criteria_met": ["list of met criteria"],
    "inclusion_criteria_failed": ["list of failed criteria"],
    "exclusion_criteria_matched": ["list of matched exclusion criteria"],
    "rationale": "clear explanation of decision"
}}

IMPORTANT:
- Return RAW JSON only - no markdown formatting
- Be conservative: when in doubt, EXCLUDE
- Provide specific evidence from the paper for your decision"""

    def _call_callback(self, event: str, data: str) -> None:
        """Call progress callback if registered."""
        if self.callback:
            try:
                self.callback(event, data)
            except Exception as e:
                logger.warning(f"Callback error: {e}")

    # =========================================================================
    # Main Evaluation Method
    # =========================================================================

    def evaluate(
        self,
        paper: PaperData,
        relevance_score: Optional[float] = None,
    ) -> InclusionDecision:
        """
        Evaluate paper against inclusion/exclusion criteria.

        Uses LLM to assess each criterion explicitly and provide
        detailed rationale.

        Args:
            paper: Paper to evaluate
            relevance_score: Optional relevance score from scoring phase

        Returns:
            InclusionDecision with detailed evaluation

        Raises:
            ConnectionError: If unable to connect to Ollama
            ValueError: If LLM response is invalid
        """
        self._call_callback(
            "inclusion_evaluation_started",
            f"Evaluating paper: {paper.title[:50]}..."
        )

        # Build evaluation prompt
        prompt = self._build_evaluation_prompt(paper, relevance_score)

        try:
            # Make LLM request
            response = ollama.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._system_prompt},
                    {"role": "user", "content": prompt},
                ],
                options={
                    "temperature": self.temperature,
                    "num_predict": LLM_MAX_TOKENS,
                },
            )

            response_text = response["message"]["content"]

            # Parse response
            decision = self._parse_evaluation_response(response_text)

            self._call_callback(
                "inclusion_evaluation_completed",
                f"Decision: {decision.status.value}"
            )

            return decision

        except Exception as e:
            logger.error(f"Inclusion evaluation failed: {e}")
            self._call_callback("inclusion_evaluation_failed", str(e))

            # Return UNCERTAIN for failed evaluations
            return InclusionDecision(
                status=InclusionStatus.UNCERTAIN,
                stage=ExclusionStage.INCLUSION_CRITERIA,
                reasons=[f"Evaluation failed: {e}"],
                rationale="Unable to evaluate due to error",
                confidence=0.0,
            )

    def _build_evaluation_prompt(
        self,
        paper: PaperData,
        relevance_score: Optional[float] = None,
    ) -> str:
        """Build the evaluation prompt for a paper."""
        # Build author string with limit
        authors_display = ', '.join(paper.authors[:MAX_AUTHORS_TO_DISPLAY])
        if len(paper.authors) > MAX_AUTHORS_TO_DISPLAY:
            authors_display += '...'

        # Build paper summary
        paper_info = f"""PAPER TO EVALUATE:

Title: {paper.title}

Authors: {authors_display}

Year: {paper.year}

Journal: {paper.journal or 'Not specified'}

Abstract:
{paper.abstract or 'No abstract available'}"""

        if relevance_score is not None:
            paper_info += f"\n\nRelevance Score: {relevance_score}/5"

        return f"""{paper_info}

Please evaluate this paper against the inclusion and exclusion criteria and provide your decision in the specified JSON format."""

    def _parse_evaluation_response(
        self,
        response: str,
    ) -> InclusionDecision:
        """
        Parse LLM response into InclusionDecision.

        Args:
            response: Raw LLM response text

        Returns:
            InclusionDecision parsed from response

        Raises:
            ValueError: If response cannot be parsed
        """
        # Clean response - remove markdown formatting if present
        cleaned = response.strip()
        if cleaned.startswith("```"):
            # Remove code block markers
            lines = cleaned.split("\n")
            lines = [
                line for line in lines
                if not line.startswith("```")
            ]
            cleaned = "\n".join(lines).strip()

        # Try to extract JSON
        try:
            # Find JSON object in response
            json_match = re.search(r'\{[^{}]*\}', cleaned, re.DOTALL)
            if json_match:
                cleaned = json_match.group()

            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}\nResponse: {cleaned[:200]}")
            raise ValueError(f"Invalid JSON response: {e}") from e

        # Extract fields
        decision_str = data.get("decision", "").upper()
        confidence = float(data.get("confidence", 0.5))
        criteria_met = data.get("inclusion_criteria_met", [])
        criteria_failed = data.get("inclusion_criteria_failed", [])
        exclusion_matched = data.get("exclusion_criteria_matched", [])
        rationale = data.get("rationale", "No rationale provided")

        # Map decision to status
        if decision_str == "INCLUDE":
            status = InclusionStatus.INCLUDED
            stage = ExclusionStage.INCLUSION_CRITERIA
            reasons = ["Meets all inclusion criteria"]
        elif decision_str == "EXCLUDE":
            status = InclusionStatus.EXCLUDED
            # Determine if exclusion is due to failed inclusion or matched exclusion
            if exclusion_matched:
                stage = ExclusionStage.EXCLUSION_CRITERIA
                reasons = exclusion_matched
            else:
                stage = ExclusionStage.INCLUSION_CRITERIA
                reasons = criteria_failed if criteria_failed else ["Does not meet inclusion criteria"]
        else:
            status = InclusionStatus.UNCERTAIN
            stage = ExclusionStage.INCLUSION_CRITERIA
            reasons = ["Requires human review"]

        return InclusionDecision(
            status=status,
            stage=stage,
            reasons=reasons,
            rationale=rationale,
            confidence=confidence,
            criteria_matched=criteria_met if criteria_met else None,
            criteria_failed=criteria_failed if criteria_failed else None,
            exclusion_matched=exclusion_matched if exclusion_matched else None,
        )

    # =========================================================================
    # Batch Evaluation
    # =========================================================================

    def evaluate_batch(
        self,
        papers: List[PaperData],
        relevance_scores: Optional[Dict[int, float]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[Tuple[PaperData, InclusionDecision]]:
        """
        Evaluate multiple papers against criteria.

        Args:
            papers: List of papers to evaluate
            relevance_scores: Optional dict mapping document_id to relevance score
            progress_callback: Optional callback(current, total) for progress

        Returns:
            List of (paper, decision) tuples
        """
        self._call_callback(
            "batch_evaluation_started",
            f"Evaluating {len(papers)} papers"
        )

        results: List[Tuple[PaperData, InclusionDecision]] = []

        for i, paper in enumerate(papers):
            relevance = None
            if relevance_scores:
                relevance = relevance_scores.get(paper.document_id)

            decision = self.evaluate(paper, relevance)
            results.append((paper, decision))

            if progress_callback:
                progress_callback(i + 1, len(papers))

        self._call_callback(
            "batch_evaluation_completed",
            f"Evaluated {len(papers)} papers"
        )

        return results

    # =========================================================================
    # Statistics
    # =========================================================================

    def get_evaluation_statistics(
        self,
        results: List[Tuple[PaperData, InclusionDecision]],
    ) -> Dict[str, Any]:
        """
        Get statistics about evaluation results.

        Args:
            results: List of (paper, decision) tuples

        Returns:
            Dictionary with evaluation statistics
        """
        status_counts = {
            "included": 0,
            "excluded": 0,
            "uncertain": 0,
        }
        stage_counts: Dict[str, int] = {}
        total_confidence = 0.0

        for _, decision in results:
            # Count by status
            status_key = decision.status.value
            status_counts[status_key] = status_counts.get(status_key, 0) + 1

            # Count by stage
            stage_key = decision.stage.value
            stage_counts[stage_key] = stage_counts.get(stage_key, 0) + 1

            # Sum confidence
            total_confidence += decision.confidence

        avg_confidence = (
            total_confidence / len(results) if results else 0.0
        )

        return {
            "total_evaluated": len(results),
            "status_counts": status_counts,
            "stage_counts": stage_counts,
            "average_confidence": round(avg_confidence, 3),
            "inclusion_rate": round(
                status_counts.get("included", 0) / len(results) * 100, 2
            ) if results else 0,
        }
