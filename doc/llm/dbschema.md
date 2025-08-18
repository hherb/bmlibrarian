# BMLibrarian Database Schema Reference

Compact schema for LLM query assistance. Production database - READ-ONLY access.

## Core Document Tables

### `document` - Main papers/articles table
- `id` (int, PK), `external_id` (text), `doi` (text)
- `title` (text), `abstract` (text), `full_text` (text)
- `authors` (text[]), `keywords` (text[]), `augmented_keywords` (text[]), `mesh_terms` (text[]), `all_keywords` (text[])
- `publication` (text), `publication_date` (date)
- `url` (text), `pdf_url` (text), `pdf_filename` (text)
- `source_id` (int→sources), `category_id` (int→categories)
- `added_date`, `updated_date`, `withdrawn_date` (timestamps)
- `abstract_length` (int), `missing_details` (bool)
- `search_vector` (tsvector, generated from title+abstract)

### `chunks` - Document text chunks for embeddings
- `id` (int, PK), `document_id` (int→document), `chunk_no` (int)
- `text` (text), `chunklength` (int), `document_title` (text)
- `chunking_strategy_id` (int→chunking_strategies), `chunktype_id` (int→chunktypes)
- `page_start`, `page_end` (int), `metadata` (jsonb)

### `document_keywords` - Document-keyword junction
- `document_id` (int→document), `keyword` (text)

## User & Project Management

### `users`
- `id` (int, PK), `username` (text), `email` (text)
- `firstname`, `surname` (text), `pwdhash` (text)

### `projects`
- `id` (int, PK), `title` (text), `description` (text)
- `manager_id` (int→users), `created_at`, `last_worked_on` (timestamps)

### `project_contributors`
- `project_id` (int→projects), `user_id` (int→users)

### `bookmarks`
- `id` (int, PK), `document_id` (int→document), `user_id` (int→users)
- `project_id` (int→projects), `bookmark_type` (text: personal/project/both)
- `created_at` (timestamp)

## Research & Evaluation

### `research_questions`
- `id` (int, PK), `question` (text), `details` (text)

### `project_research_questions`
- `project_id` (int→projects), `question_id` (int→research_questions)
- `is_active` (bool), `created_at`, `updated_at` (timestamps)

### `evaluations` - Chunk relevance ratings
- `research_question_id` (int→research_questions), `chunk_id` (int→chunks)
- `evaluator_id` (int→evaluators), `document_id` (int→document)
- `is_human_evaluator` (bool), `rating` (int), `confidence_level` (float 0-1)
- `rating_reason` (text), `evaluation_version` (int)
- `created_at`, `updated_at` (timestamps)

### `evaluators` - Human/AI evaluators
- `id` (int, PK), `name` (text), `user_id` (int→users)
- `model_id` (text), `parameters` (jsonb), `prompt` (text)
- `created_at`, `updated_at` (timestamps)

### `hypotheses`
- `id` (int, PK), `hypothesis` (text), `counterhypothesis` (text)
- `created_at` (timestamp)

### `hypotheses_projects`
- `project_id` (int→projects), `hypothesis_id` (int→hypotheses)

## AI/ML Infrastructure

### `embedding_base` - Base embedding table
- `id` (int, PK), `chunk_id` (int→chunks), `model_id` (int→embedding_models)

### `emb_768`, `emb_1024` - Embedding storage (inherit embedding_base)
- `embedding` (vector(768/1024))

### `embedding_models`
- `id` (int, PK), `provider_id` (int→embedding_provider)
- `model_name` (text), `model_description` (text), `model_parameters` (jsonb)

### `embedding_provider`
- `id` (int, PK), `provider_name` (text), `base_url` (text)

### `models` - LLM models
- `id` (int, PK), `provider_id` (int→model_providers), `name` (text)
- `params` (bigint), `context_length`, `embedding_length` (int)
- `quantization` (text), `is_free`, `is_locally_available`, `is_active` (bool)

### `model_providers`
- `id` (int, PK), `name` (text), `description` (text), `base_url` (text)
- `requires_api_key`, `is_local`, `is_active` (bool), `api_key` (text)

### `prompts`
- `id` (int, PK), `model_id` (int→models), `prompt` (text)
- `purpose` (text), `created_by` (int→users), `created_at` (timestamp)

## Content Generation & Processing

### `generated_data`
- `id` (int, PK), `document_id` (int→document)
- `generation_params_id` (int→generation_params), `generation_type` (int→generated_type)
- `data` (text)

