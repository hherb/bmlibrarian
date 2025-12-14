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

**Download sizes (XML files):**
- Descriptors: ~314 MB
- Qualifiers: ~300 KB
- Supplementary: ~240 MB

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

# Expand term to all synonyms (use MeSH terms, not abbreviations)
uv run python mesh_import_cli.py expand "Heart Attack"
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

**Important:** The expand command requires exact matches on MeSH entry terms. See [Clinical Abbreviations](#clinical-abbreviations-not-in-mesh) below for details on what terms are supported.

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

# Expand term to all synonyms (use MeSH terms, not clinical abbreviations)
terms = service.expand("Heart Attack")
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

## Clinical Abbreviations Not in MeSH

MeSH is a **controlled vocabulary** that uses standardized medical terminology, not clinical shorthand. Common medical abbreviations used in clinical practice are generally **not included** as MeSH entry terms.

### Abbreviations That Won't Work

| Abbreviation | Full Term | Why It's Not in MeSH |
|--------------|-----------|---------------------|
| MI | Myocardial Infarction | Clinical shorthand |
| AMI | Acute Myocardial Infarction | Clinical shorthand |
| ONSD | Optic Nerve Sheath Diameter | Measurement technique, not disease |
| CHF | Congestive Heart Failure | Clinical shorthand |
| COPD | Chronic Obstructive Pulmonary Disease | *Actually in MeSH as "COPD"* |
| HTN | Hypertension | Clinical shorthand |
| DM | Diabetes Mellitus | Clinical shorthand |
| CVA | Cerebrovascular Accident | Clinical shorthand |
| DVT | Deep Vein Thrombosis | Clinical shorthand |
| PE | Pulmonary Embolism | Clinical shorthand |

### What MeSH Does Include

MeSH includes:
- **Preferred terms**: Official descriptor names (e.g., "Myocardial Infarction")
- **Entry terms**: Synonyms and alternate names (e.g., "Heart Attack")
- **Some abbreviations**: Only those officially recognized in the vocabulary (e.g., "DNA", "RNA", "AIDS", "COPD", "ECG")

### Workarounds

1. **Use the full term or a known synonym:**
   ```bash
   # Instead of "MI", use:
   uv run python mesh_import_cli.py expand "Heart Attack"
   uv run python mesh_import_cli.py expand "Myocardial Infarction"
   ```

2. **Use the search command to find related terms:**
   ```bash
   # Find terms containing "infarct"
   uv run python mesh_import_cli.py search "infarct"
   ```

3. **Look up the full term first, then expand:**
   ```bash
   # Find the descriptor
   uv run python mesh_import_cli.py lookup "Myocardial Infarction"
   # Then expand it
   uv run python mesh_import_cli.py expand "Myocardial Infarction"
   ```

### Checking What Abbreviations Exist

To see what abbreviations MeSH actually contains:
```sql
-- Find short uppercase terms marked as abbreviations or acronyms
SELECT term_text, lexical_tag
FROM mesh.terms
WHERE term_text ~ '^[A-Z]{2,5}$'
  AND lexical_tag IN ('ABB', 'ACR')
ORDER BY term_text;
```

Common abbreviations that *are* in MeSH include: AIDS, ADP, AMP, ATP, DNA, RNA, ECG, EKG, ELISA, GABA, HPLC, and others primarily from biochemistry and laboratory science.

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

### "Not a gzipped file" Error

If you see an error like `Not a gzipped file (b'<?' or b'\n\n')`, this indicates the downloaded file is HTML (likely an error page) instead of XML data. This was fixed in December 2025 - ensure you have the latest code.

The importer downloads plain XML files from NLM at:
```
https://nlmpubs.nlm.nih.gov/projects/mesh/MESH_FILES/xmlmesh/desc{year}.xml
```

To verify downloads are working:
```bash
# Check a download URL returns correct content type
curl -I "https://nlmpubs.nlm.nih.gov/projects/mesh/MESH_FILES/xmlmesh/desc2025.xml"
# Should show: Content-Type: text/xml
```

### Downloaded Files Are Tiny (< 100KB)

If downloaded files are very small (e.g., 16KB), they're likely HTML error pages. Delete them and re-run the import:
```bash
# Clean old downloads
rm -rf ~/.bmlibrarian/downloads/mesh/*

# Re-run import
uv run python mesh_import_cli.py import --year 2025
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
- [MeSH Import System](../developers/mesh_import_system.md) - Technical documentation
