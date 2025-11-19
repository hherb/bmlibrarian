"""
Study Assessment Agent for Evaluating Research Quality and Trustworthiness

This agent evaluates medical research publications to assess:
- Study type and design characteristics
- Methodological quality
- Strengths and limitations
- Overall trustworthiness and confidence in findings

The assessment helps researchers and clinicians understand the reliability and
applicability of evidence when making clinical decisions or conducting systematic reviews.
"""

import json
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

from .base import BaseAgent

logger = logging.getLogger(__name__)


@dataclass
class StudyAssessment:
    """Represents a comprehensive quality assessment of a research study."""

    # Study classification
    study_type: str  # e.g., "RCT", "cohort study", "case report", "meta-analysis"
    study_design: str  # e.g., "prospective, double-blinded, multi-center"

    # Quality assessment
    quality_score: float  # 0-10 scale (10 = highest quality)
    strengths: List[str]  # List of study strengths
    limitations: List[str]  # List of weaknesses/limitations

    # Trustworthiness evaluation
    overall_confidence: float  # 0-1 scale (1 = highest confidence)
    confidence_explanation: str  # Explanation of confidence rating

    # Level of evidence
    evidence_level: str  # e.g., "Level 1 (high)", "Level 3 (moderate)", "Level 5 (low)"

    # Metadata
    document_id: str
    document_title: str

    # Optional detailed characteristics
    is_prospective: Optional[bool] = None
    is_retrospective: Optional[bool] = None
    is_blinded: Optional[bool] = None
    is_double_blinded: Optional[bool] = None
    is_randomized: Optional[bool] = None
    is_controlled: Optional[bool] = None
    is_multi_center: Optional[bool] = None
    sample_size: Optional[str] = None
    follow_up_duration: Optional[str] = None

    # Bias assessment
    selection_bias_risk: Optional[str] = None  # "low", "moderate", "high", "unclear"
    performance_bias_risk: Optional[str] = None
    detection_bias_risk: Optional[str] = None
    attrition_bias_risk: Optional[str] = None
    reporting_bias_risk: Optional[str] = None

    # Additional metadata
    pmid: Optional[str] = None
    doi: Optional[str] = None
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


class StudyAssessmentAgent(BaseAgent):
    """
    Agent for assessing the quality and trustworthiness of biomedical research studies.

    This agent uses large language models to evaluate research publications and provide
    structured assessments of study design, methodological quality, and overall reliability.
    This is essential for evidence synthesis, systematic reviews, and evidence-based practice.
    """

    def __init__(self,
                 model: str = "gpt-oss:20b",
                 host: str = "http://localhost:11434",
                 temperature: float = 0.1,
                 top_p: float = 0.9,
                 max_tokens: int = 3000,
                 callback: Optional[Callable[[str, str], None]] = None,
                 orchestrator=None,
                 show_model_info: bool = True,
                 max_retries: int = 3):
        """
        Initialize the StudyAssessmentAgent.

        Args:
            model: The name of the Ollama model to use (default: gpt-oss:20b)
            host: The Ollama server host URL (default: http://localhost:11434)
            temperature: Model temperature for assessment (default: 0.1 for consistent output)
            top_p: Model top-p sampling parameter (default: 0.9)
            max_tokens: Maximum tokens for response (default: 3000)
            callback: Optional callback function for progress updates
            orchestrator: Optional orchestrator for queue-based processing
            show_model_info: Whether to display model information on initialization
            max_retries: Maximum number of retry attempts for failed assessments (default: 3)
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
        self._assessment_stats = {
            'total_assessments': 0,
            'successful_assessments': 0,
            'failed_assessments': 0,
            'low_confidence_assessments': 0,  # confidence < 0.5
            'parse_failures': 0
        }

    def get_agent_type(self) -> str:
        """Get the agent type identifier."""
        return "study_assessment_agent"

    def assess_study(
        self,
        document: Dict[str, Any],
        min_confidence: float = 0.4
    ) -> Optional[StudyAssessment]:
        """
        Assess the quality and trustworthiness of a single research study.

        Args:
            document: Document dictionary with 'abstract' (required) and optional 'full_text'
            min_confidence: Minimum confidence threshold to accept assessment (0-1)

        Returns:
            StudyAssessment object if successful and confidence >= threshold, None otherwise
        """
        if not self.test_connection():
            logger.error("Cannot connect to Ollama - study assessment unavailable")
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

        # Truncate text if too long (keep first ~12000 chars to stay within context limits)
        if len(text_to_analyze) > 12000:
            text_to_analyze = text_to_analyze[:12000] + "..."
            logger.debug(f"Truncated text for document {doc_id} to 12000 characters")

        self._call_callback("study_assessment_started", f"Assessing study quality for document {doc_id}")

        # Build assessment prompt
        prompt = f"""You are a medical research methodologist and epidemiologist specializing in critical appraisal of biomedical literature.

