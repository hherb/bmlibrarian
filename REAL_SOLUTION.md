# The Real Problem and Solution

## Bottom Line

**Your HNSW index with m=6 is fundamentally broken for this dataset size.** No workaround will fix this - you need to rebuild the index.

## Why Hybrid Search Didn't Help

The hybrid search approach tried to reduce the search space by pre-filtering with keywords, but:
1. Medical terminology is too complex (synonyms, acronyms, abbreviations)
2. Keyword extraction isn't generalizable across all medical questions
3. **Even after filtering, the HNSW index with m=6 is still too slow**

The real issue: **Your m=6 index takes ~3 seconds per result** even on small subsets!

## The Only Real Solutions

### Option 1: Rebuild HNSW Index (Recommended)

**Problem**: m=6 creates a sparse graph that requires too many hops to find neighbors

**Solution**: Rebuild with m=16 or m=12 (not m=24 due to disk space)

```sql
-- Drop old index
DROP INDEX IF EXISTS arctic_hnsw_idx_v2;

-- Rebuild with m=12 (compromise between quality and disk space)
CREATE INDEX arctic_hnsw_idx_v3 ON emb_1024
USING hnsw (embedding vector_cosine_ops)
WITH (
    m = 12,              -- 2x current (vs 4x for m=24)
    ef_construction = 64 -- Keep default
);
```

**Expected outcomes:**
- Index size: ~412 GB (vs 824 GB for m=24)
- Net increase: ~206 GB (manageable with your 853 GB free)
- Query time: **263s → 30-60s** (5-10x improvement)
- Build time: 2-4 hours for 37M embeddings

**Disk space timeline:**
1. Start: 853 GB free
2. During build: 853 - 412 = 441 GB free (both indexes exist)
3. After dropping old: 853 - 206 = 647 GB free

### Option 2: Switch to IVFFlat Index

If you can't afford the rebuild time or disk space:

```sql
-- Drop HNSW index
DROP INDEX IF EXISTS arctic_hnsw_idx_v2;

-- Create IVFFlat index (faster build, reasonable query time)
CREATE INDEX arctic_ivfflat_idx ON emb_1024
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 5000);  -- sqrt(37M) ≈ 6000

-- At query time
SET ivfflat.probes = 50;  -- Check 50 lists (higher = better recall)
```

**Expected outcomes:**
- Index size: ~50-100 GB (much smaller than HNSW)
- Query time: **263s → 10-30s** (8-25x improvement)
- Build time: 30-60 minutes (much faster than HNSW)
- Trade-off: Slightly lower recall than good HNSW

### Option 3: Increase ef_search (Minimal Help)

Quick test to see if it helps at all:

```sql
SET hnsw.ef_search = 200;  -- or 400, 800
```

**Expected:** Minimal improvement (maybe 263s → 200s) because m=6 is the real bottleneck

## Recommendation

Given your constraints:

1. **First, try Option 3** (SET ef_search = 200) - takes 1 second, see if it helps
2. **If no major improvement** → **Do Option 1** (rebuild with m=12)
   - You have the disk space (206 GB needed, 853 GB available)
   - Will give you 5-10x speedup
   - One-time pain for long-term gain

3. **If disk space/time is a problem** → Do Option 2 (IVFFlat)
   - Faster to build
   - Smaller index
   - Still gives 8-25x speedup

## Why m=6 is So Bad

HNSW works by building a hierarchical graph where each node connects to `m` neighbors per layer.

- **m=6**: Each node has only 6 connections → requires many hops to reach similar vectors
- **m=16**: Each node has 16 connections → fewer hops, faster search
- **m=24**: Even better, but 4x the disk space

With 37M vectors and m=6, the average path length is too long, causing the 263s searches.

## Commands to Run

### Quick Test (Option 3)
```bash
psql knowledgebase -c "SET hnsw.ef_search = 200;" -c "SELECT 1"
uv run python semantic_search.py "your query"
```

### Rebuild Index (Option 1 - Recommended)
```sql
-- Run during off-hours
DROP INDEX arctic_hnsw_idx_v2;
CREATE INDEX arctic_hnsw_idx_v3 ON emb_1024
USING hnsw (embedding vector_cosine_ops)
WITH (m = 12, ef_construction = 64);

-- Monitor progress
SELECT now(), pg_stat_progress_create_index.*
FROM pg_stat_progress_create_index;
```

### Switch to IVFFlat (Option 2)
```sql
DROP INDEX arctic_hnsw_idx_v2;
CREATE INDEX arctic_ivfflat_idx ON emb_1024
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 5000);
```

## Long-term Strategy

Once you rebuild the index properly:

1. **Pure vector search** will work at acceptable speeds (30-60s)
2. **No need for keyword hacks** - the index will be fast enough
3. **Generalizable** - works for any medical question
4. **Scalable** - can handle growth to 50-60M vectors

The hybrid search approach was a good idea to work around the slow index, but it's not a sustainable solution for a general medical search system.
