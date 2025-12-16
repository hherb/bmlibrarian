"""Tests for detailed quality assessment agent."""

import pytest
from unittest.mock import MagicMock

from bmlibrarian.lite.quality.quality_agent import (
    LiteQualityAgent,
    ASSESSMENT_SYSTEM_PROMPT,
)
from bmlibrarian.lite.quality.data_models import (
    StudyDesign,
    QualityTier,
    QualityAssessment,
    BiasRisk,
)


class TestLiteQualityAgent:
    """Tests for LiteQualityAgent."""

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
    def agent(self, mock_config: MagicMock) -> LiteQualityAgent:
        """Create agent with mocked config."""
        return LiteQualityAgent(mock_config)

    def test_initialization(self, agent: LiteQualityAgent) -> None:
        """Test agent initialization."""
        assert agent.model is not None
        assert agent.config is not None

    def test_custom_model(self, mock_config: MagicMock) -> None:
        """Test agent with custom model."""
        custom_model = "custom-assessor-model"
        agent = LiteQualityAgent(mock_config, model=custom_model)
        assert agent.model == custom_model


class TestResponseParsing:
    """Tests for quality agent response parsing."""

    @pytest.fixture
    def mock_config(self) -> MagicMock:
        """Create mock configuration."""
        config = MagicMock()
        config.llm = MagicMock()
        config.llm.provider = "anthropic"
        return config

    @pytest.fixture
    def agent(self, mock_config: MagicMock) -> LiteQualityAgent:
        """Create agent for testing."""
        return LiteQualityAgent(mock_config)

    def test_parse_full_rct_response(self, agent: LiteQualityAgent) -> None:
        """Test parsing complete RCT assessment response."""
        response = '''{
            "study_design": "rct",
            "quality_score": 8,
            "evidence_level": "1b",
            "design_characteristics": {
                "randomized": true,
                "controlled": true,
                "blinded": "double",
                "prospective": true,
                "multicenter": true
            },
            "sample_size": 450,
            "bias_risk": {
                "selection": "low",
                "performance": "low",
                "detection": "low",
                "attrition": "unclear",
                "reporting": "low"
            },
            "strengths": ["Double-blind design", "Large sample size", "Pre-registered"],
            "limitations": ["Industry funded", "Short follow-up"],
            "confidence": 0.92
        }'''
        result = agent._parse_response(response)

        assert result.study_design == StudyDesign.RCT
        assert result.quality_tier == QualityTier.TIER_4_EXPERIMENTAL
        assert result.quality_score == 8.0
        assert result.evidence_level == "1b"
        assert result.is_randomized is True
        assert result.is_controlled is True
        assert result.is_blinded == "double"
        assert result.is_prospective is True
        assert result.is_multicenter is True
        assert result.sample_size == 450
        assert result.confidence == 0.92
        assert result.bias_risk is not None
        assert result.bias_risk.selection == "low"
        assert result.bias_risk.attrition == "unclear"
        assert len(result.strengths) == 3
        assert len(result.limitations) == 2
        assert result.assessment_tier == 3

    def test_parse_systematic_review_response(self, agent: LiteQualityAgent) -> None:
        """Test parsing systematic review response."""
        response = '''{
            "study_design": "systematic_review",
            "quality_score": 9,
            "evidence_level": "1a",
            "design_characteristics": {
                "randomized": null,
                "controlled": null,
                "blinded": null,
                "prospective": null,
                "multicenter": null
            },
            "sample_size": null,
            "bias_risk": {
                "selection": "low",
                "performance": "unclear",
                "detection": "low",
                "attrition": "unclear",
                "reporting": "low"
            },
            "strengths": ["Comprehensive search", "Quality assessment included"],
            "limitations": ["Publication bias possible"],
            "confidence": 0.95
        }'''
        result = agent._parse_response(response)

        assert result.study_design == StudyDesign.SYSTEMATIC_REVIEW
        assert result.quality_tier == QualityTier.TIER_5_SYNTHESIS
        assert result.quality_score == 9.0
        assert result.evidence_level == "1a"
        assert result.sample_size is None

    def test_parse_markdown_wrapped_response(self, agent: LiteQualityAgent) -> None:
        """Test parsing response wrapped in markdown code blocks."""
        response = '''```json
{
    "study_design": "cohort_prospective",
    "quality_score": 6,
    "evidence_level": "2b",
    "design_characteristics": {
        "randomized": false,
        "controlled": true,
        "blinded": "none",
        "prospective": true,
        "multicenter": false
    },
    "sample_size": 1200,
    "bias_risk": {
        "selection": "unclear",
        "performance": "high",
        "detection": "unclear",
        "attrition": "low",
        "reporting": "low"
    },
    "strengths": ["Large sample size"],
    "limitations": ["Observational design", "Confounding possible"],
    "confidence": 0.85
}
```'''
        result = agent._parse_response(response)

        assert result.study_design == StudyDesign.COHORT_PROSPECTIVE
        assert result.sample_size == 1200

    def test_parse_invalid_json(self, agent: LiteQualityAgent) -> None:
        """Test handling of invalid JSON response."""
        response = "This is not valid JSON"
        result = agent._parse_response(response)

        assert result.study_design == StudyDesign.UNKNOWN
        assert result.quality_tier == QualityTier.UNCLASSIFIED
        assert result.assessment_tier == 0

    def test_parse_missing_optional_fields(self, agent: LiteQualityAgent) -> None:
        """Test handling of response with missing optional fields."""
        response = '''{
            "study_design": "rct",
            "quality_score": 7,
            "confidence": 0.8
        }'''
        result = agent._parse_response(response)

        assert result.study_design == StudyDesign.RCT
        assert result.quality_score == 7.0
        assert result.evidence_level is None
        assert result.bias_risk is not None  # Default BiasRisk with unclear values
        assert result.strengths == []
        assert result.limitations == []


