# PaperChecker User Guide

## Overview

PaperChecker is a sophisticated fact-checking system for medical abstracts that validates research claims by systematically searching for and analyzing contradictory evidence. It combines statement extraction, counter-evidence search, and verdict generation to provide comprehensive analysis of biomedical claims.

## What is PaperChecker?

PaperChecker analyzes medical abstracts to determine if their core claims are supported by the broader literature. For any given abstract, it:

1. **Extracts statements**: Identifies core research claims, hypotheses, and conclusions
2. **Generates counter-claims**: Creates semantically precise negations of each claim
3. **Searches for evidence**: Uses multi-strategy search (semantic, HyDE, keyword)
4. **Scores documents**: Evaluates relevance of found documents to counter-claims
5. **Extracts citations**: Pulls specific passages supporting counter-claims
6. **Generates reports**: Synthesizes citations into evidence reports
7. **Analyzes verdicts**: Provides supports/contradicts/undecided classification

## Key Features

- **Automated Statement Extraction**: AI-powered identification of core research claims
- **Multi-Strategy Search**: Semantic embeddings, HyDE abstracts, and keyword matching
- **Provenance Tracking**: Know which search strategy found each document
- **Comprehensive Analysis**: Document scores, citations, and synthesized reports
- **Clear Verdicts**: Evidence-based classification with confidence levels
- **Multiple Interfaces**: CLI for batch processing, Laboratory for interactive use
- **Database Persistence**: All results stored for later review and analysis

## Quick Start

### CLI Usage

```bash
# Check abstracts from JSON file
uv run python paper_checker_cli.py abstracts.json

# Check specific PMIDs from database
uv run python paper_checker_cli.py --pmid 12345678 23456789

# Export results to JSON and markdown
uv run python paper_checker_cli.py abstracts.json -o results.json --export-markdown reports/

# Quick test mode (max 5 abstracts)
uv run python paper_checker_cli.py abstracts.json --quick
```

### Laboratory Usage

```bash
# Launch interactive laboratory (desktop mode)
uv run python paper_checker_lab.py

# Web browser mode
uv run python paper_checker_lab.py --view web

# Enable debug logging
uv run python paper_checker_lab.py --debug
```

## Understanding Results

### Verdict Types

| Verdict | Meaning |
|---------|---------|
| **SUPPORTS** | Counter-evidence search found evidence that *supports* the original claim (no contradiction found) |
| **CONTRADICTS** | Counter-evidence search found evidence that *contradicts* the original claim |
| **UNDECIDED** | Insufficient or mixed evidence to make a determination |

### Confidence Levels

| Level | Meaning |
|-------|---------|
| **High** | Strong, consistent evidence from multiple high-quality sources |
| **Medium** | Moderate evidence with some limitations or minor conflicts |
| **Low** | Limited evidence, conflicting sources, or uncertain findings |

### Search Statistics

Results include search statistics showing how documents were found:

- **Semantic**: Documents found via embedding-based conceptual similarity
- **HyDE**: Documents found via hypothetical document matching
- **Keyword**: Documents found via traditional full-text search
- **Deduplicated**: Unique documents across all strategies

Higher counts across multiple strategies typically indicate a well-researched topic with substantial literature coverage.

## Example Workflow

### Input Abstract

```
Background: Type 2 diabetes management requires effective long-term
glycemic control. Objective: To compare the efficacy of metformin versus
GLP-1 receptor agonists. Results: Metformin demonstrated superior HbA1c
reduction (1.5% vs 1.2%, p<0.001). Conclusion: Metformin shows superior
efficacy compared to GLP-1 agonists for T2DM.
```

### PaperChecker Analysis

**Statement Extracted:**
> "Metformin demonstrates superior efficacy to GLP-1 agonists in T2DM"

**Counter-Statement Generated:**
> "GLP-1 agonists are superior or equivalent to metformin in T2DM"

**Search Results:**
- Semantic search: 47 documents
- HyDE search: 38 documents
- Keyword search: 22 documents
- Deduplicated: 78 unique documents

**Scoring Results:**
- 78 documents scored
- 15 documents above threshold (score >= 3)

**Citations Extracted:**
- 8 high-relevance citations supporting counter-claim

**Verdict:** CONTRADICTS (High Confidence)

**Rationale:**
> Multiple randomized controlled trials from 2022-2023 demonstrate GLP-1
> agonist superiority over metformin in HbA1c reduction, cardiovascular
> outcomes, and weight management. Meta-analyses confirm these findings
> with high statistical significance.

## Input File Format

### JSON File Structure

```json
[
  {
    "abstract": "Full abstract text (minimum 50 characters)...",
    "metadata": {
      "pmid": 12345678,
      "title": "Study Title",
      "authors": ["Smith J", "Jones A"],
      "year": 2023,
      "journal": "Journal Name",
      "doi": "10.1234/example"
    }
  }
]
```

