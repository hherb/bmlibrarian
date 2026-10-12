# Embedding Model & Dimension Evaluation — October 2026

**Question:** can we replace `Snowflake/snowflake-arctic-embed-l-v2.0` at 1024
dimensions (current production) with `google/embeddinggemma-2` truncated to 256
dimensions, cutting vector storage by 4×, without losing retrieval quality?

**Short answer:** EmbeddingGemma 2 is the better model. At **512 dimensions** it
is at least as good as production on both test collections at half the storage.
At **256 dimensions** it is clearly better on SciFact, but on NFCorpus the
result is *inconclusive*: the point estimate is about 1 nDCG point below
production and the confidence interval crosses the −0.02 margin. Of the two
dimensions, only 512 can be justified from these data alone. Before committing
to 256, run the benchmark on a BMLibrarian-specific evaluation set (see
[Next steps](#next-steps)).

Run date: 2026-10-12. Tool: `benchmarks/embedding_dimension/run_benchmark.py`
(see `doc/users/embedding_dimension_benchmark.md`). Raw results:
`benchmarks/embedding_dimension/results/2026-10-12_*.json`.

## Setup

| | |
|---|---|
| Collections | BEIR SciFact (300 queries, 5 183 docs), BEIR NFCorpus (323 queries, 3 633 docs), full corpora (`--max-docs 0`) |
| Models | arctic = `Snowflake/snowflake-arctic-embed-l-v2.0` (native 1024 d); gemma2 = `google/embeddinggemma-2` (native 768 d, text-only) |
| Dimensions | 1024 / 768 / 512 / 256 / 128 — Matryoshka truncation + L2 re-normalisation |
| Prompts | arctic: query `query: `, document none. gemma2: query `task: search result \| query: `, document `title: none \| text: ` (the model's own built-in prompts; they match the v2 model card) |
| Hardware | Apple Silicon, MPS; gemma2 ran in bfloat16 as its model card recommends (never float16) |
| Statistics | paired bootstrap of per-query nDCG@10, 10 000 resamples, seed 42; non-inferiority margin 0.02 absolute nDCG@10 |
| Library versions | sentence-transformers 6.1.0, transformers 5.19.0, torch 2.14.1 (gemma2 needs ≥ 6.1.0 / ≥ 5.18 and torchvision) |

## Results

nDCG@10 is the primary metric. Recall@100 matters most for BMLibrarian, because
the scoring agent sees every document the search retrieves. A document the
search misses is lost; a low-ranked one is not. MB/1M = raw pgvector storage
per million vectors, before index overhead.

### SciFact

| config | nDCG@10 | R@10 | R@100 | MRR@10 | MB/1M | Δ vs arctic@1024 [95% CI] | verdict |
|---|---|---|---|---|---|---|---|
| arctic@1024 | 0.7098 | 0.8351 | 0.9350 | 0.6770 | 4104 | — | baseline |
| arctic@512 | 0.6975 | 0.8251 | 0.9283 | 0.6650 | 2056 | −0.012 [−0.023, −0.002] | inconclusive |
| arctic@256 | 0.7005 | 0.8151 | 0.9217 | 0.6723 | 1032 | −0.009 [−0.020, +0.001] | non-inferior |
| gemma2@768 | **0.8626** | 0.9442 | 0.9800 | 0.8405 | 3080 | +0.153 [+0.115, +0.191] | better |
| gemma2@512 | 0.8572 | 0.9342 | **0.9833** | 0.8370 | 2056 | +0.148 [+0.109, +0.187] | better |
| gemma2@256 | 0.8425 | 0.9147 | 0.9700 | 0.8242 | 1032 | +0.133 [+0.094, +0.172] | better |
| gemma2@128 | 0.7932 | 0.8758 | 0.9633 | 0.7729 | 520 | +0.083 [+0.042, +0.124] | better |

### NFCorpus

| config | nDCG@10 | R@10 | R@100 | MRR@10 | MB/1M | Δ vs arctic@1024 [95% CI] | verdict |
|---|---|---|---|---|---|---|---|
| arctic@1024 | 0.3528 | 0.1678 | 0.2981 | **0.5662** | 4104 | — | baseline |
| arctic@512 | 0.3431 | 0.1656 | 0.2997 | 0.5502 | 2056 | −0.010 [−0.017, −0.003] | non-inferior |
| arctic@256 | 0.3454 | 0.1660 | 0.2932 | 0.5560 | 1032 | −0.007 [−0.013, −0.002] | non-inferior |
| gemma2@768 | **0.3603** | 0.1767 | **0.3428** | 0.5580 | 3080 | +0.008 [−0.008, +0.024] | non-inferior |
| gemma2@512 | 0.3568 | **0.1769** | 0.3383 | 0.5552 | 2056 | +0.004 [−0.012, +0.020] | non-inferior |
| gemma2@256 | 0.3417 | 0.1707 | 0.3232 | 0.5445 | 1032 | −0.011 [−0.028, +0.005] | inconclusive |
| gemma2@128 | 0.2885 | 0.1371 | 0.2681 | 0.4856 | 520 | −0.064 [−0.085, −0.045] | worse |

Arctic@768 and arctic@128 are omitted from these tables; they are in the JSON.
Arctic@128 is `worse` on both collections.

### Macro-average nDCG@10

| dim | arctic | gemma2 |
|---|---|---|
| 1024 | 0.531 | — |
| 768 | 0.523 | **0.611** |
| 512 | 0.520 | 0.607 |
| 256 | 0.523 | 0.592 |
| 128 | 0.466 | 0.541 |

### Same-storage and within-model comparisons

These runs use the same cached embeddings with a different `--baseline`.

| comparison | SciFact Δ [95% CI] | NFCorpus Δ [95% CI] |
|---|---|---|
| gemma2@256 vs arctic@256 (equal storage) | +0.142 [+0.103, +0.182] better | −0.004 [−0.021, +0.013] inconclusive |
| gemma2@512 vs gemma2@768 | −0.005 [−0.013, +0.002] non-inferior | −0.003 [−0.009, +0.002] non-inferior |
| gemma2@256 vs gemma2@768 | −0.020 [−0.032, −0.009] inconclusive | −0.019 [−0.029, −0.009] inconclusive |

## Interpretation

1. **Gemma2 is a stronger retriever than Arctic.** Gemma2 is better or
   non-inferior to production at 512 d and above on both collections. Its
   macro-average beats Arctic at every dimension, even when Gemma2 has fewer
   dimensions. Even gemma2@128 beats arctic@1024 on SciFact.

2. **The SciFact margin is suspiciously large.** A +0.15 nDCG@10 gap between
   two modern retrieval-tuned embedders is far more than usual. SciFact and
   NFCorpus are both MTEB retrieval tasks. The EmbeddingGemma 2 model card
   reports MTEB scores but makes no decontamination statement, so training on
   SciFact's train split, or on similar claim-verification data, cannot be
   ruled out. NFCorpus shows a much smaller gap. **Treat NFCorpus as the
   more trustworthy signal**, and treat SciFact as an upper bound on the gain.

3. **512 is nearly lossless; 256 costs about 2 nDCG points.** Within Gemma2,
   512 d is non-inferior to 768 d on both collections. 256 d loses about 0.02
   on both, and its CI straddles the margin. The model card describes 256 as
   "close to lossless" on MTEB averages. On these biomedical collections it
   is slightly worse than that.

4. **Gemma2@256 vs production depends on the collection.** It is
   decisively better on SciFact. On NFCorpus it is inconclusive: the
   point estimate is −0.011, and the CI runs from −0.028 to +0.005. A
   loss of up to about 3 nDCG points cannot be excluded.

5. **Recall@100 favours Gemma2, even at 256 d.** Gemma2@256 retrieves more
   relevant documents in the top 100 than arctic@1024 on both collections:
   0.970 vs 0.935 on SciFact and 0.323 vs 0.298 on NFCorpus. Because
   BMLibrarian re-scores every retrieved document with an LLM, top-100 recall
   matters more than top-10 ordering. This is the strongest argument for 256.
   However, the tool does not yet bootstrap recall, so these recall differences
   have no confidence interval.

## Caveats

- **Small corpora.** The collections hold 3.6 k–5.2 k documents. Production
  holds tens of millions of abstracts and chunks. With more distractors,
  truncated vectors usually lose more, so the 256 d penalty is likely to grow
  at PubMed scale.
- **Proxy queries.** SciFact queries are scientific claims. NFCorpus queries
  are consumer-health questions matched against PubMed-style documents.
  Neither matches BMLibrarian's real research questions or HyDE queries
  exactly.
- **Single run, one hardware path.** Gemma2 ran in bfloat16 on MPS. Results
  on CUDA or in float32 should match closely but were not checked.
- **Throughput not compared.** Gemma2 took about 150 s (SciFact) and 140 s
  (NFCorpus) to embed the documents on MPS. Arctic's embeddings came from cache,
  so the two models' speeds were not measured side by side.

## Storage implications

These are raw vector sizes for 38 M PubMed abstracts, before HNSW/IVF index
overhead and before chunk embeddings, which multiply the vector count:

| config | per 1 M vectors | 38 M vectors |
|---|---|---|
| arctic@1024 (production) | 4.1 GB | ~156 GB |
| gemma2@512 | 2.1 GB | ~78 GB |
| gemma2@256 | 1.0 GB | ~39 GB |

## Recommendation

1. **Adopt EmbeddingGemma 2 as the candidate replacement**, subject to step 3.
2. **Default to 512 d.** It is the smallest dimension that is non-inferior or
   better than production on every comparison here, and it halves storage.
3. **Before choosing 256 d**, re-run the benchmark (it takes minutes from cache)
   on a BMLibrarian evaluation set. Use real research questions from past
   sessions, with judged relevant PMIDs and realistic distractors, via
   `--custom-dataset`. Choose 256 if it is non-inferior there and its
   Recall@100 holds up.
4. A model switch means re-embedding all documents and chunks, and creating new
   `vector(N)` columns, indexes and search functions through an idempotent
   migration. The benchmark does not cover that work.

## Next steps

- Build the BMLibrarian-specific evaluation set (`corpus.jsonl`,
  `queries.jsonl`, `qrels/test.tsv`). See
  `doc/users/embedding_dimension_benchmark.md`.
- Add TREC-COVID (`--datasets trec-covid --max-docs 20000`) as a third public
  collection that is larger and less likely to be in the training data.
- Extend the bootstrap to Recall@100, so the recall advantage gets a CI.

## Reproducing

```bash
# Production baseline (arctic@1024)
uv run python benchmarks/embedding_dimension/run_benchmark.py -o results.json
# Same-storage and within-model comparisons, from the cached embeddings
uv run python benchmarks/embedding_dimension/run_benchmark.py --baseline arctic@256 -o res_arctic_256.json
uv run python benchmarks/embedding_dimension/run_benchmark.py --baseline gemma2@768 -o res_gemma2_768.json
```
