# Europe PMC Bulk Download and Import Guide

This guide explains how to download and import full-text XML articles from Europe PMC's Open Access collection into BMLibrarian.

## Overview

Europe PMC provides free access to over 5.7 million open access biomedical articles in JATS XML format. The bulk download and import system allows you to:

- Download the complete Open Access collection
- Resume interrupted downloads
- Verify download integrity (gzip validation)
- Filter by PMCID range for targeted downloads
- Import full-text articles into BMLibrarian database
- Convert JATS XML to Markdown with proper formatting
- Handle figure/image references

## Quick Start

```bash
# List available packages
uv run python europe_pmc_bulk_cli.py list

# Download packages (with 1-minute delay between files)
uv run python europe_pmc_bulk_cli.py download --output-dir ~/europepmc

# Check download status
uv run python europe_pmc_bulk_cli.py status --output-dir ~/europepmc

# Import downloaded packages to database
uv run python europe_pmc_bulk_cli.py import --output-dir ~/europepmc

# Check import status
uv run python europe_pmc_bulk_cli.py import-status --output-dir ~/europepmc
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

### Import to Database

Imports downloaded packages into the BMLibrarian database:

```bash
# Import all packages
uv run python europe_pmc_bulk_cli.py import --output-dir ~/europepmc

# Import with limit (for testing)
uv run python europe_pmc_bulk_cli.py import --output-dir ~/europepmc --limit 5

# Import without updating existing records
uv run python europe_pmc_bulk_cli.py import --output-dir ~/europepmc --no-update

# Custom batch size for database commits
uv run python europe_pmc_bulk_cli.py import --output-dir ~/europepmc --batch-size 50
```

Options:
- `--output-dir`: Directory containing downloaded packages (default: `~/europepmc`)
- `--limit`: Maximum packages to import
- `--batch-size`: Articles per database commit (default: 100)
- `--no-update`: Only insert new records, skip updating existing ones

### Import Status

Shows current import progress and statistics:

```bash
uv run python europe_pmc_bulk_cli.py import-status --output-dir ~/europepmc
```

### Verify Import

Verifies a specific package can be parsed correctly before importing:

```bash
uv run python europe_pmc_bulk_cli.py verify-import --output-dir ~/europepmc --package PMC13900_PMC17829.xml.gz
```

This shows:
- Article count in the package
- Sample articles with metadata
- Full text length and figure count

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

## Database Import Details

### How Import Works

1. **Package Reading**: Gzip-compressed XML packages are decompressed and parsed
2. **Article Extraction**: Each `<article>` element is extracted with metadata
3. **Markdown Conversion**: Full text is converted to Markdown format:
   - `# Title` for article title
   - `## Section` for section headers
   - Paragraphs with proper spacing
   - **Bold** and *italic* formatting preserved
   - Lists converted to Markdown format
4. **Figure Handling**: Figure references are converted to Markdown image placeholders:
   - `![Figure 1: Caption](graphic_reference)`
   - Note: Actual image files are not included in XML packages
5. **Database Upsert**: Articles are inserted or updated based on PMCID

### Update Behavior

By default, the importer will:
- **Insert** new articles that don't exist in the database
- **Update** existing articles if the new full text is longer (adds content)
- **Skip** articles where existing full text is already comprehensive

Use `--no-update` to only insert new articles without modifying existing ones.

### Matching Strategy

Articles are matched using:
1. **PMCID + Source**: Primary matching key (Europe PMC source)
2. **DOI**: Cross-source matching to add full text to existing records

This means if you have articles from PubMed or medRxiv, importing Europe PMC data will add full text to those existing records.

## Programmatic Usage - Import

```python
from pathlib import Path
from bmlibrarian.importers import EuropePMCImporter

# Create importer
importer = EuropePMCImporter(
    packages_dir=Path('~/europepmc/packages'),
    batch_size=100,
    update_existing=True
)

# List available packages
packages = importer.list_packages()
print(f"Found {len(packages)} packages")

# Verify a package before importing
result = importer.verify_package(packages[0])
print(f"Package valid: {result['valid']}")
print(f"Article count: {result['article_count']}")

# Import all packages with progress
def on_progress(pkg_name, pkg_num, total_pkgs, articles):
    print(f"[{pkg_num}/{total_pkgs}] {pkg_name}: {articles} articles imported")

stats = importer.import_all_packages(
    progress_callback=on_progress,
    limit=10  # Optional: limit packages
)

print(f"Inserted: {stats['imported_articles']}")
print(f"Updated: {stats['updated_articles']}")
print(f"Skipped: {stats['skipped_articles']}")

# Check status
status = importer.get_status()
print(f"Total processed: {status['total_articles']}")
```

### Parsing XML Directly

```python
from bmlibrarian.importers import EuropePMCXMLParser

parser = EuropePMCXMLParser()

# Parse a package (xml_content is the decompressed XML string)
for article in parser.parse_package(xml_content):
    print(f"PMCID: {article.pmcid}")
    print(f"Title: {article.title}")
    print(f"Full text length: {len(article.full_text)} chars")
    print(f"Figures: {len(article.figures)}")
```

## Image Handling

### Current Behavior

Europe PMC XML packages contain **references** to images, not the actual image files. The importer converts these to Markdown placeholders:

```markdown
![Figure 1: Cell division in vitro](BCR-3-1-061-1)
```

The graphic reference (e.g., `BCR-3-1-061-1`) can be used to fetch images from Europe PMC's servers if needed.

### Fetching Images (Future Enhancement)

Images can be retrieved from Europe PMC using URLs like:
```
https://europepmc.org/articles/PMC123456/bin/BCR-3-1-061-1.jpg
```

A future enhancement could add automatic image downloading and local storage.

## Related Documentation

- [Europe PMC Downloads](https://europepmc.org/downloads)
- [Europe PMC Open Access](https://europepmc.org/downloads/openaccess)
- [JATS XML Format](https://jats.nlm.nih.gov/)
- [BMLibrarian Importers](../developers/importer_system.md)
