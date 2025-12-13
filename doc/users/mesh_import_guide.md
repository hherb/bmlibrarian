# MeSH Import Guide

This guide explains how to download and import the MeSH (Medical Subject Headings) vocabulary into BMLibrarian for fast local lookup.

## Overview

MeSH is a controlled vocabulary developed by the National Library of Medicine (NLM) for indexing and searching biomedical literature. BMLibrarian can store MeSH data locally for:

- **Fast term validation** - Instantly validate MeSH terms without API calls
- **Term expansion** - Expand queries with synonyms and entry terms
- **Hierarchical navigation** - Navigate broader/narrower terms
- **Offline operation** - Work without internet connectivity

## Database Size

| Component | Approximate Count | Storage |
|-----------|------------------|---------|
| Descriptors | ~30,000 | ~50 MB |
| Concepts | ~60,000 | ~20 MB |
| Terms (entry terms) | ~300,000 | ~100 MB |
| Tree numbers | ~60,000 | ~10 MB |
| Qualifiers | ~80 | <1 MB |
| Supplementary Concepts (SCRs) | ~300,000 | ~200 MB |

**Total estimated storage:** ~400 MB with SCRs, ~180 MB without

**Download sizes (compressed XML):**
- Descriptors: ~150 MB
- Qualifiers: ~1 MB
- Supplementary: ~200 MB

## Quick Start

### 1. Import MeSH Data

```bash
# Import MeSH 2025 (descriptors, qualifiers, and supplementary concepts)
uv run python mesh_import_cli.py import --year 2025

# Skip supplementary concepts for faster import (~180 MB vs ~400 MB)
uv run python mesh_import_cli.py import --year 2025 --no-supplementary

# Auto-confirm without prompt
uv run python mesh_import_cli.py import --year 2025 -y
```

### 2. Verify Import

```bash
# Check database statistics
uv run python mesh_import_cli.py status

# View import history
uv run python mesh_import_cli.py history
```

### 3. Test Lookup

```bash
# Look up a term
uv run python mesh_import_cli.py lookup "heart attack"

# Search by partial match
uv run python mesh_import_cli.py search "cardio"

# Expand term to all synonyms
uv run python mesh_import_cli.py expand "MI"
```

## CLI Commands

### Import Command

```bash
uv run python mesh_import_cli.py import [options]
```

Options:
- `--year YEAR` - MeSH year to import (default: current year)
- `--no-supplementary` - Skip supplementary concept records
- `--download-dir PATH` - Directory for downloaded files
- `--delete-downloads` - Delete downloaded files after import
- `-y, --yes` - Skip confirmation prompt

### Status Command

```bash
uv run python mesh_import_cli.py status
```

Shows:
- Local database statistics
- API cache statistics
- Connection status

### History Command

```bash
uv run python mesh_import_cli.py history [--limit N]
```

Shows import history with statistics.

### Lookup Command

```bash
uv run python mesh_import_cli.py lookup "term"
```

Look up a MeSH term and display:
- Descriptor UI and name
- Scope note (definition)
- Tree numbers (hierarchy)
- Entry terms (synonyms)
- PubMed query syntax

### Search Command

```bash
uv run python mesh_import_cli.py search "query" [--limit N]
```

Search MeSH by partial match.

### Expand Command

```bash
uv run python mesh_import_cli.py expand "term"
```

Expand a term to all synonyms/entry terms.

### Clear Cache Command

```bash
uv run python mesh_import_cli.py clear-cache [-y]
```

Clear the API cache (SQLite).

## Programmatic Usage

### Using MeSHService

```python
from bmlibrarian.mesh import MeSHService

# Create service (auto-detects local database)
service = MeSHService()

# Check if local database is available
print(f"Local DB: {service.is_local_db_available()}")

# Look up a term
result = service.lookup("heart attack")
if result.found:
    print(f"Descriptor: {result.descriptor_name}")
    print(f"UI: {result.descriptor_ui}")
    print(f"Source: {result.source}")  # local_database, nlm_api, or cache
    print(f"Entry terms: {result.entry_terms}")

# Expand term to all synonyms
terms = service.expand("MI")
print(f"Synonyms: {terms}")

# Search by partial match
results = service.search("cardio", limit=10)
for r in results:
    print(f"  {r.descriptor_name} ({r.descriptor_ui})")

# Get broader terms (parents in hierarchy)
broader = service.get_broader_terms("D009203")  # Myocardial Infarction

# Get narrower terms (children in hierarchy)
narrower = service.get_narrower_terms("D006331")  # Heart Diseases
```

