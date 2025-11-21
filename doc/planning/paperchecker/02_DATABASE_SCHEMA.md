# Step 2: Database Schema Design and Implementation

## Context

Data models (Step 1) are now defined. We need a PostgreSQL schema to persist all PaperChecker results for analysis, auditing, and future improvements.

## Objective

Create a comprehensive PostgreSQL schema (`papercheck`) that stores:
- Abstracts being checked
- All intermediate processing results
- Final verdicts and reports
- Metadata for reproducibility

## Requirements

- PostgreSQL >=12 with pgvector extension
- New schema `papercheck` (separate from `public` and `factcheck`)
- Foreign keys to main documents table
- Indexes for query performance
- Audit trails (timestamps, model info)

## Implementation Location

Create: `migrations/papercheck_schema.sql`

## Schema Design

### Core Principles

1. **Complete Audit Trail**: Every processing step recorded
2. **Reproducibility**: Store model, config, timestamps
3. **Referential Integrity**: Foreign keys to existing tables
4. **Query Performance**: Indexes on common queries
5. **Future Analysis**: JSONB for flexible metadata

### Schema Structure

```sql
-- Create dedicated schema for paper checking
CREATE SCHEMA IF NOT EXISTS papercheck;

-- Grant permissions
GRANT USAGE ON SCHEMA papercheck TO bmlibrarian_user;
GRANT ALL ON ALL TABLES IN SCHEMA papercheck TO bmlibrarian_user;
GRANT ALL ON ALL SEQUENCES IN SCHEMA papercheck TO bmlibrarian_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA papercheck
    GRANT ALL ON TABLES TO bmlibrarian_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA papercheck
    GRANT ALL ON SEQUENCES TO bmlibrarian_user;
```

### Table 1: abstracts_checked

```sql
CREATE TABLE papercheck.abstracts_checked (
    id SERIAL PRIMARY KEY,
    abstract_text TEXT NOT NULL CHECK (length(abstract_text) > 0),

    -- Source metadata (optional if checking external abstracts)
    source_pmid INTEGER,
    source_doi TEXT,
    source_title TEXT,
    source_authors TEXT[],
    source_year INTEGER,
    source_journal TEXT,

    -- Processing metadata
    checked_at TIMESTAMP DEFAULT NOW() NOT NULL,
    model_used VARCHAR(100) NOT NULL,
    config JSONB DEFAULT '{}'::jsonb,

    -- Results summary
    num_statements INTEGER,
    overall_assessment TEXT,
    processing_time_seconds FLOAT,

    -- Status tracking
    status VARCHAR(20) DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    error_message TEXT,

    UNIQUE(source_pmid, checked_at),  -- Prevent duplicate checks
    CHECK (source_pmid IS NOT NULL OR source_doi IS NOT NULL)  -- Must have identifier
);

CREATE INDEX idx_abstracts_checked_pmid ON papercheck.abstracts_checked(source_pmid);
CREATE INDEX idx_abstracts_checked_doi ON papercheck.abstracts_checked(source_doi);
CREATE INDEX idx_abstracts_checked_date ON papercheck.abstracts_checked(checked_at DESC);
CREATE INDEX idx_abstracts_checked_status ON papercheck.abstracts_checked(status);
```

### Table 2: statements

```sql
CREATE TABLE papercheck.statements (
    id SERIAL PRIMARY KEY,
    abstract_id INTEGER NOT NULL REFERENCES papercheck.abstracts_checked(id) ON DELETE CASCADE,

    -- Statement content
    statement_text TEXT NOT NULL CHECK (length(statement_text) > 0),
    context TEXT,  -- Surrounding sentences

    -- Classification
    statement_type VARCHAR(50) NOT NULL
        CHECK (statement_type IN ('hypothesis', 'finding', 'conclusion')),
    statement_order INTEGER NOT NULL CHECK (statement_order >= 1),

    -- Extraction metadata
    extraction_confidence FLOAT CHECK (extraction_confidence BETWEEN 0.0 AND 1.0),
    extraction_model VARCHAR(100),
    extracted_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(abstract_id, statement_order)  -- One statement per order position
);

CREATE INDEX idx_statements_abstract ON papercheck.statements(abstract_id);
CREATE INDEX idx_statements_type ON papercheck.statements(statement_type);
```

