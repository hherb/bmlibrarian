# Cochrane Assessment Guide

## Overview

The Cochrane Assessment system provides Cochrane Handbook-compliant study characterization and risk of bias assessment for systematic reviews. The output format matches the standard Cochrane template exactly, ensuring nothing required by systematic review standards is missing.

## Features

### Study Characteristics Table

Extracts five key components as required by Cochrane:

| Section | Description |
|---------|-------------|
| **Methods** | Study design (e.g., "Parallel randomised trial") |
| **Participants** | Setting, population, inclusion criteria, sample sizes |
| **Interventions** | Description of intervention(s) and control |
| **Outcomes** | Primary and secondary outcomes measured |
| **Notes** | Follow-up, funding, conflicts of interest, ethics |

### Risk of Bias Assessment

Nine Cochrane domains with judgement and support text:

| Domain | Bias Type |
|--------|-----------|
| Random sequence generation | Selection bias |
| Allocation concealment | Selection bias |
| Baseline outcome measurements | Selection bias |
| Baseline characteristics | Selection bias |
| Blinding of participants and personnel | Performance bias |
| Blinding of outcome assessment (subjective) | Detection bias |
| Blinding of outcome assessment (objective) | Detection bias |
| Incomplete outcome data | Attrition bias |
| Selective reporting | Reporting bias |

Each domain includes:
- **Judgement**: "Low risk", "High risk", or "Unclear risk"
- **Support for judgement**: Explanation text

## Usage

### Basic Usage

```python
from bmlibrarian.agents.systematic_review import CochraneAssessmentAgent

# Initialize the agent
agent = CochraneAssessmentAgent()

# Assess a single document
document = {
    "id": 12345,
    "title": "Randomized trial of statin therapy...",
    "abstract": "Background: ...",
    "authors": ["Smith J", "Johnson A"],
    "year": 2023,
    "pmid": "12345678",
    "doi": "10.1000/example"
}

assessment = agent.assess_document(document)

# Format as Markdown
markdown = agent.format_assessment_markdown(assessment)
print(markdown)
```

### Batch Assessment

```python
# Assess multiple documents
documents = [doc1, doc2, doc3]

def progress_callback(current, total, title):
    print(f"Assessing {current}/{total}: {title}")

assessments = agent.assess_batch(
    documents,
    progress_callback=progress_callback
)

# Format all assessments as a single document
full_report = agent.format_multiple_assessments_markdown(
    assessments,
    title="Characteristics of included studies"
)
```

### Risk of Bias Summary

```python
# Generate summary table across all studies
summary = agent.format_risk_of_bias_summary(assessments)
print(summary)
```

### Using with Reporter

```python
from bmlibrarian.agents.systematic_review import Reporter, Documenter

documenter = Documenter(review_id="SR001")
reporter = Reporter(documenter)

# Generate Cochrane characteristics report
reporter.generate_cochrane_characteristics_report(
    cochrane_assessments=assessments,
    output_path="characteristics_of_studies.md",
    format_type="markdown"  # or "html"
)

# Generate risk of bias summary
reporter.generate_risk_of_bias_summary(
    cochrane_assessments=assessments,
    output_path="risk_of_bias_summary.md"
)
```

## Output Format Examples

### Study Characteristics Table (Markdown)

```markdown
### Smith 2023

*Study characteristics*

| **Characteristic** | **Description** |
|---|---|
| Methods | Parallel randomised trial |
| Participants | Setting: United States |
| | Adults with hypercholesterolemia (N=500) |
| Interventions | High-intensity statin therapy vs placebo |
| Outcomes | Primary: Major cardiovascular events |
| Notes | Follow-up at 1, 2, 3, and 5 years |
| | Funding: National Heart Institute |
```

### Risk of Bias Table (Markdown)

```markdown
*Risk of bias*

| **Bias** | **Authors' judgement** | **Support for judgement** |
|---|---|---|
| Random sequence generation (selection bias) | Low risk | Computer-generated random sequence |
| Allocation concealment (selection bias) | Low risk | Central allocation with sealed envelopes |
| Blinding of participants and personnel (performance bias) | Low risk | Double-blind placebo-controlled design |
| ... | ... | ... |
```

### Risk of Bias Summary (Across Studies)

```markdown
## Risk of Bias Summary

| Domain | Smith 2023 | Jones 2022 | Lee 2021 |
|---|---|---|---|
| Random sequence generation (selection bias) | + | + | ? |
| Allocation concealment (selection bias) | + | ? | - |
| ... | ... | ... | ... |

**Legend:** + Low risk | - High risk | ? Unclear risk
```

## Configuration

The Cochrane assessment agent uses the standard BMLibrarian configuration:

```json
{
  "agents": {
    "cochrane_assessment": {
      "model": "gpt-oss:20b",
      "temperature": 0.1,
      "top_p": 0.9
    }
  }
}
```

## Integration with Systematic Review Workflow

The Cochrane assessment integrates with the SystematicReviewAgent:

```python
from bmlibrarian.agents.systematic_review import (
    SystematicReviewAgent,
    CochraneAssessmentAgent,
    SearchCriteria,
)

# Run systematic review
sr_agent = SystematicReviewAgent()
result = sr_agent.run_review(criteria=criteria)

# Get Cochrane assessments for included papers
cochrane_agent = CochraneAssessmentAgent()
cochrane_assessments = cochrane_agent.assess_batch(
    [p["paper"] for p in result.included_papers]
)

# Generate Cochrane-compliant report
reporter = sr_agent.get_reporter()
reporter.generate_cochrane_characteristics_report(
    cochrane_assessments,
    "characteristics_of_included_studies.md"
)
```

## Best Practices

1. **Use full text when available**: The agent produces better assessments when full text is provided rather than just abstracts.

2. **Review "Unclear risk" judgements**: When information is not reported in the text, the agent marks it as "Unclear risk". Human review may be able to find additional information.

3. **Verify study IDs**: The agent generates study IDs in "Author Year" format. Verify these match your citation style.

4. **Check for completeness**: The agent extracts only what is present in the text. Missing information indicates gaps in the original publication, not assessment errors.

## Troubleshooting

### "Not reported" in multiple fields

This indicates the source text (abstract or full text) doesn't contain the required information. This is common for abstract-only publications.

### Inconsistent study types

The agent classifies study types based on reported methodology. If the classification seems wrong, check the methods section of the source document.

### Low confidence scores

Confidence below 0.5 indicates the agent had difficulty extracting information. This often happens with:
- Short abstracts
- Non-interventional studies
- Methodology-focused papers without primary data

## Reference

- [Cochrane Handbook for Systematic Reviews](https://training.cochrane.org/handbook)
- [Cochrane Risk of Bias Tool](https://methods.cochrane.org/bias/resources/rob-2-revised-cochrane-risk-bias-tool-randomized-trials)
