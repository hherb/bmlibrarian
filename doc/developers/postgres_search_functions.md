# PostgreSQL Search Functions

This document describes the custom PostgreSQL functions available in the BMLibrarian knowledge base for searching biomedical literature.

## Overview

BMLibrarian provides four complementary search functions:

1. **`fulltext_search`** - Traditional keyword-based search using PostgreSQL's full-text search
2. **`bm25`** - BM25-like ranked search with length normalization for better relevance
3. **`semantic_search`** - AI-powered semantic search using vector embeddings
4. **`ollama_embedding`** - Helper function to generate embeddings (used by semantic_search)

## Functions

### 1. fulltext_search

Performs traditional keyword-based full-text search on document metadata (title, abstract, authors, etc.).

**Signature:**
```sql
fulltext_search(
    ts_query_expression TEXT,
    max_results INTEGER DEFAULT 100
)
RETURNS TABLE(
    id INTEGER,
    title TEXT,
    abstract TEXT,
    authors TEXT[],
    publication TEXT,
    publication_date DATE,
    doi TEXT,
    url TEXT,
    pdf_filename TEXT,
    external_id TEXT,
    source_id INTEGER,
    rank REAL
)
```

**Parameters:**
- `ts_query_expression` - Text search query (can use PostgreSQL tsquery syntax or plain text)
- `max_results` - Maximum number of results to return (default: 100)

**Returns:**
- Complete document records ordered by relevance rank
- `rank` - Relevance score from ts_rank (higher is more relevant)

**Features:**
- Automatically parses complex query syntax (AND, OR, NOT)
- Falls back to simpler parsing if complex syntax fails
- Excludes withdrawn documents
- Orders by relevance rank, then publication date

**Examples:**

```sql
-- Simple keyword search
SELECT id, title, rank
FROM fulltext_search('cardiovascular exercise', 20);

-- Boolean operators
SELECT id, title, rank
FROM fulltext_search('diabetes & (treatment | therapy)', 50);

-- Phrase search
SELECT id, title, rank
FROM fulltext_search('myocardial infarction', 100);

-- Exclude terms
SELECT id, title, rank
FROM fulltext_search('cancer & !melanoma', 30);
```

**Use Cases:**
- Finding documents with specific keywords
- Boolean queries with AND/OR/NOT operators
- Quick keyword-based filtering
- Traditional bibliographic search

---

### 2. bm25

Performs BM25-like ranked full-text search with advanced length normalization for superior relevance ranking.

**Signature:**
```sql
bm25(
    search_expression TEXT,
    max_results INTEGER DEFAULT 100
)
RETURNS TABLE(
    id INTEGER,
    title TEXT,
    abstract TEXT,
    authors TEXT[],
    publication TEXT,
    publication_date DATE,
    doi TEXT,
    url TEXT,
    pdf_filename TEXT,
    external_id TEXT,
    source_id INTEGER,
    rank REAL
)
```

**Parameters:**
- `search_expression` - Text search query (can use PostgreSQL tsquery syntax or plain text)
- `max_results` - Maximum number of results to return (default: 100)

**Returns:**
- Complete document records ordered by BM25-like relevance rank
- `rank` - BM25-approximated relevance score (higher is more relevant)

**Features:**
- Uses `ts_rank_cd` with length normalization for BM25-like behavior
- Better relevance ranking than basic `ts_rank` (especially for varying document lengths)
- Automatically parses complex query syntax (AND, OR, NOT)
- Falls back to simpler parsing if complex syntax fails
- Excludes withdrawn documents
- Orders by relevance rank, then publication date

**Technical Details:**
- Uses `ts_rank_cd` (cover density ranking) instead of `ts_rank`
- Normalization flag 1: divides rank by document length
- Approximates BM25 parameters: k1=1.2, b=0.75
- More accurate than `ts_rank` for documents with varying lengths

**Examples:**

