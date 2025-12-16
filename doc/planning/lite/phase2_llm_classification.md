# Phase 2: LLM Classification

## Overview

This phase implements LLM-based quality classification:
1. `LiteStudyClassifier` - Fast classification using Claude Haiku (Tier 2)
2. `LiteQualityAgent` - Detailed assessment using Claude Sonnet (Tier 3)
3. `QualityManager` - Orchestrates all tiers

## Prerequisites

- Phase 1 complete (data models and metadata filter implemented)
- Anthropic API key configured in BMLibrarian Lite

---

## Step 1: Implement Study Classifier (Tier 2)

### 1.1 File: `study_classifier.py`

```python
# src/bmlibrarian/lite/quality/study_classifier.py
"""
Tier 2: Fast study design classification using Claude Haiku.

Provides accurate classification at minimal cost (~$0.00025/document)
for documents without PubMed publication type metadata.
"""

import json
import logging
from typing import Optional

from ..agents.base import LiteBaseAgent
from ..data_models import LiteDocument
from ..config import LiteConfig
from .data_models import StudyDesign, StudyClassification

logger = logging.getLogger(__name__)


# Default model for fast classification
DEFAULT_CLASSIFICATION_MODEL = "claude-3-haiku-20240307"


class LiteStudyClassifier(LiteBaseAgent):
    """
    Fast study design classification using Claude Haiku.

    This classifier focuses on accurately determining what study design
    THIS paper used, ignoring any other studies mentioned in the abstract.
    """

    SYSTEM_PROMPT = """You are a biomedical research classifier.
Your task is to classify the study design of research papers.

CRITICAL RULES:
1. Classify what THIS paper reports, NOT studies it references
2. Look for phrases like "we conducted", "this study", "our trial"
3. Ignore phrases like "previous studies", "Smith et al. reported", "unlike RCTs"
4. If uncertain, return "other" with low confidence
5. Return ONLY valid JSON, no explanation"""

    def __init__(
        self,
        config: LiteConfig,
        model: Optional[str] = None
    ):
        """
        Initialize the study classifier.

        Args:
            config: BMLibrarian Lite configuration
            model: Optional model override (default: Haiku)
        """
        super().__init__(config)
        self.model = model or DEFAULT_CLASSIFICATION_MODEL

    def classify(self, document: LiteDocument) -> StudyClassification:
        """
        Classify study design for a document.

        Args:
            document: The document to classify

        Returns:
            StudyClassification with design and confidence
        """
        # Prepare prompt with truncated abstract
        abstract = (document.abstract or "")[:2000]
        title = document.title or "Untitled"

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
            response = self._call_llm(
                prompt=prompt,
                model=self.model,
                max_tokens=200,  # Short response expected
                temperature=0.1  # Low temperature for consistency
            )
            return self._parse_response(response)

        except Exception as e:
            logger.error(f"Classification failed: {e}")
            return StudyClassification(
                study_design=StudyDesign.UNKNOWN,
                confidence=0.0,
                raw_response=str(e)
            )

    def _parse_response(self, response: str) -> StudyClassification:
        """
        Parse LLM response into StudyClassification.

        Args:
            response: Raw LLM response string

        Returns:
            Parsed StudyClassification
        """
        try:
            # Clean response (remove markdown code blocks if present)
            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            cleaned = cleaned.strip()

            data = json.loads(cleaned)

            # Parse study design
            design_str = data.get("study_design", "unknown").lower().strip()
            study_design = self._parse_study_design(design_str)

            # Parse blinding
            is_blinded = data.get("is_blinded")
            if is_blinded is not None:
                is_blinded = str(is_blinded).lower()
                if is_blinded not in ["none", "single", "double", "triple"]:
                    is_blinded = None

            # Parse sample size
            sample_size = data.get("sample_size")
            if sample_size is not None:
                try:
                    sample_size = int(sample_size)
                except (ValueError, TypeError):
                    sample_size = None

            return StudyClassification(
                study_design=study_design,
                is_randomized=data.get("is_randomized"),
                is_blinded=is_blinded,
                sample_size=sample_size,
                confidence=float(data.get("confidence", 0.5)),
                raw_response=response
            )

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {e}")
            return StudyClassification(
                study_design=StudyDesign.UNKNOWN,
                confidence=0.0,
                raw_response=response
            )

    def _parse_study_design(self, design_str: str) -> StudyDesign:
        """
        Parse study design string to enum.

        Args:
            design_str: Study design as lowercase string

        Returns:
            StudyDesign enum value
        """
        design_map = {
            "systematic_review": StudyDesign.SYSTEMATIC_REVIEW,
            "meta_analysis": StudyDesign.META_ANALYSIS,
            "meta-analysis": StudyDesign.META_ANALYSIS,
            "rct": StudyDesign.RCT,
            "randomized_controlled_trial": StudyDesign.RCT,
            "cohort_prospective": StudyDesign.COHORT_PROSPECTIVE,
            "prospective_cohort": StudyDesign.COHORT_PROSPECTIVE,
            "cohort_retrospective": StudyDesign.COHORT_RETROSPECTIVE,
            "retrospective_cohort": StudyDesign.COHORT_RETROSPECTIVE,
            "retrospective": StudyDesign.COHORT_RETROSPECTIVE,
            "case_control": StudyDesign.CASE_CONTROL,
            "case-control": StudyDesign.CASE_CONTROL,
            "cross_sectional": StudyDesign.CROSS_SECTIONAL,
            "cross-sectional": StudyDesign.CROSS_SECTIONAL,
            "case_series": StudyDesign.CASE_SERIES,
            "case_report": StudyDesign.CASE_REPORT,
            "editorial": StudyDesign.EDITORIAL,
            "letter": StudyDesign.LETTER,
            "comment": StudyDesign.COMMENT,
            "guideline": StudyDesign.GUIDELINE,
            "practice_guideline": StudyDesign.GUIDELINE,
            "other": StudyDesign.OTHER,
            "unknown": StudyDesign.UNKNOWN,
        }
        return design_map.get(design_str, StudyDesign.UNKNOWN)

    def classify_batch(
        self,
        documents: list[LiteDocument],
        progress_callback: Optional[callable] = None
    ) -> list[StudyClassification]:
        """
        Classify multiple documents.

        Args:
            documents: List of documents to classify
            progress_callback: Optional callback(current, total)

        Returns:
            List of classifications in same order as input
        """
        results = []
        for i, doc in enumerate(documents):
            results.append(self.classify(doc))
            if progress_callback:
                progress_callback(i + 1, len(documents))
        return results
```

