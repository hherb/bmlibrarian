-- Migration: Create PaperCheck Schema for Paper Abstract Weight Assessment
-- Description: Creates papercheck schema for comprehensive paper quality assessment using multi-agent workflow
-- Author: BMLibrarian
-- Date: 2025-11-21
-- Version: 010

-- ============================================================================
-- Migration Tracking Setup
-- ============================================================================

-- Create schema_migrations table if it doesn't exist (for tracking applied migrations)
CREATE TABLE IF NOT EXISTS public.schema_migrations (
    version VARCHAR(100) PRIMARY KEY,
    applied_at TIMESTAMP NOT NULL DEFAULT NOW(),
    description TEXT
);

COMMENT ON TABLE public.schema_migrations IS 'Tracks applied database migrations for version control';

-- Record this migration (idempotent - won't fail if re-run)
INSERT INTO public.schema_migrations (version, applied_at, description)
VALUES ('010_create_papercheck_schema', NOW(), 'PaperChecker: Paper abstract quality assessment with counter-evidence analysis')
ON CONFLICT (version) DO NOTHING;

-- ============================================================================
-- Create papercheck schema
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS papercheck;

-- Grant permissions
GRANT USAGE ON SCHEMA papercheck TO bmlibrarian_user;
GRANT ALL ON ALL TABLES IN SCHEMA papercheck TO bmlibrarian_user;
GRANT ALL ON ALL SEQUENCES IN SCHEMA papercheck TO bmlibrarian_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA papercheck
    GRANT ALL ON TABLES TO bmlibrarian_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA papercheck
    GRANT ALL ON SEQUENCES TO bmlibrarian_user;

COMMENT ON SCHEMA papercheck IS 'PaperChecker: Comprehensive paper abstract quality assessment with counter-evidence analysis';

-- ============================================================================
-- Enum Types for Type Safety
-- ============================================================================

-- Statement types for classification
DO $$ BEGIN
    CREATE TYPE papercheck.statement_type AS ENUM ('hypothesis', 'finding', 'conclusion');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Verdict types for final assessment
DO $$ BEGIN
    CREATE TYPE papercheck.verdict_type AS ENUM ('supports', 'contradicts', 'undecided');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Confidence levels for verdict certainty
DO $$ BEGIN
    CREATE TYPE papercheck.confidence_level AS ENUM ('high', 'medium', 'low');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Processing status tracking
DO $$ BEGIN
    CREATE TYPE papercheck.processing_status AS ENUM ('pending', 'processing', 'completed', 'failed');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Search strategy types
DO $$ BEGIN
    CREATE TYPE papercheck.search_strategy AS ENUM ('semantic', 'hyde', 'keyword');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

COMMENT ON TYPE papercheck.statement_type IS 'Types of statements extracted from abstracts';
COMMENT ON TYPE papercheck.verdict_type IS 'Possible verdicts for statement validation';
COMMENT ON TYPE papercheck.confidence_level IS 'Confidence levels for verdict assessment';
COMMENT ON TYPE papercheck.processing_status IS 'Status tracking for abstract processing';
COMMENT ON TYPE papercheck.search_strategy IS 'Search strategy types for counter-evidence';

-- ============================================================================
-- 1. abstracts_checked - Main table for abstracts being evaluated
-- ============================================================================

CREATE TABLE papercheck.abstracts_checked (
    id SERIAL PRIMARY KEY,
    -- Abstract content with reasonable length validation (min 50 chars, max 50KB)
    abstract_text TEXT NOT NULL CHECK (length(abstract_text) >= 50 AND length(abstract_text) <= 51200),

    -- Source metadata (optional if checking external abstracts)
    source_pmid INTEGER,
    source_doi TEXT,
    source_title TEXT,
    source_authors TEXT[],
    source_year INTEGER CHECK (source_year IS NULL OR (source_year >= 1800 AND source_year <= 2100)),
    source_journal TEXT,

    -- Processing metadata with duration tracking
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    checked_at TIMESTAMP DEFAULT NOW() NOT NULL,
    model_used VARCHAR(100) NOT NULL,
    config JSONB DEFAULT '{}'::jsonb,

    -- Results summary
    num_statements INTEGER CHECK (num_statements IS NULL OR num_statements >= 0),
    overall_assessment TEXT,
    processing_time_seconds FLOAT CHECK (processing_time_seconds IS NULL OR processing_time_seconds >= 0),

    -- Status tracking using enum type
    status papercheck.processing_status DEFAULT 'pending' NOT NULL,
    error_message TEXT,

    UNIQUE(source_pmid, checked_at),  -- Prevent duplicate checks
    CHECK (source_pmid IS NOT NULL OR source_doi IS NOT NULL),  -- Must have identifier
    CHECK (completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at)  -- Duration sanity
);

CREATE INDEX idx_abstracts_checked_pmid ON papercheck.abstracts_checked(source_pmid);
CREATE INDEX idx_abstracts_checked_doi ON papercheck.abstracts_checked(source_doi);
CREATE INDEX idx_abstracts_checked_date ON papercheck.abstracts_checked(checked_at DESC);
CREATE INDEX idx_abstracts_checked_status ON papercheck.abstracts_checked(status);

COMMENT ON TABLE papercheck.abstracts_checked IS 'Abstracts being checked with processing metadata and status';
COMMENT ON COLUMN papercheck.abstracts_checked.abstract_text IS 'Full abstract text being evaluated';
COMMENT ON COLUMN papercheck.abstracts_checked.source_pmid IS 'PubMed ID if from PubMed/PMC';
COMMENT ON COLUMN papercheck.abstracts_checked.source_doi IS 'DOI if available';
COMMENT ON COLUMN papercheck.abstracts_checked.model_used IS 'AI model used for processing (e.g., gpt-oss:20b)';
COMMENT ON COLUMN papercheck.abstracts_checked.config IS 'Complete configuration snapshot for reproducibility';
COMMENT ON COLUMN papercheck.abstracts_checked.overall_assessment IS 'High-level summary of paper quality assessment';

-- ============================================================================
-- 2. statements - Extracted key statements from abstracts
-- ============================================================================

CREATE TABLE papercheck.statements (
    id SERIAL PRIMARY KEY,
    abstract_id INTEGER NOT NULL REFERENCES papercheck.abstracts_checked(id) ON DELETE CASCADE,

    -- Statement content with length validation (min 10 chars, max 10KB)
    statement_text TEXT NOT NULL CHECK (length(statement_text) >= 10 AND length(statement_text) <= 10240),
    context TEXT CHECK (context IS NULL OR length(context) <= 20480),  -- Max 20KB for context

    -- Classification using enum type
    statement_type papercheck.statement_type NOT NULL,
    statement_order INTEGER NOT NULL CHECK (statement_order >= 1 AND statement_order <= 100),

    -- Extraction metadata
    extraction_confidence FLOAT CHECK (extraction_confidence BETWEEN 0.0 AND 1.0),
    extraction_model VARCHAR(100),
    extracted_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(abstract_id, statement_order)  -- One statement per order position
);

CREATE INDEX idx_statements_abstract ON papercheck.statements(abstract_id);
CREATE INDEX idx_statements_type ON papercheck.statements(statement_type);

COMMENT ON TABLE papercheck.statements IS 'Key statements extracted from abstracts (hypotheses, findings, conclusions)';
COMMENT ON COLUMN papercheck.statements.statement_text IS 'The extracted statement text';
COMMENT ON COLUMN papercheck.statements.context IS 'Surrounding sentences for context';
COMMENT ON COLUMN papercheck.statements.statement_type IS 'Type of statement: hypothesis, finding, or conclusion';
COMMENT ON COLUMN papercheck.statements.statement_order IS 'Order of statement within the abstract';

-- ============================================================================
-- 3. counter_statements - Counter-claims generated for each statement
-- ============================================================================

CREATE TABLE papercheck.counter_statements (
    id SERIAL PRIMARY KEY,
    statement_id INTEGER NOT NULL REFERENCES papercheck.statements(id) ON DELETE CASCADE,

    -- Counter-claim content with security constraints
    negated_text TEXT NOT NULL CHECK (length(negated_text) >= 10 AND length(negated_text) <= 10240),
    -- HyDE abstracts: at least 1, max 50 to prevent abuse
    hyde_abstracts TEXT[] NOT NULL CHECK (
        array_length(hyde_abstracts, 1) > 0 AND
        array_length(hyde_abstracts, 1) <= 50
    ),
    -- Keywords: at least 1, max 100 to prevent abuse
    keywords TEXT[] NOT NULL CHECK (
        array_length(keywords, 1) > 0 AND
        array_length(keywords, 1) <= 100
    ),

    -- Generation metadata
    generation_model VARCHAR(100),
    generation_config JSONB DEFAULT '{}'::jsonb,
    generated_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(statement_id)  -- One counter-statement per statement
);

CREATE INDEX idx_counter_statements_statement ON papercheck.counter_statements(statement_id);

COMMENT ON TABLE papercheck.counter_statements IS 'Counter-claims generated for statement verification';
COMMENT ON COLUMN papercheck.counter_statements.negated_text IS 'Negated version of the original statement';
COMMENT ON COLUMN papercheck.counter_statements.hyde_abstracts IS 'Hypothetical abstract examples for semantic search';
COMMENT ON COLUMN papercheck.counter_statements.keywords IS 'Keywords for keyword-based search';

-- ============================================================================
-- 4. search_results - Documents found through multi-strategy search
-- ============================================================================

CREATE TABLE papercheck.search_results (
    id SERIAL PRIMARY KEY,
    counter_statement_id INTEGER NOT NULL
        REFERENCES papercheck.counter_statements(id) ON DELETE CASCADE,

    -- Document reference
    doc_id INTEGER NOT NULL,  -- FK to public.documents (not enforced for flexibility)

    -- Search provenance using enum type
    search_strategy papercheck.search_strategy NOT NULL,
    search_rank INTEGER CHECK (search_rank IS NULL OR (search_rank >= 1 AND search_rank <= 1000)),
    search_score FLOAT CHECK (search_score IS NULL OR search_score >= 0),

    -- Metadata
    searched_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_search_results_counter ON papercheck.search_results(counter_statement_id);
CREATE INDEX idx_search_results_doc ON papercheck.search_results(doc_id);
CREATE INDEX idx_search_results_strategy ON papercheck.search_results(search_strategy);

COMMENT ON TABLE papercheck.search_results IS 'Documents found through semantic, HyDE, and keyword search strategies';
COMMENT ON COLUMN papercheck.search_results.doc_id IS 'Reference to document in public.documents table';
COMMENT ON COLUMN papercheck.search_results.search_strategy IS 'Strategy that found this document: semantic, hyde, or keyword';
COMMENT ON COLUMN papercheck.search_results.search_rank IS 'Rank within the search strategy results';
COMMENT ON COLUMN papercheck.search_results.search_score IS 'Relevance/similarity score from search';

-- ============================================================================
-- 5. scored_documents - Relevance-scored documents from search results
-- ============================================================================

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

COMMENT ON TABLE papercheck.scored_documents IS 'Documents scored for relevance to counter-statements';
COMMENT ON COLUMN papercheck.scored_documents.relevance_score IS 'Relevance score 1-5 (5 = highly relevant)';
COMMENT ON COLUMN papercheck.scored_documents.explanation IS 'Explanation of relevance assessment';
COMMENT ON COLUMN papercheck.scored_documents.supports_counter IS 'Whether document supports the counter-statement';
COMMENT ON COLUMN papercheck.scored_documents.found_by IS 'List of search strategies that found this document';

-- ============================================================================
-- 6. citations - Extracted passages from high-scoring documents
-- ============================================================================

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

COMMENT ON TABLE papercheck.citations IS 'Relevant passages extracted from high-scoring documents';
COMMENT ON COLUMN papercheck.citations.passage IS 'Extracted text passage supporting counter-statement';
COMMENT ON COLUMN papercheck.citations.relevance_score IS 'Relevance score of citation (1-5)';
COMMENT ON COLUMN papercheck.citations.citation_order IS 'Order of citation in report';
COMMENT ON COLUMN papercheck.citations.formatted_citation IS 'Full formatted citation (Author Year, Journal)';
COMMENT ON COLUMN papercheck.citations.doc_metadata IS 'Denormalized document metadata for quick access';

-- ============================================================================
-- 7. counter_reports - Generated reports for counter-statements
-- ============================================================================

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

COMMENT ON TABLE papercheck.counter_reports IS 'Reports synthesizing evidence for counter-statements';
COMMENT ON COLUMN papercheck.counter_reports.report_text IS 'Plain text report content';
COMMENT ON COLUMN papercheck.counter_reports.report_markdown IS 'Markdown-formatted report';
COMMENT ON COLUMN papercheck.counter_reports.num_citations IS 'Number of citations in report';
COMMENT ON COLUMN papercheck.counter_reports.search_stats IS 'Statistics about document search and scoring';

-- ============================================================================
-- 8. verdicts - Final verdicts on statements
-- ============================================================================

CREATE TABLE papercheck.verdicts (
    id SERIAL PRIMARY KEY,
    statement_id INTEGER NOT NULL
        REFERENCES papercheck.statements(id) ON DELETE CASCADE,

    -- Verdict using enum types for type safety
    verdict papercheck.verdict_type NOT NULL,
    rationale TEXT NOT NULL CHECK (length(rationale) >= 10 AND length(rationale) <= 20480),
    confidence papercheck.confidence_level NOT NULL,

    -- Analysis metadata
    analysis_model VARCHAR(100),
    analysis_config JSONB DEFAULT '{}'::jsonb,
    analyzed_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(statement_id)  -- One verdict per statement
);

CREATE INDEX idx_verdicts_statement ON papercheck.verdicts(statement_id);
CREATE INDEX idx_verdicts_verdict ON papercheck.verdicts(verdict);
CREATE INDEX idx_verdicts_confidence ON papercheck.verdicts(confidence);

COMMENT ON TABLE papercheck.verdicts IS 'Final verdicts on statement validity based on counter-evidence';
COMMENT ON COLUMN papercheck.verdicts.verdict IS 'Assessment: supports (confirmed), contradicts (refuted), or undecided';
COMMENT ON COLUMN papercheck.verdicts.rationale IS 'Explanation of verdict based on evidence';
COMMENT ON COLUMN papercheck.verdicts.confidence IS 'Confidence level in verdict: high, medium, or low';

-- ============================================================================
-- Composite Indexes for Common Query Patterns
-- ============================================================================

-- For filtering statements by abstract and type (common in reports)
CREATE INDEX idx_statements_abstract_type ON papercheck.statements(abstract_id, statement_type);

-- For scoring queries - finding high-scoring documents for counter-statements
CREATE INDEX idx_scored_docs_counter_score ON papercheck.scored_documents(counter_statement_id, relevance_score);

-- For finding supporting documents above threshold
CREATE INDEX idx_scored_docs_counter_supports ON papercheck.scored_documents(counter_statement_id, supports_counter)
    WHERE supports_counter = true;

-- For verdict analysis by confidence and verdict type
CREATE INDEX idx_verdicts_verdict_confidence ON papercheck.verdicts(verdict, confidence);

-- For search results by strategy and score (common in analytics)
CREATE INDEX idx_search_results_strategy_score ON papercheck.search_results(search_strategy, search_score DESC);

-- For citations ordered by counter-statement and relevance
CREATE INDEX idx_citations_counter_score ON papercheck.citations(counter_statement_id, relevance_score DESC);

-- For abstracts by status and date (operational queries)
CREATE INDEX idx_abstracts_status_date ON papercheck.abstracts_checked(status, checked_at DESC);

-- ============================================================================
-- Views for Convenient Queries
-- ============================================================================

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

COMMENT ON VIEW papercheck.v_complete_results IS 'Complete results for all checked abstracts with statement verdicts';

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

COMMENT ON VIEW papercheck.v_search_strategy_stats IS 'Statistics on effectiveness of different search strategies';

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

COMMENT ON VIEW papercheck.v_verdict_distribution IS 'Distribution of verdicts by type and confidence level';

-- ============================================================================
-- Utility Functions
-- ============================================================================

-- Function to get complete result for an abstract
-- Enhanced with error handling and validation
CREATE OR REPLACE FUNCTION papercheck.get_complete_result(p_abstract_id INTEGER)
RETURNS TABLE (
    statement_text TEXT,
    counter_statement TEXT,
    verdict papercheck.verdict_type,
    confidence papercheck.confidence_level,
    rationale TEXT,
    num_citations INTEGER,
    counter_report TEXT
) AS $$
DECLARE
    abstract_exists BOOLEAN;
BEGIN
    -- Validate input parameter
    IF p_abstract_id IS NULL THEN
        RAISE EXCEPTION 'abstract_id parameter cannot be NULL';
    END IF;

    -- Check if abstract exists
    SELECT EXISTS (
        SELECT 1 FROM papercheck.abstracts_checked WHERE id = p_abstract_id
    ) INTO abstract_exists;

    IF NOT abstract_exists THEN
        RAISE WARNING 'Abstract with id % does not exist', p_abstract_id;
        RETURN;  -- Return empty result set
    END IF;

    -- Return results
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

COMMENT ON FUNCTION papercheck.get_complete_result(INTEGER) IS 'Retrieve complete results for a specific abstract. Returns empty set if abstract not found.';

-- Function to clean up orphaned search results (docs not in main table)
-- Enhanced with error handling and transaction safety
CREATE OR REPLACE FUNCTION papercheck.cleanup_orphaned_search_results()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
    table_exists BOOLEAN;
BEGIN
    -- Verify public.documents table exists before attempting cleanup
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'documents'
    ) INTO table_exists;

    IF NOT table_exists THEN
        RAISE EXCEPTION 'public.documents table does not exist - cannot verify orphaned search results';
    END IF;

    -- Verify papercheck.search_results table exists
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'papercheck' AND table_name = 'search_results'
    ) INTO table_exists;

    IF NOT table_exists THEN
        RAISE NOTICE 'papercheck.search_results table does not exist - nothing to clean up';
        RETURN 0;
    END IF;

    -- Perform the cleanup with transaction safety
    BEGIN
        WITH deleted AS (
            DELETE FROM papercheck.search_results sr
            WHERE NOT EXISTS (
                SELECT 1 FROM public.documents d WHERE d.id = sr.doc_id
            )
            RETURNING *
        )
        SELECT COUNT(*) INTO deleted_count FROM deleted;

        IF deleted_count > 0 THEN
            RAISE NOTICE 'Cleaned up % orphaned search results', deleted_count;
        END IF;

        RETURN deleted_count;
    EXCEPTION
        WHEN OTHERS THEN
            RAISE WARNING 'Error during cleanup: % - %', SQLSTATE, SQLERRM;
            RETURN -1;  -- Indicate error condition
    END;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION papercheck.cleanup_orphaned_search_results() IS 'Remove search results referencing deleted documents. Returns -1 on error.';

-- ============================================================================
-- Migration Complete
-- ============================================================================

-- Log successful migration
DO $$
BEGIN
    RAISE NOTICE 'PaperCheck schema migration completed successfully';
    RAISE NOTICE 'Created schema: papercheck';
    RAISE NOTICE 'Created types: 5 (statement_type, verdict_type, confidence_level, processing_status, search_strategy)';
    RAISE NOTICE 'Created tables: 8 (abstracts_checked, statements, counter_statements, search_results, scored_documents, citations, counter_reports, verdicts)';
    RAISE NOTICE 'Created views: 3 (v_complete_results, v_search_strategy_stats, v_verdict_distribution)';
    RAISE NOTICE 'Created functions: 2 (get_complete_result, cleanup_orphaned_search_results)';
    RAISE NOTICE 'Created indexes: 22 (including 7 composite indexes for common query patterns)';
    RAISE NOTICE 'Migration tracking: Recorded in public.schema_migrations';
END $$;
