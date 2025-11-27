# Systematic Review Agent Benchmark System

## Overview

The benchmark system validates the SystematicReviewAgent against published Cochrane systematic reviews. It measures whether our agent can find and score as relevant all papers that expert human reviewers included in their systematic reviews.

**Target Metric: 100% Recall**

Every paper cited in a Cochrane review must be:
1. Found in our database (by PMID, DOI, or fuzzy title match)
2. Scored as relevant by the agent
3. Included in the agent's final results

## Architecture

```
tests/benchmarks/
├── __init__.py                    # Module exports
├── benchmark_utils.py             # Core data models and matching logic
├── test_benchmark_recall.py       # pytest benchmark tests
├── test_benchmark_utils.py        # Unit tests for utilities
├── data/                          # Ground truth JSON files
│   └── cochrane_{id}.json
└── results/                       # Generated results (gitignored)
    └── benchmark_{id}.json
```

## Data Models

### GroundTruthPaper

Represents a single paper from a Cochrane review's reference list.

```python
@dataclass
class GroundTruthPaper:
    pmid: Optional[str] = None      # PubMed ID (primary identifier)
    doi: Optional[str] = None       # DOI (secondary identifier)
    title: Optional[str] = None     # Title (fuzzy matching fallback)
    authors: Optional[List[str]] = None
    year: Optional[int] = None
    cochrane_ref_id: Optional[str] = None  # Reference ID in Cochrane
    notes: Optional[str] = None
```

At least one identifier (pmid, doi, or title) is required.

### CochraneGroundTruth

Complete ground truth dataset for a Cochrane review.

```python
@dataclass
class CochraneGroundTruth:
    cochrane_id: str                           # e.g., "CD012345"
    title: str
    research_question: str
    included_studies: List[GroundTruthPaper]   # Papers to find
    pico: Optional[Dict[str, str]] = None
    inclusion_criteria: Optional[List[str]] = None
    exclusion_criteria: Optional[List[str]] = None
    authors_conclusion: Optional[str] = None   # For future verdict testing
    date_range: Optional[Tuple[int, int]] = None
```

### BenchmarkResult

Results of comparing agent output against ground truth.

```python
@dataclass
class BenchmarkResult:
    ground_truth: CochraneGroundTruth
    total_ground_truth_papers: int
    total_agent_included: int
    papers_found: int                   # Found in database
    papers_found_and_included: int      # Found AND included by agent
    papers_not_found: int               # Not in database
    papers_found_but_excluded: int      # In database but agent excluded
    recall: float                       # found_and_included / total_gt
    precision: float                    # gt_in_included / total_included
    matches: List[PaperMatch]           # Per-paper matching details
    passed: bool                        # recall >= 1.0
    failure_reasons: List[str]
```

## Matching Logic

Papers are matched in priority order:

1. **PMID (exact)**: Highest confidence, stop searching if found
2. **DOI (exact)**: After URL prefix normalization and lowercase
3. **Title (fuzzy)**: SequenceMatcher ratio ≥ 0.85

```python
def match_paper_to_result(
    ground_truth: GroundTruthPaper,
    agent_papers: List[Dict[str, Any]],
    included_doc_ids: Set[int],
) -> PaperMatch:
```

### Normalization

All identifiers are normalized before comparison:

- **DOI**: Lowercase, strip whitespace, remove URL prefixes
- **PMID**: Extract numeric portion, remove leading zeros
- **Title**: Lowercase, remove punctuation, collapse whitespace

## Metrics

### Recall (Target: 100%)

```
Recall = papers_found_and_included / total_ground_truth_papers
```

This is our primary metric. All Cochrane-cited papers must be found AND included.

### Precision (Informational)

```
Precision = gt_papers_in_included / total_agent_included
```

Lower precision is acceptable - our agent may find additional relevant papers.

## Running Benchmarks

