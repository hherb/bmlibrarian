# Step 1: Database Migration Script - PaperWeightAssessment

## Objective
Create a PostgreSQL migration script to add the `paper_weights` schema with all necessary tables for storing multi-dimensional paper weight assessments with full audit trail.

## Prerequisites
- PostgreSQL database with pgvector extension installed
- Existing BMLibrarian database schema
- Access to `migrations/` directory

## Implementation Details

### File to Create
- `migrations/011_add_paper_weight_schema.sql`

### Schema Components

#### 1. Schema Creation
```sql
CREATE SCHEMA IF NOT EXISTS paper_weights;
```

#### 2. Main Assessment Table
**Table:** `paper_weights.assessments`

**Purpose:** Store one assessment per (document_id, assessor_version) combination

**Columns:**
- `assessment_id`: SERIAL PRIMARY KEY
- `document_id`: INTEGER, FK to public.documents(id)
- `assessed_at`: TIMESTAMP DEFAULT NOW()
- `assessor_version`: TEXT NOT NULL (e.g., "v1.0.0")
- **Dimension Scores (0-10 scale):**
  - `study_design_score`: NUMERIC(4,2) CHECK (0-10)
  - `sample_size_score`: NUMERIC(4,2) CHECK (0-10)
  - `methodological_quality_score`: NUMERIC(4,2) CHECK (0-10)
  - `risk_of_bias_score`: NUMERIC(4,2) CHECK (0-10)
  - `replication_status_score`: NUMERIC(4,2) CHECK (0-10)
- `final_weight`: NUMERIC(5,2) CHECK (0-10)
- `dimension_weights`: JSONB (stores weights used for calculation)
- **Metadata:**
  - `study_type`: TEXT (e.g., "RCT", "cohort")
  - `sample_size`: INTEGER (extracted n)

**Constraints:**
- UNIQUE(document_id, assessor_version) - allows re-assessment with new versions

**Indexes:**
```sql
CREATE INDEX idx_assessments_document ON paper_weights.assessments(document_id);
CREATE INDEX idx_assessments_version ON paper_weights.assessments(assessor_version);
```

#### 3. Audit Trail Table
**Table:** `paper_weights.assessment_details`

**Purpose:** Granular audit trail for reproducibility - stores every component of every dimension score

**Columns:**
- `detail_id`: SERIAL PRIMARY KEY
- `assessment_id`: INTEGER, FK to assessments(assessment_id) ON DELETE CASCADE
- `dimension`: TEXT NOT NULL (e.g., "study_design", "sample_size")
- `component`: TEXT (e.g., "randomization", "blinding_type")
- `extracted_value`: TEXT (what was found in the paper)
- `score_contribution`: NUMERIC(4,2) (contribution to dimension score)
- `evidence_text`: TEXT (relevant excerpt from paper)
- `reasoning`: TEXT (LLM reasoning for this score)
- `created_at`: TIMESTAMP DEFAULT NOW()

**Indexes:**
```sql
CREATE INDEX idx_details_assessment ON paper_weights.assessment_details(assessment_id);
```

#### 4. Replication Tracking Table
**Table:** `paper_weights.replications`

**Purpose:** Manual tracking of replication studies (automated discovery = future project)

**Columns:**
- `replication_id`: SERIAL PRIMARY KEY
- `source_document_id`: INTEGER, FK to public.documents(id)
- `replication_document_id`: INTEGER, FK to public.documents(id)
- `replication_type`: TEXT CHECK ('confirms', 'contradicts', 'extends')
- `quality_comparison`: TEXT CHECK ('lower', 'comparable', 'higher')
- `assessed_at`: TIMESTAMP DEFAULT NOW()
- `assessed_by`: TEXT (username/system identifier)
- `confidence`: TEXT CHECK ('low', 'medium', 'high')
- `notes`: TEXT

**Constraints:**
- UNIQUE(source_document_id, replication_document_id)

**Indexes:**
```sql
CREATE INDEX idx_replications_source ON paper_weights.replications(source_document_id);
CREATE INDEX idx_replications_replication ON paper_weights.replications(replication_document_id);
```

## Complete Migration Script Template

