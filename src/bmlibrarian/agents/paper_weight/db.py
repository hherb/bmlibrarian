"""
Paper Weight Database Operations

Functions for database persistence and caching of paper weight assessments:
- Caching: retrieve cached assessments by document_id and version
- Storage: store assessments with full audit trail
- Document retrieval: fetch documents from database
- Replication status: query replication information

Uses DatabaseManager for PostgreSQL connectivity (golden rule #5).
"""

import json
import logging
from typing import Optional, Dict, List

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
from ...database import get_db_manager


logger = logging.getLogger(__name__)

# Replication scoring constants
# Score depends on number of replications and their quality relative to the original
REPLICATION_SCORE_SINGLE_COMPARABLE = 5.0   # One replication of comparable quality
REPLICATION_SCORE_SINGLE_HIGHER = 8.0       # One replication of higher quality
REPLICATION_SCORE_MULTIPLE_COMPARABLE = 8.0  # 2+ replications of comparable quality
REPLICATION_SCORE_MULTIPLE_HIGHER = 10.0     # 2+ replications of higher quality
REPLICATION_SCORE_LOWER_QUALITY = 3.0        # Lower quality replications


def get_cached_assessment(
    document_id: int,
    version: str
) -> Optional[PaperWeightResult]:
    """
    Retrieve cached assessment from database.

    Checks for existing assessment with matching document_id and assessor_version.

    Args:
        document_id: Database ID of document
        version: Assessor version to match

    Returns:
        PaperWeightResult if cached, None otherwise
    """
    try:
        db_manager = get_db_manager()
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Fetch assessment
                cur.execute("""
                    SELECT
                        assessment_id,
                        document_id,
                        assessed_at,
                        assessor_version,
                        study_design_score,
                        sample_size_score,
                        methodological_quality_score,
                        risk_of_bias_score,
                        replication_status_score,
                        final_weight,
                        dimension_weights,
                        study_type,
                        sample_size
                    FROM paper_weights.assessments
                    WHERE document_id = %s AND assessor_version = %s
                """, (document_id, version))

                row = cur.fetchone()
                if not row:
                    return None

                assessment_id = row[0]

                # Fetch assessment details
                cur.execute("""
                    SELECT
                        dimension,
                        component,
                        extracted_value,
                        score_contribution,
                        evidence_text,
                        reasoning
                    FROM paper_weights.assessment_details
                    WHERE assessment_id = %s
                    ORDER BY detail_id
                """, (assessment_id,))

                details = cur.fetchall()

                # Convert to PaperWeightResult
                return _reconstruct_result_from_db(row, details)

    except Exception as e:
        logger.error(f"Error fetching cached assessment: {e}")
        return None


def _reconstruct_result_from_db(
    assessment_row: tuple,
    detail_rows: List[tuple]
) -> PaperWeightResult:
    """
    Reconstruct PaperWeightResult from database rows.

    Args:
        assessment_row: Row from paper_weights.assessments
        detail_rows: Rows from paper_weights.assessment_details

    Returns:
        Reconstructed PaperWeightResult
    """
    # Unpack assessment row
    (assessment_id, document_id, assessed_at, assessor_version,
     study_design_score, sample_size_score, methodological_quality_score,
     risk_of_bias_score, replication_status_score, final_weight,
     dimension_weights, study_type, sample_size_n) = assessment_row

    # Parse dimension weights (JSONB)
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

    for detail_row in detail_rows:
        (dimension, component, extracted_value, score_contribution,
         evidence_text, reasoning) = detail_row

        if dimension in dimension_details:
            dimension_details[dimension].append(AssessmentDetail(
                dimension=dimension,
                component=component,
                extracted_value=extracted_value,
                score_contribution=float(score_contribution) if score_contribution else 0.0,
                evidence_text=evidence_text,
                reasoning=reasoning
            ))

    # Create dimension scores
    study_design = DimensionScore(
        dimension_name=DIMENSION_STUDY_DESIGN,
        score=float(study_design_score),
        details=dimension_details[DIMENSION_STUDY_DESIGN]
    )

    sample_size_dim = DimensionScore(
        dimension_name=DIMENSION_SAMPLE_SIZE,
        score=float(sample_size_score),
        details=dimension_details[DIMENSION_SAMPLE_SIZE]
    )

    methodological_quality = DimensionScore(
        dimension_name=DIMENSION_METHODOLOGICAL_QUALITY,
        score=float(methodological_quality_score),
        details=dimension_details[DIMENSION_METHODOLOGICAL_QUALITY]
    )

    risk_of_bias = DimensionScore(
        dimension_name=DIMENSION_RISK_OF_BIAS,
        score=float(risk_of_bias_score),
        details=dimension_details[DIMENSION_RISK_OF_BIAS]
    )

    replication_status = DimensionScore(
        dimension_name=DIMENSION_REPLICATION_STATUS,
        score=float(replication_status_score),
        details=dimension_details[DIMENSION_REPLICATION_STATUS]
    )

    # Create result
    return PaperWeightResult(
        document_id=document_id,
        assessor_version=assessor_version,
        assessed_at=assessed_at,
        study_design=study_design,
        sample_size=sample_size_dim,
        methodological_quality=methodological_quality,
        risk_of_bias=risk_of_bias,
        replication_status=replication_status,
        final_weight=float(final_weight),
        dimension_weights=dimension_weights,
        study_type=study_type,
        sample_size_n=sample_size_n
    )


