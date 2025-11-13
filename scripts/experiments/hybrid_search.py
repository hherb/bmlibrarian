#!/usr/bin/env python3
"""
Hybrid semantic search combining full-text and vector search.
Uses full-text search to pre-filter candidates before vector similarity.
"""

import os
import time
import requests
import psycopg
from typing import List, Tuple, Optional
import re


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


def extract_keywords(text: str, min_length: int = 4) -> List[str]:
    """Extract meaningful keywords from search phrase."""
    # Remove common stop words
    stop_words = {'what', 'when', 'where', 'which', 'who', 'whom', 'this', 'that',
                  'these', 'those', 'have', 'has', 'had', 'does', 'could', 'would',
                  'should', 'will', 'for', 'the', 'and', 'but', 'not', 'with', 'from'}

    # Split and clean
    words = re.findall(r'\b[a-z]+\b', text.lower())
    keywords = [w for w in words if len(w) >= min_length and w not in stop_words]

    return keywords


def hybrid_search(
    search_phrase: str,
    top_k: int = 10,
    fulltext_limit: Optional[int] = 1000,
    use_fulltext_prefilter: bool = True
) -> List[Tuple[str, float]]:
    """
    Perform hybrid semantic search with optional full-text pre-filtering.

    Args:
        search_phrase: Text to search for
        top_k: Number of final results to return
        fulltext_limit: Max candidates from full-text search (default: 1000, lower is faster)
        use_fulltext_prefilter: Whether to use full-text pre-filtering

    Returns:
        List of (document_title, similarity_score) tuples
    """
    # Database connection parameters
    db_params = {
        "dbname": os.getenv("POSTGRES_DB", "knowledgebase"),
        "user": os.getenv("POSTGRES_USER"),
        "password": os.getenv("POSTGRES_PASSWORD"),
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": os.getenv("POSTGRES_PORT", "5432")
    }

    # Generate embedding for search phrase
    print(f"Generating embedding for: '{search_phrase}'")
    embed_start = time.time()
    query_embedding = get_embedding(search_phrase)
    embed_time = time.time() - embed_start
    print(f"Embedding generation took: {embed_time:.3f}s")

    # Perform search
    search_start = time.time()

    with psycopg.connect(**db_params) as conn:
        with conn.cursor() as cur:

            if use_fulltext_prefilter:
                # Extract keywords for full-text search
                keywords = extract_keywords(search_phrase)
                print(f"Using keywords for pre-filter: {keywords}")

                # Build full-text query (OR combination of keywords)
                tsquery = ' | '.join(keywords)

                sql = """
                    SELECT d.title,
                           1 - distance AS similarity
                    FROM (
                        SELECT c.document_id,
                               e.embedding <=> %s::vector AS distance
                        FROM emb_1024 e
                        JOIN chunks c ON e.chunk_id = c.id
                        WHERE e.model_id = 1
                          AND c.text_search @@ to_tsquery('english', %s)
                        ORDER BY distance
                        LIMIT %s
                    ) AS ranked
                    JOIN document d ON ranked.document_id = d.id
                """

                cur.execute(sql, (query_embedding, tsquery, fulltext_limit or top_k))

            else:
                # Pure vector search (original approach)
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
    print(f"Database search took: {search_time:.3f}s")
    print(f"Total time: {embed_time + search_time:.3f}s")
    print(f"Found {len(results)} results")

    return results[:top_k]


if __name__ == "__main__":
    import sys

    # Get search phrase from command line or use default
    if len(sys.argv) > 1:
        search_phrase = " ".join(sys.argv[1:])
    else:
        search_phrase = input("Enter search phrase: ")

    print(f"\nSearching for: '{search_phrase}'\n")
    print("=" * 80)

    try:
        # Try hybrid search first
        print("\n--- HYBRID SEARCH (Full-text + Vector) ---\n")
        results = hybrid_search(search_phrase, top_k=10, fulltext_limit=10000)

        if results:
            print(f"\nTop {len(results)} matching documents:\n")
            for i, (title, score) in enumerate(results, 1):
                print(f"{i:2d}. [{score:.4f}] {title}")
        else:
            print("No results found.")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
