# Cochrane Assessment System - Developer Documentation

## Architecture Overview

The Cochrane Assessment system provides Cochrane Handbook-compliant study characterization and risk of bias assessment. It consists of three main components:

```
cochrane_models.py     - Data models for Cochrane-aligned output
cochrane_formatter.py  - Formatting utilities for Markdown/HTML output
cochrane_assessor.py   - LLM agent for extracting Cochrane fields
```

## Data Models (`cochrane_models.py`)

### Risk of Bias Models

```python
@dataclass
class RiskOfBiasItem:
    """Single risk of bias domain assessment."""
    domain: str                    # e.g., "Random sequence generation"
    bias_type: str                 # e.g., "selection bias"
    judgement: str                 # "Low risk", "High risk", "Unclear risk"
    support_for_judgement: str     # Explanation text
    outcome_type: Optional[str]    # For detection bias: "subjective" or "objective"

@dataclass
class CochraneRiskOfBias:
    """Complete Cochrane Risk of Bias assessment with 9 domains."""
    random_sequence_generation: RiskOfBiasItem
    allocation_concealment: RiskOfBiasItem
    baseline_outcome_measurements: RiskOfBiasItem
    baseline_characteristics: RiskOfBiasItem
    blinding_participants_personnel: RiskOfBiasItem
    blinding_outcome_assessment_subjective: RiskOfBiasItem
    blinding_outcome_assessment_objective: RiskOfBiasItem
    incomplete_outcome_data: RiskOfBiasItem
    selective_reporting: RiskOfBiasItem
```

### Study Characteristics Models

```python
@dataclass
class CochraneParticipants:
    """Participants section of Cochrane characteristics."""
    setting: str
    population: str
    inclusion_criteria: Optional[List[str]]
    exclusion_criteria: Optional[List[str]]
    total_participants: Optional[int]
    group_sizes: Optional[Dict[str, int]]
    baseline_characteristics_reported: bool

@dataclass
class CochraneInterventions:
    """Interventions section."""
    description: str
    intervention_groups: Optional[List[str]]
    control_description: Optional[str]
    duration: Optional[str]

@dataclass
class CochraneOutcomes:
    """Outcomes section."""
    description: str
    primary_outcomes: Optional[List[str]]
    secondary_outcomes: Optional[List[str]]
    outcome_timepoints: Optional[List[str]]

@dataclass
class CochraneNotes:
    """Notes section."""
    follow_up_periods: Optional[List[str]]
    funding_source: Optional[str]
    conflicts_of_interest: Optional[str]
    ethical_approval: Optional[str]
    trial_registration: Optional[str]
    publication_status: Optional[str]

@dataclass
class CochraneStudyCharacteristics:
    """Complete study characteristics table."""
    study_id: str          # e.g., "Smith 2023"
    methods: str           # Study design
    participants: CochraneParticipants
    interventions: CochraneInterventions
    outcomes: CochraneOutcomes
    notes: CochraneNotes
    # Metadata
    document_id: Optional[int]
    document_title: Optional[str]
    pmid: Optional[str]
    doi: Optional[str]
```

### Complete Assessment

```python
@dataclass
class CochraneStudyAssessment:
    """Complete Cochrane-aligned assessment."""
    study_characteristics: CochraneStudyCharacteristics
    risk_of_bias: CochraneRiskOfBias
    # Additional metadata (superset of Cochrane requirements)
    overall_quality_score: Optional[float]  # 0-10
    overall_confidence: Optional[float]     # 0-1
    evidence_level: Optional[str]
    assessment_notes: Optional[List[str]]
    assessment_version: str = "2.0.0"
```

## Formatter (`cochrane_formatter.py`)

### Markdown Formatters

```python
def format_study_characteristics_markdown(
    study_chars: CochraneStudyCharacteristics
) -> str:
    """Format study characteristics as Markdown table."""

def format_risk_of_bias_markdown(
    rob: CochraneRiskOfBias
) -> str:
    """Format risk of bias as Markdown table."""

def format_complete_assessment_markdown(
    assessment: CochraneStudyAssessment
) -> str:
    """Format complete assessment as Markdown."""

def format_multiple_assessments_markdown(
    assessments: List[CochraneStudyAssessment],
    title: str = "Characteristics of included studies"
) -> str:
    """Format multiple assessments as single Markdown document."""

def format_risk_of_bias_summary_markdown(
    assessments: List[CochraneStudyAssessment]
) -> str:
    """Format risk of bias summary table across all studies."""
```

