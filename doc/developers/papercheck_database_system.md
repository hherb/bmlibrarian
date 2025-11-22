# PaperChecker Database System - Developer Documentation

This document provides technical details about the PaperCheckDB class implementation for developers working on the BMLibrarian project.

## Architecture Overview

The PaperCheckDB class provides a dedicated database interface for the PaperChecker module, separate from the main DatabaseManager. This design allows:

1. **Schema isolation**: All PaperChecker data lives in the `papercheck` schema
2. **Specialized operations**: Methods tailored for fact-checking workflows
3. **Transaction management**: Complete results saved atomically
4. **Connection flexibility**: Support for both owned and external connections

## Module Structure

```
src/bmlibrarian/paperchecker/
├── __init__.py          # Exports PaperCheckDB
├── database.py          # PaperCheckDB implementation
├── data_models.py       # Data classes (Statement, Verdict, etc.)
├── agent.py             # PaperCheckerAgent
└── components/          # Workflow components
```

## Class Design

### PaperCheckDB

```python
class PaperCheckDB:
    """Database interface for PaperChecker result persistence."""

    # Constants
    DEFAULT_DB_NAME: str = "knowledgebase"
    DEFAULT_DB_HOST: str = "localhost"
    DEFAULT_DB_PORT: str = "5432"

    # Attributes
    conn: psycopg.Connection      # Database connection
    schema: str                    # Schema name ("papercheck")
    db_name: str                   # Database name
    db_host: str                   # Database host
    db_port: str                   # Database port
    _owns_connection: bool         # True if connection was created internally
```

### Initialization

The constructor supports three modes:

1. **Default mode**: Reads from environment variables
2. **Explicit parameters**: Override with provided values
3. **External connection**: Use an existing psycopg connection

```python
def __init__(
    self,
    connection: Optional[psycopg.Connection] = None,
    db_name: Optional[str] = None,
    db_user: Optional[str] = None,
    db_password: Optional[str] = None,
    db_host: Optional[str] = None,
    db_port: Optional[str] = None
) -> None:
```

The `_owns_connection` flag determines whether `close()` will actually close the connection. This prevents accidentally closing a shared connection.

## Database Schema

### Table: abstracts_checked

Primary table for checked abstracts.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PRIMARY KEY | Unique identifier |
| abstract_text | TEXT NOT NULL | Original abstract text |
| source_pmid | INTEGER | PubMed ID |
| source_doi | TEXT | DOI |
| source_title | TEXT | Paper title |
| source_metadata | JSONB | Additional source metadata |
| checked_at | TIMESTAMP | When the check was performed |
| model_used | VARCHAR(100) | LLM model used |
| config | JSONB | Processing configuration |
| overall_assessment | TEXT | Overall assessment text |
| processing_time_seconds | FLOAT | Total processing time |

### Table: statements

Extracted statements from abstracts.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PRIMARY KEY | Unique identifier |
| abstract_id | INTEGER FK | Reference to abstracts_checked |
| statement_text | TEXT NOT NULL | Extracted statement |
| context | TEXT | Surrounding context |
| statement_type | VARCHAR(50) | Type (finding/hypothesis/conclusion) |
| extraction_confidence | FLOAT | Extraction confidence (0-1) |
| statement_order | INTEGER | Position in abstract |

### Table: counter_statements

Generated counter-claims with search materials.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PRIMARY KEY | Unique identifier |
| statement_id | INTEGER FK | Reference to statements |
| negated_text | TEXT NOT NULL | Counter-claim text |
| hyde_abstracts | TEXT[] | Generated HyDE abstracts |
| keywords | TEXT[] | Search keywords |
| generation_metadata | JSONB | Generation parameters |

### Table: search_results

Multi-strategy search results with provenance.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PRIMARY KEY | Unique identifier |
| counter_statement_id | INTEGER FK | Reference to counter_statements |
| doc_id | INTEGER NOT NULL | Document ID from main database |
| search_strategy | VARCHAR(20) | Strategy (semantic/hyde/keyword) |
| search_rank | INTEGER | Rank within strategy results |
| search_score | FLOAT | Strategy-specific score |

### Table: scored_documents

Documents scored for relevance.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PRIMARY KEY | Unique identifier |
| counter_statement_id | INTEGER FK | Reference to counter_statements |
| doc_id | INTEGER NOT NULL | Document ID |
| relevance_score | INTEGER CHECK (1-5) | Relevance score |
| explanation | TEXT | Scoring explanation |
| supports_counter | BOOLEAN | Does it support counter-claim? |
| found_by | TEXT[] | Strategies that found it |

### Table: citations

Extracted citation passages.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PRIMARY KEY | Unique identifier |
| counter_statement_id | INTEGER FK | Reference to counter_statements |
| doc_id | INTEGER NOT NULL | Document ID |
| passage | TEXT NOT NULL | Extracted passage |
| relevance_score | INTEGER | Document relevance score |
| full_citation | TEXT | Formatted citation (AMA style) |
| metadata | JSONB | Citation metadata (PMID, DOI, etc.) |
| citation_order | INTEGER | Order in report |

### Table: counter_reports