### Using MeSHLookup (Existing API)

The existing `MeSHLookup` class now automatically uses the local database:

```python
from bmlibrarian.pubmed_search import MeSHLookup

# Create lookup (now checks local DB first)
lookup = MeSHLookup()

# Check local DB availability
print(f"Local DB: {lookup.is_local_db_available()}")

# Validate a term
result = lookup.validate_term("Cardiovascular Diseases")
if result.is_valid:
    print(f"Valid: {result.descriptor_name}")
    print(f"Entry terms: {result.entry_terms}")

# Disable local DB lookup (API only)
lookup_api_only = MeSHLookup(use_local_db=False)
```

### Using MeSHImporter

```python
from bmlibrarian.importers import MeSHImporter

# Create importer
importer = MeSHImporter(keep_downloads=True)

# Import MeSH 2025
stats = importer.import_mesh(year=2025, include_supplementary=True)

print(f"Imported: {stats.descriptors:,} descriptors")
print(f"          {stats.concepts:,} concepts")
print(f"          {stats.terms:,} terms")
print(f"          {stats.supplementary_concepts:,} SCRs")
print(f"Duration: {stats.duration_seconds:.1f}s")

# Get import history
history = importer.get_import_history()

# Get current statistics
stats = importer.get_statistics()
```

## Database Schema

The MeSH data is stored in the `mesh` schema:

```sql
-- Main descriptors (MeSH headings)
mesh.descriptors

-- Concepts within descriptors
mesh.concepts

-- Term variants (entry terms, synonyms)
mesh.terms

-- Hierarchical tree numbers
mesh.tree_numbers

-- Subheading qualifiers
mesh.qualifiers

-- Supplementary concept records (chemicals, drugs, etc.)
mesh.supplementary_concepts

-- Import history
mesh.import_history
```

### Utility Functions

The schema includes helpful PostgreSQL functions:

```sql
-- Look up a term
SELECT * FROM mesh.lookup_term('heart attack');

-- Get all entry terms for a descriptor
SELECT * FROM mesh.get_entry_terms('D009203');

-- Get tree hierarchy
SELECT * FROM mesh.get_tree_hierarchy('D009203');

-- Get broader (parent) terms
SELECT * FROM mesh.get_broader_terms('D009203');

-- Get narrower (child) terms
SELECT * FROM mesh.get_narrower_terms('D006331');

-- Search by partial match
SELECT * FROM mesh.search('cardio', 20);

-- Expand term to all synonyms
SELECT * FROM mesh.expand_term('MI');

-- Get database statistics
SELECT * FROM mesh.get_statistics();
```

## Lookup Behavior

When validating MeSH terms, the system checks sources in this order:

1. **Local PostgreSQL database** (mesh schema) - Fastest, no network
2. **SQLite API cache** - For previously looked up terms (API results)
3. **NLM API** - For terms not in local DB or cache

This ensures:
- Fast lookups when local data is available
- Automatic fallback when local data is incomplete
- Cached API results to minimize network calls

## Updating MeSH Data

MeSH is updated annually (new version released in November/December). To update:

```bash
# Import new year's data
uv run python mesh_import_cli.py import --year 2026

# The importer uses UPSERT, so existing records are updated
```

## Troubleshooting

### Import Fails to Download

Check network connectivity and try:
```bash
# Specify download directory
uv run python mesh_import_cli.py import --year 2025 --download-dir ~/Downloads/mesh
```

### Database Connection Issues

Ensure PostgreSQL is running and credentials are configured:
```bash
# Check connection
uv run python -c "from bmlibrarian.database import get_db_manager; print(get_db_manager())"
```

### Migration Not Applied

If the `mesh` schema doesn't exist, apply migrations:
```bash
# Migrations are auto-applied on database connection
uv run python -c "from bmlibrarian.database import get_db_manager; get_db_manager()"
```

### Slow Lookups

If lookups are slow, ensure indexes exist:
```sql
-- Check for indexes
SELECT indexname FROM pg_indexes WHERE schemaname = 'mesh';
```

## See Also

- [PubMed Search Lab](pubmed_search_lab_guide.md) - Uses MeSH for query conversion
- [Query Converter](query_converter_guide.md) - Natural language to PubMed queries
- [MeSH Architecture](../developers/mesh_architecture.md) - Technical documentation
