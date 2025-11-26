-- Migration: Create Medical Thesaurus Schema
-- Description: Creates thesaurus schema for medical terminology, synonyms, abbreviations, and hierarchical relationships
-- Primary Source: MeSH (Medical Subject Headings) from NLM
-- Purpose: Enable keyword expansion for improved literature search recall
-- Author: BMLibrarian
-- Date: 2025-11-26

-- ============================================================================
-- Create schema
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS thesaurus;

COMMENT ON SCHEMA thesaurus IS
'Medical terminology thesaurus for keyword expansion in literature search.
Primary source: MeSH (Medical Subject Headings) from NLM.
Supports term expansion, synonym lookup, abbreviation resolution, and hierarchical navigation.';

-- ============================================================================
-- Create concepts table
-- Stores main medical concepts with definitions and source tracking
-- ============================================================================

CREATE TABLE IF NOT EXISTS thesaurus.concepts (
    concept_id SERIAL PRIMARY KEY,
    preferred_term TEXT NOT NULL,
    definition TEXT,
    semantic_type TEXT,
    source_vocabulary TEXT NOT NULL DEFAULT 'mesh',
    source_concept_id TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Ensure unique concepts per source vocabulary
    CONSTRAINT uq_thesaurus_concepts_source
        UNIQUE(source_vocabulary, source_concept_id),

    -- Validate vocabulary names
    CONSTRAINT chk_thesaurus_concepts_vocabulary
        CHECK (source_vocabulary IN ('mesh', 'rxnorm', 'loinc', 'snomed', 'umls', 'custom'))
);

-- Add table comment
COMMENT ON TABLE thesaurus.concepts IS
'Main medical concepts table. Each concept represents a unique medical term with a preferred name.
Example: Concept "Myocardial Infarction" (D009203) with 6 term variants.
Expected scale: ~30,000 rows for MeSH, ~400,000 for full UMLS.';

-- Add column comments
COMMENT ON COLUMN thesaurus.concepts.concept_id IS 'Internal primary key for concept';
COMMENT ON COLUMN thesaurus.concepts.preferred_term IS 'Canonical/preferred term for this concept (e.g., "Myocardial Infarction")';
COMMENT ON COLUMN thesaurus.concepts.definition IS 'Concept definition from source vocabulary (MeSH ScopeNote)';
COMMENT ON COLUMN thesaurus.concepts.semantic_type IS 'Semantic category (disease, drug, procedure, anatomy, etc.)';
COMMENT ON COLUMN thesaurus.concepts.source_vocabulary IS 'Source vocabulary: mesh, rxnorm, loinc, snomed, umls, custom';
COMMENT ON COLUMN thesaurus.concepts.source_concept_id IS 'Original ID from source vocabulary (e.g., MeSH DescriptorUI "D009203")';

-- ============================================================================
-- Create terms table
-- Stores all term variants (preferred, synonyms, abbreviations, trade names)
-- ============================================================================

CREATE TABLE IF NOT EXISTS thesaurus.terms (
    term_id SERIAL PRIMARY KEY,
    concept_id INTEGER NOT NULL REFERENCES thesaurus.concepts(concept_id) ON DELETE CASCADE,
    term_text TEXT NOT NULL,
    term_type TEXT NOT NULL,
    lexical_tag TEXT,
    case_sensitive BOOLEAN NOT NULL DEFAULT FALSE,
    source_term_id TEXT,
    language TEXT NOT NULL DEFAULT 'en',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Validate term types
    CONSTRAINT chk_thesaurus_terms_type
        CHECK (term_type IN ('preferred', 'synonym', 'abbreviation', 'trade_name', 'obsolete')),

    -- Validate lexical tags (MeSH tags)
    CONSTRAINT chk_thesaurus_terms_lexical_tag
        CHECK (lexical_tag IS NULL OR lexical_tag IN ('NON', 'ABB', 'SYN', 'TRD', 'OBS')),

    -- Validate language codes
    CONSTRAINT chk_thesaurus_terms_language
        CHECK (language ~ '^[a-z]{2}$')
);

-- Add table comment
COMMENT ON TABLE thesaurus.terms IS
'All term variants for concepts including synonyms, abbreviations, and trade names.
Example: For concept "Myocardial Infarction", terms include "MI", "Heart Attack", "AMI", etc.
Expected scale: ~300,000 rows for MeSH, ~14 million for full UMLS.';

