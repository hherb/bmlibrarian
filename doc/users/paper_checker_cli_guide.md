# PaperChecker CLI User Guide

## Overview

The PaperChecker CLI (`paper_checker_cli.py`) is a command-line tool for fact-checking medical abstracts against biomedical literature. It analyzes abstracts, extracts core research claims, searches for contradictory evidence, and generates verdicts on whether the claims are supported or contradicted by existing literature.

## Quick Start

```bash
# Check abstracts from a JSON file
uv run python paper_checker_cli.py abstracts.json

# Check specific PMIDs from database
uv run python paper_checker_cli.py --pmid 12345678 23456789

# Export results to JSON and markdown
uv run python paper_checker_cli.py abstracts.json -o results.json --export-markdown reports/
```

## Installation

PaperChecker is part of BMLibrarian. Ensure you have:

1. Python 3.12 or higher
2. PostgreSQL with pgvector extension
3. Ollama running with required models

```bash
# Install dependencies
uv sync

# Verify installation
uv run python paper_checker_cli.py --help
```

## Input Formats

### JSON File Format

The input JSON file should contain a list of abstract objects:

```json
[
  {
    "abstract": "Background: Type 2 diabetes management requires effective long-term glycemic control. Objective: To compare the efficacy of metformin versus GLP-1 receptor agonists in long-term outcomes. Methods: Retrospective cohort study of 10,000 patients over 5 years. Results: Metformin demonstrated superior HbA1c reduction (1.5% vs 1.2%, p<0.001) and lower cardiovascular events (HR 0.75, 95% CI 0.65-0.85). Conclusion: Metformin shows superior long-term efficacy compared to GLP-1 agonists for T2DM.",
    "metadata": {
      "pmid": 12345678,
      "title": "Metformin vs GLP-1 in Type 2 Diabetes",
      "authors": ["Smith J", "Jones A"],
      "year": 2023,
      "journal": "Diabetes Care",
      "doi": "10.1234/example"
    }
  },
  {
    "abstract": "Another abstract text...",
    "metadata": {
      "pmid": 23456789
    }
  }
]
```

**Required fields:**
- `abstract`: Full abstract text (minimum 50 characters)

**Optional metadata fields:**
- `pmid`: PubMed ID
- `title`: Article title
- `authors`: List of author names
- `year`: Publication year
- `journal`: Journal name
- `doi`: Digital Object Identifier

### PMID-Based Input

Instead of a JSON file, you can specify PMIDs directly:

```bash
uv run python paper_checker_cli.py --pmid 12345678 23456789 34567890
```

The CLI will fetch abstracts from your local database for the specified PMIDs.

## Command-Line Options

### Input Options

| Option | Description |
|--------|-------------|
| `input_file` | JSON file with abstracts to check |
| `--pmid PMID [PMID ...]` | Check abstracts by PMID (fetch from database) |

### Output Options

| Option | Description |
|--------|-------------|
| `-o FILE, --output FILE` | Export results to JSON file |
| `--export-markdown DIR` | Export markdown reports to directory |

### Processing Options

| Option | Description |
|--------|-------------|
| `--max-abstracts N` | Limit number of abstracts to check |
| `--continue-on-error` | Continue processing if an abstract fails |
| `--quick` | Quick test mode (process max 5 abstracts) |
| `--config FILE` | Custom config file path |

### Display Options

| Option | Description |
|--------|-------------|
| `-v, --verbose` | Verbose output with debug messages |
| `--detailed` | Show detailed results for each abstract |
| `--no-stats` | Skip printing statistics summary |

## Usage Examples

### Basic Usage

```bash
# Check all abstracts in a JSON file
uv run python paper_checker_cli.py abstracts.json
```

### Export Results

```bash
# Export to JSON
uv run python paper_checker_cli.py abstracts.json -o results.json

# Export markdown reports (one per abstract)
uv run python paper_checker_cli.py abstracts.json --export-markdown reports/

# Export both formats
uv run python paper_checker_cli.py abstracts.json -o results.json --export-markdown reports/
```

### Testing and Development

```bash
# Quick test mode (only 5 abstracts)
uv run python paper_checker_cli.py abstracts.json --quick

# Verbose output for debugging
uv run python paper_checker_cli.py abstracts.json -v --detailed

# Continue on errors (for batch processing)
uv run python paper_checker_cli.py abstracts.json --continue-on-error
```

### Limiting Processing

```bash
# Process only first 10 abstracts
uv run python paper_checker_cli.py abstracts.json --max-abstracts 10
```

## Output Formats

### Console Output

The CLI displays progress and summary statistics:

```
Loading abstracts...
+ Loaded 10 abstracts

Initializing PaperCheckerAgent...
Testing connections...
+ All connections successful

Processing 10 abstracts...
============================================================
Checking abstracts: 100%|████████████| 10/10 [05:32<00:00, 33.2s/abstract]
============================================================

============================================================
SUMMARY STATISTICS
============================================================

Abstracts checked: 10
Statements extracted: 18
Average statements per abstract: 1.8

Verdict Distribution:
  Supports    :    5 ( 27.8%) [=====               ]
  Contradicts :    8 ( 44.4%) [=========           ]
  Undecided   :    5 ( 27.8%) [=====               ]

Confidence Distribution:
  High        :    7 ( 38.9%) [========            ]
  Medium      :    8 ( 44.4%) [=========           ]
  Low         :    3 ( 16.7%) [===                 ]

Search Statistics (aggregated):
  Documents found:  1,234
  Documents scored: 456
  Documents cited:  123
  Citation rate:    10.0%

============================================================
PROCESSING COMPLETE
============================================================
+ Completed: 10/10 abstracts
+ JSON results: results.json
+ Markdown reports: reports/
============================================================
```

