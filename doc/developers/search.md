# Search (`rust/bml-search`)

Hybrid retrieval over a library's chunks, one hit per paper. It is the
walking skeleton the investor-demo spec asks for
(`docs/superpowers/specs/2026-11-15-investor-demo-europepmc-design.md`, part
3). The app's search screen and `bml search` both call it.

## API

`search(db, embedder, query, limit) -> Result<Vec<SearchHit>, SearchError>`

- A query that is blank after trimming ASCII whitespace, or `limit == 0`,
  returns no hits without touching the model or the database. An empty
  library returns no hits, not an error.
- `SearchHit`: `publication_id`, `title`, `journal`, `year` (from the ISO
  `publication_date`), `authors` (the JSON list in `publications.authors`),
  `passage` (the best chunk's text) and `score` (comparable within one
  search only). It derives `Serialize` for the app.
- `SearchError`: the database failed, the model failed, or there is no chunk
  index yet (`NoIndex`, "run `bml setup`").

## How it ranks

1. The query is embedded with `ChunkEmbedder::embed_query`. It is bmlib's
   `query_text` (Arctic's `query: ` prefix, `bmlib::embed::QUERY_PREFIX`)
   followed by `embed`, as bmlib's `Embedder::embed_query` does.
2. **Vectors**: the `VECTOR_K` (100) nearest chunks, `embedding <=> query`
   over the HNSW index. `hnsw.ef_search` is set to `VECTOR_K` first, because
   HNSW returns at most `ef_search` rows and the default is 40.
3. **Words**: the `LEXICAL_K` (100) best chunks for the query's words. With
   pg_search that is BM25, `text ||| query ORDER BY pdb.score(id)`. Without
   it, the `tsvector` fallback: `plainto_tsquery('english', …)` ordered by
   `ts_rank`. `bml_db::lexical_index` says which index the library has.
4. **Fusion** (`fusion::fuse`): weighted reciprocal rank,
   `w / (RRF_K + rank)` with `RRF_K` 60, vectors weighted 2.0 and words 1.0.
   Equal scores keep the order they first appeared in, vectors before
   words.
5. **No boilerplate** (`filter::is_boilerplate`): a fused chunk that is a
   reference list or a funding, competing-interest or acknowledgements
   statement is dropped before grouping, so a paper whose only matches are
   such passages drops out. The heuristic counts reference signals: DOIs
   (double weight), "(2022) 27:" year-volume, "56(9):37-44" page ranges,
   "et al." outside an in-text "(… et al., 2025)" citation, and numbered
   author entries. `REFERENCE_SIGNALS` (3) or more, at least one of them a
   hard signal (a DOI, a year-volume or a page range), is a reference list:
   narrative citations in a discussion ("Cuijpers et al. found…") have no
   hard signal and stay. A statement needs a heading form ("Funding:",
   "Competing interests.") or "This study was funded by". On
   the demo library on 2026-11-15, 6 of 24 passages shown for 8 clinical
   questions were reference lists before the filter and none after.
6. **One hit per paper** (`fusion::best_per_paper`): each paper's best
   chunk, in score order, truncated to `limit`; then one query for the hits'
   metadata.

## Reading a paper

`bml_library::index::paper_text(cache, db, id) -> PaperText { title, meta,
text }`. The text is the held full text, read with the index's own
`canonical` (JATS, or PDF through MuPDF). It falls back to the abstract when
only the abstract is held, or when the file cannot be read. `meta` is
"Journal · year".

## Tests

`fusion.rs` unit tests cover fusion and grouping. `tests/search.rs` (ignored;
`BML_TEST_PG_BINDIR`, plus `BML_TEST_PG_EXTENSION_DIRS` for BM25) covers:
blank and whitespace queries, which never call the model; an empty library;
a paper found by meaning alone (a keyword stub embedder, where no query word
is in the paper); a word query; boilerplate passages left out
(`boilerplate_passages_are_not_shown`); and the tsvector fallback, run on a
server set up without the folders that bring pg_search
(`the_fallback_server_has_the_tsvector_index` checks it really is
tsvector). Where pgvector and pg_search share one extension folder (a pgdist
bundle), the fallback tests skip; bml-db's schema tests cover tsvector
there.
