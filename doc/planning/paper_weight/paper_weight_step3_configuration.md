# Step 3: Configuration Schema - PaperWeightAssessment

## Objective
Add configuration schema for PaperWeightAssessmentAgent to the BMLibrarian config system with reasonable defaults and validation.

## Prerequisites
- Step 1 completed (database migration)
- Step 2 completed (data models implemented)
- Understanding of BMLibrarian's configuration system (`src/bmlibrarian/cli/config.py`)

## Implementation Details

### Configuration File Location
- **Primary:** `~/.bmlibrarian/config.json`
- **Legacy fallback:** `bmlibrarian_config.json` in current directory

### Configuration Structure

Add new section under `agents.paper_weight_assessment`:

```json
{
  "agents": {
    "paper_weight_assessment": {
      "model": "gpt-oss:20b",
      "temperature": 0.3,
      "top_p": 0.9,
      "version": "1.0.0",
      "dimension_weights": {
        "study_design": 0.25,
        "sample_size": 0.15,
        "methodological_quality": 0.30,
        "risk_of_bias": 0.20,
        "replication_status": 0.10
      },
      "study_type_hierarchy": {
        "systematic_review": 10.0,
        "meta_analysis": 10.0,
        "rct": 8.0,
        "cohort_prospective": 6.0,
        "cohort_retrospective": 5.0,
        "case_control": 4.0,
        "cross_sectional": 3.0,
        "case_series": 2.0,
        "case_report": 1.0
      },
      "study_type_keywords": {
        "systematic_review": [
          "systematic review",
          "systematic literature review"
        ],
        "meta_analysis": [
          "meta-analysis",
          "meta analysis",
          "pooled analysis"
        ],
        "rct": [
          "randomized controlled trial",
          "randomised controlled trial",
          "RCT",
          "randomized trial",
          "randomised trial",
          "random allocation",
          "randomly assigned"
        ],
        "cohort_prospective": [
          "prospective cohort",
          "prospective study",
          "longitudinal cohort"
        ],
        "cohort_retrospective": [
          "retrospective cohort",
          "retrospective study"
        ],
        "case_control": [
          "case-control",
          "case control study"
        ],
        "cross_sectional": [
          "cross-sectional",
          "cross sectional study",
          "prevalence study"
        ],
        "case_series": [
          "case series",
          "case-series"
        ],
        "case_report": [
          "case report",
          "case study"
        ]
      },
      "sample_size_scoring": {
        "log_base": 10,
        "log_multiplier": 2.0,
        "power_calculation_bonus": 2.0,
        "ci_reported_bonus": 0.5
      },
      "methodological_quality_weights": {
        "randomization": 2.0,
        "blinding": 3.0,
        "allocation_concealment": 1.5,
        "protocol_preregistration": 1.5,
        "itt_analysis": 1.0,
        "attrition_handling": 1.0
      },
      "risk_of_bias_weights": {
        "selection_bias": 2.5,
        "performance_bias": 2.5,
        "detection_bias": 2.5,
        "reporting_bias": 2.5
      },
      "attrition_thresholds": {
        "excellent": 0.05,
        "good": 0.10,
        "acceptable": 0.20
      }
    }
  }
}
```

## Configuration Parameters Explained

### Core Agent Settings
- **model**: Ollama model to use (default: "gpt-oss:20b" for accuracy)
- **temperature**: LLM temperature (0.3 = more deterministic for scoring)
- **top_p**: Nucleus sampling parameter
- **version**: Assessor version for database versioning (increment when methodology changes)

### Dimension Weights
Controls final weight calculation: `final_weight = sum(dimension_score * weight)`

**Must sum to 1.0**

Default rationale:
- **methodological_quality (0.30)**: Highest weight - execution matters most
- **study_design (0.25)**: Important but not everything
- **risk_of_bias (0.20)**: Critical for validity
- **sample_size (0.15)**: Important but not dominant
- **replication_status (0.10)**: Bonus for replicated findings

### Study Type Hierarchy
Maps study types to baseline scores (0-10 scale)

**Rationale:**
- Systematic reviews/meta-analyses: 10 (highest level of evidence)
- RCTs: 8 (gold standard for causality)
- Cohorts: 5-6 (good observational evidence)
- Case-control: 4 (moderate quality)
- Cross-sectional: 3 (limited temporal information)
- Case series/reports: 1-2 (lowest level)

