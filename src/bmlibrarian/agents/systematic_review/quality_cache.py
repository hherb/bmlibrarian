"""
Quality Assessment Cache Module

Database operations for caching quality assessments:
- Study assessments (StudyAssessmentAgent)
- PICO extractions (PICOAgent)
- PRISMA assessments (PRISMA2020Agent)

Uses DatabaseManager for PostgreSQL connectivity (golden rule #5).
"""

import hashlib
import json
import logging
from typing import Optional, Dict, Any

from ...database import get_db_manager


logger = logging.getLogger(__name__)


# =============================================================================
# Version Management
# =============================================================================

# Agent versions should be extracted from agent classes automatically
# Default fallback versions
DEFAULT_STUDY_ASSESSMENT_VERSION = "1.0.0"
DEFAULT_PICO_VERSION = "1.0.0"
DEFAULT_PRISMA_VERSION = "1.0.0"


def get_agent_version(agent_class: type) -> str:
    """
    Extract version from agent class.

    Looks for VERSION class attribute or __version__ module attribute.
    Falls back to default if not found.

    Args:
        agent_class: Agent class to extract version from

    Returns:
        Version string
    """
    # Try class attribute first
    if hasattr(agent_class, 'VERSION'):
        return agent_class.VERSION

    # Try module __version__
    if hasattr(agent_class, '__module__'):
        module = __import__(agent_class.__module__, fromlist=['__version__'])
        if hasattr(module, '__version__'):
            return module.__version__

    # Fallback based on class name
    class_name = agent_class.__name__
    if 'StudyAssessment' in class_name:
        return DEFAULT_STUDY_ASSESSMENT_VERSION
    elif 'PICO' in class_name:
        return DEFAULT_PICO_VERSION
    elif 'PRISMA' in class_name:
        return DEFAULT_PRISMA_VERSION

    return "1.0.0"


# =============================================================================
# Prompt Hashing for Cache Invalidation
# =============================================================================

def hash_prompt(prompt_template: str) -> str:
    """
    Generate SHA256 hash of prompt template for cache invalidation.

    When prompt templates change, the hash changes, invalidating old cache entries.

    Args:
        prompt_template: Prompt template string

    Returns:
        SHA256 hash (hexadecimal string)
    """
    return hashlib.sha256(prompt_template.encode('utf-8')).hexdigest()


# =============================================================================
# Study Assessment Caching
# =============================================================================

def get_cached_study_assessment(
    document_id: int,
    agent_version: str,
    model_name: str,
    prompt_hash: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Retrieve cached study assessment from database.

    Args:
        document_id: Database ID of document
        agent_version: StudyAssessmentAgent version
        model_name: LLM model name
        prompt_hash: Optional prompt hash for strict matching

    Returns:
        Assessment dictionary if cached, None otherwise
    """
    try:
        db_manager = get_db_manager()
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        study_type,
                        study_design,
                        quality_score,
                        overall_confidence,
                        evidence_level,
                        strengths,
                        limitations,
                        confidence_explanation,
                        document_title,
                        pmid,
                        doi,
                        assessed_at
                    FROM quality_assessment.study_assessments
                    WHERE document_id = %s
                      AND agent_version = %s
                      AND model_name = %s
                      AND (%s IS NULL OR prompt_hash = %s)
                    ORDER BY assessed_at DESC
                    LIMIT 1
                """, (document_id, agent_version, model_name, prompt_hash, prompt_hash))

                row = cur.fetchone()
                if not row:
                    return None

                return {
                    "study_type": row[0],
                    "study_design": row[1],
                    "quality_score": float(row[2]),
                    "overall_confidence": float(row[3]),
                    "evidence_level": row[4],
                    "strengths": row[5] or [],
                    "limitations": row[6] or [],
                    "confidence_explanation": row[7],
                    "document_title": row[8],
                    "pmid": row[9],
                    "doi": row[10],
                    "document_id": str(document_id),
                }

    except Exception as e:
        logger.error(f"Error fetching cached study assessment: {e}")
        return None