-- Add column comments
COMMENT ON COLUMN thesaurus.terms.term_id IS 'Internal primary key for term';
COMMENT ON COLUMN thesaurus.terms.concept_id IS 'Foreign key to parent concept';
COMMENT ON COLUMN thesaurus.terms.term_text IS 'Actual term string (e.g., "MI", "Heart Attack")';
COMMENT ON COLUMN thesaurus.terms.term_type IS 'Simplified term type: preferred, synonym, abbreviation, trade_name, obsolete';
COMMENT ON COLUMN thesaurus.terms.lexical_tag IS 'Original MeSH lexical tag: NON (preferred), ABB (abbreviation), SYN (synonym), TRD (trade name)';
COMMENT ON COLUMN thesaurus.terms.case_sensitive IS 'Whether term matching should be case-sensitive (usually false for medical terms)';
COMMENT ON COLUMN thesaurus.terms.source_term_id IS 'Original term ID from source vocabulary (e.g., MeSH TermUI "T000745")';
COMMENT ON COLUMN thesaurus.terms.language IS 'ISO 639-1 two-letter language code (en, de, fr, etc.)';

-- ============================================================================
-- Create concept_hierarchies table
-- Stores hierarchical relationships using MeSH tree numbers
-- ============================================================================

CREATE TABLE IF NOT EXISTS thesaurus.concept_hierarchies (
    hierarchy_id SERIAL PRIMARY KEY,
    concept_id INTEGER NOT NULL REFERENCES thesaurus.concepts(concept_id) ON DELETE CASCADE,
    tree_number TEXT NOT NULL,
    tree_level INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Ensure unique tree numbers per concept
    CONSTRAINT uq_thesaurus_hierarchies_concept_tree
        UNIQUE(concept_id, tree_number),

    -- Validate tree number format (e.g., "C14.280.647.500")
    CONSTRAINT chk_thesaurus_hierarchies_tree_format
        CHECK (tree_number ~ '^[A-Z][0-9]{2}(\.[0-9]+)*$'),

    -- Validate tree level
    CONSTRAINT chk_thesaurus_hierarchies_level
        CHECK (tree_level >= 1 AND tree_level <= 10)
);

-- Add table comment
COMMENT ON TABLE thesaurus.concept_hierarchies IS
'Hierarchical classification of concepts using MeSH tree numbers.
Tree numbers like "C14.280.647.500" represent: C (Diseases) > 14 (Cardiovascular) > 280 (Heart) > 647 (Ischemia) > 500 (Infarction).
Supports broader/narrower term navigation for query expansion.';

-- Add column comments
COMMENT ON COLUMN thesaurus.concept_hierarchies.hierarchy_id IS 'Internal primary key for hierarchy entry';
COMMENT ON COLUMN thesaurus.concept_hierarchies.concept_id IS 'Foreign key to concept';
COMMENT ON COLUMN thesaurus.concept_hierarchies.tree_number IS 'MeSH tree number (e.g., "C14.280.647.500")';
COMMENT ON COLUMN thesaurus.concept_hierarchies.tree_level IS 'Depth in tree hierarchy (1=top level, higher=more specific)';

-- ============================================================================
-- Create import_history table
-- Tracks vocabulary imports for version control and auditing
-- ============================================================================

CREATE TABLE IF NOT EXISTS thesaurus.import_history (
    import_id SERIAL PRIMARY KEY,
    source_vocabulary TEXT NOT NULL,
    source_version TEXT,
    import_date TIMESTAMP NOT NULL DEFAULT NOW(),
    concepts_imported INTEGER NOT NULL DEFAULT 0,
    terms_imported INTEGER NOT NULL DEFAULT 0,
    hierarchies_imported INTEGER NOT NULL DEFAULT 0,
    import_duration_seconds INTEGER,
    import_status TEXT NOT NULL DEFAULT 'completed',
    notes TEXT,

    -- Validate import status
    CONSTRAINT chk_thesaurus_import_status
        CHECK (import_status IN ('completed', 'failed', 'partial', 'in_progress')),

    -- Validate counts
    CONSTRAINT chk_thesaurus_import_counts
        CHECK (concepts_imported >= 0 AND terms_imported >= 0 AND hierarchies_imported >= 0)
);

-- Add table comment
COMMENT ON TABLE thesaurus.import_history IS
'Import history and audit trail for vocabulary updates.
Tracks version numbers, import statistics, and status for each vocabulary load.';

