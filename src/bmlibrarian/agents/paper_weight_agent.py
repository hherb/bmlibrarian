"""
Paper Weight Assessment Agent

Multi-dimensional paper quality assessment agent that coordinates:
- Rule-based extractors for study type and sample size
- LLM-based assessors for methodological quality and risk of bias
- Database persistence with caching

This module provides the main PaperWeightAssessmentAgent class that orchestrates
all assessment components. The actual implementations are in separate modules:
- paper_weight_models.py: Data models (dataclasses)
- paper_weight_extractors.py: Rule-based extraction functions
- paper_weight_llm_assessors.py: LLM-based assessment functions
- paper_weight_db.py: Database operations
"""

import logging
from datetime import datetime
from typing import Optional, Callable, Dict, TYPE_CHECKING

from .base import BaseAgent
from ..config import get_model, get_agent_config, get_ollama_host

# Import data models
from .paper_weight_models import (
    AssessmentDetail,
    DimensionScore,
    PaperWeightResult,
    DIMENSION_STUDY_DESIGN,
    DIMENSION_SAMPLE_SIZE,
    DIMENSION_METHODOLOGICAL_QUALITY,
    DIMENSION_RISK_OF_BIAS,
    DIMENSION_REPLICATION_STATUS,
)

# Import extractors
from .paper_weight_extractors import (
    STUDY_TYPE_PRIORITY,
    extract_study_type,
    extract_sample_size_dimension,
    get_extracted_sample_size,
    get_extracted_study_type,
)

# Import LLM assessors
from .paper_weight_llm_assessors import (
    prepare_text_for_analysis,
    build_methodological_quality_prompt,
    calculate_methodological_quality_score,
    build_risk_of_bias_prompt,
    calculate_risk_of_bias_score,
    extract_mq_from_study_assessment,
    extract_rob_from_study_assessment,
    create_error_dimension_score,
)

# Import database operations
from .paper_weight_db import (
    get_cached_assessment,
    store_assessment,
    get_document,
    check_replication_status,
)

if TYPE_CHECKING:
    from .orchestrator import AgentOrchestrator


logger = logging.getLogger(__name__)


