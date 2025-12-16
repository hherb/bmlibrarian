"""
Tier 2: Fast study design classification using Claude Haiku.

Provides accurate classification at minimal cost (~$0.00025/document)
for documents without high-confidence PubMed publication type metadata.

This classifier focuses on determining what study design THIS paper used,
ignoring any other studies mentioned in the abstract. This distinction is
critical because documents often reference other study types in their
literature review sections.
"""

import json
import logging
import time
import warnings
from typing import Optional, Callable

from ..agents.base import LiteBaseAgent
from ..data_models import LiteDocument
from ..config import LiteConfig
from ..constants import (
    QUALITY_CLASSIFIER_MODEL,
    QUALITY_LLM_TEMPERATURE,
    QUALITY_CLASSIFIER_MAX_TOKENS,
    QUALITY_API_DELAY_SECONDS,
    JSON_MAX_RESPONSE_SIZE_BYTES,
    VALID_BLINDING_VALUES,
    CONFIDENCE_PARSE_FAILURE_DEFAULT,
    ABSTRACT_MAX_SINGLE_PASS_LENGTH,
    ABSTRACT_CHUNK_SIZE,
    ABSTRACT_CHUNK_OVERLAP,
    CLASSIFICATION_MAX_RETRIES,
    CLASSIFICATION_RETRY_BASE_DELAY,
    CLASSIFICATION_RETRY_BACKOFF_MULTIPLIER,
)
from .data_models import StudyDesign, StudyClassification

logger = logging.getLogger(__name__)


class ClassificationParseWarning(UserWarning):
    """Warning issued when classification parsing falls back to defaults.

    This warning alerts users that the LLM response could not be fully parsed
    and default values are being used. In medical/scientific contexts, it's
    critical to acknowledge uncertainty rather than hide it.
    """
    pass


# System prompt for study classification - emphasizes classifying THIS study
CLASSIFICATION_SYSTEM_PROMPT = """You are a biomedical research classifier.
Your task is to classify the study design of research papers.

CRITICAL RULES:
1. Classify what THIS paper reports, NOT studies it references
2. Look for phrases like "we conducted", "this study", "our trial", "we analyzed"
3. Ignore phrases like "previous studies", "Smith et al. reported", "unlike RCTs"
4. If uncertain, return "other" with low confidence
5. Return ONLY valid JSON, no explanation"""


# Mapping from LLM response strings to StudyDesign enum
STUDY_DESIGN_MAPPING: dict[str, StudyDesign] = {
    "systematic_review": StudyDesign.SYSTEMATIC_REVIEW,
    "systematic review": StudyDesign.SYSTEMATIC_REVIEW,
    "meta_analysis": StudyDesign.META_ANALYSIS,
    "meta-analysis": StudyDesign.META_ANALYSIS,
    "metaanalysis": StudyDesign.META_ANALYSIS,
    "rct": StudyDesign.RCT,
    "randomized_controlled_trial": StudyDesign.RCT,
    "randomized controlled trial": StudyDesign.RCT,
    "randomised_controlled_trial": StudyDesign.RCT,
    "clinical_trial": StudyDesign.RCT,
    "clinical trial": StudyDesign.RCT,
    "cohort_prospective": StudyDesign.COHORT_PROSPECTIVE,
    "prospective_cohort": StudyDesign.COHORT_PROSPECTIVE,
    "prospective cohort": StudyDesign.COHORT_PROSPECTIVE,
    "cohort_retrospective": StudyDesign.COHORT_RETROSPECTIVE,
    "retrospective_cohort": StudyDesign.COHORT_RETROSPECTIVE,
    "retrospective cohort": StudyDesign.COHORT_RETROSPECTIVE,
    "retrospective": StudyDesign.COHORT_RETROSPECTIVE,
    "case_control": StudyDesign.CASE_CONTROL,
    "case-control": StudyDesign.CASE_CONTROL,
    "cross_sectional": StudyDesign.CROSS_SECTIONAL,
    "cross-sectional": StudyDesign.CROSS_SECTIONAL,
    "crosssectional": StudyDesign.CROSS_SECTIONAL,
    "case_series": StudyDesign.CASE_SERIES,
    "case series": StudyDesign.CASE_SERIES,
    "case_report": StudyDesign.CASE_REPORT,
    "case report": StudyDesign.CASE_REPORT,
    "editorial": StudyDesign.EDITORIAL,
    "letter": StudyDesign.LETTER,
    "comment": StudyDesign.COMMENT,
    "commentary": StudyDesign.COMMENT,
    "guideline": StudyDesign.GUIDELINE,
    "practice_guideline": StudyDesign.GUIDELINE,
    "practice guideline": StudyDesign.GUIDELINE,
    "other": StudyDesign.OTHER,
    "unknown": StudyDesign.UNKNOWN,
}


