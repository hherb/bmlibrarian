-- Migration 032: PubMed withdrawals (DeleteCitation) are marked, not deleted.
--
-- PubMed update files list PMIDs that NCBI has withdrawn (duplicates, records
-- created in error) in <DeleteCitation>. Deleting those rows would break
-- references to them (citations, fact-check evidence, embeddings), so they are
-- kept and marked instead:
--
-- 1. document.withdrawn: the date the withdrawal was imported (NULL = current).
--    Searches exclude rows where it is set.
-- 2. ingest.withdrawn_pmid: every withdrawn PMID with the file that listed it.
--    The importer marks documents from this table both when a deletion is
--    imported and when a record arrives, so files can still be imported in any
--    order (a deletion seen before its record still applies).
--
-- ADD COLUMN without a default is a metadata-only change (no table rewrite).
-- Idempotent: safe to run repeatedly.

ALTER TABLE public.document ADD COLUMN IF NOT EXISTS withdrawn date;

COMMENT ON COLUMN public.document.withdrawn IS
    'Date the source withdrew this record (PubMed DeleteCitation); NULL = current. Searches exclude withdrawn rows.';

CREATE SCHEMA IF NOT EXISTS ingest;

CREATE TABLE IF NOT EXISTS ingest.withdrawn_pmid (
    pmid text PRIMARY KEY,
    file text NOT NULL,
    withdrawn date NOT NULL DEFAULT CURRENT_DATE
);

COMMENT ON TABLE ingest.withdrawn_pmid IS
    'PMIDs withdrawn by PubMed (DeleteCitation), with the update file that listed them.';
