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
from pathlib import Path
from typing import Optional, Callable, Dict, List, Any, TYPE_CHECKING

from ..base import BaseAgent
from ...config import get_model, get_agent_config, get_ollama_host

# Import data models
from .models import (
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
from .extractors import (
    STUDY_TYPE_PRIORITY,
    extract_study_type,
    extract_sample_size_dimension,
    get_extracted_sample_size,
    get_extracted_study_type,
)

# Import LLM assessors
from .llm_assessors import (
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
from .db import (
    get_cached_assessment,
    store_assessment,
    get_document,
    check_replication_status,
)

# Import validators for LLM validation of rule-based extractions
from .validators import (
    ValidationResult,
    validate_study_type_extraction,
    validate_sample_size_extraction,
    add_validation_to_dimension_score,
    get_all_document_chunks,
    search_chunks_by_query,
)

# Import LLM-first extractors
from .llm_extractors import (
    extract_study_type_llm,
    extract_sample_size_llm,
    ensure_document_embeddings,
)

if TYPE_CHECKING:
    from ..orchestrator import AgentOrchestrator


logger = logging.getLogger(__name__)


# Default configuration values
DEFAULT_CONFIG = {
    'temperature': 0.3,
    'top_p': 0.9,
    'max_tokens': 3000,
    'version': '1.0.0',
    'validate_extractions': True,  # Enable LLM validation of rule-based extractions
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
    MIN_MEANINGFUL_CHUNK_LENGTH = 100  # Minimum characters worth adding when truncating

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

    def _validate_extractions(
        self,
        document_id: int,
        study_design_score: DimensionScore,
        sample_size_score: DimensionScore,
        document: Optional[dict] = None,
    ) -> List[str]:
        """
        Validate rule-based extractions using LLM.

        Performs LLM validation of study type and sample size extractions
        to detect potential misclassifications. Uses semantic chunks when
        available, but falls back to full_text/abstract when chunks aren't
        available.

        Args:
            document_id: Database ID of the document
            study_design_score: Study design DimensionScore from rule-based extraction
            sample_size_score: Sample size DimensionScore from rule-based extraction
            document: Optional document dict with 'full_text', 'abstract' fields

        Returns:
            List of conflict descriptions (empty if no conflicts)
        """
        import ollama

        conflicts = []

        # Check if document has chunks available
        chunks = get_all_document_chunks(document_id, limit=5)

        # If no chunks, try to use full_text directly
        if not chunks and document:
            full_text = document.get('full_text') or ''
            abstract = document.get('abstract') or ''

            # Create synthetic "chunks" from full_text or abstract
            text_to_use = full_text if len(full_text) > len(abstract) else abstract

            if text_to_use:
                # Split into manageable chunks (roughly 2000 chars each)
                chunk_size = 2000
                synthetic_chunks = []
                for i in range(0, min(len(text_to_use), 10000), chunk_size):
                    chunk_text = text_to_use[i:i + chunk_size]
                    if chunk_text.strip():
                        synthetic_chunks.append({
                            'chunk_no': i // chunk_size,
                            'chunk_text': chunk_text,
                        })
                if synthetic_chunks:
                    logger.info(
                        f"Using {len(synthetic_chunks)} synthetic chunks from "
                        f"{'full_text' if len(full_text) > len(abstract) else 'abstract'} "
                        f"for validation of document {document_id}"
                    )
                    chunks = synthetic_chunks

        if not chunks:
            logger.debug(f"No chunks or text available for document {document_id}, skipping validation")
            return conflicts

        try:
            # Get configured model for validation
            model = self.model  # Use the agent's configured model

            # Validate study type
            study_validation = validate_study_type_extraction(
                document_id=document_id,
                dimension_score=study_design_score,
                llm_client=ollama,
                model=model,
                fallback_chunks=chunks,
            )

            if study_validation.has_conflict:
                conflict_msg = (
                    f"Study type conflict: Rule-based extracted '{study_validation.rule_based_value}', "
                    f"but LLM assessment suggests '{study_validation.llm_assessed_value}'. "
                    f"{study_validation.conflict_details}"
                )
                conflicts.append(conflict_msg)
                logger.warning(f"Document {document_id}: {conflict_msg}")

                # Add validation info to dimension score
                add_validation_to_dimension_score(study_design_score, study_validation)
            else:
                # Even when no conflict, add the validation info for audit trail
                add_validation_to_dimension_score(study_design_score, study_validation)

            # Validate sample size
            sample_validation = validate_sample_size_extraction(
                document_id=document_id,
                dimension_score=sample_size_score,
                llm_client=ollama,
                model=model,
                fallback_chunks=chunks,
            )

            if sample_validation.has_conflict:
                conflict_msg = (
                    f"Sample size conflict: Rule-based extracted '{sample_validation.rule_based_value}', "
                    f"but LLM assessment suggests '{sample_validation.llm_assessed_value}'. "
                    f"{sample_validation.conflict_details}"
                )
                conflicts.append(conflict_msg)
                logger.warning(f"Document {document_id}: {conflict_msg}")

                # Add validation info to dimension score
                add_validation_to_dimension_score(sample_size_score, sample_validation)
            else:
                # Even when no conflict, add the validation info for audit trail
                add_validation_to_dimension_score(sample_size_score, sample_validation)

        except Exception as e:
            logger.error(f"Error during extraction validation for document {document_id}: {e}")
            # Don't add to conflicts on error - validation is optional enhancement

        return conflicts

    def assess_paper(
        self,
        document_id: int,
        force_reassess: bool = False,
        study_assessment: Optional[dict] = None,
        use_llm_extraction: bool = True,
    ) -> PaperWeightResult:
        """
        Assess paper weight with intelligent caching.

        This is the main entry point for paper weight assessment.

        Args:
            document_id: Database ID of document to assess
            force_reassess: If True, skip cache and re-assess
            study_assessment: Optional StudyAssessmentAgent output to leverage
            use_llm_extraction: If True (default), use LLM-first extraction with
                               semantic search. If False, use legacy keyword/regex
                               extraction with LLM validation.

        Returns:
            PaperWeightResult with full audit trail

        Workflow (LLM-first mode - default):
            1. Check cache (unless force_reassess=True)
            2. If cached and version matches, return cached result
            3. Otherwise, perform full assessment:
               a. Fetch document from database
               b. Ensure embeddings exist (create if full_text available but no chunks)
               c. Extract study type using LLM + semantic search
               d. Extract sample size using LLM + semantic search
               e. Assess methodological quality (LLM)
               f. Assess risk of bias (LLM)
               g. Check replication status (database query)
               h. Compute final weight
               i. Store in database
            4. Return result

        Workflow (legacy mode):
            Uses keyword/regex extraction with LLM validation fallback.
        """
        import ollama

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

            # Step 1: Ensure embeddings exist if document has full_text
            # This enables semantic search for LLM-first extraction
            # Full text documents MUST be properly chunked and embedded - no fallback to synthetic chunks
            if use_llm_extraction:
                has_full_text = bool(document.get('full_text'))
                if has_full_text:
                    embeddings_ready = ensure_document_embeddings(
                        document_id=document_id,
                        document=document,
                    )
                    if embeddings_ready:
                        logger.info(f"Document {document_id} embeddings ready for semantic search")
                    else:
                        raise ValueError(
                            f"Document {document_id} has full_text but embedding creation failed. "
                            "Full text documents must be properly chunked and embedded before assessment."
                        )

            # Get config values
            hierarchy_config = self.config.get('study_type_hierarchy')
            scoring_config = self.config.get('sample_size_scoring')

            # Step 2: Extract study type and sample size
            if use_llm_extraction:
                # LLM-first extraction with semantic search
                logger.info("Using LLM-first extraction with semantic search")

                study_design_score = extract_study_type_llm(
                    document_id=document_id,
                    llm_client=ollama,
                    model=self.model,
                    document=document,
                    hierarchy_config=hierarchy_config,
                )

                sample_size_score = extract_sample_size_llm(
                    document_id=document_id,
                    llm_client=ollama,
                    model=self.model,
                    document=document,
                    scoring_config=scoring_config,
                )

                # No validation conflicts in LLM-first mode (LLM is primary)
                validation_conflicts = []

            else:
                # Legacy: keyword/regex extraction with LLM validation
                logger.info("Using legacy keyword/regex extraction with LLM validation")

                keywords_config = self.config.get('study_type_keywords')

                study_design_score = extract_study_type(
                    document, keywords_config, hierarchy_config, STUDY_TYPE_PRIORITY
                )
                sample_size_score = extract_sample_size_dimension(document, scoring_config)

                # Validate rule-based extractions with LLM if enabled
                validation_conflicts = []
                if self.config.get('validate_extractions', True):
                    validation_conflicts = self._validate_extractions(
                        document_id,
                        study_design_score,
                        sample_size_score,
                        document=document,
                    )

            # Step 3: LLM assessments (same for both modes)
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
                sample_size_n=sample_size_n,
                validation_conflicts=validation_conflicts,
            )

            # Store in database
            store_assessment(result)

            return result

        except Exception as e:
            logger.error(f"Error assessing paper {document_id}: {e}")
            return self._create_error_result(document_id, str(e))

    def assess_full_paper(
        self,
        document_id: int,
        pdf_path: Optional[Path] = None,
        force_reassess: bool = False,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> PaperWeightResult:
        """
        Assess paper weight using full paper text (not just abstract).

        This method extends assess_paper() to work with full papers:
        - If pdf_path is provided and document has no full_text, ingests the PDF
        - Uses semantic chunk search to retrieve relevant passages
        - Performs LLM assessment on the most relevant chunks

        Args:
            document_id: Database ID of document to assess
            pdf_path: Optional path to PDF file (will be ingested if provided)
            force_reassess: If True, skip cache and re-assess
            progress_callback: Optional callback(stage, current, total) for progress.
                              Stages: "ingesting", "searching", "assessing"

        Returns:
            PaperWeightResult with full audit trail

        Raises:
            FileNotFoundError: If pdf_path provided but file doesn't exist
        """
        from ...database import get_db_manager

        try:
            # Step 1: Check if PDF ingestion is needed
            document = get_document(document_id)
            has_full_text = bool(document.get('full_text'))

            if pdf_path and not has_full_text:
                if progress_callback:
                    progress_callback("ingesting", 0, 1)

                logger.info(f"Ingesting PDF for document {document_id}")

                # Import here to avoid circular imports
                from ...importers.pdf_ingestor import PDFIngestor

                ingestor = PDFIngestor()
                ingest_result = ingestor.ingest_pdf_immediate(
                    document_id=document_id,
                    pdf_path=pdf_path,
                    progress_callback=progress_callback,
                )

                if not ingest_result.success:
                    logger.error(f"PDF ingestion failed: {ingest_result.error_message}")
                    return self._create_error_result(
                        document_id,
                        f"PDF ingestion failed: {ingest_result.error_message}"
                    )

                # Refresh document data
                document = get_document(document_id)

                if progress_callback:
                    progress_callback("ingesting", 1, 1)

            # Step 2: Check if document has semantic chunks
            if progress_callback:
                progress_callback("searching", 0, 1)

            # Use semantic chunk search to get relevant content
            relevant_chunks = self._search_document_chunks(document_id)

            if progress_callback:
                progress_callback("searching", 1, 1)

            # Step 3: Log chunk availability (chunks provide semantic search capability)
            # Note: assess_paper() uses full_text from database directly.
            # Chunks are stored for future semantic search enhancement.
            if relevant_chunks:
                logger.info(f"Document {document_id} has {len(relevant_chunks)} semantic chunks available")

            # Step 4: Perform standard assessment using full text from database
            if progress_callback:
                progress_callback("assessing", 0, 1)

            result = self.assess_paper(
                document_id=document_id,
                force_reassess=force_reassess,
            )

            if progress_callback:
                progress_callback("assessing", 1, 1)

            return result

        except FileNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Error in full paper assessment for {document_id}: {e}")
            return self._create_error_result(document_id, str(e))

    def _search_document_chunks(
        self,
        document_id: int,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Search for semantic chunks belonging to a specific document.

        Args:
            document_id: Document database ID
            limit: Maximum chunks to retrieve

        Returns:
            List of chunk dicts with 'chunk_no', 'chunk_text', 'start_pos', 'end_pos'
        """
        from ...database import get_db_manager

        db_manager = get_db_manager()

        try:
            with db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    # Get chunks for this document ordered by position
                    cur.execute("""
                        SELECT
                            c.chunk_no,
                            c.start_pos,
                            c.end_pos,
                            substr(d.full_text, c.start_pos + 1, c.end_pos - c.start_pos + 1) as chunk_text
                        FROM semantic.chunks c
                        JOIN public.document d ON c.document_id = d.id
                        WHERE c.document_id = %s
                        ORDER BY c.chunk_no
                        LIMIT %s
                    """, (document_id, limit))

                    results = []
                    for row in cur.fetchall():
                        results.append({
                            'chunk_no': row[0],
                            'start_pos': row[1],
                            'end_pos': row[2],
                            'chunk_text': row[3] or '',
                        })

                    return results

        except Exception as e:
            logger.warning(f"Error searching document chunks: {e}")
            return []

    def _combine_chunks_for_analysis(
        self,
        chunks: List[Dict[str, Any]],
        max_length: int = None,
    ) -> str:
        """
        Combine chunks into a single text for analysis.

        Args:
            chunks: List of chunk dicts with 'chunk_text'
            max_length: Maximum combined length (uses MAX_TEXT_LENGTH if None)

        Returns:
            Combined text string
        """
        if max_length is None:
            max_length = self.MAX_TEXT_LENGTH

        # Sort by chunk_no to maintain reading order
        sorted_chunks = sorted(chunks, key=lambda c: c.get('chunk_no', 0))

        combined_parts = []
        current_length = 0

        for chunk in sorted_chunks:
            text = chunk.get('chunk_text', '')
            if not text:
                continue

            # Check if adding this chunk would exceed limit
            if current_length + len(text) > max_length:
                # Add truncated version if there's room
                remaining = max_length - current_length
                if remaining > self.MIN_MEANINGFUL_CHUNK_LENGTH:
                    combined_parts.append(text[:remaining])
                break

            combined_parts.append(text)
            current_length += len(text)

        return '\n\n'.join(combined_parts)


# Re-export models for backward compatibility
__all__ = [
    'AssessmentDetail',
    'DimensionScore',
    'PaperWeightResult',
    'PaperWeightAssessmentAgent',
]
