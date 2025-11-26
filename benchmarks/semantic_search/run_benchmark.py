#!/usr/bin/env python3
"""
Benchmark script for SemanticQueryAgent.

This script evaluates the semantic search and Q&A capabilities by:
1. Loading benchmark questions from JSON files
2. Ensuring the document is in the database with full-text and embeddings
3. Running each question through the SemanticQueryAgent + LLM
4. Comparing answers to expected values
5. Generating detailed statistics and results

Supports multiple search modes:
- semantic: Pure semantic similarity search (default, baseline)
- hybrid: Combined semantic + keyword search with RRF fusion
- expanded: Hybrid search with query expansion (best for factual queries)

Usage:
    uv run python benchmarks/semantic_search/run_benchmark.py bm1.json
    uv run python benchmarks/semantic_search/run_benchmark.py bm1.json --output results.json
    uv run python benchmarks/semantic_search/run_benchmark.py bm1.json --mode hybrid
    uv run python benchmarks/semantic_search/run_benchmark.py bm1.json --mode expanded
    uv run python benchmarks/semantic_search/run_benchmark.py bm1.json --skip-download
"""

import argparse
import json
import logging
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class QuestionResult:
    """Result for a single benchmark question."""

    question: str
    expected: str
    got: str
    correct: bool
    similarity_score: float  # How similar the answer is (for partial matches)
    chunks_used: int
    threshold_used: float
    iterations: int
    queries_tried: int
    processing_time_seconds: float
    error: Optional[str] = None


@dataclass
class BenchmarkMetadata:
    """Metadata for the benchmark run."""

    benchmark_file: str
    doi: str
    pmid: int
    document_id: Optional[int]
    document_title: str
    qa_model: str
    qa_temperature: float
    embedding_model: str
    chunk_size: int
    chunk_overlap: int
    initial_threshold: float
    adaptive_search_enabled: bool
    run_timestamp: str
    total_questions: int
    unique_questions: int
    search_mode: str = "semantic"  # semantic, hybrid, or expanded


@dataclass
class BenchmarkResults:
    """Complete benchmark results."""

    metadata: BenchmarkMetadata
    results: List[QuestionResult] = field(default_factory=list)
    statistics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "metadata": asdict(self.metadata),
            "results": [asdict(r) for r in self.results],
            "statistics": self.statistics,
        }


def normalize_answer(answer: str) -> str:
    """
    Normalize an answer for comparison.

    Handles common variations like:
    - Whitespace differences
    - Case differences for text answers
    - Percentage symbol variations (66.7% vs 66.7)
    - Number formatting (1.03 vs 1.030)
    """
    answer = answer.strip().lower()

    # Remove trailing percentage signs for comparison
    # but keep track if it was a percentage
    is_percentage = answer.endswith("%")
    if is_percentage:
        answer = answer[:-1].strip()

    # Try to normalize as number
    try:
        num = float(answer)
        # Round to reasonable precision
        if num == int(num):
            return str(int(num))
        return f"{num:.2f}".rstrip("0").rstrip(".")
    except ValueError:
        pass

    return answer


def extract_answer_from_response(response: str, expected: str) -> str:
    """
    Extract the actual answer from an LLM response.

    The LLM often provides context around the answer. This function
    attempts to extract just the relevant value.
    """
    response = response.strip()

    # If the response is very short, it's probably just the answer
    if len(response) < 50:
        # Extract numbers or short phrases
        # Try to find a number if expected is numeric
        try:
            float(normalize_answer(expected))
            # Expected is numeric, look for numbers in response
            numbers = re.findall(r"[\d.]+%?", response)
            if numbers:
                # Return the first number found
                return numbers[0]
        except ValueError:
            pass

        return response

    # For longer responses, try to extract the key value
    # Look for patterns like "The answer is X" or "X was the median"

    # Pattern: "is X" or "was X" or "were X"
    patterns = [
        r"(?:is|was|were|had|have)\s+(\d+\.?\d*%?)",
        r"(\d+\.?\d*%?)\s+(?:participants|patients|subjects)",
        r"median\s+(?:was|is|of)?\s*(\d+\.?\d*)",
        r"(\d+\.?\d*%?)\s*(?:\.|$)",
    ]

    for pattern in patterns:
        match = re.search(pattern, response, re.IGNORECASE)
        if match:
            return match.group(1)

    # For text answers, look for quoted values or specific words
    if not any(c.isdigit() for c in expected):
        # Expected is text, look for it in response
        if expected.lower() in response.lower():
            return expected

    # Default: return first line or first sentence
    first_line = response.split("\n")[0]
    if len(first_line) < 100:
        return first_line

    first_sentence = response.split(".")[0]
    return first_sentence


