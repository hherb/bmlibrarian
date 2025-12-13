# MeSH Import System - Developer Documentation

## Architecture Overview

The MeSH Import System downloads and imports the complete MeSH (Medical Subject Headings) vocabulary from the National Library of Medicine (NLM) into the local PostgreSQL database. This enables fast local lookups without API calls.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         MeSHImporter                                     │
│                    (Download + Import Orchestration)                     │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        ▼                           ▼                           ▼
┌───────────────────┐    ┌───────────────────┐    ┌───────────────────┐
│  NLM File Server  │    │   XML Parser      │    │   PostgreSQL      │
│  (HTTPS Download) │    │   (iterparse)     │    │   (mesh schema)   │
└───────────────────┘    └───────────────────┘    └───────────────────┘
        │                           │                           │
        ▼                           ▼                           ▼
┌───────────────────┐    ┌───────────────────┐    ┌───────────────────┐
│  Local Downloads  │    │   Dataclasses     │    │  MeSHService      │
│  (~/.bmlibrarian) │    │   (Parsed Data)   │    │  (Lookup API)     │
└───────────────────┘    └───────────────────┘    └───────────────────┘
```

## Module Structure

```
src/bmlibrarian/importers/
├── __init__.py           # Public API exports
└── mesh_importer.py      # MeSH download and import

src/bmlibrarian/mesh/
├── __init__.py           # Public API exports
├── lookup.py             # MeSHService for lookups
└── data_types.py         # MeSH-specific dataclasses

src/bmlibrarian/pubmed_search/
├── mesh_lookup.py        # MeSHLookup (integrates with local DB)
└── constants.py          # Shared constants (MESH_DESCRIPTOR_PREFIX, etc.)
```

## NLM File Server URLs

MeSH XML files are hosted on NLM's public file server:

```
Base URL: https://nlmpubs.nlm.nih.gov/projects/mesh/MESH_FILES/xmlmesh/

Files available:
- desc{year}.xml     - Descriptors (~314 MB for 2025)
- qual{year}.xml     - Qualifiers (~300 KB)
- supp{year}.xml     - Supplementary Concepts (~240 MB)
- pa{year}.xml       - Pharmacological Actions
```

**Important URL Notes:**
- Files are downloaded as plain XML (not gzipped)
- The server auto-decompresses `.gz` files via `Content-Encoding: x-gzip`
- This caused issues when requesting `.gz` URLs as the received content was uncompressed
- The correct approach is to download `.xml` files directly

**Historical URL Issue (Fixed December 2025):**
```python
# WRONG - Returns uncompressed XML despite .gz extension
url = f"https://nlmpubs.nlm.nih.gov/projects/mesh/{year}/xmlmesh/desc{year}.xml.gz"

# CORRECT - Downloads plain XML
url = f"https://nlmpubs.nlm.nih.gov/projects/mesh/MESH_FILES/xmlmesh/desc{year}.xml"
```

## Data Types

### MeSHDescriptor
```python
@dataclass
class MeSHDescriptor:
    descriptor_ui: str           # e.g., "D009203"
    descriptor_name: str         # e.g., "Myocardial Infarction"
    scope_note: Optional[str]    # Definition text
    annotation: Optional[str]    # Indexing guidance
    history_note: Optional[str]
    public_mesh_note: Optional[str]
    nlm_classification: Optional[str]
    date_created: Optional[str]
    date_revised: Optional[str]
    date_established: Optional[str]
    concepts: List[Dict[str, Any]]      # Concepts with terms
    tree_numbers: List[str]             # Hierarchical codes
    allowable_qualifiers: List[str]     # Valid qualifier UIs
```

### MeSHQualifier
```python
@dataclass
class MeSHQualifier:
    qualifier_ui: str           # e.g., "Q000175"
    qualifier_name: str         # e.g., "diagnosis"
    abbreviation: str           # e.g., "DI"
    scope_note: Optional[str]
    annotation: Optional[str]
