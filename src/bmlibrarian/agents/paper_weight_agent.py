"""
Paper Weight Assessment Agent - Multi-dimensional paper quality assessment

This module provides an AI-powered agent for assessing the evidential weight of
biomedical research papers across five dimensions: study design, sample size,
methodological quality, risk of bias, and replication status.

The module currently contains the data models (dataclasses) for representing
assessments. The agent implementation will be added in later steps.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict
from datetime import datetime
import json


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
            f"**Assessed:** {self.assessed_at.strftime('%Y-%m-%d %H:%M:%S')}",
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
                        # Truncate evidence text if too long
                        evidence = detail.evidence_text
                        if len(evidence) > 100:
                            evidence = evidence[:100] + "..."
                        lines.append(f"  - Evidence: *\"{evidence}\"*")
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


# Export all dataclasses
__all__ = ['AssessmentDetail', 'DimensionScore', 'PaperWeightResult']
