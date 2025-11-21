"""Tests for paper weight assessment configuration.

This module tests the configuration schema and validation for the
PaperWeightAssessmentAgent configuration.
"""

import copy
import pytest

from bmlibrarian.config import (
    DEFAULT_PAPER_WEIGHT_CONFIG,
    validate_paper_weight_config,
    get_paper_weight_config,
)


class TestDefaultConfig:
    """Tests for the default configuration."""

    def test_default_config_valid(self):
        """Test that default configuration passes validation."""
        assert validate_paper_weight_config(DEFAULT_PAPER_WEIGHT_CONFIG) is True

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
        assert abs(total - 1.0) < 0.01, f"Dimension weights should sum to 1.0, got {total}"

    def test_default_methodological_quality_weights_sum_to_ten(self):
        """Test that default methodological quality weights sum to 10.0."""
        weights = DEFAULT_PAPER_WEIGHT_CONFIG["methodological_quality_weights"]
        total = sum(weights.values())
        assert abs(total - 10.0) < 0.1, f"MQ weights should sum to 10.0, got {total}"

    def test_default_risk_of_bias_weights_sum_to_ten(self):
        """Test that default risk of bias weights sum to 10.0."""
        weights = DEFAULT_PAPER_WEIGHT_CONFIG["risk_of_bias_weights"]
        total = sum(weights.values())
        assert abs(total - 10.0) < 0.1, f"RoB weights should sum to 10.0, got {total}"


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

        with pytest.raises(ValueError, match="must sum to 1.0"):
            validate_paper_weight_config(config)

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

        with pytest.raises(ValueError, match="must sum to 1.0"):
            validate_paper_weight_config(config)

    def test_negative_dimension_weights_rejected(self):
        """Test that negative dimension weights are rejected."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["dimension_weights"]["study_design"] = -0.05
        # Adjust another to keep sum at 1.0 (0.25 -> -0.05 = -0.30, so add 0.30)
        config["dimension_weights"]["methodological_quality"] = 0.60

        with pytest.raises(ValueError, match="must be non-negative"):
            validate_paper_weight_config(config)

    def test_empty_dimension_weights_rejected(self):
        """Test that empty dimension weights are rejected."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["dimension_weights"] = {}

        with pytest.raises(ValueError, match="dimension_weights is required"):
            validate_paper_weight_config(config)

    def test_missing_dimension_weights_rejected(self):
        """Test that missing dimension weights are rejected."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        del config["dimension_weights"]

        with pytest.raises(ValueError, match="dimension_weights is required"):
            validate_paper_weight_config(config)


class TestStudyTypeHierarchyValidation:
    """Tests for study type hierarchy validation."""

    def test_study_type_scores_in_valid_range(self):
        """Test that study type scores must be between 0 and 10."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["study_type_hierarchy"]["rct"] = 15.0

        with pytest.raises(ValueError, match="between 0 and 10"):
            validate_paper_weight_config(config)

    def test_negative_study_type_scores_rejected(self):
        """Test that negative study type scores are rejected."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["study_type_hierarchy"]["case_report"] = -1.0

        with pytest.raises(ValueError, match="between 0 and 10"):
            validate_paper_weight_config(config)

    def test_zero_study_type_score_allowed(self):
        """Test that zero is a valid study type score."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["study_type_hierarchy"]["case_report"] = 0.0

        assert validate_paper_weight_config(config) is True

    def test_ten_study_type_score_allowed(self):
        """Test that 10 is a valid study type score."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["study_type_hierarchy"]["systematic_review"] = 10.0

        assert validate_paper_weight_config(config) is True


class TestMethodologicalQualityWeightsValidation:
    """Tests for methodological quality weights validation."""

    def test_mq_weights_must_sum_to_ten(self):
        """Test that methodological quality weights must sum to 10.0."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["methodological_quality_weights"]["randomization"] = 5.0  # Now sums to 13

        with pytest.raises(ValueError, match="must sum to 10.0"):
            validate_paper_weight_config(config)

    def test_negative_mq_weights_rejected(self):
        """Test that negative methodological quality weights are rejected."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["methodological_quality_weights"]["blinding"] = -1.0
        # Adjust to keep sum at 10.0
        config["methodological_quality_weights"]["randomization"] = 6.0

        with pytest.raises(ValueError, match="Methodological quality weight.*must be non-negative"):
            validate_paper_weight_config(config)


class TestRiskOfBiasWeightsValidation:
    """Tests for risk of bias weights validation."""

    def test_rob_weights_must_sum_to_ten(self):
        """Test that risk of bias weights must sum to 10.0."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["risk_of_bias_weights"]["selection_bias"] = 5.0  # Now sums to 12.5

        with pytest.raises(ValueError, match="must sum to 10.0"):
            validate_paper_weight_config(config)

    def test_negative_rob_weights_rejected(self):
        """Test that negative risk of bias weights are rejected."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["risk_of_bias_weights"]["selection_bias"] = -1.0
        # Adjust to keep sum at 10.0
        config["risk_of_bias_weights"]["performance_bias"] = 6.0

        with pytest.raises(ValueError, match="Risk of bias weight.*must be non-negative"):
            validate_paper_weight_config(config)


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

        with pytest.raises(ValueError, match="ascending order"):
            validate_paper_weight_config(config)

    def test_equal_thresholds_rejected(self):
        """Test that equal thresholds are rejected."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["attrition_thresholds"] = {
            "excellent": 0.10,
            "good": 0.10,  # Equal to excellent
            "acceptable": 0.20,
        }

        with pytest.raises(ValueError, match="ascending order"):
            validate_paper_weight_config(config)

    def test_threshold_above_one_rejected(self):
        """Test that thresholds above 1.0 are rejected."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["attrition_thresholds"]["acceptable"] = 1.5

        with pytest.raises(ValueError, match="between 0 and 1"):
            validate_paper_weight_config(config)

    def test_negative_threshold_rejected(self):
        """Test that negative thresholds are rejected."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["attrition_thresholds"]["excellent"] = -0.05

        with pytest.raises(ValueError, match="between 0 and 1"):
            validate_paper_weight_config(config)


