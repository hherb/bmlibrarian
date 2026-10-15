-- Migration 032: PubMed withdrawals (DeleteCitation) are marked, not deleted.
--
-- PubMed update files list PMIDs that NCBI has withdrawn (duplicates, records
-- created in error) in <DeleteCitation>. Deleting those rows would break
-- references to them (citations, fact-check evidence, embeddings), so they are
-- kept and marked instead, in the baseline schema's existing columns
-- document.withdrawn_date / document.withdrawn_reason. Every search function
-- (fulltext_search, bm25, semantic_docsearch, the chunk searches) already
-- excludes rows where withdrawn_date is set.
--
-- ingest.withdrawn_pmid records every withdrawn PMID with the file that listed
-- it. The importer marks documents from this table both when a deletion is
-- imported and when a record arrives, so files can still be imported in any
-- order (a deletion seen before its record still applies).
--
-- An earlier revision of this migration also added a separate
-- document.withdrawn column; migration 033 folds it into withdrawn_date.
--
-- Idempotent: safe to run repeatedly.

CREATE SCHEMA IF NOT EXISTS ingest;

CREATE TABLE IF NOT EXISTS ingest.withdrawn_pmid (
    pmid text PRIMARY KEY,
    file text NOT NULL,
    withdrawn date NOT NULL DEFAULT CURRENT_DATE
);

COMMENT ON TABLE ingest.withdrawn_pmid IS
    'PMIDs withdrawn by PubMed (DeleteCitation), with the file that listed them and the date BMLibrarian recorded the withdrawal.';