### `generation_params`
- `id` (int, PK), `model_id` (int→models)
- `system_prompt`, `generation_prompt` (text)

### `summaries`
- `id` (int, PK), `document_id` (int→document), `summary` (text)
- `evaluation` (bool), `reason` (text), `interests` (text[])
- `created_at` (timestamp)

### `processing_queue`
- `id` (int, PK), `document_id` (int→document), `task_id` (int→task)
- `status` (int), `error` (text), `created`, `updated` (timestamps)

## User Activity & Recommendations

### `reading_records`
- `id` (int, PK), `user_id` (int→users), `document_id` (int→document)
- `read_timestamp` (timestamp), `rating` (int), `notes` (text)

### `reading_suggestions`
- `id` (int, PK), `document_id` (int→document), `user_id` (int→users)
- `evaluator_id` (int→evaluators), `recommendation_strength` (int 0-5)
- `confidence_level` (float), `comment` (text), `user_agreement` (bool)
- `created_at`, `updated_at` (timestamps)

### `user_interests`
- `id` (int, PK), `user_id` (int→users), `interest` (text)

### `tags`
- `id` (int, PK), `document_id` (int→document), `user_id` (int→users)
- `tag` (text)

## Metadata & Classification

### `categories`
- `id` (int, PK), `name` (text), `description` (text)

### `sources` - Publication sources
- `id` (int, PK), `name` (text), `url` (text)
- `is_reputable`, `is_free` (bool)

### `keywords` - Global keyword list
- `keyword` (text, PK)

### `chunking_strategies`
- `id` (int, PK), `strategy_name` (text), `modelname` (text)
- `parameters` (jsonb)

### `chunktypes`
- `id` (int, PK), `chunktype` (text)

## DOI & External Data

### `doi_metadata` (public schema)
- `doi` (text, PK), `openalex_id` (text), `title` (text)
- `publication_year` (int), `work_type` (text), `is_retracted` (bool)
- `created_at`, `updated_at` (timestamps)

### `doi_urls` (public schema)
- `id` (bigint, PK), `doi` (text), `url` (text), `pdf_url` (text)
- `openalex_id`, `title` (text), `publication_year` (int)
- `location_type` (text), `version`, `license`, `host_type`, `oa_status` (text)
- `is_oa` (bool), `url_quality_score` (int), `last_verified` (timestamp)

### `unpaywall` schema - External open access data
- `unpaywall.doi_urls` - DOI URLs with OA status
- `unpaywall.host_type`, `unpaywall.license`, `unpaywall.oa_status`, `unpaywall.work_type` - Lookup tables

## Utility Tables

### `import_tracker`
- `filename` (text, PK), `imported`, `chunked` (timestamps)
- `embedded`, `md5checked` (bool)

### `pubmed_download_log`
- `id` (int, PK), `file_name` (varchar), `file_type` (varchar)
- `download_date`, `process_date` (timestamps), `processed` (bool)
- `file_size` (bigint), `checksum` (varchar), `status` (varchar)

### `human_edited` - Human corrections
- `id` (int, PK), `context`, `machine`, `human` (text)
- `timestamp` (timestamp)

### `version` - Schema versioning
- `version` (int, PK), `migrated` (timestamp), `migration_success` (bool)

## Key Relationships

- Documents have chunks with embeddings
- Users create projects with research questions
- Evaluations rate chunk relevance to research questions
- Bookmarks link users/projects to documents
- Reading records track user document interactions
- Generated data stores AI-produced content per document

## Query Patterns

- Search documents: Use `search_vector` or filter by `keywords`/`authors`
- Find relevant chunks: Join `chunks`→`evaluations` by research question
- User activity: Join `users`→`reading_records`→`documents`
- Project research: Join `projects`→`project_research_questions`→`research_questions`
- Embeddings: Join `chunks`→`embedding_base`→`emb_768/emb_1024`

## High-Level API

**`find_abstracts()` function:**
- `find_abstracts(query, max_rows=100, use_pubmed=True, use_medrxiv=True, use_others=True, plain=True)`
- `plain=True`: Uses `plainto_tsquery` for simple text search ("covid vaccine")
- `plain=False`: Uses `to_tsquery` for advanced syntax ("covid & vaccine", "covid | sars", "vaccine & !covid")
- Returns generator with document dict including all metadata fields
- Optimized with source ID caching for fast queries on 38M+ documents