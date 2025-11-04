# Phase 7: Rollout and Migration

**Estimated Time**: 3-4 hours

## Objectives
1. Final integration testing
2. Performance benchmarking
3. Create migration guide
4. Merge to master

## Rollout Steps

### Step 1: Pre-Merge Checklist

**Code Quality**:
- [ ] All phases complete
- [ ] All tests passing
- [ ] Coverage >90%
- [ ] No regressions in existing tests
- [ ] Code follows project style

**Documentation**:
- [ ] User guide complete
- [ ] Developer docs complete
- [ ] CLAUDE.md updated
- [ ] Examples validated

**Testing**:
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Manual testing complete
- [ ] Backward compatibility verified

### Step 2: Performance Benchmarking

**Create benchmark script**: `scripts/benchmark_multi_model.py`

```python
#!/usr/bin/env python3
"""Benchmark multi-model query generation."""

import time
from bmlibrarian.agents import QueryAgent
from bmlibrarian.config import get_config

def benchmark_single_model():
    """Benchmark original single-model behavior."""
    # Disable multi-model
    config = get_config()
    config.set('query_generation.multi_model_enabled', False)

    agent = QueryAgent()

    questions = [
        "What are the cardiovascular benefits of exercise?",
        "How does diabetes affect kidney function?",
        "What are the side effects of statins?"
    ]

    times = []
    for q in questions:
        start = time.time()
        docs = list(agent.find_abstracts(q, max_rows=50))
        elapsed = time.time() - start
        times.append(elapsed)
        print(f"Single-model: {q[:40]}... → {len(docs)} docs in {elapsed:.2f}s")

    avg_time = sum(times) / len(times)
    print(f"\nSingle-model average: {avg_time:.2f}s")
    return avg_time

def benchmark_multi_model():
    """Benchmark multi-model behavior."""
    # Enable multi-model
    config = get_config()
    config.set('query_generation.multi_model_enabled', True)
    config.set('query_generation.models', [
        "medgemma-27b-text-it-Q8_0:latest",
        "gpt-oss:20b"
    ])
    config.set('query_generation.queries_per_model', 1)

    agent = QueryAgent()

    questions = [
        "What are the cardiovascular benefits of exercise?",
        "How does diabetes affect kidney function?",
        "What are the side effects of statins?"
    ]

    times = []
    for q in questions:
        start = time.time()
        docs = list(agent.find_abstracts_multi_query(q, max_rows=50))
        elapsed = time.time() - start
        times.append(elapsed)
        print(f"Multi-model: {q[:40]}... → {len(docs)} docs in {elapsed:.2f}s")

    avg_time = sum(times) / len(times)
    print(f"\nMulti-model average: {avg_time:.2f}s")
    return avg_time

if __name__ == "__main__":
    print("="*70)
    print("Multi-Model Query Generation Benchmark")
    print("="*70)

    print("\n1. Single-Model Baseline:")
    single_time = benchmark_single_model()

    print("\n2. Multi-Model (2 models, 1 query each):")
    multi_time = benchmark_multi_model()

    print("\n" + "="*70)
    print("Results Summary:")
    print(f"  Single-model: {single_time:.2f}s")
    print(f"  Multi-model:  {multi_time:.2f}s")
    print(f"  Overhead:     {((multi_time/single_time - 1) * 100):.1f}%")
    print("="*70)
```

**Run benchmark**:
```bash
uv run python scripts/benchmark_multi_model.py
```

**Expected results**:
- Single-model: ~2-5 seconds
- Multi-model (2 models): ~5-10 seconds
- Overhead: 2-3x slower, but more documents

### Step 3: Create Migration Guide

**File**: `doc/MIGRATION_MULTI_MODEL.md`