```sql
-- Simple BM25 search
SELECT id, title, rank
FROM bm25('cardiovascular exercise benefits', 20);

-- Boolean operators with BM25
SELECT id, title, abstract, rank
FROM bm25('diabetes & (treatment | therapy)', 50);

-- Phrase search with BM25
SELECT id, title, publication_date, rank
FROM bm25('myocardial infarction', 100);

-- Complex query with metadata filtering
SELECT id, title, authors, publication_date, rank
FROM bm25('cancer immunotherapy', 50)
WHERE publication_date >= '2020-01-01';

-- Compare BM25 vs basic fulltext
SELECT
    'BM25' AS method,
    id,
    title,
    rank
FROM bm25('machine learning drug discovery', 10)
UNION ALL
SELECT
    'Fulltext' AS method,
    id,
    title,
    rank
FROM fulltext_search('machine learning drug discovery', 10)
ORDER BY method, rank DESC;
```

**Use Cases:**
- Superior relevance ranking compared to basic full-text search
- Finding most relevant documents when corpus has varying document lengths
- Research queries where ranking quality is critical
- Boolean queries with better relevance weighting
- Preferred over `fulltext_search` for most keyword-based searches

**Performance Notes:**
- Similar performance to `fulltext_search` (uses same GIN index)
- Slightly more computation for rank calculation
- Better precision/recall trade-off than basic ts_rank

---

### 3. semantic_search

Performs AI-powered semantic search using vector embeddings to find conceptually similar content.

**Signature:**
```sql
semantic_search(
    search_text TEXT,
    threshold FLOAT DEFAULT 0.7,
    result_limit INTEGER DEFAULT 100
)
RETURNS TABLE(
    chunk_id INTEGER,
    document_id INTEGER,
    score FLOAT
)
```

**Parameters:**
- `search_text` - Natural language search query
- `threshold` - Minimum similarity score (0.0 to 1.0, default: 0.7)
- `result_limit` - Maximum number of results to return (default: 100)

**Returns:**
- `chunk_id` - ID of the matching text chunk
- `document_id` - ID of the source document
- `score` - Similarity score from 0 to 1 (1 is most similar)

**Features:**
- Uses cosine similarity on 1024-dimensional vector embeddings
- Finds conceptually similar content, not just keyword matches
- Searches at chunk level for precise passage retrieval
- Powered by Snowflake Arctic Embed 2 model via Ollama

**Technical Details:**
- Embeddings table: `emb_1024` (vector dimension: 1024)
- Embedding model: `snowflake-arctic-embed2:latest`
- Similarity metric: Cosine similarity (pgvector `<=>` operator)
- Index: HNSW for fast approximate nearest neighbor search

**Examples:**

```sql
-- Basic semantic search
SELECT chunk_id, document_id, score
FROM semantic_search('What are the cardiovascular benefits of exercise?', 0.7, 20);

-- High precision search (stricter threshold)
SELECT chunk_id, document_id, score
FROM semantic_search('mechanisms of insulin resistance', 0.85, 50);

-- Broader search (lower threshold, more results)
SELECT chunk_id, document_id, score
FROM semantic_search('diabetes treatment options', 0.6, 100);

-- Join with chunks table to get text
SELECT s.score, c.text, c.document_title
FROM semantic_search('CRISPR gene editing applications', 0.75, 10) s
JOIN chunks c ON s.chunk_id = c.id
ORDER BY s.score DESC;

-- Join with document table for full metadata
SELECT DISTINCT ON (s.document_id)
    s.score,
    d.title,
    d.authors,
    d.publication_date,
    d.doi
FROM semantic_search('immunotherapy cancer treatment', 0.7, 50) s
JOIN chunks c ON s.chunk_id = c.id
JOIN document d ON s.document_id = d.id
ORDER BY s.document_id, s.score DESC;
```

**Use Cases:**
- Conceptual similarity search
- Finding related research even with different terminology
- Question answering over document corpus
- Discovering relevant passages for evidence synthesis
- Finding documents by research question, not just keywords

**Performance Notes:**
- Embedding generation takes ~2-5 seconds per query
- Sequential scan is used when HNSW index is rebuilding
- Consider adjusting `result_limit` based on corpus size
- Lower `threshold` values return more results but may be less relevant

---

### 4. ollama_embedding

Helper function that generates vector embeddings for text using the Ollama embedding service.