def compare_answers(got: str, expected: str) -> tuple[bool, float]:
    """
    Compare two answers and return (is_correct, similarity_score).

    Returns:
        Tuple of (exact_match: bool, similarity: float 0.0-1.0)
    """
    got_norm = normalize_answer(got)
    expected_norm = normalize_answer(expected)

    # Exact match
    if got_norm == expected_norm:
        return True, 1.0

    # Check if one contains the other
    if got_norm in expected_norm or expected_norm in got_norm:
        return True, 0.9

    # For numeric values, check if they're close
    try:
        got_num = float(got_norm.replace("%", ""))
        expected_num = float(expected_norm.replace("%", ""))

        # Allow 1% tolerance for rounding differences
        if abs(got_num - expected_num) < 0.1:
            return True, 0.95
        if abs(got_num - expected_num) / max(abs(expected_num), 1) < 0.05:
            return True, 0.9

    except ValueError:
        pass

    return False, 0.0


def get_document_by_pmid(pmid: int) -> Optional[Dict[str, Any]]:
    """Look up document in database by PMID."""
    try:
        from bmlibrarian.database import get_db_manager

        db = get_db_manager()
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, title, abstract, full_text, doi
                    FROM document
                    WHERE external_id = %s
                    """,
                    (str(pmid),),
                )
                row = cur.fetchone()
                if row:
                    return {
                        "id": row[0],
                        "title": row[1],
                        "abstract": row[2],
                        "full_text": row[3],
                        "doi": row[4],
                    }
        return None
    except Exception as e:
        logger.error(f"Database lookup failed: {e}")
        return None


def get_document_by_doi(doi: str) -> Optional[Dict[str, Any]]:
    """Look up document in database by DOI."""
    try:
        from bmlibrarian.database import get_db_manager

        db = get_db_manager()
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, title, abstract, full_text, external_id
                    FROM document
                    WHERE doi = %s
                    """,
                    (doi,),
                )
                row = cur.fetchone()
                if row:
                    return {
                        "id": row[0],
                        "title": row[1],
                        "abstract": row[2],
                        "full_text": row[3],
                        "pmid": row[4],
                    }
        return None
    except Exception as e:
        logger.error(f"Database lookup failed: {e}")
        return None


def ensure_document_embedded(document_id: int) -> bool:
    """
    Ensure document has full-text chunks with embeddings.

    Returns True if embeddings exist or were successfully created.
    """
    try:
        from bmlibrarian.embeddings.chunk_embedder import ChunkEmbedder

        embedder = ChunkEmbedder()

        # Check if chunks already exist
        if embedder.has_chunks(document_id):
            logger.info(f"Document {document_id} already has embeddings")
            return True

        # Check if full_text exists
        full_text = embedder.get_document_full_text(document_id)
        if not full_text:
            logger.warning(f"Document {document_id} has no full_text to embed")
            return False

        # Generate chunks and embeddings
        logger.info(f"Generating embeddings for document {document_id}...")
        num_chunks = embedder.chunk_and_embed(document_id, overwrite=False)

        if num_chunks > 0:
            logger.info(f"Created {num_chunks} chunks for document {document_id}")
            return True
        else:
            logger.warning(f"Failed to create chunks for document {document_id}")
            return False

    except Exception as e:
        logger.error(f"Embedding failed: {e}")
        return False


def get_embedding_config() -> Dict[str, Any]:
    """Get current embedding configuration."""
    try:
        from bmlibrarian.config import get_config
        from bmlibrarian.embeddings.chunk_embedder import (
            DEFAULT_CHUNK_SIZE,
            DEFAULT_CHUNK_OVERLAP,
            DEFAULT_EMBEDDING_MODEL_NAME,
        )

        config = get_config()
        embeddings_config = config.get("embeddings", {})

        return {
            "model": embeddings_config.get("model", DEFAULT_EMBEDDING_MODEL_NAME),
            "chunk_size": embeddings_config.get("chunk_size", DEFAULT_CHUNK_SIZE),
            "chunk_overlap": embeddings_config.get("chunk_overlap", DEFAULT_CHUNK_OVERLAP),
            "backend": embeddings_config.get("backend", "ollama"),
        }
    except Exception:
        return {
            "model": "snowflake-arctic-embed2:latest",
            "chunk_size": 1000,
            "chunk_overlap": 100,
            "backend": "ollama",
        }