-- Add column comments
COMMENT ON COLUMN thesaurus.import_history.import_id IS 'Internal primary key for import record';
COMMENT ON COLUMN thesaurus.import_history.source_vocabulary IS 'Vocabulary imported (mesh, rxnorm, loinc, etc.)';
COMMENT ON COLUMN thesaurus.import_history.source_version IS 'Version identifier (e.g., "2025" for MeSH 2025)';
COMMENT ON COLUMN thesaurus.import_history.concepts_imported IS 'Number of concepts added/updated in this import';
COMMENT ON COLUMN thesaurus.import_history.terms_imported IS 'Number of terms added/updated in this import';
COMMENT ON COLUMN thesaurus.import_history.hierarchies_imported IS 'Number of hierarchy relationships added';
COMMENT ON COLUMN thesaurus.import_history.import_duration_seconds IS 'Time taken for import in seconds';
COMMENT ON COLUMN thesaurus.import_history.import_status IS 'Import status: completed, failed, partial, in_progress';

-- ============================================================================
-- Create indexes for performance
-- ============================================================================

-- Concepts table indexes
CREATE INDEX IF NOT EXISTS idx_thesaurus_concepts_preferred_term
    ON thesaurus.concepts(LOWER(preferred_term));

CREATE INDEX IF NOT EXISTS idx_thesaurus_concepts_preferred_term_gin
    ON thesaurus.concepts USING gin(to_tsvector('english', preferred_term));

CREATE INDEX IF NOT EXISTS idx_thesaurus_concepts_source
    ON thesaurus.concepts(source_vocabulary, source_concept_id);

CREATE INDEX IF NOT EXISTS idx_thesaurus_concepts_semantic_type
    ON thesaurus.concepts(semantic_type) WHERE semantic_type IS NOT NULL;

-- Terms table indexes
CREATE INDEX IF NOT EXISTS idx_thesaurus_terms_text_lower
    ON thesaurus.terms(LOWER(term_text));

CREATE INDEX IF NOT EXISTS idx_thesaurus_terms_text_gin
    ON thesaurus.terms USING gin(to_tsvector('english', term_text));

CREATE INDEX IF NOT EXISTS idx_thesaurus_terms_concept
    ON thesaurus.terms(concept_id);

CREATE INDEX IF NOT EXISTS idx_thesaurus_terms_type
    ON thesaurus.terms(term_type);

CREATE INDEX IF NOT EXISTS idx_thesaurus_terms_source
    ON thesaurus.terms(source_term_id) WHERE source_term_id IS NOT NULL;

-- Hierarchies table indexes
CREATE INDEX IF NOT EXISTS idx_thesaurus_hierarchies_concept
    ON thesaurus.concept_hierarchies(concept_id);

CREATE INDEX IF NOT EXISTS idx_thesaurus_hierarchies_tree
    ON thesaurus.concept_hierarchies(tree_number);

CREATE INDEX IF NOT EXISTS idx_thesaurus_hierarchies_tree_pattern
    ON thesaurus.concept_hierarchies(tree_number text_pattern_ops);

CREATE INDEX IF NOT EXISTS idx_thesaurus_hierarchies_level
    ON thesaurus.concept_hierarchies(tree_level);

-- Import history indexes
CREATE INDEX IF NOT EXISTS idx_thesaurus_import_history_vocabulary
    ON thesaurus.import_history(source_vocabulary, source_version);

CREATE INDEX IF NOT EXISTS idx_thesaurus_import_history_date
    ON thesaurus.import_history(import_date DESC);

-- ============================================================================
-- Create utility functions
-- ============================================================================

-- Function: Expand a term to all its synonyms and variants
CREATE OR REPLACE FUNCTION thesaurus.get_all_synonyms(input_term TEXT)
RETURNS TABLE(
    synonym TEXT,
    term_type TEXT,
    preferred_term TEXT,
    concept_id INTEGER
) AS $$
BEGIN
    RETURN QUERY
    WITH matched_concepts AS (
        SELECT DISTINCT c.concept_id, c.preferred_term
        FROM thesaurus.terms t
        JOIN thesaurus.concepts c ON t.concept_id = c.concept_id
        WHERE LOWER(t.term_text) = LOWER(input_term)
    )
    SELECT DISTINCT
        t.term_text AS synonym,
        t.term_type,
        mc.preferred_term,
        mc.concept_id
    FROM thesaurus.terms t
    JOIN matched_concepts mc ON t.concept_id = mc.concept_id
    WHERE LOWER(t.term_text) != LOWER(input_term)
    ORDER BY t.term_type, t.term_text;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION thesaurus.get_all_synonyms(TEXT) IS
