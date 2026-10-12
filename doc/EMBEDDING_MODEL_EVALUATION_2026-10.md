# Embedding Model & Dimension Evaluation — October 2026

**Question:** can we cut vector storage by 4× by moving from
`Snowflake/snowflake-arctic-embed-l-v2.0` at 1024 dimensions (production) to
`google/embeddinggemma-2` truncated to 256 dimensions, without losing retrieval
quality?

**Answer: no, but truncating Arctic to 256 dimensions works.**

- **Do not switch to EmbeddingGemma 2.** It wins on the public BEIR
  collections (Part 1), especially SciFact. On BMLibrarian's own data (Part 2)
  it is significantly worse than Arctic at every dimension: −0.036 nDCG@10 at
  768 d and −0.051 at 256 d versus production, over 1000 queries.
- **Arctic@256 is non-inferior to Arctic@1024 on every collection with enough
  queries.** It costs 0.5–1 nDCG@10 point on four collections (SciFact,
  NFCorpus, and two BMLibrarian sets) and uses a quarter of the storage.
- **No re-embedding is needed.** Production vectors (Ollama
  `snowflake-arctic-embed2`) match the benchmarked HuggingFace model: median
  cosine 0.9985 on 20 random production chunks. The existing 37.5 M vectors
  can be truncated and re-normalised in place.

Run date: 2026-10-12. Tools: `benchmarks/embedding_dimension/run_benchmark.py`
and `build_bmlibrarian_eval.py` (see `doc/users/embedding_dimension_benchmark.md`).
Raw results: `benchmarks/embedding_dimension/results/2026-10-12_*.json`.

## Part 2 — BMLibrarian's own data (decisive)

### Evaluation sets

The sets were built with `build_bmlibrarian_eval.py`, using a read-only
transaction on `knowledgebase`. All three share one corpus of **48 629 PubMed
abstracts**: 18 629 judged documents plus 30 000 random PubMed abstracts
(≥ 200 characters, `TABLESAMPLE … REPEATABLE(42)`). Documents are
**abstract only**. PubMedQA questions are their source paper's title verbatim
(median similarity 1.0), so including titles would test string matching.

| set | queries | judgements | what counts as relevant | pool bias |
|---|---|---|---|---|
| `pubmedqa_source` | 1000 | 1000 | the paper each fact-checker PubMedQA question was written from | **none** (human-sourced) |
| `pubmedqa_graded` | 1000 | 12 168 | source paper (grade 2) + fact-checker evidence, LLM score 5 → 2, 4 → 1 | favours Arctic |
| `research_questions` | 12 | 173 | research questions typed into BMLibrarian; scoring-agent score 3/4/5 → 1/2/3 | favours Arctic |

**Pool bias.** BMLibrarian's hybrid search uses Arctic for its semantic leg, so
only documents that search found were ever judged. A relevant document that
only gemma2 ranks highly is unjudged and counts against gemma2. The
`pubmedqa_source` set has no such bias, and it shows the *largest* gemma2
deficit, so pool bias does not explain the result.

Low-scored judged documents stay in the corpus as hard negatives: 0–2 from the
scoring agent, 3 from the evidence table.

### Results vs production (arctic@1024)

Paired bootstrap, 10 000 resamples, margin 0.02. "MB/1M" is listed in Part 1:
1024 d = 4104, 768 d = 3080, 512 d = 2056, 256 d = 1032.

**`pubmedqa_source`** (1000 queries, model-neutral judgements)

