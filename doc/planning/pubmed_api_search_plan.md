# PubMed API Search Module - Implementation Plan

## Overview

This module enables users without local PubMed/medRxiv mirrors to search PubMed directly via their E-utilities API. It converts natural language research questions into optimized PubMed queries using MeSH terms, field tags, and boolean operators to approximate semantic search quality.

## Use Case

**Target Users**: Researchers conducting systematic reviews who lack disk space (~500GB+) for full PubMed mirroring.

**Workflow Integration**:
1. User enters research question in bmlibrarian_cli or systematic_review_gui
2. System detects "API search mode" (config flag or empty local database)
3. Question is converted to optimized PubMed query
4. PubMed API is queried, results are retrieved and stored locally
5. Standard workflow continues (scoring, citations, reports)
6. Optional: Full-text PDFs are discovered and downloaded

## Architecture

### New Module: `src/bmlibrarian/pubmed_search/`

```
src/bmlibrarian/pubmed_search/
├── __init__.py              # Module exports
├── query_converter.py       # NL → PubMed query conversion (LLM-based)
├── mesh_lookup.py           # MeSH term resolution and expansion
├── search_client.py         # PubMed E-utilities API client
├── result_processor.py      # Parse results, store in database
└── data_types.py            # Type-safe dataclasses
```

### Integration Points

1. **QueryAgent**: Add `convert_to_pubmed_query()` method alongside existing `convert_question()`
2. **Workflow System**: New workflow step `SEARCH_PUBMED_API` as alternative to `SEARCH_DOCUMENTS`
3. **Configuration**: New `pubmed_api` config section
4. **CLI**: New `pubmed_search_cli.py` and integration into `bmlibrarian_cli.py`

## Component Design

### 1. Query Converter (`query_converter.py`)

Converts natural language questions to optimized PubMed queries using LLM.

**Key Features**:
- Extract biomedical concepts and map to MeSH terms
- Generate field-specific queries (title, abstract, MeSH, author)
- Build boolean query structure (AND, OR, NOT)
- Apply date filters and publication type filters
- Support PICO-based query construction

**Input**: Natural language research question
**Output**: `PubMedQuery` dataclass with:
- `query_string`: Final PubMed query
- `mesh_terms`: List of MeSH terms used
- `keywords`: Non-MeSH keywords
- `date_range`: Optional date filter
- `publication_types`: Optional filter (RCT, meta-analysis, etc.)

**Example Transformation**:
```
Input:  "What are the cardiovascular benefits of exercise in elderly patients?"

Output: ((("Exercise"[MeSH] OR "Physical Activity"[MeSH] OR exercise[tiab] OR
          "physical activity"[tiab]) AND ("Cardiovascular Diseases"[MeSH] OR
          "Heart"[MeSH] OR cardiovascular[tiab] OR cardiac[tiab]) AND
          ("Aged"[MeSH] OR elderly[tiab] OR "older adults"[tiab])))
```

**LLM Prompt Strategy**:
```python
QUERY_CONVERSION_PROMPT = """
You are a biomedical information specialist expert at PubMed searching.
Convert the following research question into an optimized PubMed query.

Research Question: {question}

Instructions:
1. Identify the key biomedical concepts (PICO if applicable)
2. For each concept, provide:
   - Primary MeSH term(s) - use exact MeSH vocabulary
   - Alternative MeSH terms (narrower/broader)
   - Free-text keywords for title/abstract [tiab]
3. Structure the query with:
   - OR between synonyms within a concept
   - AND between different concepts
   - Parentheses for proper grouping
4. Consider adding filters if appropriate:
   - Publication types: Clinical Trial, Meta-Analysis, Systematic Review
   - Date range based on topic currency
   - Human studies filter if relevant

Output JSON format:
{
  "concepts": [
    {
      "name": "concept name",
      "mesh_terms": ["MeSH Term 1", "MeSH Term 2"],
      "keywords": ["keyword1", "keyword2"],
      "field_tags": ["tiab", "tw"]  // tiab=title/abstract, tw=text word
    }
  ],
  "filters": {
    "publication_types": [],
    "date_from": null,
    "date_to": null,
    "humans_only": false
  },
  "final_query": "complete PubMed query string"
}
"""
```

### 2. MeSH Lookup (`mesh_lookup.py`)

Validates and expands MeSH terms using NCBI's MeSH database.

