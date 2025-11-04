# Phase 5: Testing

**Estimated Time**: 4-6 hours

## Objectives
1. Write comprehensive unit tests
2. Write integration tests
3. Achieve >90% code coverage
4. Verify backward compatibility

## Test Files to Create

### 1. tests/test_query_generation_data_types.py

**Purpose**: Test data classes

```python
import pytest
from bmlibrarian.agents.query_generation.data_types import (
    QueryGenerationResult, MultiModelQueryResult
)

def test_query_generation_result_creation():
    """Test QueryGenerationResult creation."""
    result = QueryGenerationResult(
        model="test-model",
        query="test & query",
        generation_time=0.5,
        temperature=0.1,
        attempt_number=1
    )
    assert result.model == "test-model"
    assert result.query == "test & query"
    assert result.error is None

def test_multi_model_query_result():
    """Test MultiModelQueryResult aggregation."""
    # Create test data and verify counts
    pass
```

### 2. tests/test_multi_model_generator.py

**Purpose**: Test serial query generation

```python
import pytest
from bmlibrarian.agents.query_generation.generator import MultiModelQueryGenerator

def test_single_model_single_query():
    """Test 1 model, 1 query (backward compatible)."""
    generator = MultiModelQueryGenerator("http://localhost:11434")
    result = generator.generate_queries(
        question="test question",
        system_prompt="test prompt",
        models=["medgemma4B_it_q8:latest"],
        queries_per_model=1
    )

    assert result.model_count == 1
    assert result.total_queries == 1
    assert len(result.unique_queries) == 1

def test_multi_model_serial_execution():
    """Test 3 models, 1 query each = 3 queries."""
    generator = MultiModelQueryGenerator("http://localhost:11434")
    result = generator.generate_queries(
        question="test question",
        system_prompt="test prompt",
        models=["model1", "model2", "model3"],
        queries_per_model=1
    )

    assert result.model_count == 3
    assert result.total_queries == 3

def test_query_deduplication():
    """Test duplicate queries are removed."""
    # Mock to generate same query twice
    # Verify unique_queries has only one
    pass

def test_multiple_queries_per_model():
    """Test 2 models, 2 queries each = 4 total."""
    pass

def test_error_handling():
    """Test behavior when model fails."""
    # Mock Ollama failure
    # Verify graceful error handling
    pass
```

### 3. tests/test_database_multi_query.py

**Purpose**: Test database functions

```python
import pytest
from bmlibrarian.database import find_abstract_ids, fetch_documents_by_ids

def test_find_abstract_ids():
    """Test ID-only query returns Set[int]."""
    ids = find_abstract_ids("aspirin & heart", max_rows=10)

    assert isinstance(ids, set)
    assert all(isinstance(i, int) for i in ids)
    assert len(ids) <= 10

def test_fetch_documents_by_ids():
    """Test bulk document fetch."""
    # First get some IDs
    ids = find_abstract_ids("diabetes", max_rows=5)

    # Fetch documents
    docs = fetch_documents_by_ids(ids)

    assert len(docs) == len(ids)
    assert all('id' in doc for doc in docs)

    # Verify IDs match
    fetched_ids = {doc['id'] for doc in docs}
    assert fetched_ids == ids

def test_empty_id_set():
    """Test fetch with empty ID set."""
    docs = fetch_documents_by_ids(set())
    assert docs == []

def test_large_id_set_batching():
    """Test batching with >50 IDs."""
    # Create large ID set
    large_ids = set(range(1, 101))

    # Should batch automatically
    docs = fetch_documents_by_ids(large_ids, batch_size=25)
    # Verify no errors (some IDs may not exist)
    assert isinstance(docs, list)
```

### 4. tests/test_query_agent_multi_model.py

**Purpose**: Test QueryAgent multi-model methods

```python
import pytest
from bmlibrarian.agents import QueryAgent

def test_convert_question_multi_model_disabled():
    """Test fallback when multi-model disabled."""
    agent = QueryAgent()
    result = agent.convert_question_multi_model("test question")

    # Should return single query result
    assert result.model_count == 1
    assert result.total_queries == 1

def test_convert_question_multi_model_enabled():
    """Test with multi-model enabled."""
    # Mock config to enable multi-model
    # Verify multiple queries generated
    pass

def test_find_abstracts_multi_query():
    """Test multi-query document search."""
    agent = QueryAgent()

    # Mock config
    # Execute search
    # Verify de-duplication
    pass

def test_backward_compatibility():
    """Test original methods still work."""
    agent = QueryAgent()

    # Test convert_question()
    query = agent.convert_question("test question")
    assert isinstance(query, str)

    # Test find_abstracts()
    docs = list(agent.find_abstracts("test question", max_rows=5))
    assert len(docs) <= 5
```

### 5. tests/test_cli_multi_query_integration.py

**Purpose**: Test CLI integration

```python
import pytest
from bmlibrarian.cli import QueryProcessor, UserInterface, CLIConfig

def test_single_model_search():
    """Test backward compatible single-model search."""
    # Verify original behavior preserved
    pass

def test_multi_model_search_orchestration():
    """Test multi-model search flow."""
    # Mock multi-model config
    # Verify query generation -> execution -> dedup
    pass

def test_query_selection_ui():
    """Test query selection interface."""
    # Test user can select queries
    pass

def test_query_editing_ui():
    """Test query editing interface."""
    # Test user can edit queries
    pass
```

## Running Tests

### Run All Tests
```bash
uv run python -m pytest tests/ -v
```

### Run Specific Test File
```bash
uv run python -m pytest tests/test_multi_model_generator.py -v
```

### Run with Coverage
```bash
uv run python -m pytest tests/ --cov=bmlibrarian.agents.query_generation --cov-report=html
```

### Target Coverage
- **query_generation module**: >95%
- **database functions**: >90%
- **query_agent multi-model**: >90%
- **cli integration**: >85%

## Test Matrix

| Component | Test Type | Coverage Target |
|-----------|-----------|----------------|
| Data types | Unit | 100% |
| Generator | Unit | 95% |
| Database | Unit | 90% |
| QueryAgent | Unit | 90% |
| CLI | Integration | 85% |

## Completion Criteria
- [x] All unit tests written
- [x] All integration tests written
- [x] Coverage targets met
- [x] Backward compatibility verified
- [x] No regressions in existing tests

## Next Step
Update `00_OVERVIEW.md`, read `06_PHASE6_DOCS.md`.

## Key Testing Notes
- **Mock Ollama**: Use mocks to avoid hitting real API during tests
- **Test database**: Use test database or mock connections
- **Backward compat**: Verify all existing tests still pass
- **Error cases**: Test model failures, network errors, etc.