Conduct a comprehensive quality assessment of the research study below.

Paper Title: {title}

Paper Text:
{text_to_analyze}

INSTRUCTIONS:

1. Study Type: Classify the study design. Common types include:
   - Randomized Controlled Trial (RCT)
   - Cohort study (prospective or retrospective)
   - Case-control study
   - Cross-sectional study
   - Case report or case series
   - Systematic review
   - Meta-analysis
   - Observational study
   - In vitro/laboratory study
   - Animal study
   Be specific (e.g., "Prospective randomized double-blinded controlled trial")

2. Study Design Characteristics: Describe the key design features:
   - Prospective vs retrospective
   - Randomized vs non-randomized
   - Blinded, single-blinded, or double-blinded
   - Controlled (with comparison group) vs uncontrolled
   - Single-center vs multi-center
   Example: "Retrospective, single-center, unblinded cohort study"

3. Quality Score (0-10): Rate overall methodological quality:
   - 9-10: Exceptional quality, rigorous methods, minimal bias risk
   - 7-8: High quality, good methods, low bias risk
   - 5-6: Moderate quality, acceptable methods, some limitations
   - 3-4: Low quality, significant methodological concerns
   - 1-2: Very poor quality, major flaws, high bias risk
   - 0: Fundamentally flawed, unreliable

4. Strengths: List 2-5 specific strengths (e.g., "Large sample size (N=5000)", "Long follow-up period (10 years)", "Randomized allocation", "Validated outcome measures")

5. Limitations/Weaknesses: List 2-5 specific limitations (e.g., "Small sample size", "Short follow-up", "Selection bias", "Lack of blinding", "High dropout rate")

6. Overall Confidence (0.0-1.0): Rate confidence in the study's findings:
   - 0.9-1.0: Very high confidence, findings highly reliable
   - 0.7-0.8: High confidence, findings generally reliable
   - 0.5-0.6: Moderate confidence, findings should be interpreted cautiously
   - 0.3-0.4: Low confidence, significant concerns about reliability
   - 0.0-0.2: Very low confidence, findings questionable

7. Confidence Explanation: Explain your confidence rating (1-2 sentences)

8. Evidence Level: Classify using standard hierarchy:
   - "Level 1 (high)": Systematic reviews of RCTs, high-quality RCTs
   - "Level 2 (moderate-high)": Individual RCTs, systematic reviews of cohort studies
   - "Level 3 (moderate)": Cohort studies, case-control studies
   - "Level 4 (low-moderate)": Case series, poor-quality cohort/case-control
   - "Level 5 (low)": Expert opinion, case reports, mechanistic studies

9. Design Characteristics (boolean flags):
   - is_prospective, is_retrospective, is_randomized, is_controlled
   - is_blinded, is_double_blinded, is_multi_center

10. Sample Size: Extract if mentioned (e.g., "N=150 patients")

11. Follow-up Duration: Extract if mentioned (e.g., "6 months", "median 2.5 years")

12. Bias Risk Assessment: For each bias type, rate as "low", "moderate", "high", or "unclear":
    - selection_bias_risk: How participants were selected
    - performance_bias_risk: Differences in care/interventions received
    - detection_bias_risk: How outcomes were measured
    - attrition_bias_risk: Completeness of outcome data
    - reporting_bias_risk: Selective reporting of outcomes

CRITICAL REQUIREMENTS:
- Extract ONLY information that is ACTUALLY PRESENT in the text
- DO NOT invent, assume, or fabricate any information
- If information is unclear or not mentioned, use null/false or mark as "unclear"
- Be specific and evidence-based in your assessment
- Consider both statistical and clinical significance where mentioned
- Note any conflicts of interest or funding sources if mentioned

