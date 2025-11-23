"""
Paper Weight LLM Validators

LLM-based validation for rule-based extraction results using semantic search.
Validates study type and sample size extractions against document chunks,
detecting conflicts between rule-based and LLM assessments.

When conflicts are detected, they are flagged for user review.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional

from .paper_weight_models import DimensionScore

logger = logging.getLogger(__name__)

# Default configuration constants
DEFAULT_EMBEDDING_MODEL = "snowflake-arctic-embed2:latest"
DEFAULT_SIMILARITY_THRESHOLD = 0.3
DEFAULT_MAX_CHUNKS = 5
DEFAULT_MAX_CONTEXT_LENGTH = 4000
DEFAULT_SAMPLE_SIZE_CONFLICT_THRESHOLD = 0.2  # 20% difference triggers conflict


@dataclass
class ValidationResult:
    """
    Result of LLM validation for a rule-based extraction.

    Attributes:
        is_valid: Whether the rule-based extraction appears valid
        has_conflict: Whether there's a conflict requiring user attention
        rule_based_value: The value from rule-based extraction
        llm_assessed_value: The LLM's independent assessment
        relevant_passages: Text passages supporting the assessment
        confidence: LLM confidence in its assessment (0.0-1.0)
        reasoning: Explanation of the validation result
        conflict_details: Details about the conflict if has_conflict is True
    """

    is_valid: bool = True
    has_conflict: bool = False
    rule_based_value: str = ""
    llm_assessed_value: str = ""
    relevant_passages: List[str] = field(default_factory=list)
    confidence: float = 0.0
    reasoning: str = ""
    conflict_details: str = ""


def search_chunks_by_query(
    document_id: int,
    query: str,
    max_chunks: int = DEFAULT_MAX_CHUNKS,
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> List[Dict[str, Any]]:
    """
    Search document chunks using semantic similarity.

    Uses embedding-based search to find chunks most relevant to the query.
    Filters by document_id first, then performs vector search on only
    that document's chunks for efficiency.

    The semantic.chunks table stores embeddings directly with the chunks,
    so we can query them together without joining to a separate embedding table.

    Args:
        document_id: Database ID of the document (must be positive)
        query: Natural language query for semantic matching (non-empty)
        max_chunks: Maximum chunks to retrieve (must be positive)
        similarity_threshold: Minimum similarity score (0.0-1.0)

    Returns:
        List of chunk dicts with 'chunk_no', 'chunk_text', 'similarity'

    Raises:
        ValueError: If inputs are invalid
    """
    # Input validation
    if document_id <= 0:
        raise ValueError(f"document_id must be positive, got {document_id}")
    if not query or not query.strip():
        raise ValueError("query cannot be empty")
    if max_chunks <= 0:
        raise ValueError(f"max_chunks must be positive, got {max_chunks}")
    if not 0.0 <= similarity_threshold <= 1.0:
        raise ValueError(f"similarity_threshold must be 0.0-1.0, got {similarity_threshold}")

    from ..database import get_db_manager

    try:
        db_manager = get_db_manager()

        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Generate embedding for the query, then search within document's chunks
                # semantic.chunks stores embedding directly (not in separate table)
                # Filter by document_id first for efficiency, then do vector search
                cur.execute("""
                    WITH query_embedding AS (
                        SELECT ollama_embedding(%s) AS embedding
                    )
                    SELECT
                        c.chunk_no,
                        substr(d.full_text, c.start_pos + 1, c.end_pos - c.start_pos + 1) as chunk_text,
                        (1 - (c.embedding <=> qe.embedding))::FLOAT AS similarity
                    FROM semantic.chunks c
                    JOIN public.document d ON c.document_id = d.id
                    CROSS JOIN query_embedding qe
                    WHERE c.document_id = %s
                      AND (1 - (c.embedding <=> qe.embedding)) >= %s
                    ORDER BY c.embedding <=> qe.embedding
                    LIMIT %s
                """, (query, document_id, similarity_threshold, max_chunks))

                results = []
                for row in cur.fetchall():
                    results.append({
                        'chunk_no': row[0],
                        'chunk_text': row[1] or '',
                        'similarity': row[2],
                    })

                logger.info(
                    f"Semantic search found {len(results)} relevant chunks "
                    f"for document {document_id}"
                )
                return results

    except Exception as e:
        logger.warning(f"Error in semantic chunk search: {e}")
        return []


DEFAULT_CHUNK_LIMIT = 20  # Default limit for get_all_document_chunks


def get_all_document_chunks(
    document_id: int,
    limit: int = DEFAULT_CHUNK_LIMIT,
) -> List[Dict[str, Any]]:
    """
    Get all chunks for a document ordered by position.

    Fallback when semantic search is unavailable or for comprehensive analysis.

    Args:
        document_id: Database ID of the document (must be positive)
        limit: Maximum chunks to retrieve (must be positive)

    Returns:
        List of chunk dicts with 'chunk_no', 'chunk_text'

    Raises:
        ValueError: If inputs are invalid
    """
    # Input validation
    if document_id <= 0:
        raise ValueError(f"document_id must be positive, got {document_id}")
    if limit <= 0:
        raise ValueError(f"limit must be positive, got {limit}")

    from ..database import get_db_manager

    try:
        db_manager = get_db_manager()

        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        c.chunk_no,
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
                        'chunk_text': row[1] or '',
                    })

                return results

    except Exception as e:
        logger.warning(f"Error getting document chunks: {e}")
        return []


def _build_study_type_validation_prompt(
    rule_based_type: str,
    rule_based_evidence: str,
    context_passages: List[str],
) -> str:
    """
    Build prompt for LLM study type validation.

    Args:
        rule_based_type: Study type extracted by rule-based method
        rule_based_evidence: Evidence text from rule-based extraction
        context_passages: Relevant passages from semantic search

    Returns:
        Formatted prompt string
    """
    context_text = "\n\n---\n\n".join(context_passages[:5])

    return f"""You are validating a study type classification for a biomedical research paper.