### Table 3: counter_statements

```sql
CREATE TABLE papercheck.counter_statements (
    id SERIAL PRIMARY KEY,
    statement_id INTEGER NOT NULL REFERENCES papercheck.statements(id) ON DELETE CASCADE,

    -- Counter-claim content
    negated_text TEXT NOT NULL CHECK (length(negated_text) > 0),
    hyde_abstracts TEXT[] NOT NULL CHECK (array_length(hyde_abstracts, 1) > 0),
    keywords TEXT[] NOT NULL CHECK (array_length(keywords, 1) > 0),

    -- Generation metadata
    generation_model VARCHAR(100),
    generation_config JSONB DEFAULT '{}'::jsonb,
    generated_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(statement_id)  -- One counter-statement per statement
);

CREATE INDEX idx_counter_statements_statement ON papercheck.counter_statements(statement_id);
```

### Table 4: search_results

```sql
CREATE TABLE papercheck.search_results (
    id SERIAL PRIMARY KEY,
    counter_statement_id INTEGER NOT NULL
        REFERENCES papercheck.counter_statements(id) ON DELETE CASCADE,

    -- Document reference
    doc_id INTEGER NOT NULL,  -- FK to public.documents (not enforced for flexibility)

    -- Search provenance
    search_strategy VARCHAR(20) NOT NULL
        CHECK (search_strategy IN ('semantic', 'hyde', 'keyword')),
    search_rank INTEGER CHECK (search_rank >= 1),
    search_score FLOAT,

    -- Metadata
    searched_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_search_results_counter ON papercheck.search_results(counter_statement_id);
CREATE INDEX idx_search_results_doc ON papercheck.search_results(doc_id);
CREATE INDEX idx_search_results_strategy ON papercheck.search_results(search_strategy);
```

### Table 5: scored_documents

```sql
CREATE TABLE papercheck.scored_documents (
    id SERIAL PRIMARY KEY,
    counter_statement_id INTEGER NOT NULL
        REFERENCES papercheck.counter_statements(id) ON DELETE CASCADE,

    -- Document reference
    doc_id INTEGER NOT NULL,

    -- Scoring results
    relevance_score INTEGER NOT NULL CHECK (relevance_score BETWEEN 1 AND 5),
    explanation TEXT NOT NULL,
    supports_counter BOOLEAN NOT NULL,

    -- Search provenance (which strategies found this doc)
    found_by TEXT[] NOT NULL,

    -- Scoring metadata
    scoring_model VARCHAR(100),
    scored_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(counter_statement_id, doc_id)  -- One score per doc per statement
);

CREATE INDEX idx_scored_documents_counter ON papercheck.scored_documents(counter_statement_id);
CREATE INDEX idx_scored_documents_doc ON papercheck.scored_documents(doc_id);
CREATE INDEX idx_scored_documents_score ON papercheck.scored_documents(relevance_score);
CREATE INDEX idx_scored_documents_supports ON papercheck.scored_documents(supports_counter);
```

### Table 6: citations

```sql
CREATE TABLE papercheck.citations (
    id SERIAL PRIMARY KEY,
    counter_statement_id INTEGER NOT NULL
        REFERENCES papercheck.counter_statements(id) ON DELETE CASCADE,

    -- Document reference
    doc_id INTEGER NOT NULL,

    -- Citation content
    passage TEXT NOT NULL CHECK (length(passage) > 0),
    relevance_score INTEGER NOT NULL CHECK (relevance_score BETWEEN 1 AND 5),
    citation_order INTEGER NOT NULL CHECK (citation_order >= 1),

    -- Formatted citation
    formatted_citation TEXT NOT NULL,

    -- Metadata (denormalized for convenience)
    doc_metadata JSONB DEFAULT '{}'::jsonb,  -- authors, year, journal, pmid, doi

    -- Extraction metadata
    extracted_by VARCHAR(100),  -- CitationFinderAgent
    extracted_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(counter_statement_id, citation_order)  -- Ordered citations
);

CREATE INDEX idx_citations_counter ON papercheck.citations(counter_statement_id);
CREATE INDEX idx_citations_doc ON papercheck.citations(doc_id);
CREATE INDEX idx_citations_order ON papercheck.citations(citation_order);
```

### Table 7: counter_reports