**Signature:**
```sql
ollama_embedding(text_content TEXT)
RETURNS vector(1024)
```

**Parameters:**
- `text_content` - Text to generate embedding for

**Returns:**
- 1024-dimensional vector embedding
- `NULL` if embedding generation fails

**Features:**
- Uses PL/Python3 to call Ollama API
- Embedding model: `snowflake-arctic-embed2:latest`
- Caches Ollama client in session dictionary for performance
- Returns NULL on error with warning message

**Technical Details:**
- Language: PL/Python3U (untrusted)
- Model: Snowflake Arctic Embed 2 (1024 dimensions)
- Ollama server: Default local instance (http://localhost:11434)

**Examples:**

```sql
-- Generate embedding for a text
SELECT ollama_embedding('cardiovascular benefits of regular exercise');

-- Calculate similarity between two texts
SELECT
    1 - (ollama_embedding('heart disease prevention') <=>
         ollama_embedding('cardiovascular health maintenance'))::FLOAT AS similarity;

-- Find most similar existing embedding
WITH query_emb AS (
    SELECT ollama_embedding('diabetes medication') AS emb
)
SELECT c.id, c.text,
       (1 - (e.embedding <=> query_emb.emb))::FLOAT AS similarity
FROM emb_1024 e
CROSS JOIN query_emb
JOIN chunks c ON e.chunk_id = c.id
ORDER BY e.embedding <=> query_emb.emb
LIMIT 10;
```

**Use Cases:**
- Direct embedding generation for custom queries
- Calculating text similarity
- Building custom search functions
- Used internally by `semantic_search`

**Requirements:**
- Ollama service must be running
- `snowflake-arctic-embed2:latest` model must be installed
- PL/Python3 extension must be enabled

---

## Comparison: Search Methods

| Feature | fulltext_search | bm25 | semantic_search |
|---------|----------------|------|-----------------|
| **Search Type** | Keyword-based | Keyword-based (better ranking) | Concept-based |
| **Returns** | Complete documents | Complete documents | Text chunks |
| **Speed** | Very fast (GIN index) | Very fast (GIN index) | Slower (embedding generation) |
| **Precision** | Good for exact terms | Better for exact terms | High for concepts |
| **Recall** | Misses synonyms | Misses synonyms | Finds related concepts |
| **Ranking Quality** | Basic | Superior (length-normalized) | Excellent (semantic) |
| **Use Case** | Quick keyword search | Best keyword search | Natural questions |
| **Query Type** | Boolean operators | Boolean operators | Natural language |
| **Best For** | Simple queries | Research queries | Conceptual similarity |

### When to Use Each

**Use `fulltext_search` when:**
- You need the absolute fastest results
- Ranking quality is not critical
- You're doing simple keyword lookups
- You want basic Boolean operators

**Use `bm25` when:**
- You know specific keywords or phrases
- You need high-quality relevance ranking
- You want complete document metadata
- You're using Boolean operators (AND, OR, NOT)
- Documents have varying lengths (BM25 handles this well)
- You want the best keyword-based search (recommended default)

**Use `semantic_search` when:**
- You have a natural language question
- You want conceptually similar content
- Keywords may vary (synonyms, different terminology)
- You need specific passages that answer a question
- You want to find related research with different wording

**General Recommendation:**
- For keyword searches: Use `bm25` (better ranking than `fulltext_search`)
- For concept searches: Use `semantic_search`
- For hybrid approaches: Combine `bm25` + `semantic_search`

### Combining Multiple Approaches

For best results, consider using hybrid search combining keyword and semantic methods:

```sql
-- Example: Hybrid search combining BM25 and semantic search
WITH bm25_results AS (
    SELECT id AS document_id, rank * 2 AS score  -- Scale BM25 score
    FROM bm25('cardiovascular exercise', 100)
),
semantic_results AS (
    SELECT DISTINCT document_id, AVG(score) AS score
    FROM semantic_search('What are the cardiovascular benefits of exercise?', 0.7, 100)
    GROUP BY document_id
)
SELECT
    COALESCE(bm.document_id, sr.document_id) AS document_id,
    COALESCE(bm.score, 0) + COALESCE(sr.score, 0) AS combined_score,
    COALESCE(bm.score, 0) AS keyword_score,
    COALESCE(sr.score, 0) AS semantic_score
FROM bm25_results bm
FULL OUTER JOIN semantic_results sr ON bm.document_id = sr.document_id
ORDER BY combined_score DESC
LIMIT 50;
```

---

## Database Schema Reference

### Tables Used

**document** - Stores document metadata
- `id` - Primary key
- `title`, `abstract`, `authors`, `publication`, etc.
- `search_vector` - tsvector for full-text search
- `withdrawn_date` - NULL for active documents

**chunks** - Stores document text chunks
- `id` - Primary key (chunk_id)
- `document_id` - Foreign key to document
- `text` - Chunk text content
- `document_title`, `chunk_no`, `page_start`, `page_end`

**emb_1024** - Stores 1024-dimensional embeddings
- `id` - Primary key
- `chunk_id` - Foreign key to chunks
- `embedding` - vector(1024)
- Inherits from `embedding_base`

### Indexes

**Full-text search:**
- `document.search_vector` - GIN index for fast text search

**Semantic search:**
- `arctic_hnsw_idx_v4` - HNSW index on `emb_1024.embedding` for fast vector similarity

---

## Installation and Setup

### Prerequisites

1. **PostgreSQL Extensions:**
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;     -- pgvector for embeddings
   CREATE EXTENSION IF NOT EXISTS plpython3u; -- PL/Python for ollama_embedding
   ```

2. **Ollama Service:**
   - Install Ollama: https://ollama.ai
   - Pull embedding model: `ollama pull snowflake-arctic-embed2:latest`
   - Ensure service is running on localhost:11434

3. **Python Dependencies (for PL/Python):**
   ```bash
   pip install ollama
   ```

### Function Installation

All functions are already installed in the `knowledgebase` database. To reinstall or update, see the function definitions in this document.

---

## Performance Tips

### Full-text Search
- Use specific keywords for better precision
- Combine with publication date filters
- Use `max_results` to limit large result sets

### Semantic Search
- Adjust `threshold` based on your precision/recall needs:
  - 0.85+ : High precision, narrow results
  - 0.70-0.85 : Balanced (default)
  - 0.60-0.70 : High recall, broader results
- Use appropriate `result_limit` (smaller limits are faster)
- Join with chunks/document tables only for final results
- Consider caching frequent queries

### General Tips
- HNSW index rebuilding? Semantic search will use sequential scan (slower)
- Monitor Ollama service resource usage
- For production, consider connection pooling to Ollama
- Use `EXPLAIN ANALYZE` to understand query plans

---

## Troubleshooting

### Semantic Search Taking Too Long
- Check if HNSW index is valid: `\d emb_1024`
- Verify Ollama service is running: `curl http://localhost:11434/api/tags`
- Reduce `result_limit` for faster results
- Consider using a lower `threshold` to reduce filtering overhead

### Embedding Generation Fails
- Check Ollama service: `ollama list` should show `snowflake-arctic-embed2:latest`
- Verify network connectivity to localhost:11434
- Check PostgreSQL logs for PL/Python errors
- Test directly: `SELECT ollama_embedding('test');`

### No Results from Fulltext Search
- Verify query syntax: Try simple keywords first
- Check if documents exist: `SELECT COUNT(*) FROM document WHERE withdrawn_date IS NULL;`
- Test with broader terms
- Use `plainto_tsquery` for automatic query simplification

### Permission Errors
- Ensure database user has EXECUTE permissions on functions
- PL/Python functions require superuser or trusted language privileges
- Check table SELECT permissions on document, chunks, emb_1024

---

## Examples: Common Query Patterns

### Pattern 1: Find documents and relevant passages

```sql
-- Find documents about a topic with their most relevant passages
WITH semantic_results AS (
    SELECT chunk_id, document_id, score
    FROM semantic_search('role of inflammation in atherosclerosis', 0.75, 50)
)
SELECT
    d.title,
    d.authors,
    d.publication_date,
    c.text,
    sr.score
FROM semantic_results sr
JOIN chunks c ON sr.chunk_id = c.id
JOIN document d ON sr.document_id = d.id
ORDER BY sr.score DESC
LIMIT 20;
```

### Pattern 2: Hybrid search with ranking

```sql
-- Combine fulltext and semantic search with weighted scoring
WITH ft AS (
    SELECT id AS document_id, rank * 1.5 AS ft_score
    FROM fulltext_search('CRISPR & gene & editing', 100)
),
sem AS (
    SELECT document_id, AVG(score) AS sem_score
    FROM semantic_search('CRISPR gene editing applications in medicine', 0.7, 100)
    GROUP BY document_id
)
SELECT
    d.title,
    d.publication_date,
    d.doi,
    COALESCE(ft.ft_score, 0) AS keyword_score,
    COALESCE(sem.sem_score, 0) AS semantic_score,
    (COALESCE(ft.ft_score, 0) + COALESCE(sem.sem_score, 0)) AS total_score
FROM ft
FULL OUTER JOIN sem ON ft.document_id = sem.document_id
JOIN document d ON COALESCE(ft.document_id, sem.document_id) = d.id
ORDER BY total_score DESC
LIMIT 25;
```

### Pattern 3: Find contradictory evidence

```sql
-- Find documents that discuss opposite viewpoints
WITH supporting AS (
    SELECT DISTINCT document_id
    FROM semantic_search('benefits of low-carbohydrate diets for diabetes', 0.75, 30)
),
contradicting AS (
    SELECT DISTINCT document_id
    FROM semantic_search('risks and concerns about low-carbohydrate diets', 0.75, 30)
)
SELECT
    d.title,
    d.authors,
    d.publication_date,
    CASE
        WHEN s.document_id IS NOT NULL AND c.document_id IS NOT NULL THEN 'Both'
        WHEN s.document_id IS NOT NULL THEN 'Supporting'
        ELSE 'Contradicting'
    END AS evidence_type
FROM supporting s
FULL OUTER JOIN contradicting c ON s.document_id = c.document_id
JOIN document d ON COALESCE(s.document_id, c.document_id) = d.id
ORDER BY evidence_type, d.publication_date DESC;
```

### Pattern 4: Recent high-impact research

```sql
-- Find recent, highly relevant papers
SELECT
    d.title,
    d.authors,
    d.publication_date,
    s.score
FROM semantic_search('machine learning in drug discovery', 0.80, 100) s
JOIN document d ON s.document_id = d.id
WHERE d.publication_date >= '2020-01-01'
ORDER BY s.score DESC, d.publication_date DESC
LIMIT 15;
```

### Pattern 5: Topic clustering

```sql
-- Find related documents by embedding similarity
WITH seed_docs AS (
    SELECT DISTINCT document_id
    FROM semantic_search('COVID-19 vaccine efficacy', 0.85, 10)
),
related_chunks AS (
    SELECT e.chunk_id, e.embedding
    FROM seed_docs sd
    JOIN chunks c ON sd.document_id = c.document_id
    JOIN emb_1024 e ON c.id = e.chunk_id
)
SELECT DISTINCT
    d.id,
    d.title,
    d.publication_date,
    AVG((1 - (e.embedding <=> rc.embedding))::FLOAT) AS avg_similarity
FROM related_chunks rc
CROSS JOIN emb_1024 e
JOIN chunks c ON e.chunk_id = c.id
JOIN document d ON c.document_id = d.id
WHERE e.chunk_id NOT IN (SELECT chunk_id FROM related_chunks)
GROUP BY d.id, d.title, d.publication_date
HAVING AVG((1 - (e.embedding <=> rc.embedding))::FLOAT) > 0.75
ORDER BY avg_similarity DESC
LIMIT 20;
```

---

## See Also

- [BMLibrarian Query Agent Guide](../users/query_agent_guide.md)
- [Multi-Model Query Generation](../users/multi_model_query_guide.md)
- [PostgreSQL Full-Text Search](https://www.postgresql.org/docs/current/textsearch.html)
- [pgvector Documentation](https://github.com/pgvector/pgvector)
- [Ollama Documentation](https://ollama.ai/docs)
