# Fact Checker Guide

## Overview

The BMLibrarian Fact Checker is a tool for auditing biomedical statements in LLM training datasets. It evaluates the veracity of statements by searching the literature database and comparing them against published evidence.

## Key Features

- **Automated Verification**: Evaluates biomedical statements as yes/no/maybe based on literature evidence
- **Evidence Extraction**: Provides specific citations supporting or contradicting each statement
- **Batch Processing**: Process multiple statements from JSON input files
- **Confidence Assessment**: Rates confidence (high/medium/low) based on evidence strength
- **Validation Support**: Compare evaluations against expected answers for accuracy testing

## Use Cases

1. **LLM Training Data Auditing**: Verify factual accuracy of biomedical statements in training datasets
2. **Medical Knowledge Validation**: Check claims against current literature
3. **Dataset Quality Control**: Identify potentially incorrect statements in medical corpora
4. **Evidence-Based Verification**: Validate medical facts with specific literature references

## Quick Start

### Installation

The fact checker is part of BMLibrarian. Ensure you have:

- Python ≥3.12
- PostgreSQL database with biomedical literature
- Ollama running locally with appropriate models

### Basic Usage

1. **Create an input file** (`input.json`):

```json
[
  {
    "statement": "All cases of childhood ulcerative colitis require colectomy",
    "answer": "no"
  },
  {
    "statement": "Vitamin D deficiency is common in IBD patients",
    "answer": "yes"
  },
  {
    "statement": "Probiotics are effective for all forms of inflammatory bowel disease",
    "answer": "maybe"
  }
]
```

2. **Run the fact checker**:

```bash
uv run python fact_checker_cli.py input.json -o results.json
```

3. **Review results** (`results.json`):

```json
{
  "results": [
    {
      "statement": "All cases of childhood ulcerative colitis require colectomy",
      "evaluation": "no",
      "reason": "Literature shows most pediatric UC cases respond to medical management. Only severe, refractory cases require surgical intervention.",
      "evidence_list": [
        {
          "citation": "Most childhood UC cases can be managed medically...",
          "pmid": "PMID:12345678",
          "doi": "DOI:10.1234/test",
          "relevance_score": 4.5,
          "stance": "contradicts"
        }
      ],
      "confidence": "high",
      "metadata": {
        "documents_reviewed": 15,
        "supporting_citations": 0,
        "contradicting_citations": 5,
        "neutral_citations": 0
      },
      "expected_answer": "no",
      "matches_expected": true
    }
  ],
  "summary": {
    "total_statements": 3,
    "evaluations": {
      "yes": 1,
      "no": 1,
      "maybe": 1
    },
    "confidences": {
      "high": 2,
      "medium": 1,
      "low": 0
    },
    "validation": {
      "matches": 3,
      "mismatches": 0,
      "accuracy": 1.0
    }
  }
}
```

## Command-Line Options

### Basic Options

```bash
python fact_checker_cli.py INPUT_FILE -o OUTPUT_FILE [OPTIONS]
```

**Required Arguments:**
- `INPUT_FILE`: JSON file with statements to check
- `-o, --output OUTPUT_FILE`: Output JSON file for results

### Configuration Options

**Model Selection:**
```bash
--model MODEL_NAME          # Use specific Ollama model
--temperature 0.1           # Set model temperature (0.0-1.0)
```

**Search Configuration:**
```bash
--score-threshold 2.5       # Minimum relevance score (1-5)
--max-search-results 50     # Maximum documents to search
--max-citations 10          # Maximum citations to extract
```

**Quick Mode:**
```bash
--quick                     # Fast mode with fewer documents
```

**Display Options:**
```bash
-v, --verbose              # Show progress messages
--detailed                 # Show detailed results for each statement
```

### Examples

**Basic fact checking:**
```bash
uv run python fact_checker_cli.py statements.json -o results.json
```

**Custom thresholds:**
```bash
uv run python fact_checker_cli.py statements.json -o results.json \
  --score-threshold 3.0 \
  --max-search-results 100
```

**Quick test mode:**
```bash
uv run python fact_checker_cli.py test_statements.json -o test_results.json --quick
```

**Verbose mode with details:**
```bash
uv run python fact_checker_cli.py statements.json -o results.json -v --detailed
```

