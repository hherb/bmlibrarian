"""Tests for paper weight assessment configuration.

This module tests the configuration schema and validation for the
PaperWeightAssessmentAgent configuration.
"""

import copy
import pytest

from bmlibrarian.config import (
    DEFAULT_PAPER_WEIGHT_CONFIG,
    validate_paper_weight_config,
    validate_paper_weight_config_legacy,
    get_paper_weight_config,
    ValidationResult,
    FLOAT_TOLERANCE,
    WEIGHT_SUM_EXPECTED,
    QUALITY_WEIGHT_SUM_EXPECTED,
    TEMPERATURE_MIN,
    TEMPERATURE_MAX,
    TOP_P_MIN,
    TOP_P_MAX,
)


class TestValidationResult:
    """Tests for the ValidationResult dataclass."""

    def test_valid_result_is_truthy(self):
        """Test that a valid result evaluates to True in boolean context."""
        result = ValidationResult(valid=True, errors=[], warnings=[])
        assert result
        assert bool(result) is True

    def test_invalid_result_is_falsy(self):
        """Test that an invalid result evaluates to False in boolean context."""
        result = ValidationResult(valid=False, errors=["error1"], warnings=[])
        assert not result
        assert bool(result) is False

    def test_raise_if_invalid_does_nothing_when_valid(self):
        """Test that raise_if_invalid does not raise when valid."""
        result = ValidationResult(valid=True, errors=[], warnings=[])
        result.raise_if_invalid()  # Should not raise

    def test_raise_if_invalid_raises_when_invalid(self):
        """Test that raise_if_invalid raises ValueError when invalid."""
        result = ValidationResult(valid=False, errors=["error1", "error2"], warnings=[])
        with pytest.raises(ValueError, match="error1; error2"):
            result.raise_if_invalid()


class TestValidationConstants:
    """Tests for validation constants."""

    def test_float_tolerance_is_reasonable(self):
        """Test that FLOAT_TOLERANCE is within expected range."""
        assert 0.001 <= FLOAT_TOLERANCE <= 0.1
        assert FLOAT_TOLERANCE == 0.01  # Documented value

    def test_weight_sum_expected_is_one(self):
        """Test that WEIGHT_SUM_EXPECTED is 1.0."""
        assert WEIGHT_SUM_EXPECTED == 1.0

    def test_quality_weight_sum_expected_is_ten(self):
        """Test that QUALITY_WEIGHT_SUM_EXPECTED is 10.0."""
        assert QUALITY_WEIGHT_SUM_EXPECTED == 10.0

    def test_temperature_range_is_valid(self):
        """Test that temperature range constants are valid."""
        assert TEMPERATURE_MIN == 0.0
        assert TEMPERATURE_MAX >= 1.0  # At least 1.0

    def test_top_p_range_is_valid(self):
        """Test that top_p range constants are valid."""
        assert TOP_P_MIN == 0.0
        assert TOP_P_MAX == 1.0


class TestDefaultConfig:
    """Tests for the default configuration."""

    def test_default_config_valid(self):
        """Test that default configuration passes validation."""
        result = validate_paper_weight_config(DEFAULT_PAPER_WEIGHT_CONFIG)
        assert result.valid is True
        assert len(result.errors) == 0

    def test_default_config_returns_validation_result(self):
        """Test that validation returns ValidationResult object."""
        result = validate_paper_weight_config(DEFAULT_PAPER_WEIGHT_CONFIG)
        assert isinstance(result, ValidationResult)

    def test_default_config_has_required_keys(self):
        """Test that default config has all required keys."""
        required_keys = [
            "model",
            "temperature",
            "top_p",
            "version",
            "dimension_weights",
            "study_type_hierarchy",
            "study_type_keywords",
            "sample_size_scoring",
            "methodological_quality_weights",
            "risk_of_bias_weights",
            "attrition_thresholds",
        ]
        for key in required_keys:
            assert key in DEFAULT_PAPER_WEIGHT_CONFIG, f"Missing required key: {key}"

    def test_default_dimension_weights_sum_to_one(self):
        """Test that default dimension weights sum to 1.0."""
        weights = DEFAULT_PAPER_WEIGHT_CONFIG["dimension_weights"]
        total = sum(weights.values())
        assert abs(total - WEIGHT_SUM_EXPECTED) < FLOAT_TOLERANCE, \
            f"Dimension weights should sum to {WEIGHT_SUM_EXPECTED}, got {total}"

    def test_default_methodological_quality_weights_sum_to_ten(self):
        """Test that default methodological quality weights sum to 10.0."""
        weights = DEFAULT_PAPER_WEIGHT_CONFIG["methodological_quality_weights"]
        total = sum(weights.values())
        assert abs(total - QUALITY_WEIGHT_SUM_EXPECTED) < FLOAT_TOLERANCE * 10, \
            f"MQ weights should sum to {QUALITY_WEIGHT_SUM_EXPECTED}, got {total}"

    def test_default_risk_of_bias_weights_sum_to_ten(self):
        """Test that default risk of bias weights sum to 10.0."""
        weights = DEFAULT_PAPER_WEIGHT_CONFIG["risk_of_bias_weights"]
        total = sum(weights.values())
        assert abs(total - QUALITY_WEIGHT_SUM_EXPECTED) < FLOAT_TOLERANCE * 10, \
            f"RoB weights should sum to {QUALITY_WEIGHT_SUM_EXPECTED}, got {total}"