| config | nDCG@10 | R@10 | R@100 | MRR@10 | Δ nDCG@10 [95% CI] | verdict |
|---|---|---|---|---|---|---|
| arctic@1024 | **0.7915** | **0.9240** | 0.9980 | **0.7490** | — | baseline |
| arctic@768 | 0.7881 | 0.9200 | 0.9980 | 0.7456 | −0.003 [−0.008, +0.001] | non-inferior |
| arctic@512 | 0.7838 | 0.9200 | 0.9980 | 0.7401 | −0.008 [−0.013, −0.003] | non-inferior |
| arctic@256 | 0.7815 | 0.9200 | 0.9980 | 0.7371 | −0.010 [−0.016, −0.005] | non-inferior |
| arctic@128 | 0.7600 | 0.9010 | 0.9970 | 0.7148 | −0.032 [−0.042, −0.021] | worse |
| gemma2@768 | 0.7558 | 0.8980 | 0.9960 | 0.7100 | −0.036 [−0.051, −0.020] | worse |
| gemma2@512 | 0.7522 | 0.8980 | 0.9960 | 0.7054 | −0.039 [−0.055, −0.024] | worse |
| gemma2@256 | 0.7406 | 0.8940 | 0.9950 | 0.6915 | −0.051 [−0.067, −0.035] | worse |
| gemma2@128 | 0.7058 | 0.8830 | 0.9870 | 0.6496 | −0.086 [−0.103, −0.068] | worse |

**`pubmedqa_graded`** (1000 queries, 12.2 relevant per query)

| config | nDCG@10 | R@10 | R@100 | MRR@10 | Δ nDCG@10 [95% CI] | verdict |
|---|---|---|---|---|---|---|
| arctic@1024 | **0.8384** | **0.6911** | **0.9984** | **0.9622** | — | baseline |
| arctic@768 | 0.8349 | 0.6875 | 0.9984 | 0.9583 | −0.004 [−0.006, −0.001] | non-inferior |
| arctic@512 | 0.8350 | 0.6880 | 0.9984 | 0.9584 | −0.003 [−0.006, −0.001] | non-inferior |
| arctic@256 | 0.8335 | 0.6881 | 0.9984 | 0.9590 | −0.005 [−0.008, −0.002] | non-inferior |
| arctic@128 | 0.8178 | 0.6756 | 0.9963 | 0.9471 | −0.021 [−0.026, −0.015] | inconclusive |
| gemma2@768 | 0.8169 | 0.6739 | 0.9968 | 0.9522 | −0.021 [−0.028, −0.015] | inconclusive* |
| gemma2@512 | 0.8142 | 0.6711 | 0.9963 | 0.9487 | −0.024 [−0.031, −0.017] | inconclusive* |
| gemma2@256 | 0.8043 | 0.6617 | 0.9939 | 0.9422 | −0.034 [−0.042, −0.027] | worse |
| gemma2@128 | 0.7808 | 0.6445 | 0.9796 | 0.9277 | −0.058 [−0.066, −0.049] | worse |

\* The whole CI is below 0, so the loss is real. "Inconclusive" only means it
is not proven to exceed the 0.02 margin.

**`research_questions`** (12 queries: descriptive only)

| config | nDCG@10 | R@10 | R@100 | Δ nDCG@10 [95% CI] |
|---|---|---|---|---|
| arctic@1024 | 0.5480 | 0.4724 | **0.9703** | — |
| arctic@256 | 0.5444 | 0.4816 | 0.9506 | −0.004 [−0.026, +0.029] |
| gemma2@768 | 0.5254 | 0.5177 | 0.9595 | −0.023 [−0.122, +0.077] |
| gemma2@512 | 0.5303 | **0.5315** | 0.9595 | −0.018 [−0.125, +0.092] |
| gemma2@256 | 0.5219 | **0.5315** | 0.9345 | −0.026 [−0.123, +0.071] |

All verdicts on this set are inconclusive, as 12 queries can't separate
anything. The point estimates agree with the PubMedQA sets: Arctic leads on
nDCG, and gemma2 has slightly higher R@10 but lower R@100.

### Equal-storage and within-model comparisons

| comparison | `pubmedqa_source` Δ [95% CI] | `pubmedqa_graded` Δ [95% CI] |
|---|---|---|
| gemma2@256 vs arctic@256 (same storage) | −0.041 [−0.057, −0.025] worse | −0.029 [−0.036, −0.022] worse |
| arctic@256 vs gemma2@768 (⅓ the storage) | +0.026 [+0.010, +0.041] better | +0.017 [+0.010, +0.023] better |
| gemma2@512 vs gemma2@768 | −0.004 [−0.009, +0.001] non-inferior | −0.003 [−0.006, −0.000] non-inferior |
| gemma2@256 vs gemma2@768 | −0.015 [−0.023, −0.008] inconclusive | −0.013 [−0.017, −0.009] non-inferior |

