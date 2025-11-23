# PDF Download Guide

This guide covers the PDF download functionality in BMLibrarian, including the intelligent discovery system and browser-based fallback for protected PDFs.

## Overview

BMLibrarian provides a comprehensive PDF retrieval system that:

1. **Discovers** the best available PDF sources (PMC, Unpaywall, DOI, direct URL)
2. **Downloads** via direct HTTP from discovered sources (prioritizing open access)
3. **Falls back** to browser-based download for Cloudflare-protected or paywalled sites

## Quick Start

### Using the Discovery System

```python
from bmlibrarian.discovery import download_pdf_for_document
from pathlib import Path

# Document with DOI (recommended)
document = {
    'doi': '10.1038/nature12373',
    'id': 12345,
    'publication_date': '2024-01-15'
}

# Download PDF
result = download_pdf_for_document(
    document=document,
    output_dir=Path('~/pdfs').expanduser(),
    unpaywall_email='your@email.com'  # Optional but recommended
)

if result.success:
    print(f"Downloaded to: {result.file_path}")
    print(f"Source: {result.source.source_type.value}")
    print(f"Size: {result.file_size} bytes")
else:
    print(f"Failed: {result.error_message}")
```

### Using PDFManager

```python
from bmlibrarian.utils.pdf_manager import PDFManager

pdf_manager = PDFManager(base_dir='~/pdfs')

document = {
    'doi': '10.1234/example',
    'pmid': '12345678',
    'id': 123
}

# Discovery-based download (recommended)
path = pdf_manager.download_pdf_with_discovery(
    document,
    unpaywall_email='your@email.com'
)

# Or use the simpler direct download (uses browser fallback)
path = pdf_manager.download_pdf(document)
```

## Download Strategies

### 1. Direct HTTP Download

The simplest approach, using a URL stored in the database:

```python
path = pdf_manager.download_pdf({'pdf_url': 'https://example.com/paper.pdf'})
```

**Pros:** Fast, simple
**Cons:** May fail on protected sites

### 2. Discovery-First Workflow

Uses multiple resolvers to find the best available source:

```python
path = pdf_manager.download_pdf_with_discovery(
    document={'doi': '10.1234/example'},
    use_browser_fallback=True
)
```

**Workflow:**
1. PMC (PubMed Central) - Verified open access
2. Unpaywall - Open access aggregator
3. DOI resolution - CrossRef and doi.org
4. Direct URL - From database
5. OpenAthens - Institutional proxy (if configured)

**Pros:** Finds best source automatically, handles paywalls
**Cons:** Slower due to multiple API calls

### 3. Browser-Based Download

For Cloudflare-protected and anti-bot protected sites:

```python
from bmlibrarian.utils.browser_downloader import download_pdf_with_browser

result = download_pdf_with_browser(
    url='https://protected-site.com/paper.pdf',
    save_path=Path('/tmp/paper.pdf'),
    headless=True
)
```

**Features:**
- Cloudflare bypass (waits for verification)
- Anti-bot protection handling
- Embedded PDF viewer detection
- Download link detection

**Pros:** Works on protected sites
**Cons:** Slower, requires Playwright

## Configuration

### Config File Settings

Add to `~/.bmlibrarian/config.json`:

```json
{
  "unpaywall_email": "your@email.com",
  "discovery": {
    "timeout": 30,
    "prefer_open_access": true,
    "use_browser_fallback": true,
    "browser_headless": true,
    "browser_timeout": 60000,
    "skip_resolvers": []
  },
  "openathens": {
    "enabled": false,
    "institution_url": "https://your-institution.openathens.net"
  }
}
```

### Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `unpaywall_email` | None | Email for Unpaywall API (strongly recommended) |
| `discovery.timeout` | 30 | HTTP request timeout in seconds |
| `discovery.prefer_open_access` | true | Stop search at first OA source |
| `discovery.use_browser_fallback` | true | Use browser when HTTP fails |
| `discovery.browser_headless` | true | Run browser without UI |
| `discovery.browser_timeout` | 60000 | Browser timeout in milliseconds |
| `discovery.skip_resolvers` | [] | Resolvers to skip: pmc, unpaywall, doi, direct_url, openathens |