```

### MeSHSupplementary
```python
@dataclass
class MeSHSupplementary:
    supplemental_ui: str            # e.g., "C123456"
    supplemental_name: str          # Chemical/drug name
    note: Optional[str]
    cas_registry_number: Optional[str]
    frequency: Optional[int]        # Usage frequency
    heading_mapped_to: List[str]    # Related descriptor UIs
    indexing_information: Optional[str]
```

### ImportStats
```python
@dataclass
class ImportStats:
    mesh_year: int
    import_type: str        # "full" or "supplementary"
    descriptors: int
    concepts: int
    terms: int
    tree_numbers: int
    qualifiers: int
    supplementary_concepts: int
    started_at: datetime
    completed_at: Optional[datetime]
    duration_seconds: Optional[float]
    status: str             # "in_progress", "completed", "failed"
    error_message: Optional[str]
```

## Database Schema

The MeSH data is stored in the `mesh` PostgreSQL schema:

```sql
-- Main descriptors (MeSH headings)
CREATE TABLE mesh.descriptors (
    id SERIAL PRIMARY KEY,
    descriptor_ui VARCHAR(20) UNIQUE NOT NULL,
    descriptor_name VARCHAR(500) NOT NULL,
    scope_note TEXT,
    annotation TEXT,
    history_note TEXT,
    public_mesh_note TEXT,
    nlm_classification VARCHAR(50),
    date_created DATE,
    date_revised DATE,
    date_established DATE,
    mesh_year INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Concepts within descriptors
CREATE TABLE mesh.concepts (
    id SERIAL PRIMARY KEY,
    concept_ui VARCHAR(20) UNIQUE NOT NULL,
    concept_name VARCHAR(500) NOT NULL,
    descriptor_id INTEGER REFERENCES mesh.descriptors(id),
    is_preferred BOOLEAN DEFAULT FALSE,
    scope_note TEXT,
    cas_registry_number VARCHAR(100)
);

-- Term variants (entry terms, synonyms)
CREATE TABLE mesh.terms (
    id SERIAL PRIMARY KEY,
    term_ui VARCHAR(20),
    term_text VARCHAR(500) NOT NULL,
    concept_id INTEGER REFERENCES mesh.concepts(id),
    is_preferred BOOLEAN DEFAULT FALSE,
    is_permuted BOOLEAN DEFAULT FALSE,
    lexical_tag VARCHAR(50),
    entry_combination VARCHAR(200),
    sort_version VARCHAR(200),
    UNIQUE(term_ui, concept_id)
);

-- Hierarchical tree numbers
CREATE TABLE mesh.tree_numbers (
    id SERIAL PRIMARY KEY,
    descriptor_id INTEGER REFERENCES mesh.descriptors(id),
    tree_number VARCHAR(100) NOT NULL,
    tree_level INTEGER,
    UNIQUE(descriptor_id, tree_number)
);

-- Subheading qualifiers
CREATE TABLE mesh.qualifiers (
    id SERIAL PRIMARY KEY,
    qualifier_ui VARCHAR(20) UNIQUE NOT NULL,
    qualifier_name VARCHAR(200) NOT NULL,
    abbreviation VARCHAR(10),
    scope_note TEXT,
    annotation TEXT,
    mesh_year INTEGER
);

-- Supplementary concept records (chemicals, drugs, etc.)
CREATE TABLE mesh.supplementary_concepts (
    id SERIAL PRIMARY KEY,
    supplemental_ui VARCHAR(20) UNIQUE NOT NULL,
    supplemental_name VARCHAR(500) NOT NULL,
    note TEXT,
    cas_registry_number VARCHAR(100),
    frequency INTEGER,
    heading_mapped_to TEXT[],
    indexing_information TEXT,
    mesh_year INTEGER
);

-- Import history tracking
CREATE TABLE mesh.import_history (
    id SERIAL PRIMARY KEY,
    mesh_year INTEGER,
    import_type VARCHAR(50),
    descriptors_imported INTEGER,
    concepts_imported INTEGER,
    terms_imported INTEGER,
    tree_numbers_imported INTEGER,
    qualifiers_imported INTEGER,
    scrs_imported INTEGER,
    import_status VARCHAR(20),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT
);
```

## Key Functions

### PostgreSQL Functions

```sql
-- Look up a term (returns descriptor info)
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

## Import Process

### Download Phase

1. Build download URLs for descriptor, qualifier, and supplementary files
2. Download using `requests` with streaming and progress tracking
3. Store in `~/.bmlibrarian/downloads/mesh/`

```python
def _download_file(self, url: str, output_path: Path, progress_callback) -> bool:
    response = requests.get(
        url,
        stream=True,
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers={"User-Agent": "BMLibrarian/1.0"},
    )
    # ... streaming download with progress
```

### Parse Phase

Uses `xml.etree.ElementTree.iterparse` for memory-efficient streaming:

```python
def _iter_xml_records(self, file_path: Path, record_tag: str) -> Iterator[ET.Element]:
    with self._open_xml_file(file_path) as f:
        context = ET.iterparse(f, events=("end",))
        for event, elem in context:
            if elem.tag == record_tag:
                yield elem
                elem.clear()  # Free memory
```

### Store Phase

Uses UPSERT (INSERT ... ON CONFLICT DO UPDATE) for idempotent imports:

```python
cur.execute("""
    INSERT INTO mesh.descriptors (descriptor_ui, descriptor_name, ...)
    VALUES (%s, %s, ...)
    ON CONFLICT (descriptor_ui) DO UPDATE SET
        descriptor_name = EXCLUDED.descriptor_name,
        ...
    RETURNING id
""", (descriptor.descriptor_ui, descriptor.descriptor_name, ...))
```

## Integration with Lookup Services

### MeSHService (mesh/lookup.py)

High-level service for MeSH lookups:

```python
from bmlibrarian.mesh import MeSHService

service = MeSHService()
result = service.lookup("heart attack")
# Returns MeSHResult with descriptor info, source, entry terms
```

### MeSHLookup (pubmed_search/mesh_lookup.py)

Integrates with the PubMed search system:

```python
from bmlibrarian.pubmed_search import MeSHLookup

lookup = MeSHLookup()
# Checks: 1. Local PostgreSQL, 2. SQLite cache, 3. NLM API
result = lookup.validate_term("Cardiovascular Diseases")
```

## Constants

Defined in `pubmed_search/constants.py`:

```python
# MeSH cache settings
MESH_CACHE_FILENAME = "mesh_cache.db"
MESH_CACHE_TTL_DAYS = 30

# MeSH descriptor identifier prefix (e.g., D001234)
MESH_DESCRIPTOR_PREFIX = "D"
```

## Error Handling

### Download Errors

- Retries with exponential backoff (3 attempts)
- Validates response status codes
- Checks Content-Type header

### Parse Errors

- Uses iterparse for memory efficiency
- Clears elements after processing
- Handles missing optional fields gracefully

### Database Errors

- Uses transactions for consistency
- UPSERT prevents duplicate key errors
- Import history tracks failures

## Testing

```bash
# Run MeSH importer tests
uv run python -m pytest tests/importers/test_mesh_importer.py

# Run MeSH lookup tests
uv run python -m pytest tests/mesh/test_lookup.py

# Run integration tests
uv run python -m pytest tests/pubmed_search/test_mesh_lookup.py
```

## CLI Commands

```bash
# Import MeSH vocabulary
uv run python mesh_import_cli.py import --year 2025

# Check import status
uv run python mesh_import_cli.py status

# Look up a term
uv run python mesh_import_cli.py lookup "heart attack"

# Search by partial match
uv run python mesh_import_cli.py search "cardio"
```

## Performance Considerations

- **Memory**: Uses iterparse streaming to handle ~300MB XML files
- **Database**: Batch commits every 100 descriptors
- **Indexes**: Created on descriptor_ui, term_text for fast lookups
- **Cache**: SQLite cache for API results (30-day TTL)

## See Also

- [MeSH Import Guide](../users/mesh_import_guide.md) - User documentation
- [PubMed API Search System](pubmed_api_search_system.md) - Related search system
- [Database Schema](../developers/database_schema.md) - Full schema reference
