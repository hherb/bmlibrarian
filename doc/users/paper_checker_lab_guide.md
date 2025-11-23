# PaperChecker Laboratory User Guide

The PaperChecker Laboratory provides an interactive desktop GUI for testing and exploring the PaperChecker fact-checking system on individual medical abstracts. Built with PySide6/Qt, it offers PDF upload support, step-by-step workflow visualization, intermediate result inspection, and export capabilities.

## Overview

PaperChecker is a sophisticated fact-checking system that validates research claims in medical abstracts by:

1. Extracting core statements from the abstract
2. Generating counter-statements (semantic negations)
3. Searching for contradictory evidence using multiple strategies (semantic, HyDE, keyword)
4. Scoring and extracting citations from relevant documents
5. Generating counter-evidence reports
6. Analyzing verdicts (supports/contradicts/undecided)

The laboratory interface allows you to watch this process unfold in real-time and inspect each intermediate result.

## Quick Start

### Launch the Laboratory

```bash
# Desktop mode (default, using PySide6/Qt)
uv run python paper_checker_lab.py

# Enable debug logging
uv run python paper_checker_lab.py --debug

# Legacy Flet-based interface (deprecated)
uv run python paper_checker_lab.py --flet
uv run python paper_checker_lab.py --flet --view web --port 8080
```

### Basic Usage

1. **Text Input Tab**: Enter abstract text directly or fetch by PMID
2. **PDF Upload Tab**: Upload a PDF and extract the abstract automatically
3. Click **Check Abstract** to start the fact-checking process
4. Watch the workflow progress in the **Workflow** tab
5. Explore results in the **Results** tab with 5 sub-tabs
6. Export results as JSON or Markdown

## Interface Layout

The application uses a modern tabbed interface with four main tabs:

### Tab 1: Text Input

For entering abstract text directly or fetching from the database:

- **Model Selector**: Choose the LLM model for analysis
- **Refresh Models**: Update the list of available Ollama models
- **Abstract Text Area**: Multi-line text input for pasting abstracts
- **Character Count**: Shows current character count with validation
- **PMID Lookup**: Enter a PubMed ID and click "Fetch Abstract" to load from database
- **Browse...**: Open a dialog to search the database for documents
- **Check Abstract**: Start the fact-checking process
- **Clear**: Reset all inputs

### Tab 2: PDF Upload

For extracting abstracts from PDF files:

- **File Selection**: Browse for PDF files
- **Analyze PDF**: Extract abstract and metadata using AI
- **Analysis Status**: Shows progress of PDF processing
- **Extracted Content**:
  - Metadata display (title, authors, journal, year, PMID, DOI)
  - Editable abstract text (review/modify before checking)
- **Use in Input Tab**: Copy extracted abstract to Text Input tab
- **Check Abstract**: Start fact-checking directly from PDF

### Tab 3: Workflow

Real-time visualization of the 11-step workflow:

1. Initializing
2. Extracting statements
3. Generating counter-statements
4. Searching for counter-evidence
5. Scoring documents
6. Extracting citations
7. Generating counter-report
8. Analyzing verdict
9. Generating overall assessment
10. Saving results
11. Complete

Each step shows:
- Step number
- Status icon (⊡ pending, ⟳ running, ✓ complete, ✗ error)
- Step name
- Overall progress bar
- Abort button (to cancel processing)

### Tab 4: Results

Contains 5 sub-tabs for comprehensive result inspection:

#### Summary Sub-Tab
- **Overall Assessment**: AI-generated synthesis of findings
- **Processing Statistics**: Number of statements, verdict breakdown
- **Processing Info**: Model used, processing time, timestamp
- **Source Document**: Title, PMID, DOI of the checked abstract

#### Statements Sub-Tab
- **Statement Cards**: Each extracted statement displayed with:
  - Statement type badge (Hypothesis/Finding/Conclusion)
  - Confidence score
  - Full statement text
  - Counter-statement (semantic negation)
  - Search keywords

#### Evidence Sub-Tab
- **Search Statistics**: Documents found by each strategy
  - Semantic search count
  - HyDE search count
  - Keyword search count
  - Total (deduplicated)
- **Citation Cards**: Expandable cards showing:
  - Document title and metadata
  - Relevance score badge
  - Strategies that found it
  - Click to expand passage text

#### Verdicts Sub-Tab
- **Verdict Cards**: For each statement:
  - Verdict badge (Supports/Contradicts/Undecided)
  - Confidence level (High/Medium/Low)
  - Original statement text
  - Detailed rationale explaining the verdict

#### Export Sub-Tab
- **Export JSON**: Preview and save complete results as JSON
- **Export Markdown**: Preview and save as Markdown report
- **Copy Summary**: Copy brief summary to clipboard

## Workflow Details

### Statement Extraction

The system extracts 1-2 key testable statements from the abstract:
- Identifies hypotheses, findings, and conclusions
- Assigns confidence scores to each extraction
- Preserves original context

### Counter-Statement Generation

For each statement, generates:
- Semantically precise negation
- 2 hypothetical abstracts that would support the counter-claim
- Up to 10 search keywords

### Multi-Strategy Search

Three parallel search strategies:
- **Semantic Search**: Embedding-based conceptual similarity
- **HyDE Search**: Searches for documents similar to hypothetical supporting abstracts
- **Keyword Search**: Full-text search with extracted keywords

Results are deduplicated with provenance tracking.

### Document Scoring

Each found document is scored 1-5 for relevance:
- 5: Directly addresses the counter-claim
- 4: Strongly relevant evidence
- 3: Moderately relevant
- 2: Tangentially related
- 1: Not relevant

### Citation Extraction

From high-scoring documents, extracts:
- Specific passages supporting the counter-claim
- Full AMA-formatted citations
- Relevance scores

### Verdict Analysis

For each statement, determines:
- **Supports**: Evidence supports the original claim
- **Contradicts**: Evidence contradicts the original claim
- **Undecided**: Insufficient or mixed evidence

## Keyboard Shortcuts

- **Enter** in PMID field: Fetch abstract
- **Ctrl+V**: Paste into text areas
- **Escape**: Cancel dialogs

## Troubleshooting

### "Could not load models from Ollama"
- Ensure Ollama is running: `ollama serve`
- Check that models are available: `ollama list`

### "Failed to initialize PaperCheckerAgent"
- Verify database connection
- Check Ollama is accessible

### PDF Analysis Fails
- Ensure the PDF contains extractable text (not scanned images)
- Try a different PDF or enter the abstract manually

### Slow Processing
- Normal for complex abstracts (2-10 minutes)
- Use the Abort button to cancel if needed

## Configuration

The laboratory uses settings from `~/.bmlibrarian/config.json`:

```json
{
  "paper_checker": {
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

## Architecture

The PaperChecker Laboratory is built as a modular PySide6/Qt package:

```
paper_checker_lab/
├── __init__.py          # Lazy imports, module exports
├── constants.py         # UI constants (no magic numbers)
├── utils.py             # Pure utility functions
├── worker.py            # Background QThread workers
├── widgets.py           # Custom Qt widgets
├── dialogs.py           # Dialog classes
├── main_window.py       # Main application window
└── tabs/
    ├── input_tab.py     # Text input and PMID lookup
    ├── pdf_upload_tab.py # PDF upload and extraction
    ├── workflow_tab.py  # Workflow progress visualization
    └── results_tab.py   # Results display (5 sub-tabs)
```

## See Also

- [PaperChecker Architecture](../developers/paper_checker_architecture.md)
- [PaperChecker CLI Guide](paper_checker_cli_guide.md)
- [PDF Import Guide](pdf_import_guide.md)
