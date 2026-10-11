"""
BEIR-format dataset download, loading and sub-sampling.

A dataset directory contains::

    corpus.jsonl        {"_id": ..., "title": ..., "text": ...} per line
    queries.jsonl       {"_id": ..., "text": ...} per line
    qrels/<split>.tsv   header "query-id<TAB>corpus-id<TAB>score", then rows

The same layout is used for in-house evaluation sets, so a custom directory
can be passed straight to the benchmark.

All file and network content is treated as untrusted: names are validated,
archive members are checked against path traversal, and malformed lines are
counted and skipped rather than trusted.
"""

import csv
import json
import logging
import random
import re
import shutil
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)

BEIR_BASE_URL = "https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets"
DOWNLOAD_TIMEOUT_SECONDS = 120
DOWNLOAD_CHUNK_BYTES = 1 << 20
DATASET_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9\-]{0,63}$")

CORPUS_FILE = "corpus.jsonl"
QUERIES_FILE = "queries.jsonl"
QRELS_DIR = "qrels"
DEFAULT_SPLIT = "test"
QRELS_HEADER = ("query-id", "corpus-id", "score")


@dataclass
class BeirDataset:
    """An information-retrieval test collection."""

    name: str
    corpus: Dict[str, str]
    queries: Dict[str, str]
    qrels: Dict[str, Dict[str, int]]
    skipped_lines: int = 0
    notes: List[str] = field(default_factory=list)


def validate_dataset_name(name: str) -> str:
    """
    Validate a BEIR dataset name before it is used in a URL or path.

    Raises:
        ValueError: If the name contains anything but lowercase letters,
            digits and hyphens.
    """
    if not DATASET_NAME_PATTERN.match(name):
        raise ValueError(f"invalid dataset name: {name!r}")
    return name


def extract_zip_safely(archive: Path, destination: Path) -> None:
    """
    Extract ``archive`` into ``destination``, rejecting path-traversal members.

    Raises:
        ValueError: If any member would be written outside ``destination``.
    """
    destination = destination.resolve()
    with zipfile.ZipFile(archive) as zf:
        for member in zf.namelist():
            target = (destination / member).resolve()
            if destination != target and destination not in target.parents:
                raise ValueError(f"unsafe path in archive: {member!r}")
        zf.extractall(destination)


def download_beir_dataset(name: str, cache_dir: Path) -> Path:
    """
    Download (once) and unpack a BEIR dataset, returning its directory.

    Args:
        name: BEIR dataset name, e.g. "scifact".
        cache_dir: Directory under which datasets are stored.

    Returns:
        Path of the unpacked dataset directory.

    Raises:
        ValueError: On an invalid name or unsafe archive.
        OSError / urllib.error.URLError: On download failure.
    """
    validate_dataset_name(name)
    dataset_dir = cache_dir / name
    if (dataset_dir / CORPUS_FILE).exists():
        return dataset_dir
    cache_dir.mkdir(parents=True, exist_ok=True)
    archive = cache_dir / f"{name}.zip"
    url = f"{BEIR_BASE_URL}/{name}.zip"
    logger.info("Downloading %s", url)
    partial = archive.with_suffix(".zip.part")
    try:
        with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT_SECONDS) as resp, \
                open(partial, "wb") as out:
            shutil.copyfileobj(resp, out, DOWNLOAD_CHUNK_BYTES)
        partial.replace(archive)
        extract_zip_safely(archive, cache_dir)
    finally:
        partial.unlink(missing_ok=True)
    if not (dataset_dir / CORPUS_FILE).exists():
        raise ValueError(f"archive for {name!r} did not contain {name}/{CORPUS_FILE}")
    return dataset_dir