### Prompt check

PubMedQA queries are questions. For questions, the EmbeddingGemma 2 card offers
a `task: question answering | query: ` prompt as well as the default
`task: search result | query: `. Re-running with the QA prompt changed nothing
material. gemma2@768 scored 0.7520 vs 0.7558 on `pubmedqa_source`, 0.8168 vs
0.8169 on `pubmedqa_graded`, and 0.5316 vs 0.5254 on `research_questions`.
Gemma2's deficit is not a prompt artefact. (Results:
`*_gemma-qa-prompt.json`.)

### Production vectors match the benchmarked model

I took 20 random production chunks (`emb_1024`, model_id 1 =
`snowflake-arctic-embed2:latest` via Ollama) and re-embedded their text with
HuggingFace `Snowflake/snowflake-arctic-embed-l-v2.0`. Cosine similarity to the
stored vectors: median **0.9985** (min 0.9873) at 1024 d, and median **0.9987**
(min 0.9906) after both are truncated to 256 d and re-normalised. These
benchmark results therefore apply to the stored vectors, and truncation needs
no re-embedding.

### Why Part 1 and Part 2 disagree

Gemma2's +0.15 nDCG lead on SciFact was already flagged in Part 1 as
implausibly large. SciFact is an MTEB task, and the gemma2 model card makes no
decontamination statement. On NFCorpus, the BEIR collection most like
BMLibrarian's use (PubMed-style documents), the two models were already tied.
On 48.6 k real PubMed abstracts with realistic distractors, Arctic is clearly
better. The most plausible reading is that gemma2's public-benchmark
advantage does not carry over to this domain.

### Part 2 caveats

- **PubMedQA queries are paper titles phrased as questions.** The task is
  "find the abstract behind this title-question". That is semantically
  meaningful because there are no titles in the corpus, but it is not the
  same as open research questions. The 12 real research questions point the
  same way but can't confirm it statistically.
- **Recall@100 is at the ceiling** (≥ 0.994) on both PubMedQA sets, so the
  sets can't separate configurations on the metric that matters most for
  BMLibrarian. On the research set, arctic@256 has R@100 0.951 vs 0.970 at
  1024 d. With 12 queries and no CI, that may be noise, but it should be
  watched.
- **Possible training exposure for Arctic.** PubMedQA is public, and Arctic's
  training data is not fully documented either. The `research_questions` set,
  whose queries cannot have been seen in training, agrees with the PubMedQA
  sets.
- **Corpus scale.** 48.6 k documents vs 37.5 M production chunks. Truncation
  losses usually grow with corpus size. Production also embeds chunks, while
  this benchmark embedded whole abstracts.
- **Run notes.** Apple Silicon, MPS, single run. Document encoding took about
  53 min for Arctic and about 28 min for gemma2 (bf16). One gemma2 pass was
  killed by macOS partway through. `run_benchmark.py` now encodes in
  resumable 4096-text chunks and frees accelerator memory between them.

### Storage and migration notes

| | now (1024 d) | arctic@256 |
|---|---|---|
| raw vector payload, 37.5 M vectors | ~154 GB | ~39 GB |
| `emb_1024` total incl. indexes | 484 GB (HNSW `arctic_hnsw_idx_v4`: 286 GB) | substantially smaller; rebuild needed to measure |

- The installed pgvector is **0.5.1**, which has no `subvector()`,
  `l2_normalize()` or `halfvec`; they arrived in 0.7.0. Either upgrade pgvector
  and populate a `vector(256)` column/table with
  `l2_normalize(subvector(embedding, 1, 256))`, or truncate and normalise in
  Python batches.