```sql
-- Paper Weight Assessment Schema Migration
-- Version: 1.0.0
-- Purpose: Multi-dimensional paper weight assessment with full audit trail

BEGIN;

-- Create schema
CREATE SCHEMA IF NOT EXISTS paper_weights;

-- Main assessment table
CREATE TABLE paper_weights.assessments (
    assessment_id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES public.documents(id),
    assessed_at TIMESTAMP NOT NULL DEFAULT NOW(),
    assessor_version TEXT NOT NULL,

    -- Multi-dimensional scores (0-10 scale)
    study_design_score NUMERIC(4,2) NOT NULL CHECK (study_design_score >= 0 AND study_design_score <= 10),
    sample_size_score NUMERIC(4,2) NOT NULL CHECK (sample_size_score >= 0 AND sample_size_score <= 10),
    methodological_quality_score NUMERIC(4,2) NOT NULL CHECK (methodological_quality_score >= 0 AND methodological_quality_score <= 10),
    risk_of_bias_score NUMERIC(4,2) NOT NULL CHECK (risk_of_bias_score >= 0 AND risk_of_bias_score <= 10),
    replication_status_score NUMERIC(4,2) NOT NULL CHECK (replication_status_score >= 0 AND replication_status_score <= 10),

    -- Final weighted score
    final_weight NUMERIC(5,2) NOT NULL CHECK (final_weight >= 0 AND final_weight <= 10),
    dimension_weights JSONB NOT NULL,

    -- Extracted metadata
    study_type TEXT,
    sample_size INTEGER,

    -- One assessment per (document, version) combination
    UNIQUE(document_id, assessor_version)
);

-- Audit trail for reproducibility
CREATE TABLE paper_weights.assessment_details (
    detail_id SERIAL PRIMARY KEY,
    assessment_id INTEGER NOT NULL REFERENCES paper_weights.assessments(assessment_id) ON DELETE CASCADE,
    dimension TEXT NOT NULL,
    component TEXT,
    extracted_value TEXT,
    score_contribution NUMERIC(4,2),
    evidence_text TEXT,
    reasoning TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Replication tracking (manual initially)
CREATE TABLE paper_weights.replications (
    replication_id SERIAL PRIMARY KEY,
    source_document_id INTEGER NOT NULL REFERENCES public.documents(id),
    replication_document_id INTEGER NOT NULL REFERENCES public.documents(id),
    replication_type TEXT NOT NULL CHECK (replication_type IN ('confirms', 'contradicts', 'extends')),
    quality_comparison TEXT CHECK (quality_comparison IN ('lower', 'comparable', 'higher')),
    assessed_at TIMESTAMP NOT NULL DEFAULT NOW(),
    assessed_by TEXT,
    confidence TEXT CHECK (confidence IN ('low', 'medium', 'high')),
    notes TEXT,

    UNIQUE(source_document_id, replication_document_id)
);

-- Indexes for performance
CREATE INDEX idx_assessments_document ON paper_weights.assessments(document_id);
CREATE INDEX idx_assessments_version ON paper_weights.assessments(assessor_version);
CREATE INDEX idx_details_assessment ON paper_weights.assessment_details(assessment_id);
CREATE INDEX idx_replications_source ON paper_weights.replications(source_document_id);
CREATE INDEX idx_replications_replication ON paper_weights.replications(replication_document_id);

COMMIT;
```

## Testing the Migration

### 1. Run Migration
```bash
# From project root
psql -U $POSTGRES_USER -d $POSTGRES_DB -f migrations/add_paper_weight_schema.sql
```

### 2. Verify Schema Creation
```sql
-- Check schema exists
SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'paper_weights';

-- Check tables
SELECT table_name FROM information_schema.tables WHERE table_schema = 'paper_weights';

-- Expected tables:
-- - assessments
-- - assessment_details
-- - replications

-- Check indexes
SELECT indexname FROM pg_indexes WHERE schemaname = 'paper_weights';
```

