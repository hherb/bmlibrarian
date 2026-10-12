# Phase 0b findings — embedding throughput (2026-10-12)

Machine: Apple M3 Max, MPS/Metal. Model: `snowflake-arctic-embed-l-v2.0`
(XLM-RoBERTa large, 568 M parameters), as documents (no prompt), CLS pooling.
Compared at the **production size: first 256 dims, L2-renormalised**. Sample:
2 000 PubMed abstracts from the 2026-10-12 evaluation corpus, seeded (median
1 389 characters, 668 563 tokens in total, ≈ 334 tokens/abstract). Raw data:
`results/timings.jsonl`.

## Results

| Backend | Precision | Batch | docs/s | tokens/s | 256-d cosine vs reference (median / min) |
|---|---|---|---|---|---|
| sentence-transformers, MPS | f32 | 16 | 16.9 | 5 664 | 1.0 / 1.0 |
| sentence-transformers, MPS | f32 | 32 | 14.6 | 4 871 | reference |
| sentence-transformers, MPS | f32 | 64 | 15.0 | 5 000 | 1.0 / 1.0 |
| **sentence-transformers, MPS** | **f16** | 16 | **32.7** | **10 928** | 1.0 / 0.99969 |
| sentence-transformers, MPS | bf16 | 16 | 32.2 | 10 770 | 0.99993 / 0.99953 |
| Ollama `snowflake-arctic-embed2` (GGUF F16, llama.cpp/Metal) via `bmlibrarian.llm` | f16 | 32 | 26.7 | — | 0.99999 / 0.99965 |
| Rust candle 0.11 `xlm_roberta`, Metal | f32 | 16 | 10.5 | 3 520 | 1.0 / 1.0 |
| Rust candle 0.11 `xlm_roberta`, Metal | f32 | 32 | 8.3 | 2 783 | 1.0 / 1.0 |

Every backend computes the same vectors. All pass the ≥ 0.99 median-cosine
gate by a wide margin; even the worst single document in the half-precision
runs is at 0.9995.

## Verdict

- **Fastest: PyTorch on MPS in half precision (32.7 docs/s)**, then Ollama
  (26.7 docs/s, F16 GGUF). Both are 2× or more faster than any f32 path.
- **candle is not competitive yet.** At equal precision (f32) it runs at
  0.6× PyTorch MPS. Its `xlm_roberta` model is f32/f64-only:
  `prepare_4d_attention_mask` panics on any other dtype, so it cannot use the
  half-precision speed-up. Native Rust inference is **not** a reason for the
  port.
- **Embedding throughput is a hardware/precision question, not a language
  one.** For Phase 1, embedding stays a *service* behind a trait:
  - Ollama (works from Rust through bmlib's OpenAI-compatible client or
    `ollama-rs`; stability under bulk load was a concern in
    `chunk_embedder.py`), **or**
  - a small fp16 PyTorch sidecar, the fastest measured,
  - with candle kept as an option should it gain f16 support for XLM-R.

## What it means for the backlog

At 32.7 abstract-sized texts/s, 1 M texts take ≈ 8.5 h, and 38 M take
≈ 13.5 days of continuous GPU time. That is why the plan **reuses the
existing 37.5 M vectors** (truncated to 256 d, cosine 0.9987 against this
model) instead of re-embedding. Only new documents and the 6.7 M-document
chunk queue need embedding.

Levers, in rough order of size:
1. f16 instead of f32: 1.9×, measured.
2. A CUDA box, if available: typically several × an M3 Max for encoder
   models (not measured here).
3. Capping `max_seq_length` for chunks (8192 is the model limit; chunks are
   ~1–2 k characters, so long-tail padding cost is small).
4. Sorting by length before batching (already done by every backend here).

Truncating to 256 d does **not** reduce inference cost; the full network still
runs. It reduces storage and index cost only.

## Caveats

- One sample, one machine, one run per configuration. Ollama ran with its
  default parallelism; candle and sentence-transformers report time after a
  warm-up batch.
- TEI (HF text-embeddings-inference) was not installed. It is candle-based, so
  on Metal it is likely to share candle's f32 limitation; that is unverified.
