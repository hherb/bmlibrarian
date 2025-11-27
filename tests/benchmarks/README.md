# Systematic Review Agent Benchmarks

This directory contains benchmark tests for validating the SystematicReviewAgent against published Cochrane systematic reviews.

## Purpose

The benchmark suite validates that our agent can:
1. **Find** all papers cited in a Cochrane review
2. **Score** them as relevant (include them in final results)

**Target: 100% Recall** - Every paper the Cochrane reviewers included must also be found and included by our agent.

## Directory Structure

```
tests/benchmarks/
├── __init__.py                  # Module exports
├── benchmark_utils.py           # Core utilities and data models
├── test_benchmark_recall.py     # Main pytest benchmark tests
├── README.md                    # This file
├── data/                        # Ground truth JSON files
│   ├── sample_cochrane_template.json  # Template (delete when adding real data)
│   └── cochrane_cd012345.json         # Example: real Cochrane review data
└── results/                     # Generated benchmark results (gitignored)
    └── benchmark_CD012345.json
```

## Ground Truth Format

Each Cochrane review is represented as a JSON file in `data/`:

```json
{
  "cochrane_id": "CD012345",
  "title": "Title of the Cochrane Systematic Review",
  "research_question": "The research question from the review",
  "pico": {
    "population": "...",
    "intervention": "...",
    "comparison": "...",
    "outcome": "..."
  },
  "inclusion_criteria": [
    "Criterion 1",
    "Criterion 2"
  ],
  "exclusion_criteria": [
    "Exclusion 1"
  ],
  "included_studies": [
    {
      "pmid": "12345678",
      "doi": "10.1000/xxx",
      "title": "Study title",
      "authors": ["Author A", "Author B"],
      "year": 2020,
      "cochrane_ref_id": "Study1",
      "notes": "Optional notes"
    }
  ],
  "authors_conclusion": "The review's conclusion (for future verdict testing)",
  "date_range": [2010, 2023],
  "source_url": "https://..."
}
```

### Paper Identification

Each paper in `included_studies` should have at least one identifier:
- **pmid** (preferred): PubMed ID for exact matching
- **doi**: Digital Object Identifier for fallback matching
- **title**: Paper title for fuzzy matching (last resort)

## Running Benchmarks

```bash
# Run all benchmarks
uv run pytest tests/benchmarks/ -v

# Run specific Cochrane review benchmark
uv run pytest tests/benchmarks/test_benchmark_recall.py -v -k "cd012345"

# Run with detailed output on failure
uv run pytest tests/benchmarks/ -v --tb=long

# Check database coverage (diagnostic)
uv run pytest tests/benchmarks/test_benchmark_recall.py::TestDatabaseCoverage -v
```

## Adding New Benchmarks

1. **Find a suitable Cochrane review**:
   - Start with reviews that have few included studies (5-15)
   - Ensure papers are likely in our database (check PMIDs/DOIs exist)

2. **Create ground truth JSON**:
   - Copy `sample_cochrane_template.json` as starting point
   - Extract included studies from Cochrane review
   - Get PMIDs/DOIs from the reference list
   - Name file: `cochrane_{review_id}.json`

3. **Verify database coverage**:
   ```bash
   uv run pytest tests/benchmarks/test_benchmark_recall.py::TestDatabaseCoverage -v -k "{review_id}"
   ```

4. **Run the benchmark**:
   ```bash
   uv run pytest tests/benchmarks/test_benchmark_recall.py::TestBenchmarkRecall -v -k "{review_id}"
   ```

## Metrics

### Recall (Primary Target: 100%)
```
Recall = (Ground truth papers found AND included) / (Total ground truth papers)
```

All papers from the Cochrane review must be:
- Found in our database
- Scored as relevant by the agent
- Included in the agent's final results

### Precision (Informational)
```
Precision = (Agent included papers in ground truth) / (Total agent included)
```

Lower precision is acceptable - our agent may find additional relevant papers that the Cochrane review missed or excluded for other reasons.

## Troubleshooting

### "Paper not found in database"
- Check if PMID/DOI is correct
- Paper may not be in PubMed/medRxiv or not yet imported
- Try importing the paper manually and re-running

### "Paper found but not included"
- Check the agent's relevance score for the paper
- May need to adjust scoring thresholds
- Review the exclusion rationale in results

### Low precision
- Not a failure - agent may legitimately find more papers
- Review included papers to ensure they're actually relevant
- Update ground truth if Cochrane missed relevant papers

## Results

Benchmark results are saved to `results/` (gitignored) as JSON:
- `benchmark_{cochrane_id}.json`: Detailed matching results
- Includes per-paper match status, methods, and scores

## Future Work

- **Verdict Similarity**: Compare agent conclusions vs. Cochrane conclusions
- **Automated Ground Truth Extraction**: Parse Cochrane PDFs for citations
- **Regression Testing**: Track benchmark performance over time