class TestDimensionWeightsValidation:
    """Tests for dimension weights validation."""

    def test_dimension_weights_must_sum_to_one(self):
        """Test that dimension weights must sum to 1.0."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["dimension_weights"] = {
            "study_design": 0.1,
            "sample_size": 0.1,
            "methodological_quality": 0.1,
            "risk_of_bias": 0.1,
            "replication_status": 0.1,
        }  # Sums to 0.5

        result = validate_paper_weight_config(config)
        assert not result.valid
        assert any("must sum to" in e and "1" in e for e in result.errors)

    def test_dimension_weights_sum_above_one_rejected(self):
        """Test that dimension weights summing to more than 1.0 are rejected."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["dimension_weights"] = {
            "study_design": 0.30,
            "sample_size": 0.30,
            "methodological_quality": 0.30,
            "risk_of_bias": 0.30,
            "replication_status": 0.30,
        }  # Sums to 1.5

        result = validate_paper_weight_config(config)
        assert not result.valid
        assert any("must sum to" in e and "1" in e for e in result.errors)

    def test_negative_dimension_weights_rejected(self):
        """Test that negative dimension weights are rejected."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["dimension_weights"]["study_design"] = -0.05
        # Adjust another to keep sum at 1.0 (0.25 -> -0.05 = -0.30, so add 0.30)
        config["dimension_weights"]["methodological_quality"] = 0.60

        result = validate_paper_weight_config(config)
        assert not result.valid
        assert any("must be non-negative" in e for e in result.errors)

    def test_empty_dimension_weights_rejected(self):
        """Test that empty dimension weights are rejected."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["dimension_weights"] = {}

        result = validate_paper_weight_config(config)
        assert not result.valid
        assert any("dimension_weights is required" in e for e in result.errors)

    def test_missing_dimension_weights_rejected(self):
        """Test that missing dimension weights are rejected."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        del config["dimension_weights"]

        result = validate_paper_weight_config(config)
        assert not result.valid
        assert any("dimension_weights is required" in e for e in result.errors)

    def test_legacy_validation_raises_valueerror(self):
        """Test that legacy validation function raises ValueError."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["dimension_weights"] = {}

        with pytest.raises(ValueError, match="dimension_weights is required"):
            validate_paper_weight_config_legacy(config)


class TestStudyTypeHierarchyValidation:
    """Tests for study type hierarchy validation."""

    def test_study_type_scores_in_valid_range(self):
        """Test that study type scores must be between 0 and 10."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["study_type_hierarchy"]["rct"] = 15.0

        result = validate_paper_weight_config(config)
        assert not result.valid
        assert any("between 0 and 10" in e for e in result.errors)

    def test_negative_study_type_scores_rejected(self):
        """Test that negative study type scores are rejected."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["study_type_hierarchy"]["case_report"] = -1.0

        result = validate_paper_weight_config(config)
        assert not result.valid
        assert any("between 0 and 10" in e for e in result.errors)

    def test_zero_study_type_score_allowed(self):
        """Test that zero is a valid study type score."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["study_type_hierarchy"]["case_report"] = 0.0

        result = validate_paper_weight_config(config)
        assert result.valid

    def test_ten_study_type_score_allowed(self):
        """Test that 10 is a valid study type score."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["study_type_hierarchy"]["systematic_review"] = 10.0

        result = validate_paper_weight_config(config)
        assert result.valid