**Required fields:**
- `abstract`: Full abstract text (minimum 50 characters)

**Optional metadata fields:**
- `pmid`: PubMed ID (integer)
- `title`: Article title
- `authors`: List of author names
- `year`: Publication year (integer)
- `journal`: Journal name
- `doi`: Digital Object Identifier

## Best Practices

### When to Use PaperChecker

**Good use cases:**
- Validating claims from new preprints before citation
- Auditing systematic reviews for missed contradictory evidence
- Identifying controversial findings that need further investigation
- Training data quality assessment for AI/ML models
- Literature review to understand evidence landscape

**Not recommended for:**
- Extremely recent findings (< 3 months) where literature may not exist
- Highly specialized niche topics with limited literature coverage
- Methodological statements without empirical claims
- Non-biomedical content

### Interpreting Results

1. **Check confidence levels**: High confidence verdicts are more reliable
2. **Review citations**: Examine the specific evidence found
3. **Consider database coverage**: PaperChecker searches your database, not all literature
4. **Apply domain expertise**: Always use your medical knowledge to interpret results
5. **Check provenance**: Multi-strategy matches may indicate stronger evidence

### Optimizing Performance

1. **Ensure good database coverage**: More documents = better counter-evidence search
2. **Generate embeddings**: Semantic search requires document embeddings
3. **Use appropriate models**: Larger models provide better statement extraction
4. **Adjust thresholds**: Lower `score_threshold` for more results, higher for precision

## Architecture Overview

PaperChecker uses a hybrid architecture combining patterns from CounterfactualAgent and FactCheckerAgent:

```
┌─────────────────────────────────────────────────────────┐
│              PaperCheckerAgent                          │
│  (Main orchestrator, inherits from BaseAgent)           │
└───────────────────┬─────────────────────────────────────┘
                    │
        ┌───────────┼───────────┐
        │           │           │
┌───────▼─────┐ ┌──▼────────┐ ┌▼──────────────┐
│ Statement   │ │ Counter-  │ │ HyDE          │
│ Extractor   │ │ Statement │ │ Generator     │
│             │ │ Generator │ │               │
└─────────────┘ └───────────┘ └───────────────┘
                    │
            ┌───────┼───────┐
            │       │       │
    ┌───────▼───┐ ┌▼───────▼────┐ ┌────────────┐
    │ Search    │ │ Document    │ │ Citation   │
    │Coordinator│ │ Scoring     │ │ Extractor  │
    │           │ │ Agent       │ │            │
    └───────────┘ └─────────────┘ └────────────┘
                    │
            ┌───────┼───────┐
            │               │
    ┌───────▼────┐  ┌──────▼────────┐
    │ Counter-   │  │ Verdict       │
    │ Report     │  │ Analyzer      │
    │ Generator  │  │               │
    └────────────┘  └───────────────┘
                    │
            ┌───────▼────────┐
            │ PaperCheckDB   │
            │ (PostgreSQL)   │
            └────────────────┘
```

## Troubleshooting

### "No documents found"

**Causes:**
- Database may not contain relevant literature
- Search terms too specific
- Embeddings not generated for documents

**Solutions:**
- Expand your document database with relevant literature
- Verify embeddings exist: `uv run python embed_documents_cli.py status`
- Try broader search terms in manual queries first

### "All undecided verdicts"

**Causes:**
- Genuinely mixed evidence in the literature
- Topic too specialized for database coverage
- Counter-statements not well-formed

**Solutions:**
- Check that database has adequate domain coverage
- Lower `score_threshold` to capture more documents
- Review counter-statements for semantic accuracy

### Slow processing

**Causes:**
- Each abstract takes 2-5 minutes due to multi-step workflow
- Large batch sizes strain resources

**Solutions:**
- Use `--quick` mode for testing (limits to 5 abstracts)
- Process abstracts in smaller batches
- Use faster models for scoring if available
- Ensure sufficient system resources (CPU, RAM, GPU)

### Connection errors

**Solutions:**
- Verify Ollama is running: `curl http://localhost:11434/api/tags`
- Check PostgreSQL: `psql -c "SELECT 1" your_database`
- Verify model availability in Ollama
- Check `.env` file for correct database credentials

## See Also

- [CLI Guide](paper_checker_cli_guide.md) - Detailed CLI usage and options
- [Laboratory Guide](paper_checker_lab_guide.md) - Interactive interface guide
- [Configuration Guide](paper_checker_configuration.md) - Configuration reference
- [Architecture Documentation](../developers/paper_checker_architecture.md) - Technical details
- [Database Schema](../developers/paper_checker_database.md) - Database structure
