#!/usr/bin/env python3
"""
Embedding-dimension benchmark: does a truncated embedding match a larger one?

Embeds each BEIR-format collection once per model at its native dimension,
then evaluates every Matryoshka truncation (e.g. 1024/768/512/256/128) with
nDCG@10, Recall@10/100 and MRR@10, and compares every configuration to a
baseline with a paired bootstrap and a non-inferiority verdict.

Defaults compare the current BMLibrarian model (snowflake-arctic-embed-l-v2.0)
with google/embeddinggemma-2 on two small biomedical collections.

Usage:
    uv run python benchmarks/embedding_dimension/run_benchmark.py
    uv run python benchmarks/embedding_dimension/run_benchmark.py \
        --datasets scifact nfcorpus trec-covid --max-docs 20000 -o results.json
    uv run python benchmarks/embedding_dimension/run_benchmark.py \
        --custom-dataset ~/my_eval_set --baseline arctic@1024

Nothing here touches the BMLibrarian database.
"""

import argparse
import hashlib
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Protocol, Sequence, Tuple

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from beir_data import BeirDataset, download_beir_dataset, load_beir_dataset, subsample_corpus  # noqa: E402
from retrieval_metrics import (  # noqa: E402
    DEFAULT_BOOTSTRAP_RESAMPLES,
    DEFAULT_NONINFERIORITY_MARGIN,
    DEFAULT_RANDOM_SEED,
    RECALL_CUTOFFS,
    BootstrapResult,
    PerQueryMetrics,
    evaluate_rankings,
    noninferiority_verdict,
    paired_bootstrap,
    pgvector_bytes_per_vector,
    rank_corpus,
    truncate_and_normalize,
)

logger = logging.getLogger("embedding_dimension_benchmark")

DEFAULT_MODELS = (
    "arctic=Snowflake/snowflake-arctic-embed-l-v2.0",
    "gemma2=google/embeddinggemma-2",
)
DEFAULT_DATASETS = ("scifact", "nfcorpus")
DEFAULT_DIMS = (1024, 768, 512, 256, 128)
DEFAULT_BATCH_SIZE = 32
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "bmlibrarian" / "embedding_benchmark"
BYTES_PER_MB = 1_000_000
VECTORS_PER_MILLION = 1_000_000
RANKING_DEPTH = max(RECALL_CUTOFFS)
CACHE_KEY_HEX_CHARS = 24
TABLE_SEPARATOR = "-" * 100
# Texts per resumable encoding chunk (see encode_resumable).
ENCODE_CHUNK_SIZE = 4096
PARTIAL_DIR_NAME = "partial"


class Encoder(Protocol):
    """Anything that turns texts into float vectors; injectable for testing."""

    native_dim: int

    def encode(self, texts: Sequence[str], role: str) -> np.ndarray:
        """Embed ``texts`` for ``role`` ("query" or "document") -> (n, native_dim)."""

    def describe_prompt(self, role: str) -> str:
        """Human-readable prompt applied for ``role`` (for the audit trail)."""


@dataclass(frozen=True)
class ModelSpec:
    """A model to benchmark: short label plus HuggingFace id."""

    label: str
    model_id: str


@dataclass
class ConfigResult:
    """Metrics of one (dataset, model, dimension) configuration."""

    dataset: str
    label: str
    dim: int
    metrics: Dict[str, float]
    per_query: PerQueryMetrics = field(repr=False)
    vs_baseline: Optional[BootstrapResult] = None
    verdict: str = ""


def parse_model_specs(values: Sequence[str]) -> List[ModelSpec]:
    """
    Parse ``label=hf_id`` strings.

    Raises:
        ValueError: On a malformed or duplicated label.
    """
    specs: List[ModelSpec] = []
    for value in values:
        label, sep, model_id = value.partition("=")
        label, model_id = label.strip(), model_id.strip()
        if not sep or not label or not model_id or "@" in label:
            raise ValueError(f"--model must look like label=org/model, got {value!r}")
        if any(s.label == label for s in specs):
            raise ValueError(f"duplicate model label {label!r}")
        specs.append(ModelSpec(label, model_id))
    return specs


