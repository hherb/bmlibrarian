# Audit Trail Validation GUI - User Guide

## Overview

The Audit Trail Validation GUI enables human reviewers to evaluate the correctness of automated decisions in BMLibrarian's systematic review workflow. This is essential for:

1. **Quality Assurance**: Ensuring automated evaluations meet research standards
2. **Benchmarking**: Measuring AI accuracy against human judgment
3. **Fine-tuning**: Collecting labeled data for model improvement

## Quick Start

```bash
# Launch with reviewer name prompt
uv run python audit_validation_gui.py

# Launch with specified reviewer name
uv run python audit_validation_gui.py --user alice

# Show only unvalidated items (incremental mode)
uv run python audit_validation_gui.py --user alice --incremental

# Enable debug logging
uv run python audit_validation_gui.py --debug
```

## Interface Overview

### Main Layout

The GUI is organized into two main areas:

1. **Review Items Tab**: For validating individual audit trail items
2. **Statistics Tab**: For viewing validation progress and benchmarking data

### Review Items Tab

#### Research Question Selector

At the top, select the research question you want to review. The dropdown shows:
- Question text (truncated)
- Validation progress: `[validated/total]` items

#### Item Type Tabs

Five tabs organize items by workflow step:

| Tab | Description | What to Validate |
|-----|-------------|------------------|
| **Queries** | Generated database queries | SQL syntax, search term relevance |
| **Scores** | Document relevance scores (0-5) | Whether the score matches document relevance |
| **Citations** | Extracted passages and summaries | Accuracy of passage selection and interpretation |
| **Reports** | Generated research reports | Evidence synthesis quality |
| **Counterfactuals** | Questions for finding contradictory evidence | Question relevance and framing |

#### Item List

The left panel shows items with validation status icons:
- `[ ]` - Not yet validated
- `[+]` - Validated (agrees with AI)
- `[X]` - Marked incorrect
- `[?]` - Uncertain
- `[!]` - Needs additional review

#### Detail View

The right panel shows full details for the selected item:
- Metadata (evaluator, timestamp, etc.)
- AI-generated content
- Source document information (for scores/citations)

### Validation Controls

#### Status Options

| Status | Use When |
|--------|----------|
| **Validated** | You agree with the automated evaluation |
| **Incorrect** | You disagree - the AI made an error |
| **Uncertain** | You cannot determine correctness |
| **Needs Review** | Flag for additional expert review |

#### Severity Levels (for Incorrect items)

| Severity | Description |
|----------|-------------|
| **Minor** | Small error with minimal impact |
| **Moderate** | Notable error affecting quality |
| **Major** | Significant error that affects conclusions |
| **Critical** | Fundamental error requiring immediate attention |

#### Error Categories

When marking an item as incorrect, select the applicable error category:

**Query Errors:**
- Syntax Error
- Missing Search Terms
- Wrong Database Fields
- Too Broad / Too Narrow
- Logic Error (AND/OR)

**Score Errors:**
- Overscored / Underscored
- Wrong Reasoning
- Missed Relevance
- False Relevance

**Citation Errors:**
- Wrong Passage
- Misinterpretation
- Out of Context
- Incomplete
- Fabricated

**Report Errors:**
- Unsupported Claim
- Misrepresentation
- Missing Evidence
- Logical Error
- Poor Synthesis

**Counterfactual Errors:**
- Irrelevant Question
- Biased Framing
- Too Vague
- Missed Angle

#### Comment and Suggested Correction

- **Comment**: Explain your validation decision (required for incorrect items)
- **Suggested Correction**: What the correct value should be (optional but helpful)

### Statistics Tab

The Statistics tab shows:

1. **Summary Cards**: Overall validation metrics
2. **By Target Type**: Validation rates for each item type
3. **Error Categories**: Breakdown of common error types

## Workflow Recommendations

### Systematic Review Validation

1. **Start with Scores**: Review document relevance scores first
2. **Then Citations**: Validate extracted passages for high-scoring documents
3. **Check Reports**: Review the final synthesized reports
4. **Review Counterfactuals**: Validate questions for finding contradictory evidence
5. **Query Review**: Check database queries if many documents were missed

### Best Practices

1. **Be Consistent**: Apply the same standards across all items
2. **Document Reasoning**: Always explain why you marked something incorrect
3. **Use Categories**: Select appropriate error categories for benchmarking
4. **Take Breaks**: Review quality degrades with fatigue
5. **Track Time**: The timer helps identify complex items

### Inter-Rater Reliability

For research purposes:
- Multiple reviewers can validate the same items
- Each reviewer's validations are tracked separately
- Statistics show agreement rates across reviewers

## Database Tables

The validation system uses these tables in the `audit` schema:

| Table | Purpose |
|-------|---------|
| `human_validations` | Core validation records |
| `validation_categories` | Predefined error categories |
| `validation_category_assignments` | Links validations to categories |

### Views for Analysis

| View | Purpose |
|------|---------|
| `v_validation_statistics` | Aggregated validation rates |
| `v_validation_error_categories` | Error category breakdown |
| `v_evaluator_validation_performance` | Per-evaluator accuracy |

## Troubleshooting

### Connection Errors

If you see "Failed to initialize the audit validation plugin":
1. Check that PostgreSQL is running
2. Verify database credentials in `~/.bmlibrarian/config.json`
3. Ensure the audit schema is up to date (run migrations)

### Missing Items

If no items appear after selecting a research question:
1. Check that the research question has audit data
2. If using incremental mode, items may already be validated
3. Try unchecking "Show validated items"

### Slow Performance

For large audit trails:
1. Use incremental mode to reduce data loading
2. Focus on one item type at a time
3. Close other applications to free memory

## See Also

- [Audit System Design](../developers/AUDIT_SYSTEM_DESIGN.md) - Technical architecture
- [Fact-Checker Review Guide](fact_checker_review_guide.md) - Similar validation interface
- [Multi-Model Query Guide](multi_model_query_guide.md) - Query generation details