### Study Type Keywords
Patterns for rule-based study type detection

**Important:** Keywords are case-insensitive and matched against abstract + methods section

### Sample Size Scoring
Formula: `min(10, log10(n) * log_multiplier) + bonuses`

**Parameters:**
- **log_base**: 10 (standard logarithm)
- **log_multiplier**: 2.0 (scales log to 0-10 range)
- **power_calculation_bonus**: +2.0 if power analysis mentioned
- **ci_reported_bonus**: +0.5 if confidence intervals properly reported

**Examples:**
- n=10: log10(10) * 2 = 2.0
- n=100: log10(100) * 2 = 4.0
- n=1000: log10(1000) * 2 = 6.0
- n=10000: log10(10000) * 2 = 8.0
- n=100000: log10(100000) * 2 = 10.0

### Methodological Quality Weights
Sub-component weights for methodological quality dimension (sum to 10.0)

**Components:**
- **randomization (2.0)**: Proper sequence generation?
- **blinding (3.0)**: None(0) / Single(1) / Double(2) / Triple(3)
- **allocation_concealment (1.5)**: Was allocation hidden?
- **protocol_preregistration (1.5)**: Protocol published before study?
- **itt_analysis (1.0)**: Intention-to-treat analysis?
- **attrition_handling (1.0)**: Dropout rate and handling quality

### Risk of Bias Weights
Sub-component weights for risk of bias dimension (sum to 10.0)

**Components (inverted scale: 10=low risk, 0=high risk):**
- **selection_bias (2.5)**: Random sampling, inclusion/exclusion criteria
- **performance_bias (2.5)**: Blinding, standardization of interventions
- **detection_bias (2.5)**: Blinded outcome assessment
- **reporting_bias (2.5)**: Selective outcome reporting, protocol adherence

### Attrition Thresholds
Defines attrition rate quality levels

- **excellent (<5%)**: Full points (1.0)
- **good (5-10%)**: 0.7 points
- **acceptable (10-20%)**: 0.3 points
- **poor (>20%)**: 0.0 points

## Code Integration

### Update `src/bmlibrarian/cli/config.py`

Add default configuration dictionary:

```python
# Add to existing defaults
DEFAULT_PAPER_WEIGHT_CONFIG = {
    "model": "gpt-oss:20b",
    "temperature": 0.3,
    "top_p": 0.9,
    "version": "1.0.0",
    "dimension_weights": {
        "study_design": 0.25,
        "sample_size": 0.15,
        "methodological_quality": 0.30,
        "risk_of_bias": 0.20,
        "replication_status": 0.10
    },
    "study_type_hierarchy": {
        "systematic_review": 10.0,
        "meta_analysis": 10.0,
        "rct": 8.0,
        "cohort_prospective": 6.0,
        "cohort_retrospective": 5.0,
        "case_control": 4.0,
        "cross_sectional": 3.0,
        "case_series": 2.0,
        "case_report": 1.0
    },
    "study_type_keywords": {
        "systematic_review": ["systematic review", "systematic literature review"],
        "meta_analysis": ["meta-analysis", "meta analysis", "pooled analysis"],
        "rct": ["randomized controlled trial", "randomised controlled trial", "RCT", "randomized trial", "randomised trial", "random allocation", "randomly assigned"],
        "cohort_prospective": ["prospective cohort", "prospective study", "longitudinal cohort"],
        "cohort_retrospective": ["retrospective cohort", "retrospective study"],
        "case_control": ["case-control", "case control study"],
        "cross_sectional": ["cross-sectional", "cross sectional study", "prevalence study"],
        "case_series": ["case series", "case-series"],
        "case_report": ["case report", "case study"]
    },
    "sample_size_scoring": {
        "log_base": 10,
        "log_multiplier": 2.0,
        "power_calculation_bonus": 2.0,
        "ci_reported_bonus": 0.5
    },
    "methodological_quality_weights": {
        "randomization": 2.0,
        "blinding": 3.0,
        "allocation_concealment": 1.5,
        "protocol_preregistration": 1.5,
        "itt_analysis": 1.0,
        "attrition_handling": 1.0
    },
    "risk_of_bias_weights": {
        "selection_bias": 2.5,
        "performance_bias": 2.5,
        "detection_bias": 2.5,
        "reporting_bias": 2.5
    },
    "attrition_thresholds": {
        "excellent": 0.05,
        "good": 0.10,
        "acceptable": 0.20
    }
}

def get_default_config():
    """Get default configuration with all agents"""
    return {
        "agents": {
            # ... existing agents ...
            "paper_weight_assessment": DEFAULT_PAPER_WEIGHT_CONFIG
        }
    }
```

