# BMLibrarian Database Schema Reference

Compact schema for LLM query assistance. Production database - READ-ONLY access.

## Core Document Tables

### `document` - Main papers/articles table
- `id` (int, PK), `external_id` (text, NOT NULL), `doi` (text)
- `title` (text), `abstract` (text), `full_text` (text)
- `authors` (text[]), `keywords` (text[]), `augmented_keywords` (text[]), `mesh_terms` (text[]), `all_keywords` (text[])
- `publication` (text), `publication_date` (date)
- `url` (text), `pdf_url` (text), `pdf_filename` (text)
- `source_id` (int→sources), `category_id` (int→categories)
- `added_date`, `updated_date`, `withdrawn_date` (timestamps), `withdrawn_reason` (text)
- `abstract_length` (int), `missing_details` (bool, default: false)
- `search_vector` (tsvector, generated from title+abstract with A/B weights)
- **Indexes**: GIN on `search_vector`, btree on `doi`, `external_id`, `publication_date`, `source_id`, `added_date`, `updated_date`
- **Unique**: (source_id, external_id)

### `chunks` - Document text chunks for embeddings
- `id` (int, PK), `document_id` (int→document), `chunk_no` (int, NOT NULL)
- `text` (text), `chunklength` (int), `document_title` (text)
- `chunking_strategy_id` (int→chunking_strategies), `chunktype_id` (int→chunktypes)
- `page_start`, `page_end` (int, default: 0), `metadata` (jsonb)
- `text_search` (tsvector)
- **Indexes**: btree on `document_id`, `chunktype_id`, `(document_id, chunking_strategy_id)`, GIN on `text_search`
- **Unique**: (document_id, chunking_strategy_id, chunk_no)

### `document_keywords` - Document-keyword junction
- `document_id` (int→document, NOT NULL), `keyword` (text→keywords, NOT NULL)
- **Primary Key**: (document_id, keyword)
- Cascade deletes when document or keyword deleted

## User & Project Management

### `users`
- `id` (int, PK), `username` (text), `email` (text)
- `firstname`, `surname` (text), `pwdhash` (text)

### `projects`
- `id` (int, PK), `title` (text), `description` (text)
- `manager_id` (int→users), `created_at`, `last_worked_on` (timestamps)

### `project_contributors`
- `project_id` (int→projects), `user_id` (int→users)

### `bookmarks`
- `id` (int, PK), `document_id` (int→document), `user_id` (int→users)
- `project_id` (int→projects), `bookmark_type` (text: personal/project/both)
- `created_at` (timestamp)

## Research & Evaluation

### `research_questions`
- `id` (int, PK), `question` (text), `details` (text)

### `project_research_questions`
- `project_id` (int→projects), `question_id` (int→research_questions)
- `is_active` (bool), `created_at`, `updated_at` (timestamps)

### `evaluations` - Chunk relevance ratings
- `research_question_id` (int→research_questions), `chunk_id` (int→chunks)
- `evaluator_id` (int→evaluators), `document_id` (int→document)
- `is_human_evaluator` (bool), `rating` (int), `confidence_level` (float 0-1)
- `rating_reason` (text), `evaluation_version` (int)
- `created_at`, `updated_at` (timestamps)

### `evaluators` - Human/AI evaluators
- `id` (int, PK), `name` (text), `user_id` (int→users)
- `model_id` (text), `parameters` (jsonb), `prompt` (text)
- `created_at`, `updated_at` (timestamps)

### `hypotheses`
- `id` (int, PK), `hypothesis` (text), `counterhypothesis` (text)
- `created_at` (timestamp)

### `hypotheses_projects`
- `project_id` (int→projects), `hypothesis_id` (int→hypotheses)

## AI/ML Infrastructure

### `embedding_base` - Base embedding table
- `id` (int, PK), `chunk_id` (int→chunks, NOT NULL), `model_id` (int→embedding_models)
- Parent table for embedding storage