Synthesized counter-evidence reports.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PRIMARY KEY | Unique identifier |
| counter_statement_id | INTEGER FK | Reference to counter_statements |
| report_text | TEXT NOT NULL | Markdown report text |
| num_citations | INTEGER | Number of citations |
| search_stats | JSONB | Search statistics |
| generation_metadata | JSONB | Generation parameters |
| generated_at | TIMESTAMP | Generation timestamp |

### Table: verdicts

Final verdicts on statements.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PRIMARY KEY | Unique identifier |
| statement_id | INTEGER FK | Reference to statements |
| verdict | VARCHAR(20) CHECK | Verdict value |
| rationale | TEXT NOT NULL | Verdict rationale |
| confidence | VARCHAR(20) CHECK | Confidence level |
| analysis_metadata | JSONB | Analysis parameters |
| generated_at | TIMESTAMP | Verdict timestamp |

## Transaction Management

The `save_complete_result` method saves all data atomically:

```python
def save_complete_result(self, result: PaperCheckResult) -> int:
    try:
        with self.conn.cursor() as cur:
            # 1. Insert abstract -> get abstract_id
            # 2. For each statement:
            #    - Insert statement -> get statement_id
            #    - Insert counter_statement -> get counter_stmt_id
            #    - Insert search_results (batch)
            #    - Insert scored_documents (batch)
            #    - Insert citations (batch)
            #    - Insert counter_report
            #    - Insert verdict
            self.conn.commit()
            return abstract_id
    except Exception as e:
        self.conn.rollback()
        raise
```

Key design decisions:
- **Single transaction**: All-or-nothing save prevents partial data
- **Explicit commit**: Only commits after all inserts succeed
- **Rollback on error**: Any error triggers rollback

## Index Strategy

Indexes are created for common query patterns:

```sql
-- Lookup by source identifiers
CREATE INDEX idx_abstracts_pmid ON papercheck.abstracts_checked(source_pmid);
CREATE INDEX idx_abstracts_doi ON papercheck.abstracts_checked(source_doi);

-- Foreign key traversal
CREATE INDEX idx_statements_abstract ON papercheck.statements(abstract_id);
CREATE INDEX idx_search_results_counter ON papercheck.search_results(counter_statement_id);
CREATE INDEX idx_verdicts_statement ON papercheck.verdicts(statement_id);
```

## Error Handling

All public methods follow consistent error handling:

```python
def method_name(self, param: Type) -> ReturnType:
    try:
        # Database operations
        ...
        return result
    except Exception as e:
        logger.error(f"Failed to [operation]: {e}")
        return default_value  # or raise
```

For methods that modify data:
- Errors are logged with full context
- Transactions are rolled back
- Exceptions are re-raised for caller handling

For read-only methods:
- Errors are logged
- Safe defaults are returned (empty lists, None, etc.)

## Testing Strategy

### Unit Tests

Test with mocked connections for fast execution:

```python
def test_init_uses_environment_variables():
    with patch.dict(os.environ, {"POSTGRES_DB": "test_db"}):
        with patch("psycopg.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn

            db = PaperCheckDB()
            assert db.db_name == "test_db"
```

### Integration Tests

Test with real database (dev database):

```python
@pytest.mark.database
def test_save_and_retrieve(db_connection):
    result = create_sample_result()
    abstract_id = db_connection.save_complete_result(result)

    retrieved = db_connection.get_result_by_id(abstract_id)
    assert retrieved is not None

    # Cleanup
    db_connection.delete_result(abstract_id)
```

### Running Tests

```bash
# Run unit tests only
uv run pytest tests/test_papercheck_database.py -v -m "not database"

# Run integration tests (requires database)
uv run pytest tests/test_papercheck_database.py -v --run-database-tests
```

## Golden Rule Compliance

This module adheres to the project's golden rules:

1. **Input validation**: All parameters are validated before use
2. **No magic numbers**: Uses constants for default values
3. **No hardcoded paths**: Uses environment variables for configuration
4. **Type hints**: All parameters and return types are annotated
5. **Docstrings**: All public methods have comprehensive docstrings
6. **Error handling**: All errors are caught, logged, and handled appropriately
7. **No truncation**: Full data is preserved without arbitrary limits
8. **Testing**: Comprehensive unit and integration tests
9. **Documentation**: User and developer documentation provided

## Performance Considerations

### Connection Management

- Use context managers for automatic cleanup
- Don't create new connections for every operation
- Consider connection pooling for high-throughput scenarios

### Query Optimization

- All queries use parameterized statements (no SQL injection risk)
- Batch inserts used for multiple records
- Indexes support common query patterns

### Memory Management

- Large results are streamed where possible
- Limit/offset pagination prevents loading entire tables

## Future Improvements

Potential enhancements for future development:

1. **Connection pooling**: Integrate with main DatabaseManager pool
2. **Caching**: Cache frequently-accessed results
3. **Bulk operations**: Add bulk save/delete methods
4. **Search**: Add full-text search on abstracts and statements
5. **Analytics**: Add aggregate query methods for analysis
6. **Migration support**: Add schema migration framework

## Related Documentation

- [User Guide](../users/papercheck_database_guide.md) - End-user documentation
- [Data Models](papercheck_data_models.md) - Data class documentation
- [Agent System](papercheck_agent_system.md) - Workflow agent documentation
