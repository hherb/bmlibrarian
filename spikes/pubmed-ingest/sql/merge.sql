-- Set-based merge shared by every COPY variant (Python P2/P3 and Rust R1/R2),
-- read from this file at runtime so both languages run byte-identical SQL.
-- Staging tables are session TEMP tables created by `staging.sql`.
-- Semantics mirror PubMedBulkImporter._store_article_batch: insert new rows;
-- for existing rows COALESCE doi/abstract/publication/date and overwrite
-- title/authors/mesh/keywords. Transparency rows mirror
-- _store_transparency_metadata_batch's ON CONFLICT clause.
-- Statements are separated by a line holding only the separator marker (two dashes, space, two semicolons).

INSERT INTO spike_ingest.document (
    source_id, external_id, doi, title, abstract, authors, publication,
    publication_date, url, mesh_terms, keywords)
SELECT DISTINCT ON (external_id)
    1, external_id, doi, title, abstract, authors, publication,
    publication_date, url, mesh_terms, keywords
FROM stage_document
ORDER BY external_id, ord DESC
ON CONFLICT (source_id, external_id) DO UPDATE SET
    doi = COALESCE(EXCLUDED.doi, spike_ingest.document.doi),
    title = EXCLUDED.title,
    abstract = COALESCE(EXCLUDED.abstract, spike_ingest.document.abstract),
    authors = EXCLUDED.authors,
    publication = COALESCE(EXCLUDED.publication, spike_ingest.document.publication),
    publication_date = COALESCE(EXCLUDED.publication_date, spike_ingest.document.publication_date),
    mesh_terms = EXCLUDED.mesh_terms,
    keywords = EXCLUDED.keywords,
    updated_date = CURRENT_TIMESTAMP;
-- ;;
INSERT INTO spike_ingest.document_metadata (
    document_id, grants, publication_types, is_retracted, author_affiliations, source)
SELECT DISTINCT ON (d.id)
    d.id, m.grants, m.publication_types, m.is_retracted, m.author_affiliations, 'pubmed_bulk'
FROM stage_metadata m
JOIN spike_ingest.document d ON d.source_id = 1 AND d.external_id = m.external_id
ORDER BY d.id, m.ord DESC
ON CONFLICT (document_id) DO UPDATE SET
    grants = COALESCE(EXCLUDED.grants, spike_ingest.document_metadata.grants),
    publication_types = COALESCE(EXCLUDED.publication_types, spike_ingest.document_metadata.publication_types),
    is_retracted = EXCLUDED.is_retracted OR spike_ingest.document_metadata.is_retracted,
    author_affiliations = COALESCE(EXCLUDED.author_affiliations, spike_ingest.document_metadata.author_affiliations),
    imported_at = NOW();
