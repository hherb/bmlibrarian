# Multi-Model Query Generation - Implementation Overview

## Goal
Improve query quality by using multiple models (1-3) to generate queries, executing them serially, de-duplicating document IDs, then continuing with existing workflow.

## Key Design Decisions

### 1. Serial Execution (NOT Parallel)
- **Rationale**: Local Ollama + local PostgreSQL = serial is just as fast
- **Benefits**: Avoids memory/connection bottlenecks, simpler debugging
- **Implementation**: Use simple for-loops, not ThreadPoolExecutor

### 2. Configuration-Driven
- Models specified in `~/.bmlibrarian/config.json`
- Default: 1 model (backward compatible)
- Max: 3 models, 1-3 queries per model

### 3. ID-Only Search First
- Execute queries to get document IDs only (fast)
- De-duplicate IDs using Set[int]
- Fetch full documents once

### 4. Backward Compatible
- Feature flag: `query_generation.multi_model_enabled: false` (default)
- Original single-model code preserved
- No breaking changes

## Implementation Phases

Each phase has its own context file in this directory:

1. **01_PHASE1_CONFIG.md** - Configuration system updates (2-3 hrs)
2. **02_PHASE2_CORE.md** - Core query generation (6-8 hrs)
3. **03_PHASE3_DATABASE.md** - Database layer (3-4 hrs)
4. **04_PHASE4_CLI.md** - CLI integration (4-5 hrs)
5. **05_PHASE5_TESTS.md** - Testing (4-6 hrs)
6. **06_PHASE6_DOCS.md** - Documentation (3-4 hrs)
7. **07_PHASE7_ROLLOUT.md** - Migration (3-4 hrs)

## Current Status
- [x] Phase 1: Configuration
- [ ] Phase 2: Core Architecture
- [ ] Phase 3: Database Layer
- [ ] Phase 4: CLI Integration
- [ ] Phase 5: Testing
- [ ] Phase 6: Documentation
- [ ] Phase 7: Rollout

## Branch Strategy
```
master
  └── feature/multi-model-query-generation (all work here)
```

Keep it simple - one feature branch, merge when complete.

## Next Step
Read `01_PHASE1_CONFIG.md` and begin Phase 1.
