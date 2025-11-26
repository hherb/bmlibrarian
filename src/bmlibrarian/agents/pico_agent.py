"""
PICO Agent for Extracting Study Components from Biomedical Papers

The PICO framework is a standardized approach used in evidence-based medicine to
structure research questions and analyze clinical studies:

- Population (P): Who was studied? (demographics, condition, setting)
- Intervention (I): What was done to the study population? (treatment, test, exposure)
- Comparison (C): Who/what do we compare against? (control group, alternative treatment)
- Outcome (O): What was measured? (effects, results, endpoints)

This agent extracts PICO components from biomedical research paper abstracts and full texts,
enabling systematic review and meta-analysis workflows.
"""

import json
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

from .base import BaseAgent

logger = logging.getLogger(__name__)


@dataclass
class PICOExtraction:
    """Represents extracted PICO components from a study."""

    # Core PICO components
    population: str
    intervention: str
    comparison: str
    outcome: str

    # Metadata
    document_id: str
    document_title: str
    extraction_confidence: float  # 0-1 overall confidence in extraction quality

    # Optional fields
    study_type: Optional[str] = None  # e.g., "RCT", "cohort study", "case-control"
    sample_size: Optional[str] = None  # e.g., "N=150 patients"
    pmid: Optional[str] = None
    doi: Optional[str] = None

    # Detailed confidence scores for each component
    population_confidence: Optional[float] = None
    intervention_confidence: Optional[float] = None
    comparison_confidence: Optional[float] = None
    outcome_confidence: Optional[float] = None

    # Timestamp
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        if self.created_at:
            data['created_at'] = self.created_at.isoformat()
        return data


