# Fact Checker Guide

## Overview

The BMLibrarian Fact Checker is a tool for auditing biomedical statements in LLM training datasets. It evaluates the veracity of statements by searching the literature database and comparing them against published evidence.

**Storage**: All results are stored in **PostgreSQL** (factcheck schema) with optional JSON export.

## Key Features

- **Automated Verification**: Evaluates biomedical statements as yes/no/maybe based on literature evidence
- **Evidence Extraction**: Provides specific citations supporting or contradicting each statement
- **Batch Processing**: Process multiple statements from JSON input files
- **Confidence Assessment**: Rates confidence (high/medium/low) based on evidence strength
- **Validation Support**: Compare evaluations against expected answers for accuracy testing
- **PostgreSQL Storage**: Persistent storage in centralized database with multi-user annotation support
- **Incremental Mode**: Resume processing by skipping already-evaluated statements
- **JSON Import/Export**: Import legacy JSON files or export database results to JSON

## Use Cases

1. **LLM Training Data Auditing**: Verify factual accuracy of biomedical statements in training datasets
2. **Medical Knowledge Validation**: Check claims against current literature
3. **Dataset Quality Control**: Identify potentially incorrect statements in medical corpora
4. **Evidence-Based Verification**: Validate medical facts with specific literature references
5. **Multi-Reviewer Annotation**: Support collaborative fact-checking with human annotations

## Quick Start

### Installation

The fact checker is part of BMLibrarian. Ensure you have:

- Python ≥3.12
- PostgreSQL database with biomedical literature and factcheck schema
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

2. **Run the fact checker** (stores in PostgreSQL):

```bash
uv run python fact_checker_cli.py input.json
```

3. **Optional: Export to JSON**:

```bash
# Export results to JSON file
uv run python fact_checker_cli.py input.json -o results.json
```

4. **Resume processing** (incremental mode):

```bash
# Skip statements that already have AI evaluations
uv run python fact_checker_cli.py input.json --incremental
```

## Command-Line Options

### Basic Options

```bash
python fact_checker_cli.py INPUT_FILE [OPTIONS]
```

**Required Arguments:**
- `INPUT_FILE`: JSON file with statements to check

**Optional Arguments:**
- `-o, --output OUTPUT_FILE`: Export results to JSON file (database is always used)
- `--incremental`: Skip statements that already have AI evaluations (resume functionality)

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
--quick                     # Fast mode with fewer documents (20 docs, 5 citations)
```

**Display Options:**
```bash
-v, --verbose              # Show progress messages
--detailed                 # Show detailed results for each statement
```

### Examples

**Basic fact checking** (stores in PostgreSQL):
```bash
uv run python fact_checker_cli.py statements.json
```

**With JSON export**:
```bash
uv run python fact_checker_cli.py statements.json -o results.json
```

**Incremental processing** (resume after interruption):
```bash
uv run python fact_checker_cli.py statements.json --incremental
```

**Custom thresholds**:
```bash
uv run python fact_checker_cli.py statements.json \
  --score-threshold 3.0 \
  --max-search-results 100
```

**Quick test mode**:
```bash
uv run python fact_checker_cli.py test_statements.json --quick
```

**Verbose mode with details**:
```bash
uv run python fact_checker_cli.py statements.json -v --detailed
```

**Custom model**:
```bash
uv run python fact_checker_cli.py statements.json \
  --model medgemma-27b-text-it-Q8_0:latest \
  --temperature 0.15
```

## Input Format

### Required Fields

Each statement object must have:
- `statement` (string): The biomedical statement to evaluate
  - **OR** `question` (string): Alternative key for statement text

### Optional Fields

- `answer` (string): Expected answer ("yes", "no", or "maybe") for validation
  - **OR** `expected_answer` (string): Alternative key for expected answer
- `id` (string): Original statement identifier (e.g., PMID)
  - **OR** `input_statement_id` (string): Alternative key for statement ID

**Note**: The fact-checker supports both legacy format (`statement`/`answer`) and extracted format (`question`/`answer`/`id`) from training data extraction tools.

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
    "question": "Ketogenic diet cures epilepsy in all children",
    "answer": "no",
    "id": "PMID:12345678"
  }
]
```

## Database Storage

### PostgreSQL Schema

Results are stored in the **factcheck schema** in PostgreSQL:

**Tables:**
- `statements`: Biomedical statements to be fact-checked
- `ai_evaluations`: AI-generated fact-check evaluations
- `evidence`: Literature citations supporting evaluations (FK to `public.document`)
- `human_annotations`: Human reviewer annotations (multi-user support)
- `annotators`: Registered human reviewers
- `processing_metadata`: Session tracking and configuration snapshots
- `export_history`: Export audit trail

**Key Features:**
- **No Data Duplication**: Evidence table references `public.document(id)` directly
- **Multi-User Annotations**: Support for multiple human reviewers
- **Version Tracking**: AI evaluations support versioning
- **Session Tracking**: Processing sessions with configuration snapshots

