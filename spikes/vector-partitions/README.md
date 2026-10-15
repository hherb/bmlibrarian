# Phase 0d — resumable vector indexing (pgvector, 256 d)

Question: can HNSW indexing over tens of millions of 256-d vectors be split
into bounded, restartable units — one index per partition of ~1 M vectors —
instead of one multi-week, all-or-nothing build, and what does partitioning
cost in recall and query latency?

Data: the first N production chunk vectors (`emb_1024`, by `chunk_id`), read
from `knowledgebase` in READ ONLY transactions, sliced to 256 dims in SQL and
L2-renormalised. Queries: PubMedQA questions embedded with arctic's
`query: ` prompt and truncated the same way. Everything is written to schema
`spike_vec` in `bmlibrarian_dev` (after `ALTER EXTENSION vector UPDATE` there).

```bash
P=spikes/vector-partitions/vector_bench.py
uv run python $P extract --n 5000000
uv run python $P queries
uv run python $P load
uv run python $P build --whole     # per-partition HNSW (restartable), then one 5 M index
uv run python $P recall
uv run python $P insert            # after recall: it leaves dead index entries
```

Results: `results/timings.jsonl`; conclusions in `FINDINGS.md`.
