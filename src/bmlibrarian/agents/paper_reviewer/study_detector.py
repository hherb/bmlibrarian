"""
Study Type Detector for Paper Reviewer

Detects study type to determine which assessments (PICO, PRISMA) are applicable.
Combines rule-based detection with LLM confirmation.
"""

import json
import logging
import re
from typing import Dict, Any, Optional, Callable, List

from ..base import BaseAgent
from ...config import get_model, get_agent_config, get_ollama_host
from .models import StudyTypeResult

logger = logging.getLogger(__name__)


# Constants
MAX_TEXT_LENGTH = 8000  # Maximum characters to analyze
DEFAULT_TEMPERATURE = 0.1  # Low temperature for consistent classification
DEFAULT_MAX_TOKENS = 1000

# Rule-based keywords for study type detection
STUDY_TYPE_KEYWORDS = {
    'systematic_review': [
        'systematic review', 'systematic literature review',
        'cochrane review', 'prisma', 'preferred reporting items',
        'systematic search', 'systematic overview',
    ],
    'meta_analysis': [
        'meta-analysis', 'meta analysis', 'pooled analysis',
        'pooled estimate', 'forest plot', 'heterogeneity i2',
        'random effects model', 'fixed effects model',
    ],
    'rct': [
        'randomized controlled trial', 'randomised controlled trial',
        'rct', 'randomized trial', 'randomised trial',
        'random allocation', 'randomly assigned', 'randomly allocated',
        'double-blind', 'double blind', 'placebo-controlled',
    ],
    'cohort_prospective': [
        'prospective cohort', 'prospective study', 'longitudinal cohort',
        'followed prospectively', 'follow-up study', 'inception cohort',
    ],
    'cohort_retrospective': [
        'retrospective cohort', 'retrospective study',
        'retrospective analysis', 'historical cohort',
    ],
    'case_control': [
        'case-control', 'case control study', 'matched controls',
        'cases and controls', 'case-referent',
    ],
    'cross_sectional': [
        'cross-sectional', 'cross sectional study', 'prevalence study',
        'survey study', 'cross-sectional survey',
    ],
    'case_series': [
        'case series', 'case-series', 'consecutive cases',
        'series of cases', 'clinical series',
    ],
    'case_report': [
        'case report', 'case study', 'clinical case',
        'index case', 'single case',
    ],
    'laboratory': [
        'in vitro', 'cell culture', 'animal model', 'mouse model',
        'rat model', 'preclinical', 'bench study', 'experimental study',
    ],
    'narrative_review': [
        'narrative review', 'literature review', 'review article',
        'overview', 'state of the art',
    ],
}

# Study type to display name mapping
STUDY_TYPE_NAMES = {
    'systematic_review': 'Systematic Review',
    'meta_analysis': 'Meta-Analysis',
    'rct': 'Randomized Controlled Trial',
    'cohort_prospective': 'Prospective Cohort Study',
    'cohort_retrospective': 'Retrospective Cohort Study',
    'case_control': 'Case-Control Study',
    'cross_sectional': 'Cross-Sectional Study',
    'case_series': 'Case Series',
    'case_report': 'Case Report',
    'laboratory': 'Laboratory/Preclinical Study',
    'narrative_review': 'Narrative Review',
    'unknown': 'Unknown Study Type',
}


