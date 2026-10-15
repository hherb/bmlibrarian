#!/usr/bin/env python3
"""
Build BMLibrarian-specific evaluation sets for the embedding-dimension benchmark.

Reads (read-only) relevance judgements that BMLibrarian already holds and writes
BEIR-format directories that ``run_benchmark.py --custom-dataset`` accepts:

- ``pubmedqa_source/eval``: the 1000 PubMedQA questions from the fact-checker
  (``factcheck.statements``). Relevant = the paper each question was written
  from (``input_statement_id`` is its PMID). Human-sourced and model-neutral.
- ``pubmedqa_graded/eval``: same queries; source paper = grade 2, plus the
  fact-checker's evidence documents graded by their LLM relevance score
  (5 -> 2, 4 -> 1; 3 and below ignored).
- ``research_questions/eval``: real research questions typed into BMLibrarian
  (``audit.research_questions``) with the scoring agent's 0-5 relevance scores
  (``audit.document_scores``); score 3/4/5 -> grade 1/2/3. Near-duplicate
  questions are merged.

All three share one corpus, so document embeddings are computed once. Every
directory is named ``eval`` because run_benchmark.py keys its embedding cache
on the directory name; identical names plus an identical corpus mean cache hits.
The corpus is every judged document plus a seeded random sample of PubMed
abstracts as distractors. Documents are **abstract only, no title**: PubMedQA
questions are usually their source paper's title verbatim, which would turn
retrieval into string matching.

Usage:
    uv run python benchmarks/embedding_dimension/build_bmlibrarian_eval.py
    uv run python benchmarks/embedding_dimension/build_bmlibrarian_eval.py \
        --distractors 50000 --output-dir ~/bmlib_eval
"""

import argparse
import csv
import difflib
import json
import logging
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

logger = logging.getLogger("build_bmlibrarian_eval")

DEFAULT_OUTPUT_DIR = Path.home() / ".cache" / "bmlibrarian" / "embedding_benchmark" / "bmlibrarian_eval"
DEFAULT_DISTRACTORS = 30_000
DEFAULT_SEED = 42
# Percent of the document table to sample per TABLESAMPLE round; resampled with
# a new seed until enough distractors are collected.
SAMPLE_PERCENT = 0.15
MAX_SAMPLE_ROUNDS = 20
MIN_ABSTRACT_CHARS = 200
PUBMED_SOURCE_NAME = "pubmed"
CACHE_SAFE_DIR_NAME = "eval"

SOURCE_PAPER_GRADE = 2
# LLM relevance score (1-5) -> graded relevance; unlisted scores are ignored.
EVIDENCE_GRADES: Mapping[int, int] = {5: 2, 4: 1}
RESEARCH_GRADES: Mapping[int, int] = {5: 3, 4: 2, 3: 1}
DUPLICATE_QUESTION_RATIO = 0.93

QRELS_HEADER = ("query-id", "corpus-id", "score")
MARKDOWN_EMPHASIS = re.compile(r"(\*\*|__|`)")
WHITESPACE = re.compile(r"\s+")
NON_ALNUM = re.compile(r"[^a-z0-9 ]+")

Qrels = Dict[str, Dict[str, int]]


@dataclass
class EvalSet:
    """One BEIR-format evaluation set (queries + qrels; corpus is shared)."""

    name: str
    queries: Dict[str, str]
    qrels: Qrels
    notes: List[str] = field(default_factory=list)


# --------------------------------------------------------------------------- pure functions

def clean_abstract(text: Optional[str]) -> str:
    """Strip Markdown emphasis markers and collapse whitespace in an abstract."""
    if not text:
        return ""
    return WHITESPACE.sub(" ", MARKDOWN_EMPHASIS.sub("", text)).strip()


def add_qrel(qrels: Qrels, query_id: str, doc_id: str, grade: int) -> None:
    """Record ``grade`` for (query, doc), keeping the highest grade seen."""
    if grade <= 0:
        return
    row = qrels.setdefault(query_id, {})
    row[doc_id] = max(grade, row.get(doc_id, 0))


