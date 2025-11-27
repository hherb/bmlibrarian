"""
Cochrane Assessment Agent for Systematic Reviews

This agent produces assessments that align with the Cochrane Handbook
for Systematic Reviews of Interventions, generating:
- Study Characteristics tables (Methods, Participants, Interventions, Outcomes, Notes)
- Risk of Bias assessment (9 Cochrane domains with judgement + support)

The output format matches Cochrane template requirements exactly, ensuring
nothing required by systematic review standards is missing.

Reference: Cochrane Handbook for Systematic Reviews of Interventions
https://training.cochrane.org/handbook
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Optional

from ..base import BaseAgent
from .cochrane_models import (
    CochraneStudyAssessment,
    CochraneStudyCharacteristics,
    CochraneParticipants,
    CochraneInterventions,
    CochraneOutcomes,
    CochraneNotes,
    CochraneRiskOfBias,
    RiskOfBiasItem,
    create_default_cochrane_risk_of_bias,
    ROB_JUDGEMENT_LOW,
    ROB_JUDGEMENT_HIGH,
    ROB_JUDGEMENT_UNCLEAR,
)
from .cochrane_formatter import (
    format_complete_assessment_markdown,
    format_multiple_assessments_markdown,
    format_risk_of_bias_summary_markdown,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Maximum text length for context (fits within LLM context window)
MAX_TEXT_LENGTH = 12000

# Default confidence threshold for accepting assessments
DEFAULT_MIN_CONFIDENCE = 0.4

# Agent version for cache invalidation
AGENT_VERSION = "1.0.0"


# =============================================================================
# CochraneAssessmentAgent
# =============================================================================

class CochraneAssessmentAgent(BaseAgent):
    """
    Agent for generating Cochrane-aligned study assessments.

    Produces assessments that match the Cochrane Handbook template requirements:
    - Complete Study Characteristics table
    - Full Risk of Bias assessment with 9 domains
    - Each bias domain includes judgement + support for judgement

    This ensures systematic review outputs are compliant with Cochrane
    standards and can be directly used in Cochrane-style publications.

    Example:
        >>> agent = CochraneAssessmentAgent()
        >>> assessment = agent.assess_document(document)
        >>> markdown = agent.format_assessment_markdown(assessment)
    """

    VERSION = AGENT_VERSION

    def __init__(
        self,
        model: str = "gpt-oss:20b",
        host: str = "http://localhost:11434",
        temperature: float = 0.1,
        top_p: float = 0.9,
        max_tokens: int = 4000,
        callback: Optional[Callable[[str, str], None]] = None,
        orchestrator: Optional[Any] = None,
        show_model_info: bool = True,
        max_retries: int = 3,
    ) -> None:
        """
        Initialize the CochraneAssessmentAgent.

        Args:
            model: The name of the Ollama model to use
            host: The Ollama server host URL
            temperature: Model temperature for assessment (low for consistency)
            top_p: Model top-p sampling parameter
            max_tokens: Maximum tokens for response
            callback: Optional callback function for progress updates
            orchestrator: Optional orchestrator for queue-based processing
            show_model_info: Whether to display model information
            max_retries: Maximum retry attempts for failed assessments
        """
        super().__init__(
            model=model,
            host=host,
            temperature=temperature,
            top_p=top_p,
            callback=callback,
            orchestrator=orchestrator,
            show_model_info=show_model_info,
        )
        self.max_tokens = max_tokens
        self.max_retries = max_retries

        # Statistics tracking
        self._stats = {
            "total_assessments": 0,
            "successful_assessments": 0,
            "failed_assessments": 0,
            "parse_failures": 0,
        }

        logger.info(f"CochraneAssessmentAgent initialized (version {AGENT_VERSION})")

    def get_agent_type(self) -> str:
        """Get the agent type identifier."""
        return "cochrane_assessment_agent"

    def assess_document(
        self,
        document: Dict[str, Any],
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    ) -> Optional[CochraneStudyAssessment]:
        """
        Assess a document using Cochrane standards.

        Extracts all information required by the Cochrane template:
        - Study Characteristics (Methods, Participants, Interventions, Outcomes, Notes)
        - Risk of Bias (9 domains with judgement + support)

        Args:
            document: Document dictionary with at minimum 'id', 'title', and 'abstract'
            min_confidence: Minimum confidence threshold to accept assessment

        Returns:
            CochraneStudyAssessment object if successful, None otherwise
        """
        if not self.test_connection():
            logger.error("Cannot connect to Ollama - Cochrane assessment unavailable")
            return None

        # Extract document metadata
        doc_id = document.get("id", "unknown")
        title = document.get("title", "Untitled")
        abstract = document.get("abstract", "")
        full_text = document.get("full_text", "")
        authors = document.get("authors", [])
        year = document.get("year") or document.get("publication_date", "")

        # Determine study ID (Author Year format)
        if authors:
            first_author = authors[0] if isinstance(authors, list) else authors.split(",")[0]
            # Extract surname
            first_author_surname = first_author.split()[-1] if first_author else "Unknown"
            study_id = f"{first_author_surname} {year}"
        else:
            study_id = f"Study {doc_id}"

        # Use full text if available, fall back to abstract
        text_to_analyze = full_text if full_text else abstract

        if not text_to_analyze:
            logger.warning(f"No text found for document {doc_id}")
            return None

        # Truncate if needed
        if len(text_to_analyze) > MAX_TEXT_LENGTH:
            text_to_analyze = text_to_analyze[:MAX_TEXT_LENGTH] + "..."
            logger.debug(f"Truncated text for document {doc_id}")

        self._call_callback(
            "cochrane_assessment_started",
            f"Assessing document {doc_id} for Cochrane compliance"
        )

        # Build and execute assessment prompt
        prompt = self._build_assessment_prompt(title, text_to_analyze)

        try:
            assessment_data = self._generate_and_parse_json(
                prompt,
                max_retries=self.max_retries,
                retry_context=f"Cochrane assessment (doc {doc_id})",
                num_predict=self.max_tokens,
            )
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse failed for document {doc_id}: {e}")
            self._stats["parse_failures"] += 1
            return None
        except (ConnectionError, ValueError) as e:
            logger.error(f"Ollama request failed for document {doc_id}: {e}")
            self._stats["failed_assessments"] += 1
            return None

        # Convert response to Cochrane models
        try:
            assessment = self._parse_assessment_response(
                assessment_data, study_id, doc_id, title,
                document.get("pmid"), document.get("doi")
            )
        except (KeyError, TypeError, ValueError) as e:
            logger.error(f"Failed to parse assessment response for {doc_id}: {e}")
            self._stats["failed_assessments"] += 1
            return None

        # Update statistics
        self._stats["total_assessments"] += 1
        self._stats["successful_assessments"] += 1

        self._call_callback(
            "cochrane_assessment_completed",
            f"Completed Cochrane assessment for document {doc_id}"
        )

        logger.info(f"Successfully assessed document {doc_id}")
        return assessment

    def _build_assessment_prompt(self, title: str, text: str) -> str:
        """
        Build the LLM prompt for Cochrane assessment.

        The prompt is carefully structured to extract all fields required
        by the Cochrane template format.

        Args:
            title: Document title
            text: Document text to analyze

        Returns:
            Complete prompt string
        """
        return f"""You are a medical research methodologist specializing in systematic reviews and the Cochrane methodology.

