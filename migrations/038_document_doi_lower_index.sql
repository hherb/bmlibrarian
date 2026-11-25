-- Migration: Case-insensitive DOI index
-- Description: DOIs are case-insensitive (DOI Handbook), so lookups compare
--              LOWER(doi). Without an expression index each such lookup scans
--              the whole document table (~2 min on the full PubMed import).
--              Built CONCURRENTLY so imports and searches keep running; on
--              ~41 M rows the build takes several minutes. Issue #333.
-- Author: BMLibrarian
-- Date: 2026-11-25

-- ============================================================================
-- Expression index on lower(doi)
-- ============================================================================

-- Used by every `LOWER(doi) = LOWER(%s)` lookup (PDF matching, verification
-- prompt, paper reviewer, Europe PMC cross-source matching). The migration
-- manager runs CONCURRENTLY statements outside the transaction and rebuilds
-- an index left invalid by an interrupted build.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_document_doi_lower
ON public.document (lower(doi));
