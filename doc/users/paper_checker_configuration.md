# PaperChecker Configuration Guide

## Overview

PaperChecker uses the BMLibrarian configuration system, storing settings in `~/.bmlibrarian/config.json`. This guide covers all configurable options for tuning PaperChecker behavior.

## Configuration File Location

**Primary location:** `~/.bmlibrarian/config.json`

**Legacy fallback:** `bmlibrarian_config.json` in the current directory

## Configuration Structure

```json
{
  "paper_checker": {
    "model": "gpt-oss:20b",
    "temperature": 0.3,
    "top_p": 0.9,
    "max_statements": 2,
    "score_threshold": 3.0,
    "hyde": {
      "num_abstracts": 2,
      "max_keywords": 10
    },
    "search": {
      "semantic_limit": 50,
      "hyde_limit": 50,
      "keyword_limit": 50,
      "max_deduplicated": 100
    },
    "scoring": {
      "batch_size": 20,
      "early_stop_count": 20
    },
    "citation": {
      "min_score": 3,
      "max_citations_per_statement": 10,
      "min_relevance": 0.7
    },
    "report_max_tokens": 4000
  }
}
```

## Core Settings

### `model`

The Ollama model used for PaperChecker operations.

| Key | Default | Description |
|-----|---------|-------------|
| `model` | `"gpt-oss:20b"` | Main model for statement extraction, counter-generation, and verdict analysis |

**Recommendations:**
- Use larger models (20B+) for better statement extraction quality
- Smaller models (7B) work for testing but may miss nuanced claims

### `temperature`

Controls randomness in LLM outputs.

| Key | Default | Range | Description |
|-----|---------|-------|-------------|
| `temperature` | `0.3` | 0.0-1.0 | Lower = more deterministic, higher = more creative |

**Recommendations:**
- `0.1-0.3`: Best for factual extraction and analysis
- `0.5-0.7`: More varied counter-statement generation
- Avoid `> 0.8`: May produce inconsistent results

### `top_p`

Nucleus sampling parameter.

| Key | Default | Range | Description |
|-----|---------|-------|-------------|
| `top_p` | `0.9` | 0.0-1.0 | Cumulative probability threshold for token selection |

### `max_statements`

Maximum number of statements to extract per abstract.

| Key | Default | Range | Description |
|-----|---------|-------|-------------|
| `max_statements` | `2` | 1-10 | Limits extracted statements per abstract |

**Recommendations:**
- `2`: Balances thoroughness with processing time
- `1`: Focus on the most important claim only
- `3+`: For comprehensive analysis of complex abstracts

### `score_threshold`

Minimum relevance score for document inclusion.

| Key | Default | Range | Description |
|-----|---------|-------|-------------|
| `score_threshold` | `3.0` | 1.0-5.0 | Documents must score >= this to be processed |

**Recommendations:**
- `3.0`: Good balance of precision and recall
- `4.0`: Higher precision, fewer documents
- `2.0`: More documents, may include noise

## HyDE Settings

HyDE (Hypothetical Document Embeddings) generates synthetic abstracts for improved search.

```json
{
  "hyde": {
    "num_abstracts": 2,
    "max_keywords": 10
  }
}
```

### `num_abstracts`

Number of hypothetical abstracts to generate per counter-statement.

| Key | Default | Range | Description |
|-----|---------|-------|-------------|
| `num_abstracts` | `2` | 1-5 | More = broader search, higher latency |

### `max_keywords`

Maximum keywords to extract for keyword search.

| Key | Default | Range | Description |
|-----|---------|-------|-------------|
| `max_keywords` | `10` | 5-20 | Keywords used for full-text search strategy |

## Search Settings

Controls the multi-strategy search behavior.

```json
{
  "search": {
    "semantic_limit": 50,
    "hyde_limit": 50,
    "keyword_limit": 50,
    "max_deduplicated": 100
  }
}
```

### Strategy Limits

| Key | Default | Description |
|-----|---------|-------------|
| `semantic_limit` | `50` | Max documents from semantic (embedding) search |
| `hyde_limit` | `50` | Max documents from HyDE search |
| `keyword_limit` | `50` | Max documents from keyword search |
| `max_deduplicated` | `100` | Max unique documents after deduplication |

**Recommendations:**
- Lower limits for faster processing
- Higher limits for comprehensive literature coverage
- Total unique documents limited by `max_deduplicated`

## Scoring Settings

Controls document scoring behavior.

```json
{
  "scoring": {
    "batch_size": 20,
    "early_stop_count": 20
  }
}
```

### `batch_size`

Number of documents to score in each batch.

| Key | Default | Range | Description |
|-----|---------|-------|-------------|
| `batch_size` | `20` | 5-50 | Larger batches = fewer API calls, more memory |

### `early_stop_count`

Stop scoring after finding this many documents above threshold.

| Key | Default | Range | Description |
|-----|---------|-------|-------------|
| `early_stop_count` | `20` | 0-100 | `0` = no early stopping |

**Recommendations:**
- `20`: Good balance for most cases
- `0`: Score all documents (slower but comprehensive)
- Higher values for thorough literature searches

## Citation Settings

Controls citation extraction from scored documents.

