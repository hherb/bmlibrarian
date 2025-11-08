#!/usr/bin/env python3
"""
Smart hybrid search that balances sensitivity and specificity.
Uses selective keyword expansion for high-value terms only.
"""

import os
import time
import requests
import psycopg
from typing import List, Tuple, Optional, Set
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


# Medical domain synonyms for common concepts
MEDICAL_SYNONYMS = {
    'mountain': ['altitude', 'high-altitude', 'elevation', 'hypobaric'],
    'acute': ['rapid', 'sudden', 'abrupt'],
    'prevention': ['prophylaxis', 'prophylactic', 'preventive', 'preventative'],
    'treatment': ['therapy', 'therapeutic', 'intervention', 'management'],
    'effective': ['efficacy', 'effectiveness', 'efficacious', 'beneficial'],
    'drug': ['medication', 'pharmaceutical', 'pharmacologic', 'agent'],
    'study': ['trial', 'research', 'investigation', 'analysis', 'review'],
}


def extract_highly_selective_keywords(text: str) -> Set[str]:
    """
    Extract only highly selective keywords that are likely unique to the domain.
    These are terms that will have high precision for filtering.

    Returns keywords that should use OR logic (high recall).
    """
    text_lower = text.lower()
    selective_keywords = set()

    # Drug names are highly selective
    drug_patterns = [
        r'\b(acetazolamide|dexamethasone|methylprednisolone|ibuprofen|nifedipine)\b',
        r'\b(sildenafil|tadalafil|theophylline|aspirin|ginkgo)\b',
    ]

    # Disease/condition names are highly selective
    condition_patterns = [
        r'\b(mountain\s+sickness|altitude\s+sickness|hace|hape)\b',
        r'\b(edema|oedema|hypoxia|hypoxemia)\b',
    ]

    # Extract drug names
    for pattern in drug_patterns:
        matches = re.findall(pattern, text_lower)
        selective_keywords.update(matches)

    # Extract condition names
    for pattern in condition_patterns:
        matches = re.findall(pattern, text_lower)
        # Keep multi-word phrases intact
        selective_keywords.update([m.replace(' ', '_') for m in matches])

    # Extract key single words that are domain-specific
    key_terms = ['mountain', 'altitude', 'prophylaxis', 'prophylactic']
    words = re.findall(r'\b[a-z]+\b', text_lower)
    for term in key_terms:
        if term in words:
            selective_keywords.add(term)

    return selective_keywords


def expand_keywords_with_synonyms(keywords: Set[str]) -> Set[str]:
    """
    Expand keywords with medical synonyms for better recall.
    Only expand selective terms to avoid over-broadening.
    """
    expanded = set(keywords)

    for keyword in keywords:
        # Handle underscored phrases
        base_keyword = keyword.replace('_', ' ')

        # Check for synonyms
        for key, synonyms in MEDICAL_SYNONYMS.items():
            if key in base_keyword or base_keyword in key:
                # Add all synonyms
                expanded.update(synonyms)
                expanded.add(key)

    return expanded


def smart_hybrid_search(
    search_phrase: str,
    top_k: int = 10,
    vector_search_limit: int = 100,
    use_synonym_expansion: bool = True
) -> List[Tuple[str, float, str]]:
    """
    Smart hybrid search with selective keyword filtering and synonym expansion.

    Strategy:
    1. Extract highly selective keywords (drug names, specific conditions)
    2. Optionally expand with medical synonyms for better recall
    3. Use OR logic for keywords (high sensitivity)
    4. Perform vector search only on pre-filtered subset

    Args:
        search_phrase: Text to search for
        top_k: Number of final results to return
        vector_search_limit: Max results from vector search on filtered set
        use_synonym_expansion: Whether to expand keywords with synonyms

    Returns:
        List of (document_title, similarity_score, strategy) tuples
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
    print(f"Searching for: '{search_phrase}'")
    print("=" * 80)
    embed_start = time.time()
    query_embedding = get_embedding(search_phrase)
    embed_time = time.time() - embed_start
    print(f"✓ Embedding generation: {embed_time:.3f}s")

    # Extract selective keywords
    selective_keywords = extract_highly_selective_keywords(search_phrase)

    if not selective_keywords:
        print("⚠ No selective keywords found - using pure vector search")
        strategy = "pure_vector"
        fulltext_filter = False
    else:
        strategy = "hybrid"
        fulltext_filter = True

        # Expand with synonyms if enabled
        if use_synonym_expansion:
            search_keywords = expand_keywords_with_synonyms(selective_keywords)
            print(f"✓ Selective keywords: {selective_keywords}")
            print(f"✓ Expanded with synonyms: {search_keywords - selective_keywords}")
        else:
            search_keywords = selective_keywords
            print(f"✓ Using selective keywords: {selective_keywords}")

    # Perform search
    search_start = time.time()

    with psycopg.connect(**db_params) as conn:
        with conn.cursor() as cur:

            if fulltext_filter:
                # Build tsquery with OR logic (use | for OR)
                # Handle underscored phrases by converting back to phrases
                tsquery_terms = []
                for kw in search_keywords:
                    if '_' in kw:
                        # Multi-word phrase: use <-> for adjacency
                        words = kw.split('_')
                        phrase_query = ' <-> '.join(words)
                        tsquery_terms.append(f"({phrase_query})")
                    else:
                        tsquery_terms.append(kw)

                tsquery = ' | '.join(tsquery_terms)
                print(f"✓ Full-text query: {tsquery}")

                # First, check how many chunks match the full-text filter
                cur.execute("""
                    SELECT COUNT(*) FROM chunks WHERE text_search @@ to_tsquery('english', %s)
                """, (tsquery,))
                fulltext_matches = cur.fetchone()[0]
                print(f"✓ Full-text pre-filter matches: {fulltext_matches:,} chunks")

                if fulltext_matches == 0:
                    print("⚠ No full-text matches - falling back to pure vector search")
                    fulltext_filter = False
                elif fulltext_matches > 100000:
                    print(f"⚠ Too many matches ({fulltext_matches:,}) - keywords too broad")
                    print("  Consider using more selective terms or pure vector search")

            if fulltext_filter and fulltext_matches > 0:
                # Hybrid search with full-text pre-filter
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
                cur.execute(sql, (query_embedding, tsquery, vector_search_limit))
            else:
                # Pure vector search (no pre-filter)
                print("⚠ Using pure vector search (slow with m=6 index)")
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
                strategy = "pure_vector"

            results = cur.fetchall()

    search_time = time.time() - search_start
    print(f"✓ Database search: {search_time:.3f}s")
    print(f"✓ Total time: {embed_time + search_time:.3f}s")
    print(f"✓ Strategy used: {strategy}")

    # Add strategy to results
    return [(title, score, strategy) for title, score in results[:top_k]]


if __name__ == "__main__":
    import sys

    # Get search phrase from command line or use default
    if len(sys.argv) > 1:
        search_phrase = " ".join(sys.argv[1:])
    else:
        search_phrase = input("Enter search phrase: ")

    print("\n")

    try:
        results = smart_hybrid_search(search_phrase, top_k=10, vector_search_limit=100)

        if results:
            print(f"\n{len(results)} results:\n")
            for i, (title, score, strategy) in enumerate(results, 1):
                print(f"{i:2d}. [{score:.4f}] {title}")
        else:
            print("\nNo results found.")

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
