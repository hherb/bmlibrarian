# Phase 0b — embedding throughput spike

Embeds one seeded sample of 2 000 PubMed abstracts (taken from the 2026-10-12
evaluation corpus) with `snowflake-arctic-embed-l-v2.0` through several
backends, and compares them at the production size: the first 256 dims,
L2-renormalised.

| Backend | How |
|---|---|
| `st_bs*` | sentence-transformers on MPS (reference: `st_bs32`) |
| `ollama_bs*` | Ollama `snowflake-arctic-embed2` via `bmlibrarian.llm.LLMClient.embed_batch` |
| `candle_metal_bs*` | Rust candle `xlm_roberta` on Metal, f32, CLS pooling (`rust/`) |

```bash
uv run python spikes/embedding-throughput/bench_python.py sample
uv run python spikes/embedding-throughput/bench_python.py st
uv run python spikes/embedding-throughput/bench_python.py ollama
(cd spikes/embedding-throughput/rust && cargo build --release && \
  ./target/release/embedding-throughput-spike --model-dir \
  ~/.cache/huggingface/hub/models--Snowflake--snowflake-arctic-embed-l-v2.0/snapshots/<rev> --batch 32)
uv run python spikes/embedding-throughput/bench_python.py compare
```

Output: `results/timings.jsonl`, `results/*.npy` (256-d), comparison on stdout.
Results and conclusions: `FINDINGS.md`.
