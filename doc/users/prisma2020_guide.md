# PRISMA 2020 Assessment Guide - User Documentation

## Introduction

The PRISMA 2020 agent helps you assess the reporting quality of systematic reviews and meta-analyses against the PRISMA 2020 (Preferred Reporting Items for Systematic reviews and Meta-Analyses) guidelines.

### What is PRISMA 2020?

PRISMA 2020 is an evidence-based minimum set of items for reporting in systematic reviews and meta-analyses. It consists of a 27-item checklist designed to help authors improve the transparency and completeness of their systematic review reporting.

### Why Use PRISMA Assessment?

- **Quality Control**: Identify reporting gaps in your systematic reviews
- **Peer Review**: Evaluate systematic reviews submitted for publication
- **Editorial Decision**: Assess whether submissions meet reporting standards
- **Research Transparency**: Improve reproducibility and transparency of evidence synthesis
- **Training**: Learn PRISMA 2020 standards by seeing assessments of example reviews

## Quick Start

### Using the PRISMA 2020 Lab (GUI)

The easiest way to assess systematic reviews is through the interactive laboratory interface:

```bash
uv run python prisma2020_lab.py
```

**Step-by-step:**

1. **Launch the lab**: Run the command above
2. **Enter document ID**: Type a document ID from your BMLibrarian database
3. **Load & Assess**: Click the button to start the assessment
4. **Review suitability**: The system first checks if it's a systematic review
5. **View compliance**: If suitable, see the full 27-item PRISMA assessment

### Using Python Code

```python
from bmlibrarian.agents import PRISMA2020Agent, AgentOrchestrator
from bmlibrarian.database import fetch_documents_by_ids

# Initialize the agent
orchestrator = AgentOrchestrator(max_workers=2)
agent = PRISMA2020Agent(
    model="gpt-oss:20b",
    orchestrator=orchestrator
)

# Load a systematic review from the database
documents = fetch_documents_by_ids([12345])  # Replace with your document ID
document = documents[0]

# Assess PRISMA compliance
assessment = agent.assess_prisma_compliance(document)

if assessment:
    # Print compliance summary
    print(f"\nOverall Compliance: {assessment.overall_compliance_percentage:.1f}%")
    print(f"Category: {assessment.get_compliance_category()}")
    print(f"\nFully Reported: {assessment.fully_reported_items}/27 items")
    print(f"Partially Reported: {assessment.partially_reported_items}/27 items")
    print(f"Not Reported: {assessment.not_reported_items}/27 items")

    # Print formatted summary
    print(agent.format_assessment_summary(assessment))
else:
    print("Assessment failed or document not suitable")
```

## Understanding the Assessment

### Two-Step Process

The PRISMA 2020 agent uses a two-step assessment process:

#### Step 1: Suitability Check

Before performing a full PRISMA assessment, the agent determines if the document is appropriate:

- **Is it a systematic review?** Uses explicit methodology, systematic search, quality assessment
- **Is it a meta-analysis?** Includes statistical synthesis of multiple studies
- **Document type identification**: e.g., "systematic review with meta-analysis", "primary RCT", "narrative review"

**Example Output:**
```
✓ Document is suitable for PRISMA assessment
Document Type: Systematic review with meta-analysis
Confidence: 92%
Rationale: This document is a systematic review as evidenced by the explicit
search strategy across multiple databases, systematic study selection process,
and formal quality assessment using the Cochrane Risk of Bias tool.
```

#### Step 2: PRISMA Compliance Assessment (27 Items)

If suitable, the agent evaluates all 27 PRISMA checklist items across 7 sections:

1. **Title** (1 item)
2. **Abstract** (1 item)
3. **Introduction** (2 items): Rationale, Objectives
4. **Methods** (11 items): Eligibility, Search, Selection, Data collection, Bias assessment, Synthesis, etc.
5. **Results** (7 items): Study selection, Characteristics, Synthesis results, Certainty of evidence
6. **Discussion** (3 items): Interpretation, Limitations, Conclusions
7. **Other Information** (2 items): Registration, Funding

### Scoring System

Each item receives a score from 0 to 2:

| Score | Meaning | Description |
|-------|---------|-------------|
| **2.0** | Fully Reported | All required information present, meets PRISMA standards completely |
| **1.0** | Partially Reported | Some required information present, but missing key details |
| **0.0** | Not Reported | Required information absent or not addressed |

### Compliance Categories

Overall compliance percentage determines the quality category:

