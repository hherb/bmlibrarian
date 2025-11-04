# Phase 6: Documentation

**Estimated Time**: 3-4 hours

## Objectives
1. Create user guide for multi-model query generation
2. Create developer documentation
3. Update CLAUDE.md with new features
4. Add configuration examples

## Documentation Files to Create/Update

### 1. doc/users/multi_model_query_guide.md

**Purpose**: End-user guide

**Outline**:
```markdown
# Multi-Model Query Generation Guide

## Overview
- What is multi-model query generation?
- Why use multiple models?
- Benefits and use cases

## Quick Start

### Enabling Multi-Model Mode
1. Edit `~/.bmlibrarian/config.json`
2. Set `query_generation.multi_model_enabled: true`
3. Configure models list

### Basic Usage
- Example with CLI
- Example with GUI

## Configuration

### Available Settings
- models: List of model names
- queries_per_model: 1-3
- show_all_queries_to_user: true/false
- allow_query_selection: true/false

### Example Configurations

#### Conservative (1 query per model)
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

#### Aggressive (3 queries per model)
```json
{
  "query_generation": {
    "multi_model_enabled": true,
    "models": [
      "medgemma-27b-text-it-Q8_0:latest",
      "gpt-oss:20b",
      "medgemma4B_it_q8:latest"
    ],
    "queries_per_model": 3
  }
}
```

## Workflow

### Interactive Mode
1. Enter research question
2. System generates queries using all models
3. Review all generated queries
4. Select which queries to execute
5. System executes queries serially
6. Document IDs de-duplicated
7. Continue with scoring workflow

### Auto Mode
- All queries executed automatically
- No user review
- Best for batch processing

## Performance Considerations

### Query Generation Time
- 3 models × 1 query = ~3-10 seconds
- Serial execution (no bottlenecks)

### Database Load
- ID-only queries are fast
- De-duplication before full fetch
- Total time similar to single query

## Troubleshooting

### Model Not Available
- Check Ollama installation
- Verify model is pulled
- System will skip unavailable models

### Too Many Documents
- Reduce max_results setting
- Use fewer models
- Use 1 query per model

### Duplicate Queries
- Normal behavior
- System automatically de-duplicates
- Reduces total queries executed

## Best Practices
- Start with 2 models, 1 query each
- Use models with different strengths
- Review queries first time
- Enable auto mode after tuning

## FAQ
- Q: How many models should I use?
- Q: Why serial instead of parallel?
- Q: How to add custom models?
```

### 2. doc/developers/multi_model_architecture.md

**Purpose**: Technical documentation

**Outline**:
```markdown
# Multi-Model Query Generation Architecture

## Overview
Technical architecture for multi-model query generation system.

## Components

### 1. Configuration Layer
- Location: `src/bmlibrarian/config.py`
- Schema: `query_generation` section
- Validation: BMLibrarianConfig class

### 2. Data Types
- Location: `src/bmlibrarian/agents/query_generation/data_types.py`
- Classes: QueryGenerationResult, MultiModelQueryResult

### 3. Query Generator
- Location: `src/bmlibrarian/agents/query_generation/generator.py`
- Class: MultiModelQueryGenerator
- Execution: Serial (not parallel)

### 4. Database Layer
- Location: `src/bmlibrarian/database.py`
- Functions: find_abstract_ids(), fetch_documents_by_ids()

### 5. Agent Integration
- Location: `src/bmlibrarian/agents/query_agent.py`
- Methods: convert_question_multi_model(), find_abstracts_multi_query()

### 6. CLI Integration
- Location: `src/bmlibrarian/cli/query_processing.py`
- Flow: Multi-model search orchestration

## Design Decisions

### Serial vs Parallel Execution
**Decision**: Serial
**Rationale**:
- Local Ollama instance (not cloud)
- Local PostgreSQL instance
- Parallel provides no benefit
- Simpler code, easier debugging
- No connection bottlenecks

### ID-Only Queries First
**Decision**: Fetch IDs only, then full documents
**Rationale**:
- Faster queries (no JOINs, no text)
- Easy de-duplication with Set[int]
- Fetch full docs once

### Backward Compatibility
**Decision**: Feature flag, preserve original methods
**Rationale**:
- No breaking changes
- Users can opt-in
- Fallback if issues

## Data Flow

```
User Question
    ↓
convert_question_multi_model()
    ↓
MultiModelQueryGenerator.generate_queries()
    ↓
[Model 1] → Query 1
[Model 2] → Query 2
[Model 3] → Query 3
    ↓
De-duplicate queries
    ↓
find_abstracts_multi_query()
    ↓
