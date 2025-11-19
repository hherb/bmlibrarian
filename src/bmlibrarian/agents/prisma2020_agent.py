"""
PRISMA 2020 Agent for Assessing Systematic Review Reporting Quality

This agent evaluates systematic reviews and meta-analyses against the PRISMA 2020
(Preferred Reporting Items for Systematic reviews and Meta-Analyses) guidelines.

The PRISMA 2020 statement includes a 27-item checklist covering:
- Title and Abstract
- Introduction (Rationale, Objectives)
- Methods (Eligibility, Search, Selection, Data Collection, Bias Assessment, Synthesis)
- Results (Study Selection, Characteristics, Syntheses, Certainty)
- Discussion (Interpretation, Limitations, Conclusions)
- Other Information (Registration, Funding)

This agent first determines if a document is suitable for PRISMA assessment (i.e., is it
a systematic review or meta-analysis?), then conducts a comprehensive evaluation of
adherence to PRISMA 2020 reporting standards.

Reference:
Page MJ, McKenzie JE, Bossuyt PM, et al. The PRISMA 2020 statement: an updated
guideline for reporting systematic reviews. BMJ 2021;372:n71.
"""

import json
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone

from .base import BaseAgent
from bmlibrarian.config import get_model, get_agent_config, get_ollama_host

logger = logging.getLogger(__name__)


# Constants for configuration
DEFAULT_MIN_CONFIDENCE = 0.4  # Default minimum confidence threshold
DEFAULT_CONFIDENCE_FALLBACK = 0.5  # Fallback confidence when not provided by LLM
SUMMARY_SEPARATOR_WIDTH = 80  # Width of separator lines in formatted summaries


@dataclass
class SuitabilityAssessment:
    """Represents assessment of whether a document is suitable for PRISMA evaluation."""

    is_systematic_review: bool
    is_meta_analysis: bool
    is_suitable: bool  # True if systematic review OR meta-analysis
    confidence: float  # 0-1 confidence in suitability assessment
    rationale: str  # Explanation of why suitable or not suitable
    document_type: str  # e.g., "systematic review", "meta-analysis", "narrative review", "primary research"

    # Metadata
    document_id: str
    document_title: str


@dataclass
class PRISMA2020Assessment:
    """
    Represents a comprehensive PRISMA 2020 checklist assessment.

    The PRISMA 2020 checklist includes 27 items across 7 sections.
    Each item is assessed for compliance with a score (0-2) and explanation:
    - 0: Not reported / Not present
    - 1: Partially reported / Inadequately reported
    - 2: Fully reported / Adequately reported
    - N/A: Not applicable (for items not relevant to all review types)
    """

    # Suitability
    is_systematic_review: bool
    is_meta_analysis: bool
    suitability_rationale: str

    # TITLE (Item 1)
    title_score: float  # Identifies report as systematic review
    title_explanation: str

    # ABSTRACT (Item 2)
    abstract_score: float  # Structured summary (background, objectives, methods, results, conclusions, funding, registration)
    abstract_explanation: str

    # INTRODUCTION
    rationale_score: float  # Item 3: Rationale for review in context of existing knowledge
    rationale_explanation: str

    objectives_score: float  # Item 4: Explicit objectives/questions with PICO
    objectives_explanation: str

    # METHODS
    eligibility_criteria_score: float  # Item 5: Inclusion/exclusion criteria with rationale
    eligibility_criteria_explanation: str

    information_sources_score: float  # Item 6: Databases, registers, websites, dates, restrictions
    information_sources_explanation: str

    search_strategy_score: float  # Item 7: Full search strategy for at least one database
    search_strategy_explanation: str

    selection_process_score: float  # Item 8: Methods for selecting studies, duplicate screening
    selection_process_explanation: str

    data_collection_score: float  # Item 9: Methods for data extraction, duplicate extraction
    data_collection_explanation: str

    data_items_score: float  # Item 10a: Variables for which data sought, assumptions made
    data_items_explanation: str

    risk_of_bias_score: float  # Item 11: Tools/methods for assessing risk of bias in individual studies
    risk_of_bias_explanation: str

    effect_measures_score: float  # Item 12: Effect measures (e.g., risk ratio, mean difference)
    effect_measures_explanation: str

    synthesis_methods_score: float  # Item 13a: Methods to prepare/combine/present study results
    synthesis_methods_explanation: str

    reporting_bias_assessment_score: float  # Item 14: Methods to assess publication bias
    reporting_bias_assessment_explanation: str

    certainty_assessment_score: float  # Item 15: Methods to assess certainty of evidence (e.g., GRADE)
    certainty_assessment_explanation: str

    # RESULTS
    study_selection_score: float  # Item 16a: Results of search and selection process with PRISMA flow diagram
    study_selection_explanation: str

    study_characteristics_score: float  # Item 17: Characteristics of included studies (citation, design, population, etc.)
    study_characteristics_explanation: str

    risk_of_bias_results_score: float  # Item 18: Risk of bias assessments for included studies
    risk_of_bias_results_explanation: str

    individual_studies_results_score: float  # Item 19: Results of individual studies with summary statistics
    individual_studies_results_explanation: str

    synthesis_results_score: float  # Item 20a: Synthesized results (meta-analysis or other)
    synthesis_results_explanation: str

    reporting_biases_results_score: float  # Item 21: Assessment of publication bias
    reporting_biases_results_explanation: str

    certainty_of_evidence_score: float  # Item 22: Assessment of certainty of evidence
    certainty_of_evidence_explanation: str

    # DISCUSSION
    discussion_score: float  # Item 23a: Interpretation of results in context of other evidence
    discussion_explanation: str

    limitations_score: float  # Item 24a: Limitations at study and review level
    limitations_explanation: str

    conclusions_score: float  # Item 25: General interpretation considering objectives, limitations, certainty
    conclusions_explanation: str

    # OTHER INFORMATION
    registration_score: float  # Item 26a: Registration information (registry, number) or protocol availability
    registration_explanation: str

    support_score: float  # Item 27: Sources of financial/non-financial support, role of funders
    support_explanation: str

    # Overall assessment
    overall_compliance_score: float  # 0-2 scale (average of all applicable items)
    overall_compliance_percentage: float  # 0-100% (compliance score / 2 * 100)
    total_applicable_items: int  # Number of items that were applicable
    fully_reported_items: int  # Number of items scoring 2.0
    partially_reported_items: int  # Number of items scoring 1.0
    not_reported_items: int  # Number of items scoring 0.0

    overall_confidence: float  # 0-1 confidence in assessment

    # Metadata
    document_id: str
    document_title: str
    pmid: Optional[str] = None
    doi: Optional[str] = None
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        if self.created_at:
            data['created_at'] = self.created_at.isoformat()
        return data

    def get_compliance_category(self) -> str:
        """Get qualitative compliance category based on percentage."""
        pct = self.overall_compliance_percentage
        if pct >= 90:
            return "Excellent (≥90%)"
        elif pct >= 75:
            return "Good (75-89%)"
        elif pct >= 60:
            return "Adequate (60-74%)"
        elif pct >= 40:
            return "Poor (40-59%)"
        else:
            return "Very Poor (<40%)"