| Percentage | Category | Interpretation |
|------------|----------|----------------|
| **90-100%** | Excellent | Outstanding adherence to PRISMA 2020 |
| **75-89%** | Good | Strong reporting with minor gaps |
| **60-74%** | Adequate | Acceptable reporting with some improvement needed |
| **40-59%** | Poor | Significant reporting deficiencies |
| **0-39%** | Very Poor | Major reporting failures |

## GUI Laboratory Features

The PRISMA 2020 Lab provides a visual interface with these sections:

### 1. Input Panel (Top)

- **Model Selection**: Choose which Ollama model to use for assessment
- **Refresh Button**: Update available models list
- **Document ID**: Enter the database ID of the systematic review
- **Load & Assess**: Start the assessment process
- **Clear**: Reset the interface

### 2. Document Panel (Left Side)

- **Title & Metadata**: Document title, PMID, DOI
- **Suitability Card**: Color-coded suitability assessment
  - Green border: Suitable systematic review
  - Red border: Not suitable (primary research, narrative review, etc.)
- **Abstract**: Full abstract text for reference

### 3. Assessment Results Panel (Right Side)

- **Overall Compliance Summary**:
  - Compliance percentage and category
  - Confidence in assessment
  - Visual indicators for fully/partially/not reported items

- **Item-by-Item Breakdown**:
  - Organized by PRISMA section
  - Color-coded cards:
    - Green (✓✓): Fully reported (2.0)
    - Orange (✓): Partially reported (1.0)
    - Red (✗): Not reported (0.0)
  - Explanations for each score

## Common Use Cases

### Use Case 1: Self-Assessment Before Submission

**Scenario**: You've written a systematic review and want to check PRISMA compliance before submitting to a journal.

**Steps:**
1. Import your systematic review into BMLibrarian database (if not already present)
2. Run PRISMA assessment using the lab or Python code
3. Review items scoring 0.0 or 1.0
4. Add missing information to your manuscript
5. Reassess to verify improvements

**Example:**
```python
# Initial assessment
assessment1 = agent.assess_prisma_compliance(my_review)
print(f"Initial compliance: {assessment1.overall_compliance_percentage:.1f}%")

# Identify gaps
for i, (item, score, explanation) in enumerate([
    ("Title", assessment1.title_score, assessment1.title_explanation),
    ("Abstract", assessment1.abstract_score, assessment1.abstract_explanation),
    # ... all 27 items
]):
    if score < 2.0:
        print(f"{item}: {score}/2.0 - {explanation}")

# After revisions, reassess
assessment2 = agent.assess_prisma_compliance(my_improved_review)
print(f"Improved compliance: {assessment2.overall_compliance_percentage:.1f}%")
```

### Use Case 2: Peer Review

**Scenario**: You're reviewing a systematic review manuscript and need to assess reporting quality.

**Steps:**
1. Load the submitted manuscript into BMLibrarian
2. Run PRISMA assessment
3. Generate formatted report
4. Include assessment in your peer review comments

**Example:**
```python
# Assess submitted manuscript
assessment = agent.assess_prisma_compliance(submitted_manuscript)

# Generate detailed report
report = agent.format_assessment_summary(assessment)

# Save to file for peer review
with open("prisma_assessment.txt", "w") as f:
    f.write(report)

# Identify critical gaps for authors
critical_gaps = []
items = [
    ("Search strategy", assessment.search_strategy_score, assessment.search_strategy_explanation),
    ("Risk of bias", assessment.risk_of_bias_score, assessment.risk_of_bias_explanation),
    ("PRISMA flow diagram", assessment.study_selection_score, assessment.study_selection_explanation),
    # ... check other critical items
]

for item, score, explanation in items:
    if score < 1.0:
        critical_gaps.append(f"- {item}: {explanation}")

print("\nCritical reporting gaps to address:")
for gap in critical_gaps:
    print(gap)
```

### Use Case 3: Batch Assessment of Multiple Reviews

**Scenario**: You want to assess PRISMA compliance across multiple systematic reviews (e.g., from a journal, research group, or database).

**Steps:**
1. Collect document IDs for all systematic reviews
2. Run batch assessment
3. Export results to CSV for analysis
4. Analyze compliance trends

