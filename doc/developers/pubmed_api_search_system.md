# PubMed API Search System - Developer Documentation

## Architecture Overview

The PubMed API Search module provides a complete workflow for searching PubMed directly via the NCBI E-utilities API, converting natural language questions to optimized queries, and storing results in the local database.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    SearchAndImportOrchestrator                          │
│                    (Coordinates complete workflow)                       │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        ▼                           ▼                           ▼
┌───────────────────┐    ┌───────────────────┐    ┌───────────────────┐
│  QueryConverter   │    │ PubMedSearchClient │    │  ResultProcessor  │
│  (NL → PubMed)    │    │  (E-utilities API) │    │  (DB Storage)     │
└───────────────────┘    └───────────────────┘    └───────────────────┘
        │                                                   │
        ▼                                                   ▼
┌───────────────────┐                           ┌───────────────────┐
│   MeSHLookup      │                           │   DatabaseManager │
│   (Validation)    │                           │   (bmlibrarian)   │
└───────────────────┘                           └───────────────────┘
        │
        ▼
┌───────────────────┐
│  SQLite Cache     │
│  (MeSH terms)     │
└───────────────────┘
```

## Module Structure

```
src/bmlibrarian/pubmed_search/
├── __init__.py           # Public API exports
├── constants.py          # Module constants (no magic numbers)
├── data_types.py         # Type-safe dataclasses
├── mesh_lookup.py        # MeSH validation with SQLite caching
├── query_converter.py    # LLM-based NL to PubMed conversion
├── search_client.py      # E-utilities API wrapper
└── result_processor.py   # Database storage and orchestration
```

## Component Details

### 1. Data Types (`data_types.py`)

Type-safe dataclasses for all module data:

| Class | Purpose |
|-------|---------|
| `PublicationType` | Enum of PubMed publication type filters |
| `SearchStatus` | Enum of search session states |
| `MeSHTerm` | MeSH descriptor with metadata |
| `QueryConcept` | Semantic concept from research question |
| `DateRange` | Date filter for searches |
| `PubMedQuery` | Complete query with filters |
| `SearchResult` | Search response with PMIDs |
| `ArticleMetadata` | Parsed article data |
| `ImportResult` | Database import statistics |
| `SearchSession` | Complete workflow tracking |
| `QueryConversionResult` | LLM conversion output |

### 2. MeSH Lookup (`mesh_lookup.py`)

Validates MeSH terms against NCBI's vocabulary with SQLite caching.

**Key Features:**
- SQLite-based local cache (30-day TTL)
- Validates terms via NCBI E-utilities
- Finds official descriptor names for entry terms
- Expands terms with synonyms

**Cache Schema:**
```sql
mesh_terms (
    descriptor_ui TEXT PRIMARY KEY,
    descriptor_name TEXT,
    tree_numbers TEXT,      -- JSON array
    entry_terms TEXT,       -- JSON array
    scope_note TEXT,
    cached_at TIMESTAMP
)

mesh_name_lookup (
    search_name TEXT PRIMARY KEY,
    descriptor_ui TEXT,
    is_valid INTEGER,
    cached_at TIMESTAMP
)
```

### 3. Query Converter (`query_converter.py`)

Converts natural language to PubMed queries using LLM.

**Workflow:**
1. Send question to LLM with structured prompt
2. Parse JSON response to extract concepts
3. Validate MeSH terms against NCBI
4. Expand keywords with synonyms (optional)
5. Build final PubMed query string

**LLM Prompt Strategy:**
- Request PICO component identification
- Ask for MeSH terms AND free-text keywords
- Include synonyms and alternative spellings
- Suggest appropriate filters

**Fallback Handling:**
- If LLM fails, extract keywords from question
- Create simple title/abstract search
- Mark result as low confidence

### 4. Search Client (`search_client.py`)

Wraps NCBI E-utilities API with proper rate limiting.

**API Endpoints Used:**
- `esearch.fcgi` - Search PubMed, get PMIDs
- `efetch.fcgi` - Fetch article XML

**Rate Limiting:**
- Without API key: 3 requests/second (0.34s delay)
- With API key: 10 requests/second (0.1s delay)

**Large Result Sets:**
- Uses history server for >1000 results
- Batches efetch requests (200 PMIDs per batch)
- Supports generator-based fetching for memory efficiency

### 5. Result Processor (`result_processor.py`)

Stores articles in PostgreSQL with duplicate handling.

**Key Features:**
- Batch duplicate detection via PMIDs
- Prefers existing local records
- Records search provenance
- Links documents to search sessions

**Orchestrator:**
The `SearchAndImportOrchestrator` class coordinates the complete workflow:

```python
orchestrator.search_and_import(question, max_results)
    → QueryConverter.convert()
    → PubMedSearchClient.search()
    → PubMedSearchClient.fetch_articles()
    → ResultProcessor.import_articles()
