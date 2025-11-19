-- Migration: Add context and long_answer columns to factcheck.statements
-- Description: Adds columns for PubMedQA abstracts (CONTEXTS) and reasoning (LONG_ANSWER)
-- Author: BMLibrarian
-- Date: 2025-11-19

-- ============================================================================
-- Add columns to factcheck.statements table
-- ============================================================================

-- Add context column (stores abstract/background from CONTEXTS field)
ALTER TABLE factcheck.statements
ADD COLUMN IF NOT EXISTS context TEXT;

-- Add long_answer column (stores reasoning from LONG_ANSWER field)
ALTER TABLE factcheck.statements
ADD COLUMN IF NOT EXISTS long_answer TEXT;

-- ============================================================================
-- Add comments for documentation
-- ============================================================================

COMMENT ON COLUMN factcheck.statements.context IS 'Abstract/background text from PubMedQA CONTEXTS field (joined array of context paragraphs)';
COMMENT ON COLUMN factcheck.statements.long_answer IS 'Detailed reasoning for the answer from PubMedQA LONG_ANSWER field';

-- ============================================================================
-- Migration Complete
-- ============================================================================
