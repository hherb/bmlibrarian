# PaperChecker Example Datasets

This directory contains sample data for testing and demonstrating the PaperChecker system.

## Files

### `sample_abstract.json`
A single medical abstract for quick testing. Ideal for:
- Initial setup verification
- Quick functionality checks
- Learning the PaperChecker workflow

```bash
# Quick test with single abstract
uv run python paper_checker_cli.py examples/paperchecker/sample_abstract.json -o results.json
```

### `diverse_test_abstracts.json`
A collection of five abstracts representing different study types:
1. **Randomized Controlled Trial (RCT)**: Exercise and cardiovascular outcomes
2. **Meta-Analysis**: Statins for primary prevention
3. **Observational Cohort Study**: Sleep duration and diabetes risk
4. **Case Report**: Recurrent spontaneous coronary artery dissection
5. **Review Article**: Gut microbiome and cardiovascular health

Use for comprehensive integration testing:

```bash
# Full integration test with diverse abstracts
uv run python paper_checker_cli.py examples/paperchecker/diverse_test_abstracts.json \
  -o examples/paperchecker/diverse_results.json \
  --export-markdown examples/paperchecker/reports/

# Quick mode (faster, uses reduced limits)
uv run python paper_checker_cli.py examples/paperchecker/diverse_test_abstracts.json \
  -o examples/paperchecker/quick_results.json --quick
```

## Expected Outputs

When running PaperChecker on these abstracts, you should see:

1. **Statement Extraction**: 1-2 core claims per abstract
2. **Counter-Statement Generation**: Semantic negations of each claim
3. **Multi-Strategy Search**: Results from semantic, HyDE, and keyword searches
4. **Document Scoring**: Relevance scores (1-5) for found documents
5. **Citation Extraction**: Relevant passages from high-scoring documents
6. **Verdict Analysis**: Supports/contradicts/undecided with confidence levels

## Interactive Testing

For step-by-step exploration, use the PaperChecker Laboratory:

```bash
uv run python paper_checker_lab.py
```

The laboratory GUI allows you to:
- Enter abstracts manually or load by PMID
- Watch each workflow step execute
- Inspect intermediate results
- Adjust parameters and re-run

## Performance Expectations

Approximate processing times (on typical hardware with local Ollama):

| Abstract Type | Expected Time |
|---------------|---------------|
| Short (~100 words) | 60-90 seconds |
| Medium (~250 words) | 90-180 seconds |
| Long (~500 words) | 120-300 seconds |

Times vary based on:
- Number of statements extracted
- Documents found in database
- LLM model performance
- Database size and indexing

## Troubleshooting

If processing fails:

1. **Database connection**: Verify PostgreSQL is running and accessible
2. **Ollama service**: Ensure Ollama is running (`ollama serve`)
3. **Models available**: Check required models are downloaded (`ollama list`)
4. **Schema applied**: Verify `papercheck` schema exists in database

For detailed documentation, see:
- User Guide: `doc/users/paper_checker_guide.md`
- CLI Reference: `doc/users/paper_checker_cli_guide.md`
- Laboratory Guide: `doc/users/paper_checker_lab_guide.md`