### Add Configuration Validation

```python
def validate_paper_weight_config(config: dict) -> bool:
    """
    Validate paper weight assessment configuration.

    Checks:
    - Dimension weights sum to 1.0
    - All scores are in valid range
    - Required keys present

    Args:
        config: Paper weight assessment config dict

    Returns:
        True if valid

    Raises:
        ValueError: If configuration is invalid
    """
    # Check dimension weights sum to 1.0
    weights = config.get("dimension_weights", {})
    weight_sum = sum(weights.values())
    if not (0.99 <= weight_sum <= 1.01):  # Allow small floating point error
        raise ValueError(f"Dimension weights must sum to 1.0, got {weight_sum}")

    # Check all dimension weights are positive
    if any(w < 0 for w in weights.values()):
        raise ValueError("Dimension weights must be non-negative")

    # Check study type hierarchy scores are 0-10
    hierarchy = config.get("study_type_hierarchy", {})
    if any(not (0 <= score <= 10) for score in hierarchy.values()):
        raise ValueError("Study type hierarchy scores must be between 0 and 10")

    # Check methodological quality weights sum to 10.0
    mq_weights = config.get("methodological_quality_weights", {})
    mq_sum = sum(mq_weights.values())
    if not (9.9 <= mq_sum <= 10.1):
        raise ValueError(f"Methodological quality weights must sum to 10.0, got {mq_sum}")

    # Check risk of bias weights sum to 10.0
    rob_weights = config.get("risk_of_bias_weights", {})
    rob_sum = sum(rob_weights.values())
    if not (9.9 <= rob_sum <= 10.1):
        raise ValueError(f"Risk of bias weights must sum to 10.0, got {rob_sum}")

    # Check attrition thresholds are in ascending order
    thresholds = config.get("attrition_thresholds", {})
    if not (thresholds.get("excellent", 0) < thresholds.get("good", 0) < thresholds.get("acceptable", 0)):
        raise ValueError("Attrition thresholds must be in ascending order")

    return True
```

## Creating Example Configuration File

Create `config_examples/paper_weight_assessment_example.json`:

```json
{
  "agents": {
    "paper_weight_assessment": {
      "_comment": "Paper Weight Assessment Agent Configuration",
      "_version_note": "Increment 'version' when methodology changes to trigger re-assessment",

      "model": "gpt-oss:20b",
      "temperature": 0.3,
      "top_p": 0.9,
      "version": "1.0.0",

      "_dimension_weights_note": "Must sum to 1.0. Controls final weight calculation.",
      "dimension_weights": {
        "study_design": 0.25,
        "sample_size": 0.15,
        "methodological_quality": 0.30,
        "risk_of_bias": 0.20,
        "replication_status": 0.10
      },

      "_study_type_hierarchy_note": "Baseline scores (0-10) for different study types",
      "study_type_hierarchy": {
        "systematic_review": 10.0,
        "meta_analysis": 10.0,
        "rct": 8.0,
        "cohort_prospective": 6.0,
        "cohort_retrospective": 5.0,
        "case_control": 4.0,
        "cross_sectional": 3.0,
        "case_series": 2.0,
        "case_report": 1.0
      },

      "_sample_size_scoring_note": "Formula: min(10, log10(n) * log_multiplier) + bonuses",
      "sample_size_scoring": {
        "log_base": 10,
        "log_multiplier": 2.0,
        "power_calculation_bonus": 2.0,
        "ci_reported_bonus": 0.5
      },

      "_methodological_quality_note": "Must sum to 10.0. LLM assesses each component.",
      "methodological_quality_weights": {
        "randomization": 2.0,
        "blinding": 3.0,
        "allocation_concealment": 1.5,
        "protocol_preregistration": 1.5,
        "itt_analysis": 1.0,
        "attrition_handling": 1.0
      },

      "_risk_of_bias_note": "Must sum to 10.0. Inverted: 10=low risk, 0=high risk",
      "risk_of_bias_weights": {
        "selection_bias": 2.5,
        "performance_bias": 2.5,
        "detection_bias": 2.5,
        "reporting_bias": 2.5
      },

      "_attrition_thresholds_note": "Dropout rate quality levels (0.0-1.0)",
      "attrition_thresholds": {
        "excellent": 0.05,
        "good": 0.10,
        "acceptable": 0.20
      }
    }
  }
}
```