def store_assessment(result: PaperWeightResult) -> None:
    """
    Store assessment in database with full audit trail.

    Inserts into both paper_weights.assessments and paper_weights.assessment_details.
    Uses ON CONFLICT to handle re-assessments with same version.

    Args:
        result: PaperWeightResult to store
    """
    try:
        db_manager = get_db_manager()
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Insert/update assessment
                cur.execute("""
                    INSERT INTO paper_weights.assessments (
                        document_id,
                        assessor_version,
                        assessed_at,
                        study_design_score,
                        sample_size_score,
                        methodological_quality_score,
                        risk_of_bias_score,
                        replication_status_score,
                        final_weight,
                        dimension_weights,
                        study_type,
                        sample_size
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (document_id, assessor_version)
                    DO UPDATE SET
                        assessed_at = EXCLUDED.assessed_at,
                        study_design_score = EXCLUDED.study_design_score,
                        sample_size_score = EXCLUDED.sample_size_score,
                        methodological_quality_score = EXCLUDED.methodological_quality_score,
                        risk_of_bias_score = EXCLUDED.risk_of_bias_score,
                        replication_status_score = EXCLUDED.replication_status_score,
                        final_weight = EXCLUDED.final_weight,
                        dimension_weights = EXCLUDED.dimension_weights,
                        study_type = EXCLUDED.study_type,
                        sample_size = EXCLUDED.sample_size
                    RETURNING assessment_id
                """, (
                    result.document_id,
                    result.assessor_version,
                    result.assessed_at,
                    result.study_design.score,
                    result.sample_size.score,
                    result.methodological_quality.score,
                    result.risk_of_bias.score,
                    result.replication_status.score,
                    result.final_weight,
                    json.dumps(result.dimension_weights),
                    result.study_type,
                    result.sample_size_n
                ))

                assessment_id = cur.fetchone()[0]

                # Delete old details (if updating)
                cur.execute("""
                    DELETE FROM paper_weights.assessment_details
                    WHERE assessment_id = %s
                """, (assessment_id,))

                # Insert new details
                all_details = result.get_all_details()
                for detail in all_details:
                    cur.execute("""
                        INSERT INTO paper_weights.assessment_details (
                            assessment_id,
                            dimension,
                            component,
                            extracted_value,
                            score_contribution,
                            evidence_text,
                            reasoning
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (
                        assessment_id,
                        detail.dimension,
                        detail.component,
                        detail.extracted_value,
                        detail.score_contribution,
                        detail.evidence_text,
                        detail.reasoning
                    ))

                conn.commit()

    except Exception as e:
        logger.error(f"Error storing assessment: {e}")
        raise


def get_document(document_id: int) -> dict:
    """
    Fetch document from database by ID.

    Args:
        document_id: Database ID of document

    Returns:
        Document dict with title, abstract, and full_text fields

    Raises:
        ValueError: If document not found
    """
    try:
        db_manager = get_db_manager()
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        id,
                        title,
                        abstract,
                        full_text
                    FROM public.document
                    WHERE id = %s
                """, (document_id,))

                row = cur.fetchone()
                if not row:
                    raise ValueError(f"Document {document_id} not found")

                return {
                    'id': row[0],
                    'title': row[1],
                    'abstract': row[2],
                    'full_text': row[3]
                }

    except ValueError:
        raise
    except Exception as e:
        logger.error(f"Error fetching document {document_id}: {e}")
        raise