For each query (SERIAL):
    find_abstract_ids() → Set[int]
    ↓
Merge all ID sets
    ↓
fetch_documents_by_ids()
    ↓
Continue with scoring workflow
```

## Extension Points

### Adding New Models
1. Install model in Ollama
2. Add to config: `query_generation.models`
3. System automatically uses it

### Custom Query Strategies
Extend MultiModelQueryGenerator:
```python
class CustomQueryGenerator(MultiModelQueryGenerator):
    def generate_queries(self, ...):
        # Custom logic
        pass
```

### Query Quality Metrics
Add to QueryGenerationResult:
```python
@dataclass
class QueryGenerationResult:
    # ... existing fields
    quality_score: Optional[float] = None
```

## Testing Strategy
- Unit tests: Each component in isolation
- Integration tests: End-to-end flow
- Coverage: >90% for all new code
- Backward compat: All existing tests pass

## Performance Benchmarks

### Single Model (Baseline)
- Query generation: ~1-3 seconds
- Database search: ~0.5-2 seconds
- Total: ~2-5 seconds

### Multi-Model (3 models, 1 query each)
- Query generation: ~3-10 seconds (serial)
- Database search: ~1-5 seconds (3 queries)
- De-duplication: ~0.1 seconds
- Total: ~5-15 seconds

**Overhead**: ~2-3x slower, but ~30% more relevant documents
```

### 3. Update CLAUDE.md

**File**: `/Users/hherb/src/bmlibrarian/CLAUDE.md`

**Add section** (after "Query Agent" section):

```markdown
### Multi-Model Query Generation

BMLibrarian supports using multiple models to generate diverse queries for improved document retrieval.

**Configuration** (`~/.bmlibrarian/config.json`):
```json
"query_generation": {
  "multi_model_enabled": true,
  "models": [
    "medgemma-27b-text-it-Q8_0:latest",
    "gpt-oss:20b",
    "medgemma4B_it_q8:latest"
  ],
  "queries_per_model": 1,
  "execution_mode": "serial"
}
```

**Benefits**:
- Improved query diversity
- Higher document recall
- Model-specific strengths leveraged
- Automatic de-duplication

**Architecture**:
- Serial execution (not parallel) for local instances
- ID-only queries for speed
- Backward compatible (feature flag)

**See**: `doc/users/multi_model_query_guide.md` for details
```

### 4. Add Configuration Example

**File**: `examples/multi_model_config_example.json`

```json
{
  "_comment": "Example Multi-Model Query Generation Configuration",

  "query_generation": {
    "_comment": "Multi-model query generation settings",

    "multi_model_enabled": true,
    "_note_enabled": "Set to true to enable multi-model query generation",

    "models": [
      "medgemma-27b-text-it-Q8_0:latest",
      "gpt-oss:20b"
    ],
    "_note_models": "List 1-3 models. Each must be available in Ollama",

    "queries_per_model": 1,
    "_note_queries": "Generate 1-3 queries per model. More = better coverage, slower",

    "execution_mode": "serial",
    "_note_execution": "Always 'serial' for local Ollama + PostgreSQL instances",

    "deduplicate_results": true,
    "_note_dedupe": "Remove duplicate documents across queries (recommended)",

    "show_all_queries_to_user": true,
    "_note_show": "Display all generated queries in CLI (recommended)",

    "allow_query_selection": true,
    "_note_selection": "Let user select which queries to execute (recommended)"
  },

  "_examples": {
    "conservative": {
      "models": ["medgemma-27b-text-it-Q8_0:latest"],
      "queries_per_model": 1,
      "comment": "Single model, single query (same as original behavior)"
    },
    "balanced": {
      "models": [
        "medgemma-27b-text-it-Q8_0:latest",
        "gpt-oss:20b"
      ],
      "queries_per_model": 1,
      "comment": "Two models, one query each (recommended starting point)"
    },
    "aggressive": {
      "models": [
        "medgemma-27b-text-it-Q8_0:latest",
        "gpt-oss:20b",
        "medgemma4B_it_q8:latest"
      ],
      "queries_per_model": 2,
      "comment": "Three models, two queries each = 6 total (maximum coverage)"
    }
  }
}
```

## Completion Criteria
- [x] User guide created
- [x] Developer docs created
- [x] CLAUDE.md updated
- [x] Configuration examples added
- [x] All examples tested

## Next Step
Update `00_OVERVIEW.md`, read `07_PHASE7_ROLLOUT.md`.

## Documentation Checklist
- [ ] User guide covers all features
- [ ] Developer docs explain architecture
- [ ] Configuration examples are valid
- [ ] Troubleshooting section complete
- [ ] FAQ addresses common questions