### `emb_1024` - 1024-dim embedding storage (inherits embedding_base)
- `id` (int, PK), `chunk_id` (int→chunks, NOT NULL), `model_id` (int)
- `embedding` (vector(1024))
- **Indexes**: btree on `chunk_id`, `model_id`, `(chunk_id, model_id)`, HNSW on `embedding` (cosine distance)
- **Unique**: (chunk_id, model_id)
- Used for semantic search with snowflake-arctic-embed2 model

### `embedding_models`
- `id` (int, PK), `provider_id` (int→embedding_provider)
- `model_name` (text, NOT NULL), `model_description` (text), `model_parameters` (jsonb)

### `embedding_provider`
- `id` (int, PK), `provider_name` (text), `base_url` (text)

### `embedding_source`
- Tracks embedding generation sources and metadata

### `models` - LLM models
- `id` (int, PK), `provider_id` (int→model_providers), `name` (text)
- `params` (bigint), `context_length`, `embedding_length` (int)
- `quantization` (text), `is_free`, `is_locally_available`, `is_active` (bool)

### `model_providers`
- `id` (int, PK), `name` (text), `description` (text), `base_url` (text)
- `requires_api_key`, `is_local`, `is_active` (bool), `api_key` (text)

### `model_capabilities`
- Tracks model feature support (embedding, chat, vision, etc.)

### `model_capability_junction`
- Links models to their capabilities

### `prompts`
- `id` (int, PK), `model_id` (int→models), `prompt` (text)
- `purpose` (text), `created_by` (int→users), `created_at` (timestamp)

## Content Generation & Processing

### `generated_data`
- `id` (int, PK), `document_id` (int→document)
- `generation_params_id` (int→generation_params), `generation_type` (int→generated_type)
- `data` (text)

### `generated_type`
- Type definitions for generated content

### `generation_params`
- `id` (int, PK), `model_id` (int→models)
- `system_prompt`, `generation_prompt` (text)

### `summaries`
- `id` (int, PK), `document_id` (int→document), `summary` (text)
- `evaluation` (bool), `reason` (text), `interests` (text[])
- `created_at` (timestamp)

### `processing_queue`
- `id` (int, PK), `document_id` (int→document), `task_id` (int→task)
- `status` (int), `error` (text), `created`, `updated` (timestamps)

### `task`
- Task definitions for queue processing

## User Activity & Recommendations

### `reading_records`
- `id` (int, PK), `user_id` (int→users), `document_id` (int→document)
- `read_timestamp` (timestamp), `rating` (int), `notes` (text)

### `reading_records_tags`
- Tags associated with reading records

### `reading_tags`
- Tag definitions for reading records

### `reading_suggestions`
- `id` (int, PK), `document_id` (int→document), `user_id` (int→users)
- `evaluator_id` (int→evaluators), `recommendation_strength` (int 0-5)
- `confidence_level` (float), `comment` (text), `user_agreement` (bool)
- `created_at`, `updated_at` (timestamps)

### `user_interests`
- `id` (int, PK), `user_id` (int→users), `interest` (text)

### `tags`
- `id` (int, PK), `document_id` (int→document), `user_id` (int→users)
- `tag` (text)

## Metadata & Classification

### `categories`
- `id` (int, PK), `name` (text, UNIQUE, NOT NULL), `description` (text)

### `sources` - Publication sources
- `id` (int, PK), `name` (text, UNIQUE, NOT NULL), `url` (text)
- `is_reputable` (bool, default: false), `is_free` (bool, default: true)

### `keywords` - Global keyword list
- `keyword` (text, PK)

### `chunking_strategies`
- `id` (int, PK), `strategy_name` (text), `modelname` (text)
- `parameters` (jsonb)

### `chunktypes`
- `id` (int, PK), `chunktype` (text)

## DOI & External Data

### `doi_metadata`
- `doi` (text, PK), `openalex_id` (text), `title` (text)
- `publication_year` (int), `work_type` (text), `is_retracted` (bool)
- `created_at`, `updated_at` (timestamps)