Conduct a comprehensive Cochrane-style assessment of the following study.

Paper Title: {title}

Paper Text:
{text}

IMPORTANT: Extract information ONLY from what is ACTUALLY PRESENT in the text. For information not reported, use "Not reported" or "Details not reported" as appropriate.

Generate a complete Cochrane assessment with the following structure:

1. STUDY CHARACTERISTICS:

   a) Methods: Describe the study design (e.g., "Parallel randomised trial", "Prospective cohort study")

   b) Participants:
      - Setting: Country/location where the study was conducted
      - Population: Description of participants, inclusion criteria, conditions
      - Total participants: Number recruited (if reported)
      - Group sizes: Sample sizes per group if applicable (e.g., {{"intervention": 25, "control": 20}})

   c) Interventions:
      - Description: Full description of the intervention(s) being tested
      - Control: Description of control/comparison group

   d) Outcomes:
      - Description: What outcomes were measured (e.g., "Mortality, biological measures, and cost")
      - Primary outcomes: List primary outcomes if identified
      - Secondary outcomes: List secondary outcomes if identified
      - Timepoints: When outcomes were measured

   e) Notes:
      - Follow-up: Follow-up periods (e.g., ["1 month", "3 months", "6 months", "12 months"])
      - Funding: Funding source and sponsor information
      - Conflicts of interest: Any reported conflicts
      - Ethical approval: Ethical approval status
      - Publication status: Whether full publication or abstract-only

