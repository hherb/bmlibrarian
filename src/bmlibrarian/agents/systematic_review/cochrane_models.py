"""
Cochrane-Aligned Data Models for Systematic Review Assessment

This module provides data models that closely match the Cochrane Handbook
requirements for systematic reviews, particularly:
- Study Characteristics Table (Methods, Participants, Interventions, Outcomes, Notes)
- Risk of Bias Assessment (Cochrane RoB 2.0 domains with judgement + support)

Reference: Cochrane Handbook for Systematic Reviews of Interventions
https://training.cochrane.org/handbook

These models ensure our assessment output aligns with Cochrane template
requirements for study characterization and risk of bias reporting.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Risk of bias judgement options (Cochrane standard)
ROB_JUDGEMENT_LOW = "Low risk"
ROB_JUDGEMENT_HIGH = "High risk"
ROB_JUDGEMENT_UNCLEAR = "Unclear risk"

# Valid judgement values for validation
VALID_ROB_JUDGEMENTS = {ROB_JUDGEMENT_LOW, ROB_JUDGEMENT_HIGH, ROB_JUDGEMENT_UNCLEAR}


# =============================================================================
# Enums
# =============================================================================

class RiskOfBiasJudgement(Enum):
    """
    Cochrane Risk of Bias judgement categories.

    These match the Cochrane RoB tool standard categories.
    """
    LOW = "Low risk"
    HIGH = "High risk"
    UNCLEAR = "Unclear risk"

    @classmethod
    def from_string(cls, value: str) -> "RiskOfBiasJudgement":
        """
        Convert string to RiskOfBiasJudgement enum.

        Handles case-insensitive matching and common variations.

        Args:
            value: String representation of judgement

        Returns:
            Corresponding RiskOfBiasJudgement enum
        """
        value_lower = value.lower().strip()

        # Handle common variations
        if value_lower in ("low", "low risk", "low_risk"):
            return cls.LOW
        elif value_lower in ("high", "high risk", "high_risk"):
            return cls.HIGH
        elif value_lower in ("unclear", "unclear risk", "unclear_risk", "unknown"):
            return cls.UNCLEAR
        else:
            logger.warning(f"Unknown RoB judgement '{value}', defaulting to UNCLEAR")
            return cls.UNCLEAR


# =============================================================================
# Risk of Bias Data Models
# =============================================================================

@dataclass
class RiskOfBiasItem:
    """
    Single risk of bias domain assessment.

    Each domain requires two fields per Cochrane requirements:
    - judgement: Low risk / High risk / Unclear risk
    - support_for_judgement: Text explaining the judgement

    This matches the Cochrane RoB table format shown in systematic review outputs.

    Attributes:
        domain: Name of the bias domain (e.g., "Random sequence generation")
        bias_type: Category of bias (e.g., "selection bias")
        judgement: Risk assessment ("Low risk", "High risk", or "Unclear risk")
        support_for_judgement: Text explaining the basis for the judgement
        outcome_type: For detection bias, specifies "subjective" or "objective" outcomes
    """
    domain: str
    bias_type: str
    judgement: str  # "Low risk", "High risk", "Unclear risk"
    support_for_judgement: str
    outcome_type: Optional[str] = None  # For detection bias: "subjective" or "objective"

    def __post_init__(self) -> None:
        """Validate judgement is in allowed values."""
        if self.judgement not in VALID_ROB_JUDGEMENTS:
            logger.warning(
                f"Invalid RoB judgement '{self.judgement}' for domain '{self.domain}', "
                f"expected one of {VALID_ROB_JUDGEMENTS}"
            )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {
            "domain": self.domain,
            "bias_type": self.bias_type,
            "judgement": self.judgement,
            "support_for_judgement": self.support_for_judgement,
        }
        if self.outcome_type:
            result["outcome_type"] = self.outcome_type
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RiskOfBiasItem":
        """Create RiskOfBiasItem from dictionary."""
        return cls(
            domain=data["domain"],
            bias_type=data["bias_type"],
            judgement=data["judgement"],
            support_for_judgement=data["support_for_judgement"],
            outcome_type=data.get("outcome_type"),
        )


@dataclass
class CochraneRiskOfBias:
    """
    Complete Cochrane Risk of Bias assessment.

    Contains all nine standard Cochrane RoB domains:

    Selection Bias:
    1. Random sequence generation
    2. Allocation concealment
    3. Baseline outcome measurements
    4. Baseline characteristics

    Performance Bias:
    5. Blinding of participants and personnel (all outcomes)

    Detection Bias:
    6. Blinding of outcome assessment (subjective outcomes)
    7. Blinding of outcome assessment (objective outcomes)

    Attrition Bias:
    8. Incomplete outcome data (all outcomes)

    Reporting Bias:
    9. Selective reporting

    Each domain includes both judgement and support text as required
    by the Cochrane template.
    """

    # Selection bias domains (4 items)
    random_sequence_generation: RiskOfBiasItem
    allocation_concealment: RiskOfBiasItem
    baseline_outcome_measurements: RiskOfBiasItem
    baseline_characteristics: RiskOfBiasItem

    # Performance bias (1 item)
    blinding_participants_personnel: RiskOfBiasItem

    # Detection bias (2 items - split by outcome type)
    blinding_outcome_assessment_subjective: RiskOfBiasItem
    blinding_outcome_assessment_objective: RiskOfBiasItem

    # Attrition bias (1 item)
    incomplete_outcome_data: RiskOfBiasItem

    # Reporting bias (1 item)
    selective_reporting: RiskOfBiasItem

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "random_sequence_generation": self.random_sequence_generation.to_dict(),
            "allocation_concealment": self.allocation_concealment.to_dict(),
            "baseline_outcome_measurements": self.baseline_outcome_measurements.to_dict(),
            "baseline_characteristics": self.baseline_characteristics.to_dict(),
            "blinding_participants_personnel": self.blinding_participants_personnel.to_dict(),
            "blinding_outcome_assessment_subjective": self.blinding_outcome_assessment_subjective.to_dict(),
            "blinding_outcome_assessment_objective": self.blinding_outcome_assessment_objective.to_dict(),
            "incomplete_outcome_data": self.incomplete_outcome_data.to_dict(),
            "selective_reporting": self.selective_reporting.to_dict(),
        }

    def to_list(self) -> List[RiskOfBiasItem]:
        """
        Convert to list of RiskOfBiasItems for iteration.

        Returns items in Cochrane table order.
        """
        return [
            self.random_sequence_generation,
            self.allocation_concealment,
            self.baseline_outcome_measurements,
            self.baseline_characteristics,
            self.blinding_participants_personnel,
            self.blinding_outcome_assessment_subjective,
            self.blinding_outcome_assessment_objective,
            self.incomplete_outcome_data,
            self.selective_reporting,
        ]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CochraneRiskOfBias":
        """Create CochraneRiskOfBias from dictionary."""
        return cls(
            random_sequence_generation=RiskOfBiasItem.from_dict(
                data["random_sequence_generation"]
            ),
            allocation_concealment=RiskOfBiasItem.from_dict(
                data["allocation_concealment"]
            ),
            baseline_outcome_measurements=RiskOfBiasItem.from_dict(
                data["baseline_outcome_measurements"]
            ),
            baseline_characteristics=RiskOfBiasItem.from_dict(
                data["baseline_characteristics"]
            ),
            blinding_participants_personnel=RiskOfBiasItem.from_dict(
                data["blinding_participants_personnel"]
            ),
            blinding_outcome_assessment_subjective=RiskOfBiasItem.from_dict(
                data["blinding_outcome_assessment_subjective"]
            ),
            blinding_outcome_assessment_objective=RiskOfBiasItem.from_dict(
                data["blinding_outcome_assessment_objective"]
            ),
            incomplete_outcome_data=RiskOfBiasItem.from_dict(
                data["incomplete_outcome_data"]
            ),
            selective_reporting=RiskOfBiasItem.from_dict(
                data["selective_reporting"]
            ),
        )

    def get_summary_counts(self) -> Dict[str, int]:
        """
        Get count of each judgement type.

        Returns:
            Dictionary with counts for "Low risk", "High risk", "Unclear risk"
        """
        counts = {
            ROB_JUDGEMENT_LOW: 0,
            ROB_JUDGEMENT_HIGH: 0,
            ROB_JUDGEMENT_UNCLEAR: 0,
        }
        for item in self.to_list():
            if item.judgement in counts:
                counts[item.judgement] += 1
        return counts


# =============================================================================
# Study Characteristics Data Models
# =============================================================================

@dataclass
class CochraneParticipants:
    """
    Participants section of Cochrane study characteristics.

    Captures detailed information about study participants as required
    by Cochrane systematic review standards.

    Attributes:
        setting: Study location/setting (e.g., "Romania", "University hospital")
        population: Description of the study population
        inclusion_criteria: List of inclusion criteria (if reported)
        exclusion_criteria: List of exclusion criteria (if reported)
        total_participants: Total number recruited
        group_sizes: Sample sizes per group (e.g., {"intervention": 25, "control": 20})
        baseline_characteristics_reported: Whether baseline characteristics were reported
    """
    setting: str
    population: str
    inclusion_criteria: Optional[List[str]] = None
    exclusion_criteria: Optional[List[str]] = None
    total_participants: Optional[int] = None
    group_sizes: Optional[Dict[str, int]] = None
    baseline_characteristics_reported: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "setting": self.setting,
            "population": self.population,
            "inclusion_criteria": self.inclusion_criteria,
            "exclusion_criteria": self.exclusion_criteria,
            "total_participants": self.total_participants,
            "group_sizes": self.group_sizes,
            "baseline_characteristics_reported": self.baseline_characteristics_reported,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CochraneParticipants":
        """Create CochraneParticipants from dictionary."""
        return cls(
            setting=data.get("setting", "Not reported"),
            population=data.get("population", "Not reported"),
            inclusion_criteria=data.get("inclusion_criteria"),
            exclusion_criteria=data.get("exclusion_criteria"),
            total_participants=data.get("total_participants"),
            group_sizes=data.get("group_sizes"),
            baseline_characteristics_reported=data.get("baseline_characteristics_reported", False),
        )

    def format_for_table(self) -> str:
        """
        Format participants info for Cochrane table display.

        Returns:
            Formatted string suitable for Cochrane characteristics table
        """
        lines = [f"Setting: {self.setting}", "", self.population]

        if self.total_participants:
            if self.group_sizes:
                group_str = ", ".join(
                    f"{k}: {v}" for k, v in self.group_sizes.items()
                )
                lines.append(f"N={self.total_participants} ({group_str})")
            else:
                lines.append(f"N={self.total_participants}")

        return "\n".join(lines)


@dataclass
class CochraneInterventions:
    """
    Interventions section of Cochrane study characteristics.

    Captures intervention and control/comparison details.

    Attributes:
        description: Full description of the intervention(s)
        intervention_groups: List of intervention group descriptions
        control_description: Description of control/comparison group
        duration: Duration of intervention
        setting: Where intervention was delivered (if different from participants setting)
    """
    description: str
    intervention_groups: Optional[List[str]] = None
    control_description: Optional[str] = None
    duration: Optional[str] = None
    setting: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "description": self.description,
            "intervention_groups": self.intervention_groups,
            "control_description": self.control_description,
            "duration": self.duration,
            "setting": self.setting,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CochraneInterventions":
        """Create CochraneInterventions from dictionary."""
        return cls(
            description=data.get("description", "Not reported"),
            intervention_groups=data.get("intervention_groups"),
            control_description=data.get("control_description"),
            duration=data.get("duration"),
            setting=data.get("setting"),
        )


@dataclass
class CochraneOutcomes:
    """
    Outcomes section of Cochrane study characteristics.

    Captures primary and secondary outcomes measured in the study.

    Attributes:
        description: Brief description of outcomes measured
        primary_outcomes: List of primary outcomes
        secondary_outcomes: List of secondary outcomes
        outcome_timepoints: When outcomes were measured
        outcome_assessment_methods: How outcomes were assessed
    """
    description: str
    primary_outcomes: Optional[List[str]] = None
    secondary_outcomes: Optional[List[str]] = None
    outcome_timepoints: Optional[List[str]] = None
    outcome_assessment_methods: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "description": self.description,
            "primary_outcomes": self.primary_outcomes,
            "secondary_outcomes": self.secondary_outcomes,
            "outcome_timepoints": self.outcome_timepoints,
            "outcome_assessment_methods": self.outcome_assessment_methods,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CochraneOutcomes":
        """Create CochraneOutcomes from dictionary."""
        return cls(
            description=data.get("description", "Not reported"),
            primary_outcomes=data.get("primary_outcomes"),
            secondary_outcomes=data.get("secondary_outcomes"),
            outcome_timepoints=data.get("outcome_timepoints"),
            outcome_assessment_methods=data.get("outcome_assessment_methods"),
        )


@dataclass
class CochraneNotes:
    """
    Notes section of Cochrane study characteristics.

    Captures additional study information required by Cochrane template.

    Attributes:
        follow_up_periods: Follow-up time points (e.g., ["1 month", "3 months", "12 months"])
        funding_source: Funding source and sponsor information
        conflicts_of_interest: Reported conflicts of interest
        ethical_approval: Ethical approval status
        trial_registration: Trial registration number if applicable
        publication_status: Full publication, abstract only, etc.
        additional_notes: Any other relevant notes
    """
    follow_up_periods: Optional[List[str]] = None
    funding_source: Optional[str] = None
    conflicts_of_interest: Optional[str] = None
    ethical_approval: Optional[str] = None
    trial_registration: Optional[str] = None
    publication_status: Optional[str] = None
    additional_notes: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "follow_up_periods": self.follow_up_periods,
            "funding_source": self.funding_source,
            "conflicts_of_interest": self.conflicts_of_interest,
            "ethical_approval": self.ethical_approval,
            "trial_registration": self.trial_registration,
            "publication_status": self.publication_status,
            "additional_notes": self.additional_notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CochraneNotes":
        """Create CochraneNotes from dictionary."""
        return cls(
            follow_up_periods=data.get("follow_up_periods"),
            funding_source=data.get("funding_source"),
            conflicts_of_interest=data.get("conflicts_of_interest"),
            ethical_approval=data.get("ethical_approval"),
            trial_registration=data.get("trial_registration"),
            publication_status=data.get("publication_status"),
            additional_notes=data.get("additional_notes"),
        )

    def format_for_table(self) -> str:
        """
        Format notes for Cochrane table display.

        Returns:
            Formatted string suitable for Cochrane characteristics table
        """
        lines = []

        if self.follow_up_periods:
            lines.append(f"Follow-up at {', '.join(self.follow_up_periods)}")

        if self.funding_source:
            lines.append(f"Funding: {self.funding_source}")

        if self.conflicts_of_interest:
            lines.append(f"Conflicts of interest: {self.conflicts_of_interest}")

        if self.ethical_approval:
            lines.append(f"Ethical approval: {self.ethical_approval}")

        if self.trial_registration:
            lines.append(f"Trial registration: {self.trial_registration}")

        if self.publication_status:
            lines.append(f"Publication status: {self.publication_status}")

        if self.additional_notes:
            lines.extend(self.additional_notes)

        return "\n\n".join(lines) if lines else "No additional notes"


@dataclass
class CochraneStudyCharacteristics:
    """
    Complete Cochrane Study Characteristics table.

    This matches the standard Cochrane format with five main sections:
    - Methods: Study design
    - Participants: Setting, population, sample sizes
    - Interventions: What was tested
    - Outcomes: What was measured
    - Notes: Follow-up, funding, ethics, etc.

    Example from Cochrane template:

    | Study characteristics |                                                              |
    |-----------------------|--------------------------------------------------------------|
    | Methods               | Parallel randomised trial                                    |
    | Participants          | Setting: Romania                                             |
    |                       | People with chronic heart failure who had deteriorated...    |
    | Interventions         | Admission avoidance hospital at home; the first 48 hours...  |
    | Outcomes              | Mortality, biological measures, and cost                     |
    | Notes                 | Follow-up at 1, 3, 6, and 12 months                         |
    |                       | Funding: the study was published as an abstract...          |

    Attributes:
        study_id: Study identifier (e.g., "Andrei 2011")
        methods: Study design description
        participants: Detailed participant information
        interventions: Intervention details
        outcomes: Outcome measures
        notes: Additional notes (funding, ethics, etc.)
    """
    study_id: str  # e.g., "Andrei 2011"
    methods: str   # e.g., "Parallel randomised trial"
    participants: CochraneParticipants
    interventions: CochraneInterventions
    outcomes: CochraneOutcomes
    notes: CochraneNotes

    # Metadata
    document_id: Optional[int] = None
    document_title: Optional[str] = None
    pmid: Optional[str] = None
    doi: Optional[str] = None
    created_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        """Set creation timestamp if not provided."""
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "study_id": self.study_id,
            "methods": self.methods,
            "participants": self.participants.to_dict(),
            "interventions": self.interventions.to_dict(),
            "outcomes": self.outcomes.to_dict(),
            "notes": self.notes.to_dict(),
            "document_id": self.document_id,
            "document_title": self.document_title,
            "pmid": self.pmid,
            "doi": self.doi,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CochraneStudyCharacteristics":
        """Create CochraneStudyCharacteristics from dictionary."""
        created_at = None
        if data.get("created_at"):
            created_at = datetime.fromisoformat(data["created_at"])

        return cls(
            study_id=data["study_id"],
            methods=data["methods"],
            participants=CochraneParticipants.from_dict(data["participants"]),
            interventions=CochraneInterventions.from_dict(data["interventions"]),
            outcomes=CochraneOutcomes.from_dict(data["outcomes"]),
            notes=CochraneNotes.from_dict(data["notes"]),
            document_id=data.get("document_id"),
            document_title=data.get("document_title"),
            pmid=data.get("pmid"),
            doi=data.get("doi"),
            created_at=created_at,
        )


# =============================================================================
# Complete Cochrane Assessment
# =============================================================================

@dataclass
class CochraneStudyAssessment:
    """
    Complete Cochrane-aligned study assessment.

    Combines:
    - Study Characteristics (Methods, Participants, Interventions, Outcomes, Notes)
    - Risk of Bias assessment (9 Cochrane domains with judgement + support)

    This provides a superset of the standard Cochrane template output,
    ensuring nothing required by Cochrane is missing while allowing
    additional fields for internal use.

    Attributes:
        study_characteristics: Complete study characteristics table
        risk_of_bias: Complete risk of bias assessment
        overall_quality_score: Optional overall quality score (0-10)
        overall_confidence: Agent confidence in assessment (0-1)
        evidence_level: Oxford CEBM evidence level
        assessment_notes: Any notes from the assessment process
    """
    study_characteristics: CochraneStudyCharacteristics
    risk_of_bias: CochraneRiskOfBias

    # Additional assessment metadata (superset of Cochrane requirements)
    overall_quality_score: Optional[float] = None  # 0-10 scale
    overall_confidence: Optional[float] = None     # 0-1 scale
    evidence_level: Optional[str] = None           # e.g., "Level 2 (moderate-high)"
    assessment_notes: Optional[List[str]] = None

    # Version tracking
    assessment_version: str = "2.0.0"  # Updated version for Cochrane alignment

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "study_characteristics": self.study_characteristics.to_dict(),
            "risk_of_bias": self.risk_of_bias.to_dict(),
            "overall_quality_score": self.overall_quality_score,
            "overall_confidence": self.overall_confidence,
            "evidence_level": self.evidence_level,
            "assessment_notes": self.assessment_notes,
            "assessment_version": self.assessment_version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CochraneStudyAssessment":
        """Create CochraneStudyAssessment from dictionary."""
        return cls(
            study_characteristics=CochraneStudyCharacteristics.from_dict(
                data["study_characteristics"]
            ),
            risk_of_bias=CochraneRiskOfBias.from_dict(data["risk_of_bias"]),
            overall_quality_score=data.get("overall_quality_score"),
            overall_confidence=data.get("overall_confidence"),
            evidence_level=data.get("evidence_level"),
            assessment_notes=data.get("assessment_notes"),
            assessment_version=data.get("assessment_version", "2.0.0"),
        )

    @property
    def study_id(self) -> str:
        """Get study ID for convenience."""
        return self.study_characteristics.study_id

    @property
    def document_id(self) -> Optional[int]:
        """Get document ID for convenience."""
        return self.study_characteristics.document_id


# =============================================================================
# Factory Functions
# =============================================================================

def create_default_risk_of_bias_item(
    domain: str,
    bias_type: str,
    outcome_type: Optional[str] = None
) -> RiskOfBiasItem:
    """
    Create a default RiskOfBiasItem with "Unclear risk" judgement.

    Used when assessment information is not available or not reported.

    Args:
        domain: Name of the bias domain
        bias_type: Category of bias
        outcome_type: Optional outcome type for detection bias

    Returns:
        RiskOfBiasItem with unclear risk and default support text
    """
    return RiskOfBiasItem(
        domain=domain,
        bias_type=bias_type,
        judgement=ROB_JUDGEMENT_UNCLEAR,
        support_for_judgement="Not reported or insufficient information to assess",
        outcome_type=outcome_type,
    )


def create_default_cochrane_risk_of_bias() -> CochraneRiskOfBias:
    """
    Create a default CochraneRiskOfBias with all domains set to "Unclear risk".

    Used as a starting point when assessment cannot extract information.

    Returns:
        CochraneRiskOfBias with all domains unclear
    """
    return CochraneRiskOfBias(
        random_sequence_generation=create_default_risk_of_bias_item(
            "Random sequence generation", "selection bias"
        ),
        allocation_concealment=create_default_risk_of_bias_item(
            "Allocation concealment", "selection bias"
        ),
        baseline_outcome_measurements=create_default_risk_of_bias_item(
            "Baseline outcome measurements", "selection bias"
        ),
        baseline_characteristics=create_default_risk_of_bias_item(
            "Baseline characteristics", "selection bias"
        ),
        blinding_participants_personnel=create_default_risk_of_bias_item(
            "Blinding of participants and personnel", "performance bias"
        ),
        blinding_outcome_assessment_subjective=create_default_risk_of_bias_item(
            "Blinding of outcome assessment (subjective outcomes)",
            "detection bias",
            outcome_type="subjective"
        ),
        blinding_outcome_assessment_objective=create_default_risk_of_bias_item(
            "Blinding of outcome assessment (objective outcomes)",
            "detection bias",
            outcome_type="objective"
        ),
        incomplete_outcome_data=create_default_risk_of_bias_item(
            "Incomplete outcome data", "attrition bias"
        ),
        selective_reporting=create_default_risk_of_bias_item(
            "Selective reporting", "reporting bias"
        ),
    )