### HTML Formatters

```python
def format_study_characteristics_html(
    study_chars: CochraneStudyCharacteristics
) -> str:
    """Format study characteristics as HTML table."""

def format_risk_of_bias_html(
    rob: CochraneRiskOfBias
) -> str:
    """Format risk of bias as HTML table."""

def get_cochrane_css() -> str:
    """Get CSS stylesheet for Cochrane HTML output."""
```

## Assessment Agent (`cochrane_assessor.py`)

### CochraneAssessmentAgent

```python
class CochraneAssessmentAgent(BaseAgent):
    """Agent for generating Cochrane-aligned study assessments."""

    VERSION = "1.0.0"

    def assess_document(
        self,
        document: Dict[str, Any],
        min_confidence: float = 0.4,
    ) -> Optional[CochraneStudyAssessment]:
        """Assess a document using Cochrane standards."""

    def assess_batch(
        self,
        documents: List[Dict[str, Any]],
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> List[CochraneStudyAssessment]:
        """Assess multiple documents."""

    def format_assessment_markdown(
        self, assessment: CochraneStudyAssessment
    ) -> str:
        """Format a single assessment as Markdown."""

    def format_multiple_assessments_markdown(
        self,
        assessments: List[CochraneStudyAssessment],
        title: str = "Characteristics of included studies",
    ) -> str:
        """Format multiple assessments as Markdown document."""
```

### Prompt Engineering

The agent uses a carefully structured prompt that:
1. Requests all Cochrane-required fields
2. Specifies exact judgement values ("Low risk", "High risk", "Unclear risk")
3. Requires support text for each bias domain
4. Outputs structured JSON

Key prompt sections:
- Study characteristics extraction (5 sections)
- Risk of bias assessment (9 domains with explicit criteria)
- Overall assessment metadata

## Integration Points

### With SystematicReviewAgent

The Cochrane assessment can be integrated into the systematic review workflow:

```python
# In quality.py, after existing assessments
if self._config.run_cochrane_assessment:
    cochrane_assessment = self._run_cochrane_assessment(document)
```

### With Reporter

The Reporter class includes methods for Cochrane output:

```python
def generate_cochrane_characteristics_report(
    self,
    cochrane_assessments: List[CochraneStudyAssessment],
    output_path: str,
    format_type: str = "markdown",  # or "html"
) -> None:
    """Generate Cochrane-style report."""

def generate_risk_of_bias_summary(
    self,
    cochrane_assessments: List[CochraneStudyAssessment],
    output_path: str,
) -> None:
    """Generate risk of bias summary table."""
```

## Comparison with Previous StudyAssessmentAgent

| Feature | StudyAssessmentAgent | CochraneAssessmentAgent |
|---------|---------------------|-------------------------|
| Risk of Bias domains | 5 (aggregated) | 9 (Cochrane standard) |
| RoB judgement | "low/moderate/high/unclear" | "Low risk/High risk/Unclear risk" |
| RoB support text | No | Yes (required) |
| Study characteristics | Basic | Full Cochrane table |
| Participants section | sample_size only | Setting, population, groups |
| Interventions | No | Yes |
| Outcomes | No | Yes |
| Notes (funding, etc.) | follow_up only | Full Cochrane notes |

## Factory Functions

```python
def create_default_risk_of_bias_item(
    domain: str,
    bias_type: str,
    outcome_type: Optional[str] = None
) -> RiskOfBiasItem:
    """Create RiskOfBiasItem with "Unclear risk" default."""

def create_default_cochrane_risk_of_bias() -> CochraneRiskOfBias:
    """Create CochraneRiskOfBias with all domains unclear."""
```

## Testing

```python
# Test imports
from bmlibrarian.agents.systematic_review import (
    CochraneAssessmentAgent,
    CochraneStudyAssessment,
    CochraneRiskOfBias,
    format_complete_assessment_markdown,
)

# Test data model creation
rob = create_default_cochrane_risk_of_bias()
assert len(rob.to_list()) == 9

# Test formatting
markdown = format_risk_of_bias_markdown(rob)
assert "Random sequence generation" in markdown
```

## Version History

- **2.0.0**: Initial Cochrane-aligned release
  - 9 RoB domains with judgement + support
  - Full study characteristics table
  - Markdown and HTML output formats
  - Risk of bias summary across studies