def grade_from_score(score: Optional[float], mapping: Mapping[int, int]) -> int:
    """Map an LLM relevance score to a qrels grade (0 = not relevant / unknown)."""
    if score is None:
        return 0
    try:
        return mapping.get(int(round(float(score))), 0)
    except (TypeError, ValueError):
        return 0


def build_pubmedqa_sets(
    statements: Sequence[Tuple[str, str, Optional[str]]],
    evidence: Iterable[Tuple[str, str, Optional[float]]],
) -> Tuple[EvalSet, EvalSet]:
    """
    Build the source-only and graded PubMedQA evaluation sets.

    Args:
        statements: (query_id, question, source_doc_id or None if not in the DB).
        evidence: (query_id, doc_id, llm_relevance_score) from the fact-checker.

    Returns:
        (pubmedqa_source, pubmedqa_graded). Queries without a source document
        are dropped from both, so the two sets contain the same queries.
    """
    queries: Dict[str, str] = {}
    source: Qrels = {}
    graded: Qrels = {}
    missing = 0
    for qid, question, doc_id in statements:
        if not doc_id or not (question or "").strip():
            missing += 1
            continue
        queries[qid] = question.strip()
        add_qrel(source, qid, doc_id, 1)
        add_qrel(graded, qid, doc_id, SOURCE_PAPER_GRADE)
    added = 0
    for qid, doc_id, score in evidence:
        if qid not in queries:
            continue
        grade = grade_from_score(score, EVIDENCE_GRADES)
        if grade:
            before = graded[qid].get(doc_id, 0)
            add_qrel(graded, qid, doc_id, grade)
            added += int(before == 0)
    notes = [f"{missing} statements skipped (no source document in the database)"] if missing else []
    return (
        EvalSet("pubmedqa_source", dict(queries), source, list(notes)),
        EvalSet("pubmedqa_graded", dict(queries), graded,
                notes + [f"{added} evidence judgements added from factcheck.evidence"]),
    )


def normalize_question(text: str) -> str:
    """Lower-case and strip punctuation, for near-duplicate detection."""
    return WHITESPACE.sub(" ", NON_ALNUM.sub(" ", text.lower())).strip()


def merge_near_duplicates(
    questions: Mapping[str, str], ratio: float = DUPLICATE_QUESTION_RATIO
) -> Dict[str, str]:
    """
    Map each question id to a canonical id, merging near-identical questions.

    The earliest id (in iteration order) of a group of questions whose
    normalised texts reach ``ratio`` similarity becomes the canonical id.
    """
    canonical: Dict[str, str] = {}
    kept: List[Tuple[str, str]] = []
    for qid, text in questions.items():
        norm = normalize_question(text)
        match = next((cid for cid, ctext in kept
                      if difflib.SequenceMatcher(None, norm, ctext).ratio() >= ratio), None)
        if match is None:
            kept.append((qid, norm))
            canonical[qid] = qid
        else:
            canonical[qid] = match
    return canonical


def build_research_set(
    questions: Mapping[str, str],
    scores: Iterable[Tuple[str, str, Optional[float]]],
) -> EvalSet:
    """
    Build the research-question set from scoring-agent judgements.

    Args:
        questions: question_id -> question text.
        scores: (question_id, doc_id, relevance_score 0-5).

    Returns:
        EvalSet keeping only questions with at least one relevant document.
    """
    canonical = merge_near_duplicates(questions)
    qrels: Qrels = {}
    judged: Dict[str, Set[str]] = defaultdict(set)
    for qid, doc_id, score in scores:
        cid = canonical.get(qid)
        if cid is None:
            continue
        judged[cid].add(doc_id)
        add_qrel(qrels, cid, doc_id, grade_from_score(score, RESEARCH_GRADES))
    queries = {cid: questions[cid].strip() for cid in qrels}
    merged = sum(1 for qid, cid in canonical.items() if qid != cid)
    no_relevant = sum(1 for cid in judged if cid not in qrels)
    notes = [f"{merged} near-duplicate questions merged",
             f"{no_relevant} questions dropped (no document scored >= 3)"]
    return EvalSet("research_questions", queries, qrels, notes)


