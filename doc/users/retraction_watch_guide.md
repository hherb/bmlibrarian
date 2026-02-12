# Retraction Watch Import Guide

## Overview

BMLibrarian can import retraction data from the Retraction Watch database, a comprehensive record of retracted scientific publications. This enables offline detection of retracted papers in your document collection.

## What It Provides

After import, the system flags documents that have been retracted and records:
- **Retraction status** (is_retracted flag)
- **Retraction reason** (misconduct, data fabrication, plagiarism, etc.)
- **Retraction date**
- **Matching by DOI and PMID**

This data is stored in `transparency.document_metadata` and used by the TransparencyAgent to add retraction warnings to assessments.

## Obtaining the Data

The Retraction Watch database is available as a CSV file (~50 MB). It can be obtained:

1. **Via CrossRef**: Available as part of CrossRef's metadata services
2. **Direct request**: Request access at [retractionwatch.com](http://retractionwatch.com) for research use

The CSV typically contains columns like:
- DOI of retracted paper
- PMID (if available)
- Retraction date
- Retraction reason(s)
- Original paper DOI (for retraction notices)

## Prerequisites

1. The transparency database schema must be created:
   ```bash
   # Run migration 029
   uv run python initial_setup_and_download.py your.env
   ```

2. A Retraction Watch CSV file (see "Obtaining the Data" above).

## Usage

### Import CSV

```bash
uv run python retraction_watch_cli.py import --file retraction_watch.csv
```

The importer:
- Automatically detects column names (handles variations in CSV headers)
- Matches entries to documents by DOI first, then PMID
- Handles multiple CSV encodings (UTF-8, Latin-1, CP1252)

Options:
- `--file PATH` — Path to the Retraction Watch CSV file
- `--limit N` — Maximum number of entries to process

### Look Up a Specific Paper

```bash
uv run python retraction_watch_cli.py lookup --doi 10.1234/example
uv run python retraction_watch_cli.py lookup --pmid 12345678
```

Checks if a specific paper appears in the imported retraction data.

### Check Status

```bash
uv run python retraction_watch_cli.py status
```

Shows import statistics: total retraction records, documents matched, retraction reasons distribution.

## How Matching Works

The importer matches retraction records to documents by:

1. **DOI matching** (primary): Looks up the retracted paper's DOI in `public.document.doi`
2. **PMID matching** (fallback): If no DOI match, looks up PMID in `public.document.external_id`

When a match is found:
- `transparency.document_metadata.is_retracted` is set to `TRUE`
- `transparency.document_metadata.retraction_reason` is populated
- `transparency.document_metadata.retraction_date` is set
- `transparency.document_metadata.retraction_source` is set to `"retraction_watch"`

## Data Storage

Imported data is stored in `transparency.document_metadata`:

| Column | Source | Example |
|--------|--------|---------|
| `is_retracted` | Match found | TRUE |
| `retraction_reason` | CSV data | "Data Fabrication/Falsification" |
| `retraction_date` | CSV data | 2023-05-15 |
| `retraction_source` | Fixed | retraction_watch |

## Integration with Transparency Assessment

When running a transparency assessment, the TransparencyAgent automatically checks for retraction status. If a document is retracted:

- `is_retracted` is set to `True` on the assessment
- `retraction_reason` is included
- A risk indicator "Paper has been retracted" is added
- This significantly impacts the overall risk assessment

## Column Name Flexibility

The importer handles common variations in CSV column headers:

| Data | Recognized Column Names |
|------|------------------------|
| DOI | `doi`, `DOI`, `RetractionDOI`, `OriginalPaperDOI` |
| PMID | `pmid`, `PMID`, `PubMedID`, `OriginalPaperPubMedID` |
| Reason | `reason`, `Reason`, `RetractionNature`, `RetractionReasons` |
| Date | `retraction_date`, `RetractionDate` |

If the CSV uses different column names, the importer will attempt to match them. If it cannot find required columns, it will report an error with the available column names.

## Updating

To update with a newer Retraction Watch dataset:

```bash
uv run python retraction_watch_cli.py import --file retraction_watch_2026.csv
```

The import uses UPSERT logic, so re-importing updates existing records without creating duplicates. New retraction entries will be added automatically.

## See Also

- [Transparency Assessment Guide](transparency_assessment_guide.md) — Main transparency assessment documentation
- [ClinicalTrials.gov Import Guide](clinicaltrials_import_guide.md) — Importing trial data