def store_study_assessment(
    document_id: int,
    agent_version: str,
    model_name: str,
    model_parameters: Dict[str, Any],
    prompt_hash: Optional[str],
    assessment: Dict[str, Any]
) -> None:
    """
    Store study assessment in cache.

    Args:
        document_id: Database ID of document
        agent_version: StudyAssessmentAgent version
        model_name: LLM model name
        model_parameters: Model parameters dict (temperature, top_p, etc.)
        prompt_hash: Prompt template hash (or None)
        assessment: Assessment dictionary to cache
    """
    try:
        db_manager = get_db_manager()
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO quality_assessment.study_assessments (
                        document_id,
                        agent_version,
                        model_name,
                        model_parameters,
                        prompt_hash,
                        study_type,
                        study_design,
                        evidence_level,
                        quality_score,
                        overall_confidence,
                        strengths,
                        limitations,
                        confidence_explanation,
                        document_title,
                        pmid,
                        doi
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (document_id, agent_version, model_name, prompt_hash)
                    DO UPDATE SET
                        assessed_at = NOW(),
                        study_type = EXCLUDED.study_type,
                        study_design = EXCLUDED.study_design,
                        evidence_level = EXCLUDED.evidence_level,
                        quality_score = EXCLUDED.quality_score,
                        overall_confidence = EXCLUDED.overall_confidence,
                        strengths = EXCLUDED.strengths,
                        limitations = EXCLUDED.limitations,
                        confidence_explanation = EXCLUDED.confidence_explanation,
                        document_title = EXCLUDED.document_title,
                        pmid = EXCLUDED.pmid,
                        doi = EXCLUDED.doi
                """, (
                    document_id,
                    agent_version,
                    model_name,
                    json.dumps(model_parameters),
                    prompt_hash,
                    assessment.get("study_type", "unknown"),
                    assessment.get("study_design", "unknown"),
                    assessment.get("evidence_level"),
                    assessment.get("quality_score", 5.0),
                    assessment.get("overall_confidence", 0.5),
                    assessment.get("strengths", []),
                    assessment.get("limitations", []),
                    assessment.get("confidence_explanation", ""),
                    assessment.get("document_title", ""),
                    assessment.get("pmid"),
                    assessment.get("doi")
                ))

                conn.commit()

    except Exception as e:
        logger.error(f"Error storing study assessment: {e}")
        raise


# =============================================================================
# PICO Extraction Caching
# =============================================================================

def get_cached_pico_extraction(
    document_id: int,
    agent_version: str,
    model_name: str,
    prompt_hash: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Retrieve cached PICO extraction from database.

    Args:
        document_id: Database ID of document
        agent_version: PICOAgent version
        model_name: LLM model name
        prompt_hash: Optional prompt hash for strict matching

    Returns:
        PICO extraction dictionary if cached, None otherwise
    """
    try:
        db_manager = get_db_manager()
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        is_suitable,
                        suitability_rationale,
                        population,
                        population_confidence,
                        intervention,
                        intervention_confidence,
                        comparison,
                        comparison_confidence,
                        outcome,
                        outcome_confidence,
                        overall_confidence,
                        interpretation,
                        document_title,
                        pmid,
                        doi,
                        extracted_at
                    FROM quality_assessment.pico_extractions
                    WHERE document_id = %s
                      AND agent_version = %s
                      AND model_name = %s
                      AND (%s IS NULL OR prompt_hash = %s)
                    ORDER BY extracted_at DESC
                    LIMIT 1
                """, (document_id, agent_version, model_name, prompt_hash, prompt_hash))

                row = cur.fetchone()
                if not row:
                    return None

                return {
                    "is_suitable": row[0],
                    "suitability_rationale": row[1],
                    "population": row[2],
                    "population_confidence": float(row[3]) if row[3] is not None else None,
                    "intervention": row[4],
                    "intervention_confidence": float(row[5]) if row[5] is not None else None,
                    "comparison": row[6],
                    "comparison_confidence": float(row[7]) if row[7] is not None else None,
                    "outcome": row[8],
                    "outcome_confidence": float(row[9]) if row[9] is not None else None,
                    "overall_confidence": float(row[10]) if row[10] is not None else None,
                    "interpretation": row[11],
                    "document_title": row[12],
                    "pmid": row[13],
                    "doi": row[14],
                    "document_id": str(document_id),
                }

    except Exception as e:
        logger.error(f"Error fetching cached PICO extraction: {e}")
        return None


def store_pico_extraction(
    document_id: int,
    agent_version: str,
    model_name: str,
    model_parameters: Dict[str, Any],
    prompt_hash: Optional[str],
    extraction: Dict[str, Any]
) -> None:
    """
    Store PICO extraction in cache.

    Args:
        document_id: Database ID of document
        agent_version: PICOAgent version
        model_name: LLM model name
        model_parameters: Model parameters dict
        prompt_hash: Prompt template hash
        extraction: PICO extraction dictionary to cache
    """
    try:
        db_manager = get_db_manager()
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO quality_assessment.pico_extractions (
                        document_id,
                        agent_version,
                        model_name,
                        model_parameters,
                        prompt_hash,
                        is_suitable,
                        suitability_rationale,
                        population,
                        population_confidence,
                        intervention,
                        intervention_confidence,
                        comparison,
                        comparison_confidence,
                        outcome,
                        outcome_confidence,
                        overall_confidence,
                        interpretation,
                        document_title,
                        pmid,
                        doi
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (document_id, agent_version, model_name, prompt_hash)
                    DO UPDATE SET
                        extracted_at = NOW(),
                        is_suitable = EXCLUDED.is_suitable,
                        suitability_rationale = EXCLUDED.suitability_rationale,
                        population = EXCLUDED.population,
                        population_confidence = EXCLUDED.population_confidence,
                        intervention = EXCLUDED.intervention,
                        intervention_confidence = EXCLUDED.intervention_confidence,
                        comparison = EXCLUDED.comparison,
                        comparison_confidence = EXCLUDED.comparison_confidence,
                        outcome = EXCLUDED.outcome,
                        outcome_confidence = EXCLUDED.outcome_confidence,
                        overall_confidence = EXCLUDED.overall_confidence,
                        interpretation = EXCLUDED.interpretation,
                        document_title = EXCLUDED.document_title,
                        pmid = EXCLUDED.pmid,
                        doi = EXCLUDED.doi
                """, (
                    document_id,
                    agent_version,
                    model_name,
                    json.dumps(model_parameters),
                    prompt_hash,
                    extraction.get("is_suitable", False),
                    extraction.get("suitability_rationale", ""),
                    extraction.get("population"),
                    extraction.get("population_confidence"),
                    extraction.get("intervention"),
                    extraction.get("intervention_confidence"),
                    extraction.get("comparison"),
                    extraction.get("comparison_confidence"),
                    extraction.get("outcome"),
                    extraction.get("outcome_confidence"),
                    extraction.get("overall_confidence"),
                    extraction.get("interpretation", ""),
                    extraction.get("document_title", ""),
                    extraction.get("pmid"),
                    extraction.get("doi")
                ))

                conn.commit()

    except Exception as e:
        logger.error(f"Error storing PICO extraction: {e}")
        raise


