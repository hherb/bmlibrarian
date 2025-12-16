"""Tests for LLM-based study classifier."""

import pytest
from unittest.mock import MagicMock, patch

from bmlibrarian.lite.quality.study_classifier import (
    LiteStudyClassifier,
    STUDY_DESIGN_MAPPING,
    CLASSIFICATION_SYSTEM_PROMPT,
)
from bmlibrarian.lite.quality.data_models import StudyDesign, StudyClassification


class TestStudyDesignMapping:
    """Tests for study design string mapping."""

    def test_all_study_designs_have_mappings(self) -> None:
        """Test that common study design strings are mapped."""
        expected_keys = [
            "systematic_review",
            "meta_analysis",
            "rct",
            "cohort_prospective",
            "cohort_retrospective",
            "case_control",
            "cross_sectional",
            "case_report",
            "editorial",
            "letter",
            "guideline",
        ]
        for key in expected_keys:
            assert key in STUDY_DESIGN_MAPPING, f"Missing mapping for {key}"

    def test_variant_spellings(self) -> None:
        """Test that variant spellings are mapped correctly."""
        # Hyphenated variants
        assert STUDY_DESIGN_MAPPING["meta-analysis"] == StudyDesign.META_ANALYSIS
        assert STUDY_DESIGN_MAPPING["case-control"] == StudyDesign.CASE_CONTROL
        assert STUDY_DESIGN_MAPPING["cross-sectional"] == StudyDesign.CROSS_SECTIONAL

        # Alternative names
        assert STUDY_DESIGN_MAPPING["prospective_cohort"] == StudyDesign.COHORT_PROSPECTIVE
        assert STUDY_DESIGN_MAPPING["retrospective_cohort"] == StudyDesign.COHORT_RETROSPECTIVE


class TestLiteStudyClassifier:
    """Tests for LiteStudyClassifier."""

    @pytest.fixture
    def mock_config(self) -> MagicMock:
        """Create mock configuration."""
        config = MagicMock()
        config.llm = MagicMock()
        config.llm.provider = "anthropic"
        config.llm.temperature = 0.3
        config.llm.max_tokens = 4096
        return config

    @pytest.fixture
    def classifier(self, mock_config: MagicMock) -> LiteStudyClassifier:
        """Create classifier with mocked config."""
        return LiteStudyClassifier(mock_config)

    def test_initialization(self, classifier: LiteStudyClassifier) -> None:
        """Test classifier initialization."""
        assert classifier.model is not None
        assert classifier.config is not None

    def test_custom_model(self, mock_config: MagicMock) -> None:
        """Test classifier with custom model."""
        custom_model = "custom-classifier-model"
        classifier = LiteStudyClassifier(mock_config, model=custom_model)
        assert classifier.model == custom_model