Response format (JSON only):
{{
    "study_type": "specific study type",
    "study_design": "detailed design description",
    "quality_score": 7.5,
    "strengths": ["strength 1", "strength 2", "strength 3"],
    "limitations": ["limitation 1", "limitation 2", "limitation 3"],
    "overall_confidence": 0.75,
    "confidence_explanation": "explanation of confidence rating",
    "evidence_level": "Level X (quality descriptor)",
    "is_prospective": true,
    "is_retrospective": false,
    "is_randomized": true,
    "is_controlled": true,
    "is_blinded": false,
    "is_double_blinded": false,
    "is_multi_center": true,
    "sample_size": "N=X participants",
    "follow_up_duration": "duration or null",
    "selection_bias_risk": "low/moderate/high/unclear",
    "performance_bias_risk": "low/moderate/high/unclear",
    "detection_bias_risk": "low/moderate/high/unclear",
    "attrition_bias_risk": "low/moderate/high/unclear",
    "reporting_bias_risk": "low/moderate/high/unclear"
}}

Respond ONLY with valid JSON. Do not include any explanatory text outside the JSON."""

        # Make request with retry logic
        try:
            assessment_data = self._generate_and_parse_json(
                prompt,
                max_retries=self.max_retries,
                retry_context=f"study assessment (doc {doc_id})",
                num_predict=self.max_tokens
            )
        except json.JSONDecodeError as e:
            logger.error(f"Could not parse JSON from LLM after {self.max_retries + 1} attempts for document {doc_id}: {e}")
            self._assessment_stats['parse_failures'] += 1
            return None
        except (ConnectionError, ValueError) as e:
            logger.error(f"Ollama request failed for document {doc_id}: {e}")
            self._assessment_stats['failed_assessments'] += 1
            return None

        # Validate required fields
        required_fields = ['study_type', 'study_design', 'quality_score', 'strengths',
                          'limitations', 'overall_confidence', 'confidence_explanation',
                          'evidence_level']
        if not all(field in assessment_data for field in required_fields):
            logger.error(f"Missing required fields in assessment response for document {doc_id}")
            self._assessment_stats['failed_assessments'] += 1
            return None

        # Get confidence score
        overall_confidence = float(assessment_data.get('overall_confidence', 0.5))

        # Check confidence threshold
        if overall_confidence < min_confidence:
            logger.info(
                f"Study assessment confidence {overall_confidence:.2f} below threshold "
                f"{min_confidence:.2f} for document {doc_id}"
            )
            self._assessment_stats['low_confidence_assessments'] += 1
            # Still return the assessment, just log it as low confidence
            # (unlike PICO where we return None, assessments are still useful even with lower confidence)

        # Create StudyAssessment object
        assessment = StudyAssessment(
            study_type=assessment_data['study_type'],
            study_design=assessment_data['study_design'],
            quality_score=float(assessment_data['quality_score']),
            strengths=assessment_data['strengths'],
            limitations=assessment_data['limitations'],
            overall_confidence=overall_confidence,
            confidence_explanation=assessment_data['confidence_explanation'],
            evidence_level=assessment_data['evidence_level'],
            document_id=str(doc_id),
            document_title=title,
            is_prospective=assessment_data.get('is_prospective'),
            is_retrospective=assessment_data.get('is_retrospective'),
            is_blinded=assessment_data.get('is_blinded'),
            is_double_blinded=assessment_data.get('is_double_blinded'),
            is_randomized=assessment_data.get('is_randomized'),
            is_controlled=assessment_data.get('is_controlled'),
            is_multi_center=assessment_data.get('is_multi_center'),
            sample_size=assessment_data.get('sample_size'),
            follow_up_duration=assessment_data.get('follow_up_duration'),
            selection_bias_risk=assessment_data.get('selection_bias_risk'),
            performance_bias_risk=assessment_data.get('performance_bias_risk'),
            detection_bias_risk=assessment_data.get('detection_bias_risk'),
            attrition_bias_risk=assessment_data.get('attrition_bias_risk'),
            reporting_bias_risk=assessment_data.get('reporting_bias_risk'),
            pmid=document.get('pmid'),
            doi=document.get('doi')
        )

        # Update statistics
        self._assessment_stats['total_assessments'] += 1
        self._assessment_stats['successful_assessments'] += 1

        self._call_callback("study_assessment_completed", f"Assessed study quality for document {doc_id}")

        logger.info(
            f"Successfully assessed study {doc_id} "
            f"(quality: {assessment.quality_score:.1f}/10, confidence: {overall_confidence:.2f})"
        )

        return assessment

    def assess_batch(
        self,
        documents: List[Dict[str, Any]],
        min_confidence: float = 0.4,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> List[StudyAssessment]:
        """
        Assess quality and trustworthiness for multiple studies.

        Args:
            documents: List of document dictionaries
            min_confidence: Minimum confidence threshold to accept assessments
            progress_callback: Optional callback(current, total, doc_title) for progress updates

        Returns:
            List of successful StudyAssessment objects
        """
        assessments = []
        total = len(documents)

        logger.info(f"Starting batch study assessment for {total} documents")

        for i, document in enumerate(documents):
            doc_title = document.get('title', 'Unknown Document')

            # Call progress callback
            if progress_callback:
                progress_callback(i + 1, total, doc_title)

            # Assess study
            assessment = self.assess_study(
                document=document,
                min_confidence=min_confidence
            )

            if assessment:
                assessments.append(assessment)
                logger.debug(f"Assessed study {document.get('id')}")

        logger.info(
            f"Batch assessment completed: {len(assessments)} successful out of {total} documents"
        )

        return assessments

    def get_assessment_stats(self) -> Dict[str, Any]:
        """
        Get study assessment statistics.

        Returns:
            Dictionary with assessment statistics including success rate
        """
        total = self._assessment_stats['total_assessments']
        if total == 0:
            return {**self._assessment_stats, 'success_rate': 0.0}

        return {
            **self._assessment_stats,
            'success_rate': self._assessment_stats['successful_assessments'] / total
        }

    def format_assessment_summary(self, assessment: StudyAssessment) -> str:
        """
        Format a study assessment as a human-readable summary.

        Args:
            assessment: StudyAssessment object

        Returns:
            Formatted string summary
        """
        lines = [
            f"\n{'='*80}",
            f"STUDY QUALITY ASSESSMENT: {assessment.document_title}",
            f"{'='*80}",
            f"Document ID: {assessment.document_id}",
        ]

        if assessment.pmid:
            lines.append(f"PMID: {assessment.pmid}")
        if assessment.doi:
            lines.append(f"DOI: {assessment.doi}")

        lines.extend([
            f"\n--- STUDY CLASSIFICATION ---",
            f"Study Type: {assessment.study_type}",
            f"Study Design: {assessment.study_design}",
            f"Evidence Level: {assessment.evidence_level}",
        ])

        if assessment.sample_size:
            lines.append(f"Sample Size: {assessment.sample_size}")
        if assessment.follow_up_duration:
            lines.append(f"Follow-up: {assessment.follow_up_duration}")

        # Design characteristics
        design_chars = []
        if assessment.is_prospective:
            design_chars.append("Prospective")
        if assessment.is_retrospective:
            design_chars.append("Retrospective")
        if assessment.is_randomized:
            design_chars.append("Randomized")
        if assessment.is_controlled:
            design_chars.append("Controlled")
        if assessment.is_double_blinded:
            design_chars.append("Double-blinded")
        elif assessment.is_blinded:
            design_chars.append("Blinded")
        if assessment.is_multi_center:
            design_chars.append("Multi-center")

        if design_chars:
            lines.append(f"Characteristics: {', '.join(design_chars)}")

        lines.extend([
            f"\n--- QUALITY ASSESSMENT ---",
            f"Quality Score: {assessment.quality_score:.1f}/10",
            f"Overall Confidence: {assessment.overall_confidence:.2%}",
            f"Confidence Explanation: {assessment.confidence_explanation}",
        ])

        lines.append(f"\n--- STRENGTHS ---")
        for i, strength in enumerate(assessment.strengths, 1):
            lines.append(f"{i}. {strength}")

        lines.append(f"\n--- LIMITATIONS ---")
        for i, limitation in enumerate(assessment.limitations, 1):
            lines.append(f"{i}. {limitation}")

        # Bias assessment
        bias_items = []
        if assessment.selection_bias_risk:
            bias_items.append(f"Selection: {assessment.selection_bias_risk}")
        if assessment.performance_bias_risk:
            bias_items.append(f"Performance: {assessment.performance_bias_risk}")
        if assessment.detection_bias_risk:
            bias_items.append(f"Detection: {assessment.detection_bias_risk}")
        if assessment.attrition_bias_risk:
            bias_items.append(f"Attrition: {assessment.attrition_bias_risk}")
        if assessment.reporting_bias_risk:
            bias_items.append(f"Reporting: {assessment.reporting_bias_risk}")

        if bias_items:
            lines.append(f"\n--- BIAS RISK ASSESSMENT ---")
            for item in bias_items:
                lines.append(f"  {item}")

        lines.append(f"{'='*80}\n")

        return '\n'.join(lines)

    def export_to_json(self, assessments: List[StudyAssessment], output_file: str) -> None:
        """
        Export study assessments to JSON file.

        Args:
            assessments: List of StudyAssessment objects
            output_file: Path to output JSON file
        """
        data = {
            'assessments': [a.to_dict() for a in assessments],
            'metadata': {
                'total_assessments': len(assessments),
                'assessment_date': datetime.now(timezone.utc).isoformat(),
                'agent_model': self.model,
                'statistics': self.get_assessment_stats()
            }
        }

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Exported {len(assessments)} study assessments to {output_file}")

    def export_to_csv(self, assessments: List[StudyAssessment], output_file: str) -> None:
        """
        Export study assessments to CSV file for analysis tools.

        Args:
            assessments: List of StudyAssessment objects
            output_file: Path to output CSV file
        """
        import csv

        fieldnames = [
            'document_id', 'document_title', 'pmid', 'doi',
            'study_type', 'study_design', 'evidence_level',
            'quality_score', 'overall_confidence', 'confidence_explanation',
            'is_prospective', 'is_retrospective', 'is_randomized', 'is_controlled',
            'is_blinded', 'is_double_blinded', 'is_multi_center',
            'sample_size', 'follow_up_duration',
            'selection_bias_risk', 'performance_bias_risk', 'detection_bias_risk',
            'attrition_bias_risk', 'reporting_bias_risk',
            'strengths', 'limitations', 'created_at'
        ]

        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for assessment in assessments:
                row = assessment.to_dict()
                # Convert lists to strings for CSV
                row['strengths'] = '; '.join(row['strengths'])
                row['limitations'] = '; '.join(row['limitations'])
                # Keep only fields in fieldnames
                row = {k: v for k, v in row.items() if k in fieldnames}
                writer.writerow(row)

        logger.info(f"Exported {len(assessments)} study assessments to {output_file}")

    def get_quality_distribution(self, assessments: List[StudyAssessment]) -> Dict[str, int]:
        """
        Get distribution of quality scores across assessments.

        Args:
            assessments: List of StudyAssessment objects

        Returns:
            Dictionary with quality categories and counts
        """
        distribution = {
            'exceptional (9-10)': 0,
            'high (7-8)': 0,
            'moderate (5-6)': 0,
            'low (3-4)': 0,
            'very_low (0-2)': 0
        }

        for assessment in assessments:
            score = assessment.quality_score
            if score >= 9:
                distribution['exceptional (9-10)'] += 1
            elif score >= 7:
                distribution['high (7-8)'] += 1
            elif score >= 5:
                distribution['moderate (5-6)'] += 1
            elif score >= 3:
                distribution['low (3-4)'] += 1
            else:
                distribution['very_low (0-2)'] += 1

        return distribution

    def get_evidence_level_distribution(self, assessments: List[StudyAssessment]) -> Dict[str, int]:
        """
        Get distribution of evidence levels across assessments.

        Args:
            assessments: List of StudyAssessment objects

        Returns:
            Dictionary with evidence levels and counts
        """
        distribution = {}
        for assessment in assessments:
            level = assessment.evidence_level
            distribution[level] = distribution.get(level, 0) + 1

        return distribution
