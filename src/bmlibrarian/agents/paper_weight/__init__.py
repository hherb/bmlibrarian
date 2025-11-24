"""
Paper Weight Assessment Module

This module provides AI-powered assessment of research paper evidential weight
based on multiple dimensions including study design, sample size, methodological
quality, risk of bias, and replication status.

Main Components:
- PaperWeightAssessmentAgent: Main agent for assessing paper weight
- PaperWeightResult: Complete assessment result with all dimensions
- DimensionScore: Score for a single dimension with audit trail
- AssessmentDetail: Audit trail entry for a single assessment component

Database Functions:
- get_cached_assessment: Retrieve cached assessment from database
- store_assessment: Store assessment result to database
- get_document: Retrieve document metadata
- search_documents: Search documents by text query
- semantic_search_documents: Search documents by semantic similarity

LLM-First Extractors (Default - Recommended):
- extract_study_type_llm: Extract study type using semantic search + LLM
- extract_sample_size_llm: Extract sample size using semantic search + LLM
- ensure_document_embeddings: Create embeddings if full_text exists but no chunks

Legacy Extractors (Keyword/Regex-based):
- extract_study_type: Extract study design type via keyword matching
- extract_sample_size_dimension: Extract sample size via regex patterns
- find_sample_size: Find sample size values in text

Validators (for legacy mode):
- validate_study_type_extraction: LLM validation of keyword extraction
- validate_sample_size_extraction: LLM validation of regex extraction

LLM Assessors:
- calculate_methodological_quality_score: Calculate MQ from extracted components
- calculate_risk_of_bias_score: Calculate RoB from extracted components
- extract_mq_from_study_assessment: Extract MQ using LLM
- extract_rob_from_study_assessment: Extract RoB using LLM

Note:
    The default workflow (use_llm_extraction=True) uses LLM-first extraction
    with semantic search. This is more reliable than keyword matching because
    it understands context (e.g., "mentions systematic review" vs "IS a
    systematic review"). The legacy mode is available by setting
    use_llm_extraction=False in assess_paper().
"""

# Models - data structures
from .models import (
    AssessmentDetail,
    DimensionScore,
    PaperWeightResult,
    DATETIME_FORMAT,
    DIMENSION_STUDY_DESIGN,
    DIMENSION_SAMPLE_SIZE,
    DIMENSION_METHODOLOGICAL_QUALITY,
    DIMENSION_RISK_OF_BIAS,
    DIMENSION_REPLICATION_STATUS,
    ALL_DIMENSIONS,
)

# Main agent
from .agent import (
    PaperWeightAssessmentAgent,
    DEFAULT_CONFIG,
    merge_config_with_defaults,
)

# Database operations
from .db import (
    get_cached_assessment,
    store_assessment,
    get_document,
    check_replication_status,
    search_documents,
    semantic_search_documents,
    get_recent_assessments,
    get_document_metadata,
    SEARCH_RESULT_LIMIT,
    RECENT_ASSESSMENTS_LIMIT,
    DEFAULT_SEMANTIC_THRESHOLD,
)

# Extractors - rule-based extraction
from .extractors import (
    extract_study_type,
    extract_sample_size_dimension,
    find_sample_size,
    calculate_sample_size_score,
    has_power_calculation,
    has_ci_reporting,
    get_extracted_sample_size,
    get_extracted_study_type,
    prepare_extractor_search_text,
    STUDY_TYPE_PRIORITY,
    DEFAULT_STUDY_TYPE_KEYWORDS,
    DEFAULT_STUDY_TYPE_HIERARCHY,
    SAMPLE_SIZE_PATTERNS,
)

# Validators - LLM-based validation
from .validators import (
    ValidationResult,
    validate_study_type_extraction,
    validate_sample_size_extraction,
    add_validation_to_dimension_score,
    search_chunks_by_query,
    get_all_document_chunks,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_SIMILARITY_THRESHOLD,
    MIN_SIMILARITY_THRESHOLD,
    THRESHOLD_DECREMENT,
)

# LLM Assessors - AI-based assessment
from .llm_assessors import (
    calculate_methodological_quality_score,
    calculate_risk_of_bias_score,
    extract_mq_from_study_assessment,
    extract_rob_from_study_assessment,
    prepare_text_for_analysis,
    create_error_dimension_score,
    DEFAULT_MAX_TEXT_LENGTH,
)

# Prompts
from .prompts import (
    build_methodological_quality_prompt,
    build_risk_of_bias_prompt,
)

# LLM-first extractors - semantic search + LLM extraction
from .llm_extractors import (
    extract_study_type_llm,
    extract_sample_size_llm,
    ensure_document_embeddings,
)

__all__ = [
    # Models
    "AssessmentDetail",
    "DimensionScore",
    "PaperWeightResult",
    "DATETIME_FORMAT",
    "DIMENSION_STUDY_DESIGN",
    "DIMENSION_SAMPLE_SIZE",
    "DIMENSION_METHODOLOGICAL_QUALITY",
    "DIMENSION_RISK_OF_BIAS",
    "DIMENSION_REPLICATION_STATUS",
    "ALL_DIMENSIONS",
    # Agent
    "PaperWeightAssessmentAgent",
    "DEFAULT_CONFIG",
    "merge_config_with_defaults",
    # Database
    "get_cached_assessment",
    "store_assessment",
    "get_document",
    "check_replication_status",
    "search_documents",
    "semantic_search_documents",
    "get_recent_assessments",
    "get_document_metadata",
    "SEARCH_RESULT_LIMIT",
    "RECENT_ASSESSMENTS_LIMIT",
    "DEFAULT_SEMANTIC_THRESHOLD",
    # Extractors
    "extract_study_type",
    "extract_sample_size_dimension",
    "find_sample_size",
    "calculate_sample_size_score",
    "has_power_calculation",
    "has_ci_reporting",
    "get_extracted_sample_size",
    "get_extracted_study_type",
    "prepare_extractor_search_text",
    "STUDY_TYPE_PRIORITY",
    "DEFAULT_STUDY_TYPE_KEYWORDS",
    "DEFAULT_STUDY_TYPE_HIERARCHY",
    "SAMPLE_SIZE_PATTERNS",
    # Validators
    "ValidationResult",
    "validate_study_type_extraction",
    "validate_sample_size_extraction",
    "add_validation_to_dimension_score",
    "search_chunks_by_query",
    "get_all_document_chunks",
    "DEFAULT_EMBEDDING_MODEL",
    "DEFAULT_SIMILARITY_THRESHOLD",
    "MIN_SIMILARITY_THRESHOLD",
    "THRESHOLD_DECREMENT",
    # LLM Assessors
    "calculate_methodological_quality_score",
    "calculate_risk_of_bias_score",
    "extract_mq_from_study_assessment",
    "extract_rob_from_study_assessment",
    "prepare_text_for_analysis",
    "create_error_dimension_score",
    "DEFAULT_MAX_TEXT_LENGTH",
    # Prompts
    "build_methodological_quality_prompt",
    "build_risk_of_bias_prompt",
    # LLM-first extractors
    "extract_study_type_llm",
    "extract_sample_size_llm",
    "ensure_document_embeddings",
]