class TestResponseParsing:
    """Tests for classifier response parsing."""

    @pytest.fixture
    def mock_config(self) -> MagicMock:
        """Create mock configuration."""
        config = MagicMock()
        config.llm = MagicMock()
        config.llm.provider = "anthropic"
        return config

    @pytest.fixture
    def classifier(self, mock_config: MagicMock) -> LiteStudyClassifier:
        """Create classifier for testing."""
        return LiteStudyClassifier(mock_config)

    def test_parse_rct_response(self, classifier: LiteStudyClassifier) -> None:
        """Test parsing RCT classification response."""
        response = '''{
            "study_design": "rct",
            "is_randomized": true,
            "is_blinded": "double",
            "sample_size": 450,
            "confidence": 0.92
        }'''
        result = classifier._parse_response(response)

        assert result.study_design == StudyDesign.RCT
        assert result.is_randomized is True
        assert result.is_blinded == "double"
        assert result.sample_size == 450
        assert result.confidence == 0.92

    def test_parse_systematic_review_response(self, classifier: LiteStudyClassifier) -> None:
        """Test parsing systematic review response."""
        response = '''{
            "study_design": "systematic_review",
            "is_randomized": null,
            "is_blinded": null,
            "sample_size": null,
            "confidence": 0.95
        }'''
        result = classifier._parse_response(response)

        assert result.study_design == StudyDesign.SYSTEMATIC_REVIEW
        assert result.is_randomized is None
        assert result.sample_size is None
        assert result.confidence == 0.95

    def test_parse_cohort_response(self, classifier: LiteStudyClassifier) -> None:
        """Test parsing cohort study response."""
        response = '''{
            "study_design": "cohort_prospective",
            "is_randomized": false,
            "is_blinded": null,
            "sample_size": 1200,
            "confidence": 0.88
        }'''
        result = classifier._parse_response(response)

        assert result.study_design == StudyDesign.COHORT_PROSPECTIVE
        assert result.is_randomized is False
        assert result.sample_size == 1200

    def test_parse_markdown_wrapped_response(self, classifier: LiteStudyClassifier) -> None:
        """Test parsing response wrapped in markdown code blocks."""
        response = '''```json
{
    "study_design": "cohort_prospective",
    "is_randomized": false,
    "is_blinded": null,
    "sample_size": 1200,
    "confidence": 0.88
}
```'''
        result = classifier._parse_response(response)

        assert result.study_design == StudyDesign.COHORT_PROSPECTIVE
        assert result.sample_size == 1200

    def test_parse_invalid_json(self, classifier: LiteStudyClassifier) -> None:
        """Test handling of invalid JSON response."""
        response = "This is not valid JSON"
        result = classifier._parse_response(response)

        assert result.study_design == StudyDesign.UNKNOWN
        assert result.confidence == 0.0
        assert result.raw_response == response

    def test_parse_empty_response(self, classifier: LiteStudyClassifier) -> None:
        """Test handling of empty response."""
        response = ""
        result = classifier._parse_response(response)

        assert result.study_design == StudyDesign.UNKNOWN
        assert result.confidence == 0.0

    def test_parse_missing_fields(self, classifier: LiteStudyClassifier) -> None:
        """Test handling of response with missing fields."""
        response = '''{"study_design": "rct"}'''
        result = classifier._parse_response(response)

        assert result.study_design == StudyDesign.RCT
        # Default confidence is 0.0 (CONFIDENCE_PARSE_FAILURE_DEFAULT)
        # to signal uncertainty rather than hiding it with arbitrary values
        assert result.confidence == 0.0
        assert result.is_randomized is None
        assert result.sample_size is None


class TestStudyDesignParsing:
    """Tests for study design string parsing."""

    @pytest.fixture
    def mock_config(self) -> MagicMock:
        """Create mock configuration."""
        config = MagicMock()
        config.llm = MagicMock()
        config.llm.provider = "anthropic"
        return config

    @pytest.fixture
    def classifier(self, mock_config: MagicMock) -> LiteStudyClassifier:
        """Create classifier for testing."""
        return LiteStudyClassifier(mock_config)

    def test_parse_study_design_lowercase(self, classifier: LiteStudyClassifier) -> None:
        """Test parsing lowercase study design strings."""
        assert classifier._parse_study_design("rct") == StudyDesign.RCT
        assert classifier._parse_study_design("meta_analysis") == StudyDesign.META_ANALYSIS
        assert classifier._parse_study_design("case_control") == StudyDesign.CASE_CONTROL

    def test_parse_study_design_variants(self, classifier: LiteStudyClassifier) -> None:
        """Test parsing variant study design strings."""
        assert classifier._parse_study_design("meta-analysis") == StudyDesign.META_ANALYSIS
        assert classifier._parse_study_design("case-control") == StudyDesign.CASE_CONTROL
        assert classifier._parse_study_design("cross-sectional") == StudyDesign.CROSS_SECTIONAL

    def test_parse_unknown_design(self, classifier: LiteStudyClassifier) -> None:
        """Test parsing unknown study design returns UNKNOWN."""
        assert classifier._parse_study_design("invalid_type") == StudyDesign.UNKNOWN
        assert classifier._parse_study_design("") == StudyDesign.UNKNOWN
        assert classifier._parse_study_design("foobar") == StudyDesign.UNKNOWN