---

## Step 2: Implement Quality Agent (Tier 3)

### 2.1 File: `quality_agent.py`

```python
# src/bmlibrarian/lite/quality/quality_agent.py
"""
Tier 3: Detailed quality assessment using Claude Sonnet.

Provides comprehensive assessment including bias risk, strengths,
and limitations. Optional - used when detailed assessment is requested.
"""

import json
import logging
from typing import Optional

from ..agents.base import LiteBaseAgent
from ..data_models import LiteDocument
from ..config import LiteConfig
from .data_models import (
    StudyDesign,
    QualityTier,
    QualityAssessment,
    BiasRisk,
    DESIGN_TO_TIER,
    DESIGN_TO_SCORE,
)

logger = logging.getLogger(__name__)


# Default model for detailed assessment
DEFAULT_ASSESSMENT_MODEL = "claude-sonnet-4-20250514"


class LiteQualityAgent(LiteBaseAgent):
    """
    Comprehensive quality assessment using Claude Sonnet.

    Provides detailed evaluation including:
    - Study design classification
    - Evidence level (Oxford CEBM)
    - Design characteristics (randomization, blinding, etc.)
    - Risk of bias assessment
    - Methodological strengths and limitations
    """

    SYSTEM_PROMPT = """You are a research quality assessment expert.
Evaluate the methodological quality of biomedical research papers.

CRITICAL RULES:
1. Extract ONLY information that is ACTUALLY PRESENT in the text
2. DO NOT invent, assume, or fabricate any information
3. If information is unclear or not mentioned, use null or "unclear"
4. Focus on THIS study's methodology, not studies it references
5. Return ONLY valid JSON, no explanation"""

    def __init__(
        self,
        config: LiteConfig,
        model: Optional[str] = None
    ):
        """
        Initialize the quality agent.

        Args:
            config: BMLibrarian Lite configuration
            model: Optional model override (default: Sonnet)
        """
        super().__init__(config)
        self.model = model or DEFAULT_ASSESSMENT_MODEL

    def assess_quality(self, document: LiteDocument) -> QualityAssessment:
        """
        Perform detailed quality assessment on a document.

        Args:
            document: The document to assess

        Returns:
            QualityAssessment with full details
        """
        # Prepare prompt with abstract
        abstract = (document.abstract or "")[:4000]
        title = document.title or "Untitled"

        prompt = f"""Assess this research paper's methodological quality:

Title: {title}
Abstract: {abstract}

Return JSON:
{{
    "study_design": "systematic_review|meta_analysis|rct|cohort_prospective|cohort_retrospective|case_control|cross_sectional|case_series|case_report|editorial|letter|guideline|other",
    "quality_score": <1-10>,
    "evidence_level": "1a|1b|2a|2b|3a|3b|4|5|null",
    "design_characteristics": {{
        "randomized": true|false|null,
        "controlled": true|false|null,
        "blinded": "none"|"single"|"double"|"triple"|null,
        "prospective": true|false|null,
        "multicenter": true|false|null
    }},
    "sample_size": <number or null>,
    "bias_risk": {{
        "selection": "low"|"unclear"|"high",
        "performance": "low"|"unclear"|"high",
        "detection": "low"|"unclear"|"high",
        "attrition": "low"|"unclear"|"high",
        "reporting": "low"|"unclear"|"high"
    }},
    "strengths": ["2-3 methodological strengths"],
    "limitations": ["2-3 methodological limitations"],
    "confidence": <0.0 to 1.0>
}}

Focus on THIS study's methodology, not studies it references."""

        try:
            response = self._call_llm(
                prompt=prompt,
                model=self.model,
                max_tokens=800,
                temperature=0.1
            )
            return self._parse_response(response)

        except Exception as e:
            logger.error(f"Quality assessment failed: {e}")
            return QualityAssessment.unclassified()

    def _parse_response(self, response: str) -> QualityAssessment:
        """
        Parse LLM response into QualityAssessment.

        Args:
            response: Raw LLM response string

        Returns:
            Parsed QualityAssessment
        """
        try:
            # Clean response
            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            cleaned = cleaned.strip()

            data = json.loads(cleaned)

            # Parse study design
            design_str = data.get("study_design", "unknown").lower().strip()
            study_design = self._parse_study_design(design_str)

            # Parse design characteristics
            chars = data.get("design_characteristics", {})

            # Parse bias risk
            bias_data = data.get("bias_risk", {})
            bias_risk = BiasRisk(
                selection=bias_data.get("selection", "unclear"),
                performance=bias_data.get("performance", "unclear"),
                detection=bias_data.get("detection", "unclear"),
                attrition=bias_data.get("attrition", "unclear"),
                reporting=bias_data.get("reporting", "unclear")
            )

            # Parse sample size
            sample_size = data.get("sample_size")
            if sample_size is not None:
                try:
                    sample_size = int(sample_size)
                except (ValueError, TypeError):
                    sample_size = None

            # Parse blinding
            is_blinded = chars.get("blinded")
            if is_blinded is not None:
                is_blinded = str(is_blinded).lower()
                if is_blinded not in ["none", "single", "double", "triple"]:
                    is_blinded = None

            return QualityAssessment(
                assessment_tier=3,
                extraction_method="llm_sonnet",
                study_design=study_design,
                quality_tier=DESIGN_TO_TIER.get(study_design, QualityTier.UNCLASSIFIED),
                quality_score=float(data.get("quality_score", 0)),
                evidence_level=data.get("evidence_level"),
                is_randomized=chars.get("randomized"),
                is_controlled=chars.get("controlled"),
                is_blinded=is_blinded,
                is_prospective=chars.get("prospective"),
                is_multicenter=chars.get("multicenter"),
                sample_size=sample_size,
                confidence=float(data.get("confidence", 0.5)),
                bias_risk=bias_risk,
                strengths=data.get("strengths", []),
                limitations=data.get("limitations", []),
                extraction_details=["Detailed assessment via Claude Sonnet"]
            )

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {e}")
            return QualityAssessment.unclassified()

    def _parse_study_design(self, design_str: str) -> StudyDesign:
        """Parse study design string to enum."""
        design_map = {
            "systematic_review": StudyDesign.SYSTEMATIC_REVIEW,
            "meta_analysis": StudyDesign.META_ANALYSIS,
            "meta-analysis": StudyDesign.META_ANALYSIS,
            "rct": StudyDesign.RCT,
            "cohort_prospective": StudyDesign.COHORT_PROSPECTIVE,
            "cohort_retrospective": StudyDesign.COHORT_RETROSPECTIVE,
            "case_control": StudyDesign.CASE_CONTROL,
            "cross_sectional": StudyDesign.CROSS_SECTIONAL,
            "case_series": StudyDesign.CASE_SERIES,
            "case_report": StudyDesign.CASE_REPORT,
            "editorial": StudyDesign.EDITORIAL,
            "letter": StudyDesign.LETTER,
            "guideline": StudyDesign.GUIDELINE,
            "other": StudyDesign.OTHER,
        }
        return design_map.get(design_str, StudyDesign.UNKNOWN)
```

