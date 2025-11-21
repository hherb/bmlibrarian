"""
Paper Weight Assessment Agent - Multi-dimensional paper quality assessment

This module provides an AI-powered agent for assessing the evidential weight of
biomedical research papers across five dimensions: study design, sample size,
methodological quality, risk of bias, and replication status.

The module currently contains the data models (dataclasses) for representing
assessments. The agent implementation will be added in later steps.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Callable, Any, TYPE_CHECKING
from datetime import datetime
import json

if TYPE_CHECKING:
    from .orchestrator import AgentOrchestrator

# Constants for formatting and display
DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'  # Standard datetime format for reports


@dataclass
class AssessmentDetail:
    """
    Audit trail entry for a single assessment component.

    Provides full reproducibility by storing:
    - What was extracted from the paper
    - How it contributed to the dimension score
    - Evidence text supporting the assessment
    - LLM reasoning (for AI-based assessments)

    Attributes:
        dimension: Name of the dimension (e.g., "study_design", "sample_size")
        component: Specific component assessed (e.g., "randomization", "blinding_type")
        extracted_value: Value found in the paper (e.g., "double-blind", "450")
        score_contribution: Points contributed to dimension score (0-10)
        evidence_text: Relevant excerpt from paper (optional)
        reasoning: AI reasoning for this score (optional)

    Example:
        >>> detail = AssessmentDetail(
        ...     dimension="methodological_quality",
        ...     component="blinding_type",
        ...     extracted_value="double-blind",
        ...     score_contribution=3.0,
        ...     evidence_text="Participants and investigators were masked...",
        ...     reasoning="Double-blind design detected, contributing full 3.0 points"
        ... )
    """
    dimension: str
    component: str
    extracted_value: Optional[str]
    score_contribution: float
    evidence_text: Optional[str] = None
    reasoning: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for database storage."""
        return {
            'dimension': self.dimension,
            'component': self.component,
            'extracted_value': self.extracted_value,
            'score_contribution': self.score_contribution,
            'evidence_text': self.evidence_text,
            'reasoning': self.reasoning
        }


@dataclass
class DimensionScore:
    """
    Score for a single assessment dimension with full audit trail.

    Each dimension (study design, sample size, etc.) has a final score
    and a list of components that contributed to that score.

    Attributes:
        dimension_name: Name of this dimension
        score: Final score for this dimension (0-10)
        details: List of component assessments that contributed to the score

    Example:
        >>> sample_size_score = DimensionScore(dimension_name="sample_size", score=7.1)
        >>> sample_size_score.add_detail(
        ...     component="extracted_n",
        ...     value="450",
        ...     contribution=5.3,
        ...     reasoning="Log10(450) * 2 = 5.3"
        ... )
        >>> sample_size_score.add_detail(
        ...     component="power_calculation",
        ...     value="yes",
        ...     contribution=2.0,
        ...     evidence="Sample size was calculated to provide 80% power...",
        ...     reasoning="Power calculation mentioned, bonus +2.0"
        ... )
    """
    dimension_name: str
    score: float
    details: List[AssessmentDetail] = field(default_factory=list)

    def add_detail(self, component: str, value: str, contribution: float,
                   evidence: Optional[str] = None, reasoning: Optional[str] = None) -> None:
        """
        Add an audit trail entry for a component of this dimension.

        Args:
            component: Name of the component (e.g., "randomization")
            value: Extracted value (e.g., "proper sequence generation")
            contribution: Points contributed to dimension score
            evidence: Supporting text from paper (optional)
            reasoning: AI reasoning for this score (optional)
        """
        self.details.append(AssessmentDetail(
            dimension=self.dimension_name,
            component=component,
            extracted_value=value,
            score_contribution=contribution,
            evidence_text=evidence,
            reasoning=reasoning
        ))

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            'dimension_name': self.dimension_name,
            'score': self.score,
            'details': [d.to_dict() for d in self.details]
        }