```json
{
  "citation": {
    "min_score": 3,
    "max_citations_per_statement": 10,
    "min_relevance": 0.7
  }
}
```

### `min_score`

Minimum document score for citation extraction.

| Key | Default | Range | Description |
|-----|---------|-------|-------------|
| `min_score` | `3` | 1-5 | Only extract citations from documents scoring >= this |

### `max_citations_per_statement`

Maximum citations to extract per statement.

| Key | Default | Range | Description |
|-----|---------|-------|-------------|
| `max_citations_per_statement` | `10` | 1-50 | Limits citations in counter-report |

### `min_relevance`

Minimum relevance score for citation passage.

| Key | Default | Range | Description |
|-----|---------|-------|-------------|
| `min_relevance` | `0.7` | 0.0-1.0 | Filters low-relevance passages |

## Report Settings

Controls counter-report generation.

| Key | Default | Description |
|-----|---------|-------------|
| `report_max_tokens` | `4000` | Maximum tokens for generated counter-report |

## Agent-Specific Models

PaperChecker reuses BMLibrarian's scoring and citation agents. Configure their models separately:

```json
{
  "models": {
    "paper_checker_agent": "gpt-oss:20b",
    "scoring_agent": "medgemma4B_it_q8:latest",
    "citation_agent": "gpt-oss:20b"
  }
}
```

| Agent | Recommended Model | Purpose |
|-------|-------------------|---------|
| `paper_checker_agent` | `gpt-oss:20b` | Statement extraction, counter-generation, verdicts |
| `scoring_agent` | `medgemma4B_it_q8:latest` | Fast document relevance scoring |
| `citation_agent` | `gpt-oss:20b` | Citation passage extraction |

## Example Configurations

### Fast Testing Configuration

```json
{
  "paper_checker": {
    "model": "medgemma4B_it_q8:latest",
    "temperature": 0.3,
    "max_statements": 1,
    "score_threshold": 4.0,
    "search": {
      "semantic_limit": 20,
      "hyde_limit": 20,
      "keyword_limit": 20,
      "max_deduplicated": 30
    },
    "scoring": {
      "early_stop_count": 10
    },
    "citation": {
      "max_citations_per_statement": 5
    }
  }
}
```

### Comprehensive Analysis Configuration

```json
{
  "paper_checker": {
    "model": "gpt-oss:20b",
    "temperature": 0.2,
    "max_statements": 3,
    "score_threshold": 2.5,
    "hyde": {
      "num_abstracts": 3,
      "max_keywords": 15
    },
    "search": {
      "semantic_limit": 100,
      "hyde_limit": 100,
      "keyword_limit": 100,
      "max_deduplicated": 200
    },
    "scoring": {
      "batch_size": 30,
      "early_stop_count": 0
    },
    "citation": {
      "min_score": 3,
      "max_citations_per_statement": 20,
      "min_relevance": 0.6
    },
    "report_max_tokens": 6000
  }
}
```

### High-Precision Configuration

```json
{
  "paper_checker": {
    "model": "gpt-oss:20b",
    "temperature": 0.1,
    "max_statements": 2,
    "score_threshold": 4.0,
    "search": {
      "semantic_limit": 50,
      "hyde_limit": 50,
      "keyword_limit": 50,
      "max_deduplicated": 100
    },
    "scoring": {
      "early_stop_count": 15
    },
    "citation": {
      "min_score": 4,
      "max_citations_per_statement": 8,
      "min_relevance": 0.8
    }
  }
}
```

## Environment Variables

Database connection settings come from environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_DB` | `knowledgebase` | Database name |
| `POSTGRES_USER` | - | Database user |
| `POSTGRES_PASSWORD` | - | Database password |
| `POSTGRES_HOST` | `localhost` | Database host |
| `POSTGRES_PORT` | `5432` | Database port |

## CLI Configuration Override

Use the `--config` option to specify an alternative configuration file:

```bash
uv run python paper_checker_cli.py abstracts.json --config /path/to/custom_config.json
```

## Validating Configuration

Test your configuration by running:

```bash
# Check that services are accessible
uv run python paper_checker_cli.py --pmid 12345678 --quick -v

# The verbose (-v) flag will show configuration being used
```

## Performance Tuning

### For Faster Processing

1. Reduce `max_statements` to 1-2
2. Lower search limits (20-30 per strategy)
3. Enable early stopping (`early_stop_count: 15`)
4. Use faster models for scoring
5. Reduce `max_citations_per_statement`

### For More Comprehensive Analysis

1. Increase `max_statements` to 3-4
2. Raise search limits (100+ per strategy)
3. Disable early stopping (`early_stop_count: 0`)
4. Use larger models throughout
5. Increase `max_citations_per_statement`

### For Better Precision

1. Raise `score_threshold` to 4.0
2. Increase `min_score` for citations
3. Lower `temperature` to 0.1-0.2
4. Raise `min_relevance` for passages
5. Use larger, more capable models

## See Also

- [PaperChecker User Guide](paper_checker_guide.md) - Overview and quick start
- [CLI Guide](paper_checker_cli_guide.md) - Command-line options
- [Laboratory Guide](paper_checker_lab_guide.md) - Interactive interface
- [Architecture Documentation](../developers/paper_checker_architecture.md) - Technical details