---

## Step 3: Implement Quality Manager

### 3.1 File: `quality_manager.py`

```python
# src/bmlibrarian/lite/quality/quality_manager.py
"""
Quality Manager: Orchestrates tiered quality assessment.

Combines Tier 1 (metadata), Tier 2 (Haiku), and Tier 3 (Sonnet)
into a unified assessment workflow.
"""

import logging
from typing import Optional, Callable

from ..data_models import LiteDocument
from ..config import LiteConfig
from .data_models import (
    QualityTier,
    QualityFilter,
    QualityAssessment,
)
from .metadata_filter import MetadataFilter
from .study_classifier import LiteStudyClassifier
from .quality_agent import LiteQualityAgent

logger = logging.getLogger(__name__)


class QualityManager:
    """
    Orchestrates tiered quality assessment.

    Assessment flow:
    1. Tier 1: Check PubMed metadata (free, instant)
    2. Tier 2: LLM classification via Haiku (if needed)
    3. Tier 3: Detailed assessment via Sonnet (if requested)
    """

    def __init__(
        self,
        config: LiteConfig,
        classification_model: Optional[str] = None,
        assessment_model: Optional[str] = None
    ):
        """
        Initialize the quality manager.

        Args:
            config: BMLibrarian Lite configuration
            classification_model: Model for Tier 2 (default: Haiku)
            assessment_model: Model for Tier 3 (default: Sonnet)
        """
        self.config = config
        self.metadata_filter = MetadataFilter()
        self.study_classifier = LiteStudyClassifier(
            config,
            model=classification_model
        )
        self.quality_agent = LiteQualityAgent(
            config,
            model=assessment_model
        )

    def assess_document(
        self,
        document: LiteDocument,
        filter_settings: QualityFilter
    ) -> QualityAssessment:
        """
        Assess document quality using tiered approach.

        Args:
            document: The document to assess
            filter_settings: Quality filter configuration

        Returns:
            QualityAssessment from appropriate tier
        """
        # Tier 1: Always try metadata first (free)
        metadata_result = self.metadata_filter.assess(document)
        logger.debug(
            f"Tier 1 result: {metadata_result.study_design.value} "
            f"(confidence: {metadata_result.confidence:.2f})"
        )

        # User wants metadata only - return immediately
        if filter_settings.use_metadata_only:
            return metadata_result

        # If metadata has high confidence, use it
        if (
            metadata_result.confidence >= 0.9 and
            metadata_result.quality_tier != QualityTier.UNCLASSIFIED
        ):
            # Optionally enhance with detailed assessment
            if filter_settings.use_detailed_assessment:
                logger.debug("Tier 3: Detailed assessment requested")
                return self.quality_agent.assess_quality(document)
            return metadata_result

        # Tier 2: LLM classification for unclassified/low-confidence
        if filter_settings.use_llm_classification:
            classification = self.study_classifier.classify(document)
            logger.debug(
                f"Tier 2 result: {classification.study_design.value} "
                f"(confidence: {classification.confidence:.2f})"
            )

            # Tier 3: Detailed assessment if requested
            if filter_settings.use_detailed_assessment:
                logger.debug("Tier 3: Detailed assessment requested")
                return self.quality_agent.assess_quality(document)

            # Convert classification to assessment
            return QualityAssessment.from_classification(classification)

        # Fallback to metadata result
        return metadata_result

    def filter_documents(
        self,
        documents: list[LiteDocument],
        filter_settings: QualityFilter,
        progress_callback: Optional[Callable[[int, int, QualityAssessment], None]] = None
    ) -> tuple[list[LiteDocument], list[QualityAssessment]]:
        """
        Filter documents based on quality criteria.

        Args:
            documents: List of documents to filter
            filter_settings: Quality filter configuration
            progress_callback: Optional callback(current, total, assessment)

        Returns:
            Tuple of (filtered_documents, all_assessments)
        """
        filtered = []
        assessments = []

        for i, doc in enumerate(documents):
            assessment = self.assess_document(doc, filter_settings)
            assessments.append(assessment)

            if assessment.passes_filter(filter_settings):
                filtered.append(doc)

            if progress_callback:
                progress_callback(i + 1, len(documents), assessment)

        logger.info(
            f"Quality filtering: {len(filtered)}/{len(documents)} documents passed"
        )
        return filtered, assessments

    def get_assessment_summary(
        self,
        assessments: list[QualityAssessment]
    ) -> dict:
        """
        Generate summary statistics for assessments.

        Args:
            assessments: List of quality assessments

        Returns:
            Dictionary with summary statistics
        """
        tier_counts = {}
        design_counts = {}
        tier_sources = {1: 0, 2: 0, 3: 0, 0: 0}

        for assessment in assessments:
            # Count by quality tier
            tier_name = assessment.quality_tier.name
            tier_counts[tier_name] = tier_counts.get(tier_name, 0) + 1

            # Count by study design
            design_name = assessment.study_design.value
            design_counts[design_name] = design_counts.get(design_name, 0) + 1

            # Count by assessment source tier
            tier_sources[assessment.assessment_tier] += 1

        return {
            "total": len(assessments),
            "by_quality_tier": tier_counts,
            "by_study_design": design_counts,
            "by_assessment_tier": {
                "metadata": tier_sources[1],
                "haiku": tier_sources[2],
                "sonnet": tier_sources[3],
                "unclassified": tier_sources[0]
            },
            "avg_confidence": (
                sum(a.confidence for a in assessments) / len(assessments)
                if assessments else 0.0
            )
        }
```