### `doi_urls`
- `id` (bigint, PK), `doi` (text), `url` (text), `pdf_url` (text)
- `openalex_id`, `title` (text), `publication_year` (int)
- `location_type` (text), `version`, `license`, `host_type`, `oa_status` (text)
- `is_oa` (bool), `url_quality_score` (int), `last_verified` (timestamp)

## Human Editing & Corrections

### `human_edit`
- Human corrections to AI outputs
- Owner: hherb

### `human_edited`
- `id` (int, PK), `context`, `machine`, `human` (text)
- `timestamp` (timestamp)

## Utility Tables

### `bmlibrarian_migrations`
- Tracks BMLibrarian schema migrations

### `import_tracker`
- `filename` (text, PK), `imported`, `chunked` (timestamps)
- `embedded`, `md5checked` (bool)

### `pubmed_download_log`
- `id` (int, PK), `file_name` (varchar), `file_type` (varchar)
- `download_date`, `process_date` (timestamps), `processed` (bool)
- `file_size` (bigint), `checksum` (varchar), `status` (varchar)

### `version` - Schema versioning
- `version` (int, PK), `migrated` (timestamp), `migration_success` (bool)

## Database Functions

### `bm25(search_expression text, max_results int = 100)`
**BM25-ranked full-text search with length normalization**
- Parameters:
  - `search_expression`: PostgreSQL tsquery format (e.g., 'exercise & cardiovascular')
  - `max_results`: Maximum documents to return (default: 100)
- Returns: TABLE with document fields plus `rank` (real)
- Features:
  - Uses `ts_rank_cd` with length normalization (approximates BM25 k1=1.2, b=0.75)
  - Searches title (weight A) and abstract (weight B)
  - Uses `idx_document_fts` GIN index
  - Excludes withdrawn documents
  - Falls back to `plainto_tsquery` if parsing fails
  - Orders by rank DESC, then publication_date DESC
- Query syntax: AND (&), OR (|), NOT (!), phrase ("text"), prefix (cardio:*)
- Best for: Keyword-based retrieval with superior relevance ranking

### `semantic_search(search_text text, threshold float = 0.7, result_limit int = 100)`
**Semantic similarity search using vector embeddings**
- Parameters:
  - `search_text`: Natural language query
  - `threshold`: Minimum similarity (0.0-1.0, default: 0.7)
  - `result_limit`: Maximum results (default: 100)
- Returns: TABLE(chunk_id int, document_id int, score float)
- Features:
  - Generates embedding via `ollama_embedding()` with snowflake-arctic-embed2:latest
  - Uses cosine similarity (pgvector `<=>` operator)
  - HNSW index for fast approximate nearest neighbor search
  - Searches at chunk level for precise passage retrieval
  - Embedding generation takes ~2-5 seconds per query
- Threshold guidance:
  - 0.85+: High precision, narrow results
  - 0.70-0.85: Balanced (default)
  - 0.60-0.70: High recall, broader results
- Best for: Conceptual similarity, different terminology, question answering

### `fulltext_search(ts_query_expression text, max_results int = 100)`
**Basic full-text search with ts_rank scoring**
- Parameters:
  - `ts_query_expression`: PostgreSQL tsquery format
  - `max_results`: Maximum documents to return (default: 100)
- Returns: TABLE with document fields plus `rank` (real)
- Features:
  - Uses `ts_rank` (simpler than BM25)
  - Uses `idx_document_fts` GIN index
  - Excludes withdrawn documents
  - Falls back to `plainto_tsquery` if parsing fails
  - Orders by rank DESC, then publication_date DESC
- Query syntax: Same as BM25 - AND (&), OR (|), NOT (!), phrase ("text"), prefix (*)
- Best for: Basic keyword search without length normalization

### `ollama_embedding(text_content text)`
**Generate 1024-dimensional embedding vector via Ollama**
- Parameters:
  - `text_content`: Text to embed (query or document chunk)
- Returns: vector(1024) - Embedding vector, or NULL on error
- Features:
  - Calls local Ollama service with snowflake-arctic-embed2:latest model
  - Uses PLPython3u (Python 3 stored procedure)
  - Caches ollama module in session dictionary (SD) for performance
  - Returns 1024-dimensional vector for semantic similarity
  - Logs warnings to PostgreSQL log on errors