def check_replication_status(document_id: int) -> DimensionScore:
    """
    Check replication status from database.

    Queries paper_weights.replications table for this document.
    Initially manual entry only - automated discovery is future work.

    Args:
        document_id: Database ID of document

    Returns:
        DimensionScore for replication status
    """
    try:
        db_manager = get_db_manager()
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Check for replications
                cur.execute("""
                    SELECT
                        replication_id,
                        replication_type,
                        quality_comparison,
                        confidence
                    FROM paper_weights.replications
                    WHERE source_document_id = %s
                    AND replication_type = 'confirms'
                """, (document_id,))

                replications = cur.fetchall()

                if not replications:
                    # No replications found
                    dimension_score = DimensionScore(
                        dimension_name=DIMENSION_REPLICATION_STATUS,
                        score=0.0
                    )
                    dimension_score.add_detail(
                        component='replication_count',
                        value='0',
                        contribution=0.0,
                        reasoning='No confirming replications found in database'
                    )
                    return dimension_score

                # Calculate score based on replications
                replication_count = len(replications)
                quality_comparison = replications[0][2]  # First replication quality

                # Scoring logic
                score = _calculate_replication_score(replication_count, quality_comparison)

                dimension_score = DimensionScore(
                    dimension_name=DIMENSION_REPLICATION_STATUS,
                    score=score
                )

                dimension_score.add_detail(
                    component='replication_count',
                    value=str(replication_count),
                    contribution=score,
                    reasoning=f'{replication_count} confirming replications found (quality: {quality_comparison})'
                )

                return dimension_score

    except Exception as e:
        logger.error(f"Error checking replication status: {e}")

        # Return zero score on error
        dimension_score = DimensionScore(
            dimension_name=DIMENSION_REPLICATION_STATUS,
            score=0.0
        )
        dimension_score.add_detail(
            component='error',
            value='query_failed',
            contribution=0.0,
            reasoning=f'Database query failed: {str(e)}'
        )
        return dimension_score


def _calculate_replication_score(replication_count: int, quality_comparison: str) -> float:
    """
    Calculate replication status score based on count and quality.

    Scoring rubric:
    - Single replication of comparable quality: 5.0
    - Single replication of higher quality: 8.0
    - Multiple (2+) replications of comparable quality: 8.0
    - Multiple (2+) replications of higher quality: 10.0
    - Lower quality replications: 3.0

    Args:
        replication_count: Number of confirming replications
        quality_comparison: Quality comparison ('higher', 'comparable', 'lower')

    Returns:
        Score (0-10)
    """
    if replication_count == 1 and quality_comparison == 'comparable':
        return REPLICATION_SCORE_SINGLE_COMPARABLE
    elif replication_count == 1 and quality_comparison == 'higher':
        return REPLICATION_SCORE_SINGLE_HIGHER
    elif replication_count >= 2 and quality_comparison == 'comparable':
        return REPLICATION_SCORE_MULTIPLE_COMPARABLE
    elif replication_count >= 2 and quality_comparison == 'higher':
        return REPLICATION_SCORE_MULTIPLE_HIGHER
    else:
        return REPLICATION_SCORE_LOWER_QUALITY


# Search and query limits
SEARCH_RESULT_LIMIT = 50
RECENT_ASSESSMENTS_LIMIT = 20
DEFAULT_SEMANTIC_THRESHOLD = 0.6
PUBMED_SOURCE_ID = 1