**Features**:
- Validate LLM-suggested MeSH terms against official vocabulary
- Expand terms with narrower terms (explosion) when appropriate
- Find entry terms (synonyms) for better recall
- Cache MeSH lookups to reduce API calls

**API Endpoints**:
- MeSH Browser API: `https://meshb.nlm.nih.gov/api/`
- E-utilities esearch with `db=mesh`

**Caching Strategy**:
- SQLite cache for MeSH term → tree number mappings
- TTL: 30 days (MeSH updated annually)
- Location: `~/.bmlibrarian/cache/mesh_cache.db`

### 3. Search Client (`search_client.py`)

Wraps PubMed E-utilities API with proper rate limiting and error handling.

**Reuses from `pubmed_importer.py`**:
- `_make_request()` with retry logic
- Rate limiting (3 req/sec without key, 10 with key)
- XML parsing utilities
- Error handling patterns

**New Capabilities**:
- History server support for large result sets
- Relevance sorting option
- Count-only queries for result estimation
- Batch retrieval with progress callbacks

**API Workflow**:
```
1. esearch.fcgi → Get PMIDs matching query (uses history server for >10k results)
2. efetch.fcgi → Retrieve full article metadata in batches
3. elink.fcgi → Optional: Get related articles for query expansion
```

**Result Limits**:
- Default: 500 articles (configurable)
- Maximum recommended: 10,000 (use history server)
- For systematic reviews: Support unlimited with pagination

### 4. Result Processor (`result_processor.py`)

Parses PubMed XML and stores in local database.

**Reuses from `pubmed_importer.py`**:
- `_parse_article()` for XML → dict conversion
- `_store_articles()` for database insertion
- Markdown abstract formatting
- MeSH term extraction

**New Features**:
- Duplicate detection against existing local documents
- Update existing records if newer data available
- Track search provenance (which query found which articles)
- Batch processing with progress callbacks

**Database Integration**:
- Uses existing `documents` table schema
- Adds new tracking table for API search history

### 5. Data Types (`data_types.py`)

Type-safe dataclasses for the module.

```python
from dataclasses import dataclass, field
from typing import Optional, List
from datetime import date
from enum import Enum

class PublicationType(Enum):
    """PubMed publication type filters."""
    CLINICAL_TRIAL = "Clinical Trial"
    RCT = "Randomized Controlled Trial"
    META_ANALYSIS = "Meta-Analysis"
    SYSTEMATIC_REVIEW = "Systematic Review"
    REVIEW = "Review"
    CASE_REPORT = "Case Reports"

@dataclass
class QueryConcept:
    """A single concept in the research question."""
    name: str
    mesh_terms: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    mesh_explosion: bool = True  # Include narrower terms

@dataclass
class PubMedQuery:
    """Structured PubMed query ready for API submission."""
    original_question: str
    query_string: str
    concepts: List[QueryConcept] = field(default_factory=list)
    publication_types: List[PublicationType] = field(default_factory=list)
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    humans_only: bool = False

    def to_url_params(self) -> dict:
        """Convert to E-utilities URL parameters."""
        params = {"term": self.query_string, "db": "pubmed"}
        if self.date_from:
            params["mindate"] = self.date_from.strftime("%Y/%m/%d")
        if self.date_to:
            params["maxdate"] = self.date_to.strftime("%Y/%m/%d")
        return params

@dataclass
class SearchResult:
    """Result from a PubMed API search."""
    query: PubMedQuery
    total_count: int
    retrieved_count: int
    pmids: List[str]
    search_time_seconds: float

@dataclass
class APISearchSession:
    """Tracks a complete API search session for provenance."""
    session_id: str
    research_question: str
    queries_executed: List[PubMedQuery]
    total_articles_found: int
    articles_imported: int
    articles_skipped_duplicate: int
    full_texts_downloaded: int
    created_at: datetime
```

## Configuration

New section in `~/.bmlibrarian/config.json`:

```json
{
  "pubmed_api": {
    "enabled": true,
    "email": "user@example.com",
    "api_key": null,
    "default_max_results": 500,
    "max_results_limit": 10000,
    "auto_download_fulltext": false,
    "mesh_validation": true,
    "mesh_explosion": true,
    "default_filters": {
      "humans_only": false,
      "publication_types": [],
      "date_range_years": null
    },
    "query_model": "gpt-oss:20b",
    "cache_ttl_days": 30
  }
}
```