'Expand an input term to all its variants (synonyms, abbreviations, etc.).
Example: get_all_synonyms(''MI'') returns [''Myocardial Infarction'', ''Heart Attack'', ''AMI'', etc.]
Excludes the input term itself from results.';

-- Function: Get complete term expansion including input term
CREATE OR REPLACE FUNCTION thesaurus.expand_term(input_term TEXT)
RETURNS TABLE(
    term TEXT,
    term_type TEXT,
    preferred_term TEXT,
    concept_id INTEGER,
    is_input_term BOOLEAN
) AS $$
BEGIN
    RETURN QUERY
    WITH matched_concepts AS (
        SELECT DISTINCT c.concept_id, c.preferred_term
        FROM thesaurus.terms t
        JOIN thesaurus.concepts c ON t.concept_id = c.concept_id
        WHERE LOWER(t.term_text) = LOWER(input_term)
    )
    SELECT DISTINCT
        t.term_text AS term,
        t.term_type,
        mc.preferred_term,
        mc.concept_id,
        LOWER(t.term_text) = LOWER(input_term) AS is_input_term
    FROM thesaurus.terms t
    JOIN matched_concepts mc ON t.concept_id = mc.concept_id
    ORDER BY is_input_term DESC, t.term_type, t.term_text;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION thesaurus.expand_term(TEXT) IS
'Complete term expansion including the input term itself.
Returns all variants for the concept(s) matching the input term.
The is_input_term column indicates which term matches the input.';

-- Function: Get broader terms via hierarchical navigation
CREATE OR REPLACE FUNCTION thesaurus.get_broader_terms(input_term TEXT)
RETURNS TABLE(
    broader_term TEXT,
    tree_number TEXT,
    tree_level INTEGER,
    concept_id INTEGER
) AS $$
BEGIN
    RETURN QUERY
    WITH input_concepts AS (
        SELECT DISTINCT c.concept_id, h.tree_number, h.tree_level
        FROM thesaurus.terms t
        JOIN thesaurus.concepts c ON t.concept_id = c.concept_id
        JOIN thesaurus.concept_hierarchies h ON c.concept_id = h.concept_id
        WHERE LOWER(t.term_text) = LOWER(input_term)
    ),
    parent_trees AS (
        SELECT
            ic.concept_id AS child_concept_id,
            substring(ic.tree_number from '^(.+)\.[^.]+$') AS parent_tree,
            ic.tree_level - 1 AS parent_level
        FROM input_concepts ic
        WHERE ic.tree_number ~ '\.'  -- Has at least one dot (not root level)
    )
    SELECT DISTINCT
        c.preferred_term AS broader_term,
        h.tree_number,
        h.tree_level,
        c.concept_id
    FROM thesaurus.concept_hierarchies h
    JOIN thesaurus.concepts c ON h.concept_id = c.concept_id
    JOIN parent_trees pt ON h.tree_number = pt.parent_tree
    ORDER BY h.tree_level, c.preferred_term;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION thesaurus.get_broader_terms(TEXT) IS
'Get broader (parent) terms in the MeSH hierarchy.
Example: get_broader_terms(''Myocardial Infarction'') returns [''Myocardial Ischemia'', ''Heart Diseases'', etc.]
Uses MeSH tree numbers to navigate hierarchical relationships.';

-- Function: Get narrower terms via hierarchical navigation
CREATE OR REPLACE FUNCTION thesaurus.get_narrower_terms(input_term TEXT)
RETURNS TABLE(
    narrower_term TEXT,
    tree_number TEXT,
    tree_level INTEGER,
    concept_id INTEGER
) AS $$
BEGIN
    RETURN QUERY
    WITH input_concepts AS (
        SELECT DISTINCT c.concept_id, h.tree_number, h.tree_level
        FROM thesaurus.terms t
        JOIN thesaurus.concepts c ON t.concept_id = c.concept_id
        JOIN thesaurus.concept_hierarchies h ON c.concept_id = h.concept_id
        WHERE LOWER(t.term_text) = LOWER(input_term)
    )
    SELECT DISTINCT
        c.preferred_term AS narrower_term,
        h.tree_number,
        h.tree_level,
        c.concept_id
    FROM thesaurus.concept_hierarchies h
    JOIN thesaurus.concepts c ON h.concept_id = c.concept_id
    JOIN input_concepts ic ON h.tree_number LIKE ic.tree_number || '.%'
    WHERE h.tree_level = ic.tree_level + 1  -- Only immediate children
    ORDER BY h.tree_number, c.preferred_term;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION thesaurus.get_narrower_terms(TEXT) IS
