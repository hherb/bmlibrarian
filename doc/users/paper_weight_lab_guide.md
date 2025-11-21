# Paper Weight Assessment Laboratory User Guide

## Overview

The Paper Weight Assessment Laboratory is a graphical application for evaluating and validating paper weight assessments. It provides a visual interface for:

- Searching and selecting documents from the database
- Running paper weight assessments with real-time progress tracking
- Inspecting detailed audit trails for each assessment
- Configuring dimension weights
- Exporting results to Markdown or JSON formats

## Getting Started

### Launching the Laboratory

```bash
uv run python paper_weight_lab.py
```

### System Requirements

- Python 3.12 or later
- PySide6 (Qt for Python)
- PostgreSQL database with BMLibrarian schema
- Ollama server running for LLM-based assessments

## User Interface

### Document Selection

The top section provides two ways to select documents:

1. **Search**: Enter a PMID, DOI, or title keywords and press Enter or click "Search"
   - Numeric queries are treated as PMIDs
   - Queries starting with "10." or containing "/" are treated as DOIs
   - Other queries search by title

2. **Recent Assessments**: Select from the dropdown of recently assessed documents

### Selected Document Display

Once a document is selected, you'll see:
- **Title**: Full document title
- **Metadata**: Authors, year, PMID, DOI
- **Show Abstract**: Toggle to view the abstract

### Action Buttons

- **Assess Paper Weight**: Run a new assessment (uses cache if available)
- **Force Re-assess**: Run assessment without using cached results
- **Configure Weights**: Adjust dimension weights for the final score calculation

### Assessment Progress

During assessment, progress indicators show the status of each dimension:
- ⊡ Pending
- ⟳ Analyzing...
- ✓ Complete with score
- ✗ Error

### Results Visualization

After assessment completes:
- **Final Weight**: Combined score (0-10 scale)
- **Version**: Assessment methodology version
- **Timestamp**: When the assessment was performed
- **Dimension Breakdown**: Individual scores for each dimension

### Audit Trail

The expandable tree view shows:
- Each dimension with its total score
- Component assessments that contributed to the score
- Extracted values and evidence text
- LLM reasoning (where applicable)

#### Accessing Full Text

No information is hidden by truncation. To view complete text:

1. **Tooltips**: Hover over any cell to see the full untruncated text
2. **Double-click**: Double-click any row to open a dialog with full details
3. **Right-click**: Right-click for context menu options:
   - "Copy Cell Text" - Copy the cell content to clipboard
   - "View Full Details..." - Open the full text dialog

### Export Options

- **Export Report (Markdown)**: Generate a human-readable report
- **Export JSON**: Export structured data for further analysis

## Assessment Dimensions

The paper weight assessment evaluates five dimensions:

### 1. Study Design (25% weight)
Evaluates the research methodology:
- Systematic review/meta-analysis: 10/10
- Randomized controlled trial: 8/10
- Prospective cohort: 6/10
- Retrospective cohort: 5/10
- Case-control: 4/10
- Cross-sectional: 3/10
- Case series: 2/10
- Case report: 1/10

### 2. Sample Size (15% weight)
Evaluates statistical power:
- Base score from log10(n) * 2.0
- Bonus for power calculation: +2.0
- Bonus for confidence interval reporting: +0.5

### 3. Methodological Quality (30% weight)
LLM-assessed components:
- Randomization: up to 2.0 points
- Blinding: up to 3.0 points
- Allocation concealment: up to 1.5 points
- Protocol preregistration: up to 1.5 points
- Intention-to-treat analysis: up to 1.0 point
- Attrition handling: up to 1.0 point

### 4. Risk of Bias (20% weight)
LLM-assessed domains (inverted scale: 10 = low risk):
- Selection bias: up to 2.5 points
- Performance bias: up to 2.5 points
- Detection bias: up to 2.5 points
- Reporting bias: up to 2.5 points

### 5. Replication Status (10% weight)
Based on database records:
- Not replicated: 0/10
- Replicated once (comparable quality): 5/10
- Replicated 2+ times: 8/10
- Replicated with higher quality: 10/10

## Configuring Dimension Weights

Click "Configure Weights" to adjust the relative importance of each dimension:

1. Use sliders to adjust each weight (0.00 to 1.00)
2. Ensure weights sum to 1.0 (shown in status)
3. Click OK to apply
4. Use "Force Re-assess" to apply new weights to current document

## Tips for Effective Use

### Batch Validation
1. Keep a list of diverse papers (RCTs, cohorts, case reports)
2. Assess each and compare scores
3. Use the audit trail to identify scoring issues
4. Refine prompts or weights as needed

### Identifying Issues
- Check the audit trail for unexpected values
- Review LLM reasoning for accuracy
- Compare similar papers to ensure consistency

### Export and Analysis
- Export JSON for programmatic analysis
- Export Markdown for reports or documentation
- Use the audit trail to document assessment decisions

## Troubleshooting

### Agent Not Available
If you see "Paper weight assessment agent is not initialized":
- Verify Ollama is running
- Check your `~/.bmlibrarian/config.json` configuration
- Ensure the required model is available

### Database Connection Errors
If searches return no results or assessments fail:
- Verify PostgreSQL is running
- Check database credentials in your environment
- Ensure the `paper_weights` schema exists

### LLM Timeout
If assessments take too long or timeout:
- Check Ollama server status
- Try a smaller/faster model
- Check system resources

## Keyboard Shortcuts

- **Enter** in search box: Quick search
- **Escape**: Close dialogs

## Related Documentation

- [Paper Weight Implementation Guide](../developers/paper_weight_implementation_guide.md)
- [Paper Weight Step 7: Qt Laboratory GUI](../developers/paper_weight_step7_qt_laboratory_gui.md)
- [Study Assessment Guide](study_assessment_guide.md)