---

## Step 4: Update Module Exports

### 4.1 Update `__init__.py`

```python
# src/bmlibrarian/lite/quality/__init__.py
"""
Quality filtering module for BMLibrarian Lite.

Provides tiered quality assessment:
- Tier 1: PubMed metadata filtering (free, instant)
- Tier 2: LLM classification via Claude Haiku (cheap, accurate)
- Tier 3: Detailed assessment via Claude Sonnet (optional)
"""

from .data_models import (
    StudyDesign,
    QualityTier,
    QualityFilter,
    QualityAssessment,
    StudyClassification,
    BiasRisk,
    DESIGN_TO_TIER,
    DESIGN_TO_SCORE,
)
from .metadata_filter import MetadataFilter
from .study_classifier import LiteStudyClassifier
from .quality_agent import LiteQualityAgent
from .quality_manager import QualityManager

__all__ = [
    # Data models
    "StudyDesign",
    "QualityTier",
    "QualityFilter",
    "QualityAssessment",
    "StudyClassification",
    "BiasRisk",
    "DESIGN_TO_TIER",
    "DESIGN_TO_SCORE",
    # Tier 1
    "MetadataFilter",
    # Tier 2
    "LiteStudyClassifier",
    # Tier 3
    "LiteQualityAgent",
    # Manager
    "QualityManager",
]
```