def write_beir_dir(path: Path, corpus: Mapping[str, str], eval_set: EvalSet) -> None:
    """Write corpus.jsonl, queries.jsonl and qrels/test.tsv (BEIR layout) to ``path``."""
    (path / "qrels").mkdir(parents=True, exist_ok=True)
    with open(path / "corpus.jsonl", "w", encoding="utf-8") as fh:
        for doc_id, text in corpus.items():
            fh.write(json.dumps({"_id": doc_id, "title": "", "text": text}, ensure_ascii=False) + "\n")
    with open(path / "queries.jsonl", "w", encoding="utf-8") as fh:
        for qid, text in eval_set.queries.items():
            fh.write(json.dumps({"_id": qid, "text": text}, ensure_ascii=False) + "\n")
    with open(path / "qrels" / "test.tsv", "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t")
        writer.writerow(QRELS_HEADER)
        for qid in sorted(eval_set.qrels):
            for doc_id, grade in sorted(eval_set.qrels[qid].items()):
                writer.writerow((qid, doc_id, grade))


def qrel_stats(eval_set: EvalSet) -> Dict[str, float]:
    """Summary counts for the build manifest."""
    per_query = [len(v) for v in eval_set.qrels.values()]
    return {
        "queries": len(eval_set.queries),
        "judgements": sum(per_query),
        "mean_relevant_per_query": round(sum(per_query) / len(per_query), 2) if per_query else 0.0,
    }


# --------------------------------------------------------------------------- database access

def fetch_judgements(cur) -> Tuple[list, list, Dict[str, str], list]:
    """Read statements, evidence, research questions and document scores."""
    cur.execute(
        """SELECT s.statement_id::text, s.statement_text, d.id::text
             FROM factcheck.statements s
             LEFT JOIN public.document d
               ON d.external_id = s.input_statement_id
              AND d.source_id = (SELECT id FROM public.sources WHERE name = %s)
            ORDER BY s.statement_id""",
        (PUBMED_SOURCE_NAME,),
    )
    statements = cur.fetchall()
    cur.execute(
        """SELECT a.statement_id::text, e.document_id::text, e.relevance_score
             FROM factcheck.evidence e
             JOIN factcheck.ai_evaluations a ON a.evaluation_id = e.evaluation_id
            WHERE e.document_id IS NOT NULL"""
    )
    evidence = cur.fetchall()
    # Order by the qualified bigint column: a bare name would sort by the ::text alias.
    cur.execute("SELECT rq.research_question_id::text, rq.question_text "
                "FROM audit.research_questions rq ORDER BY rq.research_question_id")
    questions = {qid: text for qid, text in cur.fetchall() if text}
    cur.execute("SELECT research_question_id::text, document_id::text, relevance_score "
                "FROM audit.document_scores WHERE document_id IS NOT NULL")
    scores = cur.fetchall()
    return statements, evidence, questions, scores


def fetch_abstracts(cur, doc_ids: Sequence[str]) -> Dict[str, str]:
    """Fetch cleaned abstracts for ``doc_ids``; documents without one are omitted."""
    cur.execute("SELECT id::text, abstract FROM public.document WHERE id = ANY(%s)",
                ([int(d) for d in doc_ids],))
    out = {doc_id: clean_abstract(abstract) for doc_id, abstract in cur.fetchall()}
    return {k: v for k, v in out.items() if v}


