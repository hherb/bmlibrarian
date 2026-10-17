-- Migration 034: flag fact-check verdicts that rest on partial evidence.
--
-- A verdict can be reached although part of the evidence could not be
-- examined: a search strategy failed, some documents could not be scored, or
-- some passages could not be extracted (PR #298). Such verdicts are stored
-- with factcheck.ai_evaluations.degradation_notes, a JSON list of strings
-- describing what is missing. NULL means the check was complete.
--
-- Additive and nullable: existing rows are untouched.
-- Idempotent: safe to run repeatedly; a no-op where the factcheck schema
-- (migration 008) does not exist.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema = 'factcheck' AND table_name = 'ai_evaluations') THEN
        ALTER TABLE factcheck.ai_evaluations
            ADD COLUMN IF NOT EXISTS degradation_notes JSONB;

        COMMENT ON COLUMN factcheck.ai_evaluations.degradation_notes IS
            'Evidence that could not be examined for this verdict (JSON list of strings); NULL = complete check';
    END IF;
END $$;