---

## Step 5: Unit Tests

### 5.1 File: `tests/lite/quality/test_study_classifier.py`

```python
"""Tests for LLM-based study classifier."""

import pytest
from unittest.mock import MagicMock, patch

from bmlibrarian.lite.quality.study_classifier import LiteStudyClassifier
from bmlibrarian.lite.quality.data_models import StudyDesign


class TestLiteStudyClassifier:
    """Tests for LiteStudyClassifier."""

    @pytest.fixture
    def mock_config(self):
        """Create mock configuration."""
        config = MagicMock()
        config.llm = MagicMock()
        return config

    @pytest.fixture
    def classifier(self, mock_config):
        """Create classifier with mocked LLM."""
        return LiteStudyClassifier(mock_config)

    def test_parse_rct_response(self, classifier):
        """Test parsing RCT classification response."""
        response = '''{"study_design": "rct", "is_randomized": true, "is_blinded": "double", "sample_size": 450, "confidence": 0.92}'''
        result = classifier._parse_response(response)

        assert result.study_design == StudyDesign.RCT
        assert result.is_randomized is True
        assert result.is_blinded == "double"
        assert result.sample_size == 450
        assert result.confidence == 0.92

    def test_parse_systematic_review_response(self, classifier):
        """Test parsing systematic review response."""
        response = '''{"study_design": "systematic_review", "is_randomized": null, "is_blinded": null, "sample_size": null, "confidence": 0.95}'''
        result = classifier._parse_response(response)

        assert result.study_design == StudyDesign.SYSTEMATIC_REVIEW
        assert result.is_randomized is None
        assert result.sample_size is None

    def test_parse_markdown_wrapped_response(self, classifier):
        """Test parsing response wrapped in markdown code blocks."""
        response = '''```json
{"study_design": "cohort_prospective", "is_randomized": false, "is_blinded": null, "sample_size": 1200, "confidence": 0.88}
```'''
        result = classifier._parse_response(response)

        assert result.study_design == StudyDesign.COHORT_PROSPECTIVE
        assert result.sample_size == 1200

    def test_parse_invalid_json(self, classifier):
        """Test handling of invalid JSON response."""
        response = "This is not valid JSON"
        result = classifier._parse_response(response)

        assert result.study_design == StudyDesign.UNKNOWN
        assert result.confidence == 0.0

    def test_parse_study_design_variants(self, classifier):
        """Test parsing various study design string formats."""
        assert classifier._parse_study_design("rct") == StudyDesign.RCT
        assert classifier._parse_study_design("meta-analysis") == StudyDesign.META_ANALYSIS
        assert classifier._parse_study_design("case-control") == StudyDesign.CASE_CONTROL
        assert classifier._parse_study_design("cross-sectional") == StudyDesign.CROSS_SECTIONAL
        assert classifier._parse_study_design("unknown_type") == StudyDesign.UNKNOWN
```

