"""
Paper Weight Assessment Agent - Multi-dimensional paper quality assessment

This module provides an AI-powered agent for assessing the evidential weight of
biomedical research papers across five dimensions: study design, sample size,
methodological quality, risk of bias, and replication status.

The module currently contains the data models (dataclasses) for representing
assessments. The agent implementation will be added in later steps.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Callable, TYPE_CHECKING
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

    This class currently implements the rule-based extractors (Step 4).
    LLM-based assessors and database persistence will be added in later steps.
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


# Export all dataclasses and the agent class
__all__ = ['AssessmentDetail', 'DimensionScore', 'PaperWeightResult', 'PaperWeightAssessmentAgent']
