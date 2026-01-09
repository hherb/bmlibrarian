# Paper Reviewer Laboratory Guide

The Paper Reviewer Laboratory is a PySide6/Qt desktop application for comprehensive paper assessment. It provides an interactive interface for reviewing research papers with automated quality analysis, study type detection, and contradictory literature search.

## Overview

The Paper Reviewer Lab combines multiple assessment agents to provide a thorough review of scientific papers. It accepts input via DOI, PMID, PDF file, or pasted text, and produces a comprehensive report including:

- Brief summary (2-3 sentences)
- Core statement/hypothesis extraction
- PICO analysis (for clinical studies)
- PRISMA 2020 assessment (for systematic reviews)
- Paper weight and evidential strength
- Study quality assessment
- Strengths and weaknesses synthesis
- Contradictory literature search (optional)

## Quick Start

```bash
# Launch the laboratory
uv run python scripts/paper_reviewer_lab.py

# Or with debug logging
uv run python scripts/paper_reviewer_lab.py --debug

# Alternative: Run as module
uv run python -m bmlibrarian.lab.paper_reviewer_lab
```

## Interface Overview

The application has three main tabs:

### Input Tab

The Input tab provides multiple ways to specify a paper for review:

**DOI/PMID Sub-tab:**
- Enter a DOI (e.g., `10.1038/nature12373`)
- Enter a PMID (e.g., `12345678`)
- The system will fetch metadata from CrossRef, PubMed, or local database

**PDF Upload Sub-tab:**
- Select a PDF file from your filesystem
- Drag and drop a PDF file into the panel
- Full text will be extracted for analysis

**Text Input Sub-tab:**
- Paste abstract or full text directly
- Select a text/markdown file
- Useful for papers not indexed in databases

**Options:**
- **Model**: Select which Ollama model to use for analysis
- **Search PubMed**: Enable/disable contradictory evidence search

### Workflow Tab

The Workflow tab shows real-time progress through 11 assessment steps:

1. **Resolving Input** - Fetching document metadata and content
2. **Generating Summary** - Creating a brief 2-3 sentence overview
3. **Extracting Hypothesis** - Identifying core claims and statements
4. **Detecting Study Type** - Classifying the research methodology
5. **PICO Analysis** - Extracting Population, Intervention, Comparison, Outcome (clinical studies only)
6. **PRISMA Assessment** - Evaluating systematic review compliance (reviews only)
7. **Paper Weight Assessment** - Determining evidential weight
8. **Study Quality Assessment** - Evaluating trustworthiness and rigor
9. **Synthesizing Strengths/Weaknesses** - Summarizing key findings
10. **Searching for Contradictory Evidence** - Finding opposing literature (if enabled)
11. **Compiling Final Report** - Generating comprehensive output

**Features:**
- Progress bar showing overall completion
- Step cards that expand to show intermediate results
- Abort button to cancel long-running reviews
- Status indicators (pending, in progress, complete, skipped, failed)

### Results Tab

The Results tab displays the final comprehensive report:

**Report View:**
- Formatted markdown display
- Sections for each assessment component
- References and contradictory papers listed

**JSON View:**
- Raw JSON output for programmatic use
- Complete data structure access

**Export Options:**
- **Copy to Clipboard**: Copy current view text
- **Export Markdown**: Save as `.md` file
- **Export PDF**: Generate PDF document (uses BMLibrarian's PDF exporter)
- **Export JSON**: Save complete data as `.json`

## Study Type Detection

The system automatically detects study types and applies appropriate assessments:

| Study Type | PICO Applied | PRISMA Applied |
|------------|--------------|----------------|
| Randomized Controlled Trial | Yes | No |
| Clinical Trial | Yes | No |
| Cohort Study | Yes | No |
| Case-Control Study | Yes | No |
| Systematic Review | No | Yes |
| Meta-Analysis | No | Yes |
| Case Report | No | No |
| Laboratory Study | No | No |
| Review Article | No | No |

## Understanding Results

### Summary
A concise 2-3 sentence overview of the paper's key findings and methodology.

### Hypothesis/Core Statement
The main claim or hypothesis being tested or presented in the paper.

### PICO Components
For clinical studies:
- **P**opulation: Who was studied
- **I**ntervention: What was done
- **C**omparison: Control or alternative
- **O**utcome: What was measured

### PRISMA Compliance
For systematic reviews, a checklist of 27 items evaluating:
- Title, abstract, and introduction completeness
- Methods reporting (search strategy, eligibility criteria)
- Results reporting (study selection, data synthesis)
- Discussion and conclusion quality

### Paper Weight
Multi-dimensional assessment of evidential weight:
- Study design quality
- Sample size adequacy
- Methodological rigor
- Result clarity

### Study Quality
Overall trustworthiness evaluation considering:
- Bias risk
- Confounding control
- Reproducibility
- Statistical appropriateness

### Contradictory Papers
List of papers that may contradict the main findings, including:
- Title and authors
- Brief summary of contradiction
- Relevance score

## Configuration

The lab uses settings from `~/.bmlibrarian/config.json`:

```json
{
  "agents": {
    "paper_reviewer": {
      "model": "gpt-oss:20b",
      "temperature": 0.7
    }
  },
  "ollama": {
    "host": "http://localhost:11434"
  }
}
```

## Troubleshooting

### "Qt interface not available"
Ensure PySide6 is installed:
```bash
uv add PySide6
```

### "Failed to initialize agent"
Check that Ollama is running:
```bash
ollama serve
```

### No models appearing in dropdown
Refresh the models list by checking Ollama connection:
```bash
ollama list
```

### Review taking too long
- Use the Abort button to cancel
- Disable PubMed search for faster reviews
- Use a smaller/faster model (e.g., `medgemma4B_it_q8:latest`)

### Empty results for some sections
- PICO/PRISMA sections are skipped for non-applicable study types
- Check if the input text is sufficient for analysis
- Verify the document was resolved correctly

## See Also

- [Paper Reviewer Agent Architecture](../developers/paper_reviewer_architecture.md)
- [Study Assessment Guide](study_assessment_guide.md)
- [PRISMA 2020 Guide](prisma2020_guide.md)
- [PDF Export Guide](pdf_export_guide.md)