- Performance: ~2-5 seconds per embedding generation
- Used by: `semantic_search()` function for query embedding
- Requirements: Ollama service running locally with snowflake-arctic-embed2:latest model
- Example:
  ```sql
  SELECT ollama_embedding('cardiovascular benefits of exercise');
  ```

## High-Level Python API

### `find_abstracts()` - Full-text search with filtering
```python
find_abstracts(
    ts_query_str: str,
    max_rows: int = 100,
    use_pubmed: bool = True,
    use_medrxiv: bool = True,
    use_others: bool = True,
    plain: bool = True,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    batch_size: int = 50,
    use_ranking: bool = False,
    offset: int = 0
) -> Generator[Dict, None, None]
```
- `plain=True`: Uses `plainto_tsquery` for simple text ("covid vaccine")
- `plain=False`: Uses `to_tsquery` for advanced syntax ("covid & vaccine")
- `use_ranking=True`: Orders by `ts_rank_cd` (slower, better relevance)
- `use_ranking=False`: Orders by publication_date (faster)
- Date filtering: `from_date` and `to_date` for publication_date range
- Source filtering: Control PubMed, medRxiv, other sources
- Returns: Generator of document dicts with all metadata fields
- Optimization: Source ID caching for fast queries on 38M+ documents

### `find_abstract_ids()` - Fast ID-only search
```python
find_abstract_ids(
    ts_query_str: str,
    max_rows: int = 100,
    use_pubmed: bool = True,
    use_medrxiv: bool = True,
    use_others: bool = True,
    plain: bool = False,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    offset: int = 0
) -> set[int]
```
- Returns document IDs only (no JOINs, no text fields)
- ~10x faster than `find_abstracts()` for ID collection
- Designed for multi-query workflows (collect IDs, de-duplicate, bulk fetch)
- Same filtering options as `find_abstracts()`

### `fetch_documents_by_ids()` - Bulk document fetch
```python
fetch_documents_by_ids(
    document_ids: set[int],
    batch_size: int = 50
) -> list[Dict[str, Any]]
```
- Fetch full document details for given IDs
- Batched queries to avoid PostgreSQL parameter limits
- Designed for multi-query pattern: collect IDs → de-duplicate → bulk fetch
- Returns complete document dicts (same format as `find_abstracts()`)

### `search_by_embedding()` - Vector similarity search
```python
search_by_embedding(
    embedding: List[float],
    max_results: int = 100,
    model_id: int = 1
) -> List[Dict[str, Any]]
```
- Direct vector similarity search using pgvector
- Requires pre-computed embedding (1024-dim for model_id=1)
- Returns: List of dicts with `id`, `title`, `similarity` (0-1 score)
- Uses HNSW index on `emb_1024.embedding`

### `search_with_bm25()` - BM25 ranked search
```python
search_with_bm25(
    query_text: str,
    max_results: int = 100,
    use_pubmed: bool = True,
    use_medrxiv: bool = True,
    use_others: bool = True
) -> Generator[Dict, None, None]
```
- Wrapper for `bm25()` function
- Returns generator of document dicts with BM25 rank scores
- Best for keyword search with length normalization

### `search_with_semantic()` - Semantic search wrapper
```python
search_with_semantic(
    search_text: str,
    threshold: float = 0.7,
    max_results: int = 100
) -> Generator[Dict, None, None]
```
- Wrapper for `semantic_search()` function
- Aggregates chunk-level results to document level
- Returns generator with `semantic_score`, `matching_chunks` per document
- Joins with document table for full metadata

### `search_hybrid()` - Multi-strategy search orchestrator
```python
search_hybrid(
    search_text: str,
    query_text: str,
    search_config: Optional[Dict[str, Any]] = None,
    use_pubmed: bool = True,
    use_medrxiv: bool = True,
    use_others: bool = True
) -> tuple[List[Dict], Dict[str, Any]]
```
- Combines semantic, BM25, and/or fulltext search
- Configuration controls which strategies are enabled
- Merges and de-duplicates results by document ID
- Calculates combined scores from all strategies
- Returns: (documents list, strategy_metadata dict)
- Priority order: semantic → BM25 → fulltext (fallback)