class LiteStudyClassifier(LiteBaseAgent):
    """
    Fast study design classification using Claude Haiku.

    This classifier provides accurate study design classification at minimal
    cost. It specifically focuses on classifying what study design THIS paper
    used, ignoring any other studies mentioned in the abstract.

    Attributes:
        model: The LLM model to use for classification
    """

    def __init__(
        self,
        config: Optional[LiteConfig] = None,
        model: Optional[str] = None,
    ) -> None:
        """
        Initialize the study classifier.

        Args:
            config: BMLibrarian Lite configuration
            model: Optional model override (default: from constants)
        """
        super().__init__(config)
        self.model = model or QUALITY_CLASSIFIER_MODEL

    def classify(self, document: LiteDocument) -> StudyClassification:
        """
        Classify study design for a document.

        For long abstracts (> ABSTRACT_MAX_SINGLE_PASS_LENGTH), this method
        uses a chunking strategy to process the full abstract without
        information loss.

        Args:
            document: The document to classify

        Returns:
            StudyClassification with design and confidence
        """
        abstract = document.abstract or ""
        title = document.title or "Untitled"
        doc_id = getattr(document, "id", None) or getattr(document, "pmid", "unknown")

        # Validate input encoding - ensure safe ASCII/UTF-8
        try:
            abstract.encode("utf-8")
            title.encode("utf-8")
        except UnicodeEncodeError as e:
            logger.warning(
                f"Document {doc_id}: Invalid encoding in text, attempting cleanup: {e}"
            )
            # Remove problematic characters but preserve content
            abstract = abstract.encode("utf-8", errors="replace").decode("utf-8")
            title = title.encode("utf-8", errors="replace").decode("utf-8")

        # Check if abstract needs chunked processing
        if len(abstract) > ABSTRACT_MAX_SINGLE_PASS_LENGTH:
            return self._classify_long_abstract(document, abstract, title, doc_id)

        return self._classify_single_pass(document, abstract, title, doc_id)

    def _classify_single_pass(
        self,
        document: LiteDocument,
        abstract: str,
        title: str,
        doc_id: str | int,
    ) -> StudyClassification:
        """
        Classify document with a single LLM call.

        Args:
            document: The document to classify
            abstract: Document abstract
            title: Document title
            doc_id: Document identifier for error reporting

        Returns:
            StudyClassification with design and confidence
        """
        prompt = f"""Classify THIS paper's study design:

Title: {title}
Abstract: {abstract}

Return JSON:
{{
    "study_design": "systematic_review|meta_analysis|rct|cohort_prospective|cohort_retrospective|case_control|cross_sectional|case_series|case_report|editorial|letter|guideline|other",
    "is_randomized": true|false|null,
    "is_blinded": "none"|"single"|"double"|"triple"|null,
    "sample_size": <number or null>,
    "confidence": <0.0 to 1.0>
}}

IMPORTANT: Classify what THIS study did, not studies it references."""

        try:
            messages = [
                self._create_system_message(CLASSIFICATION_SYSTEM_PROMPT),
                self._create_user_message(prompt),
            ]
            response = self._chat(
                messages=messages,
                temperature=QUALITY_LLM_TEMPERATURE,
                max_tokens=QUALITY_CLASSIFIER_MAX_TOKENS,
                json_mode=True,
            )
            return self._parse_response(response, doc_id)

        except Exception as e:
            logger.error(
                f"Classification failed for document {doc_id} "
                f"(title: '{title[:50]}...'): {e}"
            )
            return StudyClassification(
                study_design=StudyDesign.UNKNOWN,
                confidence=0.0,
                raw_response=str(e),
            )

    def _classify_long_abstract(
        self,
        document: LiteDocument,
        abstract: str,
        title: str,
        doc_id: str | int,
    ) -> StudyClassification:
        """
        Classify document with a long abstract using chunked processing.

        This implements a map-reduce strategy:
        1. Process abstract in overlapping chunks
        2. Collect design indicators from each chunk
        3. Aggregate results with confidence weighting

        Args:
            document: The document to classify
            abstract: Full document abstract (not truncated)
            title: Document title
            doc_id: Document identifier for error reporting

        Returns:
            StudyClassification with aggregated results
        """
        logger.info(
            f"Document {doc_id}: Abstract length {len(abstract)} exceeds "
            f"single-pass limit ({ABSTRACT_MAX_SINGLE_PASS_LENGTH}), "
            "using chunked processing"
        )

        # Create overlapping chunks
        chunks = self._create_abstract_chunks(abstract)
        chunk_results: list[StudyClassification] = []

        for i, chunk in enumerate(chunks):
            prompt = f"""Classify THIS paper's study design based on this section of the abstract.

Title: {title}
Abstract Section {i + 1}/{len(chunks)}: {chunk}

Return JSON:
{{
    "study_design": "systematic_review|meta_analysis|rct|cohort_prospective|cohort_retrospective|case_control|cross_sectional|case_series|case_report|editorial|letter|guideline|other",
    "is_randomized": true|false|null,
    "is_blinded": "none"|"single"|"double"|"triple"|null,
    "sample_size": <number or null>,
    "confidence": <0.0 to 1.0>
}}

IMPORTANT: Classify what THIS study did, not studies it references.
Note: This is part {i + 1} of {len(chunks)} sections from a long abstract."""

            try:
                messages = [
                    self._create_system_message(CLASSIFICATION_SYSTEM_PROMPT),
                    self._create_user_message(prompt),
                ]
                response = self._chat(
                    messages=messages,
                    temperature=QUALITY_LLM_TEMPERATURE,
                    max_tokens=QUALITY_CLASSIFIER_MAX_TOKENS,
                    json_mode=True,
                )
                result = self._parse_response(response, doc_id)
                chunk_results.append(result)
            except Exception as e:
                logger.warning(
                    f"Document {doc_id}: Failed to classify chunk {i + 1}: {e}"
                )
                continue

        if not chunk_results:
            logger.error(f"Document {doc_id}: All chunk classifications failed")
            return StudyClassification(
                study_design=StudyDesign.UNKNOWN,
                confidence=0.0,
                raw_response="All chunk classifications failed",
            )

        # Aggregate results using confidence-weighted voting
        return self._aggregate_chunk_results(chunk_results, doc_id)

    def _create_abstract_chunks(self, abstract: str) -> list[str]:
        """
        Split abstract into overlapping chunks for processing.

        Args:
            abstract: Full abstract text

        Returns:
            List of overlapping text chunks
        """
        chunks = []
        start = 0
        while start < len(abstract):
            end = start + ABSTRACT_CHUNK_SIZE
            chunk = abstract[start:end]
            chunks.append(chunk)

            # Move start position, accounting for overlap
            start = end - ABSTRACT_CHUNK_OVERLAP
            if start >= len(abstract):
                break

        return chunks

    def _aggregate_chunk_results(
        self,
        results: list[StudyClassification],
        doc_id: str | int,
    ) -> StudyClassification:
        """
        Aggregate classification results from multiple chunks.

        Uses confidence-weighted voting to determine final classification.

        Args:
            results: List of classifications from each chunk
            doc_id: Document identifier for logging

        Returns:
            Aggregated StudyClassification
        """
        from collections import Counter

        # Confidence-weighted vote for study design
        design_weights: dict[StudyDesign, float] = {}
        for result in results:
            design = result.study_design
            weight = result.confidence
            design_weights[design] = design_weights.get(design, 0) + weight

        # Select design with highest weighted vote
        best_design = max(design_weights, key=design_weights.get)  # type: ignore

        # Aggregate other fields from highest-confidence result for that design
        best_result = max(
            (r for r in results if r.study_design == best_design),
            key=lambda r: r.confidence
        )

        # Calculate aggregate confidence (weighted average)
        total_weight = sum(design_weights.values())
        aggregate_confidence = design_weights[best_design] / total_weight if total_weight > 0 else 0.0

        # Collect sample sizes (take maximum as most likely accurate)
        sample_sizes = [r.sample_size for r in results if r.sample_size is not None]
        final_sample_size = max(sample_sizes) if sample_sizes else None

        logger.debug(
            f"Document {doc_id}: Aggregated {len(results)} chunks, "
            f"design={best_design.value}, confidence={aggregate_confidence:.2f}"
        )

        return StudyClassification(
            study_design=best_design,
            is_randomized=best_result.is_randomized,
            is_blinded=best_result.is_blinded,
            sample_size=final_sample_size,
            confidence=aggregate_confidence,
            raw_response=f"Aggregated from {len(results)} chunks",
        )

    def _parse_response(
        self, response: str, doc_id: str | int = "unknown"
    ) -> StudyClassification:
        """
        Parse LLM response into StudyClassification.

        Args:
            response: Raw LLM response string
            doc_id: Document identifier for error reporting

        Returns:
            Parsed StudyClassification
        """
        try:
            # Security: Validate response size before parsing
            if len(response.encode("utf-8")) > JSON_MAX_RESPONSE_SIZE_BYTES:
                logger.error(
                    f"Document {doc_id}: Response size "
                    f"({len(response.encode('utf-8'))} bytes) exceeds "
                    f"maximum ({JSON_MAX_RESPONSE_SIZE_BYTES} bytes)"
                )
                warnings.warn(
                    f"Document {doc_id}: LLM response too large, classification failed",
                    ClassificationParseWarning,
                    stacklevel=2,
                )
                return StudyClassification(
                    study_design=StudyDesign.UNKNOWN,
                    confidence=0.0,
                    raw_response="Response size exceeded maximum allowed",
                )

            # Clean response (remove markdown code blocks if present)
            cleaned = self._clean_json_response(response)

            # Security: Additional validation after cleaning
            if not cleaned or not cleaned.strip():
                logger.warning(f"Document {doc_id}: Empty response after cleaning")
                return StudyClassification(
                    study_design=StudyDesign.UNKNOWN,
                    confidence=0.0,
                    raw_response=response,
                )

            data = json.loads(cleaned)

            # Validate data is a dictionary
            if not isinstance(data, dict):
                logger.warning(
                    f"Document {doc_id}: Response is not a JSON object: {type(data)}"
                )
                return StudyClassification(
                    study_design=StudyDesign.UNKNOWN,
                    confidence=0.0,
                    raw_response=response,
                )

            # Parse study design
            design_str = data.get("study_design", "unknown").lower().strip()
            study_design = self._parse_study_design(design_str)

            # Parse blinding - validate against known values
            is_blinded = self._parse_blinding(data.get("is_blinded"), doc_id)

            # Parse sample size - convert to int safely
            sample_size = self._parse_sample_size(data.get("sample_size"), doc_id)

            # Parse confidence - ensure valid range, with proper fallback handling
            confidence = self._parse_confidence(data.get("confidence"), doc_id)

            return StudyClassification(
                study_design=study_design,
                is_randomized=data.get("is_randomized"),
                is_blinded=is_blinded,
                sample_size=sample_size,
                confidence=confidence,
                raw_response=response,
            )

        except json.JSONDecodeError as e:
            logger.warning(f"Document {doc_id}: Failed to parse JSON response: {e}")
            return StudyClassification(
                study_design=StudyDesign.UNKNOWN,
                confidence=0.0,
                raw_response=response,
            )

    def _clean_json_response(self, response: str) -> str:
        """
        Clean LLM response by removing markdown code blocks.

        Args:
            response: Raw response string

        Returns:
            Cleaned JSON string
        """
        cleaned = response.strip()
        if cleaned.startswith("```"):
            # Remove opening code block
            parts = cleaned.split("```")
            if len(parts) >= 2:
                cleaned = parts[1]
                # Remove language identifier if present
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
        cleaned = cleaned.strip()
        return cleaned

    def _parse_study_design(self, design_str: str) -> StudyDesign:
        """
        Parse study design string to enum.

        Args:
            design_str: Study design as lowercase string

        Returns:
            StudyDesign enum value
        """
        return STUDY_DESIGN_MAPPING.get(design_str, StudyDesign.UNKNOWN)

    def _parse_blinding(
        self, value: Optional[str], doc_id: str | int = "unknown"
    ) -> Optional[str]:
        """
        Parse and validate blinding value.

        Args:
            value: Raw blinding value from response
            doc_id: Document identifier for error reporting

        Returns:
            Validated blinding string or None
        """
        if value is None:
            return None
        normalized = str(value).lower().strip()
        if normalized in VALID_BLINDING_VALUES:
            return normalized
        # Invalid value - log it but don't warn (expected for observational studies)
        logger.debug(
            f"Document {doc_id}: Invalid blinding value '{value}', "
            f"expected one of: {', '.join(sorted(VALID_BLINDING_VALUES))}"
        )
        return None

    def _parse_sample_size(
        self, value: Optional[int | str], doc_id: str | int = "unknown"
    ) -> Optional[int]:
        """
        Parse sample size to integer.

        Args:
            value: Raw sample size value
            doc_id: Document identifier for error reporting

        Returns:
            Integer sample size or None
        """
        if value is None:
            return None
        try:
            result = int(value)
            if result < 0:
                logger.warning(
                    f"Document {doc_id}: Negative sample size {result}, treating as None"
                )
                return None
            return result
        except (ValueError, TypeError) as e:
            logger.debug(
                f"Document {doc_id}: Could not parse sample size '{value}': {e}"
            )
            return None

    def _parse_confidence(
        self, value: Optional[float | str], doc_id: str | int = "unknown"
    ) -> float:
        """
        Parse and clamp confidence value.

        In medical/scientific contexts, we must acknowledge uncertainty rather
        than hide it behind default values. When parsing fails, this method:
        1. Logs the failure with document context
        2. Issues a user-visible warning
        3. Returns a LOW confidence value (not arbitrary middle-ground)

        Args:
            value: Raw confidence value (can be None, float, or string)
            doc_id: Document identifier for error reporting

        Returns:
            Confidence clamped to 0.0-1.0 range, or CONFIDENCE_PARSE_FAILURE_DEFAULT
            if parsing fails
        """
        if value is None:
            # Missing confidence is distinct from parse failure
            logger.debug(
                f"Document {doc_id}: No confidence value provided, "
                f"using default {CONFIDENCE_PARSE_FAILURE_DEFAULT}"
            )
            return CONFIDENCE_PARSE_FAILURE_DEFAULT

        try:
            conf = float(value)
            return max(0.0, min(1.0, conf))
        except (ValueError, TypeError) as e:
            # IMPORTANT: Log and warn - don't silently return arbitrary values
            logger.warning(
                f"Document {doc_id}: Failed to parse confidence value '{value}': {e}. "
                f"Using fallback value {CONFIDENCE_PARSE_FAILURE_DEFAULT} to indicate "
                "uncertainty."
            )
            warnings.warn(
                f"Document {doc_id}: Could not parse LLM confidence value. "
                "Classification confidence set to 0.0 to indicate uncertainty. "
                "Review the raw response for details.",
                ClassificationParseWarning,
                stacklevel=3,
            )
            return CONFIDENCE_PARSE_FAILURE_DEFAULT

    def classify_batch(
        self,
        documents: list[LiteDocument],
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> list[StudyClassification]:
        """
        Classify multiple documents with rate limiting and retry logic.

        This method processes documents sequentially with:
        - Rate limiting between API calls (QUALITY_API_DELAY_SECONDS)
        - Retry logic for transient failures (CLASSIFICATION_MAX_RETRIES)
        - Exponential backoff between retries

        Args:
            documents: List of documents to classify
            progress_callback: Optional callback(current, total)

        Returns:
            List of classifications in same order as input
        """
        results = []
        total = len(documents)

        for i, doc in enumerate(documents):
            doc_id = getattr(doc, "id", None) or getattr(doc, "pmid", f"doc_{i}")

            # Retry logic with exponential backoff
            result = self._classify_with_retry(doc, doc_id)
            results.append(result)

            if progress_callback:
                progress_callback(i + 1, total)

            # Rate limiting: delay between API calls (except after last document)
            if i < total - 1 and QUALITY_API_DELAY_SECONDS > 0:
                time.sleep(QUALITY_API_DELAY_SECONDS)

        return results

    def _classify_with_retry(
        self,
        document: LiteDocument,
        doc_id: str | int,
    ) -> StudyClassification:
        """
        Classify document with retry logic for transient failures.

        Args:
            document: Document to classify
            doc_id: Document identifier for logging

        Returns:
            StudyClassification result
        """
        last_error: Optional[Exception] = None
        delay = CLASSIFICATION_RETRY_BASE_DELAY

        for attempt in range(CLASSIFICATION_MAX_RETRIES):
            try:
                result = self.classify(document)

                # If classification succeeded (even with UNKNOWN), return it
                # We only retry on actual exceptions, not low-confidence results
                return result

            except Exception as e:
                last_error = e
                if attempt < CLASSIFICATION_MAX_RETRIES - 1:
                    logger.warning(
                        f"Document {doc_id}: Classification attempt {attempt + 1} "
                        f"failed: {e}. Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                    delay *= CLASSIFICATION_RETRY_BACKOFF_MULTIPLIER
                else:
                    logger.error(
                        f"Document {doc_id}: All {CLASSIFICATION_MAX_RETRIES} "
                        f"classification attempts failed. Last error: {e}"
                    )

        # All retries exhausted - return unknown classification
        return StudyClassification(
            study_design=StudyDesign.UNKNOWN,
            confidence=0.0,
            raw_response=f"All retries failed: {last_error}",
        )

    def _get_model(self) -> str:
        """
        Override to use classifier-specific model.

        Returns:
            Model string with provider prefix
        """
        provider = self.config.llm.provider
        return f"{provider}:{self.model}"
