# Systematic Review Filtering Guide

This guide explains how the SystematicReviewAgent filters papers to identify relevant studies for your systematic review.

## Overview

When conducting a systematic review, you typically start with thousands of search results that need to be narrowed down to relevant studies. BMLibrarian uses a two-stage filtering process:

1. **Initial Filter** - Fast automated screening based on title, abstract, and metadata
2. **Inclusion Evaluator** - AI-powered evaluation against your specific criteria

## How Initial Filtering Works

### What Gets Filtered Out

The initial filter removes papers that are clearly outside your scope:

| Filter Type | Examples |
|-------------|----------|
| **Date Range** | Papers outside your specified year range |
| **Study Type** | Case reports, editorials, letters, commentaries |
| **Research Type** | Animal studies, in vitro studies, cell culture |
| **Document Type** | Retracted articles, errata, protocols |
| **Content** | Papers with missing or very short abstracts |

### Context-Aware Filtering

The filter is smart enough to understand context. It won't incorrectly reject:

- **Systematic reviews** that mention "we excluded case reports"
- **Human studies** that reference "prior animal experiments"
- **Meta-analyses** that compare "human vs animal findings"

This prevents false positives where good papers mention excluded study types in passing.

## Defining Your Criteria

When setting up your systematic review, you specify:

### Inclusion Criteria

What papers MUST have to be included:

```python
inclusion_criteria = [
    "Human studies",
    "Randomized controlled trial or cohort study",
    "Cardiovascular disease outcomes measured",
]
```

### Exclusion Criteria

What automatically excludes a paper:

```python
exclusion_criteria = [
    "Animal studies",
    "Pediatric-only populations (under 18)",
    "Case reports or case series",
    "Conference abstracts only",
]
```

### Study Types

Which study designs to include:

```python
from bmlibrarian.agents.systematic_review import StudyTypeFilter

target_study_types = [
    StudyTypeFilter.RCT,
    StudyTypeFilter.SYSTEMATIC_REVIEW,
    StudyTypeFilter.META_ANALYSIS,
    StudyTypeFilter.COHORT_PROSPECTIVE,
]
```

### Date Range

Publication year range:

```python
date_range = (2010, 2024)  # Papers from 2010-2024 inclusive
```

## Understanding Filter Results

### FilterResult

Each filtered paper returns:

| Field | Description |
|-------|-------------|
| `passed` | True/False - whether paper passed |
| `reason` | Why the paper was accepted/rejected |
| `stage` | Which filtering stage made the decision |
| `confidence` | How confident the filter is (0-1) |

### BatchFilterResult

For batch filtering:

| Field | Description |
|-------|-------------|
| `passed` | List of papers that passed |
| `rejected` | List of (paper, reason) tuples |
| `pass_rate` | Percentage of papers that passed |
| `execution_time_seconds` | How long filtering took |

## Customizing Exclusion Keywords

You can add custom keywords to exclude:

```python
from bmlibrarian.agents.systematic_review import InitialFilter

filter_obj = InitialFilter(
    criteria,
    custom_exclusion_keywords=[
        "simulation study",
        "theoretical model",
        "computational analysis",
    ]
)
```

## AI-Powered Inclusion Evaluation

Papers that pass the initial filter are evaluated by an AI against your explicit criteria. The AI:

1. Reads the title and abstract carefully
2. Checks each inclusion criterion
3. Checks each exclusion criterion
4. Makes a decision: **INCLUDE**, **EXCLUDE**, or **UNCERTAIN**
5. Provides detailed rationale

### Understanding AI Decisions

| Status | Meaning |
|--------|---------|
| **INCLUDED** | Meets all inclusion criteria, no exclusion criteria matched |
| **EXCLUDED** | Failed an inclusion criterion OR matched an exclusion criterion |
| **UNCERTAIN** | Borderline case - needs human review |

## Tips for Better Filtering

### Be Specific in Criteria

Instead of:
> "Good quality studies"

Use:
> "Randomized controlled trials with sample size ≥100 participants"

### Use Standard Terminology

The filter recognizes standard study type terms:
- "randomized controlled trial" or "RCT"
- "systematic review"
- "meta-analysis"
- "cohort study"
- "case-control study"

### Consider Edge Cases

If you want to include studies that compare human and animal results, make this explicit:
> "Human studies (may include comparative discussion of animal findings)"

## Interpreting Statistics

After filtering, you'll see statistics like:

```
Initial Filter Results:
- Total papers: 1,247
- Passed: 342 (27.4%)
- Rejected: 905 (72.6%)

Rejection breakdown:
- Date range: 156 papers
- Exclusion keywords: 523 papers
- Study type: 187 papers
- Insufficient content: 39 papers
```

A pass rate of 20-40% is typical for well-designed search strategies. Very high (>60%) or very low (<10%) rates may indicate:
- **High rate**: Search terms too specific, may miss relevant papers
- **Low rate**: Search terms too broad, consider refining

## Troubleshooting

### Papers Being Incorrectly Rejected

If you notice relevant papers being rejected:

1. Check the rejection reason in the results
2. Look for keywords that might trigger false positives
3. Consider if the paper mentions excluded study types in context
4. Review your exclusion criteria for unintended matches

### Too Many Papers Passing

If too many irrelevant papers pass the initial filter:

1. Add more specific exclusion keywords
2. Narrow your date range
3. Be more specific in study type requirements
4. Consider adding custom exclusion keywords

## Related Documentation

- [Systematic Review Agent Overview](systematic_review_guide.md)
- [Relevance Scoring Guide](systematic_review_scoring_guide.md)
- [Search Strategy Guide](systematic_review_search_guide.md)