## Key Relationships

- Documents have chunks with embeddings
- Users create projects with research questions
- Evaluations rate chunk relevance to research questions
- Bookmarks link users/projects to documents
- Reading records track user document interactions
- Generated data stores AI-produced content per document

## Common Query Patterns

### Document Search
```sql
-- Full-text search with BM25
SELECT * FROM bm25('aspirin & cardiovascular', 100);

-- Semantic search (returns chunks)
SELECT * FROM semantic_search('benefits of exercise', 0.75, 50);

-- Hybrid: semantic + full-text
SELECT d.*
FROM semantic_search('gene editing', 0.7, 100) s
JOIN chunks c ON s.chunk_id = c.id
JOIN document d ON c.document_id = d.id
UNION
SELECT * FROM bm25('CRISPR & "gene editing"', 100);
```

### Python API Usage
```python
from bmlibrarian.database import (
    find_abstracts, find_abstract_ids, fetch_documents_by_ids,
    search_hybrid
)

# Simple search
for doc in find_abstracts("covid vaccine", max_rows=50):
    print(doc['title'], doc['publication_date'])

# Multi-query pattern (fast)
ids1 = find_abstract_ids("aspirin & heart", max_rows=100)
ids2 = find_abstract_ids("acetylsalicylic & cardiovascular", max_rows=100)
all_ids = ids1 | ids2  # Set union
docs = fetch_documents_by_ids(all_ids)

# Hybrid search (semantic + BM25 + fulltext)
docs, metadata = search_hybrid(
    search_text="cardiovascular exercise benefits",
    query_text="cardiovascular & exercise & benefits",
    search_config={"semantic": {"enabled": True}, "bm25": {"enabled": True}}
)
```

### Find Relevant Chunks
```sql
SELECT c.text, e.rating, e.confidence_level
FROM chunks c
JOIN evaluations e ON c.id = e.chunk_id
WHERE e.research_question_id = 42
  AND e.rating >= 4
ORDER BY e.rating DESC, e.confidence_level DESC;
```

### User Activity
```sql
SELECT u.username, d.title, r.rating, r.read_timestamp
FROM users u
JOIN reading_records r ON u.id = r.user_id
JOIN document d ON r.document_id = d.id
WHERE u.id = 123
ORDER BY r.read_timestamp DESC;
```

### Project Research
```sql
SELECT p.title, rq.question, rq.details
FROM projects p
JOIN project_research_questions prq ON p.id = prq.project_id
JOIN research_questions rq ON prq.question_id = rq.id
WHERE prq.is_active = true
  AND p.manager_id = 456;
```

### Embeddings Lookup
```sql
SELECT c.document_id, c.text, e.embedding
FROM chunks c
JOIN emb_1024 e ON c.id = e.chunk_id
WHERE c.document_id = 789
  AND e.model_id = 1;
```

## Performance Notes

- **Full-text search**: Very fast with GIN index (`idx_document_fts`)
- **BM25 search**: Fast, uses GIN index, better ranking than basic ts_rank
- **Semantic search**: Slower (~2-5s embedding generation), uses HNSW index
- **Source filtering**: Pre-cached source IDs for fast filtering
- **Date filtering**: btree indexes on `publication_date`
- **Batch processing**: Use `find_abstract_ids()` + `fetch_documents_by_ids()` for multi-query workflows
- **Multi-query optimization**: Collect IDs from multiple queries, de-duplicate with sets, single bulk fetch

## Database Statistics

- **38M+ documents** across PubMed, medRxiv, and other sources
- GIN indexes for fast full-text search
- HNSW indexes for fast vector similarity search
- Production database: **knowledgebase** (read-only for BMLibrarian agents)
- Development database: **bmlibrarian_dev** (for testing/experiments)
