#!/usr/bin/env python3
"""Performance test for spaCy-based sentence-aware chunker.

This script tests the performance of the sentence_aware_chunker on 1000 real
documents from the database, measuring throughput, chunk statistics, and
identifying potential bottlenecks.
"""

import time
import statistics
from typing import List, Dict, Any
from pathlib import Path
import sys

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from bmlibrarian.database import DatabaseManager
from bmlibrarian.embeddings.spacy_chunker import sentence_aware_chunker


def fetch_test_documents(db: DatabaseManager, limit: int = 1000) -> List[Dict[str, Any]]:
    """Fetch documents with non-empty full_text from the database.

    Args:
        db: DatabaseManager instance
        limit: Maximum number of documents to fetch

    Returns:
        List of document dictionaries containing id and full_text
    """
    print(f"Fetching {limit} documents with full_text...")

    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, full_text,
                       LENGTH(full_text) as text_length
                FROM document
                WHERE full_text IS NOT NULL
                  AND full_text != ''
                  AND LENGTH(full_text) > 100
                ORDER BY id
                LIMIT %s
            """, (limit,))

            documents = []
            for row in cur.fetchall():
                documents.append({
                    'id': row[0],
                    'full_text': row[1],
                    'text_length': row[2]
                })

    print(f"Fetched {len(documents)} documents")
    return documents


def test_chunker_performance(
    documents: List[Dict[str, Any]],
    max_chars: int = 1800,
    overlap_chars: int = 320
) -> Dict[str, Any]:
    """Test the performance of sentence_aware_chunker on a set of documents.

    Args:
        documents: List of document dictionaries with 'id', 'full_text', 'text_length'
        max_chars: Maximum chunk size in characters
        overlap_chars: Overlap between chunks in characters

    Returns:
        Dictionary containing performance statistics
    """
    print(f"\nTesting chunker with max_chars={max_chars}, overlap_chars={overlap_chars}")
    print("=" * 80)

    # Statistics tracking
    total_docs = len(documents)
    total_chunks = 0
    total_chars_processed = 0
    processing_times = []
    chunks_per_doc = []
    chunk_sizes = []
    overlap_sizes = []

    # Progress tracking
    start_time = time.time()
    last_progress_time = start_time

    # Process each document
    for idx, doc in enumerate(documents):
        doc_start = time.time()

        # Chunk the document
        chunks = sentence_aware_chunker(
            doc['full_text'],
            max_chars=max_chars,
            overlap_chars=overlap_chars
        )

        doc_end = time.time()
        doc_time = doc_end - doc_start

        # Record statistics
        processing_times.append(doc_time)
        chunks_per_doc.append(len(chunks))
        total_chunks += len(chunks)
        total_chars_processed += doc['text_length']

        # Track chunk sizes
        for chunk in chunks:
            chunk_sizes.append(len(chunk))

        # Calculate overlap sizes (for chunks after the first)
        if len(chunks) > 1:
            for i in range(1, len(chunks)):
                # Simple overlap estimation
                overlap_sizes.append(min(len(chunks[i]), overlap_chars))

        # Progress reporting every 10 seconds
        current_time = time.time()
        if current_time - last_progress_time >= 10.0:
            elapsed = current_time - start_time
            docs_per_sec = (idx + 1) / elapsed
            eta_seconds = (total_docs - idx - 1) / docs_per_sec if docs_per_sec > 0 else 0
            print(f"Progress: {idx+1}/{total_docs} docs ({(idx+1)/total_docs*100:.1f}%) | "
                  f"Speed: {docs_per_sec:.2f} docs/sec | "
                  f"ETA: {eta_seconds:.0f}s")
            last_progress_time = current_time

    total_time = time.time() - start_time

    # Calculate statistics
    stats = {
        # Overall performance
        'total_documents': total_docs,
        'total_chunks': total_chunks,
        'total_chars_processed': total_chars_processed,
        'total_time_seconds': total_time,
        'docs_per_second': total_docs / total_time,
        'chars_per_second': total_chars_processed / total_time,
        'chunks_per_second': total_chunks / total_time,

        # Per-document statistics
        'avg_time_per_doc': statistics.mean(processing_times),
        'median_time_per_doc': statistics.median(processing_times),
        'min_time_per_doc': min(processing_times),
        'max_time_per_doc': max(processing_times),
        'stdev_time_per_doc': statistics.stdev(processing_times) if len(processing_times) > 1 else 0,

        # Chunk statistics
        'avg_chunks_per_doc': statistics.mean(chunks_per_doc),
        'median_chunks_per_doc': statistics.median(chunks_per_doc),
        'min_chunks_per_doc': min(chunks_per_doc),
        'max_chunks_per_doc': max(chunks_per_doc),

        # Chunk size statistics
        'avg_chunk_size': statistics.mean(chunk_sizes),
        'median_chunk_size': statistics.median(chunk_sizes),
        'min_chunk_size': min(chunk_sizes),
        'max_chunk_size': max(chunk_sizes),

        # Overlap statistics
        'avg_overlap_size': statistics.mean(overlap_sizes) if overlap_sizes else 0,
        'median_overlap_size': statistics.median(overlap_sizes) if overlap_sizes else 0,

        # Configuration
        'max_chars': max_chars,
        'overlap_chars': overlap_chars,
    }

    return stats


def print_statistics(stats: Dict[str, Any]) -> None:
    """Print performance statistics in a formatted manner.

    Args:
        stats: Dictionary containing performance statistics
    """
    print("\n" + "=" * 80)
    print("PERFORMANCE STATISTICS")
    print("=" * 80)

    print("\nCONFIGURATION:")
    print(f"  Max chunk size:       {stats['max_chars']:,} characters")
    print(f"  Overlap size:         {stats['overlap_chars']:,} characters")

    print("\nOVERALL PERFORMANCE:")
    print(f"  Total documents:      {stats['total_documents']:,}")
    print(f"  Total chunks:         {stats['total_chunks']:,}")
    print(f"  Total characters:     {stats['total_chars_processed']:,}")
    print(f"  Total time:           {stats['total_time_seconds']:.2f} seconds")
    print(f"  Throughput:           {stats['docs_per_second']:.2f} docs/second")
    print(f"  Throughput:           {stats['chars_per_second']:,.0f} chars/second")
    print(f"  Throughput:           {stats['chunks_per_second']:.2f} chunks/second")

    print("\nPER-DOCUMENT STATISTICS:")
    print(f"  Average time:         {stats['avg_time_per_doc']*1000:.2f} ms")
    print(f"  Median time:          {stats['median_time_per_doc']*1000:.2f} ms")
    print(f"  Min time:             {stats['min_time_per_doc']*1000:.2f} ms")
    print(f"  Max time:             {stats['max_time_per_doc']*1000:.2f} ms")
    print(f"  Std deviation:        {stats['stdev_time_per_doc']*1000:.2f} ms")

    print("\nCHUNKS PER DOCUMENT:")
    print(f"  Average:              {stats['avg_chunks_per_doc']:.2f}")
    print(f"  Median:               {stats['median_chunks_per_doc']:.1f}")
    print(f"  Min:                  {stats['min_chunks_per_doc']}")
    print(f"  Max:                  {stats['max_chunks_per_doc']}")

    print("\nCHUNK SIZE STATISTICS:")
    print(f"  Average:              {stats['avg_chunk_size']:.0f} characters")
    print(f"  Median:               {stats['median_chunk_size']:.0f} characters")
    print(f"  Min:                  {stats['min_chunk_size']:,} characters")
    print(f"  Max:                  {stats['max_chunk_size']:,} characters")

    print("\nOVERLAP STATISTICS:")
    print(f"  Average:              {stats['avg_overlap_size']:.0f} characters")
    print(f"  Median:               {stats['median_overlap_size']:.0f} characters")

    print("\n" + "=" * 80)


def analyze_slowest_documents(
    documents: List[Dict[str, Any]],
    processing_times: List[float],
    top_n: int = 10
) -> None:
    """Analyze the slowest documents to identify bottlenecks.

    Args:
        documents: List of document dictionaries
        processing_times: List of processing times for each document
        top_n: Number of slowest documents to analyze
    """
    # Pair documents with their processing times
    doc_times = list(zip(documents, processing_times))
    doc_times.sort(key=lambda x: x[1], reverse=True)

    print("\n" + "=" * 80)
    print(f"TOP {top_n} SLOWEST DOCUMENTS")
    print("=" * 80)
    print(f"{'Doc ID':<10} {'Time (ms)':<12} {'Text Length':<15} {'Chars/sec':<12}")
    print("-" * 80)

    for doc, proc_time in doc_times[:top_n]:
        chars_per_sec = doc['text_length'] / proc_time if proc_time > 0 else 0
        print(f"{doc['id']:<10} {proc_time*1000:<12.2f} {doc['text_length']:<15,} {chars_per_sec:<12,.0f}")

    print("=" * 80)


def main():
    """Main test execution function."""
    print("SpaCy Chunker Performance Test")
    print("=" * 80)

    # Initialize database connection
    print("Initializing database connection...")
    db = DatabaseManager()

    # Fetch test documents
    documents = fetch_test_documents(db, limit=1000)

    if not documents:
        print("ERROR: No documents found with full_text!")
        return 1

    # Run performance test
    stats = test_chunker_performance(documents)

    # Print results
    print_statistics(stats)

    # Calculate processing times for analysis
    processing_times = []
    for doc in documents:
        start = time.time()
        sentence_aware_chunker(doc['full_text'])
        processing_times.append(time.time() - start)

    # Analyze slowest documents
    analyze_slowest_documents(documents, processing_times, top_n=10)

    # Print summary recommendations
    print("\nRECOMMENDATIONS:")
    if stats['docs_per_second'] < 10:
        print("  ⚠ Low throughput detected. Consider:")
        print("    - Using a lighter spaCy model (en_core_web_sm)")
        print("    - Implementing batch processing with nlp.pipe()")
        print("    - Pre-loading the spaCy model once instead of per-chunk")

    if stats['avg_time_per_doc'] > 1.0:
        print("  ⚠ High per-document processing time. Consider:")
        print("    - Disabling unnecessary spaCy pipeline components")
        print("    - Using multi-threading for parallel document processing")

    if stats['max_chunk_size'] > stats['max_chars'] * 1.5:
        print("  ⚠ Some chunks exceed target size significantly")
        print("    - Review sentence segmentation logic")
        print("    - Consider sentence splitting for very long sentences")

    print("\n✓ Performance test completed successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