### Incremental Mode

Use `--incremental` to resume processing after interruption or add new statements to existing batch:

```bash
# First run: processes all statements
uv run python fact_checker_cli.py batch1.json

# Later: add more statements to same file
uv run python fact_checker_cli.py batch1_updated.json --incremental
# Only processes NEW statements (skips those with existing evaluations)
```

**How it works:**
1. Checks which statements already exist in database
2. Identifies statements that already have AI evaluations
3. Skips evaluated statements, processes only new/unevaluated ones
4. Efficient for large datasets or interrupted runs

## JSON Export Format

When using `-o` flag, results are exported to JSON:

```json
{
  "results": [
    {
      "id": 1,
      "statement_text": "All cases of childhood ulcerative colitis require colectomy",
      "input_statement_id": "PMID:12345678",
      "expected_answer": "no",
      "eval_id": 1,
      "evaluation": "no",
      "reason": "Literature shows most pediatric UC cases respond to medical management...",
      "confidence": "high",
      "documents_reviewed": 15,
      "supporting_citations": 0,
      "contradicting_citations": 5,
      "neutral_citations": 0,
      "matches_expected": true,
      "model_used": "gpt-oss:20b",
      "evidence": [
        {
          "citation_text": "Most childhood UC cases can be managed medically...",
          "document_id": 98765,
          "pmid": "12345678",
          "doi": "10.1234/test",
          "relevance_score": 4.5,
          "supports_statement": "contradicts"
        }
      ],
      "human_annotations": []
    }
  ],
  "export_metadata": {
    "export_date": "2025-11-12T10:30:00Z",
    "export_type": "full",
    "total_statements": 1,
    "database": "PostgreSQL factcheck schema"
  }
}
```

### Export Fields

Each result contains:

**Core Evaluation:**
- `statement_text`: Original statement
- `evaluation`: "yes", "no", or "maybe"
- `reason`: Brief explanation (1-3 sentences)
- `confidence`: "high", "medium", or "low"

**Evidence:**
- `evidence`: Array of citations with:
  - `citation_text`: Extracted passage
  - `document_id`: Database document ID (FK to public.document)
  - `pmid`: PubMed ID (if available)
  - `doi`: DOI (if available)
  - `relevance_score`: Document relevance (1-5)
  - `supports_statement`: "supports", "contradicts", or "neutral"

**Metadata:**
- `documents_reviewed`: Total documents analyzed
- `supporting_citations`: Count of supporting evidence
- `contradicting_citations`: Count of contradicting evidence
- `neutral_citations`: Count of neutral evidence
- `model_used`: AI model used for evaluation

**Validation (if expected answer provided):**
- `expected_answer`: Expected evaluation
- `matches_expected`: Boolean indicating match

**Human Annotations (if available):**
- `human_annotations`: Array of human reviewer annotations with username, annotation, and explanation

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
4. **Use incremental mode**: Resume processing if interrupted
5. **Review results**: Check accuracy on sample before processing full dataset

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

## Human Annotation Workflow

After AI fact-checking, use the Review GUI for human annotation:

```bash
# Launch review GUI (loads from PostgreSQL)
uv run python fact_checker_review_gui.py

# Filter to only unannotated statements for specific user
uv run python fact_checker_review_gui.py --incremental --user alice

# Blind mode: hide AI/original annotations
uv run python fact_checker_review_gui.py --blind --user bob
```

See [Fact-Checker Review Guide](fact_checker_review_guide.md) for detailed review interface documentation.

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

**Incremental mode not skipping statements:**
- Verify statements exist in database with AI evaluations
- Check statement text matches exactly (whitespace sensitive)
- Use `-v` flag to see which statements are being processed

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
- Check required fields present (`statement` or `question`)
- Ensure proper array structure

**"Database connection error":**
- Verify PostgreSQL is running
- Check database credentials in `.env` or `~/.bmlibrarian/config.json`
- Ensure factcheck schema exists (run database migrations if needed)

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
  },
  "database": {
    "host": "localhost",
    "port": 5432,
    "database": "knowledgebase",
    "user": "your_username",
    "password": "your_password"
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
- PostgreSQL database storage (efficient with no duplication)
- JSON exports: ~1-10 KB per statement

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
- Integration with external databases (PubMed API)
- Real-time literature updates

## Support

For issues or questions:
- GitHub Issues: https://github.com/hherb/bmlibrarian/issues
- Developer Documentation: `doc/developers/fact_checker_system.md`
- Review GUI Guide: `doc/users/fact_checker_review_guide.md`

## Related Documentation

- [Fact-Checker Review GUI Guide](fact_checker_review_guide.md)
- [Developer Guide](../developers/fact_checker_system.md)
- [Citation System Guide](citation_guide.md)
- [Query Agent Guide](query_agent_guide.md)
- [Multi-Agent Architecture](../developers/agent_module.md)
