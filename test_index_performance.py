#!/usr/bin/env python3
"""
Quick benchmark script to test HNSW index performance
Tests semantic search with the new arctic_hnsw_idx_v4 index
"""

import time
import psycopg
from pathlib import Path
import json
import ollama

def load_config():
    """Load database configuration"""
    config_path = Path.home() / ".bmlibrarian" / "config.json"
    if config_path.exists():
        with open(config_path) as f:
            return json.load(f)
    return {}

def get_embedding_for_text(text: str) -> list[float]:
    """Get embedding from Ollama for search text"""
    response = ollama.embed(
        model="snowflake-arctic-embed2:latest",
        input=text
    )
    return response['embeddings'][0]

def benchmark_semantic_search(query_text: str, k: int = 10):
    """Benchmark semantic search with HNSW index"""

    print(f"Query: {query_text}")
    print(f"Retrieving top {k} results\n")

    # Get embedding
    print("Generating embedding...")
    embed_start = time.time()
    embedding = get_embedding_for_text(query_text)
    embed_time = time.time() - embed_start
    print(f"✓ Embedding generated in {embed_time:.2f}s\n")

    # Connect to database
    conn = psycopg.connect("dbname=knowledgebase")

    # Run search with timing
    print("Running semantic search...")
    search_start = time.time()

    with conn.cursor() as cur:
        # Set ef_search parameter for better recall
        cur.execute("SET hnsw.ef_search = 64;")

        # Execute search query
        cur.execute("""
            SELECT
                c.document_id,
                c.chunk_no,
                c.text,
                e.embedding <=> %s::vector AS distance,
                c.document_title
            FROM emb_1024 e
            JOIN chunks c ON c.id = e.chunk_id
            ORDER BY e.embedding <=> %s::vector
            LIMIT %s;
        """, (embedding, embedding, k))

        results = cur.fetchall()

    search_time = time.time() - search_start

    print(f"✓ Search completed in {search_time:.2f}s")
    print(f"✓ Total time: {embed_time + search_time:.2f}s\n")

    # Display results
    print("=" * 80)
    print("TOP RESULTS:")
    print("=" * 80)

    for i, (doc_id, chunk_num, text, distance, title) in enumerate(results[:5], 1):
        print(f"\n{i}. Distance: {distance:.4f}")
        print(f"   Document ID: {doc_id}")
        print(f"   Title: {title[:70] if title else 'N/A'}...")
        print(f"   Chunk {chunk_num}: {text[:200] if text else 'N/A'}...")

    conn.close()

    return {
        'embed_time': embed_time,
        'search_time': search_time,
        'total_time': embed_time + search_time,
        'results': len(results)
    }

if __name__ == "__main__":
    import sys

    # Default test query
    query = "prophylactic methylprednisolone mountain sickness"

    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])

    print("=" * 80)
    print("HNSW INDEX PERFORMANCE BENCHMARK")
    print("=" * 80)
    print(f"Index: arctic_hnsw_idx_v4 (m=16, ef_construction=80)")
    print(f"Search parameter: ef_search=64")
    print("=" * 80)
    print()

    try:
        stats = benchmark_semantic_search(query)

        print("\n" + "=" * 80)
        print("PERFORMANCE SUMMARY")
        print("=" * 80)
        print(f"Embedding time:  {stats['embed_time']:.2f}s")
        print(f"Search time:     {stats['search_time']:.2f}s")
        print(f"Total time:      {stats['total_time']:.2f}s")
        print(f"Results found:   {stats['results']}")
        print()
        print("Expected performance: 15-25s total (with new index)")
        print("Previous performance: ~290s (without optimized index)")
        print("=" * 80)

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
