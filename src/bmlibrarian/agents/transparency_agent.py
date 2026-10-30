"""
Transparency Assessment Agent for Detecting Undisclosed Bias Risk

This agent evaluates biomedical research publications for transparency and
disclosure completeness, detecting potential undisclosed bias risk. It assesses:

- Funding disclosure: presence, quality, and industry involvement
- Conflict of interest: declaration quality and specific conflicts
- Data availability: openness and sharing policies
- Author contributions: CRediT or equivalent attribution
- Trial registration: registry IDs and compliance

The agent works fully offline using local LLMs (Ollama) to analyze full-text
articles stored in the database. It can optionally enrich assessments with
structured metadata from bulk imports (PubMed grants, ClinicalTrials.gov
sponsors, Retraction Watch retraction data).

Usage:
    from bmlibrarian.agents import TransparencyAgent, TransparencyAssessment

    agent = TransparencyAgent()
    try:
        assessment = agent.assess_transparency(document)
    except TransparencyAssessmentError as e:
        print(f"Not assessed: {e}")
    else:
        print(agent.format_assessment_summary(assessment))

    # Batch processing: failures are collected, not raised
    result = agent.assess_batch(documents, progress_callback=my_callback)
    print(f"{len(result.failures)} of {len(documents)} failed")
"""

import csv
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from .base import BaseAgent
from .transparency_data import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MIN_CONFIDENCE,
    MAX_TEXT_LENGTH,
    MAX_TOTAL_SCORE,
    MAX_UNIT_VALUE,
    MIN_TRANSPARENCY_SCORE,
    MIN_UNIT_VALUE,
    PATTERN_INDUSTRY_MIN_CONFIDENCE,
    SPONSOR_INDUSTRY_MIN_CONFIDENCE,
    SUMMARY_SEPARATOR_WIDTH,
    SCORE_THRESHOLD_HIGH_RISK,
    SCORE_THRESHOLD_MEDIUM_RISK,
    DataAvailability,
    RiskLevel,
    TransparencyAssessment,
    TransparencyAssessmentError,
    TransparencyBatchResult,
    coerce_bounded_float,
    coerce_data_availability,
    coerce_optional_bool,
    coerce_str_list,
    extract_trial_registry_ids,
    filter_trial_registry_ids,
    is_likely_industry_funder,
    parse_finite_float,
    score_distribution_label,
)

logger = logging.getLogger(__name__)

# Fields the LLM response must contain for an assessment to be usable
REQUIRED_ASSESSMENT_FIELDS = (
    "has_funding_disclosure",
    "has_coi_disclosure",
    "data_availability",
    "transparency_score",
    "overall_confidence",
)

# Numeric LLM fields: name -> (minimum, maximum, required).
# A missing, non-numeric or out-of-range required value fails the assessment
# (out of range usually means the model answered on the wrong scale, e.g.
# 0-100, and clamping would turn that into the most favourable score).
# Optional fields become None ("not assessed") when missing or invalid, with a
# warning when invalid; out-of-range values are clamped with a warning.
NUMERIC_ASSESSMENT_FIELDS = {
    "transparency_score": (MIN_TRANSPARENCY_SCORE, MAX_TOTAL_SCORE, True),
    "overall_confidence": (MIN_UNIT_VALUE, MAX_UNIT_VALUE, True),
    "industry_funding_confidence": (MIN_UNIT_VALUE, MAX_UNIT_VALUE, False),
    "funding_disclosure_quality": (MIN_UNIT_VALUE, MAX_UNIT_VALUE, False),
    "coi_disclosure_quality": (MIN_UNIT_VALUE, MAX_UNIT_VALUE, False),
}

# Required boolean LLM fields: an unrecognisable value fails the assessment
REQUIRED_BOOL_ASSESSMENT_FIELDS = (
    "has_funding_disclosure",
    "has_coi_disclosure",
)

# Optional boolean LLM fields: name -> value used if missing/unrecognisable
# (None for is_industry_funded means "LLM could not tell")
OPTIONAL_BOOL_ASSESSMENT_FIELDS = {
    "is_industry_funded": None,
    "has_author_contributions": False,
}

# List-of-string LLM fields
LIST_ASSESSMENT_FIELDS = (
    "funding_sources",
    "conflicts_identified",
    "trial_registry_ids",
    "risk_indicators",
    "strengths",
    "weaknesses",
)


def _percent(value: Optional[float]) -> str:
    """Format a 0-1 value as a percentage, or 'not assessed' for None.

    Args:
        value: The value, or None if it was not assessed.

    Returns:
        E.g. ``"80%"`` or ``"not assessed"``.
    """
    return "not assessed" if value is None else f"{value:.0%}"