class TestBlindingParsing:
    """Tests for blinding value parsing."""

    @pytest.fixture
    def mock_config(self) -> MagicMock:
        """Create mock configuration."""
        config = MagicMock()
        config.llm = MagicMock()
        config.llm.provider = "anthropic"
        return config

    @pytest.fixture
    def classifier(self, mock_config: MagicMock) -> LiteStudyClassifier:
        """Create classifier for testing."""
        return LiteStudyClassifier(mock_config)

    def test_parse_valid_blinding(self, classifier: LiteStudyClassifier) -> None:
        """Test parsing valid blinding values."""
        assert classifier._parse_blinding("none") == "none"
        assert classifier._parse_blinding("single") == "single"
        assert classifier._parse_blinding("double") == "double"
        assert classifier._parse_blinding("triple") == "triple"

    def test_parse_blinding_case_insensitive(self, classifier: LiteStudyClassifier) -> None:
        """Test blinding parsing is case insensitive."""
        assert classifier._parse_blinding("DOUBLE") == "double"
        assert classifier._parse_blinding("Single") == "single"

    def test_parse_invalid_blinding(self, classifier: LiteStudyClassifier) -> None:
        """Test invalid blinding returns None."""
        assert classifier._parse_blinding("invalid") is None
        assert classifier._parse_blinding("quadruple") is None
        assert classifier._parse_blinding("") is None

    def test_parse_null_blinding(self, classifier: LiteStudyClassifier) -> None:
        """Test null blinding returns None."""
        assert classifier._parse_blinding(None) is None


class TestSampleSizeParsing:
    """Tests for sample size parsing."""

    @pytest.fixture
    def mock_config(self) -> MagicMock:
        """Create mock configuration."""
        config = MagicMock()
        config.llm = MagicMock()
        config.llm.provider = "anthropic"
        return config

    @pytest.fixture
    def classifier(self, mock_config: MagicMock) -> LiteStudyClassifier:
        """Create classifier for testing."""
        return LiteStudyClassifier(mock_config)

    def test_parse_integer_sample_size(self, classifier: LiteStudyClassifier) -> None:
        """Test parsing integer sample size."""
        assert classifier._parse_sample_size(100) == 100
        assert classifier._parse_sample_size(1500) == 1500

    def test_parse_string_sample_size(self, classifier: LiteStudyClassifier) -> None:
        """Test parsing string sample size."""
        assert classifier._parse_sample_size("100") == 100
        assert classifier._parse_sample_size("1500") == 1500

    def test_parse_invalid_sample_size(self, classifier: LiteStudyClassifier) -> None:
        """Test parsing invalid sample size returns None."""
        assert classifier._parse_sample_size("invalid") is None
        assert classifier._parse_sample_size("n=100") is None

    def test_parse_null_sample_size(self, classifier: LiteStudyClassifier) -> None:
        """Test null sample size returns None."""
        assert classifier._parse_sample_size(None) is None


class TestConfidenceParsing:
    """Tests for confidence value parsing."""

    @pytest.fixture
    def mock_config(self) -> MagicMock:
        """Create mock configuration."""
        config = MagicMock()
        config.llm = MagicMock()
        config.llm.provider = "anthropic"
        return config

    @pytest.fixture
    def classifier(self, mock_config: MagicMock) -> LiteStudyClassifier:
        """Create classifier for testing."""
        return LiteStudyClassifier(mock_config)

    def test_parse_valid_confidence(self, classifier: LiteStudyClassifier) -> None:
        """Test parsing valid confidence values."""
        assert classifier._parse_confidence(0.5) == 0.5
        assert classifier._parse_confidence(0.95) == 0.95
        assert classifier._parse_confidence(0.0) == 0.0
        assert classifier._parse_confidence(1.0) == 1.0

    def test_parse_confidence_clamping(self, classifier: LiteStudyClassifier) -> None:
        """Test confidence values are clamped to 0-1 range."""
        assert classifier._parse_confidence(-0.5) == 0.0
        assert classifier._parse_confidence(1.5) == 1.0
        assert classifier._parse_confidence(100) == 1.0

    def test_parse_string_confidence(self, classifier: LiteStudyClassifier) -> None:
        """Test parsing string confidence values."""
        assert classifier._parse_confidence("0.75") == 0.75

    def test_parse_invalid_confidence(self, classifier: LiteStudyClassifier) -> None:
        """Test invalid confidence returns zero (signals uncertainty)."""
        # Default is 0.0 (CONFIDENCE_PARSE_FAILURE_DEFAULT)
        # to signal uncertainty rather than hiding it with arbitrary values
        assert classifier._parse_confidence("invalid") == 0.0
