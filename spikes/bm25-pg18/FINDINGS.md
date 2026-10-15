# Phase 0f findings — pg_search BM25 vs ts_rank_cd, PostgreSQL 18 (2026-10-13)

Server: Postgres.app 18.1 on :5532, `pg_search` 0.26.1 (Postgres.app package;
`shared_preload_libraries = 'pg_search'` in `postgresql.conf`, which
Postgres.app merges into its launch flags), pgvector 0.8.1. Database:
`bmlibrarian_dev` on :5532, schema `bm25_eval`.

Corpus: the 48 629 abstracts (abstract only, no title) shared by the
BMLibrarian evaluation sets. Queries and judgements:

| Set | Queries | Relevant |
|---|---|---|
| `pubmedqa_source` | 1 000 | the paper each question was written from |
| `pubmedqa_graded` | 1 000 | graded LLM evidence |
| `research_questions` | 12 | real BMLibrarian questions |

Vectors: the cached arctic-embed-l-v2.0 embeddings, truncated to 256 d,
searched exactly.

## Methods

| Method | What |
|---|---|
| `tsrank` | today's FTS: `tsvector` + GIN (`fastupdate = off`), OR of the query's English lexemes, `ts_rank_cd` |
| `bm25` | `pg_search`, default tokenizer, `|||` (match any term), `pdb.score` |
| `bm25_stem` | `pg_search`, `pdb.simple('stemmer=english', 'stopwords_language=English')` |
| `vector` | exact cosine, 256 d |
| `hybrid_*` | reciprocal rank fusion (k = 60) of lexical top 100 and vector top 100; `_v2` / `_v3` weight the vector list 2× / 3× |

Index builds over 48.6 k abstracts took about 1 s each. Sizes: GIN 28 MB,
`bm25` 32 MB, `bm25_stem` 27 MB.

## Results (nDCG@10; recall@100; Δ with paired-bootstrap 95 % CI)

| Method | pubmedqa_source | pubmedqa_graded | research_questions (n = 12) | p50 latency |
|---|---|---|---|---|
| tsrank | 0.375; 0.902 | 0.395; 0.724 | 0.062; 0.210 | 60–112 ms |
| bm25 | 0.753; 0.988 | 0.768; 0.953 | 0.310; 0.707 | 4–6 ms |
| **bm25_stem** | 0.744; 0.992 | 0.773; 0.964 | 0.322; **0.827** | **3–4 ms** |
| **vector** | 0.782; 0.998 | **0.834**; 0.998 | **0.544**; 0.951 | (HNSW: §9 of the plan) |
| hybrid_tsrank | 0.656 | 0.711 | 0.271 | |
| hybrid_bm25_stem | 0.790; 0.998 | 0.823; 0.998 | 0.415; **0.979** | |
| **hybrid_bm25_stem_v2** | **0.794** (+0.013 [+0.004, +0.021] vs vector) | 0.832 (−0.002 [−0.006, +0.003]) | 0.430 (−0.115 [−0.231, −0.006]) | |
| hybrid_bm25_stem_v3 | 0.792 | 0.833 | 0.429 | |

- **pg_search BM25 doubles ranking quality over `ts_rank_cd`** (+0.37 to
  +0.38 nDCG@10 on the PubMedQA sets, CIs far from 0) and is about **20×
  faster** (4–6 ms against 60–112 ms).
- Stemming plus stopwords is roughly neutral on nDCG and better on recall
  (research questions R@100 0.83 against 0.71), and its index is smaller.
  Use `bm25_stem`.
- **Vectors remain the best single method on every set.**
- Fusing with `ts_rank_cd` **hurts** (−0.12 to −0.27 against vector alone).
- Weighted fusion with BM25 (vector 2×) is slightly better on title-like
  queries (pubmedqa_source, significant) and neutral on the graded set. On
  the 12 real research questions, any fusion lowers nDCG@10, while
  equal-weight fusion raises recall@100 (0.951 → 0.979).

## Conclusion

1. **Replace `tsvector`/`ts_rank_cd` with `pg_search` (`bm25_stem`) for
   lexical search.** It is better on every set, ~20× faster, comparable in
   index size, and inside Postgres. If no feature still needs the generated
   `search_vector` and its GIN, drop them from the ingest path (that was
   the largest Postgres-side ingest cost in Phase 0).
2. **Ranking stays vector-led.** In BMLibrarian's pipeline the LLM scores
   every retrieved document, so lexical search should **add candidates**
   rather than re-rank:
   - candidates = vector top-K ∪ BM25 top-K (the union's recall is at least
     each list's);
   - order for display or truncation by weighted RRF (vector 2×);
   - BM25 also keeps exact-term queries (gene and drug names, trial IDs)
     working, which these evaluation sets do not test.
3. **Still to measure** (before Phase B commits to dropping the GIN):
   `pg_search` index-maintenance cost during the resumable ingest (per-file
   throughput, SIGKILL/resume consistency, size at 38 M rows).

## Caveats

- The `tsrank` baseline is an OR of query lexemes. Production builds AND/OR
  tsqueries with an LLM (QueryAgent), which is not reproducible here; an
  LLM-built query could rank better than this baseline.
- PubMedQA questions are paper titles phrased as questions (titles are not in
  the corpus); the research-question set has only 12 queries.
- The graded set's judgements came from Arctic-backed retrieval (pool bias
  toward vectors).

## Ingest cost and resumability with pg_search (PG 18, 2026-10-13)

80 modern baseline files (2 398 955 records), Rust loader, 8 threads, per-file
transactions + ledger, fresh table each time, default server settings
(`shared_buffers` 128 MB, `max_wal_size` 1 GB). Index: `bm25` on
`(id, title, abstract)` with the stemmed tokenizer.

| Variant | Wall | Throughput | Median / worst file | Table + indexes | Forced checkpoints |
|---|---|---|---|---|---|
| no FTS | 99 s | 24.2 k/s | 8.9 / 15 s | 7.5 GB | 32 |
| **pg_search BM25** | **140 s** | **17.1 k/s** | 12.0 / 32 s | **8.4 GB** | 41 |
| tsvector (STORED) + GIN `fastupdate = off` | 517 s | 4.6 k/s | 43.8 / 97 s | 13 GB | 179 |

**Kill/resume with BM25:** SIGKILL after 7/80 files; the resumed run gave an
identical PMID set with no duplicates, and the BM25 index returns exactly the
table's 2 398 955 rows (`id @@@ pdb.all()`). Its updates are transactional
with the data.

**Verdict:** pg_search is **3.7× cheaper to maintain during ingest than
tsvector + GIN** and 35 % smaller, as well as 2× better at ranking and ~20×
faster to query. Drop the generated `search_vector` and its GIN from the
schema; BM25 via pg_search becomes the only lexical index.
