"""
Paper Weight Assessment Data Models

This module contains the dataclasses for representing paper weight assessments:
- AssessmentDetail: Audit trail entry for a single component
- DimensionScore: Score for a single dimension with audit trail
- PaperWeightResult: Complete assessment with all dimensions

These models are used by PaperWeightAssessmentAgent and related modules.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict
from datetime import datetime
import json


# Constants for formatting and display
DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'  # Standard datetime format for reports

# Dimension names as constants
DIMENSION_STUDY_DESIGN = 'study_design'
DIMENSION_SAMPLE_SIZE = 'sample_size'
DIMENSION_METHODOLOGICAL_QUALITY = 'methodological_quality'
DIMENSION_RISK_OF_BIAS = 'risk_of_bias'
DIMENSION_REPLICATION_STATUS = 'replication_status'

ALL_DIMENSIONS = [
    DIMENSION_STUDY_DESIGN,
    DIMENSION_SAMPLE_SIZE,
    DIMENSION_METHODOLOGICAL_QUALITY,
    DIMENSION_RISK_OF_BIAS,
    DIMENSION_REPLICATION_STATUS,
]


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
    """
    dimension_name: str
    score: float
    details: List[AssessmentDetail] = field(default_factory=list)

    def add_detail(
        self,
        component: str,
        value: str,
        contribution: float,
        evidence: Optional[str] = None,
        reasoning: Optional[str] = None
    ) -> None:
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
            "# Paper Weight Assessment Report",
            "",
            f"**Document ID:** {self.document_id}",
            f"**Study Type:** {self.study_type or 'Unknown'}",
            f"**Sample Size:** {self.sample_size_n or 'Not extracted'}",
            f"**Assessed:** {self.assessed_at.strftime(DATETIME_FORMAT)}",
            f"**Assessor Version:** {self.assessor_version}",
            "",
            f"## Final Weight: {self.final_weight:.2f}/10",
            "",
            "## Dimension Scores",
            "",
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
            DIMENSION_STUDY_DESIGN: [],
            DIMENSION_SAMPLE_SIZE: [],
            DIMENSION_METHODOLOGICAL_QUALITY: [],
            DIMENSION_RISK_OF_BIAS: [],
            DIMENSION_REPLICATION_STATUS: []
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
            dimension_name=DIMENSION_STUDY_DESIGN,
            score=float(row['study_design_score']),
            details=dimension_details[DIMENSION_STUDY_DESIGN]
        )
        sample_size = DimensionScore(
            dimension_name=DIMENSION_SAMPLE_SIZE,
            score=float(row['sample_size_score']),
            details=dimension_details[DIMENSION_SAMPLE_SIZE]
        )
        methodological_quality = DimensionScore(
            dimension_name=DIMENSION_METHODOLOGICAL_QUALITY,
            score=float(row['methodological_quality_score']),
            details=dimension_details[DIMENSION_METHODOLOGICAL_QUALITY]
        )
        risk_of_bias = DimensionScore(
            dimension_name=DIMENSION_RISK_OF_BIAS,
            score=float(row['risk_of_bias_score']),
            details=dimension_details[DIMENSION_RISK_OF_BIAS]
        )
        replication_status = DimensionScore(
            dimension_name=DIMENSION_REPLICATION_STATUS,
            score=float(row['replication_status_score']),
            details=dimension_details[DIMENSION_REPLICATION_STATUS]
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


__all__ = [
    'AssessmentDetail',
    'DimensionScore',
    'PaperWeightResult',
    'DATETIME_FORMAT',
    'DIMENSION_STUDY_DESIGN',
    'DIMENSION_SAMPLE_SIZE',
    'DIMENSION_METHODOLOGICAL_QUALITY',
    'DIMENSION_RISK_OF_BIAS',
    'DIMENSION_REPLICATION_STATUS',
    'ALL_DIMENSIONS',
]
