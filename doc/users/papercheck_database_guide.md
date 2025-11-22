# PaperChecker Database Guide

This guide explains how to use the PaperCheckDB database interface for storing and retrieving fact-checking results from the PaperChecker module.

## Overview

The PaperCheckDB class provides persistent storage for all PaperChecker results in PostgreSQL. It manages the `papercheck` schema, which stores:

- Checked abstracts with source metadata
- Extracted statements from each abstract
- Counter-statements with search materials (HyDE abstracts, keywords)
- Multi-strategy search results with provenance tracking
- Scored documents with relevance explanations
- Extracted citations with full reference metadata
- Counter-evidence reports
- Final verdicts with confidence levels

## Prerequisites

Before using the database module, ensure you have:

1. **PostgreSQL** installed and running
2. **Database credentials** configured via environment variables:
   - `POSTGRES_DB` (default: "knowledgebase")
   - `POSTGRES_USER` (required)
   - `POSTGRES_PASSWORD` (required)
   - `POSTGRES_HOST` (default: "localhost")
   - `POSTGRES_PORT` (default: "5432")

3. **Environment setup** in `~/.bmlibrarian/.env`:
   ```bash
   POSTGRES_DB=knowledgebase
   POSTGRES_USER=your_username
   POSTGRES_PASSWORD=your_password
   POSTGRES_HOST=localhost
   POSTGRES_PORT=5432
   ```

## Quick Start

### Basic Usage

```python
from bmlibrarian.paperchecker import PaperCheckDB, PaperCheckerAgent

# Create database connection
db = PaperCheckDB()

# Verify connection and schema
if db.test_connection():
    print("Database connection successful!")
else:
    # Create schema if it doesn't exist
    db.ensure_schema()

# Run fact-checking workflow
agent = PaperCheckerAgent()
result = agent.check_abstract(
    abstract="Your abstract text here...",
    source_metadata={"pmid": 12345678}
)

# Save result to database
abstract_id = db.save_complete_result(result)
print(f"Result saved with ID: {abstract_id}")

# Close connection when done
db.close()
```

### Using Context Manager

For automatic connection management:

```python
from bmlibrarian.paperchecker import PaperCheckDB

with PaperCheckDB() as db:
    # Connection is automatically managed
    db.ensure_schema()

    # List recent checks
    recent = db.list_recent_checks(limit=10)
    for check in recent:
        print(f"ID: {check['id']}, PMID: {check['source_pmid']}")

# Connection is automatically closed when exiting the context
```

## Database Operations

### Saving Results

After running the PaperChecker workflow, save the complete result:

```python
from bmlibrarian.paperchecker import PaperCheckDB, PaperCheckResult

db = PaperCheckDB()

# result is a PaperCheckResult from PaperCheckerAgent
abstract_id = db.save_complete_result(result)
```

The `save_complete_result` method:
- Saves all data in a single transaction
- Returns the abstract ID (primary key)
- Rolls back automatically on errors

### Retrieving Results

**Get a specific result by ID:**

```python
result = db.get_result_by_id(abstract_id=123)

if result:
    print(f"Abstract: {result['abstract']['abstract_text'][:100]}...")
    print(f"Statements: {len(result['statements'])}")
```

**Get all results for a PMID:**

```python
results = db.get_results_by_pmid(pmid=12345678)

for r in results:
    print(f"Checked: {r['checked_at']}, Assessment: {r['overall_assessment']}")
```

**List recent checks:**

```python
recent = db.list_recent_checks(limit=20, offset=0)

for check in recent:
    print(f"ID: {check['id']}")
    print(f"  Title: {check['source_title']}")
    print(f"  Checked: {check['checked_at']}")
    print(f"  Statements: {check['num_statements']}")
    print(f"  Assessment: {check['overall_assessment']}")
```

### Getting Verdicts Summary

For a quick view of verdicts for an abstract:

```python
summary = db.get_verdicts_summary(abstract_id=123)

for stmt in summary:
    print(f"Statement: {stmt['statement_text'][:50]}...")
    print(f"  Verdict: {stmt['verdict']}")
    print(f"  Confidence: {stmt['confidence']}")
    print(f"  Citations: {stmt['num_citations']}")
```

