# PubMed API Search Guide

## Overview

The PubMed API Search module enables BMLibrarian users who don't have a local PubMed mirror to search PubMed directly via the NCBI E-utilities API. It converts natural language research questions into optimized PubMed queries using MeSH terms, field tags, and boolean operators.

## When to Use This Module

Use the PubMed API Search module when:

- You don't have disk space (~500GB+) for a full PubMed mirror
- You need quick access to recent publications not in your local database
- You're conducting a systematic review on a specific topic
- You want to supplement your local database with targeted searches

## Quick Start

### Basic Usage

```python
from bmlibrarian.pubmed_search import SearchAndImportOrchestrator

# Create orchestrator (uses default settings)
orchestrator = SearchAndImportOrchestrator()

# Search and import articles
session = orchestrator.search_and_import(
    question="What are the cardiovascular benefits of exercise in elderly patients?",
    max_results=200,  # Default limit
)

# Check results
if session.import_result:
    print(f"Found: {session.import_result.total_found} articles")
    print(f"Imported: {session.import_result.articles_imported} new articles")
    print(f"Skipped: {session.import_result.articles_skipped} existing articles")
```

### Preview Query Before Searching

```python
from bmlibrarian.pubmed_search import QueryConverter

converter = QueryConverter()

# Just get the query without executing
result = converter.convert("cardiovascular benefits of exercise in elderly")

print("Generated PubMed Query:")
print(result.primary_query.query_string)

# Review MeSH terms identified
print("\nMeSH terms found:")
for term in result.mesh_terms_validated:
    print(f"  - {term}")

# Check for warnings
if result.warnings:
    print("\nWarnings:")
    for warning in result.warnings:
        print(f"  - {warning}")
```

## Step-by-Step Workflow

### 1. Convert Question to PubMed Query

```python
from bmlibrarian.pubmed_search import QueryConverter, PublicationType, DateRange
from datetime import date

converter = QueryConverter()

# Basic conversion
result = converter.convert(
    question="What treatments are effective for type 2 diabetes?"
)

# With filters
result = converter.convert(
    question="What treatments are effective for type 2 diabetes?",
    publication_types=[PublicationType.RCT, PublicationType.META_ANALYSIS],
    date_range=DateRange(start_date=date(2020, 1, 1)),
    humans_only=True,
    has_abstract=True,
)

# Access the query
query = result.primary_query
print(f"Query: {query.query_string}")
print(f"Confidence: {query.confidence_score:.0%}")
```

### 2. Search PubMed

```python
from bmlibrarian.pubmed_search import PubMedSearchClient

client = PubMedSearchClient(
    email="your.email@example.com",  # Recommended
    api_key="your_ncbi_api_key",     # Optional, faster rate limit
)

# Search with the converted query
search_result = client.search(
    query=query,
    max_results=200,
)

print(f"Total matches in PubMed: {search_result.total_count}")
print(f"Retrieved: {search_result.retrieved_count} PMIDs")
```

### 3. Fetch Article Metadata

```python
# Fetch full metadata for found articles
articles = client.fetch_articles(
    pmids=search_result.pmids,
    batch_size=200,
)

# Preview first article
if articles:
    article = articles[0]
    print(f"Title: {article.title}")
    print(f"Authors: {', '.join(article.authors[:3])}...")
    print(f"Journal: {article.publication}")
    print(f"MeSH Terms: {', '.join(article.mesh_terms[:5])}...")
```

### 4. Import to Local Database

```python
from bmlibrarian.pubmed_search import ResultProcessor

processor = ResultProcessor()

# Import articles (skips existing)
import_result = processor.import_articles(articles)

print(f"Imported: {import_result.articles_imported} new articles")
print(f"Skipped: {import_result.articles_skipped} existing articles")

# Get database IDs of imported documents
for doc_id in import_result.imported_document_ids[:5]:
    print(f"  Document ID: {doc_id}")
```

## Configuration

Add to `~/.bmlibrarian/config.json`:

```json
{
  "pubmed_api": {
    "email": "your.email@example.com",
    "api_key": null,
    "default_max_results": 200,
    "validate_mesh": true,
    "expand_keywords": true
  }
}
```

### Environment Variables

You can also use environment variables:

```bash
export NCBI_EMAIL="your.email@example.com"
export NCBI_API_KEY="your_api_key"
```

## Publication Type Filters

Available publication type filters:

| Filter | Description |
|--------|-------------|
| `CLINICAL_TRIAL` | Clinical trials |
| `RCT` | Randomized controlled trials |
| `META_ANALYSIS` | Meta-analyses |
| `SYSTEMATIC_REVIEW` | Systematic reviews |
| `REVIEW` | Review articles |
| `CASE_REPORT` | Case reports |
| `GUIDELINE` | Clinical guidelines |
| `OBSERVATIONAL` | Observational studies |

Example:

```python
from bmlibrarian.pubmed_search import PublicationType

result = converter.convert(
    question="effectiveness of statins",
    publication_types=[
        PublicationType.RCT,
        PublicationType.META_ANALYSIS,
        PublicationType.SYSTEMATIC_REVIEW,
    ],
)
```

## MeSH Term Handling

The module automatically:

1. **Extracts MeSH terms** from your question using LLM
2. **Validates terms** against the official NCBI MeSH vocabulary
3. **Expands terms** with synonyms and narrower terms (optional)
4. **Caches lookups** to improve performance

### Check MeSH Validation

```python
from bmlibrarian.pubmed_search import MeSHLookup

lookup = MeSHLookup()

# Validate a single term
result = lookup.validate_term("Cardiovascular Diseases")
if result.is_valid:
    print(f"Valid: {result.descriptor_name}")
    print(f"UI: {result.descriptor_ui}")
else:
    print("Invalid term")

# Get cache statistics
stats = lookup.get_cache_stats()
print(f"Cached terms: {stats['cached_terms']}")
```

## Rate Limiting

The module respects NCBI's rate limits:

| API Key | Rate Limit |
|---------|------------|
| No key | 3 requests/second |
| With key | 10 requests/second |

Get an API key at: https://ncbiinsights.ncbi.nlm.nih.gov/2017/11/02/new-api-keys-for-the-e-utilities/

## Progress Callbacks

Track progress during long operations:

```python
def my_progress_callback(step: str, message: str) -> None:
    print(f"[{step}] {message}")

session = orchestrator.search_and_import(
    question="cardiovascular exercise",
    max_results=500,
    progress_callback=my_progress_callback,
)
```

Output:
```
[convert] Converting question to PubMed query...
[extract] Extracting biomedical concepts...
[validate] Validating MeSH terms...
[build] Building PubMed query string...
[search] Searching PubMed...
[found] Found 1234 articles, retrieving 500...
[fetch] Fetching batch 1/3...
[import] Importing articles to database...
[complete] Imported 423 new articles
```

## Search History

The module tracks all API searches for reproducibility:

```sql
-- View recent searches
SELECT * FROM v_pubmed_api_search_history LIMIT 10;

-- Get search statistics
SELECT * FROM get_pubmed_api_search_stats();
```

## Best Practices

1. **Provide your email**: NCBI recommends identifying yourself
2. **Use an API key** for faster searches (10x rate limit)
3. **Review generated queries** before large searches
4. **Start with lower limits** (100-200) to test query quality
5. **Use publication type filters** for systematic reviews
6. **Enable MeSH validation** for better query accuracy

## Troubleshooting

### No Results Found

- Check if MeSH terms were validated (see warnings)
- Try broader keywords
- Remove restrictive filters
- Check date range if specified

### Invalid MeSH Terms

- Use official MeSH vocabulary
- Check MeSH Browser: https://meshb.nlm.nih.gov/
- The module suggests alternatives when terms are invalid

### API Errors

- Check your internet connection
- Verify NCBI API is accessible
- Check rate limiting (wait if hitting limits)
- Try with API key for higher rate limit

## GUI: PubMed Search Lab

For users who prefer a graphical interface, BMLibrarian provides the PubMed Search Lab:

```bash
uv run python scripts/pubmed_search_lab.py
```

The PubMed Search Lab provides:

- **Question Input**: Enter your research question in natural language
- **Search Options**: Configure max results and whether to check for existing documents
- **Query Preview**: See the generated PubMed query before results are displayed
- **Results Display**: View retrieved articles as expandable cards showing:
  - Title, authors, journal, and year
  - PMID, DOI, and PMC identifiers
  - Abstract (expandable)
  - MeSH terms and keywords
- **Existing Document Feedback**: Shows how many results already exist in your local database
- **No Database Storage**: Results are displayed for review only, not automatically imported

This is useful for:
- Previewing search results before importing
- Testing query quality
- Quick literature exploration without database modifications

## See Also

- [PubMed API Search Architecture](../developers/pubmed_api_search_system.md)
- [Multi-Model Query Guide](multi_model_query_guide.md)
- [Full-Text Discovery Guide](full_text_discovery_guide.md)