class TestMethodologicalQualityWeightsValidation:
    """Tests for methodological quality weights validation."""

    def test_mq_weights_must_sum_to_ten(self):
        """Test that methodological quality weights must sum to 10.0."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["methodological_quality_weights"]["randomization"] = 5.0  # Now sums to 13

        result = validate_paper_weight_config(config)
        assert not result.valid
        assert any("must sum to" in e and "10" in e for e in result.errors)

    def test_negative_mq_weights_rejected(self):
        """Test that negative methodological quality weights are rejected."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["methodological_quality_weights"]["blinding"] = -1.0
        # Adjust to keep sum at 10.0
        config["methodological_quality_weights"]["randomization"] = 6.0

        result = validate_paper_weight_config(config)
        assert not result.valid
        assert any("Methodological quality weight" in e and "non-negative" in e for e in result.errors)


class TestRiskOfBiasWeightsValidation:
    """Tests for risk of bias weights validation."""

    def test_rob_weights_must_sum_to_ten(self):
        """Test that risk of bias weights must sum to 10.0."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["risk_of_bias_weights"]["selection_bias"] = 5.0  # Now sums to 12.5

        result = validate_paper_weight_config(config)
        assert not result.valid
        assert any("must sum to" in e and "10" in e for e in result.errors)

    def test_negative_rob_weights_rejected(self):
        """Test that negative risk of bias weights are rejected."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["risk_of_bias_weights"]["selection_bias"] = -1.0
        # Adjust to keep sum at 10.0
        config["risk_of_bias_weights"]["performance_bias"] = 6.0

        result = validate_paper_weight_config(config)
        assert not result.valid
        assert any("Risk of bias weight" in e and "non-negative" in e for e in result.errors)


class TestAttritionThresholdsValidation:
    """Tests for attrition thresholds validation."""

    def test_attrition_thresholds_must_be_ascending(self):
        """Test that attrition thresholds must be in ascending order."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["attrition_thresholds"] = {
            "excellent": 0.20,  # Wrong order
            "good": 0.10,
            "acceptable": 0.05,
        }

        result = validate_paper_weight_config(config)
        assert not result.valid
        assert any("ascending order" in e for e in result.errors)

    def test_equal_thresholds_rejected(self):
        """Test that equal thresholds are rejected."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["attrition_thresholds"] = {
            "excellent": 0.10,
            "good": 0.10,  # Equal to excellent
            "acceptable": 0.20,
        }

        result = validate_paper_weight_config(config)
        assert not result.valid
        assert any("ascending order" in e for e in result.errors)

    def test_threshold_above_one_rejected(self):
        """Test that thresholds above 1.0 are rejected."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["attrition_thresholds"]["acceptable"] = 1.5

        result = validate_paper_weight_config(config)
        assert not result.valid
        assert any("between 0 and 1" in e for e in result.errors)

    def test_negative_threshold_rejected(self):
        """Test that negative thresholds are rejected."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["attrition_thresholds"]["excellent"] = -0.05

        result = validate_paper_weight_config(config)
        assert not result.valid
        assert any("between 0 and 1" in e for e in result.errors)


