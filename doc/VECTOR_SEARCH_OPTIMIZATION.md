# Vector Search Optimization Guide

## Current Performance Issue

**Problem**: Vector search on 60M chunks taking ~263 seconds (4+ minutes)
- Database: 40M documents, 60M chunks
- Embedding: 1024-dimensional vectors
- Index: HNSW index on embeddings
- Query time: 262.9s for database search

## Optimization Strategies

### 1. Hybrid Search (Full-text + Vector) **[RECOMMENDED - TRY FIRST]**

Pre-filter candidates using PostgreSQL full-text search before vector similarity:

**Prerequisites**:
```sql
-- Add tsvector column to chunks table (if not exists)
ALTER TABLE chunks ADD COLUMN text_search tsvector;

-- Populate the tsvector column
UPDATE chunks SET text_search = to_tsvector('english', content);

-- Create GIN index for full-text search
CREATE INDEX idx_chunks_text_search ON chunks USING GIN(text_search);
```

**Expected Impact**:
- Reduces search space from 60M to ~1K-100K chunks
- Should bring query time from 263s to <5s
- Best for queries with specific domain terms (e.g., "mountain", "methylprednisolone")

**Usage**:
```bash
uv run python hybrid_search.py "mountain sickness prevention"
```

### 2. HNSW Index Tuning

Your HNSW index may need optimization:

```sql
-- Check current HNSW index parameters
SELECT * FROM pg_indexes WHERE indexname LIKE '%emb_1024%';

-- Drop existing index
DROP INDEX IF EXISTS idx_emb_1024_embedding;

-- Recreate with optimized parameters for large dataset
CREATE INDEX idx_emb_1024_embedding ON emb_1024
USING hnsw (embedding vector_cosine_ops)
WITH (
    m = 16,              -- Connections per layer (default: 16, range: 2-100)
    ef_construction = 64 -- Build-time search depth (default: 64, higher = better recall)
);

-- At query time, increase ef_search for better recall (default: 40)
SET hnsw.ef_search = 100;
```

**Parameter Tuning**:
- **m**: Number of bi-directional links per layer
  - Higher = better recall, more memory, slower indexing
  - For 60M chunks: try 16-32

- **ef_construction**: Candidate list size during index build
  - Higher = better index quality, slower build time
  - For production: try 64-128

- **ef_search**: Query-time search depth
  - Higher = better recall, slower queries
  - Try: 40, 80, 100, 200

**Expected Impact**: May improve from 263s to 100-150s (not dramatic)

### 3. Partitioning Strategy

Partition embeddings by document type, date, or domain:

```sql
-- Create partitioned table
CREATE TABLE emb_1024_partitioned (
    id BIGSERIAL,
    chunk_id BIGINT NOT NULL,
    model_id INTEGER NOT NULL,
    embedding vector(1024),
    document_type TEXT  -- Add partitioning key
) PARTITION BY LIST (document_type);

-- Create partitions
CREATE TABLE emb_1024_medical PARTITION OF emb_1024_partitioned
    FOR VALUES IN ('medical', 'clinical');
CREATE TABLE emb_1024_research PARTITION OF emb_1024_partitioned
    FOR VALUES IN ('research', 'academic');

-- Create HNSW indexes on each partition
CREATE INDEX idx_emb_1024_medical_embedding
    ON emb_1024_medical USING hnsw (embedding vector_cosine_ops);
```

**Expected Impact**:
- Can reduce search to specific partition (e.g., medical only)
- Potentially 5-10x speedup if queries target specific partitions

### 4. Approximate Search with Distance Threshold

Use distance threshold to short-circuit searches:

```sql
-- Add WHERE clause to limit search space
SELECT d.title,
       1 - distance AS similarity
FROM (
    SELECT c.document_id,
           e.embedding <=> %s::vector AS distance
    FROM emb_1024 e
    JOIN chunks c ON e.chunk_id = c.id
    WHERE e.model_id = 1
      AND e.embedding <=> %s::vector < 0.5  -- Distance threshold
    ORDER BY distance
    LIMIT %s
) AS ranked
JOIN document d ON ranked.document_id = d.id;
```

**Caveat**: May miss relevant results if threshold too strict.

