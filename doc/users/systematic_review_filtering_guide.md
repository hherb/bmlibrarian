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

## Performance Characteristics

The filtering system is designed to handle large document sets efficiently:

### Processing Speed

| Dataset Size | Expected Throughput | Notes |
|--------------|---------------------|-------|
| **Small** (<1000 papers) | ~1000 papers/second | Near-instant results |
| **Medium** (1000-10,000) | ~700-1000 papers/second | Completes in seconds |
| **Large** (>10,000) | ~500-800 papers/second | Batch processing recommended |

### Optimization Features

The filter uses several optimizations for performance:

1. **Pre-compiled Regex Patterns** - Title patterns are compiled once at initialization
2. **Pattern Caching** - Common keyword patterns are cached with LRU cache (256 entries)
3. **Early Exit Evaluation** - Stops checking once a rejection criterion is met
4. **Minimal Memory Footprint** - Processes papers in streaming fashion

### Performance Tips

**For Large Datasets (>5000 papers):**
- Use batch processing with `filter_batch()` instead of individual calls
- Consider processing in parallel batches if your system has multiple cores
- Monitor memory usage with very large keyword sets (>500 keywords)

**For Complex Criteria:**
- Simpler exclusion criteria (2-5 keywords per criterion) perform better than complex multi-clause statements
- Use standard study type filters when possible instead of custom keywords
- Pre-compile custom regex patterns if you need advanced matching

### Confidence Levels

The filter assigns confidence scores to help you understand decision quality:

| Confidence Level | Range | Meaning |
|------------------|-------|---------|
| **High** | 0.85-1.0 | Definitive pattern match (e.g., "Case Report:" in title) |
| **Medium** | 0.6-0.85 | Keyword-based match with context checking |
| **Low** | 0.0-0.6 | Uncertain decision, may need review |

**Confidence Thresholds:**
- Exclusion keyword matches: 0.85 (HIGH)
- Study type keyword matches: 0.6 (MEDIUM)

Papers with LOW confidence (<0.6) should be manually reviewed to ensure accuracy.

### Regex Pattern Customization

For advanced users who need custom matching patterns:

```python
from bmlibrarian.agents.systematic_review.filters import (
    _compile_negative_context_pattern,
)

# Custom patterns are automatically cached for performance
# Pattern template uses {keyword} placeholder for substitution
pattern = _compile_negative_context_pattern(
    r"exclud(?:ed|ing)\s+(?:\w+\s+)*{keyword}",
    "case reports"
)

# Check cache performance
cache_info = _compile_negative_context_pattern.cache_info()
print(f"Cache hits: {cache_info.hits}, misses: {cache_info.misses}")
```

**Pattern Best Practices:**
- Test patterns thoroughly before deploying
- Use raw strings (r"pattern") to avoid escaping issues
- Keep patterns focused - simpler patterns match faster
- Keywords are automatically escaped for regex safety

### Common Performance Questions

**Q: Why is my first batch slow?**
A: The first batch compiles and caches patterns. Subsequent batches will be much faster due to caching.

**Q: How many custom keywords can I add?**
A: Up to ~1000 keywords should perform well. Beyond that, consider grouping similar terms or using regex patterns.

**Q: Can I process papers in parallel?**
A: Yes, the filter is thread-safe. You can process different batches concurrently using threading.

**Q: What's the maximum abstract length supported?**
A: No hard limit. Abstracts up to 10,000 words have been tested and perform well (<1s per paper).

## Related Documentation

- [Systematic Review Agent Overview](systematic_review_guide.md)
- [Relevance Scoring Guide](systematic_review_scoring_guide.md)
- [Search Strategy Guide](systematic_review_search_guide.md)
