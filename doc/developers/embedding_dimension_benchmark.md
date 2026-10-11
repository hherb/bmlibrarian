# Embedding Dimension Benchmark – Developer Notes

Location: `benchmarks/embedding_dimension/`. User guide:
`doc/users/embedding_dimension_benchmark.md`. Tests:
`tests/benchmarks/test_embedding_dimension_benchmark.py`.

## Modules

| File | Responsibility |
|---|---|
| `retrieval_metrics.py` | Pure numpy functions: `truncate_and_normalize`, `rank_corpus`, `evaluate_rankings` (nDCG/Recall/MRR), `paired_bootstrap`, `noninferiority_verdict` |
| `beir_data.py` | BEIR download (name-validated, zip-slip-safe), JSONL/TSV loading with malformed-row accounting, seeded corpus sub-sampling that keeps all relevant docs |
| `run_benchmark.py` | CLI and orchestration. Encoders are injected through an `Encoder` protocol; the default is `SentenceTransformerEncoder` |

The code is deliberately independent of the `bmlibrarian` package (importing
`bmlibrarian.embeddings` pulls in the database layer), so it runs in a bare
environment with `numpy` and `sentence-transformers`.

## Design decisions

- **Embed once, truncate afterwards.** Each model embeds each collection at its
  native dimension; truncation + L2 re-normalisation is applied to both queries
  and documents in numpy. This equals what storing a shortened pgvector value
  and using cosine distance does, and makes extra dimensions free.
- **Content-addressed embedding cache** keyed by model id, dataset, role, prompt,
  `max_seq_length` and the text itself. Any change in those invalidates the
  entry automatically.
- **Graded nDCG** with linear gain and log2 discount (pytrec_eval / BEIR
  convention). Queries without positive qrels are rejected, not scored 0.
- **Paired bootstrap over queries** (same resample indices for both
  configurations) for the difference in per-query nDCG@10, plus a
  non-inferiority verdict against a configurable margin
  (`DEFAULT_NONINFERIORITY_MARGIN = 0.02`).
- **Prompt auditability.** The resolved query/document prompts are printed and
  stored in the JSON output.
- **Failure isolation.** A model that fails to load is logged and listed under
  `failures`; remaining models still run, and the exit code is 1.

## Known limits

- Brute-force exact search, so no ANN (HNSW) recall effects are measured; those
  should be checked separately on the real pgvector index after a decision.
- BEIR's "exclude query id from results" rule is not applied (irrelevant for the
  default collections).
- Document text is `title + " " + text`; models whose cards prescribe a
  structured document prompt (e.g. `title: ... | text: ...`) need
  `--document-prefix`, which cannot interpolate the title.
- Run time is dominated by encoding; the cache mitigates reruns only.