```sql
CREATE TABLE papercheck.counter_reports (
    id SERIAL PRIMARY KEY,
    counter_statement_id INTEGER NOT NULL
        REFERENCES papercheck.counter_statements(id) ON DELETE CASCADE,

    -- Report content
    report_text TEXT NOT NULL CHECK (length(report_text) > 0),
    report_markdown TEXT,  -- Formatted version

    -- Statistics
    num_citations INTEGER NOT NULL CHECK (num_citations >= 0),
    search_stats JSONB DEFAULT '{}'::jsonb,  -- documents_found, scored, cited

    -- Generation metadata
    generation_model VARCHAR(100),
    generation_config JSONB DEFAULT '{}'::jsonb,
    generated_at TIMESTAMP DEFAULT NOW(),
    generation_time_seconds FLOAT,

    UNIQUE(counter_statement_id)  -- One report per counter-statement
);

CREATE INDEX idx_counter_reports_counter ON papercheck.counter_reports(counter_statement_id);
```

### Table 8: verdicts

```sql
CREATE TABLE papercheck.verdicts (
    id SERIAL PRIMARY KEY,
    statement_id INTEGER NOT NULL
        REFERENCES papercheck.statements(id) ON DELETE CASCADE,

    -- Verdict
    verdict VARCHAR(20) NOT NULL
        CHECK (verdict IN ('supports', 'contradicts', 'undecided')),
    rationale TEXT NOT NULL CHECK (length(rationale) > 0),
    confidence VARCHAR(20) NOT NULL
        CHECK (confidence IN ('high', 'medium', 'low')),

    -- Analysis metadata
    analysis_model VARCHAR(100),
    analysis_config JSONB DEFAULT '{}'::jsonb,
    analyzed_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(statement_id)  -- One verdict per statement
);

CREATE INDEX idx_verdicts_statement ON papercheck.verdicts(statement_id);
CREATE INDEX idx_verdicts_verdict ON papercheck.verdicts(verdict);
CREATE INDEX idx_verdicts_confidence ON papercheck.verdicts(confidence);
```

### Views for Convenient Queries

```sql
-- Complete results view (joins all tables)
CREATE OR REPLACE VIEW papercheck.v_complete_results AS
SELECT
    a.id as abstract_id,
    a.source_pmid,
    a.source_doi,
    a.source_title,
    a.checked_at,
    a.overall_assessment,
    s.id as statement_id,
    s.statement_text,
    s.statement_type,
    cs.id as counter_statement_id,
    cs.negated_text as counter_statement,
    v.verdict,
    v.confidence,
    v.rationale,
    cr.num_citations,
    cr.report_text as counter_report,
    (SELECT COUNT(*) FROM papercheck.search_results sr
     WHERE sr.counter_statement_id = cs.id) as total_docs_found,
    (SELECT COUNT(*) FROM papercheck.scored_documents sd
     WHERE sd.counter_statement_id = cs.id) as total_docs_scored,
    (SELECT COUNT(*) FROM papercheck.scored_documents sd
     WHERE sd.counter_statement_id = cs.id AND sd.supports_counter) as docs_above_threshold
FROM papercheck.abstracts_checked a
JOIN papercheck.statements s ON s.abstract_id = a.id
JOIN papercheck.counter_statements cs ON cs.statement_id = s.id
JOIN papercheck.verdicts v ON v.statement_id = s.id
JOIN papercheck.counter_reports cr ON cr.counter_statement_id = cs.id
ORDER BY a.checked_at DESC, s.statement_order;

-- Search strategy effectiveness view
CREATE OR REPLACE VIEW papercheck.v_search_strategy_stats AS
SELECT
    search_strategy,
    COUNT(*) as total_docs_found,
    COUNT(DISTINCT doc_id) as unique_docs,
    AVG(sd.relevance_score) as avg_relevance_score,
    SUM(CASE WHEN sd.supports_counter THEN 1 ELSE 0 END) as docs_above_threshold
FROM papercheck.search_results sr
LEFT JOIN papercheck.scored_documents sd
    ON sd.counter_statement_id = sr.counter_statement_id
    AND sd.doc_id = sr.doc_id
GROUP BY search_strategy;

-- Verdict distribution view
CREATE OR REPLACE VIEW papercheck.v_verdict_distribution AS
SELECT
    verdict,
    confidence,
    COUNT(*) as count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) as percentage
FROM papercheck.verdicts
GROUP BY verdict, confidence
ORDER BY verdict, confidence;
```