def run_question(
    document_id: int,
    question: str,
    model: str,
    temperature: float,
    initial_threshold: float,
    use_adaptive: bool,
    search_mode: str = "semantic",
) -> Dict[str, Any]:
    """
    Run a single question through the Q&A system.

    Args:
        document_id: Document to search.
        question: Question to answer.
        model: LLM model for generating answer.
        temperature: LLM temperature.
        initial_threshold: Starting similarity threshold.
        use_adaptive: Whether to use adaptive threshold adjustment.
        search_mode: "semantic", "hybrid", or "expanded".

    Returns dict with answer and metadata.
    """
    try:
        # Import modules needed for direct Q&A
        from bmlibrarian.database import get_db_manager
        from bmlibrarian.agents.semantic_query_agent import SemanticQueryAgent, SearchMode
        import ollama

        start_time = time.time()

        db_manager = get_db_manager()

        # Use SemanticQueryAgent directly to bypass config overrides
        agent = SemanticQueryAgent(initial_threshold=initial_threshold)

        # Select search method based on mode
        if search_mode == "expanded":
            # Use hybrid search with query expansion
            search_result = agent.search_with_expansion(
                document_id=document_id,
                query=question,
                min_results=1,
                max_results=5,
                use_fulltext=True,
                db_manager=db_manager,
                search_mode=SearchMode.HYBRID,
            )
        elif search_mode == "hybrid":
            # Use hybrid search (semantic + keyword)
            search_result = agent.search_document(
                document_id=document_id,
                query=question,
                min_results=1,
                max_results=5,
                use_fulltext=True,
                db_manager=db_manager,
                search_mode=SearchMode.HYBRID,
            )
        else:
            # Default: pure semantic search
            search_result = agent.search_document(
                document_id=document_id,
                query=question,
                min_results=1,
                max_results=5,
                use_fulltext=True,
                db_manager=db_manager,
                search_mode=SearchMode.SEMANTIC,
            )

        if not search_result.success or not search_result.chunks:
            return {
                "answer": "No relevant content found in document.",
                "success": False,
                "error": search_result.message or "No chunks found",
                "chunks_used": 0,
                "processing_time": time.time() - start_time,
                "source": "none",
                "threshold_used": search_result.threshold_used,
                "iterations": search_result.iterations,
                "queries_tried": len(search_result.queries_tried),
            }

        # Build context from chunks
        context_text = "\n\n---\n\n".join(
            f"[Chunk {c.chunk_no + 1}, Score: {c.score:.2f}]\n{c.text}"
            for c in search_result.chunks
        )

        # Generate answer using LLM
        system_prompt = """You are a biomedical research assistant. Answer questions based ONLY on the provided context.
If the context contains the answer, provide it concisely - ideally as a single number, percentage, or short phrase.
If the context doesn't contain enough information, say "Information not found in context"."""

        user_prompt = f"""Context from document:
{context_text}

Question: {question}

Answer with just the relevant value (number, percentage, or short phrase):"""

        client = ollama.Client()
        response = client.chat(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            options={"temperature": temperature},
        )

        answer = response["message"]["content"].strip()

        elapsed = time.time() - start_time

        return {
            "answer": answer,
            "success": True,
            "error": None,
            "chunks_used": len(search_result.chunks),
            "processing_time": elapsed,
            "source": "fulltext_semantic",
            "threshold_used": search_result.threshold_used,
            "iterations": search_result.iterations,
            "queries_tried": len(search_result.queries_tried),
        }

    except Exception as e:
        logger.error(f"Question failed: {e}")
        return {
            "answer": "",
            "success": False,
            "error": str(e),
            "chunks_used": 0,
            "processing_time": 0,
            "source": "error",
            "threshold_used": initial_threshold,
            "iterations": 0,
            "queries_tried": 0,
        }