class PICOAgent(BaseAgent):
    """
    Agent for extracting PICO components from biomedical research papers.

    This agent uses large language models to identify and extract the Population,
    Intervention, Comparison, and Outcome elements from research study abstracts
    and full texts. This is essential for systematic reviews, meta-analyses, and
    evidence synthesis workflows.
    """

    VERSION = "1.0.0"  # Agent version for cache invalidation

    def __init__(self,
                 model: str = "gpt-oss:20b",
                 host: str = "http://localhost:11434",
                 temperature: float = 0.1,
                 top_p: float = 0.9,
                 max_tokens: int = 2000,
                 callback: Optional[Callable[[str, str], None]] = None,
                 orchestrator=None,
                 show_model_info: bool = True,
                 max_retries: int = 3):
        """
        Initialize the PICOAgent.

        Args:
            model: The name of the Ollama model to use (default: gpt-oss:20b)
            host: The Ollama server host URL (default: http://localhost:11434)
            temperature: Model temperature for extraction (default: 0.1 for consistent output)
            top_p: Model top-p sampling parameter (default: 0.9)
            max_tokens: Maximum tokens for response (default: 2000)
            callback: Optional callback function for progress updates
            orchestrator: Optional orchestrator for queue-based processing
            show_model_info: Whether to display model information on initialization
            max_retries: Maximum number of retry attempts for failed extractions (default: 3)
        """
        super().__init__(
            model=model,
            host=host,
            temperature=temperature,
            top_p=top_p,
            callback=callback,
            orchestrator=orchestrator,
            show_model_info=show_model_info
        )
        self.max_tokens = max_tokens
        self.max_retries = max_retries

        # Statistics tracking
        self._extraction_stats = {
            'total_extractions': 0,
            'successful_extractions': 0,
            'failed_extractions': 0,
            'low_confidence_extractions': 0,  # confidence < 0.6
            'parse_failures': 0
        }

    def get_agent_type(self) -> str:
        """Get the agent type identifier."""
        return "pico_agent"

    def extract_pico_from_document(
        self,
        document: Dict[str, Any],
        min_confidence: float = 0.5
    ) -> Optional[PICOExtraction]:
        """
        Extract PICO components from a single document.

        Args:
            document: Document dictionary with 'abstract' (required) and optional 'full_text'
            min_confidence: Minimum confidence threshold to accept extraction (0-1)

        Returns:
            PICOExtraction object if successful and confidence >= threshold, None otherwise
        """
        if not self.test_connection():
            logger.error("Cannot connect to Ollama - PICO extraction unavailable")
            return None

        # Get document metadata
        doc_id = document.get('id', 'unknown')
        title = document.get('title', 'Untitled')
        abstract = document.get('abstract', '')
        full_text = document.get('full_text', '')

        # Prefer full text if available, fall back to abstract
        text_to_analyze = full_text if full_text else abstract

        if not text_to_analyze:
            logger.warning(f"No text found for document {doc_id}")
            return None

        # Truncate text if too long (keep first ~8000 chars to stay within context limits)
        if len(text_to_analyze) > 8000:
            text_to_analyze = text_to_analyze[:8000] + "..."
            logger.debug(f"Truncated text for document {doc_id} to 8000 characters")

        self._call_callback("pico_extraction_started", f"Extracting PICO from document {doc_id}")

        # Build extraction prompt
        prompt = f"""You are a medical research expert specializing in evidence-based medicine and systematic reviews.

Extract the PICO components (Population, Intervention, Comparison, Outcome) from the research paper below.

Paper Title: {title}

Paper Text:
{text_to_analyze}

INSTRUCTIONS:
1. Population (P): Describe who was studied. Include:
   - Demographics (age, gender, condition, etc.)
   - Inclusion/exclusion criteria if mentioned
   - Setting (hospital, community, etc.)
   Example: "Adults aged 40-65 with type 2 diabetes and HbA1c > 7%, recruited from primary care clinics"

2. Intervention (I): Describe what was done to the study population. Include:
   - Treatment, procedure, or exposure being tested
   - Dosage, frequency, duration if mentioned
   Example: "Metformin 1000mg twice daily for 12 weeks"

3. Comparison (C): Describe the control or comparison group. Include:
   - What the intervention was compared against
   - Placebo, standard care, no treatment, or alternative intervention
   - If no comparison stated, write "None reported" or "No comparison group"
   Example: "Placebo tablets twice daily for 12 weeks"

4. Outcome (O): Describe what was measured. Include:
   - Primary and secondary outcomes
   - How outcomes were measured
   - Time points if mentioned
   Example: "Change in HbA1c from baseline to 12 weeks (primary); fasting glucose and body weight (secondary)"

5. Study Type: Identify the study design if clear (RCT, cohort study, case-control, cross-sectional, meta-analysis, etc.)

6. Sample Size: Extract the number of participants if mentioned (e.g., "N=150")

7. Confidence Scores: Rate your confidence (0.0-1.0) for each PICO component:
   - 1.0 = Explicitly stated in text, no ambiguity
   - 0.8 = Clearly stated but some details missing
   - 0.6 = Can be inferred but not explicitly stated
   - 0.4 = Partially mentioned, significant uncertainty
   - 0.2 = Barely mentioned, high uncertainty
   - 0.0 = Not found in text

CRITICAL REQUIREMENTS:
- Extract ONLY information that is ACTUALLY PRESENT in the text
- DO NOT invent, assume, or fabricate any information
- If a PICO component is not mentioned, write "Not clearly stated" and give low confidence
- Be specific and use direct quotes or close paraphrases from the text
- Calculate overall_confidence as the average of all four component confidences

Response format (JSON only):
{{
    "population": "detailed description of who was studied",
    "intervention": "detailed description of what was done",
    "comparison": "detailed description of control/comparison group",
    "outcome": "detailed description of what was measured",
    "study_type": "study design type or null if unclear",
    "sample_size": "N=X participants or null if not mentioned",
    "population_confidence": 0.9,
    "intervention_confidence": 0.95,
    "comparison_confidence": 0.85,
    "outcome_confidence": 0.9,
    "overall_confidence": 0.9
}}

Respond ONLY with valid JSON. Do not include any explanatory text outside the JSON."""

        # Make request with retry logic
        try:
            pico_data = self._generate_and_parse_json(
                prompt,
                max_retries=self.max_retries,
                retry_context=f"PICO extraction (doc {doc_id})",
                num_predict=self.max_tokens
            )
        except json.JSONDecodeError as e:
            logger.error(f"Could not parse JSON from LLM after {self.max_retries + 1} attempts for document {doc_id}: {e}")
            self._extraction_stats['parse_failures'] += 1
            return None
        except (ConnectionError, ValueError) as e:
            logger.error(f"Ollama request failed for document {doc_id}: {e}")
            self._extraction_stats['failed_extractions'] += 1
            return None

        # Validate required fields
        required_fields = ['population', 'intervention', 'comparison', 'outcome']
        if not all(field in pico_data for field in required_fields):
            logger.error(f"Missing required PICO fields in response for document {doc_id}")
            self._extraction_stats['failed_extractions'] += 1
            return None

        # Get confidence scores
        overall_confidence = float(pico_data.get('overall_confidence', 0.5))

        # Check confidence threshold
        if overall_confidence < min_confidence:
            logger.info(
                f"PICO extraction confidence {overall_confidence:.2f} below threshold "
                f"{min_confidence:.2f} for document {doc_id}"
            )
            self._extraction_stats['low_confidence_extractions'] += 1
            return None

        # Create PICOExtraction object
        extraction = PICOExtraction(
            population=pico_data['population'],
            intervention=pico_data['intervention'],
            comparison=pico_data['comparison'],
            outcome=pico_data['outcome'],
            document_id=str(doc_id),
            document_title=title,
            extraction_confidence=overall_confidence,
            study_type=pico_data.get('study_type'),
            sample_size=pico_data.get('sample_size'),
            pmid=document.get('pmid'),
            doi=document.get('doi'),
            population_confidence=pico_data.get('population_confidence'),
            intervention_confidence=pico_data.get('intervention_confidence'),
            comparison_confidence=pico_data.get('comparison_confidence'),
            outcome_confidence=pico_data.get('outcome_confidence')
        )

        # Update statistics
        self._extraction_stats['total_extractions'] += 1
        self._extraction_stats['successful_extractions'] += 1

        self._call_callback("pico_extraction_completed", f"Extracted PICO from document {doc_id}")

        logger.info(
            f"Successfully extracted PICO from document {doc_id} "
            f"(confidence: {overall_confidence:.2f})"
        )

        return extraction

    def extract_pico_batch(
        self,
        documents: List[Dict[str, Any]],
        min_confidence: float = 0.5,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> List[PICOExtraction]:
        """
        Extract PICO components from multiple documents.

        Args:
            documents: List of document dictionaries
            min_confidence: Minimum confidence threshold to accept extractions
            progress_callback: Optional callback(current, total, doc_title) for progress updates

        Returns:
            List of successful PICOExtraction objects
        """
        extractions = []
        total = len(documents)

        logger.info(f"Starting batch PICO extraction for {total} documents")

        for i, document in enumerate(documents):
            doc_title = document.get('title', 'Unknown Document')

            # Call progress callback
            if progress_callback:
                progress_callback(i + 1, total, doc_title)

            # Extract PICO
            extraction = self.extract_pico_from_document(
                document=document,
                min_confidence=min_confidence
            )

            if extraction:
                extractions.append(extraction)
                logger.debug(f"Extracted PICO from document {document.get('id')}")

        logger.info(
            f"Batch extraction completed: {len(extractions)} successful out of {total} documents"
        )

        return extractions

    def get_extraction_stats(self) -> Dict[str, Any]:
        """
        Get PICO extraction statistics.

        Returns:
            Dictionary with extraction statistics including success rate
        """
        total = self._extraction_stats['total_extractions']
        if total == 0:
            return {**self._extraction_stats, 'success_rate': 0.0}

        return {
            **self._extraction_stats,
            'success_rate': self._extraction_stats['successful_extractions'] / total
        }

    def format_pico_summary(self, extraction: PICOExtraction) -> str:
        """
        Format a PICO extraction as a human-readable summary.

        Args:
            extraction: PICOExtraction object

        Returns:
            Formatted string summary
        """
        lines = [
            f"\n{'='*80}",
            f"PICO EXTRACTION: {extraction.document_title}",
            f"{'='*80}",
            f"Document ID: {extraction.document_id}",
        ]

        if extraction.pmid:
            lines.append(f"PMID: {extraction.pmid}")
        if extraction.doi:
            lines.append(f"DOI: {extraction.doi}")
        if extraction.study_type:
            lines.append(f"Study Type: {extraction.study_type}")
        if extraction.sample_size:
            lines.append(f"Sample Size: {extraction.sample_size}")

        lines.extend([
            f"\nOverall Confidence: {extraction.extraction_confidence:.2%}",
            f"\n--- POPULATION (Confidence: {extraction.population_confidence or 'N/A'}) ---",
            extraction.population,
            f"\n--- INTERVENTION (Confidence: {extraction.intervention_confidence or 'N/A'}) ---",
            extraction.intervention,
            f"\n--- COMPARISON (Confidence: {extraction.comparison_confidence or 'N/A'}) ---",
            extraction.comparison,
            f"\n--- OUTCOME (Confidence: {extraction.outcome_confidence or 'N/A'}) ---",
            extraction.outcome,
            f"{'='*80}\n"
        ])

        return '\n'.join(lines)

    def export_to_json(self, extractions: List[PICOExtraction], output_file: str) -> None:
        """
        Export PICO extractions to JSON file.

        Args:
            extractions: List of PICOExtraction objects
            output_file: Path to output JSON file
        """
        data = {
            'extractions': [e.to_dict() for e in extractions],
            'metadata': {
                'total_extractions': len(extractions),
                'extraction_date': datetime.now(timezone.utc).isoformat(),
                'agent_model': self.model,
                'statistics': self.get_extraction_stats()
            }
        }

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Exported {len(extractions)} PICO extractions to {output_file}")

    def export_to_csv(self, extractions: List[PICOExtraction], output_file: str) -> None:
        """
        Export PICO extractions to CSV file for systematic review tools.

        Args:
            extractions: List of PICOExtraction objects
            output_file: Path to output CSV file
        """
        import csv

        fieldnames = [
            'document_id', 'document_title', 'pmid', 'doi',
            'study_type', 'sample_size',
            'population', 'intervention', 'comparison', 'outcome',
            'population_confidence', 'intervention_confidence',
            'comparison_confidence', 'outcome_confidence',
            'extraction_confidence', 'created_at'
        ]

        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for extraction in extractions:
                row = extraction.to_dict()
                # Keep only fields in fieldnames
                row = {k: v for k, v in row.items() if k in fieldnames}
                writer.writerow(row)

        logger.info(f"Exported {len(extractions)} PICO extractions to {output_file}")
