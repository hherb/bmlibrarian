# Phase 1: Configuration System Updates

**Estimated Time**: 2-3 hours

## Objectives
1. Add `query_generation` config section to DEFAULT_CONFIG
2. Update BMLibrarianConfig to handle new settings
3. Add GUI configuration tab (optional, can defer)

## Files to Modify

### 1. src/bmlibrarian/config.py

**Location**: Lines 80-90 (after "search" section)

**Add this to DEFAULT_CONFIG**:
```python
"query_generation": {
    "multi_model_enabled": False,  # Feature flag - default disabled
    "models": [
        "medgemma-27b-text-it-Q8_0:latest"  # Default: single model
    ],
    "queries_per_model": 1,  # 1-3 queries per model
    "execution_mode": "serial",  # Always serial for local instances
    "deduplicate_results": True,
    "show_all_queries_to_user": True,  # Show all generated queries
    "allow_query_selection": True  # Let user pick which queries to run
}
```

**Add convenience function** (after line 335):
```python
def get_query_generation_config() -> Dict[str, Any]:
    """Get query generation configuration."""
    return get_config().get("query_generation", DEFAULT_CONFIG["query_generation"])
```

### 2. Update User's Config File (Optional)

**File**: `~/.bmlibrarian/config.json`

User can enable feature by setting:
```json
"query_generation": {
    "multi_model_enabled": true,
    "models": [
        "medgemma-27b-text-it-Q8_0:latest",
        "gpt-oss:20b",
        "medgemma4B_it_q8:latest"
    ]
}
```

## Testing Phase 1

### Manual Test
```python
from bmlibrarian.config import get_query_generation_config

config = get_query_generation_config()
print(config)
# Should print default config with multi_model_enabled: False
```

### Validation
- [ ] Config loads without errors
- [ ] Default values correct
- [ ] get_query_generation_config() works
- [ ] Backward compatible (no breaking changes)

## Completion Criteria
- [x] DEFAULT_CONFIG updated
- [x] Convenience function added
- [x] Manual test passes
- [x] No breaking changes to existing code

## Next Step
When Phase 1 complete, update `00_OVERVIEW.md` status, then read `02_PHASE2_CORE.md`.

## Key Files Reference
- Current: `src/bmlibrarian/config.py` (lines 1-335)
- User config: `~/.bmlibrarian/config.json`
