# PDF Discovery and Download System - Developer Documentation

This document describes the architecture and implementation of the PDF discovery and download system in BMLibrarian.

## Architecture Overview

The PDF retrieval system uses a **three-phase approach**:

```
┌─────────────────────────────────────────────────────────┐
│                    Document with identifiers             │
│                 (DOI, PMID, PMCID, pdf_url)             │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│              Phase 1: Discovery                          │
│                                                          │
│  ┌──────────┐ ┌───────────┐ ┌─────────┐ ┌────────────┐ │
│  │   PMC    │ │ Unpaywall │ │   DOI   │ │ Direct URL │ │
│  │ Resolver │ │ Resolver  │ │Resolver │ │  Resolver  │ │
│  └────┬─────┘ └─────┬─────┘ └────┬────┘ └─────┬──────┘ │
│       │             │            │            │         │
│       └─────────────┴──────┬─────┴────────────┘         │
│                            │                            │
│                    [PDFSource list]                     │
│                    (sorted by priority)                 │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│              Phase 2: Direct HTTP Download               │
│                                                          │
│  for source in sources:                                 │
│      try HTTP GET with retries                          │
│      if success: return                                 │
│      if 401/403/404: skip (no retry)                    │
│      if other error: retry with backoff                 │
└────────────────────────┬────────────────────────────────┘
                         │ (if all HTTP attempts fail)
                         ▼
┌─────────────────────────────────────────────────────────┐
│              Phase 3: Browser Fallback                   │
│                                                          │
│  Uses Playwright to handle:                             │
│  - Cloudflare verification                              │
│  - Anti-bot protections                                 │
│  - Embedded PDF viewers                                 │
│  - Protected download pages                             │
└─────────────────────────────────────────────────────────┘
```

## Key Components

### 1. FullTextFinder (`src/bmlibrarian/discovery/full_text_finder.py`)

The main orchestrator class that coordinates the discovery and download workflow.

**Key Methods:**
- `discover()` - Find PDF sources without downloading
- `discover_and_download()` - Complete workflow with browser fallback
- `download_for_document()` - Convenience method for document dicts
- `_download_with_browser()` - Browser-based fallback

**Configuration Constants:**
```python
DEFAULT_TIMEOUT = 30               # HTTP timeout in seconds
DEFAULT_BROWSER_TIMEOUT_MS = 60000 # Browser timeout in milliseconds
DEFAULT_BROWSER_HEADLESS = True    # Run browser without UI
DEFAULT_MAX_DOWNLOAD_ATTEMPTS = 3  # Retries per source
```

### 2. Resolvers (`src/bmlibrarian/discovery/resolvers.py`)

Each resolver implements `BaseResolver` and provides sources from a specific service:

| Resolver | Priority | Access Type | Description |
|----------|----------|-------------|-------------|
| PMCResolver | 5-6 | OPEN | PubMed Central (verified OA) |
| UnpaywallResolver | 1-2 | OPEN | OA aggregator with best source selection |
| DOIResolver | 15-20 | UNKNOWN | CrossRef + doi.org content negotiation |
| DirectURLResolver | 10 | UNKNOWN | URL from database |
| OpenAthensResolver | 50 | INSTITUTIONAL | Proxy URL construction |

### 3. Data Types (`src/bmlibrarian/discovery/data_types.py`)

Type-safe dataclasses for all data structures:

- `DocumentIdentifiers` - Input identifiers (DOI, PMID, etc.)
- `PDFSource` - A discovered source with URL and metadata
- `DiscoveryResult` - Complete discovery output
- `DownloadResult` - Download attempt result

### 4. BrowserDownloader (`src/bmlibrarian/utils/browser_downloader.py`)

Playwright-based download handler for protected sites:

- Stealth browser configuration
- Cloudflare verification waiting
- Embedded PDF viewer detection
- Download link extraction

### 5. PDFManager Integration (`src/bmlibrarian/utils/pdf_manager.py`)

Extended methods for discovery-based downloads:

- `download_pdf_with_discovery()` - Full discovery workflow
- `get_or_download_with_discovery()` - Check-then-download pattern

## Error Handling Strategy

```python
# HTTP Errors
401, 403, 404 → Skip source immediately (no retry)
Other HTTP    → Retry with exponential backoff

# Content Errors
HTML instead of PDF → Skip source (likely paywall)
Empty file          → Retry (transmission error)
Invalid PDF         → Skip source

# All Sources Failed
→ Try browser fallback (if enabled)
→ Return DownloadResult with error_message
```

## Configuration

### Config File (`~/.bmlibrarian/config.json`)

```json
{
  "unpaywall_email": "user@example.com",
  "discovery": {
    "timeout": 30,
    "prefer_open_access": true,
    "use_browser_fallback": true,
    "browser_headless": true,
    "browser_timeout": 60000,
    "skip_resolvers": []
  }
}
```

### Environment Variables

- `PDF_BASE_DIR` - Base directory for PDF storage (default: `~/knowledgebase/pdf`)

## Thread Safety

The `QtDocumentCardFactory` uses `QMutex` for thread-safe state transitions in PDF buttons. The download handlers execute in the main thread to avoid Qt threading issues.

## File Organization

PDFs are organized by publication year:

```
base_dir/
├── 2024/
│   ├── 10.1234_example1.pdf
│   └── 10.1234_example2.pdf
├── 2023/
│   └── doc_12345.pdf
└── unknown/
    └── doc_99999.pdf
```

## Adding New Resolvers

1. Create a new class inheriting from `BaseResolver`
2. Implement `resolve(identifiers: DocumentIdentifiers) -> ResolutionResult`
3. Set appropriate priority values for returned sources
4. Add to `FullTextFinder.__init__()` resolver list
5. Add to skip_resolvers config handling

Example:
```python
class MyNewResolver(BaseResolver):
    name = "my_resolver"

    def resolve(self, identifiers: DocumentIdentifiers) -> ResolutionResult:
        # Implementation
        pass
```

## Testing

Tests are in `tests/test_pdf_discovery_download.py`:

- Unit tests for FullTextFinder methods
- Mock-based tests for download workflow
- Year extraction tests
- Path generation tests

Run tests:
```bash
uv run python -m pytest tests/test_pdf_discovery_download.py -v
```

## Performance Considerations

1. **Early Exit**: Discovery stops at first OA source (configurable)
2. **Source Caching**: PDF paths cached in `QtDocumentCardFactory`
3. **Parallel Discovery**: Resolvers run sequentially (could be parallelized)
4. **Browser Reuse**: Browser instance created per-download (could pool)

## Dependencies

Required:
- `requests` - HTTP downloads
- `pathlib` - Path handling

Optional:
- `playwright` - Browser fallback (install separately)

## See Also

- `doc/users/pdf_download_guide.md` - User guide
- `doc/users/BROWSER_DOWNLOADER.md` - Browser downloader details
- `doc/users/openathens_guide.md` - OpenAthens authentication