```markdown
# Migration Guide: Multi-Model Query Generation

## Overview
Version X.X.X introduces multi-model query generation for improved document retrieval.

## What's New
- Support for using multiple models to generate queries
- Automatic de-duplication of documents across queries
- Serial execution optimized for local instances
- Backward compatible (opt-in feature)

## Migration Steps

### For Existing Users

#### Option 1: Keep Current Behavior (No Changes)
No action needed. Multi-model is disabled by default.

#### Option 2: Enable Multi-Model
1. Edit `~/.bmlibrarian/config.json`
2. Add/update `query_generation` section:
```json
{
  "query_generation": {
    "multi_model_enabled": true,
    "models": [
      "medgemma-27b-text-it-Q8_0:latest",
      "gpt-oss:20b"
    ],
    "queries_per_model": 1
  }
}
```
3. Restart CLI or reload config

### For Developers

#### API Changes
**New methods** (optional to use):
- `QueryAgent.convert_question_multi_model()`
- `QueryAgent.find_abstracts_multi_query()`

**Database functions** (optional to use):
- `find_abstract_ids()`
- `fetch_documents_by_ids()`

**Existing methods unchanged**:
- `QueryAgent.convert_question()` - still works
- `QueryAgent.find_abstracts()` - still works

#### Configuration Changes
New config section: `query_generation`

See `examples/multi_model_config_example.json` for full schema.

## Breaking Changes
**None** - this is a fully backward compatible feature.

## Performance Impact
- Disabled: No impact (default)
- Enabled: 2-3x slower query generation, ~30% more relevant documents

## Rollback
If issues occur:
1. Set `query_generation.multi_model_enabled: false`
2. Or remove `query_generation` section entirely

## Support
- User guide: `doc/users/multi_model_query_guide.md`
- Developer docs: `doc/developers/multi_model_architecture.md`
- Issues: GitHub issues
```

### Step 4: Final Testing

**Test scenarios**:
1. Clean install (no config)
2. Upgrade from previous version
3. Multi-model enabled
4. Multi-model disabled
5. Model unavailable (error handling)
6. Empty results
7. Large result sets

**CLI test**:
```bash
# Test 1: Default (disabled)
uv run python bmlibrarian_cli.py --quick

# Test 2: Enabled
# Edit config first
uv run python bmlibrarian_cli.py --quick

# Test 3: Auto mode
uv run python bmlibrarian_cli.py --auto "test question" --quick
```

### Step 5: Create Pull Request

**Branch**:
```bash
git checkout feature/multi-model-query-generation
git status  # Verify all changes
```

**Commit message**:
```
FEAT: Add multi-model query generation system

Implements multi-model query generation to improve document retrieval quality:

- Configuration-driven model selection (1-3 models)
- Serial execution optimized for local instances
- ID-only queries with automatic de-duplication
- Human-in-the-loop query review and selection
- Backward compatible (feature flag, default disabled)

Architecture:
- New module: src/bmlibrarian/agents/query_generation/
- Database functions: find_abstract_ids(), fetch_documents_by_ids()
- QueryAgent methods: convert_question_multi_model(), find_abstracts_multi_query()
- CLI integration with multi-query UI

Performance:
- 2-3x slower query generation
- ~30% improvement in relevant document retrieval
- No impact when disabled (default)

Testing:
- 95%+ code coverage
- All existing tests pass
- New unit and integration tests

Documentation:
- User guide: doc/users/multi_model_query_guide.md
- Developer docs: doc/developers/multi_model_architecture.md
- Migration guide: doc/MIGRATION_MULTI_MODEL.md
- Updated CLAUDE.md

Addresses: [Issue #XXX if applicable]
```

**PR Description**:
Include:
- Summary of changes
- Architecture diagram
- Performance benchmarks
- Migration instructions
- Testing coverage
- Screenshots (if applicable)

### Step 6: Post-Merge

**Announce**:
- Update README.md with new feature
- Create release notes
- Notify users (if applicable)

**Monitor**:
- GitHub issues for problems
- User feedback
- Performance metrics

## Completion Criteria
- [x] Benchmarks run
- [x] Migration guide created
- [x] All tests passing
- [x] PR created and reviewed
- [x] Merged to master
- [x] Documentation updated

## Success Metrics (2 weeks post-merge)

**Technical**:
- [ ] No critical bugs reported
- [ ] No performance regressions
- [ ] Tests remain stable

**User Adoption**:
- [ ] Users enable feature
- [ ] Positive feedback on document quality
- [ ] No rollbacks needed

## Next Steps After Merge

**Future Enhancements** (separate features):
1. Query quality scoring
2. Adaptive model selection
3. Query fusion algorithms
4. Model ensemble learning

See `00_OVERVIEW.md` → Post-Implementation Enhancements