'Get narrower (child) terms in the MeSH hierarchy.
Example: get_narrower_terms(''Heart Diseases'') returns [''Arrhythmias'', ''Cardiomyopathies'', ''Myocardial Ischemia'', etc.]
Returns only immediate children (one level down).';

-- Function: Get all terms for a concept by concept ID
CREATE OR REPLACE FUNCTION thesaurus.get_concept_terms(p_concept_id INTEGER)
RETURNS TABLE(
    term TEXT,
    term_type TEXT,
    lexical_tag TEXT,
    is_preferred BOOLEAN
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        t.term_text AS term,
        t.term_type,
        t.lexical_tag,
        (t.term_type = 'preferred') AS is_preferred
    FROM thesaurus.terms t
    WHERE t.concept_id = p_concept_id
    ORDER BY is_preferred DESC, t.term_type, t.term_text;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION thesaurus.get_concept_terms(INTEGER) IS
'Get all terms for a specific concept by concept_id.
Useful for programmatic access when concept ID is already known.';

-- Function: Search concepts by partial text match
CREATE OR REPLACE FUNCTION thesaurus.search_concepts(search_text TEXT, max_results INTEGER DEFAULT 20)
RETURNS TABLE(
    concept_id INTEGER,
    preferred_term TEXT,
    definition TEXT,
    match_type TEXT,
    rank REAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT DISTINCT
        c.concept_id,
        c.preferred_term,
        c.definition,
        CASE
            WHEN LOWER(c.preferred_term) = LOWER(search_text) THEN 'exact'
            WHEN LOWER(t.term_text) = LOWER(search_text) THEN 'exact_variant'
            WHEN c.preferred_term ILIKE search_text || '%' THEN 'prefix'
            WHEN t.term_text ILIKE search_text || '%' THEN 'prefix_variant'
            ELSE 'partial'
        END AS match_type,
        ts_rank(
            to_tsvector('english', c.preferred_term || ' ' || COALESCE(c.definition, '')),
            plainto_tsquery('english', search_text)
        ) AS rank
    FROM thesaurus.concepts c
    LEFT JOIN thesaurus.terms t ON c.concept_id = t.concept_id
    WHERE
        LOWER(c.preferred_term) LIKE '%' || LOWER(search_text) || '%'
        OR LOWER(t.term_text) LIKE '%' || LOWER(search_text) || '%'
        OR to_tsvector('english', c.preferred_term || ' ' || COALESCE(c.definition, '')) @@ plainto_tsquery('english', search_text)
    ORDER BY
        CASE match_type
            WHEN 'exact' THEN 1
            WHEN 'exact_variant' THEN 2
            WHEN 'prefix' THEN 3
            WHEN 'prefix_variant' THEN 4
            ELSE 5
        END,
        rank DESC,
        c.preferred_term
    LIMIT max_results;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION thesaurus.search_concepts(TEXT, INTEGER) IS
'Search for concepts by partial text match on preferred terms, variants, or definitions.
Returns ranked results with match type classification (exact, prefix, partial).
Default limit: 20 results.';

-- ============================================================================
-- Grant permissions
-- ============================================================================

-- Grant usage on schema
GRANT USAGE ON SCHEMA thesaurus TO PUBLIC;

-- Grant read access on tables
GRANT SELECT ON ALL TABLES IN SCHEMA thesaurus TO PUBLIC;

-- Grant execute on functions
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA thesaurus TO PUBLIC;

-- ============================================================================
-- Migration complete
-- ============================================================================

-- Insert migration record
DO $$
BEGIN
    RAISE NOTICE 'Migration 021: Thesaurus schema created successfully';
    RAISE NOTICE 'Next steps:';
    RAISE NOTICE '  1. Run thesaurus_import_cli.py to import MeSH data';
    RAISE NOTICE '  2. Verify import with: SELECT * FROM thesaurus.import_history;';
    RAISE NOTICE '  3. Test expansion with: SELECT * FROM thesaurus.expand_term(''MI'');';
END $$;
