# Embedding Dimension Benchmark

Answers the question: *"If we store a shorter (Matryoshka-truncated) embedding –
e.g. 256 dimensions of `google/embeddinggemma-2` – do we lose retrieval quality
compared with our current `snowflake-arctic-embed-l-v2.0` at 1024 dimensions?"*

The tool lives in `benchmarks/embedding_dimension/` and **never touches the
BMLibrarian database**. It embeds a retrieval test collection once per model,
then evaluates every truncation of those embeddings.

## Quick start

```bash
# Default: arctic vs gemma2 on SciFact + NFCorpus (small biomedical collections)
uv run python benchmarks/embedding_dimension/run_benchmark.py -o results.json

# Add the larger TREC-COVID collection, capped at 20 000 documents
uv run python benchmarks/embedding_dimension/run_benchmark.py \
    --datasets scifact nfcorpus trec-covid --max-docs 20000 -o results.json
```

The first run downloads the models (several GB in total) from HuggingFace and
the datasets from the BEIR mirror. Embeddings are cached in
`~/.cache/bmlibrarian/embedding_benchmark` (`--cache-dir` to change), so
re-running with different `--dims` or `--margin` costs seconds.
A GPU is strongly recommended; on CPU expect an hour or more per model for the
default datasets.

## What is reported

For every dataset and every (model, dimension) pair:

| Column | Meaning |
|---|---|
| nDCG@10 | primary ranking-quality metric (graded relevance) |
| R@10, R@100 | fraction of relevant documents retrieved – important because BMLibrarian scores everything it retrieves |
| MRR@10 | reciprocal rank of the first relevant hit |
| MB/1M vec | pgvector storage per million vectors |
| Δ nDCG@10 | paired-bootstrap mean difference to the baseline with 95% CI |
| verdict | `better`, `non-inferior`, `worse`, `inconclusive` or `baseline` |

**Verdict logic** (margin defaults to 0.02 absolute nDCG@10, `--margin`):

- `better` – the whole CI is above 0
- `non-inferior` – the lower CI bound is above −margin ("comparable")
- `worse` – the whole CI is below −margin
- `inconclusive` – the CI straddles the margin; use more queries

The baseline is the first `--model` at its native dimension (arctic@1024 by
default). Change it with `--baseline arctic@256`, e.g. to ask whether
Gemma-2@256 is comparable to Arctic *at the same 256 storage budget*, which is
the fairest comparison because Arctic-Embed 2.0 was also trained with a 256-d
Matryoshka objective.

## Using your own evaluation set (recommended)

BEIR collections are a proxy. The decisive test is queries and relevance
judgements resembling your real use. Create a directory:

```
my_eval/
  corpus.jsonl      {"_id": "pmid123", "title": "...", "text": "abstract ..."}
  queries.jsonl     {"_id": "q1", "text": "does X reduce Y in Z?"}
  qrels/test.tsv    query-id<TAB>corpus-id<TAB>score   (header row required)
```

then run `--datasets --custom-dataset ~/my_eval` (an empty `--datasets` list
skips the BEIR downloads). Relevance scores are graded integers; 0 is ignored.
Include the distractor documents your real searches would see: the corpus must
contain more than just the relevant papers.

## Prompts matter

Embedding models are trained with task prompts (e.g. `query: `). The tool uses
the model's own built-in prompts called `query` / `document` when they exist and
**prints exactly what was applied** for each model. If the HuggingFace card for
a model recommends a different format, pass it explicitly:

```bash
--query-prefix "gemma2=task: search result | query: " \
--document-prefix "gemma2=title: none | text: "
```

(Those example strings are the EmbeddingGemma v1 format – verify the v2 model
card before relying on them.) A wrong prompt can cost several nDCG points and
invalidate the comparison.

## Interpreting results

- Compare **like with like**: Gemma-2@256 vs Arctic@256, and Gemma-2@256 vs
  Arctic@1024 (current production). Both answers are useful.
- `--max-docs` inflates absolute scores (an easier corpus) but keeps the
  comparison fair.
- Per-collection results can disagree; look at the macro-average and at your
  own evaluation set before deciding.
- A `non-inferior` verdict is only as strong as the test collection. With fewer
  than about 100 queries the CI is usually too wide to conclude anything.
- Switching models means re-embedding every document and chunk and creating
  new `vector(N)` columns/functions; this benchmark only informs that decision.

## Options

Run with `--help` for the complete list. Notable: `--model LABEL=HF_ID`
(repeatable, to add candidates), `--dims`, `--device`, `--batch-size`,
`--max-seq-length`, `--trust-remote-code` (off by default; enable only for model
repos you trust), `--seed`.
