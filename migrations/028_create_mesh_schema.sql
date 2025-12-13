-- Migration: Create MeSH (Medical Subject Headings) Schema
-- Description: Creates dedicated mesh schema for MeSH vocabulary storage and lookup
-- Source: NLM MeSH (https://www.nlm.nih.gov/mesh/)
-- Purpose: Local MeSH database for fast lookup with API fallback
-- Author: BMLibrarian
-- Date: 2025-12-13

-- ============================================================================
-- Create schema
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS mesh;

COMMENT ON SCHEMA mesh IS
'Medical Subject Headings (MeSH) controlled vocabulary from NLM.
Provides local storage for fast MeSH term lookup, validation, and expansion.
Supports ~30,000 descriptors with ~300,000 entry terms and hierarchical relationships.';

-- ============================================================================
-- Create descriptors table (main MeSH terms)
-- ============================================================================

CREATE TABLE IF NOT EXISTS mesh.descriptors (
    id SERIAL PRIMARY KEY,
    descriptor_ui TEXT NOT NULL UNIQUE,  -- e.g., D009203
    descriptor_name TEXT NOT NULL,        -- Preferred term, e.g., "Myocardial Infarction"
    scope_note TEXT,                      -- Definition/description
    annotation TEXT,                      -- Usage notes for indexers
    history_note TEXT,                    -- Historical information
    public_mesh_note TEXT,                -- Public notes
    nlm_classification TEXT,              -- NLM classification number
    date_created DATE,                    -- Date descriptor was created
    date_revised DATE,                    -- Date last revised
    date_established DATE,                -- Date established as MeSH term
    mesh_year INTEGER NOT NULL,           -- MeSH version year (e.g., 2025)
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE mesh.descriptors IS
'Main MeSH descriptors (controlled vocabulary headings).
Each descriptor represents a unique biomedical concept with a preferred name.
Expected scale: ~30,000 descriptors for current MeSH.';

COMMENT ON COLUMN mesh.descriptors.descriptor_ui IS 'Unique MeSH identifier (e.g., D009203 for Myocardial Infarction)';
COMMENT ON COLUMN mesh.descriptors.descriptor_name IS 'Preferred/canonical term for this descriptor';
COMMENT ON COLUMN mesh.descriptors.scope_note IS 'Definition and scope of the descriptor';
COMMENT ON COLUMN mesh.descriptors.annotation IS 'Indexing notes and usage guidelines';
COMMENT ON COLUMN mesh.descriptors.mesh_year IS 'MeSH vocabulary year (e.g., 2025)';

-- ============================================================================
-- Create concepts table (semantic units within descriptors)
-- ============================================================================

CREATE TABLE IF NOT EXISTS mesh.concepts (
    id SERIAL PRIMARY KEY,
    concept_ui TEXT NOT NULL UNIQUE,      -- e.g., M0014340
    concept_name TEXT NOT NULL,           -- Preferred concept name
    descriptor_id INTEGER NOT NULL REFERENCES mesh.descriptors(id) ON DELETE CASCADE,
    is_preferred BOOLEAN NOT NULL DEFAULT FALSE,  -- Is this the preferred concept?
    scope_note TEXT,                      -- Concept-specific scope note
    cas_registry_number TEXT,             -- Chemical Abstracts Service number (for chemicals)
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE mesh.concepts IS
'MeSH concepts - semantic units within descriptors.
A descriptor may have multiple concepts; one is marked as preferred.
Example: Descriptor "Heart Attack" has concepts for different clinical presentations.';

COMMENT ON COLUMN mesh.concepts.concept_ui IS 'Unique concept identifier (e.g., M0014340)';
COMMENT ON COLUMN mesh.concepts.is_preferred IS 'True if this is the preferred concept for the descriptor';
COMMENT ON COLUMN mesh.concepts.cas_registry_number IS 'CAS number for chemical substances';

-- ============================================================================
-- Create terms table (all term variants)
-- ============================================================================

CREATE TABLE IF NOT EXISTS mesh.terms (
    id SERIAL PRIMARY KEY,
    term_ui TEXT NOT NULL,                -- e.g., T000745
    term_text TEXT NOT NULL,              -- The actual term string
    concept_id INTEGER NOT NULL REFERENCES mesh.concepts(id) ON DELETE CASCADE,
    is_preferred BOOLEAN NOT NULL DEFAULT FALSE,  -- Preferred term for this concept?
    is_permuted BOOLEAN NOT NULL DEFAULT FALSE,   -- Is this a permuted term?
    lexical_tag TEXT,                     -- ABB, ABX, ACR, EPO, EQV, LAB, NAM, NON, TRD
    entry_combination TEXT,               -- Entry combination info
    sort_version TEXT,                    -- Sort key
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Constraint for lexical tags (MeSH 2025 values)
    CONSTRAINT chk_mesh_terms_lexical_tag
        CHECK (lexical_tag IS NULL OR lexical_tag IN (
            'ABB',   -- Abbreviation
            'ABX',   -- Embedded abbreviation
            'ACR',   -- Acronym
            'ACX',   -- Embedded acronym
            'EPO',   -- Eponym
            'EQV',   -- Equivalent term
            'HIST',  -- Historical term
            'LAB',   -- Lab number
            'NAM',   -- Proper name
            'NON',   -- None (standard term)
            'TRD'    -- Trade name
        ))
);

COMMENT ON TABLE mesh.terms IS
'All MeSH term variants (entry terms, synonyms, abbreviations).
Terms are linked to concepts, which are linked to descriptors.
Expected scale: ~300,000 terms for current MeSH.';

COMMENT ON COLUMN mesh.terms.term_ui IS 'Unique term identifier (e.g., T000745)';
COMMENT ON COLUMN mesh.terms.term_text IS 'Actual term string (e.g., "MI", "Heart Attack")';
COMMENT ON COLUMN mesh.terms.is_preferred IS 'True if this is the preferred term for the concept';
COMMENT ON COLUMN mesh.terms.lexical_tag IS 'Term type: ABB (abbreviation), ACR (acronym), TRD (trade name), etc.';

-- ============================================================================
-- Create tree_numbers table (hierarchical structure)
-- ============================================================================

CREATE TABLE IF NOT EXISTS mesh.tree_numbers (
    id SERIAL PRIMARY KEY,
    descriptor_id INTEGER NOT NULL REFERENCES mesh.descriptors(id) ON DELETE CASCADE,
    tree_number TEXT NOT NULL,            -- e.g., C14.280.647.500
    tree_level INTEGER NOT NULL,          -- Depth in hierarchy (1 = top)
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Ensure unique tree numbers per descriptor
    CONSTRAINT uq_mesh_tree_numbers UNIQUE(descriptor_id, tree_number),

    -- Validate tree number format
    CONSTRAINT chk_mesh_tree_format CHECK (tree_number ~ '^[A-Z][0-9]{2}(\.[0-9]+)*$'),

    -- Validate tree level
    CONSTRAINT chk_mesh_tree_level CHECK (tree_level >= 1 AND tree_level <= 15)
);

COMMENT ON TABLE mesh.tree_numbers IS
'MeSH tree structure for hierarchical navigation.
Tree numbers encode the hierarchy: C14.280.647.500 = Diseases > Cardiovascular > Heart > Ischemia > Infarction.
Used for broader/narrower term navigation.';

COMMENT ON COLUMN mesh.tree_numbers.tree_number IS 'Hierarchical tree number (e.g., C14.280.647.500)';
COMMENT ON COLUMN mesh.tree_numbers.tree_level IS 'Depth in tree (1 = top level category)';

-- ============================================================================
-- Create qualifiers table (subheadings)
-- ============================================================================

CREATE TABLE IF NOT EXISTS mesh.qualifiers (
    id SERIAL PRIMARY KEY,
    qualifier_ui TEXT NOT NULL UNIQUE,    -- e.g., Q000175
    qualifier_name TEXT NOT NULL,         -- e.g., "diagnosis"
    abbreviation TEXT NOT NULL,           -- e.g., "DI"
    scope_note TEXT,
    annotation TEXT,
    mesh_year INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE mesh.qualifiers IS
'MeSH qualifiers (subheadings) that can modify descriptors.
Example: "therapy" (TH), "diagnosis" (DI), "adverse effects" (AE).
Expected scale: ~80 qualifiers.';

-- ============================================================================
-- Create allowable_qualifiers table (descriptor-qualifier pairs)
-- ============================================================================

CREATE TABLE IF NOT EXISTS mesh.allowable_qualifiers (
    id SERIAL PRIMARY KEY,
    descriptor_id INTEGER NOT NULL REFERENCES mesh.descriptors(id) ON DELETE CASCADE,
    qualifier_id INTEGER NOT NULL REFERENCES mesh.qualifiers(id) ON DELETE CASCADE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Each pair is unique
    CONSTRAINT uq_mesh_allowable_qualifiers UNIQUE(descriptor_id, qualifier_id)
);

COMMENT ON TABLE mesh.allowable_qualifiers IS
'Maps which qualifiers can be used with which descriptors.
Not all combinations are valid in MeSH.';

-- ============================================================================
-- Create supplementary_concepts table (SCRs - chemicals, drugs, etc.)
-- ============================================================================

CREATE TABLE IF NOT EXISTS mesh.supplementary_concepts (
    id SERIAL PRIMARY KEY,
    supplemental_ui TEXT NOT NULL UNIQUE,  -- e.g., C000657245
    supplemental_name TEXT NOT NULL,
    note TEXT,
    cas_registry_number TEXT,
    frequency INTEGER,                     -- Usage frequency in MEDLINE
    heading_mapped_to TEXT[],              -- Array of descriptor UIs
    indexing_information TEXT,
    mesh_year INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE mesh.supplementary_concepts IS
'MeSH Supplementary Concept Records (SCRs) for chemicals, drugs, diseases.
Mapped to main descriptors but provide more specific terminology.
Expected scale: ~300,000 SCRs.';

-- ============================================================================
-- Create import_history table
-- ============================================================================

CREATE TABLE IF NOT EXISTS mesh.import_history (
    id SERIAL PRIMARY KEY,
    mesh_year INTEGER NOT NULL,
    import_type TEXT NOT NULL,            -- 'full', 'incremental', 'supplementary'
    file_name TEXT,
    file_size_bytes BIGINT,
    descriptors_imported INTEGER NOT NULL DEFAULT 0,
    concepts_imported INTEGER NOT NULL DEFAULT 0,
    terms_imported INTEGER NOT NULL DEFAULT 0,
    tree_numbers_imported INTEGER NOT NULL DEFAULT 0,
    qualifiers_imported INTEGER NOT NULL DEFAULT 0,
    scrs_imported INTEGER NOT NULL DEFAULT 0,
    import_status TEXT NOT NULL DEFAULT 'in_progress',
    started_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP,
    error_message TEXT,

    -- Validate import status
    CONSTRAINT chk_mesh_import_status
        CHECK (import_status IN ('in_progress', 'completed', 'failed', 'partial')),

    -- Validate import type
    CONSTRAINT chk_mesh_import_type
        CHECK (import_type IN ('full', 'incremental', 'supplementary'))
);

COMMENT ON TABLE mesh.import_history IS
'Audit trail for MeSH imports. Tracks statistics and status for each import operation.';

-- ============================================================================
-- Create indexes for performance
-- ============================================================================

-- Descriptors indexes
CREATE INDEX IF NOT EXISTS idx_mesh_descriptors_name_lower
    ON mesh.descriptors(LOWER(descriptor_name));

CREATE INDEX IF NOT EXISTS idx_mesh_descriptors_name_gin
    ON mesh.descriptors USING gin(to_tsvector('english', descriptor_name));

CREATE INDEX IF NOT EXISTS idx_mesh_descriptors_year
    ON mesh.descriptors(mesh_year);

-- Concepts indexes
CREATE INDEX IF NOT EXISTS idx_mesh_concepts_descriptor
    ON mesh.concepts(descriptor_id);

CREATE INDEX IF NOT EXISTS idx_mesh_concepts_preferred
    ON mesh.concepts(descriptor_id, is_preferred) WHERE is_preferred = TRUE;

-- Terms indexes
CREATE INDEX IF NOT EXISTS idx_mesh_terms_text_lower
    ON mesh.terms(LOWER(term_text));

CREATE INDEX IF NOT EXISTS idx_mesh_terms_text_gin
    ON mesh.terms USING gin(to_tsvector('english', term_text));

CREATE INDEX IF NOT EXISTS idx_mesh_terms_concept
    ON mesh.terms(concept_id);

CREATE INDEX IF NOT EXISTS idx_mesh_terms_preferred
    ON mesh.terms(concept_id, is_preferred) WHERE is_preferred = TRUE;

-- Combined search index (term_ui + text)
CREATE INDEX IF NOT EXISTS idx_mesh_terms_ui_text
    ON mesh.terms(term_ui, LOWER(term_text));

-- Tree numbers indexes
CREATE INDEX IF NOT EXISTS idx_mesh_tree_descriptor
    ON mesh.tree_numbers(descriptor_id);

CREATE INDEX IF NOT EXISTS idx_mesh_tree_number
    ON mesh.tree_numbers(tree_number);

CREATE INDEX IF NOT EXISTS idx_mesh_tree_pattern
    ON mesh.tree_numbers(tree_number text_pattern_ops);

CREATE INDEX IF NOT EXISTS idx_mesh_tree_level
    ON mesh.tree_numbers(tree_level);

-- Qualifiers indexes
CREATE INDEX IF NOT EXISTS idx_mesh_qualifiers_name
    ON mesh.qualifiers(LOWER(qualifier_name));

CREATE INDEX IF NOT EXISTS idx_mesh_qualifiers_abbrev
    ON mesh.qualifiers(abbreviation);

-- Supplementary concepts indexes
CREATE INDEX IF NOT EXISTS idx_mesh_scr_name_lower
    ON mesh.supplementary_concepts(LOWER(supplemental_name));

CREATE INDEX IF NOT EXISTS idx_mesh_scr_name_gin
    ON mesh.supplementary_concepts USING gin(to_tsvector('english', supplemental_name));

CREATE INDEX IF NOT EXISTS idx_mesh_scr_cas
    ON mesh.supplementary_concepts(cas_registry_number) WHERE cas_registry_number IS NOT NULL;

-- ============================================================================
-- Create triggers for auto-updating timestamps
-- ============================================================================

CREATE OR REPLACE FUNCTION mesh.update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_mesh_descriptors_updated_at ON mesh.descriptors;
CREATE TRIGGER trigger_mesh_descriptors_updated_at
    BEFORE UPDATE ON mesh.descriptors
    FOR EACH ROW
    EXECUTE FUNCTION mesh.update_updated_at();

-- ============================================================================
-- Create utility functions
-- ============================================================================

-- Function: Look up a MeSH term and return descriptor info
CREATE OR REPLACE FUNCTION mesh.lookup_term(search_term TEXT)
RETURNS TABLE(
    descriptor_ui TEXT,
    descriptor_name TEXT,
    matched_term TEXT,
    is_preferred_term BOOLEAN,
    lexical_tag TEXT,
    scope_note TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT DISTINCT
        d.descriptor_ui,
        d.descriptor_name,
        t.term_text AS matched_term,
        (t.is_preferred AND c.is_preferred) AS is_preferred_term,
        t.lexical_tag,
        d.scope_note
    FROM mesh.terms t
    JOIN mesh.concepts c ON t.concept_id = c.id
    JOIN mesh.descriptors d ON c.descriptor_id = d.id
    WHERE LOWER(t.term_text) = LOWER(search_term)
    ORDER BY is_preferred_term DESC, d.descriptor_name;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION mesh.lookup_term(TEXT) IS
'Look up a MeSH term by exact match and return descriptor information.
Returns multiple rows if term maps to multiple descriptors.
Example: mesh.lookup_term(''heart attack'')';

-- Function: Get all entry terms (synonyms) for a descriptor
CREATE OR REPLACE FUNCTION mesh.get_entry_terms(p_descriptor_ui TEXT)
RETURNS TABLE(
    term_text TEXT,
    is_preferred BOOLEAN,
    lexical_tag TEXT,
    concept_name TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        t.term_text,
        (t.is_preferred AND c.is_preferred) AS is_preferred,
        t.lexical_tag,
        c.concept_name
    FROM mesh.terms t
    JOIN mesh.concepts c ON t.concept_id = c.id
    JOIN mesh.descriptors d ON c.descriptor_id = d.id
    WHERE d.descriptor_ui = p_descriptor_ui
    ORDER BY is_preferred DESC, t.term_text;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION mesh.get_entry_terms(TEXT) IS
'Get all entry terms (synonyms) for a descriptor by UI.
Example: mesh.get_entry_terms(''D009203'')';

-- Function: Get tree hierarchy for a descriptor
CREATE OR REPLACE FUNCTION mesh.get_tree_hierarchy(p_descriptor_ui TEXT)
RETURNS TABLE(
    tree_number TEXT,
    tree_level INTEGER,
    parent_tree_number TEXT,
    parent_descriptor_ui TEXT,
    parent_descriptor_name TEXT
) AS $$
BEGIN
    RETURN QUERY
    WITH descriptor_trees AS (
        SELECT tn.tree_number, tn.tree_level
        FROM mesh.tree_numbers tn
        JOIN mesh.descriptors d ON tn.descriptor_id = d.id
        WHERE d.descriptor_ui = p_descriptor_ui
    )
    SELECT
        dt.tree_number,
        dt.tree_level,
        substring(dt.tree_number from '^(.+)\.[^.]+$') AS parent_tree_number,
        pd.descriptor_ui AS parent_descriptor_ui,
        pd.descriptor_name AS parent_descriptor_name
    FROM descriptor_trees dt
    LEFT JOIN mesh.tree_numbers ptn ON ptn.tree_number = substring(dt.tree_number from '^(.+)\.[^.]+$')
    LEFT JOIN mesh.descriptors pd ON ptn.descriptor_id = pd.id
    ORDER BY dt.tree_number;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION mesh.get_tree_hierarchy(TEXT) IS
'Get tree hierarchy information for a descriptor, including parent terms.
Example: mesh.get_tree_hierarchy(''D009203'')';

-- Function: Get broader (parent) terms
CREATE OR REPLACE FUNCTION mesh.get_broader_terms(p_descriptor_ui TEXT)
RETURNS TABLE(
    descriptor_ui TEXT,
    descriptor_name TEXT,
    tree_number TEXT,
    tree_level INTEGER
) AS $$
BEGIN
    RETURN QUERY
    WITH input_trees AS (
        SELECT tn.tree_number, tn.tree_level
        FROM mesh.tree_numbers tn
        JOIN mesh.descriptors d ON tn.descriptor_id = d.id
        WHERE d.descriptor_ui = p_descriptor_ui
    ),
    parent_trees AS (
        SELECT DISTINCT substring(it.tree_number from '^(.+)\.[^.]+$') AS parent_tree
        FROM input_trees it
        WHERE it.tree_number ~ '\.'
    )
    SELECT DISTINCT
        d.descriptor_ui,
        d.descriptor_name,
        tn.tree_number,
        tn.tree_level
    FROM mesh.tree_numbers tn
    JOIN mesh.descriptors d ON tn.descriptor_id = d.id
    JOIN parent_trees pt ON tn.tree_number = pt.parent_tree
    ORDER BY tn.tree_level, d.descriptor_name;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION mesh.get_broader_terms(TEXT) IS
'Get broader (parent) terms in the MeSH hierarchy.
Example: mesh.get_broader_terms(''D009203'') -- parents of Myocardial Infarction';

-- Function: Get narrower (child) terms
CREATE OR REPLACE FUNCTION mesh.get_narrower_terms(p_descriptor_ui TEXT)
RETURNS TABLE(
    descriptor_ui TEXT,
    descriptor_name TEXT,
    tree_number TEXT,
    tree_level INTEGER
) AS $$
BEGIN
    RETURN QUERY
    WITH input_trees AS (
        SELECT tn.tree_number, tn.tree_level
        FROM mesh.tree_numbers tn
        JOIN mesh.descriptors d ON tn.descriptor_id = d.id
        WHERE d.descriptor_ui = p_descriptor_ui
    )
    SELECT DISTINCT
        d.descriptor_ui,
        d.descriptor_name,
        tn.tree_number,
        tn.tree_level
    FROM mesh.tree_numbers tn
    JOIN mesh.descriptors d ON tn.descriptor_id = d.id
    JOIN input_trees it ON tn.tree_number LIKE it.tree_number || '.%'
    WHERE tn.tree_level = it.tree_level + 1  -- Only immediate children
    ORDER BY tn.tree_number, d.descriptor_name;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION mesh.get_narrower_terms(TEXT) IS
'Get narrower (child) terms in the MeSH hierarchy (immediate children only).
Example: mesh.get_narrower_terms(''D006331'') -- children of Heart Diseases';

-- Function: Search MeSH by partial match
CREATE OR REPLACE FUNCTION mesh.search(
    search_text TEXT,
    max_results INTEGER DEFAULT 20
)
RETURNS TABLE(
    descriptor_ui TEXT,
    descriptor_name TEXT,
    matched_term TEXT,
    match_type TEXT,
    score REAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT DISTINCT ON (d.descriptor_ui)
        d.descriptor_ui,
        d.descriptor_name,
        t.term_text AS matched_term,
        CASE
            WHEN LOWER(d.descriptor_name) = LOWER(search_text) THEN 'exact_preferred'
            WHEN LOWER(t.term_text) = LOWER(search_text) THEN 'exact_entry'
            WHEN d.descriptor_name ILIKE search_text || '%' THEN 'prefix_preferred'
            WHEN t.term_text ILIKE search_text || '%' THEN 'prefix_entry'
            ELSE 'partial'
        END AS match_type,
        ts_rank(
            to_tsvector('english', d.descriptor_name || ' ' || COALESCE(d.scope_note, '')),
            plainto_tsquery('english', search_text)
        ) AS score
    FROM mesh.terms t
    JOIN mesh.concepts c ON t.concept_id = c.id
    JOIN mesh.descriptors d ON c.descriptor_id = d.id
    WHERE
        LOWER(d.descriptor_name) LIKE '%' || LOWER(search_text) || '%'
        OR LOWER(t.term_text) LIKE '%' || LOWER(search_text) || '%'
        OR to_tsvector('english', d.descriptor_name) @@ plainto_tsquery('english', search_text)
    ORDER BY
        d.descriptor_ui,
        CASE match_type
            WHEN 'exact_preferred' THEN 1
            WHEN 'exact_entry' THEN 2
            WHEN 'prefix_preferred' THEN 3
            WHEN 'prefix_entry' THEN 4
            ELSE 5
        END,
        score DESC
    LIMIT max_results;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION mesh.search(TEXT, INTEGER) IS
'Search MeSH by partial text match on descriptors and entry terms.
Returns ranked results with match type classification.
Example: mesh.search(''heart attack'', 10)';

-- Function: Expand a term to all synonyms
CREATE OR REPLACE FUNCTION mesh.expand_term(search_term TEXT)
RETURNS TABLE(
    term_text TEXT,
    is_original BOOLEAN,
    lexical_tag TEXT,
    descriptor_ui TEXT,
    descriptor_name TEXT
) AS $$
BEGIN
    RETURN QUERY
    WITH matched_descriptors AS (
        SELECT DISTINCT d.id, d.descriptor_ui, d.descriptor_name
        FROM mesh.terms t
        JOIN mesh.concepts c ON t.concept_id = c.id
        JOIN mesh.descriptors d ON c.descriptor_id = d.id
        WHERE LOWER(t.term_text) = LOWER(search_term)
    )
    SELECT DISTINCT
        t.term_text,
        (LOWER(t.term_text) = LOWER(search_term)) AS is_original,
        t.lexical_tag,
        md.descriptor_ui,
        md.descriptor_name
    FROM mesh.terms t
    JOIN mesh.concepts c ON t.concept_id = c.id
    JOIN matched_descriptors md ON c.descriptor_id = md.id
    ORDER BY is_original DESC, t.term_text;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION mesh.expand_term(TEXT) IS
'Expand a MeSH term to all its synonyms/entry terms.
Example: mesh.expand_term(''MI'') returns Myocardial Infarction, Heart Attack, etc.';

-- Function: Get statistics
CREATE OR REPLACE FUNCTION mesh.get_statistics()
RETURNS TABLE(
    stat_name TEXT,
    stat_value BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 'descriptors'::TEXT, COUNT(*)::BIGINT FROM mesh.descriptors
    UNION ALL
    SELECT 'concepts', COUNT(*) FROM mesh.concepts
    UNION ALL
    SELECT 'terms', COUNT(*) FROM mesh.terms
    UNION ALL
    SELECT 'tree_numbers', COUNT(*) FROM mesh.tree_numbers
    UNION ALL
    SELECT 'qualifiers', COUNT(*) FROM mesh.qualifiers
    UNION ALL
    SELECT 'supplementary_concepts', COUNT(*) FROM mesh.supplementary_concepts
    ORDER BY stat_name;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION mesh.get_statistics() IS
'Get counts of all MeSH entities in the database.';

-- ============================================================================
-- Grant permissions
-- ============================================================================

GRANT USAGE ON SCHEMA mesh TO PUBLIC;
GRANT SELECT ON ALL TABLES IN SCHEMA mesh TO PUBLIC;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA mesh TO PUBLIC;

-- ============================================================================
-- Migration complete
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE 'Migration 028: MeSH schema created successfully';
    RAISE NOTICE 'Tables created: descriptors, concepts, terms, tree_numbers, qualifiers, supplementary_concepts, import_history';
    RAISE NOTICE 'Functions created: lookup_term, get_entry_terms, get_tree_hierarchy, get_broader_terms, get_narrower_terms, search, expand_term, get_statistics';
    RAISE NOTICE 'Next steps:';
    RAISE NOTICE '  1. Run mesh_import_cli.py to download and import MeSH data';
    RAISE NOTICE '  2. Verify import with: SELECT * FROM mesh.get_statistics();';
    RAISE NOTICE '  3. Test lookup with: SELECT * FROM mesh.lookup_term(''heart attack'');';
END $$;
