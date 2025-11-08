#!/usr/bin/env python3
"""
Test different HNSW ef_search values to see if they improve performance.
"""

import os
import time
import requests
import psycopg
from typing import List


def get_embedding(text: str, model: str = "snowflake-arctic-embed2:latest") -> List[float]:
    """Generate embedding for text using Ollama."""
    ollama_url = os.getenv("OLLAMA_HOST", "http://localhost:11434")

    response = requests.post(
        f"{ollama_url}/api/embed",
        json={"model": model, "input": text},
        timeout=30
    )
    response.raise_for_status()

    result = response.json()
    return result["embeddings"][0]


def test_search_with_ef(search_phrase: str, ef_search: int, top_k: int = 10):
    """Test search performance with a specific ef_search value."""
    db_params = {
        "dbname": os.getenv("POSTGRES_DB", "knowledgebase"),
        "user": os.getenv("POSTGRES_USER"),
        "password": os.getenv("POSTGRES_PASSWORD"),
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": os.getenv("POSTGRES_PORT", "5432")
    }

    # Generate embedding
    print(f"\n{'='*80}")
    print(f"Testing with ef_search = {ef_search}")
    print(f"{'='*80}")

    embed_start = time.time()
    query_embedding = get_embedding(search_phrase)
    embed_time = time.time() - embed_start
    print(f"Embedding generation: {embed_time:.3f}s")

    # Perform search with specific ef_search
    search_start = time.time()
    with psycopg.connect(**db_params) as conn:
        with conn.cursor() as cur:
            # Set ef_search for this session
            cur.execute(f"SET hnsw.ef_search = {ef_search}")

            sql = """
                SELECT d.title,
                       1 - distance AS similarity
                FROM (
                    SELECT c.document_id,
                           e.embedding <=> %s::vector AS distance
                    FROM emb_1024 e
                    JOIN chunks c ON e.chunk_id = c.id
                    WHERE e.model_id = 1
                    ORDER BY distance
                    LIMIT %s
                ) AS ranked
                JOIN document d ON ranked.document_id = d.id
            """

            cur.execute(sql, (query_embedding, top_k))
            results = cur.fetchall()

    search_time = time.time() - search_start
    total_time = embed_time + search_time

    print(f"Database search: {search_time:.3f}s")
    print(f"Total time: {total_time:.3f}s")
    print(f"Found {len(results)} results")

    if results:
        print(f"\nTop 3 results:")
        for i, (title, score) in enumerate(results[:3], 1):
            print(f"  {i}. [{score:.4f}] {title[:80]}")

    return total_time, len(results)


if __name__ == "__main__":
    import sys

    # Get search phrase
    if len(sys.argv) > 1:
        search_phrase = " ".join(sys.argv[1:])
    else:
        search_phrase = "Is prophylactic administration of methylprednisolone effective for preventing acute mountain sickness?"

    print(f"Search phrase: '{search_phrase}'")
    print(f"\nTesting different ef_search values to find optimal setting...")

    # Test different ef_search values
    ef_values = [40, 100, 200, 400]  # 40 is default
    results = {}

    for ef in ef_values:
        try:
            total_time, num_results = test_search_with_ef(search_phrase, ef, top_k=10)
            results[ef] = (total_time, num_results)
        except Exception as e:
            print(f"\nError with ef_search={ef}: {e}")
            results[ef] = (None, None)

    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"\n{'ef_search':<12} {'Time (s)':<12} {'Results':<10} {'vs Default':<15}")
    print("-" * 50)

    baseline_time = results.get(40, (None, None))[0]

    for ef in ef_values:
        time_val, num_res = results[ef]
        if time_val is not None:
            if baseline_time and ef != 40:
                speedup = baseline_time / time_val
                vs_default = f"{speedup:.2f}x"
            else:
                vs_default = "baseline"
            print(f"{ef:<12} {time_val:<12.3f} {num_res:<10} {vs_default:<15}")
        else:
            print(f"{ef:<12} {'ERROR':<12} {'-':<10} {'-':<15}")

    print("\n" + "="*80)
    print("CONCLUSION")
    print("="*80)

    if baseline_time:
        best_ef = min([ef for ef in ef_values if results[ef][0] is not None],
                     key=lambda ef: results[ef][0])
        best_time = results[best_ef][0]
        improvement = baseline_time / best_time if best_ef != 40 else 1.0

        print(f"\nBest ef_search value: {best_ef}")
        print(f"Best time: {best_time:.3f}s")

        if improvement > 1.1:
            print(f"Improvement: {improvement:.2f}x faster than default")
            print(f"\n✓ Setting ef_search={best_ef} helps!")
            print(f"  Add to your queries: SET hnsw.ef_search = {best_ef};")
        else:
            print(f"\n✗ ef_search tuning provides minimal benefit (<10% improvement)")
            print(f"  The m=6 index is the real bottleneck.")
            print(f"  You need to rebuild the index with higher m value.")
    else:
        print("\n✗ All tests failed - check your database connection")