### Utility Functions

```sql
-- Function to get complete result for an abstract
CREATE OR REPLACE FUNCTION papercheck.get_complete_result(p_abstract_id INTEGER)
RETURNS TABLE (
    statement_text TEXT,
    counter_statement TEXT,
    verdict VARCHAR(20),
    confidence VARCHAR(20),
    rationale TEXT,
    num_citations INTEGER,
    counter_report TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        s.statement_text,
        cs.negated_text,
        v.verdict,
        v.confidence,
        v.rationale,
        cr.num_citations,
        cr.report_text
    FROM papercheck.statements s
    JOIN papercheck.counter_statements cs ON cs.statement_id = s.id
    JOIN papercheck.verdicts v ON v.statement_id = s.id
    JOIN papercheck.counter_reports cr ON cr.counter_statement_id = cs.id
    WHERE s.abstract_id = p_abstract_id
    ORDER BY s.statement_order;
END;
$$ LANGUAGE plpgsql;

-- Function to clean up orphaned search results (docs not in main table)
CREATE OR REPLACE FUNCTION papercheck.cleanup_orphaned_search_results()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    WITH deleted AS (
        DELETE FROM papercheck.search_results sr
        WHERE NOT EXISTS (
            SELECT 1 FROM public.documents d WHERE d.id = sr.doc_id
        )
        RETURNING *
    )
    SELECT COUNT(*) INTO deleted_count FROM deleted;

    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;
```

## Implementation Steps

1. **Create migration file**: `migrations/papercheck_schema.sql`

2. **Test on development database** (`bmlibrarian_dev`):
   ```bash
   psql -U postgres -d bmlibrarian_dev -f migrations/papercheck_schema.sql
   ```

3. **Verify schema creation**:
   ```sql
   \dn papercheck
   \dt papercheck.*
   \dv papercheck.*
   \df papercheck.*
   ```

4. **Test foreign key constraints**:
   - Try inserting statement without abstract → should fail
   - Try inserting counter_statement without statement → should fail
   - Verify CASCADE deletes work correctly

5. **Test check constraints**:
   - Invalid verdict values → should fail
   - Invalid score ranges → should fail
   - Empty required text fields → should fail

6. **Apply to production** (after testing):
   ```bash
   psql -U postgres -d knowledgebase -f migrations/papercheck_schema.sql
   ```

7. **Create Python database interface** (src/bmlibrarian/paperchecker/database.py):
   ```python
   class PaperCheckDB:
       """Database interface for PaperChecker"""

       def save_abstract_check(self, result: PaperCheckResult) -> int:
           """Save complete result to database, returns abstract_id"""
           pass

       def get_abstract_check(self, abstract_id: int) -> PaperCheckResult:
           """Retrieve complete result from database"""
           pass

       def list_checks(self, limit: int = 100) -> List[Dict]:
           """List recent checks with summary info"""
           pass
   ```

## Testing Criteria

Create `tests/test_paperchecker_database.py`:

1. **Test schema exists**: Query information_schema
2. **Test table creation**: All 8 tables exist
3. **Test indexes**: All indexes created
4. **Test views**: All 3 views queryable
5. **Test functions**: Both utility functions work
6. **Test foreign keys**: Referential integrity enforced
7. **Test check constraints**: Invalid data rejected
8. **Test CASCADE deletes**: Deleting abstract removes all related data
9. **Test uniqueness constraints**: Duplicates prevented
10. **Test performance**: Queries with indexes are fast

## Success Criteria

- [ ] Schema `papercheck` created successfully
- [ ] All 8 tables created with correct columns
- [ ] All foreign keys and constraints working
- [ ] All indexes created for performance
- [ ] All 3 views queryable and returning expected results
- [ ] Both utility functions working
- [ ] Python database interface implemented
- [ ] All tests passing
- [ ] Migration tested on development database
- [ ] Documentation of schema design complete

## Next Steps

After completing this step, proceed to:
- **Step 3**: Core PaperCheckerAgent Structure (03_AGENT_STRUCTURE.md)
- This agent will use both the data models and database schema