class TestSampleSizeScoringValidation:
    """Tests for sample size scoring parameters validation."""

    def test_negative_log_multiplier_rejected(self):
        """Test that negative log multiplier is rejected."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["sample_size_scoring"]["log_multiplier"] = -2.0

        result = validate_paper_weight_config(config)
        assert not result.valid
        assert any("log_multiplier must be positive" in e for e in result.errors)

    def test_zero_log_multiplier_rejected(self):
        """Test that zero log multiplier is rejected."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["sample_size_scoring"]["log_multiplier"] = 0.0

        result = validate_paper_weight_config(config)
        assert not result.valid
        assert any("log_multiplier must be positive" in e for e in result.errors)

    def test_negative_power_bonus_rejected(self):
        """Test that negative power calculation bonus is rejected."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["sample_size_scoring"]["power_calculation_bonus"] = -1.0

        result = validate_paper_weight_config(config)
        assert not result.valid
        assert any("power_calculation_bonus must be non-negative" in e for e in result.errors)

    def test_negative_ci_bonus_rejected(self):
        """Test that negative CI bonus is rejected."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["sample_size_scoring"]["ci_reported_bonus"] = -0.5

        result = validate_paper_weight_config(config)
        assert not result.valid
        assert any("ci_reported_bonus must be non-negative" in e for e in result.errors)

    def test_zero_bonuses_allowed(self):
        """Test that zero bonuses are valid."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["sample_size_scoring"]["power_calculation_bonus"] = 0.0
        config["sample_size_scoring"]["ci_reported_bonus"] = 0.0

        result = validate_paper_weight_config(config)
        assert result.valid


class TestCustomConfigVariations:
    """Tests for valid custom configuration variations."""

    def test_adjusted_weights_valid(self):
        """Test that adjusted weights that still sum correctly are valid."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        # Emphasize methodological quality more
        config["dimension_weights"] = {
            "study_design": 0.20,
            "sample_size": 0.10,
            "methodological_quality": 0.40,
            "risk_of_bias": 0.20,
            "replication_status": 0.10,
        }

        result = validate_paper_weight_config(config)
        assert result.valid

    def test_custom_study_type_hierarchy_valid(self):
        """Test that custom study type hierarchy is valid."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        # Add a new study type
        config["study_type_hierarchy"]["observational"] = 3.5

        result = validate_paper_weight_config(config)
        assert result.valid

    def test_empty_optional_sections_valid(self):
        """Test that empty optional sections are valid."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["study_type_hierarchy"] = {}
        config["methodological_quality_weights"] = {}
        config["risk_of_bias_weights"] = {}
        config["attrition_thresholds"] = {}
        config["sample_size_scoring"] = {}
        config["study_type_keywords"] = {}

        # Only dimension_weights is required
        result = validate_paper_weight_config(config)
        assert result.valid


class TestTemperatureValidation:
    """Tests for temperature parameter validation."""

    def test_valid_temperature_zero(self):
        """Test that temperature of 0.0 is valid."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["temperature"] = 0.0

        result = validate_paper_weight_config(config)
        assert result.valid

    def test_valid_temperature_one(self):
        """Test that temperature of 1.0 is valid."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["temperature"] = 1.0

        result = validate_paper_weight_config(config)
        assert result.valid

    def test_valid_temperature_two(self):
        """Test that temperature of 2.0 is valid (some models support this)."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["temperature"] = 2.0

        result = validate_paper_weight_config(config)
        assert result.valid

    def test_negative_temperature_rejected(self):
        """Test that negative temperature is rejected."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["temperature"] = -0.1

        result = validate_paper_weight_config(config)
        assert not result.valid
        assert any("temperature must be between" in e for e in result.errors)

    def test_temperature_above_max_rejected(self):
        """Test that temperature above maximum is rejected."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["temperature"] = 2.5

        result = validate_paper_weight_config(config)
        assert not result.valid
        assert any("temperature must be between" in e for e in result.errors)

    def test_invalid_temperature_type_rejected(self):
        """Test that non-numeric temperature is rejected."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["temperature"] = "hot"

        result = validate_paper_weight_config(config)
        assert not result.valid
        assert any("temperature must be a number" in e for e in result.errors)


class TestTopPValidation:
    """Tests for top_p parameter validation."""

    def test_valid_top_p_zero(self):
        """Test that top_p of 0.0 is valid."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["top_p"] = 0.0

        result = validate_paper_weight_config(config)
        assert result.valid

    def test_valid_top_p_one(self):
        """Test that top_p of 1.0 is valid."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["top_p"] = 1.0

        result = validate_paper_weight_config(config)
        assert result.valid

    def test_valid_top_p_middle(self):
        """Test that top_p of 0.5 is valid."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["top_p"] = 0.5

        result = validate_paper_weight_config(config)
        assert result.valid

    def test_negative_top_p_rejected(self):
        """Test that negative top_p is rejected."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["top_p"] = -0.1

        result = validate_paper_weight_config(config)
        assert not result.valid
        assert any("top_p must be between" in e for e in result.errors)

    def test_top_p_above_one_rejected(self):
        """Test that top_p above 1.0 is rejected."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["top_p"] = 1.5

        result = validate_paper_weight_config(config)
        assert not result.valid
        assert any("top_p must be between" in e for e in result.errors)

    def test_invalid_top_p_type_rejected(self):
        """Test that non-numeric top_p is rejected."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["top_p"] = "high"

        result = validate_paper_weight_config(config)
        assert not result.valid
        assert any("top_p must be a number" in e for e in result.errors)