```bash
# Run all benchmarks
uv run pytest tests/benchmarks/ -v

# Run specific Cochrane review
uv run pytest tests/benchmarks/test_benchmark_recall.py -v -k "cd012345"

# Run with detailed failure output
uv run pytest tests/benchmarks/ -v --tb=long

# Run database coverage check (diagnostic)
uv run pytest tests/benchmarks/test_benchmark_recall.py::TestDatabaseCoverage -v

# Run benchmark utilities unit tests
uv run pytest tests/benchmarks/test_benchmark_utils.py -v
```

## Adding New Benchmarks

### 1. Find a Suitable Cochrane Review

Criteria for good benchmark candidates:
- **Small initially**: 5-15 included studies (easier to debug)
- **Good coverage**: Papers likely in our database (recent PubMed papers)
- **Clear criteria**: Well-defined inclusion/exclusion criteria
- **Narrow scope**: Focused research question

### 2. Extract Ground Truth

From the Cochrane review:
1. Find the "Characteristics of included studies" section
2. Extract PMIDs and DOIs from references
3. Copy the research question from abstract
4. Extract PICO components if present
5. Copy inclusion/exclusion criteria

### 3. Create JSON File

```json
{
  "cochrane_id": "CD012345",
  "title": "...",
  "research_question": "...",
  "pico": {"population": "...", "intervention": "...", ...},
  "inclusion_criteria": ["...", "..."],
  "exclusion_criteria": ["...", "..."],
  "included_studies": [
    {"pmid": "12345678", "title": "...", "year": 2020},
    {"doi": "10.1000/xxx", "title": "...", "year": 2019}
  ],
  "authors_conclusion": "...",
  "date_range": [2010, 2023],
  "source_url": "https://..."
}
```

Save to `tests/benchmarks/data/cochrane_{id}.json`.

### 4. Verify Database Coverage

```bash
uv run pytest tests/benchmarks/test_benchmark_recall.py::TestDatabaseCoverage -v -k "{id}"
```

This shows which papers are/aren't in the database.

### 5. Run Benchmark

```bash
uv run pytest tests/benchmarks/test_benchmark_recall.py::TestBenchmarkRecall -v -k "{id}"
```

## Interpreting Results

### Pass

All ground truth papers found and included. Example:
```
Benchmark Result: PASSED
  Cochrane ID: CD012345
  Ground Truth Papers: 12
  Agent Included Papers: 18
  Papers Found & Included: 12
  Recall: 100.0% (target: 100%)
```

### Fail: Papers Not Found

Papers missing from database:
```
Failure Reasons:
  - 2 ground truth paper(s) not found in database
```

**Resolution**: Import missing papers, or document as database limitation.

### Fail: Papers Found but Excluded

Agent excluded relevant papers:
```
Failure Reasons:
  - 3 ground truth paper(s) found but not included
```

**Resolution**: Investigate agent's exclusion rationale. May need to:
- Adjust relevance threshold
- Review scoring logic
- Update inclusion/exclusion criteria interpretation

## Future Work

### Verdict Similarity Testing

Compare agent's conclusion against Cochrane's conclusion:
1. Extract "Authors' conclusions" from Cochrane review
2. Generate equivalent conclusion from agent's report
3. Calculate semantic similarity (embeddings or LLM-as-judge)
4. Define pass threshold (to be calibrated)

### Automated Ground Truth Extraction

Parse Cochrane review PDFs to automatically extract:
- Research question
- PICO components
- Inclusion/exclusion criteria
- Reference list with PMIDs/DOIs

### Regression Testing

Track benchmark performance over time:
- Store historical results
- Alert on recall regression
- Dashboard for benchmark status

## Related Documentation

- [Systematic Review Agent](/doc/users/systematic_review_guide.md)
- [Implementation Plan](/doc/planning/SystematicReviewAgent/implementation_plan.md)
- [Data Models](/doc/planning/SystematicReviewAgent/data_models.md)
