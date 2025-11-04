#!/usr/bin/env python3
"""Benchmark multi-model query generation performance.

This script compares single-model (baseline) vs multi-model query generation
to measure performance overhead and document coverage improvements.

Usage:
    uv run python scripts/benchmark_multi_model.py

Requirements:
    - Ollama running with required models
    - Database connection available
    - Models: medgemma-27b-text-it-Q8_0:latest, gpt-oss:20b

Output:
    - Timing for single-model baseline
    - Timing for multi-model (2 models, 1 query each)
    - Overhead percentage
    - Document count comparisons
"""

import time
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bmlibrarian.agents import QueryAgent
from bmlibrarian.config import get_config, DEFAULT_CONFIG


def benchmark_single_model(questions: list[str]) -> dict:
    """Benchmark original single-model behavior.

    Args:
        questions: List of research questions to test

    Returns:
        dict with timing and document count results
    """
    print("\n" + "="*70)
    print("SINGLE-MODEL BASELINE (Original Behavior)")
    print("="*70)

    # Get config and ensure multi-model is disabled
    config = get_config()
    original_enabled = config.get("query_generation", {}).get("multi_model_enabled", False)

    # Temporarily disable multi-model
    if "query_generation" not in config:
        config["query_generation"] = DEFAULT_CONFIG["query_generation"].copy()
    config["query_generation"]["multi_model_enabled"] = False

    agent = QueryAgent()

    times = []
    doc_counts = []

    for i, question in enumerate(questions, 1):
        print(f"\n[{i}/{len(questions)}] Question: {question[:60]}...")

        start = time.time()
        docs = list(agent.find_abstracts(question, max_rows=50))
        elapsed = time.time() - start

        times.append(elapsed)
        doc_counts.append(len(docs))

        print(f"  → {len(docs)} documents in {elapsed:.2f}s")

    # Restore original setting
    config["query_generation"]["multi_model_enabled"] = original_enabled

    avg_time = sum(times) / len(times)
    avg_docs = sum(doc_counts) / len(doc_counts)

    print(f"\nSingle-Model Summary:")
    print(f"  Average time: {avg_time:.2f}s")
    print(f"  Average docs: {avg_docs:.1f}")

    return {
        "times": times,
        "doc_counts": doc_counts,
        "avg_time": avg_time,
        "avg_docs": avg_docs
    }


def benchmark_multi_model(questions: list[str], num_models: int = 2) -> dict:
    """Benchmark multi-model behavior.

    Args:
        questions: List of research questions to test
        num_models: Number of models to use (2 or 3)

    Returns:
        dict with timing and document count results
    """
    print("\n" + "="*70)
    print(f"MULTI-MODEL ({num_models} models, 1 query each)")
    print("="*70)

    # Get config and enable multi-model
    config = get_config()
    if "query_generation" not in config:
        config["query_generation"] = DEFAULT_CONFIG["query_generation"].copy()

    config["query_generation"]["multi_model_enabled"] = True

    if num_models == 2:
        config["query_generation"]["models"] = [
            "medgemma-27b-text-it-Q8_0:latest",
            "gpt-oss:20b"
        ]
    else:  # 3 models
        config["query_generation"]["models"] = [
            "medgemma-27b-text-it-Q8_0:latest",
            "gpt-oss:20b",
            "medgemma4B_it_q8:latest"
        ]

    config["query_generation"]["queries_per_model"] = 1

    agent = QueryAgent()

    times = []
    doc_counts = []

    for i, question in enumerate(questions, 1):
        print(f"\n[{i}/{len(questions)}] Question: {question[:60]}...")

        start = time.time()
        docs = list(agent.find_abstracts_multi_query(
            question,
            max_rows=50,
            human_in_the_loop=False  # Automated for benchmark
        ))
        elapsed = time.time() - start

        times.append(elapsed)
        doc_counts.append(len(docs))

        print(f"  → {len(docs)} documents in {elapsed:.2f}s")

    avg_time = sum(times) / len(times)
    avg_docs = sum(doc_counts) / len(doc_counts)

    print(f"\nMulti-Model Summary ({num_models} models):")
    print(f"  Average time: {avg_time:.2f}s")
    print(f"  Average docs: {avg_docs:.1f}")

    return {
        "times": times,
        "doc_counts": doc_counts,
        "avg_time": avg_time,
        "avg_docs": avg_docs
    }


def print_comparison(single_results: dict, multi_results: dict, num_models: int = 2):
    """Print comparison summary.

    Args:
        single_results: Results from single-model benchmark
        multi_results: Results from multi-model benchmark
        num_models: Number of models used in multi-model
    """
    print("\n" + "="*70)
    print("RESULTS SUMMARY")
    print("="*70)

    print("\nTiming Comparison:")
    print(f"  Single-model:  {single_results['avg_time']:.2f}s")
    print(f"  Multi-model:   {multi_results['avg_time']:.2f}s")

    overhead_pct = ((multi_results['avg_time'] / single_results['avg_time']) - 1) * 100
    print(f"  Overhead:      {overhead_pct:+.1f}%")

    print("\nDocument Coverage:")
    print(f"  Single-model:  {single_results['avg_docs']:.1f} documents")
    print(f"  Multi-model:   {multi_results['avg_docs']:.1f} documents")

    if single_results['avg_docs'] > 0:
        improvement_pct = ((multi_results['avg_docs'] / single_results['avg_docs']) - 1) * 100
        print(f"  Improvement:   {improvement_pct:+.1f}%")
    else:
        print(f"  Improvement:   N/A (no single-model documents)")

    print("\nTrade-off Analysis:")
    if overhead_pct > 0 and improvement_pct > 0:
        efficiency = improvement_pct / overhead_pct
        print(f"  For every 1% slowdown, you get {efficiency:.2f}% more documents")

    print("\nRecommendation:")
    if overhead_pct < 150 and improvement_pct > 20:
        print("  ✓ Multi-model is recommended (good coverage/speed trade-off)")
    elif overhead_pct < 100:
        print("  ✓ Multi-model has minimal overhead")
    else:
        print("  ⚠ Multi-model has significant overhead, use for comprehensive searches only")

    print("="*70)


def main():
    """Run benchmarks and print results."""
    print("="*70)
    print("Multi-Model Query Generation Benchmark")
    print("="*70)
    print("\nThis benchmark compares:")
    print("  1. Single-model (baseline)")
    print("  2. Multi-model with 2 models")
    print("\nTest questions:")

    # Test questions covering different topics
    questions = [
        "What are the cardiovascular benefits of exercise?",
        "How does diabetes affect kidney function?",
        "What are the side effects of statins?",
    ]

    for i, q in enumerate(questions, 1):
        print(f"  {i}. {q}")

    print("\nStarting benchmarks...")
    print("(This will take several minutes)")

    try:
        # Run single-model baseline
        single_results = benchmark_single_model(questions)

        # Run multi-model (2 models)
        multi_results = benchmark_multi_model(questions, num_models=2)

        # Print comparison
        print_comparison(single_results, multi_results, num_models=2)

    except KeyboardInterrupt:
        print("\n\nBenchmark interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nError during benchmark: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print("\nBenchmark complete!")


if __name__ == "__main__":
    main()