## Document Card Integration

The document card "Fetch" button automatically uses the discovery workflow:

```python
from bmlibrarian.gui.qt.qt_document_card_factory import QtDocumentCardFactory
from bmlibrarian.utils.pdf_manager import PDFManager

# Create factory with discovery enabled
factory = QtDocumentCardFactory(
    pdf_manager=PDFManager(base_dir='~/pdfs'),
    use_discovery=True,
    unpaywall_email='your@email.com'
)

# Cards created with this factory will use discovery for the Fetch button
card = factory.create_card(card_data)
```

## Source Priority

When discovering sources, they are prioritized:

| Priority | Source | Description |
|----------|--------|-------------|
| 1 | Unpaywall (best_oa) | Curated best open access location |
| 2+ | Unpaywall (other) | Other open access locations |
| 5-6 | PMC | PubMed Central (verified OA) |
| 10 | Direct URL | URL from database |
| 15 | DOI (doi.org) | Content negotiation |
| 20 | DOI (CrossRef) | CrossRef API |
| 50 | OpenAthens | Institutional proxy |

## Error Handling

### Common Errors

```python
result = download_pdf_for_document(document)

if not result.success:
    if "403" in result.error_message:
        print("Access denied - may need institutional subscription")
    elif "404" in result.error_message:
        print("PDF not found at source")
    elif "No PDF sources found" in result.error_message:
        print("Could not discover any PDF sources")
    elif "Browser download failed" in result.error_message:
        print("Browser fallback also failed")
```

### Progress Callbacks

Track download progress:

```python
def progress_callback(stage: str, status: str):
    print(f"[{stage}] {status}")
    # Stages: discovery, download, browser_download
    # Statuses: starting, found, not_found, success, failed

result = download_pdf_for_document(
    document,
    progress_callback=progress_callback
)
```

## Requirements

### For Basic Functionality

- Python >= 3.12
- requests library (included)

### For Browser Fallback

Install Playwright:

```bash
uv add playwright
uv run python -m playwright install chromium
```

### For OpenAthens Support

See `doc/users/openathens_guide.md` for institutional access setup.

## Troubleshooting

### Browser Download Not Working

1. Verify Playwright is installed:
   ```bash
   uv run python -c "from playwright.sync_api import sync_playwright; print('OK')"
   ```

2. Install browser:
   ```bash
   uv run python -m playwright install chromium
   ```

3. Try visible mode for debugging:
   ```python
   result = download_pdf_for_document(
       document,
       browser_headless=False  # See browser UI
   )
   ```

### Unpaywall Not Finding Sources

1. Verify email is set (required for API)
2. Check DOI format is correct (e.g., "10.1234/example")
3. Try searching manually at https://unpaywall.org/

### PMC Sources Not Working

1. Verify PMCID format (e.g., "PMC1234567")
2. Check if article is actually in PMC
3. Some PMC articles are embargoed

## API Reference

### download_pdf_for_document()

```python
download_pdf_for_document(
    document: Dict[str, Any],           # Document with identifiers
    output_dir: Optional[Path] = None,  # Output directory
    unpaywall_email: Optional[str] = None,
    openathens_proxy_url: Optional[str] = None,
    use_browser_fallback: bool = True,
    browser_headless: bool = True,
    browser_timeout: int = 60000,       # milliseconds
    progress_callback: Optional[Callable] = None
) -> DownloadResult
```

### DownloadResult

```python
@dataclass
class DownloadResult:
    success: bool                       # True if download succeeded
    source: Optional[PDFSource]         # Source that worked
    file_path: Optional[str]            # Path to downloaded file
    file_size: int = 0                  # Size in bytes
    error_message: Optional[str]        # Error description
    duration_ms: float = 0              # Total time taken
    attempts: int = 1                   # Number of sources tried
```

## See Also

- `doc/users/openathens_guide.md` - OpenAthens institutional access
- `doc/users/BROWSER_DOWNLOADER.md` - Browser downloader details
- `doc/developers/discovery_system.md` - Technical architecture
