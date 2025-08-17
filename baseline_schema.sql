--
-- PostgreSQL database dump
--

-- Dumped from database version 16.8 (Postgres.app)
-- Dumped by pg_dump version 16.8 (Postgres.app)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: unpaywall; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA unpaywall;


--
-- Name: plpython3u; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS plpython3u WITH SCHEMA pg_catalog;


--
-- Name: EXTENSION plpython3u; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION plpython3u IS 'PL/Python3U untrusted procedural language';


--
-- Name: pg_trgm; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;


--
-- Name: EXTENSION pg_trgm; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pg_trgm IS 'text similarity measurement and index searching based on trigrams';


--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: EXTENSION vector; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';


--
-- Name: generate_embedding(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.generate_embedding() RETURNS trigger
    LANGUAGE plpython3u
    AS $$
    # Use SD to cache the imported module per connection
    if 'ollama' not in SD:
        import ollama
        SD['ollama'] = ollama
    
    ollama = SD['ollama']
    
    # Process the embedding with the cached module
    try:
        response = ollama.embeddings(
            model="snowflake-arctic-embed2:latest",
            prompt=TD["new"]["text_content"]
        )
        TD["new"]["embedding_vector"] = response.get("embedding")
    except Exception as e:
        plpy.warning(f"Embedding generation error: {str(e)}")
    
    return "MODIFY"
$$;


--
-- Name: get_all_urls_for_doi(text); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.get_all_urls_for_doi(input_doi text) RETURNS TABLE(url text, location_type text, version text, host_type text, oa_status text, is_oa boolean, quality_score integer, rank integer)
    LANGUAGE sql
    AS $$
    SELECT 
        dur.url,
        dur.location_type,
        dur.version,
        dur.host_type,
        dur.oa_status,
        dur.is_oa,
        dur.url_quality_score,
        dur.rank::INTEGER
    FROM doi_urls_ranked dur
    WHERE dur.doi = input_doi
    ORDER BY dur.rank;
$$;


--
-- Name: get_oa_urls_for_doi(text); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.get_oa_urls_for_doi(input_doi text) RETURNS TABLE(url text, location_type text, version text, host_type text, oa_status text, quality_score integer, rank integer)
    LANGUAGE sql
    AS $$
    SELECT 
        doar.url,
        doar.location_type,
        doar.version,
        doar.host_type,
        doar.oa_status,
        doar.url_quality_score,
        doar.rank::INTEGER
    FROM doi_oa_urls_ranked doar
    WHERE doar.doi = input_doi
    ORDER BY doar.rank;
$$;


--
-- Name: get_quality_urls_for_doi(text, integer); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.get_quality_urls_for_doi(input_doi text, min_quality integer DEFAULT 60) RETURNS TABLE(url text, location_type text, oa_status text, quality_score integer, is_oa boolean)
    LANGUAGE sql
    AS $$
    SELECT 
        dur.url,
        dur.location_type,
        dur.oa_status,
        dur.url_quality_score,
        dur.is_oa
    FROM doi_urls_ranked dur
    WHERE dur.doi = input_doi 
      AND dur.url_quality_score >= min_quality
    ORDER BY dur.rank;
$$;


--
-- Name: ollama_embedding(text); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.ollama_embedding(text_content text) RETURNS public.vector
    LANGUAGE plpython3u
    AS $$
    if 'ollama' not in SD:
        import ollama
        SD['ollama'] = ollama

    ollama = SD['ollama']
    
    try:
        response = ollama.embeddings(
            model="snowflake-arctic-embed2:latest",
            prompt=text_content
        )
        return response.get("embedding")
    except Exception as e:
        plpy.warning(f"Embedding generation error: {str(e)}")
        return None
$$;


--
-- Name: test_generate_embedding(text); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.test_generate_embedding(text_content text) RETURNS public.vector
    LANGUAGE plpython3u
    AS $$
    if 'ollama' not in SD:
        import ollama
        SD['ollama'] = ollama

    ollama = SD['ollama']
    
    try:
        response = ollama.embeddings(
            model="snowflake-arctic-embed2:latest",
            prompt=text_content
        )
        return response.get("embedding")
    except Exception as e:
        plpy.warning(f"Embedding generation error: {str(e)}")
        return None
$$;


--
-- Name: trg_bump_version_and_timestamp(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.trg_bump_version_and_timestamp() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF NEW IS DISTINCT FROM OLD THEN
        NEW.updated_at := CURRENT_TIMESTAMP;
        NEW.evaluation_version := OLD.evaluation_version + 1;
    END IF;
    RETURN NEW;
END;
$$;


--
-- Name: trg_update_timestamp_on_status_change(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.trg_update_timestamp_on_status_change() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF NEW.is_active IS DISTINCT FROM OLD.is_active THEN
        NEW.updated_at := CURRENT_TIMESTAMP;
    END IF;
    RETURN NEW;
END;
$$;


--
-- Name: trim_text_array(text[], integer); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.trim_text_array(input text[], max_bytes integer) RETURNS text[]
    LANGUAGE plpgsql
    AS $$
DECLARE
    output text[] := '{}';
    total_bytes integer := 0;
    elem text;
BEGIN
    FOREACH elem IN ARRAY input LOOP
        total_bytes := total_bytes + length(elem)::integer;  -- length() gives byte count in PostgreSQL
        IF total_bytes > max_bytes THEN
            RETURN output;
        END IF;
        output := array_append(output, elem);
    END LOOP;
    RETURN output;
END;
$$;


--
-- Name: update_all_keywords_trigger(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_all_keywords_trigger() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
    BEGIN
      -- Combine, lowercase, and de-duplicate
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
    $$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: bookmarks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bookmarks (
    id integer NOT NULL,
    document_id integer NOT NULL,
    user_id integer NOT NULL,
    project_id integer,
    bookmark_type text NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT bookmarks_bookmark_type_check CHECK ((bookmark_type = ANY (ARRAY['personal'::text, 'project'::text, 'both'::text])))
);


--
-- Name: bookmarks_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.bookmarks_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: bookmarks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.bookmarks_id_seq OWNED BY public.bookmarks.id;


--
-- Name: categories; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.categories (
    id integer NOT NULL,
    name text NOT NULL,
    description text
);


--
-- Name: categories_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.categories_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: categories_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.categories_id_seq OWNED BY public.categories.id;


--
-- Name: chunking_strategies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.chunking_strategies (
    id integer NOT NULL,
    strategy_name text NOT NULL,
    modelname text,
    parameters jsonb
);


--
-- Name: chunking_strategies_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.chunking_strategies_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: chunking_strategies_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.chunking_strategies_id_seq OWNED BY public.chunking_strategies.id;


--
-- Name: chunks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.chunks (
    id integer NOT NULL,
    document_id integer,
    chunking_strategy_id integer,
    chunktype_id integer,
    document_title text,
    text text,
    chunklength integer,
    chunk_no integer NOT NULL,
    page_start integer DEFAULT 0,
    page_end integer DEFAULT 0,
    metadata jsonb
);


--
-- Name: chunks_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.chunks_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: chunks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.chunks_id_seq OWNED BY public.chunks.id;


--
-- Name: chunktypes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.chunktypes (
    id integer NOT NULL,
    chunktype text NOT NULL
);


--
-- Name: chunktypes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.chunktypes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: chunktypes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.chunktypes_id_seq OWNED BY public.chunktypes.id;


--
-- Name: document; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.document (
    id integer NOT NULL,
    source_id integer,
    external_id text NOT NULL,
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
    added_date timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_date timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    withdrawn_date timestamp without time zone,
    withdrawn_reason text,
    all_keywords text[],
    abstract_length integer,
    missing_details boolean DEFAULT false,
    search_vector tsvector GENERATED ALWAYS AS ((setweight(to_tsvector('english'::regconfig, COALESCE(title, ''::text)), 'A'::"char") || setweight(to_tsvector('english'::regconfig, COALESCE(abstract, ''::text)), 'B'::"char"))) STORED
);


--
-- Name: document_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.document_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: document_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.document_id_seq OWNED BY public.document.id;


--
-- Name: document_keywords; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.document_keywords (
    document_id integer NOT NULL,
    keyword text NOT NULL
);


--
-- Name: doi_metadata; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.doi_metadata (
    doi text NOT NULL,
    openalex_id text,
    title text,
    publication_year integer,
    work_type text,
    is_retracted boolean DEFAULT false,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: doi_urls; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.doi_urls (
    id bigint NOT NULL,
    doi text NOT NULL,
    url text NOT NULL,
    pdf_url text,
    openalex_id text,
    title text,
    publication_year integer,
    location_type text NOT NULL,
    version text,
    license text,
    host_type text,
    oa_status text,
    is_oa boolean DEFAULT false,
    url_quality_score integer DEFAULT 50,
    last_verified timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: doi_urls_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.doi_urls_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: doi_urls_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.doi_urls_id_seq OWNED BY public.doi_urls.id;


--
-- Name: embedding_base; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.embedding_base (
    id integer NOT NULL,
    chunk_id integer NOT NULL,
    model_id integer
);


--
-- Name: emb_1024; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.emb_1024 (
    embedding public.vector(1024)
)
INHERITS (public.embedding_base);


--
-- Name: emb_768; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.emb_768 (
    embedding public.vector(768)
)
INHERITS (public.embedding_base);


--
-- Name: embedding_base_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.embedding_base_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: embedding_base_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.embedding_base_id_seq OWNED BY public.embedding_base.id;


--
-- Name: embedding_models; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.embedding_models (
    id integer NOT NULL,
    provider_id integer,
    model_name text NOT NULL,
    model_description text,
    model_parameters jsonb
);


--
-- Name: embedding_models_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.embedding_models_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: embedding_models_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.embedding_models_id_seq OWNED BY public.embedding_models.id;


--
-- Name: embedding_provider; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.embedding_provider (
    id integer NOT NULL,
    provider_name text NOT NULL,
    base_url text
);


--
-- Name: embedding_provider_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.embedding_provider_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: embedding_provider_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.embedding_provider_id_seq OWNED BY public.embedding_provider.id;


--
-- Name: embedding_source; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.embedding_source (
    id integer NOT NULL,
    name text NOT NULL,
    description text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: embedding_source_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.embedding_source_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: embedding_source_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.embedding_source_id_seq OWNED BY public.embedding_source.id;


--
-- Name: evaluations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.evaluations (
    research_question_id integer NOT NULL,
    chunk_id integer NOT NULL,
    evaluator_id integer NOT NULL,
    document_id integer NOT NULL,
    is_human_evaluator boolean DEFAULT false NOT NULL,
    rating integer NOT NULL,
    rating_reason text,
    confidence_level double precision NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    evaluation_version integer DEFAULT 1,
    CONSTRAINT evaluations_confidence_level_check CHECK (((confidence_level >= (0.0)::double precision) AND (confidence_level <= (1.0)::double precision)))
);


--
-- Name: evaluators; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.evaluators (
    id integer NOT NULL,
    name text NOT NULL,
    user_id integer,
    model_id text,
    parameters jsonb,
    prompt text,
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now()
);


--
-- Name: evaluators_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.evaluators_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: evaluators_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.evaluators_id_seq OWNED BY public.evaluators.id;


--
-- Name: generated_data; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.generated_data (
    id integer NOT NULL,
    document_id integer,
    generation_params_id integer,
    generation_type integer,
    data text
);


--
-- Name: TABLE generated_data; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.generated_data IS 'data generated for machine learning, e.g. Q/A pairs';


--
-- Name: generated_data_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.generated_data_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: generated_data_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.generated_data_id_seq OWNED BY public.generated_data.id;


--
-- Name: generated_type; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.generated_type (
    id integer NOT NULL,
    type_name text,
    description text
);


--
-- Name: TABLE generated_type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.generated_type IS 'descriptor of data created for machine learning e.g. Q/A pairs';


--
-- Name: generated_type_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.generated_type_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: generated_type_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.generated_type_id_seq OWNED BY public.generated_type.id;


--
-- Name: generation_params; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.generation_params (
    id integer NOT NULL,
    model_id integer,
    system_prompt text,
    generation_prompt text
);


--
-- Name: TABLE generation_params; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.generation_params IS 'model name and parameters as well as prompts used to generate machine learning data sets';


--
-- Name: generation_params_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.generation_params_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: generation_params_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.generation_params_id_seq OWNED BY public.generation_params.id;


--
-- Name: human_edited; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.human_edited (
    id integer NOT NULL,
    context text,
    machine text,
    human text,
    "timestamp" timestamp without time zone DEFAULT now()
);


--
-- Name: human_edited_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.human_edited_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: human_edited_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.human_edited_id_seq OWNED BY public.human_edited.id;


--
-- Name: hypotheses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.hypotheses (
    id integer NOT NULL,
    hypothesis text NOT NULL,
    counterhypothesis text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: hypotheses_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.hypotheses_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: hypotheses_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.hypotheses_id_seq OWNED BY public.hypotheses.id;


--
-- Name: hypotheses_projects; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.hypotheses_projects (
    project_id integer NOT NULL,
    hypothesis_id integer NOT NULL
);


--
-- Name: import_tracker; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.import_tracker (
    filename text NOT NULL,
    imported timestamp with time zone,
    chunked timestamp with time zone,
    embedded boolean DEFAULT false,
    md5checked boolean DEFAULT false
);


--
-- Name: keywords; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.keywords (
    keyword text NOT NULL
);


--
-- Name: model_capabilities; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.model_capabilities (
    id integer NOT NULL,
    name text NOT NULL,
    description text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: model_capabilities_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.model_capabilities_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: model_capabilities_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.model_capabilities_id_seq OWNED BY public.model_capabilities.id;


--
-- Name: model_capability_junction; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.model_capability_junction (
    model_id integer NOT NULL,
    capability_id integer NOT NULL
);


--
-- Name: model_providers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.model_providers (
    id integer NOT NULL,
    name text NOT NULL,
    description text,
    base_url text,
    requires_api_key boolean DEFAULT false,
    api_key text,
    is_local boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    is_active boolean DEFAULT true
);


--
-- Name: model_providers_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.model_providers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: model_providers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.model_providers_id_seq OWNED BY public.model_providers.id;


--
-- Name: models; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.models (
    id integer NOT NULL,
    provider_id integer NOT NULL,
    name text NOT NULL,
    description text,
    params bigint,
    quantization text,
    context_length integer,
    embedding_length integer,
    is_free boolean DEFAULT false,
    is_locally_available boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    is_active boolean DEFAULT true
);


--
-- Name: models_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.models_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: models_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.models_id_seq OWNED BY public.models.id;


--
-- Name: processing_queue_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.processing_queue_id_seq
    START WITH 3194068
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: processing_queue; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.processing_queue (
    id integer DEFAULT nextval('public.processing_queue_id_seq'::regclass) NOT NULL,
    document_id integer NOT NULL,
    task_id integer NOT NULL,
    status integer,
    error text,
    created timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated timestamp with time zone
);


--
-- Name: project_contributors; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.project_contributors (
    project_id integer NOT NULL,
    user_id integer NOT NULL
);


--
-- Name: project_research_questions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.project_research_questions (
    project_id integer NOT NULL,
    question_id integer NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: projects; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.projects (
    id integer NOT NULL,
    title text NOT NULL,
    description text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    last_worked_on timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    manager_id integer
);


--
-- Name: projects_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.projects_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: projects_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.projects_id_seq OWNED BY public.projects.id;


--
-- Name: prompts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.prompts (
    id integer NOT NULL,
    model_id integer,
    prompt text NOT NULL,
    purpose text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    created_by integer
);


--
-- Name: prompts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.prompts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: prompts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.prompts_id_seq OWNED BY public.prompts.id;


--
-- Name: pubmed_download_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pubmed_download_log (
    id integer NOT NULL,
    file_name character varying(255) NOT NULL,
    file_type character varying(50) NOT NULL,
    download_date timestamp without time zone NOT NULL,
    processed boolean DEFAULT false,
    process_date timestamp without time zone,
    file_size bigint,
    checksum character varying(64),
    status character varying(20) DEFAULT 'downloaded'::character varying
);


--
-- Name: pubmed_download_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.pubmed_download_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pubmed_download_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.pubmed_download_log_id_seq OWNED BY public.pubmed_download_log.id;


--
-- Name: reading_records; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.reading_records (
    id integer NOT NULL,
    user_id integer,
    read_timestamp timestamp without time zone,
    rating integer,
    notes text,
    document_id integer
);


--
-- Name: reading_records_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.reading_records_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: reading_records_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.reading_records_id_seq OWNED BY public.reading_records.id;


--
-- Name: reading_records_tags; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.reading_records_tags (
    record_id integer NOT NULL,
    tag_id integer NOT NULL
);


--
-- Name: reading_suggestions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.reading_suggestions (
    id integer NOT NULL,
    document_id integer NOT NULL,
    user_id integer NOT NULL,
    evaluator_id integer NOT NULL,
    recommendation_strength integer,
    confidence_level double precision,
    comment text,
    user_agreement boolean,
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now(),
    CONSTRAINT reading_suggestions_recommendation_strength_check CHECK (((recommendation_strength >= 0) AND (recommendation_strength <= 5)))
);


--
-- Name: reading_suggestions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.reading_suggestions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: reading_suggestions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.reading_suggestions_id_seq OWNED BY public.reading_suggestions.id;


--
-- Name: reading_tags; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.reading_tags (
    id integer NOT NULL,
    name text NOT NULL
);


--
-- Name: reading_tags_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.reading_tags_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: reading_tags_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.reading_tags_id_seq OWNED BY public.reading_tags.id;


--
-- Name: research_questions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.research_questions (
    id integer NOT NULL,
    question text NOT NULL,
    details text
);


--
-- Name: research_questions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.research_questions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: research_questions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.research_questions_id_seq OWNED BY public.research_questions.id;


--
-- Name: sources; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sources (
    id integer NOT NULL,
    name text NOT NULL,
    url text,
    is_reputable boolean DEFAULT false,
    is_free boolean DEFAULT true
);


--
-- Name: sources_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.sources_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sources_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sources_id_seq OWNED BY public.sources.id;


--
-- Name: summaries; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.summaries (
    id integer NOT NULL,
    summary text,
    evaluation boolean,
    reason text,
    interests text[],
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    document_id integer NOT NULL
);


--
-- Name: summaries_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.summaries_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: summaries_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.summaries_id_seq OWNED BY public.summaries.id;


--
-- Name: tags; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tags (
    id integer NOT NULL,
    document_id integer,
    user_id integer,
    tag text NOT NULL
);


--
-- Name: tags_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.tags_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tags_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.tags_id_seq OWNED BY public.tags.id;


--
-- Name: task; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task (
    id integer NOT NULL,
    description text
);


--
-- Name: task_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.task_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: task_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.task_id_seq OWNED BY public.task.id;


--
-- Name: user_interests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_interests (
    id integer NOT NULL,
    user_id integer,
    interest text NOT NULL
);


--
-- Name: user_interests_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_interests_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_interests_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_interests_id_seq OWNED BY public.user_interests.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id integer NOT NULL,
    username text NOT NULL,
    firstname text,
    surname text,
    email text NOT NULL,
    pwdhash text NOT NULL
);


--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.version (
    version integer NOT NULL,
    migrated timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    migration_success boolean NOT NULL
);


--
-- Name: doi_urls; Type: TABLE; Schema: unpaywall; Owner: -
--

CREATE TABLE unpaywall.doi_urls (
    id bigint NOT NULL,
    doi text NOT NULL,
    url text NOT NULL,
    pdf_url text,
    openalex_id bigint,
    title text,
    publication_year integer,
    location_type character(1) NOT NULL,
    version text,
    license_id integer,
    host_type_id integer,
    oa_status_id integer,
    is_oa boolean DEFAULT false,
    work_type_id integer,
    is_retracted boolean DEFAULT false,
    url_quality_score integer DEFAULT 50,
    last_verified timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT doi_urls_location_type_check CHECK ((location_type = ANY (ARRAY['p'::bpchar, 'a'::bpchar, 'b'::bpchar])))
);


--
-- Name: doi_urls_id_seq; Type: SEQUENCE; Schema: unpaywall; Owner: -
--

CREATE SEQUENCE unpaywall.doi_urls_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: doi_urls_id_seq; Type: SEQUENCE OWNED BY; Schema: unpaywall; Owner: -
--

ALTER SEQUENCE unpaywall.doi_urls_id_seq OWNED BY unpaywall.doi_urls.id;


--
-- Name: host_type; Type: TABLE; Schema: unpaywall; Owner: -
--

CREATE TABLE unpaywall.host_type (
    id integer NOT NULL,
    value text NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: host_type_id_seq; Type: SEQUENCE; Schema: unpaywall; Owner: -
--

CREATE SEQUENCE unpaywall.host_type_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: host_type_id_seq; Type: SEQUENCE OWNED BY; Schema: unpaywall; Owner: -
--

ALTER SEQUENCE unpaywall.host_type_id_seq OWNED BY unpaywall.host_type.id;


--
-- Name: import_progress; Type: TABLE; Schema: unpaywall; Owner: -
--

CREATE TABLE unpaywall.import_progress (
    import_id text NOT NULL,
    csv_file_path text NOT NULL,
    csv_file_hash text NOT NULL,
    total_rows integer NOT NULL,
    processed_rows integer DEFAULT 0,
    last_batch_id integer DEFAULT 0,
    status text DEFAULT 'in_progress'::text,
    start_time timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    end_time timestamp without time zone,
    error_message text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: license; Type: TABLE; Schema: unpaywall; Owner: -
--

CREATE TABLE unpaywall.license (
    id integer NOT NULL,
    value text NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: license_id_seq; Type: SEQUENCE; Schema: unpaywall; Owner: -
--

CREATE SEQUENCE unpaywall.license_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: license_id_seq; Type: SEQUENCE OWNED BY; Schema: unpaywall; Owner: -
--

ALTER SEQUENCE unpaywall.license_id_seq OWNED BY unpaywall.license.id;


--
-- Name: oa_status; Type: TABLE; Schema: unpaywall; Owner: -
--

CREATE TABLE unpaywall.oa_status (
    id integer NOT NULL,
    value text NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: oa_status_id_seq; Type: SEQUENCE; Schema: unpaywall; Owner: -
--

CREATE SEQUENCE unpaywall.oa_status_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: oa_status_id_seq; Type: SEQUENCE OWNED BY; Schema: unpaywall; Owner: -
--

ALTER SEQUENCE unpaywall.oa_status_id_seq OWNED BY unpaywall.oa_status.id;


--
-- Name: work_type; Type: TABLE; Schema: unpaywall; Owner: -
--

CREATE TABLE unpaywall.work_type (
    id integer NOT NULL,
    value text NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: work_type_id_seq; Type: SEQUENCE; Schema: unpaywall; Owner: -
--

CREATE SEQUENCE unpaywall.work_type_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: work_type_id_seq; Type: SEQUENCE OWNED BY; Schema: unpaywall; Owner: -
--

ALTER SEQUENCE unpaywall.work_type_id_seq OWNED BY unpaywall.work_type.id;


--
-- Name: bookmarks id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bookmarks ALTER COLUMN id SET DEFAULT nextval('public.bookmarks_id_seq'::regclass);


--
-- Name: categories id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.categories ALTER COLUMN id SET DEFAULT nextval('public.categories_id_seq'::regclass);


--
-- Name: chunking_strategies id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chunking_strategies ALTER COLUMN id SET DEFAULT nextval('public.chunking_strategies_id_seq'::regclass);


--
-- Name: chunks id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chunks ALTER COLUMN id SET DEFAULT nextval('public.chunks_id_seq'::regclass);


--
-- Name: chunktypes id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chunktypes ALTER COLUMN id SET DEFAULT nextval('public.chunktypes_id_seq'::regclass);


--
-- Name: document id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document ALTER COLUMN id SET DEFAULT nextval('public.document_id_seq'::regclass);


--
-- Name: doi_urls id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.doi_urls ALTER COLUMN id SET DEFAULT nextval('public.doi_urls_id_seq'::regclass);


--
-- Name: emb_1024 id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.emb_1024 ALTER COLUMN id SET DEFAULT nextval('public.embedding_base_id_seq'::regclass);


--
-- Name: emb_768 id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.emb_768 ALTER COLUMN id SET DEFAULT nextval('public.embedding_base_id_seq'::regclass);


--
-- Name: embedding_base id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.embedding_base ALTER COLUMN id SET DEFAULT nextval('public.embedding_base_id_seq'::regclass);


--
-- Name: embedding_models id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.embedding_models ALTER COLUMN id SET DEFAULT nextval('public.embedding_models_id_seq'::regclass);


--
-- Name: embedding_provider id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.embedding_provider ALTER COLUMN id SET DEFAULT nextval('public.embedding_provider_id_seq'::regclass);


--
-- Name: embedding_source id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.embedding_source ALTER COLUMN id SET DEFAULT nextval('public.embedding_source_id_seq'::regclass);


--
-- Name: evaluators id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evaluators ALTER COLUMN id SET DEFAULT nextval('public.evaluators_id_seq'::regclass);


--
-- Name: generated_data id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.generated_data ALTER COLUMN id SET DEFAULT nextval('public.generated_data_id_seq'::regclass);


--
-- Name: generated_type id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.generated_type ALTER COLUMN id SET DEFAULT nextval('public.generated_type_id_seq'::regclass);


--
-- Name: generation_params id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.generation_params ALTER COLUMN id SET DEFAULT nextval('public.generation_params_id_seq'::regclass);


--
-- Name: human_edited id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.human_edited ALTER COLUMN id SET DEFAULT nextval('public.human_edited_id_seq'::regclass);


--
-- Name: hypotheses id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hypotheses ALTER COLUMN id SET DEFAULT nextval('public.hypotheses_id_seq'::regclass);


--
-- Name: model_capabilities id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.model_capabilities ALTER COLUMN id SET DEFAULT nextval('public.model_capabilities_id_seq'::regclass);


--
-- Name: model_providers id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.model_providers ALTER COLUMN id SET DEFAULT nextval('public.model_providers_id_seq'::regclass);


--
-- Name: models id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.models ALTER COLUMN id SET DEFAULT nextval('public.models_id_seq'::regclass);


--
-- Name: projects id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.projects ALTER COLUMN id SET DEFAULT nextval('public.projects_id_seq'::regclass);


--
-- Name: prompts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prompts ALTER COLUMN id SET DEFAULT nextval('public.prompts_id_seq'::regclass);


--
-- Name: pubmed_download_log id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pubmed_download_log ALTER COLUMN id SET DEFAULT nextval('public.pubmed_download_log_id_seq'::regclass);


--
-- Name: reading_records id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reading_records ALTER COLUMN id SET DEFAULT nextval('public.reading_records_id_seq'::regclass);


--
-- Name: reading_suggestions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reading_suggestions ALTER COLUMN id SET DEFAULT nextval('public.reading_suggestions_id_seq'::regclass);


--
-- Name: reading_tags id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reading_tags ALTER COLUMN id SET DEFAULT nextval('public.reading_tags_id_seq'::regclass);


--
-- Name: research_questions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.research_questions ALTER COLUMN id SET DEFAULT nextval('public.research_questions_id_seq'::regclass);


--
-- Name: sources id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sources ALTER COLUMN id SET DEFAULT nextval('public.sources_id_seq'::regclass);


--
-- Name: summaries id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.summaries ALTER COLUMN id SET DEFAULT nextval('public.summaries_id_seq'::regclass);


--
-- Name: tags id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tags ALTER COLUMN id SET DEFAULT nextval('public.tags_id_seq'::regclass);


--
-- Name: task id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task ALTER COLUMN id SET DEFAULT nextval('public.task_id_seq'::regclass);


--
-- Name: user_interests id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_interests ALTER COLUMN id SET DEFAULT nextval('public.user_interests_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Name: doi_urls id; Type: DEFAULT; Schema: unpaywall; Owner: -
--

ALTER TABLE ONLY unpaywall.doi_urls ALTER COLUMN id SET DEFAULT nextval('unpaywall.doi_urls_id_seq'::regclass);


--
-- Name: host_type id; Type: DEFAULT; Schema: unpaywall; Owner: -
--

ALTER TABLE ONLY unpaywall.host_type ALTER COLUMN id SET DEFAULT nextval('unpaywall.host_type_id_seq'::regclass);


--
-- Name: license id; Type: DEFAULT; Schema: unpaywall; Owner: -
--

ALTER TABLE ONLY unpaywall.license ALTER COLUMN id SET DEFAULT nextval('unpaywall.license_id_seq'::regclass);


--
-- Name: oa_status id; Type: DEFAULT; Schema: unpaywall; Owner: -
--

ALTER TABLE ONLY unpaywall.oa_status ALTER COLUMN id SET DEFAULT nextval('unpaywall.oa_status_id_seq'::regclass);


--
-- Name: work_type id; Type: DEFAULT; Schema: unpaywall; Owner: -
--

ALTER TABLE ONLY unpaywall.work_type ALTER COLUMN id SET DEFAULT nextval('unpaywall.work_type_id_seq'::regclass);


--
-- Name: bookmarks bookmarks_document_id_user_id_project_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bookmarks
    ADD CONSTRAINT bookmarks_document_id_user_id_project_id_key UNIQUE (document_id, user_id, project_id);


--
-- Name: bookmarks bookmarks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bookmarks
    ADD CONSTRAINT bookmarks_pkey PRIMARY KEY (id);


--
-- Name: categories categories_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.categories
    ADD CONSTRAINT categories_name_key UNIQUE (name);


--
-- Name: categories categories_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.categories
    ADD CONSTRAINT categories_pkey PRIMARY KEY (id);


--
-- Name: chunking_strategies chunking_strategies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chunking_strategies
    ADD CONSTRAINT chunking_strategies_pkey PRIMARY KEY (id);


--
-- Name: chunks chunks_doc_strategy_chunkno_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chunks
    ADD CONSTRAINT chunks_doc_strategy_chunkno_unique UNIQUE (document_id, chunking_strategy_id, chunk_no);


--
-- Name: chunks chunks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chunks
    ADD CONSTRAINT chunks_pkey PRIMARY KEY (id);


--
-- Name: chunktypes chunktypes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chunktypes
    ADD CONSTRAINT chunktypes_pkey PRIMARY KEY (id);


--
-- Name: document_keywords document_keywords_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_keywords
    ADD CONSTRAINT document_keywords_pkey PRIMARY KEY (document_id, keyword);


--
-- Name: document document_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document
    ADD CONSTRAINT document_pkey PRIMARY KEY (id);


--
-- Name: document document_source_id_external_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document
    ADD CONSTRAINT document_source_id_external_id_key UNIQUE (source_id, external_id);


--
-- Name: doi_metadata doi_metadata_openalex_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.doi_metadata
    ADD CONSTRAINT doi_metadata_openalex_id_key UNIQUE (openalex_id);


--
-- Name: doi_metadata doi_metadata_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.doi_metadata
    ADD CONSTRAINT doi_metadata_pkey PRIMARY KEY (doi);


--
-- Name: doi_urls doi_urls_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.doi_urls
    ADD CONSTRAINT doi_urls_pkey PRIMARY KEY (id);


--
-- Name: emb_1024 emb_1024_chunk_model_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.emb_1024
    ADD CONSTRAINT emb_1024_chunk_model_unique UNIQUE (chunk_id, model_id);


--
-- Name: emb_768 emb_768_chunk_model_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.emb_768
    ADD CONSTRAINT emb_768_chunk_model_unique UNIQUE (chunk_id, model_id);


--
-- Name: embedding_base embedding_base_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.embedding_base
    ADD CONSTRAINT embedding_base_pkey PRIMARY KEY (id);


--
-- Name: embedding_models embedding_models_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.embedding_models
    ADD CONSTRAINT embedding_models_pkey PRIMARY KEY (id);


--
-- Name: embedding_provider embedding_provider_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.embedding_provider
    ADD CONSTRAINT embedding_provider_pkey PRIMARY KEY (id);


--
-- Name: embedding_source embedding_source_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.embedding_source
    ADD CONSTRAINT embedding_source_name_key UNIQUE (name);


--
-- Name: embedding_source embedding_source_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.embedding_source
    ADD CONSTRAINT embedding_source_pkey PRIMARY KEY (id);


--
-- Name: evaluations evaluations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evaluations
    ADD CONSTRAINT evaluations_pkey PRIMARY KEY (research_question_id, chunk_id, evaluator_id);


--
-- Name: evaluators evaluators_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evaluators
    ADD CONSTRAINT evaluators_pkey PRIMARY KEY (id);


--
-- Name: generated_data generated_data_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.generated_data
    ADD CONSTRAINT generated_data_pkey PRIMARY KEY (id);


--
-- Name: generated_type generated_type_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.generated_type
    ADD CONSTRAINT generated_type_pkey PRIMARY KEY (id);


--
-- Name: generation_params generation_params_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.generation_params
    ADD CONSTRAINT generation_params_pkey PRIMARY KEY (id);


--
-- Name: human_edited human_edited_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.human_edited
    ADD CONSTRAINT human_edited_pkey PRIMARY KEY (id);


--
-- Name: hypotheses hypotheses_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hypotheses
    ADD CONSTRAINT hypotheses_pkey PRIMARY KEY (id);


--
-- Name: hypotheses_projects hypotheses_projects_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hypotheses_projects
    ADD CONSTRAINT hypotheses_projects_pkey PRIMARY KEY (project_id, hypothesis_id);


--
-- Name: import_tracker import_tracker_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.import_tracker
    ADD CONSTRAINT import_tracker_pkey PRIMARY KEY (filename);


--
-- Name: keywords keywords_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.keywords
    ADD CONSTRAINT keywords_pkey PRIMARY KEY (keyword);


--
-- Name: model_capabilities model_capabilities_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.model_capabilities
    ADD CONSTRAINT model_capabilities_pkey PRIMARY KEY (id);


--
-- Name: model_capability_junction model_capability_junction_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.model_capability_junction
    ADD CONSTRAINT model_capability_junction_pkey PRIMARY KEY (model_id, capability_id);


--
-- Name: model_providers model_providers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.model_providers
    ADD CONSTRAINT model_providers_pkey PRIMARY KEY (id);


--
-- Name: models models_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.models
    ADD CONSTRAINT models_pkey PRIMARY KEY (id);


--
-- Name: processing_queue processing_queue_pkey1; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.processing_queue
    ADD CONSTRAINT processing_queue_pkey1 PRIMARY KEY (id);


--
-- Name: project_contributors project_contributors_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_contributors
    ADD CONSTRAINT project_contributors_pkey PRIMARY KEY (project_id, user_id);


--
-- Name: project_research_questions project_research_questions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_research_questions
    ADD CONSTRAINT project_research_questions_pkey PRIMARY KEY (project_id, question_id);


--
-- Name: projects projects_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_pkey PRIMARY KEY (id);


--
-- Name: prompts prompts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prompts
    ADD CONSTRAINT prompts_pkey PRIMARY KEY (id);


--
-- Name: pubmed_download_log pubmed_download_log_file_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pubmed_download_log
    ADD CONSTRAINT pubmed_download_log_file_name_key UNIQUE (file_name);


--
-- Name: pubmed_download_log pubmed_download_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pubmed_download_log
    ADD CONSTRAINT pubmed_download_log_pkey PRIMARY KEY (id);


--
-- Name: reading_records reading_records_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reading_records
    ADD CONSTRAINT reading_records_pkey PRIMARY KEY (id);


--
-- Name: reading_records_tags reading_records_tags_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reading_records_tags
    ADD CONSTRAINT reading_records_tags_pkey PRIMARY KEY (record_id, tag_id);


--
-- Name: reading_suggestions reading_suggestions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reading_suggestions
    ADD CONSTRAINT reading_suggestions_pkey PRIMARY KEY (id);


--
-- Name: reading_tags reading_tags_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reading_tags
    ADD CONSTRAINT reading_tags_name_key UNIQUE (name);


--
-- Name: reading_tags reading_tags_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reading_tags
    ADD CONSTRAINT reading_tags_pkey PRIMARY KEY (id);


--
-- Name: research_questions research_questions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.research_questions
    ADD CONSTRAINT research_questions_pkey PRIMARY KEY (id);


--
-- Name: sources sources_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sources
    ADD CONSTRAINT sources_name_key UNIQUE (name);


--
-- Name: sources sources_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sources
    ADD CONSTRAINT sources_pkey PRIMARY KEY (id);


--
-- Name: summaries summaries_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.summaries
    ADD CONSTRAINT summaries_pkey PRIMARY KEY (id);


--
-- Name: tags tags_document_id_user_id_tag_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tags
    ADD CONSTRAINT tags_document_id_user_id_tag_key UNIQUE (document_id, user_id, tag);


--
-- Name: tags tags_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tags
    ADD CONSTRAINT tags_pkey PRIMARY KEY (id);


--
-- Name: task task_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task
    ADD CONSTRAINT task_pkey PRIMARY KEY (id);


--
-- Name: processing_queue unique_document_task; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.processing_queue
    ADD CONSTRAINT unique_document_task UNIQUE (document_id, task_id);


--
-- Name: doi_urls unique_doi_url; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.doi_urls
    ADD CONSTRAINT unique_doi_url UNIQUE (doi, url);


--
-- Name: user_interests user_interests_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_interests
    ADD CONSTRAINT user_interests_pkey PRIMARY KEY (id);


--
-- Name: user_interests user_interests_user_id_interest_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_interests
    ADD CONSTRAINT user_interests_user_id_interest_key UNIQUE (user_id, interest);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: users users_username_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_username_key UNIQUE (username);


--
-- Name: version version_version_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.version
    ADD CONSTRAINT version_version_key UNIQUE (version);


--
-- Name: doi_urls doi_urls_pkey; Type: CONSTRAINT; Schema: unpaywall; Owner: -
--

ALTER TABLE ONLY unpaywall.doi_urls
    ADD CONSTRAINT doi_urls_pkey PRIMARY KEY (id);


--
-- Name: host_type host_type_pkey; Type: CONSTRAINT; Schema: unpaywall; Owner: -
--

ALTER TABLE ONLY unpaywall.host_type
    ADD CONSTRAINT host_type_pkey PRIMARY KEY (id);


--
-- Name: host_type host_type_value_key; Type: CONSTRAINT; Schema: unpaywall; Owner: -
--

ALTER TABLE ONLY unpaywall.host_type
    ADD CONSTRAINT host_type_value_key UNIQUE (value);


--
-- Name: import_progress import_progress_pkey; Type: CONSTRAINT; Schema: unpaywall; Owner: -
--

ALTER TABLE ONLY unpaywall.import_progress
    ADD CONSTRAINT import_progress_pkey PRIMARY KEY (import_id);


--
-- Name: license license_pkey; Type: CONSTRAINT; Schema: unpaywall; Owner: -
--

ALTER TABLE ONLY unpaywall.license
    ADD CONSTRAINT license_pkey PRIMARY KEY (id);


--
-- Name: license license_value_key; Type: CONSTRAINT; Schema: unpaywall; Owner: -
--

ALTER TABLE ONLY unpaywall.license
    ADD CONSTRAINT license_value_key UNIQUE (value);


--
-- Name: oa_status oa_status_pkey; Type: CONSTRAINT; Schema: unpaywall; Owner: -
--

ALTER TABLE ONLY unpaywall.oa_status
    ADD CONSTRAINT oa_status_pkey PRIMARY KEY (id);


--
-- Name: oa_status oa_status_value_key; Type: CONSTRAINT; Schema: unpaywall; Owner: -
--

ALTER TABLE ONLY unpaywall.oa_status
    ADD CONSTRAINT oa_status_value_key UNIQUE (value);


--
-- Name: doi_urls unique_unpaywall_doi_url; Type: CONSTRAINT; Schema: unpaywall; Owner: -
--

ALTER TABLE ONLY unpaywall.doi_urls
    ADD CONSTRAINT unique_unpaywall_doi_url UNIQUE (doi, url);


--
-- Name: work_type work_type_pkey; Type: CONSTRAINT; Schema: unpaywall; Owner: -
--

ALTER TABLE ONLY unpaywall.work_type
    ADD CONSTRAINT work_type_pkey PRIMARY KEY (id);


--
-- Name: work_type work_type_value_key; Type: CONSTRAINT; Schema: unpaywall; Owner: -
--

ALTER TABLE ONLY unpaywall.work_type
    ADD CONSTRAINT work_type_value_key UNIQUE (value);


--
-- Name: chunks_chunktype_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX chunks_chunktype_id_idx ON public.chunks USING btree (chunktype_id);


--
-- Name: chunks_document_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX chunks_document_id_idx ON public.chunks USING btree (document_id);


--
-- Name: emb_1024_chunk_model_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX emb_1024_chunk_model_idx ON public.emb_1024 USING btree (chunk_id, model_id);


--
-- Name: emb_768_chunk_model_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX emb_768_chunk_model_idx ON public.emb_768 USING btree (chunk_id, model_id);


--
-- Name: hypotheses_hypothesis_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX hypotheses_hypothesis_idx ON public.hypotheses USING gin (to_tsvector('english'::regconfig, hypothesis));


--
-- Name: idx_bookmarks_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bookmarks_document_id ON public.bookmarks USING btree (document_id);


--
-- Name: idx_bookmarks_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bookmarks_project_id ON public.bookmarks USING btree (project_id);


--
-- Name: idx_bookmarks_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bookmarks_type ON public.bookmarks USING btree (bookmark_type);


--
-- Name: idx_bookmarks_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bookmarks_user_id ON public.bookmarks USING btree (user_id);


--
-- Name: idx_chunks_chunktype_1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_chunks_chunktype_1 ON public.chunks USING btree (id) WHERE (chunktype_id = 1);


--
-- Name: idx_chunks_document_id_chunking_strategy_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_chunks_document_id_chunking_strategy_id ON public.chunks USING btree (document_id, chunking_strategy_id);


--
-- Name: idx_chunks_strategy_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_chunks_strategy_type ON public.chunks USING btree (chunking_strategy_id, chunktype_id);


--
-- Name: idx_document_added_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_document_added_date ON public.document USING btree (added_date);


--
-- Name: idx_document_doi; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_document_doi ON public.document USING btree (doi) WITH (deduplicate_items='true');


--
-- Name: idx_document_external_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_document_external_id ON public.document USING btree (external_id);


--
-- Name: idx_document_fts; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_document_fts ON public.document USING gin (search_vector);


--
-- Name: idx_document_publication_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_document_publication_date ON public.document USING btree (publication_date);


--
-- Name: idx_document_source_doi; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_document_source_doi ON public.document USING btree (source_id, doi) WHERE (doi IS NOT NULL);


--
-- Name: idx_document_source_publication_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_document_source_publication_date ON public.document USING btree (source_id, publication_date) WHERE (publication_date IS NOT NULL);


--
-- Name: idx_document_updated_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_document_updated_date ON public.document USING btree (updated_date);


--
-- Name: idx_doi_metadata_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_doi_metadata_type ON public.doi_metadata USING btree (work_type);


--
-- Name: idx_doi_metadata_year; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_doi_metadata_year ON public.doi_metadata USING btree (publication_year);


--
-- Name: idx_emb_1024_chunk_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_emb_1024_chunk_id ON public.emb_1024 USING btree (chunk_id);


--
-- Name: idx_emb_1024_chunk_model; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_emb_1024_chunk_model ON public.emb_1024 USING btree (chunk_id, model_id);


--
-- Name: idx_emb_1024_model_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_emb_1024_model_id ON public.emb_1024 USING btree (model_id);


--
-- Name: idx_eval_chunk; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_eval_chunk ON public.evaluations USING btree (chunk_id);


--
-- Name: idx_eval_document; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_eval_document ON public.evaluations USING btree (document_id);


--
-- Name: idx_eval_evaluator; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_eval_evaluator ON public.evaluations USING btree (evaluator_id);


--
-- Name: idx_eval_llm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_eval_llm ON public.evaluations USING btree (is_human_evaluator) WHERE (is_human_evaluator = false);


--
-- Name: idx_eval_question; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_eval_question ON public.evaluations USING btree (research_question_id);


--
-- Name: idx_eval_question_doc; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_eval_question_doc ON public.evaluations USING btree (research_question_id, document_id);


--
-- Name: idx_hypotheses_projects_hypothesis; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_hypotheses_projects_hypothesis ON public.hypotheses_projects USING btree (hypothesis_id);


--
-- Name: idx_hypotheses_projects_project; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_hypotheses_projects_project ON public.hypotheses_projects USING btree (project_id);


--
-- Name: idx_model_cap_junction_capability; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_model_cap_junction_capability ON public.model_capability_junction USING btree (capability_id);


--
-- Name: idx_model_cap_junction_model; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_model_cap_junction_model ON public.model_capability_junction USING btree (model_id);


--
-- Name: idx_models_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_models_name ON public.models USING btree (name);


--
-- Name: idx_models_provider_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_models_provider_id ON public.models USING btree (provider_id);


--
-- Name: idx_project_contributors_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_project_contributors_user_id ON public.project_contributors USING btree (user_id);


--
-- Name: idx_projects_manager_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_projects_manager_id ON public.projects USING btree (manager_id);


--
-- Name: idx_prompts_model_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_prompts_model_id ON public.prompts USING btree (model_id);


--
-- Name: idx_prq_project_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_prq_project_active ON public.project_research_questions USING btree (project_id) WHERE is_active;


--
-- Name: idx_prq_question_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_prq_question_active ON public.project_research_questions USING btree (question_id) WHERE is_active;


--
-- Name: idx_reading_records_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_reading_records_document_id ON public.reading_records USING btree (document_id);


--
-- Name: idx_reading_records_read_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_reading_records_read_timestamp ON public.reading_records USING btree (read_timestamp);


--
-- Name: idx_reading_suggestions_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_reading_suggestions_document_id ON public.reading_suggestions USING btree (document_id);


--
-- Name: idx_reading_suggestions_evaluator_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_reading_suggestions_evaluator_id ON public.reading_suggestions USING btree (evaluator_id);


--
-- Name: idx_reading_suggestions_recommendation_strength; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_reading_suggestions_recommendation_strength ON public.reading_suggestions USING btree (recommendation_strength);


--
-- Name: idx_reading_suggestions_unique; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_reading_suggestions_unique ON public.reading_suggestions USING btree (document_id, user_id, evaluator_id);


--
-- Name: idx_reading_suggestions_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_reading_suggestions_user_id ON public.reading_suggestions USING btree (user_id);


--
-- Name: idx_summaries_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_summaries_document_id ON public.summaries USING btree (document_id);


--
-- Name: idx_user_interests_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_interests_user_id ON public.user_interests USING btree (user_id);


--
-- Name: processing_queue_document_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX processing_queue_document_id_idx ON public.processing_queue USING btree (document_id);


--
-- Name: idx_unpaywall_doi_urls_doi; Type: INDEX; Schema: unpaywall; Owner: -
--

CREATE INDEX idx_unpaywall_doi_urls_doi ON unpaywall.doi_urls USING btree (doi);


--
-- Name: idx_unpaywall_doi_urls_doi_location_type; Type: INDEX; Schema: unpaywall; Owner: -
--

CREATE INDEX idx_unpaywall_doi_urls_doi_location_type ON unpaywall.doi_urls USING btree (doi, location_type);


--
-- Name: idx_unpaywall_doi_urls_host_type_id; Type: INDEX; Schema: unpaywall; Owner: -
--

CREATE INDEX idx_unpaywall_doi_urls_host_type_id ON unpaywall.doi_urls USING btree (host_type_id);


--
-- Name: idx_unpaywall_doi_urls_is_retracted; Type: INDEX; Schema: unpaywall; Owner: -
--

CREATE INDEX idx_unpaywall_doi_urls_is_retracted ON unpaywall.doi_urls USING btree (is_retracted);


--
-- Name: idx_unpaywall_doi_urls_license_id; Type: INDEX; Schema: unpaywall; Owner: -
--

CREATE INDEX idx_unpaywall_doi_urls_license_id ON unpaywall.doi_urls USING btree (license_id);


--
-- Name: idx_unpaywall_doi_urls_location_type; Type: INDEX; Schema: unpaywall; Owner: -
--

CREATE INDEX idx_unpaywall_doi_urls_location_type ON unpaywall.doi_urls USING btree (location_type);


--
-- Name: idx_unpaywall_doi_urls_oa_status_id; Type: INDEX; Schema: unpaywall; Owner: -
--

CREATE INDEX idx_unpaywall_doi_urls_oa_status_id ON unpaywall.doi_urls USING btree (oa_status_id);


--
-- Name: idx_unpaywall_doi_urls_openalex_work_id; Type: INDEX; Schema: unpaywall; Owner: -
--

CREATE INDEX idx_unpaywall_doi_urls_openalex_work_id ON unpaywall.doi_urls USING btree (openalex_id);


--
-- Name: idx_unpaywall_doi_urls_pdf_url; Type: INDEX; Schema: unpaywall; Owner: -
--

CREATE INDEX idx_unpaywall_doi_urls_pdf_url ON unpaywall.doi_urls USING btree (pdf_url) WHERE (pdf_url IS NOT NULL);


--
-- Name: idx_unpaywall_doi_urls_publication_year; Type: INDEX; Schema: unpaywall; Owner: -
--

CREATE INDEX idx_unpaywall_doi_urls_publication_year ON unpaywall.doi_urls USING btree (publication_year);


--
-- Name: idx_unpaywall_doi_urls_url; Type: INDEX; Schema: unpaywall; Owner: -
--

CREATE INDEX idx_unpaywall_doi_urls_url ON unpaywall.doi_urls USING btree (url);


--
-- Name: idx_unpaywall_doi_urls_work_type_id; Type: INDEX; Schema: unpaywall; Owner: -
--

CREATE INDEX idx_unpaywall_doi_urls_work_type_id ON unpaywall.doi_urls USING btree (work_type_id);


--
-- Name: idx_unpaywall_import_progress_file_path; Type: INDEX; Schema: unpaywall; Owner: -
--

CREATE INDEX idx_unpaywall_import_progress_file_path ON unpaywall.import_progress USING btree (csv_file_path);


--
-- Name: idx_unpaywall_import_progress_status; Type: INDEX; Schema: unpaywall; Owner: -
--

CREATE INDEX idx_unpaywall_import_progress_status ON unpaywall.import_progress USING btree (status);


--
-- Name: evaluations trg_update_eval_version; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_update_eval_version BEFORE UPDATE ON public.evaluations FOR EACH ROW EXECUTE FUNCTION public.trg_bump_version_and_timestamp();


--
-- Name: project_research_questions trg_update_prq_status; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_update_prq_status BEFORE UPDATE ON public.project_research_questions FOR EACH ROW EXECUTE FUNCTION public.trg_update_timestamp_on_status_change();


--
-- Name: document update_all_keywords_before_ins_upd; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_all_keywords_before_ins_upd BEFORE INSERT OR UPDATE ON public.document FOR EACH ROW EXECUTE FUNCTION public.update_all_keywords_trigger();


--
-- Name: bookmarks bookmarks_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bookmarks
    ADD CONSTRAINT bookmarks_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.document(id) ON DELETE CASCADE;


--
-- Name: bookmarks bookmarks_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bookmarks
    ADD CONSTRAINT bookmarks_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: bookmarks bookmarks_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bookmarks
    ADD CONSTRAINT bookmarks_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: document document_category_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document
    ADD CONSTRAINT document_category_id_fkey FOREIGN KEY (category_id) REFERENCES public.categories(id);


--
-- Name: document_keywords document_keywords_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_keywords
    ADD CONSTRAINT document_keywords_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.document(id) ON DELETE CASCADE;


--
-- Name: document_keywords document_keywords_keyword_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_keywords
    ADD CONSTRAINT document_keywords_keyword_fkey FOREIGN KEY (keyword) REFERENCES public.keywords(keyword) ON DELETE CASCADE;


--
-- Name: document document_source_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document
    ADD CONSTRAINT document_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.sources(id);


--
-- Name: embedding_base embedding_base_chunk_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.embedding_base
    ADD CONSTRAINT embedding_base_chunk_id_fkey FOREIGN KEY (chunk_id) REFERENCES public.chunks(id) ON DELETE CASCADE;


--
-- Name: evaluations evaluations_chunk_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evaluations
    ADD CONSTRAINT evaluations_chunk_id_fkey FOREIGN KEY (chunk_id) REFERENCES public.chunks(id);


--
-- Name: evaluations evaluations_evaluator_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evaluations
    ADD CONSTRAINT evaluations_evaluator_id_fkey FOREIGN KEY (evaluator_id) REFERENCES public.evaluators(id);


--
-- Name: evaluations evaluations_research_question_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evaluations
    ADD CONSTRAINT evaluations_research_question_id_fkey FOREIGN KEY (research_question_id) REFERENCES public.research_questions(id);


--
-- Name: evaluators evaluators_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evaluators
    ADD CONSTRAINT evaluators_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: generated_data generated_data_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.generated_data
    ADD CONSTRAINT generated_data_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.document(id);


--
-- Name: generated_data generated_data_generation_params_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.generated_data
    ADD CONSTRAINT generated_data_generation_params_id_fkey FOREIGN KEY (generation_params_id) REFERENCES public.generation_params(id);


--
-- Name: generated_data generated_data_generation_type_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.generated_data
    ADD CONSTRAINT generated_data_generation_type_fkey FOREIGN KEY (generation_type) REFERENCES public.generated_type(id);


--
-- Name: generation_params generation_params_model_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.generation_params
    ADD CONSTRAINT generation_params_model_id_fkey FOREIGN KEY (model_id) REFERENCES public.models(id);


--
-- Name: hypotheses_projects hypotheses_projects_hypothesis_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hypotheses_projects
    ADD CONSTRAINT hypotheses_projects_hypothesis_id_fkey FOREIGN KEY (hypothesis_id) REFERENCES public.hypotheses(id) ON DELETE CASCADE;


--
-- Name: hypotheses_projects hypotheses_projects_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hypotheses_projects
    ADD CONSTRAINT hypotheses_projects_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: model_capability_junction model_capability_junction_capability_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.model_capability_junction
    ADD CONSTRAINT model_capability_junction_capability_id_fkey FOREIGN KEY (capability_id) REFERENCES public.model_capabilities(id);


--
-- Name: model_capability_junction model_capability_junction_model_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.model_capability_junction
    ADD CONSTRAINT model_capability_junction_model_id_fkey FOREIGN KEY (model_id) REFERENCES public.models(id);


--
-- Name: models models_provider_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.models
    ADD CONSTRAINT models_provider_id_fkey FOREIGN KEY (provider_id) REFERENCES public.model_providers(id);


--
-- Name: project_contributors project_contributors_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_contributors
    ADD CONSTRAINT project_contributors_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: project_contributors project_contributors_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_contributors
    ADD CONSTRAINT project_contributors_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: project_research_questions project_research_questions_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_research_questions
    ADD CONSTRAINT project_research_questions_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: project_research_questions project_research_questions_question_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_research_questions
    ADD CONSTRAINT project_research_questions_question_id_fkey FOREIGN KEY (question_id) REFERENCES public.research_questions(id) ON DELETE CASCADE;


--
-- Name: projects projects_manager_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_manager_id_fkey FOREIGN KEY (manager_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: prompts prompts_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prompts
    ADD CONSTRAINT prompts_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: prompts prompts_model_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prompts
    ADD CONSTRAINT prompts_model_id_fkey FOREIGN KEY (model_id) REFERENCES public.models(id);


--
-- Name: reading_records reading_records_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reading_records
    ADD CONSTRAINT reading_records_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.document(id) ON DELETE CASCADE;


--
-- Name: reading_records_tags reading_records_tags_record_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reading_records_tags
    ADD CONSTRAINT reading_records_tags_record_id_fkey FOREIGN KEY (record_id) REFERENCES public.reading_records(id) ON DELETE CASCADE;


--
-- Name: reading_records_tags reading_records_tags_tag_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reading_records_tags
    ADD CONSTRAINT reading_records_tags_tag_id_fkey FOREIGN KEY (tag_id) REFERENCES public.reading_tags(id) ON DELETE CASCADE;


--
-- Name: reading_suggestions reading_suggestions_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reading_suggestions
    ADD CONSTRAINT reading_suggestions_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.document(id);


--
-- Name: reading_suggestions reading_suggestions_evaluator_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reading_suggestions
    ADD CONSTRAINT reading_suggestions_evaluator_id_fkey FOREIGN KEY (evaluator_id) REFERENCES public.evaluators(id);


--
-- Name: reading_suggestions reading_suggestions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reading_suggestions
    ADD CONSTRAINT reading_suggestions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: summaries summaries_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.summaries
    ADD CONSTRAINT summaries_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.document(id) ON DELETE CASCADE;


--
-- Name: tags tags_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tags
    ADD CONSTRAINT tags_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.document(id) ON DELETE CASCADE;


--
-- Name: user_interests user_interests_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_interests
    ADD CONSTRAINT user_interests_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: doi_urls doi_urls_host_type_id_fkey; Type: FK CONSTRAINT; Schema: unpaywall; Owner: -
--

ALTER TABLE ONLY unpaywall.doi_urls
    ADD CONSTRAINT doi_urls_host_type_id_fkey FOREIGN KEY (host_type_id) REFERENCES unpaywall.host_type(id);


--
-- Name: doi_urls doi_urls_license_id_fkey; Type: FK CONSTRAINT; Schema: unpaywall; Owner: -
--

ALTER TABLE ONLY unpaywall.doi_urls
    ADD CONSTRAINT doi_urls_license_id_fkey FOREIGN KEY (license_id) REFERENCES unpaywall.license(id);


--
-- Name: doi_urls doi_urls_oa_status_id_fkey; Type: FK CONSTRAINT; Schema: unpaywall; Owner: -
--

ALTER TABLE ONLY unpaywall.doi_urls
    ADD CONSTRAINT doi_urls_oa_status_id_fkey FOREIGN KEY (oa_status_id) REFERENCES unpaywall.oa_status(id);


--
-- Name: doi_urls doi_urls_work_type_id_fkey; Type: FK CONSTRAINT; Schema: unpaywall; Owner: -
--

ALTER TABLE ONLY unpaywall.doi_urls
    ADD CONSTRAINT doi_urls_work_type_id_fkey FOREIGN KEY (work_type_id) REFERENCES unpaywall.work_type(id);


--
-- PostgreSQL database dump complete
--

