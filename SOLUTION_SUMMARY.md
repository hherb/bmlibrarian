# Vector Search Optimization - Solution Summary

## The Problem

**Current performance**: 263 seconds per search query
**Root cause**: HNSW index with m=6 is too sparse for 37M embeddings
**Why hybrid search failed**: Even with keyword pre-filtering, the m=6 index is still too slow

## Your Options (in order of recommendation)

### Option 1: Test ef_search Parameter (TEST THIS FIRST)

**What**: Increase the query-time search depth parameter
**Time**: 1 second to test
**Risk**: None - it's just a query parameter

**Command**:
```bash
uv run python test_ef_search.py "your query"
```

**Expected outcome**:
- If it helps 20%+: Great! Use `SET hnsw.ef_search = 200;` in your queries
- If it helps <10%: Confirms m=6 is the bottleneck, need to rebuild

---

### Option 2: Rebuild with m=12 (RECOMMENDED IF TEST FAILS)

**What**: Rebuild HNSW index with better parameters
**Time**: 2-4 hours
**Disk**: +206 GB (you have 853 GB free)
**Performance**: **263s → 30-60s (5-10x faster)**

**Command**:
```bash
# Run during off-hours
psql knowledgebase -f rebuild_index_m12.sql
```

**Why m=12 instead of m=24?**
- m=12: 412 GB index (2x current)
- m=24: 824 GB index (4x current) - would use 72% of free space
- m=12 is a safe compromise with good performance improvement

**Pros**:
- ✅ 5-10x speedup
- ✅ Permanent fix
- ✅ Works for any medical query
- ✅ Manageable disk space

**Cons**:
- ⏱️ 2-4 hours downtime
- 💾 +206 GB disk space

---

### Option 3: Switch to IVFFlat (IF DISK/TIME CONSTRAINED)

**What**: Use a different index type that's faster to build
**Time**: 30-60 minutes
**Disk**: +50-100 GB (vs +206 GB for HNSW m=12)
**Performance**: **263s → 10-30s (8-25x faster)**

**Command**:
```bash
psql knowledgebase -f rebuild_index_ivfflat.sql
```

**Pros**:
- ✅ 8-25x speedup
- ✅ Much faster build (30-60 min vs 2-4 hours)
- ✅ Smaller index (50-100 GB vs 412 GB)
- ✅ Still very good performance

**Cons**:
- ⚠️ Slightly lower recall than HNSW m=12+
- ⚠️ Need to tune `probes` parameter per query type

---

## Decision Tree

```
Start: 263s queries with m=6 index
│
├─ Step 1: Test ef_search parameter
│  └─ Run: uv run python test_ef_search.py
│     │
│     ├─ If >20% improvement
│     │  └─ ✓ Use SET hnsw.ef_search = 200; in queries
│     │     Still slow but better than nothing
│     │
│     └─ If <10% improvement (likely)
│        └─ Proceed to Step 2
│
├─ Step 2: Check constraints
│  │
│  ├─ Have 2-4 hours downtime + 206 GB disk?
│  │  └─ YES → Option 2: rebuild_index_m12.sql
│  │     Expected: 263s → 30-60s
│  │
│  └─ Need faster solution or less disk space?
│     └─ YES → Option 3: rebuild_index_ivfflat.sql
│        Expected: 263s → 10-30s
```

## Files Created

**Testing & Analysis**:
- `test_ef_search.py` - Test if ef_search parameter helps
- `analyze_index.py` - Analyze current index configuration
- `estimate_disk_space.py` - Estimate disk space requirements

**Index Rebuild Scripts**:
- `rebuild_index_m12.sql` - Rebuild HNSW with m=12 (recommended)
- `rebuild_index_ivfflat.sql` - Switch to IVFFlat index (alternative)

**Documentation**:
- `REAL_SOLUTION.md` - Detailed explanation of the problem
- `PERFORMANCE_FINDINGS.md` - Analysis of your current setup
- `VECTOR_SEARCH_OPTIMIZATION.md` - Comprehensive optimization guide
- `SOLUTION_SUMMARY.md` - This file

**Search Scripts** (for reference, but not the solution):
- `semantic_search.py` - Original pure vector search
- `hybrid_search.py` - Keyword-based hybrid (not generalizable)
- `smart_hybrid_search.py` - Smart hybrid (not generalizable)

## Recommended Action Plan

### Today (5 minutes)
1. Run the ef_search test:
   ```bash
   uv run python test_ef_search.py "your typical query"
   ```
2. Review results - does it help significantly (>20%)?

### If ef_search doesn't help much (<10% improvement)

**Schedule during next maintenance window:**

**Option A** (Best performance, more resources):
```bash
# 2-4 hours, +206 GB disk
psql knowledgebase -f rebuild_index_m12.sql
```

**Option B** (Fast build, less disk):
```bash
# 30-60 min, +50-100 GB disk
psql knowledgebase -f rebuild_index_ivfflat.sql
```

## Why Hybrid Search Isn't The Answer

❌ **Problem with keyword-based hybrid search**:
- Medical terminology has many synonyms (mountain → altitude, high-elevation, etc.)
- Acronyms and abbreviations vary widely
- Drug names can be written multiple ways
- Keyword extraction isn't generalizable across all medical questions
- Even with good keywords, m=6 index is still too slow on filtered results

✅ **The real solution**:
- Fix the index itself (m=6 → m=12 or use IVFFlat)
- Makes pure semantic search fast enough (~30-60s)
- Works for ANY medical question without keyword engineering
- Generalizable and maintainable

## Expected Outcomes

| Solution | Query Time | Build Time | Disk Usage | Generalizability |
|----------|------------|------------|------------|------------------|
| Current (m=6) | 263s | - | 206 GB | ✓ |
| ef_search=200 | ~200-250s | 0 min | 206 GB | ✓ |
| HNSW m=12 | 30-60s | 2-4 hr | 412 GB | ✓ |
| HNSW m=24 | 10-30s | 4-8 hr | 824 GB | ✓ |
| IVFFlat | 10-30s | 30-60 min | 50-100 GB | ✓ |
| Hybrid (keywords) | varies | 0 min | 206 GB | ✗ Not generalizable |

## Questions?

- **"Can I just use better keywords?"** - No, medical terminology is too complex and varied
- **"What if I can't afford downtime?"** - IVFFlat builds faster (30-60 min vs 2-4 hours)
- **"Will m=12 be enough?"** - Should give 5-10x improvement (263s → 30-60s), which is acceptable
- **"Why not m=24?"** - Would work great but uses 618 GB extra (you have 853 GB free, too risky)
- **"Can I test before committing?"** - Yes! Run test_ef_search.py first to confirm m=6 is the issue

## Next Steps

1. **Run test_ef_search.py** to confirm the diagnosis
2. **Review the test results** - if <10% improvement, m=6 is confirmed as bottleneck
3. **Choose Option 2 or 3** based on your constraints
4. **Schedule the rebuild** during a maintenance window
5. **Test performance** after rebuild with semantic_search.py

The hybrid search experiments were valuable for learning, but the path forward is to fix the index itself.