## Database Schema Addition

New table for tracking API search sessions:

```sql
-- Migration: Add PubMed API search tracking
CREATE TABLE IF NOT EXISTS pubmed_api_searches (
    id SERIAL PRIMARY KEY,
    session_id UUID NOT NULL DEFAULT gen_random_uuid(),
    research_question TEXT NOT NULL,
    pubmed_query TEXT NOT NULL,
    query_concepts JSONB,
    total_results INTEGER,
    results_retrieved INTEGER,
    results_imported INTEGER,
    results_duplicate INTEGER,
    search_timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    user_id INTEGER REFERENCES users(id),
    UNIQUE(session_id)
);

-- Track which documents came from which search
CREATE TABLE IF NOT EXISTS pubmed_api_search_documents (
    search_id INTEGER REFERENCES pubmed_api_searches(id),
    document_id INTEGER REFERENCES documents(id),
    relevance_rank INTEGER,
    PRIMARY KEY (search_id, document_id)
);

CREATE INDEX idx_pubmed_api_searches_timestamp
    ON pubmed_api_searches(search_timestamp);
CREATE INDEX idx_pubmed_api_search_docs_search
    ON pubmed_api_search_documents(search_id);
```

## CLI Interface

### New CLI: `pubmed_search_cli.py`

```bash
# Basic search with natural language question
uv run python pubmed_search_cli.py search "cardiovascular benefits of exercise in elderly"

# With options
uv run python pubmed_search_cli.py search "COVID-19 vaccine efficacy" \
    --max-results 1000 \
    --publication-types "Randomized Controlled Trial" "Meta-Analysis" \
    --date-from 2020-01-01 \
    --download-fulltext

# Show the generated PubMed query without executing
uv run python pubmed_search_cli.py preview "treatment options for type 2 diabetes"

# Search with manual PubMed query (expert mode)
uv run python pubmed_search_cli.py query '"Diabetes Mellitus, Type 2"[MeSH] AND treatment[tiab]'

# View search history
uv run python pubmed_search_cli.py history --limit 10

# Re-run a previous search with updated results
uv run python pubmed_search_cli.py refresh --session-id abc123
```

### Integration with `bmlibrarian_cli.py`

Add option to use API search instead of local database:

```bash
# Use API search mode (automatic if local DB is empty/small)
uv run python bmlibrarian_cli.py --api-search

# Force local database search
uv run python bmlibrarian_cli.py --local-only

# Hybrid: search local first, supplement with API
uv run python bmlibrarian_cli.py --hybrid-search
```

## Workflow Integration

### New Workflow Step

Add to `workflow_steps.py`:

```python
class WorkflowStep(Enum):
    # ... existing steps ...
    SEARCH_PUBMED_API = "search_pubmed_api"  # Alternative to SEARCH_DOCUMENTS

# Step configuration
STEP_CONFIG = {
    WorkflowStep.SEARCH_PUBMED_API: StepConfig(
        name="Search PubMed API",
        description="Search PubMed directly via API for relevant articles",
        repeatable=True,
        can_branch_to=[
            WorkflowStep.REVIEW_SEARCH_RESULTS,
            WorkflowStep.GENERATE_AND_EDIT_QUERY  # If no results
        ]
    ),
}
```

### Automatic Mode Detection

```python
def determine_search_mode(config: BMLibrarianConfig, db_manager: DatabaseManager) -> SearchMode:
    """Determine whether to use local DB or API search."""

    # Check configuration preference
    if config.get("search", {}).get("force_api_search"):
        return SearchMode.API_ONLY
    if config.get("search", {}).get("force_local_search"):
        return SearchMode.LOCAL_ONLY

    # Check local database size
    doc_count = db_manager.get_document_count(source='pubmed')
    if doc_count < 1000:  # Threshold for "minimal local data"
        return SearchMode.API_ONLY
    elif doc_count < 100000:  # Threshold for "limited local data"
        return SearchMode.HYBRID
    else:
        return SearchMode.LOCAL_ONLY
```

## Full-Text Discovery Integration

Integrate with existing discovery module for optional PDF download:

