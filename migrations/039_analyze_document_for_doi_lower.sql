-- Migration: Statistics for the lower(doi) index
-- Description: PostgreSQL only gathers statistics for an expression index
--              (idx_document_doi_lower, migration 038) at the next ANALYZE of
--              the table, which autovacuum may not run for a long time on a
--              large, mostly static table. Until then the planner assumes a
--              DOI matches ~0.5% of all rows, and
--              `WHERE LOWER(doi) = ... ORDER BY id LIMIT 1` walks the primary
--              key over the whole table instead of using the index. ANALYZE
--              samples a fixed number of rows (~5 s on 41 M rows) and is safe
--              to repeat. A separate file because the migration manager builds
--              038's CONCURRENTLY index after that file's other statements.
-- Author: BMLibrarian
-- Date: 2026-11-25

ANALYZE public.document;