RULE-BASED EXTRACTION:
- Study Type: {rule_based_type}
- Evidence: {rule_based_evidence}

RELEVANT DOCUMENT PASSAGES:
{context_text}

TASK:
1. Read the passages carefully to understand the study design
2. Determine if the rule-based classification "{rule_based_type}" is correct
3. If incorrect, identify what the actual study type should be

VALID STUDY TYPES (in order of evidence strength):
- systematic_review: Systematic review of multiple studies
- meta_analysis: Meta-analysis with statistical pooling
- rct: Randomized controlled trial
- quasi_experimental: Non-randomized interventional study
- cohort_prospective: Prospective cohort study
- cohort_retrospective: Retrospective cohort study
- case_control: Case-control study
- cross_sectional: Cross-sectional survey/study
- case_series: Series of case reports
- case_report: Single case report
- unknown: Cannot determine from text

Respond in JSON format:
{{
    "is_valid": true/false,
    "assessed_type": "<study type from list above>",
    "confidence": 0.0-1.0,
    "reasoning": "<brief explanation>",
    "has_conflict": true/false,
    "conflict_details": "<explain conflict if any>"
}}"""


def _build_sample_size_validation_prompt(
    rule_based_n: Optional[int],
    rule_based_evidence: str,
    context_passages: List[str],
) -> str:
    """
    Build prompt for LLM sample size validation.

    Args:
        rule_based_n: Sample size extracted by rule-based method
        rule_based_evidence: Evidence text from rule-based extraction
        context_passages: Relevant passages from semantic search

    Returns:
        Formatted prompt string
    """
    context_text = "\n\n---\n\n".join(context_passages[:5])
    n_str = str(rule_based_n) if rule_based_n else "not_found"

    return f"""You are validating a sample size extraction from a biomedical research paper.

RULE-BASED EXTRACTION:
- Sample Size (N): {n_str}
- Evidence: {rule_based_evidence}

RELEVANT DOCUMENT PASSAGES:
{context_text}

TASK:
1. Read the passages to find mentions of sample size, participants, subjects, or patients
2. Identify the total sample size for the main analysis
3. Determine if the rule-based extraction "{n_str}" is correct or if there's a better value

GUIDELINES:
- Look for: "n=", "N=", "participants", "subjects", "patients", "enrolled", "recruited"
- Prefer total sample size over subgroup sizes
- For RCTs, sum both arms if only arm sizes given
- For multi-center studies, use total across centers