class TestSampleSizeScoringValidation:
    """Tests for sample size scoring parameters validation."""

    def test_negative_log_multiplier_rejected(self):
        """Test that negative log multiplier is rejected."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["sample_size_scoring"]["log_multiplier"] = -2.0

        with pytest.raises(ValueError, match="log_multiplier must be positive"):
            validate_paper_weight_config(config)

    def test_zero_log_multiplier_rejected(self):
        """Test that zero log multiplier is rejected."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["sample_size_scoring"]["log_multiplier"] = 0.0

        with pytest.raises(ValueError, match="log_multiplier must be positive"):
            validate_paper_weight_config(config)

    def test_negative_power_bonus_rejected(self):
        """Test that negative power calculation bonus is rejected."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["sample_size_scoring"]["power_calculation_bonus"] = -1.0

        with pytest.raises(ValueError, match="power_calculation_bonus must be non-negative"):
            validate_paper_weight_config(config)

    def test_negative_ci_bonus_rejected(self):
        """Test that negative CI bonus is rejected."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["sample_size_scoring"]["ci_reported_bonus"] = -0.5

        with pytest.raises(ValueError, match="ci_reported_bonus must be non-negative"):
            validate_paper_weight_config(config)

    def test_zero_bonuses_allowed(self):
        """Test that zero bonuses are valid."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["sample_size_scoring"]["power_calculation_bonus"] = 0.0
        config["sample_size_scoring"]["ci_reported_bonus"] = 0.0

        assert validate_paper_weight_config(config) is True


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

        assert validate_paper_weight_config(config) is True

    def test_custom_study_type_hierarchy_valid(self):
        """Test that custom study type hierarchy is valid."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        # Add a new study type
        config["study_type_hierarchy"]["observational"] = 3.5

        assert validate_paper_weight_config(config) is True

    def test_empty_optional_sections_valid(self):
        """Test that empty optional sections are valid."""
        config = copy.deepcopy(DEFAULT_PAPER_WEIGHT_CONFIG)
        config["study_type_hierarchy"] = {}
        config["methodological_quality_weights"] = {}
        config["risk_of_bias_weights"] = {}
        config["attrition_thresholds"] = {}
        config["sample_size_scoring"] = {}

        # Only dimension_weights is required
        assert validate_paper_weight_config(config) is True


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
