"""
Pure retrieval-evaluation functions for the embedding-dimension benchmark.

Everything here is a side-effect-free numpy function so it can be unit tested
without any model, database or network:

- Matryoshka truncation with re-normalisation (what pgvector storage of a
  shortened vector effectively does).
- Brute-force cosine ranking of a corpus.
- nDCG@k / Recall@k / MRR@k with graded relevance (BEIR / pytrec_eval
  convention: linear gain, log2 discount).
- Paired bootstrap for the difference between two configurations, and a
  non-inferiority verdict against a margin.
"""

import math
from dataclasses import dataclass
from typing import Dict, List, Mapping, Sequence, Tuple

import numpy as np

# Cut-offs reported by the benchmark.
NDCG_CUTOFF = 10
RECALL_CUTOFFS: Tuple[int, ...] = (10, 100)
MRR_CUTOFF = 10

# Documents scored per matrix multiplication; bounds peak memory at
# QUERY_CHUNK_SIZE x n_docs float32 scores.
QUERY_CHUNK_SIZE = 256

# Bootstrap defaults.
DEFAULT_BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_BATCH_SIZE = 500
BOOTSTRAP_CI_LEVEL = 0.95
DEFAULT_RANDOM_SEED = 42

# Default non-inferiority margin: the lower confidence bound of the paired
# nDCG@10 difference must be above -margin (absolute nDCG points, 0.02 = 2).
DEFAULT_NONINFERIORITY_MARGIN = 0.02

# pgvector stores a vector as 4 bytes per float32 component plus an 8-byte header.
PGVECTOR_BYTES_PER_COMPONENT = 4
PGVECTOR_HEADER_BYTES = 8

# Numerical floor to avoid dividing by a zero norm.
NORM_EPSILON = 1e-12

Qrels = Mapping[str, Mapping[str, int]]


def truncate_and_normalize(embeddings: np.ndarray, dim: int) -> np.ndarray:
    """
    Keep the first ``dim`` components of each row and L2-normalise the result.

    This is the Matryoshka-style truncation: the leading components of an MRL
    trained model carry the most information. Re-normalisation is required
    for cosine similarity because slicing a unit vector shortens it.

    Args:
        embeddings: Array of shape (n, native_dim).
        dim: Target dimensionality, 1 <= dim <= native_dim.

    Returns:
        float32 array of shape (n, dim) with unit-length rows (zero rows stay zero).

    Raises:
        ValueError: If embeddings is not 2-D or dim is out of range.
    """
    if embeddings.ndim != 2:
        raise ValueError(f"embeddings must be 2-D, got shape {embeddings.shape}")
    native_dim = embeddings.shape[1]
    if not 1 <= dim <= native_dim:
        raise ValueError(f"dim must be in [1, {native_dim}], got {dim}")
    truncated = embeddings[:, :dim].astype(np.float32, copy=True)
    norms = np.linalg.norm(truncated, axis=1, keepdims=True)
    np.divide(truncated, np.maximum(norms, NORM_EPSILON), out=truncated)
    return truncated


def rank_corpus(
    query_embeddings: np.ndarray,
    doc_embeddings: np.ndarray,
    k: int,
    query_chunk_size: int = QUERY_CHUNK_SIZE,
) -> np.ndarray:
    """
    Return, for every query, the indices of the top-``k`` documents by dot product.

    Inputs are expected to be unit-normalised, making dot product equal to
    cosine similarity. Ties are broken by ascending document index.

    Args:
        query_embeddings: Array (n_queries, dim).
        doc_embeddings: Array (n_docs, dim).
        k: Number of documents to return per query (capped at n_docs).
        query_chunk_size: Queries scored per matrix multiplication.

    Returns:
        int array (n_queries, min(k, n_docs)), best match first.

    Raises:
        ValueError: On dimension mismatch or non-positive k.
    """
    if k < 1:
        raise ValueError(f"k must be >= 1, got {k}")
    if query_embeddings.shape[1] != doc_embeddings.shape[1]:
        raise ValueError(
            f"dimension mismatch: queries {query_embeddings.shape[1]} vs "
            f"documents {doc_embeddings.shape[1]}"
        )
    n_docs = doc_embeddings.shape[0]
    k = min(k, n_docs)
    result = np.empty((query_embeddings.shape[0], k), dtype=np.int64)
    for start in range(0, query_embeddings.shape[0], query_chunk_size):
        chunk = query_embeddings[start:start + query_chunk_size]
        scores = chunk @ doc_embeddings.T
        if k < n_docs:
            candidate = np.argpartition(-scores, k - 1, axis=1)[:, :k]
        else:
            candidate = np.tile(np.arange(n_docs), (scores.shape[0], 1))
        candidate = np.sort(candidate, axis=1)  # index order => stable tie-break
        candidate_scores = np.take_along_axis(scores, candidate, axis=1)
        order = np.argsort(-candidate_scores, axis=1, kind="stable")
        result[start:start + chunk.shape[0]] = np.take_along_axis(candidate, order, axis=1)
    return result


def _dcg(gains: Sequence[float]) -> float:
    """Discounted cumulative gain with linear gain and log2(rank + 1) discount."""
    return sum(gain / math.log2(rank + 2) for rank, gain in enumerate(gains))