# Default configuration values
DEFAULT_CONFIG = {
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
        'rct': [
            'randomized controlled trial', 'randomised controlled trial', 'RCT',
            'randomized trial', 'randomised trial', 'random allocation', 'randomly assigned'
        ],
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


def merge_config_with_defaults(config: dict, defaults: dict) -> dict:
    """
    Deep merge config with defaults (config takes precedence).

    Args:
        config: User configuration
        defaults: Default configuration

    Returns:
        Merged configuration
    """
    result = config.copy()
    for key, value in defaults.items():
        if key not in result:
            result[key] = value
        elif isinstance(value, dict) and isinstance(result[key], dict):
            # Deep merge for nested dicts
            for subkey, subvalue in value.items():
                if subkey not in result[key]:
                    result[key][subkey] = subvalue
    return result


class PaperWeightAssessmentAgent(BaseAgent):
    """
    Multi-dimensional paper weight assessment agent.

    Assesses the evidential weight of biomedical research papers across five dimensions:
    - Study design (rule-based keyword matching)
    - Sample size (rule-based regex extraction + scoring)
    - Methodological quality (LLM-based assessment)
    - Risk of bias (LLM-based assessment)
    - Replication status (database lookup)

    The agent coordinates rule-based extractors, LLM-based assessors, and database
    operations to produce comprehensive paper weight assessments with full audit trails.
    """

    # Constants
    MAX_TEXT_LENGTH = 8000  # Maximum characters to send to LLM

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
        temperature = self.config.get('temperature', 0.3)
        top_p = self.config.get('top_p', 0.9)
        self.max_tokens = self.config.get('max_tokens', 3000)
        self.version = self.config.get('version', '1.0.0')

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
        return merge_config_with_defaults(config, DEFAULT_CONFIG)

    def get_agent_type(self) -> str:
        """Get the agent type identifier."""
        return "PaperWeightAssessmentAgent"

    def get_dimension_weights(self) -> Dict[str, float]:
        """
        Get dimension weights from configuration.

        Returns:
            Dictionary mapping dimension names to their weights
        """
        return self.config.get('dimension_weights', DEFAULT_CONFIG['dimension_weights'])

    def _assess_methodological_quality(
        self,
        document: dict,
        study_assessment: Optional[dict] = None
    ) -> DimensionScore:
        """
        Assess methodological quality using LLM analysis.

        Args:
            document: Document dict with 'abstract', 'full_text' fields
            study_assessment: Optional StudyAssessmentAgent output to leverage

        Returns:
            DimensionScore for methodological quality with detailed audit trail
        """
        # Try to leverage StudyAssessmentAgent output first
        if study_assessment:
            result = extract_mq_from_study_assessment(study_assessment)
            if result is not None:
                return result

        try:
            # Prepare text for analysis
            text = prepare_text_for_analysis(document, self.MAX_TEXT_LENGTH)

            # Build LLM prompt
            prompt = build_methodological_quality_prompt(text)

            # Call LLM with JSON parsing and retry logic
            components = self._generate_and_parse_json(
                prompt,
                max_retries=3,
                retry_context="methodological quality assessment",
                num_predict=self.max_tokens
            )

            # Calculate score
            dimension_score = calculate_methodological_quality_score(components)

            logger.info(
                f"Methodological quality assessment complete: score={dimension_score.score:.2f}/10"
            )

            return dimension_score

        except Exception as e:
            logger.error(f"Error in methodological quality assessment: {e}")
            return create_error_dimension_score(
                DIMENSION_METHODOLOGICAL_QUALITY,
                str(e)
            )

    def _assess_risk_of_bias(
        self,
        document: dict,
        study_assessment: Optional[dict] = None
    ) -> DimensionScore:
        """
        Assess risk of bias using LLM analysis.

        Args:
            document: Document dict with 'abstract', 'full_text' fields
            study_assessment: Optional StudyAssessmentAgent output to leverage

        Returns:
            DimensionScore for risk of bias with detailed audit trail
        """
        # Try to leverage StudyAssessmentAgent output first
        if study_assessment:
            result = extract_rob_from_study_assessment(study_assessment)
            if result is not None:
                return result

        try:
            # Prepare text
            text = prepare_text_for_analysis(document, self.MAX_TEXT_LENGTH)

            # Build LLM prompt
            prompt = build_risk_of_bias_prompt(text)

            # Call LLM with JSON parsing and retry logic
            components = self._generate_and_parse_json(
                prompt,
                max_retries=3,
                retry_context="risk of bias assessment",
                num_predict=self.max_tokens
            )

            # Calculate score
            dimension_score = calculate_risk_of_bias_score(components)

            logger.info(
                f"Risk of bias assessment complete: score={dimension_score.score:.2f}/10 (higher=lower risk)"
            )

            return dimension_score

        except Exception as e:
            logger.error(f"Error in risk of bias assessment: {e}")
            return create_error_dimension_score(
                DIMENSION_RISK_OF_BIAS,
                str(e)
            )

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
            assessor_version=self.version,
            assessed_at=datetime.now(),
            study_design=error_score,
            sample_size=error_score,
            methodological_quality=error_score,
            risk_of_bias=error_score,
            replication_status=error_score,
            final_weight=0.0,
            dimension_weights=self.get_dimension_weights()
        )

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
               c. Extract sample size (rule-based)
               d. Assess methodological quality (LLM)
               e. Assess risk of bias (LLM)
               f. Check replication status (database query)
               g. Compute final weight
               h. Store in database
            4. Return result
        """
        try:
            # Check cache
            if not force_reassess:
                cached = get_cached_assessment(document_id, self.version)
                if cached:
                    logger.info(f"Using cached assessment for document {document_id} (version {self.version})")
                    return cached

            logger.info(f"Performing fresh assessment for document {document_id}...")

            # Fetch document
            document = get_document(document_id)

            # Get config values for extractors
            keywords_config = self.config.get('study_type_keywords')
            hierarchy_config = self.config.get('study_type_hierarchy')
            scoring_config = self.config.get('sample_size_scoring')

            # Perform assessments
            study_design_score = extract_study_type(
                document, keywords_config, hierarchy_config, STUDY_TYPE_PRIORITY
            )
            sample_size_score = extract_sample_size_dimension(document, scoring_config)
            methodological_quality_score = self._assess_methodological_quality(document, study_assessment)
            risk_of_bias_score = self._assess_risk_of_bias(document, study_assessment)
            replication_status_score = check_replication_status(document_id)

            # Compute final weight
            dimension_scores = {
                DIMENSION_STUDY_DESIGN: study_design_score,
                DIMENSION_SAMPLE_SIZE: sample_size_score,
                DIMENSION_METHODOLOGICAL_QUALITY: methodological_quality_score,
                DIMENSION_RISK_OF_BIAS: risk_of_bias_score,
                DIMENSION_REPLICATION_STATUS: replication_status_score
            }
            final_weight = self._compute_final_weight(dimension_scores)

            # Extract metadata from dimension scores
            study_type = get_extracted_study_type(study_design_score)
            sample_size_n = get_extracted_sample_size(sample_size_score)

            # Create result
            result = PaperWeightResult(
                document_id=document_id,
                assessor_version=self.version,
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
            store_assessment(result)

            return result

        except Exception as e:
            logger.error(f"Error assessing paper {document_id}: {e}")
            return self._create_error_result(document_id, str(e))


# Re-export models for backward compatibility
__all__ = [
    'AssessmentDetail',
    'DimensionScore',
    'PaperWeightResult',
    'PaperWeightAssessmentAgent',
]
