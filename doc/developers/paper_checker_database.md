# PaperChecker Database Schema

## Overview

PaperChecker uses PostgreSQL for result persistence, storing all fact-checking results in the `papercheck` schema. This document describes the database structure, relationships, and access patterns.

## Schema: `papercheck`

All PaperChecker tables reside in the `papercheck` schema, separate from the main BMLibrarian `public` schema.

## Entity-Relationship Diagram

```
┌─────────────────────┐
│ abstracts_checked   │
│ (main entry point)  │
└─────────┬───────────┘
          │1
          │
          │*
┌─────────▼───────────┐
│ statements          │
│ (extracted claims)  │
└────────┬────────────┘
         │1
    ┌────┴────┐
    │         │1
    │*        │
┌───▼───┐  ┌──▼──────────────┐
│verdicts│  │counter_statements│
└────────┘  └────────┬────────┘
                     │1
         ┌───────────┼───────────┐
         │           │           │
         │*          │*          │*
┌────────▼──┐ ┌──────▼──────┐ ┌──▼───────────┐
│search_    │ │scored_      │ │counter_      │
│results    │ │documents    │ │reports       │
└───────────┘ └─────────────┘ └──────┬───────┘
                                     │1
                                     │
                                     │*
                              ┌──────▼───────┐
                              │citations     │
                              └──────────────┘
```

## Tables

### `abstracts_checked`

Main entry point for all abstract checks. One record per abstract analyzed.

```sql
CREATE TABLE papercheck.abstracts_checked (
    id SERIAL PRIMARY KEY,
    abstract_text TEXT NOT NULL,
    source_pmid INTEGER,
    source_doi TEXT,
    source_title TEXT,
    source_metadata JSONB DEFAULT '{}',
    checked_at TIMESTAMP DEFAULT NOW(),
    model_used VARCHAR(100),
    config JSONB,
    overall_assessment TEXT,
    processing_time_seconds FLOAT
);
```

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL | Primary key |
| `abstract_text` | TEXT | Full abstract text |
| `source_pmid` | INTEGER | PubMed ID (optional) |
| `source_doi` | TEXT | DOI (optional) |
| `source_title` | TEXT | Paper title (optional) |
| `source_metadata` | JSONB | Additional metadata (authors, journal, etc.) |
| `checked_at` | TIMESTAMP | When the check was performed |
| `model_used` | VARCHAR(100) | LLM model used |
| `config` | JSONB | Configuration used for this check |
| `overall_assessment` | TEXT | Final overall assessment |
| `processing_time_seconds` | FLOAT | Total processing time |

### `statements`

Extracted statements from abstracts.

```sql
CREATE TABLE papercheck.statements (
    id SERIAL PRIMARY KEY,
    abstract_id INTEGER REFERENCES papercheck.abstracts_checked(id) ON DELETE CASCADE,
    statement_text TEXT NOT NULL,
    context TEXT,
    statement_type VARCHAR(50),
    extraction_confidence FLOAT,
    statement_order INTEGER
);
```

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL | Primary key |
| `abstract_id` | INTEGER | FK to abstracts_checked |
| `statement_text` | TEXT | Extracted statement |
| `context` | TEXT | Surrounding context |
| `statement_type` | VARCHAR(50) | "hypothesis", "finding", "conclusion" |
| `extraction_confidence` | FLOAT | 0.0-1.0 confidence |
| `statement_order` | INTEGER | Position in abstract |

### `counter_statements`

Counter-claims with search materials.

```sql
CREATE TABLE papercheck.counter_statements (
    id SERIAL PRIMARY KEY,
    statement_id INTEGER REFERENCES papercheck.statements(id) ON DELETE CASCADE,
    negated_text TEXT NOT NULL,
    hyde_abstracts TEXT[],
    keywords TEXT[],
    generation_metadata JSONB DEFAULT '{}'
);
```

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL | Primary key |
| `statement_id` | INTEGER | FK to statements |
| `negated_text` | TEXT | Counter-claim text |
| `hyde_abstracts` | TEXT[] | Generated hypothetical abstracts |
| `keywords` | TEXT[] | Search keywords |
| `generation_metadata` | JSONB | Model, timestamp, parameters |

