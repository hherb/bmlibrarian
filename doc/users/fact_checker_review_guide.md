# Fact-Checker Review GUI User Guide

## Overview

The Fact-Checker Review GUI is a desktop application for human reviewers to annotate and validate AI-generated fact-checking results. Built with the Flet framework, it provides an intuitive interface for reviewing biomedical statements, their AI evaluations, and supporting evidence.

## Features

- **Load Fact-Check Results**: Import JSON files containing fact-check results from the FactCheckerAgent
- **Statement-by-Statement Review**: Navigate through statements with clear progress tracking
- **Annotation Comparison**: View original annotations, AI evaluations, and provide human annotations side-by-side
- **Evidence Review**: Examine supporting citations with stance indicators (supports/contradicts/neutral)
- **Human Annotations**: Select yes/no/maybe annotations with optional explanations
- **Export Reviews**: Save human-annotated results to a new JSON file for analysis

## Getting Started

### Prerequisites

- Python >=3.12
- BMLibrarian installed with GUI dependencies
- Flet framework (automatically installed with BMLibrarian)

### Installation

The Fact-Checker Review GUI is included with BMLibrarian. No additional installation is required.

### Running the Application

```bash
# Start the Fact-Checker Review GUI
uv run python fact_checker_review_gui.py
```

The application will open in a desktop window.

## Using the Review Interface

### 1. Load Fact-Check Results

1. Click the **"Load Fact-Check Results"** button
2. Select a JSON file containing fact-check results
3. The file must contain a `results` array with fact-check evaluations

**Supported JSON Formats:**
- Output from `FactCheckerAgent.check_batch()` or `check_batch_from_file()`
- JSON files with a `results` array at the root level
- Direct JSON arrays of fact-check results

### 2. Review Each Statement

The review interface displays:

#### Progress Section
- **Statement counter**: Shows current position (e.g., "Statement 1 of 5")
- **Progress bar**: Visual indicator of completion

#### Statement Section
- The biomedical statement being fact-checked

#### Annotations Section (3 Columns)

**Column 1 - Original Annotation**
- Shows the original yes/no/maybe annotation from the input
- Purple badge displays the expected answer
- May show "N/A" if no original annotation was provided

**Column 2 - AI Fact-Checker**
- Shows the AI's evaluation (yes/no/maybe)
- Blue badge displays the AI's decision
- **AI Rationale**: Detailed explanation of the AI's reasoning

**Column 3 - Human Review**
- **Your Annotation**: Dropdown to select yes/no/maybe
- **Explanation**: Optional text field for justification
- Green section highlights this is your input

#### Citations Section
- Scrollable list of supporting evidence
- Each citation card shows:
  - **Stance icon and badge**:
    - ✓ Green = Supports the statement
    - ✗ Red = Contradicts the statement
    - ? Grey = Neutral/unclear
  - **Identifiers**: PMID, DOI, relevance score
  - **Citation text**: The relevant passage from the literature

### 3. Provide Human Annotations

For each statement:

1. **Review the evidence**: Read the statement, AI evaluation, rationale, and citations
2. **Select your annotation**: Choose yes/no/maybe from the dropdown
3. **Add explanation (optional)**: Describe your reasoning, especially if you disagree with the AI
4. **Navigate**: Use Previous/Next buttons to move between statements

**Annotation Guidelines:**
- **Yes**: The statement is supported by the evidence
- **No**: The statement is contradicted by the evidence
- **Maybe**: Evidence is insufficient, mixed, or inconclusive
- **Blank**: Leave blank if you want to skip this statement

### 4. Save Reviews

1. Click the **"Save Reviews"** button
2. Edit the output file path if desired (default: `<original>_reviewed_<timestamp>.json`)
3. Click **"Save"** to export your annotations

**Output JSON Format:**
```json
{
  "reviewed_statements": [
    {
      "statement": "The biomedical statement",
      "original_annotation": "yes",
      "ai_annotation": "yes",
      "ai_rationale": "AI's explanation",
      "human_annotation": "yes",
      "human_explanation": "Your explanation",
      "evidence_count": 3,
      "matches_expected": true
    }
  ],
  "metadata": {
    "source_file": "/path/to/original.json",
    "review_date": "2025-11-11T10:30:00",
    "total_statements": 5,
    "reviewed_count": 4
  }
}
```

