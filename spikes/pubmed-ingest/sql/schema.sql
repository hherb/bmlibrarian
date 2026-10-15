-- Phase 0a ingest spike: a copy of public.document and
-- transparency.document_metadata, with the same columns, indexes, generated
-- search_vector and keyword trigger, so every variant pays the same per-row
-- database cost as production. FKs to sources/categories are dropped.
-- Idempotent. Only ever applied to bmlibrarian_dev (the runners refuse other DBs).

CREATE SCHEMA IF NOT EXISTS spike_ingest;

CREATE OR REPLACE FUNCTION spike_ingest.update_all_keywords_trigger()
RETURNS trigger LANGUAGE plpgsql AS $function$
BEGIN
  NEW.all_keywords := (
    SELECT ARRAY(
      SELECT DISTINCT LOWER(element)
      FROM unnest(
        coalesce(NEW.keywords, '{}') ||
        coalesce(NEW.augmented_keywords, '{}') ||
        coalesce(NEW.mesh_terms, '{}')
      ) AS element
      WHERE element IS NOT NULL
    )
  );
  RETURN NEW;
END;
$function$;

CREATE TABLE IF NOT EXISTS spike_ingest.document (
    id serial PRIMARY KEY,
    source_id integer,
    external_id text,
    doi text,
    title text,
    abstract text,
    category_id integer,
    keywords text[],
    augmented_keywords text[],
    mesh_terms text[],
    authors text[],
    publication text,
    publication_date date,
    url text,
    pdf_url text,
    pdf_filename text,
    full_text text,
    added_date timestamp DEFAULT CURRENT_TIMESTAMP,
    updated_date timestamp DEFAULT CURRENT_TIMESTAMP,
    withdrawn_date timestamp,
    withdrawn_reason text,
    all_keywords text[],
    abstract_length integer,
    missing_details boolean DEFAULT false,
    search_vector tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english'::regconfig, COALESCE(title, '')), 'A') ||
        setweight(to_tsvector('english'::regconfig, COALESCE(abstract, '')), 'B')
    ) STORED,
    CONSTRAINT spike_document_source_external_key UNIQUE (source_id, external_id)
);

CREATE INDEX IF NOT EXISTS spike_doc_publication_date ON spike_ingest.document (publication_date);
CREATE INDEX IF NOT EXISTS spike_doc_added_date ON spike_ingest.document (added_date);
CREATE INDEX IF NOT EXISTS spike_doc_updated_date ON spike_ingest.document (updated_date);
CREATE INDEX IF NOT EXISTS spike_doc_doi ON spike_ingest.document (doi) WITH (deduplicate_items = true);
CREATE INDEX IF NOT EXISTS spike_doc_external_id ON spike_ingest.document (external_id);
-- The FTS index exists only while the table has search_vector (long_run.py's
-- default "no-fts" variant drops the column; BM25 is meant to move to tantivy).
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'spike_ingest'
               AND table_name = 'document' AND column_name = 'search_vector') THEN
        CREATE INDEX IF NOT EXISTS spike_doc_fts ON spike_ingest.document USING gin (search_vector);
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS spike_doc_source_pubdate ON spike_ingest.document (source_id, publication_date)
    WHERE publication_date IS NOT NULL;
CREATE INDEX IF NOT EXISTS spike_doc_source_doi ON spike_ingest.document (source_id, doi)
    WHERE doi IS NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'spike_update_all_keywords'
                   AND tgrelid = 'spike_ingest.document'::regclass) THEN
        CREATE TRIGGER spike_update_all_keywords BEFORE INSERT OR UPDATE ON spike_ingest.document
            FOR EACH ROW EXECUTE FUNCTION spike_ingest.update_all_keywords_trigger();
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS spike_ingest.document_metadata (
    id serial PRIMARY KEY,
    document_id integer UNIQUE,
    grants jsonb,
    publication_types text[],
    is_retracted boolean DEFAULT false,
    retraction_reason text,
    retraction_date date,
    retraction_source text,
    author_affiliations jsonb,
    clinical_trial_id text,
    trial_sponsor text,
    trial_sponsor_class text,
    trial_status text,
    source text,
    imported_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS spike_meta_document_id ON spike_ingest.document_metadata (document_id);
CREATE INDEX IF NOT EXISTS spike_meta_retracted ON spike_ingest.document_metadata (is_retracted)
    WHERE is_retracted = true;
CREATE INDEX IF NOT EXISTS spike_meta_trial ON spike_ingest.document_metadata (clinical_trial_id)
    WHERE clinical_trial_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS spike_meta_sponsor ON spike_ingest.document_metadata (trial_sponsor_class)
    WHERE trial_sponsor_class IS NOT NULL;
CREATE INDEX IF NOT EXISTS spike_meta_grants ON spike_ingest.document_metadata USING gin (grants)
    WHERE grants IS NOT NULL;

-- Ingest ledger: one row per committed file, written in the same transaction
-- as the file's data, so a crash/kill at any point leaves either the whole file
-- or none of it, and a restart skips exactly the committed files.
CREATE TABLE IF NOT EXISTS spike_ingest.ingest_ledger (
    file text PRIMARY KEY,
    articles integer NOT NULL,
    seconds real NOT NULL,
    finished_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