2. RISK OF BIAS ASSESSMENT (9 domains):

For EACH domain, provide:
- judgement: EXACTLY one of "Low risk", "High risk", or "Unclear risk"
- support_for_judgement: Text explaining the basis for your judgement

The 9 required domains are:

a) Random sequence generation (selection bias):
   - Assess how randomization sequence was generated
   - "Low risk" if adequate (computer-generated, random number table)
   - "High risk" if inadequate (alternation, birth date, odd/even)
   - "Unclear risk" if not reported

b) Allocation concealment (selection bias):
   - Assess how allocation was concealed
   - "Low risk" if adequate (central allocation, sealed envelopes)
   - "High risk" if inadequate (open random lists, alternation)
   - "Unclear risk" if not reported

c) Baseline outcome measurements (selection bias):
   - Assess if baseline outcome measurements were similar
   - "Low risk" if groups similar at baseline
   - "High risk" if groups differed significantly
   - "Unclear risk" if not reported

d) Baseline characteristics (selection bias):
   - Assess if baseline characteristics were similar
   - "Low risk" if groups balanced at baseline
   - "High risk" if important imbalances
   - "Unclear risk" if not reported

e) Blinding of participants and personnel (performance bias):
   - Assess blinding of participants and study personnel
   - "Low risk" if blinded or outcome unlikely affected by lack of blinding
   - "High risk" if not blinded and outcome likely affected
   - "Unclear risk" if not reported

f) Blinding of outcome assessment - subjective outcomes (detection bias):
   - Assess blinding for subjective outcomes (patient-reported, quality of life)
   - "Low risk" if outcome assessors blinded
   - "High risk" if assessors not blinded
   - "Unclear risk" if not reported

g) Blinding of outcome assessment - objective outcomes (detection bias):
   - Assess blinding for objective outcomes (mortality, lab values)
   - "Low risk" if blinded or objective outcomes unlikely affected
   - "High risk" if not blinded and bias likely
   - "Unclear risk" if methods not reported

h) Incomplete outcome data (attrition bias):
   - Assess completeness of outcome data
   - "Low risk" if low dropout, balanced across groups, appropriate handling
   - "High risk" if high dropout, imbalanced, or inappropriate handling
   - "Unclear risk" if not reported

i) Selective reporting (reporting bias):
   - Assess selective outcome reporting
   - "Low risk" if all pre-specified outcomes reported
   - "High risk" if some outcomes not reported or reported selectively
   - "Unclear risk" if insufficient information

3. OVERALL ASSESSMENT:
   - overall_confidence: Your confidence in this assessment (0.0-1.0)
   - evidence_level: Evidence level using Oxford CEBM hierarchy
     ("Level 1 (high)", "Level 2 (moderate-high)", "Level 3 (moderate)",
      "Level 4 (low-moderate)", "Level 5 (low)")
   - assessment_notes: Any important notes about the assessment

