"""
Paper Weight LLM-First Extractors

LLM-based extraction functions for study type and sample size that use
semantic search to find relevant passages and then apply LLM analysis.

This approach is more reliable than keyword/regex extraction because:
1. It understands context (e.g., "mentions a systematic review" vs "is a systematic review")
2. It can find relevant information even with varied terminology
3. It provides supporting quotes for audit trails

The workflow is:
1. Use semantic search to find relevant chunks (study design, methods, etc.)
2. Send relevant passages to LLM with extraction prompts
3. Return structured DimensionScore with audit trail
"""

import json
import logging
from typing import Dict, List, Any, Optional

from .models import (
    DimensionScore,
    DIMENSION_STUDY_DESIGN,
    DIMENSION_SAMPLE_SIZE,
)
from .extractors import (
    DEFAULT_STUDY_TYPE_HIERARCHY,
    calculate_sample_size_score,
)
from .validators import (
    search_chunks_by_query,
    get_all_document_chunks,
    DEFAULT_SIMILARITY_THRESHOLD,
    MIN_SIMILARITY_THRESHOLD,
    THRESHOLD_DECREMENT,
)

logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_MAX_CHUNKS = 5


def _build_study_type_extraction_prompt(passages: List[str]) -> str:
    """
    Build prompt for LLM-first study type extraction.

    Args:
        passages: Relevant text passages from semantic search

    Returns:
        Formatted prompt string
    """
    context_text = "\n\n---\n\n".join(passages[:5])

    return f"""You are analyzing a biomedical research paper to determine its study design type.

DOCUMENT PASSAGES:
{context_text}

TASK:
1. Read the passages carefully to understand what type of study this paper describes
2. Identify the PRIMARY study design - what the paper itself IS, not what it references or discusses
3. Be careful: A paper that MENTIONS or REVIEWS systematic reviews is not necessarily a systematic review itself
4. Look for explicit methodology descriptions: "We conducted a...", "This is a...", "Methods: ..."

VALID STUDY TYPES (in order of evidence strength):
- systematic_review: Paper IS a systematic review of multiple studies (has PRISMA, search strategy, inclusion criteria)
- meta_analysis: Paper IS a meta-analysis with statistical pooling of data from multiple studies
- rct: Paper IS a randomized controlled trial (random allocation, control group, intervention). Includes crossover RCTs where participants receive all treatments in random order.
- quasi_experimental: Paper IS a non-randomized interventional study
- pilot_feasibility: Paper IS a pilot or feasibility study (preliminary, small-scale)
- interventional_single_arm: Paper IS an open-label, single-arm interventional study
- cohort_prospective: Paper IS a prospective cohort study (followed subjects over time)
- cohort_retrospective: Paper IS a retrospective cohort study (looked back at records)
- case_control: Paper IS a case-control study (compared cases to controls)
- cross_sectional: Paper IS a cross-sectional study (snapshot in time)
- case_series: Paper IS a case series (multiple case reports)
- case_report: Paper IS a single case report
- unknown: Cannot determine study type from available text

KEY PHRASES TO LOOK FOR:
- "randomized crossover study" or "randomized crossover trial" → rct
- "randomized controlled trial" or "RCT" → rct
- "participants were randomized" → rct
- "systematic review" with PRISMA/search strategy → systematic_review
- "meta-analysis" with pooled data → meta_analysis
- "prospective cohort" → cohort_prospective
- "retrospective cohort" or "retrospective analysis" → cohort_retrospective

IMPORTANT DISTINCTIONS:
- A review article discussing RCTs is NOT an RCT
- A paper citing systematic reviews is NOT a systematic review
- Look for the paper's OWN methodology, not what it discusses

Respond in JSON format:
{{
    "study_type": "<one of the study types listed above>",
    "confidence": 0.0-1.0,
    "reasoning": "<brief explanation of why this study type was identified>",
    "supporting_quote": "<exact verbatim quote from the text that identifies what type of study THIS PAPER is>"
}}"""