**Example:**
```python
# List of systematic review IDs
review_ids = [12345, 23456, 34567, 45678, 56789]

# Fetch documents
documents = fetch_documents_by_ids(review_ids)

# Batch assessment
assessments = agent.assess_batch(
    documents,
    min_confidence=0.5,
    progress_callback=lambda curr, total, title:
        print(f"[{curr}/{total}] Assessing: {title[:60]}...")
)

# Export to CSV for analysis
agent.export_to_csv(assessments, "systematic_reviews_prisma.csv")

# Calculate summary statistics
avg_compliance = sum(a.overall_compliance_percentage for a in assessments) / len(assessments)
excellent_count = sum(1 for a in assessments if a.overall_compliance_percentage >= 90)
poor_count = sum(1 for a in assessments if a.overall_compliance_percentage < 60)

print(f"\nSummary of {len(assessments)} systematic reviews:")
print(f"Average compliance: {avg_compliance:.1f}%")
print(f"Excellent (≥90%): {excellent_count} ({excellent_count/len(assessments)*100:.1f}%)")
print(f"Poor (<60%): {poor_count} ({poor_count/len(assessments)*100:.1f}%)")
```

### Use Case 4: Journal Editorial Assessment

**Scenario**: As an editor, you want to screen systematic review submissions for PRISMA compliance.

**Steps:**
1. Set minimum compliance threshold (e.g., 75%)
2. Assess submitted reviews
3. Use results to make editorial decisions
4. Provide specific feedback to authors

**Example:**
```python
# Editorial policy: minimum 75% compliance
MINIMUM_COMPLIANCE = 75.0

# Assess submission
assessment = agent.assess_prisma_compliance(submission)

if assessment.overall_compliance_percentage >= MINIMUM_COMPLIANCE:
    print(f"✓ Submission meets PRISMA standards ({assessment.overall_compliance_percentage:.1f}%)")
    print("Recommendation: Proceed to peer review")
else:
    print(f"✗ Submission below PRISMA threshold ({assessment.overall_compliance_percentage:.1f}% < {MINIMUM_COMPLIANCE}%)")
    print("Recommendation: Request revisions before peer review")

    # Generate feedback for authors
    print("\nRequired improvements:")
    all_items = [...]  # All 27 items
    for item_name, score, explanation in all_items:
        if score < 1.5:  # Focus on poorly reported items
            print(f"- {item_name}: {explanation}")
```

## Interpreting Results

### Reading the Suitability Assessment

The suitability check answers three questions:

1. **Is this a systematic review?**
   - Look for: systematic search, explicit methodology, quality assessment

2. **Does it include meta-analysis?**
   - Look for: statistical synthesis, forest plots, pooled estimates

3. **What is the document type?**
   - Systematic review (with or without meta-analysis)
   - Primary research (RCT, cohort, case-control, etc.)
   - Narrative review
   - Scoping review
   - Other

**If not suitable**: The agent explains why and does not proceed with PRISMA assessment.

### Understanding Item Scores

Each PRISMA item includes:

- **Score** (0.0, 1.0, or 2.0)
- **Explanation**: What was found (or missing) in the text

**Examples:**

✓✓ **Item 7: Search strategy (2.0/2.0)**
> "Full search strategy provided for PubMed including all search terms, Boolean operators, and filters used."

✓ **Item 14: Reporting bias assessment (1.0/2.0)**
> "Funnel plots mentioned but formal statistical tests (e.g., Egger's test) not specified."

✗ **Item 26: Registration (0.0/2.0)**
> "No mention of protocol registration (e.g., PROSPERO) or protocol availability."

### Common Patterns

**High-scoring systematic reviews typically:**
- State "systematic review" in title
- Provide structured abstract
- Report PROSPERO registration
- Include PRISMA flow diagram
- Detail full search strategy
- Use established bias assessment tools (e.g., Cochrane RoB)
- Apply GRADE for certainty of evidence

**Common deficiencies:**
- Missing protocol registration
- Incomplete search strategy (not all databases shown)
- No PRISMA flow diagram
- Inadequate bias assessment reporting
- Missing certainty of evidence assessment

## Export and Reporting

### JSON Export

Full assessment data with all scores and explanations:

```python
# Export single assessment
agent.export_to_json([assessment], "review_assessment.json")

# Export batch assessments
agent.export_to_json(assessments, "batch_assessments.json")
```

**JSON Structure:**
```json
{
  "assessments": [
    {
      "document_id": "12345",
      "document_title": "Systematic review of...",
      "overall_compliance_percentage": 84.3,
      "fully_reported_items": 18,
      "partially_reported_items": 7,
      "not_reported_items": 2,
      "title_score": 2.0,
      "title_explanation": "...",
      // ... all 27 items
    }
  ],
  "metadata": {
    "total_assessments": 1,
    "assessment_date": "2025-01-19T10:30:00Z",
    "agent_model": "gpt-oss:20b"
  }
}
```