**Custom model:**
```bash
uv run python fact_checker_cli.py statements.json -o results.json \
  --model medgemma-27b-text-it-Q8_0:latest \
  --temperature 0.15
```

## Input Format

### Required Fields

Each statement object must have:
- `statement` (string): The biomedical statement to evaluate

### Optional Fields

- `answer` (string): Expected answer ("yes", "no", or "maybe") for validation

### Example Input File

```json
[
  {
    "statement": "Metformin is first-line therapy for type 2 diabetes",
    "answer": "yes"
  },
  {
    "statement": "All patients with hypertension require medication",
    "answer": "no"
  },
  {
    "statement": "Ketogenic diet cures epilepsy in all children"
  }
]
```

## Output Format

### Result Fields

Each result contains:

**Core Evaluation:**
- `statement`: Original statement
- `evaluation`: "yes", "no", or "maybe"
- `reason`: Brief explanation (1-3 sentences)
- `confidence`: "high", "medium", or "low"

**Evidence:**
- `evidence_list`: Array of citations with:
  - `citation`: Extracted passage
  - `pmid`: PubMed ID (if available)
  - `doi`: DOI (if available)
  - `relevance_score`: Document relevance (0-5)
  - `stance`: "supports" or "contradicts"

**Metadata:**
- `documents_reviewed`: Total documents analyzed
- `supporting_citations`: Count of supporting evidence
- `contradicting_citations`: Count of contradicting evidence
- `neutral_citations`: Count of neutral evidence
- `timestamp`: ISO 8601 timestamp

**Validation (if expected answer provided):**
- `expected_answer`: Expected evaluation
- `matches_expected`: Boolean indicating match

### Summary Statistics

The output includes aggregate statistics:
- Total statements processed
- Evaluation distribution (yes/no/maybe)
- Confidence distribution (high/medium/low)
- Validation accuracy (if expected answers provided)

## Evaluation Criteria

### "Yes" Evaluation

Statement is supported by literature when:
- Multiple high-quality citations support the statement
- Evidence is consistent across sources
- No significant contradicting evidence found

**Confidence Factors:**
- High: 3+ supporting citations, 5+ documents, >70% agreement
- Medium: 2+ supporting citations, consistent evidence
- Low: Limited evidence or few sources

### "No" Evaluation

Statement is contradicted by literature when:
- Multiple citations directly contradict the statement
- Strong evidence against the claim
- Consensus in literature opposes the statement

**Confidence Factors:**
- High: 3+ contradicting citations, 5+ documents, >70% opposition
- Medium: 2+ contradicting citations, clear contradiction
- Low: Limited contradicting evidence

### "Maybe" Evaluation

Insufficient or mixed evidence when:
- No relevant literature found
- Mixed evidence (both supporting and contradicting)
- Limited quality evidence available
- Evidence is inconclusive

**Typical Reasons:**
- "Insufficient evidence: No relevant documents found"
- "Mixed evidence: Both supporting and contradicting studies found"
- "Limited evidence: Few high-quality sources available"

## Best Practices

### Statement Formulation

**Good statements:**
- Clear and specific: "Metformin reduces cardiovascular mortality in T2DM"
- Testable claims: "Vitamin D supplementation improves bone density"
- Well-defined scope: "First-line antibiotics for community-acquired pneumonia include..."

**Avoid:**
- Vague statements: "Treatment is sometimes effective"
- Opinion-based: "The best approach is..."
- Overly broad: "Medicine is important"

### Threshold Selection

**Score Threshold (1-5):**
- `2.5`: Default, balanced relevance
- `3.0+`: Strict, high-relevance documents only
- `2.0`: Inclusive, captures more potential evidence

**Max Search Results:**
- `50`: Default, good balance
- `100+`: Comprehensive, slower processing
- `20`: Quick testing, faster results

**Max Citations:**
- `10`: Default, representative sample
- `20+`: Comprehensive evidence gathering
- `5`: Quick overview

### Batch Processing

For large datasets:

1. **Start small**: Test with 10-20 statements first
2. **Use quick mode**: Validate approach before full run
3. **Monitor progress**: Use `-v` flag for verbose output
4. **Review results**: Check accuracy on sample before processing full dataset