### JSON Output Format

The JSON output contains complete results for each abstract:

```json
[
  {
    "original_abstract": "...",
    "source_metadata": {
      "pmid": 12345678,
      "title": "...",
      "authors": ["..."]
    },
    "statements": [
      {
        "text": "Metformin shows superior long-term efficacy...",
        "type": "conclusion",
        "confidence": 0.85,
        "order": 1
      }
    ],
    "results": [
      {
        "statement": "...",
        "counter_statement": "...",
        "search_stats": {
          "semantic": 45,
          "hyde": 38,
          "keyword": 22,
          "deduplicated": 78
        },
        "scoring_stats": {
          "total_scored": 78,
          "above_threshold": 15
        },
        "counter_report": "## Counter-Evidence Summary\n\n...",
        "verdict": {
          "verdict": "contradicts",
          "rationale": "Multiple studies found GLP-1 agonists...",
          "confidence": "high",
          "num_citations": 8
        }
      }
    ],
    "overall_assessment": "The abstract's main claim about metformin superiority is contradicted by...",
    "metadata": {
      "model": "gpt-oss:20b",
      "timestamp": "2024-01-15T10:30:00",
      "processing_time_seconds": 32.5
    }
  }
]
```

### Markdown Report Format

Each markdown report includes:

1. **Original Abstract** - The full abstract text
2. **Source Information** - PMID, title, DOI
3. **Analysis Results** - For each statement:
   - Extracted claim
   - Verdict (SUPPORTS/CONTRADICTS/UNDECIDED)
   - Confidence level
   - Rationale
   - Counter-evidence summary with citations
4. **Overall Assessment** - Aggregate findings

## Verdict Categories

### Verdict Values

| Verdict | Meaning |
|---------|---------|
| `supports` | Counter-evidence search found evidence that **supports** the original claim (no contradiction found) |
| `contradicts` | Counter-evidence search found evidence that **contradicts** the original claim |
| `undecided` | Insufficient or mixed evidence to make a determination |

### Confidence Levels

| Level | Meaning |
|-------|---------|
| `high` | Strong evidence from multiple high-quality sources |
| `medium` | Moderate evidence with some limitations |
| `low` | Limited evidence or conflicting sources |

## Error Handling

### Continue on Error

By default, processing stops on the first error. Use `--continue-on-error` for batch processing:

```bash
uv run python paper_checker_cli.py abstracts.json --continue-on-error
```

Failed abstracts are reported at the end:

```
============================================================
ERRORS (2 abstracts failed)
============================================================
  PMID 12345678: Connection timeout during search
  index 5: Abstract text too short (45 chars)
```

### Common Errors

| Error | Solution |
|-------|----------|
| `Input file not found` | Check file path exists |
| `Connection test failed` | Ensure Ollama and PostgreSQL are running |
| `Abstract too short` | Minimum 50 characters required |
| `Invalid JSON` | Validate JSON structure |

## Configuration

### Default Configuration

The CLI uses settings from `~/.bmlibrarian/config.json`:

```json
{
  "paper_checker": {
    "model": "gpt-oss:20b",
    "temperature": 0.3,
    "max_statements": 2,
    "score_threshold": 3.0,
    "search": {
      "semantic_limit": 50,
      "hyde_limit": 50,
      "keyword_limit": 50
    }
  }
}
```

### Custom Configuration

Use the `--config` option to specify a different configuration file:

```bash
uv run python paper_checker_cli.py abstracts.json --config custom_config.json
```

## Performance Considerations

- **Processing Time**: Expect 30-60 seconds per abstract depending on complexity
- **Memory Usage**: Each abstract is processed sequentially to minimize memory
- **Database Load**: Multi-strategy search performs multiple queries per statement
- **Quick Mode**: Use `--quick` for testing (limits to 5 abstracts)

## Troubleshooting

### Check Services

```bash
# Test Ollama
curl http://localhost:11434/api/tags

# Test PostgreSQL
psql -c "SELECT 1" your_database
```

### Verbose Mode

Enable verbose output for debugging:

```bash
uv run python paper_checker_cli.py abstracts.json -v --detailed
```

### Common Issues

1. **"No module named 'tqdm'"**: Run `uv sync` to install dependencies
2. **"Connection test failed"**: Check Ollama and PostgreSQL services
3. **"Abstract too short"**: Ensure abstracts have at least 50 characters
4. **"PMID not found"**: Verify PMIDs exist in your database

## See Also

- [PaperChecker Architecture](../developers/paperchecker_architecture.md)
- [PaperChecker Database Guide](papercheck_database_guide.md)
- [BMLibrarian Configuration Guide](configuration_guide.md)