def _build_sample_size_extraction_prompt(passages: List[str]) -> str:
    """
    Build prompt for LLM-first sample size extraction.

    Args:
        passages: Relevant text passages from semantic search

    Returns:
        Formatted prompt string
    """
    context_text = "\n\n---\n\n".join(passages[:5])

    return f"""You are analyzing a biomedical research paper to extract the sample size.

DOCUMENT PASSAGES:
{context_text}

TASK:
1. Find mentions of sample size, participants, subjects, or patients
2. Identify the TOTAL sample size for the main analysis (not subgroups)
3. For RCTs, sum both/all arms if only arm sizes are given
4. For multi-center studies, use total across centers
5. Extract the EXACT quote that states the sample size

LOOK FOR:
- "n=", "N=", "sample size of", "total of X participants"
- "enrolled X subjects", "recruited X patients"
- Participant flow diagrams/CONSORT numbers
- Methods section sample size statements

GUIDELINES:
- Prefer the final analyzed sample over initially enrolled if both are given
- If multiple numbers are found, report the most relevant (total study N)
- If no sample size can be determined, report null

Respond in JSON format:
{{
    "sample_size": <integer or null if cannot determine>,
    "confidence": 0.0-1.0,
    "reasoning": "<brief explanation of how sample size was determined>",
    "supporting_quote": "<exact verbatim quote stating the sample size>",
    "has_power_calculation": true/false,
    "has_confidence_intervals": true/false
}}"""


