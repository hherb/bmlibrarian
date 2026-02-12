# Transparency Assessment Guide

## Overview

The Transparency Assessment system detects undisclosed bias risk in biomedical research papers by analyzing funding disclosures, conflict of interest statements, data availability, trial registration, and author contributions. It works **entirely offline** using local Ollama LLM models and documents already stored in the PostgreSQL database.

## What It Checks

### 1. Funding Disclosure (0-3 points)
- **Is there a funding section?** Many journals require explicit funding statements.
- **Are specific funders named?** Vague "funded by grants" vs. explicit "NIH R01-HL-12345".
- **Are grant numbers provided?** Complete disclosures include grant identifiers.
- **Is the funding governmental, academic, or commercial/industry?** Industry funding without disclosure is a red flag.

**Scoring:**
| Score | Criteria |
|-------|----------|
| 0 | No funding statement found |
| 1 | Vague or generic statement ("supported by grants") |
| 2 | Named funding sources without grant numbers |
| 3 | Complete disclosure with funders, grant numbers, and roles |

### 2. Conflict of Interest (0-3 points)
- **Is there a COI/competing interests section?** Required by most journals.
- **Are specific conflicts declared, or "none"?** Both are valid; absence is not.
- **Is the disclosure per-author?** Best practice is individual declarations.

**Scoring:**
| Score | Criteria |
|-------|----------|
| 0 | No COI statement found |
| 1 | Generic statement without specifics |
| 2 | Explicit "no conflicts" or specific conflicts listed |
| 3 | Detailed per-author disclosure with specific relationships |

### 3. Data Availability (0-2 points)
- **Is there a data availability statement?** Increasingly required by journals.
- **What level of access?** Open, on request, restricted, or not available.

**Scoring:**
| Score | Criteria |
|-------|----------|
| 0 | No data availability statement |
| 1 | Data available on request or restricted |
| 2 | Open access data in public repositories |

### 4. Trial Registration (0-1 point)
- **Are trial registry IDs mentioned?** NCT, ISRCTN, EudraCT, etc.
- Only scored if the study is a clinical trial or interventional study.

### 5. Author Contributions (0-1 point)
- **Is there a CRediT or author contributions section?** Increasingly expected.

## Risk Classification

The total transparency score (0-10) determines the risk level:

| Risk Level | Score Range | Description |
|------------|-------------|-------------|
| **Low** | > 6.0 | Comprehensive, transparent disclosures |
| **Medium** | 3.0 - 6.0 | Partial disclosures, some gaps |
| **High** | < 3.0 | Missing critical disclosures |
| **Unknown** | N/A | Insufficient text for assessment |

## Industry Funding Detection

The system uses a dual approach to detect potential industry funding:

1. **Pattern Matching**: A curated list of ~60 major pharmaceutical, biotech, medical device, CRO, and diagnostics companies, plus regex patterns for corporate indicators (Inc., Corp., Ltd., pharma, biotech, therapeutics, etc.)
2. **LLM Analysis**: The language model analyzes the full text for industry funding signals that patterns might miss.

## Using the CLI

### Assess a Single Document

```bash
# By document ID
uv run python transparency_analyzer_cli.py assess --doc-id 12345

# By DOI
uv run python transparency_analyzer_cli.py assess --doc-id "10.1038/nature12373"
```

### Assess Documents from a Query

```bash
# Assess documents matching a search
uv run python transparency_analyzer_cli.py assess --query "cardiovascular exercise" --limit 50

# Assess documents with full text available
uv run python transparency_analyzer_cli.py assess --has-fulltext --limit 100
```

### View Statistics

```bash
uv run python transparency_analyzer_cli.py stats
```

Example output:
```
Transparency Assessment Statistics
──────────────────────────────────────────
Total assessed:     1,234
Average score:      5.8 / 10.0

Risk Distribution:
  Low risk:         456 (37.0%)
  Medium risk:      512 (41.5%)
  High risk:        198 (16.0%)
  Unknown:           68  (5.5%)

Disclosure Rates:
  Funding:          892 (72.3%)
  COI:              756 (61.3%)
  Trial registration: 234 (19.0%)

Industry funded:    312 (25.3%)
Retracted:           12  (1.0%)
```

### View Assessment Details

```bash
uv run python transparency_analyzer_cli.py show --doc-id 12345
```

### Export Results

```bash
# Export to JSON
uv run python transparency_analyzer_cli.py export --output results.json

# Export to CSV
uv run python transparency_analyzer_cli.py export --output results.csv
```

## Using the Laboratory GUI

Launch the interactive Transparency Assessment Laboratory:

```bash
uv run python scripts/transparency_lab.py
```

### Features
- **Document Input**: Enter a document ID, DOI, or PMID to load a paper
- **Model Selector**: Choose from available Ollama models
- **Split View**: Document information (left) and assessment results (right)
- **Background Processing**: Assessment runs in a background thread, keeping the UI responsive

### Workflow
1. Enter a document identifier in the input field
2. Click **Load** to fetch the document from the database
3. Review the document information in the left panel
4. Select an appropriate model from the dropdown
5. Click **Assess Transparency** to run the analysis
6. Review the results in the right panel

## Enrichment with Bulk Metadata

When bulk metadata has been imported (from PubMed, ClinicalTrials.gov, or Retraction Watch), the assessment is automatically enriched with:

- **Grant information** from PubMed XML (`<GrantList>`)
- **Retraction status** from Retraction Watch or PubMed
- **Trial sponsor classification** (NIH, Industry, Other) from ClinicalTrials.gov
- **Author affiliations** from PubMed XML

This enrichment happens automatically during assessment if the data is available in the `transparency.document_metadata` table.

## Interpreting Results

### Risk Indicators
The assessment includes specific risk indicators, such as:
- "No funding disclosure found"
- "Industry funded with no COI disclosure"
- "Data not available or not stated"
- "Paper has been retracted"

### Strengths and Weaknesses
Each assessment lists what the paper does well (strengths) and where it falls short (weaknesses), providing actionable feedback.

### Confidence Score
The overall confidence (0-1) indicates how reliable the assessment is. Lower confidence may result from:
- Very short text (abstract only)
- Ambiguous or unclear disclosures
- Non-standard formatting

## Offline Capability

The transparency assessment system is designed for fully offline operation:

| Feature | Offline? | Notes |
|---------|----------|-------|
| Funding disclosure detection | Yes | Analyzes text in database |
| COI statement extraction | Yes | Analyzes text in database |
| Data availability assessment | Yes | Analyzes text in database |
| Industry funder detection | Yes | Built-in company list + LLM |
| Trial registry ID extraction | Yes | Regex pattern matching |
| PubMed grants/affiliations | Yes | From already-downloaded XML |
| ClinicalTrials.gov sponsors | Yes | After one-time ~10GB download |
| Retraction Watch data | Yes | After one-time ~50MB download |

## See Also

- [ClinicalTrials.gov Import Guide](clinicaltrials_import_guide.md) - Downloading and importing trial data
- [Retraction Watch Import Guide](retraction_watch_guide.md) - Importing retraction data
- [Study Assessment Guide](study_assessment_guide.md) - Related study quality assessment
