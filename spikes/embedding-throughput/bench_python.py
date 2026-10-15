#!/usr/bin/env python3
"""
Phase 0b embedding-throughput spike — Python backends + comparison.

Every backend embeds the same sample of PubMed abstracts as *documents* (arctic
uses no document prompt) and is compared at the production size: the first 256
dims, L2-renormalised.

Subcommands:
    sample   write the text sample (seeded) to texts.jsonl
    st       sentence-transformers on MPS (reference), several batch sizes
    ollama   Ollama snowflake-arctic-embed2 via bmlibrarian.llm (batch embed)
    compare  cosine agreement of every saved .npy against the reference

Usage:
    uv run python spikes/embedding-throughput/bench_python.py sample
    uv run python spikes/embedding-throughput/bench_python.py st
"""

import argparse
import json
import random
import sys
import time
from pathlib import Path
from typing import List, Optional, Sequence

import numpy as np

SPIKE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = SPIKE_DIR / "results"
TEXTS_FILE = RESULTS_DIR / "texts.jsonl"
REFERENCE = "st_bs32"
DEFAULT_CORPUS = (Path.home() / ".cache" / "bmlibrarian" / "embedding_benchmark" / "bmlibrarian_eval"
                  / "pubmedqa_source" / "eval" / "corpus.jsonl")
HF_MODEL = "Snowflake/snowflake-arctic-embed-l-v2.0"
OLLAMA_MODEL = "snowflake-arctic-embed2:latest"
PRODUCTION_DIM = 256
DEFAULT_SAMPLE = 2000
DEFAULT_SEED = 42
ST_BATCH_SIZES = (16, 32, 64)
OLLAMA_BATCH = 32
MIN_MEDIAN_COSINE = 0.99


def truncate(emb: np.ndarray, dim: int = PRODUCTION_DIM) -> np.ndarray:
    """Matryoshka truncation + L2 re-normalisation."""
    t = emb[:, :dim].astype(np.float32)
    return t / np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-12)


def load_texts() -> List[str]:
    """Read the shared text sample."""
    with open(TEXTS_FILE, encoding="utf-8") as fh:
        return [json.loads(line)["text"] for line in fh]


def record(name: str, emb: np.ndarray, seconds: float, extra: dict) -> None:
    """Save 256-d embeddings and append a timing record."""
    np.save(RESULTS_DIR / f"{name}.npy", truncate(emb))
    row = {"backend": name, "docs": len(emb), "seconds": round(seconds, 2),
           "docs_per_s": round(len(emb) / seconds, 1), **extra}
    with open(RESULTS_DIR / "timings.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    print(json.dumps(row))


def cmd_sample(args: argparse.Namespace) -> None:
    """Write a seeded sample of abstracts (whole corpus order is deterministic)."""
    with open(args.corpus, encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh]
    random.Random(args.seed).shuffle(rows)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(TEXTS_FILE, "w", encoding="utf-8") as fh:
        for row in rows[:args.n]:
            fh.write(json.dumps({"id": row["_id"], "text": row["text"]}, ensure_ascii=False) + "\n")
    chars = [len(r["text"]) for r in rows[:args.n]]
    print(json.dumps({"written": min(args.n, len(rows)), "median_chars": int(np.median(chars))}))


def cmd_st(args: argparse.Namespace) -> None:
    """sentence-transformers on the best available device."""
    import torch
    from sentence_transformers import SentenceTransformer

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model = SentenceTransformer(HF_MODEL, device=device)
    if args.dtype != "float32":
        model = model.to(getattr(torch, args.dtype))
    texts = load_texts()
    tokens = sum(len(model.tokenizer(t, truncation=True, max_length=model.max_seq_length)["input_ids"])
                 for t in texts)
    model.encode(texts[:64], batch_size=32)  # warm-up (kernel compilation)
    for bs in args.batch_sizes:
        started = time.perf_counter()
        emb = model.encode(texts, batch_size=bs, normalize_embeddings=True, convert_to_numpy=True)
        if device == "mps":
            torch.mps.synchronize()
        seconds = time.perf_counter() - started
        suffix = "" if args.dtype == "float32" else f"_{args.dtype}"
        record(f"st{suffix}_bs{bs}", emb, seconds, {"device": device, "batch": bs, "tokens": tokens,
                                             "tokens_per_s": round(tokens / seconds),
                                             "max_seq_length": model.max_seq_length,
                                             "dtype": str(next(model.parameters()).dtype)})


def cmd_ollama(args: argparse.Namespace) -> None:
    """Ollama through the project's LLM abstraction layer (batch embed)."""
    sys.path.insert(0, str(SPIKE_DIR.parents[1] / "src"))
    from bmlibrarian.llm import LLMClient

    client = LLMClient()
    texts = load_texts()
    client.embed_batch(texts[:8], model=OLLAMA_MODEL, max_batch_size=8)  # warm-up / model load
    started = time.perf_counter()
    resp = client.embed_batch(texts, model=OLLAMA_MODEL, max_batch_size=args.batch)
    seconds = time.perf_counter() - started
    record(f"ollama_bs{args.batch}", np.asarray(resp.embeddings, dtype=np.float32), seconds,
           {"model": OLLAMA_MODEL, "batch": args.batch})


def cmd_compare(args: argparse.Namespace) -> None:
    """Median/min cosine of each backend's 256-d vectors against the reference."""
    ref = np.load(RESULTS_DIR / f"{REFERENCE}.npy")
    for path in sorted(RESULTS_DIR.glob("*.npy")):
        emb = np.load(path)
        if emb.shape != ref.shape:
            print(json.dumps({"backend": path.stem, "error": f"shape {emb.shape} != {ref.shape}"}))
            continue
        cos = (truncate(emb) * ref).sum(axis=1)
        print(json.dumps({"backend": path.stem, "median_cos": round(float(np.median(cos)), 5),
                          "p01_cos": round(float(np.quantile(cos, 0.01)), 5),
                          "min_cos": round(float(cos.min()), 5),
                          "pass": bool(np.median(cos) >= MIN_MEDIAN_COSINE)}))


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point."""
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample")
    s.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    s.add_argument("--n", type=int, default=DEFAULT_SAMPLE)
    s.add_argument("--seed", type=int, default=DEFAULT_SEED)
    s = sub.add_parser("st")
    s.add_argument("--batch-sizes", type=int, nargs="+", default=list(ST_BATCH_SIZES))
    s.add_argument("--dtype", choices=("float32", "float16", "bfloat16"), default="float32")
    s = sub.add_parser("ollama")
    s.add_argument("--batch", type=int, default=OLLAMA_BATCH)
    sub.add_parser("compare")
    args = p.parse_args(argv)
    {"sample": cmd_sample, "st": cmd_st, "ollama": cmd_ollama, "compare": cmd_compare}[args.cmd](args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