class PRISMA2020Agent(BaseAgent):
    """
    Agent for assessing systematic reviews against PRISMA 2020 reporting guidelines.

    This agent uses large language models to:
    1. Determine if a document is a systematic review or meta-analysis (suitability check)
    2. If suitable, evaluate adherence to all 27 PRISMA 2020 checklist items
    3. Provide detailed scoring and recommendations for improving reporting quality

    This is essential for:
    - Quality assessment of systematic reviews
    - Identifying reporting gaps
    - Improving transparency and reproducibility of evidence synthesis
    - Editorial review and peer review processes
    """

    def __init__(self,
                 model: Optional[str] = None,
                 host: Optional[str] = None,
                 temperature: Optional[float] = None,
                 top_p: Optional[float] = None,
                 max_tokens: Optional[int] = None,
                 callback: Optional[Callable[[str, str], None]] = None,
                 orchestrator=None,
                 show_model_info: bool = True,
                 max_retries: Optional[int] = None):
        """
        Initialize the PRISMA2020Agent.

        Args:
            model: The name of the Ollama model to use (default: from config system)
            host: The Ollama server host URL (default: from config system)
            temperature: Model temperature for assessment (default: from config system)
            top_p: Model top-p sampling parameter (default: from config system)
            max_tokens: Maximum tokens for response (default: from config system, 4000 for PRISMA assessments)
            callback: Optional callback function for progress updates
            orchestrator: Optional orchestrator for queue-based processing
            show_model_info: Whether to display model information on initialization
            max_retries: Maximum number of retry attempts for failed assessments (default: from config system)
        """
        # Load configuration defaults
        agent_config = get_agent_config("prisma2020")

        # Use provided values or fall back to config
        model = model or get_model("prisma2020_agent", default="gpt-oss:20b")
        host = host or get_ollama_host()
        temperature = temperature if temperature is not None else agent_config.get("temperature", 0.1)
        top_p = top_p if top_p is not None else agent_config.get("top_p", 0.9)
        max_tokens_value = max_tokens if max_tokens is not None else agent_config.get("max_tokens", 4000)
        max_retries_value = max_retries if max_retries is not None else agent_config.get("max_retries", 3)

        # Filter to only include supported BaseAgent parameters
        base_params = {
            "model": model,
            "host": host,
            "temperature": temperature,
            "top_p": top_p,
            "callback": callback,
            "orchestrator": orchestrator,
            "show_model_info": show_model_info
        }

        super().__init__(**base_params)
        self.max_tokens = max_tokens_value
        self.max_retries = max_retries_value

        # Statistics tracking
        self._assessment_stats = {
            'total_assessments': 0,
            'successful_assessments': 0,
            'failed_assessments': 0,
            'unsuitable_documents': 0,  # Not systematic reviews
            'low_confidence_assessments': 0,
            'parse_failures': 0
        }

    def get_agent_type(self) -> str:
        """Get the agent type identifier."""
        return "prisma2020_agent"

    def check_suitability(
        self,
        document: Dict[str, Any]
    ) -> Optional[SuitabilityAssessment]:
        """
        Check if a document is suitable for PRISMA 2020 assessment.

        This preliminary check determines whether the document is a systematic review
        or meta-analysis before conducting the full PRISMA checklist assessment.

        Args:
            document: Document dictionary with 'abstract' (required) and optional 'full_text'

        Returns:
            SuitabilityAssessment object if check successful, None otherwise
        """
        if not self.test_connection():
            logger.error("Cannot connect to Ollama - suitability check unavailable")
            return None

        # Get document metadata
        doc_id = document.get('id', 'unknown')
        title = document.get('title', 'Untitled')
        abstract = document.get('abstract', '')
        full_text = document.get('full_text', '')

        # Use abstract + title for suitability check (more efficient)
        text_to_analyze = f"{title}\n\n{abstract}"

        # If abstract is very short, add some full text
        if len(abstract) < 200 and full_text:
            text_to_analyze += "\n\n" + full_text[:2000]

        if not text_to_analyze.strip():
            logger.warning(f"No text found for document {doc_id}")
            return None

        self._call_callback("suitability_check_started", f"Checking if document {doc_id} is suitable for PRISMA assessment")

        # Build suitability prompt
        prompt = f"""You are an expert in systematic review methodology and the PRISMA 2020 reporting guidelines.

Determine if the document below is a SYSTEMATIC REVIEW or META-ANALYSIS, which would make it suitable for PRISMA 2020 assessment.

Document Title: {title}

Document Text:
{text_to_analyze[:3000]}

INSTRUCTIONS:

A document is SUITABLE for PRISMA 2020 assessment if it is:
- A systematic review (comprehensive literature search with systematic methods to identify, select, appraise studies)
- A meta-analysis (statistical synthesis of results from multiple studies)
- A systematic review WITH meta-analysis

A document is NOT SUITABLE if it is:
- Primary research (RCT, cohort study, case-control, etc.)
- Narrative review (non-systematic literature review)
- Scoping review (without formal quality assessment)
- Clinical guideline
- Commentary or editorial
- Case report or case series

KEY INDICATORS of a systematic review:
- Mentions systematic literature search
- Reports search strategy (databases, keywords, filters)
- Describes study selection criteria
- Includes quality/bias assessment of included studies
- May include PRISMA flow diagram or mention PRISMA
- Often includes "systematic review" or "meta-analysis" in title

Assess the following:
1. is_systematic_review: Does this appear to be a systematic review?
2. is_meta_analysis: Does this include statistical meta-analysis?
3. is_suitable: Should we conduct a PRISMA 2020 assessment? (True if systematic review OR meta-analysis)
4. confidence: How confident are you in this assessment? (0.0-1.0)
5. rationale: Brief explanation (2-3 sentences) of why suitable or not suitable
6. document_type: What type of document is this? (e.g., "systematic review with meta-analysis", "primary RCT", "narrative review", "cohort study")

CRITICAL REQUIREMENTS:
- Base your assessment ONLY on what is ACTUALLY PRESENT in the text
- DO NOT assume a document is a systematic review just because it reviews literature
- Look for explicit methodology descriptions typical of systematic reviews
- If uncertain, lean towards NOT SUITABLE and explain why in the rationale

Response format (JSON only):
{{
    "is_systematic_review": true,
    "is_meta_analysis": false,
    "is_suitable": true,
    "confidence": 0.9,
    "rationale": "This document is a systematic review as evidenced by... [or] This document is not suitable because it is a [document type] which...",
    "document_type": "systematic review"
}}

Respond ONLY with valid JSON. Do not include any explanatory text outside the JSON."""

        # Make request with retry logic
        try:
            suitability_data = self._generate_and_parse_json(
                prompt,
                max_retries=self.max_retries,
                retry_context=f"suitability check (doc {doc_id})",
                num_predict=1000  # Shorter response for suitability check
            )
        except json.JSONDecodeError as e:
            logger.error(f"Could not parse JSON from LLM after {self.max_retries + 1} attempts for document {doc_id}: {e}")
            self._assessment_stats['parse_failures'] += 1
            return None
        except (ConnectionError, ValueError) as e:
            logger.error(f"Ollama request failed for document {doc_id}: {e}")
            self._assessment_stats['failed_assessments'] += 1
            return None

        # Validate JSON schema and data types
        if not self._validate_suitability_schema(suitability_data, doc_id):
            return None

        # Create SuitabilityAssessment object
        suitability = SuitabilityAssessment(
            is_systematic_review=bool(suitability_data['is_systematic_review']),
            is_meta_analysis=bool(suitability_data['is_meta_analysis']),
            is_suitable=bool(suitability_data['is_suitable']),
            confidence=float(suitability_data['confidence']),
            rationale=suitability_data['rationale'],
            document_type=suitability_data['document_type'],
            document_id=str(doc_id),
            document_title=title
        )

        self._call_callback("suitability_check_completed",
                           f"Document {doc_id} suitability: {suitability.is_suitable}")

        logger.info(
            f"Suitability check for document {doc_id}: "
            f"suitable={suitability.is_suitable}, type={suitability.document_type}, "
            f"confidence={suitability.confidence:.2f}"
        )

        if not suitability.is_suitable:
            self._assessment_stats['unsuitable_documents'] += 1

        return suitability

    def assess_prisma_compliance(
        self,
        document: Dict[str, Any],
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
        skip_suitability_check: bool = False
    ) -> Optional[PRISMA2020Assessment]:
        """
        Assess a document's compliance with PRISMA 2020 reporting guidelines.

        This method first checks if the document is suitable (systematic review or
        meta-analysis), then conducts a comprehensive assessment of all 27 PRISMA
        checklist items if suitable.

        Args:
            document: Document dictionary with 'abstract' (required) and optional 'full_text'
            min_confidence: Minimum confidence threshold to accept assessment (0-1)
            skip_suitability_check: If True, skip suitability check and assess anyway

        Returns:
            PRISMA2020Assessment object if successful, None if unsuitable or failed
        """
        if not self.test_connection():
            logger.error("Cannot connect to Ollama - PRISMA assessment unavailable")
            return None

        # Get document metadata
        doc_id = document.get('id', 'unknown')
        title = document.get('title', 'Untitled')
        abstract = document.get('abstract', '')
        full_text = document.get('full_text', '')

        # Check suitability first (unless skipped)
        if not skip_suitability_check:
            suitability = self.check_suitability(document)
            if not suitability:
                logger.error(f"Failed to assess suitability for document {doc_id}")
                return None

            if not suitability.is_suitable:
                logger.info(
                    f"Document {doc_id} not suitable for PRISMA assessment: "
                    f"{suitability.rationale}"
                )
                return None

            # Store suitability info for use in assessment
            is_systematic_review = suitability.is_systematic_review
            is_meta_analysis = suitability.is_meta_analysis
            suitability_rationale = suitability.rationale
        else:
            # Default values if suitability check skipped
            is_systematic_review = True
            is_meta_analysis = False
            suitability_rationale = "Suitability check skipped by user request"

        # Prefer full text if available, fall back to abstract
        text_to_analyze = full_text if full_text else abstract

        if not text_to_analyze:
            logger.warning(f"No text found for document {doc_id}")
            return None

        # Log text length for monitoring (but do NOT truncate - full text is essential for PRISMA assessment)
        logger.debug(f"Analyzing {len(text_to_analyze)} characters for document {doc_id}")

        self._call_callback("prisma_assessment_started",
                           f"Assessing PRISMA 2020 compliance for document {doc_id}")

        # Build comprehensive PRISMA assessment prompt
        prompt = self._build_prisma_assessment_prompt(title, text_to_analyze)

        # Make request with retry logic
        try:
            assessment_data = self._generate_and_parse_json(
                prompt,
                max_retries=self.max_retries,
                retry_context=f"PRISMA assessment (doc {doc_id})",
                num_predict=self.max_tokens
            )
        except json.JSONDecodeError as e:
            logger.error(f"Could not parse JSON from LLM after {self.max_retries + 1} attempts for document {doc_id}: {e}")
            self._assessment_stats['parse_failures'] += 1
            return None
        except (ConnectionError, ValueError) as e:
            logger.error(f"Ollama request failed for document {doc_id}: {e}")
            self._assessment_stats['failed_assessments'] += 1
            return None

        # Validate presence of required fields
        if not self._validate_assessment_data(assessment_data, doc_id):
            return None

        # Calculate summary statistics
        scores = self._extract_scores(assessment_data)
        overall_compliance_score = sum(scores) / len(scores)
        overall_compliance_percentage = (overall_compliance_score / 2.0) * 100

        fully_reported = sum(1 for s in scores if s >= 1.9)  # Score 2.0 or close
        partially_reported = sum(1 for s in scores if 0.9 <= s < 1.9)
        not_reported = sum(1 for s in scores if s < 0.9)

        # Get overall confidence
        overall_confidence = float(assessment_data.get('overall_confidence', DEFAULT_CONFIDENCE_FALLBACK))

        # Check confidence threshold
        if overall_confidence < min_confidence:
            logger.info(
                f"PRISMA assessment confidence {overall_confidence:.2f} below threshold "
                f"{min_confidence:.2f} for document {doc_id}"
            )
            self._assessment_stats['low_confidence_assessments'] += 1

        # Map all PRISMA fields using helper method
        prisma_fields = self._map_prisma_fields(assessment_data)

        # Create PRISMA2020Assessment object
        assessment = PRISMA2020Assessment(
            # Suitability
            is_systematic_review=is_systematic_review,
            is_meta_analysis=is_meta_analysis,
            suitability_rationale=suitability_rationale,

            # All 27 PRISMA items (score + explanation) - mapped automatically
            **prisma_fields,

            # Overall summary
            overall_compliance_score=overall_compliance_score,
            overall_compliance_percentage=overall_compliance_percentage,
            total_applicable_items=len(scores),
            fully_reported_items=fully_reported,
            partially_reported_items=partially_reported,
            not_reported_items=not_reported,
            overall_confidence=overall_confidence,

            # Metadata
            document_id=str(doc_id),
            document_title=title,
            pmid=document.get('pmid'),
            doi=document.get('doi')
        )

        # Update statistics
        self._assessment_stats['total_assessments'] += 1
        self._assessment_stats['successful_assessments'] += 1

        self._call_callback("prisma_assessment_completed",
                           f"Completed PRISMA assessment for document {doc_id}")

        logger.info(
            f"Successfully assessed PRISMA compliance for document {doc_id} "
            f"(compliance: {overall_compliance_percentage:.1f}%, confidence: {overall_confidence:.2f})"
        )

        return assessment

    def _build_prisma_assessment_prompt(self, title: str, text: str) -> str:
        """Build the comprehensive PRISMA assessment prompt."""
        return f"""You are an expert in systematic review methodology and the PRISMA 2020 (Preferred Reporting Items for Systematic reviews and Meta-Analyses) reporting guidelines.

Conduct a comprehensive assessment of how well this systematic review adheres to the PRISMA 2020 checklist (27 items).

Paper Title: {title}

Paper Text:
{text}

INSTRUCTIONS:

For each of the 27 PRISMA 2020 checklist items below, provide:
1. A score (0.0, 1.0, or 2.0):
   - 2.0: Fully reported / Adequately reported
   - 1.0: Partially reported / Inadequately reported
   - 0.0: Not reported / Not present

2. An explanation (1-2 sentences) describing what was found or missing

PRISMA 2020 CHECKLIST (27 items):

TITLE (Item 1):
- Does the title identify the report as a systematic review?

ABSTRACT (Item 2):
- Does the abstract provide a structured summary covering: background, objectives, data sources, study eligibility, participants, interventions, assessment methods, results, limitations, conclusions, funding, and protocol registration?

INTRODUCTION:
- Rationale (Item 3): Is the rationale for the review described in context of existing knowledge?
- Objectives (Item 4): Are objectives/questions explicit, with PICO elements specified?

METHODS:
- Eligibility criteria (Item 5): Are study characteristics (PICO, follow-up, study design) and report characteristics (language, publication period) described with rationale?
- Information sources (Item 6): Are all databases, registers, websites, etc. specified with dates and any restrictions?
- Search strategy (Item 7): Is the full search strategy presented for at least one database?
- Selection process (Item 8): Is the process for study selection described (screening, eligibility, duplicates)?
- Data collection (Item 9): Are data extraction methods and verification described?
- Data items (Item 10): Are variables/outcomes clearly defined with assumptions/simplifications noted?
- Risk of bias assessment (Item 11): Are tools/methods for bias assessment clearly specified?
- Effect measures (Item 12): Are effect measures (RR, MD, etc.) defined?
- Synthesis methods (Item 13): Are methods for data synthesis/combination described (meta-analysis methods, sensitivity analysis)?
- Reporting bias assessment (Item 14): Are methods to assess publication bias described?
- Certainty assessment (Item 15): Are methods to assess certainty/quality of evidence described (e.g., GRADE)?

RESULTS:
- Study selection (Item 16): Are selection results presented with flow diagram?
- Study characteristics (Item 17): Are included studies cited and described (design, population, setting, interventions)?
- Risk of bias results (Item 18): Are risk of bias assessments presented?
- Individual study results (Item 19): Are results of individual studies presented with summary statistics?
- Synthesis results (Item 20): Are synthesized results presented (meta-analysis, forest plots)?
- Reporting biases (Item 21): Are publication bias assessments presented?
- Certainty of evidence (Item 22): Is certainty of evidence reported with justification?

DISCUSSION:
- Discussion (Item 23): Are results interpreted in context of other evidence, implications discussed?
- Limitations (Item 24): Are review and study-level limitations discussed?
- Conclusions (Item 25): Are conclusions clear and related to objectives, avoiding overstatement?

OTHER:
- Registration (Item 26): Is protocol registration reported (registry, number, availability)?
- Support (Item 27): Are funding sources and sponsor role described?

CRITICAL REQUIREMENTS:
- Score based ONLY on what is ACTUALLY PRESENT in the text
- DO NOT assume or infer information not explicitly stated
- Be strict: partial reporting gets 1.0, not 2.0
- If analyzing an abstract only (no full text), many items will likely score 0.0 or 1.0
- Provide specific, evidence-based explanations

Additional:
- overall_confidence: Your confidence in this assessment (0.0-1.0)

Response format (JSON only):
{{
    "title_score": 2.0,
    "title_explanation": "Title clearly identifies this as a systematic review",

    "abstract_score": 1.0,
    "abstract_explanation": "Abstract present but missing protocol registration information",

    "rationale_score": 2.0,
    "rationale_explanation": "Rationale clearly stated in context of existing evidence gaps",

    "objectives_score": 2.0,
    "objectives_explanation": "Objectives explicit with PICO elements defined",

    "eligibility_criteria_score": 2.0,
    "eligibility_criteria_explanation": "Inclusion/exclusion criteria clearly stated with rationale",

    "information_sources_score": 1.0,
    "information_sources_explanation": "Databases listed but date ranges not specified",

    "search_strategy_score": 0.0,
    "search_strategy_explanation": "Search strategy not provided in text",

    "selection_process_score": 2.0,
    "selection_process_explanation": "Study selection process described with duplicate screening",

    "data_collection_score": 1.0,
    "data_collection_explanation": "Data extraction described but verification process unclear",

    "data_items_score": 2.0,
    "data_items_explanation": "Variables and outcomes clearly defined",

    "risk_of_bias_score": 2.0,
    "risk_of_bias_explanation": "Cochrane Risk of Bias tool specified",

    "effect_measures_score": 2.0,
    "effect_measures_explanation": "Risk ratios and mean differences defined",

    "synthesis_methods_score": 2.0,
    "synthesis_methods_explanation": "Random-effects meta-analysis described with sensitivity analyses",

    "reporting_bias_assessment_score": 1.0,
    "reporting_bias_assessment_explanation": "Funnel plots mentioned but formal tests not specified",

    "certainty_assessment_score": 2.0,
    "certainty_assessment_explanation": "GRADE methodology used to assess certainty",

    "study_selection_score": 2.0,
    "study_selection_explanation": "PRISMA flow diagram provided showing selection process",

    "study_characteristics_score": 2.0,
    "study_characteristics_explanation": "Included studies described in detail with table",

    "risk_of_bias_results_score": 2.0,
    "risk_of_bias_results_explanation": "Risk of bias results presented for each study",

    "individual_studies_results_score": 2.0,
    "individual_studies_results_explanation": "Individual study results presented with effect sizes and CIs",

    "synthesis_results_score": 2.0,
    "synthesis_results_explanation": "Forest plots provided for meta-analysis results",

    "reporting_biases_results_score": 1.0,
    "reporting_biases_results_explanation": "Funnel plot shown but not formally assessed",

    "certainty_of_evidence_score": 2.0,
    "certainty_of_evidence_explanation": "GRADE ratings presented with justifications",

    "discussion_score": 2.0,
    "discussion_explanation": "Results interpreted in context with clinical implications",

    "limitations_score": 2.0,
    "limitations_explanation": "Both review and study limitations discussed",

    "conclusions_score": 2.0,
    "conclusions_explanation": "Conclusions aligned with objectives without overstatement",

    "registration_score": 2.0,
    "registration_explanation": "PROSPERO registration number provided",

    "support_score": 2.0,
    "support_explanation": "Funding sources and roles clearly stated",

    "overall_confidence": 0.9
}}

Respond ONLY with valid JSON. Do not include any explanatory text outside the JSON."""

    def _validate_suitability_schema(self, data: Dict[str, Any], doc_id: str) -> bool:
        """
        Validate suitability response JSON schema and data types.

        Args:
            data: Parsed JSON data from LLM
            doc_id: Document ID for error reporting

        Returns:
            True if schema is valid, False otherwise
        """
        required_fields = {
            'is_systematic_review': bool,
            'is_meta_analysis': bool,
            'is_suitable': bool,
            'confidence': (int, float),  # Allow both int and float
            'rationale': str,
            'document_type': str
        }

        # Check for missing fields
        missing_fields = [field for field in required_fields.keys() if field not in data]
        if missing_fields:
            logger.error(
                f"Missing required fields in suitability response for document {doc_id}: "
                f"{', '.join(missing_fields)}. Got fields: {', '.join(data.keys())}"
            )
            self._assessment_stats['failed_assessments'] += 1
            return False

        # Validate data types
        type_errors = []
        for field, expected_type in required_fields.items():
            value = data[field]
            if not isinstance(value, expected_type):
                type_errors.append(
                    f"{field} (expected {expected_type.__name__}, got {type(value).__name__})"
                )

        if type_errors:
            logger.error(
                f"Type validation errors in suitability response for document {doc_id}: "
                f"{', '.join(type_errors)}"
            )
            self._assessment_stats['failed_assessments'] += 1
            return False

        # Validate confidence range
        confidence = float(data['confidence'])
        if not (0.0 <= confidence <= 1.0):
            logger.error(
                f"Invalid confidence value in suitability response for document {doc_id}: "
                f"{confidence} (must be between 0.0 and 1.0)"
            )
            self._assessment_stats['failed_assessments'] += 1
            return False

        return True

    def _validate_assessment_data(self, data: Dict[str, Any], doc_id: str) -> bool:
        """
        Validate that all required fields are present in assessment data with correct types.

        Args:
            data: Parsed JSON data from LLM
            doc_id: Document ID for error reporting

        Returns:
            True if validation passes, False otherwise
        """
        required_score_fields = [
            'title_score', 'abstract_score', 'rationale_score', 'objectives_score',
            'eligibility_criteria_score', 'information_sources_score', 'search_strategy_score',
            'selection_process_score', 'data_collection_score', 'data_items_score',
            'risk_of_bias_score', 'effect_measures_score', 'synthesis_methods_score',
            'reporting_bias_assessment_score', 'certainty_assessment_score',
            'study_selection_score', 'study_characteristics_score', 'risk_of_bias_results_score',
            'individual_studies_results_score', 'synthesis_results_score',
            'reporting_biases_results_score', 'certainty_of_evidence_score',
            'discussion_score', 'limitations_score', 'conclusions_score',
            'registration_score', 'support_score'
        ]

        required_explanation_fields = [f.replace('_score', '_explanation') for f in required_score_fields]

        all_required = required_score_fields + required_explanation_fields + ['overall_confidence']

        # Check for missing fields
        missing = [f for f in all_required if f not in data]
        if missing:
            logger.error(
                f"Missing required PRISMA fields for document {doc_id}: "
                f"{', '.join(missing)} ({len(missing)} fields missing). "
                f"Got {len(data)} fields: {', '.join(sorted(data.keys())[:10])}{'...' if len(data) > 10 else ''}"
            )
            self._assessment_stats['failed_assessments'] += 1
            return False

        # Validate score field types and ranges
        type_errors = []
        range_errors = []
        for score_field in required_score_fields:
            value = data[score_field]
            # Check if value is numeric
            if not isinstance(value, (int, float)):
                type_errors.append(
                    f"{score_field} (expected numeric, got {type(value).__name__})"
                )
            else:
                # Check if score is in valid range (0.0-2.0)
                if not (0.0 <= float(value) <= 2.0):
                    range_errors.append(
                        f"{score_field}={value} (must be between 0.0 and 2.0)"
                    )

        # Validate explanation field types
        for explanation_field in required_explanation_fields:
            value = data[explanation_field]
            if not isinstance(value, str):
                type_errors.append(
                    f"{explanation_field} (expected str, got {type(value).__name__})"
                )

        # Validate overall_confidence
        confidence = data.get('overall_confidence')
        if not isinstance(confidence, (int, float)):
            type_errors.append(
                f"overall_confidence (expected numeric, got {type(confidence).__name__})"
            )
        elif not (0.0 <= float(confidence) <= 1.0):
            range_errors.append(
                f"overall_confidence={confidence} (must be between 0.0 and 1.0)"
            )

        # Report validation errors
        if type_errors:
            logger.error(
                f"Type validation errors for document {doc_id}: "
                f"{', '.join(type_errors)}"
            )
            self._assessment_stats['failed_assessments'] += 1
            return False

        if range_errors:
            logger.error(
                f"Value range validation errors for document {doc_id}: "
                f"{', '.join(range_errors)}"
            )
            self._assessment_stats['failed_assessments'] += 1
            return False

        return True

    def _extract_scores(self, data: Dict[str, Any]) -> List[float]:
        """Extract all score values from assessment data."""
        score_fields = [
            'title_score', 'abstract_score', 'rationale_score', 'objectives_score',
            'eligibility_criteria_score', 'information_sources_score', 'search_strategy_score',
            'selection_process_score', 'data_collection_score', 'data_items_score',
            'risk_of_bias_score', 'effect_measures_score', 'synthesis_methods_score',
            'reporting_bias_assessment_score', 'certainty_assessment_score',
            'study_selection_score', 'study_characteristics_score', 'risk_of_bias_results_score',
            'individual_studies_results_score', 'synthesis_results_score',
            'reporting_biases_results_score', 'certainty_of_evidence_score',
            'discussion_score', 'limitations_score', 'conclusions_score',
            'registration_score', 'support_score'
        ]

        return [float(data[f]) for f in score_fields]

    def _map_prisma_fields(self, assessment_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map PRISMA assessment data fields to PRISMA2020Assessment constructor arguments.

        This method uses a field list to automatically map score and explanation fields,
        avoiding repetitive code and making maintenance easier.

        Args:
            assessment_data: Raw assessment data from LLM

        Returns:
            Dictionary of mapped field names to values for PRISMA2020Assessment constructor
        """
        # List of all PRISMA items (base field names without _score or _explanation suffix)
        prisma_items = [
            'title', 'abstract', 'rationale', 'objectives',
            'eligibility_criteria', 'information_sources', 'search_strategy',
            'selection_process', 'data_collection', 'data_items',
            'risk_of_bias', 'effect_measures', 'synthesis_methods',
            'reporting_bias_assessment', 'certainty_assessment',
            'study_selection', 'study_characteristics', 'risk_of_bias_results',
            'individual_studies_results', 'synthesis_results',
            'reporting_biases_results', 'certainty_of_evidence',
            'discussion', 'limitations', 'conclusions',
            'registration', 'support'
        ]

        # Build field mapping using dictionary comprehension
        field_mapping = {}
        for item in prisma_items:
            score_field = f"{item}_score"
            explanation_field = f"{item}_explanation"
            field_mapping[score_field] = float(assessment_data[score_field])
            field_mapping[explanation_field] = assessment_data[explanation_field]

        return field_mapping

    def assess_batch(
        self,
        documents: List[Dict[str, Any]],
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
        skip_suitability_check: bool = False,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> List[PRISMA2020Assessment]:
        """
        Assess PRISMA compliance for multiple systematic reviews.

        Args:
            documents: List of document dictionaries
            min_confidence: Minimum confidence threshold to accept assessments
            skip_suitability_check: If True, skip suitability checks
            progress_callback: Optional callback(current, total, doc_title) for progress updates

        Returns:
            List of successful PRISMA2020Assessment objects
        """
        assessments = []
        total = len(documents)

        logger.info(f"Starting batch PRISMA assessment for {total} documents")

        for i, document in enumerate(documents):
            doc_title = document.get('title', 'Unknown Document')

            # Call progress callback
            if progress_callback:
                progress_callback(i + 1, total, doc_title)

            # Assess PRISMA compliance
            assessment = self.assess_prisma_compliance(
                document=document,
                min_confidence=min_confidence,
                skip_suitability_check=skip_suitability_check
            )

            if assessment:
                assessments.append(assessment)
                logger.debug(f"Assessed PRISMA compliance for document {document.get('id')}")

        logger.info(
            f"Batch PRISMA assessment completed: {len(assessments)} successful out of {total} documents"
        )

        return assessments

    def get_assessment_stats(self) -> Dict[str, Any]:
        """
        Get PRISMA assessment statistics.

        Returns:
            Dictionary with assessment statistics including success rate
        """
        total = self._assessment_stats['total_assessments']
        if total == 0:
            return {**self._assessment_stats, 'success_rate': 0.0}

        return {
            **self._assessment_stats,
            'success_rate': self._assessment_stats['successful_assessments'] / total
        }

    def format_assessment_summary(self, assessment: PRISMA2020Assessment) -> str:
        """
        Format a PRISMA assessment as a human-readable summary.

        Args:
            assessment: PRISMA2020Assessment object

        Returns:
            Formatted string summary
        """
        lines = [
            f"\n{'='*SUMMARY_SEPARATOR_WIDTH}",
            f"PRISMA 2020 COMPLIANCE ASSESSMENT: {assessment.document_title}",
            f"{'='*SUMMARY_SEPARATOR_WIDTH}",
            f"Document ID: {assessment.document_id}",
        ]

        if assessment.pmid:
            lines.append(f"PMID: {assessment.pmid}")
        if assessment.doi:
            lines.append(f"DOI: {assessment.doi}")

        lines.extend([
            f"\n--- DOCUMENT TYPE ---",
            f"Systematic Review: {assessment.is_systematic_review}",
            f"Meta-Analysis: {assessment.is_meta_analysis}",
            f"Rationale: {assessment.suitability_rationale}",

            f"\n--- OVERALL COMPLIANCE ---",
            f"Compliance Score: {assessment.overall_compliance_score:.2f}/2.0 ({assessment.overall_compliance_percentage:.1f}%)",
            f"Compliance Category: {assessment.get_compliance_category()}",
            f"Assessment Confidence: {assessment.overall_confidence:.2%}",
            f"\nItems Fully Reported (2.0): {assessment.fully_reported_items}/{assessment.total_applicable_items}",
            f"Items Partially Reported (1.0): {assessment.partially_reported_items}/{assessment.total_applicable_items}",
            f"Items Not Reported (0.0): {assessment.not_reported_items}/{assessment.total_applicable_items}",
        ])

        # Show item-by-item breakdown
        lines.append(f"\n--- ITEM-BY-ITEM ASSESSMENT ---")

        items = [
            ("TITLE", "Item 1: Title", assessment.title_score, assessment.title_explanation),
            ("ABSTRACT", "Item 2: Abstract", assessment.abstract_score, assessment.abstract_explanation),
            ("INTRODUCTION", "Item 3: Rationale", assessment.rationale_score, assessment.rationale_explanation),
            ("", "Item 4: Objectives", assessment.objectives_score, assessment.objectives_explanation),
            ("METHODS", "Item 5: Eligibility criteria", assessment.eligibility_criteria_score, assessment.eligibility_criteria_explanation),
            ("", "Item 6: Information sources", assessment.information_sources_score, assessment.information_sources_explanation),
            ("", "Item 7: Search strategy", assessment.search_strategy_score, assessment.search_strategy_explanation),
            ("", "Item 8: Selection process", assessment.selection_process_score, assessment.selection_process_explanation),
            ("", "Item 9: Data collection", assessment.data_collection_score, assessment.data_collection_explanation),
            ("", "Item 10: Data items", assessment.data_items_score, assessment.data_items_explanation),
            ("", "Item 11: Risk of bias", assessment.risk_of_bias_score, assessment.risk_of_bias_explanation),
            ("", "Item 12: Effect measures", assessment.effect_measures_score, assessment.effect_measures_explanation),
            ("", "Item 13: Synthesis methods", assessment.synthesis_methods_score, assessment.synthesis_methods_explanation),
            ("", "Item 14: Reporting bias assessment", assessment.reporting_bias_assessment_score, assessment.reporting_bias_assessment_explanation),
            ("", "Item 15: Certainty assessment", assessment.certainty_assessment_score, assessment.certainty_assessment_explanation),
            ("RESULTS", "Item 16: Study selection", assessment.study_selection_score, assessment.study_selection_explanation),
            ("", "Item 17: Study characteristics", assessment.study_characteristics_score, assessment.study_characteristics_explanation),
            ("", "Item 18: Risk of bias results", assessment.risk_of_bias_results_score, assessment.risk_of_bias_results_explanation),
            ("", "Item 19: Individual studies results", assessment.individual_studies_results_score, assessment.individual_studies_results_explanation),
            ("", "Item 20: Synthesis results", assessment.synthesis_results_score, assessment.synthesis_results_explanation),
            ("", "Item 21: Reporting biases", assessment.reporting_biases_results_score, assessment.reporting_biases_results_explanation),
            ("", "Item 22: Certainty of evidence", assessment.certainty_of_evidence_score, assessment.certainty_of_evidence_explanation),
            ("DISCUSSION", "Item 23: Discussion", assessment.discussion_score, assessment.discussion_explanation),
            ("", "Item 24: Limitations", assessment.limitations_score, assessment.limitations_explanation),
            ("", "Item 25: Conclusions", assessment.conclusions_score, assessment.conclusions_explanation),
            ("OTHER", "Item 26: Registration", assessment.registration_score, assessment.registration_explanation),
            ("", "Item 27: Support/Funding", assessment.support_score, assessment.support_explanation),
        ]

        current_section = None
        for section, item_name, score, explanation in items:
            if section and section != current_section:
                lines.append(f"\n{section}:")
                current_section = section

            score_symbol = "✓✓" if score >= 1.9 else "✓" if score >= 0.9 else "✗"
            lines.append(f"  [{score_symbol}] {item_name} ({score:.1f}/2.0)")
            lines.append(f"      {explanation}")

        lines.append(f"{'='*SUMMARY_SEPARATOR_WIDTH}\n")

        return '\n'.join(lines)

    def export_to_json(self, assessments: List[PRISMA2020Assessment], output_file: str) -> None:
        """
        Export PRISMA assessments to JSON file.

        Args:
            assessments: List of PRISMA2020Assessment objects
            output_file: Path to output JSON file
        """
        data = {
            'assessments': [a.to_dict() for a in assessments],
            'metadata': {
                'total_assessments': len(assessments),
                'assessment_date': datetime.now(timezone.utc).isoformat(),
                'agent_model': self.model,
                'statistics': self.get_assessment_stats()
            }
        }

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Exported {len(assessments)} PRISMA assessments to {output_file}")

    def export_to_csv(self, assessments: List[PRISMA2020Assessment], output_file: str) -> None:
        """
        Export PRISMA assessments to CSV file.

        Args:
            assessments: List of PRISMA2020Assessment objects
            output_file: Path to output CSV file
        """
        import csv

        fieldnames = [
            'document_id', 'document_title', 'pmid', 'doi',
            'is_systematic_review', 'is_meta_analysis',
            'overall_compliance_score', 'overall_compliance_percentage',
            'fully_reported_items', 'partially_reported_items', 'not_reported_items',
            'overall_confidence',
            # All 27 item scores
            'title_score', 'abstract_score', 'rationale_score', 'objectives_score',
            'eligibility_criteria_score', 'information_sources_score', 'search_strategy_score',
            'selection_process_score', 'data_collection_score', 'data_items_score',
            'risk_of_bias_score', 'effect_measures_score', 'synthesis_methods_score',
            'reporting_bias_assessment_score', 'certainty_assessment_score',
            'study_selection_score', 'study_characteristics_score', 'risk_of_bias_results_score',
            'individual_studies_results_score', 'synthesis_results_score',
            'reporting_biases_results_score', 'certainty_of_evidence_score',
            'discussion_score', 'limitations_score', 'conclusions_score',
            'registration_score', 'support_score',
            'created_at'
        ]

        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for assessment in assessments:
                row = assessment.to_dict()
                # Keep only fields in fieldnames
                row = {k: v for k, v in row.items() if k in fieldnames}
                writer.writerow(row)

        logger.info(f"Exported {len(assessments)} PRISMA assessments to {output_file}")