### `search_results`

Document IDs from multi-strategy search.

```sql
CREATE TABLE papercheck.search_results (
    id SERIAL PRIMARY KEY,
    counter_statement_id INTEGER REFERENCES papercheck.counter_statements(id) ON DELETE CASCADE,
    doc_id INTEGER NOT NULL,
    search_strategy VARCHAR(20) NOT NULL,
    search_rank INTEGER,
    search_score FLOAT
);
```

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL | Primary key |
| `counter_statement_id` | INTEGER | FK to counter_statements |
| `doc_id` | INTEGER | Document ID from main database |
| `search_strategy` | VARCHAR(20) | "semantic", "hyde", "keyword" |
| `search_rank` | INTEGER | Rank within strategy results |
| `search_score` | FLOAT | Search similarity score |

### `scored_documents`

Documents with relevance scores.

```sql
CREATE TABLE papercheck.scored_documents (
    id SERIAL PRIMARY KEY,
    counter_statement_id INTEGER REFERENCES papercheck.counter_statements(id) ON DELETE CASCADE,
    doc_id INTEGER NOT NULL,
    relevance_score INTEGER CHECK (relevance_score BETWEEN 1 AND 5),
    explanation TEXT,
    supports_counter BOOLEAN,
    found_by TEXT[]
);
```

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL | Primary key |
| `counter_statement_id` | INTEGER | FK to counter_statements |
| `doc_id` | INTEGER | Document ID from main database |
| `relevance_score` | INTEGER | 1-5 relevance score |
| `explanation` | TEXT | Score explanation |
| `supports_counter` | BOOLEAN | True if score >= threshold |
| `found_by` | TEXT[] | Search strategies that found this doc |

### `citations`

Extracted citation passages.

```sql
CREATE TABLE papercheck.citations (
    id SERIAL PRIMARY KEY,
    counter_statement_id INTEGER REFERENCES papercheck.counter_statements(id) ON DELETE CASCADE,
    doc_id INTEGER NOT NULL,
    passage TEXT NOT NULL,
    relevance_score INTEGER,
    full_citation TEXT,
    metadata JSONB DEFAULT '{}',
    citation_order INTEGER
);
```

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL | Primary key |
| `counter_statement_id` | INTEGER | FK to counter_statements |
| `doc_id` | INTEGER | Document ID from main database |
| `passage` | TEXT | Extracted text passage |
| `relevance_score` | INTEGER | Document's relevance score |
| `full_citation` | TEXT | AMA-formatted citation |
| `metadata` | JSONB | PMID, DOI, authors, year, journal |
| `citation_order` | INTEGER | Order in counter-report |

### `counter_reports`

Synthesized counter-evidence reports.

```sql
CREATE TABLE papercheck.counter_reports (
    id SERIAL PRIMARY KEY,
    counter_statement_id INTEGER REFERENCES papercheck.counter_statements(id) ON DELETE CASCADE,
    report_text TEXT NOT NULL,
    num_citations INTEGER,
    search_stats JSONB DEFAULT '{}',
    generation_metadata JSONB DEFAULT '{}',
    generated_at TIMESTAMP DEFAULT NOW()
);
```

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL | Primary key |
| `counter_statement_id` | INTEGER | FK to counter_statements |
| `report_text` | TEXT | Markdown prose report |
| `num_citations` | INTEGER | Number of citations |
| `search_stats` | JSONB | Documents found/scored/cited |
| `generation_metadata` | JSONB | Model, timestamp, parameters |
| `generated_at` | TIMESTAMP | Report generation time |

### `verdicts`

Final verdicts for statements.

```sql
CREATE TABLE papercheck.verdicts (
    id SERIAL PRIMARY KEY,
    statement_id INTEGER REFERENCES papercheck.statements(id) ON DELETE CASCADE,
    verdict VARCHAR(20) CHECK (verdict IN ('supports', 'contradicts', 'undecided')),
    rationale TEXT NOT NULL,
    confidence VARCHAR(20) CHECK (confidence IN ('high', 'medium', 'low')),
    analysis_metadata JSONB DEFAULT '{}',
    generated_at TIMESTAMP DEFAULT NOW()
);
```

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL | Primary key |
| `statement_id` | INTEGER | FK to statements |
| `verdict` | VARCHAR(20) | "supports", "contradicts", "undecided" |
| `rationale` | TEXT | 2-3 sentence explanation |
| `confidence` | VARCHAR(20) | "high", "medium", "low" |
| `analysis_metadata` | JSONB | Model, timestamp, parameters |
| `generated_at` | TIMESTAMP | Verdict generation time |

