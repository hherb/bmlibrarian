-- Per-session staging tables for the COPY variants (shared by Python and Rust).
-- `ord` keeps file order so the merge keeps the last occurrence of a PMID,
-- which is what the row-at-a-time importer ends up with.
-- Statements are separated by a line holding only the separator marker (two dashes, space, two semicolons).

CREATE TEMP TABLE IF NOT EXISTS stage_document (
    ord integer,
    external_id text,
    doi text,
    title text,
    abstract text,
    authors text[],
    publication text,
    publication_date date,
    url text,
    mesh_terms text[],
    keywords text[]
) ON COMMIT DELETE ROWS;
-- ;;
CREATE TEMP TABLE IF NOT EXISTS stage_metadata (
    ord integer,
    external_id text,
    grants jsonb,
    publication_types text[],
    is_retracted boolean,
    author_affiliations jsonb
) ON COMMIT DELETE ROWS;