### 5. Two-Stage Retrieval

**Stage 1**: Fast approximate search with relaxed HNSW parameters
**Stage 2**: Re-rank top-K candidates with exact computation

```python
def two_stage_search(query_embedding, k=10, stage1_k=1000):
    # Stage 1: Fast approximate search
    SET hnsw.ef_search = 40  # Lower for speed
    candidates = vector_search(query_embedding, limit=stage1_k)

    # Stage 2: Re-rank with exact cosine similarity
    reranked = [(doc, exact_cosine(query_embedding, doc.embedding))
                for doc in candidates]
    return sorted(reranked, key=lambda x: x[1], reverse=True)[:k]
```

### 6. Product Quantization (PQ)

Compress vectors to reduce memory and I/O:

```sql
-- Requires pgvector with Product Quantization support
-- Compress 1024-dim to 256 bytes (4x compression)
CREATE INDEX idx_emb_1024_pq ON emb_1024
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 1000);
```

**Trade-off**: Slightly reduced recall for much faster search

### 7. Hardware/Configuration

**PostgreSQL Configuration** (`postgresql.conf`):
```ini
# Increase work memory for sorting
work_mem = 256MB

# Increase shared buffers for caching
shared_buffers = 8GB

# Increase effective cache size
effective_cache_size = 24GB

# Parallel query workers
max_parallel_workers_per_gather = 4
```

**Expected Impact**: 10-30% improvement

### 8. Materialized Chunk Metadata

Pre-join frequently accessed data:

```sql
-- Materialized view with denormalized data
CREATE MATERIALIZED VIEW emb_1024_denorm AS
SELECT
    e.id,
    e.chunk_id,
    e.model_id,
    e.embedding,
    c.document_id,
    d.title,
    d.publication_year,
    d.document_type
FROM emb_1024 e
JOIN chunks c ON e.chunk_id = c.id
JOIN document d ON c.document_id = d.id
WHERE e.model_id = 1;

CREATE INDEX idx_emb_1024_denorm_embedding
    ON emb_1024_denorm USING hnsw (embedding vector_cosine_ops);

-- Refresh periodically
REFRESH MATERIALIZED VIEW emb_1024_denorm;
```

**Expected Impact**: Eliminates join overhead, 20-40% speedup

## Recommended Action Plan

### Phase 1: Quick Wins (Try Today)
1. ✅ **Implement hybrid search** (full-text + vector) - `hybrid_search.py`
2. ✅ **Tune HNSW ef_search** parameter (try 100, 200)
3. ✅ **Add full-text search index** if missing

### Phase 2: Index Optimization (This Week)
4. Rebuild HNSW index with optimized parameters
5. Add materialized view for denormalized data
6. Tune PostgreSQL configuration

### Phase 3: Architecture Changes (If Still Slow)
7. Implement table partitioning by document type/domain
8. Consider two-stage retrieval strategy
9. Evaluate product quantization for memory reduction

## Benchmarking Commands

```bash
# Test original vector search
uv run python semantic_search.py "mountain sickness prevention"

# Test hybrid search with different limits
uv run python hybrid_search.py "mountain sickness prevention"

# SQL benchmarks
psql -d knowledgebase -c "
SET hnsw.ef_search = 100;
EXPLAIN ANALYZE
SELECT ...
"
```

## Expected Results

| Method | Expected Time | Recall Quality |
|--------|---------------|----------------|
| Current (pure vector) | 263s | High |
| Hybrid (10K pre-filter) | 2-5s | High |
| Hybrid (1K pre-filter) | <1s | Medium-High |
| Optimized HNSW | 100-150s | High |
| Partitioned + Hybrid | <1s | High (in partition) |

## Monitoring Queries

```sql
-- Check index usage
SELECT schemaname, tablename, indexname, idx_scan, idx_tup_read, idx_tup_fetch
FROM pg_stat_user_indexes
WHERE indexname LIKE '%emb%';

-- Check table size
SELECT pg_size_pretty(pg_total_relation_size('emb_1024'));

-- Check HNSW index size
SELECT pg_size_pretty(pg_relation_size('idx_emb_1024_embedding'));
```
