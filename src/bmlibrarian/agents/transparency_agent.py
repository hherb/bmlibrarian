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
    assessment = agent.assess_transparency(document)
    if assessment:
        print(agent.format_assessment_summary(assessment))

    # Batch processing
    assessments = agent.assess_batch(documents, progress_callback=my_callback)
"""

import csv
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from .base import BaseAgent
from .transparency_data import (
    DEFAULT_CONFIDENCE_FALLBACK,
    DEFAULT_MAX_RETRIES,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MIN_CONFIDENCE,
    MAX_TEXT_LENGTH,
    SUMMARY_SEPARATOR_WIDTH,
    SCORE_THRESHOLD_HIGH_RISK,
    SCORE_THRESHOLD_MEDIUM_RISK,
    DataAvailability,
    RiskLevel,
    TransparencyAssessment,
    extract_trial_registry_ids,
    is_likely_industry_funder,
)

logger = logging.getLogger(__name__)


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
    ) -> Optional[TransparencyAssessment]:
        """Assess the transparency and disclosure completeness of a research publication.

        Analyzes the document text (preferring full_text over abstract) to evaluate
        funding disclosure, COI declarations, data availability, and other transparency
        indicators. Uses a local LLM for text analysis and pattern matching for
        trial registry ID extraction.

        Args:
            document: Document dictionary with 'abstract' (required) and optional 'full_text'.
            min_confidence: Minimum confidence threshold to accept assessment (0-1).

        Returns:
            TransparencyAssessment object if successful, None on failure.
        """
        if not self.test_connection():
            logger.error("Cannot connect to Ollama - transparency assessment unavailable")
            return None

        doc_id = document.get("id", "unknown")
        title = document.get("title", "Untitled")
        abstract = document.get("abstract", "")
        full_text = document.get("full_text", "")

        text_to_analyze = full_text if full_text else abstract

        if not text_to_analyze:
            logger.warning(f"No text found for document {doc_id}")
            return None

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
            logger.error(
                f"Could not parse JSON from LLM after {self.max_retries + 1} "
                f"attempts for document {doc_id}: {e}"
            )
            self._assessment_stats["parse_failures"] += 1
            return None
        except (ConnectionError, ValueError) as e:
            logger.error(f"Ollama request failed for document {doc_id}: {e}")
            self._assessment_stats["failed_assessments"] += 1
            return None

        # Validate required fields
        required_fields = [
            "has_funding_disclosure",
            "has_coi_disclosure",
            "data_availability",
            "transparency_score",
            "overall_confidence",
        ]
        if not all(f in assessment_data for f in required_fields):
            missing = [f for f in required_fields if f not in assessment_data]
            logger.error(
                f"Missing required fields {missing} in assessment response for document {doc_id}"
            )
            self._assessment_stats["failed_assessments"] += 1
            return None

        # Parse confidence
        overall_confidence = float(
            assessment_data.get("overall_confidence", DEFAULT_CONFIDENCE_FALLBACK)
        )

        if overall_confidence < min_confidence:
            logger.info(
                f"Transparency assessment confidence {overall_confidence:.2f} below "
                f"threshold {min_confidence:.2f} for document {doc_id}"
            )
            self._assessment_stats["low_confidence_assessments"] += 1

        # Merge LLM-found registry IDs with pattern-extracted ones
        llm_registry_ids = assessment_data.get("trial_registry_ids", [])
        all_registry_ids = list(set(pre_extracted_registry_ids + llm_registry_ids))

        # Check funding sources for industry involvement
        funding_sources = assessment_data.get("funding_sources", [])
        llm_industry_flag = assessment_data.get("is_industry_funded")
        pattern_industry_flag = any(is_likely_industry_funder(s) for s in funding_sources)

        # Use pattern matching result if LLM didn't identify, or combine
        if llm_industry_flag is None:
            is_industry = pattern_industry_flag
        else:
            is_industry = llm_industry_flag or pattern_industry_flag

        industry_confidence = float(assessment_data.get("industry_funding_confidence", 0.0))
        if pattern_industry_flag and industry_confidence < 0.8:
            industry_confidence = max(industry_confidence, 0.8)

        # Build assessment object
        assessment = TransparencyAssessment(
            document_id=str(doc_id),
            document_title=title,
            pmid=document.get("pmid"),
            doi=document.get("doi"),
            has_funding_disclosure=bool(assessment_data.get("has_funding_disclosure", False)),
            funding_statement=assessment_data.get("funding_statement"),
            funding_sources=funding_sources,
            is_industry_funded=is_industry,
            industry_funding_confidence=industry_confidence,
            funding_disclosure_quality=float(
                assessment_data.get("funding_disclosure_quality", 0.0)
            ),
            has_coi_disclosure=bool(assessment_data.get("has_coi_disclosure", False)),
            coi_statement=assessment_data.get("coi_statement"),
            conflicts_identified=assessment_data.get("conflicts_identified", []),
            coi_disclosure_quality=float(
                assessment_data.get("coi_disclosure_quality", 0.0)
            ),
            data_availability=assessment_data.get(
                "data_availability", DataAvailability.NOT_STATED.value
            ),
            data_availability_statement=assessment_data.get("data_availability_statement"),
            has_author_contributions=bool(
                assessment_data.get("has_author_contributions", False)
            ),
            contributions_statement=assessment_data.get("contributions_statement"),
            has_trial_registration=bool(len(all_registry_ids) > 0),
            trial_registry_ids=all_registry_ids,
            transparency_score=float(assessment_data.get("transparency_score", 0.0)),
            overall_confidence=overall_confidence,
            risk_indicators=assessment_data.get("risk_indicators", []),
            strengths=assessment_data.get("strengths", []),
            weaknesses=assessment_data.get("weaknesses", []),
            model_used=self.model,
            agent_version=self.VERSION,
        )

        # Classify risk based on score
        assessment.risk_level = assessment.classify_risk()

        # Update statistics
        self._assessment_stats["total_assessments"] += 1
        self._assessment_stats["successful_assessments"] += 1

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

    def assess_transparency_by_id(
        self,
        document_id: int,
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    ) -> Optional[TransparencyAssessment]:
        """Assess transparency by fetching document from the database.

        Convenience method that fetches the document by ID and calls
        assess_transparency().

        Args:
            document_id: The database ID of the document to assess.
            min_confidence: Minimum confidence threshold to accept assessment (0-1).

        Returns:
            TransparencyAssessment object if successful, None otherwise.

        Raises:
            ValueError: If document ID is not found in database.
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
    ) -> List[TransparencyAssessment]:
        """Assess transparency for multiple documents.

        Args:
            documents: List of document dictionaries.
            min_confidence: Minimum confidence threshold to accept assessments.
            progress_callback: Optional callback(current, total, doc_title) for progress.

        Returns:
            List of successful TransparencyAssessment objects.
        """
        assessments: List[TransparencyAssessment] = []
        total = len(documents)

        logger.info(f"Starting batch transparency assessment for {total} documents")

        for i, document in enumerate(documents):
            doc_title = document.get("title", "Unknown Document")

            if progress_callback:
                progress_callback(i + 1, total, doc_title)

            assessment = self.assess_transparency(
                document=document,
                min_confidence=min_confidence,
            )

            if assessment:
                assessments.append(assessment)
                logger.debug(f"Assessed transparency for document {document.get('id')}")

        logger.info(
            f"Batch transparency assessment completed: "
            f"{len(assessments)} successful out of {total} documents"
        )

        return assessments

    def enrich_with_metadata(
        self,
        assessment: TransparencyAssessment,
    ) -> TransparencyAssessment:
        """Enrich a transparency assessment with bulk-imported metadata.

        Queries the transparency.document_metadata table for additional
        information about the document (grants, retraction status, trial
        sponsor classification) and merges it into the assessment.

        Args:
            assessment: The assessment to enrich.

        Returns:
            The enriched assessment (modified in-place and returned).
        """
        from bmlibrarian.database import get_db_connection

        try:
            doc_id = int(assessment.document_id)
        except (ValueError, TypeError):
            logger.debug(f"Cannot enrich assessment - non-numeric document_id: {assessment.document_id}")
            return assessment

        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
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
                            assessment.industry_funding_confidence, 0.95
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
            logger.debug(f"Could not enrich assessment with metadata (table may not exist): {e}")

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
            f"Confidence: {assessment.overall_confidence:.0%}",
        ])

        if assessment.is_retracted:
            lines.append(f"*** RETRACTED *** Reason: {assessment.retraction_reason or 'Unknown'}")

        # Funding
        lines.append(f"\n--- FUNDING DISCLOSURE ---")
        if assessment.has_funding_disclosure:
            lines.append(f"Status: Disclosed (quality: {assessment.funding_disclosure_quality:.0%})")
            if assessment.funding_sources:
                lines.append(f"Sources: {', '.join(assessment.funding_sources)}")
            if assessment.is_industry_funded:
                lines.append(
                    f"Industry Funded: Yes (confidence: {assessment.industry_funding_confidence:.0%})"
                )
            if assessment.trial_sponsor_class:
                lines.append(f"Trial Sponsor Class: {assessment.trial_sponsor_class}")
        else:
            lines.append("Status: NOT DISCLOSED")

        # COI
        lines.append(f"\n--- CONFLICT OF INTEREST ---")
        if assessment.has_coi_disclosure:
            lines.append(f"Status: Disclosed (quality: {assessment.coi_disclosure_quality:.0%})")
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
    ) -> None:
        """Export transparency assessments to JSON file.

        Args:
            assessments: List of TransparencyAssessment objects.
            output_file: Path to output JSON file.
        """
        data = {
            "assessments": [a.to_dict() for a in assessments],
            "metadata": {
                "total_assessments": len(assessments),
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
        distribution = {
            "high_transparency (7-10)": 0,
            "moderate_transparency (4-6)": 0,
            "low_transparency (0-3)": 0,
        }

        for assessment in assessments:
            score = assessment.transparency_score
            if score >= SCORE_THRESHOLD_MEDIUM_RISK + 1:
                distribution["high_transparency (7-10)"] += 1
            elif score >= SCORE_THRESHOLD_HIGH_RISK:
                distribution["moderate_transparency (4-6)"] += 1
            else:
                distribution["low_transparency (0-3)"] += 1

        return distribution
