#!/usr/bin/env python3
"""
Semantic search script for the emb1024 table.
Performs cosine similarity search using Snowflake Arctic embeddings.
"""

import os
import json
import time
import requests
import psycopg
from typing import List, Tuple

MAX_RESULTS=50

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


def semantic_search(search_phrase: str, top_k: int = MAX_RESULTS) -> List[Tuple[str, float]]:
    """
    Perform semantic search on emb1_024 table.

    Args:
        search_phrase: Text to search for
        top_k: Number of results to return (default: 10)

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

    # Perform semantic search using cosine similarity
    search_start = time.time()
    with psycopg.connect(**db_params) as conn:
        with conn.cursor() as cur:
            # Using cosine similarity: 1 - (embedding <=> query_embedding)
            # The <=> operator is cosine distance, so we subtract from 1 for similarity
            # Calculate distance once and reuse in ORDER BY
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

    return results


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
        results = semantic_search(search_phrase, top_k=MAX_RESULTS)

        if results:
            print(f"\nTop {len(results)} matching documents:\n")
            for i, (title, score) in enumerate(results, 1):
                print(f"{i:2d}. [{score:.4f}] {title}")
        else:
            print("No results found.")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
