#!/usr/bin/env python3
"""Example script showing how to use the find_abstracts API."""

from datetime import date
import bmlibrarian

def search_example():
    """Example of searching for abstracts."""
    print("BMLibrarian Abstract Search Example")
    print("=" * 40)
    
    # Example 1: Basic search
    print("Searching for 'machine learning' papers...")
    count = 0
    for doc in bmlibrarian.find_abstracts("machine learning", max_rows=3):
        count += 1
        print(f"\n{count}. {doc['title']}")
        print(f"   Authors: {', '.join(doc['authors'][:2]) if doc['authors'] else 'N/A'}")
        print(f"   Published: {doc['publication_date']}")
        print(f"   Source: {doc['source_name']}")
    
    print(f"\nFound {count} machine learning papers")
    
    # Example 2: Advanced query syntax
    print("\n" + "=" * 40)
    print("Advanced query: 'diabetes & treatment'...")
    
    advanced_count = 0
    for doc in bmlibrarian.find_abstracts(
        "diabetes & treatment", 
        max_rows=2, 
        plain=False  # Use advanced syntax
    ):
        advanced_count += 1
        print(f"{advanced_count}. {doc['title'][:80]}...")
        print(f"   DOI: {doc['doi'] or 'N/A'}")
    
    # Example 3: Source filtering
    print("\n" + "=" * 40)
    print("Searching PubMed only for 'cancer'...")
    
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
    
    # Example 4: Date filtering
    print("\n" + "=" * 40)
    print("Recent COVID papers (2023-2024)...")
    
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
    
    # Example 5: Keyword analysis
    print("\n" + "=" * 40)
    print("Keywords from cancer research papers...")
    
    keywords_set = set()
    for doc in bmlibrarian.find_abstracts("cancer", max_rows=5):
        if doc['keywords']:
            keywords_set.update(doc['keywords'][:3])  # Take first 3 keywords
        if len(keywords_set) >= 10:
            break
    
    print("Common keywords:", ", ".join(list(keywords_set)[:10]))
    
    # Clean up
    bmlibrarian.close_database()
    print("\nSearch complete!")

if __name__ == "__main__":
    search_example()