### CSV Export

Tabular data suitable for Excel, R, or statistical analysis:

```python
# Export to CSV
agent.export_to_csv(assessments, "prisma_scores.csv")
```

**CSV Columns:**
- `document_id`, `document_title`, `pmid`, `doi`
- `overall_compliance_score`, `overall_compliance_percentage`
- `fully_reported_items`, `partially_reported_items`, `not_reported_items`
- All 27 individual item scores
- Timestamps

### Formatted Text Report

Human-readable summary for reports or documentation:

```python
# Generate formatted report
report = agent.format_assessment_summary(assessment)

# Print to console
print(report)

# Save to file
with open("prisma_report.txt", "w") as f:
    f.write(report)
```

**Report Format:**
```
================================================================================
PRISMA 2020 COMPLIANCE ASSESSMENT: [Title]
================================================================================
Document ID: 12345
PMID: 98765432
DOI: 10.1234/example

--- DOCUMENT TYPE ---
Systematic Review: True
Meta-Analysis: True
...

--- OVERALL COMPLIANCE ---
Compliance Score: 1.68/2.0 (84.3%)
Compliance Category: Good (75-89%)
...

--- ITEM-BY-ITEM ASSESSMENT ---
TITLE:
  [✓✓] Item 1: Title (2.0/2.0)
      Title clearly identifies this as a systematic review and meta-analysis

ABSTRACT:
  [✓] Item 2: Abstract (1.0/2.0)
      Structured abstract present but missing protocol registration information
...
```

## Configuration

### Model Selection

Configure which Ollama model to use in `~/.bmlibrarian/config.json`:

```json
{
  "models": {
    "prisma2020_agent": "gpt-oss:20b"
  },
  "agents": {
    "prisma2020": {
      "temperature": 0.1,
      "top_p": 0.9,
      "max_tokens": 4000
    }
  }
}
```

**Recommended models:**
- `gpt-oss:20b`: High-quality assessments, comprehensive
- `medgemma-27b-text-it-Q8_0:latest`: Medical domain expertise

### Parameters

- **temperature** (0.1): Low temperature for consistent, objective assessment
- **top_p** (0.9): Sampling parameter
- **max_tokens** (4000): Sufficient for detailed 27-item assessment

## Troubleshooting

### Issue: "Document not suitable for PRISMA assessment"

**Cause**: The document is not a systematic review or meta-analysis.

**Solution**:
- Verify the document is actually a systematic review
- Check the suitability rationale for details
- If incorrectly classified, try with `skip_suitability_check=True` (use with caution)

### Issue: Low confidence scores

**Cause**: Document text is ambiguous or incomplete (e.g., abstract only, no full text).

**Solution**:
- Import full text if available
- Accept that abstract-only assessments will have lower confidence
- Many items cannot be assessed from abstract alone

### Issue: Assessment takes too long

**Cause**: Large documents with extensive full text.

**Solution**:
- Normal assessment time: 30-60 seconds
- Text is auto-truncated to 15,000 characters
- Ensure Ollama service is running locally (not remote)

### Issue: All items score 0.0 or 1.0

**Cause**:
- Analyzing wrong document type (not a systematic review)
- Only abstract available (no full text)
- Poor quality systematic review

**Solution**:
- Verify document type with suitability check
- Import full text for comprehensive assessment
- Accept that some reviews may genuinely have poor PRISMA compliance

## Best Practices

1. **Always review suitability first**: Don't force PRISMA assessment on non-systematic reviews

2. **Use full text when available**: Abstract-only assessments are incomplete

3. **Interpret in context**: Consider publication date (older reviews may not follow PRISMA 2020)

4. **Focus on critical items**:
   - Item 7 (search strategy)
   - Item 11 (bias assessment)
   - Item 16 (PRISMA flow diagram)
   - Item 22 (certainty of evidence)

5. **Provide constructive feedback**: Use explanations to guide improvements

6. **Batch process for trends**: Assess multiple reviews to identify patterns

7. **Export for records**: Save assessments as JSON/CSV for documentation

## Resources

- **PRISMA 2020 Statement**: https://www.prisma-statement.org/
- **PRISMA 2020 Checklist**: Official checklist and explanation
- **BMJ Article**: Page MJ, et al. The PRISMA 2020 statement. BMJ 2021;372:n71

## Examples

See the PRISMA 2020 Lab for interactive examples:

```bash
uv run python prisma2020_lab.py
```

For code examples, see `doc/developers/prisma2020_system.md`