def run_benchmark(
    benchmark_file: Path,
    output_file: Optional[Path],
    model: str,
    temperature: float,
    initial_threshold: float,
    use_adaptive: bool,
    skip_download: bool,
    limit: Optional[int],
    search_mode: str = "semantic",
) -> BenchmarkResults:
    """
    Run the full benchmark.

    Args:
        benchmark_file: Path to benchmark JSON file
        output_file: Path to save results (optional)
        model: LLM model for Q&A
        temperature: LLM temperature
        initial_threshold: Starting similarity threshold
        use_adaptive: Whether to use adaptive search
        skip_download: Skip PDF download attempts
        limit: Limit number of questions (for testing)
        search_mode: "semantic", "hybrid", or "expanded"

    Returns:
        BenchmarkResults with all data
    """
    # Load benchmark
    logger.info(f"Loading benchmark from {benchmark_file}")
    with open(benchmark_file) as f:
        benchmark_data = json.load(f)

    doi = benchmark_data.get("doi", "")
    pmid = benchmark_data.get("PMID", 0)
    questions = benchmark_data.get("QA", [])

    # De-duplicate questions (benchmark has duplicates)
    seen_questions = set()
    unique_questions = []
    for q in questions:
        q_text = q["question"]
        if q_text not in seen_questions:
            seen_questions.add(q_text)
            unique_questions.append(q)

    logger.info(
        f"Loaded {len(questions)} questions ({len(unique_questions)} unique) "
        f"for DOI: {doi}, PMID: {pmid}"
    )

    if limit:
        unique_questions = unique_questions[:limit]
        logger.info(f"Limited to {limit} questions")

    # Find document in database
    document = None
    if pmid:
        document = get_document_by_pmid(pmid)
    if not document and doi:
        document = get_document_by_doi(doi)

    if not document:
        logger.error(f"Document not found in database (PMID: {pmid}, DOI: {doi})")
        logger.error("Please import the document first using pubmed_import_cli.py or pdf_import_cli.py")
        sys.exit(1)

    document_id = document["id"]
    document_title = document.get("title", "N/A")
    logger.info(f"Found document ID: {document_id}, Title: {document_title[:60]}...")

    # Warn about potential document mismatch
    # Check if first few questions mention terms not in title
    sample_questions = " ".join(q["question"] for q in unique_questions[:5]).lower()
    title_lower = document_title.lower()
    mismatch_keywords = ["covid", "sars", "viral", "vaccine", "infection"]
    for keyword in mismatch_keywords:
        if keyword in sample_questions and keyword not in title_lower:
            logger.warning(
                f"⚠️  Potential mismatch: questions mention '{keyword}' but document title doesn't. "
                f"Verify the benchmark file has correct DOI/PMID."
            )
            break

    # Check if full-text exists
    if not document.get("full_text"):
        logger.warning("Document has no full-text. Results may be limited to abstract.")
        if not skip_download:
            logger.info("Attempting to download full-text PDF...")
            # Could add PDF download logic here
            pass

    # Ensure embeddings exist
    if not ensure_document_embedded(document_id):
        logger.error("Failed to create embeddings for document")
        sys.exit(1)

    # Get embedding config for metadata
    embedding_config = get_embedding_config()

    # Create metadata
    metadata = BenchmarkMetadata(
        benchmark_file=str(benchmark_file),
        doi=doi,
        pmid=pmid,
        document_id=document_id,
        document_title=document_title,
        qa_model=model,
        qa_temperature=temperature,
        embedding_model=embedding_config["model"],
        chunk_size=embedding_config["chunk_size"],
        chunk_overlap=embedding_config["chunk_overlap"],
        initial_threshold=initial_threshold,
        adaptive_search_enabled=use_adaptive,
        run_timestamp=datetime.now().isoformat(),
        total_questions=len(questions),
        unique_questions=len(unique_questions),
        search_mode=search_mode,
    )

    logger.info(f"Search mode: {search_mode}")

    # Run questions
    results = BenchmarkResults(metadata=metadata)
    correct_count = 0
    total_time = 0.0

    for i, qa in enumerate(unique_questions):
        question = qa["question"]
        expected = qa["answer"]

        logger.info(f"\n[{i+1}/{len(unique_questions)}] Q: {question}")
        logger.info(f"    Expected: {expected}")

        # Run question
        qa_result = run_question(
            document_id=document_id,
            question=question,
            model=model,
            temperature=temperature,
            initial_threshold=initial_threshold,
            use_adaptive=use_adaptive,
            search_mode=search_mode,
        )

        # Extract and compare answer
        raw_answer = qa_result["answer"]
        extracted = extract_answer_from_response(raw_answer, expected)
        is_correct, similarity = compare_answers(extracted, expected)

        if is_correct:
            correct_count += 1
            logger.info(f"    Got: {extracted} ✓")
        else:
            logger.info(f"    Got: {extracted} ✗")
            if len(raw_answer) > 100:
                logger.debug(f"    Full response: {raw_answer[:200]}...")

        total_time += qa_result["processing_time"]

        # Create result
        result = QuestionResult(
            question=question,
            expected=expected,
            got=extracted,
            correct=is_correct,
            similarity_score=similarity,
            chunks_used=qa_result["chunks_used"],
            threshold_used=qa_result.get("threshold_used", initial_threshold),
            iterations=qa_result.get("iterations", 1),
            queries_tried=qa_result.get("queries_tried", 1),
            processing_time_seconds=qa_result["processing_time"],
            error=qa_result.get("error"),
        )
        results.results.append(result)

    # Calculate statistics
    accuracy = correct_count / len(unique_questions) if unique_questions else 0
    avg_time = total_time / len(unique_questions) if unique_questions else 0

    results.statistics = {
        "total_questions": len(unique_questions),
        "correct": correct_count,
        "incorrect": len(unique_questions) - correct_count,
        "accuracy": accuracy,
        "accuracy_percent": f"{accuracy * 100:.1f}%",
        "total_time_seconds": total_time,
        "avg_time_per_question": avg_time,
        "questions_with_errors": sum(1 for r in results.results if r.error),
    }

    # Print summary
    print("\n" + "=" * 60)
    print("BENCHMARK RESULTS")
    print("=" * 60)
    print(f"Document: PMID {pmid} / DOI {doi}")
    print(f"Model: {model}")
    print(f"Search mode: {search_mode}")
    print(f"Questions: {len(unique_questions)} unique (of {len(questions)} total)")
    print(f"Correct: {correct_count}/{len(unique_questions)} ({accuracy * 100:.1f}%)")
    print(f"Total time: {total_time:.1f}s (avg {avg_time:.2f}s/question)")
    print("=" * 60)

    # Show incorrect answers
    incorrect = [r for r in results.results if not r.correct]
    if incorrect:
        print(f"\nIncorrect answers ({len(incorrect)}):")
        for r in incorrect[:10]:  # Show first 10
            print(f"  Q: {r.question[:60]}...")
            print(f"     Expected: {r.expected}, Got: {r.got}")

    # Save results
    if output_file:
        with open(output_file, "w") as f:
            json.dump(results.to_dict(), f, indent=2)
        logger.info(f"\nResults saved to {output_file}")

    return results


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run semantic search benchmarks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    uv run python benchmarks/semantic_search/run_benchmark.py bm1.json
    uv run python benchmarks/semantic_search/run_benchmark.py bm1.json --output results.json
    uv run python benchmarks/semantic_search/run_benchmark.py bm1.json --mode hybrid
    uv run python benchmarks/semantic_search/run_benchmark.py bm1.json --mode expanded
    uv run python benchmarks/semantic_search/run_benchmark.py bm1.json --limit 5  # Quick test
        """,
    )

    parser.add_argument(
        "benchmark_file",
        type=Path,
        help="Path to benchmark JSON file",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        help="Output file for results JSON",
    )
    parser.add_argument(
        "--mode",
        choices=["semantic", "hybrid", "expanded"],
        default="semantic",
        help="Search mode: semantic (pure similarity), hybrid (semantic+keyword), "
             "expanded (hybrid with query expansion). Default: semantic",
    )
    parser.add_argument(
        "--model",
        default="gpt-oss:20b",
        help="LLM model for Q&A (default: gpt-oss:20b)",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.1,
        help="LLM temperature (default: 0.1 for deterministic answers)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help="Initial similarity threshold (default: 0.5)",
    )
    parser.add_argument(
        "--no-adaptive",
        action="store_true",
        help="Disable adaptive search (use fixed threshold)",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip PDF download attempts",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of questions (for testing)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Resolve benchmark file path
    benchmark_file = args.benchmark_file
    if not benchmark_file.is_absolute():
        # Try relative to script directory first
        script_dir = Path(__file__).parent
        if (script_dir / benchmark_file).exists():
            benchmark_file = script_dir / benchmark_file
        elif not benchmark_file.exists():
            logger.error(f"Benchmark file not found: {benchmark_file}")
            sys.exit(1)

    # Generate default output filename if not specified
    output_file = args.output
    if not output_file:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = benchmark_file.parent / f"results_{benchmark_file.stem}_{timestamp}.json"

    # Run benchmark
    run_benchmark(
        benchmark_file=benchmark_file,
        output_file=output_file,
        model=args.model,
        temperature=args.temperature,
        initial_threshold=args.threshold,
        use_adaptive=not args.no_adaptive,
        skip_download=args.skip_download,
        limit=args.limit,
        search_mode=args.mode,
    )


if __name__ == "__main__":
    main()