### 3. Test Constraints
```sql
-- Test score CHECK constraints (should fail)
INSERT INTO paper_weights.assessments
    (document_id, assessor_version, study_design_score, sample_size_score,
     methodological_quality_score, risk_of_bias_score, replication_status_score,
     final_weight, dimension_weights)
VALUES (1, 'v1.0.0', 15.0, 5.0, 5.0, 5.0, 5.0, 5.0, '{}'::jsonb);
-- Expected: ERROR - violates check constraint

-- Test UNIQUE constraint (should succeed first time, fail second time)
INSERT INTO paper_weights.assessments
    (document_id, assessor_version, study_design_score, sample_size_score,
     methodological_quality_score, risk_of_bias_score, replication_status_score,
     final_weight, dimension_weights)
VALUES (1, 'v1.0.0', 8.0, 7.0, 6.5, 7.5, 0.0, 7.2, '{"study_design": 0.25}'::jsonb);
-- Expected: SUCCESS

-- Try again (should fail)
INSERT INTO paper_weights.assessments
    (document_id, assessor_version, study_design_score, sample_size_score,
     methodological_quality_score, risk_of_bias_score, replication_status_score,
     final_weight, dimension_weights)
VALUES (1, 'v1.0.0', 9.0, 8.0, 7.5, 8.5, 5.0, 8.0, '{"study_design": 0.25}'::jsonb);
-- Expected: ERROR - duplicate key value violates unique constraint

-- Clean up test data
DELETE FROM paper_weights.assessments;
```

### 4. Test Foreign Keys
```sql
-- Test FK to documents (should fail if document doesn't exist)
INSERT INTO paper_weights.assessments
    (document_id, assessor_version, study_design_score, sample_size_score,
     methodological_quality_score, risk_of_bias_score, replication_status_score,
     final_weight, dimension_weights)
VALUES (999999999, 'v1.0.0', 8.0, 7.0, 6.5, 7.5, 0.0, 7.2, '{}'::jsonb);
-- Expected: ERROR - violates foreign key constraint
```

### 5. Test CASCADE Deletion
```sql
-- Insert test assessment with details
INSERT INTO paper_weights.assessments
    (document_id, assessor_version, study_design_score, sample_size_score,
     methodological_quality_score, risk_of_bias_score, replication_status_score,
     final_weight, dimension_weights, study_type)
VALUES ((SELECT id FROM public.documents LIMIT 1), 'test_v1', 8.0, 7.0, 6.5, 7.5, 0.0, 7.2, '{}'::jsonb, 'RCT')
RETURNING assessment_id;

-- Insert detail
INSERT INTO paper_weights.assessment_details (assessment_id, dimension, component, score_contribution)
VALUES ((SELECT assessment_id FROM paper_weights.assessments WHERE assessor_version = 'test_v1'),
        'study_design', 'study_type', 8.0);

-- Delete assessment (should cascade to details)
DELETE FROM paper_weights.assessments WHERE assessor_version = 'test_v1';

-- Verify detail is gone
SELECT * FROM paper_weights.assessment_details WHERE dimension = 'study_design';
-- Expected: 0 rows
```

## Rollback Script

Create `migrations/rollback_paper_weight_schema.sql`:

```sql
-- Rollback Paper Weight Assessment Schema
BEGIN;

DROP TABLE IF EXISTS paper_weights.assessment_details CASCADE;
DROP TABLE IF EXISTS paper_weights.replications CASCADE;
DROP TABLE IF EXISTS paper_weights.assessments CASCADE;
DROP SCHEMA IF EXISTS paper_weights CASCADE;

COMMIT;
```

## Success Criteria
- [ ] Migration script created in `migrations/add_paper_weight_schema.sql`
- [ ] Rollback script created in `migrations/rollback_paper_weight_schema.sql`
- [ ] Schema `paper_weights` created successfully
- [ ] All three tables created with correct columns
- [ ] All CHECK constraints working correctly
- [ ] UNIQUE constraint on (document_id, assessor_version) working
- [ ] Foreign keys properly referencing public.documents(id)
- [ ] CASCADE deletion working for assessment_details
- [ ] All indexes created
- [ ] No errors when running migration on clean database

## Notes for Future Reference
- **Versioning Strategy:** The `assessor_version` field allows us to re-assess papers when methodology improves. Old assessments remain in the database for historical analysis.
- **Audit Trail:** Every component of every dimension score should have at least one entry in `assessment_details`. This ensures complete reproducibility.
- **Replication Tracking:** Initially manual via GUI. Future automation will query this table to compute replication_status_score.
- **JSONB for Weights:** Storing dimension weights in JSONB allows flexibility if we change the weighting formula over time.

## Next Step
After successful migration, proceed to **Step 2: Data Models Implementation**.
