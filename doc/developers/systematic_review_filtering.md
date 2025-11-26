# Systematic Review Filtering System

This document describes the filtering architecture for the SystematicReviewAgent, specifically the InitialFilter and InclusionEvaluator components from Phase 3.

## Overview

The filtering system uses a **two-tier approach** to eliminate irrelevant papers efficiently:

1. **InitialFilter** - Fast heuristic-based filtering using keywords, patterns, and date ranges
2. **InclusionEvaluator** - LLM-based evaluation against explicit inclusion/exclusion criteria

This design ensures expensive LLM evaluations are only applied to papers that pass fast heuristics first.

## Architecture

```
Papers from Search
       │
       ▼
┌─────────────────┐
│  InitialFilter  │  Fast heuristic checks (~ms per paper)
│                 │  - Date range validation
│                 │  - Definitive title patterns
│                 │  - Context-aware keyword matching
│                 │  - Minimum content requirements
└────────┬────────┘
         │ Passed papers only
         ▼
┌─────────────────┐
│InclusionEvaluator│  LLM-based evaluation (~seconds per paper)
│                 │  - Explicit criteria checking
│                 │  - Detailed rationale generation
│                 │  - Confidence scoring
└────────┬────────┘
         │
         ▼
    Included Papers
```

## InitialFilter: Context-Aware Filtering

### Problem Statement

Simple keyword matching produces false positives in common scenarios:
- A systematic review stating "we excluded case reports" would be incorrectly rejected
- A human clinical trial mentioning "prior animal experiments" would be incorrectly rejected
- A meta-analysis comparing human and animal findings would be incorrectly rejected

### Solution: Multi-Tier Context-Aware Filtering

The InitialFilter uses a three-tier approach:

#### Tier 1: Definitive Title Patterns

High-confidence regex patterns that definitively indicate excluded study types based on title structure:

```python
DEFINITIVE_TITLE_PATTERNS = [
    r"^case report[:\s]",     # "Case Report: Rare Complication..."
    r"^a case of\b",          # "A case of severe reaction..."
    r"\bin rats\b",           # "Treatment Effects in Rats"
    r"\bin mice\b",           # "Neuroprotection in Mice"
    r"^editorial[:\s]",       # "Editorial: Future Directions..."
    r"\bretracted\b$",        # "Original Title RETRACTED"
]
```

**When matched**: Paper is immediately rejected with high confidence.

#### Tier 2: Negative Context Pattern Detection

Before rejecting on keyword matches, the filter checks if the keyword appears in a protective context:

```python
NEGATIVE_CONTEXT_PATTERNS = [
    # Exclusion statements
    r"(?:we |were |was )?exclud(?:ed|ing)\s+(?:\w+\s+)*{keyword}",
    r"{keyword}\s+(?:\w+\s+)?(?:were|was)\s+(?:\w+\s+)?excluded",

    # Comparative statements
    r"unlike\s+(?:\w+\s+)*{keyword}",
    r"(?:in\s+)?contrast\s+to\s+(?:\w+\s+)*{keyword}",
    r"(?:prior|previous|earlier)\s+(?:\w+\s+)*{keyword}",

    # Limitation discussions
    r"limit(?:ed|ation)s?\s+(?:of\s+)?(?:\w+\s+)*{keyword}",
    r"differ(?:s|ed|ing|ent)?\s+(?:from\s+)?(?:\w+\s+)*{keyword}",
]
```

**When matched**: The keyword is considered to be in protective context, and the paper passes.

#### Tier 3: Standard Keyword Matching

If no definitive title pattern matches and no negative context is found, standard keyword matching applies:
- Keywords in title without protective context → **Rejected** (high confidence)
- Keywords in abstract without protective context → **Rejected** (lower confidence)

### Decision Flow

```
┌─────────────────────────────────────────┐
│  Check Definitive Title Patterns        │
│  (e.g., "Case Report:", "in rats")      │
└─────────────────┬───────────────────────┘
                  │
         Match?   │
          ┌───────┴───────┐
          │ Yes           │ No
          ▼               ▼
      REJECT         ┌────────────────────────┐
                     │ Check Exclusion Keywords│
                     └───────────┬────────────┘
                                 │
                        Found?   │
                     ┌───────────┴───────────┐
                     │ Yes                   │ No
                     ▼                       ▼
              ┌──────────────────┐        PASS
              │ Check Negative   │
              │ Context Patterns │
              └────────┬─────────┘
                       │
              Context? │
              ┌────────┴────────┐
              │ Yes             │ No
              ▼                 ▼
            PASS             REJECT
```

## Code Structure

### Key Files

- `src/bmlibrarian/agents/systematic_review/filters.py` - Main filtering module
- `tests/test_systematic_review_filtering.py` - Comprehensive test suite

### Key Classes

#### InitialFilter

