-- Migration 031: resumable bulk-import bookkeeping and revision-aware merges.
--
-- 1. document.date_revised (MedlineCitation/DateRevised): when a PMID arrives
--    again, the newest revision wins regardless of arrival order.
-- 2. ingest.ledger: one row per imported source file, written in the same
--    transaction as the file's data, so an import can be stopped at any point
--    and resumed exactly (see doc/planning/rust/implementation_plan.md §3.2).
-- 3. all_keywords: the trigger now returns the de-duplicated keywords sorted
--    (DISTINCT without ORDER BY gave plan-dependent order).
-- 4. idx_document_fts: fastupdate = off. With fastupdate on, one inserter pays
--    for flushing the whole GIN pending list (a 52-minute stall measured in
--    Phase 0); off is ~14 % faster overall with no stalls.
--
-- Idempotent: safe to run repeatedly.

ALTER TABLE public.document ADD COLUMN IF NOT EXISTS date_revised date;

CREATE SCHEMA IF NOT EXISTS ingest;

CREATE TABLE IF NOT EXISTS ingest.ledger (
    source text NOT NULL,
    file text NOT NULL,
    sha256 text,
    records integer NOT NULL,
    seconds real NOT NULL,
    finished_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (source, file)
);

COMMENT ON TABLE ingest.ledger IS
    'One row per imported source file, committed with the file''s data; a resumed import skips files listed here.';

CREATE OR REPLACE FUNCTION public.update_all_keywords_trigger()
RETURNS trigger LANGUAGE plpgsql AS $function$
BEGIN
  -- Combine, lowercase, de-duplicate and sort (stable output).
  NEW.all_keywords := (
    SELECT ARRAY(
      SELECT DISTINCT LOWER(element)
      FROM unnest(
        coalesce(NEW.keywords, '{}') ||
        coalesce(NEW.augmented_keywords, '{}') ||
        coalesce(NEW.mesh_terms, '{}')
      ) AS element
      WHERE element IS NOT NULL
      ORDER BY 1
    )
  );
  RETURN NEW;
END;
$function$;

DO $$
BEGIN
    IF to_regclass('public.idx_document_fts') IS NOT NULL THEN
        ALTER INDEX public.idx_document_fts SET (fastupdate = off);
    END IF;
END $$;