# =============================================================================
# PRISMA Assessment Caching
# =============================================================================

def get_cached_prisma_assessment(
    document_id: int,
    agent_version: str,
    model_name: str,
    prompt_hash: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Retrieve cached PRISMA assessment from database.

    Args:
        document_id: Database ID of document
        agent_version: PRISMA2020Agent version
        model_name: LLM model name
        prompt_hash: Optional prompt hash for strict matching

    Returns:
        PRISMA assessment dictionary if cached, None otherwise
    """
    try:
        db_manager = get_db_manager()
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        is_suitable,
                        suitability_rationale,
                        study_type,
                        items_assessed,
                        items_reported,
                        compliance_score,
                        item_assessments,
                        overall_assessment,
                        strengths,
                        weaknesses,
                        document_title,
                        pmid,
                        doi,
                        assessed_at
                    FROM quality_assessment.prisma_assessments
                    WHERE document_id = %s
                      AND agent_version = %s
                      AND model_name = %s
                      AND (%s IS NULL OR prompt_hash = %s)
                    ORDER BY assessed_at DESC
                    LIMIT 1
                """, (document_id, agent_version, model_name, prompt_hash, prompt_hash))

                row = cur.fetchone()
                if not row:
                    return None

                # Parse JSONB item_assessments
                item_assessments = row[6]
                if isinstance(item_assessments, str):
                    item_assessments = json.loads(item_assessments)

                return {
                    "is_suitable": row[0],
                    "suitability_rationale": row[1],
                    "study_type": row[2],
                    "items_assessed": row[3],
                    "items_reported": row[4],
                    "compliance_score": float(row[5]) if row[5] is not None else None,
                    "item_assessments": item_assessments,
                    "overall_assessment": row[7],
                    "strengths": row[8] or [],
                    "weaknesses": row[9] or [],
                    "document_title": row[10],
                    "pmid": row[11],
                    "doi": row[12],
                    "document_id": str(document_id),
                }

    except Exception as e:
        logger.error(f"Error fetching cached PRISMA assessment: {e}")
        return None