class TransparencyAgent(BaseAgent):
    """Agent for assessing transparency and undisclosed bias risk in biomedical research.

    This agent uses large language models to evaluate research publications and
    provide structured assessments of funding disclosure, conflict of interest
    declarations, data availability policies, and overall transparency.

    The agent operates fully offline, analyzing document text through a local
    Ollama model. It can be enriched with bulk-imported metadata from PubMed,
    ClinicalTrials.gov, and Retraction Watch for more comprehensive assessments.
    """

    VERSION = "1.0.0"

    def __init__(
        self,
        model: str = "gpt-oss:20b",
        host: str = "http://localhost:11434",
        temperature: float = 0.1,
        top_p: float = 0.9,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        callback: Optional[Callable[[str, str], None]] = None,
        orchestrator: Optional[Any] = None,
        show_model_info: bool = True,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ):
        """Initialize the TransparencyAgent.

        Args:
            model: The name of the Ollama model to use.
            host: The Ollama server host URL.
            temperature: Model temperature for assessment (low for consistency).
            top_p: Model top-p sampling parameter.
            max_tokens: Maximum tokens for response.
            callback: Optional callback function for progress updates.
            orchestrator: Optional orchestrator for queue-based processing.
            show_model_info: Whether to display model information on initialization.
            max_retries: Maximum number of retry attempts for failed assessments.
        """
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
        self.max_retries = max_retries

        self._assessment_stats: Dict[str, int] = {
            "total_assessments": 0,
            "successful_assessments": 0,
            "failed_assessments": 0,
            "low_confidence_assessments": 0,
            "parse_failures": 0,
        }

    def get_agent_type(self) -> str:
        """Get the agent type identifier."""
        return "transparency_agent"

    def assess_transparency(
        self,
        document: Dict[str, Any],
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    ) -> TransparencyAssessment:
        """Assess the transparency and disclosure completeness of a research publication.

        Analyzes the document text (preferring full_text over abstract) to evaluate
        funding disclosure, COI declarations, data availability, and other transparency
        indicators. Uses a local LLM for text analysis and pattern matching for
        trial registry ID extraction. Every call counts as an attempt in
        ``get_assessment_stats()``.

        Args:
            document: Document dictionary with 'abstract' (required) and optional 'full_text'.
            min_confidence: Confidence (0-1) below which the assessment is flagged
                as low-confidence (``low_confidence=True``, logged and counted;
                it is still returned).

        Returns:
            The TransparencyAssessment.

        Raises:
            TransparencyAssessmentError: The document could not be assessed
                (LLM provider unreachable or model missing, no text,
                unparseable or invalid LLM response, request failure); the
                message gives the reason. Any other exception (e.g. an LLM provider timeout) is logged
                with its traceback and re-raised as this error.
        """
        self._assessment_stats["total_assessments"] += 1
        try:
            assessment = self._assess_document(document, min_confidence)
        except Exception as e:
            self._assessment_stats["failed_assessments"] += 1
            expected = isinstance(e, TransparencyAssessmentError)
            logger.error(
                f"Transparency assessment failed for document "
                f"{document.get('id', 'unknown')}: {e}",
                exc_info=not expected,
            )
            if expected:
                raise
            raise TransparencyAssessmentError(f"{type(e).__name__}: {e}") from e
        self._assessment_stats["successful_assessments"] += 1
        return assessment

    def _assess_document(
        self,
        document: Dict[str, Any],
        min_confidence: float,
    ) -> TransparencyAssessment:
        """Run one assessment (the body of :meth:`assess_transparency`).

        Args:
            document: Document dictionary.
            min_confidence: Low-confidence threshold (0-1).

        Returns:
            The TransparencyAssessment.

        Raises:
            TransparencyAssessmentError: The document could not be assessed.
        """
        if not self.test_connection():
            raise TransparencyAssessmentError(
                f"LLM provider unreachable or model {self.model} not available "
                f"- transparency assessment unavailable"
            )

        doc_id = document.get("id", "unknown")
        title = document.get("title", "Untitled")
        abstract = document.get("abstract", "")
        full_text = document.get("full_text", "")

        text_to_analyze = full_text if full_text else abstract

        if not text_to_analyze:
            raise TransparencyAssessmentError(f"No text found for document {doc_id}")

        if len(text_to_analyze) > MAX_TEXT_LENGTH:
            text_to_analyze = text_to_analyze[:MAX_TEXT_LENGTH] + "..."
            logger.debug(f"Truncated text for document {doc_id} to {MAX_TEXT_LENGTH} characters")

        self._call_callback(
            "transparency_assessment_started",
            f"Assessing transparency for document {doc_id}",
        )

        # Pre-extract trial registry IDs using pattern matching (no LLM needed)
        pre_extracted_registry_ids = extract_trial_registry_ids(text_to_analyze)

        # Build and send prompt
        prompt = self._build_prompt(title, text_to_analyze, pre_extracted_registry_ids)

        try:
            assessment_data = self._generate_and_parse_json(
                prompt,
                max_retries=self.max_retries,
                retry_context=f"transparency assessment (doc {doc_id})",
                num_predict=self.max_tokens,
            )
        except json.JSONDecodeError as e:
            self._assessment_stats["parse_failures"] += 1
            raise TransparencyAssessmentError(
                f"Could not parse JSON from LLM after {self.max_retries + 1} "
                f"attempts for document {doc_id}: {e}"
            ) from e
        except (ConnectionError, ValueError) as e:
            raise TransparencyAssessmentError(
                f"Ollama request failed for document {doc_id}: {e}"
            ) from e

        # Validate and normalize the untrusted LLM output
        assessment_data = self._validate_assessment_data(assessment_data, doc_id)

        overall_confidence = assessment_data["overall_confidence"]
        low_confidence = overall_confidence < min_confidence

        if low_confidence:
            logger.info(
                f"Transparency assessment confidence {overall_confidence:.2f} below "
                f"threshold {min_confidence:.2f} for document {doc_id}"
            )
            self._assessment_stats["low_confidence_assessments"] += 1

        # Merge LLM-found registry IDs (already format-checked) with
        # pattern-extracted ones
        llm_registry_ids = assessment_data["trial_registry_ids"]
        all_registry_ids = list(set(pre_extracted_registry_ids + llm_registry_ids))

        # Check funding sources for industry involvement
        funding_sources = assessment_data["funding_sources"]
        llm_industry_flag = assessment_data["is_industry_funded"]
        pattern_industry_flag = any(is_likely_industry_funder(s) for s in funding_sources)

        # Use pattern matching result if LLM didn't identify, or combine
        if llm_industry_flag is None:
            is_industry = pattern_industry_flag
        else:
            is_industry = llm_industry_flag or pattern_industry_flag

        industry_confidence = assessment_data["industry_funding_confidence"]
        if pattern_industry_flag:
            industry_confidence = max(industry_confidence or 0.0, PATTERN_INDUSTRY_MIN_CONFIDENCE)

        # Build assessment object
        assessment = TransparencyAssessment(
            document_id=str(doc_id),
            document_title=title,
            pmid=document.get("pmid"),
            doi=document.get("doi"),
            has_funding_disclosure=assessment_data["has_funding_disclosure"],
            funding_statement=assessment_data.get("funding_statement"),
            funding_sources=funding_sources,
            is_industry_funded=is_industry,
            industry_funding_confidence=industry_confidence,
            funding_disclosure_quality=assessment_data["funding_disclosure_quality"],
            has_coi_disclosure=assessment_data["has_coi_disclosure"],
            coi_statement=assessment_data.get("coi_statement"),
            conflicts_identified=assessment_data["conflicts_identified"],
            coi_disclosure_quality=assessment_data["coi_disclosure_quality"],
            data_availability=assessment_data["data_availability"],
            data_availability_statement=assessment_data.get("data_availability_statement"),
            has_author_contributions=assessment_data["has_author_contributions"],
            contributions_statement=assessment_data.get("contributions_statement"),
            has_trial_registration=bool(len(all_registry_ids) > 0),
            trial_registry_ids=all_registry_ids,
            transparency_score=assessment_data["transparency_score"],
            overall_confidence=overall_confidence,
            low_confidence=low_confidence,
            risk_indicators=assessment_data["risk_indicators"],
            strengths=assessment_data["strengths"],
            weaknesses=assessment_data["weaknesses"],
            model_used=self.model,
            agent_version=self.VERSION,
        )

        # Classify risk based on score
        assessment.risk_level = assessment.classify_risk()

        self._call_callback(
            "transparency_assessment_completed",
            f"Assessed transparency for document {doc_id}",
        )

        logger.info(
            f"Successfully assessed transparency for {doc_id} "
            f"(score: {assessment.transparency_score:.1f}/10, "
            f"risk: {assessment.risk_level}, "
            f"confidence: {overall_confidence:.2f})"
        )

        return assessment

    def _validate_assessment_data(
        self,
        data: Any,
        doc_id: Any,
    ) -> Dict[str, Any]:
        """Validate and normalize a parsed LLM transparency response.

        Fails the assessment (raises) when the response is not an object, a required field is missing, a required
        numeric field is not a number (numeric strings are accepted) or is out
        of range, or a required boolean is unrecognisable.

        Otherwise repairs are applied and logged as warnings: optional numeric
        fields that are invalid become ``None`` (not assessed) and out-of-range
        ones are clamped; optional booleans that are unrecognisable fall back
        to their defaults; an unknown ``data_availability`` becomes
        ``not_stated``; list fields of the wrong type become empty lists and
        LLM trial registry IDs that match no known registry format are
        dropped. Silent normalizations: missing optional fields take their
        defaults (debug log), single strings become one-element lists, list
        items are stringified and stripped, and blank or ``None`` items are
        dropped.

        Args:
            data: Parsed JSON from the LLM (not trusted to be a dict).
            doc_id: Document ID for log messages.

        Returns:
            A normalized copy of ``data``.

        Raises:
            TransparencyAssessmentError: ``data`` is unusable; the message
                says why.
        """
        if not isinstance(data, dict):
            raise TransparencyAssessmentError(
                f"Transparency response for document {doc_id} is "
                f"{type(data).__name__}, expected a JSON object"
            )

        missing = [f for f in REQUIRED_ASSESSMENT_FIELDS if f not in data]
        if missing:
            raise TransparencyAssessmentError(
                f"Missing required fields {missing} in assessment response for document {doc_id}"
            )

        normalized = dict(data)

        for name, (minimum, maximum, required) in NUMERIC_ASSESSMENT_FIELDS.items():
            raw = data.get(name)
            number = parse_finite_float(raw)
            if number is None:
                if required:
                    raise TransparencyAssessmentError(
                        f"Invalid value {raw!r} for required field '{name}' "
                        f"in assessment response for document {doc_id}"
                    )
                if raw is None:
                    logger.debug(f"'{name}' missing (document {doc_id}); not assessed")
                else:
                    logger.warning(
                        f"Invalid value {raw!r} for '{name}' (document {doc_id}); "
                        f"not assessed"
                    )
                normalized[name] = None
                continue
            if not minimum <= number <= maximum:
                if required:
                    raise TransparencyAssessmentError(
                        f"Out-of-range value {raw!r} for required field '{name}' "
                        f"(expected {minimum:g}-{maximum:g}) in assessment response "
                        f"for document {doc_id}"
                    )
                logger.warning(
                    f"Out-of-range value {raw!r} for '{name}' (document {doc_id}); "
                    f"clamping to {minimum:g}-{maximum:g}"
                )
            normalized[name] = coerce_bounded_float(number, minimum, maximum)

        for name in REQUIRED_BOOL_ASSESSMENT_FIELDS:
            value = coerce_optional_bool(data.get(name))
            if value is None:
                raise TransparencyAssessmentError(
                    f"Invalid value {data.get(name)!r} for required boolean field "
                    f"'{name}' in assessment response for document {doc_id}"
                )
            normalized[name] = value

        for name, default in OPTIONAL_BOOL_ASSESSMENT_FIELDS.items():
            raw = data.get(name)
            value = coerce_optional_bool(raw)
            if value is None:
                if raw is not None:
                    logger.warning(
                        f"Invalid value {raw!r} for '{name}' (document {doc_id}); "
                        f"using {default}"
                    )
                value = default
            normalized[name] = value

        raw_availability = data.get("data_availability")
        availability = coerce_data_availability(raw_availability)
        if availability is None:
            availability = DataAvailability.NOT_STATED.value
            logger.warning(
                f"Unknown data_availability {raw_availability!r} (document {doc_id}); "
                f"using '{availability}'"
            )
        normalized["data_availability"] = availability

        for name in LIST_ASSESSMENT_FIELDS:
            items, ok = coerce_str_list(data.get(name))
            if not ok:
                logger.warning(
                    f"Unexpected type {type(data.get(name)).__name__} for '{name}' "
                    f"(document {doc_id}); using an empty list"
                )
            normalized[name] = items

        registry_ids, rejected = filter_trial_registry_ids(normalized["trial_registry_ids"])
        if rejected:
            logger.warning(
                f"Dropping trial registry IDs with no recognised registry format "
                f"{rejected} (document {doc_id})"
            )
        normalized["trial_registry_ids"] = registry_ids

        return normalized

    def assess_transparency_by_id(
        self,
        document_id: int,
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    ) -> TransparencyAssessment:
        """Assess transparency by fetching document from the database.

        Convenience method that fetches the document by ID and calls
        assess_transparency().

        Args:
            document_id: The database ID of the document to assess.
            min_confidence: Confidence (0-1) below which the assessment is flagged
                as low-confidence (logged and counted; it is still returned).

        Returns:
            The TransparencyAssessment.

        Raises:
            ValueError: If document ID is not found in database.
            TransparencyAssessmentError: The document could not be assessed.
        """
        from bmlibrarian.database import fetch_documents_by_ids

        logger.debug(f"Fetching document {document_id} from database")

        try:
            documents = fetch_documents_by_ids({document_id})
        except Exception as e:
            logger.error(f"Failed to fetch document {document_id} from database: {e}")
            raise ValueError(f"Could not fetch document {document_id} from database") from e

        if not documents:
            logger.error(f"Document {document_id} not found in database")
            raise ValueError(f"Document {document_id} not found in database")

        document = documents[0]
        return self.assess_transparency(document, min_confidence=min_confidence)

    def assess_batch(
        self,
        documents: List[Dict[str, Any]],
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> TransparencyBatchResult:
        """Assess transparency for multiple documents.

        A failure for one document never aborts the batch: it is recorded in
        the result's ``failures`` with its reason.

        Args:
            documents: List of document dictionaries.
            min_confidence: Confidence (0-1) below which assessments are flagged
                as low-confidence (logged and counted; they are still returned).
            progress_callback: Optional callback(current, total, doc_title) for progress.

        Returns:
            The successful assessments and the ``(document_id, reason)`` failures.
        """
        result = TransparencyBatchResult()
        total = len(documents)

        logger.info(f"Starting batch transparency assessment for {total} documents")

        for i, document in enumerate(documents):
            doc_title = document.get("title", "Unknown Document")

            if progress_callback:
                progress_callback(i + 1, total, doc_title)

            doc_id = str(document.get("id", "unknown"))
            try:
                assessment = self.assess_transparency(
                    document=document,
                    min_confidence=min_confidence,
                )
            except TransparencyAssessmentError as e:
                result.failures.append((doc_id, str(e)))
                continue

            result.assessments.append(assessment)
            logger.debug(f"Assessed transparency for document {doc_id}")

        logger.info(
            f"Batch transparency assessment completed: "
            f"{len(result.assessments)} successful, {len(result.failures)} failed "
            f"out of {total} documents"
        )

        return result

    def enrich_with_metadata(
        self,
        assessment: TransparencyAssessment,
    ) -> TransparencyAssessment:
        """Enrich a transparency assessment with bulk-imported metadata.

        Queries the transparency.document_metadata table for additional
        information about the document (grants, retraction status, trial
        sponsor classification) and merges it into the assessment.

        A document with no metadata row is left unchanged. A database error
        raises: an unenriched assessment would claim "not retracted" without
        having checked, and saving it would overwrite a stored retraction.

        Args:
            assessment: The assessment to enrich.

        Returns:
            The enriched assessment (modified in-place and returned).

        Raises:
            TransparencyAssessmentError: The metadata lookup failed.
        """
        from bmlibrarian.database import get_db_manager

        try:
            doc_id = int(assessment.document_id)
        except (ValueError, TypeError):
            logger.debug(f"Cannot enrich assessment - non-numeric document_id: {assessment.document_id}")
            return assessment

        try:
            with get_db_manager().get_connection() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT is_retracted, retraction_reason, trial_sponsor_class,
                           clinical_trial_id, grants, publication_types
                    FROM transparency.document_metadata
                    WHERE document_id = %s
                    """,
                    (doc_id,),
                )
                row = cur.fetchone()

            if row:
                is_retracted, retraction_reason, sponsor_class, trial_id, grants, pub_types = row

                if is_retracted is not None:
                    assessment.is_retracted = is_retracted
                if retraction_reason:
                    assessment.retraction_reason = retraction_reason
                if sponsor_class:
                    assessment.trial_sponsor_class = sponsor_class
                    if sponsor_class.lower() == "industry" and not assessment.is_industry_funded:
                        assessment.is_industry_funded = True
                        assessment.industry_funding_confidence = max(
                            assessment.industry_funding_confidence or 0.0, SPONSOR_INDUSTRY_MIN_CONFIDENCE
                        )
                if trial_id and not assessment.has_trial_registration:
                    assessment.has_trial_registration = True
                    if trial_id not in assessment.trial_registry_ids:
                        assessment.trial_registry_ids.append(trial_id)

                # Add retraction as risk indicator
                if is_retracted and "Paper has been retracted" not in assessment.risk_indicators:
                    assessment.risk_indicators.append("Paper has been retracted")
                    assessment.risk_level = RiskLevel.HIGH.value

                logger.debug(f"Enriched assessment for document {doc_id} with bulk metadata")

        except Exception as e:
            logger.error(
                f"Could not enrich transparency assessment for document {doc_id} "
                f"with bulk metadata: {e}"
            )
            raise TransparencyAssessmentError(
                f"Metadata lookup failed for document {doc_id} "
                f"(retraction/sponsor status unknown): {e}"
            ) from e

        return assessment

    def _build_prompt(
        self,
        title: str,
        text: str,
        pre_extracted_registry_ids: List[str],
    ) -> str:
        """Build the LLM prompt for transparency assessment.

        Args:
            title: Document title.
            text: Document text to analyze.
            pre_extracted_registry_ids: Registry IDs already found by pattern matching.

        Returns:
            Formatted prompt string.
        """
        registry_context = ""
        if pre_extracted_registry_ids:
            registry_context = (
                f"\nNote: The following trial registry IDs were detected in the text: "
                f"{', '.join(pre_extracted_registry_ids)}\n"
            )

        return f"""You are an expert in research transparency, open science, and publication ethics.

Evaluate the transparency and completeness of disclosures in the research paper below.

Paper Title: {title}
{registry_context}
Paper Text:
{text}

INSTRUCTIONS:

Analyze the paper text for the following transparency indicators. Extract ONLY information
that is ACTUALLY PRESENT in the text. Do NOT invent, assume, or fabricate information.

1. **Funding Disclosure** (funding_disclosure_quality: 0.0-1.0):
   - 1.0: Complete disclosure with specific funding bodies AND grant numbers
   - 0.7: Specific funding bodies named but no grant numbers
   - 0.5: General/vague funding mention (e.g., "supported by industry")
   - 0.3: Only mentions "no funding" or "self-funded"
   - 0.0: No funding disclosure found anywhere in the text

2. **Industry Funding Detection**:
   - Identify if ANY funding source is a pharmaceutical company, biotech firm,
     medical device company, CRO, or other commercial entity
   - Look for corporate indicators: Inc., Corp., Ltd., pharma, biotech, therapeutics
   - Rate confidence (0.0-1.0) in the industry funding determination

3. **Conflict of Interest Disclosure** (coi_disclosure_quality: 0.0-1.0):
   - 1.0: Detailed per-author COI statement with specific relationships
   - 0.8: Explicit "no conflicts of interest" declaration
   - 0.6: General COI statement mentioning some relationships
   - 0.3: Vague or incomplete COI disclosure
   - 0.0: No COI disclosure found anywhere in the text

4. **Data Availability**:
   - "open": Data in public repositories (Zenodo, Figshare, GEO, Dryad, GitHub, etc.)
   - "on_request": Available upon reasonable request to the authors
   - "restricted": IRB, ethics, confidentiality restrictions
   - "not_available": Explicitly stated as not available or proprietary
   - "not_stated": No data availability statement found

5. **Author Contributions**:
   - Check for CRediT (Contributor Roles Taxonomy) or similar attribution

6. **Trial Registration**:
   - Check if any clinical trial registry IDs are mentioned

7. **Overall Transparency Score** (0-10 scale):
   - Funding: 0-3 points (0=absent, 1=vague, 2=named sources, 3=complete with grants)
   - COI: 0-3 points (0=absent, 1=generic, 2=explicit "none"/specific, 3=detailed per-author)
   - Data availability: 0-2 points (0=absent, 1=restricted/on request, 2=open)
   - Trial registration: 0-1 point (if applicable to this study type)
   - Author contributions: 0-1 point

8. **Risk Indicators**: List specific concerns (e.g., "Industry funded with no COI disclosure",
   "Missing data availability statement", "No funding disclosure for clinical trial")

9. **Strengths & Weaknesses**: List transparency strengths and weaknesses

Response format (JSON only):
{{
    "has_funding_disclosure": true,
    "funding_statement": "extracted funding text or null",
    "funding_sources": ["Funder 1", "Funder 2"],
    "is_industry_funded": false,
    "industry_funding_confidence": 0.9,
    "funding_disclosure_quality": 0.8,
    "has_coi_disclosure": true,
    "coi_statement": "extracted COI text or null",
    "conflicts_identified": ["Author X: consulting for Company Y"],
    "coi_disclosure_quality": 0.7,
    "data_availability": "open",
    "data_availability_statement": "extracted statement or null",
    "has_author_contributions": true,
    "contributions_statement": "extracted contributions text or null",
    "has_trial_registration": true,
    "trial_registry_ids": ["NCT12345678"],
    "transparency_score": 7.5,
    "overall_confidence": 0.85,
    "risk_indicators": ["specific concern 1"],
    "strengths": ["strength 1", "strength 2"],
    "weaknesses": ["weakness 1"]
}}

Respond ONLY with valid JSON. Do not include any explanatory text outside the JSON."""

    def get_assessment_stats(self) -> Dict[str, Any]:
        """Get transparency assessment statistics.

        Returns:
            Dictionary with assessment statistics including success rate.
        """
        total = self._assessment_stats["total_assessments"]
        if total == 0:
            return {**self._assessment_stats, "success_rate": 0.0}

        return {
            **self._assessment_stats,
            "success_rate": self._assessment_stats["successful_assessments"] / total,
        }

    def format_assessment_summary(self, assessment: TransparencyAssessment) -> str:
        """Format a transparency assessment as a human-readable summary.

        Args:
            assessment: TransparencyAssessment object.

        Returns:
            Formatted string summary.
        """
        sep = "=" * SUMMARY_SEPARATOR_WIDTH
        lines = [
            f"\n{sep}",
            f"TRANSPARENCY ASSESSMENT: {assessment.document_title}",
            f"{sep}",
            f"Document ID: {assessment.document_id}",
        ]

        if assessment.pmid:
            lines.append(f"PMID: {assessment.pmid}")
        if assessment.doi:
            lines.append(f"DOI: {assessment.doi}")

        # Overall scores
        risk_emoji = {
            RiskLevel.LOW.value: "[LOW RISK]",
            RiskLevel.MEDIUM.value: "[MEDIUM RISK]",
            RiskLevel.HIGH.value: "[HIGH RISK]",
            RiskLevel.UNKNOWN.value: "[UNKNOWN]",
        }
        lines.extend([
            f"\n--- OVERALL ---",
            f"Transparency Score: {assessment.transparency_score:.1f}/10",
            f"Risk Level: {risk_emoji.get(assessment.risk_level, assessment.risk_level)}",
            f"Confidence: {assessment.overall_confidence:.0%}"
            + (" (LOW CONFIDENCE)" if assessment.low_confidence else ""),
        ])

        if assessment.is_retracted:
            lines.append(f"*** RETRACTED *** Reason: {assessment.retraction_reason or 'Unknown'}")

        # Funding
        lines.append(f"\n--- FUNDING DISCLOSURE ---")
        if assessment.has_funding_disclosure:
            lines.append(f"Status: Disclosed (quality: {_percent(assessment.funding_disclosure_quality)})")
            if assessment.funding_sources:
                lines.append(f"Sources: {', '.join(assessment.funding_sources)}")
            if assessment.is_industry_funded:
                lines.append(
                    f"Industry Funded: Yes (confidence: {_percent(assessment.industry_funding_confidence)})"
                )
            if assessment.trial_sponsor_class:
                lines.append(f"Trial Sponsor Class: {assessment.trial_sponsor_class}")
        else:
            lines.append("Status: NOT DISCLOSED")

        # COI
        lines.append(f"\n--- CONFLICT OF INTEREST ---")
        if assessment.has_coi_disclosure:
            lines.append(f"Status: Disclosed (quality: {_percent(assessment.coi_disclosure_quality)})")
            if assessment.conflicts_identified:
                for conflict in assessment.conflicts_identified:
                    lines.append(f"  - {conflict}")
        else:
            lines.append("Status: NOT DISCLOSED")

        # Data availability
        lines.append(f"\n--- DATA AVAILABILITY ---")
        lines.append(f"Status: {assessment.data_availability.replace('_', ' ').title()}")
        if assessment.data_availability_statement:
            stmt = assessment.data_availability_statement[:200]
            lines.append(f"Statement: {stmt}")

        # Trial registration
        if assessment.trial_registry_ids:
            lines.append(f"\n--- TRIAL REGISTRATION ---")
            lines.append(f"Registry IDs: {', '.join(assessment.trial_registry_ids)}")

        # Author contributions
        lines.append(f"\n--- AUTHOR CONTRIBUTIONS ---")
        lines.append(f"Status: {'Disclosed' if assessment.has_author_contributions else 'NOT DISCLOSED'}")

        # Risk indicators
        if assessment.risk_indicators:
            lines.append(f"\n--- RISK INDICATORS ---")
            for indicator in assessment.risk_indicators:
                lines.append(f"  ! {indicator}")

        # Strengths
        if assessment.strengths:
            lines.append(f"\n--- STRENGTHS ---")
            for i, strength in enumerate(assessment.strengths, 1):
                lines.append(f"{i}. {strength}")

        # Weaknesses
        if assessment.weaknesses:
            lines.append(f"\n--- WEAKNESSES ---")
            for i, weakness in enumerate(assessment.weaknesses, 1):
                lines.append(f"{i}. {weakness}")

        lines.append(f"{sep}\n")

        return "\n".join(lines)

    def export_to_json(
        self,
        assessments: List[TransparencyAssessment],
        output_file: str,
        failures: Optional[List[Tuple[str, str]]] = None,
    ) -> None:
        """Export transparency assessments to JSON file.

        Args:
            assessments: List of TransparencyAssessment objects.
            output_file: Path to output JSON file.
            failures: ``(document_id, reason)`` for documents that were not
                assessed, so the file does not pass for the complete set.
        """
        data = {
            "assessments": [a.to_dict() for a in assessments],
            "metadata": {
                "total_assessments": len(assessments),
                "failures": [
                    {"document_id": doc_id, "reason": reason}
                    for doc_id, reason in failures or []
                ],
                "assessment_date": datetime.now(timezone.utc).isoformat(),
                "agent_model": self.model,
                "agent_version": self.VERSION,
                "statistics": self.get_assessment_stats(),
            },
        }

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Exported {len(assessments)} transparency assessments to {output_file}")

    def export_to_csv(
        self,
        assessments: List[TransparencyAssessment],
        output_file: str,
    ) -> None:
        """Export transparency assessments to CSV file for analysis tools.

        Args:
            assessments: List of TransparencyAssessment objects.
            output_file: Path to output CSV file.
        """
        fieldnames = [
            "document_id", "document_title", "pmid", "doi",
            "transparency_score", "risk_level", "overall_confidence",
            "has_funding_disclosure", "funding_disclosure_quality",
            "is_industry_funded", "industry_funding_confidence",
            "has_coi_disclosure", "coi_disclosure_quality",
            "data_availability", "has_author_contributions",
            "has_trial_registration", "is_retracted",
            "trial_sponsor_class",
            "funding_sources", "conflicts_identified",
            "trial_registry_ids", "risk_indicators",
            "strengths", "weaknesses",
            "created_at",
        ]

        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for assessment in assessments:
                row = assessment.to_dict()
                # Convert lists to semicolon-separated strings for CSV
                for list_field in (
                    "funding_sources", "conflicts_identified", "trial_registry_ids",
                    "risk_indicators", "strengths", "weaknesses",
                ):
                    if list_field in row and isinstance(row[list_field], list):
                        row[list_field] = "; ".join(str(x) for x in row[list_field])
                row = {k: v for k, v in row.items() if k in fieldnames}
                writer.writerow(row)

        logger.info(f"Exported {len(assessments)} transparency assessments to {output_file}")

    def get_risk_distribution(
        self,
        assessments: List[TransparencyAssessment],
    ) -> Dict[str, int]:
        """Get distribution of risk levels across assessments.

        Args:
            assessments: List of TransparencyAssessment objects.

        Returns:
            Dictionary with risk levels and counts.
        """
        distribution = {
            "low": 0,
            "medium": 0,
            "high": 0,
            "unknown": 0,
        }

        for assessment in assessments:
            level = assessment.risk_level
            if level in distribution:
                distribution[level] += 1
            else:
                distribution["unknown"] += 1

        return distribution

    def get_score_distribution(
        self,
        assessments: List[TransparencyAssessment],
    ) -> Dict[str, int]:
        """Get distribution of transparency scores across assessments.

        Args:
            assessments: List of TransparencyAssessment objects.

        Returns:
            Dictionary with score categories and counts.
        """
        # Buckets use the same thresholds as classify_risk() on the score
        # (high transparency = low risk). Ranges are half-open: 3.0 is
        # moderate, 6.0 is high. Metadata enrichment can raise a document's
        # risk level (e.g. retraction) without moving it between buckets.
        high = f"{SCORE_THRESHOLD_MEDIUM_RISK:g}-{MAX_TOTAL_SCORE:g}"
        moderate = f"{SCORE_THRESHOLD_HIGH_RISK:g}-<{SCORE_THRESHOLD_MEDIUM_RISK:g}"
        low = f"{MIN_TRANSPARENCY_SCORE:g}-<{SCORE_THRESHOLD_HIGH_RISK:g}"
        labels = {
            "high_transparency": f"high_transparency ({high})",
            "moderate_transparency": f"moderate_transparency ({moderate})",
            "low_transparency": f"low_transparency ({low})",
        }
        distribution = {label: 0 for label in labels.values()}

        for assessment in assessments:
            bucket = score_distribution_label(assessment.transparency_score)
            distribution[labels[bucket]] += 1

        return distribution