def semantic_search_documents(
    query: str,
    limit: int = SEARCH_RESULT_LIMIT,
    threshold: float = DEFAULT_SEMANTIC_THRESHOLD
) -> List[Dict]:
    """
    Search documents using semantic similarity (vector search).

    Uses the semantic_docsearch PostgreSQL function for fast embedding-based search.

    Args:
        query: Natural language query for semantic matching
        limit: Maximum number of results to return
        threshold: Similarity threshold (0.0 to 1.0, higher = more similar)

    Returns:
        List of document dictionaries with id, title, pmid, doi, year, similarity,
        has_pdf, has_full_text, pdf_filename
    """
    try:
        db_manager = get_db_manager()
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        d.id,
                        d.title,
                        CASE WHEN d.source_id = %s THEN d.external_id ELSE NULL END as pmid,
                        d.doi,
                        EXTRACT(YEAR FROM d.publication_date)::INTEGER as year,
                        s.score as similarity,
                        d.pdf_filename IS NOT NULL AND d.pdf_filename != '' as has_pdf,
                        d.full_text IS NOT NULL AND d.full_text != '' as has_full_text,
                        d.pdf_filename,
                        d.pdf_url
                    FROM semantic_docsearch(%s, %s, %s) s
                    JOIN public.document d ON s.document_id = d.id
                    ORDER BY s.score DESC
                """, (PUBMED_SOURCE_ID, query, threshold, limit))

                rows = cur.fetchall()
                return [
                    {
                        'id': row[0],
                        'title': row[1],
                        'pmid': row[2],
                        'doi': row[3],
                        'year': row[4],
                        'similarity': float(row[5]) if row[5] else None,
                        'has_pdf': bool(row[6]),
                        'has_full_text': bool(row[7]),
                        'pdf_filename': row[8],
                        'pdf_url': row[9],
                    }
                    for row in rows
                ]

    except Exception as e:
        logger.error(f"Error in semantic search: {e}")
        return []


def search_documents(
    query: str,
    limit: int = SEARCH_RESULT_LIMIT
) -> List[Dict]:
    """
    Search documents by PMID (external_id), DOI, or title.

    Args:
        query: Search query (PMID, DOI, or title keywords)
        limit: Maximum number of results to return

    Returns:
        List of document dictionaries with id, title, pmid, doi, year,
        has_pdf, has_full_text, pdf_filename, pdf_url
    """
    try:
        db_manager = get_db_manager()
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Common SELECT columns
                select_cols = """
                    id, title, external_id as pmid, doi,
                    EXTRACT(YEAR FROM publication_date)::INTEGER as year,
                    pdf_filename IS NOT NULL AND pdf_filename != '' as has_pdf,
                    full_text IS NOT NULL AND full_text != '' as has_full_text,
                    pdf_filename,
                    pdf_url
                """

                # Try PMID first (numeric) - stored in external_id column
                if query.isdigit():
                    cur.execute(f"""
                        SELECT {select_cols}
                        FROM public.document
                        WHERE external_id = %s
                        LIMIT %s
                    """, (query, limit))
                # Try DOI pattern
                elif query.startswith('10.') or '/' in query:
                    cur.execute(f"""
                        SELECT {select_cols}
                        FROM public.document
                        WHERE doi ILIKE %s
                        LIMIT %s
                    """, (f'%{query}%', limit))
                # Title search
                else:
                    cur.execute(f"""
                        SELECT {select_cols}
                        FROM public.document
                        WHERE title ILIKE %s
                        ORDER BY publication_date DESC NULLS LAST
                        LIMIT %s
                    """, (f'%{query}%', limit))

                rows = cur.fetchall()
                return [
                    {
                        'id': row[0],
                        'title': row[1],
                        'pmid': row[2],
                        'doi': row[3],
                        'year': row[4],
                        'has_pdf': bool(row[5]),
                        'has_full_text': bool(row[6]),
                        'pdf_filename': row[7],
                        'pdf_url': row[8],
                    }
                    for row in rows
                ]

    except Exception as e:
        logger.error(f"Error searching documents: {e}")
        return []


def get_recent_assessments(limit: int = RECENT_ASSESSMENTS_LIMIT) -> List[Dict]:
    """
    Get recently assessed documents.

    Args:
        limit: Maximum number of results to return

    Returns:
        List of dictionaries with assessment info and document metadata
    """
    try:
        db_manager = get_db_manager()
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        a.document_id,
                        d.title,
                        d.external_id as pmid,
                        d.doi,
                        a.final_weight,
                        a.assessed_at,
                        a.assessor_version
                    FROM paper_weights.assessments a
                    JOIN public.document d ON a.document_id = d.id
                    ORDER BY a.assessed_at DESC
                    LIMIT %s
                """, (limit,))

                rows = cur.fetchall()
                return [
                    {
                        'document_id': row[0],
                        'title': row[1],
                        'pmid': row[2],
                        'doi': row[3],
                        'final_weight': row[4],
                        'assessed_at': row[5],
                        'version': row[6]
                    }
                    for row in rows
                ]

    except Exception as e:
        logger.error(f"Error fetching recent assessments: {e}")
        return []


def get_document_metadata(document_id: int) -> Optional[Dict]:
    """
    Get document metadata by ID.

    Args:
        document_id: Database ID of document

    Returns:
        Document metadata dictionary or None if not found
    """
    try:
        db_manager = get_db_manager()
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        id, title, abstract, external_id as pmid, doi, authors,
                        EXTRACT(YEAR FROM publication_date)::INTEGER as year
                    FROM public.document
                    WHERE id = %s
                """, (document_id,))

                row = cur.fetchone()
                if row:
                    return {
                        'id': row[0],
                        'title': row[1],
                        'abstract': row[2],
                        'pmid': row[3],
                        'doi': row[4],
                        'authors': row[5],
                        'year': row[6]
                    }
                return None

    except Exception as e:
        logger.error(f"Error fetching document metadata: {e}")
        return None


__all__ = [
    'get_cached_assessment',
    'store_assessment',
    'get_document',
    'check_replication_status',
    'search_documents',
    'semantic_search_documents',
    'get_recent_assessments',
    'get_document_metadata',
    'SEARCH_RESULT_LIMIT',
    'RECENT_ASSESSMENTS_LIMIT',
    'DEFAULT_SEMANTIC_THRESHOLD',
    'PUBMED_SOURCE_ID',
]