Response format (JSON only):
{{
    "study_characteristics": {{
        "methods": "study design description",
        "participants": {{
            "setting": "location/country",
            "population": "description of participants",
            "inclusion_criteria": ["criterion 1", "criterion 2"] or null,
            "exclusion_criteria": ["criterion 1"] or null,
            "total_participants": 45 or null,
            "group_sizes": {{"intervention": 25, "control": 20}} or null,
            "baseline_characteristics_reported": true or false
        }},
        "interventions": {{
            "description": "intervention description",
            "intervention_groups": ["group 1 description"] or null,
            "control_description": "control description" or null,
            "duration": "duration" or null
        }},
        "outcomes": {{
            "description": "outcomes measured",
            "primary_outcomes": ["outcome 1"] or null,
            "secondary_outcomes": ["outcome 1"] or null,
            "outcome_timepoints": ["1 month", "3 months"] or null
        }},
        "notes": {{
            "follow_up_periods": ["1 month", "3 months", "6 months", "12 months"] or null,
            "funding_source": "funding info" or null,
            "conflicts_of_interest": "conflicts" or null,
            "ethical_approval": "approval status" or null,
            "publication_status": "full publication or abstract" or null,
            "additional_notes": ["note 1"] or null
        }}
    }},
    "risk_of_bias": {{
        "random_sequence_generation": {{
            "judgement": "Low risk" or "High risk" or "Unclear risk",
            "support_for_judgement": "explanation text"
        }},
        "allocation_concealment": {{
            "judgement": "Low risk" or "High risk" or "Unclear risk",
            "support_for_judgement": "explanation text"
        }},
        "baseline_outcome_measurements": {{
            "judgement": "Low risk" or "High risk" or "Unclear risk",
            "support_for_judgement": "explanation text"
        }},
        "baseline_characteristics": {{
            "judgement": "Low risk" or "High risk" or "Unclear risk",
            "support_for_judgement": "explanation text"
        }},
        "blinding_participants_personnel": {{
            "judgement": "Low risk" or "High risk" or "Unclear risk",
            "support_for_judgement": "explanation text"
        }},
        "blinding_outcome_assessment_subjective": {{
            "judgement": "Low risk" or "High risk" or "Unclear risk",
            "support_for_judgement": "explanation text"
        }},
        "blinding_outcome_assessment_objective": {{
            "judgement": "Low risk" or "High risk" or "Unclear risk",
            "support_for_judgement": "explanation text"
        }},
        "incomplete_outcome_data": {{
            "judgement": "Low risk" or "High risk" or "Unclear risk",
            "support_for_judgement": "explanation text"
        }},
        "selective_reporting": {{
            "judgement": "Low risk" or "High risk" or "Unclear risk",
            "support_for_judgement": "explanation text"
        }}
    }},
    "overall_confidence": 0.7,
    "evidence_level": "Level X (description)",
    "assessment_notes": ["note 1", "note 2"] or null
}}

