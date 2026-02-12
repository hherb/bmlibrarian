# ClinicalTrials.gov Bulk Import Guide

## Overview

BMLibrarian can import trial metadata from ClinicalTrials.gov's bulk data download. This enables offline detection of industry-sponsored trials by matching clinical trial records to documents in your database.

## What It Provides

After import, the system has access to:
- **NCT IDs** matched to documents that mention them in their text
- **Trial sponsor names** (e.g., "Pfizer", "National Heart, Lung, and Blood Institute")
- **Sponsor classification** (NIH, Industry, FedGov, Other)
- **Trial status** (Completed, Recruiting, Terminated, etc.)

This data is stored in `transparency.document_metadata` and used by the TransparencyAgent to enrich assessments with verified sponsor information.

## Prerequisites

1. The transparency database schema must be created:
   ```bash
   # Run migration 029
   uv run python initial_setup_and_download.py your.env
   ```

2. Sufficient disk space: the ClinicalTrials.gov bulk download is approximately **10 GB** compressed.

## Usage

### Download Trial Data

```bash
uv run python clinicaltrials_import_cli.py download --output-dir ~/clinicaltrials
```

This downloads `AllPublicXML.zip` from ClinicalTrials.gov. The download is **resumable** — if interrupted, re-running the command continues from where it left off.

Options:
- `--output-dir PATH` — Directory to store the downloaded ZIP file (default: `~/clinicaltrials`)

### Import to Database

```bash
uv run python clinicaltrials_import_cli.py import --input-dir ~/clinicaltrials
```

This streams through the ZIP file without full extraction, parsing each XML entry and matching trials to documents in your database by searching for NCT IDs in document text.

Options:
- `--input-dir PATH` — Directory containing the downloaded ZIP file
- `--limit N` — Maximum number of trials to process (useful for testing)

### Check Status

```bash
uv run python clinicaltrials_import_cli.py status
```

Shows import statistics: total trials processed, documents matched, sponsor class distribution.

## How Matching Works

The importer matches trials to documents by:
1. Extracting the NCT ID from each trial XML record
2. Searching `public.document.full_text` and `public.document.abstract` for that NCT ID
3. When a match is found, storing the trial metadata in `transparency.document_metadata`

This means documents must have the NCT ID mentioned in their text to be matched. Most clinical trial publications include their registry ID in the methods section.

## Data Storage

Imported data is stored in `transparency.document_metadata`:

| Column | Source | Example |
|--------|--------|---------|
| `clinical_trial_id` | NCT ID | NCT01234567 |
| `trial_sponsor` | Lead sponsor name | Pfizer |
| `trial_sponsor_class` | Sponsor classification | Industry |
| `source` | Provenance | clinicaltrials_bulk |

## Integration with Transparency Assessment

When running a transparency assessment, the TransparencyAgent automatically checks `transparency.document_metadata` for trial sponsor data. If a document is linked to an industry-sponsored trial, this is reflected in:
- `is_industry_funded` flag
- `trial_sponsor_class` field
- Risk indicators (if industry funded without proper disclosure)

## Updating

ClinicalTrials.gov updates their bulk download regularly. To update:

1. Re-download: `uv run python clinicaltrials_import_cli.py download --output-dir ~/clinicaltrials`
2. Re-import: `uv run python clinicaltrials_import_cli.py import --input-dir ~/clinicaltrials`

The import uses UPSERT logic, so re-importing updates existing records without creating duplicates.

## See Also

- [Transparency Assessment Guide](transparency_assessment_guide.md) — Main transparency assessment documentation
- [Retraction Watch Import Guide](retraction_watch_guide.md) — Importing retraction data