class StudyTypeDetector(BaseAgent):
    """
    Detects study type to determine PICO/PRISMA applicability.

    Uses a two-phase approach:
    1. Rule-based keyword detection for initial classification
    2. LLM confirmation and detailed characterization
    """

    VERSION = "1.0.0"

    def __init__(
        self,
        model: Optional[str] = None,
        host: Optional[str] = None,
        temperature: float = DEFAULT_TEMPERATURE,
        top_p: float = 0.9,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        callback: Optional[Callable[[str, str], None]] = None,
        orchestrator: Optional[Any] = None,
        show_model_info: bool = True,
    ):
        """
        Initialize the StudyTypeDetector.

        Args:
            model: LLM model name (default: from config)
            host: Ollama server host URL (default: from config)
            temperature: Model temperature (default: 0.1)
            top_p: Model top-p sampling parameter
            max_tokens: Maximum tokens for response
            callback: Optional callback for progress updates
            orchestrator: Optional orchestrator for queue-based processing
            show_model_info: Whether to display model information
        """
        # Get defaults from config if not provided
        if model is None:
            model = get_model('paper_reviewer')
        if host is None:
            host = get_ollama_host()

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

    def get_agent_type(self) -> str:
        """Get the agent type identifier."""
        return "study_type_detector"

    def detect_study_type(
        self,
        document: Dict[str, Any],
        use_llm: bool = True,
    ) -> StudyTypeResult:
        """
        Detect study type and determine assessment applicability.

        Args:
            document: Document dictionary with title, abstract, and optionally full_text
            use_llm: Whether to use LLM for confirmation (default True)

        Returns:
            StudyTypeResult with study type and applicability flags
        """
        self._call_callback("detection_started", "Detecting study type")

        # Get text to analyze
        text = self._get_analysis_text(document)
        title = document.get('title', '')

        # Phase 1: Rule-based detection
        rule_based_type = self._rule_based_detection(text, title)
        logger.debug(f"Rule-based detection result: {rule_based_type}")

        # Phase 2: LLM confirmation and detailed analysis
        if use_llm:
            result = self._llm_detection(document, rule_based_type)
        else:
            # Use rule-based result only
            result = self._create_result_from_type(rule_based_type)

        self._call_callback(
            "detection_completed",
            f"Detected: {result.study_type} (PICO: {result.pico_applicable}, PRISMA: {result.prisma_applicable})"
        )

        return result

    def _rule_based_detection(self, text: str, title: str) -> str:
        """
        Perform rule-based study type detection using keywords.

        Args:
            text: Document text to analyze
            title: Document title

        Returns:
            Detected study type key
        """
        text_lower = text.lower()
        title_lower = title.lower()
        combined = f"{title_lower} {text_lower}"

        # Count keyword matches for each study type
        scores: Dict[str, int] = {}

        for study_type, keywords in STUDY_TYPE_KEYWORDS.items():
            score = 0
            for keyword in keywords:
                # Title matches are weighted more heavily
                if keyword in title_lower:
                    score += 3
                # Body text matches
                count = len(re.findall(re.escape(keyword), combined))
                score += count

            if score > 0:
                scores[study_type] = score

        if not scores:
            return 'unknown'

        # Return the highest scoring type
        return max(scores, key=scores.get)

    def _llm_detection(
        self,
        document: Dict[str, Any],
        rule_based_hint: str,
    ) -> StudyTypeResult:
        """
        Use LLM for detailed study type detection and characterization.

        Args:
            document: Document dictionary
            rule_based_hint: Hint from rule-based detection

        Returns:
            StudyTypeResult with detailed classification
        """
        text = self._get_analysis_text(document)
        title = document.get('title', 'Untitled')

        hint_text = ""
        if rule_based_hint and rule_based_hint != 'unknown':
            hint_text = f"\nInitial detection suggests this may be a {STUDY_TYPE_NAMES.get(rule_based_hint, rule_based_hint)}."

        prompt = f"""You are a medical research methodologist. Classify the study type of this paper.

Paper Title: {title}

Paper Text:
{text}
{hint_text}

INSTRUCTIONS:
Determine the study design and classify the paper into ONE of these categories:

PRIMARY RESEARCH:
1. **Randomized Controlled Trial (RCT)**: Participants randomly assigned to intervention/control
2. **Prospective Cohort Study**: Follows participants forward in time
3. **Retrospective Cohort Study**: Looks back at historical data
4. **Case-Control Study**: Compares cases with condition to controls without
5. **Cross-Sectional Study**: Snapshot at single point in time
6. **Case Series**: Multiple cases without controls
7. **Case Report**: Single case description
8. **Laboratory Study**: In vitro, animal models, preclinical

SECONDARY RESEARCH:
9. **Systematic Review**: Comprehensive search and synthesis following protocol
10. **Meta-Analysis**: Statistical pooling of multiple studies
11. **Narrative Review**: Non-systematic literature overview

For each classification, determine:
- Is this a clinical/intervention study? (PICO applicable)
- Is this a systematic review or meta-analysis? (PRISMA applicable)

Response format (JSON only):
{{
    "study_type": "rct|prospective_cohort|retrospective_cohort|case_control|cross_sectional|case_series|case_report|laboratory|systematic_review|meta_analysis|narrative_review|unknown",
    "study_type_detailed": "More detailed description of the study design",
    "is_clinical_study": true,
    "is_systematic_review": false,
    "is_meta_analysis": false,
    "is_observational": false,
    "is_case_report": false,
    "is_laboratory": false,
    "confidence": 0.85,
    "rationale": "Brief explanation for this classification"
}}

Classification guidance:
- is_clinical_study: True for RCTs, cohort studies, case-control, cross-sectional with interventions
- is_systematic_review: True only for studies following systematic review methodology
- is_meta_analysis: True if statistical pooling of multiple studies is performed
- is_observational: True for cohort, case-control, cross-sectional studies
- is_case_report: True for case reports and case series
- is_laboratory: True for in vitro, animal, and preclinical studies

Respond ONLY with valid JSON. No additional text."""

        try:
            result = self._generate_and_parse_json(
                prompt,
                max_retries=3,
                retry_context="study type detection",
                num_predict=self.max_tokens,
            )

            # Extract and validate fields
            study_type = result.get('study_type', 'unknown')
            study_type_detailed = result.get('study_type_detailed', STUDY_TYPE_NAMES.get(study_type, 'Unknown'))
            is_clinical = bool(result.get('is_clinical_study', False))
            is_systematic = bool(result.get('is_systematic_review', False))
            is_meta = bool(result.get('is_meta_analysis', False))
            is_observational = bool(result.get('is_observational', False))
            is_case = bool(result.get('is_case_report', False))
            is_lab = bool(result.get('is_laboratory', False))
            confidence = float(result.get('confidence', 0.7))
            rationale = result.get('rationale', '')

            return StudyTypeResult(
                study_type=study_type,
                study_type_detailed=study_type_detailed,
                is_clinical_study=is_clinical,
                is_systematic_review=is_systematic,
                is_meta_analysis=is_meta,
                is_observational=is_observational,
                is_case_report=is_case,
                is_laboratory=is_lab,
                confidence=confidence,
                rationale=rationale,
            )

        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to detect study type via LLM: {e}")
            return self._create_result_from_type(rule_based_hint or 'unknown')

    def _create_result_from_type(self, study_type: str) -> StudyTypeResult:
        """
        Create StudyTypeResult from a study type string.

        Args:
            study_type: Study type key

        Returns:
            StudyTypeResult with appropriate flags set
        """
        # Determine flags based on study type
        is_clinical = study_type in ['rct', 'cohort_prospective', 'cohort_retrospective',
                                      'case_control', 'cross_sectional']
        is_systematic = study_type == 'systematic_review'
        is_meta = study_type == 'meta_analysis'
        is_observational = study_type in ['cohort_prospective', 'cohort_retrospective',
                                           'case_control', 'cross_sectional']
        is_case = study_type in ['case_report', 'case_series']
        is_lab = study_type == 'laboratory'

        return StudyTypeResult(
            study_type=study_type,
            study_type_detailed=STUDY_TYPE_NAMES.get(study_type, 'Unknown Study Type'),
            is_clinical_study=is_clinical,
            is_systematic_review=is_systematic,
            is_meta_analysis=is_meta,
            is_observational=is_observational,
            is_case_report=is_case,
            is_laboratory=is_lab,
            confidence=0.6,  # Lower confidence for rule-based only
            rationale="Classification based on keyword detection without LLM confirmation.",
        )

    def _get_analysis_text(self, document: Dict[str, Any]) -> str:
        """
        Get text for analysis, preferring abstract for classification.

        For study type detection, abstract is often sufficient and more efficient.

        Args:
            document: Document dictionary

        Returns:
            Text string for analysis
        """
        # For classification, abstract is usually sufficient
        abstract = document.get('abstract', '')
        if abstract and len(abstract) > 200:
            # Include title + abstract (usually sufficient for classification)
            title = document.get('title', '')
            text = f"{title}\n\n{abstract}"
        else:
            # Fall back to full text
            full_text = document.get('full_text', '')
            if full_text:
                text = full_text
            else:
                text = abstract or document.get('content', '') or document.get('text', '')

        # Truncate if too long
        if len(text) > MAX_TEXT_LENGTH:
            text = text[:MAX_TEXT_LENGTH] + "..."

        return text


__all__ = ['StudyTypeDetector']