def extract_study_type_llm(
    document_id: int,
    llm_client: Any,
    model: str,
    document: Optional[Dict[str, Any]] = None,
    hierarchy_config: Optional[Dict[str, float]] = None,
) -> DimensionScore:
    """
    Extract study type using LLM with semantic search context.

    This is the LLM-first approach that uses semantic search to find
    relevant passages about study design, then applies LLM analysis.

    Args:
        document_id: Database ID of the document
        llm_client: Ollama client instance
        model: LLM model name to use
        document: Optional document dict (used for fallback if no chunks)
        hierarchy_config: Optional dict mapping study types to scores

    Returns:
        DimensionScore for study design with audit trail
    """
    if hierarchy_config is None:
        hierarchy_config = DEFAULT_STUDY_TYPE_HIERARCHY

    # Search for relevant chunks about study design using semantic search
    # Uses dynamic threshold reduction to find results if initial threshold too strict
    chunks = search_chunks_by_query(
        document_id=document_id,
        query="study design methodology methods randomized controlled trial cohort retrospective prospective systematic review meta-analysis we conducted this study",
        max_chunks=DEFAULT_MAX_CHUNKS,
        similarity_threshold=DEFAULT_SIMILARITY_THRESHOLD,
        min_threshold=MIN_SIMILARITY_THRESHOLD,
        threshold_decrement=THRESHOLD_DECREMENT,
    )

    # Fall back to positional chunks if semantic search returns nothing
    if not chunks:
        logger.info(f"No semantic search results for document {document_id}, falling back to positional chunks")
        chunks = get_all_document_chunks(document_id, limit=5)

    # If still no chunks, try using abstract only (full_text should already be chunked)
    # Synthetic chunks are ONLY allowed for abstract-only documents
    if not chunks and document:
        full_text = document.get('full_text') or ''
        abstract = document.get('abstract') or ''

        # If document has full_text, it should have been chunked - don't use synthetic
        if full_text and full_text.strip():
            logger.warning(
                f"Document {document_id} has full_text but no chunks found. "
                "Full text documents should be chunked before assessment."
            )
            # Don't create synthetic chunks for full_text - assessment should fail upstream
        elif abstract and abstract.strip():
            # Abstract-only documents can use synthetic chunks
            chunk_size = 2000
            synthetic_chunks = []
            for i in range(0, min(len(abstract), 10000), chunk_size):
                chunk_text = abstract[i:i + chunk_size]
                if chunk_text.strip():
                    synthetic_chunks.append({'chunk_text': chunk_text})
            chunks = synthetic_chunks
            logger.info(f"Using {len(chunks)} synthetic chunks from abstract for study type extraction")

    # If still no text available, return unknown
    if not chunks:
        dimension_score = DimensionScore(
            dimension_name=DIMENSION_STUDY_DESIGN,
            score=5.0  # Neutral score
        )
        dimension_score.add_detail(
            component='study_type',
            value='unknown',
            contribution=5.0,
            reasoning='No document text available for LLM extraction'
        )
        return dimension_score

    # Extract passage texts
    passages = [c.get('chunk_text', '') for c in chunks if c.get('chunk_text')]

    # Always prepend the abstract if available - it typically contains the clearest
    # study design statement (e.g., "randomized crossover study")
    if document:
        abstract = document.get('abstract') or ''
        if abstract and abstract.strip():
            # Check if abstract is already in passages (avoid duplication)
            abstract_already_present = any(abstract[:100] in p for p in passages if p)
            if not abstract_already_present:
                passages.insert(0, f"ABSTRACT:\n{abstract}")
                logger.debug(f"Prepended abstract to passages for study type extraction")

    # Build and execute LLM prompt
    prompt = _build_study_type_extraction_prompt(passages)

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

            study_type = parsed.get('study_type', 'unknown')
            confidence = parsed.get('confidence', 0.5)
            reasoning = parsed.get('reasoning', '')
            supporting_quote = parsed.get('supporting_quote', '')

            # Get score from hierarchy
            score = hierarchy_config.get(study_type, 5.0)

            # Create dimension score with audit trail
            dimension_score = DimensionScore(
                dimension_name=DIMENSION_STUDY_DESIGN,
                score=score
            )

            dimension_score.add_detail(
                component='study_type',
                value=study_type,
                contribution=score,
                evidence=supporting_quote,
                reasoning=f"LLM extraction (confidence: {confidence:.2f}): {reasoning}"
            )

            # Add extraction method detail
            dimension_score.add_detail(
                component='extraction_method',
                value='llm_semantic_search',
                contribution=0.0,
                reasoning=f"Used semantic search with {len(chunks)} chunks"
            )

            logger.info(
                f"LLM study type extraction: {study_type} (score={score:.1f}, "
                f"confidence={confidence:.2f})"
            )

            return dimension_score

        else:
            logger.warning(f"Could not parse LLM response: {response_text[:200]}")

    except Exception as e:
        logger.error(f"Error in LLM study type extraction: {e}")

    # Fallback on error
    dimension_score = DimensionScore(
        dimension_name=DIMENSION_STUDY_DESIGN,
        score=5.0
    )
    dimension_score.add_detail(
        component='study_type',
        value='unknown',
        contribution=5.0,
        reasoning='LLM extraction failed, assigned neutral score'
    )
    return dimension_score


