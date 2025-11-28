# Systematic Review GUI User Guide

The Systematic Review GUI provides a checkpoint-based interface for conducting systematic literature reviews with the ability to monitor progress and resume from any checkpoint with modified parameters.

## Overview

Key features:
- **Checkpoint Management**: Resume from any checkpoint in the workflow
- **Parameter Modification**: Adjust thresholds and weights when resuming
- **Progress Monitoring**: Real-time tracking of review progress
- **Redundancy Prevention**: Existing work is preserved when resuming
- **Export Capabilities**: Export results to JSON or Markdown

## Quick Start

### Launching the GUI

```bash
# Start with default directory
uv run python systematic_review_gui.py

# Start with specific review directory
uv run python systematic_review_gui.py --review-dir ~/my_reviews

# Enable debug logging
uv run python systematic_review_gui.py --debug
```

### Starting a New Review

1. Select the "New Review" tab
2. Enter your research question (e.g., "What is the efficacy of metformin for type 2 diabetes?")
3. Optionally specify the purpose (e.g., "Clinical guideline development")
4. Add inclusion criteria (one per line):
   - Human studies
   - Randomized controlled trials
   - Published after 2015
5. Add exclusion criteria (one per line):
   - Animal studies
   - Case reports
   - Non-English language
6. Select an output directory
7. Adjust parameters if needed (thresholds, max results)
8. Click "Start New Review"

### Resuming from a Checkpoint

1. Select the "Resume from Checkpoint" tab
2. Browse to the review directory containing your checkpoints
3. Click "Refresh Checkpoints" to load available checkpoints
4. Select a checkpoint from the list
5. Review the checkpoint details to see what work has been done
6. Adjust parameters if needed (e.g., lower relevance threshold)
7. Click "Resume from Selected Checkpoint"

## Checkpoint Types

The systematic review workflow creates checkpoints at key phases:

| Checkpoint | Description | What's Saved |
|------------|-------------|--------------|
| **Search Strategy** | After query generation | Search plan, queries |
| **Initial Results** | After search execution | Found papers, deduplication stats |
| **Scoring Complete** | After relevance scoring | Scored papers, scores |
| **Quality Assessment** | After quality evaluation | Assessed papers, quality scores |

When you resume from a checkpoint, all work completed up to that point is preserved, and only subsequent phases are re-executed.

## Parameters

You can modify these parameters before starting a new review or resuming:

### Relevance Threshold (Default: 3.0)
- Range: 0.0 - 10.0
- Papers with scores below this threshold are excluded
- Lower values include more papers (higher recall)
- Higher values include fewer papers (higher precision)

### Quality Threshold (Default: 5.0)
- Range: 0.0 - 10.0
- Final quality gate for paper inclusion
- Papers must pass both relevance and quality thresholds

### Max Results per Query (Default: 100)
- Range: 10 - 1000
- Maximum documents retrieved per search query
- Higher values provide more comprehensive coverage
- Lower values run faster

## Progress Monitoring

During review execution:
- **Status Label**: Shows current operation
- **Progress Bar**: Shows estimated completion percentage
- **Workflow Steps**: Lists completed checkpoints and steps
- **Cancel Button**: Stops the current operation (saves checkpoints)

## Results Summary

After completion, the results summary shows:
- Total papers considered
- Papers passing each filter stage
- Final included/excluded counts
- Papers requiring human review
- Processing time

## Exporting Results

### JSON Export
Complete machine-readable output including:
- All paper metadata
- Scores and assessments
- Search strategy details
- Audit trail

### Markdown Export
Human-readable report with:
- Summary statistics
- Included paper list
- Excluded paper reasons
- PRISMA flow diagram data

## Best Practices

### For Comprehensive Reviews
1. Start with default parameters
2. Use broad inclusion criteria initially
3. Review results and adjust thresholds if needed
4. Resume with tighter criteria if too many papers included

### For Quick Scans
1. Increase relevance threshold (e.g., 5.0)
2. Reduce max results per query (e.g., 50)
3. Focus on high-quality papers only

### Handling Errors
- If a review fails, you can resume from the last successful checkpoint
- Adjust parameters that may have caused issues
- Check the error message for specific problems

## File Organization

The GUI creates the following structure:
```
~/systematic_reviews/
├── checkpoints/
│   ├── review_abc123_search_strategy.json
│   ├── review_abc123_initial_results.json
│   └── review_abc123_scoring_complete.json
├── systematic_review_20240115_143022.json
├── systematic_review_20240115_143022.md
└── ...
```

## Troubleshooting

### No Checkpoints Found
- Ensure you've selected the correct review directory
- Check that the directory contains a `checkpoints/` subdirectory
- Run a review to create checkpoints

### Review Fails to Start
- Verify Ollama is running and accessible
- Check database connection settings
- Ensure sufficient disk space for results

### Progress Stalls
- Some phases (scoring, quality assessment) can take time
- The LLM processes each paper sequentially
- Check Ollama logs for issues

## See Also

- [Systematic Review Agent Guide](systematic_review_guide.md) - CLI and programmatic usage
- [Systematic Review Filtering Guide](systematic_review_filtering_guide.md) - Detailed filtering options
- [Audit Validation Guide](audit_validation_guide.md) - Human validation interface