```python
async def search_and_download(
    question: str,
    max_results: int = 500,
    download_fulltext: bool = False,
    progress_callback: Optional[Callable] = None
) -> APISearchSession:
    """Complete workflow: search → import → optionally download PDFs."""

    # 1. Convert question to PubMed query
    converter = QueryConverter(model=config.get_model("pubmed_api", "query_model"))
    pubmed_query = await converter.convert(question)

    # 2. Execute search
    client = PubMedSearchClient(email=config.email, api_key=config.api_key)
    search_result = await client.search(pubmed_query, max_results=max_results)

    # 3. Fetch and store articles
    processor = ResultProcessor(db_manager)
    import_stats = await processor.import_results(search_result, progress_callback)

    # 4. Optionally download full-texts
    if download_fulltext:
        from bmlibrarian.discovery import download_pdf_for_document

        for doc in import_stats.imported_documents:
            if progress_callback:
                progress_callback("download", f"Downloading PDF for {doc['pmid']}")

            result = await download_pdf_for_document(
                document=doc,
                output_dir=config.pdf_base_dir,
                use_browser_fallback=True
            )

    return APISearchSession(...)
```

## Implementation Phases

### Phase 1: Core Query Conversion (Week 1)
- [ ] Create module structure
- [ ] Implement `QueryConverter` with LLM-based conversion
- [ ] Add `PubMedQuery` and related dataclasses
- [ ] Write unit tests for query conversion
- [ ] Create basic CLI for testing

### Phase 2: PubMed API Integration (Week 2)
- [ ] Implement `PubMedSearchClient` (reuse from pubmed_importer.py)
- [ ] Add history server support for large result sets
- [ ] Implement `ResultProcessor` for database storage
- [ ] Add database migration for search tracking tables
- [ ] Write integration tests

### Phase 3: MeSH Validation & Enhancement (Week 3)
- [ ] Implement `MeSHLookup` with NCBI API
- [ ] Add MeSH caching layer
- [ ] Integrate MeSH validation into query converter
- [ ] Add MeSH explosion (narrower terms) support
- [ ] Test with real research questions

### Phase 4: Workflow & CLI Integration (Week 4)
- [ ] Create `pubmed_search_cli.py` with full feature set
- [ ] Integrate into `bmlibrarian_cli.py` workflow
- [ ] Add `SEARCH_PUBMED_API` workflow step
- [ ] Implement automatic search mode detection
- [ ] Update configuration system

### Phase 5: Full-Text Integration & Polish (Week 5)
- [ ] Integrate with discovery module for PDF downloads
- [ ] Add search session tracking and history
- [ ] Write user documentation
- [ ] Write developer documentation
- [ ] Performance optimization and edge case handling

## Testing Strategy

### Unit Tests
- Query conversion with various question types
- MeSH term validation and expansion
- XML parsing and database storage
- Configuration handling

### Integration Tests
- End-to-end search workflow
- Database insertion and duplicate detection
- Full-text discovery integration
- CLI command execution

### Validation Tests
- Compare API search results vs local database search
- Measure recall/precision on known research questions
- Verify MeSH term accuracy against manual queries

## Success Metrics

1. **Query Quality**: Generated PubMed queries should retrieve 80%+ of relevant articles compared to expert-crafted queries
2. **Performance**: Search and import 500 articles in < 60 seconds
3. **Reliability**: Handle API rate limiting, network errors, and malformed responses gracefully
4. **Integration**: Seamless workflow with existing agents (scoring, citation, reporting)

## Dependencies

**Existing (no new packages)**:
- `ollama` - LLM for query conversion
- `requests` - HTTP client
- `psycopg` - Database access
- `xml.etree.ElementTree` - XML parsing

**Optional**:
- `aiohttp` - Async HTTP for parallel downloads (if needed)

## Open Questions

1. **Query refinement loop**: Should users be able to iteratively refine the generated PubMed query before execution?
2. **Result ranking**: Use PubMed's relevance ranking or re-rank locally with scoring agent?
3. **Hybrid search strategy**: When combining local + API results, how to deduplicate and merge?
4. **MeSH version handling**: How to handle MeSH vocabulary updates (annual)?

## References

- [NCBI E-utilities Documentation](https://www.ncbi.nlm.nih.gov/books/NBK25500/)
- [PubMed Search Field Tags](https://pubmed.ncbi.nlm.nih.gov/help/#search-tags)
- [MeSH Browser](https://meshb.nlm.nih.gov/)
- [PubMed Query Syntax](https://pubmed.ncbi.nlm.nih.gov/help/#how-do-i-search-pubmed)
