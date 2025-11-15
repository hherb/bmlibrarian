-- SQLite Schema for Fact-Checker Review Packages
--
-- This schema creates a self-contained SQLite database for distributing
-- fact-check results to external reviewers. All data needed for review
-- is embedded in a single .db file with no PostgreSQL dependency.
--
-- Key differences from PostgreSQL schema:
-- - Simpler data types (TEXT instead of JSONB)
-- - All timestamps as TEXT (ISO 8601 format)
-- - No schema separation (all tables in main database)
-- - Includes embedded documents table with full abstracts
-- - Package metadata for tracking export source

-- ============================================================================
-- 1. Package Metadata
-- ============================================================================

CREATE TABLE package_metadata (
    metadata_id INTEGER PRIMARY KEY AUTOINCREMENT,
    export_date TEXT NOT NULL,  -- ISO 8601 timestamp
    source_database TEXT NOT NULL,  -- e.g., "knowledgebase @ postgresql://host"
    postgresql_version TEXT,
    bmlibrarian_version TEXT,
    total_statements INTEGER NOT NULL,
    total_evaluations INTEGER NOT NULL,
    total_evidence INTEGER NOT NULL,
    total_documents INTEGER NOT NULL,
    exported_by TEXT,  -- Username who created the package
    export_filters TEXT,  -- JSON text describing any filters applied
    package_version INTEGER NOT NULL DEFAULT 1
);

-- ============================================================================
-- 2. Statements - Biomedical statements to be fact-checked
-- ============================================================================

CREATE TABLE statements (
    statement_id INTEGER PRIMARY KEY,  -- Preserved from PostgreSQL
    statement_text TEXT NOT NULL UNIQUE,
    input_statement_id TEXT,
    expected_answer TEXT CHECK (expected_answer IN ('yes', 'no', 'maybe')),
    created_at TEXT,  -- ISO 8601 timestamp
    source_file TEXT,
    review_status TEXT NOT NULL DEFAULT 'pending' CHECK (review_status IN ('pending', 'in_review', 'completed', 'flagged'))
);

CREATE INDEX idx_statements_text ON statements(statement_text);
CREATE INDEX idx_statements_input_id ON statements(input_statement_id);
CREATE INDEX idx_statements_review_status ON statements(review_status);

-- ============================================================================
-- 3. Annotators - Human reviewers
-- ============================================================================

CREATE TABLE annotators (
    annotator_id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    full_name TEXT,
    email TEXT,
    expertise_level TEXT CHECK (expertise_level IN ('expert', 'intermediate', 'novice')),
    institution TEXT,
    created_at TEXT  -- ISO 8601 timestamp
);

CREATE INDEX idx_annotators_username ON annotators(username);

-- ============================================================================
-- 4. AI Evaluations - AI-generated fact-check evaluations
-- ============================================================================

CREATE TABLE ai_evaluations (
    evaluation_id INTEGER PRIMARY KEY,  -- Preserved from PostgreSQL
    statement_id INTEGER NOT NULL REFERENCES statements(statement_id) ON DELETE CASCADE,
    evaluation TEXT NOT NULL CHECK (evaluation IN ('yes', 'no', 'maybe', 'error')),
    reason TEXT NOT NULL,
    confidence TEXT CHECK (confidence IN ('high', 'medium', 'low')),
    documents_reviewed INTEGER NOT NULL DEFAULT 0,
    supporting_citations INTEGER NOT NULL DEFAULT 0,
    contradicting_citations INTEGER NOT NULL DEFAULT 0,
    neutral_citations INTEGER NOT NULL DEFAULT 0,
    matches_expected INTEGER,  -- SQLite uses INTEGER for boolean (0/1/NULL)
    evaluated_at TEXT,  -- ISO 8601 timestamp
    model_used TEXT,
    model_version TEXT,
    agent_config TEXT,  -- JSON as TEXT
    session_id TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    UNIQUE (statement_id, version)
);

