-- Migration 035: record which citations were widened from a quoted fragment.
--
-- When the model quotes a verbatim fragment of a sentence, the citation is
-- stored as the abstract's complete enclosing sentence(s) (PR #306). The
-- model's summary and relevance score describe the fragment, so reviewers
-- need to know a passage was widened (issue #310). widened_from holds the
-- fragment as it appears in the abstract; NULL means the passage was quoted
-- as a whole (or was stored before this migration).
--
-- Additive and nullable: existing rows are untouched.
-- Idempotent: safe to run repeatedly; each table is skipped where its schema
-- (audit: migration 003, factcheck: migration 008) does not exist.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema = 'audit' AND table_name = 'extracted_citations') THEN
        ALTER TABLE audit.extracted_citations
            ADD COLUMN IF NOT EXISTS widened_from TEXT;

        COMMENT ON COLUMN audit.extracted_citations.widened_from IS
            'The quoted fragment as it appears in the abstract, when passage was widened to its complete sentence(s); NULL = quoted as a whole';
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema = 'factcheck' AND table_name = 'evidence') THEN
        ALTER TABLE factcheck.evidence
            ADD COLUMN IF NOT EXISTS widened_from TEXT;

        COMMENT ON COLUMN factcheck.evidence.widened_from IS
            'The quoted fragment as it appears in the abstract, when citation_text was widened to its complete sentence(s); NULL = quoted as a whole';
    END IF;
END $$;