def _read_jsonl(path: Path) -> "tuple[List[dict], int]":
    """Read a JSONL file, returning (valid dict rows, number of skipped lines)."""
    rows: List[dict] = []
    skipped = 0
    with open(path, encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("%s:%d: invalid JSON, skipped", path.name, line_no)
                skipped += 1
                continue
            if not isinstance(row, dict) or "_id" not in row or not isinstance(row.get("text"), str):
                logger.warning("%s:%d: missing _id/text, skipped", path.name, line_no)
                skipped += 1
                continue
            rows.append(row)
    return rows, skipped


def load_beir_dataset(path: Path, split: str = DEFAULT_SPLIT, name: str = "") -> BeirDataset:
    """
    Load a BEIR-format directory.

    Document text is ``title + " " + text`` (BEIR convention) when a title exists.
    Queries without qrels, and qrels pointing at unknown documents, are dropped
    and counted in ``notes``.

    Raises:
        FileNotFoundError: If a required file is missing.
        ValueError: If the dataset ends up with no usable queries.
    """
    corpus_rows, skipped_c = _read_jsonl(path / CORPUS_FILE)
    query_rows, skipped_q = _read_jsonl(path / QUERIES_FILE)
    corpus = {
        str(r["_id"]): " ".join(filter(None, [str(r.get("title") or "").strip(), r["text"].strip()]))
        for r in corpus_rows
    }
    queries = {str(r["_id"]): r["text"].strip() for r in query_rows}

    qrels: Dict[str, Dict[str, int]] = {}
    dropped = 0
    with open(path / QRELS_DIR / f"{split}.tsv", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh, delimiter="\t")
        header = next(reader, None)
        if header is None or tuple(h.strip() for h in header[:3]) != QRELS_HEADER:
            raise ValueError(f"unexpected qrels header: {header!r}")
        for row in reader:
            if len(row) < 3:
                dropped += 1
                continue
            qid, did, score = row[0].strip(), row[1].strip(), row[2].strip()
            try:
                gain = int(float(score))
            except ValueError:
                dropped += 1
                continue
            if gain <= 0 or qid not in queries or did not in corpus:
                dropped += 1
                continue
            qrels.setdefault(qid, {})[did] = gain

    queries = {q: t for q, t in queries.items() if q in qrels and t}
    qrels = {q: r for q, r in qrels.items() if q in queries}
    if not queries:
        raise ValueError(f"no usable queries in {path}")
    notes = [f"{dropped} qrels rows dropped (non-positive, unknown id or malformed)"] if dropped else []
    return BeirDataset(
        name=name or path.name,
        corpus=corpus,
        queries=queries,
        qrels=qrels,
        skipped_lines=skipped_c + skipped_q,
        notes=notes,
    )


def subsample_corpus(dataset: BeirDataset, max_docs: int, seed: int) -> BeirDataset:
    """
    Reduce the corpus to at most ``max_docs`` documents, keeping every relevant one.

    All documents with a positive judgement are retained (so recall stays
    measurable) and the remainder is filled with a seeded random sample of
    non-relevant documents. Absolute scores on a subsampled corpus are
    inflated relative to the full corpus, but the comparison between
    embedding configurations stays like-for-like.

    Raises:
        ValueError: If max_docs < 1.
    """
    if max_docs < 1:
        raise ValueError("max_docs must be >= 1")
    if len(dataset.corpus) <= max_docs:
        return dataset
    relevant = {d for judged in dataset.qrels.values() for d in judged}
    others = sorted(set(dataset.corpus) - relevant)
    rng = random.Random(seed)
    room = max(max_docs - len(relevant), 0)
    keep = relevant | set(rng.sample(others, min(room, len(others))))
    note = f"corpus subsampled to {len(keep)} of {len(dataset.corpus)} documents (seed {seed})"
    if len(relevant) > max_docs:
        note += f"; max_docs raised to {len(relevant)} to keep all relevant documents"
    return BeirDataset(
        name=dataset.name,
        corpus={d: dataset.corpus[d] for d in sorted(keep)},
        queries=dataset.queries,
        qrels=dataset.qrels,
        skipped_lines=dataset.skipped_lines,
        notes=dataset.notes + [note],
    )