@dataclass
class PaperWeightResult:
    """
    Complete paper weight assessment with full audit trail.

    This is the top-level result object containing all dimension scores,
    the final weighted score, and complete reproducibility information.

    Attributes:
        document_id: Database ID of assessed document
        assessor_version: Version of assessment methodology
        assessed_at: Timestamp of assessment
        study_design: Study design dimension score
        sample_size: Sample size dimension score
        methodological_quality: Methodological quality dimension score
        risk_of_bias: Risk of bias dimension score (inverted: 10=low risk)
        replication_status: Replication status dimension score
        final_weight: Weighted combination of all dimensions (0-10)
        dimension_weights: Weights used to compute final_weight
        study_type: Extracted study type (e.g., "RCT", "cohort")
        sample_size_n: Extracted sample size (number of participants)

    Example:
        >>> result = PaperWeightResult(
        ...     document_id=12345,
        ...     assessor_version="1.0.0",
        ...     assessed_at=datetime.now(),
        ...     study_design=DimensionScore("study_design", 8.0),
        ...     sample_size=DimensionScore("sample_size", 7.5),
        ...     methodological_quality=DimensionScore("methodological_quality", 6.5),
        ...     risk_of_bias=DimensionScore("risk_of_bias", 7.0),
        ...     replication_status=DimensionScore("replication_status", 5.0),
        ...     final_weight=7.2,
        ...     dimension_weights={
        ...         "study_design": 0.25,
        ...         "sample_size": 0.15,
        ...         "methodological_quality": 0.30,
        ...         "risk_of_bias": 0.20,
        ...         "replication_status": 0.10
        ...     },
        ...     study_type="RCT",
        ...     sample_size_n=450
        ... )
    """
    document_id: int
    assessor_version: str
    assessed_at: datetime

    # Dimension scores
    study_design: DimensionScore
    sample_size: DimensionScore
    methodological_quality: DimensionScore
    risk_of_bias: DimensionScore
    replication_status: DimensionScore

    # Final weight
    final_weight: float
    dimension_weights: Dict[str, float]

    # Metadata
    study_type: Optional[str] = None
    sample_size_n: Optional[int] = None

    def to_dict(self) -> dict:
        """
        Convert to flat dictionary for database storage.

        Returns flattened structure matching paper_weights.assessments table schema.
        """
        return {
            'document_id': self.document_id,
            'assessor_version': self.assessor_version,
            'assessed_at': self.assessed_at,
            'study_design_score': self.study_design.score,
            'sample_size_score': self.sample_size.score,
            'methodological_quality_score': self.methodological_quality.score,
            'risk_of_bias_score': self.risk_of_bias.score,
            'replication_status_score': self.replication_status.score,
            'final_weight': self.final_weight,
            'dimension_weights': json.dumps(self.dimension_weights),
            'study_type': self.study_type,
            'sample_size': self.sample_size_n
        }

    def get_all_details(self) -> List[AssessmentDetail]:
        """
        Collect all audit trail entries from all dimensions.

        Returns:
            Flat list of all AssessmentDetail objects across all dimensions
        """
        all_details = []
        for dimension_score in [
            self.study_design,
            self.sample_size,
            self.methodological_quality,
            self.risk_of_bias,
            self.replication_status
        ]:
            all_details.extend(dimension_score.details)
        return all_details

    def to_markdown(self) -> str:
        """
        Format assessment as human-readable Markdown report.

        Returns:
            Markdown-formatted assessment report with all dimensions and audit trail
        """
        lines = [
            f"# Paper Weight Assessment Report",
            f"",
            f"**Document ID:** {self.document_id}",
            f"**Study Type:** {self.study_type or 'Unknown'}",
            f"**Sample Size:** {self.sample_size_n or 'Not extracted'}",
            f"**Assessed:** {self.assessed_at.strftime(DATETIME_FORMAT)}",
            f"**Assessor Version:** {self.assessor_version}",
            f"",
            f"## Final Weight: {self.final_weight:.2f}/10",
            f"",
            f"## Dimension Scores",
            f"",
        ]

        # Add each dimension with details
        for dim_name, dim_score in [
            ("Study Design", self.study_design),
            ("Sample Size", self.sample_size),
            ("Methodological Quality", self.methodological_quality),
            ("Risk of Bias", self.risk_of_bias),
            ("Replication Status", self.replication_status)
        ]:
            lines.append(f"### {dim_name}: {dim_score.score:.2f}/10")
            lines.append("")

            if dim_score.details:
                for detail in dim_score.details:
                    lines.append(f"- **{detail.component}:** {detail.extracted_value}")
                    lines.append(f"  - Score contribution: {detail.score_contribution:.2f}")
                    if detail.reasoning:
                        lines.append(f"  - Reasoning: {detail.reasoning}")
                    if detail.evidence_text:
                        # Preserve full evidence text for audit trail integrity
                        lines.append(f"  - Evidence: *\"{detail.evidence_text}\"*")
                    lines.append("")
            else:
                lines.append("*No detailed breakdown available*")
                lines.append("")

        # Add dimension weights
        lines.append("## Dimension Weights Used")
        lines.append("")
        for dim, weight in self.dimension_weights.items():
            lines.append(f"- **{dim}:** {weight:.2f}")
        lines.append("")

        return "\n".join(lines)

    @classmethod
    def from_db_row(cls, row: dict, details: List[dict]) -> 'PaperWeightResult':
        """
        Reconstruct PaperWeightResult from database rows.

        Args:
            row: Row from paper_weights.assessments table
            details: Rows from paper_weights.assessment_details table

        Returns:
            Reconstructed PaperWeightResult object
        """
        # Parse dimension weights from JSONB
        dimension_weights = row['dimension_weights']
        if isinstance(dimension_weights, str):
            dimension_weights = json.loads(dimension_weights)

        # Group details by dimension
        dimension_details: Dict[str, List[AssessmentDetail]] = {
            'study_design': [],
            'sample_size': [],
            'methodological_quality': [],
            'risk_of_bias': [],
            'replication_status': []
        }

        for detail in details:
            dim = detail['dimension']
            if dim in dimension_details:
                dimension_details[dim].append(AssessmentDetail(
                    dimension=detail['dimension'],
                    component=detail['component'],
                    extracted_value=detail['extracted_value'],
                    score_contribution=float(detail['score_contribution']) if detail['score_contribution'] else 0.0,
                    evidence_text=detail['evidence_text'],
                    reasoning=detail['reasoning']
                ))

        # Create dimension scores
        study_design = DimensionScore(
            dimension_name='study_design',
            score=float(row['study_design_score']),
            details=dimension_details['study_design']
        )
        sample_size = DimensionScore(
            dimension_name='sample_size',
            score=float(row['sample_size_score']),
            details=dimension_details['sample_size']
        )
        methodological_quality = DimensionScore(
            dimension_name='methodological_quality',
            score=float(row['methodological_quality_score']),
            details=dimension_details['methodological_quality']
        )
        risk_of_bias = DimensionScore(
            dimension_name='risk_of_bias',
            score=float(row['risk_of_bias_score']),
            details=dimension_details['risk_of_bias']
        )
        replication_status = DimensionScore(
            dimension_name='replication_status',
            score=float(row['replication_status_score']),
            details=dimension_details['replication_status']
        )

        return cls(
            document_id=row['document_id'],
            assessor_version=row['assessor_version'],
            assessed_at=row['assessed_at'],
            study_design=study_design,
            sample_size=sample_size,
            methodological_quality=methodological_quality,
            risk_of_bias=risk_of_bias,
            replication_status=replication_status,
            final_weight=float(row['final_weight']),
            dimension_weights=dimension_weights,
            study_type=row.get('study_type'),
            sample_size_n=row.get('sample_size')
        )


# Additional imports for agent implementation
import re
import math
import logging

from .base import BaseAgent
from ..config import get_model, get_agent_config, get_ollama_host

logger = logging.getLogger(__name__)