class TestBiasRiskParsing:
    """Tests for bias risk parsing."""

    @pytest.fixture
    def mock_config(self) -> MagicMock:
        """Create mock configuration."""
        config = MagicMock()
        config.llm = MagicMock()
        config.llm.provider = "anthropic"
        return config

    @pytest.fixture
    def agent(self, mock_config: MagicMock) -> LiteQualityAgent:
        """Create agent for testing."""
        return LiteQualityAgent(mock_config)

    def test_parse_valid_bias_risk(self, agent: LiteQualityAgent) -> None:
        """Test parsing valid bias risk values."""
        bias_data = {
            "selection": "low",
            "performance": "high",
            "detection": "unclear",
            "attrition": "low",
            "reporting": "high",
        }
        result = agent._parse_bias_risk(bias_data)

        assert result.selection == "low"
        assert result.performance == "high"
        assert result.detection == "unclear"
        assert result.attrition == "low"
        assert result.reporting == "high"

    def test_parse_invalid_bias_values(self, agent: LiteQualityAgent) -> None:
        """Test invalid bias values default to unclear."""
        bias_data = {
            "selection": "invalid",
            "performance": "maybe",
            "detection": "",
        }
        result = agent._parse_bias_risk(bias_data)

        assert result.selection == "unclear"
        assert result.performance == "unclear"
        assert result.detection == "unclear"
        assert result.attrition == "unclear"
        assert result.reporting == "unclear"

    def test_parse_empty_bias_data(self, agent: LiteQualityAgent) -> None:
        """Test empty bias data returns all unclear."""
        result = agent._parse_bias_risk({})

        assert result.selection == "unclear"
        assert result.performance == "unclear"
        assert result.detection == "unclear"
        assert result.attrition == "unclear"
        assert result.reporting == "unclear"


class TestQualityScoreParsing:
    """Tests for quality score parsing."""

    @pytest.fixture
    def mock_config(self) -> MagicMock:
        """Create mock configuration."""
        config = MagicMock()
        config.llm = MagicMock()
        config.llm.provider = "anthropic"
        return config

    @pytest.fixture
    def agent(self, mock_config: MagicMock) -> LiteQualityAgent:
        """Create agent for testing."""
        return LiteQualityAgent(mock_config)

    def test_parse_valid_quality_score(self, agent: LiteQualityAgent) -> None:
        """Test parsing valid quality scores."""
        assert agent._parse_quality_score(5) == 5.0
        assert agent._parse_quality_score(8.5) == 8.5
        assert agent._parse_quality_score(0) == 0.0
        assert agent._parse_quality_score(10) == 10.0

    def test_parse_quality_score_clamping(self, agent: LiteQualityAgent) -> None:
        """Test quality scores are clamped to 0-10 range."""
        assert agent._parse_quality_score(-5) == 0.0
        assert agent._parse_quality_score(15) == 10.0
        assert agent._parse_quality_score(100) == 10.0

    def test_parse_string_quality_score(self, agent: LiteQualityAgent) -> None:
        """Test parsing string quality scores."""
        assert agent._parse_quality_score("7") == 7.0
        assert agent._parse_quality_score("8.5") == 8.5

    def test_parse_invalid_quality_score(self, agent: LiteQualityAgent) -> None:
        """Test invalid quality score returns 0."""
        assert agent._parse_quality_score("invalid") == 0.0


class TestStudyDesignMapping:
    """Tests for study design string parsing in agent."""

    @pytest.fixture
    def mock_config(self) -> MagicMock:
        """Create mock configuration."""
        config = MagicMock()
        config.llm = MagicMock()
        config.llm.provider = "anthropic"
        return config

    @pytest.fixture
    def agent(self, mock_config: MagicMock) -> LiteQualityAgent:
        """Create agent for testing."""
        return LiteQualityAgent(mock_config)

    def test_parse_common_designs(self, agent: LiteQualityAgent) -> None:
        """Test parsing common study design strings."""
        assert agent._parse_study_design("rct") == StudyDesign.RCT
        assert agent._parse_study_design("systematic_review") == StudyDesign.SYSTEMATIC_REVIEW
        assert agent._parse_study_design("meta_analysis") == StudyDesign.META_ANALYSIS
        assert agent._parse_study_design("cohort_prospective") == StudyDesign.COHORT_PROSPECTIVE

    def test_parse_variant_designs(self, agent: LiteQualityAgent) -> None:
        """Test parsing variant design strings."""
        assert agent._parse_study_design("meta-analysis") == StudyDesign.META_ANALYSIS
        assert agent._parse_study_design("case-control") == StudyDesign.CASE_CONTROL

    def test_parse_unknown_design(self, agent: LiteQualityAgent) -> None:
        """Test unknown design returns UNKNOWN."""
        assert agent._parse_study_design("foobar") == StudyDesign.UNKNOWN
        assert agent._parse_study_design("") == StudyDesign.UNKNOWN
