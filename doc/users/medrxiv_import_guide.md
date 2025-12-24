# MedRxiv Import Guide

## Overview

The MedRxiv importer allows you to import biomedical preprints from [medRxiv](https://www.medrxiv.org) into your BMLibrarian knowledge base. MedRxiv is a preprint server for health sciences, and this importer provides automated access to its API for downloading metadata, PDFs, and extracting full text.

## Features

- **Automated Metadata Import**: Fetch paper metadata from the medRxiv API
- **Multi-Format Full-Text Extraction**: Priority-based extraction from text, HTML, XML, and PDF
- **PDF Downloads**: Download PDFs for preprints (fallback for full-text extraction)
- **Incremental Updates**: Automatically resume from the last import date
- **Batch Processing**: Handle large datasets efficiently with weekly chunking
- **Error Recovery**: Retry logic with exponential backoff for network errors
- **AWS MECA Bulk Sync** (Optional): Download complete MECA packages from AWS S3 for offline access

## Full-Text Extraction Strategies

BMLibrarian supports three extraction strategies for medRxiv papers:

| Strategy | Description | Use Case |
|----------|-------------|----------|
| `auto` (default) | Try text → HTML → JATS XML → PDF | Best quality, recommended |
| `pdf_only` | Only use PDF extraction | Legacy behavior, offline use |
| `web_only` | Only try web formats, skip PDF | Fast, minimal downloads |

### Extraction Priority (Auto Strategy)

1. **Plain Text** (`.full.txt`) - Fastest, cleanest output when available
2. **HTML** (`.full.html`) - Web scraping with BeautifulSoup → Markdown conversion
3. **JATS XML** (via API `jats_xml_path`) - Structured XML parsing
4. **PDF** (`.full.pdf`) - Subprocess-isolated pymupdf4llm extraction (fallback)

## Installation Requirements

The medRxiv importer requires the following Python packages:

```bash
# Install via uv (recommended)
uv pip install pymupdf4llm requests tqdm beautifulsoup4 markdownify lxml

# Or via pip
pip install pymupdf4llm requests tqdm beautifulsoup4 markdownify lxml

# For AWS MECA bulk sync (optional)
uv pip install bmlibrarian[aws]
# Or: pip install boto3
```

These dependencies are included in BMLibrarian's standard `pyproject.toml` file.

## Quick Start

### Basic Update (Metadata Only)

Fetch the last 7 days of new papers without downloading PDFs:

```bash
uv run python medrxiv_import_cli.py update --days-to-fetch 7
```

### Full Update with Multi-Format Extraction (Recommended)

Fetch papers with automatic multi-format full-text extraction:

```bash
uv run python medrxiv_import_cli.py update --download-pdfs --days-to-fetch 30
```

This uses the default `auto` strategy: tries text → HTML → JATS XML → PDF fallback.

### Update with Specific Extraction Strategy

```bash
# Use only PDF extraction (legacy behavior)
uv run python medrxiv_import_cli.py update --download-pdfs --extraction-strategy pdf_only

# Use only web formats (faster, no PDF downloads)
uv run python medrxiv_import_cli.py update --extraction-strategy web_only
```

### Re-Extract Full Text for Existing Records

Update papers that are missing full text using better formats:

```bash
# Re-extract only papers without full text
uv run python medrxiv_import_cli.py extract-text --missing-only --limit 100

# Re-extract all papers with a specific strategy
uv run python medrxiv_import_cli.py extract-text --extraction-strategy auto
```

### Download Missing PDFs

Download PDFs for papers already in the database:

```bash
uv run python medrxiv_import_cli.py fetch-pdfs --limit 100
```

### Check Import Status

View statistics about your medRxiv collection:

```bash
uv run python medrxiv_import_cli.py status
```

## Command Reference

### `update` - Import New Papers

Import new papers from the medRxiv API.

**Usage:**
```bash
uv run python medrxiv_import_cli.py update [OPTIONS]
```

**Options:**
- `--download-pdfs`: Download PDFs for each paper (increases processing time)
- `--extraction-strategy {auto,pdf_only,web_only}`: Full-text extraction strategy (default: auto)
- `--start-date YYYY-MM-DD`: Override start date (useful for backfilling)
- `--end-date YYYY-MM-DD`: Override end date (defaults to today)
- `--days-to-fetch N`: Number of days back to fetch if database is empty (default: 1095)
- `--max-retries N`: Maximum retry attempts for failed API requests (default: 5)
- `--pdf-dir PATH`: Override PDF storage directory
- `-v, --verbose`: Enable verbose logging

**Examples:**

1. **Daily update (metadata only):**
   ```bash
   uv run python medrxiv_import_cli.py update --days-to-fetch 1
   ```

2. **Backfill 2024 papers with PDFs:**
   ```bash
   uv run python medrxiv_import_cli.py update \
       --start-date 2024-01-01 \
       --end-date 2024-12-31 \
       --download-pdfs
   ```

3. **Complete historical import:**
   ```bash
   uv run python medrxiv_import_cli.py update \
       --start-date 2019-06-06 \
       --download-pdfs
   ```

### `fetch-pdfs` - Download Missing PDFs

Download PDFs for papers already in the database that don't have PDFs yet.

**Usage:**
```bash
uv run python medrxiv_import_cli.py fetch-pdfs [OPTIONS]
```

**Options:**
- `--limit N`: Maximum number of PDFs to download
- `--max-retries N`: Maximum retry attempts for failed downloads (default: 5)
- `--no-convert`: Skip PDF to markdown conversion (faster but no full text)
- `--pdf-dir PATH`: Override PDF storage directory
- `-v, --verbose`: Enable verbose logging

**Examples:**

1. **Download 50 missing PDFs:**
   ```bash
   uv run python medrxiv_import_cli.py fetch-pdfs --limit 50
   ```

2. **Download all missing PDFs (no limit):**
   ```bash
   uv run python medrxiv_import_cli.py fetch-pdfs
   ```

### `extract-text` - Re-Extract Full Text

Re-extract full text for existing records using multi-format extraction.

**Usage:**
```bash
uv run python medrxiv_import_cli.py extract-text [OPTIONS]
```

**Options:**
- `--limit N`: Maximum number of papers to process
- `--missing-only`: Only process papers without full text
- `--extraction-strategy {auto,pdf_only,web_only}`: Extraction strategy (default: auto)
- `--pdf-dir PATH`: Override PDF storage directory
- `-v, --verbose`: Enable verbose logging

**Examples:**

1. **Re-extract papers missing full text:**
   ```bash
   uv run python medrxiv_import_cli.py extract-text --missing-only --limit 100
   ```

2. **Re-extract all papers with web formats only:**
   ```bash
   uv run python medrxiv_import_cli.py extract-text --extraction-strategy web_only
   ```

3. **Full re-extraction of all papers:**
   ```bash
   uv run python medrxiv_import_cli.py extract-text --extraction-strategy auto
   ```

### `status` - Show Import Statistics

Display statistics about your medRxiv collection.

**Usage:**
```bash
uv run python medrxiv_import_cli.py status
```

**Output includes:**
- Latest paper date in database
- Suggested resume date for next update
- Total number of medRxiv papers
- Number/percentage of papers with PDFs
- Number/percentage of papers with full text
- Number of papers missing full text
- Current extraction strategy and priority order

## Configuration

### PDF Storage Directory

By default, PDFs are stored in `~/knowledgebase/pdf`. You can override this in three ways:

1. **Environment variable** (in `.env` file):
   ```bash
   PDF_BASE_DIR=~/my_pdfs
   ```

2. **Command-line flag**:
   ```bash
   uv run python medrxiv_import_cli.py update --pdf-dir /path/to/pdfs
   ```

3. **Programmatic usage**:
   ```python
   from bmlibrarian.importers import MedRxivImporter
   importer = MedRxivImporter(pdf_base_dir="/path/to/pdfs")
   ```

### Database Configuration

The importer uses BMLibrarian's standard database configuration from your `.env` file:

```bash
POSTGRES_DB=knowledgebase
POSTGRES_USER=your_username
POSTGRES_PASSWORD=your_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
```

Ensure these are properly configured before running the importer.

## Programmatic Usage

You can also use the importer directly in Python code:

```python
from bmlibrarian.importers import MedRxivImporter

# Initialize importer with extraction strategy
importer = MedRxivImporter(
    extraction_strategy='auto',  # 'auto', 'pdf_only', or 'web_only'
    extraction_priority=['text', 'html', 'jats_xml', 'pdf']  # Custom priority
)

# Update database with last 30 days of papers
stats = importer.update_database(
    download_pdfs=True,
    days_to_fetch=30
)

print(f"Processed {stats['total_processed']} papers")

# Download missing PDFs (limit to 100)
count = importer.fetch_missing_pdfs(limit=100)
print(f"Downloaded {count} PDFs")

# Re-extract full text for papers missing it
reextract_stats = importer.reextract_full_text(
    limit=100,
    missing_only=True
)
print(f"Re-extracted {reextract_stats['extracted']} papers")
print(f"By format: {reextract_stats['by_format']}")

# Get extraction statistics
stats = importer.get_extraction_statistics()
print(f"Total papers: {stats['total_papers']}")
print(f"With full text: {stats['with_fulltext']} ({stats['fulltext_percentage']}%)")
print(f"Strategy: {stats['extraction_strategy']}")
print(f"Priority: {' → '.join(stats['extraction_priority'])}")

# Check status
latest_date = importer.get_latest_date()
print(f"Latest paper: {latest_date}")

missing = importer.get_preprints_without_fulltext(limit=10)
print(f"Found {len(missing)} papers without full text")
```

## Workflow Recommendations

### Initial Setup

1. **Start with metadata only** to quickly populate your database:
   ```bash
   uv run python medrxiv_import_cli.py update --days-to-fetch 1095
   ```

2. **Download PDFs in batches** to avoid overwhelming your system:
   ```bash
   uv run python medrxiv_import_cli.py fetch-pdfs --limit 1000
   ```

3. **Check progress regularly**:
   ```bash
   uv run python medrxiv_import_cli.py status
   ```

### Daily Maintenance

Set up a daily cron job or scheduled task:

```bash
# Update metadata daily
0 2 * * * cd /path/to/bmlibrarian && uv run python medrxiv_import_cli.py update --days-to-fetch 2

# Download missing PDFs weekly (100 at a time)
0 3 * * 0 cd /path/to/bmlibrarian && uv run python medrxiv_import_cli.py fetch-pdfs --limit 100
```

### Backfilling Historical Data

To backfill papers from a specific time period:

```bash
# Import 2023 papers (metadata only, fast)
uv run python medrxiv_import_cli.py update \
    --start-date 2023-01-01 \
    --end-date 2023-12-31

# Then download PDFs in batches
uv run python medrxiv_import_cli.py fetch-pdfs --limit 1000
```

## Performance Considerations

### API Rate Limiting

The medRxiv API is rate-limited. The importer includes:
- Exponential backoff retry logic
- Weekly batching of date ranges
- 1-2 second delays between requests

**Avoid:**
- Running multiple import jobs simultaneously
- Requesting very large date ranges without chunking

### PDF Processing

PDF download and text extraction can be time-consuming:
- Each PDF: ~5-20 seconds (download + conversion)
- Large batches (1000+ PDFs): Several hours

**Recommendations:**
- Use `--limit` flag to process PDFs in manageable batches
- Run PDF downloads during off-hours
- Monitor disk space (PDFs can be large)

### Database Performance

The importer checks for existing papers before insertion to avoid duplicates. For best performance:
- Ensure database indexes are in place (automatic with BMLibrarian migrations)
- Process papers in date-ordered batches (done automatically)

## Troubleshooting

### "MedRxiv source not found in database"

**Problem:** The `sources` table doesn't have a 'medrxiv' entry.

**Solution:** Add the source manually:
```sql
INSERT INTO sources (name, description)
VALUES ('medrxiv', 'MedRxiv preprint server for health sciences');
```

### "pymupdf4llm not installed"

**Problem:** PDF text extraction library is missing.

**Solution:**
```bash
uv pip install pymupdf4llm
```

### PDF Conversion Timeouts

**Problem:** Some PDFs fail to convert with timeout errors.

**Solution:**
- Failed PDFs are automatically moved to a `failed/` subdirectory
- These are problematic PDFs (often large or malformed)
- The importer continues processing other files
- You can manually review failed PDFs later

### Network Errors

**Problem:** API requests fail with connection errors.

**Solution:**
- The importer automatically retries with exponential backoff
- If errors persist, check your internet connection
- Verify medRxiv API is accessible: https://api.biorxiv.org/
- Reduce batch size with date ranges if needed

### Duplicate Papers

**Problem:** Concerned about importing papers twice.

**Solution:**
- The importer checks for existing DOIs before insertion
- Running the same date range multiple times is safe
- Existing papers are skipped automatically

## AWS MECA Bulk Sync (Optional)

For comprehensive offline access, medRxiv provides MECA (Manuscript Exchange Common Approach) packages via AWS S3. These packages contain:
- Full-text JATS XML (structured, machine-readable)
- PDF files
- Images and supplementary materials

**Important:** AWS MECA sync requires:
- AWS credentials (access key and secret key)
- AWS S3 costs (requester-pays bucket)

### Installing AWS Dependencies

```bash
uv pip install bmlibrarian[aws]
# Or: pip install boto3
```

### MECA CLI Commands

The `medrxiv_meca_cli.py` provides commands for AWS S3 operations:

```bash
# List available MECA packages
uv run python medrxiv_meca_cli.py list --limit 10

# Download MECA packages
uv run python medrxiv_meca_cli.py download --limit 10 --output-dir ~/medrxiv_meca

# Import downloaded packages to database
uv run python medrxiv_meca_cli.py import --meca-dir ~/medrxiv_meca

# Full sync workflow (download + import)
uv run python medrxiv_meca_cli.py sync --output-dir ~/medrxiv_meca --limit 100

# Show import status
uv run python medrxiv_meca_cli.py status --meca-dir ~/medrxiv_meca
```

### MECA Command Reference

#### `list` - List Available Packages

```bash
uv run python medrxiv_meca_cli.py list [OPTIONS]
```

**Options:**
- `--output-dir PATH`: Output directory for state files (default: ~/medrxiv_meca)
- `--prefix PREFIX`: S3 key prefix filter (e.g., "Current_Content/2024-01/")
- `--limit N`: Maximum packages to list
- `--aws-access-key KEY`: AWS access key
- `--aws-secret-key KEY`: AWS secret key

#### `download` - Download Packages

```bash
uv run python medrxiv_meca_cli.py download [OPTIONS]
```

**Options:**
- `--output-dir PATH`: Output directory for downloads (default: ~/medrxiv_meca)
- `--prefix PREFIX`: S3 key prefix filter
- `--limit N`: Maximum packages to download
- `--delay N`: Delay between downloads in seconds (default: 60)
- `--aws-access-key KEY`: AWS access key
- `--aws-secret-key KEY`: AWS secret key

#### `import` - Import Downloaded Packages

```bash
uv run python medrxiv_meca_cli.py import [OPTIONS]
```

**Options:**
- `--meca-dir PATH`: Directory containing MECA packages (default: ~/medrxiv_meca)
- `--limit N`: Maximum packages to import

#### `sync` - Full Workflow

```bash
uv run python medrxiv_meca_cli.py sync [OPTIONS]
```

Combines download + import in a single command.

**Options:**
- `--output-dir PATH`: Output directory (default: ~/medrxiv_meca)
- `--prefix PREFIX`: S3 key prefix filter
- `--limit N`: Maximum packages
- `--delay N`: Delay between downloads (default: 60)
- `--aws-access-key KEY`: AWS access key
- `--aws-secret-key KEY`: AWS secret key

#### `status` - Show Progress

```bash
uv run python medrxiv_meca_cli.py status [OPTIONS]
```

**Options:**
- `--meca-dir PATH`: Directory containing MECA imports (default: ~/medrxiv_meca)

### AWS Configuration

You can provide AWS credentials in three ways:

1. **Command-line flags:**
   ```bash
   uv run python medrxiv_meca_cli.py list --aws-access-key YOUR_KEY --aws-secret-key YOUR_SECRET
   ```

2. **Environment variables:**
   ```bash
   export AWS_ACCESS_KEY_ID=YOUR_KEY
   export AWS_SECRET_ACCESS_KEY=YOUR_SECRET
   ```

3. **AWS credentials file** (~/.aws/credentials):
   ```ini
   [default]
   aws_access_key_id = YOUR_KEY
   aws_secret_access_key = YOUR_SECRET
   ```

### MECA Cost Considerations

The medRxiv MECA S3 bucket is **requester-pays**, meaning you pay for:
- Data transfer out of AWS
- S3 GET requests

Estimated costs (as of 2024):
- Data transfer: ~$0.09/GB (varies by region)
- Total MECA archive: ~500GB+ (all packages)

For more information, see the [medRxiv TDM page](https://www.medrxiv.org/tdm).

## Technical Details

### Database Schema

Papers are stored in the `document` table with:
- `source_id`: References 'medrxiv' in `sources` table
- `external_id`: Set to the paper's DOI
- `doi`: Paper's DOI
- `title`, `abstract`: Paper metadata
- `authors`: Array of author names
- `publication`: Set to 'medRxiv'
- `publication_date`: Date paper was posted
- `url`: Link to paper on medRxiv.org
- `pdf_url`: Direct PDF download URL
- `pdf_filename`: Local filename (relative to PDF_BASE_DIR)
- `full_text`: Markdown-formatted text extracted from PDF

### API Details

- **Base URL:** https://api.biorxiv.org/details/medrxiv
- **Format:** `{base_url}/{start_date}/{end_date}/{cursor}`
- **Dates:** YYYY-MM-DD format
- **Pagination:** Cursor-based, 100 papers per page
- **Rate Limits:** Undocumented, but respectful usage recommended

### Full-Text Extraction System

The importer supports multiple extraction formats with priority-based selection:

**1. Plain Text** (`.full.txt`)
- Direct download from medRxiv
- Fastest and cleanest when available
- No HTML/XML parsing required

**2. HTML** (`.full.html`)
- BeautifulSoup parsing with lxml backend
- Converted to Markdown using markdownify
- Removes navigation, headers, footers, sidebars
- Preserves article structure (headings, paragraphs, lists)

**3. JATS XML** (via `jats_xml_path` API field)
- Uses NXMLParser from discovery module
- Structured content extraction
- High-quality semantic markup

**4. PDF** (`.full.pdf`)
- Uses `pymupdf4llm` for PDF to markdown conversion
- Subprocess-isolated for crash protection
- Preserves document structure (headings, paragraphs, lists)
- Handles multi-column layouts
- Timeout: 20 seconds per PDF

### Extraction Strategy Selection

| Strategy | Formats Tried | PDF Fallback | Use Case |
|----------|--------------|--------------|----------|
| `auto` | text → HTML → XML → PDF | Yes | Best quality (default) |
| `pdf_only` | PDF only | N/A | Offline, legacy |
| `web_only` | text → HTML → XML | No | Fast, minimal downloads |

## See Also

- [BMLibrarian Query Guide](query_agent_guide.md) - Search imported papers
- [Citation Guide](citation_guide.md) - Extract citations from papers
- [Reporting Guide](reporting_guide.md) - Generate reports from papers
- [Multi-Model Query Guide](multi_model_query_guide.md) - Advanced search strategies