class TestModelNameValidation:
    """Tests for model name validation."""

    def test_valid_model_name_with_tag(self):
        """Test that model name with tag is valid."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["model"] = "gpt-oss:20b"

        result = validate_paper_weight_config(config)
        assert result.valid

    def test_valid_model_name_without_tag(self):
        """Test that model name without tag is valid."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["model"] = "medgemma"

        result = validate_paper_weight_config(config)
        assert result.valid

    def test_valid_model_name_with_path(self):
        """Test that model name with path separator is valid."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["model"] = "library/model:tag"

        result = validate_paper_weight_config(config)
        assert result.valid

    def test_empty_model_name_after_strip_rejected(self):
        """Test that whitespace-only model name is rejected."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["model"] = "   "

        result = validate_paper_weight_config(config)
        assert not result.valid
        assert any("model must be a non-empty string" in e for e in result.errors)

    def test_excessively_long_model_name_rejected(self):
        """Test that model name exceeding 256 chars is rejected."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["model"] = "a" * 300

        result = validate_paper_weight_config(config)
        assert not result.valid
        assert any("exceeds maximum length" in e for e in result.errors)

    def test_model_name_with_unusual_chars_warns(self):
        """Test that model name with unusual characters generates warning."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["model"] = "model@name#test"

        result = validate_paper_weight_config(config)
        # Should be valid but with warnings
        assert result.valid
        assert any("unusual characters" in w for w in result.warnings)


class TestStudyTypeKeywordsValidation:
    """Tests for study type keywords validation."""

    def test_valid_keywords(self):
        """Test that valid keywords configuration passes."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        # Default config should have valid keywords
        result = validate_paper_weight_config(config)
        assert result.valid

    def test_empty_keyword_list_rejected(self):
        """Test that empty keyword list is rejected."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["study_type_keywords"]["rct"] = []

        result = validate_paper_weight_config(config)
        assert not result.valid
        assert any("must contain at least one keyword" in e for e in result.errors)

    def test_non_list_keywords_rejected(self):
        """Test that non-list keywords value is rejected."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["study_type_keywords"]["rct"] = "randomized trial"

        result = validate_paper_weight_config(config)
        assert not result.valid
        assert any("must be a list" in e for e in result.errors)

    def test_empty_string_keyword_rejected(self):
        """Test that empty string in keyword list is rejected."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["study_type_keywords"]["rct"] = ["randomized trial", "", "RCT"]

        result = validate_paper_weight_config(config)
        assert not result.valid
        assert any("must be a non-empty string" in e for e in result.errors)

    def test_whitespace_only_keyword_rejected(self):
        """Test that whitespace-only keyword is rejected."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["study_type_keywords"]["rct"] = ["randomized trial", "   ", "RCT"]

        result = validate_paper_weight_config(config)
        assert not result.valid
        assert any("must be a non-empty string" in e for e in result.errors)

    def test_non_string_keyword_rejected(self):
        """Test that non-string keyword is rejected."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["study_type_keywords"]["rct"] = ["randomized trial", 123, "RCT"]

        result = validate_paper_weight_config(config)
        assert not result.valid
        assert any("must be a non-empty string" in e for e in result.errors)


class TestMultipleValidationErrors:
    """Tests for collecting multiple validation errors."""

    def test_multiple_errors_collected(self):
        """Test that multiple errors are collected in a single validation."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        # Introduce multiple errors
        config["temperature"] = -1.0  # Invalid
        config["top_p"] = 1.5  # Invalid
        config["dimension_weights"] = {}  # Invalid

        result = validate_paper_weight_config(config)
        assert not result.valid
        # Should have at least 3 errors
        assert len(result.errors) >= 3

    def test_errors_are_descriptive(self):
        """Test that error messages are descriptive."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["temperature"] = -1.0

        result = validate_paper_weight_config(config)
        assert not result.valid
        # Error should mention the actual value
        assert any("-1" in e for e in result.errors)


class TestConfigIntegration:
    """Integration tests for config loading."""

    def test_get_paper_weight_config_returns_dict(self):
        """Test that get_paper_weight_config returns a dictionary."""
        config = get_paper_weight_config()
        assert isinstance(config, dict)

    def test_get_paper_weight_config_has_dimension_weights(self):
        """Test that loaded config has dimension_weights."""
        config = get_paper_weight_config()
        # Config should have dimension_weights from defaults
        assert "dimension_weights" in config or config == {}