```

## Database Schema

### Search Tracking Tables

```sql
-- Search sessions
pubmed_api_searches (
    id SERIAL PRIMARY KEY,
    session_id UUID,
    research_question TEXT,
    pubmed_query TEXT,
    query_concepts JSONB,
    total_results INTEGER,
    results_retrieved INTEGER,
    results_imported INTEGER,
    results_duplicate INTEGER,
    search_timestamp TIMESTAMPTZ,
    user_id INTEGER REFERENCES users(id)
)

-- Document-search relationships
pubmed_api_search_documents (
    search_id INTEGER REFERENCES pubmed_api_searches(id),
    document_id INTEGER REFERENCES document(id),
    relevance_rank INTEGER,
    PRIMARY KEY (search_id, document_id)
)
```

### Views

- `v_pubmed_api_search_history` - Recent searches with statistics
- `v_document_search_provenance` - Which searches found each document

### Functions

- `get_pubmed_api_search_stats()` - Aggregate statistics

## Integration Points

### With LLM Abstraction Layer

Uses `bmlibrarian.llm.LLMClient` for all LLM communication:

```python
from bmlibrarian.llm import LLMClient, LLMMessage, get_llm_client

client = get_llm_client()
response = client.chat(
    messages=[LLMMessage(role="user", content=prompt)],
    model="gpt-oss:20b",
    temperature=0.1,
    json_mode=True,
)
```

### With Database Manager

Uses `bmlibrarian.database.get_db_manager()` for all database operations:

```python
from bmlibrarian.database import get_db_manager

db_manager = get_db_manager()
with db_manager.get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT ...")
```

### With Configuration System

Reads settings from `~/.bmlibrarian/config.json`:

```python
from bmlibrarian.config import get_model

model = get_model("pubmed_search", "gpt-oss:20b")
```

## Error Handling

All components follow BMLibrarian's error handling patterns:

1. **Log errors** with appropriate level
2. **Return graceful fallbacks** where possible
3. **Preserve partial results** on failures
4. **Include error details** in result objects

Example:
```python
try:
    articles = client.fetch_articles(pmids)
except Exception as e:
    logger.error(f"Fetch failed: {e}")
    result.errors.append(str(e))
    return result  # Return partial results
```

## Testing

Test files in `tests/pubmed_search/`:

- `test_data_types.py` - Dataclass tests
- `test_mesh_lookup.py` - MeSH validation tests
- `test_query_converter.py` - LLM conversion tests
- `test_search_client.py` - API client tests

Run tests:
```bash
uv run pytest tests/pubmed_search/ -v
```

## Configuration Constants

From `constants.py`:

| Constant | Value | Description |
|----------|-------|-------------|
| `DEFAULT_MAX_RESULTS` | 200 | Default article limit |
| `MAX_RESULTS_LIMIT` | 10000 | Maximum allowed |
| `DEFAULT_BATCH_SIZE` | 200 | PMIDs per efetch |
| `MESH_CACHE_TTL_DAYS` | 30 | Cache expiration |
| `REQUEST_TIMEOUT_SECONDS` | 30 | API timeout |

## Future Enhancements

Potential improvements:

1. **Alternative query generation** - Generate multiple query variants
2. **Related articles** - Use elink to find related articles
3. **Citation network** - Retrieve citing/cited articles
4. **MeSH hierarchy** - Navigate MeSH tree for term expansion
5. **Query optimization** - Learn from search results to refine queries

## See Also

- [PubMed API Search User Guide](../users/pubmed_api_search_guide.md)
- [Implementation Plan](../planning/pubmed_api_search_plan.md)
- [NCBI E-utilities Documentation](https://www.ncbi.nlm.nih.gov/books/NBK25500/)