### Database Statistics

Get an overview of all stored data:

```python
stats = db.get_statistics()

print(f"Total abstracts checked: {stats['total_abstracts']}")
print(f"Total statements analyzed: {stats['total_statements']}")
print(f"Recent activity (24h): {stats['recent_activity']}")

print("\nVerdicts breakdown:")
for verdict, count in stats['verdicts_breakdown'].items():
    print(f"  {verdict}: {count}")

print("\nConfidence breakdown:")
for confidence, count in stats['confidence_breakdown'].items():
    print(f"  {confidence}: {count}")
```

### Deleting Results

To remove a result and all related data:

```python
success = db.delete_result(abstract_id=123)

if success:
    print("Result deleted successfully")
else:
    print("Result not found or deletion failed")
```

Note: Deletion is cascading - all related statements, verdicts, citations, etc. are automatically removed.

## Database Schema

The `papercheck` schema contains the following tables:

| Table | Description |
|-------|-------------|
| `abstracts_checked` | Main table with abstract text and source metadata |
| `statements` | Extracted statements from each abstract |
| `counter_statements` | Counter-claims with HyDE abstracts and keywords |
| `search_results` | Multi-strategy search results with provenance |
| `scored_documents` | Documents with relevance scores (1-5) |
| `citations` | Extracted citation passages |
| `counter_reports` | Synthesized counter-evidence reports |
| `verdicts` | Final verdicts (supports/contradicts/undecided) |

### Schema Relationships

```
abstracts_checked (1) ─┬─► (N) statements (1) ─┬─► (1) counter_statements
                       │                        │
                       │                        ├─► (1) verdicts
                       │                        │
                       │   counter_statements (1) ─┬─► (N) search_results
                       │                           │
                       │                           ├─► (N) scored_documents
                       │                           │
                       │                           ├─► (N) citations
                       │                           │
                       │                           └─► (1) counter_reports
```

## Connection Configuration

### Using Environment Variables

The most common approach is to set environment variables:

```bash
export POSTGRES_DB=knowledgebase
export POSTGRES_USER=myuser
export POSTGRES_PASSWORD=mypassword
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
```

### Using Explicit Parameters

Override defaults with explicit parameters:

```python
db = PaperCheckDB(
    db_name="my_database",
    db_user="my_user",
    db_password="my_password",
    db_host="db.example.com",
    db_port="5432"
)
```

### Using an Existing Connection

If you have an existing psycopg connection:

```python
import psycopg

# Your existing connection
conn = psycopg.connect("dbname=knowledgebase user=myuser ...")

# Wrap it with PaperCheckDB
db = PaperCheckDB(connection=conn)

# Note: The connection will NOT be closed when db.close() is called
# since it was externally provided
```

## Error Handling

The database module provides comprehensive error handling:

```python
try:
    db = PaperCheckDB()

    if not db.test_connection():
        print("Connection failed - check credentials")
        return

    abstract_id = db.save_complete_result(result)
    print(f"Saved as {abstract_id}")

except Exception as e:
    print(f"Database error: {e}")

finally:
    db.close()
```

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| "Schema 'papercheck' does not exist" | Schema not created | Call `db.ensure_schema()` |
| "Database credentials not configured" | Missing env vars | Set POSTGRES_USER and POSTGRES_PASSWORD |
| "Connection refused" | PostgreSQL not running | Start PostgreSQL service |
| "Transaction rolled back" | Constraint violation | Check data integrity |

## Performance Tips

1. **Use context managers** for automatic connection cleanup
2. **Batch operations** when processing multiple abstracts
3. **Use limit/offset** for pagination when listing results
4. **Index usage**: The schema includes indexes on PMID, DOI, and foreign keys
5. **Connection pooling**: For high-throughput scenarios, consider using the main DatabaseManager

## See Also

- [PaperChecker Agent Guide](papercheck_agent_guide.md) - How to run the fact-checking workflow
- [Developer Documentation](../developers/papercheck_database_system.md) - Technical implementation details
- [Database Schema](../developers/papercheck_schema.md) - Complete schema reference
