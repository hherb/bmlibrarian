#!/usr/bin/env python3
"""
Test script for hybrid search integration.
Tests the complete workflow including audit trail.
"""

import json
from bmlibrarian.database import search_hybrid

def test_hybrid_search():
    """Test hybrid search with a simple query."""
    print("=" * 80)
    print("HYBRID SEARCH TEST")
    print("=" * 80)
    print()

    # Test query
    search_text = "diabetes treatment"
    query_text = "diabetes & treatment"

    print(f"Search text (for semantic): {search_text}")
    print(f"Query text (for BM25/fulltext): {query_text}")
    print()

    # Execute hybrid search
    print("Executing hybrid search...")
    documents, strategy_metadata = search_hybrid(
        search_text=search_text,
        query_text=query_text,
        search_config=None  # Will read from config.json
    )

    # Display results
    print(f"\n{'=' * 80}")
    print("SEARCH RESULTS")
    print(f"{'=' * 80}\n")

    print(f"Total documents found: {len(documents)}")
    print()

    # Display strategy metadata
    print(f"{'=' * 80}")
    print("STRATEGY METADATA (for audit trail)")
    print(f"{'=' * 80}\n")

    print(json.dumps(strategy_metadata, indent=2))
    print()

    # Display first few documents
    if documents:
        print(f"{'=' * 80}")
        print("SAMPLE DOCUMENTS (first 3)")
        print(f"{'=' * 80}\n")

        for i, doc in enumerate(documents[:3], 1):
            print(f"Document {i}:")
            print(f"  ID: {doc.get('id')}")
            print(f"  Title: {doc.get('title', 'N/A')[:80]}...")
            print(f"  Source: {doc.get('source_name', 'N/A')}")

            # Show search scores if available
            if '_search_scores' in doc:
                scores = doc['_search_scores']
                sem = scores.get('semantic', None)
                bm = scores.get('bm25', None)
                ft = scores.get('fulltext', None)
                comb = scores.get('combined', None)
                print(f"  Scores: semantic={sem if sem is not None else 'N/A'}, "
                      f"bm25={bm if bm is not None else 'N/A'}, "
                      f"fulltext={ft if ft is not None else 'N/A'}, "
                      f"combined={comb if comb is not None else 'N/A'}")
            print()

    print(f"{'=' * 80}")
    print("TEST COMPLETE")
    print(f"{'=' * 80}")

if __name__ == "__main__":
    test_hybrid_search()