class PaperWeightAssessmentAgent(BaseAgent):
    """
    Multi-dimensional paper weight assessment agent.

    Assesses the evidential weight of biomedical research papers across five dimensions:
    - Study design (rule-based keyword matching)
    - Sample size (rule-based regex extraction + scoring)
    - Methodological quality (LLM-based assessment - Step 5)
    - Risk of bias (LLM-based assessment - Step 5)
    - Replication status (database lookup - Step 6)

    This class implements rule-based extractors (Step 4), LLM-based assessors (Step 5),
    and database persistence with caching (Step 6).
    """

    # Priority order for study type detection (highest evidence level first)
    STUDY_TYPE_PRIORITY = [
        'systematic_review',
        'meta_analysis',
        'rct',
        'cohort_prospective',
        'cohort_retrospective',
        'case_control',
        'cross_sectional',
        'case_series',
        'case_report'
    ]

    # Constants for LLM assessors
    MAX_TEXT_LENGTH = 8000  # Maximum characters to send to LLM (avoids token limits)

    def __init__(
        self,
        model: Optional[str] = None,
        host: Optional[str] = None,
        callback: Optional[Callable[[str, str], None]] = None,
        orchestrator: Optional["AgentOrchestrator"] = None,
        show_model_info: bool = True
    ):
        """
        Initialize the PaperWeightAssessmentAgent.

        Args:
            model: The Ollama model to use (default: from config)
            host: The Ollama server host URL (default: from config)
            callback: Optional callback function for progress updates
            orchestrator: Optional orchestrator for queue-based processing
            show_model_info: Whether to display model information on initialization
        """
        # Load configuration
        self.config = self._load_config()

        # Get model and host from config if not provided
        if model is None:
            model = get_model('paper_weight_assessment_agent')
        if host is None:
            host = get_ollama_host()

        # Get agent-specific parameters
        agent_config = self.config
        temperature = agent_config.get('temperature', 0.3)
        top_p = agent_config.get('top_p', 0.9)
        self.max_tokens = agent_config.get('max_tokens', 3000)
        self.version = agent_config.get('version', '1.0.0')

        super().__init__(
            model=model,
            host=host,
            temperature=temperature,
            top_p=top_p,
            callback=callback,
            orchestrator=orchestrator,
            show_model_info=show_model_info
        )

    def _load_config(self) -> dict:
        """
        Load paper weight assessment configuration with defaults.

        Returns:
            Configuration dictionary with all paper weight settings
        """
        config = get_agent_config('paper_weight_assessment')

        # Ensure all required keys are present with defaults
        defaults = {
            'temperature': 0.3,
            'top_p': 0.9,
            'max_tokens': 3000,
            'version': '1.0.0',
            'dimension_weights': {
                'study_design': 0.25,
                'sample_size': 0.15,
                'methodological_quality': 0.30,
                'risk_of_bias': 0.20,
                'replication_status': 0.10
            },
            'study_type_hierarchy': {
                'systematic_review': 10.0,
                'meta_analysis': 10.0,
                'rct': 8.0,
                'cohort_prospective': 6.0,
                'cohort_retrospective': 5.0,
                'case_control': 4.0,
                'cross_sectional': 3.0,
                'case_series': 2.0,
                'case_report': 1.0
            },
            'study_type_keywords': {
                'systematic_review': ['systematic review', 'systematic literature review'],
                'meta_analysis': ['meta-analysis', 'meta analysis', 'pooled analysis'],
                'rct': ['randomized controlled trial', 'randomised controlled trial', 'RCT',
                       'randomized trial', 'randomised trial', 'random allocation', 'randomly assigned'],
                'cohort_prospective': ['prospective cohort', 'prospective study', 'longitudinal cohort'],
                'cohort_retrospective': ['retrospective cohort', 'retrospective study'],
                'case_control': ['case-control', 'case control study'],
                'cross_sectional': ['cross-sectional', 'cross sectional study', 'prevalence study'],
                'case_series': ['case series', 'case-series'],
                'case_report': ['case report', 'case study']
            },
            'sample_size_scoring': {
                'log_base': 10,
                'log_multiplier': 2.0,
                'power_calculation_bonus': 2.0,
                'ci_reported_bonus': 0.5
            }
        }

        # Merge defaults with loaded config (loaded config takes precedence)
        for key, value in defaults.items():
            if key not in config:
                config[key] = value
            elif isinstance(value, dict) and isinstance(config[key], dict):
                # Deep merge for nested dicts
                for subkey, subvalue in value.items():
                    if subkey not in config[key]:
                        config[key][subkey] = subvalue

        return config

    def get_agent_type(self) -> str:
        """Get the agent type identifier."""
        return "PaperWeightAssessmentAgent"

    # ========================================================================
    # Rule-Based Extractors (Step 4)
    # ========================================================================

    def _extract_study_type(self, document: dict) -> DimensionScore:
        """
        Extract study type using keyword matching.

        Matches keywords from config against abstract and methods section.
        Uses priority hierarchy: systematic review > RCT > cohort > etc.

        Args:
            document: Document dict with 'abstract' and optional 'methods_text' fields

        Returns:
            DimensionScore for study design with audit trail
        """
        # Get text to search
        abstract = document.get('abstract', '') or ''
        methods = document.get('methods_text', '') or ''
        search_text = f"{abstract} {methods}".lower()

        # Get config
        keywords_config = self.config.get('study_type_keywords', {})
        hierarchy_config = self.config.get('study_type_hierarchy', {})

        # Try each study type in priority order
        for study_type in self.STUDY_TYPE_PRIORITY:
            keywords = keywords_config.get(study_type, [])
            for keyword in keywords:
                if keyword.lower() in search_text:
                    # Found match - get score from hierarchy
                    score = hierarchy_config.get(study_type, 5.0)

                    # Create dimension score with audit trail
                    dimension_score = DimensionScore(
                        dimension_name='study_design',
                        score=score
                    )

                    # Find evidence context (50 chars before/after keyword)
                    evidence_text = self._extract_context(search_text, keyword.lower())

                    dimension_score.add_detail(
                        component='study_type',
                        value=study_type,
                        contribution=score,
                        evidence=evidence_text,
                        reasoning=f"Matched keyword '{keyword}' indicating {study_type.replace('_', ' ')}"
                    )

                    return dimension_score

        # No match found - default to unknown
        dimension_score = DimensionScore(
            dimension_name='study_design',
            score=5.0  # Neutral score
        )
        dimension_score.add_detail(
            component='study_type',
            value='unknown',
            contribution=5.0,
            reasoning='No study type keywords matched - assigned neutral score'
        )

        return dimension_score

    def _extract_context(self, text: str, keyword: str, context_chars: int = 50) -> str:
        """
        Extract text context around a keyword.

        Args:
            text: Full text to search
            keyword: Keyword to find
            context_chars: Characters to include before/after keyword

        Returns:
            Text snippet with context around keyword
        """
        keyword_pos = text.find(keyword)
        if keyword_pos == -1:
            return ""

        start = max(0, keyword_pos - context_chars)
        end = min(len(text), keyword_pos + len(keyword) + context_chars)

        context = text[start:end]

        # Add ellipsis if truncated
        if start > 0:
            context = "..." + context
        if end < len(text):
            context = context + "..."

        return context

    def _extract_sample_size(self, document: dict) -> DimensionScore:
        """
        Extract sample size and calculate score.

        Uses regex patterns to find sample size mentions, applies logarithmic
        scoring, and adds bonuses for power calculation and CI reporting.

        Args:
            document: Document dict with 'abstract' and optional 'methods_text' fields

        Returns:
            DimensionScore for sample size with audit trail
        """
        # Get text to search
        abstract = document.get('abstract', '') or ''
        methods = document.get('methods_text', '') or ''
        search_text = f"{abstract} {methods}"

        # Extract sample size
        sample_size = self._find_sample_size(search_text)

        if sample_size is None:
            # No sample size found
            dimension_score = DimensionScore(
                dimension_name='sample_size',
                score=0.0
            )
            dimension_score.add_detail(
                component='extracted_n',
                value='not_found',
                contribution=0.0,
                reasoning='No sample size could be extracted from text'
            )
            return dimension_score

        # Calculate base score using logarithmic scaling
        base_score = self._calculate_sample_size_score(sample_size)

        # Create dimension score
        dimension_score = DimensionScore(
            dimension_name='sample_size',
            score=base_score
        )

        # Get scoring config
        scoring_config = self.config.get('sample_size_scoring', {})
        log_multiplier = scoring_config.get('log_multiplier', 2.0)

        # Add base score detail
        dimension_score.add_detail(
            component='extracted_n',
            value=str(sample_size),
            contribution=base_score,
            reasoning=f"Log10({sample_size}) * {log_multiplier} = {base_score:.2f}"
        )

        # Check for power calculation
        if self._has_power_calculation(search_text):
            power_bonus = scoring_config.get('power_calculation_bonus', 2.0)
            new_score = min(10.0, dimension_score.score + power_bonus)
            dimension_score.score = new_score
            dimension_score.add_detail(
                component='power_calculation',
                value='yes',
                contribution=power_bonus,
                evidence=self._find_power_calc_context(search_text),
                reasoning=f'Power calculation mentioned, bonus +{power_bonus}'
            )

        # Check for confidence interval reporting
        if self._has_ci_reporting(search_text):
            ci_bonus = scoring_config.get('ci_reported_bonus', 0.5)
            new_score = min(10.0, dimension_score.score + ci_bonus)
            dimension_score.score = new_score
            dimension_score.add_detail(
                component='ci_reporting',
                value='yes',
                contribution=ci_bonus,
                reasoning=f'Confidence intervals reported, bonus +{ci_bonus}'
            )

        return dimension_score

    def _find_sample_size(self, text: str) -> Optional[int]:
        """
        Find sample size in text using regex patterns.

        Returns largest number found (usually total sample size).

        Args:
            text: Text to search

        Returns:
            Sample size (int) or None if not found
        """
        patterns = [
            r'n\s*=\s*(\d+)',  # n = 450
            r'N\s*=\s*(\d+)',  # N = 450
            r'(\d+)\s+participants',  # 450 participants
            r'(\d+)\s+subjects',  # 450 subjects
            r'(\d+)\s+patients',  # 450 patients
            r'sample\s+size\s+of\s+(\d+)',  # sample size of 450
            r'total\s+of\s+(\d+)\s+(?:participants|subjects|patients)',  # total of 450 participants
            r'enrolled\s+(\d+)\s+(?:participants|subjects|patients)',  # enrolled 450 participants
            r'recruited\s+(\d+)\s+(?:participants|subjects|patients)',  # recruited 450 participants
        ]

        found_sizes = []

        for pattern in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                size = int(match.group(1))
                # Filter out unrealistic values (too small or too large)
                if 5 <= size <= 1000000:  # Reasonable range
                    found_sizes.append(size)

        if not found_sizes:
            return None

        # Return largest (usually total sample size)
        return max(found_sizes)

    def _calculate_sample_size_score(self, n: int) -> float:
        """
        Calculate sample size score using logarithmic scaling.

        Formula: min(10, log10(n) * log_multiplier)

        Args:
            n: Sample size

        Returns:
            Score (0-10)
        """
        scoring_config = self.config.get('sample_size_scoring', {})
        log_multiplier = scoring_config.get('log_multiplier', 2.0)

        if n <= 0:
            return 0.0

        score = math.log10(n) * log_multiplier
        return min(10.0, max(0.0, score))

    def _has_power_calculation(self, text: str) -> bool:
        """
        Check if text mentions power calculation.

        Args:
            text: Text to search

        Returns:
            True if power calculation mentioned
        """
        keywords = [
            'power calculation',
            'power analysis',
            'sample size calculation',
            'calculated sample size',
            'statistical power',
            'power to detect'
        ]

        text_lower = text.lower()
        return any(keyword in text_lower for keyword in keywords)

    def _find_power_calc_context(self, text: str) -> str:
        """
        Find context around power calculation mention.

        Args:
            text: Text to search

        Returns:
            Context string around power calculation mention
        """
        keywords = [
            'power calculation',
            'power analysis',
            'sample size calculation'
        ]

        text_lower = text.lower()
        for keyword in keywords:
            if keyword in text_lower:
                return self._extract_context(text_lower, keyword)

        return ""

    def _has_ci_reporting(self, text: str) -> bool:
        """
        Check if text reports confidence intervals.

        Args:
            text: Text to search

        Returns:
            True if confidence intervals are reported
        """
        patterns = [
            r'confidence interval',
            r'\bCI\b',
            r'95%\s*CI',
            r'\[\s*\d+\.?\d*\s*,\s*\d+\.?\d*\s*\]',  # [1.2, 3.4]
            r'\(\s*\d+\.?\d*\s*-\s*\d+\.?\d*\s*\)',  # (1.2-3.4)
        ]

        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True

        return False

    def get_dimension_weights(self) -> Dict[str, float]:
        """
        Get dimension weights from configuration.

        Returns:
            Dictionary mapping dimension names to their weights
        """
        return self.config.get('dimension_weights', {
            'study_design': 0.25,
            'sample_size': 0.15,
            'methodological_quality': 0.30,
            'risk_of_bias': 0.20,
            'replication_status': 0.10
        })

    # ========================================================================
    # LLM-Based Assessors (Step 5)
    # ========================================================================

    def _prepare_text_for_analysis(self, document: Dict[str, Any]) -> str:
        """
        Prepare document text for LLM analysis.

        Combines title, abstract and full text (if available), limits length
        to avoid token limits.

        Args:
            document: Document dict with 'title', 'abstract', 'full_text' fields

        Returns:
            Prepared text string suitable for LLM prompt
        """
        title = document.get('title', '') or ''
        abstract = document.get('abstract', '') or ''
        full_text = document.get('full_text', '') or ''

        # Prefer full text if available, otherwise use abstract
        if full_text:
            text = f"TITLE: {title}\n\nFULL TEXT:\n{full_text}"
        else:
            text = f"TITLE: {title}\n\nABSTRACT:\n{abstract}"

        # Limit to MAX_TEXT_LENGTH characters to avoid token limits
        if len(text) > self.MAX_TEXT_LENGTH:
            text = text[:self.MAX_TEXT_LENGTH] + "\n\n[Text truncated...]"
            logger.debug(f"Truncated text to {self.MAX_TEXT_LENGTH} characters")

        return text

    def _build_methodological_quality_prompt(self, text: str) -> str:
        """
        Build prompt for methodological quality assessment.

        Args:
            text: Prepared document text

        Returns:
            Prompt string for LLM
        """
        return f"""You are an expert in biomedical research methodology. Analyze the following research paper and assess its methodological quality across six components.

PAPER TEXT:
{text}

TASK:
Analyze the methodological quality and provide assessments for each component:

1. RANDOMIZATION (0-2 points):
   - 0: No randomization or inadequate sequence generation
   - 1: Randomization mentioned but method unclear
   - 2: Proper random sequence generation (e.g., computer-generated, random number table)

2. BLINDING (0-3 points):
   - 0: No blinding
   - 1: Single-blind (participants OR assessors)
   - 2: Double-blind (participants AND assessors)
   - 3: Triple-blind (participants, assessors, AND data analysts)

3. ALLOCATION CONCEALMENT (0-1.5 points):
   - 0: No allocation concealment or inadequate
   - 0.75: Unclear or partially described
   - 1.5: Proper allocation concealment (e.g., sealed envelopes, central randomization)

4. PROTOCOL PREREGISTRATION (0-1.5 points):
   - 0: No protocol registration mentioned
   - 0.75: Protocol mentioned but not verified
   - 1.5: Protocol clearly registered before study (e.g., ClinicalTrials.gov, registry number provided)

5. ITT ANALYSIS (0-1 points):
   - 0: No ITT analysis or per-protocol only
   - 0.5: Modified ITT or unclear
   - 1: Clear intention-to-treat analysis

6. ATTRITION HANDLING (0-1 points):
   - Extract dropout/attrition rate
   - Assess quality of handling (imputation methods, sensitivity analysis)
   - Score based on rate and handling quality

OUTPUT FORMAT (JSON):
{{
  "randomization": {{
    "score": <0-2>,
    "evidence": "<quote from paper>",
    "reasoning": "<explanation>"
  }},
  "blinding": {{
    "score": <0-3>,
    "evidence": "<quote from paper>",
    "reasoning": "<explanation>"
  }},
  "allocation_concealment": {{
    "score": <0-1.5>,
    "evidence": "<quote from paper>",
    "reasoning": "<explanation>"
  }},
  "protocol_preregistration": {{
    "score": <0-1.5>,
    "evidence": "<quote from paper>",
    "reasoning": "<explanation>"
  }},
  "itt_analysis": {{
    "score": <0-1>,
    "evidence": "<quote from paper>",
    "reasoning": "<explanation>"
  }},
  "attrition_handling": {{
    "score": <0-1>,
    "attrition_rate": <decimal or null>,
    "evidence": "<quote from paper>",
    "reasoning": "<explanation>"
  }}
}}

CRITICAL REQUIREMENTS:
- Extract ONLY information that is ACTUALLY PRESENT in the text
- DO NOT invent, assume, or fabricate any information
- If information is unclear or not mentioned, score it as 0 and explain why
- Be specific and evidence-based in your assessment
- Provide exact quotes from the paper as evidence when available

Provide ONLY the JSON output, no additional text."""

    def _calculate_methodological_quality_score(self, components: Dict[str, Any]) -> DimensionScore:
        """
        Calculate methodological quality score from component assessments.

        Args:
            components: Parsed component assessments from LLM

        Returns:
            DimensionScore with full audit trail
        """
        dimension_score = DimensionScore(
            dimension_name='methodological_quality',
            score=0.0
        )

        # Add each component
        for component_name, component_data in components.items():
            if not isinstance(component_data, dict):
                continue

            score_contribution = float(component_data.get('score', 0.0))
            evidence = component_data.get('evidence', '')
            reasoning = component_data.get('reasoning', '')

            # Handle attrition_rate if present
            value = str(score_contribution)
            if component_name == 'attrition_handling':
                attrition_rate = component_data.get('attrition_rate')
                if attrition_rate is not None:
                    value = f"{score_contribution} (attrition rate: {attrition_rate})"

            dimension_score.add_detail(
                component=component_name,
                value=value,
                contribution=score_contribution,
                evidence=evidence,
                reasoning=reasoning
            )

            dimension_score.score += score_contribution

        # Cap at 10.0
        dimension_score.score = min(10.0, dimension_score.score)

        return dimension_score

    def _assess_methodological_quality(
        self,
        document: Dict[str, Any],
        study_assessment: Optional[Dict[str, Any]] = None
    ) -> DimensionScore:
        """
        Assess methodological quality using LLM analysis.

        Evaluates: randomization, blinding, allocation concealment,
        protocol preregistration, ITT analysis, attrition handling.

        Args:
            document: Document dict with 'abstract', 'full_text' fields
            study_assessment: Optional StudyAssessmentAgent output to leverage

        Returns:
            DimensionScore for methodological quality with detailed audit trail
        """
        # Check if we can leverage StudyAssessmentAgent output
        if study_assessment:
            result = self._extract_mq_from_study_assessment(study_assessment, document)
            if result is not None:
                return result

        try:
            # Prepare text for analysis
            text = self._prepare_text_for_analysis(document)

            # Build LLM prompt
            prompt = self._build_methodological_quality_prompt(text)

            # Call LLM with JSON parsing and retry logic
            components = self._generate_and_parse_json(
                prompt,
                max_retries=3,
                retry_context="methodological quality assessment",
                num_predict=self.max_tokens
            )

            # Calculate score
            dimension_score = self._calculate_methodological_quality_score(components)

            logger.info(
                f"Methodological quality assessment complete: score={dimension_score.score:.2f}/10"
            )

            return dimension_score

        except Exception as e:
            # Log error and return degraded score
            logger.error(f"Error in methodological quality assessment: {e}")

            dimension_score = DimensionScore(
                dimension_name='methodological_quality',
                score=5.0  # Neutral score on error
            )
            dimension_score.add_detail(
                component='error',
                value='assessment_failed',
                contribution=5.0,
                reasoning=f'LLM assessment failed: {str(e)}'
            )
            return dimension_score

    def _build_risk_of_bias_prompt(self, text: str) -> str:
        """
        Build prompt for risk of bias assessment.

        Args:
            text: Prepared document text

        Returns:
            Prompt string for LLM
        """
        return f"""You are an expert in biomedical research methodology and bias assessment. Analyze the following research paper and assess its risk of bias across four domains.

PAPER TEXT:
{text}

TASK:
Assess risk of bias using INVERTED SCALE (higher score = lower risk of bias):

1. SELECTION BIAS (0-2.5 points):
   - 0: High risk (convenience sampling, no clear criteria)
   - 1.25: Moderate risk (some limitations in sampling)
   - 2.5: Low risk (random/consecutive sampling, clear inclusion/exclusion criteria)

2. PERFORMANCE BIAS (0-2.5 points):
   - 0: High risk (no blinding, unstandardized interventions)
   - 1.25: Moderate risk (partial blinding or standardization)
   - 2.5: Low risk (proper blinding, standardized protocols)

3. DETECTION BIAS (0-2.5 points):
   - 0: High risk (unblinded outcome assessment)
   - 1.25: Moderate risk (partially blinded or objective outcomes only)
   - 2.5: Low risk (blinded outcome assessment for all outcomes)

4. REPORTING BIAS (0-2.5 points):
   - 0: High risk (selective reporting, outcomes not pre-specified)
   - 1.25: Moderate risk (some evidence of selective reporting)
   - 2.5: Low risk (all pre-specified outcomes reported, protocol available)

OUTPUT FORMAT (JSON):
{{
  "selection_bias": {{
    "score": <0-2.5>,
    "risk_level": "<high|moderate|low>",
    "evidence": "<quote from paper>",
    "reasoning": "<explanation>"
  }},
  "performance_bias": {{
    "score": <0-2.5>,
    "risk_level": "<high|moderate|low>",
    "evidence": "<quote from paper>",
    "reasoning": "<explanation>"
  }},
  "detection_bias": {{
    "score": <0-2.5>,
    "risk_level": "<high|moderate|low>",
    "evidence": "<quote from paper>",
    "reasoning": "<explanation>"
  }},
  "reporting_bias": {{
    "score": <0-2.5>,
    "risk_level": "<high|moderate|low>",
    "evidence": "<quote from paper>",
    "reasoning": "<explanation>"
  }}
}}

CRITICAL REQUIREMENTS:
- Extract ONLY information that is ACTUALLY PRESENT in the text
- DO NOT invent, assume, or fabricate any information
- If information is unclear or not mentioned, assume high risk (score 0) and explain why
- Be specific and evidence-based in your assessment
- Provide exact quotes from the paper as evidence when available

Provide ONLY the JSON output, no additional text."""

    def _calculate_risk_of_bias_score(self, components: Dict[str, Any]) -> DimensionScore:
        """
        Calculate risk of bias score from component assessments.

        Args:
            components: Parsed component assessments from LLM

        Returns:
            DimensionScore with full audit trail
        """
        dimension_score = DimensionScore(
            dimension_name='risk_of_bias',
            score=0.0
        )

        # Add each component
        for component_name, component_data in components.items():
            if not isinstance(component_data, dict):
                continue

            score_contribution = float(component_data.get('score', 0.0))
            risk_level = component_data.get('risk_level', 'unknown')
            evidence = component_data.get('evidence', '')
            reasoning = component_data.get('reasoning', '')

            dimension_score.add_detail(
                component=component_name,
                value=f"{risk_level} risk ({score_contribution})",
                contribution=score_contribution,
                evidence=evidence,
                reasoning=reasoning
            )

            dimension_score.score += score_contribution

        # Cap at 10.0
        dimension_score.score = min(10.0, dimension_score.score)

        return dimension_score

    def _assess_risk_of_bias(
        self,
        document: Dict[str, Any],
        study_assessment: Optional[Dict[str, Any]] = None
    ) -> DimensionScore:
        """
        Assess risk of bias using LLM analysis.

        Evaluates: selection bias, performance bias, detection bias, reporting bias.
        Uses INVERTED SCALE: 10 = low risk, 0 = high risk.

        Args:
            document: Document dict with 'abstract', 'full_text' fields
            study_assessment: Optional StudyAssessmentAgent output to leverage

        Returns:
            DimensionScore for risk of bias with detailed audit trail
        """
        # Check if we can leverage StudyAssessmentAgent output
        if study_assessment:
            result = self._extract_rob_from_study_assessment(study_assessment, document)
            if result is not None:
                return result

        try:
            # Prepare text
            text = self._prepare_text_for_analysis(document)

            # Build LLM prompt
            prompt = self._build_risk_of_bias_prompt(text)

            # Call LLM with JSON parsing and retry logic
            components = self._generate_and_parse_json(
                prompt,
                max_retries=3,
                retry_context="risk of bias assessment",
                num_predict=self.max_tokens
            )

            # Calculate score
            dimension_score = self._calculate_risk_of_bias_score(components)

            logger.info(
                f"Risk of bias assessment complete: score={dimension_score.score:.2f}/10 (higher=lower risk)"
            )

            return dimension_score

        except Exception as e:
            # Log error and return degraded score
            logger.error(f"Error in risk of bias assessment: {e}")

            dimension_score = DimensionScore(
                dimension_name='risk_of_bias',
                score=5.0  # Neutral score on error
            )
            dimension_score.add_detail(
                component='error',
                value='assessment_failed',
                contribution=5.0,
                reasoning=f'LLM assessment failed: {str(e)}'
            )
            return dimension_score

    # ========================================================================
    # StudyAssessmentAgent Integration (Step 5)
    # ========================================================================

    def _extract_mq_from_study_assessment(
        self,
        study_assessment: Dict[str, Any],
        document: Dict[str, Any]
    ) -> Optional[DimensionScore]:
        """
        Extract methodological quality from StudyAssessmentAgent output.

        If StudyAssessmentAgent has already analyzed the paper, reuse
        relevant assessments to avoid duplicate LLM calls.

        Args:
            study_assessment: Output from StudyAssessmentAgent (as dict)
            document: Document dict (for fallback if needed)

        Returns:
            DimensionScore for methodological quality, or None if extraction fails
        """
        try:
            dimension_score = DimensionScore(
                dimension_name='methodological_quality',
                score=0.0
            )

            total_score = 0.0

            # Extract randomization from is_randomized
            is_randomized = study_assessment.get('is_randomized', False)
            if is_randomized:
                randomization_score = 2.0
                dimension_score.add_detail(
                    component='randomization',
                    value='yes',
                    contribution=randomization_score,
                    reasoning='Extracted from StudyAssessmentAgent: is_randomized=True'
                )
                total_score += randomization_score
            else:
                dimension_score.add_detail(
                    component='randomization',
                    value='no',
                    contribution=0.0,
                    reasoning='Extracted from StudyAssessmentAgent: is_randomized=False or not specified'
                )

            # Extract blinding
            is_double_blinded = study_assessment.get('is_double_blinded', False)
            is_blinded = study_assessment.get('is_blinded', False)
            if is_double_blinded:
                blinding_score = 2.0  # Double-blind
                dimension_score.add_detail(
                    component='blinding',
                    value='double-blind',
                    contribution=blinding_score,
                    reasoning='Extracted from StudyAssessmentAgent: is_double_blinded=True'
                )
                total_score += blinding_score
            elif is_blinded:
                blinding_score = 1.0  # Single-blind
                dimension_score.add_detail(
                    component='blinding',
                    value='single-blind',
                    contribution=blinding_score,
                    reasoning='Extracted from StudyAssessmentAgent: is_blinded=True (not double)'
                )
                total_score += blinding_score
            else:
                dimension_score.add_detail(
                    component='blinding',
                    value='no blinding',
                    contribution=0.0,
                    reasoning='Extracted from StudyAssessmentAgent: no blinding detected'
                )

            # Check quality_score to estimate remaining components
            quality_score_raw = study_assessment.get('quality_score', 5.0)
            # Handle None or invalid values
            quality_score = float(quality_score_raw) if quality_score_raw is not None else 5.0
            # Clamp to valid range
            quality_score = max(0.0, min(10.0, quality_score))

            # Map quality_score (0-10) to remaining components estimate
            # quality_score reflects overall methodological quality
            # We allocate remaining 5 points (allocation_concealment + protocol + ITT + attrition)
            # based on quality_score proportion
            remaining_max = 5.0  # Max remaining points
            remaining_proportion = quality_score / 10.0
            remaining_estimate = remaining_max * remaining_proportion

            dimension_score.add_detail(
                component='other_components',
                value=f'estimated from quality_score={quality_score:.1f}',
                contribution=remaining_estimate,
                reasoning=f'Estimated from StudyAssessmentAgent quality_score ({quality_score:.1f}/10) - covers allocation concealment, protocol registration, ITT analysis, and attrition handling'
            )
            total_score += remaining_estimate

            dimension_score.score = min(10.0, total_score)

            logger.info(
                f"Extracted methodological quality from StudyAssessmentAgent: score={dimension_score.score:.2f}/10"
            )

            return dimension_score

        except Exception as e:
            logger.warning(f"Failed to extract MQ from StudyAssessmentAgent: {e}")
            return None  # Fall back to direct LLM assessment

    def _extract_rob_from_study_assessment(
        self,
        study_assessment: Dict[str, Any],
        document: Dict[str, Any]
    ) -> Optional[DimensionScore]:
        """
        Extract risk of bias from StudyAssessmentAgent output.

        Similar to methodological quality extraction.

        Args:
            study_assessment: Output from StudyAssessmentAgent (as dict)
            document: Document dict (for fallback if needed)

        Returns:
            DimensionScore for risk of bias, or None if extraction fails
        """
        try:
            dimension_score = DimensionScore(
                dimension_name='risk_of_bias',
                score=0.0
            )

            total_score = 0.0

            # Risk level mapping to scores (inverted: high risk = low score)
            risk_level_scores = {
                'low': 2.5,
                'moderate': 1.25,
                'high': 0.0,
                'unclear': 0.625  # Between moderate and high
            }

            # Extract selection bias
            selection_risk = study_assessment.get('selection_bias_risk', 'unclear')
            if selection_risk:
                selection_score = risk_level_scores.get(selection_risk.lower(), 0.625)
                dimension_score.add_detail(
                    component='selection_bias',
                    value=f'{selection_risk} risk ({selection_score})',
                    contribution=selection_score,
                    reasoning=f'Extracted from StudyAssessmentAgent: selection_bias_risk={selection_risk}'
                )
                total_score += selection_score

            # Extract performance bias
            performance_risk = study_assessment.get('performance_bias_risk', 'unclear')
            if performance_risk:
                performance_score = risk_level_scores.get(performance_risk.lower(), 0.625)
                dimension_score.add_detail(
                    component='performance_bias',
                    value=f'{performance_risk} risk ({performance_score})',
                    contribution=performance_score,
                    reasoning=f'Extracted from StudyAssessmentAgent: performance_bias_risk={performance_risk}'
                )
                total_score += performance_score

            # Extract detection bias
            detection_risk = study_assessment.get('detection_bias_risk', 'unclear')
            if detection_risk:
                detection_score = risk_level_scores.get(detection_risk.lower(), 0.625)
                dimension_score.add_detail(
                    component='detection_bias',
                    value=f'{detection_risk} risk ({detection_score})',
                    contribution=detection_score,
                    reasoning=f'Extracted from StudyAssessmentAgent: detection_bias_risk={detection_risk}'
                )
                total_score += detection_score

            # Extract reporting bias
            reporting_risk = study_assessment.get('reporting_bias_risk', 'unclear')
            if reporting_risk:
                reporting_score = risk_level_scores.get(reporting_risk.lower(), 0.625)
                dimension_score.add_detail(
                    component='reporting_bias',
                    value=f'{reporting_risk} risk ({reporting_score})',
                    contribution=reporting_score,
                    reasoning=f'Extracted from StudyAssessmentAgent: reporting_bias_risk={reporting_risk}'
                )
                total_score += reporting_score

            dimension_score.score = min(10.0, total_score)

            logger.info(
                f"Extracted risk of bias from StudyAssessmentAgent: score={dimension_score.score:.2f}/10"
            )

            return dimension_score

        except Exception as e:
            logger.warning(f"Failed to extract RoB from StudyAssessmentAgent: {e}")
            return None  # Fall back to direct LLM assessment

    # ========================================================================
    # Database Persistence and Caching (Step 6)
    # ========================================================================

    def _get_db_connection(self):
        """
        Create database connection using environment variables.

        Returns:
            psycopg connection object
        """
        import psycopg
        import os

        return psycopg.connect(
            dbname=os.getenv('POSTGRES_DB', 'knowledgebase'),
            user=os.getenv('POSTGRES_USER'),
            password=os.getenv('POSTGRES_PASSWORD'),
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=os.getenv('POSTGRES_PORT', '5432')
        )

    def _get_cached_assessment(self, document_id: int) -> Optional[PaperWeightResult]:
        """
        Retrieve cached assessment from database.

        Checks for existing assessment with matching document_id and assessor_version.

        Args:
            document_id: Database ID of document

        Returns:
            PaperWeightResult if cached, None otherwise
        """
        version = self.config.get('version', '1.0.0')

        try:
            with self._get_db_connection() as conn:
                with conn.cursor() as cur:
                    # Fetch assessment
                    cur.execute("""
                        SELECT
                            assessment_id,
                            document_id,
                            assessed_at,
                            assessor_version,
                            study_design_score,
                            sample_size_score,
                            methodological_quality_score,
                            risk_of_bias_score,
                            replication_status_score,
                            final_weight,
                            dimension_weights,
                            study_type,
                            sample_size
                        FROM paper_weights.assessments
                        WHERE document_id = %s AND assessor_version = %s
                    """, (document_id, version))

                    row = cur.fetchone()
                    if not row:
                        return None

                    assessment_id = row[0]

                    # Fetch assessment details
                    cur.execute("""
                        SELECT
                            dimension,
                            component,
                            extracted_value,
                            score_contribution,
                            evidence_text,
                            reasoning
                        FROM paper_weights.assessment_details
                        WHERE assessment_id = %s
                        ORDER BY detail_id
                    """, (assessment_id,))

                    details = cur.fetchall()

                    # Convert to PaperWeightResult
                    return self._reconstruct_result_from_db(row, details)

        except Exception as e:
            logger.error(f"Error fetching cached assessment: {e}")
            return None

    def _reconstruct_result_from_db(self, assessment_row: tuple, detail_rows: list) -> PaperWeightResult:
        """
        Reconstruct PaperWeightResult from database rows.

        Args:
            assessment_row: Row from paper_weights.assessments
            detail_rows: Rows from paper_weights.assessment_details

        Returns:
            Reconstructed PaperWeightResult
        """
        # Unpack assessment row
        (assessment_id, document_id, assessed_at, assessor_version,
         study_design_score, sample_size_score, methodological_quality_score,
         risk_of_bias_score, replication_status_score, final_weight,
         dimension_weights, study_type, sample_size_n) = assessment_row

        # Parse dimension weights (JSONB)
        if isinstance(dimension_weights, str):
            dimension_weights = json.loads(dimension_weights)

        # Group details by dimension
        dimension_details: Dict[str, List[AssessmentDetail]] = {
            'study_design': [],
            'sample_size': [],
            'methodological_quality': [],
            'risk_of_bias': [],
            'replication_status': []
        }

        for detail_row in detail_rows:
            (dimension, component, extracted_value, score_contribution,
             evidence_text, reasoning) = detail_row

            if dimension in dimension_details:
                dimension_details[dimension].append(AssessmentDetail(
                    dimension=dimension,
                    component=component,
                    extracted_value=extracted_value,
                    score_contribution=float(score_contribution) if score_contribution else 0.0,
                    evidence_text=evidence_text,
                    reasoning=reasoning
                ))

        # Create dimension scores
        study_design = DimensionScore(
            dimension_name='study_design',
            score=float(study_design_score),
            details=dimension_details['study_design']
        )

        sample_size_dim = DimensionScore(
            dimension_name='sample_size',
            score=float(sample_size_score),
            details=dimension_details['sample_size']
        )

        methodological_quality = DimensionScore(
            dimension_name='methodological_quality',
            score=float(methodological_quality_score),
            details=dimension_details['methodological_quality']
        )

        risk_of_bias = DimensionScore(
            dimension_name='risk_of_bias',
            score=float(risk_of_bias_score),
            details=dimension_details['risk_of_bias']
        )

        replication_status = DimensionScore(
            dimension_name='replication_status',
            score=float(replication_status_score),
            details=dimension_details['replication_status']
        )

        # Create result
        return PaperWeightResult(
            document_id=document_id,
            assessor_version=assessor_version,
            assessed_at=assessed_at,
            study_design=study_design,
            sample_size=sample_size_dim,
            methodological_quality=methodological_quality,
            risk_of_bias=risk_of_bias,
            replication_status=replication_status,
            final_weight=float(final_weight),
            dimension_weights=dimension_weights,
            study_type=study_type,
            sample_size_n=sample_size_n
        )

    def _store_assessment(self, result: PaperWeightResult) -> None:
        """
        Store assessment in database with full audit trail.

        Inserts into both paper_weights.assessments and paper_weights.assessment_details.
        Uses ON CONFLICT to handle re-assessments with same version.

        Args:
            result: PaperWeightResult to store
        """
        try:
            with self._get_db_connection() as conn:
                with conn.cursor() as cur:
                    # Insert/update assessment
                    cur.execute("""
                        INSERT INTO paper_weights.assessments (
                            document_id,
                            assessor_version,
                            assessed_at,
                            study_design_score,
                            sample_size_score,
                            methodological_quality_score,
                            risk_of_bias_score,
                            replication_status_score,
                            final_weight,
                            dimension_weights,
                            study_type,
                            sample_size
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        )
                        ON CONFLICT (document_id, assessor_version)
                        DO UPDATE SET
                            assessed_at = EXCLUDED.assessed_at,
                            study_design_score = EXCLUDED.study_design_score,
                            sample_size_score = EXCLUDED.sample_size_score,
                            methodological_quality_score = EXCLUDED.methodological_quality_score,
                            risk_of_bias_score = EXCLUDED.risk_of_bias_score,
                            replication_status_score = EXCLUDED.replication_status_score,
                            final_weight = EXCLUDED.final_weight,
                            dimension_weights = EXCLUDED.dimension_weights,
                            study_type = EXCLUDED.study_type,
                            sample_size = EXCLUDED.sample_size
                        RETURNING assessment_id
                    """, (
                        result.document_id,
                        result.assessor_version,
                        result.assessed_at,
                        result.study_design.score,
                        result.sample_size.score,
                        result.methodological_quality.score,
                        result.risk_of_bias.score,
                        result.replication_status.score,
                        result.final_weight,
                        json.dumps(result.dimension_weights),
                        result.study_type,
                        result.sample_size_n
                    ))

                    assessment_id = cur.fetchone()[0]

                    # Delete old details (if updating)
                    cur.execute("""
                        DELETE FROM paper_weights.assessment_details
                        WHERE assessment_id = %s
                    """, (assessment_id,))

                    # Insert new details
                    all_details = result.get_all_details()
                    for detail in all_details:
                        cur.execute("""
                            INSERT INTO paper_weights.assessment_details (
                                assessment_id,
                                dimension,
                                component,
                                extracted_value,
                                score_contribution,
                                evidence_text,
                                reasoning
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """, (
                            assessment_id,
                            detail.dimension,
                            detail.component,
                            detail.extracted_value,
                            detail.score_contribution,
                            detail.evidence_text,
                            detail.reasoning
                        ))

                    conn.commit()

        except Exception as e:
            logger.error(f"Error storing assessment: {e}")
            raise

    def _get_document(self, document_id: int) -> dict:
        """
        Fetch document from database by ID.

        Args:
            document_id: Database ID of document

        Returns:
            Document dict with title, abstract, and full_text fields

        Raises:
            ValueError: If document not found
        """
        try:
            with self._get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT
                            id,
                            title,
                            abstract,
                            full_text
                        FROM public.document
                        WHERE id = %s
                    """, (document_id,))

                    row = cur.fetchone()
                    if not row:
                        raise ValueError(f"Document {document_id} not found")

                    return {
                        'id': row[0],
                        'title': row[1],
                        'abstract': row[2],
                        'full_text': row[3]
                    }

        except Exception as e:
            logger.error(f"Error fetching document {document_id}: {e}")
            raise

    def _check_replication_status(self, document_id: int) -> DimensionScore:
        """
        Check replication status from database.

        Queries paper_weights.replications table for this document.
        Initially manual entry only - automated discovery is future work.

        Args:
            document_id: Database ID of document

        Returns:
            DimensionScore for replication status
        """
        try:
            with self._get_db_connection() as conn:
                with conn.cursor() as cur:
                    # Check for replications
                    cur.execute("""
                        SELECT
                            replication_id,
                            replication_type,
                            quality_comparison,
                            confidence
                        FROM paper_weights.replications
                        WHERE source_document_id = %s
                        AND replication_type = 'confirms'
                    """, (document_id,))

                    replications = cur.fetchall()

                    if not replications:
                        # No replications found
                        dimension_score = DimensionScore(
                            dimension_name='replication_status',
                            score=0.0
                        )
                        dimension_score.add_detail(
                            component='replication_count',
                            value='0',
                            contribution=0.0,
                            reasoning='No confirming replications found in database'
                        )
                        return dimension_score

                    # Calculate score based on replications
                    replication_count = len(replications)
                    quality_comparison = replications[0][2]  # First replication quality

                    # Scoring logic
                    if replication_count == 1 and quality_comparison == 'comparable':
                        score = 5.0
                    elif replication_count == 1 and quality_comparison == 'higher':
                        score = 8.0
                    elif replication_count >= 2 and quality_comparison == 'comparable':
                        score = 8.0
                    elif replication_count >= 2 and quality_comparison == 'higher':
                        score = 10.0
                    else:
                        score = 3.0  # Lower quality replications

                    dimension_score = DimensionScore(
                        dimension_name='replication_status',
                        score=score
                    )

                    dimension_score.add_detail(
                        component='replication_count',
                        value=str(replication_count),
                        contribution=score,
                        reasoning=f'{replication_count} confirming replications found (quality: {quality_comparison})'
                    )

                    return dimension_score

        except Exception as e:
            logger.error(f"Error checking replication status: {e}")

            # Return zero score on error
            dimension_score = DimensionScore(
                dimension_name='replication_status',
                score=0.0
            )
            dimension_score.add_detail(
                component='error',
                value='query_failed',
                contribution=0.0,
                reasoning=f'Database query failed: {str(e)}'
            )
            return dimension_score

    def _compute_final_weight(self, dimension_scores: Dict[str, DimensionScore]) -> float:
        """
        Compute final weight from dimension scores.

        Formula: final_weight = sum(dimension_score * weight)

        Args:
            dimension_scores: Dict mapping dimension names to DimensionScore objects

        Returns:
            Final weight (0-10)
        """
        weights = self.get_dimension_weights()

        final_weight = 0.0
        for dim_name, dim_score in dimension_scores.items():
            weight = weights.get(dim_name, 0.0)
            final_weight += dim_score.score * weight

        return min(10.0, max(0.0, final_weight))

    def _create_error_result(self, document_id: int, error_message: str) -> PaperWeightResult:
        """
        Create minimal result on error.

        Args:
            document_id: Database ID of document
            error_message: Error message to include

        Returns:
            PaperWeightResult with error information
        """
        error_score = DimensionScore('error', 0.0)
        error_score.add_detail('error', 'assessment_failed', 0.0, reasoning=error_message)

        return PaperWeightResult(
            document_id=document_id,
            assessor_version=self.config.get('version', '1.0.0'),
            assessed_at=datetime.now(),
            study_design=error_score,
            sample_size=error_score,
            methodological_quality=error_score,
            risk_of_bias=error_score,
            replication_status=error_score,
            final_weight=0.0,
            dimension_weights=self.get_dimension_weights()
        )

    # ========================================================================
    # Main Entry Point (Step 6)
    # ========================================================================

    def assess_paper(
        self,
        document_id: int,
        force_reassess: bool = False,
        study_assessment: Optional[dict] = None
    ) -> PaperWeightResult:
        """
        Assess paper weight with intelligent caching.

        This is the main entry point for paper weight assessment.

        Args:
            document_id: Database ID of document to assess
            force_reassess: If True, skip cache and re-assess
            study_assessment: Optional StudyAssessmentAgent output to leverage

        Returns:
            PaperWeightResult with full audit trail

        Workflow:
            1. Check cache (unless force_reassess=True)
            2. If cached and version matches, return cached result
            3. Otherwise, perform full assessment:
               a. Fetch document from database
               b. Extract study type (rule-based)
               c. Extract sample size (rule-based + LLM)
               d. Assess methodological quality (LLM)
               e. Assess risk of bias (LLM)
               f. Check replication status (database query)
               g. Compute final weight
               h. Store in database
            4. Return result
        """
        version = self.config.get('version', '1.0.0')

        try:
            # Check cache
            if not force_reassess:
                cached = self._get_cached_assessment(document_id)
                if cached:
                    logger.info(f"Using cached assessment for document {document_id} (version {version})")
                    return cached

            logger.info(f"Performing fresh assessment for document {document_id}...")

            # Fetch document
            document = self._get_document(document_id)

            # Perform assessments
            study_design_score = self._extract_study_type(document)
            sample_size_score = self._extract_sample_size(document)
            methodological_quality_score = self._assess_methodological_quality(document, study_assessment)
            risk_of_bias_score = self._assess_risk_of_bias(document, study_assessment)
            replication_status_score = self._check_replication_status(document_id)

            # Compute final weight
            dimension_scores = {
                'study_design': study_design_score,
                'sample_size': sample_size_score,
                'methodological_quality': methodological_quality_score,
                'risk_of_bias': risk_of_bias_score,
                'replication_status': replication_status_score
            }
            final_weight = self._compute_final_weight(dimension_scores)

            # Extract study type and sample size from dimension scores
            study_type = None
            sample_size_n = None

            if study_design_score.details:
                study_type = study_design_score.details[0].extracted_value

            if sample_size_score.details:
                extracted_value = sample_size_score.details[0].extracted_value
                if extracted_value and extracted_value.isdigit():
                    sample_size_n = int(extracted_value)

            # Create result
            result = PaperWeightResult(
                document_id=document_id,
                assessor_version=version,
                assessed_at=datetime.now(),
                study_design=study_design_score,
                sample_size=sample_size_score,
                methodological_quality=methodological_quality_score,
                risk_of_bias=risk_of_bias_score,
                replication_status=replication_status_score,
                final_weight=final_weight,
                dimension_weights=self.get_dimension_weights(),
                study_type=study_type,
                sample_size_n=sample_size_n
            )

            # Store in database
            self._store_assessment(result)

            return result

        except Exception as e:
            logger.error(f"Error assessing paper {document_id}: {e}")
            # Return degraded assessment with error noted
            return self._create_error_result(document_id, str(e))


# Export all dataclasses and the agent class
__all__ = ['AssessmentDetail', 'DimensionScore', 'PaperWeightResult', 'PaperWeightAssessmentAgent']