CREATE INDEX idx_ai_eval_statement ON ai_evaluations(statement_id, version DESC);
CREATE INDEX idx_ai_eval_session ON ai_evaluations(session_id);
CREATE INDEX idx_ai_eval_evaluation ON ai_evaluations(evaluation);
CREATE INDEX idx_ai_eval_matches ON ai_evaluations(matches_expected) WHERE matches_expected IS NOT NULL;

-- ============================================================================
-- 5. Documents - Full document data from public.document table
--
-- This table contains ONLY documents that are referenced in evidence.
-- It includes full abstracts, titles, and metadata needed for review.
-- ============================================================================

CREATE TABLE documents (
    id INTEGER PRIMARY KEY,  -- Preserved from PostgreSQL document.id
    source_id INTEGER,
    external_id TEXT NOT NULL,  -- PMID for PubMed, etc.
    doi TEXT,
    title TEXT,
    abstract TEXT,  -- FULL ABSTRACT - critical for review!
    authors TEXT,  -- JSON array as TEXT (e.g., '["Smith J", "Doe A"]')
    publication TEXT,
    publication_date TEXT,  -- ISO 8601 date
    url TEXT,
    pdf_url TEXT,
    added_date TEXT,  -- ISO 8601 timestamp
    updated_date TEXT  -- ISO 8601 timestamp
);

CREATE INDEX idx_documents_external_id ON documents(external_id);
CREATE INDEX idx_documents_doi ON documents(doi);

-- ============================================================================
-- 6. Evidence - Literature citations supporting evaluations
-- ============================================================================

CREATE TABLE evidence (
    evidence_id INTEGER PRIMARY KEY,  -- Preserved from PostgreSQL
    evaluation_id INTEGER NOT NULL REFERENCES ai_evaluations(evaluation_id) ON DELETE CASCADE,
    citation_text TEXT NOT NULL,
    document_id INTEGER NOT NULL REFERENCES documents(id),  -- FK to local documents table!
    pmid TEXT,
    doi TEXT,
    relevance_score REAL CHECK (relevance_score BETWEEN 0.0 AND 5.0),
    supports_statement TEXT CHECK (supports_statement IN ('supports', 'contradicts', 'neutral')),
    created_at TEXT  -- ISO 8601 timestamp
);

CREATE INDEX idx_evidence_evaluation ON evidence(evaluation_id);
CREATE INDEX idx_evidence_document ON evidence(document_id);
CREATE INDEX idx_evidence_stance ON evidence(supports_statement);

-- ============================================================================
-- 7. Human Annotations - Human reviewer annotations
-- ============================================================================

CREATE TABLE human_annotations (
    annotation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    statement_id INTEGER NOT NULL REFERENCES statements(statement_id) ON DELETE CASCADE,
    annotator_id INTEGER NOT NULL REFERENCES annotators(annotator_id) ON DELETE CASCADE,
    annotation TEXT NOT NULL CHECK (annotation IN ('yes', 'no', 'maybe', 'unclear')),
    explanation TEXT,
    confidence TEXT CHECK (confidence IN ('high', 'medium', 'low')),
    review_duration_seconds INTEGER,
    review_date TEXT,  -- ISO 8601 timestamp
    session_id TEXT,
    UNIQUE (statement_id, annotator_id)
);

CREATE INDEX idx_human_ann_statement ON human_annotations(statement_id);
CREATE INDEX idx_human_ann_annotator ON human_annotations(annotator_id);
CREATE INDEX idx_human_ann_annotation ON human_annotations(annotation);

-- ============================================================================
-- Helper Views
-- ============================================================================

-- View: Complete fact-check results with AI and human annotations
CREATE VIEW v_complete_results AS
SELECT
    s.statement_id,
    s.statement_text,
    s.input_statement_id,
    s.expected_answer,
    s.review_status,
    ae.evaluation_id,
    ae.evaluation as ai_evaluation,
    ae.reason as ai_reason,
    ae.confidence as ai_confidence,
    ae.documents_reviewed,
    ae.supporting_citations,
    ae.contradicting_citations,
    ae.neutral_citations,
    ae.matches_expected,
    ae.model_used,
    ae.evaluated_at,
    COUNT(DISTINCT ha.annotation_id) as human_annotation_count,
    COUNT(DISTINCT e.evidence_id) as evidence_count