@dataclass
class PerQueryMetrics:
    """Per-query metric vectors, aligned with ``query_ids``."""

    query_ids: List[str]
    ndcg: np.ndarray
    recall: Dict[int, np.ndarray]
    mrr: np.ndarray

    def means(self) -> Dict[str, float]:
        """Return the macro-average of every metric as a flat name -> value dict."""
        out = {f"ndcg@{NDCG_CUTOFF}": float(self.ndcg.mean())}
        for cutoff, values in sorted(self.recall.items()):
            out[f"recall@{cutoff}"] = float(values.mean())
        out[f"mrr@{MRR_CUTOFF}"] = float(self.mrr.mean())
        return out


def evaluate_rankings(
    ranked_doc_ids: Sequence[Sequence[str]],
    query_ids: Sequence[str],
    qrels: Qrels,
) -> PerQueryMetrics:
    """
    Compute nDCG@10, Recall@{10,100} and MRR@10 for every query.

    Relevance is graded (qrels value > 0 is relevant, the value is the gain).
    Queries without any relevant document are rejected rather than silently
    scored zero, because that would bias the macro-average.

    Args:
        ranked_doc_ids: For each query, document ids best-first.
        query_ids: Query ids aligned with ``ranked_doc_ids``.
        qrels: query id -> {doc id -> graded relevance}.

    Returns:
        PerQueryMetrics.

    Raises:
        ValueError: On length mismatch or a query without relevant documents.
    """
    if len(ranked_doc_ids) != len(query_ids):
        raise ValueError("ranked_doc_ids and query_ids differ in length")
    ndcg, mrr = [], []
    recall: Dict[int, List[float]] = {c: [] for c in RECALL_CUTOFFS}
    for qid, ranking in zip(query_ids, ranked_doc_ids):
        relevant = {d: g for d, g in qrels.get(qid, {}).items() if g > 0}
        if not relevant:
            raise ValueError(f"query {qid!r} has no relevant documents in qrels")
        gains = [relevant.get(d, 0) for d in ranking[:NDCG_CUTOFF]]
        ideal = sorted(relevant.values(), reverse=True)[:NDCG_CUTOFF]
        ndcg.append(_dcg(gains) / _dcg(ideal))
        for cutoff in RECALL_CUTOFFS:
            hits = sum(1 for d in ranking[:cutoff] if d in relevant)
            recall[cutoff].append(hits / len(relevant))
        rr = 0.0
        for rank, doc_id in enumerate(ranking[:MRR_CUTOFF], start=1):
            if doc_id in relevant:
                rr = 1.0 / rank
                break
        mrr.append(rr)
    return PerQueryMetrics(
        query_ids=list(query_ids),
        ndcg=np.asarray(ndcg, dtype=np.float64),
        recall={c: np.asarray(v, dtype=np.float64) for c, v in recall.items()},
        mrr=np.asarray(mrr, dtype=np.float64),
    )


@dataclass(frozen=True)
class BootstrapResult:
    """Paired bootstrap summary of mean(a - b)."""

    mean_diff: float
    ci_low: float
    ci_high: float
    n_queries: int


def paired_bootstrap(
    a: np.ndarray,
    b: np.ndarray,
    n_resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
    seed: int = DEFAULT_RANDOM_SEED,
    ci_level: float = BOOTSTRAP_CI_LEVEL,
) -> BootstrapResult:
    """
    Percentile bootstrap CI for the mean per-query difference ``a - b``.

    Resampling queries (not documents) with the same indices for both
    configurations preserves the pairing, which is what makes small
    differences detectable.

    Args:
        a: Per-query scores of the candidate.
        b: Per-query scores of the baseline (same query order).
        n_resamples: Number of bootstrap resamples.
        seed: RNG seed for reproducibility.
        ci_level: Confidence level of the interval.

    Returns:
        BootstrapResult.

    Raises:
        ValueError: On shape mismatch, empty input, or invalid parameters.
    """
    if a.shape != b.shape or a.ndim != 1:
        raise ValueError("a and b must be 1-D arrays of equal length")
    if a.size == 0:
        raise ValueError("cannot bootstrap an empty sample")
    if n_resamples < 1 or not 0.0 < ci_level < 1.0:
        raise ValueError("n_resamples must be >= 1 and ci_level in (0, 1)")
    diff = a - b
    rng = np.random.default_rng(seed)
    means = np.empty(n_resamples, dtype=np.float64)
    for start in range(0, n_resamples, BOOTSTRAP_BATCH_SIZE):
        size = min(BOOTSTRAP_BATCH_SIZE, n_resamples - start)
        idx = rng.integers(0, diff.size, size=(size, diff.size))
        means[start:start + size] = diff[idx].mean(axis=1)
    tail = (1.0 - ci_level) / 2.0
    low, high = np.quantile(means, [tail, 1.0 - tail])
    return BootstrapResult(float(diff.mean()), float(low), float(high), int(diff.size))


def noninferiority_verdict(result: BootstrapResult, margin: float) -> str:
    """
    Classify a paired difference (candidate - baseline) against a margin.

    Returns:
        "better" if the CI lies entirely above zero;
        "non-inferior" if the lower bound is above -margin;
        "worse" if the upper bound is below -margin;
        "inconclusive" otherwise (CI straddles the margin: more queries needed).
    """
    if margin < 0:
        raise ValueError("margin must be >= 0")
    if result.ci_low > 0:
        return "better"
    if result.ci_low > -margin:
        return "non-inferior"
    if result.ci_high < -margin:
        return "worse"
    return "inconclusive"


def pgvector_bytes_per_vector(dim: int) -> int:
    """Return the on-disk size of one float32 pgvector value of dimension ``dim``."""
    return PGVECTOR_BYTES_PER_COMPONENT * dim + PGVECTOR_HEADER_BYTES
