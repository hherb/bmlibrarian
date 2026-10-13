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

## Follow-up (2026-10-13): Rust-native embedding in-process with llama.cpp

**The question.** The owner remembered "a Rust implementation for fast
embeddings". Research (crates.io/GitHub, Oct 2026) found:
- That is most likely **fastembed-rs** (`fastembed` 7.1.1). Its built-in
  "SnowflakeArcticEmbedL" is the **v1** model (BERT-large, English), whose
  vectors are incompatible with ours; the v2.0 entry (PR #239) was closed
  unmerged. It also runs ONNX Runtime, whose CoreML path is reported slow for
  BERT-large on Apple Silicon.
- HF text-embeddings-inference is server-only (best on CUDA).
- model2vec-rs (static embeddings) uses a different vector space.
- The strongest library candidate was **`llama-cpp-2` 0.1.159**: Rust
  bindings to llama.cpp (the engine inside Ollama), with Metal and CUDA as
  features.

**The spike.** `llamacpp/`: tokenise, sort by length, pack up to 2 048
tokens and 16 sequences per batch, CLS pooling inside llama.cpp, then the
production step (256 d, L2). Same 2 000 abstracts. Ollama's 17-month-old blob
no longer loads in current llama.cpp ("invalid gguf type for
tokenizer.ggml.precompiled_charsmap"), so the model came from HF:
`Casual-Autopsy/snowflake-arctic-embed-l-v2.0-gguf`.

| Backend | Runs (docs/s) | Mean | 256-d cosine vs sentence-transformers (median / min) |
|---|---|---|---|
| `llama-cpp-2` F16, in-process, Metal | 37.4, 30.9, 29.0, 26.9 | ~31 | 0.99999 / 0.99965 |
| PyTorch MPS fp16 (sentence-transformers) | 32.7, 31.7, 28.0, 28.4 | ~30 | 1.0 / 0.99969 |
| `llama-cpp-2` Q8_0 | 35.1, 30.7 | ~33 | 0.99959 / 0.9992 |
| Ollama F16 (HTTP, same engine, old build) | 26.7 | — | 0.99999 / 0.99965 |

Larger batches brought no clear benefit (4 096 tokens / 32 sequences: 34.0;
8 192 / 64: 29.0 docs/s). Runs drifted downward over the session (thermal),
±10–15 %, so the two leading methods were alternated.

**Verdict.** Rust in-process llama.cpp **matches PyTorch fp16** within noise,
with essentially identical vectors, and beats Ollama's HTTP path. Q8_0 brings
no speed gain and slightly lower agreement, so use **F16**. **Recommendation
for the port:** embed in-process through `llama-cpp-2` (`metal` now, `cuda`
later), with the GGUF pinned by repository + revision + sha256. No Python
sidecar and no Ollama dependency for embeddings.
