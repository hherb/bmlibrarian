# Full-Text PDF Discovery Guide

BMLibrarian includes a full-text discovery system that finds and downloads PDF versions of academic papers through legal channels. The system prioritizes open access sources and optionally supports institutional access via OpenAthens authentication.

## Overview

The discovery system searches multiple sources in order of preference:

1. **PubMed Central (PMC)** - Verified open access repository
2. **Unpaywall** - Open access aggregator covering millions of papers
3. **DOI Resolution** - CrossRef and doi.org content negotiation
4. **Direct URL** - Existing PDF URLs from the database
5. **OpenAthens** - Institutional proxy (if configured and authenticated)

## Quick Start

### Basic Usage

```python
from bmlibrarian.discovery import FullTextFinder, DocumentIdentifiers

# Create finder with your email (required for Unpaywall)
finder = FullTextFinder(unpaywall_email="your@email.com")

# Discover PDF sources by DOI
identifiers = DocumentIdentifiers(doi="10.1038/nature12373")
result = finder.discover(identifiers)

# Check results
if result.best_source:
    print(f"Best source: {result.best_source.url}")
    print(f"Access type: {result.best_source.access_type.value}")
    print(f"Source: {result.best_source.source_type.value}")
```

### Download PDFs

```python
from pathlib import Path

# Discover and download in one step
download_result = finder.discover_and_download(
    identifiers,
    output_path=Path("paper.pdf")
)

if download_result.success:
    print(f"Downloaded: {download_result.file_path}")
    print(f"Size: {download_result.file_size} bytes")
else:
    print(f"Failed: {download_result.error_message}")
```

### Convenience Function

```python
from bmlibrarian.discovery import discover_full_text

# Quick discovery without creating a finder instance
result = discover_full_text(
    doi="10.1038/nature12373",
    unpaywall_email="your@email.com"
)
```

## Document Identifiers

You can search using any combination of identifiers:

```python
from bmlibrarian.discovery import DocumentIdentifiers

# From individual identifiers
identifiers = DocumentIdentifiers(
    doi="10.1038/nature12373",
    pmid="23831764",
    pmcid="PMC3749849",
    title="CRISPR-Cas systems for editing"
)

# From database row
row = {'id': 123, 'doi': '10.1038/nature12373', 'pmid': '23831764'}
identifiers = DocumentIdentifiers.from_dict(row)
```

## Configuration

### Basic Configuration

```python
finder = FullTextFinder(
    unpaywall_email="your@email.com",  # Required for Unpaywall API
    timeout=30,                         # HTTP request timeout (seconds)
    prefer_open_access=True,            # Prioritize OA sources
    skip_resolvers=['doi']              # Skip specific resolvers
)
```

### With OpenAthens

```python
from bmlibrarian.utils.openathens_auth import OpenAthensAuth, OpenAthensConfig

# Configure OpenAthens
oa_config = OpenAthensConfig(
    institution_url="https://your-institution.openathens.net"
)
oa_auth = OpenAthensAuth(oa_config)

# Authenticate (opens browser for login)
import asyncio
asyncio.run(oa_auth.login_interactive())

# Create finder with OpenAthens
finder = FullTextFinder(
    unpaywall_email="your@email.com",
    openathens_proxy_url="https://your-institution.openathens.net",
    openathens_auth=oa_auth
)
```

### From Configuration File

Add to your `~/.bmlibrarian/config.json`:

```json
{
  "unpaywall_email": "your@email.com",
  "discovery": {
    "timeout": 30,
    "prefer_open_access": true,
    "skip_resolvers": []
  },
  "openathens": {
    "enabled": true,
    "institution_url": "https://your-institution.openathens.net"
  }
}
```

Then load:

```python
from bmlibrarian.discovery import FullTextFinder
from bmlibrarian.config import load_config

config = load_config()
finder = FullTextFinder.from_config(config)
```

## Understanding Results

### Discovery Result