## Navigation Shortcuts

- **Previous Button**: Go to the previous statement (disabled on first statement)
- **Next Button**: Go to the next statement (disabled on last statement)
- **Auto-save**: Your annotations are preserved as you navigate between statements

## Tips for Effective Review

1. **Read citations carefully**: The AI's evaluation is based on these evidence passages
2. **Check stance accuracy**: Verify that citation stance labels (supports/contradicts/neutral) are correct
3. **Consider evidence quality**: Look at relevance scores and source identifiers (PMID/DOI)
4. **Explain disagreements**: When your annotation differs from the AI's, add an explanation
5. **Review systematically**: Go through all statements before saving to ensure consistency
6. **Save frequently**: Export your reviews periodically to avoid data loss

## Common Use Cases

### Quality Control
Review AI fact-checking results to validate accuracy and identify systematic errors.

### Training Data Creation
Generate human-annotated datasets for improving fact-checking models.

### Disagreement Analysis
Identify cases where AI and human reviewers disagree to understand model limitations.

### Evidence Assessment
Evaluate the quality and relevance of citations extracted by the system.

## Troubleshooting

### Error Loading File
- **Symptom**: "Invalid JSON format" error
- **Solution**: Verify the file contains a `results` array or is a direct array of results
- **Check**: Ensure the file was generated by FactCheckerAgent

### Missing Citations
- **Symptom**: "No citations available" message
- **Cause**: Statement evaluation found no supporting evidence
- **Note**: This is normal for statements where no relevant literature was found

### Cannot Save Reviews
- **Symptom**: Save dialog shows error
- **Solution**: Check file path permissions and ensure directory exists
- **Tip**: Use absolute paths for reliability

## Integration with Fact-Checking Workflow

The review GUI integrates with BMLibrarian's fact-checking workflow:

1. **Generate Results**: Use `fact_checker_cli.py` or `FactCheckerAgent` to create fact-check results
2. **Review Results**: Load results in `fact_checker_review_gui.py` for human annotation
3. **Analyze Reviews**: Use the exported JSON for quality metrics and model improvement

**Example Workflow:**
```bash
# Step 1: Generate fact-check results
uv run python fact_checker_cli.py --input statements.json --output results.json

# Step 2: Review with GUI
uv run python fact_checker_review_gui.py
# (Load results.json, review, save as results_reviewed.json)

# Step 3: Analyze reviews
uv run python analyze_factcheck_progress.py results_reviewed.json
```

## Technical Details

### Supported JSON Schema

**Input (Fact-Check Results):**
- Must contain `results` array
- Each result must have: `statement`, `evaluation`, `reason`, `evidence_list`
- Optional fields: `expected_answer`, `matches_expected`, `confidence`, `metadata`

**Output (Reviewed Annotations):**
- Contains `reviewed_statements` array with human annotations
- Includes `metadata` with review statistics and source information

### Citation Stance Indicators

Citations are color-coded by stance:
- **Green border/background**: Supports the statement
- **Red border/background**: Contradicts the statement
- **Grey border/background**: Neutral or unclear stance

### UI Components

Built using Flet framework:
- **ExpansionTiles**: Collapsible sections for space efficiency
- **DataTables**: Structured display of evidence
- **Dialogs**: File selection and save operations
- **Responsive Layout**: Adapts to different screen sizes

## See Also

- **Fact-Checker User Guide**: `doc/users/fact_checker_guide.md`
- **Fact-Checker CLI**: `fact_checker_cli.py`
- **Developer Documentation**: `doc/developers/fact_checker_system.md`
- **Progress Analysis**: `analyze_factcheck_progress.py`

## Version History

- **v1.0.0** (2025-11-11): Initial release
  - Statement-by-statement review interface
  - Citation display with stance indicators
  - Human annotation input with explanations
  - JSON export with metadata