### Interpreting Results

**High confidence "no"**: Statement is likely false
- Review contradicting citations
- Check if evidence is recent and high-quality
- Consider scope of generalization

**High confidence "yes"**: Statement is well-supported
- Review supporting citations
- Verify evidence quality and recency
- Check for consensus in literature

**Medium/low confidence**: Uncertain or limited evidence
- May need manual review
- Consider additional data sources
- Evidence may be emerging or controversial

**"Maybe" results**: Require human judgment
- Check if statement is too vague
- Review available evidence manually
- Consider rephrasing for clarity

## Troubleshooting

### Common Issues

**No documents found:**
- Statement may be too specific or use uncommon terminology
- Try rephrasing the statement
- Check database coverage for the topic

**All "maybe" results:**
- Score threshold may be too high (try lowering to 2.0)
- Database may lack coverage for these topics
- Statements may be too vague

**Low accuracy (vs expected answers):**
- Review mismatched results individually
- Check if expected answers are accurate
- Consider adjusting thresholds
- May indicate data quality issues

**Slow processing:**
- Use `--quick` mode for testing
- Reduce `--max-search-results`
- Reduce `--max-citations`
- Process smaller batches

### Error Messages

**"Cannot connect to Ollama server":**
- Ensure Ollama is running: `ollama serve`
- Check port 11434 is available
- Verify model is available: `ollama list`

**"Model not found":**
- Pull required model: `ollama pull gpt-oss:20b`
- Check model name in config
- Verify Ollama installation

**"Invalid JSON format":**
- Validate JSON syntax
- Check required fields present
- Ensure proper array structure

## Configuration

### Config File Location

`~/.bmlibrarian/config.json`

### Fact Checker Configuration

```json
{
  "models": {
    "fact_checker_agent": "gpt-oss:20b"
  },
  "agents": {
    "fact_checker": {
      "temperature": 0.1,
      "top_p": 0.9,
      "max_tokens": 2000,
      "score_threshold": 2.5,
      "max_search_results": 50,
      "max_citations": 10
    }
  }
}
```

### Configuration Options

- `fact_checker_agent`: Model for statement evaluation
- `temperature`: Creativity/randomness (0.0-1.0, default 0.1)
- `top_p`: Nucleus sampling (0.0-1.0, default 0.9)
- `max_tokens`: Maximum response length
- `score_threshold`: Minimum document relevance score
- `max_search_results`: Maximum documents to retrieve
- `max_citations`: Maximum citations to extract

## Performance Considerations

### Processing Time

Typical processing time per statement:
- Quick mode (~20 documents): 30-60 seconds
- Normal mode (~50 documents): 60-120 seconds
- Comprehensive mode (~100+ documents): 120-300 seconds

**Factors affecting speed:**
- Number of relevant documents found
- Model complexity (gpt-oss:20b is slower than medgemma4B)
- Database size and query complexity
- Available system resources

### Resource Usage

**Memory:**
- Typical: 2-4 GB RAM
- Peak: 6-8 GB with large models

**Storage:**
- Minimal (results only)
- Output files: ~1-10 KB per statement

**Network:**
- No external network required (all local)
- Ollama and PostgreSQL on localhost

## Limitations

### Current Limitations

1. **Language Models**: Evaluation quality depends on model capabilities
2. **Database Coverage**: Limited to literature in the database
3. **Temporal Scope**: Current knowledge as of database last update
4. **Statement Complexity**: Works best with clear, specific statements
5. **Context Understanding**: May miss nuanced or context-dependent claims

### Future Enhancements

- Multi-model consensus evaluation
- Temporal analysis (tracking claim evolution)
- Confidence calibration
- Domain-specific tuning
- Integration with external databases

## Support

For issues or questions:
- GitHub Issues: https://github.com/hherb/bmlibrarian/issues
- Documentation: `doc/developers/fact_checker_system.md`
- Examples: `examples/fact_checker_demo.py`

## Related Documentation

- [Developer Guide](../developers/fact_checker_system.md)
- [Citation System Guide](citation_guide.md)
- [Query Agent Guide](query_agent_guide.md)
- [Multi-Agent Architecture](../developers/agent_module.md)