Respond in JSON format:
{{
    "is_valid": true/false,
    "assessed_n": <integer or null if cannot determine>,
    "confidence": 0.0-1.0,
    "reasoning": "<brief explanation>",
    "has_conflict": true/false,
    "conflict_details": "<explain conflict if any>"
}}"""


def validate_study_type_extraction(
    document_id: int,
    dimension_score: DimensionScore,
    llm_client: Any,
    model: str,
) -> ValidationResult:
    """
    Validate study type extraction using LLM with semantic search context.

    Args:
        document_id: Database ID of the document
        dimension_score: DimensionScore from rule-based extraction
        llm_client: Ollama client instance
        model: LLM model name to use

    Returns:
        ValidationResult with validation details and conflict flags
    """
    import json

    result = ValidationResult()

    # Extract rule-based values from dimension score
    rule_based_type = "unknown"
    rule_based_evidence = ""

    for detail in dimension_score.details:
        if detail.component == 'study_type':
            rule_based_type = detail.extracted_value or "unknown"
            rule_based_evidence = detail.evidence_text or ""
            break

    result.rule_based_value = rule_based_type

    # Search for relevant chunks about study design
    chunks = search_chunks_by_query(
        document_id=document_id,
        query="study design methodology randomized controlled trial cohort retrospective prospective systematic review meta-analysis",
        max_chunks=DEFAULT_MAX_CHUNKS,
    )

    if not chunks:
        # Fall back to getting first few chunks
        chunks = get_all_document_chunks(document_id, limit=5)

    if not chunks:
        result.reasoning = "No document chunks available for validation"
        result.is_valid = True
        return result

    # Extract passage texts
    passages = [c['chunk_text'] for c in chunks if c.get('chunk_text')]
    result.relevant_passages = passages

    # Build and execute LLM prompt
    prompt = _build_study_type_validation_prompt(
        rule_based_type=rule_based_type,
        rule_based_evidence=rule_based_evidence,
        context_passages=passages,
    )

    try:
        response = llm_client.generate(
            model=model,
            prompt=prompt,
            options={'temperature': 0.1},
        )

        response_text = response.get('response', '')

        # Parse JSON response
        # Find JSON in response (handle markdown code blocks)
        json_start = response_text.find('{')
        json_end = response_text.rfind('}') + 1

        if json_start >= 0 and json_end > json_start:
            json_str = response_text[json_start:json_end]
            parsed = json.loads(json_str)

            result.is_valid = parsed.get('is_valid', True)
            result.llm_assessed_value = parsed.get('assessed_type', rule_based_type)
            result.confidence = parsed.get('confidence', 0.5)
            result.reasoning = parsed.get('reasoning', '')
            result.has_conflict = parsed.get('has_conflict', False)
            result.conflict_details = parsed.get('conflict_details', '')

            # Check for implicit conflict
            if (result.llm_assessed_value != rule_based_type and
                result.llm_assessed_value != 'unknown' and
                rule_based_type != 'unknown'):
                result.has_conflict = True
                if not result.conflict_details:
                    result.conflict_details = (
                        f"Rule-based: {rule_based_type}, "
                        f"LLM assessed: {result.llm_assessed_value}"
                    )

        else:
            result.reasoning = "Could not parse LLM response"
            logger.warning(f"Failed to parse study type validation response: {response_text[:200]}")

    except Exception as e:
        logger.error(f"Error in study type validation: {e}")
        result.reasoning = f"Validation error: {str(e)}"

    return result


def validate_sample_size_extraction(
    document_id: int,
    dimension_score: DimensionScore,
    llm_client: Any,
    model: str,
) -> ValidationResult:
    """
    Validate sample size extraction using LLM with semantic search context.

    Args:
        document_id: Database ID of the document
        dimension_score: DimensionScore from rule-based extraction
        llm_client: Ollama client instance
        model: LLM model name to use

    Returns:
        ValidationResult with validation details and conflict flags
    """
    import json

    result = ValidationResult()

    # Extract rule-based values from dimension score
    rule_based_n: Optional[int] = None
    rule_based_evidence = ""

    for detail in dimension_score.details:
        if detail.component == 'extracted_n':
            try:
                if detail.extracted_value and detail.extracted_value != 'not_found':
                    rule_based_n = int(detail.extracted_value)
            except (ValueError, TypeError):
                pass
            rule_based_evidence = detail.evidence_text or ""
            break

    result.rule_based_value = str(rule_based_n) if rule_based_n else "not_found"

    # Search for relevant chunks about sample size
    chunks = search_chunks_by_query(
        document_id=document_id,
        query="sample size participants subjects patients enrolled recruited n= N= total number",
        max_chunks=DEFAULT_MAX_CHUNKS,
    )

    if not chunks:
        # Fall back to getting first few chunks (methods section usually early)
        chunks = get_all_document_chunks(document_id, limit=5)

    if not chunks:
        result.reasoning = "No document chunks available for validation"
        result.is_valid = True
        return result

    # Extract passage texts
    passages = [c['chunk_text'] for c in chunks if c.get('chunk_text')]
    result.relevant_passages = passages

    # Build and execute LLM prompt
    prompt = _build_sample_size_validation_prompt(
        rule_based_n=rule_based_n,
        rule_based_evidence=rule_based_evidence,
        context_passages=passages,
    )

    try:
        response = llm_client.generate(
            model=model,
            prompt=prompt,
            options={'temperature': 0.1},
        )

        response_text = response.get('response', '')

        # Parse JSON response
        json_start = response_text.find('{')
        json_end = response_text.rfind('}') + 1

        if json_start >= 0 and json_end > json_start:
            json_str = response_text[json_start:json_end]
            parsed = json.loads(json_str)

            result.is_valid = parsed.get('is_valid', True)
            assessed_n = parsed.get('assessed_n')
            result.llm_assessed_value = str(assessed_n) if assessed_n else "not_found"
            result.confidence = parsed.get('confidence', 0.5)
            result.reasoning = parsed.get('reasoning', '')
            result.has_conflict = parsed.get('has_conflict', False)
            result.conflict_details = parsed.get('conflict_details', '')

            # Check for significant sample size difference
            if rule_based_n and assessed_n:
                diff_ratio = abs(rule_based_n - assessed_n) / max(rule_based_n, assessed_n)
                if diff_ratio > DEFAULT_SAMPLE_SIZE_CONFLICT_THRESHOLD:
                    result.has_conflict = True
                    if not result.conflict_details:
                        result.conflict_details = (
                            f"Rule-based: {rule_based_n}, "
                            f"LLM assessed: {assessed_n} "
                            f"(difference: {diff_ratio:.1%})"
                        )

        else:
            result.reasoning = "Could not parse LLM response"
            logger.warning(f"Failed to parse sample size validation response: {response_text[:200]}")

    except Exception as e:
        logger.error(f"Error in sample size validation: {e}")
        result.reasoning = f"Validation error: {str(e)}"

    return result


def add_validation_to_dimension_score(
    dimension_score: DimensionScore,
    validation_result: ValidationResult,
) -> DimensionScore:
    """
    Add validation result information to a DimensionScore.

    Adds a validation detail and sets conflict flags if needed.

    Args:
        dimension_score: Original dimension score to augment
        validation_result: Result from LLM validation

    Returns:
        Updated DimensionScore with validation information
    """
    # Add validation as a detail
    validation_status = "valid" if validation_result.is_valid else "invalid"
    if validation_result.has_conflict:
        validation_status = "CONFLICT"

    dimension_score.add_detail(
        component='llm_validation',
        value=validation_status,
        contribution=0.0,  # Validation doesn't change score directly
        evidence=validation_result.relevant_passages[0] if validation_result.relevant_passages else "",
        reasoning=validation_result.reasoning,
    )

    # Add conflict detail if present
    if validation_result.has_conflict:
        dimension_score.add_detail(
            component='validation_conflict',
            value=validation_result.llm_assessed_value,
            contribution=0.0,
            evidence="",
            reasoning=validation_result.conflict_details,
        )

    return dimension_score


__all__ = [
    'ValidationResult',
    'search_chunks_by_query',
    'get_all_document_chunks',
    'validate_study_type_extraction',
    'validate_sample_size_extraction',
    'add_validation_to_dimension_score',
]