## Testing Configuration

### Create Test File: `tests/test_paper_weight_config.py`

```python
"""Tests for paper weight assessment configuration"""

import pytest
from bmlibrarian.cli.config import (
    validate_paper_weight_config,
    DEFAULT_PAPER_WEIGHT_CONFIG
)


def test_default_config_valid():
    """Test that default configuration is valid"""
    assert validate_paper_weight_config(DEFAULT_PAPER_WEIGHT_CONFIG)


def test_dimension_weights_sum():
    """Test dimension weights validation"""
    config = DEFAULT_PAPER_WEIGHT_CONFIG.copy()

    # Valid: sums to 1.0
    assert validate_paper_weight_config(config)

    # Invalid: sums to 0.5
    config["dimension_weights"] = {
        "study_design": 0.1,
        "sample_size": 0.1,
        "methodological_quality": 0.1,
        "risk_of_bias": 0.1,
        "replication_status": 0.1
    }
    with pytest.raises(ValueError, match="must sum to 1.0"):
        validate_paper_weight_config(config)


def test_negative_weights():
    """Test that negative weights are rejected"""
    config = DEFAULT_PAPER_WEIGHT_CONFIG.copy()
    config["dimension_weights"]["study_design"] = -0.1

    with pytest.raises(ValueError, match="must be non-negative"):
        validate_paper_weight_config(config)


def test_study_type_scores_range():
    """Test study type scores are in valid range"""
    config = DEFAULT_PAPER_WEIGHT_CONFIG.copy()
    config["study_type_hierarchy"]["rct"] = 15.0

    with pytest.raises(ValueError, match="between 0 and 10"):
        validate_paper_weight_config(config)


def test_methodological_quality_weights_sum():
    """Test methodological quality weights sum to 10"""
    config = DEFAULT_PAPER_WEIGHT_CONFIG.copy()
    config["methodological_quality_weights"]["randomization"] = 5.0  # Now sums to 13

    with pytest.raises(ValueError, match="must sum to 10.0"):
        validate_paper_weight_config(config)


def test_attrition_thresholds_order():
    """Test attrition thresholds are in ascending order"""
    config = DEFAULT_PAPER_WEIGHT_CONFIG.copy()
    config["attrition_thresholds"] = {
        "excellent": 0.20,  # Wrong order
        "good": 0.10,
        "acceptable": 0.05
    }

    with pytest.raises(ValueError, match="ascending order"):
        validate_paper_weight_config(config)
```

### Run Tests
```bash
uv run python -m pytest tests/test_paper_weight_config.py -v
```

## Configuration Access in Agent

### Helper Function in PaperWeightAssessmentAgent

```python
def _load_config(self) -> dict:
    """Load paper weight assessment configuration"""
    from bmlibrarian.cli.config import get_agent_config, validate_paper_weight_config

    config = get_agent_config("paper_weight_assessment")
    validate_paper_weight_config(config)
    return config

def _get_dimension_weights(self) -> dict:
    """Get dimension weights from config"""
    return self.config.get("dimension_weights", {
        "study_design": 0.25,
        "sample_size": 0.15,
        "methodological_quality": 0.30,
        "risk_of_bias": 0.20,
        "replication_status": 0.10
    })
```

## Success Criteria
- [ ] Configuration section added to default config
- [ ] All parameters documented with comments
- [ ] Validation function implemented
- [ ] Validation tests passing
- [ ] Example configuration file created
- [ ] Configuration properly integrated with config.py
- [ ] Dimension weights sum to 1.0
- [ ] Methodological quality weights sum to 10.0
- [ ] Risk of bias weights sum to 10.0
- [ ] All scores in valid ranges (0-10)

## Notes for Future Reference
- **Versioning:** Increment `version` field when methodology changes to trigger re-assessment of cached papers
- **Weight Tuning:** These are starting weights based on expert judgment. Battle testing will reveal if adjustments needed.
- **Keyword Expansion:** Study type keywords can be expanded based on missed classifications
- **Temperature Setting:** 0.3 provides good balance between determinism and reasoning quality

## Next Step
After configuration is complete and tested, proceed to **Step 4: PaperWeightAssessmentAgent - Rule-Based Extractors**.