def parse_label_map(values: Sequence[str]) -> Dict[str, str]:
    """Parse repeated ``label=text`` options (used for prompt prefixes)."""
    out: Dict[str, str] = {}
    for value in values:
        label, sep, text = value.partition("=")
        if not sep or not label.strip():
            raise ValueError(f"expected label=text, got {value!r}")
        out[label.strip()] = text
    return out


def parse_config_ref(ref: str) -> Tuple[str, Optional[int]]:
    """Parse ``label@dim`` (dim optional) used by --baseline."""
    label, sep, dim = ref.partition("@")
    if not label:
        raise ValueError(f"invalid baseline {ref!r}")
    if not sep:
        return label, None
    try:
        return label, int(dim)
    except ValueError as exc:
        raise ValueError(f"invalid baseline dimension in {ref!r}") from exc


def resolve_prompt(
    available: Dict[str, str],
    role: str,
    explicit_prefix: Optional[str],
    disabled: bool,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Decide which prompt to apply for ``role``.

    Priority: disabled > explicit prefix > a model-defined prompt called
    ``role`` (non-empty) > nothing. Returns (prompt_name, prompt_text); at most one is set.
    """
    if disabled:
        return None, None
    if explicit_prefix is not None:
        return None, explicit_prefix
    if available.get(role):
        return role, None
    return None, None


class SentenceTransformerEncoder:
    """sentence-transformers backed encoder with model-defined or explicit prompts."""

    def __init__(
        self,
        spec: ModelSpec,
        device: Optional[str],
        batch_size: int,
        max_seq_length: Optional[int],
        trust_remote_code: bool,
        query_prefix: Optional[str],
        document_prefix: Optional[str],
        no_prompts: bool,
    ) -> None:
        """Load the model and resolve the query/document prompts."""
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(
            spec.model_id, device=device, trust_remote_code=trust_remote_code
        )
        if max_seq_length is not None:
            self.model.max_seq_length = max_seq_length
        self.batch_size = batch_size
        # Renamed in recent sentence-transformers; support both spellings.
        dim_getter = getattr(self.model, "get_embedding_dimension", None) \
            or self.model.get_sentence_embedding_dimension
        self.native_dim = int(dim_getter())
        available = dict(getattr(self.model, "prompts", {}) or {})
        self._prompts = {
            "query": resolve_prompt(available, "query", query_prefix, no_prompts),
            "document": resolve_prompt(available, "document", document_prefix, no_prompts),
        }
        self._available = available

    def encode(self, texts: Sequence[str], role: str) -> np.ndarray:
        """Embed ``texts`` for ``role``; returns float32 (n, native_dim)."""
        name, text = self._prompts[role]
        kwargs = {}
        if name is not None:
            kwargs["prompt_name"] = name
        elif text is not None:
            kwargs["prompt"] = text
        out = self.model.encode(
            list(texts),
            batch_size=self.batch_size,
            convert_to_numpy=True,
            normalize_embeddings=False,
            show_progress_bar=True,
            **kwargs,
        )
        return np.asarray(out, dtype=np.float32)

    def release_memory(self) -> None:
        """Return cached accelerator memory to the OS between encoding chunks."""
        import torch

        if torch.backends.mps.is_available():
            torch.mps.empty_cache()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def describe_prompt(self, role: str) -> str:
        """Describe the prompt in use so results are auditable."""
        name, text = self._prompts[role]
        if name is not None:
            return f"model prompt '{name}': {self._available[name]!r}"
        if text is not None:
            return f"explicit prefix: {text!r}"
        return "none"


def cache_path(cache_dir: Path, model_id: str, dataset: str, role: str, prompt: str,
               max_seq_length: Optional[int], texts: Sequence[str]) -> Path:
    """Return the .npy cache file for one embedding job (content-addressed)."""
    digest = hashlib.sha256()
    for part in (model_id, dataset, role, prompt, str(max_seq_length)):
        digest.update(part.encode("utf-8"))
        digest.update(b"\x00")
    for text in texts:
        digest.update(text.encode("utf-8"))
        digest.update(b"\x00")
    return cache_dir / "embeddings" / f"{digest.hexdigest()[:CACHE_KEY_HEX_CHARS]}.npy"


def partial_path(final_path: Path, chunk_index: int) -> Path:
    """Location of one saved chunk of an in-progress embedding job."""
    return final_path.parent / PARTIAL_DIR_NAME / f"{final_path.stem}_{chunk_index:05d}.npy"


def encode_resumable(encoder: Encoder, texts: Sequence[str], role: str, final_path: Path,
                     chunk_size: int = ENCODE_CHUNK_SIZE) -> np.ndarray:
    """
    Encode ``texts`` in chunks, saving each chunk so a killed run resumes.

    Large corpora take tens of minutes per model, and the OS can kill the process
    (e.g. accelerator memory pressure). Finished chunks are kept next to the final
    cache file and reused; ``remove_partials`` deletes them once the result is cached.
    Accelerator memory is released between chunks when the encoder supports it.
    """
    if len(texts) <= chunk_size:
        return encoder.encode(texts, role)
    parts: List[np.ndarray] = []
    starts = range(0, len(texts), chunk_size)
    for index, start in enumerate(starts):
        chunk_texts = texts[start:start + chunk_size]
        path = partial_path(final_path, index)
        chunk: Optional[np.ndarray] = None
        if path.exists():
            try:
                chunk = np.load(path)
                if chunk.shape != (len(chunk_texts), encoder.native_dim):
                    chunk = None
            except (OSError, ValueError) as exc:
                logger.warning("ignoring unreadable partial %s: %s", path, exc)
                chunk = None
        if chunk is None:
            logger.info("encoding %s chunk %d/%d", role, index + 1, len(starts))
            chunk = np.asarray(encoder.encode(chunk_texts, role), dtype=np.float32)
            if chunk.shape == (len(chunk_texts), encoder.native_dim) and np.isfinite(chunk).all():
                path.parent.mkdir(parents=True, exist_ok=True)
                np.save(path, chunk)
            release = getattr(encoder, "release_memory", None)
            if callable(release):
                release()
        else:
            logger.info("resumed %s chunk %d/%d from disk", role, index + 1, len(starts))
        parts.append(chunk)
    return np.concatenate(parts, axis=0)


def remove_partials(final_path: Path) -> None:
    """Delete the saved chunks of a job whose full result is now cached."""
    for path in (final_path.parent / PARTIAL_DIR_NAME).glob(f"{final_path.stem}_*.npy"):
        path.unlink(missing_ok=True)


def embed_cached(
    encoder: Encoder,
    spec: ModelSpec,
    dataset: str,
    role: str,
    texts: Sequence[str],
    cache_dir: Path,
    max_seq_length: Optional[int],
) -> Tuple[np.ndarray, float]:
    """
    Embed ``texts`` with an on-disk cache so reruns and new dimensions are free.

    Returns:
        (embeddings, seconds spent encoding; 0.0 if loaded from cache).
    """
    path = cache_path(cache_dir, spec.model_id, dataset, role,
                      encoder.describe_prompt(role), max_seq_length, texts)
    if path.exists():
        try:
            cached = np.load(path)
            if cached.shape == (len(texts), encoder.native_dim):
                logger.info("cache hit: %s %s %s", spec.label, dataset, role)
                return cached, 0.0
            logger.warning("ignoring cache with unexpected shape %s", cached.shape)
        except (OSError, ValueError) as exc:
            logger.warning("ignoring unreadable cache %s: %s", path, exc)
    started = time.perf_counter()
    embeddings = encode_resumable(encoder, texts, role, path)
    elapsed = time.perf_counter() - started
    if embeddings.shape != (len(texts), encoder.native_dim):
        raise ValueError(f"encoder returned shape {embeddings.shape}, expected "
                         f"{(len(texts), encoder.native_dim)}")
    if not np.isfinite(embeddings).all():
        raise ValueError(f"{spec.label} produced non-finite embeddings")
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, embeddings)
    remove_partials(path)
    return embeddings, elapsed


def evaluate_dimensions(
    dataset: BeirDataset,
    label: str,
    query_emb: np.ndarray,
    doc_emb: np.ndarray,
    dims: Sequence[int],
) -> List[ConfigResult]:
    """
    Evaluate each requested truncation of one model on one dataset.

    Dimensions above the native size are skipped; the native size is always
    included so the untruncated model is the reference point.
    """
    native = doc_emb.shape[1]
    wanted = sorted({d for d in dims if 1 <= d <= native} | {native}, reverse=True)
    query_ids = list(dataset.queries)
    doc_ids = list(dataset.corpus)
    results: List[ConfigResult] = []
    for dim in wanted:
        q = truncate_and_normalize(query_emb, dim)
        d = truncate_and_normalize(doc_emb, dim)
        top = rank_corpus(q, d, RANKING_DEPTH)
        ranked = [[doc_ids[i] for i in row] for row in top]
        per_query = evaluate_rankings(ranked, query_ids, dataset.qrels)
        results.append(ConfigResult(dataset.name, label, dim, per_query.means(), per_query))
    return results


def attach_comparisons(
    results: List[ConfigResult],
    baseline: Tuple[str, Optional[int]],
    resamples: int,
    margin: float,
    seed: int,
) -> None:
    """Fill ``vs_baseline``/``verdict`` for every result of a single dataset, in place."""
    label, dim = baseline
    candidates = [r for r in results if r.label == label and (dim is None or r.dim == dim)]
    if not candidates:
        logger.warning("baseline %s@%s not evaluated on %s; no comparison",
                       label, dim, results[0].dataset if results else "?")
        return
    base = max(candidates, key=lambda r: r.dim)
    for r in results:
        if r is base:
            r.verdict = "baseline"
            continue
        r.vs_baseline = paired_bootstrap(r.per_query.ndcg, base.per_query.ndcg, resamples, seed)
        r.verdict = noninferiority_verdict(r.vs_baseline, margin)


def format_table(dataset: str, results: Sequence[ConfigResult], n_queries: int, n_docs: int) -> str:
    """Render one dataset's results as a fixed-width text table."""
    lines = [
        TABLE_SEPARATOR,
        f"{dataset}  ({n_queries} queries, {n_docs} documents)",
        f"{'config':<14}{'nDCG@10':>9}{'R@10':>8}{'R@100':>8}{'MRR@10':>8}"
        f"{'MB/1M vec':>11}  {'Δ nDCG@10 vs baseline [95% CI]':<34}verdict",
    ]
    for r in sorted(results, key=lambda x: (x.label, -x.dim)):
        m = r.metrics
        delta = ""
        if r.vs_baseline is not None:
            b = r.vs_baseline
            delta = f"{b.mean_diff:+.4f} [{b.ci_low:+.4f}, {b.ci_high:+.4f}]"
        size_mb = pgvector_bytes_per_vector(r.dim) * VECTORS_PER_MILLION / BYTES_PER_MB
        lines.append(
            f"{r.label + '@' + str(r.dim):<14}{m['ndcg@10']:>9.4f}{m['recall@10']:>8.4f}"
            f"{m['recall@100']:>8.4f}{m['mrr@10']:>8.4f}{size_mb:>11.0f}  {delta:<34}{r.verdict}"
        )
    return "\n".join(lines)


def macro_average(all_results: Dict[str, List[ConfigResult]]) -> Dict[str, Dict[int, float]]:
    """Mean nDCG@10 across datasets per (label, dim); only configs present everywhere."""
    pooled: Dict[Tuple[str, int], List[float]] = {}
    for results in all_results.values():
        for r in results:
            pooled.setdefault((r.label, r.dim), []).append(r.metrics["ndcg@10"])
    n_datasets = len(all_results)
    out: Dict[str, Dict[int, float]] = {}
    for (label, dim), values in pooled.items():
        if len(values) == n_datasets:
            out.setdefault(label, {})[dim] = float(np.mean(values))
    return out


def load_datasets(args: argparse.Namespace) -> List[BeirDataset]:
    """Load named BEIR datasets and custom directories, applying sub-sampling."""
    datasets: List[BeirDataset] = []
    for name in args.datasets:
        path = download_beir_dataset(name, args.cache_dir / "datasets")
        datasets.append(load_beir_dataset(path, name=name))
    for custom in args.custom_dataset:
        path = Path(custom).expanduser()
        datasets.append(load_beir_dataset(path, name=f"custom:{path.name}"))
    if args.max_docs:
        datasets = [subsample_corpus(d, args.max_docs, args.seed) for d in datasets]
    for d in datasets:
        for note in d.notes:
            logger.info("%s: %s", d.name, note)
    return datasets


def run(
    args: argparse.Namespace,
    encoder_factory: Callable[[ModelSpec, argparse.Namespace], Encoder],
) -> dict:
    """
    Execute the benchmark and return a JSON-serialisable result document.

    Args:
        args: Parsed CLI arguments.
        encoder_factory: Builds an Encoder for a ModelSpec (injectable for tests).
    """
    specs = parse_model_specs(args.model)
    prefixes = {
        "query": parse_label_map(args.query_prefix),
        "document": parse_label_map(args.document_prefix),
    }
    args.prefix_maps = prefixes
    baseline = parse_config_ref(args.baseline or specs[0].label)
    datasets = load_datasets(args)

    all_results: Dict[str, List[ConfigResult]] = {d.name: [] for d in datasets}
    timings: Dict[str, Dict[str, float]] = {}
    prompts: Dict[str, Dict[str, str]] = {}
    failures: List[str] = []

    for spec in specs:
        try:
            encoder = encoder_factory(spec, args)
        except Exception as exc:  # model load can fail in many library-specific ways
            logger.error("could not load %s (%s): %s", spec.label, spec.model_id, exc)
            failures.append(spec.label)
            continue
        prompts[spec.label] = {r: encoder.describe_prompt(r) for r in ("query", "document")}
        logger.info("%s native dim %d, prompts: %s", spec.label, encoder.native_dim, prompts[spec.label])
        for ds in datasets:
            doc_texts = list(ds.corpus.values())
            query_texts = list(ds.queries.values())
            doc_emb, doc_time = embed_cached(encoder, spec, ds.name, "document", doc_texts,
                                             args.cache_dir, args.max_seq_length)
            query_emb, query_time = embed_cached(encoder, spec, ds.name, "query", query_texts,
                                                 args.cache_dir, args.max_seq_length)
            timings.setdefault(spec.label, {})[ds.name] = doc_time
            all_results[ds.name].extend(
                evaluate_dimensions(ds, spec.label, query_emb, doc_emb, args.dims))
            logger.info("%s on %s: %d docs in %.1fs, %d queries in %.1fs", spec.label, ds.name,
                        len(doc_texts), doc_time, len(query_texts), query_time)
        del encoder

    report_lines: List[str] = []
    for ds in datasets:
        results = all_results[ds.name]
        if not results:
            continue
        attach_comparisons(results, baseline, args.bootstrap_resamples, args.margin, args.seed)
        report_lines.append(format_table(ds.name, results, len(ds.queries), len(ds.corpus)))
    macro = macro_average({k: v for k, v in all_results.items() if v})

    print("\n".join(report_lines))
    print(TABLE_SEPARATOR)
    print("Macro-average nDCG@10 across datasets:")
    for label, by_dim in macro.items():
        print("  " + label + ": " + "  ".join(f"{d}d={v:.4f}" for d, v in sorted(by_dim.items(), reverse=True)))
    print(f"\nVerdicts: paired bootstrap ({args.bootstrap_resamples} resamples) of nDCG@10 vs "
          f"{baseline[0]}@{baseline[1] or 'native'}; non-inferior = lower 95% bound > -{args.margin}.")
    for label, p in prompts.items():
        print(f"Prompts {label}: query={p['query']}; document={p['document']}")
    if failures:
        print(f"FAILED TO LOAD: {', '.join(failures)}")

    return {
        "config": {
            "models": [vars(s) for s in specs],
            "datasets": [d.name for d in datasets],
            "dims": list(args.dims),
            "baseline": f"{baseline[0]}@{baseline[1] or 'native'}",
            "margin": args.margin,
            "bootstrap_resamples": args.bootstrap_resamples,
            "seed": args.seed,
            "max_docs": args.max_docs,
            "max_seq_length": args.max_seq_length,
        },
        "prompts": prompts,
        "document_encode_seconds": timings,
        "failures": failures,
        "results": [
            {
                "dataset": r.dataset, "model": r.label, "dim": r.dim, "metrics": r.metrics,
                "delta_ndcg10": None if r.vs_baseline is None else {
                    "mean": r.vs_baseline.mean_diff, "ci_low": r.vs_baseline.ci_low,
                    "ci_high": r.vs_baseline.ci_high, "n_queries": r.vs_baseline.n_queries},
                "verdict": r.verdict,
            }
            for results in all_results.values() for r in results
        ],
        "macro_ndcg10": {k: {str(d): v for d, v in by.items()} for k, by in macro.items()},
    }


def build_arg_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", action="append", default=None, metavar="LABEL=HF_ID",
                   help="model to benchmark (repeatable); default: arctic + gemma2")
    p.add_argument("--datasets", nargs="*", default=list(DEFAULT_DATASETS),
                   help="BEIR dataset names to download (e.g. scifact nfcorpus trec-covid)")
    p.add_argument("--custom-dataset", action="append", default=[], metavar="DIR",
                   help="BEIR-format directory of your own evaluation set (repeatable)")
    p.add_argument("--dims", nargs="+", type=int, default=list(DEFAULT_DIMS),
                   help="truncation dimensions to evaluate")
    p.add_argument("--baseline", default=None, metavar="LABEL[@DIM]",
                   help="comparison reference (default: first model at native dimension)")
    p.add_argument("--margin", type=float, default=DEFAULT_NONINFERIORITY_MARGIN,
                   help="non-inferiority margin in absolute nDCG@10")
    p.add_argument("--bootstrap-resamples", type=int, default=DEFAULT_BOOTSTRAP_RESAMPLES)
    p.add_argument("--max-docs", type=int, default=0,
                   help="subsample corpora above this size (0 = use everything)")
    p.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    p.add_argument("--max-seq-length", type=int, default=None,
                   help="override the model's max sequence length (same for all models)")
    p.add_argument("--device", default=None, help="cpu, cuda, mps (default: auto)")
    p.add_argument("--trust-remote-code", action="store_true",
                   help="allow model repos to run custom code (off by default)")
    p.add_argument("--query-prefix", action="append", default=[], metavar="LABEL=TEXT",
                   help="explicit query prompt for a model, overriding its built-in prompt")
    p.add_argument("--document-prefix", action="append", default=[], metavar="LABEL=TEXT",
                   help="explicit document prompt for a model")
    p.add_argument("--no-prompts", action="store_true", help="disable all prompts (not recommended)")
    p.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    p.add_argument("--seed", type=int, default=DEFAULT_RANDOM_SEED)
    p.add_argument("-o", "--output", type=Path, default=None, help="write full results as JSON")
    return p


def make_sentence_transformer_encoder(spec: ModelSpec, args: argparse.Namespace) -> Encoder:
    """Default encoder factory used by the CLI."""
    return SentenceTransformerEncoder(
        spec, args.device, args.batch_size, args.max_seq_length, args.trust_remote_code,
        args.prefix_maps["query"].get(spec.label), args.prefix_maps["document"].get(spec.label),
        args.no_prompts,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point. Returns a process exit code."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = build_arg_parser().parse_args(argv)
    args.model = args.model or list(DEFAULT_MODELS)
    try:
        document = run(args, make_sentence_transformer_encoder)
    except (ValueError, OSError) as exc:
        logger.error("benchmark aborted: %s", exc)
        return 2
    if args.output:
        args.output.write_text(json.dumps(document, indent=2), encoding="utf-8")
        logger.info("wrote %s", args.output)
    return 1 if document["failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
