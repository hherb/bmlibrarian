#!/usr/bin/env python3
"""Example script showing how to use the find_abstracts API."""

from datetime import date
import time
import bmlibrarian

def search_example():
    """Example of searching for abstracts."""
    print("BMLibrarian Abstract Search Example")
    print("=" * 40)
    
    # Start overall timer
    overall_start = time.time()
    
    # Example 1: Basic search (without ranking)
    print("Searching for 'machine learning' papers (no ranking)...")
    query_start = time.time()
    count = 0
    for doc in bmlibrarian.find_abstracts("machine learning", max_rows=3, use_ranking=False):
        count += 1
        print(f"\n{count}. {doc['title']}")
        print(f"   Authors: {', '.join(doc['authors'][:2]) if doc['authors'] else 'N/A'}")
        print(f"   Published: {doc['publication_date']}")
        print(f"   Source: {doc['source_name']}")
    
    query_time = time.time() - query_start
    print(f"\nFound {count} machine learning papers (No ranking: {query_time:.3f}s)")
    
    # Example 1b: Same search with ranking
    print("\nSearching for 'machine learning' papers (with ranking)...")
    query_start = time.time()
    count = 0
    for doc in bmlibrarian.find_abstracts("machine learning", max_rows=3, use_ranking=True):
        count += 1
        print(f"\n{count}. {doc['title']}")
        print(f"   Authors: {', '.join(doc['authors'][:2]) if doc['authors'] else 'N/A'}")
        print(f"   Published: {doc['publication_date']}")
        print(f"   Source: {doc['source_name']}")
    
    query_time = time.time() - query_start
    print(f"\nFound {count} machine learning papers (With ranking: {query_time:.3f}s)")
    
    # Example 2: Advanced query syntax (no ranking)
    print("\n" + "=" * 40)
    print("Advanced query: 'diabetes & treatment' (no ranking)...")
    
    query_start = time.time()
    advanced_count = 0
    for doc in bmlibrarian.find_abstracts(
        "diabetes & treatment", 
        max_rows=2, 
        plain=False,  # Use advanced syntax
        use_ranking=False
    ):
        advanced_count += 1
        print(f"{advanced_count}. {doc['title'][:80]}...")
        print(f"   DOI: {doc['doi'] or 'N/A'}")
    
    query_time = time.time() - query_start
    print(f"Advanced query (no ranking) completed in {query_time:.3f}s")
    
    # Example 2b: Same query with ranking
    print("\nAdvanced query: 'diabetes & treatment' (with ranking)...")
    
    query_start = time.time()
    advanced_count = 0
    for doc in bmlibrarian.find_abstracts(
        "diabetes & treatment", 
        max_rows=2, 
        plain=False,  # Use advanced syntax
        use_ranking=True
    ):
        advanced_count += 1
        print(f"{advanced_count}. {doc['title'][:80]}...")
        print(f"   DOI: {doc['doi'] or 'N/A'}")
    
    query_time = time.time() - query_start
    print(f"Advanced query (with ranking) completed in {query_time:.3f}s")
    
    # Example 3: Source filtering
    print("\n" + "=" * 40)
    print("Searching PubMed only for 'cancer'...")
    
    query_start = time.time()
    pubmed_count = 0
    for doc in bmlibrarian.find_abstracts(
        "cancer", 
        max_rows=2, 
        use_pubmed=True, 
        use_medrxiv=False, 
        use_others=False
    ):
        pubmed_count += 1
        print(f"{pubmed_count}. {doc['title'][:80]}...")
        print(f"   DOI: {doc['doi'] or 'N/A'}")
    
    query_time = time.time() - query_start
    print(f"PubMed filtering query completed in {query_time:.3f}s")
    
    # Example 4: Date filtering
    print("\n" + "=" * 40)
    print("Recent COVID papers (2023-2024)...")
    
    query_start = time.time()
    recent_count = 0
    for doc in bmlibrarian.find_abstracts(
        "covid", 
        max_rows=3,
        from_date=date(2023, 1, 1),
        to_date=date(2024, 12, 31)
    ):
        recent_count += 1
        pub_date = doc['publication_date'] or 'Unknown'
        print(f"{recent_count}. {doc['title'][:60]}... ({pub_date})")
    
    query_time = time.time() - query_start
    print(f"Date filtering query completed in {query_time:.3f}s")
    
    # Example 5: Keyword analysis
    print("\n" + "=" * 40)
    print("Keywords from cancer research papers...")
    
    query_start = time.time()
    keywords_set = set()
    for doc in bmlibrarian.find_abstracts("cancer", max_rows=5):
        if doc['keywords']:
            keywords_set.update(doc['keywords'][:3])  # Take first 3 keywords
        if len(keywords_set) >= 10:
            break
    
    query_time = time.time() - query_start
    print("Common keywords:", ", ".join(list(keywords_set)[:10]))
    print(f"Keyword analysis completed in {query_time:.3f}s")
    
    # Example 6: Complex medical query (no ranking)
    print("\n" + "=" * 40)
    print("Complex medical query: ONSD & ICP & ultrasound (no ranking)...")
    
    query_start = time.time()
    complex_count = 0
    complex_query = "(ONSD | 'optic nerve sheath diameter') & (ICP | 'intracranial pressure'| 'intra-cranial pressure' | 'intra cranial pressure') & (ultrasound | sonography | sonographic)"
    
    for doc in bmlibrarian.find_abstracts(
        complex_query,
        max_rows=5,
        plain=False,  # Use advanced syntax for complex query
        use_ranking=False
    ):
        complex_count += 1
        print(f"{complex_count}. {doc['title'][:70]}...")
        print(f"   Published: {doc['publication_date']}")
        print(f"   Source: {doc['source_name']}")
    
    query_time = time.time() - query_start
    print(f"Found {complex_count} papers matching complex criteria")
    print(f"Complex medical query (no ranking) completed in {query_time:.3f}s")
    
    # Example 6b: Same complex query with ranking
    print("\nComplex medical query: ONSD & ICP & ultrasound (with ranking)...")
    
    query_start = time.time()
    complex_count = 0
    
    for doc in bmlibrarian.find_abstracts(
        complex_query,
        max_rows=5,
        plain=False,  # Use advanced syntax for complex query
        use_ranking=True
    ):
        complex_count += 1
        print(f"{complex_count}. {doc['title'][:70]}...")
        print(f"   Published: {doc['publication_date']}")
        print(f"   Source: {doc['source_name']}")
    
    query_time = time.time() - query_start
    print(f"Found {complex_count} papers matching complex criteria")
    print(f"Complex medical query (with ranking) completed in {query_time:.3f}s")
    
    # Calculate and display overall time
    overall_time = time.time() - overall_start
    print("\n" + "=" * 40)
    print(f"All queries completed in {overall_time:.3f}s total")
    
    # Clean up
    bmlibrarian.close_database()
    print("\nSearch complete!")

if __name__ == "__main__":
    search_example()