```python
class InitialFilter:
    def __init__(
        self,
        criteria: SearchCriteria,
        custom_exclusion_keywords: Optional[List[str]] = None,
        callback: Optional[Callable[[str, str], None]] = None,
    ) -> None

    def filter_paper(self, paper: PaperData) -> FilterResult
    def filter_batch(self, papers: List[PaperData], ...) -> BatchFilterResult
```

#### InclusionEvaluator

```python
class InclusionEvaluator:
    def __init__(
        self,
        criteria: SearchCriteria,
        model: Optional[str] = None,
        host: Optional[str] = None,
        temperature: float = DEFAULT_TEMPERATURE,
        config: Optional[SystematicReviewConfig] = None,
        callback: Optional[Callable[[str, str], None]] = None,
    ) -> None

    def evaluate(self, paper: PaperData, relevance_score: Optional[float] = None) -> InclusionDecision
    def evaluate_batch(self, papers: List[PaperData], ...) -> List[Tuple[PaperData, InclusionDecision]]
```

### Constants

```python
# Minimum abstract length for evaluation
MIN_ABSTRACT_LENGTH = 50

# Default exclusion keywords
DEFAULT_EXCLUSION_KEYWORDS: List[str] = [
    "animal study", "animal model", "mouse model", "rat model",
    "in vitro", "cell culture", "in vivo",
    "veterinary", "canine", "feline", "bovine", "porcine",
    "editorial", "letter to editor", "commentary",
    "protocol only", "study protocol",
    "erratum", "corrigendum", "retracted",
    "case report", "case reports", "case series",
]

# Confidence thresholds
HIGH_CONFIDENCE_THRESHOLD = 0.85
MEDIUM_CONFIDENCE_THRESHOLD = 0.6
```

## Usage Examples

### Basic Filtering

```python
from bmlibrarian.agents.systematic_review import (
    InitialFilter,
    SearchCriteria,
    StudyTypeFilter,
)

criteria = SearchCriteria(
    research_question="What is the efficacy of statins for CVD prevention?",
    purpose="Systematic review",
    inclusion_criteria=["Human studies", "Statin intervention"],
    exclusion_criteria=["Animal studies", "Case reports"],
    date_range=(2010, 2024),
)

filter_obj = InitialFilter(criteria)
result = filter_obj.filter_paper(paper)

if result.passed:
    print("Paper passed initial filter")
else:
    print(f"Paper rejected: {result.reason}")
```

### Batch Filtering with Progress

```python
def progress_callback(current: int, total: int) -> None:
    print(f"Filtering: {current}/{total}")

batch_result = filter_obj.filter_batch(papers, progress_callback=progress_callback)

print(f"Passed: {len(batch_result.passed)}")
print(f"Rejected: {len(batch_result.rejected)}")
print(f"Pass rate: {batch_result.pass_rate:.1%}")
```

### LLM-Based Evaluation

```python
from bmlibrarian.agents.systematic_review import InclusionEvaluator

evaluator = InclusionEvaluator(criteria)
decision = evaluator.evaluate(paper, relevance_score=4.0)

print(f"Status: {decision.status.value}")
print(f"Confidence: {decision.confidence}")
print(f"Rationale: {decision.rationale}")
```

## Testing

The filtering system has comprehensive tests covering:

- **TestInitialFilter**: Date range, keywords, batch processing
- **TestContextAwareFiltering**: Edge cases for protective context
- **TestDefinitiveTitlePatterns**: Title pattern matching
- **TestInclusionEvaluator**: LLM-based evaluation (mocked)

Run tests:

```bash
uv run python -m pytest tests/test_systematic_review_filtering.py -v
```

## Extending the System

### Adding New Exclusion Keywords

Add to `DEFAULT_EXCLUSION_KEYWORDS` or pass via `custom_exclusion_keywords`:

```python
filter_obj = InitialFilter(
    criteria,
    custom_exclusion_keywords=["simulation study", "theoretical model"]
)
```

### Adding New Title Patterns

Add regex patterns to `DEFINITIVE_TITLE_PATTERNS`:

```python
DEFINITIVE_TITLE_PATTERNS.append(r"\bsimulation\b")
```

### Adding New Protective Context Patterns

Add patterns to `NEGATIVE_CONTEXT_PATTERNS` using `{keyword}` placeholder:

```python
NEGATIVE_CONTEXT_PATTERNS.append(r"based on prior {keyword}")
```

## Performance Considerations

- **InitialFilter**: O(n × k × p) where n=papers, k=keywords, p=patterns
- **InclusionEvaluator**: O(n) LLM calls, ~2-5 seconds per paper

For large paper sets (>1000), consider:
1. Running InitialFilter first to reduce set size
2. Using batch operations with progress callbacks
3. Implementing caching for repeated evaluations

## Related Documentation

- [Implementation Plan](../planning/SystematicReviewAgent/implementation_plan.md)
- [Data Models](../planning/SystematicReviewAgent/data_models.md)
- [Architecture](../planning/SystematicReviewAgent/architecture.md)