### 5.2 File: `tests/lite/quality/test_quality_manager.py`

```python
"""Tests for quality manager orchestration."""

import pytest
from unittest.mock import MagicMock, patch

from bmlibrarian.lite.quality.quality_manager import QualityManager
from bmlibrarian.lite.quality.data_models import (
    StudyDesign,
    QualityTier,
    QualityFilter,
    QualityAssessment,
)


class TestQualityManager:
    """Tests for QualityManager."""

    @pytest.fixture
    def mock_config(self):
        """Create mock configuration."""
        return MagicMock()

    @pytest.fixture
    def manager(self, mock_config):
        """Create quality manager with mocked components."""
        manager = QualityManager(mock_config)
        manager.metadata_filter = MagicMock()
        manager.study_classifier = MagicMock()
        manager.quality_agent = MagicMock()
        return manager

    def test_uses_metadata_when_confident(self, manager):
        """Manager should use metadata when confidence is high."""
        # Mock high-confidence metadata result
        metadata_result = QualityAssessment.from_metadata(
            study_design=StudyDesign.RCT,
            confidence=0.95
        )
        manager.metadata_filter.assess.return_value = metadata_result

        doc = MagicMock()
        filter_settings = QualityFilter()

        result = manager.assess_document(doc, filter_settings)

        assert result.study_design == StudyDesign.RCT
        assert result.assessment_tier == 1
        # Study classifier should not be called
        manager.study_classifier.classify.assert_not_called()

    def test_falls_back_to_llm_when_unclassified(self, manager):
        """Manager should use LLM when metadata is unclassified."""
        # Mock unclassified metadata result
        metadata_result = QualityAssessment.unclassified()
        manager.metadata_filter.assess.return_value = metadata_result

        # Mock LLM classification
        from bmlibrarian.lite.quality.data_models import StudyClassification
        classification = StudyClassification(
            study_design=StudyDesign.COHORT_PROSPECTIVE,
            confidence=0.88
        )
        manager.study_classifier.classify.return_value = classification

        doc = MagicMock()
        filter_settings = QualityFilter(use_llm_classification=True)

        result = manager.assess_document(doc, filter_settings)

        assert result.study_design == StudyDesign.COHORT_PROSPECTIVE
        assert result.assessment_tier == 2
        manager.study_classifier.classify.assert_called_once()

    def test_uses_detailed_assessment_when_requested(self, manager):
        """Manager should use Sonnet when detailed assessment requested."""
        metadata_result = QualityAssessment.unclassified()
        manager.metadata_filter.assess.return_value = metadata_result

        detailed_result = QualityAssessment(
            assessment_tier=3,
            extraction_method="llm_sonnet",
            study_design=StudyDesign.RCT,
            quality_tier=QualityTier.TIER_4_EXPERIMENTAL,
            quality_score=8.0,
            confidence=0.92
        )
        manager.quality_agent.assess_quality.return_value = detailed_result

        doc = MagicMock()
        filter_settings = QualityFilter(
            use_llm_classification=True,
            use_detailed_assessment=True
        )

        result = manager.assess_document(doc, filter_settings)

        assert result.assessment_tier == 3
        manager.quality_agent.assess_quality.assert_called_once()

    def test_filter_documents(self, manager):
        """Manager should correctly filter documents by quality."""
        # Create test documents
        docs = [MagicMock() for _ in range(5)]

        # Mock assessments: 3 RCTs (pass), 2 case reports (fail)
        def mock_assess(doc, settings):
            if docs.index(doc) < 3:
                return QualityAssessment.from_metadata(
                    study_design=StudyDesign.RCT,
                    confidence=0.9
                )
            else:
                return QualityAssessment.from_metadata(
                    study_design=StudyDesign.CASE_REPORT,
                    confidence=0.9
                )

        manager.metadata_filter.assess.side_effect = lambda d: mock_assess(d, None)

        filter_settings = QualityFilter(
            minimum_tier=QualityTier.TIER_4_EXPERIMENTAL,
            use_metadata_only=True
        )

        filtered, assessments = manager.filter_documents(docs, filter_settings)

        assert len(filtered) == 3
        assert len(assessments) == 5

    def test_assessment_summary(self, manager):
        """Manager should generate correct summary statistics."""
        assessments = [
            QualityAssessment.from_metadata(StudyDesign.RCT, 0.9),
            QualityAssessment.from_metadata(StudyDesign.RCT, 0.9),
            QualityAssessment.from_metadata(StudyDesign.SYSTEMATIC_REVIEW, 0.95),
            QualityAssessment.from_metadata(StudyDesign.CASE_REPORT, 0.85),
        ]

        summary = manager.get_assessment_summary(assessments)

        assert summary["total"] == 4
        assert summary["by_study_design"]["rct"] == 2
        assert summary["by_study_design"]["systematic_review"] == 1
        assert summary["by_quality_tier"]["TIER_4_EXPERIMENTAL"] == 2
        assert summary["by_quality_tier"]["TIER_5_SYNTHESIS"] == 1
```

---

## Verification Checklist

After implementing Phase 2, verify:

- [ ] `study_classifier.py` implements LiteStudyClassifier
- [ ] `quality_agent.py` implements LiteQualityAgent
- [ ] `quality_manager.py` implements QualityManager
- [ ] All classes properly handle JSON parsing errors
- [ ] Unit tests pass: `uv run pytest tests/lite/quality/ -v`
- [ ] Integration test with real Anthropic API (optional)

---

## Next Steps

After Phase 2 is complete, proceed to **Phase 3: GUI Integration** which implements:
- QualityFilterPanel widget
- Quality badges for document cards
- Settings dialog integration