## Indexes

The migration system creates these performance indexes:

```sql
-- Abstract lookup
CREATE INDEX idx_abstracts_pmid ON papercheck.abstracts_checked(source_pmid);
CREATE INDEX idx_abstracts_checked_at ON papercheck.abstracts_checked(checked_at DESC);

-- Statement relationships
CREATE INDEX idx_statements_abstract_id ON papercheck.statements(abstract_id);
CREATE INDEX idx_counter_statements_statement_id ON papercheck.counter_statements(statement_id);

-- Search result analysis
CREATE INDEX idx_search_results_counter_id ON papercheck.search_results(counter_statement_id);
CREATE INDEX idx_search_results_strategy ON papercheck.search_results(search_strategy);

-- Verdict queries
CREATE INDEX idx_verdicts_statement_id ON papercheck.verdicts(statement_id);
CREATE INDEX idx_verdicts_verdict ON papercheck.verdicts(verdict);
```

## Access Patterns

### PaperCheckDB Class

The `PaperCheckDB` class provides the primary interface:

```python
from bmlibrarian.paperchecker.database import PaperCheckDB

with PaperCheckDB() as db:
    # Save complete result
    abstract_id = db.save_complete_result(paper_check_result)

    # Retrieve result
    result = db.get_result_by_id(abstract_id)

    # List recent checks
    recent = db.list_recent_checks(limit=10)

    # Get statistics
    stats = db.get_statistics()
```

### Common Queries

**List recent checks:**
```sql
SELECT
    a.id,
    a.source_pmid,
    a.source_title,
    a.checked_at,
    a.overall_assessment,
    (SELECT COUNT(*) FROM papercheck.statements s WHERE s.abstract_id = a.id) as num_statements
FROM papercheck.abstracts_checked a
ORDER BY a.checked_at DESC
LIMIT 100;
```

**Get verdicts for an abstract:**
```sql
SELECT
    s.statement_text,
    s.statement_type,
    v.verdict,
    v.rationale,
    v.confidence
FROM papercheck.statements s
JOIN papercheck.verdicts v ON v.statement_id = s.id
WHERE s.abstract_id = :abstract_id
ORDER BY s.statement_order;
```

**Verdict distribution:**
```sql
SELECT verdict, COUNT(*) as count
FROM papercheck.verdicts
GROUP BY verdict;
```

**Search strategy effectiveness:**
```sql
SELECT
    search_strategy,
    COUNT(*) as docs_found,
    COUNT(DISTINCT counter_statement_id) as statements_searched
FROM papercheck.search_results
GROUP BY search_strategy;
```

## Cascade Deletes

All tables use `ON DELETE CASCADE` for foreign keys. Deleting an abstract automatically removes:
- All statements
- All counter-statements
- All search results
- All scored documents
- All citations
- All counter-reports
- All verdicts

```python
# Single call deletes everything
db.delete_result(abstract_id)
```

## Schema Creation

The schema is created via:

1. **Migration system:** `migrations/010_create_papercheck_schema.sql`
2. **Programmatic:** `PaperCheckDB.ensure_schema()` (for testing/development)

```python
db = PaperCheckDB()
db.ensure_schema()  # Creates schema if not exists
```

## Backup Considerations

When backing up PaperChecker data:

```bash
# Backup papercheck schema only
pg_dump -n papercheck knowledgebase > papercheck_backup.sql

# Restore
psql knowledgebase < papercheck_backup.sql
```

## See Also

- [Architecture Documentation](paper_checker_architecture.md) - System design
- [Component Documentation](paper_checker_components.md) - Component details
- [API Reference](paper_checker_api_reference.md) - Complete API docs