def sample_distractors(cur, wanted: int, exclude: Set[str], seed: int) -> Dict[str, str]:
    """Collect ``wanted`` random PubMed abstracts (repeatable TABLESAMPLE)."""
    found: Dict[str, str] = {}
    for round_no in range(MAX_SAMPLE_ROUNDS):
        if len(found) >= wanted:
            break
        cur.execute(
            """SELECT id::text, abstract FROM public.document
                 TABLESAMPLE SYSTEM (%s) REPEATABLE (%s)
                WHERE source_id = (SELECT id FROM public.sources WHERE name = %s)
                  AND length(abstract) >= %s""",
            (SAMPLE_PERCENT, seed + round_no, PUBMED_SOURCE_NAME, MIN_ABSTRACT_CHARS),
        )
        for doc_id, abstract in cur.fetchall():
            if doc_id in exclude or doc_id in found:
                continue
            text = clean_abstract(abstract)
            if text:
                found[doc_id] = text
        logger.info("distractor sampling round %d: %d collected", round_no + 1, len(found))
    if len(found) < wanted:
        logger.warning("only %d of %d distractors collected", len(found), wanted)
    return dict(sorted(found.items(), key=lambda kv: int(kv[0]))[:wanted])


# --------------------------------------------------------------------------- main

def drop_missing_docs(eval_set: EvalSet, corpus: Mapping[str, str]) -> EvalSet:
    """Remove judgements for documents absent from the corpus (no abstract)."""
    dropped = 0
    qrels: Qrels = {}
    for qid, row in eval_set.qrels.items():
        kept = {d: g for d, g in row.items() if d in corpus}
        dropped += len(row) - len(kept)
        if kept:
            qrels[qid] = kept
    queries = {q: t for q, t in eval_set.queries.items() if q in qrels}
    notes = eval_set.notes + [f"{dropped} judgements dropped (document has no abstract)"]
    return EvalSet(eval_set.name, queries, qrels, notes)


def build(output_dir: Path, distractors: int, seed: int) -> Dict[str, object]:
    """Read the database, build all evaluation sets and write them; returns the manifest."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
    from bmlibrarian.database import get_db_manager

    db = get_db_manager()
    with db.get_connection() as conn, conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute("SELECT current_database()")
        database = cur.fetchone()[0]
        statements, evidence, questions, scores = fetch_judgements(cur)
        source_set, graded_set = build_pubmedqa_sets(statements, evidence)
        research_set = build_research_set(questions, scores)
        # Every judged document joins the corpus, including low-scored ones:
        # they were retrieved for the query, so they are realistic hard negatives.
        judged_ids = sorted({d for s in (source_set, graded_set, research_set)
                             for row in s.qrels.values() for d in row}
                            | {doc for _, doc, _ in scores}
                            | {doc for _, doc, _ in evidence}, key=int)
        logger.info("fetching %d judged documents", len(judged_ids))
        judged = fetch_abstracts(cur, judged_ids)
        corpus = dict(judged)
        corpus.update(sample_distractors(cur, distractors, set(judged_ids), seed))

    sets = [drop_missing_docs(s, corpus) for s in (source_set, graded_set, research_set)]
    set_info: Dict[str, Dict[str, object]] = {}
    manifest: Dict[str, object] = {
        "database": database,
        "seed": seed,
        "corpus_documents": len(corpus),
        "judged_documents": len(judged),
        "distractor_documents": len(corpus) - len(judged),
        "document_text": "abstract only (no title), Markdown emphasis stripped",
        "sets": set_info,
    }
    for eval_set in sets:
        path = output_dir / eval_set.name / CACHE_SAFE_DIR_NAME
        write_beir_dir(path, corpus, eval_set)
        set_info[eval_set.name] = {"path": str(path), **qrel_stats(eval_set),
                                           "notes": eval_set.notes}
        logger.info("wrote %s: %s", path, qrel_stats(eval_set))
    with open(output_dir / "manifest.json", "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    return manifest


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--distractors", type=int, default=DEFAULT_DISTRACTORS,
                   help="random PubMed abstracts added as non-relevant documents")
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = p.parse_args(argv)
    if args.distractors < 0:
        p.error("--distractors must be >= 0")
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args(argv)
    try:
        manifest = build(args.output_dir.expanduser(), args.distractors, args.seed)
    except Exception as exc:  # report any DB/IO failure to the user, then exit non-zero
        logger.error("building the evaluation sets failed: %s", exc)
        return 1
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