def extract_sample_size_llm(
    document_id: int,
    llm_client: Any,
    model: str,
    document: Optional[Dict[str, Any]] = None,
    scoring_config: Optional[Dict[str, float]] = None,
) -> DimensionScore:
    """
    Extract sample size using LLM with semantic search context.

    This is the LLM-first approach that uses semantic search to find
    relevant passages about sample size, then applies LLM analysis.

    Args:
        document_id: Database ID of the document
        llm_client: Ollama client instance
        model: LLM model name to use
        document: Optional document dict (used for fallback if no chunks)
        scoring_config: Optional scoring configuration

    Returns:
        DimensionScore for sample size with audit trail
    """
    if scoring_config is None:
        scoring_config = {
            'log_multiplier': 2.0,
            'power_calculation_bonus': 2.0,
            'ci_reported_bonus': 0.5
        }

    log_multiplier = scoring_config.get('log_multiplier', 2.0)
    power_bonus = scoring_config.get('power_calculation_bonus', 2.0)
    ci_bonus = scoring_config.get('ci_reported_bonus', 0.5)

    # Search for relevant chunks about sample size using semantic search
    # Uses dynamic threshold reduction to find results if initial threshold too strict
    chunks = search_chunks_by_query(
        document_id=document_id,
        query="sample size participants subjects patients enrolled recruited n= N= total number methods population study design",
        max_chunks=DEFAULT_MAX_CHUNKS,
        similarity_threshold=DEFAULT_SIMILARITY_THRESHOLD,
        min_threshold=MIN_SIMILARITY_THRESHOLD,
        threshold_decrement=THRESHOLD_DECREMENT,
    )

    # Fall back to positional chunks if semantic search returns nothing
    if not chunks:
        logger.info(f"No semantic search results for document {document_id}, falling back to positional chunks")
        chunks = get_all_document_chunks(document_id, limit=5)

    # If still no chunks, try using abstract only (full_text should already be chunked)
    # Synthetic chunks are ONLY allowed for abstract-only documents
    if not chunks and document:
        full_text = document.get('full_text') or ''
        abstract = document.get('abstract') or ''

        # If document has full_text, it should have been chunked - don't use synthetic
        if full_text and full_text.strip():
            logger.warning(
                f"Document {document_id} has full_text but no chunks found. "
                "Full text documents should be chunked before assessment."
            )
            # Don't create synthetic chunks for full_text - assessment should fail upstream
        elif abstract and abstract.strip():
            # Abstract-only documents can use synthetic chunks
            chunk_size = 2000
            synthetic_chunks = []
            for i in range(0, min(len(abstract), 10000), chunk_size):
                chunk_text = abstract[i:i + chunk_size]
                if chunk_text.strip():
                    synthetic_chunks.append({'chunk_text': chunk_text})
            chunks = synthetic_chunks
            logger.info(f"Using {len(chunks)} synthetic chunks from abstract for sample size extraction")

    # If still no text available, return zero score
    if not chunks:
        dimension_score = DimensionScore(
            dimension_name=DIMENSION_SAMPLE_SIZE,
            score=0.0
        )
        dimension_score.add_detail(
            component='extracted_n',
            value='not_found',
            contribution=0.0,
            reasoning='No document text available for LLM extraction'
        )
        return dimension_score

    # Extract passage texts
    passages = [c.get('chunk_text', '') for c in chunks if c.get('chunk_text')]

    # Always prepend the abstract if available - it often states sample size
    # (e.g., "Ten participants with type 2 diabetes were recruited")
    if document:
        abstract = document.get('abstract') or ''
        if abstract and abstract.strip():
            # Check if abstract is already in passages (avoid duplication)
            abstract_already_present = any(abstract[:100] in p for p in passages if p)
            if not abstract_already_present:
                passages.insert(0, f"ABSTRACT:\n{abstract}")
                logger.debug(f"Prepended abstract to passages for sample size extraction")

    # Build and execute LLM prompt
    prompt = _build_sample_size_extraction_prompt(passages)

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

            sample_size = parsed.get('sample_size')
            confidence = parsed.get('confidence', 0.5)
            reasoning = parsed.get('reasoning', '')
            supporting_quote = parsed.get('supporting_quote', '')
            has_power_calc = parsed.get('has_power_calculation', False)
            has_ci = parsed.get('has_confidence_intervals', False)

            if sample_size is None or sample_size <= 0:
                # No sample size found
                dimension_score = DimensionScore(
                    dimension_name=DIMENSION_SAMPLE_SIZE,
                    score=0.0
                )
                dimension_score.add_detail(
                    component='extracted_n',
                    value='not_found',
                    contribution=0.0,
                    reasoning=f"LLM could not determine sample size: {reasoning}"
                )
                return dimension_score

            # Calculate base score
            base_score = calculate_sample_size_score(sample_size, log_multiplier)

            # Create dimension score
            dimension_score = DimensionScore(
                dimension_name=DIMENSION_SAMPLE_SIZE,
                score=base_score
            )

            # Add base score detail
            dimension_score.add_detail(
                component='extracted_n',
                value=str(sample_size),
                contribution=base_score,
                evidence=supporting_quote,
                reasoning=f"LLM extraction (confidence: {confidence:.2f}): {reasoning}"
            )

            # Add extraction method detail
            dimension_score.add_detail(
                component='extraction_method',
                value='llm_semantic_search',
                contribution=0.0,
                reasoning=f"Used semantic search with {len(chunks)} chunks"
            )

            # Add bonuses for power calculation
            if has_power_calc:
                new_score = min(10.0, dimension_score.score + power_bonus)
                dimension_score.score = new_score
                dimension_score.add_detail(
                    component='power_calculation',
                    value='yes',
                    contribution=power_bonus,
                    reasoning=f'Power calculation detected by LLM, bonus +{power_bonus}'
                )

            # Add bonus for confidence intervals
            if has_ci:
                new_score = min(10.0, dimension_score.score + ci_bonus)
                dimension_score.score = new_score
                dimension_score.add_detail(
                    component='ci_reporting',
                    value='yes',
                    contribution=ci_bonus,
                    reasoning=f'Confidence intervals detected by LLM, bonus +{ci_bonus}'
                )

            logger.info(
                f"LLM sample size extraction: n={sample_size} (score={dimension_score.score:.2f}, "
                f"confidence={confidence:.2f})"
            )

            return dimension_score

        else:
            logger.warning(f"Could not parse LLM response: {response_text[:200]}")

    except Exception as e:
        logger.error(f"Error in LLM sample size extraction: {e}")

    # Fallback on error
    dimension_score = DimensionScore(
        dimension_name=DIMENSION_SAMPLE_SIZE,
        score=0.0
    )
    dimension_score.add_detail(
        component='extracted_n',
        value='not_found',
        contribution=0.0,
        reasoning='LLM extraction failed'
    )
    return dimension_score


