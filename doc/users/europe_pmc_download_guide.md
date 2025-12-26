# Europe PMC Bulk Download Guide

This guide explains how to download full-text XML articles from Europe PMC's Open Access collection for offline access.

## Overview

Europe PMC provides free access to over 5.7 million open access biomedical articles in JATS XML format. The bulk downloader allows you to:

- Download the complete Open Access collection
- Resume interrupted downloads
- Verify download integrity (gzip validation)
- Filter by PMCID range for targeted downloads

## Quick Start

```bash
# List available packages
uv run python europe_pmc_bulk_cli.py list

# Download all packages (with 1-minute delay between files)
uv run python europe_pmc_bulk_cli.py download --output-dir ~/europepmc

# Check download status
uv run python europe_pmc_bulk_cli.py status --output-dir ~/europepmc
```

## CLI Commands

### List Available Packages

Shows all available XML packages from Europe PMC:

```bash
uv run python europe_pmc_bulk_cli.py list --output-dir ~/europepmc
```

Options:
- `--output-dir`: Directory for state files (default: `~/europepmc`)
- `--range`: Filter by PMCID range (e.g., `1-1000000`)
- `--refresh`: Force refresh package list from server

### Download Packages

Downloads packages with resumable progress and verification:

```bash
# Download all packages
uv run python europe_pmc_bulk_cli.py download --output-dir ~/europepmc

# Download with custom delay (2 minutes between files)
uv run python europe_pmc_bulk_cli.py download --output-dir ~/europepmc --delay 120

# Download only 10 packages (for testing)
uv run python europe_pmc_bulk_cli.py download --output-dir ~/europepmc --limit 10

# Download specific PMCID range
uv run python europe_pmc_bulk_cli.py download --output-dir ~/europepmc --range 1-1000000
```

Options:
- `--output-dir`: Directory for downloads (default: `~/europepmc`)
- `--limit`: Maximum packages to download
- `--delay`: Seconds between downloads (default: 60)
- `--range`: PMCID range filter (e.g., `1-1000000`)
- `--max-retries`: Retry attempts per file (default: 3)

### Check Status

Shows current download progress:

```bash
uv run python europe_pmc_bulk_cli.py status --output-dir ~/europepmc
```

### Verify Downloads

Verifies gzip integrity of all downloaded files:

```bash
uv run python europe_pmc_bulk_cli.py verify --output-dir ~/europepmc
```

### Estimate Time

Estimates remaining download time based on current progress:

```bash
uv run python europe_pmc_bulk_cli.py estimate --output-dir ~/europepmc
```

## Directory Structure

After downloading, your output directory will contain:

```
~/europepmc/
├── packages/                    # Downloaded .xml.gz files
│   ├── PMC13900_PMC17829.xml.gz
│   ├── PMC17830_PMC27829.xml.gz
│   └── ...
└── download_state.json          # Resumable state
```

## File Format

Each package file is a gzip-compressed XML file containing approximately 10,000 articles in JATS (Journal Article Tag Suite) format.

Example structure inside a package:
```xml
<article-set>
  <article>
    <front>
      <article-meta>
        <article-id pub-id-type="pmcid">PMC123456</article-id>
        <article-id pub-id-type="pmid">12345678</article-id>
        <article-id pub-id-type="doi">10.1234/example</article-id>
        <title-group>
          <article-title>Example Article Title</article-title>
        </title-group>
        <!-- ... -->
      </article-meta>
    </front>
    <body>
      <!-- Full-text content -->
    </body>
  </article>
  <!-- More articles... -->
</article-set>
```

## Resuming Downloads

Downloads are automatically resumable. If interrupted (e.g., by Ctrl+C or network issues):

1. Progress is saved to `download_state.json`
2. Simply run the download command again
3. Already-downloaded and verified files will be skipped

## Download Verification

Every downloaded file is automatically verified:

1. **Gzip integrity check**: The entire file is read through gzip to verify no corruption
2. **Automatic retry**: If verification fails, the file is deleted and re-downloaded
3. **Manual verification**: Use `verify` command to re-check all files

## Rate Limiting

The downloader includes built-in rate limiting to be polite to Europe PMC servers:

- Default: 60 seconds between file downloads
- Configurable via `--delay` option
- Linear backoff on retries (5 × attempt seconds)

## Storage Requirements

Estimated storage requirements:

- **Compressed**: 50-100+ GB (gzip files as downloaded)
- **Uncompressed**: 200-500+ GB (if you extract the XML)

## Programmatic Usage

```python
from pathlib import Path
from bmlibrarian.importers import EuropePMCBulkDownloader

# Create downloader
downloader = EuropePMCBulkDownloader(
    output_dir=Path('~/europepmc'),
    delay_between_files=60,  # 1 minute
    max_retries=3
)

# List available packages
packages = downloader.list_available_packages()
print(f"Found {len(packages)} packages")

# Download with progress callback
def on_progress(filename, current, total):
    print(f"[{current}/{total}] Downloading {filename}")

downloaded = downloader.download_packages(
    limit=10,  # Download first 10 only
    progress_callback=on_progress
)

# Check status
status = downloader.get_status()
print(f"Downloaded: {status['packages']['downloaded']}")
print(f"Verified: {status['packages']['verified']}")

# Verify all downloads
results = downloader.verify_all_downloads()
print(f"Verified: {results['verified']}, Failed: {results['failed']}")
```

## Filtering by PMCID Range

To download only specific PMCID ranges:

```bash
# Download PMCIDs 1 to 1,000,000 only
uv run python europe_pmc_bulk_cli.py download --range 1-1000000

# Download PMCIDs 5,000,000 to 6,000,000
uv run python europe_pmc_bulk_cli.py download --range 5000000-6000000
```

Programmatically:

```python
downloader = EuropePMCBulkDownloader(
    output_dir=Path('~/europepmc'),
    pmcid_ranges=[(1, 1000000)]  # List of (start, end) tuples
)
```

## Troubleshooting

### Download Keeps Failing

1. Check your internet connection
2. Increase timeout: Edit the downloader with longer timeout
3. Reduce delay to ensure you're not timing out between downloads
4. Check Europe PMC service status

### Verification Fails

1. File may be corrupted during download
2. The downloader will automatically delete and retry
3. If persistent, check disk space and filesystem integrity

### Slow Downloads

1. This is expected - files are large (100+ MB each)
2. Use `estimate` command to check projected time
3. Consider running overnight for large downloads

## Related Documentation

- [Europe PMC Downloads](https://europepmc.org/downloads)
- [Europe PMC Open Access](https://europepmc.org/downloads/openaccess)
- [JATS XML Format](https://jats.nlm.nih.gov/)
