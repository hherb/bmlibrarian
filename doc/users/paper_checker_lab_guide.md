# PaperChecker Laboratory User Guide

The PaperChecker Laboratory provides an interactive GUI for testing and exploring the PaperChecker fact-checking system on individual medical abstracts. It offers step-by-step workflow visualization, intermediate result inspection, and export capabilities.

## Overview

PaperChecker is a sophisticated fact-checking system that validates research claims in medical abstracts by:

1. Extracting core statements from the abstract
2. Generating counter-statements (negations)
3. Searching for contradictory evidence using multiple strategies
4. Scoring and extracting citations from relevant documents
5. Generating counter-evidence reports
6. Analyzing verdicts (supports/contradicts/undecided)

The laboratory interface allows you to watch this process unfold in real-time and inspect each intermediate result.

## Quick Start

### Launch the Laboratory

```bash
# Desktop mode (native window)
uv run python paper_checker_lab.py

# Web browser mode
uv run python paper_checker_lab.py --view web

# Web mode with custom port
uv run python paper_checker_lab.py --view web --port 8080

# Enable debug logging
uv run python paper_checker_lab.py --debug
```

### Basic Usage

1. **Enter abstract text** directly in the text area, or
2. **Enter a PMID** to fetch an abstract from your database
3. Click **Check Abstract** to start the fact-checking process
4. Watch the workflow progress in real-time
5. Explore results in the tabbed display
6. Export results as JSON or Markdown

## Interface Layout

### Header Section

- **Title**: "PaperChecker Laboratory"
- **Subtitle**: Brief description of the application

### Input Section

- **Model Selector**: Choose the LLM model for analysis
- **Refresh Models**: Update the list of available Ollama models
- **Abstract Text**: Multi-line text area for pasting abstracts
- **PMID Field**: Enter a PubMed ID to fetch from database
- **Check Abstract**: Start the fact-checking process
- **Clear**: Reset all inputs and results

### Progress Section

- **Progress Bar**: Visual progress indicator
- **Status Text**: Current operation description

### Main Content Area

#### Workflow Panel (Left)

Displays step-by-step progress through the fact-checking workflow:

- Extracting statements
- Generating counter-statements
- Searching for counter-evidence
- Scoring documents
- Extracting citations
- Generating counter-report
- Analyzing verdict
- Generating overall assessment
- Complete

Each step shows:
- Status icon (pending/in-progress/complete)
- Step name
- Progress percentage

#### Results Panel (Right)

Tabbed display with five tabs:

**Summary Tab**
- Overall assessment text
- Statistics (statements, verdicts, citations)
- Source metadata (PMID, DOI, title)
- Processing information (model, time)

**Statements Tab**
- Extracted statements from the abstract
- Statement type (hypothesis/finding/conclusion)
- Extraction confidence
- Generated counter-statement
- Search keywords

**Evidence Tab**
- Counter-evidence reports for each statement
- Search statistics (semantic/HyDE/keyword results)
- Report summary with inline citations
- Individual citation cards with passages

**Verdicts Tab**
- Verdict for each statement (supports/contradicts/undecided)
- Confidence level (high/medium/low)
- Rationale explaining the verdict
- Citation count

**Export Tab**
- Export as JSON button
- Export as Markdown button
- Copy to Clipboard button
- Output display area

## Working with Results

### Understanding Verdicts

Each statement receives one of three verdicts:

- **SUPPORTS**: Counter-evidence found that supports the opposite of the claim
- **CONTRADICTS**: Evidence found that contradicts the original statement
- **UNDECIDED**: Insufficient or mixed evidence to make a determination

Confidence levels:

- **High**: Strong, consistent evidence with multiple citations
- **Medium**: Moderate evidence or some conflicting results
- **Low**: Limited evidence or primarily indirect support

### Interpreting Search Statistics

The evidence tab shows document counts from three search strategies:

- **Semantic**: Embedding-based conceptual similarity search
- **HyDE**: Hypothetical Document Embeddings for structural similarity
- **Keyword**: Traditional full-text keyword matching

Higher counts across multiple strategies typically indicate a well-researched topic with substantial literature.

### Citation Quality

Citations include:

- Full bibliographic reference (AMA format)
- Extracted passage supporting the counter-claim
- Document relevance score (1-5)
- Source information (PMID, DOI)

## Exporting Results

### JSON Export

Produces structured data including:
- Original abstract
- Source metadata
- All extracted statements
- Counter-statements with keywords
- Search statistics
- Counter-evidence reports
- Verdicts with rationale
- Overall assessment
- Processing metadata

### Markdown Export

Produces human-readable report with:
- Formatted abstract
- Statement-by-statement analysis
- Verdicts with explanations
- References section
- Search statistics

### Clipboard

Copies a brief summary including the overall assessment for quick sharing.

## Configuration

The laboratory uses the same configuration as other BMLibrarian components:

**Configuration file**: `~/.bmlibrarian/config.json`

Key settings:
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

## Troubleshooting

### Agent Not Initialized

**Symptom**: Error message about agent initialization failure

**Solutions**:
1. Verify Ollama is running: `curl http://localhost:11434/api/tags`
2. Check model availability in Ollama
3. Verify database connection in `.env` file
4. Check logs for detailed error messages

### PMID Not Found

**Symptom**: Error when entering a PMID

**Solutions**:
1. Verify the PMID is correct
2. Ensure the document is in your database
3. Try importing the document first using PubMed import CLI

### Slow Processing

**Symptom**: Long wait times during fact-checking

**Solutions**:
1. Use a faster model for initial testing
2. Reduce `max_statements` in configuration
3. Lower search limits in configuration
4. Ensure sufficient system resources

### No Counter-Evidence Found

**Symptom**: Empty reports or "undecided" verdicts for all statements

**Possible causes**:
1. Statement is well-supported by existing literature
2. Topic has limited coverage in your database
3. Search threshold may be too high

**Solutions**:
1. Expand your document database
2. Lower `score_threshold` in configuration
3. Verify database has relevant domain coverage

## Best Practices

1. **Start with known abstracts**: Test with abstracts from your database to verify the system is working
2. **Compare PMID vs. pasted text**: Using PMIDs preserves metadata and enables better citation tracking
3. **Review all tabs**: Each tab provides different insights into the analysis
4. **Check search statistics**: Low document counts may indicate gaps in your database
5. **Export for reference**: Save results for comparison or documentation

## Related Documentation

- [PaperChecker CLI Guide](paper_checker_cli_guide.md) - Batch processing interface
- [PaperChecker Architecture](../developers/paper_checker_architecture.md) - Technical details
- [Document Embedding Guide](document_embedding_guide.md) - Database preparation
- [Configuration Guide](configuration_guide.md) - System configuration

## Support

For issues or questions:
- Report bugs: https://github.com/hherb/bmlibrarian/issues
- Check logs with `--debug` flag for detailed information