- **Query vectors must be truncated and re-normalised the same way.**
  Comparing a 256 d corpus against an untruncated query is invalid.
- Use an idempotent migration, test it on `bmlibrarian_dev` first, and get
  explicit approval before touching `knowledgebase`.

## Part 1 — public BEIR collections

These results came first and led to a provisional recommendation of
EmbeddingGemma 2 at 512 d. **Part 2 overturns that recommendation.** Part 1 is
kept because the BEIR numbers, and the SciFact contamination concern, explain
why the two parts disagree.

### Setup

| | |
|---|---|
| Collections | BEIR SciFact (300 queries, 5 183 docs), BEIR NFCorpus (323 queries, 3 633 docs), full corpora (`--max-docs 0`) |
| Models | arctic = `Snowflake/snowflake-arctic-embed-l-v2.0` (native 1024 d); gemma2 = `google/embeddinggemma-2` (native 768 d, text-only) |
| Dimensions | 1024 / 768 / 512 / 256 / 128 — Matryoshka truncation + L2 re-normalisation |
| Prompts | arctic: query `query: `, document none. gemma2: query `task: search result \| query: `, document `title: none \| text: ` (the model's own built-in prompts; they match the v2 model card) |
| Hardware | Apple Silicon, MPS; gemma2 ran in bfloat16 as its model card recommends (never float16) |
| Statistics | paired bootstrap of per-query nDCG@10, 10 000 resamples, seed 42; non-inferiority margin 0.02 absolute nDCG@10 |
| Library versions | sentence-transformers 6.1.0, transformers 5.19.0, torch 2.14.1 (gemma2 needs ≥ 6.1.0 / ≥ 5.18 and torchvision) |

### Results

nDCG@10 is the primary metric. Recall@100 matters most for BMLibrarian, because
the scoring agent sees every document the search retrieves. A document the
search misses is lost; a low-ranked one is not. MB/1M = raw pgvector storage
per million vectors, before index overhead.

#### SciFact

| config | nDCG@10 | R@10 | R@100 | MRR@10 | MB/1M | Δ vs arctic@1024 [95% CI] | verdict |
|---|---|---|---|---|---|---|---|
| arctic@1024 | 0.7098 | 0.8351 | 0.9350 | 0.6770 | 4104 | — | baseline |
| arctic@512 | 0.6975 | 0.8251 | 0.9283 | 0.6650 | 2056 | −0.012 [−0.023, −0.002] | inconclusive |
| arctic@256 | 0.7005 | 0.8151 | 0.9217 | 0.6723 | 1032 | −0.009 [−0.020, +0.001] | non-inferior |
| gemma2@768 | **0.8626** | 0.9442 | 0.9800 | 0.8405 | 3080 | +0.153 [+0.115, +0.191] | better |
| gemma2@512 | 0.8572 | 0.9342 | **0.9833** | 0.8370 | 2056 | +0.148 [+0.109, +0.187] | better |
| gemma2@256 | 0.8425 | 0.9147 | 0.9700 | 0.8242 | 1032 | +0.133 [+0.094, +0.172] | better |
| gemma2@128 | 0.7932 | 0.8758 | 0.9633 | 0.7729 | 520 | +0.083 [+0.042, +0.124] | better |

#### NFCorpus

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

#### Macro-average nDCG@10

| dim | arctic | gemma2 |
|---|---|---|
| 1024 | 0.531 | — |
| 768 | 0.523 | **0.611** |
| 512 | 0.520 | 0.607 |
| 256 | 0.523 | 0.592 |
| 128 | 0.466 | 0.541 |

#### Same-storage and within-model comparisons

These runs use the same cached embeddings with a different `--baseline`.

| comparison | SciFact Δ [95% CI] | NFCorpus Δ [95% CI] |
|---|---|---|
| gemma2@256 vs arctic@256 (equal storage) | +0.142 [+0.103, +0.182] better | −0.004 [−0.021, +0.013] inconclusive |
| gemma2@512 vs gemma2@768 | −0.005 [−0.013, +0.002] non-inferior | −0.003 [−0.009, +0.002] non-inferior |
| gemma2@256 vs gemma2@768 | −0.020 [−0.032, −0.009] inconclusive | −0.019 [−0.029, −0.009] inconclusive |

### Interpretation

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

### Caveats

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

### Storage implications

These are raw vector sizes for 38 M PubMed abstracts, before HNSW/IVF index
overhead and before chunk embeddings, which multiply the vector count:

| config | per 1 M vectors | 38 M vectors |
|---|---|---|
| arctic@1024 (production) | 4.1 GB | ~156 GB |
| gemma2@512 | 2.1 GB | ~78 GB |
| gemma2@256 | 1.0 GB | ~39 GB |

### Part 1 provisional recommendation (superseded)

Part 1 proposed adopting EmbeddingGemma 2 at 512 d, pending a
BMLibrarian-specific evaluation. Part 2 is that evaluation, and gemma2 is
significantly worse there at every dimension. Arctic@256 was non-inferior on
both BEIR collections too: −0.009 on SciFact and −0.007 on NFCorpus.

## Recommendation

1. **Keep Arctic. Do not switch to EmbeddingGemma 2.** Gemma2 is significantly
   worse on BMLibrarian's own data at every dimension, including at equal
   storage (−0.041 / −0.029 nDCG@10 at 256 d).
2. **Truncate Arctic to 256 d.** Across the four collections with ≥ 300
   queries, arctic@256 costs 0.5–1 nDCG@10 point versus 1024 d, and every
   lower CI bound stays inside the 0.02 margin. Vector storage drops 4×. If
   that point matters, 512 d is the fallback at 2× savings (−0.003 to −0.012;
   inconclusive on SciFact, non-inferior elsewhere).
3. **No re-embedding**: truncate and re-normalise the existing vectors (see
   Storage and migration notes in Part 2). Queries get the same treatment.
4. **Before switching search over:** on `bmlibrarian_dev`, compare top-100
   results of HNSW@256 against exact search@1024 for a batch of real queries.
   Truncation loss and HNSW approximation stack, and the scoring agent depends
   on top-100 recall.

## Next steps

- Grow the `research_questions` set. Every BMLibrarian session adds scored
  documents to `audit.document_scores`, and about 100 questions would make
  that set decisive.
- Extend the bootstrap to Recall@100, so recall differences get CIs.
- Consider `halfvec` (pgvector ≥ 0.7) on top of truncation, for another 2× with
  typically negligible loss. Benchmark it first.
- Optionally add TREC-COVID (`--datasets trec-covid --max-docs 20000`) as a
  larger public cross-check.

## Reproducing

```bash
# Part 1 — BEIR (production baseline, then alternative baselines from cache)
uv run python benchmarks/embedding_dimension/run_benchmark.py -o results.json
uv run python benchmarks/embedding_dimension/run_benchmark.py --baseline arctic@256 -o res_arctic_256.json
uv run python benchmarks/embedding_dimension/run_benchmark.py --baseline gemma2@768 -o res_gemma2_768.json

# Part 2 — BMLibrarian sets (reads the database; read-only)
uv run python benchmarks/embedding_dimension/build_bmlibrarian_eval.py
E=~/.cache/bmlibrarian/embedding_benchmark/bmlibrarian_eval
for s in pubmedqa_source pubmedqa_graded research_questions; do
  uv run python benchmarks/embedding_dimension/run_benchmark.py --datasets \
      --custom-dataset $E/$s/eval -o results_$s.json
done
# alternative baselines / prompt check, e.g.
uv run python benchmarks/embedding_dimension/run_benchmark.py --datasets \
    --custom-dataset $E/pubmedqa_source/eval --baseline arctic@256 -o src_arctic256.json
uv run python benchmarks/embedding_dimension/run_benchmark.py --datasets \
    --custom-dataset $E/pubmedqa_source/eval \
    --query-prefix "gemma2=task: question answering | query: " -o src_qa.json
```
