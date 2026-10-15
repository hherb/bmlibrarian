-- Migration 033: fold document.withdrawn into the baseline withdrawn_date column.
--
-- The first revision of migration 032 added document.withdrawn (date), but the
-- baseline schema already had document.withdrawn_date / withdrawn_reason, and
-- every search function filters on withdrawn_date. Records marked only in
-- document.withdrawn therefore stayed searchable. This migration copies those
-- marks into withdrawn_date / withdrawn_reason and drops the redundant column.
--
-- No information is lost: the copy happens in the same transaction before the
-- drop, and ingest.withdrawn_pmid keeps every withdrawn PMID with its date.
-- The copy walks ingest.withdrawn_pmid (thousands of rows) through
-- idx_document_external_id instead of scanning the whole document table.
--
-- Databases created after 032 was revised never had the column: no-op there.
-- Idempotent: safe to run repeatedly.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = 'public' AND table_name = 'document'
                 AND column_name = 'withdrawn') THEN
        UPDATE public.document d
           SET withdrawn_date = d.withdrawn::timestamp,
               withdrawn_reason = 'PubMed DeleteCitation'
          FROM ingest.withdrawn_pmid w
         WHERE d.external_id = w.pmid
           AND d.withdrawn IS NOT NULL
           AND d.withdrawn_date IS NULL;

        ALTER TABLE public.document DROP COLUMN withdrawn;
    END IF;
END $$;