Respond ONLY with valid JSON. Do not include any explanatory text outside the JSON."""

    def _parse_assessment_response(
        self,
        data: Dict[str, Any],
        study_id: str,
        doc_id: Any,
        title: str,
        pmid: Optional[str],
        doi: Optional[str],
    ) -> CochraneStudyAssessment:
        """
        Parse LLM response into CochraneStudyAssessment object.

        Args:
            data: Parsed JSON response from LLM
            study_id: Study identifier (Author Year format)
            doc_id: Database document ID
            title: Document title
            pmid: PubMed ID if available
            doi: DOI if available

        Returns:
            CochraneStudyAssessment object
        """
        # Parse study characteristics
        sc_data = data.get("study_characteristics", {})

        participants = CochraneParticipants.from_dict(
            sc_data.get("participants", {"setting": "Not reported", "population": "Not reported"})
        )

        interventions = CochraneInterventions.from_dict(
            sc_data.get("interventions", {"description": "Not reported"})
        )

        outcomes = CochraneOutcomes.from_dict(
            sc_data.get("outcomes", {"description": "Not reported"})
        )

        notes = CochraneNotes.from_dict(
            sc_data.get("notes", {})
        )

        study_characteristics = CochraneStudyCharacteristics(
            study_id=study_id,
            methods=sc_data.get("methods", "Not reported"),
            participants=participants,
            interventions=interventions,
            outcomes=outcomes,
            notes=notes,
            document_id=doc_id if isinstance(doc_id, int) else None,
            document_title=title,
            pmid=pmid,
            doi=doi,
        )

        # Parse risk of bias
        rob_data = data.get("risk_of_bias", {})
        risk_of_bias = self._parse_risk_of_bias(rob_data)

        # Create complete assessment
        assessment = CochraneStudyAssessment(
            study_characteristics=study_characteristics,
            risk_of_bias=risk_of_bias,
            overall_confidence=data.get("overall_confidence"),
            evidence_level=data.get("evidence_level"),
            assessment_notes=data.get("assessment_notes"),
        )

        return assessment

    def _parse_risk_of_bias(self, rob_data: Dict[str, Any]) -> CochraneRiskOfBias:
        """
        Parse risk of bias data into CochraneRiskOfBias object.

        Args:
            rob_data: Risk of bias section from LLM response

        Returns:
            CochraneRiskOfBias object
        """
        def parse_item(
            data: Dict[str, Any],
            domain: str,
            bias_type: str,
            outcome_type: Optional[str] = None
        ) -> RiskOfBiasItem:
            return RiskOfBiasItem(
                domain=domain,
                bias_type=bias_type,
                judgement=data.get("judgement", ROB_JUDGEMENT_UNCLEAR),
                support_for_judgement=data.get(
                    "support_for_judgement",
                    "Not reported or insufficient information"
                ),
                outcome_type=outcome_type,
            )

        return CochraneRiskOfBias(
            random_sequence_generation=parse_item(
                rob_data.get("random_sequence_generation", {}),
                "Random sequence generation",
                "selection bias"
            ),
            allocation_concealment=parse_item(
                rob_data.get("allocation_concealment", {}),
                "Allocation concealment",
                "selection bias"
            ),
            baseline_outcome_measurements=parse_item(
                rob_data.get("baseline_outcome_measurements", {}),
                "Baseline outcome measurements",
                "selection bias"
            ),
            baseline_characteristics=parse_item(
                rob_data.get("baseline_characteristics", {}),
                "Baseline characteristics",
                "selection bias"
            ),
            blinding_participants_personnel=parse_item(
                rob_data.get("blinding_participants_personnel", {}),
                "Blinding of participants and personnel",
                "performance bias"
            ),
            blinding_outcome_assessment_subjective=parse_item(
                rob_data.get("blinding_outcome_assessment_subjective", {}),
                "Blinding of outcome assessment (subjective outcomes)",
                "detection bias",
                outcome_type="subjective"
            ),
            blinding_outcome_assessment_objective=parse_item(
                rob_data.get("blinding_outcome_assessment_objective", {}),
                "Blinding of outcome assessment (objective outcomes)",
                "detection bias",
                outcome_type="objective"
            ),
            incomplete_outcome_data=parse_item(
                rob_data.get("incomplete_outcome_data", {}),
                "Incomplete outcome data",
                "attrition bias"
            ),
            selective_reporting=parse_item(
                rob_data.get("selective_reporting", {}),
                "Selective reporting",
                "reporting bias"
            ),
        )

    # =========================================================================
    # Batch Processing
    # =========================================================================

    def assess_batch(
        self,
        documents: List[Dict[str, Any]],
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> List[CochraneStudyAssessment]:
        """
        Assess multiple documents for Cochrane compliance.

        Args:
            documents: List of document dictionaries
            progress_callback: Optional callback(current, total, doc_title) for progress

        Returns:
            List of successful CochraneStudyAssessment objects
        """
        assessments = []
        total = len(documents)

        logger.info(f"Starting batch Cochrane assessment for {total} documents")

        for i, document in enumerate(documents):
            doc_title = document.get("title", "Unknown Document")

            if progress_callback:
                progress_callback(i + 1, total, doc_title)

            assessment = self.assess_document(document)
            if assessment:
                assessments.append(assessment)

        logger.info(
            f"Batch assessment completed: {len(assessments)}/{total} successful"
        )
        return assessments

    # =========================================================================
    # Output Formatting
    # =========================================================================

    def format_assessment_markdown(
        self, assessment: CochraneStudyAssessment
    ) -> str:
        """
        Format a single assessment as Markdown.

        Args:
            assessment: CochraneStudyAssessment object

        Returns:
            Markdown formatted string
        """
        return format_complete_assessment_markdown(assessment)

    def format_multiple_assessments_markdown(
        self,
        assessments: List[CochraneStudyAssessment],
        title: str = "Characteristics of included studies",
    ) -> str:
        """
        Format multiple assessments as Markdown document.

        Args:
            assessments: List of CochraneStudyAssessment objects
            title: Section title

        Returns:
            Complete Markdown document
        """
        return format_multiple_assessments_markdown(assessments, title)

    def format_risk_of_bias_summary(
        self, assessments: List[CochraneStudyAssessment]
    ) -> str:
        """
        Format risk of bias summary table.

        Args:
            assessments: List of CochraneStudyAssessment objects

        Returns:
            Markdown formatted summary table
        """
        return format_risk_of_bias_summary_markdown(assessments)

    # =========================================================================
    # Statistics
    # =========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """
        Get assessment statistics.

        Returns:
            Dictionary with assessment statistics
        """
        total = self._stats["total_assessments"]
        success_rate = (
            self._stats["successful_assessments"] / total if total > 0 else 0.0
        )

        return {
            **self._stats,
            "success_rate": success_rate,
        }