def ensure_document_embeddings(
    document_id: int,
    document: Optional[Dict[str, Any]] = None,
    progress_callback: Optional[Any] = None,
) -> bool:
    """
    Ensure document has embeddings created for its full_text.

    If embeddings don't exist but full_text does, creates them.

    Args:
        document_id: Database ID of the document
        document: Optional document dict (to avoid extra DB query)
        progress_callback: Optional callback(stage, current, total) for progress

    Returns:
        True if embeddings exist or were created, False otherwise
    """
    from ...database import get_db_manager
    from ...embeddings.chunk_embedder import ChunkEmbedder

    db_manager = get_db_manager()

    try:
        # Check if chunks already exist
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM semantic.chunks WHERE document_id = %s",
                    (document_id,)
                )
                chunk_count = cur.fetchone()[0]

        if chunk_count > 0:
            logger.debug(f"Document {document_id} already has {chunk_count} chunks")
            return True

        # Check if document has full_text
        if document is None:
            with db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT full_text FROM public.document WHERE id = %s",
                        (document_id,)
                    )
                    result = cur.fetchone()
                    full_text = result[0] if result else None
        else:
            full_text = document.get('full_text')

        if not full_text or not full_text.strip():
            logger.debug(f"Document {document_id} has no full_text for embedding")
            return False

        # Create embeddings
        logger.info(f"Creating embeddings for document {document_id} ({len(full_text)} chars)")

        if progress_callback:
            progress_callback("embedding", 0, 1)

        embedder = ChunkEmbedder()

        def embed_progress(current: int, total: int) -> None:
            """Forward progress to main callback."""
            if progress_callback:
                progress_callback("embedding", current, total)

        num_chunks = embedder.chunk_and_embed(
            document_id=document_id,
            progress_callback=embed_progress,
        )

        if progress_callback:
            progress_callback("embedding", 1, 1)

        logger.info(f"Created {num_chunks} embeddings for document {document_id}")
        return num_chunks > 0

    except Exception as e:
        logger.error(f"Error ensuring embeddings for document {document_id}: {e}")
        return False


__all__ = [
    'extract_study_type_llm',
    'extract_sample_size_llm',
    'ensure_document_embeddings',
]