def store_prisma_assessment(
    document_id: int,
    agent_version: str,
    model_name: str,
    model_parameters: Dict[str, Any],
    prompt_hash: Optional[str],
    assessment: Dict[str, Any]
) -> None:
    """
    Store PRISMA assessment in cache.

    Args:
        document_id: Database ID of document
        agent_version: PRISMA2020Agent version
        model_name: LLM model name
        model_parameters: Model parameters dict
        prompt_hash: Prompt template hash
        assessment: PRISMA assessment dictionary to cache
    """
    try:
        db_manager = get_db_manager()
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO quality_assessment.prisma_assessments (
                        document_id,
                        agent_version,
                        model_name,
                        model_parameters,
                        prompt_hash,
                        is_suitable,
                        suitability_rationale,
                        study_type,
                        items_assessed,
                        items_reported,
                        compliance_score,
                        item_assessments,
                        overall_assessment,
                        strengths,
                        weaknesses,
                        document_title,
                        pmid,
                        doi
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (document_id, agent_version, model_name, prompt_hash)
                    DO UPDATE SET
                        assessed_at = NOW(),
                        is_suitable = EXCLUDED.is_suitable,
                        suitability_rationale = EXCLUDED.suitability_rationale,
                        study_type = EXCLUDED.study_type,
                        items_assessed = EXCLUDED.items_assessed,
                        items_reported = EXCLUDED.items_reported,
                        compliance_score = EXCLUDED.compliance_score,
                        item_assessments = EXCLUDED.item_assessments,
                        overall_assessment = EXCLUDED.overall_assessment,
                        strengths = EXCLUDED.strengths,
                        weaknesses = EXCLUDED.weaknesses,
                        document_title = EXCLUDED.document_title,
                        pmid = EXCLUDED.pmid,
                        doi = EXCLUDED.doi
                """, (
                    document_id,
                    agent_version,
                    model_name,
                    json.dumps(model_parameters),
                    prompt_hash,
                    assessment.get("is_suitable", False),
                    assessment.get("suitability_rationale", ""),
                    assessment.get("study_type"),
                    assessment.get("items_assessed"),
                    assessment.get("items_reported"),
                    assessment.get("compliance_score"),
                    json.dumps(assessment.get("item_assessments", [])),
                    assessment.get("overall_assessment", ""),
                    assessment.get("strengths", []),
                    assessment.get("weaknesses", []),
                    assessment.get("document_title", ""),
                    assessment.get("pmid"),
                    assessment.get("doi")
                ))

                conn.commit()

    except Exception as e:
        logger.error(f"Error storing PRISMA assessment: {e}")
        raise


# =============================================================================
# Cache Statistics
# =============================================================================

def get_cache_statistics() -> Dict[str, Any]:
    """
    Get caching statistics for all assessment types.

    Returns:
        Dictionary with cache statistics
    """
    try:
        db_manager = get_db_manager()
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM quality_assessment.get_cache_stats()")
                rows = cur.fetchall()

                stats = {}
                for row in rows:
                    assessment_type = row[0]
                    stats[assessment_type] = {
                        "total_cached": row[1],
                        "unique_documents": row[2],
                        "unique_versions": row[3],
                        "avg_assessments_per_document": float(row[4]) if row[4] else 0.0
                    }

                return stats

    except Exception as e:
        logger.error(f"Error fetching cache statistics: {e}")
        return {}


__all__ = [
    'get_agent_version',
    'hash_prompt',
    'get_cached_study_assessment',
    'store_study_assessment',
    'get_cached_pico_extraction',
    'store_pico_extraction',
    'get_cached_prisma_assessment',
    'store_prisma_assessment',
    'get_cache_statistics',
]