FROM statements s
LEFT JOIN ai_evaluations ae ON s.statement_id = ae.statement_id
    AND ae.version = (SELECT MAX(version) FROM ai_evaluations WHERE statement_id = s.statement_id)
LEFT JOIN human_annotations ha ON s.statement_id = ha.statement_id
LEFT JOIN evidence e ON ae.evaluation_id = e.evaluation_id
GROUP BY s.statement_id, s.statement_text, s.input_statement_id, s.expected_answer, s.review_status,
         ae.evaluation_id, ae.evaluation, ae.reason, ae.confidence, ae.documents_reviewed,
         ae.supporting_citations, ae.contradicting_citations, ae.neutral_citations,
         ae.matches_expected, ae.model_used, ae.evaluated_at;

-- View: Statements needing human annotation
CREATE VIEW v_statements_needing_annotation AS
SELECT s.*, ae.evaluation, ae.reason
FROM statements s
LEFT JOIN ai_evaluations ae ON s.statement_id = ae.statement_id
    AND ae.version = (SELECT MAX(version) FROM ai_evaluations WHERE statement_id = s.statement_id)
LEFT JOIN human_annotations ha ON s.statement_id = ha.statement_id
WHERE ha.annotation_id IS NULL;

-- ============================================================================
-- Indexes for Performance
-- ============================================================================

-- Composite indexes for common queries
CREATE INDEX idx_evidence_eval_doc ON evidence(evaluation_id, document_id);
CREATE INDEX idx_ai_eval_stmt_ver ON ai_evaluations(statement_id, version);

-- ============================================================================
-- Package Integrity Check
-- ============================================================================

-- This query can be run to verify package integrity:
-- SELECT
--     (SELECT COUNT(*) FROM statements) as statements_count,
--     (SELECT COUNT(*) FROM ai_evaluations) as evaluations_count,
--     (SELECT COUNT(*) FROM evidence) as evidence_count,
--     (SELECT COUNT(*) FROM documents) as documents_count,
--     (SELECT COUNT(*) FROM human_annotations) as annotations_count,
--     (SELECT total_statements FROM package_metadata) as expected_statements,
--     (SELECT total_evaluations FROM package_metadata) as expected_evaluations,
--     (SELECT total_evidence FROM package_metadata) as expected_evidence,
--     (SELECT total_documents FROM package_metadata) as expected_documents;

-- ============================================================================
-- SQLite-Specific Optimizations
-- ============================================================================

-- Enable foreign key constraints (SQLite default is OFF!)
PRAGMA foreign_keys = ON;

-- Use WAL mode for better concurrency (important for GUI writes)
PRAGMA journal_mode = WAL;

-- Optimize page size for typical fact-check data
PRAGMA page_size = 4096;

-- Enable automatic index creation for optimization
PRAGMA automatic_index = ON;

-- Set synchronous mode for balance of safety and performance
PRAGMA synchronous = NORMAL;

-- ============================================================================
-- Schema Version Tracking
-- ============================================================================

CREATE TABLE schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL,  -- ISO 8601 timestamp
    description TEXT
);

INSERT INTO schema_version (version, applied_at, description)
VALUES (1, datetime('now'), 'Initial SQLite review package schema');

-- ============================================================================
-- Usage Notes
-- ============================================================================

-- This schema is designed for:
-- 1. Export from PostgreSQL (export_review_package.py)
-- 2. Review in GUI with SQLite backend (fact_checker_review_gui.py --db-file)
-- 3. Export human annotations to JSON (export_human_evaluations.py)
-- 4. Re-import to PostgreSQL (import_human_evaluations.py)
--
-- Key features:
-- - Self-contained: All data needed for review in one .db file
-- - Full abstracts: documents table includes complete abstract text
-- - Portable: No PostgreSQL dependency for reviewers
-- - Efficient: Proper indexes for GUI performance
-- - Safe: Foreign key constraints and check constraints
-- - Versioned: Support for schema migrations