```python
result = finder.discover(identifiers)

# All found sources (sorted by priority)
for source in result.sources:
    print(f"URL: {source.url}")
    print(f"Type: {source.source_type.value}")
    print(f"Access: {source.access_type.value}")
    print(f"Priority: {source.priority}")

# Best source (selected automatically)
print(f"Best: {result.best_source}")

# Open access check
if result.has_open_access():
    oa_sources = result.get_open_access_sources()
    print(f"Found {len(oa_sources)} OA sources")

# Resolution details
for resolution in result.resolution_results:
    print(f"{resolution.resolver_name}: {resolution.status.value}")
    print(f"  Duration: {resolution.duration_ms:.1f}ms")
```

### Source Types

| Type | Description | Typical Priority |
|------|-------------|------------------|
| `pmc` | PubMed Central | 5-6 (highest) |
| `unpaywall` | Unpaywall OA | 1-3 |
| `doi_redirect` | DOI resolution | 15-20 |
| `direct_url` | Database URL | 10 |
| `openathens` | Institutional | 50 (lowest) |

### Access Types

| Type | Description |
|------|-------------|
| `open` | Freely accessible (OA) |
| `institutional` | Requires institutional access |
| `subscription` | Requires subscription |
| `unknown` | Access level not determined |

## Progress Tracking

Monitor discovery progress with callbacks:

```python
def on_progress(resolver: str, status: str):
    print(f"[{resolver}] {status}")

result = finder.discover(
    identifiers,
    progress_callback=on_progress
)
```

Status values:
- `resolving` - Currently querying resolver
- `found` - Sources found
- `not_found` - No sources found
- `found_oa` - Open access source found (early exit)
- `error` - Resolver failed

## Batch Processing

Process multiple documents efficiently:

```python
from bmlibrarian.discovery import FullTextFinder, DocumentIdentifiers
from pathlib import Path

finder = FullTextFinder(unpaywall_email="your@email.com")

documents = [
    {"doi": "10.1038/nature12373", "id": 1},
    {"doi": "10.1126/science.1231143", "id": 2},
    # ... more documents
]

output_dir = Path("pdfs")
output_dir.mkdir(exist_ok=True)

for doc in documents:
    identifiers = DocumentIdentifiers.from_dict(doc)
    result = finder.discover_and_download(
        identifiers,
        output_path=output_dir / f"{doc['id']}.pdf"
    )

    status = "OK" if result.success else f"FAILED: {result.error_message}"
    print(f"[{doc['id']}] {status}")
```

## Best Practices

### 1. Provide Your Email

Always provide a real email address for the Unpaywall API. This is required by their terms of service and helps them contact you if there are issues.

### 2. Respect Rate Limits

The system includes exponential backoff for retries, but you should still:
- Add delays between batch requests
- Avoid hammering servers with rapid requests
- Use caching where possible

### 3. Use Multiple Identifiers

When available, provide multiple identifiers (DOI, PMID, PMCID) to maximize discovery success.

### 4. Check Access Types

Before downloading, check the access type:

```python
if result.best_source.access_type == AccessType.OPEN:
    # Safe to download without authentication
    pass
elif result.best_source.access_type == AccessType.INSTITUTIONAL:
    # Requires OpenAthens authentication
    pass
```

### 5. Handle Failures Gracefully

```python
result = finder.discover_and_download(identifiers, output_path)

if not result.success:
    if "access denied" in result.error_message.lower():
        # Try with OpenAthens if available
        pass
    elif "not found" in result.error_message.lower():
        # Document may not have PDF available
        pass
    else:
        # Network or other error, may retry
        pass
```

## Troubleshooting

### No Sources Found

1. Verify the identifiers are correct
2. Check if the paper is too new (not yet indexed)
3. Try alternative identifiers (PMID if DOI fails)
4. Some papers simply don't have PDFs available

### Access Denied

1. Paper may be paywalled - configure OpenAthens
2. Check your institutional subscription
3. Some publishers block automated downloads

### Download Validation Fails

1. Server may be returning HTML login page
2. Temporary server issue - retry later
3. PDF may be corrupted at source

### Slow Performance

1. Reduce timeout for faster failures
2. Skip slow resolvers: `skip_resolvers=['doi']`
3. Enable early exit: `stop_on_first_oa=True`

## API Reference

See the [developer documentation](../developers/full_text_discovery_system.md) for detailed API reference and architecture information.
