# Vector Search Performance Analysis

## Current Situation

**Performance Problem:**
- Query time: **263 seconds** (4+ minutes)
- Database: 37.5M embeddings, 405 GB total size
- HNSW index: 206 GB (using default parameters)

## Root Causes Identified

### 1. **Suboptimal HNSW Index Parameters** ⚠️

Your current index:
```sql
CREATE INDEX arctic_hnsw_idx_v2 ON emb_1024
USING hnsw (embedding vector_cosine_ops)
WITH (m='6', ef_construction='48')
```

**Problems:**
- `m = 6` is **extremely low** (default is 16, recommended 24-32 for large datasets)
  - This means only 6 connections per node in the graph
  - Results in poor navigation through the vector space
  - Likely the main cause of slow searches
- `ef_construction = 48` is below default (64)
  - Lower quality index construction
- `ef_search = 40` (query time) is default but could be higher

**Impact:** This is likely causing most of your 263s delay. The HNSW graph is too sparse to navigate efficiently.

### 2. **No Hybrid Search Capability** 🔴

Your `chunks` table doesn't have a `text_search` column for full-text pre-filtering.

**Current columns:**
- `id`, `document_id`, `chunking_strategy_id`, `chunktype_id`
- `document_title`, `text` ← content column
- `chunklength`, `chunk_no`, `page_start`, `page_end`, `metadata`

**Missing:** `text_search tsvector` column + GIN index

### 3. **Index Usage Statistics**

```
arctic_hnsw_idx_v2: 206 GB
  Scans: 0
  Tuples read: 0
  Tuples fetched: 0
```

**Note:** The HNSW index shows 0 scans, which likely means:
- Either the statistics were recently reset
- Or the index isn't being used as expected

## Recommended Solutions

### Quick Wins (Try First)

#### Option A: Increase `ef_search` Parameter (Immediate)

```sql
-- Try in your session before each query
SET hnsw.ef_search = 100;  -- or 200, 400
```

**Expected:** Modest improvement, but won't fix the core issue with m=6

#### Option B: Rebuild HNSW Index (High Impact, Takes Time)

```sql
-- Drop existing index
DROP INDEX IF EXISTS arctic_hnsw_idx_v2;

-- Recreate with proper parameters for 37M vectors
CREATE INDEX arctic_hnsw_idx_v3 ON emb_1024
USING hnsw (embedding vector_cosine_ops)
WITH (
    m = 24,                -- 4x increase from current m=6
    ef_construction = 96   -- 2x increase from current 48
);
```

**Expected:** Could reduce 263s to 30-60s (5-10x improvement)
**Downside:** Will take hours to build (possibly 4-8 hours for 37M rows)

### Major Optimization (Highest Impact)

#### Enable Hybrid Search (Full-text + Vector)

**Step 1: Add text search column**
```sql
ALTER TABLE chunks ADD COLUMN text_search tsvector;
UPDATE chunks SET text_search = to_tsvector('english', text);
CREATE INDEX idx_chunks_text_search ON chunks USING GIN(text_search);
```

**Step 2: Use hybrid search script**
```bash
uv run python hybrid_search.py "your query"
```

**Expected:** 263s → 2-5s (50-100x improvement!)
**How it works:** Pre-filter 37M chunks to ~1K-10K using keywords, then vector search
**Time to implement:** 30-60 minutes to create text_search column

## Action Plan

### Recommended Sequence

**Phase 1: Quick Test (5 minutes)**
```sql
SET hnsw.ef_search = 200;
-- Then run your query
```
- If this helps significantly → your query needs better exploration
- If minimal impact → m=6 is the real bottleneck

**Phase 2: Enable Hybrid Search (1 hour)**
Run the SQL from `optimize_index.sql`:
```bash
psql knowledgebase -f optimize_index.sql
```

This will:
1. Add text_search column to chunks
2. Populate it (30-45 min for 37M rows)
3. Create GIN index (5-10 min)
4. Set up trigger for future updates

Then test:
```bash
uv run python hybrid_search.py "mountain sickness prevention"
```

**Phase 3: Rebuild HNSW Index (4-8 hours, optional)**
Only if hybrid search isn't enough:
```sql
DROP INDEX arctic_hnsw_idx_v2;
CREATE INDEX arctic_hnsw_idx_v3 ON emb_1024
USING hnsw (embedding vector_cosine_ops)
WITH (m = 24, ef_construction = 96);
```

**Note:** This can run overnight. You can use pure full-text search during the rebuild.

## Performance Expectations

| Optimization | Expected Time | Improvement | Effort |
|--------------|---------------|-------------|--------|
| Current | 263s | baseline | - |
| SET ef_search=200 | 200-250s | 1.1-1.3x | 1 min |
| Hybrid search | 2-5s | 50-100x | 1 hour |
| Rebuild m=24 | 30-60s | 4-9x | 4-8 hours |
| Hybrid + Rebuild | 1-2s | 100-200x | 5-9 hours |

## Key Insights

1. **m=6 is extremely low** - This is your main bottleneck
2. **Hybrid search is your best option** - Quick to implement, massive impact
3. **37.5M embeddings is manageable** - With proper indexing and hybrid search
4. **206 GB index size is reasonable** - For 37.5M × 1024-dim vectors

## Files Created

- `semantic_search.py` - Pure vector search (current approach)
- `hybrid_search.py` - Combined full-text + vector search
- `optimize_index.sql` - SQL commands for all optimizations
- `analyze_index.py` - Diagnostic tool
- `VECTOR_SEARCH_OPTIMIZATION.md` - Detailed technical guide
