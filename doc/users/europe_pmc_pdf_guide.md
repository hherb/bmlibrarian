# Europe PMC PDF Bulk Download Guide

This guide explains how to download PDF files from Europe PMC Open Access for offline access to biomedical literature.

## Overview

The Europe PMC PDF downloader complements the XML downloader by providing access to the PDF versions of Open Access articles. PDFs are organized in tar.gz packages by PMCID ranges and can be downloaded, verified, and extracted for local use.

## Features

- **Resumable downloads** - Progress is saved automatically; interrupted downloads resume from where they left off
- **Download verification** - Tar.gz archive integrity is verified after each download
- **PDF extraction** - Automatically extracts PDFs to organized subdirectories
- **Rate limiting** - Configurable delay between downloads (default: 60 seconds)
- **PMCID filtering** - Download only specific PMCID ranges
- **Progress tracking** - Real-time status updates and time estimation

## Quick Start

```bash
# List available PDF packages
uv run python europe_pmc_pdf_cli.py list

# Download all packages (with default 60s delay)
uv run python europe_pmc_pdf_cli.py download --output-dir ~/europepmc_pdf

# Check status
uv run python europe_pmc_pdf_cli.py status --output-dir ~/europepmc_pdf
```

## CLI Commands

### List Available Packages

```bash
# List all available packages
uv run python europe_pmc_pdf_cli.py list --output-dir ~/europepmc_pdf

# Refresh from server
uv run python europe_pmc_pdf_cli.py list --refresh

# Filter by PMCID range
uv run python europe_pmc_pdf_cli.py list --range 1-1000000
```

### Download Packages

```bash
# Download all packages
uv run python europe_pmc_pdf_cli.py download --output-dir ~/europepmc_pdf

# Limit number of packages
uv run python europe_pmc_pdf_cli.py download --limit 10

# Custom delay between downloads (seconds)
uv run python europe_pmc_pdf_cli.py download --delay 120

# Download specific PMCID range
uv run python europe_pmc_pdf_cli.py download --range 1-1000000

# Download without extracting PDFs
uv run python europe_pmc_pdf_cli.py download --no-extract
```

### Verify Downloads

```bash
# Verify all downloaded packages
uv run python europe_pmc_pdf_cli.py verify --output-dir ~/europepmc_pdf
```

### Extract PDFs

```bash
# Extract PDFs from verified packages
uv run python europe_pmc_pdf_cli.py extract --output-dir ~/europepmc_pdf

# Extract with limit
uv run python europe_pmc_pdf_cli.py extract --limit 10
```

### Check Status

```bash
# Show download status
uv run python europe_pmc_pdf_cli.py status --output-dir ~/europepmc_pdf
```

### Estimate Time

```bash
# Estimate remaining download time
uv run python europe_pmc_pdf_cli.py estimate --output-dir ~/europepmc_pdf
```

### Find a PDF

```bash
# Find a specific PDF by PMCID
uv run python europe_pmc_pdf_cli.py find --pmcid PMC123456

# Also works without PMC prefix
uv run python europe_pmc_pdf_cli.py find --pmcid 123456
```

## Directory Structure

The downloader creates the following directory structure:

```
~/europepmc_pdf/
├── packages/                    # Downloaded tar.gz files
│   ├── PMC13900_PMC17829.tar.gz
│   └── ...
├── pdf/                         # Extracted PDFs
│   └── 13000/                   # Grouped by 1000s
│       └── 13900-13999/         # Then by 100s
│           ├── PMC13900.pdf
│           ├── PMC13901.pdf
│           └── ...
└── pdf_download_state.json      # Progress state file
```

## Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `--output-dir` | `~/europepmc_pdf` | Base directory for downloads |
| `--delay` | 60 | Seconds between downloads |
| `--limit` | None | Maximum packages to download |
| `--range` | None | PMCID range filter (e.g., "1-1000000") |
| `--no-extract` | False | Skip PDF extraction after download |
| `--max-retries` | 3 | Retry attempts per failed download |

## Rate Limiting

To be polite to Europe PMC servers, the default delay between downloads is 60 seconds. For batch downloads of many packages, consider increasing this:

```bash
# 2-minute delay for polite downloading
uv run python europe_pmc_pdf_cli.py download --delay 120
```

## Resuming Downloads

If a download is interrupted (Ctrl+C, network error, etc.), simply run the download command again. The downloader will:

1. Load the saved state from `pdf_download_state.json`
2. Skip already-downloaded and verified packages
3. Resume with the next package

## Programmatic Usage

```python
from pathlib import Path
from bmlibrarian.importers import EuropePMCPDFDownloader

# Initialize downloader
downloader = EuropePMCPDFDownloader(
    output_dir=Path('~/europepmc_pdf').expanduser(),
    delay_between_files=60,  # seconds
    extract_pdfs=True  # automatically extract after download
)

# List available packages
packages = downloader.list_available_packages()
print(f"Found {len(packages)} packages")

# Download with progress callback
def progress(filename, current, total):
    print(f"[{current}/{total}] {filename}")

downloaded = downloader.download_packages(
    limit=10,
    progress_callback=progress
)

# Get status
status = downloader.get_status()
print(f"Downloaded: {status['packages']['downloaded']}")
print(f"PDFs extracted: {status['pdfs']['total']}")

# Find a specific PDF
pdf_path = downloader.get_pdf_path('PMC123456')
if pdf_path:
    print(f"Found: {pdf_path}")
```

## Troubleshooting

### Download Failed

If a download fails:
1. Check your internet connection
2. Run `verify` to check existing downloads
3. Run `download` again - it will retry failed packages

### Archive Verification Failed

If verification fails for a package:
1. The downloader automatically deletes corrupted files
2. Run `download` again to re-download

### PDFs Not Extracting

If PDFs are not being extracted:
1. Check that `--no-extract` is not set
2. Run `extract` manually to process verified packages
3. Check logs for extraction errors

## Storage Requirements

Storage requirements vary based on the packages downloaded:
- Each tar.gz package is typically 50-500 MB
- Extracted PDFs may be 2-5x the compressed size
- Full Open Access collection may require several TB

Use `estimate` command to track download progress and estimate remaining time.

## See Also

- [Europe PMC XML Bulk Download Guide](europe_pmc_bulk_guide.md) - For XML/full-text downloads
- [PDF Import Guide](pdf_import_guide.md) - For importing local PDFs to database
- [Full-Text Discovery Guide](full_text_discovery_guide.md) - For discovering PDFs from multiple sources
